#!/usr/bin/env python3
"""tools/check-cish.py: the two halves of cish's oracle (docs/specs/2026-11-06-cish-shell.md section 9, CS-1).

  check-cish.py linux CPIO SESSION OUT SHELL [ARG...]
      Runs SHELL with ARG... in a fresh directory holding the members of the image CPIO (hard links as copies,
      directories as directories, as tools/check-user.py unpacks them), SESSION's bytes as its standard input
      (without a final 0x04), descriptors 1 and 2 together, the environment PATH=<that directory>/bin only, and
      Daphnis's process quota as RLIMIT_AS. The directory's path reads as "/" in the output (getcwd prints paths
      from the root). Writes the output, then a line `status N` (or `signal N`), to OUT.
  check-cish.py refuse CPIO LIST OUT SHELL
      CS-3: each line of LIST run as `SHELL -c LINE` in such a directory; OUT holds, for each, the line, the
      output (1 and 2 together) and `status N`. Exits 1 unless every status is 2 (gate 4: refused by name).
  check-cish.py daphnis TRANSCRIPT PID OUT [NAME]
      The block of `daphnis: run NAME pid PID` (NAME cish unless given; K-10: ctrlc; K-9: keyed) in TRANSCRIPT in the same form:
      the program's bytes, then its exit or signal line. Exits 1 when there is no such block.
  check-cish.py screen LOG OUT
      K-9: the bytes keyed logged (all the terminal showed) drawn in the terminal twin of tools/check-tiler.py, 80 x 24
      as typist.ci opens it: OUT holds each row, its trailing blanks dropped, then `cursor ROW COL`, 1-based."""
import importlib.util
import os
import re
import resource
import subprocess
import sys
import tempfile

QUOTA = 15360 * 4096   # M-1: a process's RLIMIT_AS under Daphnis (src/uvm.ci MAX_FRAMES)


def members(cpio):
    with open(cpio, "rb") as f:
        data = f.read()
    at = 0
    raw = []
    while at + 110 <= len(data) and data[at:at + 6] == b"070701":
        fields = [int(data[at + 6 + 8 * k:at + 14 + 8 * k], 16) for k in range(13)]
        ino, mode, size, namesize = fields[0], fields[1], fields[6], fields[11]
        name = data[at + 110:at + 110 + namesize - 1].decode()
        start = (at + 110 + namesize + 3) & ~3
        at = (start + size + 3) & ~3
        if name == "TRAILER!!!":
            break
        raw.append((name, ino, mode, data[start:start + size]))
    held = {ino: body for _, ino, _, body in raw if body}
    return [(name, mode & 0o170777, body or held.get(ino, b"")) for name, ino, mode, body in raw]


def quota():
    resource.setrlimit(resource.RLIMIT_AS, (QUOTA, QUOTA))


def unpack(cpio, cwd):
    for member, mode, body in members(cpio):
        p = os.path.join(cwd, member)
        if mode & 0o170000 == 0o040000:
            os.mkdir(p)
        else:
            with open(p, "wb") as f:
                f.write(body)
        os.chmod(p, mode & 0o777)


def refuse(cpio, listing, out, shell):
    with open(listing, "rb") as f:
        cases = [c for c in f.read().split(b"\n") if c]
    text = b""
    ok = True
    with tempfile.TemporaryDirectory() as cwd:
        unpack(cpio, cwd)
        for c in cases:
            r = subprocess.run([shell, "-c", c], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60,
                               env={"PATH": os.path.join(cwd, "bin")}, cwd=cwd, preexec_fn=quota)
            text += c + b"\n" + r.stdout + b"status %d\n" % r.returncode
            ok = ok and r.returncode == 2
    with open(out, "wb") as f:
        f.write(text)
    return 0 if ok else 1


def linux(cpio, session, out, argv):
    with open(session, "rb") as f:
        stdin = f.read()
    if stdin.endswith(b"\x04"):
        stdin = stdin[:-1]
    with tempfile.TemporaryDirectory() as cwd:
        unpack(cpio, cwd)
        r = subprocess.run(argv, input=stdin, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60,
                           env={"PATH": os.path.join(cwd, "bin")}, cwd=cwd, preexec_fn=quota)
        root = os.path.realpath(cwd).encode()
        text = r.stdout.replace(root + b"/", b"/").replace(root, b"/")
    end = b"signal %d\n" % -r.returncode if r.returncode < 0 else b"status %d\n" % r.returncode
    with open(out, "wb") as f:
        f.write(text + end)
    return 0


def daphnis(transcript, pid, out, name=b"cish"):
    with open(transcript, "rb") as f:
        lines = f.read().split(b"\n")
    head = b"daphnis: run %s pid %d" % (name, pid)
    if head not in lines:
        print("check-cish.py: no block %r in %s" % (head, transcript))
        return 1
    i = lines.index(head) + 1
    body = []
    while i < len(lines) and not lines[i].startswith(b"daphnis: "):
        body.append(lines[i] + b"\n")
        i += 1
    while i < len(lines) and re.match(rb"^daphnis: (fault|state) ", lines[i]):
        i += 1
    m = re.match(rb"^daphnis: (exit|signal) ([0-9]+)$", lines[i]) if i < len(lines) else None
    if not m:
        print("check-cish.py: the block of pid %d has no exit line" % pid)
        return 1
    word = b"status" if m.group(1) == b"exit" else b"signal"
    with open(out, "wb") as f:
        f.write(b"".join(body) + word + b" " + m.group(2) + b"\n")
    return 0


def screen(log, out):
    spec = importlib.util.spec_from_file_location("check_tiler", os.path.join(os.path.dirname(__file__), "check-tiler.py"))
    ct = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ct)
    with open(log, "rb") as f:
        grid, x, y, _ = ct.vt(f.read(), 80, 24)
    rows = [bytes(c[0] for c in row).rstrip(b" ") + b"\n" for row in grid]
    with open(out, "wb") as f:
        f.write(b"".join(rows) + b"cursor %d %d\n" % (y + 1, x + 1))
    return 0


def main(argv):
    if len(argv) >= 5 and argv[0] == "linux":
        return linux(argv[1], argv[2], argv[3], argv[4:])
    if len(argv) == 5 and argv[0] == "refuse":
        return refuse(argv[1], argv[2], argv[3], argv[4])
    if len(argv) == 3 and argv[0] == "screen":
        return screen(argv[1], argv[2])
    if len(argv) in (4, 5) and argv[0] == "daphnis":
        return daphnis(argv[1], int(argv[2]), argv[3], *[a.encode() for a in argv[4:]])
    sys.exit(__doc__)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
