#!/usr/bin/env python3
"""tests/cvim/cvim_pty.py CVIM WORKDIR [--vim VIM] [--big]: CV-4a's program on a real pseudo-terminal.

Each case writes its file into WORKDIR, runs CVIM (or, with --vim, the same keys in the pinned Vim as the oracle:
`VIM -u NONE -U NONE -i NONE -N -n --clean`) on a 24 x 80 pty, types its keys, and checks what it left: the file's
bytes and mode, the screen's message (E37, E13, ...), the exit status, and that the terminal's settings after the
program are the ones before it (`stty -g` before and after, run by /bin/sh around the program on the same terminal)
and that the program left the alternate screen. With
--vim the written bytes of every case must equal Vim's. --big adds the 64 MiB opening (CV-R3: a file of exactly
64 MiB opens and quits; one byte more is refused by name with status 1). One PASS or FAIL line a case; status 1 on
any FAIL.
"""
import os
import pty
import select
import shutil
import signal
import stat
import sys
import termios
import time
import struct
import fcntl
# the program's own status comes from the wrapper's `rc` (128 + N after signal N)

ROWS, COLS = 24, 80
# CV-8: a directory holding cint: CINT_DIR, else the one cint on PATH comes from, else none
CINT_DIR = os.environ.get("CINT_DIR") or (os.path.dirname(shutil.which("cint")) if shutil.which("cint") else "/nonexistent")
BAD_CI = b'I64 f() {\n    I64 x = "no";\n    return x;\n}\n'   # one error: line 2, column 13
DIRTY1, DIRTY0 = b"\x1b]7770;dirty;1\x07", b"\x1b]7770;dirty;0\x07"
DAPHNIS = b"\x1bP>|Daphnis\x1b\\\x1b[?62;22c"      # AM section 7.2: the desk terminal's XTVERSION, then DA1
OTHER = b"\x1b[?62;22c"                             # another terminal: DA1 alone


