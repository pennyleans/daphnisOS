#!/usr/bin/env bash
# user/qbe/build.sh TARBALL [BUILDDIR]: builds user/cint/opt/qbe, QBE 1.3 static against musl, the compiler back end of
# the SW-2 toolchain (docs/specs/2026-11-07-bu4-toolchain.md 4.6; DU-2: the binary is committed, with this script to
# build it again). TARBALL is qbe-1.3.tar.xz (https://c9x.me/compile/release/), checked against its SHA-256; its tree
# is tag v1.3, commit c0818978acec60ebb6167fade60fb7012cbf20ca, the pin of cint's tools/cint_qbe_check.py. QBE's own
# Makefile, with musl-gcc, -O2, static, stripped. Prints the binary's SHA-256. A host whose musl or gcc differs builds
# a different file, which is a note, not a failure. Needs musl-gcc, make, xz. The tarball is not in the repository.
set -euo pipefail
tarball=$1
build=${2:-$(mktemp -d)}
want=d587905d620dc5e1d2bfa7c2cc642b9b837aa89a3188c6e37b53d756cf66e320
here=$(cd "$(dirname "$0")" && pwd)
echo "$want  $tarball" | sha256sum --quiet -c -
mkdir -p "$build"
tar -xJf "$tarball" -C "$build"
src=$build/qbe-1.3
make -s -C "$src" CC=musl-gcc CFLAGS="-std=c99 -O2 -Wall -Wextra -Wpedantic" LDFLAGS="-static -s" qbe
mkdir -p "$here/../cint/opt"
cp "$src/qbe" "$here/../cint/opt/qbe"
sha256sum "$here/../cint/opt/qbe"
