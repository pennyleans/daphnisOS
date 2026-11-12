#!/usr/bin/env python3
"""Synthetic capture-leaf checks; build products stay outside the checkout."""
import argparse
import ctypes as c
import hashlib
import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
U8 = c.c_uint8
P = c.POINTER(U8)
KEY = bytes(range(32))  # Synthetic test key, never provisioned.
STREAM = bytes(range(128, 144))
AAD = bytes((i * 29 + 197) % 256 for i in range(96))


def buf(data):
    return (U8 * len(data)).from_buffer_copy(data)


def run(args):
    return subprocess.check_output([str(x) for x in args], text=True)


def load(path):
    lib = c.CDLL(str(path))
    lib.daph_capture_key_open.argtypes = [P, P, c.c_int]
    lib.daph_capture_key_open.restype = c.c_int64
    lib.daph_capture_key_close.argtypes = [c.c_int64]
    lib.daph_capture_key_matches.argtypes = [c.c_int64, P, c.c_int]
    lib.daph_capture_key_matches.restype = c.c_int
    common = [c.c_int64, c.c_uint64, P, c.c_size_t, P, c.c_size_t, P, P]
    lib.daph_capture_seal.argtypes = common
    lib.daph_capture_open.argtypes = common
    lib.daph_capture_test_zeroed.argtypes = [c.c_uint]
    lib.daph_capture_test_zeroed.restype = c.c_int
    lib.daph_capture_test_counter.argtypes = [c.c_int64, c.c_uint64]
    return lib


def oracle(key, stream, seq, aad, plain):
    # libsodium.so.23 (Ubuntu 24.04), else the host's soname (Arch: .so.26); the API used is the same
    try:
        sodium = c.CDLL('libsodium.so.23')
    except OSError:
        sodium = c.CDLL('libsodium.so.26')
    fn = sodium.crypto_aead_xchacha20poly1305_ietf_encrypt
    fn.argtypes = [P, c.POINTER(c.c_ulonglong), P, c.c_ulonglong, P,
                   c.c_ulonglong, P, P, P]
    out = (U8 * (len(plain) + 16))()
    size = c.c_ulonglong()
    assert fn(out, c.byref(size), buf(plain), len(plain), buf(aad), len(aad),
              None, buf(stream + seq.to_bytes(8, 'little')), buf(key)) == 0
    assert size.value == len(out)
    return bytes(out[:-16]), bytes(out[-16:])


