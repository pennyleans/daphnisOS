#!/usr/bin/env python3
"""Run a bounded Unix-host encrypted capture or offline replay with QEMU TCG."""
import argparse
from contextlib import ExitStack
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import selectors
import stat
import struct
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location('capture_key', ROOT / 'tools/capture-key.py')
keys = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(keys)
HEADER_PREFIX = b'DAPHREC1\x01\0\x01\0\0\x10\0\0'
MAX_CAPTURE = 16 * 1024 * 1024
MAX_DIAGNOSTICS = 1024 * 1024
REQUIRED_SYMBOLS = {'rt_capture_boot', 'daph_capture_sink_begin', 'daph_capture_replay_open'}


def canonical(path):
    """Resolve existing parents while preserving the final no-follow component."""
    path = Path(path).absolute()
    if path.name in ('', '.', '..'):
        raise ValueError('invalid path')
    return path.parent.resolve(strict=True) / path.name


def within(path, parent):
    return path == parent or parent in path.parents


def private_directory(path):
    info = path.lstat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) & 0o077):
        raise ValueError('a trusted private directory is required')


def absent(path):
    if os.path.lexists(path):
        raise ValueError('destination already exists')


def fingerprint(fd):
    info = os.fstat(fd)
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def regular(stack, path, private=False, limit=None):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    stack.callback(os.close, fd)
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode):
        raise ValueError('input must be a regular file')
    if private and (stat.S_IMODE(info.st_mode) != 0o600 or info.st_uid != os.getuid()):
        raise ValueError('private input must have mode 0600 and current uid')
    if limit is not None and info.st_size > limit:
        raise ValueError('input exceeds size bound')
    return fd


def key_fd(stack, path):
    private_directory(path.parent)
    checked = keys.load_key(path)
    fd = regular(stack, path, private=True, limit=56)
    if os.pread(fd, 57, 0) != checked:
        raise ValueError('recovery file changed')
    return fd, checked


def digest(fd):
    result, offset = hashlib.sha256(), 0
    while True:
        chunk = os.pread(fd, 65536, offset)
        if not chunk:
            return result.hexdigest()
        result.update(chunk)
        offset += len(chunk)


def fd_path(fd):
    return '/proc/self/fd/' + str(fd)


def validate_kernel(fd):
    """Require the capture/replay boundary symbols before opening serial output."""
    result = subprocess.run(['nm', '--defined-only', fd_path(fd)], pass_fds=(fd,),
                            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, timeout=10, check=True)
    found = {line.split()[-1].decode('ascii', errors='replace')
             for line in result.stdout.splitlines() if line.split()}
    if not REQUIRED_SYMBOLS <= found:
        raise ValueError('kernel lacks required capture/replay symbols')


def structure(fd):
    """Check envelope framing only. This does not authenticate ciphertext."""
    size = os.fstat(fd).st_size
    header = os.pread(fd, 64, 0)
    if size > MAX_CAPTURE or len(header) != 64 or header[:16] != HEADER_PREFIX:
        raise ValueError('invalid capture header or size')
    offset, sequence, previous, final = 64, 0, bytes(16), False
    while offset < size:
        prefix = os.pread(fd, 32, offset)
        if final or len(prefix) != 32:
            raise ValueError('invalid capture frame')
        seq, length, flag = struct.unpack('<QIB', prefix[:13])
        if (seq != sequence or seq == (1 << 64) - 1 or prefix[13:16] != bytes(3)
                or prefix[16:] != previous or flag not in (0, 1) or length > 4096
                or ((length == 0) != (flag == 1)) or offset + 48 + length > size):
            raise ValueError('invalid capture frame')
        previous = os.pread(fd, 16, offset + 32 + length)
        offset += 48 + length
        sequence += 1
        final = flag == 1
    if not final:
        raise ValueError('capture has no complete final frame')
    return header


def write_all(fd, data):
    view = memoryview(data)
    while view:
        count = os.write(fd, view)
        if count <= 0:
            raise OSError('short artifact write')
        view = view[count:]


