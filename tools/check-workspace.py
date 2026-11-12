#!/usr/bin/env python3
"""tools/check-workspace.py --out /absolute/fresh-results: the guest acceptance of native workspace persistence and
recovery (docs/guide/workspace-recovery.md).

Per kernel (gcc, clang), each on its own fresh volume of tools/mkcintvol.sh, three QEMU processes boot in turn:
  boot 1  create a project (a directory name with a space) and a source under /home by shell editing, keep a backup,
          build it with the bundled /home/opt/cint/cib into a fresh output name, run it, hash, sync, end normally;
  boot 2  verify what boot 1 saved, break the source on purpose and build into another fresh name (the one expected
          nonzero native command), verify the earlier source backup and executable are intact, restore the source from
          the backup, rebuild into a third fresh name and compare; write and sync a final marker, then wait;
          the host stops exactly this QEMU process (kill of its own child handle) after the guest printed
          `ws-marker final-synced`, without a guest shutdown;
  boot 3  a new process verifies the marker, source, backup and both executables and runs them.
The host never writes the guest's result: it reads `ws-*` receipt lines from each serial transcript and refuses on
any missing phase marker, missing member, wrong hash, unexpected nonzero native command or unexpected guest exit.

Exit status: 0 every leg passed, 1 a leg failed, 2 refused (bad arguments or environment), 3 unrun (a required
dependency is missing; nothing passed)."""
import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WS = os.path.join(ROOT, "tests", "workspace")
LEGS = ("gcc", "clang")
QEMU_STATUS_DONE = 33   # isa-debug-exit: the guest's normal end
PROJECT_DIR = "/home/work/proj one"
FINAL_MARKER_TEXT = b"workspace recovery final marker\n"
TOOLS = ("cint", "gcc", "clang", "musl-gcc", "python3", "sha256sum", "cmp", "git", "qemu-system-x86_64", "mke2fs",
         "debugfs", "e2fsck", "make", "as", "ld", "objcopy", "awk")
CORE_EXTRA = ("sh",)   # cish is /sh and /bin/sh; the native core set fills the rest of /bin

# The receipt names each boot must print, enumerated one by one. A name missing from a transcript fails the leg
# even when every name that is present checks out.
BOOT1 = {
    "phases": ("1 begin", "1 end"),
    "steps": ("mkdir-work", "mkdir-proj", "cd-proj", "write-src", "backup-src", "cib-1", "run-1", "cmp-run-1",
              "sync-1"),
    "hashes": ("src", "bak", "exe1", "run-1-out"),
    "markers": (),
}
BOOT2 = {
    "phases": ("2 begin", "2 end", "3 begin"),
    "steps": ("cd-proj", "run-saved", "break-src", "cib-bad", "run-after-fail", "restore-src", "cib-2", "cmp-exe",
              "run-2", "cmp-run-2", "write-marker", "sync-final"),
    "hashes": ("v-src", "v-bak", "v-exe1", "run-saved-out", "bak-after-fail", "exe1-after-fail",
               "run-after-fail-out", "restored-src", "exe2", "run-2-out"),
    "markers": ("final-synced",),
}
BOOT3 = {
    "phases": ("3 verify begin", "3 verify end"),
    "steps": ("cd-proj", "f-run-1", "f-run-2"),
    "hashes": ("f-marker", "f-src", "f-bak", "f-exe1", "f-exe2", "f-run-1-out", "f-run-2-out"),
    "markers": (),
}
EXPECT_FAIL = {"cib-bad"}   # the only native command that must exit nonzero

# (boot, label, boot, label or literal): the receipt on the left must be the digest on the right. `exp:` names a
# digest the host knows from fixed bytes (the program output, the marker text, the source text of phase1.sh).
EQUAL = (
    (1, "src", "exp", "source"), (1, "bak", "exp", "source"), (1, "run-1-out", "exp", "output"),
    (2, "v-src", 1, "src"), (2, "v-bak", 1, "bak"), (2, "v-exe1", 1, "exe1"),
    (2, "run-saved-out", "exp", "output"),
    (2, "bak-after-fail", 1, "bak"), (2, "exe1-after-fail", 1, "exe1"), (2, "run-after-fail-out", "exp", "output"),
    (2, "restored-src", 1, "src"), (2, "exe2", 1, "exe1"), (2, "run-2-out", "exp", "output"),
    (3, "f-marker", "exp", "marker"), (3, "f-src", 1, "src"), (3, "f-bak", 1, "bak"), (3, "f-exe1", 1, "exe1"),
    (3, "f-exe2", 1, "exe1"), (3, "f-run-1-out", "exp", "output"), (3, "f-run-2-out", "exp", "output"),
)


