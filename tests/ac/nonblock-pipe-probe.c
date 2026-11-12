#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <stdio.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>
static long long clock_ms(void) {
    struct timespec t;
    if (clock_gettime(CLOCK_BOOTTIME, &t) < 0) return 0;
    return t.tv_sec * 1000LL + t.tv_nsec / 1000000;
}
int main(void) {
    int p[2];
    if (pipe(p) < 0 || fcntl(p[0], F_SETFL, O_NONBLOCK) < 0) return 2;
    long long until = clock_ms() + 500;
    pid_t child = fork();
    if (child < 0) return 3;
    if (child == 0) {
        close(p[0]);
        while (clock_ms() < until) {}
        if (write(p[1], "x", 1) != 1) _exit(4);
        close(p[1]);
        _exit(0);
    }
    close(p[1]);
    char b = 0;
    int first = (int)read(p[0], &b, 1);
    if (first < 0) first = -errno;
    int status = 0;
    if (waitpid(child, &status, 0) != child) return 5;
    int data = (int)read(p[0], &b, 1);
    int eof = (int)read(p[0], &b, 1);
    dprintf(1, "pipe-probe: empty=%d data=%d byte=%d eof=%d child=%d\n", first, data, b, eof, status);
    return first == -EAGAIN && data == 1 && b == 'x' && eof == 0 && status == 0 ? 0 : 1;
}
