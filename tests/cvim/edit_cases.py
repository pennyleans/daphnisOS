"""CV-2b scripts (docs/handoff/20261108-cv2b.md section 2). Every record is captured from Vim by edit.py; none is
written by hand. Each script ends in Normal mode with nothing pending and no recording."""
CASES = []


def add(group, name, text, script):
    CASES.append(dict(id=group + '-' + name, group=group, text=text, keys=script))


# Text objects: each object after d, c and y, from a place it covers, and with counts.
WORDS = 'one two  three, four\n  five-six seven\n\nlast (word) here\n'
SENT = 'First one. Second  two!  Third? (Fourth.) Fifth\nstill fifth.\n\nPara two. More\n'
PARA = 'a b\nc d\n\n\ne f\n  g h\n\nlast\n'
BRACK = 'f(a, (b + c), d) [x [y] z] {p {q} r} <m <n> o>\n'
BLOCK = 'if (x) {\n    foo(1);\n    bar(2);\n}\n'
QUOTE = 'say "hello there" and \'it is\' or `tick` "a\\"b" end\n'
for i, (obj, text, pre) in enumerate([
        ('iw', WORDS, 'w'), ('aw', WORDS, 'w'), ('iw', WORDS, 'wwl'), ('aw', WORDS, 'wwl'), ('iW', WORDS, 'jw'),
        ('aW', WORDS, 'jw'), ('iw', WORDS, '$'), ('aw', WORDS, '$'), ('aw', WORDS, 'j'), ('iw', WORDS, 'jj'),
        ('is', SENT, 'w'), ('as', SENT, 'w'), ('is', SENT, '4w'), ('as', SENT, '4w'), ('is', SENT, 'f!l'),
        ('as', SENT, 'f?w'), ('is', SENT, 'j'), ('as', SENT, 'G'),
        ('ip', PARA, ''), ('ap', PARA, ''), ('ip', PARA, 'jj'), ('ap', PARA, 'jj'), ('ip', PARA, 'G'), ('ap', PARA, '5G'),
        ('i(', BRACK, 'fb'), ('a(', BRACK, 'fb'), ('i(', BRACK, 'fd'), ('a)', BRACK, 'fd'), ('ib', BRACK, 'f('),
        ('i[', BRACK, 'fy'), ('a[', BRACK, 'fz'), ('i]', BRACK, 'fx'), ('i{', BRACK, 'fq'), ('a{', BRACK, 'fr'),
        ('iB', BRACK, 'fp'), ('i<', BRACK, 'fn'), ('a<', BRACK, 'fo'), ('i>', BRACK, 'fm'),
        ('i{', BLOCK, 'j'), ('a{', BLOCK, 'j'), ('i(', BLOCK, 'jf1'), ('i{', BLOCK, 'G'),
        ('i"', QUOTE, 'fh'), ('a"', QUOTE, 'fh'), ('i"', QUOTE, 'f"'), ("i'", QUOTE, 'fi'), ("a'", QUOTE, 'fi'),
        ('i`', QUOTE, 'fk'), ('a`', QUOTE, 'fk'), ('i"', QUOTE, '$'), ('i"', QUOTE, ''), ('a"', QUOTE, '$F"')]):
    for op in ['d', 'c', 'y']:
        add('object', str(i) + op, text, pre + op + obj + ('X<Esc>' if op == 'c' else ''))
for script in ['d2aw', '2daw', 'c3iwX<Esc>', 'y2aw', 'd2i(', 'd2a(', 'y2is', 'd2ap', '2dip', 'd3iw', 'd2i"',
               'diwP', 'daw.', 'ciwX<Esc>w.']:
    add('object_count', script, 'one two three four five\n  six (seven (eight) nine)\n\n "q" ten\n', 'w' + script)
add('object_count', 'indent', BLOCK, 'jdi{')

