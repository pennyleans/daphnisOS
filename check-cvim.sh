#!/usr/bin/env bash
# check-cvim.sh: the gate of cvim (docs/specs/2026-11-07-cv-cvim.md sections 4 and 14), on its own budget beside
# check.sh. One PASS or FAIL line per check; exit status 1 if any FAIL. Linux only so far.
#   CV-1: user/ci/cvim/test_buf.ci's tests (the piece table against a flat model, with small blocks and chunks);
#   CV-4b: user/ci/cvim/test_pat.ci and test_ex.ci (the patterns of :s and :g, the core's command line);
#   cvbuf (user/ci/cvbuf.ci) built with musl-gcc, gcc and clang, each given tools/check-cvim.py's 64 MiB file: it
#   loads it, jumps to its last line, takes 1,000 typed bytes at its middle line, saves it, and the saved file is
#   want.txt byte for byte; every key under 16 ms (gate 3); a file one byte past 64 MiB refused (CV-R3 A).
#   CV-2b: tests/cvim/edit.py's groups (text objects, registers, repeat, macros, Visual and block mode, g~ gu gU =,
#   H M L and the scroll keys, marks) against edit_golden.json, then the pinned Vim; the Clang leg frozen only.
#   CV-3: user/ci/cvim/term.ci's tests; tests/cvim/screen.py's groups: every frame played through a terminal model
#   leaves the last grid, and the frame digests equal screen_golden.json; the Clang leg the same.
#   CV-4a: cvim (user/ci/cvim.ci) built with musl-gcc as user/ci/build.sh builds user/bin/cvim, then
#   tests/cvim/cvim_pty.py on a pty: :w :q :wq :x ZZ ZQ :e! :N :set, E37 E13 E492 E32, the file's mode kept, Vim's
#   final line feed, the terminal given back after :q and after SIGTERM, a 64 MiB file opened, a byte more refused;
#   then the same keys in the pinned Vim ($VIM, default vim) as the oracle of every expected byte and message.
# Outputs go under $DAPHNIS_BUILD (default ~/daphnis-work/build-cvim), cleared as check.sh clears its own.
set -u
cd "$(dirname "$0")"
B=${DAPHNIS_BUILD:-$HOME/daphnis-work/build-cvim}
CINT_TOOLCHAIN=${CINT_TOOLCHAIN:-$HOME/cint-work/build-pin/out/cint.toolchain}
export CINT_TOOLCHAIN
BUDGET=525   # the legs take about this on Arch (integrator, 20261110)
gate_want=62   # the PASS lines before the last one (CV-4b: +2, test_pat and test_ex; the ex edit group adds 1 once frozen; CV-6: +2, test_hl and the hl gate; CV-7: +1, test_comp; CV-8: +1, test_tool)
export PYTHONDONTWRITEBYTECODE=1
start=$SECONDS
fails=0 passes=0
line() { # ok|bad label [detail]
    if [ "$1" = ok ]; then echo "PASS  $2"; passes=$((passes + 1)); else echo "FAIL  $2${3:+: $3}"; fails=$((fails + 1)); fi
}
fail_exit() { echo "check-cvim.sh: $*"; echo "RESULT: FAIL"; exit 1; }

for t in cint gcc clang musl-gcc python3 cmp git; do
    command -v "$t" >/dev/null || fail_exit "$t not found"
done
[ -f "$CINT_TOOLCHAIN" ] || fail_exit "cint toolchain file $CINT_TOOLCHAIN not found (set CINT_TOOLCHAIN)"
if [ -e "$B" ] && [ -n "$(ls -A "$B" 2>/dev/null)" ] && [ ! -f "$B/.daphnis-build" ]; then
    fail_exit "$B exists, is not empty and is not a Daphnis build directory (no .daphnis-build); set DAPHNIS_BUILD"
fi
rm -rf "$B"; mkdir -p "$B"; : > "$B/.daphnis-build"
git_state_before=$(git status --porcelain 2>/dev/null)

# 1. the piece table against a flat model
CINT_BUILD=$B/cint-cache cint test --root . user/ci/cvim/test_buf.ci > "$B/test.log" 2>&1 \
    && line ok "buf: user/ci/cvim/test_buf.ci ($(tail -1 "$B/test.log"))" \
    || line bad "buf: user/ci/cvim/test_buf.ci" "$(tail -1 "$B/test.log"); see $B/test.log"
# CV-4b: the patterns of :s and :g (pat.ci) and the core's command line (ex.ci); CV-6: the highlighting (hl.ci);
# CV-8: the build's diagnostics list (tool.ci)
for t in pat ex hl comp tool; do
    CINT_BUILD=$B/cint-cache cint test --root . user/ci/cvim/test_$t.ci > "$B/test-$t.log" 2>&1 \
        && line ok "$t: user/ci/cvim/test_$t.ci ($(tail -1 "$B/test-$t.log"))" \
        || line bad "$t: user/ci/cvim/test_$t.ci" "$(tail -1 "$B/test-$t.log"); see $B/test-$t.log"
