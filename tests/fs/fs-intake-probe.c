/* tests/fs/fs-intake-probe.c: the guest side of the filesystem intake's regression targets 1 to 8
 * (docs/superpowers/specs/2026-11-09-filesystem-security-intake.md; FSP-1 A, FSP-2 A). tools/check-fs-intake.py adds
 * it to a disposable initrd as /bin/fsprobe and types `grant disk fsprobe MODE` in each account's session.
 *
 * Every line goes to /home/<account>/fsprobe-MODE.txt as soon as it is known (one write each, no buffering), so a
 * crash keeps what came before it. A line is `T<n> <check> ok|bad <what was seen>`; the last is `end <n> checks <f>
 * bad`. A denial is ok only when the call failed with an expected errno and the object's bytes and metadata are the
 * same as before it. The host reads the file back with debugfs; nothing here is trusted to judge the volume's bytes
 * alone (the host hashes ada's seeds itself).
 *
 * Modes: seed (ada: the objects sam must not reach), sam (targets 1 to 6 and 8 as sam), cross (ada: sam's
 * home), admin (ada under `kern`: the permitted chown), home (target 7: the home this session runs in).
 * No fault injection, no bypass: the probe uses the ordinary calls an account has.
 */
#define _GNU_SOURCE
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/uio.h>
#include <sys/wait.h>
#include <unistd.h>

static int out = -1;          /* the result file, opened while the disk grant is held */
static int nchk, nbad;
static char home[64];

static void line(const char *fmt, ...) {
    char b[512];
    va_list ap;
    va_start(ap, fmt);
    int n = vsnprintf(b, sizeof b - 1, fmt, ap);
    va_end(ap);
    if (n < 0) { return; }
    if (n > (int)sizeof b - 2) { n = (int)sizeof b - 2; }
    b[n++] = '\n';
    if (out >= 0) { (void)!write(out, b, (size_t)n); }
    (void)!write(2, b, (size_t)n);
}

static void verdict(int t, const char *name, int ok, const char *fmt, ...) {
    char d[384];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(d, sizeof d, fmt, ap);
    va_end(ap);
    nchk++;
    if (!ok) { nbad++; }
    line("T%d %s %s %s", t, name, ok ? "ok" : "bad", d);
}

/* An object's state: its bytes (when readable) and its metadata. */
struct snap {
    int have_stat, have_bytes;
    struct stat st;
    unsigned char *bytes;
    size_t n;
};

static void take(struct snap *s, const char *p) {
    memset(s, 0, sizeof *s);
    s->have_stat = lstat(p, &s->st) == 0;
    int fd = open(p, O_RDONLY | O_NOFOLLOW);
    if (fd < 0) { return; }
    size_t cap = 1 << 16;
    s->bytes = malloc(cap);
    for (;;) {
        if (s->n == cap) {
            cap *= 2;
            s->bytes = realloc(s->bytes, cap);
        }
        ssize_t r = read(fd, s->bytes + s->n, cap - s->n);
        if (r <= 0) { break; }
        s->n += (size_t)r;
    }
    close(fd);
    s->have_bytes = 1;
}

static void drop(struct snap *s) { free(s->bytes); s->bytes = NULL; }

/* Whether p is as s found it: the same inode, mode, owner, size, link count and modification time, and (when they
 * were readable) the same bytes. */
static int same(const struct snap *s, const char *p) {
    struct snap now;
    take(&now, p);
    int ok = now.have_stat == s->have_stat;
    if (ok && s->have_stat) {
        ok = now.st.st_ino == s->st.st_ino && now.st.st_mode == s->st.st_mode && now.st.st_uid == s->st.st_uid &&
             now.st.st_gid == s->st.st_gid && now.st.st_size == s->st.st_size &&
             now.st.st_nlink == s->st.st_nlink && now.st.st_mtim.tv_sec == s->st.st_mtim.tv_sec &&
             now.st.st_mtim.tv_nsec == s->st.st_mtim.tv_nsec;
    }
    if (ok && s->have_bytes) { ok = now.have_bytes && now.n == s->n && memcmp(now.bytes, s->bytes, s->n) == 0; }
    drop(&now);
    return ok;
}

static int in(int e, const int *set);

/* FSP-2 A's reads through a held descriptor: its size and bytes from the start, without opening the path again. */
struct fsnap {
    off_t size;
    unsigned char b[256];
    ssize_t n;
};