# Registers.
REG = 'alpha beta\ngamma delta\nepsilon\nzeta eta\n'
for name, script in [
        ('named', '"ayy"ap'), ('named_char', '"ayiwj"aP'), ('append', '"ayyj"Ayy"ap'), ('append_char', '"ayiww"Ayiw$"ap'),
        ('append_mixed', '"ayiwj"Ayy"aP'), ('append_mixed2', '"ayyw"Ayiw"ap'), ('zero', 'yyjddk"0p'),
        ('zero_kept', 'yywdw"0P'), ('one', 'ddjdd"1p'), ('rotate', 'dddddd"1p"2p"3p'), ('rotate_dot', 'dddddd"1p..'),
        ('small', 'dwj"-P'), ('small_not_one', 'dddw"1p"-p'), ('small_x', 'xxx"-p'), ('blackhole', 'yy"_ddp'),
        ('blackhole_char', 'yiw"_dwP'), ('named_delete', '"add"ap'), ('named_delete_one', '"adddd"1p"2p'),
        ('upper_delete', '"adddd"Add"ap'), ('change_one', 'ccX<Esc>j"1p'), ('change_small', 'cwX<Esc>"-p'),
        ('count_put', '"ayiw3"ap'), ('quote_quote', 'yiw""p'), ('percent_one', 'jf(d%"1p'), ('brace_one', 'd}"1p'),
        ('x_count', '3"axj"ap'), ('Y', '"aYj"ap'), ('D', 'w"bD"bp'), ('linewise_count', '2"byyG"bp'),
        ('rotate9', 'dddddddd"1p"4p')]:
    add('register', name, REG if name not in ('percent_one',) else 'a\nb (c d) e\n', script)

# Repeat: . with counts, after Insert mode, after cw, after Visual operators.
REP = 'one two three four\nfive six seven eight\nnine ten\n'
for name, script in [
        ('x', 'x..'), ('x_count', '3x.'), ('x_newcount', '3x2.'), ('dw', 'dw..'), ('d2w', 'd2w.'), ('2d3w', '2dw.'),
        ('dd', 'dd.'), ('dd_count', '2ddu.'), ('newcount_sticks', 'x3..'), ('cw', 'cwXY<Esc>w.'), ('cw_word', 'cwX<Esc>ww.'),
        ('cw_count', 'c2wX<Esc>j0.'), ('insert', 'iab<Esc>j.'), ('insert_count', '2iab<Esc>j.'), ('insert_newcount', 'iab<Esc>j3.'),
        ('append', 'Ax<Esc>j.'), ('o', 'oNEW<Esc>.'), ('O', 'ONEW<Esc>j.'), ('A_cr', 'Ax<CR>y<Esc>j.'), ('r', 'rZl.'),
        ('r_count', '2rZw.'), ('tilde', '~~.'), ('J', 'J.'), ('p', 'yyp.'), ('P_char', 'yiwP.'), ('shift', '>>j.'),
        ('shift_count', '2>>.'), ('gU', 'gUiwj.'), ('guu', 'VjUguuj.'), ('arrow', 'ia<Left>b<Esc>j.'), ('bs', 'Rab<BS>c<Esc>j0.'),
        ('S', 'SXY<Esc>j.'), ('C', 'wCZ<Esc>j.'), ('s', 'sQ<Esc>l.'), ('undo_dot', 'dwu.'), ('yank_no_dot', 'xyy.'),
        ('visual_d', 'vld.'), ('visual_d_lines', 'vjd.'), ('visual_line', 'Vd.'), ('visual_c', 'vlcZ<Esc>w.'),
        ('visual_shift', 'Vj>.'), ('visual_tilde', 'vee~w.'), ('visual_after_move', 'vlldj0.'), ('dot_dot', 'A!<Esc>j..'),
        ('register_one_dot', 'dddd"1p.'), ('dt', 'dtsj0.'), ('df_count', 'd2fej0.')]:
    add('repeat', name, REP, script)

# Macros: record, run, @@, counts, undo one step per command.
MAC = 'a1 b2\nc3 d4\ne5 f6\ng7 h8\n'
for name, script in [
        ('simple', 'qaxjq@a'), ('count', 'qaxjq2@a'), ('atat', 'qaxjq@a@@'), ('insert', 'qaI-<Esc>jq@a'),
        ('register_text', 'qaA!<Esc>q'), ('put_macro', 'qaxq"ap'), ('stop_at_end', 'qaxjq9@a'), ('undo_steps', 'qaxxq@au'),
        ('undo_steps2', 'qaxxq@auu'), ('undo_redo', 'qaxxq@auu<C-r>'), ('append_qA', 'qaxqqAjq@a'), ('word', 'qadwjq@a'),
        ('dot_in_macro', 'xqa.jq@a'), ('macro_then_dot', 'qaxjq@a.'), ('count_word', 'qa2xjq@a'), ('change', 'qacwZ<Esc>jq@a'),
        ('recursive', 'qaqqaxj@aq@a'), ('named_b', 'qbr*jq@b@b'), ('cr', 'qaA<CR>x<Esc>q@a'),
        ('visual', 'qavldjq@a'), ('fail_stops', 'qaxjjjjq@a'), ('o_macro', 'qaoZ<Esc>q2@a'), ('esc_inside', 'qaix<Esc>lq3@a')]:
    add('macro', name, MAC, script)

