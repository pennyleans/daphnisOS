#!/usr/bin/env python3
"""tools/check-prompt-title.py [FILE]: the approval prompt's title has one writer (AC-T, plan call AC-R1).

The title of frame 17 names the window that asks. It was the window's comm, text a program sets (prctl
PR_SET_NAME), so a program could make the prompt read another program's name. In user/ci/hdesk.ci (or FILE) this
check holds the wiring of docs/specs/2026-11-11-ac-t-prompt-title.md section 5 in place:

- kp_title is written by its zeroing loop and by one call, prompttitle.title(lx_app[kp_win] - 1, ask[0..64],
  kp_title), and by nothing else; no byte of a FBIO_TILE_INFO record is copied into it; AC-T2 (edition 3): the
  record it reads is kind 13's for pid[kp_win], the image the window's first process runs, read on the line
  before the call, or all zero when the kernel gives none; the comm (kinds 0 and 1) is not read for it;
- lx_app is set in one place, to prompttitle.record(cmd) for the line pl_run has just typed (0 unless that line
  can only start an app's program), and cleared to 0 where a window slot is opened as a terminal and where it is
  closed;
- every read of kp_title is a draw loop bounded at 16.
"""
import re
import sys

CALL = "prompttitle.title(lx_app[kp_win] - 1, ask[0..64], kp_title)"
READ = "if (hdeskctl.tile_ask(FBIO_TILE_INFO, 13, pid[kp_win], ask[0..64]) != 0) { for k in 0..64 { ask[k] = 0; } }"
SET = "lx_app[t] = prompttitle.record(cmd);"
TYPED = "I64 put = ptyctl.pty_write(master[t], c[0..cn]);"


def check(lines):
    bad = []
    code = [(n + 1, l.split("//")[0]) for n, l in enumerate(lines)]
    decl = [n for n, l in code if re.match(r"\s*U8\[16\] kp_title;", l)]
    if len(decl) != 1:
        bad.append("kp_title is not declared once as U8[16]")
    calls = 0
    for i, (n, l) in enumerate(code):
        if "kp_title" not in l or n in decl:
            continue
        if re.search(r"kp_title\[[^\]]*\]\s*=[^=]", l):
            if not re.fullmatch(r"\s*for k in 0\.\.16 \{ kp_title\[k\] = 0; \}\s*", l):
                bad.append("%d: kp_title written outside its zeroing loop" % n)
        elif CALL in l:
            calls += 1
            if code[i - 1][1].strip() != READ:
                bad.append("%d: the title is not read from kind 13's record of pid[kp_win] on the line before" % n)
        elif re.search(r"kp_title\[n\]", l):
            if "n < 16" not in l and "t[n] = kp_title[n];" not in l:
                bad.append("%d: kp_title read outside a draw loop bounded at 16" % n)
        else:
            bad.append("%d: kp_title used in a way this check does not know" % n)
    if calls != 1:
        bad.append("prompttitle.title writes kp_title %d times, not once: %s" % (calls, CALL))
    sets = []
    clears = 0
    for i, (n, l) in enumerate(code):
        m = re.search(r"lx_app\[[^\]]*\]\s*=[^=]\s*(.*?);", l)
        if not m:
            continue
        if m.group(1).strip() == "0":
            clears += 1
        else:
            sets.append(n)
            near = "".join(c for _, c in code[max(0, i - 6):i])
            if l.strip() != SET or TYPED not in near:
                bad.append("%d: lx_app set to other than the record of the line pl_run typed" % n)
    if len(sets) != 1:
        bad.append("lx_app is set %d times, not once: %s" % (len(sets), SET))
    if clears < 2:
        bad.append("lx_app is cleared %d times; a new terminal and a closed window both clear it" % clears)
    return bad


def main(argv):
    path = argv[0] if argv else "user/ci/hdesk.ci"
    with open(path, encoding="utf-8") as fh:
        bad = check(fh.read().split("\n"))
    for b in bad:
        print("%s: %s" % (path, b))
    print("FAIL" if bad else "the prompt's title has one writer, the desk's own record")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
