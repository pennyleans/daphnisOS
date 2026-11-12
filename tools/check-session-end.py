#!/usr/bin/env python3
"""tools/check-session-end.py [HDESK [TEST]]: what a session leaves on the desk's overlay ends with it.

The asks live on the desk's overlay, not in a window, so closing the windows does not end them. Frame 23's Empty
Trash ask, left up across a logout, emptied the next account's Trash (a run as it) under the last account's count,
and the Storage page showed the last account's folder sizes until the next walk. AM section 7's unsaved ask, left
up, took the next account's keys and its GO ended the machine with no scan of that account's windows. In
user/ci/hdesk.ci (or HDESK) this check holds the wiring in place (PR 412):

- logout() and lock_now() close the Empty Trash ask when it is up; logout() closes the unsaved ask, and lock_now()
  does not (the same account comes back to it);
- logout() and start_session() forget the page's facts by st_storage_forget(), whose body sets st_trash_n and the
  page's count to 0 and gives the page an empty walk (homeuse cleared, then walk_started and walk_done: no row), and
  nothing else;
- st_trash_n and the page's count are written there and by rn_take's count alone; the ask is raised once, by
  st_act, only for a count above 0.

tests/rs/sessionend_test.ci (or TEST) runs these statements hosted; each must be in it as it is in hdesk.ci.
"""
import re
import sys

CLOSE = "if (indextrash.is_up()) { indextrash.close(); }"
FORGET = "st_storage_forget();"
BODY = ["st_trash_n = 0;", "ststore.set_trash_entries(0);", 'homeuse.start(b"", 0);', "ststore.walk_started();",
        "ststore.walk_done();"]
COUNT = ["ststore.set_trash_entries(c);", "st_trash_n = c;"]
GATE = "if (p == stside.STORAGE && a == ststore.EMPTY && st_trash_n > 0) {"
ASK = 'indextrash.ask(indextrash.EMPTY_TRASH, st_trash_n, b"");'
ROUTE = ["if (indextrash.is_up() && !kp_open) {", "if (value == 1) { et_answer(indextrash.key(code)); }",
         "if (unsaved.is_up() && !kp_open) {", "if (value == 1) { uv_answer(unsaved.key(code)); }"]
UVCLOSE = "if (unsaved.is_up()) { unsaved.close(); }"


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
    where = {}
    for name in ("logout", "lock_now", "start_session", "st_storage_forget", "rn_take", "st_act"):
        b = body(lines, name)
        if b is None:
            bad.append("no function %s" % name)
        else:
            where[name] = b
    if len(where) < 6:
        return bad

    def lines_of(name):
        return c[where[name][0] + 1:where[name][1]]

    for name in ("logout", "lock_now"):
        if lines_of(name).count(CLOSE) != 1:
            bad.append("%s does not close the Empty Trash ask once: %s" % (name, CLOSE))
    if lines_of("logout").count(UVCLOSE) != 1:
        bad.append("logout does not close the unsaved ask once: %s" % UVCLOSE)
    if any("unsaved.close()" in l for l in lines_of("lock_now")):
        bad.append("lock_now closes the unsaved ask; the same account comes back to it")
    for name in ("logout", "start_session"):
        if lines_of(name).count(FORGET) != 1:
            bad.append("%s does not forget the Storage page's facts once: %s" % (name, FORGET))
    if [l for l in lines_of("st_storage_forget") if l] != BODY:
        bad.append("st_storage_forget is not exactly: %s" % " ".join(BODY))
    take = lines_of("rn_take")
    k = [i for i, l in enumerate(take) if l == COUNT[0]]
    if len(k) != 1 or take[k[0] + 1] != COUNT[1]:
        bad.append("rn_take does not set the count once, %s then %s" % tuple(COUNT))
    act = lines_of("st_act")
    g = [i for i, l in enumerate(act) if l == GATE]
    if len(g) != 1 or act[g[0] + 1] != ASK:
        bad.append("st_act does not raise the ask once, on %s" % GATE)
    inside = {n: range(where[n][0] + 1, where[n][1]) for n in where}
    for n, l in enumerate(c):
        if re.search(r"\bst_trash_n\s*=[^=]", l) and l != "I64 st_trash_n = 0;":
            if not ((l == BODY[0] and n in inside["st_storage_forget"]) or (l == COUNT[1] and n in inside["rn_take"])):
                bad.append("%d: st_trash_n written outside st_storage_forget and rn_take's count" % (n + 1))
        if "ststore.set_trash_entries(" in l:
            if not ((l == BODY[1] and n in inside["st_storage_forget"]) or (l == COUNT[0] and n in inside["rn_take"])):
                bad.append("%d: the page's count set outside st_storage_forget and rn_take's count" % (n + 1))
        if "indextrash.ask(" in l and not (l == ASK and n in inside["st_act"]):
            bad.append("%d: the Empty Trash ask raised outside st_act" % (n + 1))
    t = code(test)
    for s in [CLOSE, UVCLOSE, FORGET, GATE, ASK] + BODY + COUNT + ROUTE:
        if s not in t:
            bad.append("the hosted test does not run hdesk.ci's %s" % s)
    for s in ROUTE:
        if s not in c:
            bad.append("hdesk.ci's route no longer reads: %s" % s)
    return bad


def main(argv):
    path = argv[0] if argv else "user/ci/hdesk.ci"
    tpath = argv[1] if len(argv) > 1 else "tests/rs/sessionend_test.ci"
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().split("\n")
    with open(tpath, encoding="utf-8") as fh:
        test = fh.read().split("\n")
    bad = check(lines, test)
    for b in bad:
        print("%s: %s" % (path, b))
    print("FAIL" if bad else "the Empty Trash and unsaved asks and the Storage page's facts end with the session")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
# SPDX-License-Identifier: Apache-2.0