add('macro', 'yank_run', 'xj\nabc\ndef\n', 'yiw@0')
add('macro', 'put_ignore', MAC, 'qaA!<Esc>q"ap')
add('macro', 'put_r', MAC, 'qar*q"ap')

# Visual mode, characterwise and linewise.
VIS = '  one two three\n  four five six\nseven\n\neight nine\n'
for name, script in [
        ('d', 'wvld'), ('d_lines', 'wvjd'), ('d_back', 'jwvkd'), ('y', 'wveey'), ('y_lines', 'wvjy'), ('c', 'wvecX<Esc>'),
        ('x', 'wvlx'), ('dollar_d', 'wv$d'), ('dollar_y', 'wv$y'), ('dollar_j_d', 'wv$jd'), ('dollar_h', 'wv$hd'),
        ('o', 'wvlloholdd' if False else 'wvllohd'), ('o2', 'wvjoly'), ('gt', 'wvj>'), ('lt', 'Vj<lt>'), ('shift_count', 'Vj2>'),
        ('tilde', 'wve~'), ('u', 'wvjeu'), ('U', 'wvjeU'), ('gU', 'wvegU'), ('J', 'vjJ'), ('J_one', 'vJ'),
        ('r', 'wvlrx'), ('r_lines', 'wvjrx'), ('V_d', 'Vd'), ('V_jd', 'Vjd'), ('V_y', 'jVjy'), ('V_c', 'VjcX<Esc>'),
        ('V_tilde', 'jV~'), ('V_r', 'Vr-'), ('V_last', 'GVkd'), ('V_X', 'wvX'), ('V_D', 'wvjD'), ('V_C', 'wvCX<Esc>'),
        ('V_S', 'wvSX<Esc>'), ('V_R', 'wvRX<Esc>'), ('V_Y', 'wvY'), ('switch', 'wvjVd'), ('switch_back', 'wVjvd'),
        ('esc', 'wvjj<Esc>x'), ('vv', 'wvlvx'), ('gv', 'wvl<Esc>0gvd'), ('gv_line', 'Vj<Esc>Ggvd'), ('iw', 'wviwd'),
        ('aw', 'wvawd'), ('ip', 'vipd'), ('i(', 'Gviwd'), ('count_motion', 'v3ld'), ('empty_line', 'jjjvd'),
        ('register', 'wve"ay"aP'), ('reg_d', 'wve"bd"bp'), ('regs_one', 'vjd"1p'), ('small', 'vld"-p'),
        ('eq', 'Vj='), ('G', 'vGd'), ('gg', 'Gvggd'), ('find', 'vfed'), ('percent', 'v%d')]:
    add('visual', name, VIS, script)

# Visual block, with lines shorter than the block and the block's Insert and Append.
BLK = 'abcdef\nab\nabcdefgh\n\nabcdef\n'
for name, script in [
        ('d', 'l<C-v>jjld'), ('y', 'l<C-v>jjly'), ('y_p_char', 'l<C-v>jly$p' if False else 'l<C-v>jlyG'), ('c', 'l<C-v>jjlcXY<Esc>'),
        ('I', 'l<C-v>jjlIXY<Esc>'), ('I_short', 'lll<C-v>jjIZ<Esc>'), ('I_edge', 'll<C-v>jjjjIZ<Esc>'), ('A', 'l<C-v>jjlAXY<Esc>'),
        ('A_short', 'llll<C-v>jjAQ<Esc>'), ('A_dollar', 'l<C-v>jj$AQ<Esc>'), ('I_undo', 'l<C-v>jjlIXY<Esc>u'),
        ('I_dot', 'l<C-v>jjlIXY<Esc>j.'), ('d_dot', 'l<C-v>jld.'), ('tilde', 'l<C-v>jjl~'), ('U', '<C-v>jjlU'), ('r', 'l<C-v>jjlr*'),
        ('o', 'l<C-v>jjloD' if False else 'l<C-v>jjlod'), ('D', 'l<C-v>jjD'), ('C', 'l<C-v>jjCZ<Esc>'), ('dollar_d', 'l<C-v>j$d'),
        ('J', '<C-v>jjJ'), ('switch', 'l<C-v>jvd'), ('X', 'l<C-v>jX'), ('gv', 'l<C-v>jl<Esc>Ggvd'), ('upwards', 'Gll<C-v>kkd'),
        ('x', 'l<C-v>jjlx'), ('reg', 'l<C-v>jl"ay'), ('s', 'l<C-v>jsZ<Esc>')]:
    add('block', name, BLK, script)

