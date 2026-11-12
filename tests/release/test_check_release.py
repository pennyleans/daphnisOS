"""tools/check-release.py on made-up images: the recipe, apps, doom, names and rows checks and the ledger's four, hosted,
no QEMU; and tools/check-release-volume.py on small ext2 volumes (mke2fs, debugfs). Run: python3 tests/release/test_check_release.py"""
import importlib.util
import io
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

ROOT = pathlib.Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("check_release", ROOT / "tools/check-release.py")
cr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cr)

APPS = ('export const I64 N = 3;\nI64[3] runs = [1, 0, 3];\nBool[3] cmds = [false, false, false];\n'
        'parse("Index|/bin/finder|index files|File explorer|Home\\nConsole|/bin/cish|console shell|Shell|A shell\\n'
        'Web Browser||browser|Web browser|Not built\\n");\n')
LEDGER_HEAD = "# test\nid\tapproved\tartifact\tproof\tlicense\tstate\n"


class CheckRelease(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory(prefix="rel-", dir=os.environ.get("TMPDIR"))
        self.addCleanup(t.cleanup)
        self.d = pathlib.Path(t.name)
        (self.d / "src/user/ci/kit").mkdir(parents=True)
        (self.d / "src/user/ci/kit/apps.ci").write_text(APPS)
        (self.d / "src/user/ci/hdesk.ci").write_text('import user.ci.kit.apps;\nU8[9] c = b"/bin/cish";\n')
        (self.d / "elf").write_bytes(b"\x7fELF" + b"Welcome to Daphnis" + bytes(40))
        cr.fails = 0

    def image(self, *members):
        out = self.d / "initrd.cpio"
        args = [a if a.endswith("/") else "%s=%s" % (a, self.d / "elf") for a in members]
        subprocess.run([sys.executable, str(ROOT / "tools/mkcpio.py"), str(out)] + args, check=True)
        (self.d / "recipe.txt").write_text("echo x\npython3 tools/mkcpio.py %s %s\n" % (out, " ".join(args)))
        return out

    def run_static(self, initrd, recipe=None):
        if recipe:
            (self.d / "recipe.txt").write_text(recipe)
        f = io.StringIO()
        with redirect_stdout(f):
            cr.static(str(initrd), str(self.d / "recipe.txt"), str(self.d / "src"))
        return f.getvalue().splitlines()

    def test_the_image_of_its_recipe_with_every_app_passes(self):
        out = self.run_static(self.image("hdesk", "bin/", "bin/finder", "bin/cish"))
        self.assertEqual([x[:4] for x in out], ["PASS"] * 5, out)

    def test_a_member_the_recipe_lacks_fails(self):
        img = self.image("hdesk", "bin/", "bin/finder", "bin/cish")
        out = self.run_static(img, "python3 tools/mkcpio.py X hdesk=a bin/ bin/finder=b bin/cish=c\n"
                              .replace("bin/cish=c", "bin/cish=c bin/extra=d"))
        self.assertTrue(out[0].startswith("FAIL  recipe") and "bin/extra" in out[0], out)

    def test_an_app_not_in_the_image_and_a_named_path_fail(self):
        out = self.run_static(self.image("hdesk", "bin/", "bin/finder"))
        self.assertTrue(out[1].startswith("FAIL  apps") and "Console (/bin/cish)" in out[1], out)
        self.assertTrue(out[3].startswith("FAIL  names") and "/bin/cish (user/ci/hdesk.ci)" in out[3], out)

    def test_doom_fails(self):
        out = self.run_static(self.image("hdesk", "bin/", "bin/finder", "bin/cish", "e1m6.wad"))
        self.assertTrue(out[2].startswith("FAIL  doom") and "e1m6.wad" in out[2], out)

    def test_a_host_row_module_reached_only_indirectly_fails(self):
        (self.d / "src/user/ci/build.sh").write_text(
            'case " $imports " in *" user/ci/fdctl.ci "*) rows="$rows -DCI_ROWS_FD" ;; esac\n')
        (self.d / "src/user/ci/kit/setfile.ci").write_text("import user.ci.fdctl;\n")
        (self.d / "src/user/ci/fdctl.ci").write_text("export extern I64 fd_stat(I64 fd);\n")
        (self.d / "src/user/ci/cview.ci").write_text("import user.ci.kit.setfile;\n")
        out = self.run_static(self.image("hdesk", "bin/", "bin/finder", "bin/cish", "bin/cview"))
        self.assertTrue(out[4].startswith("FAIL  rows") and "cview reaches user/ci/fdctl.ci" in out[4], out)
        (self.d / "src/user/ci/cview.ci").write_text("import user.ci.kit.setfile;\nimport user.ci.fdctl;\n")
        out = self.run_static(self.image("hdesk", "bin/", "bin/finder", "bin/cish", "bin/cview"))
        self.assertTrue(out[4].startswith("PASS  rows"), out)

    def ledger(self, rows, gate="PASS  Index (/bin/finder) opens: its window bound\n"
                                "PASS  Console (/bin/cish) opens: its terminal 1 up\n", transcript=True):
        initrd = self.image("hdesk", "bin/", "bin/finder", "bin/cish")
        (self.d / "LEDGER.tsv").write_text(LEDGER_HEAD + "".join("\t".join(r) + "\n" for r in rows))
        (self.d / "esp.txt").write_text("::/EFI/BOOT/BOOTX64.EFI\n")
        if transcript:
            (self.d / "desk.txt").write_text("daphnis: net dhcp 10.0.2.15/24 gateway 10.0.2.2 dns 10.0.2.3\n")
        (self.d / "gate.log").write_text(gate)
        (self.d / "DECISIONS.md").write_text("| DN-5 | icons | A | 2026-11-10 | x |\n")
        f = io.StringIO()
        with redirect_stdout(f):
            cr.ledger(str(self.d / "LEDGER.tsv"), str(initrd), str(self.d / "esp.txt"), str(self.d / "none.img"),
                      str(self.d / "src/user/ci/kit/apps.ci"), str(self.d / "desk.txt"), str(self.d / "gate.log"),
                      str(self.d / "DECISIONS.md"))
        return f.getvalue().splitlines()

    GOOD = [("APP-Index", "DN-5 l", "app Index; member bin/finder", "p", "Apache-2.0", "IN"),
            ("APP-Console", "x", "app Console; word hdesk Welcome to Daphnis", "p", "Apache-2.0", "IN"),
            ("APP-Web", "x", "app Web Browser; esp EFI/BOOT/BOOTX64.EFI; line daphnis: net dhcp ", "p", "x", "IN"),
            ("SAVE-1", "x", "nomember bin/save", "-", "x", "DEFERRED (l 2026-11-11 21:15Z: after 0.1.0)")]

    def test_a_ledger_whose_rows_hold_passes(self):
        out = self.ledger(self.GOOD)
        self.assertEqual([x[:4] for x in out], ["PASS"] * 4, out)

    def test_an_app_that_never_opened_fails_its_in_row(self):
        out = self.ledger(self.GOOD, gate="")
        self.assertTrue(out[2].startswith("FAIL  ledger in") and "APP-Index: app Index" in out[2], out)

    def test_open_rows_uncovered_rulings_and_bare_deferrals_fail(self):
        rows = self.GOOD[1:] + [("P1-C", "x", "member bin/shot", "p", "x", "MISSING (not built)"),
                                ("X", "x", "-", "-", "x", "DEFERRED (later)")]
        out = self.ledger(rows)
        self.assertTrue(out[0].startswith("FAIL  ledger form") and "X: DEFERRED without" in out[0], out)
        self.assertTrue(out[1].startswith("FAIL  ledger cover") and "app Index" in out[1] and "DN-5" in out[1], out)
        self.assertTrue(out[3].startswith("FAIL  ledger open") and "P1-C MISSING" in out[3], out)


    def test_a_module_row_holds_only_when_a_shipped_program_imports_the_module(self):
        (self.d / "src/user/ci/kit/shotsel.ci").write_text("export I64 cross = 1;\n")
        (self.d / "src/user/ci/kit/bar.ci").write_text("import user.ci.kit.shotsel;\n")
        row = [("RS-SHOT-cross", "x", "module hdesk user/ci/kit/shotsel.ci", "p", "x", "IN")]
        out = self.ledger(self.GOOD + row)
        self.assertTrue(out[2].startswith("FAIL  ledger in") and
                        "RS-SHOT-cross: module hdesk user/ci/kit/shotsel.ci" in out[2], out)
        (self.d / "src/user/ci/hdesk.ci").write_text('import user.ci.kit.apps;\nimport user.ci.kit.bar;\n'
                                                     'U8[9] c = b"/bin/cish";\n')
        cr.fails = 0
        out = self.ledger(self.GOOD + row)
        self.assertEqual([x[:4] for x in out], ["PASS"] * 4, out)

    def test_a_module_row_fails_on_its_own_program_or_a_member_not_shipped(self):
        for item in ("module hdesk user/ci/hdesk.ci", "module bin/shot user/ci/kit/apps.ci"):
            cr.fails = 0
            out = self.ledger(self.GOOD + [("X", "x", item, "p", "x", "IN")])
            self.assertTrue(out[2].startswith("FAIL  ledger in") and "X: " + item in out[2], out)


    def test_a_source_row_holds_only_when_the_text_is_in_the_shipped_program_closure(self):
        (self.d / "src/user/ci/kit/bar.ci").write_text("I64 hold_ms = 400;   // DN-11\n")
        row = [("DN-11", "x", "source hdesk hold_ms = 400", "p", "x", "IN")]
        out = self.ledger(self.GOOD + row)
        self.assertTrue(out[2].startswith("FAIL  ledger in") and "DN-11: source hdesk hold_ms = 400" in out[2], out)
        (self.d / "src/user/ci/hdesk.ci").write_text('import user.ci.kit.apps;\nimport user.ci.kit.bar;\n'
                                                     'U8[9] c = b"/bin/cish";\n')
        cr.fails = 0
        out = self.ledger(self.GOOD + row)
        self.assertEqual([x[:4] for x in out], ["PASS"] * 4, out)


    def test_a_nosource_row_fails_when_the_text_is_in_the_closure(self):
        (self.d / "src/user/ci/kit/bar.ci").write_text('U8[16] m = b"Minimize to Tray";\n')
        row = [("DN-19", "x", "nosource hdesk Minimize to Tray", "p", "x", "IN")]
        out = self.ledger(self.GOOD + row)
        self.assertEqual([x[:4] for x in out], ["PASS"] * 4, out)
        (self.d / "src/user/ci/hdesk.ci").write_text('import user.ci.kit.apps;\nimport user.ci.kit.bar;\n'
                                                     'U8[9] c = b"/bin/cish";\n')
        cr.fails = 0
        out = self.ledger(self.GOOD + row)
        self.assertTrue(out[2].startswith("FAIL  ledger in") and "DN-19: nosource hdesk" in out[2], out)

    def test_an_in_row_on_membership_alone_fails_its_form(self):
        for arts in ("member hdesk; member bin/finder", "nomember bin/doom", "member hdesk; nomember bin/doom"):
            cr.fails = 0
            out = self.ledger(self.GOOD + [("DN-23", "x", arts, "p", "x", "IN")])
            self.assertTrue(out[0].startswith("FAIL  ledger form") and "DN-23: IN on membership alone" in out[0], out)

    def test_a_source_row_does_not_hold_on_a_comment(self):
        (self.d / "src/user/ci/hdesk.ci").write_text('import user.ci.kit.apps;\nU8[9] c = b"/bin/cish";\n'
                                                     '// STRIP_HOLD_MS = 800 is ruled\nU8[8] u = b"a//b";\n')
        out = self.ledger(self.GOOD + [("DN-11", "x", "source hdesk STRIP_HOLD_MS = 800", "p", "x", "IN")])
        self.assertTrue(out[2].startswith("FAIL  ledger in") and "DN-11: source hdesk" in out[2], out)
        cr.fails = 0
        out = self.ledger(self.GOOD + [("U", "x", 'source hdesk b"a//b"', "p", "x", "IN")])
        self.assertEqual([x[:4] for x in out], ["PASS"] * 4, out)


    def test_a_file_row_holds_only_on_a_line_of_the_tree_that_is_no_comment(self):
        (self.d / "src/tools").mkdir(parents=True, exist_ok=True)
        (self.d / "src/tools/build-release-stick.sh").write_text("# needs Debian or Ubuntu\n")
        row = [("BUILD-HOST", "x", "file tools/build-release-stick.sh needs Debian or Ubuntu", "p", "x", "IN")]
        out = self.ledger(self.GOOD + row)
        self.assertTrue(out[2].startswith("FAIL  ledger in") and "BUILD-HOST: file tools/" in out[2], out)
        (self.d / "src/tools/build-release-stick.sh").write_text(
            '#!/bin/sh\n[ -x /usr/bin/dpkg ] || { echo "build-release-stick: needs Debian or Ubuntu" >&2; exit 2; }\n')
        cr.fails = 0
        out = self.ledger(self.GOOD + row)
        self.assertEqual([x[:4] for x in out], ["PASS"] * 4, out)
        for item in ("file ../src/tools/build-release-stick.sh needs", "file tools/none.sh needs"):
            cr.fails = 0
            out = self.ledger(self.GOOD + [("X", "x", item, "p", "x", "IN")])
            self.assertTrue(out[2].startswith("FAIL  ledger in") and "X: " + item in out[2], out)

    def test_bars_apps_holds_only_when_the_booted_bar_names_every_app(self):
        row = [("NAMES-28", "x", "bars apps", "p", "x", "IN")]
        (self.d / "desk.txt").write_text("hdesk: bar desktop 1 |Index| var |/|\nhdesk: bar desktop 1 |bin/cish|\n")
        out = self.ledger(self.GOOD + row, transcript=False)
        self.assertTrue(out[2].startswith("FAIL  ledger in") and "NAMES-28: bars apps" in out[2], out)
        (self.d / "desk.txt").write_text("daphnis: net dhcp 10.0.2.15/24\nhdesk: bar desktop 1 |Index| var |/|\n"
                                         "hdesk: bar desktop 2 |Console| var |/|\n")
        cr.fails = 0
        out = self.ledger(self.GOOD + row, transcript=False)
        self.assertEqual([x[:4] for x in out], ["PASS"] * 4, out)



class CheckReleaseVolume(unittest.TestCase):
    """tools/check-release-volume.py on small ext2 volumes made with mke2fs -d, as tools/mkcintvol.sh makes them."""
    def setUp(self):
        t = tempfile.TemporaryDirectory(prefix="relvol-", dir=os.environ.get("TMPDIR"))
        self.addCleanup(t.cleanup)
        self.d = pathlib.Path(t.name)
        self.tree = self.d / "tree"
        (self.tree / "user/cint/opt/lib").mkdir(parents=True)
        (self.tree / "user/cint/opt/cint").write_bytes(b"\x7fELF cint")
        (self.tree / "user/cint/opt/lib/libc.a").write_bytes(b"!<arch>\n")
        (self.tree / "user/ci").mkdir(parents=True)
        (self.tree / "user/ci/acct.ci").write_text("// the release acct.ci\n")
        (self.tree / "src").mkdir()
        (self.tree / "src/sha256.ci").write_text("// sha256\n")
        (self.tree / "tests/image").mkdir(parents=True)
        (self.tree / "tests/image/build-sources.txt").write_text("user/ci/acct.ci\nsrc/sha256.ci\n")

    def volume(self, change=None):
        st = self.d / "stage"
        subprocess.run(["rm", "-rf", str(st)], check=True)
        for p in ("opt", "src/user/ci", "src/src", "out", ".daphnis", "log"):
            (st / p).mkdir(parents=True, exist_ok=True)
        subprocess.run(["cp", "-RP", str(self.tree / "user/cint/opt"), str(st / "opt/cint")], check=True)
        (st / "src/user/ci/acct.ci").write_bytes((self.tree / "user/ci/acct.ci").read_bytes())
        (st / "src/src/sha256.ci").write_bytes((self.tree / "src/sha256.ci").read_bytes())
        if change:
            change(st)
        img = self.d / "vol.img"
        subprocess.run(["mke2fs", "-q", "-F", "-t", "ext2", "-b", "4096", "-d", str(st), str(img), "2M"],
                       check=True, env=dict(os.environ, PATH=os.environ.get("PATH", "") + ":/usr/sbin:/sbin",
                                            MKE2FS_CONFIG="/dev/null"))
        return img

    def check(self, img):
        r = subprocess.run([sys.executable, str(ROOT / "tools/check-release-volume.py"), str(img), str(self.tree)],
                           capture_output=True, text=True,
                           env=dict(os.environ, PATH=os.environ.get("PATH", "") + ":/usr/sbin:/sbin"))
        return r.returncode, r.stdout

    def test_the_release_volume_passes(self):
        rc, out = self.check(self.volume())
        self.assertEqual(rc, 0, out)
        self.assertIn("each TREE's bytes", out)

    def test_a_fixture_under_a_release_files_name_fails(self):
        rc, out = self.check(self.volume(lambda st: (st / "src/user/ci/acct.ci").write_text("hello\n")))
        self.assertEqual(rc, 1, out)
        self.assertIn("/src/user/ci/acct.ci does not hold TREE's bytes", out)

    def test_a_name_with_a_newline_fails(self):
        rc, out = self.check(self.volume(lambda st: (st / "a\nb").write_text("x\n")))
        self.assertEqual(rc, 1, out)
        self.assertIn("does not parse", out)

    def test_a_test_fixture_fails(self):
        rc, out = self.check(self.volume(lambda st: (st / "hello.txt").write_text("hello\n")))
        self.assertEqual(rc, 1, out)
        self.assertIn("/hello.txt on the volume is not a release file", out)


class BuildReleaseStickHost(unittest.TestCase):
    """tools/build-release-stick.sh refuses, before any work, a host without dpkg's grub-efi-amd64-bin (0.1.0 builds
    the stick on Debian or Ubuntu only: the release publishes that package's GRUB source)."""
    LINE = "build-release-stick: needs Debian or Ubuntu with grub-efi-amd64-bin; see NOTES.md"

    def run_with(self, dpkg_query):
        with tempfile.TemporaryDirectory() as d:
            if dpkg_query is not None:
                fake = os.path.join(d, "dpkg-query")
                with open(fake, "w") as f:
                    f.write("#!/bin/sh\n" + dpkg_query + "\n")
                os.chmod(fake, 0o755)
            out = os.path.join(d, "out", "stick.img")
            r = subprocess.run(["/bin/bash", os.path.join(ROOT, "tools", "build-release-stick.sh"), out],
                               env={"PATH": d, "HOME": d}, capture_output=True, text=True)
            return r, os.path.exists(os.path.dirname(out))

    def test_no_dpkg(self):
        r, made = self.run_with(None)
        self.assertEqual((r.returncode, r.stderr.strip(), made), (1, self.LINE, False))

    def test_no_grub_package(self):
        r, made = self.run_with("exit 1")
        self.assertEqual((r.returncode, r.stderr.strip(), made), (1, self.LINE, False))

    def test_grub_removed_config_kept(self):
        r, made = self.run_with("printf 'rc '")
        self.assertEqual((r.returncode, r.stderr.strip(), made), (1, self.LINE, False))

    def test_grub_installed_goes_on(self):
        r, _ = self.run_with("printf 'ii '")
        self.assertNotIn(self.LINE, r.stderr)
        self.assertNotEqual(r.returncode, 0)   # past the host check: this PATH has no realpath, git or cint

if __name__ == "__main__":
    unittest.main()
