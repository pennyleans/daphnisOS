#!/usr/bin/env bash
# user/ci/build.sh [NAME...]: builds the cint programs of ring 3 (stage R-1) into $CI_OUT: each
# NAME.ci here is emitted to C by the pinned `cint emit-c` (as the kernel is) and built with the
# toolchain's hosted runtime (rt/cint_rt.c, builtin overflow helpers on gcc/clang) and the host's musl-gcc, static, -O2,
# stripped, with user/ci/main.c in place of the emitted main (renamed cint_emitted_main) and the rows
# of user/ci/host.c; each function and datum in its own section and the unused ones dropped at the link
# (-Wl,--gc-sections), so a program keeps only the runtime it calls and the desk image stays under 32 MiB. Prints each SHA-256. The pinned bytes (tests/expected) are the gate's (ruling DU-2 A): a host
# whose musl or compiler differs builds a different file, which is a note, not a failure. CINT_TOOLCHAIN names the
# pinned toolchain file and must be set; build.sh ends naming it when it is not.
# W-1: `user/ci/build.sh tiler` builds the tiler (user/ci/tiler.ci and the kit, user/ci/kit/); CI_CC (default
# musl-gcc) and CI_OUT (default the Makefile's own O/ubin, $TMPDIR/daphnis-build/ubin; never the tree's user/bin,
# RG-1) build the same emitted C with another C17 compiler and libc, static, into another directory (check-tiler.sh
# builds it with the host's gcc and clang).
# A-4: a program that imports user/ci/tls.ci links BearSSL from CI_TLS, the OUT of user/tls/build.sh, which must be
# set for such a program, and its anchors (user/tls/anchors.h).
set -eu
cd "$(dirname "$0")/../.."
# rows_for NAME: the -D flags of user/ci/host.c that program NAME is built with, in rows: the CI_ROWS_ sets its
# imports need (main.c binds an extern of every imported module to a row, and a row left out stops the program
# at its start with status 2) and its frame arena. tools/check-rows.py reads them through --rows. imports is the
# program's whole import closure, every module it imports directly or through another, so a kit's own call (as
# kit/setfile.ci's fdctl.fd_stat) brings its rows to every program that imports the kit.
rows_for() {
    p=$1
    imports=""
    local todo="user/ci/$p.ci" f
    while [ -n "$todo" ]; do
        f=${todo%% *}
        todo=${todo#"$f"}
        todo=${todo# }
        case " $imports " in *" $f "*) continue ;; esac
        imports="$imports $f"
        [ -f "$f" ] || continue
        todo="$todo $(sed -n 's/^import \([a-z0-9_.]*\);.*/\1/p' "$f" | tr . / | sed 's/$/.ci/' | tr '\n' ' ')"
        todo=${todo# }
        todo=${todo% }
    done
    rows=""
    case " $imports " in *" user/ci/udp.ci "*|*" user/ci/dns.ci "*) rows=-DCI_ROWS_NET ;; esac   # N-2: the socket rows of host.c
    case " $imports " in *" user/ci/tcp.ci "*|*" user/ci/dns.ci "*) rows="$rows -DCI_ROWS_TCP" ;; esac   # N-3: the stream rows
    case " $imports " in *" user/ci/ptyctl.ci "*) rows="$rows -DCI_ROWS_PTY" ;; esac   # W-4: the pty rows
    case " $imports " in *" user/ci/grantcall.ci "*) rows="$rows -DCI_ROWS_GRANT" ;; esac   # P-3: grant's rows
    case " $imports " in *" user/ci/kerncall.ci "*) rows="$rows -DCI_ROWS_KERN" ;; esac   # R0-2: kern's row
    case " $imports " in *" user/ci/traycall.ci "*) rows="$rows -DCI_ROWS_TRAY" ;; esac   # SP-2: tray's row
    case " $imports " in *" user/ci/opencall.ci "*) rows="$rows -DCI_ROWS_OPEN" ;; esac   # FF-6c: finder's open
    case " $imports " in *" user/ci/dirctl.ci "*) rows="$rows -DCI_ROWS_DIR" ;; esac   # FF 3h: the Trash store's names
    case " $imports " in *" user/ci/shctl.ci "*|*" user/ci/dns.ci "*) rows="$rows -DCI_ROWS_SH" ;; esac   # CS-1: cish's rows
    case " $imports " in *" user/ci/corectl.ci "*) rows="$rows -DCI_ROWS_CORE" ;; esac   # CT-1: the core set's rows
    case " $imports " in *" user/ci/sigctl.ci "*) rows="$rows -DCI_ROWS_SIG" ;; esac   # K-10: cish's signal row
    case " $imports " in *" user/ci/viewctl.ci "*) rows="$rows -DCI_ROWS_VIEW" ;; esac   # BP-2: cless's terminal size
    case " $imports " in *" user/ci/tilepoint.ci "*) rows="$rows -DCI_ROWS_POINT" ;; esac   # BP-6: cview's pointer
    [ "$p" = cview ] && rows="$rows -DCI_FRAME_ARENA_BYTES=1073741824"   # RS-VIEW: 128 Mi elements (the arena counts one an 8 bytes, RT-OQ-34): the large decode buffers, 128 MiB, of a picture past 2,097,152 pixels up to 3840 x 2160; a window starts on the small, 32 MiB
    [ "$p" = bgread ] && rows="$rows -DCI_FRAME_ARENA_BYTES=1073741824"   # BG-1: cview's large decode buffers, 128 MiB
    [ "$p" = cvbuf ] && rows="$rows -DCI_FRAME_ARENA_BYTES=838860800"   # CV-1: 100 Mi elements for orig (64 MiB), add (32 MiB) and the table
    [ "$p" = cvim ] && rows="$rows -DCI_FRAME_ARENA_BYTES=1006632960"   # CV-4a: cvbuf's tables, the undo spans, the screen's grids
    case " $imports " in *" user/ci/runctl.ci "*) rows="$rows -DCI_ROWS_RUN" ;; esac   # CT-4: the core set's exec
    case " $imports " in *" user/ci/metactl.ci "*) rows="$rows -DCI_ROWS_META" ;; esac   # BU-2b: tier C-2's rows
    case " $imports " in *" user/ci/factsctl.ci "*) rows="$rows -DCI_ROWS_FACTS" ;; esac   # KF-1: stage KF's rows
    case " $imports " in *" user/ci/fdctl.ci "*) rows="$rows -DCI_ROWS_FD" ;; esac   # FS-5: fstat of a descriptor
    case " $imports " in *" user/ci/wall.ci "*) rows="$rows -DCI_ROWS_WALL" ;; esac   # NW-0: the wall clock
    case " $imports " in *" user/ci/tileplace.ci "*) rows="$rows -DCI_ROWS_PLACE" ;; esac   # H-2: the tiler's placement
    case " $imports " in *" user/ci/tilewin.ci "*) rows="$rows -DCI_ROWS_WIN" ;; esac   # H-3c3: a window that asks
    case " $imports " in *" user/ci/tilesurf.ci "*) rows="$rows -DCI_ROWS_SURF" ;; esac   # RS-SURF: fb_resize
    case " $imports " in *" user/ci/tls.ci "*) rows="$rows -DCI_ROWS_TLS" ;; esac   # A-4: the TLS rows (BearSSL below)
    case " $imports " in *" user/ci/hdeskctl.ci "*) rows="$rows -DCI_ROWS_HDESK" ;; esac   # H-3a: the hybrid desk's rows
    case " $imports " in *" user/ci/dspdev.ci "*) rows="$rows -DCI_ROWS_DSP" ;; esac   # AU-3: /dev/dsp
    case " $imports " in *" user/ci/authctl.ci "*) rows="$rows -DCI_ROWS_AUTH" ;; esac   # AC-1b: authd's getrandom
    case " $imports " in *" user/ci/cvimctl.ci "*) rows="$rows -DCI_ROWS_CVIM" ;; esac   # CV-4a: cvim's terminal and files
    case " $imports " in *" user/ci/sysinfoctl.ci "*) rows="$rows -DCI_ROWS_SYSINFO" ;; esac   # KF-2: Monitor's sysinfo
    case " $imports " in *" user/ci/revokectl.ci "*) rows="$rows -DCI_ROWS_REVOKE" ;; esac   # GV-2: the desk's revoke
    [ "$p" = authd ] && rows="$rows -DCI_FRAME_ARENA_BYTES=75497472"   # AC-1b: 72 MiB, Argon2id's 64 MiB of blocks (DS-6) a frame local
    [ "$p" = shot ] && rows="$rows -DCI_FRAME_ARENA_BYTES=629145600"   # RS-SHOT: 75 Mi elements, a 4K shot
    return 0                                # the last test above is false for every other program
}
if [ "${1:-}" = --deps ]; then   # --deps NAME: the files of NAME's import closure, one a line (the Makefile's rule)
    rows_for "$2"
    for f in $imports; do [ -f "$f" ] && echo "$f"; done
    exit 0
