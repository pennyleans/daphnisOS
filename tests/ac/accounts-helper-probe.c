#define _DEFAULT_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <unistd.h>

/*
 * Test wrapper installed at /bin/authd in a disposable initrd while the real
 * helper lives at /bin/authd-real.
 *
 * When invoked by accounts (uid != 0) during 'kern accounts add' or
 * 'kern accounts passwd', checks before execve('/bin/authd-real', ...):
 *   1. open('/home/accounts-helper-disk.txt', O_WRONLY|O_CREAT|O_TRUNC, 0600)
 *      requires GRANT_DISK (or GRANT_KERN) and fails with EROFS (30) when dropped.
 *   2. open('/home/.daphnis/accounts-helper-kern.txt', O_WRONLY|O_CREAT|O_TRUNC, 0600)
 *      requires GRANT_KERN when uid != 0 (src/fs.ci walk on x_daphnis) and fails
 *      with EACCES (13) even if GRANT_DISK were held.
 *   3. syscall(1001, 0, 0) (kern_held) returns 0 when GRANT_KERN is not held.
 *
 * Because accounts runs under a terminal pty rather than the serial console,
 * non-root invocations append their records to /probe/accounts-probe.log (FS-2: /probe
 * is a 0777 directory the harness adds, since no account writes the image's root); the
 * next uid 0 invocation by hdesk drains /probe/accounts-probe.log
 * to fd 2 (serial.txt) before chaining to /bin/authd-real.
 *
 * When invoked as 'authd --check-fail-start', exercises pipe exhaustion (first
 * and second pipe) and child pre-exec exit (127) against /bin/accounts and
 * verifies /home/.daphnis/accounts is unchanged.
 */

static void append_log(const char *line, size_t n)
{
    int fd = open("/probe/accounts-probe.log", O_WRONLY | O_CREAT | O_APPEND, 0666);
    if (fd >= 0) {
        (void)!write(fd, line, n);
        close(fd);
    }
}

static void drain_log_to_serial(void)
{
    char buf[1024];
    int fd = open("/probe/accounts-probe.log", O_RDONLY);
    if (fd < 0) return;
    for (;;) {
        ssize_t got = read(fd, buf, sizeof buf);
        if (got <= 0) break;
        (void)!write(2, buf, (size_t)got);
    }
    close(fd);
    unlink("/probe/accounts-probe.log");
}

static int count_logged_calls(void)
{
    char buf[1024];
    int fd = open("/probe/accounts-probe.log", O_RDONLY);
    int calls = 0;
    if (fd < 0) return 0;
    ssize_t got = read(fd, buf, sizeof buf - 1);
    close(fd);
    if (got <= 0) return 0;
    buf[got] = '\0';
    for (char *p = buf; (p = strstr(p, "call=")) != NULL; p += 5) calls++;
    return calls;
}

static ssize_t read_whole(const char *path, char *buf, size_t cap)
{
    int fd = open(path, O_RDONLY);
    if (fd < 0) return -1;
    size_t total = 0;
    while (total < cap) {
        ssize_t got = read(fd, buf + total, cap - total);
        if (got < 0) {
            close(fd);
            return -1;
        }
        if (got == 0) break;
        total += (size_t)got;
    }
    close(fd);
    return (ssize_t)total;
}

static int run_accounts_add_once(void)
{
    pid_t pid = fork();
    if (pid < 0) return -1;
    if (pid == 0) {
        int in_fd = open("/probe/accounts-probe-in", O_RDONLY);
        int err_fd = open("/probe/accounts-probe-err", O_WRONLY | O_CREAT | O_TRUNC, 0666);
        if (in_fd < 0 || err_fd < 0) _exit(126);
        if (dup2(in_fd, 0) < 0 || dup2(err_fd, 1) < 0 || dup2(err_fd, 2) < 0) _exit(126);
        if (in_fd > 2) close(in_fd);
        if (err_fd > 2) close(err_fd);
        char *const args[] = {"accounts", "add", "ivy", "child", "net", NULL};
        char *const env[] = {NULL};
        execve("/bin/accounts", args, env);
        _exit(126);
    }
    int status = 0;
    if (waitpid(pid, &status, 0) < 0) return -1;
    return WIFEXITED(status) ? WEXITSTATUS(status) : -1;
}

