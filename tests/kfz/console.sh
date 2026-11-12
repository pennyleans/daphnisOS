#!/usr/bin/env bash
# tests/kfz/console.sh [ROOT]: HW-14's console cases, tests/kfz/console_user.c, built against ROOT's rt/boot.c,
# rt/console.c and rt/host.c (default: this tree) in the user flavor (RT_USER), with ASan and UBSan, and run. Prints a
# line a case and "N of M tests passed"; exit status 1 if a case failed or the file did not build. tests/kfz/run.sh
# runs it after the hosted passes, tests/kfz/mutants.py on each mutant of rt/. Needs gcc and CINT_TOOLCHAIN for the
# toolchain's cint_rt.h, as for check.sh. Only host.c's port rows are used: section garbage collection drops the rest
# of its table and what it calls, so ASan leaves globals uninstrumented (a global it registers would keep the table).
set -eu
here=$(cd "$(dirname "$0")/../.." && pwd)
root=${1:-$here}
: "${CINT_TOOLCHAIN:?tests/kfz/console.sh needs CINT_TOOLCHAIN (the toolchain file, for cint_rt.h)}"
inc=$(awk '$1=="include" {print $2}' "$CINT_TOOLCHAIN")
B=$(mktemp -d)
trap 'rm -rf "$B"' EXIT
if ! gcc -std=c17 -Wall -Wextra -Wpedantic -Werror -DRT_USER -fsanitize=address,undefined --param asan-globals=0 \
    -fno-pie -no-pie -ffunction-sections -fdata-sections -Wl,--gc-sections -I"$inc" "$root/tests/kfz/console_user.c" \
    -o "$B/console" > "$B/build.log" 2>&1; then
    cat "$B/build.log" >&2
    echo "console: tests/kfz/console_user.c did not build" >&2
    exit 1
fi
"$B/console"
