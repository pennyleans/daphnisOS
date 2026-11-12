"""Explicit contract and capacity expectations, independent of token production."""


def rows():
    result = []

    def add(identity, text, want=None, **kw):
        result.append(dict(id='adversarial:' + identity, input=text, want=want or [], **kw))

    add('invalid-mode', '', refusal=1, mode=6)
    add('invalid-negative-mode', '', refusal=1, mode=-1)
    add('last-tag-exact', '', [], last='a' * 1024)
    add('last-tag-over', '', refusal=2, last='a' * 1025)
    for n in [1024, 1025]:
        add(f'tag-name-{n}', '<' + 'a' * n + '>', [['StartTag', 'a' * n, {}]], **({'refusal': 2} if n > 1024 else {}))
        add(f'doctype-name-{n}', '<!DOCTYPE ' + 'a' * n + '>', [['DOCTYPE', 'a' * n, None, None, True]], **({'refusal': 2} if n > 1024 else {}))
        add(f'pi-target-{n}', '<?' + 'a' * n + '>', [['ProcessingInstruction', 'a' * n, '']], **({'refusal': 2} if n > 1024 else {}))
    for n in [65536, 65537]:
        over = {'refusal': 3} if n > 65536 else {}
        add(f'comment-{n}', '<!--' + 'x' * n + '-->', [['Comment', 'x' * n]], **over)
        add(f'bogus-comment-{n}', '<!' + 'x' * n + '>', [['Comment', 'x' * n]], **over)
        add(f'pi-data-{n}', '<?a ' + 'x' * n + '>', [['ProcessingInstruction', 'a', 'x' * n]], **over)
        for field in ['PUBLIC', 'SYSTEM']:
            public = 'x' * n if field == 'PUBLIC' else None
            system = 'x' * n if field == 'SYSTEM' else None
            add(f'{field.lower()}-id-{n}', '<!DOCTYPE h ' + field + ' "' + 'x' * n + '">',
                [['DOCTYPE', 'h', public, system, True]], **({'refusal': 6} if n > 65536 else {}))
    for n in [128, 129]:
        attrs = {f'a{i}': str(i) for i in range(n)}
        add(f'attribute-count-{n}', '<a ' + ' '.join(k + '=' + v for k, v in attrs.items()) + '>',
            [['StartTag', 'a', attrs]], **({'refusal': 4} if n > 128 else {}))
    add('attribute-arena-exact', '<a x="' + 'y' * 65535 + '">', [['StartTag', 'a', {'x': 'y' * 65535}]])
    add('attribute-arena-over', '<a x="' + 'y' * 65536 + '">', refusal=5)
    add('duplicate-first-wins', '<a X=1 x=2 X=3 y=4>', [['StartTag', 'a', {'x': '1', 'y': '4'}]], errors=2)
    add('attribute-order', '<a b=1 a=2 B=3 c=4>', [['StartTag', 'a', {'b': '1', 'a': '2', 'c': '4'}]],
        errors=1, attribute_order=[['b', 'a', 'c']])
    add('duplicate-storage-reclaimed', '<a ' + 'x="y" ' * 10000 + 'z=4>', [['StartTag', 'a', {'x': 'y', 'z': '4'}]], errors=9999)
    add('crlf-everywhere', 'a\rb\r\nc\n<a X="d\re\r\nf"><!--g\rh\r\ni-->',
        [['Character', 'a\nb\nc\n'], ['StartTag', 'a', {'x': 'd\ne\nf'}], ['Comment', 'g\nh\ni']])
    add('scalar-extension', '', [['Character', '\ufffd\ud800\udfff']], points=[1114112, 55296, 57343], errors=3)
    add('nul-data', '\0', [['Character', '\0']], errors=1)
    add('input-errors', '\x01\x7f\ufdd0\uffff', [['Character', '\x01\x7f\ufdd0\uffff']], errors=4)
    add('reference-errors', '&#0;&#xD800;&#x110000;&#128;', [['Character', '\ufffd\ufffd\ufffd\u20ac']], errors=4)
    add('doctype-missing-name', '<!DOCTYPE>', [['DOCTYPE', None, None, None, False]], errors=1)
    add('endtag-fields', '</a x=1/>', [['EndTag', 'a']], errors=1, end_fields=[{'attributes': {'x': '1/'}, 'self_closing': False}])
    add('endtag-selfclosing', '</a/>', [['EndTag', 'a']], errors=1, end_fields=[{'attributes': {}, 'self_closing': True}])
    add('cdata-admitted', '<![CDATA[a\0<&]]>z', [['Character', 'a\0<&z']], cdata=True)
    add('cdata-denied', '<![CDATA[a]]>', [['Comment', '[CDATA[a]]']], errors=1)
    add('cdata-eof', 'a]]', [['Character', 'a]]']], mode=5, errors=1)
    add('script-double-escape', '<!--<script>x</script>y--></script>z',
        [['Character', '<!--<script>x</script>y-->'], ['EndTag', 'script'], ['Character', 'z']], mode=3, last='script')
    add('script-escaped-eof', '<!--', [['Character', '<!--']], mode=3, last='script', errors=1)
    add('script-double-escaped-eof', '<!--<script>', [['Character', '<!--<script>']], mode=3, last='script', errors=1)
    add('script-escape-start-eof', '<!-', [['Character', '<!-']], mode=3, last='script', errors=0)
    add('long-chunked-data', 'x' * 131072, [['Character', 'x' * 131072]], errors=0)
    add('raw-endtag-case', 'x</TiTlE a=1>y', [['Character', 'x'], ['EndTag', 'title'], ['Character', 'y']], mode=1, last='title', errors=1)
    add('raw-inappropriate-endtag', '</titlex>&amp;', [['Character', '</titlex>&']], mode=1, last='title')
    for mode in [1, 2, 3]:
        for last in ['a-b', 'a1', 'a_b', 'aé']:
            text = '</' + last + '><b>'
            add(f'raw-nonalpha-{mode}-{last}', text, [['Character', text]], mode=mode, last=last)
    add('plaintext', '<a>&amp;\0', [['Character', '<a>&amp;\ufffd']], mode=4, errors=1)
    add('pi-nul-data', '<?x \0?>', [['ProcessingInstruction', 'x', '\0']], errors=0)
    add('pi-open-eof', '<?', [], errors=1)
    add('pi-target-eof', '<?x', [], errors=1)
    add('pi-data-eof', '<?x data', [], errors=1)
    add('pi-question-eof', '<?x data?', [], errors=1)
    add('pi-invalid-nul-target', '<?a\0>', [['Comment', '?a\ufffd']], errors=2)
    add('select-rcdata', '<title>a<b>&amp;</title><i>',
        [['StartTag', 'title', {}], ['Character', 'a<b>&'], ['EndTag', 'title'], ['StartTag', 'i', {}]],
        select=[[1, 1, 0, 1]], errors=0)
    add('select-script', '<script><!--<script>x</script>y--></script><b>',
        [['StartTag', 'script', {}], ['Character', '<!--<script>x</script>y-->'], ['EndTag', 'script'], ['StartTag', 'b', {}]],
        select=[[1, 3, 0, 1]], errors=0)
    add('select-cdata-toggle', '<svg><![CDATA[x]]><g><![CDATA[y]]>',
        [['StartTag', 'svg', {}], ['Character', 'x'], ['StartTag', 'g', {}], ['Comment', '[CDATA[y]]']],
        select=[[1, 0, 1, 1], [3, 0, 0, 1]], errors=1)
    add('select-invalid', '<a>x', refusal=1, select=[[1, 6, 0, 0]], prefix=[['StartTag', 'a', {}]], errors=0)
    add('reset-clean', '<p ok=yes>reset</p>', [['StartTag', 'p', {'ok': 'yes'}], ['Character', 'reset'], ['EndTag', 'p']], errors=0)
    return result
