/* user/c/mmeta.c: the probe of BU-2a (docs/specs/2026-11-07-bu2-meta.md section 7). `mmeta DIR` makes DIR and
 * runs every metadata call of the unit inside it, printing one line a step: the call, its result (0, a value or
 * an errno name) and the stat fields Linux and Daphnis agree on (mode, links, size, atime, mtime; never inode,
 * device, ctime, blocks or a directory's size or links). It reads nothing after setting a time, so no atime
 * moves on Linux. Built by user/c/build.sh (static musl, committed as user/bin/mmeta, ruling DU-2 A). */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/utsname.h>
#include <unistd.h>

static const char *err(int e)
{
    switch (e) {
    case EPERM: return "EPERM";
    case ENOENT: return "ENOENT";
    case EEXIST: return "EEXIST";
    case EINVAL: return "EINVAL";
    case ELOOP: return "ELOOP";
    case EXDEV: return "EXDEV";
    case ENOTDIR: return "ENOTDIR";
    case ENAMETOOLONG: return "ENAMETOOLONG";
    case EROFS: return "EROFS";
    default: return "E?";
    }
}

static void rc(const char *what, long r)
{
    if (r < 0) printf("%s: %s\n", what, err(errno));
    else printf("%s: %ld\n", what, r);
}

/* mode, links and size of a file (lstat when nofollow) */
static void show(const char *p, int nofollow)
{
    struct stat st;
    int r = nofollow ? lstat(p, &st) : stat(p, &st);
    if (r < 0) { printf("  %s: %s\n", p, err(errno)); return; }
    printf("  %s: mode %06o links %ld size %ld\n", p, (unsigned)st.st_mode, (long)st.st_nlink, (long)st.st_size);
}

/* a directory's mode alone */
static void showdir(const char *p)
{
    struct stat st;
    if (stat(p, &st) < 0) { printf("  %s: %s\n", p, err(errno)); return; }
    printf("  %s: mode %06o\n", p, (unsigned)st.st_mode);
}

static void times(const char *p, int nofollow)
{
    struct stat st;
    int r = nofollow ? lstat(p, &st) : stat(p, &st);
    if (r < 0) { printf("  %s: %s\n", p, err(errno)); return; }
    printf("  %s: atime %ld mtime %ld\n", p, (long)st.st_atime, (long)st.st_mtime);
}

static void put(const char *p, const char *s, int flags)
{
    int fd = open(p, O_WRONLY | O_CREAT | flags, 0666);
    if (fd < 0) { printf("  open %s: %s\n", p, err(errno)); return; }
    if (write(fd, s, strlen(s)) != (ssize_t)strlen(s)) printf("  write %s: short\n", p);
    close(fd);
}

static void cat(const char *p)
{
    char b[128];
    int fd = open(p, O_RDONLY);
    if (fd < 0) { printf("  cat %s: %s\n", p, err(errno)); return; }
    ssize_t n = read(fd, b, sizeof b - 1);
    close(fd);
    b[n < 0 ? 0 : n] = 0;
    printf("  cat %s: %ld [%s]\n", p, (long)n, b);
}

static void link_text(const char *p, int at)
{
    char b[256];
    ssize_t n = at ? readlinkat(AT_FDCWD, p, b, sizeof b) : readlink(p, b, sizeof b);
    if (n < 0) { printf("  readlink%s %s: %s\n", at ? "at" : "", p, err(errno)); return; }
    printf("  readlink%s %s: %ld [%.*s]\n", at ? "at" : "", p, (long)n, (int)n, b);
}

