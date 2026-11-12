/* tests/hosted/homedirs_test.c: RS-HOME (docs/specs/2026-11-11-rs-home.md), hosted. user/ci/homedirs.h as
 * user/ci/host.c includes it, with the login (Daphnis's call 1003) replaced by one that notes what it was asked and
 * can refuse. Over a directory of its own under TMPDIR (default /tmp): the three folders are made 0700 whatever the
 * caller's umask, by a child that logged in first, as the uid and gid given; a second run changes nothing; a file,
 * a link and a link to nothing under one of the names are left as they are, and what a link names is not touched;
 * a refused login and a missing home make nothing; the caller keeps its directory and its umask and has no child
 * left. Run by check.sh with gcc and with clang:
 *   cc -std=c11 -Iuser/ci tests/hosted/homedirs_test.c -o homedirs_test && ./homedirs_test
 * One line for each case that fails, then "homedirs: N checks, F failed"; exit status 1 if any failed. */
#define _XOPEN_SOURCE 700
#include <fcntl.h>
#include <ftw.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int refuse;                 /* the login's answer; the child has the caller's copy */
static char note[4200];            /* where the login writes what it was asked */

/* The stand-in for call 1003: writes "uid gid seen" to the note, seen the count of the three names that exist in
 * the home at that moment (the login comes before any folder), then refuses when told to. */
static long test_login(long uid, long gid);
#define HOME_LOGIN(uid, gid) test_login((uid), (gid))

#include "homedirs.h"

static char home[4200];

static long test_login(long uid, long gid)
{
    char p[4400];
    struct stat sb;
    int seen = 0;
    int fd;
    for (int i = 0; i < HOME_FOLDERS; i++) {
        snprintf(p, sizeof p, "%s/%s", home, home_folder[i]);
        if (lstat(p, &sb) == 0) seen++;
    }
    fd = open(note, O_WRONLY | O_CREAT | O_TRUNC, 0600);
    if (fd >= 0) {
        (void)fchmod(fd, 0600);   /* the caller's umask may have taken every bit */
        (void)dprintf(fd, "%ld %ld %d", uid, gid, seen);
        (void)close(fd);
    }
    return refuse ? -1 : 0;
}

static unsigned checks, failed;

static void expect(int ok, const char *what)
{
    checks++;
    if (!ok) {
        failed++;
        printf("FAIL %s\n", what);
    }
}

static const char *in_home(const char *name)
{
    static char p[4400];
    snprintf(p, sizeof p, "%s/%s", home, name);
    return p;
}

/* 'd' a directory, 'f' a file, 'l' a link, '-' nothing, by lstat */
static char kind(const char *path)
{
    struct stat sb;
    if (lstat(path, &sb) < 0) return '-';
    return S_ISDIR(sb.st_mode) ? 'd' : S_ISLNK(sb.st_mode) ? 'l' : S_ISREG(sb.st_mode) ? 'f' : '?';
}

static unsigned mode_of(const char *path)
{
    struct stat sb;
    return lstat(path, &sb) < 0 ? 0xFFFFu : (unsigned)(sb.st_mode & 07777);
}

static unsigned long long ino_of(const char *path)
{
    struct stat sb;
    return lstat(path, &sb) < 0 ? 0u : (unsigned long long)sb.st_ino;
}

static int note_is(const char *want)
{
    char got[64] = "";
    FILE *f = fopen(note, "r");
    if (f == NULL) return 0;
    if (fgets(got, (int)sizeof got, f) == NULL) got[0] = '\0';
    fclose(f);
    return strcmp(got, want) == 0;
}

static int drop(const char *path, const struct stat *sb, int flag, struct FTW *ftw)
{
    (void)sb; (void)flag; (void)ftw;
    return remove(path);
}

static void fresh(const char *root)
{
    (void)nftw(root, drop, 16, FTW_DEPTH | FTW_PHYS);
    (void)mkdir(root, 0700);
    (void)mkdir(home, 0700);
    (void)remove(note);
    refuse = 0;
}

static void put(const char *path, const char *text)
{
    FILE *f = fopen(path, "w");
    if (f != NULL) {
        fputs(text, f);
        fclose(f);
    }
}

