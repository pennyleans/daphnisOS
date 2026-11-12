import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('check_encoding',ROOT/'tools/html/check-encoding.py')
checker=importlib.util.module_from_spec(spec);spec.loader.exec_module(checker)
SOURCE='a'*64
class RelativeCompiler(unittest.TestCase):
    def setup_tools(self,base,path_source):
        cwd=base/'cwd';search=base/'path';cwd.mkdir();search.mkdir();log=base/'invocations'
        for directory,source in [(cwd,SOURCE),(search,path_source)]:
            exe=directory/'cint'
            exe.write_text('#!/bin/sh\n# '+directory.name+'\nprintf "%s|%s\\n" "$0" "$1" >> "$CINT_PROBE_LOG"\nif [ "$1" = --version ]; then\n echo "cint 0.2.17"\n echo "compiler source identity '+source+'"\n exit 0\nfi\nexit 23\n')
            exe.chmod(0o755)
        self.assertNotEqual(checker.sha(cwd/'cint'),checker.sha(search/'cint'))
        (cwd/'bootstrap.json').write_text(json.dumps({'identity':{'compiler_source_identity':SOURCE}}))
        toolchain=base/'toolchain';toolchain.write_text(Path(os.environ['CINT_TOOLCHAIN']).read_text())
        env=dict(os.environ,PATH=str(search)+':'+os.environ['PATH'],CINT_PROBE_LOG=str(log))
        return cwd,log,toolchain,env
    def test_relative_identity_invokes_hashed_cwd_executable(self):
        with tempfile.TemporaryDirectory(prefix='relative-identity-',dir=os.environ.get('HTML_TEST_WORK')) as d:
            cwd,log,toolchain,env=self.setup_tools(Path(d),'b'*64)
            old=Path.cwd()
            try:
                os.chdir(cwd)
                with patch.dict(os.environ,env,clear=True):result=checker.compiler_identity(Path('./cint'),SOURCE,checker.sha(cwd/'cint'))
            finally:os.chdir(old)
            self.assertEqual(result['version_source_id'],SOURCE)
            self.assertEqual(log.read_text().splitlines(),[str(cwd/'cint')+'|--version'])
    def test_both_emit_commands_use_hashed_cwd_executable(self):
        for script in ['check-encoding.py','check-html-bytes.py']:
            with self.subTest(script=script),tempfile.TemporaryDirectory(prefix='relative-emit-',dir=os.environ.get('HTML_TEST_WORK')) as d:
                cwd,log,toolchain,env=self.setup_tools(Path(d),SOURCE)
                result=subprocess.run(['python3','-B',str(ROOT/'tools/html'/script),'--out',str(Path(d)/'output'),'--cint','./cint','--toolchain',str(toolchain),'--compiler-source-id',SOURCE,'--compiler-sha256',checker.sha(cwd/'cint')],cwd=cwd,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
                self.assertNotEqual(result.returncode,0)
                self.assertIn('command failed (23)',result.stderr)
                invocations=log.read_text().splitlines()
                self.assertIn(str(cwd/'cint')+'|emit-c',invocations)
                self.assertTrue(all(row.startswith(str(cwd/'cint')+'|') for row in invocations),invocations)
if __name__=='__main__':unittest.main()
