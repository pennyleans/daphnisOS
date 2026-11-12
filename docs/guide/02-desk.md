# 02 The desk (`hdesk`)

`hdesk` is the desk: a cint program that takes the framebuffer and draws every window itself, with no display
server. Nine desktops under a 24 px bar. A window is a terminal (a pty running `cish`) or a pixel client (a program
that opened `/dev/fb0`, such as Doom or `mwin`). The kernel copies each client's private surface into its window.

## Start it

```
B=$DAPHNIS_BUILD
make FLAVORS=hdesk COMPILERS=gcc O=$B
PLAY=1 QEMU_TIMEOUT=0 MODE=1920x1080 POOL=max MEM=4096 INITRD=$B/hdesk/initrd.cpio \
    tools/run-qemu.sh $B/gcc-hdesk/kernel32.elf $B/desk.txt
```

Click into the QEMU window for the keyboard; Ctrl+Alt+G releases it. The desk boots with one terminal filling the
screen. `exit` in the first terminal ends the desk. `tools/play.sh` boots the same desk with Doom (05-doom.md).

The image holds `hdesk`, `cish` (as `/sh` and `/bin/sh`), busybox applets in `/bin`, `ced`, `grant`, `mwin`,
`mcifb`, Doom with `e1m6.wad`, and the text files of `tests/image/`.

## Keys

| keys | action |
| --- | --- |
| Super (tap alone) | open or close the Super menu |
| Super+Enter | new terminal |
| Super+arrows | focus the nearest window that way |
| Super+Shift+arrows | swap a tiled window; move a floating one |
| Super+Ctrl+arrows | resize a floating window |
| Super+1 .. 9 | go to desktop N |
| Super+Shift+1 .. 9 | send the focused window to desktop N |
| Super+f | float or tile |
| Super+z | monocle (one window fills the desktop) |
| Super+m, Super+Shift+m | minimize, restore |
| Super+q | SIGTERM to the focused window's foreground process |
| Super+= , Super+- | UI scale up, down |
| Alt+Tab, Alt+Shift+Tab, Super+Tab | switcher: recent windows; Tab and arrows move; release chooses; Esc closes |

## Mouse

| action | result |
| --- | --- |
| click a window | focus it |
| click in the focused pixel window | the window takes the pointer (Doom's mouse) |
| Super + left drag | move |
| Super + right drag | resize |
| click the mark in the bar | Super menu |
| click a desktop number in the bar | go there |
| click the focused window's title | App menu: float or tile, minimize, monocle, move to a desktop, terminate |

## Super menu

Type to filter; prefixes rank first, then letters in order. Sections: open windows (with their desktop), minimized
windows, commands (`new terminal`, `float or tile`, `monocle`, `minimize`, `restore`, `terminate`, `settings`).

## Settings

Open from the Super menu (`settings`). Esc or Super+q closes it. Up and Down move between the page row and the
setting row; Left and Right change the page on the first and the value on the second.

| page | line | keys |
| --- | --- | --- |
| Display | Resolution: 640x480, 800x600, 1024x768, 1280x720, 1280x1024, 1600x900, 1920x1080, 2560x1440, 3840x2160, 720x1280, 768x1024, 1080x1920 | Left, Right pick; Enter switches the screen live |
| Display | UI scale | Super+= , Super+- |
| Display | persistence | with a volume at `/disk` the choice is kept for the next boot; without one it lasts this boot |
| Desktops | tiling of the current desktop: along the long side, columns, rows | Left, Right |
| About | screen size, free memory frames, volume present | read only |

Portrait screens (1080x1920) tile along the long side by default.

## Grant colors

A window whose foreground process holds a grant gets a ring: sienna for `disk`, ochre for `net`. The bar's right
strip lists grants held by covered, minimized or other-desktop windows.

## Limits today

95 ASCII glyphs, no UTF-8. No clipboard between windows. No sound. The network and agent images still use the first
desk (`tiler`), not `hdesk`.

Checked by `check-hybrid.sh` (31 checks: portrait boot, clicks, drags, the switcher, Settings, the App menu, 2560x1440
and 3840x2160 modes).
