# tests/cish/s4.sh: the CS-4 session. cish and busybox ash give the same bytes (1 and 2 together) and status.
eval echo eval one; eval 'x=5; echo x is $x'
cmd='echo built $((x * 2))'; eval "$cmd"; eval "$cmd" '; echo second'
eval 'f() { echo defined in eval $1; }'; f arg
for i in 1 2 3; do eval "if [ $i = 2 ]; then continue; fi"; echo loop $i; done
eval false; echo eval status $?; eval; echo empty eval $?
printf 'y=7\necho dot $y $1\ng() { echo g from dot; }\nreturn 3\necho not reached\n' > lib.sh
. ./lib.sh; echo after dot $? $y; g
. ./lib.sh p q; echo dot args $? $#; rm lib.sh
z=1 eval 'echo z is $z'; g() { eval "h() { echo h via g; }"; }; g; h
read a b <<EOF
first second third
EOF
echo "[$a] [$b]"
read -r r <<'EOF'
back\slash kept
EOF
echo "$r"
read r <<'EOF'
back\slash gone \
continued
EOF
echo "$r"
IFS=: read p q r <<EOF
1:2:3:4
EOF
echo "$p $q $r"
printf 'l1\nl2\nl3' | while read line; do echo got $line; done
printf 'no newline' | { read v; echo status $? "$v"; }
echo one two | { read only; echo "$only"; }
read e1 e2 <<EOF
  padded   words  
EOF
echo "<$e1> <$e2>"
true & wait $!; echo waited $?
(exit 4) & p1=$!; wait $p1; echo bg status $?
echo a > w1.txt & echo b > w2.txt & wait; cat w1.txt w2.txt; rm w1.txt w2.txt; echo all waited
exec 3> fd3.txt; echo to three >&3; exec 3>&-; cat fd3.txt; rm fd3.txt
(exec echo exec replaces; echo not printed)
(exec > ex.txt; echo into the file); cat ex.txt; rm ex.txt
printf 'cat <<E\nno newline after the delimiter\nE' > nl.sh; ./cish nl.sh; sh nl.sh; ./cish -c "$(cat nl.sh)"; rm nl.sh
echo end; exec sh -c 'exit 5'
