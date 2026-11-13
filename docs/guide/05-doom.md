# 05 Doom

Doom runs in the separate `deskplay` development image. The Daphnis 0.1.1 disk
image excludes Doom. The development build fetches the cint port of
linuxdoom 1.10 and Freedoom data from the revision listed in
[doom.pin](../../doom.pin).

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

Settings persist in `/home/doom.cfg` on the play volume. The play image supports
sound effects through QEMU's audio backend. Game saves are disabled.

After the run, `play.sh` copies the record (`g.lmp`) off the volume and replays it on the host, sealed. The replay's
last line must equal the live run's: the record is the proof of the game. In the desk's terminal, `. /doom.sh`
plays again.

## The sealed run

```
D="$(tools/doom/fetch.sh)"
cd "$D/data"
../bin/doom --sealed --headless e1m6.wad
```

Each tic prints a SHA-256 digest that includes the preceding digest, the tic,
the game state, and the rendered frame. `--demo FILE` replays a recorded game.

`check-doom.sh` compares sealed test runs on Linux and Daphnis.
`check-episode.sh` compares recorded episode runs with linuxdoom on Linux.
