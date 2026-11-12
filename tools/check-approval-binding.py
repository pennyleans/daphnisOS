#!/usr/bin/env python3
"""Qualify approval-prompt request binding and stale-completion invalidation in hdesk."""

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import guestlines  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
# The compiler directory (cint and cint.toolchain) for a rebuild of hdesk: APPROVAL_CINT_DIR, else the directory of
# the cint on PATH. The gate runs with APPROVAL_USE_BUNDLED=1 and builds no hdesk.
PINNED_CINT_DIR = Path(os.environ.get("APPROVAL_CINT_DIR") or os.path.dirname(shutil.which("cint") or "") or ".")

CHAR_KEY = {
    "a": ("a", False), "b": ("b", False), "c": ("c", False), "d": ("d", False),
    "e": ("e", False), "f": ("f", False), "g": ("g", False), "h": ("h", False),
    "i": ("i", False), "j": ("j", False), "k": ("k", False), "l": ("l", False),
    "m": ("m", False), "n": ("n", False), "o": ("o", False), "p": ("p", False),
    "q": ("q", False), "r": ("r", False), "s": ("s", False), "t": ("t", False),
    "u": ("u", False), "v": ("v", False), "w": ("w", False), "x": ("x", False),
    "y": ("y", False), "z": ("z", False),
    "0": ("0", False), "1": ("1", False), "2": ("2", False), "3": ("3", False),
    "4": ("4", False), "5": ("5", False), "6": ("6", False), "7": ("7", False),
    "8": ("8", False), "9": ("9", False),
    "-": ("minus", False), "_": ("minus", True),
    " ": ("spc", False), "\n": ("ret", False),
}


def file_sha256(path: Path):
    """The file's SHA-256, or None when the compiler directory holds no such file."""
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def parse_newc(blob: bytes):
    off = 0
    entries = []
    while off + 110 <= len(blob):
        if blob[off : off + 6] != b"070701":
            raise ValueError(f"invalid cpio magic at {off}")
        fields = [int(blob[off + 6 + 8 * i : off + 14 + 8 * i], 16) for i in range(13)]
        namesize = fields[11]
        filesize = fields[6]
        name_start = off + 110
        name_end = name_start + namesize
        name = blob[name_start : name_end - 1].decode("utf-8", errors="replace")
        data_start = (name_end + 3) & ~3
        data_end = data_start + filesize
        data = blob[data_start:data_end]
        off = (data_end + 3) & ~3
        if name == "TRAILER!!!":
            break
        entries.append((name, fields, data))
    return entries


def pack_newc_entry(name: str, fields, data: bytes) -> bytes:
    name_bytes = name.encode("utf-8") + b"\x00"
    f = list(fields)
    f[6] = len(data)
    f[11] = len(name_bytes)
    hdr = b"070701" + "".join(f"{v:08x}" for v in f).encode("ascii")
    out = bytearray(hdr)
    out.extend(name_bytes)
    while len(out) % 4 != 0:
        out.append(0)
    out.extend(data)
    while len(out) % 4 != 0:
        out.append(0)
    return bytes(out)


def build_probe_initrd(base_cpio: Path, out_cpio: Path, hdesk_bin: Path, probe_bin: Path):
    blob = base_cpio.read_bytes()
    entries = parse_newc(blob)
    hdesk_data = hdesk_bin.read_bytes()
    probe_data = probe_bin.read_bytes()
    out = bytearray()
    authd_fields = None
    authd_data = None
    for name, fields, data in entries:
        if name == "hdesk":
            out.extend(pack_newc_entry("hdesk", fields, hdesk_data))
        elif name == "bin/authd":
            authd_fields = list(fields)
            authd_data = data
            out.extend(pack_newc_entry("bin/authd", fields, probe_data))
        else:
            out.extend(pack_newc_entry(name, fields, data))
    if authd_fields is None or authd_data is None:
        raise RuntimeError("bin/authd not found in base initrd.cpio")
    real_fields = list(authd_fields)
    real_fields[0] += 10000
    out.extend(pack_newc_entry("bin/authd-real", real_fields, authd_data))
    # FS-2: the probe's shared files live in /probe, 0777 (no account may write the image's root)
    probe_dir = [real_fields[0] + 1, 0o040777, 0, 0, 2, 0, 0, 0, 0, 0, 0, 0, 0]
    out.extend(pack_newc_entry("probe", probe_dir, b""))
    trailer_fields = [0] * 13
    trailer_fields[3] = 1
    out.extend(pack_newc_entry("TRAILER!!!", trailer_fields, b""))
    while len(out) % 512 != 0:
        out.append(0)
    out_cpio.write_bytes(bytes(out))


