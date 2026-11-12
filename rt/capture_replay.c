/* Complete authentication and bounded typed-input cursors for CR-1 sources. */
#include "capture_replay.h"
#include "capture_crypto.h"
#include "../vendor/monocypher/monocypher.h"

#ifdef DAPH_CAPTURE_PRIVATE_HIGH
#define CAPTURE_PRIVATE __attribute__((section(".high.data")))
#else
#define CAPTURE_PRIVATE
#endif

struct replay_cursor {
    uint8_t plain[DAPH_CAPTURE_MAX_PLAIN];
    uint8_t previous[16];
    uint64_t file_offset;
    uint64_t sequence;
    uint64_t logical_next;
    uint64_t cache_base;
    size_t cache_n;
    int cached;
    int ended;
};

struct capture_replay {
    struct replay_cursor cursors[2];
    uint8_t header[64];
    uint8_t aad[96];
    uint8_t tag[16];
    uint8_t staged[DAPH_CAPTURE_MAX_PLAIN];
    uint64_t totals[2];
    uint64_t sealed_bytes;
    int64_t slot;
    daph_capture_read_at read_at;
    void *user;
};

static struct capture_replay replay CAPTURE_PRIVATE;
static int active CAPTURE_PRIVATE;
static int busy CAPTURE_PRIVATE;
static int poisoned CAPTURE_PRIVATE;

static void copy_bytes(uint8_t *dst, const uint8_t *src, size_t n)
{
    size_t i;
    for (i = 0u; i < n; i++) dst[i] = src[i];
}

static int same(const uint8_t *a, const uint8_t *b, size_t n)
{
    uint8_t diff = 0u;
    size_t i;
    for (i = 0u; i < n; i++) diff |= a[i] ^ b[i];
    return diff == 0u;
}

static void erase(void)
{
    daph_capture_key_close(replay.slot);
    crypto_wipe(&replay, sizeof replay);
    active = 0;
}

static int fail(void)
{
    poisoned = 1;
    erase();
    return -1;
}

static int enter(void)
{
    if (busy) return fail();
    busy = 1;
    return 0;
}

static int64_t leave(int64_t result)
{
    busy = 0;
    return result;
}

static int source(uint64_t offset, uint8_t *dst, size_t n)
{
    int result;
    if (poisoned || replay.read_at == NULL || offset > replay.sealed_bytes ||
        (uint64_t)n > replay.sealed_bytes - offset) return fail();
    result = replay.read_at(replay.user, offset, dst, n);
    if (poisoned || result != 0) return fail();
    return 0;
}

static uint64_t get64(const uint8_t *p)
{
    uint64_t value = 0u;
    unsigned i;
    for (i = 0u; i < 8u; i++) value |= (uint64_t)p[i] << (8u * i);
    return value;
}

/* We authenticate before inspecting any plaintext, including the schema. */
static int load_frame(uint64_t offset, uint64_t sequence,
                      const uint8_t previous[16], uint8_t *plain,
                      size_t *n, int *final)
{
    uint8_t *prefix = replay.aad + 64u;
    size_t size;
    crypto_wipe(plain, DAPH_CAPTURE_MAX_PLAIN);
    if (source(offset, prefix, 32u) != 0) return -1;
    size = (size_t)prefix[8] | ((size_t)prefix[9] << 8u);
    if (get64(prefix) != sequence || sequence == UINT64_MAX ||
        prefix[10] != 0u || prefix[11] != 0u || prefix[12] > 1u ||
        prefix[13] != 0u || prefix[14] != 0u || prefix[15] != 0u ||
        !same(prefix + 16u, previous, 16u) || size > DAPH_CAPTURE_MAX_PLAIN ||
        (prefix[12] == 1u ? size != 0u : size == 0u) ||
        offset > replay.sealed_bytes || replay.sealed_bytes - offset < size + 48u)
        return fail();
    *final = (int)prefix[12];
    *n = size;
    copy_bytes(replay.aad, replay.header, 64u);
    if (source(offset + 32u, plain, size) != 0 ||
        source(offset + 32u + size, replay.tag, 16u) != 0) return -1;
    if (daph_capture_open(replay.slot, sequence, replay.aad, 96u,
                          plain, size, replay.tag, plain) != 0)
        return fail();
    return 0;
}

