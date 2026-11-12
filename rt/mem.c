/* rt/mem.c: the four memory functions that gcc and clang may call even with -ffreestanding
 * (SPEC-09 EMIT-31). memcpy, memmove and memset move eight bytes a store and the rest a byte at a time (DS D-FB,
 * docs/specs/2026-11-07-ds-desk-speed.md: a byte a store was the kernel's every copy, the screen's among them); x86
 * takes a word at any address. Build with -fno-tree-loop-distribute-patterns on gcc so the loops do not turn back
 * into calls to themselves. */
#include <stddef.h>
#include <stdint.h>

typedef uint64_t __attribute__((may_alias, aligned(1))) word;

void *memcpy(void *restrict dst, const void *restrict src, size_t n)
{
    unsigned char *d = dst;
    const unsigned char *s = src;
    for (; n >= 8u; n -= 8u, d += 8, s += 8) *(word *)d = *(const word *)s;
    while (n-- > 0u) *d++ = *s++;
    return dst;
}

void *memmove(void *dst, const void *src, size_t n)
{
    unsigned char *d = dst;
    const unsigned char *s = src;
    if (d == s || n == 0u) return dst;
    if ((uintptr_t)d < (uintptr_t)s) {
        for (; n >= 8u; n -= 8u, d += 8, s += 8) *(word *)d = *(const word *)s;
        while (n-- > 0u) *d++ = *s++;
    } else {
        d += n;
        s += n;
        for (; n >= 8u; n -= 8u) {
            d -= 8;
            s -= 8;
            *(word *)d = *(const word *)s;
        }
        while (n-- > 0u) *--d = *--s;
    }
    return dst;
}

void *memset(void *dst, int c, size_t n)
{
    unsigned char *d = dst;
    uint64_t w = 0x0101010101010101u * (unsigned char)c;
    for (; n >= 8u; n -= 8u, d += 8) *(word *)d = w;
    while (n-- > 0u) *d++ = (unsigned char)c;
    return dst;
}

int memcmp(const void *a, const void *b, size_t n)
{
    const unsigned char *x = a;
    const unsigned char *y = b;
    while (n-- > 0u) {
        if (*x != *y) return *x < *y ? -1 : 1;
        x++;
        y++;
    }
    return 0;
}