def build_hdesk_and_probe(out_dir: Path, ubin: Path):
    bin_dir = out_dir / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["CI_OUT"] = str(bin_dir)
    if os.environ.get("APPROVAL_CINT_DIR"):
        if not (PINNED_CINT_DIR / "cint").is_file() or not (PINNED_CINT_DIR / "cint.toolchain").is_file():
            raise SystemExit(f"check-approval-binding: APPROVAL_CINT_DIR {PINNED_CINT_DIR} holds no cint and cint.toolchain")
        env["PATH"] = f"{PINNED_CINT_DIR}:{env.get('PATH', '')}"
        env["CINT_TOOLCHAIN"] = str(PINNED_CINT_DIR / "cint.toolchain")
    if os.environ.get("APPROVAL_USE_BUNDLED") == "1":
        hdesk_bin = ubin / "hdesk"   # RG-1: the desk the images take (O/ubin, built from source at HEAD)
    else:
        subprocess.run(["bash", str(REPO_ROOT / "user/ci/build.sh"), "hdesk"], cwd=REPO_ROOT, env=env, check=True)
        hdesk_bin = bin_dir / "hdesk"
    probe_src = REPO_ROOT / "tests/ac/approval-delay-probe.c"
    probe_bin = out_dir / "approval-delay-probe"
    subprocess.run(
        [
            "musl-gcc",
            "-O2",
            "-static",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-o",
            str(probe_bin),
            str(probe_src),
        ],
        check=True,
    )
    return hdesk_bin, probe_bin


def compute_verifiers(probe_bin: Path, ubin: Path):
    parent_req = b"enroll 64 1\nada-parent-01"
    child_req = b"enroll 64 1\nsam-pass-01"
    authd_real = ubin / "authd"   # RG-1: O/ubin, built from source at HEAD
    p_out = subprocess.check_output([str(authd_real)], input=parent_req).decode("ascii").splitlines()
    c_out = subprocess.check_output([str(authd_real)], input=child_req).decode("ascii").splitlines()
    p_salt = p_out[0].split()[1]
    p_ver = p_out[1].split()[1]
    c_salt = c_out[0].split()[1]
    c_ver = c_out[1].split()[1]
    return (
        "daphnis-accounts 1\n"
        f"acct id={p_salt} uid=1000 gid=1000 name=ada role=parent m=64 t=1 salt={p_salt} ver={p_ver} ceil=7\n"
        f"acct id={c_salt} uid=1001 gid=1001 name=sam role=child m=64 t=1 salt={c_salt} ver={c_ver} ceil=0\n"
    )


