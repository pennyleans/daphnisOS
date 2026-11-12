#!/usr/bin/env bash
# tools/desk.sh: boot an already-built Daphnis desktop on an existing persistent volume and keep a receipt.
#   bash tools/desk.sh --kernel /abs/kernel32.elf --initrd /abs/initrd.cpio --volume /abs/work.img \
#       --out /abs/new-run-directory [--mode WxH] [--accel kvm|tcg] [--timeout SECONDS] [--headless] [--dry-run]
# Run with --help for the full list. The script builds nothing, never creates or formats the volume, and starts QEMU
# directly with an argument array (no eval, no tools/run-qemu.sh), so the shared gate runner is untouched.
set -u
export LC_ALL=C

# Runner controls inherited from the environment never reach this command: only the options below change it.
unset QEMU_EXTRA NET NET_FWD SOUND PLAY PLAY_DISPLAY MONITOR DISK INITRD MODE POOL RTC APPEND CPU KVM MEM \
    QEMU_TIMEOUT STDIN_FILE QEMU_AUDIO_DRV QEMU_PA_SERVER QEMU_ALSA_DAC_BUFFER_SIZE

usage() {
    local text
    read -r -d '' text <<'EOF'
usage: bash tools/desk.sh --kernel PATH --initrd PATH --volume PATH --out DIR [options]

boots a built desktop on an existing volume. every path is absolute. nothing is built, created or formatted.

required:
  --kernel PATH    kernel32.elf of the desktop flavor
  --initrd PATH    initrd.cpio of the same flavor
  --volume PATH    existing raw volume; the guest writes it
  --out DIR        new run directory; must not exist, must be outside this checkout

options:
  --mode WxH       framebuffer, 640x480 to 3840x2160 (default 1920x1080)
  --accel A        kvm or tcg (default kvm); there is no fallback between them
  --timeout N      seconds before qemu is stopped, 0 for none (default 0)
  --headless       no window; for automation
  --monitor        also open a qemu monitor on DIR/monitor.sock (local unix socket) so a script can type keys;
                   default none; tools/sendkeys.py takes that socket
  --dry-run        validate and print the command; start nothing, write nothing
  --qemu PATH      qemu-system-x86_64 to run (default: the one on PATH)
  --kvm-device P   kvm device node checked for --accel kvm (default /dev/kvm)
  -h, --help       this text

fixed: 4096 MiB, daphnis.pool=max, daphnis.rtc=1, -cpu max, no network, no audio, cache=writeback on the volume.
writes under DIR: receipt.json, serial.log, qemu.err.
exit: 0 guest shutdown (status 33); 2 refused before launch; 124 timeout; 1 any other end.
EOF
    printf '%s\n' "$text"
}

die() {
    printf 'desk.sh: %s\n' "$*" >&2
    exit 2
}

kernel= initrd= volume= out=
mode=1920x1080 accel=kvm timeout=0 headless=0 dry=0 monitor=0
qemu=qemu-system-x86_64 kvmdev=/dev/kvm

while [ $# -gt 0 ]; do
    case $1 in
        -h|--help) usage; exit 0;;
        --headless) headless=1; shift; continue;;
        --dry-run) dry=1; shift; continue;;
        --monitor) monitor=1; shift; continue;;
        --kernel|--initrd|--volume|--out|--mode|--accel|--timeout|--qemu|--kvm-device) ;;
        *) die "unknown argument: $1 (see --help)";;
    esac
    [ $# -ge 2 ] || die "$1 needs a value"
    case $1 in
        --kernel) kernel=$2;;
        --initrd) initrd=$2;;
        --volume) volume=$2;;
        --out) out=$2;;
        --mode) mode=$2;;
        --accel) accel=$2;;
        --timeout) timeout=$2;;
        --qemu) qemu=$2;;
        --kvm-device) kvmdev=$2;;
    esac
    shift 2
done

[ -n "$kernel" ] || die "--kernel is required"
[ -n "$initrd" ] || die "--initrd is required"
[ -n "$volume" ] || die "--volume is required"
[ -n "$out" ] || die "--out is required"

absolute() {   # NAME PATH
    case $2 in
        *$'\n'*) die "$1 holds a newline";;
        /*) ;;
        *) die "$1 must be an absolute path: $2";;
    esac
}
absolute --kernel "$kernel"
absolute --initrd "$initrd"
absolute --volume "$volume"
absolute --out "$out"

if ! [[ $mode =~ ^([1-9][0-9]{2,3})x([1-9][0-9]{2,3})$ ]]; then
    die "--mode must be WxH, as 1920x1080: $mode"
fi
mw=${BASH_REMATCH[1]} mh=${BASH_REMATCH[2]}
if [ "$mw" -lt 640 ] || [ "$mw" -gt 3840 ] || [ "$mh" -lt 480 ] || [ "$mh" -gt 2160 ]; then
    die "--mode is outside 640x480 to 3840x2160: $mode"
fi
case $accel in kvm|tcg) ;; *) die "--accel must be kvm or tcg: $accel";; esac
[[ $timeout =~ ^[0-9]{1,6}$ ]] || die "--timeout must be whole seconds: $timeout"
timeout=$((10#$timeout))

for t in python3 sha256sum realpath dirname basename mkdir date; do
    command -v "$t" > /dev/null || die "$t not found"
done
[ "$timeout" -eq 0 ] || command -v timeout > /dev/null || die "timeout not found (needed for --timeout)"

case $qemu in
    */*) qpath=$qemu;;
    *) qpath=$(command -v -- "$qemu") || die "$qemu not found";;
