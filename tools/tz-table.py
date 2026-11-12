#!/usr/bin/env python3
"""tools/tz-table.py [--zic PATH] [--zdump PATH]: RS-TZa's table from vendor/tzdata (docs/specs/2026-11-11-rs-tza.md).

Compiles vendor/tzdata/tzdata.zi with `zic -b slim` into a temporary folder, reads the TZif file of each zone in
vendor/tzdata/zone.tab (RFC 8536), and writes:
  user/ci/core/tzdata.ci            the cities by name, each zone's changes after 1970-01-01 and before 2038-01-01,
                                    the type in force at 1970-01-01 00:00:00 UTC, and the rule of its TZ string
  tests/tz/zdump-2026-2027.txt      `zdump -V` lines of every change in 2026 and 2027, every city
  tests/tz/probe-2026-2027.txt      the same form at 00:00:00 UT on January 1 and July 1 of 2026 and 2027, for
                                    each city with no change in those years, from the C library's localtime over
                                    the same compiled files
  tests/tz/zdump-1970-2037.sha256   the SHA-256 and line count of `zdump -V` over every change of 1970 to 2037
Integer data only. Stops on anything the table cannot hold (a TZ rule not of the Mm.w.d form, a name collision)."""
import argparse
import calendar
import hashlib
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import time

CUT = 2145916800                        # 2038-01-01 00:00:00 UTC
Y2026 = 1767225600
Y2028 = 1830297600
PROBES = [calendar.timegm((y, m, 1, 0, 0, 0)) for y in (2026, 2027) for m in (1, 7)]
FULL = (0, CUT)
WDAY = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def tzif(path):
    """(times, type indexes, types as (gmtoff, isdst, abbr), TZ string) of a version 2+ TZif file."""
    b = path.read_bytes()
    if b[:4] != b"TZif" or b[4] < ord("2"):
        sys.exit("%s: not TZif version 2 or later" % path)

    def counts(at):
        return struct.unpack(">6l", b[at + 20:at + 44])
    isutc, isstd, leap, timecnt, typecnt, charcnt = counts(0)
    at = 44 + timecnt * 5 + typecnt * 6 + charcnt + leap * 8 + isstd + isutc
    isutc, isstd, leap, timecnt, typecnt, charcnt = counts(at)
    at += 44
    times = list(struct.unpack(">%dq" % timecnt, b[at:at + 8 * timecnt]))
    at += 8 * timecnt
    idx = list(b[at:at + timecnt])
    at += timecnt
    raw = []
    for _ in range(typecnt):
        raw.append(struct.unpack(">lBB", b[at:at + 6]))
        at += 6
    chars = b[at:at + charcnt]
    at += charcnt + leap * 12 + isstd + isutc
    foot = b[at:].strip(b"\n").decode("ascii")
    types = [(off, dst, chars[ai:chars.index(b"\0", ai)].decode("ascii")) for off, dst, ai in raw]
    return times, idx, types, foot


def hms(s):
    """Seconds of [+-]hh[:mm[:ss]]."""
    sign = -1 if s.startswith("-") else 1
    parts = [int(p) for p in s.lstrip("+-").split(":")]
    parts += [0] * (3 - len(parts))
    return sign * (parts[0] * 3600 + parts[1] * 60 + parts[2])


def posix(foot, where):
    """The TZ string: (std (gmtoff, 0, abbr), dst (gmtoff, 1, abbr) or None, start, end) with each of start and
    end (month, week, weekday, seconds)."""
    s = foot

    def name():
        nonlocal s
        if s.startswith("<"):
            k = s.index(">")
            n, s = s[1:k], s[k + 1:]
        else:
            k = 0
            while k < len(s) and s[k].isalpha():
                k += 1
            n, s = s[:k], s[k:]
        return n

    def offset():
        nonlocal s
        k = 0
        while k < len(s) and (s[k].isdigit() or s[k] in "+-:"):
            k += 1
        o, s = s[:k], s[k:]
        return o
    std_name = name()
    std = (-hms(offset()), 0, std_name)
    if not s:
        return std, None, None, None
    dst_name = name()
    o = ""
    if s and s[0] != ",":
        o = offset()
    dst = (-hms(o) if o else std[0] + 3600, 1, dst_name)
    rules = s.split(",")[1:]
    if len(rules) != 2:
        sys.exit("%s: TZ string %r: no rule" % (where, foot))
    out = []
    for r in rules:
        date, _, t = r.partition("/")
        if not date.startswith("M"):
            sys.exit("%s: TZ string %r: only Mm.w.d rules are held" % (where, foot))
        m, w, d = (int(x) for x in date[1:].split("."))
        out.append((m, w, d, hms(t) if t else 7200))
    return std, dst, out[0], out[1]


