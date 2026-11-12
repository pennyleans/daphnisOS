"""Tests for tools/desk.sh: argument handling, validation and receipts, against a fake QEMU that is never evaluated."""
import hashlib
import json
import os
import shutil
import stat
import subprocess
import tempfile
import unittest

ROOT = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
DESK = os.path.join(ROOT, "tools", "desk.sh")

FAKE_QEMU = r"""#!/bin/sh
if [ "${1:-}" = --version ]; then echo "QEMU emulator version 0.0.0 (fake)"; exit 0; fi
: > "$FAKE_QEMU_LOG"
for a in "$@"; do printf '%s\0' "$a" >> "$FAKE_QEMU_LOG"; done
env | grep -E '^(QEMU_EXTRA|NET|NET_FWD|SOUND|PLAY|PLAY_DISPLAY|MONITOR|DISK|INITRD|MODE|POOL|RTC|APPEND|CPU|KVM|MEM|QEMU_TIMEOUT|STDIN_FILE)=' > "$FAKE_QEMU_LOG.env"
echo 'fake serial line'
echo 'fake diagnostic' >&2
if [ -n "${FAKE_QEMU_SLEEP:-}" ]; then exec sleep "$FAKE_QEMU_SLEEP"; fi
exit "${FAKE_QEMU_STATUS:-33}"
"""


def read(path):
    with open(path) as f:
        return f.read()


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


