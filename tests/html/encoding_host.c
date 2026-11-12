/* Test transport only. All byte decoding runs in emitted CINT. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "host.h"
static FILE *input_file;
static int64_t parameters[7];
static uint32_t points[131080];
static unsigned point_count;
static uint64_t little(unsigned n) {
    uint64_t value = 0;
    for (unsigned i = 0; i < n; i++) {
        int b = fgetc(input_file); assert(b != EOF);
        value |= (uint64_t)(unsigned)b << (8u * i);
    }
    return value;
}
static void put_byte(cint_value view, uint64_t at, uint8_t b) {
    assert(at < (uint64_t)view.as.view.shape[0]);
    uint8_t *p = view.as.view.mem.u.host.ptr;
    p[(int64_t)at * view.as.view.byte_stride[0]] = b;
}
static cint_status next_case(void *u, const cint_value *a, uint32_t n, cint_value *r) {
    (void)u; assert(n == 2);
    if (!input_file) { input_file = fopen(getenv("HTML_ENCODING_INPUT"), "rb"); assert(input_file); }
    int b = fgetc(input_file);
    if (b == EOF) { r->as.i64 = -1; return CINT_OK; }
    assert(ungetc(b, input_file) != EOF);
    uint64_t count = little(4);
    for (unsigned i = 0; i < 7; i++) { parameters[i] = (int64_t)little(4); }
    for (int64_t i = 0; i < parameters[0]; i++) { put_byte(a[1], (uint64_t)i, (uint8_t)little(1)); }
    for (uint64_t i = 0; i < 3 + count * (uint64_t)parameters[6]; i++) { put_byte(a[0], i, 0xa5); }
    for (uint64_t i = 0; i < count; i++) { put_byte(a[0], 3 + i * (uint64_t)parameters[6], (uint8_t)little(1)); }
    point_count = 0;
    r->as.i64 = (int64_t)count;
    return CINT_OK;
}
static cint_status parameter(void *u, const cint_value *a, uint32_t n, cint_value *r) {
    (void)u; assert(n == 1); assert(a[0].as.i64 >= 0 && a[0].as.i64 < 7);
    r->as.i64 = parameters[a[0].as.i64]; return CINT_OK;
}
static cint_status scalar(void *u, const cint_value *a, uint32_t n, cint_value *r) {
    (void)u; (void)r; assert(n == 1); assert(point_count < 131080);
    points[point_count++] = (uint32_t)a[0].as.i64; return CINT_OK;
}
static cint_status report(void *u, const cint_value *a, uint32_t n, cint_value *r) {
    (void)u; (void)r; assert(n == 4);
    printf("%lld %lld %lld %lld", (long long)a[0].as.i64, (long long)a[1].as.i64,
           (long long)a[2].as.i64, (long long)a[3].as.i64);
    for (unsigned i = 0; i < point_count; i++) { printf(" %u", points[i]); }
    putchar('\n'); return CINT_OK;
}
const ci_row ci_rows[] = {
    {"fixture_next", next_case}, {"fixture_parameter", parameter},
    {"fixture_scalar", scalar}, {"fixture_report", report},
};
const uint32_t ci_row_count = sizeof ci_rows / sizeof ci_rows[0];