int main(void)
{
    char root[4096], cwd0[4096], cwd1[4096], away[4200], p[4400];
    const char *tmp = getenv("TMPDIR");
    mode_t m;

    snprintf(root, sizeof root, "%s/homedirs-XXXXXX", tmp != NULL && tmp[0] == '/' ? tmp : "/tmp");
    if (mkdtemp(root) == NULL || getcwd(cwd0, sizeof cwd0) == NULL) {
        printf("FAIL no directory to work in\n");
        return 1;
    }
    snprintf(home, sizeof home, "%s/sam", root);
    snprintf(note, sizeof note, "%s/login", root);
    snprintf(away, sizeof away, "%s/away", root);

    /* 1: a new home, under each umask the caller could hold */
    for (unsigned k = 0; k < 3; k++) {
        static const mode_t masks[3] = {0, 022, 0777};
        fresh(root);
        (void)umask(masks[k]);
        expect(home_folders(home, 1001, 1002) == 0, "a new home: status 0");
        m = umask(077);
        expect(m == masks[k], "the caller's umask is as it was");
        for (int i = 0; i < HOME_FOLDERS; i++) {
            expect(kind(in_home(home_folder[i])) == 'd', "a new home: the folder is a directory");
            expect(mode_of(in_home(home_folder[i])) == 0700u, "a new home: the folder is 0700");
        }
        expect(note_is("1001 1002 0"), "the login came first, with the uid and gid given");
    }
    expect(getcwd(cwd1, sizeof cwd1) != NULL && strcmp(cwd0, cwd1) == 0, "the caller's directory is as it was");
    expect(waitpid(-1, NULL, WNOHANG) < 0 && errno == ECHILD, "no child is left");

    /* 2: a second login changes nothing: the same directories, what they hold, their modes */
    fresh(root);
    expect(home_folders(home, 1001, 1001) == 0, "first run");
    snprintf(p, sizeof p, "%s/Documents/letter", home);
    put(p, "kept");
    (void)chmod(in_home("Pictures"), 0750);
    {
        unsigned long long ino[HOME_FOLDERS];
        for (int i = 0; i < HOME_FOLDERS; i++) ino[i] = ino_of(in_home(home_folder[i]));
        expect(home_folders(home, 1001, 1001) == 0, "second run: status 0");
        for (int i = 0; i < HOME_FOLDERS; i++) {
            expect(ino[i] != 0u && ino_of(in_home(home_folder[i])) == ino[i], "second run: the same directory");
        }
    }
    expect(kind(p) == 'f', "second run: a file in Documents stays");
    expect(mode_of(in_home("Pictures")) == 0750u, "second run: a mode the account set stays");
    expect(note_is("1001 1001 3"), "second run: the login saw all three");

    /* 3: a file, a link to a directory elsewhere and a link to nothing hold the three names */
    fresh(root);
    (void)mkdir(away, 0700);
    put(in_home("Documents"), "a file");
    snprintf(p, sizeof p, "%s/none", root);
    expect(symlink(away, in_home("Downloads")) == 0 && symlink(p, in_home("Pictures")) == 0, "links placed");
    expect(home_folders(home, 1001, 1001) == 0, "names taken: status 0");
    expect(kind(in_home("Documents")) == 'f', "a file named Documents stays a file");
    expect(kind(in_home("Downloads")) == 'l', "a link named Downloads stays a link");
    expect(kind(in_home("Pictures")) == 'l', "a link to nothing named Pictures stays a link");
    expect(kind(p) == '-', "nothing is made where the link to nothing points");
    expect(mode_of(away) == 0700u, "the directory a link names keeps its mode");
    for (int i = 0; i < HOME_FOLDERS; i++) {
        snprintf(p, sizeof p, "%s/%s", away, home_folder[i]);
        expect(kind(p) == '-', "nothing is made in the directory a link names");
    }

    /* 4: one name taken, the other two made */
    fresh(root);
    put(in_home("Downloads"), "a file");
    expect(home_folders(home, 1001, 1001) == 0, "one name taken: status 0");
    expect(kind(in_home("Documents")) == 'd' && kind(in_home("Downloads")) == 'f'
           && kind(in_home("Pictures")) == 'd', "one name taken: the other two are made");

    /* 5: the login refuses: 126, and nothing is made (the child never acts with the caller's rights) */
    fresh(root);
    refuse = 1;
    expect(home_folders(home, 1001, 1001) == 126, "a refused login: status 126");
    for (int i = 0; i < HOME_FOLDERS; i++) {
        expect(kind(in_home(home_folder[i])) == '-', "a refused login: no folder");
    }
    expect(note_is("1001 1001 0"), "a refused login: it was asked");

    /* 6: no home: 126, and nothing is made in the caller's directory or beside the home */
    fresh(root);
    (void)rmdir(home);
    expect(chdir(root) == 0, "into the work directory");
    expect(home_folders(home, 1001, 1001) == 126, "no home: status 126");
    for (int i = 0; i < HOME_FOLDERS; i++) {
        snprintf(p, sizeof p, "%s/%s", root, home_folder[i]);
        expect(kind(p) == '-', "no home: nothing in the caller's directory");
    }
    expect(kind(home) == '-', "no home: the home is not made here");

    /* 7: a home the account cannot write (not for uid 0, which the mode does not hold) */
    fresh(root);
    if (geteuid() != 0) {
        (void)chmod(home, 0500);
        expect(home_folders(home, 1001, 1001) == 0, "a home without write: status 0");
        expect(kind(in_home("Documents")) == '-', "a home without write: no folder");
        (void)chmod(home, 0700);
    }
    expect(waitpid(-1, NULL, WNOHANG) < 0 && errno == ECHILD, "no child is left at the end");

    (void)chdir(cwd0);
    (void)nftw(root, drop, 16, FTW_DEPTH | FTW_PHYS);
    printf("homedirs: %u checks, %u failed\n", checks, failed);
    return failed == 0u ? 0 : 1;
}
