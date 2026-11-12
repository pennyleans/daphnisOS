#!/usr/bin/env bash
# tests/ac/authd.sh AUTHD: AC-1b's gate for authd (the program built from source at HEAD, O/ubin/authd) on the host (docs/specs/2026-11-08-ac-accounts.md
# section 6). derive is compared with tools/ac-vectors.py, the plain-Python Argon2id that reproduces RFC 9106's vector,
# at 1 MiB and 4 MiB (several address blocks a segment), and enroll then verify must accept the right passphrase and
# refuse a wrong one. Prints one `ok` or `bad` line a check and exits 1 if any is bad. TIME=1 also times DS-6's
# parameters (64 MiB, 3 passes) and prints the seconds; that number is a receipt, never a pass or a fail.
set -u
cd "$(dirname "$0")/../.."
authd=${1:?"usage: tests/ac/authd.sh AUTHD (O/ubin/authd, built by make)"}
bad=0
line() { if [ "$1" = ok ]; then echo "ok $2"; else echo "bad $2"; bad=1; fi; }
salt=000102030405060708090a0b0c0d0e0f

for case in "1024 3 correct-horse-battery" "4096 1 daphnis" "8 1 x"; do
    set -- $case
    want=$(python3 tools/ac-vectors.py argon2id "$1" "$2" 1 "$salt" "$3" | sed -n 's/^verifier //p')
    got=$(printf 'derive %s %s %s\n%s' "$1" "$2" "$salt" "$3" | "$authd" | sed -n 's/^verifier //p')
    [ -n "$want" ] && [ "$got" = "$want" ] && line ok "authd derive m=$1 t=$2 equals tools/ac-vectors.py" \
        || line bad "authd derive m=$1 t=$2: got '$got', want '$want'"
done

enr=$(printf 'enroll 1024 2\nsevenhorsesrun' | "$authd")
s=$(echo "$enr" | sed -n 's/^salt //p')
v=$(echo "$enr" | sed -n 's/^verifier //p')
[ ${#s} -eq 32 ] && [ ${#v} -eq 64 ] && line ok "authd enroll gives a 16-byte salt and a 32-byte verifier" \
    || line bad "authd enroll: '$enr'"
out=$(printf 'verify 1024 2 %s %s\nsevenhorsesrun' "$s" "$v" | "$authd"); st=$?
[ "$out" = ok ] && [ $st -eq 0 ] && line ok "authd verify accepts the enrolled passphrase (status 0)" \
    || line bad "authd verify, right passphrase: '$out' status $st"
out=$(printf 'verify 1024 2 %s %s\nsevenhorsesrum' "$s" "$v" | "$authd"); st=$?
[ "$out" = no ] && [ $st -eq 1 ] && line ok "authd verify refuses a wrong passphrase (status 1)" \
    || line bad "authd verify, wrong passphrase: '$out' status $st"
enr2=$(printf 'enroll 1024 2\nsevenhorsesrun' | "$authd")
[ "$(echo "$enr2" | sed -n 's/^salt //p')" != "$s" ] && line ok "two enrollments draw two salts" \
    || line bad "two enrollments drew one salt"

for req in 'verify 8 1 00 00\nx' 'derive 7 1 '"$salt"'\nx' 'derive 8 1 '"$salt"'\n' 'unlock 8 1\nx'; do
    out=$(printf "$req" | "$authd"); st=$?
    case "$out" in error*) [ $st -eq 2 ] && line ok "authd refuses a malformed request ($out)" \
        || line bad "authd malformed request: status $st" ;;
        *) line bad "authd accepted a malformed request: '$out'" ;; esac
done

# RS-ROLE: the store operations. A malformed one is refused before any store is opened, on any host. The rest runs
# the program over a real directory in a mount namespace of its own with an empty /home (tests/ac/authd-store.sh);
# a host that gives no such namespace prints one skip line, and tools/check-authop.py covers the same rules.
out=$(printf 'role ci sam\nx' | "$authd"); st=$?
[ "$out" = "error request" ] && [ $st -eq 2 ] && line ok "authd refuses a malformed store operation (status 2)" \
    || line bad "authd malformed store operation: '$out' status $st"
if unshare -rm sh -c 'mount -t tmpfs none /home' 2>/dev/null; then
    t=$(mktemp -d)
    cp "$authd" "$t/authd"; cp tests/ac/authd-store.sh "$t/run.sh"
    {
        echo "daphnis-accounts 1"
        k=0
        for a in "ci parent 7 correct horse" "sam child 1 kid4" "lee child 3 long=1 a longer password"; do
            set -- $a; name=$1 role=$2 ceil=$3; shift 3
            mark=""; [ "$1" = long=1 ] && { mark=" long=1"; shift; }
            s=$(printf '%032x' $((k + 1)))
            v=$(python3 tools/ac-vectors.py argon2id 8 1 1 "$s" "$*" | sed -n 's/^verifier //p')
            echo "acct id=$s uid=$((1000 + k)) gid=$((1000 + k)) name=$name role=$role m=8 t=1 salt=$s ver=$v ceil=$ceil$mark"
            k=$((k + 1))
        done
    } > "$t/accounts"
    pmin=$(sed -n 's/^export const I64 PARENT_MIN = \([0-9]*\);.*/\1/p' user/ci/acct.ci)   # AC-D3, as authd checks it
    unshare -rm sh -c 'mount -t tmpfs none /home && exec sh "$0/run.sh" "$0/authd" "$0/accounts" "$1"' "$t" "$pmin" \
        > "$t/log" 2>&1
    [ $? -eq 0 ] || bad=1
    cat "$t/log"
    rm -rf "${t:?}"
else
    echo "skip authd store operations over a real directory: no mount namespace on this host (unshare -rm)"
fi

if [ "${TIME:-0}" = 1 ]; then
    t0=$(date +%s%N)
    printf 'derive 65536 3 %s\nsevenhorsesrun' "$salt" | "$authd" > /dev/null
    t1=$(date +%s%N)
    echo "time authd derive m=65536 t=3 (DS-6): $(( (t1 - t0) / 1000000 )) ms on $(uname -m) $(uname -r)"
fi
exit $bad
