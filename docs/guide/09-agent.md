# 09 Claude in a terminal (`talk`, `agent`)

An app a person starts, never part of the base image and never running in the background (AG-1 A, FOUNDING law 3).

| program | what it does |
| --- | --- |
| `talk` | a line client: sends each line to `tools/claudebridge.py` on the host, which runs Claude Code headless there. Claude's tools act on the host, not on Daphnis. |
| `agent` | a native client of the Messages API, written in cint: DNS, TLS 1.2 (BearSSL), streaming. Its tools (`sh`, `read_file`, `write_file`, ...) act on Daphnis, and each call runs only after `y`. |

## `talk` (the bridge)

```
tools/run-desk-agent.sh          # FAKE=1 uses a fake bridge; nothing leaves the host
```

In the desk's terminal:

```
./grant net ./talk 10.0.2.2 7070
```

Type a line at each `> `. Ctrl+D or `exit` ends `talk`.

## `agent` (live)

```
ANTHROPIC_API_KEY=... tools/run-agent-live.sh       # MODEL=... picks the model id
```

The script writes the key and model id to a small ext2 volume (mode 0600, removed when QEMU exits). In the desk's
terminal:

```
./grant net ./agent -k /disk/agent.key -t -x api.anthropic.com 443
```

Each tool call is shown and runs only on `y`. Ctrl+D ends it.

## Read this first

- The serial transcript journals every received frame and every random draw, so it can decrypt the whole session,
  the key included. It stays on the host, mode 0600. Never share it.
- `-cpu max` (the scripts pass it) gives the guest RDRAND; without it `agent` opens no TLS session.
- 37 public roots ship in `user/tls/roots/public.pem` (from Ubuntu 24.04's ca-certificates).

Checked by `check-agent.sh` (33 checks, mocks only: the bridge, plain HTTP, DNS, TLS against a test certificate, a
six-call tool session).