def make_seed_disk(seed_img: Path, accounts_text: str):
    if seed_img.exists():
        seed_img.unlink()
    acct_file = seed_img.parent / "accounts.seed"
    acct_file.write_text(accounts_text, encoding="ascii")
    env = dict(os.environ, ACCOUNTS=str(acct_file))
    subprocess.run(
        ["bash", str(REPO_ROOT / "tools/mkdisk.sh"), str(seed_img)],
        env=env,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    acct_file.unlink()


class QemuHarness:
    def __init__(self, kernel: Path, initrd: Path, disk_img: Path, run_dir: Path):
        self.run_dir = run_dir
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.serial_path = self.run_dir / "serial.txt"
        self.serial_path.write_bytes(b"")
        self.err_path = self.run_dir / "serial.err"
        self.mon_sock_path = self.run_dir / "mon.sock"
        if self.mon_sock_path.exists():
            self.mon_sock_path.unlink()
        self.serial_file = open(self.serial_path, "wb")
        self.err_file = open(self.err_path, "wb")
        cmd = [
            "qemu-system-x86_64",
            "-display", "none",
            "-accel", os.environ.get("QEMU_ACCEL", "tcg"),
            "-serial", "stdio",
            "-monitor", f"unix:{self.mon_sock_path},server=on,wait=off",
            "-nic", "none",
            "-m", "512",
            "-no-reboot",
            "-device", "isa-debug-exit,iobase=0xf4,iosize=0x04",
            "-cpu", "max",
            "-drive", f"file={disk_img},if=virtio,format=raw,cache=unsafe",
            "-kernel", str(kernel),
            "-initrd", str(initrd),
            "-append", "daphnis.pool=max",
        ]
        self.proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=self.serial_file,
            stderr=self.err_file,
        )
        deadline = time.time() + 10.0
        while not self.mon_sock_path.exists():
            if time.time() >= deadline:
                raise RuntimeError("monitor socket did not appear")
            time.sleep(0.05)
        self.mon = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.mon.connect(str(self.mon_sock_path))
        self.mon.settimeout(0.2)
        time.sleep(0.1)
        self._drain_mon()

    def _drain_mon(self):
        try:
            while self.mon.recv(4096):
                pass
        except OSError:
            pass

    def mon_cmd(self, cmd: str, pause: float = 0.03):
        self.mon.sendall((cmd + "\n").encode("ascii"))
        time.sleep(pause)
        self._drain_mon()

    def send_key(self, key: str, pause: float = 0.03):
        self.mon_cmd(f"sendkey {key}", pause=pause)

    def send_text(self, text: str):
        for ch in text:
            k, shift = CHAR_KEY[ch]
            if shift:
                self.send_key(f"shift-{k}", pause=0.025)
            else:
                self.send_key(k, pause=0.025)

    def serial_text(self) -> str:
        return self.serial_path.read_text(encoding="utf-8", errors="replace")

    def count(self, needle: str) -> int:
        return self.serial_text().count(needle)

    def wait_for(self, needle: str, timeout: float = 20.0, count: int = 1) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.count(needle) >= count:
                return True
            if self.proc.poll() is not None:
                return self.count(needle) >= count
            time.sleep(0.05)
        return self.count(needle) >= count

    def close(self):
        try:
            self.mon.close()
        except OSError:
            pass
        if self.proc.poll() is None:
            try:
                self.proc.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
        self.serial_file.close()
        self.err_file.close()
        if self.err_path.exists() and self.err_path.stat().st_size == 0:
            self.err_path.unlink()
        if self.mon_sock_path.exists():
            self.mon_sock_path.unlink()


