# Results: K5 (tasks that can be saved, the journal, the state tree, kill and restore, replay across builds)

Branch `opencode/k5`, from `main` (the history of 2026-10-25, rewritten). Code under test: the branch head
(a clean clone of it, built into a fresh directory); the commits after it change only docs (this file and a
wording or two). What the stage built is `docs/snapshot.md`; the older stages are `docs/RESULTS.md` and
`docs/RESULTS-K45.md`.

## The gate

`./check.sh` from the clean clone: **308 PASS, 0 FAIL, 232 s** (budget 360 s: the stage's exit gate says
6 minutes, the line said 5 and now says 6; no other check was weakened or deleted), `RESULT: PASS`. The whole
old gate (240 lines of K0 to K4.5 at the start of this stage) still passes, with the same goldens. Machine:
CachyOS, gcc 16.2.1, clang 23.1.3, GNU ld 2.47, QEMU 11.1.2 (TCG). cint at the pin of `toolchain.pin` (slice head
a pre-release slice); `cint --version` does not exist, so the identity is: compiler source identity
`18620842d9aa...`, executable sha256 `42d15d580a5e2272...`, `cint_rt.h` sha256 `1f1be52c0c96c69c...` (the pin was not moved).

Commands: `./check.sh` (about four minutes: run it as `nohup ./check.sh > LOG &` and read the log; the shell of the
harness stops a command after two minutes). One K5 run by hand:

    make -s O=$DAPHNIS_BUILD COMPILERS=gcc FLAVORS=k5
    python3 tools/k5blob.py desc /tmp/x.blob 1 250 0            # record, quantum 250, network 0
    QEMU_EXTRA="-device loader,file=/tmp/x.blob,addr=0x6000000,force-raw=on" STDIN_FILE=tests/k5/script.txt \
        tools/run-qemu.sh $DAPHNIS_BUILD/gcc-k5/kernel32.elf /tmp/out.txt
    python3 tools/check-k5.py /tmp/out.txt tests/k5/script.txt     # 17 checks, recomputed in Python

## The exit gate, line by line

| Exit gate of the stage | Lines of `check.sh` that test it | Result |
| --- | --- | --- |
| Every existing line still passes | the 240 lines of K0 to K4.5, unchanged (the `shep` skeleton too) | PASS |
| New flavors boot on gcc and clang with byte-identical transcripts | `boot gcc-k5`, `boot clang-k5`, `serial k5: gcc and clang transcripts byte-identical`, `k5 record q=...: gcc and clang transcripts byte-identical` (5 quanta), `k5 net N: ...` (8 networks, 2 quanta), and the images at `-O0` (replay lines) | PASS |
| The single-owner walk passes at every commit; the foreign-page write faults identically on every schedule | `check-k5` (walks = commits, networks 0 and 4 and 8), `k5 net 1` and `k5 net 4` (same record under q=0 and q=1, gcc and clang, -O2 and -O0), networks 2, 3, 5 and 6 (the walk refuses a frame in two spaces, a writable and executable entry, a stray entry in an upper table, a page the kernel does not know) | PASS |
| 20 of 20 kill-and-restore roots equal the uninterrupted root | `k5 kill and restore (gcc, q=250)` and `(clang, q=1)`: 20 of 20 each; `(network 1, 4, 8)`: 8 of 8 each; `k5 restore from every snapshot` (q=1 and q=250: the machine restored from each snapshot it wrote) | PASS |
| Cross-compiler replay passes in both directions | `k5 replay of the q=... recording` (5 lines: gcc to clang, clang to gcc, gcc and clang at -O0, other quanta) and `k5 replay of a recording made by gcc/clang at -O0` | PASS |
| The divergence finder names the planted mutation | `k5 diverge` (`tools/check-diverge.py`) | PASS |
| `net 1` (the racy control) still varies, and under the journal it replays exactly | K4.5's `shep` net 1 is unchanged and its check passes; K5 network 0 is its select version: `k5 control` (3 different final roots under 5 quanta) and the replay lines | PASS |
| The whole check stays under 6 minutes | `time` line | PASS (232 s) |

The K5 lines of the clean-clone run:

```
PASS  boot gcc-k5: QEMU exit status 33 on both runs
PASS  boot gcc-k5: QEMU wrote nothing to stderr
PASS  boot clang-k5: QEMU exit status 33 on both runs
PASS  boot clang-k5: QEMU wrote nothing to stderr
PASS  serial k5: gcc and clang transcripts byte-identical (cmp)
PASS  serial k5: gcc run 1 and run 2 byte-identical (cmp)
PASS  serial k5: clang run 1 and run 2 byte-identical (cmp)
PASS  k5 record q=0: gcc and clang transcripts byte-identical, both exit 33
PASS  k5 record q=0: Merkle roots, journal chains, the input chunking and the counts recomputed in Python
PASS  k5 record q=1: gcc and clang transcripts byte-identical, both exit 33
PASS  k5 record q=1: Merkle roots, journal chains, the input chunking and the counts recomputed in Python
PASS  k5 record q=100: gcc and clang transcripts byte-identical, both exit 33
PASS  k5 record q=100: Merkle roots, journal chains, the input chunking and the counts recomputed in Python
PASS  k5 record q=250: gcc and clang transcripts byte-identical, both exit 33
PASS  k5 record q=250: Merkle roots, journal chains, the input chunking and the counts recomputed in Python
PASS  k5 record q=2000: gcc and clang transcripts byte-identical, both exit 33
PASS  k5 record q=2000: Merkle roots, journal chains, the input chunking and the counts recomputed in Python
PASS  k5 control: the racy network gives 3 different final roots under 5 quanta (the schedule shows)
PASS  k5 replay of the q=0 recording: on clang (q=1), on gcc from the clang recording (q=1), on gcc -O0 and clang -O0 (q=250): same final root, same journal, same final leaves
PASS  k5 replay of the q=1 recording: on clang (q=100), on gcc from the clang recording (q=100), on gcc -O0 and clang -O0 (q=2000): same final root, same journal, same final leaves
PASS  k5 replay of the q=100 recording: on clang (q=250), on gcc from the clang recording (q=250), on gcc -O0 and clang -O0 (q=0): same final root, same journal, same final leaves
PASS  k5 replay of the q=250 recording: on clang (q=2000), on gcc from the clang recording (q=2000), on gcc -O0 and clang -O0 (q=1): same final root, same journal, same final leaves
PASS  k5 replay of the q=2000 recording: on clang (q=0), on gcc from the clang recording (q=0), on gcc -O0 and clang -O0 (q=100): same final root, same journal, same final leaves
PASS  k5 net 1: gcc and clang transcripts byte-identical under q=0 and q=1, all exit 33
PASS  k5 net 1: decoded and recomputed in Python (9 checks under each of two quanta)
PASS  k5 net 2: gcc and clang transcripts byte-identical under q=0 and q=1, all exit 33
PASS  k5 net 2: decoded and recomputed in Python (1 checks under each of two quanta)
PASS  k5 net 3: gcc and clang transcripts byte-identical under q=0 and q=1, all exit 33
PASS  k5 net 3: decoded and recomputed in Python (1 checks under each of two quanta)
PASS  k5 net 4: gcc and clang transcripts byte-identical under q=0 and q=1, all exit 33
PASS  k5 net 4: decoded and recomputed in Python (8 checks under each of two quanta)
PASS  k5 net 5: gcc and clang transcripts byte-identical under q=0 and q=1, all exit 33
PASS  k5 net 5: decoded and recomputed in Python (1 checks under each of two quanta)
PASS  k5 net 6: gcc and clang transcripts byte-identical under q=0 and q=1, all exit 33
PASS  k5 net 6: decoded and recomputed in Python (1 checks under each of two quanta)
PASS  k5 net 7: gcc and clang transcripts byte-identical under q=0 and q=1, all exit 33
PASS  k5 net 7: decoded and recomputed in Python (1 checks under each of two quanta)
PASS  k5 net 8: gcc and clang transcripts byte-identical under q=0 and q=1, all exit 33
PASS  k5 net 8: decoded and recomputed in Python (8 checks under each of two quanta)
PASS  k5 net 1: the fault record of the refused page access is the same bytes under q=0 and q=1, on gcc and clang, at -O2 and -O0
PASS  k5 net 4: the fault record of the refused page access is the same bytes under q=0 and q=1, on gcc and clang, at -O2 and -O0
PASS  k5 kill and restore (gcc, q=250): 20 of 20 seeded kill points restore to the uninterrupted final root, commit roots, journal and snapshots
PASS  k5 kill and restore (clang, q=1): 20 of 20 seeded kill points restore to the uninterrupted final root, commit roots, journal and snapshots
PASS  k5 kill and restore (network 1): 8 of 8 kill points, the last from the final snapshot, restore to the uninterrupted run
PASS  k5 kill and restore (network 4): 8 of 8 kill points, the last from the final snapshot, restore to the uninterrupted run
PASS  k5 kill and restore (network 8): 8 of 8 kill points, the last from the final snapshot, restore to the uninterrupted run
PASS  k5 audit q=250: every cached leaf equals the leaf made again from the state at every commit, and the audit adds no byte to the transcript
PASS  k5 audit q=1: every cached leaf equals the leaf made again from the state at every commit, and the audit adds no byte to the transcript
PASS  k5 restore from every snapshot (gcc, q=1): 18 snapshots, each restored and finished to the uninterrupted run
PASS  k5 restore from every snapshot (gcc, q=250): 12 snapshots, each restored and finished to the uninterrupted run
PASS  k5 restore: a snapshot with one flipped digit is refused (its digest is wrong), nothing runs
PASS  k5 restore: a snapshot whose journal is not the one its tables say (digest made again) is refused, nothing runs
PASS  k5 restore: a snapshot whose program revision is another build's is refused, nothing runs
PASS  k5 replay of a recording made by gcc at -O0, on clang at -O2 under q=1: same final root, same journal
PASS  k5 replay of a recording made by clang at -O0, on gcc at -O2 under q=1: same final root, same journal
PASS  k5 replay: a journal whose fuel stamp is one off is refused at the entry (diverged: task 2 entry 5), the run halts, no commit or snapshot follows
PASS  k5 replay: an entry whose chain is one bit off is refused (diverged: journal chain), the run halts
PASS  k5 diverge: the divergence finder names the planted mutation (commit, task, leaves) and agrees on a run with itself
```

