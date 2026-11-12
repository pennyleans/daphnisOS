"""HW-1 builders and input lifecycle, using fake children, never host disks or QEMU."""
import os
import pathlib
import signal
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


class Tools(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="hw-tools-", dir=os.environ.get("TMPDIR"))
        self.addCleanup(self.temp.cleanup)
        self.b = pathlib.Path(self.temp.name)
        self.input = self.b / "input"
        self.input.write_bytes(b"input bytes\n")

    def cleanup_child(self, p):
        if p.poll() is None:
            p.terminate()
            try:
                p.wait(timeout=8)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()
        if p.stdout is not None:
            p.stdout.close()
        if p.stderr is not None:
            p.stderr.close()

    def ready_pid(self, path):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                pid = int(path.read_text())
                if pid > 0:
                    return pid
            except (OSError, ValueError):
                pass
            time.sleep(0.02)
        self.fail("child readiness PID was not published")

    def fake_tools(self):
        tools = self.b / "bin"
        tools.mkdir()
        for name in ("grub-mkstandalone", "mformat", "mmd", "mcopy"):
            p = tools / name
            p.write_text("#!/bin/sh\necho build-refusal >&2\nexit 7\n")
            p.chmod(0o700)
        return {**os.environ, "PATH": str(tools) + os.pathsep + os.environ["PATH"]}

    def test_esp_alias_refusal(self):
        env = self.fake_tools()
        image = self.b / "boot.esp"
        log = self.b / "boot.esp.log"
        # Direct path, then hardlink and symlink aliases at either destination.
        for dest in (image, log):
            os.link(self.input, dest)
            p = subprocess.run(["bash", str(ROOT / "tools/build-esp.sh"), str(self.input), str(image)],
                               env=env, capture_output=True)
            self.assertNotEqual(p.returncode, 0)
            self.assertIn(b"aliases an input", p.stderr)
            dest.unlink()
            dest.symlink_to(self.input)
            p = subprocess.run(["bash", str(ROOT / "tools/build-esp.sh"), str(self.input), str(image)],
                               env=env, capture_output=True)
            self.assertNotEqual(p.returncode, 0)
            self.assertIn(b"aliases an input", p.stderr)
            dest.unlink()
        p = subprocess.run(["bash", str(ROOT / "tools/build-esp.sh"), str(self.input), str(self.input)],
                           env=env, capture_output=True)
        self.assertNotEqual(p.returncode, 0)
        # A kernel named exactly like the output's log must not be truncated.
        log.write_bytes(b"kernel bytes")
        p = subprocess.run(["bash", str(ROOT / "tools/build-esp.sh"), str(log), str(image)], env=env, capture_output=True)
        self.assertNotEqual(p.returncode, 0)
        self.assertEqual(log.read_bytes(), b"kernel bytes")
        self.assertEqual(self.input.read_bytes(), b"input bytes\n")

    def test_esp_failure_preserves_image(self):
        env = self.fake_tools()
        image = self.b / "boot.esp"
        image.write_bytes(b"previous complete image")
        p = subprocess.run(["bash", str(ROOT / "tools/build-esp.sh"), str(self.input), str(image)],
                           env=env, capture_output=True)
        self.assertNotEqual(p.returncode, 0)
        self.assertEqual(image.read_bytes(), b"previous complete image")
        self.assertIn(b"build-refusal", pathlib.Path(str(image) + ".log").read_bytes())
        self.assertFalse(list(self.b.glob(".esp-*")))

    def test_esp_symlink_sizes(self):
        # Stub only external packaging tools; real stat/truncate must size the
        # published image for the bytes mcopy reads, not a symlink's metadata.
        tools = self.b / "bin"
        tools.mkdir()
        grub = tools / "grub-mkstandalone"
        grub.write_text("#!/bin/sh\nwhile [ $# -gt 0 ]; do\n"
                        " if [ \"$1\" = -o ]; then shift; printf EFI > \"$1\"; exit 0; fi\n"
                        " shift\ndone\nexit 1\n")
        grub.chmod(0o700)
        for name in ("mformat", "mmd", "mcopy"):
            p = tools / name
            p.write_text("#!/bin/sh\nexit 0\n")
            p.chmod(0o700)
        large = self.b / "large"
        with large.open("wb") as f:
            f.truncate(80 * 1048576)
        link = self.b / "link"
        link.symlink_to(large)
        env = {**os.environ, "PATH": str(tools) + os.pathsep + os.environ["PATH"]}
        for kernel, module in ((link, self.input), (self.input, link)):
            with self.subTest(kernel=kernel, module=module):
                image = self.b / "boot.esp"
                p = subprocess.run(["bash", str(ROOT / "tools/build-esp.sh"), str(kernel), str(image), str(module)],
                                   env=env, capture_output=True)
                self.assertEqual(p.returncode, 0, p.stderr)
                self.assertGreaterEqual(image.stat().st_size, large.stat().st_size + 8388608)
        self.assertFalse(list(self.b.glob(".esp-*")))

    def feeder(self, code):
        transcript = self.b / "serial"
        transcript.write_bytes(b"")
        out = transcript.open("wb")
        self.addCleanup(out.close)
        p = subprocess.Popen([sys.executable, str(ROOT / "tools/serial-after.py"), "KERNEL\n",
                                 str(self.input), str(transcript), sys.executable, "-c", code],
                                stdout=out, stderr=subprocess.PIPE)
        self.addCleanup(self.cleanup_child, p)
        return p

    def test_feeder_success(self):
        p = self.feeder("import sys; print('KERNEL',flush=True); assert sys.stdin.buffer.read()==b'input bytes\\n'; sys.exit(33)")
        _, err = p.communicate(timeout=5)
        self.assertEqual(p.returncode, 33, err)
        self.assertEqual(err, b"")

    def test_feeder_missing_marker(self):
        p = self.feeder("pass")
        _, err = p.communicate(timeout=5)
        self.assertEqual(p.returncode, 1)
        self.assertIn(b"before the kernel marker", err)

    def test_feeder_closed_stdin(self):
        self.input.write_bytes(b"x" * 1048576)
        p = self.feeder("import os,time; os.close(0); print('KERNEL',flush=True); time.sleep(30)")
        _, err = p.communicate(timeout=5)
        self.assertEqual(p.returncode, 1)
        self.assertIn(b"serial-after:", err)

    def test_feeder_cancellation(self):
        self.input.write_bytes(b"x" * 1048576)
        pidfile = self.b / "child.pid"
        p = self.feeder(f"import os,signal,time,pathlib; signal.signal(signal.SIGTERM,signal.SIG_IGN); pathlib.Path({str(pidfile)!r}).write_text(str(os.getpid())); print('KERNEL',flush=True); time.sleep(30)")
        child = self.ready_pid(pidfile)
        p.terminate()
        _, err = p.communicate(timeout=8)
        self.assertEqual(p.returncode, 143, err)
        with self.assertRaises(ProcessLookupError):
            os.kill(child, 0)

    def test_supervisor_cancellation(self):
        pidfile = self.b / "group.pid"
        child_code = f"import os,signal,time,pathlib; signal.signal(signal.SIGTERM,signal.SIG_IGN); pathlib.Path({str(pidfile)!r}).write_text(str(os.getpid())); time.sleep(30)"
        code = f"import importlib.util; s=importlib.util.spec_from_file_location('jobs',{str(ROOT / 'tools/ovmf-jobs.py')!r}); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); raise SystemExit(m.run([[{sys.executable!r},'-c',{child_code!r}]]))"
        p = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.addCleanup(self.cleanup_child, p)
        child = self.ready_pid(pidfile)
        p.terminate()   # only the supervisor, not its child's process group
        _, err = p.communicate(timeout=9)
        self.assertEqual(p.returncode, 143, err)
        with self.assertRaises(ProcessLookupError):
            os.kill(child, 0)

    def test_ovmf_environment_isolation(self):
        tools = self.b / "bin"
        tools.mkdir()
        (self.b / "ovmf").mkdir()
        args = self.b / "argv.json"
        qemu = tools / "qemu-system-x86_64"
        qemu.write_text(f"#!{sys.executable}\nimport json,pathlib,sys\npathlib.Path({str(args)!r}).write_text(json.dumps(sys.argv[1:]))\nsys.stdout.buffer.write(b'hello from Daphnis\\n')\nsys.exit(33)\n")
        qemu.chmod(0o700)
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PATH": str(tools) + os.pathsep + os.environ["PATH"],
               "OVMF": str(self.input), "DISK": "/forbidden-device", "QEMU_EXTRA": "-device forbidden-device",
               "NET": "user", "PLAY": "1", "KVM": "1", "CPU": "host", "SOUND": "forbidden-sound",
               "MODE": "1920x1080", "POOL": "max", "APPEND": "forbidden-argument", "INITRD": "/forbidden-module"}
        p = subprocess.run(["bash", "tools/check-ovmf.sh", str(self.b), "--case", "gcc", "hello", "esp", "128"],
                           cwd=ROOT, env=env, capture_output=True, timeout=10)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        import json
        argv = json.loads(args.read_text())
        self.assertIn("tcg", argv)
        self.assertIn("none", argv)
        self.assertNotIn("kvm", argv)
        self.assertNotIn("-cpu", argv)
        self.assertFalse(any("forbidden" in a for a in argv))
        self.assertEqual(argv.count("-drive"), 1)
        self.assertIn("snapshot=on", argv[argv.index("-drive") + 1])

    def test_home_keys_only_remove_final_wait(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("home_keys", ROOT / "tools/check-home.py")
        home = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(home)
        k = home.editor.qemu_keys
        def old_typed(lines):
            return ",".join(",".join(k([line]) + [home.WAIT]) for line in lines)
        old = {
            1: old_typed([b"seq 1 170000 > big.txt\r", b"cp big.txt /big.txt\r"]) + "," + ",".join(k([b"$EDITOR big.txt\r"])),
            2: ",".join([home.LONG] + k([home.KEPT[:-1], b"\r"]) + [home.WAIT] + k([b"\x13"]) + [home.LONG] + k([b"\x11"]) + [home.LONG]) + "," +
               old_typed([b"pwd\r", b"sha256sum /big.txt big.txt\r", b"sync\r", b"exit\r"]),
            3: old_typed([b"pwd\r", b"wc -c big.txt\r", b"sha256sum big.txt\r", b"exit\r"])
        }
        self.assertEqual(home.keys(1), old[1])
        for n in (2, 3):
            self.assertEqual(home.keys(n) + "," + home.WAIT, old[n])
        with self.assertRaises(AssertionError):
            home.typed([b"pwd\r"], last_wait=False)

    def test_home_driver_failure_blocks_second_boot(self):
        tools = self.b / "tools"
        tools.mkdir()
        (tools / "check-home.py").write_text("print('a,ret')\n")
        (tools / "sendkeys.py").write_text("""import os,pathlib,sys
sock,transcript,mark=sys.argv[1:4]
t=pathlib.Path(transcript)
assert b'STALE' not in t.read_bytes()
assert not pathlib.Path(sock).exists()
assert mark=='hdesk: bar desktop 1 |Console| var |/home| grants |DISK 1|'
pathlib.Path(transcript+'.started').write_text('ready')
raise SystemExit(int(os.environ.get('FAKE_DRIVER_FAIL','0')))
""")
        qemu = tools / "run-qemu.sh"
        qemu.write_text(f"#!{sys.executable}\n" + """import pathlib,sys,time
t=pathlib.Path(sys.argv[2]);started=pathlib.Path(str(t)+'.started')
deadline=time.monotonic()+3
while not started.exists() and time.monotonic()<deadline:time.sleep(.01)
assert started.exists()
t.write_text('new guest transcript')
pathlib.Path(str(t)+'.err').write_text('')
print(33)
""")
        qemu.chmod(0o700)
        prefix = self.b / "home"
        for n in (1, 2):
            pathlib.Path(f"{prefix}.{n}.txt").write_bytes(b"STALE")
            pathlib.Path(f"{prefix}.{n}.txt.mon").write_bytes(b"STALE")
        cmd = ["bash", str(ROOT / "tools/home-boots.sh"), str(self.input), str(self.input), str(self.input), str(prefix)]
        env = {**os.environ, "FAKE_DRIVER_FAIL": "1", "PYTHONDONTWRITEBYTECODE": "1"}
        p = subprocess.run(cmd, cwd=self.b, env=env, capture_output=True, timeout=10)
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertTrue(pathlib.Path(str(prefix) + ".2.blocked").exists())
        self.assertFalse(pathlib.Path(str(prefix) + ".2.txt.rc").exists())
        self.assertEqual(pathlib.Path(str(prefix) + ".1.keys.rc").read_text().strip(), "1")
        env["FAKE_DRIVER_FAIL"] = "0"
        # Successful retry must clear the old blocked result and stale first-boot state.
        pathlib.Path(str(prefix) + ".1.txt").write_bytes(b"STALE")
        pathlib.Path(str(prefix) + ".1.txt.mon").write_bytes(b"STALE")
        pathlib.Path(str(prefix) + ".1.txt.started").unlink()
        p = subprocess.run(cmd, cwd=self.b, env=env, capture_output=True, timeout=10)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertFalse(pathlib.Path(str(prefix) + ".2.blocked").exists())
        for n in (1, 2):
            self.assertEqual(pathlib.Path(f"{prefix}.{n}.keys.rc").read_text().strip(), "0")
            self.assertEqual(pathlib.Path(f"{prefix}.{n}.txt.rc").read_text().strip(), "33")


if __name__ == "__main__":
    unittest.main()
