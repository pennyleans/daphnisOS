#!/usr/bin/env python3
"""tests/rs/guest/guest.py COMMAND ...: the parts of the stage RS guest legs (tests/rs/guest/train.sh). Host side
only: nothing here boots a guest, and every input and output is a file.

  keys TEXT                  TEXT as QEMU key names joined by commas, tools/sendkeys.py's INPUT (the US layout)
  marks TRANSCRIPT FILE      FILE's marks in TRANSCRIPT (MARKS below); PASS or FAIL, status 1 on FAIL
  pool [-m MAKEFILE] T...    every transcript T read for a state pool fault (POOL below); status 1 on one
  vol VOLUME FILE            FILE's expectations of the ext2 VOLUME (VOL below), read with debugfs and e2fsck -fn
  card TRANSCRIPT A B        the approval prompt's left part in screendumps A and B is one picture, and holds text
  color TRANSCRIPT PPM RGB   the middle of the last pixel window's float, as TRANSCRIPT placed it, is RGB (6 hex
                             digits) in the screendump PPM
  differ TRANSCRIPT A B      that window's frame is not one picture in screendumps A and B: it drew between them
  sheet TRANSCRIPT WIN A B [moved]
                             the About sheet over window WIN (kit/about.ci, centered on the frame the desk last
                             logged for WIN before `hdesk: about WIN`) is one picture in A and B and holds text; with
                             moved, the rest of WIN's frame is not: the window drew under the sheet, around it
  png OUT W H RGB PATH       a PNG of W x H pixels of color RGB at OUT, and OUT.want, the line `cview -d PATH`
                             prints for it: `cview: PATH WxH rgba SHA256`
  cpio IN OUT MEMBER...      IN, a newc archive, with MEMBERs under rs/ only (rs/NAME=FILE or rs/)
                             put before its trailer, into OUT
  ops TABLE OUT [k|-]        the shell script that sends TABLE's requests (or only its k or - rows) to authd (OPS)
  status TABLE WAIT          what a script of TABLE says by the wait status WAIT the desk printed for its terminal

MARKS: one a line, in order. TEXT: a line that begins with TEXT, after the line of the mark before. =TEXT: a line that
is TEXT, after it. ~REGEX: a line the regular expression matches whole, after it. !TEXT: TEXT on no line at all (a
passphrase, a line that must never come). -TEXT: TEXT on no line between the line of the mark before and the line of
the mark after (to the end when it is last). Lines that begin with # and empty lines are skipped. The marks of
tools/check-accounts.py, with `=`, `~` and `-` added. A transcript with the line `daphnis: input dropped` fails before
any mark is read: the kernel's input queue was full, so a key the leg sent was lost and what the guest typed is not
what the leg sent (board 20261112T012351Z). The kernel prints the line when the desk ends, not when the key is lost.

POOL: rt/ctx.c's state_fault records `host.resource` when a module's state does not fit RT_STATE_POOL_BYTES; the
kernel prints the record as `fault: cint-core-1/fault/v2 N bytes` and its bytes in hex (rt_print_fault). Each record
is decoded; host.resource fails with a banner naming the transcript, the line and the Makefile's pool of the user
flavors (RTDEF_user), so a boot that dies there says why at once (board 20261111T185628Z). Other records are listed.

VOL: one expectation a line. `dir PATH MODE UID GID` a directory with those bits, uid and gid; `gone PATH` debugfs
finds no such name; `store NAME KEY=VALUE...` NAME's row of /.daphnis/accounts holds each pair; `nostore NAME` no row
for NAME; `header WORD` the store's first line holds WORD; `fsck` e2fsck -fn finds the volume clean. PATH is on the
volume, whose / is the guest's /home.

OPS: one request a line, five fields split by ` | `: `k` (through `kern`, ring 0) or `-` (as the session); the
request's first line; the passphrases, each joined to the next with nothing between (authd reads BY's N bytes, then
the new one); the answer line authd must print; its exit status. The script exits 0 when every answer and status is
as written, else at the first that is not: K for request K's answer, 100 + K for its status, K the table's row
either way. A `-` row runs before any ring 0 is held: kern's hold (R0-R4 B) is on the window's shell, and whatever
the shell starts in it holds ring 0 too, so train.sh sends a table's `-` rows first, then `kern true`, then its `k`
rows. Each row also appends `row K status S: ANSWER` to $HOME/rs.log, which train.sh prints from the volume when a
leg fails; no passphrase is written there.
"""
import hashlib
import os
import re
import struct
import subprocess
import sys
import zlib

