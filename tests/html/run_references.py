#!/usr/bin/env python3
"""Check actual emitted CINT against pinned data and explicit numeric vectors."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(cmd, log, **kwargs):
    p = subprocess.run([str(x) for x in cmd], stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, **kwargs)
    log.write_bytes(p.stdout + p.stderr)
    if p.returncode:
        raise RuntimeError(f'command failed ({p.returncode}): {cmd}\n' + p.stderr.decode(errors='replace')[-4000:])
    return p.stdout


def cases(root):
    table = json.loads((root / 'vendor/whatwg-html/entities.json').read_bytes())
    named = {name[1:]: row['codepoints'] for name, row in table.items()}
    records = []

    def add(text, expected, attribute=False, at=0, group='numeric'):
        points = [ord(c) for c in text] if isinstance(text, str) else text
        records.append((points, at, attribute, tuple(expected), group))

    # Expectations select complete source keys, independently of prefix-range lookup.
    for name in sorted(named):
        for suffix in ['', '!', 'a', '=', ';']:
            text = name + suffix
            matches = [text[:n] for n in range(1, len(text) + 1) if text[:n] in named]
            best = max(matches, key=len)
            cps = named[best]
            expected = (len(best), len(cps), cps[0], cps[1] if len(cps) == 2 else 0, 0 if best.endswith(';') else 2)
            for attribute in [False, True]:
                result = expected
                if attribute and not best.endswith(';') and len(text) > len(best) and (text[len(best)].isascii() and text[len(best)].isalnum() or text[len(best)] == '='):
                    result = (0, 0, 0, 0, 0)
                add(text, result, attribute, group='named')
        cps = named[name]
        add('x&' + name, (len(name), len(cps), cps[0], cps[1] if len(cps) == 2 else 0, 0 if name.endswith(';') else 2), at=2, group='offset')

    for text in sorted({name[:n] for name in named for n in range(1, len(name))}):
        matches = [key for key in named if text.startswith(key)]
        best = max(matches, key=len) if matches else None
        for attribute in [False, True]:
            expected = (0, 0, 0, 0, 0)
            if best and not (attribute and len(best) < len(text)):
                cps = named[best]
                expected = (len(best), len(cps), cps[0], cps[1] if len(cps) == 2 else 0, 2)
            add(text, expected, attribute, group='truncated-name')

    numeric = [
        ('#;', 0, 0, 1), ('#x;', 0, 0, 1), ('#Xg', 0, 0, 1), ('#', 0, 0, 1), ('#x', 0, 0, 1),
        ('#65;', 4, 65, 0), ('#65!', 3, 65, 2), ('#65', 3, 65, 2), ('#x41;', 5, 65, 0), ('#X41;', 5, 65, 0),
        ('#x41G;', 4, 65, 2), ('#00000065;', 10, 65, 0), ('#0;', 3, 65533, 4), ('#0', 2, 65533, 6),
        ('#1114111;', 9, 1114111, 32), ('#1114112;', 9, 65533, 8), ('#x10ffff;', 9, 1114111, 32),
        ('#x110000;', 9, 65533, 8), ('#xD800;', 7, 65533, 16), ('#xDFFF', 6, 65533, 18),
        ('#xD7FF;', 7, 55295, 0), ('#xE000;', 7, 57344, 0), ('#xFDD0;', 7, 64976, 32),
        ('#xFDEF;', 7, 65007, 32), ('#xFDCF;', 7, 64975, 0), ('#xFDF0;', 7, 65008, 0),
        ('#999999999999999999999999999;', 29, 65533, 8),
        ('#xFFFFFFFFFFFFFFFFFFFFFFFF;', 27, 65533, 8),
    ]
    for text, used, cp, errors in numeric:
        for attribute in [False, True]:
            add(text, (used, int(used != 0), cp, 0, errors), attribute)
    remapped = [8364,129,8218,402,8222,8230,8224,8225,710,8240,352,8249,338,141,381,143,
                144,8216,8217,8220,8221,8226,8211,8212,732,8482,353,8250,339,157,382,376]
    for cp in range(1, 161):
        text = f'#{cp};'
        control = cp <= 8 or cp == 11 or 13 <= cp <= 31 or 127 <= cp <= 159
        expected_cp = remapped[cp - 128] if 128 <= cp <= 159 else cp
        add(text, (len(text), 1, expected_cp, 0, 64 if control else 0))
    for plane in range(17):
        for low in [65534, 65535]:
            cp = plane * 65536 + low
            text = f'#{cp};'
            add(text, (len(text), 1, cp, 0, 32))
    for text, errors in [('', 0), (';', 0), (' ', 0), ('unknown;', 128), ('unknown', 0),
                         ('unknown!;', 0), ('zzzz9;', 128), ('notit;', 2), ('notin;', 0)]:
        if text == 'notit;':
            add(text, (3, 1, 172, 0, errors), group='malformed')
            add(text, (0, 0, 0, 0, 0), True, group='malformed')
        elif text == 'notin;':
            add(text, (6, 1, 8713, 0, 0), group='malformed')
        else:
            for attribute in [False, True]:
                add(text, (0, 0, 0, 0, errors), attribute, group='malformed')
    for at in [-9223372036854775808, -1, 4, 5, 9223372036854775807]:
        add('amp;', (0, 0, 0, 0, 0), at=at, group='indices')
    for cp in [0, 0xd800, 0x110000, 0xffffffff]:
        add([cp], (0, 0, 0, 0, 0), group='scalar-boundary')
        add([97, 109, 112, 59, cp], (4, 1, 38, 0, 0), group='scalar-boundary')
    for base in ['', 'x']:
        for digits, cp, errors in [('0' * 65536 + '65' if not base else '0' * 65536 + '41', 65, 0),
                                   ('9' * 65536 if not base else 'F' * 65536, 65533, 8)]:
            text = '#' + base + digits + ';'
            add(text, (len(text), 1, cp, 0, errors), group='long')
    add('z' * 65536 + ';', (0, 0, 0, 0, 128), group='long')
    return records


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--cint', type=Path, required=True)
    ap.add_argument('--toolchain', type=Path, required=True)
    args = ap.parse_args()
    root = Path(__file__).resolve().parents[2]
    out = args.out.resolve()
    assert root != out and root not in out.parents
    out.mkdir(parents=True, exist_ok=True)
    run(['python3', root / 'tools/html/generate_references.py', '--check'], out / 'generation.log')
    rows = cases(root)
    fixture = out / 'cases.bin'
    with fixture.open('wb') as stream:
        for points, at, attribute, expected, group in rows:
            stream.write(struct.pack('<IqB', len(points), at, attribute))
            stream.write(struct.pack('<' + 'I' * len(points), *points))
    (out / 'expectations.json').write_text(json.dumps([{'at': at, 'attribute': attr, 'expected': exp, 'group': group} for _, at, attr, exp, group in rows]))
    modules = ['user/ci/web/reference_data.ci', 'user/ci/web/reference.ci', 'tests/html/reference_driver.ci']
    run([args.cint, 'emit-c', '--toolchain', args.toolchain, '--root', root,
         '--out', out / 'emit', *modules], out / 'emit.log', cwd=root)
    emitted = out / (out / 'emit/MANIFEST.ref').read_text().split()[0]
    program = emitted / 'cint-program.c'
    entry = re.search(r'\bcg_[0-9A-Za-z_]+_run\b', program.read_text()).group()
    include = Path(next(line.split(' ', 1)[1] for line in args.toolchain.read_text().splitlines() if line.startswith('include ')))
    common = ['-std=c17', '-O2', '-Wall', '-Wextra', '-Werror', '-DCINT_RT_HELPERS_PORTABLE',
              '-DCI_FRAME_ARENA_BYTES=4194304', '-I' + str(include), '-I' + str(root / 'user/ci')]
    receipts = {'cases': len(rows), 'groups': {group: sum(r[4] == group for r in rows) for group in sorted({r[4] for r in rows})}}
    env = dict(os.environ, HTML_REFERENCE_INPUT=str(fixture))
    for cc in ['gcc', 'clang']:
        obj, binary = out / f'{cc}.o', out / f'{cc}-references'
        run([cc, *common, '-Dmain=cint_emitted_main', '-c', program, '-o', obj], out / f'{cc}-compile.log')
        run([cc, *common, '-DCI_RUN=' + entry, obj, *sorted(p for p in emitted.rglob('*.c') if p != program),
             root / 'user/ci/main.c', root / 'tests/html/reference_host.c', include / 'cint_rt.c', '-o', binary], out / f'{cc}-link.log')
        for repeat in range(2):
            stdout = run([binary], out / f'{cc}-{repeat}.stdout', env=env)
            actual = [tuple(map(int, line.split())) for line in stdout.splitlines()]
            assert len(actual) == len(rows), (cc, len(actual), len(rows))
            failures = [{'index': i, 'actual': result, 'expected': row[3], 'group': row[4], 'input_prefix': row[0][:80]} for i, (result, row) in enumerate(zip(actual, rows)) if result != row[3]]
            (out / f'{cc}-{repeat}-failures.json').write_text(json.dumps(failures, indent=2) + '\n')
            assert not failures, (cc, len(failures), failures[:3])
        receipts[cc] = {'passed': len(rows), 'failed': 0, 'refused': 0, 'skipped': 0, 'repeats': 2,
                        'binary_sha256': sha(binary), 'stdout_sha256': hashlib.sha256(stdout).hexdigest(),
                        'version': subprocess.check_output([cc, '--version'], text=True).splitlines()[0]}
        print(f'{cc}: {len(rows)} cases passed, 0 failed/refused/skipped, repeated twice')
    sources = modules + ['tools/html/generate_references.py', 'tests/html/run_references.py', 'tests/html/reference_host.c', 'tests/html/REFERENCES.md',
                        'vendor/whatwg-html/entities.json', 'vendor/whatwg-html/LICENSE', 'vendor/whatwg-html/SOURCE.json']
    receipts['sources_sha256'] = {p: sha(root / p) for p in sources}
    receipts['cint_sha256'] = sha(args.cint)
    receipts['toolchain_sha256'] = sha(args.toolchain)
    receipts['bootstrap_sha256'] = sha(args.cint.parent / 'bootstrap.json')
    receipts['compiler_source_identity'] = json.loads((args.cint.parent / 'bootstrap.json').read_text())['identity']['compiler_source_identity']
    receipts['emitted_c_bytes'] = sum(p.stat().st_size for p in emitted.rglob('*.c'))
    (out / 'reference-receipt.json').write_text(json.dumps(receipts, indent=2) + '\n')


if __name__ == '__main__':
    main()
