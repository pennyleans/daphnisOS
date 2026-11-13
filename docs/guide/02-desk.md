# 02 The desk (`hdesk`)

`hdesk` is the Daphnis desktop. It has nine workspaces with tiled and floating
windows. Console runs the `cish` shell.

## Start the release image

Boot the image as described in the [project README](../../README.md). On first
boot, choose an account name and enter the passphrase twice. The account opens
in Console and stores files under `/home/NAME`. Press Super+Shift+Q twice to shut
down.

## Start a development image

This QEMU example builds the `hdesk` test image, which also carries the Doom
fixture. The 0.1.1 disk image ships separately.

```
B="${DAPHNIS_BUILD:-${TMPDIR:-/tmp}/daphnis-build-hdesk}"
make FLAVORS=hdesk COMPILERS=gcc O="$B"
PLAY=1 QEMU_TIMEOUT=0 MODE=1920x1080 POOL=max MEM=4096 INITRD="$B/hdesk/initrd.cpio" \
    tools/run-qemu.sh "$B/gcc-hdesk/kernel32.elf" "$B/desk.txt"
```

Click into the QEMU window for the keyboard. Ctrl+Alt+G releases it.
The development image opens a terminal at startup.

## Keys

| keys | action |
| --- | --- |
| Super (tap alone) | open or close the Super menu |
| Super+/ | open the shortcut sheet |
| Super+, | open Settings |
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
| click in a focused app window | pass the pointer to the app |
| Super + left drag | move |
| Super + right drag | resize |
| click the mark in the bar | Super menu |
| click a desktop number in the bar | go there |
| click the focused window's title | App menu: float or tile, minimize, monocle, move to a desktop, terminate |

## Super menu

Type to search for apps, windows, or commands.

## Settings

Open Settings with Super+, or from the Super menu. Available display modes
depend on the graphics device and firmware. A writable home volume keeps
the selected mode across boots.

## Grant colors

A window's border indicates grants held by its foreground process. Sienna
indicates Disk and ochre indicates Net. See [Files and grants](06-files.md).
