"""tests/cvim/vim_leg.py: the oracle's Vim leg (docs/specs/2026-11-07-cv-cvim.md gate 1).

Each case's start file goes into a scratch directory; Vim runs on it under a pseudo-terminal of 24 rows and 80 columns
(TERM=xterm), started as `vim --clean -u NONE -i NONE -n -N -S tests/cvim/oracle.vim FILE`. The script's keys go in
as an xterm sends them, with a pause after each lone Esc so Vim reads no key code. Then the driver types an Ex line
that writes the cursor's line and byte column (both from 1) to a file, and `:wq`. A script must end in Normal mode
with no command pending, as cvim's leg checks. Linux only.
"""

import os
import pty
import select
import struct
import subprocess
import tempfile
import time
from pathlib import Path

import fcntl
import termios

import keys

HERE = Path(__file__).resolve().parent
ESC_PAUSE = 0.06


def version():
    """The first line of `vim --version`, or None when there is no Vim."""
    try:
        run = subprocess.run(["vim", "--version"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    lines = run.stdout.splitlines()
    patches = next((l for l in lines if l.startswith("Included patches")), "")
    return (lines[0] + "; " + patches).strip() if lines else None


def drain(fd, seconds):
    end = time.monotonic() + seconds
    while True:
        left = end - time.monotonic()
        if left <= 0:
            return
        r, _, _ = select.select([fd], [], [], left)
        if r:
            try:
                if not os.read(fd, 65536):
                    return
            except OSError:
                return


def run_case(text, script, limit=10.0):
    """(file bytes, (line, col), (register type, register bytes)) after `script` in Vim on a file holding `text`."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "f.txt"
        path.write_bytes(text)
        cur = Path(tmp) / "cursor"
        env = dict(os.environ, TERM="xterm", HOME=tmp, LANG="C.UTF-8", LC_ALL="C.UTF-8")
        env.pop("DISPLAY", None)
        pid, fd = pty.fork()
        if pid == 0:
            os.chdir(tmp)
            os.execvpe("vim", ["vim", "--clean", "-u", "NONE", "-i", "NONE", "-n", "-N", "-X",
                               "-S", str(HERE / "oracle.vim"), "f.txt"], env)
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 80, 0, 0))
        try:
            drain(fd, 0.25)
            batch = b""
            for b, lone_esc in keys.vim_bytes(script):
                batch += b
                if lone_esc:
                    os.write(fd, batch)
                    batch = b""
                    drain(fd, ESC_PAUSE)
            if batch:
                os.write(fd, batch)
                drain(fd, 0.02)
            os.write(fd, (":call writefile([line('.') . ' ' . col('.'), getregtype('\"')] + getreg('\"', 1, 1), '"
                          + str(cur) + "')\r:wq\r").encode())
            end = time.monotonic() + limit
            while True:
                done, status = os.waitpid(pid, os.WNOHANG)
                if done:
                    break
                if time.monotonic() > end:
                    os.kill(pid, 9)
                    os.waitpid(pid, 0)
                    raise RuntimeError("vim did not quit (a script left a command pending?)")
                drain(fd, 0.02)
        finally:
            os.close(fd)
        if not cur.exists():
            raise RuntimeError("vim wrote no cursor (a script left Insert mode or a command pending?)")
        lines = cur.read_bytes()[:-1].split(b"\n")
        line, col = (int(v) for v in lines[0].split())
        kind = lines[1].decode()
        reg = b"\n".join(lines[2:]) + (b"\n" if kind == "V" else b"")
        if kind not in ("v", "V"):
            kind, reg = "v", b""
        return path.read_bytes() if path.exists() else b"", (line, col), (kind, reg)


# CV-2b: the registers each new case records, in this order; '"' is the unnamed register.
REGS = '"0123456789-abq'


def run_full(text, script, limit=10.0):
    """run_case plus the window's top line and height and every register of REGS as (kind, bytes): kind 'v', 'V',
    'b' and the block's width, or '' with no bytes for an empty register."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "f.txt"
        path.write_bytes(text)
        env = dict(os.environ, TERM="xterm", HOME=tmp, LANG="C.UTF-8", LC_ALL="C.UTF-8")
        env.pop("DISPLAY", None)
        pid, fd = pty.fork()
        if pid == 0:
            os.chdir(tmp)
            os.execvpe("vim", ["vim", "--clean", "-u", "NONE", "-i", "NONE", "-n", "-N", "-X",
                               "-S", str(HERE / "oracle.vim"), "f.txt"], env)
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 80, 0, 0))
        try:
            drain(fd, 0.25)
            batch = b""
            for b, lone_esc in keys.vim_bytes(script):
                batch += b
                if lone_esc:
                    os.write(fd, batch)
                    batch = b""
                    drain(fd, ESC_PAUSE)
            if batch:
                os.write(fd, batch)
                drain(fd, 0.02)
            ex = (":let s='" + REGS.replace("'", "''") + "'|call writefile([line('.') . ' ' . col('.'), line('w0') . ' '"
                  " . winheight(0), mode()] + map(split(s, '\\zs'), 'getregtype(v:val)'), 'cur')|for n in range(len(s))"
                  "|call writefile(getreg(s[n], 1, 1), 'r' . n, 'b')|endfor\r:wq\r")
            os.write(fd, ex.encode())
            end = time.monotonic() + limit
            while True:
                done, status = os.waitpid(pid, os.WNOHANG)
                if done:
                    break
                if time.monotonic() > end:
                    os.kill(pid, 9)
                    os.waitpid(pid, 0)
                    raise RuntimeError("vim did not quit (a script left a command pending?)")
                drain(fd, 0.02)
        finally:
            os.close(fd)
        cur = Path(tmp) / "cur"
        if not cur.exists():
            raise RuntimeError("vim wrote no cursor (a script left Insert mode or a command pending?)")
        rows = cur.read_bytes().split(b"\n")
        line, col = (int(v) for v in rows[0].split())
        top, height = (int(v) for v in rows[1].split())
        regs = {}
        for n, name in enumerate(REGS):
            kind = rows[3 + n].decode("latin-1")
            body = (Path(tmp) / ("r" + str(n))).read_bytes()
            if kind == "V":
                body += b"\n"
            elif kind.startswith("\x16"):
                kind = "b" + kind[1:]
            if not body:
                kind = ""
            regs[name] = (kind, body)
        return dict(text=path.read_bytes() if path.exists() else b"", cursor=(line, col), top=top, height=height,
                    vmode=rows[2].decode(), regs=regs)


if __name__ == "__main__":
    import sys
    print(version())
    t = sys.argv[1].encode().decode("unicode_escape").encode("utf-8")
    print(run_case(t, sys.argv[2]))
