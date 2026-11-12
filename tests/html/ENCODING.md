# native web decoders

`user/ci/web/encoding.ci` implements all 40 pinned WHATWG decoders in native CINT.
`encoding_data.ci` contains immutable packed three-byte code points and alias bytes.
`vendor/whatwg-encoding/generated-metadata.json` lists each one-based identifier,
canonical name, all 228 labels and table coverage. `SOURCE.json` binds original
standard/data/license hashes and the WPT pin. no browser decoder uses a host codec.

`label` trims only ASCII tab, LF, FF, CR and space, folds ASCII case and returns
zero for unknown labels. replacement and x-user-defined remain valid labels.
`reset` clears every state and counter, returning false and entering terminal -2
for an invalid identifier. mutable fields live in private CINT context state.

`next(input, final)` accepts bytes from any rank-one byte view. `Step.used` counts
newly accepted bytes; `Step.value` is a scalar, -3 for non-final exhaustion, -1
for terminal EOF or -2 for terminal fatal error. output can use zero new bytes.
the caller removes `used` bytes and supplies the remaining view on its next call.
final exhaustion flushes errors. terminal calls always accept zero bytes.
`position()` counts accepted bytes exactly once. `errors()` counts decoder errors,
including errors that become terminal in fatal mode; literal U+FFFD is not an error.

three replay bytes suffice: the longest restore is gb18030's second, third and
current byte. UTF-16 restores two bytes, Japanese handlers at most two and other
handlers at most one. one pending scalar serves Big5's two-point mappings.
no input view is retained and no state grows with input length. BOM serialization
suppresses only an initial U+FEFF in UTF-8/UTF-16 when ignore_bom is false.

run from the repository root:

```sh
python3 -B tools/html/check-encoding.py \
  --out OUT/encoding/final \
  --cint CINT_DIR/cint \
  --toolchain CINT_DIR/cint.toolchain
```

`OUT` is a fresh output directory. `CINT_DIR` holds the cint under test and its
`cint.toolchain`.

`--node` selects the supplemental Node executable. the default is the existing
Windows Node at `/mnt/c/Program Files/nodejs/node.exe`. its version, ICU version,
executable hash, unsupported cases and every disagreement are retained. primary
expectations never come from Node or the implementation under test. the protocol
checks astral scalars and fatal-prefix retention, plus serialization of all four
two-output scalar pairs independently of Node mapping conformance. Big5 mapping
differences remain conformance disagreements.

primary tests cover every alias, embedded NUL at five positions for every alias, all 256 bytes for each single-byte decoder,
every mapped multibyte table cell reachable by the standard, all structurally
valid null cells, Shift_JIS EUDC, gb18030 range boundaries and explicit malformed,
fatal, EOF, replay, Unicode scalar and BOM cases. selected short vectors run at
every split point, including empty chunks; byte views have nonzero offsets and
strides one and two. long multilingual UTF-8 runs use widths 1, 3, 7, 64, 4096 and
65536. the CINT driver asserts terminal stability, scalar validity, exact view
consumption bounds, counters and resets, including reset with pending input/output.

340 original encoding WPT files are retained at the specified pin. 170 static
independent vectors from two files are projected into native split cases.
the GBK file inspected by the normalizer contains no static decode calls; its
dynamic pointer loop is inventoried separately.
`corpus/encoding/wpt-cases.json` identifies the original file and decode-call
ordinal. `wpt-inventory.json` gives each imported file's projection status and
reason. this is not execution of the entire browser WPT API or navigation suite.
`generate_encodings.py --check` verifies original hashes, regenerated tables and
regenerated WPT normalization, so editing original fixtures or expectations drifts.

build artifacts remain outside the repository. both GCC and Clang compile emitted
C17 with warnings as errors and portable runtime helpers. complete batches run
twice and every output byte must match across all four runs. a compressed complete
case inventory and hashes, tool identities, source hashes, output hashes, binary
sizes and supplemental discrepancies are retained in the build directory.

fixture bounds are explicit: at most 65,536 bytes per case, a 131,080-byte input
arena supporting offset/stride-two views, 256 label bytes, 520 strided label bytes,
a 131,080-scalar reporting buffer and a 4 MiB CINT frame arena. overflow asserts;
no destination truncation is accepted. these are driver capacities, not decoder
input-length limits. no production decoder test or implementation calls a host codec.
