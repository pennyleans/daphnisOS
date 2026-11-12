#!/usr/bin/env python3
"""tools/apihost.py: the mock Messages API of stage A's gate (docs/specs/2026-11-06-a-agent.md, A-1).

  apihost.py [--port N] [--turns K] [--seconds S] [--big] [--dns PORT --answer A.B.C.D] [--cert PEM --key PEM]

Serves K connections (default 2) on 127.0.0.1:N (default 8080; the guest's 10.0.2.2:N), one request each, then
exits. Each request must be what the agent sends: `POST /v1/messages`, an `anthropic-version` and an
`x-api-key` header, `content-length`, a JSON body with `stream: true` and messages that alternate user and
assistant and end with a user turn. A request that is not answers HTTP 400 with an API error body, which the
agent prints. A good one answers HTTP 200, `transfer-encoding: chunked`, with the event stream of a streamed
Messages response (message_start, content_block_start, ping, content_block_delta per piece, content_block_stop,
message_delta, message_stop) whose text is a fixed function of the conversation: the turn's number, the count of
messages, the SHA-256 of the last line, the line itself, then a line of escapes (a quote, a backslash, a tab, an
e with an accent, a snowman, a face outside the basic plane). Half the deltas carry their non-ASCII as \\u escapes
(a surrogate pair for the face), half as raw UTF-8, and the chunks cut events, lines and characters at fixed odd
places. --big adds 64 KiB of text to every reply, to measure the stream.

With --dns it also answers DNS over UDP on 127.0.0.1:PORT (A-2): an A query for `api.mock` gets a CNAME to
`edge.mock` and then edge.mock's A record, A.B.C.D (the guest's 10.0.2.2, or 127.0.0.1 for the Linux run), both
names compressed; any other name gets NXDOMAIN. One line per query.

With --cert and --key it speaks TLS 1.2 only (A-4) with that certificate (tests/tls/: api.mock.pem by the mock root,
expired.pem out of its dates, stranger.pem by a root the agent does not hold) and ends each connection with
close_notify both ways; a handshake that fails is one line, `apihost: request N, tls: REASON`, and counts as a turn.

A request with `tools` (agent -x, A-5) must offer sh, read_file, write_file and edit_file, and every tool_result must
answer the tool_use before it, id for id. The first user line then gets a fixed script of calls, one a reply: sh,
write_file, edit_file and read_file on note.txt, a write_file of refused.txt (the gate answers n), and sh removing
note.txt; then a reply that lists each result's status, digest and text. Any later line gets the plain reply.

Prints `apihost: listening on 127.0.0.1:N` when ready and, per request, its size and digest, the reply's size,
and the seconds from the request's first byte to the connection's close (for the measure; not in any golden).
"""
import hashlib
import json
import socket
import ssl
import struct
import sys
import threading
import time

ESCAPES = "escapes: \"quote\" back\\slash\ttab caf\u00e9 \u2603 \U0001F600"


