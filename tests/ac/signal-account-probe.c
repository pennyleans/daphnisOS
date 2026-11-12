#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <sys/ioctl.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <unistd.h>
static int send_result(pid_t pid, int sig) {
    return kill(pid, sig) < 0 ? -errno : 0;
}
int main(void) {
    int fb = open("/dev/fb0", O_RDWR);
    int ready[2], go[2], hold[2];
    char byte = 0;
    if (fb < 0 || ioctl(fb, 0x4680, 0) < 0 || pipe(ready) || pipe(go) || pipe(hold)) return 2;
    signal(SIGTERM, SIG_IGN);
    pid_t root = getpid();
    pid_t bob = fork();
    if (bob < 0) return 3;
    if (bob == 0) {
        close(ready[0]); close(hold[1]);
        if (syscall(1003, 1001, 1001, 0) != 0 || write(ready[1], "b", 1) != 1) _exit(4);
        read(hold[0], &byte, 1);
        _exit(0);
    }
    if (read(ready[0], &byte, 1) != 1) return 5;
    pid_t alice = fork();
    if (alice < 0) return 6;
    if (alice == 0) {
        if (syscall(1003, 1000, 1000, 0) != 0) _exit(7);
        int root0 = send_result(root, 0), root_term = send_result(root, SIGTERM);
        int bob0 = send_result(bob, 0), bob_term = send_result(bob, SIGTERM);
        int self0 = send_result(getpid(), 0), missing = send_result(99999, 0);
        pid_t peer = fork();
        if (peer < 0) _exit(8);
        if (peer == 0) _exit(send_result(getppid(), 0) == 0 ? 0 : 9);
        int peer_status = 0;
        waitpid(peer, &peer_status, 0);
        dprintf(1, "signal-probe: root0=%d root_term=%d other0=%d other_term=%d self=%d peer=%d missing=%d\n", root0, root_term, bob0, bob_term, self0, peer_status, missing);
        if (write(ready[1], "a", 1) != 1 || read(go[0], &byte, 1) != 1) _exit(10);
        int elevated_root = send_result(root, 0), elevated_other = send_result(bob, 0);
        dprintf(1, "signal-probe: elevated_root=%d elevated_other=%d\n", elevated_root, elevated_other);
        _exit(root0 == -EPERM && root_term == -EPERM && bob0 == -EPERM && bob_term == -EPERM && self0 == 0 && peer_status == 0 && missing == -ESRCH && elevated_root == 0 && elevated_other == 0 ? 0 : 1);
    }
    if (read(ready[0], &byte, 1) != 1) return 11;
    uint32_t grant[2] = {(uint32_t)alice, 2};
    int elevated = ioctl(fb, 0x468D, grant);
    if (elevated != 0 || write(go[1], "g", 1) != 1) return 12;
    int status = 0;
    waitpid(alice, &status, 0);
    int root_can_signal = send_result(bob, 0);
    kill(bob, SIGKILL);
    waitpid(bob, NULL, 0);
    dprintf(1, "signal-probe: child=%d root_can_signal=%d\n", status, root_can_signal);
    return status == 0 && root_can_signal == 0 ? 0 : 1;
}
