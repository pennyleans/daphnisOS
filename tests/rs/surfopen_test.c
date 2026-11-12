/* tests/rs/surfopen_test.c: RS-SURF's first box, hosted. user/ci/host.c's window rows (CI_ROWS_WIN, CI_ROWS_SURF)
 * against a fake /dev/fb0 whose desk lays the window out the moment its size is asked, before the client's fb_open
 * returns, and tells the box once, as hdesk's resizes() does; the kernel drops the tell for a client that has not
 * asked FBIO_TILE_RESIZE (src/tile.ci input_to). A win_resize asked before fb_open is asked at the open, ahead of
 * FBIO_TILE_WANT, so the first box is told; asked after the open it is dropped, and View opened cropped. fb_resize asks
 * again in the same order. View, Index and Monitor ask win_resize just before their window's fb_open. Run by check.sh
 * from the repository root with gcc and with clang, INC the toolchain's include directory:
 *   cc -std=c17 -O1 -DCINT_RT_HELPERS_PORTABLE -I"$INC" -Iuser/ci tests/rs/surfopen_test.c -o surfopen_test
 * One line for each check that fails, then "surfopen: N checks, F failed"; exit status 1 if any failed. */
#define _POSIX_C_SOURCE 200809L
#define CI_ROWS_WIN
#define CI_ROWS_SURF
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

/* The fake kernel and desk. */
static uint8_t surf[4u * 1920u * 1080u];
static uint32_t ask_w, ask_h;          /* the surface asked (FBIO_TILE_WANT) */
static int64_t box_w, box_h;           /* the desk's content box for this window, 1x px */
static int64_t told_w, told_h;         /* hdesk's rbw, rbh: the box last told; 0 before the first */
static int on_resize, told, dropped, wants, resize_first;
static int seen_resize_on_fd;          /* FBIO_TILE_RESIZE came on the fd that then asked the size */
static int next_fd = 40;

static void desk_lays_out(void)
{
    if (box_w == told_w && box_h == told_h) return;
    if (told_w == 0 && box_w == (int64_t)ask_w && box_h == (int64_t)ask_h) return;   /* the ask fits: nothing */
    told_w = box_w;
    told_h = box_h;
    if (on_resize) told++;
    else dropped++;                    /* input_to: a client that did not ask never gets one */
}

static int fake_open(const char *path, int flags, ...)
{
    (void)flags;
    if (strcmp(path, "/dev/fb0") != 0) {
        errno = ENOENT;
        return -1;
    }
    seen_resize_on_fd = 0;
    return next_fd++;
}

static int fake_ioctl(int fd, unsigned long req, void *arg)
{
    (void)fd;
    if (req == 0x468AUL) {
        uint32_t on;
        memcpy(&on, arg, 4u);
        on_resize = on != 0u;
        seen_resize_on_fd = 1;
        return 0;
    }
    if (req == 0x4689UL) {
        uint32_t wh[2];
        memcpy(wh, arg, 8u);
        wants++;
        if (wants == 1) resize_first = seen_resize_on_fd;
        ask_w = wh[0];
        ask_h = wh[1];
        desk_lays_out();               /* the desk is first: it places the window before the open returns */
        return 0;
    }
    if (req == 0x4600UL) {
        uint32_t *var = arg;
        memset(var, 0, 160u);
        var[0] = ask_w;
        var[1] = ask_h;
        var[6] = 32u;
        return 0;
    }
    if (req == 0x4602UL) {
        uint8_t *fix = arg;
        uint32_t ll = 4u * ask_w, len = 4u * ask_w * ask_h;
        memset(fix, 0, 80u);
        memcpy(fix + 48, &ll, 4u);
        memcpy(fix + 24, &len, 4u);
        return 0;
    }
    errno = ENOTTY;
    return -1;
}

