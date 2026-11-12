#!/usr/bin/env python3
"""tools/check-tz.py TWIN_OUTPUT: RS-TZa's hosted check (docs/specs/2026-11-11-rs-tza.md section 4).

Renders each line of tests/tz/tz_twin.ci in zdump's form and compares:
  zdump-2026-2027  with tests/tz/zdump-2026-2027.txt, line for line (zdump -V, every change of 2026 and 2027)
  probe-2026-2027  with tests/tz/probe-2026-2027.txt, line for line (localtime at four instants, cities with no change)
  zdump-1970-2037  with tests/tz/zdump-1970-2037.sha256 (SHA-256 and line count of zdump -V over 1970 to 2037)
  inverse-1970-2037  RS-TZc's utc_of against the inverse of zdump's own lines (the part above, once it agrees, and the
                   probe part for a city with no change): the earliest t whose stretch of one offset holds l - offset,
                   so a repeated local time takes the offset before the change; none is a skipped one ("gap")
and that vendor/tzdata's files have the SHA-256s that vendor/tzdata/SOURCE.json and user/ci/core/tzdata.ci name (the
LICENSE beside them, the one SOURCE.json names).

zone-path (RS-TZc, TZ-R1 A): the path user/ci/core/zonefile.ci opens passes the kernel's own AC-1c rule (src/fs.ci's
walk refuses the volume root's account directory to an account session), read from the kernel's source, so every
session reads the zone file; and the volume root is uid 0's, 0755, in tools/mkdisk.sh, so only uid 0 writes it."""
import calendar
import hashlib
import json
from pathlib import Path
import re
import sys

WDAY = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def asc(f):
    y, mo, d, h, mi, s, wd = f
    return "%s %s %2d %02d:%02d:%02d %d" % (WDAY[wd], MON[mo - 1], d, h, mi, s, y)


def utc_of(changes, l):
    """The earliest t whose stretch of one offset holds t = l - offset; None for a skipped local time. changes: the
    (u, o1, o2) of each change in order, o1 the offset before u and o2 from u."""
    edges = [None] + [u for u, _, _ in changes] + [None]
    offs = [changes[0][1]] + [o2 for _, _, o2 in changes]
    for k, o in enumerate(offs):
        t = l - o
        if (edges[k] is None or t >= edges[k]) and (edges[k + 1] is None or t < edges[k + 1]):
            return t
    return None


def inverse(lines, got):
    """RS-TZc: each I line against the inverse of the zdump part's lines (pairs: the second before a change and the
    second of it) and, for a city with no change, the probe part's offset."""
    changes, still = {}, {}
    pairs = lines.get("zdump-1970-2037", [])
    for k in range(0, len(pairs) - 1, 2):
        (i, t0, o1), (j, t1, o2) = pairs[k], pairs[k + 1]
        if i != j or t1 != t0 + 1:
            print("check-tz: inverse-1970-2037: the zdump part is not in pairs at line %d" % k)
            return 1
        changes.setdefault(i, []).append((t1, o1, o2))
    for i, _, o in lines.get("probe-2026-2027", []):
        still.setdefault(i, o)
    want = []
    for i in sorted(set(changes) | set(still)):
        if i not in changes:
            want.append((i, 1767225600, str(1767225600 - still[i])))
            continue
        for u, o1, o2 in changes[i]:
            for l in (u + o1 - 1, u + o1, u + o2 - 1, u + o2):
                t = utc_of(changes[i], l)
                want.append((i, l, "gap" if t is None else str(t)))
    bad = [k for k in range(max(len(want), len(got))) if k >= len(want) or k >= len(got) or want[k] != got[k]]
    gaps = sum(1 for w in want if w[2] == "gap")
    print("check-tz: inverse-1970-2037: %d local times, %d skipped, %d differ" % (len(want), gaps, len(bad)))
    for k in bad[:5]:
        print("  want: %r\n  got:  %r" % (want[k] if k < len(want) else "-", got[k] if k < len(got) else "-"))
    return 1 if bad else 0


