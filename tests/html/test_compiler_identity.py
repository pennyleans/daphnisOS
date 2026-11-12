"""Focused profile guards; no decoder execution is substituted."""
import importlib.util
import os
from pathlib import Path
import tempfile
import hashlib
import json
import unittest
import subprocess

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('check_encoding', ROOT / 'tools/html/check-encoding.py')
checker = importlib.util.module_from_spec(spec); spec.loader.exec_module(checker)
# the two compilers these guards compare, by path: HTML_PRIVATE_CINT and HTML_PUBLIC_CINT (each beside its bootstrap.json)
PRIVATE = Path(os.environ.get('HTML_PRIVATE_CINT', 'HTML_PRIVATE_CINT-not-set'))
PUBLIC = Path(os.environ.get('HTML_PUBLIC_CINT', 'HTML_PUBLIC_CINT-not-set'))
NEED = unittest.skipUnless(PRIVATE.is_file() and PUBLIC.is_file(), 'set HTML_PRIVATE_CINT and HTML_PUBLIC_CINT')
PUBLIC_SOURCE = 'baa6d80a6614ba2872e763cb45e5f80a45995578cd3288fc369b0525bb2f661f'
PUBLIC_SHA = '59d948a4ef18b9786a6fa1c4e2387a96eeca0f891ff840e005e5781ec1b9e50a'

class CompilerIdentity(unittest.TestCase):
    @NEED
    def test_defaults_preserve_private(self):
        source, executable = checker.identity_pair(None, None)
        result = checker.compiler_identity(PRIVATE, source, executable)
        self.assertEqual(result['expected_source_id'], result['version_source_id'])
        self.assertEqual(result['expected_sha256'], result['observed_sha256'])
    @NEED
    def test_explicit_public(self):
        source, executable = checker.identity_pair(PUBLIC_SOURCE, PUBLIC_SHA)
        result = checker.compiler_identity(PUBLIC, source, executable)
        self.assertEqual(result['bootstrap_source_id'], PUBLIC_SOURCE)
        self.assertEqual(result['version_source_id'], PUBLIC_SOURCE)
    def test_pair_validation(self):
        for source, executable in [(None, PUBLIC_SHA), (PUBLIC_SOURCE, None), ('', ''), ('A'*64, 'a'*64), ('a'*63, 'b'*64), ('a'*64, 'g'*64)]:
            with self.subTest(source=source, executable=executable):
                with self.assertRaises(ValueError): checker.identity_pair(source, executable)
    @NEED
    def test_default_rejects_public(self):
        with self.assertRaisesRegex(ValueError, 'executable'): checker.compiler_identity(PUBLIC, *checker.identity_pair(None, None))
    @NEED
    def test_wrong_expected_source(self):
        with self.assertRaisesRegex(ValueError, 'bootstrap'): checker.compiler_identity(PRIVATE, '0'*64, checker.sha(PRIVATE))
    @NEED
    def test_cli_rejects_partial_and_malformed_pairs(self):
        for script in ['check-encoding.py','check-html-bytes.py']:
            for pair in [['--compiler-source-id',PUBLIC_SOURCE],['--compiler-sha256',PUBLIC_SHA],['--compiler-source-id','A'*64,'--compiler-sha256',PUBLIC_SHA]]:
                result=subprocess.run(['python3','-B',str(ROOT/'tools/html'/script),'--out',str(Path(os.environ.get('HTML_TEST_WORK') or tempfile.gettempdir())/'identity-cli'),'--cint',str(PUBLIC),'--toolchain',str(PUBLIC)+'.toolchain',*pair],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
                self.assertEqual(result.returncode,2)
                self.assertIn('compiler',result.stderr)
    def test_version_and_bootstrap_mismatches(self):
        with tempfile.TemporaryDirectory(prefix='identity-', dir=os.environ.get('HTML_TEST_WORK')) as d:
            p=Path(d); exe=p/'cint'; source='a'*64
            exe.write_text('#!/bin/sh\necho "cint 0.2.17"\necho "compiler source identity '+source+'"\n'); exe.chmod(0o755)
            (p/'bootstrap.json').write_text(json.dumps({'identity': {'compiler_source_identity': 'b'*64}}))
            with self.assertRaisesRegex(ValueError, 'bootstrap'): checker.compiler_identity(exe, source, checker.sha(exe))
            (p/'bootstrap.json').write_text(json.dumps({'identity': {'compiler_source_identity': 'b'*64}}))
            with self.assertRaisesRegex(ValueError, 'version'): checker.compiler_identity(exe, 'b'*64, checker.sha(exe))
            exe.write_text('#!/bin/sh\necho "cint 0.2.17"\n'); exe.chmod(0o755)
            with self.assertRaisesRegex(ValueError, 'version'): checker.compiler_identity(exe, 'b'*64, checker.sha(exe))

if __name__ == '__main__': unittest.main()
