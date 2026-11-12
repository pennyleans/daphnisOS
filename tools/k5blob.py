#!/usr/bin/env python3
"""k5blob.py: the run blob of K5 (docs/snapshot.md), the file QEMU's loader puts at 96 MiB.
  k5blob.py desc FILE MODE QUANTUM NET [AUDIT]  a run descriptor alone (mode 1: record; AUDIT 1 makes the kernel check
                                                every cached leaf at every commit)
  k5blob.py replay TRANSCRIPT FILE QUANTUM NET  mode 2: the whole journal of a recorded run, which
                                                the kernel feeds back instead of asking the schedule
  k5blob.py tamper TRANSCRIPT FILE QUANTUM NET TASK SEQ [chain]
                                                the same, but entry SEQ of TASK has its fuel stamp raised
                                                by one and the chains from there on are recomputed, so the
                                                blob is well formed and only the stamp is wrong (the kernel
                                                must refuse it: a replay is checked against the source). With
                                                chain, instead one byte of that entry's chain is changed and
                                                nothing is recomputed (the kernel must refuse the chain)
  k5blob.py restore TRANSCRIPT FILE QUANTUM NET [flip|rev|journal]
                                                mode 3: the last whole snapshot in TRANSCRIPT and the journal
                                                after it (killrun.py does this for a killed run). With flip, one
                                                hex digit of the snapshot is changed (the digest must refuse it);
                                                with rev, the program's revision in it is changed and the digest
                                                is made again (the kernel must refuse a snapshot of another build);
                                                with journal, one byte of a journal entry in it is changed and the
                                                digest is made again (the kernel must refuse a journal that is not
                                                the one the tables say)
The descriptor is 32 bytes: the magic DAPH0RUN, then u32 little endian: version 1, mode, quantum,
network, the length of the snapshot that follows (0), and the audit flag. A snapshot, if any, follows
the descriptor, and then the journal entries to replay: per task a u32 count, then each entry as a
length byte, the entry and the 32 byte chain it ends in. The journal of TRANSCRIPT is verified
(chains and sequence numbers) before a byte is written."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import k5lib  # noqa: E402

if len(sys.argv) in (6, 7) and sys.argv[1] == "desc":
    open(sys.argv[2], "wb").write(k5lib.descriptor(int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5]), 0, int(sys.argv[6]) if len(sys.argv) == 7 else 0))
elif len(sys.argv) == 6 and sys.argv[1] == "replay":
    entries = k5lib.journal_lines(open(sys.argv[2]).read())
    ok, why, per = k5lib.verify_journal(entries)
    if not ok:
        sys.exit("k5blob: the journal does not verify: " + why)
    open(sys.argv[3], "wb").write(k5lib.descriptor(2, int(sys.argv[4]), int(sys.argv[5])) + k5lib.tail_section(per))
elif len(sys.argv) in (8, 9) and sys.argv[1] == "tamper":
    import struct
    entries = k5lib.journal_lines(open(sys.argv[2]).read())
    ok, why, per = k5lib.verify_journal(entries)
    if not ok:
        sys.exit("k5blob: the journal does not verify: " + why)
    task, seq = int(sys.argv[6]), int(sys.argv[7])
    es = [e for e, _ in per[task]]
    p = k5lib.parse_entry(es[seq])
    if len(sys.argv) == 9:
        c = per[task][seq][1]
        per[task][seq] = (es[seq], bytes([c[0] ^ 1]) + c[1:])
        open(sys.argv[3], "wb").write(k5lib.descriptor(2, int(sys.argv[4]), int(sys.argv[5])) + k5lib.tail_section(per))
        sys.exit(0)
    es[seq] = es[seq][:-8] + struct.pack("<Q", p["fuel"] + 1)
    head, out = k5lib.ZERO, []
    for i, e in enumerate(es):
        head = k5lib.sha(head, e)
        out.append((e, head))
    per[task] = out
    open(sys.argv[3], "wb").write(k5lib.descriptor(2, int(sys.argv[4]), int(sys.argv[5])) + k5lib.tail_section(per))
elif len(sys.argv) in (6, 7) and sys.argv[1] == "restore":
    text = open(sys.argv[2]).read()
    blob, snapc, consumed, tail = k5lib.restore_blob(text, int(sys.argv[4]), int(sys.argv[5]))
    if len(sys.argv) == 7:
        snap = k5lib.best_snapshot(text)[1]
        if sys.argv[6] == "flip":
            bad = bytearray(snap)
            bad[100] ^= 1
        elif sys.argv[6] == "rev":
            bad = bytearray(snap)
            bad[8] ^= 1
            body = bytes(bad[:-k5lib.TRAILER])
            bad[-k5lib.TRAILER + 160:-k5lib.TRAILER + 192] = k5lib.sha(body)
        elif sys.argv[6] == "journal":
            bad = bytearray(snap)
            pos = k5lib.parse_snapshot(snap)["jstart"]
            for _ in range(3):
                n = int.from_bytes(bad[pos:pos + 4], "little")
                if n:
                    bad[pos + 5 + 8] ^= 1
                    break
                pos += 4 + n
            bad[-k5lib.TRAILER + 160:-k5lib.TRAILER + 192] = k5lib.sha(bytes(bad[:-k5lib.TRAILER]))
        else:
            sys.exit(__doc__)
        blob = blob.replace(snap, bytes(bad), 1)
    open(sys.argv[3], "wb").write(blob)
else:
    sys.exit(__doc__)
