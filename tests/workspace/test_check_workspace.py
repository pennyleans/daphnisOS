"""Unit tests of tools/check-workspace.py: receipt parsing, the refusals of the runner and the child-handle stop. No
QEMU runs here. Run: python3 -B -m unittest discover -s tests/workspace -p 'test_*.py'"""
import importlib.util
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
spec = importlib.util.spec_from_file_location("check_workspace", os.path.join(ROOT, "tools", "check-workspace.py"))
cw = importlib.util.module_from_spec(spec)
sys.modules["check_workspace"] = cw
spec.loader.exec_module(cw)


def hexof(label):
    return cw.sha256_bytes(label.encode())


def good_hashes(boot, expected):
    """Digests a correct run prints for BOOTn, drawn from the same table the checker enforces."""
    base = {"exe1": hexof("exe"), "src": expected["source"], "bak": expected["source"]}
    out = {}
    spec = {1: cw.BOOT1, 2: cw.BOOT2, 3: cw.BOOT3}[boot]
    for label in spec["hashes"]:
        out[label] = None
    for lb, ll, rb, rl in cw.EQUAL:
        if lb == boot:
            out[ll] = expected[rl] if rb == "exp" else base[rl]
    for label in spec["hashes"]:
        if out[label] is None:
            out[label] = base.get(label, hexof(label))
    return out


def transcript(spec, hashes, drop=(), status=None, diag=("cib: emit-qbe: exit 1", "syntax error"), extra=(),
               normal_end=True, grant=0):
    status = status or {}
    lines = ["Daphnis P: the block device"]
    for p in spec["phases"][:1]:
        lines.append("ws-phase " + p)
    for s in spec["steps"]:
        if s in drop:
            continue
        lines.append("ws-step %s %d" % (s, status.get(s, 1 if s in cw.EXPECT_FAIL else 0)))
        if s == "cib-bad":
            lines += ["ws-diag-begin"] + list(diag) + ["ws-diag-end"]
    for h in spec["hashes"]:
        if h not in drop:
            lines.append("ws-hash %s %s file" % (h, hashes[h]))
    for p in spec["phases"][1:]:
        if "ph:" + p not in drop:
            lines.append("ws-phase " + p)
    for m in spec["markers"]:
        if m not in drop:
            lines.append("ws-marker " + m)
    lines += list(extra)
    if normal_end:
        lines += ["grant: %d" % grant, "daphnis: done"]
    return "\n".join(lines) + "\n"


