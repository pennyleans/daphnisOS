#!/usr/bin/env python3
"""tests/rs/guest/test_guest.py: hosted tests of tests/rs/guest/guest.py, the host side of the stage RS guest legs.
Every input is made here; nothing boots. python3 tests/rs/guest/test_guest.py (train.sh runs it first)."""
import contextlib
import hashlib
import io
import os
import struct
import sys
import tempfile
import unittest
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import guest  # noqa: E402


def quiet(f, *a):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        r = f(*a)
    return r, out.getvalue()


def fault_record(op, code=7):
    """A cint-core-1/fault/v2 record as rt/fault.c lays it out: the domain, the code, the operation, then more."""
    d = b"cint-core-1/fault/v2"
    o = op.encode()
    return struct.pack("<I", len(d)) + d + struct.pack("<H", code) + struct.pack("<I", len(o)) + o + b"\0" * 12


def ppm(w, h, px):
    return b"P6\n# a comment\n%d %d\n255\n" % (w, h) + px


class Tmp(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.d.cleanup()

    def path(self, name, data=None):
        p = os.path.join(self.d.name, name)
        if data is not None:
            with open(p, "wb" if isinstance(data, bytes) else "w") as f:
                f.write(data)
        return p


class Keys(unittest.TestCase):
    def test_a_line_with_its_shifted_bytes(self):
        self.assertEqual(guest.key_names("sh /rs/a.sh; exit $?"),
                         ["s", "h", "spc", "slash", "r", "s", "slash", "a", "dot", "s", "h", "semicolon", "spc",
                          "e", "x", "i", "t", "spc", "shift-4", "shift-slash"])

    def test_upper_case_quote_and_parentheses(self):
        self.assertEqual(guest.key_names("A'(*)="), ["shift-a", "apostrophe", "shift-9", "shift-8", "shift-0", "equal"])

    def test_a_byte_no_key_types(self):
        with self.assertRaises(ValueError):
            guest.key_names("\x01")


class Marks(unittest.TestCase):
    LINES = ["boot", "hdesk: login ada uid 1000", "hdesk: terminal 1 ended, status 0",
             "hdesk: pixel 1 pid 9 size 4x4"]

    def test_prefix_exact_regex_and_absent_in_order(self):
        marks = ["hdesk: login ada", "=hdesk: terminal 1 ended, status 0",
                 "~hdesk: pixel 1 pid [0-9]+ size [0-9]+x[0-9]+", "!sevenhorsesrun"]
        self.assertIsNone(guest.check_marks(self.LINES, marks))

    def test_a_dropped_key_fails_first(self):
        lines = self.LINES + ["daphnis: input dropped", "daphnis: shut down"]
        why = guest.check_marks(lines, ["hdesk: login ada", "no such mark"])
        self.assertIn("'daphnis: input dropped' at line 5", why)
        self.assertNotIn("no such mark", why)

    def test_exact_is_whole(self):
        self.assertIn("in order", guest.check_marks(self.LINES, ["=hdesk: terminal 1 ended, status"]))

    def test_regex_is_whole(self):
        self.assertIsNotNone(guest.check_marks(self.LINES, ["~hdesk: pixel 1 pid [0-9]+"]))

    def test_order(self):
        self.assertIsNotNone(guest.check_marks(self.LINES, ["hdesk: terminal 1 ended", "hdesk: login"]))

    def test_absent_anywhere(self):
        self.assertIn("found", guest.check_marks(self.LINES, ["!uid 1000"]))

    def test_absent_between_two_marks(self):
        lines = ["hdesk: about 1", "finder: dir |/| items 3", "hdesk: about closed", "finder: dir |/| items 3"]
        marks = ["hdesk: about 1", "-finder: dir", "=hdesk: about closed", "finder: dir"]
        self.assertIsNone(guest.check_marks(lines[:1] + lines[2:], marks))
        why = guest.check_marks(lines, ["hdesk: about 1", "-finder: dir", "=hdesk: about closed"])
        self.assertIn("before", why)
        self.assertIn("after the last mark", guest.check_marks(lines, ["=hdesk: about closed", "-finder: dir"]))
        self.assertIsNone(guest.check_marks(lines, ["finder: dir", "-hdesk: about 1", "=hdesk: about closed"]))

    def test_the_files_skip_comments_and_blank_lines(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "m")
            with open(p, "w") as f:
                f.write("# a comment\n\nboot\n=x\n")
            self.assertEqual(guest.read_marks(p), ["boot", "=x"])


class Pool(Tmp):
    def transcript(self, *records):
        lines = ["daphnis: boot"]
        for r in records:
            lines += ["fault: cint-core-1/fault/v2 %d bytes" % len(r), r.hex()]
        return self.path("t%d.txt" % len(os.listdir(self.d.name)), "\n".join(lines) + "\n")

    def test_the_operation_of_a_record(self):
        r = fault_record("host.resource")
        self.assertEqual(guest.record_operation(r.hex(), len(r)), "host.resource")
        self.assertIsNone(guest.record_operation(r.hex(), len(r) + 1))
        self.assertIsNone(guest.record_operation("zz", 1))

    def test_a_state_pool_fault_fails_with_its_banner(self):
        mk = self.path("Makefile", "RTDEF_user := -DRT_USER -DRT_STATE_POOL_BYTES=197632u -DRT_MAX_TASKS=1u\n")
        t = self.transcript(fault_record("host.resource"))
        r, out = quiet(guest.pool, ["-m", mk, t])
        self.assertEqual(r, 1)
        self.assertIn("STATE POOL FAULT", out)
        self.assertIn("RT_STATE_POOL_BYTES=197632", out)
        self.assertIn(t + " line 2", out)

    def test_another_fault_is_a_note(self):
        r, out = quiet(guest.pool, [self.transcript(fault_record("checked.add"))])
        self.assertEqual(r, 0)
        self.assertIn("operation checked.add", out)
        self.assertIn("PASS: 1 transcripts", out)

    def test_no_fault(self):
        self.assertEqual(quiet(guest.pool, [self.transcript(), self.transcript()])[0], 0)

    def test_a_missing_transcript_is_not_a_pool_fault(self):
        r, out = quiet(guest.pool, [self.transcript(), self.path("none") + ".txt"])
        self.assertEqual(r, 2)
        self.assertIn("no transcript", out)
        self.assertNotIn("STATE POOL FAULT", out)


class Vol(unittest.TestCase):
    STORE = ("daphnis-accounts 1 next=1003\n"
             "acct id=00 uid=1000 gid=1000 name=ada role=parent m=64 t=1 salt=00 ver=00 ceil=7\n"
             "acct id=01 uid=1001 gid=1001 name=sam role=parent m=65536 t=3 salt=01 ver=01 ceil=7\n")
    STAT = "Inode: 12   Type: directory    Mode:  0700   Flags: 0x0\nUser:  1003   Group:  1003   Size: 4096\n"

    def setUp(self):
        self.saved = guest.debugfs
        guest.debugfs = self.fake

    def tearDown(self):
        guest.debugfs = self.saved

    def fake(self, volume, request, err=False):
        if request == "cat /.daphnis/accounts":
            return self.STORE
        if request == "stat /eve":
            return self.STAT
        return "/x: File not found by ext2_lookup \n" if err else ""

    def run_vol(self, text):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "v")
            with open(p, "w") as f:
                f.write(text)
            return quiet(guest.vol, "vol.img", p)

    def test_store_rows_header_and_dirs(self):
        r, out = self.run_vol("# c\nstore sam role=parent uid=1001\nnostore ivy\nheader next=1003\n"
                              "dir /eve 0700 1003 1003\ngone /ivy\n")
        self.assertEqual(r, 0, out)
        self.assertIn("PASS: 5 expectations", out)

    def test_each_miss_is_said(self):
        r, out = self.run_vol("store sam role=child\nnostore sam\nheader next=1004\ndir /eve 0755 1003 1003\n"
                              "gone /eve\nstore ivy role=child\nwhat\n")
        self.assertEqual(r, 1)
        self.assertEqual(out.count("FAIL: "), 7, out)

    def test_an_unreadable_volume_fails_gone_and_nostore(self):
        saved, self.fake_text = self.fake, "debugfs: Bad magic number in super-block while opening filesystem\n"
        guest.debugfs = lambda volume, request, err=False: self.fake_text
        try:
            r, out = self.run_vol("gone /ivy\nnostore ivy\n")
        finally:
            guest.debugfs = saved
        self.assertEqual(r, 1)
        self.assertEqual(out.count("FAIL: "), 2, out)
        self.assertIn("no store on the volume", out)


