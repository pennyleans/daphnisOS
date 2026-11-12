/* user/c/mperm.c: FS-1's probe (ruling FSP-1 A, docs/superpowers/specs/2026-11-09-filesystem-security-intake.md).
 * Under Daphnis, as the desk's first process, it makes /p (0777) and /p/a (0700, uid 0) with a file in it, then
 * logs a child in as uid 1000 gid 100 and checks directory search and read, one line each, `mperm: WHAT = RESULT`:
 * a path through /p/a and its "..", opening /p/a, chdir and fchdir into it are refused with EACCES; what the
 * account makes is its own (uid 1000, gid 100) and it can search, enter and read it; uid 0, back in the desk,
 * cannot search the account's 0700 directory (no uid 0 bypass). check-tiler.sh compares the lines with
 * tests/expected/fs-mperm.out. Its own static musl binary (user/c/build.sh, ruling DU-2 A). Exit status 0. */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <unistd.h>

#define NR_LOGIN 1003
#define FBIO_TILER 0x4680

static long r(long v)
{
    return v < 0 ? -errno : v;
}

static void show(const char *what, long v)
{
    printf("mperm: %s = %ld\n", what, v);
    fflush(stdout);
}

static long owner(const char *p, int gid)
{
    struct stat st;
    if (stat(p, &st) < 0) {
        return -errno;
    }
    return gid ? (long)st.st_gid : (long)st.st_uid;
}

int main(void)
{
    umask(0);
    show("mkdir /p 0777 (want 0)", r(mkdir("/p", 0777)));
    show("mkdir /p/a 0700 (want 0)", r(mkdir("/p/a", 0700)));
    int f = open("/p/a/f", O_WRONLY | O_CREAT | O_EXCL, 0644);
    show("create /p/a/f (want 0)", f < 0 ? -errno : 0);
    if (f >= 0) {
        close(f);
    }
    show("uid of /p/a", owner("/p/a", 0));
    int fb = open("/dev/fb0", O_RDWR);
    if (fb < 0) {
        show("open /dev/fb0 (no framebuffer: the rest skipped)", -errno);
        return 0;
    }
    show("FBIO_TILER as uid 0 (want 0)", r(ioctl(fb, FBIO_TILER, 0)));
    int held = open("/p/a", O_RDONLY | O_DIRECTORY);
    show("uid 0 opens /p/a (want 0)", held < 0 ? -errno : 0);
    pid_t c = fork();
    if (c == 0) {
        show("child: login uid 1000 gid 100 (want 0)", r(syscall(NR_LOGIN, 1000L, 100L, 0L)));
        struct stat st;
        show("child: stat /p (want 0)", r(stat("/p", &st)));
        show("child: stat /p/a/f, no search (want -EACCES -13)", r(stat("/p/a/f", &st)));
        show("child: stat /p/a/.. (want -EACCES -13)", r(stat("/p/a/..", &st)));
        show("child: open /p/a/f (want -EACCES -13)", r(open("/p/a/f", O_RDONLY)));
        show("child: open /p/a to read (want -EACCES -13)", r(open("/p/a", O_RDONLY | O_DIRECTORY)));
        show("child: chdir /p/a (want -EACCES -13)", r(chdir("/p/a")));
        show("child: fchdir to uid 0's /p/a (want -EACCES -13)", r(held >= 0 ? fchdir(held) : -1));
        show("child: openat /p/a f (want -EACCES -13)", r(held >= 0 ? openat(held, "f", O_RDONLY) : -1));
        show("child: mkdir /p/m 0700 (want 0)", r(mkdir("/p/m", 0700)));
        show("child: uid of /p/m", owner("/p/m", 0));
        show("child: gid of /p/m", owner("/p/m", 1));
        show("child: chdir /p/m (want 0)", r(chdir("/p/m")));
        int g = open("x", O_WRONLY | O_CREAT | O_EXCL, 0600);
        show("child: create x there (want 0)", g < 0 ? -errno : 0);
        if (g >= 0) {
            close(g);
        }
        show("child: uid of /p/m/x", owner("/p/m/x", 0));
        int d = open("/p/m", O_RDONLY | O_DIRECTORY);
        show("child: open /p/m to read (want 0)", d < 0 ? -errno : 0);
        _exit(0);
    }
    waitpid(c, NULL, 0);
    struct stat st;
    show("uid 0: stat /p/m (want 0)", r(stat("/p/m", &st)));
    show("uid 0: stat /p/m/x, no bypass (want -EACCES -13)", r(stat("/p/m/x", &st)));
    show("uid 0: chdir /p/m, no bypass (want -EACCES -13)", r(chdir("/p/m")));
    show("uid 0: stat /p/a/f, its own (want 0)", r(stat("/p/a/f", &st)));
    show("done", 0);
    return 0;
}
