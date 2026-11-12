#!/usr/bin/env python3
"""tools/check-release.py: the checks of check-release.sh, the release image gate (RG-1: l 2026-11-12 07:53Z, "make
sure this mistake never happens again"; the release image is the app list, and no test adds a program to it).

tools/check-release.py --static INITRD RECIPE SRC: the release initrd as it stands on the stick; SRC is the tree it is
built from (APPS below is SRC/user/ci/kit/apps.ci).
  recipe   its members, in order, are the ones the Makefile's recipe names (RECIPE holds `make -n`'s mkcpio line):
           nothing added, nothing left out
  apps     every app of APPS (user/ci/kit/apps.ci) that names a program has it as a member: an ELF file
  doom     no Doom (DOOM-1, l 07:59Z): no member doom, tables.bin, info.bin or *.wad, and no Doom row in APPS
  names    every "/bin/NAME" the image's programs name in their source (each one's import closure) is a member

tools/check-release.py --drive MONITOR TRANSCRIPT APPS RUN: types into the desk through QEMU's monitor, as a person
  would: the first boot's parent account; then each app of APPS that names a program, from the Super plane (a Super
  tap, the app's name, its row, Enter), with a screendump under RUN once it is up, and Super+Q; Print; Super+Shift+Q
  twice. One line an app:
  window   Index, View and Monitor (WINDOW in APPS) bind a pixel window
  stays    the others' terminal is still up after SETTLE seconds (the shell found and ran the program)
  closes   Super+Q ends an app's terminal with the app (DN-60, kit/launch.ci: an app takes the shell's place)
  `hdesk: launch none` (the program is not in /bin) fails the app at once.

tools/check-release.py --after TRANSCRIPT INITRD VOLUME NAME: the transcript of the whole run and the volume QEMU left.
  network  the boot leases an address over DHCP and the gateway answers
  image    the loader's module is INITRD's bytes, by size
  keys     no key was dropped (`daphnis: input dropped`), so every line the gate typed is what the desk read
  shot     Print wrote a PNG into NAME's Pictures

tools/check-release.py --ledger LEDGER INITRD ESP VOLUME APPS TRANSCRIPT GATE DECISIONS: docs/release/0.1.0/LEDGER.tsv
  against the image (ESP: `mdir -/ -b` of the stick's ESP; GATE: this gate's PASS and FAIL lines so far).
  form     every row has six fields, a unique id and a known state; every DEFERRED row carries l's word and time
           and no IN row rests on member or nomember artifacts alone
  cover    every app of APPS and every DN ruling of DECISIONS is named by a row
  in       every artifact of every IN and DEFERRED row holds in the image (the grammar is in LEDGER's header); a
           module artifact holds only when the program that ships as its member imports it, directly or through
           others, a source artifact only when TEXT is in the code (not a // comment) of that program's import
           closure, and nosource only when it is not (SRC, the tree the image is built from, is APPS's tree:
           APPS is SRC/user/ci/kit/apps.ci)
           bar NAME holds when the booted desk's transcript has `hdesk: bar desktop N |NAME|`, and bars apps when
           it has one for each app of APPS that names a program and is no command, by the app's name (DN-60 B: a
           command, Fetch, keeps its Console, so its window is Console's)
  open     no row is MISSING or PARTIAL

tools/check-release.py --count APPS: how many apps of APPS name a program (check-release.sh's fixed count).

One PASS or FAIL line a check; exits 1 on any FAIL."""
import os
import re
import shlex
import socket
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import guestlines

SETTLE = 6                 # seconds an app's terminal must outlive its launch
DOOM = ("doom", "tables.bin", "info.bin")
PASS = "gate-release-1"    # the first boot's passphrase: 14 characters, past the parent's 12 (AC-D3)
fails = 0


def read(path, mode="r"):
    """The whole of path: str (bad bytes replaced) or, with mode "rb", bytes."""
    with open(path, mode, **({} if "b" in mode else {"errors": "replace"})) as f:
        return f.read()


def line(ok, label, detail=""):
    global fails
    print(("PASS  " if ok else "FAIL  ") + label + ("" if ok or not detail else ": " + detail))
    fails += 0 if ok else 1


