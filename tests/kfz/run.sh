#!/usr/bin/env bash
# tests/kfz/run.sh: the kernel fault and fuzz tests, hosted (tests/kfz/hostroot.py builds the kernel they run in),
# twice: with a test process's pages backed and filled before its first call, then with them promises a call's own
# touch backs (k0_kit.ci's KZ_LAZY); then HW-14's console cases, C on the host (tests/kfz/console.sh). Last line:
# "N of M tests passed", all three. Exit status 1 if any failed.
#   tests/kfz/run.sh              the suite, which passes at this tree
#   tests/kfz/run.sh --defects    the suite, then tests/kfz/defects/*.ci: the findings not yet fixed, which fail
# Needs python3, gcc with ASan and the cint of toolchain.pin on PATH; CINT_TOOLCHAIN
# names its toolchain file as for check.sh. The build goes to $DAPHNIS_BUILD/kfz (default
# $TMPDIR/daphnis-build/kfz), cleared first.
set -eu
cd "$(dirname "$0")/../.."
B=${DAPHNIS_BUILD:-${TMPDIR:-/tmp}/daphnis-build}/kfz
rm -rf "$B"
mkdir -p "$B"
python3 tests/kfz/hostroot.py "$@" "$B/backed"
python3 tests/kfz/hostroot.py --lazy "$@" "$B/promised"
tc=()
if [ -n "${CINT_TOOLCHAIN:-}" ]; then
    tc=(--toolchain "$CINT_TOOLCHAIN")
fi
status=0
passed=0
total=0
for mode in backed promised; do
    echo "== $mode"
    set +e
    (cd "$B/$mode" && cint test "${tc[@]}" --cache "$B/cache-$mode" --root . src/proc.ci) | tee "$B/$mode.log"
    rc=${PIPESTATUS[0]}
    set -e
    if [ "$rc" -ne 0 ]; then
        status=1
    fi
    line=$(grep -E '^[0-9]+ of [0-9]+ tests passed' "$B/$mode.log" | tail -1 || true)
    if [ -z "$line" ]; then
        echo "kfz: the $mode pass gave no count" >&2
        status=1
        continue
    fi
    set -- $line
    passed=$((passed + $1))
    total=$((total + $3))
done
echo "== console"
set +e
bash tests/kfz/console.sh | tee "$B/console.log"
rc=${PIPESTATUS[0]}
set -e
if [ "$rc" -ne 0 ]; then
    status=1
fi
line=$(grep -E '^[0-9]+ of [0-9]+ tests passed' "$B/console.log" | tail -1 || true)
if [ -z "$line" ]; then
    echo "kfz: the console cases gave no count" >&2
    status=1
else
    set -- $line
    passed=$((passed + $1))
    total=$((total + $3))
fi
echo "$passed of $total tests passed"
exit $status
