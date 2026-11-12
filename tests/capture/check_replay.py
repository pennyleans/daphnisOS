#!/usr/bin/env python3
"""Synthetic typed native replay qualification; fixtures contain no live keys."""
import argparse
import ctypes as c
import hashlib
import json
import re
import struct
from pathlib import Path

from check_crypto import buf, oracle
from check_sink import (ROOT, U8, P, KEY, STREAM, REVISION, HEADER,
                        Instance, reference_records, run, typed)

READ_AT = c.CFUNCTYPE(c.c_int, c.c_void_p, c.c_uint64, P, c.c_size_t)
MAX_BYTES = 16 * 1024 * 1024


def envelope(parts, final=True):
    out, previous = bytearray(HEADER), bytes(16)
    for seq, part in enumerate([*parts, *([b''] if final else [])]):
        prefix = struct.pack('<QIB3x', seq, len(part), int(not part)) + previous
        cipher, previous = oracle(KEY, STREAM, seq, HEADER + prefix, part)
        out += prefix + cipher + previous
    return bytes(out)


def offsets(data):
    at, result = 64, []
    while at < len(data):
        n = int.from_bytes(data[at + 8:at + 10], 'little')
        result.append(at)
        at += n + 48
    assert at == len(data)
    return result


class Reader:
    def __init__(self, shared):
        self.lib = lib = c.CDLL(str(shared))
        lib.daph_capture_replay_open.argtypes = [P, P, P, READ_AT, c.c_void_p, c.c_uint64]
        lib.daph_capture_replay_open.restype = c.c_int
        lib.daph_capture_replay_size.argtypes = [c.c_int]
        lib.daph_capture_replay_size.restype = c.c_int64
        lib.daph_capture_replay_read.argtypes = [c.c_int, c.c_uint64, P, c.c_size_t]
        lib.daph_capture_replay_read.restype = c.c_int64
        lib.daph_capture_replay_close.restype = None
        lib.daph_capture_replay_test_zeroed.restype = c.c_int
        lib.daph_capture_test_zeroed.argtypes = [c.c_uint]
        self.calls, self.errors = [], []
        self.hook = None

        def read_at(user, offset, dst, n):
            self.calls.append((offset, n))
            try:
                assert user == 0x4321
                assert n <= 4096 and offset <= len(self.data) and n <= len(self.data) - offset
                if self.hook:
                    result = self.hook(self, offset, dst, n)
                    if result is not None:
                        return result
                if n:
                    c.memmove(dst, bytes(self.data[offset:offset + n]), n)
                return 0
            except BaseException as error:
                self.errors.append(error)
                return -1
        self.callback = READ_AT(read_at)

    def open(self, data, key=KEY, stream=STREAM, revision=REVISION, size=None):
        self.data = bytearray(data)
        self.calls.clear()
        return self.lib.daph_capture_replay_open(buf(key), buf(stream), buf(revision),
                                                self.callback, c.c_void_p(0x4321),
                                                len(data) if size is None else size)

    def read(self, kind, offset, n):
        dst = (U8 * max(1, n))(*([0xa5] * max(1, n)))
        count = self.lib.daph_capture_replay_read(kind, offset, dst, n)
        if count < 0:
            assert bytes(dst) == b'\xa5' * max(1, n), 'failed read published bytes'
            return count, b''
        assert 0 <= count <= n
        assert bytes(dst[count:]) == b'\xa5' * (max(1, n) - count)
        return count, bytes(dst[:count])

    def wiped(self):
        assert self.lib.daph_capture_replay_test_zeroed() == 1
        assert all(self.lib.daph_capture_test_zeroed(i) for i in range(4))
        assert self.lib.daph_capture_replay_size(1) == -1
        assert self.lib.daph_capture_replay_size(2) == -1
        assert not self.errors, self.errors

    def close(self):
        self.lib.daph_capture_replay_close()
        self.wiped()

    def reject(self, data, **kwargs):
        assert self.open(data, **kwargs) == -1
        self.wiped()
        assert self.read(1, 0, 4096)[0] == -1
        self.close()


