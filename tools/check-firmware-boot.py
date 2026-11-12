#!/usr/bin/env python3
"""tools/check-firmware-boot.py STICK CODE VARS MEM ACCEL RUN: the boots of tools/check-firmware-boot.sh (RG-1).

STICK is the release image file, booted as a reader boots it: through OVMF and the stick's own GRUB from the removable
path (EFI/BOOT/BOOTX64.EFI), as usb-storage on qemu-xhci, no -kernel, nothing added. CODE is OVMF's code file
(read-only pflash) and VARS its variable store, copied fresh to RUN before each boot, so no NVRAM passes from one boot
to the next; CODE `-` means VARS is a combined OVMF.fd, copied fresh the same way. MEM is QEMU's -m, ACCEL kvm or tcg.
The display is a bochs-display whose EDID asks 1920x1080: OVMF takes the EDID's preferred mode, GRUB keeps it
(gfxpayload=keep), and the desk comes up at it (QEMU's default VGA leaves OVMF at 640x480).

The release boot line has daphnis.uart=0, so the guest says nothing on a serial port: the screen (QMP screendump) and
the volume QEMU leaves are what this reads. A screen is the frame below the bar (the bar's clock moves); it is up when
it differs from the one before, is the desk's (its last pixel is not black, as OVMF's logo, GRUB's and the kernel's
early screens are; a Console is nearly one color), is not a single color, and holds for SETTLE seconds. A new screen (the Console after
the form or the sign-in) must differ from the one before in at least NEW of its pixels: the form's own "making the
account" state, the fields wiped, differs in 0.2 %, the Console in 2.4 %.
  boot 1   the first boot's Parent form at 1920x1080; the Parent rel (check-release.py's passphrase), its session's
           Console; `echo fw-boot > fwboot.txt`; Super+Shift+Q twice, and QEMU ends on its own through ACPI S5
           (QMP SHUTDOWN, reason guest-shutdown, exit status 0); a hang is a failure. Then the volume: the account
           store names rel and /rel/fwboot.txt holds the line.
  boot 2   the same file again, a fresh variable store: the sign-in screen (not the first boot's form), the passphrase,
           rel's Console; `cat fwboot.txt > back.txt`; the shut down again. Then the volume: back.txt holds the line,
           owned as fwboot.txt is, so the second boot signed in as rel and read back the file the first saved.
It prints the QEMU command once, before boot 1 (boot 2 runs the same command). One PASS or FAIL line a check; exits 1
on any FAIL. Screens it read are saved under RUN as PPM."""
import hashlib
import json
import os
import re
import shlex
import shutil
import socket
import subprocess
import sys
import time

import importlib.util

_spec = importlib.util.spec_from_file_location("check_release", os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                                             "check-release.py"))
check_release = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_release)
PASS = check_release.PASS          # the first boot's passphrase, the release gate's
keys = check_release.keys

MODE = (1920, 1080)
BAR = 48                           # rows of the bar at the top, left out of a screen's hash: its clock moves
SETTLE = 10
NEW = 0.01
STRIDE = 5                         # every fifth pixel, for NEW
TOKEN = "fw-boot"
fails = 0


def line(ok, label, detail=""):
    global fails
    if not ok:
        fails += 1
    print("%s  %s%s" % ("PASS" if ok else "FAIL", label, "" if ok or not detail else ": " + detail), flush=True)


