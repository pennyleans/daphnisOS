#!/usr/bin/env python3
"""check-approved-words.py TSV (--bin DIR | --image FILE): the approved words are in what ships (RG-1).

TSV rows: program<TAB>word<TAB>approved where (lines starting with # are notes). With --bin DIR each word must be
in the bytes of DIR/program (O/ubin, built from the commit the release image is built from). With --image FILE each word
must be somewhere in the image's bytes (the initrd is stored whole, so a word is not split). The complement of
tools/check-stale-design.py: that one fails on retired words, this one fails when an approved word is absent.
The app order of note 71 is checked too: the app table's rows must stand in the TSV's order.
Exit 0 all present, 1 any absent.
Written by the design thread for RG-1 (its audit of batch/l-3 90055086); check-release.sh runs it with --image on the
stick's initrd, and tests/release/ holds its TSVs.
"""
import os, sys


def main(argv):
    if len(argv) != 3 or argv[1] not in ("--bin", "--image"):
        print("usage: check-approved-words.py TSV (--bin DIR | --image FILE)")
        return 2
    rows = [l.rstrip("\n").split("\t") for l in open(argv[0]) if l.strip() and not l.startswith("#")]
    data = {}

    def blob(prog):
        key = prog if argv[1] == "--bin" else ""
        if key not in data:
            p = os.path.join(argv[2], prog) if argv[1] == "--bin" else argv[2]
            data[key] = open(p, "rb").read() if os.path.isfile(p) else None
        return data[key]

    bad, order = 0, []
    for prog, word, where in (r[:3] for r in rows):
        b = blob(prog)
        if b is None:
            print("ABSENT PROGRAM  %s (for %r, %s)" % (prog, word, where)); bad += 1; continue
        at = b.find(word.encode())
        if at < 0:
            print("ABSENT  %-8s %r (%s)" % (prog, word, where)); bad += 1
        elif "|/bin/" in word:
            order.append((at, word))
    if order != sorted(order):
        print("ORDER  the app table is not in the approved order: " + ", ".join(w.split("|")[0] for _, w in sorted(order)))
        bad += 1
    if bad:
        print("FAIL: %d approved word(s) or rule(s) not met" % bad)
        return 1
    print("all %d approved words are present" % len(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
