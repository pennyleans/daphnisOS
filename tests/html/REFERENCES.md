# Native character references

`user/ci/web/reference.ci` implements the code-point resolver described in
`docs/specs/2026-11-09-html-input.md`. It has no host parser calls, mutable module
state, floating-point operations or output buffer. The returned record holds at
most two Unicode points.

The generator pins the exact WHATWG `entities.json` bytes under
`vendor/whatwg-html`. That directory retains source URLs, SHA-256 identities,
attribution and the original license. The generated module stores sorted names,
16-bit byte offsets, byte lengths and pairs of 24-bit output points. A binary
search narrows the remaining sorted prefix range at each input point. The longest
terminal name wins. The 2,231 source keys include the 106 legacy keys without
semicolons. Generation is deterministic and `--check` detects drift.

Numeric accumulation saturates at 0x110000 while still consuming every digit.
There is no numeric digit limit or input-length refusal in the resolver.
Invalid starting indices produce an empty result. Unknown alphanumeric names
ending in a semicolon return error bit 128 with zero consumption; rejected legacy
attribute matches return zero consumption with no error. A numeric prefix without
digits returns bit 1 with zero consumption. The caller emits the literal ampersand
for every zero-consumption result.

Run from the checkout with the qualified compiler and an output directory outside
the checkout:

```sh
python3 tools/html/generate_references.py --check
python3 tests/html/run_references.py \
  --out OUT/references \
  --cint CINT_DIR/cint \
  --toolchain CINT_DIR/cint.toolchain
```

`OUT` is a fresh output directory outside the checkout. `CINT_DIR` holds the cint under test and its
`cint.toolchain`.

The test driver calls the real emitted CINT resolver. C only transports input
points and result fields. Expectations come directly from source keys and their
point lists, with separate explicit numeric, control-remapping, malformed and
index vectors. Every source key is checked in both contexts at EOF and before
punctuation, letters, equals and a second semicolon. Proper name prefixes are
checked at EOF; offset cases put the ampersand before the starting index.
Adversarial cases contain 65,536 significant or leading-zero decimal/hex digits
and an unknown name of that length. GCC and Clang each run the same full fixture
twice and retain complete transcripts, mismatch files and hashed receipts outside
the checkout. The harness provisions a 4 MiB CINT arena for its 70,000-point array
and host staging; this is test provisioning, not a resolver capacity.

This qualifies the reference resolver against the pinned table and listed
vectors. It does not establish tokenizer, HTML tree-builder, rendering or browser
conformance. Parse-error positions are outside this API.
