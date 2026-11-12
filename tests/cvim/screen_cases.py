"""CV-3 screen scripts: each is typed into cvim on a screen of rows x cols; screen.py checks every frame."""
CASES = []


def add(group, name, text, script, rows=24, cols=80, file='f.ci'):
    CASES.append(dict(id=group + '-' + name, group=group, text=text, keys=script, rows=rows, cols=cols, name=file))


CODE = ''.join('line %d\tvalue = %d;\n' % (i, i * 7) for i in range(1, 121))
SMALL = 'one two three\n  four five\n\tsix\nseven\n'
WIDE = 'x' * 50 + 'MIDDLE' + 'y' * 120 + '\nshort\n'
UNI = 'é λ 文 ✓\ncafé\n'

# The layout: buffer line, gutter, text, status line, message line, in several sizes.
for rows, cols in [(24, 80), (10, 40), (40, 120), (5, 30), (65, 238), (118, 133)]:
    add('layout', '%dx%d' % (rows, cols), SMALL, '', rows, cols)
add('layout', 'empty', '', '')
add('layout', 'no_name', SMALL, '', file='')
add('layout', 'shell', SMALL, '', file='x.sh')
add('layout', 'text', SMALL, '', file='notes')
add('layout', 'gutter_4', CODE * 10, 'G')
add('layout', 'tabs', '\ta\tb\n  \tc\n', '')
add('layout', 'utf8', UNI, '$')

# The status line: modes, [+], line:col and percent.
for name, script in [('insert', 'i'), ('replace', 'R'), ('visual', 'v'), ('vline', 'V'), ('vblock', '<C-v>'),
                     ('modified', 'x'), ('undone', 'xu'), ('redone', 'xu<C-r>'), ('col', 'jll'), ('percent', '60G'),
                     ('end', 'G$'), ('insert_esc', 'iab<Esc>'), ('o', 'oNEW<Esc>')]:
    add('status', name, CODE, script + ('<Esc>' if name in ('insert', 'replace', 'visual', 'vline', 'vblock') and False else ''))

# The message line: refusals, a full table, a recording.
for name, script in [('refusal', '?'), ('refusal_ctrl', '<C-v><Esc><C-u>' if False else 'Q'), ('refusal_g', 'g?'),
                     ('cleared', '?l'), ('recording', 'qa'), ('recording_stop', 'qaxq'), ('bell_motion', 'k')]:
    add('message', name, SMALL, script)

# Scrolling: the text rows follow the window's top line.
for name, script in [('j_bottom', '25j'), ('G', 'G'), ('gg_after_G', 'Ggg'), ('ctrl_d', '<C-d>'), ('ctrl_f', '<C-f><C-f>'),
                     ('ctrl_b', 'G<C-b>'), ('H', '50GH'), ('L', 'L'), ('insert_bottom', '20GoA<CR>B<CR>C<Esc>'),
                     ('small_window', '30G')]:
    add('scroll', name, CODE, script, *(10, 60) if name == 'small_window' else (24, 80))

# Horizontal: the text area follows the cursor's column without wrapping.
for name, script in [('right', '60l'), ('end', '$'), ('back', '$0'), ('middle', 'fM'), ('next_line', '$j'),
                     ('narrow', '40l')]:
    add('column', name, WIDE, script, *(10, 30) if name == 'narrow' else (24, 80))

# Selections: v, V and blocks, reversed.
for name, script in [('v', 'wvee'), ('v_lines', 'wvjj'), ('v_dollar', 'wv$'), ('V', 'Vj'), ('block', 'l<C-v>jjl'),
                     ('block_dollar', 'l<C-v>jj$'), ('v_back', 'jjvkk'), ('v_empty_line', 'jjvjj'), ('gv', 'vjl<Esc>Ggv')]:
    add('select', name, SMALL + '\n\nlast line\n', script)

# Frame diffing: most keys change few cells, so a frame is far smaller than a full one.
for name, script in [('typing', 'A' + 'abcdefghij' * 3 + '<Esc>'), ('motions', 'jjjkkkllllhhhh'), ('words', 'wwwwbbbb'),
                     ('undo_cycle', 'ddpuu<C-r>'), ('scroll_back', '<C-d><C-u><C-d><C-u>'), ('visual_grow', 'vllllljjj<Esc>'),
                     ('dot', 'x....'), ('macro', 'qaxjq3@a')]:
    add('diff', name, CODE, script)