def run_flow_boot(kernel: Path, initrd: Path, seed_img: Path, run_dir: Path, meta_out: dict):
    run_dir.mkdir(parents=True, exist_ok=True)
    disk_img = run_dir / "disk.img"
    shutil.copyfile(seed_img, disk_img)
    q = QemuHarness(kernel, initrd, disk_img, run_dir)
    try:
        if not q.wait_for("hdesk: accounts 2", timeout=30.0):
            raise RuntimeError("flow: login screen did not appear")
        time.sleep(0.3)
        q.send_key("down", pause=0.08)
        q.send_text("sam-pass-01\n")
        if not q.wait_for("hdesk: login sam uid 1001", timeout=90.0):
            raise RuntimeError("flow: sam login failed")
        if not q.wait_for("hdesk: terminal 0", timeout=15.0):
            raise RuntimeError("flow: terminal 0 did not open")
        time.sleep(0.3)

        # Open terminal 1 on desktop 2 and start worker 1
        q.send_key("meta_l-2", pause=0.15)
        q.send_key("meta_l-ret", pause=0.2)
        if not q.wait_for("hdesk: terminal 1", timeout=15.0):
            raise RuntimeError("flow: terminal 1 did not open")
        time.sleep(0.25)
        q.send_text("exec authd --worker 1\n")
        if not q.wait_for("approval-probe: worker win=1", timeout=15.0):
            raise RuntimeError("flow: worker 1 did not become ready")

        # Open terminal 2 on desktop 3 and start worker 2
        q.send_key("meta_l-3", pause=0.15)
        q.send_key("meta_l-ret", pause=0.2)
        if not q.wait_for("hdesk: terminal 2", timeout=15.0):
            raise RuntimeError("flow: terminal 2 did not open")
        time.sleep(0.25)
        q.send_text("exec authd --worker 2\n")
        if not q.wait_for("approval-probe: worker win=2", timeout=15.0):
            raise RuntimeError("flow: worker 2 did not become ready")

        # Return to desktop 1 (terminal 0) and launch flow coordinator
        q.send_key("meta_l-1", pause=0.15)
        time.sleep(0.25)
        q.send_text("exec authd --run-flow\n")

        # Phase 1: req_a in window 0, req_b queued in window 1
        if not q.wait_for("|req_a|", timeout=15.0):
            raise RuntimeError("flow: req_a prompt did not open")
        time.sleep(0.15)
        q.send_text("ada-parent-01\n")
        if not q.wait_for("approval-probe: held seq=1 verdict=ok", timeout=90.0):
            raise RuntimeError("flow: seq=1 hold did not start")
        time.sleep(0.1)
        q.send_key("esc", pause=0.08)
        if not q.wait_for("approval-probe: release seq=1 verdict=ok", timeout=20.0):
            raise RuntimeError("flow: seq=1 did not release")
        if not q.wait_for("hdesk: approval stale ignored", timeout=20.0, count=1):
            raise RuntimeError("flow: canceled success was not discarded")

        # Phase 2: 3 wrong passphrases on window 1 prompt, then 4th held wrong passphrase + Esc -> req_c in window 2
        if not (q.count("|req_b|") >= 1 or q.wait_for("|req_b2|", timeout=15.0)):
            raise RuntimeError("flow: window 1 prompt not open for phase 2")
        time.sleep(0.3)
        wrong_count = q.count("hdesk: approval wrong passphrase")
        for idx in range(1, 4):
            q.send_text(f"wrong-pass-0{idx}\n")
            wrong_count += 1
            if not q.wait_for("hdesk: approval wrong passphrase", timeout=30.0, count=wrong_count):
                raise RuntimeError(f"flow: wrong passphrase {idx} did not complete")
            time.sleep(0.1)

        q.send_text("wrong-pass-04\n")
        if not q.wait_for("approval-probe: held seq=2 verdict=no", timeout=90.0):
            raise RuntimeError("flow: seq=2 hold did not start")
        time.sleep(0.1)
        q.send_key("esc", pause=0.08)
        if not q.wait_for("|req_c|", timeout=15.0):
            raise RuntimeError("flow: req_c prompt did not open")
        if not q.wait_for("approval-probe: release seq=2 verdict=no", timeout=20.0):
            raise RuntimeError("flow: seq=2 did not release")
        time.sleep(0.1)

        if not q.wait_for("hdesk: approval stale ignored", timeout=20.0, count=2):
            raise RuntimeError("flow: canceled failure was not discarded")
        # Immediately submit valid passphrase on req_c to verify no 2s lockout was applied from req_b's stale failure
        auth_starts_before_c = q.count("hdesk: auth start 4")
        grants_before_c = q.count("hdesk: grant 2 to pid ")
        q.send_text("ada-parent-01\n")
        phase2_immediate_ok = q.wait_for("hdesk: auth start 4", timeout=1.0, count=auth_starts_before_c + 1)
        meta_out["phase2_immediate_ok"] = phase2_immediate_ok
        if not phase2_immediate_ok:
            # Unpatched red baseline locked out ada for 2s; wait out the lockout and complete req_c
            time.sleep(2.2)
            for _ in range(20):
                q.send_key("backspace", pause=0.015)
            q.send_text("ada-parent-01\n")
        if not q.wait_for("hdesk: grant 2 to pid ", timeout=90.0, count=grants_before_c + 1):
            raise RuntimeError("flow: req_c did not complete")

        # Phase 3: req_exit1 exits before completion + req_exit2 in same window 2
        if not q.wait_for("|req_exit1|", timeout=15.0):
            raise RuntimeError("flow: req_exit1 prompt did not open")
        time.sleep(0.15)
        q.send_text("ada-parent-01\n")
        if not q.wait_for("approval-probe: held seq=3 verdict=ok", timeout=90.0):
            raise RuntimeError("flow: seq=3 hold did not start")
        if not q.wait_for("approval-probe: release seq=3 verdict=ok", timeout=20.0):
            raise RuntimeError("flow: seq=3 did not release")
        if not q.wait_for("|req_exit2|", timeout=15.0):
            raise RuntimeError("flow: req_exit2 prompt did not open")
        if not q.wait_for("hdesk: approval stale ignored", timeout=20.0, count=3):
            raise RuntimeError("flow: exited requester verdict was not discarded")
        grants_before_exit2 = q.count("hdesk: grant 2 to pid ")
        q.send_text("ada-parent-01\n")
        if not q.wait_for("hdesk: grant 2 to pid ", timeout=90.0, count=grants_before_exit2 + 1):
            raise RuntimeError("flow: req_exit2 was not approved by fresh auth")

        # Phase 4: req_lock in window 0 + Super+L lock invalidation
        if not q.wait_for("|req_lock|", timeout=15.0):
            raise RuntimeError("flow: req_lock prompt did not open")
        time.sleep(0.15)
        q.send_text("ada-parent-01\n")
        if not q.wait_for("approval-probe: held seq=4 verdict=ok", timeout=90.0):
            raise RuntimeError("flow: seq=4 hold did not start")
        time.sleep(0.1)
        q.send_key("meta_l-l", pause=0.1)
        if not q.wait_for("approval-probe: release seq=4 verdict=ok", timeout=20.0):
            raise RuntimeError("flow: seq=4 did not release")
        phase4_locked = q.wait_for("hdesk: lock sam", timeout=1.0)
        meta_out["phase4_locked"] = phase4_locked
        if phase4_locked:
            if not q.wait_for("hdesk: approval stale ignored", timeout=20.0, count=4):
                raise RuntimeError("flow: locked request verdict was not discarded")
            q.send_text("sam-pass-01\n")
            if not q.wait_for("hdesk: unlock sam", timeout=90.0):
                raise RuntimeError("flow: sam unlock failed")

        # Phase 5: req_logout1 + req_logout2 + logout invalidation
        if not q.wait_for("|req_logout1|", timeout=15.0):
            raise RuntimeError("flow: req_logout1 prompt did not open")
        time.sleep(0.15)
        q.send_text("ada-parent-01\n")
        if not q.wait_for("approval-probe: held seq=5 verdict=ok", timeout=90.0):
            raise RuntimeError("flow: seq=5 hold did not start")
        if not q.wait_for("hdesk: logout sam", timeout=15.0):
            raise RuntimeError("flow: logout did not occur")
        if not q.wait_for("approval-probe: release seq=5 verdict=ok", timeout=20.0):
            raise RuntimeError("flow: seq=5 did not release")
        if not q.wait_for("hdesk: approval stale ignored", timeout=20.0, count=5):
            raise RuntimeError("flow: logged out request verdict was not discarded")
        q.wait_for("approval-probe: req tag=req_logout2", timeout=10.0)
        time.sleep(0.4)
        q.send_key("meta_l-esc", pause=0.1)
        q.wait_for("daphnis: done", timeout=15.0)
    finally:
        q.close()
        meta_out["qemu_exit"] = q.proc.returncode
        if disk_img.exists():
            disk_img.unlink()


