#!/usr/bin/env python3
"""check-k5.py TRANSCRIPT SCRIPT [NET]: checks one run of the K5 kernel against what Python can recompute.
NET is the network of the run: 0 (the default) is described next; 1, 2 and 3 are the tests of the page
tables, described at the end.

TRANSCRIPT is the serial stream of a run of the k5 flavor (network 0: a producer, an editor that
takes lines of input, and a sink that selects between them); SCRIPT is the file that was on the
serial input. Every check recomputes from bytes with hashlib or from the script; none trusts a
'yes' the kernel printed.
  the run ends as it should (final root, commit count, the run loop's last line)
  the commit lines are numbered 1 to N, and the root on each is the Merkle root of its four leaves
    (leaf pairs hashed under the tag 2, as docs/snapshot.md says); the final root is the last one
  the journal verifies: every entry's chain is SHA-256 of the task's previous chain and the entry,
    sequence numbers run 0, 1, 2 ... per task, the fuel stamps of a task never go down
  the editor's input entries are the script, chunked the way the kernel must chunk it (up to 7
    bytes, or fewer at a line end, which is then consumed and is not in the chunk), in order
  the sink made 36 select entries, 24 won by channel 0 and 12 by channel 1, and the bytes the
    kernel consumed are exactly the bytes of the script
  the single-owner walk ran at every commit (walks N, N commits)
  the boot tables hold no entry that is both writable and executable, and the hardware enforces it: a store
    into the code traps with error code 3 (a write to a present, read-only page) and a jump into data with
    error code 17 (0x11, an instruction fetch from a no-execute page)
  every snapshot (DAPH0001, docs/snapshot.md) is whole and verifies, decoded here: the digest of its body,
    its four leaves recomputed from the preimages it carries, the Merkle root (which is the root of the
    commit it was taken at), the journals against the chain heads in the kernel tables and against the J
    lines; and the last snapshot, taken at the end, is checked against a model of the network written
    here from the script and the journal alone (the producer's SHA-256 rounds, the editor's checksums,
    the sink's fold in the order of the journal's winners, the page that moved to the sink): a final
    state that is the right answer and not only a self-consistent one
Network 4: task 0 gives its page to task 1, which takes it into slot 3 and finds 77; task 0 then writes to
  the slot, which its tables no longer hold: the same record, task 1. Network 1: task 2 (index 1) writes to a page that is in the space of task 0 and not in its own: its fault
  record is host.error.trap_pf, vector 14, error code 2 (a write to a page that is not present), the address
  0x40000000 of the slot, IST 3, at the page_store call of src/ts_work.ci; task 0 wrote its own page (77).
  Networks 2 and 3 corrupt a space on purpose (one frame in two spaces; a page both writable and
  executable): the walk must say so at the first commit and the run must halt with no final root.
Prints PASS or FAIL per check; exits 1 on any FAIL."""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import k5lib  # noqa: E402

fail = 0


def check(ok, label, detail=""):
    global fail
    print(("PASS  " if ok else "FAIL  ") + label + ("" if ok else ": " + detail))
    if not ok:
        fail = 1


def chunks(script):
    """The chunks the kernel must read from the script: ([bytes], line_end_read)."""
    out, cur = [], b""
    for c in script:
        if c == 10:
            out.append((cur, 1))
            cur = b""
        else:
            cur += bytes([c])
            if len(cur) == 7:
                out.append((cur, 0))
                cur = b""
    if cur:
        out.append((cur, 0))
    return out


text = open(sys.argv[1]).read()
script = open(sys.argv[2], "rb").read()
net = int(sys.argv[3]) if len(sys.argv) > 3 else 0
cs = k5lib.commits(text)
if net in (2, 3, 5, 6, 7):
    want = {2: "walk: one frame is mapped writable by task 0 slot 0 and by task 1 slot 0\n",
            3: "walk: task 0 slot 0 is writable and executable\n",
            5: "walk: task 0 has table 2 wrong at entry 5\n",
            6: "walk: the pages of task 1 are not the pages the kernel says\n",
            7: "commit refused: a task has state outside the task modules\n"}[net]
    check(text.endswith(want + "halted\nruns: 0 faulted, then one entry returned\n") and not cs and "final root" not in text,
          "the first commit is refused with the right line and the run halts with no commit and no final root", text[-160:])
    sys.exit(fail)
