/* user/ci/host.c: the host side of a cint program's externs in ring 3 (stage R-1). Each row is a
 * Linux system call or a few, so it runs on Linux and under Daphnis alike (DU-1 A). Rows:
 *   fb_open() -> I64: opens /dev/fb0, reads the two screen infos and maps the framebuffer; 0, or
 *     -errno (-ENOENT without a framebuffer).
 *   fb_word(I64 i) -> U64: the five words of the surface contract after fb_open: 0 w, 1 h, 2 stride,
 *     3 bits per pixel, 4 the mapping's length; 0 before fb_open.
 *   fb_row(I64 y, in U8[_] px): copies px (4 bytes a pixel, XRGB little endian, at most 4 * w) to
 *     row y of the mapping; a row outside the surface is not written.
 *   ev_read(out U8[_] ev) -> I64: one input_event (24 bytes) from /dev/input/event0 into ev, opened
 *     on the first call; 1 for an event, 0 for none (O_NONBLOCK), or -errno.
 *   clock_ns() -> I64: CLOCK_MONOTONIC in nanoseconds (the virtual clock under Daphnis).
 *   exit_now(I64 code): exits the process at once with the status.
 *   out_open(in U8[_] path) -> I64: creates or truncates the file at path (mode 0644) as the output file
 *     of out_put; 0, or -errno (-ENAMETOOLONG for a path of 4,096 bytes or more, -EINVAL for one holding
 *     a NUL). W-1: the tiler's --surface-out.
 *   out_put(in U8[_] bytes) -> I64: writes bytes to the output file whole; the count, or -errno (-EBADF
 *     before out_open).
 *   tile_ctl(I64 req, in U8[_] arg) -> I64: ioctl(req) on a descriptor of /dev/fb0 kept open (O_CLOEXEC) for
 *     the tiler's requests (W-2, src/tile.ci), arg as its buffer (at most 64 bytes); what ioctl returns, or -errno.
 *   tile_big(I64 req, in U8[_] arg) -> I64: the same for at most 9,236 bytes (FBIO_TILE_BUSY's sprite, DN-37).
 *   spawn(in U8[_] path) -> I64: fork, and the child runs path with argv {path} and no environment (status
 *     127 if it cannot); the child's pid, or -errno.
 *   reap(I64 pid, Bool nohang) -> I64: waits for the child pid to end; its wait status, -EAGAIN with nohang
 *     while it runs, or -errno.
 *   stop(I64 pid, I64 sig) -> I64: kill(pid, sig); 0, or -errno.
 *   fb_span(I64 y, I64 x, in U32[_] px) -> I64: copies px (a word a pixel, D-ROW) to row y of the mapping from column x, clipped to
 *     the surface; 0, or -1 before fb_open (W-3).
 * NW-0, built only into a program that imports user/ci/wall.ci (CI_ROWS_WALL):
 *   wall_ns() -> I64: CLOCK_BOOTTIME in nanoseconds (the PIT's ticks under Daphnis, G-2; never in a digest).
 * KF-2, built only into a program that imports user/ci/sysinfoctl.ci (CI_ROWS_SYSINFO):
 *   co_sysinfo(out I64[_] rec) -> I64: sysinfo into rec's five words (uptime, totalram, freeram, procs, mem_unit);
 *     0, or -errno.
 *   co_ids(out I64[_] ids) -> I64: getpid and geteuid into ids' first two words; 0, or -EINVAL.
 * GV-2, built only into a program that imports user/ci/revokectl.ci (CI_ROWS_REVOKE):
 *   co_revoke(I64 vpid, I64 word) -> I64: Daphnis's revoke (1008); the processes changed, or -errno (-ENOSYS on Linux).
 * N-2, built only into a program that imports user/ci/udp.ci (user/ci/build.sh defines CI_ROWS_NET), so the
 * other programs' bytes do not change:
 *   udp_open() -> I64: socket(AF_INET, SOCK_DGRAM, 0), SO_RCVTIMEO 2 s; the descriptor, or -errno.
 *   udp_send(I64 fd, U64 ip, I64 port, in U8[_] bytes) -> I64: sendto; the count, or -errno.
 *   udp_recv(I64 fd, out U8[_] buf) -> I64: recvfrom (at most 1,500 bytes); the count, or -errno.
 *   udp_from(I64 i) -> U64: the last udp_recv's sender, 0 its address as a word, 1 its port.
 *   stdout_put(in U8[_] bytes) -> I64: bytes to descriptor 1 whole; the count, or -errno.
 * N-3, built only into a program that imports user/ci/tcp.ci (CI_ROWS_TCP):
 *   tcp_listen(I64 port) -> I64: socket(AF_INET, SOCK_STREAM, 0), bind to 0.0.0.0:port, listen(1); the
 *     descriptor, or -errno.
 *   tcp_accept(I64 fd) -> I64: accept; the new descriptor, or -errno.
 *   tcp_connect(U64 ip, I64 port) -> I64: socket(AF_INET, SOCK_STREAM, 0) connected to ip:port (ip as a word,
 *     10.0.2.2 is 0x0A000202); the descriptor, or -errno (A-0, user/ci/talk.ci).
 *   fd_read(I64 fd, out U8[_] buf) -> I64: one read of at most buf's length (4,096 bytes for a strided view); the
 *     count, 0 at the end, or -errno.
 *   fd_write(I64 fd, in U8[_] bytes) -> I64: writes until all are written, at any length; the count, or -errno.
 *   fd_close(I64 fd) -> I64: close; 0, or -errno.
 * W-4, built only into a program that imports user/ci/ptyctl.ci (CI_ROWS_PTY), for the same reason:
 *   pty_open(I64 cols, I64 rows) -> I64: a pty's master (/dev/ptmx, O_CLOEXEC), unlocked, its window
 *     cols x rows cells of 8 x 16; the descriptor, or -errno.
 *   pty_spawn(in U8[_] path, in U8[_] env, I64 master) -> I64: fork, and the child leads a new session (setsid) and
 *     opens the master's slave, which becomes its controlling terminal (K-10: Ctrl-C reaches its group), as
 *     descriptors 0, 1 and 2 and runs path with argv {path} and env as its environment: NAME=value strings, each
 *     ended by a NUL byte, at most 16 in 512 bytes (E-6; -E2BIG past them, -EINVAL for an unended one); status 127
 *     if it cannot; the pid, or -errno.
 *   pty_read(I64 fd, out U8[_] buf) -> I64: read, at most 4096 bytes; the count, or -errno.
 *   pty_write(I64 fd, in U8[_] bytes) -> I64: write, at most 512 bytes; the count taken, or -errno.
 * H-3a, built only into a program that imports user/ci/hdeskctl.ci (CI_ROWS_HDESK), the hybrid desk:
 *   tile_ask(I64 req, I64 a, I64 b, out U8[_] buf) -> I64: ioctl(req) on /dev/fb0 with the u32 words a and b in a
 *     64-byte argument, what the kernel wrote there copied into buf (FBIO_TILE_INFO); what ioctl returns, or -errno.
 *   pty_winsize(I64 fd, I64 cols, I64 rows) -> I64: TIOCSWINSZ on a master, cells of 8 x 16; 0, or -errno.
 *   pty_nonblock(I64 fd) -> I64: O_NONBLOCK on a master, so pty_read gives -EAGAIN when it has nothing; 0, or -errno.
 *   pty_sigsess(I64 fd, I64 sig) -> I64: Daphnis's TIOCSIGSESS (0x5480) on a master, sig to every process of the
 *     pair's session (WB-4: the close of a terminal window); 0, or -errno.
 *   fb_remap() -> I64: /dev/fb0 mapped again at the size it has now (HX-13: after FBIO_TILE_MODE); 0, or -errno.
 *   power(I64 how) -> I64: FF-4, reboot(2): 1 shut down (RB_POWER_OFF), 2 restart (RB_AUTOBOOT); returns only when
 *     it did not take: -errno (-EPERM for a process that is not the tiler, -EINVAL for another how).
 *   spawn_as(in U8[_] path, in U8[_] env, I64 master, I64 uid, I64 gid, I64 ceil) -> I64: AC-1c, pty_spawn's fork and
 *     pty, then in the child Daphnis's call 1003, login(uid, gid, ceil) (AC-1a; status 126 if it is refused), then a
 *     chdir to env's HOME (status 126 if it fails: FS-3, no fallback home), then execve; the pid, or -errno.
 *   auth_start(in U8[_] req) -> I64: AC-1c, AC-D8: forks /bin/authd with pipes on its descriptors 0 and 1, writes
 *     req (at most 640 bytes: RS-R4's two passphrases) and closes its input, the answer's end non-blocking; one at
 *     a time; 0, or -errno (-EBUSY while one runs). The copy of req is zeroed.
 *   auth_poll(out U8[_] buf) -> I64: authd's answer so far: the count read, -EAGAIN while it works, 0 at its end (the
 *     descriptor closed and authd reaped), -ENOENT with none started.
 *   home(in U8[_] path, I64 uid, I64 gid) -> I64: FS-3, Daphnis's call 1006, the desk's alone: the account's home
 *     made 0700 as uid and gid, or checked (a directory, not a link, owned by uid, no group or other write); 0, or
 *     -errno. RS-HOME: after a 0, Documents, Downloads and Pictures are made in it, 0700, by a child that runs as
 *     the account (user/ci/homedirs.h); a name already there is left alone, and no folder changes the answer.
 *   fb_hold(I64 on) -> I64: RS-SHOT, the screen held: with on, a copy of the framebuffer as it is now, which fb_peek
 *     and shot_as read until fb_hold(0) zeroes and frees it (a second hold replaces the first); 0, or -errno.
 *   fb_peek(I64 x, I64 y, out U8[_] px) -> I64: pixels of row y from x, of the held screen or else the live one, 4
 *     bytes each as the framebuffer holds them, as many as px takes up to the row's end; the count, -EINVAL off the
 *     screen.
 *   shot_as(I64 x, I64 y, I64 w, I64 h, I64 uid, I64 gid, I64 ceil, in U8[_] home) -> I64: RS-SHOT, the rectangle
 *     (at most 3840 x 2160, inside the held or live screen) copied, then a child of the desk that logs in (call 1003,
 *     the ceiling cut to Disk alone; status 126 if it is refused, and nothing more runs), keeps only a name pipe as descriptors 1 and 2, goes to home
 *     (/home/NAME), and runs /bin/shot with no arguments and no environment, the pixels on a pipe after a header of
 *     u32 width, height and stride and u64 the bar's date (FBIO_TILE_INFO kind 2, read when shot_as is called), which
 *     names the file; the child's status is shot's. The desk does not wait or write: the child writes.
 *     Four at a time; the child's pid, or -errno (-EBUSY with four running, -EINVAL for a bad rectangle or home).
 *   shot_end(I64 pid, out U8[_] name) -> I64: after the desk reaps pid, the file name shot printed (a plain
 *     "Screenshot ... .png" in Pictures), and the pipe closed; its length, -EINVAL with no such name, -ENOENT for
 *     another pid, -EBUSY (the slot kept) while pid is not yet reaped.
 *   run_session(I64 uid, I64 gid, I64 ceil, in U8[_] home) -> I64, run_start(I64 job, in U8[_] arg) -> I64,
 *   run_poll(out U8[_] buf) -> I64, run_stop() -> I64: the desk's runs as the account (user/ci/runas.h): a job of a
 *     fixed table, as the session's login record and no other, its stdout read without blocking under a byte cap
 *     and a time limit, the child always reaped.
 * H-3c3, built only into a program that imports user/ci/tilewin.ci (CI_ROWS_WIN), a pixel window that asks (a C
 * client defines CI_WIN_C for ci_win_want, ci_win_var and ci_win_resize alone, no rows: user/ci/doom/build.sh):
 *   win_want(I64 w, I64 h) -> I64: the surface size fb_open asks (FBIO_TILE_WANT) between its open and its mmap; 0.
 *   win_var(in U8[_] v) -> I64: FBIO_TILE_VAR with v's first 64 bytes, NUL padded; what ioctl returns, or -errno.
 *   win_menu(in U8[_] rec) -> I64: FBIO_TILE_MENU (AM-2, AM-4) with rec's first 1220 bytes (u32 n, n up to 38 records);
 *   what ioctl returns, or -errno.
 *   win_resize(I64 on) -> I64: FBIO_TILE_RESIZE {on}: EV_WIN_RESIZE from the tiler; what ioctl returns, or -errno.
 *     Before fb_open it is kept and asked at the open, ahead of the size, so the desk's first box reaches it; 0.
 * RS-SURF, built only into a program that imports user/ci/tilesurf.ci (CI_ROWS_SURF) and tilewin.ci: Index, View
 * and Monitor (docs/specs/2026-11-05-h-hybrid.md section 5a):
 *   fb_resize(I64 w, I64 h) -> I64: the surface taken to w x h after its first map: munmap, FBIO_TILE_WANT {w, h},
 *     mmap again; fb_word reads the size it has after. What FBIO_TILE_WANT answered (0, or -EINVAL while the desk
 *     has not placed the window again since its last ask: the surface is mapped back at the size it had), or the
 *     open's or the map's -errno, with no surface.
 * BP-6, built only into a program that imports user/ci/tilepoint.ci (CI_ROWS_POINT) and tilewin.ci, cview:
 *   win_point(I64 on) -> I64: FBIO_TILE_POINT {on}: EV_ABS, the pointer's place, from the tiler; what ioctl returns,
 *     or -errno.
 * H-2, built only into a program that imports user/ci/tileplace.ci (CI_ROWS_PLACE):
 *   tile_place(in U8[_] arg) -> I64: FBIO_TILE_PLACE (src/tile.ci) with arg's 24-byte head {u32 pid, i32 dst_x,
 *     dst_y, u16 scale, nrects, u64 uaddr} and its nrects rectangles of 16 bytes after it (at most 32); uaddr
 *     becomes the address of the copy's rectangles. What ioctl returns, or -errno.
 * P-3, built only into a program that imports user/ci/grantcall.ci (CI_ROWS_GRANT):
 *   grant_set(U64 w) -> I64: Daphnis's call 1000, the process's grant word becomes w (P-3, GR-1 A); 0, or
 *     -errno (-ENOSYS on Linux, which has no such call).
 *   grant_ask(in U8[_] args, I64 at, U64 w) -> I64: AC-1c, Daphnis's call 1004 (AC-1a) with args' bytes from at as
 *     the command line the prompt names: the grants of w past the ceiling asked of the desk, the call waiting while
 *     its prompt is up; 0 on a parent's yes or with nothing to ask, else -errno (-EPERM on a no or with no desk).
 *   exec_from(in U8[_] args, I64 at) -> I64: execve of the NUL-terminated strings of args from byte at on
 *     (the first is the path and argv[0]; at most 63), with the process's environment; a first string with
 *     no slash is looked up in PATH first, then taken as it is (BU-2c); only a failure returns: -errno.
 * R0-2, built only into a program that imports user/ci/kerncall.ci (CI_ROWS_KERN):
 *   kern_ask(in U8[_] args, I64 at) -> I64: Daphnis's call 1001 with args' bytes from at (the command line, its
 *     strings NUL-separated): ring 0 asked of the desk, the call waiting while its prompt is up; 0 on Super+Enter or
 *     a hold, else -errno (-EPERM on Esc or with no desk; -ENOSYS on Linux).
 *   kern_held() -> I64: call 1001 with no text, which asks nothing: 1 when the process holds ring 0, 0 when not,
 *     or -errno.
 * SP-2, built only into a program that imports user/ci/traycall.ci (CI_ROWS_TRAY):
 *   tray_ask(I64 on) -> I64: Daphnis's call 1002, 1 asks for the desk's tray, 0 leaves it; 0, or -errno (-ENOSYS on
 *     Linux).
 * FF 3h, built only into a program that imports user/ci/dirctl.ci (CI_ROWS_DIR):
 *   dir_names(in U8[_] path, out U8[_] buf) -> I64: path's names (readdir's, . and .. among them), each ended by a 0
 *     byte, the first ones that fit buf whole: the bytes written, or -errno. Unlike sh_dirents it never answers -E2BIG:
 *     the Trash store frees a folder of any size by reading what fits, freeing it and reading again.
 * FF-6c, built only into a program that imports user/ci/opencall.ci (CI_ROWS_OPEN):
 *   open_ask(in U8[_] path) -> I64: Daphnis's call 1005, the desk asked to open path (1..256 bytes) as the Super plane
 *     opens a file; 0, or -errno (-ENOSYS on Linux).
 * CS-1, built only into a program that imports user/ci/shctl.ci (CI_ROWS_SH; docs/specs/2026-11-06-cish-shell.md
 * section 7): cish's rows, one per call, each the call's value or -errno, with fd_read, fd_write and fd_close:
 *   sh_fork, sh_exec(path, argv, envp), sh_wait(pid, nohang), sh_pipe, sh_dup2, sh_dupfd(fd, least) (F_DUPFD_CLOEXEC),
 *   sh_open(path, flags, mode), sh_chdir, sh_getcwd(buf), sh_environ(i, buf), sh_getpid; CS-2: sh_stat(path, follow,
 *   buf) (mode and size), sh_access(path, mode); CS-3: sh_dirents(path, buf) (a directory's names, each NUL-ended);
 *   CS-4: sh_geteuid (the prompt's # or $), sh_tcget(fd, buf), sh_tcset(fd, buf) (the termios as bytes).
 *   BU-4h2: sh_maxrss (user/ci/peakctl.ci, with the rows above), the ru_maxrss (KiB) wait4 gave for the child sh_wait
 *   last reaped (Daphnis: its peak of frames).
 * CT-1, built only into a program that imports user/ci/corectl.ci (CI_ROWS_CORE; docs/specs/2026-11-06-c-core.md
 *   section 4): the core set's rows beside cish's: co_stat(path, follow, rec) (the full record), co_lseek(fd, off,
 *   whence), co_mkdir(path, mode), co_rmdir, co_unlink, co_rename(from, to), co_clock(which), co_sleep(ns). CT-2:
 *   co_readlink(path, buf) (the target's length), co_symlink(target, path), co_ignore_int() (SIGINT ignored, tee -i).
 *   CT-5: co_ftruncate(fd, len) (truncate), co_sync() (sync). RS-CLK: co_settime(s) (clock_settime, CLOCK_REALTIME).
 * BP-2, built only into a program that imports user/ci/viewctl.ci (CI_ROWS_VIEW), cless and cish (K-9):
 *   view_winsize(I64 fd) -> I64: TIOCGWINSZ; (rows << 16) | columns, or -errno.
 * K-10, built only into a program that imports user/ci/sigctl.ci (CI_ROWS_SIG), cish:
 *   sig_set(I64 sig, I64 ignore) -> I64: signal(sig, SIG_IGN) for 1, SIG_DFL for 0; 0, or -errno.
 * CT-4, built only into a program that imports user/ci/runctl.ci (CI_ROWS_RUN, with CI_ROWS_SH; docs/specs/
 * 2026-11-06-c-core.md section 5): co_exec(path, argv, envp), sh_exec with the core set's limits: ARGS_MAX (4,096)
 * arguments in ARGS_BYTES (65,536) bytes, 1,024 environment strings in 65,536 bytes; -E2BIG past them.
 * BU-2b, built only into a program that imports user/ci/metactl.ci (CI_ROWS_META, with CI_ROWS_CORE; docs/specs/
 *   2026-11-07-bu2-meta.md section 6): co_chmod, co_umask, co_utimens, co_link, co_uname (tier C-2).
 * A-4, built only into a program that imports user/ci/tls.ci (CI_ROWS_TLS; user/ci/build.sh links BearSSL, built by
 *   user/tls/build.sh): one TLS 1.2 client session at a time over a connected descriptor. A BearSSL failure is
 *   -(1000 + its error code): -1054 a certificate out of its dates, -1056 a name it does not hold, -1062 a chain to
 *   no anchor held.
 *   tls_open(I64 fd, in U8[_] host) -> I64: draws 32 bytes from getrandom (318) as the engine's whole seed,
 *     then the handshake with host as the server's name; the anchors are user/tls/anchors.h's TA_MOCK for a name
 *     under .mock and TA_PUBLIC for any other; 0, or -errno (-ENOSYS with no entropy source, -ENAMETOOLONG for
 *     a name of 254 bytes or more), or a BearSSL failure.
 *   tls_read(out U8[_] buf) -> I64: at most 4,096 bytes of application data; the count, 0 after the server's
 *     close_notify, or a BearSSL failure (-1031 for a connection that ends without one).
 *   tls_write(in U8[_] bytes) -> I64: writes and flushes all; the count, or a BearSSL failure.
 *   tls_close() -> I64: sends close_notify without waiting for the server; 0, or a failure. The
 *     descriptor stays open (fd_close).
 * AC-1b, built only into a program that imports user/ci/authctl.ci (CI_ROWS_AUTH), authd:
 *   rand_fill(out U8[_] buf) -> I64: fills buf, at most 256 bytes, from getrandom (318); the count, or -errno.
 * CV-4a, built only into a program that imports user/ci/cvimctl.ci (CI_ROWS_CVIM), cvim:
 *   cv_term_enter(I64 fd) -> I64: fd's termios kept here, then raw (no ICANON, ECHO, ISIG, IEXTEN, IXON, ICRNL or
 *     OPOST; VMIN 1, VTIME 0), the alternate screen; SIGTERM, SIGHUP, SIGINT, SIGQUIT, SIGABRT, SIGSEGV, SIGBUS,
 *     SIGFPE, SIGILL and SIGTRAP restore the terminal and then end the process as the signal would; atexit too;
 *     SIGWINCH sets a flag, with no SA_RESTART so a read returns -EINTR; 0, or -errno (-ENOTTY with no terminal).
 *   cv_term_leave() -> I64: the cursor's form reset, the cursor shown, the main screen back, the termios as it was.
 *   cv_winch() -> I64: 1 once after a SIGWINCH, else 0.
 *   cv_fsync(I64 fd), cv_fchmod(I64 fd, I64 mode) -> I64: fsync, fchmod; 0, or -errno. */
