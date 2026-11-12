#!/usr/bin/env python3
"""tools/claudebridge.py: the host end of the day-one bridge (docs/specs/2026-11-06-a-agent.md, A-0).

  claudebridge.py [--fake] [--port N] [--seconds S] [-- CLAUDE_ARG...]

Listens on 127.0.0.1:N (default 7070; the guest's 10.0.2.2:N on QEMU's user network) and serves one
connection of `talk` (user/ci/talk.ci), then exits. Each line `talk` sends is one user turn; the reply goes back
as ASCII lines (the desk's face has 95 glyphs), a line that starts with "." doubled, and a line holding only "."
after it. Prints `claudebridge: listening on 127.0.0.1:N` when ready and one `claudebridge: turn K, ...` line a
turn.

Without --fake, one headless Claude Code process runs for the connection:
  claude -p --input-format stream-json --output-format stream-json --verbose CLAUDE_ARG...
Its text streams back line by line as it arrives; a tool call shows as `[tool NAME]`. Claude Code runs here, on
the host, with this host's login and permissions: its tools act on the host, never on Daphnis. Headless, a tool
that needs permission is refused unless CLAUDE_ARG allows it.

With --fake no process runs and nothing leaves the host: each turn's reply is a fixed function of the line, so
the gate (check-agent.sh) and a Linux run of `talk` print the same bytes. --seconds ends the wait for the
connection (default 0, no limit).
"""
import hashlib
import json
import socket
import subprocess
import sys

ASCII = {
    "\u2014": "-", "\u2013": "-", "\u2212": "-", "\u2010": "-", "\u2011": "-",
    "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
    "\u2026": "...", "\u2022": "*", "\u00b7": "*", "\u2192": "->", "\u2190": "<-",
    "\u00a0": " ", "\u2002": " ", "\u2003": " ", "\u2009": " ", "\u2713": "v", "\u2717": "x",
}


def ascii_line(s):
    out = []
    for ch in s:
        o = ord(ch)
        if ch == "\t" or 32 <= o < 127:
            out.append(ch)
        elif ch in ASCII:
            out.append(ASCII[ch])
        elif o >= 32:
            out.append("?")
    return "".join(out)


class Conn:
    def __init__(self, sock):
        self.sock = sock
        self.rest = b""

    def line(self):
        """The next line from talk, without its newline; None at the end."""
        while b"\n" not in self.rest:
            got = self.sock.recv(4096)
            if not got:
                return None
            self.rest += got
        line, self.rest = self.rest.split(b"\n", 1)
        return line.decode("utf-8", "replace").rstrip("\r")

    def send(self, text):
        text = ascii_line(text)
        if text.startswith("."):
            text = "." + text
        self.sock.sendall(text.encode("ascii") + b"\n")

    def end(self):
        self.sock.sendall(b".\n")


def fake_turn(conn, k, line):
    digest = hashlib.sha256(line.encode("utf-8")).hexdigest()[:16]
    conn.send(f"fake model, turn {k}: you said {len(line.encode('utf-8'))} bytes, sha256 {digest}...")
    conn.send(f"you said: {line}")
    conn.send(".a line that starts with a dot")
    conn.send(".")
    conn.send("\u2014 the end of turn \u2026")
    conn.end()


class Claude:
    def __init__(self, extra):
        cmd = ["claude", "-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose", *extra]
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)

    def turn(self, conn, line):
        msg = {"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": line}]}}
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()
        pending = ""
        streamed = False
        for raw in self.proc.stdout:
            try:
                ev = json.loads(raw)
            except ValueError:
                continue
            kind = ev.get("type")
            if kind == "stream_event":
                e = ev.get("event", {})
                if e.get("type") == "content_block_delta" and e.get("delta", {}).get("type") == "text_delta":
                    streamed = True
                    pending += e["delta"].get("text", "")
                    while "\n" in pending:
                        one, pending = pending.split("\n", 1)
                        conn.send(one)
                elif e.get("type") == "content_block_stop" and pending:
                    conn.send(pending)
                    pending = ""
            elif kind == "assistant":
                for block in ev.get("message", {}).get("content", []):
                    if block.get("type") == "tool_use":
                        conn.send(f"[tool {block.get('name', '?')}]")
                    elif block.get("type") == "text" and not streamed:
                        for one in block.get("text", "").split("\n"):
                            conn.send(one)
            elif kind == "result":
                if pending:
                    conn.send(pending)
                if ev.get("is_error"):
                    conn.send(f"[error: {ev.get('subtype', 'unknown')}]")
                conn.end()
                return True
        conn.send("[claude ended]")
        conn.end()
        return False

    def close(self):
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            self.proc.kill()


def main(argv):
    fake, port, seconds, extra = False, 7070, 0, []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--":
            extra = argv[i + 1:]
            break
        if a == "--fake":
            fake = True
        elif a == "--port" and i + 1 < len(argv):
            i += 1
            port = int(argv[i])
        elif a == "--seconds" and i + 1 < len(argv):
            i += 1
            seconds = int(argv[i])
        else:
            print(__doc__.strip(), file=sys.stderr)
            return 2
        i += 1
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", port))
    srv.listen(1)
    if seconds:
        srv.settimeout(seconds)
    print(f"claudebridge: listening on 127.0.0.1:{port}{' (fake)' if fake else ''}", flush=True)
    try:
        sock, _ = srv.accept()
    except socket.timeout:
        print("claudebridge: no connection", flush=True)
        return 1
    srv.close()
    sock.settimeout(None)
    conn = Conn(sock)
    claude = None if fake else Claude(extra)
    k = 0
    while True:
        line = conn.line()
        if line is None:
            break
        k += 1
        if fake:
            fake_turn(conn, k, line)
        elif not claude.turn(conn, line):
            break
        print(f"claudebridge: turn {k}, {len(line.encode('utf-8'))} bytes in", flush=True)
    if claude:
        claude.close()
    sock.close()
    print(f"claudebridge: {k} turns, connection closed", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
