/* user/ci/main.c: the C main of a cint program in ring 3 (stage R-1, docs/specs/2026-11-05-r-desync.md
 * section 5). The program is emitted by `cint emit-c` as the kernel is and built with the toolchain's
 * hosted runtime (rt/cint_rt.c) and musl, static, so one binary runs on Linux and under Daphnis.
 * The emitted cint-program.c carries its own main, which `cint run` would use; the build renames it
 * (-Dmain=cint_emitted_main) and this one takes its place, because the emitted one supplies no host
 * functions: a program's externs that are not a service's resolve against the table of user/ci/host.c
 * (SPEC-03 A-10), each row's effect class and type signature taken from the import row cintc wrote.
 *
 * Output: a print statement's bytes go to descriptor 1 whole. A fault prints one line on descriptor
 * 2, `fault[E_CODE]: operation at path:line:column`, and the exit status is 1; any other failure of
 * the runtime is status 2 with one line. The exit status of a program that returns is 0.
 * DN-51 frame 23 (the Fault window): in a desk terminal (TERM_PROGRAM=daphnis, AM-3) the line follows the whole
 * record for the desk on the same descriptor, `ESC ] 7770 ; fault ; E_CODE ; operation ; operands ; exact ; limit
 * ; path:line:column BEL`, the operands in decimal joined by `, `, a field empty when the record has none, each
 * value cut to VAL_MAX bytes behind `...`. A terminal draws no OSC, so the screen shows the one line as before. */
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include "cint_rt.h"
#include "host.h"

extern const cint_program cg_program;
extern const cint_host_desc cint_imports_desc;
cint_status CI_RUN(cint_ctx *ctx, int64_t fuel);

static void put(int fd, const void *bytes, size_t len)
{
    const uint8_t *p = (const uint8_t *)bytes;
    while (len > 0u) {
        ssize_t n = write(fd, p, len);
        if (n <= 0) return;
        p += n;
        len -= (size_t)n;
    }
}

static void put_str(int fd, const char *s)
{
    put(fd, s, strlen(s));
}

static void put_u64(int fd, uint64_t v)
{
    char buf[21];
    size_t i = sizeof buf;
    buf[--i] = '\0';
    do {
        buf[--i] = (char)('0' + v % 10u);
        v /= 10u;
    } while (v != 0u);
    put_str(fd, buf + i);
}

static cint_status out_fn(void *user, const uint8_t *bytes, size_t len)
{
    (void)user;
    put(1, bytes, len);
    return CINT_OK;
}

/* The host table: one cint_host_fn per import row that names a function of host.c. */
static cint_host_fn fns[CI_MAX_ROWS];

/* The distinct host rows the imports name (a service's aside), counted whole when they pass CI_MAX_ROWS. */
static uint64_t rows_wanted(void)
{
    uint64_t want = 0u;
    for (uint32_t m = 0u; m < cint_imports_desc.module_count; m++) {
        const cint_host_table *t = cint_imports_desc.tables[m];
        for (uint32_t k = 0u; t != NULL && k < t->count; k++) {
            const cint_host_import *r = &t->imports[k];
            int first = 1;
            if (memchr(r->name.bytes, '/', r->name.len) != NULL) continue;
            for (uint32_t m2 = 0u; m2 <= m && first; m2++) {
                const cint_host_table *t2 = cint_imports_desc.tables[m2];
                uint32_t end = t2 == NULL ? 0u : (m2 == m ? k : t2->count);
                for (uint32_t k2 = 0u; k2 < end; k2++) {
                    const cint_host_import *q = &t2->imports[k2];
                    if (q->name.len != r->name.len) continue;
                    if (memcmp(q->name.bytes, r->name.bytes, r->name.len) == 0) {
                        first = 0;
                        break;
                    }
                }
            }
            if (first) want++;
        }
    }
    return want;
}

