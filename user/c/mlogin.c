/* user/c/mlogin.c: AC-1a's probe (docs/specs/2026-11-08-ac-accounts.md section 5). Under Daphnis it checks each
 * rule of the kernel's accounts, one line each, `mlogin: WHAT = RESULT`: the uid calls, login refused without the desk,
 * the probe becoming the desk (FBIO_TILER), login's refusals and its one-way door in the desk's child, the grant
 * ceiling (EACCES past it; keep, drop and retake within it), grant_ask's refusals, FBIO_TILER refused to a user, the
 * uid kept across fork, and login refused after execve. check-cish.sh compares the lines with
 * tests/expected/ac-mlogin.out. On Linux the Daphnis calls are -ENOSYS. Its own static musl binary (user/c/build.sh,
 * ruling DU-2 A). Exit status 0. */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <unistd.h>

#define NR_GRANT 1000
#define NR_LOGIN 1003
#define NR_GRANT_ASK 1004
#define FBIO_TILER 0x4680
#define DISK 1L
#define NET 2L
#define KERN 8L

static long call(long nr, long a, long b, long c)
{
    long r = syscall(nr, a, b, c);
    return r < 0 ? -errno : r;
}

static void show(const char *what, long r)
{
    printf("mlogin: %s = %ld\n", what, r);
    fflush(stdout);
}

int main(int argc, char **argv)
{
    if (argc > 1 && strcmp(argv[1], "afterexec") == 0) {
        show("login after execve (want -EPERM -1)", call(NR_LOGIN, 1001, 1001, DISK));
        return 0;
    }
    show("getuid", (long)getuid());
    show("getgid", (long)getgid());
    show("login with no desk (want -EPERM -1)", call(NR_LOGIN, 1000, 1000, DISK));
    int fd = open("/dev/fb0", O_RDWR);
    if (fd < 0) {
        show("open /dev/fb0 (no framebuffer: the rest skipped)", -errno);
        return 0;
    }
    long t = ioctl(fd, FBIO_TILER, 0);
    show("FBIO_TILER as uid 0 (want 0)", t < 0 ? -errno : t);
    pid_t c = fork();
    if (c == 0) {
        show("child: login uid 0 (want -EINVAL -22)", call(NR_LOGIN, 0, 0, DISK));
        show("child: login with ring 0 in the ceiling (want -EINVAL -22)", call(NR_LOGIN, 1000, 1000, DISK | KERN));
        show("child: login uid 1000 gid 100 ceiling disk (want 0)", call(NR_LOGIN, 1000, 100, DISK));
        show("child: getuid", (long)getuid());
        show("child: getgid", (long)getgid());
        show("child: login again (want -EPERM -1)", call(NR_LOGIN, 1001, 1001, DISK | NET));
        show("child: grant disk, within the ceiling (want 0)", call(NR_GRANT, DISK, 0, 0));
        show("child: grant disk and net, net past it (want -EACCES -13)", call(NR_GRANT, DISK | NET, 0, 0));
        show("child: grant nothing, a drop (want 0)", call(NR_GRANT, 0, 0, 0));
        show("child: grant disk again (want 0)", call(NR_GRANT, DISK, 0, 0));
        show("child: grant_ask disk, within the ceiling (want 0)", call(NR_GRANT_ASK, (long)"x", 1, DISK));
        show("child: grant_ask ring 0 (want -EINVAL -22)", call(NR_GRANT_ASK, (long)"x", 1, KERN));
        t = ioctl(fd, FBIO_TILER, 0);
        show("child: FBIO_TILER as uid 1000 (want -EPERM -1)", t < 0 ? -errno : t);
        pid_t g = fork();
        if (g == 0) {
            show("grandchild: getuid", (long)getuid());
            _exit(0);
        }
        waitpid(g, NULL, 0);
        _exit(0);
    }
    waitpid(c, NULL, 0);
    pid_t e = fork();
    if (e == 0) {
        char *args[] = {"mlogin", "afterexec", NULL};
        execv("/proc/self/exe", args);
        show("execve /proc/self/exe", -errno);
        _exit(1);
    }
    waitpid(e, NULL, 0);
    show("done", 0);
    return 0;
}