done

# 2. 64 MiB on each compiler
python3 tools/check-cvim.py make "$B" > "$B/make.log" 2>&1 || fail_exit "tools/check-cvim.py make: see $B/make.log"
for cc in musl-gcc gcc clang; do
    o=$B/bin-$cc
    if CI_CC=$cc CI_OUT=$o bash user/ci/build.sh cvbuf > "$B/build-$cc.log" 2>&1 \
        && "$o/cvbuf" "$B/big.txt" "$B/got-$cc.txt" > "$B/run-$cc.log" 2>&1 \
        && cmp -s "$B/got-$cc.txt" "$B/want.txt"; then
        python3 tools/check-cvim.py read "$B/run-$cc.log" > "$B/read-$cc.log" 2>&1 \
            && line ok "64 MiB $cc: load $(($(grep '^load_ns' "$B/run-$cc.log" | cut -d' ' -f2) / 1000000)) ms, last line $(($(grep '^jump_ns' "$B/run-$cc.log" | cut -d' ' -f2) / 1000)) us, 1,000 keys, worst $(($(grep '^key_worst_ns' "$B/run-$cc.log" | cut -d' ' -f2) / 1000)) us, saved = want.txt" \
            || line bad "64 MiB $cc: a key took 16 ms or more" "see $B/run-$cc.log"
    else
        line bad "64 MiB $cc" "see $B/build-$cc.log, $B/run-$cc.log"
    fi
    "$o/cvbuf" "$B/over.txt" "$B/over-$cc.txt" > "$B/over-$cc.log" 2>&1
    [ $? = 1 ] && grep -q 'over 64 MiB' "$B/over-$cc.log" \
        && line ok "refuse $cc: a file one byte past 64 MiB is refused by name" || line bad "refuse $cc" "see $B/over-$cc.log"
done

# 3. CV-2a: core refusals, frozen replay groups and the pinned Vim oracle.
if CINT_BUILD=$B/cint-cache cint test --toolchain "$CINT_TOOLCHAIN" --root . tests/cvim/test_core.ci > "$B/core-unit.log" 2>&1; then
    line ok "cvim core: $(tail -1 "$B/core-unit.log")"
else
    line bad "cvim core" "see $B/core-unit.log"
fi
if CINT_BUILD=$B/cint-cache cint test --toolchain "$CINT_TOOLCHAIN" --root . tests/cvim/test_capacity.ci > "$B/capacity-unit.log" 2>&1; then
    line ok "cvim capacity: $(tail -1 "$B/capacity-unit.log")"
else
    line bad "cvim capacity" "see $B/capacity-unit.log"
fi
if cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . tests/cvim/test_reclaim.ci > "$B/reclaim-unit.log" 2>&1; then
    line ok "cvim reclamation: $(tail -1 "$B/reclaim-unit.log")"
else
    line bad "cvim reclamation" "see $B/reclaim-unit.log"
fi
if cint build --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . --out "$B/reclaim-native" \
        --frame-arena 134217728 tests/cvim/reclaim_probe.ci > "$B/reclaim-build.log" 2>&1 \
        && "$B/reclaim-native/reclaim_probe" > "$B/reclaim-native.log" 2>&1; then
    line ok "cvim history: production redo, oldest-step and operation-limit reclamation"
else
    line bad "cvim history" "see $B/reclaim-build.log and $B/reclaim-native.log"
fi
python3 tests/cvim/run.py --out "$B/replay" > "$B/core.log" 2>&1
core_status=$?
while IFS= read -r row; do
    case "$row" in
        "PASS  "*) line ok "$(printf '%s' "$row" | cut -c7-)" ;;
        "FAIL  "*) line bad "$(printf '%s' "$row" | cut -c7-)" "see $B/core.log" ;;
        "NOTE  "*) echo "$row" ;;
    esac
done < "$B/core.log"
[ "$core_status" -eq 0 ] || fail_exit "cvim replay failed; see $B/core.log"

# The emitted modal core also agrees when Clang compiles it. This leg shares the pinned hosted runtime.
if python3 tests/cvim/run.py --cc clang --frozen-only --out "$B/replay-clang" > "$B/core-clang.log" 2>&1; then
    line ok "cvim clang: $(tail -1 "$B/core-clang.log")"
else
    line bad "cvim clang" "see $B/core-clang.log"
fi

for cc in gcc clang; do
    motion_args=()
    if [ "$cc" = clang ]; then motion_args=(--cc clang --frozen-only); fi
    if CINT_CACHE=$B/cint-cache python3 tests/cvim/motion.py "${motion_args[@]}" --out "$B/motion-$cc" > "$B/motion-$cc.log" 2>&1; then
        line ok "cvim motion $cc: 115 equality cases and one distinct unicode policy case"
    else
        line bad "cvim motion $cc" "see $B/motion-$cc.log"
    fi
done