def asc(tm):
    return "%s %s %2d %02d:%02d:%02d %d" % (WDAY[tm.tm_wday], MON[tm.tm_mon - 1], tm.tm_mday, tm.tm_hour, tm.tm_min,
                                           tm.tm_sec, tm.tm_year)


def rows(name, values, kind):
    head = "%s[%d] %s = [" % (kind, len(values), name)
    lines, line = [], head
    for k, v in enumerate(values):
        piece = str(v) + (", " if k + 1 < len(values) else "];")
        if len(line) + len(piece.rstrip()) > 119:
            lines.append(line.rstrip())
            line = "    "
        line += piece
    lines.append(line)
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--zic", default="zic")
    parser.add_argument("--zdump", default="zdump")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    zi = repo / "vendor/tzdata/tzdata.zi"
    tab = repo / "vendor/tzdata/zone.tab"
    version = zi.read_text().splitlines()[0].removeprefix("# version ").strip()
    sums = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (zi, tab)}
    zic_version = subprocess.run([args.zic, "--version"], stdout=subprocess.PIPE, text=True).stdout.strip()

    names = [line.split("\t")[2] for line in tab.read_text().splitlines() if line and not line.startswith("#")]
    shown = {n: n.split("/")[-1].replace("_", " ") for n in names}
    if len(set(shown.values())) != len(names):
        sys.exit("zone.tab: two zones show the same city name")
    cities = sorted(names, key=lambda n: (shown[n].lower(), shown[n]))

    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run([args.zic, "-b", "slim", "-d", tmp, str(zi)], check=True)
        types, zones, zone_of, by_data = [], [], [], {}

        def type_of(t):
            if t not in types:
                types.append(t)
            return types.index(t)
        for n in cities:
            times, idx, tys, foot = tzif(Path(tmp) / n)
            before = [i for t, i in zip(times, idx) if t <= 0]
            init = tys[before[-1]] if before else tys[0]
            kept = [(t, tys[i]) for t, i in zip(times, idx) if 0 < t < CUT]
            if any(t >= CUT for t in times):
                start = CUT
            else:
                start = times[-1] if times else -1
            std, dst, r0, r1 = posix(foot, n)
            key = (init, tuple(kept), start, std, dst, r0, r1)
            if key not in by_data:
                by_data[key] = len(zones)
                zones.append(key)
            zone_of.append(by_data[key])
        zone_rows, change_t, change_ty, rule = [0], [], [], []
        init_ty, start_t = [], []
        for init, kept, start, std, dst, r0, r1 in zones:
            init_ty.append(type_of(init))
            for t, ty in kept:
                change_t.append(t)
                change_ty.append(type_of(ty))
            zone_rows.append(len(change_t))
            start_t.append(start)
            if dst is None:
                rule += [type_of(std), -1] + [0] * 8
            else:
                rule += [type_of(std), type_of(dst)] + list(r0) + list(r1)
        if len(types) > 255 or len(change_t) > 65536:
            sys.exit("the table outgrew its arrays: %d types, %d changes" % (len(types), len(change_t)))

        env = dict(os.environ, TZDIR=tmp)

        def zdump(lo, hi):
            out = []
            for n in cities:
                run = subprocess.run([args.zdump, "-V", "-t", "%d,%d" % (lo - 1, hi - 1), n], env=env, check=True,
                                     stdout=subprocess.PIPE, text=True)
                out += run.stdout.splitlines()
            return out
        window = zdump(Y2026, Y2028)
        full = zdump(*FULL)
        probe = []
        changed = {line.split()[0] for line in window}
        for n in cities:
            if n in changed:
                continue
            os.environ["TZ"] = ":" + os.path.join(tmp, n)
            time.tzset()
            for t in PROBES:
                tm = time.localtime(t)
                probe.append("%s  %s UT = %s %s isdst=%d gmtoff=%d" % (n, asc(time.gmtime(t)), asc(tm), tm.tm_zone,
                                                                       tm.tm_isdst, tm.tm_gmtoff))

    def text(strings):
        at, data = [0], []
        for s in strings:
            data += list(s.encode("ascii"))
            at.append(len(data))
        return data, at
    city_text, city_at = text([shown[n] for n in cities])
    name_text, name_at = text(cities)
    abbr_text, abbr_at = text([t[2] for t in types])
    head = f"""\
// user/ci/core/tzdata.ci: RS-TZa's table (docs/specs/2026-11-11-rs-tza.md), written by tools/tz-table.py: do not
// edit. The IANA time zone database {version} (public domain), vendor/tzdata/tzdata.zi sha256
// {sums["tzdata.zi"]} and zone.tab sha256
// {sums["zone.tab"]}, compiled by `zic -b slim`:
// {zic_version}.
// A city is a row of zone.tab, by its shown name; its zone is the data it shares with every city of the same changes.
// A zone: its changes after 1970-01-01 00:00:00 UTC and before CUT (2038-01-01), the type in force at 1970-01-01
// 00:00:00 UTC, and the rule of its TZ string, in force from zone_from on. A type: UTC offset, daylight flag, letters.
// A rule: 10 words a zone (standard type, daylight type or -1, then month, week, weekday and seconds of the start in
// standard time and of the end in daylight time).

export const I64 CITIES = {len(cities)};
export const I64 ZONES = {len(zones)};
export const I64 TYPES = {len(types)};
export const I64 CHANGES = {len(change_t)};
export const I64 CUT = {CUT};

"""
    body = "".join([
        rows("city_text", city_text, "U8"), rows("city_rows", city_at, "U16"),
        rows("name_text", name_text, "U8"), rows("name_rows", name_at, "U16"),
        rows("city_zone", zone_of, "U16"),
        rows("change_t", change_t, "U32"), rows("change_ty", change_ty, "U8"), rows("zone_rows", zone_rows, "U16"),
        rows("zone_init", init_ty, "U8"), rows("zone_start", start_t, "I64"), rows("rules", rule, "I32"),
        rows("type_off", [t[0] for t in types], "I32"), rows("type_dst", [t[1] for t in types], "U8"),
        rows("abbr_text", abbr_text, "U8"), rows("abbr_rows", abbr_at, "U16"),
    ])
    tail = """
export I64 city_at(I64 i) { return city_rows[i] as I64; }
export I64 city_char(I64 k) { return city_text[k] as I64; }
export I64 name_at(I64 i) { return name_rows[i] as I64; }
export I64 name_char(I64 k) { return name_text[k] as I64; }
export I64 zone_of(I64 i) { return city_zone[i] as I64; }
export I64 first(I64 z) { return zone_rows[z] as I64; }
export I64 change(I64 k) { return change_t[k] as I64; }
export I64 change_type(I64 k) { return change_ty[k] as I64; }
export I64 init(I64 z) { return zone_init[z] as I64; }
export I64 from(I64 z) { return zone_start[z]; }
export I64 rule(I64 z, I64 f) { return rules[10 * z + f] as I64; }
export I64 off(I64 ty) { return type_off[ty] as I64; }
export I64 dst(I64 ty) { return type_dst[ty] as I64; }
export I64 abbr_at(I64 ty) { return abbr_rows[ty] as I64; }
export I64 abbr_char(I64 k) { return abbr_text[k] as I64; }
// SPDX-License-Identifier: Apache-2.0
"""
    (repo / "user/ci/core/tzdata.ci").write_text(head + body + tail)
    tests = repo / "tests/tz"
    tests.mkdir(exist_ok=True)
    (tests / "zdump-2026-2027.txt").write_text("\n".join(window) + "\n")
    (tests / "probe-2026-2027.txt").write_text("\n".join(probe) + "\n")
    blob = ("\n".join(full) + "\n").encode("ascii")
    (tests / "zdump-1970-2037.sha256").write_text("%s %d\n" % (hashlib.sha256(blob).hexdigest(), len(full)))
    print("tz-table: %s, %d cities, %d zones, %d types, %d changes; zdump lines %d (2026-2027), %d (1970-2037)" %
          (version, len(cities), len(zones), len(types), len(change_t), len(window), len(full)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
