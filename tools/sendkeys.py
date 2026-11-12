#!/usr/bin/env python3
"""tools/sendkeys.py SOCKET TRANSCRIPT MARK INPUT [MARK INPUT ...]: sends input to QEMU through its monitor
(tools/run-qemu.sh with MONITOR=SOCKET) once a line of TRANSCRIPT starts with MARK (MARK@@N: its Nth such line). After
other text on a line, where a program's title can stand, MARK does not count (AC-R1, tools/guestlines.py); a MARK that
begins with `...` is a fragment of a line and counts anywhere (`...|bin/cat| var`). INPUT is a comma-separated list
of QEMU key names (a,b,c: each a `sendkey`, which holds the key 100 ms) or whole monitor commands
(`mouse_move 10 -5`, `mouse_button 1`: an item with a space is sent as it is). Items follow each other 300 ms
apart, so they reach the guest in order. An item `@TARGET` or `@TARGET DX DY` puts the pointer on a target the desk's
own lines place, at the moment it is sent, never at a fixed offset (point below): the pointer is first driven to the
screen's top left, where hdesk holds it, then moved to the target in steps of 100 px or less. Gives up 40 s after the start (SENDKEYS_WAIT seconds when set: W-4's
desk waits for a doom run). Prints what it sent; exits 1 when a mark never showed (F-2, F-3; docs/specs/2026-11-05-f-surface.md section 6)."""
import math
import os
import re
import socket
import sys
import time

import guestlines


def wait_for(transcript, mark, deadline):
    text, n = mark, 1
    if "@@" in mark:                     # SP-3: MARK@@N waits for MARK's Nth time in the transcript
        text, k = mark.rsplit("@@", 1)
        n = int(k)
    anywhere = text.startswith("...")    # a fragment of a line, found anywhere
    want = text[3:].encode() if anywhere else text.encode()
    while time.monotonic() < deadline:
        try:
            with open(transcript, "rb") as f:
                data = f.read()
            got = data.count(want) if anywhere else guestlines.count(data, want)
            if got >= n:
                return True
        except OSError:
            pass
        time.sleep(0.05)
    return False


BAR_1X, CELL = 28, 8                     # hdesk.ci: the bar's height and a clock cell at 1x


def last(lines, rx):
    """The last line matching rx (from its start), or None."""
    for ln in reversed(lines):
        m = re.match(rx, ln)
        if m:
            return m
    return None


def point(text, item):
    """Where `@TARGET [DX DY]` stands on the screen, in device pixels, and the screen's size, from the desk's lines in
    text so far. The scale is the last `hdesk: scale N`, else the bar's height in `hdesk: screen WxH plane PWxPH`.
    Targets, each its center plus DX, DY at 1x times the scale:
      squares  the system panel's four squares, a 24 px slot 8 px left of the clock, which is CELL a character of
               the last `hdesk: clock |...|` and 8 px from the right (hdesk.ci bar_geom);
      chevron  the tray's chevron, the 24 px slot 8 px left of the squares;
      ov       the overlay's frame, the last `hdesk: win N kind 0 ... frame X,Y WxH` (a panel, a plate, the plane):
               its top left plus DX, DY."""
    lines = guestlines.lines(text)
    word = item[1:].split()
    name, dx, dy = word[0], int(word[1]) if len(word) > 1 else 0, int(word[2]) if len(word) > 2 else 0
    scr = last(lines, r"hdesk: screen (\d+)x(\d+) plane (\d+)x(\d+)$")
    if not scr:
        raise ValueError("no `hdesk: screen` line")
    w, h = int(scr.group(1)), int(scr.group(2))
    sc = last(lines, r"hdesk: scale (\d+)")
    sc = int(sc.group(1)) if sc else (h - int(scr.group(4))) // BAR_1X
    if name == "ov":
        f = last(lines, r"hdesk: win \d+ kind 0 .* frame (\d+),(\d+) ")
        if not f:
            raise ValueError("no overlay frame line")
        return int(f.group(1)) + dx * sc, int(f.group(2)) + dy * sc, w, h
    clk = last(lines, r"hdesk: clock \|(.*)\|$")
    if not clk or name not in ("squares", "chevron"):
        raise ValueError("no clock line" if not clk else "no target %r" % name)
    x = w // sc - 8 - (CELL * len(clk.group(1)) + 16) - 8 - 24
    if name == "chevron":
        x = x - 8 - 24
    return (x + 12 + dx) * sc, (BAR_1X // 2 + dy) * sc, w, h


def moves(x, y, w, h):
    """The monitor commands that drive the pointer to the top left and then to (x, y)."""
    out = ["mouse_move -100 -100"] * (math.ceil(max(w, h) / 100) + 1)
    while x > 0 or y > 0:
        sx, sy = min(x, 100), min(y, 100)
        out.append("mouse_move %d %d" % (sx, sy))
        x, y = x - sx, y - sy
    return out


def main(argv):
    sock, transcript = argv[0], argv[1]
    deadline = time.monotonic() + float(os.environ.get("SENDKEYS_WAIT", "40"))
    for mark, keys in zip(argv[2::2], argv[3::2]):
        if not wait_for(transcript, mark, deadline):
            print("sendkeys: no line %r within the time" % mark)
            return 1
        s = socket.socket(socket.AF_UNIX)
        s.settimeout(5)
        s.connect(sock)
        time.sleep(0.2)
        for k in keys.split(","):
            if k.startswith("@"):
                with open(transcript, "rb") as f:
                    x, y, w, h = point(f.read().decode("latin-1"), k)
                print("sendkeys: %s at %d,%d" % (k, x, y))
                for c in moves(x, y, w, h):
                    s.sendall((c + "\n").encode())
                    time.sleep(0.02)
                time.sleep(0.3)
                continue
            s.sendall(((k if " " in k else "sendkey " + k) + "\n").encode())
            time.sleep(0.3)
        s.close()
        print("sendkeys: typed %s after %r" % (keys, mark))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
