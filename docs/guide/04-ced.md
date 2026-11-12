# 04 `ced`, the editor

`ced` is the one bundled editor: one file, undo and redo, search and replace, word wrap, written in cint. It is the
same program as the standalone ced 0.2.1 (Apache-2.0 or MIT), copied unchanged into `user/ced/` at the commit in
`user/ced/CED_PIN`.

## Start it

In any desk terminal:

```
./ced notes.txt
```

ced needs about 57 MiB, so the desk must boot with the pool sized from RAM (`POOL=max`, as `tools/play.sh` and the
02-desk command do). In the gates' fixed 64 MiB pool it is refused at start.

## Keys

| keys | action |
| --- | --- |
| Ctrl+S | save (a temporary file, then a rename) |
| Ctrl+Q | quit |
| Ctrl+Z, Ctrl+Y | undo, redo |
| Ctrl+A | select all |
| Ctrl+C, Ctrl+X, Ctrl+V | copy, cut, paste (inside ced) |
| Ctrl+F | find |
| Ctrl+R | replace |
| Ctrl+G | go to line |
| Ctrl+W | word wrap on or off |
| Shift+arrows | select |
| Ctrl+Left, Ctrl+Right | word left, right |
| Ctrl+Home, Ctrl+End | start, end of the file |

## Limits today

A file created inside Daphnis holds at most 64 KiB (`src/fs.ci` `FILE_FRAMES`). ced itself opens up to 8 MiB. The
terminal shows 95 ASCII glyphs; no UTF-8.

Checked by `check-editor.sh` (18 checks): the sources against `user/ced/SOURCES.sha256`, ced's own test suite, the
same keys on a pty from three builds, and the desk at 512 MiB saving a file equal to Linux's.
