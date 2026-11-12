/* user/c/mcut.c: GV-1b's probe (docs/specs/2026-11-11-gv-revoke.md section 3, option A, and section 5). Under Daphnis,
 * as the desk, it shows what a revoke does to what a window already has open, one line each, `mcut: WHAT = RESULT`:
 *   net (a boot with a network and a host HTTP server at 10.0.2.2:8080): a TCP connection in the middle of a download
 *     and a UDP socket; after the revoke a read ends, a write fails, no new socket is made;
 *   disk (a boot with a volume on /home): a file open for reading and writing; after the revoke a write and a truncate
 *     fail, a read through the same descriptor still reads;
 *   audio (a boot with /dev/dsp): an open /dev/dsp; after the revoke a write and an ioctl fail.
 * Each part runs only where the boot has the device, and the first lines say which it has, so the desknet flavor
 * (network, volume) and the hdesk flavor (/dev/dsp, volume) each print their own pinned lines
 * (tests/expected/gv-mcut-desknet.out, gv-mcut-hdesk.out; check-revoke.sh). The program is never ended and nothing is
 * closed for it. On Linux the Daphnis calls are -ENOSYS. Its own static musl binary (user/c/build.sh, DU-2 A). */
#define _GNU_SOURCE
#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <unistd.h>

#define NR_GRANT 1000
#define NR_LOGIN 1003
#define NR_REVOKE 1008
#define FBIO_TILER 0x4680
#define DISK 1L
#define NET 2L
#define AUDIO 4L
#define HOST "10.0.2.2"
#define HTTP 8080

static long call(long nr, long a, long b, long c)
{
    long r = syscall(nr, a, b, c);
    return r < 0 ? -errno : r;
}

static void show(const char *what, long r)
{
    printf("mcut: %s = %ld\n", what, r);
    fflush(stdout);
}

static long ret(long r) { return r < 0 ? -errno : r; }
static void wait_byte(int fd) { char x; if (read(fd, &x, 1) != 1) _exit(1); }
static void send_byte(int fd) { if (write(fd, "x", 1) != 1) _exit(1); }

static int tcp_to_host(void)
{
    struct sockaddr_in a = {0};
    int s = socket(AF_INET, SOCK_STREAM, 0);
    if (s < 0) return -1;
    a.sin_family = AF_INET;
    a.sin_port = htons(HTTP);
    inet_pton(AF_INET, HOST, &a.sin_addr);
    if (connect(s, (struct sockaddr *)&a, sizeof a) < 0) { close(s); return -1; }
    return s;
}

