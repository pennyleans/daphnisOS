#!/usr/bin/env bash
# tools/run-qemu.sh IMAGE TRANSCRIPT: boot IMAGE (elf32 Multiboot 1, or a .iso: GRUB, Multiboot 2) once; the serial
# stream goes to TRANSCRIPT; prints QEMU's exit status. No network unless NET=user, no monitor, no stdin,
# TCG (no host CPU features), 30 s watchdog.
#   QEMU_TIMEOUT: the watchdog in seconds (default 30).
#   QEMU_EXTRA: more qemu arguments (K5: -device loader for the run blob), STDIN_FILE: the serial input
#   (K5: the scripted keys); both default to nothing and /dev/null. INITRD: a file QEMU hands the
#   kernel as its first Multiboot 1 module (the user image, U1-5); an .iso carries its own. MONITOR: a
#   path; the monitor then listens on that unix socket (tools/sendkeys.py types keys through it, F-2).
#   NET: none (the default) or user: QEMU's user network with one virtio-net device (N-1).
#   NET_MAC: with NET=user, the guest NIC's MAC address (NW-5: non-default MAC triggers boot DHCP).
#   NET_MODEL: with NET=user, the device model, virtio-net-pci unless given (HW-7: e1000, e1000e).
#   NET_FWD: with NET=user, forwards added to it, as QEMU's hostfwd= takes them (N-3: tcp:127.0.0.1:H-:G).
#   DISK: a raw volume (tools/mkdisk.sh) as a virtio block device, legacy interface (P-1); QEMU writes it.
#   MODE: WxH for the framebuffer (HX-0 A): -append daphnis.mode=WxH and a standard VGA of 64 MiB; -kernel only.
#   POOL: max for the pool sized from the memory map (M-3): -append daphnis.pool=max; -kernel only. With MEM.
#   RTC: 1 for the date read from the CMOS clock at boot even without RDRAND (K-6b): -append daphnis.rtc=1;
#   -kernel only. tools/play.sh passes it; a gate passes it only with a fixed -rtc base= in QEMU_EXTRA.
#   APPEND: more words for the kernel's boot line, -kernel only (G-5: daphnis.skill=N, daphnis.warp=M, daphnis.seal=1).
#   CPU: QEMU's -cpu model; empty (the default) leaves QEMU's own, which has no RDRAND. A-3: check-agent.sh's
#   draw legs pass max, so getrandom has a source; no other gate passes it, so no golden moves.
#   PLAY=1 (G-5, tools/play.sh): KVM and a window instead of TCG and no display, so a person plays at real time;
#   PLAY_DISPLAY is QEMU's -display for it (default gtk,zoom-to-fit=on). QEMU_TIMEOUT=0 turns the watchdog off.
#   SOUND (AU-6, tools/play.sh): a QEMU audio backend (pa, pipewire, alsa, sdl, or wav,path=...); with it the guest
#   gets intel-hda and hda-output,mixer=off, the device and path of the AU gate (check-audio.sh). Empty (the
#   default) adds no device, so no gate's transcript moves.
#   KVM=1 (AU-7, check-opl.sh on Arch): KVM with no display, to measure a gate's cost at the host's speed.
#   -display none (not -nographic): -nographic sends SeaBIOS's console text to the serial port.
#   FW=ovmf and OVMF=FILE: UEFI firmware; no persistent variable store is written. An .esp is
#   a FAT EFI image on a snapshot IDE drive (never virtio, which would change blk's device list).
#   STDIN_AFTER=TEXT: hold STDIN_FILE until TEXT appears in the transcript, after firmware handoff.
#   QEMU_FOREGROUND=1: timeout shares an OVMF supervisor's owned process group. Only that
#   supervisor uses it; ordinary calls keep timeout's default process-group behavior.
#   no -no-shutdown: QEMU 11.1.2 routes isa-debug-exit through the shutdown request, and
#   -no-shutdown turns that into a pause (docs/boot.md).
set -u
image=$1 transcript=$2
boot=-kernel
module=()
[ "${image##*.}" = iso ] && boot=-cdrom   # Multiboot 2 through GRUB (tools/build-iso.sh)
esp=() firmware=() feeder=()
if [ "${image##*.}" = esp ]; then
    boot=""
    esp=(-drive "file=$image,format=raw,if=ide,snapshot=on")
