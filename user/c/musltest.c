/* user/c/musltest.c: the U1-2 test programs (docs/specs/2026-11-05-u1-2-musl.md section 7), one
 * static musl binary that does what its name says: the cpio image holds it under its names (U1-2 to E-1).
 * Built once by user/c/build.sh (ruling DU-2 A); the bytes live in user/bin/musltest. */
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <sys/mman.h>
#include <sys/syscall.h>
#include <sys/stat.h>
#include <sys/uio.h>
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <sys/wait.h>
#include <sys/ioctl.h>
#include <stdint.h>
#include <sys/resource.h>
#include <poll.h>

/* printf fields: signed, unsigned, hex, widths, strings */
static int t_printf(int argc, char **argv)
{
    printf("%s: argc %d\n", argv[0], argc);
    printf("[%d] [%5d] [%-5d|] [%05d]\n", -42, 42, 42, 42);
    printf("[%u] [%lu] [%x] [%#lx]\n", 4000000000u, 18446744073709551615ul, 48879u, 0xdaf1ul);
    printf("[%s] [%8s] [%-8s|] [%.3s]\n", "desync", "cint", "ring3", "musl-libc");
    printf("[%c%c%c] [%%]\n", 'D', 'a', 'p');
    return 0;
}

/* malloc through brk and mmap, 100 bytes and 1 MiB */
static int t_malloc(int argc, char **argv)
{
    char *small = malloc(100);
    char *big = malloc(1 << 20);
    long s = 0;
    if (!small || !big) return 1;
    memset(big, 7, 1 << 20);
    for (int i = 0; i < (1 << 20); i += 4096) s += big[i];
    strcpy(small, argv[0]);
    printf("%s: %d args, sum %ld\n", small, argc, s);
    free(big);
    free(small);
    return 3;
}

/* the raw brk call, up and down; only moves print, since the start differs from Linux */
static int t_brk(void)
{
    long start = syscall(SYS_brk, 0);
    long up = syscall(SYS_brk, start + 65536);
    volatile char *top = (char *)(up - 1);
    *top = 42;
    int seen = *top;
    long down = syscall(SYS_brk, start);
    long again = syscall(SYS_brk, 0);
    printf("brk up %ld\n", up - start);
    printf("top byte %d\n", seen);
    printf("brk down %ld, now %ld\n", down - start, again - start);
    return 0;
}

