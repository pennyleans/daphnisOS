#!/usr/bin/env python3
"""Synthetic native sink qualification; no live keys or in-tree build products."""
import argparse
import ctypes as c
import hashlib
import json
import re
import shutil
import struct
import subprocess
from pathlib import Path

from check_crypto import buf, oracle


ROOT = Path(__file__).resolve().parents[2]
U8 = c.c_uint8
P = c.POINTER(U8)
EMIT = c.CFUNCTYPE(c.c_int, c.c_void_p, P, c.c_size_t)
KEY = bytes(range(80, 112))  # Synthetic fixtures only, never provisioned.
STREAM = bytes(range(16))
REVISION = bytes(range(32, 64))
HEADER = b'DAPHREC1' + struct.pack('<HHI', 1, 1, 4096) + STREAM + REVISION
CASES = [(0, False), (1, False), (4092, False), (4093, False),
         (4094, False), (4096, False),
         (9000, False), (9000, True)]


def run(command, cwd=None):
    result = subprocess.run([str(x) for x in command], cwd=cwd,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        raise RuntimeError(result.stdout.decode(errors='replace') +
                           result.stderr.decode(errors='replace'))
    return result.stdout


def payload(count, lines=False):
    data = bytearray((i % 251) + 1 for i in range(count))
    data = data.replace(b'\n', b'\xfe')
    if lines:
        for at in [0, 1, 4095, count - 1]:
            data[at] = 10
    return bytes(data)


def chunks(data):
    pending = bytearray()
    for byte in data:
        pending.append(byte)
        if byte == 10 or len(pending) == 4093:
            yield bytes(pending)
            pending.clear()
    if pending:
        yield bytes(pending)


def typed(kind, body):
    return bytes([kind]) + struct.pack('<H', len(body)) + body


def reference_records(records):
    output = bytearray(HEADER)
    previous = bytes(16)
    for sequence, part in enumerate([b'DAPHEVT1', *records, b'']):
        prefix = struct.pack('<QIB3x', sequence, len(part), int(not part)) + previous
        cipher, previous = oracle(KEY, STREAM, sequence, HEADER + prefix, part)
        output += prefix + cipher + previous
    return bytes(output)


def reference(data):
    return reference_records([typed(0, part) for part in chunks(data)])


def mixed_records():
    return [typed(0, b'net:fake\n'), typed(0, b'rng:fake\n'),
            typed(0, b'pending'), typed(1, b'net:real\n'),
            typed(0, b'console'), typed(2, b'rng:real\n')]


def decrypt(envelope):
    assert envelope[:64] == HEADER
    # libsodium.so.23 (Ubuntu 24.04), else the host's soname (Arch: .so.26); the API used is the same
    try:
        sodium = c.CDLL('libsodium.so.23')
    except OSError:
        sodium = c.CDLL('libsodium.so.26')
    fn = sodium.crypto_aead_xchacha20poly1305_ietf_decrypt
    fn.argtypes = [P, c.POINTER(c.c_ulonglong), P, P, c.c_ulonglong,
                   P, c.c_ulonglong, P, P]
    position, sequence, previous, plain, final = 64, 0, bytes(16), [], False
    while position < len(envelope):
        assert not final, 'trailing bytes after final'
        prefix = envelope[position:position + 32]
        assert len(prefix) == 32
        seq, size, flag = struct.unpack('<QIB3x', prefix[:16])
        assert seq == sequence and prefix[13:16] == bytes(3)
        assert prefix[16:] == previous and flag in [0, 1]
        assert (flag == 1 and size == 0) or (flag == 0 and 1 <= size <= 4096)
        sealed = envelope[position + 32:position + 48 + size]
        assert len(sealed) == size + 16
        decoded, count = (U8 * max(size, 1))(), c.c_ulonglong()
        assert fn(decoded, c.byref(count), None, buf(sealed), len(sealed),
                  buf(HEADER + prefix), 96,
                  buf(STREAM + seq.to_bytes(8, 'little')), buf(KEY)) == 0
        assert count.value == size
        if not flag:
            plain.append(bytes(decoded[:size]))
        previous = sealed[-16:]
        position += size + 48
        sequence += 1
        final = bool(flag)
    assert final and position == len(envelope), 'incomplete recording'
    assert plain[0] == b'DAPHEVT1'
    console = bytearray()
    for part in plain[1:]:
        assert len(part) >= 3 and part[0] <= 2
        assert int.from_bytes(part[1:3], 'little') == len(part) - 3
        if part[0] == 0:
            console += part[3:]
        else:
            assert part.endswith(b'\n')
    return bytes(console)


class Instance:
    number = 0

    def __init__(self, shared, build, callback=None):
        # Each independently loaded image models a fresh boot's terminal sink.
        Instance.number += 1
        path = build / f'instance-{Instance.number}.so'
        shutil.copyfile(shared, path)
        self.lib = lib = c.CDLL(str(path))
        path.unlink()
        lib.daph_capture_sink_begin.argtypes = [P, P, P, EMIT, c.c_void_p]
        lib.daph_capture_sink_begin.restype = c.c_int
        lib.daph_capture_sink_put.argtypes = [U8]
        lib.daph_capture_sink_put.restype = c.c_int
        lib.daph_capture_sink_record.argtypes = [c.c_int, P, c.c_size_t]
        lib.daph_capture_sink_record.restype = c.c_int
        lib.daph_capture_sink_finish.restype = c.c_int
        lib.daph_capture_sink_abort.restype = None
        lib.daph_capture_sink_test_zeroed.restype = c.c_int
        lib.daph_capture_sink_test_counter.argtypes = [c.c_uint64]
        lib.daph_capture_key_open.argtypes = [P, P, c.c_int]
        lib.daph_capture_key_open.restype = c.c_int64
        lib.daph_capture_key_matches.argtypes = [c.c_int64, P, c.c_int]
        lib.daph_capture_key_close.argtypes = [c.c_int64]
        lib.daph_capture_test_zeroed.argtypes = [c.c_uint]
        self.parts = []
        self.calls = 0
        self.errors = []

        def emit(user, data, size):
            self.calls += 1
            try:
                assert user == 0x1234
                assert 0 < size <= 4144
                if callback:
                    return callback(self, bytes(data[:size]))
                self.parts.append(bytes(data[:size]))
                return 0
            except BaseException as error:
                self.errors.append(error)
                return -1

        self.emit = EMIT(emit)

    def begin(self):
        return self.lib.daph_capture_sink_begin(buf(KEY), buf(STREAM), buf(REVISION),
                                               self.emit, c.c_void_p(0x1234))

    def put(self, data):
        for byte in data:
            assert self.lib.daph_capture_sink_put(byte) == 0

    def wiped(self):
        assert self.lib.daph_capture_sink_test_zeroed() == 1
        assert all(self.lib.daph_capture_test_zeroed(i) for i in range(4))
        assert not self.errors, self.errors

    def terminal(self):
        before = self.calls, b''.join(self.parts)
        assert self.lib.daph_capture_sink_put(65) == -1
        assert self.lib.daph_capture_sink_finish() == -1
        assert self.begin() == -1
        self.lib.daph_capture_sink_abort()
        assert (self.calls, b''.join(self.parts)) == before
        self.wiped()


def checks(shared, build):
    envelopes = []
    for count, lines in CASES:
        sink = Instance(shared, build)
        assert sink.begin() == 0 and b"".join(sink.parts) == reference(b"")[:-48]
        data = payload(count, lines)
        sink.put(data)
        # Every complete chunk, including newline, is already emitted.
        committed = list(chunks(data))
        if data and data[-1] != 10 and len(committed[-1]) < 4093:
            committed.pop()
        assert len(sink.parts) == 2 + len(committed)
        assert sink.lib.daph_capture_sink_finish() == 0
        envelope = b''.join(sink.parts)
        assert envelope == reference(data), (count, lines)
        assert decrypt(envelope) == data
        assert len(envelope) == 64 + 56 + len(data) + 51 * len(list(chunks(data))) + 48
        sink.wiped()
        sink.terminal()
        envelopes.append(envelope)

    # All input bytes, including binary zero and 255, remain exact.
    sink = Instance(shared, build)
    assert sink.begin() == 0
    binary = bytes(range(256)) * 35
    sink.put(binary)
    assert sink.lib.daph_capture_sink_finish() == 0
    assert b''.join(sink.parts) == reference(binary)
    assert decrypt(b''.join(sink.parts)) == binary
    sink.terminal()

    # A partial output acceptance cannot be undone; nothing is emitted later.
    for target in [1, 2, 3, 4]:
        for accepted in [0, 1, 17, 47, 9999]:
            def reject(sink, data):
                sink.parts.append(data[:accepted] if sink.calls == target else data)
                return -7 if sink.calls == target else 0
            sink = Instance(shared, build, reject)
            result = sink.begin()
            if target > 2:
                assert result == 0
                sink.put(b'private pending bytes')
                assert sink.lib.daph_capture_sink_finish() == -1
            else:
                assert result == -1
            assert sink.calls == target
            sink.terminal()

    # Failures reached during put, including a full output buffer, are terminal.
    for data in [b'line\n', b'x' * 4093]:
        def reject_flush(sink, frame):
            sink.parts.append(frame)
            return 1 if sink.calls == 3 else 0
        sink = Instance(shared, build, reject_flush)
        assert sink.begin() == 0
        sink.put(data[:-1])
        assert sink.lib.daph_capture_sink_put(data[-1]) == -1
        assert sink.calls == 3
        sink.terminal()

    # Reentry poisons the outer call even if a callback swallows the error.
    for target in [1, 2, 3, 4]:
        for action in ['put', 'record', 'begin', 'finish', 'abort']:
            def reenter(sink, data):
                sink.parts.append(data)
                if sink.calls == target:
                    if action == 'put':
                        assert sink.lib.daph_capture_sink_put(10) == -1
                    elif action == 'record':
                        assert sink.lib.daph_capture_sink_record(1, buf(b'x\n'), 2) == -1
                    elif action == 'begin':
                        assert sink.begin() == -1
                    elif action == 'finish':
                        assert sink.lib.daph_capture_sink_finish() == -1
                    else:
                        sink.lib.daph_capture_sink_abort()
                return 0
            sink = Instance(shared, build, reenter)
            result = sink.begin()
            if target > 2:
                assert result == 0
                sink.put(b'secret')
                assert sink.lib.daph_capture_sink_finish() == -1
            else:
                assert result == -1
            assert sink.calls == target
            sink.terminal()

    for action in ['begin', 'abort']:
        sink = Instance(shared, build)
        assert sink.begin() == 0
        sink.put(b'never sealed')
        if action == 'begin':
            assert sink.begin() == -1
        else:
            sink.lib.daph_capture_sink_abort()
        assert b"".join(sink.parts) == reference(b"")[:-48]
        sink.terminal()

    for action in ['put', 'finish', 'abort']:
        sink = Instance(shared, build)
        if action == 'put':
            assert sink.lib.daph_capture_sink_put(0) == -1
        elif action == 'finish':
            assert sink.lib.daph_capture_sink_finish() == -1
        else:
            sink.lib.daph_capture_sink_abort()
        sink.terminal()
        assert sink.calls == 0

    for missing in range(4):
        sink = Instance(shared, build)
        args = [buf(KEY), buf(STREAM), buf(REVISION), sink.emit, c.c_void_p(0x1234)]
        args[missing] = EMIT() if missing == 3 else None
        assert sink.lib.daph_capture_sink_begin(*args) == -1
        sink.terminal()
        assert sink.calls == 0

    sink = Instance(shared, build)
    slots = [sink.lib.daph_capture_key_open(buf(KEY), buf(STREAM), 0) for _ in range(4)]
    assert all(slot > 0 for slot in slots)
    assert sink.begin() == -1 and sink.calls == 0
    for slot in slots:
        assert sink.lib.daph_capture_key_matches(slot, buf(STREAM), 0) == 1
        sink.lib.daph_capture_key_close(slot)
    sink.terminal()

    # A native crypto refusal discards pending plaintext without output.
    sink = Instance(shared, build)
    assert sink.begin() == 0
    sink.put(b'pending before native refusal')
    sink.lib.daph_capture_key_close(1)  # First synthetic slot in this fresh image.
    assert sink.lib.daph_capture_sink_finish() == -1
    assert b"".join(sink.parts) == reference(b"")[:-48]
    sink.terminal()

    # No sequence wrap or final marker after an exhausted native counter.
    sink = Instance(shared, build)
    assert sink.begin() == 0
    assert sink.lib.daph_capture_sink_test_counter((1 << 64) - 2) == 0
    sink.put(b'x\n')
    assert sink.lib.daph_capture_sink_finish() == -1
    assert len(sink.parts) == 3
    sink.terminal()
    # Typed inputs flush console first and remain distinct from spoofed lines.
    sink = Instance(shared, build)
    assert sink.begin() == 0
    sink.put(b'net:fake\nrng:fake\npending')
    net, rng = b'net:real\n', b'rng:real\n'
    assert sink.lib.daph_capture_sink_record(1, buf(net), len(net)) == 0
    sink.put(b'console')
    assert sink.lib.daph_capture_sink_record(2, buf(rng), len(rng)) == 0
    assert sink.lib.daph_capture_sink_finish() == 0
    records = [typed(0, part) for part in chunks(b'net:fake\nrng:fake\npending')]
    records += [typed(1, net), typed(0, b'console'), typed(2, rng)]
    assert records == mixed_records()
    assert b''.join(sink.parts) == reference_records(records)
    envelopes.append(b''.join(sink.parts))
    sink.terminal()

    for target in [3, 4]:
        def reject_record(sink, data):
            sink.parts.append(data)
            return -1 if sink.calls == target else 0
        sink = Instance(shared, build, reject_record)
        assert sink.begin() == 0
        sink.put(b'pending console')
        assert sink.lib.daph_capture_sink_record(1, buf(b'line\n'), 5) == -1
        assert sink.calls == target
        sink.terminal()

    for kind, n, body in [(0, 1, b'\n'), (3, 1, b'\n'), (1, 0, b''),
                          (2, 0, b''), (1, 3102, b'x' * 3101 + b'\n'),
                          (2, 522, b'x' * 521 + b'\n'), (1, 1, b'x'),
                          (2, 1, b'x'), (1, 1, None)]:
        sink = Instance(shared, build)
        assert sink.begin() == 0
        assert sink.lib.daph_capture_sink_record(kind, None if body is None else buf(body), n) == -1
        sink.terminal()
    for kind, n in [(1, 3101), (2, 521)]:
        sink = Instance(shared, build)
        assert sink.begin() == 0
        body = b'x' * (n - 1) + b'\n'
        assert sink.lib.daph_capture_sink_record(kind, buf(body), n) == 0
        assert sink.lib.daph_capture_sink_finish() == 0
        assert b''.join(sink.parts) == reference_records([typed(kind, body)])
        sink.terminal()
    return b''.join(envelopes)


def cint_oracle(args, build):
    fields = {}
    for line in args.toolchain.read_text().splitlines():
        if ' ' in line:
            key, value = line.split(' ', 1)
            fields.setdefault(key, value)
    include = Path(fields['include'])
    modules = ['src/capture_api.ci', 'src/capture_format.ci', 'src/capture.ci',
               'tests/capture/native_oracle.ci']
    run([args.cint, 'emit-c', '--toolchain', args.toolchain, '--root', ROOT,
         '--out', build / 'oracle-emit', *modules], cwd=ROOT)
    manifest = (build / 'oracle-emit/MANIFEST.ref').read_text().split()[0]
    emitted = (build / manifest).resolve()
    program = emitted / 'cint-program.c'
    entry = re.search(r'\bcg_[0-9A-Za-z_]+_run\b', program.read_text())
    assert entry
    common = ['-std=c17', '-O2', '-Wall', '-Wextra', '-Werror',
              '-DCINT_RT_HELPERS_PORTABLE', '-DDAPH_CAPTURE_TESTHOST',
              '-I' + str(include), '-I' + str(ROOT / 'user/ci')]
    expected = b''.join(reference(payload(count, lines)) for count, lines in CASES)
    expected += reference_records(mixed_records())
    for compiler in ['gcc', 'clang']:
        obj, binary = build / f'{compiler}-oracle.o', build / f'{compiler}-oracle'
        run([compiler, *common, '-Dmain=cint_emitted_main', '-c', program, '-o', obj])
        run([compiler, *common, '-DCI_RUN=' + entry.group(), obj,
             *sorted(p for p in emitted.rglob('*.c') if p != program),
             ROOT / 'user/ci/main.c', ROOT / 'tests/capture/host.c',
             ROOT / 'rt/capture_crypto.c', ROOT / 'vendor/monocypher/monocypher.c',
             include / 'cint_rt.c', '-o', binary])
        actual = run([binary])
        (build / f'{compiler}-cint.envelopes').write_bytes(actual)
        assert actual == expected, 'cint envelope mismatch'
    return expected


def audit(compiler, build):
    for high in [False, True]:
        obj = build / f'{compiler}-sink-{int(high)}.o'
        flags = ['-DDAPH_CAPTURE_PRIVATE_HIGH'] if high else []
        run([compiler, '-std=c99', '-O2', '-Wall', '-Wextra', '-Werror',
             '-ffreestanding', '-fno-builtin', '-fno-stack-protector',
             '-fno-pic', '-fno-pie', '-m64', '-mno-red-zone', '-mcmodel=kernel',
             '-mno-sse', '-mno-sse2', '-mno-mmx', '-mno-80387', *flags,
             '-c', ROOT / 'rt/capture_sink.c', '-o', obj])
        symbols = run(['nm', '-u', obj]).decode()
        assert {line.split()[-1] for line in symbols.splitlines()} <= {
            'crypto_wipe', 'daph_capture_key_open', 'daph_capture_key_close',
            'daph_capture_seal'}, symbols
        assert 'daph_capture_sink_test_' not in run(['nm', '-g', obj]).decode()
        assembly = run(['objdump', '-d', '--no-show-raw-insn', obj]).decode()
        assert not re.search(r'%(?:[xyz]mm\d+|mm\d+|st(?:\(\d+\))?)\b', assembly)
        assert not re.search(r'\t(?:f[a-z0-9]+|emms|vzero[a-z]+)\b', assembly)
        table = run(['objdump', '-t', obj]).decode()
        storage = [line for line in table.splitlines()
                   if line.split() and line.split()[-1] in {'sink', 'started', 'failed', 'busy', 'done'}]
        assert len(storage) == 5
        assert all(('.high.data' in line) == high for line in storage)
        assert 8400 <= sum(int(line.split()[-2], 16) for line in storage) <= 9000


def main():
    if not __debug__:
        raise RuntimeError('checks require assertions enabled')
    parser = argparse.ArgumentParser()
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--cint', type=Path, required=True)
    parser.add_argument('--toolchain', type=Path, required=True)
    args = parser.parse_args()
    build = args.build.resolve()
    assert build != ROOT and ROOT not in build.parents
    build.mkdir(parents=True, exist_ok=True)
    sources = [ROOT / 'rt/capture_sink.c', ROOT / 'rt/capture_crypto.c',
               ROOT / 'vendor/monocypher/monocypher.c']
    expected = cint_oracle(args, build)
    receipts = {}
    for compiler in ['gcc', 'clang']:
        shared = build / f'{compiler}-sink.so'
        run([compiler, '-std=c99', '-O2', '-Wall', '-Wextra', '-Werror',
             '-DDAPH_CAPTURE_TEST', '-fPIC', '-shared', *sources, '-o', shared])
        actual = checks(shared, build)
        assert actual == expected, 'native/cint envelope mismatch'
        (build / f'{compiler}-native.envelopes').write_bytes(actual)
        audit(compiler, build)
        receipts[compiler] = {'envelope_sha256': hashlib.sha256(actual).hexdigest(),
                             'shared_sha256': hashlib.sha256(shared.read_bytes()).hexdigest()}
        print(f'pass: {compiler} native/cint/sodium envelopes, bounds, erasure, reentry, failures, freestanding/high-private')
    tracked = sources + [ROOT / 'rt/capture_sink.h', ROOT / 'rt/capture_crypto.h',
                         Path(__file__), ROOT / 'tests/capture/native_oracle.ci',
                         ROOT / 'tests/capture/check_crypto.py',
                         ROOT / 'src/capture.ci', ROOT / 'src/capture_format.ci',
                         ROOT / 'src/capture_api.ci', ROOT / 'tests/capture/host.c',
                         ROOT / 'vendor/monocypher/monocypher.h',
                         ROOT / 'user/ci/main.c', ROOT / 'user/ci/host.h']
    receipts['sources_sha256'] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in tracked}
    receipts['cint_sha256'] = hashlib.sha256(args.cint.read_bytes()).hexdigest()
    receipts['toolchain_sha256'] = hashlib.sha256(args.toolchain.read_bytes()).hexdigest()
    (build / 'writer-receipt.json').write_text(json.dumps(receipts, indent=2) + '\n')
    print('result: pass')


if __name__ == '__main__':
    main()
