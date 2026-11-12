/* tests/hosted/runas_test.c: the desk's runs as the account (user/ci/runas.h), hosted. The header as user/ci/host.c
 * includes it, with the login (Daphnis's call 1003) replaced by one that writes what it was asked to a note and can
 * refuse, the chdir to the home replaced by one into TMPDIR (the test has no /home), every job's program this test
 * itself (it acts as the program when argv[0] is du, finder or setkey), and a 1 KiB cap and a 300 ms limit. Checks:
 * uid 0, no record and a home that is not one name under /home are refused; a job outside the table and bad
 * arguments are refused; a run takes the record's uid, gid and ceiling, gets its argument vector word for word (no
 * shell; du only the home's parts the run's directory holds), a fixed environment of HOME, PATH and LANG, and ends
 * with its status; a refused login ends 126; a run past the cap is killed (-E2BIG), one past the time is killed
 * (-ETIMEDOUT), run_stop kills one that runs; one run at a time; after every case the caller has no child left. RG-1:
 * RUN_PEEK as account ada (uid 1000, /home/ada) takes an absolute path as one word, answers d for a folder and f and
 * the first 512 bytes for a file in a 0700 folder, its status 1 for a path it cannot stat, and is killed past its 513
 * bytes. Run by check.sh with gcc and with clang:
 *   cc -std=c11 -Iuser/ci tests/hosted/runas_test.c -o runas_test && ./runas_test
 * One line for each case that fails, then "runas: N checks, F failed"; exit status 1 if any failed. */
#define _XOPEN_SOURCE 700
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

static int refuse;                     /* the login's answer; the child has the caller's copy */
static char note[4400];                /* where the login writes what it was asked */
static char self[4200];                /* this test's own path: every job's program */
static char tmp[4200];                 /* TMPDIR: the runs' working directory */

static long test_login(long uid, long gid, long ceil)
{
    FILE *f = fopen(note, "w");
    if (f != NULL) {
        fprintf(f, "%ld %ld %ld\n", uid, gid, ceil);
        fclose(f);
    }
    return refuse ? -1 : 0;
}

#define RUN_LOGIN(uid, gid, ceil) test_login((long)(uid), (long)(gid), (long)(ceil))
#define RUN_CHDIR(path) chdir(tmp)
#define RUN_PROGRAM(job) self
#define RUN_CAP 1024
#define RUN_TIMEOUT_MS 300
#define RUN_PICTURE_MS 300
#include "runas.h"

static unsigned int checks, failed;
static size_t drained;                 /* the bytes the last drain took */
#define ARG(lit) lit, sizeof(lit) - 1  /* a literal argument and its length, NULs inside counted, the last not */

static void check(int ok, const char *what)
{
    checks++;
    if (!ok) {
        failed++;
        printf("FAIL %s\n", what);
    }
}

/* The run's output into out (at most cap - 1 bytes, NUL ended) until it answers below 0; that answer. drained
 * counts every byte taken. */
static long drain(char *out, size_t cap)
{
    size_t at = 0;
    drained = 0;
    for (;;) {
        unsigned char buf[256];
        long got = run_poll(buf, sizeof buf);
        if (got < 0) {
            out[at] = '\0';
            return got;
        }
        drained += (size_t)got;
        for (long i = 0; i < got && at + 1 < cap; i++) out[at++] = (char)buf[i];
        if (got == 0) {
            struct timespec ts = {0, 1000000};
            (void)nanosleep(&ts, NULL);
        }
    }
}

/* Whether the caller has no child left. */
static int no_child(void)
{
    return waitpid(-1, NULL, WNOHANG) < 0 && errno == ECHILD;
}

/* As a job's program: by the home's last name, write past the cap (big), sleep (slow), or print the argument vector
 * and the environment, each word between bars, and end 3 for a home named fail, else 0. */