static int bind_rows(const char *prog, uint32_t *count)
{
    uint32_t n = 0u;
    for (uint32_t m = 0u; m < cint_imports_desc.module_count; m++) {
        const cint_host_table *t = cint_imports_desc.tables[m];
        for (uint32_t k = 0u; t != NULL && k < t->count; k++) {
            const cint_host_import *r = &t->imports[k];
            const ci_row *row = NULL;
            if (memchr(r->name.bytes, '/', r->name.len) != NULL) continue;   /* a service's: the runtime's */
            for (uint32_t j = 0u; j < ci_row_count; j++) {
                if (strlen(ci_rows[j].name) == r->name.len && memcmp(ci_rows[j].name, r->name.bytes, r->name.len) == 0) {
                    row = &ci_rows[j];
                    break;
                }
            }
            if (row == NULL) {
                put_str(2, "cint: the extern `");
                put(2, r->name.bytes, r->name.len);
                put_str(2, "` has no host function in user/ci/host.c\n");
                return 0;
            }
            {
                uint32_t j = 0u;
                while (j < n && fns[j].name != row->name) j++;
                if (j < n) continue;   /* bound already (another module's row) */
            }
            if (n == CI_MAX_ROWS) {   /* never a silent exit 2: the program, its rows and the cap */
                put_str(2, "cint: ");
                put_str(2, prog);
                put_str(2, " binds ");
                put_u64(2, rows_wanted());
                put_str(2, " host rows, past CI_MAX_ROWS ");
                put_u64(2, (uint64_t)CI_MAX_ROWS);
                put_str(2, " (user/ci/host.h)\n");
                return 0;
            }
            memset(&fns[n], 0, sizeof fns[n]);
            fns[n].name = row->name;
            fns[n].effect = r->effect;
            cint_signature_hash(r->type_signature, (size_t)r->type_signature_len, fns[n].signature);
            fns[n].call = row->call;
            n++;
        }
    }
    *count = n;
    return 1;
}

static const char *const names[] = {"", "E_OVERFLOW", "E_DIV_ZERO", "E_BOUNDS", "E_SHAPE", "E_SHIFT",
                                    "E_NARROW", "E_ALIAS", "E_STALE_HANDLE", "E_FUEL", "E_UNSUPPORTED",
                                    "E_DOMAIN", "E_DEPTH", "E_ASSERT"};

static void put_code(int fd, uint16_t code)
{
    if (code < sizeof names / sizeof names[0]) put_str(fd, names[code]);
    else put_u64(fd, code);
}

#define VAL_MAX 40u   /* the desk's record holds 256 bytes (user/ci/terms.ci OSC_T) */

/* A tagged value's decimal text (SPEC-01 11.1: Bool, Z, an integer of I8 to U64, Q's raw integer) into out, at most
 * VAL_MAX bytes, a longer one cut behind `...`; its length. Little-endian two's complement bytes are divided by 10
 * in place, a digit at a time. */
static size_t val_text(const cint_tvalue *v, char *out)
{
    uint8_t m[CINT_TVALUE_MAX];
    char d[CINT_TVALUE_MAX * 3u];
    size_t n = 0u, at = 1u, len = v->len, k = 0u;
    int neg = 0, sig = 1;
    if (len == 0u) return 0u;
    if (v->bytes[0] == CINT_TAG_BOOL) {
        memcpy(out, v->bytes[1] ? "true" : "false", v->bytes[1] ? 4u : 5u);
        return v->bytes[1] ? 4u : 5u;
    }
    if (v->bytes[0] == CINT_TAG_Z) at = 5u;
    else if (v->bytes[0] == 0x31u) at = 4u;
    else sig = v->bytes[0] < 0x20u;
    if (at >= len) {
        out[0] = '0';
        return 1u;
    }
    n = len - at;
    memcpy(m, v->bytes + at, n);
    if (sig && (m[n - 1u] & 0x80u) != 0u) {   /* negative: its magnitude, two's complement */
        neg = 1;
        for (size_t i = 0u, c = 1u; i < n; i++) {
            c += (uint8_t)~m[i];
            m[i] = (uint8_t)c;
            c >>= 8;
        }
    }
    for (;;) {
        unsigned rem = 0u, any = 0u;
        for (size_t i = n; i-- > 0u;) {
            unsigned cur = rem * 256u + m[i];
            m[i] = (uint8_t)(cur / 10u);
            rem = cur % 10u;
            any |= m[i];
        }
        d[k++] = (char)('0' + rem);
        if (any == 0u) break;
    }
    n = 0u;
    if (neg) out[n++] = '-';
    while (k > 0u && n < VAL_MAX) out[n++] = d[--k];
    if (k > 0u) {
        memcpy(out + VAL_MAX - 3u, "...", 3u);
        n = VAL_MAX;
    }
    return n;
}

