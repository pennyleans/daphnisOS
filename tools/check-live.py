#!/usr/bin/env python3
"""tools/check-live.py TRANSCRIPT: G-1, the live flavor's run (src/main_live.ci) after check-doom.sh typed its
script through the QEMU monitor (forward held, a turn on the keyboard and one on the mouse, Ctrl and the left
button to fire, Esc). A live run is not pinned, so this checks what the input must have done: the run started
and ended at Esc with status 0 after at least one tic, the player moved and turned, ticcmds carried the fire
button (the clip is no witness: a pickup refills it), and no frames are held after the runs (the volume's cache
holds its own); G-2: the run played no more tics than the wall clock passed. Prints PASS or FAIL per check; exits 1 on any FAIL."""
import re
import sys

import guestlines

POSE = re.compile(r"x (-?\d+) y (-?\d+) angle (-?\d+) health (-?\d+) clip (-?\d+)$")


def main(path):
    lines = guestlines.lines(open(path, encoding="utf-8", errors="replace").read())
    fails = 0

    def check(ok, label):
        nonlocal fails
        print(("PASS  " if ok else "FAIL  ") + label)
        fails += not ok

    start = next((POSE.search(l) for l in lines if l.startswith("doom: live start ")), None)
    end_line = next((l for l in lines if l.startswith("doom: live end tics ")), None)
    end = POSE.search(end_line) if end_line else None
    check(start is not None and end is not None, "the run printed its start and end poses")
    if start is None or end is None:
        return 1
    tics = int(end_line.split()[4])
    attacks = int(end_line.split()[7])
    sx, sy, sa, _, sc = (int(v) for v in start.groups())
    ex, ey, ea, eh, ec = (int(v) for v in end.groups())
    check(tics > 0, "the run played %d tics" % tics)
    check("doom: no input device" not in "\n".join(lines), "the input device opened")
    check("daphnis: exit 0" in lines, "doom ended with status 0 (Esc)")
    check((ex, ey) != (sx, sy), "the player moved: (%d, %d) to (%d, %d)" % (sx, sy, ex, ey))
    check(ea != sa, "the player turned: angle %d to %d" % (sa, ea))
    check(attacks > 0, "the player fired: %d ticcmds with BT_ATTACK (clip %d to %d)" % (attacks, sc, ec))
    # G-2: the tics follow the wall clock (CLOCK_BOOTTIME, the PIT): never more tics than wall tics passed,
    # one draw per frame, and a frame plays at least one tic
    pace = next((l.split() for l in lines if l.startswith("doom: live frames ")), None)
    if pace is None:
        check(False, "the run printed its frames and wall tics")
    else:
        frames, wall = int(pace[3]), int(pace[6])
        check(0 < frames <= tics + 1 and tics <= wall, "paced at 35 Hz: %d tics in %d wall tics (%.1f s), %d frames drawn" % (tics, wall, wall / 35, frames))
    pools = [l for l in lines if l.startswith("daphnis: pool frames free ")]
    check(len(pools) >= 1 and len(set(pools)) == 1, "no frames held after the runs: %s" % (pools[-1][len("daphnis: pool frames free "):] if pools else "no pool line"))
    # G-4: the record. The live run replayed its record in memory: the chain at its end, the pose and the
    # simulation state equal the live run's; then `doom --sealed --demo home/g.lmp`, a second process reading
    # the record back from the volume, printed the same chain at the same tic and ends in the same pose.
    live = next((l.split() for l in lines if l.startswith("doom: live tics ")), None)
    poses = [(l.split()[4], POSE.search(l).groups()) for l in lines if l.startswith("doom: replay end tics ") and POSE.search(l)]
    sealed = [l.split() for l in lines if re.fullmatch(r"doom: tic \d+ sha256 [0-9a-f]{64}", l)]
    check(live is not None, "the live run printed its end chain")
    check("doom: the replay's simulation state equals the live run's" in lines, "the record replays the live run: the simulation state at its end is the live run's")
    check(len(poses) == 2 and all(p == (end_line.split()[4], end.groups()) for p in poses),
          "both replays (in memory, and the sealed run from the volume) end at the live run's tic and pose")
    check(live is not None and len(sealed) > 0 and sealed[-1][2] == live[3] and sealed[-1][4] == live[5],
          "doom --sealed --demo home/g.lmp prints the live run's chain: tic %s sha256 %s" % (live[3], live[5][:16]) if live else "the sealed replay's chain")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
