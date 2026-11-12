#!/bin/sh
# tests/ac/authd-store.sh AUTHD STORE PARENT_MIN: authd's store operations (RS-ROLE, docs/specs/2026-11-11-rs-role.md;
# RS-R3 and RS-R4, docs/specs/2026-11-11-rs-accounts-ops.md), the built program over a real directory. tests/ac/authd.sh
# runs it in a mount namespace of its own with an empty /home, so it never sees the host's. STORE holds ci (parent,
# `correct horse`), sam (child, `kid4`, ceiling 1) and lee (child, `a longer password`, long=1, ceiling 3) at 8 KiB and
# one pass. PARENT_MIN is acct.ci's (AC-D3), which tests/ac/authd.sh reads. One `ok` or `bad` line a check.
authd=$1
store=$2
pmin=$3
case "$pmin" in ''|*[!0-9]*) echo "bad no parent minimum"; exit 1;; esac
short=$(printf "%$((pmin - 1))s" "" | tr ' ' x)   # one character short of a parent's passphrase
bad=0
d=/home/.daphnis
[ -e "$d" ] && { echo "bad $d is there already: not an empty /home"; exit 1; }
mkdir -m 700 "$d" && cp "$store" "$d/accounts" && chmod 600 "$d/accounts" || { echo "bad no store"; exit 1; }
line() { if [ "$1" = ok ]; then echo "ok $2"; else echo "bad $2"; bad=1; fi; }
sum() { sha256sum "$d/accounts" | cut -d' ' -f1; }
# ask WANT STATUS REQUEST: authd's one line and status
ask() {
    out=$(printf "$3" | "$authd"); st=$?
    [ "$out" = "$1" ] && [ $st -eq "$2" ]
}
same() { [ "$(sum)" = "$before" ] && [ "$(ls -A "$d" | tr '\n' ' ')" = "$names" ]; }

before=$(sum); names=$(ls -A "$d" | tr '\n' ' ')
ask no 1 'remove ci sam\ncorrect horsf' && same && line ok "authd remove with a wrong passphrase: no, the store's bytes kept" \
    || line bad "authd remove, wrong passphrase: '$out' status $st"
ask no 1 'remove ci sam\nkid4' && same && line ok "authd remove with the target's passphrase: no, the store's bytes kept" \
    || line bad "authd remove, the target's passphrase: '$out' status $st"
ask 'refused approver' 3 'ceil sam sam 7\nkid4' && same && line ok "authd ceil approved by a child: refused" \
    || line bad "authd ceil, a child approves: '$out' status $st"
ask 'refused last parent' 3 'role ci ci child\ncorrect horse' && same && line ok "authd role: the last parent stays a parent" \
    || line bad "authd role, the last parent: '$out' status $st"
ask 'refused last parent' 3 'remove ci ci\ncorrect horse' && same && line ok "authd remove: the last parent stays" \
    || line bad "authd remove, the last parent: '$out' status $st"
ask 'refused password' 3 'role ci sam parent\ncorrect horse' && same && line ok "authd role: a short passphrase is no parent's" \
    || line bad "authd role, a short passphrase: '$out' status $st"
ask 'error request' 2 'role ci sam\ncorrect horse' && same && line ok "authd refuses a malformed operation" \
    || line bad "authd malformed operation: '$out' status $st"

ask ok 0 'ceil ci sam 5\ncorrect horse' && grep -q '^acct .* name=sam role=child .* ceil=5$' "$d/accounts" \
    && [ "$(sha256sum "$d/accounts.prev" | cut -d' ' -f1)" = "$before" ] \
    && [ "$(ls -A "$d" | tr '\n' ' ')" = "accounts accounts.prev " ] && [ "$(stat -c %a "$d/accounts")" = 600 ] \
    && line ok "authd ceil: written whole, mode 600, the old store kept as accounts.prev, no new file left" \
    || line bad "authd ceil: '$out' status $st, $(ls -A "$d" | tr '\n' ' ')"
ask ok 0 'role ci lee parent\ncorrect horse' && grep -q '^acct .* name=lee role=parent .* ceil=7$' "$d/accounts" \
    && line ok "authd role: lee is a parent with every grant" || line bad "authd role lee parent: '$out' status $st"
ask ok 0 'role lee ci child\na longer password' && grep -q '^acct .* name=ci role=child .* ceil=7 long=1$' "$d/accounts" \
    && line ok "authd role: the new parent demotes the first, who keeps the parent's mark" \
    || line bad "authd role ci child: '$out' status $st"