class Receipts(unittest.TestCase):
    def setUp(self):
        self.exp = cw.expected_digests()

    def rec(self, boot, **kw):
        spec = {1: cw.BOOT1, 2: cw.BOOT2, 3: cw.BOOT3}[boot]
        return cw.parse_receipts(transcript(spec, good_hashes(boot, self.exp), normal_end=(boot != 2), **kw))

    def specs(self, boot):
        return {1: [cw.BOOT1], 2: [cw.BOOT2], 3: [cw.BOOT3]}[boot]

    def test_good_boots_pass(self):
        for boot in (1, 2, 3):
            self.assertEqual(cw.check_boot(None, self.rec(boot), self.specs(boot), boot != 2), [], boot)

    def test_parse_receipts(self):
        r = cw.parse_receipts("junk\r\nws-step a 0\r\nws-hash x %s file\r\nws-marker m\r\nws-phase 1 begin\r\n"
                              "ws-diag-begin\r\nboom\r\nws-diag-end\r\ngrant: 0\r\ndaphnis: done\r\n" % ("a" * 64))
        self.assertEqual(r["steps"], {"a": 0})
        self.assertEqual(r["hashes"], {"x": "a" * 64})
        self.assertEqual((r["markers"], r["phases"], r["diag"], r["grant"], r["done"]),
                         (["m"], ["1 begin"], ["boom"], 0, True))

    def test_malformed_and_duplicate_lines_fail(self):
        r = cw.parse_receipts("ws-hash x nothex file\nws-step a 0\nws-step a 0\n")
        self.assertTrue(r["bad"])
        self.assertEqual(r["dups"], ["step a"])
        self.assertTrue(cw.check_boot(None, r, [{"phases": (), "steps": ("a",), "hashes": (), "markers": ()}], False))

    def test_absent_phase_markers_fail(self):
        for boot in (1, 2, 3):
            spec = self.specs(boot)[0]
            for p in spec["phases"]:
                key = p if p == spec["phases"][0] else "ph:" + p
                text = transcript(spec, good_hashes(boot, self.exp), normal_end=(boot != 2))
                text = text.replace("ws-phase %s\n" % p, "")
                fails = cw.check_boot(None, cw.parse_receipts(text), self.specs(boot), boot != 2)
                self.assertIn("missing phase marker ws-phase %s" % p, fails)

    def test_missing_final_marker_fails(self):
        r = self.rec(2, drop=("final-synced",))
        self.assertIn("missing marker final-synced", cw.check_boot(None, r, self.specs(2), False))

    def test_unsuccessful_native_command_fails(self):
        for boot in (1, 2, 3):
            for s in self.specs(boot)[0]["steps"]:
                if s in cw.EXPECT_FAIL:
                    continue
                r = self.rec(boot, status={s: 1})
                fails = cw.check_boot(None, r, self.specs(boot), boot != 2)
                self.assertIn("native command %s returned 1" % s, fails, s)

    def test_expected_failure_must_fail(self):
        r = self.rec(2, status={"cib-bad": 0})
        self.assertIn("step cib-bad must fail and returned 0", cw.check_boot(None, r, self.specs(2), False))

    def test_failed_build_needs_a_diagnostic(self):
        r = self.rec(2, diag=("", "  "))
        self.assertIn("the failing build kept no compiler diagnostic", cw.check_boot(None, r, self.specs(2), False))

    def test_unexpected_step_fails(self):
        r = self.rec(1, extra=("ws-step surprise 0",))
        self.assertIn("unexpected step surprise", cw.check_boot(None, r, self.specs(1), True))

    def test_missing_step_and_hash_members_fail(self):
        for boot in (1, 2, 3):
            spec = self.specs(boot)[0]
            for name in list(spec["steps"]) + list(spec["hashes"]):
                r = self.rec(boot, drop=(name,))
                fails = cw.check_boot(None, r, self.specs(boot), boot != 2)
                self.assertTrue(any(name in f for f in fails), name)

    def test_normal_end_needs_grant_zero_and_done(self):
        spec = cw.BOOT1
        text = transcript(spec, good_hashes(1, self.exp), grant=2)
        self.assertIn("guest script did not end with `grant: 0`", cw.check_boot(None, cw.parse_receipts(text),
                                                                               [spec], True))
        text = transcript(spec, good_hashes(1, self.exp), normal_end=False)
        fails = cw.check_boot(None, cw.parse_receipts(text), [spec], True)
        self.assertIn("kernel did not print `daphnis: done`", fails)

    def test_unexpected_guest_exit_fails(self):
        fails = cw.check_boot("exited before the marker (status 33)", self.rec(2), self.specs(2), False)
        self.assertEqual(fails, ["guest exit: exited before the marker (status 33)"])


