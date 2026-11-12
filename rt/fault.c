/* rt/fault.c: the fault path. Builds the cint fault record of SPEC-01 9.2 and encodes it
 * as the canonical bytes of IM-149 (`cint-core-1/fault/v2`, the version the hosted
 * cint-rt-3 writes), with the same byte layout as the hosted runtime. Scalar types I8 to
 * U64 only: the emitted C of a program that uses a wider type needs more of the runtime
 * than this file (docs/runtime.md). The exact value of an overflow is computed on a pair
 * of 64-bit limbs, so there is no __int128. */
#include "rt.h"

typedef struct z128 {
    bool negative;
    uint64_t hi, lo;
} z128;

static bool is_scalar_tag(uint32_t tag)
{
    return (tag >= CINT_TAG_I8 && tag <= CINT_TAG_I64) || (tag >= CINT_TAG_U8 && tag <= CINT_TAG_U64);
}

static unsigned tag_width(uint32_t tag)
{
    return 8u << ((tag & 0x0Fu) - 1u);
}

static bool tag_signed(uint32_t tag)
{
    return (tag & 0xF0u) == 0x10u;
}

static const char *type_ident(uint32_t tag)
{
    static const char *const names[8] = {"i8", "i16", "i32", "i64", "u8", "u16", "u32", "u64"};
    return names[(tag >> 4 == 1u ? 0u : 4u) + (tag & 0x0Fu) - 1u];
}

static z128 z_make(bool negative, uint64_t hi, uint64_t lo)
{
    z128 z;
    z.negative = negative && (lo != 0u || hi != 0u);
    z.hi = hi;
    z.lo = lo;
    return z;
}

static z128 z_from_bits(uint32_t tag, uint64_t bits)
{
    if (tag_signed(tag) && (bits >> 63) != 0u) return z_make(true, 0u, (uint64_t)0 - bits);
    return z_make(false, 0u, bits);
}

static z128 z_neg(z128 x)
{
    return z_make(!x.negative, x.hi, x.lo);
}

static int mag_cmp(z128 x, z128 y)
{
    if (x.hi != y.hi) return x.hi < y.hi ? -1 : 1;
    if (x.lo != y.lo) return x.lo < y.lo ? -1 : 1;
    return 0;
}

static z128 z_add(z128 x, z128 y)
{
    uint64_t lo, hi;
    if (x.negative == y.negative) {
        lo = x.lo + y.lo;
        hi = x.hi + y.hi + (lo < x.lo ? 1u : 0u);
        return z_make(x.negative, hi, lo);
    }
    if (mag_cmp(x, y) < 0) {
        z128 t = x;
        x = y;
        y = t;
    }
    lo = x.lo - y.lo;
    hi = x.hi - y.hi - (x.lo < y.lo ? 1u : 0u);
    return z_make(x.negative, hi, lo);
}

static z128 z_mul(z128 x, z128 y)
{
    uint64_t a0 = x.lo & 0xFFFFFFFFu, a1 = x.lo >> 32;
    uint64_t b0 = y.lo & 0xFFFFFFFFu, b1 = y.lo >> 32;
    uint64_t p00 = a0 * b0, p01 = a0 * b1, p10 = a1 * b0, p11 = a1 * b1;
    uint64_t mid = (p00 >> 32) + (p01 & 0xFFFFFFFFu) + (p10 & 0xFFFFFFFFu);
    uint64_t lo = (p00 & 0xFFFFFFFFu) | (mid << 32);
    uint64_t hi = p11 + (p01 >> 32) + (p10 >> 32) + (mid >> 32);
    return z_make(x.negative != y.negative, hi, lo);
}

static z128 z_shl(z128 x, unsigned k)
{
    uint64_t hi = k == 0u ? 0u : x.lo >> (64u - k);
    return z_make(x.negative, hi, x.lo << k);
}