static int record_shape(const uint8_t *plain, size_t n, int *kind, size_t *body)
{
    size_t length;
    int type;
    if (n < 3u) return fail();
    type = (int)plain[0];
    length = (size_t)plain[1] | ((size_t)plain[2] << 8u);
    if (type > 2 || length != n - 3u ||
        (type == 0 && length > 4093u) ||
        (type == 1 && (length == 0u || length > 3101u)) ||
        (type == 2 && (length == 0u || length > 521u)) ||
        (type != 0 && plain[n - 1u] != (uint8_t)'\n')) return fail();
    *kind = type;
    *body = length;
    return 0;
}

int daph_capture_replay_open(const uint8_t key[32], const uint8_t stream[16],
                             const uint8_t revision[32],
                             daph_capture_read_at read_at, void *user,
                             uint64_t sealed_bytes)
{
    static const uint8_t fixed[16] = {
        'D','A','P','H','R','E','C','1',1,0,1,0,0,16,0,0
    };
    uint8_t previous[16] = {0};
    uint64_t offset = 64u, sequence = 0u;
    uint8_t *plain = replay.cursors[0].plain;
    int result = -1;
    if (enter() != 0) return -1;
    if (active || key == NULL || stream == NULL || revision == NULL ||
        read_at == NULL || sealed_bytes > DAPH_CAPTURE_REPLAY_MAX_BYTES ||
        sealed_bytes < 168u) goto invalid;
    poisoned = 0;
    replay.read_at = read_at;
    replay.user = user;
    replay.sealed_bytes = sealed_bytes;
    if (source(0u, replay.header, 64u) != 0) goto end;
    if (!same(replay.header, fixed, 16u) ||
        !same(replay.header + 16u, stream, 16u) ||
        !same(replay.header + 32u, revision, 32u)) goto invalid;
    replay.slot = daph_capture_key_open(key, stream, 0);
    if (replay.slot <= 0) goto invalid;
    while (offset < sealed_bytes) {
        size_t n, body;
        int final, kind;
        if (load_frame(offset, sequence, previous, plain, &n, &final) != 0) goto end;
        if (final) {
            if (sequence == 0u || offset + 48u != sealed_bytes) goto invalid;
            active = 1;
            result = 0;
            break;
        }
        if (sequence == 0u) {
            if (n != 8u || !same(plain, (const uint8_t *)"DAPHEVT1", 8u))
                goto invalid;
        } else {
            if (record_shape(plain, n, &kind, &body) != 0) goto end;
            if (kind != 0) replay.totals[kind - 1] += body;
        }
        copy_bytes(previous, replay.tag, 16u);
        crypto_wipe(plain, DAPH_CAPTURE_MAX_PLAIN);
        offset += n + 48u;
        sequence++;
    }
    if (result != 0) goto invalid;
    crypto_wipe(plain, DAPH_CAPTURE_MAX_PLAIN);
    crypto_wipe(replay.cursors, sizeof replay.cursors);
    replay.cursors[0].file_offset = 64u;
    replay.cursors[1].file_offset = 64u;
    crypto_wipe(replay.aad, sizeof replay.aad);
    crypto_wipe(replay.tag, sizeof replay.tag);
    goto end;
invalid:
    (void)fail();
end:
    crypto_wipe(previous, sizeof previous);
    return (int)leave(result);
}

int64_t daph_capture_replay_size(int kind)
{
    int64_t result;
    if (enter() != 0) return -1;
    result = active && !poisoned && (kind == 1 || kind == 2)
        ? (int64_t)replay.totals[kind - 1] : -1;
    return leave(result);
}