class Equal(unittest.TestCase):
    def setUp(self):
        self.exp = cw.expected_digests()
        self.rec = {n: {"hashes": good_hashes(n, self.exp)} for n in (1, 2, 3)}

    def test_all_equal_passes(self):
        self.assertEqual(cw.check_equal(self.rec, self.exp), [])

    def test_wrong_hash_fails(self):
        for n, label in ((1, "exe1"), (2, "exe2"), (2, "v-bak"), (3, "f-exe1"), (3, "f-marker"), (1, "src"),
                         (2, "run-2-out"), (3, "f-run-2-out")):
            rec = {k: {"hashes": dict(v["hashes"])} for k, v in self.rec.items()}
            rec[n]["hashes"][label] = hexof("wrong")
            self.assertTrue(cw.check_equal(rec, self.exp), (n, label))

    def test_comparing_only_the_subset_produced_fails(self):
        for n in (1, 2, 3):
            for label in list(self.rec[n]["hashes"]):
                rec = {k: {"hashes": dict(v["hashes"])} for k, v in self.rec.items()}
                del rec[n]["hashes"][label]
                fails = cw.check_equal(rec, self.exp)
                in_table = any((lb == n and ll == label) or (rb == n and rl == label) for lb, ll, rb, rl in cw.EQUAL)
                self.assertEqual(bool(fails), in_table, (n, label))

    def test_missing_boot_fails(self):
        for n in (1, 2, 3):
            rec = {k: v for k, v in self.rec.items() if k != n}
            self.assertTrue(cw.check_equal(rec, self.exp), n)

    def test_every_required_hash_is_in_the_table(self):
        tabled = {(lb, ll) for lb, ll, _, _ in cw.EQUAL} | {(rb, rl) for _, _, rb, rl in cw.EQUAL}
        for n, spec in ((1, cw.BOOT1), (2, cw.BOOT2), (3, cw.BOOT3)):
            for h in spec["hashes"]:
                self.assertIn((n, h), tabled, h)


