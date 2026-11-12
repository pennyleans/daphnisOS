#!/usr/bin/env python3
"""tools/k12.py: K-12, the speed bar of docs/specs/2026-11-07-ds-desk-speed.md section 4, measured (RV-6 A).

Boots the hdesk flavor with daphnis.k12=1 under KVM at each mode, types through the QEMU monitor and reads the
k12 lines of the transcript (the kernel's clock, microseconds since boot, src/k12.ci):
  k12 key US CODE      a key press, stamped at its interrupt (rt/ps2.c)
  k12 mark WHAT US     the desk: 1 a drain drawn (a terminal's output on the screen), 2 a switcher frame drawn
  k12 frame PID US     a copy of a placed window whose pages were written (a frame shown) ended
Legs at each mode: keys (200 letters 100 ms apart: key to the next mark 1), screen (`seq 200`, 5 times: Enter to
the last mark 1 before 300 ms of quiet), switcher (Alt+Tab 20 times: the Tab press to the next mark 2), busy keys
(the keys leg again with `seq 1000000000 > /dev/null` running in a second terminal, SCHED-1). Then, at 1080 x 1920
1x, Doom: `./doom --sealed` in a monocle window (3x), frames shown a second over its run.

Usage: tools/k12.py BUILD [MODE ...]. BUILD holds gcc-hdesk/kernel32.elf and hdesk/initrd.cpio (make
O=BUILD FLAVORS=hdesk). A MODE is WxH:S (default 1920x1080:1 1920x1080:2 1080x1920:1 1080x1920:2). Writes
BUILD/k12/MODE.txt (each transcript) and BUILD/k12/report.md, and prints the report. Needs /dev/kvm
(K12_KVM=0 runs under TCG: a smoke of the tool, not a measure). The QEMU
display's refresh is outside the measure: the clock stops when the desk's last write of the frame is done."""
import os
import re
import socket
import statistics
import subprocess
import sys
import time

import guestlines

BAR = {"key_median": 16.0, "key_p99": 20.0, "screen": 20.0, "switch": 10.0, "doom_fps": 35.0}
LETTERS = "abcdefghijklmnopqrstuvwxyz"
READY = "hdesk: bar desktop 1 |Console| var |/|"


class Monitor:
    def __init__(self, path, deadline=60):
        end = time.monotonic() + deadline
        while not os.path.exists(path):
            if time.monotonic() > end:
                raise SystemExit("k12: no monitor at %s" % path)
            time.sleep(0.05)
        self.s = socket.socket(socket.AF_UNIX)
        self.s.connect(path)
        self.s.setblocking(False)

    def send(self, item, gap=0.1):
        cmd = item if " " in item else "sendkey %s 20" % item
        self.s.sendall((cmd + "\n").encode())
        time.sleep(gap)
        try:
            self.s.recv(65536)
        except BlockingIOError:
            pass

    def type(self, text, gap=0.1):
        names = {" ": "spc", ">": "shift-dot", "/": "slash", ".": "dot", "-": "minus", "\n": "ret"}
        for ch in text:
            self.send(names.get(ch, ch), gap)


def wait_line(path, pattern, after=0, deadline=120):
    end = time.monotonic() + deadline
    rx = re.compile(pattern)
    while time.monotonic() < end:
        try:
            lines = guestlines.lines(open(path, errors="replace").read())
        except OSError:
            lines = []
        for i in range(after, len(lines)):
            if rx.search(lines[i]):
                return i + 1
        time.sleep(0.05)
    raise SystemExit("k12: no line /%s/ in %s" % (pattern, path))


def lines_of(path):
    return guestlines.lines(open(path, errors="replace").read())


def events(lines, lo, hi):
    keys, marks, frames = [], [], []
    for ln in lines[lo:hi]:
        f = ln.split()
        if len(f) >= 4 and f[0] == "k12" and f[1] == "key":
            keys.append((int(f[2]), int(f[3])))
        elif len(f) >= 4 and f[0] == "k12" and f[1] == "mark":
            marks.append((int(f[2]), int(f[3])))
        elif len(f) >= 4 and f[0] == "k12" and f[1] == "frame":
            frames.append((int(f[2]), int(f[3])))
    return keys, marks, frames


def next_mark(marks, what, t):
    for w, u in marks:
        if w == what and u >= t:
            return u
    return None


def p99(xs):
    s = sorted(xs)
    return s[min(len(s) - 1, int(0.99 * len(s)))]


def key_leg(mon, path, n=200):
    at = len(lines_of(path))
    mon.type("echo ")
    time.sleep(0.5)
    lo = len(lines_of(path))
    for k in range(n):
        mon.send(LETTERS[k % 26], 0.1)
    time.sleep(0.5)
    hi = len(lines_of(path))
    mon.send("ctrl-u", 0.3)
    keys, marks, _ = events(lines_of(path), lo, hi)
    lat = []
    for u, code in keys:
        m = next_mark(marks, 1, u)
        if m is not None:
            lat.append((m - u) / 1000.0)
    return lat, at


