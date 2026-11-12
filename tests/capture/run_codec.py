#!/usr/bin/env python3
"""Build and run the synthetic capture codec with a test-only host adapter."""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

EXPECTED = (
    'capture: six payload boundaries pass\n'
    'capture: 113 frame-byte mutations rejected\n'
    'capture: header identity and authenticated revision reject changes\n'
    'capture: valid frame from a different chain rejected\n'
    'capture: truncation and short output are atomic\n'
    'capture: wrong key, order, duplicate, trailing data rejected\n'
    'capture: restored writer metadata cannot reuse a nonce\n'
    'capture: authenticated empty stream and incomplete end pass\n'
)


HOST_TEST = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "host.h"

static cint_value scalar(uint16_t tag, uint64_t bits)
{
    cint_value v;
    memset(&v, 0, sizeof v);
    v.kind = CINT_VAL_SCALAR;
    v.type.code = tag;
    v.as.u64 = bits;
    return v;
}

static cint_value view(uint8_t *p, int64_t n, int64_t stride, uint8_t perm)
{
    cint_value v;
    memset(&v, 0, sizeof v);
    v.kind = CINT_VAL_VIEW;
    v.type.code = CINT_TAG_U8;
    v.as.view.type.code = CINT_TAG_U8;
    v.as.view.rank = 1u;
    v.as.view.perm = perm;
    v.as.view.mem.kind = CINT_MEM_HOST;
    v.as.view.mem.u.host.ptr = p;
    v.as.view.shape[0] = n;
    v.as.view.byte_stride[0] = stride;
    v.as.view.reachable_bytes = n > 0 ? (n - 1) * (stride < 0 ? -stride : stride) + 1 : 0;
    return v;
}

static int64_t call(const char *name, cint_value *a, uint32_t n)
{
    cint_value r = scalar(CINT_TAG_I64, 0u);
    for (uint32_t i = 0u; i < ci_row_count; i++) {
        if (strcmp(name, ci_rows[i].name) == 0) {
            assert(ci_rows[i].call(NULL, a, n, &r) == CINT_OK);
            return r.as.i64;
        }
    }
    assert(0);
    return -1;
}