def save_manifest(fd, manifest):
    payload = (json.dumps(manifest, indent=2, sort_keys=True) + '\n').encode()
    os.lseek(fd, 0, os.SEEK_SET)
    write_all(fd, payload)
    os.ftruncate(fd, len(payload))
    os.fsync(fd)


def artifact(stack, directory_fd, name):
    fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                 0o600, dir_fd=directory_fd)
    stack.callback(os.close, fd)
    os.fchmod(fd, 0o600)
    return fd


def command(args, kernel, initrd, output_key, input_capture=None, input_key=None):
    argv = [args.qemu, '-display', 'none', '-accel', 'tcg', '-m', '128',
            '-serial', 'stdio', '-monitor', 'none', '-nic',
            'user,model=virtio-net-pci' if args.command == 'record' and args.network == 'user' else 'none',
            '-no-reboot', '-device', 'isa-debug-exit,iobase=0xf4,iosize=0x04',
            '-kernel', fd_path(kernel)]
    if initrd is not None:
        argv += ['-initrd', fd_path(initrd)]
    argv += ['-cpu', 'max,-rdrand,-rdseed' if args.command == 'replay' else 'max']
    for name, fd in (('capture', output_key), ('replay', input_capture), ('replay-key', input_key)):
        if fd is not None:
            argv += ['-fw_cfg', 'name=opt/dev.integerc/daphnis-' + name + ',file=' + fd_path(fd)]
    return argv


def execute(argv, passed, capture, stream, timeout):
    """Bound runtime and output, withholding serial bytes until header qualification."""
    state = {'returncode': None, 'timed_out': False, 'signal': None, 'cancelled': False}
    error = None
    stderr_hash, stderr_bytes = hashlib.sha256(), 0
    pending, accepted, count = bytearray(), False, 0
    process = None
    try:
        process = subprocess.Popen(argv, pass_fds=tuple(passed), stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        deadline = time.monotonic() + timeout
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ, 'stdout')
            selector.register(process.stderr, selectors.EVENT_READ, 'stderr')
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    state['timed_out'] = True
                    raise ValueError('runtime timeout')
                for selected, _ in selector.select(min(remaining, 0.1)):
                    chunk = os.read(selected.fileobj.fileno(), 65536)
                    if not chunk:
                        selector.unregister(selected.fileobj)
                        continue
                    if selected.data == 'stderr':
                        stderr_bytes += len(chunk)
                        stderr_hash.update(chunk)
                        if stderr_bytes > MAX_DIAGNOSTICS:
                            raise ValueError('diagnostic output exceeds bound')
                        continue
                    if not accepted:
                        pending.extend(chunk)
                        if (len(pending) >= 16 and pending[:16] != HEADER_PREFIX):
                            raise ValueError('serial output is not an encrypted capture')
                        if len(pending) < 64:
                            continue
                        if pending[16:32] != stream:
                            raise ValueError('capture stream does not match recovery file')
                        accepted, chunk = True, bytes(pending)
                        pending.clear()
                    if count + len(chunk) > MAX_CAPTURE:
                        raise ValueError('capture output exceeds bound')
                    write_all(capture, chunk)
                    count += len(chunk)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            state['timed_out'] = True
            raise ValueError('runtime timeout')
        try:
            process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            state['timed_out'] = True
            raise ValueError('runtime timeout') from None
        if not accepted:
            raise ValueError('serial output lacks a complete encrypted header')
    except KeyboardInterrupt:
        state['cancelled'] = True
        error = 'runtime cancelled'
    except (OSError, ValueError) as exc:
        error = str(exc) if isinstance(exc, ValueError) else 'qemu or artifact io failed'
    finally:
        if process is not None:
            if process.poll() is None:
                process.kill()
            process.wait()
            process.stdout.close()
            process.stderr.close()
            state['returncode'] = process.returncode
            state['signal'] = -process.returncode if process.returncode < 0 else None
        state['stderr_bytes'] = stderr_bytes
        state['stderr_sha256'] = stderr_hash.hexdigest()
    return state, error


