#!/usr/bin/env python3
"""killrun.py: kill the K5 machine anywhere, restore it, finish, and compare with the run that was
never killed (the exit gate's "unsaved work is never lost").

  killrun.py IMAGE REF SCRIPT WORKDIR SEED N QUANTUM NET [JOBS]     (N may be `all`: see below)

IMAGE is a k5 kernel, REF the transcript of the run of it that was never killed (same quantum, same
script, record mode), SCRIPT the serial input of that run. For each of N kill points, chosen by a
generator seeded with SEED from the length of REF:
  1. the machine is started again and really killed (SIGKILL) as soon as it has written the chosen number
     of bytes to the serial port; what is durable is then exactly that many bytes: the transcript is
     cut there, mid line if the point falls mid line (so the cut classes depend on the seed and on REF,
     not on how fast the machine ran). Four classes in turn: anywhere, inside a journal line, inside a
     commit line, inside a snapshot;
  2. the restore blob is made from the cut transcript alone: the last snapshot that is whole and verifies
     (digest, leaves, root, chains) with the journal entries after it, or the whole journal if there is no
     snapshot yet; the rest of the script (what the user types after the last journaled input) goes on
     the serial input;
  3. the machine is started on that blob and runs to its end.
Then the restored run must: exit 33; print the final root of REF; have commit lines that, appended to
the cut run's commits up to the snapshot's, are exactly the commit lines of REF (every root and leaf);
have a journal that, merged with the cut run's, is exactly the journal of REF; and print snapshots equal,
byte for byte, to REF's at the same commits. With N = all there is one kill point after each snapshot of REF instead, so that the machine is restored from every
snapshot it wrote (the inbox a task has been given and not yet used, a faulted task, a task past its last step).
Prints one line per kill and PASS or FAIL for the lot."""
import os
import random
import re
import signal
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import k5lib  # noqa: E402

RUN = os.path.join(HERE, "run-qemu.sh")


def qemu(image, blob, out, stdin, kill_at=None):
    """Runs run-qemu.sh on image with the blob; returns (status, was_killed)."""
    env = dict(os.environ, QEMU_EXTRA="-device loader,file=%s,addr=0x6000000,force-raw=on" % blob, STDIN_FILE=stdin)
    p = subprocess.Popen([RUN, image, out], env=env, stdout=subprocess.PIPE, start_new_session=True)
    if kill_at is not None:
        while p.poll() is None:
            try:
                if os.path.getsize(out) >= kill_at:
                    os.killpg(p.pid, signal.SIGKILL)
                    p.wait()
                    return None, True
            except OSError:
                pass
            time.sleep(0.0005)
    status = p.communicate()[0].decode().strip()
    return (int(status) if status else None), False


def line_spans(text, prefix):
    return [(m.start(), m.end()) for m in re.finditer(r"^" + prefix + r".*\n", text, re.M)]


def plan(ref, n, seed):
    if n == "all":   # one cut just after each snapshot: the machine is restored from every snapshot it ever wrote
        return [("after snapshot %s" % m[1], m.end() + 1) for m in re.finditer(r"^S end (\d+)\n", ref, re.M)]
    n = int(n)
    rng = random.Random(seed)
    spans = {"journal": line_spans(ref, "J "), "commit": line_spans(ref, "C "), "snapshot": line_spans(ref, "[0-9a-f]{500,}")}
    out = []
    for i in range(n):
        cls = ["anywhere", "journal", "commit", "snapshot"][i % 4]
        if cls == "anywhere" or not spans[cls]:
            out.append((cls, rng.randrange(1, len(ref))))
        else:
            a, b = rng.choice(spans[cls])
            out.append((cls, rng.randrange(a + 1, b - 1)))
    ends = [m.end() for m in re.finditer(r"^S end \d+\n", ref, re.M)]
    out[-1] = ("after the last snapshot", ends[-1] + 1)   # the whole final snapshot is durable: restore from it
    return out