def zone_path(repo):
    """The zone file's path against src/fs.ci's AC-1c rule: 0 when an account session may open it, else 1."""
    fs = (repo / "src/fs.ci").read_text()
    rule = re.search(r"xd == ext2\.ROOT_INO && k == (\d+) && acct_name\(c\) && puid\[pid\] != 0", fs)
    want = re.search(r"Bool acct_name\(in U8\[_\] c\) \{\s*U8\[(\d+)\] want = \[([0-9, ]+)\];", fs)
    opened = re.findall(r'sh_open\(b"([^"]+)"', (repo / "user/ci/core/zonefile.ci").read_text())
    disk = (repo / "tools/mkdisk.sh").read_text()
    root = "root_owner=0:0" in disk and 'find "$stage" -type d -exec chmod 0755 {} +' in disk
    if not rule or not want or len(opened) != 1:
        print("check-tz: zone-path: the AC-1c rule, acct_name or the zone file's one path not found")
        return 1
    name = bytes(int(v) for v in want.group(2).split(","))
    k = int(rule.group(1))

    def refused(path):
        parts = path.split("/")
        if parts[:2] != ["", "home"] or len(parts) < 3:
            return True                # off the volume: not the account session's to read
        c = parts[2].encode("ascii")
        return len(c) == k and c[:len(name)] == name
    ok = not refused(opened[0]) and refused("/home/.daphnis/zone") and root
    print("check-tz: zone-path: %s %s (AC-1c refuses /home/%s to an account session; volume root uid 0, 0755)" %
          (opened[0], "is read by every session" if ok else "IS NOT READ BY AN ACCOUNT SESSION", name.decode()))
    return 0 if ok else 1


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    repo = Path(__file__).resolve().parents[1]
    names, parts, part, part_name, lines = {}, {}, None, None, {}
    for raw in Path(sys.argv[1]).read_text().splitlines():
        w = raw.split()
        if w[0] == "N":
            names[int(w[1])] = bytes.fromhex(w[2]).decode("ascii")
        elif w[0] == "W":
            part = parts.setdefault(w[1], [])
            part.clear()
            part_name = w[1]
        elif w[0] == "I":
            part.append((int(w[1]), int(w[2]), w[3]))
        elif w[0] == "L":
            v = [int(x) for x in w[1:18]]
            part.append("%s  %s UT = %s %s isdst=%d gmtoff=%d" % (
                names[v[0]], asc(v[1:8]), asc(v[8:15]), bytes.fromhex(w[18]).decode("ascii"), v[15], v[16]))
            lines.setdefault(part_name, []).append((v[0], calendar.timegm(tuple(v[1:7])), v[16]))
        else:
            sys.exit("check-tz: line not understood: %r" % raw)
    failed = 0
    for name in ("zdump-2026-2027", "probe-2026-2027"):
        want = (repo / "tests/tz" / (name + ".txt")).read_text().splitlines()
        got = parts.get(name, [])
        bad = [k for k in range(max(len(want), len(got))) if k >= len(want) or k >= len(got) or want[k] != got[k]]
        print("check-tz: %s: %d lines, %d differ" % (name, len(want), len(bad)))
        for k in bad[:5]:
            print("  want: %s\n  got:  %s" % (want[k] if k < len(want) else "-", got[k] if k < len(got) else "-"))
        failed += 1 if bad else 0
    digest, count = (repo / "tests/tz/zdump-1970-2037.sha256").read_text().split()
    full = parts.get("zdump-1970-2037", [])
    mine = hashlib.sha256(("\n".join(full) + "\n").encode("ascii")).hexdigest()
    same = mine == digest and len(full) == int(count)
    print("check-tz: zdump-1970-2037: %d lines (want %s), SHA-256 %s" % (len(full), count, "agrees" if same else
                                                                          "DIFFERS: " + mine))
    failed += 0 if same else 1
    failed += inverse(lines, parts.get("inverse-1970-2037", []))
    source = json.loads((repo / "vendor/tzdata/SOURCE.json").read_text())
    head = (repo / "user/ci/core/tzdata.ci").read_text()[:1200]
    for f, want in source["sha256"].items():
        have = hashlib.sha256((repo / "vendor/tzdata" / f).read_bytes()).hexdigest()
        ok = have == want and want in head
        print("check-tz: vendor/tzdata/%s sha256 %s" % (f, "agrees with SOURCE.json and the table" if ok else
                                                         "DIFFERS: " + have))
        failed += 0 if ok else 1
    lic = source["license_file"]
    have = hashlib.sha256((repo / "vendor/tzdata" / lic["file"]).read_bytes()).hexdigest()
    print("check-tz: vendor/tzdata/%s sha256 %s" % (lic["file"], "agrees with SOURCE.json" if have == lic["sha256"]
                                                     else "DIFFERS: " + have))
    failed += 0 if have == lic["sha256"] else 1
    failed += zone_path(repo)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
