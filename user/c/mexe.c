/* user/c/mexe.c: the probe of unit BU-4f (docs/specs/2026-11-07-bu4-toolchain.md 4.5): what readlink of
 * /proc/self/exe answers, and its errno for a buffer of 0 bytes. check-disk.sh runs it as an image member at the
 * root and under bin/, and copied onto the volume; tools/check-disk.py holds each line to the same run on Linux,
 * whose working directory reads as "/" (so no length is printed: Linux's path is longer by that directory). */
#include <errno.h>
#include <stdio.h>
#include <unistd.h>

static void show(const char *what, size_t n)
{
    char b[256];
    ssize_t r = readlink("/proc/self/exe", b, n);
    if (r < 0) {
        printf("%s: errno %d\n", what, errno);
    } else {
        printf("%s: %.*s\n", what, (int)r, b);
    }
}

int main(void)
{
    show("exe", sizeof(char[256]));
    show("none", 0);
    return 0;
}
