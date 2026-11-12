#ifndef DAPH_CAPTURE_CRYPTO_H
#define DAPH_CAPTURE_CRYPTO_H

#include <stddef.h>
#include <stdint.h>

#define DAPH_CAPTURE_KEY_BYTES 32u
#define DAPH_CAPTURE_STREAM_BYTES 16u
#define DAPH_CAPTURE_TAG_BYTES 16u
#define DAPH_CAPTURE_MAX_PLAIN 4096u
#define DAPH_CAPTURE_MAX_AAD 96u
#define DAPH_CAPTURE_KEY_SLOTS 4u

/* Native private control only. No key import is exported to cint.
 * Calls must be serialized. Each new writer requires a fresh key and stream;
 * this leaf does not provision keys or establish uniqueness across boots. */
int64_t daph_capture_key_open(const uint8_t key[32],
                             const uint8_t stream[16], int writer);
void daph_capture_key_close(int64_t slot);
int daph_capture_key_matches(int64_t slot, const uint8_t stream[16], int writer);

/* We bind nonce = stream || sequence in little endian. Writers start at zero
 * and consume exactly one sequence on success; UINT64_MAX is never sealed.
 * Readers leave sequence policy to the authenticated framing state machine.
 * Returns 0 on success, -1 on failure with all output bytes unchanged.
 * Input/output buffers may alias, except the seal cipher and tag outputs.
 * Null data pointers are allowed only for a zero corresponding length. */
int daph_capture_seal(int64_t slot, uint64_t sequence,
                      const uint8_t *aad, size_t aad_n,
                      const uint8_t *plain, size_t n,
                      uint8_t *cipher, uint8_t tag[16]);
int daph_capture_open(int64_t slot, uint64_t sequence,
                      const uint8_t *aad, size_t aad_n,
                      const uint8_t *cipher, size_t n,
                      const uint8_t tag[16], uint8_t *plain);

#ifdef DAPH_CAPTURE_TEST
/* Synthetic tests can inspect erasure and reach an otherwise impractical edge. */
int daph_capture_test_zeroed(unsigned index);
int daph_capture_test_counter(int64_t slot, uint64_t sequence);
#endif

#endif
