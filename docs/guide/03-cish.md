# 03 `cish`, the shell

`cish` is the Daphnis shell. It implements a subset of POSIX `sh` and runs
in the desktop's Console. The release image provides it as `/bin/sh`.

## What it speaks

| area | supported |
| --- | --- |
| lists | `;` newline `&&` `\|\|` `!` `&` (background, no job control) and pipelines |
| redirections | `<` `>` `>>` `<>` `>\|` `n>&m` `n<&m` `n>&-` and here-documents `<<` `<<-` |
| compound | `{ }` `( )` `if elif else fi` `while` `until` `for in` `case esac` functions `name() body` |
| expansion | parameters and `${x:-w}` forms, `${#x}`, `%` `%%` `#` `##`, `$(...)` and backquotes, `$((...))`, `IFS` splitting, `*` `?` `[...]` |
| builtins | `cd` `exit` `export` `unset` `set` `shift` `readonly` `return` `break` `continue` `.` `eval` `exec` `read` `wait` `trap` `umask` `:` `true` `false` `echo` `test` `[` `printf` |
| prompt | `PS1` (`# ` for user 0, else `$ `), `PS2` (`> `); no dotfile is read at start |

External commands on the release image come from the native utilities in `/bin`.

## Where it differs from `ash` on purpose

| case | `cish` | `ash` |
| --- | --- | --- |
| arithmetic overflow or division by zero | diagnostic, status 2 | wraps |
| `[[` arrays brace expansion `function` `<<<` `select` `$'...'` | `cish: not supported: TOKEN`, status 2 | accepts some |
| a table past its size | `cish: limit: NAME N`, status 2 | no fixed limit |

The terminal settings are restored before every prompt, so a program that leaves raw mode (or faults) never strands
the shell.

## Checks

`check-cish.sh` compares scripted shell sessions with BusyBox `ash` on Linux.
`check-core.sh` exercises the native command-line utilities.
