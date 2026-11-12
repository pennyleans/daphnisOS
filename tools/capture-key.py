#!/usr/bin/env python3
"""Create and validate separate Unix-host capture recovery-key files."""
import argparse
import errno
import os
from pathlib import Path
import stat
import sys

MAGIC = b"DAPHKEY1"
KEY_FILE_SIZE = 56


def _parent(path):
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        raise OSError("private key files require a Unix host")
    path = Path(path).absolute()
    parent = path.parent.resolve(strict=True)
    fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    return fd, path.name


def _validate_stat(info):
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("key file must be regular")
    if stat.S_IMODE(info.st_mode) != 0o600:
        raise ValueError("key file must have mode 0600")
    if info.st_size != KEY_FILE_SIZE:
        raise ValueError("key file must contain exactly 56 bytes")


def _same_file(parent_fd, name, identity):
    try:
        current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return False
    return (current.st_dev, current.st_ino) == identity


def load_key(path):
    """Return the validated 56-byte payload without changing existing permissions."""
    parent_fd, name = _parent(path)
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                     dir_fd=parent_fd)
        try:
            before = os.fstat(fd)
            _validate_stat(before)
            payload = bytearray()
            while len(payload) <= KEY_FILE_SIZE:
                chunk = os.read(fd, KEY_FILE_SIZE + 1 - len(payload))
                if not chunk:
                    break
                payload.extend(chunk)
            after = os.fstat(fd)
            _validate_stat(after)
            if (len(payload) != KEY_FILE_SIZE or payload[:8] != MAGIC
                    or before.st_mtime_ns != after.st_mtime_ns
                    or before.st_ctime_ns != after.st_ctime_ns
                    or not _same_file(parent_fd, name, (before.st_dev, before.st_ino))):
                raise ValueError("invalid or changed key file")
            return bytes(payload)
        finally:
            os.close(fd)
    finally:
        os.close(parent_fd)


def create_key(path):
    """Exclusively create a fresh private key file and sync it and its directory."""
    parent_fd, name = _parent(path)
    fd = None
    identity = None
    try:
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=parent_fd)
        info = os.fstat(fd)
        identity = (info.st_dev, info.st_ino)
        os.fchmod(fd, 0o600)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("key file must be regular")
        payload = MAGIC + os.urandom(32) + os.urandom(16)
        if len(payload) != KEY_FILE_SIZE:
            raise OSError("entropy source returned wrong length")
        remaining = memoryview(payload)
        while remaining:
            written = os.write(fd, remaining)
            if written <= 0:
                raise OSError(errno.EIO, "key file write failed")
            remaining = remaining[written:]
        _validate_stat(os.fstat(fd))
        os.fsync(fd)
        if not _same_file(parent_fd, name, identity):
            raise OSError("key file path changed")
        os.fsync(parent_fd)
    except BaseException:
        if identity is not None and _same_file(parent_fd, name, identity):
            os.unlink(name, dir_fd=parent_fd)
            try:
                os.fsync(parent_fd)
            except OSError:
                pass
        raise
    finally:
        if fd is not None:
            os.close(fd)
        os.close(parent_fd)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("create", "check"):
        sub.add_parser(command).add_argument("path")
    args = parser.parse_args(argv)
    try:
        if args.command == "create":
            create_key(args.path)
            status = "created"
        else:
            load_key(args.path)
            status = "valid"
    except (OSError, ValueError):
        print(f"error {args.path}", file=sys.stderr)
        return 1
    print(f"{status} {args.path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())