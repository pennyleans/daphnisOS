#!/usr/bin/env bash
# tools/doom/mktree.sh OUT: builds the freedoom-ci tree (docs/specs/2026-11-08-doom-split.md, step DS-2) from this
# checkout into OUT, a new directory, and commits it there as one commit in a fresh git repository. Pushes nothing.
#
#   daphnis-dev                         freedoom-ci
#   user/ci/doom/*.ci, client.c, build.sh   src/            (notice header added; imports user.ci.doom. -> src.)
#   user/ci/doom/COPYING                COPYING
#   user/ci/doom/data/                  data/
#   user/bin/doom                       bin/doom        (bytes unchanged; pinned by tests/expected/doom.sha256)
#   src/sha256.ci, user/ci/dev.ci,      src/            (bytes unchanged; the Apache-2.0 files the port links,
#   user/ci/host.c, user/ci/host.h                       granted under GPL-2.0 too: LICENSES.md)
#   tools/doomref, tools/doomdata,      tools/
#   tools/episode-cut.sh, check-doom.py, check-episode.py
#   tests/episode, the doom and episode goldens of tests/expected   tests/   (doom.serial, a Daphnis transcript, stays)
#   check-episode.sh                    check.sh
#
# The commit's dates are this checkout's HEAD commit date, so one daphnis-dev commit gives one freedoom-ci commit.
# Run it from a commit that still has the Doom files, one from before DS-3 removes them.
# Text files get the path rewrites of `rewrite` below; WADs, tables, demos and the binary keep their bytes.
set -eu
cd "$(dirname "$0")/../.."
out=${1:?usage: tools/doom/mktree.sh OUT}
[ -e "$out" ] && { echo "mktree.sh: $out exists"; exit 1; }
here=$(git rev-parse --short=8 HEAD)
export GIT_AUTHOR_DATE GIT_COMMITTER_DATE
GIT_AUTHOR_DATE=$(git log -1 --format=%cI HEAD) GIT_COMMITTER_DATE=$GIT_AUTHOR_DATE

mkdir -p "$out"/{src,data,bin,tools,tests/episode,tests/expected}
cp user/ci/doom/*.ci user/ci/doom/client.c user/ci/doom/build.sh "$out/src/"
cp src/sha256.ci user/ci/dev.ci user/ci/host.c user/ci/host.h "$out/src/"
cp user/ci/doom/COPYING "$out/COPYING"
cp user/ci/doom/data/* "$out/data/"
cp user/bin/doom "$out/bin/doom"
cp -r tools/doomref tools/doomdata "$out/tools/"
cp tools/episode-cut.sh tools/check-doom.py tools/check-episode.py "$out/tools/"
cp tests/episode/*.lmp "$out/tests/episode/"
for f in doom.sha256 doom.tics doom-sfx48.sha256 doomref.txt doomref-sfx3.txt doomref-sfx8.txt \
         episode.sha256 episode.tics episode-ta.tics episoderef-ta.txt episoderef-tb.txt episoderef-tc.txt; do
    cp "tests/expected/$f" "$out/tests/expected/"
done
cp check-episode.sh "$out/check.sh"

# the path rewrites, longest first; the copied Apache files (sha256.ci, dev.ci, host.c, host.h) keep their bytes
rewrite() {
    sed -i -e 's#user/ci/doom/data#data#g' -e 's#user/ci/doom/#src/#g' -e 's#user/ci/doom\b#src#g' \
           -e 's#user/ci/dev\.ci#src/dev.ci#g' -e 's#user/ci/host\.\([ch]\)\b#src/host.\1#g' -e 's#-Iuser/ci\b#-Isrc#g' \
           -e 's#user/bin/doom#bin/doom#g' -e 's#import user\.ci\.doom\.#import src.#g' -e 's#import user\.ci\.dev;#import src.dev;#g' \
           -e 's#check-episode\.sh#check.sh#g' -e 's#DAPHNIS_BUILD#DOOM_BUILD#g' -e 's#daphnis-work/build-episode#freedoom-work/build#g' \
           -e 's#\.daphnis-build#.doom-build#g' -e 's#not a Daphnis build directory#not a freedoom-ci build directory#g' "$@"
}
port=$(cd user/ci/doom && ls ./*.ci client.c | sed 's#^\./##')
for f in $port build.sh; do rewrite "$out/src/$f"; done
rewrite "$out/check.sh" "$out/tools/episode-cut.sh" "$out/tools/check-doom.py" "$out/tools/check-episode.py" \
        "$out"/tools/doomref/* "$out"/tools/doomdata/*.py "$out/data/SOURCES.md" \
        "$out/tests/expected/doom.sha256" "$out/tests/expected/episode.sha256"
sed -i 's#cd "$(dirname "$0")/../../.."#cd "$(dirname "$0")/.."#' "$out/src/build.sh"
sed -i "s#mkdir -p user/bin#mkdir -p bin#" "$out/src/build.sh"

# the notice every port file opens with (spec section 3)
for f in $port; do
    if [ "${f##*.}" = c ]; then
        printf '%s\n' '/* Derived from linuxdoom-1.10, Copyright (C) 1993-1996 id Software, Inc.' \
            ' * The cint port: Copyright 2026 The Daphnis authors.' ' * SPDX-License-Identifier: GPL-2.0-only */' > "$out/src/$f.n"
    else
        printf '%s\n' '// Derived from linuxdoom-1.10, Copyright (C) 1993-1996 id Software, Inc.' \
            '// The cint port: Copyright 2026 The Daphnis authors.' '// SPDX-License-Identifier: GPL-2.0-only' > "$out/src/$f.n"
    fi
    cat "$out/src/$f" >> "$out/src/$f.n" && mv "$out/src/$f.n" "$out/src/$f"
