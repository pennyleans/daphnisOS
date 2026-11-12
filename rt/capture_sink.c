/* Bounded native typed-record writer within the unchanged CR-1 envelope. */
#include "capture_sink.h"
#include "capture_crypto.h"
#include "../vendor/monocypher/monocypher.h"

struct capture_sink {
    uint8_t header[64];
    uint8_t previous[16];
    uint8_t pending[DAPH_CAPTURE_MAX_PLAIN];
    uint8_t aad[96];
    uint8_t frame[DAPH_CAPTURE_MAX_PLAIN + 48u];
    size_t pending_n;
    uint64_t sequence;
    int64_t slot;
    daph_capture_emit emit;
    void *user;
};

#ifdef DAPH_CAPTURE_PRIVATE_HIGH
#define CAPTURE_PRIVATE __attribute__((section(".high.data")))
#else
#define CAPTURE_PRIVATE
#endif

static struct capture_sink sink CAPTURE_PRIVATE;
/* Lifecycle and the reentry latch survive erasure of private buffers. */
static int started CAPTURE_PRIVATE;
static int failed CAPTURE_PRIVATE;
static int busy CAPTURE_PRIVATE;
static int done CAPTURE_PRIVATE;

static void copy_bytes(uint8_t *dst, const uint8_t *src, size_t n)
{
    size_t i;
    for (i = 0u; i < n; i++) dst[i] = src[i];
}

static void erase(void)
{
    daph_capture_key_close(sink.slot);
    crypto_wipe(&sink, sizeof sink);
}

static int fail(void)
{
    failed = 1;
    erase();
    return -1;
}

static int enter(void)
{
    if (busy) return fail();
    busy = 1;
    return 0;
}

static int leave(int result)
{
    busy = 0;
    return result;
}

static int emit_bytes(const uint8_t *bytes, size_t n)
{
    int result;
    if (failed || sink.emit == NULL) return fail();
    result = sink.emit(sink.user, bytes, n);
    /* Reentry may erase sink even if the callback reports success. */
    if (failed || result != 0) return fail();
    return 0;
}

static int frame(int final)
{
    size_t i, n = sink.pending_n;
    uint8_t *prefix = sink.aad + 64u;
    if (failed || sink.sequence == UINT64_MAX ||
        (final ? n != 0u : n == 0u)) return fail();
    copy_bytes(sink.aad, sink.header, 64u);
    for (i = 0u; i < 32u; i++) prefix[i] = 0u;
    for (i = 0u; i < 8u; i++) prefix[i] = (uint8_t)(sink.sequence >> (8u * i));
    prefix[8] = (uint8_t)n;
    prefix[9] = (uint8_t)(n >> 8u);
    prefix[12] = (uint8_t)final;
    copy_bytes(prefix + 16u, sink.previous, 16u);
    copy_bytes(sink.frame, prefix, 32u);
    if (daph_capture_seal(sink.slot, sink.sequence, sink.aad, 96u,
                          sink.pending, n, sink.frame + 32u,
                          sink.frame + 32u + n) != 0) return fail();
    /* No plaintext is retained while the external output callback runs. */
    crypto_wipe(sink.pending, sizeof sink.pending);
    sink.pending_n = 0u;
    if (emit_bytes(sink.frame, n + 48u) != 0) return -1;
    copy_bytes(sink.previous, sink.frame + 32u + n, 16u);
    sink.sequence++;
    crypto_wipe(sink.aad, sizeof sink.aad);
    crypto_wipe(sink.frame, sizeof sink.frame);
    return 0;
}

int daph_capture_sink_begin(const uint8_t key[32], const uint8_t stream[16],
                            const uint8_t revision[32],
                            daph_capture_emit emit, void *user)
{
    size_t i;
    static const uint8_t magic[8] = {'D','A','P','H','R','E','C','1'};
    if (enter() != 0) return -1;
    if (started || failed || done || key == NULL || stream == NULL ||
        revision == NULL || emit == NULL) return leave(fail());
    started = 1;
    sink.slot = daph_capture_key_open(key, stream, 1);
    if (sink.slot <= 0) return leave(fail());
    for (i = 0u; i < 64u; i++) sink.header[i] = 0u;
    copy_bytes(sink.header, magic, sizeof magic);
    sink.header[8] = 1u;
    sink.header[10] = 1u;
    sink.header[13] = 16u;
    copy_bytes(sink.header + 16u, stream, 16u);
    copy_bytes(sink.header + 32u, revision, 32u);
    sink.emit = emit;
    sink.user = user;
    if (emit_bytes(sink.header, sizeof sink.header) != 0) return leave(-1);
    copy_bytes(sink.pending, (const uint8_t *)"DAPHEVT1", 8u);
    sink.pending_n = 8u;
    return leave(frame(0));
}

static int console_frame(void)
{
    size_t i, n = sink.pending_n;
    if (n == 0u) return 0;
    for (i = n; i > 0u; i--) sink.pending[i + 2u] = sink.pending[i - 1u];
    sink.pending[0] = 0u;
    sink.pending[1] = (uint8_t)n;
    sink.pending[2] = (uint8_t)(n >> 8u);
    sink.pending_n = n + 3u;
    return frame(0);
}

int daph_capture_sink_record(int kind, const uint8_t *bytes, size_t n)
{
    size_t limit;
    if (enter() != 0) return -1;
    limit = kind == 1 ? 3101u : 521u;
    if (!started || failed || done || (kind != 1 && kind != 2) ||
        bytes == NULL || n == 0u || n > limit || bytes[n - 1u] != (uint8_t)'\n')
        return leave(fail());
    if (console_frame() != 0) return leave(-1);
    sink.pending[0] = (uint8_t)kind;
    sink.pending[1] = (uint8_t)n;
    sink.pending[2] = (uint8_t)(n >> 8u);
    copy_bytes(sink.pending + 3u, bytes, n);
    sink.pending_n = n + 3u;
    return leave(frame(0));
}

int daph_capture_sink_put(uint8_t byte)
{
    if (enter() != 0) return -1;
    if (!started || failed || done) return leave(fail());
    sink.pending[sink.pending_n++] = byte;
    if (sink.pending_n == sizeof sink.pending - 3u || byte == (uint8_t)'\n')
        return leave(console_frame());
    return leave(0);
}

int daph_capture_sink_finish(void)
{
    int result;
    if (enter() != 0) return -1;
    if (!started || failed || done) return leave(fail());
    if (sink.pending_n != 0u && console_frame() != 0) return leave(-1);
    result = frame(1);
    if (result == 0) {
        done = 1;
        erase();
    }
    return leave(result);
}

void daph_capture_sink_abort(void)
{
    if (enter() != 0) return;
    (void)fail();
    (void)leave(-1);
}

#ifdef DAPH_CAPTURE_TEST
int daph_capture_sink_test_zeroed(void)
{
    const uint8_t *bytes = (const uint8_t *)&sink;
    uint8_t diff = 0u;
    size_t i;
    for (i = 0u; i < sizeof sink; i++) diff |= bytes[i];
    return diff == 0u;
}

int daph_capture_sink_test_counter(uint64_t sequence)
{
    if (busy || !started || failed || done ||
        daph_capture_test_counter(sink.slot, sequence) != 0) return -1;
    sink.sequence = sequence;
    return 0;
}
#endif
