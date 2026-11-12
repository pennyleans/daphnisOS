#!/usr/bin/env python3
# tests/hw/mutants.py: whether tests/hw/gpt_test.ci has teeth for HW-12, the boot line naming the partition a board
# may write by its unique GUID (src/gpt.ci: guid, names, and entry's GUID). Each mutant breaks one rule in a copy of
# src/ and tests/hw/, never in the tree; a test of gpt_test.ci must then fail. One line a mutant: CAUGHT (a test
# failed), MISSED (none did) or BROKEN (the mutant did not build, which proves nothing). Exit status 1 unless every
# mutant is caught. Not part of the gate: some seconds a mutant.
#   python3 tests/hw/mutants.py OUT      (OUT must not exist; cint on PATH, CINT_TOOLCHAIN as for check.sh)
import os
import pathlib
import shutil
import subprocess
import sys

TREE = pathlib.Path(__file__).resolve().parent.parent.parent

# (name, file, text, its replacement): each text occurs once.
MUTANTS = [
    ("a GUID's bytes kept in the text's order", 'src/gpt.ci',
     'I64[16] place = [3, 2, 1, 0, 5, 4, 7, 6,', 'I64[16] place = [0, 1, 2, 3, 4, 5, 6, 7,'),
    ('a high digit read as the low', 'src/gpt.ci',
     'g[place[k]] = (16 * hi + lo) as U8;', 'g[place[k]] = (16 * lo + hi) as U8;'),
    ('G read as a digit', 'src/gpt.ci', 'c >= 65 && c <= 70', 'c >= 65 && c <= 71'),
    ('@ read as a digit', 'src/gpt.ci', 'c >= 65 && c <= 70', 'c >= 64 && c <= 70'),
    (': read as a digit', 'src/gpt.ci', 'c >= 48 && c <= 57', 'c >= 48 && c <= 58'),
    ('/ read as a digit', 'src/gpt.ci', 'c >= 48 && c <= 57', 'c >= 47 && c <= 57'),
    ('` read as a digit', 'src/gpt.ci', 'c >= 97 && c <= 102', 'c >= 96 && c <= 102'),
    ('g read as a digit', 'src/gpt.ci', 'c >= 97 && c <= 102', 'c >= 97 && c <= 103'),
    ('lower case refused', 'src/gpt.ci', 'c >= 97 && c <= 102', 'c >= 97 && c <= 96'),
    ('a dash not checked', 'src/gpt.ci', 'ok = s[at + i] == 45;', 'ok = true;'),
    ('a text longer than 36 bytes read', 'src/gpt.ci', 'if (n != 36) {', 'if (n < 36) {'),
    ('a GUID of zeros named', 'src/gpt.ci', 'while (!blank && !found', 'while (!found'),
    ("a word's end not checked", 'src/gpt.ci',
     '(i + w == nbytes || line[i + w] == 32)) {\n            Bool hit', 'true) {\n            Bool hit'),
    ("a word's start not checked", 'src/gpt.ci',
     'if ((i == 0 || line[i - 1] == 32) && (i + w == nbytes || line[i + w] == 32)) {\n            Bool hit',
     'if ((i + w == nbytes || line[i + w] == 32)) {\n            Bool hit'),
    ('the key not compared', 'src/gpt.ci', 'hit = hit && line[i + j] == key[j];', 'hit = hit;'),
    ('the GUID compared on 15 bytes', 'src/gpt.ci',
     '            for j in 0..16 {\n                hit = hit && g[j] == uid[j];',
     '            for j in 0..15 {\n                hit = hit && g[j] == uid[j];'),
    ("an entry's GUID taken from its type", 'src/gpt.ci', 'uid[k] = b[at + 16 + k];', 'uid[k] = b[at + k];'),
]


def main():
    if len(sys.argv) != 2:
        sys.exit('usage: tests/hw/mutants.py OUT')
    out = pathlib.Path(sys.argv[1])
    if out.exists():
        sys.exit('OUT exists: %s' % out)
    tc = os.environ.get('CINT_TOOLCHAIN')
    caught = 0
    for n, (name, rel, text, repl) in enumerate(MUTANTS):
        root = out / ('m%02d' % n)
        shutil.copytree(TREE / 'src', root / 'src', ignore=shutil.ignore_patterns('*.c', '*.h'))
        shutil.copytree(TREE / 'tests' / 'hw', root / 'tests' / 'hw', ignore=shutil.ignore_patterns('*.py', '*.c'))
        f = root / rel
        body = f.read_text()
        if body.count(text) != 1:
            sys.exit('mutant %r: its text occurs %d times in %s' % (name, body.count(text), rel))
        f.write_text(body.replace(text, repl))
        cmd = ['cint', 'test'] + (['--toolchain', tc] if tc else []) + ['--cache', str(out / 'cache'), '--root', '.',
                                                                     'tests/hw/gpt_test.ci']
        r = subprocess.run(cmd, cwd=root, capture_output=True, text=True)
        (out / ('m%02d.log' % n)).write_text(r.stdout + r.stderr)
        last = (r.stdout.strip().splitlines() or [''])[-1]
        if r.returncode != 0 and 'tests passed' in last:
            verdict = 'CAUGHT'
            caught += 1
        elif r.returncode == 0:
            verdict = 'MISSED'
        else:
            verdict = 'BROKEN'
        print('%-7s %s (%s)' % (verdict, name, last or 'no result line'))
    print('%d of %d mutants caught' % (caught, len(MUTANTS)))
    return 0 if caught == len(MUTANTS) else 1


if __name__ == '__main__':
    sys.exit(main())
# SPDX-License-Identifier: Apache-2.0
