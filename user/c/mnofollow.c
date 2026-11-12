/* user/c/mnofollow.c: FS-5's probe (docs/specs/2026-11-07-bu2-meta.md section 4.9). In the directory named by its
 * argument (none: the root) it makes a file, a link to it, a directory, a link to that and a link to nothing, opens
 * each with and without O_NOFOLLOW, one line each, `nofollow: WHAT = RESULT`, and removes them. The lines are Linux's:
 * check.sh builds it with the host's gcc, runs it in a fresh directory and compares them with
 * tests/expected/fs-mnofollow.out; under Daphnis the same lines must come out for the image tree (no argument) and for
 * the volume (`grant disk mnofollow /home`). Its own static musl binary (user/c/build.sh, ruling DU-2 A). */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
static void show(const char *what, long r) { printf("nofollow: %s = %ld\n", what, r); fflush(stdout); }
static long op(const char *p, int fl) { int fd = open(p, fl, 0644); if (fd < 0) return -errno; close(fd); return 0; }
int main(int argc, char **argv)
{
    const char *d = argc > 1 ? argv[1] : "";
    char f[512], l[512], dl[512], via[512], dang[512], dir[512];
    snprintf(f, sizeof f, "%s/nf_file", d); snprintf(l, sizeof l, "%s/nf_link", d); snprintf(dir, sizeof dir, "%s/nf_dir", d);
    snprintf(dl, sizeof dl, "%s/nf_dirlink", d); snprintf(via, sizeof via, "%s/nf_dirlink/inner", d); snprintf(dang, sizeof dang, "%s/nf_dangling", d);
    int fd = open(f, O_CREAT | O_WRONLY | O_TRUNC, 0644);
    if (fd < 0) { show("create the file", -errno); return 1; }
    if (write(fd, "x", 1) != 1) {}
    close(fd);
    show("symlink to the file (want 0)", symlink("nf_file", l) < 0 ? -errno : 0);
    mkdir(dir, 0755);
    char inner[520]; snprintf(inner, sizeof inner, "%s/inner", dir);
    fd = open(inner, O_CREAT | O_WRONLY, 0644); if (fd >= 0) close(fd);
    show("symlink to the directory (want 0)", symlink("nf_dir", dl) < 0 ? -errno : 0);
    show("symlink to nothing (want 0)", symlink("nf_none", dang) < 0 ? -errno : 0);
    show("open the file, O_NOFOLLOW (want 0)", op(f, O_RDONLY | O_NOFOLLOW));
    show("open the link (want 0)", op(l, O_RDONLY));
    show("open the link, O_NOFOLLOW (want -ELOOP -40)", op(l, O_RDONLY | O_NOFOLLOW));
    show("open the link for writing, O_NOFOLLOW (want -40)", op(l, O_WRONLY | O_NOFOLLOW));
    show("open the link, O_NOFOLLOW|O_CREAT (want -40)", op(l, O_WRONLY | O_NOFOLLOW | O_CREAT));
    show("open the link, O_NOFOLLOW|O_CREAT|O_EXCL (want -EEXIST -17)", op(l, O_WRONLY | O_NOFOLLOW | O_CREAT | O_EXCL));
    show("open the dangling link, O_NOFOLLOW (want -40)", op(dang, O_RDONLY | O_NOFOLLOW));
    show("open the dangling link (want -ENOENT -2)", op(dang, O_RDONLY));
    show("open through a link in the directories, O_NOFOLLOW (want 0)", op(via, O_RDONLY | O_NOFOLLOW));
    show("open the directory link, O_NOFOLLOW|O_DIRECTORY (want -ENOTDIR -20)", op(dl, O_RDONLY | O_NOFOLLOW | O_DIRECTORY));
    show("open a name that is not there, O_NOFOLLOW (want -2)", op("/nf_absent", O_RDONLY | O_NOFOLLOW));
    fd = open(f, O_RDONLY | O_NOFOLLOW);
    struct stat st;
    show("fstat the descriptor: a regular file (want 1)", fd >= 0 && fstat(fd, &st) == 0 && S_ISREG(st.st_mode));
    if (fd >= 0) close(fd);
    unlink(l); unlink(dl); unlink(dang); unlink(inner); rmdir(dir); unlink(f);
    return 0;
}