static void take_fd(struct fsnap *s, int fd) {
    struct stat st;
    s->size = fstat(fd, &st) == 0 ? st.st_size : -1;
    lseek(fd, 0, SEEK_SET);
    s->n = read(fd, s->b, sizeof s->b);
}

static int same_fd(const struct fsnap *s, int fd) {
    struct fsnap now;
    take_fd(&now, fd);
    return now.size == s->size && now.n == s->n && (s->n <= 0 || memcmp(now.b, s->b, (size_t)s->n) == 0);
}

/* A denial through a held descriptor: rc failed with an errno in want and the descriptor's bytes are as before. */
static void deny_fd(int t, const char *name, long rc, int e, const int *want, const struct fsnap *s, int fd) {
    int kept = same_fd(s, fd);
    verdict(t, name, rc < 0 && in(e, want) && kept, "rc=%ld errno=%d kept=%d", rc, rc < 0 ? e : 0, kept);
}

static int in(int e, const int *set) {
    for (; *set; set++) {
        if (*set == e) { return 1; }
    }
    return 0;
}

static const int E_ACCES[] = {EACCES, 0};
static const int E_PERM[] = {EPERM, 0};
static const int E_BADF[] = {EBADF, 0};
static const int E_BADF_INVAL[] = {EBADF, EINVAL, 0};
static const int E_LINK[] = {EPERM, EACCES, EXDEV, 0};          /* Linux's protected_hardlinks, or another volume */
static const int E_REPLACE[] = {EACCES, EXDEV, 0};               /* a rename across volumes cannot replace either */
static const int E_ACCES_ROFS[] = {EACCES, EROFS, 0};            /* a path write with no disk grant is EROFS today */

/* A denial: rc failed with an errno in want, and every object in objs is as its snapshot. */
static void deny(int t, const char *name, long rc, int e, const int *want, struct snap *sn, const char **objs, int k) {
    int kept = 1;
    for (int i = 0; i < k; i++) { kept = kept && same(&sn[i], objs[i]); }
    verdict(t, name, rc < 0 && in(e, want) && kept, "rc=%ld errno=%d kept=%d", rc, rc < 0 ? e : 0, kept);
}

#define DENY1(t, name, call, want, path)                                                                               \
    do {                                                                                                               \
        struct snap s_[1];                                                                                             \
        const char *o_[1] = {path};                                                                                    \
        take(&s_[0], path);                                                                                            \
        errno = 0;                                                                                                     \
        long r_ = (long)(call);                                                                                        \
        int e_ = errno;                                                                                                \
        deny(t, name, r_, e_, want, s_, o_, 1);                                                                        \
        drop(&s_[0]);                                                                                                  \
    } while (0)

/* A call an account must be able to make: rc is not negative. */
static void allow(int t, const char *name, long rc) {
    int e = errno;
    verdict(t, name, rc >= 0, "rc=%ld errno=%d", rc, rc < 0 ? e : 0);
}

static int put(const char *p, const char *text, mode_t m) {
    int fd = open(p, O_WRONLY | O_CREAT | O_TRUNC, m);
    if (fd < 0) { return -1; }
    ssize_t n = write(fd, text, strlen(text));
    close(fd);
    return n == (ssize_t)strlen(text) ? 0 : -1;
}

static int copy(const char *from, const char *to, mode_t m) {
    struct snap s;
    take(&s, from);
    if (!s.have_bytes) { drop(&s); return -1; }
    int fd = open(to, O_WRONLY | O_CREAT | O_TRUNC, m);
    int ok = fd >= 0 && write(fd, s.bytes, s.n) == (ssize_t)s.n;
    if (fd >= 0) { close(fd); }
    drop(&s);
    return ok ? 0 : -1;
}

/* fork, execve p, the child's exit status (or -errno of the exec, or -1000 for a signal). */
static int run(const char *p) {
    int pfd[2];
    if (pipe(pfd) < 0) { return -1000; }
    pid_t c = fork();
    if (c == 0) {
        close(pfd[0]);
        char *av[] = {(char *)p, NULL};
        char *ev[] = {NULL};
        execve(p, av, ev);
        int e = errno;
        (void)!write(pfd[1], &e, sizeof e);
        _exit(127);
    }
    close(pfd[1]);
    int e = 0;
    ssize_t got = read(pfd[0], &e, sizeof e);
    close(pfd[0]);
    int st = 0;
    waitpid(c, &st, 0);
    if (got == (ssize_t)sizeof e) { return -e; }
    return WIFEXITED(st) ? WEXITSTATUS(st) : -1000;
}