class Refusal(Exception):
    """The arguments or environment are refused; nothing was started."""


class Unrun(Exception):
    """A required dependency is missing; the acceptance did not run."""


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def inside(path, base):
    path, base = os.path.realpath(path), os.path.realpath(base)
    return os.path.commonpath([path, base]) == base


def validate_out(out, checkout=ROOT):
    """The fresh results directory: absolute, no `..` component, not existing, not within the checkout (also not by
    a symlinked parent), its parent a directory. Returns the path to create."""
    if not out or not os.path.isabs(out):
        raise Refusal("--out must be an absolute path")
    if ".." in out.split(os.sep):
        raise Refusal("--out must not contain a .. component")
    if os.path.lexists(out):
        raise Refusal("%s exists; a fresh results directory is required" % out)
    parent = os.path.dirname(out.rstrip(os.sep)) or os.sep
    if not os.path.isdir(parent):
        raise Refusal("the parent of --out, %s, is not a directory" % parent)
    if inside(os.path.join(os.path.realpath(parent), os.path.basename(out.rstrip(os.sep))), checkout):
        raise Refusal("--out is within the checkout; results stay outside it")
    return out


def parse_receipts(text):
    """Receipt lines of one serial transcript. Returns a dict: steps {name: status}, hashes {label: hex}, markers,
    phases, diag (lines between ws-diag-begin and ws-diag-end), grant (the status of `grant: N`, or None), done
    (the kernel's `daphnis: done` seen), dups (names printed twice), bad (malformed ws- lines)."""
    r = {"steps": {}, "hashes": {}, "markers": [], "phases": [], "diag": [], "grant": None, "done": False,
         "dups": [], "bad": []}
    in_diag = False
    for raw in text.replace("\r", "").split("\n"):
        line = raw.rstrip()
        if line == "ws-diag-begin":
            in_diag = True
            continue
        if line == "ws-diag-end":
            in_diag = False
            continue
        if in_diag:
            r["diag"].append(line)
            continue
        m = re.fullmatch(r"ws-step (\S+) (-?[0-9]+)", line)
        if m:
            if m.group(1) in r["steps"]:
                r["dups"].append("step " + m.group(1))
            r["steps"][m.group(1)] = int(m.group(2))
            continue
        m = re.fullmatch(r"ws-hash (\S+) ([0-9a-f]{64})(?: .*)?", line)
        if m:
            if m.group(1) in r["hashes"]:
                r["dups"].append("hash " + m.group(1))
            r["hashes"][m.group(1)] = m.group(2)
            continue
        m = re.fullmatch(r"ws-marker (\S+)", line)
        if m:
            r["markers"].append(m.group(1))
            continue
        m = re.fullmatch(r"ws-phase ([0-9a-z ]+)", line)
        if m:
            r["phases"].append(m.group(1))
            continue
        m = re.fullmatch(r"grant: (-?[0-9]+)", line)
        if m:
            r["grant"] = int(m.group(1))
            continue
        if line == "daphnis: done":
            r["done"] = True
            continue
        if line.startswith("ws-"):
            r["bad"].append(line)
    return r