int main(void)
{
    uint8_t stream[32], aad[192], plain[130], cipher[130], tag[32], output[130];
    cint_value f[2] = {scalar(CINT_TAG_I64, 1u), scalar(CINT_TAG_I64, 0u)};
    int64_t writer = call("fixture_slot", f, 2u), reader;
    assert(writer > 0);
    f[0].as.i64 = 0;
    reader = call("fixture_slot", f, 2u);
    assert(reader > writer);
    for (unsigned i = 0u; i < 32u; i++) stream[i] = (uint8_t)(i / 2u);
    for (unsigned i = 0u; i < 192u; i++) aad[i] = (uint8_t)(i * 7u);
    for (unsigned i = 0u; i < 130u; i++) plain[i] = (uint8_t)(255u - i);
    memset(cipher, 0xA5, sizeof cipher);
    memset(tag, 0xB6, sizeof tag);
    memset(output, 0xC7, sizeof output);
    cint_value match[3] = {scalar(CINT_TAG_I64, (uint64_t)writer),
                          view(stream, 16, 2, CINT_VIEW_READ), scalar(CINT_TAG_I64, 1u)};
    assert(call("capture_match", match, 3u) == 1);
    match[1].as.view.shape[0] = 15;
    assert(call("capture_match", match, 3u) == 0);
    cint_value seal[6] = {scalar(CINT_TAG_I64, (uint64_t)writer), scalar(CINT_TAG_U64, 0u),
                         view(aad, 96, 2, CINT_VIEW_READ), view(plain, 65, 2, CINT_VIEW_READ),
                         view(cipher, 65, 2, CINT_VIEW_WRITE), view(tag, 16, 2, CINT_VIEW_WRITE)};
    seal[4].as.view.shape[0] = 64;
    assert(call("capture_seal", seal, 6u) == -1);
    for (unsigned i = 0u; i < 130u; i++) assert(cipher[i] == 0xA5);
    for (unsigned i = 0u; i < 32u; i++) assert(tag[i] == 0xB6);
    seal[4].as.view.shape[0] = 65;
    assert(call("capture_seal", seal, 6u) == 0);
    for (unsigned i = 1u; i < 130u; i += 2u) assert(cipher[i] == 0xA5);
    for (unsigned i = 1u; i < 32u; i += 2u) assert(tag[i] == 0xB6);
    cint_value open[6] = {scalar(CINT_TAG_I64, (uint64_t)reader), scalar(CINT_TAG_U64, 0u),
                         view(aad, 96, 2, CINT_VIEW_READ), view(cipher, 65, 2, CINT_VIEW_READ),
                         view(tag, 16, 2, CINT_VIEW_READ), view(output, 65, 2, CINT_VIEW_WRITE)};
    tag[0] ^= 1u;
    assert(call("capture_open", open, 6u) == -1);
    for (unsigned i = 0u; i < 130u; i++) assert(output[i] == 0xC7);
    tag[0] ^= 1u;
    assert(call("capture_open", open, 6u) == 0);
    for (unsigned i = 0u; i < 130u; i++) assert(output[i] == ((i & 1u) ? 0xC7 : plain[i]));
    memset(output, 0xC7, sizeof output);
    open[3] = view(cipher + 128, 65, -2, CINT_VIEW_READ);
    assert(call("capture_open", open, 6u) == -1);
    for (unsigned i = 0u; i < 130u; i++) assert(output[i] == 0xC7);
    assert(call("capture_seal", seal, 6u) == -1);
    assert(call("capture_seal", seal, 5u) == -1);
    seal[1].as.u64 = 1u;
    seal[2] = view(aad + 190, 96, -2, CINT_VIEW_READ);
    seal[3] = view(plain + 128, 65, -2, CINT_VIEW_READ);
    seal[4] = view(cipher + 128, 65, -2, CINT_VIEW_WRITE);
    seal[5] = view(tag + 30, 16, -2, CINT_VIEW_WRITE);
    assert(call("capture_seal", seal, 6u) == 0);
    open[1].as.u64 = 1u;
    open[2] = view(aad + 190, 96, -2, CINT_VIEW_READ);
    open[3] = view(cipher + 128, 65, -2, CINT_VIEW_READ);
    open[4] = view(tag + 30, 16, -2, CINT_VIEW_READ);
    open[5] = view(output + 128, 65, -2, CINT_VIEW_WRITE);
    assert(call("capture_open", open, 6u) == 0);
    for (unsigned i = 0u; i < 130u; i++) assert(output[i] == ((i & 1u) ? 0xC7 : plain[i]));
    open[5].as.view.shape[0] = -1;
    assert(call("capture_open", open, 6u) == -1);
    cint_value release[1] = {scalar(CINT_TAG_I64, (uint64_t)writer)};
    (void)call("capture_release", release, 1u);
    match[1].as.view.shape[0] = 16;
    assert(call("capture_match", match, 3u) == 0);
    release[0].as.i64 = reader;
    (void)call("capture_release", release, 1u);
    puts("pass: test host strided views, atomic rejection, slots");
    return 0;
}
'''


def run(command, cwd=None):
    result = subprocess.run([str(x) for x in command], cwd=cwd, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return result.stdout


def main():
    if not __debug__:
        raise RuntimeError('checks require assertions enabled')
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--toolchain', type=Path, required=True)
    parser.add_argument('--cint', type=Path)
    parser.add_argument('--host-only', action='store_true')
    args = parser.parse_args()
    root, out = args.root.resolve(), args.out.resolve()
    assert root != out and root not in out.parents, 'outputs must be outside checkout'
    out.mkdir(parents=True, exist_ok=True)
    assert (root / 'tests/capture/host.c').is_file(), 'test host adapter is missing'
    fields = {}
    for line in args.toolchain.read_text().splitlines():
        if ' ' in line:
            name, value = line.split(' ', 1)
            fields.setdefault(name, value)
    inc = Path(fields['include'])
    harness = out / 'host-test.c'
    harness.write_text(HOST_TEST)
    common = ['-std=c17', '-O2', '-Wall', '-Wextra', '-Werror',
              '-DCINT_RT_HELPERS_PORTABLE', '-DDAPH_CAPTURE_TESTHOST',
              '-I' + str(inc), '-I' + str(root / 'user/ci')]
    support = [root / 'tests/capture/host.c', root / 'rt/capture_crypto.c',
               root / 'vendor/monocypher/monocypher.c']
    for cc in ['gcc', 'clang']:
        binary = out / f'{cc}-host-test'
        run([cc, *common, harness, *support, '-o', binary])
        print(run([binary]), end='')
    if args.host_only:
        print('result: pass')
        return
    modules = ['src/capture_api.ci', 'src/capture_format.ci', 'src/capture.ci',
               'tests/capture/driver.ci']
    cint = args.cint or shutil.which('cint') or str(Path.home() / '.local/bin/cint')
    run([cint, 'emit-c', '--toolchain', args.toolchain.resolve(), '--root', root,
         '--out', out / 'emit', *modules], cwd=root)
    manifest = (out / 'emit/MANIFEST.ref').read_text().split()[0]
    emitted = (out / manifest).resolve()
    program = emitted / 'cint-program.c'
    entry = re.search(r'\bcg_[0-9A-Za-z_]+_run\b', program.read_text())
    assert entry, 'emitted entry is missing'
    receipts = {}
    for cc in ['gcc', 'clang']:
        obj, binary = out / f'{cc}-emitted.o', out / f'{cc}-codec'
        run([cc, *common, '-Dmain=cint_emitted_main', '-c', program, '-o', obj])
        run([cc, *common, '-DCI_RUN=' + entry.group(), obj,
             *sorted(p for p in emitted.rglob('*.c') if p != program),
             root / 'user/ci/main.c', *support, inc / 'cint_rt.c', '-o', binary])
        stdout = run([binary])
        assert stdout == EXPECTED, 'driver transcript does not include every expected check group'
        (out / f'{cc}-codec.stdout').write_text(stdout)
        receipts[cc] = {'stdout_sha256': hashlib.sha256(stdout.encode()).hexdigest(),
                        'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest()}
        print(stdout, end='')
    assert receipts['gcc']['stdout_sha256'] == receipts['clang']['stdout_sha256'], 'compiler transcript mismatch'
    receipt_sources = [root / name for name in modules] + support + [
        root / 'user/ci/main.c', root / 'user/ci/host.h', root / 'rt/capture_crypto.h',
        root / 'vendor/monocypher/monocypher.h']
    receipts['sources_sha256'] = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in receipt_sources}
    receipts['toolchain_sha256'] = hashlib.sha256(args.toolchain.read_bytes()).hexdigest()
    receipts['cint_sha256'] = hashlib.sha256(Path(cint).read_bytes()).hexdigest()
    (out / 'codec-receipt.json').write_text(json.dumps(receipts, indent=2) + '\n')
    print('result: pass')


if __name__ == '__main__':
    main()
