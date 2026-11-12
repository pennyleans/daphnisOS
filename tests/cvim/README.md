# CV-2a replay checks

Run from the repository root with the pinned cint and CINT_TOOLCHAIN:

    python3 tests/cvim/run.py
    bash check-cvim.sh

cases.py holds 501 start-file/key-script pairs in 15 groups. golden.json records file text, one-based byte cursor, Normal mode and unnamed register bytes/type captured from the exact Vim in VIM_VERSION. The default run builds replay.ci, compares every result to the frozen record, then compares it to a fresh Vim PTY session. Missing or different Vim prints NOTE, never an oracle PASS; check-cvim.sh's fixed count refuses an incomplete oracle leg.

The gate also compiles the modal core with Clang and checks all frozen records. This alternate toolchain retains the pinned GCC-built hosted runtime objects; the emitted program is compiled by Clang. The CV-1 large-buffer program is independently built with musl-gcc, GCC and Clang. Daphnis editor integration and its replay leg remain CV-9.

The replay driver owns its tables and calls key.init, key.load and key.step. No core function performs I/O. The fixture tables are smaller than the production capacities and do not represent a 64 MiB modal-editor performance measurement. CV-1's separate large-buffer gate supplies that buffer measurement.

## Adding cases

Add a named start text and script to cases.py, then deliberately capture expectations using the pinned Vim:

    python3 tests/cvim/run.py --freeze

Review the changed records. Do not update expectations to match cvim. Every existing motion and operator has multiple cases; composition groups include both count slots, UTF-8, empty buffers, unterminated input, repeated insertion and undo across sessions. test_core.ci checks unsupported keys and small-table capacity refusals that an unconstrained Vim session cannot model.

Unicode word classes and simple case toggles are integer constants generated from the same Vim, with no host character library at runtime:

    python3 tests/cvim/unicode.py

DIFFS.md lists the terminal's required one-cell Unicode difference. It is tested separately from equality cases; keys assigned to later units remain outside CV-2a.

## Motion review regressions

The original 501 cases and golden.json remain byte-identical. motion_cases.py adds 115 equality cases and one distinct width-policy case, captured from the exact installed Vim in VIM_VERSION into motion_golden.json. Independent capture_motion.py corroborates all new records with Ex feedkeys, explicit cursor initialization, saved bytes, byte cursor and unnamed register. It does not import run.py, vim_leg.py or keys.py. Its command hashes are retained with the evidence. The scripts end in Normal mode by construction; mode zero is an expectation, not an independently observed Vim mode.

    python3 tests/cvim/motion.py --out /external/build/motion-gcc
    python3 tests/cvim/motion.py --cc clang --frozen-only --out /external/build/motion-clang
    python3 tests/cvim/capture_motion.py /external/build/oracle

The new runner never rewrites expectations. The replay asserts Normal mode and empty operator, prefix and both count slots for every original and new script. The GCC leg compares frozen and fresh equality records, asserts cvim's width policy, then separately confirms the pinned Vim width result differs. The Clang leg checks frozen equality and cvim policy results. check-cvim.sh includes both legs; these focused checks do not qualify desktop rendering or large-buffer performance.

Set CINT_CACHE to pass an explicit compiler --cache directory; TMPDIR supplies external scratch space. Clang retains the pinned GCC-built hosted runtime.

## CV-2b: text objects, registers, repeat, macros, Visual mode, scrolling and marks

edit_cases.py holds the CV-2b scripts in 11 groups (docs/handoff/20261108-cv2b.md). Each record in edit_golden.json
holds the file, the byte cursor, the window's top line (`line('w0')`) and the registers `" 0-9 - a b q` with their
kinds (`v`, `V`, `b` and the block's width). The Vim leg (`vim_leg.run_full`) runs on a 24-row pty, so the window is
23 rows; oracle.vim sets `nowrap` and `scrolloff=4` (section 6) for H M L and the scroll keys. The replay core takes
the same height (`key.window`, 23 by default).

    python3 tests/cvim/edit.py --out /external/build/edit-gcc
    python3 tests/cvim/edit.py --cc clang --frozen-only --out /external/build/edit-clang
    python3 tests/cvim/edit.py --freeze                # the pinned Vim only: recapture and mark verified
    python3 tests/cvim/edit.py --capture-unverified    # any Vim: recapture and mark unverified

edit_golden.json names the Vim that captured it. Records from a Vim other than VIM_VERSION are unverified: the run
prints NOTE, and they are no pass of record until `--freeze` recaptures them with the pinned Vim. The records on
l/cvim-cv2b were captured on macOS (Vim 9.1, patches 1-1752); four of them are known to differ from cvim there,
where that Vim is newer than the pin: `case-gUG`, `case-unicode_gU`, `case-unicode_g~` (its case tables map
U+00DF to U+1E9E; unicode.ci holds the pinned Vim's) and `scroll-cf_end` (Ctrl+F at the end, rewritten after
patch 16). check-cvim.sh runs both legs; its fixed count includes the 11 groups, the oracle line and the Clang line.

## CV-3: the screen and its frames

user/ci/cvim/view.ci composes the screen as cells (the S1 sheet's layout and roles): the buffer line, the text rows
(a two-cell diagnostic column, the number gutter of three digits or the line count's, the line, no wrap, the text
area following the cursor's column), the status line (mode, file, `[+]`, file type, `line:col`, percent) and the
message line (`not in cvim: g?`, a full table, `recording @a`). user/ci/cvim/term.ci writes a frame: only the cells
that changed since the last frame, one CUP a run, SGR only where the role changes, the cursor's form per mode as
DECSCUSR when it changes.

    python3 tests/cvim/screen.py --out /external/build/screen
    python3 tests/cvim/screen.py --cc clang --out /external/build/screen-clang
    python3 tests/cvim/screen.py --freeze --out DIR      print every screen, record its digests

screen_cases.py holds 66 scripts in 7 groups at sizes from 5 x 30 to 118 x 133. For each, the frames played in order
through screen.py's terminal model must leave exactly the last grid (characters, SGR and cursor), no frame may be
larger than a full one, and the SHA-256 of the frames and of the grid must equal screen_golden.json. There is no Vim
oracle for frames: --freeze records cvim's own output, read before it is committed. screen_golden.json keeps each
case's last screen as text for that reading.