#define _POSIX_C_SOURCE 200809L
#if defined(CI_ROWS_GRANT) || defined(CI_ROWS_TLS) || defined(CI_ROWS_CORE) || defined(CI_ROWS_KERN) || defined(CI_ROWS_AUTH) || defined(CI_ROWS_SH) || defined(CI_ROWS_HDESK)
#define _DEFAULT_SOURCE   /* syscall declarations and wait4 */
#endif
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <signal.h>
#include <sys/syscall.h>
#include <sys/stat.h>
#include <dirent.h>
#include <sys/resource.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#include "host.h"

#define FBIOGET_VSCREENINFO_ 0x4600u
#define FBIOGET_FSCREENINFO_ 0x4602u

static uint8_t *fb_base;
static uint64_t fb_words[5];   /* w, h, stride, bpp, len */
static int ev_fd = -1;
static int out_fd = -1;
static int tile_fd = -1;

#if defined(CI_ROWS_WIN) || defined(CI_WIN_C)
static uint32_t win_wh[2]; /* H-3c3: the size ci_win_want asked, 0 x 0 for the offer */
static uint32_t win_rs;    /* ci_win_resize before the open: asked at it, before the size */
#endif
#ifdef CI_ROWS_SURF
static int64_t win_got; /* RS-SURF: what the last FBIO_TILE_WANT answered: 0, or -errno */
#endif

