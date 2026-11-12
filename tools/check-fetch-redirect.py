#!/usr/bin/env python3
"""Check URL handling and redirects against local HTTP and TLS peers."""

import argparse
import importlib.util
import pathlib
import socketserver
import ssl
import subprocess
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("https_fixture", ROOT / "tools/check-fetch-https.py")
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
PAYLOAD = b"redirect destination\x00\xff\n"


class RedirectHTTP(socketserver.BaseRequestHandler):
    def handle(self):
        conn = self.request
        conn.settimeout(5)
        try:
            if self.server.context:
                conn = self.server.context.wrap_socket(conn, server_side=True)
            with conn:
                data = b""
                while b"\r\n\r\n" not in data and len(data) < 16384:
                    part = conn.recv(2048)
                    if not part:
                        return
                    data += part
                self.server.requests.append(data)
                path = data.split(b" ")[1]
                response = self.server.routes.get(path)
                if response is None:
                    response = b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n"
                for at in range(0, len(response), 11):
                    conn.sendall(response[at:at + 11])
                if self.server.context:
                    conn.unwrap().close()
        except (ssl.SSLError, OSError):
            return


def redirect(location=None, code=302, extra=b""):
    header = f"HTTP/1.1 {code} Redirect\r\n".encode()
    if location is not None:
        header += b"Location: " + location.encode() + b"\r\n"
    return header + extra + b"Content-Length: 7\r\n\r\ndiscard"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("program", type=pathlib.Path)
    opts = parser.parse_args()
    program = opts.program.resolve()
    checks = []

    def check(name, ok, detail=""):
        checks.append(ok)
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f": {detail}" if not ok else ""), flush=True)

    fixture.HTTP = RedirectHTTP
    with tempfile.TemporaryDirectory(prefix="fetch-redirect-") as tmp, fixture.server(dns=True) as dns, \
            fixture.server("api.mock.pem") as secure, fixture.server("api.mock.pem") as other, fixture.server() as plain:
        work = pathlib.Path(tmp)
        for server in (secure, other, plain):
            response = b"HTTP/1.1 200 OK\r\nContent-Length: " + str(len(PAYLOAD)).encode() + b"\r\n\r\n" + PAYLOAD
            server.routes = {path: response for path in (
                b"/body", b"/body?x=1", b"/body?from=relative", b"/query?next=yes",
                b"/?only=query", b"/a%2Fb?q=%23x")}
        base = f"https://api.mock:{secure.server_address[1]}"
        alternate = f"https://api.mock:{other.server_address[1]}"
        insecure = f"http://api.mock:{plain.server_address[1]}"
        resolver = f"127.0.0.1:{dns.server_address[1]}"

        def run(url, destination="-"):
            argv = [str(program), "-d", resolver, "-o", destination, url]
            try:
                return subprocess.run(argv, cwd=work, capture_output=True, timeout=8)
            except subprocess.TimeoutExpired:
                return subprocess.CompletedProcess(argv, 124, b"", b"timeout")

        def succeeds(name, url):
            result = run(url)
            check(name, result.returncode == 0 and result.stdout == PAYLOAD and not result.stderr, repr(result.stderr))

        def refuses(name, url, error):
            saved = work / "saved"
            saved.write_bytes(b"keep")
            result = run(url, "saved")
            check(name, result.returncode != 0 and result.returncode != 124 and error in result.stderr
                  and not result.stdout and saved.read_bytes() == b"keep", repr(result.stderr))

        for code in (301, 302, 303, 307, 308):
            secure.routes[f"/r/{code}".encode()] = redirect("/body?x=1#anchor", code)
            succeeds(f"follows {code} without intermediate body", f"{base}/r/{code}")
        check("fragments stay off the wire", any(b"GET /body?x=1 HTTP/1.1" in r for r in secure.requests)
              and all(b"#" not in r.split(b"\r\n")[0] for r in secure.requests))
        secure.routes[b"/dir/start"] = redirect("../body?from=relative")
        succeeds("relative location", f"{base}/dir/start")
        check("relative target path", b"GET /body?from=relative HTTP/1.1" in secure.requests[-1])
        secure.routes[b"/query"] = redirect("?next=yes")
        succeeds("query-only location", f"{base}/query")
        check("query-only target path", b"GET /query?next=yes HTTP/1.1" in secure.requests[-1])
        secure.routes[b"/network"] = redirect(f"//api.mock:{other.server_address[1]}/body")
        succeeds("scheme-relative location", f"{base}/network")
        check("new authority uses its port", len(other.requests) == 1
              and f"Host: api.mock:{other.server_address[1]}\r\n".encode() in other.requests[0])
        secure.routes[b"/absolute"] = redirect(alternate + "/body")
        before = len(other.requests)
        succeeds("absolute cross-origin location", f"{base}/absolute")
        check("absolute location changes authority", len(other.requests) == before + 1
              and b"GET /body HTTP/1.1" in other.requests[-1])
        plain.routes[b"/upgrade"] = redirect(base + "/body")
        succeeds("http to https upgrade", insecure + "/upgrade")
        before = len(plain.requests)
        secure.routes[b"/downgrade"] = redirect(insecure + "/body")
        refuses("refuses https downgrade before output", base + "/downgrade", b"downgrade")
        check("downgrade sends no plain request", len(plain.requests) == before)
        before = len(other.requests)
        secure.routes[b"/wrong"] = redirect(f"https://wrong.mock:{other.server_address[1]}/body")
        refuses("redirect target authenticates independently", base + "/wrong", b"1056")
        check("bad target receives no http", len(other.requests) == before)
        secure.routes[b"/loop"] = redirect("/loop")
        before = len(secure.requests)
        refuses("redirect loop is bounded", base + "/loop", b"redirect limit")
        check("ten redirect maximum", len(secure.requests) - before == 11)
        secure.routes[b"/missing"] = redirect()
        refuses("missing location preserves destination", base + "/missing", b"location")
        secure.routes[b"/duplicate"] = redirect("/body", extra=b"Location: /elsewhere\r\n")
        refuses("duplicate location is refused", base + "/duplicate", b"location")
        secure.routes[b"/unsafe"] = redirect("javascript:alert(1)")
        refuses("unsupported redirect scheme", base + "/unsafe", b"location")
        secure.routes[b"/large"] = redirect("/" + "a" * 4096)
        refuses("overlong location", base + "/large", b"location")
        succeeds("query without path", base + "?only=query#fragment")
        check("query gets leading slash", b"GET /?only=query HTTP/1.1" in secure.requests[-1])
        succeeds("encoded delimiters remain encoded", base + "/a%2Fb?q=%23x#fragment")
        check("encoded target bytes", b"GET /a%2Fb?q=%23x HTTP/1.1" in secure.requests[-1])
        succeeds("rooted DNS hostname", base.replace("api.mock", "api.mock.") + "/body")
        check("root dot excluded from TLS name only", secure.names[-1] == "api.mock"
              and f"Host: api.mock.:{secure.server_address[1]}\r\n".encode() in secure.requests[-1])
        succeeds("rooted IPv4 hostname", insecure.replace("api.mock", "127.0.0.1.") + "/body")
        longest = base + "/" + "a" * (4096 - len(base) - 1)
        longest_path = longest[len(base):].encode()
        secure.routes[b"/maximum"] = redirect(longest)
        secure.routes[longest_path] = secure.routes[b"/body"]
        succeeds("maximum URL crosses TLS write boundary", base + "/maximum")
        check("maximum target stays byte-exact", secure.requests[-1].split(b" ")[1] == longest_path)
        for suffix in ("/bad\r\nX-Test: injected", "/bad%", "/bad\\path", "/bad space"):
            before = len(secure.requests)
            refuses(f"refuses malformed URL {suffix!r}", base + suffix, b"URL")
            check("malformed URL sends no request", len(secure.requests) == before)
        before = len(secure.requests)
        refuses("userinfo is refused", base.replace("api.mock", "user@api.mock") + "/body", b"URL")
        check("userinfo sends no request", len(secure.requests) == before)

    if len(checks) != 44:
        raise RuntimeError(f"expected 44 checks, ran {len(checks)}")
    print(f"RESULT: {'PASS' if all(checks) else 'FAIL'} ({sum(checks)}/{len(checks)})")
    return 0 if all(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
