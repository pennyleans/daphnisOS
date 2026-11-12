/* user/c/mchurn.c: the Track 2 churn of the sealed run (docs/specs/2026-11-05-r-desync.md sections 2 and 7),
 * unprivileged work an ordinary process may do before `doom --sealed` to leave the kernel in another shape:
 * memory mapped, written and given back out of order, files made and some removed (the rest stay in the
 * image's view), a pipe carrying 64 KiB between two processes, children that exit, sleep and are killed
 * while running, the descriptor table filled to EMFILE and emptied. Built by user/c/build.sh (static musl,
 * committed as user/bin/mchurn, ruling DU-2 A). Prints one line per part and exits 0. */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#define MAPS 12
#define FILES 16

static int memory(void)
{
    uint8_t *m[MAPS];
    uint32_t sum = 0u;
    for (int i = 0; i < MAPS; i++) {
        size_t len = (size_t)(i + 1) * 65536u;
        m[i] = mmap(NULL, len, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
        if (m[i] == MAP_FAILED) return 1;
        for (size_t k = 0; k < len; k += 4096u) m[i][k] = (uint8_t)(i * 7 + k / 4096u);
    }
    for (int i = 0; i < MAPS; i += 2) munmap(m[i], (size_t)(i + 1) * 65536u);   /* every other one back */
    for (int i = 1; i < MAPS; i += 2) sum += m[i][4096];
    uintptr_t top = (uintptr_t)syscall(SYS_brk, 0);   /* musl's sbrk takes only 0 */
    if ((uintptr_t)syscall(SYS_brk, top + (1u << 20)) != top + (1u << 20)) return 2;
    memset((void *)top, 0x5a, 1u << 20);
    if ((uintptr_t)syscall(SYS_brk, top + (1u << 19)) != top + (1u << 19)) return 3;
    printf("mchurn: memory %d maps, %d returned, brk up 1 MiB and down half, sum %u\n", MAPS, MAPS / 2, sum);
    return 0;
}

static int files(void)
{
    char name[16], buf[512];
    int kept = 0;
    memset(buf, 'c', sizeof buf);
    for (int i = 0; i < FILES; i++) {
        snprintf(name, sizeof name, "churn%02d", i);
        int fd = open(name, O_WRONLY | O_CREAT | O_TRUNC, 0644);
        if (fd < 0) return 1;
        for (int k = 0; k <= i % 5; k++)
            if (write(fd, buf, sizeof buf) != (ssize_t)sizeof buf) return 2;
        close(fd);
    }
    for (int i = 0; i < FILES; i++) {
        snprintf(name, sizeof name, "churn%02d", i);
        if (i % 3 != 0) {
            if (unlink(name) != 0) return 3;
        } else {
            kept++;
        }
    }
    printf("mchurn: files %d made, %d removed, %d left\n", FILES, FILES - kept, kept);
    return 0;
}

static int pipes(void)
{
    int p[2];
    char buf[4096];
    long got = 0;
    if (pipe(p) != 0) return 1;
    pid_t c = fork();
    if (c < 0) return 2;
    if (c == 0) {
        close(p[0]);
        memset(buf, 'p', sizeof buf);
        for (int i = 0; i < 16; i++)
            if (write(p[1], buf, sizeof buf) != (ssize_t)sizeof buf) _exit(1);
        _exit(0);
    }
    close(p[1]);
    for (;;) {
        ssize_t n = read(p[0], buf, sizeof buf);
        if (n <= 0) break;
        got += n;
    }
    close(p[0]);
    int st = 0;
    waitpid(c, &st, 0);
    printf("mchurn: pipe %ld bytes, writer status %d\n", got, WEXITSTATUS(st));
    return 0;
}

static int processes(void)
{
    pid_t c[4];
    int st[4];
    for (int i = 0; i < 4; i++) {
        c[i] = fork();
        if (c[i] < 0) return 1;
        if (c[i] == 0) {
            if (i == 0) _exit(7);
            if (i == 1) {
                struct timespec d = {0, 20000000};   /* 20 ms of the virtual clock */
                nanosleep(&d, NULL);
                _exit(0);
            }
            for (volatile uint64_t k = 0;; k++) {   /* 2 and 3 run until killed */
            }
        }
    }
    kill(c[2], SIGKILL);
    kill(c[3], SIGTERM);
    for (int i = 0; i < 4; i++) waitpid(c[i], &st[i], 0);
    printf("mchurn: processes exit %d, slept exit %d, killed by %d and %d\n", WEXITSTATUS(st[0]),
           WEXITSTATUS(st[1]), WTERMSIG(st[2]), WTERMSIG(st[3]));
    return 0;
}

static int descriptors(void)
{
    int fds[256], n = 0;                  /* FS-4: 256 descriptors a process */
    for (;;) {
        int fd = open("hello.txt", O_RDONLY);
        if (fd < 0) break;
        fds[n++] = fd;
        if (n == 256) return 1;
    }
    int err = errno;
    for (int i = n - 1; i >= 0; i -= 2) close(fds[i]);   /* the high half first, out of order */
    for (int i = n - 2; i >= 0; i -= 2) close(fds[i]);
    printf("mchurn: descriptors %d opened until %s, all closed\n", n, err == EMFILE ? "EMFILE" : "another error");
    return 0;
}

int main(void)
{
    setvbuf(stdout, NULL, _IONBF, 0);   /* the children's lines never carry the parent's buffer */
    int r = memory();
    if (r == 0) r = files() ? 10 : 0;
    if (r == 0) r = pipes() ? 20 : 0;
    if (r == 0) r = processes() ? 30 : 0;
    if (r == 0) r = descriptors() ? 40 : 0;
    if (r != 0) printf("mchurn: failed %d\n", r);
    return r;
}
