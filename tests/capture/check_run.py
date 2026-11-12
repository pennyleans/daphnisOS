#!/usr/bin/env python3
"""Exercise the bounded Unix capture launcher using temporary synthetic sessions."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import tempfile
import shutil
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('capture_run', ROOT / 'tools/capture-run.py')
run = None
if Path(SPEC.origin).exists():
    run = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(run)

HEADER = b'DAPHREC1\x01\0\x01\0\0\x10\0\0'


def envelope(stream):
    return HEADER + stream + bytes(32) + bytes(8) + bytes(4) + b'\x01' + bytes(35)


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(run, 'bounded launcher is missing')
        self.tmp = tempfile.TemporaryDirectory(prefix='capture-run-', dir=TEST_OUT)
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.kernel = self.base / 'kernel,with=keyval.elf'
        self.kernel.write_bytes(b'synthetic image')
        self.qemu = self.base / 'qemu'
        self.output = self.base / 'session'
        self.key = self.base / 'recovery.key'
        self.meta = self.base / 'argv.json'
        self.fake()
        self.guard = patch.object(run, 'validate_kernel')
        self.guard.start()
        self.addCleanup(self.guard.stop)

    def fake(self, mode='complete', exit_code=33):
        self.qemu.write_text('''#!/usr/bin/python3
import json, os, pathlib, sys, time
args = sys.argv[1:]
items = [args[i+1] for i, x in enumerate(args) if x == '-fw_cfg']
fds = [int(x.split('/proc/self/fd/')[1]) for x in items]
blobs = [os.pread(fd, os.fstat(fd).st_size, 0) for fd in fds]
pathlib.Path(%r).write_text(json.dumps({'argv': args, 'sizes': [len(b) for b in blobs]}))
key = blobs[0]
data = %r + key[40:56] + bytes(32) + bytes(8) + bytes(4) + b'\\x01' + bytes(35)
mode = %r
if mode == 'plaintext': data = b'secret plaintext, never store this'
if mode == 'partial': data = data[:-1]
if mode == 'short-header': data = b'DAPHREC1'
if mode == 'overflow': data += bytes(17 * 1024 * 1024)
if mode == 'empty': data = b''
if mode == 'trailing': data += b'x'
if mode == 'missing-final': data = data[:64]
os.write(1, data)
if mode == 'timeout': time.sleep(10)
sys.exit(%r)
''' % (str(self.meta), HEADER, mode, exit_code))
        self.qemu.chmod(0o700)

    def args(self, command='record', **kw):
        values = {'kernel': self.kernel, 'output': self.output, 'key': self.key,
                  'qemu': self.qemu, 'timeout': '2'}
        values.update(kw)
        argv = [command]
        for name, value in values.items():
            argv += ['--' + name.replace('_', '-'), str(value)]
        return argv

    def invoke(self, **kw):
        return run.main(self.args(**kw))

    def manifest(self):
        return json.loads((self.output / 'manifest.json').read_text())

    def test_record_private_files_and_fd_command(self):
        self.assertEqual(self.invoke(network='user'), 0)
        self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), 0o700)
        for file in self.output.iterdir():
            self.assertEqual(stat.S_IMODE(file.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.key.stat().st_mode), 0o600)
        data = self.meta.read_text()
        self.assertNotIn(str(self.key), data)
        self.assertNotIn(str(self.kernel), data)
        argv = json.loads(data)['argv']
        for required in ('tcg', 'none', 'user,model=virtio-net-pci', 'max', 'stdio', 'isa-debug-exit,iobase=0xf4,iosize=0x04'):
            self.assertIn(required, argv)
        self.assertEqual(json.loads(data)['sizes'], [56])
        manifest = self.manifest()
        self.assertEqual(manifest['status'], 'recorded')
        self.assertEqual(manifest['exit']['returncode'], 33)
        self.assertEqual(manifest['authentication'], 'not independently authenticated')
        self.assertEqual(manifest['kernel_sha256'], hashlib.sha256(self.kernel.read_bytes()).hexdigest())
        self.assertEqual(manifest['capture_sha256'], hashlib.sha256((self.output / 'capture.cr1').read_bytes()).hexdigest())
        self.assertNotIn(self.key.read_bytes()[8:40].hex(), json.dumps(manifest))

    def test_fresh_keys_for_every_run(self):
        self.assertEqual(self.invoke(), 0)
        original = self.key.read_bytes()
        self.assertEqual(self.invoke(output=self.base / 'again', key=self.base / 'again.key'), 0)
        self.assertNotEqual(original[8:40], (self.base / 'again.key').read_bytes()[8:40])
        self.assertNotEqual(original[40:], (self.base / 'again.key').read_bytes()[40:])

    def test_replay_fd_inputs_no_network_no_rdrand(self):
        self.assertEqual(self.invoke(), 0)
        original = self.key.read_bytes()
        self.output, source = self.base / 'replay', self.output
        self.key, source_key = self.base / 'replay.key', self.key
        self.assertEqual(self.invoke(command='replay', input=source, input_key=source_key), 0)
        meta = json.loads(self.meta.read_text())
        self.assertEqual(meta['sizes'][0], 56)
        self.assertEqual(meta['sizes'][1:], [(source / 'capture.cr1').stat().st_size, 56])
        argv = meta['argv']
        self.assertEqual(argv[argv.index('-nic') + 1], 'none')
        self.assertIn('max,-rdrand,-rdseed', argv)
        self.assertNotIn(str(source_key), json.dumps(meta))
        self.assertNotEqual(original[8:40], self.key.read_bytes()[8:40])
        self.assertEqual(self.manifest()['input_capture_sha256'], hashlib.sha256((source / 'capture.cr1').read_bytes()).hexdigest())

    def test_plaintext_and_short_header_never_saved(self):
        for mode in ('plaintext', 'short-header'):
            with self.subTest(mode=mode):
                self.fake(mode)
                self.output, self.key = self.base / mode, self.base / (mode + '.key')
                self.assertEqual(self.invoke(), 1)
                self.assertEqual((self.output / 'capture.cr1').read_bytes(), b'')
                self.assertEqual(self.manifest()['status'], 'failed')
                self.assertTrue(self.key.exists())

    def test_failures_preserve_ciphertext_and_key(self):
        for mode, code in (('partial', 33), ('complete', 37), ('timeout', 33), ('overflow', 33), ('empty', 63), ('trailing', 33), ('missing-final', 33)):
            with self.subTest(mode=mode, code=code):
                self.fake(mode, code)
                self.output, self.key = self.base / (mode + str(code)), self.base / (mode + str(code) + '.key')
                self.assertEqual(self.invoke(timeout='.15'), 1)
                m = self.manifest()
                self.assertEqual(m['status'], 'failed')
                self.assertTrue(self.key.exists())
                self.assertLessEqual((self.output / 'capture.cr1').stat().st_size, run.MAX_CAPTURE)
                if mode == 'timeout':
                    self.assertTrue(m['exit']['timed_out'])
                if mode == 'partial':
                    self.assertGreater((self.output / 'capture.cr1').stat().st_size, 64)

    def test_nooverwrite_symlink_fifo_and_alias(self):
        for kind in ('existing-key', 'key-link', 'key-fifo', 'existing-output', 'output-link', 'same', 'nested'):
            with self.subTest(kind=kind):
                case = self.base / kind
                case.mkdir(mode=0o700)
                self.output, self.key = case / 'session', case / 'key'
                if kind == 'existing-key': self.key.write_bytes(b'keep')
                if kind == 'key-link': self.key.symlink_to(self.kernel)
                if kind == 'key-fifo': os.mkfifo(self.key, 0o600)
                if kind == 'existing-output': self.output.mkdir(mode=0o700)
                if kind == 'output-link': self.output.symlink_to(self.kernel)
                if kind == 'same': self.key = self.output
                if kind == 'nested': self.key = self.output / 'key'
                self.assertEqual(self.invoke(), 1)
                if kind == 'existing-key': self.assertEqual(self.key.read_bytes(), b'keep')
                self.assertEqual(self.kernel.read_bytes(), b'synthetic image')

    def test_reject_public_parent_and_repository_key(self):
        public = self.base / 'public'
        public.mkdir(mode=0o755)
        public.chmod(0o755)
        self.assertEqual(self.invoke(key=public / 'key'), 1)
        self.assertEqual(self.invoke(key=ROOT / 'never-created.key'), 1)
        self.assertFalse(self.output.exists())

    def test_input_hash_manifest_and_image_tamper(self):
        self.assertEqual(self.invoke(), 0)
        source, source_key = self.output, self.key
        manifest_file = source / 'manifest.json'
        original = manifest_file.read_bytes()
        for field in ('capture_sha256', 'kernel_sha256', 'stream_id', 'program_revision', 'status', 'initrd_sha256'):
            with self.subTest(field=field):
                m = json.loads(original)
                m[field] = 'tampered'
                manifest_file.write_text(json.dumps(m))
                self.output, self.key = self.base / field, self.base / (field + '.key')
                self.assertEqual(self.invoke(command='replay', input=source, input_key=source_key), 1)
                self.assertFalse(self.output.exists())
        manifest_file.write_bytes(original)
        (source / 'capture.cr1').write_bytes((source / 'capture.cr1').read_bytes() + b'x')
        self.output, self.key = self.base / 'artifact', self.base / 'artifact.key'
        self.assertEqual(self.invoke(command='replay', input=source, input_key=source_key), 1)
        self.assertFalse(self.output.exists())

    def test_key_input_alias_and_bad_input_key(self):
        self.assertEqual(self.invoke(), 0)
        source, source_key = self.output, self.key
        self.output, self.key = self.base / 'replay', source_key
        self.assertEqual(self.invoke(command='replay', input=source, input_key=source_key), 1)
        self.assertFalse(self.output.exists())
        bad = self.base / 'bad.key'
        bad.write_bytes(source_key.read_bytes())
        bad.chmod(0o644)
        self.assertEqual(self.invoke(command='replay', key=self.base / 'new.key', input=source, input_key=bad), 1)
        self.assertFalse(self.output.exists())

    def test_capture_guard_refuses_plain_kernel(self):
        self.guard.stop()
        self.assertEqual(self.invoke(), 1)
        self.assertFalse(self.output.exists())

    def test_complete_fault_stays_replayable_with_nonzero_cli(self):
        self.fake('complete', 35)
        self.assertEqual(self.invoke(), 1)
        self.assertEqual(self.manifest()['status'], 'recorded')
        self.assertEqual(self.manifest()['guest_outcome'], 'fault')
        source, source_key = self.output, self.key
        self.output, self.key = self.base / 'replay', self.base / 'replay.key'
        self.assertEqual(self.invoke(command='replay', input=source, input_key=source_key), 1)
        self.assertEqual(self.manifest()['status'], 'recorded')
        self.assertEqual(self.manifest()['guest_outcome'], 'fault')
    def test_failed_input_exit_state_refused(self):
        self.assertEqual(self.invoke(), 0)
        source, source_key = self.output, self.key
        m = self.manifest()
        m['exit']['returncode'] = 35
        (source / 'manifest.json').write_text(json.dumps(m))
        self.output, self.key = self.base / 'replay', self.base / 'replay.key'
        self.assertEqual(self.invoke(command='replay', input=source, input_key=source_key), 1)
        self.assertFalse(self.output.exists())

    def test_partial_capture_binds_visible_header_identity(self):
        self.fake('partial')
        self.assertEqual(self.invoke(), 1)
        m = self.manifest()
        self.assertEqual(m['stream_id'], self.key.read_bytes()[40:].hex())
        self.assertEqual(m['program_revision'], bytes(32).hex())
    def test_interrupt_retains_cancelled_exit_state(self):
        self.fake('timeout')
        with patch.object(run.selectors.DefaultSelector, 'select', side_effect=KeyboardInterrupt):
            try:
                status = self.invoke()
            except KeyboardInterrupt:
                self.fail('interrupt escaped without failed session status')
        self.assertEqual(status, 1)
        state = self.manifest()['exit']
        self.assertTrue(state['cancelled'])
        self.assertEqual(state['returncode'], -9)
        self.assertEqual(state['signal'], 9)
        self.assertTrue(self.key.exists())
    def test_initrd_identity_and_fd_passing(self):
        initrd = self.base / 'initrd,with=keyval.cpio'
        initrd.write_bytes(b'unchanged synthetic initrd')
        self.assertEqual(self.invoke(initrd=initrd), 0)
        m = self.manifest()
        self.assertEqual(m['initrd_sha256'], hashlib.sha256(initrd.read_bytes()).hexdigest())
        meta = self.meta.read_text()
        self.assertNotIn(str(initrd), meta)
        self.assertIn('-initrd', json.loads(meta)['argv'])
        source, source_key = self.output, self.key
        self.output, self.key = self.base / 'replay', self.base / 'replay.key'
        self.assertEqual(self.invoke(command='replay', input=source, input_key=source_key), 1)
        self.assertFalse(self.output.exists())
        self.assertEqual(self.invoke(command='replay', input=source, input_key=source_key, initrd=initrd), 0)
        self.assertEqual(initrd.read_bytes(), b'unchanged synthetic initrd')

    def test_parent_symlink_alias_is_refused(self):
        alias = self.base / 'alias'
        alias.symlink_to(self.base, target_is_directory=True)
        self.assertEqual(self.invoke(key=alias / self.output.name), 1)
        self.assertFalse(self.output.exists())

    def test_input_capture_symlink_is_refused_without_mutation(self):
        self.assertEqual(self.invoke(), 0)
        source, source_key = self.output, self.key
        artifact = source / 'capture.cr1'
        artifact.rename(self.base / 'saved.cr1')
        artifact.symlink_to(self.base / 'saved.cr1')
        self.output, self.key = self.base / 'replay', self.base / 'replay.key'
        self.assertEqual(self.invoke(command='replay', input=source, input_key=source_key), 1)
        self.assertFalse(self.output.exists())
        self.assertTrue(artifact.is_symlink())
        self.assertTrue((self.base / 'saved.cr1').exists())
    def test_missing_qemu_retains_failed_status(self):
        self.assertEqual(self.invoke(qemu=self.base / 'absent-qemu'), 1)
        self.assertEqual(self.manifest()['status'], 'failed')
        self.assertTrue(self.key.exists())




def fault_check(directory, images, compiler):
    from check_guest import events
    kernel = images / (compiler + '-fault') / 'kernel32.elf'
    record, replay = directory / (compiler + '-fault-record'), directory / (compiler + '-fault-replay')
    key, fresh = directory / (compiler + '-fault.key'), directory / (compiler + '-fault-replay.key')
    common = ['--kernel', str(kernel), '--timeout', '30']
    assert run.main(['record'] + common + ['--output', str(record), '--key', str(key)]) == 1
    assert run.main(['replay'] + common + ['--output', str(replay), '--key', str(fresh), '--input', str(record), '--input-key', str(key)]) == 1
    first, again = (record / 'capture.cr1').read_bytes(), (replay / 'capture.cr1').read_bytes()
    assert events(first, key.read_bytes()[8:40]) == events(again, fresh.read_bytes()[8:40])
    for session in (record, replay):
        manifest = json.loads((session / 'manifest.json').read_text())
        assert manifest['status'] == 'recorded' and manifest['guest_outcome'] == 'fault'
        assert manifest['exit']['returncode'] == 35
    return {'kernel_sha256': hashlib.sha256(kernel.read_bytes()).hexdigest(),
            'record_exit': 35, 'replay_exit': 35, 'cli_exit': 1,
            'independent_authentication_and_equality': True}


def tls_check(directory, images, compiler):
    from check_guest import events
    spec = importlib.util.spec_from_file_location('launcher_tls', ROOT / 'tools/check-fetch-https.py')
    fixtures = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixtures)
    kernel = images / (compiler + '-net') / 'kernel32.elf'
    initrd = directory / (compiler + '-tls.cpio')
    script = directory / (compiler + '-go.sh')
    record, replay = directory / (compiler + '-tls-record'), directory / (compiler + '-tls-replay')
    key, fresh = directory / (compiler + '-tls.key'), directory / (compiler + '-tls-replay.key')
    with fixtures.server(dns=True, guest=True) as dns, fixtures.server('api.mock.pem') as good:
        resolver = f'10.0.2.2:{dns.server_address[1]}'
        port = good.server_address[1]
        script.write_text(
            f'./fetch -d {resolver} -o /saved https://api.mock:{port}/guest\n'
            'echo FETCH_GOOD=$?\ncat /saved\n'
            f'./fetch -d {resolver} -o - https://api.mock:{port}/redirect\n'
            'echo FETCH_REDIRECT=$?\n'
            f'./fetch -d {resolver} -o /saved https://wrong.mock:{port}/guest\n'
            'echo FETCH_BAD=$?\ncat /saved\n')
        script.chmod(0o600)
        run.subprocess.run(['python3', 'tools/mkcpio.py', str(initrd),
                            *fixtures.shell_members(images),
                            f'fetch={fixtures.built(images, ["fetch"]) / "fetch"}', f'go.sh={script}'], cwd=ROOT,
                           check=True, capture_output=True)
        initrd.chmod(0o600)
        common = ['--kernel', str(kernel), '--initrd', str(initrd), '--timeout', '60']
        assert run.main(['record'] + common + ['--output', str(record), '--key', str(key), '--network', 'user']) == 0
        assert len(good.requests) == 3
    # Both fixture servers have stopped before offline replay starts.
    assert run.main(['replay'] + common + ['--output', str(replay), '--key', str(fresh), '--input', str(record), '--input-key', str(key)]) == 0
    first, again = (record / 'capture.cr1').read_bytes(), (replay / 'capture.cr1').read_bytes()
    channels, revision = events(first, key.read_bytes()[8:40])
    replay_channels, replay_revision = events(again, fresh.read_bytes()[8:40])
    assert revision == replay_revision and channels[1:] == replay_channels[1:]
    modes = (b'daphnis: net virtio-net', b'daphnis: net replay', b'daphnis: rng rdrand', b'daphnis: rng replay')
    normalize = lambda data: [line for line in data.split(b'\n') if not line.startswith(modes)]
    assert normalize(channels[0]) == normalize(replay_channels[0])
    assert all(marker in channels[0] for marker in (b'FETCH_GOOD=0\n', b'FETCH_REDIRECT=0\n', b'FETCH_BAD=1\n', b'tls: error 1056'))
    assert channels[0].count(b'fetch-https-guest-ok\n') == 3
    assert channels[1].startswith(b'net mac ') and channels[2].startswith(b'rtc ')
    assert b'daphnis: rng rdrand, live\n' in channels[0]
    assert b'daphnis: rng replay' in replay_channels[0] and b'daphnis: net replay' in replay_channels[0]
    for sealed in (first, again):
        for recovery in (key, fresh):
            secret = recovery.read_bytes()[8:40]
            assert secret not in sealed and secret.hex().encode() not in sealed
        for line in channels[2].splitlines():
            if line.startswith(b'rng '):
                encoded = line.split()[2]
                assert encoded not in sealed and bytes.fromhex(encoded.decode()) not in sealed
    return {'kernel_sha256': hashlib.sha256(kernel.read_bytes()).hexdigest(),
            'initrd_sha256': hashlib.sha256(initrd.read_bytes()).hexdigest(),
            'record_sha256': hashlib.sha256(first).hexdigest(), 'replay_sha256': hashlib.sha256(again).hexdigest(),
            'record_bytes': len(first), 'replay_bytes': len(again),
            'decrypted_channel_bytes': [len(channel) for channel in channels],
            'http_requests': 3, 'https_success_redirect_hostname_refusal': True,
            'offline_replay_after_servers_stopped': True,
            'independent_authentication_input_equality_normalized_console_equality': True,
            'raw_key_rng_and_hex_absent': True}

def guest_checks(output, images):
    """Use only temporary synthetic secrets and retain private ciphertext receipts."""
    from check_guest import events
    directory = Path(tempfile.mkdtemp(prefix='guest-', dir=output))
    receipt = {'sessions': str(directory), 'compilers': {}}
    for compiler in ('gcc', 'clang'):
        kernel = images / (compiler + '-hello') / 'kernel32.elf'
        record, replay = directory / (compiler + '-record'), directory / (compiler + '-replay')
        record_key, replay_key = directory / (compiler + '-record.key'), directory / (compiler + '-replay.key')
        common = ['--kernel', str(kernel), '--timeout', '30']
        assert run.main(['record'] + common + ['--output', str(record), '--key', str(record_key), '--network', 'none']) == 0
        assert run.main(['replay'] + common + ['--output', str(replay), '--key', str(replay_key), '--input', str(record), '--input-key', str(record_key)]) == 0
        first, again = (record / 'capture.cr1').read_bytes(), (replay / 'capture.cr1').read_bytes()
        first_key, again_key = record_key.read_bytes()[8:40], replay_key.read_bytes()[8:40]
        original_events, revision = events(first, first_key)
        replay_events, replay_revision = events(again, again_key)
        assert original_events == replay_events and revision == replay_revision
        assert original_events[0] and first_key != again_key
        for sealed in (first, again):
            for secret in (first_key, again_key):
                assert secret not in sealed and secret.hex().encode() not in sealed
            assert original_events[0] not in sealed
        bad = directory / (compiler + '-tampered-source')
        shutil.copytree(record, bad)
        data = bytearray((bad / 'capture.cr1').read_bytes())
        data[96] ^= 1
        (bad / 'capture.cr1').write_bytes(data)
        manifest = json.loads((bad / 'manifest.json').read_text())
        manifest['capture_sha256'] = hashlib.sha256(data).hexdigest()
        (bad / 'manifest.json').write_text(json.dumps(manifest))
        refused, refused_key = directory / (compiler + '-refused'), directory / (compiler + '-refused.key')
        assert run.main(['replay'] + common + ['--output', str(refused), '--key', str(refused_key), '--input', str(bad), '--input-key', str(record_key)]) == 1
        rejection = json.loads((refused / 'manifest.json').read_text())
        assert rejection['status'] == 'failed' and rejection['exit']['returncode'] == 63
        assert not (refused / 'capture.cr1').read_bytes() and refused_key.exists()
        receipt['compilers'][compiler] = {
            'kernel_path': str(kernel), 'kernel_sha256': hashlib.sha256(kernel.read_bytes()).hexdigest(),
            'program_revision': revision.hex(), 'record_bytes': len(first), 'replay_bytes': len(again),
            'record_sha256': hashlib.sha256(first).hexdigest(), 'replay_sha256': hashlib.sha256(again).hexdigest(),
            'decrypted_channel_bytes': [len(channel) for channel in original_events],
            'independent_libsodium_authentication': True, 'all_channel_equality': True,
            'raw_secret_and_hex_absent': True, 'tampered_rehashed_input_exit': 63,
            'tampered_replay_output_bytes': 0}
        receipt['compilers'][compiler]['fault'] = fault_check(directory, images, compiler)
        receipt['compilers'][compiler]['tls'] = tls_check(directory, images, compiler)
    (directory / 'test-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    (directory / 'test-receipt.json').chmod(0o600)
    print('pass: gcc and clang hello/fault capture, local https, offline replay, libsodium equality, tamper refusal')
    print('guest receipt: ' + str(directory / 'test-receipt.json'))

if __name__ == '__main__':
    if not __debug__:
        raise RuntimeError('checks require assertions enabled')
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--guest-images', type=Path)
    args, unittest_args = parser.parse_known_args()
    TEST_OUT = args.out.resolve()
    assert ROOT != TEST_OUT and ROOT not in TEST_OUT.parents
    TEST_OUT.mkdir(parents=True, exist_ok=True, mode=0o700)
    result = unittest.main(argv=[__file__] + unittest_args, exit=False).result
    if not result.wasSuccessful():
        sys.exit(1)
    if args.guest_images:
        guest_checks(TEST_OUT, args.guest_images.resolve())