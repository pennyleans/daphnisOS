# What cint did not give us

Observed with the cint pin of K0 to K5 (a pre-release cint slice, compiler
source identity `18620842d9aa...`); item 17 with `cint-v0.2.12`; the pin in `toolchain.pin` is the public cint v0.2.18 (`a14a03f3`) from 2026-11-10. Earlier pins used v0.2.17 and cint P1. Each item has a reproducer and the way
Daphnis worked around it. These are historical observations against the named
toolchain pins.

## 1. No freestanding program profile (the main one)

`cint emit-c` always writes a hosted `int main(int argc, char **argv)` in `cint-program.c`,
and it calls `cint_program_run_args`, a hosted-runtime function. Emitted modules also call
~15 `cint_rt_*` and `cint_mem_*` functions with no way to ask for fewer or for a profile that
names them. EMIT-31 lists the four `mem*` symbols for a freestanding environment, but nothing
produces or checks a program that links against a runtime other than `rt/cint_rt.c`.

    cd /tmp && printf 'void main() {\n    "hi\\n";\n}\n' > hello.ci
    cint emit-c --root . --out o hello.ci
    grep -n 'int main' -A3 "$(cut -d' ' -f1 o/MANIFEST.ref)"/cint-program.c

Around it: `rt/` implements the used entry points, including `cint_program_run_args`, so the
emitted `main` is the kernel's entry (`docs/runtime.md`). The set to implement was found by
`nm -u` on the compiled output, not from a specification.

## 2. The default helper mode needs `__int128` and libgcc

On gcc and clang, `cint_rt.h` defaults to builtin helpers (`__int128`, and a `__udivti3` call
that EMIT-31 allows). A kernel with no libgcc must define `-DCINT_RT_HELPERS_PORTABLE`. It
works, but nothing says so in the freestanding context, and the hosted tests use the builtin
mode, so a program is tested in one helper mode and run in the other (`docs/runtime.md`).

## 3. Frame-arena charges only when the program recurses, and no bound for `emit-c`