def check_boot(exit_problem, receipts, spec_list, normal_end):
    """Failures of one boot's receipts against the enumerated specs (a list of BOOTn dicts the boot covers). An empty
    list is a pass. exit_problem: None when the QEMU process ended as this boot requires, else a description.
    normal_end: the boot ends by itself, so `grant: 0` and the kernel's `daphnis: done` are required."""
    fails = []
    if exit_problem:
        fails.append("guest exit: %s" % exit_problem)
    steps_ok = set()
    for spec in spec_list:
        steps_ok.update(spec["steps"])
    for spec in spec_list:
        for p in spec["phases"]:
            if p not in receipts["phases"]:
                fails.append("missing phase marker ws-phase %s" % p)
        for s in spec["steps"]:
            if s not in receipts["steps"]:
                fails.append("missing step %s" % s)
            elif s in EXPECT_FAIL:
                if receipts["steps"][s] == 0:
                    fails.append("step %s must fail and returned 0" % s)
            elif receipts["steps"][s] != 0:
                fails.append("native command %s returned %d" % (s, receipts["steps"][s]))
        for h in spec["hashes"]:
            if h not in receipts["hashes"]:
                fails.append("missing hash %s" % h)
        for m in spec["markers"]:
            if m not in receipts["markers"]:
                fails.append("missing marker %s" % m)
    for s in receipts["steps"]:
        if s not in steps_ok:
            fails.append("unexpected step %s" % s)
    if "cib-bad" in steps_ok and "cib-bad" in receipts["steps"] and not any(l.strip() for l in receipts["diag"]):
        fails.append("the failing build kept no compiler diagnostic")
    fails += ["duplicate %s" % d for d in receipts["dups"]]
    fails += ["malformed receipt line %r" % b for b in receipts["bad"]]
    if normal_end:
        if receipts["grant"] != 0:
            fails.append("guest script did not end with `grant: 0`")
        if not receipts["done"]:
            fails.append("kernel did not print `daphnis: done`")
    return fails


def check_equal(rec, expected):
    """Failures of the EQUAL table. rec: {boot number: receipts}; expected: the host-known digests. Every row is
    checked: a row with a missing side fails, so the subset of what was produced cannot pass."""
    fails = []
    for lb, ll, rb, rl in EQUAL:
        left = rec.get(lb, {}).get("hashes", {}).get(ll) if rec.get(lb) else None
        if rb == "exp":
            right = expected.get(rl)
            rname = "expected " + rl
        else:
            right = rec.get(rb, {}).get("hashes", {}).get(rl) if rec.get(rb) else None
            rname = "boot %s %s" % (rb, rl)
        if left is None or right is None:
            fails.append("cannot compare boot %s %s with %s: member missing" % (lb, ll, rname))
        elif left != right:
            fails.append("boot %s %s %s differs from %s %s" % (lb, ll, left[:12], rname, right[:12]))
    return fails


def heredoc_body(script_text, tag="SRC"):
    """The text between `<<'SRC'` and the line SRC in a phase script (what the guest writes as the source)."""
    m = re.search(r"<<'%s'\n(.*?)\n%s\n" % (tag, tag), script_text, re.S)
    if not m:
        raise Refusal("no <<'%s' here-document in the phase script" % tag)
    return (m.group(1) + "\n").encode()


def expected_digests(ws_dir=WS):
    with open(os.path.join(ws_dir, "phase1.sh")) as f:
        source = heredoc_body(f.read())
    with open(os.path.join(ws_dir, "expected.txt"), "rb") as f:
        output = f.read()
    return {"source": sha256_bytes(source), "output": sha256_bytes(output), "marker": sha256_bytes(FINAL_MARKER_TEXT)}


def qemu_argv(kernel, initrd, volume, mem=512):
    """QEMU's argv as tools/run-qemu.sh builds it for the disk legs (KVM, no display, serial on stdout, isa-debug-exit)
    with the volume's cache mode `writeback`: QEMU honors the guest's flush, and nothing is `cache=unsafe`."""
    argv = ["qemu-system-x86_64", "-display", "none", "-accel", "kvm", "-serial", "stdio", "-monitor", "none",
            "-nic", "none", "-m", str(mem), "-no-reboot", "-device", "isa-debug-exit,iobase=0xf4,iosize=0x04",
            "-drive", "file=%s,if=virtio,format=raw,cache=writeback" % volume,
            "-kernel", kernel, "-initrd", initrd, "-append", "daphnis.pool=max"]
    if any("unsafe" in a for a in argv):
        raise Refusal("cache=unsafe is never used")
    return argv


def guest_input(script_text):
    """The serial input of a boot: the phase script run by cish under the disk grant, ended by byte 0x04."""
    body = "".join(l + "\n" for l in script_text.split("\n") if l and not l.startswith("#"))
    return ("./grant disk ./sh <<'EOF'\n%sEOF\necho grant: $?\nexit 0\n\x04" % body).encode()