def apps(path):
    """APPS' rows: index, name, program, aliases, kind (0 TERM, 1 WINDOW, 2 DESK, 3 LABEL) and command (DN-60)."""
    text = read(path)
    rows = re.search(r'parse\("(.*?)"\);', text, re.S).group(1).split("\\n")
    runs = [int(v) for v in re.search(r"runs = \[([0-9, ]+)\]", text).group(1).split(",")]
    cmds = [v.strip() == "true" for v in re.search(r"cmds = \[([a-z, ]+)\]", text).group(1).split(",")]
    out = []
    for i, r in enumerate(x for x in rows if x):
        f = r.split("|")
        out.append({"i": i, "name": f[0], "program": f[1], "aliases": f[2].split(), "kind": runs[i],
                    "command": cmds[i]})
    return out


def members(path):
    """The newc members of path in order, the trailer left out: (name, mode, size, first 4 bytes), size and bytes
    those of the member's inode (tools/mkcpio.py writes a hard link's bytes under its last name only)."""
    data, at, out, body = read(path, "rb"), 0, [], {}
    while True:
        if data[at:at + 6] != b"070701":
            raise ValueError("not newc at %d" % at)
        f = [int(data[at + 6 + 8 * k:at + 14 + 8 * k], 16) for k in range(13)]
        ino, mode, size, nlen = f[0], f[1], f[6], f[11]
        name = data[at + 110:at + 110 + nlen - 1].decode()
        at = (at + 110 + nlen + 3) & ~3
        if name == "TRAILER!!!":
            return [(n, m, len(body.get(i, b"")), body.get(i, b"")[:4]) for n, m, i in out]
        out.append((name, mode, ino))
        if size:
            body[ino] = data[at:at + size]
        at = (at + size + 3) & ~3


def recipe(path):
    """The member names of the mkcpio line in path (`make -n`'s), in order: NAME=FILE, DIR/ and DIR/@MODE."""
    for ln in read(path).splitlines():
        if "tools/mkcpio.py" in ln:
            names = []
            for a in shlex.split(ln)[3:]:
                if "=" in a:
                    names.append(a.split("=", 1)[0])
                else:
                    names.append(a.split("/@", 1)[0].rstrip("/"))
            return names
    return None


def static(initrd, rec, src):
    apps_ci = os.path.join(src, "user/ci/kit/apps.ci")
    m = members(initrd)
    got = [x[0] for x in m]
    want = recipe(rec)
    if want is None:
        line(False, "recipe", "no mkcpio line in " + rec)
    else:
        extra = [n for n in got if n not in want]
        gone = [n for n in want if n not in got]
        line(got == want, "recipe: the image's %d members are the Makefile recipe's, in its order, nothing added "
             "(no injection)" % len(got), "added %s, left out %s%s" % (extra or "none", gone or "none",
                                                                       "" if extra or gone else ", order differs"))
    by = {x[0]: x for x in m}
    rows = apps(apps_ci)
    named = [a for a in rows if a["program"]]
    bad = []
    for a in named:
        x = by.get(a["program"].lstrip("/"))
        if x is None:
            bad.append("%s (%s) not in the image" % (a["name"], a["program"]))
        elif x[1] & 0o170000 != 0o100000 or x[3] != b"\x7fELF":
            bad.append("%s (%s) is not an ELF file" % (a["name"], a["program"]))
    line(not bad, "apps: each of the %d apps of the app list that names a program has it in the image, an ELF file"
         % len(named), "; ".join(bad))
    doom = [n for n in got if os.path.basename(n) in DOOM or n.lower().endswith(".wad")]
    rowd = [a["name"] for a in rows if "doom" in [a["name"].lower(), os.path.basename(a["program"])] + a["aliases"]]
    line(not doom and not rowd, "doom: no Doom file in the image and no Doom row in the app list (DOOM-1)",
         "members %s, app rows %s" % (doom or "none", rowd or "none"))
    named = {}
    for n in got:
        b = {"sh": "cish", "[": "bracket"}.get(os.path.basename(n), os.path.basename(n))
        for f in closure(src, "user/ci/%s.ci" % b):
            for w in re.findall(r'"(/bin/[A-Za-z0-9_.-]+)', read(os.path.join(src, f))):
                named.setdefault(w, f)
    gone = ["%s (%s)" % (w, f) for w, f in sorted(named.items()) if w.lstrip("/") not in by]
    line(not gone, "names: the %d /bin paths the image's programs name in their source are members" % len(named),
         "not in the image: " + ", ".join(gone))
    # rows: user/ci/build.sh gives a program host.c's rows by the modules the program imports DIRECTLY; a module
    # reached only through another (cview's fdctl through kit/setfile, found 2026-11-12 on PR 467) leaves its externs
    # without a host function, and the program built from candidate source dies at start ("cint: the extern `X` has
    # no host function"), while a stale committed binary hides it. A gap is release drift: P1 (RG-1).
    bsh = os.path.join(src, "user/ci/build.sh")
    ctl = set(re.findall(r'\*" (user/ci/[a-z0-9_/]+\.ci) "\*', read(bsh))) if os.path.isfile(bsh) else set()
    short, progs = [], 0
    for n in got:
        b = {"sh": "cish", "[": "bracket"}.get(os.path.basename(n), os.path.basename(n))
        f = "user/ci/%s.ci" % b
        if not os.path.isfile(os.path.join(src, f)):
            continue
        progs += 1
        direct = {m.group(1).replace(".", "/") + ".ci"
                  for m in re.finditer(r"^import ([a-z0-9_.]+);", read(os.path.join(src, f)), re.M)}
        miss = sorted((closure(src, f) - direct - {f}) & ctl)
        if miss:
            short.append("%s reaches %s only through another module" % (b, ", ".join(miss)))
    line(not short, "rows: each of the %d programs of the image built by user/ci/build.sh imports every host-row "
         "module it reaches, so its build gets those rows" % progs,
         "P1, a program built from this source dies at start (cint: the extern has no host function): "
         + "; ".join(short))