# CV-2b: one PASS line per edit group and one for the pinned Vim oracle (unverified records print NOTE).
if CINT_CACHE=$B/cint-cache python3 tests/cvim/edit.py --out "$B/edit" > "$B/edit.log" 2>&1; then edit_status=0; else edit_status=1; fi
while IFS= read -r row; do
    case "$row" in
        "PASS  "*) line ok "$(printf '%s' "$row" | cut -c7-)" ;;
        "FAIL  "*) line bad "$(printf '%s' "$row" | cut -c7-)" "see $B/edit.log" ;;
        "NOTE  "*) echo "$row" ;;
    esac
done < "$B/edit.log"
[ "$edit_status" -eq 0 ] || line bad "cvim edit" "see $B/edit.log"
if CINT_CACHE=$B/cint-cache python3 tests/cvim/edit.py --cc clang --frozen-only --out "$B/edit-clang" > "$B/edit-clang.log" 2>&1; then
    line ok "cvim edit clang: $(tail -1 "$B/edit-clang.log")"
else
    line bad "cvim edit clang" "see $B/edit-clang.log"
fi

# CV-6: hl.ci's tokens equal the vendored scan.ci's on every corpus file scan.ci accepts (spec section 7)
if CINT_CACHE=$B/cint-cache python3 tests/cvim/hl_gate.py --corpus "${CINT_CORPUS:-$HOME/cint-work/cint-pub-0218/conformance}" \
    --out "$B/hl" > "$B/hl.log" 2>&1; then
    line ok "$(tail -1 "$B/hl.log" | cut -c7-)"
else
    line bad "cvim hl gate" "see $B/hl.log"
fi

# CV-3: the screen, its frames and their digests.
if cint test --toolchain "$CINT_TOOLCHAIN" --cache "$B/cint-cache" --root . user/ci/cvim/term.ci > "$B/term-unit.log" 2>&1; then
    line ok "cvim term: $(tail -1 "$B/term-unit.log")"
else
    line bad "cvim term" "see $B/term-unit.log"
fi
if CINT_CACHE=$B/cint-cache python3 tests/cvim/screen.py --out "$B/screen" > "$B/screen.log" 2>&1; then screen_status=0; else screen_status=1; fi
while IFS= read -r row; do
    case "$row" in
        "PASS  "*) line ok "$(printf '%s' "$row" | cut -c7-)" ;;
        "FAIL  "*) line bad "$(printf '%s' "$row" | cut -c7-)" "see $B/screen.log" ;;
    esac
done < "$B/screen.log"
[ "$screen_status" -eq 0 ] || line bad "cvim screen" "see $B/screen.log"
if CINT_CACHE=$B/cint-cache python3 tests/cvim/screen.py --cc clang --out "$B/screen-clang" > "$B/screen-clang.log" 2>&1; then
    line ok "cvim screen clang: $(tail -1 "$B/screen-clang.log")"
else
    line bad "cvim screen clang" "see $B/screen-clang.log"
fi
# 4. CV-4a: the program on a pty, then the same keys in the pinned Vim
if CI_OUT=$B/bin-cvim bash user/ci/build.sh cvim > "$B/build-cvim.log" 2>&1 \
    && CINT_DIR=${CINT_DIR:-$(dirname "$(command -v cint 2>/dev/null || echo /nonexistent/cint)")} python3 tests/cvim/cvim_pty.py "$B/bin-cvim/cvim" "$B/pty" --big > "$B/pty.log" 2>&1; then
    line ok "cvim program: $(grep -c '^PASS' "$B/pty.log") pty cases pass (edit, :w, :q, E37, E13, the mode, the terminal back, 64 MiB)"
else
    line bad "cvim program" "see $B/build-cvim.log, $B/pty.log"
fi
if python3 tests/cvim/cvim_pty.py "$B/bin-cvim/cvim" "$B/pty-vim" --vim "${VIM:-vim}" > "$B/pty-vim.log" 2>&1; then
    line ok "cvim program against $("${VIM:-vim}" --version | head -1 | cut -c1-24): every expected byte and message is Vim's"
else
    line bad "cvim program against the pinned Vim" "see $B/pty-vim.log"
fi

# 5. housekeeping
[ "$(git status --porcelain 2>/dev/null)" = "$git_state_before" ] \
    && line ok "repository: this run changed no file in the checkout" || line bad "repository" "the run changed the checkout"
elapsed=$((SECONDS - start))
echo "elapsed: $elapsed s (budget $BUDGET s)"
[ "$elapsed" -le "$BUDGET" ] && line ok "time: whole check in $elapsed s, within $BUDGET s" || line bad "time" "$elapsed s"
[ "$passes" = "$gate_want" ] \
    && line ok "gate: $passes PASS lines above, the fixed count ($gate_want)" \
    || line bad "gate: fixed count" "$passes PASS lines above, $gate_want expected"
if [ "$fails" -eq 0 ]; then echo "RESULT: PASS"; else echo "RESULT: FAIL ($fails failing lines)"; exit 1; fi