class Qemu:
    """One boot: QEMU with a QMP socket; screendumps, keys through the human monitor's sendkey, and its events."""

    def __init__(self, cmd, sock):
        self.events = []
        self.start = time.monotonic()
        self.proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        for _ in range(100):
            try:
                self.s = socket.socket(socket.AF_UNIX)
                self.s.connect(sock)
                break
            except OSError:
                self.s.close()
                if self.proc.poll() is not None:
                    raise SystemExit("check-firmware-boot: QEMU ended at once: %s" %
                                     self.proc.stderr.read().decode("utf-8", "replace").strip())
                time.sleep(0.1)
        else:
            raise SystemExit("check-firmware-boot: no QMP socket at %s" % sock)
        self.f = self.s.makefile("rw")
        json.loads(self.f.readline())
        self.cmd("qmp_capabilities")

    def secs(self):
        return int(time.monotonic() - self.start)

    def cmd(self, name, args=None):
        self.f.write(json.dumps({"execute": name, **({"arguments": args} if args else {})}) + "\n")
        self.f.flush()
        while True:
            ln = self.f.readline()
            if not ln:
                return None                  # QEMU has ended
            r = json.loads(ln)
            if "event" in r:
                self.events.append(r)
            else:
                return r

    def send(self, seq):
        """Keys as check-release.py types them: sendkey names, comma separated, 300 ms a key."""
        for k in seq.split(","):
            self.cmd("human-monitor-command", {"command-line": "sendkey " + k})
            time.sleep(0.3)

    def screen(self, path):
        """(width, height, sha256 of the rows below the bar, distinct colors in a sample, those rows), or None once
        QEMU has ended."""
        if self.proc.poll() is not None or self.cmd("screendump", {"filename": path}) is None:
            return None
        try:
            with open(path, "rb") as f:
                b = f.read()
        except OSError:
            return None
        m = re.match(rb"P6\s+(\d+)\s+(\d+)\s+255\s", b)
        if not m:
            return None
        w, h, at = int(m.group(1)), int(m.group(2)), m.end()
        px = b[at + 3 * w * BAR:]
        return w, h, hashlib.sha256(px).hexdigest(), len({px[k:k + 3] for k in range(0, len(px) - 2, 3 * 997)}), px

    def wait_screen(self, run, tag, before, secs, least=0.0, settle=SETTLE):
        """The next screen up after `before` (a screen, or None), differing from it in at least `least` of its pixels:
        (w, h, hash, rows) once it has held `settle` seconds (0: at once, read every quarter second), the frame saved
        as RUN/TAG.ppm; None after secs or when QEMU ends."""
        end = time.monotonic() + secs
        path = os.path.join(run, tag + ".ppm")
        held, since = None, 0.0
        while time.monotonic() < end:
            s = self.screen(path)
            if s is None:
                return None
            if s[3] > 1 and s[4][-3:] != b"\0\0\0" and (before is None or (s[2] != before[2] and changed(before[3], s[4]) >= least)):
                if settle == 0:
                    return s[0], s[1], s[2], s[4]
                if held != s[2]:
                    held, since = s[2], time.monotonic()
                elif time.monotonic() - since >= settle:
                    return s[0], s[1], s[2], s[4]
            else:
                held = None
            time.sleep(0.25 if settle == 0 else 2)
        return None

    def wait_end(self, secs):
        """QEMU's exit status, or None when it still runs after secs (then it is killed)."""
        try:
            rc = self.proc.wait(secs)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()
            return None
        try:
            for ln in self.f:
                r = json.loads(ln)
                if "event" in r:
                    self.events.append(r)
        except (OSError, ValueError):
            pass
        return rc

    def shutdown_reason(self):
        return next((e.get("data", {}).get("reason") for e in self.events if e.get("event") == "SHUTDOWN"), None)