m = re.search(r"final root ([0-9a-f]{64})\ncommits (\d+)\nwalks (\d+)\nrehashed (\d+)\n(page: [^\n]*? (\d+)\n)?runs: 0 faulted, then one entry returned\n$", text)
check(m is not None and bool(cs) and m[1] == cs[-1][2] and int(m[2]) == len(cs),
      "the run ends with its final root (the last commit's), the commit count and the run loop's line",
      "tail: %r" % text[-120:])
check(text.startswith("run 0\nDaphnis K5: the kernel keeps its books\nboot tables: no entry is both writable and executable\nwx: a store into the code traps, error code 3\nwx: a jump into data traps, error code 17\nwx: a jump into read-only data traps, error code 17\nrun: mode"),
      "the boot tables have no entry both writable and executable, and a store into the code (3), a jump into data and a jump into read-only data (17) trap", text[:300])
check(m is not None and int(m[3]) == len(cs), "the single-owner walk ran at every commit (%s walks, %d commits)" % (m[3] if m else "?", len(cs)))
if net == 0:
    check(m is not None and len(cs) <= int(m[4]) < 3 * len(cs),
          "only the tasks that ran are rehashed: %s task leaves made again in %d commits (%d if all were)" % (m[4] if m else "?", len(cs), 3 * len(cs)))
check([c[0] for c in cs] == list(range(1, len(cs) + 1)), "the commits are numbered 1 to %d" % len(cs))
bad = []
for n, t, root, lv in cs:
    a = k5lib.sha(b"\2", bytes.fromhex(lv[0]), bytes.fromhex(lv[1]))
    b = k5lib.sha(b"\2", bytes.fromhex(lv[2]), bytes.fromhex(lv[3]))
    if k5lib.sha(b"\2", a, b).hex() != root:
        bad.append(n)
check(not bad, "the root of every commit is the Merkle root of its four leaves, recomputed here", "commits %s" % bad[:5])

if net in (1, 4):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from faultrec import decode  # noqa: E402
    who, call = {1: ("2", "page_store(0, 0, 5)"), 4: ("1", "page_store(0, 0, 9)")}[net]
    f = re.search(r"task " + who + r" faulted\nfault: cint-core-1/fault/v2 (\d+) bytes\n([0-9a-f]+)\n", text)
    r = decode(bytes.fromhex(f[2])) if f else None
    I64 = lambda v: (0x14, v.to_bytes(8, "little"))  # noqa: E731
    U64 = lambda v: (0x24, v.to_bytes(8, "little"))  # noqa: E731
    check(f is not None and len(bytes.fromhex(f[2])) == int(f[1]) and r["code"] == 10 and r["operation"] == "host.error.trap_pf"
          and r["operands"] == [I64(14), U64(2), U64(0x40000000), U64(3)],
          "task %s faulted: host.error.trap_pf, vector 14, error code 2, address 0x40000000, IST 3" % who,
          str(r and (r["operation"], r["operands"])))
    src = open("src/ts_work.ci").read().split("\n")
    check(r is not None and r["position"][0] == "src/ts_work.ci" and call in src[r["position"][1] - 1],
          "the record names the %s call in src/ts_work.ci" % call, str(r and r["position"]))
    if net == 1:
        ok3, sn3 = k5lib.verify_snapshot(k5lib.snapshots(text)[-1][1])
        orec = int.from_bytes(sn3["tasks"][0]["state"][64 + 8 * 16:72 + 8 * 16], "little", signed=True) if ok3 else None
        check(orec == 0, "task 0 asked for the length of the last trap record after task 1 faulted and was told 0: a fault record is its task's, no other task can read it", str(orec))
    check(m is not None and m[6] == "77", "the page holds 77, in task 0 (it wrote it) in network 1 and in task 1, slot 3 (it took it) in network 4")
    sys.exit(fail)


