#!/usr/bin/env python3
"""tools/check-pixel-apps.py [ROOT]: every app of user/ci/kit/apps.ci runs in its own window (apps.WINDOW) exactly
when its program asks a window of the desk (it binds `win_want`, user/ci/tilewin.ci).

RG-1: the desk starts each app in a terminal (hdesk.ci pl_run). For an app in its own window that terminal only
holds the app's process and is never shown (new_term, lx_host); for any other app it is the app's window. A row that
says TERM for a pixel program leaves a terminal on screen beside the app's window (the desk read of 2026-11-12,
board 903f1eb, P1 6); a row that says WINDOW for a terminal program hides the only window it has. This check reads
the app table's records and `runs`, and each program's import graph as tools/check-rows.py does. A program with no
user/ci/NAME.ci is no CINT program and is named, not judged. One line a disagreeing app; then the count; exit
status 1 if any disagrees.
"""
import importlib.util
import os
import re
import sys


def table(root):
    """[(name, program, runs)] in kit/apps.ci's order, and the value of apps.WINDOW."""
    with open(os.path.join(root, "user/ci/kit/apps.ci"), encoding="utf-8") as fh:
        src = fh.read()
    window = int(re.search(r"export const I64 WINDOW = (\d+);", src).group(1))
    runs = [int(x) for x in re.search(r"I64\[\d+\] runs = \[([^\]]*)\];", src).group(1).split(",")]
    text = re.search(r'parse\("((?:[^"\\]|\\.)*)"\);', src).group(1)
    recs = [r.split("|") for r in text.split("\\n") if r]
    if len(recs) != len(runs):
        raise SystemExit("check-pixel-apps: %d records against %d runs in kit/apps.ci" % (len(recs), len(runs)))
    return [(r[0], r[1], runs[i]) for i, r in enumerate(recs)], window


def main(argv):
    root = os.path.abspath(argv[0] if argv else os.path.join(os.path.dirname(__file__), ".."))
    spec = importlib.util.spec_from_file_location("check_rows", os.path.join(root, "tools/check-rows.py"))
    rows = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rows)
    apps, window = table(root)
    fails, pixel, other = [], [], []
    for name, prog, runs in apps:
        if not prog.startswith("/bin/"):
            continue                   # the desk's own (Settings) or listed, not built (Web Browser)
        p = prog[5:]
        if not os.path.exists(os.path.join(root, "user/ci", p + ".ci")):
            other.append(name)
            continue
        asks = "win_want" in rows.rows_of(root, p)
        if asks != (runs == window):
            fails.append(name)
            print("FAIL %s: %s %s a window, and kit/apps.ci runs it %s" % (
                name, p, "asks" if asks else "does not ask",
                "in its own window" if runs == window else "elsewhere (runs %d)" % runs))
        elif asks:
            pixel.append(name)
    if other:
        print("not CINT programs, not judged: %s" % ", ".join(other))
    print("%d apps in their own window, each a program that asks one (%s); %d disagree" % (
        len(pixel), ", ".join(pixel), len(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
# SPDX-License-Identifier: Apache-2.0
