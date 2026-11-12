"""k5lib.py: reading what a K5 kernel prints (docs/snapshot.md). Shared by k5blob.py, check-k5.py,
diverge.py and killrun.py. Python only checks and carries bytes; every hash it computes it
computes with hashlib from the bytes of the format, not from anything the kernel claims."""
import hashlib
import re
import struct

ZERO = b"\0" * 32
MAGIC_RUN = b"DAPH0RUN"
MAGIC_SNAP = b"DAPH0001"
MAGIC_END = b"DAPHEND0"


def sha(*parts):
    h = hashlib.sha256()
    for p in parts:
        h.update(p)
    return h.digest()


# ---- the journal ----

def parse_entry(e):
    """entry bytes -> dict(task, seq, kind, payload, fuel); None if malformed"""
    if len(e) < 15:
        return None
    task, seq, kind, plen = e[0], struct.unpack_from("<I", e, 1)[0], e[5], e[6]
    if len(e) != 15 + plen:
        return None
    return dict(task=task, seq=seq, kind=kind, payload=e[7:7 + plen], fuel=struct.unpack_from("<Q", e, 7 + plen)[0])


def journal_lines(text):
    """The complete J lines of a transcript, in order: [(entry bytes, chain bytes)]. A line that is
    cut (a kill) or malformed ends the list: what is durable is what is whole."""
    out = []
    for m in re.finditer(r"^J ([0-9a-f]+) ([0-9a-f]{64})\n", text, re.M):
        out.append((bytes.fromhex(m[1]), bytes.fromhex(m[2])))
    return out


def verify_journal(entries):
    """Checks every entry's chain (SHA-256 of the task's previous chain and the entry, from 32 zero
    bytes) and that sequence numbers run 0, 1, 2 ... per task. Returns (ok, why, per_task)."""
    heads, seqs, per = {}, {}, {}
    for e, c in entries:
        p = parse_entry(e)
        if p is None:
            return False, "malformed entry %s" % e.hex(), per
        t = p["task"]
        if p["seq"] != seqs.get(t, 0):
            return False, "task %d: sequence %d, wanted %d" % (t, p["seq"], seqs.get(t, 0)), per
        want = sha(heads.get(t, ZERO), e)
        if want != c:
            return False, "task %d seq %d: chain does not verify" % (t, p["seq"]), per
        heads[t] = want
        seqs[t] = p["seq"] + 1
        per.setdefault(t, []).append((e, c))
    return True, "", per


def input_consumed(entries):
    """The bytes of the serial script the entries consumed: for each input entry (kind 5), its chunk
    and the line end if it was read (payload[0])."""
    n = 0
    for e, _ in entries:
        p = parse_entry(e)
        if p and p["kind"] == 5 and p["payload"]:
            n += len(p["payload"]) - 1 + p["payload"][0]
    return n


# ---- commits ----

def commits(text):
    """[(number, task, root hex, [leaf hex x4])] from the C lines."""
    out = []
    for m in re.finditer(r"^C (\d+) (\d+) ([0-9a-f]{64})((?: [0-9a-f]{64}){4})\n", text, re.M):
        out.append((int(m[1]), int(m[2]), m[3], m[4].split()))
    return out


def final_root(text):
    m = re.search(r"^final root ([0-9a-f]{64})$", text, re.M)
    return m[1] if m else None


# ---- the blob ----

def descriptor(mode, quantum, net, snapshot_len=0, audit=0):
    return MAGIC_RUN + struct.pack("<IIIIII", 1, mode, quantum, net, snapshot_len, audit)


def tail_section(per_task, ntasks=3, first=None):
    """per_task: {task: [(entry, chain)]}; first: {task: first sequence number to include}."""
    first = first or {}
    out = b""
    for t in range(ntasks):
        es = [(e, c) for e, c in per_task.get(t, []) if parse_entry(e)["seq"] >= first.get(t, 0)]
        out += struct.pack("<I", len(es))
        for e, c in es:
            out += bytes([len(e)]) + e + c
    return out


# ---- snapshots (docs/snapshot.md) ----

TRAILER = 200          # four leaves, the root, the digest of everything before, DAPHEND0
KERNEL_PRE = 326       # tag, 3 tasks x 78, 4 channels x 20, input consumed, 3 slot masks
TASK_BLOCK = 78        # in the kernel preimage: request (33), inbox (9), journal seq (4), chain (32)


def merkle(leaves):
    return sha(b"\2", sha(b"\2", leaves[0], leaves[1]), sha(b"\2", leaves[2], leaves[3]))


def snapshots(text):
    """[(commit number, bytes)] for every snapshot whose lines are whole: 'S begin N', one line of hex,
    'S end N'. A snapshot cut by a kill has no 'S end' and is not listed."""
    out = []
    for m in re.finditer(r"^S begin (\d+)\n([0-9a-f]+)\nS end \1\n", text, re.M):
        if len(m[2]) % 2 == 0:
            out.append((int(m[1]), bytes.fromhex(m[2])))
    return out