def source(member):
    """The cint source a member of the image is built from: hdesk is user/ci/hdesk.ci, bin/NAME user/ci/NAME.ci
    (sh is cish, [ is bracket)."""
    b = os.path.basename(member)
    if b == "ced":
        return "user/ced/ced.ci"           # ced is vendored (user/ced, CED_PIN); its imports name its own files
    return "user/ci/%s.ci" % {"sh": "cish", "[": "bracket"}.get(b, b)


def code(text):
    """text with its // comments removed (a // inside a string or character literal stays), so a source artifact
    holds only on code, never on a comment that names the text."""
    out, k, q = [], 0, None
    while k < len(text):
        c = text[k]
        if q:
            out.append(c)
            if c == "\\" and k + 1 < len(text):
                out.append(text[k + 1])
                k += 1
            elif c == q or c == "\n":
                q = None
        elif c in "\"'":
            q = c
            out.append(c)
        elif text.startswith("//", k):
            while k < len(text) and text[k] != "\n":
                k += 1
            continue
        else:
            out.append(c)
        k += 1
    return "".join(out)


def closure(src, first):
    """first and every .ci file it imports, followed (`import a.b.c;` is a/b/c.ci), as paths under src."""
    seen, todo = set(), [first]
    while todo:
        f = todo.pop()
        if f in seen or not os.path.isfile(os.path.join(src, f)):
            continue
        seen.add(f)
        for m in re.finditer(r"^import ([a-z0-9_.]+);", read(os.path.join(src, f)), re.M):
            g = m.group(1).replace(".", "/") + ".ci"
            near = os.path.join(os.path.dirname(f), g)    # `import desk;` in user/ced/ced.ci is user/ced/desk.ci
            todo.append(g if os.path.isfile(os.path.join(src, g)) or not os.path.isfile(os.path.join(src, near))
                        else near)
    return seen


STATES = ("IN", "PARTIAL", "MISSING", "DEFERRED")


