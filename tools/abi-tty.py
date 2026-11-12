#!/usr/bin/env python3
"""tools/abi-tty.py KEYS ARGV...: runs ARGV on a pty of 80 x 24 with TERM=vt100 (unit BU-4d,
docs/specs/2026-11-07-bu4-toolchain.md section 5), so tools/abi-gap.sh can trace a full-screen program that needs a
terminal: ARGV is the tracer, then the program and its arguments. A second and a half after the start it writes KEYS (C
escapes allowed, one byte every 100 ms) and waits up to 10 s for the end. Prints only `status N` (or `signal N`, or
`timeout`): what the screen showed depends on time and chance, the end does not."""
import os
import pty
import select
import signal
import struct
import sys
import termios
import time
import fcntl


def main():
    keys = sys.argv[1].encode().decode("unicode_escape").encode("latin-1")
    argv = sys.argv[2:]
    pid, fd = pty.fork()
    if pid == 0:
        env = {"TERM": "vt100", "HOME": os.getcwd(), "PATH": "/usr/bin:/bin"}
        os.execve(argv[0], argv, env)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 80, 0, 0))
    start = time.monotonic()
    sent = 0
    status = None
    while time.monotonic() - start < 10:
        r, _, _ = select.select([fd], [], [], 0.1)
        if r:
            try:
                os.read(fd, 4096)
            except OSError:
                pass
        if time.monotonic() - start > 1.5 and sent < len(keys):
            os.write(fd, keys[sent:sent + 1])
            sent += 1
        done, st = os.waitpid(pid, os.WNOHANG)
        if done:
            status = st
            break
    if status is None:
        os.kill(pid, signal.SIGKILL)
        os.waitpid(pid, 0)
        print("timeout")
    elif os.WIFSIGNALED(status):
        print("signal %d" % os.WTERMSIG(status))
    else:
        print("status %d" % os.WEXITSTATUS(status))


if __name__ == "__main__":
    main()
