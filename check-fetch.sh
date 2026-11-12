#!/usr/bin/env bash
# Build fetch on three host configurations and exercise HTTPS in Daphnis.
set -euo pipefail
cd "$(dirname "$0")"
: "${CINT_TOOLCHAIN:?set CINT_TOOLCHAIN to the pinned compiler toolchain}"
: "${CI_TLS:?set CI_TLS to the pinned BearSSL build}"
: "${DAPHNIS_BUILD:?set DAPHNIS_BUILD to an output directory outside the repository}"
B=$(realpath -m "$DAPHNIS_BUILD")
case "$B/" in "$PWD/"*) echo 'build outputs must be outside the repository' >&2; exit 2 ;; esac
mkdir -p "$B"
export PYTHONDONTWRITEBYTECODE=1
trap 'echo "RESULT: FAIL (see build output)" >&2' ERR
echo "source $(git rev-parse HEAD)"
sha256sum user/ci/fetch.ci user/ci/http.ci user/ci/url.ci user/ci/host.c user/ci/tls.ci tools/check-fetch-https.py tools/check-fetch-redirect.py check-fetch.sh
cint --version
for suite in url_test http_redirect_test; do
    cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/test-cache" --root . "tests/fetch/$suite.ci" > "$B/$suite.log" 2>&1
    echo "$suite: $(tail -1 "$B/$suite.log")"
done
for cc in musl-gcc gcc clang; do
    CI_CC=$cc CI_OUT="$B/$cc" user/ci/build.sh fetch > "$B/build-$cc.log" 2>&1
    python3 -B tools/check-fetch-https.py "$B/$cc/fetch" > "$B/test-$cc.log" 2>&1
    echo "$cc: $(tail -1 "$B/test-$cc.log")"
    python3 -B tools/check-fetch-redirect.py "$B/$cc/fetch" > "$B/redirect-$cc.log" 2>&1
    echo "$cc redirects: $(tail -1 "$B/redirect-$cc.log")"
done
make -s -j4 O="$B/net" FLAVORS=net all > "$B/build-net.log" 2>&1
for cc in gcc clang; do
    python3 -B tools/check-fetch-https.py "$B/musl-gcc/fetch" \
        --kernel "$B/net/$cc-net/kernel32.elf" --out "$B/guest-$cc" > "$B/guest-$cc.log" 2>&1
    echo "daphnis $cc: $(tail -1 "$B/guest-$cc.log")"
done
echo 'RESULT: PASS'