for name, script in [
        ('shift', 'l<C-v>jj>'), ('shift_count', 'l<C-v>jj2>'), ('shift_ws', 'l<C-v>jjj>'), ('unshift_none', 'll<C-v>jj<lt>'),
        ('unshift', '<C-v>jj<lt>'), ('eq', 'l<C-v>jj='), ('shift_dot', 'l<C-v>jj>.'), ('shift_undo', 'l<C-v>jj>u')]:
    add('block', name, 'abcdef\n  ab\nabcdefgh\n\nabcdef\n', script)
for name, script in [('vI', 'lvlIX<Esc>'), ('vA', 'lvjAX<Esc>'), ('VI', 'lVjIX<Esc>'), ('VA', 'lVjAX<Esc>')]:
    add('visual', name, 'abcdef\n  ab\nabcdefgh\n\nabcdef\n', script)
for name, script in [
        ('i(i(', 'fcvi(i(d'), ('a(a(', 'fcva(a(d'), ('i(a(', 'fcvi(a(d'), ('ipip', 'vipipd'), ('ipap', 'vipapd'),
        ('ipip_mid', 'jjvipipd'), ('ipip_end', 'Gvipipd'), ('apap', 'vapapd'), ('iwiwiw', 'fcviwiwiwd'),
        ('awaw', 'fcvawawd'), ('ipip_y', 'vipipy'), ('Vip', 'Vipd'), ('Vipip', 'Vipipd'), ('Vipap', 'Vipapd'),
        ('ipipip', 'vipipipd'), ('ipap_mid', 'jjvipapd'), ('vap', 'vapd'), ('i{i{', 'fcvi{d' if False else 'fdvi(i(y')]:
    add('visual', 'extend_' + name, 'a (b (c d) e) f\n\npara one\npara two\n\nthird\n', script)

# g~ gu gU and =.
CASE = 'Hello World foo\nMIXED case Line\néλ Straße\n'
for name, script in [
        ('g~w', 'g~w'), ('g~~', 'g~~'), ('g~g~', 'jg~g~'), ('guw', 'guw'), ('guu', 'jguu'), ('gugu', 'jgugu'), ('gUw', 'gUw'),
        ('gUU', 'gUU'), ('gUgU', 'gUgU'), ('g~iw', 'wg~iw'), ('gUj', 'gUj'), ('guk', 'jguk'), ('gU$', 'wgU$'), ('g~2w', 'g~2w'),
        ('2g~~', '2g~~'), ('gUG', 'gUG'), ('gu_count', 'j3guu'), ('unicode_gU', 'GgUU'), ('unicode_gu', 'GgUUguu'),
        ('unicode_g~', 'Gg~~'), ('gU_dot', 'gUiww.'), ('g~_undo', 'g~~u')]:
    add('case', name, CASE, script)
CODE = 'int f() {\nint a;\n  if (a) {\nb();\n      }\n        return a;\n}\n\nint g() {\n    x;\n}\n'
for name, script in [
        ('eq_all', 'gg=G'), ('eq_line', 'j=='), ('eq_count', 'j3=='), ('eq_j', 'jj=j'), ('eq_ip', '=ip'), ('eq_block', 'jj=i{'),
        ('eq_close', '4j=='), ('eq_V', 'Vjjj='), ('eq_dot', 'j==j.'), ('eq_blank', '7j==u=G'), ('eq_last', 'G=gg')]:
    add('indent', name, CODE, script)