# --- keys ---------------------------------------------------------------------------------------------------------

PLAIN = {" ": "spc", "\n": "ret", "\t": "tab", "-": "minus", "=": "equal", "[": "bracket_left",
         "]": "bracket_right", "\\": "backslash", ";": "semicolon", "'": "apostrophe", "`": "grave_accent",
         ",": "comma", ".": "dot", "/": "slash"}
SHIFTED = {"!": "1", "@": "2", "#": "3", "$": "4", "%": "5", "^": "6", "&": "7", "*": "8", "(": "9", ")": "0",
           "_": "minus", "+": "equal", "{": "bracket_left", "}": "bracket_right", "|": "backslash",
           ":": "semicolon", '"': "apostrophe", "~": "grave_accent", "<": "comma", ">": "dot", "?": "slash"}


def key_names(text):
    """The QEMU sendkey names that type text on a US keyboard, one a character."""
    out = []
    for c in text:
        if "a" <= c <= "z" or "0" <= c <= "9":
            out.append(c)
        elif "A" <= c <= "Z":
            out.append("shift-" + c.lower())
        elif c in PLAIN:
            out.append(PLAIN[c])
        elif c in SHIFTED:
            out.append("shift-" + SHIFTED[c])
        else:
            raise ValueError("no key types %r" % c)
    return out


# --- marks --------------------------------------------------------------------------------------------------------

def read_marks(path):
    marks = []
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n")
            if line and not line.startswith("#"):
                marks.append(line)
    return marks


DROPPED = "daphnis: input dropped"


def check_marks(lines, marks):
    """None when lines hold marks, else what is missing (first, a key the kernel dropped)."""
    for k, ln in enumerate(lines, 1):
        if ln.startswith(DROPPED):
            return ("%r at line %d: the kernel's input queue was full and lost a key, so the typed text is not what "
                    "the leg sent" % (DROPPED, k))
    at, between = 0, []
    for mark in marks:
        if mark.startswith("!"):
            if any(mark[1:] in ln for ln in lines):
                return "found %r" % mark[1:]
            continue
        if mark.startswith("-"):
            between.append(mark[1:])
            continue
        start = at
        if mark.startswith("="):
            hit = lambda ln, t=mark[1:]: ln == t
        elif mark.startswith("~"):
            hit = lambda ln, r=re.compile(mark[1:]): r.fullmatch(ln) is not None
        else:
            hit = lambda ln, t=mark: ln.startswith(t)
        while at < len(lines) and not hit(lines[at]):
            at += 1
        if at == len(lines):
            return "no line %r in order" % mark
        for t in between:
            if any(t in ln for ln in lines[start:at]):
                return "found %r before %r" % (t, mark)
        between = []
        at += 1
    for t in between:
        if any(t in ln for ln in lines[at:]):
            return "found %r after the last mark" % t
    return None


def transcript_lines(path):
    with open(path, "rb") as f:
        return f.read().decode("latin-1").split("\n")


# --- pool ---------------------------------------------------------------------------------------------------------

FAULT = re.compile(r"^fault: cint-core-1/fault/v2 (\d+) bytes$")


def record_operation(hexline, size):
    """The operation of a cint-core-1/fault/v2 record (rt/fault.c rt_fault_encode), or None if it does not read."""
    try:
        b = bytes.fromhex(hexline.strip())
    except ValueError:
        return None
    if len(b) != size or len(b) < 10:
        return None
    dn = struct.unpack_from("<I", b, 0)[0]
    if b[4:4 + dn] != b"cint-core-1/fault/v2":
        return None
    at = 4 + dn + 2
    if len(b) < at + 4:
        return None
    on = struct.unpack_from("<I", b, at)[0]
    op = b[at + 4:at + 4 + on]
    if len(op) != on:
        return None
    return op.decode("latin-1")


def faults(lines):
    """(line number from 1, operation or None) of each fault record."""
    out = []
    for i, ln in enumerate(lines):
        m = FAULT.match(ln)
        if m:
            nxt = lines[i + 1] if i + 1 < len(lines) else ""
            out.append((i + 1, record_operation(nxt, int(m.group(1)))))
    return out