def one(i, cls, at, a):
    image, ref, script, work, quantum, net, refd = a
    d = os.path.join(work, "kill%02d" % i)
    os.makedirs(d, exist_ok=True)
    blob0 = os.path.join(d, "start.blob")
    open(blob0, "wb").write(k5lib.descriptor(1, quantum, net))
    killed_out = os.path.join(d, "killed.txt")
    status, was_killed = qemu(image, blob0, killed_out, script, kill_at=at)
    cut = open(killed_out, "rb").read()[:at].decode("ascii", "replace")
    last = cut.rsplit("\n", 1)[-1]
    landed = "mid " + ("snapshot" if re.match(r"[0-9a-f]{20}", last) or last.startswith("S ") else "journal line" if last.startswith("J") else "commit line" if last.startswith("C") else "line") if last else "at a line end"
    try:
        blob, snapc, consumed, tail = k5lib.restore_blob(cut, quantum, net)
    except ValueError as e:
        return dict(i=i, ok=False, why="blob: %s" % e, cls=cls, at=at, landed=landed, killed=was_killed)
    open(os.path.join(d, "restore.blob"), "wb").write(blob)
    open(os.path.join(d, "rest.in"), "wb").write(script_bytes(script)[consumed:])
    rest_out = os.path.join(d, "restored.txt")
    status, _ = qemu(image, os.path.join(d, "restore.blob"), rest_out, os.path.join(d, "rest.in"))
    rest = open(rest_out).read()
    why = []
    if status != 33:
        why.append("exit status %s" % status)
    if k5lib.final_root(rest) != refd["final"]:
        why.append("final root %s" % k5lib.final_root(rest))
    pre = [c for c in k5lib.commits(cut) if c[0] <= snapc]
    if pre + k5lib.commits(rest) != refd["commits"]:
        why.append("the commit lines do not stitch to the reference's")
    jm = {}
    for e, c in k5lib.journal_lines(cut) + k5lib.journal_lines(rest):
        jm[(e[0], k5lib.parse_entry(e)["seq"])] = (e, c)
    if [jm[k] for k in sorted(jm)] != refd["journal"]:
        why.append("the merged journal is not the reference's")
    for n, b in k5lib.snapshots(rest):
        if refd["snaps"].get(n) != b:
            why.append("the snapshot of commit %d differs from the reference's" % n)
    return dict(i=i, ok=not why, why="; ".join(why), cls=cls, at=at, landed=landed, killed=was_killed, snap=snapc, tail=tail, consumed=consumed)


def script_bytes(path):
    return open(path, "rb").read()


if __name__ == "__main__":
    if len(sys.argv) < 9:
        sys.exit(__doc__)
    image, reff, script, work, seed, n, quantum, net = sys.argv[1:9]
    jobs = int(sys.argv[9]) if len(sys.argv) > 9 else 8
    ref = open(reff).read()
    if k5lib.final_root(ref) is None:
        sys.exit("FAIL: the reference run has no final root")
    ok, why, per = k5lib.verify_journal(k5lib.journal_lines(ref))
    refd = dict(final=k5lib.final_root(ref), commits=k5lib.commits(ref), snaps=dict(k5lib.snapshots(ref)),
                journal=[x for t in sorted(per) for x in per[t]])
    refd["journal"].sort(key=lambda x: (x[0][0], k5lib.parse_entry(x[0])["seq"]))
    os.makedirs(work, exist_ok=True)
    pts = plan(ref, n if n == "all" else int(n), int(seed))
    args = (image, ref, script, work, int(quantum), int(net), refd)
    with ThreadPoolExecutor(max_workers=jobs) as ex:
        res = list(ex.map(lambda ia: one(ia[0], ia[1][0], ia[1][1], args), enumerate(pts)))
    good = 0
    for r in res:
        print("kill %2d: cut at byte %6d of %d (%s, %s)%s: restored from commit %s with %s journal entries to replay: %s" % (
            r["i"], r["at"], len(ref), r["cls"], r["landed"], "" if r["killed"] else " [the machine had already finished]",
            r.get("snap", "?") or "none (restarted from the journal)", r.get("tail", "?"), "ok" if r["ok"] else "FAIL " + r["why"]))
        good += r["ok"]
    print("%s: %d of %d kill points restored to the uninterrupted run (final root %s, every commit root, the journal and the snapshots)" % (
        "PASS" if good == len(res) else "FAIL", good, len(res), refd["final"]))
    print("classes of the cut: %s" % ", ".join(sorted({r["landed"] for r in res})))
    sys.exit(0 if good == len(res) else 1)