def kernel_fields(pre):
    """(per task: kind, a, b, v, fuel, inbox value, inbox tag, jseq; per channel: open, sender, receiver, count, v0, v1; input consumed; slot masks)"""
    u = lambda o, n: int.from_bytes(pre[o:o + n], "little")  # noqa: E731
    tasks = [dict(kind=pre[1 + 78 * t], rest=[u(2 + 78 * t + 8 * k, 8) for k in range(4)], inbox=u(34 + 78 * t, 8), tag=pre[42 + 78 * t],
                  jseq=u(43 + 78 * t, 4)) for t in range(3)]
    chans = [dict(open=pre[235 + 20 * c], snd=pre[236 + 20 * c], rcv=pre[237 + 20 * c], cnt=pre[238 + 20 * c], v=[u(239 + 20 * c + 8 * k, 8) for k in range(2)]) for c in range(4)]
    return tasks, chans, u(315, 8), list(pre[323:326])


def residue_free(sn):
    tasks, chans, _, _ = kernel_fields(sn["kernel"])
    return all(t["kind"] != 0 or not any(t["rest"]) for t in tasks) and all(not any(c["v"][c["cnt"]:]) for c in chans)


if net == 8:
    snaps8 = [k5lib.verify_snapshot(b) for _, b in k5lib.snapshots(text)]
    check(bool(snaps8) and all(ok2 for ok2, _ in snaps8), "the snapshots are whole and verify", str(snaps8[:1]))
    st = snaps8[-1][1]["tasks"][2]["state"] if snaps8 and snaps8[-1][0] else b""
    init = bytes(64) + b"".join((v % 2 ** 64).to_bytes(8, "little") for v in [0, 0, 0, 0, 0, 0, 0, 24, 12, 0, 0, 0, 0, 0, 0, 0, -1])
    check(all(ok2 and sn["tasks"][1]["state"] == init for ok2, sn in snaps8 if ok2),
          "task 1 never touches its module state, so its block is absent and is encoded as the initial image (24 and 12 in the sink's variables, -1 in the last), in every snapshot")
    check(int.from_bytes(st[64 + 8 * 15:72 + 8 * 15], "little") == 2 ** 63 + 1 and snaps8[-1][1]["tasks"][0]["flags"] == 1,
          "the sink holds the most negative value but one that the producer sent (0x8000000000000001 in its state), through a channel, an inbox and a snapshot")
    sys.exit(fail)

entries = k5lib.journal_lines(text)
ok, why, per = k5lib.verify_journal(entries)
check(ok and len(entries) > 0, "the journal verifies: %d entries, every chain and sequence number" % len(entries), why)
stamps = {t: [k5lib.parse_entry(e)["fuel"] for e, _ in per.get(t, [])] for t in per}
check(all(all(a < b for a, b in zip(v, v[1:])) for v in stamps.values()),
      "the fuel stamps of each task go up from one entry to the next (every step costs fuel, and the fuel of all steps is summed)")
ed = [k5lib.parse_entry(e) for e, _ in per.get(1, [])]
want = chunks(script)
got = [(p["payload"][1:], p["payload"][0]) for p in ed if p["kind"] == 5]
check(got == want and all(p["kind"] == 5 for p in ed), "the editor's %d input entries are the script, chunked as specified" % len(want),
      "got %s want %s" % (got[:3], want[:3]))
sink = [k5lib.parse_entry(e) for e, _ in per.get(2, [])]
winners = [p["payload"][0] for p in sink if p["kind"] == 4]
check(len(sink) == 36 and winners.count(0) == 24 and winners.count(1) == 12 and 0 not in per,
      "the sink made 36 select entries, 24 won by channel 0 and 12 by channel 1; the producer made none",
      "%d entries, winners %s" % (len(sink), winners[:6]))
check(k5lib.input_consumed(entries) == len(script), "the bytes the kernel consumed are the %d bytes of the script" % len(script),
      "consumed %d" % k5lib.input_consumed(entries))

# ---- the snapshots ----
import hashlib  # noqa: E402
snaps = k5lib.snapshots(text)
parsed, bad = [], []
for n, b in snaps:
    ok2, sn = k5lib.verify_snapshot(b)
    if not ok2 or sn["commits"] != n:
        bad.append((n, sn if not ok2 else "commit field"))
    else:
        parsed.append(sn)
