#!/usr/bin/env python3
"""tools/nethost.py: the host side of stage N's and stage NW's live legs
(docs/specs/2026-11-05-n-net.md section 4, docs/specs/2026-11-07-nw-window.md sections 3 and 6).

  nethost.py udp PORT [SECONDS]: a UDP echo on 0.0.0.0:PORT; each datagram goes back whole to its sender.
  Prints `nethost: udp echo on PORT` once bound (flushed: a caller waits for it), then one line per datagram
  on stderr; stops after SECONDS (default 60) or when killed. Under QEMU's user network a guest reaches it
  at 10.0.2.2:PORT; on the host the Linux oracle reaches it at 127.0.0.1:PORT.
  nethost.py http PORT [SECONDS [BYTES]]: HTTP/1.0 on 0.0.0.0:PORT (Python's http.server); GET /f is BYTES
  (default FILE_BYTES = 262,144) bytes, byte i being (31 * i + i // 512) % 256, so its digest is fixed
  (`nethost.py md5 [BYTES]`). Prints `nethost: http on PORT` once bound; stops after SECONDS (default 60).
  nethost.py md5 [BYTES]: the MD5 of /f, as md5sum prints it.
  nethost.py tcp PORT WATCH LINE [BYTES]: waits (30 s at most) until the file WATCH has a line starting with
  LINE, then connects to 127.0.0.1:PORT, sends BYTES (default TCP_BYTES = 10,000) bytes (byte i is
  (7 * i + 3) % 251), shuts its side while reading concurrently to the end, and prints `nethost: tcp sent N,
  got back N, equal` (or `differ`). N-3's and NW-2's mtcp leg.
  nethost.py source PORT BYTES [SECONDS]: NW-0 (docs/specs/2026-11-07-nw-window.md). Listens on 0.0.0.0:PORT,
  prints `nethost: source on PORT` once bound, takes one connection (within SECONDS, default 60), sends BYTES
  bytes (byte i is (7 * i + 3) % 251), shuts its side, reads to the peer's close and prints `nethost: source N
  bytes in S s, sha256 HEX`: S from the accept to the peer's close, by this host's clock. `mtcp -r` is the peer.
  nethost.py sink PORT [SECONDS]: listens, prints `nethost: sink on PORT`, takes one connection, reads to its
  end and prints `nethost: sink N bytes in S s, sha256 HEX`, S from the accept to the end. `mtcp -s` is the peer.
  nethost.py lossy DIR [SECONDS [EVERY]]: NW-2 frame forwarder for QEMU's filter-redirector (`NET_LOSSY=DIR`).
  Listens on DIR/{rx_out,rx_in,tx_out,tx_in}, prints `nethost: lossy on DIR` once bound, forwards raw Ethernet
  frames in both directions and drops every EVERY-th (default 10) IPv4 TCP segment in each direction.
"""
import hashlib
import http.server
import os
import socket
import struct
import sys
import threading
import time

FILE_BYTES = 262144
TCP_BYTES = 10000
HTTP_BODY = None