def screen_leg(mon, path, reps=5):
    out = []
    for _ in range(reps):
        mon.type("seq 200")
        time.sleep(0.3)
        lo = len(lines_of(path))
        mon.send("ret", 1.5)
        hi = len(lines_of(path))
        keys, marks, _ = events(lines_of(path), lo, hi)
        if not keys:
            continue
        t0 = keys[0][0]
        last = None
        for w, u in marks:
            if w == 1 and u >= t0 and (last is None or u - last < 300000):
                last = u
        if last is not None:
            out.append((last - t0) / 1000.0)
    return out


def switch_leg(mon, path, reps=20):
    out = []
    for _ in range(reps):
        lo = len(lines_of(path))
        mon.send("alt-tab", 0.6)
        hi = len(lines_of(path))
        keys, marks, _ = events(lines_of(path), lo, hi)
        tabs = [u for u, c in keys if c == 15]
        if tabs:
            m = next_mark(marks, 2, tabs[0])
            if m is not None:
                out.append((m - tabs[0]) / 1000.0)
    return out


def boot(build, mode, path, extra=""):
    mon = path + ".mon"
    if os.path.exists(mon):
        os.unlink(mon)
    env = dict(os.environ, MODE=mode, KVM=os.environ.get("K12_KVM", "1"), QEMU_TIMEOUT="600", MEM="128", POOL="max", MONITOR=mon,
               INITRD=os.path.join(build, "hdesk", "initrd.cpio"), APPEND=("daphnis.k12=1 " + extra).strip())
    here = os.path.dirname(os.path.abspath(__file__))
    q = subprocess.Popen([os.path.join(here, "run-qemu.sh"), os.path.join(build, "gcc-hdesk", "kernel32.elf"), path],
                         env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    wait_line(path, "^" + re.escape(READY))
    return q, Monitor(mon)


def summary(xs):
    if not xs:
        return "no samples"
    return "n %d, median %.2f ms, p99 %.2f ms, max %.2f ms" % (len(xs), statistics.median(xs), p99(xs), max(xs))


def run_mode(build, spec, out):
    mode, scale = spec.split(":")
    path = os.path.join(out, "%s-%sx.txt" % (mode, scale))
    q, mon = boot(build, mode, path)
    rows = []
    try:
        if scale == "2":
            mon.send("meta_l-equal", 0.5)
            wait_line(path, r"^hdesk: scale 2")
        keys, _ = key_leg(mon, path)
        screen = screen_leg(mon, path)
        mon.send("meta_l-ret", 0.5)
        wait_line(path, r"^hdesk: terminal 1 slot")
        time.sleep(1)
        switch = switch_leg(mon, path)
        mon.type("seq 1000000000 >/dev/null\n")
        time.sleep(0.5)
        mon.send("alt-tab", 0.8)
        busy, _ = key_leg(mon, path)
        rows = [("key to glyph", keys), ("a screen of output", screen), ("switcher", switch),
                ("key to glyph, busy second terminal", busy)]
    finally:
        q.kill()
        q.wait()
    return rows


def doom_leg(build, out):
    path = os.path.join(out, "doom-1080x1920.txt")
    q, mon = boot(build, "1080x1920", path)
    try:
        mon.send("meta_l-z", 0.5)
        mon.type("./doom --sealed\n")
        at = wait_line(path, r"^hdesk: pixel \d+", deadline=240)
        wait_line(path, r"^hdesk: pixel \d+ ended", after=at, deadline=300)
    finally:
        q.kill()
        q.wait()
    _, _, frames = events(lines_of(path), 0, len(lines_of(path)))
    by = {}
    for pid, u in frames:
        by.setdefault(pid, []).append(u)
    if not by:
        return None, 0
    us = max(by.values(), key=len)
    if len(us) < 2:
        return None, len(us)
    return (len(us) - 1) / ((us[-1] - us[0]) / 1e6), len(us)


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    build = argv[0]
    specs = argv[1:] or ["1920x1080:1", "1920x1080:2", "1080x1920:1", "1080x1920:2"]
    out = os.path.join(build, "k12")
    os.makedirs(out, exist_ok=True)
    rep = ["# K-12 run", "", "| mode | leg | result | bar | holds |", "| --- | --- | --- | --- | --- |"]
    ok = True
    for spec in specs:
        for name, xs in run_mode(build, spec, out):
            if name == "a screen of output" or name == "switcher":
                bar = BAR["screen"] if name == "a screen of output" else BAR["switch"]
                holds = bool(xs) and statistics.median(xs) <= bar
                want = "median <= %g ms" % bar
            else:
                holds = bool(xs) and statistics.median(xs) <= BAR["key_median"] and p99(xs) <= BAR["key_p99"]
                want = "median <= 16, p99 <= 20 ms"
            ok = ok and holds
            rep.append("| %s | %s | %s | %s | %s |" % (spec, name, summary(xs), want, "yes" if holds else "NO"))
    fps, n = doom_leg(build, out)
    holds = fps is not None and fps >= BAR["doom_fps"]
    ok = ok and holds
    rep.append("| 1080x1920:1 | Doom at 3x, frames shown a second | %s | >= 35 | %s |" %
               ("%.1f over %d frames" % (fps, n) if fps else "%d frames" % n, "yes" if holds else "NO"))
    rep += ["", "RESULT: %s" % ("PASS, the bar holds at every mode" if ok else "FAIL"),
            "The QEMU display's refresh is outside the measure."]
    text = "\n".join(rep) + "\n"
    open(os.path.join(out, "report.md"), "w").write(text)
    print(text, end="")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
