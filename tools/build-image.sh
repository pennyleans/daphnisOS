#!/usr/bin/env bash
# tools/build-image.sh CC FLAVOR O: compile the emitted C, rt/ and arch/ with CC and link.
# Called by the Makefile; CINT_INC and the flags come from its environment.
set -euo pipefail
export LC_ALL=C   # the link's obj/*.o and the compile list sort by bytes: one commit gives one kernel on every host
cc=$1 flavor=$2 out=$3
dir=$out/$cc-$flavor
emit=$out/emit-$flavor/c
rm -rf "$dir"
mkdir -p "$dir/obj"
extra=()
[ "$cc" = gcc ] && extra=(-fno-tree-loop-distribute-patterns)
asdef=()   # INITRD embeds a cpio image (arch/x86_64/initrd.S); the Makefile passes none since U1-5
[ -n "${INITRD:-}" ] && asdef=(-DINITRD="\"$INITRD\"")
for w in $RTFLAGS; do case $w in -D*) asdef+=("$w");; esac; done   # the flavor's defines reach boot.S too (RT_USER: the framebuffer tag, F-1)
# emitted C: warnings are logged, not fatal (it is the compiler's output, not ours)
while IFS= read -r f; do
    o=$dir/obj/em_$(echo "${f%.c}" | tr / _).o
    cold=()   # BU4-4 A2: a module of EMCOLD (main_% for every main) at -Os, after FFLAGS' -O2
    for m in ${EMCOLD:-}; do
        case "$(basename "${f%.c}")" in ${m//%/*}) cold=(-Os) ;; esac
    done
    (cd "$emit" && $cc $FFLAGS "${extra[@]}" "${cold[@]}" -Wall -c "$f" -o "$o") 2>> "$dir/emitted-c-warnings.log"
done < <(cd "$emit" && find . -name '*.c' | sed 's|^\./||' | sort)
for f in $RT_C; do
    $cc $RTFLAGS "${extra[@]}" -c "$f" -o "$dir/obj/rt_$(basename "$f" .c).o"
done
for f in $ASM; do
    $cc "${asdef[@]}" -c -x assembler-with-cpp "$f" -o "$dir/obj/as_$(basename "$f" .S).o"
done
ld -m elf_x86_64 -nostdlib -z max-page-size=0x1000 -z noexecstack --no-warn-rwx-segments --orphan-handling=error -T arch/x86_64/linker.ld \
    -Map="$dir/kernel.map" -o "$dir/kernel.elf" "$dir"/obj/*.o