class Refusals(unittest.TestCase):
    def test_existing_dir_refused(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(cw.Refusal):
                cw.validate_out(d, checkout=ROOT)

    def test_existing_file_and_dangling_symlink_refused(self):
        with tempfile.TemporaryDirectory() as d:
            f = os.path.join(d, "f")
            open(f, "w").close()
            os.symlink(os.path.join(d, "nowhere"), os.path.join(d, "l"))
            for p in (f, os.path.join(d, "l")):
                with self.assertRaises(cw.Refusal):
                    cw.validate_out(p, checkout=ROOT)

    def test_fresh_path_outside_accepted(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "fresh")
            self.assertEqual(cw.validate_out(p, checkout=ROOT), p)

    def test_relative_refused(self):
        with self.assertRaises(cw.Refusal):
            cw.validate_out("fresh-results", checkout=ROOT)
        with self.assertRaises(cw.Refusal):
            cw.validate_out("", checkout=ROOT)

    def test_inside_checkout_refused(self):
        with self.assertRaises(cw.Refusal):
            cw.validate_out(os.path.join(ROOT, "results"), checkout=ROOT)

    def test_path_escape_refused(self):
        with tempfile.TemporaryDirectory() as d:
            sneaky = os.path.join(d, "..", os.path.basename(ROOT), "results")
            with self.assertRaises(cw.Refusal):
                cw.validate_out(sneaky, checkout=ROOT)

    def test_symlinked_parent_into_checkout_refused(self):
        with tempfile.TemporaryDirectory() as d:
            link = os.path.join(d, "link")
            os.symlink(ROOT, link)
            with self.assertRaises(cw.Refusal):
                cw.validate_out(os.path.join(link, "results"), checkout=ROOT)

    def test_missing_parent_refused(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(cw.Refusal):
                cw.validate_out(os.path.join(d, "a", "b"), checkout=ROOT)

    def test_explicit_toolchain_required(self):
        with self.assertRaises(cw.Refusal):
            cw.check_environment({"PATH": os.environ["PATH"]})
        with self.assertRaises(cw.Refusal):
            cw.check_environment({"CINT_TOOLCHAIN": "", "PATH": os.environ["PATH"]})

    def test_missing_toolchain_file_is_unrun(self):
        with self.assertRaises(cw.Unrun):
            cw.check_environment({"CINT_TOOLCHAIN": "/nonexistent/cint.toolchain", "PATH": os.environ["PATH"]})

    def test_no_option_takes_an_existing_disk(self):
        with self.assertRaises(SystemExit):
            cw.main(["--out", "/tmp/x", "--disk", "/dev/sda"])
        with self.assertRaises(SystemExit):
            cw.main([])

    def test_main_refuses_existing_out(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(cw.main(["--out", d]), 2)


class QemuArgv(unittest.TestCase):
    def test_no_unsafe_cache_and_flush_respecting(self):
        argv = cw.qemu_argv("k", "i", "/v/vol.img")
        self.assertFalse(any("unsafe" in a for a in argv))
        drive = argv[argv.index("-drive") + 1]
        self.assertIn("cache=writeback", drive)
        self.assertIn("-accel", argv)
        self.assertEqual(argv[argv.index("-accel") + 1], "kvm")
        self.assertIn("isa-debug-exit,iobase=0xf4,iosize=0x04", argv)

    def test_one_drive_only(self):
        self.assertEqual(cw.qemu_argv("k", "i", "v").count("-drive"), 1)


class StopHelper(unittest.TestCase):
    def sleeper(self):
        return [sys.executable, "-c", "import time; time.sleep(60)"]

    def test_stops_only_its_own_child(self):
        other = subprocess.Popen(self.sleeper())
        try:
            with tempfile.TemporaryDirectory() as d:
                open(os.path.join(d, "in"), "wb").close()
                vm = cw.Vm(self.sleeper(), os.path.join(d, "in"), os.path.join(d, "out"), os.path.join(d, "err"))
                self.assertIsNone(vm.proc.poll())
                rc = vm.stop()
                self.assertEqual(rc, -signal.SIGKILL)
                self.assertTrue(vm.stopped_by_us)
                self.assertIsNone(other.poll(), "an unrelated process was stopped")
        finally:
            other.kill()
            other.wait()

    def test_no_name_killing_or_power_calls_in_source(self):
        import ast
        with open(os.path.join(ROOT, "tools", "check-workspace.py")) as f:
            tree = ast.parse(f.read())
        docs = {id(n.value) for n in ast.walk(tree) if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)}
        strings = [n.value for n in ast.walk(tree)
                   if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs]
        calls = {n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", "")
                 for n in ast.walk(tree) if isinstance(n, ast.Call)}
        for bad in ("kill", "killpg", "system", "popen"):
            self.assertNotIn(bad, calls, bad)
        for bad in ("pkill", "killall", "shutdown", "reboot", "poweroff", "systemctl", "taskkill", "kill"):
            self.assertFalse([s for s in strings if s == bad or s.startswith(bad + " ")], bad)

    def test_stop_uses_only_the_child_handle(self):
        calls = []
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "in"), "wb").close()
            vm = cw.Vm(self.sleeper(), os.path.join(d, "in"), os.path.join(d, "out"), os.path.join(d, "err"))
            real = vm.proc.send_signal
            vm.proc.send_signal = lambda sig: (calls.append((vm.proc.pid, sig)), real(sig))
            old_run, old_system = subprocess.run, os.system
            subprocess.run = lambda *a, **k: self.fail("a command was run to stop the VM")
            os.system = lambda *a, **k: self.fail("os.system was used to stop the VM")
            try:
                vm.stop()
            finally:
                subprocess.run, os.system = old_run, old_system
        self.assertEqual(calls, [(vm.proc.pid, signal.SIGKILL)])

    def test_marker_wait_reports_early_exit(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "in"), "wb").close()
            vm = cw.Vm([sys.executable, "-c", "print('ws-step a 0')"], os.path.join(d, "in"),
                       os.path.join(d, "out"), os.path.join(d, "err"))
            self.assertFalse(vm.wait_marker("final-synced", time.time() + 10))
            self.assertIsNotNone(vm.proc.poll())
            vm.close()

    def test_marker_wait_sees_marker_while_running(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "in"), "wb").close()
            code = "import sys,time; print('ws-marker final-synced'); sys.stdout.flush(); time.sleep(60)"
            vm = cw.Vm([sys.executable, "-c", code], os.path.join(d, "in"), os.path.join(d, "out"),
                       os.path.join(d, "err"))
            try:
                self.assertTrue(vm.wait_marker("final-synced", time.time() + 10))
                self.assertIsNone(vm.proc.poll())
            finally:
                vm.stop()

    def test_wait_end_deadline_stops_the_child(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "in"), "wb").close()
            vm = cw.Vm(self.sleeper(), os.path.join(d, "in"), os.path.join(d, "out"), os.path.join(d, "err"))
            self.assertIsNone(vm.wait_end(time.time() + 0.2))
            self.assertIsNotNone(vm.proc.poll())


