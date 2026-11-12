/* rt/ctx.c: the context, entries, calls, fuel, frame charges, and the program entry that
 * replaces the hosted main of cint-program.c's runtime (cint_program_run_args). One static
 * context for the kernel's own entry, one more per task (rt/task.c), no allocation. Semantics follow the hosted cint-rt-3. */
#include "rt.h"

struct cint_ctx rt_ctx;

/* Module state (SPEC-03 A-7): one block per module, made from the image at its first access
 * and kept for the life of the context, so a store is not undone by a fault and the blocks
 * survive from one entry of the run loop to the next. The blocks come from a pool of the
 * context's own: the kernel's here, each task's in rt/task.c (K4.5), so no state is shared
 * between contexts and a task that is made anew starts from the image again. */
#ifndef RT_STATE_POOL_BYTES
#define RT_STATE_POOL_BYTES 65536u /* 64 KiB: the 255 KiB bitmap of src/frames.ci, here since M-3, is in pool frames since FB */
#endif
static void *state_blocks[2u * RT_MAX_MODULES];
/* in the image's high window (linker.ld): only the kernel's own tables reach it, never a ring 3 trap path */
static uint8_t state_pool[RT_STATE_POOL_BYTES] __attribute__((aligned(16), section(".high.data")));

/* The program arguments of the run loop: the decimal run number and a NUL, as a hosted
 * `-- N` gives main(in U8[_] args). */
static uint8_t args_buf[24];
static size_t args_len;

static void state_fault(cint_ctx *ctx)
{
    cint_fault_record *rec = rt_record_begin(ctx, rt_placeholder_site(ctx->program), (uint16_t)CINT_E_UNSUPPORTED);
    if (rec != NULL) {
        rt_record_op(rec, "host");
        rt_record_op(rec, "resource");
    }
}

void *cint_rt_state_slow(cint_ctx *ctx, const cint_state *s)
{
    cint_rt_head *h = &ctx->head;
    size_t need;
    void *block;
    if (h->state == NULL || s->module >= h->module_count || s->bytes == 0u) {
        state_fault(ctx);
        return NULL;
    }
    if (h->state[s->module] != NULL) return h->state[s->module];
    need = ((size_t)s->bytes + 15u) & ~(size_t)15u;
    if (need > ctx->pool_bytes - ctx->pool_used) {
        state_fault(ctx);
        return NULL;
    }
    block = ctx->pool + ctx->pool_used;
    ctx->pool_used += need;
    memcpy(block, s->init, s->bytes);
    h->state[s->module] = block;
    h->state[h->module_count + s->module] = (void *)(uintptr_t)s;
    return block;
}

const uint8_t *cint_ctx_args(const cint_ctx *ctx, size_t *length)
{
    const uint8_t *task_args = rt_task_args(ctx, length);
    if (task_args != NULL) return task_args;
    *length = args_len;
    return args_buf;
}

void cint_rt_arg_view(cint_value *v, uint32_t tag, const void *elements, int64_t origin, int64_t extent, int64_t stride,
                      uint32_t perm)
{
    size_t w;
    int64_t span = stride < 0 ? -stride : stride;
    switch (tag) {
    case CINT_TAG_I8: case CINT_TAG_U8: w = 1u; break;
    case CINT_TAG_I16: case CINT_TAG_U16: w = 2u; break;
    case CINT_TAG_I32: case CINT_TAG_U32: w = 4u; break;
    default: w = 8u; break;
    }
    memset(v, 0, sizeof *v);
    v->type.code = (uint16_t)tag;
    v->kind = CINT_VAL_VIEW;
    v->as.view.type.code = (uint16_t)tag;
    v->as.view.rank = 1u;
    v->as.view.perm = (uint8_t)perm;
    v->as.view.mem.kind = CINT_MEM_HOST;
    v->as.view.mem.u.host.ptr = (uint8_t *)(uintptr_t)elements + (ptrdiff_t)origin * (ptrdiff_t)w;
    v->as.view.shape[0] = extent;
    v->as.view.byte_stride[0] = stride * (int64_t)w;
    v->as.view.reachable_bytes = extent > 0 ? (span * (extent - 1) + 1) * (int64_t)w : 0;
}

