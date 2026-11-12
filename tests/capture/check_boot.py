#!/usr/bin/env python3
"""Native mocked platform checks. Build products stay outside the checkout."""
import argparse
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BRIDGE = r'''
#include <assert.h>
#include <setjmp.h>
#include <stdio.h>
#include <string.h>
#include "@BOOT@"
static const uint8_t revision[32] = {91, 73, 22};
const cint_program cg_program = {.revision = revision};
static jmp_buf stopped;
static uint8_t directory[4 + 256 * 64], fixture[56], signature[4];
static uint8_t replay_fixture[56], expected_replay_fixture[56], archive[128], saved_replay_key[32];
static size_t offset;
static unsigned reader_opens, reader_closes, reader_sizes, reader_reads, records;
static unsigned archive_reads, archive_selects;
static int reader_error, reader_read_error, record_error, reader_active, validated;
static int expected_replay;
static daph_capture_read_at archive_read_at;
static void *archive_user;
static uint16_t selector;
static uint64_t root_cr3;
static unsigned begins, put_calls, finishes, aborts, serial_bytes, polls, exits, halts, cli, wipes;
static int begin_error, put_error, finish_error, uart_blocked, active, dlab, drain_blocked;
static unsigned drain_delay, drain_after_bytes;
static uint8_t forwarded_key[32], forwarded_stream[16], forwarded_revision[32];
static daph_capture_emit callback;
static void *callback_user;
void crypto_wipe(void *secret, size_t size)
{
    volatile uint8_t *p = secret;
    while (size--) *p++ = 0;
    wipes++;
}
void cpu_cli(void) { cli++; }
void cpu_halt(void) { halts++; longjmp(stopped, 1); }
uint64_t cr3_read(void) { return root_cr3; }
void port_out16(uint16_t port, uint16_t value)
{
    assert(port == 0x510u); selector = value; offset = 0;
    if (value == 0x22u) archive_selects++;
}
uint8_t port_in8(uint16_t port)
{
    if (port == 0x3FBu) return dlab ? 0x80u : 3u;
    if (port == 0x3FDu) {
        polls++; assert(polls <= 100001u);
        if (uart_blocked) return 0;
        if (drain_blocked) return 0x20u;
        if (serial_bytes >= drain_after_bytes && drain_delay) { drain_delay--; return 0x20u; }
        return 0x60u;
    }
    assert(port == 0x511u);
    if (selector == 0) { assert(offset < sizeof signature); return signature[offset++]; }
    if (selector == 0x19u) { assert(offset < sizeof directory); return directory[offset++]; }
    if (selector == 0x21u) { assert(offset < sizeof replay_fixture); return replay_fixture[offset++]; }
    if (selector == 0x22u) { assert(offset < sizeof archive); archive_reads++; return archive[offset++]; }
    assert(selector == 0x20u && offset < sizeof fixture);
    return fixture[offset++];
}
void port_out8(uint16_t port, uint8_t value)
{
    if (port == 0xF4u) { assert(value == RT_EXIT_PANIC); exits++; return; }
    if (port == 0x3FBu) dlab = (value & 0x80u) != 0;
    if (port == 0x3F8u && !dlab) serial_bytes++;
}
static int zeroed(const uint8_t *p, size_t n);
int daph_capture_sink_begin(const uint8_t key[32], const uint8_t stream[16],
                            const uint8_t rev[32], daph_capture_emit cb, void *user)
{
    begins++;
    assert(zeroed(replay_key, sizeof replay_key));
    if (expected_replay) assert(validated && reader_active && reader_opens == 1);
    memcpy(forwarded_key, key, 32); memcpy(forwarded_stream, stream, 16);
    memcpy(forwarded_revision, rev, 32); callback = cb; callback_user = user;
    active = !begin_error;
    return begin_error ? -1 : 0;
}
int daph_capture_sink_put(uint8_t byte)
{
    assert(byte == 0xA7u); put_calls++;
    return put_error ? -1 : 0;
}
int daph_capture_sink_finish(void)
{
    finishes++;
    if (finish_error) return -1;
    active = 0; return 0;
}
void daph_capture_sink_abort(void) { aborts++; active = 0; }
int crypto_verify32(const uint8_t a[32], const uint8_t b[32])
{
    return memcmp(a, b, 32) == 0 ? 0 : -1;
}
int daph_capture_sink_record(int kind, const uint8_t *bytes, size_t n)
{
    assert(kind == 1 && n == 3 && memcmp(bytes, "n!\n", 3) == 0);
    records++; return record_error ? -1 : 0;
}
int daph_capture_replay_open(const uint8_t key[32], const uint8_t stream[16],
                             const uint8_t rev[32], daph_capture_read_at read_at,
                             void *user, uint64_t sealed_bytes)
{
    uint8_t bytes[128];
    reader_opens++; assert(begins == 0 && !ready);
    assert(memcmp(rev, revision, 32) == 0);
    archive_read_at = read_at; archive_user = user;
    memcpy(saved_replay_key, key, 32);
    if (reader_error || sealed_bytes != sizeof archive ||
        memcmp(key, expected_replay_fixture + 8, 32) != 0 ||
        memcmp(stream, expected_replay_fixture + 40, 16) != 0) return -1;
    /* Whole-source validation is modeled before the sink may begin. */
    if (read_at(user, 0, bytes, sizeof bytes) != 0 ||
        memcmp(bytes, archive, sizeof bytes) != 0) return -1;
    validated = reader_active = 1;
    return 0;
}
int64_t daph_capture_replay_size(int kind)
{
    reader_sizes++;
    return reader_active && (kind == 1 || kind == 2) ? 17 : -1;
}
int64_t daph_capture_replay_read(int kind, uint64_t logical_offset, uint8_t *dst, size_t n)
{
    reader_reads++;
    if (!reader_active || reader_read_error || kind != 1 || logical_offset > 17) return -1;
    if (n > 17 - logical_offset) n = (size_t)(17 - logical_offset);
    if (n) memcpy(dst, archive + logical_offset, n);
    return (int64_t)n;
}
void daph_capture_replay_close(void)
{
    reader_closes++; reader_active = 0;
    crypto_wipe(saved_replay_key, sizeof saved_replay_key);
}
static void be_store(uint8_t *p, uint32_t n)
{
    p[0] = (uint8_t)(n >> 24); p[1] = (uint8_t)(n >> 16);
    p[2] = (uint8_t)(n >> 8); p[3] = (uint8_t)n;
}
static void entry(unsigned i, const char *name, uint32_t size, uint16_t item)
{
    uint8_t *p = directory + 4 + i * 64;
    memset(p, 0, 64); be_store(p, size);
    p[4] = (uint8_t)(item >> 8); p[5] = (uint8_t)item;
    memcpy(p + 8, name, strlen(name) + 1);
}
static void with_replay(void)
{
    be_store(directory, 3);
    entry(1, "opt/dev.integerc/daphnis-replay", sizeof archive, 0x22);
    entry(2, "opt/dev.integerc/daphnis-replay-key", sizeof replay_fixture, 0x21);
    expected_replay = 1;
}
static int zeroed(const uint8_t *p, size_t n)
{
    for (size_t i = 0; i < n; i++) if (p[i]) return 0;
    return 1;
}
static void reset(void)
{
    ready = 0; kernel_root = 0; replay_present = 0;
    memset(&replay_file, 0, sizeof replay_file);
    memset(replay_key, 0xCD, sizeof replay_key);
    memset(saved_replay_key, 0, sizeof saved_replay_key);
    memcpy(replay_fixture, "DAPHKEY1", 8);
    for (unsigned i = 8; i < sizeof replay_fixture; i++) replay_fixture[i] = (uint8_t)(i + 71);
    memcpy(expected_replay_fixture, replay_fixture, sizeof replay_fixture);
    for (unsigned i = 0; i < sizeof archive; i++) archive[i] = (uint8_t)(i * 7 + 11);
    reader_opens = reader_closes = reader_sizes = reader_reads = records = 0;
    archive_reads = archive_selects = 0;
    reader_error = reader_read_error = record_error = reader_active = validated = expected_replay = 0;
    archive_read_at = NULL; archive_user = NULL;
    memset(key_file, 0xCD, sizeof key_file);
    memset(directory, 0, sizeof directory); memcpy(signature, "QEMU", 4);
    memcpy(fixture, "DAPHKEY1", 8);
    for (unsigned i = 8; i < sizeof fixture; i++) fixture[i] = (uint8_t)i;
    be_store(directory, 1); be_store(directory + 4, 56); directory[9] = 0x20;
    memcpy(directory + 12, "opt/dev.integerc/daphnis-capture", 33);
    offset = 0; selector = 0; root_cr3 = 0x123000;
    begins = put_calls = finishes = aborts = serial_bytes = polls = exits = halts = cli = wipes = 0;
    begin_error = put_error = finish_error = uart_blocked = active = dlab = drain_blocked = 0;
    drain_delay = drain_after_bytes = 0;
    callback = NULL; callback_user = NULL;
}
static void stopped_check(void (*fn)(void))
{
    if (!setjmp(stopped)) { fn(); assert(!"expected stop"); }
    assert(exits == 1 && halts == 1 && cli == 1 && serial_bytes == 0);
}
static void put_one(void) { rt_capture_byte(0xA7u); }
static void record_one(void) { rt_journal_record(1, (const uint8_t *)"n!\n", 3); }
static void size_one(void) { (void)rt_journal_size(1); }
static void read_one(void) { uint8_t byte; (void)rt_journal_read(1, 0, &byte, 1); }
static void read_negative(void) { uint8_t byte; (void)rt_journal_read(1, -1, &byte, 1); }
static void boot_ok(void)
{
    if (setjmp(stopped)) assert(!"unexpected stop during valid boot");
    rt_capture_boot(); assert(begins == 1 && ready && active);
    assert(memcmp(forwarded_key, fixture + 8, 32) == 0);
    assert(memcmp(forwarded_stream, fixture + 40, 16) == 0);
    assert(memcmp(forwarded_revision, revision, 32) == 0);
    assert(zeroed(key_file, sizeof key_file) && wipes >= 1);
    assert(zeroed(replay_key, sizeof replay_key));
}
static void fail_boot(void)
{
    stopped_check(rt_capture_boot); assert(begins == 0 && !ready);
    assert(zeroed(key_file, sizeof key_file));
    assert(zeroed(replay_key, sizeof replay_key));
    assert(zeroed(saved_replay_key, sizeof saved_replay_key) && !reader_active);
}
static void run_case(const char *name)
{
    reset();
    if (!strcmp(name, "valid")) {
        boot_ok(); put_one(); rt_capture_finish();
        assert(put_calls == 1 && finishes == 1 && !ready && !active);
    } else if (!strcmp(name, "signature")) { signature[0] ^= 1; fail_boot();
    } else if (!strcmp(name, "missing")) { be_store(directory, 0); fail_boot();
    } else if (!strcmp(name, "wrong-name")) { directory[12] ^= 1; fail_boot();
    } else if (!strcmp(name, "name-unterminated")) { directory[44] = 'x'; fail_boot();
    } else if (!strcmp(name, "count-over-limit")) { be_store(directory, 257); fail_boot();
    } else if (!strcmp(name, "size-short")) { be_store(directory + 4, 55); fail_boot();
    } else if (!strcmp(name, "size-long")) { be_store(directory + 4, 57); fail_boot();
    } else if (!strcmp(name, "magic")) { fixture[0] ^= 1; fail_boot();
    } else if (!strcmp(name, "duplicate")) {
        be_store(directory, 2); memcpy(directory + 68, directory + 4, 64); fail_boot();
    } else if (!strcmp(name, "reserved-high")) { directory[10] = 1; fail_boot();
    } else if (!strcmp(name, "reserved-low")) { directory[11] = 1; fail_boot();
    } else if (!strcmp(name, "selector-zero")) { directory[9] = 0; fail_boot();
    } else if (!strcmp(name, "selector-reserved")) { directory[9] = 0x1F; fail_boot();
    } else if (!strcmp(name, "selector-dma")) { directory[8] = 0x40; fail_boot();
    } else if (!strcmp(name, "selector-write")) { directory[8] = 0x80; fail_boot();
    } else if (!strcmp(name, "count-limit")) { be_store(directory, 256); boot_ok();
    } else if (!strcmp(name, "before-byte")) { stopped_check(put_one); assert(put_calls == 0);
    } else if (!strcmp(name, "before-finish")) { stopped_check(rt_capture_finish); assert(finishes == 0);
    } else if (!strcmp(name, "cr3-byte")) {
        boot_ok(); root_cr3 ^= 0x1000; stopped_check(put_one); assert(put_calls == 0 && aborts == 0);
    } else if (!strcmp(name, "cr3-finish")) {
        boot_ok(); root_cr3 ^= 0x1000; stopped_check(rt_capture_finish); assert(finishes == 0 && aborts == 0);
    } else if (!strcmp(name, "begin-failure")) {
        begin_error = 1; stopped_check(rt_capture_boot);
        assert(begins == 1 && !active && zeroed(key_file, sizeof key_file));
    } else if (!strcmp(name, "put-failure")) {
        boot_ok(); put_error = 1; stopped_check(put_one); assert(put_calls == 1 && !active && aborts == 1 && !ready);
    } else if (!strcmp(name, "finish-failure")) {
        boot_ok(); finish_error = 1; stopped_check(rt_capture_finish); assert(finishes == 1 && !active && aborts == 1 && !ready);
    } else if (!strcmp(name, "after-finish-byte")) {
        boot_ok(); rt_capture_finish(); stopped_check(put_one); assert(put_calls == 0);
    } else if (!strcmp(name, "double-finish")) {
        boot_ok(); rt_capture_finish(); stopped_check(rt_capture_finish); assert(finishes == 1);
    } else if (!strcmp(name, "uart-ready")) {
        const uint8_t bytes[] = {0xAA, 0xBB}; boot_ok();
        assert(callback(callback_user, bytes, sizeof bytes) == 0 && serial_bytes == 2 && polls == 3);
    } else if (!strcmp(name, "uart-dlab")) {
        const uint8_t byte = 0xAA; boot_ok(); dlab = 1;
        assert(callback(callback_user, &byte, 1) == -1 && serial_bytes == 0 && polls == 0);
    } else if (!strcmp(name, "uart-timeout")) {
        const uint8_t byte = 0xAA; boot_ok(); uart_blocked = 1;
        assert(callback(callback_user, &byte, 1) == -1 && serial_bytes == 0 && polls == 100000);
    } else if (!strcmp(name, "uart-drain-delayed")) {
        const uint8_t byte = 0xAA; boot_ok(); drain_after_bytes = 1; drain_delay = 7;
        assert(callback(callback_user, &byte, 1) == 0 && serial_bytes == 1 && polls == 9);
    } else if (!strcmp(name, "uart-drain-last-poll")) {
        const uint8_t byte = 0xAA; boot_ok(); drain_after_bytes = 1; drain_delay = 99999;
        assert(callback(callback_user, &byte, 1) == 0 && serial_bytes == 1 && polls == 100001);
    } else if (!strcmp(name, "uart-drain-timeout")) {
        const uint8_t byte = 0xAA; boot_ok(); drain_blocked = 1;
        assert(callback(callback_user, &byte, 1) == -1 && serial_bytes == 1 && polls == 100001);
    } else if (!strcmp(name, "uart-empty-ready")) {
        boot_ok(); assert(callback(callback_user, NULL, 0) == 0 && serial_bytes == 0 && polls == 1);
    } else if (!strcmp(name, "uart-empty-delayed")) {
        boot_ok(); drain_delay = 7;
        assert(callback(callback_user, NULL, 0) == 0 && serial_bytes == 0 && polls == 8);
    } else if (!strcmp(name, "uart-empty-timeout")) {
        boot_ok(); drain_blocked = 1;
        assert(callback(callback_user, NULL, 0) == -1 && serial_bytes == 0 && polls == 100000);
    } else if (!strcmp(name, "replay-valid")) {
        with_replay(); boot_ok();
        assert(replay_present && reader_opens == 1 && validated && archive_reads == sizeof archive);
        assert(rt_journal_size(1) == 17 && rt_journal_size(2) == 17);
        uint8_t bytes[6];
        assert(rt_journal_read(1, 5, bytes, sizeof bytes) == 6);
        assert(memcmp(bytes, archive + 5, sizeof bytes) == 0);
        assert(rt_journal_read(1, 17, bytes, sizeof bytes) == 0);
        record_one(); assert(records == 1);
        rt_capture_finish();
        assert(!replay_present && !reader_active && reader_closes == 1);
        assert(zeroed(saved_replay_key, sizeof saved_replay_key));
    } else if (!strcmp(name, "replay-missing-key")) {
        with_replay(); be_store(directory, 2); fail_boot(); assert(reader_opens == 0);
    } else if (!strcmp(name, "replay-missing-archive")) {
        with_replay(); directory[76] ^= 1; fail_boot(); assert(reader_opens == 0);
    } else if (!strcmp(name, "replay-wrong-key")) {
        with_replay(); replay_fixture[8] ^= 1; fail_boot(); assert(reader_opens == 1 && !validated);
    } else if (!strcmp(name, "replay-wrong-stream")) {
        with_replay(); replay_fixture[40] ^= 1; fail_boot(); assert(reader_opens == 1 && !validated);
    } else if (!strcmp(name, "replay-key-magic")) {
        with_replay(); replay_fixture[0] ^= 1; fail_boot(); assert(reader_opens == 0);
    } else if (!strcmp(name, "replay-key-short")) {
        with_replay(); be_store(directory + 132, 55); fail_boot(); assert(reader_opens == 0);
    } else if (!strcmp(name, "replay-key-long")) {
        with_replay(); be_store(directory + 132, 57); fail_boot(); assert(reader_opens == 0);
    } else if (!strcmp(name, "replay-same-output-key")) {
        with_replay(); memcpy(replay_fixture + 8, fixture + 8, 32);
        fail_boot(); assert(reader_opens == 0);
    } else if (!strcmp(name, "replay-duplicate-archive")) {
        with_replay(); be_store(directory, 4); memcpy(directory + 196, directory + 68, 64);
        fail_boot(); assert(reader_opens == 0);
    } else if (!strcmp(name, "replay-duplicate-key")) {
        with_replay(); be_store(directory, 4); memcpy(directory + 196, directory + 132, 64);
        fail_boot(); assert(reader_opens == 0);
    } else if (!strcmp(name, "replay-archive-selector")) {
        with_replay(); directory[73] = 0x1f; fail_boot(); assert(reader_opens == 0);
    } else if (!strcmp(name, "replay-key-selector")) {
        with_replay(); directory[137] = 0x1f; fail_boot(); assert(reader_opens == 0);
    } else if (!strcmp(name, "replay-archive-reserved")) {
        with_replay(); directory[74] = 1; fail_boot(); assert(reader_opens == 0);
    } else if (!strcmp(name, "replay-key-reserved")) {
        with_replay(); directory[139] = 1; fail_boot(); assert(reader_opens == 0);
    } else if (!strcmp(name, "replay-auth-failure")) {
        with_replay(); reader_error = 1; fail_boot(); assert(reader_opens == 1 && !validated);
    } else if (!strcmp(name, "replay-size-failure")) {
        with_replay(); be_store(directory + 68, sizeof archive - 1);
        fail_boot(); assert(reader_opens == 1 && !validated);
    } else if (!strcmp(name, "replay-read-at")) {
        uint8_t bytes[16]; with_replay(); boot_ok();
        unsigned selections = archive_selects, reads = archive_reads;
        assert(archive_read_at(archive_user, 8, bytes, 4) == 0);
        assert(memcmp(bytes, archive + 8, 4) == 0 && archive_selects == selections + 1);
        assert(archive_reads == reads + 12);
        selections = archive_selects; reads = archive_reads;
        assert(archive_read_at(archive_user, 30, bytes, sizeof bytes) == 0);
        assert(memcmp(bytes, archive + 30, sizeof bytes) == 0 && archive_selects == selections);
        assert(archive_reads == reads + 34);
        assert(archive_read_at(archive_user, 2, bytes, sizeof bytes) == 0);
        assert(memcmp(bytes, archive + 2, sizeof bytes) == 0 && archive_selects == selections + 1);
        selections = archive_selects; reads = archive_reads;
        memset(bytes, 0xAD, sizeof bytes);
        assert(archive_read_at(archive_user, sizeof archive + 1, bytes, 0) == -1);
        assert(archive_read_at(archive_user, sizeof archive, bytes, 1) == -1);
        assert(archive_read_at(archive_user, UINT64_MAX, bytes, 1) == -1);
        assert(archive_reads == reads && archive_selects == selections);
        for (unsigned i = 0; i < sizeof bytes; i++) assert(bytes[i] == 0xAD);
        assert(archive_read_at(archive_user, sizeof archive, bytes, 0) == 0);
    } else if (!strcmp(name, "record-before-boot")) {
        stopped_check(record_one); assert(records == 0);
    } else if (!strcmp(name, "size-before-boot")) {
        stopped_check(size_one); assert(reader_sizes == 0);
    } else if (!strcmp(name, "read-before-boot")) {
        stopped_check(read_one); assert(reader_reads == 0);
    } else if (!strcmp(name, "record-without-replay")) {
        boot_ok(); record_one(); assert(records == 1 && rt_journal_size(1) == -1 && reader_sizes == 0);
    } else if (!strcmp(name, "read-without-replay")) {
        boot_ok(); stopped_check(read_one); assert(reader_reads == 0 && aborts == 1 && reader_closes == 1);
    } else if (!strcmp(name, "replay-record-cr3")) {
        with_replay(); boot_ok(); root_cr3 ^= 0x1000;
        stopped_check(record_one); assert(records == 0 && aborts == 0 && reader_closes == 0);
    } else if (!strcmp(name, "replay-size-cr3")) {
        with_replay(); boot_ok(); root_cr3 ^= 0x1000;
        stopped_check(size_one); assert(reader_sizes == 0 && aborts == 0 && reader_closes == 0);
    } else if (!strcmp(name, "replay-read-cr3")) {
        with_replay(); boot_ok(); root_cr3 ^= 0x1000;
        stopped_check(read_one); assert(reader_reads == 0 && aborts == 0 && reader_closes == 0);
    } else if (!strcmp(name, "replay-read-negative")) {
        with_replay(); boot_ok(); stopped_check(read_negative);
        assert(reader_reads == 0 && aborts == 1 && reader_closes == 1 && !ready);
    } else if (!strcmp(name, "replay-read-failure")) {
        with_replay(); boot_ok(); reader_read_error = 1; stopped_check(read_one);
        assert(reader_reads == 1 && aborts == 1 && reader_closes == 1 && !ready);
        assert(zeroed(saved_replay_key, sizeof saved_replay_key));
    } else if (!strcmp(name, "replay-record-failure")) {
        with_replay(); boot_ok(); record_error = 1; stopped_check(record_one);
        assert(records == 1 && aborts == 1 && reader_closes == 1 && !ready);
        assert(zeroed(saved_replay_key, sizeof saved_replay_key));
    } else if (!strcmp(name, "replay-begin-failure")) {
        with_replay(); begin_error = 1; stopped_check(rt_capture_boot);
        assert(begins == 1 && validated && reader_closes == 1 && !reader_active);
        assert(zeroed(key_file, sizeof key_file) && zeroed(replay_key, sizeof replay_key));
        assert(zeroed(saved_replay_key, sizeof saved_replay_key));
    } else if (!strcmp(name, "replay-put-failure")) {
        with_replay(); boot_ok(); put_error = 1; stopped_check(put_one);
        assert(put_calls == 1 && aborts == 1 && reader_closes == 1 && !ready);
        assert(zeroed(saved_replay_key, sizeof saved_replay_key));
    } else if (!strcmp(name, "replay-finish-failure")) {
        with_replay(); boot_ok(); finish_error = 1; stopped_check(rt_capture_finish);
        assert(finishes == 1 && aborts == 1 && reader_closes == 1 && !ready);
        assert(zeroed(saved_replay_key, sizeof saved_replay_key));
    } else if (!strcmp(name, "replay-after-finish")) {
        with_replay(); boot_ok(); rt_capture_finish(); stopped_check(size_one);
        assert(reader_sizes == 0 && reader_closes == 1);
    } else { assert(!"unknown case"); }
    printf("pass %s\n", name);
}
int main(int argc, char **argv) { assert(argc == 2); run_case(argv[1]); return 0; }
'''
CASES = ('valid signature missing wrong-name name-unterminated count-over-limit '
         'size-short size-long magic duplicate reserved-high reserved-low '
         'selector-zero selector-reserved selector-dma selector-write count-limit '
         'before-byte before-finish cr3-byte cr3-finish begin-failure put-failure '
         'finish-failure after-finish-byte double-finish uart-ready uart-dlab uart-timeout '
         'uart-drain-delayed uart-drain-last-poll uart-drain-timeout '
         'uart-empty-ready uart-empty-delayed uart-empty-timeout '
         'replay-valid replay-missing-key replay-missing-archive replay-wrong-key replay-wrong-stream replay-key-magic '
         'replay-key-short replay-key-long replay-same-output-key replay-duplicate-archive '
         'replay-duplicate-key replay-archive-selector replay-key-selector '
         'replay-archive-reserved replay-key-reserved replay-auth-failure replay-size-failure '
         'replay-read-at record-before-boot size-before-boot read-before-boot '
         'record-without-replay read-without-replay replay-record-cr3 replay-size-cr3 '
         'replay-read-cr3 replay-read-negative replay-read-failure replay-record-failure '
         'replay-begin-failure replay-put-failure replay-finish-failure replay-after-finish').split()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--boot-source', type=Path, default=ROOT / 'rt/capture_boot.c')
    parser.add_argument('--toolchain', type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    if out == ROOT or ROOT in out.parents:
        parser.error('--out must be outside the checkout')
    out.mkdir(parents=True, exist_ok=True)
    include = next(line.split(' ', 1)[1] for line in args.toolchain.read_text().splitlines()
                   if line.startswith('include '))
    source = out / 'boot_mock.c'
    source.write_text(BRIDGE.replace('@BOOT@', str(args.boot_source.resolve())))
    compilers = ('gcc', 'clang')
    missing = [cc for cc in compilers if not shutil.which(cc)]
    if missing:
        raise RuntimeError('required compilers missing: ' + ', '.join(missing))
    results = []
    for cc in compilers:
        binary = out / f'boot_mock_{cc}'
        command = [cc, '-std=c17', '-O2', '-Wall', '-Wextra', '-Werror',
                   '-I', include, str(source), '-o', str(binary)]
        subprocess.run(command, check=True, timeout=30, cwd=out)
        for case in CASES:
            result = subprocess.run([str(binary), case], text=True, capture_output=True, timeout=5, cwd=out)
            print(f'{cc}: {case}: {"pass" if result.returncode == 0 else "fail"}', flush=True)
            results.append({'compiler': cc, 'case': case, 'returncode': result.returncode,
                            'stdout': result.stdout, 'stderr': result.stderr})
    (out / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
    failures = sum(result['returncode'] != 0 for result in results)
    print(f'boot mock checks: {len(results) - failures}/{len(results)} passed')
    raise SystemExit(bool(failures))


if __name__ == '__main__':
    main()
