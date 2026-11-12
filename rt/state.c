/* rt/state.c: the canonical form of a task's module state (K5, docs/snapshot.md).
 *
 * A task's state between steps is its module variables (its stack is empty). The program's
 * state descriptors (cint_state_table, which the emitted main passes to the run loop) say, for
 * each module with variables, each variable's tag, offset and extents. The canonical bytes are
 * the variables of the task modules (modules whose path begins "src/ts_"), in descriptor order,
 * each element little endian at its own width, a block that does not exist yet as its initial
 * image. No offset, padding byte or address is in them, so they are the same on gcc and clang,
 * at any -O, and the same whether or not the task has touched a module yet.
 * Supported: scalars and integer or Bool arrays. Anything else (a struct, a handle) makes the
 * size -1, which the kernel treats as a fault of the build. */
#include "rt.h"

#define STATE_MAX 4096

static const cint_state_table *table;
static uint8_t scratch[STATE_MAX];
static uint8_t stage[STATE_MAX];

void rt_state_register(const cint_state_table *t)
{
    table = t;
}

static unsigned width_of(uint32_t tag)
{
    switch (tag) {
    case CINT_TAG_BOOL: case CINT_TAG_I8: case CINT_TAG_U8: return 1u;
    case CINT_TAG_I16: case CINT_TAG_U16: return 2u;
    case CINT_TAG_I32: case CINT_TAG_U32: return 4u;
    case CINT_TAG_I64: case CINT_TAG_U64: return 8u;
    default: return 0u;
    }
}

static bool included(const cint_program *p, const cint_state *s)
{
    static const char prefix[] = "src/ts_";
    const cint_module *m;
    unsigned i;
    if (s->module >= p->module_count) return false;
    m = p->modules[s->module];
    if (m == NULL || m->path_len < sizeof prefix - 1u) return false;
    for (i = 0u; i < sizeof prefix - 1u; i++)
        if (m->path[i] != prefix[i]) return false;
    return true;
}

/* Encodes the state of ctx into buf, or decodes buf into it. Returns the length, or -1. */
static int64_t walk(struct cint_ctx *ctx, bool decode, uint8_t *buf, size_t cap)
{
    size_t pos = 0u;
    uint32_t i, v, r;
    if (table == NULL || ctx == NULL || ctx->program == NULL) return -1;
    for (i = 0u; i < table->count; i++) {
        const cint_state *s = table->states[i];
        uint8_t *block;
        if (!included(ctx->program, s)) {
            /* a block this context touched outside the task modules is state that no snapshot would carry */
            if (!decode && ctx->head.state[s->module] != NULL) return -1;
            continue;
        }
        block = (uint8_t *)ctx->head.state[s->module];
        if (decode && block == NULL) block = (uint8_t *)cint_rt_state_slow(ctx, s);
        if (decode && block == NULL) return -1;
        for (v = 0u; v < s->var_count; v++) {
            const cint_state_var *var = &s->vars[v];
            unsigned w = width_of(var->tag);
            size_t n = 1u, k;
            if (w == 0u || var->rank > 4u || (var->rank > 0u && var->extents == NULL)) return -1;
            for (r = 0u; r < var->rank; r++) {
                if (var->extents[r] <= 0 || (uint64_t)var->extents[r] > STATE_MAX) return -1;
                n *= (size_t)var->extents[r];
                if (n > STATE_MAX) return -1;
            }
            for (k = 0u; k < n; k++) {
                size_t at = (size_t)var->offset + k * w;
                if (pos + w > cap) return -1;
                if (decode)
                    memcpy(block + at, buf + pos, w);
                else
                    memcpy(buf + pos, (block != NULL ? block : (const uint8_t *)s->init) + at, w);
                pos += w;
            }
        }
    }
    return (int64_t)pos;
}

int64_t rt_state_size(int64_t id)
{
    return walk(rt_task_ctx_of(id), false, scratch, sizeof scratch);
}

/* Up to n bytes of the canonical state of task id from offset off. Returns how many (0 past the end). */
int64_t rt_state_read(int64_t id, int64_t off, uint8_t *dst, int64_t n)
{
    int64_t len = walk(rt_task_ctx_of(id), false, scratch, sizeof scratch);
    if (len < 0 || off < 0 || n < 0) return -1;
    if (off >= len) return 0;
    if (n > len - off) n = len - off;
    memcpy(dst, scratch + off, (size_t)n);
    return n;
}

void rt_state_stage(int64_t off, const uint8_t *src, int64_t n)
{
    if (off < 0 || n < 0 || off > STATE_MAX || n > STATE_MAX - off) return;
    memcpy(stage + off, src, (size_t)n);
}

/* Decodes the staged bytes into task id, whose canonical size must be len. Returns len, or -1. */
int64_t rt_state_apply(int64_t id, int64_t len)
{
    struct cint_ctx *ctx = rt_task_ctx_of(id);
    int64_t want = walk(ctx, false, scratch, sizeof scratch);
    if (want < 0 || want != len) return -1;
    return walk(ctx, true, stage, (size_t)len);
}

uint8_t rt_rev_byte(int64_t i)
{
    const cint_program *p = rt_ctx.program;
    return p != NULL && p->revision != NULL && i >= 0 && i < 32 ? p->revision[i] : 0u;
}