class Desk(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="desk-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.bin = os.path.join(self.tmp, "bin")
        os.mkdir(self.bin)
        self.fake = os.path.join(self.bin, "qemu-system-x86_64")
        with open(self.fake, "w") as f:
            f.write(FAKE_QEMU)
        os.chmod(self.fake, 0o755)
        self.log = os.path.join(self.tmp, "qemu-argv.log")
        self.kvm = os.path.join(self.tmp, "kvm")
        open(self.kvm, "w").close()
        self.inputs = os.path.join(self.tmp, "in")
        os.mkdir(self.inputs)
        self.kernel = self.make("kernel32.elf", b"kernel bytes")
        self.initrd = self.make("initrd.cpio", b"initrd bytes")
        self.volume = self.make("work.img", b"volume bytes" * 100)
        self.runs = os.path.join(self.tmp, "runs")
        os.mkdir(self.runs)
        self.n = 0

    def make(self, name, data, where=None):
        path = os.path.join(where or self.inputs, name)
        with open(path, "wb") as f:
            f.write(data)
        return path

    def out(self):
        self.n += 1
        return os.path.join(self.runs, "run%d" % self.n)

    def env(self, **extra):
        env = {"PATH": self.bin + ":" + os.environ.get("PATH", "/usr/bin:/bin"), "DISPLAY": ":99",
               "FAKE_QEMU_LOG": self.log, "HOME": self.tmp}
        env.update(extra)
        return env

    def run_desk(self, *args, env=None, **kw):
        base = ["--kernel", self.kernel, "--initrd", self.initrd, "--volume", self.volume,
                "--out", kw.pop("out", None) or self.out(), "--accel", "tcg", "--headless"]
        if args and args[0] == "RAW":
            base = list(args[1:])
        else:
            base += list(args)
        full = ["bash", DESK] + base
        return subprocess.run(full, env=env or self.env(), capture_output=True, text=True, timeout=60, **kw)

    def argv(self):
        with open(self.log, "rb") as f:
            data = f.read()
        return [a.decode() for a in data.split(b"\0")[:-1]]

    def receipt(self, out):
        with open(os.path.join(out, "receipt.json")) as f:
            return json.load(f)

    # help and dependencies

    def test_help_needs_no_qemu_compiler_or_display(self):
        r = subprocess.run(["/bin/bash", DESK, "--help"], env={"PATH": "/nonexistent"}, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("usage: bash tools/desk.sh", r.stdout)

    def test_missing_arguments_and_unknown_option(self):
        for args in ([], ["--kernel"], ["--bogus"]):
            r = subprocess.run(["bash", DESK] + args, env=self.env(), capture_output=True, text=True)
            self.assertEqual(r.returncode, 2, args)

    def test_missing_qemu_is_refused(self):
        r = self.run_desk("--qemu", os.path.join(self.tmp, "no-such-qemu"))
        self.assertEqual(r.returncode, 2)
        self.assertIn("qemu", r.stderr)
        r = self.run_desk("--qemu", "qemu-that-is-not-on-path")
        self.assertEqual(r.returncode, 2)
        self.assertIn("not found", r.stderr)

    def test_non_executable_qemu_is_refused(self):
        plain = self.make("qemu-plain", b"#!/bin/sh\n", self.bin)
        r = self.run_desk("--qemu", plain)
        self.assertEqual(r.returncode, 2)

    def test_missing_display_is_refused_without_headless(self):
        base = ["--kernel", self.kernel, "--initrd", self.initrd, "--volume", self.volume,
                "--out", self.out(), "--accel", "tcg"]
        env = self.env()
        del env["DISPLAY"]
        r = subprocess.run(["bash", DESK] + base, env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertIn("--headless", r.stderr)

    def test_window_mode_uses_gtk_and_headless_none(self):
        base = ["--kernel", self.kernel, "--initrd", self.initrd, "--volume", self.volume, "--accel", "tcg"]
        r = subprocess.run(["bash", DESK] + base + ["--out", self.out()], env=self.env(), capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        a = self.argv()
        self.assertEqual(a[a.index("-display") + 1], "gtk,zoom-to-fit=on")
        r = self.run_desk()
        self.assertEqual(r.returncode, 0, r.stderr)
        a = self.argv()
        self.assertEqual(a[a.index("-display") + 1], "none")

    # inputs

    def test_absent_and_unreadable_inputs(self):
        os.unlink(self.kernel)
        r = self.run_desk()
        self.assertEqual(r.returncode, 2)
        self.assertIn("--kernel does not exist", r.stderr)
        self.kernel = self.make("kernel32.elf", b"k")
        os.unlink(self.initrd)
        self.assertEqual(self.run_desk().returncode, 2)
        self.initrd = self.make("initrd.cpio", b"i")
        os.unlink(self.volume)
        out = self.out()
        self.assertEqual(self.run_desk(out=out).returncode, 2)
        self.assertFalse(os.path.exists(self.volume), "the launcher must never create the volume")
        self.assertFalse(os.path.exists(out))
        self.volume = self.make("work.img", b"v")
        os.chmod(self.initrd, 0)
        if os.access(self.initrd, os.R_OK):
            self.skipTest("running as a user that reads mode 0 files")
        self.assertEqual(self.run_desk().returncode, 2)

    def test_relative_paths_are_refused(self):
        r = self.run_desk("RAW", "--kernel", "kernel32.elf", "--initrd", self.initrd, "--volume", self.volume,
                          "--out", self.out(), "--accel", "tcg", "--headless")
        self.assertEqual(r.returncode, 2)
        self.assertIn("absolute", r.stderr)

    def test_nonregular_volume(self):
        d = os.path.join(self.inputs, "dirvol")
        os.mkdir(d)
        r = self.run_desk("RAW", "--kernel", self.kernel, "--initrd", self.initrd, "--volume", d,
                          "--out", self.out(), "--accel", "tcg", "--headless")
        self.assertEqual(r.returncode, 2)
        self.assertIn("regular file", r.stderr)
        fifo = os.path.join(self.inputs, "fifovol")
        os.mkfifo(fifo)
        r = self.run_desk("RAW", "--kernel", self.kernel, "--initrd", self.initrd, "--volume", fifo,
                          "--out", self.out(), "--accel", "tcg", "--headless")
        self.assertEqual(r.returncode, 2)
        self.assertIn("regular file", r.stderr)

    def test_empty_volume_is_refused(self):
        empty = self.make("empty.img", b"")
        r = self.run_desk("RAW", "--kernel", self.kernel, "--initrd", self.initrd, "--volume", empty,
                          "--out", self.out(), "--accel", "tcg", "--headless")
        self.assertEqual(r.returncode, 2)

    def test_bad_dimensions(self):
        for mode in ("1920", "1920x", "x1080", "0x0", "0640x480", "639x480", "640x479", "3841x2160", "1920x2161",
                     "99999x99999", "1920x1080;touch-x", "1920x1080 daphnis.skill=4", "-1x-1", "19e2x1080", ""):
            out = self.out()
            r = self.run_desk("--mode", mode, out=out)
            self.assertEqual(r.returncode, 2, mode)
            self.assertFalse(os.path.exists(out), mode)
        for mode in ("640x480", "1920x1080", "3840x2160", "1080x1920"):
            r = self.run_desk("--mode", mode)
            self.assertEqual(r.returncode, 0, (mode, r.stderr))
            a = self.argv()
            self.assertIn("daphnis.mode=%s daphnis.pool=max daphnis.rtc=1" % mode, a)

    def test_bad_accel_and_timeout(self):
        self.assertEqual(self.run_desk("--accel", "hvf").returncode, 2)
        self.assertEqual(self.run_desk("--timeout", "-3").returncode, 2)
        self.assertEqual(self.run_desk("--timeout", "1s").returncode, 2)

    def test_unavailable_kvm_does_not_fall_back(self):
        r = self.run_desk("--accel", "kvm", "--kvm-device", os.path.join(self.tmp, "no-kvm"))
        self.assertEqual(r.returncode, 2)
        self.assertIn("--accel tcg", r.stderr)
        self.assertFalse(os.path.exists(self.log), "qemu must not start")
        r = self.run_desk("--accel", "kvm", "--kvm-device", self.kvm)
        self.assertEqual(r.returncode, 0, r.stderr)
        a = self.argv()
        self.assertEqual(a[a.index("-accel") + 1], "kvm")

    # output directory

    def test_output_inside_checkout_is_refused(self):
        for out in (os.path.join(ROOT, "desk-test-output"), os.path.join(ROOT, "tools", "x")):
            r = self.run_desk(out=out)
            self.assertEqual(r.returncode, 2)
            self.assertIn("inside this checkout", r.stderr)
            self.assertFalse(os.path.exists(out))

    def test_output_through_symlink_into_checkout_is_refused(self):
        link = os.path.join(self.tmp, "to-checkout")
        os.symlink(ROOT, link)
        out = os.path.join(link, "desk-test-output")
        r = self.run_desk(out=out)
        self.assertEqual(r.returncode, 2)
        self.assertIn("inside this checkout", r.stderr)
        self.assertFalse(os.path.exists(os.path.join(ROOT, "desk-test-output")))

    def test_existing_output_and_symlink_output_are_refused(self):
        out = self.out()
        self.assertEqual(self.run_desk(out=out).returncode, 0)
        before = read(os.path.join(out, "receipt.json"))
        r = self.run_desk(out=out)
        self.assertEqual(r.returncode, 2)
        self.assertIn("exists", r.stderr)
        self.assertEqual(read(os.path.join(out, "receipt.json")), before, "a receipt is never overwritten")
        link = self.out()
        os.symlink(os.path.join(self.tmp, "nowhere"), link)
        self.assertEqual(self.run_desk(out=link).returncode, 2)
        elink = self.out()
        os.mkdir(os.path.join(self.tmp, "elsewhere"))
        os.symlink(os.path.join(self.tmp, "elsewhere"), elink)
        self.assertEqual(self.run_desk(out=elink).returncode, 2)
        self.assertEqual(os.listdir(os.path.join(self.tmp, "elsewhere")), [])

    def test_output_parent_must_exist(self):
        r = self.run_desk(out=os.path.join(self.tmp, "missing-parent", "run"))
        self.assertEqual(r.returncode, 2)

    def test_input_collisions(self):
        for a, b, name in (("kernel", "volume", "k-v"), ("initrd", "volume", "i-v"), ("kernel", "initrd", "k-i")):
            files = {"kernel": self.kernel, "initrd": self.initrd, "volume": self.volume}
            link = os.path.join(self.inputs, "link-" + name)
            os.symlink(files[b], link)
            files[a] = link
            r = self.run_desk("RAW", "--kernel", files["kernel"], "--initrd", files["initrd"],
                              "--volume", files["volume"], "--out", self.out(), "--accel", "tcg", "--headless")
            self.assertEqual(r.returncode, 2, name)
            self.assertIn("three different files", r.stderr)
        hard = os.path.join(self.inputs, "hard.img")
        os.link(self.volume, hard)
        r = self.run_desk("RAW", "--kernel", self.kernel, "--initrd", hard, "--volume", self.volume,
                          "--out", self.out(), "--accel", "tcg", "--headless")
        self.assertEqual(r.returncode, 2)

    # command construction

    def test_shell_sensitive_and_spaced_paths_survive_as_single_arguments(self):
        marker = os.path.join(self.tmp, "pwned")
        odd = os.path.join(self.tmp, "a b;touch pwned;$(touch pwned)`touch pwned`'\"x,y,,z")
        os.mkdir(odd)
        kernel = self.make("k e;rnel.elf", b"k", odd)
        initrd = self.make("in$HOME,itrd.cpio", b"i", odd)
        volume = self.make("vol,ume=1,if=ide.img", b"v" * 10, odd)
        out = os.path.join(odd, "run out;1")
        r = self.run_desk("RAW", "--kernel", kernel, "--initrd", initrd, "--volume", volume, "--out", out,
                          "--accel", "tcg", "--headless", cwd=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.exists(marker))
        a = self.argv()
        self.assertEqual(a[a.index("-kernel") + 1], kernel)
        self.assertEqual(a[a.index("-initrd") + 1], initrd)
        drive = a[a.index("-drive") + 1]
        self.assertEqual(drive, "file=%s,if=virtio,format=raw,cache=writeback" % volume.replace(",", ",,"))
        self.assertEqual(a.count("-drive"), 1)
        rec = self.receipt(out)
        self.assertEqual(rec["inputs"]["volume"]["resolved"], volume)
        self.assertEqual(rec["qemu"]["argv"], a)

    def test_fixed_command_shape(self):
        r = self.run_desk()
        self.assertEqual(r.returncode, 0, r.stderr)
        a = self.argv()
        for pair in (("-m", "4096"), ("-cpu", "max"), ("-nic", "none"), ("-monitor", "none"), ("-serial", "stdio")):
            self.assertEqual(a[a.index(pair[0]) + 1], pair[1])
        self.assertIn("-no-reboot", a)
        self.assertIn("isa-debug-exit,iobase=0xf4,iosize=0x04", a)
        self.assertNotIn("-audiodev", a)
        self.assertNotIn("-nographic", a)
        self.assertIn("cache=writeback", a[a.index("-drive") + 1])
        self.assertNotIn("cache=unsafe", a[a.index("-drive") + 1])

    def test_inherited_runner_controls_are_cleared(self):
        env = self.env(QEMU_EXTRA="-bogus-flag", NET="user", NET_FWD="tcp::2222-:22", SOUND="pa", PLAY="1",
                       MONITOR="/tmp/x", DISK="/tmp/other.img", INITRD="/tmp/other.cpio", MODE="1x1", POOL="min",
                       RTC="0", APPEND="daphnis.skill=9", CPU="qemu64", KVM="1", MEM="1", QEMU_TIMEOUT="1",
                       STDIN_FILE="/etc/passwd")
        r = self.run_desk(env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        a = self.argv()
        joined = " ".join(a)
        for bad in ("-bogus-flag", "hostfwd", "other.img", "other.cpio", "skill=9", "qemu64", "pulse", "-audiodev"):
            self.assertNotIn(bad, joined)
        self.assertEqual(a[a.index("-nic") + 1], "none")
        self.assertEqual(a[a.index("-m") + 1], "4096")
        self.assertEqual(read(self.log + ".env"), "", "no runner control reaches qemu")

    def test_dry_run_starts_nothing_and_leaves_the_volume_alone(self):
        before = sha(self.volume)
        mtime = os.stat(self.volume).st_mtime_ns
        out = self.out()
        r = self.run_desk("--dry-run", out=out)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("nothing started", r.stdout)
        self.assertIn("command:", r.stdout)
        self.assertIn("cache=writeback", r.stdout)
        self.assertFalse(os.path.exists(self.log), "qemu must not start")
        self.assertFalse(os.path.exists(out), "a dry run writes no run directory")
        self.assertEqual(sha(self.volume), before)
        self.assertEqual(os.stat(self.volume).st_mtime_ns, mtime)
        r = self.run_desk("--dry-run", "--mode", "12", out=self.out())
        self.assertEqual(r.returncode, 2, "a dry run reports the same refusals")

    # runs and receipts

    def test_guest_shutdown_status_33_is_a_normal_end_with_a_receipt(self):
        out = self.out()
        vol_before = sha(self.volume)
        r = self.run_desk(out=out)
        self.assertEqual(r.returncode, 0, r.stderr)
        rec = self.receipt(out)
        self.assertEqual(rec["state"], "finished")
        self.assertEqual(rec["result"], "guest-shutdown")
        self.assertEqual(rec["qemu_status"], 33)
        self.assertEqual(rec["inputs"]["kernel"]["sha256"], sha(self.kernel))
        self.assertEqual(rec["inputs"]["initrd"]["sha256"], sha(self.initrd))
        self.assertEqual(rec["inputs"]["volume"]["sha256"], vol_before)
        self.assertEqual(rec["volume_sha256_after"], vol_before)
        self.assertEqual(rec["settings"]["memory_mib"], 4096)
        self.assertEqual(rec["settings"]["pool"], "max")
        self.assertEqual(rec["settings"]["volume_cache"], "writeback")
        self.assertTrue(rec["started_utc"] and rec["ended_utc"])
        self.assertIn("source_head", rec["launcher"])
        self.assertEqual(rec["serial_log_sha256"], sha(os.path.join(out, "serial.log")))
        self.assertEqual(read(os.path.join(out, "serial.log")), "fake serial line\n")
        self.assertEqual(rec["command"][0], rec["qemu"]["path"])

    def test_failed_launch_and_abnormal_exit_keep_receipt_and_diagnostic(self):
        for status, result in (("1", "abnormal-exit"), ("127", "launch-failed"), ("0", "qemu-exited-without-guest-shutdown"),
                               ("3", "abnormal-exit")):
            out = self.out()
            r = self.run_desk(out=out, env=self.env(FAKE_QEMU_STATUS=status))
            self.assertEqual(r.returncode, 1, status)
            rec = self.receipt(out)
            self.assertEqual(rec["qemu_status"], int(status))
            self.assertEqual(rec["result"], result)
            self.assertIn("fake diagnostic", r.stderr)
            self.assertEqual(read(os.path.join(out, "qemu.err")), "fake diagnostic\n")

    def test_timeout_stops_qemu_and_returns_nonzero(self):
        out = self.out()
        r = self.run_desk("--timeout", "1", out=out, env=self.env(FAKE_QEMU_SLEEP="30"))
        self.assertEqual(r.returncode, 124, r.stderr)
        rec = self.receipt(out)
        self.assertEqual(rec["result"], "timeout")
        self.assertEqual(rec["settings"]["timeout_seconds"], 1)
        self.assertEqual(rec["command"][0], "timeout")

    def test_no_timeout_wrapper_by_default(self):
        out = self.out()
        self.assertEqual(self.run_desk(out=out).returncode, 0)
        self.assertNotEqual(self.receipt(out)["command"][0], "timeout")

    def test_receipt_exists_before_qemu_ends(self):
        slow = os.path.join(self.bin, "qemu-slow")
        with open(slow, "w") as f:
            f.write('#!/bin/sh\n[ "$1" = --version ] && exit 0\ncp "$RECEIPT_COPY_FROM"/receipt.json "$RECEIPT_COPY_TO"\nexit 33\n')
        os.chmod(slow, 0o755)
        out = self.out()
        copy = os.path.join(self.tmp, "mid-run.json")
        r = self.run_desk("--qemu", slow, out=out, env=self.env(RECEIPT_COPY_FROM=out, RECEIPT_COPY_TO=copy))
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(copy) as f:
            mid = json.load(f)
        self.assertEqual(mid["state"], "started")
        self.assertIsNone(mid["qemu_status"])

    def test_repeated_runs_reuse_the_exact_volume_path(self):
        seen = []
        for _ in range(2):
            out = self.out()
            r = self.run_desk(out=out)
            self.assertEqual(r.returncode, 0, r.stderr)
            a = self.argv()
            seen.append(a[a.index("-drive") + 1])
            self.assertEqual(self.receipt(out)["inputs"]["volume"]["resolved"], self.volume)
        self.assertEqual(seen[0], seen[1])
        self.assertEqual(os.listdir(self.inputs).count("work.img"), 1)
        self.assertEqual(sorted(os.listdir(self.inputs)), ["initrd.cpio", "kernel32.elf", "work.img"])

    def test_monitor_is_absent_by_default(self):
        out = self.out()
        self.assertEqual(self.run_desk(out=out).returncode, 0)
        a = self.argv()
        self.assertEqual(a[a.index("-monitor") + 1], "none")
        self.assertEqual(a.count("-monitor"), 1)
        self.assertIsNone(self.receipt(out)["settings"]["monitor_socket"])

    def test_explicit_monitor_is_a_fresh_local_socket_in_the_run_directory(self):
        out = self.out()
        r = self.run_desk("--monitor", out=out)
        self.assertEqual(r.returncode, 0, r.stderr)
        a = self.argv()
        sock = os.path.join(out, "monitor.sock")
        self.assertEqual(a.count("-monitor"), 1)
        self.assertEqual(a[a.index("-monitor") + 1], "unix:%s,server=on,wait=off" % sock)
        rec = self.receipt(out)
        self.assertEqual(rec["settings"]["monitor_socket"], sock)
        self.assertEqual(rec["qemu"]["argv"], a)
        self.assertNotIn("none", a[a.index("-monitor") + 1])

    def test_monitor_socket_path_commas_are_doubled_and_long_paths_refused(self):
        odd = os.path.join(self.tmp, "m,o,n")
        os.mkdir(odd)
        out = os.path.join(odd, "run")
        self.assertEqual(self.run_desk("--monitor", out=out).returncode, 0)
        a = self.argv()
        self.assertEqual(a[a.index("-monitor") + 1],
                         "unix:%s,server=on,wait=off" % os.path.join(out, "monitor.sock").replace(",", ",,"))
        deep = self.tmp
        while len(deep) < 120:
            deep = os.path.join(deep, "d" * 30)
            os.mkdir(deep)
        out = os.path.join(deep, "run")
        r = self.run_desk("--monitor", out=out)
        self.assertEqual(r.returncode, 2)
        self.assertIn("too long", r.stderr)
        self.assertFalse(os.path.exists(out))
        self.assertEqual(self.run_desk(out=out).returncode, 0, "without --monitor a long path is fine")

    def test_monitor_ignores_inherited_runner_variable_and_dry_run_reports_it(self):
        r = self.run_desk("--monitor", "--dry-run", env=self.env(MONITOR="/tmp/other.sock"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("monitor.sock", r.stdout)
        self.assertNotIn("other.sock", r.stdout)
        self.assertFalse(os.path.exists(self.log))

    def test_script_never_formats_or_elevates(self):
        with open(DESK) as f:
            code = "".join(l for l in f if not l.lstrip().startswith("#"))
        for word in ("mke2fs", "mkfs", "mkdisk", "mkcintvol", "truncate", "qemu-img", "sudo", "chmod", "chown"):
            self.assertNotIn(word, code)

    def test_script_syntax_and_no_eval(self):
        r = subprocess.run(["bash", "-n", DESK], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(DESK) as f:
            code = [l for l in f if not l.lstrip().startswith("#")]
        self.assertFalse([l for l in code if l.split("#")[0].split() and l.split()[0] == "eval"])


if __name__ == "__main__":
    unittest.main()
