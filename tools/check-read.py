#!/usr/bin/env python3
"""tools/check-read.py: Read on the desk (RS-RE, docs/specs/2026-11-11-rs-rel-s1-units.md; frames 40 and 41).

  check-read.py BIN TREE   runs BIN (cless) on a pty of 80 x 24 with TERM_PROGRAM=daphnis over TREE/lines.txt,
                           types the keys below, reads the screen back through a small terminal model and checks each
                           step against what this file works out from the fixture's bytes alone:

  declare   the first bytes are the title (OSC 2, the file's name), About, Settings dimmed (plan A), then the four
            rows of frame 41 in the AM-4 form, Copy dimmed (`d`)
  page      no status line: the 24 rows hold lines 1 to 24 in columns 1 to 79, nothing drawn reversed; column 80
            holds the place bar (U+2590 in SGR 30) on the rows of the bytes shown
  find      Ctrl+F then `line 5`: the bottom row is `Find: line 5` with `1 of N` at the right in SGR 90, N the
            pattern's starts in the file; the text shrinks to 23 rows; the current match is SGR 33 reversed and
            every other match on the screen SGR 33 on 40
  next      Enter, then a chosen Find Next row (`ESC ] 7770 ; chose ; 7 BEL`), then Ctrl+G: 2, 3 and 4 of N, the
            screen brought to each
  around    from the last match, Ctrl+G goes back to 1 of N
  arrows    22 Down arrows in one write (66 bytes, so cless's 64-byte read ends at the 22nd arrow's ESC): the find
            line stays open, as a held arrow leaves it
  close     Esc: the find line gone, the text on 24 rows again, nothing lit
  open      Ctrl+O, a name that does not open: `Couldn't open NAME.`; a key; Ctrl+O then odd.txt: the title is
            odd.txt and the rows are declared again
  fifo      Ctrl+O, a FIFO with no writer: `Couldn't open NAME.` at once, not a wait on the open
  live      Ctrl+O, a text past 4 MiB whose one `zzz` is past its first 4 MiB; Ctrl+F then `zzz`: the screen stays
            and no count shows (typing looks 4 MiB on); Enter: the match on the screen and `1 of 1`
  long      Ctrl+O, one line of 100,000 bytes: the bar is the rows on the screen, not the whole line; at the top
            row 1, after G row 24
  huge      Ctrl+O, one line of 4 MiB, each row of it numbered; then G, b, space, k, j and g: every frame is the right
            rows, drawn within FRAME_S of its key (a frame walks the bytes it shows, not the line), the open and G
            within WALK_S (each walks the line once); after G the bar is the last row
  cut       Ctrl+O, 4,000 lines of 50 bytes; the file cut to its first 20 lines under cless (logrotate's
            copytruncate), then G: within CUT_S the 20 lines on rows 1 to 20, the rest empty, no bar; then g still
            answers (a walk that met the new end used to spin, and cless never read a key again); then the same file
            whole again, Ctrl+F, the file cut, and `z`: the find line answers within CUT_S (a find walks the old
            size until the next frame, so each byte past the new end must cost no read); then for `n` and for `N`:
            100 lines and a hole to CUT_BIG, Ctrl+F, `0005`, Esc, the file cut to its first 20 lines, and the key:
            the find line answers within CUT_S (the search stops where it finds the new end; it stepped over the old
            size a byte at a time, about 21 ns a byte, 5.7 s on 256 MiB), then g still answers
  quit      q: status 0, the terminal's mode as before
  pipe      cless with descriptor 0 a pipe: the first OSC is an empty title (`2;`), then About

Exit status 0 when every step holds, 1 with the failing step on stderr."""
import codecs
import fcntl
import os
import pty
import re
import select
import shutil
import signal
import struct
import sys
import tempfile
import termios
import time

ROWS, COLS = 24, 80
FRAME_S = 3.0   # huge: the most a frame of one 4 MiB line may take from its key, hosted (spec section 2a, gate 4a);
                # about 0.05 s measured, and the walk from the line's start that it replaced took 6 to 30 s a key
WALK_S = 10.0   # and the open and G, which walk the whole line once (its rows; G also finds the end)
CUT_S = 3.0     # cut: G's frame after the file was cut short
CUT_BIG = 1 << 30   # cut n and N: the file's size before the cut, a hole past its 100 lines (no disk); far past what
                    # the old step a byte at a time walks in CUT_S on any machine
ESC = "\x1b"


