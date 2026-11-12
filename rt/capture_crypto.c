/* Native capture key slots and failure-atomic XChaCha20-Poly1305 operations. */
#include "capture_crypto.h"
#include "../vendor/monocypher/monocypher.h"

struct capture_key_slot {
    int64_t handle;
    uint64_t sequence;
    int writer;
    uint8_t key[DAPH_CAPTURE_KEY_BYTES];
    uint8_t stream[DAPH_CAPTURE_STREAM_BYTES];
    uint8_t scratch[DAPH_CAPTURE_MAX_PLAIN];
};

#ifdef DAPH_CAPTURE_PRIVATE_HIGH
static struct capture_key_slot slots[DAPH_CAPTURE_KEY_SLOTS] __attribute__((section(".high.data")));
#else
static struct capture_key_slot slots[DAPH_CAPTURE_KEY_SLOTS];
#endif
static uint64_t next_handle = 1u;

static void copy_bytes(uint8_t *dst, const uint8_t *src, size_t n)
{
    size_t i;
    for (i = 0u; i < n; i++) dst[i] = src[i];
}

static struct capture_key_slot *find_slot(int64_t handle)
{
    unsigned i;
    if (handle <= 0) return NULL;
    for (i = 0u; i < DAPH_CAPTURE_KEY_SLOTS; i++)
        if (slots[i].handle == handle) return &slots[i];
    return NULL;
}

int64_t daph_capture_key_open(const uint8_t key[32],
                             const uint8_t stream[16], int writer)
{
    unsigned i;
    if (key == NULL || stream == NULL || (writer != 0 && writer != 1) ||
        next_handle > (uint64_t)INT64_MAX) return -1;
    for (i = 0u; i < DAPH_CAPTURE_KEY_SLOTS; i++) {
        struct capture_key_slot *s = &slots[i];
        if (s->handle != 0) continue;
        crypto_wipe(s, sizeof *s);
        copy_bytes(s->key, key, DAPH_CAPTURE_KEY_BYTES);
        copy_bytes(s->stream, stream, DAPH_CAPTURE_STREAM_BYTES);
        s->writer = writer;
        s->handle = (int64_t)next_handle;
        next_handle++;
        return s->handle;
    }
    return -1;
}

void daph_capture_key_close(int64_t handle)
{
    struct capture_key_slot *s = find_slot(handle);
    if (s != NULL) crypto_wipe(s, sizeof *s);
}

int daph_capture_key_matches(int64_t handle, const uint8_t stream[16], int writer)
{
    struct capture_key_slot *s = find_slot(handle);
    uint8_t diff = 0u;
    unsigned i;
    if (s == NULL || stream == NULL || s->writer != writer) return 0;
    for (i = 0u; i < DAPH_CAPTURE_STREAM_BYTES; i++)
        diff |= s->stream[i] ^ stream[i];
    return diff == 0u;
}

static void make_nonce(uint8_t nonce[24], const struct capture_key_slot *s,
                       uint64_t sequence)
{
    unsigned i;
    copy_bytes(nonce, s->stream, DAPH_CAPTURE_STREAM_BYTES);
    for (i = 0u; i < 8u; i++) nonce[16u + i] = (uint8_t)(sequence >> (8u * i));
}

static int valid_buffers(const uint8_t *aad, size_t aad_n,
                          const uint8_t *input, size_t n,
                          const uint8_t *output, const uint8_t *tag)
{
    return aad_n <= DAPH_CAPTURE_MAX_AAD && n <= DAPH_CAPTURE_MAX_PLAIN &&
           (aad_n == 0u || aad != NULL) &&
           (n == 0u || (input != NULL && output != NULL)) && tag != NULL;
}

static int overlap(const uint8_t *a, size_t an, const uint8_t *b, size_t bn)
{
    uintptr_t av = (uintptr_t)a, bv = (uintptr_t)b;
    if (an == 0u || bn == 0u) return 0;
    /* Subtraction avoids wrapping end addresses. */
    return av <= bv ? bv - av < an : av - bv < bn;
}

int daph_capture_seal(int64_t handle, uint64_t sequence,
                      const uint8_t *aad, size_t aad_n,
                      const uint8_t *plain, size_t n,
                      uint8_t *cipher, uint8_t tag[16])
{
    struct capture_key_slot *s = find_slot(handle);
    uint8_t nonce[24], staged_tag[DAPH_CAPTURE_TAG_BYTES];
    if (s == NULL || s->writer != 1 || sequence == UINT64_MAX ||
        sequence != s->sequence || !valid_buffers(aad, aad_n, plain, n, cipher, tag) ||
        overlap(cipher, n, tag, DAPH_CAPTURE_TAG_BYTES)) return -1;
    make_nonce(nonce, s, sequence);
    crypto_aead_lock(s->scratch, staged_tag, s->key, nonce, aad, aad_n, plain, n);
    copy_bytes(cipher, s->scratch, n);
    copy_bytes(tag, staged_tag, DAPH_CAPTURE_TAG_BYTES);
    s->sequence++;
    crypto_wipe(s->scratch, sizeof s->scratch);
    crypto_wipe(staged_tag, sizeof staged_tag);
    crypto_wipe(nonce, sizeof nonce);
    return 0;
}

int daph_capture_open(int64_t handle, uint64_t sequence,
                      const uint8_t *aad, size_t aad_n,
                      const uint8_t *cipher, size_t n,
                      const uint8_t tag[16], uint8_t *plain)
{
    struct capture_key_slot *s = find_slot(handle);
    uint8_t nonce[24];
    int result;
    if (s == NULL || s->writer != 0 ||
        !valid_buffers(aad, aad_n, cipher, n, plain, tag)) return -1;
    make_nonce(nonce, s, sequence);
    result = crypto_aead_unlock(s->scratch, tag, s->key, nonce, aad, aad_n, cipher, n);
    if (result == 0) copy_bytes(plain, s->scratch, n);
    crypto_wipe(s->scratch, sizeof s->scratch);
    crypto_wipe(nonce, sizeof nonce);
    return result == 0 ? 0 : -1;
}

#ifdef DAPH_CAPTURE_TEST
int daph_capture_test_zeroed(unsigned index)
{
    const uint8_t *bytes;
    size_t i;
    uint8_t diff = 0u;
    if (index >= DAPH_CAPTURE_KEY_SLOTS) return 0;
    bytes = (const uint8_t *)&slots[index];
    for (i = 0u; i < sizeof slots[index]; i++) diff |= bytes[i];
    return diff == 0u;
}

int daph_capture_test_counter(int64_t handle, uint64_t sequence)
{
    struct capture_key_slot *s = find_slot(handle);
    if (s == NULL || s->writer != 1) return -1;
    s->sequence = sequence;
    return 0;
}
#endif