static int as_program(int argc, char **argv, char **envp)
{
    const char *home = getenv("HOME");
    const char *last = home != NULL && strrchr(home, '/') != NULL ? strrchr(home, '/') + 1 : "";
    if (strcmp(argv[0], "bgread") == 0 && argc == 4 && strcmp(last, "args") != 0) {
        /* RUN_PICTURE's stand-in: the header and W x H pixels (exact), one byte less (short), one more (long), late,
         * or whole and then status 1 (fail) */
        long n = 8 + 4 * atol(argv[2]) * atol(argv[3]);
        struct timespec tick = {0, 10000000};   /* a Daphnis pipe's least rate: 4 KiB a 10 ms tick */
        struct timespec slow = {0, 100000000};
        if (strcmp(last, "short") == 0) n = n - 1;
        if (strcmp(last, "long") == 0) n = n + 1;
        if (strcmp(last, "late") == 0) sleep(5);
        for (long i = 0; i < n; i++) {
            putchar((int)(i % 251));
            if (strcmp(last, "drip") == 0 && i % 4096 == 4095) {
                fflush(stdout);
                (void)nanosleep(&tick, NULL);
            }
            if (strcmp(last, "crawl") == 0) {
                fflush(stdout);
                (void)nanosleep(&slow, NULL);
            }
            if (strcmp(last, "stall") == 0 && i == 7) {
                fflush(stdout);
                sleep(5);
            }
        }
        return strcmp(last, "fail") == 0 ? 1 : 0;
    }
    if (strcmp(argv[0], "finder") == 0 && argc == 3 && strcmp(argv[1], "--peek") == 0 && strcmp(last, "big") != 0) {
        /* RUN_PEEK's stand-in, as user/ci/finder.ci peek: d, or f and the first 512 bytes of a regular file opened
         * without waiting; 1 when stat fails or the path is a device, a pipe or a socket */
        struct stat sb;
        char b[512];
        int fd;
        if (stat(argv[2], &sb) < 0) return 1;
        if (S_ISDIR(sb.st_mode)) {
            putchar('d');
            return 0;
        }
        if (!S_ISREG(sb.st_mode)) return 1;
        fd = open(argv[2], O_RDONLY | O_NONBLOCK);
        if (fd >= 0) {
            ssize_t g;
            if (fstat(fd, &sb) < 0 || !S_ISREG(sb.st_mode)) {
                close(fd);
                return 1;
            }
            putchar('f');
            g = read(fd, b, sizeof b);
            if (g > 0) fwrite(b, 1, (size_t)g, stdout);
            close(fd);
            return 0;
        }
        putchar('f');
        return 0;
    }
    if (strcmp(last, "big") == 0) {
        for (int i = 0; i < 4 * RUN_CAP; i++) putchar('x');
        return 0;
    }
    if (strcmp(last, "slow") == 0) {
        sleep(5);
        return 0;
    }
    printf("argv");
    for (int i = 0; i < argc; i++) printf("|%s", argv[i]);
    printf("\nenv");
    for (int i = 0; envp[i] != NULL; i++) printf("|%s", envp[i]);
    printf("\n");
    return strcmp(last, "fail") == 0 ? 3 : 0;
}

/* name under the run's directory (TMPDIR), in a buffer of its own */
static const char *part_path(const char *name)
{
    static char p[4300];
    snprintf(p, sizeof p, "%s/%s", tmp, name);
    return p;
}

/* Makes (make) or removes the home's four parts in the run's directory; whether each is as asked. */
static int home_parts(int make)
{
    static const char *const part[4] = {"Documents", "Downloads", "Pictures", ".trash"};
    int ok = 1;
    for (int i = 0; i < 4; i++) {
        if (make) {
            if (mkdir(part_path(part[i]), 0700) < 0 && errno != EEXIST) ok = 0;
        } else if (rmdir(part_path(part[i])) < 0 && errno != ENOENT) {
            ok = 0;
        }
    }
    return ok;
}

static int session(long uid, const char *home) { return run_session(uid, 1000, 7, home, strlen(home)); }