int64_t ci_fb_open(void)
{
    uint32_t var[40];
    uint8_t fix[80];
    uint32_t v32;
    int fd;
    if (fb_base != NULL) return 0;
    fd = open("/dev/fb0", O_RDWR);
    if (fd < 0) return -(int64_t)errno;
#if defined(CI_ROWS_WIN) || defined(CI_WIN_C)
    if (win_rs != 0u) (void)ioctl(fd, 0x468AUL, &win_rs);   /* before the size: the desk lays the window out after it */
#ifdef CI_ROWS_SURF
    if (win_wh[0] != 0u) win_got = ioctl(fd, 0x4689UL, win_wh) < 0 ? -(int64_t)errno : 0;
#else
    if (win_wh[0] != 0u) (void)ioctl(fd, 0x4689UL, win_wh); /* refused for a tile, a whole screen, or on Linux */
#endif
#endif
    if (ioctl(fd, FBIOGET_VSCREENINFO_, var) < 0 || ioctl(fd, FBIOGET_FSCREENINFO_, fix) < 0) {
        int64_t e = -(int64_t)errno;
        close(fd);
        return e;
    }
    fb_words[0] = var[0];
    fb_words[1] = var[1];
    fb_words[3] = var[6];
    memcpy(&v32, fix + 48, 4u);   /* line_length, u32 at byte 48 */
    fb_words[2] = v32;
    memcpy(&v32, fix + 24, 4u);   /* smem_len, u32 at byte 24 */
    fb_words[4] = v32;
    fb_base = (uint8_t *)mmap(NULL, (size_t)fb_words[4], PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    close(fd);
    if (fb_base == MAP_FAILED) { fb_base = NULL; return -(int64_t)errno; }
    return 0;
}

uint64_t ci_fb_word(int64_t i)
{
    return fb_base != NULL && i >= 0 && i < 5 ? fb_words[i] : 0u;
}

void ci_fb_put(int64_t y, const uint8_t *px, int64_t len)
{
    if (fb_base == NULL || y < 0 || (uint64_t)y >= fb_words[1]) return;
    if ((uint64_t)len > 4u * fb_words[0]) len = (int64_t)(4u * fb_words[0]);
    memcpy(fb_base + (uint64_t)y * fb_words[2], px, (size_t)len);
}

static cint_status r_fb_open(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    (void)u; (void)a; (void)n;
    r->as.i64 = ci_fb_open();
    return CINT_OK;
}

static cint_status r_fb_word(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    (void)u; (void)n;
    r->as.u64 = ci_fb_word(a[0].as.i64);
    return CINT_OK;
}

static cint_status r_fb_row(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    int64_t y = a[0].as.i64, len = a[1].as.view.shape[0], stride = a[1].as.view.byte_stride[0];
    const uint8_t *src = (const uint8_t *)a[1].as.view.mem.u.host.ptr;
    uint8_t *dst;
    (void)u; (void)n; (void)r;
    if (fb_base == NULL || y < 0 || (uint64_t)y >= fb_words[1]) return CINT_OK;
    if ((uint64_t)len > 4u * fb_words[0]) len = (int64_t)(4u * fb_words[0]);
    dst = fb_base + (uint64_t)y * fb_words[2];
    for (int64_t i = 0; i < len; i++) dst[i] = src[i * stride];
    return CINT_OK;
}

static cint_status r_ev_read(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    uint8_t ev[24];
    ssize_t got;
    int64_t len, stride;
    uint8_t *dst;
    (void)u; (void)n;
    if (ev_fd < 0) {
        ev_fd = open("/dev/input/event0", O_RDONLY | O_NONBLOCK | O_CLOEXEC);
        if (ev_fd < 0) { r->as.i64 = -(int64_t)errno; return CINT_OK; }
    }
    got = read(ev_fd, ev, sizeof ev);
    if (got < 0) { r->as.i64 = errno == EAGAIN ? 0 : -(int64_t)errno; return CINT_OK; }
    if (got != (ssize_t)sizeof ev) { r->as.i64 = 0; return CINT_OK; }
    len = a[0].as.view.shape[0];
    stride = a[0].as.view.byte_stride[0];
    dst = (uint8_t *)a[0].as.view.mem.u.host.ptr;
    for (int64_t i = 0; i < len && i < 24; i++) dst[i * stride] = ev[i];
    r->as.i64 = 1;
    return CINT_OK;
}

static cint_status r_clock_ns(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    struct timespec ts;
    (void)u; (void)a; (void)n;
    if (clock_gettime(CLOCK_MONOTONIC, &ts) < 0) { r->as.i64 = -(int64_t)errno; return CINT_OK; }
    r->as.i64 = (int64_t)ts.tv_sec * 1000000000 + ts.tv_nsec;
    return CINT_OK;
}

#ifdef CI_ROWS_AUTH
static cint_status r_rand_fill(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    uint8_t buf[256];
    int64_t len = a[0].as.view.shape[0], stride = a[0].as.view.byte_stride[0];
    uint8_t *dst = (uint8_t *)a[0].as.view.mem.u.host.ptr;
    long got;
    (void)u; (void)n;
    if (len > (int64_t)sizeof buf) len = (int64_t)sizeof buf;
    got = syscall(SYS_getrandom, buf, (size_t)len, 0);
    if (got < 0) { r->as.i64 = -(int64_t)errno; return CINT_OK; }
    for (int64_t i = 0; i < (int64_t)got; i++) dst[i * stride] = buf[i];
    r->as.i64 = (int64_t)got;
    return CINT_OK;
}
#endif

#ifdef CI_ROWS_WALL
static cint_status r_wall_ns(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    struct timespec ts;
    (void)u; (void)a; (void)n;
    if (clock_gettime(CLOCK_BOOTTIME, &ts) < 0) { r->as.i64 = -(int64_t)errno; return CINT_OK; }
    r->as.i64 = (int64_t)ts.tv_sec * 1000000000 + ts.tv_nsec;
    return CINT_OK;
}
#endif

#ifdef CI_ROWS_REVOKE
/* GV-2 (docs/specs/2026-11-11-gv-revoke.md section 2): co_revoke(vpid, word), Daphnis's call 1008: the desk takes the
 * disk and network bits of word back from every process of vpid's window; the count changed, or -errno. */
static cint_status r_co_revoke(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    long v;
    (void)u; (void)n;
    v = syscall(1008, (long)a[0].as.i64, (long)a[1].as.i64, 0L, 0L);
    r->as.i64 = v < 0 ? -(int64_t)errno : (int64_t)v;
    return CINT_OK;
}
#endif

#ifdef CI_ROWS_SYSINFO
#include <sys/sysinfo.h>
/* KF-2 (docs/specs/2026-11-11-kf-facts.md section 2): co_sysinfo(rec), sysinfo (99) into rec's five words in the
 * order of user/ci/sysinfoctl.ci's SI_ names; 0, or -errno (-EINVAL for fewer than five words). */
static cint_status r_co_sysinfo(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    struct sysinfo si;
    int64_t w[5];
    (void)u; (void)n;
    if (a[0].as.view.shape[0] < 5) { r->as.i64 = -EINVAL; return CINT_OK; }
    if (sysinfo(&si) < 0) { r->as.i64 = -(int64_t)errno; return CINT_OK; }
    w[0] = (int64_t)si.uptime;
    w[1] = (int64_t)si.totalram;
    w[2] = (int64_t)si.freeram;
    w[3] = (int64_t)si.procs;
    w[4] = (int64_t)si.mem_unit;
    for (int i = 0; i < 5; i++)
        memcpy((uint8_t *)a[0].as.view.mem.u.host.ptr + i * a[0].as.view.byte_stride[0], &w[i], sizeof w[i]);
    r->as.i64 = 0;
    return CINT_OK;
}

/* co_ids(ids): the caller's pid and effective uid, for a program that binds no shctl rows. */
static cint_status r_co_ids(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    int64_t w[2];
    (void)u; (void)n;
    if (a[0].as.view.shape[0] < 2) { r->as.i64 = -EINVAL; return CINT_OK; }
    w[0] = (int64_t)getpid();
    w[1] = (int64_t)geteuid();
    for (int i = 0; i < 2; i++)
        memcpy((uint8_t *)a[0].as.view.mem.u.host.ptr + i * a[0].as.view.byte_stride[0], &w[i], sizeof w[i]);
    r->as.i64 = 0;
    return CINT_OK;
}
#endif

static cint_status r_exit_now(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    (void)u; (void)n; (void)r;
    _exit((int)a[0].as.i64);
}

static cint_status r_out_open(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    char path[4096];
    int64_t len = a[0].as.view.shape[0], stride = a[0].as.view.byte_stride[0];
    const uint8_t *src = (const uint8_t *)a[0].as.view.mem.u.host.ptr;
    (void)u; (void)n;
    if (len >= (int64_t)sizeof path) { r->as.i64 = -ENAMETOOLONG; return CINT_OK; }
    for (int64_t i = 0; i < len; i++) {
        path[i] = (char)src[i * stride];
        if (path[i] == '\0') { r->as.i64 = -EINVAL; return CINT_OK; }
    }
    path[len] = '\0';
    if (out_fd >= 0) close(out_fd);
    out_fd = open(path, O_WRONLY | O_CREAT | O_TRUNC, 0644);
    r->as.i64 = out_fd < 0 ? -(int64_t)errno : 0;
    return CINT_OK;
}

static cint_status r_out_put(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    uint8_t buf[4096];
    int64_t len = a[0].as.view.shape[0], stride = a[0].as.view.byte_stride[0], done = 0;
    const uint8_t *src = (const uint8_t *)a[0].as.view.mem.u.host.ptr;
    (void)u; (void)n;
    if (out_fd < 0) { r->as.i64 = -EBADF; return CINT_OK; }
    while (done < len) {
        int64_t k = len - done < (int64_t)sizeof buf ? len - done : (int64_t)sizeof buf, at = 0;
        for (int64_t i = 0; i < k; i++) buf[i] = src[(done + i) * stride];
        while (at < k) {
            ssize_t w = write(out_fd, buf + at, (size_t)(k - at));
            if (w <= 0) { r->as.i64 = w < 0 ? -(int64_t)errno : -EIO; return CINT_OK; }
            at += w;
        }
        done += k;
    }
    r->as.i64 = len;
    return CINT_OK;
}

/* A view's bytes into buf (at most cap): the count, or -1 when it is longer. */
static int64_t view_bytes(const cint_value *v, uint8_t *buf, int64_t cap)
{
    int64_t len = v->as.view.shape[0], stride = v->as.view.byte_stride[0];
    const uint8_t *src = (const uint8_t *)v->as.view.mem.u.host.ptr;
    if (len > cap) return -1;
    for (int64_t i = 0; i < len; i++) buf[i] = src[i * stride];
    return len;
}

/* DN-37: tile_ctl for FBIO_TILE_BUSY's sprite, a header of 20 bytes and 48 x 48 words at most. */
static cint_status r_tile_big(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    static uint8_t buf[20 + 4 * 48 * 48];
    (void)u; (void)n;
    memset(buf, 0, sizeof buf);
    if (view_bytes(&a[1], buf, (int64_t)sizeof buf) < 0) { r->as.i64 = -EINVAL; return CINT_OK; }
    if (tile_fd < 0) {
        tile_fd = open("/dev/fb0", O_RDWR | O_CLOEXEC);
        if (tile_fd < 0) { r->as.i64 = -(int64_t)errno; return CINT_OK; }
    }
    {
        int got = ioctl(tile_fd, (unsigned long)a[0].as.i64, buf);
        r->as.i64 = got < 0 ? -(int64_t)errno : got;
    }
    return CINT_OK;
}

static cint_status r_tile_ctl(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    uint8_t buf[64];
    (void)u; (void)n;
    memset(buf, 0, sizeof buf);
    if (view_bytes(&a[1], buf, (int64_t)sizeof buf) < 0) { r->as.i64 = -EINVAL; return CINT_OK; }
    if (tile_fd < 0) {
        tile_fd = open("/dev/fb0", O_RDWR | O_CLOEXEC);
        if (tile_fd < 0) { r->as.i64 = -(int64_t)errno; return CINT_OK; }
    }
    {
        int got = ioctl(tile_fd, (unsigned long)a[0].as.i64, buf);
        r->as.i64 = got < 0 ? -(int64_t)errno : got;
    }
    return CINT_OK;
}

#if defined(CI_ROWS_WIN) || defined(CI_WIN_C)
static int64_t win_ioctl(unsigned long req, void *arg)
{
    int fd = open("/dev/fb0", O_RDWR | O_CLOEXEC);
    int got;
    if (fd < 0) return -(int64_t)errno;
    got = ioctl(fd, req, arg);
    if (got < 0) got = -errno;
    close(fd);
    return got;
}

void ci_win_want(int64_t w, int64_t h)
{
    win_wh[0] = (uint32_t)w;
    win_wh[1] = (uint32_t)h;
}

int64_t ci_win_var(const uint8_t *v, int64_t n)
{
    uint8_t b[64];                     /* src/tile.ci VAR_LEN */
    memset(b, 0, sizeof b);
    memcpy(b, v, (size_t)(n < 0 ? 0 : n > 64 ? 64 : n));
    return win_ioctl(0x4688UL, b);
}

int64_t ci_win_resize(int64_t on)
{
    uint32_t o = on != 0 ? 1u : 0u;
    if (fb_base == NULL) {
        win_rs = o;
        return 0;
    }
    return win_ioctl(0x468AUL, &o);
}

int64_t ci_win_menu(const uint8_t *v, int64_t n)
{
    uint8_t b[4 + 32 * 38];        /* AM-2, AM-4 (kernel B's layout): u32 n, n up to 38 records of 32 bytes (FBIO_TILE_MENU) */
    memset(b, 0, sizeof b);
    memcpy(b, v, (size_t)(n < 0 ? 0 : n > (int64_t)sizeof b ? (int64_t)sizeof b : n));
    return win_ioctl(0x4691UL, b);
}
#endif

#ifdef CI_ROWS_WIN
static cint_status r_win_want(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    (void)u; (void)n;
    ci_win_want(a[0].as.i64, a[1].as.i64);
    r->as.i64 = 0;
    return CINT_OK;
}

/* RS-TTL section 6: the first 64 bytes of a longer v, where view_bytes would refuse it whole and the bar showed no name
 * (View's `Screenshot 2026-11-12 06.54.09.png`, 34 bytes, against 32). */
static cint_status r_win_var(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    uint8_t v[64];
    int64_t len = a[0].as.view.shape[0], stride = a[0].as.view.byte_stride[0];
    const uint8_t *src = (const uint8_t *)a[0].as.view.mem.u.host.ptr;
    (void)u; (void)n;
    memset(v, 0, sizeof v);
    if (len > (int64_t)sizeof v) len = (int64_t)sizeof v;
    for (int64_t i = 0; i < len; i++) v[i] = src[i * stride];
    r->as.i64 = ci_win_var(v, (int64_t)sizeof v);
    return CINT_OK;
}

static cint_status r_win_resize(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    (void)u; (void)n;
    r->as.i64 = ci_win_resize(a[0].as.i64);
    return CINT_OK;
}

static cint_status r_win_menu(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    uint8_t v[4 + 32 * 16];
    (void)u; (void)n;
    memset(v, 0, sizeof v);
    (void)view_bytes(&a[0], v, (int64_t)sizeof v);
    r->as.i64 = ci_win_menu(v, (int64_t)sizeof v);
    return CINT_OK;
}
#endif

#if defined(CI_ROWS_SURF) && defined(CI_ROWS_WIN)
/* RS-SURF: the surface unmapped, asked again at w x h and mapped; WANT's answer, or the open's or map's -errno. */
static cint_status r_fb_resize(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    int64_t st;
    (void)u; (void)n;
    if (fb_base != NULL) munmap(fb_base, (size_t)fb_words[4]);
    fb_base = NULL;
    win_got = 0;
    ci_win_want(a[0].as.i64, a[1].as.i64);
    st = ci_fb_open();
    r->as.i64 = st < 0 ? st : win_got;
    return CINT_OK;
}
#endif

#if defined(CI_ROWS_POINT) && defined(CI_ROWS_WIN)
static cint_status r_win_point(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    uint32_t o = a[0].as.i64 != 0 ? 1u : 0u;
    (void)u; (void)n;
    r->as.i64 = win_ioctl(0x468CUL, &o);
    return CINT_OK;
}
#endif

#ifdef CI_ROWS_PLACE
static cint_status r_tile_place(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    uint8_t buf[24 + 16 * 32];
    uint64_t at;
    (void)u; (void)n;
    memset(buf, 0, sizeof buf);
    if (view_bytes(&a[0], buf, (int64_t)sizeof buf) < 24) { r->as.i64 = -EINVAL; return CINT_OK; }
    at = (uint64_t)(uintptr_t)(buf + 24);
    for (int i = 0; i < 8; i++) buf[16 + i] = (uint8_t)(at >> (8 * i));
    if (tile_fd < 0) {
        tile_fd = open("/dev/fb0", O_RDWR | O_CLOEXEC);
        if (tile_fd < 0) { r->as.i64 = -(int64_t)errno; return CINT_OK; }
    }
    {
        int got = ioctl(tile_fd, 0x4685UL, buf);
        r->as.i64 = got < 0 ? -(int64_t)errno : got;
    }
    return CINT_OK;
}

#endif

#ifdef CI_ROWS_HDESK
#include <stdio.h>
#include <sys/reboot.h>
static cint_status r_power(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    (void)u; (void)n;
    if (a[0].as.i64 != 1 && a[0].as.i64 != 2) { r->as.i64 = -EINVAL; return CINT_OK; }
    r->as.i64 = reboot(a[0].as.i64 == 1 ? RB_POWER_OFF : RB_AUTOBOOT) < 0 ? -(int64_t)errno : 0;
    return CINT_OK;
}

static cint_status r_spawn_as(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    char path[256], name[32], env[512];
    char *envp[17];
    const char *home = "/";
    unsigned int pn = 0, envc = 0;
    int64_t len, elen;
    pid_t pid;
    (void)u; (void)n;
    len = view_bytes(&a[0], (uint8_t *)path, (int64_t)sizeof path - 1);
    if (len < 0) { r->as.i64 = -ENAMETOOLONG; return CINT_OK; }
    path[len] = '\0';
    if (strlen(path) != (size_t)len) { r->as.i64 = -EINVAL; return CINT_OK; }
    elen = view_bytes(&a[1], (uint8_t *)env, (int64_t)sizeof env);
    if (elen < 0) { r->as.i64 = -E2BIG; return CINT_OK; }
    if (elen > 0 && env[elen - 1] != '\0') { r->as.i64 = -EINVAL; return CINT_OK; }
    for (int64_t i = 0; i < elen; i += (int64_t)strlen(env + i) + 1) {
        if (envc == 16) { r->as.i64 = -E2BIG; return CINT_OK; }
        if (strncmp(env + i, "HOME=", 5) == 0) home = env + i + 5;
        envp[envc++] = env + i;
    }
    envp[envc] = NULL;
    if (ioctl((int)a[2].as.i64, TIOCGPTN, &pn) < 0) { r->as.i64 = -(int64_t)errno; return CINT_OK; }
    snprintf(name, sizeof name, "/dev/pts/%u", pn);
    pid = fork();
    if (pid < 0) { r->as.i64 = -(int64_t)errno; return CINT_OK; }
    if (pid == 0) {
        char *argv[2] = {path, NULL};
        int s = setsid() < 0 ? -1 : open(name, O_RDWR);
        if (s < 0 || dup2(s, 0) < 0 || dup2(s, 1) < 0 || dup2(s, 2) < 0) _exit(127);
        if (s > 2) close(s);
        /* A session keeps only its controlling terminal, across all 256 descriptor slots. */
        for (int fd = 3; fd < 256; fd++) {
            if (close(fd) < 0 && errno != EBADF) _exit(127);
        }
        if (syscall(1003, (long)a[3].as.i64, (long)a[4].as.i64, (long)a[5].as.i64) < 0) _exit(126);
        if (chdir(home) < 0) _exit(126);   /* FS-3: no fallback home */
        execve(path, argv, envp);
        _exit(127);
    }
    r->as.i64 = pid;
    return CINT_OK;
}

#include "homedirs.h"
#include "runas.h"

/* The runs as the account (user/ci/runas.h): the session's record, a job of the fixed table, its output, its end. */
static cint_status r_run_session(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    char home[RUN_HOME];
    int64_t len;
    (void)u; (void)n;
    len = view_bytes(&a[3], (uint8_t *)home, (int64_t)sizeof home);
    if (len < 0) { r->as.i64 = -EINVAL; return CINT_OK; }
    r->as.i64 = run_session((long)a[0].as.i64, (long)a[1].as.i64, (long)a[2].as.i64, home, (size_t)len);
    return CINT_OK;
}

static cint_status r_run_start(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    char arg[48 + 1 + 4096];
    int64_t len;
    (void)u; (void)n;
    len = view_bytes(&a[1], (uint8_t *)arg, (int64_t)sizeof arg);
    if (len < 0) { r->as.i64 = -E2BIG; return CINT_OK; }
    if (a[0].as.i64 < 0 || a[0].as.i64 >= RUN_JOBS) { r->as.i64 = -EINVAL; return CINT_OK; }
    r->as.i64 = run_start((int)a[0].as.i64, arg, (size_t)len);
    return CINT_OK;
}

static cint_status r_run_poll(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    unsigned char buf[65536];          /* a picture's stream comes in reads of a pipe's size */
    int64_t len = a[0].as.view.shape[0], stride = a[0].as.view.byte_stride[0];
    uint8_t *dst = (uint8_t *)a[0].as.view.mem.u.host.ptr;
    long got;
    (void)u; (void)n;
    if (len > (int64_t)sizeof buf) len = (int64_t)sizeof buf;
    got = run_poll(buf, (size_t)len);
    for (long i = 0; i < got; i++) dst[i * stride] = buf[i];
    r->as.i64 = got;
    return CINT_OK;
}

/* RS-KR (PR 372): the key repeat on the event device, the desk alone: rep_get(v) gives the delay and the period in
 * ms (EVIOCGREP), rep_set(delay, period) sets them (EVIOCSREP); 0, or -errno (-ENOTTY or -EINVAL on a kernel without
 * the request). */
static int rep_fd(void)
{
    if (ev_fd < 0) ev_fd = open("/dev/input/event0", O_RDONLY | O_NONBLOCK | O_CLOEXEC);
    return ev_fd;
}

static cint_status r_rep_get(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    unsigned int v[2] = {0u, 0u};
    int64_t len = a[0].as.view.shape[0], stride = a[0].as.view.byte_stride[0];
    int64_t *dst = (int64_t *)a[0].as.view.mem.u.host.ptr;
    (void)u; (void)n;
    if (rep_fd() < 0) { r->as.i64 = -(int64_t)errno; return CINT_OK; }
    if (ioctl(ev_fd, 0x80084503UL, v) < 0) { r->as.i64 = -(int64_t)errno; return CINT_OK; }
    if (len >= 2) {
        *(int64_t *)((uint8_t *)dst) = (int64_t)v[0];
        *(int64_t *)((uint8_t *)dst + stride) = (int64_t)v[1];
    }
    r->as.i64 = 0;
    return CINT_OK;
}

static cint_status r_rep_set(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    unsigned int v[2];
    (void)u; (void)n;
    if (a[0].as.i64 < 0 || a[0].as.i64 > 100000 || a[1].as.i64 < 0 || a[1].as.i64 > 100000) {
        r->as.i64 = -EINVAL;
        return CINT_OK;
    }
    v[0] = (unsigned int)a[0].as.i64;
    v[1] = (unsigned int)a[1].as.i64;
    if (rep_fd() < 0) { r->as.i64 = -(int64_t)errno; return CINT_OK; }
    r->as.i64 = ioctl(ev_fd, 0x40084503UL, v) < 0 ? -(int64_t)errno : 0;
    return CINT_OK;
}

static cint_status r_run_stop(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    (void)u; (void)a; (void)n;
    run_stop();
    r->as.i64 = 0;
    return CINT_OK;
}

/* LO-1: seat(uid) and sweep(uid), Daphnis's calls 1009 and 1010; -ENOSYS on Linux. */
static cint_status r_seat(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    long s;
    (void)u; (void)n;
    s = syscall(1009, (long)a[0].as.i64);
    r->as.i64 = s < 0 ? -(int64_t)errno : s;
    return CINT_OK;
}

static cint_status r_sweep(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    long s;
    (void)u; (void)n;
    s = syscall(1010, (long)a[0].as.i64);
    r->as.i64 = s < 0 ? -(int64_t)errno : s;
    return CINT_OK;
}

static cint_status r_home(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    char path[64];
    int64_t len;
    long s;
    (void)u; (void)n;
    len = view_bytes(&a[0], (uint8_t *)path, (int64_t)sizeof path - 1);
    if (len < 0) { r->as.i64 = -ENAMETOOLONG; return CINT_OK; }
    path[len] = '\0';
    s = syscall(1006, path, (long)a[1].as.i64, (long)a[2].as.i64);
    r->as.i64 = s < 0 ? -(int64_t)errno : 0;
    if (s >= 0) (void)home_folders(path, (long)a[1].as.i64, (long)a[2].as.i64);   /* RS-HOME */
    return CINT_OK;
}

static int auth_fd = -1;
static pid_t auth_pid = -1;

static cint_status r_auth_start(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    uint8_t req[640];   /* user/ci/authd.ci's REQ_MAX */
    int in[2], out[2];
    int64_t len;
    pid_t pid;
    (void)u; (void)n;
    if (auth_fd >= 0) { r->as.i64 = -EBUSY; return CINT_OK; }
    len = view_bytes(&a[0], req, (int64_t)sizeof req);
    if (len < 0) { r->as.i64 = -E2BIG; return CINT_OK; }
    if (pipe(in) < 0) { memset(req, 0, sizeof req); r->as.i64 = -(int64_t)errno; return CINT_OK; }
    if (pipe(out) < 0) {
        close(in[0]); close(in[1]); memset(req, 0, sizeof req);
        r->as.i64 = -(int64_t)errno;
        return CINT_OK;
    }
    pid = fork();
    if (pid < 0) {
        close(in[0]); close(in[1]); close(out[0]); close(out[1]); memset(req, 0, sizeof req);
        r->as.i64 = -(int64_t)errno;
        return CINT_OK;
    }
    if (pid == 0) {
        char *argv[2] = {"authd", NULL};
        char *envp[1] = {NULL};
        /* The helper starts without grants inherited from the desktop. */
        if (syscall(1000, 0UL) < 0 && errno != ENOSYS) _exit(127);
        if (dup2(in[0], 0) < 0 || dup2(out[1], 1) < 0) _exit(127);
        close(in[0]); close(in[1]); close(out[0]); close(out[1]);
        execve("/bin/authd", argv, envp);
        _exit(127);
    }
    close(in[0]);
    close(out[1]);
    for (int64_t off = 0; off < len;) {
        ssize_t w = write(in[1], req + off, (size_t)(len - off));
        if (w < 0 && errno == EINTR) continue;
        if (w <= 0) break;
        off += w;
    }
    memset(req, 0, sizeof req);
    close(in[1]);
    fcntl(out[0], F_SETFL, fcntl(out[0], F_GETFL) | O_NONBLOCK);
    auth_fd = out[0];
    auth_pid = pid;
    r->as.i64 = 0;
    return CINT_OK;
}

static cint_status r_auth_poll(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    uint8_t buf[256];
    int64_t len = a[0].as.view.shape[0], stride = a[0].as.view.byte_stride[0];
    uint8_t *dst = (uint8_t *)a[0].as.view.mem.u.host.ptr;
    ssize_t got;
    (void)u; (void)n;
    if (auth_fd < 0) { r->as.i64 = -ENOENT; return CINT_OK; }
    if (len > (int64_t)sizeof buf) len = (int64_t)sizeof buf;
    do {
        got = read(auth_fd, buf, (size_t)len);
    } while (got < 0 && errno == EINTR);
    if (got < 0) { r->as.i64 = -(int64_t)errno; return CINT_OK; }
    if (got == 0) {
        int st;
        close(auth_fd);
        auth_fd = -1;
        waitpid(auth_pid, &st, 0);
        auth_pid = -1;
        r->as.i64 = 0;
        return CINT_OK;
    }
    for (ssize_t i = 0; i < got; i++) dst[i * stride] = buf[i];
    r->as.i64 = (int64_t)got;
    return CINT_OK;
}

static cint_status r_tile_ask(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    uint8_t buf[64];
    int64_t len = a[3].as.view.shape[0], stride = a[3].as.view.byte_stride[0];
    uint8_t *dst = (uint8_t *)a[3].as.view.mem.u.host.ptr;
    (void)u; (void)n;
    memset(buf, 0, sizeof buf);
    for (int i = 0; i < 4; i++) {
        buf[i] = (uint8_t)((uint64_t)a[1].as.i64 >> (8 * i));
        buf[4 + i] = (uint8_t)((uint64_t)a[2].as.i64 >> (8 * i));
    }
    if (len > (int64_t)sizeof buf) len = (int64_t)sizeof buf;
    if (tile_fd < 0) {
        tile_fd = open("/dev/fb0", O_RDWR | O_CLOEXEC);
        if (tile_fd < 0) { r->as.i64 = -(int64_t)errno; return CINT_OK; }
    }
    {
        int got = ioctl(tile_fd, (unsigned long)a[0].as.i64, buf);
        r->as.i64 = got < 0 ? -(int64_t)errno : got;
    }
    for (int64_t i = 0; i < len; i++) dst[i * stride] = buf[i];
    return CINT_OK;
}

static cint_status r_pty_winsize(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    struct winsize ws;
    (void)u; (void)n;
    ws.ws_col = (unsigned short)a[1].as.i64;
    ws.ws_row = (unsigned short)a[2].as.i64;
    ws.ws_xpixel = (unsigned short)(8 * a[1].as.i64);
    ws.ws_ypixel = (unsigned short)(16 * a[2].as.i64);
    r->as.i64 = ioctl((int)a[0].as.i64, TIOCSWINSZ, &ws) < 0 ? -(int64_t)errno : 0;
    return CINT_OK;
}

static cint_status r_pty_sigsess(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    (void)u; (void)n;
    r->as.i64 = ioctl((int)a[0].as.i64, 0x5480, (unsigned long)a[1].as.i64) < 0 ? -(int64_t)errno : 0;
    return CINT_OK;
}

static cint_status r_pty_nonblock(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    int fl;
    (void)u; (void)n;
    fl = fcntl((int)a[0].as.i64, F_GETFL);
    r->as.i64 = fl < 0 || fcntl((int)a[0].as.i64, F_SETFL, fl | O_NONBLOCK) < 0 ? -(int64_t)errno : 0;
    return CINT_OK;
}

static cint_status r_fb_remap(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    (void)u; (void)a; (void)n;
    if (fb_base != NULL) munmap(fb_base, (size_t)fb_words[4]);
    fb_base = NULL;
    r->as.i64 = ci_fb_open();
    return CINT_OK;
}

/* RS-SHOT (docs/specs/2026-11-11-rs-rel-s1-units.md, RS-SHOT): the screen held still while an area is chosen, read
 * back for the picture plate, and a shot handed to /bin/shot, which runs as the account and writes the file. The desk
 * never writes into a home. */
#include <stdlib.h>

#define SHOT_MAX_W 3840
#define SHOT_MAX_H 2160
#define SHOT_SLOTS 4
#define SHOT_GRANT_DISK 1           /* src/fs.ci GRANT_DISK: all a shot needs of the account's ceiling */

static uint8_t *hold_px;            /* the held screen: hold_w x hold_h pixels of 4 bytes, rows packed; NULL: none */
static uint64_t hold_w, hold_h;
static pid_t shot_pid[SHOT_SLOTS];  /* a shot's child, 0 for a free slot */
static int shot_fd[SHOT_SLOTS];     /* the read end of its name pipe, valid while shot_pid is not 0 */

/* The held screen zeroed and freed: it holds a session's pixels. */
static void hold_drop(void)
{
    if (hold_px != NULL) {
        memset(hold_px, 0, (size_t)(4u * hold_w * hold_h));
        free(hold_px);
    }
    hold_px = NULL;
    hold_w = 0;
    hold_h = 0;
}

/* The size reads see: the held screen's, else the live framebuffer's at 32 bits a pixel; whether there is one. */
static int src_size(uint64_t *w, uint64_t *h)
{
    if (hold_px != NULL) {
        *w = hold_w;
        *h = hold_h;
        return 1;
    }
    if (fb_base == NULL || fb_words[3] != 32u) return 0;
    *w = fb_words[0];
    *h = fb_words[1];
    return 1;
}

/* Pixel (x, y) of the source; the caller has checked both against src_size. */
static const uint8_t *src_at(uint64_t x, uint64_t y)
{
    if (hold_px != NULL) return hold_px + 4u * (y * hold_w + x);
    return fb_base + y * fb_words[2] + 4u * x;
}

static cint_status r_fb_hold(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    uint64_t w, h;
    uint8_t *px;
    (void)u; (void)n;
    hold_drop();
    r->as.i64 = 0;
    if (a[0].as.i64 == 0) return CINT_OK;
    if (!src_size(&w, &h)) { r->as.i64 = -ENODEV; return CINT_OK; }
    px = (uint8_t *)malloc((size_t)(4u * w * h));
    if (px == NULL) { r->as.i64 = -ENOMEM; return CINT_OK; }
    for (uint64_t y = 0; y < h; y++) memcpy(px + 4u * w * y, src_at(0, y), (size_t)(4u * w));
    hold_px = px;
    hold_w = w;
    hold_h = h;
    return CINT_OK;
}

static cint_status r_fb_peek(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    int64_t x = a[0].as.i64, y = a[1].as.i64;
    int64_t len = a[2].as.view.shape[0], stride = a[2].as.view.byte_stride[0];
    uint8_t *dst = (uint8_t *)a[2].as.view.mem.u.host.ptr;
    uint64_t w, h, k;
    const uint8_t *s;
    (void)u; (void)n;
    if (!src_size(&w, &h) || x < 0 || y < 0 || (uint64_t)x >= w || (uint64_t)y >= h) {
        r->as.i64 = -EINVAL;
        return CINT_OK;
    }
    k = (uint64_t)len / 4u;
    if (k > w - (uint64_t)x) k = w - (uint64_t)x;
    s = src_at((uint64_t)x, (uint64_t)y);
    for (uint64_t i = 0; i < 4u * k; i++) dst[(int64_t)i * stride] = s[i];
    r->as.i64 = (int64_t)k;
    return CINT_OK;
}

/* "/home/" and an account name (acct.ci name_ok: 1 to 32 of a-z, 0-9 and '-', not starting with '-'). */
static int shot_home_ok(const char *p, int64_t n)
{
    if (n < 7 || n > 38 || memcmp(p, "/home/", 6) != 0 || p[6] == '-') return 0;
    for (int64_t i = 6; i < n; i++) {
        char c = p[i];
        if (!((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '-')) return 0;
    }
    return 1;
}

/* The name /bin/shot printed: "Screenshot ", then letters, digits, ' ', '-' and '.', ending ".png"; 64 at most. */
static int shot_name_ok(const char *p, int64_t n)
{
    if (n < 15 || n > 64 || memcmp(p, "Screenshot ", 11) != 0 || memcmp(p + n - 4, ".png", 4) != 0) return 0;
    for (int64_t i = 0; i < n; i++) {
        char c = p[i];
        if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == ' ' || c == '-' ||
              c == '.')) return 0;
    }
    return 1;
}

