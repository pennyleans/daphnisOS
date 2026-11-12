"""Ruling A must never drop bytes after the first kernel line."""
import importlib.util
import pathlib
import unittest

spec = importlib.util.spec_from_file_location("fw_split", pathlib.Path(__file__).parents[2] / "tools/fw-split.py")
fw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fw)


class FirmwareSplit(unittest.TestCase):
    def test_prefix(self):
        golden = b"hello from Daphnis\n"
        prefix = b"\x1b[2Jfirmware\r\nGRUB\r"
        self.assertEqual(fw.split(prefix + golden, golden), (prefix, golden))

    def test_every_later_byte_survives(self):
        golden = b"Daphnis F: ring 3\nline\n"
        later = golden + b"unexpected firmware\r\n"
        self.assertEqual(fw.split(b"firmware" + later, golden), (b"firmware", later))
        self.assertNotEqual(fw.split(later, golden)[1], golden)

    def test_first_occurrence(self):
        golden = b"hello\n"
        self.assertEqual(fw.split(golden + golden, golden), (b"", golden + golden))

    def test_no_partial_marker(self):
        with self.assertRaises(ValueError):
            fw.split(b"hello\r\n", b"hello\n")
        with self.assertRaises(ValueError):
            fw.split(b"anything", b"")

    def test_comparison_rejects_changed_suffix(self):
        golden = b"Daphnis F: ring 3\nline\n"
        for changed in (golden[:-1], golden.replace(b"line", b"Line"), golden + b"extra", golden + golden):
            self.assertNotEqual(fw.split(b"firmware\r" + changed, golden)[1], golden)


if __name__ == "__main__":
    unittest.main()