# H M L and the scroll keys, with the window 23 rows and 'scrolloff' 4.
LONG = ''.join('line %d%s\n' % (i, '' if i % 7 else ' x') for i in range(1, 61))
SHORT = 'a\n b\nc\n'
for name, text, script in [
        ('H', LONG, 'H'), ('L', LONG, 'L'), ('M', LONG, 'M'), ('H_count', LONG, '3H'), ('L_count', LONG, '3L'),
        ('H_scrolled', LONG, '30GH'), ('L_scrolled', LONG, '30GL'), ('M_scrolled', LONG, 'GM'), ('dL', LONG, 'dL'),
        ('dH', LONG, '10GdH'), ('yM', LONG, 'yMP'), ('H_short', SHORT, 'GH'), ('L_short', SHORT, 'L'), ('M_short', SHORT, 'M'),
        ('cd', LONG, '<C-d>'), ('cd2', LONG, '<C-d><C-d>'), ('cd_count', LONG, '5<C-d>'), ('cd_count_sticks', LONG, '5<C-d><C-d>'),
        ('cu', LONG, 'G<C-u>'), ('cu_count', LONG, 'G3<C-u>'), ('cd_end', LONG, 'G<C-d>'), ('cu_top', LONG, '<C-u>'),
        ('cf', LONG, '<C-f>'), ('cf2', LONG, '<C-f><C-f>'), ('cf_count', LONG, '2<C-f>'), ('cb', LONG, 'G<C-b>'),
        ('cf_cb', LONG, '<C-f><C-b>'), ('cb_top', LONG, '<C-b>'), ('cf_end', LONG, '<C-f><C-f><C-f><C-f>'),
        ('jump_mid', LONG, '35G'), ('jump_far', LONG, '40G'), ('jump_end', LONG, 'G'), ('jump_back', LONG, 'G20G'),
        ('jump_back_near', LONG, '45G35G'), ('step_down', LONG, '30j'), ('step_up', LONG, 'G30k'), ('cd_x', LONG, '<C-d>x'),
        ('visual_cd', LONG, 'v<C-d>d'), ('dd_bottom', LONG, 'Gdd'), ('o_bottom', LONG, '22GoX<Esc>'), ('cd_short', SHORT, '<C-d>'),
        ('H_dd', LONG, 'Hdd'), ('L_visual', LONG, 'VLd')]:
    add('scroll', name, text, script)

# Marks: m{a-z}, ` and '.
MARK = 'one two three\n  four five\nsix seven\neight\n'
for name, script in [
        ('back', 'wmajj`a'), ('quote', 'wwmajj\'a'), ('d_back', 'wmajjd`a'), ('d_quote', 'wmajd\'a'), ('y_back', 'jwmaggy`aP'),
        ('c_back', 'wwmabbc`aX<Esc>'), ('two', 'majjmb`a`b'), ('unset', '`a'), ('above_line', 'jjmaggOZ<Esc>`a'),
        ('above_dd', 'jjmaggdd\'a'), ('deleted', 'jmadd`ax'), ('join', 'jwmakJ`a'), ('V_mark', 'mbjjV\'bd'), ('dot', 'wmajd`a.'),
        ('upper_line', 'jmakdd`a')]:
    add('mark', name, MARK, script)