/* The frame arena is accounting only (cint_mem_frame_*): local arrays live on the C stack,
 * and a charge past the capacity faults E_BOUNDS arena.alloc. */
bool cint_mem_frame_charge(cint_ctx *ctx, cint_site site, int64_t n)
{
    cint_fault_record *rec;
    int64_t used, cap;
    if (cint_rt_faulted(ctx)) return false;
    used = ctx->frame_charged;
    cap = ctx->frame_arena_bytes / 8;
    if (n >= 0 && n <= cap - used) {
        ctx->frame_charged += n;
        return true;
    }
    rec = rt_record_begin(ctx, site, (uint16_t)CINT_E_BOUNDS);
    if (rec != NULL) {
        rt_record_op(rec, "arena.alloc");
        rt_record_operand(rec, CINT_TAG_I64, (uint64_t)n);
        rt_record_operand(rec, CINT_TAG_I64, (uint64_t)used);
        rt_record_operand(rec, CINT_TAG_I64, (uint64_t)cap);
    }
    return false;
}

int64_t cint_mem_frame_mark(const cint_ctx *ctx)
{
    return ctx->frame_charged;
}

void cint_mem_frame_release(cint_ctx *ctx, int64_t mark)
{
    if (mark >= 0 && mark < ctx->frame_charged) ctx->frame_charged = mark;
}

cint_status cint_rt_entry_begin(cint_ctx *ctx, cint_site site, int64_t fuel, int64_t depth)
{
    if (ctx->head.in_entry != 0u) return CINT_BUSY;
    if (ctx->head.faulted != 0u) return CINT_FAULTED;
    if (depth == CINT_DEPTH_FROM_CONFIG) depth = ctx->config_depth;
    if (fuel < CINT_FUEL_UNBOUNDED || depth < 1) return CINT_REFUSED;
    ctx->frame_charged = 0;
    ctx->head.in_entry = 1u;
    ctx->head.fuel_limit = fuel;
    ctx->head.fuel_used = 0;
    ctx->head.depth_limit = depth;
    ctx->head.depth = 1;
    ctx->head.stack_count = 0u;
    if (depth > (int64_t)CINT_RT_MAX_DEPTH) {
        cint_fault_record *rec = rt_record_begin(ctx, site, (uint16_t)CINT_E_UNSUPPORTED);
        if (rec != NULL) {
            rt_record_op(rec, "call.enter");
            rt_record_operand(rec, CINT_TAG_I64, (uint64_t)depth);
            rt_record_limit_i64(rec, (int64_t)CINT_RT_MAX_DEPTH);
        }
        ctx->head.in_entry = 0u;
        return CINT_FAULT;
    }
    if (!cint_fuel_charge(ctx, site, 1u)) {
        ctx->head.in_entry = 0u;
        return CINT_FAULT;
    }
    return CINT_OK;
}

cint_status cint_rt_entry_end(cint_ctx *ctx)
{
    cint_status st = ctx->head.faulted == 0u ? CINT_OK : ctx->head.faulted == 2u ? CINT_RESOURCE : CINT_FAULT;
    ctx->head.in_entry = 0u;
    return st;
}

bool cint_rt_call_enter_slow(cint_ctx *ctx, cint_site site)
{
    if (ctx->head.faulted != 0u) return false;
    if (ctx->head.depth >= ctx->head.depth_limit) {
        cint_fault_record *rec = rt_record_begin(ctx, site, (uint16_t)CINT_E_DEPTH);
        if (rec != NULL) {
            rt_record_op(rec, "call.enter");
            rt_record_limit_i64(rec, ctx->head.depth_limit);
        }
        return false;
    }
    if (!cint_fuel_charge(ctx, site, 1u)) return false;
    ctx->stack[ctx->head.stack_count] = site;
    ctx->head.stack_count++;
    ctx->head.depth++;
    return true;
}

