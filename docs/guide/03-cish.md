# 03 `cish`, the shell

`cish` is the Daphnis shell, written in cint (`user/ci/cish.ci`, `user/ci/cish/`). It speaks a POSIX `sh` subset
(ruling CSH-1 A). It is `/sh` and `/bin/sh` in every image a person or the agent uses (CSH-2 A). Busybox `ash` stays
only in the gate images, as the oracle.

## Start it

Every terminal in the desk runs it. On Linux the committed static build runs as is: `user/bin/cish`.

## What it speaks

| area | supported |
| --- | --- |
| lists | `;` newline `&&` `\|\|` `!` `&` (background, no job control) and pipelines |
| redirections | `<` `>` `>>` `<>` `>\|` `n>&m` `n<&m` `n>&-` and here-documents `<<` `<<-` |
| compound | `{ }` `( )` `if elif else fi` `while` `until` `for in` `case esac` functions `name() body` |
| expansion | parameters and `${x:-w}` forms, `${#x}`, `%` `%%` `#` `##`, `$(...)` and backquotes, `$((...))`, `IFS` splitting, `*` `?` `[...]` |
| builtins | `cd` `exit` `export` `unset` `set` `shift` `readonly` `return` `break` `continue` `.` `eval` `exec` `read` `wait` `trap` `umask` `:` `true` `false` `echo` `test` `[` `printf` |
| prompt | `PS1` (`# ` for user 0, else `$ `), `PS2` (`> `); no dotfile is read at start |

Everything else is a program on `PATH` (`/bin`: busybox applets until the native core set lands).

## Where it differs from `ash` on purpose

| case | `cish` | `ash` |
| --- | --- | --- |
| arithmetic overflow or division by zero | diagnostic, status 2 | wraps |
| `[[` arrays brace expansion `function` `<<<` `select` `$'...'` | `cish: not supported: TOKEN`, status 2 | accepts some |
| a table past its size | `cish: limit: NAME N`, status 2 | no fixed limit |

The terminal settings are restored before every prompt, so a program that leaves raw mode (or faults) never strands
the shell.

## Not yet

Job control, `trap` actions (Daphnis delivers no signals), `alias`, `getopts`, `command`, `type`, `hash`.

Checked by `check-cish.sh` (49 checks): every session in `tests/cish/` gives the bytes and status of busybox `ash` on
Linux, from gcc, clang and Daphnis builds.
