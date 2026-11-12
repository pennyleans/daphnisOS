#!/usr/bin/env python3
"""PR 225 P1: a stale unlock after a log out must not open the desk, and with accounts on and no session the desk
starts no shell.

Usage: check-unlock-race.py BUILD OUT [HDESK]

One boot of the hdesk flavor on a volume with accounts, authd replaced by tests/ac/approval-delay-probe.c (as
tools/check-approval-binding.py does). sam logs in; `exec authd --run-unlock` makes the probe sam's first shell
and arms a hold on the next verify. Super+L locks; sam's passphrase starts the unlock verify, which the probe holds;
the probe then ends, so the first shell has ended, the desk logs out, and the held "ok" arrives after the log out.

  (a) unlock_stale_after_logout: the log out comes before the release, the desk prints `hdesk: auth stale ignored`
      and never `hdesk: unlock sam`;
  (b) no_session_no_shell: Super+Enter after that opens no terminal and no uid-0 process appears. On the fixed desk
      the login screen takes the key; new_term's own refusal (`hdesk: no session, no shell`) is the second wall.

HDESK (default: BUILD/ubin/hdesk, the desk the images take, built from source at HEAD) is the desk under test, so the same script takes the red receipt on
an older desk. Exit 0 only if both hold.
"""

import importlib.util
import json
import shutil
import sys
import time
from pathlib import Path

import guestlines

REPO_ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("binding", REPO_ROOT / "tools/check-approval-binding.py")
binding = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(binding)


def after(text: str, needle: str, start: int, anywhere: bool = False) -> int:
    """The first line at or after offset start that begins with needle, or -1 (AC-R1: a program's title can stand
    after other text on a line); with anywhere, needle at any place, for a probe's line, which is drained in chunks
    and can follow other text (tools/test_approval_evidence.py)."""
    if start < 0:
        return -1
    return text.find(needle, start) if anywhere else guestlines.find(text, needle, start)


def run_unlock_boot(kernel: Path, initrd: Path, seed_img: Path, run_dir: Path, meta: dict):
    run_dir.mkdir(parents=True, exist_ok=True)
    disk_img = run_dir / "disk.img"
    shutil.copyfile(seed_img, disk_img)
    q = binding.QemuHarness(kernel, initrd, disk_img, run_dir)
    try:
        if not q.wait_for("hdesk: accounts 2", timeout=30.0):
            raise RuntimeError("login screen did not appear")
        time.sleep(0.3)
        q.send_key("down", pause=0.08)
        q.send_text("sam-pass-01\n")
        if not q.wait_for("hdesk: login sam uid 1001", timeout=90.0):
            raise RuntimeError("sam login failed")
        if not q.wait_for("hdesk: terminal 0", timeout=15.0):
            raise RuntimeError("terminal 0 did not open")
        time.sleep(0.4)
        q.send_text("exec authd --run-unlock\n")
        if not q.wait_for("approval-probe: unlock_race armed", timeout=20.0):
            raise RuntimeError("the probe did not arm")
        time.sleep(0.2)
        q.send_key("meta_l-l", pause=0.1)
        if not q.wait_for("hdesk: lock sam", timeout=15.0):
            raise RuntimeError("Super+L did not lock")
        time.sleep(0.3)
        q.send_text("sam-pass-01\n")
        if not q.wait_for("approval-probe: held seq=1 verdict=ok", timeout=90.0):
            raise RuntimeError("the unlock verify was not held")
        meta["logged_out"] = q.wait_for("hdesk: logout", timeout=15.0)
        if not q.wait_for("approval-probe: release seq=1 verdict=ok", timeout=30.0):
            raise RuntimeError("the unlock verify was not released")
        deadline = time.time() + 20.0
        while time.time() < deadline:
            if q.count("hdesk: auth stale ignored") or q.count("hdesk: unlock sam"):
                break
            time.sleep(0.05)
        time.sleep(0.5)
        terms_before = q.count("hdesk: terminal ")
        q.send_key("meta_l-ret", pause=0.2)
        time.sleep(3.0)
        meta["shell_opened"] = q.count("hdesk: terminal ") > terms_before
        if meta["shell_opened"]:
            # the red desk: the new terminal has the focus; ask its shell who it runs as
            q.send_text("authd --whoami\n")
            q.wait_for("approval-probe: whoami uid=", timeout=15.0)
            time.sleep(0.3)
        if q.count("hdesk: shut down from the account screen") == 0:
            q.send_key("meta_l-esc", pause=0.2)
        if not q.wait_for("daphnis: done", timeout=10.0):
            q.send_key("meta_l-shift-q", pause=0.3)       # the desk is up with no session: FF-R6 B's chord, twice
            q.wait_for("hdesk: ff armed 3", timeout=5.0)
            q.send_key("meta_l-shift-q", pause=0.3)
            q.wait_for("daphnis: done", timeout=20.0)
    finally:
        q.close()
        meta["qemu_exit"] = q.proc.returncode
        if disk_img.exists():
            disk_img.unlink()


