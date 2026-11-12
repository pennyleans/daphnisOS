/* user/c/mresize.c: RS-SURF's probe (docs/specs/2026-11-05-h-hybrid.md section 5a). Under Daphnis it is the desk and
 * forks one pixel client, places it, and reads the screen back after each step, one line each,
 * `mresize: WHAT = RESULT`:
 *   the client draws red at 64 x 32; FBIO_TILE_WANT while mapped is -EINVAL; after munmap a new size is 0 and a
 *   second ask before the desk places it again is -EINVAL; placed again at 96 x 48 the screen still shows the old
 *   red, also once the new surface is mapped and not yet drawn (no black); the client draws green and the screen
 *   shows it, inside the old box and outside it; a smaller size maps at the address of the larger one; 100 resizes
 *   take no pool frame more than the client held before them.
 * check-tiler.sh compares the lines with tests/expected/rs-mresize.out. Its own static musl binary (user/c/build.sh,
 * DU-2 A). Exit status 0. */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/wait.h>
#include <unistd.h>

#define FBIO_TILER 0x4680
#define FBIO_TILE_NEXT 0x4681
#define FBIO_TILE_SYNC 0x4683
#define FBIO_TILE_PLACE 0x4685
#define FBIO_TILE_INFO 0x4687
#define FBIO_TILE_WANT 0x4689
#define SETTLE 1
#define RED 0x00FF0000u
#define GREEN 0x0000FF00u
#define BLUE 0x000000FFu
#define DX 100
#define DY 100
#define ROUNDS 100

static int fb, up[2], down[2];
static volatile uint32_t *screen;
static unsigned stride;

static void show(const char *what, long r)
{
    printf("mresize: %s = %ld\n", what, r);
    fflush(stdout);
}

static void tell(int fd, long v) { if (write(fd, &v, sizeof v) != sizeof v) _exit(1); }
static long hear(int fd) { long v = 0; if (read(fd, &v, sizeof v) != sizeof v) _exit(1); return v; }

static long ioc(int fd, unsigned long req, void *arg) { return ioctl(fd, req, arg) < 0 ? -errno : 0; }

static long want(int f, unsigned w, unsigned h)
{
    unsigned a[2] = {w, h};
    return ioc(f, FBIO_TILE_WANT, a);
}

static long place(pid_t c, unsigned w, unsigned h)
{
    uint32_t r[4] = {DX, DY, w, h};
    unsigned char b[24] = {0};
    uint32_t vp = (uint32_t)c, dx = DX, dy = DY;
    uint16_t s = 1, n = 1;
    uint64_t at = (uint64_t)(uintptr_t)r;
    memcpy(b, &vp, 4);
    memcpy(b + 4, &dx, 4);
    memcpy(b + 8, &dy, 4);
    memcpy(b + 12, &s, 2);
    memcpy(b + 14, &n, 2);
    memcpy(b + 16, &at, 8);
    return ioc(fb, FBIO_TILE_PLACE, b);
}

static void settle(void)
{
    uint32_t f = SETTLE;
    ioctl(fb, FBIO_TILE_SYNC, &f);
}

static const char *color(unsigned x, unsigned y)
{
    uint32_t v = screen[y * (stride / 4) + x] & 0x00FFFFFFu;
    return v == RED ? "red" : v == GREEN ? "green" : v == BLUE ? "blue" : v == 0 ? "black" : "other";
}

static void show_color(const char *what, unsigned x, unsigned y)
{
    printf("mresize: %s = %s\n", what, color(x, y));
    fflush(stdout);
}

static long frames_free(void)
{
    unsigned char b[64] = {0};
    unsigned kind = 2;
    memcpy(b, &kind, 4);
    if (ioctl(fb, FBIO_TILE_INFO, b) < 0) return -errno;
    uint32_t f;
    memcpy(&f, b, 4);
    return f;
}

/* The client: each request from the desk is one word; the answer goes back on up. */
static void client(void)
{
    int f = open("/dev/fb0", O_RDWR);
    uint32_t *s = 0;
    unsigned w = 0, h = 0;
    for (;;) {
        long op = hear(down[0]);
        if (op == 0) _exit(0);
        if (op == 1 || op == 5) {                  /* map w x h (sent next) */
            w = (unsigned)hear(down[0]);
            h = (unsigned)hear(down[0]);
            void *m = mmap(0, (size_t)w * h * 4, PROT_READ | PROT_WRITE, MAP_SHARED, f, 0);
            s = m == MAP_FAILED ? 0 : m;
            tell(up[1], s ? (long)(uintptr_t)s : -errno);
        } else if (op == 2) {                      /* draw the color sent next */
            uint32_t c = (uint32_t)hear(down[0]);
            for (unsigned i = 0; s && i < w * h; i++) s[i] = c;
            tell(up[1], 0);
        } else if (op == 3) {                      /* ask w x h without unmapping */
            unsigned a = (unsigned)hear(down[0]), b = (unsigned)hear(down[0]);
            tell(up[1], want(f, a, b));
        } else if (op == 4) {                      /* unmap, then ask w x h, then ask it again */
            unsigned a = (unsigned)hear(down[0]), b = (unsigned)hear(down[0]);
            long u = munmap(s, (size_t)w * h * 4) < 0 ? -errno : 0;
            s = 0;
            long r1 = want(f, a, b);
            long r2 = want(f, a, b);
            tell(up[1], u);
            tell(up[1], r1);
            tell(up[1], r2);
        }
    }
}

