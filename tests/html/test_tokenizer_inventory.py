"""Keep exact tokenizer inventory checks inside the original corpus boundary."""
import importlib.util
import os
import json
from pathlib import Path
import shutil
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('tokenizer_check',ROOT/'tools/html/check-tokenizer.py')
checker=importlib.util.module_from_spec(spec);spec.loader.exec_module(checker)
class Inventory(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='tokenizer-inventory-',dir=os.environ.get('HTML_TEST_WORK'))
        self.corpus=Path(self.temp.name)
        original=ROOT/'tests/html/corpus'
        self.manifest=json.loads((original/'SOURCE.json').read_text())
        shutil.copyfile(original/'SOURCE.json',self.corpus/'SOURCE.json')
        for name in self.manifest['files']:
            target=self.corpus/name;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(original/name,target)
    def tearDown(self):self.temp.cleanup()
    def extra(self,name):
        path=self.corpus/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'unexpected')
    def test_original_and_exact_sibling_boundaries_are_accepted(self):
        self.assertEqual(checker.verify_corpus(self.corpus),self.manifest)
        self.extra('encoding/independent.dat');self.extra('sniff/independent.dat')
        self.assertEqual(checker.verify_corpus(self.corpus),self.manifest)
    def test_unexpected_tokenizer_file_is_rejected(self):
        self.extra('tokenizer/unexpected.test')
        with self.assertRaisesRegex(AssertionError,'inventory'):checker.verify_corpus(self.corpus)
    def test_unknown_sibling_is_rejected(self):
        self.extra('unknown/independent.dat')
        with self.assertRaisesRegex(AssertionError,'inventory'):checker.verify_corpus(self.corpus)
    def test_nested_names_are_not_excluded(self):
        self.extra('tokenizer/encoding/independent.dat');self.extra('wpt/sniff/independent.dat')
        with self.assertRaisesRegex(AssertionError,'inventory'):checker.verify_corpus(self.corpus)
    def test_unexpected_nested_manifest_is_rejected(self):
        self.extra('tokenizer/SOURCE.json')
        with self.assertRaisesRegex(AssertionError,'inventory'):checker.verify_corpus(self.corpus)
    def test_sibling_names_do_not_hide_root_files(self):
        self.extra('sniff')
        with self.assertRaisesRegex(AssertionError,'inventory'):checker.verify_corpus(self.corpus)
    def test_missing_original_is_rejected(self):
        (self.corpus/next(iter(self.manifest['files']))).unlink()
        with self.assertRaisesRegex(AssertionError,'inventory'):checker.verify_corpus(self.corpus)
    def test_modified_original_is_rejected(self):
        path=self.corpus/next(iter(self.manifest['files']));data=bytearray(path.read_bytes());data[0]^=1;path.write_bytes(data)
        with self.assertRaisesRegex(AssertionError,'identity'):checker.verify_corpus(self.corpus)
if __name__=='__main__':unittest.main()
