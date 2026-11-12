# tests/cish/s5.sh: the environment a child gets (CT-5b, docs/specs/2026-11-06-c-core.md section 7a): exported
# variables and a command's own assignments reach it, under Daphnis as on Linux; an unset one does not.
export W=1 X='two words'
v=1 sh -c 'echo child sees [$v] [$W] [$X]'; echo parent sees [$v]
unset W; sh -c 'echo after unset [$W] [$X]'
sh -c 'echo $0 $1' zero one
echo end; exit 0
