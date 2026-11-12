#!/usr/bin/env bash
# Qualify the native HTML input modules against pinned external cases.
set -euo pipefail
cd "$(dirname "$0")"
identity_args=()
if [[ -v CINT_EXPECTED_SOURCE_ID || -v CINT_EXPECTED_SHA256 ]]; then
    if [[ ! -v CINT_EXPECTED_SOURCE_ID || ! -v CINT_EXPECTED_SHA256 ]]; then
        echo 'compiler identity source and SHA-256 must be supplied together' >&2; exit 2
    fi
    if [[ ! $CINT_EXPECTED_SOURCE_ID =~ ^[0-9a-f]{64}$ || ! $CINT_EXPECTED_SHA256 =~ ^[0-9a-f]{64}$ ]]; then
        echo 'compiler identity values must be 64 lowercase hexadecimal digits' >&2; exit 2
    fi
    identity_args=(--compiler-source-id "$CINT_EXPECTED_SOURCE_ID" --compiler-sha256 "$CINT_EXPECTED_SHA256")
fi
: "${CINT_TOOLCHAIN:?set CINT_TOOLCHAIN}"
: "${DAPHNIS_BUILD:?set DAPHNIS_BUILD outside the repository}"
B=$(realpath -m "$DAPHNIS_BUILD")
case "$B/" in "$PWD/"*) echo 'build outputs must be outside the repository' >&2; exit 2 ;; esac
mkdir -p "$B"
export PYTHONDONTWRITEBYTECODE=1
trap 'echo "RESULT: FAIL (see build output)" >&2' ERR
echo "source $(git rev-parse HEAD)"
cint --version
python3 -B tests/html/run_references.py --out "$B/references" \
    --cint "$(command -v cint)" --toolchain "$CINT_TOOLCHAIN" > "$B/references.log" 2>&1
cat "$B/references.log"
python3 -B tools/html/check-tokenizer.py --out "$B/tokenizer" \
    --cint "$(command -v cint)" --toolchain "$CINT_TOOLCHAIN" > "$B/tokenizer.log" 2>&1
cat "$B/tokenizer.log"
python3 -B tools/html/check-encoding.py --out "$B/encoding" \
    --cint "$(command -v cint)" --toolchain "$CINT_TOOLCHAIN" "${identity_args[@]}" > "$B/encoding.log" 2>&1
cat "$B/encoding.log"
python3 -B tools/html/check-html-bytes.py --out "$B/html-bytes" \
    --cint "$(command -v cint)" --toolchain "$CINT_TOOLCHAIN" "${identity_args[@]}" > "$B/html-bytes.log" 2>&1
cat "$B/html-bytes.log"
echo 'RESULT: PASS'
