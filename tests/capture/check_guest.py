#!/usr/bin/env python3
"""Compare decrypted guest output with normal output using synthetic keys only."""
import argparse
import ctypes
import ctypes.util
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess


def decrypt_frames(data, key):
    lib = ctypes.CDLL(ctypes.util.find_library('sodium'))
    fn = lib.crypto_aead_xchacha20poly1305_ietf_decrypt
    fn.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulonglong), ctypes.c_void_p,
                   ctypes.c_void_p, ctypes.c_ulonglong, ctypes.c_void_p,
                   ctypes.c_ulonglong, ctypes.c_void_p, ctypes.c_void_p]
    fn.restype = ctypes.c_int
    assert len(data) >= 112 and data[:16] == b'DAPHREC1\x01\x00\x01\x00\x00\x10\x00\x00'
    header, at, sequence, previous = data[:64], 64, 0, bytes(16)
    result, final = [], False
    while at < len(data):
        assert not final and len(data) - at >= 48
        prefix = data[at:at + 32]
        n = int.from_bytes(prefix[8:12], 'little')
        assert int.from_bytes(prefix[:8], 'little') == sequence
        assert prefix[13:16] == bytes(3) and prefix[16:] == previous
        final = prefix[12] == 1
        assert prefix[12] in (0, 1) and n <= 4096 and ((n == 0) == final)
        sealed = data[at + 32:at + 48 + n]
        assert len(sealed) == n + 16
        plain, actual = ctypes.create_string_buffer(max(1, n)), ctypes.c_ulonglong()
        nonce = header[16:32] + sequence.to_bytes(8, 'little')
        assert fn(plain, ctypes.byref(actual), None, sealed, len(sealed), header + prefix,
                  96, nonce, key) == 0
        assert actual.value == n
        if not final:
            result.append(plain.raw[:n])
        previous = sealed[-16:]
        sequence += 1
        at += 48 + n
    assert final
    return result, header[32:64]


def events(data, key):
    frames, revision = decrypt_frames(data, key)
    assert frames and frames[0] == b'DAPHEVT1', 'missing typed capture marker'
    channels = [bytearray(), bytearray(), bytearray()]
    for frame in frames[1:]:
        assert len(frame) >= 3 and frame[0] <= 2
        kind, body = frame[0], frame[3:]
        assert int.from_bytes(frame[1:3], 'little') == len(body)
        assert len(body) <= (4093, 3101, 521)[kind]
        if kind:
            assert body and body.endswith(b'\n')
        channels[kind].extend(body)
    return tuple(bytes(c) for c in channels), revision


def decrypt(data, key):
    channels, revision = events(data, key)
    return channels[0], revision


