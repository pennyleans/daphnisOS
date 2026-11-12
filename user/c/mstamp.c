/* user/c/mstamp.c: the probe of FS-4 with ruling FS-R3 C (docs/specs/2026-11-07-bu2-meta.md section 4.6). Under
 * Daphnis it shows that file stamps take one time for the whole system, one line each, `mstamp: WHAT = RESULT`, in
 * seconds past the boot's base: a long-running program sleeps 3 s and writes a file; a program it starts afresh,
 * whose own clock reads 0, writes a second file, which must not read earlier; its utimensat with no times agrees;
 * the stamp moves on only when a clock passes the furthest one. check-tiler.sh compares the lines with
 * tests/expected/fs-mstamp.out. Gates boot on the fixed epoch, 2026-01-01T00:00:00Z. Its own static musl binary
 * (user/c/build.sh, ruling DU-2 A). Exit status 0. */
#define _GNU_SOURCE
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#define EPOCH 1767225600L

static void show(const char *what, long r)
{
    printf("mstamp: %s = %ld\n", what, r);
    fflush(stdout);
}

static long mtime_of(const char *p)
{
    struct stat s;
    return stat(p, &s) == 0 ? (long)s.st_mtime - EPOCH : -1;
}

static void make(const char *p)
{
    int fd = open(p, O_CREAT | O_WRONLY | O_TRUNC, 0644);
    if (fd >= 0) {
        if (write(fd, "x", 1) != 1) {}
        close(fd);
    }
}

static void rest(long s)
{
    struct timespec ts = {s, 0};
    nanosleep(&ts, 0);
}

static long own_clock(void)
{
    struct timespec now;
    clock_gettime(CLOCK_REALTIME, &now);
    return (long)now.tv_sec - EPOCH;
}

int main(int argc, char **argv)
{
    if (argc > 1 && strcmp(argv[1], "fresh") == 0) {
        show("the fresh program: its own CLOCK_REALTIME, unchanged by the ruling (want 0)", own_clock());
        make("/late");
        show("the fresh program writes /late: its stamp (want 3)", mtime_of("/late"));
        show("/late is not earlier than /early (want 1)", mtime_of("/late") >= mtime_of("/early"));
        show("utimensat with no times on /early, from the fresh program (want 0)", utimensat(AT_FDCWD, "/early", NULL, 0));
        show("/early after it (want 3)", mtime_of("/early"));
        rest(2);
        make("/later");
        show("after the fresh program slept 2 s, behind the furthest clock: /later (want 3)", mtime_of("/later"));
        rest(2);
        make("/last");
        show("after 2 s more, its clock at 4, past the furthest: /last (want 4)", mtime_of("/last"));
        return 0;
    }
    make("/first");
    show("a file written at once (want 0)", mtime_of("/first"));
    rest(3);
    make("/early");
    show("the long-running program slept 3 s and writes /early (want 3)", mtime_of("/early"));
    pid_t c = fork();
    if (c == 0) {
        char *args[] = {"mstamp", "fresh", NULL};
        execv("/proc/self/exe", args);
        _exit(1);
    }
    waitpid(c, NULL, 0);
    make("/after");
    show("the long-running program again, its clock at 3: /after is not earlier than /last (want 1)", mtime_of("/after") >= mtime_of("/last"));
    show("/after (want 4)", mtime_of("/after"));
    show("done", 0);
    return 0;
}