def checks(shared, build):
    reader = Reader(shared)
    reader.close()
    assert reader.read(1, 0, 10)[0] == -1
    # Console containing exact journal prefixes is not admitted as input.
    records = [typed(0, b'net:ffff:0000\nrng:0000:ffff\n'),
               typed(1, b'network-one\n'), typed(2, b'rng-one\n'),
               typed(0, bytes(range(256)) * 15), typed(1, b'network-two\n'),
               typed(2, b'rng-two\n'), typed(0, b'')]
    sealed = reference_records(records)
    expected = {1: b'network-one\nnetwork-two\n', 2: b'rng-one\nrng-two\n'}
    assert reader.open(sealed) == 0
    assert reader.lib.daph_capture_replay_size(0) == -1
    assert reader.read(0, 0, 10)[0] == -1
    assert reader.read(3, 0, 10)[0] == -1
    assert reader.read(1, 0, 4097)[0] == -1
    assert reader.lib.daph_capture_replay_read(1, 0, None, 1) == -1
    assert reader.lib.daph_capture_replay_read(1, 0, None, 0) == 0
    for kind, data in expected.items():
        assert reader.lib.daph_capture_replay_size(kind) == len(data)
        for offset in range(len(data) + 2):
            assert reader.read(kind, offset, 4096) == (len(data[offset:]), data[offset:])
        assert reader.read(kind, (1 << 64) - 1, 5) == (0, b'')
    # Two independent byte-at-a-time cursors cache their verified records.
    reader.close()
    assert reader.open(sealed) == 0
    for offset in range(max(map(len, expected.values()))):
        for kind, data in expected.items():
            if offset < len(data):
                assert reader.read(kind, offset, 1) == (1, data[offset:offset + 1])
    # Each channel loaded magic through its last data frame exactly once.
    assert len(reader.calls) <= 1 + 3 * (len(records) + 2) + 2 * 3 * (len(records) + 1)
    calls = len(reader.calls)
    assert reader.read(1, len(expected[1]) - 1, 1) == (1, b'\n')
    assert len(reader.calls) == calls
    assert reader.read(1, 0, 1) == (1, b'n')
    assert len(reader.calls) > calls  # Backward read resets only this cursor.
    reader.close()

    assert reader.open(reference_records([typed(0, b'only console')])) == 0
    assert reader.lib.daph_capture_replay_size(1) == 0
    assert reader.lib.daph_capture_replay_size(2) == 0
    assert reader.read(1, 0, 4096) == (0, b'')
    reader.close()
    assert reader.open(reference_records([])) == 0
    reader.close()

    # Every byte of a compact valid stream, including final tag, is bound.
    compact = reference_records([typed(1, b'n\n'), typed(2, b'r\n')])
    for at in range(len(compact)):
        changed = bytearray(compact)
        changed[at] ^= 1
        reader.reject(changed)
    for end in range(len(compact)):
        reader.reject(compact[:end])
    reader.reject(compact + b'x')
    reader.reject(compact + compact)
    reader.reject(compact, key=bytes(32))
    reader.reject(compact, stream=bytes(16))
    reader.reject(compact, revision=bytes(32))
    reader.reject(compact, size=MAX_BYTES + 1)
    assert reader.calls == []
    for missing in range(4):
        args = [buf(KEY), buf(STREAM), buf(REVISION), reader.callback,
                c.c_void_p(0x4321), len(compact)]
        args[missing] = READ_AT() if missing == 3 else None
        assert reader.lib.daph_capture_replay_open(*args) == -1
        reader.wiped()

    # Authenticated malformed schema is rejected before any input is visible.
    malformed = [b'old untyped net:0000\n', b'DAPHEVT2', b'DAPHEVT1x']
    for magic in malformed:
        reader.reject(envelope([magic, typed(1, b'n\n')]))
    bad = [b'x', b'xx', typed(3, b'x\n'), typed(255, b'x\n'),
           b'\x01\x01\x00x\n', typed(1, b''), typed(2, b''),
           typed(1, b'no newline'), typed(2, b'no newline'),
           typed(1, b'x' * 3101 + b'\n'), typed(2, b'x' * 521 + b'\n'),
           b'DAPHEVT1']
    for part in bad:
        reader.reject(envelope([b'DAPHEVT1', part]))
    reader.reject(envelope([b'DAPHEVT1'], final=False))
    reader.reject(envelope([]))
    frames = offsets(compact)
    reader.reject(compact[:frames[2]] + compact[frames[1]:frames[2]] + compact[frames[2]:])
    reader.reject(compact[:frames[1]] + compact[frames[2]:])
    reader.reject(compact[:frames[1]] + compact[frames[2]:frames[3]] +
                  compact[frames[1]:frames[2]] + compact[frames[3]:])

    # No input-record count ceiling; long channel reads cross frame boundaries.
    many = [typed(0, b'ignored\n')]
    net = []
    for i in range(3001):
        body = f'{i:04d}\n'.encode()
        many += [typed(1, body), typed(2, b'r\n')]
        net.append(body)
    large = reference_records(many)
    expected_net = b''.join(net)
    assert reader.open(large) == 0
    assert reader.lib.daph_capture_replay_size(1) == len(expected_net)
    for at in range(0, len(expected_net), 4096):
        part = expected_net[at:at + 4096]
        assert reader.read(1, at, 4096) == (len(part), part)
    reader.close()
    # Exact per-kind and CR-1 payload bounds, plus binary input body bytes.
    large_records = [typed(0, b'z' * 4093), typed(1, bytes(range(256)) * 12 + b'x' * 28 + b'\n'),
                     typed(2, b'r' * 520 + b'\n'), typed(1, b'n' * 3100 + b'\n')]
    large = reference_records(large_records)
    assert reader.open(large) == 0
    net = large_records[1][3:] + large_records[3][3:]
    rng = large_records[2][3:]
    for kind, data in [(1, net), (2, rng)]:
        for at, n in [(0, 4096), (2000, 4096), (10, 1), (3000, 4096), (0, 4096)]:
            part = data[at:at + n]
            assert reader.read(kind, at, n) == (len(part), part)
    reader.close()

    # The sealed-byte ceiling is inclusive and independent of record count.
    frame_size = 4096 + 48
    count, remaining = divmod(MAX_BYTES - 168, frame_size)
    full = typed(0, b'z' * 4093)
    maximum_parts = [full] * count
    assert remaining >= 51
    maximum_parts.append(typed(0, b'z' * (remaining - 51)))
    maximum = reference_records(maximum_parts)
    assert len(maximum) == MAX_BYTES
    assert reader.open(maximum) == 0
    assert reader.lib.daph_capture_replay_size(1) == 0
    reader.close()

    # Reentry at every source step closes the outer open, even if swallowed.
    assert reader.open(compact) == 0
    calls = len(reader.calls)
    reader.close()
    for target in range(1, calls + 1):
        for action in ['read', 'size', 'close', 'open']:
            def reenter(r, offset, dst, n):
                if len(r.calls) != target:
                    return None
                if action == 'read':
                    assert r.read(1, 0, 1)[0] == -1
                elif action == 'size':
                    assert r.lib.daph_capture_replay_size(1) == -1
                elif action == 'close':
                    r.lib.daph_capture_replay_close()
                else:
                    assert r.lib.daph_capture_replay_open(buf(KEY), buf(STREAM), buf(REVISION),
                                                         r.callback, None, len(compact)) == -1
                return 0
            reader.hook = reenter
            reader.reject(compact)
    reader.hook = None
    for target in range(1, calls + 1):
        reader.hook = lambda r, offset, dst, n: -1 if len(r.calls) == target else None
        reader.reject(compact)
    reader.hook = None

    # Mutation of an uncached later frame cannot publish an earlier staged byte.
    two = reference_records([typed(1, b'first\n'), typed(1, b'second\n')])
    second_offset = offsets(two)[2]
    assert reader.open(two) == 0
    reader.data[second_offset + 32] ^= 1
    assert reader.read(1, 0, 4096)[0] == -1
    reader.wiped()
    # Previously authenticated cached bytes remain stable under the explicit
    # immutable-provider contract. A rewind reload catches changed source.
    assert reader.open(two) == 0
    assert reader.read(1, 0, 1) == (1, b'f')
    reader.data[offsets(two)[1] + 32] ^= 1
    calls = len(reader.calls)
    assert reader.read(1, 1, 1) == (1, b'i')
    assert len(reader.calls) == calls
    assert reader.read(1, 6, 1) == (1, b's')
    assert reader.read(1, 0, 1)[0] == -1
    reader.wiped()
    # A callback failure after staging one whole record is also atomic.
    assert reader.open(two) == 0
    reader.hook = lambda r, offset, dst, n: -1 if offset == second_offset else None
    assert reader.read(1, 0, 4096)[0] == -1
    reader.wiped()
    reader.hook = None
    for action in ['read', 'size', 'close', 'open']:
        assert reader.open(two) == 0
        def reenter_read(r, offset, dst, n):
            if offset != second_offset:
                return None
            if action == 'read':
                assert r.read(1, 0, 1)[0] == -1
            elif action == 'size':
                assert r.lib.daph_capture_replay_size(1) == -1
            elif action == 'close':
                r.lib.daph_capture_replay_close()
            else:
                assert r.lib.daph_capture_replay_open(buf(KEY), buf(STREAM), buf(REVISION),
                                                     r.callback, None, len(two)) == -1
            return 0
        reader.hook = reenter_read
        assert reader.read(1, 0, 4096)[0] == -1
        reader.wiped()
        reader.hook = None

    # Writer and reader coexist in independent private native key slots.
    sink = Instance(shared, build)
    assert sink.begin() == 0
    lib = sink.lib
    lib.daph_capture_replay_open.argtypes = [P, P, P, READ_AT, c.c_void_p, c.c_uint64]
    lib.daph_capture_replay_size.argtypes = [c.c_int]
    lib.daph_capture_replay_size.restype = c.c_int64
    lib.daph_capture_replay_read.argtypes = [c.c_int, c.c_uint64, P, c.c_size_t]
    # The callback fixture remains on the original image but its data is immutable.
    reader.data = bytearray(two)
    assert lib.daph_capture_replay_open(buf(KEY), buf(STREAM), buf(REVISION),
                                        reader.callback, c.c_void_p(0x4321), len(two)) == 0
    assert lib.daph_capture_replay_size(1) == 13
    sink.put(b'simultaneous console\n')
    assert sink.lib.daph_capture_sink_record(1, buf(b'input\n'), 6) == 0
    assert sink.lib.daph_capture_sink_finish() == 0
    assert lib.daph_capture_replay_size(1) == 13
    lib.daph_capture_replay_close()
    reader.data = bytearray(b''.join(sink.parts))
    assert lib.daph_capture_replay_open(buf(KEY), buf(STREAM), buf(REVISION),
                                        reader.callback, c.c_void_p(0x4321), len(reader.data)) == 0
    assert lib.daph_capture_replay_size(1) == 6
    dst = (U8 * 6)()
    assert lib.daph_capture_replay_read(1, 0, dst, 6) == 6
    assert bytes(dst) == b'input\n'
    assert lib.daph_capture_replay_size(2) == 0
    lib.daph_capture_replay_close()
    sink.wiped()
    reader.close()
    return {'compact_sha256': hashlib.sha256(compact).hexdigest(),
            'large_sha256': hashlib.sha256(large).hexdigest(),
            'many_records': len(many)}