fi
if [ "${1:-}" = --rows ]; then   # --rows NAME...: each NAME and its flags, one line each; nothing is built
    shift
    for n in "$@"; do
        rows_for "$n"
        echo "$n $rows"
    done
    exit 0
fi
: "${CINT_TOOLCHAIN:?set CINT_TOOLCHAIN to the pinned compiler toolchain}"
inc=$(awk '$1=="include" {print $2}' "$CINT_TOOLCHAIN")
progs=${*:-"mci mcifb msha"}
work=$(mktemp -d)
trap 'rm -rf "${work:?}"' EXIT
out=${CI_OUT:-${TMPDIR:-/tmp}/daphnis-build/ubin}
cc=${CI_CC:-musl-gcc}
mkdir -p "$out"
for p in $progs; do
    rows_for "$p"
    mkdir -p "$work/$p"
    libs=""
    case " $imports " in *" user/ci/tls.ci "*)   # A-4: BearSSL for the TLS rows
        tls=${CI_TLS:?set CI_TLS to the BearSSL build, the OUT of user/tls/build.sh}
        [ -f "$tls/libbearssl.a" ] || { echo "build.sh: $tls/libbearssl.a not found (user/tls/build.sh TARBALL)" >&2; exit 1; }
        rows="$rows -I$tls/inc -Iuser/tls"; libs=$tls/libbearssl.a ;;
    esac
    # The program is emit-c's only root: emit-c resolves its imports itself. Listing them as roots failed with C9102
    # once a module imported one listed after it, and a closure past 64 modules cannot be listed at all. The import
    # list above only picks the rows of host.c.
    cint emit-c --toolchain "$CINT_TOOLCHAIN" --root . --out "$work/$p/out" "user/ci/$p.ci"
    c="$work/$p/$(cut -d' ' -f1 "$work/$p/out/MANIFEST.ref")"
    run=$(grep -o 'cg_[0-9A-Za-z_]*_run' "$c/cint-program.c" | head -1)
    $cc -std=c17 -O2 -static -fno-asynchronous-unwind-tables -ffunction-sections -fdata-sections -I"$inc" -Iuser/ci \
        -Dmain=cint_emitted_main -o "$work/$p/emitted.o" -c "$c/cint-program.c"
    # B3: the module files link in byte order of their paths, not in the directory order find meets them in, so two
    # Linux hosts with the same musl-gcc link the same bytes
    # shellcheck disable=SC2046
    $cc -std=c17 -O2 -static -fno-asynchronous-unwind-tables -ffunction-sections -fdata-sections -Wl,--gc-sections -s -I"$inc" -Iuser/ci $rows \
        -DCI_RUN="$run" -o "$out/$p" "$work/$p/emitted.o" $(find "$c" -name '*.c' ! -name cint-program.c | LC_ALL=C sort) \
        user/ci/main.c user/ci/host.c "$inc/cint_rt.c" $libs
    sha256sum "$out/$p"
done
