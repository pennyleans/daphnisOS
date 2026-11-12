#!/usr/bin/env bash
# tools/ac-receipt.sh: AC-1b's timing receipt under Daphnis (docs/specs/2026-11-08-ac-accounts.md sections 6 and 7).
# Builds the cish flavor (gcc), boots an image of cish, the native printf and echo, and authd (O/ubin), with a session
# that runs `authd derive` at DS-6's parameters (64 MiB, 3 passes) and one at 8 KiB as the baseline, under TCG and,
# where /dev/kvm is writable, KVM. Prints each boot's wall time and its authd lines, and the verifier
# tools/ac-vectors.py gives. The cish flavor runs its session twice, so one attempt is (auth - base) / 2.
# A receipt, not a gate: nothing here passes or fails. Outputs under $DAPHNIS_BUILD (default $TMPDIR/daphnis-build-ac).
set -u
cd "$(dirname "$0")/.."
B=${DAPHNIS_BUILD:-${TMPDIR:-/tmp}/daphnis-build-ac}
CINT_TOOLCHAIN=${CINT_TOOLCHAIN:-$(dirname "$(readlink -f "$(command -v cint)")")/cint.toolchain}
mkdir -p "$B"
touch "$B/.daphnis-build"
make -s -j"$(nproc)" O="$B" FLAVORS=cish CINT_TOOLCHAIN="$CINT_TOOLCHAIN" > "$B/make.log" 2>&1 \
    || { echo "ac-receipt: make failed, see $B/make.log"; exit 1; }
UB=$(realpath -m "$B/ubin")   # RG-1: the programs, built from source at HEAD by make (O/ubin)
make -s -j"$(nproc)" O="$B" "$UB/cish" "$UB/printf" "$UB/echo" "$UB/authd" > "$B/ubin.log" 2>&1 \
    || { echo "ac-receipt: the programs did not build, see $B/ubin.log"; exit 1; }
python3 tools/mkcpio.py "$B/auth.cpio" cish="$UB"/cish bin/ bin/printf="$UB"/printf bin/echo="$UB"/echo \
    authd="$UB"/authd > "$B/cpio.log" 2>&1 || { cat "$B/cpio.log"; exit 1; }
salt=000102030405060708090a0b0c0d0e0f
{ echo "printf 'derive 65536 3 $salt\\nsevenhorsesrun' | /authd"; echo "echo authd-done"; printf '\004'; } > "$B/auth.in"
{ echo "printf 'derive 8 1 $salt\\nx' | /authd"; echo "echo authd-done"; printf '\004'; } > "$B/base.in"
echo "want verifier $(python3 tools/ac-vectors.py argon2id 65536 3 1 "$salt" sevenhorsesrun | sed -n 's/^verifier //p')"
for accel in tcg kvm; do
    kvm=0
    if [ $accel = kvm ]; then
        [ -w /dev/kvm ] || { echo "kvm: /dev/kvm is not writable here; skipped"; continue; }
        kvm=1
    fi
    for s in base auth; do
        t=$B/$s-$accel.txt
        t0=$(date +%s%N)
        KVM=$([ $kvm = 1 ] && echo 1) QEMU_TIMEOUT=600 INITRD=$B/auth.cpio STDIN_FILE=$B/$s.in MEM=512 POOL=max \
            tools/run-qemu.sh "$B/gcc-cish/kernel32.elf" "$t" > "$t.rc"
        t1=$(date +%s%N)
        echo "$accel $s: $(( (t1 - t0) / 1000000 )) ms wall, qemu status $(cat "$t.rc")"
        grep -a -E '^(verifier|error|fault)' "$t" | sed "s/^/  /"
    done
done
