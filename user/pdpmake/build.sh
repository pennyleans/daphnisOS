#!/usr/bin/env bash
# user/pdpmake/build.sh TARBALL [BUILDDIR]: builds user/cint/opt/make, pdpmake 2.0.4 (POSIX make, public domain) static
# against musl, the make of the SW-2 toolchain (docs/specs/2026-11-07-bu4-toolchain.md 4.8; SW-5 A; DU-2: the binary
# is committed, with this script to build it again). TARBALL is pdpmake-2.0.4.tgz (https://frippery.org/make/),
# checked against its SHA-256; its tree is tag 2.0.4 of https://github.com/rmyorston/pdpmake (commit 0faaf258). Its own
# Makefile, with musl-gcc, -O2, static, stripped. It runs every recipe through system(), so it needs K12 (BU-4a) and a
# /bin/sh. Prints the binary's SHA-256. A host whose musl or gcc differs builds a different file, which is a note, not
# a failure. Needs musl-gcc, make, gzip. The tarball is not in the repository.
set -euo pipefail
tarball=$1
build=${2:-$(mktemp -d)}
want=7e19294d54edf360591d76d3b7a0a511864902ac3a75a0b5b11c7b3cae14c13f
here=$(cd "$(dirname "$0")" && pwd)
echo "$want  $tarball" | sha256sum --quiet -c -
mkdir -p "$build"
tar -xzf "$tarball" -C "$build"
src=$build/pdpmake-2.0.4
make -s -C "$src" CC=musl-gcc CFLAGS="-std=c99 -O2" LDFLAGS="-static -s" make
mkdir -p "$here/../cint/opt"
cp "$src/make" "$here/../cint/opt/make"
sha256sum "$here/../cint/opt/make"