ask 'refused approver' 3 'remove ci sam\ncorrect horse' && line ok "authd remove: the demoted parent approves nothing" \
    || line bad "authd remove by the demoted: '$out' status $st"
ask ok 0 'remove lee sam\na longer password' && ! grep -q 'name=sam ' "$d/accounts" \
    && [ "$(head -1 "$d/accounts")" = "daphnis-accounts 1" ] \
    && line ok "authd remove: sam is gone; lee's uid is still the highest, so the header is plain" \
    || line bad "authd remove sam: '$out' status $st, $(head -1 "$d/accounts")"
ask ok 0 'role lee ci parent\na longer password' && ask ok 0 'remove ci lee\ncorrect horse' \
    && [ "$(head -1 "$d/accounts")" = "daphnis-accounts 1 next=1003" ] && [ "$(grep -c '^acct ' "$d/accounts")" = 1 ] \
    && line ok "authd remove: the highest uid removed is never given again (next=1003)" \
    || line bad "authd remove lee: '$out' status $st, $(head -1 "$d/accounts")"

# RS-R4 and RS-R3 (docs/specs/2026-11-11-rs-accounts-ops.md): an account added and a passphrase set at DS-6's
# parameters (64 MiB, 3 passes), and a removed account's home set aside. The store holds ci alone here, next=1003.
ask ok 0 'add ci eve child 13\ncorrect horsefour' && [ ! -e /home/eve ] \
    && grep -q '^acct .* uid=1003 gid=1003 name=eve role=child m=65536 t=3 .* ceil=0$' "$d/accounts" \
    && line ok "authd add: eve is a child with no grant, a uid never given before, DS-6's parameters, no home made" \
    || line bad "authd add eve: '$out' status $st, $(grep name=eve "$d/accounts")"
before=$(sum); names=$(ls -A "$d" | tr '\n' ' ')
ask 'refused taken' 3 'add ci eve child 13\ncorrect horsefour' && same \
    && line ok "authd add: a name taken is refused" || line bad "authd add, a name taken: '$out' status $st"
ask 'refused password' 3 "add ci max parent 13\\ncorrect horse$short" && same \
    && line ok "authd add: a parent's passphrase under $pmin characters is refused" \
    || line bad "authd add, a short parent passphrase: '$out' status $st"
ask 'refused approver' 3 'passwd eve ci 4\nfoura passphrase of a parent' && same \
    && line ok "authd passwd: a child sets no passphrase but its own" \
    || line bad "authd passwd by a child: '$out' status $st"
ask ok 0 'passwd eve eve 4\nfoura passphrase of a parent' \
    && grep -q '^acct .* name=eve role=child m=65536 t=3 .* ceil=0 long=1$' "$d/accounts" \
    && line ok "authd passwd: the account's own passphrase sets a new one, noted as of a parent's length" \
    || line bad "authd passwd eve: '$out' status $st"
ask no 1 'passwd eve eve 4\nfourabcd' && line ok "authd passwd: the old passphrase approves nothing" \
    || line bad "authd passwd, the old passphrase: '$out' status $st"
mkdir -m 700 /home/eve && echo kept > /home/eve/file
ask ok 0 'remove ci eve\ncorrect horse' && [ ! -e /home/eve ] && [ "$(cat /home/.removed.eve.1003/file)" = kept ] \
    && [ "$(stat -c %a /home/.removed.eve.1003)" = 700 ] && ! grep -q 'name=eve ' "$d/accounts" \
    && line ok "authd remove: the home is set aside as /home/.removed.eve.1003, its mode and contents kept" \
    || line bad "authd remove eve with a home: '$out' status $st, $(ls -A /home | tr '\n' ' ')"
ask ok 0 'add ci eve child 13\ncorrect horsefour' && grep -q '^acct .* uid=1004 gid=1004 name=eve ' "$d/accounts" \
    && mkdir -m 700 /home/eve /home/.removed.eve.1004 && before=$(sum) && names=$(ls -A "$d" | tr '\n' ' ') \
    && ask 'refused home' 3 'remove ci eve\ncorrect horse' && same && [ -d /home/eve ] \
    && line ok "authd remove: the name added again has a new uid; a name where its home would go refuses it whole" \
    || line bad "authd remove eve, the aside name taken: '$out' status $st"
rm "$d/accounts" "$d/accounts.prev"
ask 'error store' 2 'remove ci sam\ncorrect horse' && [ -z "$(ls -A "$d")" ] && line ok "authd with no store: error, nothing made" \
    || line bad "authd with no store: '$out' status $st"
exit $bad