def ledger(path, initrd, esp, volume, apps_ci, transcript, gate, decisions):
    rows, bad = [], []
    for k, ln in enumerate(read(path).splitlines(), 1):
        if ln.startswith("#") or not ln.strip() or ln.startswith("id\t"):
            continue
        f = ln.rstrip("\n").split("\t")
        if len(f) != 6 or not all(f):
            bad.append("line %d has %d fields" % (k, len(f)))
            continue
        rows.append(f)
    ids = [r[0] for r in rows]
    bad += ["id %s twice" % i for i in sorted(set(ids)) if ids.count(i) > 1]
    for r in rows:
        st = r[5].split(" ", 1)[0]
        if st not in STATES:
            bad.append("%s: state %r" % (r[0], r[5]))
        elif st == "DEFERRED" and not re.search(r"\bl 20\d\d-\d\d-\d\d \d\d:\d\dZ", r[5]):
            bad.append("%s: DEFERRED without l's word and time" % r[0])
        elif st == "IN" and all(i.split(" ", 1)[0] in ("member", "nomember") for i in r[2].split("; ")):
            bad.append("%s: IN on membership alone (prove it with module, source, word, line, pass or app)" % r[0])
    line(not bad, "ledger form: %d rows, six fields each, unique ids, known states, every DEFERRED row with l's word "
         "and time, no IN row on membership alone" % len(rows), "; ".join(bad))
    listed = [a["name"] for a in apps(apps_ci)]
    text = " ".join(r[0] + " " + r[1] for r in rows)
    dn = set()
    for m in re.finditer(r"DN-(\d+S?)((?:,? (?:and )?(?:DN-)?\d+S?\b)*)", text):
        dn.add(m.group(1))
        dn.update(re.findall(r"\d+S?", m.group(2)))
    ruled = re.findall(r"^\| DN-(\d+S?) \|", read(decisions), re.M)
    named = {i.split(" ", 1)[1] for r in rows for i in r[2].split("; ") if i.split(" ", 1)[0] in ("app", "noapp")}
    miss = ["app " + n for n in listed if n not in named]
    miss += ["DN-" + d for d in ruled if d not in dn]
    line(not miss, "ledger cover: a row for each of the %d apps and each of the %d DN rulings of %s" % (
        len(listed), len(set(ruled)), os.path.basename(decisions)), "no row: " + ", ".join(miss))
    m = members(initrd)
    by = {x[0]: x for x in m}
    blob = read(initrd, "rb")
    espf = {ln.split("::/", 1)[1].strip() for ln in read(esp).splitlines() if "::/" in ln}
    tl = guestlines.lines(read(transcript, "rb").decode("latin-1"))
    gl = read(gate).splitlines()
    rows_apps = {a["name"]: a for a in apps(apps_ci)}
    src = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(apps_ci)))))
    reach = {}

    ino, data, at = {}, {}, 0           # a hard link's bytes ride its last name (tools/mkcpio.py): read by inode
    while blob[at:at + 6] == b"070701":
        fl = [int(blob[at + 6 + 8 * k:at + 14 + 8 * k], 16) for k in range(13)]
        nm = blob[at + 110:at + 110 + fl[11] - 1].decode()
        at = (at + 110 + fl[11] + 3) & ~3
        ino[nm] = fl[0]
        data[fl[0]] = data.get(fl[0], b"") + blob[at:at + fl[6]]
        at = (at + fl[6] + 3) & ~3

    def body(name):
        return data.get(ino.get(name), b"")

    def holds(item):
        kind, _, v = item.partition(" ")
        if item == "-":
            return True
        if kind == "member":
            return v in by
        if kind == "nomember":
            return v not in by
        if kind == "esp":
            return v in espf
        if kind == "volume":
            o = subprocess.run(["debugfs", "-R", "stat /" + v, volume], capture_output=True, text=True).stdout
            return "Inode:" in o
        if kind == "app":
            a = rows_apps.get(v)
            if not a:
                return False
            if not a["program"]:
                return True
            return a["program"].lstrip("/") in by and any(
                g.startswith("PASS  %s (%s) opens" % (v, a["program"])) for g in gl)
        if kind == "noapp":
            return v not in rows_apps
        if kind == "word":
            mem, _, w = v.partition(" ")
            return mem in by and w.encode() in body(mem)
        if kind == "module":
            mem, _, mod = v.partition(" ")
            if mem not in by:
                return False
            if mem not in reach:
                reach[mem] = closure(src, source(mem))
            return mod != source(mem) and mod in reach[mem]
        if kind in ("source", "nosource"):
            mem, _, w = v.partition(" ")
            if mem not in by:
                return False
            if mem not in reach:
                reach[mem] = closure(src, source(mem))
            found = any(w in code(read(os.path.join(src, f))) for f in reach[mem])
            return found if kind == "source" else not found
        if kind == "file":                  # a host script's word: TEXT on a line of PATH, no # comment, in the tree
            path, _, w = v.partition(" ")
            f = os.path.join(src, path)
            if os.path.normpath(path) != path or path.startswith(("/", "..")) or not os.path.isfile(f):
                return False
            return any(w in x for x in read(f).splitlines() if not x.lstrip().startswith("#"))
        if kind == "line":
            return any(x.startswith(v) for x in tl)
        if kind == "bar":                   # the booted desk's bar named the window NAME
            return any(re.match(r"hdesk: bar desktop \d+ \|%s\|" % re.escape(v), x) for x in tl)
        if kind == "bars" and v == "apps":  # ... for every app of APPS with a program, by its approved name
            return all(holds("bar " + a["name"]) for a in apps(apps_ci) if a["program"] and not a["command"])
        if kind == "pass":
            return any(g.startswith("PASS  " + v) for g in gl)
        return False

    short = []
    checked = 0
    for r in rows:
        if r[5].split(" ", 1)[0] not in ("IN", "DEFERRED"):
            continue
        for item in r[2].split("; "):
            checked += 1
            if not holds(item):
                short.append("%s: %s" % (r[0], item))
    line(not short, "ledger in: the %d artifacts of the IN and DEFERRED rows hold in the image" % checked,
         "%d do not: %s" % (len(short), "; ".join(short)))
    op = ["%s %s" % (r[0], r[5]) for r in rows if r[5].split(" ", 1)[0] in ("MISSING", "PARTIAL")]
    line(not op, "ledger open: no row is MISSING or PARTIAL", "%d rows: %s" % (len(op), "; ".join(op)))