/* The lean call (cint_rt.h 6e, cint OQ-320, from cint-v0.2.12): as the hosted cint-rt-3. A lean check that
 * failed: the head takes the frame's count and depth, so the record is the one cint_rt_call_enter_slow writes
 * for that call. */
void cint_rt_lean_fail(cint_ctx *ctx, cint_site site, int64_t dr, int64_t fu)
{
    int64_t depth = ctx->head.depth;
    ctx->head.fuel_used = fu;
    ctx->head.depth = ctx->head.depth_limit - dr;
    (void)cint_rt_call_enter_slow(ctx, site);
    ctx->head.depth = depth;
}

/* A lean callee failed: the caller's site goes into the record after the heavy frames' sites and before
 * those of the lean frames inside it, where the stack would have held it. */
void cint_rt_lean_unwind(cint_ctx *ctx, cint_site site)
{
    cint_fault_record *rec = &ctx->fault;
    uint32_t at = ctx->head.stack_count, n = rec->stack_count;
    if (ctx->head.faulted != 1u || at > n || n >= CINT_RT_MAX_DEPTH) return;
    memmove(&rec->stack[at + 1u], &rec->stack[at], (size_t)(n - at) * sizeof rec->stack[0]);
    rec->stack[at] = site;
    rec->stack_count = n + 1u;
}

void cint_rt_arg_scalar(cint_value *v, uint32_t tag, uint64_t bits)
{
    memset(v, 0, sizeof *v);
    v->type.code = (uint16_t)tag;
    v->kind = CINT_VAL_SCALAR;
    if (tag == CINT_TAG_BOOL) {
        v->as.i64 = bits != 0u ? 1 : 0;
    } else if (tag >= CINT_TAG_I8 && tag <= CINT_TAG_I64) {
        v->as.i64 = (int64_t)bits;
    } else {
        v->as.u64 = bits;
    }
}

void cint_rt_result_init(cint_value *r, uint32_t tag)
{
    memset(r, 0, sizeof *r);
    r->type.code = (uint16_t)tag;
    r->kind = tag == 0u ? 0u : CINT_VAL_SCALAR;
}

/* One entry. The context is cleared (a fault ends the entry and the record is single-use) but
 * the state blocks stay. */
void rt_ctx_init(struct cint_ctx *ctx, const cint_program *program)
{
    memset(ctx, 0, sizeof *ctx);
    ctx->program = program;
    ctx->config_depth = CINT_DEFAULT_DEPTH;
    ctx->frame_arena_bytes = (int64_t)RT_FRAME_ARENA_ELEMENTS * 8;
    ctx->head.stack = ctx->stack;
    ctx->head.module_count = program->module_count;
    rt_ctx_pool(ctx, state_blocks, state_pool, sizeof state_pool);
}

/* Gives a context its own state table and pool (rt_ctx_init gives it the kernel's). */
void rt_ctx_pool(struct cint_ctx *ctx, void **blocks, uint8_t *pool, size_t pool_bytes)
{
    ctx->head.state = blocks;
    ctx->pool = pool;
    ctx->pool_bytes = pool_bytes;
    ctx->pool_used = 0u;
}

/* One entry of the kernel's context. Its state blocks survive from entry to entry (above), so the
 * pool's fill does too: a module first touched in a later entry takes the bytes after every block
 * an earlier entry made, never one of them. */
static cint_status run_once(const cint_program *program, cint_main_fn main_fn, int64_t fuel)
{
    size_t used = rt_ctx.pool_used;
    rt_ctx_init(&rt_ctx, program);
    rt_ctx.pool_used = used;
    return main_fn(&rt_ctx, fuel);
}

/* Prints the fault record of the context: a header line, then the canonical bytes as hex,
 * streamed (a count pass, then an emit pass) so there is no buffer to overflow. */
void rt_print_fault(const cint_fault_record *rec)
{
    size_t n = rt_fault_encode(rec, NULL, 0u, NULL);
    if (n == 0u) rt_panic("fault record does not encode");
    rt_puts("fault: cint-core-1/fault/v2 ");
    rt_put_dec(n);
    rt_puts(" bytes\n");
    (void)rt_fault_encode(rec, NULL, 0u, rt_put_hex_byte);
    rt_puts("\n");
}