# CV-4b: the command line in the core (ex.ci): ranges, :s and its flags and replacement, :& and :&&, :g, :g!, :v,
# :d, :N, Visual :, and undo of a whole command. Captured from the pinned Vim by edit.py --freeze (Arch); until then
# the records are pending (edit.py runs the replay and says so).
EXF = 'alpha beta\nBeta gamma\n  delta alpha\nepsilon\nalpha\n'
NUMS = '1\n2\n3\n4\n5\n6\n'
for name, text, script in [
        ('s_first', EXF, ':s/a/X/<CR>'), ('s_g', EXF, ':s/a/X/g<CR>'), ('s_all', EXF, ':%s/alpha/A/g<CR>'),
        ('s_range', EXF, ':2,4s/a/_/g<CR>'), ('s_dot_plus', EXF, 'j:.,+2s/^/> /<CR>'), ('s_dollar', EXF, ':$s/a/Z/<CR>'),
        ('s_semicolon', EXF, ':2;+1s/e/E/g<CR>'), ('s_count', EXF, ':s/a/@/g 3<CR>'), ('s_zero', EXF, ':0s/l/L/<CR>'),
        ('s_groups', EXF, ':%s/\\(\\w\\+\\) \\(\\w\\+\\)/\\2 \\1/<CR>'), ('s_amp', EXF, ':s/beta/[&]/<CR>'),
        ('s_amp_lit', EXF, ':s/beta/\\&/<CR>'), ('s_split', EXF, ':s/ /\\r/<CR>'), ('s_join_none', EXF, ':s/xyz/q/<CR>'),
        ('s_upper_one', EXF, ':%s/\\w\\+/\\u&/g<CR>'), ('s_upper_all', EXF, ':s/.*/\\U&/<CR>'),
        ('s_lower_end', EXF, ':2s/\\w\\+/\\L&\\E!/<CR>'), ('s_tilde', EXF, ':s/alpha/A1/<CR>:3s/alpha/~2/<CR>'),
        ('s_ignorecase', EXF, ':%s/beta/b/g<CR>'), ('s_smartcase', EXF, ':%s/Beta/b/g<CR>'), ('s_I', EXF, ':%s/beta/b/gI<CR>'),
        ('s_i', EXF, ':%s/BETA/b/gi<CR>'), ('s_e', EXF, ':s/xyz/q/e<CR>x'), ('s_empty_match', EXF, ':s/x*/-/g<CR>'),
        ('s_bol', EXF, ':%s/^/#/<CR>'), ('s_eol', EXF, ':%s/$/;/<CR>'), ('s_word', EXF, ':%s/\\<a/A/g<CR>'),
        ('s_class', EXF, ':%s/[aeiou]\\+/./g<CR>'), ('s_star_lazy', EXF, ':s/a.\\{-}a/<lt>&>/<CR>'),
        ('s_alt', EXF, ':%s/alpha\\|gamma/W/g<CR>'), ('s_hash_delim', EXF, ':s#a#/#g<CR>'), ('s_undo', EXF, ':%s/a/X/g<CR>u'),
        ('s_undo_redo', EXF, ':%s/a/X/g<CR>u<C-r>'), ('amp', EXF, ':s/a/X/<CR>j:&<CR>'), ('amp_amp', EXF, ':s/a/X/g<CR>j:&&<CR>'),
        ('amp_range', EXF, ':s/a/X/<CR>:%&<CR>'), ('s_repeat', EXF, ':s/a/X/g<CR>j:s<CR>'), ('s_reuse_pat', EXF, ':s/a/X/<CR>:2s//Y/<CR>'),
        ('g_d', EXF, ':g/alpha/d<CR>'), ('v_d', EXF, ':v/alpha/d<CR>'), ('g_bang', EXF, ':g!/alpha/d<CR>'),
        ('g_s', EXF, ':g/a/s/a/@/g<CR>'), ('g_amp', EXF, ':s/e/E/<CR>:g/e/&<CR>'), ('g_range', EXF, ':2,4g/a/d<CR>'),
        ('g_undo', EXF, ':g/alpha/d<CR>u'), ('g_next_line', EXF, ':g/alpha/.,+1d<CR>'), ('g_split', EXF, ':g/beta/s/ /\\r/<CR>'),
        ('g_none', EXF, ':g/xyz/d<CR>x'), ('g_cursor', EXF, ':g/a/s/a/b/<CR>x'),
        ('d_range', NUMS, ':2,4d<CR>'), ('d_count', NUMS, ':2d 3<CR>'), ('d_reg', NUMS, ':3d a<CR>"ap'), ('d_upper', NUMS, ':1d a<CR>:2d A<CR>"ap'),
        ('d_all', NUMS, ':%d<CR>'), ('d_numbered', NUMS, ':1d<CR>:1d<CR>"2p'), ('d_last', NUMS, ':$d<CR>'),
        ('goto', NUMS, ':4<CR>x'), ('goto_past', NUMS, ':99<CR>x'), ('goto_plus', NUMS, ':2<CR>:+2<CR>x'), ('goto_dot_minus', NUMS, 'G:.-3<CR>x'),
        ('mark_range', NUMS, 'jmajjmb:\'a,\'bd<CR>'), ('visual_s', NUMS, 'jVj:s/$/!/<CR>'), ('visual_d', NUMS, 'Vjj:d<CR>'),
        ('backwards', NUMS, ':4,2d<CR>'), ('bad_range', NUMS, ':9d<CR>x'), ('esc_cancels', NUMS, ':2d<Esc>x'),
        ('bs_leaves', NUMS, ':<BS>x'), ('dot_after_s', EXF, 'x:s/a/X/<CR>j.')]:
    add('ex', name, text, script)