def user_pool(makefile):
    try:
        with open(makefile, encoding="utf-8") as f:
            for ln in f:
                if ln.startswith("RTDEF_user :="):
                    m = re.search(r"-DRT_STATE_POOL_BYTES=(\d+)u?", ln)
                    if m:
                        return int(m.group(1))
    except OSError:
        pass
    return None


def pool(args):
    makefile = "Makefile"
    if args[:1] == ["-m"]:
        makefile, args = args[1], args[2:]
    hit, missing = [], [t for t in args if not os.path.isfile(t)]
    for t in missing:
        print("FAIL: no transcript %s (QEMU did not run)" % t)
    if missing:
        return 2
    for t in args:
        for n, op in faults(transcript_lines(t)):
            if op == "host.resource":
                hit.append((t, n))
            else:
                print("note: %s line %d: a fault record, operation %s" % (t, n, op if op else "unreadable"))
    if not hit:
        print("PASS: %d transcripts, no state pool fault (host.resource)" % len(args))
        return 0
    size = user_pool(makefile)
    bar = "!" * 100
    print(bar)
    print("STATE POOL FAULT: the kernel's module state does not fit its pool (rt/ctx.c state_fault, host.resource)")
    for t, n in hit:
        print("STATE POOL FAULT:   %s line %d" % (t, n))
    print("STATE POOL FAULT: %s RTDEF_user sets RT_STATE_POOL_BYTES=%s; the module state of the flavor is larger."
          % (makefile, size if size is not None else "(not found)"))
    print("STATE POOL FAULT: raise the pool in the Makefile (one line; PR 273 carries 256 KiB) or cut module state;")
    print("STATE POOL FAULT: the legs after this boot would say nothing about the units, since nothing past it ran.")
    print(bar)
    return 1


# --- vol ----------------------------------------------------------------------------------------------------------

def debugfs(volume, request, err=False):
    """debugfs's answer; with err, its stderr after it (where it says a name is not found)."""
    r = subprocess.run(["debugfs", "-R", request, volume], capture_output=True)
    return (r.stdout + (r.stderr if err else b"")).decode("latin-1")


def stat_of(volume, path):
    """(type, mode, uid, gid) of path on the volume, or None."""
    s = debugfs(volume, "stat " + path)
    m = re.search(r"Type:\s+(\S+)\s+Mode:\s+(\d+)", s)
    o = re.search(r"User:\s+(\d+)\s+Group:\s+(\d+)", s)
    if not m or not o:
        return None
    return m.group(1), m.group(2).lstrip("0").rjust(4, "0"), int(o.group(1)), int(o.group(2))


def store_rows(text):
    head, rows = "", {}
    for i, ln in enumerate(text.split("\n")):
        if i == 0:
            head = ln
            continue
        if ln.startswith("acct "):
            kv = dict(w.split("=", 1) for w in ln.split()[1:] if "=" in w)
            rows[kv.get("name", "")] = kv
    return head, rows


def vol(volume, expect):
    store = None
    bad = []
    n = 0
    with open(expect, encoding="utf-8") as f:
        text = f.read().split("\n")
    for raw in text:
        w = raw.split()
        if not w or w[0].startswith("#"):
            continue
        n += 1
        if w[0] in ("store", "nostore", "header") and store is None:
            store = store_rows(debugfs(volume, "cat /.daphnis/accounts"))
            if not store[0].startswith("daphnis-accounts "):
                bad.append("no store on the volume (debugfs read %r)" % store[0])
        if w[0] == "dir":
            got = stat_of(volume, w[1])
            want = ("directory", w[2], int(w[3]), int(w[4]))
            if got != want:
                bad.append("%s: %s, not %s" % (w[1], got, want))
        elif w[0] == "gone":
            if "File not found by ext2_lookup" not in debugfs(volume, "stat " + w[1], err=True):
                bad.append("%s: debugfs does not say it is not found" % w[1])
        elif w[0] == "store":
            row = store[1].get(w[1])
            if row is None:
                bad.append("no store row for %s" % w[1])
            else:
                for kv in w[2:]:
                    k, v = kv.split("=", 1)
                    if row.get(k) != v:
                        bad.append("%s: %s=%s, not %s" % (w[1], k, row.get(k), v))
        elif w[0] == "nostore":
            if w[1] in store[1]:
                bad.append("a store row for %s" % w[1])
        elif w[0] == "header":
            if w[1] not in store[0].split():
                bad.append("store header %r has no %s" % (store[0], w[1]))
        elif w[0] == "fsck":
            r = subprocess.run(["e2fsck", "-fn", volume], capture_output=True)
            if r.returncode != 0:
                bad.append("e2fsck -fn status %d" % r.returncode)
        else:
            bad.append("unknown expectation %r" % raw.strip())
    for b in bad:
        print("FAIL: " + b)
    if bad:
        return 1
    print("PASS: %d expectations" % n)
    return 0