def parse_snapshot(b):
    """Decodes a DAPH0001 snapshot; raises ValueError if it is not one. Returns a dict with the
    revision, the scheduler's place, per task its preimage, flags, fuel, module state bytes and
    pages (each a dict of its non-zero words by index), the kernel preimage, the journals (a list of entries per task) and the trailer."""
    def u(pos, n):
        return int.from_bytes(b[pos:pos + n], "little")
    if len(b) < 54 + TRAILER or b[:8] != MAGIC_SNAP:
        raise ValueError("not a DAPH0001 snapshot")
    snap = dict(revision=b[8:40], next_t=b[40], ran=b[41], commits=u(42, 4), walks=u(46, 4), rehashes=u(50, 4), tasks=[], journal=[])
    pos = 54
    for t in range(3):
        start = pos
        if b[pos] != 0 or b[pos + 1] != t:
            raise ValueError("task %d: bad preimage tag" % t)
        flags, fuel, slen = b[pos + 2], u(pos + 3, 8), u(pos + 11, 4)
        state = b[pos + 15:pos + 15 + slen]
        pos += 15 + slen
        np, pos, pages = b[pos], pos + 1, {}
        for _ in range(np):
            slot, nz = b[pos], u(pos + 1, 2)
            pos += 3
            pages[slot] = {}
            for _ in range(nz):
                pages[slot][u(pos, 2)] = u(pos + 2, 8)
                pos += 10
        snap["tasks"].append(dict(pre=b[start:pos], flags=flags, fuel=fuel, state=state, pages=pages))
    snap["kernel"] = b[pos:pos + KERNEL_PRE]
    pos += KERNEL_PRE
    snap["jstart"] = pos
    for t in range(3):
        n = u(pos, 4)
        raw, pos, es = b[pos + 4:pos + 4 + n], pos + 4 + n, []
        i = 0
        while i < len(raw):
            es.append(raw[i + 1:i + 1 + raw[i]])
            i += 1 + raw[i]
        snap["journal"].append(es)
    snap["trailer"] = b[pos:]
    if len(snap["trailer"]) != TRAILER:
        raise ValueError("trailer is %d bytes" % len(snap["trailer"]))
    snap["body"] = b[:pos]
    return snap


def verify_snapshot(b):
    """(True, snapshot) if the bytes are a snapshot that is whole and says what it hashes to: the digest
    of the body, the four leaves from the preimages, the root, the closing magic, and the chain heads
    in the kernel tables against the journals; else (False, why)."""
    try:
        s = parse_snapshot(b)
    except (ValueError, IndexError) as e:
        return False, str(e)
    tr = s["trailer"]
    leaves = [sha(t["pre"]) for t in s["tasks"]] + [sha(s["kernel"])]
    if sha(s["body"]) != tr[160:192]:
        return False, "the digest of the body is wrong"
    if tr[:128] != b"".join(leaves) or tr[128:160] != merkle(leaves) or tr[192:] != MAGIC_END:
        return False, "the trailer is not the leaves, the root and the end"
    for t in range(3):
        blk = s["kernel"][1 + TASK_BLOCK * t:1 + TASK_BLOCK * (t + 1)]
        jseq, head = int.from_bytes(blk[42:46], "little"), blk[46:78]
        h = ZERO
        for e in s["journal"][t]:
            h = sha(h, e)
        if jseq != len(s["journal"][t]) or head != h:
            return False, "task %d: the journal does not end in the chain head of the tables" % t
    s["leaves"], s["root"] = leaves, merkle(leaves)
    return True, s


def best_snapshot(text):
    """The last snapshot in the transcript that verifies: (commit number, bytes, parsed) or None."""
    for n, b in reversed(snapshots(text)):
        ok, s = verify_snapshot(b)
        if ok and s["commits"] == n:
            return n, b, s
    return None


def restore_blob(text, quantum, net, ntasks=3):
    """The blob that restores a run killed after `text` was written: the last whole snapshot and the
    journal entries after it, or, if there is none, the whole journal with no snapshot (the machine
    starts again and the journal brings it to where it was). Returns (blob, snapshot commit or 0,
    bytes of input consumed, number of tail entries)."""
    entries = journal_lines(text)
    ok, why, per = verify_journal(entries)
    if not ok:
        raise ValueError("journal: " + why)
    best = best_snapshot(text)
    if best is None:
        return descriptor(2, quantum, net) + tail_section(per), 0, input_consumed(entries), len(entries)
    n, b, s = best
    first = {t: len(s["journal"][t]) for t in range(ntasks)}
    tail = tail_section(per, first=first)
    return (descriptor(3, quantum, net, len(b)) + b + tail, n, input_consumed(entries),
            sum(len(per.get(t, [])) - first[t] for t in range(ntasks)))
