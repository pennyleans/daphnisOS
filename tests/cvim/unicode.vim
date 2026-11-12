set encoding=utf-8
let rows = []
let changes = []
let start = 128
let prev = charclass(nr2char(start))
for cp in range(128, 0x10ffff)
  let ch = nr2char(cp)
  let cl = charclass(ch)
  if cl != prev
    call add(rows, [start, cp - 1, prev])
    let start = cp
    let prev = cl
  endif
  let lo = tolower(ch)
  let dest = lo ==# ch ? toupper(ch) : lo
  if dest !=# ch && strchars(dest) == 1
    call add(changes, [cp, char2nr(dest)])
  endif
endfor
call add(rows, [start, 0x10ffff, prev])
call writefile([json_encode({'classes': rows, 'toggle': changes})], '/tmp/cvim-unicode.json')
qa!