done

cat > "$out/README.md" <<'EOF'
# freedoom-ci

A cint port of linuxdoom-1.10 playing Freedoom. Not affiliated with or endorsed by id Software; Doom is a trademark
of id Software. No id Software art is included: the data is cut from Freedoom 0.13.0 (`data/SOURCES.md`).

The port is deterministic: every tic of a demo hashes the game state and the frame into one chain, and the same
demo gives the same chain on every build. `check.sh` proves it on Linux: the committed `bin/doom` and the same
source built by gcc and clang play all of episode 1 against the linuxdoom reference tool's records.

## Layout

| path | holds |
| --- | --- |
| `src/` | the port (cint), its C client `client.c`, `build.sh`, and the four files it links from Daphnis |
| `data/` | the Freedoom cuts, `info.bin` and `tables.bin` (`SOURCES.md` says how each is made) |
| `bin/doom` | the static musl build, pinned by `tests/expected/doom.sha256` |
| `tools/` | the reference tool (`doomref`, fetches linuxdoom at a pinned commit), the data cutters, the checkers |
| `tests/` | the three test demos and the expected records and chains |
| `check.sh` | the gate: one `PASS` or `FAIL` line per check, then `RESULT:` |

## Build and check

Needs cint `cint-v0.2.17` with its `cint.toolchain`, gcc, clang, musl-gcc, python3, git.

```
CINT_TOOLCHAIN=path/to/cint.toolchain ./check.sh
bash src/build.sh                       # rebuilds bin/doom with musl-gcc
bin/doom --headless data/e1.wad data/tables.bin data/info.bin --demo tests/episode/ta.lmp
```

Daphnis (github.com/pennyleans/daphnisOS) runs `bin/doom` in its desk and pins this repository by commit.

## License

GPL-2.0 (`COPYING`). Freedoom data: BSD-3-Clause (`data/COPYING-freedoom.txt`). Per-file terms: `LICENSES.md`.
EOF

cat > "$out/LICENSES.md" <<'EOF'
# Licenses

| files | license | copyright |
| --- | --- | --- |
| `src/*.ci` (but the two below), `src/client.c`, `src/build.sh`, `tools/`, `check.sh` | GPL-2.0-only (`COPYING`) | derived from linuxdoom-1.10, (C) 1993-1996 id Software, Inc.; the port, 2026 The Daphnis authors |
| `src/sha256.ci`, `src/dev.ci`, `src/host.c`, `src/host.h` | Apache-2.0 OR GPL-2.0-only | 2026 The Daphnis authors; copied unchanged from Daphnis, granted here under GPL-2.0 as well so they link into `bin/doom` |
| `data/*.wad` | BSD-3-Clause (`data/COPYING-freedoom.txt`) | contributors to the Freedoom project |
| `data/info.bin`, `data/tables.bin` | GPL-2.0-only | read from linuxdoom-1.10 source, (C) 1993-1996 id Software, Inc. |
| `bin/doom` | GPL-2.0-only; links musl (MIT, `NOTICE`) and the cint hosted runtime (Apache-2.0) | as above |
EOF

cat > "$out/NOTICE" <<'EOF'
bin/doom is statically linked with musl libc, Copyright (C) 2005-2020 Rich Felker, et al., MIT license
(https://musl.libc.org/COPYRIGHT), and with the cint hosted runtime (rt/cint_rt.c), Apache-2.0.
EOF

sed -i 's#^`info.bin` and `tables.bin` are the engine.s own tables#`info.bin` and `tables.bin` (GPL-2.0, as linuxdoom-1.10) are the engine'"'"'s own tables#' "$out/data/SOURCES.md"

git -C "$out" init -q -b main
git -C "$out" -c commit.gpgsign=false -c user.name=pennyleans -c user.email=294672563+pennyleans@users.noreply.github.com add -A
git -C "$out" -c commit.gpgsign=false -c user.name=pennyleans -c user.email=294672563+pennyleans@users.noreply.github.com \
    commit -q -m "freedoom-ci: a cint port of linuxdoom-1.10 playing Freedoom (from daphnis-dev $here)"
echo "commit $(git -C "$out" rev-parse HEAD) tree $(git -C "$out" rev-parse "HEAD^{tree}")"