def prepare_input(stack, args, kernel_sha, initrd_sha):
    directory = canonical(args.input)
    private_directory(directory)
    recovery = canonical(args.input_key)
    if within(recovery, directory) or within(recovery, ROOT):
        raise ValueError('input recovery file must be outside recording and repository')
    manifest_fd = regular(stack, directory / 'manifest.json', private=True, limit=65536)
    try:
        manifest = json.loads(os.pread(manifest_fd, 65537, 0))
    except (ValueError, UnicodeError):
        raise ValueError('invalid input manifest') from None
    if not isinstance(manifest, dict):
        raise ValueError('invalid input manifest')
    capture = regular(stack, directory / 'capture.cr1', private=True, limit=MAX_CAPTURE)
    header = structure(capture)
    capture_sha = digest(capture)
    expected = {'format': 'daphnis-capture-session-v1', 'status': 'recorded',
                'kernel_sha256': kernel_sha, 'initrd_sha256': initrd_sha,
                'capture_sha256': capture_sha, 'stream_id': header[16:32].hex(),
                'program_revision': header[32:64].hex()}
    if any(manifest.get(name) != value for name, value in expected.items()):
        raise ValueError('input manifest or image identity mismatch')
    exit_state = manifest.get('exit')
    if (not isinstance(exit_state, dict) or exit_state.get('returncode') not in (33, 35)
            or exit_state.get('timed_out') is not False or exit_state.get('signal') is not None
            or exit_state.get('cancelled') is not False):
        raise ValueError('input manifest has no replayable runtime exit')
    expected_outcome = 'success' if exit_state['returncode'] == 33 else 'fault'
    if manifest.get('guest_outcome') != expected_outcome:
        raise ValueError('input manifest guest outcome mismatch')
    original_key, material = key_fd(stack, recovery)
    if material[40:] != header[16:32]:
        raise ValueError('input recovery stream identity mismatch')
    return directory, recovery, capture, original_key, material, capture_sha, header