static bool bind(const cint_program *program, const cint_host_desc *imports)
{
    if (program->module_count > RT_MAX_MODULES) rt_panic("more modules than RT_MAX_MODULES");
    return rt_host_bind(program, imports);
}

/* The program entry. The emitted main of cint-program.c calls this with the program's
 * entry function and import table; start.c calls that main. Returns the exit class. */
int cint_program_run_args(const cint_program *program, cint_main_fn main_fn, int64_t fuel, int argc, char **argv,
                          const cint_host_desc *imports, const cint_state_table *state)
{
    cint_status st;
    (void)argc;
    (void)argv;
    (void)state;
    if (!bind(program, imports)) rt_panic("unresolved extern");
    st = run_once(program, main_fn, fuel);
    if (st == CINT_OK) return 0;
    if (st != CINT_FAULT) {
        rt_puts("daphnis: entry status ");
        rt_put_dec((uint64_t)(int64_t)st);
        rt_puts("\n");
        return 2;
    }
    rt_print_fault(&rt_ctx.fault);
    return 1;
}

/* The entry of a program whose main takes `in U8[_] args` (CINT_PROGRAM_ARGS). The kernel
 * runs it as a loop: entry i gets the decimal i and a NUL as its arguments, a fault is
 * printed and the loop goes on with i + 1 (the module state survives), and the loop ends at
 * the first entry that returns normally. This is how one image shows many faults: a fault
 * ends an entry (SPEC-03 A-7), and the hosted twin of entry i is `prog RECORD --arg i`.
 * Every entry has the same finite fuel, so a probe that loops forever ends in a fuel fault. */
#define RT_MAX_RUNS 64
#ifndef RT_RUN_FUEL
#define RT_RUN_FUEL 1000000
#endif
int cint_program_run_argv(const cint_program *program, cint_main_fn main_fn, int64_t fuel, int argc, char **argv,
                          const cint_host_desc *imports, const cint_state_table *state, unsigned flags)
{
    int64_t i;
    (void)argc;
    (void)argv;
    rt_state_register(state);
    if ((flags & CINT_PROGRAM_ARGS) == 0u) return cint_program_run_args(program, main_fn, fuel, argc, argv, imports, state);
    if (fuel == CINT_FUEL_UNBOUNDED) fuel = RT_RUN_FUEL;
    if (!bind(program, imports)) rt_panic("unresolved extern");
    rt_task_setup(program, main_fn);
    for (i = 0; i < RT_MAX_RUNS; i++) {
        cint_status st;
        uint8_t digits[20];
        size_t k = 0u, j;
        uint64_t v = (uint64_t)i;
        do {
            digits[k++] = (uint8_t)('0' + v % 10u);
            v /= 10u;
        } while (v != 0u);
        for (j = 0u; j < k; j++) args_buf[j] = digits[k - 1u - j];
        args_buf[k] = 0u;
        args_len = k + 1u;
        rt_puts("run ");
        rt_put_dec((uint64_t)i);
        rt_puts("\n");
        st = run_once(program, main_fn, fuel);
        if (st == CINT_OK) {
            rt_puts("runs: ");
            rt_put_dec((uint64_t)i);
            rt_puts(" faulted, then one entry returned\n");
            return 0;
        }
        if (st != CINT_FAULT) {
            rt_puts("daphnis: entry status ");
            rt_put_dec((uint64_t)(int64_t)st);
            rt_puts("\n");
            return 2;
        }
        rt_print_fault(&rt_ctx.fault);
    }
    rt_panic("run loop did not end");
    return 2;
}

/* The program's capability manifest (its `requires` lines), registered by the emitted main
 * before the entry runs. The hosted runtime grants the manifest when the embedder gives no
 * grant (RT-OQ-80); the kernel does not: a task's grants are exactly the mask it was created
 * with (rt/task.c), and the manifest is only recorded. */
static const char *program_requires;

void cint_program_requires(const char *lines)
{
    program_requires = lines;
}

const char *rt_program_requires(void)
{
    return program_requires;
}
