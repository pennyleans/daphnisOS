#!/usr/bin/env python3
"""Test the current kernel journal wrappers with a synthetic native adapter."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

HARNESS = r'''
#include <assert.h>
#include <limits.h>
#include <stdio.h>
#include <string.h>

static unsigned record_calls, read_calls, size_calls;
static int64_t seen_kind, seen_offset, read_result = -2;
static size_t seen_size;
static uint8_t recorded[4096];

void rt_journal_record(int64_t kind, const uint8_t *bytes, size_t n)
{
    assert(kind == 1 || kind == 2);
    assert(n <= sizeof recorded);
    record_calls++;
    seen_kind = kind;
    seen_size = n;
    if (n != 0u) memcpy(recorded, bytes, n);
}

int64_t rt_journal_size(int64_t kind)
{
    size_calls++;
    seen_kind = kind;
    return kind == 1 ? 17 : kind == 2 ? 29 : -1;
}

int64_t rt_journal_read(int64_t kind, int64_t offset, uint8_t *bytes, size_t n)
{
    assert(kind == 1 || kind == 2);
    assert(offset >= 0 && n <= sizeof recorded);
    read_calls++;
    seen_kind = kind;
    seen_offset = offset;
    seen_size = n;
    /* The entire temporary is dirtied even when reporting failure or a short read. */
    for (size_t i = 0u; i < n; i++) bytes[i] = (uint8_t)(5u + i % 251u);
    return read_result == -2 ? (int64_t)n : read_result;
}

static cint_value scalar(int64_t value)
{
    cint_value v;
    memset(&v, 0, sizeof v);
    v.kind = CINT_VAL_SCALAR;
    v.type.code = CINT_TAG_I64;
    v.as.i64 = value;
    return v;
}

static cint_value view(uint8_t *p, int64_t n, int64_t stride, int64_t reachable, uint8_t perm)
{
    cint_value v;
    memset(&v, 0, sizeof v);
    v.kind = CINT_VAL_VIEW;
    v.type.code = CINT_TAG_U8;
    v.as.view.type.code = CINT_TAG_U8;
    v.as.view.rank = 1u;
    v.as.view.perm = perm;
    v.as.view.mem.kind = CINT_MEM_HOST;
    v.as.view.mem.u.host.ptr = p;
    v.as.view.shape[0] = n;
    v.as.view.byte_stride[0] = stride;
    v.as.view.reachable_bytes = reachable;
    return v;
}

static void task_boundary(void)
{
    assert(task_allowed("console/1.raw"));
    assert(task_allowed("emit"));
    assert(!task_allowed("journal_record"));
    assert(!task_allowed("journal_size"));
    assert(!task_allowed("journal_read"));
    assert(!task_allowed("console/1.rawjournal_record"));
    assert(!task_allowed("journal_record/1.raw"));
}

#ifdef RT_CAPTURE
static void transfer(int64_t n, int64_t stride)
{
    uint8_t input[8208], output[8208], expected[8208];
    int64_t span = n > 0 ? (n - 1) * (stride < 0 ? -stride : stride) : 0;
    int64_t base = stride < 0 ? 8 + span : 8;
    for (size_t i = 0u; i < sizeof input; i++) input[i] = (uint8_t)(i % 251u);
    cint_value a[3] = {scalar(1), view(input + base, n, stride, span + 1, CINT_VIEW_READ), scalar(0)};
    cint_value result = scalar(777);
    unsigned before = record_calls;
    assert(hf_journal_record(a, &result) == CINT_OK);
    assert(record_calls == before + 1u && seen_kind == 1 && seen_size == (size_t)n);
    assert(result.as.i64 == 777);
    for (int64_t i = 0; i < n; i++) assert(recorded[i] == input[base + i * stride]);
    if (n > 0) {
        uint8_t first = recorded[0];
        input[base] ^= 255u;
        assert(recorded[0] == first);
    }
    memset(output, 0xA5, sizeof output);
    memcpy(expected, output, sizeof output);
    for (int64_t i = 0; i < n; i++) expected[base + i * stride] = (uint8_t)(5 + i % 251);
    a[0] = scalar(2);
    a[1] = scalar(7);
    a[2] = view(output + base, n, stride, span + 1, CINT_VIEW_WRITE);
    before = read_calls;
    read_result = -2;
    assert(hf_journal_read(a, &result) == CINT_OK);
    assert(read_calls == before + 1u && seen_kind == 2 && seen_offset == 7 && seen_size == (size_t)n);
    assert(result.as.i64 == n);
    assert(memcmp(output, expected, sizeof output) == 0);
}

static void refuse_view(cint_value v)
{
    cint_value a[3] = {scalar(1), v, v}, result = scalar(777);
    unsigned before = record_calls;
    assert(!journal_view(&v.as.view));
    assert(hf_journal_record(a, &result) == CINT_REFUSED);
    assert(record_calls == before && result.as.i64 == 777);
    a[1] = scalar(0);
    before = read_calls;
    assert(hf_journal_read(a, &result) == CINT_REFUSED);
    assert(read_calls == before && result.as.i64 == 777);
}

static void extent_guards(void)
{
    uint8_t bytes[8];
    cint_value v = view(bytes, 1, 1, 1, CINT_VIEW_WRITE);
    refuse_view(view(bytes, -1, 1, 8, CINT_VIEW_WRITE));
    refuse_view(view(bytes, 4097, 0, 1, CINT_VIEW_WRITE));
    refuse_view(view(bytes, 1, INT64_MIN, 1, CINT_VIEW_WRITE));
    refuse_view(view(NULL, 0, INT64_MIN, 0, CINT_VIEW_WRITE));
    refuse_view(view(NULL, 1, 1, 1, CINT_VIEW_WRITE));
    refuse_view(view(bytes, 1, 1, 0, CINT_VIEW_WRITE));
    refuse_view(view(bytes, 1, 1, -1, CINT_VIEW_WRITE));
    refuse_view(view(bytes, 3, 2, 4, CINT_VIEW_WRITE));
    refuse_view(view(bytes, 3, -2, 4, CINT_VIEW_WRITE));
    refuse_view(view(bytes, 4096, INT64_MAX, INT64_MAX, CINT_VIEW_WRITE));
    refuse_view(view(bytes, 4096, -INT64_MAX, INT64_MAX, CINT_VIEW_WRITE));
    refuse_view(view((uint8_t *)(uintptr_t)UINTPTR_MAX, 2, 1, 2, CINT_VIEW_WRITE));
    refuse_view(view((uint8_t *)(uintptr_t)1, 3, -1, 3, CINT_VIEW_WRITE));
    v.as.view.mem.kind = (uint8_t)(CINT_MEM_HOST + 1u);
    refuse_view(v);
    v = view((uint8_t *)(uintptr_t)(UINTPTR_MAX - 1u), 2, 1, 2, CINT_VIEW_WRITE);
    assert(journal_view(&v.as.view));
    v = view((uint8_t *)(uintptr_t)1, 2, -1, 2, CINT_VIEW_WRITE);
    assert(journal_view(&v.as.view));
    v = view(bytes, 1, INT64_MAX, 1, CINT_VIEW_WRITE);
    assert(journal_view(&v.as.view));
    v = view(NULL, 0, 0, 0, CINT_VIEW_WRITE);
    assert(journal_view(&v.as.view));
    cint_value a[3] = {scalar(1), v, v}, result = scalar(777);
    assert(hf_journal_record(a, NULL) == CINT_OK && seen_size == 0u);
    a[1] = scalar(0);
    read_result = -2;
    assert(hf_journal_read(a, &result) == CINT_OK && result.as.i64 == 0);
}

static void failures_and_short_reads(void)
{
    uint8_t output[40], expected[40];
    cint_value a[3] = {scalar(1), scalar(9), view(output + 12, 5, -2, 9, CINT_VIEW_WRITE)};
    cint_value result = scalar(777);
    memset(output, 0xA5, sizeof output);
    memcpy(expected, output, sizeof output);
    for (unsigned i = 0u; i < 2u; i++) {
        read_result = i == 0u ? -1 : 6;
        assert(hf_journal_read(a, &result) == CINT_REFUSED);
        assert(result.as.i64 == 777 && memcmp(output, expected, sizeof output) == 0);
    }
    read_result = 3;
    assert(hf_journal_read(a, &result) == CINT_OK && result.as.i64 == 3);
    expected[12] = 5; expected[10] = 6; expected[8] = 7;
    assert(memcmp(output, expected, sizeof output) == 0);
    memset(output, 0xA5, sizeof output);
    memset(expected, 0xA5, sizeof expected);
    read_result = 0;
    assert(hf_journal_read(a, &result) == CINT_OK && result.as.i64 == 0);
    assert(memcmp(output, expected, sizeof output) == 0);
    const int64_t bad_kind[] = {INT64_MIN, -1, 0, 3, INT64_MAX};
    for (unsigned i = 0u; i < sizeof bad_kind / sizeof bad_kind[0]; i++) {
        a[0] = scalar(bad_kind[i]);
        result = scalar(777);
        unsigned before = read_calls;
        assert(hf_journal_read(a, &result) == CINT_REFUSED && read_calls == before);
        assert(result.as.i64 == 777 && memcmp(output, expected, sizeof output) == 0);
        cint_value rec[2] = {a[0], a[2]};
        before = record_calls;
        assert(hf_journal_record(rec, &result) == CINT_REFUSED && record_calls == before);
        assert(hf_journal_size(a, &result) == CINT_OK && result.as.i64 == -1);
    }
    a[0] = scalar(1);
    for (unsigned i = 0u; i < 2u; i++) {
        a[1] = scalar(i == 0u ? -1 : INT64_MIN);
        result = scalar(777);
        unsigned before = read_calls;
        assert(hf_journal_read(a, &result) == CINT_REFUSED && read_calls == before);
        assert(result.as.i64 == 777 && memcmp(output, expected, sizeof output) == 0);
    }
    a[1] = scalar(INT64_MAX);
    read_result = -1;
    assert(hf_journal_read(a, &result) == CINT_REFUSED);
    assert(seen_offset == INT64_MAX && memcmp(output, expected, sizeof output) == 0);
    a[0] = scalar(1);
    assert(hf_journal_size(a, &result) == CINT_OK && result.as.i64 == 17);
    a[0] = scalar(2);
    assert(hf_journal_size(a, &result) == CINT_OK && result.as.i64 == 29);
    assert(size_calls >= 7u);
}
#else
static void disabled_capture(void)
{
    uint8_t output[8], expected[8];
    memset(output, 0xA5, sizeof output);
    memcpy(expected, output, sizeof output);
    cint_value a[3] = {scalar(0), scalar(-1), view(output, 4097, INT64_MIN, -1, CINT_VIEW_WRITE)};
    cint_value result = scalar(777);
    assert(hf_journal_record(a, &result) == CINT_OK && result.as.i64 == 777);
    assert(hf_journal_size(a, &result) == CINT_OK && result.as.i64 == -1);
    result = scalar(777);
    assert(hf_journal_read(a, &result) == CINT_OK && result.as.i64 == -1);
    assert(memcmp(output, expected, sizeof output) == 0);
    assert(record_calls == 0u && read_calls == 0u && size_calls == 0u);
}
#endif

int main(void)
{
    (void)seen_kind;   /* read only by the capture=1 asserts: clang 23's -Wunused-but-set-global otherwise */
    (void)seen_offset;
    (void)seen_size;
    task_boundary();
#ifdef RT_CAPTURE
    transfer(0, 0);
    transfer(1, 0);
    transfer(4, 2);
    transfer(4, -2);
    transfer(4, 0);
    transfer(4096, 1);
    transfer(4096, 2);
    transfer(4096, -2);
    transfer(4096, 0);
    extent_guards();
    failures_and_short_reads();
    puts("capture=1: journal views, atomic reads, task restriction pass");
#else
    disabled_capture();
    puts("capture=0: inert journal wrappers and task restriction pass");
#endif
    return 0;
}
'''


def run(command):
    result = subprocess.run([str(x) for x in command], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    if result.stderr:
        raise RuntimeError('unexpected stderr: ' + result.stderr)
    return result.stdout


def extract(source, start, end):
    assert source.count(start) == 1, 'source boundary changed: ' + start
    begin = source.index(start)
    finish = source.index(end, begin)
    return source[begin:finish]


def main():
    if not __debug__:
        raise RuntimeError('checks require assertions enabled')
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--toolchain', type=Path, required=True)
    parser.add_argument('--host-source', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    host = (args.host_source or root / 'rt/host.c').resolve()
    out = args.out.resolve()
    assert root != out and root not in out.parents, 'outputs must be outside checkout'
    out.mkdir(parents=True, exist_ok=True)
    source = host.read_text()
    macro = extract(source, '#define ROW(fname, body)', '\n#ifdef RT_CAPTURE')
    wrappers = extract(source, '#ifdef RT_CAPTURE\nstatic bool journal_view', '\nROW(hf_fb_init')
    allowed = extract(source, 'static bool task_allowed(const char *name)', '\nstatic const host_entry host_table[]')
    header = host.with_name('rt.h')
    assert header.is_file(), 'the adjacent real rt.h is required'
    fixture = out / 'host-fixture.c'
    fixture.write_text('#include "' + str(header) + '"\n' + '\n'.join([macro, wrappers, allowed, HARNESS]))
    include = next(line.split(' ', 1)[1] for line in args.toolchain.read_text().splitlines() if line.startswith('include '))
    common = ['-std=c17', '-O2', '-Wall', '-Wextra', '-Werror', '-Wconversion', '-Wsign-conversion', '-Wpedantic', '-DCINT_RT_HELPERS_PORTABLE', '-I' + include]
    receipt = {'host_source': str(host), 'host_sha256': hashlib.sha256(host.read_bytes()).hexdigest(),
               'rt_header_sha256': hashlib.sha256(header.read_bytes()).hexdigest(),
               'toolchain_sha256': hashlib.sha256(args.toolchain.read_bytes()).hexdigest(),
               'test_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'builds': {}}
    for cc in ('gcc', 'clang'):
        for capture in (0, 1):
            binary = out / f'{cc}-capture-{capture}'
            flags = ['-DRT_CAPTURE'] if capture else []
            run([cc, *common, *flags, fixture, '-o', binary])
            stdout = run([binary])
            (out / f'{cc}-capture-{capture}.stdout').write_text(stdout)
            receipt['builds'][f'{cc}-capture-{capture}'] = {'stdout': stdout, 'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest()}
            print(cc + ': ' + stdout, end='')
    (out / 'host-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')


if __name__ == '__main__':
    main()