int main(int argc, char **argv, char **envp)
{
    char out[8192];
    const char *t = getenv("TMPDIR");
    long r;
    if (strcmp(argv[0], "du") == 0 || strcmp(argv[0], "finder") == 0 || strcmp(argv[0], "setkey") == 0
        || strcmp(argv[0], "bgread") == 0) {
        return as_program(argc, argv, envp);
    }
    if (realpath(argv[0], self) == NULL) return 1;
    if (strlen(t != NULL ? t : "/tmp") >= 4096) return 1;
    snprintf(tmp, sizeof tmp, "%s", t != NULL ? t : "/tmp");
    snprintf(note, sizeof note, "%s/runas-note-%ld", tmp, (long)getpid());

    /* the record: uid 0 refused, no record refused, a home that is not one name under /home refused */
    check(session(0, "/home/sam") == -EPERM && run_start(RUN_DU, "", 0) == -EPERM, "uid 0 is refused");
    check(run_start(RUN_TRASH_COUNT, "", 0) == -EPERM, "no record: no run");
    check(session(1001, "/etc") == -EINVAL && session(1001, "/home/a/b") == -EINVAL, "a home under /home only");
    check(session(1001, "/home/..") == -EINVAL && session(1001, "/home/") == -EINVAL, "a home is one name");
    check(run_session(1001, -1, 7, "/home/sam", 9) == -EPERM, "a gid under 0 is refused");

    /* the table: a job outside it, an argument where none is taken, a bad key or value */
    check(session(1001, "/home/sam") == 0, "a record is taken");
    check(run_start(RUN_JOBS, "", 0) == -EINVAL && run_start(-1, "", 0) == -EINVAL, "a job outside the table");
    check(run_start(RUN_DU, "x", 1) == -EINVAL, "du takes no argument");
    check(run_start(RUN_SET, "Bad\0v", 5) == -EINVAL, "a key with a capital is refused");
    check(run_start(RUN_SET, "time.24-hour\0a\nb", 16) == -EINVAL, "a value with a line feed is refused");
    check(run_start(RUN_SET, "novalue", 7) == -EINVAL, "a key with no value is refused");
    check(no_child(), "no child after the refusals");

    /* a run: the record's login, the vector word for word, the fixed environment, its status */
    refuse = 0;
    check(run_start(RUN_SET, "desk.background\0/home/sam/a b; rm -rf ~ $(x)", 44) == 0, "setkey starts");
    check(run_start(RUN_DU, "", 0) == -EBUSY, "one run at a time");
    r = drain(out, sizeof out);
    check(r == RUN_END, "setkey ends 0");
    check(strstr(out, "argv|setkey|desk.background|/home/sam/a b; rm -rf ~ $(x)\n") != NULL, "the vector, no shell");
    check(strstr(out, "env|HOME=/home/sam|PATH=/bin|LANG=C.UTF-8\n") != NULL, "the fixed environment, no more");
    {
        FILE *f = fopen(note, "r");
        long u = -1, g = -1, c = -1;
        if (f != NULL) {
            if (fscanf(f, "%ld %ld %ld", &u, &g, &c) != 3) u = -1;
            fclose(f);
        }
        check(u == 1001 && g == 1000 && c == 7, "the login takes the record's uid, gid and ceiling");
    }
    check(no_child(), "no child after a run");
    check(home_parts(1), "the four parts made in the run's directory");
    check(run_start(RUN_DU, "", 0) == 0, "du starts");
    r = drain(out, sizeof out);
    check(r == RUN_END && strstr(out, "argv|du|-k|-s|/home/sam/Documents|/home/sam/Downloads|/home/sam/Pictures|"
                                      "/home/sam/.trash|/home/sam\n") != NULL,
          "du's fixed vector: the parts, then the home");
    check(rmdir(part_path(".trash")) == 0 && run_start(RUN_DU, "", 0) == 0, "du starts on a home with no .trash");
    r = drain(out, sizeof out);
    check(r == RUN_END && strstr(out, "argv|du|-k|-s|/home/sam/Documents|/home/sam/Downloads|/home/sam/Pictures|"
                                      "/home/sam\n") != NULL, "a new home's missing .trash is left out");
    check(home_parts(0) && run_start(RUN_DU, "", 0) == 0, "du starts on a bare home");
    r = drain(out, sizeof out);
    check(r == RUN_END && strstr(out, "argv|du|-k|-s|/home/sam\n") != NULL, "a bare home: the home alone");
    check(run_start(RUN_TRASH_EMPTY, "", 0) == 0 && drain(out, sizeof out) == RUN_END
          && strstr(out, "argv|finder|--trash-empty\n") != NULL, "finder --trash-empty");
    check(session(1001, "/home/fail") == 0 && run_start(RUN_TRASH_COUNT, "", 0) == 0
          && drain(out, sizeof out) == RUN_END - 3, "the status comes back");
    refuse = 1;
    check(run_start(RUN_TRASH_COUNT, "", 0) == 0 && drain(out, sizeof out) == RUN_END - 126, "a refused login: 126");
    refuse = 0;
    check(no_child(), "no child after the ends");

    /* the argument bytes main.c holds in all, 4096: "setkey" or "bgread", every word and each NUL */
    {
        static char big[4200];
        memset(big, 'v', sizeof big);
        big[0] = 'k';
        big[1] = '\0';                  /* "k\0" then the value: 7 + 1 + 1 + 4086 + 1 = 4096 */
        check(session(1001, "/home/args") == 0 && run_start(RUN_SET, big, 2 + 4086) == 0,
              "a setting at the total of 4096 argument bytes starts");
        run_stop();
        check(run_start(RUN_SET, big, 2 + 4087) == -EINVAL, "one byte past the total is refused");
        memset(big, 'p', sizeof big);
        big[0] = '/';                    /* PATH of 4084, "4", "3": 7 + 4085 + 2 + 2 = 4096 */
        memcpy(big + 4084, "\0" "4\0" "3", 4);
        check(session(1001, "/home/exact") == 0 && run_start(RUN_PICTURE, big, 4084 + 4) == 0
              && drain(out, sizeof out) == RUN_END && drained == 8 + 4 * 4 * 3,
              "a picture's arguments at the total run");
        memset(big, 'p', sizeof big);
        big[0] = '/';
        memcpy(big + 4085, "\0" "4\0" "3", 4);
        check(run_start(RUN_PICTURE, big, 4085 + 4) == -EINVAL, "a picture's arguments one past the total are refused");
        check(no_child(), "no child after the totals");
    }

    /* a session that ends and a later one for another uid at the same home name: the run is the new uid's */
    {
        FILE *f;
        long u = -1, g = -1, c = -1;
        check(session(1001, "/home/sam") == 0 && session(-1, "") == 0, "the record cleared at the end");
        check(run_start(RUN_DU, "", 0) == -EPERM, "between sessions nothing runs");
        check(run_session(1002, 1002, 1, "/home/sam", 9) == 0 && run_start(RUN_DU, "", 0) == 0
              && drain(out, sizeof out) == RUN_END, "the next session's run");
        f = fopen(note, "r");
        if (f != NULL) {
            if (fscanf(f, "%ld %ld %ld", &u, &g, &c) != 3) u = -1;
            fclose(f);
        }
        check(u == 1002 && g == 1002 && c == 1, "it logs in as the new uid, never the last");
    }

    /* RUN_PICTURE (BG-1): its arguments, its exact cap, its own time */
    check(session(1001, "/home/args") == 0, "a record for the picture");
    check(run_start(RUN_PICTURE, ARG("a.png\0" "4\0" "3")) == -EINVAL, "a relative path is refused");
    check(run_start(RUN_PICTURE, ARG("/p.png\0" "0\0" "3")) == -EINVAL, "a width of 0 is refused");
    check(run_start(RUN_PICTURE, ARG("/p.png\0" "3841\0" "3")) == -EINVAL, "a width past 3840 is refused");
    check(run_start(RUN_PICTURE, ARG("/p.png\0" "4\0" "3841")) == -EINVAL, "a side past 3840 is refused");
    check(run_start(RUN_PICTURE, ARG("/p.png\0" "3840\0" "2161")) == -EINVAL, "an area past 3840 x 2160 is refused");
    check(run_start(RUN_PICTURE, ARG("/p.png\0" "04\0" "3")) == -EINVAL, "a leading zero is refused");
    check(run_start(RUN_PICTURE, ARG("/p.png\0" "4")) == -EINVAL, "a height is needed");
    check(run_start(RUN_PICTURE, ARG("/home/sam/my pic $(x).png\0" "64\0" "64")) == 0
          && drain(out, sizeof out) == RUN_END
          && strstr(out, "argv|bgread|/home/sam/my pic $(x).png|64|64\n") != NULL, "the path is one word, as it is");
    check(session(1001, "/home/exact") == 0 && run_start(RUN_PICTURE, ARG("/p.png\0" "4\0" "3")) == 0
          && drain(out, sizeof out) == RUN_END && drained == 8 + 4 * 4 * 3, "an exact stream: whole, status 0");
    check(session(1001, "/home/short") == 0 && run_start(RUN_PICTURE, ARG("/p.png\0" "4\0" "3")) == 0
          && drain(out, sizeof out) == RUN_END && drained == 8 + 4 * 4 * 3 - 1, "a short stream: counted short");
    check(session(1001, "/home/long") == 0 && run_start(RUN_PICTURE, ARG("/p.png\0" "4\0" "3")) == 0
          && drain(out, sizeof out) == -E2BIG, "one byte past header and pixels: -E2BIG");
    check(no_child(), "the long picture's child is reaped");
    check(session(1001, "/home/late") == 0 && run_start(RUN_PICTURE, ARG("/p.png\0" "4\0" "3")) == 0
          && drain(out, sizeof out) == -ETIMEDOUT, "a late picture: -ETIMEDOUT");
    check(no_child(), "the late picture's child is reaped");
    check(session(1001, "/home/drip") == 0 && run_start(RUN_PICTURE, ARG("/p.png\0" "128\0" "320")) == 0
          && drain(out, sizeof out) == RUN_END && drained == 8 + 4 * 128 * 320,
          "a 4 KiB pipe's rate: 400 ms in all, past the 300 ms with no byte, lands whole (the time is progress)");
    check(no_child(), "the drip's child is reaped");
    check(session(1001, "/home/stall") == 0 && run_start(RUN_PICTURE, ARG("/p.png\0" "128\0" "320")) == 0
          && drain(out, sizeof out) == -ETIMEDOUT && drained == 8, "the header, then no byte: -ETIMEDOUT");
    check(no_child(), "the stall's child is reaped");
    check(session(1001, "/home/crawl") == 0 && run_start(RUN_PICTURE, ARG("/p.png\0" "4\0" "3")) == 0
          && drain(out, sizeof out) == -ETIMEDOUT, "bytes that keep coming past twice the pipe's rate: -ETIMEDOUT");
    check(no_child(), "the crawl's child is reaped");
    check(session(1001, "/home/fail") == 0 && run_start(RUN_PICTURE, ARG("/p.png\0" "4\0" "3")) == 0
          && drain(out, sizeof out) == RUN_END - 1, "status 1 comes back");
    check(session(1001, "/home/big") == 0 && run_start(RUN_DU, "", 0) == 0 && drain(out, sizeof out) == -E2BIG,
          "after a picture the other jobs keep their own cap");

    /* RG-1, RUN_PEEK as ada: a file in ada's 0700 home opened from Index, peeked as ada for the desk */
    {
        char dir[4300], file[4400], none[4400], fifo[4400], want[600];
        static char big[4200];
        FILE *f;
        long u = -1, g = -1, c = -1;
        snprintf(dir, sizeof dir, "%s/runas-ada-%ld", tmp, (long)getpid());
        snprintf(file, sizeof file, "%s/notes.txt", dir);
        snprintf(none, sizeof none, "%s/gone.txt", dir);
        check(mkdir(dir, 0700) == 0, "ada's home, 0700");
        f = fopen(file, "w");
        if (f != NULL) {
            for (int i = 0; i < 600; i++) fputc(i < 6 ? "hello\n"[i] : 'a' + i % 26, f);
            fclose(f);
        }
        check(run_session(1000, 1000, 7, "/home/ada", 9) == 0, "ada's record");
        check(run_start(RUN_PEEK, ARG("notes.txt")) == -EINVAL, "a relative path is refused");
        check(run_start(RUN_PEEK, ARG("/")) == -EINVAL, "a path of one byte is refused");
        check(run_start(RUN_PEEK, ARG("/home/ada/a\0b")) == -EINVAL, "a NUL inside the path is refused");
        memset(big, 'p', sizeof big);
        big[0] = '/';                    /* "finder", "--peek" and PATH with their NULs: 7 + 7 + 4082 = 4096 */
        check(run_start(RUN_PEEK, big, 4082) == -EINVAL, "a path past the 4096 argument bytes is refused");
        check(run_start(RUN_PEEK, big, 4081) == 0 && drain(out, sizeof out) == RUN_END - 1,
              "a path at the total runs (and is not there: status 1)");
        check(run_start(RUN_PEEK, file, strlen(file)) == 0, "the peek starts");
        r = drain(out, sizeof out);
        memcpy(want, "fhello\n", 7);
        for (int i = 6; i < 512; i++) want[1 + i] = (char)('a' + i % 26);
        check(r == RUN_END && drained == 513 && memcmp(out, want, 513) == 0, "f and the file's first 512 bytes");
        f = fopen(note, "r");
        if (f != NULL) {
            if (fscanf(f, "%ld %ld %ld", &u, &g, &c) != 3) u = -1;
            fclose(f);
        }
        check(u == 1000 && g == 1000 && c == 7, "the peek logs in as ada");
        check(run_start(RUN_PEEK, dir, strlen(dir)) == 0 && drain(out, sizeof out) == RUN_END && drained == 1
              && out[0] == 'd', "a folder: d");
        check(run_start(RUN_PEEK, none, strlen(none)) == 0 && drain(out, sizeof out) == RUN_END - 1,
              "a path ada cannot stat either: status 1");
        snprintf(fifo, sizeof fifo, "%s/pipe", dir);
        check(mkfifo(fifo, 0600) == 0 && run_start(RUN_PEEK, fifo, strlen(fifo)) == 0
              && drain(out, sizeof out) == RUN_END - 1 && drained == 0,
              "a pipe in ada's home is never opened: status 1 at once, nothing written (no stall to the run's time)");
        check(run_start(RUN_PEEK, "/dev/null", 9) == 0 && drain(out, sizeof out) == RUN_END - 1 && drained == 0,
              "a device: status 1, never opened");
        (void)unlink(fifo);
        /* RUN_PREFS: ada's settings, read by ada's own setkey (the desk cannot open the 0700 home) */
        check(run_start(RUN_PREFS, "x", 1) == -EINVAL, "the settings read takes no argument");
        check(run_start(RUN_PREFS, "", 0) == 0 && drain(out, sizeof out) == RUN_END
              && strstr(out, "argv|setkey|--print\n") != NULL && strstr(out, "env|HOME=/home/ada|") != NULL,
              "the settings read: setkey --print as ada, HOME ada's home");
        check(session(1000, "/home/big") == 0 && run_start(RUN_PEEK, file, strlen(file)) == 0
              && drain(out, sizeof out) == -E2BIG, "past the peek's 513 bytes: -E2BIG");
        check(no_child(), "no child after the peeks");
        (void)unlink(file);
        (void)rmdir(dir);
    }

    /* the limits: the cap, the time, run_stop */
    check(session(1001, "/home/big") == 0 && run_start(RUN_DU, "", 0) == 0, "big starts");
    check(drain(out, sizeof out) == -E2BIG, "past the cap: -E2BIG");
    check(no_child(), "the cap's child is reaped");
    check(session(1001, "/home/slow") == 0 && run_start(RUN_DU, "", 0) == 0, "slow starts");
    check(drain(out, sizeof out) == -ETIMEDOUT, "past the time: -ETIMEDOUT");
    check(no_child(), "the time's child is reaped");
    check(run_start(RUN_DU, "", 0) == 0, "slow starts again");
    run_stop();
    check(no_child() && run_poll((unsigned char *)out, 16) == -ENOENT, "run_stop kills and reaps");
    check(run_start(RUN_DU, "", 0) == 0 && session(-1, "") == 0, "a cleared record stops the run");
    check(no_child() && run_start(RUN_DU, "", 0) == -EPERM, "and nothing runs without a record");

    (void)unlink(note);
    printf("runas: %u checks, %u failed\n", checks, failed);
    return failed == 0u ? 0 : 1;
}
