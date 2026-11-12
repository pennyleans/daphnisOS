#!/usr/bin/env python3
"""tools/check-core.py: the case runner of the native core set (docs/specs/2026-11-06-c-core.md section 6).

  check-core.py cases CASES TREE OUT ARGV...
      Runs each case of CASES (`ARGS | STDIN | DIFF`, split at the last two |, so ARGS may hold one; # starts a
      comment) as ARGV followed by ARGS (split as the shell splits words), in a fresh copy of TREE, standard input the tree's file STDIN or nothing for `-`, the
      environment TZ=UTC0 only, umask 022, Daphnis's process quota as RLIMIT_AS. The copy is made the same on every host (CT-1):
      directories mode 0755, files 0644 (0755 when the tree's file has its owner's x bit), and the k-th path in
      byte order modified and accessed at T0 + 60 k seconds; a case whose ARGS name `many` or `deep` also gets many/ (1,000 empty files, f000 to f999) or deep/ (DEEP
      nested directories `d`, one file `f` at the bottom), which git does not hold. Writes OUT: for each case
      `$ ARGS`, its stdout, `-- stderr` and its stderr when there is any, `-- tree` and each entry of the copy the case
      added (+), removed (-) or changed (~) when there is any (CT-2), and `status N` (or `signal N`); and OUT.json,
      the same data. A name made from a mktemp template (a word of ARGS ending in XXX, or tmp.XXXXXX) prints as its
      template. A case whose DIFF holds the word `H` (alone, or after a row: `D-10 H`) depends on the
      host (owners, a directory's size, links and blocks): OUT holds `-- host: N lines` in place of its stdout and
      stderr, OUT.json the whole bytes. BU-2b: the word `T` adds each file's and link's times and links to the tree
      lines (` t ATIME MTIME n LINKS`), for the cases that set them (touch -d, -t, -r; ln).
  check-core.py compare CASES NATIVE ORACLE
      Gate 1: the stdout, tree and status of each case without a DIFF row (`-` or `H`) agree between the two OUT.json
      files, and each case with a row disagrees (a row that no longer differs is stale). A case of an UNORDERED row
      (D-4: a walk in byte order against busybox's directory order) agrees when its output records, each ended by
      '\n' or NUL, are the same once sorted, and its status is the same. Prints each failure; exit 1 on any.
  check-core.py http TREE OUT ARGV...
      CT-5, BU-5a, D-57: fetch over a loopback HTTP/1.0 server serving TREE (its oracle through
      tools/core-fetch-oracle.sh). Each fetch of HTTP_CASES runs as ARGV followed
      by its words (PORT the server's port), in a fresh empty directory; OUT holds for each `$ WORDS`, its stdout's
      length and SHA-256, each file it made with its length and SHA-256, and `status N`. Descriptor 2 is not kept
      (it names the port)."""
import functools
import hashlib
import http.server
import json
import os
import re
import resource
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading

UNORDERED = {"D-4"}
QUOTA = 15360 * 4096   # M-1: a process's RLIMIT_AS under Daphnis (src/uvm.ci MAX_FRAMES), as tools/check-cish.py
T0 = 1000000000        # 2001-09-09 01:46:40 UTC: more than six months past, so ls -l prints the year
DEEP = 260             # past DEPTH_MAX (256)


def load(path):
    out = []
    with open(path, "rb") as f:
        for raw in f.read().decode().split("\n"):
            if not raw.strip() or raw.lstrip().startswith("#"):
                continue
            fields = [x.strip() for x in raw.rsplit("|", 2)]   # CT-3: ARGS may hold | (grep -E a|b)
            if len(fields) != 3:
                sys.exit("check-core.py: %s: not ARGS | STDIN | DIFF: %r" % (path, raw))
            out.append((fields[0], fields[1], fields[2]))
    return out


def quota():
    os.umask(0o022)
    resource.setrlimit(resource.RLIMIT_AS, (QUOTA, QUOTA))


