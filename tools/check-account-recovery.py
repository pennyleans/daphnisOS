#!/usr/bin/env python3
"""Check account recovery and enrollment decisions on disposable guest volumes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import guestlines
from mkcpio import member


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def overlay(source, binaries):
    raw = source.read_bytes()
    result = bytearray()
    at = 0
    wanted = {"hdesk": binaries / "hdesk", "bin/accounts": binaries / "accounts"}
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
            raise ValueError("truncated newc archive")
        if name == "TRAILER!!!":
            if found != set(wanted):
                raise ValueError("missing replacement program")
            return bytes(result) + raw[at:]
        if name in wanted:
            if name in found or fields[4] != 1 or size == 0:
                raise ValueError("expected one independent program member")
            found.add(name)
            result += member(fields[0], name, wanted[name].read_bytes(), fields[1], 1)
        else:
            result += raw[at:end]
        at = end
    raise ValueError("missing archive trailer")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("build", type=Path, help="completed hybrid build supplying kernel and initrd")
    parser.add_argument("output", type=Path, help="fresh external output directory")
    parser.add_argument("--bin-dir", type=Path, help="explicit replacement hdesk/accounts binaries")
    parser.add_argument("--case", help="one case name; default all")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    build, output = args.build.resolve(), args.output.resolve()
    if output == repo or repo in output.parents:
        parser.error("output must be outside the repository")
    output.mkdir(parents=True, exist_ok=False)
    kernel = build / "gcc-hdesk/kernel32.elf"
    source_image = build / "hdesk/initrd.cpio"
    initrd = output / "initrd.cpio"
    initrd.write_bytes(overlay(source_image, args.bin_dir.resolve()) if args.bin_dir else source_image.read_bytes())
    valid = (repo / "tests/ac/accounts.txt").read_bytes()
    child = b"daphnis-accounts 1\n" + b"\n".join(line for line in valid.splitlines() if b"role=child" in line) + b"\n"
    damaged = valid.replace(b"salt=", b"salt=z", 1)
    oversized = valid + b"\n" * (4097 - len(valid))
    cases = {
        "missing": (None, None, "first boot", False),
        "damaged-backup": (damaged, valid, "2", True),
        "parentless-backup": (child, valid, "2", True),
        "oversized-backup": (oversized, valid, "2", True),
        "parentless-pair": (child, child, "store unreadable", False),
        "empty-pair": (b"", b"", "store unreadable", False),
        "directory-primary": ("directory", None, "store unreadable", False),
        "directory-pair": ("directory", "directory", "store unreadable", False),
    }
    if args.case:
        if args.case not in cases:
            parser.error("unknown case: " + args.case)
        cases = {args.case: cases[args.case]}
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", TMPDIR=str(output),
               CPU="max", POOL="max", MEM="512", QEMU_TIMEOUT="120", INITRD=str(initrd),
               PLAY="0", KVM="0", NET="none", MODE="", RTC="", APPEND="", QEMU_EXTRA="",
               SOUND="", STDIN_FILE="/dev/null", SENDKEYS_WAIT="100")
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=repo).decode().split("\0")
    source_hashes = {name: sha(repo / name) for name in tracked if name and (repo / name).is_file()}
    source_hashes["tools/check-account-recovery.py"] = sha(Path(__file__).resolve())
    (output / "source-files.json").write_text(json.dumps(source_hashes, indent=2) + "\n")
    identity = {"head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip(),
                "status": subprocess.check_output(["git", "status", "--porcelain"], cwd=repo, text=True),
                "kernel": {"path": str(kernel), "sha256": sha(kernel)},
                "source_initrd": {"path": str(source_image), "sha256": sha(source_image)},
                "run_initrd_sha256": sha(initrd)}
    if args.bin_dir:
        identity["replacement_sha256"] = {name: sha(args.bin_dir / name) for name in ["hdesk", "accounts"]}
    (output / "identity.json").write_text(json.dumps(identity, indent=2) + "\n")
    results = []
    for name, (primary, backup, screen, login) in cases.items():
        case = output / name
        case.mkdir()
        commands = []

        def run(command, label, extra=None, input_text=None):
            commands.append(command)
            result = subprocess.run(command, cwd=repo, env=dict(env, **(extra or {})),
                                    input=input_text, capture_output=True, text=True)
            (case / (label + ".log")).write_text(result.stdout + result.stderr)
            if result.returncode:
                raise RuntimeError(f"{name}: {label} exited {result.returncode}")
            return result

        volume = case / "volume.img"
        run(["bash", "tools/mkdisk.sh", str(volume)], "volume", {"ACCOUNTS": ""})
        for filename, content in [("accounts", primary), ("accounts.prev", backup)]:
            if content is None:
                continue
            if content == "directory":
                command = "mkdir /.daphnis/" + filename
            else:
                fixture = case / filename
                fixture.write_bytes(content)
                if any(c in str(fixture) for c in ['"', "\n", "\r"]):
                    raise ValueError("unsupported fixture path")
                command = f'write "{fixture}" /.daphnis/{filename}'
            result = run(["debugfs", "-w", "-f", "-", str(volume)], filename + "-write", input_text=command + "\n")
            if any(word in result.stderr.lower() for word in ["not found", "usage:", "error", "could not"]):
                raise RuntimeError("debugfs did not install the fixture")
        initial_volume_sha = sha(volume)
        transcript, monitor = case / "serial.txt", case / "monitor.sock"
        expected = "hdesk: accounts " + screen
        keys = ["python3", "tools/sendkeys.py", str(monitor), str(transcript), "hdesk: accounts "]
        if login:
            keys += ["s,e,v,e,n,h,o,r,s,e,s,r,u,n,ret", "hdesk: bar desktop 1 |Console|", "e,x,i,t,ret",
                     "hdesk: logout ada", "meta_l-esc"]
        else:
            keys += ["meta_l-esc"]
        commands.append(keys)
        with (case / "keys.log").open("w") as log:
            sender = subprocess.Popen(keys, cwd=repo, env=env, stdout=log, stderr=subprocess.STDOUT)
            try:
                result = run(["bash", "tools/run-qemu.sh", str(kernel), str(transcript)], "qemu",
                             {"DISK": str(volume), "MONITOR": str(monitor)})
                sender_rc = sender.wait(timeout=110)
            finally:
                if sender.poll() is None:
                    sender.terminate()
                    sender.wait(timeout=10)
        lines = guestlines.lines(transcript.read_text(errors="replace"))
        account_lines = [line for line in lines if line.startswith("hdesk: accounts ")]
        passed = (result.stdout.strip() == "33" and sender_rc == 0
                  and account_lines and account_lines[0] == expected
                  and not transcript.with_suffix(".txt.err").read_bytes())
        if screen != "first boot":
            passed = passed and "hdesk: accounts first boot" not in lines
        if login:
            passed = passed and "hdesk: login ada uid 1000" in lines and "hdesk: logout ada" in lines
        receipt = {"case": name, "commands": commands, "qemu_status": result.stdout.strip(),
                   "sender_exit": sender_rc, "account_lines": account_lines,
                   "initial_volume_sha256": initial_volume_sha, "final_volume_sha256": sha(volume),
                   "pass": bool(passed)}
        (case / "result.json").write_text(json.dumps(receipt, indent=2) + "\n")
        results.append(receipt)
        (output / "results.json").write_text(json.dumps(results, indent=2) + "\n")
        print(("PASS" if passed else "FAIL") + ": " + name, flush=True)
        if not passed:
            return 1
    changed = [name for name, value in source_hashes.items() if sha(repo / name) != value]
    if changed:
        print("FAIL: source changed during run: " + ", ".join(changed))
        return 1
    print(f"RESULT: PASS ({len(results)}/{len(cases)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
