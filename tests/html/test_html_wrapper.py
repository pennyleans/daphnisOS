"""Exercise shell identity validation and argument forwarding at process boundaries."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
SOURCE='a'*64
SHA='b'*64

class HtmlWrapper(unittest.TestCase):
    def invoke(self, pair):
        with tempfile.TemporaryDirectory(prefix='wrapper-',dir=os.environ.get('HTML_TEST_WORK')) as d:
            p=Path(d);log=p/'calls'
            (p/'cint').write_text('#!/bin/sh\nprintf "cint fixture\\n"\n');(p/'cint').chmod(0o755)
            (p/'python3').write_text('#!/bin/sh\nprintf "CALL\\n" >> "$CALL_LOG"\nprintf "%s\\n" "$@" >> "$CALL_LOG"\n');(p/'python3').chmod(0o755)
            env=dict(os.environ,PATH=str(p)+':/usr/bin:/bin',CALL_LOG=str(log),DAPHNIS_BUILD=str(p/'output'),CINT_TOOLCHAIN='/fixture/toolchain')
            for key in ['CINT_EXPECTED_SOURCE_ID','CINT_EXPECTED_SHA256']:env.pop(key,None)
            env.update(pair)
            result=subprocess.run(['bash',str(ROOT/'check-html.sh')],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            return result,log.read_text().split('CALL\n')[1:] if log.exists() else []
    def test_partial_and_malformed_pairs_rejected(self):
        for pair in [{'CINT_EXPECTED_SOURCE_ID':SOURCE},{'CINT_EXPECTED_SHA256':SHA},{'CINT_EXPECTED_SOURCE_ID':'','CINT_EXPECTED_SHA256':''},{'CINT_EXPECTED_SOURCE_ID':'A'*64,'CINT_EXPECTED_SHA256':SHA}]:
            with self.subTest(pair=pair):
                result,calls=self.invoke(pair)
                self.assertEqual(result.returncode,2)
                self.assertIn('compiler identity',result.stderr)
                self.assertEqual(calls,[])
    def test_explicit_pair_reaches_both_new_suites(self):
        result,calls=self.invoke({'CINT_EXPECTED_SOURCE_ID':SOURCE,'CINT_EXPECTED_SHA256':SHA})
        self.assertEqual(result.returncode,0,result.stderr)
        for script in ['check-encoding.py','check-html-bytes.py']:
            selected=[c for c in calls if script in c]
            self.assertEqual(len(selected),1)
            self.assertIn('--compiler-source-id\n'+SOURCE+'\n',selected[0])
            self.assertIn('--compiler-sha256\n'+SHA+'\n',selected[0])
    def test_default_has_no_explicit_pair(self):
        result,calls=self.invoke({})
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(len(calls),4)
        self.assertTrue(all('--compiler-source-id' not in c and '--compiler-sha256' not in c for c in calls))

if __name__=='__main__':unittest.main()
