# native html tokenizer

`user/ci/web/tokenizer.ci` implements the code-point pull interface in
`docs/specs/2026-11-09-html-input.md`. it uses the native reference resolver.
the host fixture only transports integer code points and serialized token fields;
python compiles, transports and compares independent expectations.

the normative source is whatwg/html at
`5fcc2318395821db61e353705e6368ad9a000af5`, including its processing-instruction
states. html5lib/html5lib-tests is pinned at
`c5495c539ca8a79c3c5107f5f14010bcff9a35d5`. the original test files, readme and
license are under `corpus/`. `corpus/SOURCE.json` binds each imported file's bytes
and sha256. the harness verifies that complete inventory before compilation.

the html5lib suite requests 7046 tokenizer runs across data, rcdata, rawtext,
script data, plaintext and cdata initial states. every requested state and
last-start-tag context runs. the four `xmlViolation.test` cases test downstream
dom infoset coercion and are explicitly skipped, with case identities and input
and expected hashes in each receipt. no tokenizer vectors are filtered.

current processing-instruction expectations come from wpt commit
`45337b80082d8987761d04fd2a406dcb3c48f4c5`, file
`html/syntax/parsing/resources/processing-instructions.dat`. the original file and
license are retained. cases 0 through 106 have an explicit body start tag and
simple tree outputs that project to tokenizer values: pi target/data, bogus
comments, text and a span start tag. the harness compares those 107 projections.
cases 107 through 123 need tree placement or a tree-selected text mode. they are
explicitly skipped in this projection, with input and document-expectation hashes.
the tokenizer-only raw-text modes are independently exercised by html5lib and
local fixtures. this does not qualify wpt tree construction.

`tokenizer_adversarial.py` contains explicit capacity and malformed-input
expectations. it includes processing-instruction eof/null recovery, script
double-escape transitions and escaped eof, crlf, references, duplicates, end-tag
attributes and self-closing flags, long chunked text, cdata admission, scalar
handling, invalid modes and reset after terminal refusal. the driver checks
that repeated eof/refusal calls preserve the terminal kind, errors and reason.
all cases share one context per process and reset between cases; each complete
batch runs twice per compiler and must produce identical bytes.

`select_mode(mode, allow_cdata)` changes the active initial state between tokens
without resetting the input cursor, error count, remembered start tag or exposed
token. local integration fixtures select rcdata after a title start tag, script
data after a script start tag, and toggle foreign cdata admission midstream.
an invalid mode causes terminal refusal with reason 1. selection after eof or
refusal returns false without changing terminal state. every token also checks
negative and upper-bound accessor indices. a separate fixture checks attribute
order after a duplicate name.

## input and limits

input is one immutable code-point view across `next` calls. cr and crlf normalize
to lf. surrogate code points remain present with an input parse error, matching
html preprocessing and the corpus. values above u+10ffff deterministically become
u+fffd with an input parse error. noncharacters and prohibited controls increment
the input error count. null handling depends on the tokenizer state. byte
decoding and encoding detection precede this separate code-point interface.

character tokens contain one or two code points; comparison concatenates adjacent
character tokens. tag, doctype and pi names have capacity 1024. comments and pi
data have capacity 65536. public and system identifiers each have capacity 65536.
attributes have capacity 128 and use a shared 65536-code-point arena for names
and values, including the currently parsed duplicate. completed duplicate storage
is reclaimed and the first value remains present.

`limit_reason()` returns 0 normally, 1 for an invalid reset mode, 2 for name/last
tag capacity, 3 for comment/pi data capacity, 4 for attribute count, 5 for
attribute arena capacity, and 6 for public/system identifier capacity. any refusal
returns -1 and remains terminal until reset. boundary fixtures test exact capacity
and one point beyond for every storage class. no token is silently truncated.
out-of-range accessor indices return zero.

`errors()` is cumulative since reset. local diagnostic fixtures check selected
counts. html5lib parse-error codes, locations and full diagnostic correspondence
are not claimed. same-process interleaving of separate runtime contexts is not
qualified by this driver. dom construction, rendering, scripts, browser session
integration and gmail acceptance remain separate units.

## reproduce

run from the repository root, with all artifacts outside the repository:

```sh
python3 tools/html/check-tokenizer.py \
  --out OUT/tokenizer \
  --cint CINT_DIR/cint \
  --toolchain CINT_DIR/cint.toolchain
```

`OUT` is a fresh output directory outside the checkout. `CINT_DIR` holds the cint under test and its
`cint.toolchain`.

the harness emits once using the actual cint compiler, then compiles emitted c
and the hosted runtime on gcc and clang. the receipt records source hashes,
compiler source and executable identities, bootstrap/toolchain/runtime hashes,
binary sizes/hashes, every case identity and expectation hash, explicit skipped
cases, per-suite totals, expected capacity refusals and unexpected failures.
`--only` selects a diagnostic subset and records that selection; its receipt is
not a complete-suite qualification. `--reuse-emitted` is diagnostic only because
it reuses the already emitted program.

the first corpus run exposed four surrogate-policy mismatches. that failed
receipt is preserved separately; the policy was corrected to preserve surrogate
code points before the passing qualification. review then identified raw-text
end-tag recognition accepting non-letter fragment names. the review's 12 failing
probes and source identity are retained in
`receipts/tokenizer-raw-end-first-failure.json`; the same 12 cases now guard the
ascii-letter-only end-tag-name rule in rcdata, rawtext and script modes.
