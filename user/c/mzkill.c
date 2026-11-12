/* user/c/mzkill.c: KILL-Z's probe. A signal sent to a child that has ended and is not yet waited for: Linux answers 0
 * and the child's status is its own exit; Daphnis ran the signal's end a second time on a process whose space was
 * already freed, and the kernel faulted (host.error.phys_read64 in src/uvm.ci's state digest). Any process could do
 * it to its own child. One line each, `mzkill: WHAT = RESULT`; the same lines on Linux and under Daphnis
 * (check-tiler.sh compares them with tests/expected/k-mzkill.out). Its own static musl binary (user/c/build.sh,
 * DU-2 A). Exit status 0. */
#define _GNU_SOURCE
#include <errno.h>
#include <signal.h>
#include <stdio.h>
#include <sys/wait.h>
#include <unistd.h>

static void show(const char *what, long r)
{
    printf("mzkill: %s = %ld\n", what, r);
    fflush(stdout);
}

static long status_of(pid_t c)
{
    int st = 0;
    if (waitpid(c, &st, 0) != c) return -1;
    if (WIFEXITED(st)) return WEXITSTATUS(st);
    if (WIFSIGNALED(st)) return 1000 + WTERMSIG(st);
    return -2;
}

int main(void)
{
    int p[2];
    if (pipe(p) < 0) return 1;
    pid_t c = fork();
    if (c == 0) {
        close(p[0]);
        _exit(7);
    }
    close(p[1]);
    char x;
    while (read(p[0], &x, 1) > 0) {}            /* its end of the pipe closed: it has ended */
    close(p[0]);
    usleep(100000);
    show("kill(SIGKILL) of an ended child not yet waited for (want 0)", kill(c, SIGKILL) < 0 ? -errno : 0);
    show("kill(SIGTERM) of it again (want 0)", kill(c, SIGTERM) < 0 ? -errno : 0);
    show("kill(0) of it, a probe (want 0)", kill(c, 0) < 0 ? -errno : 0);
    show("its status, waited: its own exit (want 7)", status_of(c));
    show("kill(SIGKILL) of it once waited for (want -ESRCH -3)", kill(c, SIGKILL) < 0 ? -errno : 0);

    int q[2];
    if (pipe(q) < 0) return 1;
    c = fork();
    if (c == 0) {
        close(q[1]);
        while (read(q[0], &x, 1) > 0) {}        /* runs until the parent's end closes */
        _exit(0);
    }
    close(q[0]);
    show("kill(SIGKILL) of a running child (want 0)", kill(c, SIGKILL) < 0 ? -errno : 0);
    show("its status, waited: the signal (want 1009, 1000 + SIGKILL)", status_of(c));
    close(q[1]);
    show("done", 0);
    return 0;
}
