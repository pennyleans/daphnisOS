"""Replay frozen cases through cvim and, when present, the exact pinned Vim."""
import argparse
import concurrent.futures
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import keys
from cases import CASES
import vim_leg
ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
GOLDEN = HERE / 'golden.json'
def expected(case):
    t, cur, reg = vim_leg.run_case(case['text'].encode(), case['keys'])
    return dict(text=t.decode(), cursor=list(cur), mode=0, register=[reg[0], reg[1].decode()])
KIND = {0: '', 1: 'v', 2: 'V'}
def replay(cases, outdir, cc=None, full=False):
    compiler = shutil.which('cint')
    cmd = [compiler, 'build', '--root', '.', '--out', str(outdir), '--frame-arena', '33554432']
    if os.environ.get('CINT_CACHE'): cmd += ['--cache', os.environ['CINT_CACHE']]
    toolchain = os.environ.get('CINT_TOOLCHAIN')
    if cc:
        if not toolchain: raise RuntimeError('--cc requires CINT_TOOLCHAIN')
        compiler_path = shutil.which(cc)
        if not compiler_path: raise RuntimeError(cc+' is not installed')
        cc_version = subprocess.check_output([compiler_path, '-dumpversion'], text=True).strip()
        rows = Path(toolchain).read_text().splitlines()
        rows = [('cc '+compiler_path if r.startswith('cc ') else 'cc_version '+cc_version if r.startswith('cc_version ') else 'leg '+cc if r.startswith('leg ') else r) for r in rows]
        alternate = outdir/'host.toolchain'; alternate.write_text('\n'.join(rows)+'\n')
        toolchain = str(alternate)
    if toolchain: cmd += ['--toolchain', toolchain]
    build = subprocess.run(cmd + ['tests/cvim/replay.ci'], cwd=ROOT, capture_output=True)
    if build.returncode: raise RuntimeError((build.stdout + build.stderr).decode())
    packed = bytearray(struct.pack('<q', len(cases)))
    for c in cases:
        t = c['text'].encode(); kk = keys.codes(c['keys'])
        packed += struct.pack('<qq', len(t), len(kk)) + t + struct.pack('<' + 'q'*len(kk), *kk)
    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, 'all').write_bytes(packed)
        p = subprocess.run([str(outdir/'replay'), '--grant', 'fs.read:/case='+tmp], capture_output=True, timeout=15)
    if p.returncode: raise RuntimeError(p.stderr.decode() + p.stdout.decode(errors='replace'))
    out = p.stdout; pos = 0; results = []
    for c in cases:
        end = out.index(b'\n', pos)
        _, index, nt, line, col, mode, rt, nr, bell, msg, top = out[pos:end].split()
        nt, nr = int(nt), int(nr); pos = end+1
        t = out[pos:pos+nt].decode(errors='surrogateescape'); pos += nt+1
        reg = out[pos:pos+nr].decode(errors='surrogateescape'); pos += nr+1
        regs = {}
        for name in vim_leg.REGS:
            end = out.index(b'\n', pos)
            kind, width, n = (int(v) for v in out[pos:end].split()); pos = end+1
            body = out[pos:pos+n].decode(errors='surrogateescape'); pos += n+1
            k = 'b'+str(width) if kind == 3 else KIND[kind]
            regs[name] = [k if body else '', body]
        got = dict(text=t, cursor=[int(line),int(col)], mode=int(mode), register=['V' if int(rt) else 'v',reg])
        if full: got.update(top=int(top), regs=regs)
        results.append(got)
    assert pos == len(out), out[pos:]
    return results
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--freeze', action='store_true'); ap.add_argument('--only'); ap.add_argument('--cc', choices=['gcc','clang']); ap.add_argument('--frozen-only', action='store_true'); ap.add_argument('--out', type=Path, default=Path(os.environ.get('CINT_BUILD','/tmp/cint-build'))/'cvim-tests'); args=ap.parse_args()
    pinned=(HERE/'VIM_VERSION').read_text().strip(); actual=vim_leg.version()
    if args.freeze:
        if actual != pinned: sys.exit('Vim pin mismatch: '+str(actual))
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex: want=list(ex.map(expected, CASES))
        GOLDEN.write_text(json.dumps({c['id']:w for c,w in zip(CASES,want)},ensure_ascii=False,indent=2)+'\n')
        print('froze',len(want),'cases from pinned Vim'); return 0
    assert len(CASES) >= 150 and len({c['id'] for c in CASES}) == len(CASES), 'case count or duplicate ID'
    cases=[c for c in CASES if not args.only or args.only in c['id']]
    assert cases, 'no matching cases'
    frozen=json.loads(GOLDEN.read_text())
    assert set(frozen) == {c['id'] for c in CASES}, 'cases and frozen goldens differ'
    args.out.mkdir(parents=True,exist_ok=True)
    got=replay(cases,args.out,args.cc); failures=0
    for group in sorted({c['group'] for c in cases}):
        bad=[]
        for c,g in zip(cases,got):
            if c['group']==group and g!=frozen[c['id']]: bad.append(c['id']); print('DIFF',c['id'],repr(c['keys']),'want',frozen[c['id']],'got',g)
        print(('FAIL' if bad else 'PASS')+'  cvim '+group+': '+str(sum(c['group']==group for c in cases))+' cases')
        failures+=len(bad)
    if not args.frozen_only and actual==pinned:
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex: oracle=list(ex.map(expected,cases))
        bad=[c['id'] for c,w,g in zip(cases,oracle,got) if w!=g or w!=frozen[c['id']]]
        print(('FAIL' if bad else 'PASS')+'  cvim Vim oracle: '+str(len(cases))+' cases'); failures+=len(bad)
    elif not args.frozen_only: print('NOTE  Vim oracle not passed: expected '+pinned+'; got '+str(actual))
    print('cvim:',len(cases)-sum(g!=frozen[c['id']] for c,g in zip(cases,got)),'of',len(cases),'pass')
    return bool(failures)
if __name__=='__main__': sys.exit(main())
