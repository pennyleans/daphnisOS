#!/usr/bin/env python3
"""tools/check-editor.py CED DIR: the Linux half of the editor gate (docs/specs/2026-11-06-e-editor.md section 2,
gate 3). Starts CED on a pty of 80 x 24 with DIR/notes.txt as its one argument, writes KEYS one key a write (as the
desks write a key, E-3), waiting after each until CED has answered and then written nothing for IDLE seconds, and
checks:

  ends     CED ends with status 0 after Ctrl+Q
  file     DIR/notes.txt is NOTES
  screen   what CED wrote ends by leaving the screen as it found it (bracketed paste off, plain, cleared, home)

Writes DIR/screen.bin, every byte CED wrote. One PASS or FAIL line a check; exits 1 on any FAIL.

tools/check-editor.py --keys: the same keys as QEMU key names, one comma-separated list for tools/sendkeys.py, after
`$EDITOR notes.txt` (the desk shell's EDITOR is /bin/ced, E-6, BU-2c); WAIT (monitor commands, 300 ms each) lets ced start
and end before the next key.

tools/check-editor.py --boot TRANSCRIPT: the Daphnis half (E-5) on a boot of the desk flavor at 512 MiB with the pool
from the memory map, where --keys, then `cat notes.txt` and `exit`, were typed into the desk's shell:

  rows     after ced the terminal holds the shell's `cat notes.txt` of NOTES, then `exit`: the file is Linux's

The monitor types a word as one key a write with no wait on ced, so ced reads the keys in as many reads, and draws as
many frames, as the host's load allows: the desk's count and digest of the terminal's bytes (`tiler: term bytes`) are
not the run's to pin, and check-editor.sh compares the transcript without that line (E-5b). The bytes ced writes are
pinned on Linux, where each key waits for ced's answer.
  ends     the shell and the tiler end with status 0, nothing dropped, and the pool whole but for notes.txt, a file
           made since the image was read, which holds its chain: one map frame and a data frame a page (src/fs.ci, FS-3)"""
import re
import fcntl
import os
import pty
import select
import struct
import sys
import termios
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import guestlines  # noqa: E402

IDLE = 0.3
SHIFT_LEFT = b"\x1b[1;2D"
KEYS = [b"first line", b"\r", b"second line",          # two lines
        b"\x17", b"\x17",                              # Ctrl+W twice: wrap on, then off
        SHIFT_LEFT, SHIFT_LEFT, SHIFT_LEFT, SHIFT_LEFT,  # a selection: the last four bytes
        b"LINE",                                       # typed over it
        b"\x13", b"\x11"]                              # Ctrl+S, Ctrl+Q
NOTES = b"first line\nsecond LINE\n"
LEAVE = b"\x1b[?2004l\x1b[0m\x1b[2J\x1b[H"
QEMU = {b"\r": "ret", b" ": "spc", b".": "dot", b"/": "slash", b"\x17": "ctrl-w", b"\x13": "ctrl-s",
        b"\x11": "ctrl-q", b"$": "shift-4", SHIFT_LEFT: "shift-left"}
WAIT = ",".join(["info version"] * 10)
PAGE, MAP_SLOTS = 4096, 511   # src/fs.ci (FS-3): a created file holds a chain of map frames, each naming 511 pages


def pools(text):
    """Each pool line as (free, frames, the filesystem tables' frames, named on the line before it; FS-4)."""
    return [(int(f), int(n), int(t)) for t, f, n in re.findall(
        r"^daphnis: fs tables (\d+) frames held\ndaphnis: pool frames free (\d+) of (\d+)$", text, re.M)]


def whole(text):
    """The pool lines whose pool is whole but for the filesystem's tables."""
    return [p for p in pools(text) if p[0] + p[2] == p[1]]


def chain_frames(size):
    """The frames a created file of SIZE bytes holds, written front to back: its pages and the maps naming them."""
    pages = (size + PAGE - 1) // PAGE
    return pages + (pages + MAP_SLOTS - 1) // MAP_SLOTS


