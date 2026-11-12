"""Motion regressions and separately asserted terminal-width differences."""
import argparse
import concurrent.futures
import json
from pathlib import Path
import run
from motion_cases import CASES, EXCEPTIONS

HERE = Path(__file__).resolve().parent
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--cc', choices=['gcc', 'clang'])
    ap.add_argument('--frozen-only', action='store_true')
    args = ap.parse_args()
    frozen = json.loads((HERE/'motion_golden.json').read_text())
    cases = CASES + EXCEPTIONS
    assert set(frozen) == {c['id'] for c in cases}
    args.out.mkdir(parents=True, exist_ok=True)
    got = run.replay(cases, args.out, args.cc)
    bad = 0
    equality_bad = 0
    policy_bad = 0
    for c, g in zip(cases, got):
        want = c.get('cvim', frozen[c['id']])
        if g != want:
            print('DIFF', c['id'], 'want', want, 'got', g)
            bad += 1
            if 'cvim' in c: policy_bad += 1
            else: equality_bad += 1
    print('motion frozen equality:', len(CASES)-equality_bad, 'of', len(CASES), 'pass')
    print('motion cvim policy:', len(EXCEPTIONS)-policy_bad, 'of', len(EXCEPTIONS), 'pass')
    if not args.frozen_only:
        assert run.vim_leg.version() == (HERE/'VIM_VERSION').read_text().strip(), 'Vim pin mismatch'
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
            oracle = list(ex.map(run.expected, cases))
        failures = sum(w != frozen[c['id']] or g != w
                       for c, w, g in zip(CASES, oracle, got))
        policy_failures = sum(w != frozen[c['id']] or g != c['cvim'] or g == w
                              for c,w,g in zip(EXCEPTIONS,oracle[len(CASES):],got[len(CASES):]))
        bad += failures + policy_failures
        print('motion fresh equality:', len(CASES)-failures, 'of', len(CASES), 'pass')
        print('motion Vim distinct policy:', len(EXCEPTIONS)-policy_failures, 'of', len(EXCEPTIONS), 'pass')
    return bool(bad)
if __name__ == '__main__': raise SystemExit(main())
