#!/usr/bin/env bash
# tools/oracle-vim.sh PREFIX: cvim's Vim oracle (ruling A, l 2026-11-10 15:43Z), Vim v9.1.1752 (commit fe0061c) built
# from source in the Ubuntu 24.04 container daphnis-u2404 (gcc 13.3.0, libncurses-dev, make) and installed into
# PREFIX, a path under $HOME the container shares. tests/cvim/VIM_VERSION is the first two lines of its
# `vim --version` joined by "; ", so a new build repins it (its compile time is part of the line).
set -eu
prefix=$1
src=$prefix-src
rm -rf "$src"
git clone -q --depth 1 --branch v9.1.1752 https://github.com/vim/vim "$src"
[ "$(git -C "$src" rev-parse --short=7 HEAD)" = fe0061c ] || { echo "oracle-vim.sh: v9.1.1752 is not fe0061c" >&2; exit 1; }
podman exec -w "$src" daphnis-u2404 bash -c "./configure --prefix='$prefix' --with-features=huge --enable-gui=no \
    --without-x --disable-gpm --disable-sysmouse --disable-netbeans --disable-canberra --disable-libsodium \
    --with-tlib=ncurses >/dev/null && make -j6 >/dev/null && make install >/dev/null"
podman exec daphnis-u2404 "$prefix/bin/vim" --version | head -2
