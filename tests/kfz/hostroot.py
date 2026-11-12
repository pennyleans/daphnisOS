#!/usr/bin/env python3
# tests/kfz/hostroot.py: the hosted kernel of the fault and fuzz tests. Builds, under OUT, a copy of src/ in which
# src/proc.ci and every module it imports run under `cint test` as they are, but for each extern declaration, which
# becomes a function: the one tests/kfz/machine.ci or tests/kfz/xhc.ci (the USB controller) gives for it (named
# <module>_<name>), or a default that returns 0 and writes zeros. Then src/proc.ci imports both, and every module of
# src/ the tests name, after its own imports, and the test files tests/kfz/k*.ci are appended to it in name order, so
# their tests run inside the kernel's own module: they call syscall(pid), the dispatcher the scheduler calls, and read
# the process table it keeps. No kernel line changes.
# With --defects, tests/kfz/defects/*.ci follow them: cases that fail at this base, each a finding on the board.
# With --lazy, k0_kit.ci's KZ_LAZY is true: a test process's pages stay promises until touched (k0_kit.ci's header).
#   python3 tests/kfz/hostroot.py [--defects] [--lazy] OUT     (OUT must not exist; tests/kfz/run.sh runs it)
import pathlib
import re
import shutil
import sys

HERE = pathlib.Path(__file__).resolve().parent
TREE = HERE.parent.parent
MACHINES = ['machine', 'xhc']        # tests/kfz/<name>.ci, imported as tests.kfz.<name>
EXTERN = re.compile(r'^(export\s+)?extern\s+(observe|unrestricted)\s+(\w+)\s+(\w+)\s*\(([^)]*)\)\s*;', re.M | re.S)
MACHINE_FN = re.compile(r'^export\s+\w+\s+(\w+)\s*\(', re.M)
IMPORT = re.compile(r'^import ([\w.]+);', re.M)


def closure(top):
    seen, todo = [], [top]
    while todo:
        m = todo.pop()
        if m in seen:
            continue
        seen.append(m)
        text = (TREE / (m.replace('.', '/') + '.ci')).read_text()
        todo.extend(i for i in IMPORT.findall(text) if i.startswith('src.'))
    return seen


# (mode, type, name) of each parameter; the names become a0, a1, ... (an extern may name one `len`, which a function
# may not).
def params(text):
    out = []
    for i, p in enumerate(x.strip() for x in text.split(',') if x.strip()):
        words = p.split()
        mode = words[0] if words[0] in ('in', 'out', 'inout') else ''
        out.append((mode, ' '.join(words[1 if mode else 0:-1]), 'a%d' % i))
    return out


def body(mod, name, ret, ps, given):
    args = ', '.join(n for _, _, n in ps)
    if mod + '_' + name in given:
        call = '%s.%s_%s(%s);' % (given[mod + '_' + name], mod, name, args)
        return call if ret == 'void' else 'return ' + call
    lines = []
    for mode, ty, n in ps:
        if mode == 'out':
            lines.append('for k in 0..len(%s) { %s[k] = 0; }' % (n, n))
        elif mode:
            lines.append('_ = len(%s);' % n)
        else:
            lines.append('_ = %s;' % n)
    if ret != 'void':
        lines.append('return 0 as %s;' % ret)
    return ' '.join(lines)


def rewrite(mod, text, given, used):
    before = set(used)

    def one(m):
        ex, _, ret, name, plist = m.groups()
        ps = params(plist)
        sig = ', '.join(('inout ' if mode == 'out' else mode + ' ' if mode else '') + ty + ' ' + n
                        for mode, ty, n in ps)
        used.add(mod + '_' + name)
        return '%s%s %s(%s) { %s }' % (ex or '', ret, name, sig, body(mod, name, ret, ps, given))
    text, n = EXTERN.subn(one, text)
    return text, n, sorted({given[f] for f in used - before if f in given})


LAZY_OFF = 'const Bool KZ_LAZY = false;'


def main():
    args = sys.argv[1:]
    defects = '--defects' in args
    lazy = '--lazy' in args
    args = [a for a in args if a not in ('--defects', '--lazy')]
    if len(args) != 1:
        sys.exit('usage: hostroot.py [--defects] [--lazy] OUT')
    out = pathlib.Path(args[0])
    if out.exists():
        sys.exit('hostroot.py: %s exists' % out)
    (out / 'src').mkdir(parents=True)
    (out / 'tests' / 'kfz').mkdir(parents=True)
    given = {}
    for m in MACHINES:
        shutil.copy(HERE / (m + '.ci'), out / 'tests' / 'kfz' / (m + '.ci'))
        for f in MACHINE_FN.findall((HERE / (m + '.ci')).read_text()):
            if f in given:
                sys.exit('hostroot.py: %s is given twice' % f)
            given[f] = m
    used = set()
    total = 0
    tests = []
    mods = [m.split('.')[1] for m in closure('src.proc')]
    for name in mods:
        text = (TREE / 'src' / (name + '.ci')).read_text()
        text, n, delegated = rewrite(name, text, given, used)
        total += n
        if re.search(r'\bextern\b', re.sub(r'//.*', '', text)):
            sys.exit('hostroot.py: src/%s.ci keeps an extern this tool does not read' % name)
        if name == 'proc':
            tests = sorted(HERE.glob('k*.ci')) + (sorted((HERE / 'defects').glob('*.ci')) if defects else [])
            if not tests:
                sys.exit('hostroot.py: no tests/kfz/k*.ci')
            said = '\n'.join(t.read_text() for t in tests)
            have = set(IMPORT.findall(text))
            named = ['src.' + m for m in mods if m != 'proc' and 'src.' + m not in have
                     and re.search(r'\b%s\.' % m, said)]
            text = add_import(text, ['tests.kfz.' + m for m in MACHINES] + named)
            for t in tests:
                body = t.read_text()
                if lazy and t.name == 'k0_kit.ci':
                    if body.count(LAZY_OFF) != 1:
                        sys.exit('hostroot.py: k0_kit.ci does not say %r once' % LAZY_OFF)
                    body = body.replace(LAZY_OFF, LAZY_OFF.replace('false', 'true'))
                text += '\n// ---- %s, appended by tests/kfz/hostroot.py ----\n' % t.relative_to(TREE) + body
        elif delegated:
            text = add_import(text, ['tests.kfz.' + m for m in delegated])
        (out / 'src' / (name + '.ci')).write_text(text)
    hw = [g for g in given if not g.startswith('kfz_') and g not in used]
    if hw:
        sys.exit('hostroot.py: tests/kfz gives %s, which no extern names' % ', '.join(sorted(hw)))
    print('hostroot: %d modules, %d externs made functions (%d by tests/kfz), %d test files'
          % (len(mods), total, len(set(given) & used), len(tests)))


def add_import(text, names):
    lines = ''.join('import %s;\n' % n for n in names)
    found = list(IMPORT.finditer(text))
    if found:
        return text[:found[-1].end()] + '\n' + lines.rstrip('\n') + text[found[-1].end():]
    head = re.match(r'(//[^\n]*\n)*', text).end()
    return text[:head] + lines + text[head:]


if __name__ == '__main__':
    main()