def changed(a, b):
    """The share of pixels (every STRIDE-th) that differ between two screens' rows; 1.0 when their sizes differ."""
    if len(a) != len(b):
        return 1.0
    step = 3 * STRIDE
    return sum(a[k:k + 3] != b[k:k + 3] for k in range(0, len(a) - 2, step)) / max(1, len(a) // step)


def shut_down(q, run, n, last):
    """Super+Shift+Q, which opens the plane with Shut Down armed, and again as soon as the plane shows, inside the 2 s
    the desk gives the second press (FF-R6 B, hdesk.ci pw_chord): the desk's Shut Down. QEMU must then end on its own,
    through S5."""
    q.send("meta_l-shift-q")
    armed = q.wait_screen(run, "boot%d-armed" % n, last, 60, NEW, settle=0)
    q.send("meta_l-shift-q")
    if not armed:
        line(False, "shut down %d: Super+Shift+Q opens the plane" % n, "no plane in 60 s")
    t0 = q.secs()
    rc = q.wait_end(900)
    why = q.shutdown_reason()
    line(rc == 0 and why == "guest-shutdown",
         "shut down %d: Super+Shift+Q twice ends QEMU on its own through ACPI S5 (SHUTDOWN guest-shutdown, exit 0) "
         "%d s after the second press" % (n, q.secs() - t0),
         "QEMU still ran 900 s after the second press (a hang), killed" if rc is None
         else "exit %s, SHUTDOWN reason %s" % (rc, why))


def volume(stick, run, n):
    """Partition 2 of STICK cut to RUN/volume-N.img (HW-8: the volume)."""
    d = subprocess.run(["sfdisk", "-d", stick], capture_output=True, text=True).stdout
    m = re.search(r"^\S*2 : start= *(\d+), size= *(\d+),", d, re.M)
    if not m:
        raise SystemExit("check-firmware-boot: %s has no partition 2" % stick)
    img = os.path.join(run, "volume-%d.img" % n)
    with open(stick, "rb") as src, open(img, "wb") as dst:
        src.seek(int(m.group(1)) * 512)
        left = int(m.group(2)) * 512
        while left:
            b = src.read(min(left, 1 << 22))
            if not b:
                break
            dst.write(b)
            left -= len(b)
    return img


def cat(img, path):
    r = subprocess.run(["debugfs", "-R", "cat " + path, img], capture_output=True)
    return r.stdout if r.returncode == 0 else b""


def names_rel(store):
    """An `acct` line of the store (user/ci/acct.ci) with name=rel."""
    return any(ln.startswith(b"acct ") and b" name=rel " in ln + b" " for ln in store.split(b"\n"))


def owner(img, path):
    r = subprocess.run(["debugfs", "-R", "stat " + path, img], capture_output=True, text=True)
    m = re.search(r"User:\s+(\d+)", r.stdout)
    return int(m.group(1)) if m else None


def boot_cmd(stick, code, vars_, mem, accel, run):
    fw = ["-drive", "if=pflash,format=raw,file=" + os.path.join(run, "ovmf.fd")] if code == "-" else [
        "-drive", "if=pflash,format=raw,readonly=on,file=" + code,
        "-drive", "if=pflash,format=raw,file=" + os.path.join(run, "vars.fd")]
    return (["qemu-system-x86_64", "-accel", accel, "-cpu", "max", "-m", mem] + fw +
            ["-vga", "none", "-device", "bochs-display,edid=on,xres=%d,yres=%d" % MODE,
             "-device", "qemu-xhci", "-drive", "if=none,id=stick,format=raw,file=" + stick,
             "-device", "usb-storage,drive=stick",
             "-display", "none", "-qmp", "unix:%s,server=on,wait=off" % os.path.join(run, "qmp.sock")])


def fresh_vars(code, vars_, run):
    shutil.copyfile(vars_, os.path.join(run, "ovmf.fd" if code == "-" else "vars.fd"))


def main(argv):
    if len(argv) != 6:
        sys.exit(__doc__.split("\n")[0])
    stick, code, vars_, mem, accel, run = argv
    os.makedirs(run, exist_ok=True)
    sock = os.path.join(run, "qmp.sock")
    cmd = boot_cmd(stick, code, vars_, mem, accel, run)
    print("command: " + shlex.join(cmd), flush=True)
    w, h = MODE

    # Boot 1: first boot, a Parent, a file, Shut Down.
    fresh_vars(code, vars_, run)
    q = Qemu(cmd, sock)
    form = q.wait_screen(run, "boot1-form", None, 900)
    line(bool(form) and form[:2] == MODE,
         "first boot: OVMF and the stick's GRUB bring up the Parent form at %dx%d, %d s after power on (no -kernel)"
         % (w, h, q.secs()),
         "no screen held in 900 s" if not form else "the screen is %dx%d, not %dx%d" % (form[0], form[1], w, h))
    if not form:
        q.wait_end(0)
        return 1
    time.sleep(2)
    q.send("r,e,l,tab,%s,tab,%s,ret" % (keys(PASS), keys(PASS)))
    t0 = q.secs()
    desk = q.wait_screen(run, "boot1-desk", form, 1200, NEW)
    line(bool(desk), "first boot: the Parent rel is made and its session's Console comes up, %d s after Enter"
         % (q.secs() - t0), "the form's screen held for 1200 s")
    if not desk:
        q.wait_end(0)
        return 1
    q.send("%s,spc,shift-dot,spc,%s,ret" % (keys("echo " + TOKEN), keys("fwboot") + ",dot,t,x,t"))
    saved = q.wait_screen(run, "boot1-saved", desk, 120)
    shut_down(q, run, 1, saved or desk)
    v1 = volume(stick, run, 1)
    store = cat(v1, "/.daphnis/accounts")
    got = cat(v1, "/rel/fwboot.txt")
    line(store.startswith(b"daphnis-accounts 1") and names_rel(store) and got == (TOKEN + "\n").encode(),
         "volume after boot 1: the account store names rel; /rel/fwboot.txt holds `%s`" % TOKEN,
         "store %s; /rel/fwboot.txt %r" % ("names rel" if names_rel(store) else "has no rel" if store else
                                           "missing", got))

    # Boot 2: the same file, a fresh variable store; sign in, read the file back, Shut Down.
    fresh_vars(code, vars_, run)
    q = Qemu(cmd, sock)
    sign = q.wait_screen(run, "boot2-signin", None, 900)
    line(bool(sign) and sign[:2] == MODE and sign[2] != form[2],
         "second boot: the same image file through OVMF and GRUB again, a fresh variable store: the sign-in screen at "
         "%dx%d, not the first boot's form, %d s after power on" % (w, h, q.secs()),
         "no screen held in 900 s" if not sign else "the first boot's form again: the account was not kept"
         if sign[2] == form[2] else "the screen is %dx%d" % sign[:2])
    if not sign:
        q.wait_end(0)
        return 1
    time.sleep(2)
    q.send(keys(PASS) + ",ret")
    t0 = q.secs()
    desk2 = q.wait_screen(run, "boot2-desk", sign, 1200, NEW)
    line(bool(desk2), "sign in: rel's session opens on its passphrase, %d s after Enter" % (q.secs() - t0),
         "the sign-in screen held for 1200 s")
    if not desk2:
        q.wait_end(0)
        return 1
    q.send("%s,spc,shift-dot,spc,%s" % (keys("cat fwboot") + ",dot,t,x,t", keys("back") + ",dot,t,x,t,ret"))
    read = q.wait_screen(run, "boot2-read", desk2, 120)
    shut_down(q, run, 2, read or desk2)
    v2 = volume(stick, run, 2)
    back = cat(v2, "/rel/back.txt")
    same = owner(v2, "/rel/back.txt")
    line(back == (TOKEN + "\n").encode() and same is not None and same == owner(v2, "/rel/fwboot.txt")
         and names_rel(cat(v2, "/.daphnis/accounts")),
         "read back: /rel/back.txt holds fwboot.txt's `%s`, owned as fwboot.txt (uid %s): the second boot signed in "
         "as rel and read the file the first saved; the account store still names rel" % (TOKEN, same),
         "/rel/back.txt %r, owner %s, fwboot.txt's %s" % (back, same, owner(v2, "/rel/fwboot.txt")))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
