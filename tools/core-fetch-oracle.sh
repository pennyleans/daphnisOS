#!/bin/sh
# tools/core-fetch-oracle.sh ORACLE ARG...: busybox-net's wget as the oracle of fetch for check-core.sh (BU-5a,
# docs/specs/2026-11-07-bu5-fetch.md): fetch's `-o FILE` is wget's `-O FILE`, and fetch is as quiet as wget -q.
o=$1
shift
n=$#
i=0
while [ "$i" -lt "$n" ]; do
    a=$1
    shift
    [ "$a" = -o ] && a=-O
    set -- "$@" "$a"
    i=$((i + 1))
done
exec "$o" wget -q "$@"