static int shot_write_all(int fd, const uint8_t *b, size_t n)
{
    while (n > 0) {
        ssize_t w = write(fd, b, n);
        if (w < 0 && errno == EINTR) continue;
        if (w <= 0) return 0;
        b += w;
        n -= (size_t)w;
    }
    return 1;
}

/* The seconds since 1970 a shot is named for: the bar's date (FBIO_TILE_INFO kind 2, its u64 at byte 16) on the
 * descriptor the desk's own asks opened, the clock the person reads; the host's clock where there is none or the ask
 * is refused (off Daphnis). Never shot's CLOCK_REALTIME: Daphnis starts it at the boot's second in a new process. */
static uint64_t shot_date(void)
{
    uint8_t b[64];
    uint64_t s = 0;
    memset(b, 0, sizeof b);
    b[0] = 2;
    if (tile_fd < 0 || ioctl(tile_fd, 0x4687UL, b) != 0) return (uint64_t)time(NULL);
    for (int k = 0; k < 8; k++) s |= (uint64_t)b[16 + k] << (8 * k);
    return s;
}

/* The ceiling a shot logs in with: Disk alone of the account's, so Net and Audio stay out of its reach. */
static long shot_ceil(int64_t c)
{
    return (long)(c & SHOT_GRANT_DISK);
}

/* The shot's child of the desk: login first (nothing runs as uid 0 after a refusal), then only the name pipe as
 * descriptors 1 and 2 (a message from shot makes shot_end refuse the name; nothing running as the account holds the
 * desk's log or its input), the home, and /bin/shot with the pixels on a pipe as descriptor 0. Its status is shot's,
 * 126 when a step before the fork fails, 125 when shot did not end by itself.
 * The child keeps a copy of the desk's memory, as the account, until shot ends. No process of the account can read
 * it while Daphnis has no ptrace, no process_vm_readv and no /proc (src/proc.ci); revisit this the day any of the
 * three exists. */
static void shot_child(const uint8_t *px, int64_t w, int64_t h, uint64_t date, const cint_value *a, const char *home,
                       int name_w)
{
    static char path[] = "/bin/shot";
    static char arg0[] = "shot";
    char *argv[2] = {arg0, NULL};
    char *envp[1] = {NULL};
    struct sigaction sa;
    uint8_t head[20];
    int pp[2], st = 0;
    pid_t s;
    if (syscall(1003, (long)a[4].as.i64, (long)a[5].as.i64, shot_ceil(a[6].as.i64)) < 0) _exit(126);
    if (setsid() < 0 || dup2(name_w, 1) < 0 || dup2(name_w, 2) < 0) _exit(126);
    if (close(0) < 0 && errno != EBADF) _exit(126);
    /* Daphnis gives a process 256 descriptors (src/fs.ci FDS), so 3 to 255 is every other one. */
    for (int fd = 3; fd < 256; fd++) {
        if (close(fd) < 0 && errno != EBADF) _exit(126);
    }
    if (chdir(home) < 0) _exit(126);
    memset(&sa, 0, sizeof sa);
    sa.sa_handler = SIG_IGN;
    if (sigaction(SIGPIPE, &sa, NULL) < 0 || pipe(pp) < 0) _exit(126);
    s = fork();
    if (s < 0) _exit(126);
    if (s == 0) {
        sa.sa_handler = SIG_DFL;
        if (sigaction(SIGPIPE, &sa, NULL) < 0 || dup2(pp[0], 0) < 0) _exit(127);
        if (pp[0] != 0) close(pp[0]);
        close(pp[1]);
        execve(path, argv, envp);
        _exit(127);
    }
    close(pp[0]);
    close(1);
    close(2);
    for (int k = 0; k < 4; k++) {
        head[k] = (uint8_t)((uint64_t)w >> (8 * k));
        head[4 + k] = (uint8_t)((uint64_t)h >> (8 * k));
        head[8 + k] = (uint8_t)((uint64_t)(4 * w) >> (8 * k));
    }
    for (int k = 0; k < 8; k++) head[12 + k] = (uint8_t)(date >> (8 * k));
    if (shot_write_all(pp[1], head, sizeof head)) (void)shot_write_all(pp[1], px, (size_t)(4 * w * h));
    close(pp[1]);
    while (waitpid(s, &st, 0) < 0) {
        if (errno != EINTR) _exit(125);
    }
    _exit(WIFEXITED(st) ? WEXITSTATUS(st) : 125);
}

static cint_status r_shot_as(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    int64_t x = a[0].as.i64, y = a[1].as.i64, w = a[2].as.i64, h = a[3].as.i64, len;
    char home[40];
    uint64_t sw, sh, date;
    uint8_t *px;
    int np[2], slot = -1, e;
    pid_t pid;
    (void)u; (void)n;
    len = view_bytes(&a[7], (uint8_t *)home, (int64_t)sizeof home - 1);
    if (len < 0 || !shot_home_ok(home, len)) { r->as.i64 = -EINVAL; return CINT_OK; }
    home[len] = '\0';
    if (!src_size(&sw, &sh) || x < 0 || y < 0 || w < 1 || h < 1 || w > SHOT_MAX_W || h > SHOT_MAX_H ||
        (uint64_t)w > sw || (uint64_t)h > sh || (uint64_t)x > sw - (uint64_t)w || (uint64_t)y > sh - (uint64_t)h) {
        r->as.i64 = -EINVAL;
        return CINT_OK;
    }
    for (int i = SHOT_SLOTS - 1; i >= 0; i--) {
        if (shot_pid[i] == 0) slot = i;
    }
    if (slot < 0) { r->as.i64 = -EBUSY; return CINT_OK; }
    px = (uint8_t *)malloc((size_t)(4 * w * h));
    if (px == NULL) { r->as.i64 = -ENOMEM; return CINT_OK; }
    for (int64_t j = 0; j < h; j++) memcpy(px + 4 * w * j, src_at((uint64_t)x, (uint64_t)(y + j)), (size_t)(4 * w));
    date = shot_date();
    /* The name pipe's read end stays in the desk: never inherited by the desk's other children, never blocking. */
    e = pipe(np) < 0 ? errno : 0;
    if (e == 0 && (fcntl(np[0], F_SETFD, FD_CLOEXEC) < 0 || fcntl(np[0], F_SETFL, O_NONBLOCK) < 0)) {
        e = errno;
        close(np[0]);
        close(np[1]);
    }
    if (e != 0) {
        memset(px, 0, (size_t)(4 * w * h));
        free(px);
        r->as.i64 = -(int64_t)e;
        return CINT_OK;
    }
    pid = fork();
    if (pid == 0) shot_child(px, w, h, date, a, home, np[1]);
    e = errno;
    close(np[1]);
    memset(px, 0, (size_t)(4 * w * h));
    free(px);
    if (pid < 0) {
        close(np[0]);
        r->as.i64 = -(int64_t)e;
        return CINT_OK;
    }
    shot_pid[slot] = pid;
    shot_fd[slot] = np[0];
    r->as.i64 = pid;
    return CINT_OK;
}

static cint_status r_shot_end(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    int64_t len = a[1].as.view.shape[0], stride = a[1].as.view.byte_stride[0];
    uint8_t *dst = (uint8_t *)a[1].as.view.mem.u.host.ptr;
    char buf[80];
    int64_t k = 0;
    ssize_t got;
    int slot = -1;
    (void)u; (void)n;
    for (int i = 0; i < SHOT_SLOTS; i++) {
        if (shot_pid[i] != 0 && shot_pid[i] == (pid_t)a[0].as.i64) slot = i;
    }
    if (slot < 0) { r->as.i64 = -ENOENT; return CINT_OK; }
    /* The child not yet reaped (running, or ended and not waited for): its name may still come; the slot stays. */
    if (kill(shot_pid[slot], 0) == 0) { r->as.i64 = -EBUSY; return CINT_OK; }
    for (;;) {
        got = read(shot_fd[slot], buf + k, sizeof buf - (size_t)k);
        if (got < 0 && errno == EINTR) continue;
        if (got <= 0) break;
        k += got;
        if (k == (int64_t)sizeof buf) break;
    }
    close(shot_fd[slot]);
    shot_pid[slot] = 0;
    shot_fd[slot] = -1;
    if (k < 1 || buf[k - 1] != '\n' || !shot_name_ok(buf, k - 1)) { r->as.i64 = -EINVAL; return CINT_OK; }
    if (k - 1 > len) { r->as.i64 = -E2BIG; return CINT_OK; }
    for (int64_t i = 0; i < k - 1; i++) dst[i * stride] = (uint8_t)buf[i];
    r->as.i64 = k - 1;
    return CINT_OK;
}
#endif

static cint_status r_spawn(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    char path[256];
    int64_t len;
    pid_t pid;
    (void)u; (void)n;
    len = view_bytes(&a[0], (uint8_t *)path, (int64_t)sizeof path - 1);
    if (len < 0) { r->as.i64 = -ENAMETOOLONG; return CINT_OK; }
    path[len] = '\0';
    if (strlen(path) != (size_t)len) { r->as.i64 = -EINVAL; return CINT_OK; }
    pid = fork();
    if (pid < 0) { r->as.i64 = -(int64_t)errno; return CINT_OK; }
    if (pid == 0) {
        char *argv[2] = {path, NULL};
        char *envp[1] = {NULL};
        execve(path, argv, envp);
        _exit(127);
    }
    r->as.i64 = pid;
    return CINT_OK;
}

static cint_status r_reap(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    int st = 0;
    pid_t got;
    (void)u; (void)n;
    do {
        got = waitpid((pid_t)a[0].as.i64, &st, a[1].as.i64 != 0 ? WNOHANG : 0);
    } while (got < 0 && errno == EINTR);
    r->as.i64 = got < 0 ? -(int64_t)errno : got == 0 ? -EAGAIN : st;
    return CINT_OK;
}

static cint_status r_stop(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    (void)u; (void)n;
    r->as.i64 = kill((pid_t)a[0].as.i64, (int)a[1].as.i64) < 0 ? -(int64_t)errno : 0;
    return CINT_OK;
}

