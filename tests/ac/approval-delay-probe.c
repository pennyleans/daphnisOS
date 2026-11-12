#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#define SYS_DAPHNIS_KERN 1001
#define SYS_DAPHNIS_GRANT_ASK 1004
#define GRANT_NET 2UL

#define LOG_PATH "/probe/approval-probe.log"
#define DRAIN_PATH "/probe/approval-probe.draining"
#define DRAINER_PID_PATH "/probe/approval-drainer.pid"
#define WAKE_DRAIN_PATH "/probe/wake-drain"
#define WAKE_FLOW_PATH "/probe/wake-flow"
#define WAKE_HOLD_PATH "/probe/wake-hold"
#define WAKE_SURVIVE_PATH "/probe/wake-survive"
#define EXIT_ON_HOLD_PID_PATH "/probe/exit-on-hold.pid"
#define HOLD_PATH "/probe/approval-hold"
#define HOLDING_PATH "/probe/approval-holding"
#define SEQ_PATH "/probe/approval-seq"
#define TOTAL_SEQ_PATH "/probe/auth-total-seq"

static long long now_ms(void)
{
    struct timespec ts;
    if (clock_gettime(CLOCK_BOOTTIME, &ts) < 0) return 0;
    return (long long)ts.tv_sec * 1000LL + (long long)(ts.tv_nsec / 1000000L);
}

static void sleep_ms(int ms)
{
    long long end;
    if (ms <= 0) return;
    end = now_ms() + (long long)ms;
    while (now_ms() < end) {
        for (volatile int k = 0; k < 200000; k++) {}
    }
}

static void write_all(int fd, const void *buf, size_t n)
{
    const char *p = (const char *)buf;
    size_t off = 0;
    while (off < n) {
        ssize_t w = write(fd, p + off, n - off);
        if (w < 0) {
            if (errno == EINTR) continue;
            break;
        }
        off += (size_t)w;
    }
}

static void write_file_str(const char *path, const char *s)
{
    int fd = open(path, O_WRONLY | O_CREAT | O_TRUNC, 0666);
    if (fd < 0) return;
    write_all(fd, s, strlen(s));
    close(fd);
}

static int read_file_str(const char *path, char *buf, size_t cap)
{
    int fd = open(path, O_RDONLY);
    ssize_t r;
    if (fd < 0) return -1;
    r = read(fd, buf, cap - 1);
    close(fd);
    if (r < 0) return -1;
    buf[r] = '\0';
    return (int)r;
}

static int read_int_file(const char *path)
{
    char buf[64];
    if (read_file_str(path, buf, sizeof buf) < 0) return 0;
    return atoi(buf);
}

static int bump_int_file(const char *path)
{
    char buf[64];
    int v = read_int_file(path) + 1;
    snprintf(buf, sizeof buf, "%d\n", v);
    write_file_str(path, buf);
    return v;
}

static void wake_waiter(const char *wake_path)
{
    int wpid = read_int_file(wake_path);
    if (wpid > 1) {
        unlink(wake_path);
        kill((pid_t)wpid, SIGKILL);
    }
}

static void wait_for_file_state(const char *target_path, const char *wake_path, int want_exist)
{
    if (getuid() == 0) {
        while ((access(target_path, F_OK) == 0) != want_exist) { sleep_ms(20); }
        return;
    }
    for (;;) {
        int have = (access(target_path, F_OK) == 0) ? 1 : 0;
        int pfd[2];
        pid_t cpid;
        int st = 0;
        char buf[32];

        if (have == want_exist) return;
        if (pipe(pfd) < 0) {
            sleep_ms(50);
            continue;
        }
        cpid = fork();
        if (cpid < 0) {
            close(pfd[0]);
            close(pfd[1]);
            sleep_ms(50);
            continue;
        }
        if (cpid == 0) {
            char dummy;
            close(pfd[1]);
            while (read(pfd[0], &dummy, 1) > 0) {}
            _exit(0);
        }
        close(pfd[0]);
        snprintf(buf, sizeof buf, "%d\n", (int)cpid);
        write_file_str(wake_path, buf);

        have = (access(target_path, F_OK) == 0) ? 1 : 0;
        if (have == want_exist) {
            unlink(wake_path);
            kill(cpid, SIGKILL);
        }
        while (waitpid(cpid, &st, 0) < 0 && errno == EINTR) {}
        close(pfd[1]);
    }
}

