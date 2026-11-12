#!/usr/bin/env python3
"""Run authd's store operations (RS-ROLE, RS-R3, RS-R4) as they are over a volume in memory.

tests/ac/authop_test.ci runs in an isolated root where tests/ac/vol_shctl.ci and vol_corectl.ci stand in for the
call rows; every other module is the tree's own. Prints cint test's lines; exit status 1 if a test fails or a source
changes during the run.
"""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys

COPIES = {
    "user/ci/acct.ci": "user/ci/acct.ci",
    "user/ci/acctio.ci": "user/ci/acctio.ci",
    "user/ci/acctput.ci": "user/ci/acctput.ci",
    "user/ci/argon2.ci": "user/ci/argon2.ci",
    "user/ci/authop.ci": "user/ci/authop.ci",
    "user/ci/authreq.ci": "user/ci/authreq.ci",
    "user/ci/authver.ci": "user/ci/authver.ci",
    "user/ci/blake2b.ci": "user/ci/blake2b.ci",
    "user/ci/homeaside.ci": "user/ci/homeaside.ci",
    "tests/ac/vol_shctl.ci": "user/ci/shctl.ci",
    "tests/ac/vol_corectl.ci": "user/ci/corectl.ci",
    "tests/ac/authop_test.ci": "tests/ac/authop_test.ci",
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--cint", default="cint")
    parser.add_argument("--toolchain", default=os.environ.get("CINT_TOOLCHAIN"))
    args = parser.parse_args()
    if not args.toolchain:
        parser.error("--toolchain or CINT_TOOLCHAIN is required")
    repo = Path(__file__).resolve().parents[1]
    out = args.out.resolve()
    if out == repo or repo in out.parents:
        parser.error("--out must be outside the repository")
    out.mkdir(parents=True, exist_ok=False)
    root = out / "root"
    hashes = {source: digest(repo / source) for source in COPIES}
    for source, target in COPIES.items():
        dest = root / target
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(repo / source, dest)
    command = [args.cint, "test", "--toolchain", str(Path(args.toolchain).resolve()),
               "--cache", str(out / "cache"), "--root", str(root), "tests/ac/authop_test.ci"]
    result = subprocess.run(command, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    print(result.stdout, end="")
    changed = [source for source, value in hashes.items() if digest(repo / source) != value]
    if changed:
        print("source changed during the test: " + ", ".join(changed), file=sys.stderr)
        return 1
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
