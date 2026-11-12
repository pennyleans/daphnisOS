#!/usr/bin/env python3
"""tools/check-home.py: the home gate of FS-3 (docs/reviews/2026-11-07-macos-critic-review.md B-1; ruling RV-1 A,
FS-R1 A): the hybrid desk boots on the test volume, its shell starts in /home with the disk grant, and a file of more
than 1 MiB that ced wrote there is the same bytes on the next boot of the same volume.

tools/check-home.py --keys 1: what the gate types into the desk's first terminal on the first boot once the bar shows
  sh, as QEMU key names, one comma-separated list for tools/sendkeys.py: `seq 1 170000` into big.txt in the home, a
  copy of it in the ramfs (/big.txt, past the old 64 KiB cap of a created file: the chain), then `$EDITOR big.txt`.
tools/check-home.py --keys 2: once the bar shows ced: LONG lets ced read the file, KEPT is typed at its first line,
  Ctrl+S saves, Ctrl+Q leaves (ced clears the screen as it goes); then pwd, the sha256sum of /big.txt and big.txt,
  sync, exit.
tools/check-home.py --keys 3: the second boot of the same volume: pwd, wc -c big.txt, sha256sum big.txt, exit.

tools/check-home.py --check FIRST SECOND VOLUME: the checks of the two transcripts and the volume QEMU left:

  home     each boot says `daphnis: the desk starts in /home, the disk grant held` and its terminal's `pwd` is /home
  chain    the ramfs copy's sha256sum is the seq's (1,078,895 bytes in pool frames)
  saved    the first boot's sha256sum of big.txt after ced is KEPT then the seq's, BIG bytes in all
  kept     the second boot's wc -c and sha256sum of big.txt are the same numbers
  volume   debugfs dumps /big.txt from the volume as those bytes; e2fsck -fn finds the volume clean
  ends     both desks end with their shell's status 0, nothing dropped

One PASS or FAIL line a check; exits 1 on any FAIL."""
import hashlib
import importlib.util
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import guestlines  # noqa: E402
spec = importlib.util.spec_from_file_location("check_editor", os.path.join(HERE, "check-editor.py"))
editor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(editor)
editor.QEMU.update({b">": "shift-dot", b"-": "minus"})

SEQ = b"".join(b"%d\n" % i for i in range(1, 170001))
KEPT = b"kept on the home\n"
BIG = KEPT + SEQ
GRANT_LINE = "daphnis: the desk starts in /home, the disk grant held"
WAIT = editor.WAIT
LONG = ",".join([WAIT] * 6)          # about 18 s: ced reads and draws a 1 MiB file under TCG, or writes it


def keys(n):
    k = editor.qemu_keys
    if n == 1:
        return typed([b"seq 1 170000 > big.txt\r", b"cp big.txt /big.txt\r"]) + "," + ",".join(k([b"$EDITOR big.txt\r"]))
    if n == 2:
        return ",".join([LONG] + k([KEPT[:-1], b"\r"]) + [WAIT] + k([b"\x13"]) + [LONG] + k([b"\x11"]) + [LONG]) + "," + \
            typed([b"pwd\r", b"sha256sum /big.txt big.txt\r", b"sync\r", b"exit\r"], last_wait=False)
    return typed([b"pwd\r", b"wc -c big.txt\r", b"sha256sum big.txt\r", b"exit\r"], last_wait=False)


def typed(lines, last_wait=True):
    """Each command line, then WAIT, so a command's output and the next line never mix."""
    if not last_wait:
        assert lines and lines[-1] == b"exit\r"
    return ",".join(",".join(editor.qemu_keys([c]) + ([WAIT] if last_wait or i + 1 < len(lines) else []))
                    for i, c in enumerate(lines))


def rows(text):
    return [r.rstrip() for r in re.findall(r"^hdesk: term \d+ \|(.*)\|$", text, re.M)]


def main(argv):
    if argv[:1] == ["--keys"]:
        print(keys(int(argv[1])))
        return 0
    first, second, volume = argv[1:4]
    a = open(first, encoding="ascii", errors="replace").read()
    b = open(second, encoding="ascii", errors="replace").read()
    ra, rb = rows(a), rows(b)
    results = []

    def line(ok, label, detail=""):
        results.append(ok)
        print("%s  %s%s" % ("PASS" if ok else "FAIL", label, "" if ok else ": " + detail))

    seq_h, big_h = hashlib.sha256(SEQ).hexdigest(), hashlib.sha256(BIG).hexdigest()
    line(GRANT_LINE in guestlines.lines(a) and GRANT_LINE in guestlines.lines(b) and "/home" in ra and "/home" in rb,
         "home: both desks start in /home with the disk grant, and pwd says /home", "rows %r" % (ra[:4] + rb[:4]))
    line("%s  /big.txt" % seq_h in ra, "chain: the ramfs copy of the %d-byte seq is its bytes" % len(SEQ),
         "rows %r" % ra)
    line("%s  big.txt" % big_h in ra, "saved: after ced, big.txt is %r then the seq, %d bytes" % (KEPT, len(BIG)),
         "rows %r" % ra)
    line("%d big.txt" % len(BIG) in rb and "%s  big.txt" % big_h in rb,
         "kept: the next boot of the volume reads big.txt back, %d bytes, the same sha256" % len(BIG), "rows %r" % rb)
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "big.txt")
        subprocess.run(["debugfs", "-R", "dump /big.txt " + out, volume], capture_output=True)
        got = open(out, "rb").read() if os.path.exists(out) else b""
        fsck = subprocess.run(["e2fsck", "-fn", volume], capture_output=True, text=True)
    line(got == BIG and fsck.returncode == 0, "volume: debugfs dumps /big.txt as those bytes, e2fsck -fn clean",
         "dump %d bytes, e2fsck status %d" % (len(got), fsck.returncode))
    ends = all("hdesk: shell ended, status 0" in ls and "daphnis: input dropped" not in ls
               and ls[-1:] == ["daphnis: done"] for ls in (guestlines.lines(a), guestlines.lines(b)))
    line(ends, "ends: both desks end with their shell's status 0, nothing dropped")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
