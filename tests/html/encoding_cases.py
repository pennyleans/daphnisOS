"""Independent expected values from pinned tables and explicit standard vectors."""
import json
import struct


def cases(root):
    enc = [e for g in json.loads((root / 'vendor/whatwg-encoding/encodings.json').read_bytes()) for e in g['encodings']]
    indexes = json.loads((root / 'vendor/whatwg-encoding/indexes.json').read_bytes())
    ids = {e['name'].lower(): i + 1 for i, e in enumerate(enc)}
    rows = []

    def add(name, data, points, faults=0, group='explicit', fatal=False, bom=False, split=None, width=None, stride=1, label=None, terminal=-1, position=None):
        ident = ids[name.lower()] if isinstance(name, str) else name
        data = bytes(data)
        label = (label if label is not None else enc[ident - 1]['labels'][0] if ident else '').encode('ascii')
        expected_label = next((i + 1 for i, e in enumerate(enc) if label.decode('ascii').strip(' \t\n\r\f').lower() in e['labels']), 0)
        rows.append(dict(id=ident, data=data, points=list(points), faults=faults, group=group, fatal=fatal, bom=bom,
                         split=len(data) if split is None else split, width=max(1, len(data)) if width is None else width,
                         stride=stride, label=label, expected=(expected_label, terminal, faults, len(data) if position is None else position, *points)))

    for i, e in enumerate(enc, 1):
        for label in e['labels']:
            for decorated in [label, ' \t' + label.upper() + '\r\n\f']:
                add(i, [], [], group='alias', label=decorated)
            for invalid in [label + '\0', label + '\0suffix', '\0' + label, label[:len(label) // 2] + '\0' + label[len(label) // 2:], ' \t' + label.upper() + '\0 \r\n']:
                add(0, [], [], group='alias-nul', label=invalid, terminal=-2)
    for invalid in ['', 'utf8x', '\vutf-8', 'utf-8\v', 'utf-7', 'iso-8859-1x', 'utf-8\0', 'utf-8\0x', '\0utf-8', ' UTF-8\0 ']:
        add(0, [], [], group='invalid-label', label=invalid, terminal=-2)
    for invalid_id in [41, 4294967295]:
        add(invalid_id, [], [], group='invalid-reset', label='', terminal=-2)
    for i, e in enumerate(enc[1:29], 2):
        table = indexes['iso-8859-8' if i == 10 else e['name'].lower()]
        for b in range(256):
            cp = b if b < 128 else table[b - 128]
            add(i, [b], [65533 if cp is None else cp], int(cp is None), group='single-byte')
            if cp is None:
                add(i, [b], [], 1, group='single-byte-fatal', fatal=True, terminal=-2)
    for b in range(256):
        add('x-user-defined', [b], [b if b < 128 else 0xf780 + b - 128], group='user-defined')

    for table_name in ['gb18030', 'big5', 'jis0208', 'jis0212', 'euc-kr']:
        for pointer, cp in enumerate(indexes[table_name]):
            if cp is None: continue
            if table_name == 'gb18030':
                lead, trail = divmod(pointer, 190); trail += 0x40 if trail < 63 else 0x41
                for name in ['GBK', 'gb18030']: add(name, [lead + 129, trail], [cp], group='mapped-' + name)
            elif table_name == 'big5':
                lead, trail = divmod(pointer, 157); trail += 64 if trail < 63 else 98
                add('Big5', [lead + 129, trail], [cp], group='mapped-big5')
            elif table_name == 'jis0208':
                if pointer < 8836:
                    lead, trail = divmod(pointer, 94)
                    add('EUC-JP', [lead + 161, trail + 161], [cp], group='mapped-euc-jp')
                    add('ISO-2022-JP', [27, 36, 66, lead + 33, trail + 33], [cp], group='mapped-iso2022jp')
                lead, trail = divmod(pointer, 188); lead += 129 if lead < 31 else 193; trail += 64 if trail < 63 else 65
                if lead <= 252:
                    add('Shift_JIS', [lead, trail], [0xe000 + pointer - 8836 if 8836 <= pointer <= 10715 else cp], group='mapped-shiftjis')
            elif table_name == 'jis0212':
                lead, trail = divmod(pointer, 94)
                add('EUC-JP', [143, lead + 161, trail + 161], [cp], group='mapped-jis0212')
            else:
                lead, trail = divmod(pointer, 190)
                add('EUC-KR', [lead + 129, trail + 65], [cp], group='mapped-euckr')
    for table_name in ['big5', 'jis0208', 'jis0212', 'euc-kr']:
        for pointer, cp in enumerate(indexes[table_name]):
            if cp is not None: continue
            if table_name == 'big5':
                if pointer in [1133, 1135, 1164, 1166]: continue
                lead, trail = divmod(pointer, 157); trail += 64 if trail < 63 else 98
                add('Big5', [lead + 129, trail], [65533] + ([trail] if trail < 128 else []), 1, group='null-big5')
            elif table_name == 'jis0208':
                if pointer < 8836:
                    lead, trail = divmod(pointer, 94)
                    add('EUC-JP', [lead + 161, trail + 161], [65533], 1, group='null-euc-jp')
                    add('ISO-2022-JP', [27, 36, 66, lead + 33, trail + 33], [65533], 1, group='null-iso2022jp')
                if not 8836 <= pointer <= 10715:
                    lead, trail = divmod(pointer, 188); lead += 129 if lead < 31 else 193; trail += 64 if trail < 63 else 65
                    if lead <= 252:
                        add('Shift_JIS', [lead, trail], [65533] + ([trail] if trail < 128 else []), 1, group='null-shiftjis')
            elif table_name == 'jis0212':
                lead, trail = divmod(pointer, 94)
                add('EUC-JP', [143, lead + 161, trail + 161], [65533], 1, group='null-jis0212')
            else:
                lead, trail = divmod(pointer, 190)
                add('EUC-KR', [lead + 129, trail + 65], [65533] + ([trail + 65] if trail + 65 < 128 else []), 1, group='null-euckr')
    for pointer in range(8836, 10716):
        lead, trail = divmod(pointer, 188); lead += 129 if lead < 31 else 193; trail += 64 if trail < 63 else 65
        add('Shift_JIS', [lead, trail], [0xe000 + pointer - 8836], group='shiftjis-eudc')
    ranges = indexes['gb18030-ranges']
    boundaries = {0, 7457, 39419, 39420, 188999, 189000, 1237575, 1237576, 1587599}
    for pointer, cp in ranges:
        boundaries.update([pointer - 1, pointer, pointer + 1])
    for pointer in sorted(boundaries):
        if pointer < 0: continue
        q, d = divmod(pointer, 10); q, c = divmod(q, 126); a, b = divmod(q, 10)
        if a > 125: continue
        cp = None if 39419 < pointer < 189000 or pointer > 1237575 else 0xe7c7 if pointer == 7457 else next(v + pointer - k for k, v in reversed(ranges) if k <= pointer)
        for name in ['GBK', 'gb18030']:
            add(name, [a + 129, b + 48, c + 129, d + 48], [cp] if cp is not None else [65533], int(cp is None), group='gb-ranges')

    vectors = [
        ('UTF-8', [0xe2, 0x28, 0xa1], [65533, 40, 65533], 2),
        ('UTF-8', [0xf0, 0x9f], [65533], 1),
        ('UTF-8', [194], [65533], 1),
        ('UTF-8', [224], [65533], 1),
        ('UTF-8', [224, 160], [65533], 1),
        ('UTF-8', [226], [65533], 1),
        ('UTF-8', [226, 130], [65533], 1),
        ('UTF-8', [240], [65533], 1),
        ('UTF-8', [240, 144], [65533], 1),
        ('UTF-8', [240, 144, 128], [65533], 1),

        ('UTF-8', [0xc0, 0xaf, 65], [65533, 65533, 65], 2),
        ('UTF-8', [0xed, 0xa0, 0x80], [65533] * 3, 3),
        ('UTF-8', [0xf4, 0x90, 0x80, 0x80], [65533] * 4, 4),
        ('UTF-16LE', [0, 0xd8, 65, 0], [65533, 65], 1),
        ('UTF-16LE', [0, 0xd8, 0], [65533], 1),
        ('UTF-16LE', [0, 0xdc, 65, 0], [65533, 65], 1),
        ('UTF-16LE', [0, 0xd8, 0, 0xdc], [65536], 0),
        ('UTF-16BE', [0xd8, 0, 0xdc, 0], [65536], 0),
        ('Big5', [0x88, 0x62, 0x88, 0x64, 0x88, 0xa3, 0x88, 0xa5], [202, 772, 202, 780, 234, 772, 234, 780], 0),
        ('Big5', [129, 60], [65533, 60], 1),
        ('EUC-JP', [143, 161, 60], [65533, 60], 1),
        ('EUC-JP', [142, 161, 142, 223], [65377, 65439], 0),
        ('Shift_JIS', [129, 60], [65533, 60], 1),
        ('Shift_JIS', [128, 161, 223], [128, 65377, 65439], 0),
        ('EUC-KR', [129, 60], [65533, 60], 1),
        ('gb18030', [129, 48, 60], [65533, 48, 60], 1),
        ('gb18030', [129, 48, 129, 60], [65533, 48, 65533, 60], 2),
        ('gb18030', [128], [8364], 0),
        ('ISO-2022-JP', [27], [65533], 1),
        ('ISO-2022-JP', [27, 36], [65533, 36], 1),
        ('ISO-2022-JP', [27, 36, 60], [65533, 36, 60], 1),
        ('ISO-2022-JP', [27, 40, 74, 92, 126], [165, 8254], 0),
        ('ISO-2022-JP', [27, 40, 73, 33, 95], [65377, 65439], 0),
        ('ISO-2022-JP', [27, 40, 66, 27, 40, 66, 65], [65533, 65], 1),
        ('ISO-2022-JP', [27, 36, 66, 33], [65533], 1),
        ('ISO-2022-JP', [27, 36, 66, 33, 27, 40, 66, 65], [65533, 65], 1),
        ('replacement', [65, 66], [65533], 1),
        ('replacement', [], [], 0),
    ]
    for pair, points in [([136,98], [202,772]), ([136,100], [202,780]), ([136,163], [234,772]), ([136,165], [234,780])]:
        vectors.append(('Big5', pair, points, 0))
    for name in ['Big5', 'EUC-JP', 'Shift_JIS', 'EUC-KR', 'gb18030']:
        for pending in [[129]] if name != 'EUC-JP' else [[142], [143], [143, 161], [161]]:
            vectors.append((name, pending, [65533], 1))
    for pending in [[129, 48], [129, 48, 129]]:
        vectors.append(('gb18030', pending, [65533], 1))
    for cp in [0, 127, 128, 2047, 2048, 55295, 57344, 65535, 65536, 1114111, 65533]:
        vectors.append(('UTF-8', list(chr(cp).encode('utf-8')), [cp], 0))
        for name, codec in [('UTF-16LE', 'utf-16le'), ('UTF-16BE', 'utf-16be')]:
            vectors.append((name, list(chr(cp).encode(codec)), [cp], 0))
    for name, data, points, faults in vectors:
        for split in range(len(data) + 1):
            for stride in [1, 2]:
                add(name, data, points, faults, split=split, width=1, stride=stride, group='split-explicit')
        if faults:
            # Fatal vectors start at the first offending sequence in this focused subset.
            if points and points[0] == 65533:
                add(name, data, [], 1, fatal=True, terminal=-2, position=None, group='fatal-explicit')
                first = {
                    ('UTF-8', (0xe2, 0x28, 0xa1)): 2, ('UTF-8', (0xc0, 0xaf, 65)): 1,
                    ('UTF-8', (0xed, 0xa0, 0x80)): 2, ('UTF-8', (0xf4, 0x90, 0x80, 0x80)): 2,
                    ('UTF-16LE', (0, 0xdc, 65, 0)): 2,
                    ('gb18030', (129, 48, 129, 60)): 4,
                    ('ISO-2022-JP', (27, 40, 66, 27, 40, 66, 65)): 6,
                    ('ISO-2022-JP', (27, 36, 66, 33, 27, 40, 66, 65)): 5,
                    ('replacement', (65, 66)): 1,
                }.get((name, tuple(data)), len(data))
                rows[-1]['expected'] = (rows[-1]['expected'][0], -2, 1, first)
    for name, bom_bytes, body in [('UTF-8', [239,187,191], [65]), ('UTF-16LE', [255,254], [65,0]), ('UTF-16BE', [254,255], [0,65])]:
        data = bom_bytes + body + bom_bytes
        for keep in [False, True]:
            for split in range(len(data) + 1):
                add(name, data, ([65279] if keep else []) + [65,65279], split=split, width=1, bom=keep, group='bom')
    for width in [1, 3, 7, 64, 4096, 65536]:
        data = ('<p>日本語 Ελληνικά 한국어 中文 😀</p>' * 400).encode('utf-8')
        add('UTF-8', data, list(map(ord, '<p>日本語 Ελληνικά 한국어 中文 😀</p>' * 400)), split=0, width=width, group='long')
    for row in list(rows):
        if row['group'] == 'fatal-explicit':
            for split in range(len(row['data']) + 1):
                copy = dict(row, split=split, width=1, stride=2, group='split-fatal')
                rows.append(copy)
    for fixture in json.loads((root / 'tests/html/corpus/encoding/wpt-cases.json').read_bytes()):
        for split in range(len(fixture['data']) + 1):
            add(fixture['encoding'], fixture['data'], fixture['points'], fixture['faults'],
                split=split, width=1, stride=2, group='wpt-' + fixture['source'])
            rows[-1]['wpt_case'] = fixture['case']
    return rows


def write_fixture(rows, path):
    with path.open('wb') as f:
        for r in rows:
            assert len(r['data']) <= 65536 and len(r['label']) <= 256
            assert r['stride'] in [1,2] and 0 <= r['split'] <= len(r['data']) and r['width'] > 0
            f.write(struct.pack('<8I', len(r['data']), len(r['label']), r['id'], r['fatal'], r['bom'], r['split'], r['width'], r['stride']))
            f.write(r['label']); f.write(r['data'])
