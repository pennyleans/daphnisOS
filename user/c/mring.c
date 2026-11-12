/* user/c/mring.c: GV-1c's probe (docs/specs/2026-11-11-gv-revoke.md section 2a, ruling GV-R2). Under Daphnis, as the
 * desk, it shows that nothing a process took while it held ring 0 outlasts ring 0, one line each,
 * `mring: WHAT = RESULT`:
 *   A, the ruled case: the desk revokes net from a window; under a hold (ring 0) the program takes net again and
 *     uses it; the desk ends the hold; the bit is gone, grant (1000) answers -EACCES again, the connection it opened
 *     is shut;
 *   B: a program in ring 0 leaves it with one grant call that asks for a grant beyond its ceiling: -EACCES, and
 *     ring 0 has ended all the same;
 *   C: the same in two calls (the grant with ring 0 first, then without);
 *   D: a grant the desk said yes to (grant_ask) is beyond the ceiling too and goes when ring 0 ends; ending a hold
 *     on a program outside ring 0 changes nothing.
 * The TCP lines run only where the boot has a network and the host's HTTP server (10.0.2.2:8080), and the first
 * line says so. The lines are pinned in tests/expected/gv-mring-desknet.out (check-revoke.sh). On Linux the Daphnis
 * calls are -ENOSYS. Its own static musl binary (user/c/build.sh, DU-2 A). */
#define _GNU_SOURCE
#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <sched.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <unistd.h>

#define NR_GRANT 1000
#define NR_KERN 1001
#define NR_LOGIN 1003
#define NR_GRANT_ASK 1004
#define NR_REVOKE 1008
#define FBIO_TILER 0x4680
#define FBIO_TILE_KERN 0x468D
#define DISK 1L
#define NET 2L
#define KERN 8L
#define HOST "10.0.2.2"
#define HTTP 8080

static int fb, up[2], down[2];

static long call(long nr, long a, long b, long c)
{
    long r = syscall(nr, a, b, c);
    return r < 0 ? -errno : r;
}

static void show(const char *what, long r)
{
    printf("mring: %s = %ld\n", what, r);
    fflush(stdout);
}

static long ret(long r) { return r < 0 ? -errno : r; }
static void wait_byte(int fd) { char x; if (read(fd, &x, 1) != 1) _exit(1); }
static void send_byte(int fd) { if (write(fd, "x", 1) != 1) _exit(1); }
static void child_turn(void) { send_byte(up[1]); wait_byte(down[0]); }   /* the child stops; the desk acts */
static void desk_wait(void) { wait_byte(up[0]); }
static void desk_go(void) { send_byte(down[1]); }

/* The desk's word on ring 0 for the child: 1 yes to its request, 2 a hold, 3 the hold cleared. */
static long word(pid_t c, unsigned verb)
{
    unsigned a[2] = {(unsigned)c, verb};
    return ret(ioctl(fb, FBIO_TILE_KERN, a));
}

static long sock(void)
{
    int s = socket(AF_INET, SOCK_DGRAM, 0);
    if (s < 0) return -errno;
    close(s);
    return 1;
}

static int tcp_to_host(void)
{
    struct sockaddr_in a = {0};
    int s = socket(AF_INET, SOCK_STREAM, 0);
    if (s < 0) return -1;
    a.sin_family = AF_INET;
    a.sin_port = htons(HTTP);
    inet_pton(AF_INET, HOST, &a.sin_addr);
    if (connect(s, (struct sockaddr *)&a, sizeof a) < 0) { close(s); return -1; }
    return s;
}

static pid_t start(void)
{
    if (pipe(up) < 0 || pipe(down) < 0) _exit(1);
    return fork();
}

static void ended(const char *what, pid_t c)
{
    int st = -1;
    waitpid(c, &st, 0);
    show(what, WIFEXITED(st) ? WEXITSTATUS(st) : -1);
    close(up[0]); close(up[1]); close(down[0]); close(down[1]);
}