static long drop_grants(void) { return syscall(1000, 0UL); }   /* Daphnis's grant_set(0): every grant dropped */

/* ---------- target 1: /bin/authd from an ordinary account ---------- */
static void t1(void) {
    const char *a = "/bin/authd";
    DENY1(1, "open-write-authd", open(a, O_WRONLY), E_ACCES, a);
    DENY1(1, "open-trunc-authd", open(a, O_RDWR | O_TRUNC), E_ACCES, a);
    DENY1(1, "truncate-authd", truncate(a, 0), E_ACCES, a);
    DENY1(1, "unlink-authd", unlink(a), E_ACCES, a);
    DENY1(1, "rename-authd-away", rename(a, "/bin/authd.old"), E_ACCES, a);
    DENY1(1, "chmod-authd", chmod(a, 0777), E_PERM, a);
    DENY1(1, "mkdir-in-bin", mkdir("/bin/fsprobe.d", 0700), E_ACCES, "/bin/fsprobe.d");
    char al[96];
    snprintf(al, sizeof al, "%s/authd.alias", home);
    unlink(al);
    allow(1, "symlink-alias", symlink(a, al));
    DENY1(1, "open-write-symlink-alias", open(al, O_WRONLY), E_ACCES, a);
    DENY1(1, "open-trunc-symlink-alias", open(al, O_WRONLY | O_TRUNC), E_ACCES, a);
    {   /* a hard link from a writable ramfs directory, when there is one; else from the home (another volume) */
        char hl[96];
        snprintf(hl, sizeof hl, "%s", access("/tmp", W_OK) == 0 ? "/tmp/authd.link" : "/bin/authd.link");
        unlink(hl);
        struct snap s[1];
        const char *o[1] = {a};
        take(&s[0], a);
        errno = 0;
        long r = link(a, hl);
        int e = errno;
        if (r == 0) {   /* the link stands: no write through it */
            errno = 0;
            long w = open(hl, O_WRONLY | O_TRUNC);
            e = errno;
            deny(1, "open-trunc-hard-link", w, e, E_ACCES, s, o, 1);
            unlink(hl);
        } else {
            deny(1, "hard-link-authd", r, e, E_LINK, s, o, 1);
        }
        drop(&s[0]);
    }
    {   /* replacing the path: a file of the account's renamed over /bin/authd */
        char ev[96];
        snprintf(ev, sizeof ev, "%s", access("/tmp", W_OK) == 0 ? "/tmp/authd.evil" : "/bin/authd.evil");
        int made = put(ev, "#!/bin/sh\nexit 0\n", 0755) == 0;
        if (!made) {
            snprintf(ev, sizeof ev, "%s/authd.evil", home);
            made = put(ev, "#!/bin/sh\nexit 0\n", 0755) == 0;
        }
        struct snap s[1];
        const char *o[1] = {a};
        take(&s[0], a);
        errno = 0;
        long r = rename(ev, a);
        int e = errno;
        deny(1, "rename-over-authd", made ? r : -1, made ? e : EACCES, E_REPLACE, s, o, 1);
        drop(&s[0]);
        unlink(ev);
    }
    {   /* the containing system directory renamed or removed */
        struct snap s[2];
        const char *o[2] = {"/bin", a};
        take(&s[0], "/bin");
        take(&s[1], a);
        errno = 0;
        long r = rename("/bin", "/bin.old");
        int e = errno;
        deny(1, "rename-bin", r, e, E_ACCES, s, o, 2);
        errno = 0;
        r = rmdir("/bin");
        e = errno;
        deny(1, "rmdir-bin", r, e, E_ACCES, s, o, 2);
        drop(&s[0]);
        drop(&s[1]);
    }
}