static cint_status r_fb_span(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    int64_t y = a[0].as.i64, x = a[1].as.i64, len = a[2].as.view.shape[0], stride = a[2].as.view.byte_stride[0];
    const uint8_t *src = (const uint8_t *)a[2].as.view.mem.u.host.ptr;
    uint8_t *dst;
    (void)u; (void)n;
    if (fb_base == NULL) { r->as.i64 = -1; return CINT_OK; }
    r->as.i64 = 0;
    if (y < 0 || (uint64_t)y >= fb_words[1] || x < 0 || (uint64_t)x >= fb_words[0]) return CINT_OK;
    if ((uint64_t)len > fb_words[0] - (uint64_t)x) len = (int64_t)(fb_words[0] - (uint64_t)x);
    dst = fb_base + (uint64_t)y * fb_words[2] + 4u * (uint64_t)x;
    if (stride == 4) { memcpy(dst, src, (size_t)(4 * len)); return CINT_OK; }   /* D-ROW: a run, one copy */
    for (int64_t i = 0; i < len; i++) memcpy(dst + 4 * i, src + i * stride, 4u);
    return CINT_OK;
}
#ifdef CI_ROWS_NET
#include <netinet/in.h>
#include <sys/socket.h>
#include <sys/time.h>

static uint64_t udp_src[2];

static int64_t copy_in(const cint_value *v, uint8_t *dst, int64_t most)
{
    int64_t len = v->as.view.shape[0], stride = v->as.view.byte_stride[0];
    const uint8_t *src = (const uint8_t *)v->as.view.mem.u.host.ptr;
    if (len > most) return -1;
    for (int64_t i = 0; i < len; i++) dst[i] = src[i * stride];
    return len;
}

static cint_status r_udp_open(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    struct timeval tv = {2, 0};
    int fd;
    (void)u; (void)a; (void)n;
    fd = socket(AF_INET, SOCK_DGRAM, 0);
    if (fd < 0) { r->as.i64 = -(int64_t)errno; return CINT_OK; }
    (void)setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof tv);
    r->as.i64 = fd;
    return CINT_OK;
}

static cint_status r_udp_send(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    uint8_t buf[1500];
    struct sockaddr_in to;
    int64_t len = copy_in(&a[3], buf, (int64_t)sizeof buf);
    ssize_t w;
    (void)u; (void)n;
    if (len < 0 || a[2].as.i64 < 0 || a[2].as.i64 > 65535) { r->as.i64 = -EINVAL; return CINT_OK; }
    memset(&to, 0, sizeof to);
    to.sin_family = AF_INET;
    to.sin_port = htons((uint16_t)a[2].as.i64);
    to.sin_addr.s_addr = htonl((uint32_t)a[1].as.u64);
    w = sendto((int)a[0].as.i64, buf, (size_t)len, 0, (const struct sockaddr *)&to, sizeof to);
    r->as.i64 = w < 0 ? -(int64_t)errno : (int64_t)w;
    return CINT_OK;
}

static cint_status r_udp_recv(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    uint8_t buf[1500];
    struct sockaddr_in from;
    socklen_t fl = sizeof from;
    int64_t len = a[1].as.view.shape[0], stride = a[1].as.view.byte_stride[0];
    uint8_t *dst = (uint8_t *)a[1].as.view.mem.u.host.ptr;
    ssize_t got;
    (void)u; (void)n;
    got = recvfrom((int)a[0].as.i64, buf, sizeof buf, 0, (struct sockaddr *)&from, &fl);
    if (got < 0) { r->as.i64 = -(int64_t)errno; return CINT_OK; }
    udp_src[0] = ntohl(from.sin_addr.s_addr);
    udp_src[1] = ntohs(from.sin_port);
    if ((int64_t)got > len) got = (ssize_t)len;
    for (int64_t i = 0; i < (int64_t)got; i++) dst[i * stride] = buf[i];
    r->as.i64 = (int64_t)got;
    return CINT_OK;
}

static cint_status r_udp_from(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    (void)u; (void)n;
    r->as.u64 = a[0].as.i64 >= 0 && a[0].as.i64 < 2 ? udp_src[a[0].as.i64] : 0u;
    return CINT_OK;
}

static cint_status r_stdout_put(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    uint8_t buf[1500];
    int64_t len = copy_in(&a[0], buf, (int64_t)sizeof buf), at = 0;
    (void)u; (void)n;
    if (len < 0) { r->as.i64 = -EINVAL; return CINT_OK; }
    while (at < len) {
        ssize_t w = write(1, buf + at, (size_t)(len - at));
        if (w <= 0) { r->as.i64 = w < 0 ? -(int64_t)errno : -EIO; return CINT_OK; }
        at += w;
    }
    r->as.i64 = len;
    return CINT_OK;
}
#endif

#ifdef CI_ROWS_TCP
#include <netinet/in.h>
#include <sys/socket.h>

static cint_status r_tcp_listen(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    struct sockaddr_in at;
    int fd;
    (void)u; (void)n;
    fd = socket(AF_INET, SOCK_STREAM, 0);
    if (fd < 0) { r->as.i64 = -(int64_t)errno; return CINT_OK; }
    memset(&at, 0, sizeof at);
    at.sin_family = AF_INET;
    at.sin_port = htons((uint16_t)a[0].as.i64);
    if (bind(fd, (const struct sockaddr *)&at, sizeof at) < 0 || listen(fd, 1) < 0) {
        r->as.i64 = -(int64_t)errno;
        close(fd);
        return CINT_OK;
    }
    r->as.i64 = fd;
    return CINT_OK;
}

static cint_status r_tcp_accept(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    int fd;
    (void)u; (void)n;
    fd = accept((int)a[0].as.i64, NULL, NULL);
    r->as.i64 = fd < 0 ? -(int64_t)errno : fd;
    return CINT_OK;
}

static cint_status r_tcp_connect(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    struct sockaddr_in at;
    int fd;
    (void)u; (void)n;
    fd = socket(AF_INET, SOCK_STREAM, 0);
    if (fd < 0) { r->as.i64 = -(int64_t)errno; return CINT_OK; }
    memset(&at, 0, sizeof at);
    at.sin_family = AF_INET;
    at.sin_port = htons((uint16_t)a[1].as.i64);
    at.sin_addr.s_addr = htonl((uint32_t)a[0].as.u64);
    if (connect(fd, (const struct sockaddr *)&at, sizeof at) < 0) {
        r->as.i64 = -(int64_t)errno;
        close(fd);
        return CINT_OK;
    }
    r->as.i64 = fd;
    return CINT_OK;
}

#endif
#if defined(CI_ROWS_TCP) || defined(CI_ROWS_SH)   /* the N-3 descriptor rows, shared with cish */
static cint_status r_fd_read(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    uint8_t buf[4096];
    int64_t len = a[1].as.view.shape[0], stride = a[1].as.view.byte_stride[0];
    uint8_t *dst = (uint8_t *)a[1].as.view.mem.u.host.ptr;
    ssize_t got;
    (void)u; (void)n;
    if (stride == 1) {   /* a contiguous view: one read straight into it, at its whole length */
        got = read((int)a[0].as.i64, dst, (size_t)len);
        r->as.i64 = got < 0 ? -(int64_t)errno : (int64_t)got;
        return CINT_OK;
    }
    got = read((int)a[0].as.i64, buf, (size_t)(len < (int64_t)sizeof buf ? len : (int64_t)sizeof buf));
    if (got < 0) { r->as.i64 = -(int64_t)errno; return CINT_OK; }
    for (int64_t i = 0; i < (int64_t)got; i++) dst[i * stride] = buf[i];
    r->as.i64 = (int64_t)got;
    return CINT_OK;
}

static cint_status r_fd_write(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    uint8_t buf[4096];
    int64_t len = a[1].as.view.shape[0], stride = a[1].as.view.byte_stride[0], done = 0;
    const uint8_t *src = (const uint8_t *)a[1].as.view.mem.u.host.ptr;
    (void)u; (void)n;
    while (done < len) {   /* a contiguous view goes whole; a strided one through buf, 4,096 bytes at a time */
        int64_t k = len - done, at = 0;
        const uint8_t *p = src + done;
        if (stride != 1) {
            if (k > (int64_t)sizeof buf) k = (int64_t)sizeof buf;
            for (int64_t i = 0; i < k; i++) buf[i] = src[(done + i) * stride];
            p = buf;
        }
        while (at < k) {
            ssize_t w = write((int)a[0].as.i64, p + at, (size_t)(k - at));
            if (w <= 0) { r->as.i64 = w < 0 ? -(int64_t)errno : -EIO; return CINT_OK; }
            at += w;
        }
        done += k;
    }
    r->as.i64 = len;
    return CINT_OK;
}

static cint_status r_fd_close(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    (void)u; (void)n;
    r->as.i64 = close((int)a[0].as.i64) < 0 ? -(int64_t)errno : 0;
    return CINT_OK;
}
#endif

#ifdef CI_ROWS_TLS
#include "bearssl.h"
#include "anchors.h"

static br_ssl_client_context tls_sc;
static br_x509_minimal_context tls_xc;
static br_sslio_context tls_io;
static unsigned char tls_buf[BR_SSL_BUFSIZE_BIDI];
static int tls_fd = -1;

static int tls_low_read(void *ctx, unsigned char *buf, size_t len)
{
    for (;;) {
        ssize_t got = read(*(int *)ctx, buf, len);
        if (got > 0) return (int)got;
        if (got < 0 && errno == EINTR) continue;
        return -1;
    }
}

static int tls_low_write(void *ctx, const unsigned char *buf, size_t len)
{
    for (;;) {
        ssize_t w = write(*(int *)ctx, buf, len);
        if (w > 0) return (int)w;
        if (w < 0 && errno == EINTR) continue;
        return -1;
    }
}

static int64_t tls_failure(void)
{
    int err = br_ssl_engine_last_error(&tls_sc.eng);
    return -(1000 + (int64_t)(err ? err : BR_ERR_IO));
}

static cint_status r_tls_open(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    char host[254];
    unsigned char seed[32];
    int64_t len;
    long got;
    int mock;
    (void)u; (void)n;
    len = view_bytes(&a[1], (uint8_t *)host, (int64_t)sizeof host - 1);
    if (len < 0) { r->as.i64 = -ENAMETOOLONG; return CINT_OK; }
    host[len] = '\0';
    if (strlen(host) != (size_t)len) { r->as.i64 = -EINVAL; return CINT_OK; }
    got = syscall(SYS_getrandom, seed, sizeof seed, 0);
    if (got != (long)sizeof seed) { r->as.i64 = got < 0 ? -(int64_t)errno : -EIO; return CINT_OK; }
    mock = len > 5 && memcmp(host + len - 5, ".mock", 5) == 0;
    br_ssl_client_init_full(&tls_sc, &tls_xc, mock ? TA_MOCK : TA_PUBLIC, mock ? TA_MOCK_N : TA_PUBLIC_N);
    br_ssl_engine_set_versions(&tls_sc.eng, BR_TLS12, BR_TLS12);
    br_ssl_engine_set_buffer(&tls_sc.eng, tls_buf, sizeof tls_buf, 1);
    br_ssl_engine_inject_entropy(&tls_sc.eng, seed, sizeof seed);
    memset(seed, 0, sizeof seed);
    /* A-6: a server that closes first (the real API after an error) must not kill agent on Linux when close_notify
       goes out; Daphnis has no SIGPIPE and takes rt_sigaction as nothing to do. */
    signal(SIGPIPE, SIG_IGN);
    tls_fd = (int)a[0].as.i64;
    if (!br_ssl_client_reset(&tls_sc, host, 0)) { r->as.i64 = tls_failure(); return CINT_OK; }
    br_sslio_init(&tls_io, &tls_sc.eng, tls_low_read, &tls_fd, tls_low_write, &tls_fd);
    r->as.i64 = br_sslio_flush(&tls_io) < 0 ? tls_failure() : 0;
    return CINT_OK;
}

static cint_status r_tls_read(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    uint8_t buf[4096];
    int64_t len = a[0].as.view.shape[0], stride = a[0].as.view.byte_stride[0];
    uint8_t *dst = (uint8_t *)a[0].as.view.mem.u.host.ptr;
    int got;
    (void)u; (void)n;
    got = br_sslio_read(&tls_io, buf, (size_t)(len < (int64_t)sizeof buf ? len : (int64_t)sizeof buf));
    if (got < 0) {
        r->as.i64 = br_ssl_engine_last_error(&tls_sc.eng) == BR_ERR_OK ? 0 : tls_failure();
        return CINT_OK;
    }
    for (int64_t i = 0; i < (int64_t)got; i++) dst[i * stride] = buf[i];
    r->as.i64 = got;
    return CINT_OK;
}

static cint_status r_tls_write(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    uint8_t buf[4096];
    int64_t len;
    (void)u; (void)n;
    len = view_bytes(&a[0], buf, (int64_t)sizeof buf);
    if (len < 0) { r->as.i64 = -EINVAL; return CINT_OK; }
    if (br_sslio_write_all(&tls_io, buf, (size_t)len) < 0 || br_sslio_flush(&tls_io) < 0) {
        r->as.i64 = tls_failure();
        return CINT_OK;
    }
    r->as.i64 = len;
    return CINT_OK;
}

static cint_status r_tls_close(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    (void)u; (void)a; (void)n;
    /* A peer close that tls_read processed has already been answered. */
    if (tls_sc.eng.shutdown_recv) { r->as.i64 = 0; return CINT_OK; }
    /* The close notification goes out without reading again. A complete HTTP
       frame needs no further input; a peer may never answer the notification. */
    br_ssl_engine_close(&tls_sc.eng);
    for (;;) {
        size_t len;
        unsigned char *buf = br_ssl_engine_sendrec_buf(&tls_sc.eng, &len);
        int written;
        if (buf == NULL || len == 0) break;
        written = tls_low_write(&tls_fd, buf, len);
        if (written < 0) { r->as.i64 = tls_failure(); return CINT_OK; }
        br_ssl_engine_sendrec_ack(&tls_sc.eng, (size_t)written);
    }
    r->as.i64 = br_ssl_engine_last_error(&tls_sc.eng) == BR_ERR_OK ? 0 : tls_failure();
    return CINT_OK;
}
#endif

#ifdef CI_ROWS_PTY
#include <stdio.h>
#include <termios.h>

static cint_status r_pty_open(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    int m, unlock = 0;
    struct winsize ws;
    (void)u; (void)n;
    m = open("/dev/ptmx", O_RDWR | O_NOCTTY | O_CLOEXEC);
    if (m < 0) { r->as.i64 = -(int64_t)errno; return CINT_OK; }
    ws.ws_col = (unsigned short)a[0].as.i64;
    ws.ws_row = (unsigned short)a[1].as.i64;
    ws.ws_xpixel = (unsigned short)(8 * a[0].as.i64);
    ws.ws_ypixel = (unsigned short)(16 * a[1].as.i64);
    if (ioctl(m, TIOCSPTLCK, &unlock) < 0 || ioctl(m, TIOCSWINSZ, &ws) < 0) {
        r->as.i64 = -(int64_t)errno;
        close(m);
        return CINT_OK;
    }
    r->as.i64 = m;
    return CINT_OK;
}

static cint_status r_pty_spawn(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    char path[256], name[32], env[512];
    char *envp[17];
    unsigned int pn = 0, envc = 0;
    int64_t len, elen;
    pid_t pid;
    (void)u; (void)n;
    len = view_bytes(&a[0], (uint8_t *)path, (int64_t)sizeof path - 1);
    if (len < 0) { r->as.i64 = -ENAMETOOLONG; return CINT_OK; }
    path[len] = '\0';
    if (strlen(path) != (size_t)len) { r->as.i64 = -EINVAL; return CINT_OK; }
    elen = view_bytes(&a[1], (uint8_t *)env, (int64_t)sizeof env);
    if (elen < 0) { r->as.i64 = -E2BIG; return CINT_OK; }
    if (elen > 0 && env[elen - 1] != '\0') { r->as.i64 = -EINVAL; return CINT_OK; }
    for (int64_t i = 0; i < elen; i += (int64_t)strlen(env + i) + 1) {
        if (envc == 16) { r->as.i64 = -E2BIG; return CINT_OK; }
        envp[envc++] = env + i;
    }
    envp[envc] = NULL;
    if (ioctl((int)a[2].as.i64, TIOCGPTN, &pn) < 0) { r->as.i64 = -(int64_t)errno; return CINT_OK; }
    snprintf(name, sizeof name, "/dev/pts/%u", pn);
    pid = fork();
    if (pid < 0) { r->as.i64 = -(int64_t)errno; return CINT_OK; }
    if (pid == 0) {
        char *argv[2] = {path, NULL};
        int s = setsid() < 0 ? -1 : open(name, O_RDWR);
        if (s < 0 || dup2(s, 0) < 0 || dup2(s, 1) < 0 || dup2(s, 2) < 0) _exit(127);
        if (s > 2) close(s);
        execve(path, argv, envp);
        _exit(127);
    }
    r->as.i64 = pid;
    return CINT_OK;
}