## A run (k5 flavor, network 0, gcc `-O2`, quantum 250; digests cut to 12 digits)

```
run 0
Daphnis K5: the kernel keeps its books
boot tables: no entry is both writable and executable
wx: a store into the code traps, error code 3
wx: a jump into data traps, error code 17
wx: a jump into read-only data traps, error code 17
run: mode 1 net 0 q 250
J 0100000000050601616c7068610300000000000000 c4634e3a5bf3...
J 0101000000050601627261766f1300000000000000 6b69727b7a9f...
C 1 0 1ac921b7b814... e8bc66128d04... 688fc55bed9dc9 ...
C 2 1 47f656352a8f... e8bc66128d04... 96ab04d9409313 ...
... 56 commit lines, 12 snapshots (1441, 1609, 1839, ... bytes each, then the last at the end)
final root 7d18dbc18fa196964d5f22c2d1fce396aacb34d3029320b7335756f170aa39ff
commits 56
walks 56
rehashed 59
runs: 0 faulted, then one entry returned
```

Final roots of the same program under five quanta (the racy network: they differ, and each replays exactly):

| quantum | final root |
| --- | --- |
| 0 | `011e8a73c53b5ad11a5d59360bac622022de024a2ad74614e0f0a8a9c8e8fa2b` |
| 1 | `8568a2ef8b63fe29abde8b2fe08dd2bf604a075f1b408fa64f7a28207da54ef5` |
| 100 | `7d18dbc18fa196964d5f22c2d1fce396aacb34d3029320b7335756f170aa39ff` |
| 250 | `7d18dbc18fa196964d5f22c2d1fce396aacb34d3029320b7335756f170aa39ff` |
| 2000 | `011e8a73c53b5ad11a5d59360bac622022de024a2ad74614e0f0a8a9c8e8fa2b` |

## Kill and restore

The kill point list is a function of the seed and of the reference transcript, so it is the same on every
machine; the machine is really killed (SIGKILL) and the transcript is cut at the chosen byte (`docs/snapshot.md`
section 9).

```
kill  0: cut at byte  33482 of 71713 (anywhere, mid snapshot): restored from commit 25 with 3 journal entries to replay: ok
kill  1: cut at byte  61564 of 71713 (journal, mid journal line): restored from commit 50 with 1 journal entries to replay: ok
kill  2: cut at byte  60694 of 71713 (commit, mid commit line): restored from commit 50 with 0 journal entries to replay: ok
kill  3: cut at byte   4680 of 71713 (snapshot, mid snapshot): restored from commit none (restarted from the journal) with 8 journal entries to replay: ok
kill  4: cut at byte  32644 of 71713 (anywhere, mid snapshot): restored from commit 25 with 3 journal entries to replay: ok
kill  5: cut at byte  48229 of 71713 (journal, mid journal line): restored from commit 40 with 0 journal entries to replay: ok
kill  6: cut at byte  11658 of 71713 (commit, mid commit line): restored from commit 10 with 2 journal entries to replay: ok
kill  7: cut at byte  33564 of 71713 (snapshot, mid snapshot): restored from commit 25 with 3 journal entries to replay: ok
kill  8: cut at byte  32319 of 71713 (anywhere, mid snapshot): restored from commit 25 with 3 journal entries to replay: ok
kill  9: cut at byte  13620 of 71713 (journal, mid journal line): restored from commit 10 with 8 journal entries to replay: ok
kill 10: cut at byte   6588 of 71713 (commit, mid commit line): restored from commit 5 with 3 journal entries to replay: ok
kill 11: cut at byte  20014 of 71713 (snapshot, mid snapshot): restored from commit 15 with 5 journal entries to replay: ok
kill 12: cut at byte  28408 of 71713 (anywhere, mid snapshot): restored from commit 20 with 2 journal entries to replay: ok
kill 13: cut at byte  18149 of 71713 (journal, mid journal line): restored from commit 15 with 0 journal entries to replay: ok
kill 14: cut at byte  12432 of 71713 (commit, mid commit line): restored from commit 10 with 5 journal entries to replay: ok
kill 15: cut at byte  17214 of 71713 (snapshot, mid snapshot): restored from commit 10 with 10 journal entries to replay: ok
kill 16: cut at byte   9429 of 71713 (anywhere, mid snapshot): restored from commit 5 with 8 journal entries to replay: ok
kill 17: cut at byte   5743 of 71713 (journal, mid journal line): restored from commit 5 with 0 journal entries to replay: ok
kill 18: cut at byte  43549 of 71713 (commit, mid commit line): restored from commit 35 with 3 journal entries to replay: ok
kill 19: cut at byte  71565 of 71713 (after the last snapshot, mid line): restored from commit 56 with 0 journal entries to replay: ok
PASS: 20 of 20 kill points restored to the uninterrupted run (final root 7d18dbc18fa196964d5f22c2d1fce396aacb34d3029320b7335756f170aa39ff, every commit root, the journal and the snapshots)
classes of the cut: mid commit line, mid journal line, mid line, mid snapshot
```

and on clang, under another schedule (q=1):

