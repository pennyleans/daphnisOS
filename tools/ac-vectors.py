#!/usr/bin/env python3
"""tools/ac-vectors.py: an independent oracle for AC-1b (docs/specs/2026-11-08-ac-accounts.md section 6).

`blake2b`: BLAKE2b digests from CPython's hashlib for the messages tests/ac/blake2b_test.ci checks.
`argon2id M T P SALTHEX PASS`: an Argon2id tag (RFC 9106) and the AC-D9 verifier, computed here in plain Python over
hashlib.blake2b, so check.sh can compare authd's answer (O/ubin/authd) at parameters the RFC's one vector does not reach.
This file is a test oracle only; nothing in an image runs it.
"""
import hashlib
import sys

MASK = (1 << 64) - 1


def msg(n):
    return bytes((i * 7 + (i >> 8)) & 255 for i in range(n))


def blake2b_vectors():
    key = bytes(range(64))
    print("abc64", hashlib.blake2b(b"abc").hexdigest())
    print("empty64", hashlib.blake2b(b"").hexdigest())
    print("kempty64", hashlib.blake2b(b"", key=key).hexdigest())
    for n in (127, 128, 129, 256, 1000):
        print("m%d_32" % n, hashlib.blake2b(msg(n), digest_size=32).hexdigest())
        print("km%d_64" % n, hashlib.blake2b(msg(n), key=key).hexdigest())
    print("k5abc16", hashlib.blake2b(b"abc", key=b"daphn", digest_size=16).hexdigest())


def le32(v):
    return v.to_bytes(4, "little")


def hprime(x, t):
    if t <= 64:
        return hashlib.blake2b(le32(t) + x, digest_size=t).digest()
    r = (t + 31) // 32 - 2
    v = hashlib.blake2b(le32(t) + x).digest()
    out = v[:32]
    for _ in range(2, r + 1):
        v = hashlib.blake2b(v).digest()
        out += v[:32]
    v = hashlib.blake2b(v, digest_size=t - 32 * r).digest()
    return out + v


def rotr(x, n):
    return ((x >> n) | (x << (64 - n))) & MASK


def bla(x, y):
    return (x + y + 2 * (x & 0xFFFFFFFF) * (y & 0xFFFFFFFF)) & MASK


def gb(v, a, b, c, d):
    v[a] = bla(v[a], v[b]); v[d] = rotr(v[d] ^ v[a], 32)
    v[c] = bla(v[c], v[d]); v[b] = rotr(v[b] ^ v[c], 24)
    v[a] = bla(v[a], v[b]); v[d] = rotr(v[d] ^ v[a], 16)
    v[c] = bla(v[c], v[d]); v[b] = rotr(v[b] ^ v[c], 63)


def pround(v, ix):
    gb(v, ix[0], ix[4], ix[8], ix[12]); gb(v, ix[1], ix[5], ix[9], ix[13])
    gb(v, ix[2], ix[6], ix[10], ix[14]); gb(v, ix[3], ix[7], ix[11], ix[15])
    gb(v, ix[0], ix[5], ix[10], ix[15]); gb(v, ix[1], ix[6], ix[11], ix[12])
    gb(v, ix[2], ix[7], ix[8], ix[13]); gb(v, ix[3], ix[4], ix[9], ix[14])


def fill(prev, ref, nxt, with_xor):
    r = [a ^ b for a, b in zip(ref, prev)]
    tmp = [a ^ b for a, b in zip(r, nxt)] if with_xor else list(r)
    for i in range(8):
        pround(r, [16 * i + k for k in range(16)])
    for i in range(8):
        pround(r, [2 * i + (k % 2) + 16 * (k // 2) for k in range(16)])
    return [a ^ b for a, b in zip(tmp, r)]


def words(b):
    return [int.from_bytes(b[8 * i:8 * i + 8], "little") for i in range(128)]


def argon2id(pwd, salt, t, m, p, tlen=32, key=b"", ad=b""):
    h = hashlib.blake2b(digest_size=64)
    for v in (p, tlen, m, t, 0x13, 2):
        h.update(le32(v))
    for x in (pwd, salt, key, ad):
        h.update(le32(len(x)) + x)
    h0 = h.digest()
    mp = 4 * p * (m // (4 * p))
    q = mp // p
    seg = q // 4
    mem = [[None] * q for _ in range(p)]
    for lane in range(p):
        mem[lane][0] = words(hprime(h0 + le32(0) + le32(lane), 1024))
        mem[lane][1] = words(hprime(h0 + le32(1) + le32(lane), 1024))
    zero = [0] * 128
    for ps in range(t):
        for sl in range(4):
            for lane in range(p):
                indep = ps == 0 and sl < 2
                addr = None
                z = None
                if indep:
                    z = [0] * 128
                    z[0], z[1], z[2], z[3], z[4], z[5] = ps, lane, sl, mp, t, 2
                start = 2 if (ps == 0 and sl == 0) else 0
                if indep and start == 2:
                    z[6] += 1
                    addr = fill(zero, fill(zero, z, zero, False), zero, False)
                for i in range(start, seg):
                    col = sl * seg + i
                    prev = mem[lane][col - 1] if col > 0 else mem[lane][q - 1]
                    if indep:
                        if i % 128 == 0:
                            z[6] += 1
                            addr = fill(zero, fill(zero, z, zero, False), zero, False)
                        pr = addr[i % 128]
                    else:
                        pr = prev[0]
                    j1 = pr & 0xFFFFFFFF
                    rl = (pr >> 32) % p
                    if ps == 0 and sl == 0:
                        rl = lane
                    same = rl == lane
                    if ps == 0:
                        if sl == 0:
                            area = i - 1
                        elif same:
                            area = sl * seg + i - 1
                        else:
                            area = sl * seg + (-1 if i == 0 else 0)
                    else:
                        if same:
                            area = q - seg + i - 1
                        else:
                            area = q - seg + (-1 if i == 0 else 0)
                    x = (j1 * j1) >> 32
                    rel = area - 1 - ((area * x) >> 32)
                    st = 0 if ps == 0 or sl == 3 else (sl + 1) * seg
                    ref = mem[rl][(st + rel) % q]
                    if ps == 0:
                        mem[lane][col] = fill(prev, ref, zero, False)
                    else:
                        mem[lane][col] = fill(prev, ref, mem[lane][col], True)
    c = mem[0][q - 1]
    for lane in range(1, p):
        c = [a ^ b for a, b in zip(c, mem[lane][q - 1])]
    cb = b"".join(w.to_bytes(8, "little") for w in c)
    return hprime(cb, tlen)


def main():
    if sys.argv[1] == "blake2b":
        blake2b_vectors()
    elif sys.argv[1] == "rfc9106":
        print(argon2id(b"\x01" * 32, b"\x02" * 16, 3, 32, 4, 32, b"\x03" * 8, b"\x04" * 12).hex())
    elif sys.argv[1] == "argon2id":
        m, t, p = int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
        salt = bytes.fromhex(sys.argv[5])
        pwd = sys.argv[6].encode()
        out = argon2id(pwd, salt, t, m, p)
        ver = hashlib.blake2b(b"daphnis-verify", key=out, digest_size=32).hexdigest()
        print("tag", out.hex())
        print("verifier", ver)


if __name__ == "__main__":
    main()