static int z_cmp(z128 x, z128 y)
{
    if (x.negative != y.negative) return x.negative ? -1 : 1;
    return x.negative ? -mag_cmp(x, y) : mag_cmp(x, y);
}

static z128 z_min(uint32_t tag)
{
    unsigned w = tag_width(tag);
    return tag_signed(tag) ? z_make(true, 0u, (uint64_t)1 << (w - 1u)) : z_make(false, 0u, 0u);
}

static z128 z_max(uint32_t tag)
{
    unsigned w = tag_width(tag);
    uint64_t mask = w == 64u ? UINT64_MAX : ((uint64_t)1 << w) - 1u;
    return z_make(false, 0u, tag_signed(tag) ? ((uint64_t)1 << (w - 1u)) - 1u : mask);
}

static uint64_t z_bits(z128 z)
{
    return z.negative ? (uint64_t)0 - z.lo : z.lo;
}

/* Tagged values (SPEC-01 11.1). */

static void tvalue_scalar(cint_tvalue *v, uint32_t tag, uint64_t bits)
{
    unsigned n = tag_width(tag) / 8u;
    unsigned i;
    memset(v, 0, sizeof *v);
    v->bytes[0] = (uint8_t)tag;
    for (i = 0u; i < n; i++) v->bytes[1u + i] = (uint8_t)(bits >> (8u * i));
    v->len = (uint16_t)(1u + n);
}

/* Z: U32 byte count, then minimal little-endian two's complement; zero is count 0. */
static void tvalue_z(cint_tvalue *v, z128 z)
{
    uint8_t b[17];
    unsigned i, n = 17u;
    for (i = 0u; i < 8u; i++) {
        b[i] = (uint8_t)(z.lo >> (8u * i));
        b[8u + i] = (uint8_t)(z.hi >> (8u * i));
    }
    b[16] = 0u;
    if (z.negative) {
        unsigned carry = 1u;
        for (i = 0u; i < 17u; i++) {
            unsigned t = (unsigned)(uint8_t)~b[i] + carry;
            b[i] = (uint8_t)t;
            carry = t >> 8;
        }
    }
    while (n > 0u) {
        uint8_t top = b[n - 1u];
        bool below_negative = n >= 2u && (b[n - 2u] & 0x80u) != 0u;
        if (top == 0x00u && !below_negative) {
            n--;
        } else if (top == 0xFFu && n >= 2u && below_negative) {
            n--;
        } else {
            break;
        }
    }
    memset(v, 0, sizeof *v);
    v->bytes[0] = CINT_TAG_Z;
    v->bytes[1] = (uint8_t)n;
    memcpy(v->bytes + 5, b, n);
    v->len = (uint16_t)(5u + n);
}

/* The record under construction. */

cint_site rt_placeholder_site(const cint_program *program)
{
    cint_site s;
    uint32_t m;
    memset(&s, 0, sizeof s);
    if (program == NULL || program->modules == NULL) return s;
    for (m = program->module_count; m > 0u; m--) { /* the root module comes last */
        const cint_module *mod = program->modules[m - 1u];
        if (mod != NULL && mod->sites != NULL && mod->site_count > 1u) {
            s.module = m - 1u;
            s.index = 1u;
            return s;
        }
    }
    return s;
}

cint_fault_record *rt_record_begin(cint_ctx *ctx, cint_site site, uint16_t code)
{
    cint_fault_record *rec = &ctx->fault;
    if (ctx->head.faulted != 0u) return NULL;
    memset(rec, 0, sizeof *rec);
    rec->program = ctx->program;
    rec->code = code;
    rec->position = site;
    if (ctx->program != NULL && ctx->program->revision != NULL) {
        rec->has_revision = 1u;
        memcpy(rec->revision, ctx->program->revision, sizeof rec->revision);
    }
    rec->stack_count = ctx->head.stack_count;
    memcpy(rec->stack, ctx->stack, (size_t)ctx->head.stack_count * sizeof ctx->stack[0]);
    ctx->head.faulted = 1u;
    return rec;
}

