#!/usr/bin/env bash
# tools/build-ced.sh: builds $CI_OUT/ced, the bundled editor (E-4, docs/specs/2026-11-06-e-editor.md section 3), from
# the ced sources of user/ced/ (ced's own lint keeps shell files out of its tree): ced-dev at the commit of CED_PIN, each file the bytes SOURCES.sha256 names. The pinned
# `cint emit-c` emits ced.ci and its modules in import order, with cint's console and fs services; the emitted main is
# wrapped as `cint build --app --frame-arena 67108864` wraps it (cint's cli/cint_main.c, write_driver), so every word
# after the name is ced's argument and ced has its 8 MiB file (with none, its manifest's grants with /arg1 on
# the working directory inside the home, else on the home: RUN-8, Edit's Untitled); then the host's musl-gcc
# builds it static, -O2, stripped, the unused sections dropped (-Wl,--gc-sections, as user/ci/build.sh), against the
# toolchain's runtime (rt/cint_rt.c, which takes in the services). Prints the SHA-256. CI_CC (default musl-gcc)
# and CI_OUT (default the Makefile's own O/ubin, $TMPDIR/daphnis-build/ubin; never the tree's user/bin, RG-1) build
# the same emitted C with another C17 compiler and libc.
set -eu
cd "$(dirname "$0")/../user/ced"
CINT_TOOLCHAIN=${CINT_TOOLCHAIN:-$(dirname "$(readlink -f "$(command -v cint)")")/cint.toolchain}
inc=$(awk '$1=="include" {print $2}' "$CINT_TOOLCHAIN")
o=${CI_OUT:-${TMPDIR:-/tmp}/daphnis-build/ubin}
out=$(cd ../.. && mkdir -p "$o" && cd "$o" && pwd)
cc=${CI_CC:-musl-gcc}
sha256sum --strict --quiet -c SOURCES.sha256
work=$(mktemp -d)
trap 'rm -rf "${work:?}"' EXIT
# ced.ci and the modules it imports, each after its own imports
order=$(python3 -I -c '
import re, sys
deps, out = {}, []
def visit(m):
    if m in out:
        return
    if m not in deps:
        try:
            deps[m] = re.findall(r"^import (\w+);", open(m + ".ci").read(), re.M)
        except FileNotFoundError:
            return          # a service of cint (console, fs)
    for d in deps[m]:
        visit(d)
    out.append(m)
visit("ced")
print(" ".join(m + ".ci" for m in out))')
# shellcheck disable=SC2086
cint emit-c --toolchain "$CINT_TOOLCHAIN" --root . --out "$work/out" $order
c="$work/$(cut -d' ' -f1 "$work/out/MANIFEST.ref")"
cat > "$work/main.c" <<'EOF'
/* ced's main: cint build --app --frame-arena 67108864 (cli/cint_main.c write_driver at the toolchain's commit). */
#define _XOPEN_SOURCE 700              /* realpath, getcwd */
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#define main cint_program_main
int cint_program_main(int argc, char **argv);
#include "cint-program.c"
#undef main

/* Untitled's directory: the working directory when it is the home or under it, else the home (a Console in / gives
 * no rights on /); NULL when HOME names no directory, and then no /argK line is granted. */
static const char *untitled_dir(void)
{
    static char home[4096], cwd[4096];
    const char *h = getenv("HOME");
    size_t n;
    if (h == NULL || h[0] != '/' || realpath(h, home) == NULL) return NULL;
    if (getcwd(cwd, sizeof cwd) == NULL) return home;
    n = strlen(home);
    if (strncmp(cwd, home, n) == 0 && (cwd[n] == '\0' || cwd[n] == '/' || home[n - 1] == '/')) return ".";
    return home;
}

/* RUN-8 (ced-dev PR 11): with no argument ced is Untitled and /arg1 is untitled_dir(). cint derives /argK only from
 * argument K, so each line of ced's own manifest (cg_requires) goes as a --grant, a line on an /argK root bound to
 * that directory; no right beyond the manifest. Fills g with the --grant pairs; their count. */
static int no_file(char **g, int room)
{
    static char grant[] = "--grant";
    static char lines[2u * sizeof cg_requires + 8u * 4096u];   /* each line NUL-ended, "=DIR" after an /argK root */
    const char *d = untitled_dir();
    size_t dn = d == NULL ? 0u : strlen(d);
    size_t at = 0u;
    int n = 0;
    for (const char *p = cg_requires; *p != '\0' && n + 2 <= room; p += strcspn(p, "\n") + (p[strcspn(p, "\n")] != '\0')) {
        size_t len = strcspn(p, "\n");
        const char *c = (const char *)memchr(p, ':', len);
        int root = c != NULL && (size_t)(p + len - c) > 5u && memcmp(c + 1, "/arg", 4u) == 0;
        if (len == 0u || (root && d == NULL) || at + len + dn + 2u > sizeof lines) continue;
        g[n++] = grant;
        g[n++] = lines + at;
        memcpy(lines + at, p, len);
        at += len;
        if (root) {
            lines[at++] = '=';
            memcpy(lines + at, d, dn);
            at += dn;
        }
        lines[at++] = '\0';
    }
    return n;
}

int main(int argc, char **argv)
{
    static char flag[] = "--frame-arena", count[] = "67108864";
    static char tail[] = "--";
    char *g[32];
    const int ng = argc == 1 ? no_file(g, 32) : 0;
    char **v = argc < 1 ? NULL : (char **)malloc(((size_t)argc + 4u + (size_t)ng) * sizeof *v);
    int k = 1;
    if (v == NULL) return argc < 1 ? cint_program_main(argc, argv) : CINT_EXIT_ENVIRONMENT;
    v[0] = argv[0];
    v[k++] = flag;
    v[k++] = count;
    for (int i = 0; i < ng; i++) v[k++] = g[i];
    v[k++] = tail;
    for (int i = 1; i <= argc; i++) v[k++] = argv[i];   /* argv[argc] is NULL */
    return cint_program_main(argc + 3 + ng, v);
}
EOF
# HW-16: the module files link in byte order of their paths (as user/ci/build.sh does since B3), so two hosts link the same bytes
# shellcheck disable=SC2046
$cc -std=c17 -O2 -static -fno-asynchronous-unwind-tables -ffunction-sections -fdata-sections -Wl,--gc-sections -s -DCINT_RT_HELPERS_PORTABLE -I"$inc" -I"$c" \
    -o "$out/ced" "$work/main.c" $(find "$c" -name '*.c' ! -name cint-program.c | LC_ALL=C sort) "$inc/cint_rt.c"
sha256sum "$out/ced"