```
kill  0: cut at byte  42446 of 97643 (anywhere, mid snapshot): restored from commit 40 with 2 journal entries to replay: ok
kill  1: cut at byte  15718 of 97643 (journal, mid journal line): restored from commit 15 with 1 journal entries to replay: ok
kill  2: cut at byte  86511 of 97643 (commit, mid commit line): restored from commit 80 with 3 journal entries to replay: ok
kill  3: cut at byte  13592 of 97643 (snapshot, mid snapshot): restored from commit 10 with 3 journal entries to replay: ok
kill  4: cut at byte  12338 of 97643 (anywhere, mid snapshot): restored from commit 10 with 3 journal entries to replay: ok
kill  5: cut at byte  45308 of 97643 (journal, mid journal line): restored from commit 45 with 1 journal entries to replay: ok
kill  6: cut at byte   5861 of 97643 (commit, mid commit line): restored from commit 5 with 2 journal entries to replay: ok
kill  7: cut at byte  31005 of 97643 (snapshot, mid snapshot): restored from commit 30 with 2 journal entries to replay: ok
kill  8: cut at byte  11266 of 97643 (anywhere, mid commit line): restored from commit 10 with 3 journal entries to replay: ok
kill  9: cut at byte  55313 of 97643 (journal, mid journal line): restored from commit 55 with 0 journal entries to replay: ok
kill 10: cut at byte   6156 of 97643 (commit, mid commit line): restored from commit 5 with 3 journal entries to replay: ok
kill 11: cut at byte  13655 of 97643 (snapshot, mid snapshot): restored from commit 10 with 3 journal entries to replay: ok
kill 12: cut at byte  55643 of 97643 (anywhere, mid commit line): restored from commit 55 with 1 journal entries to replay: ok
kill 13: cut at byte   5597 of 97643 (journal, mid journal line): restored from commit 5 with 1 journal entries to replay: ok
kill 14: cut at byte  73652 of 97643 (commit, mid commit line): restored from commit 70 with 2 journal entries to replay: ok
kill 15: cut at byte  38574 of 97643 (snapshot, mid snapshot): restored from commit 35 with 3 journal entries to replay: ok
kill 16: cut at byte  82239 of 97643 (anywhere, mid snapshot): restored from commit 75 with 3 journal entries to replay: ok
kill 17: cut at byte  72724 of 97643 (journal, mid journal line): restored from commit 70 with 0 journal entries to replay: ok
kill 18: cut at byte  74320 of 97643 (commit, mid commit line): restored from commit 70 with 3 journal entries to replay: ok
kill 19: cut at byte  97495 of 97643 (after the last snapshot, mid line): restored from commit 89 with 0 journal entries to replay: ok
PASS: 20 of 20 kill points restored to the uninterrupted run (final root 8568a2ef8b63fe29abde8b2fe08dd2bf604a075f1b408fa64f7a28207da54ef5, every commit root, the journal and the snapshots)
classes of the cut: mid commit line, mid journal line, mid line, mid snapshot
```

## What K5 needed from cint #512 (a resumable fuel point), and what it did not

It did not need it. A K5 task is a step function, so a turn ends at a step boundary, where the count is exact
because the entry has ended; the quantum is at step granularity and the journal's stamps are totals over whole
steps. What the hook would add: a step that computes for a long time cannot be ended at a given fuel count, so it
delays the other tasks (latency only: tasks share nothing, and what a schedule can change is journaled). Fuel is
per entry (`cint_rt_entry_begin` zeroes it), so a runtime that runs a task in steps adds the entries up
(`docs/cint-gaps.md` item 16).

## Mutation tests of the K5 checks

43 mutations, each a one-place edit in a copy under `/tmp/opencode`, built with gcc and clang, and run through the
checks that `check.sh` runs on them (`check-k5` on network 0, the five quanta and the control, replay at two other
quanta, the two tamper tests, networks 1 to 8, twelve kill points, two kills on network 8 and 1, the audit, the restore
refusals). **43 caught, 0 not caught, 0 invalid** (a build error).

