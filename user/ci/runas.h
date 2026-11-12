/* user/ci/runas.h: the desk's runs as the account (2026-11-11, gap 3 of the Settings wiring;
 * RS-SET6, U-SET section 3, AC-R2). The desk is uid 0 and opens nothing in a home with its own rights, so what the
 * Settings pages need from a home runs as the account that owns it:
 *   RUN_DU           du -k -s HOME/Documents HOME/Downloads HOME/Pictures HOME/.trash HOME (the Storage page; du
 *                    counts a directory once, so each part is its own line and HOME's is the rest; a part the home
 *                    lacks, as the account sees it, is left out);
 *   RUN_TRASH_COUNT  finder --trash-count (the Trash's entries);
 *   RUN_TRASH_EMPTY  finder --trash-empty (Empty Trash, after frame 23's ask);
 *   RUN_SET          setkey KEY VALUE (an account's setting, U-SET's file, written by the account's own process);
 *   RUN_PICTURE      bgread PATH W H (BG-1: the account's background picture, read and fitted as the account; the
 *                    desk never opens it);
 *   RUN_PEEK         finder --peek PATH (RG-1: a path Index or the plane opens that the desk cannot stat, such as a
 *                    file in a 0700 home: whether it is a folder, and a file's first 512 bytes, read as the account;
 *                    the program that opens it then runs in a terminal of the session, as the account);
 *   RUN_PREFS        setkey --print (RG-1: the account's own settings, U-SET's file in its 0700 home, which the desk
 *                    cannot open: the file's text as the account's process reads it, at most 8192 bytes).
 * The rules:
 * - A job is a number in this fixed table: its program and its argument vector are the table's, built from the
 *   session's home; only RUN_SET takes words of the caller's (a key and a value, each checked, each one argv word),
 *   RUN_PICTURE (the picture's path, absolute, the settings value as one argv word, and the screen's size, each
 *   side 1 to 3840, its area at most 3840 x 2160, portrait too) and RUN_PEEK (the path, absolute, one argv word,
 *   at most 4096 bytes with no NUL). No shell, no command line joined from bytes.
 * - The account is the session's own login record, which the desk gives once with run_session(uid, gid, ceil,
 *   home) when the session starts and clears with uid -1 when it ends. run_start takes no uid: it runs as that
 *   record or not at all. uid 0 (the desk's own) is refused, as is a run with no record.
 * - The child: stdin /dev/null, stdout a pipe, stderr /dev/null, every other descriptor closed; then Daphnis's
 *   login (call 1003) with the record's uid, gid and ceiling (status 126 if refused), a chdir to the home (126 if it
 *   fails: no fallback), and execve with a fixed environment: HOME (the record's), PATH=/bin, LANG=C.UTF-8.
 * - The desk reads the pipe without blocking (run_poll). Past the job's cap (RUN_CAP; RUN_PICTURE's exactly its
 *   header and W x H pixels) or its time (RUN_TIMEOUT_MS since the start; RUN_PICTURE's RUN_PICTURE_MS with no byte
 *   arriving, and the whole run at twice a Daphnis pipe's least rate, 4 KiB a 10 ms tick), the child is killed and
 *   reaped and the run answers -E2BIG or -ETIMEDOUT. A run that ends answers RUN_END - status once the pipe is
 *   drained and the child reaped. run_stop kills and reaps whatever runs. One run at a time; no path is left with a
 *   child unreaped.
 * - The desk never opens a path that the child's output names: the output is data (kit/homeuse.ci's numbers).
 * user/ci/host.c's run rows include this header as it is; tests/hosted/runas_test.c includes it with RUN_LOGIN,
 * RUN_PROGRAM and the limits of its own. */
#ifndef DAPH_RUNAS_H
#define DAPH_RUNAS_H

