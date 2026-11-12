#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <unistd.h>
#include <sys/syscall.h>
static void probe(const char *name, const char *label) {
    errno = 0;
    int fd = open(name, O_WRONLY | O_CREAT | O_TRUNC, 0600);
    int saved = errno;
    dprintf(2, "auth-probe: %s open=%d errno=%d\n", label, fd, saved);
    if (fd >= 0) { (void)write(fd, "probe\n", 6); close(fd); }
}
int main(void) {
    probe("/home/auth-helper-before.txt", "inherited");
    long rc = syscall(1000, 0);
    dprintf(2, "auth-probe: drop=%ld\n", rc);
    probe("/home/auth-helper-after.txt", "dropped");
    char *args[] = {"authd", NULL};
    char *env[] = {NULL};
    execve("/bin/authd-real", args, env);
    dprintf(2, "auth-probe: exec errno=%d\n", errno);
    return 127;
}
