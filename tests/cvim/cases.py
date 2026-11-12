"""CV-2a scripts. Every expected result is captured independently from pinned Vim."""
CASES = []
def add(group, name, text, script):
    CASES.append(dict(id=group + '-' + name, group=group, text=text, keys=script))
BASE = 'one two, three! four five six seven\n  alpha beta gamma\nlast word\n'
for m in ['h','j','k','l','w','b','e','W','B','E','ge','gE','0','^','$','gg','G','2G','{','}','%','<Left>','<Right>','<Up>','<Down>','<Home>','<End>']:
    for n, prefix in enumerate(['', 'jll', 'G$']):
        add('motion', str(len(CASES)), BASE if m != '%' else 'a (b [c] d) z\n', prefix + m)
for m in ['fx','Fx','tx','Tx','fx;', 'fx;,', '2fx', '2tx']:
    for prefix in ['', '$']:
        add('find', str(len(CASES)), 'axbxcxdxe\n', prefix + m)
for op in ['d','c','y','>','<']:
    for m in ['w','e','b','$','0','j','k','gg','G','fx','tx','%','}','{']:
        script = 'jll' + op + m + ('Q<Esc>' if op == 'c' else '')
        add('operator', str(len(CASES)), '  one two three\n  axbxc (q) tail\n  three four\n\nend\n', script)
    for n in ['', '2', '3']:
        add('line', op + (n or '1'), BASE, n + op + op + ('Q<Esc>' if op == 'c' else ''))
for script in ['2d3w','d3w','3dw','2y2w','2c2wZ<Esc>','2>2j','2<2j','2d2j','2dG','d2G','2dd','2yy','2ccX<Esc>']:
    add('count', str(len(CASES)), BASE * 2, script)
for cmd in ['D','C','Y','x','X','s','S','rZ','J','~','p','P']:
    for pre in ['', 'jll']:
        script = pre + ('yy' if cmd in ('p','P') else '') + cmd
        if cmd in ('C','s','S'): script += 'Z<Esc>'
        add('direct', str(len(CASES)), BASE, script)
for cmd in ['i','a','I','A','o','O','R']:
    for pre in ['', 'jll']:
        for body in ['xy<Esc>', 'ab<BS>Z<Esc>', 'x<CR>y<Esc>']:
            add('insert', str(len(CASES)), BASE, pre + cmd + body)
for script in ['3iXY<Esc>', '3aXY<Esc>', '2oXY<Esc>', '2OXY<Esc>', '2RXY<Esc>', 'i<Tab>x<Esc>', 'i<Del><Esc>', 'Rxy<BS><BS><Esc>', 'Rxy<BS>Z<Esc>', 'iXY<Left>Z<Esc>', 'iXY<Right>Z<Esc>', 'iXY<End>Z<Esc>', 'iXY<Home>Z<Esc>', 'iXY<Down>Z<Esc>', 'jA<Up>Z<Esc>', '3iXY<Left>Z<Esc>', 'i<C-[>']:
    add('insert_keys', str(len(CASES)), BASE, script)
for script in ['A<CR>x<Esc>', 'o<Esc>', 'o<CR><Esc>', 'o}<Esc>', 'o<BS>x<Esc>', 'o<Tab>x<Esc>', 'O<Esc>', 'o<CR>x<Esc>', 'ofoo<CR>}<Esc>', 'A<CR>}<Esc>']:
    add('indent', str(len(CASES)), '  if (x) {\n    y;\n  }\n', script)
for script in ['xux<C-r>', 'xuu<C-r>', 'ixy<Esc>u', 'ixy<Esc>u<C-r>', 'ix<Esc>ay<Esc>u', 'ix<Esc>ay<Esc>uu<C-r>', 'ddPu', 'ccX<Esc>u', 'oX<Esc>u', 'J u', '2dd u', 'iXY<Left>Z<Esc>u', 'Rxy<BS>Z<Esc>u']:
    add('undo', str(len(CASES)), BASE, script.replace(' ', ''))
for text in ['', '\n', 'x\n', 'éλ文\n']:
    for script in ['ix<Esc>', 'x', 'dd', 'yyP', 'Rz<Esc>', '$aQ<Esc>', 'oX<Esc>']:
        add('edge', str(len(CASES)), text, script)

# Boundary and composition cases keep the oracle useful beyond one successful command.
for script in ['yy','p','P','dd','ccX<Esc>','iX<Esc>u','yyPu','ddpu','Gdd','Gddp','GccX<Esc>','GddPu','jyyP','jyypp','jddPu','xppu','lxu<C-r>','2J','3J','10x','10X','2rX','r<CR>','2r<CR>','R<Tab>x<Esc>','Rxy<CR>Z<Esc>','Rxy<CR><BS>Z<Esc>','R<Tab><BS><Esc>']:
    add('boundary', str(len(CASES)), '  a b c\n\n last\n', script)
for source in ['abc', 'abc\ndef', 'éλ文', 'a\tb\n', '   \n', '\n\n']:
    for script in ['$', 'G', 'iX<Esc>', 'dd', 'yyP', 'A<CR>X<Esc>', 'Rxy<BS><Esc>']:
        add('file_edge', str(len(CASES)), source, script)
for m in ['h','l','0','^','w','W','b','B','e','E','ge','gE','gg','G','f,','F,','t,','T,',';',',','%','{','}','<Left>','<Right>','<Home>','<End>']:
    for cmd in ['d','c','y']:
        add('composition', str(len(CASES)), '  one, two (three)\n  four, five\n\nsix\n', '$F,'+cmd+m+('X<Esc>' if cmd=='c' else ''))
for script in ['x','llx','lllX','lrl','3~','R文<Esc>','R文<BS><Esc>','iéλ<Esc>u','fx','f文','w','e','b','ge']:
    add('utf8', str(len(CASES)), 'éλ文 x\n', script)

for text,script in [('  a{ tail{\n','f{i<CR>X<Esc>'),('  aa{\n','li<CR>X<Esc>'),('  ab{cd\n','f{a<CR>X<Esc>'),('abcde\n','Rxyz<Left><BS><Esc>'),('abcde\n','Rxyz<Left><BS>Z<Esc>'),('éİßz\n','4~'),('abc\n','2iXY<Up>Z<Esc>')]:
    add('composition', str(len(CASES)), text, script)
