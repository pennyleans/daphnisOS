#!/usr/bin/env python3
"""tools/mkabout.py OUTDIR: the release image's About files (frame 31, DN-53), made from the tree, never literals.

OUTDIR/daphnis, what the desk's About page reads from /etc/daphnis, a line a fact as `KEY VALUE`:
  version   VERSION's first line;
  build     the commit's first 7 hex digits and its date (UTC), "7eb1c92, 2026-11-10": RELEASE_STICK_HEAD and
            SOURCE_DATE_EPOCH when tools/build-release-stick.sh sets them (its archive has no .git), else git's HEAD
            and its commit time; no line when neither is there;
  compiler  "cint" and toolchain.pin's cint_tag without its "v".
OUTDIR/notices.txt, what Licenses opens in Read from /etc/notices.txt: LICENSE, NOTICE and every license or notice
text NOTICE names (a path whose file name holds LICENSE, LICENCE, COPYING, NOTICE or OFL), the rule of
tools/build-release-stick.sh's LICENSES/, each under a line of its path. A named text missing from the tree stops it.

A file is written only when its bytes change, so make rebuilds the image only then. Standard library only."""
import os
import re
import subprocess
import sys
import time


def git(*args):
    try:
        return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def facts():
    with open("VERSION", encoding="utf-8") as f:
        version = f.readline().strip()
    tag = ""
    with open("toolchain.pin", encoding="utf-8") as f:
        for line in f:
            if line.startswith("cint_tag="):
                tag = line.split("=", 1)[1].strip().lstrip("v")
    head = os.environ.get("RELEASE_STICK_HEAD") or git("rev-parse", "--verify", "-q", "HEAD")
    when = os.environ.get("SOURCE_DATE_EPOCH") or (git("log", "-1", "--format=%ct", head) if head else "")
    out = "version %s\n" % version
    if re.fullmatch(r"[0-9a-f]{40}", head) and when.isdigit():
        out += "build %s, %s\n" % (head[:7], time.strftime("%Y-%m-%d", time.gmtime(int(when))))
    if tag:
        out += "compiler cint %s\n" % tag
    return out.encode()


def notices():
    with open("NOTICE", encoding="utf-8") as f:
        named = re.findall(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_./-]+", f.read())
    texts = sorted({p.rstrip(".") for p in named
                    if re.search(r"(LICEN[CS]E|COPYING|NOTICE|OFL)[^/]*$", p.rstrip(".").rsplit("/", 1)[-1])})
    out = []
    for p in ["LICENSE", "NOTICE"] + texts:
        if not os.path.isfile(p):
            raise SystemExit("mkabout.py: NOTICE names %s, which is not in the tree" % p)
        with open(p, "rb") as f:
            body = f.read().replace(b"\r\n", b"\n")
        out.append(b"==> " + p.encode() + b" <==\n\n" + body.rstrip(b"\n") + b"\n")
    return b"\n".join(out)


def put(path, data):
    try:
        with open(path, "rb") as f:
            if f.read() == data:
                return
    except OSError:
        pass
    with open(path, "wb") as f:
        f.write(data)


def main(argv):
    if len(argv) != 1:
        raise SystemExit("usage: tools/mkabout.py OUTDIR")
    os.makedirs(argv[0], exist_ok=True)
    put(os.path.join(argv[0], "daphnis"), facts())
    put(os.path.join(argv[0], "notices.txt"), notices())


if __name__ == "__main__":
    main(sys.argv[1:])
# SPDX-License-Identifier: Apache-2.0
