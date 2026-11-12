/* user/c/mfacts.c: KF-3b's probe (docs/specs/2026-11-11-kf-facts.md section 2). Under Daphnis it checks who sees a
 * process record of facts(2, slot, buf, n), one line each, `mfacts: WHAT = RESULT`: as the desk (uid 0) it sees
 * itself and its children; a child that login made uid 1000 sees itself and its own child, and reads the desk's
 * slot, its parent's, as the same bytes and the same return value as a slot with no process; a second child, uid
 * 1001, reads the first child's slot the same way; a third, uid 1002 logged in as a Parent (DN-69 item 5), sees
 * every record; KF edition 14: kill(pid, 0), getpgid and getsid of a process the caller may not see answer -ESRCH, as
 * for no process (a Parent that sees it and may not signal it, Linux's -EPERM); and the call's bounds. check-tiler.sh
 * compares the lines with
 * tests/expected/kf-mfacts.out. On Linux the Daphnis calls are -ENOSYS. Its own static musl binary
 * (user/c/build.sh, ruling DU-2 A). Exit status 0. */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <unistd.h>

#define NR_LOGIN 1003
#define NR_FACTS 1007
#define FBIO_TILER 0x4680
#define DISK 1L
#define PARENT (1L << 32)   /* DN-69 item 5: login's word that the account is a Parent */
#define REC 96   /* KF-R1: the CPU time in ticks follows the 88 bytes of KF-3b */

static long call(long nr, long a, long b, long c, long d)
{
    long r = syscall(nr, a, b, c, d);
    return r < 0 ? -errno : r;
}

static void show(const char *what, long r)
{
    printf("mfacts: %s = %ld\n", what, r);
    fflush(stdout);
}

static unsigned long word(const unsigned char *b, int at)
{
    unsigned long v;
    memcpy(&v, b + at, 8);
    return v;
}

/* The slot whose record names pid, or -1; *seen counts the records that are not empty, *slots the slots. */
static long find(long pid, long *seen, long *slots)
{
    unsigned char b[REC];
    long at = -1, n = 0, id = 0;
    for (;; id++) {
        long r = call(NR_FACTS, 2, id, (long)b, REC);
        if (r != REC) break;
        if (word(b, 24) != 0) {
            n++;
            if ((long)word(b, 0) == pid) at = id;
        }
    }
    if (seen) *seen = n;
    if (slots) *slots = id;
    return at;
}

/* 1 when slot id reads, for this caller, exactly as the slot `none`, which holds no process: the same return value
 * and the same bytes over buffers that held different bytes before. */
static long same_as_empty(long id, long none)
{
    unsigned char a[REC], e[REC];
    memset(a, 0x11, REC);
    memset(e, 0xEE, REC);
    long ra = call(NR_FACTS, 2, id, (long)a, REC);
    long re = call(NR_FACTS, 2, none, (long)e, REC);
    return ra == re && memcmp(a, e, REC) == 0;
}

