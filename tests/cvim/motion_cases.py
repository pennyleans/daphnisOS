"""Additional motion cases; the original 501 records remain immutable."""
CASES = []
def case(name, text, script):
    CASES.append(dict(id=name, group='motion-review', text=text, keys=script))

for mode in ['i', 'R']:
    for direction, start in [('Down', ''), ('Up', 'G')]:
        base = start + 'll' + mode + '<' + direction + '><' + direction + '>'
        for suffix, script in [('goal', 'X<Esc>'), ('undo', 'X<Esc>u'),
                               ('redo', 'X<Esc>u<C-r>')]:
            case(mode+direction+suffix, 'abcdef\nx\nabcdef\n', base+script)
    for reset in ['<Left>', '<Right>', '<Home>', '<End>', 'Z', '<BS>', '<Del>']:
        case(mode+'reset'+reset, 'abcdef\nx\nabcdef\n', 'll'+mode+'<Down>'+reset+'<Down>X<Esc>')
    case(mode+'groups', 'abcdef\nx\nabcdef\n', 'll'+mode+'Q<Down><Down>X<Esc>u')
    case(mode+'groups2', 'abcdef\nx\nabcdef\n', 'll'+mode+'Q<Down><Down>X<Esc>uu')

for slashes in range(1, 5):
    for pair in ['()', '[]', '{}']:
        text = 'a '+pair[0]+'b'+'\\'*slashes+pair[1]+'c'+pair[1]+' z\n'
        for script in ['%', 'd%', 'c%X<Esc>', 'y%', '$%']:
            case('escape'+str(slashes)+pair+script, text, script)
for script in ['1%', '25%', '33%', '50%', '67%', '99%', '100%', '101%', '999%',
               '0%', 'd50%', '50d%', '2d25%', 'd101%', '101d%', 'y50%',
               'c50%X<Esc>', '>50%', '<50%', 'G50%', 'Gd50%', 'd50%u',
               '101%x', 'd101%x', '101d%x']:
    case('count'+script, '  a\n b\n   c\nd\ne\n', script)

EXCEPTIONS = [dict(id='wide_vertical', group='unicode-policy', text='a文z\nabcdef\n', keys='llj',
                   cvim=dict(text='a文z\nabcdef\n', cursor=[2,3], mode=0, register=['v','']))]