/* mmap, mprotect to read only, read, then write: SIGSEGV */
static int t_prot(void)
{
    volatile char *p = mmap(0, 4096, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (p == MAP_FAILED) return 1;
    p[100] = 9;
    if (mprotect((void *)p, 4096, PROT_READ) != 0) return 2;
    printf("read %d after mprotect\n", p[100]);
    fflush(stdout);
    p[100] = 10;
    return 3;
}

static long long ns(struct timespec t)
{
    return (long long)t.tv_sec * 1000000000LL + t.tv_nsec;
}

/* clock_gettime and nanosleep: Daphnis serves a virtual clock, so only order prints */
static int t_clock(void)
{
    struct timespec a, b, c, r, d = {0, 1000000};
    clock_gettime(CLOCK_MONOTONIC, &a);
    clock_gettime(CLOCK_MONOTONIC, &b);
    nanosleep(&d, 0);
    clock_gettime(CLOCK_MONOTONIC, &c);
    clock_gettime(CLOCK_REALTIME, &r);
    printf("monotonic %s\n", ns(b) >= ns(a) ? "yes" : "no");
    printf("slept %s\n", ns(c) - ns(b) >= 1000000 ? "yes" : "no");
    printf("realtime after 2026 %s\n", r.tv_sec >= 1767225600 ? "yes" : "no");
    return 0;
}

static __thread int counter = 5;
static __thread char tag[8] = "tls";

/* thread-local storage through the FS base */
static int t_tls(int argc, char **argv)
{
    for (int i = 0; i < 37; i++) counter += argc;
    printf("%s %s counter %d\n", argv[0], tag, counter);
    return 0;
}

typedef unsigned int v4 __attribute__((vector_size(16)));

/* vector sums held in XMM registers across many timer turns; the seed is the last letter of the
 * name, so ssea and sseb run together hold different values */
static int t_sse(int argc, char **argv)
{
    unsigned seed = (unsigned char)argv[0][strlen(argv[0]) - 1] + (unsigned)argc;
    v4 x = {seed, seed * 3u, seed * 5u, seed * 7u};
    v4 k = {0x9E3779B9u, 0x7F4A7C15u, 0x85EBCA6Bu, 0xC2B2AE35u};
    v4 acc = {0, 0, 0, 0};
    for (unsigned i = 0; i < (1u << 22); i++) {
        x = (x ^ (x << 7)) + k;
        x ^= x >> 9;
        acc += x >> 3;
    }
    printf("%s: %08x %08x %08x %08x\n", argv[0], acc[0], acc[1], acc[2], acc[3]);
    return 0;
}

/* U1-3: fstat and read of hello.txt to stdout */
static int t_cat(void)
{
    char b[256];
    struct stat st;
    int fd = open("hello.txt", O_RDONLY);
    if (fd < 0) return 1;
    if (fstat(fd, &st) != 0) return 2;
    printf("size %ld\n", (long)st.st_size);
    fflush(stdout);
    for (;;) {
        ssize_t n = read(fd, b, sizeof b);
        if (n <= 0) break;
        if (write(1, b, (size_t)n) != n) return 3;
    }
    return close(fd);
}

static int by_name(const void *a, const void *b)
{
    return strcmp(*(const char *const *)a, *(const char *const *)b);
}

/* U1-3: the root directory, names sorted, with sizes; P-0: a directory shows "dir", since a
 * directory's size is the host filesystem's own number */
static int t_ls(void)
{
    static char store[64][32];
    char *list[64];
    int n = 0;
    DIR *d = opendir(".");
    struct dirent *e;
    if (!d) return 1;
    while ((e = readdir(d)) && n < 64) {
        if (!strcmp(e->d_name, ".") || !strcmp(e->d_name, "..")) continue;
        strncpy(store[n], e->d_name, 31);
        list[n] = store[n];
        n++;
    }
    closedir(d);
    qsort(list, (size_t)n, sizeof list[0], by_name);
    for (int i = 0; i < n; i++) {
        struct stat st;
        if (stat(list[i], &st) != 0) return 2;
        if (S_ISDIR(st.st_mode))
            printf("%-10s dir\n", list[i]);
        else
            printf("%-10s %ld\n", list[i], (long)st.st_size);
    }
    printf("%d entries\n", n);
    return 0;
}

/* U1-3: create, write, read back, append, stat, unlink */
static int t_write(void)
{
    char b[128];
    struct stat st;
    int fd = open("out.txt", O_WRONLY | O_CREAT | O_TRUNC, 0644);
    if (fd < 0) return 1;
    if (write(fd, "one\ntwo\n", 8) != 8) return 2;
    close(fd);
    fd = open("out.txt", O_RDONLY);
    if (fd < 0) return 3;
    ssize_t n = read(fd, b, sizeof b - 1);
    if (n < 0) return 4;
    b[n] = 0;
    close(fd);
    printf("read back %zd bytes: %s", n, b);
    fd = open("out.txt", O_WRONLY | O_APPEND);
    if (fd < 0) return 5;
    if (write(fd, "three\n", 6) != 6) return 6;
    close(fd);
    if (stat("out.txt", &st) != 0) return 7;
    printf("after append %ld bytes\n", (long)st.st_size);
    if (unlink("out.txt") != 0) return 8;
    fd = open("out.txt", O_RDONLY);
    printf("open after unlink: %d, errno %d\n", fd, fd < 0 ? errno : 0);
    return 0;
}

/* U1-3: the numbers descriptors get, and the ways to read a file */
static int t_fd(void)
{
    char a[8], c[8];
    struct iovec v[2] = {{a, 4}, {c, 4}};
    int fd = open("lines.txt", O_RDONLY);
    int d1 = dup(fd);
    int d2 = dup2(fd, 9);
    int d3 = fcntl(fd, F_DUPFD, 5);
    printf("open %d dup %d dup2 %d dupfd %d\n", fd, d1, d2, d3);
    close(d1);
    int again = open("lines.txt", O_RDONLY);
    printf("after close %d: open gives %d\n", d1, again);
    printf("getfl %d\n", fcntl(fd, F_GETFL) & O_ACCMODE);
    printf("lseek end %ld\n", (long)lseek(fd, 0, SEEK_END));
    printf("lseek 7 then cur %ld\n", (long)(lseek(fd, 7, SEEK_SET), lseek(fd, 0, SEEK_CUR)));
    if (readv(fd, v, 2) != 8) return 1;
    printf("readv [%.4s][%.4s]\n", a, c);
    char p[12] = {0};
    if (pread(d2, p, 11, 20) != 11) return 2;
    printf("pread [%s], shared offset %ld\n", p, (long)lseek(d2, 0, SEEK_CUR));
    printf("close bad fd: %d\n", close(12));
    return 0;
}

/* U1-3: stdin to EOF */
static int t_stdin(void)
{
    char b[512];
    size_t n = 0;
    for (;;) {
        ssize_t r = read(0, b + n, sizeof b - n);
        if (r <= 0) break;
        n += (size_t)r;
        if (n == sizeof b) break;
    }
    int lines = 0;
    for (size_t i = 0; i < n; i++) {
        if (b[i] == '\n') lines++;
        if (b[i] >= 'a' && b[i] <= 'z') b[i] -= 32;
    }
    printf("%zu bytes, %d lines\n", n, lines);
    fwrite(b, 1, n, stdout);
    printf("\n");
    return 0;
}

/* U1-3: leaves files, a rewritten hello.txt and open descriptors behind */
static int t_litter(void)
{
    char name[16];
    for (int i = 0; i < 5; i++) {
        snprintf(name, sizeof name, "litter%d.txt", i);
        int fd = open(name, O_WRONLY | O_CREAT | O_TRUNC, 0644);
        if (fd < 0) return 1;
        write(fd, name, strlen(name));
        if (i % 2) close(fd);
    }
    int fd = open("hello.txt", O_WRONLY | O_TRUNC);
    if (fd < 0) return 2;
    write(fd, "rewritten\n", 10);
    dup2(fd, 11);
    return 0;
}

/* U1-4: fork and wait4; the child sees its parent */
static int t_fork(void)
{
    pid_t me = getpid();
    pid_t c = fork();
    int st = 0;
    if (c < 0) return 1;
    if (c == 0) {
        printf("child: parent is %s\n", getppid() == me ? "the forker" : "someone else");
        fflush(stdout);
        _exit(7);
    }
    pid_t w = waitpid(c, &st, 0);
    printf("parent: waited for %s, exit %d\n", w == c ? "the child" : "another", WIFEXITED(st) ? WEXITSTATUS(st) : -1);
    printf("parent: second wait: %d\n", waitpid(-1, &st, 0) < 0 ? errno : 0);
    return 0;
}

/* U1-4: a pipe between parent and child */
static int t_pipe(void)
{
    int p[2];
    char b[64];
    size_t n = 0;
    int st = 0;
    if (pipe(p)) return 1;
    pid_t c = fork();
    if (c == 0) {
        close(p[0]);
        for (int i = 0; i < 3; i++) {
            char l[16];
            int k = snprintf(l, sizeof l, "ping %d\n", i);
            write(p[1], l, (size_t)k);
        }
        close(p[1]);
        _exit(0);
    }
    close(p[1]);
    for (;;) {
        ssize_t r = read(p[0], b + n, sizeof b - n);
        if (r <= 0) break;
        n += (size_t)r;
    }
    waitpid(c, &st, 0);
    printf("read %zu bytes:\n", n);
    fwrite(b, 1, n, stdout);
    printf("child exit %d\n", WEXITSTATUS(st));
    return 0;
}

/* U1-4: execve with arguments */
static int t_exec(void)
{
    char *av[] = {"mprintf", "one", "two", 0};
    printf("exec mprintf with 3 args\n");
    fflush(stdout);
    execve("mprintf", av, 0);
    printf("exec failed %d\n", errno);
    return 1;
}

/* U1-4: a two-program pipeline, as a shell builds one: mcat | mstdin */
static int t_pipeline(void)
{
    int p[2];
    int sa = 0, sb = 0;
    if (pipe(p)) return 1;
    pid_t a = fork();
    if (a == 0) {
        dup2(p[1], 1);
        close(p[0]);
        close(p[1]);
        char *av[] = {"mcat", 0};
        execve("mcat", av, 0);
        _exit(127);
    }
    pid_t b = fork();
    if (b == 0) {
        dup2(p[0], 0);
        close(p[0]);
        close(p[1]);
        char *av[] = {"mstdin", 0};
        execve("mstdin", av, 0);
        _exit(127);
    }
    close(p[0]);
    close(p[1]);
    waitpid(a, &sa, 0);
    waitpid(b, &sb, 0);
    printf("pipeline: mcat exit %d, mstdin exit %d\n", WEXITSTATUS(sa), WEXITSTATUS(sb));
    return 0;
}

/* F-1: the surface (docs/specs/2026-11-05-f-surface.md section 3). The two structs are Linux's
 * fb_var_screeninfo (160 bytes) and fb_fix_screeninfo (80 bytes), as x86-64 lays them out. */
struct fb_var {
    uint32_t xres, yres, xres_virtual, yres_virtual, xoffset, yoffset, bits_per_pixel, grayscale;
    uint32_t red[3], green[3], blue[3], transp[3];
    uint32_t rest[20];
};
struct fb_fix {
    char id[16];
    unsigned long smem_start;
    uint32_t smem_len, type, type_aux, visual;
    uint16_t xpanstep, ypanstep, ywrapstep;
    uint32_t line_length;
    unsigned long mmio_start;
    uint32_t mmio_len, accel;
    uint16_t capabilities, reserved[2];
};

static int t_fb(void)
{
    struct fb_var v;
    struct fb_fix f;
    int fd = open("/dev/fb0", O_RDWR);
    uint8_t *p;
    if (fd < 0) {
        printf("fb: open: %s\n", strerror(errno));
        return 1;
    }
    if (ioctl(fd, 0x4600, &v) < 0 || ioctl(fd, 0x4602, &f) < 0) {
        printf("fb: ioctl: %s\n", strerror(errno));
        return 1;
    }
    printf("fb: %s %ux%u stride %u bpp %u red %u green %u blue %u len %u\n", f.id, v.xres, v.yres, f.line_length,
           v.bits_per_pixel, v.red[0], v.green[0], v.blue[0], f.smem_len);
    if (read(fd, &v, 1) != -1 || errno != EINVAL || lseek(fd, 0, SEEK_SET) != -1 || errno != EINVAL) {
        printf("fb: read or lseek did not refuse\n");
        return 1;
    }
    p = mmap(0, f.smem_len, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    if (p == MAP_FAILED) {
        printf("fb: mmap: %s\n", strerror(errno));
        return 1;
    }
    for (uint32_t y = 0; y < v.yres; y++) {
        uint32_t *row = (uint32_t *)(p + (size_t)y * f.line_length);
        for (uint32_t x = 0; x < v.xres; x++) {
            uint32_t r = x * 255u / (v.xres - 1u), g = y * 255u / (v.yres - 1u), b = (x ^ y) & 255u;
            row[x] = (r << 16) | (g << 8) | b;
        }
    }
    printf("fb: drew %ux%u, pixel (1, 2) %08x\n", v.xres, v.yres, ((uint32_t *)(p + 2u * f.line_length))[1]);
    if (munmap(p, f.smem_len) != 0 || close(fd) != 0) return 1;
    return 0;
}

/* F-2: the input stream (section 4): /dev/input/event0, one input_event (24 bytes) per read, until
 * three keys were pressed and released and every EV_SYN after them was read; then a non-blocking
 * open must say EAGAIN. */
struct in_event {
    uint64_t sec, usec;
    uint16_t type, code;
    int32_t value;
};

static int t_keys(void)
{
    struct in_event ev;
    int fd = open("/dev/input/event0", O_RDONLY), nb, presses = 0, releases = 0, syn = 0;
    if (fd < 0) {
        printf("keys: open: %s\n", strerror(errno));
        return 1;
    }
    while (presses < 3 || releases < 3 || syn < presses + releases) {
        ssize_t n = read(fd, &ev, sizeof ev);
        if (n != (ssize_t)sizeof ev) {
            printf("keys: read %ld: %s\n", (long)n, strerror(errno));
            return 1;
        }
        if (ev.type == 1) {
            printf("key %u %d\n", ev.code, ev.value);
            if (ev.value) presses++;
            else releases++;
        } else if (ev.type == 0) {
            syn++;
        }
    }
    printf("syn %d\n", syn);
    nb = open("/dev/input/event0", O_RDONLY | O_NONBLOCK);
    if (nb < 0 || read(nb, &ev, sizeof ev) != -1 || errno != EAGAIN) {
        printf("keys: a non-blocking read with nothing queued did not say EAGAIN\n");
        return 1;
    }
    printf("keys: nothing more queued, EAGAIN\n");
    close(nb);
    close(fd);
    return 0;
}

/* F-3: the mouse on the same stream: reads until two buttons were pressed and released, printing each
 * button event and, at the end, the sum of the relative motion and the EV_SYN count. */
static int t_mouse(void)
{
    struct in_event ev;
    int fd = open("/dev/input/event0", O_RDONLY), presses = 0, releases = 0, syn = 0;
    long x = 0, y = 0;
    if (fd < 0) {
        printf("mouse: open: %s\n", strerror(errno));
        return 1;
    }
    while (presses < 2 || releases < 2 || syn < presses + releases + (x != 0 || y != 0)) {
        ssize_t n = read(fd, &ev, sizeof ev);
        if (n != (ssize_t)sizeof ev) {
            printf("mouse: read %ld: %s\n", (long)n, strerror(errno));
            return 1;
        }
        if (ev.type == 2 && ev.code == 0) x += ev.value;
        else if (ev.type == 2 && ev.code == 1) y += ev.value;
        else if (ev.type == 1) {
            printf("button %u %d\n", ev.code, ev.value);
            if (ev.value) presses++;
            else releases++;
        } else if (ev.type == 0) syn++;
    }
    printf("rel x %ld y %ld, syn %d\n", x, y, syn);
    close(fd);
    return 0;
}

/* P-0: directories. Each call's result and errno as Linux gives them, in the image's root: make,
 * walk, open by a directory descriptor, move, refuse, remove; the working directory through
 * chdir, fchdir, fork and a removed directory. getcwd prints the path from the root (the oracle
 * reads its own temporary root as "/"). Leaves the root as it found it. */
static void said(const char *what, long r)
{
    printf("%-34s %ld errno %d\n", what, r, r < 0 ? errno : 0);
    errno = 0;
}

static void cwd_line(void)
{
    char buf[256];
    if (getcwd(buf, sizeof buf)) printf("getcwd %s\n", buf);
    else said("getcwd", -1);
}

static int t_dirs(void)
{
    char buf[64];
    struct stat st;
    said("mkdir d1", mkdir("d1", 0755));
    said("mkdir d1 again", mkdir("d1", 0755));
    said("mkdir d1/d2/", mkdir("d1/d2/", 0755));
    said("mkdir nope/d3", mkdir("nope/d3", 0755));
    said("mkdir hello.txt/d", mkdir("hello.txt/d", 0755));
    int fd = open("d1/d2/f", O_WRONLY | O_CREAT | O_TRUNC, 0644);
    said("open d1/d2/f", fd < 0 ? -1 : 0);
    said("write", write(fd, "nested\n", 7));
    close(fd);
    said("open hello.txt/", open("hello.txt/", O_RDONLY));
    said("open d1 for writing", open("d1", O_WRONLY));
    said("open hello.txt O_DIRECTORY", open("hello.txt", O_RDONLY | O_DIRECTORY));
    int dfd = open("d1", O_RDONLY | O_DIRECTORY);
    said("open d1 O_DIRECTORY", dfd < 0 ? -1 : 0);
    fd = openat(dfd, "d2/f", O_RDONLY);
    ssize_t n = read(fd, buf, sizeof buf);
    close(fd);
    printf("openat d1 d2/f: %.*s", (int)(n > 0 ? n : 0), buf);
    said("mkdirat d1 d4", mkdirat(dfd, "d4", 0755));
    said("renameat d1 d2/f d1 d4/g", renameat(dfd, "d2/f", dfd, "d4/g"));
    said("stat d1/d4/g", stat("d1/d4/g", &st) == 0 ? (long)st.st_size : -1);
    said("fstatat d1 d4 is a directory", fstatat(dfd, "d4", &st, 0) == 0 ? (long)S_ISDIR(st.st_mode) : -1);
    said("stat d1/./d4/../d2", stat("d1/./d4/../d2", &st) == 0 ? (long)S_ISDIR(st.st_mode) : -1);
    said("rmdir d1", rmdir("d1"));
    said("rmdir d1/.", rmdir("d1/."));
    said("rename d1 d1/d4/x", rename("d1", "d1/d4/x"));
    said("rename d1/d4/g d1/d2", rename("d1/d4/g", "d1/d2"));
    said("rename d1/d2 hello.txt", rename("d1/d2", "hello.txt"));
    said("unlinkat d1 d4 AT_REMOVEDIR", unlinkat(dfd, "d4", AT_REMOVEDIR));
    said("unlink d1/d4", unlink("d1/d4"));
    said("chdir hello.txt", chdir("hello.txt"));
    said("chdir d1/d4", chdir("d1/d4"));
    cwd_line();
    fd = open("g", O_RDONLY);
    n = read(fd, buf, sizeof buf);
    close(fd);
    printf("read g: %.*s", (int)(n > 0 ? n : 0), buf);
    said("chdir ../..", chdir("../.."));
    cwd_line();
    said("getcwd into 1 byte", getcwd(buf, 1) ? 0 : -1);
    said("fchdir d1", fchdir(dfd));
    cwd_line();
    fflush(stdout);
    pid_t c = fork();
    if (c == 0) {
        said("child chdir d2", chdir("d2"));
        cwd_line();
        fflush(stdout);
        _exit(0);
    }
    waitpid(c, NULL, 0);
    printf("after the child: ");
    cwd_line();
    said("chdir ..", chdir(".."));
    said("rename d1/d2 d1/d4/d2", rename("d1/d2", "d1/d4/d2"));
    said("rename d1/d4/g d1/d4/d2/h", rename("d1/d4/g", "d1/d4/d2/h"));
    said("stat d1/d4/d2/h", stat("d1/d4/d2/h", &st) == 0 ? (long)st.st_size : -1);
    said("mkdir d5", mkdir("d5", 0755));
    said("chdir d5", chdir("d5"));
    said("rmdir ../d5", rmdir("../d5"));
    said("getcwd in a removed directory", getcwd(buf, sizeof buf) ? 0 : -1);
    said("create in a removed directory", open("x", O_WRONLY | O_CREAT, 0644));
    said("chdir ..", chdir(".."));
    cwd_line();
    said("unlink d1/d4/d2/h", unlink("d1/d4/d2/h"));
    said("rmdir d1/d4/d2", rmdir("d1/d4/d2"));
    said("unlinkat d1 d4 AT_REMOVEDIR", unlinkat(dfd, "d4", AT_REMOVEDIR));
    close(dfd);
    said("rmdir d1", rmdir("d1"));
    said("access d1", access("d1", F_OK));
    return 0;
}

/* mlimit (M-1, docs/specs/2026-11-06-m-memory.md): the one limit. RLIMIT_AS is the quota; one map of 16 MiB and a
 * break 40 MiB up are granted and touched; maps of 16 MiB are taken until the call refuses, which is -ENOMEM and
 * nothing else; given back, the pool grants again. The maps are 16 MiB so the count is the quota's, not the
 * kernel's own use of the pool. Under Linux: prlimit --as=62914560 ./mlimit, as tools/check-user.py runs it. */
static int t_limit(void)
{
    struct rlimit r;
    if (getrlimit(RLIMIT_AS, &r) != 0) return 1;
    printf("mlimit: as MiB %lu\n", (unsigned long)(r.rlim_cur >> 20));
    size_t big = (size_t)16 << 20;
    uint8_t *m = mmap(NULL, big, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (m == MAP_FAILED) return 2;
    unsigned sum = 0;
    for (size_t k = 0; k < big; k += 4096u) m[k] = (uint8_t)(k >> 12);
    for (size_t k = 0; k < big; k += 4096u) sum += m[k];
    munmap(m, big);
    printf("mlimit: map MiB %zu touched, sum %u\n", big >> 20, sum);
    uintptr_t top = (uintptr_t)syscall(SYS_brk, 0);
    size_t grow = (size_t)40 << 20;
    if ((uintptr_t)syscall(SYS_brk, top + grow) != top + grow) return 3;
    volatile uint8_t *last = (uint8_t *)(top + grow - 1);
    *last = 7;
    int seen = *last;
    if ((uintptr_t)syscall(SYS_brk, top) != top) return 4;
    printf("mlimit: brk up MiB %zu, last byte %d, down\n", grow >> 20, seen);
    void *chunk[8];
    int n = 0;
    size_t cs = (size_t)16 << 20;
    errno = 0;
    while (n < 8) {
        void *c = mmap(NULL, cs, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
        if (c == MAP_FAILED) break;
        chunk[n++] = c;
    }
    printf("mlimit: full after %d maps of 16 MiB, errno %s\n", n, errno == ENOMEM ? "ENOMEM" : "other");
    for (int i = 0; i < n; i++) munmap(chunk[i], cs);
    void *again = mmap(NULL, cs, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    printf("mlimit: after unmap, 16 MiB %s\n", again == MAP_FAILED ? "refused" : "granted");
    if (again != MAP_FAILED) munmap(again, cs);
    return 0;
}

/* mpoll (E-1, docs/specs/2026-11-06-e-editor.md section 4a): poll(2) and ppoll(2) on a pipe's ends, a file, a
 * negative and a closed descriptor, a timeout with nothing ready and a sleep with no descriptors. Linux waits out
 * the timeouts in real time; Daphnis expires them when every process waits, and the clock moves on as far. */
static int t_poll(void)
{
    int p[2], q[2];
    char c = 'x';
    if (pipe(p) != 0 || pipe(q) != 0) return 1;
    struct pollfd f[2] = {{p[0], POLLIN, 0}, {p[1], POLLOUT, 0}};
    int n = poll(f, 1, 0);
    printf("mpoll: empty %d revents %x\n", n, f[0].revents);
    if (write(p[1], &c, 1) != 1) return 1;
    n = poll(f, 2, -1);
    printf("mpoll: one byte %d revents %x %x\n", n, f[0].revents, f[1].revents);
    if (read(p[0], &c, 1) != 1) return 1;
    struct timespec a, b;
    clock_gettime(CLOCK_MONOTONIC, &a);
    n = poll(f, 1, 100);
    clock_gettime(CLOCK_MONOTONIC, &b);
    long ms = (long)(b.tv_sec - a.tv_sec) * 1000 + (b.tv_nsec - a.tv_nsec) / 1000000;
    printf("mpoll: timeout %d revents %x, 100 ms passed %s\n", n, f[0].revents, ms >= 100 ? "yes" : "no");
    n = poll(NULL, 0, 50);
    printf("mpoll: sleep %d\n", n);
    close(p[1]);
    n = poll(f, 1, -1);
    printf("mpoll: no writer %d revents %x\n", n, f[0].revents);
    close(q[0]);
    struct pollfd w = {q[1], POLLOUT, 0};
    n = poll(&w, 1, 0);
    printf("mpoll: no reader %d revents %x\n", n, w.revents);
    int fd = open("hello.txt", O_RDONLY);
    struct pollfd g[3] = {{fd, POLLIN | POLLOUT, 0}, {-1, POLLIN, 7}, {13, POLLIN, 0}};
    n = poll(g, 3, 0);
    printf("mpoll: file, negative, closed %d revents %x %x %x\n", n, g[0].revents, g[1].revents, g[2].revents);
    struct timespec t = {0, 20000000};
    n = ppoll(f, 1, &t, NULL);
    printf("mpoll: ppoll %d revents %x\n", n, f[0].revents);
    return 0;
}

int main(int argc, char **argv)
{
    const char *name = strrchr(argv[0], '/');
    name = name ? name + 1 : argv[0];
    if (!strcmp(name, "mprintf")) return t_printf(argc, argv);
    if (!strcmp(name, "mmalloc")) return t_malloc(argc, argv);
    if (!strcmp(name, "mbrk")) return t_brk();
    if (!strcmp(name, "mprot")) return t_prot();
    if (!strcmp(name, "mclock")) return t_clock();
    if (!strcmp(name, "mtls")) return t_tls(argc, argv);
    if (!strcmp(name, "ssea") || !strcmp(name, "sseb")) return t_sse(argc, argv);
    if (!strcmp(name, "mcat")) return t_cat();
    if (!strcmp(name, "mls")) return t_ls();
    if (!strcmp(name, "mwrite")) return t_write();
    if (!strcmp(name, "mfd")) return t_fd();
    if (!strcmp(name, "mstdin")) return t_stdin();
    if (!strcmp(name, "mlitter")) return t_litter();
    if (!strcmp(name, "mfork")) return t_fork();
    if (!strcmp(name, "mpipe")) return t_pipe();
    if (!strcmp(name, "mexec")) return t_exec();
    if (!strcmp(name, "mpipeline")) return t_pipeline();
    if (!strcmp(name, "mfb")) return t_fb();
    if (!strcmp(name, "mkeys")) return t_keys();
    if (!strcmp(name, "mmouse")) return t_mouse();
    if (!strcmp(name, "mdirs")) return t_dirs();
    if (!strcmp(name, "mlimit")) return t_limit();
    if (!strcmp(name, "mpoll")) return t_poll();
    printf("musltest: run me as one of mprintf mmalloc mbrk mprot mclock mtls ssea sseb mcat mls mwrite mfd mstdin mlitter mfork mpipe mexec mpipeline mfb mkeys mmouse mdirs mlimit mpoll\n");
    return 64;
}