void rt_record_op(cint_fault_record *rec, const char *part)
{
    size_t n = 0u, used = rec->operation_len;
    size_t dot = used > 0u ? 1u : 0u;
    while (part[n] != '\0') n++;
    if (used + dot + n > CINT_FAULT_MAX_OPERATION) {
        rec->operation_len = 0u;
        return;
    }
    if (dot != 0u) rec->operation[used++] = '.';
    memcpy(rec->operation + used, part, n);
    rec->operation_len = (uint8_t)(used + n);
}

void rt_record_operand(cint_fault_record *rec, uint32_t tag, uint64_t bits)
{
    if (rec->operand_count < CINT_FAULT_MAX_OPERANDS) {
        tvalue_scalar(&rec->operands[rec->operand_count], tag, bits);
        rec->operand_count++;
    }
}

static void record_range(cint_fault_record *rec, z128 exact, uint32_t tag)
{
    z128 max = z_max(tag);
    z128 bound = z_cmp(exact, max) > 0 ? max : z_min(tag);
    rec->has_exact = 1u;
    tvalue_z(&rec->exact, exact);
    rec->has_limit = 1u;
    tvalue_scalar(&rec->limit, tag, z_bits(bound));
}

void rt_record_limit_i64(cint_fault_record *rec, int64_t limit)
{
    rec->has_limit = 1u;
    tvalue_scalar(&rec->limit, CINT_TAG_I64, (uint64_t)limit);
}

static cint_fault_record *record_checked(cint_ctx *ctx, cint_site site, uint16_t code, const char *name, uint32_t tag)
{
    cint_fault_record *rec = rt_record_begin(ctx, site, code);
    if (rec != NULL) {
        rt_record_op(rec, name);
        rt_record_op(rec, "checked");
        rt_record_op(rec, type_ident(tag));
    }
    return rec;
}

/* A boundary fault (SPEC-03 A-6, Proposed encoding): E_UNSUPPORTED with operation `op`,
 * and the host status as an I64 operand when has_status. Returns false. */
bool rt_fault_host(cint_ctx *ctx, cint_site site, const char *op, bool has_status, int64_t status)
{
    cint_fault_record *rec = rt_record_begin(ctx, site, (uint16_t)CINT_E_UNSUPPORTED);
    if (rec != NULL) {
        rt_record_op(rec, op);
        if (has_status) rt_record_operand(rec, CINT_TAG_I64, (uint64_t)status);
    }
    return false;
}

static bool fault_refused(cint_ctx *ctx, cint_site site)
{
    return rt_fault_host(ctx, site, "dispatch.admit", false, 0);
}

/* The fault entry points of cint_rt.h that emitted code calls. */

bool cint_rt_fault_arith(cint_ctx *ctx, cint_site site, uint32_t op, uint32_t tag, uint64_t a, uint64_t b)
{
    static const char *const names[7] = {"", "add", "sub", "mul", "neg", "div", "rem"};
    cint_fault_record *rec;
    z128 za, zb, exact;
    bool divides = op == CINT_RT_OP_DIV || op == CINT_RT_OP_REM;
    if (op < CINT_RT_OP_ADD || op > CINT_RT_OP_REM || !is_scalar_tag(tag)) return fault_refused(ctx, site);
    rec = record_checked(ctx, site, (uint16_t)(divides && b == 0u ? CINT_E_DIV_ZERO : CINT_E_OVERFLOW), names[op], tag);
    if (rec == NULL) return false;
    rt_record_operand(rec, tag, a);
    if (op != CINT_RT_OP_NEG) rt_record_operand(rec, tag, b);
    if (rec->code == CINT_E_DIV_ZERO) return false;
    za = z_from_bits(tag, a);
    zb = z_from_bits(tag, b);
    switch (op) {
    case CINT_RT_OP_ADD:
        exact = z_add(za, zb);
        break;
    case CINT_RT_OP_SUB:
        exact = z_add(za, z_neg(zb));
        break;
    case CINT_RT_OP_MUL:
        exact = z_mul(za, zb);
        break;
    default:
        exact = z_neg(za);
        break;
    }
    record_range(rec, exact, tag);
    return false;
}

