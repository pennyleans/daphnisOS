#!/usr/bin/env python3
"""Compile actual CINT and compare independently specified decoding expectations."""
import argparse
import hashlib
import gzip
from collections import Counter
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


PRIVATE_SOURCE_ID = '76e0457bf381168bc9b36c4a9cb3649486f52b12f1be0d8f19efeed2c077acfa'
PRIVATE_SHA256 = '96e95f6821e0a9d50668a233032bc5a921222179a5ad14b4c270d4b9464099cb'


def identity_pair(source_id, executable_sha256):
    if source_id is None and executable_sha256 is None:
        return PRIVATE_SOURCE_ID, PRIVATE_SHA256
    if source_id is None or executable_sha256 is None:
        raise ValueError('compiler source identity and executable SHA-256 must be supplied together')
    if any(re.fullmatch('[0-9a-f]{64}', value) is None for value in (source_id, executable_sha256)):
        raise ValueError('compiler identity values must be 64 lowercase hexadecimal digits')
    return source_id, executable_sha256


def compiler_identity(cint, source_id, executable_sha256):
    cint = cint.resolve(strict=True)
    observed = sha(cint)
    if observed != executable_sha256:
        raise ValueError('compiler executable identity drift')
    bootstrap_path = cint.parent / 'bootstrap.json'
    bootstrap = json.loads(bootstrap_path.read_text())
    bootstrap_source = bootstrap['identity']['compiler_source_identity']
    if bootstrap_source != source_id:
        raise ValueError('compiler bootstrap source identity drift')
    version = subprocess.check_output([str(cint), '--version'], text=True)
    matches = re.findall(r'^compiler source identity ([0-9a-f]{64})$', version, flags=re.M)
    if matches != [source_id]:
        raise ValueError('compiler version source identity drift')
    return dict(expected_source_id=source_id, expected_sha256=executable_sha256,
                observed_sha256=observed, bootstrap_source_id=bootstrap_source,
                bootstrap_sha256=sha(bootstrap_path),
                version_source_id=matches[0], version=version)


def run(cmd, log, **kwargs):
    proc = subprocess.run([str(x) for x in cmd], stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs)
    log.write_bytes(proc.stdout + proc.stderr)
    if proc.returncode:
        raise RuntimeError(f'command failed ({proc.returncode}): {cmd}\n' + proc.stderr.decode(errors='replace')[-5000:])
    return proc.stdout


