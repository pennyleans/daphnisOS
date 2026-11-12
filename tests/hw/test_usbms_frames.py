"""HW-4m (kernel read P1 of PR 346): src/usbms.ci names only the two frames it holds for the boot in a TRB.

A bulk transfer that times out may be answered late; its bytes must land in a frame the pool never hands on. The
driver keeps io and data from init to the end of the boot, so: every xhci.bulk call names io or data, never a
parameter; the module never releases a frame; and the two frames are taken once, as one run.
"""
import pathlib
import re
import unittest

SRC = pathlib.Path(__file__).resolve().parents[2] / "src" / "usbms.ci"


def code(text):
    return "\n".join(line.split("//", 1)[0] for line in text.splitlines())


class UsbmsFrames(unittest.TestCase):
    def setUp(self):
        self.text = code(SRC.read_text(encoding="utf-8"))

    def test_every_transfer_names_a_driver_frame(self):
        calls = re.findall(r"xhci\.bulk(?:_wait)?\(\s*[^,]+,\s*([^,]+),", self.text)
        self.assertGreaterEqual(len(calls), 4)
        sites = [c.strip() for c in calls]
        # run() passes its addr through; every run() call must then name io or data
        self.assertEqual([s for s in sites if not re.fullmatch(r"(io|data)(\s*\+\s*\d+)?|addr", s)], [])
        runs = re.findall(r"(?<!I64 )\brun\(\s*[^,]+,\s*[^,]+,\s*[^,]+,\s*([^,]+),", self.text)
        self.assertGreaterEqual(len(runs), 5)
        self.assertEqual([r.strip() for r in runs if not re.fullmatch(r"(io|data)(\s*\+\s*\d+)?|0", r.strip())], [])

    def test_no_frame_is_released(self):
        self.assertNotIn("frames.release", self.text)
        self.assertNotIn("frames.unhold", self.text)

    def test_the_frames_are_taken_once(self):
        self.assertEqual(len(re.findall(r"frames\.alloc\(", self.text)), 1)
        self.assertRegex(self.text, r"if \(io == 0\) \{\s*I64 f = frames\.alloc\(2\);")


if __name__ == "__main__":
    unittest.main()
