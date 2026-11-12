#!/usr/bin/env bash
# tools/run-agent-live.sh: A-6 (docs/specs/2026-11-06-a-agent.md section 3), Claude inside Daphnis on the real
# Messages API. Builds the desknet flavor (the desk with the network; agent is in its image), writes a 4 MiB ext2
# volume holding agent.key (line 1 the key, line 2 the model id), and boots Daphnis in a QEMU window with QEMU's
# user network and that volume at /home. In the desk's shell, type
#     grant net agent -k /home/agent.key -t -x api.anthropic.com 443
# then a line at each `> `; each tool call is shown and runs only on `y` (AG-4). Ctrl+D ends agent.
# The key comes from ANTHROPIC_API_KEY, or from the first line of the file KEYFILE names; MODEL is the model id
# (default claude-sonnet-5-5). The key never enters the repository: the volume ($B/agent-disk.img) is made with
# umask 077 and removed when QEMU exits, and the serial transcript ($B/agent-live.txt), which holds every frame
# and every random draw and so the whole session, the key included, once decrypted (section 4), stays on this
# machine, mode 0600. KVM when /dev/kvm is usable (ACCEL=tcg to force TCG); -cpu max gives the guest RDRAND (A-3),
# without which agent opens no TLS session. MODE=WxH and PLAY_DISPLAY as tools/run-desk-agent.sh's. Needs
# qemu-system-x86_64, mke2fs and the cint toolchain of user/ci/build.sh.
set -eu
umask 077
cd "$(dirname "$0")/.."
B=${DAPHNIS_BUILD:-${TMPDIR:-/tmp}/daphnis-build-desknet}
CINT_TOOLCHAIN=${CINT_TOOLCHAIN:-$(dirname "$(readlink -f "$(command -v cint)")")/cint.toolchain}
CC_LEG=${CC_LEG:-gcc}
MODEL=${MODEL:-claude-sonnet-5-5}
key=${ANTHROPIC_API_KEY:-}
if [ -z "$key" ] && [ -n "${KEYFILE:-}" ]; then key=$(head -n 1 "$KEYFILE"); fi
[ -n "$key" ] || { echo "run-agent-live: set ANTHROPIC_API_KEY, or KEYFILE to a file whose first line is the key" >&2; exit 2; }
command -v mke2fs > /dev/null || { echo "run-agent-live: mke2fs not found (e2fsprogs)" >&2; exit 2; }
mkdir -p "$B"; [ -f "$B/.daphnis-build" ] || : > "$B/.daphnis-build"
make -s -j"$(nproc)" O="$B" FLAVORS=desknet CINT_TOOLCHAIN="$CINT_TOOLCHAIN"
stage=$(mktemp -d)
disk=$B/agent-disk.img
trap 'rm -rf "${stage:?}"; rm -f "$disk"' EXIT
printf '%s\n%s\n' "$key" "$MODEL" > "$stage/agent.key"
rm -f "$disk"
MKE2FS_CONFIG=/dev/null mke2fs -q -t ext2 -b 4096 -I 128 -O none -d "$stage" "$disk" 4M
rm -rf "${stage:?}"
accel=tcg
if [ "${ACCEL:-}" != tcg ] && [ -w /dev/kvm ]; then accel=kvm; fi
mode=()
[ -n "${MODE:-}" ] && mode=(-append "daphnis.mode=$MODE" -vga none -device VGA,vgamem_mb=64)
: > "$B/agent-live.txt"; chmod 600 "$B/agent-live.txt"
echo "run-agent-live: $accel, model $MODEL; in the desk's shell:"
echo "    grant net agent -k /home/agent.key -t -x api.anthropic.com 443"
qemu-system-x86_64 -display "${PLAY_DISPLAY:-gtk,zoom-to-fit=on}" -serial "file:$B/agent-live.txt" -monitor none \
    -nic user,model=virtio-net-pci -drive "file=$disk,if=virtio,format=raw" \
    -accel "$accel" -cpu max -m 128 -no-reboot -device isa-debug-exit,iobase=0xf4,iosize=0x04 \
    -kernel "$B/$CC_LEG-desknet/kernel32.elf" -initrd "$B/desknet/initrd.cpio" "${mode[@]}" || true
echo "run-agent-live: the transcript is $B/agent-live.txt (holds the session; keep it on this machine)"