esac
[ -f "$qpath" ] && [ -x "$qpath" ] || die "qemu is not an executable file: $qpath"

if [ "$accel" = kvm ]; then
    [ -r "$kvmdev" ] && [ -w "$kvmdev" ] ||
        die "kvm is not usable at $kvmdev; this launcher does not fall back, pass --accel tcg to run without it"
fi
if [ "$headless" -eq 0 ] && [ -z "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]; then
    die "no display (DISPLAY and WAYLAND_DISPLAY are unset); pass --headless to run without a window"
fi

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)

check_input() {   # NAME PATH
    [ -e "$2" ] || die "$1 does not exist: $2"
    [ -f "$2" ] || die "$1 is not a regular file: $2"
    [ -r "$2" ] || die "$1 is not readable: $2"
    [ -s "$2" ] || die "$1 is empty: $2"
}
check_input --kernel "$kernel"
check_input --initrd "$initrd"
check_input --volume "$volume"
[ -w "$volume" ] || die "--volume is not writable: $volume"

kres=$(realpath -e -- "$kernel") || die "cannot resolve --kernel"
ires=$(realpath -e -- "$initrd") || die "cannot resolve --initrd"
vres=$(realpath -e -- "$volume") || die "cannot resolve --volume"
if [ "$kernel" -ef "$initrd" ] || [ "$kernel" -ef "$volume" ] || [ "$initrd" -ef "$volume" ]; then
    die "--kernel, --initrd and --volume must be three different files"
fi

while [ "${#out}" -gt 1 ] && [ "${out%/}" != "$out" ]; do out=${out%/}; done
if [ -e "$out" ] || [ -L "$out" ]; then
    die "--out exists: $out (every boot gets a fresh directory; no receipt is overwritten)"
