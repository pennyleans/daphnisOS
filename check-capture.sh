#!/usr/bin/env bash
# Synthetic encrypted recording codec, native leaf and host-boundary checks.
set -euo pipefail
cd "$(dirname "$0")"
: "${CINT_TOOLCHAIN:?set CINT_TOOLCHAIN to the pinned compiler toolchain}"
: "${DAPHNIS_BUILD:?set DAPHNIS_BUILD to an output directory outside the repository}"
B=$(realpath -m "$DAPHNIS_BUILD")
case "$B/" in "$PWD/"*) echo 'build outputs must be outside the repository' >&2; exit 2 ;; esac
mkdir -p "$B"
export PYTHONDONTWRITEBYTECODE=1
trap 'echo "RESULT: FAIL (see build output)" >&2' ERR
echo "source $(git rev-parse HEAD)"
sha256sum src/capture*.ci rt/capture_crypto.c rt/capture_crypto.h capture.pin tests/capture/*
cint --version
cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cache" --root . tests/capture/format_test.ci > "$B/format.log" 2>&1
echo "format: $(tail -1 "$B/format.log")"
python3 -B tests/capture/check_crypto.py --build "$B/crypto" > "$B/crypto.log" 2>&1
cat "$B/crypto.log"
python3 -B tests/capture/run_codec.py --root . --out "$B/codec" \
    --toolchain "$CINT_TOOLCHAIN" --cint "$(command -v cint)" > "$B/codec.log" 2>&1
cat "$B/codec.log"
echo 'RESULT: PASS'