static void *fake_mmap(void *a, size_t len, int prot, int fl, int fd, off_t off)
{
    (void)a; (void)prot; (void)fl; (void)fd; (void)off;
    if (len > sizeof surf) {
        errno = ENOMEM;
        return MAP_FAILED;
    }
    return surf;
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

/* A fresh process: the host's statics and the fake kernel's. */
static void fresh(int64_t bw, int64_t bh)
{
    fb_base = NULL;
    win_rs = 0u;
    win_wh[0] = win_wh[1] = 0u;
    win_got = 0;
    ask_w = ask_h = 0u;
    box_w = bw;
    box_h = bh;
    told_w = told_h = 0;
    on_resize = told = dropped = wants = resize_first = seen_resize_on_fd = 0;
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

/* Each adopter's window: the win_resize(1) line is the line just before an fb_open. */
static void asks_before_open(const char *path)
{
    static char text[1 << 18];
    char what[160];
    FILE *f = fopen(path, "rb");
    size_t n = f != NULL ? fread(text, 1u, sizeof text - 1u, f) : 0u;
    const char *r, *eol, *next;
    if (f != NULL) fclose(f);
    text[n] = '\0';
    r = strstr(text, "tilewin.win_resize(1);");
    eol = r != NULL ? strchr(r, '\n') : NULL;
    next = eol != NULL ? strchr(eol + 1, '\n') : NULL;
    snprintf(what, sizeof what, "%s: win_resize(1) is asked just before fb_open", path);
    check(r != NULL && eol != NULL && next != NULL && strstr(eol + 1, "dev.fb_open();") != NULL
              && strstr(eol + 1, "dev.fb_open();") < next && strstr(r + 1, "tilewin.win_resize(") == NULL,
          what);
}

int main(void)
{
    cint_value a[2], r;

    /* View opens a 1280 x 720 screenshot at a 1280 x 720 mode: its surface is wider than the floating box. */
    fresh(1240, 660);
    ci_win_want(1280, 744);
    check(ci_win_resize(1) == 0, "win_resize before fb_open: kept, 0");
    check(wants == 0 && on_resize == 0, "win_resize before fb_open: nothing asked yet");
    check(ci_fb_open() == 0, "fb_open");
    check(resize_first == 1, "the open asks FBIO_TILE_RESIZE ahead of FBIO_TILE_WANT");
    check(told == 1 && dropped == 0, "the desk laid out first and its box is told");
    check(ci_fb_word(0) == 1280u && ci_fb_word(1) == 744u, "the surface is the ask until fb_resize");

    /* The surface follows the box: fb_resize asks again in the same order, and the desk tells nothing more. */
    memset(a, 0, sizeof a);
    memset(&r, 0, sizeof r);
    a[0].kind = a[1].kind = CINT_VAL_SCALAR;
    a[0].as.i64 = told_w;
    a[1].as.i64 = told_h;
    resize_first = 0;
    wants = 0;
    r_fb_resize(NULL, a, 2u, &r);
    check(r.as.i64 == 0, "fb_resize: 0");
    check(resize_first == 1, "fb_resize: FBIO_TILE_RESIZE ahead of FBIO_TILE_WANT");
    check(ci_fb_word(0) == 1240u && ci_fb_word(1) == 660u, "fb_resize: the surface is the box");
    check(told == 1 && dropped == 0, "fb_resize: the same box is not told again");

    /* The order PR 468 had: win_resize after the open. The desk's first box is dropped and View opens cropped. */
    fresh(1240, 660);
    ci_win_want(1280, 744);
    check(ci_fb_open() == 0, "fb_open, then win_resize");
    check(ci_win_resize(1) == 0, "win_resize after the open: asked at once");
    check(on_resize == 1, "win_resize after the open: on");
    check(told == 0 && dropped == 1, "win_resize after the open: the first box is dropped (the race this test holds)");

    /* A window that fits its box is never told; win_resize(0) before the open asks nothing. */
    fresh(640, 480);
    ci_win_want(640, 480);
    check(ci_win_resize(1) == 0 && ci_fb_open() == 0, "a window that fits: open");
    check(told == 0 && dropped == 0, "a window that fits: nothing told");
    fresh(1240, 660);
    ci_win_want(1280, 744);
    check(ci_win_resize(0) == 0 && ci_fb_open() == 0, "win_resize(0) before the open: open");
    check(resize_first == 0 && on_resize == 0 && dropped == 1, "win_resize(0) before the open: never asked");

    asks_before_open("user/ci/cview.ci");
    asks_before_open("user/ci/finder.ci");
    asks_before_open("user/ci/monitor.ci");

    printf("surfopen: %d checks, %d failed\n", checks, fails);
    return fails != 0;
}
/* SPDX-License-Identifier: Apache-2.0 */