static void reset_cursor(struct replay_cursor *cursor)
{
    crypto_wipe(cursor, sizeof *cursor);
    cursor->file_offset = 64u;
}

/* We retain one current record per channel and scan forward from its successor.
 * Backward reads reset only that channel. Console is never input. */
static int advance(struct replay_cursor *cursor, int wanted_kind)
{
    cursor->cached = 0;
    while (!cursor->ended) {
        size_t n, body;
        int final, kind;
        uint64_t offset = cursor->file_offset, sequence = cursor->sequence;
        if (load_frame(offset, sequence, cursor->previous, cursor->plain,
                       &n, &final) != 0) return -1;
        if (final) {
            if (offset + 48u != replay.sealed_bytes) return fail();
            cursor->ended = 1;
            crypto_wipe(cursor->plain, sizeof cursor->plain);
            return 0;
        }
        cursor->file_offset += n + 48u;
        cursor->sequence++;
        copy_bytes(cursor->previous, replay.tag, 16u);
        if (sequence == 0u) {
            if (n != 8u || !same(cursor->plain, (const uint8_t *)"DAPHEVT1", 8u))
                return fail();
        } else {
            if (record_shape(cursor->plain, n, &kind, &body) != 0) return -1;
            if (kind == wanted_kind) {
                cursor->cache_base = cursor->logical_next;
                cursor->cache_n = body;
                cursor->logical_next += body;
                cursor->cached = 1;
                return 1;
            }
        }
        crypto_wipe(cursor->plain, sizeof cursor->plain);
    }
    return 0;
}

int64_t daph_capture_replay_read(int kind, uint64_t logical_offset,
                                uint8_t *dst, size_t n)
{
    struct replay_cursor *cursor;
    size_t wanted, copied = 0u;
    int64_t result = -1;
    if (enter() != 0) return -1;
    if (!active || poisoned || (kind != 1 && kind != 2) ||
        n > DAPH_CAPTURE_MAX_PLAIN || (n != 0u && dst == NULL)) goto end;
    if (logical_offset >= replay.totals[kind - 1] || n == 0u) {
        result = 0;
        goto end;
    }
    wanted = n;
    if ((uint64_t)wanted > replay.totals[kind - 1] - logical_offset)
        wanted = (size_t)(replay.totals[kind - 1] - logical_offset);
    cursor = &replay.cursors[kind - 1];
    if (cursor->cached && logical_offset < cursor->cache_base) reset_cursor(cursor);
    while (copied < wanted) {
        size_t from, take;
        if (!cursor->cached || logical_offset >= cursor->logical_next) {
            int step = advance(cursor, kind);
            if (step < 0) goto end;
            if (step == 0) goto invalid;
            if (logical_offset >= cursor->logical_next) continue;
        }
        if (logical_offset < cursor->cache_base) goto invalid;
        from = (size_t)(logical_offset - cursor->cache_base);
        take = cursor->cache_n - from;
        if (take > wanted - copied) take = wanted - copied;
        copy_bytes(replay.staged + copied, cursor->plain + 3u + from, take);
        copied += take;
        logical_offset += take;
    }
    copy_bytes(dst, replay.staged, wanted);
    result = (int64_t)wanted;
    goto end;
invalid:
    (void)fail();
end:
    crypto_wipe(replay.staged, copied);
    crypto_wipe(replay.aad, sizeof replay.aad);
    crypto_wipe(replay.tag, sizeof replay.tag);
    return leave(result);
}

void daph_capture_replay_close(void)
{
    if (enter() != 0) return;
    erase();
    poisoned = 0;
    (void)leave(0);
}

#ifdef DAPH_CAPTURE_TEST
int daph_capture_replay_test_zeroed(void)
{
    const uint8_t *bytes = (const uint8_t *)&replay;
    uint8_t diff = 0u;
    size_t i;
    for (i = 0u; i < sizeof replay; i++) diff |= bytes[i];
    return diff == 0u && active == 0;
}
#endif
