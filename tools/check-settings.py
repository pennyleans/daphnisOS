#!/usr/bin/env python3
"""tools/check-settings.py --out DIR [--toolchain FILE]: U-SET's file tests (docs/specs/2026-11-11-u-set.md).

Copies user/ci/kit/settings.ci, setfile.ci and indexpick.ci as they are, with tests/set/fs_shctl.ci, fs_corectl.ci
and fs_fdctl.ci over user/ci/shctl.ci, corectl.ci and fdctl.ci, into DIR/root (outside the repository), and runs
`cint test` there on tests/set/setfile_test.ci and indexpick_test.ci (Choose Picture's write): the real modules over
a volume in memory, not the guest's filesystem. The last line counts the tests of both."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

COPIES = {
    "user/ci/kit/settings.ci": "user/ci/kit/settings.ci",
    "user/ci/kit/setfile.ci": "user/ci/kit/setfile.ci",
    "tests/set/fs_shctl.ci": "user/ci/shctl.ci",
    "tests/set/fs_corectl.ci": "user/ci/corectl.ci",
    "tests/set/fs_fdctl.ci": "user/ci/fdctl.ci",
    "tests/set/setfile_test.ci": "tests/set/setfile_test.ci",
    "user/ci/kit/indexpick.ci": "user/ci/kit/indexpick.ci",
    "tests/set/indexpick_test.ci": "tests/set/indexpick_test.ci",
}
TESTS = ["tests/set/setfile_test.ci", "tests/set/indexpick_test.ci"]


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
    for source, target in COPIES.items():
        dest = root / target
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(repo / source, dest)
    code = 0
    passed = 0
    total = 0
    for test in TESTS:
        command = [args.cint, "test", "--toolchain", str(Path(args.toolchain).resolve()), "--cache",
                   str(out / "cache"), "--root", str(root), test]
        result = subprocess.run(command, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        print(result.stdout, end="")
        code = code or result.returncode
        last = result.stdout.strip().splitlines()[-1:] or [""]
        words = last[0].split()
        if len(words) == 5 and words[1] == "of" and words[3:] == ["tests", "passed"]:
            passed += int(words[0])
            total += int(words[2])
        else:
            code = code or 1
    print(f"{passed} of {total} tests passed")
    return code


if __name__ == "__main__":
    sys.exit(main())
