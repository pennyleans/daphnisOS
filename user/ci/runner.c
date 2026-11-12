/* user/ci/runner.c: the runner of a cint program built inside Daphnis (docs/specs/2026-11-07-bu4-toolchain.md 4.1,
 * unit BU-4b). cint emit-qbe's program file ends with a main that calls cint_program_run_args (cint_program_run_argv
 * for a main that takes arguments) with the program, its run function and the import tables; cib renames those calls
 * to the two below (cint #595). They keep the run function and hand argc and argv to user/ci/main.c, compiled once as
 * ci_daphnis_main with CI_RUN this file's trampoline, which binds the program's extern rows to user/ci/host.c and
 * prints Daphnis's fault line, as the C leg's -Dmain build does. One object for every program: no C compiler runs. */
#include <stdint.h>

#include "cint_rt.h"

int ci_daphnis_main(int argc, char **argv);
cint_status ci_run_trampoline(cint_ctx *ctx, int64_t fuel);
int ci_program_run_args(const cint_program *program, cint_main_fn main_fn, int64_t fuel, int argc, char **argv,
                        const cint_host_desc *imports, const cint_state_table *state);
int ci_program_run_argv(const cint_program *program, cint_main_fn main_fn, int64_t fuel, int argc, char **argv,
                        const cint_host_desc *imports, const cint_state_table *state, uint32_t flags);

static cint_main_fn run_fn;

cint_status ci_run_trampoline(cint_ctx *ctx, int64_t fuel)
{
    return run_fn(ctx, fuel);
}

/* The program, the fuel, the import tables and the state table are main.c's own (cg_program, unbounded fuel,
 * cint_imports_desc), the same objects the program file passes. */
int ci_program_run_args(const cint_program *program, cint_main_fn main_fn, int64_t fuel, int argc, char **argv,
                        const cint_host_desc *imports, const cint_state_table *state)
{
    (void)program;
    (void)fuel;
    (void)imports;
    (void)state;
    run_fn = main_fn;
    return ci_daphnis_main(argc, argv);
}

int ci_program_run_argv(const cint_program *program, cint_main_fn main_fn, int64_t fuel, int argc, char **argv,
                        const cint_host_desc *imports, const cint_state_table *state, uint32_t flags)
{
    (void)flags;
    return ci_program_run_args(program, main_fn, fuel, argc, argv, imports, state);
}
