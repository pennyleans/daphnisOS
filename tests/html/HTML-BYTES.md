# native html byte pipeline

`user/ci/web/sniff.ci` chooses an initial encoding for a fresh navigation:
BOM (source 1), transport (2), bounded HTML prescan (3), fallback (4).
unknown fallback identifiers select windows-1252. the decoder API and identifiers
remain those in `ENCODING.md`. no input views are retained.

the prescan follows the pinned HTML source in
`vendor/whatwg-html/sniff-source`, with provenance in `SNIFF-SOURCE.json`.
all byte reads are confined to the first 1024 bytes. attribute parsing is the
prescan algorithm, including generic tags, quoted delimiters, duplicate names,
pragma/content ordering and case folding. initial UTF-16 XML byte patterns and
the final XML-declaration compatibility fallback follow that same algorithm.
this does not parse XML as HTML. meta declarations adjust UTF-16 to UTF-8 and
x-user-defined to windows-1252; transport and fallback do not apply those meta
adjustments. XML fallback applies only its specified UTF-16 adjustment.

`sniff_cases.py` retains independent expected selections and complete serialized
token values. `sniff_driver.ci` checks ordinary and offset/strided prefix views.
`byte_token_driver.ci` decodes complete and chunked byte views into caller-owned
scalar storage, then passes that view directly to the native tokenizer. every
short fixture split and two strides are tested. the declared destination capacity
is checked before each store; -4 reports exhaustion and no token stream is emitted.
this is a fixture pipeline, not a new retained streaming tokenizer interface.

original html5lib encoding fixtures at
`c5495c539ca8a79c3c5107f5f14010bcff9a35d5` live unchanged in `corpus/sniff/`.
`SOURCE.json` pins their bytes and license. all 82 source cases retain identities:
75 are direct initial-choice projections (encoding expectation only, since the
originals specify no selection-source value); seven tests1.dat cases 47-53 (zero-based)
expect late declarations outside the 1024-byte API and are explicitly excluded
from this initial-choice comparison. original data and expectations are unchanged.
heuristic chardet and scripted directories are not projected: this API has no
heuristic detector, inherited context, prior-visit hints or executed script.
later meta reparsing and navigation confidence belong to future tree building.
these tests do not qualify trees, a browser or Gmail.

run outside the repository:

```sh
python3 -B tools/html/check-html-bytes.py --out BUILD/html-bytes \
  --cint CINT --toolchain TOOLCHAIN
python3 -B tests/html/test_compiler_identity.py
python3 -B tests/html/test_html_wrapper.py
python3 -B tests/html/test_sniff_provenance.py
python3 -B tests/html/test_tokenizer_inventory.py
python3 -B tests/html/test_sniff_inventory.py
python3 -B tests/html/test_relative_compiler.py
```

both native suites compile actual CINT with GCC and Clang, portable C17 helpers,
warnings as errors, and repeat each batch twice with exact output-byte equality.
receipts retain each case, original/source hashes, compiler bytes, bootstrap,
version source identity, toolchain, emitted C sizes and native binary hashes.

`check-encoding.py` and `check-html-bytes.py` default to the retained private
compiler profile. explicit `--compiler-source-id` and `--compiler-sha256` must be
a pair of 64 lowercase hex values. the executable hash and bootstrap/version
source identities must match. expected and observed identities are recorded.
`check-html.sh` forwards the optional pair from `CINT_EXPECTED_SOURCE_ID` and
`CINT_EXPECTED_SHA256`; partial, empty or malformed values are rejected.

the tokenizer harness retains exact equality and hashes for its original corpus.
only first-level `encoding/` and `sniff/` sibling suites are outside that inventory;
unknown siblings, nested lookalikes, missing files and changed originals reject.

the sniff corpus accepts exactly the original files declared by `SOURCE.json`
plus the explicit local `SOURCE.json` and `PROJECTION.json` metadata. unlisted
.dat files, nested unknown files and arbitrary receipts reject before case import.
both native harnesses resolve the compiler path before hashing, bootstrap/version
checks and emission; a conflicting same-basename executable on PATH cannot replace
the measured executable.
