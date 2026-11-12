#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <unistd.h>

static int read_result(int fd) {
    unsigned char ev[24];
    int r = (int)read(fd, ev, sizeof ev);
    return r < 0 ? -errno : r;
}

int main(int argc, char **argv) {
    if (argc > 1 && strcmp(argv[1], "session") == 0) {
        struct stat got;
        int inherited = 0;
        /* FS-2/3: the account writes in its own home (HOME, from spawn_as), not at the volume's root */
        const char *home = getenv("HOME");
        char path[128];
        if (home == NULL || snprintf(path, sizeof path, "%s/raw-session-result", home) >= (int)sizeof path) return 9;
        int result = open(path, O_WRONLY | O_CREAT | O_TRUNC, 0600);
        if (result < 0) return 9;
        for (int fd = 0; fd < 256; fd++) {
            if (fstat(fd, &got) == 0 && S_ISCHR(got.st_mode) && got.st_rdev == 0xD40) inherited++;
        }
        dprintf(result, "raw-probe: inherited=%d\n", inherited);
        int fd = open("/dev/input/event0", O_RDONLY | O_NONBLOCK);
        if (fd < 0) return 3;
        dprintf(result, "raw-probe: fresh=%d\n", read_result(fd));
        close(fd);
        close(result);
        return inherited == 0 ? 0 : 1;
    }
    int fb = open("/dev/fb0", O_RDWR);
    if (fb < 0 || ioctl(fb, 0x4680, 0) < 0) return 4;
    int raw = open("/dev/input/event0", O_RDONLY | O_NONBLOCK);
    if (raw < 0) return 5;
    pid_t pid = fork();
    if (pid < 0) return 6;
    if (pid == 0) {
        int before = read_result(raw);
        long login = syscall(1003, 1000, 1000, 0);
        int after = read_result(raw);
        int fresh = open("/dev/input/event0", O_RDONLY | O_NONBLOCK);
        int queued = fresh < 0 ? -errno : read_result(fresh);
        dprintf(1, "raw-probe: fork=%d login=%ld inherited=%d fresh=%d\n", before, login, after, queued);
        _exit(before == -EACCES && login == 0 && after == -EACCES && queued == -EAGAIN ? 0 : 1);
    }
    int status = 0;
    if (waitpid(pid, &status, 0) != pid) return 7;
    dprintf(1, "raw-probe: child_status=%d\n", status);
    return WIFEXITED(status) ? WEXITSTATUS(status) : 8;
}
