#!/usr/bin/env python3
"""tools/mktestpki.py: makes the mock PKI of stage A's TLS gate (docs/specs/2026-11-06-a-agent.md, A-4).

  mktestpki.py

Writes, all ECDSA P-256 with SHA-256:
  user/tls/roots/mock.pem   the mock root, a CA valid 2025-01-01 to 2036-01-01 (agent trusts it for .mock names only)
  tests/tls/api.mock.key    the server's key (the root's is thrown away)
  tests/tls/api.mock.pem    api.mock, by the mock root, valid 2025-01-01 to 2036-01-01
  tests/tls/expired.pem     api.mock, by the mock root, valid 2024-01-01 to 2025-01-01
  tests/tls/stranger.pem    api.mock, by a root agent does not hold (also thrown away)
Every run makes new keys, so after one the committed a4 journal and its transcript are made again, and
user/tls/anchors.h by tools/mkanchors.py. Needs the `cryptography` package; no gate runs it.
"""
import datetime
import os
import sys

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


def day(y):
    return datetime.datetime(y, 1, 1, tzinfo=datetime.timezone.utc)


def name(cn):
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])


def cert(subject, key, issuer, ikey, start, end, ca):
    b = (x509.CertificateBuilder().subject_name(name(subject)).issuer_name(name(issuer))
         .public_key(key.public_key()).serial_number(x509.random_serial_number())
         .not_valid_before(day(start)).not_valid_after(day(end))
         .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True))
    if ca:
        b = b.add_extension(x509.KeyUsage(False, False, False, False, False, True, True, False, False), critical=True)
    else:
        b = (b.add_extension(x509.KeyUsage(True, False, False, False, False, False, False, False, False), critical=True)
             .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
             .add_extension(x509.SubjectAlternativeName([x509.DNSName("api.mock")]), critical=False))
    return b.sign(ikey, hashes.SHA256()).public_bytes(serialization.Encoding.PEM)


def main():
    os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    root, other, leaf = (ec.generate_private_key(ec.SECP256R1()) for _ in range(3))
    files = {
        "user/tls/roots/mock.pem": cert("Daphnis mock root", root, "Daphnis mock root", root, 2025, 2036, True),
        "tests/tls/api.mock.key": leaf.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                     serialization.NoEncryption()),
        "tests/tls/api.mock.pem": cert("api.mock", leaf, "Daphnis mock root", root, 2025, 2036, False),
        "tests/tls/expired.pem": cert("api.mock", leaf, "Daphnis mock root", root, 2024, 2025, False),
        "tests/tls/stranger.pem": cert("api.mock", leaf, "Stranger root", other, 2025, 2036, False),
    }
    for path, data in files.items():
        with open(path, "wb") as f:
            f.write(data)
        print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
