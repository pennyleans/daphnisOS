#!/usr/bin/env python3
"""Verify that accounts drops disk and kern grants in its child helper before exec."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

import guestlines
from mkcpio import member

PAUSE = "info version,info version,info version,info version,info version,info version,info version,info version"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_probe_initrd(source, probe, accounts_bin=None):
    raw = source.read_bytes()
    result = bytearray()
    at = 0
    real_authd = None
    real_mode = 0o100755
    max_ino = 0
    replaced_accounts = False
    while at < len(raw):
        if raw[at:at + 6] != b"070701":
            raise ValueError("invalid newc archive")
        fields = [int(raw[at + 6 + i * 8:at + 14 + i * 8], 16) for i in range(13)]
        ino, mode, nlink, size, namesize = fields[0], fields[1], fields[4], fields[6], fields[11]
        max_ino = max(max_ino, ino)
        name_start = at + 110
        name = raw[name_start:name_start + namesize - 1].decode()
        data_start = (name_start + namesize + 3) & ~3
        end = (data_start + size + 3) & ~3
        if end > len(raw):
            raise ValueError("truncated newc archive")
        data = raw[data_start:data_start + size]
        if name == "TRAILER!!!":
            if real_authd is None:
                raise ValueError("bin/authd not found in initrd")
            if accounts_bin is not None and not replaced_accounts:
                raise ValueError("bin/accounts not found in initrd")
            result += member(max_ino + 1, "bin/authd-real", real_authd, real_mode, 1)
            # FS-2: the probe's shared files live in /probe, 0777 (no account may write the image's root)
            result += member(max_ino + 2, "probe", b"", 0o040777, 2)
            result += raw[at:end]
            return bytes(result)
        if name == "bin/authd":
            if real_authd is not None or nlink != 1:
                raise ValueError("expected one independent bin/authd member")
            real_authd = data
            real_mode = mode
            result += member(ino, name, probe.read_bytes(), mode, 1)
        elif name == "bin/accounts" and accounts_bin is not None:
            if replaced_accounts or nlink != 1:
                raise ValueError("expected one independent bin/accounts member")
            replaced_accounts = True
            result += member(ino, name, accounts_bin.read_bytes(), mode, 1)
        else:
            result += raw[at:end]
        at = end
    raise ValueError("missing newc trailer")


def parse_kv(prefix, line):
    if not line.startswith(prefix):
        return None
    out = {}
    for token in line[len(prefix):].strip().split():
        if "=" not in token:
            continue
        k, v = token.split("=", 1)
        out[k] = int(v)
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("build", type=Path, help="completed hybrid build directory")
    parser.add_argument("output", type=Path, help="fresh external output directory")
    parser.add_argument("--use-initrd-accounts", action="store_true",
                        help="use bin/accounts already in initrd instead of building user/ci/accounts.ci")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    build = args.build.resolve()
    output = args.output.resolve()
    if output == repo or repo in output.parents:
        parser.error("output must be outside the repository")
    output.mkdir(parents=True, exist_ok=False)

    kernel = build / "gcc-hdesk/kernel32.elf"
    source_initrd = build / "hdesk/initrd.cpio"
    probe_src = repo / "tests/ac/accounts-helper-probe.c"
    probe_bin = output / "accounts-helper-probe"
    probe_initrd = output / "probe.cpio"
    volume = output / "disk.img"
    transcript = output / "serial.txt"
    monitor = output / "monitor.sock"
    if len(str(monitor)) > 100:
        parser.error("monitor socket path is too long for a unix socket")

    # the gate's own toolchain (toolchain.pin): cint from CINT, else from PATH; its file from CINT_TOOLCHAIN
    cint_name = os.environ.get("CINT") or shutil.which("cint")
    if not cint_name or not Path(cint_name).is_file():
        parser.error("no cint: set CINT to the pinned compiler or put it on PATH")
    toolchain_name = os.environ.get("CINT_TOOLCHAIN")
    if not toolchain_name or not Path(toolchain_name).is_file():
        parser.error("no cint toolchain file: set CINT_TOOLCHAIN to the pinned compiler's cint.toolchain")
    cint_bin = Path(cint_name).resolve()
    toolchain = Path(toolchain_name).resolve()
    env = dict(
        os.environ,
        PYTHONDONTWRITEBYTECODE="1",
        TMPDIR=str(output),
        PATH=f"{cint_bin.parent}:{os.environ.get('PATH', '')}",
        CINT=str(cint_bin),
        CINT_TOOLCHAIN=str(toolchain),
        CPU="max",
        POOL="max",
        MEM="512",
        QEMU_TIMEOUT="300",
        INITRD=str(probe_initrd),
        DISK=str(volume),
        MONITOR=str(monitor),
        PLAY="0",
        KVM="0",
        NET="none",
        MODE="",
        RTC="",
        APPEND="",
        QEMU_EXTRA="",
        SOUND="",
        STDIN_FILE="/dev/null",
        SENDKEYS_WAIT="280",
    )

    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=repo).decode().split("\0")
    source_hashes = {name: sha(repo / name) for name in tracked if name and (repo / name).is_file()}

    def run(command, label, extra=None):
        result = subprocess.run(
            command,
            cwd=repo,
            env=dict(env, **(extra or {})),
            capture_output=True,
            text=True,
        )
        (output / f"{label}.log").write_text(result.stdout + result.stderr)
        if result.returncode != 0:
            raise RuntimeError(f"{label} exited {result.returncode}")
        return result

    run(["musl-gcc", "-O2", "-static", "-Wall", "-Wextra", "-Werror", str(probe_src), "-o", str(probe_bin)], "compile")

    accounts_bin = None
    if not args.use_initrd_accounts:
        bin_dir = output / "bin"
        tmp_dir = output / "tmp"
        bin_dir.mkdir()
        tmp_dir.mkdir()
        run(["bash", "user/ci/build.sh", "accounts"], "build-accounts",
            {"CI_OUT": str(bin_dir), "TMPDIR": str(tmp_dir)})
        accounts_bin = bin_dir / "accounts"

    probe_initrd.write_bytes(build_probe_initrd(source_initrd, probe_bin, accounts_bin))
    run(["bash", "tools/mkdisk.sh", str(volume)], "mkdisk", {"ACCOUNTS": "tests/ac/accounts.txt"})

    har = "s,e,v,e,n,h,o,r,s,e,s,r,u,n"
    ivy_old = "i,v,y,minus,p,a,s,s"
    ivy_new = "i,v,y,minus,n,e,x,t"
    fail_cmd = "k,e,r,n,spc,a,u,t,h,d,spc,minus,minus,c,h,e,c,k,minus,f,a,i,l,minus,s,t,a,r,t,ret"
    add_cmd = "k,e,r,n,spc,a,c,c,o,u,n,t,s,spc,a,d,d,spc,i,v,y,spc,c,h,i,l,d,spc,n,e,t,ret"
    passwd_cmd = "k,e,r,n,spc,a,c,c,o,u,n,t,s,spc,p,a,s,s,w,d,spc,i,v,y,ret"

    keys_cmd = [
        "python3",
        "tools/sendkeys.py",
        str(monitor),
        str(transcript),
        "hdesk: accounts 2",
        f"{har},ret",
        "hdesk: bar desktop 1 |Console| var |/home/ada|",
        fail_cmd,
        "hdesk: approval ask want 8 uid 1000",
        f"{har},ret",
        "hdesk: bar desktop 1 |Console| var |/home/ada| grants |KERN 1",
        add_cmd,
        "hdesk: bar desktop 1 |bin/accounts|",
        f"{PAUSE},{ivy_old},ret,{PAUSE},{ivy_old},ret",
        "hdesk: bar desktop 1 |Console| var |/home/ada| grants |KERN 1@@2",
        passwd_cmd,
        "hdesk: bar desktop 1 |bin/accounts|@@2",
        f"{PAUSE},{ivy_new},ret,{PAUSE},{ivy_new},ret",
        "hdesk: bar desktop 1 |Console| var |/home/ada| grants |KERN 1@@3",
        "e,x,i,t,ret",
        "hdesk: accounts 3",
        f"down,down,{ivy_old},ret",
        "hdesk: auth refused ivy",
        f"{ivy_new},ret",
        "hdesk: login ivy uid 1002",
        f"{PAUSE},e,x,i,t,ret",
        "hdesk: logout ivy",
        "meta_l-esc",
    ]
    with (output / "keys.log").open("w") as keys_log:
        sender = subprocess.Popen(keys_cmd, cwd=repo, env=env, stdout=keys_log, stderr=subprocess.STDOUT)
        try:
            qemu = run(["bash", "tools/run-qemu.sh", str(kernel), str(transcript)], "qemu")
            sender_rc = sender.wait(timeout=290)
        finally:
            if sender.poll() is None:
                sender.terminate()
                sender.wait(timeout=10)

    check = subprocess.run(
        [
            "python3",
            "tools/check-accounts.py",
            str(transcript),
            "hdesk: accounts 2",
            "hdesk: login ada uid 1000",
            "hdesk: approval ask want 8 uid 1000",
            "hdesk: approved by ada",
            "hdesk: kern 0 pid",
            "hdesk: logout ada",
            "hdesk: accounts 3",
            "hdesk: auth refused ivy",
            "hdesk: login ivy uid 1002",
            "hdesk: logout ivy",
            "hdesk: shut down from the account screen",
            "!sevenhorsesrun",
            "!ivy-pass",
            "!ivy-next",
        ],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
    )
    (output / "accounts-check.log").write_text(check.stdout + check.stderr)

    text = transcript.read_text(errors="replace")
    probe_lines = [line for line in guestlines.lines(text) if line.startswith("accounts-probe: ")]
    fail_starts = [
        parse_kv("accounts-probe: fail_start ", line)
        for line in probe_lines
        if line.startswith("accounts-probe: fail_start ")
    ]
    calls = [
        parse_kv("accounts-probe: ", line)
        for line in probe_lines
        if re.match(r"^accounts-probe: call=\d+ ", line)
    ]

    fail_start_ok = (
        len(fail_starts) == 1
        and fail_starts[0] == {
            "pin_rc": 1,
            "pout_rc": 1,
            "child_rc": 1,
            "pipe_leak": 0,
            "store_unchanged": 1,
        }
    )
    calls_ok = (
        len(calls) == 2
        and [c.get("call") for c in calls] == [1, 2]
        and all(
            c.get("uid") == 1000
            and c.get("disk_open") == -1
            and c.get("disk_errno") == 30
            and c.get("kern_open") == -1
            and c.get("kern_errno") == 13
            and c.get("kern_held") == 0
            for c in calls
        )
    )
    changed = [name for name, digest in source_hashes.items() if sha(repo / name) != digest]
    passed = (
        qemu.stdout.strip() == "33"
        and sender_rc == 0
        and check.returncode == 0
        and fail_start_ok
        and calls_ok
        and not (output / "serial.txt.err").read_bytes()
        and not changed
    )
    receipt = {
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip(),
        "status": subprocess.check_output(["git", "status", "--porcelain"], cwd=repo, text=True),
        "cint_sha256": sha(cint_bin),
        "toolchain_sha256": sha(toolchain),
        "accounts_ci_sha256": sha(repo / "user/ci/accounts.ci"),
        "accounts_bin_sha256": sha(accounts_bin) if accounts_bin is not None else None,
        "kernel_sha256": sha(kernel),
        "source_initrd_sha256": sha(source_initrd),
        "probe_initrd_sha256": sha(probe_initrd),
        "qemu_status": qemu.stdout.strip(),
        "sender_exit": sender_rc,
        "accounts_check_exit": check.returncode,
        "probe_lines": probe_lines,
        "fail_start": fail_starts,
        "calls": calls,
        "changed_tracked_files": changed,
        "pass": passed,
    }
    (output / "result.json").write_text(json.dumps(receipt, indent=2) + "\n")
    if not passed:
        print("FAIL: accounts helper grant probe failed", file=sys.stderr)
        print("RESULT: FAIL")
        return 1
    print("PASS: accounts helper dropped disk and kern grants across add and passwd; failure starts clean")
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
