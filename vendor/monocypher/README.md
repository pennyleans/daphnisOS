# monocypher 4.0.3

`monocypher.c`, `monocypher.h`, and `LICENCE.md` are byte-for-byte copies from
the [official 4.0.3 archive](https://monocypher.org/download/monocypher-4.0.3.tar.gz).
`capture.pin` records the archive URL, its SHA-256, its verified
[upstream SHA-512](https://monocypher.org/download/monocypher-4.0.3.tar.gz.sha512),
and the vendored file SHA-256 values. The upstream dual BSD-2-Clause / CC0
license and source notices are preserved without changes.

The capture leaf uses only `crypto_aead_lock`, `crypto_aead_unlock`, and
`crypto_wipe`. The full unmodified portable source is retained for provenance.
It supplies XChaCha20-Poly1305 with a 32-byte key and 24-byte nonce.

The [Cure53 audit](https://monocypher.org/quality-assurance/audit) covered
version 3.1.1 in June 2020. It does not establish an audit of version 4.0.3,
the capture wrapper, its framing, key provisioning, or deployment.
The [upstream changelog](https://monocypher.org/changelog) records changes
after that audit, including the 4.0.0 AEAD API and the 4.0.2 Poly1305 changes.
Version 4.0.3 also fixes a signature timing leak in code the capture leaf does
not call. We do not claim that the changed implementation is covered by the
2020 audit.

`tests/capture/check_crypto.py` compares deterministic synthetic records with
the installed libsodium XChaCha20-Poly1305 implementation. It also checks
failure atomicity, native slot lifecycle, writer counters, and freestanding
gcc/clang objects. These checks do not establish production key provisioning
or nonce uniqueness across different writer handles or boots. Each new
writer needs a fresh key and stream supplied outside cint and recordings.
