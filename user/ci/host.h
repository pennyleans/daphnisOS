/* user/ci/host.h: the host rows of a cint program in ring 3 (user/ci/host.c), bound by user/ci/main.c. */
#ifndef CI_HOST_H
#define CI_HOST_H
#include <stdint.h>

#include "cint_rt.h"

typedef struct ci_row {
    const char *name;   /* as the `extern` declares it */
    cint_status (*call)(void *user, const cint_value *args, uint32_t nargs, cint_value *result);
} ci_row;

extern const ci_row ci_rows[];
extern const uint32_t ci_row_count;

/* The surface from C, for a client that blits its own frame (user/ci/doom/client.c): ci_fb_open as the
 * `fb_open` row (0, or -errno), ci_fb_word as `fb_word`, ci_fb_put as `fb_row` with px contiguous. */
int64_t ci_fb_open(void);
uint64_t ci_fb_word(int64_t i);
void ci_fb_put(int64_t y, const uint8_t *px, int64_t len);

#if defined(CI_ROWS_WIN) || defined(CI_WIN_C)
/* H-3c3: the size the next ci_fb_open asks (FBIO_TILE_WANT; a refusal leaves the offer), the bar variable
 * (FBIO_TILE_VAR, at most 64 bytes) and resize events (FBIO_TILE_RESIZE); 0, or -errno. */
void ci_win_want(int64_t w, int64_t h);
int64_t ci_win_var(const uint8_t *v, int64_t n);
int64_t ci_win_resize(int64_t on);
#endif

/* A program past its cap cannot start (user/ci/main.c says so on descriptor 2); tools/check-rows.py holds every
 * program within its cap. RS-SET (PR 412): hdesk binds 78 (l-3 68: run_as's 4, EVIOCGREP/SREP's 2, factsctl's 2,
 * fdctl's fd_stat, corectl's co_settime) and finder 49 (co_settime), past 72 and 48: 96 and 64 now. */
#if defined(CI_ROWS_HDESK) && defined(CI_ROWS_CORE)
#define CI_MAX_ROWS 96u   /* FF-5: the desk with the index binds 55: dev, tilectl, tileplace, hdeskctl, ptyctl, sh, corectl; FF-R6 B: 56, and wall; RS-SHOT: 65 */
#elif defined(CI_ROWS_CORE)
#define CI_MAX_ROWS 64u   /* CT-1: a core tool binds dev's 6, cish's 23 and corectl's 13 at most (CT-5) */
#elif defined(CI_ROWS_SH) && (defined(CI_ROWS_TLS) || defined(CI_ROWS_TCP))
#define CI_MAX_ROWS 40u   /* A-5: agent binds 37 (dev, tcp, udp, tls and cish's sh rows); 39 declared after CS-4; CT-5: wget, the same less tls */
#elif defined(CI_ROWS_SH)
#define CI_MAX_ROWS 32u   /* CS-1: cish binds 15 rows of its own and dev's 6; CS-4: 20 of its own */
#elif defined(CI_ROWS_PTY) || (defined(CI_ROWS_NET) && defined(CI_ROWS_TCP))
#define CI_MAX_ROWS 24u   /* W-4: the tiler binds 17 rows; A-2: agent 17 (dev, tcp, udp), A-4: 21 (and tls); the others keep their bytes */
#else
#define CI_MAX_ROWS 16u
#endif
/* The frame arena (SPEC-04 LS-110): 1 MiB here, well under a process's quota (src/uvm.ci MAX_FRAMES, M-1)
 * with room for the heap; the arena is taken as the program needs it. */
#ifndef CI_FRAME_ARENA_BYTES   /* BP-3: user/ci/build.sh gives cview its own (its decode buffers are frame locals) */
#define CI_FRAME_ARENA_BYTES ((int64_t)1048576)
#endif
#endif
