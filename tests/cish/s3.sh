# tests/cish/s3.sh: the CS-3 session. cish and busybox ash give the same bytes (1 and 2 together) and status.
x=hello; unset u; e=
echo ${x:-d} ${u:-default} ${e:-empty} ${e-unset} [${u-}] ${u+set} ${x+set} [${e:+no}]
echo ${u:=assigned} $u; echo ${e=kept}[$e]; echo ${e:=now} $e
echo ${#x} ${#u} ${#} ${#e}
p=/usr/local/lib/file.tar.gz
echo ${p#*/} ${p##*/} ${p%.*} ${p%%.*} ${p#/usr} ${p%gz}
echo "${p##*/}" "${x%l*}" "${x%%l*}" "${x#?}" "${x##*l}"
echo $((1 + 2 * 3)) $(( (1 + 2) * 3 )) $((7 / 2)) $((-7 / 2)) $((7 % 3)) $((-7 % 3)) $((1 << 4)) $((256 >> 2))
echo $((5 > 3)) $((5 < 3)) $((2 == 2)) $((2 != 2)) $((!0)) $((~0)) $((6 & 3)) $((6 | 3)) $((6 ^ 3))
echo $((1 && 0)) $((1 || 0)) $((0 ? 10 : 20)) $((0x1f + 010)) $((2 ** 10))
n=5; echo $((n * 2)) $(($n + 1)) $((n += 3)) $n $((n -= 1, n * 10))
i=0; while [ $i -lt 3 ]; do i=$((i + 1)); echo loop $i; done
echo $(echo inner) "$(echo quoted   spaces)" `echo back` "`echo backq`"
echo $(echo $(echo nested))
lines=$(printf 'a\nb\n\n\n'); echo "[$lines]"
v=$(false); echo status $?
count=$(ls | wc -l); echo files $count
echo "$(cd etc; pwd)" $(pwd)
f() { echo from function $1; }; echo "$(f arg)"
set -- one "two three" four
IFS=:; data="a:b::c"; for w in $data; do echo "<$w>"; done
echo "$*"; IFS=; echo "$*"; unset IFS
IFS=' :'; data=" x : y :z"; for w in $data; do echo "{$w}"; done; unset IFS
s="  spaced   out  "; for w in $s; do echo "($w)"; done
echo h*; echo "h*"; echo e?c; echo [eh]*.txt; echo */motd; echo no*match; echo \*
pat='*.txt'; echo $pat; echo "$pat"
HOME=/home/me; echo ~ ~/bin "~" x~
cat <<EOF
here $x and $((2 + 2))
  indented "quotes" 'single'
\$escaped and $(echo sub)
EOF
cat <<'EOF'
literal $x $(echo no)
EOF
cat <<-EOF
	tab stripped $x
		two tabs
	EOF
wc -l <<EOF
1
2
3
EOF
for f in *.txt; do echo glob $f; done
for f in $(echo a b c); do echo subst $f; done
echo "$(echo "nested quotes" here)" "$(echo 'single' "double")"
echo ${x:-$(echo not run)} ${u2:-$(echo lazy run)}
case $(echo hello) in h*) echo case of a substitution;; esac
x=$(exit 3) y=1; echo assignment status $?
echo $(( $(echo 6) * $(echo 7) ))
k=1; echo $((k > 0 ? k * 100 : -1))
echo end $(( 6 * 7 )); exit 7