int main(int argc, char **argv)
{
    if (argc != 2) { fprintf(stderr, "usage: mmeta DIR\n"); return 2; }
    umask(022);
    rc("mkdir", mkdir(argv[1], 0777));
    if (chdir(argv[1]) < 0) { printf("chdir: %s\n", err(errno)); return 1; }

    printf("umask\n");
    printf("  old %03o\n", (unsigned)umask(027));
    put("f", "data\n", 0);
    rc("  mkdir d", mkdir("d", 0777));
    show("f", 0);
    showdir("d");
    printf("  back %03o\n", (unsigned)umask(022));

    printf("chmod\n");
    rc("  chmod f 0604", chmod("f", 0604));
    show("f", 0);
    int fd = open("f", O_RDONLY);
    rc("  fchmod f 0711", fchmod(fd, 0711));
    show("f", 0);
    rc("  fchmodat d 01750", fchmodat(AT_FDCWD, "d", 01750, 0));
    showdir("d");
    rc("  chmod missing", chmod("missing", 0644));

    printf("chown\n");
    rc("  chown f self", chown("f", getuid(), getgid()));
    rc("  chown f -1 -1", chown("f", (uid_t)-1, (gid_t)-1));
    rc("  fchown f -1 gid", fchown(fd, (uid_t)-1, getgid()));
    rc("  chown missing", chown("missing", getuid(), getgid()));
    show("f", 0);

    printf("utimensat\n");
    struct timespec t[2] = {{1000, 0}, {2000, 0}};
    rc("  f 1000 2000", utimensat(AT_FDCWD, "f", t, 0));
    times("f", 0);
    t[0].tv_nsec = UTIME_OMIT; t[1].tv_sec = 3000;
    rc("  f omit 3000", utimensat(AT_FDCWD, "f", t, 0));
    times("f", 0);
    t[0].tv_sec = 4000; t[0].tv_nsec = 0; t[1].tv_nsec = UTIME_OMIT;
    rc("  futimens f 4000 omit", futimens(fd, t));
    times("f", 0);
    t[1].tv_nsec = 1000000000;
    rc("  bad nsec", utimensat(AT_FDCWD, "f", t, 0));
    rc("  bad flag", utimensat(AT_FDCWD, "f", NULL, 0x4));
    close(fd);

    printf("link\n");
    rc("  link f g", link("f", "g"));
    show("f", 0);
    show("g", 0);
    put("g", "more\n", O_APPEND);
    cat("f");
    rc("  unlink f", unlink("f"));
    show("g", 0);
    rc("  link d e", link("d", "e"));
    rc("  link g d", link("g", "d"));
    rc("  link missing h", link("missing", "h"));
    rc("  link g h", link("g", "h"));
    rc("  rename g h", rename("g", "h"));
    show("g", 0);
    show("h", 0);
    rc("  unlink h", unlink("h"));
    show("g", 0);

    printf("symlink\n");
    static const char longt[] = "./././././././././././././././././././././././././././././././././././g";
    rc("  symlink g s", symlink("g", "s"));
    rc("  symlink long l", symlink(longt, "l"));
    link_text("s", 0);
    link_text("l", 1);
    show("s", 1);
    show("l", 1);
    show("s", 0);
    cat("l");
    rc("  symlink d sd", symlink("d", "sd"));
    put("sd/x", "via\n", 0);
    cat("d/x");
    rc("  mkdir sd/y", mkdir("sd/y", 0777));
    showdir("d/y");
    rc("  symlink nowhere dang", symlink("nowhere", "dang"));
    show("dang", 0);
    show("dang", 1);
    rc("  symlink loop2 loop1", symlink("loop2", "loop1"));
    rc("  symlink loop1 loop2", symlink("loop1", "loop2"));
    rc("  open loop1", open("loop1", O_RDONLY));
    link_text("g", 0);
    rc("  symlink g s again", symlink("g", "s"));
    t[0].tv_sec = 5000; t[0].tv_nsec = 0; t[1].tv_sec = 6000; t[1].tv_nsec = 0;
    rc("  utimensat s nofollow", utimensat(AT_FDCWD, "s", t, AT_SYMLINK_NOFOLLOW));
    times("s", 1);
    rc("  lchown s self", lchown("s", getuid(), getgid()));
    rc("  link s hs", link("s", "hs"));
    show("hs", 1);
    rc("  unlink s", unlink("s"));
    show("g", 0);
    show("hs", 1);

    struct utsname u;
    rc("uname", uname(&u));
    printf("  machine %s\n", u.machine);
    return 0;
}