def run(args):
    if os.name != 'posix' or not hasattr(os, 'O_NOFOLLOW') or not Path('/proc/self/fd').is_dir():
        raise ValueError('Unix host with /proc/self/fd is required')
    if not math.isfinite(args.timeout) or not 0 < args.timeout <= 3600:
        raise ValueError('timeout must be greater than zero and at most 3600 seconds')
    output, recovery = canonical(args.output), canonical(args.key)
    for path in (output, recovery):
        if within(path, ROOT):
            raise ValueError('session and recovery paths must be outside repository')
        private_directory(path.parent)
        absent(path)
    if within(output, recovery) or within(recovery, output):
        raise ValueError('session and recovery paths must be separate')
    kernel_path = canonical(args.kernel)
    initrd_path = canonical(args.initrd) if args.initrd else None
    if any(within(path, output) for path in (kernel_path, initrd_path) if path is not None):
        raise ValueError('images must stay outside recording')
    with ExitStack() as stack:
        kernel = regular(stack, kernel_path)
        initrd = regular(stack, initrd_path) if initrd_path else None
        validate_kernel(kernel)
        kernel_sha, initrd_sha = digest(kernel), digest(initrd) if initrd is not None else None
        input_capture = input_key = input_sha = input_header = original_material = None
        if args.command == 'replay':
            (source, source_key, input_capture, input_key, original_material,
             input_sha, input_header) = prepare_input(stack, args, kernel_sha, initrd_sha)
            if (within(output, source) or within(source, output) or recovery == source_key
                    or within(recovery, source)):
                raise ValueError('replay destinations must be separate from input session')
        tracked = {fd: fingerprint(fd) for fd in (kernel, initrd, input_capture, input_key)
                   if fd is not None}
        os.mkdir(output, 0o700)
        os.chmod(output, 0o700)
        directory = os.open(output, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        stack.callback(os.close, directory)
        manifest_fd = artifact(stack, directory, 'manifest.json')
        capture = artifact(stack, directory, 'capture.cr1')
        manifest = {'format': 'daphnis-capture-session-v1', 'mode': args.command,
                    'status': 'failed', 'guest_outcome': None, 'error': 'session setup incomplete',
                    'kernel_sha256': kernel_sha, 'initrd_sha256': initrd_sha,
                    'input_capture_sha256': input_sha, 'capture_sha256': digest(capture),
                    'stream_id': None, 'program_revision': None,
                    'authentication': 'not independently authenticated',
                    'input_authentication': 'required from kernel before execution' if input_sha else None,
                    'network': 'none' if args.command == 'replay' else args.network,
                    'rdrand_disabled': args.command == 'replay',
                    'timeout_seconds': args.timeout, 'exit': {'returncode': None, 'timed_out': False}}
        save_manifest(manifest_fd, manifest)
        os.fsync(directory)
        error = None
        try:
            keys.create_key(recovery)
            output_key, material = key_fd(stack, recovery)
            if original_material is not None and original_material[8:40] == material[8:40]:
                raise ValueError('fresh output key equals input key')
            tracked[output_key] = fingerprint(output_key)
            argv = command(args, kernel, initrd, output_key, input_capture, input_key)
            manifest['exit'], error = execute(argv, tracked, capture, material[40:], args.timeout)
            visible = os.pread(capture, 64, 0)
            if len(visible) == 64:
                manifest['stream_id'] = visible[16:32].hex()
                manifest['program_revision'] = visible[32:64].hex()
            if error:
                raise ValueError(error)
            if any(fingerprint(fd) != before for fd, before in tracked.items()):
                raise ValueError('a session input changed during execution')
            header = structure(capture)
            if input_header is not None and header[32:64] != input_header[32:64]:
                raise ValueError('replay output program identity mismatch')
            manifest['stream_id'], manifest['program_revision'] = header[16:32].hex(), header[32:64].hex()
            code = manifest['exit']['returncode']
            if code not in (33, 35):
                raise ValueError('runtime exit is not replayable')
            manifest['guest_outcome'] = 'success' if code == 33 else 'fault'
            if input_sha:
                manifest['input_authentication'] = 'kernel accepted before output'
            manifest['status'], manifest['error'] = 'recorded', None
        except (OSError, ValueError) as exc:
            error = str(exc) if isinstance(exc, ValueError) else 'session io or key creation failed'
            manifest['error'] = error
        finally:
            manifest['capture_sha256'] = digest(capture)
            os.fsync(capture)
            save_manifest(manifest_fd, manifest)
            os.fsync(directory)
        if manifest['status'] == 'recorded':
            return 'recorded' if manifest['guest_outcome'] == 'success' else 'recorded-fault'
        return 'failed'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for action in ('record', 'replay'):
        p = sub.add_parser(action)
        p.add_argument('--kernel', required=True)
        p.add_argument('--initrd')
        p.add_argument('--output', required=True, help='new session directory')
        p.add_argument('--key', required=True, help='new recovery file outside session and repository')
        p.add_argument('--qemu', default='qemu-system-x86_64')
        p.add_argument('--timeout', type=float, default=30)
        if action == 'record':
            p.add_argument('--network', choices=('none', 'user'), default='none')
        else:
            p.add_argument('--input', required=True, help='existing recorded session directory')
            p.add_argument('--input-key', required=True)
    args = parser.parse_args(argv)
    try:
        status = run(args)
    except KeyboardInterrupt:
        print('failed: session cancelled', file=sys.stderr)
        return 1
    except (OSError, ValueError, subprocess.SubprocessError):
        print('failed: session validation or io refused', file=sys.stderr)
        return 1
    print(status + ': ' + str(args.output))
    return 0 if status == 'recorded' else 1


if __name__ == '__main__':
    sys.exit(main())