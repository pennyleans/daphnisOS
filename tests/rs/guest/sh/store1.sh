# tests/rs/guest/sh/store1.sh, in the guest as /rs/s1: the store leg's - rows (ops/store.ops) as the session, before
# `kern true`. Its status is the first line of /tmp/rs.a for /rs/s2; rs.log gets it after row 2's answer, and rs.err
# session.sh's stderr (both in the home, read back from the volume). The window types only `sh /rs/s1`, since a key
# the kernel drops garbles a long line (board 20261112T012351Z).
sh /rs/session.sh 2>> "$HOME/rs.err"
a=$?
echo "session.sh status $a" >> "$HOME/rs.log"
echo "$a" > /tmp/rs.a