class Run:
    def __init__(self, argv, cwd, desk=False, answer=None, path=None):
        self.master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", ROWS, COLS, 0, 0))
        self.cwd = cwd
        for f in ("stty.before", "stty.after", "rc", "pid"):
            if os.path.exists(os.path.join(cwd, f)):
                os.unlink(os.path.join(cwd, f))
        self.pid = os.fork()
        if self.pid == 0:
            os.setsid()
            fcntl.ioctl(slave, termios.TIOCSCTTY, 0)
            for fd in (0, 1, 2):
                os.dup2(slave, fd)
            os.close(self.master)
            os.chdir(cwd)
            os.environ["TERM"] = "xterm-256color"
            os.environ["HOME"] = cwd          # CV-4b: no init file but the case's own (section 6a)
            os.environ.pop("TERM_PROGRAM", None)
            if path is not None:
                os.environ["PATH"] = path        # CV-8: where cint is found, or not
            if desk:
                os.environ["TERM_PROGRAM"] = "daphnis"   # AM-3: a Daphnis desk terminal
            script = 'stty -g > stty.before; "$@"; echo $? > rc; stty -g > stty.after'
            os.execv("/bin/sh", ["/bin/sh", "-c", script, "sh"] + argv)
        self.slave = slave
        self.answer = answer            # AM section 7.2: the terminal's replies to cvim's probe, once
        self.out = b""
        self.status = None

    def pump(self, idle=0.25, limit=10.0):
        t0 = time.monotonic()
        last = time.monotonic()
        while time.monotonic() - t0 < limit:
            r, _, _ = select.select([self.master], [], [], 0.05)
            if r:
                try:
                    data = os.read(self.master, 65536)
                except OSError:
                    return
                if not data:
                    return
                self.out += data
                if self.answer is not None and b"\x1b[>q\x1b[c" in self.out:
                    os.write(self.master, self.answer)
                    self.answer = None
                last = time.monotonic()
            elif time.monotonic() - last >= idle:
                return
            if self.reap(False):
                self.pump_rest()
                return

    def reap(self, block):
        """The wrapper shell (self.pid, ours alone) reaped once: True when it has ended. A pid already reaped (ECHILD:
        the status was taken, or the system took it) counts as ended; its exit status is the rc file's."""
        if self.status is not None:
            return True
        try:
            pid, st = os.waitpid(self.pid, 0 if block else os.WNOHANG)
        except ChildProcessError:
            self.status = -1
            return True
        if pid == self.pid:
            self.status = st
            return True
        return False

    def pump_rest(self):
        while True:
            r, _, _ = select.select([self.master], [], [], 0.05)
            if not r:
                return
            try:
                data = os.read(self.master, 65536)
            except OSError:
                return
            if not data:
                return
            self.out += data

    def type(self, keys, idle=0.25):
        for chunk in keys:
            try:
                os.write(self.master, chunk)
            except OSError:
                return                 # the program ended before its last keys: the case's checks say what it left
            self.pump(idle)

    def wait(self, limit=10.0):
        t0 = time.monotonic()
        while self.status is None and time.monotonic() - t0 < limit:
            self.pump(0.05, 0.5)
        if self.status is None:
            try:
                os.kill(self.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            self.reap(True)
        os.close(self.slave)
        os.close(self.master)
        rd = lambda f: open(os.path.join(self.cwd, f)).read().strip() if os.path.exists(os.path.join(self.cwd, f)) else None
        self.rc = int(rd("rc")) if rd("rc") else None
        b, a = rd("stty.before"), rd("stty.after")
        if sys.platform == "darwin" and a:   # Darwin sets PENDIN (0x20000000) when input waits at the switch
            a = a.replace("lflag=%x:" % (int(b.split("lflag=")[1].split(":")[0], 16) | 0x20000000),
                          "lflag=%s:" % b.split("lflag=")[1].split(":")[0])
        return b is not None and a == b

    def child(self):
        """The program's pid: the wrapper shell's one child."""
        import subprocess
        out = subprocess.run(["pgrep", "-P", str(self.pid)], capture_output=True, text=True).stdout.split()
        return int(out[0]) if out else None


ESC = b"\x1b"


def cases(big):
    """(name, file bytes or None, file mode, keys, checks) a case; checks a dict of what must hold."""
    c = [
        ("edit-w-q", b"a\nb\n", 0o640, [b"A", b"x", ESC, b":w\r", b":q\r"],
         {"bytes": b"ax\nb\n", "mode": 0o640, "exit": 0}),
        ("q-refused-E37", b"one\n", 0o644, [b"ix", ESC, b":q\r"],
         {"screen": b"E37: No write since last change (add ! to override)", "then": [b":q!\r"], "bytes": b"one\n",
          "exit": 0}),
        ("wq-new-file", None, None, [b"ihello", ESC, b":wq\r"], {"bytes": b"hello\n", "exit": 0}),
        ("x-writes", b"k\n", 0o600, [b"dd", b"itwo", ESC, b":x\r"], {"bytes": b"two\n", "mode": 0o600, "exit": 0}),
        ("ZZ-ZQ", b"z\n", 0o644, [b"ix", ESC, b"ZQ"], {"bytes": b"z\n", "exit": 0}),
        ("ZZ-writes", b"z\n", 0o644, [b"ix", ESC, b"ZZ"], {"bytes": b"xz\n", "exit": 0}),
        ("noeol-fixeol", b"abc", 0o644, [b"Ad", ESC, b":w\r", b":q\r"], {"bytes": b"abcd\n", "exit": 0}),
        ("e-bang", b"keep\n", 0o644, [b"dd", b":e!\r", b":wq\r"], {"bytes": b"keep\n", "exit": 0}),
        ("goto-line", b"1\n2\n3\n4\n", 0o644, [b":3\r", b"dd", b":wq\r"], {"bytes": b"1\n2\n4\n", "exit": 0}),
        ("w-other-E13", b"mine\n", 0o644, [b":w other.txt\r"],
         {"other": b"theirs\n", "screen": b"E13: File exists (add ! to override)", "then": [b":q\r"], "exit": 0,
          "bytes": b"mine\n"}),
        ("unknown-E492", b"u\n", 0o644, [b":frob\r"],
         {"screen": b"E492: Not an editor command: frob", "then": [b":q\r"], "exit": 0, "bytes": b"u\n"}),
        ("no-name-E32", None, None, [b":w\r"], {"noname": True, "screen": b"E32: No file name", "then": [b":q\r"],
                                                 "exit": 0}),
        ("set-nonumber", b"s\n", 0o644, [b":set nonumber\r", b":set number\r", b":q\r"], {"exit": 0, "bytes": b"s\n"}),
        ("sigterm-restores", b"t\n", 0o644, [b"ix"], {"signal": signal.SIGTERM, "bytes": b"t\n"}),
        # CV-4b: buffers (Vim's 'nohidden'), the init file and --clean. Unverified until the --vim leg runs (Arch).
        ("buf-e-other-back", b"a\nb\n", 0o644, [b":e other.txt\r", b"ix", ESC, b":w\r", b":b1\r", b"dd", b":wq\r"],
         {"other": b"c\n", "bytes": b"b\n", "files": {"other.txt": b"xc\n"}, "exit": 0}),
        ("buf-bn-bp", b"a\nb\n", 0o644, [b":e other.txt\r", b":bp\r", b"dd", b":w\r", b":bn\r", b"dd", b":w\r",
                                          b":q\r"],
         {"other": b"c\nd\n", "bytes": b"b\n", "files": {"other.txt": b"d\n"}, "exit": 0}),
        ("buf-nohidden-E37", b"a\nb\n", 0o644, [b"dd", b":e other.txt\r"],
         {"other": b"c\n", "screen": b"E37: No write since last change (add ! to override)",
          "then": [b":e! other.txt\r", b":b1\r", b"ix", ESC, b":wq\r"], "bytes": b"xa\nb\n", "exit": 0}),
        ("buf-bn-E37", b"a\n", 0o644, [b":e other.txt\r", b"dd", b":bn\r"],
         {"other": b"c\nd\n", "screen": b"E37: No write since last change (add ! to override)",
          "then": [b":w\r", b":bn\r", b":wq\r"], "files": {"other.txt": b"d\n"}, "bytes": b"a\n", "exit": 0}),
        ("buf-b-E86", b"a\n", 0o644, [b":b 5\r"], {"screen": b"E86: Buffer 5 does not exist", "then": [b":q\r"],
                                                     "bytes": b"a\n", "exit": 0}),
        ("buf-ls", b"a\n", 0o644, [b":e other.txt\r", b":ls\r"],
         {"other": b"c\n", "screen": b'  2 %a   "other.txt"', "then": [b":q\r"], "exit": 0}),
        ("buf-bd", b"a\nb\n", 0o644, [b":e other.txt\r", b":bd\r", b"dd", b":wq\r"],
         {"other": b"c\n", "bytes": b"b\n", "exit": 0}),
        ("buf-registers-stay", b"a\nb\n", 0o644, [b"yy", b":e other.txt\r", b"p", b":w\r", b":q\r"],
         {"other": b"c\n", "files": {"other.txt": b"c\na\n"}, "exit": 0}),
        ("buf-args", b"a\n", 0o644, [b":bn\r", b"dd", b":w\r", b":q!\r"],   # :q! leaves with a file unseen, Vim too
         {"other": b"c\nd\n", "args": ["other.txt"], "files": {"other.txt": b"d\n"}, "exit": 0}),
        ("init-nnoremap", b"a\nb\n", 0o644, [b",", b":wq\r"],
         {"init": b'" a comment\n\nnnoremap , dd\n', "bytes": b"b\n", "exit": 0}),
        ("init-inoremap", b"a\n", 0o644, [b"ixjk", b":wq\r"],
         {"init": b"inoremap jk <Esc>\n", "bytes": b"xa\n", "exit": 0}),
        ("init-clean", b"a\nb\n", 0o644, [b",", b":wq\r"],
         {"init": b"nnoremap , dd\n", "clean": True, "bytes": b"a\nb\n", "exit": 0}),
        ("init-set", b"aA\n", 0o644, [b":s/a/x/g\r", b":wq\r"],
         {"init": b"set noignorecase\n", "bytes": b"xA\n", "exit": 0}),
        ("init-refused", b"a\nb\n", 0o644, [b",", b":wq\r"],
         {"init": b"autocmd BufRead * echo 1\nnnoremap , dd\n", "cvim_only": True,
          "screen": b"init 1: not in cvim: autocmd", "bytes": b"b\n", "exit": 0}),
        ("init-leader", b"a\nb\n", 0o644, [b" d", b":wq\r"],
         {"init": b"nnoremap <leader>d dd\n", "cvim_only": True, "bytes": b"b\n", "exit": 0}),
        ("init-set-lists", b"a\n", 0o644, [b":set\r"],
         {"init": b"set nonumber\n", "cvim_only": True, "screen": b"nonumber", "then": [b"\r", b":q\r"], "exit": 0}),
        # AM section 7 (DN-47): in a desk terminal cvim reports its modified flag when it changes, and clears it on
        # every way out; elsewhere it sends no OSC 7770 at all (every other case).
        # CV-8: Space c b builds with the cint on PATH (CINT_DIR, else none found); the error's line gets E, the status
        # line E1; Space c d and Enter, or ] d, put the cursor on its column, which x then deletes.
        ("build-list-jump", BAD_CI, 0o644, [b" cb", b" cd", b"\r", b"x", b":wq\r"],
         {"fname": "f.ci", "cint_dir": CINT_DIR, "cvim_only": True, "bytes": BAD_CI.replace(b'= "', b"= "),
          "exit": 0, "has": [b"\x1b[0;1;31mE", b" E1"]}),
        ("build-bracket-d", BAD_CI, 0o644, [b" cb", b"]d", b"x", b":wq\r"],
         {"fname": "f.ci", "cint_dir": CINT_DIR, "cvim_only": True, "bytes": BAD_CI.replace(b'= "', b"= "),
          "exit": 0}),
        ("build-no-cint", BAD_CI, 0o644, [b" cb"],
         {"fname": "f.ci", "cint_dir": "/nonexistent", "cvim_only": True, "screen": b"no cint in this image",
          "then": [b":q\r"], "exit": 0}),
        ("desk-dirty-w-q-bang", b"a\n", 0o644, [b"ix", ESC, b":w\r", b"iy", ESC, b":q!\r"],
         {"desk": True, "answer": DAPHNIS, "cvim_only": True, "bytes": b"xa\n", "exit": 0,
          "osc": [b"\x1b]7770;about;", DIRTY1, DIRTY0, DIRTY1, DIRTY0], "osc_count": 4}),
        ("desk-dirty-undo-q-bang", b"a\n", 0o644, [b"ix", ESC, b"u", b"iy", ESC, b":q!\r"],
         {"desk": True, "answer": DAPHNIS, "cvim_only": True, "bytes": b"a\n", "exit": 0,
          "osc": [DIRTY1, DIRTY0, DIRTY1, DIRTY0],
          "osc_count": 4}),
        ("desk-other-terminal", b"a\n", 0o644, [b"ix", ESC, b"u", b":q\r"],   # DA1 alone: quiet, no stray keys
         {"desk": True, "answer": OTHER, "cvim_only": True, "bytes": b"a\n", "exit": 0, "no_osc": True}),
        ("desk-dirty-undo", b"a\n", 0o644, [b"ix", ESC, b"u", b":q\r"],
         {"desk": True, "answer": DAPHNIS, "cvim_only": True, "bytes": b"a\n", "exit": 0, "osc": [DIRTY1, DIRTY0],
          "osc_count": 2}),
    ]
    if big:
        n = 64 << 20
        line = b"0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ012345678\n"   # 72 bytes
        body = (line * (n // len(line) + 1))[:n - 1] + b"\n"
        c.append(("open-64MiB", body, 0o644, [b"G", b":q\r"], {"exit": 0, "bytes": body, "timed": True}))
        c.append(("refuse-64MiB-plus-1", body + b"x", 0o644, [], {"exit": 1, "refused": True}))
    return c


def main(argv):
    prog, work = argv[0], argv[1]
    vim = argv[argv.index("--vim") + 1] if "--vim" in argv else None
    big = "--big" in argv
    os.makedirs(work, exist_ok=True)
    bad = 0
    for name, data, mode, keys, want in cases(big):
        if vim and want.get("cvim_only"):
            print("SKIP  cvim %s (cvim's own: its words or its leader)" % name)
            continue
        d = os.path.join(work, name)
        os.makedirs(d, exist_ok=True)
        f = os.path.join(d, want.get("fname", "f.txt"))
        for p in (f, os.path.join(d, "other.txt")):
            if os.path.lexists(p):
                os.unlink(p)
        if data is not None:
            with open(f, "wb") as h:
                h.write(data)
            os.chmod(f, mode)
        if "other" in want:
            with open(os.path.join(d, "other.txt"), "wb") as h:
                h.write(want["other"])
        init = os.path.join(d, ".config", "cvim", "init")
        if os.path.lexists(init):
            os.unlink(init)
        if "init" in want:
            os.makedirs(os.path.dirname(init), exist_ok=True)
            with open(init, "wb") as h:
                h.write(want["init"])
        args = [os.path.abspath(prog)] + (["--clean"] if want.get("clean") else []) + \
            ([] if want.get("noname") else [want.get("fname", "f.txt")]) + want.get("args", [])
        if vim:
            rc = init if "init" in want and not want.get("clean") else "NONE"
            args = [vim, "-u", rc, "-U", "NONE", "-i", "NONE", "-N", "-n"] + \
                (["--clean"] if rc == "NONE" else []) + args[1 + (1 if want.get("clean") else 0):]
        t0 = time.monotonic()
        path = None
        if "cint_dir" in want:
            path = want["cint_dir"] + ":/usr/bin:/bin"
        run = Run(args, d, want.get("desk", False), want.get("answer"), path)
        run.pump(0.5, 30.0 if want.get("timed") else 5.0)
        first = time.monotonic() - t0
        run.type(keys)
        notes = []
        ok = True
        if "screen" in want:
            seen = want["screen"] in run.out
            ok = ok and seen
            if not seen:
                notes.append("no %r on the screen" % want["screen"])
            run.type(want.get("then", []))
        if "signal" in want:
            os.kill(run.child(), want["signal"])
        restored = run.wait()
        st = run.rc
        if "signal" in want:
            ok = ok and st == 128 + want["signal"]
        elif "exit" in want:
            ok = ok and st == want["exit"]
        if vim and "signal" in want:
            restored = True   # the oracle's own SIGTERM leaves its terminal as it is; cvim's must not
        ok = ok and restored
        if not restored:
            notes.append("terminal settings not restored")
        if not vim and not want.get("refused") and b"\x1b[?1049l" not in run.out:
            ok = False
            notes.append("did not leave the alternate screen")
        if "bytes" in want:
            got = open(f, "rb").read() if os.path.exists(f) else None
            same = got == want["bytes"]
            ok = ok and same
            if not same:
                notes.append("bytes %r" % (got[:40] if got else got))
        for other, b in want.get("files", {}).items():
            p = os.path.join(d, other)
            got = open(p, "rb").read() if os.path.exists(p) else None
            if got != b:
                ok = False
                notes.append("%s %r" % (other, got[:40] if got else got))
        if "mode" in want:
            m = stat.S_IMODE(os.stat(f).st_mode)
            ok = ok and m == want["mode"]
            if m != want["mode"]:
                notes.append("mode %o" % m)
        if want.get("refused"):
            ok = ok and b"over 64 MiB" in run.out
        if not vim and (not want.get("desk") or want.get("no_osc")) and b"\x1b]7770" in run.out:
            ok = False
            notes.append("an OSC 7770 outside a desk terminal")
        for h in want.get("has", []):
            if h not in run.out:
                ok = False
                notes.append("no %r" % h)
        at = 0
        for o in want.get("osc", []):
            k = run.out.find(o, at)
            if k < 0:
                ok = False
                notes.append("no %r in order" % o)
                break
            at = k + len(o)
        if "osc_count" in want:
            n = run.out.count(b"\x1b]7770;dirty;")
            if n != want["osc_count"]:
                ok = False
                notes.append("%d dirty reports" % n)
        extra = " (first frame %.2f s)" % first if want.get("timed") else ""
        print("%s  cvim %s%s%s" % ("PASS" if ok else "FAIL", name, extra, "" if ok else ": " + "; ".join(notes) +
                                     " status %r" % st))
        bad += not ok
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
