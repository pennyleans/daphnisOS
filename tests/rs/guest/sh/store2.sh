# tests/rs/guest/sh/store2.sh, in the guest as /rs/s2: the store leg's k rows (ops/store.ops), after `kern true` in the
# same window, so this script and what it starts hold ring 0. Exits with /rs/s1's status unless that is 0 (127 when
# /rs/s1 left none), else with store.sh's; ops/store.ops reads either (guest.py status).
sh /rs/store.sh 2>> "$HOME/rs.err"
b=$?
echo "store.sh status $b" >> "$HOME/rs.log"
a=127
[ -f /tmp/rs.a ] && a=$(cat /tmp/rs.a)
[ "$a" = 0 ] || exit "$a"
exit $b