roots = {c[0]: c[2] for c in cs}
check(len(snaps) >= len(cs) // 5 and not bad, "all %d snapshots are whole and verify: digest, leaves from their preimages, root, chain heads" % len(snaps), str(bad[:2]))
check(all(sn["root"].hex() == roots.get(sn["commits"]) for sn in parsed) and snaps and snaps[-1][0] == len(cs),
      "each snapshot's root is the root of the commit it was taken at, and the last one is of the final commit")
jprefix = True
for sn in parsed:
    for t in range(3):
        if sn["journal"][t] != [e for e, _ in per.get(t, [])][:len(sn["journal"][t])]:
            jprefix = False
check(jprefix, "the journal in each snapshot is the prefix of the printed J lines of each task")
check(all(residue_free(sn) for sn in parsed), "no snapshot holds the residue of a request that was served, or a value past the count of a channel")

# the model
blk = bytearray(((7 + i) % 256) for i in range(64))
vals0 = []
for r in range(24):
    d = hashlib.sha256(bytes(blk)).digest()
    blk[:32] = d
    vals0.append(d[0] + d[31])
ch = chunks(script)[:12]
v = [sum(c << (8 * i) for i, c in enumerate(cb)) + len(cb) * 2 ** 56 for cb, _ in ch]
ecks, vals1 = 0, []
for x in v:
    ecks = (ecks * 31 + x) % 1000003
    vals1.append(ecks)
acc, i0, i1 = 0, 0, 0
for w in winners:
    if w == 0:
        val, i0 = vals0[i0], i0 + 1
    else:
        val, i1 = vals1[i1], i1 + 1
    acc = (acc * 31 + val * 2 + w) % 1000003
for x in v:
    acc = (acc * 31 + x) % 1000003


def state(sn, t):
    st = sn["tasks"][t]["state"]
    return st[:64], [int.from_bytes(st[64 + 8 * k:72 + 8 * k], "little") for k in range(12)]


if parsed:
    last = parsed[-1]
    b0, v0 = state(last, 0)
    b1, v1 = state(last, 1)
    b2, v2 = state(last, 2)
    page = last["tasks"][2]["pages"].get(0, {})
    words = [page.get(k, 0) for k in range(512)]
    # pround pready eline ephase ecks sphase sacc srem0 srem1 swait oval ophase
    # the variables a task never touches are the initial image of their block (srem0 24, srem1 12 are the
    # sink's, which the producer and the editor never touch; the others start at 0)
    untouched = v0[2:7] == [0] * 5 and v0[7:9] == [24, 12] and v0[9:] == [0] * 3 and v1[0:2] == [0, 0] and v1[5:6] == [0] and v1[7:9] == [24, 12] and v1[9:] == [0] * 3
    ktasks, kchans, kin, kmasks = kernel_fields(last["kernel"])
    check([t["kind"] for t in ktasks] == [0, 0, 0] and [t["jseq"] for t in ktasks] == [0, 12, 36] and kin == len(script)
          and kmasks == [0, 0, 1] and all(c["cnt"] == 0 for c in kchans),
          "the kernel's tables in the final snapshot: nothing pending, journal lengths 0, 12 and 36, %d bytes of input consumed, the page in task 2's slot 0, the channels empty" % len(script))
    check(untouched and v0[0] == 24 and v0[1] == 1 and b0 == bytes(blk) and v1[2] == 12 and v1[3] == 3 and v1[4] == ecks
          and v2[5] == 2 and v2[6] == acc and v2[7] == 0 and v2[8] == 0 and v2[9] == 0 and not last["tasks"][1]["pages"]
          and words[:12] == v and not any(words[12:]) and [t["flags"] for t in last["tasks"]] == [1, 1, 1],
          "the final snapshot is what the model says: producer block after 24 rounds, editor checksum %d, sink fold %d, the page (12 lines) in the sink's slot 0 and gone from the editor, and the variables a task never touches are the initial image" % (ecks, acc),
          "producer %s editor %s sink %s" % (v0, v1, v2))
sys.exit(fail)
