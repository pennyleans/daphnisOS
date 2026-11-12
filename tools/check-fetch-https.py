#!/usr/bin/env python3
"""Exercise fetch against local HTTP, DNS, and certificate fixtures."""

import argparse
import contextlib
import os
import pathlib
import re
import socketserver
import ssl
import struct
import subprocess
import tempfile
import threading

ROOT = pathlib.Path(__file__).resolve().parent.parent
BODY = b"fetch https: \x00\xff\n" * 700


def built(o, names):
    """RG-1: the programs names at O/ubin, built from source at HEAD by the Makefile's rules, never the committed
    user/bin (which holds none): the directory."""
    ub = pathlib.Path(o).resolve() / "ubin"
    subprocess.run(["make", "-s", f"O={pathlib.Path(o).resolve()}", *[str(ub / n) for n in names]], cwd=ROOT, check=True,
                   capture_output=True)
    return ub


def shell_members(o):
    """The mkcpio members of an image's shell, as the Makefile's SH_BIN (DOS-3, unit 4b: busybox is in no image):
    cish as sh and /bin/sh, and in /bin the native tools of SH_TOOLS, all from O/ubin; and grant."""
    tools = re.search(r"^SH_TOOLS := (.*)$", (ROOT / "Makefile").read_text(), re.M).group(1).split()
    ub = built(o, ["cish", "grant", *tools])
    return [f"sh={ub}/cish", "bin/", f"bin/sh={ub}/cish", f"grant={ub}/grant"] + [f"bin/{t}={ub}/{t}" for t in tools]


class DNS(socketserver.BaseRequestHandler):
    def handle(self):
        data, sock = self.request
        reply = data[:2] + struct.pack("!5H", 0x8180, 1, 1, 0, 0)
        reply += data[12:] + b"\xc0\x0c" + struct.pack("!HHIH", 1, 1, 0, 4)
        sock.sendto(reply + self.server.address_bytes, self.client_address)


class HTTP(socketserver.BaseRequestHandler):
    def handle(self):
        conn = self.request
        conn.settimeout(5)
        try:
            if self.server.context:
                conn = self.server.context.wrap_socket(conn, server_side=True)
            with conn:
                data = b""
                while b"\r\n\r\n" not in data and len(data) < 8192:
                    part = conn.recv(2048)
                    if not part:
                        return
                    data += part
                self.server.requests.append(data)
                path = data.split(b" ")[1]
                if path == b"/guest":
                    body = b"fetch-https-guest-ok\n"
                    reply = f"HTTP/1.1 200 OK\r\nContent-Length: {len(body)}\r\n\r\n".encode() + body
                elif path == b"/redirect":
                    reply = b"HTTP/1.1 302 Found\r\nLocation: /guest\r\nContent-Length: 7\r\n\r\ndiscard"
                elif path in (b"/chunked", b"/chunked-hold"):
                    reply = b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n"
                    for at in range(0, len(BODY), 317):
                        part = BODY[at:at + 317]
                        reply += f"{len(part):x}\r\n".encode() + part + b"\r\n"
                    reply += b"0\r\n\r\n"
                elif path == b"/missing":
                    reply = b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n"
                elif path == b"/short":
                    reply = b"HTTP/1.1 200 OK\r\nContent-Length: 10\r\n\r\nabc"
                elif path in (b"/abrupt", b"/unframed"):
                    reply = b"HTTP/1.1 200 OK\r\n\r\nabc"
                else:
                    reply = f"HTTP/1.1 200 OK\r\nContent-Length: {len(BODY)}\r\n\r\n".encode() + BODY
                conn.sendall(reply)
                if path == b"/abrupt":
                    return
                if path in (b"/hold", b"/chunked-hold"):
                    self.server.release.wait(20)
                if self.server.context:
                    conn.unwrap().close()
        except (ssl.SSLError, OSError):
            # Certificate rejection can end the handshake before an HTTP request.
            return