def qemu_keys(keys):
    """KEYS as QEMU key names: a letter, shift-letter for a capital, or QEMU's name for the rest."""
    out = []
    for k in keys:
        if k in QEMU:
            out.append(QEMU[k])
        else:
            out += [("shift-" + chr(c).lower()) if chr(c).isupper() else QEMU.get(bytes((c,)), chr(c)) for c in k]
    return out


def sequence():
    """What the gate types after the desk's first prompt: ced, the keys, then cat and exit."""
    return ",".join(qemu_keys([b"$EDITOR notes.txt\r"]) + [WAIT] + qemu_keys(KEYS[:-1]) + [WAIT] +
                    qemu_keys(KEYS[-1:]) + [WAIT] + qemu_keys([b"cat notes.txt\r"]) + [WAIT] +
                    qemu_keys([b"exit\r"]))


def boot(path):
    text = open(path, encoding="ascii", errors="replace").read()
    lines = guestlines.lines(text)
    results = []

    def line(ok, label, detail=""):
        results.append(ok)
        print("%s  %s%s" % ("PASS" if ok else "FAIL", label, "" if ok else ": " + detail))

    rows = re.findall(r"^tiler: term \d+ \|(.*)\|$", text, re.M)
    want = ["# cat notes.txt"] + NOTES.decode("ascii").splitlines() + ["# exit"]
    line(rows[:len(want)] == want and not any(rows[len(want):]), "rows: after ced the terminal holds `cat notes.txt` "
         "of %r, then `exit`" % NOTES, "rows %r" % rows[:6])
    pool = pools(text)
    line("tiler: desk shell ended, status 0" in lines and lines.count("daphnis: exit 0") == 1 and
         len(pool) == 1 and pool[0][0] + pool[0][2] == pool[0][1] - chain_frames(len(NOTES)) and "daphnis: input dropped" not in lines
         and lines[-1:] == ["daphnis: done"], "ends: the shell and the tiler end with status 0, nothing dropped, the "
         "pool whole but for notes.txt's %d frames" % chain_frames(len(NOTES)), "see %s" % path)
    return 0 if all(results) else 1


def run(ced, path):
    pid, fd = pty.fork()
    if pid == 0:   # the size is set before ced runs: set after, a loaded host let ced draw at 0 x 0, then again
        fcntl.ioctl(0, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 80, 0, 0))
        os.execv(ced, [ced, path])
    out = bytearray()

    def pump(limit):
        """Read until CED has answered (its first byte) and then written nothing for IDLE seconds: ced draws one
        frame a read, so a key written before the last frame was read would join it in one read and one frame."""
        end = time.monotonic() + limit
        quiet = end
        while time.monotonic() < min(end, quiet):
            r, _, _ = select.select([fd], [], [], 0.02)
            if r:
                try:
                    got = os.read(fd, 65536)
                except OSError:
                    return False
                if not got:
                    return False
                out.extend(got)
                quiet = time.monotonic() + IDLE
        return True

    pump(5)
    for k in KEYS:
        os.write(fd, k)
        if not pump(5):
            break
    pump(2)
    _, status = os.waitpid(pid, 0)
    os.close(fd)
    return status, bytes(out)


def main(argv):
    if argv[:1] == ["--keys"]:
        print(sequence())
        return 0
    if argv[:1] == ["--boot"]:
        return boot(argv[1])
    ced, d = argv
    path = os.path.join(d, "notes.txt")
    if os.path.exists(path):
        os.remove(path)
    status, out = run(ced, path)
    with open(os.path.join(d, "screen.bin"), "wb") as f:
        f.write(out)
    results = []

    def line(ok, label, detail=""):
        results.append(ok)
        print("%s  %s%s" % ("PASS" if ok else "FAIL", label, "" if ok else ": " + detail))

    line(os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0, "ends: ced ends with status 0 after Ctrl+Q",
         "wait status %d" % status)
    got = open(path, "rb").read() if os.path.exists(path) else None
    line(got == NOTES, "file: notes.txt is %r" % NOTES, "it is %r" % got)
    line(out.endswith(LEAVE), "screen: ced leaves the terminal as it found it (%d bytes written)" % len(out),
         "the last bytes are %r" % out[-40:])
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