static int check_fail_start(void)
{
    char before[4096], after[4096];
    ssize_t before_n = read_whole("/home/.daphnis/accounts", before, sizeof before);
    if (before_n <= 0) return 1;

    int in_fd = open("/probe/accounts-probe-in", O_WRONLY | O_CREAT | O_TRUNC, 0666);
    if (in_fd < 0) return 1;
    const char pass_in[] = "ivy-pass\nivy-pass\n";
    if (write(in_fd, pass_in, sizeof pass_in - 1) != (ssize_t)(sizeof pass_in - 1)) {
        close(in_fd);
        unlink("/probe/accounts-probe-in");
        return 1;
    }
    close(in_fd);

    int pipes[32][2];
    int npipes = 0;
    while (npipes < 32 && pipe(pipes[npipes]) == 0) {
        fcntl(pipes[npipes][0], F_SETFD, FD_CLOEXEC);
        fcntl(pipes[npipes][1], F_SETFD, FD_CLOEXEC);
        npipes++;
    }
    int pin_rc = (npipes > 0) ? run_accounts_add_once() : -1;

    int pout_rc = -1;
    if (npipes > 0) {
        npipes--;
        close(pipes[npipes][0]);
        close(pipes[npipes][1]);
        pout_rc = run_accounts_add_once();
    }
    for (int i = 0; i < npipes; i++) {
        close(pipes[i][0]);
        close(pipes[i][1]);
    }

    int probe_pipe[2];
    int pipe_leak = 1;
    if (pipe(probe_pipe) == 0) {
        close(probe_pipe[0]);
        close(probe_pipe[1]);
        pipe_leak = 0;
    }

    int fail_fd = open("/probe/accounts-probe-fail", O_WRONLY | O_CREAT | O_TRUNC, 0666);
    if (fail_fd >= 0) close(fail_fd);
    int child_rc = run_accounts_add_once();
    unlink("/probe/accounts-probe-fail");
    unlink("/probe/accounts-probe-in");
    unlink("/probe/accounts-probe-err");

    ssize_t after_n = read_whole("/home/.daphnis/accounts", after, sizeof after);
    int store_unchanged = (after_n == before_n && memcmp(before, after, (size_t)before_n) == 0) ? 1 : 0;

    char line[256];
    int len = snprintf(
        line, sizeof line,
        "accounts-probe: fail_start pin_rc=%d pout_rc=%d child_rc=%d pipe_leak=%d store_unchanged=%d\n",
        pin_rc, pout_rc, child_rc, pipe_leak, store_unchanged);
    if (len > 0 && (size_t)len < sizeof line) append_log(line, (size_t)len);

    return (pin_rc == 1 && pout_rc == 1 && child_rc == 1 && pipe_leak == 0 && store_unchanged == 1) ? 0 : 1;
}

int main(int argc, char **argv, char **envp)
{
    umask(0);   /* FS-2: the probe's files are shared between the account and uid 0 */
    if (argc >= 2 && strcmp(argv[1], "--check-fail-start") == 0) {
        return check_fail_start();
    }
    if (unlink("/probe/accounts-probe-fail") == 0) {
        _exit(127);
    }

    int uid = (int)getuid();
    if (uid == 0) {
        drain_log_to_serial();
        execve("/bin/authd-real", argv, envp);
        _exit(127);
    }

    int call = count_logged_calls() + 1;
    errno = 0;
    int disk_fd = open("/home/accounts-helper-disk.txt", O_WRONLY | O_CREAT | O_TRUNC, 0600);
    int disk_err = disk_fd < 0 ? errno : 0;
    if (disk_fd >= 0) {
        close(disk_fd);
        unlink("/home/accounts-helper-disk.txt");
    }

    errno = 0;
    int kern_fd = open("/home/.daphnis/accounts-helper-kern.txt", O_WRONLY | O_CREAT | O_TRUNC, 0600);
    int kern_err = kern_fd < 0 ? errno : 0;
    if (kern_fd >= 0) {
        close(kern_fd);
        unlink("/home/.daphnis/accounts-helper-kern.txt");
    }

    long kern_held = syscall(1001, 0UL, 0UL);

    char line[256];
    int len = snprintf(
        line, sizeof line,
        "accounts-probe: call=%d uid=%d disk_open=%d disk_errno=%d kern_open=%d kern_errno=%d kern_held=%ld\n",
        call, uid, disk_fd, disk_err, kern_fd, kern_err, kern_held);
    if (len > 0 && (size_t)len < sizeof line) {
        append_log(line, (size_t)len);
        (void)!write(2, line, (size_t)len);
    }

    execve("/bin/authd-real", argv, envp);
    _exit(127);
}
