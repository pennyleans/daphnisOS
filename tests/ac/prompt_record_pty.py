#!/usr/bin/env python3
"""tests/ac/prompt_record_pty.py [CISH]: why the desk records an app only for a plain line (AC-Tw,
docs/specs/2026-11-11-ac-t-prompt-title.md section 5), with CISH (O/ubin/cish) on a pty of a Linux host, started as the
desk starts a terminal's shell. The desk types `exec `, the line and Enter; the window's first process is the
shell's pid, and the approval prompt's title names the app the desk recorded for it.

  hazard   `exec app <nope;exec OTHER`: the redirection fails, an interactive cish goes on, and OTHER is the pid.
           kit/prompttitle.ci `plain` refuses this line, so the window records no app. What cish does with the
           line is printed as a note and is not judged: a cish that ends there instead is no failure
  quoted   the same bytes as one single-quoted word, as the desk writes a path: app is the pid
  quote    a quote in the word written '\\'' : app is the pid
  bare     words of letters, digits and _ . / - : app is the pid

`plain` below is kit/prompttitle.ci plain's twin (tests/ac/prompttitle_test.ci pins the original, every byte).
Prints one `ok` or `bad` line a check; exits 1 if any is bad. Linux only (cish is a static Linux binary)."""
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
SAFE = set(b"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 _./-")
bad = 0


def line(ok, text):
    global bad
    print(("ok " if ok else "bad ") + text)
    if not ok:
        bad = 1


def plain(cmd):
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
        elif b not in SAFE:
            return False
        i += 1
    return len(cmd) > 0 and not quoted


def first_process(d, cmd):
    """Types `exec cmd` into a new cish; the name (app, other) the shell's own pid then prints, or None."""
    pid, fd = pty.fork()
    if pid == 0:
        os.chdir(d)
        os.execve(CISH, [CISH], {"PATH": d, "HOME": d, "TERM_PROGRAM": "daphnis"})
    os.write(fd, b"exec " + cmd + b"\n")
    out = b""
    who = None
    end = time.time() + 5.0
    while who is None and time.time() < end:
        r, _, _ = select.select([fd], [], [], 0.05)
        if r:
            try:
                out += os.read(fd, 4096)
            except OSError:
                break
        m = re.search(rb"i am (\w+) pid (\d+)\r\n", out)
        if m and int(m.group(2)) == pid:
            who = m.group(1).decode()
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    os.waitpid(pid, 0)
    os.close(fd)
    return who


def main():
    d = tempfile.mkdtemp(prefix="prompt-record-")
    for name in ("app", "other"):
        p = os.path.join(d, name)
        with open(p, "w") as f:
            f.write("#!/bin/sh\necho \"i am %s pid $$\"\nread x\n" % name)
        os.chmod(p, 0o755)
    other = os.path.join(d, "other").encode()
    tail = b"<nope;exec " + other
    cases = [
        ("hazard", b"app " + tail, "other"),
        ("quoted", b"app '" + tail + b"'", "app"),
        ("quote", b"app 'a'\\''" + tail + b"'", "app"),
        ("bare", b"app /a_b/c-d.e", "app"),
    ]
    for name, cmd, want in cases:
        got = first_process(d, cmd)
        if want == "app":
            line(got == "app", "%s: the shell's pid runs app (%s)" % (name, got))
        else:
            print("note %s: the shell's pid runs %s" % (name, got))
        line(plain(cmd) == (want == "app"), "%s: plain is %s" % (name, want == "app"))
    shutil.rmtree(d, ignore_errors=True)
    return bad


if __name__ == "__main__":
    sys.exit(main())