@contextlib.contextmanager
def server(cert=None, dns=False, guest=False):
    cls = socketserver.ThreadingUDPServer if dns else socketserver.ThreadingTCPServer
    with cls(("127.0.0.1", 0), DNS if dns else HTTP) as srv:
        srv.daemon_threads = True
        srv.context = None
        srv.requests = []
        srv.names = []
        srv.release = threading.Event()
        srv.address_bytes = b"\x0a\x00\x02\x02" if guest else b"\x7f\x00\x00\x01"
        if cert:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.minimum_version = ctx.maximum_version = ssl.TLSVersion.TLSv1_2
            ctx.load_cert_chain(ROOT / "tests/tls" / cert, ROOT / "tests/tls/api.mock.key")
            ctx.set_servername_callback(lambda conn, name, context: srv.names.append(name))
            srv.context = ctx
        thread = threading.Thread(target=srv.serve_forever, daemon=True)
        thread.start()
        try:
            yield srv
        finally:
            srv.release.set()
            srv.shutdown()
            thread.join()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("program", type=pathlib.Path)
    parser.add_argument("--kernel", type=pathlib.Path)
    parser.add_argument("--out", type=pathlib.Path)
    opts = parser.parse_args()
    program = opts.program.resolve()
    checks = []

    def check(name, ok, detail=""):
        checks.append(ok)
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f": {detail}" if not ok else ""), flush=True)

    if opts.kernel:
        if opts.out is None:
            parser.error("--kernel requires --out outside the repository")
        out = opts.out.resolve()
        if out == ROOT or ROOT in out.parents:
            parser.error("--out must be outside the repository")
        out.mkdir(parents=True, exist_ok=True)
        with server(dns=True, guest=True) as dns, server("api.mock.pem") as good:
            resolver = f"10.0.2.2:{dns.server_address[1]}"
            port = good.server_address[1]
            script = out / "go.sh"
            script.write_text(
                f"./fetch -d {resolver} -o /saved https://api.mock:{port}/guest\n"
                "echo FETCH_GOOD=$?\ncat /saved\n"
                f"./fetch -d {resolver} -o - https://api.mock:{port}/redirect\n"
                "echo FETCH_REDIRECT=$?\n"
                f"./fetch -d {resolver} -o /saved https://wrong.mock:{port}/guest\n"
                "echo FETCH_BAD=$?\ncat /saved\n"
            )
            archive = out / "fetch.cpio"
            subprocess.run(["python3", "tools/mkcpio.py", str(archive), *shell_members(opts.kernel.resolve().parent.parent),
                            f"fetch={program}", f"go.sh={script}"], cwd=ROOT, check=True, capture_output=True)
            env = {**os.environ, "NET": "user", "CPU": "max", "INITRD": str(archive), "QEMU_TIMEOUT": "60"}
            transcript = out / "guest.serial"
            boot = subprocess.run(["tools/run-qemu.sh", str(opts.kernel.resolve()), str(transcript)],
                                  cwd=ROOT, env=env, capture_output=True, timeout=70)
            data = transcript.read_bytes()
            check("daphnis exits cleanly", boot.returncode == 0 and boot.stdout.strip() == b"33"
                  and not pathlib.Path(str(transcript) + ".err").read_bytes(), repr(boot.stdout + boot.stderr))
            check("daphnis https succeeds", b"FETCH_GOOD=0\n" in data)
            check("daphnis https redirect succeeds", b"FETCH_REDIRECT=0\n" in data)
            check("daphnis hostname rejection", b"FETCH_BAD=1\n" in data and b"tls: error 1056" in data)
            check("daphnis rejection preserves destination", data.count(b"fetch-https-guest-ok\n") == 3)
            check("daphnis follows the location", len(good.requests) == 3 and b"GET /redirect HTTP/1.1" in good.requests[1]
                  and b"GET /guest HTTP/1.1" in good.requests[2] and b"discard" not in data)
            check("daphnis authenticates before http", len(good.requests) == 3)
            check("daphnis closes connections", b"tcp connections open 0" in data)
        if len(checks) != 8:
            raise RuntimeError(f"expected 8 guest checks, ran {len(checks)}")
        print(f"RESULT: {'PASS' if all(checks) else 'FAIL'} ({sum(checks)}/{len(checks)})")
        return 0 if all(checks) else 1

    with tempfile.TemporaryDirectory(prefix="fetch-test-") as tmp, server(dns=True) as dns:
        work = pathlib.Path(tmp)
        resolver = f"127.0.0.1:{dns.server_address[1]}"

        def run(url, *extra, use_dns=True):
            argv = [str(program)]
            if use_dns:
                argv += ["-d", resolver]
            argv += list(extra) + [url]
            try:
                return subprocess.run(argv, cwd=work, capture_output=True, timeout=5)
            except subprocess.TimeoutExpired as error:
                return subprocess.CompletedProcess(argv, 124, error.stdout or b"", b"fetch timed out")

        with server() as plain:
            result = run(f"http://127.0.0.1:{plain.server_address[1]}/body", "-o", "-", use_dns=False)
            check("http remains byte-exact", result.returncode == 0 and result.stdout == BODY and not result.stderr, repr(result.stderr))

        with server("api.mock.pem") as good:
            base = f"https://api.mock:{good.server_address[1]}"
            for endpoint in ("body", "chunked"):
                result = run(f"{base}/{endpoint}", "-o", "-")
                check(f"https {endpoint}", result.returncode == 0 and result.stdout == BODY and not result.stderr, repr(result.stderr))
            result = run(f"{base}/body", "-o", "saved")
            saved = work / "saved"
            check("https file output", result.returncode == 0 and saved.exists() and saved.read_bytes() == BODY, repr(result.stderr))
            result = run(f"{base}/missing", "-o", "missing")
            check("http error creates no file", result.returncode == 1 and b"404" in result.stderr and not (work / "missing").exists(), repr(result.stderr))
            result = run(f"{base}/short", "-o", "-")
            check("truncated https body fails", result.returncode == 1 and result.stdout == b"abc" and b"short body: 3 of 10 bytes" in result.stderr, repr(result.stderr))
            check("tls authenticates hostname without port", bool(good.names) and all(name == "api.mock" for name in good.names), repr(good.names))
            authority = f"Host: api.mock:{good.server_address[1]}\r\n".encode()
            check("http preserves authority port", len(good.requests) == 5 and all(authority in req for req in good.requests), repr(good.requests[:1]))

        with server("api.mock.pem") as closing:
            base = f"https://api.mock:{closing.server_address[1]}"
            for path in ("hold", "chunked-hold"):
                result = run(f"{base}/{path}", "-o", "-")
                check(f"{path} does not wait for peer shutdown", result.returncode == 0 and result.stdout == BODY and not result.stderr, repr(result.stderr))
            closing.release.set()
            result = run(f"{base}/unframed", "-o", "-")
            check("unframed body ends at authenticated tls eof", result.returncode == 0 and result.stdout == b"abc" and not result.stderr, repr(result.stderr))
            result = run(f"{base}/abrupt", "-o", "-")
            check("unframed body requires authenticated tls eof", result.returncode == 1 and b"tls: error" in result.stderr, repr(result.stderr))

        for cert, host, code in (("api.mock.pem", "wrong.mock", b"1056"), ("expired.pem", "api.mock", b"1054"), ("stranger.pem", "api.mock", b"1062")):
            with server(cert) as bad:
                saved = work / "protected"
                saved.write_bytes(b"keep")
                result = run(f"https://{host}:{bad.server_address[1]}/body", "-o", "protected")
                check(f"reject {cert} for {host}", result.returncode == 1 and code in result.stderr and not result.stdout, repr(result.stderr))
                check(f"rejection preserves file and sends no http: {cert}/{host}", saved.read_bytes() == b"keep" and not bad.requests)

        for resolver_arg in ("", "127.0.0.1:0", "127.0.0.1:65536", "localhost:53", "127.0.0.1:"):
            result = run("http://127.0.0.1:1/", "-d", resolver_arg, "-o", "-", use_dns=False)
            check(f"reject invalid resolver {resolver_arg!r}", result.returncode == 2 and b"bad resolver" in result.stderr, repr(result.stderr))

    if len(checks) != 23:
        raise RuntimeError(f"expected 23 host checks, ran {len(checks)}")
    print(f"RESULT: {'PASS' if all(checks) else 'FAIL'} ({sum(checks)}/{len(checks)})")
    return 0 if all(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