int main(void)
{
    char buf[2048];
    int fb = open("/dev/fb0", O_RDWR);
    if (fb < 0) {
        show("open /dev/fb0 (no framebuffer: nothing checked)", -errno);
        return 0;
    }
    long t = ioctl(fb, FBIO_TILER, 0);
    show("FBIO_TILER as uid 0 (want 0)", t < 0 ? -errno : t);
    show("desk: grant disk, net and audio to itself (want 0)", call(NR_GRANT, DISK | NET | AUDIO, 0, 0));

    /* what this boot has */
    int probe = tcp_to_host();
    long has_net = probe >= 0;
    if (probe >= 0) close(probe);
    int d = open("/dev/dsp", O_WRONLY);
    long has_dsp = d >= 0;
    if (d >= 0) close(d);
    int f = open("/home/mcut.txt", O_CREAT | O_RDWR | O_TRUNC, 0666);
    long has_vol = f >= 0;
    if (f >= 0) { fchmod(f, 0666); close(f); }
    show("this boot has a network and the host's server", has_net);
    show("this boot has /dev/dsp", has_dsp);
    show("this boot has a volume on /home", has_vol);

    int up[2], down[2];
    if (pipe(up) < 0 || pipe(down) < 0) return 1;
    pid_t c = fork();
    if (c == 0) {
        show("child: login uid 1000, ceiling disk, net and audio (want 0)", call(NR_LOGIN, 1000, 100, DISK | NET | AUDIO));
        show("child: grant all three, within the ceiling (want 0)", call(NR_GRANT, DISK | NET | AUDIO, 0, 0));
        int s = -1, u = -1, file = -1, dsp = -1;
        if (has_net) {
            s = tcp_to_host();
            show("child: a TCP connection to the host (want 1)", s >= 0);
            const char *req = "GET /f HTTP/1.0\r\n\r\n";
            show("child: sends the request (want 19)", ret(write(s, req, strlen(req))));
            long got = ret(read(s, buf, 1000));
            show("child: reads the first bytes of the download (want 1)", got > 0);
            u = socket(AF_INET, SOCK_DGRAM, 0);
            show("child: a UDP socket (want 1)", u >= 0);
        }
        if (has_vol) {
            file = open("/home/mcut.txt", O_RDWR);
            show("child: opens the file on /home for reading and writing (want 1)", file >= 0);
            show("child: writes 5 bytes (want 5)", ret(write(file, "hello", 5)));
        }
        if (has_dsp) {
            dsp = open("/dev/dsp", O_WRONLY);
            show("child: opens /dev/dsp (want 1)", dsp >= 0);
            memset(buf, 0, 64);
            show("child: writes 64 bytes of silence (want 64)", ret(write(dsp, buf, 64)));
        }
        send_byte(up[1]);
        wait_byte(down[0]);                      /* the desk has revoked disk, net and audio */
        if (has_net) {
            struct sockaddr_in a = {0};
            a.sin_family = AF_INET;
            a.sin_port = htons(9);
            inet_pton(AF_INET, HOST, &a.sin_addr);
            show("child: the next read of the download ends (want 0)", ret(read(s, buf, 1000)));
            show("child: a write to the connection fails (want -EACCES -13)", ret(write(s, "x", 1)));
            show("child: a datagram on the UDP socket fails (want -13)", ret(sendto(u, "x", 1, 0, (struct sockaddr *)&a, sizeof a)));
            show("child: a read of the UDP socket ends (want 0)", ret(recv(u, buf, 100, 0)));
            show("child: a new socket (want -13)", ret(socket(AF_INET, SOCK_STREAM, 0)));
            show("child: closing the cut connection (want 0)", ret(close(s)));
        }
        if (has_vol) {
            show("child: a write to the open file fails (want -13)", ret(write(file, "again", 5)));
            show("child: a truncate through it fails (want -13)", ret(ftruncate(file, 0)));
            show("child: a read through it still reads, from the start (want 5)", ret(pread(file, buf, 100, 0)));
            show("child: opening the file again for writing fails (want -EROFS -30)", ret(open("/home/mcut.txt", O_WRONLY)));
            show("child: opening it for reading still works (want 1)", open("/home/mcut.txt", O_RDONLY) >= 0);
        }
        if (has_dsp) {
            show("child: a write to the open /dev/dsp fails (want -13)", ret(write(dsp, buf, 64)));
            show("child: an ioctl on it fails (want -13)", ret(ioctl(dsp, 0x5000, 0)));
            show("child: opening /dev/dsp again fails (want -13)", ret(open("/dev/dsp", O_WRONLY)));
        }
        show("child: still running, its own exit (want 0)", 0);
        _exit(0);
    }
    wait_byte(up[0]);
    show("desk: revoke disk, net and audio from the child's window (want 1)", call(NR_REVOKE, c, DISK | NET | AUDIO, 0));
    send_byte(down[1]);
    int st = -1;
    waitpid(c, &st, 0);
    show("desk: the child ended by itself, status (want 0)", WIFEXITED(st) ? WEXITSTATUS(st) : -1);
    if (has_vol) {
        struct stat sb;
        show("desk: the file keeps the 5 bytes written before the revoke (want 5)", stat("/home/mcut.txt", &sb) == 0 ? (long)sb.st_size : -1);
        unlink("/home/mcut.txt");
    }
    show("done", 0);
    return 0;
}
