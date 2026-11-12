# Bounded capture and replay

`tools/capture-run.py` records encrypted serial output from a capture-qualified
Daphnis image, or supplies an existing encrypted recording to its native replay
reader. It runs QEMU TCG on a Unix host with `/proc/self/fd`, Python 3, `nm` and
`qemu-system-x86_64`. The image must expose the capture boot, sink and replay
boundary symbols. This check excludes ordinary development images; it is not a
code audit or attestation of an arbitrary image.

Use trusted private directories outside the repository. Each direct parent must
belong to the current uid and deny group and other access. Existing parent
symlinks resolve before path separation checks. Final symlinks, FIFOs, existing
output paths, overlapping session/recovery paths and input/output aliases are
refused. Input sessions use mode `0700`; their manifest, capture and separate
recovery file use mode `0600`. Kernel and optional initrd remain separate and
unchanged. Their descriptors are opened read-only, hashed and checked for changes.

```sh
mkdir -m 700 /private/path/sessions /private/path/recovery
python3 tools/capture-run.py record \
  --kernel /qualified/kernel32.elf --initrd /qualified/session.cpio \
  --output /private/path/sessions/first \
  --key /private/path/recovery/first.key \
  --network user --timeout 60

python3 tools/capture-run.py replay \
  --kernel /qualified/kernel32.elf --initrd /qualified/session.cpio \
  --input /private/path/sessions/first \
  --input-key /private/path/recovery/first.key \
  --output /private/path/sessions/second \
  --key /private/path/recovery/second.key --timeout 60
```

Omit `--initrd` when the image needs none. Recording defaults to `--network none`;
`user` selects QEMU user networking with `virtio-net-pci`. Record uses CPU `max`
for the native live RDRAND path. Replay always has no NIC, disables RDRAND and
RDSEED, and accepts no networking override. Both use a headless display, no
monitor, closed stdin, the debug-exit device, 128 MiB and TCG. `--qemu` selects an
executable; no extra QEMU arguments or shell command are accepted. Timeout defaults
to 30 seconds and must be positive and at most 3600 seconds. Capture output is
limited to 16 MiB and QEMU diagnostics to 1 MiB.

## Files and recovery

A run exclusively creates its mode-`0700` session directory, `capture.cr1` and
`manifest.json`. Artifacts use mode `0600`. It calls
[`capture-key.py`](../../tools/capture-key.py) to create a fresh external recovery
file for every run, including replay. Keys and stream identifiers use OS
randomness. Replay refuses an output key equal to the input key. See the
[recovery-file guide](capture-keys.md) for separate backups and loss consequences.

Recovery contents never enter command arguments, environment variables, initrd,
recording files or logs. QEMU receives read-only regular-file descriptors through
fixed `/proc/self/fd/N` paths. User paths containing commas or key/value text cannot
inject firmware options. Key bytes exist in the launcher and QEMU address spaces;
this workflow makes no host memory-erasure promise.

The launcher buffers serial bytes until the complete CR-1 header is valid and its
stream matches the fresh recovery file. Plaintext or a short header creates no
capture bytes. Once the header qualifies, partial encrypted output is preserved.
QEMU stderr is counted and hashed; its raw text is neither recorded nor printed.
The launcher does not decrypt or unpack journals.

The manifest binds the kernel SHA-256, optional initrd SHA-256, capture SHA-256,
stream identifier, CINT program revision, timeout and actual subprocess exit state.
Replay adds the input capture SHA-256. A visible header identity is retained even
for an incomplete recording. A refused header leaves these fields null.

A complete structurally valid envelope and debug-exit status 33 produce
`status: recorded`, `guest_outcome: success` and CLI exit 0. A complete encrypted
explicit fault with status 35 produces `status: recorded`, `guest_outcome: fault`
and CLI exit 1; it remains replayable for diagnosis. The printed result is
`recorded-fault`. Other exits, timeout, cancellation, malformed/trailing frames,
missing final frames or host failures produce `status: failed` and CLI exit 1.
Timeout and interruption kill and reap QEMU and retain its resulting exit state.

Failed sessions retain their partial capture, failed manifest and any completed
recovery file. Existing input and destination files are never deleted or
rewritten. The key utility can remove its own incomplete creation if key creation
itself fails. A crash can leave an unfinished artifact or initial failed manifest;
this is not an atomic publication protocol. Directory and artifact syncs accompany
normal finalization.

## Authentication boundary

Host framing and hash checks are structural checks, not authentication. The
manifest says `not independently authenticated` for output. It is unsigned and
protects against accidental mismatch, not a hostile host editing both a file and
its digest.

Replay requires a replayable input manifest, matching capture/hash/header fields,
a matching recovery stream, and exactly the original kernel and initrd identities.
The unchanged native kernel authenticates the complete source, typed input
structure, final frame and expected program revision before emitting output or
starting the application. A structurally valid but tampered source with a recomputed
manifest hash still reaches that authenticator and is refused without serial
output. Successful record status alone does not establish authenticated recovery;
replay or independent test authentication supplies that evidence.

Only trusted immutable inputs and trusted private parent directories are supported.
The launcher checks descriptor identity and modification metadata after execution;
it does not defend against a hostile uid, host, hypervisor or concurrent writer.
Physical key loading, encrypted snapshots and persistent outputs, browser session
integration, origin/account isolation and Gmail operation remain unfinished. This
launcher does not qualify a production confidential session.

## Synthetic checks

```sh
python3 -B tests/capture/check_run.py --out /private/test-results
python3 -B tests/capture/check_run.py --out /private/test-results \
  --guest-images /qualified/final-capture/encrypted
```

The standard-library unit tests use temporary synthetic files and a subprocess
fixture. Optional guest checks use the existing GCC and Clang hello, fault and net
images, fresh synthetic recovery files, local DNS/HTTPS fixtures, and independent
libsodium authentication in memory. They check offline replay with the fixture
servers stopped, typed input equality, console equality except established mode
lines, key/RNG absence, and refusal of rehashed tampered ciphertext. They retain
private guest sessions and a hash-bound receipt outside the repository. No
plaintext journal or recovered console file is written.