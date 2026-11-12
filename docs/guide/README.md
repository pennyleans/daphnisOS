# Daphnis userland guide

Draft, 2026-11-06. Fact source for the public copy pass (`docs/release/OPEN-SOURCE.md`).
Every command here was read from the tree at that commit; the gate named on each page is what proves it.

| page | piece | image (flavor) that carries it | gate |
| --- | --- | --- | --- |
| [01-build.md](01-build.md) | build, boot, run the gates | all | `check.sh` and the 11 stage gates |
| [02-desk.md](02-desk.md) | the desk: windows, desktops, Super menu, switcher, Settings | `hdesk`, `deskplay` | `check-hybrid.sh` |
| [03-cish.md](03-cish.md) | `cish`, the shell | every image a person uses | `check-cish.sh` |
| [04-ced.md](04-ced.md) | `ced`, the editor | `desk`, `hdesk`, `deskplay`, `desknet`, `cish` | `check-editor.sh` |
| [05-doom.md](05-doom.md) | Doom in a window, the sealed run, the record | `deskplay` (play), `doom` (sealed) | `check-doom.sh`, `check-episode.sh` |
| [06-files.md](06-files.md) | files, directories, the `/disk` volume, grants | every image; `/disk` with a volume | `check.sh`, `check-disk.sh` |
| [07-network.md](07-network.md) | TCP, UDP, names, `grant net` | `net`, `desknet` | `check-net.sh` |
| [08-audio.md](08-audio.md) | `/dev/dsp`, the mixer, the OPL3 | gate images | `check-audio.sh`, `check-opl.sh` |
| [09-agent.md](09-agent.md) | `talk` and `agent`: Claude in a terminal tile | `desknet` | `check-agent.sh` |

## Two desks

| desk | program | flavor | state |
| --- | --- | --- | --- |
| the hybrid desk | `hdesk` | `hdesk`, `deskplay` | current: desktops 1 to 9, float and tile, Super menu, switcher, Settings, mouse |
| the first desk | `tiler` | `desk`, `desknet` | W-4: two fixed tiles (shell over doom); still the desk of the network and agent images |

The agent and network walkthroughs run in the first desk until `desknet` moves to `hdesk`.

## Not in any image yet

Doom's sound and music (AU-5, AU-6, AU-8), a native core tool set (SW-3 B; busybox applets stand in), packages
(SW-4 open), job control and signal delivery, UTF-8 text, files over 64 KiB made inside Daphnis, real hardware
(stage HW, specified only).