/* ---------- target 2: write, writev, truncate, ftruncate and held descriptors; FSP-2 A ---------- */
static void t2(void) {
    const char *a = "/bin/authd";
    int ro = open(a, O_RDONLY);
    allow(2, "open-read-authd", ro);
    if (ro >= 0) {
        struct snap s[1];
        const char *o[1] = {a};
        take(&s[0], a);
        errno = 0;
        long r = write(ro, "x", 1);
        deny(2, "write-read-only-fd", r, errno, E_BADF, s, o, 1);
        struct iovec iv[2] = {{"x", 1}, {"y", 1}};
        errno = 0;
        r = writev(ro, iv, 2);
        deny(2, "writev-read-only-fd", r, errno, E_BADF, s, o, 1);
        errno = 0;
        r = ftruncate(ro, 0);
        deny(2, "ftruncate-read-only-fd", r, errno, E_BADF_INVAL, s, o, 1);
        int d = dup(ro);
        errno = 0;
        r = write(d, "x", 1);
        deny(2, "write-dup-of-read-only-fd", r, errno, E_BADF, s, o, 1);
        close(d);
        errno = 0;
        r = pwrite(ro, "x", 1, 0);
        int e = errno;
        verdict(2, "pwrite-unsupported", r < 0 && (e == ENOSYS || e == EBADF), "rc=%ld errno=%d (ENOSYS today)", r, e);
        errno = 0;
        void *m = mmap(NULL, 4096, PROT_READ | PROT_WRITE, MAP_SHARED, ro, 0);
        e = errno;
        verdict(2, "mmap-shared-unsupported", m == MAP_FAILED && (e == ENODEV || e == EACCES),
                "errno=%d (ENODEV today)", m == MAP_FAILED ? e : 0);
        if (m != MAP_FAILED) { munmap(m, 4096); }
        drop(&s[0]);
        close(ro);
    }
    /* FSP-2 A: a held writable volume descriptor keeps its rights across chmod; once the disk grant is dropped,
     * write, writev, ftruncate and fchmod through it are refused with EACCES and the bytes stay; reads go on. */
    char f[96];
    snprintf(f, sizeof f, "%s/t2.dat", home);
    allow(2, "create-volume-file", put(f, "held descriptor bytes\n", 0644));
    int fd = open(f, O_RDWR);
    allow(2, "open-volume-rdwr", fd);
    if (fd < 0) { return; }
    chmod(f, 0444);   /* FSP-2 A: the descriptor keeps the rights it was opened with */
    lseek(fd, 0, SEEK_SET);
    errno = 0;
    allow(2, "write-held-fd-after-chmod", write(fd, "h", 1));
    chmod(f, 0644);
    int pfd[2];
    if (pipe(pfd) < 0) { return; }
    pid_t c = fork();
    if (c == 0) {   /* the child drops every grant and reports through the pipe; the parent keeps the file */
        close(pfd[0]);
        out = pfd[1];
        nchk = 0;
        nbad = 0;
        long g = drop_grants();
        allow(2, "drop-disk-grant", g);
        struct fsnap s;
        take_fd(&s, fd);
        int d = dup(fd);
        errno = 0;
        long r = ftruncate(fd, 0);
        deny_fd(2, "ftruncate-held-fd-after-drop", r, errno, E_ACCES, &s, fd);
        lseek(fd, 0, SEEK_SET);
        errno = 0;
        r = write(fd, "z", 1);
        deny_fd(2, "write-held-fd-after-drop", r, errno, E_ACCES, &s, fd);
        struct iovec iv[2] = {{"z", 1}, {"w", 1}};
        lseek(fd, 0, SEEK_SET);
        errno = 0;
        r = writev(fd, iv, 2);
        deny_fd(2, "writev-held-fd-after-drop", r, errno, E_ACCES, &s, fd);
        lseek(d, 0, SEEK_SET);
        errno = 0;
        r = write(d, "z", 1);
        deny_fd(2, "write-dup-after-drop", r, errno, E_ACCES, &s, fd);
        struct stat before, after;
        int hb = fstat(fd, &before) == 0;
        errno = 0;
        r = fchmod(fd, 0600);
        int e2 = errno;
        int ha = fstat(fd, &after) == 0;
        verdict(2, "fchmod-held-fd-after-drop", r < 0 && e2 == EACCES && hb && ha && before.st_mode == after.st_mode,
                "rc=%ld errno=%d mode %o -> %o", r, r < 0 ? e2 : 0, hb ? before.st_mode & 07777 : 0,
                ha ? after.st_mode & 07777 : 0);
        errno = 0;
        r = truncate(f, 0);
        deny_fd(2, "truncate-path-after-drop", r, errno, E_ACCES_ROFS, &s, fd);
        char b[8];
        lseek(fd, 0, SEEK_SET);
        r = read(fd, b, sizeof b);
        verdict(2, "read-held-fd-after-drop", r > 0, "rc=%ld", r);
        char tail[32];
        snprintf(tail, sizeof tail, "child %d %d\n", nchk, nbad);
        (void)!write(pfd[1], tail, strlen(tail));
        _exit(0);
    }
    close(pfd[1]);
    /* the child's lines come through the pipe and go on to the file; its counts are added */
    char buf[4096];
    size_t have = 0;
    for (;;) {
        ssize_t r = read(pfd[0], buf + have, sizeof buf - 1 - have);
        if (r <= 0) { break; }
        have += (size_t)r;
        buf[have] = 0;
        char *nl;
        while ((nl = memchr(buf, '\n', have)) != NULL) {
            *nl = 0;
            int ck, bd;
            if (sscanf(buf, "child %d %d", &ck, &bd) == 2) {
                nchk += ck;
                nbad += bd;
            } else {
                line("%s", buf);
            }
            size_t used = (size_t)(nl - buf) + 1;
            memmove(buf, nl + 1, have - used);
            have -= used;
        }
    }
    close(pfd[0]);
    int st = 0;
    waitpid(c, &st, 0);
    verdict(2, "child-ran", WIFEXITED(st) && WEXITSTATUS(st) == 0, "status=%d", st);
    close(fd);
}

