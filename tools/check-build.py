#!/usr/bin/env python3
"""tools/check-build.py TRANSCRIPT LINUX PIN PROGRAM...: the checks of BU-4c's boot (docs/specs/2026-11-07-bu4-toolchain.md
section 2), the disk flavor on the volume of tools/mkcintvol.sh with tests/image/build.txt as its input.

LINUX is check-build.sh's build directory after its Linux leg: for each PROGRAM, PROGRAM.stages (`SHA256  PATH` of the
executable and every file cib left in PROGRAM.cib) and PROGRAM.q1.run (its stdout, stderr and `status N`).
  - the volume's digest at boot is PIN's;
  - the session (sh pid 2) printed `cib PROGRAM: 0` for each, then `grant: 0`;
  - C1: the session's sha256sum lines for PROGRAM are LINUX's PROGRAM.stages, path for path, no more and no fewer;
  - C2: the kernel's two runs of /home/out/PROGRAM (pids 5 and 6, then 7 and 8, ...) print LINUX's bytes and end with
    its status;
  - C3: the two runs have one state digest.
Prints one line per check and exits 1 if any fails."""
import re
import sys

LINE = re.compile(r"^([0-9a-f]{64})  (\S+)$")


def block(text, name, pid):
    m = re.search(r"^daphnis: run %s pid %d\n((?:(?!daphnis: ).*\n)*)((?:daphnis: (?:fault|state) .*\n)*)daphnis: (exit|signal) (\d+)$"
                  % (re.escape(name), pid), text, re.M)
    if not m:
        return None
    return m.group(1), re.findall(r"^daphnis: state ([0-9a-f]{64})$", m.group(2), re.M), (m.group(3), int(m.group(4)))


def stages(path):
    out = {}
    for line in open(path, encoding="utf-8"):
        m = LINE.match(line.rstrip("\n"))
        if m:
            out[m.group(2)] = m.group(1)
    return out


def main():
    transcript, linux, pin_file = sys.argv[1:4]
    progs = sys.argv[4:]
    text = open(transcript, "rb").read().decode("utf-8", "replace")
    pin = open(pin_file, encoding="ascii").read().split()[0]
    checks = []
    boot = re.findall(r"^daphnis: disk (\d+) sha256 ([0-9a-f]{64})$", text, re.M)
    checks.append(("the volume read at boot is tools/mkcintvol.sh's pin", len(boot) == 2 and boot[0][1] == pin))
    sh = block(text, "sh", 2)
    session = sh[0] if sh else ""
    for p in progs:
        checks.append(("cib built %s inside Daphnis: status 0" % p, ("cib %s: 0\n" % p) in session))
    checks.append(("the session under the disk grant ended 0", "grant: 0\n" in session))
    seen = {}
    for line in session.split("\n"):
        m = LINE.match(line)
        if m:
            seen[m.group(2)] = m.group(1)
    for k, p in enumerate(progs):
        want = stages("%s/%s.stages" % (linux, p))
        got = {path: h for path, h in seen.items() if path == p or path.startswith(p + ".cib/")}
        ok = got == want and len(want) > 0
        if not ok:
            for path in sorted(set(got) | set(want)):
                if got.get(path) != want.get(path):
                    print("      %s: daphnis %s, linux %s" % (path, got.get(path), want.get(path)))
        checks.append(("C1 %s: every stage inside Daphnis is the Linux build's, byte for byte (%d files, the executable %s...)"
                       % (p, len(want), want.get(p, "?")[:16]), ok))
        run = open("%s/%s.q1.run" % (linux, p), encoding="utf-8").read()
        body, _, status = run.rpartition("status ")
        a, b = block(text, "/home/out/" + p, 5 + 2 * k), block(text, "/home/out/" + p, 6 + 2 * k)
        ends = ("exit", int(status))
        checks.append(("C2 %s: run alone under Daphnis, twice, it prints Linux's %d bytes and ends with exit %s" % (p, len(body), status.strip()),
                       a is not None and b is not None and a[0] == body and b[0] == body and a[2] == ends and b[2] == ends))
        checks.append(("C3 %s: the two runs have one state digest" % p,
                       a is not None and b is not None and len(a[1]) == 1 and a[1] == b[1]))
    bad = 0
    for label, ok in checks:
        print(("ok    " if ok else "FAIL  ") + label)
        bad += not ok
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
