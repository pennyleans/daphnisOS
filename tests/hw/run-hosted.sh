#!/usr/bin/env bash
# tests/hw/run-hosted.sh B [TREE]: the hosted I219-V tests (tests/hw/i219_test.ci) in a root of their own under B:
# src/e1000.ci and the pure modules it needs, with tests/hw/hosted/src/*.ci in place of pci, phys, pit, serial and
# mmio. src/e1000.ci declares rt/mmio.c's rows itself (its place in the build order comes before src/mmio.ci's), so
# the copy here imports the hosted mmio.ci instead: the three extern lines go, the calls are qualified. Nothing else in
# the driver's text changes. TREE (default .) is the tree to test; tests/hw/i219_mutants.py passes a mutated copy.
#   CINT_TOOLCHAIN as for check.sh; cint on PATH.
set -eu
B=$1
T=${2:-.}
hr=$B/hosted-i219
rm -rf "$hr"
mkdir -p "$hr/src" "$hr/tests/hw"
cp "$T/src/sha256.ci" "$T/src/frames.ci" "$T/src/text.ci" "$hr/src/"
cp "$T/tests/hosted/src/bits.ci" "$hr/src/bits.ci"
cp "$T"/tests/hw/hosted/src/*.ci "$hr/src/"
sed -e '/^extern .* mmio_\(map\|in32\|out32\)(/d' \
    -e 's/^import src\.pit;$/import src.pit;\nimport src.mmio;/' \
    -e 's/\bmmio_\(map\|in32\|out32\)(/mmio.mmio_\1(/g' "$T/src/e1000.ci" > "$hr/src/e1000.ci"
cp "$T/tests/hw/i219_test.ci" "$hr/tests/hw/"
exec cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root "$hr" tests/hw/i219_test.ci
# SPDX-License-Identifier: Apache-2.0