/* ---------- target 3: exec, scripts, modes, umask, access masks, traversal on both filesystems ---------- */
static void t3(void) {
    char x[96], sc[96], f[96], d[96], dd[96];
    snprintf(x, sizeof x, "%s/t3.true", home);
    allow(3, "copy-true", copy("/bin/true", x, 0755));
    { int r = run(x); verdict(3, "exec-0755-own", r == 0, "status=%d", r); }
    chmod(x, 0644);
    { int r = run(x); verdict(3, "exec-0644-refused", r == -EACCES, "status=%d", r); }
    chmod(x, 0700);
    { int r = run(x); verdict(3, "exec-0700-own", r == 0, "status=%d", r); }
    snprintf(sc, sizeof sc, "%s/t3.sh", home);
    put(sc, "#!/bin/sh\nexit 3\n", 0644);
    { int r = run(sc); verdict(3, "exec-script-0644-refused", r == -EACCES, "status=%d", r); }
    chmod(sc, 0755);
    { int r = run(sc); line("T3 exec-script-0755 info status=%d (3 when scripts run; recorded, not judged)", r); }
    { char b[128]; ssize_t n = readlink("/proc/self/exe", b, sizeof b - 1); b[n > 0 ? n : 0] = 0;
      line("T3 proc-self-exe info rc=%zd |%s| (recorded, not judged)", n, b); }
    /* creation modes and umask: new objects carry the creator's uid and gid */
    snprintf(f, sizeof f, "%s/t3.mode", home);
    unlink(f);
    umask(022);
    put(f, "m\n", 0666);
    struct stat st;
    int ok = stat(f, &st) == 0;
    verdict(3, "create-umask-022", ok && (st.st_mode & 07777) == 0644 && st.st_uid == getuid() && st.st_gid == getgid(),
            "mode=%o uid=%d gid=%d", ok ? st.st_mode & 07777 : 0, ok ? (int)st.st_uid : -1, ok ? (int)st.st_gid : -1);
    unlink(f);
    umask(077);
    put(f, "m\n", 0666);
    ok = stat(f, &st) == 0;
    verdict(3, "create-umask-077", ok && (st.st_mode & 07777) == 0600, "mode=%o", ok ? st.st_mode & 07777 : 0);
    umask(022);
    snprintf(d, sizeof d, "%s/t3.dir", home);
    rmdir(d);
    umask(027);
    mkdir(d, 0777);
    ok = stat(d, &st) == 0;
    verdict(3, "mkdir-umask-027", ok && (st.st_mode & 07777) == 0750 && st.st_uid == getuid(),
            "mode=%o uid=%d", ok ? st.st_mode & 07777 : 0, ok ? (int)st.st_uid : -1);
    umask(022);
    /* the owner class decides for the owner: no bits, no access, uid 0 or not */
    chmod(f, 0400);
    DENY1(3, "owner-0400-write", open(f, O_WRONLY), E_ACCES, f);
    chmod(f, 0200);
    DENY1(3, "owner-0200-read", open(f, O_RDONLY), E_ACCES, f);
    chmod(f, 0077);
    DENY1(3, "owner-0077-read", open(f, O_RDONLY), E_ACCES, f);
    chmod(f, 0600);
    /* access masks */
    errno = 0;
    { long r = access("/bin/authd", W_OK); verdict(3, "access-w-authd", r < 0 && errno == EACCES, "rc=%ld errno=%d", r, errno); }
    { long r = access("/bin/authd", R_OK | X_OK); verdict(3, "access-rx-authd", r == 0, "rc=%ld errno=%d", r, errno); }
    { long r = access(f, R_OK | W_OK); verdict(3, "access-rw-own", r == 0, "rc=%ld errno=%d", r, errno); }
    /* traversal: a directory without search (both filesystems, the account's own) */
    const char *roots[2] = {home, "/tmp"};
    for (int k = 0; k < 2; k++) {
        if (k == 1 && access("/tmp", W_OK) != 0) { line("T3 ramfs-traversal info no writable /tmp; ramfs leg not run"); continue; }
        snprintf(dd, sizeof dd, "%s/t3.nosearch", roots[k]);
        char in1[128];
        snprintf(in1, sizeof in1, "%s/inner", dd);
        mkdir(dd, 0700);
        put(in1, "i\n", 0644);
        chmod(dd, 0600);   /* read, no search */
        DENY1(3, k ? "ramfs-stat-through-0600-dir" : "volume-stat-through-0600-dir", stat(in1, &st), E_ACCES, dd);
        DENY1(3, k ? "ramfs-open-through-0600-dir" : "volume-open-through-0600-dir", open(in1, O_RDONLY), E_ACCES, dd);
        chmod(dd, 0300);   /* search, no read */
        { DIR *dp = opendir(dd); int e = errno; verdict(3, k ? "ramfs-opendir-0300" : "volume-opendir-0300", dp == NULL && e == EACCES, "errno=%d", dp ? 0 : e); if (dp) closedir(dp); }
        { int r = stat(in1, &st); verdict(3, k ? "ramfs-stat-through-0300" : "volume-stat-through-0300", r == 0, "rc=%d", r); }
        chmod(dd, 0700);
        unlink(in1);
        rmdir(dd);
    }
}

