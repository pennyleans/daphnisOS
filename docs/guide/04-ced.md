# 04 `ced`, the editor

`ced` is a bundled text editor with undo, redo, search, replace, and word wrap.
Its source is in `user/ced/` under Apache-2.0 or MIT.

## Start it

In any desk terminal:

```
ced "$HOME/notes.txt"
```

Use the account's home directory to keep files across reboots. For a development
boot, use the memory settings in the [desktop example](02-desk.md).

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

## Checks

`check-editor.sh` verifies the bundled source, runs the editor tests, and checks
editing through a terminal on the desktop.
