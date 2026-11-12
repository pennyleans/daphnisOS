#!/usr/bin/env python3
"""Run the production account reader against scripted filesystem outcomes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--cint", default="cint")
    parser.add_argument("--toolchain", default=os.environ.get("CINT_TOOLCHAIN"), required=False)
    args = parser.parse_args()
    if not args.toolchain:
        parser.error("--toolchain or CINT_TOOLCHAIN is required")
    repo = Path(__file__).resolve().parents[1]
    out = args.out.resolve()
    if out == repo or repo in out.parents:
        parser.error("--out must be outside the repository")
    out.mkdir(parents=True, exist_ok=False)
    root = out / "root"
    copies = {
        "user/ci/acct.ci": "user/ci/acct.ci",
        "user/ci/acctio.ci": "user/ci/acctio.ci",
        "tests/ac/store_shctl.ci": "user/ci/shctl.ci",
        "tests/ac/store_test.ci": "tests/ac/store_test.ci",
    }
    hashes = {source: digest(repo / source) for source in copies}
    for source, target in copies.items():
        dest = root / target
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(repo / source, dest)
    compiler = Path(shutil.which(args.cint) or args.cint).resolve()
    descriptor = Path(args.toolchain).resolve()
    command = [str(compiler), "test", "--toolchain", str(descriptor),
               "--cache", str(out / "cache"), "--root", str(root),
               "tests/ac/store_test.ci"]
    result = subprocess.run(command, cwd=root, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True)
    (out / "test.log").write_text(result.stdout)
    changed = [source for source, value in hashes.items() if digest(repo / source) != value]
    receipt = {
        "command": command, "exit": result.returncode,
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip(),
        "status": subprocess.check_output(["git", "status", "--porcelain"], cwd=repo, text=True),
        "source_sha256": hashes, "changed_during_test": changed,
        "compiler_sha256": digest(compiler), "toolchain_sha256": digest(descriptor),
        "scope": "production reader and parser; scripted shctl IO, not guest filesystem qualification",
    }
    (out / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(result.stdout, end="")
    if changed:
        print("source changed during the test: " + ", ".join(changed), file=sys.stderr)
        return 1
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