def fixtures(cwd, words):
    """The generated parts named by the case, then the same modes and times on every host."""
    if any(w.split("/")[0] == "many" for w in words):
        os.mkdir(os.path.join(cwd, "many"))
        for i in range(1000):
            open(os.path.join(cwd, "many", "f%03d" % i), "wb").close()
    if any(w.split("/")[0] == "deep" for w in words):
        p = os.path.join(cwd, "deep")
        os.mkdir(p)
        for _ in range(DEEP):
            p = os.path.join(p, "d")
            os.mkdir(p)
        open(os.path.join(p, "f"), "wb").close()
    paths = [cwd]
    for root, dirs, files in os.walk(cwd):
        paths += [os.path.join(root, n) for n in dirs + files]
    paths = sorted(paths, key=lambda q: os.path.relpath(q, cwd).encode())
    for k, q in enumerate(paths):
        os.chmod(q, 0o755 if os.path.isdir(q) or os.stat(q).st_mode & 0o100 else 0o644)
    for k, q in reversed(list(enumerate(paths))):
        os.utime(q, (T0 + 60 * k, T0 + 60 * k))


def entries(root, times=False):
    """Each entry under root: its relative path and `d MODE`, `l TARGET` or `f MODE SIZE SHA256[:16]`; with times
    (BU-2b, the DIFF word T), a link and a file add ` t ATIME MTIME n LINKS` (seconds)."""
    seen = {}
    for top, dirs, files in os.walk(root):
        for name in dirs + files:
            full = os.path.join(top, name)
            rel = os.path.relpath(full, root)
            st = os.lstat(full)
            mode = "%04o" % (st.st_mode & 0o7777)
            extra = " t %d %d n %d" % (st.st_atime, st.st_mtime, st.st_nlink) if times else ""
            if os.path.islink(full):
                seen[rel] = "l " + os.readlink(full) + extra
            elif os.path.isdir(full):
                seen[rel] = "d " + mode
            else:
                locked = not os.access(full, os.R_OK)   # a case's chmod can leave no read bit; root reads it anyway
                if locked:
                    os.chmod(full, (st.st_mode & 0o7777) | 0o400)
                with open(full, "rb") as f:
                    seen[rel] = "f %s %d %s" % (mode, st.st_size, hashlib.sha256(f.read()).hexdigest()[:16]) + extra
                if locked:
                    os.chmod(full, st.st_mode & 0o7777)
                os.utime(full, ns=(st.st_atime_ns, st.st_mtime_ns))   # reading moved the access time: put it back
    return seen


def changes(before, after):
    """The lines of `-- tree`: what a case added, removed and changed, in path order."""
    lines = []
    for rel in sorted(set(before) | set(after)):
        if rel not in after:
            lines.append("- " + rel)
        elif rel not in before:
            lines.append("+ %s %s" % (rel, after[rel]))
        elif before[rel] != after[rel]:
            lines.append("~ %s %s" % (rel, after[rel]))
    return "".join(x + "\n" for x in lines).encode()


def templates(args):
    """The templates a case names (mktemp): each word whose base name ends in XXX, and tmp.XXXXXX."""
    out = {"tmp.XXXXXX"}
    for w in shlex.split(args):
        base = w.rsplit("/", 1)[-1]
        if base.endswith("XXX"):
            out.add(base)
    return out


def mask(data, names):
    """data with each name made from a template written as that template."""
    for t in sorted(names):
        stem = t.rstrip("X")
        data = re.sub(re.escape(stem.encode()) + b"[A-Za-z0-9]{%d}" % (len(t) - len(stem)), t.encode(), data)
    return data


