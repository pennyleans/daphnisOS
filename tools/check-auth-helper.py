#!/usr/bin/env python3
"""Check that the desktop starts its authentication helper without disk access."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import guestlines
from mkcpio import member


def helper_image(source, probe):
    raw = source.read_bytes()
    result = bytearray()
    at = highest = 0
    original = None
    while at < len(raw):
        if raw[at:at + 6] != b"070701":
            raise ValueError("invalid newc archive")
        fields = [int(raw[at + 6 + i * 8:at + 14 + i * 8], 16) for i in range(13)]
        ino, mode = fields[:2]
        highest = max(highest, ino)
        size, namesize = fields[6], fields[11]
        name = raw[at + 110:at + 110 + namesize - 1].decode()
        start = (at + 110 + namesize + 3) & ~3
        end = (start + size + 3) & ~3
        if end > len(raw):
            raise ValueError("truncated newc archive")
        if name == "TRAILER!!!":
            break
        if name == "bin/authd":
            if original is not None or fields[4] != 1 or size == 0:
                raise ValueError("expected one independent authd member")
            original = raw[start:start + size]
            result += member(ino, name, probe.read_bytes(), mode, 1)
        else:
            if name == "bin/authd-real":
                raise ValueError("authd-real already present")
            result += raw[at:end]
        at = end
    else:
        raise ValueError("missing archive trailer")
    if original is None:
        raise ValueError("missing authd")
    result += member(highest + 1, "bin/authd-real", original, 0o100755, 1)
    result += member(highest + 2, "TRAILER!!!", b"", 0, 1)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("build", type=Path, help="completed hybrid build directory")
    parser.add_argument("output", type=Path, help="new external result directory")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parent.parent
    build, output = args.build.resolve(), args.output.resolve()
    if output == repo or repo in output.parents:
        parser.error("output must be outside the repository")
    output.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", TMPDIR=str(output))
    commands = []

    def run(command, log, extra=None):
        commands.append(command)
        result = subprocess.run(command, cwd=repo, env=env if extra is None else dict(env, **extra),
                                capture_output=True, text=True)
        (output / log).write_text(result.stdout + result.stderr)
        if result.returncode:
            raise RuntimeError(f"{command[0]} exited {result.returncode}; see {output / log}")
        return result

    probe = output / "authd-probe"
    run(["musl-gcc", "-std=c17", "-O2", "-static", "-Wall", "-Wextra", "-Werror",
         "tests/ac/auth-helper-probe.c", "-o", str(probe)], "compile.log")
    initrd = output / "probe.cpio"
    initrd.write_bytes(helper_image(build / "hdesk/initrd.cpio", probe))
    volume = output / "volume.img"
    run(["bash", "tools/mkdisk.sh", str(volume)], "volume-build.log",
        {"ACCOUNTS": "tests/ac/accounts.txt"})
    kernel = build / "gcc-hdesk/kernel32.elf"
    transcript, monitor = output / "serial.txt", output / "serial.mon"
    env.update(CPU="max", POOL="max", MEM="512", QEMU_TIMEOUT="120", INITRD=str(initrd),
               MONITOR=str(monitor), DISK=str(volume))
    keys = ["python3", "tools/sendkeys.py", str(monitor), str(transcript),
            "hdesk: accounts 2", "s,e,v,e,n,h,o,r,s,e,s,r,u,n,ret",
            "hdesk: bar desktop 1 |Console|", "e,x,i,t,ret",
            "hdesk: logout ada", "meta_l-esc"]
    commands.append(keys)
    with (output / "keys.log").open("w") as log:
        sender = subprocess.Popen(keys, cwd=repo, env=dict(env, SENDKEYS_WAIT="100"),
                                  stdout=log, stderr=subprocess.STDOUT)
        result = run(["bash", "tools/run-qemu.sh", str(kernel), str(transcript)], "qemu.log")
        sender_rc = sender.wait(timeout=110)
    lines = guestlines.lines(transcript.read_text(errors="replace"))
    wanted = ["auth-probe: inherited open=-1 errno=30", "auth-probe: drop=0",
              "auth-probe: dropped open=-1 errno=30"]
    actual = [line for line in lines if line.startswith("auth-probe:")]
    passed = (result.stdout.strip() == "33" and sender_rc == 0 and actual == wanted
              and "hdesk: login ada uid 1000" in lines
              and "hdesk: logout ada" in lines
              and not transcript.with_suffix(".txt.err").read_bytes())
    hashes = {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in [kernel, initrd, probe, repo / "user/ci/host.c",
                           repo / "tests/ac/auth-helper-probe.c"]}
    receipt = {"commands": commands, "qemu_status": result.stdout.strip(),
               "sender_exit": sender_rc, "expected": wanted, "actual": actual,
               "sha256": hashes, "pass": passed}
    (output / "result.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(("PASS" if passed else "FAIL") + ": auth helper starts without disk access; login and logout complete")
    if not passed:
        print("observed:", actual)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