static cint_status r_pty_read(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    uint8_t buf[4096];
    int64_t len = a[1].as.view.shape[0], stride = a[1].as.view.byte_stride[0];
    uint8_t *dst = (uint8_t *)a[1].as.view.mem.u.host.ptr;
    ssize_t got;
    (void)u; (void)n;
    if (len > (int64_t)sizeof buf) len = (int64_t)sizeof buf;
    do {
        got = read((int)a[0].as.i64, buf, (size_t)len);
    } while (got < 0 && errno == EINTR);
    if (got < 0) { r->as.i64 = -(int64_t)errno; return CINT_OK; }
    if (stride == 1) {
        if (got > 0) memcpy(dst, buf, (size_t)got);
    } else {
        for (ssize_t i = 0; i < got; i++) dst[i * stride] = buf[i];
    }
    r->as.i64 = got;
    return CINT_OK;
}

static cint_status r_pty_write(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    uint8_t buf[512];
    int64_t len = view_bytes(&a[1], buf, (int64_t)sizeof buf);
    ssize_t w;
    (void)u; (void)n;
    if (len < 0) { r->as.i64 = -EINVAL; return CINT_OK; }
    w = write((int)a[0].as.i64, buf, (size_t)len);
    r->as.i64 = w < 0 ? -(int64_t)errno : w;
    return CINT_OK;
}
#endif

#ifdef CI_ROWS_DSP
/* AU-3 (user/ci/dspdev.ci): /dev/dsp, the OSS subset of docs/specs/2026-11-06-au-audio.md section 4.
 *   dsp_open() -> I64: opens /dev/dsp for writing and asks for S16LE, 2 channels, 48,000 Hz; 0, -errno, or -EINVAL
 *     when the device answers another format.
 *   dsp_put(in U8[_] bytes) -> I64: writes bytes whole; the count, or -errno (-EBADF before dsp_open).
 *   dsp_sync() -> I64: SNDCTL_DSP_SYNC: returns once the device has played what was written; 0, or -errno. */
static int dsp_fd = -1;

static cint_status r_dsp_open(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    static const unsigned long req[3] = {0xC0045005ul, 0xC0045006ul, 0xC0045002ul};   /* SETFMT, CHANNELS, SPEED */
    static const int want[3] = {0x10, 2, 48000};
    (void)u; (void)a; (void)n;
    if (dsp_fd >= 0) close(dsp_fd);
    dsp_fd = open("/dev/dsp", O_WRONLY);
    if (dsp_fd < 0) { r->as.i64 = -(int64_t)errno; return CINT_OK; }
    for (int i = 0; i < 3; i++) {
        int v = want[i];
        if (ioctl(dsp_fd, req[i], &v) < 0) { r->as.i64 = -(int64_t)errno; return CINT_OK; }
        if (v != want[i]) { r->as.i64 = -EINVAL; return CINT_OK; }
    }
    r->as.i64 = 0;
    return CINT_OK;
}

static cint_status r_dsp_put(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    const uint8_t *src = (const uint8_t *)a[0].as.view.mem.u.host.ptr;
    int64_t len = a[0].as.view.shape[0], stride = a[0].as.view.byte_stride[0], at = 0;
    uint8_t buf[4096];
    (void)u; (void)n;
    if (dsp_fd < 0) { r->as.i64 = -EBADF; return CINT_OK; }
    while (at < len) {
        int64_t k = len - at < (int64_t)sizeof buf ? len - at : (int64_t)sizeof buf, done = 0;
        for (int64_t i = 0; i < k; i++) buf[i] = src[(at + i) * stride];
        while (done < k) {
            ssize_t w = write(dsp_fd, buf + done, (size_t)(k - done));
            if (w < 0 && errno == EINTR) continue;
            if (w <= 0) { r->as.i64 = w < 0 ? -(int64_t)errno : -EIO; return CINT_OK; }
            done += w;
        }
        at += k;
    }
    r->as.i64 = len;
    return CINT_OK;
}

static cint_status r_dsp_sync(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    (void)u; (void)a; (void)n;
    if (dsp_fd < 0) { r->as.i64 = -EBADF; return CINT_OK; }
    r->as.i64 = ioctl(dsp_fd, 0x5001ul, 0) < 0 ? -(int64_t)errno : 0;
    return CINT_OK;
}
#endif

#ifdef CI_ROWS_KERN
static cint_status r_kern_ask(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    static char buf[4096];
    int64_t len = a[0].as.view.shape[0], stride = a[0].as.view.byte_stride[0], at = a[1].as.i64, k = 0;
    const uint8_t *src = (const uint8_t *)a[0].as.view.mem.u.host.ptr;
    long got;
    (void)u; (void)n;
    if (at < 0 || len - at > (int64_t)sizeof buf) { r->as.i64 = -E2BIG; return CINT_OK; }
    for (int64_t i = at; i < len; i++) buf[k++] = (char)src[i * stride];
    got = syscall(1001, (unsigned long)buf, (unsigned long)k);
    r->as.i64 = got < 0 ? -(int64_t)errno : (int64_t)got;
    return CINT_OK;
}

static cint_status r_kern_held(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    long got;
    (void)u; (void)a; (void)n;
    got = syscall(1001, 0UL, 0UL);
    r->as.i64 = got < 0 ? -(int64_t)errno : (int64_t)got;
    return CINT_OK;
}
#endif

#ifdef CI_ROWS_TRAY
static cint_status r_tray_ask(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    long got;
    (void)u; (void)n;
    got = syscall(1002, (unsigned long)a[0].as.i64);
    r->as.i64 = got < 0 ? -(int64_t)errno : (int64_t)got;
    return CINT_OK;
}
#endif

#ifdef CI_ROWS_DIR
static cint_status r_dir_names(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    char path[4096];
    int64_t len = a[1].as.view.shape[0], stride = a[1].as.view.byte_stride[0], pl, k = 0;
    uint8_t *dst = (uint8_t *)a[1].as.view.mem.u.host.ptr;
    DIR *d;
    struct dirent *e;
    (void)u; (void)n;
    pl = view_bytes(&a[0], (uint8_t *)path, (int64_t)sizeof path - 1);
    if (pl < 0) { r->as.i64 = -ENAMETOOLONG; return CINT_OK; }
    path[pl] = '\0';
    if ((int64_t)strlen(path) != pl) { r->as.i64 = -EINVAL; return CINT_OK; }
    d = opendir(path);
    if (!d) { r->as.i64 = -(int64_t)errno; return CINT_OK; }
    while ((e = readdir(d)) != NULL) {
        int64_t m = (int64_t)strlen(e->d_name);
        if (k + m + 1 > len) break;    /* the names that fit; the caller reads again after freeing them */
        for (int64_t i = 0; i < m; i++) dst[(k + i) * stride] = (uint8_t)e->d_name[i];
        dst[(k + m) * stride] = 0;
        k += m + 1;
    }
    closedir(d);
    r->as.i64 = k;
    return CINT_OK;
}
#endif

#ifdef CI_ROWS_OPEN
static cint_status r_open_ask(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    uint8_t buf[256];
    int64_t len = a[0].as.view.shape[0], stride = a[0].as.view.byte_stride[0];
    const uint8_t *src = (const uint8_t *)a[0].as.view.mem.u.host.ptr;
    long got;
    (void)u; (void)n;
    if (len < 1 || len > (int64_t)sizeof buf) { r->as.i64 = -EINVAL; return CINT_OK; }
    for (int64_t i = 0; i < len; i++) buf[i] = src[i * stride];
    got = syscall(1005, (unsigned long)buf, (unsigned long)len);
    r->as.i64 = got < 0 ? -(int64_t)errno : (int64_t)got;
    return CINT_OK;
}
#endif

#ifdef CI_ROWS_GRANT
static cint_status r_grant_set(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    long got;
    (void)u; (void)n;
    got = syscall(1000, (unsigned long)a[0].as.u64);
    r->as.i64 = got < 0 ? -(int64_t)errno : (int64_t)got;
    return CINT_OK;
}

static cint_status r_grant_ask(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    static char buf[4096];
    int64_t len = a[0].as.view.shape[0], stride = a[0].as.view.byte_stride[0], at = a[1].as.i64, k = 0;
    const uint8_t *src = (const uint8_t *)a[0].as.view.mem.u.host.ptr;
    long got;
    (void)u; (void)n;
    if (at < 0 || len - at > (int64_t)sizeof buf) { r->as.i64 = -E2BIG; return CINT_OK; }
    for (int64_t i = at; i < len; i++) buf[k++] = (char)src[i * stride];
    got = syscall(1004, (unsigned long)buf, (unsigned long)k, (unsigned long)a[2].as.u64);
    r->as.i64 = got < 0 ? -(int64_t)errno : (int64_t)got;
    return CINT_OK;
}

static cint_status r_exec_from(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    extern char **environ;
    static char buf[4096];
    char *argv[64];
    int64_t len = a[0].as.view.shape[0], stride = a[0].as.view.byte_stride[0], at = a[1].as.i64, k = 0;
    const uint8_t *src = (const uint8_t *)a[0].as.view.mem.u.host.ptr;
    int argc = 0;
    (void)u; (void)n;
    if (at < 0 || len - at > (int64_t)sizeof buf) { r->as.i64 = -E2BIG; return CINT_OK; }
    for (int64_t i = at; i < len; i++) buf[k++] = (char)src[i * stride];
    for (int64_t i = 0; i < k; i++) {
        if (i == 0 || buf[i - 1] == '\0') {
            if (argc == 63) { r->as.i64 = -E2BIG; return CINT_OK; }
            argv[argc++] = buf + i;
        }
    }
    if (argc == 0 || buf[k - 1] != '\0') { r->as.i64 = -EINVAL; return CINT_OK; }
    argv[argc] = NULL;
    /* BU-2c (docs/specs/2026-11-07-bu2-meta.md section 5): a name without a slash is looked up in PATH first, as
     * the shell does (PATH unset: cish's list), then taken as it is, so `grant net talk` runs /bin/talk in a desk and
     * `grant disk sh` still runs the root's sh in a fixture image with no /bin */
    if (!strchr(argv[0], '/')) {
        static char full[4096];
        const char *path = "/sbin:/usr/sbin:/bin:/usr/bin";
        size_t nl = strlen(argv[0]);
        for (char **e = environ; e && *e; e++)
            if (strncmp(*e, "PATH=", 5) == 0) { path = *e + 5; break; }
        for (const char *p = path; *p; ) {
            const char *q = strchr(p, ':');
            size_t dl = q ? (size_t)(q - p) : strlen(p);
            if (dl > 0 && dl + 1 + nl < sizeof full) {
                memcpy(full, p, dl);
                full[dl] = '/';
                memcpy(full + dl + 1, argv[0], nl + 1);
                execve(full, argv, environ);
            }
            if (!q) break;
            p = q + 1;
        }
    }
    execve(argv[0], argv, environ);
    r->as.i64 = -(int64_t)errno;
    return CINT_OK;
}
#endif

#ifdef CI_ROWS_SH
#include <termios.h>
/* CS-1 (docs/specs/2026-11-06-cish-shell.md section 7): cish's rows, one per call, each the call's value or -errno. */
static int64_t sh_path(const cint_value *v, char *buf, int64_t cap)
{
    int64_t len = view_bytes(v, (uint8_t *)buf, cap - 1);
    if (len < 0) return -ENAMETOOLONG;
    buf[len] = '\0';
    if ((int64_t)strlen(buf) != len) return -EINVAL;
    return len;
}

/* A view of NUL-ended strings into vec: their count, or -E2BIG / -EINVAL. */
static int sh_strings(const cint_value *v, char *buf, int64_t cap, char **vec, int most)
{
    int64_t len = v->as.view.shape[0], stride = v->as.view.byte_stride[0];
    const uint8_t *src = (const uint8_t *)v->as.view.mem.u.host.ptr;
    int k = 0;
    if (len > cap) return -E2BIG;
    for (int64_t i = 0; i < len; i++) buf[i] = (char)src[i * stride];
    if (len > 0 && buf[len - 1] != '\0') return -EINVAL;
    for (int64_t i = 0; i < len; i++) {
        if (i == 0 || buf[i - 1] == '\0') {
            if (k == most) return -E2BIG;
            vec[k++] = buf + i;
        }
    }
    vec[k] = NULL;
    return k;
}

static cint_status r_sh_fork(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    pid_t pid;
    (void)u; (void)a; (void)n;
    pid = fork();
    r->as.i64 = pid < 0 ? -(int64_t)errno : (int64_t)pid;
    return CINT_OK;
}

static cint_status r_sh_exec(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    static char path[4096], abuf[32768], ebuf[32768];
    static char *argv[257], *envp[257];
    int64_t pl;
    int na, ne;
    (void)u; (void)n;
    pl = sh_path(&a[0], path, (int64_t)sizeof path);
    na = sh_strings(&a[1], abuf, (int64_t)sizeof abuf, argv, 256);
    ne = sh_strings(&a[2], ebuf, (int64_t)sizeof ebuf, envp, 256);
    if (pl < 0) { r->as.i64 = pl; return CINT_OK; }
    if (na <= 0 || ne < 0) { r->as.i64 = na < 0 ? na : ne < 0 ? ne : -EINVAL; return CINT_OK; }
    execve(path, argv, envp);
    r->as.i64 = -(int64_t)errno;
    return CINT_OK;
}

static long sh_last_maxrss;   /* the ru_maxrss of the child sh_wait last reaped, in KiB */

static cint_status r_sh_wait(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    int st = 0;
    pid_t got;
    struct rusage ru;
    (void)u; (void)n;
    do {
        memset(&ru, 0, sizeof ru);
        got = wait4((pid_t)a[0].as.i64, &st, a[1].as.i64 != 0 ? WNOHANG : 0, &ru);
    } while (got < 0 && errno == EINTR);
    if (got > 0) sh_last_maxrss = ru.ru_maxrss;
    r->as.i64 = got < 0 ? -(int64_t)errno : got == 0 ? -EAGAIN : st;
    return CINT_OK;
}

static cint_status r_sh_maxrss(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    (void)u; (void)a; (void)n;
    r->as.i64 = (int64_t)sh_last_maxrss;
    return CINT_OK;
}

static cint_status r_sh_pipe(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    int fds[2];
    (void)u; (void)a; (void)n;
    r->as.i64 = pipe(fds) < 0 ? -(int64_t)errno : ((int64_t)fds[0] << 32) | (int64_t)fds[1];
    return CINT_OK;
}

static cint_status r_sh_dup2(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    (void)u; (void)n;
    r->as.i64 = dup2((int)a[0].as.i64, (int)a[1].as.i64) < 0 ? -(int64_t)errno : a[1].as.i64;
    return CINT_OK;
}

static cint_status r_sh_dupfd(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    int fd;
    (void)u; (void)n;
    fd = fcntl((int)a[0].as.i64, F_DUPFD_CLOEXEC, (int)a[1].as.i64);
    r->as.i64 = fd < 0 ? -(int64_t)errno : fd;
    return CINT_OK;
}

/* cint programs pass Linux's open flags (the Daphnis kernel's). On Linux they go through as they are; on Darwin,
 * where the numbers differ, the access mode and O_CREAT, O_EXCL, O_TRUNC, O_APPEND, O_NONBLOCK and O_NOFOLLOW are
 * translated, so the Mac's hosted legs open files as Linux does (setfile.load relies on the last two: a link is
 * refused and a FIFO does not block before fd_stat sees it). Other bits have no Darwin meaning here and are dropped. */
#if defined(__APPLE__)
static int sh_open_flags(int64_t lf)
{
    int f = (int)(lf & 3);                 /* O_RDONLY 0, O_WRONLY 1, O_RDWR 2: the same on both */
    if (lf & 0100) { f |= O_CREAT; }
    if (lf & 0200) { f |= O_EXCL; }
    if (lf & 01000) { f |= O_TRUNC; }
    if (lf & 02000) { f |= O_APPEND; }
    if (lf & 04000) { f |= O_NONBLOCK; }
    if (lf & 0400000) { f |= O_NOFOLLOW; }
    return f;
}
#else
static int sh_open_flags(int64_t lf) { return (int)lf; }
#endif

static cint_status r_sh_open(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    char path[4096];
    int64_t len;
    int fd;
    (void)u; (void)n;
    len = sh_path(&a[0], path, (int64_t)sizeof path);
    if (len < 0) { r->as.i64 = len; return CINT_OK; }
    fd = openat(AT_FDCWD, path, sh_open_flags(a[1].as.i64), (mode_t)a[2].as.i64);
    r->as.i64 = fd < 0 ? -(int64_t)errno : fd;
    return CINT_OK;
}

static cint_status r_sh_chdir(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    char path[4096];
    int64_t len;
    (void)u; (void)n;
    len = sh_path(&a[0], path, (int64_t)sizeof path);
    if (len < 0) { r->as.i64 = len; return CINT_OK; }
    r->as.i64 = chdir(path) < 0 ? -(int64_t)errno : 0;
    return CINT_OK;
}

static cint_status r_sh_getcwd(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    char buf[4096];
    int64_t len = a[0].as.view.shape[0], stride = a[0].as.view.byte_stride[0], k;
    uint8_t *dst = (uint8_t *)a[0].as.view.mem.u.host.ptr;
    (void)u; (void)n;
    if (getcwd(buf, sizeof buf) == NULL) { r->as.i64 = -(int64_t)errno; return CINT_OK; }
    k = (int64_t)strlen(buf);
    if (k > len) { r->as.i64 = -ERANGE; return CINT_OK; }
    for (int64_t i = 0; i < k; i++) dst[i * stride] = (uint8_t)buf[i];
    r->as.i64 = k;
    return CINT_OK;
}