def audit(compiler, build):
    for high in [False, True]:
        obj = build / f'{compiler}-replay-{int(high)}.o'
        flags = ['-DDAPH_CAPTURE_PRIVATE_HIGH'] if high else []
        run([compiler, '-std=c99', '-O2', '-Wall', '-Wextra', '-Werror',
             '-ffreestanding', '-fno-builtin', '-fno-stack-protector',
             '-fno-pic', '-fno-pie', '-m64', '-mno-red-zone', '-mcmodel=kernel',
             '-mno-sse', '-mno-sse2', '-mno-mmx', '-mno-80387', *flags,
             '-c', ROOT / 'rt/capture_replay.c', '-o', obj])
        symbols = run(['nm', '-u', obj]).decode()
        assert {line.split()[-1] for line in symbols.splitlines()} <= {
            'crypto_wipe', 'daph_capture_key_open', 'daph_capture_key_close',
            'daph_capture_open'}, symbols
        assert 'daph_capture_replay_test_' not in run(['nm', '-g', obj]).decode()
        assembly = run(['objdump', '-d', '--no-show-raw-insn', obj]).decode()
        assert not re.search(r'%(?:[xyz]mm\d+|mm\d+|st(?:\(\d+\))?)\b', assembly)
        assert not re.search(r'\t(?:f[a-z0-9]+|emms|vzero[a-z]+)\b', assembly)
        table = run(['objdump', '-t', obj]).decode()
        storage = [line for line in table.splitlines()
                   if line.split() and line.split()[-1] in {'replay', 'active', 'busy', 'poisoned'}]
        assert len(storage) == 4
        assert all(('.high.data' in line) == high for line in storage)
        size = sum(int(line.split()[-2], 16) for line in storage)
        assert 12288 <= size <= 14000, size
    return size