def run_timeout_boot(kernel: Path, initrd: Path, seed_img: Path, run_dir: Path, meta_out: dict):
    run_dir.mkdir(parents=True, exist_ok=True)
    disk_img = run_dir / "disk.img"
    shutil.copyfile(seed_img, disk_img)
    q = QemuHarness(kernel, initrd, disk_img, run_dir)
    try:
        if not q.wait_for("hdesk: accounts 2", timeout=30.0):
            raise RuntimeError("timeout: login screen did not appear")
        time.sleep(0.3)
        q.send_key("down", pause=0.08)
        q.send_text("sam-pass-01\n")
        if not q.wait_for("hdesk: login sam uid 1001", timeout=90.0):
            raise RuntimeError("timeout: sam login failed")
        if not q.wait_for("hdesk: terminal 0", timeout=15.0):
            raise RuntimeError("timeout: terminal 0 did not open")
        time.sleep(0.35)
        q.send_text("authd --run-timeout\n")
        if not q.wait_for("|req_timeout|", timeout=15.0):
            raise RuntimeError("timeout: req_timeout prompt did not open")
        time.sleep(0.15)
        q.send_text("ada-parent-01\n")
        if not q.wait_for("approval-probe: held seq=1 verdict=ok", timeout=90.0):
            raise RuntimeError("timeout: seq=1 hold did not start")
        if not q.wait_for("approval-probe: release seq=1 verdict=ok", timeout=240.0):
            raise RuntimeError("timeout: seq=1 did not release after 123s")
        if not q.wait_for("hdesk: approval stale ignored", timeout=20.0):
            raise RuntimeError("timeout: expired request verdict was not discarded")
        q.wait_for("approval-probe: req tag=req_timeout", timeout=10.0)
        time.sleep(0.4)
        q.send_text("exit\n")
        if not q.wait_for("hdesk: logout sam", timeout=15.0):
            raise RuntimeError("timeout: logout after timeout test failed")
        time.sleep(0.3)
        q.send_key("meta_l-esc", pause=0.1)
        q.wait_for("daphnis: done", timeout=15.0)
    finally:
        q.close()
        meta_out["qemu_exit"] = q.proc.returncode
        if disk_img.exists():
            disk_img.unlink()