class Pictures(Tmp):
    W, H = 64, 48

    def screen(self, fill, box=None, inside=b"", stripe=None):
        px = bytearray(fill * (self.W * self.H))
        if box:
            x0, y0, x1, y1 = box
            for y in range(y0, y1):
                for x in range(x0, x1):
                    c = inside
                    if stripe and (x + y) % 3 == 0:
                        c = stripe
                    px[3 * (y * self.W + x):3 * (y * self.W + x) + 3] = c
        return bytes(px)

    def test_read_ppm_and_crop(self):
        p = self.path("a.ppm", ppm(2, 2, b"\1\2\3\4\5\6\7\10\11\12\13\14"))
        img = guest.read_ppm(p)
        self.assertEqual(img[:2], (2, 2))
        self.assertEqual(guest.crop(img, 1, 0, 2, 2), b"\4\5\6\12\13\14")

    def test_the_prompt_box_follows_hdesk(self):
        lines = ["hdesk: screen 1920x1080 plane 1920x1048 (0)"]
        self.assertEqual(guest.prompt_box(lines), (762, 32 + (1048 - 300) // 2, 750 + 252, 32 + 374 + 150))
        lines = ["hdesk: screen 3840x2160 plane 3840x2096"]
        x0 = (3840 - 840) // 2
        self.assertEqual(guest.prompt_box(lines)[:3], (x0 + 24, 64 + (2096 - 600) // 2, x0 + 504))

    def test_card_one_picture_with_text_passes_and_a_change_fails(self):
        w, h = 300, 200
        t = self.path("t.txt", "hdesk: screen %dx%d plane %dx%d\n" % (w, h, w, h))
        x0, y0, x1, y1 = guest.prompt_box(guest.transcript_lines(t))
        y0 = max(y0, 0)

        def shot(name, title):
            px = bytearray(b"\x10\x20\x30" * (w * h))
            for y in range(max(y0, 0), min(y1, h)):
                for x in range(x0, x1):
                    c = b"\xf0\xf0\xf0"
                    if (x + y) % 5 == 0:
                        c = title
                    elif (x * y) % 7 == 0:
                        c = b"\x00\x00\x00"
                    px[3 * (y * w + x):3 * (y * w + x) + 3] = c
            return self.path(name, ppm(w, h, bytes(px)))

        a, b, c = shot("a.ppm", b"\xc0\x40\x10"), shot("b.ppm", b"\xc0\x40\x10"), shot("c.ppm", b"\x10\x40\xc0")
        r, out = quiet(guest.card, t, a, b)
        self.assertEqual(r, 0, out)
        r, out = quiet(guest.card, t, a, c)
        self.assertEqual(r, 1)
        self.assertIn("differ", out)

    def sheet_shots(self, w, h, frame, under_b=b"\x10\x20\x30", sheet_b=b"\xf0\xf0\xf0"):
        """Screendumps with window frame drawn under_* and kit/about.ci's sheet (360 x 287) centered on it."""
        x, y, fw, fh = frame
        cx, cy = x + fw // 2, y + fh // 2

        def shot(name, under, top):
            px = bytearray(b"\x00\x00\x00" * (w * h))
            for yy in range(y, y + fh):
                for xx in range(x, x + fw):
                    px[3 * (yy * w + xx):3 * (yy * w + xx) + 3] = under if (xx + yy) % 4 else b"\x80\x80\x80"
            for yy in range(cy - 143, cy + 144):
                for xx in range(cx - 180, cx + 180):
                    c = b"\x20\x60\xc0" if (xx * yy) % 9 == 0 else b"\x00\x00\x00" if (xx + yy) % 7 == 0 else top
                    px[3 * (yy * w + xx):3 * (yy * w + xx) + 3] = c
            return self.path(name, ppm(w, h, bytes(px)))

        return shot("a.ppm", b"\x10\x20\x30", b"\xf0\xf0\xf0"), shot("b.ppm", under_b, sheet_b)

    def sheet_transcript(self, w, h, frame):
        x, y, fw, fh = frame
        return self.path("t.txt", "hdesk: screen %dx%d plane %dx%d\n"
                         "hdesk: win 1 kind 1 desktop 1 mode 0 rank 2 frame 0,0 10x10 rects 0\n"
                         "hdesk: win 1 kind 1 desktop 1 mode 0 rank 2 frame %d,%d %dx%d rects 1 0,0,1x1\n"
                         "hdesk: about 1\n"
                         "hdesk: win 1 kind 1 desktop 1 mode 0 rank 2 frame 0,0 10x10 rects 0\n"
                         % (w, h, w, h, x, y, fw, fh))

    def test_the_sheet_is_one_picture_and_the_window_moves_around_it(self):
        w, h, frame = 640, 480, (40, 30, 560, 420)
        t = self.sheet_transcript(w, h, frame)
        self.assertEqual(guest.sheet_frame(guest.transcript_lines(t), "1"), frame)
        a, b = self.sheet_shots(w, h, frame, under_b=b"\x30\x20\x10")
        r, out = quiet(guest.sheet, t, "1", a, b, "moved")
        self.assertEqual(r, 0, out)
        self.assertIn("differs in", out)
        r, out = quiet(guest.sheet, t, "1", a, a, "moved")
        self.assertEqual(r, 1)
        self.assertIn("drew nothing", out)
        self.assertEqual(quiet(guest.sheet, t, "1", a, a)[0], 0)

    def test_a_sheet_drawn_over_fails(self):
        w, h, frame = 640, 480, (40, 30, 560, 420)
        t = self.sheet_transcript(w, h, frame)
        a, b = self.sheet_shots(w, h, frame, sheet_b=b"\xf0\x00\xf0")
        r, out = quiet(guest.sheet, t, "1", a, b)
        self.assertEqual(r, 1)
        self.assertIn("differs in", out)
        r, out = quiet(guest.sheet, self.path("u.txt", "hdesk: screen 640x480 plane 640x448\n"), "1", a, a)
        self.assertEqual(r, 1)
        self.assertIn("no frame of window 1", out)

    def test_card_with_no_text_fails(self):
        w, h = 300, 200
        t = self.path("t.txt", "hdesk: screen %dx%d plane %dx%d\n" % (w, h, w, h))
        a = self.path("a.ppm", ppm(w, h, b"\x10\x20\x30" * (w * h)))
        r, out = quiet(guest.card, t, a, a)
        self.assertEqual(r, 1)
        self.assertIn("1 colors", out)

    def test_color_and_differ_read_the_last_placed_pixel_window(self):
        t = self.path("t.txt", "hdesk: float 1 app 3 frame 4,4 10x10\nhdesk: pixel 1 pid 8 size 8x8\n"
                               "hdesk: pixel 1 ended\nhdesk: float 2 app -1 frame 20,10 30x20\n"
                               "hdesk: pixel 2 pid 9 size 28x16\n")
        a = self.path("a.ppm", ppm(self.W, self.H, self.screen(b"\0\0\0", (20, 10, 50, 30), b"\x2a\x6f\x97")))
        b = self.path("b.ppm", ppm(self.W, self.H, self.screen(b"\0\0\0", (20, 10, 50, 30), b"\x2a\x6f\x97",
                                                                b"\xff\xff\xff")))
        self.assertEqual(quiet(guest.color, t, a, "2a6f97")[0], 0)
        self.assertEqual(quiet(guest.color, t, a, "2a6f98")[0], 1)
        r, out = quiet(guest.differ, t, a, b)
        self.assertEqual(r, 0, out)
        self.assertIn("window 2's frame 20,10 30x20", out)
        self.assertEqual(quiet(guest.differ, t, a, a)[0], 1)
        none = self.path("n.txt", "hdesk: pixel 1 pid 8 size 8x8\n")
        self.assertEqual(quiet(guest.color, none, a, "2a6f97")[0], 1)


class Png(Tmp):
    def test_the_png_and_its_digest_line(self):
        out = self.path("p.png")
        guest.png(out, "5", "3", "2a6f97", "/rs/p.png")
        with open(out, "rb") as f:
            data = f.read()
        self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
        ihdr = struct.unpack(">IIBBBBB", data[16:29])
        self.assertEqual(ihdr, (5, 3, 8, 2, 0, 0, 0))
        n = struct.unpack(">I", data[33:37])[0]
        self.assertEqual(data[37:41], b"IDAT")
        self.assertEqual(zlib.decompress(data[41:41 + n]), (b"\0" + b"\x2a\x6f\x97" * 5) * 3)
        with open(out + ".want") as f:
            want = f.read()
        digest = hashlib.sha256(b"\x2a\x6f\x97\xff" * 15).hexdigest()
        self.assertEqual(want, "cview: /rs/p.png 5x3 rgba %s\n" % digest)


class Cpio(Tmp):
    def archive(self):
        body = guest.cpio_member(1, "bin", b"", 0o040755, 2) + guest.cpio_member(2, "bin/kern", b"KERN", 0o100755, 1)
        body += guest.cpio_member(3, "TRAILER!!!", b"", 0, 1)
        return self.path("in.cpio", body)

    def members(self, path):
        with open(path, "rb") as f:
            data = f.read()
        out, at = {}, 0
        while True:
            f = [int(data[at + 6 + 8 * i:at + 14 + 8 * i], 16) for i in range(13)]
            name = data[at + 110:at + 110 + f[11] - 1].decode()
            at += 110 + f[11]
            at += -at % 4
            out[name] = (f[1], data[at:at + f[6]])
            at += f[6] + (-f[6] % 4)
            if name == "TRAILER!!!":
                return out

    def test_members_before_the_trailer(self):
        note = self.path("note", b"a note\n")
        out = self.path("out.cpio")
        guest.cpio(self.archive(), out, ["rs/", "rs/it's $(kern true)=" + note])
        m = self.members(out)
        self.assertEqual(m["bin/kern"], (0o100755, b"KERN"))
        self.assertEqual(m["rs/it's $(kern true)"], (0o100755, b"a note\n"))
        self.assertEqual(m["rs"][0], 0o040755)
        self.assertEqual(list(m)[-1], "TRAILER!!!")

    def test_nothing_outside_rs_is_added(self):
        for m in ("bin/cview=" + self.path("n", b"x"), "bin/", "?bin/cview=" + self.path("n", b"x")):
            with self.assertRaisesRegex(ValueError, "under rs/ only"):
                guest.cpio(self.archive(), self.path("o"), [m])

    def test_a_name_twice_is_refused(self):
        n = self.path("n", b"x")
        with self.assertRaises(ValueError):
            guest.cpio(self.archive(), self.path("o"), ["rs/a=" + n, "rs/a=" + n])


class Ops(Tmp):
    TABLE = ("# c\n"
             "k | role ada sam parent | sevenhorsesrux | no | 1\n"
             "- | role ada sam parent | sevenhorsesrun | error store | 2\n"
             "k | add ada ivy child 14 | sevenhorsesrunivy-pass | ok | 0\n")

    def test_the_script(self):
        t = self.path("t.ops", self.TABLE)
        out = self.path("t.sh")
        guest.ops(t, out)
        with open(out) as f:
            lines = [ln for ln in f.read().split("\n") if ln and not ln.startswith("#")]
        self.assertEqual(lines[0], "printf '%s\\n%s' 'role ada sam parent' 'sevenhorsesrux' | kern authd > "
                                   "/tmp/rs.ans; s=$?")
        self.assertEqual(lines[1], 'echo "row 1 status $s: $(cat /tmp/rs.ans)" >> "$HOME/rs.log"')
        self.assertEqual(lines[2], "grep -qxF 'no' /tmp/rs.ans || exit 1")
        self.assertEqual(lines[3], "[ $s = 1 ] || exit 101")
        self.assertTrue(lines[4].endswith("| authd > /tmp/rs.ans; s=$?"))
        self.assertEqual(lines[-1], "exit 0")
        self.assertEqual(len(lines), 13)
        self.assertNotIn("sevenhorsesrun", " ".join(ln for ln in lines if "rs.log" in ln))

    def test_only_the_rows_of_one_kind_keep_their_numbers(self):
        t = self.path("t.ops", self.TABLE)
        out = self.path("t.sh")
        guest.ops(t, out, "-")
        with open(out) as f:
            lines = [ln for ln in f.read().split("\n") if ln and not ln.startswith("#")]
        self.assertEqual(lines[1:], ['echo "row 2 status $s: $(cat /tmp/rs.ans)" >> "$HOME/rs.log"',
                                     "grep -qxF 'error store' /tmp/rs.ans || exit 2", "[ $s = 2 ] || exit 102",
                                     "exit 0"])
        self.assertTrue(lines[0].endswith("| authd > /tmp/rs.ans; s=$?"))
        guest.ops(t, out, "k")
        with open(out) as f:
            k = f.read()
        self.assertNotIn("| authd >", k)
        self.assertIn("|| exit 1\n", k)
        self.assertIn("|| exit 3\n", k)
        self.assertNotIn("|| exit 2\n", k)

    def test_the_status_names_the_request(self):
        t = self.path("t.ops", self.TABLE)
        self.assertEqual(quiet(guest.status, t, "0"), (0, "every request answered as the table says\n"))
        r, out = quiet(guest.status, t, str(3 * 256))
        self.assertEqual(r, 1)
        self.assertIn("request 3 (kern add ada ivy child 14): the answer is not 'ok'", out)
        self.assertIn("request 2 (role ada sam parent): the status is not 2",
                      quiet(guest.status, t, str(102 * 256))[1])
        self.assertIn("signal 9", quiet(guest.status, t, "9")[1])
        self.assertIn("no step", quiet(guest.status, t, str(50 * 256))[1])

    def test_a_quote_or_a_short_line_is_refused(self):
        for bad in ("k | role a b parent | it's | ok | 0\n", "k | role a b parent | pw | ok\n", "x | r | p | ok | 0\n"):
            with self.assertRaises(ValueError):
                guest.read_ops(self.path("b.ops", bad))

    def test_the_tables_of_the_legs_read(self):
        here = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ops")
        for name in sorted(os.listdir(here)):
            rows = guest.read_ops(os.path.join(here, name))
            self.assertGreater(len(rows), 0, name)
            for via, req, pw, ans, st in rows:
                self.assertEqual(guest.key_names(pw) is not None, True)
                self.assertIn(st, ("0", "1", "2", "3"), name)


class Expected(unittest.TestCase):
    def test_every_marks_file_reads_and_every_regex_compiles(self):
        here = os.path.join(os.path.dirname(os.path.abspath(__file__)), "expected")
        n = 0
        for name in sorted(os.listdir(here)):
            if name.endswith(".marks"):
                for m in guest.read_marks(os.path.join(here, name)):
                    if m.startswith("~"):
                        guest.re.compile(m[1:])
                n += 1
        self.assertGreaterEqual(n, 8)


if __name__ == "__main__":
    unittest.main()
