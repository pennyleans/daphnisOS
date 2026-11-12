"""Tests for tools/netjournal.py rng (RS-CLK2): only the kernel's own `clk` and `wal` records, whole lines in order,
enter a journal; a program's text that ends like one does not.
  python3 -B -m unittest tests/tools/test_netjournal.py"""
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
TOOL = os.path.join(ROOT, "tools", "netjournal.py")


def run(transcript):
    with tempfile.TemporaryDirectory() as d:
        t, out = os.path.join(d, "t.txt"), os.path.join(d, "j")
        with open(t, "wb") as f:
            f.write(transcript)
        p = subprocess.run([sys.executable, "-B", TOOL, "rng", t, out], capture_output=True)
        body = open(out, "rb").read() if p.returncode == 0 else None
        return p.returncode, body, p.stderr


class Rng(unittest.TestCase):
    def test_records_in_order(self):
        rc, body, _ = run(b"daphnis: rng rdrand, live\nrtc 1800000000\nwal 1 1\nrng 4 0a0b0c0d\nwal 3 3\n"
                          b"clk 1900000000\nwal 1 7\n")
        self.assertEqual(rc, 0)
        self.assertEqual(body, b"rtc 1800000000\nwal 1 1\nrng 4 0a0b0c0d\nwal 3 3\nclk 1900000000\nwal 1 7\n")

    def test_a_programs_text_is_no_record(self):
        rc, body, _ = run(b"rtc 1800000000\nmrng: wal 9 9\necho clk 5\nmrng says wal 2 2\nwal 1 1\n")
        self.assertEqual(rc, 0)
        self.assertEqual(body, b"rtc 1800000000\nwal 1 1\n")

    def test_a_forged_line_out_of_order_is_refused(self):
        for t in (b"rtc 5\nwal 3 3\nwal 2 4\n", b"rtc 5\nwal 3 3\nwal 4 3\n", b"rtc 5\nwal 3 3\nwal 3 4\n"):
            rc, _, err = run(t)
            self.assertEqual(rc, 1, t)
            self.assertIn(b"out of order", err)

    def test_wal_before_rtc_is_refused(self):
        rc, _, err = run(b"wal 3 1\nrtc 5\n")
        self.assertEqual(rc, 1)
        self.assertIn(b"before the `rtc` line", err)

    def test_the_committed_journals_pass_unchanged(self):
        for name in ("a3.journal", "a4-rng.journal"):
            src = open(os.path.join(ROOT, "tests", "net", name), "rb").read()
            rc, body, _ = run(src)
            self.assertEqual((rc, body), (0, src), name)


if __name__ == "__main__":
    unittest.main()
# SPDX-License-Identifier: Apache-2.0