def main():
    if not __debug__:
        raise RuntimeError('checks require assertions enabled')
    parser = argparse.ArgumentParser()
    parser.add_argument('--build', type=Path, required=True)
    args = parser.parse_args()
    build = args.build.resolve()
    assert build != ROOT and ROOT not in build.parents
    build.mkdir(parents=True, exist_ok=True)
    sources = [ROOT / 'rt/capture_replay.c', ROOT / 'rt/capture_sink.c',
               ROOT / 'rt/capture_crypto.c', ROOT / 'vendor/monocypher/monocypher.c']
    receipts = {}
    for compiler in ['gcc', 'clang']:
        shared = build / f'{compiler}-replay.so'
        run([compiler, '-std=c99', '-O2', '-Wall', '-Wextra', '-Werror',
             '-DDAPH_CAPTURE_TEST', '-fPIC', '-shared', *sources, '-o', shared])
        receipts[compiler] = checks(shared, build)
        receipts[compiler]['private_bytes'] = audit(compiler, build)
        receipts[compiler]['shared_sha256'] = hashlib.sha256(shared.read_bytes()).hexdigest()
        print(f'pass: {compiler} full authentication, typed input isolation, mutation/truncation/schema, atomic reads, cursor caching, erasure, freestanding/high-private')
    tracked = sources + [ROOT / 'rt/capture_replay.h', ROOT / 'rt/capture_sink.h',
                         ROOT / 'rt/capture_crypto.h', Path(__file__),
                         ROOT / 'tests/capture/check_sink.py', ROOT / 'tests/capture/check_crypto.py']
    receipts['sources_sha256'] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in tracked}
    (build / 'replay-receipt.json').write_text(json.dumps(receipts, indent=2) + '\n')
    print('result: pass')


if __name__ == '__main__':
    main()