def cases(listing, tree, out, argv):
    text = b""
    data = []
    for args, stdin, diff in load(listing):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = os.path.join(tmp, "t")
            shutil.copytree(tree, cwd)
            fixtures(cwd, shlex.split(args))
            times = "T" in diff.split()
            before = entries(cwd, times)
            feed = b""
            if stdin != "-":
                with open(os.path.join(cwd, stdin), "rb") as f:
                    feed = f.read()
            r = subprocess.run(argv + shlex.split(args), input=feed, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               timeout=60, env={"TZ": "UTC0"}, cwd=cwd, preexec_fn=quota,
                               start_new_session=True)
            names = templates(args)
            moved = mask(changes(before, entries(cwd, times)), names)
        stdout = mask(r.stdout, names)
        stderr = mask(r.stderr, names)
        end = b"signal %d\n" % -r.returncode if r.returncode < 0 else b"status %d\n" % r.returncode
        text += b"$ " + args.encode() + (b" < " + stdin.encode() if stdin != "-" else b"") + b"\n"
        if "H" in diff.split():
            text += b"-- host: %d lines\n" % r.stdout.count(b"\n")
        else:
            text += stdout
            if stderr:
                text += b"-- stderr\n" + stderr
            if moved:
                text += b"-- tree\n" + moved
        text += end
        data.append({"args": args, "diff": diff, "stdout": stdout.hex(), "tree": moved.hex(), "status": r.returncode})
    with open(out, "wb") as f:
        f.write(text)
    with open(out + ".json", "w") as f:
        json.dump(data, f)
    return 0


def records(hexed):
    return sorted(re.findall(rb"[^\n\0]*[\n\0]|[^\n\0]+$", bytes.fromhex(hexed)))


def compare(listing, native, oracle):
    with open(native + ".json") as f:
        a = json.load(f)
    with open(oracle + ".json") as f:
        b = json.load(f)
    if len(a) != len(b) or len(a) != len(load(listing)):
        print("check-core.py: the runs do not hold every case of %s" % listing)
        return 1
    bad = 0
    for x, y in zip(a, b):
        same = x["stdout"] == y["stdout"] and x["tree"] == y["tree"] and x["status"] == y["status"]
        row = [w for w in x["diff"].split() if w not in ("-", "H", "T")]
        if row and row[0] in UNORDERED:
            if records(x["stdout"]) != records(y["stdout"]) or x["status"] != y["status"]:
                print("differs from the oracle, in any order: %s %s" % (os.path.basename(listing), x["args"]))
                bad += 1
        elif not row and not same:
            print("differs from the oracle: %s %s" % (os.path.basename(listing), x["args"]))
            bad += 1
        elif row and same:
            print("stale %s: agrees with the oracle: %s %s" % (x["diff"], os.path.basename(listing), x["args"]))
            bad += 1
    return 1 if bad else 0


HTTP_CASES = [
    "-o - http://127.0.0.1:PORT/text.txt",
    "-o - http://127.0.0.1:PORT/bin.dat",
    "-o - http://127.0.0.1:PORT/long.txt",
    "-o - http://localhost:PORT/empty",
    "http://127.0.0.1:PORT/nonl.txt",
    "-o got http://127.0.0.1:PORT/look/a.txt",
    "-o - http://127.0.0.1:PORT/utf8.txt",
    "http://127.0.0.1:PORT/look/b.txt",
    "-o - http://127.0.0.1:PORT/missing",
]


class Quiet(http.server.SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def log_message(self, *args):
        pass


def fetches(tree, out, argv):
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=tree))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = str(server.server_address[1])
    text = b""
    try:
        for words in HTTP_CASES:
            with tempfile.TemporaryDirectory() as cwd:
                r = subprocess.run(argv + words.replace("PORT", port).split(), stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL, timeout=60, env={"TZ": "UTC0"}, cwd=cwd, preexec_fn=quota,
                               start_new_session=True)
                text += b"$ " + words.encode() + b"\n"
                text += b"stdout %d %s\n" % (len(r.stdout), hashlib.sha256(r.stdout).hexdigest().encode())
                for name in sorted(os.listdir(cwd)):
                    with open(os.path.join(cwd, name), "rb") as f:
                        body = f.read()
                    text += b"file %s %d %s\n" % (name.encode(), len(body), hashlib.sha256(body).hexdigest().encode())
                text += b"status %d\n" % r.returncode
    finally:
        server.shutdown()
    with open(out, "wb") as f:
        f.write(text)
    return 0


def main(argv):
    if len(argv) >= 5 and argv[0] == "cases":
        return cases(argv[1], argv[2], argv[3], argv[4:])
    if len(argv) >= 4 and argv[0] == "http":
        return fetches(argv[1], argv[2], argv[3:])
    if len(argv) == 4 and argv[0] == "compare":
        return compare(argv[1], argv[2], argv[3])
    sys.exit(__doc__)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
