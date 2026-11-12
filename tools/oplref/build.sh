#!/bin/sh
# tools/oplref/build.sh SRC OUT: the OPL3 reference tool, ymfm's YMF262 (SRC is ymfm's src directory, as
# tools/oplref/fetch.sh leaves it) driven by tools/oplref/ref.cpp, into OUT/oplref. Host only, never shipped.
set -eu
src=$1; out=$2
here=$(cd "$(dirname "$0")" && pwd)
: "${CXX:=c++}"
mkdir -p "$out"
$CXX -std=c++14 -O2 -w -I"$src" -o "$out/oplref" "$here/ref.cpp" \
    "$src/ymfm_opl.cpp" "$src/ymfm_adpcm.cpp" "$src/ymfm_pcm.cpp" "$src/ymfm_ssg.cpp" "$src/ymfm_misc.cpp"
echo "$out/oplref"
