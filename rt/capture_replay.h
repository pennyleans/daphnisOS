#ifndef DAPH_CAPTURE_REPLAY_H
#define DAPH_CAPTURE_REPLAY_H

#include <stddef.h>
#include <stdint.h>

#define DAPH_CAPTURE_REPLAY_MAX_BYTES (16u * 1024u * 1024u)

typedef int (*daph_capture_read_at)(void *user, uint64_t offset,
                                    uint8_t *dst, size_t n);

/* We accept one immutable sealed source, at most 16 MiB, through a callback
 * returning zero only after reading exactly n bytes. We authenticate the whole
 * CR-1 chain, final frame and typed schema before making any input available.
 * The expected stream and revision must match. Old untyped captures fail.
 * The firmware item must remain immutable until close; we authenticate each
 * newly loaded frame again on read. The host and hypervisor are outside this
 * boundary. Previously verified cached bytes remain available without source
 * reads; new frames and rewind reloads are authenticated again. Calls must be
 * serialized. Callback reentry closes the reader.
 * No key or source callback is exported to cint. Open returns zero or -1. */
int daph_capture_replay_open(const uint8_t key[32], const uint8_t stream[16],
                             const uint8_t revision[32],
                             daph_capture_read_at read_at, void *user,
                             uint64_t sealed_bytes);
/* We expose only input kinds 1 (network) and 2 (RNG/RTC), concatenated in their
 * original order. Console records cannot impersonate inputs. Two bounded
 * channel cursors scan forward; backward reads reset the selected cursor.
 * Size returns -1 when closed or for another kind.
 * Read returns up to n bytes, zero at EOF, or -1 with dst unchanged. We require
 * n <= 4096 and a nonnull dst unless n is zero. Authentication or source
 * failures close the reader and wipe its private cursors and scratch. */
int64_t daph_capture_replay_size(int kind);
int64_t daph_capture_replay_read(int kind, uint64_t logical_offset,
                                uint8_t *dst, size_t n);
void daph_capture_replay_close(void);

#ifdef DAPH_CAPTURE_TEST
int daph_capture_replay_test_zeroed(void);
#endif

#endif