static void append_file(const char *path, const char *fmt, ...)
{
    char buf[512];
    va_list ap;
    int n, fd;
    va_start(ap, fmt);
    n = vsnprintf(buf, sizeof buf, fmt, ap);
    va_end(ap);
    if (n <= 0) return;
    if ((size_t)n >= sizeof buf) n = (int)(sizeof buf - 1);
    fd = open(path, O_WRONLY | O_CREAT | O_APPEND, 0666);
    if (fd < 0) return;
    write_all(fd, buf, (size_t)n);
    close(fd);
}

static void append_log(const char *fmt, ...)
{
    char buf[512];
    va_list ap;
    int n, fd;
    va_start(ap, fmt);
    n = vsnprintf(buf, sizeof buf, fmt, ap);
    va_end(ap);
    if (n <= 0) return;
    if ((size_t)n >= sizeof buf) n = (int)(sizeof buf - 1);
    fd = open(LOG_PATH, O_WRONLY | O_CREAT | O_APPEND, 0666);
    if (fd >= 0) {
        write_all(fd, buf, (size_t)n);
        close(fd);
    }
    wake_waiter(WAKE_DRAIN_PATH);
}

static void drain_log_to_serial(void)
{
    char buf[512];
    int fd;
    ssize_t r;
    while (rename(LOG_PATH, DRAIN_PATH) == 0) {
        fd = open(DRAIN_PATH, O_RDONLY);
        if (fd >= 0) {
            while ((r = read(fd, buf, sizeof buf)) > 0) {
                write_all(2, buf, (size_t)r);
            }
            close(fd);
        }
        unlink(DRAIN_PATH);
    }
}

static void ensure_log_drainer(void)
{
    int dpid = read_int_file(DRAINER_PID_PATH);
    pid_t pid;
    char buf[32];
    if (dpid > 1 && kill((pid_t)dpid, 0) == 0) return;
    pid = fork();
    if (pid < 0) return;
    if (pid == 0) {
        signal(SIGTERM, SIG_IGN);
        close(0);
        close(1);
        snprintf(buf, sizeof buf, "%d\n", (int)getpid());
        write_file_str(DRAINER_PID_PATH, buf);
        for (;;) {
            drain_log_to_serial();
            wait_for_file_state(LOG_PATH, WAKE_DRAIN_PATH, 1);
        }
    }
}

static void release_hold(void)
{
    unlink(HOLDING_PATH);
    wake_waiter(WAKE_HOLD_PATH);
    wake_waiter(WAKE_SURVIVE_PATH);
    wake_waiter(WAKE_FLOW_PATH);
}

static void parse_hold_spec(const char *spec, int *skip_out, int *ms_out)
{
    const char *p;
    *skip_out = 0;
    *ms_out = 0;
    p = strstr(spec, "skip=");
    if (p) *skip_out = atoi(p + 5);
    p = strstr(spec, "ms=");
    if (p) {
        *ms_out = atoi(p + 3);
    }
}

