"""Original fixture bytes must stay bound to the imported pin."""
import importlib.util
import os
from pathlib import Path
import shutil
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('sniff_cases',ROOT/'tests/html/sniff_cases.py')
cases=importlib.util.module_from_spec(spec);spec.loader.exec_module(cases)
class Provenance(unittest.TestCase):
    def test_original_fixture_drift_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix='sniff-provenance-',dir=os.environ.get('HTML_TEST_WORK')) as d:
            root=Path(d)
            shutil.copytree(ROOT/'tests/html/corpus/sniff',root/'tests/html/corpus/sniff')
            (root/'vendor/whatwg-encoding').mkdir(parents=True)
            shutil.copyfile(ROOT/'vendor/whatwg-encoding/encodings.json',root/'vendor/whatwg-encoding/encodings.json')
            fixture=root/'tests/html/corpus/sniff/tests2.dat'
            fixture.write_bytes(fixture.read_bytes()+b'\n')
            with self.assertRaisesRegex(ValueError,'fixture identity'):cases.cases(root)
if __name__=='__main__':unittest.main()
