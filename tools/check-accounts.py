#!/usr/bin/env python3
"""tools/check-accounts.py TRANSCRIPT MARK...: AC-1c's check (docs/specs/2026-11-08-ac-accounts.md section 6).

Each MARK is the start of a line the desk prints; they must come in the transcript in this order, each after the one
before. A MARK beginning with `!` must not appear anywhere (a passphrase, for one). Prints PASS or FAIL with the first
mark missing, and exits 1 on FAIL.
"""
import sys


def main(argv):
    lines = open(argv[0], encoding="ascii", errors="replace").read().split("\n")
    at = 0
    for mark in argv[1:]:
        if mark.startswith("!"):
            bad = mark[1:]
            if any(bad in ln for ln in lines):
                print("FAIL: found", repr(bad))
                return 1
            continue
        while at < len(lines) and not lines[at].startswith(mark):
            at += 1
        if at == len(lines):
            print("FAIL: no line", repr(mark), "in order")
            return 1
        at += 1
    print("PASS:", len(argv) - 1, "marks")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
