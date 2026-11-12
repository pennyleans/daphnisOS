#!/usr/bin/env python3
"""tools/check-fs-intake.py BUILD OUT [--targets 1,2,...]: the filesystem intake's regression targets 1 to 8
(docs/superpowers/specs/2026-11-09-filesystem-security-intake.md; FSP-1 A, FSP-2 A) on disposable guests.

BUILD is a completed hybrid build (check-hybrid.sh's: hdesk/initrd.cpio, gcc-hdesk/kernel32.elf); OUT a new
directory outside the repository, where every image, transcript and the receipt (result.json) stay. Nothing here
changes the kernel, the desk or the images the gates use: tests/fs/fs-intake-probe.c is built with musl-gcc and added
to a copy of the initrd as /bin/fsprobe, and each boot gets its own volume from tools/mkdisk.sh (ACCOUNTS=
tests/ac/accounts.txt), seeded on the host with debugfs where a target needs it. No fault injection, no bypass.

Boots:
  main: ada logs in and seeds ada's home (`grant disk fsprobe seed`); sam logs in and runs targets 1 to 6 and 8
    (`grant disk fsprobe sam`); ada logs in again, tries sam's home (`fsprobe cross`), chowns under `kern`
    with ada's passphrase (`fsprobe admin`, the permitted administration path) and sets sam a new passphrase (`kern
    accounts passwd sam`); sam logs in with it; shut down. The account flows of target 8 that this boot does not
    run (first boot, lock and unlock, `accounts add`) are check-hybrid.sh's accounts legs; backup recovery has no
    scripted path yet.
  home-missing, home-existing: sam's home absent, or present as sam's own 0700 directory with a file in it; sam logs
    in and `fsprobe home` checks it (target 7).
  home-wrong-owner, home-symlink, home-file: sam's home owned by ada, a symlink to ada's home, or a
    regular file; the desk must not start a session (no shell, no `hdesk: login sam`), it says so in a line that
    starts `hdesk: home refused sam` (the test's contract with FS-3), and the object stays as seeded (target 7).

The probe writes its lines to /home/<account>/fsprobe-MODE.txt; the host reads them with debugfs after the guest
has shut down, and checks ada's seeds and sam's held-descriptor file itself (uid 0 in the guest has no bypass,
so the host is the reader of record). Each denial in the probe checks the error and the unchanged bytes and metadata.

Prints one PASS or FAIL line a target and exits 1 on any FAIL. Red is expected until FS-1 to FS-3 land: the receipt
keeps the red run's source, compiler and image hashes beside the green one's.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mkcpio import member  # noqa: E402
import guestlines  # noqa: E402

HAR = "sevenhorsesrun"
SAM = "sam-pass"
SAM2 = "sam-pass-two"          # target 8: the passphrase ada sets for sam with `kern accounts passwd sam`
KEYS = {" ": "spc", "-": "minus", "/": "slash", ".": "dot", "\n": "ret", "_": "shift-minus", ",": "comma"}
PAUSE = ",".join(["info version"] * 8)


def keys(text):
    """QEMU key names for text (lower case, digits and the few marks the commands use)."""
    return ",".join(KEYS.get(c, c) for c in text)


def with_probe(source, probe):
    """A copy of the newc archive source with bin/fsprobe (the probe, mode 0755) before its trailer."""
    raw = source.read_bytes()
    result = bytearray()
    at = highest = 0
    while at < len(raw):
        if raw[at:at + 6] != b"070701":
            raise ValueError("invalid newc archive")
        fields = [int(raw[at + 6 + i * 8:at + 14 + i * 8], 16) for i in range(13)]
        highest = max(highest, fields[0])
        size, namesize = fields[6], fields[11]
        name = raw[at + 110:at + 110 + namesize - 1].decode()
        start = (at + 110 + namesize + 3) & ~3
        end = (start + size + 3) & ~3
        if name == "TRAILER!!!":
            break
        if name == "bin/fsprobe":
            raise ValueError("fsprobe already present")
        result += raw[at:end]
        at = end
    else:
        raise ValueError("missing archive trailer")
    result += member(highest + 1, "bin/fsprobe", probe.read_bytes(), 0o100755, 1)
    result += member(highest + 2, "TRAILER!!!", b"", 0, 1)
    return bytes(result)


class Run:
    def __init__(self, repo, out):
        self.repo, self.out, self.commands = repo, out, []
        self.env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", TMPDIR=str(out))

    def sh(self, command, log, extra=None, check=True):
        self.commands.append(command)
        r = subprocess.run(command, cwd=self.repo, env=self.env if extra is None else dict(self.env, **extra),
                           capture_output=True, text=True)
        (self.out / log).write_text(r.stdout + r.stderr)
        if check and r.returncode:
            raise RuntimeError("%s exited %d; see %s" % (command[0], r.returncode, self.out / log))
        return r

    def debugfs(self, img, request, write=False):
        cmd = ["debugfs"] + (["-w"] if write else []) + ["-R", request, str(img)]
        self.commands.append(cmd)
        r = subprocess.run(cmd, capture_output=True)
        return r.stdout

    def debugfs_script(self, img, lines, log):
        script = self.out / (log + ".cmds")
        script.write_text("\n".join(lines) + "\n")
        cmd = ["debugfs", "-w", "-f", str(script), str(img)]
        self.commands.append(cmd)
        r = subprocess.run(cmd, capture_output=True, text=True)
        (self.out / log).write_text(r.stdout + r.stderr)


def inode(run, img, path):
    """(permission bits, uid, gid, size, type) of path on the volume, or None; debugfs prints the bits alone in
    Mode and the type in Type (regular, directory, symlink)."""
    text = run.debugfs(img, "stat " + path).decode(errors="replace")
    m = re.search(r"Type: (\w+)\s+Mode:\s+(\d+)", text)
    u = re.search(r"User:\s+(\d+)\s+Group:\s+(\d+)", text)
    s = re.search(r"Size: (\d+)", text)
    if not (m and u and s):
        return None
    return (int(m.group(2), 8), int(u.group(1)), int(u.group(2)), int(s.group(1)), m.group(1))


def boot(run, name, kernel, initrd, img, script, timeout=900):
    """Boots kernel with initrd and the volume img, typing script (MARK, KEYS pairs); (QEMU status, sendkeys
    status, transcript lines)."""
    transcript, monitor = run.out / (name + ".txt"), run.out / (name + ".mon")
    env = dict(CPU="max", POOL="max", MEM="512", QEMU_TIMEOUT=str(timeout), INITRD=str(initrd),
               MONITOR=str(monitor), DISK=str(img))
    sk = ["python3", "tools/sendkeys.py", str(monitor), str(transcript)] + [x for pair in script for x in pair]
    run.commands.append(sk)
    with (run.out / (name + ".keys")).open("w") as log:
        sender = subprocess.Popen(sk, cwd=run.repo, env=dict(run.env, SENDKEYS_WAIT=str(timeout)),
                                  stdout=log, stderr=subprocess.STDOUT)
        r = run.sh(["bash", "tools/run-qemu.sh", str(kernel), str(transcript)], name + ".qemu.log", env,
                   check=False)
        try:
            src = sender.wait(timeout=30)
        except subprocess.TimeoutExpired:
            sender.kill()
            src = -1
    return r.stdout.strip(), src, guestlines.lines(transcript.read_text(errors="replace"))


def volume(run, name, seed=()):
    img = run.out / (name + ".img")
    run.sh(["bash", "tools/mkdisk.sh", str(img)], name + ".mkdisk.log", {"ACCOUNTS": "tests/ac/accounts.txt"})
    if seed:
        run.debugfs_script(img, list(seed), name + ".seed.log")
    return img


def probe_lines(run, img, path):
    return guestlines.lines(run.debugfs(img, "cat " + path).decode(errors="replace"))


def judge(lines, t):
    """The probe's verdict lines for target t, and whether all are ok (and there is at least one)."""
    mine = [ln for ln in lines if ln.startswith("T%d " % t) and " info " not in ln]
    return mine, bool(mine) and all(ln.split()[2] == "ok" for ln in mine)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("build", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--targets", default="1,2,3,4,5,6,7,8")
    args = ap.parse_args()
    repo = Path(__file__).resolve().parent.parent
    build, out = args.build.resolve(), args.output.resolve()
    if out == repo or repo in out.parents:
        ap.error("output must be outside the repository")
    out.mkdir(parents=True, exist_ok=False)
    targets = sorted({int(t) for t in args.targets.split(",")})
    run = Run(repo, out)
    run.kernel = build / "gcc-hdesk/kernel32.elf"
    probe = out / "fsprobe"
    run.sh(["musl-gcc", "-std=c17", "-O2", "-static", "-Wall", "-Wextra", "-Werror", "tests/fs/fs-intake-probe.c",
            "-o", str(probe)], "compile.log")
    initrd = out / "fsprobe.cpio"
    initrd.write_bytes(with_probe(build / "hdesk/initrd.cpio", probe))
    result = {"targets": {}, "boots": {}, "probe": {}, "host": {}}
    # The bar prints its line again on every redraw of a session, so steps wait for and count `hdesk: login` lines
    # (one a session), each step after its PAUSE (Arch, board 20261110T161852Z, point 1).
    login = "hdesk: login "
    har = "hdesk: login ada uid 1000"
    sam_in = "hdesk: login sam uid 1001"

    if any(t != 7 for t in targets):
        img = volume(run, "main")
        script = [("hdesk: accounts 2", keys(HAR) + ",ret"),
                  (har, PAUSE + "," + keys("grant disk fsprobe seed\nexit\n")),
                  ("hdesk: logout ada", PAUSE + ",down," + keys(SAM) + ",ret"),
                  (sam_in, PAUSE + "," + keys("grant disk fsprobe sam\nexit\n")),
                  ("hdesk: logout sam", PAUSE + "," + keys(HAR) + ",ret"),
                  (har + "@@2", PAUSE + "," + keys("grant disk fsprobe cross\ngrant disk kern fsprobe admin\n")),
                  ("hdesk: approval ask want 8 uid 1000", keys(HAR) + ",ret"),
                  # the window's kern hold (R0-R4 B) runs the second kern with no prompt, as the parent leg's
                  ("hdesk: kern 0 pid", PAUSE + "," + PAUSE + "," + keys("kern accounts passwd sam\n") + "," + PAUSE +
                   "," + keys(SAM2 + "\n") + "," + PAUSE + "," + keys(SAM2 + "\n") + "," + PAUSE + "," + PAUSE + "," +
                   PAUSE + "," + PAUSE + "," + keys("exit\n")),
                  ("hdesk: logout ada@@2", PAUSE + ",down," + keys(SAM2) + ",ret"),
                  (sam_in + "@@2", PAUSE + "," + keys("exit\n")),
                  ("hdesk: logout sam@@2", PAUSE + ",meta_l-esc")]
        qs, ks, tl = boot(run, "main", run.kernel, initrd, img, script)
        result["boots"]["main"] = {"qemu": qs, "sendkeys": ks,
                                   "sessions": sum(ln.startswith(login) for ln in tl)}
        for mode, acct in (("seed", "ada"), ("sam", "sam"), ("cross", "ada"), ("admin", "ada")):
            result["probe"][mode] = probe_lines(run, img, "/%s/fsprobe-%s.txt" % (acct, mode))
        secret = run.debugfs(img, "cat /ada/secret")
        held = run.debugfs(img, "cat /sam/t2.dat")
        result["host"] = {
            "ada-secret": secret == b"ada's secret, not sam's\n",
            "ada-secret-inode": inode(run, img, "/ada/secret"),
            "ada-home-inode": inode(run, img, "/ada"),
            "sam-home-inode": inode(run, img, "/sam"),
            "sam-held-bytes": held == b"held descriptor bytes\n",
            "adm-inode": inode(run, img, "/ada/adm"),
            "no-secret-in-transcript": not any(HAR in ln or SAM in ln or SAM2 in ln for ln in tl),
            "sam-new-passphrase-login": sum(ln.startswith(sam_in) for ln in tl) == 2,
        }
        booted = qs == "33" and ks == 0
        sam, seed, cross, admin = (result["probe"][m] for m in ("sam", "seed", "cross", "admin"))
        h = result["host"]
        sec_ino = h["ada-secret-inode"]
        for t in (1, 2, 3, 6, 8):
            if t in targets:
                lines, ok = judge(sam, t)
                extra = h["sam-held-bytes"] if t == 2 else True
                result["targets"][t] = (booted and ok and extra and any(ln.startswith("end ") for ln in sam), lines)
        if 4 in targets:
            l4 = judge(seed, 4)[0] + judge(sam, 4)[0] + judge(cross, 4)[0]
            ok = (booted and l4 and all(ln.split()[2] == "ok" for ln in l4) and h["ada-secret"] and
                  sec_ino is not None and sec_ino[:3] == (0o600, 1000, 1000) and sec_ino[4] == "regular")
            result["targets"][4] = (bool(ok), l4)
        if 5 in targets:
            l5 = judge(seed, 5)[0] + judge(sam, 5)[0] + judge(cross, 5)[0] + judge(admin, 5)[0]
            adm = h["adm-inode"]
            ok = booted and l5 and all(ln.split()[2] == "ok" for ln in l5) and adm is not None and adm[1:3] == (1001, 1001)
            result["targets"][5] = (bool(ok), l5)
        if 8 in targets:
            ok8, l8 = result["targets"][8]
            ok8 = (ok8 and h["no-secret-in-transcript"] and h["sam-new-passphrase-login"] and
                   result["boots"]["main"]["sessions"] == 4)
            result["targets"][8] = (ok8, l8)

    if 7 in targets:
        homes = {
            "home-missing": ([], True),
            "home-existing": (["mkdir sam", "sif sam uid 1001", "sif sam gid 1001", "sif sam mode 040700",
                               "write %s sam/kept" % (out / "kept.src"), "sif sam/kept uid 1001",
                               "sif sam/kept gid 1001", "sif sam/kept mode 0100600"], True),
            "home-wrong-owner": (["mkdir sam", "sif sam uid 1000", "sif sam gid 1000", "sif sam mode 040700"], False),
            "home-symlink": (["mkdir ada", "sif ada uid 1000", "sif ada gid 1000",
                              "sif ada mode 040700", "symlink sam /home/ada"], False),
            "home-file": (["write %s sam" % (out / "kept.src"), "sif sam uid 1001", "sif sam gid 1001"], False),
        }
        (out / "kept.src").write_bytes(b"kept bytes\n")
        l7, ok7 = [], True
        for name, (seed, session) in homes.items():
            img = volume(run, name, seed)
            before = inode(run, img, "/sam")
            if session:
                script = [("hdesk: accounts 2", "down," + keys(SAM) + ",ret"),
                          (sam_in, PAUSE + "," + keys("grant disk fsprobe home\nexit\n")),
                          ("hdesk: logout sam", PAUSE + ",meta_l-esc")]
            else:   # the refusal line is the test's contract with FS-3: `hdesk: home refused sam ...`
                script = [("hdesk: accounts 2", "down," + keys(SAM) + ",ret"),
                          ("hdesk: home refused sam", PAUSE + ",meta_l-esc")]
            qs, ks, tl = boot(run, name, run.kernel, initrd, img, script, timeout=180)
            after = inode(run, img, "/sam")
            sessions = sum(ln.startswith(login) for ln in tl)
            if session:
                lines = probe_lines(run, img, "/sam/fsprobe-home.txt")
                mine, ok = judge(lines, 7)
                if name == "home-existing":
                    ok = ok and run.debugfs(img, "cat /sam/kept") == b"kept bytes\n"
                ok = ok and qs == "33" and sessions == 1
            else:
                mine = [ln for ln in tl if ln.startswith("hdesk: home refused sam")]
                ok = (qs == "33" and sessions == 0 and before == after and bool(mine) and
                      not any(ln.startswith("hdesk: login sam") for ln in tl))
                if name == "home-symlink":
                    hi = inode(run, img, "/ada")
                    ok = ok and hi is not None and hi[:3] == (0o700, 1000, 1000) and hi[4] == "directory"
            result["boots"][name] = {"qemu": qs, "sendkeys": ks, "sessions": sessions, "sam-before": before,
                                     "sam-after": after, "probe": mine}
            l7.append("%s %s qemu=%s sessions=%d sam %s -> %s" % (name, "ok" if ok else "bad", qs, sessions,
                                                                   before, after))
            ok7 = ok7 and ok
        result["targets"][7] = (ok7, l7)

    files = [run.kernel, build / "hdesk/initrd.cpio", initrd, probe, repo / "tests/fs/fs-intake-probe.c",
             repo / "src/fs.ci", repo / "src/proc.ci", repo / "user/ci/hdesk.ci"]
    files += sorted(out.glob("*.img"))
    result["sha256"] = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files if p.exists()}
    rev = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True).stdout.strip()
    result["source"] = rev
    result["when"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    result["commands"] = run.commands
    result["targets"] = {str(t): {"pass": ok, "lines": lines} for t, (ok, lines) in sorted(result["targets"].items())}
    (out / "result.json").write_text(json.dumps(result, indent=2, default=str) + "\n")
    names = {1: "/bin/authd from an ordinary account", 2: "write paths and held descriptors (FSP-2 A)",
             3: "exec, modes, umask, access masks, traversal", 4: "two accounts, 0700 homes",
             5: "chmod and chown authority; setuid refused", 6: "symlinks, links, openat, dirfds, unlinked objects",
             7: "missing, wrong, linked and existing homes", 8: "launch identity; the account flows"}
    bad = 0
    for t in targets:
        r = result["targets"][str(t)]
        bad += not r["pass"]
        n_ok = sum(" ok" in ln for ln in r["lines"])
        print("%s  fs intake target %d: %s (%d of %d lines ok at %s; %s)" % ("PASS" if r["pass"] else "FAIL", t,
              names[t], n_ok, len(r["lines"]), rev[:12], out / "result.json"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