# --- screendumps --------------------------------------------------------------------------------------------------

def read_ppm(path):
    """(width, height, rgb bytes) of a binary P6 file of maxval 255, as QEMU's screendump writes it."""
    with open(path, "rb") as f:
        data = f.read()
    fields, at = [], 0
    while len(fields) < 4:
        while data[at:at + 1].isspace():
            at += 1
        if data[at:at + 1] == b"#":
            while data[at:at + 1] not in (b"\n", b""):
                at += 1
            continue
        start = at
        while at < len(data) and not data[at:at + 1].isspace():
            at += 1
        fields.append(data[start:at])
    if fields[0] != b"P6" or fields[3] != b"255":
        raise ValueError("%s is not a P6 of maxval 255" % path)
    w, h = int(fields[1]), int(fields[2])
    px = data[at + 1:at + 1 + 3 * w * h]
    if len(px) != 3 * w * h:
        raise ValueError("%s is short" % path)
    return w, h, px


def crop(img, x0, y0, x1, y1):
    w, h, px = img
    return b"".join(px[3 * (y * w + x0):3 * (y * w + x1)] for y in range(y0, y1))


SCREEN = re.compile(r"^hdesk: screen (\d+)x(\d+) plane (\d+)x(\d+)")
KP_W, KP_TEXT = 420, 150   # hdesk.ci: the prompt is KP_W wide at 1x; its rows above the passphrase field end by 150
KP_R = 12                  # its corner's radius: the background shows outside the arc, so the box starts past it


def screen(lines):
    got = None
    for ln in lines:
        m = SCREEN.match(ln)
        if m:
            got = tuple(int(g) for g in m.groups())
    return got


def scale(w, h):
    return 2 if min(w, h) > 1600 else 1   # hdesk.ci auto_scale