/* ---------- target 4: cross-account, as sam against ada's seeds; sam's own work ---------- */
static void t4(void) {
    const char *hs = "/home/ada/secret";
    DENY1(4, "stat-ada-secret", stat(hs, &(struct stat){0}), E_ACCES, "/home/ada");
    DENY1(4, "open-read-ada-secret", open(hs, O_RDONLY), E_ACCES, "/home/ada");
    DENY1(4, "open-write-ada-secret", open(hs, O_WRONLY), E_ACCES, "/home/ada");
    DENY1(4, "create-in-ada-home", open("/home/ada/from-sam", O_WRONLY | O_CREAT, 0644), E_ACCES, "/home/ada");
    DENY1(4, "unlink-ada-secret", unlink(hs), E_ACCES, "/home/ada");
    DENY1(4, "opendir-ada-home", (long)(opendir("/home/ada") ? 0 : -1), E_ACCES, "/home/ada");
    DENY1(4, "chdir-ada-home", chdir("/home/ada"), E_ACCES, "/home/ada");
    char mine[96];
    snprintf(mine, sizeof mine, "%s/t4.mine", home);
    put(mine, "sam's\n", 0600);
    DENY1(4, "rename-over-ada-secret", rename(mine, hs), E_ACCES, "/home/ada");
    DENY1(4, "rename-ada-home", rename("/home/ada", "/home/ada.old"), E_ACCES, "/home/ada");
    /* sam's own work in the home */
    char m2[96];
    snprintf(m2, sizeof m2, "%s/t4.moved", home);
    allow(4, "own-write", put(mine, "sam's work\n", 0600));
    allow(4, "own-read", open(mine, O_RDONLY));
    allow(4, "own-rename", rename(mine, m2));
    allow(4, "own-unlink", unlink(m2));
    char sec[96];
    snprintf(sec, sizeof sec, "%s/secret-sam", home);
    allow(4, "own-secret-for-cross", put(sec, "sam's secret\n", 0600));
    struct stat st;
    int ok = stat(home, &st) == 0;
    verdict(4, "home-0700-owned", ok && (st.st_mode & 07777) == 0700 && st.st_uid == getuid() && st.st_gid == getgid(),
            "mode=%o uid=%d gid=%d", ok ? st.st_mode & 07777 : 0, ok ? (int)st.st_uid : -1, ok ? (int)st.st_gid : -1);
}

