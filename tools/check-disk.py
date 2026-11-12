#!/usr/bin/env python3
"""tools/check-disk.py TRANSCRIPT VOLUME PIN [--session SHELL IMAGE STDIN]: the checks of a boot with the
test volume (docs/specs/2026-11-05-p-disk.md section 5).
tools/check-disk.py --write WRITTEN LISTED ORIGINAL VOLUME PIN SHELL IMAGE WSTDIN LSTDIN: the checks of P-3's two
boots of one volume.

P-1:
  - the kernel names the volume's size: SECTORS * 512 is the size of VOLUME;
  - it printed `daphnis: disk SECTORS sha256 HEX` twice, at boot and at the end, and both HEX are the pin
    (the first field of the file PIN, as sha256sum writes it): what the kernel read through the device is
    the volume mkdisk.sh built;
  - the write probe read its pattern back and restored the sectors;
  - VOLUME, the file QEMU wrote and left, still has the pin's digest: the restore reached the file.

P-2, with --session: the block `daphnis: run sh pid 2` (the image's sh on the scripted input STDIN, the volume on
/home) against two oracles. Linux: SHELL (O/ubin/cish, DOS-3) runs as sh on the same input in a fresh directory
holding IMAGE's members and, as home/, the volume as `debugfs rdump` takes it out, with PATH that directory's bin/
only, so it runs the image's /bin; that directory reads as "/". debugfs: Linux's
directory has its own inodes, so each line `stat NAME ...` (and `statL NAME ...`, the target of a link) is
replaced by the volume's own inode as debugfs reads it: number, raw mode, links, owner, group, size, i_blocks,
atime, mtime, ctime. The output bytes and the exit status must be equal.

P-3, --write: WRITTEN is the boot of the pinned volume on WSTDIN, LISTED the next boot of the same volume (VOLUME,
the file QEMU left) on LSTDIN. WSTDIN's lines up to `echo -- grant` try to write without the grant: each must
print one line ending in ": Read-only file system". The rest runs `./grant disk ./sh` on a heredoc that writes
(the path, BU2-2: grant looks a bare name up in PATH first, which on Linux finds the host's sh):
from that line on the session must be Linux's, SHELL as sh on the same lines in a directory holding IMAGE's
members and ORIGINAL's dump as home/. LISTED's session must be Linux's on LSTDIN in the same directory after
that, the stat lines debugfs's on VOLUME. WRITTEN's first digest is the pin; its last and both of LISTED's are
VOLUME's digest (the second boot writes nothing); `e2fsck -fn` finds VOLUME clean.

Prints one line per check and exits 1 if any fails."""
import hashlib
import importlib.util
import os
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import guestlines  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def check_user():
    spec = importlib.util.spec_from_file_location("check_user", os.path.join(HERE, "check-user.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def debugfs_stat(volume, path):
    """The fields of `stat` -c '%i %f %h %u %g %s %b %X %Y %Z' for path on the volume, by debugfs."""
    r = subprocess.run(["debugfs", "-R", "stat " + path, volume], capture_output=True, text=True)
    t = r.stdout
    kind = {"regular": 0o100000, "directory": 0o040000, "symlink": 0o120000}
    m = re.search(r"Inode: (\d+)\s+Type: (\w+)\s+Mode:\s+(\d+)", t)
    if not m:
        return None
    mode = kind[m.group(2)] | int(m.group(3), 8)
    g = lambda pat: int(re.search(pat, t).group(1), 0)
    return "%s %x %d %d %d %d %d %d %d %d" % (
        m.group(1), mode, g(r"Links: (\d+)"), g(r"User:\s+(\d+)"), g(r"Group:\s+(\d+)"), g(r"Size: (\d+)"),
        g(r"Blockcount: (\d+)"), g(r"atime: (0x[0-9a-f]+)"), g(r"mtime: (0x[0-9a-f]+)"), g(r"ctime: (0x[0-9a-f]+)"))


def script_of(stdin):
    with open(stdin, "rb") as f:
        script = f.read()
    return script[:-1] if script.endswith(b"\x04") else script


def stage(cwd, image, volume):
    """IMAGE's members in cwd (their modes kept) and the volume's dump as cwd/home (FS-3: the volume is mounted at /home)."""
    for member, mode, body in check_user().members(image):
        if mode & 0o170000 == 0o040000:
            os.mkdir(os.path.join(cwd, member))
        else:
            with open(os.path.join(cwd, member), "wb") as f:
                f.write(body)
            os.chmod(os.path.join(cwd, member), mode & 0o777)
    home = os.path.join(cwd, "home")
    os.mkdir(home)
    subprocess.run(["debugfs", "-R", "rdump / " + home, volume], capture_output=True, check=True)


def run_sh(cwd, shell, script, stat_volume):
    """SHELL as sh on script in cwd with PATH cwd's bin/, cwd's path read as "/", each stat line debugfs's on
    stat_volume."""
    r = subprocess.run(["sh"], executable=shell, input=script, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, timeout=120, env={"PATH": os.path.join(cwd, "bin")}, cwd=cwd)
    root = os.path.realpath(cwd).encode()
    out = r.stdout.replace(root + b"/", b"/").replace(root, b"/")
    lines = []
    for line in out.split(b"\n"):
        m = re.match(rb"^(statL?) (\S+) ", line)
        if m:
            name = m.group(2).decode()
            path = name[len("home"):] or "/"
            if m.group(1) == b"statL":
                path = os.path.normpath(os.path.join(os.path.dirname(path), os.readlink(os.path.join(cwd, name))))
            fields = debugfs_stat(stat_volume, path)
            line = m.group(1) + b" " + m.group(2) + b" " + (fields or "debugfs: no such inode").encode()
        lines.append(line)
    end = ("signal", -r.returncode) if r.returncode < 0 else ("exit", r.returncode)
    return b"\n".join(lines), end


def session_oracle(volume, shell, image, stdin):
    with tempfile.TemporaryDirectory() as cwd:
        stage(cwd, image, volume)
        return run_sh(cwd, shell, script_of(stdin), volume)


def session_check(label, got, want_out, want_end):
    """One check: the one block of sh pid 2 has the oracle's bytes and end, and they are not empty; the differing
    lines printed."""
    ok = len(want_out) > 0 and len(got) == 1 and got[0][2] == want_out and got[0][3] == want_end
    if not ok:
        have = got[0][2] if got else b""
        for a, b in zip(have.split(b"\n"), want_out.split(b"\n")):
            if a != b:
                print("      daphnis: %r\n      oracle:  %r" % (a, b))
        if got:
            print("      end: daphnis %r, oracle %r" % (got[0][3], want_end))
    return (label + " (%d bytes, %s %d)" % (len(want_out), want_end[0], want_end[1]), ok)


def sh_blocks(raw):
    return [b for b in check_user().blocks(raw) if b[0] == "sh" and b[1] == 2]


def digests(text):
    return re.findall(r"^daphnis: disk (\d+) sha256 ([0-9a-f]{64})$", text, re.M)


MARK = b"echo -- grant\n"


def run_block(text, name, pid):
    """The block `daphnis: run NAME pid PID`: its output lines, its state digest and its end, or None."""
    m = re.search(r"^daphnis: run %s pid %d\n((?:(?!daphnis: ).*\n)*)((?:daphnis: (?:fault|state) .*\n)*)daphnis: (exit|signal) (\d+)$"
                  % (re.escape(name), pid), text, re.M)
    if not m:
        return None
    state = re.findall(r"^daphnis: state ([0-9a-f]{64})$", m.group(2), re.M)
    return m.group(1), state, (m.group(3), int(m.group(4)))


def k13_check(label, text):
    """K13 (BU-4e): the session left the image's msha on the volume; the kernel then ran the member (pid 3) and
    the volume's file (pid 4) alone, under one argv and comm: the same output, end and state digest."""
    a, b = run_block(text, "msha", 3), run_block(text, "/home/msha", 4)
    ok = a is not None and b is not None and a == b and len(a[1]) == 1 and a[2] == ("exit", 0)
    if not ok:
        print("      member %r\n      volume %r" % (a, b))
    return (label + ": /home/msha, loaded from the volume, has the output, exit and state digest of the image's msha", ok)


def write_main(args):
    written, listed, original, volume, pin_file, shell, image, wstdin, lstdin = args
    shell, image = os.path.abspath(shell), os.path.abspath(image)
    pin = open(pin_file, encoding="ascii").read().split()[0]
    with open(volume, "rb") as f:
        left = hashlib.sha256(f.read()).hexdigest()
    wraw, lraw = open(written, "rb").read(), open(listed, "rb").read()
    wtext, ltext = wraw.decode("utf-8", "replace"), lraw.decode("utf-8", "replace")
    wscript, lscript = script_of(wstdin), script_of(lstdin)
    before, _, after = wscript.partition(MARK)
    tries = [l for l in before.split(b"\n") if l.strip()]
    checks = []
    wd, ld = digests(wtext), digests(ltext)
    checks.append(("written: the boot digest is the pin, the last is the volume QEMU left",
                   len(wd) == 2 and wd[0][1] == pin and wd[1][1] == left))
    checks.append(("written: the write probe read its pattern back and restored the sectors",
                   "daphnis: disk write probe: the pattern read back equal, the sectors restored"
                   in guestlines.lines(wtext)))
    checks.append(("listed: both digests are the volume QEMU left (the second boot wrote nothing)",
                   len(ld) == 2 and all(h == left for _, h in ld)))
    got = sh_blocks(wraw)
    have = got[0][2] if len(got) == 1 else b""
    head, sep, tail = have.partition(b"-- grant\n")
    refused = [l for l in head.split(b"\n") if l]
    # EROFS in each program's own words: the native tools say `Read-only file system`, cish (a redirect) says it in
    # lower case
    checks.append(("without the grant, each of the %d writes refused: Read-only file system" % len(tries),
                   bool(sep) and len(refused) == len(tries) and all(l.lower().endswith(b": read-only file system") for l in refused)))
    with tempfile.TemporaryDirectory() as cwd:
        stage(cwd, image, original)
        want_w, end_w = run_sh(cwd, shell, MARK + after, volume)
        want_l, end_l = run_sh(cwd, shell, lscript, volume)
    checks.append(session_check("written: with the grant the session is Linux's on a debugfs dump",
                                [(g[0], g[1], sep + tail, g[3]) for g in got], want_w, end_w))
    checks.append(session_check("listed: the next boot's session is Linux's after the same writes, debugfs's inodes in the stat lines",
                                sh_blocks(lraw), want_l, end_l))
    checks.append(k13_check("written", wtext))
    checks.append(k13_check("listed", ltext))
    r = subprocess.run(["e2fsck", "-fn", volume], capture_output=True, text=True)
    checks.append(("e2fsck -fn finds the volume QEMU left clean", r.returncode == 0))
    if r.returncode != 0:
        print("      " + r.stdout.replace("\n", "\n      "))
    return checks


def main():
    args = sys.argv[1:]
    if args[:1] == ["--write"]:
        report(write_main(args[1:]))
    transcript, volume, pin_file = args[:3]
    session = args[4:7] if len(args) >= 7 and args[3] == "--session" else None
    raw = open(transcript, "rb").read()
    text = raw.decode("utf-8", errors="replace")
    pin = open(pin_file, encoding="ascii").read().split()[0]
    with open(volume, "rb") as f:
        left = hashlib.sha256(f.read()).hexdigest()
    size = os.path.getsize(volume)
    checks = []
    m = re.search(r"^daphnis: disk (?:virtio-blk|usb-storage), (\d+) sectors, \d+ frames held$", text, re.M)
    checks.append(("the kernel found the device and names the volume's size", m is not None and int(m.group(1)) * 512 == size))
    lines = re.findall(r"^daphnis: disk (\d+) sha256 ([0-9a-f]{64})$", text, re.M)
    checks.append(("two volume digests, at boot and at the end", len(lines) == 2))
    checks.append(("each is the pin of tools/mkdisk.sh", len(lines) == 2 and all(h == pin and int(n) * 512 == size for n, h in lines)))
    checks.append(("the write probe read its pattern back and restored the sectors",
                   "daphnis: disk write probe: the pattern read back equal, the sectors restored"
                   in guestlines.lines(text)))
    checks.append(("the volume QEMU left has the pin's digest", left == pin))
    if session:
        shell, image, stdin = [os.path.abspath(p) for p in session]
        want_out, want_end = session_oracle(volume, shell, image, stdin)
        checks.append(session_check("the session on /home is Linux's on a debugfs dump, with debugfs's inodes in the stat lines",
                                    sh_blocks(raw), want_out, want_end))
    report(checks)


def report(checks):
    bad = 0
    for label, ok in checks:
        print(("ok    " if ok else "FAIL  ") + label)
        bad += not ok
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
