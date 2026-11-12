#!/usr/bin/env python3
"""tests/rg/setkey_run.py SETKEY: user/ci/setkey.ci built for the host, run as the desk's RUN_PREFS runs it (RG-1).

The desk cannot open an account's settings in its 0700 home, so its run as the account reads them: `setkey --print`
writes the file's kept lines as KEY=VALUE text. Checks: the values setkey KEY VALUE wrote come back, in a 0700 home;
no file is no settings (status 0, nothing written); a file of 8192 bytes comes back whole; a link put where the file
goes gives status 1 and no byte; `--print` and a second word is the key `--print`, refused (status 1); three words
and no HOME give status 2. One line a check that
fails, then "setkey: N checks, F failed"; exit status 1 if any failed.
"""
import os
import subprocess
import sys
import tempfile

checks = 0
failed = 0


def check(ok, what):
    global checks, failed
    checks += 1
    if not ok:
        failed += 1
        print("FAIL", what)


def run(exe, home, *words):
    env = {"PATH": "/bin"} if home is None else {"HOME": home, "PATH": "/bin"}
    p = subprocess.run([exe, *words], env=env, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=20)
    return p.returncode, p.stdout


def main():
    exe = os.path.abspath(sys.argv[1])
    with tempfile.TemporaryDirectory() as t:
        home = os.path.join(t, "ada")
        os.mkdir(home, 0o700)
        st, out = run(exe, home, "--print")
        check(st == 0 and out == b"", "no file: no settings, status 0")
        check(run(exe, home, "time.24-hour", "1")[0] == 0, "setkey time.24-hour 1")
        check(run(exe, home, "calendar.week-starts", "1")[0] == 0, "setkey calendar.week-starts 1")
        st, out = run(exe, home, "--print")
        lines = out.split(b"\n")
        check(st == 0 and b"time.24-hour=1" in lines and b"calendar.week-starts=1" in lines,
              "the values written come back: %r" % out)
        check(oct(os.stat(home).st_mode & 0o777) == "0o700", "the home stays 0700")
        f = os.path.join(home, ".config", "daphnis", "settings")
        body = b"".join(b"k.n%04d=%s\n" % (i, b"v" * 7) for i in range(512))   # 512 lines of 16 bytes: 8192
        with open(f, "wb") as o:
            o.write(body)
        st, out = run(exe, home, "--print")
        check(st == 0 and out == body, "a file of 8192 bytes comes back whole (%d bytes)" % len(out))
        os.unlink(f)
        os.symlink("/etc/passwd", f)
        st, out = run(exe, home, "--print")
        check(st == 1 and out == b"", "a link where the file goes: status 1, nothing written")
        os.unlink(f)
        check(run(exe, home, "--print", "x")[0] == 1 and not os.path.exists(f),
              "--print and a second word is a key setkey refuses: status 1, nothing written")
        check(run(exe, home, "--print", "x", "y")[0] == 2, "three words: status 2")
        check(run(exe, None, "--print")[0] == 2, "no HOME: status 2")
    print("setkey: %d checks, %d failed" % (checks, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
# SPDX-License-Identifier: Apache-2.0