/* ---------- target 5: chmod and chown without authority; setuid and setgid refused ---------- */
static void t5(void) {
    char f[96];
    snprintf(f, sizeof f, "%s/t5.file", home);
    put(f, "five\n", 0644);
    DENY1(5, "chown-own-to-uid-0", chown(f, 0, -1), E_PERM, f);
    DENY1(5, "chown-own-to-ada", chown(f, 1000, -1), E_PERM, f);
    DENY1(5, "chgrp-own-to-gid-0", chown(f, -1, 0), E_PERM, f);
    DENY1(5, "chmod-own-setuid", chmod(f, 04755), E_PERM, f);
    DENY1(5, "chmod-own-setgid", chmod(f, 02755), E_PERM, f);
    char nf[96];
    snprintf(nf, sizeof nf, "%s/t5.setuid", home);
    unlink(nf);
    DENY1(5, "create-setuid", open(nf, O_WRONLY | O_CREAT | O_EXCL, 04755), E_PERM, nf);
    DENY1(5, "chmod-authd", chmod("/bin/authd", 04755), E_PERM, "/bin/authd");
    DENY1(5, "chown-authd", chown("/bin/authd", 1001, 1001), E_PERM, "/bin/authd");
    allow(5, "chmod-own-plain", chmod(f, 0600));
}

/* ---------- target 6: symlinks, hard links, openat, directory descriptors, renames, unlinked objects ---------- */
static void t6(void) {
    const char *a = "/bin/authd";
    char sl[96];
    snprintf(sl, sizeof sl, "%s/t6.to-ada", home);
    unlink(sl);
    symlink("/home/ada/secret", sl);
    DENY1(6, "open-symlink-to-ada", open(sl, O_RDONLY), E_ACCES, "/home/ada");
    int bin = open("/bin", O_RDONLY | O_DIRECTORY);
    allow(6, "open-bin-dirfd", bin);
    if (bin >= 0) {
        DENY1(6, "openat-bin-authd-write", openat(bin, "authd", O_WRONLY), E_ACCES, a);
        DENY1(6, "unlinkat-bin-authd", unlinkat(bin, "authd", 0), E_ACCES, a);
        DENY1(6, "renameat-bin-authd", renameat(bin, "authd", bin, "authd.old"), E_ACCES, a);
        allow(6, "fchdir-bin", fchdir(bin));
        DENY1(6, "open-relative-after-fchdir", open("authd", O_WRONLY), E_ACCES, a);
        DENY1(6, "open-dotdot-bin-authd", open("../bin/./authd", O_WRONLY), E_ACCES, a);
        chdir(home);
        DENY1(6, "utimensat-authd-now", utimensat(AT_FDCWD, a, NULL, 0), E_ACCES, a);
        struct timespec ts[2] = {{1, 0}, {1, 0}};
        DENY1(6, "utimensat-authd-explicit", utimensat(AT_FDCWD, a, ts, 0), E_PERM, a);
        int ro = open(a, O_RDONLY);
        if (ro >= 0) {
            DENY1(6, "futimens-read-only-fd", futimens(ro, NULL), E_ACCES, a);
            close(ro);
        }
        close(bin);
    }
    int hm = open(home, O_RDONLY | O_DIRECTORY);
    if (hm >= 0) {
        DENY1(6, "openat-dotdot-ada", openat(hm, "../ada/secret", O_RDONLY), E_ACCES, "/home/ada");
        DENY1(6, "linkat-ada-secret", linkat(AT_FDCWD, "/home/ada/secret", hm, "t6.hl", 0), E_ACCES, "/home/ada");
        close(hm);
    }
    /* an unlinked open object of the account's own keeps working (as on Linux) */
    char u[96];
    snprintf(u, sizeof u, "%s/t6.unlinked", home);
    put(u, "u\n", 0600);
    int fd = open(u, O_RDWR);
    unlink(u);
    allow(6, "write-unlinked-own", fd >= 0 ? write(fd, "v", 1) : -1);
    if (fd >= 0) { close(fd); }
    /* an open read-only descriptor of authd, its path then asked to be removed: refused, the bytes kept */
    int ro = open(a, O_RDONLY);
    DENY1(6, "unlink-authd-while-open", unlink(a), E_ACCES, a);
    if (ro >= 0) { close(ro); }
}

/* ---------- target 8: launch identity and inherited descriptors (recorded) ---------- */
static void t8(void) {
    line("T8 identity info uid=%d gid=%d euid=%d egid=%d pid=%d ppid=%d", getuid(), getgid(), geteuid(), getegid(),
         getpid(), getppid());
    char fds[256] = "";
    for (int k = 0; k < 64; k++) {
        if (fcntl(k, F_GETFD) >= 0 && k != out) {
            char p[32], t[96];
            snprintf(p, sizeof p, "/proc/self/fd/%d", k);
            ssize_t n = readlink(p, t, sizeof t - 1);
            t[n > 0 ? n : 0] = 0;
            int fl = fcntl(k, F_GETFL);
            char one[128];
            snprintf(one, sizeof one, " %d:%o:%s", k, fl & O_ACCMODE, n > 0 ? t : "?");
            strncat(fds, one, sizeof fds - strlen(fds) - 1);
        }
    }
    line("T8 inherited info%s", fds);
    verdict(8, "uid-is-account", getuid() == geteuid() && getuid() >= 1000, "uid=%d euid=%d", getuid(), geteuid());
}

