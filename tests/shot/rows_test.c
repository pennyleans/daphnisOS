/* tests/shot/rows_test.c: RS-SHOT's desk rows (user/ci/host.c, CI_ROWS_HDESK) on the host, called as the runtime
 * calls them: the held screen and its reads, shot_as's checks, its slots and descriptors, and the child's login. The
 * host has no call 1003, so every child must end with status 126 at its first step and run nothing more. Build from
 * the repository root with the toolchain's include directory INC:
 *   cc -std=c17 -O1 -DCINT_RT_HELPERS_PORTABLE -I"$INC" -Iuser/ci tests/shot/rows_test.c -o rows_test */
#define CI_ROWS_HDESK
#include "host.c"

#include <dirent.h>
#include <stdio.h>

static int fails, checks;

static void check(int ok, const char *what)
{
    checks++;
    if (!ok) {
        fails++;
        printf("FAIL %s\n", what);
    }
}

static cint_value num(int64_t v)
{
    cint_value x;
    memset(&x, 0, sizeof x);
    x.kind = CINT_VAL_SCALAR;
    x.as.i64 = v;
    return x;
}

static cint_value view(uint8_t *p, int64_t n)
{
    cint_value x;
    memset(&x, 0, sizeof x);
    x.kind = CINT_VAL_VIEW;
    x.as.view.rank = 1;
    x.as.view.mem.u.host.ptr = p;
    x.as.view.shape[0] = n;
    x.as.view.byte_stride[0] = 1;
    return x;
}

static int64_t call(cint_status (*f)(void *, const cint_value *, uint32_t, cint_value *), cint_value *a, uint32_t n)
{
    cint_value r;
    memset(&r, 0, sizeof r);
    f(NULL, a, n, &r);
    return r.as.i64;
}

static int64_t peek(int64_t x, int64_t y, uint8_t *buf, int64_t n)
{
    cint_value a[3] = {num(x), num(y), view(buf, n)};
    return call(r_fb_peek, a, 3);
}

static int64_t hold(int64_t on)
{
    cint_value a[1] = {num(on)};
    return call(r_fb_hold, a, 1);
}

static int64_t shot(int64_t x, int64_t y, int64_t w, int64_t h, const char *home)
{
    cint_value a[8] = {num(x), num(y), num(w), num(h), num(1000), num(1000), num(7),
                       view((uint8_t *)home, (int64_t)strlen(home))};
    return call(r_shot_as, a, 8);
}

static int64_t end(int64_t pid, uint8_t *name, int64_t n)
{
    cint_value a[2] = {num(pid), view(name, n)};
    return call(r_shot_end, a, 2);
}

static int open_fds(void)
{
    int k = 0;
    DIR *d = opendir("/proc/self/fd");
    if (d == NULL) return -1;
    while (readdir(d) != NULL) k++;
    closedir(d);
    return k;
}

/* The child's status: 126 is the login refused at its first step. */
static int status_of(pid_t pid)
{
    int st = 0;
    while (waitpid(pid, &st, 0) < 0) {
        if (errno != EINTR) return -1;
    }
    return WIFEXITED(st) ? WEXITSTATUS(st) : -2;
}

static uint8_t screen[4 * 8 * 4];   /* 6 x 4 pixels on rows of 8 */

static void paint(uint8_t tint)
{
    for (int y = 0; y < 4; y++) {
        for (int x = 0; x < 8; x++) {
            uint8_t *p = screen + 32 * y + 4 * x;
            p[0] = (uint8_t)x;
            p[1] = (uint8_t)y;
            p[2] = tint;
            p[3] = 0;
        }
    }
}