def checks(lib):
    key_open, close = lib.daph_capture_key_open, lib.daph_capture_key_close
    matches = lib.daph_capture_key_matches
    assert all(lib.daph_capture_test_zeroed(i) for i in range(4))
    assert key_open(None, buf(STREAM), 1) == -1
    assert key_open(buf(KEY), None, 1) == -1
    assert key_open(buf(KEY), buf(STREAM), 2) == -1
    writer = key_open(buf(KEY), buf(STREAM), 1)
    reader = key_open(buf(KEY), buf(STREAM), 0)
    assert 0 < writer < reader
    assert matches(writer, buf(STREAM), 1) == 1
    assert matches(writer, buf(STREAM), 0) == 0
    assert matches(writer, buf(bytes(16)), 1) == 0
    assert matches(writer, None, 1) == 0
    assert matches(writer, buf(STREAM), 2) == 0
    assert matches(-1, buf(STREAM), 1) == 0

    def seal(slot, seq, plain, aad=AAD, expected=0, n=None, an=None):
        out = buf(bytes([0xA5]) * (max(len(plain), 4097) + 16))
        tag = buf(bytes([0x5A]) * 16)
        before = bytes(out), bytes(tag)
        result = lib.daph_capture_seal(slot, seq, buf(aad), len(aad) if an is None else an,
                                       buf(plain), len(plain) if n is None else n, out, tag)
        assert result == expected, ('seal', slot, seq, len(plain), result)
        if result:
            assert (bytes(out), bytes(tag)) == before, 'seal changed failed output'
        else:
            assert bytes(out[len(plain):]) == before[0][len(plain):]
        return bytes(out[:len(plain)]), bytes(tag)

    def decrypt(slot, seq, cipher, tag, aad=AAD, expected=0, n=None, an=None):
        out = buf(bytes([0xC3]) * (max(len(cipher), 4097) + 16))
        before = bytes(out)
        result = lib.daph_capture_open(slot, seq, buf(aad), len(aad) if an is None else an,
                                       buf(cipher), len(cipher) if n is None else n, buf(tag), out)
        assert result == expected, ('open', slot, seq, len(cipher), result)
        if result:
            assert bytes(out) == before, 'open exposed unauthenticated plaintext'
        else:
            assert bytes(out[len(cipher):]) == before[len(cipher):]
        return bytes(out[:len(cipher)])

    seal(reader, 0, b'x', expected=-1)
    seal(writer, 1, b'x', expected=-1)
    seal(writer, 0, b'x', expected=-1, n=4097)
    seal(writer, 0, b'x', expected=-1, an=97)
    # Invalid pointers and overlapping outputs must preserve data and nonce order.
    sample, sample_tag = buf(b'x'), buf(bytes([0xA7]) * 16)
    for args in [
        [writer, 0, None, 1, sample, 1, sample, sample_tag],
        [writer, 0, None, 0, None, 1, sample, sample_tag],
        [writer, 0, None, 0, sample, 1, None, sample_tag],
        [writer, 0, None, 0, sample, 1, sample, None],
        [writer, 0, None, 0, sample, 1, sample_tag, sample_tag],
        [0, 0, None, 0, sample, 1, sample, sample_tag],
        [-1, 0, None, 0, sample, 1, sample, sample_tag],
    ]:
        assert lib.daph_capture_seal(*args) == -1
        assert bytes(sample) == b'x' and bytes(sample_tag) == bytes([0xA7]) * 16
    for args in [
        [reader, 0, None, 1, sample, 1, sample_tag, sample],
        [reader, 0, None, 0, None, 1, sample_tag, sample],
        [reader, 0, None, 0, sample, 1, None, sample],
        [reader, 0, None, 0, sample, 1, sample_tag, None],
        [0, 0, None, 0, sample, 1, sample_tag, sample],
        [-1, 0, None, 0, sample, 1, sample_tag, sample],
    ]:
        assert lib.daph_capture_open(*args) == -1
        assert bytes(sample) == b'x' and bytes(sample_tag) == bytes([0xA7]) * 16
    for seq, size in enumerate([0, 1, 63, 64, 65, 4095, 4096]):
        plain = bytes((i * 173 + 255) % 256 for i in range(size))
        cipher, tag = seal(writer, seq, plain)
        assert (cipher, tag) == oracle(KEY, STREAM, seq, AAD, plain)
        assert decrypt(reader, seq, cipher, tag) == plain
        seal(writer, seq, plain, expected=-1)
        decrypt(writer, seq, cipher, tag, expected=-1)
        decrypt(reader, seq ^ (1 << 63), cipher, tag, expected=-1)
        decrypt(reader, seq, cipher, bytes([tag[0] ^ 1]) + tag[1:], expected=-1)
        decrypt(reader, seq, cipher, tag, bytes([AAD[0] ^ 1]) + AAD[1:], expected=-1)
        if cipher:
            decrypt(reader, seq, bytes([cipher[0] ^ 1]) + cipher[1:], tag, expected=-1)
    decrypt(reader, 6, cipher, tag, expected=-1, n=4097)
    decrypt(reader, 6, cipher, tag, expected=-1, an=97)
    wrong = key_open(buf(bytes([KEY[0] ^ 1]) + KEY[1:]), buf(STREAM), 0)
    nonce = key_open(buf(KEY), buf(bytes([STREAM[0] ^ 1]) + STREAM[1:]), 0)
    decrypt(wrong, 6, cipher, tag, expected=-1)
    decrypt(nonce, 6, cipher, tag, expected=-1)
    assert key_open(buf(KEY), buf(STREAM), 0) == -1
    close(wrong)
    assert lib.daph_capture_test_zeroed(2)
    fresh = key_open(buf(KEY), buf(STREAM), 0)
    assert fresh > nonce
    assert matches(wrong, buf(STREAM), 0) == 0
    decrypt(wrong, 6, cipher, tag, expected=-1)
    close(wrong)  # A stale close cannot close a newer slot.
    assert decrypt(fresh, 6, cipher, tag) == plain

    # In-place and partially overlapping input/output use private staging.
    alias = buf(b'abcdefg' + bytes([0xCC]) * 16)
    alias_tag = buf(bytes(16))
    expected_cipher, expected_tag = oracle(KEY, STREAM, 7, b'', b'abcdefg')
    assert lib.daph_capture_seal(writer, 7, None, 0, alias, 7,
                                 c.cast(c.byref(alias, 1), P), alias_tag) == 0
    assert bytes(alias[1:8]) == expected_cipher and bytes(alias_tag) == expected_tag
    assert lib.daph_capture_open(reader, 7, None, 0, c.cast(c.byref(alias, 1), P), 7,
                                 alias_tag, alias) == 0
    assert bytes(alias[:7]) == b'abcdefg'
    empty_tag = buf(bytes(16))
    assert lib.daph_capture_seal(writer, 8, None, 0, None, 0, None, empty_tag) == 0
    assert (b'', bytes(empty_tag)) == oracle(KEY, STREAM, 8, b'', b'')
    assert lib.daph_capture_open(reader, 8, None, 0, None, 0, empty_tag, None) == 0

    # A synthetic counter hook reaches the wrap edge without 2**64 writes.
    assert lib.daph_capture_test_counter(writer, (1 << 64) - 2) == 0
    high, high_tag = seal(writer, (1 << 64) - 2, b'edge')
    assert (high, high_tag) == oracle(KEY, STREAM, (1 << 64) - 2, AAD, b'edge')
    seal(writer, (1 << 64) - 1, b'edge', expected=-1)
    seal(writer, 0, b'edge', expected=-1)
    assert decrypt(reader, (1 << 64) - 2, high, high_tag) == b'edge'
    for slot in [writer, reader, nonce, fresh]:
        close(slot)
    close(-1)
    close(0)
    assert all(lib.daph_capture_test_zeroed(i) for i in range(4))