/* ---------- ada's modes ---------- */
static void seed(void) {
    struct stat st;
    int ok = stat(home, &st) == 0;
    verdict(4, "ada-home-0700", ok && (st.st_mode & 07777) == 0700 && st.st_uid == getuid(),
            "mode=%o uid=%d", ok ? st.st_mode & 07777 : 0, ok ? (int)st.st_uid : -1);
    char p[96];
    snprintf(p, sizeof p, "%s/secret", home);
    allow(4, "seed-secret", put(p, "ada's secret, not sam's\n", 0600));
    snprintf(p, sizeof p, "%s/adm", home);
    allow(5, "seed-adm", put(p, "for the administration path\n", 0644));
    chmod(home, 0700);
}

static void cross(void) {
    const char *ss = "/home/sam/secret-sam";
    DENY1(4, "ada-read-sam-secret", open(ss, O_RDONLY), E_ACCES, "/home/sam");
    DENY1(4, "ada-opendir-sam-home", (long)(opendir("/home/sam") ? 0 : -1), E_ACCES, "/home/sam");
    char p[96];
    snprintf(p, sizeof p, "%s/adm", home);
    DENY1(5, "chown-without-kern", chown(p, 1001, 1001), E_PERM, p);
}

static void admin(void) {
    char p[96];
    snprintf(p, sizeof p, "%s/adm", home);
    allow(5, "chown-under-kern", chown(p, 1001, 1001));
    struct stat st;
    int ok = stat(p, &st) == 0;
    verdict(5, "chown-under-kern-took", ok && st.st_uid == 1001 && st.st_gid == 1001, "uid=%d gid=%d",
            ok ? (int)st.st_uid : -1, ok ? (int)st.st_gid : -1);
    DENY1(5, "setuid-under-kern", chmod(p, 04755), E_PERM, p);
}

static void homecheck(void) {
    struct stat st;
    int ok = lstat(home, &st) == 0;
    verdict(7, "home-is-own-0700-dir", ok && S_ISDIR(st.st_mode) && (st.st_mode & 07777) == 0700 &&
                st.st_uid == getuid() && st.st_gid == getgid(),
            "dir=%d mode=%o uid=%d gid=%d", ok && S_ISDIR(st.st_mode), ok ? st.st_mode & 07777 : 0,
            ok ? (int)st.st_uid : -1, ok ? (int)st.st_gid : -1);
    char p[96];
    snprintf(p, sizeof p, "%s/kept", home);
    struct snap s;
    take(&s, p);
    line("T7 pre-existing info kept=%d |%.*s|", s.have_bytes, (int)(s.n > 40 ? 40 : s.n), s.have_bytes ? (char *)s.bytes : "");
    drop(&s);
}

int main(int argc, char **argv) {
    const char *mode = argc > 1 ? argv[1] : "sam";
    const char *who = getenv("USER");
    if (!who || !*who) { who = getuid() == 1000 ? "ada" : getuid() == 1001 ? "sam" : "unknown"; }
    snprintf(home, sizeof home, "/home/%s", getuid() == 1000 ? "ada" : getuid() == 1001 ? "sam" : who);
    if (strcmp(mode, "admin") == 0) { snprintf(home, sizeof home, "/home/ada"); }
    char p[128];
    snprintf(p, sizeof p, "%s/fsprobe-%s.txt", home, mode);
    out = open(p, O_WRONLY | O_CREAT | O_TRUNC | O_APPEND, 0600);
    line("fsprobe %s uid %d gid %d home %s out %d", mode, getuid(), getgid(), home, out);
    if (strcmp(mode, "seed") == 0) {
        seed();
    } else if (strcmp(mode, "cross") == 0) {
        cross();
    } else if (strcmp(mode, "admin") == 0) {
        admin();
    } else if (strcmp(mode, "home") == 0) {
        homecheck();
        t8();
    } else {
        t8();
        t1();
        t3();
        t4();
        t5();
        t6();
        t2();   /* last: its child drops the disk grant */
    }
    line("end %d checks %d bad", nchk, nbad);
    if (out >= 0) { fsync(out); close(out); }
    return nbad ? 1 : 0;
}
// SPDX-License-Identifier: Apache-2.0
