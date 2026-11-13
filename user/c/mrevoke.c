/* user/c/mrevoke.c: GV-1a's probe (docs/specs/2026-11-11-gv-revoke.md sections 2 and 5). Under Daphnis it checks
 * revoke(vpid, word), one line each, `mrevoke: WHAT = RESULT`: only the desk may ask; ring 0 and unknown bits are
 * refused; a revoke named by any process of a window reaches the whole window and no other; the bits leave the word,
 * grant (1000) cannot take them back, a socket is refused, a child forked later and a program exec'd later hold
 * neither the bit nor the way back; an orphan of the window is reached. check-tiler.sh compares the lines with tests/expected/gv-mrevoke.out.
 * On Linux the Daphnis calls are -ENOSYS. Its own static musl binary (user/c/build.sh, ruling DU-2 A). Exit status 0. */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <unistd.h>

#define NR_GRANT 1000
#define NR_LOGIN 1003
#define NR_FACTS 1007
#define NR_REVOKE 1008
#define FBIO_TILER 0x4680
#define DISK 1L
#define NET 2L
#define AUDIO 4L
#define KERN 8L
#define REC 88

static long call(long nr, long a, long b, long c, long d)
{
    long r = syscall(nr, a, b, c, d);
    return r < 0 ? -errno : r;
}

static void show(const char *what, long r)
{
    printf("mrevoke: %s = %ld\n", what, r);
    fflush(stdout);
}

/* The grant word of the process whose pid is `pid`, as facts(2, slot) shows it to this caller; -1 when not seen. */
static long word_of(long pid)
{
    unsigned char b[REC];
    for (long id = 0; id < 64; id++) {
        unsigned long p, st, g;
        if (call(NR_FACTS, 2, id, (long)b, REC) < REC) break; /* the record only grows (KF-R1: 96 bytes) */
        memcpy(&p, b, 8);
        memcpy(&st, b + 24, 8);
        memcpy(&g, b + 72, 8);
        if (st != 0 && (long)p == pid) return (long)g;
    }
    return -1;
}

static long sock(void)
{
    int s = socket(AF_INET, SOCK_DGRAM, 0);
    if (s < 0) return -errno;
    close(s);
    return 0;
}

static void wait_byte(int fd) { char x; if (read(fd, &x, 1) != 1) _exit(1); }
static void send_byte(int fd) { if (write(fd, "x", 1) != 1) _exit(1); }
static void send_long(int fd, long v) { if (write(fd, &v, sizeof v) != (ssize_t)sizeof v) _exit(1); }
static long take_long(int fd) { long v; if (read(fd, &v, sizeof v) != (ssize_t)sizeof v) _exit(1); return v; }

