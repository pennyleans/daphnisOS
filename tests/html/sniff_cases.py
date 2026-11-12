"""Independent HTML standard vectors and unchanged html5lib original cases."""
import json
import hashlib
import struct


def labels(root):
    return {label: i for i, enc in enumerate([e for g in json.loads((root / 'vendor/whatwg-encoding/encodings.json').read_bytes()) for e in g['encodings']], 1) for label in enc['labels']}


def cases(root):
    corpus=root/'tests/html/corpus/sniff'
    manifest=json.loads((corpus/'SOURCE.json').read_text())
    expected={'SOURCE.json','PROJECTION.json'} | {original['path'] for original in manifest['files']}
    actual={str(path.relative_to(corpus)) for path in corpus.rglob('*') if path.is_file()}
    if actual!=expected:
        raise ValueError('original sniff fixture inventory drift: missing='+repr(sorted(expected-actual))+' unexpected='+repr(sorted(actual-expected)))
    for original in manifest['files']:
        data=(corpus/original['path']).read_bytes()
        if len(data)!=original['bytes'] or hashlib.sha256(data).hexdigest()!=original['sha256']:
            raise ValueError('original sniff fixture identity drift: '+original['path'])
    aliases = labels(root); rows = []; skipped = []
    def add(name, data, expected='windows-1252', source=4, transport=b'', fallback=0):
        rows.append(dict(name=name, data=data, label=transport, fallback=fallback,
                         expected=[aliases[expected], source, 0, 0]))
    add('empty', b'')
    add('valid-fallback', b'', 'euc-jp', 4, fallback=aliases['euc-jp'])
    add('invalid-fallback-negative', b'', fallback=-1)
    add('invalid-fallback-high', b'', fallback=41)
    add('transport', b'<meta charset=utf-8>', 'euc-jp', 2, b' \tEuC-JP\r\n')
    add('invalid-transport', b'<meta charset=utf-8>', 'utf-8', 3, b'bad')
    add('transport-utf16-unchanged', b'<meta charset=utf-8>', 'utf-16be', 2, b'utf-16be')
    add('transport-user-defined-unchanged', b'', 'x-user-defined', 2, b'x-user-defined')
    add('transport-replacement', b'', 'iso-2022-cn', 2, b'iso-2022-cn')
    for name, bom, enc in [('utf8', b'\xef\xbb\xbf', 'utf-8'), ('le', b'\xff\xfe', 'utf-16le'), ('be', b'\xfe\xff', 'utf-16be')]:
        add('bom-'+name, bom+b'<meta charset=euc-jp>', enc, 1, b'windows-1251')
        add('bom-only-'+name, bom, enc, 1)
    add('partial-bom', b'\xef\xbb')
    add('noninitial-bom', b' \xef\xbb\xbf<meta charset=utf-8>', 'utf-8', 3)
    vectors = [
      ('basic', b'<MeTa ChArSeT="UTF-8">', 'utf-8'),
      ('slash', b'<meta/charset=utf-8>', 'utf-8'),
      ('duplicate-charset', b'<meta charset=euc-jp charset=utf-8>', 'euc-jp'),
      ('duplicate-invalid', b'<meta charset=bad charset=utf-8>', None),
      ('invalid-then-valid', b'<meta charset=bad><meta charset=utf-8>', 'utf-8'),
      ('comment', b'<!--<meta charset=euc-jp>--><meta charset=utf-8>', 'utf-8'),
      ('short-comment', b'<!--><meta charset=utf-8>', 'utf-8'),
      ('unterminated-comment', b'<!--<meta charset=utf-8>', None),
      ('generic-quoted', b'<div title="<meta charset=euc-jp>"><meta charset=utf-8>', 'utf-8'),
      ('generic-end-quoted', b'</div title="<meta charset=euc-jp>"><meta charset=utf-8>', 'utf-8'),
      ('generic-name-slash', b'<x/<meta charset=euc-jp><meta charset=utf-8>', 'utf-8'),
      ('bogus-pi', b'<?x <meta charset=euc-jp> <meta charset=utf-8>', 'utf-8'),
      ('bogus-declaration', b'<!x <meta charset=euc-jp> <meta charset=utf-8>', 'utf-8'),
      ('content-first', b'<meta content="text/html;charset=euc-jp" http-equiv=CONTENT-TYPE>', 'euc-jp'),
      ('pragma-first', b'<meta http-equiv=content-type content="charset=euc-jp">', 'euc-jp'),
      ('no-pragma', b'<meta content="charset=euc-jp">', None),
      ('bad-pragma', b'<meta http-equiv=" content-type" content="charset=euc-jp">', None),
      ('duplicate-pragma', b'<meta http-equiv=bad http-equiv=content-type content="charset=euc-jp">', None),
      ('duplicate-content', b'<meta http-equiv=content-type content=bad content="charset=euc-jp">', None),
      ('charset-over-content', b'<meta content="charset=euc-jp" charset=utf-8>', 'utf-8'),
      ('charset-before-content', b'<meta charset=utf-8 content="charset=euc-jp">', 'utf-8'),
      ('invalid-charset-before-content', b'<meta charset=bad content="charset=euc-jp" http-equiv=content-type>', None),
      ('content-retry', b'<meta http-equiv=content-type content="charset x; charset = euc-jp">', 'euc-jp'),
      ('content-invalid-first', b'<meta http-equiv=content-type content="charset=bad;charset=euc-jp">', None),
      ('content-quotes', b'<meta http-equiv=content-type content="charset=\'euc-jp\';x">', 'euc-jp'),
      ('content-unmatched', b'<meta http-equiv=content-type content="charset=\'euc-jp">', None),
      ('quoted-angle', b'<meta x="a>b" charset=utf-8>', 'utf-8'),
      ('unquoted-slash', b'<meta charset=utf-8/>', None),
      ('equals-name', b'<meta =x charset=utf-8>', 'utf-8'),
      ('empty-name-lookalike', b'<meta=charset=utf-8>', None),
      ('meta-close-no-space', b'<meta><meta charset=utf-8>', 'utf-8'),
      ('entity-not-decoded', b'<meta charset="utf&#45;8">', None),
      ('utf16-adjust', b'<meta charset=utf-16>', 'utf-8'),
      ('utf16be-adjust', b'<meta charset=utf-16be>', 'utf-8'),
      ('user-defined-adjust', b'<meta charset=x-user-defined>', 'windows-1252'),
      ('replacement-meta', b'<meta charset=iso-2022-cn>', 'iso-2022-cn'),
      ('xml', b'<?xml encoding="euc-jp"?>', 'euc-jp'),
      ('xml-utf16', b'<?xml encoding="utf-16be"?>', 'utf-8'),
      ('xml-user-defined', b'<?xml encoding="x-user-defined"?>', 'x-user-defined'),
      ('xml-control-spaces', b'<?xml encoding\x01=\x02"euc-jp"?>', 'euc-jp'),
      ('xml-space-in-label', b'<?xml encoding=" euc-jp"?>', None),
      ('xml-case-sensitive', b'<?XML encoding="euc-jp"?>', None),
      ('xml-encoding-case', b'<?xml ENCODING="euc-jp"?>', None),
      ('xml-first-occurrence', b'<?xml encoding x encoding="euc-jp"?>', None),
      ('xml-noninitial', b' <?xml encoding="euc-jp"?>', None),
      ('xml-meta-precedence', b'<?xml encoding="euc-jp"?><meta charset=utf-8>', 'utf-8'),
      ('xml-no-close', b'<?xml encoding="euc-jp"', None),
      ('xml-unquoted', b'<?xml encoding=euc-jp>', None),
      ('xml-le-prefix', b'<\x00?\x00x\x00', 'utf-16le'),
      ('xml-be-prefix', b'\x00<\x00?\x00x', 'utf-16be'),
      ('xml-le-case-sensitive', b'<\x00?\x00X\x00', None),
    ]
    for name, data, enc in vectors: add(name, data, enc or 'windows-1252', 3 if enc else 4)
    meta=b'<meta charset=utf-8>'
    for ending in [1023, 1024, 1025]:
        add('bound-meta-end-'+str(ending), b'x'*(ending-len(meta))+meta, 'utf-8' if ending<=1024 else 'windows-1252', 3 if ending<=1024 else 4)
    xml=b'<?xml encoding="euc-jp"?>'
    for ending in [1024,1025]:
        data=b'<?xml '+b'x'*(ending-len(xml))+b'encoding="euc-jp"?>'
        add('bound-xml-end-'+str(ending),data,'euc-jp' if ending==1024 else 'windows-1252',3 if ending==1024 else 4)
    for data in [b'<' ,b'<!',b'<!--',b'<meta',b'<meta ',b'<meta charset',b'<meta charset=',b'<meta charset=utf-8',b'<meta charset="utf-8"',b'<a x="<meta charset=utf-8>']:
        add('truncated-'+data.hex(),data)
    for p in sorted(corpus/original['path'] for original in manifest['files'] if original['path'].endswith('.dat')):
        for i, block in enumerate(p.read_bytes().split(b'#data\n')[1:]):
            data, expected=block.split(b'\n#encoding\n'); label=expected.strip().lower().decode('ascii')
            name=f'html5lib/{p.name}:{i}'
            if len(data)>1024:
                skipped.append(dict(name=name, expected=label, reason='original expectation permits late-meta reparse beyond this API 1024-byte prescan; retained unchanged'))
                continue
            rows.append(dict(name=name, data=data, label=b'', fallback=0, expected=[aliases[label],None,0,0]))
    return rows, skipped


