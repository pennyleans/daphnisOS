#!/usr/bin/env python3
"""tests/hw/hotplug.py BUILD CC OUTDIR (run from the checkout): HP-1 under QEMU, the user flavor with no PS/2 (i8042=off), a qemu-xhci with a
usb-mouse from boot and no keyboard. While mkeys pid 38 waits, a usb-kbd is added through QMP and a, b, c are typed;
while mkeys pid 39 waits, a is pressed and held, the keyboard is removed (the kernel lets the key go), a new one is
added and b, c are typed; mmouse 40 and 41 get check.sh's mouse through the HMP monitor. Then the same boot with
the keyboard there from the start, typed the same way. Prints one line a fact; exit status 1 when one fails:
the mkeys and mmouse lines of both runs equal tests/expected/user.serial's, the hot plug lines are in the
transcript, and the pool's free frames at the end are the same in both runs (nothing kept by the two plugs)."""
import json, os, re, socket, subprocess, sys, time

build, cc, out = sys.argv[1], sys.argv[2], sys.argv[3]
os.makedirs(out, exist_ok=True)
MOUSE = ["mouse_move 10 -5", "mouse_button 1", "mouse_button 0", "mouse_button 2", "mouse_button 0"]


def lines(path):
    try:
        return open(path, errors="replace").read().splitlines()
    except OSError:
        return []


def wait_line(path, pat, after=0, secs=90):
    end = time.monotonic() + secs
    while time.monotonic() < end:
        ls = lines(path)
        for i in range(after, len(ls)):
            if re.search(pat, ls[i]):
                return i + 1
        time.sleep(0.05)
    raise SystemExit("hotplug: no line /%s/ in %s" % (pat, path))


class Qmp:
    def __init__(self, path):
        for _ in range(200):
            try:
                self.s = socket.socket(socket.AF_UNIX)
                self.s.connect(path)
                break
            except OSError:
                time.sleep(0.05)
        self.f = self.s.makefile("rw")
        self.f.readline()
        self.cmd("qmp_capabilities")

    def cmd(self, c, a=None):
        m = {"execute": c}
        if a is not None:
            m["arguments"] = a
        self.f.write(json.dumps(m) + "\n")
        self.f.flush()
        while True:
            r = json.loads(self.f.readline())
            if "return" in r or "error" in r:
                return r

    def keys(self, ks, down):
        self.cmd("input-send-event", {"events": [{"type": "key", "data": {"down": down, "key": {"type": "qcode", "data": k}}} for k in ks]})

    def tap(self, k):
        self.keys([k], True)
        time.sleep(0.08)
        self.keys([k], False)
        time.sleep(0.15)


def hmp(path, cmds):
    s = socket.socket(socket.AF_UNIX)
    s.connect(path)
    for c in cmds:
        s.sendall((c + "\n").encode())
        time.sleep(0.15)
    s.close()


def run(name, plug):
    t = os.path.join(out, "%s-%s.txt" % (name, cc))
    q = t + ".qmp"
    mon = t + ".mon"
    for p in (t, q, mon):               # an old transcript would answer the waits before QEMU starts
        if os.path.exists(p):
            os.unlink(p)
    extra = "-machine pc,i8042=off -device qemu-xhci,id=xhci -device usb-mouse,bus=xhci.0 -qmp unix:%s,server=on,wait=off" % q
    if not plug:
        extra += " -device usb-kbd,bus=xhci.0,id=k0"
    env = dict(os.environ, QEMU_TIMEOUT="120", QEMU_EXTRA=extra, STDIN_FILE="tests/image/stdin.txt", MONITOR=mon,
               INITRD=os.path.join(build, "user", "initrd.cpio"), MEM="128")
    p = subprocess.Popen(["tools/run-qemu.sh", os.path.join(build, "%s-user" % cc, "kernel32.elf"), t], env=env,
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    try:
        return drive(t, q, mon, p, plug)
    finally:
        if p.poll() is None:
            p.kill()


def drive(t, q, mon, p, plug):
    at = wait_line(t, r"^daphnis: run mkeys pid 38 \(device\)$")
    m = Qmp(q)
    if plug:
        m.cmd("device_add", {"driver": "usb-kbd", "bus": "xhci.0", "id": "k1"})
        at = wait_line(t, r"boot keyboard, after boot$", at)
    for k in ("a", "b", "c"):
        m.tap(k)
    at = wait_line(t, r"^daphnis: run mkeys pid 39 \(device\)$", at)
    if plug:
        m.keys(["a"], True)
        time.sleep(0.3)
        m.cmd("device_del", {"id": "k1"})
        at = wait_line(t, r"keyboard gone$", at)
        m.cmd("device_add", {"driver": "usb-kbd", "bus": "xhci.0", "id": "k2"})
        at = wait_line(t, r"boot keyboard, after boot$", at)
        for k in ("b", "c"):
            m.tap(k)
    else:
        for k in ("a", "b", "c"):
            m.tap(k)
    for pid in (40, 41):
        at = wait_line(t, r"^daphnis: run mmouse pid %d \(device\)$" % pid, at)
        hmp(mon, MOUSE)
    rc = p.stdout.read().strip()
    p.wait()
    return t, rc


def blocks(ls):
    """The lines after each mkeys or mmouse run line up to the next daphnis: line."""
    out, keep = [], False
    for ln in ls:
        if re.match(r"^daphnis: run (mkeys|mmouse) pid \d+ \(device\)$", ln):
            keep = True
            out.append(ln)
            continue
        if ln.startswith("daphnis: usb:"):
            continue                   # the kernel's own lines of a plug, printed while mkeys waits
        if ln.startswith("daphnis:"):
            keep = False
        if keep:
            out.append(ln)
    return out


def free_line(ls):
    return next((ln for ln in reversed(ls) if ln.startswith("daphnis: pool frames free")), None)


want = blocks(lines("tests/expected/user.serial"))
fails = 0


def say(ok, what):
    global fails
    print("%s  %s %s" % ("PASS" if ok else "FAIL", cc, what))
    fails += 0 if ok else 1


hp, rc1 = run("hotplug", True)
st, rc2 = run("boot", False)
hl, sl = lines(hp), lines(st)
say(rc1 == "33", "hot plug run: QEMU status %s (want 33)" % rc1)
say(blocks(hl) == want, "hot plug run: mkeys and mmouse lines are user.serial's (%d lines)" % len(want))
say(sum(1 for ln in hl if ln.endswith("boot keyboard, after boot")) == 2 and
    sum(1 for ln in hl if ln.endswith("keyboard gone")) == 1, "hot plug run: two keyboards taken after boot, one gone")
say(rc2 == "33" and blocks(sl) == want, "boot run (keyboard from the start): the same lines, status %s" % rc2)
say(free_line(hl) is not None and free_line(hl) == free_line(sl),
    "the pool at the end, hot plug %r, boot %r: equal" % (free_line(hl), free_line(sl)))
sys.exit(1 if fails else 0)
# SPDX-License-Identifier: Apache-2.0