/* The cold writer of the lean arithmetic forms (cint_rt_lean.h, cint OQ-321, from cint-v0.2.12): x is the
 * wrapped result for add and sub, from which a is recovered at the type's width, and a itself for mul and neg.
 * The record is byte-identical to the full forms'. */
bool cint_rt_fault_arith_cold(cint_ctx *ctx, cint_site site, uint32_t op, uint32_t tag, uint64_t x, uint64_t b)
{
    if ((op == CINT_RT_OP_ADD || op == CINT_RT_OP_SUB) && is_scalar_tag(tag)) {
        unsigned w = cint_rt_tag_width(tag);
        x = op == CINT_RT_OP_ADD ? x - b : x + b;
        x = cint_rt_tag_signed(tag) ? (uint64_t)cint_rt_sext(x, w) : x & cint_rt_mask(w);
    }
    return cint_rt_fault_arith(ctx, site, op, tag, x, b);
}

bool cint_rt_fault_shift(cint_ctx *ctx, cint_site site, uint32_t op, uint32_t tag, uint64_t a, cint_count k)
{
    cint_fault_record *rec;
    unsigned w;
    bool bad_count;
    if (op < CINT_RT_OP_SHL || op > CINT_RT_OP_SHR || !is_scalar_tag(tag) || !is_scalar_tag(k.tag))
        return fault_refused(ctx, site);
    w = tag_width(tag);
    bad_count = k.bits > (uint64_t)(w - 1u);
    rec = rt_record_begin(ctx, site, (uint16_t)(bad_count ? CINT_E_SHIFT : CINT_E_OVERFLOW));
    if (rec == NULL) return false;
    rt_record_op(rec, op == CINT_RT_OP_SHR ? "shr" : "shl");
    rt_record_op(rec, op == CINT_RT_OP_SHL_WRAP ? "wrap" : "checked");
    rt_record_op(rec, type_ident(tag));
    rt_record_operand(rec, tag, a);
    rt_record_operand(rec, k.tag, k.bits);
    if (bad_count) {
        rt_record_limit_i64(rec, (int64_t)(w - 1u));
        return false;
    }
    record_range(rec, z_shl(z_from_bits(tag, a), (unsigned)k.bits), tag);
    return false;
}

bool cint_rt_fault_narrow(cint_ctx *ctx, cint_site site, uint32_t from_tag, uint32_t to_tag, uint64_t x)
{
    cint_fault_record *rec;
    if (!is_scalar_tag(from_tag) || !is_scalar_tag(to_tag)) return fault_refused(ctx, site);
    rec = record_checked(ctx, site, (uint16_t)CINT_E_NARROW, "as", from_tag);
    if (rec == NULL) return false;
    rt_record_op(rec, type_ident(to_tag));
    rt_record_operand(rec, from_tag, x);
    record_range(rec, z_from_bits(from_tag, x), to_tag);
    return false;
}

bool cint_rt_fault_index(cint_ctx *ctx, cint_site site, const char *operation, int64_t index, int64_t extent)
{
    cint_fault_record *rec;
    size_t n = 0u;
    while (operation != NULL && operation[n] != '\0') n++;
    if (n == 0u || n > CINT_FAULT_MAX_OPERATION) return fault_refused(ctx, site);
    rec = rt_record_begin(ctx, site, (uint16_t)CINT_E_BOUNDS);
    if (rec != NULL) {
        rt_record_op(rec, operation);
        rt_record_operand(rec, CINT_TAG_I64, (uint64_t)index);
        rt_record_limit_i64(rec, extent);
    }
    return false;
}

