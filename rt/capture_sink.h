#ifndef DAPH_CAPTURE_SINK_H
#define DAPH_CAPTURE_SINK_H

#include <stddef.h>
#include <stdint.h>

typedef int (*daph_capture_emit)(void *user, const uint8_t *bytes, size_t n);

/* We serialize calls to this single native sink. The callback returns zero
 * only after accepting every byte; any nonzero result permanently fails the
 * sink. Callback reentry, including abort, also permanently fails it.
 * We require fresh key and stream bytes for each boot's recording. No key is
 * exported to cint. Begin, put, and finish return zero or -1 on failure.
 * Finish and failure are terminal; abort wipes pending bytes and the key slot.
 * We emit the header and typed magic immediately, console at 4093 bytes or
 * newline, and an empty
 * authenticated final frame only on finish. Callers must discard failed or
 * incomplete recordings. Output failure can leave bytes already emitted. */
int daph_capture_sink_begin(const uint8_t key[32], const uint8_t stream[16],
                            const uint8_t revision[32],
                            daph_capture_emit emit, void *user);
int daph_capture_sink_put(uint8_t byte);
/* We flush pending console before each input record. Kind 1 is a network
 * journal line, kind 2 an RNG/RTC journal line, including the trailing LF.
 * Limits are 3101 and 521 bytes respectively; invalid input fails the sink. */
int daph_capture_sink_record(int kind, const uint8_t *bytes, size_t n);
int daph_capture_sink_finish(void);
void daph_capture_sink_abort(void);

#ifdef DAPH_CAPTURE_TEST
int daph_capture_sink_test_zeroed(void);
int daph_capture_sink_test_counter(uint64_t sequence);
#endif

#endif
