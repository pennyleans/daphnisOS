# 05 Doom

A port of linuxdoom-1.10 to cint (`user/ci/doom/`, GPL-2.0), playing Freedoom Phase 1 data (BSD-3-Clause). It is a
test fixture and an optional program, not part of the base image (SW-1 C). It draws what vanilla Doom draws, pixel
for pixel: every frame's SHA-256 equals linuxdoom built on the host (`tools/doomref/`).

## Play episode 1 in a desk window

Needs `/dev/kvm`, a display, QEMU, musl-gcc and e2fsprogs.

```
tools/play.sh              # 1080x1920 portrait
tools/play.sh 1920x1080    # any WxH
```

The desk boots with Doom in a window at its largest integer scale (3x, 960 x 600) and Doom's own menu.

| keys | action |
| --- | --- |
| Esc | open or close the menu |
| arrows, Enter, Backspace | move, choose, back |
| New Game | pick a skill; Nightmare asks to confirm |
| Options | Messages, Screen Size (or `-` and `=`), Mouse Sensitivity |
| Controls | Enter on a row, then a key, rebinds it; mouse on or off; Defaults |
| arrows | turn and move |
| Alt, `,` and `.` | strafe |
| Shift | run |
| Ctrl | fire |
| Space | use |
| 1 to 8 | weapons |
| F10 then y | quit and write the record |

Settings live in `/disk/doom.cfg` and carry over. Saves are off. There is no sound yet (AU-5, AU-6, AU-8).

After the run, `play.sh` copies the record (`g.lmp`) off the volume and replays it on the host, sealed. The replay's
last line must equal the live run's: the record is the proof of the game. In the desk's terminal, `. ./doom.sh`
plays again.

## The sealed run

```
cd user/ci/doom/data && ../../../bin/doom --sealed --headless e1m6.wad
```

Each tic prints one line, `doom: tic T sha256 H_t`, with `H_t = SHA-256(H_(t-1) | t | S_t | F_t)`: the state
modules and the frame of that tic. `tests/expected/doom.tics` pins the 350 lines. A build with a one-bit canary
desyncs at every tic. `--demo FILE` replays any record.

## What the gates prove

| gate | proof |
| --- | --- |
| `check-doom.sh` (26) | the sealed run equals the pin on Linux (three builds) and under Daphnis, alone and after a churn of memory, files, pipes and killed processes; the canary desyncs; the screen digest is the last frame |
| `check-episode.sh` (16) | three test demos over all of E1 (11,000 tics, every map, the finale) equal linuxdoom line for line; Linux only |
| `check.sh` | the WAD, texture and level counts and the 350 tics' player words and frames equal the reference |