def parse_req_lines(serial: str):
    reqs = {}
    for match in re.finditer(r"approval-probe: req ([^\r\n]*)", serial):
        fields = {}
        for tok in match.group(1).split():
            if "=" in tok:
                k, v = tok.split("=", 1)
                try:
                    fields[k] = int(v)
                except ValueError:
                    fields[k] = v
        tag = fields.get("tag")
        if tag:
            reqs.setdefault(str(tag), []).append(fields)
    return reqs


def parse_chain_shell(serial: str):
    for match in re.finditer(r"approval-probe: chain_shell ([^\r\n]*)", serial):
        if match:
            fields = {}
            for tok in match.group(1).split():
                if "=" in tok:
                    k, v = tok.split("=", 1)
                    try:
                        fields[k] = int(v)
                    except ValueError:
                        fields[k] = v
            return fields
    return {}


def main():
    if len(sys.argv) not in (3, 4) or (len(sys.argv) == 4 and sys.argv[3] not in ("flow", "timeout")):
        print(f"usage: {sys.argv[0]} <build-dir> <output-dir>", file=sys.stderr)
        return 2
    build_dir = Path(sys.argv[1]).resolve()
    out_dir = Path(sys.argv[2]).resolve()
    if out_dir == REPO_ROOT or REPO_ROOT in out_dir.parents:
        raise ValueError("output must be outside checkout")
    out_dir.mkdir(parents=True, exist_ok=False)

    kernel = build_dir / "gcc-hdesk/kernel32.elf"
    base_cpio = build_dir / "hdesk/initrd.cpio"
    if not kernel.exists() or not base_cpio.exists():
        raise RuntimeError(f"missing kernel or initrd under {build_dir}")

    identity_paths = subprocess.check_output(["git", "ls-files", "-z"], cwd=REPO_ROOT).split(bytes([0]))
    identity = {os.fsdecode(p): hashlib.sha256((REPO_ROOT / os.fsdecode(p)).read_bytes()).hexdigest()
                for p in identity_paths if p and (REPO_ROOT / os.fsdecode(p)).is_file()}
    initial_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True).strip()
    (out_dir / "source-files.json").write_text(json.dumps(identity, sort_keys=True, indent=2))
    hdesk_bin, probe_bin = build_hdesk_and_probe(out_dir, build_dir / "ubin")
    probe_cpio = out_dir / "probe.cpio"
    build_probe_initrd(base_cpio, probe_cpio, hdesk_bin, probe_bin)

    accounts_text = compute_verifiers(probe_bin, build_dir / "ubin")
    seed_img = out_dir / "seed.img"
    make_seed_disk(seed_img, accounts_text)

    flow_meta = {}
    timeout_meta = {}
    errors = []

    def t_flow():
        try:
            run_flow_boot(kernel, probe_cpio, seed_img, out_dir / "flow", flow_meta)
        except Exception as exc:
            errors.append(f"flow_error: {exc}")

    def t_timeout():
        try:
            run_timeout_boot(kernel, probe_cpio, seed_img, out_dir / "timeout", timeout_meta)
        except Exception as exc:
            errors.append(f"timeout_error: {exc}")

    case = sys.argv[3] if len(sys.argv) == 4 else "all"
    if case != "timeout":
        t_flow()
    if case != "flow":
        t_timeout()

    if seed_img.exists():
        seed_img.unlink()

    flow_serial = (out_dir / "flow/serial.txt").read_text(errors="replace") if case != "timeout" else ""
    timeout_serial = (out_dir / "timeout/serial.txt").read_text(errors="replace") if case != "flow" else ""

    flow_records = parse_req_lines(flow_serial)
    timeout_records = parse_req_lines(timeout_serial)
    flow_reqs = {tag: rows[-1] for tag, rows in flow_records.items()}
    timeout_reqs = {tag: rows[-1] for tag, rows in timeout_records.items()}
    forbidden = {"req_a", "req_b", "req_lock", "req_logout1", "req_logout2", "req_timeout"}
    for tag, rows in {**flow_records, **timeout_records}.items():
        observed = {row.get("auth_ok") for row in rows if row.get("auth_ok") in (0, 1)}
        if len(observed) > 1:
            errors.append(f"conflicting authority outcomes for {tag}")
        if tag in forbidden and 1 in observed:
            errors.append(f"forbidden authority observed for {tag}")
    chain_shell = parse_chain_shell(flow_serial)
    stale_b_note = "approval-probe: note req_b_stale_approved=1" in flow_serial

    req_a = flow_reqs.get("req_a", {})
    req_b = flow_reqs.get("req_b", {})
    req_c = flow_reqs.get("req_c", {})
    req_exit1 = flow_reqs.get("req_exit1", {})
    req_exit2 = flow_reqs.get("req_exit2", {})
    req_lock = flow_reqs.get("req_lock", {})
    req_logout1 = flow_reqs.get("req_logout1", {})
    req_logout2 = flow_reqs.get("req_logout2", {})
    req_timeout = timeout_reqs.get("req_timeout", {})

    # Check 1: Cross-window replacement (req_a canceled -> req_b not approved by req_a's held ok)
    c1_pass = (
        req_a.get("auth_ok") == 0
        and not stale_b_note
        and req_b.get("auth_ok") == 0
    )

    # Check 2: Late wrong-password response for canceled req_b does not increment ac_fails or delay req_c
    c2_pass = (
        bool(flow_meta.get("phase2_immediate_ok"))
        and req_c.get("auth_ok") == 1
    )

    # Check 3: Requester exits before completion + subsequent request from same window 2
    pos_gone = guestlines.find(flow_serial, "hdesk: kern gone pid ")
    pos_exit2_ask = flow_serial.find("|req_exit2|")
    pos_seq3_rel = flow_serial.find("approval-probe: release seq=3 verdict=ok")
    c3_pass = (
        pos_gone != -1
        and pos_exit2_ask != -1
        and pos_seq3_rel != -1
        and pos_gone < pos_seq3_rel
        and pos_exit2_ask < pos_seq3_rel
        and req_exit1.get("auth_ok") == 0
        and req_exit2.get("auth_ok") == 1
        and req_exit2.get("kern_held") == 0
        and chain_shell.get("w2_kern_held") == 0
        and chain_shell.get("w2_kern_open") == -1
    )

    # Check 4: Lock (Super+L) invalidates in-flight approval
    c4_pass = (
        bool(flow_meta.get("phase4_locked"))
        and req_lock.get("auth_ok") == 0
        and guestlines.has(flow_serial, "hdesk: lock sam")
        and guestlines.has(flow_serial, "hdesk: unlock sam")
    )

    # Check 5: Logout invalidates in-flight approval and does not approve queued request on SCR_LOGIN
    c5_pass = (
        req_logout1.get("auth_ok") == 0
        and (req_logout2.get("auth_ok") == 0 or (req_logout2.get("auth_ok") == -1 and req_logout2.get("exited_sig") == 9))
        and guestlines.has(flow_serial, "hdesk: logout sam")
    )

    # Check 6: 120s timeout invalidates in-flight approval before 123s authd release
    pos_to_msg = guestlines.find(timeout_serial, "hdesk: prompt timed out pid ")
    pos_to_rel = timeout_serial.find("approval-probe: release seq=1 verdict=ok")
    c6_pass = (
        pos_to_msg != -1
        and pos_to_rel != -1
        and pos_to_msg < pos_to_rel
        and req_timeout.get("auth_ok") == 0
        and guestlines.has(timeout_serial, "hdesk: approval stale ignored")
    )

    clean_shutdown = (
        guestlines.has(flow_serial, "hdesk: shut down from the account screen")
        and guestlines.has(flow_serial, "daphnis: done")
        and guestlines.has(timeout_serial, "hdesk: shut down from the account screen")
        and guestlines.has(timeout_serial, "daphnis: done")
        and not errors
    )

    flow_clean = (flow_meta.get("qemu_exit") == 33 and guestlines.has(flow_serial, "daphnis: done")
                  and guestlines.has(flow_serial, "hdesk: shut down from the account screen"))
    timeout_clean = (timeout_meta.get("qemu_exit") == 33 and guestlines.has(timeout_serial, "daphnis: done")
                     and guestlines.has(timeout_serial, "hdesk: shut down from the account screen"))
    clean_shutdown = (case == "timeout" or flow_clean) and (case == "flow" or timeout_clean) and not errors
    overall_pass = (case == "timeout" or (c1_pass and c2_pass and c3_pass and c4_pass and c5_pass)) and (case == "flow" or c6_pass) and clean_shutdown

    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(REPO_ROOT)).decode("ascii").strip()
    status = subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=all"], cwd=str(REPO_ROOT)
    ).decode("utf-8")
    if head != initial_head or any(hashlib.sha256((REPO_ROOT / p).read_bytes()).hexdigest() != h for p, h in identity.items()):
        errors.append("source changed during qualification")
        overall_pass = False
    hdesk_sha256 = hashlib.sha256(hdesk_bin.read_bytes()).hexdigest()

    summary = {
        "result": "PASS" if overall_pass else "FAIL",
        "accel": os.environ.get("QEMU_ACCEL", "tcg"),
        "head": head,
        "case": case,
        "status": status,
        "hdesk_sha256": hdesk_sha256,
        "kernel_sha256": hashlib.sha256(kernel.read_bytes()).hexdigest(),
        "probe_initrd_sha256": hashlib.sha256(probe_cpio.read_bytes()).hexdigest(),
        "compiler_sha256": file_sha256(PINNED_CINT_DIR / "cint"),
        "toolchain_sha256": file_sha256(PINNED_CINT_DIR / "cint.toolchain"),
        "timeout_meta": timeout_meta,
        "errors": errors,
        "checks": {
            "cross_window_replacement": c1_pass,
            "stale_wrong_passphrase_no_penalty": c2_pass,
            "requester_exit_and_same_window_next": c3_pass,
            "lock_invalidation": c4_pass,
            "logout_invalidation": c5_pass,
            "timeout_invalidation": c6_pass,
            "clean_shutdown": clean_shutdown,
        },
        "flow_meta": flow_meta,
        "chain_shell": chain_shell,
        "stale_b_note": stale_b_note,
        "all_request_records": {**flow_records, **timeout_records},
        "requests": {
            "req_a": req_a,
            "req_b": req_b,
            "req_c": req_c,
            "req_exit1": req_exit1,
            "req_exit2": req_exit2,
            "req_lock": req_lock,
            "req_logout1": req_logout1,
            "req_logout2": req_logout2,
            "req_timeout": req_timeout,
        },
        "stale_ignored_count_flow": flow_serial.count("hdesk: approval stale ignored"),
        "stale_ignored_count_timeout": timeout_serial.count("hdesk: approval stale ignored"),
    }

    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    lines = [
        f"RESULT: {summary['result']}",
        f"head: {head}",
        f"status: {json.dumps(status)}",
        f"hdesk_sha256: {hdesk_sha256}",
        f"cross_window_replacement: {c1_pass} (req_a.auth_ok={req_a.get('auth_ok')}, req_b_stale_approved={stale_b_note}, req_b.auth_ok={req_b.get('auth_ok')})",
        f"stale_wrong_passphrase_no_penalty: {c2_pass} (phase2_immediate_ok={flow_meta.get('phase2_immediate_ok')}, req_c.auth_ok={req_c.get('auth_ok')})",
        f"requester_exit_and_same_window_next: {c3_pass} (kern_gone={pos_gone != -1}, req_exit1.auth_ok={req_exit1.get('auth_ok')}, req_exit2.auth_ok={req_exit2.get('auth_ok')}, w2_kern_held={chain_shell.get('w2_kern_held')}, w2_kern_open={chain_shell.get('w2_kern_open')})",
        f"lock_invalidation: {c4_pass} (phase4_locked={flow_meta.get('phase4_locked')}, req_lock.auth_ok={req_lock.get('auth_ok')})",
        f"logout_invalidation: {c5_pass} (req_logout1.auth_ok={req_logout1.get('auth_ok')}, req_logout2.auth_ok={req_logout2.get('auth_ok')})",
        f"timeout_invalidation: {c6_pass} (timed_out_before_release={pos_to_msg != -1 and pos_to_rel != -1 and pos_to_msg < pos_to_rel}, req_timeout.auth_ok={req_timeout.get('auth_ok')})",
        f"stale_ignored_count: flow={summary['stale_ignored_count_flow']} timeout={summary['stale_ignored_count_timeout']}",
        f"clean_shutdown: {clean_shutdown}",
    ]
    if errors:
        lines.append(f"errors: {errors}")
    summary_txt = "\n".join(lines) + "\n"
    (out_dir / "summary.txt").write_text(summary_txt, encoding="utf-8")
    print(summary_txt, end="")
    return 0 if overall_pass else 1


if __name__ == "__main__":
    sys.exit(main())