class Vm:
    """One QEMU process this test started. It owns the child handle and stops only that handle: no process-name
    killing, no host power change, nothing about any other QEMU."""

    def __init__(self, argv, input_path, transcript, errfile):
        self.argv = argv
        self.transcript = transcript
        self.started = time.time()
        self._files = [open(input_path, "rb"), open(transcript, "wb"), open(errfile, "wb")]
        self.proc = subprocess.Popen(argv, stdin=self._files[0], stdout=self._files[1], stderr=self._files[2])
        self.stopped_by_us = False

    def transcript_text(self):
        with open(self.transcript, "rb") as f:
            return f.read().decode("utf-8", "replace")

    def wait_marker(self, marker, deadline):
        """True when `ws-marker MARKER` is in the transcript; False when the process ended first or the deadline
        passed (the caller reads poll() to tell which)."""
        want = "ws-marker %s" % marker
        while time.time() < deadline:
            if want in self.transcript_text().replace("\r", "").split("\n"):
                return True
            if self.proc.poll() is not None:
                return want in self.transcript_text().replace("\r", "").split("\n")
            time.sleep(0.05)
        return False

    def wait_end(self, deadline):
        """The exit status, or None after the deadline (the process is then stopped and stays recorded as ours)."""
        while time.time() < deadline:
            rc = self.proc.poll()
            if rc is not None:
                self.close()
                return rc
            time.sleep(0.05)
        self.stop()
        return None

    def stop(self):
        """SIGKILL of this child alone; reaps it. Returns its status (-9 when the signal ended it)."""
        if self.proc.poll() is None:
            self.stopped_by_us = True
            self.proc.send_signal(signal.SIGKILL)
        rc = self.proc.wait()
        self.close()
        return rc

    def close(self):
        for f in self._files:
            if not f.closed:
                f.close()


class Run:
    """The results directory: every command, its time and its log, and the machine-readable summary."""

    def __init__(self, out):
        self.out = out
        self.commands = []
        self.n = 0
        self.env = dict(os.environ)
        self.env["PATH"] = os.environ.get("PATH", "") + ":/usr/sbin:/sbin"

    def path(self, *p):
        return os.path.join(self.out, *p)

    def cmd(self, label, argv, cwd=ROOT, check=True, env=None):
        self.n += 1
        log = self.path("logs", "%02d-%s.log" % (self.n, label))
        t0 = time.time()
        with open(log, "wb") as f:
            p = subprocess.run(argv, cwd=cwd, env=env or self.env, stdin=subprocess.DEVNULL, stdout=f,
                               stderr=subprocess.STDOUT)
        rec = {"label": label, "argv": argv, "cwd": cwd, "status": p.returncode, "seconds": round(time.time() - t0, 2),
               "log": log}
        self.commands.append(rec)
        if check and p.returncode != 0:
            raise RuntimeError("%s failed with status %d, see %s" % (label, p.returncode, log))
        return rec


def which_all(names, path):
    return [n for n in names if shutil.which(n, path=path) is None]


def toolchain_field(path, key):
    with open(path) as f:
        for line in f:
            w = line.split()
            if len(w) >= 2 and w[0] == key:
                return w[1]
    return None


def pin(key):
    with open(os.path.join(ROOT, "toolchain.pin")) as f:
        for line in f:
            if line.startswith(key + "="):
                return line.strip().split("=", 1)[1]
    return None


def core_tools():
    with open(os.path.join(ROOT, "Makefile")) as f:
        for line in f:
            if line.startswith("CORE_TOOLS := "):
                return [t for t in line.split(":=", 1)[1].split() if t != "fetch"]
    raise Refusal("CORE_TOOLS not found in the Makefile")


def initrd_args(out_path, fx_dir, ub):
    """mkcpio arguments: cish as /sh and /bin/sh, the grant tool, the native core commands in /bin (no busybox) and
    the expected-output fixture at /fx/expected.txt; the programs from ub, the Makefile's O/ubin (RG-1)."""
    args = [out_path, "sh=%s/cish" % ub, "bin/", "bin/sh=%s/cish" % ub, "grant=%s/grant" % ub]
    for t in core_tools():
        name = "[" if t == "bracket" else t
        args.append("bin/%s=%s/%s" % (name, ub, t))
    args += ["fx/", "fx/expected.txt=%s" % os.path.join(fx_dir, "expected.txt")]
    return args


