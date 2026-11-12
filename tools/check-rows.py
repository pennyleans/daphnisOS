#!/usr/bin/env python3
"""tools/check-rows.py [ROOT]: every user program has a host row for each extern it binds, within its CI_MAX_ROWS
(PR 412).

user/ci/main.c binds each extern of every module a program imports to a row of user/ci/host.c, into a table of
CI_MAX_ROWS entries. user/ci/host.h sets the cap from the CI_ROWS_ flags user/ci/build.sh gives the program, and
host.c compiles each row only under its flags. A program past its cap cannot start: hdesk at 74d37da2 bound 78 rows
against 72 and exited 2 before its first print, in every boot. Nor can a program with an extern whose row its flags
leave out: cview at 90055086 stopped at start with status 2, "the extern `fd_stat` has no host function", because
kit/setfile.ci called fdctl and build.sh gave CI_ROWS_FD to direct imports only. This check reads the same files:
for each user/ci/*.ci with a main, the flags build.sh gives it (`build.sh --rows`, build.sh's own choice), the cap
those flags select (host.h's #if chain over CI_MAX_ROWS), its rows, the distinct extern names over its import graph
(a service's name, with a '/', is the runtime's), and the rows host.c's table holds under those flags. One line a
program past its cap or missing a row, naming it; then the count of programs and the closest to its cap; exit
status 1 if any fails.
"""
import subprocess
import os
import re
import sys


def rows_of(root, prog):
    """The distinct extern names over prog's import graph."""
    seen, names, todo = set(), set(), ["user.ci." + prog]
    while todo:
        mod = todo.pop()
        if mod in seen:
            continue
        seen.add(mod)
        p = os.path.join(root, mod.replace(".", "/") + ".ci")
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8") as fh:
            for line in fh:
                c = line.split("//")[0]
                m = re.match(r"\s*import\s+([\w.]+)\s*;", c)
                if m:
                    todo.append(m.group(1))
                    continue
                m = re.search(r"\bextern\b[^(]*?\b(\w+)\s*\(", c)
                if m and "/" not in m.group(1):
                    names.add(m.group(1))
    return names


def flags_of(root, progs):
    """build.sh --rows: the CI_ROWS_ flags build.sh gives each program."""
    out = subprocess.run(["bash", os.path.join(root, "user/ci/build.sh"), "--rows"] + progs, cwd=root,
                         capture_output=True, text=True, check=True).stdout
    flags = {}
    for line in out.split("\n"):
        words = line.split()
        if words:
            flags[words[0]] = {w[2:] for w in words[1:] if w.startswith("-DCI_ROWS_")}
    return flags


def table_rows(root):
    """host.c's row table: [(row name, the CI_ROWS_ conditions it sits under)]."""
    with open(os.path.join(root, "user/ci/host.c"), encoding="utf-8") as fh:
        lines = fh.read().split("\n")
    start = lines.index("const ci_row ci_rows[] = {")
    rows, stack = [], []
    for line in lines[start + 1:]:
        if line.startswith("};"):
            return rows
        m = re.match(r"#(ifdef|if)\s+(.*)", line)
        if m:
            cond = "defined(%s)" % m.group(2).strip() if m.group(1) == "ifdef" else m.group(2).strip()
            names = re.findall(r"defined\((\w+)\)", cond)
            if not names or any(not n.startswith("CI_ROWS_") for n in names) or \
                    re.sub(r"defined\(\w+\)|&&|\|\||!|\(|\)|\s", "", cond):
                raise SystemExit("check-rows: host.c's row table has a guard this check does not read: " + line)
            stack.append(cond)
            continue
        if line.startswith("#endif"):
            stack.pop()
            continue
        if line.startswith("#"):
            raise SystemExit("check-rows: host.c's row table has a directive this check does not read: " + line)
        m = re.match(r'\s*\{"(\w+)",', line)
        if m:
            rows.append((m.group(1), list(stack)))
    raise SystemExit("check-rows: host.c's row table has no end")


def cap_chain(root):
    """host.h's #if chain over CI_MAX_ROWS: [(condition or None for #else, cap)]."""
    with open(os.path.join(root, "user/ci/host.h"), encoding="utf-8") as fh:
        lines = fh.read().split("\n")
    chain, cond = [], None
    for line in lines:
        m = re.match(r"#(if|elif)\s+(.*)", line)
        if m:
            cond = m.group(2)
            continue
        if line.startswith("#else"):
            cond = None
            continue
        m = re.match(r"#define CI_MAX_ROWS (\d+)u", line)
        if m:
            chain.append((cond, int(m.group(1))))
    return chain


def holds(cond, flags):
    expr = re.sub(r"defined\((\w+)\)", lambda m: str(m.group(1) in flags), cond)
    expr = expr.replace("&&", " and ").replace("||", " or ").replace("!", " not ")
    return eval(expr, {"__builtins__": {}}, {})


def cap_of(chain, flags):
    for cond, cap in chain:
        if cond is None or holds(cond, flags):
            return cap
    return None


def main(argv):
    root = argv[0] if argv else "."
    chain = cap_chain(root)
    table = table_rows(root)
    progs = []
    for f in sorted(os.listdir(os.path.join(root, "user/ci"))):
        p = os.path.join(root, "user/ci", f)
        if not f.endswith(".ci") or not os.path.isfile(p):
            continue
        with open(p, encoding="utf-8") as fh:
            if not re.search(r"^(export )?(void|I64) main\(", fh.read(), re.M):
                continue
        progs.append(f[:-3])
    given = flags_of(root, progs)
    bad, near = [], None
    for prog in progs:
        flags = given[prog]
        cap = cap_of(chain, flags)
        names = rows_of(root, prog)
        have = {name for name, conds in table if all(holds(c, flags) for c in conds)}
        for name in sorted(names - have):
            bad.append("%s: the extern `%s` has no row in user/ci/host.c under its flags (%s); it stops at start"
                       % (prog, name, " ".join(sorted(flags)) or "none"))
        n = len(names)
        if cap is None or n > cap:
            bad.append("%s binds %d host rows, past its CI_MAX_ROWS %s (user/ci/host.h, flags %s)"
                       % (prog, n, cap, " ".join(sorted(flags)) or "none"))
        elif near is None or cap - n < near[2] - near[1]:
            near = (prog, n, cap)
    for b in bad:
        print("FAIL", b)
    if bad:
        print("FAIL: %d failures over %d programs" % (len(bad), len(progs)))
        return 1
    print("%d programs have a host row for each extern and bind within CI_MAX_ROWS; the closest, %s, %d of %d"
          % (len(progs), near[0], near[1], near[2]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
# SPDX-License-Identifier: Apache-2.0
