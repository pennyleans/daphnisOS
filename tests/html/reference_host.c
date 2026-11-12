/* Test transport only. Reference resolution runs in emitted CINT. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "host.h"
static FILE *input_file;
static int64_t case_at;
static uint8_t case_attribute;
static uint64_t little(unsigned n)
{
    uint64_t value = 0;
    for (unsigned i = 0; i < n; i++) {
        int byte = fgetc(input_file);
        assert(byte != EOF);
        value |= (uint64_t)(unsigned)byte << (8u * i);
    }
    return value;
}
static cint_status next_case(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    (void)u; assert(n == 1);
    if (!input_file) { input_file = fopen(getenv("HTML_REFERENCE_INPUT"), "rb"); assert(input_file); }
    int byte = fgetc(input_file);
    if (byte == EOF) { r->as.i64 = -1; return CINT_OK; }
    assert(ungetc(byte, input_file) != EOF);
    uint64_t count = little(4);
    uint64_t at = little(8);
    memcpy(&case_at, &at, sizeof at);
    case_attribute = (uint8_t)little(1);
    assert(count <= (uint64_t)a[0].as.view.shape[0]);
    uint8_t *p = a[0].as.view.mem.u.host.ptr;
    for (uint64_t i = 0; i < count; i++) {
        uint32_t cp = (uint32_t)little(4);
        memcpy(p + (int64_t)i * a[0].as.view.byte_stride[0], &cp, sizeof cp);
    }
    r->as.i64 = (int64_t)count;
    return CINT_OK;
}
static cint_status at_value(void *u, const cint_value *a, uint32_t n, cint_value *r)
{ (void)u; (void)a; assert(n == 0); r->as.i64 = case_at; return CINT_OK; }
static cint_status attribute_value(void *u, const cint_value *a, uint32_t n, cint_value *r)
{ (void)u; (void)a; assert(n == 0); r->as.u64 = case_attribute; return CINT_OK; }
static cint_status report(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    (void)u; (void)r; assert(n == 5);
    printf("%lld %lld %llu %llu %lld\n", (long long)a[0].as.i64,
           (long long)a[1].as.i64, (unsigned long long)a[2].as.u64,
           (unsigned long long)a[3].as.u64, (long long)a[4].as.i64);
    return CINT_OK;
}
const ci_row ci_rows[] = {
    {"fixture_next", next_case}, {"fixture_at", at_value},
    {"fixture_attribute", attribute_value}, {"fixture_report", report},
};
const uint32_t ci_row_count = sizeof ci_rows / sizeof ci_rows[0];
