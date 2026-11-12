"""CV-2b replay checks: text objects, registers, repeat, macros, Visual mode, g~ gu gU =, H M L, the scroll keys
and marks (docs/handoff/20261108-cv2b.md). Each record holds the file, the byte cursor, the window's top line and the
registers of vim_leg.REGS, so a register, a mark or a scroll shows in the record.

    python3 tests/cvim/edit.py --out DIR                  frozen records, then the pinned Vim when present
    python3 tests/cvim/edit.py --cc clang --frozen-only --out DIR
    python3 tests/cvim/edit.py --freeze                   pinned Vim only: capture every record, mark it verified
    python3 tests/cvim/edit.py --capture-unverified       any Vim: capture, mark the file unverified

edit_golden.json says which Vim captured it. Records captured by a Vim other than VIM_VERSION are unverified: the run
prints NOTE and they are not a pass of record until --freeze recaptures them with the pinned Vim.
"""
import argparse
import concurrent.futures
import json
import os
from pathlib import Path
import sys
import run
import vim_leg
from edit_cases import CASES

HERE = Path(__file__).resolve().parent
GOLDEN = HERE / 'edit_golden.json'


def text(b):
    return b.decode('utf-8', errors='surrogateescape')


def expected(case):
    got = vim_leg.run_full(case['text'].encode(), case['keys'])
    if got['vmode'] != 'n':
        raise RuntimeError(case['id'] + ': the script did not end in Normal mode (' + got['vmode'] + ')')
    if got['height'] != 23:
        raise RuntimeError('Vim window height ' + str(got['height']) + ', not 23')
    regs = {n: [k, text(b)] for n, (k, b) in got['regs'].items()}
    return dict(text=text(got['text']), cursor=list(got['cursor']), mode=0, top=got['top'], regs=regs)


def capture(verified):
    actual = vim_leg.version()
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        want = list(ex.map(expected, CASES))
    doc = dict(vim=actual, verified=verified, cases={c['id']: w for c, w in zip(CASES, want)})
    GOLDEN.write_text(json.dumps(doc, ensure_ascii=True, indent=1, sort_keys=True) + '\n')
    print('captured', len(want), 'cases with', actual, '(verified)' if verified else '(unverified)')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--freeze', action='store_true')
    ap.add_argument('--capture-unverified', action='store_true')
    ap.add_argument('--only')
    ap.add_argument('--cc', choices=['gcc', 'clang'])
    ap.add_argument('--frozen-only', action='store_true')
    ap.add_argument('--out', type=Path, default=Path(os.environ.get('CINT_BUILD', '/tmp/cint-build')) / 'cvim-edit')
    args = ap.parse_args()
    pinned = (HERE / 'VIM_VERSION').read_text().strip()
    actual = vim_leg.version()
    if args.freeze:
        if actual != pinned:
            sys.exit('Vim pin mismatch: ' + str(actual))
        capture(True)
        return 0
    if args.capture_unverified:
        capture(False)
        return 0
    assert len({c['id'] for c in CASES}) == len(CASES), 'duplicate case ID'
    doc = json.loads(GOLDEN.read_text())
    frozen = doc['cases']
    assert set(frozen) <= {c['id'] for c in CASES}, 'a frozen record has no case'
    pending = [c for c in CASES if c['id'] not in frozen]
    if pending:
        print('NOTE  ' + str(len(pending)) + ' cases have no record yet (' + ', '.join(sorted({c['group'] for c in pending}))
              + '): replayed, not compared; edit.py --freeze on the pinned Vim captures them')
    cases = [c for c in CASES if (not args.only or args.only in c['id']) and c['id'] in frozen]
    if args.only and not cases:
        cases = [c for c in pending if args.only in c['id']]
    assert cases, 'no matching cases'
    args.out.mkdir(parents=True, exist_ok=True)
    got = run.replay(cases, args.out, args.cc, full=True)
    for g in got:
        del g['register']
    failures = 0
    if pending and not args.only:
        run.replay(pending, args.out, args.cc, full=True)   # the pending cases run too: a fault fails the leg
    for group in sorted({c['group'] for c in cases}, key=lambda g: [c['group'] for c in cases].index(g)):
        bad = []
        for c, g in zip(cases, got):
            if c['id'] not in frozen:
                continue
            if c['group'] == group and g != frozen[c['id']]:
                bad.append(c['id'])
                print('DIFF', c['id'], repr(c['keys']), '\n  want', frozen[c['id']], '\n  got ', g)
        print(('FAIL' if bad else 'PASS') + '  cvim ' + group + ': ' + str(sum(c['group'] == group for c in cases))
              + ' cases')
        failures += len(bad)
    if not doc['verified'] or doc['vim'] != pinned:
        print('NOTE  edit records unverified: captured with ' + str(doc['vim']) + '; the pin is ' + pinned)
    if not args.frozen_only and actual == pinned:
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
            oracle = list(ex.map(expected, cases))
        bad = [c['id'] for c, w, g in zip(cases, oracle, got) if w != g or w != frozen[c['id']]]
        print(('FAIL' if bad else 'PASS') + '  cvim edit Vim oracle: ' + str(len(cases)) + ' cases')
        failures += len(bad)
    elif not args.frozen_only:
        print('NOTE  Vim oracle not passed: expected ' + pinned + '; got ' + str(actual))
    print('cvim edit:', len(cases) - sum(c['id'] in frozen and g != frozen[c['id']] for c, g in zip(cases, got)), 'of',
          len(cases), 'pass')
    return bool(failures)


if __name__ == '__main__':
    sys.exit(main())