def classify_oracle(root, oracle, rows):
    indexes = json.loads((root / 'vendor/whatwg-encoding/indexes.json').read_bytes())
    standard = (root / 'vendor/whatwg-encoding/encoding.bs').read_text().splitlines()
    groups = {}
    for difference in oracle['differences']:
        name = difference['encoding']; data = difference['data']; row = rows[difference['case']]
        support = {}; kind = 'unclassified'
        section = {'Big5': 'big5', 'EUC-KR': 'euc-kr', 'Shift_JIS': 'shift_jis', 'EUC-JP': 'euc-jp', 'ISO-2022-JP': 'iso-2022-jp'}.get(name)
        special_pairs = {(136,98): [202,772], (136,100): [202,780], (136,163): [234,772], (136,165): [234,780]}
        if name == 'Big5' and all(tuple(data[i:i + 2]) in special_pairs for i in range(0, len(data), 2)):
            expected = [v for i in range(0, len(data), 2) for v in special_pairs[tuple(data[i:i + 2])]]
            assert row['points'] == expected
            support = dict(rule='Big5 decoder special table: pointers 1133,1135,1164,1166 return two code points')
            kind = 'special two-scalar mapping changed'
        elif name == 'Big5' and len(data) == 2:
            pointer = (data[0] - 129) * 157 + data[1] - (64 if data[1] < 127 else 98)
            cp = indexes['big5'][pointer]
            support = dict(index='big5', pointer=pointer, pinned=cp)
            if cp is None:
                assert row['points'] == [65533] + ([data[1]] if data[1] < 128 else [])
                kind = 'null-cell accepted as private-use scalar'
            else:
                assert row['points'] == [cp]
                target = difference['actual']['points']
                kind = 'mapped HKSCS scalar changed to private-use' if any(57344 <= v <= 63743 for v in target) else 'mapped scalar changed or rejected'
        elif name == 'EUC-KR' and len(data) == 2:
            if 65 <= data[1] <= 254:
                pointer = (data[0] - 129) * 190 + data[1] - 65
                cp = indexes['euc-kr'][pointer]
                support = dict(index='euc-kr', pointer=pointer, pinned=cp)
                if cp is None:
                    assert row['points'] == [65533] + ([data[1]] if data[1] < 128 else [])
                    kind = 'null-cell error/replay differs'
                else:
                    assert row['points'] == [cp]
                    kind = 'mapped UHC pair treated differently'
            else:
                support = dict(rule='leading 0x81..0xFE; invalid trailing byte restores ASCII before error')
                kind = 'invalid-trail fatal outcome differs' if row['fatal'] else 'invalid-trail error/replay differs'
        elif name == 'Shift_JIS':
            if len(data) == 2:
                pointer = (data[0] - (129 if data[0] < 160 else 193)) * 188 + data[1] - (64 if data[1] < 127 else 65)
                assert indexes['jis0208'][pointer] is None and data[1] < 128
                assert row['points'] == [65533, data[1]]
                support = dict(index='jis0208', pointer=pointer, pinned=None, rule='null mapping restores ASCII trailing byte')
                kind = 'null-cell ASCII replay omitted'
            elif data[0] == 128:
                support = dict(rule='standalone 0x80 returns U+0080')
                kind = 'standalone 0x80 rejected'
        elif name == 'EUC-JP':
            if len(data) == 3 and data[0] == 143 and data[2] >= 161:
                pointer = (data[1] - 161) * 94 + data[2] - 161
                assert indexes['jis0212'][pointer] is None and row['points'] == [65533]
                support = dict(index='jis0212', pointer=pointer, pinned=None)
                kind = 'unassigned JIS0212 cell accepted'
            elif data == [143,161,60]:
                assert row['points'] == [65533,60]
                support = dict(rule='0x8F 0xA1 selects JIS0212; invalid trail returns one error and restores ASCII')
                kind = 'malformed JIS0212 replacement count differs'
        elif name == 'ISO-2022-JP' and data[-2:] == [27,36]:
            support = dict(rule='escape state at EOF restores leading 0x24, restores output state and returns error')
            kind = 'escape EOF restored byte omitted'
        key = name + ': ' + kind
        if key not in groups:
            line = next((i + 1 for i, text in enumerate(standard) if section and '<h4 id=' + section + '-decoder' in text), None)
            groups[key] = dict(encoding=name, classification=kind, count=0,
                               primary_section=dict(path='vendor/whatwg-encoding/encoding.bs', line=line),
                               representative=dict(difference, primary_support=support))
        groups[key]['count'] += 1
    return dict(classes=list(groups.values()), unresolved=[key for key in groups if key.endswith(': unclassified')],
                fatal_comparison='byte streaming retains output before a thrown fatal error; astral, UTF16 and fatal-prefix controls pass; four two-scalar serialization controls pass independently of Node mapping conformance',
                native_basis='all four native batches exactly equal independent primary expectations',
                primary_expectations_revised=False)