static int run_authd_wrapper(void)
{
    unsigned char req[512];
    unsigned char ans[256];
    size_t req_len = 0;
    size_t ans_len = 0;
    int pin[2], pout[2];
    pid_t pid;
    int st = 0;
    char hold_spec[128];
    int has_hold = 0;
    int skip = 0, hold_ms = 0;

    dprintf(2, "approval-probe: wrapper start uid=%u\n", (unsigned)getuid());
    ensure_log_drainer();
    drain_log_to_serial();

    while (req_len < sizeof req) {
        ssize_t r = read(0, req + req_len, sizeof req - req_len);
        if (r < 0) {
            if (errno == EINTR) continue;
            break;
        }
        if (r == 0) break;
        req_len += (size_t)r;
    }

    dprintf(2, "approval-probe: request read\n");
    if (pipe(pin) < 0) return 1;
    if (pipe(pout) < 0) {
        close(pin[0]);
        close(pin[1]);
        return 1;
    }

    pid = fork();
    if (pid < 0) return 1;
    if (pid == 0) {
        char *argv_real[2] = {"authd", NULL};
        char *envp_real[1] = {NULL};
        if (dup2(pin[0], 0) < 0 || dup2(pout[1], 1) < 0) _exit(127);
        close(pin[0]);
        close(pin[1]);
        close(pout[0]);
        close(pout[1]);
        execve("/bin/authd-real", argv_real, envp_real);
        _exit(127);
    }
    dprintf(2, "approval-probe: real forked pid=%d\n", (int)pid);
    close(pin[0]);
    close(pout[1]);
    write_all(pin[1], req, req_len);
    close(pin[1]);

    while (ans_len < sizeof ans) {
        ssize_t r = read(pout[0], ans + ans_len, sizeof ans - ans_len);
        if (r < 0) {
            if (errno == EINTR) continue;
            break;
        }
        if (r == 0) break;
        ans_len += (size_t)r;
    }
    close(pout[0]);
    while (waitpid(pid, &st, 0) < 0 && errno == EINTR) {}

    dprintf(2, "approval-probe: real complete status=%d bytes=%u\n", st, (unsigned)ans_len);
    if (req_len >= 7 && memcmp(req, "verify ", 7) == 0 &&
        read_file_str(HOLD_PATH, hold_spec, sizeof hold_spec) >= 0) {
        parse_hold_spec(hold_spec, &skip, &hold_ms);
        if (skip > 0) {
            char next_spec[128];
            snprintf(next_spec, sizeof next_spec, "skip=%d ms=%d\n", skip - 1, hold_ms);
            write_file_str(HOLD_PATH, next_spec);
        } else {
            unlink(HOLD_PATH);
            has_hold = 1;
        }
    }
    memset(req, 0, sizeof req);

    if (has_hold) {
        int seq = bump_int_file(SEQ_PATH);
        const char *verdict = (ans_len >= 3 && memcmp(ans, "ok\n", 3) == 0) ? "ok" : "no";
        char msg[128];
        int exit_pid;

        snprintf(msg, sizeof msg, "%d %s\n", seq, verdict);
        write_file_str(HOLDING_PATH, msg);
        wake_waiter(WAKE_FLOW_PATH);

        drain_log_to_serial();
        snprintf(msg, sizeof msg, "approval-probe: held seq=%d verdict=%s\n", seq, verdict);
        write_all(2, msg, strlen(msg));

        exit_pid = read_int_file(EXIT_ON_HOLD_PID_PATH);
        if (exit_pid > 1) {
            unlink(EXIT_ON_HOLD_PID_PATH);
            kill((pid_t)exit_pid, SIGTERM);
        }

        if (hold_ms <= 0) {
            wait_for_file_state(HOLDING_PATH, WAKE_HOLD_PATH, 0);
        } else {
            long long deadline = now_ms() + (long long)hold_ms;
            while (now_ms() < deadline && access(HOLDING_PATH, F_OK) == 0) {
                sleep_ms(20);
            }
        }
        release_hold();
        drain_log_to_serial();
        snprintf(msg, sizeof msg, "approval-probe: release seq=%d verdict=%s\n", seq, verdict);
        write_all(2, msg, strlen(msg));
    }

    bump_int_file(TOTAL_SEQ_PATH);
    wake_waiter(WAKE_FLOW_PATH);
    drain_log_to_serial();

    write_all(1, ans, ans_len);
    return 0;
}

