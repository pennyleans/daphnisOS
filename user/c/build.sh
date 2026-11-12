#!/usr/bin/env bash
# user/c/build.sh [NAME...]: builds the C probes of user/c, each user/c/NAME.c into $CI_OUT/NAME: musltest, mchurn
# (R-2d), mrng (A-3), mmeta (BU-2a), mexe (BU-4f), mvfork (BU-4a), mlogin (AC-1a), mperm (FS-1), mstamp (FS-4), mfacts
# (KF-3b), mnofollow (FS-5), mrevoke (GV-1a), mcut (GV-1b), mring (GV-1c), mzkill (KILL-Z), mexepath (AC-T2) and
# mresize, or only the NAMEs given, with the host's musl-gcc (static, -O2, stripped), and prints each SHA-256. The
# pinned bytes (tests/expected) are the gate's (ruling DU-2 A): a host whose musl differs builds a different file,
# which is a note, not a failure.
# CI_OUT (default the Makefile's own O/ubin, $TMPDIR/daphnis-build/ubin; relative to the repository's root) builds
# into another directory. Never the tree's user/bin, which holds NOTICE alone (RG-1).
set -eu
cd "$(dirname "$0")/../.."
out=${CI_OUT:-${TMPDIR:-/tmp}/daphnis-build/ubin}
mkdir -p "$out"
for p in ${@:-musltest mchurn mrng mmeta mexe mvfork mlogin mperm mstamp mfacts mnofollow mrevoke mcut mring mzkill mexepath mresize}; do
    musl-gcc -std=c17 -Wall -Wextra -static -O2 -fno-asynchronous-unwind-tables -s -o "$out/$p" "user/c/$p.c"
    sha256sum "$out/$p"
done
