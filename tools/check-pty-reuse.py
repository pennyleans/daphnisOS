#!/usr/bin/env python3
"""PR 225 review P1: every terminal window gives its pty pair back when it closes.

Usage: check-pty-reuse.py BUILD OUT [HDESK]

The kernel has 8 pty pairs (src/pty.ci PTYS). Two boots of the hdesk flavor on a volume with accounts:
  terminals: sam logs in, then 9 times opens a terminal (Super+Enter) and ends its shell (`exit`);
  sessions:  9 times sam logs in and ends the session's first shell (`exit`), which logs out.
Each new terminal must open (`hdesk: terminal N slot S pid P`) and none may report `hdesk: no pty`. A desk that keeps
the masters runs out at the 8th pair. HDESK (default: BUILD/ubin/hdesk, the desk the images take, built from source at HEAD) is the desk under test.
"""

import importlib.util
import json
import shutil
import sys
import threading
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("binding", REPO_ROOT / "tools/check-approval-binding.py")
binding = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(binding)
ROUNDS = 9


def login(q, n):
    if not q.wait_for("hdesk: accounts 2", timeout=60.0, count=n):
        raise RuntimeError(f"login screen {n} did not appear")
    time.sleep(0.4)
    q.send_key("down", pause=0.08)
    q.send_text("sam-pass-01\n")
    if not q.wait_for("hdesk: login sam uid 1001", timeout=90.0, count=n):
        raise RuntimeError(f"login {n} failed")


def boot(kind, kernel, initrd, seed, run_dir, meta):
    run_dir.mkdir(parents=True, exist_ok=True)
    disk = run_dir / "disk.img"
    shutil.copyfile(seed, disk)
    q = binding.QemuHarness(kernel, initrd, disk, run_dir)
    meta["opened"] = 0
    try:
        login(q, 1)
        if not q.wait_for("hdesk: terminal 0 slot", timeout=15.0):
            raise RuntimeError("terminal 0 did not open")
        time.sleep(0.4)
        for k in range(1, ROUNDS + 1):
            if kind == "terminals":
                before = q.count(" slot ")
                q.send_key("meta_l-ret", pause=0.2)
                if not q.wait_for(" slot ", timeout=15.0, count=before + 1):
                    raise RuntimeError(f"terminal {k} did not open")
                meta["opened"] = k
                time.sleep(0.4)
                ended = q.count(" ended, status ")
                q.send_text("exit\n")
                if not q.wait_for(" ended, status ", timeout=15.0, count=ended + 1):
                    raise RuntimeError(f"terminal {k} did not end")
                time.sleep(0.3)
            else:
                q.send_text("exit\n")
                if not q.wait_for("hdesk: logout sam", timeout=20.0, count=k):
                    raise RuntimeError(f"logout {k} did not happen")
                login(q, k + 1)
                if not q.wait_for(" slot ", timeout=15.0, count=k + 1):
                    raise RuntimeError(f"session {k + 1}'s terminal did not open")
                meta["opened"] = k
                time.sleep(0.4)
        if kind == "terminals":
            q.send_text("exit\n")
            q.wait_for("hdesk: logout sam", timeout=20.0)
        else:
            q.send_text("exit\n")
            q.wait_for("hdesk: logout sam", timeout=20.0, count=ROUNDS + 1)
        time.sleep(0.4)
        q.send_key("meta_l-esc", pause=0.2)
        q.wait_for("daphnis: done", timeout=20.0)
    except Exception as exc:
        meta["error"] = str(exc)
        q.send_key("meta_l-esc", pause=0.2)
        q.wait_for("daphnis: done", timeout=10.0)
    finally:
        q.close()
        meta["qemu_exit"] = q.proc.returncode
        disk.unlink(missing_ok=True)


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
    # the hybrid image with the desk under test, and authd as it is (binding's probe initrd takes its own authd)
    entries = binding.parse_newc(base_cpio.read_bytes())
    out = bytearray()
    for name, fields, data in entries:
        out.extend(binding.pack_newc_entry(name, fields, hdesk_bin.read_bytes() if name == "hdesk" else data))
    trailer = [0] * 13
    trailer[3] = 1
    out.extend(binding.pack_newc_entry("TRAILER!!!", trailer, b""))
    out.extend(b"\0" * (-len(out) % 512))
    initrd = out_dir / "initrd.cpio"
    initrd.write_bytes(bytes(out))
    seed = out_dir / "seed.img"
    binding.make_seed_disk(seed, binding.compute_verifiers(None, build_dir / "ubin"))

    metas = {"terminals": {}, "sessions": {}}
    threads = [threading.Thread(target=boot, args=(k, kernel, initrd, seed, out_dir / k, metas[k])) for k in metas]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    seed.unlink(missing_ok=True)

    ok = True
    lines = []
    for k, meta in metas.items():
        serial = (out_dir / k / "serial.txt").read_text(errors="replace")
        good = (meta.get("opened") == ROUNDS and "error" not in meta and "hdesk: no pty" not in serial
                and meta.get("qemu_exit") == 33)
        ok = ok and good
        lines.append(f"{k}: {'PASS' if good else 'FAIL'} opened {meta.get('opened')} of {ROUNDS}, "
                     f"no pty {serial.count('hdesk: no pty')}, qemu {meta.get('qemu_exit')}"
                     + (f", {meta['error']}" if "error" in meta else ""))
    summary = {"result": "PASS" if ok else "FAIL", "hdesk_sha256": binding.file_sha256(hdesk_bin),
               "kernel_sha256": binding.file_sha256(kernel), "boots": metas, "lines": lines}
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f"RESULT: {summary['result']}")
    print(f"hdesk_sha256: {summary['hdesk_sha256']}")
    for line in lines:
        print(f"  {line}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