def boot(image, destination, key_file=None, replay_file=None, replay_key=None):
    cmd = ['qemu-system-x86_64', '-display', 'none', '-accel', 'tcg', '-m', '128',
           '-serial', 'stdio', '-monitor', 'none', '-nic', 'none', '-no-reboot',
           '-device', 'isa-debug-exit,iobase=0xf4,iosize=0x04', '-kernel', str(image)]
    if key_file:
        cmd += ['-fw_cfg', 'name=opt/dev.integerc/daphnis-capture,file=' + str(key_file)]
    if replay_file:
        cmd += ['-fw_cfg', 'name=opt/dev.integerc/daphnis-replay,file=' + str(replay_file)]
    if replay_key:
        cmd += ['-fw_cfg', 'name=opt/dev.integerc/daphnis-replay-key,file=' + str(replay_key)]
    p = subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, timeout=30)
    destination.write_bytes(p.stdout)
    destination.with_suffix('.stderr').write_bytes(p.stderr)
    assert not p.stderr, p.stderr.decode(errors='replace')
    return p.returncode, p.stdout


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    root = Path(__file__).resolve().parents[2]
    out = args.out.resolve()
    assert out != root and root not in out.parents
    out.mkdir(parents=True, exist_ok=True)
    key = bytes(range(80, 112))
    stream = bytes(range(16))
    fixture = out / 'synthetic-recovery.key'
    fixture.write_bytes(b'DAPHKEY1' + key + stream)
    os.chmod(fixture, 0o600)
    output_key = bytes(range(112, 144))
    output_fixture = out / 'synthetic-replay-output.key'
    output_fixture.write_bytes(b'DAPHKEY1' + output_key + bytes(range(16, 32)))
    os.chmod(output_fixture, 0o600)
    receipt = {}
    for cc in ('gcc', 'clang'):
        rows = []
        for flavor, status in [('hello', 33), ('fault', 35), ('trap', 33)]:
            normal_image = out / 'normal' / f'{cc}-{flavor}' / 'kernel32.elf'
            image = out / 'encrypted' / f'{cc}-{flavor}' / 'kernel32.elf'
            normal_rc, normal = boot(normal_image, out / f'{cc}-{flavor}.plain')
            rc, sealed = boot(image, out / f'{cc}-{flavor}.capture', fixture)
            assert rc == normal_rc == status, (cc, flavor, rc, normal_rc)
            plain, revision = decrypt(sealed, key)
            assert plain == normal, (cc, flavor, 'transcript mismatch')
            assert key not in sealed and normal not in sealed
            emitted = (out / 'encrypted' / f'emit-{flavor}' / 'c' / 'cint-program.c').read_text()
            revision_text = emitted.split('cg_revision[32] = {', 1)[1].split('}', 1)[0]
            expected = bytes(int(x, 16) for x in re.findall(r'0x([0-9a-fA-F]{2})', revision_text))
            assert revision == expected
            symbols = subprocess.check_output(['nm', '-S', str(image.parent / 'kernel.elf')], text=True)
            for name in ('slots', 'key_file', 'sink', 'started', 'failed', 'busy', 'done',
                         'replay', 'replay_key', 'replay_file'):
                found = re.search(r'^([0-9a-f]+)\s+([0-9a-f]+)\s+[A-Za-z]\s+' + name + r'$', symbols, re.M)
                assert found and 0x200000 <= int(found[1], 16) < 0x400000
                assert int(found[1], 16) + int(found[2], 16) <= 0x400000
            rows.append({'flavor': flavor, 'bytes': len(sealed),
                         'capture_sha256': hashlib.sha256(sealed).hexdigest(),
                         'plaintext_sha256': hashlib.sha256(plain).hexdigest(),
                         'revision': revision.hex()})
        image = out / 'encrypted' / f'{cc}-hello' / 'kernel32.elf'
        original_capture = out / f'{cc}-hello.capture'
        original = original_capture.read_bytes()
        rc, again = boot(image, out / f'{cc}-hello-replay.capture', output_fixture, original_capture, fixture)
        assert rc == 33 and decrypt(again, output_key)[0] == decrypt(original, key)[0]
        changed = bytearray(original)
        changed[110] ^= 1
        variants = [('tampered', bytes(changed)), ('truncated', original[:-1]),
                    ('missing-final', original[:-48]), ('trailing', original + b'x'),
                    ('revision', (out / f'{cc}-fault.capture').read_bytes())]
        for label, material in variants:
            path = out / f'{cc}-{label}-input.capture'
            path.write_bytes(material)
            rc, data = boot(image, out / f'{cc}-{label}-refusal.capture', output_fixture, path, fixture)
            assert rc == 63 and not data, (cc, label, rc, len(data))
        for label, output, recording, recovery in [
                ('same-key', fixture, original_capture, fixture),
                ('wrong-key', fixture, original_capture, output_fixture),
                ('missing-replay-key', output_fixture, original_capture, None),
                ('missing-replay-file', output_fixture, None, fixture)]:
            rc, data = boot(image, out / f'{cc}-{label}-refusal.capture', output, recording, recovery)
            assert rc == 63 and not data, (cc, label, rc, len(data))
        for label, material in [('missing', None), ('short', b'DAPHKEY1' + key + stream[:-1]),
                                ('long', b'DAPHKEY1' + key + stream + b'x'),
                                ('magic', b'BADMAGIC' + key + stream)]:
            bad = None
            if material is not None:
                bad = out / f'{label}.key'
                bad.write_bytes(material)
            rc, data = boot(image, out / f'{cc}-{label}.capture', bad)
            assert rc == 63 and data == b'', (cc, label, rc, len(data))
        image = out / 'encrypted' / f'{cc}-captureports' / 'kernel32.elf'
        rc, data = boot(image, out / f'{cc}-ports.capture', fixture)
        plain, _ = decrypt(data, key)
        assert rc in (35, 63) and plain.startswith(b'capture: before private port refusal\n')
        assert b'unexpected private port access' not in plain and key not in plain
        receipt[cc] = rows
        print(f'pass: {cc} normal/fault/trap transcript equality, four key refusals, private port refusal, private symbols')
        print(f'pass: {cc} encrypted replay and nine input refusals before any output')
    (out / 'guest-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print('RESULT: PASS')


if __name__ == '__main__':
    main()