class Desk:
    """The transcript read from a cursor on, and the monitor to type with (tools/sendkeys.py's 300 ms a key)."""

    def __init__(self, mon, transcript):
        self.mon, self.path, self.at = mon, transcript, 0

    def text(self):
        try:
            with open(self.path, "rb") as f:
                return f.read().decode("latin-1")
        except OSError:
            return ""

    def wait(self, pattern, secs, stop=None):
        """The first line after the cursor matching pattern (a regex, at the line's start); the cursor moves past
        it. None after secs, or when a line matching stop comes first (the cursor then moves past that one)."""
        rx, sx = re.compile(pattern), re.compile(stop) if stop else None
        end = time.monotonic() + secs
        while True:
            t = self.text()
            k = self.at
            while True:
                e = t.find("\n", k)
                if e < 0:
                    break
                ln = t[k:e].rstrip("\r")
                k = e + 1
                if sx and sx.match(ln):
                    self.at = k
                    return None
                m = rx.match(ln)
                if m:
                    self.at = k
                    return m
            if time.monotonic() > end:
                return None
            time.sleep(0.1)

    def seen(self, pattern, since):
        """Whether a line from offset since matches pattern."""
        rx = re.compile(pattern)
        return any(rx.match(ln) for ln in guestlines.lines(self.text()[since:]))

    def send(self, keys):
        s = socket.socket(socket.AF_UNIX)
        s.settimeout(5)
        s.connect(self.mon)
        time.sleep(0.2)
        for k in keys.split(","):
            s.sendall(((k if " " in k else "sendkey " + k) + "\n").encode())
            time.sleep(0.3)
        s.close()


def keys(word):
    return ",".join({" ": "spc", "-": "minus"}.get(c, c) for c in word)


def close(d, t):
    """Super+Q on the focused window (the app's); whether terminal t ended with it. tidy closes what stays."""
    d.send("meta_l-q")
    return bool(d.wait(r"hdesk: terminal %d ended, status " % t, 30))


def tidy(d, since):
    """Puts the desk back as the app found it: the plane closed, and every terminal opened from offset since ended
    (Super+Q on the focused window, newest first), so one app's failure does not fail the next."""
    for _ in range(6):
        ls = guestlines.lines(d.text()[since:])
        st = [m.group(1) for m in (re.match(r"hdesk: ff (open|closed|chose) ", x) for x in ls) if m]
        if st and st[-1] == "open":
            d.send("esc")
            d.wait(r"hdesk: ff closed", 15)
            continue
        opened, ended = {}, {}
        for x in ls:
            m = re.match(r"hdesk: terminal (\d+) (slot|ended)", x)
            if m:
                c = opened if m.group(2) == "slot" else ended
                c[m.group(1)] = c.get(m.group(1), 0) + 1
        if all(ended.get(t, 0) >= n for t, n in opened.items()):
            return
        d.send("meta_l-q")
        d.wait(r"hdesk: terminal \d+ ended", 20)