static cint_status r_sh_environ(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    extern char **environ;
    int64_t i = a[0].as.i64, len = a[1].as.view.shape[0], stride = a[1].as.view.byte_stride[0], k;
    uint8_t *dst = (uint8_t *)a[1].as.view.mem.u.host.ptr;
    (void)u; (void)n;
    for (int64_t j = 0; j < i; j++) {
        if (environ == NULL || environ[j] == NULL) { r->as.i64 = -ENOENT; return CINT_OK; }
    }
    if (environ == NULL || environ[i] == NULL) { r->as.i64 = -ENOENT; return CINT_OK; }
    k = (int64_t)strlen(environ[i]);
    if (k > len) { r->as.i64 = -E2BIG; return CINT_OK; }
    for (int64_t j = 0; j < k; j++) dst[j * stride] = (uint8_t)environ[i][j];
    r->as.i64 = k;
    return CINT_OK;
}

static cint_status r_sh_stat(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    char path[4096];
    struct stat st;
    int64_t len = a[2].as.view.shape[0], stride = a[2].as.view.byte_stride[0], pl;
    uint8_t *dst = (uint8_t *)a[2].as.view.mem.u.host.ptr;
    uint64_t mode, size;
    (void)u; (void)n;
    pl = sh_path(&a[0], path, (int64_t)sizeof path);
    if (pl < 0) { r->as.i64 = pl; return CINT_OK; }
    if (len < 12) { r->as.i64 = -EINVAL; return CINT_OK; }
    if (fstatat(AT_FDCWD, path, &st, a[1].as.i64 != 0 ? 0 : AT_SYMLINK_NOFOLLOW) < 0) { r->as.i64 = -(int64_t)errno; return CINT_OK; }
    mode = (uint64_t)st.st_mode;
    size = (uint64_t)st.st_size;
    for (int i = 0; i < 4; i++) dst[i * stride] = (uint8_t)(mode >> (8 * i));
    for (int i = 0; i < 8; i++) dst[(4 + i) * stride] = (uint8_t)(size >> (8 * i));
    r->as.i64 = 0;
    return CINT_OK;
}

static cint_status r_sh_access(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    char path[4096];
    int64_t pl;
    (void)u; (void)n;
    pl = sh_path(&a[0], path, (int64_t)sizeof path);
    if (pl < 0) { r->as.i64 = pl; return CINT_OK; }
    r->as.i64 = faccessat(AT_FDCWD, path, (int)a[1].as.i64, 0) < 0 ? -(int64_t)errno : 0;
    return CINT_OK;
}

static cint_status r_sh_dirents(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    char path[4096];
    int64_t len = a[1].as.view.shape[0], stride = a[1].as.view.byte_stride[0], pl, k = 0;
    uint8_t *dst = (uint8_t *)a[1].as.view.mem.u.host.ptr;
    DIR *d;
    struct dirent *e;
    (void)u; (void)n;
    pl = sh_path(&a[0], path, (int64_t)sizeof path);
    if (pl < 0) { r->as.i64 = pl; return CINT_OK; }
    d = opendir(path);
    if (!d) { r->as.i64 = -(int64_t)errno; return CINT_OK; }
    while ((e = readdir(d)) != NULL) {
        int64_t m = (int64_t)strlen(e->d_name);
        if (k + m + 1 > len) { closedir(d); r->as.i64 = -E2BIG; return CINT_OK; }
        for (int64_t i = 0; i < m; i++) dst[(k + i) * stride] = (uint8_t)e->d_name[i];
        dst[(k + m) * stride] = 0;
        k += m + 1;
    }
    closedir(d);
    r->as.i64 = k;
    return CINT_OK;
}

static cint_status r_sh_getpid(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    (void)u; (void)a; (void)n;
    r->as.i64 = (int64_t)getpid();
    return CINT_OK;
}

static cint_status r_sh_geteuid(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    (void)u; (void)a; (void)n;
    r->as.i64 = (int64_t)geteuid();
    return CINT_OK;
}

/* CS-4: the terminal's settings as bytes, so cish can put back what a program left (raw mode) before each prompt */
static cint_status r_sh_tcget(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    struct termios t;
    int64_t len = a[1].as.view.shape[0], stride = a[1].as.view.byte_stride[0];
    uint8_t *dst = (uint8_t *)a[1].as.view.mem.u.host.ptr;
    (void)u; (void)n;
    if (len < (int64_t)sizeof t) { r->as.i64 = -EINVAL; return CINT_OK; }
    if (tcgetattr((int)a[0].as.i64, &t) < 0) { r->as.i64 = -(int64_t)errno; return CINT_OK; }
    for (size_t i = 0; i < sizeof t; i++) dst[(int64_t)i * stride] = ((const uint8_t *)&t)[i];
    r->as.i64 = (int64_t)sizeof t;
    return CINT_OK;
}

static cint_status r_sh_tcset(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    struct termios t;
    int64_t len = a[1].as.view.shape[0], stride = a[1].as.view.byte_stride[0];
    const uint8_t *src = (const uint8_t *)a[1].as.view.mem.u.host.ptr;
    (void)u; (void)n;
    if (len < (int64_t)sizeof t) { r->as.i64 = -EINVAL; return CINT_OK; }
    for (size_t i = 0; i < sizeof t; i++) ((uint8_t *)&t)[i] = src[(int64_t)i * stride];
    r->as.i64 = tcsetattr((int)a[0].as.i64, TCSANOW, &t) < 0 ? -(int64_t)errno : 0;
    return CINT_OK;
}
#endif

#ifdef CI_ROWS_VIEW
static cint_status r_view_winsize(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    struct winsize ws;
    (void)u; (void)n;
    r->as.i64 = ioctl((int)a[0].as.i64, TIOCGWINSZ, &ws) < 0 ? -(int64_t)errno
                                                              : ((int64_t)ws.ws_row << 16) | (int64_t)ws.ws_col;
    return CINT_OK;
}
#endif

#ifdef CI_ROWS_CVIM
#include <termios.h>
#include <stdlib.h>
static struct termios cv_saved;
static int cv_fd = -1;
static volatile sig_atomic_t cv_resized = 0;
static const char cv_leave_seq[] = "\033[0 q\033[?25h\033[?1049l";

static void cv_restore(void)
{
    if (cv_fd < 0) return;
    ssize_t w = write(cv_fd, cv_leave_seq, sizeof cv_leave_seq - 1);
    (void)w;
    tcsetattr(cv_fd, TCSANOW, &cv_saved);
    cv_fd = -1;
}

static void cv_on_fatal(int sig)
{
    cv_restore();
    signal(sig, SIG_DFL);
    raise(sig);
}

static void cv_on_winch(int sig)
{
    (void)sig;
    cv_resized = 1;
}

static cint_status r_cv_term_enter(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    static const int fatal[] = {SIGTERM, SIGHUP, SIGINT, SIGQUIT, SIGABRT, SIGSEGV, SIGBUS, SIGFPE, SIGILL, SIGTRAP};
    static const char enter_seq[] = "\033[?1049h";
    struct termios raw;
    struct sigaction sa;
    int fd = (int)a[0].as.i64;
    (void)u; (void)n;
    if (tcgetattr(fd, &cv_saved) < 0) { r->as.i64 = -(int64_t)errno; return CINT_OK; }
    raw = cv_saved;
    raw.c_iflag &= ~(tcflag_t)(BRKINT | ICRNL | INPCK | ISTRIP | IXON);
    raw.c_oflag &= ~(tcflag_t)OPOST;
    raw.c_cflag |= CS8;
    raw.c_lflag &= ~(tcflag_t)(ECHO | ICANON | IEXTEN | ISIG);
    raw.c_cc[VMIN] = 1;
    raw.c_cc[VTIME] = 0;
    cv_fd = fd;
    memset(&sa, 0, sizeof sa);
    sigemptyset(&sa.sa_mask);
    sa.sa_handler = cv_on_fatal;
    for (size_t i = 0; i < sizeof fatal / sizeof fatal[0]; i++) sigaction(fatal[i], &sa, NULL);
    sa.sa_handler = cv_on_winch;
    sa.sa_flags = 0;   /* no SA_RESTART: the read returns -EINTR and the loop redraws */
    sigaction(SIGWINCH, &sa, NULL);
    atexit(cv_restore);
    if (tcsetattr(fd, TCSANOW, &raw) < 0) { r->as.i64 = -(int64_t)errno; cv_fd = -1; return CINT_OK; }
    ssize_t w = write(fd, enter_seq, sizeof enter_seq - 1);
    (void)w;
    r->as.i64 = 0;
    return CINT_OK;
}

static cint_status r_cv_term_leave(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    (void)u; (void)a; (void)n;
    cv_restore();
    r->as.i64 = 0;
    return CINT_OK;
}

static cint_status r_cv_winch(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    (void)u; (void)a; (void)n;
    r->as.i64 = cv_resized ? 1 : 0;
    cv_resized = 0;
    return CINT_OK;
}

static cint_status r_cv_fsync(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    (void)u; (void)n;
    r->as.i64 = fsync((int)a[0].as.i64) < 0 ? -(int64_t)errno : 0;
    return CINT_OK;
}

static cint_status r_cv_fchmod(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    (void)u; (void)n;
    r->as.i64 = fchmod((int)a[0].as.i64, (mode_t)a[1].as.i64) < 0 ? -(int64_t)errno : 0;
    return CINT_OK;
}
#endif

#ifdef CI_ROWS_SIG
static cint_status r_sig_set(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    (void)u; (void)n;
    r->as.i64 = signal((int)a[0].as.i64, a[1].as.i64 != 0 ? SIG_IGN : SIG_DFL) == SIG_ERR ? -(int64_t)errno : 0;
    return CINT_OK;
}
#endif

#ifdef CI_ROWS_CORE
#include <stdio.h>   /* rename */
/* CT-1 (docs/specs/2026-11-06-c-core.md section 4): the core set's rows beside cish's, one per call, each the call's
 * value or -errno: co_stat(path, follow, rec) (the full record, user/ci/corectl.ci ST_ words), co_lseek, co_mkdir,
 * co_rmdir, co_unlink, co_rename, co_clock(which) (nanoseconds), co_sleep(ns). */
static int64_t co_path(const cint_value *v, char *buf, int64_t cap)
{
    int64_t len = view_bytes(v, (uint8_t *)buf, cap - 1);
    if (len < 0) return -ENAMETOOLONG;
    buf[len] = '\0';
    if ((int64_t)strlen(buf) != len) return -EINVAL;
    return len;
}

static void co_word(const cint_value *v, int64_t i, int64_t w)
{
    uint8_t *dst = (uint8_t *)v->as.view.mem.u.host.ptr + i * v->as.view.byte_stride[0];
    memcpy(dst, &w, sizeof w);
}

static cint_status r_co_stat(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    char path[4096];
    struct stat st;
    int64_t pl;
    (void)u; (void)n;
    pl = co_path(&a[0], path, (int64_t)sizeof path);
    if (pl < 0) { r->as.i64 = pl; return CINT_OK; }
    if (a[2].as.view.shape[0] < 16) { r->as.i64 = -EINVAL; return CINT_OK; }
    if (fstatat(AT_FDCWD, path, &st, a[1].as.i64 != 0 ? 0 : AT_SYMLINK_NOFOLLOW) < 0) { r->as.i64 = -(int64_t)errno; return CINT_OK; }
    co_word(&a[2], 0, (int64_t)st.st_dev);
    co_word(&a[2], 1, (int64_t)st.st_ino);
    co_word(&a[2], 2, (int64_t)st.st_mode);
    co_word(&a[2], 3, (int64_t)st.st_nlink);
    co_word(&a[2], 4, (int64_t)st.st_uid);
    co_word(&a[2], 5, (int64_t)st.st_gid);
    co_word(&a[2], 6, (int64_t)st.st_rdev);
    co_word(&a[2], 7, (int64_t)st.st_size);
    co_word(&a[2], 8, (int64_t)st.st_blksize);
    co_word(&a[2], 9, (int64_t)st.st_blocks);
    co_word(&a[2], 10, (int64_t)st.st_atim.tv_sec);
    co_word(&a[2], 11, (int64_t)st.st_atim.tv_nsec);
    co_word(&a[2], 12, (int64_t)st.st_mtim.tv_sec);
    co_word(&a[2], 13, (int64_t)st.st_mtim.tv_nsec);
    co_word(&a[2], 14, (int64_t)st.st_ctim.tv_sec);
    co_word(&a[2], 15, (int64_t)st.st_ctim.tv_nsec);
    r->as.i64 = 0;
    return CINT_OK;
}

static cint_status r_co_lseek(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    off_t o;
    (void)u; (void)n;
    o = lseek((int)a[0].as.i64, (off_t)a[1].as.i64, (int)a[2].as.i64);
    r->as.i64 = o < 0 ? -(int64_t)errno : (int64_t)o;
    return CINT_OK;
}

static cint_status r_co_mkdir(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    char path[4096];
    int64_t pl;
    (void)u; (void)n;
    pl = co_path(&a[0], path, (int64_t)sizeof path);
    if (pl < 0) { r->as.i64 = pl; return CINT_OK; }
    r->as.i64 = mkdir(path, (mode_t)a[1].as.i64) < 0 ? -(int64_t)errno : 0;
    return CINT_OK;
}

static cint_status r_co_rmdir(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    char path[4096];
    int64_t pl;
    (void)u; (void)n;
    pl = co_path(&a[0], path, (int64_t)sizeof path);
    if (pl < 0) { r->as.i64 = pl; return CINT_OK; }
    r->as.i64 = rmdir(path) < 0 ? -(int64_t)errno : 0;
    return CINT_OK;
}

static cint_status r_co_unlink(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    char path[4096];
    int64_t pl;
    (void)u; (void)n;
    pl = co_path(&a[0], path, (int64_t)sizeof path);
    if (pl < 0) { r->as.i64 = pl; return CINT_OK; }
    r->as.i64 = unlink(path) < 0 ? -(int64_t)errno : 0;
    return CINT_OK;
}

static cint_status r_co_rename(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    char from[4096], to[4096];
    int64_t fl, tl;
    (void)u; (void)n;
    fl = co_path(&a[0], from, (int64_t)sizeof from);
    tl = co_path(&a[1], to, (int64_t)sizeof to);
    if (fl < 0 || tl < 0) { r->as.i64 = fl < 0 ? fl : tl; return CINT_OK; }
    r->as.i64 = rename(from, to) < 0 ? -(int64_t)errno : 0;
    return CINT_OK;
}

static cint_status r_co_clock(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    struct timespec ts;
    (void)u; (void)n;
    if (clock_gettime(a[0].as.i64 == 1 ? CLOCK_MONOTONIC : CLOCK_REALTIME, &ts) < 0) { r->as.i64 = -(int64_t)errno; return CINT_OK; }
    r->as.i64 = (int64_t)ts.tv_sec * 1000000000 + (int64_t)ts.tv_nsec;
    return CINT_OK;
}

static cint_status r_co_sleep(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    struct timespec ts;
    int64_t ns = a[0].as.i64;
    (void)u; (void)n;
    if (ns < 0) { r->as.i64 = -EINVAL; return CINT_OK; }
    ts.tv_sec = (time_t)(ns / 1000000000);
    ts.tv_nsec = (long)(ns % 1000000000);
    r->as.i64 = nanosleep(&ts, NULL) < 0 ? -(int64_t)errno : 0;
    return CINT_OK;
}
/* CT-2: cp -P copies a link as a link; tee -i. */
static cint_status r_co_readlink(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    char path[4096], target[4096];
    int64_t len = a[1].as.view.shape[0], pl;
    ssize_t k;
    (void)u; (void)n;
    pl = co_path(&a[0], path, (int64_t)sizeof path);
    if (pl < 0) { r->as.i64 = pl; return CINT_OK; }
    k = readlink(path, target, sizeof target);
    if (k < 0) { r->as.i64 = -(int64_t)errno; return CINT_OK; }
    if ((int64_t)k > len || k == (ssize_t)sizeof target) { r->as.i64 = -ENAMETOOLONG; return CINT_OK; }
    for (ssize_t i = 0; i < k; i++) ((uint8_t *)a[1].as.view.mem.u.host.ptr)[(int64_t)i * a[1].as.view.byte_stride[0]] = (uint8_t)target[i];
    r->as.i64 = (int64_t)k;
    return CINT_OK;
}
static cint_status r_co_symlink(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    char target[4096], path[4096];
    int64_t pl;
    (void)u; (void)n;
    pl = co_path(&a[0], target, (int64_t)sizeof target);
    if (pl < 0) { r->as.i64 = pl; return CINT_OK; }
    pl = co_path(&a[1], path, (int64_t)sizeof path);
    if (pl < 0) { r->as.i64 = pl; return CINT_OK; }
    r->as.i64 = symlink(target, path) < 0 ? -(int64_t)errno : 0;
    return CINT_OK;
}
static cint_status r_co_ignore_int(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    (void)u; (void)a; (void)n;
    r->as.i64 = signal(SIGINT, SIG_IGN) == SIG_ERR ? -(int64_t)errno : 0;
    return CINT_OK;
}