def body(count=FILE_BYTES):
    blk = bytes((31 * i + i // 512) % 256 for i in range(131072))
    return (blk * (count // len(blk) + 1))[:count]


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/f":
            self.send_error(404)
            return
        b = HTTP_BODY if HTTP_BODY is not None else body()
        self.send_response(200)
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Connection", "close")
        self.end_headers()
        for off in range(0, len(b), 32768):
            self.wfile.write(b[off:off + 32768])
            self.wfile.flush()
        try:
            self.connection.shutdown(socket.SHUT_WR)
            self.connection.settimeout(180.0)
            while self.connection.recv(4096):
                pass
        except OSError:
            pass

    def log_message(self, fmt, *args):
        print("nethost: " + fmt % args, file=sys.stderr, flush=True)


def http_serve(port, seconds, count=FILE_BYTES):
    global HTTP_BODY
    HTTP_BODY = body(count)
    srv = http.server.HTTPServer(("0.0.0.0", port), Handler)
    srv.timeout = 0.2
    print(f"nethost: http on {port}", flush=True)
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        srv.handle_request()


def tcp_client(port, watch, line, count=TCP_BYTES):
    wait_s = 30 if count <= TCP_BYTES else 180
    end = time.monotonic() + wait_s
    while time.monotonic() < end:
        try:
            with open(watch, "rb") as f:
                if any(l.startswith(line.encode()) for l in f.read().splitlines()):
                    break
        except OSError:
            pass
        time.sleep(0.05)
    else:
        sys.exit(f"nethost: no line starting {line!r} in {watch}")
    out = pattern(count)
    s = socket.create_connection(("127.0.0.1", port), timeout=wait_s)
    s.settimeout(wait_s)

    def writer():
        try:
            s.sendall(out)
            s.shutdown(socket.SHUT_WR)
        except OSError:
            pass

    wt = threading.Thread(target=writer, daemon=True)
    wt.start()
    chunks = []
    while True:
        b = s.recv(65536)
        if not b:
            break
        chunks.append(b)
    wt.join(timeout=5)
    s.close()
    got = b"".join(chunks)
    print(f"nethost: tcp sent {len(out)}, got back {len(got)}, {'equal' if got == out else 'differ'}", flush=True)


def pattern(n):
    """Bytes 0..n of the NW-0 stream, byte i being (7 * i + 3) % 251 (period 251)."""
    p = bytes((7 * i + 3) % 251 for i in range(251))
    return (p * (n // 251 + 1))[:n]


def one_connection(port, seconds, name):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", port))
    srv.listen(1)
    srv.settimeout(seconds)
    print(f"nethost: {name} on {port}", flush=True)
    try:
        c, _ = srv.accept()
    except socket.timeout:
        sys.exit(f"nethost: {name}: no connection on {port} in {seconds} s")
    srv.close()
    c.settimeout(seconds)
    return c


def drain(c, h):
    n = 0
    while True:
        b = c.recv(1 << 20)
        if not b:
            return n
        h.update(b)
        n += len(b)


def source(port, count, seconds):
    c = one_connection(port, seconds, "source")
    out = pattern(count)
    t0 = time.monotonic()
    c.sendall(out)
    c.shutdown(socket.SHUT_WR)
    drain(c, hashlib.sha256())
    s = time.monotonic() - t0
    c.close()
    print(f"nethost: source {count} bytes in {s:.3f} s, sha256 {hashlib.sha256(out).hexdigest()}", flush=True)


def sink(port, seconds):
    c = one_connection(port, seconds, "sink")
    h = hashlib.sha256()
    t0 = time.monotonic()
    n = drain(c, h)
    s = time.monotonic() - t0
    c.close()
    print(f"nethost: sink {n} bytes in {s:.3f} s, sha256 {h.hexdigest()}", flush=True)


def udp(port, seconds):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("0.0.0.0", port))
    print(f"nethost: udp echo on {port}", flush=True)
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        s.settimeout(max(0.1, end - time.monotonic()))
        try:
            data, peer = s.recvfrom(65535)
        except socket.timeout:
            break
        s.sendto(data, peer)
        print(f"nethost: {len(data)} bytes from {peer[0]}:{peer[1]} echoed", file=sys.stderr, flush=True)


def is_ipv4_tcp_data(pkt):
    if len(pkt) < 34 or pkt[12:14] != b"\x08\x00" or (pkt[14] >> 4) != 4 or pkt[23] != 6:
        return False
    ihl = (pkt[14] & 0x0F) * 4
    tot = int.from_bytes(pkt[16:18], "big")
    if len(pkt) < 14 + ihl + 20 or tot < ihl + 20:
        return False
    thl = (pkt[14 + ihl + 12] >> 4) * 4
    return tot > ihl + thl


def recv_exact(sock, n):
    buf = bytearray()
    while len(buf) < n:
        b = sock.recv(n - len(buf))
        if not b:
            return None
        buf.extend(b)
    return bytes(buf)


def lossy(dir_path, seconds, every):
    os.makedirs(dir_path, exist_ok=True)
    names = ("rx_out", "rx_in", "tx_out", "tx_in")
    listeners = {}
    for nm in names:
        p = os.path.join(dir_path, nm)
        try:
            os.unlink(p)
        except OSError:
            pass
        ls = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        ls.bind(p)
        ls.listen(1)
        ls.settimeout(seconds)
        listeners[nm] = ls
    print(f"nethost: lossy on {dir_path} (every {every})", flush=True)
    stats = {"up": [0, 0], "down": [0, 0]}

    def pipe_way(key, ls_out, ls_in):
        try:
            c_out, _ = ls_out.accept()
            c_in, _ = ls_in.accept()
        except socket.timeout:
            return
        finally:
            ls_out.close()
            ls_in.close()
        c_out.settimeout(seconds)
        c_in.settimeout(seconds)
        seen = 0
        dropped = 0
        try:
            while True:
                hdr = recv_exact(c_out, 4)
                if hdr is None:
                    break
                (n,) = struct.unpack(">I", hdr)
                if n > 65536:
                    break
                pkt = recv_exact(c_out, n)
                if pkt is None:
                    break
                if is_ipv4_tcp_data(pkt):
                    seen += 1
                    if every > 0 and seen % every == 0:
                        dropped += 1
                        continue
                c_in.sendall(hdr + pkt)
        except OSError:
            pass
        finally:
            stats[key] = [seen, dropped]
            c_out.close()
            c_in.close()

    t_up = threading.Thread(target=pipe_way, args=("up", listeners["rx_out"], listeners["rx_in"]), daemon=True)
    t_dn = threading.Thread(target=pipe_way, args=("down", listeners["tx_out"], listeners["tx_in"]), daemon=True)
    t_up.start()
    t_dn.start()
    t_up.join(timeout=seconds + 5)
    t_dn.join(timeout=seconds + 5)
    u_s, u_d = stats["up"]
    d_s, d_d = stats["down"]
    print(f"nethost: lossy up {u_s} tcp ({u_d} dropped), down {d_s} tcp ({d_d} dropped)", flush=True)


if __name__ == "__main__":
    a = sys.argv
    if len(a) in (3, 4) and a[1] == "udp":
        udp(int(a[2]), float(a[3]) if len(a) == 4 else 60.0)
    elif len(a) in (3, 4, 5) and a[1] == "http":
        http_serve(int(a[2]), float(a[3]) if len(a) >= 4 else 60.0, int(a[4]) if len(a) == 5 else FILE_BYTES)
    elif len(a) in (2, 3) and a[1] == "md5":
        print(f"{hashlib.md5(body(int(a[2]) if len(a) == 3 else FILE_BYTES)).hexdigest()}  -")
    elif len(a) in (5, 6) and a[1] == "tcp":
        tcp_client(int(a[2]), a[3], a[4], int(a[5]) if len(a) == 6 else TCP_BYTES)
    elif len(a) in (4, 5) and a[1] == "source":
        source(int(a[2]), int(a[3]), float(a[4]) if len(a) == 5 else 60.0)
    elif len(a) in (3, 4) and a[1] == "sink":
        sink(int(a[2]), float(a[3]) if len(a) == 4 else 60.0)
    elif len(a) in (3, 4, 5) and a[1] == "lossy":
        lossy(a[2], float(a[3]) if len(a) >= 4 else 120.0, int(a[4]) if len(a) == 5 else 10)
    else:
        sys.exit("usage: nethost.py udp PORT [SECONDS] | http PORT [SECONDS [BYTES]] | md5 [BYTES]"
                 " | tcp PORT WATCH LINE [BYTES] | source PORT BYTES [SECONDS] | sink PORT [SECONDS]"
                 " | lossy DIR [SECONDS [EVERY]]")