def main():
    if len(sys.argv) not in (3, 4):
        print(__doc__, file=sys.stderr)
        return 2
    build_dir = Path(sys.argv[1]).resolve()
    out_dir = Path(sys.argv[2]).resolve()
    hdesk_bin = Path(sys.argv[3]).resolve() if len(sys.argv) == 4 else build_dir / "ubin/hdesk"   # RG-1: O/ubin
    if out_dir == REPO_ROOT or REPO_ROOT in out_dir.parents:
        raise ValueError("output must be outside the checkout")
    out_dir.mkdir(parents=True, exist_ok=False)
    kernel = build_dir / "gcc-hdesk/kernel32.elf"
    base_cpio = build_dir / "hdesk/initrd.cpio"
    if not kernel.exists() or not base_cpio.exists():
        raise RuntimeError(f"missing kernel or initrd under {build_dir}")

    probe_bin = out_dir / "approval-delay-probe"
    binding.subprocess.run(["musl-gcc", "-O2", "-static", "-Wall", "-Wextra", "-Werror", "-o", str(probe_bin),
                            str(REPO_ROOT / "tests/ac/approval-delay-probe.c")], check=True)
    probe_cpio = out_dir / "probe.cpio"
    binding.build_probe_initrd(base_cpio, probe_cpio, hdesk_bin, probe_bin)
    seed_img = out_dir / "seed.img"
    binding.make_seed_disk(seed_img, binding.compute_verifiers(probe_bin, build_dir / "ubin"))

    meta = {}
    errors = []
    try:
        run_unlock_boot(kernel, probe_cpio, seed_img, out_dir / "unlock", meta)
    except Exception as exc:
        errors.append(str(exc))
    seed_img.unlink(missing_ok=True)
    serial = (out_dir / "unlock/serial.txt").read_text(errors="replace")

    p_lock = guestlines.find(serial, "hdesk: lock sam")
    p_logout = after(serial, "hdesk: logout", p_lock)
    p_release = after(serial, "approval-probe: release seq=1 verdict=ok", p_lock, anywhere=True)
    p_stale = after(serial, "hdesk: auth stale ignored", p_release)
    a_pass = (
        not errors
        and p_lock != -1 and p_logout != -1 and p_release != -1 and p_logout < p_release
        and p_stale != -1
        and "hdesk: unlock sam" not in serial
    )
    # the window of a check that a line must not appear starts at the first logout found anywhere, so it is never
    # shorter than a substring reader's
    p_logout_any = after(serial, "hdesk: logout", serial.find("hdesk: lock sam"), anywhere=True)
    tail = serial[p_logout_any:] if p_logout_any != -1 else ""
    b_pass = (
        not errors
        and p_logout != -1
        and not meta.get("shell_opened")
        and "hdesk: terminal " not in tail
        and "approval-probe: whoami uid=0 " not in serial
    )
    clean = meta.get("qemu_exit") == 33 and guestlines.has(serial, "daphnis: done")
    result = "PASS" if a_pass and b_pass and clean else "FAIL"
    summary = {
        "result": result,
        "hdesk": str(hdesk_bin),
        "hdesk_sha256": binding.file_sha256(hdesk_bin),
        "kernel_sha256": binding.file_sha256(kernel),
        "probe_initrd_sha256": binding.file_sha256(probe_cpio),
        "unlock_stale_after_logout": a_pass,
        "no_session_no_shell": b_pass,
        "clean_shutdown": clean,
        "meta": meta,
        "errors": errors,
        "lines": [l for l in guestlines.lines(serial)
                  if l.startswith(("hdesk: lock", "hdesk: logout", "hdesk: unlock", "hdesk: auth", "hdesk: no session",
                                   "hdesk: terminal", "approval-probe: held", "approval-probe: release",
                                   "approval-probe: unlock_race", "approval-probe: whoami", "daphnis: done"))],
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f"RESULT: {result}")
    print(f"hdesk_sha256: {summary['hdesk_sha256']}")
    print(f"unlock_stale_after_logout: {a_pass}")
    print(f"no_session_no_shell: {b_pass} (shell_opened={meta.get('shell_opened')})")
    print(f"clean_shutdown: {clean} (qemu_exit={meta.get('qemu_exit')})")
    for l in summary["lines"]:
        print(f"  {l}")
    if errors:
        print(f"errors: {errors}")
    return 0 if result == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
