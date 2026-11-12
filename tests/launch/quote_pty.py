#!/usr/bin/env python3
"""tests/launch/quote_pty.py [CISH]: AC-Q (docs/specs/2026-11-11-ac-q-launch-quoting.md) on a Linux host. For each
folder name below the desk's pinned-folder line is made as hdesk.ci pl_pinned makes it: `finder ` and the folder's
path through kit/shquote.ci quote (`quote` below is its twin; tests/launch/shquote_test.ci holds both to the same
bytes), refused as pl_run refuses it unless kit/shquote.ci plain holds (`plain` below), and typed as `exec LINE`
and Enter into CISH (O/ubin/cish) on a fresh pty, as the desk starts a terminal's shell.

Each case passes when the folder opens or nothing opens, and no second command runs:
  opens    the shell's own pid runs `finder` with exactly one argument, the folder's path
  nothing  the line is refused before any byte is typed (a newline in the name, or past launch.MAX)
  never    no name leaves the canary file behind (`touch CANARY` inside the name) and none runs `evil`

The names hold ; ' " $ ` & | < > ! # ~ * ? = ( { ^ % a newline, a space, a leading -, UTF-8, 200 bytes, and 240
(past launch.MAX). The same names typed unquoted, as pl_pinned typed them before AC-Q, are run too and printed as
notes, not judged. Prints one `ok` or `bad` line a check; exits 1 if any is bad. Linux only (cish is a static
Linux binary)."""
import os
import pty
import re
import select
import shutil
import signal
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
if len(sys.argv) < 2:
    sys.exit("usage: %s CISH (O/ubin/cish, built from source at HEAD by make)" % sys.argv[0])
CISH = os.path.abspath(sys.argv[1])
MAX = 255
BARE = set(b"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 _./-")
bad = 0


def line(ok, text):
    global bad
    print(("ok " if ok else "bad ") + text)
    if not ok:
        bad = 1


def quote(p, at, limit=MAX):
    """kit/shquote.ci quote's twin: the bytes it appends after `at` bytes, or None."""
    if not p or any(b < 32 or b == 127 for b in p):
        return None
    out = b"'" + (b"./" if p[:1] == b"-" else b"") + p.replace(b"'", b"'\\''") + b"'"
    return out if at + len(out) <= limit else None


def plain(cmd):
    """kit/shquote.ci plain's twin."""
    quoted = False
    i = 0
    while i < len(cmd):
        b = cmd[i]
        if b < 32 or b == 127:
            return False
        if quoted:
            quoted = b != 39
        elif b == 39:
            quoted = True
        elif b == 92:
            if i + 1 >= len(cmd) or cmd[i + 1] != 39:
                return False
            i += 1
        elif b not in BARE:
            return False
        i += 1
    return len(cmd) > 0 and not quoted


def run(d, typed):
    """typed into a new cish as the desk types it; the shell pid's report (finder's argv as hex) or None."""
    pid, fd = pty.fork()
    if pid == 0:
        os.chdir(d)
        env = {"PATH": os.path.join(d, "bin") + ":/usr/bin:/bin", "HOME": d, "TERM_PROGRAM": "daphnis"}
        os.execve(CISH, [CISH], env)
    os.write(fd, typed)
    out = b""
    got = None
    end = time.time() + 3.0
    while got is None and time.time() < end:
        r, _, _ = select.select([fd], [], [], 0.05)
        if r:
            try:
                out += os.read(fd, 4096)
            except OSError:
                break
        m = re.search(rb"finder pid (\d+) argc (\d+) arg ([0-9a-f]*)\r\n", out)
        if m and int(m.group(1)) == pid:
            got = (int(m.group(2)), bytes.fromhex(m.group(3).decode()))
    time.sleep(0.2)
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    os.waitpid(pid, 0)
    os.close(fd)
    return got


def main():
    d = tempfile.mkdtemp(prefix="quote-")
    os.mkdir(os.path.join(d, "bin"))
    with open(os.path.join(d, "bin", "finder"), "w") as f:
        f.write("#!/bin/sh\nprintf 'finder pid %s argc %s arg %s\\n' $$ $# \"$(printf '%s' \"$1\" | od -An -v -tx1 "
                "| tr -d ' \\n')\"\nread x\n")
    with open(os.path.join(d, "bin", "evil"), "w") as f:
        f.write("#!/bin/sh\ntouch %s/EVIL\nread x\n" % d)   # PATH holds the host's tools for finder's report
    for n in ("finder", "evil"):
        os.chmod(os.path.join(d, "bin", n), 0o755)
    canary = os.path.join(d, "CANARY").encode()
    names = [
        b"a;touch " + canary,
        b"a'; touch " + canary + b"; '",
        b'a"; touch ' + canary + b'; "',
        b"$(touch " + canary + b")",
        b"`touch " + canary + b"`",
        b"a&touch " + canary,
        b"a|touch " + canary,
        b"a <nope;exec evil",
        b"a >" + canary,
        b"a\ntouch " + canary,
        b"two words",
        b"-rf",
        b"x" * 200,
        b"y" * 240,
        b"it's",
        b"a!b #c ~d *e ?f =g",
        b"(touch " + canary + b")",
        b"{a,b} ^c %d",
        b"!touch " + canary,
        b"#x ~ * ?",
        b"\xc3\xa9t\xc3\xa9 \xe2\x80\x94 \xe6\x97\xa5",
    ]
    for name in names:
        folder = os.path.join(d.encode(), b"f", name.replace(b"/", b"_"))
        try:
            os.makedirs(folder, exist_ok=True)
        except OSError:
            continue
        label = repr(name[:24])[2:-1]
        q = quote(folder, len(b"finder "))
        cmd = None if q is None else b"finder " + q
        if cmd is None or not plain(cmd):
            line(b"\n" in name or len(folder) + 9 > MAX,
                 "%s: refused before any byte is typed" % label)
        else:
            got = run(d, b"exec " + cmd + b"\n")
            line(got == (1, folder), "%s: the shell's pid is finder with the folder as its one argument" % label)
        line(not os.path.exists(canary) and not os.path.exists(os.path.join(d, "EVIL")),
             "%s: no second command ran" % label)
        old = b"finder " + folder
        got = run(d, b"exec " + old + b"\n")
        ran = os.path.exists(canary) or os.path.exists(os.path.join(d, "EVIL"))
        print("note %s unquoted, as before AC-Q: %s%s" % (label, "finder %s args" % got[0] if got else "no finder",
                                                          ", a second command ran" if ran else ""))
        for p in (canary, os.path.join(d, "EVIL").encode()):
            if os.path.exists(p):
                os.unlink(p)
    shutil.rmtree(d, ignore_errors=True)
    return bad


if __name__ == "__main__":
    sys.exit(main())