int main(void)
{
    char buf[2048];
    fb = open("/dev/fb0", O_RDWR);
    if (fb < 0) {
        show("open /dev/fb0 (no framebuffer: nothing checked)", -errno);
        return 0;
    }
    long t = ioctl(fb, FBIO_TILER, 0);
    show("FBIO_TILER as uid 0 (want 0)", t < 0 ? -errno : t);
    show("desk: grant disk and net to itself (want 0)", call(NR_GRANT, DISK | NET, 0, 0));
    int probe = tcp_to_host();
    long has_net = probe >= 0;
    if (probe >= 0) close(probe);
    show("this boot has a network and the host's server", has_net);

    /* A: a revoked grant taken again under ring 0 */
    pid_t c = start();
    if (c == 0) {
        show("A child: login uid 1000, ceiling disk and net (want 0)", call(NR_LOGIN, 1000, 100, DISK | NET));
        show("A child: grant disk and net, within the ceiling (want 0)", call(NR_GRANT, DISK | NET, 0, 0));
        child_turn();                            /* the desk revokes net */
        show("A child: grant disk and net again (want -EACCES -13)", call(NR_GRANT, DISK | NET, 0, 0));
        show("A child: a socket (want -13)", sock());
        child_turn();                            /* the desk gives the window a hold */
        show("A child: holds ring 0 (want 1)", call(NR_KERN, 0, 0, 0));
        show("A child: under ring 0, grant ring 0, disk and net (want 0)", call(NR_GRANT, KERN | DISK | NET, 0, 0));
        show("A child: a socket (want 1)", sock());
        int s = -1;
        if (has_net) {
            s = tcp_to_host();
            show("A child: a TCP connection to the host (want 1)", s >= 0);
            const char *req = "GET /f HTTP/1.0\r\n\r\n";
            show("A child: sends the request (want 19)", ret(write(s, req, strlen(req))));
            show("A child: reads the first bytes of the download (want 1)", ret(read(s, buf, 1000)) > 0);
        }
        child_turn();                            /* the desk ends the hold */
        show("A child: holds ring 0 (want 0)", call(NR_KERN, 0, 0, 0));
        if (has_net) {
            show("A child: the next read of the download ends (want 0)", ret(read(s, buf, 1000)));
            show("A child: a write to the connection fails (want -13)", ret(write(s, "x", 1)));
        }
        show("A child: a socket (want -13)", sock());
        show("A child: grant disk and net, no prompt (want -13)", call(NR_GRANT, DISK | NET, 0, 0));
        show("A child: grant disk alone, still its own (want 0)", call(NR_GRANT, DISK, 0, 0));
        _exit(0);
    }
    desk_wait();
    show("A desk: revoke net from the child's window (want 1)", call(NR_REVOKE, c, NET, 0));
    desk_go();
    desk_wait();
    show("A desk: a hold for the window (want 0)", word(c, 2));
    desk_go();
    desk_wait();
    show("A desk: the hold cleared (want 0)", word(c, 3));
    desk_go();
    ended("A desk: the child ended by itself, status (want 0)", c);

    /* B: leaving ring 0 in one call that asks beyond the ceiling */
    c = start();
    if (c == 0) {
        show("B child: login uid 1000, ceiling disk (want 0)", call(NR_LOGIN, 1000, 100, DISK));
        child_turn();                            /* a hold */
        show("B child: holds ring 0 (want 1)", call(NR_KERN, 0, 0, 0));
        show("B child: grant disk and net, ring 0 left out (want -13)", call(NR_GRANT, DISK | NET, 0, 0));
        show("B child: holds ring 0, the call ended it all the same (want 0)", call(NR_KERN, 0, 0, 0));
        show("B child: a socket (want -13)", sock());
        show("B child: grant ring 0 back (want -EPERM -1)", call(NR_GRANT, KERN | DISK, 0, 0));
        show("B child: grant disk, within the ceiling (want 0)", call(NR_GRANT, DISK, 0, 0));
        _exit(0);
    }
    desk_wait();
    show("B desk: a hold for the window (want 0)", word(c, 2));
    desk_go();
    ended("B desk: the child ended by itself, status (want 0)", c);

    /* C: the same in two calls */
    c = start();
    if (c == 0) {
        show("C child: login uid 1000, ceiling disk (want 0)", call(NR_LOGIN, 1000, 100, DISK));
        child_turn();                            /* a hold */
        show("C child: under ring 0, grant ring 0, disk and net (want 0)", call(NR_GRANT, KERN | DISK | NET, 0, 0));
        show("C child: a socket (want 1)", sock());
        show("C child: grant disk and net, ring 0 left out (want -13)", call(NR_GRANT, DISK | NET, 0, 0));
        show("C child: holds ring 0 (want 0)", call(NR_KERN, 0, 0, 0));
        show("C child: a socket (want -13)", sock());
        show("C child: grant disk, within the ceiling (want 0)", call(NR_GRANT, DISK, 0, 0));
        show("C child: a socket (want -13)", sock());
        _exit(0);
    }
    desk_wait();
    show("C desk: a hold for the window (want 0)", word(c, 2));
    desk_go();
    ended("C desk: the child ended by itself, status (want 0)", c);

    /* D: the desk's yes is beyond the ceiling too */
    c = start();
    if (c == 0) {
        show("D child: login uid 1000, ceiling disk (want 0)", call(NR_LOGIN, 1000, 100, DISK));
        send_byte(up[1]);                        /* the desk answers the request this call makes */
        long asked = call(NR_GRANT_ASK, (long)"mring", 5, NET);
        wait_byte(down[0]);                      /* the desk has printed its yes: the lines keep one order */
        show("D child: grant_ask net, the desk says yes (want 0)", asked);
        show("D child: a socket (want 1)", sock());
        child_turn();                            /* the desk clears a hold the window does not have */
        show("D child: a socket, nothing changed (want 1)", sock());
        child_turn();                            /* a hold, then cleared */
        show("D child: holds ring 0 (want 0)", call(NR_KERN, 0, 0, 0));
        show("D child: a socket (want -13)", sock());
        show("D child: grant net, no prompt (want -13)", call(NR_GRANT, NET, 0, 0));
        _exit(0);
    }
    desk_wait();
    long yes = -1;
    for (int k = 0; k < 100000 && yes != 0; k++) {
        yes = word(c, 1);
        if (yes != 0) sched_yield();
    }
    show("D desk: yes to the child's request (want 0)", yes);
    desk_go();
    desk_wait();
    show("D desk: clears a hold on a window outside ring 0 (want 0)", word(c, 3));
    desk_go();
    desk_wait();
    show("D desk: a hold for the window (want 0)", word(c, 2));
    show("D desk: the hold cleared (want 0)", word(c, 3));
    desk_go();
    ended("D desk: the child ended by itself, status (want 0)", c);
    show("done", 0);
    return 0;
}
