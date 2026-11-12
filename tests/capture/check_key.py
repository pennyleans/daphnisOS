#!/usr/bin/env python3
"""Host recovery-key checks; all keys live in temporary directories."""
import importlib.util
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/capture-key.py"
spec = importlib.util.spec_from_file_location("capture_key", TOOL)
key = importlib.util.module_from_spec(spec)
if TOOL.exists():
    spec.loader.exec_module(key)


class KeyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="daphnis-key-test-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "recovery.key"

    def test_create_private_fresh_and_load(self):
        key.create_key(self.path)
        first = key.load_key(self.path)
        self.assertEqual(len(first), 56)
        self.assertEqual(first[:8], b"DAPHKEY1")
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
        second = self.path.with_name("second.key")
        key.create_key(second)
        self.assertNotEqual(first[8:40], key.load_key(second)[8:40])
        self.assertNotEqual(first[40:], key.load_key(second)[40:])

    def test_exclusive_create_preserves_existing(self):
        self.path.write_bytes(b"preserve")
        with self.assertRaises(OSError):
            key.create_key(self.path)
        self.assertEqual(self.path.read_bytes(), b"preserve")

    def test_reject_symlink_and_nonregular(self):
        target = self.path.with_name("target")
        target.write_bytes(b"preserve")
        self.path.symlink_to(target)
        for function in (key.create_key, key.load_key):
            with self.assertRaises((OSError, ValueError)):
                function(self.path)
        self.assertEqual(target.read_bytes(), b"preserve")
        self.path.unlink()
        self.path.mkdir()
        for function in (key.create_key, key.load_key):
            with self.assertRaises((OSError, ValueError)):
                function(self.path)
        self.path.rmdir()
        os.mkfifo(self.path, 0o600)
        with self.assertRaises((OSError, ValueError)):
            key.load_key(self.path)

    def test_reject_wrong_mode_without_chmod(self):
        key.create_key(self.path)
        for mode in (0o644, 0o660, 0o400, 0o700, 0o4600):
            self.path.chmod(mode)
            with self.assertRaises(ValueError):
                key.load_key(self.path)
            self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), mode)

    def test_reject_wrong_size_or_magic(self):
        for data in (b"", b"DAPHKEY1" + bytes(47), b"DAPHKEY1" + bytes(49),
                     b"BADMAGIC" + bytes(48)):
            self.path.write_bytes(data)
            self.path.chmod(0o600)
            with self.assertRaises(ValueError):
                key.load_key(self.path)

    def test_entropy_failure_cleans_up(self):
        with mock.patch.object(key.os, "urandom", side_effect=OSError("entropy unavailable")):
            with self.assertRaises(OSError):
                key.create_key(self.path)
        self.assertFalse(self.path.exists())

    def test_short_writes_complete(self):
        real_write = os.write
        def short_write(fd, data):
            return real_write(fd, data[:3])
        with mock.patch.object(key.os, "write", side_effect=short_write):
            key.create_key(self.path)
        self.assertEqual(len(key.load_key(self.path)), 56)

    def test_zero_write_and_sync_failure_clean_up(self):
        for name in ("write", "fsync"):
            patch = (mock.patch.object(key.os, name, return_value=0) if name == "write"
                     else mock.patch.object(key.os, name, side_effect=OSError("sync failed")))
            with patch:
                with self.assertRaises(OSError):
                    key.create_key(self.path)
            self.assertFalse(self.path.exists())

    def test_cleanup_preserves_replacement(self):
        def replace_then_fail(size):
            self.path.unlink()
            self.path.write_bytes(b"replacement")
            raise OSError("entropy unavailable")
        with mock.patch.object(key.os, "urandom", side_effect=replace_then_fail):
            with self.assertRaises(OSError):
                key.create_key(self.path)
        self.assertEqual(self.path.read_bytes(), b"replacement")

    def test_parent_symlink_resolves_to_chosen_directory(self):
        parent = self.path.with_name("alias")
        parent.symlink_to(Path(self.temp.name), target_is_directory=True)
        key.create_key(parent / "recovery.key")
        self.assertEqual(len(key.load_key(self.path)), 56)

    def test_cli_status_only_and_no_seed_option(self):
        result = subprocess.run([sys.executable, str(TOOL), "create", str(self.path)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, f"created {self.path}\n")
        data = key.load_key(self.path)
        self.assertNotIn(data[8:].hex(), result.stdout + result.stderr)
        result = subprocess.run([sys.executable, str(TOOL), "check", str(self.path)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, f"valid {self.path}\n")
        result = subprocess.run([sys.executable, str(TOOL), "create", "--seed", "1", str(self.path)],
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)

    def test_directory_sync_failure_cleans_up(self):
        real_sync = os.fsync
        def fail_directory(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                raise OSError("directory sync failed")
            real_sync(fd)
        with mock.patch.object(key.os, "fsync", side_effect=fail_directory):
            with self.assertRaises(OSError):
                key.create_key(self.path)
        self.assertFalse(self.path.exists())

    def test_partial_write_failure_cleans_up(self):
        real_write = os.write
        calls = 0
        def fail_after_write(fd, data):
            nonlocal calls
            calls += 1
            if calls > 1:
                raise OSError("write failed")
            return real_write(fd, data[:8])
        with mock.patch.object(key.os, "write", side_effect=fail_after_write):
            with self.assertRaises(OSError):
                key.create_key(self.path)
        self.assertFalse(self.path.exists())

    def test_restrictive_umask_still_creates_0600(self):
        old = os.umask(0o777)
        try:
            key.create_key(self.path)
        finally:
            os.umask(old)
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
    def test_unsupported_host_rejected(self):
        with mock.patch.object(key.os, "name", "nt"):
            with self.assertRaises(OSError):
                key.create_key(self.path)
        self.assertFalse(self.path.exists())


if __name__ == "__main__":
    unittest.main()