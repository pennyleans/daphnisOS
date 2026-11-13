#!/usr/bin/env python3
"""Qualify encrypted local TLS fixture output with synthetic recovery bytes only."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
FETCH_SHA256 = '084487a97a04e4bab9c84ede5e9fabb706b6c9ca2380a0efdc22153186d44cea'
SYNTHETIC_FIXTURE = b'DAPHKEY1' + bytes(range(80, 112)) + bytes(range(16))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def module(name, path):
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location(name, path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def main():
    if not __debug__:
        raise RuntimeError('checks require assertions enabled')
    parser = argparse.ArgumentParser()
    parser.add_argument('--kernel', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--key-file', type=Path, required=True)
    parser.add_argument('--program', type=Path)   # default: fetch at the kernel's O/ubin, built by make (RG-1)
    args = parser.parse_args()
    kernel, out = args.kernel.resolve(), args.out.resolve()
    o = kernel.parent.parent
    fixtures = module('capture_tls_fixtures', ROOT / 'tools/check-fetch-https.py')
    ub = fixtures.built(o, ['fetch'])
    key_file, program = args.key_file.resolve(), (args.program or ub / 'fetch').resolve()
    assert out != ROOT and ROOT not in out.parents, 'outputs must be outside checkout'
    assert ROOT not in key_file.parents, 'synthetic key file must be outside checkout'
    assert out not in key_file.parents, 'key file must be separate from recording outputs'
    # QEMU_EXTRA is split by run-qemu.sh; only its literal safe path form is admitted.
    assert re.fullmatch(r'[A-Za-z0-9_./-]+', str(key_file)), 'unsafe fw_cfg fixture path'
    fixture = key_file.read_bytes()
    assert len(fixture) == 56 and fixture == SYNTHETIC_FIXTURE, 'expected synthetic DAPHKEY1 fixture'
    key = fixture[8:40]
    assert kernel.is_file() and digest(program) == FETCH_SHA256, 'unqualified fetch fixture'
    out.mkdir(parents=True, exist_ok=True)
    guest = module('capture_tls_guest', ROOT / 'tests/capture/check_guest.py')
    checks = []

    def check(name, ok):
        checks.append({'name': name, 'passed': bool(ok)})
        print(f'{"pass" if ok else "fail"}: {name}', flush=True)

    with fixtures.server(dns=True, guest=True) as dns, fixtures.server('api.mock.pem') as good:
        resolver = f'10.0.2.2:{dns.server_address[1]}'
        port = good.server_address[1]
        script = out / 'go.sh'
        script.write_text(
            f'./fetch -d {resolver} -o /saved https://api.mock:{port}/guest\n'
            'echo FETCH_GOOD=$?\ncat /saved\n'
            f'./fetch -d {resolver} -o - https://api.mock:{port}/redirect\n'
            'echo FETCH_REDIRECT=$?\n'
            f'./fetch -d {resolver} -o /saved https://wrong.mock:{port}/guest\n'
            'echo FETCH_BAD=$?\ncat /saved\n')
        archive = out / 'fetch.cpio'
        subprocess.run(['python3', 'tools/mkcpio.py', str(archive),
                        *fixtures.shell_members(o),
                        f'fetch={program}', f'go.sh={script}'], cwd=ROOT,
                       check=True, capture_output=True)
        env = dict(os.environ)
        for name in ['NET_FWD', 'DISK', 'MONITOR', 'STDIN_FILE', 'SOUND',
                     'APPEND', 'RTC', 'POOL', 'MODE', 'PLAY_DISPLAY']:
            env.pop(name, None)
        env.update(NET='user', CPU='max', INITRD=str(archive), QEMU_TIMEOUT='60',
                   KVM='0', PLAY='0', MEM='128',
                   QEMU_EXTRA='-fw_cfg name=opt/dev.integerc/daphnis-capture,file=' + str(key_file))
        capture = out / 'guest.capture'
        boot = subprocess.run(['tools/run-qemu.sh', str(kernel), str(capture)],
                              cwd=ROOT, env=env, capture_output=True, timeout=70,
                              stdin=subprocess.DEVNULL)
        (out / 'runner.stdout').write_bytes(boot.stdout)
        (out / 'runner.stderr').write_bytes(boot.stderr)
        sealed = capture.read_bytes()
        # The shared decoder requires every chained tag, an empty final, and EOF.
        data, revision = guest.decrypt(sealed, key)
        assert sealed[16:32] == fixture[40:56], 'stream fixture mismatch'
        (out / 'recovered.serial').write_bytes(data)
        check('daphnis exits cleanly', boot.returncode == 0 and boot.stdout.strip() == b'33'
              and not Path(str(capture) + '.err').read_bytes() and not boot.stderr)
        check('daphnis https succeeds', b'FETCH_GOOD=0\n' in data)
        check('daphnis https redirect succeeds', b'FETCH_REDIRECT=0\n' in data)
        check('daphnis hostname rejection', b'FETCH_BAD=1\n' in data and b'tls: error 1056' in data)
        check('daphnis rejection preserves destination', data.count(b'fetch-https-guest-ok\n') == 3)
        check('daphnis follows the location', len(good.requests) == 3
              and b'GET /guest HTTP/1.1' in good.requests[0]
              and b'GET /redirect HTTP/1.1' in good.requests[1]
              and b'GET /guest HTTP/1.1' in good.requests[2] and b'discard' not in data)
        check('daphnis authenticates before http', len(good.requests) == 3)
        check('daphnis closes connections', b'tcp connections open 0' in data)
        assert len(checks) == 8
        requests = len(good.requests)

    records = [line for line in data.splitlines() if line.startswith(b'rng ')]
    draws = []
    for line in records:
        match = re.fullmatch(rb'rng ([1-9][0-9]*) ([0-9a-f]+)', line)
        assert match, 'malformed recovered RNG record'
        size, encoded = int(match[1]), match[2]
        assert 1 <= size <= 256 and len(encoded) == 2 * size, 'bad recovered RNG length'
        raw = bytes.fromhex(encoded.decode('ascii'))
        assert raw not in sealed and encoded not in sealed.lower(), 'RNG bytes exposed in capture'
        draws.append(size)
    assert len(draws) >= 3 and b'daphnis: rng rdrand, live\n' in data, 'missing live TLS RNG draws'
    assert key not in sealed and key.hex().encode('ascii') not in sealed.lower(), 'key exposed in capture'
    channels, _ = guest.events(sealed, key)
    assert channels[1].startswith(b'net mac ') and channels[2].startswith(b'rtc ')
    replay_key = bytes(range(112, 144))
    replay_key_file = out.parent / (out.name + '-replay-output.key')
    replay_key_file.write_bytes(b'DAPHKEY1' + replay_key + bytes(range(16, 32)))
    os.chmod(replay_key_file, 0o600)
    replay_capture = out / 'replay.capture'
    env.update(NET='none', CPU='qemu64,-rdrand',
               QEMU_EXTRA='-fw_cfg name=opt/dev.integerc/daphnis-capture,file=' + str(replay_key_file)
               + ' -fw_cfg name=opt/dev.integerc/daphnis-replay-key,file=' + str(key_file)
               + ' -fw_cfg name=opt/dev.integerc/daphnis-replay,file=' + str(capture))
    replay = subprocess.run(['tools/run-qemu.sh', str(kernel), str(replay_capture)],
                            cwd=ROOT, env=env, capture_output=True, timeout=70,
                            stdin=subprocess.DEVNULL)
    (out / 'replay-runner.stdout').write_bytes(replay.stdout)
    (out / 'replay-runner.stderr').write_bytes(replay.stderr)
    assert replay.returncode == 0 and replay.stdout.strip() == b'33' and not replay.stderr
    assert not Path(str(replay_capture) + '.err').read_bytes()
    replay_sealed = replay_capture.read_bytes()
    replay_channels, replay_revision = guest.events(replay_sealed, replay_key)
    replay_serial = out / 'replay.serial'
    replay_serial.write_bytes(replay_channels[0])
    assert replay_revision == revision and replay_channels[1:] == channels[1:]
    assert b'daphnis: rng replay' in replay_channels[0] and b'daphnis: net replay' in replay_channels[0]
    comparison = subprocess.run(['python3', 'tools/netjournal.py', 'same',
                                 str(out / 'recovered.serial'), str(replay_serial)],
                                cwd=ROOT, capture_output=True, check=True)
    (out / 'replay-comparison.log').write_bytes(comparison.stdout)
    assert replay_sealed != sealed and replay_key not in replay_sealed
    print('pass: encrypted replay without NIC or RDRAND, unchanged initrd, same typed inputs and console')
    sources = [Path(__file__), ROOT / 'tools/check-fetch-https.py',
               ROOT / 'tests/capture/check_guest.py', ROOT / 'tools/run-qemu.sh',
               ROOT / 'tools/mkcpio.py', ROOT / 'src/rng.ci', ROOT / 'src/main_net.ci',
               ROOT / 'Makefile', ub / 'cish', ub / 'grant',
               ROOT / 'tests/tls/api.mock.pem', ROOT / 'tests/tls/api.mock.key']
    receipt = {
        'synthetic_only': True,
        'kernel': str(kernel), 'kernel_sha256': digest(kernel),
        'fetch': str(program), 'fetch_sha256': digest(program),
        'capture_sha256': hashlib.sha256(sealed).hexdigest(),
        'recovered_transcript_sha256': hashlib.sha256(data).hexdigest(),
        'capture_bytes': len(sealed), 'recovered_bytes': len(data),
        'revision': revision.hex(), 'http_requests': requests,
        'rng_records': len(draws), 'rng_bytes': sum(draws), 'rng_draw_lengths': draws,
        'checks': checks,
        'sources_sha256': {str(p.relative_to(ROOT)): digest(p) for p in sources},
        'initrd_sha256': digest(archive), 'script_sha256': digest(script),
        'replay_without_live_inputs': True,
        'replay_capture_sha256': digest(replay_capture),
        'replay_transcript_sha256': digest(replay_serial),
        'typed_network_bytes': len(channels[1]), 'typed_rng_bytes': len(channels[2]),
    }
    (out / 'tls-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(f'http requests: {requests}; rng records: {len(draws)}; rng bytes: {sum(draws)}')
    print(f'receipt: {out / "tls-receipt.json"}')
    passed = all(row['passed'] for row in checks)
    print(f'result: {"pass" if passed else "fail"} ({sum(row["passed"] for row in checks)}/8)')
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
