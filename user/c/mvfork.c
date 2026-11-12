/* user/c/mvfork.c: the probe of unit BU-4a, K12 (docs/specs/2026-11-07-bu4-toolchain.md 4.8): musl's posix_spawn
 * (clone with CLONE_VM | CLONE_VFORK | SIGCHLD on a stack of its own) of a program and of a missing path, and vfork:
 * the child's store is the parent's, and the parent goes on only after the child's execve or exit. check-disk.sh runs
 * it in the write session; tools/check-disk.py holds its lines to the same run on Linux. */
#define _GNU_SOURCE   /* vfork */
#include <errno.h>
#include <spawn.h>
#include <stdio.h>
#include <sys/wait.h>
#include <unistd.h>

extern char **environ;

static volatile int shared;

int main(void)
{
    pid_t pid;
    int st = -1;
    char *hello[] = {"./hello", NULL};
    char *none[] = {"./no-such-program", NULL};

    fflush(stdout);
    int r = posix_spawn(&pid, "./hello", NULL, NULL, hello, environ);
    if (r == 0) waitpid(pid, &st, 0);
    printf("spawn hello: %d, exit %d\n", r, WIFEXITED(st) ? WEXITSTATUS(st) : -1);

    r = posix_spawn(&pid, "./no-such-program", NULL, NULL, none, environ);
    printf("spawn missing: %d\n", r);

    fflush(stdout);
    shared = 1;
    pid = vfork();
    if (pid == 0) {
        shared = 42;
        _exit(7);
    }
    st = -1;
    waitpid(pid, &st, 0);
    printf("vfork: the child's store %d, exit %d\n", shared, WIFEXITED(st) ? WEXITSTATUS(st) : -1);

    fflush(stdout);
    pid = vfork();
    if (pid == 0) {
        execve("./hello", hello, environ);
        _exit(127);
    }
    st = -1;
    waitpid(pid, &st, 0);
    printf("vfork then execve: exit %d\n", WIFEXITED(st) ? WEXITSTATUS(st) : -1);
    return 0;
}