def check_environment(env=os.environ):
    """Refusals and unrun conditions before anything is created. Returns the toolchain path."""
    tc = env.get("CINT_TOOLCHAIN")
    if not tc:
        raise Refusal("CINT_TOOLCHAIN must be set to the qualified cint toolchain file")
    if not os.path.isfile(tc):
        raise Unrun("CINT_TOOLCHAIN %s is not a file" % tc)
    path = env.get("PATH", "") + ":/usr/sbin:/sbin"
    missing = which_all(TOOLS, path)
    if missing:
        raise Unrun("not found: " + " ".join(missing))
    if not os.access("/dev/kvm", os.W_OK):
        raise Unrun("/dev/kvm is not writable; the three-boot sequence needs KVM")
    return tc


def toolchain_identity(tc, run):
    inc = toolchain_field(tc, "include")
    srcs = toolchain_field(tc, "compiler_sources")
    cint_bin = os.path.realpath(shutil.which("cint"))
    ident = {
        "toolchain_file": tc, "toolchain_file_sha256": sha256_file(tc),
        "cint_executable": cint_bin, "cint_executable_sha256": sha256_file(cint_bin),
        "toolchain_executable_sha256": toolchain_field(tc, "executable_sha256"),
        "compiler_source_identity": sha256_file(srcs) if srcs and os.path.isfile(srcs) else None,
        "pinned_compiler_source_identity": pin("compiler_source_identity"),
        "cint_rt_h_sha256": sha256_file(os.path.join(inc, "cint_rt.h")) if inc else None,
        "pinned_cint_rt_h_sha256": pin("cint_rt_h_sha256"), "cint_tag": pin("cint_tag"),
    }
    if ident["compiler_source_identity"] != ident["pinned_compiler_source_identity"]:
        raise Unrun("compiler source identity differs from toolchain.pin")
    if ident["cint_rt_h_sha256"] != ident["pinned_cint_rt_h_sha256"]:
        raise Unrun("cint_rt.h differs from toolchain.pin")
    if ident["cint_executable_sha256"] != ident["toolchain_executable_sha256"]:
        raise Unrun("the cint on PATH is not the executable the toolchain file names")
    return ident


def bundled_toolchain_hashes():
    """SHA-256 of every file of the toolchain bundled at /home/opt/cint (user/cint/opt), as the repository holds it."""
    base = os.path.join(ROOT, "user", "cint", "opt")
    out = {}
    for d, _, files in os.walk(base):
        for f in sorted(files):
            p = os.path.join(d, f)
            out[os.path.relpath(p, base)] = sha256_file(p)
    return dict(sorted(out.items()))


def pinned_volume_digest():
    with open(os.path.join(ROOT, "tests", "expected", "cint-volume.sha256")) as f:
        for line in f:
            w = line.split()
            if len(w) == 2 and w[1] == "vol.img":
                return w[0]
    return None


