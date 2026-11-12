/* Synthetic test host only. No live key provisioning or recording sink. */
#ifndef DAPH_CAPTURE_TESTHOST
#error "capture fixture rows require DAPH_CAPTURE_TESTHOST"
#endif

#include <stddef.h>
#include <stdint.h>
#include <unistd.h>
#include "host.h"
#include "../../rt/capture_crypto.h"
#include "../../vendor/monocypher/monocypher.h"

static int scalar(const cint_value *v, uint16_t type)
{
    return v->kind == CINT_VAL_SCALAR && v->type.code == type && v->is_error == 0u;
}

static int64_t view_size(const cint_value *v, size_t cap, uint8_t perm)
{
    const cint_arg_view *a = &v->as.view;
    uint64_t step, last;
    int64_t n;
    if (v->kind != CINT_VAL_VIEW || v->type.code != CINT_TAG_U8 ||
        a->type.code != CINT_TAG_U8 || a->rank != 1u || a->perm != perm ||
        a->mem.kind != CINT_MEM_HOST) return -1;
    n = a->shape[0];
    if (n < 0 || (uint64_t)n > cap) return -1;
    if (n == 0) return 0;
    if (a->mem.u.host.ptr == NULL) return -1;
    step = a->byte_stride[0] < 0 ? 0u - (uint64_t)a->byte_stride[0] : (uint64_t)a->byte_stride[0];
    if (n > 1 && step > (uint64_t)PTRDIFF_MAX / (uint64_t)(n - 1)) return -1;
    last = (uint64_t)(n - 1) * step;
    if (last >= (uint64_t)INT64_MAX || a->reachable_bytes < (int64_t)(last + 1u)) return -1;
    return n;
}

static void read_view(uint8_t *dst, const cint_value *v, size_t n)
{
    const uint8_t *src = (const uint8_t *)v->as.view.mem.u.host.ptr;
    ptrdiff_t stride = (ptrdiff_t)v->as.view.byte_stride[0];
    size_t i;
    for (i = 0u; i < n; i++) dst[i] = src[(ptrdiff_t)i * stride];
}

static void write_view(const cint_value *v, const uint8_t *src, size_t n)
{
    uint8_t *dst = (uint8_t *)v->as.view.mem.u.host.ptr;
    ptrdiff_t stride = (ptrdiff_t)v->as.view.byte_stride[0];
    size_t i;
    for (i = 0u; i < n; i++) dst[(ptrdiff_t)i * stride] = src[i];
}

static cint_status r_fixture_slot(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    uint8_t key[32], stream[16];
    unsigned i;
    (void)u;
    r->as.i64 = -1;
    if (n != 2u || !scalar(&a[0], CINT_TAG_I64) || !scalar(&a[1], CINT_TAG_I64) ||
        (a[0].as.i64 != 0 && a[0].as.i64 != 1) ||
        (a[1].as.i64 != 0 && a[1].as.i64 != 1)) return CINT_OK;
    /* These fixed bytes are synthetic fixtures, never a provisioning path. */
    for (i = 0u; i < sizeof key; i++) key[i] = (uint8_t)(80u + i);
    for (i = 0u; i < sizeof stream; i++) stream[i] = (uint8_t)i;
    if (a[1].as.i64 == 1) key[0] ^= 1u;
    r->as.i64 = daph_capture_key_open(key, stream, (int)a[0].as.i64);
    crypto_wipe(key, sizeof key);
    return CINT_OK;
}

static cint_status r_capture_match(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    uint8_t stream[16];
    (void)u;
    r->as.i64 = 0;
    if (n != 3u || !scalar(&a[0], CINT_TAG_I64) || !scalar(&a[2], CINT_TAG_I64) ||
        (a[2].as.i64 != 0 && a[2].as.i64 != 1) ||
        view_size(&a[1], sizeof stream, CINT_VIEW_READ) != (int64_t)sizeof stream) return CINT_OK;
    read_view(stream, &a[1], sizeof stream);
    r->as.i64 = daph_capture_key_matches(a[0].as.i64, stream, (int)a[2].as.i64);
    return CINT_OK;
}

static cint_status r_capture_release(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    (void)u; (void)r;
    if (n == 1u && scalar(&a[0], CINT_TAG_I64)) daph_capture_key_close(a[0].as.i64);
    return CINT_OK;
}

static cint_status capture_transform(const cint_value *a, uint32_t n, cint_value *r, int seal)
{
    uint8_t aad[DAPH_CAPTURE_MAX_AAD], input[DAPH_CAPTURE_MAX_PLAIN];
    uint8_t output[DAPH_CAPTURE_MAX_PLAIN], tag[DAPH_CAPTURE_TAG_BYTES];
    int64_t aad_n, text_n;
    const cint_value *out_view;
    r->as.i64 = -1;
    if (n != 6u || !scalar(&a[0], CINT_TAG_I64) || !scalar(&a[1], CINT_TAG_U64)) goto done;
    aad_n = view_size(&a[2], sizeof aad, CINT_VIEW_READ);
    text_n = view_size(&a[3], sizeof input, CINT_VIEW_READ);
    out_view = &a[seal ? 4u : 5u];
    if (aad_n < 0 || text_n < 0 ||
        view_size(out_view, sizeof output, CINT_VIEW_WRITE) != text_n ||
        view_size(&a[seal ? 5u : 4u], sizeof tag, seal ? CINT_VIEW_WRITE : CINT_VIEW_READ) !=
            (int64_t)sizeof tag) goto done;
    read_view(aad, &a[2], (size_t)aad_n);
    read_view(input, &a[3], (size_t)text_n);
    if (seal) {
        r->as.i64 = daph_capture_seal(a[0].as.i64, a[1].as.u64, aad, (size_t)aad_n,
                                     input, (size_t)text_n, output, tag);
    } else {
        read_view(tag, &a[4], sizeof tag);
        r->as.i64 = daph_capture_open(a[0].as.i64, a[1].as.u64, aad, (size_t)aad_n,
                                     input, (size_t)text_n, tag, output);
    }
    if (r->as.i64 == 0) {
        write_view(out_view, output, (size_t)text_n);
        if (seal) write_view(&a[5], tag, sizeof tag);
    }
done:
    crypto_wipe(aad, sizeof aad);
    crypto_wipe(input, sizeof input);
    crypto_wipe(output, sizeof output);
    crypto_wipe(tag, sizeof tag);
    return CINT_OK;
}

static cint_status r_capture_seal(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    (void)u;
    return capture_transform(a, n, r, 1);
}

static cint_status r_capture_open(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    (void)u;
    return capture_transform(a, n, r, 0);
}

static cint_status r_fixture_report(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    uint8_t bytes[4096];
    int64_t size;
    size_t at = 0u;
    (void)u; (void)r;
    if (n != 1u || (size = view_size(&a[0], sizeof bytes, CINT_VIEW_READ)) < 0) return CINT_REFUSED;
    read_view(bytes, &a[0], (size_t)size);
    while (at < (size_t)size) {
        ssize_t wrote = write(1, bytes + at, (size_t)size - at);
        if (wrote <= 0) return CINT_REFUSED;
        at += (size_t)wrote;
    }
    return CINT_OK;
}

const ci_row ci_rows[] = {
    {"fixture_slot", r_fixture_slot},
    {"fixture_report", r_fixture_report},
    {"capture_match", r_capture_match},
    {"capture_release", r_capture_release},
    {"capture_seal", r_capture_seal},
    {"capture_open", r_capture_open}
};
const uint32_t ci_row_count = sizeof ci_rows / sizeof ci_rows[0];
