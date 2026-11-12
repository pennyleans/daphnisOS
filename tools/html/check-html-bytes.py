#!/usr/bin/env python3
"""Qualify native byte selection and byte-to-token integration."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess


def module(name, path):
    spec=importlib.util.spec_from_file_location(name,path)
    loaded=importlib.util.module_from_spec(spec);spec.loader.exec_module(loaded);return loaded


def main():
    ap=argparse.ArgumentParser()
    for name in ['out','cint','toolchain']: ap.add_argument('--'+name,type=Path,required=True)
    ap.add_argument('--compiler-source-id');ap.add_argument('--compiler-sha256')
    args=ap.parse_args();args.cint=args.cint.resolve(strict=True);root=Path(__file__).resolve().parents[2]
    checker=module('check_encoding',root/'tools/html/check-encoding.py')
    try:
        pair=checker.identity_pair(args.compiler_source_id,args.compiler_sha256)
        identity=checker.compiler_identity(args.cint,*pair)
    except ValueError as exc: ap.error(str(exc))
    out=args.out.resolve();assert root!=out and root not in out.parents
    out.mkdir(parents=True,exist_ok=True)
    cases=module('sniff_cases',root/'tests/html/sniff_cases.py')
    rows,skipped=cases.cases(root);pipeline=cases.pipeline_cases(root)
    source_paths=['check-html.sh','tools/html/check-encoding.py','tools/html/check-tokenizer.py','tests/html/test_tokenizer_inventory.py','tests/html/test_sniff_inventory.py','tests/html/test_relative_compiler.py','tools/html/check-html-bytes.py','tests/html/sniff_cases.py','tests/html/sniff_driver.ci','tests/html/byte_token_driver.ci','tests/html/encoding_host.c','tests/html/test_compiler_identity.py','tests/html/test_html_wrapper.py','tests/html/test_sniff_provenance.py','tests/html/HTML-BYTES.md','user/ci/web/sniff.ci','user/ci/web/encoding.ci','user/ci/web/encoding_data.ci','user/ci/web/tokenizer.ci','user/ci/web/reference.ci','user/ci/web/reference_data.ci']
    source_paths += [str(p.relative_to(root)) for directory in ['tests/html/corpus/sniff','vendor/whatwg-html','vendor/whatwg-encoding'] for p in sorted((root/directory).rglob('*')) if p.is_file()]
    initial={p:checker.sha(root/p) for p in source_paths}
    initial_toolchain=checker.sha(args.toolchain)
    receipt=dict(source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),source_dirty_paths=subprocess.check_output(['git','status','--porcelain'],cwd=root,text=True).splitlines(),compiler_identity=identity,suites={},native_skipped=skipped)
    include=Path(next(line.split(' ',1)[1] for line in args.toolchain.read_text().splitlines() if line.startswith('include ')))
    common=['-std=c17','-O2','-Wall','-Wextra','-Werror','-DCINT_RT_HELPERS_PORTABLE','-DCI_FRAME_ARENA_BYTES=16777216','-I'+str(include),'-I'+str(root/'user/ci')]
    for suite,records,driver in [('sniff',rows,'sniff_driver.ci'),('tokens',pipeline,'byte_token_driver.ci')]:
        dest=out/suite;dest.mkdir(exist_ok=True)
        fixture=dest/'cases.bin';cases.write_fixture(records,fixture)
        inventory=[dict(row,case=i,data_hex=row['data'].hex(),label=row['label'].decode('ascii')) for i,row in enumerate(records)]
        for row in inventory: del row['data']
        (dest/'case-inventory.json').write_text(json.dumps(inventory,indent=2)+'\n')
        modules=['user/ci/web/encoding_data.ci','user/ci/web/encoding.ci','user/ci/web/sniff.ci']
        if suite=='tokens': modules+=['user/ci/web/reference_data.ci','user/ci/web/reference.ci','user/ci/web/tokenizer.ci']
        modules+=['tests/html/'+driver]
        checker.run([args.cint,'emit-c','--toolchain',args.toolchain,'--root',root,'--out',dest/'emit',*modules],dest/'emit.log',cwd=root)
        emitted=dest/(dest/'emit/MANIFEST.ref').read_text().split()[0]
        program=emitted/'cint-program.c';entry=re.search(r'\bcg_[0-9A-Za-z_]+_run\b',program.read_text()).group()
        stats=dict(cases=len(records),fixture_sha256=checker.sha(fixture),inventory_sha256=checker.sha(dest/'case-inventory.json'),emitted_c_bytes=sum(p.stat().st_size for p in emitted.rglob('*.c')))
        previous=None
        for cc in ['gcc','clang']:
            obj=dest/(cc+'.o');binary=dest/(cc+'-'+suite)
            checker.run([cc,*common,'-Dmain=cint_emitted_main','-c',program,'-o',obj],dest/(cc+'-compile.log'))
            checker.run([cc,*common,'-DCI_RUN='+entry,obj,*sorted(p for p in emitted.rglob('*.c') if p!=program),root/'user/ci/main.c',root/'tests/html/encoding_host.c',include/'cint_rt.c','-o',binary],dest/(cc+'-link.log'))
            for repeat in range(2):
                stdout=checker.run([binary],dest/f'{cc}-{repeat}.stdout',env=dict(os.environ,HTML_ENCODING_INPUT=str(fixture)))
                actual=[list(map(int,line.split())) for line in stdout.splitlines()]
                assert len(actual)==len(records),(suite,cc,len(actual),len(records))
                failures=[dict(case=i,name=row['name'],expected=row['expected'],actual=value) for i,(row,value) in enumerate(zip(records,actual)) if len(value)!=len(row['expected']) or any(e is not None and e!=v for e,v in zip(row['expected'],value))]
                (dest/f'{cc}-{repeat}-failures.json').write_text(json.dumps(failures,indent=2)+'\n')
                assert not failures,(suite,cc,len(failures),failures[:4])
                if previous is not None: assert previous==stdout,'compiler/repeat output drift'
                previous=stdout
            stats[cc]=dict(passed=len(records),failed=0,repeats=2,stdout_sha256=hashlib.sha256(stdout).hexdigest(),binary_sha256=checker.sha(binary),binary_bytes=binary.stat().st_size,version=subprocess.check_output([cc,'--version'],text=True).splitlines()[0])
            print(f'{suite} {cc}: {len(records)} passed, repeated twice',flush=True)
        receipt['suites'][suite]=stats
    assert {p:checker.sha(root/p) for p in initial}==initial,'source changed during qualification'
    assert checker.compiler_identity(args.cint,*pair)==identity,'compiler changed during qualification'
    assert checker.sha(args.toolchain)==initial_toolchain,'toolchain changed during qualification'
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()==receipt['source_commit'],'source commit changed during qualification'
    receipt['sources_sha256']=initial
    receipt['source_bytes']={p:(root/p).stat().st_size for p in source_paths}
    for key,path in [('cint',args.cint),('toolchain',args.toolchain),('bootstrap',args.cint.parent/'bootstrap.json')]: receipt[key+'_sha256']=checker.sha(path)
    (out/'html-bytes-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')

if __name__=='__main__':main()
