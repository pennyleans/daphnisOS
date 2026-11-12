#!/usr/bin/env bash
# tools/abi-gap.sh [CASES]: unit BU-0 of docs/specs/2026-11-06-sw-bundle.md (section 7). Runs each case of CASES
# (default tools/abi-gap.cases) on Linux under strace and prints one markdown row per case, then the union:
#   made   the distinct Linux calls the case made (strace -f -n: the program and every child it starts)
#   hard   calls the dispatch of src/proc.ci lacks whose -ENOSYS alone (as Daphnis answers them) changes the
#          case's stdout, stderr, status or files (strace -e inject=NR:error=ENOSYS, one call a run)
#   soft   calls it lacks that the case survives at -ENOSYS, all of them injected in one run
#   stub   calls it answers 0 and does nothing for (the branch commented "nothing to do yet")
#   ioctl  terminal requests the case made that src/pty.ci does not take (a name strace decodes, else its number)
# A case is one line `ROW | CASE | COMMAND` (# starts a comment): ROW names the survey row, COMMAND is sh run in a
# fresh empty directory with $T before the traced program, $D the repository, $B the program directory (the Makefile's
# O/ubin, built from source at HEAD; required) and $X the directory of candidates built outside the tree (static
# musl, section 7). A case whose
# program ($T's next word) is missing is SKIP; one that ends with a status other than 0 is FAIL. A case with absent
# calls whose two runs differ is `unstable` and gets no hard or soft split. Needs strace 6 or later. Exit 1 on a
# FAIL.
set -u -o pipefail
D=$(cd "$(dirname "$0")/.." && pwd)
cases=${1:-$D/tools/abi-gap.cases}
B=${B:?"set B to the program directory, the Makefile's O/ubin (RG-1)"}
X=${X:-}
S=$(command -v strace) || { echo "abi-gap: strace not found" >&2; exit 1; }
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
export D B X

# The call table: every `nr == N` of syscall() in src/proc.ci; stubs are the branch whose body says nothing to do.
awk '/^void syscall\(I64 pid\)/ {on = 1} on && /^}/ {exit} on' "$D/src/proc.ci" > "$tmp/dispatch"
grep -o 'nr == [0-9]*' "$tmp/dispatch" | awk '{print $3}' | LC_ALL=C sort -u > "$tmp/have"
awk '/nr == [0-9]/ {prev = $0; next} /nothing to do/ {print prev} {prev = ""}' "$tmp/dispatch" \
    | grep -o 'nr == [0-9]*' | awk '{print $3}' | LC_ALL=C sort -u > "$tmp/stub"
sed -n 's/^const U64 \(TC[A-Z]*\|TIOC[A-Z]*\) = .*/\1/p' "$D/src/pty.ci" | LC_ALL=C sort -u > "$tmp/ioctl"
# the first header present (Debian's multiarch path, then Arch's): gawk 5.4 stops at a file it cannot open
for nrh in /usr/include/x86_64-linux-gnu/asm/unistd_64.h /usr/include/asm/unistd_64.h; do [ -f "$nrh" ] && break; done
name() { awk -v n="$1" '$1 == "#define" && $3 == n {sub(/^__NR_/, "", $2); print $2; exit}' "$nrh" 2>/dev/null | head -1; }
label() { local out="" n; for n in $(sort -n "$1"); do out="$out, $(name "$n") $n"; done; echo "${out#, }"; }

# run TRACER OUT: the case once in a fresh $tmp/w; OUT gets a digest of stdout, stderr, status and the tree.
run() {
    rm -rf "$tmp/w"; mkdir "$tmp/w"
    (cd "$tmp/w" && T="$S -f -qq $1 --" sh -c "$cmd" > "$tmp/out" 2> "$tmp/err" < /dev/null; echo "status $?" >> "$tmp/out")
    (cd "$tmp/w" && find . -printf '%y %p\n' | LC_ALL=C sort && find . -type f -print0 | LC_ALL=C sort -z \
        | xargs -0r sha256sum) > "$tmp/tree"
    cat "$tmp/out" "$tmp/err" "$tmp/tree" | sha256sum | cut -d' ' -f1 > "$2"
}