def reply_text(n, body, big):
    msgs = body["messages"]
    last = msgs[-1]["content"]
    digest = hashlib.sha256(last.encode("utf-8")).hexdigest()[:16]
    t = f"mock turn {n}: {len(msgs)} messages, last {digest}\nyou said: {last}\n{ESCAPES}"
    if big:
        t += "\n" + "".join(f"line {i:05d} " + "abcdefghij" * 6 + "\n" for i in range(64 * 1024 // 78 + 1))
    return t


SCRIPT = [
    ("sh", {"command": "echo hello from sh; echo $((6 * 7))"}),
    ("write_file", {"path": "note.txt", "content": "Daphnis note\nline two\n"}),
    ("edit_file", {"path": "note.txt", "old_string": "line two", "new_string": "line 2, edited"}),
    ("read_file", {"path": "note.txt"}),
    ("write_file", {"path": "refused.txt", "content": "never written\n"}),
    ("sh", {"command": "rm note.txt && echo removed; test -e refused.txt || echo no refused.txt"}),
]
TOOLS = ["sh", "read_file", "write_file", "edit_file"]


def tool_reply(n, msgs):
    """(text, calls) for a request with tools, or None for the plain reply."""
    last = max(i for i, m in enumerate(msgs) if m["role"] == "user" and isinstance(m["content"], str))
    k = (len(msgs) - 1 - last) // 2
    if last == 0 and k < len(SCRIPT):
        name, inp = SCRIPT[k]
        return f"mock turn {n}: call {k + 1} of {len(SCRIPT)}, {name}\n", [(f"toolu_mock_{k + 1}", name, inp)]
    if k == 0:
        return None
    names = {b["id"]: b["name"] for m in msgs[last:] if m["role"] == "assistant" and isinstance(m["content"], list)
             for b in m["content"] if b["type"] == "tool_use"}
    out = [f"mock turn {n}: {len(msgs)} messages, {k} tool results"]
    for m in msgs[last + 1:]:
        if m["role"] != "user":
            continue
        for b in m["content"]:
            body = b["content"]
            digest = hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]
            out.append(f"{names[b['tool_use_id']]}: {'error' if b.get('is_error') else 'ok'}, sha256 {digest}")
            out.extend("  | " + line for line in body.split("\n"))
    return "\n".join(out) + "\n", []


def check_tools(req):
    """None, or why a request with tools is not one the API would take."""
    tools = req["tools"]
    if not isinstance(tools, list) or [x.get("name") for x in tools] != TOOLS \
            or any(x.get("input_schema", {}).get("type") != "object" for x in tools):
        return "tools must be sh, read_file, write_file and edit_file, each with an object input_schema"
    asked = []
    for m in req["messages"]:
        c = m["content"]
        if isinstance(c, str):
            if asked:
                return "a tool_use without its tool_result"
            continue
        if m["role"] == "assistant":
            if asked or any(b.get("type") not in ("text", "tool_use") for b in c):
                return "an assistant block that is not text or tool_use"
            asked = [b["id"] for b in c if b["type"] == "tool_use"]
            if any(b["type"] == "tool_use" and (b.get("name") not in TOOLS or not isinstance(b.get("input"), dict))
                   for b in c):
                return "a tool_use without a known name and an object input"
        else:
            got = [b.get("tool_use_id") for b in c if b.get("type") == "tool_result" and isinstance(b.get("content"), str)]
            if got != asked or len(got) != len(c):
                return "tool_result blocks must answer the tool_use blocks before them, in order"
            asked = []
    return "a tool_use without its tool_result" if asked else None


def events(text, calls=()):
    ev = []

    def add(kind, obj, ascii_only=True):
        ev.append(f"event: {kind}\ndata: {json.dumps(obj, ensure_ascii=ascii_only, separators=(',', ':'))}\n\n")

    add("message_start", {"type": "message_start", "message": {"id": "msg_mock", "type": "message", "role": "assistant",
        "content": [], "model": "mock", "stop_reason": None, "usage": {"input_tokens": 1, "output_tokens": 1}}})
    add("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}})
    add("ping", {"type": "ping"})
    pieces, at, k = [], 0, 0
    while at < len(text):
        step = 7 + (k * 5) % 23
        pieces.append(text[at:at + step])
        at += step
        k += 1
    for i, p in enumerate(pieces):
        add("content_block_delta", {"type": "content_block_delta", "index": 0,
            "delta": {"type": "text_delta", "text": p}}, ascii_only=(i % 2 == 0))
    add("content_block_stop", {"type": "content_block_stop", "index": 0})
    for i, (cid, name, inp) in enumerate(calls, 1):
        add("content_block_start", {"type": "content_block_start", "index": i,
            "content_block": {"type": "tool_use", "id": cid, "name": name, "input": {}}})
        raw = json.dumps(inp)
        cut = [0, 0, len(raw) // 3, 2 * len(raw) // 3, len(raw)]
        for a, b in zip(cut, cut[1:]):
            add("content_block_delta", {"type": "content_block_delta", "index": i,
                "delta": {"type": "input_json_delta", "partial_json": raw[a:b]}})
        add("content_block_stop", {"type": "content_block_stop", "index": i})
    stop = "tool_use" if calls else "end_turn"
    add("message_delta", {"type": "message_delta", "delta": {"stop_reason": stop, "stop_sequence": None},
        "usage": {"output_tokens": len(pieces)}})
    add("message_stop", {"type": "message_stop"})
    return "".join(ev).encode("utf-8")


def chunked(data):
    out, at, k = [], 0, 0
    while at < len(data):
        step = 37 + (k * 97) % 401
        part = data[at:at + step]
        out.append(b"%x\r\n" % len(part) + part + b"\r\n")
        at += step
        k += 1
    out.append(b"0\r\n\r\n")
    return b"".join(out)


def close_notify(sock):
    if isinstance(sock, ssl.SSLSocket):
        try:
            sock.unwrap()
        except (ssl.SSLError, OSError):
            pass


def error(sock, why):
    body = json.dumps({"type": "error", "error": {"type": "invalid_request_error", "message": why}}).encode()
    sock.sendall(b"HTTP/1.1 400 Bad Request\r\ncontent-type: application/json\r\ncontent-length: %d\r\n"
                 b"connection: close\r\n\r\n" % len(body) + body + b"\n")
    close_notify(sock)
    return why


def serve(sock, n, big):
    data = b""
    while b"\r\n\r\n" not in data:
        got = sock.recv(65536)
        if not got:
            return "closed before the headers", 0, ""
        data += got
    t0 = time.monotonic()
    head, body = data.split(b"\r\n\r\n", 1)
    lines = head.decode("latin-1").split("\r\n")
    hdr = {}
    for h in lines[1:]:
        k, _, v = h.partition(":")
        hdr[k.strip().lower()] = v.strip()
    size = int(hdr.get("content-length", "-1"))
    while len(body) < size:
        got = sock.recv(65536)
        if not got:
            break
        body += got
    digest = hashlib.sha256(body).hexdigest()
    if lines[0] != "POST /v1/messages HTTP/1.1":
        return error(sock, f"request line {lines[0]!r}"), len(body), digest
    for need in ("anthropic-version", "x-api-key", "content-type"):
        if need not in hdr:
            return error(sock, f"no {need} header"), len(body), digest
    if size != len(body):
        return error(sock, f"content-length {size}, body {len(body)}"), len(body), digest
    try:
        req = json.loads(body.decode("utf-8"))
    except ValueError as e:
        return error(sock, f"body is not JSON: {e}"), len(body), digest
    msgs = req.get("messages", [])
    if req.get("stream") is not True or not isinstance(req.get("max_tokens"), int) or not req.get("model"):
        return error(sock, "stream, max_tokens or model"), len(body), digest
    if not msgs or len(msgs) % 2 != 1 or any(m.get("role") != ("user", "assistant")[i % 2] for i, m in enumerate(msgs)):
        return error(sock, "messages must alternate user and assistant and end with user"), len(body), digest
    scripted = None
    if "tools" in req:
        why = check_tools(req)
        if why:
            return error(sock, why), len(body), digest
        scripted = tool_reply(n, msgs)
    stream = events(*scripted) if scripted else events(reply_text(n, req, big))
    sock.sendall(b"HTTP/1.1 200 OK\r\ncontent-type: text/event-stream\r\ntransfer-encoding: chunked\r\n"
                 b"connection: close\r\n\r\n" + chunked(stream))
    close_notify(sock)
    sock.shutdown(socket.SHUT_WR)
    while sock.recv(4096):
        pass
    return f"200, reply {len(stream)} bytes in {time.monotonic() - t0:.3f} s", len(body), digest


def dns_reply(qry, answer):
    if len(qry) < 17:
        return None
    qid, flags, qd = struct.unpack(">HHH", qry[:6])
    at, labels = 12, []
    while at < len(qry) and qry[at]:
        labels.append(qry[at + 1:at + 1 + qry[at]].decode("ascii", "replace"))
        at += 1 + qry[at]
    question = qry[12:at + 5]
    name = ".".join(labels).lower()
    qtype = struct.unpack(">H", qry[at + 1:at + 3])[0]
    if name != "api.mock" or qtype != 1:
        return struct.pack(">HHHHHH", qid, 0x8183, 1, 0, 0, 0) + question, name
    # api.mock CNAME edge.mock (edge, then a pointer to "mock" in the question); edge.mock A answer
    mock_at = 12 + 1 + 3                          # "mock" after the 3-byte label "api"
    cname = b"\x04edge" + struct.pack(">H", 0xC000 | mock_at)
    edge_at = 12 + len(question) + 12             # the CNAME's rdata, after its 12-byte fixed part
    rr1 = struct.pack(">HHHIH", 0xC00C, 5, 1, 60, len(cname)) + cname
    rr2 = struct.pack(">HHHIH", 0xC000 | edge_at, 1, 1, 60, 4) + socket.inet_aton(answer)
    return struct.pack(">HHHHHH", qid, 0x8180, 1, 2, 0, 0) + question + rr1 + rr2, name


def dns_serve(port, answer):
    u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    u.bind(("127.0.0.1", port))
    while True:
        qry, peer = u.recvfrom(1500)
        got = dns_reply(qry, answer)
        if got:
            u.sendto(got[0], peer)
            print(f"apihost: dns {got[1]} from a query of {len(qry)} bytes", flush=True)


def main(argv):
    port, turns, seconds, big, dns_port, answer = 8080, 2, 0, False, 0, "10.0.2.2"
    cert = key = None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--big":
            big = True
        elif a in ("--answer", "--cert", "--key") and i + 1 < len(argv):
            i += 1
            if a == "--answer":
                answer = argv[i]
            elif a == "--cert":
                cert = argv[i]
            else:
                key = argv[i]
        elif a in ("--port", "--turns", "--seconds", "--dns") and i + 1 < len(argv):
            i += 1
            v = int(argv[i])
            if a == "--port":
                port = v
            elif a == "--turns":
                turns = v
            elif a == "--dns":
                dns_port = v
            else:
                seconds = v
        else:
            print(__doc__.strip(), file=sys.stderr)
            return 2
        i += 1
    if (cert is None) != (key is None):
        print(__doc__.strip(), file=sys.stderr)
        return 2
    tls = None
    if cert:
        tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        tls.minimum_version = tls.maximum_version = ssl.TLSVersion.TLSv1_2
        tls.load_cert_chain(cert, key)
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", port))
    srv.listen(1)
    if seconds:
        srv.settimeout(seconds)
    if dns_port:
        threading.Thread(target=dns_serve, args=(dns_port, answer), daemon=True).start()
    print(f"apihost: listening on 127.0.0.1:{port}", flush=True)
    for n in range(1, turns + 1):
        try:
            sock, _ = srv.accept()
        except socket.timeout:
            print("apihost: no connection", flush=True)
            return 1
        sock.settimeout(seconds or None)
        if tls:
            try:
                sock = tls.wrap_socket(sock, server_side=True)
            except (ssl.SSLError, OSError) as e:
                sock.close()
                print(f"apihost: request {n}, tls: {getattr(e, 'reason', None) or e}", flush=True)
                continue
        what, size, digest = serve(sock, n, big)
        sock.close()
        print(f"apihost: request {n}, {size} bytes, sha256 {digest}: {what}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