static cint_status r_co_ftruncate(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    (void)u; (void)n;
    r->as.i64 = ftruncate((int)a[0].as.i64, (off_t)a[1].as.i64) < 0 ? -(int64_t)errno : 0;
    return CINT_OK;
}

static cint_status r_co_sync(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    (void)u; (void)a; (void)n;
    sync();
    r->as.i64 = 0;
    return CINT_OK;
}

static cint_status r_co_settime(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    struct timespec ts;
    (void)u; (void)n;
    ts.tv_sec = (time_t)a[0].as.i64;
    ts.tv_nsec = 0;
    r->as.i64 = clock_settime(CLOCK_REALTIME, &ts) < 0 ? -(int64_t)errno : 0;
    return CINT_OK;
}
#endif

#if defined(CI_ROWS_FD) && defined(CI_ROWS_CORE)
/* FS-5 (docs/specs/2026-11-07-bu2-meta.md section 4.9), built only into a program that imports user/ci/fdctl.ci
 * (CI_ROWS_FD, with CI_ROWS_CORE): fd_stat(fd, rec), fstat of an open descriptor into rec's sixteen words, co_stat's
 * record (user/ci/corectl.ci ST_ names); 0 or -errno. What a program learns from it is about the file it holds, not
 * about whatever a path names by then. */
static cint_status r_fd_stat(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    struct stat st;
    (void)u; (void)n;
    if (a[1].as.view.shape[0] < 16) { r->as.i64 = -EINVAL; return CINT_OK; }
    if (fstat((int)a[0].as.i64, &st) < 0) { r->as.i64 = -(int64_t)errno; return CINT_OK; }
    co_word(&a[1], 0, (int64_t)st.st_dev);
    co_word(&a[1], 1, (int64_t)st.st_ino);
    co_word(&a[1], 2, (int64_t)st.st_mode);
    co_word(&a[1], 3, (int64_t)st.st_nlink);
    co_word(&a[1], 4, (int64_t)st.st_uid);
    co_word(&a[1], 5, (int64_t)st.st_gid);
    co_word(&a[1], 6, (int64_t)st.st_rdev);
    co_word(&a[1], 7, (int64_t)st.st_size);
    co_word(&a[1], 8, (int64_t)st.st_blksize);
    co_word(&a[1], 9, (int64_t)st.st_blocks);
    co_word(&a[1], 10, (int64_t)st.st_atim.tv_sec);
    co_word(&a[1], 11, (int64_t)st.st_atim.tv_nsec);
    co_word(&a[1], 12, (int64_t)st.st_mtim.tv_sec);
    co_word(&a[1], 13, (int64_t)st.st_mtim.tv_nsec);
    co_word(&a[1], 14, (int64_t)st.st_ctim.tv_sec);
    co_word(&a[1], 15, (int64_t)st.st_ctim.tv_nsec);
    r->as.i64 = 0;
    return CINT_OK;
}
#endif

#if defined(CI_ROWS_FACTS) && defined(CI_ROWS_CORE)
#include <sys/statfs.h>
/* KF-1 (docs/specs/2026-11-11-kf-facts.md section 2), built only into a program that imports user/ci/factsctl.ci
 * (CI_ROWS_FACTS, with CI_ROWS_CORE): co_statfs(path, rec), statfs into rec's eight words (user/ci/factsctl.ci SF_
 * names: f_type, f_bsize, f_blocks, f_bfree, f_bavail, f_files, f_ffree, f_namelen); 0 or -errno. */
static cint_status r_co_statfs(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    char path[4096];
    struct statfs sf;
    int64_t pl;
    (void)u; (void)n;
    pl = co_path(&a[0], path, (int64_t)sizeof path);
    if (pl < 0) { r->as.i64 = pl; return CINT_OK; }
    if (a[1].as.view.shape[0] < 8) { r->as.i64 = -EINVAL; return CINT_OK; }
    if (statfs(path, &sf) < 0) { r->as.i64 = -(int64_t)errno; return CINT_OK; }
    co_word(&a[1], 0, (int64_t)(uint32_t)sf.f_type);
    co_word(&a[1], 1, (int64_t)sf.f_bsize);
    co_word(&a[1], 2, (int64_t)sf.f_blocks);
    co_word(&a[1], 3, (int64_t)sf.f_bfree);
    co_word(&a[1], 4, (int64_t)sf.f_bavail);
    co_word(&a[1], 5, (int64_t)sf.f_files);
    co_word(&a[1], 6, (int64_t)sf.f_ffree);
    co_word(&a[1], 7, (int64_t)sf.f_namelen);
    r->as.i64 = 0;
    return CINT_OK;
}

/* KF-3 (section 2): co_facts(kind, id, buf), Daphnis's call 1007 with buf's bytes as n: the record's full size, or
 * -errno (-ENOSYS on Linux; -EINVAL for a view that is not contiguous bytes). */
static cint_status r_co_facts(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    long v;
    (void)u; (void)n;
    if (a[2].as.view.byte_stride[0] != 1) { r->as.i64 = -EINVAL; return CINT_OK; }
    v = syscall(1007, (long)a[0].as.i64, (long)a[1].as.i64, (long)a[2].as.view.mem.u.host.ptr, (long)a[2].as.view.shape[0]);
    r->as.i64 = v < 0 ? -(int64_t)errno : (int64_t)v;
    return CINT_OK;
}
#endif

#if defined(CI_ROWS_META) && defined(CI_ROWS_CORE)
#include <sys/utsname.h>
/* BU-2b (docs/specs/2026-11-07-bu2-meta.md section 6): tier C-2's rows, each the call's value or -errno:
 * co_chmod(path, mode); co_umask(mask) (the old mask); co_utimens(path, atime, mtime, follow), each time in seconds,
 * -1 UTIME_OMIT, -2 UTIME_NOW; co_link(from, to, follow) (linkat, AT_SYMLINK_FOLLOW when follow); co_uname(buf)
 * (the six fields of struct utsname, 65 bytes each, into buf of 390). */
static cint_status r_co_chmod(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    char path[4096];
    int64_t pl;
    (void)u; (void)n;
    pl = co_path(&a[0], path, (int64_t)sizeof path);
    if (pl < 0) { r->as.i64 = pl; return CINT_OK; }
    r->as.i64 = chmod(path, (mode_t)(a[1].as.i64 & 07777)) < 0 ? -(int64_t)errno : 0;
    return CINT_OK;
}

static cint_status r_co_umask(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    (void)u; (void)n;
    r->as.i64 = (int64_t)umask((mode_t)(a[0].as.i64 & 0777));
    return CINT_OK;
}

static void co_time(struct timespec *t, int64_t v)
{
    t->tv_sec = v < 0 ? 0 : (time_t)v;
    t->tv_nsec = v == -1 ? UTIME_OMIT : v == -2 ? UTIME_NOW : 0;
}

static cint_status r_co_utimens(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    char path[4096];
    struct timespec t[2];
    int64_t pl;
    (void)u; (void)n;
    pl = co_path(&a[0], path, (int64_t)sizeof path);
    if (pl < 0) { r->as.i64 = pl; return CINT_OK; }
    co_time(&t[0], a[1].as.i64);
    co_time(&t[1], a[2].as.i64);
    r->as.i64 = utimensat(AT_FDCWD, path, t, a[3].as.i64 != 0 ? 0 : AT_SYMLINK_NOFOLLOW) < 0 ? -(int64_t)errno : 0;
    return CINT_OK;
}

static cint_status r_co_link(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    char from[4096], to[4096];
    int64_t pl;
    (void)u; (void)n;
    pl = co_path(&a[0], from, (int64_t)sizeof from);
    if (pl < 0) { r->as.i64 = pl; return CINT_OK; }
    pl = co_path(&a[1], to, (int64_t)sizeof to);
    if (pl < 0) { r->as.i64 = pl; return CINT_OK; }
    r->as.i64 = linkat(AT_FDCWD, from, AT_FDCWD, to, a[2].as.i64 != 0 ? AT_SYMLINK_FOLLOW : 0) < 0 ? -(int64_t)errno : 0;
    return CINT_OK;
}

static cint_status r_co_uname(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    struct utsname un;
    const char *f[6];
    uint8_t *dst = (uint8_t *)a[0].as.view.mem.u.host.ptr;
    (void)u; (void)n;
    if (a[0].as.view.shape[0] < 390) { r->as.i64 = -EINVAL; return CINT_OK; }
    if (uname(&un) < 0) { r->as.i64 = -(int64_t)errno; return CINT_OK; }
    f[0] = un.sysname; f[1] = un.nodename; f[2] = un.release; f[3] = un.version; f[4] = un.machine;
#ifdef _GNU_SOURCE
    f[5] = un.domainname;
#else
    f[5] = un.__domainname;
#endif
    for (int k = 0; k < 6; k++)
        for (int i = 0; i < 65; i++)
            dst[(int64_t)(65 * k + i) * a[0].as.view.byte_stride[0]] = i < 64 ? (uint8_t)f[k][i] : 0;
    r->as.i64 = 0;
    return CINT_OK;
}
#endif

#if defined(CI_ROWS_RUN) && defined(CI_ROWS_SH)
/* CT-4: execve with the core set's limits (docs/specs/2026-11-06-c-core.md section 5). */
static cint_status r_co_exec(void *u, const cint_value *a, uint32_t n, cint_value *r)
{
    static char path[4096], abuf[65536], ebuf[65536];
    static char *argv[4097], *envp[1025];
    int64_t pl;
    int na, ne;
    (void)u; (void)n;
    pl = sh_path(&a[0], path, (int64_t)sizeof path);
    na = sh_strings(&a[1], abuf, (int64_t)sizeof abuf, argv, 4096);
    ne = sh_strings(&a[2], ebuf, (int64_t)sizeof ebuf, envp, 1024);
    if (pl < 0) { r->as.i64 = pl; return CINT_OK; }
    if (na <= 0 || ne < 0) { r->as.i64 = na < 0 ? na : ne < 0 ? ne : -EINVAL; return CINT_OK; }
    execve(path, argv, envp);
    r->as.i64 = -(int64_t)errno;
    return CINT_OK;
}
#endif

const ci_row ci_rows[] = {
    {"fb_open", r_fb_open},
    {"fb_word", r_fb_word},
    {"fb_row", r_fb_row},
    {"ev_read", r_ev_read},
    {"clock_ns", r_clock_ns},
    {"exit_now", r_exit_now},
    {"out_open", r_out_open},
    {"out_put", r_out_put},
    {"tile_ctl", r_tile_ctl},
    {"tile_big", r_tile_big},
    {"spawn", r_spawn},
    {"reap", r_reap},
    {"stop", r_stop},
    {"fb_span", r_fb_span},
#ifdef CI_ROWS_WALL
    {"wall_ns", r_wall_ns},
#endif
#ifdef CI_ROWS_REVOKE
    {"co_revoke", r_co_revoke},
#endif
#ifdef CI_ROWS_SYSINFO
    {"co_sysinfo", r_co_sysinfo},
    {"co_ids", r_co_ids},
#endif
#ifdef CI_ROWS_AUTH
    {"rand_fill", r_rand_fill},
#endif
#ifdef CI_ROWS_PLACE
    {"tile_place", r_tile_place},
#endif
#ifdef CI_ROWS_WIN
    {"win_want", r_win_want},
    {"win_var", r_win_var},
    {"win_menu", r_win_menu},
    {"win_resize", r_win_resize},
#endif
#if defined(CI_ROWS_SURF) && defined(CI_ROWS_WIN)
    {"fb_resize", r_fb_resize},
#endif
#if defined(CI_ROWS_POINT) && defined(CI_ROWS_WIN)
    {"win_point", r_win_point},
#endif
#ifdef CI_ROWS_HDESK
    {"tile_ask", r_tile_ask},
    {"pty_winsize", r_pty_winsize},
    {"pty_nonblock", r_pty_nonblock},
    {"pty_sigsess", r_pty_sigsess},
    {"fb_remap", r_fb_remap},
    {"power", r_power},
    {"spawn_as", r_spawn_as},
    {"auth_start", r_auth_start},
    {"auth_poll", r_auth_poll},
    {"home", r_home},
    {"fb_hold", r_fb_hold},
    {"fb_peek", r_fb_peek},
    {"shot_as", r_shot_as},
    {"shot_end", r_shot_end},
    {"run_session", r_run_session},
    {"run_start", r_run_start},
    {"run_poll", r_run_poll},
    {"run_stop", r_run_stop},
    {"rep_get", r_rep_get},
    {"rep_set", r_rep_set},
    {"seat", r_seat},
    {"sweep", r_sweep},
#endif
#ifdef CI_ROWS_NET
    {"udp_open", r_udp_open},
    {"udp_send", r_udp_send},
    {"udp_recv", r_udp_recv},
    {"udp_from", r_udp_from},
    {"stdout_put", r_stdout_put},
#endif
#ifdef CI_ROWS_TCP
    {"tcp_listen", r_tcp_listen},
    {"tcp_accept", r_tcp_accept},
    {"tcp_connect", r_tcp_connect},
#endif
#if defined(CI_ROWS_TCP) || defined(CI_ROWS_SH)
    {"fd_read", r_fd_read},
    {"fd_write", r_fd_write},
    {"fd_close", r_fd_close},
#endif
#ifdef CI_ROWS_SH
    {"sh_fork", r_sh_fork},
    {"sh_exec", r_sh_exec},
    {"sh_wait", r_sh_wait},
    {"sh_maxrss", r_sh_maxrss},
    {"sh_pipe", r_sh_pipe},
    {"sh_dup2", r_sh_dup2},
    {"sh_dupfd", r_sh_dupfd},
    {"sh_open", r_sh_open},
    {"sh_chdir", r_sh_chdir},
    {"sh_getcwd", r_sh_getcwd},
    {"sh_environ", r_sh_environ},
    {"sh_getpid", r_sh_getpid},
    {"sh_stat", r_sh_stat},
    {"sh_access", r_sh_access},
    {"sh_dirents", r_sh_dirents},
    {"sh_geteuid", r_sh_geteuid},
    {"sh_tcget", r_sh_tcget},
    {"sh_tcset", r_sh_tcset},
#endif
#ifdef CI_ROWS_CORE
    {"co_stat", r_co_stat},
    {"co_lseek", r_co_lseek},
    {"co_mkdir", r_co_mkdir},
    {"co_rmdir", r_co_rmdir},
    {"co_unlink", r_co_unlink},
    {"co_rename", r_co_rename},
    {"co_clock", r_co_clock},
    {"co_sleep", r_co_sleep},
    {"co_readlink", r_co_readlink},
    {"co_symlink", r_co_symlink},
    {"co_ignore_int", r_co_ignore_int},
    {"co_ftruncate", r_co_ftruncate},
    {"co_sync", r_co_sync},
    {"co_settime", r_co_settime},
#endif
#if defined(CI_ROWS_RUN) && defined(CI_ROWS_SH)
    {"co_exec", r_co_exec},
#endif
#if defined(CI_ROWS_FD) && defined(CI_ROWS_CORE)
    {"fd_stat", r_fd_stat},
#endif
#if defined(CI_ROWS_FACTS) && defined(CI_ROWS_CORE)
    {"co_statfs", r_co_statfs},
    {"co_facts", r_co_facts},
#endif
#if defined(CI_ROWS_META) && defined(CI_ROWS_CORE)
    {"co_chmod", r_co_chmod},
    {"co_umask", r_co_umask},
    {"co_utimens", r_co_utimens},
    {"co_link", r_co_link},
    {"co_uname", r_co_uname},
#endif
#ifdef CI_ROWS_SIG
    {"sig_set", r_sig_set},
#endif
#ifdef CI_ROWS_CVIM
    {"cv_term_enter", r_cv_term_enter},
    {"cv_term_leave", r_cv_term_leave},
    {"cv_winch", r_cv_winch},
    {"cv_fsync", r_cv_fsync},
    {"cv_fchmod", r_cv_fchmod},
#endif
#ifdef CI_ROWS_VIEW
    {"view_winsize", r_view_winsize},
#endif
#ifdef CI_ROWS_TLS
    {"tls_open", r_tls_open},
    {"tls_read", r_tls_read},
    {"tls_write", r_tls_write},
    {"tls_close", r_tls_close},
#endif
#ifdef CI_ROWS_PTY
    {"pty_open", r_pty_open},
    {"pty_spawn", r_pty_spawn},
    {"pty_read", r_pty_read},
    {"pty_write", r_pty_write},
#endif
#ifdef CI_ROWS_DSP
    {"dsp_open", r_dsp_open},
    {"dsp_put", r_dsp_put},
    {"dsp_sync", r_dsp_sync},
#endif
#ifdef CI_ROWS_GRANT
    {"grant_set", r_grant_set},
    {"grant_ask", r_grant_ask},
    {"exec_from", r_exec_from},
#endif
#ifdef CI_ROWS_KERN
    {"kern_ask", r_kern_ask},
    {"kern_held", r_kern_held},
#endif
#ifdef CI_ROWS_TRAY
    {"tray_ask", r_tray_ask},
#endif
#ifdef CI_ROWS_OPEN
    {"open_ask", r_open_ask},
#endif
#ifdef CI_ROWS_DIR
    {"dir_names", r_dir_names},
#endif
};
const uint32_t ci_row_count = sizeof ci_rows / sizeof ci_rows[0];