def run_leg(run, cc, kernel, initrd, expected, timeouts):
    leg = {"leg": cc, "boots": [], "failures": [], "kernel": kernel, "kernel_sha256": sha256_file(kernel),
           "initrd": initrd, "initrd_sha256": sha256_file(initrd)}
    d = run.path(cc)
    os.makedirs(d)
    vol = os.path.join(d, "vol.img")
    run.cmd("%s-mkcintvol" % cc, [os.path.join(ROOT, "tools", "mkcintvol.sh"), vol])
    leg["volume"] = vol
    leg["volume_sha256_fresh"] = sha256_file(vol)
    leg["volume_matches_cint_volume_pin"] = leg["volume_sha256_fresh"] == pinned_volume_digest()
    # the bundled toolchain as the volume holds it, read with debugfs (no mount), is the bytes of cint-opt.sha256
    dump = os.path.join(d, "opt-dump")
    os.makedirs(dump)
    run.cmd("%s-debugfs-rdump" % cc, ["debugfs", "-R", "rdump /opt/cint %s" % dump, vol])
    rec = run.cmd("%s-opt-pin" % cc, ["sha256sum", "--quiet", "-c",
                                      os.path.join(ROOT, "tests", "expected", "cint-opt.sha256")],
                  cwd=os.path.join(dump, "cint"), check=False)
    leg["bundled_toolchain_in_volume_ok"] = rec["status"] == 0
    if rec["status"] != 0:
        leg["failures"].append("the bundled toolchain in the fresh volume is not the bytes of "
                               "tests/expected/cint-opt.sha256")
        return leg
    receipts = {}
    scripts = {}
    for n in (1, 2, 3):
        with open(os.path.join(WS, "phase%d.sh" % n)) as f:
            scripts[n] = f.read()
        with open(os.path.join(d, "boot%d.in" % n), "wb") as f:
            f.write(guest_input(scripts[n]))
    for n in (1, 2, 3):
        boot = {"boot": n, "argv": qemu_argv(kernel, initrd, vol)}
        t0 = time.time()
        vm = Vm(boot["argv"], os.path.join(d, "boot%d.in" % n), os.path.join(d, "boot%d.serial" % n),
                os.path.join(d, "boot%d.stderr" % n))
        boot["pid"] = vm.proc.pid
        if n == 2:
            seen = vm.wait_marker("final-synced", time.time() + timeouts["boot"])
            early = vm.proc.poll()
            boot["marker_seen"] = seen
            boot["rc"] = vm.stop()
            boot["stopped_by_test"] = vm.stopped_by_us
            ok = seen and early is None and boot["rc"] == -signal.SIGKILL
            if not seen:
                boot["why"] = "exited before the marker (status %s)" % early if early is not None else "no marker"
            boot["e2fsck"] = fsck(run, "%s-e2fsck-after-stop" % cc, vol, d, "e2fsck-after-stop.log")
        else:
            boot["rc"] = vm.wait_end(time.time() + timeouts["boot"])
            ok = boot["rc"] == QEMU_STATUS_DONE
            if n == 3:
                boot["e2fsck"] = fsck(run, "%s-e2fsck-final" % cc, vol, d, "e2fsck-final.log")
        boot["seconds"] = round(time.time() - t0, 2)
        boot["serial"] = os.path.join(d, "boot%d.serial" % n)
        boot["serial_sha256"] = sha256_file(boot["serial"])
        boot["stderr_bytes"] = os.path.getsize(os.path.join(d, "boot%d.stderr" % n))
        boot["volume_sha256_after"] = sha256_file(vol)
        receipts[n] = parse_receipts(vm.transcript_text())
        specs = {1: [BOOT1], 2: [BOOT2], 3: [BOOT3]}[n]
        why = None if ok else boot.get("why") or "unexpected guest exit, status %s" % boot["rc"]
        fails = check_boot(why, receipts[n], specs, normal_end=(n != 2))
        if boot["stderr_bytes"]:
            fails.append("QEMU wrote to stderr")
        if "e2fsck" in boot and boot["e2fsck"]["status"] != 0:
            fails.append("e2fsck -fn status %d" % boot["e2fsck"]["status"])
        boot["failures"] = fails
        leg["boots"].append(boot)
        if n == 2:
            boot["diagnostic"] = receipts[2]["diag"]
        if fails:
            leg["failures"] += ["boot %d: %s" % (n, f) for f in fails]
            break
    else:
        leg["failures"] += check_equal(receipts, expected)
    leg["hashes"] = {n: r["hashes"] for n, r in receipts.items()}
    return leg


def fsck(run, label, vol, d, name):
    """e2fsck -fn only (never a repair); the output is kept."""
    rec = run.cmd(label, ["e2fsck", "-fn", vol], check=False)
    shutil.copy(rec["log"], os.path.join(d, name))
    return {"status": rec["status"], "log": os.path.join(d, name)}