def one(d, a, run):
    """Opens app a from the plane, holds it to its lines, closes it."""
    label = "%s (%s)" % (a["name"], a["program"])
    d.send("meta_l")                     # a clean Super tap opens the plane
    if not d.wait(r"hdesk: ff open ", 30):
        line(False, label, "a Super tap did not open the plane")
        return
    word = a["aliases"][0]
    d.send(keys(word))
    q = d.wait(r"hdesk: ff \|%s\| rows (\d+) sel (\d+)$" % re.escape(word), 45)
    if not q:
        line(False, label, "the plane never showed the query |%s|" % word)
        return
    rows = {}
    for _ in range(int(q.group(1))):
        r = d.wait(r"hdesk: ff row (\d+) (\w+) \|(.*?)\| ", 5)
        if r:
            rows[int(r.group(1))] = (r.group(2), r.group(3))
    k = next((n for n, (kind, txt) in sorted(rows.items()) if kind == "prog" and txt == a["program"]), None)
    if k is None:
        line(False, label, "the plane lists no row for %s under |%s|: %s" % (a["program"], word, rows))
        return
    sel = int(q.group(2))
    for _ in range(2 * len(rows)):       # Down walks the plane's display order, which groups rows by kind, so one
        if sel == k:                     # press at a time until the row is selected
            break
        d.send("down")
        m = d.wait(r"hdesk: ff \|%s\| rows \d+ sel (\d+)$" % re.escape(word), 30)
        if not m:
            break
        sel = int(m.group(1))
    if sel != k:
        line(False, label, "the plane's selection never reached row %d (last %d)" % (k, sel))
        return
    d.send("ret")
    if not d.wait(r"hdesk: ff app %d \|%s\|$" % (a["i"], re.escape(a["program"])), 30):
        line(False, label, "Enter on its row did not open app %d%s" % (a["i"], ": the plane ran it as a program, so "
             "the desk's own app table lacks it (an hdesk older than the app list)"
             if d.seen(r"hdesk: ff chose prog \|%s\|$" % re.escape(a["program"]), 0) else ""))
        return
    s = d.wait(r"hdesk: terminal (\d+) slot \d+ pid \d+$", 20, stop=r"hdesk: launch none ")
    if not s:
        line(False, label, "`hdesk: launch none`: %s is not in the image" % a["program"]
             if d.seen(r"hdesk: launch none ", 0) else "no terminal opened")
        return
    t, since = int(s.group(1)), d.at
    if a["kind"] == 1:
        p = d.wait(r"hdesk: pixel (\d+) pid \d+ size (\d+)x(\d+)$", 90, stop=r"hdesk: terminal %d ended" % t)
        what = "its window bound, %sx%s" % (p.group(2), p.group(3)) if p else ""
        ok = bool(p)
        why = "no window bound; terminal %d %s" % (t, "ended: P1, an app that ends at once from release source (seen "
                                                   "2026-11-12: a host row user/ci/build.sh missed, see the rows "
                                                   "line); run it in a Console to read why"
                                                   if d.seen(r"hdesk: terminal %d ended" % t, since)
                                                   else "is up with no window")
    else:
        time.sleep(SETTLE)
        ok = not d.seen(r"hdesk: terminal %d ended" % t, since)
        what = "its terminal %d up %d s after the launch" % (t, SETTLE)
        why = ("terminal %d ended within %d s: %s. P1, an app that ends at once from release source (seen 2026-11-12: "
               "a host row user/ci/build.sh missed, see the rows line; a program that refuses to start with no "
               "argument); run it in a Console to read why" % (t, SETTLE, next((
                   ln for ln in guestlines.lines(d.text()[since:]) if ln.startswith("hdesk: terminal %d ended" % t)), "")))
    d.send("screendump %s/app-%d.ppm" % (run, a["i"]))
    time.sleep(1)
    line(ok, "%s opens: %s" % (label, what) if ok else label, why)
    if not ok:
        return
    ended = close(d, t)
    if a["command"] or a["program"] == "/bin/cish":
        line(ended, "%s: Super+Q ends its Console" % label, "terminal %d stayed up" % t)
    else:
        line(ended, "%s: Super+Q ends the app and its terminal with it (DN-60: `exec`)" % label,
             "terminal %d stayed up after the app ended: the app was typed without exec (a stale hdesk)" % t)


