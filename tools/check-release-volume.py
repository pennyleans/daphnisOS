#!/usr/bin/env python3
"""tools/check-release-volume.py VOLUME TREE: RG-1, the release stick's volume holds what a fresh install needs and
nothing else. VOLUME is the stick's partition 2 as an ext2 image, before any boot; TREE the checkout the stick was
built from. The volume is tools/mkcintvol.sh's: opt/cint/ (TREE's user/cint/opt, BU4-1 A), src/ (every module of
tests/image/build-sources.txt, at its path) and out/ (empty), plus lost+found/; tools/build-release-stick.sh adds
.daphnis/ and tools/build-stick.sh log/ (HW-4m), both empty. Every other entry, a test volume's fixtures above all
(tools/mkdisk.sh's big, sparse, hello.txt, link, a/), is a failure, and so is any expected entry the volume lacks
or holds as another kind, and every file and link under opt/cint and src must hold TREE's bytes, so a fixture saved
under a release file's name fails too. Walks the volume with debugfs (ls -p, every line of which must parse, so a
name with a newline fails) and reads its bytes with debugfs rdump into a temporary directory; writes nothing else.
Exit 0 and one PASS line, else each difference and exit 1.
"""
import os
import re
import subprocess
import sys
import tempfile

EMPTY_DIRS = ("/.daphnis", "/log", "/lost+found", "/out")


def kind(mode):
    t = mode & 0o170000
    return {0o040000: "dir", 0o100000: "file", 0o120000: "link"}.get(t, "other %o" % t)


LS_P = re.compile(r"/(\d+)/([0-7]{6})/(\d+)/(\d+)/([^/\n]*)/(\d*)/")


def walk_volume(img):
    """({path: kind} of every entry under / of the ext2 image, [lines of ls -p that do not parse])."""
    out, bad = {}, []
    todo = ["/"]
    while todo:
        d = todo.pop()
        r = subprocess.run(["debugfs", "-R", "ls -p " + d, img], capture_output=True)
        if r.returncode != 0:
            sys.exit("check-release-volume: debugfs cannot list %s: %s" % (d, r.stderr.decode("utf-8", "replace")))
        for line in r.stdout.decode("utf-8", "replace").split("\n"):
            if line == "":
                continue
            m = LS_P.fullmatch(line)
            if not m:
                bad.append("%s: %r" % (d, line))
                continue
            ino, mode, name = m.group(1), m.group(2), m.group(5)
            if ino == "0" or name in ("", ".", ".."):   # a free slot (lost+found's) and the two links
                continue
            p = d.rstrip("/") + "/" + name
            k = kind(int(mode, 8))
            out[p] = k
            if k == "dir":
                todo.append(p)
    return out, bad


def expected(tree):
    """{path: kind} that tools/mkcintvol.sh, build-release-stick.sh and build-stick.sh put on the volume."""
    want = {p: "dir" for p in EMPTY_DIRS}
    want["/opt"] = want["/src"] = want["/opt/cint"] = "dir"
    opt = os.path.join(tree, "user", "cint", "opt")
    for root, dirs, files in os.walk(opt):
        rel = os.path.relpath(root, opt)
        base = "/opt/cint" + ("" if rel == "." else "/" + rel)
        for n in dirs + files:
            full = os.path.join(root, n)
            want[base + "/" + n] = "link" if os.path.islink(full) else "dir" if os.path.isdir(full) else "file"
        dirs[:] = [n for n in dirs if not os.path.islink(os.path.join(root, n))]
    with open(os.path.join(tree, "tests", "image", "build-sources.txt"), encoding="utf-8") as f:
        for m in f.read().split():
            parts = m.split("/")
            for i in range(1, len(parts)):
                want["/src/" + "/".join(parts[:i])] = "dir"
            want["/src/" + m] = "file"
    return want


def source(tree, p):
    """The file in TREE that volume path p is a copy of."""
    if p.startswith("/opt/cint/"):
        return os.path.join(tree, "user", "cint", "opt", p[len("/opt/cint/"):])
    return os.path.join(tree, p[len("/src/"):])


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__.split("\n")[0])
    img, tree = sys.argv[1], sys.argv[2]
    have, unparsed = walk_volume(img)
    want = expected(tree)
    bad = 0
    for line in unparsed:
        print("check-release-volume: an entry of %s does not parse (a name with a newline?)" % line)
        bad += 1
    for p in sorted(set(have) - set(want)):
        print("check-release-volume: %s on the volume is not a release file (%s)" % (p, have[p]))
        bad += 1
    for p in sorted(set(want) - set(have)):
        print("check-release-volume: %s is missing from the volume (%s)" % (p, want[p]))
        bad += 1
    same = sorted(p for p in set(have) & set(want) if have[p] == want[p])
    for p in sorted(set(have) & set(want)):
        if have[p] != want[p]:
            print("check-release-volume: %s is a %s, not a %s" % (p, have[p], want[p]))
            bad += 1
    with tempfile.TemporaryDirectory(prefix="check-release-volume-") as t:
        r = subprocess.run(["debugfs", "-R", "rdump / " + t, img], capture_output=True)
        if r.returncode != 0:
            sys.exit("check-release-volume: debugfs cannot dump the volume: %s"
                     % r.stderr.decode("utf-8", "replace"))
        for p in same:
            got = os.path.join(t, p.lstrip("/"))
            if want[p] == "link":
                if not os.path.islink(got) or os.readlink(got) != os.readlink(source(tree, p)):
                    print("check-release-volume: %s is not the link TREE has" % p)
                    bad += 1
            elif want[p] == "file":
                with open(got, "rb") as a, open(source(tree, p), "rb") as b:
                    if a.read() != b.read():
                        print("check-release-volume: %s does not hold TREE's bytes" % p)
                        bad += 1
    if bad:
        print("check-release-volume: %d differences" % bad)
        return 1
    files = sum(1 for k in have.values() if k != "dir")
    print("check-release-volume: the volume's %d entries (%d files, each TREE's bytes) are opt/cint, src, out, "
          ".daphnis, log and lost+found, nothing else" % (len(have), files))
    return 0


if __name__ == "__main__":
    sys.exit(main())
