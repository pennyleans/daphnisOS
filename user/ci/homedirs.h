/* user/ci/homedirs.h: RS-HOME (docs/specs/2026-11-11-rs-home.md): the three folders of a home, Documents, Downloads
 * and Pictures, made by a process that runs as the account. The desk is uid 0 and writes nothing into a home with
 * its own rights: home_folders forks, and the child takes the account's uid and gid by Daphnis's call 1003 (login,
 * ceiling the disk grant alone: under /home a write needs it), enters the home and makes each name 0700. A name
 * already there, whatever it is (a directory, a file, a link), is left as it is: mkdir(2) follows no link at the
 * last name and changes nothing that exists. The child runs no program and ends; the caller waits for it.
 * Returns the child's exit status: 0 when it ran as the account inside the home (a folder it could not make is not
 * a failure), 126 when the login or the home refused it (nothing is made then), or -errno when no child ran.
 * user/ci/host.c's home row calls it after call 1006 took the home; tests/hosted/homedirs_test.c includes this
 * header as it is, with HOME_LOGIN its own. */
#ifndef DAPH_HOMEDIRS_H
#define DAPH_HOMEDIRS_H

#include <errno.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

#ifndef HOME_LOGIN
#include <sys/syscall.h>
#define HOME_LOGIN(uid, gid) syscall(1003, (long)(uid), (long)(gid), 1L)   /* AC-1a; 1: the disk grant */
#endif

#define HOME_FOLDERS 3
static const char *const home_folder[HOME_FOLDERS] = {"Documents", "Downloads", "Pictures"};

static int home_folders(const char *path, long uid, long gid)
{
    int st = 0;
    pid_t got, pid = fork();
    if (pid < 0) return -errno;
    if (pid == 0) {
        if (HOME_LOGIN(uid, gid) < 0) _exit(126);
        if (chdir(path) < 0) _exit(126);
        (void)umask(077);
        for (int i = 0; i < HOME_FOLDERS; i++) (void)mkdir(home_folder[i], 0700);
        _exit(0);
    }
    do {
        got = waitpid(pid, &st, 0);
    } while (got < 0 && errno == EINTR);
    if (got < 0) return -errno;
    return WIFEXITED(st) ? WEXITSTATUS(st) : 126;
}

#endif