#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <string.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#ifndef RUN_LOGIN
#include <sys/syscall.h>
#define RUN_LOGIN(uid, gid, ceil) syscall(1003, (long)(uid), (long)(gid), (long)(ceil))   /* AC-1a */
#endif
#ifndef RUN_CHDIR
#define RUN_CHDIR(path) chdir(path)
#endif
#ifndef RUN_CAP
#define RUN_CAP 16384                  /* the bytes a run may write in all */
#endif
#ifndef RUN_TIMEOUT_MS
#define RUN_TIMEOUT_MS 30000
#endif
#ifndef RUN_PICTURE_MS
#define RUN_PICTURE_MS 10000           /* RUN_PICTURE's time with no byte arriving */
#endif
#ifndef RUN_PIPE_RATE
#define RUN_PIPE_RATE 4096             /* the bytes a Daphnis pipe moves in RUN_PIPE_MS at the least (PIPE_BYTES) */
#endif
#ifndef RUN_PIPE_MS
#define RUN_PIPE_MS 10                 /* the desk's tick */
#endif
#define RUN_PIC_HEAD 8                 /* RUN_PICTURE's header: u32 width, u32 height, little-endian */
#define RUN_PIC_SIDE 3840              /* a side of the screen a picture is fitted to, at most */
#define RUN_PIC_AREA (3840L * 2160L)   /* and its area, at most: portrait screens too */
#define RUN_END (-4096)                /* RUN_END - status: the run ended with that exit status */
#define RUN_ARGS 4096                  /* the argument bytes a cint program's main.c holds: every word and its NUL */

#define RUN_DU 0
#define RUN_TRASH_COUNT 1
#define RUN_TRASH_EMPTY 2
#define RUN_SET 3
#define RUN_PICTURE 4
#define RUN_PEEK 5
#define RUN_PREFS 6
#define RUN_JOBS 7
#define RUN_PEEK_CAP 513               /* RUN_PEEK's answer: a kind byte (d or f) and a file's first 512 bytes */
#define RUN_PREFS_CAP 8192             /* RUN_PREFS's answer: the settings' text, kit/settings.ci SIZE at most */

#ifndef RUN_PROGRAM
static const char *const run_program[RUN_JOBS] = {"/bin/du", "/bin/finder", "/bin/finder", "/bin/setkey",
                                                  "/bin/bgread", "/bin/finder", "/bin/setkey"};
#define RUN_PROGRAM(job) run_program[job]
#endif

#define RUN_HOME 256
static long run_uid = -1;              /* the session's record; -1: none */
static long run_gid = -1;
static long run_ceil = 0;
static char run_home[RUN_HOME];
static pid_t run_pid = -1;             /* the child that runs, or -1 */
static int run_fd = -1;                /* its stdout's read end */
static long run_total = 0;             /* the bytes it wrote so far */
static long run_cap = RUN_CAP;         /* the bytes this run may write */
static long long run_limit = RUN_TIMEOUT_MS;   /* and its time, in ms: since the start, or since the last byte */
static long long run_total_ms = 0;     /* RUN_PICTURE's bound on the whole run, in ms; 0 for none */
static long long run_last = 0;         /* when its last byte came */
static long long run_t0 = 0;           /* when it started, in ms */

/* The machine's time in ms: CLOCK_BOOTTIME, the PIT on Daphnis (G-2). CLOCK_MONOTONIC there is the desk's virtual
 * clock, which moves 1 us a read, so a run's 30 s would take 30 million reads (the kernel read's sleep inventory). */
static long long run_now_ms(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_BOOTTIME, &ts);
    return (long long)ts.tv_sec * 1000 + ts.tv_nsec / 1000000;
}

/* The child killed (when kill) and reaped, the pipe closed; its exit status, or -1 when it did not exit. */
static int run_reap(int kill_it)
{
    int st = 0, code = -1;
    if (run_pid > 0) {
        if (kill_it) (void)kill(run_pid, SIGKILL);
        while (waitpid(run_pid, &st, 0) < 0 && errno == EINTR) {}
        if (WIFEXITED(st)) code = WEXITSTATUS(st);
    }
    if (run_fd >= 0) close(run_fd);
    run_pid = -1;
    run_fd = -1;
    run_total = 0;
    return code;
}