How the table came about, because it is not one run. The first 30 (K1 to K30) were run against the checks as they
were when the two advisors reviewed the stage, with the result that 6 were not caught: K5 (my driver looked for any `diverged` line; the gate looks for the exact one),
K7 (a stale request field), K10 and K11 (the scheduler's place in the snapshot: snapshots every sixth commit always fell
between passes of three tasks), K22 (a fuel count that was the last step's) and K24 (the arguments after a restore);
the advisors' own mutations showed more holes. The checks
were strengthened (a residue check on every snapshot, strictly increasing stamps, networks 5 to 8, the audit flag, the
kernel tables of the final snapshot against the model, restore from every snapshot, an altered journal under a valid
digest) and N1 to N13 were added from the reviews. The whole list (K1 to N13) was then run again against the checks of
that moment, and 6 were still not caught (K11, K23, K24, N7, N12, N13). Three more checks were added (snapshots every fifth commit; a task that is
never run has its initial image; restore from every snapshot at q=1; an altered journal; the record length read before
the probe that clears it) and those six, with K10 as a control, were run a third time and caught. The other 36 were not
run again after the last additions, which only added checks. So **no mutation here is known to pass the final gate**;
what "equivalent" means for the others was not needed.

| id | mutation | outcome | caught by / why not |
| --- | --- | --- | --- |
| K1 | the kernel leaf omits the input count | caught | check-k5: all 12 snapshots are whole and verify: digest, leaves from their preimages, root, ch; net 1: FAIL  task 0 asked for the length of the last t |
| K2 | restore does not apply the module state | caught | killrun: FAIL: 1 of 12 kill points restored to the uninterrupted run (final root 7d18dbc18fa196964d5f22c2d1fc; killrun net 8; killrun net 1 |
| K3 | restore does not restore the pages | caught | killrun: FAIL: 1 of 12 kill points restored to the uninterrupted run (final root 7d18dbc18fa196964d5f22c2d1fc; killrun net 1 |
| K4 | restore does not read the journal tail | caught | replay q=250 at q=1: final root or journal differs; replay q=1 at q=250: final root or journal differs; tampered journal was not refused |
| K5 | a replayed select ignores the fuel stamp | caught | tampered journal was not refused |
| K6 | a stale value stays in a channel slot | caught | check-k5: no snapshot holds the residue of a request that was served, or a value past the coun; replay q=250 at q=1: final root or journal differs; re |
| K7 | a stale request fuel stays in the tables | caught | check-k5: no snapshot holds the residue of a request that was served, or a value past the coun |
| K8 | the chain does not include the previous chain | caught | check-k5: the journal verifies: 48 entries, every chain and sequence number: task 1 seq 0: cha; replay q=250 at q=1: final root or journal differs; re |
| K9 | input chunks of 6 bytes | caught | check-k5: the editor's 12 input entries are the script, chunked as specified: got [(b'alpha',  |
| K10 | the snapshot does not keep the next task | caught | killrun: FAIL: 5 of 12 kill points restored to the uninterrupted run (final root 7d18dbc18fa196964d5f22c2d1fc; restore from every snapshot (q=1) |
| K11 | the snapshot does not keep the ran flag | caught | restore from every snapshot (q=1) |
| K12 | the walk is not run | caught | net 2: FAIL  the first commit is refused with the right line and the run halts with no commit and; net 2: FAIL  the first commit is refused with the r |
| K13 | the walk does not look for a frame in two spaces | caught | net 2: FAIL  the first commit is refused with the right line and the run halts with no commit and; net 2: FAIL  the first commit is refused with the r |
| K14 | the walk does not look at writable and executable | caught | net 3: FAIL  the first commit is refused with the right line and the run halts with no commit and; net 3: FAIL  the first commit is refused with the r |
| K15 | a grant does not unmap the giver | caught | check-k5: the run ends with its final root (the last commit's), the commit count and the run l; the roots do not vary with the quantum; net 4: FAIL  t |
| K16 | tasks run in the kernel's space | caught | check-k5: the run ends with its final root (the last commit's), the commit count and the run l; the roots do not vary with the quantum; net 1: FAIL  t |
| K17 | rt_wx_init does nothing | caught | boot status 63 at q=0; boot status 63 at q=1; boot status 63 at q=100 |
| K18 | data pages stay executable | caught | gcc and clang transcripts differ; check-k5: the boot tables have no entry both writable and executable, and a store into the cod; net 1: FAIL  the boo |
| K19 | the digest of a snapshot leaves out what is in no leaf | caught | check-k5: all 12 snapshots are whole and verify: digest, leaves from their preimages, root, ch; net 1: FAIL  task 0 asked for the length of the last t |
| K20 | restore does not keep the inbox value | caught | killrun: FAIL: 2 of 12 kill points restored to the uninterrupted run (final root 7d18dbc18fa196964d5f22c2d1fc; killrun net 8 |
| K21 | the quantum is in the kernel leaf | caught | check-k5: all 12 snapshots are whole and verify: digest, leaves from their preimages, root, ch; replay q=250 at q=1: final root or journal differs; re |
| K22 | the fuel count is the last step's, not the total | caught | check-k5: the fuel stamps of each task go up from one entry to the next (every step costs fuel |
| K23 | an absent block is encoded as the wrong image | caught | net 8: FAIL  task 1 never touches its module state, so its block is absent and is encoded as the ; net 8: FAIL  task 1 never touches its module state, |
| K24 | restore does not set the next step's arguments | caught | restore from every snapshot (q=1) |
| K25 | the chain of a replayed entry is not checked | caught | tampered journal chain was not refused |
| K26 | a replayed select does not wait for its winner | caught | replay q=250 at q=1: final root or journal differs; replay q=1 at q=250: final root or journal differs; killrun: FAIL: 7 of 12 kill points restored to |
| K27 | deliver does not tell the task | caught | check-k5: the run ends with its final root (the last commit's), the commit count and the run l; the roots do not vary with the quantum; net 8: FAIL  t |
| K28 | a page moves to the receiver at the giver's slot | caught | net 4: FAIL  the run ends with its final root (the last commit's), the commit count and the run l; net 4: FAIL  the run ends with its final root (the  |
| K29 | the editor's page is not the sink's after the take | caught | check-k5: the run ends with its final root (the last commit's), the commit count and the run l; the roots do not vary with the quantum; net 4: FAIL  t |
| K30 | a task's pages are not in its leaf | caught | check-k5: the final snapshot is what the model says: producer block after 24 rounds, editor ch; killrun: FAIL: 1 of 12 kill points restored to the uni |
| N1 | a served request leaves its arguments in the tables | caught | check-k5: no snapshot holds the residue of a request that was served, or a value past the coun |
| N2 | the walk does not look at the upper tables | caught | net 5: FAIL  the first commit is refused with the right line and the run halts with no commit and; net 5: FAIL  the first commit is refused with the r |
| N3 | the walk does not compare with the kernel's page table | caught | net 6: FAIL  the first commit is refused with the right line and the run halts with no commit and; net 6: FAIL  the first commit is refused with the r |
| N4 | a grant does not mark the receiver's leaf | caught | audit found a stale leaf |
| N5 | state outside the task modules is accepted | caught | net 7: FAIL  the first commit is refused with the right line and the run halts with no commit and; net 7: FAIL  the first commit is refused with the r |
| N6 | the read-only data stays executable | caught | boot status 63 at q=0; boot status 63 at q=1; boot status 63 at q=100 |
| N7 | an adopted trap record stays readable by other tasks | caught | net 1: FAIL  task 0 asked for the length of the last trap record after task 1 faulted and was tol; net 1: FAIL  task 0 asked for the length of the las |
| N8 | values of 2^63 and above fault on restore (a checked decode) | caught | killrun net 8 |
| N9 | a halted kernel goes on committing | caught | tampered journal was not refused; tampered journal chain was not refused |
| N10 | input consumed leaves out the line ends | caught | check-k5: the kernel's tables in the final snapshot: nothing pending, journal lengths 0, 12 an |
| N11 | restore turns a faulted task into a live one | caught | killrun net 1 |
| N12 | the inbox tag is not in the kernel leaf | caught | restore from every snapshot (q=1) |
| N13 | restore does not check a journal against the chain head | caught | restore of a journal snapshot not refused |

The two advisors also ran mutations of their own in copies (9 and 12); what they found is in `docs/notes.md` and
was fixed or is listed above. Their defects, all fixed: a task could read another's fault record
(`trap_record_len`), a value of 2^63 or more faulted the restore, a halted kernel went on committing and printed a
snapshot; and the tests that were missing for them.

## Known limits

* Ring 0 tasks: every task space maps the whole image, and the kernel's space maps all of RAM. The hardware check is
  exactly the page slots the kernel grants; ring 3 is U1 (`docs/snapshot.md` section 6).
* Three tasks, four channels, eight page slots, a journal of 1 KiB per task, a module state of 4 KiB per task: the
  kernel halts rather than overflow.
* The journal and the snapshots go out on the serial port and come back through QEMU's loader; there is no disk. The
  promise stops at the last journal entry that reached the port (input read from the device and not yet journaled is
  typed again by the script).
* A step that computes for long is not interrupted (#512); the quantum is at step boundaries.
* The input chunk is up to 7 bytes; one reader.
* Nothing ran on KVM or on hardware. Timing of the kill is real (SIGKILL when the machine has written the byte),
  the cut is exact.
* The inbox of a task that holds a delivered value it has not yet used is restored (checked by the kills of the q=1
  run), but a snapshot at that moment is rare at q=250; the audit and the kills at q=1 are what cover it.
* The head of this branch contains no model name; the commits of the older stages carry what they carried before
  the history was rewritten.

## Full log of the clean-clone run

```
gcc:    gcc (GCC) 16.2.1 20260810
clang:  clang version 23.1.3
qemu:   QEMU emulator version 11.1.2
ld:     GNU ld (GNU Binutils) 2.47
cint compiler source identity: 18620842d9aa78bf9c1ca72316ef3e1a9ddd44c91143ebf6439c4952a1dc2a0e
cint executable sha256:        42d15d580a5e2272d3f8ebc08434923add1b14ba3325c7289aa6f4383b865309
cint_rt.h sha256:              1f1be52c0c96c69c87dd50342bfc0f3516f325b553f9c911bd1505da9911e9c8
PASS  toolchain: cint_rt.h matches toolchain.pin
PASS  toolchain: compiler source identity matches toolchain.pin
PASS  toolchain: the cint on PATH is the executable the toolchain file names
PASS  hosted: cint test tests/src_test.ci (13 of 13 tests passed)
PASS  build: gcc and clang, flavors k1 fault trap stackover nullptr faults mem coop preempt shep k5 (make)
PASS  build: every gcc-k1 object was compiled by gcc (.comment names it)
PASS  build: every clang-k1 object was compiled by clang (.comment names it)
PASS  build: the gcc and clang images differ (two different compilers built them)
image sha256:
  gcc-k1  f2e317d8f65bdb901c0b5e4f984b6ffd21588180f1b5774fb9322ce6e537e17a
  gcc-fault  4c84e9d90bd72cd90737e1602e099a233d7dd2cd7be497e8b605581f52659dd2
  gcc-trap  52959484c1bff98feb934b02da5df5ef7afa8d3c9f89a5df9c7d9464cfd58fc1
  gcc-stackover  067bc56571b797cd7cf391d0685af3184c19911888e65aa075cdcbee081b6cb4
  gcc-nullptr  7b3d902bf049eec93dc8a4f93d35703c872134f318654545667a293b54cc9a78
  gcc-faults  cddb6c534b4e7c33e9b62afbb8a2d4bc4c05057c3880607217f0178b6634a4c9
  gcc-mem  177dd72b3945d7f30960db31307fe571adc545dbe82be1db061d22278522dddf
  gcc-coop  c60dc10a54b54fbc4c4510b7efd6490fcf5bf40945ef653cb955855bcf18f81f
  gcc-preempt  360e243351a26fcc197b92b107e48dcd97264e3922054504c1cadf8664f25943
  gcc-shep  6e00d692a41bcf0ef63b87472064b8c11e23a1aee3fc3b1e9b8947c76a48d419
  gcc-k5  d135f63a0efbd6a647a9b400b0ec75df368430e6f96a432386e9bb69c4af4e42
  clang-k1  a1d659449947bd5a2a3622f42de7d1a61bc3a043b6f3a4f2d21e71944db05e87
  clang-fault  2f1d3dff6d088d95aab27187a0bdd4448f6f064f02a99932e06f1e2cbf565c08
  clang-trap  5eaf2c477177e83d01911697892fa20f980ed337b5be1de8fc253bda01a47c70
  clang-stackover  89f80e4030d54160b3772fe8b1d51c547072cb1ba8443d9a43a86a64c52b6ca2
  clang-nullptr  2980d361efde0b8d61e0382b2107bf3d1275e5a666c6a2822916834af478d9ee
  clang-faults  4e0a7dd22f9817888b3eaedaf89736005527f867dfb15e4fa42db598b9657129
  clang-mem  620c2df766ddc2fd7e4b0f072a11b5398e424551609d6dbaed1a0804570057e6
  clang-coop  203b48bd4630e68f8be20ccc8dd4fe1be4d17bdae76a48a36202d25e66581894
  clang-preempt  4582f02b4131b482b046c6fd6161f1dc308fcaf5bb7b84184d430eb9715f7626
  clang-shep  255b8961104b03218529c935f46d81211daa8bd71742c0e7459e227462c60df9
  clang-k5  7347254d2b8ee70a5a28ecc1350a9960e519204b2105ab5e3db73b1d9f611da6
PASS  build: a second build in another directory gives byte-identical images
PASS  audit gcc-k1: every object's undefined symbols are defined in this build
PASS  audit gcc-k1: image has no undefined symbol (nm -u empty)
PASS  audit gcc-k1: no libc symbol in any object or the image
PASS  audit gcc-k1: mem functions are exactly the four of rt/mem.c
PASS  audit gcc-k1: no SSE, AVX or x87 instruction in any object
PASS  audit gcc-fault: every object's undefined symbols are defined in this build
PASS  audit gcc-fault: image has no undefined symbol (nm -u empty)
PASS  audit gcc-fault: no libc symbol in any object or the image
PASS  audit gcc-fault: mem functions are exactly the four of rt/mem.c
PASS  audit gcc-fault: no SSE, AVX or x87 instruction in any object
PASS  audit gcc-trap: every object's undefined symbols are defined in this build
PASS  audit gcc-trap: image has no undefined symbol (nm -u empty)
PASS  audit gcc-trap: no libc symbol in any object or the image
PASS  audit gcc-trap: mem functions are exactly the four of rt/mem.c
PASS  audit gcc-trap: no SSE, AVX or x87 instruction in any object
PASS  audit gcc-stackover: every object's undefined symbols are defined in this build
PASS  audit gcc-stackover: image has no undefined symbol (nm -u empty)
PASS  audit gcc-stackover: no libc symbol in any object or the image
PASS  audit gcc-stackover: mem functions are exactly the four of rt/mem.c
PASS  audit gcc-stackover: no SSE, AVX or x87 instruction in any object
PASS  audit gcc-nullptr: every object's undefined symbols are defined in this build
PASS  audit gcc-nullptr: image has no undefined symbol (nm -u empty)
PASS  audit gcc-nullptr: no libc symbol in any object or the image
PASS  audit gcc-nullptr: mem functions are exactly the four of rt/mem.c
PASS  audit gcc-nullptr: no SSE, AVX or x87 instruction in any object
PASS  audit gcc-faults: every object's undefined symbols are defined in this build
PASS  audit gcc-faults: image has no undefined symbol (nm -u empty)
PASS  audit gcc-faults: no libc symbol in any object or the image
PASS  audit gcc-faults: mem functions are exactly the four of rt/mem.c
PASS  audit gcc-faults: no SSE, AVX or x87 instruction in any object
PASS  audit gcc-mem: every object's undefined symbols are defined in this build
PASS  audit gcc-mem: image has no undefined symbol (nm -u empty)
PASS  audit gcc-mem: no libc symbol in any object or the image
PASS  audit gcc-mem: mem functions are exactly the four of rt/mem.c
PASS  audit gcc-mem: no SSE, AVX or x87 instruction in any object
PASS  audit gcc-coop: every object's undefined symbols are defined in this build
PASS  audit gcc-coop: image has no undefined symbol (nm -u empty)
PASS  audit gcc-coop: no libc symbol in any object or the image
PASS  audit gcc-coop: mem functions are exactly the four of rt/mem.c
PASS  audit gcc-coop: no SSE, AVX or x87 instruction in any object
PASS  audit gcc-preempt: every object's undefined symbols are defined in this build
PASS  audit gcc-preempt: image has no undefined symbol (nm -u empty)
PASS  audit gcc-preempt: no libc symbol in any object or the image
PASS  audit gcc-preempt: mem functions are exactly the four of rt/mem.c
PASS  audit gcc-preempt: no SSE, AVX or x87 instruction in any object
PASS  audit gcc-shep: every object's undefined symbols are defined in this build
PASS  audit gcc-shep: image has no undefined symbol (nm -u empty)
PASS  audit gcc-shep: no libc symbol in any object or the image
PASS  audit gcc-shep: mem functions are exactly the four of rt/mem.c
PASS  audit gcc-shep: no SSE, AVX or x87 instruction in any object
PASS  audit gcc-k5: every object's undefined symbols are defined in this build
PASS  audit gcc-k5: image has no undefined symbol (nm -u empty)
PASS  audit gcc-k5: no libc symbol in any object or the image
PASS  audit gcc-k5: mem functions are exactly the four of rt/mem.c
PASS  audit gcc-k5: no SSE, AVX or x87 instruction in any object
PASS  audit clang-k1: every object's undefined symbols are defined in this build
PASS  audit clang-k1: image has no undefined symbol (nm -u empty)
PASS  audit clang-k1: no libc symbol in any object or the image
PASS  audit clang-k1: mem functions are exactly the four of rt/mem.c
PASS  audit clang-k1: no SSE, AVX or x87 instruction in any object
PASS  audit clang-fault: every object's undefined symbols are defined in this build
PASS  audit clang-fault: image has no undefined symbol (nm -u empty)
PASS  audit clang-fault: no libc symbol in any object or the image
PASS  audit clang-fault: mem functions are exactly the four of rt/mem.c
PASS  audit clang-fault: no SSE, AVX or x87 instruction in any object
PASS  audit clang-trap: every object's undefined symbols are defined in this build
PASS  audit clang-trap: image has no undefined symbol (nm -u empty)
PASS  audit clang-trap: no libc symbol in any object or the image
PASS  audit clang-trap: mem functions are exactly the four of rt/mem.c
PASS  audit clang-trap: no SSE, AVX or x87 instruction in any object
PASS  audit clang-stackover: every object's undefined symbols are defined in this build
PASS  audit clang-stackover: image has no undefined symbol (nm -u empty)
PASS  audit clang-stackover: no libc symbol in any object or the image
PASS  audit clang-stackover: mem functions are exactly the four of rt/mem.c
PASS  audit clang-stackover: no SSE, AVX or x87 instruction in any object
PASS  audit clang-nullptr: every object's undefined symbols are defined in this build
PASS  audit clang-nullptr: image has no undefined symbol (nm -u empty)
PASS  audit clang-nullptr: no libc symbol in any object or the image
PASS  audit clang-nullptr: mem functions are exactly the four of rt/mem.c
PASS  audit clang-nullptr: no SSE, AVX or x87 instruction in any object
PASS  audit clang-faults: every object's undefined symbols are defined in this build
PASS  audit clang-faults: image has no undefined symbol (nm -u empty)
PASS  audit clang-faults: no libc symbol in any object or the image
PASS  audit clang-faults: mem functions are exactly the four of rt/mem.c
PASS  audit clang-faults: no SSE, AVX or x87 instruction in any object
PASS  audit clang-mem: every object's undefined symbols are defined in this build
PASS  audit clang-mem: image has no undefined symbol (nm -u empty)
PASS  audit clang-mem: no libc symbol in any object or the image
PASS  audit clang-mem: mem functions are exactly the four of rt/mem.c
PASS  audit clang-mem: no SSE, AVX or x87 instruction in any object
PASS  audit clang-coop: every object's undefined symbols are defined in this build
PASS  audit clang-coop: image has no undefined symbol (nm -u empty)
PASS  audit clang-coop: no libc symbol in any object or the image
PASS  audit clang-coop: mem functions are exactly the four of rt/mem.c
PASS  audit clang-coop: no SSE, AVX or x87 instruction in any object
PASS  audit clang-preempt: every object's undefined symbols are defined in this build
PASS  audit clang-preempt: image has no undefined symbol (nm -u empty)
PASS  audit clang-preempt: no libc symbol in any object or the image
PASS  audit clang-preempt: mem functions are exactly the four of rt/mem.c
PASS  audit clang-preempt: no SSE, AVX or x87 instruction in any object
PASS  audit clang-shep: every object's undefined symbols are defined in this build
PASS  audit clang-shep: image has no undefined symbol (nm -u empty)
PASS  audit clang-shep: no libc symbol in any object or the image
PASS  audit clang-shep: mem functions are exactly the four of rt/mem.c
PASS  audit clang-shep: no SSE, AVX or x87 instruction in any object
PASS  audit clang-k5: every object's undefined symbols are defined in this build
PASS  audit clang-k5: image has no undefined symbol (nm -u empty)
PASS  audit clang-k5: no libc symbol in any object or the image
PASS  audit clang-k5: mem functions are exactly the four of rt/mem.c
PASS  audit clang-k5: no SSE, AVX or x87 instruction in any object
PASS  K0: symbol audit ran and passed (110 checks, 5 per build, gcc and clang, flavors k1 fault trap stackover nullptr faults mem coop preempt shep k5)
PASS  boot gcc-k1: QEMU exit status 33 on both runs
PASS  boot gcc-k1: QEMU wrote nothing to stderr
PASS  boot gcc-fault: QEMU exit status 35 on both runs
PASS  boot gcc-fault: QEMU wrote nothing to stderr
PASS  boot gcc-trap: QEMU exit status 33 on both runs
PASS  boot gcc-trap: QEMU wrote nothing to stderr
PASS  boot gcc-stackover: QEMU exit status 33 on both runs
PASS  boot gcc-stackover: QEMU wrote nothing to stderr
PASS  boot gcc-nullptr: QEMU exit status 33 on both runs
PASS  boot gcc-nullptr: QEMU wrote nothing to stderr
PASS  boot gcc-faults: QEMU exit status 33 on both runs
PASS  boot gcc-faults: QEMU wrote nothing to stderr
PASS  boot gcc-mem: QEMU exit status 33 on both runs
PASS  boot gcc-mem: QEMU wrote nothing to stderr
PASS  boot gcc-coop: QEMU exit status 33 on both runs
PASS  boot gcc-coop: QEMU wrote nothing to stderr
PASS  boot gcc-preempt: QEMU exit status 33 on both runs
PASS  boot gcc-preempt: QEMU wrote nothing to stderr
PASS  boot gcc-shep: QEMU exit status 33 on both runs
PASS  boot gcc-shep: QEMU wrote nothing to stderr
PASS  boot gcc-k5: QEMU exit status 33 on both runs
PASS  boot gcc-k5: QEMU wrote nothing to stderr
PASS  boot clang-k1: QEMU exit status 33 on both runs
PASS  boot clang-k1: QEMU wrote nothing to stderr
PASS  boot clang-fault: QEMU exit status 35 on both runs
PASS  boot clang-fault: QEMU wrote nothing to stderr
PASS  boot clang-trap: QEMU exit status 33 on both runs
PASS  boot clang-trap: QEMU wrote nothing to stderr
PASS  boot clang-stackover: QEMU exit status 33 on both runs
PASS  boot clang-stackover: QEMU wrote nothing to stderr
PASS  boot clang-nullptr: QEMU exit status 33 on both runs
PASS  boot clang-nullptr: QEMU wrote nothing to stderr
PASS  boot clang-faults: QEMU exit status 33 on both runs
PASS  boot clang-faults: QEMU wrote nothing to stderr
PASS  boot clang-mem: QEMU exit status 33 on both runs
PASS  boot clang-mem: QEMU wrote nothing to stderr
PASS  boot clang-coop: QEMU exit status 33 on both runs
PASS  boot clang-coop: QEMU wrote nothing to stderr
PASS  boot clang-preempt: QEMU exit status 33 on both runs
PASS  boot clang-preempt: QEMU wrote nothing to stderr
PASS  boot clang-shep: QEMU exit status 33 on both runs
PASS  boot clang-shep: QEMU wrote nothing to stderr
PASS  boot clang-k5: QEMU exit status 33 on both runs
PASS  boot clang-k5: QEMU wrote nothing to stderr
transcript sha256:
  gcc-k1 run 1  ebaafdcaaefe7e71a0cf70c20e10862e5d9df09039f7d021858925c7498b8c37
  gcc-k1 run 2  ebaafdcaaefe7e71a0cf70c20e10862e5d9df09039f7d021858925c7498b8c37
  gcc-fault run 1  b08016e22ff0279b38faebb244707e1ea2d4ad44e1ea9c2904cd424c2a860a5f
  gcc-fault run 2  b08016e22ff0279b38faebb244707e1ea2d4ad44e1ea9c2904cd424c2a860a5f
  gcc-trap run 1  96111417515335511c9d97018ed639d045ddb33539ec33e5ca1e536532eefd8d
  gcc-trap run 2  96111417515335511c9d97018ed639d045ddb33539ec33e5ca1e536532eefd8d
  gcc-stackover run 1  e9637b872d75c13380f4e40f8f9ca4311f1de9bd9dcacf1dab72bb34df39f183
  gcc-stackover run 2  e9637b872d75c13380f4e40f8f9ca4311f1de9bd9dcacf1dab72bb34df39f183
  gcc-nullptr run 1  e1849a2e6384b6cd58066cc1b0b8b599338b3990e255d7e686927e8c63500f23
  gcc-nullptr run 2  e1849a2e6384b6cd58066cc1b0b8b599338b3990e255d7e686927e8c63500f23
  gcc-faults run 1  5a70ab8d84bde0f7f834d6462e817de9bd0edc7f493bd406b13ab73116b86a12
  gcc-faults run 2  5a70ab8d84bde0f7f834d6462e817de9bd0edc7f493bd406b13ab73116b86a12
  gcc-mem run 1  1024719344d85b8da2b4f4e08de0c6dc95045d39569faf01412cf3797c3b1b1f
  gcc-mem run 2  1024719344d85b8da2b4f4e08de0c6dc95045d39569faf01412cf3797c3b1b1f
  gcc-coop run 1  ad7588667f7d2a13158e7af30cd7c82a40bc680483aaff73768fbdf58bc4b26a
  gcc-coop run 2  ad7588667f7d2a13158e7af30cd7c82a40bc680483aaff73768fbdf58bc4b26a
  gcc-preempt run 1  19d5dcb0671454537bacde5092c3e0c1f2b0fbf5ffb0c0ff2fefbe0c685b3c64
  gcc-preempt run 2  19d5dcb0671454537bacde5092c3e0c1f2b0fbf5ffb0c0ff2fefbe0c685b3c64
  gcc-shep run 1  13b3292fdeab665e1e2d95a1b6ee528fa5db71dbd3e575aa762730069e392520
  gcc-shep run 2  13b3292fdeab665e1e2d95a1b6ee528fa5db71dbd3e575aa762730069e392520
  gcc-k5 run 1  0b3a004d99c095ea07a312b7e038022317fdc531e64b16437ffea88f699b8fd5
  gcc-k5 run 2  0b3a004d99c095ea07a312b7e038022317fdc531e64b16437ffea88f699b8fd5
  clang-k1 run 1  ebaafdcaaefe7e71a0cf70c20e10862e5d9df09039f7d021858925c7498b8c37
  clang-k1 run 2  ebaafdcaaefe7e71a0cf70c20e10862e5d9df09039f7d021858925c7498b8c37
  clang-fault run 1  b08016e22ff0279b38faebb244707e1ea2d4ad44e1ea9c2904cd424c2a860a5f
  clang-fault run 2  b08016e22ff0279b38faebb244707e1ea2d4ad44e1ea9c2904cd424c2a860a5f
  clang-trap run 1  96111417515335511c9d97018ed639d045ddb33539ec33e5ca1e536532eefd8d
  clang-trap run 2  96111417515335511c9d97018ed639d045ddb33539ec33e5ca1e536532eefd8d
  clang-stackover run 1  e9637b872d75c13380f4e40f8f9ca4311f1de9bd9dcacf1dab72bb34df39f183
  clang-stackover run 2  e9637b872d75c13380f4e40f8f9ca4311f1de9bd9dcacf1dab72bb34df39f183
  clang-nullptr run 1  e1849a2e6384b6cd58066cc1b0b8b599338b3990e255d7e686927e8c63500f23
  clang-nullptr run 2  e1849a2e6384b6cd58066cc1b0b8b599338b3990e255d7e686927e8c63500f23
  clang-faults run 1  5a70ab8d84bde0f7f834d6462e817de9bd0edc7f493bd406b13ab73116b86a12
  clang-faults run 2  5a70ab8d84bde0f7f834d6462e817de9bd0edc7f493bd406b13ab73116b86a12
  clang-mem run 1  1024719344d85b8da2b4f4e08de0c6dc95045d39569faf01412cf3797c3b1b1f
  clang-mem run 2  1024719344d85b8da2b4f4e08de0c6dc95045d39569faf01412cf3797c3b1b1f
  clang-coop run 1  ad7588667f7d2a13158e7af30cd7c82a40bc680483aaff73768fbdf58bc4b26a
  clang-coop run 2  ad7588667f7d2a13158e7af30cd7c82a40bc680483aaff73768fbdf58bc4b26a
  clang-preempt run 1  19d5dcb0671454537bacde5092c3e0c1f2b0fbf5ffb0c0ff2fefbe0c685b3c64
  clang-preempt run 2  19d5dcb0671454537bacde5092c3e0c1f2b0fbf5ffb0c0ff2fefbe0c685b3c64
  clang-shep run 1  13b3292fdeab665e1e2d95a1b6ee528fa5db71dbd3e575aa762730069e392520
  clang-shep run 2  13b3292fdeab665e1e2d95a1b6ee528fa5db71dbd3e575aa762730069e392520
  clang-k5 run 1  0b3a004d99c095ea07a312b7e038022317fdc531e64b16437ffea88f699b8fd5
  clang-k5 run 2  0b3a004d99c095ea07a312b7e038022317fdc531e64b16437ffea88f699b8fd5
PASS  serial k1: gcc and clang transcripts byte-identical (cmp)
PASS  serial k1: gcc run 1 and run 2 byte-identical (cmp)
PASS  serial k1: clang run 1 and run 2 byte-identical (cmp)
PASS  serial fault: gcc and clang transcripts byte-identical (cmp)
PASS  serial fault: gcc run 1 and run 2 byte-identical (cmp)
PASS  serial fault: clang run 1 and run 2 byte-identical (cmp)
PASS  serial trap: gcc and clang transcripts byte-identical (cmp)
PASS  serial trap: gcc run 1 and run 2 byte-identical (cmp)
PASS  serial trap: clang run 1 and run 2 byte-identical (cmp)
PASS  serial stackover: gcc and clang transcripts byte-identical (cmp)
PASS  serial stackover: gcc run 1 and run 2 byte-identical (cmp)
PASS  serial stackover: clang run 1 and run 2 byte-identical (cmp)
PASS  serial nullptr: gcc and clang transcripts byte-identical (cmp)
PASS  serial nullptr: gcc run 1 and run 2 byte-identical (cmp)
PASS  serial nullptr: clang run 1 and run 2 byte-identical (cmp)
PASS  serial faults: gcc and clang transcripts byte-identical (cmp)
PASS  serial faults: gcc run 1 and run 2 byte-identical (cmp)
PASS  serial faults: clang run 1 and run 2 byte-identical (cmp)
PASS  serial mem: gcc and clang transcripts byte-identical (cmp)
PASS  serial mem: gcc run 1 and run 2 byte-identical (cmp)
PASS  serial mem: clang run 1 and run 2 byte-identical (cmp)
PASS  serial coop: gcc and clang transcripts byte-identical (cmp)
PASS  serial coop: gcc run 1 and run 2 byte-identical (cmp)
PASS  serial coop: clang run 1 and run 2 byte-identical (cmp)
PASS  serial preempt: gcc and clang transcripts byte-identical (cmp)
PASS  serial preempt: gcc run 1 and run 2 byte-identical (cmp)
PASS  serial preempt: clang run 1 and run 2 byte-identical (cmp)
PASS  serial shep: gcc and clang transcripts byte-identical (cmp)
PASS  serial shep: gcc run 1 and run 2 byte-identical (cmp)
PASS  serial shep: clang run 1 and run 2 byte-identical (cmp)
PASS  serial k5: gcc and clang transcripts byte-identical (cmp)
PASS  serial k5: gcc run 1 and run 2 byte-identical (cmp)
PASS  serial k5: clang run 1 and run 2 byte-identical (cmp)
PASS  sha256: gcc kernel prints the FIPS 180-4 vector for "abc"
PASS  serial k1: gcc transcript equals tests/expected/k1.serial
PASS  serial fault: gcc banner and record header equal tests/expected/fault.head
PASS  sha256: clang kernel prints the FIPS 180-4 vector for "abc"
PASS  serial k1: clang transcript equals tests/expected/k1.serial
PASS  serial fault: clang banner and record header equal tests/expected/fault.head
PASS  serial trap: gcc transcript equals tests/expected/trap.skeleton (record hex masked)
PASS  trap gcc: #DE, #UD and #PF records printed from cint decode as expected; PIT ticks counted (26 checks)
PASS  serial trap: clang transcript equals tests/expected/trap.skeleton (record hex masked)
PASS  trap clang: #DE, #UD and #PF records printed from cint decode as expected; PIT ticks counted (26 checks)
PASS  serial stackover: gcc transcript equals tests/expected/stackover.skeleton (record hex masked)
PASS  stackover gcc: records decode and match the table (30 checks)
PASS  serial stackover: clang transcript equals tests/expected/stackover.skeleton (record hex masked)
PASS  stackover clang: records decode and match the table (30 checks)
PASS  serial nullptr: gcc transcript equals tests/expected/nullptr.skeleton (record hex masked)
PASS  nullptr gcc: records decode and match the table (16 checks)
PASS  serial nullptr: clang transcript equals tests/expected/nullptr.skeleton (record hex masked)
PASS  nullptr clang: records decode and match the table (16 checks)
PASS  faults: the hosted runtime wrote a record for each of probes 0 to 9
PASS  faults gcc: 11 probes, 10 records byte-identical to the hosted runtime's, table and positions (68 checks)
PASS  serial faults: gcc transcript equals tests/expected/faults.skeleton (record hex masked)
PASS  faults clang: 11 probes, 10 records byte-identical to the hosted runtime's, table and positions (68 checks)
PASS  serial faults: clang transcript equals tests/expected/faults.skeleton (record hex masked)
PASS  faults: the hosted fuel fault has the kernel's shape (E_FUEL, fuel.charge, no operands, no exact, at src/probes.ci:75:5)
PASS  serial mem: gcc transcript equals tests/expected/mem.skeleton (record hex masked)
PASS  mem gcc: bad addresses, #PF records, refusals and hashes check out (74 checks)
PASS  serial mem: clang transcript equals tests/expected/mem.skeleton (record hex masked)
PASS  mem clang: bad addresses, #PF records, refusals and hashes check out (74 checks)
PASS  mem gcc: booted with -m 64 the summary says 'ram: MiB 64' and nothing else changes
PASS  mem clang: booted with -m 64 the summary says 'ram: MiB 64' and nothing else changes
PASS  mem: the hosted runtime, running src/allocdemo.ci, reproduces all six allocator-state hashes of the kernel
PASS  mem: the twin refuses a hash that differs in one digit (it can fail)
PASS  serial coop: gcc transcript equals tests/expected/coop.serial
PASS  serial coop: clang transcript equals tests/expected/coop.serial
PASS  serial preempt: gcc transcript equals tests/expected/preempt.serial
PASS  serial preempt: clang transcript equals tests/expected/preempt.serial
PASS  tasks: the service block of src/main_tasks.ci is byte-identical to the hosted twin's
PASS  tasks coop gcc: the three task lines equal the hosted runtime's; task 2 holds console.raw only: read -1 (denied), raw 0
PASS  tasks coop clang: the three task lines equal the hosted runtime's; task 2 holds console.raw only: read -1 (denied), raw 0
PASS  tasks preempt gcc: the three task lines equal the hosted runtime's; task 2 holds console.raw only: read -1 (denied), raw 0
PASS  tasks preempt clang: the three task lines equal the hosted runtime's; task 2 holds console.raw only: read -1 (denied), raw 0
PASS  shep: the hosted twin ran the network with no scheduler and wrote its root (6359768015cb7e63bb670a771405a698df4e2567e23d103d298e785e82fb9b5b)
PASS  serial shep: gcc transcript equals tests/expected/shep.skeleton (record hex masked)
PASS  shep gcc: one root under 7 schedules (the twin's), digests differ, control splits, deadlock and fault as expected
PASS  serial shep: clang transcript equals tests/expected/shep.skeleton (record hex masked)
PASS  shep clang: one root under 7 schedules (the twin's), digests differ, control splits, deadlock and fault as expected
PASS  shep: only src/ownstate.c (the module-state test) asks for module state; the network's modules ask for none
PASS  shep -O0 gcc: boots (status 33) and the transcript equals the -O2 one byte for byte
PASS  shep -O0 clang: boots (status 33) and the transcript equals the -O2 one byte for byte
PASS  shep -O1 gcc: boots (status 33) and the transcript equals the -O2 one byte for byte
PASS  shep -O1 clang: boots (status 33) and the transcript equals the -O2 one byte for byte
PASS  shep -O3 gcc: boots (status 33) and the transcript equals the -O2 one byte for byte
PASS  shep -O3 clang: boots (status 33) and the transcript equals the -O2 one byte for byte
PASS  shep -Os gcc: boots (status 33) and the transcript equals the -O2 one byte for byte
PASS  shep -Os clang: boots (status 33) and the transcript equals the -O2 one byte for byte
PASS  k5 record q=0: gcc and clang transcripts byte-identical, both exit 33
PASS  k5 record q=0: Merkle roots, journal chains, the input chunking and the counts recomputed in Python
PASS  k5 record q=1: gcc and clang transcripts byte-identical, both exit 33
PASS  k5 record q=1: Merkle roots, journal chains, the input chunking and the counts recomputed in Python
PASS  k5 record q=100: gcc and clang transcripts byte-identical, both exit 33
PASS  k5 record q=100: Merkle roots, journal chains, the input chunking and the counts recomputed in Python
PASS  k5 record q=250: gcc and clang transcripts byte-identical, both exit 33
PASS  k5 record q=250: Merkle roots, journal chains, the input chunking and the counts recomputed in Python
PASS  k5 record q=2000: gcc and clang transcripts byte-identical, both exit 33
PASS  k5 record q=2000: Merkle roots, journal chains, the input chunking and the counts recomputed in Python
PASS  k5 control: the racy network gives 3 different final roots under 5 quanta (the schedule shows)
PASS  k5 replay of the q=0 recording: on clang (q=1), on gcc from the clang recording (q=1), on gcc -O0 and clang -O0 (q=250): same final root, same journal, same final leaves
PASS  k5 replay of the q=1 recording: on clang (q=100), on gcc from the clang recording (q=100), on gcc -O0 and clang -O0 (q=2000): same final root, same journal, same final leaves
PASS  k5 replay of the q=100 recording: on clang (q=250), on gcc from the clang recording (q=250), on gcc -O0 and clang -O0 (q=0): same final root, same journal, same final leaves
PASS  k5 replay of the q=250 recording: on clang (q=2000), on gcc from the clang recording (q=2000), on gcc -O0 and clang -O0 (q=1): same final root, same journal, same final leaves
PASS  k5 replay of the q=2000 recording: on clang (q=0), on gcc from the clang recording (q=0), on gcc -O0 and clang -O0 (q=100): same final root, same journal, same final leaves
PASS  k5 net 1: gcc and clang transcripts byte-identical under q=0 and q=1, all exit 33
PASS  k5 net 1: decoded and recomputed in Python (9 checks under each of two quanta)
PASS  k5 net 2: gcc and clang transcripts byte-identical under q=0 and q=1, all exit 33
PASS  k5 net 2: decoded and recomputed in Python (1 checks under each of two quanta)
PASS  k5 net 3: gcc and clang transcripts byte-identical under q=0 and q=1, all exit 33
PASS  k5 net 3: decoded and recomputed in Python (1 checks under each of two quanta)
PASS  k5 net 4: gcc and clang transcripts byte-identical under q=0 and q=1, all exit 33
PASS  k5 net 4: decoded and recomputed in Python (8 checks under each of two quanta)
PASS  k5 net 5: gcc and clang transcripts byte-identical under q=0 and q=1, all exit 33
PASS  k5 net 5: decoded and recomputed in Python (1 checks under each of two quanta)
PASS  k5 net 6: gcc and clang transcripts byte-identical under q=0 and q=1, all exit 33
PASS  k5 net 6: decoded and recomputed in Python (1 checks under each of two quanta)
PASS  k5 net 7: gcc and clang transcripts byte-identical under q=0 and q=1, all exit 33
PASS  k5 net 7: decoded and recomputed in Python (1 checks under each of two quanta)
PASS  k5 net 8: gcc and clang transcripts byte-identical under q=0 and q=1, all exit 33
PASS  k5 net 8: decoded and recomputed in Python (8 checks under each of two quanta)
PASS  k5 net 1: the fault record of the refused page access is the same bytes under q=0 and q=1, on gcc and clang, at -O2 and -O0
PASS  k5 net 4: the fault record of the refused page access is the same bytes under q=0 and q=1, on gcc and clang, at -O2 and -O0
  [kill gcc] classes of the cut: mid commit line, mid journal line, mid line, mid snapshot
PASS  k5 kill and restore (gcc, q=250): 20 of 20 seeded kill points restore to the uninterrupted final root, commit roots, journal and snapshots
  [kill clang] classes of the cut: mid commit line, mid journal line, mid line, mid snapshot
PASS  k5 kill and restore (clang, q=1): 20 of 20 seeded kill points restore to the uninterrupted final root, commit roots, journal and snapshots
PASS  k5 kill and restore (network 1): 8 of 8 kill points, the last from the final snapshot, restore to the uninterrupted run
PASS  k5 kill and restore (network 4): 8 of 8 kill points, the last from the final snapshot, restore to the uninterrupted run
PASS  k5 kill and restore (network 8): 8 of 8 kill points, the last from the final snapshot, restore to the uninterrupted run
PASS  k5 audit q=250: every cached leaf equals the leaf made again from the state at every commit, and the audit adds no byte to the transcript
PASS  k5 audit q=1: every cached leaf equals the leaf made again from the state at every commit, and the audit adds no byte to the transcript
PASS  k5 restore from every snapshot (gcc, q=1): 18 snapshots, each restored and finished to the uninterrupted run
PASS  k5 restore from every snapshot (gcc, q=250): 12 snapshots, each restored and finished to the uninterrupted run
PASS  k5 restore: a snapshot with one flipped digit is refused (its digest is wrong), nothing runs
PASS  k5 restore: a snapshot whose journal is not the one its tables say (digest made again) is refused, nothing runs
PASS  k5 restore: a snapshot whose program revision is another build's is refused, nothing runs
PASS  k5 replay of a recording made by gcc at -O0, on clang at -O2 under q=1: same final root, same journal
PASS  k5 replay of a recording made by clang at -O0, on gcc at -O2 under q=1: same final root, same journal
PASS  k5 replay: a journal whose fuel stamp is one off is refused at the entry (diverged: task 2 entry 5), the run halts, no commit or snapshot follows
PASS  k5 replay: an entry whose chain is one bit off is refused (diverged: journal chain), the run halts
PASS  k5 diverge: the divergence finder names the planted mutation (commit, task, leaves) and agrees on a run with itself
PASS  fault: hosted runtime wrote its record for tests/fault_probe.ci
  [gcc] PASS  kernel record length matches its header (187 bytes)
  [gcc] PASS  both records decode as cint-core-1/fault/v2
  [gcc] PASS  kernel equals hosted: domain
  [gcc] PASS  kernel equals hosted: code
  [gcc] PASS  kernel equals hosted: operation
  [gcc] PASS  kernel equals hosted: operands
  [gcc] PASS  kernel equals hosted: exact
  [gcc] PASS  kernel equals hosted: limit
  [gcc] PASS  kernel equals hosted: srcmap
  [gcc] PASS  kernel equals hosted: address_present
  [gcc] PASS  kernel equals hosted: position
  [gcc] PASS  kernel position is src/overflow.ci:7:23
  [gcc] PASS  kernel and hosted stacks both have one entry
  [gcc] PASS  kernel stack is the call site src/main_fault.ci:11:22
  [gcc] PASS  kernel revision equals cg_revision of its emitted program
  [gcc] PASS  hosted revision is present and differs (different program)
PASS  fault gcc: record printed, decodes, and matches the hosted record
  [clang] PASS  kernel record length matches its header (187 bytes)
  [clang] PASS  both records decode as cint-core-1/fault/v2
  [clang] PASS  kernel equals hosted: domain
  [clang] PASS  kernel equals hosted: code
  [clang] PASS  kernel equals hosted: operation
  [clang] PASS  kernel equals hosted: operands
  [clang] PASS  kernel equals hosted: exact
  [clang] PASS  kernel equals hosted: limit
  [clang] PASS  kernel equals hosted: srcmap
  [clang] PASS  kernel equals hosted: address_present
  [clang] PASS  kernel equals hosted: position
  [clang] PASS  kernel position is src/overflow.ci:7:23
  [clang] PASS  kernel and hosted stacks both have one entry
  [clang] PASS  kernel stack is the call site src/main_fault.ci:11:22
  [clang] PASS  kernel revision equals cg_revision of its emitted program
  [clang] PASS  hosted revision is present and differs (different program)
PASS  fault clang: record printed, decodes, and matches the hosted record
PASS  repository: this run changed no file in the checkout
elapsed: 232 s (budget 360 s)
PASS  time: whole check in 232 s, under 6 minutes
RESULT: PASS
```