fi
if [ "${FW:-}" = ovmf ]; then
    [ -f "${OVMF:-}" ] || { echo "run-qemu: set OVMF to the firmware file" >&2; exit 1; }
    firmware=(-bios "$OVMF")
fi
[ -z "${STDIN_AFTER:-}" ] || feeder=(python3 "$(dirname "$0")/serial-after.py" "$STDIN_AFTER" "${STDIN_FILE:-/dev/null}" "$transcript")
[ "$boot" = -kernel ] && [ -n "${INITRD:-}" ] && module=(-initrd "$INITRD")
mode=() line=${APPEND:-}
[ "$boot" = -kernel ] && [ -n "${MODE:-}" ] && { line="daphnis.mode=$MODE${line:+ $line}"; mode=(-vga none -device VGA,vgamem_mb=64); }
[ "$boot" = -kernel ] && [ "${POOL:-}" = max ] && line="daphnis.pool=max${line:+ $line}"   # M-3: the pool from the memory map
[ "$boot" = -kernel ] && [ "${RTC:-}" = 1 ] && line="daphnis.rtc=1${line:+ $line}"   # K-6b: the CMOS date at boot
[ "$boot" = -kernel ] && [ -n "$line" ] && mode+=(-append "$line")
accel=(-display none -accel tcg)
cpu=()
[ -n "${CPU:-}" ] && cpu=(-cpu "$CPU")
[ "${KVM:-0}" = 1 ] && accel=(-display none -accel kvm)
[ "${PLAY:-0}" = 1 ] && accel=(-display "${PLAY_DISPLAY:-gtk,zoom-to-fit=on}" -accel kvm)
nic=(-nic none)
if [ "${NET:-none}" = user ]; then
    if [ -n "${NET_LOSSY:-}" ]; then
        nic=(-netdev "user,id=u0${NET_FWD:+,hostfwd=$NET_FWD}" -device "${NET_MODEL:-virtio-net-pci},netdev=u0${NET_MAC:+,mac=$NET_MAC}"
            -chardev "socket,id=crx_out,path=$NET_LOSSY/rx_out" -chardev "socket,id=crx_in,path=$NET_LOSSY/rx_in"
            -chardev "socket,id=ctx_out,path=$NET_LOSSY/tx_out" -chardev "socket,id=ctx_in,path=$NET_LOSSY/tx_in"
            -object filter-redirector,id=frx,netdev=u0,queue=rx,outdev=crx_out,indev=crx_in
            -object filter-redirector,id=ftx,netdev=u0,queue=tx,outdev=ctx_out,indev=ctx_in)
    else
        nic=(-nic "user,model=${NET_MODEL:-virtio-net-pci}${NET_MAC:+,mac=$NET_MAC}${NET_FWD:+,hostfwd=$NET_FWD}")
    fi
fi
monitor=(-monitor none)
disk=()
sound=()
[ -n "${SOUND:-}" ] && sound=(-device intel-hda -device hda-output,audiodev=a0,mixer=off -audiodev "$SOUND,id=a0")
[ -n "${DISK:-}" ] && disk=(-drive "file=$DISK,if=virtio,format=raw,cache=unsafe")
[ -n "${MONITOR:-}" ] && { rm -f "$MONITOR"; monitor=(-monitor "unix:$MONITOR,server=on,wait=off"); }
image_arg=("$image")
[ -n "$boot" ] || image_arg=()
timeout_mode=()
[ "${QEMU_FOREGROUND:-0}" != 1 ] || timeout_mode=(--foreground)
timeout --kill-after=5s "${timeout_mode[@]}" ${QEMU_TIMEOUT:-30} "${feeder[@]}" qemu-system-x86_64 "${accel[0]}" "${accel[1]}" -serial stdio "${monitor[@]}" "${nic[@]}" \
    "${accel[2]}" "${accel[3]}" -m ${MEM:-128} -no-reboot -device isa-debug-exit,iobase=0xf4,iosize=0x04 "${cpu[@]}" "${disk[@]}" "${sound[@]}" ${QEMU_EXTRA:-} \
    "${firmware[@]}" "${esp[@]}" $boot "${image_arg[@]}" "${module[@]}" "${mode[@]}" < "${STDIN_FILE:-/dev/null}" > "$transcript" 2> "$transcript.err"
echo $?
