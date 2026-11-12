#!/usr/bin/env python3
"""Check inherited raw-input reads and the desktop session descriptor boundary."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import guestlines
from mkcpio import member


def overlay(source, replacements):
    raw = source.read_bytes()
    result = bytearray()
    at = 0
    found = set()
    while at < len(raw):
        if raw[at:at + 6] != b"070701":
            raise ValueError("invalid newc archive")
        fields = [int(raw[at + 6 + i * 8:at + 14 + i * 8], 16) for i in range(13)]
        size, namesize = fields[6], fields[11]
        name = raw[at + 110:at + 110 + namesize - 1].decode()
        start = (at + 110 + namesize + 3) & ~3
        end = (start + size + 3) & ~3
        if end > len(raw):
            raise ValueError("truncated archive")
        if name == "TRAILER!!!":
            for key, path in replacements.items():
                if key not in found:
                    result += member(50000 + len(found), key, path.read_bytes(), 0o100755, 1)
                    found.add(key)
            return bytes(result) + raw[at:]
        if name in replacements:
            if name in found or fields[4] != 1:
                raise ValueError("ambiguous replacement")
            found.add(name)
            result += member(fields[0], name, replacements[name].read_bytes(), fields[1], 1)
        else:
            result += raw[at:end]
        at = end
    raise ValueError("missing trailer")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("build", type=Path)
    ap.add_argument("output", type=Path)
    args = ap.parse_args()
    repo = Path(__file__).resolve().parents[1]
    build, out = args.build.resolve(), args.output.resolve()
    if out == repo or repo in out.parents:
        ap.error("output must be outside checkout")
    out.mkdir(parents=True, exist_ok=False)
    initial_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    initial_status = subprocess.check_output(["git", "status", "--porcelain"], cwd=repo, text=True)
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=repo).split(bytes([0]))
    source_hashes = {os.fsdecode(n): sha(repo / os.fsdecode(n)) for n in tracked if n and (repo / os.fsdecode(n)).is_file()}
    (out / "source-files.json").write_text(json.dumps(source_hashes, sort_keys=True, indent=2))
    env = dict(os.environ, CPU="max", POOL="max", MEM="512", QEMU_TIMEOUT="90",
               NET="none", PLAY="0", KVM="0", MODE="", RTC="", APPEND="", QEMU_EXTRA="",
               PYTHONDONTWRITEBYTECODE="1")
    def run(command, label, extra=None):
        r = subprocess.run(command, cwd=repo, env=dict(env, **(extra or {})), capture_output=True, text=True)
        (out / (label + ".log")).write_text(r.stdout + r.stderr)
        if r.returncode:
            raise RuntimeError(f"{label}: exit {r.returncode}")
        return r
    probe = out / "raw-probe"
    run(["musl-gcc", "-O2", "-static", "-Wall", "-Wextra", "-Werror", "tests/ac/raw-input-probe.c", "-o", str(probe)], "compile")
    kernel = build / "gcc-hdesk/kernel32.elf"
    base = build / "hdesk/initrd.cpio"
    pipe_probe = out / "pipe-probe"
    run(["musl-gcc", "-O2", "-static", "-Wall", "-Wextra", "-Werror", "tests/ac/nonblock-pipe-probe.c", "-o", str(pipe_probe)], "pipe-compile")
    pipe_image = out / "pipe.cpio"
    pipe_image.write_bytes(overlay(base, {"hdesk": pipe_probe}))
    pipe_serial = out / "pipe.serial"
    pipe_run = run(["bash", "tools/run-qemu.sh", str(kernel), str(pipe_serial)], "pipe-qemu", {"INITRD": str(pipe_image)})
    pipe_pass = pipe_run.stdout.strip() == "33" and "pipe-probe: empty=-11 data=1 byte=120 eof=0 child=0" in pipe_serial.read_text()
    signal_probe = out / "signal-probe"
    run(["musl-gcc", "-O2", "-static", "-Wall", "-Wextra", "-Werror", "tests/ac/signal-account-probe.c", "-o", str(signal_probe)], "signal-compile")
    signal_image = out / "signal.cpio"
    signal_image.write_bytes(overlay(base, {"hdesk": signal_probe}))
    signal_serial = out / "signal.serial"
    signal_run = run(["bash", "tools/run-qemu.sh", str(kernel), str(signal_serial)], "signal-qemu", {"INITRD": str(signal_image)})
    signal_pass = signal_run.stdout.strip() == "33" and "signal-probe: root0=-1 root_term=-1 other0=-1 other_term=-1 self=0 peer=0 missing=-3" in signal_serial.read_text() and "signal-probe: elevated_root=0 elevated_other=0" in signal_serial.read_text() and "signal-probe: child=0 root_can_signal=0" in signal_serial.read_text()
    fairness_probe = out / "fairness-probe"
    run(["musl-gcc", "-O2", "-static", "-Wall", "-Wextra", "-Werror", "tests/ac/desk-fairness-probe.c", "-o", str(fairness_probe)], "fairness-compile")
    fairness_image = out / "fairness.cpio"
    fairness_image.write_bytes(overlay(base, {"hdesk": fairness_probe}))
    fairness_serial = out / "fairness.serial"
    fairness_run = run(["bash", "tools/run-qemu.sh", str(kernel), str(fairness_serial)], "fairness-qemu", {"INITRD": str(fairness_image)})
    fairness_pass = fairness_run.stdout.strip() == "33" and "fairness-probe: background=1 byte=120 writer=0" in fairness_serial.read_text()
    fault_probe = out / "fault-probe"
    run(["musl-gcc", "-O2", "-static", "-Wall", "-Wextra", "-Werror", "-DFAIR_TOUCH_PAGES", "tests/ac/desk-fairness-probe.c", "-o", str(fault_probe)], "fault-compile")
    fault_image = out / "fault.cpio"
    fault_image.write_bytes(overlay(base, {"hdesk": fault_probe}))
    fault_serial = out / "fault.serial"
    fault_run = run(["bash", "tools/run-qemu.sh", str(kernel), str(fault_serial)], "fault-qemu", {"INITRD": str(fault_image)})
    fault_pass = fault_run.stdout.strip() == "33" and "fairness-probe: background=1 byte=120 writer=0" in fault_serial.read_text()
    raw_image = out / "raw.cpio"
    raw_image.write_bytes(overlay(base, {"hdesk": probe}))
    raw_serial = out / "raw.serial"
    r = run(["bash", "tools/run-qemu.sh", str(kernel), str(raw_serial)], "raw-qemu", {"INITRD": str(raw_image)})
    raw_text = raw_serial.read_text()
    raw_pass = (r.stdout.strip() == "33"
                and guestlines.has(raw_text, "raw-probe: fork=-13 login=0 inherited=-13 fresh=-11")
                and guestlines.has(raw_text, "raw-probe: child_status=0"))
    disk = out / "volume.img"
    run(["bash", "tools/mkdisk.sh", str(disk)], "mkdisk", {"ACCOUNTS": "tests/ac/accounts.txt"})
    session_image = out / "session.cpio"
    session_image.write_bytes(overlay(base, {"bin/accounts": probe}))
    serial, monitor = out / "session.serial", out / "session.mon"
    keys = ["python3", "tools/sendkeys.py", str(monitor), str(serial),
            "hdesk: accounts 2", "s,e,v,e,n,h,o,r,s,e,s,r,u,n,ret",
            "hdesk: bar desktop 1 |Console|", "a,c,c,o,u,n,t,s,spc,s,e,s,s,i,o,n,ret,e,x,i,t,ret",
            "hdesk: logout ada", "meta_l-esc"]
    with (out / "keys.log").open("w") as log:
        sender = subprocess.Popen(keys, cwd=repo, env=dict(env, SENDKEYS_WAIT="100"), stdout=log, stderr=subprocess.STDOUT)
        r = run(["bash", "tools/run-qemu.sh", str(kernel), str(serial)], "session-qemu",
                {"INITRD": str(session_image), "DISK": str(disk), "MONITOR": str(monitor)})
        sender_rc = sender.wait(timeout=110)
    report = run(["debugfs", "-R", "cat /ada/raw-session-result", str(disk)], "session-report").stdout
    session_pass = (r.stdout.strip() == "33" and sender_rc == 0
                    and guestlines.lines(report) == ["raw-probe: inherited=0", "raw-probe: fresh=-11"]
                    and guestlines.has(serial.read_text(), "hdesk: logout ada"))
    final_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    final_status = subprocess.check_output(["git", "status", "--porcelain"], cwd=repo, text=True)
    source_matches = initial_head == final_head and initial_status == final_status == "" and all(sha(repo / n) == h for n, h in source_hashes.items())
    result = {"source_matches": source_matches, "result": "PASS" if raw_pass and session_pass and pipe_pass and signal_pass and fairness_pass and fault_pass and source_matches else "FAIL", "raw_read_denied": raw_pass, "nonblock_pipe": pipe_pass, "signal_accounts": signal_pass, "background_progress": fairness_pass, "lazy_page_progress": fault_pass,
              "session_descriptors": session_pass, "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip(),
              "hashes": {str(p): sha(p) for p in [kernel, base, probe, raw_image, session_image, pipe_probe, pipe_image, signal_probe, signal_image, fairness_probe, fairness_image, fault_probe, fault_image]}, "session_report": report}
    (out / "result.json").write_text(json.dumps(result, indent=2) + chr(10))
    print(json.dumps(result, indent=2))
    return 0 if result["result"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
