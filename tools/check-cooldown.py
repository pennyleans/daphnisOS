#!/usr/bin/env python3
"""tools/check-cooldown.py [HDESK [TEST]]: what a closed window takes with it from the approval prompt (PR 412).

After a refused approval prompt with a passphrase, the same window's next ask for ring 0 within 30 s is refused at
once. AC-D4 scopes that to the asking process tree, and a window's tree ends with the window, so a new window that
takes the slot is asked. A yes puts the 5-minute hold on the asking window's tree (pid[kp_win]), so a kernel prompt
whose window closes holds no window: a new window in the slot gets neither the hold nor the cooldown. In
user/ci/hdesk.ci (or HDESK) this check holds the wiring in place:

- cool_win is declared once and written in two places only: kern_answer's refusal (cool_win = kp_win, then
  cool_until) and close_window's clear;
- kern_next refuses at once only for kp_win == cool_win before cool_until;
- kern_next finds the asking window by one match, the first terminal whose process asks, a host (lx_host, RG-1) as
  any other: an app in its own window then has its own record on the prompt and its own cooldown (PR 479);
- close_window clears cool_win after the line that may answer the window's ask (an answer there could set it again)
  and before the slot is freed (kind[i] = NONE);
- kp_win is written by kern_next, by Settings' asks (kp_win = st_win) and by close_window's clear of a kernel
  prompt's window, before the slot is freed, and nowhere else;
- the hold is put by one statement, guarded by kp_win >= 0.

tests/ac/cooldown_test.ci (or TEST) runs these statements hosted; each must be in it as it is in hdesk.ci, the
hold's with tile_kern(P, HOW) for hdeskctl.tile_ask(FBIO_TILE_KERN, P, HOW, ask[0..64]).
"""
import re
import sys

CHECK = "if (kp_win >= 0 && kp_win == cool_win && now_ns() < cool_until) {"
SET = "cool_win = kp_win;"
UNTIL = "cool_until = now_ns() + COOL_NS;"
CLEAR = "if (i == cool_win) { cool_win = -1; }"
NS = "const I64 COOL_NS = 30000000000;"
KWIN = "if (kp_open && !ac_op_up && !deskask.up() && kp_win == i) { kp_win = -1; }"
FIND = "if (kp_win < 0 && kind[i] == TERM && info(i) && vpid[i] == kp_vp) { kp_win = i; }"
HOLD = "if (kp_win >= 0) { st = hdeskctl.tile_ask(FBIO_TILE_KERN, pid[kp_win], 2, ask[0..64]); }"
THOLD = HOLD.replace("hdeskctl.tile_ask(FBIO_TILE_KERN, ", "tile_kern(").replace(", ask[0..64])", ")")
ANSWER = "kern_answer(false);"
FREED = "kind[i] = NONE;"


def code(lines):
    return [l.split("//")[0].strip() for l in lines]


def body(lines, name):
    """The lines of function name, from its head to its closing brace at column 0: (first, last) indexes."""
    for i, l in enumerate(lines):
        if re.match(r"(void|Bool|I64) %s\(" % name, l):
            for j in range(i + 1, len(lines)):
                if lines[j].rstrip() == "}":
                    return i, j
    return None


def check(lines, test):
    bad = []
    c = code(lines)
    if sum(1 for l in c if l == "I64 cool_win = -1;") != 1:
        bad.append("cool_win is not declared once as I64 cool_win = -1")
    if NS not in c:
        bad.append("no %s" % NS)
    where = {}
    for name in ("kern_next", "kern_answer", "close_window"):
        b = body(lines, name)
        if b is None:
            bad.append("no function %s" % name)
        else:
            where[name] = b
    if len(where) < 3:
        return bad

    def inside(n, name):
        return where[name][0] < n < where[name][1]

    for n, l in enumerate(c):
        if re.search(r"\bcool_win\s*=[^=]", l) and l != "I64 cool_win = -1;":
            ok = (l == SET and inside(n, "kern_answer")) or (l == CLEAR and inside(n, "close_window"))
            if not ok:
                bad.append("%d: cool_win written outside kern_answer's refusal and close_window's clear" % (n + 1))
    for n, l in enumerate(c):
        if re.search(r"\bkp_win\s*=[^=]", l) and l != "I64 kp_win = -1;":
            ok = (l in ("kp_win = -1;", FIND) and inside(n, "kern_next")) or l == "kp_win = st_win;"
            ok = ok or (l == KWIN and inside(n, "close_window"))
            if not ok:
                bad.append("%d: kp_win written outside kern_next, Settings' asks and close_window's clear" % (n + 1))
        if "FBIO_TILE_KERN" in l and "kp_win" in l and l != HOLD:
            bad.append("%d: the hold on the asking window is put other than by: %s" % (n + 1, HOLD))
    k0, k1 = where["kern_next"]
    if CHECK not in c[k0:k1]:
        bad.append("kern_next does not refuse at once on: %s" % CHECK)
    if sum(1 for l in c[k0:k1] if l == FIND) != 1:
        bad.append("kern_next does not find the asking window once by: %s" % FIND)
    a0, a1 = where["kern_answer"]
    if sum(1 for n in range(a0, a1) if c[n] == HOLD) != 1:
        bad.append("kern_answer does not put the hold once by: %s" % HOLD)
    sets = [n for n in range(a0, a1) if c[n] == SET]
    if len(sets) != 1 or c[sets[0] + 1] != UNTIL:
        bad.append("kern_answer does not set the cooldown once, %s then %s" % (SET, UNTIL))
    w0, w1 = where["close_window"]
    clears = [n for n in range(w0, w1) if c[n] == CLEAR]
    answers = [n for n in range(w0, w1) if ANSWER in c[n]]
    freed = [n for n in range(w0, w1) if c[n] == FREED]
    if len(clears) != 1:
        bad.append("close_window clears the cooldown %d times, not once: %s" % (len(clears), CLEAR))
    elif answers and clears[0] < max(answers):
        bad.append("%d: close_window clears the cooldown before its answer, which can set it again" % (clears[0] + 1))
    elif not freed or clears[0] > freed[0]:
        bad.append("%d: close_window clears the cooldown after the slot is freed" % (clears[0] + 1))
    kwins = [n for n in range(w0, w1) if c[n] == KWIN]
    if len(kwins) != 1:
        bad.append("close_window clears a kernel prompt's window %d times, not once: %s" % (len(kwins), KWIN))
    elif not freed or kwins[0] > freed[0]:
        bad.append("%d: close_window clears the kernel prompt's window after the slot is freed" % (kwins[0] + 1))
    t = code(test)
    for s in (CHECK, SET, UNTIL, CLEAR, NS, KWIN, THOLD, FIND):
        if s not in t:
            bad.append("the hosted test does not run hdesk.ci's %s" % s)
    return bad


def main(argv):
    path = argv[0] if argv else "user/ci/hdesk.ci"
    tpath = argv[1] if len(argv) > 1 else "tests/ac/cooldown_test.ci"
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().split("\n")
    with open(tpath, encoding="utf-8") as fh:
        test = fh.read().split("\n")
    bad = check(lines, test)
    for b in bad:
        print("%s: %s" % (path, b))
    print("FAIL" if bad else "the cooldown and the kernel prompt's window end with the window")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
# SPDX-License-Identifier: Apache-2.0
