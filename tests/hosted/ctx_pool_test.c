/* tests/hosted/ctx_pool_test.c: the kernel's run loop (rt/ctx.c, cint_program_run_argv), hosted. Module state
 * blocks survive from one entry to the next, so a module first touched in a later entry must take pool bytes
 * after every earlier block, not the start of the pool again. Entries 0 to 2 each touch one new module and fault;
 * entry 3 touches a fourth and returns. Every block must be its own, and hold its module's bytes at the end.
 * The runtime's console, fault and task calls are stubbed; the run loop and the pool are rt/ctx.c's own. */
#include "ctx.c"

#include <stdio.h>
#include <stdlib.h>

enum { MODULES = 4, BYTES = 40 };

static uint8_t init[MODULES][BYTES];
static cint_state states[MODULES];
static void *blocks[MODULES];
static int entries;

cint_fault_record *rt_record_begin(cint_ctx *ctx, cint_site site, uint16_t code)
{
    (void)site;
    (void)code;
    return &ctx->fault;
}
cint_site rt_placeholder_site(const cint_program *program)
{
    cint_site s;
    (void)program;
    memset(&s, 0, sizeof s);
    return s;
}
void rt_record_op(cint_fault_record *rec, const char *op)
{
    (void)rec;
    (void)op;
}
const uint8_t *rt_task_args(const cint_ctx *ctx, size_t *length)
{
    (void)ctx;
    (void)length;
    return NULL;
}
void rt_record_operand(cint_fault_record *rec, uint32_t tag, uint64_t bits)
{
    (void)rec;
    (void)tag;
    (void)bits;
}
void rt_record_limit_i64(cint_fault_record *rec, int64_t limit)
{
    (void)rec;
    (void)limit;
}
bool cint_rt_fault_fuel(cint_ctx *ctx, cint_site site, uint64_t units)
{
    (void)ctx;
    (void)site;
    (void)units;
    return false;
}
void rt_puts(const char *s)
{
    (void)s;
}
void rt_put_dec(uint64_t v)
{
    (void)v;
}
void rt_put_hex_byte(uint8_t b)
{
    (void)b;
}
size_t rt_fault_encode(const cint_fault_record *rec, uint8_t *out, size_t cap, void (*emit)(uint8_t))
{
    (void)rec;
    (void)out;
    (void)cap;
    (void)emit;
    return 1u;
}
void rt_panic(const char *why)
{
    printf("FAIL: panic: %s\n", why);
    exit(1);
}
bool rt_host_bind(const cint_program *program, const cint_host_desc *imports)
{
    (void)program;
    (void)imports;
    return true;
}
void rt_state_register(const cint_state_table *table)
{
    (void)table;
}
void rt_task_setup(const cint_program *program, cint_main_fn main_fn)
{
    (void)program;
    (void)main_fn;
}

static cint_status entry(cint_ctx *ctx, int64_t fuel)
{
    size_t n;
    const uint8_t *a = cint_ctx_args(ctx, &n);
    int i = a[0] - '0';
    (void)fuel;
    entries++;
    blocks[i] = cint_rt_state_slow(ctx, &states[i]);
    if (blocks[i] == NULL) return CINT_FAULT;
    for (int m = 0; m < i; m++) {
        if (cint_rt_state_slow(ctx, &states[m]) != blocks[m]) return CINT_FAULT;
    }
    return i == MODULES - 1 ? CINT_OK : CINT_FAULT;
}

int main(void)
{
    static const cint_program program = {MODULES, 0u, NULL, NULL};
    int bad = 0;
    for (int m = 0; m < MODULES; m++) {
        memset(init[m], 0x11 * (m + 1), BYTES);
        states[m].module = (uint32_t)m;
        states[m].bytes = BYTES;
        states[m].init = init[m];
    }
    int rc = cint_program_run_argv(&program, entry, 1000, 0, NULL, NULL, NULL, CINT_PROGRAM_ARGS);
    if (rc != 0 || entries != MODULES) {
        printf("FAIL: the loop returned %d after %d entries, want 0 after %d\n", rc, entries, MODULES);
        return 1;
    }
    for (int m = 0; m < MODULES; m++) {
        uint8_t *b = blocks[m];
        for (int k = 0; k < m; k++) {
            uint8_t *c = blocks[k];
            if (b < c + 48 && c < b + 48) {
                printf("FAIL: module %d's block overlaps module %d's (entries %d and %d)\n", m, k, m, k);
                bad = 1;
            }
        }
        if (memcmp(b, init[m], BYTES) != 0) {
            printf("FAIL: module %d's block lost its bytes\n", m);
            bad = 1;
        }
    }
    if (rt_ctx.pool_used != (size_t)MODULES * 48u) {
        printf("FAIL: the pool holds %zu bytes, want %d\n", rt_ctx.pool_used, MODULES * 48);
        bad = 1;
    }
    if (bad) return 1;
    printf("4 modules first touched in 4 entries: 4 blocks of 48 bytes, apart, each its own\n");
    return 0;
}