def published_vector(lib):
    # draft-irtf-cfrg-xchacha-03, A.3.1, a published synthetic vector:
    # https://www.ietf.org/archive/id/draft-irtf-cfrg-xchacha-03.txt
    key = bytes(range(0x80, 0xA0))
    stream = bytes(range(0x40, 0x50))
    seq = int.from_bytes(bytes(range(0x50, 0x58)), 'little')
    aad = bytes.fromhex('50515253c0c1c2c3c4c5c6c7')
    plain = bytes.fromhex(
        '4c616469657320616e642047656e746c656d656e206f662074686520636c6173'
        '73206f66202739393a204966204920636f756c64206f6666657220796f75206f'
        '6e6c79206f6e652074697020666f7220746865206675747572652c2073756e73'
        '637265656e20776f756c642062652069742e')
    cipher = bytes.fromhex(
        'bd6d179d3e83d43b9576579493c0e939572a1700252bfaccbed2902c21396cbb'
        '731c7f1b0b4aa6440bf3a82f4eda7e39ae64c6708c54c216cb96b72e1213b452'
        '2f8c9ba40db5d945b11b69b982c1bb9e3f3fac2bc369488f76b2383565d3fff9'
        '21f9664c97637da9768812f615c68b13b52e')
    tag = bytes.fromhex('c0875924c1c7987947deafd8780acf49')
    assert oracle(key, stream, seq, aad, plain) == (cipher, tag)
    reader = lib.daph_capture_key_open(buf(key), buf(stream), 0)
    out = (U8 * len(plain))()
    assert lib.daph_capture_open(reader, seq, buf(aad), len(aad), buf(cipher),
                                 len(cipher), buf(tag), out) == 0
    assert bytes(out) == plain
    lib.daph_capture_key_close(reader)
    writer = lib.daph_capture_key_open(buf(key), buf(stream), 1)
    assert lib.daph_capture_test_counter(writer, seq) == 0
    mac = (U8 * 16)()
    assert lib.daph_capture_seal(writer, seq, buf(aad), len(aad), buf(plain),
                                 len(plain), out, mac) == 0
    assert (bytes(out), bytes(mac)) == (cipher, tag)
    lib.daph_capture_key_close(writer)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--build', type=Path, required=True)
    args = parser.parse_args()
    assert (ROOT / 'rt/capture_crypto.c').is_file(), 'capture crypto leaf is missing'
    build = args.build.resolve()
    assert build != ROOT and ROOT not in build.parents, 'build must be outside checkout'
    build.mkdir(parents=True, exist_ok=True)
    pins = json.loads((ROOT / 'capture.pin').read_text())
    for name, digest in pins['files_sha256'].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
    sources = [ROOT / 'rt/capture_crypto.c', ROOT / 'vendor/monocypher/monocypher.c']
    for compiler in ['gcc', 'clang']:
        shared = build / f'{compiler}-capture.so'
        run([compiler, '-std=c99', '-O2', '-Wall', '-Wextra', '-Werror', '-fPIC',
             '-shared', '-DDAPH_CAPTURE_TEST', *sources, '-o', shared])
        checks(load(shared))
        published_vector(load(shared))
        for src in sources:
            obj = build / f'{compiler}-{src.stem}.o'
            run([compiler, '-std=c99', '-O2', '-Wall', '-Wextra', '-Werror',
                 '-ffreestanding', '-fno-builtin', '-fno-stack-protector',
                 '-fno-pic', '-fno-pie', '-m64', '-mno-red-zone', '-mcmodel=kernel',
                 '-mno-sse', '-mno-sse2', '-mno-mmx', '-mno-80387',
                 '-c', src, '-o', obj])
            symbols = run(['nm', '-u', obj])
            allowed = {'crypto_wipe', 'crypto_aead_lock', 'crypto_aead_unlock'} if src == sources[0] else set()
            assert {line.split()[-1] for line in symbols.splitlines()} <= allowed, symbols
            assert 'daph_capture_test_' not in run(['nm', '-g', obj]), 'production test hook'
            assembly = run(['objdump', '-d', '--no-show-raw-insn', obj])
            assert not re.search(r'%(?:[xyz]mm\d+|mm\d+|st(?:\(\d+\))?)\b', assembly), 'vector/x87 register'
            assert not re.search(r'\t(?:f[a-z0-9]+|emms|vzero[a-z]+)\b', assembly), 'x87/vector instruction'
        print(f'pass: {compiler} synthetic oracle, published vector, slots, atomicity, counter, freestanding audit')
    print('result: pass')


if __name__ == "__main__":
    main()