int main(void)
{
    uint8_t b[64], name[80];
    int fds;
    int64_t pid, pids[4];
    fb_base = screen;
    fb_words[0] = 6;
    fb_words[1] = 4;
    fb_words[2] = 32;
    fb_words[3] = 32;
    fb_words[4] = sizeof screen;
    paint(0x77);

    /* reads of the live screen: the row's pixels from x, cut at its end; off the screen -EINVAL */
    memset(b, 0xEE, sizeof b);
    check(peek(2, 1, b, 16) == 4 && b[0] == 2 && b[1] == 1 && b[2] == 0x77 && b[12] == 5, "peek (2, 1) 4 pixels");
    memset(b, 0xEE, sizeof b);
    check(peek(4, 3, b, 64) == 2 && b[4] == 5 && b[5] == 3 && b[8] == 0xEE, "peek cut at the row's end");
    check(peek(6, 0, b, 4) == -EINVAL && peek(0, 4, b, 4) == -EINVAL && peek(-1, 0, b, 4) == -EINVAL &&
              peek(0, -1, b, 4) == -EINVAL, "peek off the screen");
    check(peek(0, 0, b, 3) == 0, "peek into fewer than 4 bytes reads no pixel");

    /* the held screen: later drawing is not seen until it is let go; a second hold replaces the first */
    check(hold(1) == 0 && hold_px != NULL && hold_w == 6 && hold_h == 4, "hold");
    paint(0x11);
    check(peek(1, 1, b, 4) == 1 && b[2] == 0x77, "peek reads the held screen");
    check(hold(1) == 0 && peek(1, 1, b, 4) == 1 && b[2] == 0x11, "a second hold takes the screen as it is now");
    paint(0x22);
    fb_words[0] = 2;   /* the screen changes size under a hold: reads and shots keep the held size */
    fb_words[1] = 2;
    check(peek(5, 3, b, 4) == 1 && b[2] == 0x11, "peek past the live size reads the held screen");
    check(hold(0) == 0 && hold_px == NULL && hold_w == 0 && hold_h == 0, "let go");
    check(peek(5, 3, b, 4) == -EINVAL && peek(1, 1, b, 4) == 1 && b[2] == 0x22, "peek reads the live screen again");
    fb_words[0] = 6;
    fb_words[1] = 4;
    fb_words[3] = 16;
    check(peek(0, 0, b, 4) == -EINVAL && hold(1) == -ENODEV && shot(0, 0, 1, 1, "/home/ci") == -EINVAL,
          "no read and no shot of a screen that is not 32 bits a pixel");
    fb_words[3] = 32;

    /* the child logs in with Disk alone of the ceiling */
    check(shot_ceil(7) == 1 && shot_ceil(1) == 1 && shot_ceil(6) == 0 && shot_ceil(0) == 0, "the ceiling cut to Disk");

    /* shot_as refuses a bad home or rectangle before any fork */
    fds = open_fds();
    {
        static const char *homes[] = {"/etc", "/home/", "/home/a/b", "/home/../x", "/home/-a", "/home/A", "home/ci",
                                      "/home/ci ", "/home/012345678901234567890123456789012"};
        int all = 1;
        for (size_t i = 0; i < sizeof homes / sizeof homes[0]; i++) all = all && shot(0, 0, 1, 1, homes[i]) == -EINVAL;
        check(all, "a home that is not /home/NAME");
        check(shot(0, 0, 0, 1, "/home/ci") == -EINVAL && shot(0, 0, 1, 0, "/home/ci") == -EINVAL &&
                  shot(-1, 0, 1, 1, "/home/ci") == -EINVAL && shot(0, -1, 1, 1, "/home/ci") == -EINVAL &&
                  shot(1, 0, 6, 1, "/home/ci") == -EINVAL && shot(0, 1, 1, 4, "/home/ci") == -EINVAL &&
                  shot(INT64_MAX - 1, 0, 2, 1, "/home/ci") == -EINVAL &&
                  shot(0, INT64_MAX, 1, 1, "/home/ci") == -EINVAL,
              "a rectangle not inside the screen");
        check(waitpid(-1, NULL, WNOHANG) < 0 && errno == ECHILD, "no child after a refusal");
    }

    /* a shot: a child that is refused login ends with 126 and prints no name; its pipe is closed by shot_end */
    pid = shot(0, 0, 6, 4, "/home/ci");
    check(pid > 0, "shot_as gives a pid");
    check(open_fds() == fds + 1, "the desk keeps one descriptor, the name pipe's read end");
    check(end(pid, name, sizeof name) == -EBUSY && open_fds() == fds + 1, "shot_end before the reap keeps the slot");
    check(pid > 0 && status_of((pid_t)pid) == 126, "the child ends with 126 at a refused login");
    check(end(pid, name, sizeof name) == -EINVAL, "no name from a refused child");
    check(end(pid, name, sizeof name) == -ENOENT, "shot_end once a pid");
    check(open_fds() == fds, "shot_end closes the pipe");

    /* four at a time; a held screen is the source while it is held */
    for (int i = 0; i < 4; i++) pids[i] = shot(1, 1, 2, 2, "/home/ci");
    check(pids[0] > 0 && pids[1] > 0 && pids[2] > 0 && pids[3] > 0, "four shots");
    check(shot(0, 0, 1, 1, "/home/ci") == -EBUSY, "a fifth is refused");
    for (int i = 0; i < 4; i++) check(status_of((pid_t)pids[i]) == 126 && end(pids[i], name, sizeof name) == -EINVAL,
                                      "each refused and ended");
    check(open_fds() == fds, "no descriptor left after four");
    check(hold(1) == 0, "hold for a shot");
    fb_words[0] = 2;
    fb_words[1] = 2;
    pid = shot(0, 0, 6, 4, "/home/ci");
    check(pid > 0 && status_of((pid_t)pid) == 126 && end(pid, name, sizeof name) == -EINVAL, "a shot of the held size");
    check(hold(0) == 0 && shot(0, 0, 6, 4, "/home/ci") == -EINVAL, "past the live size once let go");
    check(open_fds() == fds, "no descriptor left");

    /* the date a shot is named for: off Daphnis, with no descriptor or one that refuses FBIO_TILE_INFO, the host's
     * clock; shot_date opens nothing */
    {
        uint64_t t0 = (uint64_t)time(NULL), d = shot_date();
        check(tile_fd < 0 && d >= t0 && d <= (uint64_t)time(NULL), "no descriptor: the host's clock");
        tile_fd = open("/dev/null", O_RDWR | O_CLOEXEC);
        t0 = (uint64_t)time(NULL);
        d = shot_date();
        check(tile_fd >= 0 && d >= t0 && d <= (uint64_t)time(NULL), "the ask refused: the host's clock");
        close(tile_fd);
        tile_fd = -1;
        check(open_fds() == fds, "shot_date leaves no descriptor");
    }

    printf("%d of %d checks passed\n", checks - fails, checks);
    return fails != 0;
}
/* SPDX-License-Identifier: Apache-2.0 */
