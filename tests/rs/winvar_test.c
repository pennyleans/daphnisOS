/* tests/rs/winvar_test.c: RS-TTL section 6 (docs/specs/2026-11-11-rs-ttl-bartitle.md edition 6), hosted. user/ci/host.c's
 * win_var row against a fake /dev/fb0 that keeps what FBIO_TILE_VAR (0x4688) is given: the kernel's 64 bytes
 * (src/tile.ci VAR_LEN). A name longer than the row's buffer was dropped whole, so View's bar showed no name for a
 * screenshot (`Screenshot 2026-11-12 06.54.09.png`, 34 bytes, against 32). Now the row passes a name's first 64 bytes,
 * NUL padded, from a view of any length or stride. Run by check.sh from the repository root with gcc and with clang,
 * INC the toolchain's include directory:
 *   cc -std=c17 -O1 -DCINT_RT_HELPERS_PORTABLE -I"$INC" -Iuser/ci tests/rs/winvar_test.c -o winvar_test
 * One line for each check that fails, then "winvar: N checks, F failed"; exit status 1 if any failed. */
#define _POSIX_C_SOURCE 200809L
#define CI_ROWS_WIN
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/types.h>
#include <unistd.h>

static int fake_open(const char *path, int flags, ...);
static int fake_ioctl(int fd, unsigned long req, void *arg);
static void *fake_mmap(void *a, size_t len, int prot, int fl, int fd, off_t off);
static int fake_munmap(void *a, size_t len);
static int fake_close(int fd);
#define open fake_open
#define ioctl fake_ioctl
#define mmap fake_mmap
#define munmap fake_munmap
#define close fake_close
#include "host.c"
#undef open
#undef ioctl
#undef mmap
#undef munmap
#undef close

static uint8_t var[64];                /* what the fake kernel took, its VAR_LEN bytes */
static int vars;

static int fake_open(const char *path, int flags, ...)
{
    (void)flags;
    if (strcmp(path, "/dev/fb0") != 0) {
        errno = ENOENT;
        return -1;
    }
    return 40;
}

static int fake_ioctl(int fd, unsigned long req, void *arg)
{
    (void)fd;
    if (req == 0x4688UL) {
        memcpy(var, arg, sizeof var);
        vars++;
        return 0;
    }
    errno = ENOTTY;
    return -1;
}

static void *fake_mmap(void *a, size_t len, int prot, int fl, int fd, off_t off)
{
    (void)a; (void)len; (void)prot; (void)fl; (void)fd; (void)off;
    errno = ENOMEM;
    return MAP_FAILED;
}

static int fake_munmap(void *a, size_t len)
{
    (void)a; (void)len;
    return 0;
}

static int fake_close(int fd)
{
    (void)fd;
    return 0;
}

static int fails, checks;

static void check(int ok, const char *what)
{
    checks++;
    if (!ok) {
        fails++;
        printf("FAIL %s\n", what);
    }
}

/* Whether the kernel holds the n bytes t, NUL padded to 64. */
static int holds(const char *t, size_t n)
{
    for (size_t k = 0; k < sizeof var; k++) {
        uint8_t w = k < n ? (uint8_t)t[k] : 0u;
        if (var[k] != w) return 0;
    }
    return 1;
}

/* win_var through its row, as cint calls it: a view of n bytes from p, stride bytes apart. */
static int64_t row(const uint8_t *p, int64_t n, int64_t stride)
{
    cint_value a, r;
    memset(&a, 0, sizeof a);
    memset(&r, 0, sizeof r);
    memset(var, 0xAA, sizeof var);
    a.kind = CINT_VAL_VIEW;
    a.as.view.rank = 1;
    a.as.view.mem.u.host.ptr = (void *)p;
    a.as.view.shape[0] = n;
    a.as.view.byte_stride[0] = stride;
    r_win_var(NULL, &a, 1u, &r);
    return r.as.i64;
}

int main(void)
{
    static const char shot[] = "Screenshot 2026-11-12 06.54.09.png";
    static const char five[] = "Index";
    uint8_t big[100], wide[2 * 34];

    check(strlen(shot) == 34u, "the screenshot's name is 34 bytes");
    check(row((const uint8_t *)shot, 34, 1) == 0 && vars == 1, "a 34-byte name: asked, 0");
    check(holds(shot, 34u), "a 34-byte name reaches the kernel whole, NUL padded to 64");
    check(row((const uint8_t *)five, 5, 1) == 0 && holds(five, 5u), "a 5-byte name, NUL padded");
    for (int k = 0; k < 100; k++) big[k] = (uint8_t)('a' + k % 26);
    check(row(big, 100, 1) == 0 && holds((const char *)big, 64u), "a 100-byte name: its first 64 bytes");
    check(row(big, 64, 1) == 0 && holds((const char *)big, 64u), "a 64-byte name: whole, no NUL");
    for (int k = 0; k < 34; k++) {
        wide[2 * k] = (uint8_t)shot[k];
        wide[2 * k + 1] = '#';
    }
    check(row(wide, 34, 2) == 0 && holds(shot, 34u), "a strided view: its elements, not its bytes");
    check(row(big, 0, 1) == 0 && holds("", 0u), "an empty name clears the variable");
    memset(var, 0xAA, sizeof var);
    check(ci_win_var((const uint8_t *)shot, 34) == 0 && holds(shot, 34u), "ci_win_var: 34 bytes, NUL padded");
    memset(var, 0xAA, sizeof var);
    check(ci_win_var(big, 100) == 0 && holds((const char *)big, 64u), "ci_win_var: a long name's first 64 bytes");

    printf("winvar: %d checks, %d failed\n", checks, fails);
    return fails != 0;
}
/* SPDX-License-Identifier: Apache-2.0 */