class Screen:
    """The subset of a terminal cless writes: CUP, EL, SGR (0, 7, 30-37, 40-47, 90-97), DECTCEM, OSC to BEL, UTF-8."""

    def __init__(self):
        self.cells = [[(" ", "") for _ in range(COLS)] for _ in range(ROWS)]
        self.r = self.c = 0
        self.pen = ""
        self.shown = True
        self.oscs = []
        self.dec = codecs.getincrementaldecoder("utf-8")("ignore")
        self.rest = ""

    def feed(self, data):
        """Draws data on what is there; a sequence cut at the end of data waits for the next, so a sequence split
        across reads is read whole."""
        s = self.rest + self.dec.decode(data)
        i = 0
        while i < len(s):
            ch = s[i]
            if ch == ESC and s[i + 1:i + 2] == "]":
                j = s.find("\x07", i)
                if j < 0:
                    break
                self.oscs.append(s[i + 2:j])
                i = j + 1
                continue
            if ch == ESC:
                m = re.match(r"\x1b\[([?]?)([0-9;]*)([A-Za-z])", s[i:])
                if not m:
                    break
                mark, args, f = m.group(1), m.group(2), m.group(3)
                ps = [int(x) if x else 0 for x in args.split(";")] if args else []
                if f == "H":
                    self.r = max(ps[0] if ps else 1, 1) - 1
                    self.c = max(ps[1] if len(ps) > 1 else 1, 1) - 1
                elif f == "K":
                    for x in range(self.c, COLS):
                        self.cells[self.r][x] = (" ", "")
                elif f == "m":
                    for p in ps or [0]:
                        if p == 0:
                            self.pen = ""
                        else:
                            self.pen = (self.pen + ";" + str(p)).lstrip(";")
                elif f in "hl" and mark == "?" and ps == [25]:
                    self.shown = f == "h"
                i += m.end()
                continue
            if ch >= " ":
                if self.c < COLS:
                    self.cells[self.r][self.c] = (ch, self.pen)
                    self.c += 1
            i += 1
        self.rest = s[i:]

    def text(self, r):
        return "".join(ch for ch, _ in self.cells[r])

    def pens(self, r):
        return [p for _, p in self.cells[r]]


