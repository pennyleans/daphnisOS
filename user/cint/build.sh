#!/usr/bin/env bash
# user/cint/build.sh CINT_OUT CINT_SRC [WORK]: builds user/cint/opt, the SW-2 toolchain the image build writes to
# /home/opt/cint (docs/specs/2026-11-07-bu4-toolchain.md 4.3 to 4.6, unit BU-4b; DU-2: every file is committed, with
# this script to build it again). CINT_OUT is the output directory of the pinned cint's `tools/cint_bootstrap.py
# --leg gcc` (toolchain.pin: public v0.2.18, a14a03f3; the public bootstrap writes no lib/ beside cint, so copy the
# checkout's lib/ there first), CINT_SRC a checkout of that commit. Needs musl-gcc, ar, and cib built by
# user/ci/build.sh (the cint on PATH must be CINT_OUT's). WORK (default a new temporary directory) keeps the steps.
#   cint          the bootstrap's release objects (the compiler S1, the runtime, the bridge, rt/cint_build.c, the
#                 CLI with the compiler source identity) compiled again by musl-gcc, -O2, builtin helpers, static,
#                 stripped
#   lib/, compiler.cisrc   the standard service modules and the compiler manifest, as the bootstrap put them beside cint
#   musl/         crt1.o, crti.o, crtn.o and libc.a of the host's musl
#   libcli.a      BU-4h1: those same CLI, bridge and build objects (not the compiler's) and the runtime with portable
#                 helpers (the builtin ones call libgcc's __udivti3, and cint ld links no libgcc), one archive, for
#                 `cib --self` (Q4's link of cint's tools/cint_qbe_selfhost.py)
#   src/compiler/ BU-4h1: the compiler's sources as the bootstrap read them (compiler.cisrc's files; its digest is the
#                 identity)
#   libci.a       the runtime (rt/cint_rt.c, which holds the cpu-qbe entry points) and the runner shim: user/ci/runner.c,
#                 and user/ci/main.c and host.c with every row but TLS (4.1); musl-gcc -O2, portable helpers
#   as, ld        cint-as (toolchain/as/main.ci) and cint ld (link/ld.ci) built by cib -r through QBE, first with the
#                 C leg's tools (emit-c and musl-gcc), then again with themselves, which must give the same bytes
#   cib           user/ci/cib.ci built by the given cib (CIB) through these tools and the shim, then by itself, which
#                 must give the same bytes
#   qbe, make     not here: user/qbe/build.sh and user/pdpmake/build.sh
#   cpu-qbe.toolchain   cint's toolchain file for /home/opt/cint: backend cpu-qbe, every path under it, the digests
# Prints each file's SHA-256. A host whose gcc or musl differs builds other bytes for cint, libci.a and musl/, which is a
# note, not a failure; as and ld are QBE's and cint-as's output and must not move.
set -euo pipefail
cint_out=$(cd "$1" && pwd)
cint_src=$(cd "$2" && pwd)
work=${3:-$(mktemp -d)}
mkdir -p "$work"
work=$(cd "$work" && pwd)
here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$here/../.." && pwd)
opt=$here/opt
prefix=/home/opt/cint
M=/usr/lib/musl/lib
bd=$(dirname "$(awk '$1=="compiler_sources" {print $2}' "$cint_out/cint.toolchain")")
inc=$bd/inputs/rt
ident=$(sha256sum "$bd/compiler.cisrc" | cut -d' ' -f1)
rel="-std=c17 -O2 -DCINT_RT_HELPERS_BUILTIN -fno-asynchronous-unwind-tables -I$inc"
por="-std=c17 -O2 -DCINT_RT_HELPERS_PORTABLE -fno-asynchronous-unwind-tables -I$inc"
rows="-DCI_ROWS_CORE -DCI_ROWS_DSP -DCI_ROWS_GRANT -DCI_ROWS_HDESK -DCI_ROWS_META -DCI_ROWS_NET -DCI_ROWS_PLACE"
rows="$rows -DCI_ROWS_PTY -DCI_ROWS_RUN -DCI_ROWS_SH -DCI_ROWS_SIG -DCI_ROWS_TCP -DCI_ROWS_WALL -DCI_ROWS_WIN"
cib=${CIB:-$work/cib}
mkdir -p "$opt/musl" "$work/o"

# cint
for f in "$bd/s1/main.c" "$inc/cint_rt.c" "$inc/cint_bridge.c" "$inc/cint_build.c"; do
    musl-gcc $rel -c "$f" -o "$work/o/rel-$(basename "$f" .c).o"
done
for f in cint_main cint_receipt cint_discover cint_cache cint_diag cint_proc_posix; do
    musl-gcc $rel "-DCINT_COMPILER_SOURCE_IDENTITY=\"$ident\"" -c "$bd/inputs/cli/$f.c" -o "$work/o/cli-$f.o"
done
musl-gcc -static -s -o "$opt/cint" "$work"/o/cli-cint_main.o "$work"/o/cli-cint_receipt.o "$work"/o/cli-cint_discover.o \
    "$work"/o/cli-cint_cache.o "$work"/o/cli-cint_diag.o "$work"/o/cli-cint_proc_posix.o "$work"/o/rel-main.o \
    "$work"/o/rel-cint_rt.o "$work"/o/rel-cint_bridge.o "$work"/o/rel-cint_build.o
