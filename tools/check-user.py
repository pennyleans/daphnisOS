#!/usr/bin/env python3
"""tools/check-user.py TRANSCRIPT USERDIR [--image CPIO] [--stdin FILE]: the Linux oracle of the
user flavor (U1-1 to U1-3, docs/user.md).

Every block of the transcript that runs a program unchanged,

    daphnis: run NAME pid P
    <the program's output>
    [daphnis: fault ...]
    daphnis: state <digest>
    daphnis: exit N | daphnis: signal N

is checked against the same file run on this host's Linux, with argv[0] NAME: the output bytes (descriptors 1 and 2
together, as Daphnis's console takes them, R-1) must be equal, and so must the exit status or the signal; the Linux run
has Daphnis's quota as its RLIMIT_AS (M-1). With --image, each run gets a fresh
directory holding the image's members (hard links as copies, directory members as directories, P-0) as its working
directory, which is the root directory Daphnis shows; that directory's path in Linux's output reads as "/" (P-0:
`pwd` and getcwd print paths from the root), and sh (cish, DOS-3) runs with PATH that directory's bin/ only, so it
runs the image's /bin as its default PATH does under Daphnis; with --stdin, the file's bytes without a final 0x04 (the
end of the serial input) are its standard input. Prints one PASS or FAIL line per block, then a
total; exits 1 on any FAIL, on a transcript with no block, or when a program in USERDIR was
never checked (EXEMPT names the few with an oracle of their own). A canary block (the kernel flips a bit first) is not a Linux run and is skipped
by its form, and so is a device block (`daphnis: run NAME pid P (device)`, F-1: the program draws on
the surface, which Linux does not have): it is listed as SKIP and counts as a run of its program."""
import os
import re
import resource
import subprocess
import sys
import tempfile

RUN = re.compile(rb"^daphnis: run ([a-z0-9_]+) pid ([0-9]+)( \(device\))?$")
END = re.compile(rb"^daphnis: (exit|signal) ([0-9]+)$")


def blocks(data):
    lines = data.split(b"\n")
    i = 0
    while i < len(lines):
        m = RUN.match(lines[i])
        i += 1
        if not m:
            continue
        out = []
        while i < len(lines) and not lines[i].startswith(b"daphnis: "):
            out.append(lines[i] + b"\n")
            i += 1
        while i < len(lines) and not END.match(lines[i]):
            if not re.match(rb"^daphnis: (fault|state) ", lines[i]):
                break
            i += 1
        e = END.match(lines[i]) if i < len(lines) else None
        yield m.group(1).decode(), int(m.group(2)), b"".join(out), (e.group(1).decode(), int(e.group(2))) if e else None, m.group(3) is not None


def members(cpio):
    """(name, mode, bytes) per member of a newc archive, hard links resolved; a directory's mode
    keeps its type bits."""
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


# Programs the plain oracle cannot run as a stdout program, each with its own oracle elsewhere.
EXEMPT = {
    "cvim": "a full-screen editor that needs a terminal; its oracles are check-cvim.sh (Vim 9.1.1752 core, edit and pty)",
}


QUOTA = 15360 * 4096   # M-1: a process's RLIMIT_AS under Daphnis (src/uvm.ci MAX_FRAMES), so Linux grants the same


def quota():
    resource.setrlimit(resource.RLIMIT_AS, (QUOTA, QUOTA))


def linux(path, name, image, stdin):
    with tempfile.TemporaryDirectory() as cwd:
        for member, mode, body in image:
            if mode & 0o170000 == 0o040000:
                os.mkdir(os.path.join(cwd, member))
            else:
                with open(os.path.join(cwd, member), "wb") as f:
                    f.write(body)
            os.chmod(os.path.join(cwd, member), mode & 0o777)
        env = {"PATH": os.path.join(cwd, "bin")} if name == "sh" else {}
        r = subprocess.run([name], executable=path, input=stdin, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=60, env=env, cwd=cwd, preexec_fn=quota)
        root = os.path.realpath(cwd).encode()
        out = r.stdout.replace(root + b"/", b"/").replace(root, b"/")
    end = ("signal", -r.returncode) if r.returncode < 0 else ("exit", r.returncode)
    return out, end


def main(argv):
    transcript, userdir = argv[0], argv[1]
    image = []
    stdin = b""
    rest = argv[2:]
    while rest:
        if rest[0] == "--image":
            image = members(rest[1])
        elif rest[0] == "--stdin":
            with open(rest[1], "rb") as f:
                stdin = f.read()
            if stdin.endswith(b"\x04"):
                stdin = stdin[:-1]
        else:
            sys.exit("usage: check-user.py TRANSCRIPT USERDIR [--image CPIO] [--stdin FILE]")
        rest = rest[2:]
    with open(transcript, "rb") as f:
        data = f.read()
    fails = checked = 0
    seen = set()
    for name, pid, out, end, device in blocks(data):
        if device:
            print("SKIP  oracle %s pid %d: a device run, not a Linux run" % (name, pid))
            seen.add(name)
            continue
        path = os.path.join(userdir, name)
        want_out, want_end = linux(path, name, image, stdin)
        ok = end is not None and out == want_out and end == want_end
        print("%s  oracle %s pid %d: Linux %s %d, %d output bytes" % (
            "PASS" if ok else "FAIL", name, pid, want_end[0], want_end[1], len(want_out)))
        if not ok:
            print("      daphnis: %r %r" % (out, end))
            print("      linux:   %r %r" % (want_out, want_end))
            fails += 1
        checked += 1
        seen.add(name)
    progs = {p for p in os.listdir(userdir) if "." not in p}
    for name in sorted(progs & set(EXEMPT)):
        print("SKIP  oracle %s: %s" % (name, EXEMPT[name]))
    missing = sorted(progs - seen - set(EXEMPT))
    if missing:
        print("FAIL  oracle: programs never run: %s" % " ".join(missing))
        fails += 1
    if checked == 0:
        print("FAIL  oracle: no block in %s" % transcript)
        fails += 1
    print("oracle: %d blocks, %d failed" % (checked, fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
