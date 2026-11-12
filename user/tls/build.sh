#!/usr/bin/env bash
# user/tls/build.sh TARBALL [OUT]: builds BearSSL 0.6 for agent's TLS (A-4, ruling AG-2 A) into OUT (else CI_TLS,
# which user/ci/build.sh reads; one of the two must be given): OUT/libbearssl.a and OUT/inc, static, with
# musl-gcc (CI_CC) and the flags user/ci/build.sh gives a program. TARBALL is bearssl_0.6+dfsg.1.orig.tar.xz of
# the Ubuntu archive (upstream 0.6 less T0Comp.exe, a prebuilt compiler of the T0 sources, which the build does not
# use), checked against its SHA-256; it is not in the repository, as busybox's is not. The options: no entropy of
# the system's (BR_RDRAND, BR_USE_URANDOM 0), since tls_open seeds the engine from getrandom, which Daphnis
# journals (A-3); no AES-NI, SSE2 or POWER8 code, so every host runs the same portable constant-time paths; the
# date from time(2), which is Daphnis's CLOCK_REALTIME.
set -euo pipefail
tarball=${1:?pass TARBALL, bearssl_0.6+dfsg.1.orig.tar.xz of the Ubuntu archive}
out=${2:-${CI_TLS:?pass OUT or set CI_TLS to the BearSSL build directory}}
cc=${CI_CC:-musl-gcc}
want=102a625bd8f6155260867a50c508df8d8c3f796985dd744df1a68e5cd1a79004
echo "$want  $tarball" | sha256sum --quiet -c -
work=$(mktemp -d)
trap 'rm -rf "${work:?}"' EXIT
tar -xJf "$tarball" -C "$work"
src=$work/bearssl-0.6
mkdir -p "$work/obj"
(cd "$src" && find src -name '*.c' | LC_ALL=C sort) > "$work/list"
# shellcheck disable=SC2016
xargs -P "$(nproc)" -I{} sh -c 'o=$2/obj/$(echo "$3" | tr / _ | sed "s/\.c$/.o/"); cd "$1" && '"$cc"' -std=c17 -O2 -static \
    -fno-asynchronous-unwind-tables -DBR_RDRAND=0 -DBR_USE_URANDOM=0 -DBR_AES_X86NI=0 -DBR_SSE2=0 -DBR_POWER8=0 \
    -DBR_USE_UNIX_TIME=1 -Isrc -Iinc -c "$3" -o "$o"' _ "$src" "$work" {} < "$work/list"
rm -rf "$out"; mkdir -p "$out"
(cd "$work/obj" && sed 's#/#_#g; s#\.c$#.o#' "$work/list" | xargs ar rcD "$out/libbearssl.a")
cp -r "$src/inc" "$out/inc"
cp "$src/LICENSE.txt" "$out/LICENSE.txt"
sha256sum "$out/libbearssl.a"
