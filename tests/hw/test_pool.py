"""Accounting is ownership reported by the guest, never a free-count allowance."""
import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
spec = importlib.util.spec_from_file_location("check_tiler", ROOT / "tools/check-tiler.py")
ct = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ct)


class Pool(unittest.TestCase):
    old = "daphnis: fs tables 19 frames held\ndaphnis: pool frames free 81 of 100\n"
    display = ("daphnis: display backing 2025 frames held\n"
               "daphnis: fs tables 19 frames held\ndaphnis: pool frames free 21454 of 23498\n")

    def test_existing_zero_display(self):
        self.assertEqual(ct.whole(self.old), [(81, 100, 19, 0)])

    def test_reported_display(self):
        self.assertEqual(ct.whole(self.display), [(21454, 23498, 19, 2025)])
        self.assertEqual(len(ct.whole(self.old + self.display)), 2)

    def test_unreported_or_leaked_frames(self):
        self.assertFalse(ct.whole(self.display.split("\n", 1)[1]))
        self.assertFalse(ct.whole(self.display.replace("21454", "21453")))
        self.assertFalse(ct.whole(self.old + self.display.replace("21454", "21453")))

    def test_malformed_anywhere(self):
        for bad in ("daphnis: display backing -1 frames held\n",
                    "daphnis: display backing 0 frames held\n",
                    "daphnis: display backing missing frames held\n",
                    "daphnis: fs tables -1 frames held\n",
                    "daphnis: pool frames free 100 of -1\n"):
            for text in (bad + self.old, self.old + bad, self.old + bad + self.display):
                with self.subTest(text=text):
                    self.assertFalse(ct.pools(text))
                    self.assertFalse(ct.whole(text))

    def test_duplicate_or_incomplete(self):
        display = self.display.splitlines(keepends=True)[0]
        fs = self.old.splitlines(keepends=True)[0]
        for text in (display, fs, display + display + self.old, fs + self.old,
                     self.old + display, display + "unrelated\n" + self.old,
                     self.old.splitlines(keepends=True)[1]):
            with self.subTest(text=text):
                self.assertFalse(ct.pools(text))
                self.assertFalse(ct.whole(text))

    def test_stable_hybrid_readiness(self):
        script = (ROOT / "check-hybrid.sh").read_text()
        self.assertNotIn('"hdesk: bar desktop 1 |Console| var ||"', script)
        # main's 11, the desk's 3, MS-7's 1 and MS-9a's 3 (gates 4, 8 and 7)
        self.assertEqual(script.count('"hdesk: bar desktop 1 |Console| var |/|"'), 18)
        self.assertNotIn("hdesk: bar desktop 1 |Console| var |/|", "hdesk: bar desktop 1 |Console| var |/notes|")
