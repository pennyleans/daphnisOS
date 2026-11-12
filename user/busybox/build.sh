#!/usr/bin/env bash
# user/busybox/build.sh TARBALL OUT [net|oracle]: builds a static musl busybox 1.36.1 into the directory OUT, with
# user/busybox/config.fragment over `make allnoconfig`. TARBALL is busybox-1.36.1.tar.bz2
# (https://busybox.net/downloads/busybox-1.36.1.tar.bz2; also busybox_1.36.1.orig.tar.bz2 in the Ubuntu archive),
# checked against its upstream SHA-256. Needs musl-gcc, make, gcc (the host tools), bzip2.
# DOS-3: busybox is not part of Daphnis. The repository holds no tarball and no binary, only this recipe; the gates
# run busybox as an oracle on Linux, never inside Daphnis, and build it through user/busybox/oracle.sh.
#   no variant: OUT/busybox, ash and the applets the gates' Linux sessions compare against (check-cish.sh).
#   net (N-3): OUT/busybox-net, config.fragment then net.fragment (wget, md5sum): the oracle of fetch.
#   oracle (CT-4): OUT/busybox-oracle, config.fragment then oracle.fragment (the applets and features of the core
#   set's section 8): the oracle of check-core.sh.
# The build tree is a temporary directory, removed on exit; the binary lands under its final name in one rename, so
# two gates building at once never see half a file.
set -euo pipefail
[ $# -ge 2 ] || { echo "usage: user/busybox/build.sh TARBALL OUT [net|oracle]" >&2; exit 2; }
tarball=$1
out=$2
variant=${3:-}
case $variant in '' | net | oracle) ;; *) echo "build.sh: no variant $variant (net, oracle)" >&2; exit 2 ;; esac
want=b8cc24c9574d809e7279c3be349795c5d5ceb6fdf19ca709f80cde50e47de314
here=$(cd "$(dirname "$0")" && pwd)
echo "$want  $tarball" | sha256sum --quiet -c -
mkdir -p "$out"
build=$(mktemp -d "$out/.build.XXXXXX")
trap 'rm -rf "$build"' EXIT
tar -xjf "$tarball" -C "$build"
src=$build/busybox-1.36.1
make -s -C "$src" allnoconfig > /dev/null
python3 - "$src/.config" "$here/config.fragment" ${variant:+"$here/$variant.fragment"} <<'PY'
import re, sys
cfg, frags = sys.argv[1], sys.argv[2:]
s = open(cfg).read()
for line in (l for f in frags for l in open(f)):
    line = line.strip()
    m = re.match(r'^CONFIG_(\w+)=(.*)$', line) or re.match(r'^# CONFIG_(\w+) is not set$', line)
    if not m:
        continue
    name = m.group(1)
    pat = re.compile(r'^(# )?CONFIG_%s(=.*| is not set)$' % re.escape(name), re.M)
    s = pat.sub(line, s, count=1) if pat.search(s) else s + line + "\n"
open(cfg, "w").write(s)
PY
make -s -C "$src" oldconfig < /dev/null > /dev/null
make -s -C "$src" -j"$(nproc)" CC=musl-gcc HOSTCC=gcc busybox > "$build/make.log" 2>&1 \
    || { tail -20 "$build/make.log" >&2; exit 1; }
bin=$out/busybox${variant:+-$variant}
cp "$src/busybox" "$build/busybox"
mv -f "$build/busybox" "$bin"
sha256sum "$bin"
