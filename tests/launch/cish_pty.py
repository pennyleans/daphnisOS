#!/usr/bin/env python3
"""tests/launch/cish_pty.py [CISH]: board 20261111T170652Z and DN-60 on a Linux host. The desk opens a terminal as
CISH (O/ubin/cish) on a pty, types an app as `exec CMD` and Enter and a command as CMD and Enter (user/ci/kit/launch.ci,
pinned by tests/launch/launch_test.ci; `typed` below is its twin), and frees the window record when reap of the
shell's pid returns. Each case starts cish the same way, as the session leader on a fresh pty, types the bytes and
waits on that pid. `app` stands for an app of kit/apps.ci, or for a command where the case says so.

  exec     an app runs as the shell's own process ($$ is the shell's pid), and the pid ends when the app ends,
           with its status: the desk's reap returns and the window goes
  command  a command's bytes, as fcd3c001 typed every launch: the program is a child and the shell outlives it,
           so what it printed stays (DN-60); for an app this was the defect, a Console left at a prompt
  sigterm  the desk's close (stop(pid, SIGTERM)) ends an exec'd program and so the pid
  ctrl-c   Ctrl-C ends an exec'd program: cish gives back the SIGINT it ignores (fails on fcd3c001's cish)
  missing  a program not found: cish says `NAME: not found` and the pid ends with 127, which launch.failed reads
  bg exec  `exec PROG &` in the interactive shell: the `&` child keeps SIGINT ignored through its exec, so a
           Ctrl-C for a foreground program does not end it (review on PR 300; cish has no job control)
  console  no bytes: the shell stays until `exit`

Prints one `ok` or `bad` line a check; exits 1 if any is bad. Linux only (cish is a static Linux binary)."""
import os
import pty
import re
import select
import signal
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
if len(sys.argv) < 2:
    sys.exit("usage: %s CISH (O/ubin/cish, built from source at HEAD by make)" % sys.argv[0])
CISH = os.path.abspath(sys.argv[1])
bad = 0


def line(ok, text):
    global bad
    print(("ok " if ok else "bad ") + text)
    if not ok:
        bad = 1


def typed(cmd, app=True):
    """kit/launch.ci typed's twin: none for Console; `exec `, the command and Enter for an app of kit/apps.ci; the
    command and Enter for a command (DN-60)."""
    if cmd in (b"", b"cish"):
        return b""
    return (b"exec " if app else b"") + cmd + b"\n"