/* Kills and reaps whatever runs. */
static void run_stop(void) { if (run_pid > 0 || run_fd >= 0) (void)run_reap(1); }

/* The session's record: uid, gid, ceiling and home (hn bytes, "/home/NAME"). uid -1 clears it and stops any run.
 * 0, or -EPERM for uid 0 or a gid under 0, -EINVAL for a home that is not under /home, has a NUL or is too long. */
static int run_session(long uid, long gid, long ceil, const char *home, size_t hn)
{
    run_stop();
    run_uid = -1;
    run_gid = -1;
    run_ceil = 0;
    run_home[0] = '\0';
    if (uid < 0) return 0;
    if (uid == 0 || gid < 0) return -EPERM;
    if (hn < 7 || hn >= RUN_HOME || memcmp(home, "/home/", 6) != 0 || memchr(home, '\0', hn) != NULL) return -EINVAL;
    for (size_t i = 6; i < hn; i++) {
        if (home[i] == '/') return -EINVAL;   /* one name under /home: no deeper path, no ".." */
    }
    if ((hn == 7 && home[6] == '.') || (hn == 8 && home[6] == '.' && home[7] == '.')) return -EINVAL;
    memcpy(run_home, home, hn);
    run_home[hn] = '\0';
    run_uid = uid;
    run_gid = gid;
    run_ceil = ceil;
    return 0;
}

