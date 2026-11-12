#!/usr/bin/env bash
# tools/audit-symbols.sh O "COMPILERS" "FLAVORS": the K0 symbol audit.
# For every build (compiler x flavor):
#   1. every object: each undefined symbol is defined by another object of the same build
#      (the emitted cg_/ci_/cm_ symbols and rt/ entry points) or by the linker script
#      (__bss_start, __bss_end), never by a library;
#   2. the linked image has no undefined symbol (nm -u is empty);
#   3. no libc symbol, defined or referenced, in any object or the image (deny list below);
#   4. the mem* family in the image is exactly memcpy, memmove, memset, memcmp, each
#      defined by rt/mem.c.
# Prints PASS or FAIL per build and check; exits 1 on any FAIL.
set -u -o pipefail
out=$1; compilers=$2; flavors=$3
fail=0
deny='^(printf|fprintf|sprintf|snprintf|vsnprintf|puts|putchar|fputs|fwrite|fopen|fclose|malloc|calloc|realloc|free|aligned_alloc|abort|exit|_exit|atexit|getenv|qsort|bsearch|strlen|strcpy|strncpy|strcmp|strncmp|strchr|strrchr|strstr|strcat|memchr|memrchr|memmem|mempcpy|bzero|stdout|stderr|stdin|errno|__errno_location|read|write|open|close|time|clock|rand|srand|__stack_chk_fail|__stack_chk_guard|__assert_fail|__libc_.*|__cxa_.*|_GLOBAL_OFFSET_TABLE_|__udivti3|__divti3|__umodti3|__modti3|__multi3|__popcount.*|__clz.*|__ctz.*|__mulodi4|__muloti4|__chkstk.*|_start_c|__gmon_start__|__ash[lr]ti3|__lshrti3|__[a-z]*[sdtx]f[0-9]?|__[a-z]*[sdtx]i[0-9]?f[a-z]*|__fix.*|__float.*)$'
res() { # status label detail
    if [ "$1" = ok ]; then echo "PASS  $2"; else echo "FAIL  $2: $3"; fail=1; fi
}
for cc in $compilers; do
  for fl in $flavors; do
    d=$out/$cc-$fl
    tag="audit $cc-$fl"
    if ! ls "$d"/obj/*.o > /dev/null 2>&1 || [ ! -f "$d/kernel.elf" ]; then
        res bad "$tag: inputs" "no objects or no kernel.elf under $d"
        continue
    fi
    # symbols the linker script defines (__bss_start, __bss_end) count as defined
    ldsyms=$(sed -n 's/^[[:space:]]*\([A-Za-z_][A-Za-z0-9_]*\) = \..*/\1/p' arch/x86_64/linker.ld)
    defs=$( (nm --defined-only -g "$d"/obj/*.o | awk 'NF==3 {print $3}'; echo "$ldsyms") | sort -u)
    bad=""
    for o in "$d"/obj/*.o; do
        for u in $(nm -u "$o" | awk '{print $2}'); do
            grep -qxF "$u" <<<"$defs" || bad="$bad $(basename "$o"):$u"
        done
    done
    [ -z "$bad" ] && res ok "$tag: every object's undefined symbols are defined in this build" \
                  || res bad "$tag: objects" "unresolved:$bad"
    und=$(nm -u "$d/kernel.elf" | awk '{print $2}' | tr '\n' ' ')
    [ -z "$und" ] && res ok "$tag: image has no undefined symbol (nm -u empty)" || res bad "$tag: image" "undefined: $und"
    allsyms=$( (nm "$d"/obj/*.o; nm "$d/kernel.elf") | awk 'NF>=2 {print $NF}' | sort -u)
    libc=$(grep -E "$deny" <<<"$allsyms" | tr '\n' ' ')
    [ -z "$libc" ] && res ok "$tag: no libc symbol in any object or the image" || res bad "$tag: libc" "$libc"
    mem=$(nm "$d/kernel.elf" | awk '$2 ~ /^[TtWw]$/ && $3 ~ /^mem/ {print $3}' | sort | tr '\n' ' ')
    [ "$mem" = "memcmp memcpy memmove memset " ] && res ok "$tag: mem functions are exactly the four of rt/mem.c" \
                                                  || res bad "$tag: mem functions" "got: $mem"
    # no floating point: no SSE, AVX or x87 instruction in any object (objdump), and no
    # soft-float helper in the symbol deny list above
    fp=$(objdump -d --no-show-raw-insn "$d"/obj/*.o | grep -cE '%(xmm|ymm|zmm|st)[0-9(]|\b(fld|fst|fild|fistp?|cvt[a-z0-9]*|movs[sd]|movaps|movups|movdq[au]|pxor|addss|addsd)\b')
    [ "$fp" = 0 ] && res ok "$tag: no SSE, AVX or x87 instruction in any object" || res bad "$tag: floating point" "$fp matching instructions"
    own=$(nm --defined-only "$d"/obj/rt_mem.o | awk '$2=="T" {print $3}' | sort | tr '\n' ' ')
    [ "$own" = "memcmp memcpy memmove memset " ] || res bad "$tag: rt_mem.o" "defines: $own"
  done
done
exit $fail