echo "src/proc.ci: $(wc -l < "$tmp/have") calls, stubs $(label "$tmp/stub"); strace $("$S" -V | head -1 | awk '{print $4}')"
echo
echo "| row | case | made | hard | soft | stub | ioctl |"
echo "| --- | --- | --- | --- | --- | --- | --- |"
: > "$tmp/all-hard"; : > "$tmp/all-soft"; : > "$tmp/all-io"
fail=0
while IFS= read -r line; do
    case "$line" in ''|'#'*) continue ;; esac
    row=$(echo "${line%%|*}" | xargs); rest=${line#*|}
    id=$(echo "${rest%%|*}" | xargs); cmd=${rest#*|}
    prog=$(eval "echo $(echo "${cmd#*\$T}" | awk '{print $1}')")
    if [ ! -x "$prog" ]; then
        echo "| $row | $id | SKIP: no $prog | | | | |"
        continue
    fi
    rm -rf "$tmp/tr"; mkdir "$tmp/tr"
    run "-ff -n -o $tmp/tr/t" "$tmp/d0"
    # a child that runs a host program (xargs's /bin/echo) counts up to that execve: Daphnis runs its own there
    awk -v keep="^\"($B|${X:-$B}|$tmp/w)/" 'FNR == 1 {on = 1} /^\[ *59\] execve\(/ && / = 0$/ {
        p = $0; sub(/^\[ *59\] execve\(/, "", p); if (p !~ keep) {on = 0; host[FILENAME] = 1}} on
        END {n = 0; for (f in host) n++; print n > "/dev/stderr"}' "$tmp/tr"/t.* > "$tmp/trace" 2> "$tmp/hosts"
    st=$(tail -1 "$tmp/out")
    if [ "$st" != "status 0" ] || ! grep -q 'execve(' "$tmp/trace"; then
        echo "| $row | $id | FAIL: $st, $(head -c 160 "$tmp/err" | tr '\n|' '  ') | | | | |"; fail=1; continue
    fi
    sed -n 's/^\[ *\([0-9]*\)\] [a-z_0-9]*(.*/\1/p' "$tmp/trace" | LC_ALL=C sort -u > "$tmp/made"
    comm -23 "$tmp/made" "$tmp/have" > "$tmp/absent"
    comm -12 "$tmp/made" "$tmp/stub" > "$tmp/stubs"
    sed -n 's/^\[ *16\] ioctl([0-9]*, \([A-Za-z0-9_]*\).*/\1/p' "$tmp/trace" | LC_ALL=C sort -u | comm -23 - "$tmp/ioctl" > "$tmp/io"
    : > "$tmp/hard"; : > "$tmp/soft"; split=""
    [ -s "$tmp/absent" ] && run "-o /dev/null" "$tmp/d1"
    if [ -s "$tmp/absent" ] && ! cmp -s "$tmp/d0" "$tmp/d1"; then
        split=unstable
    elif [ -s "$tmp/absent" ]; then
        run "-o /dev/null -e inject=$(paste -sd, "$tmp/absent"):error=ENOSYS" "$tmp/da"
        if cmp -s "$tmp/d0" "$tmp/da"; then
            cp "$tmp/absent" "$tmp/soft"
        else
            for n in $(cat "$tmp/absent"); do
                run "-o /dev/null -e inject=$n:error=ENOSYS" "$tmp/dn"
                if cmp -s "$tmp/d0" "$tmp/dn"; then echo "$n" >> "$tmp/soft"; else echo "$n" >> "$tmp/hard"; fi
            done
            [ -s "$tmp/hard" ] || { cp "$tmp/absent" "$tmp/hard"; : > "$tmp/soft"; split="together: "; }
        fi
    fi
    cat "$tmp/hard" >> "$tmp/all-hard"; cat "$tmp/soft" >> "$tmp/all-soft"; cat "$tmp/io" >> "$tmp/all-io"
    made=$(wc -l < "$tmp/made"); h=$(cat "$tmp/hosts")
    [ "$h" = 0 ] || made="$made; $h host execs cut"
    if [ "$split" = unstable ]; then
        echo "| $row | $id | $made | unstable: $(label "$tmp/absent") | | $(label "$tmp/stubs") | $(paste -sd' ' "$tmp/io") |"
    else
        echo "| $row | $id | $made | $split$(label "$tmp/hard") | $(label "$tmp/soft") | $(label "$tmp/stubs") | $(paste -sd' ' "$tmp/io") |"
    fi
done < "$cases"
LC_ALL=C sort -u "$tmp/all-hard" > "$tmp/u-hard"
LC_ALL=C sort -u "$tmp/all-soft" | comm -23 - "$tmp/u-hard" > "$tmp/u-soft"
echo "| all | union | | $(label "$tmp/u-hard") | $(label "$tmp/u-soft") | | $(sort -u "$tmp/all-io" | paste -sd' ') |"
exit $fail