class Fixtures(unittest.TestCase):
    def read(self, name):
        with open(os.path.join(HERE, name)) as f:
            return f.read()

    def script_names(self, name, word):
        out = []
        for line in self.read(name).split("\n"):
            if line.startswith("#"):
                continue
            out += re.findall(r"echo %s (\S+)" % word, line)
        return out

    def test_scripts_print_exactly_the_enumerated_receipts(self):
        for n, spec in ((1, cw.BOOT1), (2, cw.BOOT2), (3, cw.BOOT3)):
            name = "phase%d.sh" % n
            self.assertEqual(sorted(self.script_names(name, "ws-step")), sorted(spec["steps"]), name)
            self.assertEqual(sorted(self.script_names(name, "ws-hash")), sorted(spec["hashes"]), name)
            self.assertEqual(sorted(self.script_names(name, "ws-marker")), sorted(spec["markers"]), name)

    def test_script_phase_markers(self):
        for n, spec in ((1, cw.BOOT1), (2, cw.BOOT2), (3, cw.BOOT3)):
            got = [l[len("echo ws-phase "):] for l in self.read("phase%d.sh" % n).split("\n")
                   if l.startswith("echo ws-phase ")]
            self.assertEqual(got, list(spec["phases"]))

    def test_source_in_script_is_the_fixture_program(self):
        body = cw.heredoc_body(self.read("phase1.sh"))
        with open(os.path.join(HERE, "hello.ci"), "rb") as f:
            self.assertEqual(body, f.read())

    def test_expected_output_matches_the_program(self):
        with open(os.path.join(HERE, "expected.txt"), "rb") as f:
            self.assertEqual(f.read(), b"workspace result: 42 ok\n")

    def test_only_phase_two_writes_the_marker_and_waits(self):
        self.assertIn("sleep 3600", self.read("phase2.sh"))
        self.assertNotIn("sleep", self.read("phase1.sh") + self.read("phase3.sh"))
        self.assertIn("test $s = 0 && echo ws-marker final-synced", self.read("phase2.sh"))

    def test_marker_text_digest(self):
        self.assertIn("printf 'workspace recovery final marker\\n' > final.marker", self.read("phase2.sh"))

    def test_guest_input_shape(self):
        data = cw.guest_input("# comment\necho a\n\necho b\n")
        self.assertEqual(data, b"./grant disk ./sh <<'EOF'\necho a\necho b\nEOF\necho grant: $?\nexit 0\n\x04")

    def test_source_keeps_the_space_in_the_project_name(self):
        self.assertIn("/home/work/proj one", self.read("phase1.sh"))
        self.assertEqual(cw.PROJECT_DIR, "/home/work/proj one")

    def test_initrd_names_cish_as_sh_and_has_no_busybox(self):
        args = cw.initrd_args("out.cpio", "/fx", "/o/ubin")
        self.assertIn("sh=/o/ubin/cish", args)
        self.assertIn("bin/sh=/o/ubin/cish", args)
        self.assertIn("grant=/o/ubin/grant", args)
        self.assertFalse(any("busybox" in a or "user/bin" in a for a in args))
        for need in ("cat", "cp", "cmp", "sha256sum", "mkdir", "echo", "printf", "sleep", "sync", "test"):
            self.assertIn("bin/%s=/o/ubin/%s" % (need, need), args)


if __name__ == "__main__":
    unittest.main()
