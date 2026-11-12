#!/usr/bin/env python3
"""Compile the native CINT tokenizer and compare pinned external token vectors."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import struct
import subprocess

PIN = 'c5495c539ca8a79c3c5107f5f14010bcff9a35d5'
MODES = {'Data state': 0, 'RCDATA state': 1, 'RAWTEXT state': 2,
         'Script data state': 3, 'PLAINTEXT state': 4, 'CDATA section state': 5}


def run(command, **kw):
    p = subprocess.run(list(map(str, command)), stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kw)
    if p.returncode:
        raise RuntimeError(' '.join(map(str, command)) + '\n' + p.stdout.decode(errors='replace') + p.stderr.decode(errors='replace'))
    return p.stdout


def unescape(value):
    if isinstance(value, str):
        return re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m[1], 16)), value)
    if isinstance(value, list):
        return [unescape(v) for v in value]
    if isinstance(value, dict):
        return {unescape(k): unescape(v) for k, v in value.items()}
    return value


def cases(root):
    rows, skipped = [], []
    for path in sorted((root / 'tests/html/corpus/tokenizer').glob('*.test')):
        data = json.loads(path.read_text())
        assert set(data) <= {'tests', 'xmlViolationTests'}, path
        for key, tests in data.items():
            for index, t in enumerate(tests):
                t = dict(t)
                if t.get('doubleEscaped'):
                    t['input'], t['output'] = unescape(t['input']), unescape(t['output'])
                for state in t.get('initialStates', ['Data state']):
                    assert state in MODES, (path, state)
                    identity = f'{path.name}:{index}:{state}'
                    if key == 'xmlViolationTests':
                        skipped.append({'id': identity, 'reason': 'DOM infoset coercion is downstream of tokenization',
                                        'input_sha256': hashlib.sha256(t['input'].encode('utf-8', errors='surrogatepass')).hexdigest(),
                                        'expected_sha256': hashlib.sha256(json.dumps(t['output'], ensure_ascii=True, separators=(',', ':')).encode()).hexdigest()})
                        continue
                    rows.append({'id': identity, 'input': t['input'], 'mode': MODES[state],
                                 'last': t.get('lastStartTag', ''), 'cdata': False, 'want': t['output']})
    # WPT tree expectations provide independent PI/comment values. The first
    # 107 cases have a simple explicit body prefix and no tree repair.
    wpt = root / 'tests/html/corpus/wpt/processing-instructions.dat'
    for index, block in enumerate(wpt.read_bytes().decode().split('#data\n')[1:]):
        identity = f'wpt-processing-instructions:{index}'
        if index > 106:
            content, document = block.split('#document\n')
            skipped.append({'id': identity, 'reason': 'tree placement or tree-selected text mode; outside this tokenizer projection',
                            'input_sha256': hashlib.sha256(content.removesuffix('\n').encode()).hexdigest(),
                            'expected_sha256': hashlib.sha256(document.encode()).hexdigest()})
            continue
        content, document = block.split('#document\n')
        content = content.removesuffix('\n')
        assert content.startswith('<body>'), identity
        want = [['StartTag', 'body', {}]]
        for line in document.splitlines():
            node = line.lstrip('| ')
            if node in ('<html>', '<head>', '<body>'):
                continue
            if node.startswith('<?'):
                assert node.endswith('?>'), (identity, node)
                target, value = node[2:-2].split(' ', 1)
                want.append(['ProcessingInstruction', target, value])
            elif node.startswith('<!-- '):
                assert node.endswith(' -->'), (identity, node)
                want.append(['Comment', node[5:-4]])
            elif node.startswith('"'):
                want.append(['Character', json.loads(node)])
            elif node == '<span>':
                want.append(['StartTag', 'span', {}])
            else:
                assert not node, (identity, node)
        rows.append({'id': identity, 'input': content, 'mode': 0, 'want': want})
    local = root / 'tests/html/tokenizer-local.json'
    if local.exists():
        for row in json.loads(local.read_text()):
            rows.append(dict(row, id='local:' + row['id']))
    rows.extend(runpy.run_path(str(root / 'tests/html/tokenizer_adversarial.py'))['rows']())
    return rows, skipped


def protocol(rows):
    result = bytearray()
    for row in rows:
        cps = row.get('points', list(map(ord, row['input'])))
        last = list(map(ord, row.get('last', '')))
        selections = row.get('select', [])
        values = [len(cps), row.get('mode', 0), len(last), int(row.get('cdata', False)), len(selections), *last, *cps,
                  *[v for selection in selections for v in selection]]
        result.extend(struct.pack('<' + 'q' * len(values), *values))
    return result


def decode(data, rows):
    assert len(data) % 8 == 0
    values = iter(struct.unpack('<' + 'q' * (len(data) // 8), data))

    def text():
        n = next(values)
        assert 0 <= n <= 65536, n
        return ''.join(chr(next(values)) for _ in range(n))

    results = []
    for row in rows:
        tokens = []
        end_fields = []
        while True:
            k = next(values)
            if k <= 0:
                results.append((tokens, k, next(values), next(values), end_fields))
                break
            name, content = text(), text()
            attrs = {}
            for _ in range(next(values)):
                attr_name, attr_value = text(), text()
                assert attr_name not in attrs
                attrs[attr_name] = attr_value
            close, quirks, pp = next(values), next(values), next(values)
            public = text()
            sp = next(values)
            system = text()
            if k == 1:
                if tokens and tokens[-1][0] == 'Character':
                    tokens[-1][1] += content
                else:
                    tokens.append(['Character', content])
            elif k == 2:
                tokens.append(['StartTag', name, attrs] + ([True] if close else []))
            elif k == 3:
                tokens.append(['EndTag', name])
                end_fields.append({'attributes': attrs, 'self_closing': bool(close)})
            elif k == 4:
                tokens.append(['Comment', content])
            elif k == 5:
                tokens.append(['DOCTYPE', name if name else None, public if pp else None, system if sp else None, not quirks])
            elif k == 6:
                tokens.append(['ProcessingInstruction', name, content])
            else:
                raise AssertionError((row['id'], k))
    assert next(values, None) is None
    return results


def verify_corpus(corpus):
    manifest = json.loads((corpus / 'SOURCE.json').read_text())
    assert manifest['html5lib_revision'] == PIN
    actual = set()
    for path in corpus.rglob('*'):
        if not path.is_file():
            continue
        relative = path.relative_to(corpus)
        if relative == Path('SOURCE.json') or (len(relative.parts) > 1 and relative.parts[0] in {'encoding', 'sniff'}):
            continue
        actual.add(str(relative))
    assert set(manifest['files']) == actual, 'tokenizer corpus inventory drift'
    for name, expected in manifest['files'].items():
        data = (corpus / name).read_bytes()
        assert len(data) == expected['bytes'] and hashlib.sha256(data).hexdigest() == expected['sha256'], 'tokenizer fixture identity drift: ' + name
    return manifest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--cint', type=Path, required=True)
    ap.add_argument('--toolchain', type=Path, required=True)
    ap.add_argument('--reuse-emitted', action='store_true')
    ap.add_argument('--only', default='')
    args = ap.parse_args()
    root, outdir = Path(__file__).resolve().parents[2], args.out.resolve()
    assert root != outdir and root not in outdir.parents
    manifest = verify_corpus(root / 'tests/html/corpus')
    outdir.mkdir(parents=True, exist_ok=True)
    fixture = outdir / 'fixture'
    if not args.reuse_emitted:
        (fixture / 'user/ci/web').mkdir(parents=True, exist_ok=True)
        for source in (root / 'user/ci/web').glob('*.ci'):
            shutil.copyfile(source, fixture / 'user/ci/web' / source.name)
        shutil.copyfile(root / 'tests/html/tokenizer_driver.ci', fixture / 'driver.ci')
        names = ['reference_data.ci', 'reference.ci', 'tokenizer.ci']
        modules = ['user/ci/web/' + name for name in names]
        run([args.cint, 'emit-c', '--toolchain', args.toolchain.resolve(), '--root', fixture,
             '--out', outdir / 'emit', *modules, 'driver.ci'], cwd=fixture)
    emitted = outdir / (outdir / 'emit/MANIFEST.ref').read_text().split()[0]
    program = emitted / 'cint-program.c'
    entry = re.search(r'\bcg_[0-9A-Za-z_]+_run\b', program.read_text()).group()
    include = next(line.split(' ', 1)[1] for line in args.toolchain.read_text().splitlines() if line.startswith('include '))
    common = ['-std=c17', '-O2', '-Wall', '-Wextra', '-Werror', '-DCINT_RT_HELPERS_PORTABLE',
              '-DCI_FRAME_ARENA_BYTES=16777216', '-I' + include, '-I' + str(root / 'user/ci')]
    rows, skipped = cases(root)
    if args.only:
        rows = [r for r in rows if args.only in r['id']]
    assert rows, 'selection matched no cases'
    wire = protocol(rows)
    receipt = {'corpus_revision': PIN, 'wpt_revision': '45337b80082d8987761d04fd2a406dcb3c48f4c5',
               'standard_revision': manifest['standard_revision'],
               'selection': args.only or 'all', 'input_protocol_sha256': hashlib.sha256(wire).hexdigest(),
               'counts': {'executed': len(rows), 'skipped': len(skipped)}, 'skipped': skipped, 'toolchains': {},
               'case_inventory': [{'id': row['id'], 'input_sha256': hashlib.sha256(row['input'].encode('utf-8', errors='surrogatepass')).hexdigest(),
                                   'expected_sha256': hashlib.sha256(json.dumps(row.get('want'), ensure_ascii=True, separators=(',', ':')).encode()).hexdigest(),
                                   'expected_refusal': row.get('refusal')} for row in rows]}
    for cc in ['gcc', 'clang']:
        obj, binary = outdir / f'{cc}.o', outdir / f'{cc}-tokenizer'
        run([cc, *common, '-Dmain=cint_emitted_main', '-c', program, '-o', obj])
        run([cc, *common, '-DCI_RUN=' + entry, obj, *sorted(p for p in emitted.rglob('*.c') if p != program),
             root / 'user/ci/main.c', root / 'tests/html/tokenizer_host.c', Path(include) / 'cint_rt.c', '-o', binary])
        result = run([binary], input=wire, timeout=240)
        assert run([binary], input=wire, timeout=240) == result, (cc, 'repeated execution changed bytes')
        (outdir / f'{cc}-tokens.bin').write_bytes(result)
        failures, refused, passed = [], [], 0
        by_suite = {}
        for row, (tokens, k, errors, reason, end_fields) in zip(rows, decode(result, rows), strict=True):
            if row.get('refusal') is not None:
                okay = k == -1 and reason == row['refusal']
            else:
                okay = k == 0 and tokens == row['want']
            if okay and 'errors' in row:
                okay = errors == row['errors']
            if okay and 'end_fields' in row:
                okay = end_fields == row['end_fields']
            if okay and 'attribute_order' in row:
                okay = [list(t[2]) for t in tokens if t[0] == 'StartTag'] == row['attribute_order']
            if okay and 'prefix' in row:
                okay = tokens == row['prefix']
            if okay:
                passed += 1
            elif k == -1:
                refused.append({'id': row['id'], 'reason': reason})
            else:
                failures.append({'id': row['id'], 'input_sha256': hashlib.sha256(row['input'].encode('utf-8', errors='surrogatepass')).hexdigest(),
                                 'want': row.get('want'), 'got': tokens, 'errors': errors})
            suite = 'wpt' if row['id'].startswith('wpt-') else 'adversarial' if row['id'].startswith('adversarial:') else 'html5lib'
            totals = by_suite.setdefault(suite, {'total': 0, 'passed': 0, 'failed': 0, 'expected_limit_refusals': 0})
            totals['total'] += 1
            totals['passed' if okay else 'failed'] += 1
            if okay and k == -1:
                totals['expected_limit_refusals'] += 1
        summary = {'total': len(rows) + len(skipped), 'passed': passed, 'failed': len(failures), 'refused': len(refused),
                   'skipped': len(skipped), 'failures': failures, 'refusals': refused,
                   'by_suite': by_suite, 'repeated_runs': 2, 'output_sha256': hashlib.sha256(result).hexdigest(),
                   'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(), 'binary_bytes': binary.stat().st_size,
                   'cc_identity': run([cc, '--version']).decode().splitlines()[0]}
        receipt['toolchains'][cc] = summary
        print(cc, {k: summary[k] for k in ['total', 'passed', 'failed', 'refused', 'skipped']}, flush=True)
    sources = ['user/ci/web/tokenizer.ci', 'user/ci/web/reference.ci', 'user/ci/web/reference_data.ci',
               'tests/html/tokenizer_driver.ci', 'tests/html/tokenizer_host.c', 'tests/html/tokenizer_adversarial.py',
               'tests/html/corpus/SOURCE.json', 'tools/html/check-tokenizer.py', 'tests/html/test_tokenizer_inventory.py']
    receipt['sources_sha256'] = {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in sources}
    receipt['cint_sha256'] = hashlib.sha256(args.cint.read_bytes()).hexdigest()
    receipt['toolchain_sha256'] = hashlib.sha256(args.toolchain.read_bytes()).hexdigest()
    receipt['bootstrap_sha256'] = hashlib.sha256((args.cint.parent / 'bootstrap.json').read_bytes()).hexdigest()
    receipt['compiler_source_identity'] = json.loads((args.cint.parent / 'bootstrap.json').read_text())['identity']['compiler_source_identity']
    receipt['runtime_sha256'] = hashlib.sha256((Path(include) / 'cint_rt.c').read_bytes()).hexdigest()
    receipt['source_revision'] = run(['git', '-C', root, 'rev-parse', 'HEAD']).decode().strip()
    (outdir / 'tokenizer-receipt.json').write_text(json.dumps(receipt, indent=2, ensure_ascii=True) + '\n')
    if any(v['failed'] or v['refused'] for v in receipt['toolchains'].values()):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