class Term:
    """cish on a fresh pty, the session leader with the pty as its terminal, as the desk's pty_spawn starts /sh."""

    def __init__(self, path):
        self.out = b""
        pid, fd = pty.fork()
        if pid == 0:
            os.execve(CISH, [CISH], {"PATH": path, "HOME": path, "TERM_PROGRAM": "daphnis"})
        self.pid, self.fd = pid, fd
        self.status = None

    def read(self, secs):
        end = time.time() + secs
        while time.time() < end:
            r, _, _ = select.select([self.fd], [], [], 0.05)
            if r:
                try:
                    got = os.read(self.fd, 4096)
                except OSError:
                    return
                if not got:
                    return
                self.out += got

    def app_pid(self, secs=5.0):
        """The pid app printed on its first line (`app pid N`, ONLCR's CR LF after it), or None."""
        end = time.time() + secs
        m = None
        while m is None and time.time() < end:
            m = re.search(rb"app pid (\d+)\r\n", self.out)
            if m is None:
                self.read(0.1)
        return int(m.group(1)) if m else None

    def type(self, b):
        os.write(self.fd, b)

    def reap(self, secs):
        """The desk's reap(pid, nohang) until it returns or secs pass; the wait status, or None while it runs."""
        end = time.time() + secs
        while time.time() < end:
            got, st = os.waitpid(self.pid, os.WNOHANG)
            if got == self.pid:
                self.status = st
                return st
            self.read(0.05)
        return None

    def end(self):
        if self.status is None:
            try:
                os.kill(self.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            os.waitpid(self.pid, 0)
        os.close(self.fd)


def main():
    d = tempfile.mkdtemp(prefix="launch-")
    app = os.path.join(d, "app")
    with open(app, "w") as f:
        f.write("#!/bin/sh\necho \"app pid $$\"\nread x\nexit 7\n")
    os.chmod(app, 0o755)

    t = Term(d)
    t.read(0.5)
    t.type(typed(b"app"))
    up = t.app_pid() == t.pid
    t.type(b"q\n")
    st = t.reap(5)
    line(up and st is not None and os.WIFEXITED(st) and os.WEXITSTATUS(st) == 7,
         "exec: `exec app` runs app as the shell's own process (pid %d) and the pid ends with it, status 7 (%s)"
         % (t.pid, st))
    t.end()

    t = Term(d)
    t.read(0.5)
    t.type(typed(b"app", app=False))
    ap = t.app_pid()
    child = ap is not None and ap != t.pid
    t.type(b"q\n")
    st = t.reap(1.5)
    line(child and st is None and b"app pid %d" % ap in t.out,
         "command: `app` typed as is runs as a child; the shell outlives it and what it printed stays (DN-60; "
         "for an app, fcd3c001's defect)")
    t.end()

    t = Term(d)
    t.read(0.5)
    t.type(typed(b"app"))
    up = t.app_pid() == t.pid
    os.kill(t.pid, signal.SIGTERM)
    st = t.reap(5)
    line(up and st is not None and os.WIFSIGNALED(st) and os.WTERMSIG(st) == signal.SIGTERM,
         "sigterm: the desk's close (SIGTERM to the pid) ends an exec'd app (%s)" % st)
    t.end()

    t = Term(d)
    t.read(0.5)
    t.type(typed(b"app"))
    up = t.app_pid() == t.pid
    t.read(0.3)
    t.type(b"\x03")
    st = t.reap(5)
    line(up and st is not None and os.WIFSIGNALED(st) and os.WTERMSIG(st) == signal.SIGINT,
         "ctrl-c: Ctrl-C ends an exec'd app, SIGINT given back by cish (%s)" % st)
    t.end()

    bg = os.path.join(d, "bgapp")
    with open(bg, "w") as f:
        f.write("#!/bin/sh\necho \"bg pid $$\"\nexec /bin/sleep 30\n")
    os.chmod(bg, 0o755)
    t = Term(d)
    t.read(0.5)
    t.type(b"exec bgapp &\n")
    m = None
    end = time.time() + 5
    while m is None and time.time() < end:
        m = re.search(rb"bg pid (\d+)\r\n", t.out)
        t.read(0.1)
    bpid = int(m.group(1)) if m else None
    t.type(b"app\n")                                  # a foreground program in cooked mode
    up = t.app_pid() is not None
    t.read(0.3)
    t.type(b"\x03")                                   # SIGINT to the shell's group: the foreground app ends
    t.read(1.0)
    state = None
    if bpid is not None:
        try:
            with open("/proc/%d/status" % bpid) as f:
                state = [x for x in f.read().splitlines() if x.startswith("State:")][0].split()[1]
        except OSError:
            state = "gone"
    line(bpid is not None and up and state in ("S", "R"),
         "bg exec: `exec bgapp &` keeps SIGINT ignored: a Ctrl-C for the foreground app leaves it running (%s)"
         % state)
    if bpid is not None:
        try:
            os.kill(bpid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    t.end()

    t = Term(d)
    t.read(0.5)
    t.type(typed(b"nosuchapp"))
    st = t.reap(5)
    t.read(0.2)
    said = b"nosuchapp: not found" in t.out
    line(said and st is not None and os.WIFEXITED(st) and os.WEXITSTATUS(st) == 127,
         "missing: `exec nosuchapp` says `nosuchapp: not found` and the pid ends with 127, launch.failed's (%s)" % st)
    t.end()

    t = Term(d)
    t.read(0.5)
    t.type(typed(b""))
    alive = t.reap(1.5) is None
    t.type(b"exit\n")
    st = t.reap(5)
    line(alive and st is not None and os.WIFEXITED(st) and os.WEXITSTATUS(st) == 0,
         "console: no bytes typed, the shell stays until `exit` (%s)" % st)
    t.end()
    return bad


if __name__ == "__main__":
    sys.exit(main())
# SPDX-License-Identifier: Apache-2.0
