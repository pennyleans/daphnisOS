/* user/c/mexepath.c: AC-T2's probe (docs/specs/2026-11-11-ac-t2-image-path.md). Under Daphnis, as the desk, it
 * reads FBIO_TILE_INFO kinds 13 and 14, the program a window's process runs as the kernel loaded it, beside kinds 0
 * and 1's comm, one line each, `mexepath: WHAT = RESULT`:
 *   the desk itself; a child that renamed itself with prctl (comm moves, the path does not); a child that exec'd
 *   /bin/sleep; a child that exec'd a copy of it on the volume (source 1, its /home path); a terminal's foreground
 *   process by the pty master (kind 14); a vpid of no process (-ESRCH); a caller that is not the desk (-EPERM).
 * The volume part runs only where the boot has a volume on /home, and a line says whether it has one: the desk flavor
 * (check-tiler.sh) has none, and its lines are tests/expected/ac-mexepath.out; a desknet boot with a volume prints the
 * volume part too (source 1, the /home path).
 * On Linux the Daphnis calls are -ENOSYS. Its own static musl binary (user/c/build.sh, DU-2 A). Exit status 0. */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/prctl.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <unistd.h>

#define NR_GRANT 1000
#define FBIO_TILER 0x4680
#define FBIO_TILE_INFO 0x4687
#define TIOCGPTN_ 0x80045430
#define TIOCSPTLCK_ 0x40045431
#define DISK 1L

static int fb;

static void show(const char *what, long r)
{
    printf("mexepath: %s = %ld\n", what, r);
    fflush(stdout);
}

static void show_s(const char *what, const char *s)
{
    printf("mexepath: %s = %s\n", what, s);
    fflush(stdout);
}

static uint32_t u32(const unsigned char *b) { return b[0] | b[1] << 8 | b[2] << 16 | (uint32_t)b[3] << 24; }

/* FBIO_TILE_INFO kind, id into b (64 bytes); 0 or -errno */
static long info(int fd, unsigned kind, unsigned id, unsigned char *b)
{
    memset(b, 0, 64);
    memcpy(b, &kind, 4);
    memcpy(b + 4, &id, 4);
    return ioctl(fd, FBIO_TILE_INFO, b) < 0 ? -errno : 0;
}

/* kind 13 or 14: "source PATH", the length checked against the bytes and the NULs after them checked */
static void show_path(const char *what, unsigned kind, unsigned id)
{
    unsigned char b[64];
    char line[96];
    long r = info(fb, kind, id, b);
    if (r < 0) {
        show(what, r);
        return;
    }
    uint32_t n = u32(b + 8);
    int padded = n >= 1 && n <= 48;
    for (unsigned i = 16 + n; padded && i < 64; i++) padded = b[i] == 0;
    snprintf(line, sizeof line, "source %u, %.*s%s", u32(b + 4), (int)(n <= 48 ? n : 0), (char *)b + 16,
             padded && u32(b + 12) == 0 ? "" : " (bad padding)");
    show_s(what, line);
}

static void show_comm(const char *what, unsigned kind, unsigned id)
{
    unsigned char b[64];
    long r = info(fb, kind, id, b);
    if (r < 0) {
        show(what, r);
        return;
    }
    char c[17] = {0};
    memcpy(c, b + 16, 16);
    show_s(what, c);
}

/* A child that runs path; the parent learns the exec happened when the close-on-exec end shuts with nothing written.
 * A failed exec writes its errno there and ends: the answer is then -errno, and the child has been waited for. */
static pid_t spawn(const char *path, int pts)
{
    int p[2];
    if (pipe(p) < 0) return -1;
    fcntl(p[1], F_SETFD, FD_CLOEXEC);
    pid_t c = fork();
    if (c == 0) {
        close(p[0]);
        if (pts >= 0) {
            setsid();
            dup2(pts, 0);
        }
        char *argv[] = {"sleep", "5", 0};
        char *envp[] = {0};
        execve(path, argv, envp);
        int e = errno;
        if (write(p[1], &e, sizeof e) != sizeof e) _exit(126);
        _exit(127);
    }
    close(p[1]);
    int e = 0;
    long got = read(p[0], &e, sizeof e);
    close(p[0]);
    if (got == sizeof e) {
        waitpid(c, 0, 0);
        return -e;
    }
    return c;
}