int main(void)
{
    unsigned char b[REC];
    long seen = 0, slots = 0;
    int fd = open("/dev/fb0", O_RDWR);
    if (fd < 0) {
        show("open /dev/fb0 (no framebuffer: nothing checked)", -errno);
        return 0;
    }
    long t = ioctl(fd, FBIO_TILER, 0);
    show("FBIO_TILER as uid 0 (want 0)", t < 0 ? -errno : t);
    long me = find(getpid(), &seen, &slots);
    show("desk: slots in the table (want 64)", slots);
    show("desk: finds its own record (want 1)", me >= 0);
    show("desk: records it sees, itself alone (want 1)", seen);
    long none = -1;
    for (long id = 0; id < slots && none < 0; id++) {
        if (call(NR_FACTS, 2, id, (long)b, REC) == REC && word(b, 24) == 0) none = id;
    }
    show("desk: a slot with no process exists (want 1)", none >= 0);
    show("slot 64, past the table (want -ENOENT -2)", call(NR_FACTS, 2, 64, (long)b, REC));
    show("slot -1 (want -ENOENT -2)", call(NR_FACTS, 2, -1, (long)b, REC));
    show("kind 9 (want -EINVAL -22)", call(NR_FACTS, 9, 0, (long)b, REC));
    show("n 0 and no buffer: the record's size (want 96)", call(NR_FACTS, 2, me, 0, 0));
    show("a kernel address (want -EFAULT -14)", call(NR_FACTS, 2, me, (long)0xffffffff80000000UL, REC));

    int go1[2], up1[2], go2[2];
    if (pipe(go1) < 0 || pipe(up1) < 0 || pipe(go2) < 0) return 1;
    pid_t c1 = fork();
    if (c1 == 0) {
        char x;
        show("child 1: login uid 1000 (want 0)", call(NR_LOGIN, 1000, 100, DISK, 0));
        long mine = find(getpid(), &seen, NULL);
        show("child 1: finds its own record (want 1)", mine >= 0);
        show("child 1: records it sees, itself alone (want 1)", seen);
        show("child 1: its parent's slot, the desk's, reads as a slot with no process (want 1)", same_as_empty(me, none));
        memset(b, 0x77, REC);
        long r = call(NR_FACTS, 2, me, (long)b, REC);
        long zero = 1;
        for (int i = 0; i < REC; i++) zero = zero && b[i] == 0;
        show("child 1: that read returns the record's size (want 96)", r);
        show("child 1: and writes 96 zero bytes (want 1)", zero);
        pid_t g = fork();
        if (g == 0) {
            find(getpid(), &seen, NULL);
            show("grandchild, uid 1000: records it sees, itself and child 1 (want 2)", seen);
            _exit(0);
        }
        waitpid(g, NULL, 0);
        if (write(up1[1], &mine, sizeof mine) != (ssize_t)sizeof mine) _exit(1);   /* tell the desk our slot */
        if (read(go1[0], &x, 1) != 1) _exit(1);                                   /* live until child 2 has looked */
        _exit(0);
    }
    long slot1 = -1;
    if (read(up1[0], &slot1, sizeof slot1) != (ssize_t)sizeof slot1) return 1;
    memset(b, 0, REC);
    long r1 = call(NR_FACTS, 2, slot1, (long)b, REC);
    show("desk: reads child 1's record (want 96)", r1);
    show("desk: child 1's uid in it (want 1000)", (long)word(b, 16));
    show("desk: child 1's parent pid is the desk's (want 1)", (long)word(b, 8) == (long)getpid());
    find(getpid(), &seen, NULL);
    show("desk: records it sees, itself and child 1 (want 2)", seen);
    pid_t c2 = fork();
    if (c2 == 0) {
        show("child 2: login uid 1001 (want 0)", call(NR_LOGIN, 1001, 100, DISK, 0));
        find(getpid(), &seen, NULL);
        show("child 2: records it sees, itself alone (want 1)", seen);
        show("child 2: child 1's slot, another user's, reads as a slot with no process (want 1)", same_as_empty(slot1, none));
        show("child 2: the desk's slot reads as a slot with no process (want 1)", same_as_empty(me, none));
        show("child 2: kill(child 1, 0), another account's (want -ESRCH -3)", call(SYS_kill, c1, 0, 0, 0));
        show("child 2: kill(the desk, 0) (want -ESRCH -3)", call(SYS_kill, getppid(), 0, 0, 0));
        show("child 2: getpgid(child 1) (want -ESRCH -3)", call(SYS_getpgid, c1, 0, 0, 0));
        show("child 2: getsid(child 1) (want -ESRCH -3)", call(SYS_getsid, c1, 0, 0, 0));
        show("child 2: kill(itself, 0) (want 0)", call(SYS_kill, getpid(), 0, 0, 0));
        _exit(0);
    }
    waitpid(c2, NULL, 0);
    pid_t c3 = fork();
    if (c3 == 0) {
        show("child 3: login with an unknown bit (want -EINVAL -22)", call(NR_LOGIN, 1002, 100, DISK | (1L << 33), 0));
        show("child 3: login uid 1002 as a Parent (want 0)", call(NR_LOGIN, 1002, 100, DISK | PARENT, 0));
        find(getpid(), &seen, NULL);
        show("child 3, a Parent: records it sees, the desk, child 1 and itself (want 3)", seen);
        memset(b, 0, REC);
        show("child 3: reads child 1's record (want 96)", call(NR_FACTS, 2, slot1, (long)b, REC));
        show("child 3: child 1's uid in it (want 1000)", (long)word(b, 16));
        memset(b, 0, REC);
        call(NR_FACTS, 2, me, (long)b, REC);
        show("child 3: the desk's record is there, uid 0 (want 1)", word(b, 24) != 0 && word(b, 16) == 0);
        show("child 3: kill(child 1, 0), a Child's it sees (want -EPERM -1)", call(SYS_kill, c1, 0, 0, 0));
        show("child 3: getpgid(child 1) finds it (want 1)", call(SYS_getpgid, c1, 0, 0, 0) > 0);
        _exit(0);
    }
    waitpid(c3, NULL, 0);
    if (write(go1[1], "x", 1) != 1) return 1;
    waitpid(c1, NULL, 0);
    find(getpid(), &seen, NULL);
    show("desk: records it sees once both are waited for (want 1)", seen);
    (void)go2;
    show("done", 0);
    return 0;
}
