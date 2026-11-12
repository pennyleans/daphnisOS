# tests/cish/s1.sh: the CS-1 session. cish and busybox ash give the same bytes (1 and 2 together) and status.
echo hello from cish
ls
cat hello.txt | wc -l
grep -c line lines.txt
echo written by cish > out.txt; cat out.txt; rm out.txt
ls | head -3 | tr a-z A-Z
cat < lines.txt | sort -r | head -2
seq 1 5 | xargs echo
x=six; y="seven  eight"; echo $x $y "$y"
echo 'single $x' "double $x" \$x back\ slash "a\"b" 'c"d' "e'f"
echo "$x"'$y'"${y}"end ${x}s
echo a; echo b && echo c || echo d
false && echo no || echo yes
! false && echo bang
true | false; echo pipe status $?
! true | true; echo not pipe $?
nosuch 2>err.txt; echo not found $?; wc -l err.txt; rm err.txt
echo to stderr 1>&2
echo both 2>&1 >o.txt; cat o.txt; rm o.txt
cd etc; pwd; cat motd | head -1; cd ..; pwd
echo appended > a.txt; echo again >> a.txt; cat a.txt; rm a.txt
cat < hello.txt > h2.txt; wc -c h2.txt; rm h2.txt
exec_me=1 true; echo assignment before a builtin [$exec_me]
export Z=1; export | grep Z=
unset x; echo "x is [$x]"
:; echo colon $?
false; echo false $?
echo $# "$@" $*
echo line \
continued
echo "two
lines"
echo end; exit 3
echo never
