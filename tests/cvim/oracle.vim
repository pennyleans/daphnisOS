" tests/cvim/oracle.vim: cvim's defaults as Vim options (docs/specs/2026-11-07-cv-cvim.md sections 4 and 6), for the
" oracle's Vim, started as `vim --clean -u NONE -i NONE -n -N -S tests/cvim/oracle.vim FILE`. `-u NONE` alone leaves
" Vim in Vi-compatible mode (empty 'backspace', Vi undo, no keys in Insert mode), so `-N` turns that off and this file
" sets the options of section 6 that change what a key does to the text or the cursor.
set nocompatible
set expandtab shiftwidth=4 tabstop=4 softtabstop=0
set autoindent smartindent cinwords=
set backspace=indent,eol,start
set whichwrap=b,s
set nojoinspaces
" Not a cvim option: the pty driver waits 60 ms after a lone Esc, so Vim may decide a key code after 10 ms.
set ttimeout ttimeoutlen=10
" CV-2b: H M L and the scroll keys count the window's rows: lines do not wrap and 'scrolloff' is 4 (section 6).
set nowrap scrolloff=4
" CV-4b: :s, :g and :v match as section 6 has it: 'ignorecase' and 'smartcase' on. No earlier case searches.
set ignorecase smartcase