static void record_req_result(const char *tag, pid_t pid, uid_t uid, int ask_rc, int ask_errno,
                              int auth_ok, int auth_errno, int kern_held, int kern_open, int exited_sig)
{
    char done_path[128];
    snprintf(done_path, sizeof done_path, "/probe/req-done-%s", tag);
    append_file(done_path, "auth_ok=%d ask_rc=%d exited_sig=%d\n", auth_ok, ask_rc, exited_sig);
    append_log("approval-probe: req tag=%s pid=%d uid=%u ask_rc=%d ask_errno=%d "
               "auth_ok=%d auth_errno=%d kern_held=%d kern_open=%d exited_sig=%d\n",
               tag, (int)pid, (unsigned)uid, ask_rc, ask_errno,
               auth_ok, auth_errno, kern_held, kern_open, exited_sig);
    wake_waiter(WAKE_FLOW_PATH);
}

static int run_req_child(const char *tag, const char *kind, const char *mode)
{
    pid_t me = getpid();
    uid_t uid = getuid();
    int is_kern = strcmp(kind, "kern") == 0;
    int do_release = strcmp(mode, "release") == 0;
    int release_after_ask = strcmp(mode, "release_after_ask") == 0;
    int exit_on_hold = strcmp(mode, "exit_on_hold") == 0;
    int survive_logout = strcmp(mode, "survive_logout") == 0;
    long rc;
    int ask_errno = 0;
    int auth_ok = 0;
    int auth_errno = 0;
    int kh = 0;
    int ko = -1;

    if (do_release || survive_logout) {
        signal(SIGTERM, SIG_IGN);
    }

    if (exit_on_hold) {
        char buf[32];
        snprintf(buf, sizeof buf, "%d\n", (int)me);
        write_file_str(EXIT_ON_HOLD_PID_PATH, buf);
    }

    if (release_after_ask) {
        pid_t rpid = fork();
        if (rpid == 0) {
            close(0);
            close(1);
            close(2);
            append_log("approval-probe: release controller started\n");
            sleep_ms(120);
            append_log("approval-probe: release controller ready\n");
            release_hold();
            _exit(0);
        }
    }

    if (survive_logout) {
        pid_t wpid = fork();
        if (wpid == 0) {
            close(0);
            close(1);
            close(2);
            wait_for_file_state(HOLDING_PATH, WAKE_SURVIVE_PATH, 1);
            wait_for_file_state(HOLDING_PATH, WAKE_SURVIVE_PATH, 0);
            sleep_ms(300);
            if (kill(me, 0) == 0) {
                record_req_result(tag, me, uid, -1, ECANCELED, -1, EINPROGRESS, 0, -1, 9);
                kill(me, SIGKILL);
            }
            _exit(0);
        }
    }

    char started[128];
    snprintf(started, sizeof started, "/probe/req-start-%s", tag);
    write_file_str(started, "1");
    wake_waiter(WAKE_FLOW_PATH);
    errno = 0;
    if (is_kern) {
        rc = syscall(SYS_DAPHNIS_KERN, tag, (unsigned long)strlen(tag));
    } else {
        rc = syscall(SYS_DAPHNIS_GRANT_ASK, tag, (unsigned long)strlen(tag), GRANT_NET);
    }
    if (rc < 0) ask_errno = errno;

    kh = (int)syscall(SYS_DAPHNIS_KERN, 0UL, 0UL);
    ko = open("/home/.daphnis/accounts", O_RDONLY);
    if (ko >= 0) close(ko);

    if (is_kern) {
        errno = 0;
        ko = open("/home/.daphnis/accounts", O_RDONLY);
        if (ko >= 0) {
            auth_ok = 1;
            auth_errno = 0;
            close(ko);
        } else {
            auth_ok = 0;
            auth_errno = errno;
        }
    } else {
        int s;
        errno = 0;
        s = socket(AF_INET, SOCK_DGRAM, 0);
        if (s >= 0) {
            auth_ok = 1;
            auth_errno = 0;
            close(s);
        } else {
            auth_ok = 0;
            auth_errno = errno;
        }
    }

    record_req_result(tag, me, uid, (int)rc, ask_errno, auth_ok, auth_errno, kh, ko, 0);

    if (do_release) {
        sleep_ms(120);
        release_hold();
    }
    return 0;
}