/* One slice item `a[lo..hi]` (cint_rt.h, SPEC-04 LS-161, LS-162): the reference runtime's
 * cint_rt_slice (cint rt/cint_rt.c), ported unchanged in its arithmetic. U1-1 is the first
 * Daphnis program to slice. Out of bounds: E_BOUNDS `operation`, operands [dim when dim >= 0]
 * and the two bounds, limit extent. */
bool cint_rt_slice(cint_ctx *ctx, cint_site site, const char *operation, int64_t dim, int64_t extent,
                   int64_t stride, int64_t lo, int64_t hi, int64_t step, uint32_t flags, int64_t *origin,
                   int64_t *length, int64_t *stride_out)
{
    bool inclusive = (flags & CINT_SLICE_INCLUSIVE) != 0u, valid;
    int64_t first, last, at, s;
    uint64_t k, d;
    if (ctx->head.faulted != 0u) return false;
    if (extent < 0 || step == 0 || flags > 7u || origin == NULL || length == NULL || stride_out == NULL)
        return fault_refused(ctx, site);
    if (step > 0) {
        k = (uint64_t)step;
        first = (flags & CINT_SLICE_LO) != 0u ? lo : 0;
        last = (flags & CINT_SLICE_HI) != 0u ? hi : extent;
        valid = first >= 0 && (inclusive ? last >= first - 1 && last < extent : last >= first && last <= extent);
        d = valid ? (uint64_t)(last - first) + (inclusive ? 1u : 0u) : 0u;
    } else {
        k = (uint64_t)0 - (uint64_t)step;
        first = (flags & CINT_SLICE_LO) != 0u ? lo : extent - 1;
        if (inclusive) {
            last = (flags & CINT_SLICE_HI) != 0u ? hi : 0;
            valid = last >= 0 && first >= last - 1 && first < extent;
            d = valid && first >= last ? (uint64_t)(first - last) + 1u : 0u;
        } else {
            last = (flags & CINT_SLICE_HI) != 0u ? hi : -1;
            valid = last >= -1 && last <= first && first < extent;
            d = valid ? (uint64_t)(first - last) : 0u;
        }
    }
    if (!valid) {
        size_t n = 0u;
        cint_fault_record *rec;
        while (operation != NULL && operation[n] != '\0') n++;
        if (n == 0u || n > CINT_FAULT_MAX_OPERATION) return fault_refused(ctx, site);
        rec = rt_record_begin(ctx, site, (uint16_t)CINT_E_BOUNDS);
        if (rec != NULL) {
            rt_record_op(rec, operation);
            if (dim >= 0) rt_record_operand(rec, CINT_TAG_I64, (uint64_t)dim);
            rt_record_operand(rec, CINT_TAG_I64, (uint64_t)first);
            rt_record_operand(rec, CINT_TAG_I64, (uint64_t)last);
            rt_record_limit_i64(rec, extent);
        }
        return false;
    }
    if (!cint_rt_mul_ovf_i64_p(first, stride, &at) && !cint_rt_add_ovf_i64_p(*origin, at, &at)) *origin = at;
    if (cint_rt_mul_ovf_i64_p(stride, step, &s)) s = (stride < 0) != (step < 0) ? INT64_MIN : INT64_MAX;
    *length = (int64_t)(d / k + (d % k != 0u ? 1u : 0u));
    *stride_out = s;
    return true;
}

bool cint_rt_fault_fuel(cint_ctx *ctx, cint_site site, uint64_t units)
{
    cint_fault_record *rec;
    (void)units;
    rec = rt_record_begin(ctx, site, (uint16_t)CINT_E_FUEL);
    if (rec == NULL) return false;
    rt_record_op(rec, "fuel.charge");
    rt_record_limit_i64(rec, ctx->head.fuel_limit >= 0 ? ctx->head.fuel_limit : INT64_MAX);
    return false;
}

