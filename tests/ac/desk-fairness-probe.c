#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>
static long long clock_ms(void) {
    struct timespec t;
    if (clock_gettime(CLOCK_BOOTTIME, &t) < 0) return 0;
    return t.tv_sec * 1000LL + t.tv_nsec / 1000000;
}
static void work_until(long long deadline) {
    while (clock_ms() < deadline) {
        for (volatile int k = 0; k < 200000; k++) {}
    }
}
int main(void) {
    int fb = open("/dev/fb0", O_RDWR), p[2];
    if (fb < 0 || ioctl(fb, 0x4680, 0) < 0 || pipe(p) < 0 || fcntl(p[0], F_SETFL, O_NONBLOCK) < 0) return 2;
    long long start = clock_ms();
    pid_t hog = fork();
    if (hog < 0) return 3;
    if (hog == 0) {
        close(p[0]); close(p[1]);
        work_until(start + 3000);
        _exit(0);
    }
    pid_t writer = fork();
    if (writer < 0) return 4;
    if (writer == 0) {
        close(p[0]);
#ifdef FAIR_TOUCH_PAGES
        unsigned char *pages = mmap(NULL, 2 * 1024 * 1024, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
        if (pages == MAP_FAILED) _exit(6);
        for (int k = 0; k < 512; k++) pages[k * 4096] = 1;
#endif
        _exit(write(p[1], "x", 1) == 1 ? 0 : 5);
    }
    close(p[1]);
    work_until(start + 700);
    char byte = 0;
    int progress = (int)read(p[0], &byte, 1);
    if (progress < 0) progress = -errno;
    kill(hog, SIGKILL);
    int h = 0, w = 0;
    waitpid(hog, &h, 0); waitpid(writer, &w, 0);
    dprintf(1, "fairness-probe: background=%d byte=%d writer=%d\n", progress, byte, w);
    return progress == 1 && byte == 'x' && w == 0 ? 0 : 1;
}