def drive(mon, transcript, apps_ci, run):
    d = Desk(mon, transcript)
    if not d.wait(r"hdesk: accounts first boot$", 300):
        line(False, "first boot", "no `hdesk: accounts first boot` in 300 s")
        return
    time.sleep(2)
    d.send("r,e,l,tab,%s,tab,%s,ret" % (keys(PASS), keys(PASS)))
    login = d.wait(r"hdesk: login rel uid (\d+)$", 600, stop=r"hdesk: enroll failed")
    line(bool(login), "first boot: the parent account rel is made and its session starts",
         "no `hdesk: login rel` (%s)" % ("enroll failed" if d.seen(r"hdesk: enroll failed", 0) else "timed out"))
    if not login:
        return
    bar = d.wait(r"hdesk: bar desktop 1 \|Console\| ", 60)   # NAMES-28: the session shell's window is Console
    line(bool(bar), "first boot: the session's Console names itself on the bar",
         "no `hdesk: bar desktop 1 |Console|` in 60 s after the login")
    if not bar:
        return
    time.sleep(3)
    for a in apps(apps_ci):
        if a["program"]:
            since = d.at
            one(d, a, run)
            tidy(d, since)
    d.send("print")                      # the screenshot writer (/bin/shot, frame 43)
    d.wait(r"hdesk: shot pid \d+ ended", 40)   # its child ends, or the desk stops it past shotdesk.WAIT_MS (20 s)
    d.send("meta_l-shift-q")
    d.wait(r"hdesk: ff armed ", 20)
    d.send("meta_l-shift-q")
    line(bool(d.wait(r"daphnis: done$", 120)), "shut down: Super+Shift+Q twice ends the desk",
         "no `daphnis: done` in 120 s")


def after(transcript, initrd, volume, name):
    t = read(transcript, "rb").decode("latin-1")
    ls = guestlines.lines(t)
    lease = next((m for m in (re.match(r"daphnis: net dhcp (\S+) gateway (\S+) ", x) for x in ls) if m), None)
    gw = next((x for x in ls if re.match(r"daphnis: net gateway \S+ (known|is at )", x)), None)
    line(bool(lease and gw), "network: DHCP leases %s, gateway %s answers" % (
        lease.group(1), lease.group(2)) if lease and gw else "network",
         "no `daphnis: net dhcp ... gateway` line" if not lease else "no `daphnis: net gateway ... known` line")
    size = os.path.getsize(initrd)
    line(guestlines.has(t, "daphnis: image %d bytes " % size),
         "image: the loader's module is the stick's initrd, %d bytes" % size, "no `daphnis: image %d bytes`" % size)
    line(not guestlines.has(t, "daphnis: input dropped"), "keys: no key dropped, the desk read what the gate typed",
         "`daphnis: input dropped`: the kernel's input queue lost a key")
    pics = "/%s/Pictures" % name
    out = subprocess.run(["debugfs", "-R", "ls -p " + pics, volume], capture_output=True, text=True).stdout
    pngs = [f.split("/")[5] for f in out.splitlines() if f.count("/") >= 6 and f.split("/")[5].endswith(".png")]
    good = []
    for p in pngs:
        b = subprocess.run(["debugfs", "-R", "cat %s/%s" % (pics, p), volume], capture_output=True).stdout
        if b[:8] == b"\x89PNG\r\n\x1a\n" and b[12:16] == b"IHDR":
            good.append("%s %d bytes %dx%d" % (p, len(b), int.from_bytes(b[16:20], "big"),
                                                int.from_bytes(b[20:24], "big")))
    end = next((x for x in ls if re.match(r"hdesk: shot pid \d+ ended", x)), None)
    line(bool(good), "shot: Print wrote a PNG into %s on the volume: %s" % (pics, ", ".join(good)) if good
         else "shot: Print writes a PNG into " + pics, "%s holds %s; %s" % (
             pics, (pngs or "no .png") if out.strip() else "nothing (or does not exist)",
             "`%s`" % end if end else "no `hdesk: shot pid N ended` line"))


def main(argv):
    if argv[:1] == ["--static"] and len(argv) == 4:
        static(*argv[1:])
    elif argv[:1] == ["--drive"] and len(argv) == 5:
        drive(*argv[1:])
    elif argv[:1] == ["--after"] and len(argv) == 5:
        after(*argv[1:])
    elif argv[:1] == ["--ledger"] and len(argv) == 9:
        ledger(*argv[1:])
    elif argv[:1] == ["--count"] and len(argv) == 2:
        print(sum(1 for a in apps(argv[1]) if a["program"]))
    else:
        print(__doc__)
        return 2
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
