#!/usr/bin/env python3
"""tools/check-untitled.py CED: RUN-8's grant for an Untitled ced (tools/build-ced.sh's main), on a Linux pty. ced runs
with no FILE; the keys `hi`, Ctrl+S, a name, Enter and Ctrl+Q save the buffer under /arg1. Checks: started in a
directory outside HOME, the file lands in the home and never in that directory (a Console in / holds no rights on
/); started under the home or in it, the file lands there; with no HOME, no file is written anywhere. One PASS or
FAIL line per case; exit status 1 if any failed."""
import os
import pty
import select
import shutil
import sys
import tempfile
import time


def run(ced, cwd, env, name):
    pid, fd = pty.fork()
    if pid == 0:
        os.chdir(cwd)
        os.execve(ced, [ced], env)

    def pump(t):
        end = time.monotonic() + t
        while time.monotonic() < end:
            if select.select([fd], [], [], 0.05)[0]:
                try:
                    os.read(fd, 65536)
                except OSError:
                    return

    pump(1.0)
    for k in (b"hi", b"\x13", name.encode(), b"\r", b"\x11"):
        os.write(fd, k)
        pump(0.6)
    for _ in range(20):                # a save refused leaves the buffer dirty: Ctrl+Q does not end it
        if os.waitpid(pid, os.WNOHANG)[0]:
            break
        time.sleep(0.1)
    else:
        os.kill(pid, 9)
        os.waitpid(pid, 0)
    os.close(fd)


def files(root):
    return sorted(os.path.relpath(os.path.join(d, f), root) for d, _, fs in os.walk(root) for f in fs)


def main():
    ced = os.path.abspath(sys.argv[1])
    root = tempfile.mkdtemp()
    home = os.path.join(root, "home", "sam")
    out = os.path.join(root, "outside")
    os.makedirs(os.path.join(home, "notes"))
    os.makedirs(out)
    base = {"PATH": "/bin", "TERM": "xterm"}
    cases = (("started outside the home: the home, not there", out, dict(base, HOME=home), "o.txt",
              ["home/sam/o.txt"]),
             ("started under the home: there", os.path.join(home, "notes"), dict(base, HOME=home), "u.txt",
              ["home/sam/notes/u.txt", "home/sam/o.txt"]),
             ("started in the home: the home", home, dict(base, HOME=home), "h.txt",
              ["home/sam/h.txt", "home/sam/notes/u.txt", "home/sam/o.txt"]),
             ("no HOME: nothing written", out, base, "n.txt",
              ["home/sam/h.txt", "home/sam/notes/u.txt", "home/sam/o.txt"]))
    bad = 0
    for what, cwd, env, name, want in cases:
        run(ced, cwd, env, name)
        got = files(root)
        ok = got == want
        bad += not ok
        print(("PASS " if ok else "FAIL ") + what + ("" if ok else ": " + " ".join(got)))
    shutil.rmtree(root)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
# SPDX-License-Identifier: Apache-2.0
