#!/usr/bin/env python3
"""tools/mkanchors.py: user/tls/anchors.h, agent's trust anchors (A-4), from the committed roots.

  mkanchors.py [--check]

Reads user/tls/roots/mock.pem (the mock root, trusted for names under .mock only) and user/tls/roots/public.pem
(the roots for every other name; none yet, A-6 adds them), each a bundle of PEM certificates, and writes each
root's subject (the DER of its name) and public key (RSA n and e, or an EC curve and point) as BearSSL's
br_x509_trust_anchor arrays TA_MOCK and TA_PUBLIC. --check exits 1 if anchors.h is not what it would write.
"""
import base64
import os
import re
import sys

CURVES = {"2a8648ce3d030107": "BR_EC_secp256r1", "2b81040022": "BR_EC_secp384r1", "2b81040023": "BR_EC_secp521r1"}
RSA = "2a864886f70d010101"
EC = "2a8648ce3d0201"


def tlv(d, at):
    """(tag, start of value, end of value) of the DER element at d[at]."""
    tag, n = d[at], d[at + 1]
    at += 2
    if n & 0x80:
        k = n & 0x7F
        n = int.from_bytes(d[at:at + k], "big")
        at += k
    return tag, at, at + n


def children(d, at, end):
    out = []
    while at < end:
        t, s, e = tlv(d, at)
        out.append((t, at, s, e))
        at = e
    return out


def anchor(der):
    _, s, e = tlv(der, 0)
    tbs = children(der, *tlv(der, s)[1:])
    if tbs[0][0] == 0xA0:              # [0] version
        tbs = tbs[1:]
    subject = tbs[4]
    spki = children(der, tbs[5][2], tbs[5][3])
    alg = children(der, spki[0][2], spki[0][3])
    oid = der[alg[0][2]:alg[0][3]].hex()
    bits = der[spki[1][2] + 1:spki[1][3]]   # the BIT STRING's bytes, past its unused-bits byte
    dn = der[subject[1]:subject[3]]
    if oid == EC:
        curve = CURVES[der[alg[1][2]:alg[1][3]].hex()]
        return dn, ("ec", curve, bits)
    if oid == RSA:
        n, e = children(bits, *tlv(bits, 0)[1:])
        return dn, ("rsa", bits[n[2]:n[3]].lstrip(b"\0"), bits[e[2]:e[3]].lstrip(b"\0"))
    raise SystemExit(f"mkanchors.py: a root with a key of OID {oid}, neither RSA nor EC")


def certs(path):
    if not os.path.exists(path):
        return []
    text = open(path, encoding="ascii").read()
    return [base64.b64decode(b) for b in re.findall(r"-----BEGIN CERTIFICATE-----(.*?)-----END CERTIFICATE-----", text, re.S)]


def arr(name, b):
    rows = [", ".join(f"0x{x:02X}" for x in b[i:i + 12]) for i in range(0, len(b), 12)]
    return f"static const unsigned char {name}[] = {{\n    " + ",\n    ".join(rows) + "\n};\n"


def render(sets):
    out = ["/* user/tls/anchors.h: agent's trust anchors (A-4), written by tools/mkanchors.py from user/tls/roots/;\n"
           " * do not edit. TA_MOCK serves names under .mock, TA_PUBLIC every other name. */\n"]
    for set_name, ders in sets:
        rows = []
        for i, der in enumerate(ders):
            dn, key = anchor(der)
            p = f"{set_name}{i}"
            out.append(arr(f"{p}_DN", dn))
            if key[0] == "ec":
                out.append(arr(f"{p}_Q", key[2]))
                k = f"{{ BR_KEYTYPE_EC, {{ .ec = {{ {key[1]}, (unsigned char *){p}_Q, sizeof {p}_Q }} }} }}"
            else:
                out.append(arr(f"{p}_N", key[1]))
                out.append(arr(f"{p}_E", key[2]))
                k = (f"{{ BR_KEYTYPE_RSA, {{ .rsa = {{ (unsigned char *){p}_N, sizeof {p}_N, "
                     f"(unsigned char *){p}_E, sizeof {p}_E }} }} }}")
            rows.append(f"    {{ {{ (unsigned char *){p}_DN, sizeof {p}_DN }}, BR_X509_TA_CA, {k} }}")
        if rows:
            out.append(f"static const br_x509_trust_anchor {set_name}[] = {{\n" + ",\n".join(rows) + "\n};\n")
            out.append(f"#define {set_name}_N {len(rows)}\n")
        else:
            out.append(f"#define {set_name} ((const br_x509_trust_anchor *)0)\n#define {set_name}_N 0\n")
    return "".join(out)


def main(argv):
    os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    text = render([("TA_MOCK", certs("user/tls/roots/mock.pem")), ("TA_PUBLIC", certs("user/tls/roots/public.pem"))])
    if argv == ["--check"]:
        return 0 if os.path.exists("user/tls/anchors.h") and open("user/tls/anchors.h").read() == text else 1
    with open("user/tls/anchors.h", "w", encoding="ascii") as f:
        f.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