int main(int argc, char **argv)
{
    if (argc > 1 && strcmp(argv[1], "afterexec") == 0) {
        show("a program exec'd after the revoke: its word (want 1)", word_of(getpid()));
        show("a program exec'd after the revoke: grant net (want -EACCES -13)", call(NR_GRANT, NET | DISK, 0, 0, 0));
        show("a program exec'd after the revoke: a socket (want -EACCES -13)", sock());
        return 0;
    }
    int fd = open("/dev/fb0", O_RDWR);
    if (fd < 0) {
        show("open /dev/fb0 (no framebuffer: nothing checked)", -errno);
        return 0;
    }
    show("revoke before there is a desk (want -EPERM -1)", call(NR_REVOKE, getpid(), NET, 0, 0));
    long t = ioctl(fd, FBIO_TILER, 0);
    show("FBIO_TILER as uid 0 (want 0)", t < 0 ? -errno : t);
    show("desk: revoke ring 0 (want -EINVAL -22)", call(NR_REVOKE, 9999, KERN | NET, 0, 0));
    show("desk: revoke an unknown bit (want -EINVAL -22)", call(NR_REVOKE, 9999, 16, 0, 0));
    show("desk: revoke on a pid that is not there (want -ESRCH -3)", call(NR_REVOKE, 9999, NET, 0, 0));
    show("desk: revoke on itself, a process of no window (want -ESRCH -3)", call(NR_REVOKE, getpid(), NET, 0, 0));

    int up[2], a1[2], g1[2], gk[2], b1[2], o1[2];   /* up: to the desk; a1, b1, o1: the desk to each; g1, gk: child 1 and its child */
    if (pipe(up) < 0 || pipe(a1) < 0 || pipe(g1) < 0 || pipe(gk) < 0 || pipe(b1) < 0 || pipe(o1) < 0) return 1;

    pid_t ca = fork();                           /* window A: child 1, its child G and, later, an orphan */
    if (ca == 0) {
        show("child 1: login uid 1000, ceiling disk and net (want 0)", call(NR_LOGIN, 1000, 100, DISK | NET, 0));
        show("child 1: revoke as a user (want -EPERM -1)", call(NR_REVOKE, getpid(), NET, 0, 0));
        show("child 1: grant disk and net, within the ceiling (want 0)", call(NR_GRANT, DISK | NET, 0, 0, 0));
        show("child 1: its word (want 3)", word_of(getpid()));
        show("child 1: a socket (want 0)", sock());
        pid_t g = fork();
        if (g == 0) {
            wait_byte(g1[0]);
            show("grandchild: its word after the revoke (want 1)", word_of(getpid()));
            show("grandchild: grant net again (want -EACCES -13)", call(NR_GRANT, NET | DISK, 0, 0, 0));
            send_byte(gk[1]);
            _exit(0);
        }
        send_long(up[1], (long)g);
        wait_byte(a1[0]);                        /* the desk has revoked net, naming the grandchild */
        show("child 1: its word after the revoke (want 1)", word_of(getpid()));
        show("child 1: grant disk and net again, no prompt (want -EACCES -13)", call(NR_GRANT, DISK | NET, 0, 0, 0));
        show("child 1: grant disk alone, still its own (want 0)", call(NR_GRANT, DISK, 0, 0, 0));
        show("child 1: a socket now (want -EACCES -13)", sock());
        pid_t late = fork();
        if (late == 0) {
            show("a child forked after the revoke: its word (want 1)", word_of(getpid()));
            show("a child forked after the revoke: grant net (want -EACCES -13)", call(NR_GRANT, NET | DISK, 0, 0, 0));
            show("a child forked after the revoke: a socket (want -EACCES -13)", sock());
            _exit(0);
        }
        waitpid(late, NULL, 0);
        pid_t ex = fork();
        if (ex == 0) {
            char *args[] = {"mrevoke", "afterexec", NULL};
            execv("/proc/self/exe", args);
            show("execve /proc/self/exe", -errno);
            _exit(1);
        }
        waitpid(ex, NULL, 0);
        send_byte(g1[1]);
        wait_byte(gk[0]);                        /* the grandchild has printed */
        waitpid(g, NULL, 0);
        pid_t orphan = fork();
        if (orphan == 0) {
            send_long(up[1], (long)getpid());
            wait_byte(o1[0]);                    /* its parent has ended and the desk has revoked disk */
            show("the orphan: its word after the revoke (want 0)", word_of(getpid()));
            send_byte(up[1]);
            _exit(0);
        }
        _exit(0);                                /* child 1 ends; the orphan lives on in window A */
    }
    long gpid = take_long(up[0]);

    pid_t cb = fork();                           /* window B: child 2 */
    if (cb == 0) {
        call(NR_LOGIN, 1001, 100, NET, 0);
        call(NR_GRANT, NET, 0, 0, 0);
        send_byte(up[1]);
        wait_byte(b1[0]);
        show("child 2, another window: its word, untouched (want 2)", word_of(getpid()));
        show("child 2: a socket (want 0)", sock());
        _exit(0);
    }
    wait_byte(up[0]);

    show("desk: child 1's word before (want 3)", word_of(ca));
    show("desk: revoke net, naming the grandchild: the whole window, 2 processes (want 2)", call(NR_REVOKE, gpid, NET, 0, 0));
    show("desk: child 1's word (want 1)", word_of(ca));
    show("desk: the grandchild's word (want 1)", word_of(gpid));
    show("desk: child 2's word, another window (want 2)", word_of(cb));
    show("desk: revoke net again: none holds it (want 0)", call(NR_REVOKE, ca, NET, 0, 0));
    send_byte(a1[1]);
    long opid = take_long(up[0]);
    waitpid(ca, NULL, 0);                        /* child 1 has ended: the orphan's parent is gone */
    show("desk: revoke disk, naming the orphan of window A (want 1)", call(NR_REVOKE, opid, DISK | AUDIO, 0, 0));
    send_byte(o1[1]);
    wait_byte(up[0]);
    send_byte(b1[1]);
    waitpid(cb, NULL, 0);
    show("done", 0);
    return 0;
}
