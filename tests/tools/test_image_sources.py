"""Tests for tools/check-image-apps.py every_image and scripts (RG-1): no image's recipe, not the release image's
alone, reads or writes the committed user/bin, and no gate, leg or tool names a program there; the tree passes.
  python3 -B -m unittest tests/tools/test_image_sources.py"""
import importlib.util
import os
import tempfile
import unittest

ROOT = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
spec = importlib.util.spec_from_file_location("check_image_apps", os.path.join(ROOT, "tools", "check-image-apps.py"))
apps = importlib.util.module_from_spec(spec)
spec.loader.exec_module(apps)

HEAD = "O ?= /tmp/x\nUB := $(O)/ubin\n$(UB)/%:\n\t@echo build $*\n"


def check(makefile):
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "user", "bin"))
        os.makedirs(os.path.join(d, "user", "ci"))
        open(os.path.join(d, "user", "bin", "cat"), "w").close()
        with open(os.path.join(d, "Makefile"), "w") as f:
            f.write(HEAD + makefile)
        return apps.every_image(d, os.devnull)


class EveryImage(unittest.TestCase):
    def test_from_ubin_passes(self):
        self.assertEqual(check("$(O)/a/initrd.cpio: $(UB)/cat\n\t@python3 tools/mkcpio.py $@ bin/cat=$(UB)/cat\n"),
                         ([], 1))

    def test_user_bin_in_any_spelling_is_refused(self):
        for src in ("user/bin/cat", "./user/bin/cat", "user/ci/../bin/cat", "$(CURDIR)/user/bin/cat"):
            bad, n = check("$(O)/a/initrd.cpio: %s\n\t@python3 tools/mkcpio.py $@ bin/cat=%s\n" % (src, src))
            self.assertEqual(n, 1)
            self.assertEqual(len(bad), 1, src)
            self.assertIn("committed user/bin", bad[0])

    def test_a_copy_through_another_image_is_refused(self):
        bad, _ = check("$(O)/u/sh: user/bin/cat\n\t@cp $< $@\n"
                       "$(O)/b/release.cpio: $(O)/u/sh\n\t@python3 tools/mkcpio.py $@ sh=$(O)/u/sh\n")
        self.assertEqual(len(bad), 1)
        self.assertIn("b/release.cpio", bad[0])

    def test_a_build_into_user_bin_is_refused(self):
        bad, _ = check("$(O)/a/initrd.cpio:\n\t@bash user/c/build.sh musltest\n")
        self.assertEqual(len(bad), 1)
        self.assertIn("without CI_OUT", bad[0])

    def test_a_program_with_no_rule_is_refused(self):
        bad, _ = check("$(O)/a/initrd.cpio: user/bin/monitor\n\t@true\n")
        self.assertEqual(len(bad), 1)
        self.assertIn("cannot plan a/initrd.cpio", bad[0])

    def test_the_tree_passes(self):
        bad, n = apps.every_image(ROOT)
        self.assertEqual(bad, [])
        self.assertGreaterEqual(n, 15)


def scan(files):
    with tempfile.TemporaryDirectory() as d:
        for name, text in files.items():
            os.makedirs(os.path.dirname(os.path.join(d, name)), exist_ok=True)
            with open(os.path.join(d, name), "w") as f:
                f.write(text)
        return apps.scripts(d)


class Scripts(unittest.TestCase):
    def test_o_ubin_and_notice_pass(self):
        bad, n = scan({"check-a.sh": 'UB=$B/ubin\n"$UB"/cish -c true\ncat user/bin/NOTICE\n',
                       "t/pin.sh": "sed 's#  user/bin/#  #' tests/expected/a.sha256\n",
                       "t/x.py": "# user/bin/cish, a note\nCISH = sys.argv[1]\n"})
        self.assertEqual((bad, n), ([], 3))

    def test_a_program_path_that_comes_back_is_refused(self):
        for line in ('user/bin/cish -c true', 'env PATH=x "$PWD/user/bin/cish"', 'x=./user/bin/tiler',
                     'mkcpio.py out sh=user/bin/cish'):
            bad, _ = scan({"check-a.sh": line + "\n"})
            self.assertEqual(len(bad), 1, line)
            self.assertIn("check-a.sh:1 names user/bin/", bad[0])

    def test_a_default_of_user_bin_is_refused(self):
        for line in ('out=${CI_OUT:-user/bin}', 'mkdir -p "${CI_OUT:-./user/bin}"', 'B=${B:-user/bin/}'):
            bad, _ = scan({"user/c/build.sh": line + "\n"})
            self.assertEqual(len(bad), 1, line)
            self.assertIn("defaults a path to user/bin", bad[0])
        bad, _ = scan({"b.sh": 'out=${CI_OUT:-${TMPDIR:-/tmp}/daphnis-build/ubin}\nx=${y:-user/binary}\n'})
        self.assertEqual(bad, [])

    def test_every_script_kind_is_scanned_and_docs_are_not(self):
        bad, n = scan({"Makefile": "x: user/bin/cat\n", "a.mk": "y: user/bin/cat\n",
                       "t/a.py": 'P = "user/bin/agent"\n', "t/b.py": 'P = os.path.join(R, "user", "bin", "cish")\n',
                       "docs/n.sh": "user/bin/cat\n", "t/a.ci": "// user/bin/cat\n"})
        self.assertEqual(n, 4)
        self.assertEqual(sorted(b.split(":")[0] for b in bad), ["Makefile", "a.mk", "t/a.py", "t/b.py"])

    def test_the_tree_passes(self):
        bad, n = apps.scripts(ROOT)
        self.assertEqual(bad, [])
        self.assertGreater(n, 200)


if __name__ == "__main__":
    unittest.main()
# SPDX-License-Identifier: Apache-2.0