static pid_t spawn_req_on_current_pty(const char *tag, const char *kind, const char *mode)
{
    char done_path[128];
    pid_t pid;
    snprintf(done_path, sizeof done_path, "/probe/req-done-%s", tag);
    unlink(done_path);
    pid = fork();
    if (pid == 0) {
        char *argv_req[6];
        char *envp_req[2] = {"PATH=/bin", NULL};
        argv_req[0] = "authd";
        argv_req[1] = "--req-child";
        argv_req[2] = (char *)tag;
        argv_req[3] = (char *)kind;
        argv_req[4] = (char *)mode;
        argv_req[5] = NULL;
        execve("/bin/authd", argv_req, envp_req);
        _exit(127);
    }
    return pid;
}

static int run_worker(int win)
{
    char ready_path[64], cmd_path[64], run_path[64], wake_path[64];
    pid_t active_pid = -1;

    snprintf(ready_path, sizeof ready_path, "/probe/ready-w%d", win);
    snprintf(cmd_path, sizeof cmd_path, "/probe/cmd-w%d", win);
    snprintf(run_path, sizeof run_path, "/probe/run-w%d", win);
    snprintf(wake_path, sizeof wake_path, "/probe/wake-w%d", win);

    write_file_str(ready_path, "1\n");
    append_log("approval-probe: worker win=%d pid=%d uid=%u ready\n",
               win, (int)getpid(), (unsigned)getuid());
    wake_waiter(WAKE_FLOW_PATH);

    for (;;) {
        char line[256];
        wait_for_file_state(cmd_path, wake_path, 1);
        if (active_pid > 0) {
            int st = 0;
            pid_t w = waitpid(active_pid, &st, WNOHANG);
            if (w == active_pid || (w < 0 && errno == ECHILD)) {
                active_pid = -1;
            }
        }
        if (rename(cmd_path, run_path) == 0) {
            if (read_file_str(run_path, line, sizeof line) >= 0) {
                char op[64] = {0}, a1[64] = {0}, a2[64] = {0}, a3[64] = {0};
                unlink(run_path);
                sscanf(line, "%63s %63s %63s %63s", op, a1, a2, a3);
                if (strcmp(op, "req") == 0) {
                    if (active_pid > 0) {
                        int st = 0;
                        while (waitpid(active_pid, &st, 0) < 0 && errno == EINTR) {}
                    }
                    active_pid = spawn_req_on_current_pty(a1, a2, a3[0] ? a3 : "none");
                } else if (strcmp(op, "chain") == 0) {
                    int st1 = 0, st2 = 0;
                    pid_t c1, c2;
                    int kh_mid, ko_mid, kh_end, ko_end;
                    if (active_pid > 0) {
                        while (waitpid(active_pid, &st1, 0) < 0 && errno == EINTR) {}
                        active_pid = -1;
                    }
                    c1 = spawn_req_on_current_pty(a1, "kern", "exit_on_hold");
                    while (waitpid(c1, &st1, 0) < 0 && errno == EINTR) {}
                    kh_mid = (int)syscall(SYS_DAPHNIS_KERN, 0UL, 0UL);
                    ko_mid = open("/home/.daphnis/accounts", O_RDONLY);
                    if (ko_mid >= 0) close(ko_mid);
                    record_req_result(a1, c1, getuid(), -1, EINTR, 0, EACCES, kh_mid, ko_mid,
                                      WIFSIGNALED(st1) ? WTERMSIG(st1) : 0);

                    c2 = spawn_req_on_current_pty(a2, "net", "none");
                    while (waitpid(c2, &st2, 0) < 0 && errno == EINTR) {}
                    kh_end = (int)syscall(SYS_DAPHNIS_KERN, 0UL, 0UL);
                    ko_end = open("/home/.daphnis/accounts", O_RDONLY);
                    if (ko_end >= 0) close(ko_end);
                    append_log("approval-probe: chain_shell win=%d pid=%d w2_kern_held=%d w2_kern_open=%d\n",
                               win, (int)getpid(), kh_end, ko_end);
                    wake_waiter(WAKE_FLOW_PATH);
                }
            } else {
                unlink(run_path);
            }
        }
    }
    return 0;
}