`cint_mem_frame_charge` is emitted only when the program has a call cycle somewhere (then in
every function with local arrays). A program with no call cycle charges nothing: its local
arrays are not charged, however many or large, and `cint emit-c` takes no
`--frame-arena` (`cint run` and `cint build` take it, and it only sets the runtime's arena).
So no compile-time or run-time check relates the arrays of a non-recursive call chain to a
small stack.

    printf 'void main() {\n    U8[4000] a;\n    U8[4000] b;\n    U8[4000] c;\n    a[0] = 1;\n    b[0] = 2;\n    c[0] = 3;\n    "{a[0] + b[0] + c[0]}\\n";\n}\n' > m3.ci
    cint emit-c --root . --out o m3.ci; grep -c cint_mem_frame_charge "$(cut -d' ' -f1 o/MANIFEST.ref)"/m3.c   # 0
    cint emit-c --frame-arena 4096 --root . --out o m3.ci                                   # usage error

Around it: a 128 KiB stack with a guard page, and `docs/runtime.md` says what is and is not
checked. A local array over 4,096 bytes calls `cint_rt_scratch*`, which `rt/` does not
implement, so it fails at link time, a loud failure.

## 4. A hosted `cint test` or `cint run` cannot run a module that imports an extern

The program refuses at start because its host imports do not resolve, and the message names
something else. A module that declares an extern can have no hosted test, even of functions
that never call it.

    printf 'extern observe U8 f(U8 x);\n\ntest "t" {\n    assert(1 == 1);\n}\n' > ext.ci
    cint test --root . ext.ci
    # cint: error: the test program wrote to stderr ... program.stderr says:
    #   usage: a --grant line is malformed or names a directory that cannot be opened, or the
    #   program's host imports do not resolve (SPEC-07 SEC-CAP-6)

Around it: the pure code is in modules with no externs (`src/text.ci`, `src/gate.ci`,
`src/sha256.ci`) and `tests/src_test.ci` imports only those.

## 5. Diagnostics for reserved words

A reserved word used as a variable name gets a diagnostic about something else. `kernel` and
`over` give `C4012 statement form not permitted` at the start of the declaration; `len` and
`count` give `C3001 duplicate name` at the name. (`len` and `count` may be built-in names; the
message does not say so.)

    for w in kernel over len count; do printf 'void main() {\n    I64 %s = 0;\n}\n' $w > kw.ci; cint build --root . --out o kw.ci 2>&1 | head -2; done

Cost here: a directory first named `kernel/` could not be imported (`import kernel.sha256;`
is `C1050 syntax error`), so the source lives in `src/`.

## 6. Smaller

* (Closed at `cint-v0.2.12`: `cint --version` prints the version, the compiler source identity and the runtime contract.)
  `cint --version` is a usage error (`unknown subcommand`, after the usage text). The compiler source identity the task asks for is read
  from the toolchain file: SHA-256 of its `compiler_sources` file. `check.sh` prints it and
  compares it with `toolchain.pin`.
* `cint emit-c --out D` writes the C to `D.stage-N` beside `D` (N rotates between runs), and
  only `D/MANIFEST.ref` names it (`D.stage-N <sha256>`); the header comment of `cli/cint_main.c` describes the output
  set as under `--out`. The Makefile reads `MANIFEST.ref`.
* `cint test` and `cint build` write run directories into the toolchain's own cache unless
  given `--cache`; `emit-c` has no `--cache`, and does not write one. `check.sh` passes
  `--cache` under the build directory (the cint tree is read only here).
* `cint emit-c` takes its modules on the command line. An import that is not listed is
  `C3009 module file unreadable` at the `import`, although `cint build` and `cint run` find the
  file from `--root`:
  `mkdir -p lib; printf 'export I64 f() {\n    return 1;\n}\n' > lib/a.ci; printf 'import lib.a;\n\nvoid main() {\n    _ = a.f();\n}\n' > main.ci; cint emit-c --root . --out o main.ci`
  fails, and the same with `lib/a.ci main.ci` works. The Makefile lists each flavor's modules in
  dependency order.
* There are no if-expressions (`x = if (c) { a } else { b }` is a syntax error). Not a defect,
  only a cost: `src/text.ci` writes a four-line statement where C has `?:`.

## 7. An error union returned across modules is refused (K3)

A function that returns an error union cannot be called from another module: cintc stops with
`C9102` at the call, with no message naming a limit. `CINTC-OQ-68` describes imported error sets
and imported service externs, which work (the `console` module's `ConsoleError` unions are
caught in `src/main_tasks.ci`); a user module's own union is refused, with `catch` and `try`
alike.

    mkdir -p lib && printf 'export error E { bad }\n\nexport E!I64 f(I64 n) {\n    if (n < 0) {\n        return E.bad;\n    }\n    return n;\n}\n' > lib/a.ci
    printf 'import lib.a;\n\nvoid main() {\n    I64 x = a.f(3) catch -1;\n    "{x}\\n";\n}\n' > main.ci
    cint emit-c --root . --out o lib/a.ci main.ci      # error[C9102] at 4:15

Around it: `src/frames.ci`, `src/heap.ci` and `src/paging.ci` return a value `>= 0` or a negative
status constant (`ERR_*`), and their callers compare. The unions that remain are inside a module
(none are used) and the `console` service's.

## 8. A `Grants` value cannot be passed to another module's function (K4)

`main(Grants g)` may call a service extern with `g`, and may pass `g` to a function of its own
module. Passing it to a function of another module is `C9102`, even when that function only
returns a number.

    mkdir -p lib && printf 'export I64 take(Grants g, I64 x) {\n    return x + 1;\n}\n' > lib/e.ci
    printf 'import lib.e;\n\nvoid main(Grants g) {\n    _ = e.take(g, 1);\n}\n' > e.ci
    cint emit-c --root . --out o lib/e.ci e.ci         # error[C9102] at 4:11

Cost here: the code that calls the console service is in the root module (`src/main_tasks.ci`),
so the hosted twin (`tests/task_twin.ci`) cannot import it and carries a copy; `check.sh`
compares the two copies between their `BEGIN` and `END` markers.

## 9. `console.write` has no capability, so it cannot be gated (K4)

The task asks for the console write service behind a grant. At the pin the standard `console`
module publishes `write` under no capability (OQ-299, decided 2026-10-22: the sandbox's console
output needs none), so no grant can deny it, and `requires console.write` is `C3041`. The
service that a grant does cover is `console.input` (`read`, `read_line`, `window`) and
`console.raw`. K4 therefore gates `console.read_line` behind `console.input`, answers `write`
for every task, and shows `denied` on the read.

    printf 'import console;\nrequires console.write;\n\nvoid main(Grants g) {\n}\n' > w.ci
    cint emit-c --root . --out o w.ci                  # error[C3041] at 2:10

## 10. More built-in names

`sum` is a built-in name: `I64 sum = 0;` is `C3001 duplicate name` (like `len`, `count`,
`kernel`, `over`, section 5). `read` and `round` are not.

    printf 'void main() {\n    I64 sum = 0;\n}\n' > n.ci
    cint emit-c --root . --out o n.ci                  # error[C3001] at 2:9

K5 found two more, with diagnostics that do not name the problem: `schedule` as a
function name is `C4012 statement form not permitted` at the declaration, and `out` as a parameter name is
`C1050 syntax error`. Names found by trial so far: `kernel`, `over`, `len`, `count`, `sum`, `fill`, `schedule`, `out`.

    printf 'I64 schedule() {\n    return 1;\n}\n\nvoid main() {\n    _ = schedule();\n}\n' > a.ci
    printf 'void f(inout U8[4] out) {\n    out[0] = 1;\n}\n\nvoid main() {\n    U8[4] b;\n    f(b);\n}\n' > b.ci
    cint run --root . a.ci                             # error[C4012] at 1:1
    cint run --root . b.ci                             # error[C1050] at 1:20

## 11. No way to give a hosted run a fuel allowance

`cint run` and a built program take no fuel option (the generated `main` passes
`CINT_FUEL_UNBOUNDED`), and `cint test` runs at 1,000,000,000. So the fuel fault of the kernel
(allowance 1,000,000) cannot be reproduced byte for byte by a hosted run; `check.sh` compares the
fields of the hosted text rendering (`tests/fuel_twin.ci`) and everything but the limit value.

## 12. No way to run a hosted program with an empty grant set (K4)

With no `--grant` the hosted runtime grants the whole `requires` manifest (RT-OQ-80), one `--grant`
turns derivation off and the lines given are the whole set, and an empty line is refused (exit 4).
A test of the denied path that wants "no grant at all" has no spelling; the kernel's twin gives the
task that must be denied a grant that does not cover the call (`--grant console.raw`, with
`console.input` the capability under test).

    mkdir -p t && cd t
    printf 'import console;\nrequires console.input;\nrequires console.raw;\n\nI64 probe_raw(Grants g) {\n    console.raw(g, false) catch (e) { return e == console.ConsoleError.denied ? -1 : -2; };\n    return 0;\n}\n\nvoid main(Grants g) {\n    I64 r = probe_raw(g);\n    "{r}\\n";\n}\n' > r.ci
    cint build --root . --out o r.ci
    ./o/r rec < /dev/null                         # 0: no --grant grants the manifest
    ./o/r rec --grant console.input < /dev/null   # -1: a grant that does not cover the call
    ./o/r rec --grant "" < /dev/null; echo $?     # exit 4: refused

## 13. No resumable fuel point (K4.5)

A scheduler that wants a task's turn to end at an exact fuel count cannot use `cint_rt_fault_fuel`
for it: a function with no calls keeps its fuel in locals (EMIT-28) and its charge is
`(void)cint_fuel_charge(...); goto fault;`, so a runtime that switches tasks inside the slow path and
returns true has the result dropped, and the task ends as done with half its output and no record.

    printf 'I64 spin(I64 n) {\n    I64 s = 0;\n    for i in 0..n {\n        s += i;\n    }\n    return s;\n}\n\nvoid main() {\n    _ = spin(10);\n}\n' > leaf.ci
    cint emit-c --root . --out o leaf.ci
    grep -n 'fcap' "$(cut -d' ' -f1 o/MANIFEST.ref)"/leaf.c

Workaround used: the turn ends at a host call (`docs/shepherd.md`), where the count is exact.
## 14. Frame-arena charges depend on where the callee is (K4.5)

In a program with no call cycle, local arrays are charged to the frame arena only when a call
crosses a module boundary: two functions with a `U8[4000]` each, in one module, have no charge;
with the array passed to a function of another module, two. So the stack a freestanding runtime
must provide depends on how a program is split into modules (`docs/runtime.md`, stack budget).
## 15. A string literal cannot be indexed, and there is no array literal (K5)

`"DAPH"[i]` is `C9102`. A string literal is a `U8[n]` view when it is passed (`serial_write("abc")`), so
indexing it is what a reader expects; with no array literal either, the eight bytes of a magic number are
eight stores into a local array (`kern.ci`, `magic`). Filed: #513.

    printf 'I64 f(I64 i) {\n    U8 c = "DAPH"[i];\n    return c as I64;\n}\n\nvoid main() {\n    _ = f(1);\n}\n' > idx.ci
    cint run --root . idx.ci                           # error[C9102] at 2:12

## 16. What K5 needed from the fuel hook (item 13), and what it did not

K5 **did not need** a resumable fuel point. Its tasks are step functions: a turn ends at a step boundary, where
the count of fuel is exact because the entry has ended, so the quantum of K5 is at step granularity and the
journal's fuel stamps are totals over whole steps (`docs/snapshot.md`, section 1). K4.5's mid-host-call
quantum is not used.

K5 **would use** it for one thing: a step that computes for a long time cannot be ended at a given fuel count, so
it delays the other tasks by as much as it runs. That affects latency only, never a root, because tasks share
nothing and what the schedule can change is journaled. Fuel itself is per entry (`cint_rt_entry_begin` zeroes
`fuel_used`), so a runtime that runs a task in steps adds the entries up (`rt/task.c`, `fuel_total`).

## 17. The embedder's entry points grew under the same contract name (re-pin to cint-v0.2.12)

A freestanding embedder supplies the runtime functions emitted C calls. From the old pin to `cint-v0.2.12` that set
grew by `cint_rt_lean_fail` and `cint_rt_lean_unwind` (emitted) and `cint_rt_fault_arith_cold` (declared), while
`cint --version` still says `runtime contract cint-rt-3`. The only notice was a link failure in 6 of 22 images.
Asks: a machine-readable list of the entry points each runtime contract requires, shipped with the toolchain, and a
new contract name (or a minor number) when the list grows. Workaround: `rt/` copies the hosted bodies
(`docs/RESULTS-BOOT.md`).

## 18. An entry point a program needs only once it uses a construct (U1-1)

This is another case of the issue in item 17. `cint_rt_slice` is in `cint_rt.h` at the pin but emitted only when a
program slices an array (`a[lo..hi]`); U1-1 is the first Daphnis program that does, and its first link failed on it.
A list of the contract's entry points would have shown it before any program used it. Workaround:
`rt/fault.c` ports the reference body from cint `rt/cint_rt.c` unchanged in its arithmetic.

## 19. A constant array is refused (AU-7)

`const I64[4] T = [1, 2, 3, 4];` is `C9102` at the literal, though SPEC-04 LS-111 shows the form. A module-level
array with a constant initializer is accepted (LS-113, OQ-233), so the OPL3's tables (`user/ci/opl/opl3.ci`) are
module arrays: writable by their module, which only reads them.

    printf 'const I64[2] T = [1, 2];\n\nvoid main() {\n    "{T[0]}\\n";\n}\n' > ca.ci
    cint run --root . ca.ci                            # error[C9102] at 1:18

## 20. `emit-qbe` names no runner (BU-4)

The QBE program file's `$main` calls `cint_program_run_args` (or `_argv`) with the program, the root module's run
function and the import tables (`compiler/back_qbe.ci` `write_program`); Daphnis's own `main` (`user/ci/main.c`) has
no C compiler on this path to rename the emitted `main` with.

    cint emit-qbe --toolchain cpu-qbe.toolchain --root . --out e src/sha256.ci user/ci/msha.ci
    grep -n 'cint_program_run_arg' e.stage-0/cint-program.ssa

Around it: `cib` rewrites the two callees to `ci_program_run_args` and `ci_program_run_argv`, which a pinned shim
defines (`docs/specs/2026-11-07-bu4-toolchain.md` 4.1).

## 21. cint-as reads at most 4 MiB (BU-4)

QBE's output for four of the compiler's modules is 5.4 to 10.6 MB (`back_c.s` 10,600,428 B), so cint-as cannot
assemble cint itself:

    cint run --frame-arena 67108864 toolchain/as/main.ci -- back_c.s back_c.o   # status 6, "over 4194304 bytes"

Around it: none needed for BU-4's gate; cint's own rebuild inside Daphnis waits (BU4-3).

## 22. cint ld: 16 MiB of input, 8 MiB of output, 32 inputs (BU-4)

cint's own link is 17 MB of compiler objects before `libc.a`, and its executable is 8.7 MB:

    ld --frame-arena 67108864 -- cint crt1.o crti.o ... libc.a crtn.o   # "limit: the inputs are larger than 16 MiB"

Around it: none needed for BU-4's gate. Daphnis links through one archive (`libci.a`), so a program may have 27
modules.

## 23. The compiler source identity is a CLI macro (BU-4)

`-DCINT_COMPILER_SOURCE_IDENTITY` is compiled into the CLI objects (`tools/cint_bootstrap.py`) and `ready()` compares it
with the digest of the toolchain's `compiler_sources` (`cli/cint_main.c`). With no C compiler in Daphnis the CLI is a
pinned object, so a `cint` rebuilt there from edited compiler sources fails `ready()`:

    cint --version     # "compiler source identity <the pinned CLI's>", whatever compiler it was linked with

Around it: none for the self-rebuild gate (BU-4h2 rebuilds the pinned sources, so the identity matches); a developer
who edits the compiler inside Daphnis waits for the issue.

## Feature requests

* **The view shim**: a construct for host-owned memory that cintc can emit
  and bound-check, in place of the copy window of `docs/memory.md`.
* **A fuel allowance for hosted runs** and **an empty grant set**, above.
* **A freestanding profile with one named group per feature**: base,
  module variables, `main` arguments, views to externs, `requires`, services.
* **A ruling on denying console output**.
* **A resumable fuel point or quantum hook for task schedulers**: the K4.5 quantum ends turns at
  host calls only, the K5 quantum at step boundaries; see item 16 for what K5 needed.
* **Indexing a string literal, an array literal**, item 15.
* **A freestanding `cint_state`**: the canonical state, its hash, checkpoint and restore exist in `rt/cint_state.c` but
  need libc; K5 wrote its own walker (`rt/state.c`) and format (`docs/snapshot.md`).
* **Fuel across entries**: promise that the count of an entry is deterministic, and carry a total; K5 sums entries
  itself and stamps its journal with the sum.
* **The fault record of a hardware trap during a host call**: K3 to K5 use `host.error.trap_<name>` with the vector,
  error code, CR2 and IST as operands; nothing in the spec names it.
* The frame arena counts elements while the local array limit is in bytes: one `U8[4096]` takes the whole arena.
