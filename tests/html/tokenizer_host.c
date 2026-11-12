/* Test transport only. Parsing and token production run in emitted CINT. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include "host.h"
static int64_t mode_value, last_length, cdata_value;
static int64_t selection_count, selection[128][4];
static int64_t integer(void) { int64_t v; assert(fread(&v, sizeof v, 1, stdin) == 1); return v; }
static void view_set(const cint_value *v, int64_t i, uint32_t cp) {
    assert(i >= 0 && i < v->as.view.shape[0]);
    uint8_t *p = v->as.view.mem.u.host.ptr;
    *(uint32_t *)(void *)(p + i * v->as.view.byte_stride[0]) = cp;
}
#define FN(name) static cint_status name(void *u, const cint_value *a, uint32_t n, cint_value *r)
#define UNUSED (void)u; (void)a; (void)n; (void)r
FN(read_row) {
    UNUSED; int64_t length;
    if (fread(&length, sizeof length, 1, stdin) != 1) { r->as.i64 = -1; return CINT_OK; }
    mode_value = integer(); last_length = integer(); cdata_value = integer();
    selection_count = integer(); assert(selection_count >= 0 && selection_count <= 128);
    assert(length >= 0 && length <= a[0].as.view.shape[0]);
    assert(last_length >= 0 && last_length <= a[1].as.view.shape[0]);
    for (int64_t i = 0; i < last_length; i++) view_set(&a[1], i, (uint32_t)integer());
    for (int64_t i = 0; i < length; i++) view_set(&a[0], i, (uint32_t)integer());
    for (int64_t i = 0; i < selection_count; i++)
        for (int64_t j = 0; j < 4; j++) selection[i][j] = integer();
    r->as.i64 = length; return CINT_OK;
}
FN(get_mode) { UNUSED; r->as.i64 = mode_value; return CINT_OK; }
FN(get_last) { UNUSED; r->as.i64 = last_length; return CINT_OK; }
FN(get_cdata) { UNUSED; r->as.i64 = cdata_value; return CINT_OK; }
static int64_t selection_value(int64_t token_index, int column, int64_t fallback) {
    for (int64_t i = 0; i < selection_count; i++)
        if (selection[i][0] == token_index) return selection[i][column];
    return fallback;
}
FN(select_mode_row) { UNUSED; r->as.i64 = selection_value(a[0].as.i64, 1, -999999); return CINT_OK; }
FN(select_cdata_row) { UNUSED; r->as.i64 = selection_value(a[0].as.i64, 2, 0); return CINT_OK; }
FN(select_success_row) { UNUSED; r->as.i64 = selection_value(a[0].as.i64, 3, 0); return CINT_OK; }
FN(put_number) { UNUSED; int64_t v = a[0].as.i64; assert(fwrite(&v, sizeof v, 1, stdout) == 1); return CINT_OK; }
const ci_row ci_rows[] = {
    {"row_read", read_row}, {"row_mode", get_mode}, {"row_last_len", get_last},
    {"row_cdata", get_cdata}, {"number", put_number}, {"row_select_mode", select_mode_row},
    {"row_select_cdata", select_cdata_row}, {"row_select_success", select_success_row}
};
const uint32_t ci_row_count = sizeof ci_rows / sizeof ci_rows[0];
