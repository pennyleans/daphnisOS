# tests/cish/s2.sh: the CS-2 session. cish and busybox ash give the same bytes (1 and 2 together) and status.
if true; then echo if then; fi
if false; then echo no; else echo if else; fi
if false; then echo no; elif true; then echo elif; else echo no; fi
if false; then :; fi; echo if none $?
if ! false
then
    echo multi line if
fi
i=0
while [ $i -lt 3 ]; do echo while $i; i=${i}0; break; done
n=
while test "$n" != xxx; do n=${n}x; echo n=$n; done
until [ "$n" = "" ]; do n=; echo until; done
for w in one "two three" four; do echo for $w; done
for w in; do echo never; done; echo empty for $?
set -- a 'b c' d
for p; do echo pos $p; done
for p in "$@"; do echo quoted "$p"; done
echo count $# first $1
shift; echo after shift $# $1
shift 2; echo after shift 2 $#
shift 5; echo shift too far $?
for i in 1 2 3; do
    for j in a b c; do
        if [ $j = b ]; then continue; fi
        if [ $i = 2 ]; then continue 2; fi
        if [ $i = 3 ]; then break 2; fi
        echo $i$j
    done
done
echo loops done
for x in apple banana cherry '*' q; do
    case $x in
        a*) echo $x starts with a;;
        b?n*|c*) echo $x matched b or c;;
        "*") echo a star;;
        [!a-p]) echo $x one letter;;
    esac
done
case nothing in x) echo no;; esac; echo case none $?
case "a b" in "a b") echo quoted subject;; esac
case abc in (a|b) echo no;; (abc) echo paren pattern
esac
greet() {
    echo hello $1 with $# args
}
greet world two
greet; echo greet status $?
two() { return 2; }
two; echo returned $?
early() {
    for k in 1 2 3; do
        if [ $k = 2 ]; then return 7; fi
        echo early $k
    done
    echo not reached
}
early; echo early status $?
pp() { echo in pp $# "$@"; shift; echo shifted $1; }
set -- x y z
pp 1 2; echo outer $# $1
v=outer; scoped() { echo v is $v; }; v=inner scoped; echo v after $v
countdown() { if [ $1 = 0 ]; then echo liftoff; else echo $1; countdown $2 $3 $4 0; fi; }
countdown 3 2 1
{ echo brace one; echo brace two; } > b.txt; cat b.txt; rm b.txt
( echo in subshell; exit 4 ); echo subshell $?
(cd etc; pwd); pwd
for f in 1 2; do echo piped $f; done | tr a-z A-Z
echo text | while true; do cat; break; done
if [ -f hello.txt ] && [ -d etc ] && [ ! -e nothere ]; then echo files ok; fi
[ -n "x" ]; echo n $?; [ -z "" ]; echo z $?; [ abc = abc ]; echo eq $?; [ abc != abc ]; echo ne $?
[ 3 -lt 10 ]; echo lt $?; [ 10 -le 3 ]; echo le $?; [ -5 -ge -6 ]; echo ge $?; test 7 -eq 7 -a 1 -ne 2; echo and $?
test 1 -eq 2 -o \( 3 -gt 2 \); echo or $?; test; echo empty $?; test x; echo one $?; [ ! x ]; echo bang $?
[ -s hello.txt ]; echo size $?; [ -r hello.txt -a -w hello.txt ]; echo rw $?; [ -x bin/sh ]; echo exec $?
echo plain echo   spaced  "  kept  "
echo -n not an option
printf '%s|%d|%5s|%-4s|%03d|%x|%X|%o|%c\n' word 42 right left 7 255 255 8 char
printf '%s\n' one two three
printf 'no args %s|\n'
printf '%5.2d|%.3x|%#x|%#o|%+d|% d|%-5d|\n' 3 5 255 8 4 4 -9
printf '%b|\n' 'tab\there' 'oct\0101'
printf 'esc \101\x42\t|\n'
printf '%d %d %d %d\n' 0x1f 017 "'A" -12
printf '%*d|%-*s|%.*s|\n' 4 9 3 ab 2 hello
printf 'percent %% done\n'
printf '%s' last; echo
printf '%b\n' 'stop\cnever'; echo after stop
echo end; exit 5