def main():
    ap = argparse.ArgumentParser()
    for name in ['out', 'cint', 'toolchain']: ap.add_argument('--' + name, type=Path, required=True)
    ap.add_argument('--skip-generation', action='store_true')
    ap.add_argument('--node', type=Path, default=Path('/mnt/c/Program Files/nodejs/node.exe'))
    ap.add_argument('--compiler-source-id')
    ap.add_argument('--compiler-sha256')
    args = ap.parse_args()
    args.cint = args.cint.resolve(strict=True)
    try:
        expected_source, expected_sha256 = identity_pair(args.compiler_source_id, args.compiler_sha256)
        identity = compiler_identity(args.cint, expected_source, expected_sha256)
    except ValueError as exc:
        ap.error(str(exc))
    root = Path(__file__).resolve().parents[2]
    out = args.out.resolve(); out.mkdir(parents=True, exist_ok=True)
    assert root != out and root not in out.parents
    if not args.skip_generation:
        run(['python3', '-B', root / 'tools/html/generate_encodings.py', '--check'], out / 'generation.log')
    spec = importlib.util.spec_from_file_location('encoding_cases', root / 'tests/html/encoding_cases.py')
    cases_module = importlib.util.module_from_spec(spec); spec.loader.exec_module(cases_module)
    rows = cases_module.cases(root)
    fixture = out / 'cases.bin'; cases_module.write_fixture(rows, fixture)
    inventory = b''.join((json.dumps(dict(case=i, group=r['group'], encoding=r['id'], data_hex=r['data'].hex(),
                label=r['label'].decode('ascii'), fatal=r['fatal'], ignore_bom=r['bom'], split=r['split'],
                width=r['width'], stride=r['stride'], expected=r['expected'], wpt_case=r.get('wpt_case')), separators=(',', ':')) + '\n').encode()
                for i, r in enumerate(rows))
    (out / 'case-inventory.jsonl.gz').write_bytes(gzip.compress(inventory, mtime=0))
    modules = ['user/ci/web/encoding_data.ci', 'user/ci/web/encoding.ci', 'tests/html/encoding_driver.ci']
    source_paths = modules + ['tools/html/generate_encodings.py', 'tools/html/check-encoding.py', 'tests/html/encoding_cases.py', 'tests/html/encoding_host.c']
    source_paths += [str(p.relative_to(root)) for directory in ['vendor/whatwg-encoding', 'tests/html/corpus/encoding'] for p in sorted((root / directory).rglob('*')) if p.is_file()]
    initial_hashes = {p: sha(root / p) for p in source_paths}
    initial_toolchain = sha(args.toolchain)
    initial_commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    initial_status = subprocess.check_output(['git', 'status', '--porcelain'], cwd=root, text=True).splitlines()
    run([args.cint, 'emit-c', '--toolchain', args.toolchain, '--root', root, '--out', out / 'emit', *modules], out / 'emit.log', cwd=root)
    emitted = out / (out / 'emit/MANIFEST.ref').read_text().split()[0]
    program = emitted / 'cint-program.c'
    entry = re.search(r'\bcg_[0-9A-Za-z_]+_run\b', program.read_text()).group()
    include = Path(next(line.split(' ', 1)[1] for line in args.toolchain.read_text().splitlines() if line.startswith('include ')))
    common = ['-std=c17', '-O2', '-Wall', '-Wextra', '-Werror', '-DCINT_RT_HELPERS_PORTABLE',
              '-DCI_FRAME_ARENA_BYTES=4194304', '-I' + str(include), '-I' + str(root / 'user/ci')]
    receipt = {'case_inventory_sha256': sha(out / 'case-inventory.jsonl.gz'), 'cases': len(rows), 'groups': {g: sum(r['group'] == g for r in rows) for g in sorted({r['group'] for r in rows})}}
    env = dict(os.environ, HTML_ENCODING_INPUT=str(fixture))
    previous = None
    for cc in ['gcc', 'clang']:
        obj, binary = out / f'{cc}.o', out / f'{cc}-encoding'
        run([cc, *common, '-Dmain=cint_emitted_main', '-c', program, '-o', obj], out / f'{cc}-compile.log')
        run([cc, *common, '-DCI_RUN=' + entry, obj, *sorted(p for p in emitted.rglob('*.c') if p != program),
             root / 'user/ci/main.c', root / 'tests/html/encoding_host.c', include / 'cint_rt.c', '-o', binary], out / f'{cc}-link.log')
        for repeat in range(2):
            stdout = run([binary], out / f'{cc}-{repeat}.stdout', env=env)
            actual = [tuple(map(int, line.split())) for line in stdout.splitlines()]
            assert len(actual) == len(rows), (cc, len(actual), len(rows))
            failures = [{'index': i, 'actual': result, 'expected': row['expected'], 'group': row['group'], 'input': list(row['data'])[:80]} for i, (result, row) in enumerate(zip(actual, rows)) if result != row['expected']]
            (out / f'{cc}-{repeat}-failures.json').write_text(json.dumps(failures, indent=2) + '\n')
            assert not failures, (cc, len(failures), failures[:5])
            if previous is not None: assert stdout == previous, 'repeat/compiler output drift'
            previous = stdout
        receipt[cc] = {'passed': len(rows), 'failed': 0, 'refused': 0, 'repeats': 2,
                       'binary_sha256': sha(binary), 'binary_bytes': binary.stat().st_size,
                       'stdout_sha256': hashlib.sha256(stdout).hexdigest(),
                       'version': subprocess.check_output([cc, '--version'], text=True).splitlines()[0]}
        print(f'{cc}: {len(rows)} cases passed, 0 failed/refused, repeated twice', flush=True)
    encodings = [e for g in json.loads((root / 'vendor/whatwg-encoding/encodings.json').read_bytes()) for e in g['encodings']]
    unique = set(); oracle_rows = []
    for i, row in enumerate(rows):
        key = (row['id'], row['data'], row['fatal'], row['bom'])
        if key in unique or not 1 <= row['id'] <= 40: continue
        unique.add(key)
        oracle_rows.append(dict(case=i, encoding=encodings[row['id'] - 1]['name'], data=list(row['data']), fatal=row['fatal'],
                                bom=row['bom'], points=row['points'], terminal=row['expected'][1]))
    oracle_script = root / 'tests/html/corpus/encoding/node-oracle.js'
    oracle_stdout = run([args.node, '-e', oracle_script.read_text()], out / 'node.stdout', input=json.dumps(oracle_rows).encode())
    oracle = json.loads(oracle_stdout)
    # The native batch above established exact equality with these primary expectations.
    for difference in oracle['differences']: difference['native'] = difference['expected']
    oracle['node_executable_sha256'] = sha(args.node)
    oracle['primary_expectations_revised'] = False
    (out / 'node-oracle.json').write_text(json.dumps(oracle, indent=2) + '\n')
    classification = classify_oracle(root, oracle, rows)
    (out / 'node-classification.json').write_text(json.dumps(classification, indent=2) + '\n')
    receipt['supplemental_oracle'] = {'checked': oracle['checked'], 'skipped': len(oracle['skipped']),
                                    'disagreements': len(oracle['differences']), 'versions': oracle['versions'],
                                    'protocol_controls_passed': oracle['protocol_controls_passed'],
                                    'by_encoding': dict(Counter(d['encoding'] for d in oracle['differences'])),
                                    'executable_sha256': oracle['node_executable_sha256'], 'report_sha256': sha(out / 'node-oracle.json'), 'classification_sha256': sha(out / 'node-classification.json'),
                                    'unresolved_classes': classification['unresolved']}
    print(f"node supplemental: {oracle['checked']} checked, {len(oracle['skipped'])} unsupported, {len(oracle['differences'])} disagreements retained", flush=True)
    receipt['compiler_identity'] = identity
    assert compiler_identity(args.cint, expected_source, expected_sha256) == identity, 'compiler changed during qualification'
    assert sha(args.toolchain) == initial_toolchain, 'toolchain changed during qualification'
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip() == initial_commit, 'source commit changed during qualification'
    receipt['source_commit'] = initial_commit
    receipt['source_dirty_paths'] = initial_status
    assert {p: sha(root / p) for p in source_paths} == initial_hashes, 'source changed during qualification'
    receipt['sources_sha256'] = initial_hashes
    receipt['source_bytes'] = {p: (root / p).stat().st_size for p in modules}
    for key, path in [('cint', args.cint), ('toolchain', args.toolchain), ('bootstrap', args.cint.parent / 'bootstrap.json')]:
        receipt[key + '_sha256'] = sha(path)
    receipt['compiler_source_identity'] = json.loads((args.cint.parent / 'bootstrap.json').read_text())['identity']['compiler_source_identity']
    receipt['native_skipped'] = []
    receipt['emitted_c_bytes'] = sum(p.stat().st_size for p in emitted.rglob('*.c'))
    (out / 'encoding-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')


if __name__ == '__main__': main()