def prompt_box(lines):
    """The approval prompt's left part: hdesk.ci centers KP_W x kp_h() over the plane, under the bar (KERN-Q1). Its
    right part holds the asker's pid, which differs between two asks, and its passphrase field a caret."""
    s = screen(lines)
    if s is None:
        return None
    w, h, _, ph = s
    sc = scale(w, h)
    x0 = (w - KP_W * sc) // 2
    y0 = (h - ph) + (ph - 300 * sc) // 2      # kp_h() is KP_H2 (300) while the prompt has its field (accounts on)
    return x0 + KP_R * sc, y0, x0 + (KP_W * 3 // 5) * sc, y0 + KP_TEXT * sc


def card(transcript, a, b):
    box = prompt_box(transcript_lines(transcript))
    if box is None:
        print("FAIL: no `hdesk: screen` line in %s" % transcript)
        return 1
    pa, pb = crop(read_ppm(a), *box), crop(read_ppm(b), *box)
    colors = len({pa[i:i + 3] for i in range(0, len(pa), 3)})
    if pa != pb:
        diff = sum(1 for i in range(0, len(pa), 3) if pa[i:i + 3] != pb[i:i + 3])
        print("FAIL: the prompts' left parts differ in %d pixels (box %d,%d to %d,%d)" % ((diff,) + box))
        return 1
    if colors < 3:
        print("FAIL: the prompt's left part holds %d colors, so no text (box %d,%d to %d,%d)" % ((colors,) + box))
        return 1
    print("PASS: one picture in both, %d colors (box %d,%d to %d,%d)" % ((colors,) + box))
    return 0


FLOAT = re.compile(r"^hdesk: float (\d+) app -?\d+ frame (-?\d+),(-?\d+) (\d+)x(\d+)")
PIXEL = re.compile(r"^hdesk: pixel (\d+) pid \d+ size ")


def last_pixel(lines):
    """(window, (x, y, w, h)) of the last `hdesk: pixel N pid` window, framed by the `hdesk: float N` line before it
    (hdesk.ci prints the float first, DN-20); None when there is none."""
    got, last = None, {}
    for ln in lines:
        m = FLOAT.match(ln)
        if m:
            last[m.group(1)] = tuple(int(g) for g in m.groups()[1:])
        p = PIXEL.match(ln)
        if p and p.group(1) in last:
            got = (p.group(1), last[p.group(1)])
    return got


def color(transcript, ppm, rgb):
    got = last_pixel(transcript_lines(transcript))
    if got is None:
        print("FAIL: no `hdesk: pixel` window placed by an `hdesk: float` line in %s" % transcript)
        return 1
    win, (x, y, fw, fh) = got
    img = read_ppm(ppm)
    cx, cy = x + fw // 2, y + fh // 2
    want = bytes.fromhex(rgb)
    px = crop(img, cx - 1, cy - 1, cx + 2, cy + 2)
    if px != want * 9:
        print("FAIL: the 3 x 3 pixels at %d,%d are %s, not %s" % (cx, cy, px.hex(), rgb))
        return 1
    print("PASS: %s at %d,%d, the middle of window %s's frame %d,%d %dx%d" % (rgb, cx, cy, win, x, y, fw, fh))
    return 0


WIN = re.compile(r"^hdesk: win (\d+) kind -?\d+ desktop -?\d+ mode -?\d+ rank -?\d+ frame (-?\d+),(-?\d+) (\d+)x(\d+) ")
ABOUT = re.compile(r"^hdesk: about (\d+)$")
SHEET_X, SHEET_Y = 150, 120   # within kit/about.ci's sheet (W 360, height() at least 287) about its middle, at 1x


def sheet_frame(lines, win):
    """(x, y, w, h) of window win's frame in the last `hdesk: win WIN` line before the last `hdesk: about WIN`: the
    frame the sheet was centered on (hdesk.ci am_answer); None when the transcript has no such pair."""
    frame, got = None, None
    for ln in lines:
        m = WIN.match(ln)
        if m and m.group(1) == win:
            frame = tuple(int(g) for g in m.groups()[1:])
        a = ABOUT.match(ln)
        if a and a.group(1) == win and frame is not None:
            got = frame
    return got


def sheet(transcript, win, a, b, moved=None):
    lines = transcript_lines(transcript)
    fr, s = sheet_frame(lines, win), screen(lines)
    if fr is None or s is None:
        print("FAIL: no `hdesk: screen` line, or no frame of window %s before `hdesk: about %s`" % (win, win))
        return 1
    ia, ib = read_ppm(a), read_ppm(b)
    if ia[:2] != ib[:2]:
        print("FAIL: the screendumps are %dx%d and %dx%d" % (ia[0], ia[1], ib[0], ib[1]))
        return 1
    sc = scale(s[0], s[1])
    x, y, fw, fh = fr
    cx, cy = x + fw // 2, y + fh // 2
    box = (cx - SHEET_X * sc, cy - SHEET_Y * sc, cx + SHEET_X * sc, cy + SHEET_Y * sc)
    if box[0] < 0 or box[1] < 0 or box[2] > ia[0] or box[3] > ia[1]:
        print("FAIL: the sheet's box %d,%d to %d,%d is off the screen" % box)
        return 1
    pa, pb = crop(ia, *box), crop(ib, *box)
    colors = len({pa[i:i + 3] for i in range(0, len(pa), 3)})
    if pa != pb:
        n = sum(1 for i in range(0, len(pa), 3) if pa[i:i + 3] != pb[i:i + 3])
        print("FAIL: the sheet over window %s differs in %d pixels (box %d,%d to %d,%d)" % ((win, n) + box))
        return 1
    if colors < 3:
        print("FAIL: the sheet over window %s holds %d colors, so no text (box %d,%d to %d,%d)" % ((win, colors) + box))
        return 1
    said = "PASS: the sheet over window %s is one picture, %d colors (box %d,%d to %d,%d)" % ((win, colors) + box)
    if moved:
        n, x0, x1 = 0, max(x, 0), min(x + fw, ia[0])
        for yy in range(max(y, 0), min(y + fh, ia[1])):
            spans = [(x0, x1)] if not box[1] <= yy < box[3] else [(x0, box[0]), (box[2], x1)]
            for s0, s1 in spans:
                k0, k1 = 3 * (yy * ia[0] + s0), 3 * (yy * ia[0] + s1)
                ra, rb = ia[2][k0:k1], ib[2][k0:k1]
                if ra != rb:
                    n += sum(1 for i in range(0, len(ra), 3) if ra[i:i + 3] != rb[i:i + 3])
        if n == 0:
            print("FAIL: window %s's frame %d,%d %dx%d is the same in both outside the sheet: it drew nothing"
                  % (win, x, y, fw, fh))
            return 1
        said += "; the window around it differs in %d pixels" % n
    print(said)
    return 0


def differ(transcript, a, b):
    """The last pixel window's frame, clipped to the screen, is not one picture in screendumps a and b: the window
    drew between them."""
    got = last_pixel(transcript_lines(transcript))
    if got is None:
        print("FAIL: no `hdesk: pixel` window placed by an `hdesk: float` line in %s" % transcript)
        return 1
    win, (x, y, fw, fh) = got
    ia, ib = read_ppm(a), read_ppm(b)
    if ia[:2] != ib[:2]:
        print("FAIL: the screendumps are %dx%d and %dx%d" % (ia[0], ia[1], ib[0], ib[1]))
        return 1
    box = (max(x, 0), max(y, 0), min(x + fw, ia[0]), min(y + fh, ia[1]))
    if box[0] >= box[2] or box[1] >= box[3]:
        print("FAIL: window %s's frame %d,%d %dx%d is off the screen" % (win, x, y, fw, fh))
        return 1
    pa, pb = crop(ia, *box), crop(ib, *box)
    n = sum(1 for i in range(0, len(pa), 3) if pa[i:i + 3] != pb[i:i + 3])
    if n == 0:
        print("FAIL: window %s's frame %d,%d %dx%d is the same in both" % (win, x, y, fw, fh))
        return 1
    print("PASS: window %s's frame %d,%d %dx%d differs in %d pixels" % (win, x, y, fw, fh, n))
    return 0


# --- png ----------------------------------------------------------------------------------------------------------

def chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def png(out, w, h, rgb, path):
    w, h = int(w), int(h)
    c = bytes.fromhex(rgb)
    raw = (b"\0" + c * w) * h
    data = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    data += chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
    with open(out, "wb") as f:
        f.write(data)
    digest = hashlib.sha256((c + b"\xff") * (w * h)).hexdigest()
    with open(out + ".want", "w", encoding="ascii") as f:
        f.write("cview: %s %dx%d rgba %s\n" % (path, w, h, digest))
    return 0


# --- cpio ---------------------------------------------------------------------------------------------------------

def cpio_member(ino, name, data, mode, nlink):
    n = name.encode() + b"\0"
    fields = [ino, mode, 0, 0, nlink, 0, len(data), 0, 0, 0, 0, len(n), 0]
    head = b"070701" + b"".join(b"%08X" % f for f in fields) + n
    head += b"\0" * (-len(head) % 4)
    return head + data + b"\0" * (-len(data) % 4)


def cpio_split(data):
    """(bytes before the trailer, the highest inode number, the names) of a newc archive (tools/mkcpio.py's form)."""
    at, top, names = 0, 0, []
    while True:
        if data[at:at + 6] != b"070701":
            raise ValueError("no newc header at %d" % at)
        f = [int(data[at + 6 + 8 * i:at + 14 + 8 * i], 16) for i in range(13)]
        nlen, size = f[11], f[6]
        name = data[at + 110:at + 110 + nlen - 1].decode()
        end = at + 110 + nlen
        end += -end % 4
        end += size + (-size % 4)
        if name == "TRAILER!!!":
            return data[:at], top, names
        top = max(top, f[0])
        names.append(name)
        at = end


def cpio(src, out, members):
    """IN with the legs' files added under rs/ and nothing else (RG-1, l 2026-11-12 07:53Z: a test adds no program the
    release recipe lacks)."""
    with open(src, "rb") as f:
        body, top, names = cpio_split(f.read())
    for m in members:
        if m != "rs/" and not m.startswith("rs/"):
            raise ValueError("%s: the legs add files under rs/ only, never to the release image's own tree" % m)
        top += 1
        if m == "rs/":
            if "rs" in names:
                top -= 1
                continue
            body += cpio_member(top, "rs", b"", 0o040755, 2)
            continue
        name, _, path = m.partition("=")
        if name in names:
            raise ValueError("%s is in the archive already" % name)
        with open(path, "rb") as f:
            body += cpio_member(top, name, f.read(), 0o100755, 1)
        names.append(name)
    body += cpio_member(top + 1, "TRAILER!!!", b"", 0, 1)
    with open(out, "wb") as f:
        f.write(body)
    return 0


# --- ops ----------------------------------------------------------------------------------------------------------

def read_ops(table):
    ops = []
    with open(table, encoding="utf-8") as f:
        text = f.read().split("\n")
    for line in text:
        if not line or line.startswith("#"):
            continue
        f = [x.strip() for x in line.split(" | ")]
        if len(f) != 5 or f[0] not in ("k", "-") or not f[4].isdigit():
            raise ValueError("%s: not five fields: %r" % (table, line))
        for x in f[1:4]:
            if "'" in x:
                raise ValueError("%s: a quote in %r" % (table, x))
        ops.append(f)
    if not 0 < len(ops) < 100:
        raise ValueError("%s: 1 to 99 requests" % table)
    return ops


def ops(table, out, only=None):
    lines = ["# written by tests/rs/guest/guest.py ops from %s%s: one authd request a step; exit K or 100 + K at"
             % (table, "" if only is None else " (its %s rows)" % only),
             "# the first answer or status that is not the table's, K the table's row, 0 when all are"]
    for k, (via, req, pw, ans, st) in enumerate(read_ops(table), 1):
        if only is not None and via != only:
            continue
        run = "kern authd" if via == "k" else "authd"
        lines.append("printf '%%s\\n%%s' '%s' '%s' | %s > /tmp/rs.ans; s=$?" % (req, pw, run))
        lines.append('echo "row %d status $s: $(cat /tmp/rs.ans)" >> "$HOME/rs.log"' % k)
        lines.append("grep -qxF '%s' /tmp/rs.ans || exit %d" % (ans, k))
        lines.append("[ $s = %s ] || exit %d" % (st, 100 + k))
    lines.append("exit 0")
    with open(out, "w", encoding="ascii") as f:
        f.write("\n".join(lines) + "\n")
    return 0


def status(table, wait):
    w = int(wait)
    if w & 0x7F:
        print("the script ended by signal %d" % (w & 0x7F))
        return 1
    code = (w >> 8) & 0xFF
    if code == 0:
        print("every request answered as the table says")
        return 0
    rows = read_ops(table)
    k, what = (code - 100, "status") if code > 100 else (code, "answer")
    if not 1 <= k <= len(rows):
        print("exit %d is no step of %s" % (code, table))
        return 1
    via, req, _, ans, st = rows[k - 1]
    print("request %d (%s%s): the %s is not %s" % (k, "kern " if via == "k" else "", req, what,
                                                   repr(ans) if what == "answer" else st))
    return 1


def main(argv):
    if not argv:
        sys.exit(__doc__)
    cmd, a = argv[0], argv[1:]
    if cmd == "keys" and len(a) == 1:
        print(",".join(key_names(a[0])))
        return 0
    if cmd == "marks" and len(a) == 2:
        why = check_marks(transcript_lines(a[0]), read_marks(a[1]))
        print("FAIL: " + why if why else "PASS: %d marks" % len(read_marks(a[1])))
        return 1 if why else 0
    if cmd == "pool" and a:
        return pool(a)
    if cmd == "vol" and len(a) == 2:
        return vol(a[0], a[1])
    if cmd == "card" and len(a) == 3:
        return card(*a)
    if cmd == "color" and len(a) == 3:
        return color(*a)
    if cmd == "differ" and len(a) == 3:
        return differ(*a)
    if cmd == "sheet" and (len(a) == 4 or (len(a) == 5 and a[4] == "moved")):
        return sheet(*a)
    if cmd == "png" and len(a) == 5:
        return png(*a)
    if cmd == "cpio" and len(a) >= 2:
        return cpio(a[0], a[1], a[2:])
    if cmd == "ops" and len(a) in (2, 3) and a[2:] in ([], ["k"], ["-"]):
        return ops(*a)
    if cmd == "status" and len(a) == 2:
        return status(*a)
    sys.exit(__doc__)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