def render_report(summary):
    lines = ["workspace recovery acceptance: %s" % summary["result"], "head: %s" % summary.get("head", "?"),
             "compiler: %s" % json.dumps(summary.get("toolchain", {}), sort_keys=True)]
    for leg in summary.get("legs", []):
        lines.append("")
        lines.append("leg %s: %s" % (leg["leg"], "PASS" if not leg["failures"] else "FAIL"))
        for b in leg["boots"]:
            what = {1: "phase 1 build and save", 2: "phase 2 recovery after failed build, then phase 3 abrupt stop",
                    3: "phase 3 recovery after the stop"}[b["boot"]]
            lines.append("  boot %d (%s): rc %s, %.1f s, %s" % (b["boot"], what, b["rc"], b["seconds"],
                                                              "ok" if not b["failures"] else "FAIL"))
            if b["boot"] == 2:
                lines.append("    compiler diagnostic of the deliberate syntax error: %s" % " | ".join(
                    l for l in b.get("diagnostic", []) if l.strip()))
                lines.append("    abrupt stop: marker seen %s, stopped by test %s, e2fsck -fn status %s" % (
                    b.get("marker_seen"), b.get("stopped_by_test"), b.get("e2fsck", {}).get("status")))
            if b["boot"] == 3:
                lines.append("    e2fsck -fn status %s" % b.get("e2fsck", {}).get("status"))
        for f in leg["failures"]:
            lines.append("  FAIL: " + f)
    for u in summary.get("unrun", []):
        lines.append("UNRUN: " + u)
    return "\n".join(lines) + "\n"


def unrun_commands(out):
    return ["CINT_TOOLCHAIN=/path/to/cint.toolchain python3 -B tools/check-workspace.py --out %s" % out]


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0], allow_abbrev=False)
    ap.add_argument("--out", required=True, help="absolute path of a fresh results directory (must not exist)")
    args = ap.parse_args(argv)
    try:
        out = validate_out(args.out)
    except Refusal as e:
        print("check-workspace: refused: %s" % e, file=sys.stderr)
        return 2
    try:
        tc = check_environment()
    except Refusal as e:
        print("check-workspace: refused: %s" % e, file=sys.stderr)
        return 2
    except Unrun as e:
        print("UNRUN: %s" % e)
        print("run it with: " + unrun_commands(out)[0])
        return 3
    os.makedirs(out)
    os.makedirs(os.path.join(out, "logs"))
    run = Run(out)
    run.env["CINT_TOOLCHAIN"] = tc
    git_before = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True).stdout
    summary = {"result": "FAIL", "head": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                                                         text=True).stdout.strip(), "legs": [], "unrun": []}
    t0 = time.time()
    try:
        summary["toolchain"] = toolchain_identity(tc, run)
        summary["bundled_toolchain_sha256"] = bundled_toolchain_hashes()
        build = run.path("build")
        run.cmd("make-kernels", ["make", "-s", "-j%d" % (os.cpu_count() or 2), "O=" + build, "FLAVORS=disk",
                                 os.path.join(build, "gcc-disk", "kernel32.elf"),
                                 os.path.join(build, "clang-disk", "kernel32.elf")])
        ub = os.path.join(build, "ubin")   # RG-1: the programs, built from source at HEAD by make
        run.cmd("make-programs", ["make", "-s", "-j%d" % (os.cpu_count() or 2), "O=" + build] +
                [os.path.join(ub, t) for t in ["cish", "grant"] + core_tools()])
        initrd = run.path("initrd.cpio")
        run.cmd("mkcpio", [sys.executable, "-B", os.path.join(ROOT, "tools", "mkcpio.py")] + initrd_args(initrd, WS, ub))
        summary["initrd"] = {"path": initrd, "sha256": sha256_file(initrd)}
        expected = expected_digests()
        for cc in LEGS:
            summary["legs"].append(run_leg(run, cc, os.path.join(build, "%s-disk" % cc, "kernel32.elf"), initrd,
                                           expected, {"boot": 900}))
        failed = any(l["failures"] for l in summary["legs"])
        summary["result"] = "FAIL" if failed else "PASS"
    except Unrun as e:
        summary["result"] = "UNRUN"
        summary["unrun"].append(str(e))
        summary["unrun_commands"] = unrun_commands(out)
    except (RuntimeError, OSError, Refusal) as e:
        summary["result"] = "FAIL"
        summary["error"] = str(e)
    git_after = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True).stdout
    if git_after != git_before:
        summary["result"] = "FAIL"
        summary["error"] = "the run changed the checkout"
    summary["seconds"] = round(time.time() - t0, 1)
    summary["commands"] = run.commands
    with open(run.path("summary.json"), "w") as f:
        json.dump(summary, f, indent=2, sort_keys=True)
    report = render_report(summary)
    with open(run.path("report.txt"), "w") as f:
        f.write(report)
    sys.stdout.write(report)
    print("results: %s" % out)
    return {"PASS": 0, "FAIL": 1, "UNRUN": 3}[summary["result"]]


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