/* Canonical encoding (SPEC-01 11.2). Counts, copies into a buffer (refusing, not overrunning,
 * one too small: rt_fault_encode then returns 0), or streams to a sink, so the fault path of
 * a deep stack needs no buffer: it counts, then streams. */

typedef struct writer {
    uint8_t *buf;
    size_t cap, len;
    void (*sink)(uint8_t);
    bool ok;
} writer;

static void put_bytes(writer *w, const void *p, size_t n)
{
    const uint8_t *src = p;
    size_t i;
    if (w->buf != NULL && w->len + n > w->cap) w->ok = false;
    for (i = 0u; i < n; i++) {
        if (w->buf != NULL && w->ok) w->buf[w->len + i] = src[i];
        if (w->sink != NULL) w->sink(src[i]);
    }
    w->len += n;
}

static void put_le(writer *w, uint64_t v, unsigned n)
{
    uint8_t b[8];
    unsigned i;
    for (i = 0u; i < n; i++) b[i] = (uint8_t)(v >> (8u * i));
    put_bytes(w, b, n);
}

static bool put_position(writer *w, const cint_program *program, cint_site site)
{
    const cint_module *m;
    const cint_site_info *s;
    if (program == NULL || program->modules == NULL || site.module >= program->module_count) return false;
    m = program->modules[site.module];
    if (m == NULL || m->sites == NULL || site.index == 0u || site.index >= m->site_count || m->path_len > CINT_FAULT_MAX_PATH)
        return false;
    s = &m->sites[site.index];
    put_le(w, m->path_len, 4u);
    put_bytes(w, m->path, m->path_len);
    put_le(w, s->line, 4u);
    put_le(w, s->column, 4u);
    return true;
}

size_t rt_fault_encode(const cint_fault_record *r, uint8_t *buf, size_t cap, void (*sink)(uint8_t))
{
    static const char domain[] = "cint-core-1/fault/v2";
    writer w;
    uint32_t i;
    w.buf = buf;
    w.cap = cap;
    w.len = 0u;
    w.sink = sink;
    w.ok = true;
    if (r->code == 0u || r->operation_len == 0u || r->operation_len > CINT_FAULT_MAX_OPERATION ||
        r->operand_count > CINT_FAULT_MAX_OPERANDS || r->stack_count > CINT_RT_MAX_DEPTH || r->has_address != 0u)
        return 0u;
    put_le(&w, sizeof domain - 1u, 4u);
    put_bytes(&w, domain, sizeof domain - 1u);
    put_le(&w, r->code, 2u);
    put_le(&w, r->operation_len, 4u);
    put_bytes(&w, r->operation, r->operation_len);
    put_le(&w, r->operand_count, 4u);
    for (i = 0u; i < r->operand_count; i++) put_bytes(&w, r->operands[i].bytes, r->operands[i].len);
    put_le(&w, r->has_exact ? 1u : 0u, 1u);
    if (r->has_exact) put_bytes(&w, r->exact.bytes, r->exact.len);
    put_le(&w, r->has_limit ? 1u : 0u, 1u);
    if (r->has_limit) put_bytes(&w, r->limit.bytes, r->limit.len);
    if (!put_position(&w, r->program, r->position)) return 0u;
    put_le(&w, r->has_revision ? 1u : 0u, 1u);
    if (r->has_revision) put_bytes(&w, r->revision, 32u);
    put_le(&w, 0u, 1u); /* source-map digest: absent (RT-OQ-28) */
    put_le(&w, 0u, 1u); /* kernel address: absent for scalar code */
    put_le(&w, r->stack_count, 4u);
    for (i = 0u; i < r->stack_count; i++)
        if (!put_position(&w, r->program, r->stack[i])) return 0u;
    return w.ok ? w.len : 0u;
}
