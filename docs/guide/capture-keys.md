# Capture recovery keys

`tools/capture-key.py` creates a separate recovery-key file on a Unix host using Python 3 and the operating system CSPRNG. Choose an explicit path outside recording directories and the repository, in a private directory you trust.

```sh
python3 tools/capture-key.py create /private/path/session.key
python3 tools/capture-key.py check /private/path/session.key
```

Each creation uses fresh `os.urandom` output: 32 key bytes and 16 stream bytes. The fixed 56-byte file contains the eight-byte ASCII magic `DAPHKEY1`, then the key, then the stream. There is no seed or test-key CLI option. Commands print only status and the supplied path. They do not print recovery hex or secret bytes.

Creation is exclusive. Existing files, final symlinks, and nonregular targets are rejected without overwriting them. New files use mode `0600`; the file and containing directory are synced before success. Failed creation removes the file created by that call if the path still identifies that inode. Cleanup does not remove a replacement file. A crash or power loss during creation can leave an incomplete file; `check` rejects invalid size or magic. These are direct exclusive writes, not an atomic publication protocol.

`check` requires a regular file, no final symlink, exactly 56 bytes, the expected magic, and mode exactly `0600`. It never changes existing permissions. Python wrappers can import this tool and call `load_key(path)` to obtain the validated 56-byte payload. Callers must keep that payload out of logs, command arguments, and recordings. Checking structure and permissions cannot prove where a supplied key came from or that it has never been reused.

Parent symlinks are resolved before opening the parent directory. Subsequent operations use its directory descriptor and reject a final symlink. Use a trusted private directory; this utility does not defend against an adversary modifying that directory or the key concurrently. Keep recovery files separate from recordings and make a protected separate backup. Losing the recovery key makes its encrypted recording unrecoverable. Anyone with the key and recording can recover their contents.

This utility supports Unix permission semantics. It does not implement Windows ACL handling or a physical operating-system key loader. Existing deterministic fixtures remain synthetic. Fresh recovery-key files address host key generation only; they do not establish a complete confidential-session workflow, guest key delivery, or a release qualification.

Run the standard-library tests with:

```sh
python3 tests/capture/check_key.py
```

Tests create temporary keys outside the repository and remove them afterward.