static void end(pid_t c)
{
    if (c > 0) {                               /* a running child only: one whose exec failed has been waited for */
        kill(c, SIGKILL);
        waitpid(c, 0, 0);
    }
}

static long copy(const char *from, const char *to)
{
    char buf[4096];
    int a = open(from, O_RDONLY);
    if (a < 0) return -errno;
    int z = open(to, O_CREAT | O_WRONLY | O_TRUNC, 0755);
    if (z < 0) { close(a); return -errno; }
    long n, all = 0;
    while ((n = read(a, buf, sizeof buf)) > 0) {
        if (write(z, buf, n) != n) { all = -EIO; break; }
        all += n;
    }
    close(a);
    close(z);
    return all > 0 ? 0 : all;
}

int main(void)
{
    fb = open("/dev/fb0", O_RDWR);
    if (fb < 0) {
        show("open /dev/fb0 (no framebuffer: nothing checked)", -errno);
        return 0;
    }
    long t = ioctl(fb, FBIO_TILER, 0);
    show("FBIO_TILER as uid 0 (want 0)", t < 0 ? -errno : t);
    unsigned me = (unsigned)getpid();
    show_path("the desk itself, kind 13 (want source 0, /tiler)", 13, me);

    /* prctl moves the comm and not the path */
    int up[2], down[2];
    if (pipe(up) < 0 || pipe(down) < 0) return 1;
    pid_t c = fork();
    if (c == 0) {
        char x;
        prctl(PR_SET_NAME, "ced", 0, 0, 0);
        if (write(up[1], "x", 1) != 1 || read(down[0], &x, 1) != 1) _exit(1);
        unsigned char b[64];
        show("a child asks kind 13 itself, not the desk (want -EPERM -1)", info(fb, 13, me, b));
        _exit(0);
    }
    char x;
    if (read(up[0], &x, 1) != 1) return 1;
    show_comm("a child that named itself ced by prctl, kind 0's comm (want ced)", 0, (unsigned)c);
    show_path("the same child, kind 13 (want source 0, /tiler)", 13, (unsigned)c);
    if (write(down[1], "x", 1) != 1) return 1;
    waitpid(c, 0, 0);

    /* an image member */
    c = spawn("/bin/sleep", -1);
    show("a child execs /bin/sleep (want a vpid, 1)", c > 0 ? 1 : (long)c);
    show_comm("a child that exec'd /bin/sleep, kind 0's comm (want bin/sleep, the member's name)", 0, (unsigned)c);
    show_path("the same child, kind 13 (want source 0, /bin/sleep)", 13, (unsigned)c);
    end(c);

    /* a program on the volume */
    syscall(NR_GRANT, DISK, 0, 0);
    long cp = copy("/bin/sleep", "/home/sleep");
    show("this boot has a volume on /home (a copy of /bin/sleep made there)", cp == 0);
    if (cp == 0) {
        c = spawn("/home/sleep", -1);
        show("a child execs /home/sleep (want 1)", c > 0 ? 1 : (long)c);
        show_comm("a child that exec'd /home/sleep, kind 0's comm (want sleep)", 0, (unsigned)c);
        show_path("the same child, kind 13 (want source 1, /home/sleep)", 13, (unsigned)c);
        end(c);
        unlink("/home/sleep");
    }

    /* a terminal's foreground process, by the master */
    int m = open("/dev/ptmx", O_RDWR | O_NOCTTY);
    int unlock = 0;
    unsigned n = 0;
    if (m >= 0 && ioctl(m, TIOCSPTLCK_, &unlock) == 0 && ioctl(m, TIOCGPTN_, &n) == 0) {
        char name[32];
        snprintf(name, sizeof name, "/dev/pts/%u", n);
        int s = open(name, O_RDWR | O_NOCTTY);
        show("a pty pair (want 1)", s >= 0);
        c = spawn("/bin/sleep", s);
        if (s >= 0) close(s);
        show("a child on the pty's slave execs /bin/sleep (want 1)", c > 0 ? 1 : (long)c);
        show_comm("the terminal's foreground process, kind 1's comm (want bin/sleep)", 1, (unsigned)m);
        show_path("the same, kind 14 by the master (want source 0, /bin/sleep)", 14, (unsigned)m);
        end(c);
        close(m);
    } else {
        show("a pty pair (want 1)", 0);
    }

    show_path("a vpid of no process, kind 13 (want -ESRCH -3)", 13, 60);
    show("done", 0);
    return 0;
}