static void send_worker_cmd(int win, const char *cmd)
{
    char tmp_path[64], cmd_path[64], wake_path[64];
    snprintf(tmp_path, sizeof tmp_path, "/probe/tmp-w%d", win);
    snprintf(cmd_path, sizeof cmd_path, "/probe/cmd-w%d", win);
    snprintf(wake_path, sizeof wake_path, "/probe/wake-w%d", win);
    write_file_str(tmp_path, cmd);
    rename(tmp_path, cmd_path);
    wake_waiter(wake_path);
}

static int run_flow(void)
{
    pid_t pid_a, pid_lock;
    int st = 0;
    int t0;
    char lock_done_buf[128];

    wait_for_file_state("/probe/ready-w1", WAKE_FLOW_PATH, 1);
    wait_for_file_state("/probe/ready-w2", WAKE_FLOW_PATH, 1);
    append_log("approval-probe: flow_start w0_pid=%d\n", (int)getpid());

    /* Phase 1: req_a in window 0, req_b queued in window 1; req_a canceled while valid auth held. */
    write_file_str(HOLD_PATH, "skip=0 ms=0\n");
    pid_a = spawn_req_on_current_pty("req_a", "net", "release");
    sleep_ms(150);
    send_worker_cmd(1, "req req_b net release\n");

    while (waitpid(pid_a, &st, 0) < 0 && errno == EINTR) {}
    wait_for_file_state(HOLDING_PATH, WAKE_FLOW_PATH, 0);
    sleep_ms(200);

    /* Phase 2: on unpatched hdesk, req_a's held ok already approved req_b; if so, start req_b2 in window 1. */
    if (access("/probe/req-done-req_b", F_OK) == 0) {
        append_log("approval-probe: note req_b_stale_approved=1\n");
        send_worker_cmd(1, "req req_b2 net release\n");
        sleep_ms(150);
    } else {
        append_log("approval-probe: note req_b_stale_approved=0\n");
    }
    write_file_str(HOLD_PATH, "skip=3 ms=0\n");
    send_worker_cmd(2, "req req_c net none\n");
    wait_for_file_state("/probe/req-done-req_c", WAKE_FLOW_PATH, 1);
    sleep_ms(150);

    /* Phase 3: requester exits while valid auth held + subsequent request from same window 2. */
    write_file_str(HOLD_PATH, "skip=0 ms=1500\n");
    send_worker_cmd(2, "chain req_exit1 req_exit2\n");
    wait_for_file_state("/probe/req-done-req_exit2", WAKE_FLOW_PATH, 1);
    sleep_ms(150);

    /* Phase 4: lock (Super+L) while valid auth held for req_lock in window 0. */
    t0 = read_int_file(TOTAL_SEQ_PATH);
    write_file_str(HOLD_PATH, "skip=0 ms=1500\n");
    pid_lock = spawn_req_on_current_pty("req_lock", "net", "release");
    while (waitpid(pid_lock, &st, 0) < 0 && errno == EINTR) {}
    wait_for_file_state(HOLDING_PATH, WAKE_FLOW_PATH, 0);
    if (read_file_str("/probe/req-done-req_lock", lock_done_buf, sizeof lock_done_buf) >= 0 &&
        strstr(lock_done_buf, "auth_ok=0") != NULL) {
        while (read_int_file(TOTAL_SEQ_PATH) < t0 + 2) {
            int pfd[2];
            pid_t cpid;
            int wst = 0;
            char b[32];
            if (pipe(pfd) < 0) break;
            cpid = fork();
            if (cpid == 0) {
                char d;
                close(pfd[1]);
                while (read(pfd[0], &d, 1) > 0) {}
                _exit(0);
            }
            close(pfd[0]);
            snprintf(b, sizeof b, "%d\n", (int)cpid);
            write_file_str(WAKE_FLOW_PATH, b);
            if (read_int_file(TOTAL_SEQ_PATH) >= t0 + 2) {
                unlink(WAKE_FLOW_PATH);
                kill(cpid, SIGKILL);
            }
            while (waitpid(cpid, &wst, 0) < 0 && errno == EINTR) {}
            close(pfd[1]);
        }
    }
    sleep_ms(200);

    /* Phase 5: logout while valid auth held for req_logout1 (with req_logout2 queued behind it). */
    write_file_str(HOLD_PATH, "skip=0 ms=0\n");
    send_worker_cmd(2, "req req_logout1 net release\n");
    wait_for_file_state(HOLDING_PATH, WAKE_FLOW_PATH, 1);
    send_worker_cmd(1, "req req_logout2 net survive_logout\n");
    wait_for_file_state("/probe/req-start-req_logout2", WAKE_FLOW_PATH, 1);
    sleep_ms(80);
    append_log("approval-probe: flow_exit_w0 pid=%d\n", (int)getpid());
    return 0;
}