def run(binary, tree):
    data = open(os.path.join(tree, "lines.txt"), "rb").read()
    lines = data.decode().split("\n")[:-1]
    total = len(data)
    pid, m = pty.fork()
    if pid == 0:
        os.chdir(tree)
        env = {"TERM_PROGRAM": "daphnis", "PATH": "/bin"}
        os.execve(binary, [binary, "lines.txt"], env)
    fcntl.ioctl(m, termios.TIOCSWINSZ, struct.pack("HHHH", ROWS, COLS, 0, 0))
    scr = Screen()

    def drain(t):
        while True:
            r, _, _ = select.select([m], [], [], t)
            if not r:
                return
            try:
                d = os.read(m, 65536)
            except OSError:
                return
            if not d:
                return
            scr.feed(d)

    def typed(b):
        os.write(m, b)
        drain(0.3)

    def until(ok, limit):
        end = time.monotonic() + limit
        while not ok() and time.monotonic() < end:
            drain(0.05)
        return ok()

    fails = []

    def need(step, ok, why):
        if not ok:
            fails.append("%s: %s" % (step, why))

    before = termios.tcgetattr(m)
    drain(0.5)

    # declare
    want = ["2;lines.txt", "7770;about;Read;0.1.0;A pager for text files: page and search with the keys of less.",
            "7770;settings;1;d", "7770;item;15;0;Open;Ctrl+O;g", "7770;item;6;0;Find;Ctrl+F;g", "7770;item;7;0;Find Next;Ctrl+G;",
            "7770;item;3;0;Copy;Ctrl+C;gd"]
    need("declare", scr.oscs[:7] == want, "OSCs %r" % scr.oscs[:7])

    # page: lines 1 to 24 in columns 1 to 79, no reverse, the bar in column 80
    def thumb(n, a, b, total=total):
        if a == 0 and b == total:
            return set()
        r0 = n * a // total
        rn = max((n * (b - a) + total - 1) // total, 1)
        if r0 + rn > n:
            r0 = max(n - rn, 0)
        return set(range(r0, r0 + rn))

    def start(k):
        return sum(len(x) + 1 for x in lines[:k])

    def page(step, top, n):
        for r in range(n):
            want_t = lines[top + r] if top + r < len(lines) else ""
            need(step, scr.text(r)[:79].rstrip() == want_t, "row %d %r, want %r" % (r, scr.text(r)[:79], want_t))
        b = start(top + n) if top + n < len(lines) else total
        bar = thumb(n, start(top), b)
        got = {r for r in range(n) if scr.cells[r][79] == ("▐", "30")}
        need(step, got == bar, "bar rows %s, want %s" % (sorted(got), sorted(bar)))

    page("page", 0, 24)
    need("page", all("7" not in p.split(";") for r in range(24) for p in scr.pens(r)), "reverse video")

    # find: every start of the pattern in the file, in order
    pat = "line 5"
    starts = [i for i in range(total) if data[i:i + len(pat)] == pat.encode()]
    n = len(starts)

    def find_row(step, k):
        row = scr.text(23)
        count = "%d of %d" % (k, n)
        need(step, row.startswith("Find: " + pat), "bottom row %r" % row)
        at = 79 - len(count)
        need(step, row[at:79] == count and row[79:].strip() == "", "count %r, want %r" % (row, count))
        need(step, all(p == "90" for p in scr.pens(23)[at:79]), "count's pen %r" % scr.pens(23)[at:79])
        cur = starts[k - 1]
        line = data[:cur].count(b"\n")
        col = cur - start(line)
        on = [r for r in range(23) if scr.text(r)[:79].rstrip() == lines[line]]
        need(step, len(on) == 1, "line %d of the match not on the screen" % (line + 1))
        if on:
            r = on[0]
            cur_pens = scr.pens(r)[col:col + len(pat)]
            need(step, all(p == "33;7" for p in cur_pens), "current match pen %r" % cur_pens)
        for r in range(23):
            t = scr.text(r)[:79]
            inside = {x for s0 in range(79) if t[s0:s0 + len(pat)] == pat for x in range(s0, s0 + len(pat))}
            lit = {x for x in range(79) if scr.pens(r)[x] in ("33;40", "33;7")}
            need(step, lit == inside, "row %d lit %s, matches %s" % (r, sorted(lit), sorted(inside)))

    typed(b"\x06")
    need("find", scr.text(23).startswith("Find: ") and scr.shown, "find line %r" % scr.text(23))
    typed(pat.encode())
    find_row("find", 1)

    typed(b"\r")
    find_row("next enter", 2)
    typed(b"\x1b]7770;chose;7\x07")
    find_row("next chosen row", 3)
    typed(b"\x07")
    find_row("next ctrl+g", 4)
    for _ in range(n - 4):
        typed(b"\x07")
    find_row("last", n)
    typed(b"\x07")
    find_row("around", 1)

    typed(b"\x1b[B" * 22)
    need("arrows", scr.text(23).startswith("Find: " + pat),
         "row 24 %r: the cut ESC closed the find line" % scr.text(23))

    typed(b"\x1b")
    need("close", scr.text(23)[:79].rstrip() != "" and not scr.text(23).startswith("Find:"), "row 24 %r" % scr.text(23))
    need("close", all(p in ("", "30") for r in range(24) for p in scr.pens(r)), "a lit cell after Esc")

    # open
    k = len(scr.oscs)
    typed(b"\x0f")
    typed(b"nothing.txt\r")
    need("open fail", scr.text(23).rstrip() == "Couldn't open nothing.txt.", "row 24 %r" % scr.text(23))
    typed(b"j")
    typed(b"\x0fodd.txt\r")
    need("open", scr.oscs[k:k + 7] == ["2;odd.txt"] + want[1:], "OSCs %r" % scr.oscs[k:])
    odd = open(os.path.join(tree, "odd.txt"), "rb").read().split(b"\n")
    shown = ""
    for ch in odd[0].decode("latin-1"):
        shown += " " * (8 - len(shown) % 8) if ch == "\t" else ch if " " <= ch < "\x7f" else "?"
    shown = shown[:79].rstrip()
    need("open", scr.text(0)[:79].rstrip() == shown, "row 1 %r, want %r" % (scr.text(0), shown))

    # fifo: refused at once; a blocking open would never return, so the run ends there
    tmp = tempfile.mkdtemp()
    fifo = os.path.join(tmp, "fifo")
    os.mkfifo(fifo)
    typed(b"\x0f" + fifo.encode() + b"\r")
    drain(0.5)
    if scr.text(23).rstrip() != "Couldn't open %s." % fifo:
        need("fifo", False, "row 24 %r: the open waits on the FIFO" % scr.text(23))
        os.kill(pid, signal.SIGKILL)
        os.waitpid(pid, 0)
        shutil.rmtree(tmp)
        for f in fails:
            print("check-read.py: " + f, file=sys.stderr)
        return 1
    typed(b"j")

    # live: 4 MiB is cless's LIVE; the match lies past it, so only Enter reaches it
    x = b"x" * 63 + b"\n"
    past = os.path.join(tmp, "past.txt")
    with open(past, "wb") as f:
        f.write(x * (4194304 // len(x) + 8192) + b"zzz\n")
    typed(b"\x0f" + past.encode() + b"\r")
    typed(b"\x06zzz")
    zzz = lambda: [r for r in range(23) if scr.text(r)[:79].rstrip() == "zzz"]
    need("live", until(lambda: scr.text(23).rstrip() == "Find: zzz", 10), "row 24 %r" % scr.text(23))
    need("live", zzz() == [] and scr.text(0)[:79].rstrip() == "x" * 63, "typing searched past 4 MiB")
    typed(b"\r")
    need("live", until(lambda: len(zzz()) == 1 and scr.text(23)[:79].rstrip().endswith("1 of 1"), 20),
         "after Enter: rows of `zzz` %s, row 24 %r" % (zzz(), scr.text(23)))
    typed(b"\x1b")

    # long: rows of 79 bytes; the bar is the bytes of the 24 rows on the screen
    size = 100000
    big = os.path.join(tmp, "long.txt")
    with open(big, "wb") as f:
        f.write(b"a" * size + b"\n")
    nrows = (size + 78) // 79

    def long_page(step, s):
        for r in range(24):
            want_t = "a" * max(min(79, size - (s + r) * 79), 0)
            need(step, scr.text(r)[:79].rstrip() == want_t, "row %d %r" % (r, scr.text(r)[:79]))
        b = size + 1 if s + 24 >= nrows else (s + 24) * 79
        bar = thumb(24, s * 79, b, size + 1)
        got = {r for r in range(24) if scr.cells[r][79] == ("▐", "30")}
        need(step, got == bar, "bar rows %s, want %s" % (sorted(got), sorted(bar)))

    typed(b"\x0f" + big.encode() + b"\r")
    drain(1.0)
    long_page("long top", 0)
    typed(b"G")
    drain(1.0)
    long_page("long end", nrows - 24)

    # huge: one line of 4 MiB, row r of it `r` in 7 digits and 72 dots, so each frame shows which rows it holds
    hrows = 4194304 // 79 + 1
    huge = os.path.join(tmp, "huge.txt")
    with open(huge, "wb") as f:
        f.write(b"".join(b"%07d" % r + b"." * 72 for r in range(hrows)) + b"\n")

    def huge_rows(s):
        return all(scr.text(r)[:79] == "%07d" % (s + r) + "." * 72 for r in range(24))

    def frame(step, keys, s, bound=FRAME_S):
        t0 = time.monotonic()
        os.write(m, keys)
        ok = until(lambda: huge_rows(s), 30)
        took = time.monotonic() - t0
        need(step, ok, "rows %r to %r, want %07d on" % (scr.text(0)[:7], scr.text(23)[:7], s))
        need(step, took <= bound, "the frame took %.2f s, more than %.1f s" % (took, bound))

    frame("huge open", b"\x0f" + huge.encode() + b"\r", 0, WALK_S)
    frame("huge G", b"G", hrows - 24, WALK_S)
    got = {r for r in range(24) if scr.cells[r][79] == ("▐", "30")}
    need("huge G", got == {23}, "bar rows %s, want [23]" % sorted(got))
    frame("huge b", b"b", hrows - 48)
    frame("huge space", b" ", hrows - 24)
    frame("huge k", b"k", hrows - 25)
    frame("huge j", b"j", hrows - 24)
    frame("huge g", b"g", 0)

    # cut: the file cut short while cless has it; G finds the new end and draws its last rows
    cut = os.path.join(tmp, "cut.txt")
    clines = ["%04d " % i + "c" * 44 for i in range(4000)]
    with open(cut, "wb") as f:
        f.write("".join(x + "\n" for x in clines).encode())
    typed(b"\x0f" + cut.encode() + b"\r")
    need("cut open", until(lambda: scr.text(0)[:79].rstrip() == clines[0], 5), "row 1 %r" % scr.text(0))
    os.truncate(cut, 20 * 50)
    os.write(m, b"G")
    if not until(lambda: all(scr.text(r)[:79].rstrip() == (clines[r] if r < 20 else "") for r in range(24)), CUT_S):
        need("cut G", False, "rows %r .. %r: no frame of the 20 lines left" % (scr.text(0)[:12], scr.text(23)[:12]))
        os.kill(pid, signal.SIGKILL)
        os.waitpid(pid, 0)
        shutil.rmtree(tmp)
        for f in fails:
            print("check-read.py: " + f, file=sys.stderr)
        return 1
    got = {r for r in range(24) if scr.cells[r][79] == ("▐", "30")}
    need("cut G", got == set(), "bar rows %s with the whole text shown" % sorted(got))
    typed(b"j")
    typed(b"g")
    need("cut g", scr.text(0)[:79].rstrip() == clines[0], "row 1 %r" % scr.text(0))
    with open(cut, "wb") as f:
        f.write("".join(x + "\n" for x in clines).encode())
    typed(b"\x0f" + cut.encode() + b"\r")
    need("cut find", until(lambda: scr.text(0)[:79].rstrip() == clines[0], 5), "row 1 %r" % scr.text(0))
    typed(b"\x06")
    os.truncate(cut, 20 * 50)
    t0 = time.monotonic()
    os.write(m, b"z")
    if not until(lambda: scr.text(23).startswith("Find: z"), CUT_S):
        need("cut find", False, "row 24 %r %.1f s after the first key" % (scr.text(23), time.monotonic() - t0))
        os.kill(pid, signal.SIGKILL)
        os.waitpid(pid, 0)
        shutil.rmtree(tmp)
        for f in fails:
            print("check-read.py: " + f, file=sys.stderr)
        return 1
    typed(b"\x1b")
    # cut n and N: a match found and the find line closed, the file cut, then the key: the search meets the new end
    # and stops there
    for k in ("n", "N"):
        step = "cut " + k
        with open(cut, "wb") as f:
            f.write("".join(x + "\n" for x in clines[:100]).encode())
        os.truncate(cut, CUT_BIG)
        typed(b"\x0f" + cut.encode() + b"\r")
        need(step, until(lambda: scr.text(0)[:79].rstrip() == clines[0], 5), "row 1 %r" % scr.text(0))
        typed(b"\x060005")
        typed(b"\x1b")
        need(step, not scr.text(23).startswith("Find"), "row 24 %r: the find line did not close" % scr.text(23))
        os.truncate(cut, 20 * 50)
        t0 = time.monotonic()
        os.write(m, k.encode())
        if not until(lambda: scr.text(23).startswith("Find: 0005"), CUT_S):
            need(step, False, "row 24 %r %.1f s after the key" % (scr.text(23), time.monotonic() - t0))
            os.kill(pid, signal.SIGKILL)
            os.waitpid(pid, 0)
            shutil.rmtree(tmp)
            for f in fails:
                print("check-read.py: " + f, file=sys.stderr)
            return 1
        typed(b"\x1b")
        typed(b"g")
        need(step, scr.text(0)[:79].rstrip() == clines[0], "row 1 %r after g" % scr.text(0))

    shutil.rmtree(tmp)

    typed(b"q")
    _, st = os.waitpid(pid, 0)
    drain(0.1)
    after = termios.tcgetattr(m)
    need("quit", st == 0 and before == after, "status %d, mode %s" % (st, "kept" if before == after else "changed"))

    # pipe: descriptor 0 is no file, so the title is empty and the bar draws Read's own name
    r, w = os.pipe()
    pid, m = pty.fork()
    if pid == 0:
        os.dup2(r, 0)
        os.close(r)
        os.close(w)
        os.chdir(tree)
        os.execve(binary, [binary], {"TERM_PROGRAM": "daphnis", "PATH": "/bin"})
    os.close(r)
    fcntl.ioctl(m, termios.TIOCSWINSZ, struct.pack("HHHH", ROWS, COLS, 0, 0))
    os.write(w, data)
    os.close(w)
    scr = Screen()
    need("pipe", until(lambda: len(scr.oscs) >= 2, 5) and scr.oscs[:2] == ["2;", want[1]], "OSCs %r" % scr.oscs[:2])
    typed(b"q")
    _, st = os.waitpid(pid, 0)
    need("pipe", st == 0, "status %d" % st)
    for f in fails:
        print("check-read.py: " + f, file=sys.stderr)
    return 1 if fails else 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    sys.exit(run(os.path.abspath(sys.argv[1]), sys.argv[2]))