/* Whether a setting's key is U-SET's: 1 to 48 of a-z, 0-9, '.', '-' and '_', a letter first. */
static int run_key_ok(const char *k, size_t n)
{
    if (n < 1 || n > 48 || k[0] < 'a' || k[0] > 'z') return 0;
    for (size_t i = 0; i < n; i++) {
        char c = k[i];
        if (!((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '.' || c == '-' || c == '_')) return 0;
    }
    return 1;
}

/* A decimal of 1 to 4 digits, n bytes at s, from 1 to most; its value, or -1. */
static long run_dim(const char *s, size_t n, long most)
{
    long v = 0;
    if (n < 1 || n > 4 || s[0] == '0') return -1;
    for (size_t i = 0; i < n; i++) {
        if (s[i] < '0' || s[i] > '9') return -1;
        v = v * 10 + (s[i] - '0');
    }
    return v <= most ? v : -1;
}

/* Starts job (RUN_DU .. RUN_PREFS) as the session's account; arg is RUN_SET's "KEY\0VALUE", RUN_PICTURE's "PATH\0W\0H"
 * or RUN_PEEK's PATH (an's bytes), empty for the others. 0, or -errno: -EPERM with no record, -EINVAL for a job outside
 * the table or a bad argument, -EBUSY while a run goes on. */
static int run_start(int job, const char *arg, size_t an)
{
    char p0[RUN_HOME + 16], p1[RUN_HOME + 16], p2[RUN_HOME + 16], p3[RUN_HOME + 16], p4[RUN_HOME + 16];
    char key[49], val[4097], envh[RUN_HOME + 8], dw[5], dh[5];
    long cap = RUN_CAP;
    long long limit = RUN_TIMEOUT_MS;
    long long total = 0;
    char *argv[9];
    char *envp[4];
    int out[2], st = 0;
    pid_t pid;
    if (run_uid <= 0) return -EPERM;
    if (job < 0 || job >= RUN_JOBS) return -EINVAL;
    if (run_pid > 0 || run_fd >= 0) return -EBUSY;
    if (job == RUN_SET) {
        const char *z = memchr(arg, '\0', an);
        size_t kn, vn;
        if (z == NULL) return -EINVAL;
        kn = (size_t)(z - arg);
        vn = an - kn - 1;
        if (!run_key_ok(arg, kn) || vn > 4096 || memchr(z + 1, '\0', vn) != NULL) return -EINVAL;
        if (7 + kn + 1 + vn + 1 > RUN_ARGS) return -EINVAL;   /* "setkey", KEY, VALUE and their NULs */
        for (size_t i = 0; i < vn; i++) {
            if (z[1 + i] == '\n' || z[1 + i] == '\r') return -EINVAL;
        }
        memcpy(key, arg, kn);
        key[kn] = '\0';
        memcpy(val, z + 1, vn);
        val[vn] = '\0';
        argv[0] = "setkey";
        argv[1] = key;
        argv[2] = val;
        argv[3] = NULL;
    } else if (job == RUN_PICTURE) {   /* "PATH\0W\0H": an absolute path, the screen's width and height */
        const char *z1 = memchr(arg, '\0', an);
        const char *z2 = z1 == NULL ? NULL : memchr(z1 + 1, '\0', an - (size_t)(z1 + 1 - arg));
        size_t pn, wn, hn;
        long w, h;
        if (z1 == NULL || z2 == NULL) return -EINVAL;
        pn = (size_t)(z1 - arg);
        wn = (size_t)(z2 - z1 - 1);
        hn = an - (size_t)(z2 + 1 - arg);
        if (pn < 2 || pn > 4096 || arg[0] != '/' || memchr(z2 + 1, '\0', hn) != NULL) return -EINVAL;
        if (7 + pn + 1 + wn + 1 + hn + 1 > RUN_ARGS) return -EINVAL;   /* "bgread", PATH, W, H and their NULs */
        w = run_dim(z1 + 1, wn, RUN_PIC_SIDE);
        h = run_dim(z2 + 1, hn, RUN_PIC_SIDE);
        if (w < 0 || h < 0 || w * h > RUN_PIC_AREA) return -EINVAL;
        memcpy(val, arg, pn);
        val[pn] = '\0';
        memcpy(dw, z1 + 1, wn);
        dw[wn] = '\0';
        memcpy(dh, z2 + 1, hn);
        dh[hn] = '\0';
        argv[0] = "bgread";
        argv[1] = val;
        argv[2] = dw;
        argv[3] = dh;
        argv[4] = NULL;
        cap = RUN_PIC_HEAD + w * h * 4;
        limit = RUN_PICTURE_MS;        /* with no byte arriving; and the whole run at twice a pipe's least rate */
        total = 2LL * (cap / RUN_PIPE_RATE + 1) * RUN_PIPE_MS;
    } else if (job == RUN_PEEK) {      /* PATH: absolute, one word */
        if (an < 2 || an > 4096 || arg[0] != '/' || memchr(arg, '\0', an) != NULL) return -EINVAL;
        if (7 + 7 + an + 1 > RUN_ARGS) return -EINVAL;   /* "finder", "--peek", PATH and their NULs */
        memcpy(val, arg, an);
        val[an] = '\0';
        argv[0] = "finder";
        argv[1] = "--peek";
        argv[2] = val;
        argv[3] = NULL;
        cap = RUN_PEEK_CAP;
    } else if (an != 0) {
        return -EINVAL;
    } else if (job == RUN_PREFS) {
        argv[0] = "setkey";
        argv[1] = "--print";
        argv[2] = NULL;
        cap = RUN_PREFS_CAP;
    } else if (job == RUN_DU) {
        strcpy(p0, run_home);
        strcpy(p1, run_home); strcat(p1, "/Documents");
        strcpy(p2, run_home); strcat(p2, "/Downloads");
        strcpy(p3, run_home); strcat(p3, "/Pictures");
        strcpy(p4, run_home); strcat(p4, "/.trash");
        argv[0] = "du"; argv[1] = "-k"; argv[2] = "-s";
        argv[3] = p0; argv[4] = p1; argv[5] = p2; argv[6] = p3; argv[7] = p4; argv[8] = NULL;
    } else {
        argv[0] = "finder";
        argv[1] = job == RUN_TRASH_COUNT ? "--trash-count" : "--trash-empty";
        argv[2] = NULL;
    }
    strcpy(envh, "HOME=");
    strcat(envh, run_home);
    envp[0] = envh;
    envp[1] = "PATH=/bin";
    envp[2] = "LANG=C.UTF-8";
    envp[3] = NULL;
    if (pipe(out) < 0) return -errno;
    pid = fork();
    if (pid < 0) {
        st = -errno;
        close(out[0]);
        close(out[1]);
        return st;
    }
    if (pid == 0) {
        int nul = open("/dev/null", O_RDWR);
        if (nul < 0 || dup2(nul, 0) < 0 || dup2(out[1], 1) < 0 || dup2(nul, 2) < 0) _exit(127);
        for (int fd = 3; fd < 256; fd++) (void)close(fd);   /* 256: the kernel's FDS, every descriptor slot */
        if (RUN_LOGIN(run_uid, run_gid, run_ceil) < 0) _exit(126);
        if (RUN_CHDIR(run_home) < 0) _exit(126);   /* no fallback home */
        if (job == RUN_DU) {           /* the parts the home has, then the home: du counts a directory once, so the */
            static const char *const part[4] = {"Documents", "Downloads", "Pictures", ".trash"};
            char *home = argv[3];      /* home's line is the rest; a part it lacks is left out (no .trash: still 0) */
            int k = 3;
            for (int i = 0; i < 4; i++) {
                if (faccessat(AT_FDCWD, part[i], F_OK, 0) == 0) argv[k++] = argv[4 + i];
            }
            argv[k++] = home;
            argv[k] = NULL;
        }
        execve(RUN_PROGRAM(job), argv, envp);
        _exit(127);
    }
    close(out[1]);
    (void)fcntl(out[0], F_SETFL, fcntl(out[0], F_GETFL) | O_NONBLOCK);
    run_pid = pid;
    run_fd = out[0];
    run_total = 0;
    run_cap = cap;
    run_limit = limit;
    run_total_ms = total;
    run_t0 = run_now_ms();
    run_last = run_t0;
    return 0;
}

/* What the run wrote since the last poll, into buf (at most len): the bytes taken (0: nothing yet); RUN_END - status
 * once it ended, its output drained and the child reaped; -E2BIG past the job's cap or -ETIMEDOUT past its time (the
 * child killed and reaped); -ENOENT with no run. Whether a picture's stream was whole is the caller's count. */
static long run_poll(unsigned char *buf, size_t len)
{
    ssize_t got;
    if (run_fd < 0) return -ENOENT;
    {
        long long now = run_now_ms();
        long long since = run_total_ms > 0 ? run_last : run_t0;   /* RUN_PICTURE: progress, else the start */
        if (now - since > run_limit || (run_total_ms > 0 && now - run_t0 > run_total_ms)) {
            (void)run_reap(1);
            return -ETIMEDOUT;
        }
    }
    do {
        got = read(run_fd, buf, len);
    } while (got < 0 && errno == EINTR);
    if (got > 0) {
        run_last = run_now_ms();
        run_total += (long)got;
        if (run_total > run_cap) {
            (void)run_reap(1);
            return -E2BIG;
        }
        return (long)got;
    }
    if (got < 0 && errno == EAGAIN) return 0;
    if (got < 0) {
        (void)run_reap(1);
        return -EIO;
    }
    {
        int st = 0;
        pid_t w;
        do {
            w = waitpid(run_pid, &st, WNOHANG);
        } while (w < 0 && errno == EINTR);
        if (w == 0) return 0;          /* the pipe is closed, the child not yet ended: the next poll reaps it */
        if (w < 0) {
            close(run_fd);
            run_fd = -1;
            run_pid = -1;
            run_total = 0;
            return -ECHILD;
        }
        close(run_fd);
        run_fd = -1;
        run_pid = -1;
        run_total = 0;
        return RUN_END - (WIFEXITED(st) ? WEXITSTATUS(st) : 255);
    }
}

#endif
/* SPDX-License-Identifier: Apache-2.0 */