def write_fixture(rows, path, pipeline=False):
    with path.open('wb') as f:
        for r in rows:
            fields=[len(r['label']), r['fallback'] & 0xffffffff, r.get('capacity',131080),0,r.get('split',len(r['data'])),r.get('width',max(1,len(r['data']))),r.get('stride',1)]
            f.write(struct.pack('<8I',len(r['data']),*fields));f.write(r['label']);f.write(r['data'])


def pipeline_cases(root):
    aliases=labels(root); rows=[]
    def text(value): return [len(value),*map(ord,value)]
    def token(kind, name='', data='', attrs=(), closed=0):
        v=[kind,*text(name),*text(data),len(attrs)]
        for key,value in attrs: v += text(key)+text(value)
        return v+[closed,0,0,0,0,0]
    def add(name, data, transport, chars, faults=0, bom=False):
        tokens=[]
        for ch in chars: tokens+=token(1,data=ch)
        tokens+=token(2,name='p',attrs=[('title',chars)])
        tokens+=token(3,name='p')
        tokens += [0,0,0]
        for split in range(len(data)+1):
            for stride in [1,2]:
                rows.append(dict(name=name+f'/split-{split}/stride-{stride}',data=data,label=transport,fallback=0,split=split,width=1+split%5,stride=stride,capacity=131080,expected=[aliases[transport.decode()],1 if bom else 2,faults,0,*tokens]))
    add('utf8-multilingual','é日本😀<p title="é日本😀"></p>'.encode(),b'utf-8','é日本😀')
    add('utf8-bom',bytes.fromhex('efbbbf')+'é日本😀<p title="é日本😀"></p>'.encode(),b'utf-8','é日本😀',bom=True)
    add('utf16be','é日本😀<p title="é日本😀"></p>'.encode('utf-16be'),b'utf-16be','é日本😀')
    add('gbk',bytes.fromhex('d6d0b9fa')+b'<p title="'+bytes.fromhex('d6d0b9fa')+b'"></p>',b'gbk','中国')
    add('eucjp',bytes.fromhex('c6fccbdc')+b'<p title="'+bytes.fromhex('c6fccbdc')+b'"></p>',b'euc-jp','日本')
    add('euckr',bytes.fromhex('c7d1b1b9')+b'<p title="'+bytes.fromhex('c7d1b1b9')+b'"></p>',b'euc-kr','한국')
    add('windows1251',bytes.fromhex('cff0')+b'<p title="'+bytes.fromhex('cff0')+b'"></p>',b'windows-1251','Пр')
    add('shift-jis',bytes.fromhex('93fa967b')+b'<p title="'+bytes.fromhex('93fa967b')+b'"></p>',b'shift_jis','日本')
    add('big5-two',bytes.fromhex('8862')+b'<p title="'+bytes.fromhex('8862')+b'"></p>',b'big5','Ê̄')
    add('utf16le-bom',bytes.fromhex('fffe')+'é日本😀<p title="é日本😀"></p>'.encode('utf-16le'),b'utf-16le','é日本😀',bom=True)
    add('utf8-malformed-markup',b'\xe2<p title="\xe2"></p>',b'utf-8','�',2)
    add('shiftjis-malformed-markup',b'\x81<p title="\x81"></p>',b'shift_jis','�',2)
    for cap in [0,1,2,3]:
        rows.append(dict(name=f'capacity-{cap}',data=b'abcd<p>',label=b'utf-8',fallback=0,split=1,width=2,stride=1,capacity=cap,expected=[1,2,0,-4]))
    rows.append(dict(name='capacity-exact',data=b'abcd',label=b'utf-8',fallback=0,split=0,width=1,stride=2,capacity=4,expected=[1,2,0,0,*sum((token(1,data=c) for c in 'abcd'),[]),0,0,0]))
    return rows