fi
parent=$(dirname -- "$out")
[ -d "$parent" ] || die "the parent of --out is not a directory: $parent"
pres=$(cd "$parent" && pwd -P) || die "cannot resolve the parent of --out"
[ "$pres" = / ] && pres=
outr=$pres/$(basename -- "$out")
case $outr/ in "$root"/*) die "--out resolves inside this checkout ($root): $outr";; esac
for f in "$kres" "$ires" "$vres"; do
    case $f/ in "$outr"/*) die "an input resolves inside --out: $f";; esac
done

mon=(-monitor none)
if [ "$monitor" -eq 1 ]; then
    sock=$outr/monitor.sock
    [ "${#sock}" -le 100 ] || die "the monitor socket path is too long for a unix socket (${#sock} > 100): $sock"
    mon=(-monitor "unix:${sock//,/,,},server=on,wait=off")
fi
display=gtk,zoom-to-fit=on
[ "$headless" -eq 1 ] && display=none
vopt=${vres//,/,,}   # an option value: a comma is written twice; the shell argument itself is unescaped
args=(
    -accel "$accel" -cpu max -m 4096 -no-reboot
    -display "$display" -vga none -device VGA,vgamem_mb=64
    -serial stdio "${mon[@]}" -nic none
    -device isa-debug-exit,iobase=0xf4,iosize=0x04
    -drive "file=$vopt,if=virtio,format=raw,cache=writeback"
    -kernel "$kres" -initrd "$ires"
    -append "daphnis.mode=$mode daphnis.pool=max daphnis.rtc=1"
)
cmd=("$qpath" "${args[@]}")
if [ "$timeout" -gt 0 ]; then
    cmd=(timeout --foreground --signal=TERM --kill-after=10 "$timeout" "${cmd[@]}")
fi

ksha=$(sha256sum -- "$kres" | cut -d' ' -f1)
isha=$(sha256sum -- "$ires" | cut -d' ' -f1)
vsha=$(sha256sum -- "$vres" | cut -d' ' -f1)
head=$(git -C "$root" rev-parse HEAD 2> /dev/null) || head=unknown
dirty=0
[ -z "$(git -C "$root" status --porcelain --untracked-files=no 2> /dev/null)" ] || dirty=1

if [ "$dry" -eq 1 ]; then
    {
        echo "desk.sh dry run: inputs validated, nothing started, nothing written"
        echo "launcher head: $head$([ "$dirty" -eq 1 ] && echo ' (tree modified)')"
        echo "kernel:  $kres  sha256 $ksha"
        echo "initrd:  $ires  sha256 $isha"
        echo "volume:  $vres  sha256 $vsha"
        echo "out:     $outr (not created)"
        echo "mode $mode, accel $accel, display $display, timeout $timeout, 4096 MiB, pool max, rtc 1, monitor $([ "$monitor" -eq 1 ] && echo "$sock" || echo none)"
        printf 'command:'
        printf ' %q' "${cmd[@]}"
        echo
    }
    exit 0
fi

read -r -d '' PY <<'PYEOF'
import json, os, sys
e = os.environ
n = int(sys.argv[1])
def num(k):
    v = e.get(k, "")
    return int(v) if v != "" else None
doc = {
    "schema": "daphnis-desk-launch-1",
    "state": e["R_STATE"],
    "launcher": {"source_head": e["R_HEAD"], "tree_modified": e["R_DIRTY"] == "1"},
    "inputs": {
        n: {"given": e["R_%s_GIVEN" % n.upper()], "resolved": e["R_%s_RES" % n.upper()],
            "sha256": e["R_%s_SHA" % n.upper()]}
        for n in ("kernel", "initrd", "volume")
    },
    "volume_sha256_after": e.get("R_VOLUME_SHA_AFTER") or None,
    "settings": {"mode": e["R_MODE"], "accel": e["R_ACCEL"], "headless": e["R_HEADLESS"] == "1", "monitor_socket": e.get("R_MONITOR") or None,
                 "timeout_seconds": num("R_TIMEOUT"), "memory_mib": 4096, "pool": "max", "rtc": 1,
                 "cpu": "max", "volume_cache": "writeback"},
    "qemu": {"path": e["R_QEMU"], "version": e.get("R_QEMU_VERSION"), "argv": sys.argv[2 + n:]},
    "command": sys.argv[2:2 + n],
    "out": e["R_OUT"],
    "started_utc": e["R_START"],
    "ended_utc": e.get("R_END") or None,
    "qemu_status": num("R_STATUS"),
    "result": e.get("R_RESULT") or None,
    "serial_log_bytes": num("R_SERIAL_BYTES"),
    "serial_log_sha256": e.get("R_SERIAL_SHA") or None,
}
path = os.path.join(e["R_OUT"], "receipt.json")
tmp = path + ".tmp"
with open(tmp, "w") as f:
    json.dump(doc, f, indent=2, sort_keys=True)
    f.write("\n")
os.replace(tmp, path)
PYEOF

now() { date -u +%Y-%m-%dT%H:%M:%SZ; }
qver=$("$qpath" --version 2> /dev/null | head -n 1)

receipt() {   # STATE [STATUS RESULT END VOLUME_SHA_AFTER SERIAL_BYTES SERIAL_SHA]
    R_STATE=$1 R_HEAD=$head R_DIRTY=$dirty \
    R_KERNEL_GIVEN=$kernel R_KERNEL_RES=$kres R_KERNEL_SHA=$ksha \
    R_INITRD_GIVEN=$initrd R_INITRD_RES=$ires R_INITRD_SHA=$isha \
    R_VOLUME_GIVEN=$volume R_VOLUME_RES=$vres R_VOLUME_SHA=$vsha R_VOLUME_SHA_AFTER=${5:-} \
    R_MONITOR=$([ "$monitor" -eq 1 ] && echo "$sock") R_MODE=$mode R_ACCEL=$accel R_HEADLESS=$headless R_TIMEOUT=$timeout \
    R_QEMU=$qpath R_QEMU_VERSION=$qver R_OUT=$outr R_START=$start \
    R_END=${4:-} R_STATUS=${2:-} R_RESULT=${3:-} R_SERIAL_BYTES=${6:-} R_SERIAL_SHA=${7:-} \
        python3 -B -c "$PY" "${#cmd[@]}" "${cmd[@]}" "${args[@]}" || die "cannot write the receipt in $outr"
}

mkdir -- "$outr" || die "cannot create --out: $outr"
start=$(now)
receipt started
echo "desk.sh: run directory $outr"

"${cmd[@]}" < /dev/null > "$outr/serial.log" 2> "$outr/qemu.err"
status=$?

case $status in
    33) result=guest-shutdown;;
    124|137) if [ "$timeout" -gt 0 ]; then result=timeout; else result=abnormal-exit; fi;;
    126|127) result=launch-failed;;
    0) result=qemu-exited-without-guest-shutdown;;
    *) result=abnormal-exit;;
esac
vafter=$(sha256sum -- "$vres" | cut -d' ' -f1)
sbytes=$(wc -c < "$outr/serial.log")
ssha=$(sha256sum -- "$outr/serial.log" | cut -d' ' -f1)
receipt finished "$status" "$result" "$(now)" "$vafter" "${sbytes//[[:space:]]/}" "$ssha"

echo "desk.sh: qemu status $status, $result"
echo "desk.sh: receipt $outr/receipt.json, serial log $outr/serial.log"
case $result in
    guest-shutdown) exit 0;;
    timeout) echo "desk.sh: stopped after the $timeout second timeout" >&2; exit 124;;
    *)
        if [ -s "$outr/qemu.err" ]; then
            echo "desk.sh: qemu diagnostic ($outr/qemu.err):" >&2
            tail -n 20 "$outr/qemu.err" >&2
        fi
        exit 1;;
esac
