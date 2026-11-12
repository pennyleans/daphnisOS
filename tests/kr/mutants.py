#!/usr/bin/env python3
# tests/kr/mutants.py: whether tests/kr/inq_test.ci has teeth. Each mutant breaks one rule of RS-KR's input path in a
# copy of src/ and tests/kr/, never in the tree; a test of inq_test.ci must then fail. One line a mutant: CAUGHT (a test
# failed), MISSED (none did) or BROKEN (the mutant did not build, which proves nothing). Exit status 1 unless every
# mutant is caught. Not part of the gate: some seconds a mutant. The guard in inq.ci push() is not a mutant: the room
# kept for releases means a full queue is never pushed to, so no test can reach it.
#   python3 tests/kr/mutants.py OUT      (OUT must not exist; cint on PATH, CINT_TOOLCHAIN as for check.sh)
import os
import pathlib
import shutil
import subprocess
import sys

TREE = pathlib.Path(__file__).resolve().parent.parent.parent

# (name, file, text, its replacement): each text occurs once.
MUTANTS = [
    ('USB: a held key never repeats', 'src/inq.ci',
     '    I64 r = keyrep.due(now);', '    I64 r = 0;'),
    ("PS/2: the keyboard's own repeat reaches the reader", 'src/inq.ci',
     '    if (!keyrep.key(code, value, now)) {\n        return false;',
     '    if (!keyrep.key(code, value, now) && code > 255) {\n        return false;'),
    ('K-12: a dropped repeat is stamped', 'src/inq.ci',
     '    if (key(code, value, now) && value == 1) {', '    if ((key(code, value, now) || true) && value == 1) {'),
    ('a repeat as value 2, not a press', 'src/inq.ci',
     '    push(EV_KEY, r, 1);', '    push(EV_KEY, r, 2);'),
    ('a modifier repeats', 'src/keyrep.ci',
     '    return code == 29 || code == 97 ||', '    return code == 97 ||'),
    ('a lock key repeats', 'src/keyrep.ci',
     '        || code == 126 || code == 58 ||', '        || code == 126 ||'),
    ('EVIOCSREP stores nothing', 'src/keyrep.ci',
     '    delay_ms = d;\n    period_ms = p;', '    delay_ms = delay_ms;\n    period_ms = period_ms;'),
    ('the period ignored after the first', 'src/keyrep.ci',
     '    I64 n = 1 + (ms - delay_ms) / period_ms;', '    I64 n = 1;'),
    ('a gone keyboard goes on repeating', 'src/keyrep.ci',
     'export void reset() {\n    held = 0;', 'export void reset() {\n    held = held;'),
    ('a press takes the places kept for releases', 'src/inq.ci',
     '!keyrep.is_down(code) && room() < KEY_ROOM', '!keyrep.is_down(code) && QUEUE - qcount < 2'),
    ('a refused press reaches keyrep, so its release comes alone', 'src/inq.ci',
     '        presses_lost += 1;', '        presses_lost += 1;\n        _ = keyrep.key(code, value, now);'),
    ('keyrep does not count a key down', 'src/keyrep.ci',
     '        ndown += 1;\n', ''),
    ('a repeat takes a release\'s place', 'src/inq.ci',
     '    if (room() < 2) {\n        return false;\n    }\n    I64 r', '    I64 r'),
    ('a mouse press takes the places kept for releases', 'src/inq.ci',
     'if (on == 1 && room() < 4) {', 'if (on == 1 && room() < 1) {'),
    ('a refused mouse press marks its button down', 'src/inq.ci',
     '        mouse_lost += 1;\n        return false;\n    }\n    buttons = buttons ^ bit;',
     '        mouse_lost += 1;\n        buttons = buttons ^ bit;\n        return false;\n    }\n    buttons = buttons ^ bit;'),
    ('a refused motion is not counted', 'src/inq.ci',
     '    if (room() < 2) {\n        mouse_lost += 1;', '    if (room() < 2) {'),
    ('the drop line leaves out the presses', 'src/inq.ci',
     'pos = put_num(presses_lost, pos, line);', 'pos = put_num(0, pos, line);'),
]


def main():
    if len(sys.argv) != 2:
        sys.exit('usage: tests/kr/mutants.py OUT')
    out = pathlib.Path(sys.argv[1])
    if out.exists():
        sys.exit('OUT exists: %s' % out)
    tc = os.environ.get('CINT_TOOLCHAIN')
    caught = 0
    for n, (name, rel, text, repl) in enumerate(MUTANTS):
        root = out / ('m%02d' % n)
        shutil.copytree(TREE / 'src', root / 'src', ignore=shutil.ignore_patterns('*.c', '*.h'))
        shutil.copytree(TREE / 'tests' / 'kr', root / 'tests' / 'kr', ignore=shutil.ignore_patterns('*.py'))
        f = root / rel
        body = f.read_text()
        if body.count(text) != 1:
            sys.exit('mutant %r: its text occurs %d times in %s' % (name, body.count(text), rel))
        f.write_text(body.replace(text, repl))
        cmd = ['cint', 'test'] + (['--toolchain', tc] if tc else []) + ['--cache', str(out / 'cache'), '--root', '.',
                                                                     'tests/kr/inq_test.ci']
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