static void put_val(const cint_tvalue *v)
{
    char t[VAL_MAX];
    put(2, t, val_text(v, t));
}

/* The record for the desk, as the comment at the top says. */
static void fault_osc(const cint_fault_record *r)
{
    const char *tp = getenv("TERM_PROGRAM");
    cint_position pos;
    if (tp == NULL || strcmp(tp, "daphnis") != 0) return;
    put_str(2, "\x1b]7770;fault;");
    put_code(2, r->code);
    put_str(2, ";");
    put(2, r->operation, r->operation_len);
    put_str(2, ";");
    for (unsigned i = 0u; i < r->operand_count && i < CINT_FAULT_MAX_OPERANDS; i++) {
        if (i > 0u) put_str(2, ", ");
        put_val(&r->operands[i]);
    }
    put_str(2, ";");
    if (r->has_exact) put_val(&r->exact);
    put_str(2, ";");
    if (r->has_limit) put_val(&r->limit);
    put_str(2, ";");
    if (cint_site_resolve(r->program, r->position, &pos)) {
        put(2, pos.path, pos.path_len);
        put_str(2, ":");
        put_u64(2, pos.line);
        put_str(2, ":");
        put_u64(2, pos.column);
    }
    put_str(2, "\a");
}

static void fault_line(const cint_fault_record *r)
{
    cint_position pos;
    fault_osc(r);
    put_str(2, "fault[");
    put_code(2, r->code);
    put_str(2, "]: ");
    put(2, r->operation, r->operation_len);
    if (cint_site_resolve(r->program, r->position, &pos)) {
        put_str(2, " at ");
        put(2, pos.path, pos.path_len);
        put_str(2, ":");
        put_u64(2, pos.line);
        put_str(2, ":");
        put_u64(2, pos.column);
    }
    put_str(2, "\n");
}

/* The program arguments (SPEC-04 LS-221, `main(in U8[_] args)`): argv[1] onward, each followed by one
 * NUL, as cint_ctx_config.args takes them; a main without the parameter never reads them. */
static uint8_t arg_bytes[4096];

int main(int argc, char **argv)
{
    cint_ctx_config cfg;
    size_t arg_len = 0u;
    cint_ctx *ctx = NULL;
    cint_status st;
    uint32_t n = 0u;
    if (!bind_rows(argc > 0 && argv[0] != NULL ? argv[0] : "the program", &n)) return 2;
    for (int i = 1; i < argc; i++) {
        size_t k = strlen(argv[i]) + 1u;
        if (k > sizeof arg_bytes - arg_len) {
            put_str(2, "cint: the arguments exceed 4,096 bytes\n");
            return 2;
        }
        memcpy(arg_bytes + arg_len, argv[i], k);
        arg_len += k;
    }
    memset(&cfg, 0, sizeof cfg);
    cfg.size = (uint32_t)sizeof cfg;
    cfg.program = &cg_program;
    cfg.output = out_fn;
    cfg.imports = &cint_imports_desc;
    cfg.host = n > 0u ? fns : NULL;
    cfg.host_count = n;
    cfg.frame_arena_bytes = CI_FRAME_ARENA_BYTES;
    cfg.args = arg_len > 0u ? arg_bytes : NULL;
    cfg.args_length = arg_len;
    st = cint_ctx_create(&cfg, &ctx);
    if (st != CINT_OK) {
        put_str(2, "cint: no context, status ");
        put_u64(2, (uint64_t)st);
        put_str(2, "\n");
        return 2;
    }
    st = CI_RUN(ctx, CINT_FUEL_UNBOUNDED);
    if (st == CINT_FAULT) {
        cint_fault_record rec;
        if (cint_ctx_fault(ctx, &rec) == CINT_OK && rec.code != 0u) fault_line(&rec);
        cint_ctx_destroy(ctx);
        return 1;
    }
    cint_ctx_destroy(ctx);
    if (st != CINT_OK) {
        put_str(2, "cint: status ");
        put_u64(2, (uint64_t)st);
        put_str(2, "\n");
        return 2;
    }
    return 0;
}
