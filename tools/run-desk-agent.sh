#!/usr/bin/env bash
# tools/run-desk-agent.sh: A-0's day-one demo (docs/specs/2026-11-06-a-agent.md section 3). Builds the desknet
# flavor (src/main_desknet.ci: the desk with the network), starts tools/claudebridge.py on 127.0.0.1:7070, and
# boots Daphnis in a QEMU window with QEMU's user network. In the desk's shell, type
#     grant net talk 10.0.2.2 7070
# then a line at each `> `; Ctrl+D or `exit` ends talk, `exit` again ends the desk.
# Claude Code runs on this host, with this host's login, in the directory the script was started from: its
# tools act here, never on Daphnis, and headless it refuses a tool that needs permission. FAKE=1 runs the fake
# bridge (nothing leaves the host). KVM when /dev/kvm is usable (ACCEL=tcg to force TCG); MODE=WxH as run-qemu.sh;
# PLAY_DISPLAY as tools/play.sh's (default gtk,zoom-to-fit=on). -cpu max gives the guest RDRAND (A-3), so getrandom
# draws and the date is the host's clock.
# The serial transcript, every received frame included, goes to $DAPHNIS_BUILD/desknet.txt; it holds the
# conversation, so it stays on this machine (section 4).
#   tools/run-desk-agent.sh [-- CLAUDE_ARG...]
set -eu
here=$(pwd)
cd "$(dirname "$0")/.."
B=${DAPHNIS_BUILD:-${TMPDIR:-/tmp}/daphnis-build-desknet}
CINT_TOOLCHAIN=${CINT_TOOLCHAIN:-$(dirname "$(readlink -f "$(command -v cint)")")/cint.toolchain}
CC_LEG=${CC_LEG:-gcc}
[ "${1:-}" = -- ] && shift
mkdir -p "$B"; [ -f "$B/.daphnis-build" ] || : > "$B/.daphnis-build"
make -s -j"$(nproc)" O="$B" FLAVORS=desknet CINT_TOOLCHAIN="$CINT_TOOLCHAIN"
accel=tcg
if [ "${ACCEL:-}" != tcg ] && [ -w /dev/kvm ]; then accel=kvm; fi
mode=()
[ -n "${MODE:-}" ] && mode=(-append "daphnis.mode=$MODE" -vga none -device VGA,vgamem_mb=64)
fake=()
[ "${FAKE:-0}" = 1 ] && fake=(--fake)
(cd "$here" && exec python3 "$OLDPWD/tools/claudebridge.py" "${fake[@]}" -- "$@") > "$B/bridge.log" 2>&1 &
bridge=$!
trap 'kill $bridge 2>/dev/null || true' EXIT
for _ in 1 2 3 4 5 6 7 8 9 10; do grep -q '^claudebridge: listening' "$B/bridge.log" 2>/dev/null && break; sleep 0.2; done
grep -q '^claudebridge: listening' "$B/bridge.log" || { cat "$B/bridge.log"; exit 1; }
echo "run-desk-agent: bridge on 127.0.0.1:7070 ($accel); in the shell: grant net talk 10.0.2.2 7070"
qemu-system-x86_64 -display "${PLAY_DISPLAY:-gtk,zoom-to-fit=on}" -serial "file:$B/desknet.txt" -monitor none -nic user,model=virtio-net-pci \
    -accel "$accel" -cpu max -m 128 -no-reboot -device isa-debug-exit,iobase=0xf4,iosize=0x04 \
    -kernel "$B/$CC_LEG-desknet/kernel32.elf" -initrd "$B/desknet/initrd.cpio" "${mode[@]}" || true
cat "$B/bridge.log"
