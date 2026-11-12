import importlib.util
import os
from pathlib import Path
import shutil
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('sniff_cases',ROOT/'tests/html/sniff_cases.py')
cases=importlib.util.module_from_spec(spec);spec.loader.exec_module(cases)
class SniffInventory(unittest.TestCase):
    def reject(self,name,data):
        with tempfile.TemporaryDirectory(prefix='sniff-inventory-',dir=os.environ.get('HTML_TEST_WORK')) as d:
            root=Path(d)
            shutil.copytree(ROOT/'tests/html/corpus/sniff',root/'tests/html/corpus/sniff')
            (root/'vendor/whatwg-encoding').mkdir(parents=True)
            shutil.copyfile(ROOT/'vendor/whatwg-encoding/encodings.json',root/'vendor/whatwg-encoding/encodings.json')
            path=root/'tests/html/corpus/sniff'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
            with self.assertRaisesRegex(ValueError,'inventory'):cases.cases(root)
    def test_unlisted_dat_is_rejected(self):self.reject('unpinned.dat',b'#data\n<meta charset=utf-8>\n#encoding\nutf-8\n')
    def test_nested_unknown_is_rejected(self):self.reject('nested/unknown.bin',b'unlisted')
    def test_arbitrary_receipt_is_rejected(self):self.reject('receipt.json',b'{}')
if __name__=='__main__':unittest.main()
