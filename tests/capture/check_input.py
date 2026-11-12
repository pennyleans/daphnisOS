#!/usr/bin/env python3
"""Exercise the real input modules with isolated device and journal fixtures."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

STUBS = {
    'serial': '''extern unrestricted void fixture_console(U8 byte);
export void serial_putc(U8 byte) { fixture_console(byte); }
export void serial_write[n](in U8[n] bytes) { for i in 0..n { fixture_console(bytes[i]); } }
''',
    'user': '''export extern observe I64 initrd_size();
export extern observe I64 initrd_read(I64 at, out U8[_] bytes);
''',
    'frames': '''export const I64 FRAME_BYTES = 4096;
export const I64 POOL_BASE = 4096;
export I64 alloc(I64 n) { return 0; }
''',
    'phys': '''export extern unrestricted void phys_read8(U64 at, out U8[_] bytes);
export extern unrestricted void phys_write8(U64 at, in U8[_] bytes);
''',
    'sha256': '''export void sha_digest[n, d](in U8[n] bytes, I64 at, I64 nbytes, inout U8[d] outbuf) {
    for i in 0..d { outbuf[i] = 0; }
}
''',
    'virtio': '''export const U16 F_WRITE = 2;
export const U8 S_FAILED = 128;
export const U8 S_ACK = 1;
export const U8 S_DRIVER = 2;
export const U8 S_DRIVER_OK = 4;
extern unrestricted void fixture_forbidden();
export I64 open(U32 id) { fixture_forbidden(); return -1; }
export void accept(I64 io, U32 bits) {}
export U32 features(I64 io) { return 0; }
export I64 queue(I64 io, I64 n) { return -1; }
export I64 queue_size(I64 q) { return 0; }
export void set_status(I64 io, U8 s) {}
export void notify(I64 q) {}
export U8 config8(I64 io, I64 n) { return 0; }
export void post(I64 q, I64 s, U64 at, I64 n, U16 flags, I64 next) {}
export void offer(I64 q, I64 s) {}
export I64 take(I64 q) { return -1; }
export I64 took_len(I64 q) { return 0; }
export I64 last_irq() { return -1; }
export void ack_irq(I64 io) {}
export void no_interrupt(I64 q) {}
export Bool ready(I64 q) { return false; }
''',
    'portio': '''extern unrestricted void fixture_forbidden();
export void port_out8(U16 p, U8 v) { fixture_forbidden(); }
export U8 port_in8(U16 p) { fixture_forbidden(); return 0; }
''',
    'civil': '''export I64 bcd(U8 b) { return -1; }
export I64 epoch_seconds(I64 y, I64 m, I64 d, I64 h, I64 minute, I64 sec) { return -1; }
''',
    'proc': '''import src.serial;
import src.text;
export void put_dec(I64 v) {
    U8[20] d; I64 k = text.dec_digits(v, d);
    for i in 0..k { serial.serial_putc(d[i]); }
}
export void set_realtime(U64 s) { assert(s == 123); }
''',
    'bootarg': '''export Bool has_word[n](in U8[n] word) { return true; }
''',
}

DRIVER = '''import src.serial;
import src.net;
import src.rng;
import src.rtc;
extern observe I64 fixture_case();
void main() {
    I64 c = fixture_case();
    U8[1514] frame;
    U8[256] bytes;
    rng.init();
    if (c == 0 || c == 2) {
        assert(rng.mode() == rng.NONE);
        assert(rng.private_replay());
        assert(rng.draw(bytes, 1) == -1);
        rtc.boot();
    } else if (c == 1 || c == 4) {
        assert(rng.mode() == rng.REPLAY);
        rtc.boot();
        assert(rng.draw(bytes, 256) == 256);
        for i in 0..256 { assert(bytes[i] == (i as U8)); }
        assert(rng.draw(bytes, 1) == -1);
        assert(rng.mode() == rng.NONE);
        if (c == 1) { rtc.boot(); }
    } else if (c == 3) {
        assert(rng.mode() == rng.REPLAY);
        rtc.boot();
        assert(rng.mode() == rng.NONE);
        assert(rng.draw(bytes, 1) == -1);
        rtc.boot();
    } else if (c == 5) {
        assert(rng.mode() == rng.LIVE);
        assert(!rng.private_replay());
        serial.serial_write("rng 1 00\\nrtc 999\\n");
        assert(rng.draw(bytes, 256) == 256);
        for i in 0..256 { assert(bytes[i] == 165); }
    } else if (c == 6) {
        assert(rng.mode() == rng.REPLAY);
        rtc.boot();
        assert(rng.draw(bytes, 1) == -1);
        assert(rng.mode() == rng.NONE);
        rtc.boot();
    } else if (c == 7) {
        assert(rng.mode() == rng.NONE);
        assert(net.init());
        assert(!net.replay_step());
        assert(net.timers() == 0);
        net.tick();
        assert(net.poll(frame) == 4);
        assert(frame[0] == 0xDE && frame[3] == 0xEF);
        assert(!net.replay_step() && net.timers() == 0);
        net.tick();
        assert(net.replay_step() && net.timers() == 1);
        net.tick();
        assert(net.replay_step() && net.timers() == 2);
        net.tick();
        assert(!net.replay_step() && net.timers() == 2);
        net.tick();
        assert(net.poll(frame) == 2);
        assert(frame[0] == 0xCA && frame[1] == 0xFE);
    }
    if (c == 0) {
        assert(!net.init());
    } else if (c == 2 || c == 4) {
        assert(net.init());
        assert(net.mac_byte(0) == 170);
        serial.serial_write("net rx 99 1 ff\\nunfinished ");
        net.tick();
        assert(net.poll(frame) == 1514);
        for i in 0..1514 { assert(frame[i] == ((i % 256) as U8)); }
        assert(net.poll(frame) == 0);
        assert(net.poll(frame) == -1);
    }
}
'''

HOST = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "host.h"
static int scenario(void) { return atoi(getenv("DAPH_INPUT_CASE")); }
static int64_t size_of(const char *name) {
    const char *path = getenv(name);
    if (path == NULL) return -1;
    FILE *f = fopen(path, "rb"); assert(f != NULL);
    assert(fseek(f, 0, SEEK_END) == 0);
    long n = ftell(f); fclose(f); assert(n >= 0); return n;
}
static int64_t read_bytes(const char *name, int64_t offset, const cint_value *out) {
    const char *path = getenv(name);
    if (path == NULL || offset < 0) return -1;
    FILE *f = fopen(path, "rb"); assert(f != NULL);
    assert(fseek(f, (long)offset, SEEK_SET) == 0);
    int64_t n = out->as.view.shape[0], done = 0;
    uint8_t *p = out->as.view.mem.u.host.ptr;
    for (; done < n; done++) {
        int byte = fgetc(f); if (byte == EOF) break;
        p[done * out->as.view.byte_stride[0]] = (uint8_t)byte;
    }
    fclose(f); return done;
}
#define FN(name) static cint_status name(void *u, const cint_value *a, uint32_t n, cint_value *r)
#define UNUSED (void)u; (void)a; (void)n; (void)r
FN(case_row) { UNUSED; r->as.i64 = scenario(); return CINT_OK; }
FN(forbidden) { UNUSED; assert(!"unexpected live device or clock access"); return CINT_OK; }
FN(console) {
    UNUSED; FILE *f = fopen(getenv("DAPH_INPUT_CONSOLE"), "ab"); assert(f);
    fputc((int)a[0].as.u64, f); fclose(f); return CINT_OK;
}
FN(record) {
    UNUSED; FILE *f = fopen(getenv("DAPH_INPUT_RECORD"), "ab"); assert(f);
    uint32_t len = (uint32_t)a[1].as.view.shape[0];
    assert(a[0].as.i64 == 1 || a[0].as.i64 == 2);
    assert(len > 0 && len <= (a[0].as.i64 == 1 ? 3101u : 521u));
    fputc((int)a[0].as.i64, f);
    for (unsigned i = 0; i < 4; i++) fputc((int)((len >> (8u * i)) & 255u), f);
    uint8_t *p = a[1].as.view.mem.u.host.ptr;
    for (uint32_t i = 0; i < len; i++) fputc(p[(int64_t)i * a[1].as.view.byte_stride[0]], f);
    fclose(f); return CINT_OK;
}
FN(journal_size_row) { UNUSED; r->as.i64 = size_of(a[0].as.i64 == 1 ? "DAPH_INPUT_NET" : "DAPH_INPUT_RNG"); return CINT_OK; }
FN(journal_read_row) {
    UNUSED; r->as.i64 = scenario() == 6 ? -1 : read_bytes(a[0].as.i64 == 1 ? "DAPH_INPUT_NET" : "DAPH_INPUT_RNG", a[1].as.i64, &a[2]); return CINT_OK;
}
FN(initrd_size_row) { UNUSED; assert(scenario() == 4 || scenario() == 5); r->as.i64 = size_of("DAPH_INPUT_INITRD"); return CINT_OK; }
FN(initrd_read_row) { UNUSED; assert(scenario() == 4); r->as.i64 = read_bytes("DAPH_INPUT_INITRD", a[0].as.i64, &a[1]); return CINT_OK; }
FN(rdrand_present_row) { UNUSED; assert(scenario() == 5); r->as.i64 = 1; return CINT_OK; }
FN(rdrand_fill_row) {
    UNUSED; assert(scenario() == 5);
    uint8_t *p = a[0].as.view.mem.u.host.ptr;
    for (int64_t i = 0; i < a[0].as.view.shape[0]; i++) p[i * a[0].as.view.byte_stride[0]] = 165;
    r->as.i64 = a[0].as.view.shape[0]; return CINT_OK;
}
static uint8_t memory[70000];
FN(phys_read_row) {
    UNUSED; uint8_t *p = a[1].as.view.mem.u.host.ptr;
    for (int64_t i = 0; i < a[1].as.view.shape[0]; i++) {
        assert(a[0].as.u64 + (uint64_t)i < sizeof memory);
        p[i * a[1].as.view.byte_stride[0]] = memory[a[0].as.u64 + (uint64_t)i];
    }
    return CINT_OK;
}
FN(phys_write_row) {
    UNUSED; uint8_t *p = a[1].as.view.mem.u.host.ptr;
    for (int64_t i = 0; i < a[1].as.view.shape[0]; i++) {
        assert(a[0].as.u64 + (uint64_t)i < sizeof memory);
        memory[a[0].as.u64 + (uint64_t)i] = p[i * a[1].as.view.byte_stride[0]];
    }
    return CINT_OK;
}
const ci_row ci_rows[] = {
    {"phys_read8", phys_read_row}, {"phys_write8", phys_write_row},
    {"fixture_case", case_row}, {"fixture_forbidden", forbidden}, {"fixture_console", console},
    {"journal_record", record}, {"journal_size", journal_size_row}, {"journal_read", journal_read_row},
    {"initrd_size", initrd_size_row}, {"initrd_read", initrd_read_row},
    {"rdrand_present", rdrand_present_row}, {"rdrand_fill", rdrand_fill_row},
};
const uint32_t ci_row_count = sizeof ci_rows / sizeof ci_rows[0];
'''


def run(cmd, **kw):
    p = subprocess.run([str(x) for x in cmd], stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kw)
    if p.returncode:
        raise RuntimeError(p.stdout.decode(errors='replace') + p.stderr.decode(errors='replace'))
    return p.stdout


def cpio(entries):
    result = bytearray()
    for name, data in entries + [('TRAILER!!!', b'')]:
        nm = name.encode() + b'\0'
        fields = [1, 0o100644, 0, 0, 1, 0, len(data), 0, 0, 0, 0, len(nm), 0]
        result.extend(b'070701' + ''.join(f'{x:08x}' for x in fields).encode() + nm)
        result.extend(bytes(-len(result) % 4))
        result.extend(data)
        result.extend(bytes(-len(result) % 4))
    return result


def main():
    if not __debug__:
        raise RuntimeError('checks require assertions enabled')
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--cint', type=Path, required=True)
    ap.add_argument('--toolchain', type=Path, required=True)
    args = ap.parse_args()
    root = Path(__file__).resolve().parents[2]
    out = args.out.resolve()
    assert root != out and root not in out.parents
    out.mkdir(parents=True, exist_ok=True)
    fixture = out / 'fixture'
    (fixture / 'src').mkdir(parents=True, exist_ok=True)
    modules = ['text', 'serial', 'sha256', 'phys', 'frames', 'virtio', 'user', 'cpio', 'net', 'rng', 'portio', 'civil', 'proc', 'bootarg', 'rtc']
    for name in modules:
        target = fixture / f'src/{name}.ci'
        if name in STUBS:
            target.write_text(STUBS[name])
        else:
            shutil.copyfile(root / f'src/{name}.ci', target)
    (fixture / 'driver.ci').write_text(DRIVER)
    host = out / 'host.c'
    host.write_text(HOST)
    run([args.cint, 'emit-c', '--toolchain', args.toolchain.resolve(), '--root', fixture, '--out', out / 'emit',
         *[f'src/{name}.ci' for name in modules], 'driver.ci'], cwd=fixture)
    emitted = out / (out / 'emit/MANIFEST.ref').read_text().split()[0]
    program = emitted / 'cint-program.c'
    entry = re.search(r'\bcg_[0-9A-Za-z_]+_run\b', program.read_text()).group()
    include = next(line.split(' ', 1)[1] for line in args.toolchain.read_text().splitlines() if line.startswith('include '))
    common = ['-std=c17', '-O2', '-Wall', '-Wextra', '-Werror', '-DCINT_RT_HELPERS_PORTABLE', '-I' + include, '-I' + str(root / 'user/ci')]
    mac = b'net mac aa:bb:cc:dd:ee:ff\n'
    rx = b'net rx 1 1514 ' + bytes(i % 256 for i in range(1514)).hex().encode() + b'\n'
    zero = b'net rx 1 0 \n'
    timed1 = b'net rx 1 4 0 deadbeef\n'
    timed2 = b'net rx 5 2 2 cafe\n'
    rtc = b'rtc 123\n'
    rng = b'rng 256 ' + bytes(range(256)).hex().encode() + b'\n'
    live_rng = b'rng 256 ' + bytes([165] * 256).hex().encode() + b'\n'
    cases = [
        (b'', b'', b'', []),
        (b'', rtc + rng, b'', [(2, rtc), (2, rng)]),
        (mac + rx + zero, b'', b'', [(1, mac), (1, rx), (1, zero)]),
        (b'', rtc, b'', [(2, rtc)]),
        (None, None, cpio([('rng.journal', rtc + rng), ('net.journal', mac + rx + zero)]), [(2, rtc), (2, rng), (1, mac), (1, rx), (1, zero)]),
        (None, None, b'', [(2, live_rng)]),
        (b'', rtc + rng, b'', []),
        (mac + timed1 + timed2, b'', b'', [(1, mac), (1, timed1), (1, timed2)]),
    ]
    def rng_mode(data):
        return b'daphnis: rng replay from rng.journal, ' + str(len(data)).encode() + b' bytes\n'

    def net_mode(data):
        return b'daphnis: net replay from net.journal, ' + str(len(data)).encode() + b' bytes\n'

    exhausted = b"daphnis: rng journal: a line that is not the next draw's `rng` record ends the replay\n"
    forged_net = b'net rx 99 1 ff\nunfinished '
    expected_console = [
        b'daphnis: net journal refused: no `net mac` first line\n',
        rng_mode(rtc + rng) + rtc + rng + exhausted,
        net_mode(mac + rx + zero) + mac + forged_net + rx + zero,
        rng_mode(rtc) + rtc,
        rng_mode(rtc + rng) + rtc + rng + exhausted + net_mode(mac + rx + zero) + mac + forged_net + rx + zero,
        b'daphnis: rng rdrand, live\n' + b'rng 1 00\nrtc 999\n' + live_rng,
        rng_mode(rtc + rng) + exhausted,
        net_mode(mac + timed1 + timed2) + mac + timed1 + timed2,
    ]
    receipts = {}
    for cc in ['gcc', 'clang']:
        obj, binary = out / f'{cc}.o', out / f'{cc}-input'
        run([cc, *common, '-Dmain=cint_emitted_main', '-c', program, '-o', obj])
        run([cc, *common, '-DCI_RUN=' + entry, obj, *sorted(p for p in emitted.rglob('*.c') if p != program), root / 'user/ci/main.c', host, Path(include) / 'cint_rt.c', '-o', binary])
        for index, (net, random, initrd, expected) in enumerate(cases):
            env = dict(os.environ)
            env['DAPH_INPUT_CASE'] = str(index)
            for name, data in [('NET', net), ('RNG', random), ('INITRD', initrd)]:
                env.pop('DAPH_INPUT_' + name, None)
                if data is not None:
                    path = out / f'{cc}-{index}-{name.lower()}.bin'
                    path.write_bytes(data)
                    env['DAPH_INPUT_' + name] = str(path)
            record, console = out / f'{cc}-{index}.records', out / f'{cc}-{index}.console'
            record.write_bytes(b'')
            console.write_bytes(b'')
            env['DAPH_INPUT_RECORD'], env['DAPH_INPUT_CONSOLE'] = str(record), str(console)
            run([binary], env=env)
            want = b''.join(bytes([kind]) + len(data).to_bytes(4, 'little') + data for kind, data in expected)
            assert record.read_bytes() == want, (cc, index, 'typed record mismatch')
            assert console.read_bytes() == expected_console[index], (cc, index, 'serial bytes changed')
        receipts[cc] = {'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(), 'cases_passed': len(cases)}
        print(f'{cc}: seven input source and canonical record cases pass')
    paths = ['src/net.ci', 'src/rng.ci', 'src/rtc.ci', 'tests/capture/check_input.py']
    receipts['sources_sha256'] = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in paths}
    receipts['cint_sha256'] = hashlib.sha256(args.cint.read_bytes()).hexdigest()
    receipts['toolchain_sha256'] = hashlib.sha256(args.toolchain.read_bytes()).hexdigest()
    (out / 'input-receipt.json').write_text(json.dumps(receipts, indent=2) + '\n')


if __name__ == '__main__':
    main()