rm -rf "$opt/lib"
cp -R "$cint_out/lib" "$opt/lib"
cp "$bd/compiler.cisrc" "$opt/compiler.cisrc"
cp "$M/crt1.o" "$M/crti.o" "$M/crtn.o" "$M/libc.a" "$opt/musl/"
musl-gcc $por -c "$inc/cint_rt.c" -o "$work/o/cint_rt.o"
rm -f "$opt/libcli.a"
(cd "$work/o" && ar rcD "$opt/libcli.a" cli-cint_main.o cli-cint_receipt.o cli-cint_discover.o cli-cint_cache.o \
    cli-cint_diag.o cli-cint_proc_posix.o cint_rt.o rel-cint_bridge.o rel-cint_build.o)
rm -rf "$opt/src"
mkdir -p "$opt/src/compiler"
cp "$bd"/inputs/compiler/*.ci "$opt/src/compiler/"

# libci.a
musl-gcc $por -I"$repo/user/ci" $rows -Dmain=ci_daphnis_main -DCI_RUN=ci_run_trampoline -c "$repo/user/ci/main.c" -o "$work/o/main.o"
musl-gcc $por -I"$repo/user/ci" $rows -c "$repo/user/ci/host.c" -o "$work/o/host.o"
musl-gcc $por -Wall -Wextra -c "$repo/user/ci/runner.c" -o "$work/o/runner.o"
rm -f "$opt/libci.a"
(cd "$work/o" && ar rcD "$opt/libci.a" runner.o main.o host.o cint_rt.o)

# toolchain DIR PREFIX AS LD: DIR/cpu-qbe.toolchain naming PREFIX's files, the assembler AS and the linker LD.
toolchain() {
    local d=$1 p=$2
    {
        echo "cint-toolchain-1"
        echo "leg gcc"
        echo "cc /nonexistent-c-driver"
        echo "compiler_sources $p/compiler.cisrc"
        echo "executable_sha256 $(sha256sum "$opt/cint" | cut -d' ' -f1)"
        echo "host Daphnis"
        echo "include $p/include"
        echo "runtime_object $p/libci.a"
        echo "flag -std=c17"
        echo "runtime_source $p/rt/cint_rt.c"
        echo "backend cpu-qbe"
        echo "qbe $p/qbe"
        echo "qbe_commit c0818978acec60ebb6167fade60fb7012cbf20ca"
        echo "qbe_sha256 $(sha256sum "$opt/qbe" | cut -d' ' -f1)"
        echo "target amd64_sysv"
        echo "assembler $3"
        echo "linker $4"
        echo "link_before $p/musl/crt1.o"
        echo "link_before $p/musl/crti.o"
        echo "link_after $p/musl/libc.a"
        echo "link_after $p/musl/crtn.o"
    } > "$d/cpu-qbe.toolchain"
}

# as and ld: the C leg's first (the runtime's own main, as cint run gives it), then cib -r with them, then with itself.
lin=$work/lin
rm -rf "$lin" "$work/boot" "$work/q1" "$work/q2"
mkdir -p "$work/boot" "$work/q1" "$work/q2"
cp -R "$opt" "$lin"
cleg() {   # cleg NAME MODULE...
    local n=$1; shift
    (cd "$cint_src" && "$cint_out/cint" emit-c --toolchain "$cint_out/cint.toolchain" --root . --out "$work/boot/$n.e" "$@")
    local c="$work/boot/$(cut -d' ' -f1 "$work/boot/$n.e/MANIFEST.ref")"
    # shellcheck disable=SC2046
    musl-gcc $por -static -s -o "$work/boot/$n" $(find "$c" -name '*.c' | LC_ALL=C sort) "$inc/cint_rt.c"
}
cleg as toolchain/as/text.ci toolchain/as/x86.ci toolchain/as/obj.ci toolchain/as/elf.ci toolchain/as/asm.ci toolchain/as/main.ci
cleg ld link/le.ci link/core.ci link/ld.ci
for round in q1 q2; do
    if [ $round = q1 ]; then toolchain "$lin" "$lin" "$work/boot/as" "$work/boot/ld"
    else toolchain "$lin" "$lin" "$work/q1/as" "$work/q1/ld"; fi
    (cd "$cint_src" && "$cib" -r -t "$lin/cpu-qbe.toolchain" "$work/$round/as" toolchain/as/main.ci)
    (cd "$cint_src" && "$cib" -r -t "$lin/cpu-qbe.toolchain" "$work/$round/ld" link/ld.ci)
done
cmp "$work/q1/as" "$work/q2/as" && cmp "$work/q1/ld" "$work/q2/ld"
cp "$work/q2/as" "$work/q2/ld" "$opt/"
# cib itself, through the toolchain and the runner shim: built by the given cib, then by itself, the same bytes
toolchain "$lin" "$lin" "$work/q2/as" "$work/q2/ld"
cp "$opt/libci.a" "$lin/libci.a"
(cd "$repo" && "$cib" -t "$lin/cpu-qbe.toolchain" "$work/q1/cib" user/ci/cib.ci)
(cd "$repo" && "$work/q1/cib" -t "$lin/cpu-qbe.toolchain" "$work/q2/cib" user/ci/cib.ci)
cmp "$work/q1/cib" "$work/q2/cib"
cp "$work/q2/cib" "$opt/"
toolchain "$opt" "$prefix" "$prefix/as" "$prefix/ld"
(cd "$opt" && find . -type f | LC_ALL=C sort | sed 's|^\./||' | xargs sha256sum)