static long ask(long op, long a, long b, long c)
{
    tell(down[1], op);
    if (op == 1 || op == 5 || op == 3 || op == 4) { tell(down[1], a); tell(down[1], b); }
    if (op == 2) tell(down[1], c);
    return op == 4 ? 0 : hear(up[0]);
}

int main(void)
{
    fb = open("/dev/fb0", O_RDWR);
    if (fb < 0) {
        show("open /dev/fb0 (no framebuffer: nothing checked)", -errno);
        return 0;
    }
    show("FBIO_TILER as uid 0 (want 0)", ioc(fb, FBIO_TILER, 0));
    unsigned char inf[64] = {0};
    struct { uint32_t w, h, x, y; } nx = {64, 32, 0, 0};
    show("the tile set next, 64 x 32 (want 0)", ioc(fb, FBIO_TILE_NEXT, &nx));
    if (pipe(up) < 0 || pipe(down) < 0) return 1;
    pid_t c = fork();
    if (c == 0) {
        client();
    }
    (void)inf;
    /* the desk's view of the screen */
    unsigned sw = 640, sh = 480;
    stride = sw * 4;
    void *m = mmap(0, (size_t)stride * sh, PROT_READ | PROT_WRITE, MAP_SHARED, fb, 0);
    screen = m == MAP_FAILED ? 0 : m;
    show("the desk maps the screen (want 1)", screen != 0);
    if (!screen) return 0;
    for (unsigned y = 0; y < sh; y++) for (unsigned x = 0; x < sw; x++) screen[y * sw + x] = 0;

    show("place the client at 100,100, 64 x 32 (want 0)", place(c, 64, 32));
    long a1 = ask(1, 64, 32, 0);
    show("the client maps 64 x 32 (want 1)", a1 > 0);
    ask(2, 0, 0, RED);
    settle();
    show_color("the screen inside the box (want red)", DX + 10, DY + 10);

    show("FBIO_TILE_WANT 96 x 48 while mapped (want -EINVAL -22)", ask(3, 96, 48, 0));
    ask(4, 96, 48, 0);
    show("munmap of the surface (want 0)", hear(up[0]));
    show("FBIO_TILE_WANT 96 x 48 after it (want 0)", hear(up[0]));
    show("FBIO_TILE_WANT again before the desk places it (want -EINVAL -22)", hear(up[0]));
    show("place it again, 96 x 48 (want 0)", place(c, 96, 48));
    settle();
    show_color("the screen inside the old box, nothing mapped (want red)", DX + 10, DY + 10);
    long a2 = ask(1, 96, 48, 0);
    show("the client maps 96 x 48 (want 1)", a2 > 0);
    show("a larger surface takes a new span (want 1)", a2 != a1);
    settle();
    show_color("the screen inside the old box, mapped and not drawn (want red)", DX + 10, DY + 10);
    show_color("the screen outside the old box, inside the new (want black)", DX + 80, DY + 40);
    ask(2, 0, 0, GREEN);
    settle();
    show_color("drawn green: inside the old box (want green)", DX + 10, DY + 10);
    show_color("drawn green: outside it, inside the new (want green)", DX + 80, DY + 40);

    ask(4, 48, 24, 0);
    show("smaller: munmap (want 0)", hear(up[0]));
    show("smaller: FBIO_TILE_WANT 48 x 24 (want 0)", hear(up[0]));
    hear(up[0]);
    show("smaller: placed (want 0)", place(c, 48, 24));
    long a3 = ask(1, 48, 24, 0);
    show("smaller: mapped where the 96 x 48 surface was (want 1)", a3 == a2);
    ask(2, 0, 0, BLUE);
    settle();
    show_color("smaller: drawn blue (want blue)", DX + 10, DY + 10);

    long before = frames_free();
    long bad = 0;
    for (int i = 0; i < ROUNDS; i++) {
        unsigned w = i % 2 ? 48 : 96, h = i % 2 ? 24 : 48;
        ask(4, w, h, 0);
        if (hear(up[0]) != 0 || hear(up[0]) != 0) bad++;
        hear(up[0]);
        if (place(c, w, h) != 0) bad++;
        if (ask(1, w, h, 0) != a2) bad++;
        ask(2, 0, 0, i % 2 ? BLUE : GREEN);
        settle();
    }
    long after = frames_free();
    show("100 resizes between 96 x 48 and 48 x 24: steps that failed (want 0)", bad);
    show("pool frames the 100 resizes kept (want 0)", before - after);
    show_color("after them: the last drawn (want blue)", DX + 10, DY + 10);
    tell(down[1], 0);
    int st = -1;
    waitpid(c, &st, 0);
    show("the client ended, status (want 0)", WIFEXITED(st) ? WEXITSTATUS(st) : -1);
    show("done", 0);
    return 0;
}