static int run_timeout_flow(void)
{
    pid_t pid_t;
    int st = 0;

    write_file_str(HOLD_PATH, "skip=0 ms=123000\n");
    pid_t = spawn_req_on_current_pty("req_timeout", "net", "none");
    while (waitpid(pid_t, &st, 0) < 0 && errno == EINTR) {}
    wait_for_file_state(HOLDING_PATH, WAKE_FLOW_PATH, 0);
    sleep_ms(200);
    return 0;
}

/* PR 225 P1: run with `exec` in the session's first terminal, so this process is its first shell. The next
 * verify (the unlock) is held; once it is held this process ends, the desk logs out, and the held "ok" arrives
 * after the log out. */
static int run_unlock_race(void)
{
    write_file_str(HOLD_PATH, "skip=0 ms=8000\n");
    append_log("approval-probe: unlock_race armed pid=%d uid=%u\n", (int)getpid(), (unsigned)getuid());
    wait_for_file_state(HOLDING_PATH, WAKE_FLOW_PATH, 1);
    return 0;   /* no line here: it would cross the desk's "hdesk: logout" on the serial line */
}

/* Who a shell runs as: typed into a terminal the desk opened. */
static int run_whoami(void)
{
    append_log("approval-probe: whoami uid=%u pid=%d\n", (unsigned)getuid(), (int)getpid());
    return 0;
}

int main(int argc, char **argv)
{
    umask(0);   /* FS-2: the probe's files under /probe are shared between sam and authd's wrapper */
    if (argc == 1) {
        return run_authd_wrapper();
    }
    if (argc >= 3 && strcmp(argv[1], "--worker") == 0) {
        return run_worker(atoi(argv[2]));
    }
    if (argc >= 5 && strcmp(argv[1], "--req-child") == 0) {
        return run_req_child(argv[2], argv[3], argv[4]);
    }
    if (argc >= 2 && strcmp(argv[1], "--run-flow") == 0) {
        return run_flow();
    }
    if (argc >= 2 && strcmp(argv[1], "--run-timeout") == 0) {
        return run_timeout_flow();
    }
    if (argc >= 2 && strcmp(argv[1], "--run-unlock") == 0) {
        return run_unlock_race();
    }
    if (argc >= 2 && strcmp(argv[1], "--whoami") == 0) {
        return run_whoami();
    }
    return 1;
}
