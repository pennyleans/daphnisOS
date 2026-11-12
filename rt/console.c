/* rt/console.c: HW-3 (docs/specs/2026-11-06-hw-hardware.md section 5, row HW-3), the console on a board. Every byte
 * of the transcript, cint's (src/serial.ci's console_putc row) and C's (rt_serial_byte: faults and panics, which run
 * when cint cannot), goes here first:
 *   - into a RAM ring of 64 KiB (the spec says 256; the image's low window has room for 64), the last bytes of the run,
 *     for the stick's log once HW-4m writes one;
 *   - to COM1 when the 16550 answers its scratch register (a board without one reads 0xFF there), unless the boot line
 *     holds daphnis.uart=0 (HW-14): then COM1 is never probed or written, because each byte waits for the UART's
 *     transmit register and on a board that makes the network's journal lines cost 105 to 270 ms each. The word is
 *     read once, at the first byte after rt_boot_init made the line readable; a byte before that (a panic in
 *     rt_boot_init) may still reach COM1;
 *   - to the screen with daphnis.console=screen once there is a surface (the user flavors): the kit's face (rt/face.h,
 *     8 x 16) at 2x from 1920 pixels wide and at 1x below, white on black, on the shadow surface rt/fb.c presents.
 *     The text fills the screen top to bottom, then the screen is cleared and it starts again at the top (no
 *     scrolling, so a line costs one row's pixels, not a copy of the screen; a photo reads top to bottom in order).
 * It lives in C, not in a cint module, because a fault or panic must reach the screen and the ring too. A capture build
 * (RT_CAPTURE) has none of it: its bytes go to the encrypted sink, and its 64 KiB stay out of the low window. */
#include "rt.h"

#ifndef RT_CAPTURE   /* capture builds send every byte to their sink (rt/serial.c, rt/host.c), not here */
#include "face.h"

#define CONSOLE_RING (64u * 1024u)   /* the spec's 256 KiB does not fit the low window (below 2 MiB) with the image */
#define COM1 0x3F8u

static uint8_t ring[CONSOLE_RING];
static uint64_t written;       /* every byte since boot; the ring holds the last CONSOLE_RING */
static int uart = -1;          /* -1 not decided, 0 none or daphnis.uart=0, 1 there */
static int off = -1;           /* daphnis.uart=0: -1 not decided, 0 absent, 1 held */

/* 1 when a 16550 answers its scratch register at COM1, else 0. */
static int uart_probe(void)
{
    port_out8(COM1 + 7u, 0xA5u);
    if (port_in8(COM1 + 7u) != 0xA5u) return 0;
    port_out8(COM1 + 7u, 0x5Au);
    return port_in8(COM1 + 7u) == 0x5Au ? 1 : 0;
}

/* HW-14: true when the boot line holds daphnis.uart=0, decided once it is readable; false before. rt/host.c asks it
 * too, so cint's own COM1 driver (src/serial.ci, src/serialrx.ci) never reaches the port with the word. */
bool rt_console_uart_off(void)
{
    if (off < 0) {
        if (!rt_boot_read()) return false;
        off = rt_boot_uart_off() ? 1 : 0;
    }
    return off == 1;
}

/* Decided once the boot line is readable; before that, COM1 when it answers, each byte asking again. */
static bool uart_there(void)
{
    if (uart < 0) {
        if (!rt_boot_read()) return uart_probe() == 1;
        uart = rt_console_uart_off() ? 0 : uart_probe();
    }
    return uart == 1;
}

uint64_t rt_console_written(void) { return written; }

/* The ring's byte at absolute position at (at < written, at >= written - CONSOLE_RING), else 0. */
uint8_t rt_console_at(uint64_t at)
{
    if (at >= written || written - at > CONSOLE_RING) return 0u;
    return ring[at % CONSOLE_RING];
}

#ifdef RT_USER
static int screen = -1;        /* -1 not decided, 0 off, 1 on */
static uint32_t col, row, cols, rows, scale;

static bool cmdline_word(const char *w)
{
    char line[256];
    size_t n = rt_boot_cmdline(line, sizeof line), k = 0u;
    while (w[k] != '\0') k++;
    for (size_t i = 0u; i + k <= n; i++) {
        if ((i == 0u || line[i - 1u] == ' ') && (i + k == n || line[i + k] == ' ')) {
            size_t j = 0u;
            while (j < k && line[i + j] == w[j]) j++;
            if (j == k) return true;
        }
    }
    return false;
}

/* The screen once the surface is up: off until rt_fb_word gives a width, then decided once. */
static bool screen_on(void)
{
    uint64_t w, h;
    if (screen >= 0) return screen == 1;
    w = rt_fb_word(0);
    h = rt_fb_word(1);
    if (w == 0u || h == 0u) return false;
    screen = cmdline_word("daphnis.console=screen") ? 1 : 0;
    scale = w >= 1920u ? 2u : 1u;
    cols = (uint32_t)(w / (8u * scale));
    rows = (uint32_t)(h / (16u * scale));
    if (cols == 0u || rows < 2u) screen = 0;
    return screen == 1;
}

static void screen_byte(uint8_t c);

/* The surface came up after the banner: what the ring holds of the last screenful is drawn first. */
static void replay(void)
{
    uint64_t span = (uint64_t)cols * (rows - 1u), from = written > span ? written - span : 0u;
    if (written - from > CONSOLE_RING) from = written - CONSOLE_RING;
    for (uint64_t at = from; at < written; at++) screen_byte(ring[at % CONSOLE_RING]);
}

/* One text cell: glyph c (a space for 0, '?' outside 32 to 126) at cell (x, y). */
static void cell(uint32_t x, uint32_t y, uint8_t c)
{
    uint32_t px[16];
    uint64_t stride = rt_fb_word(2);
    uint32_t wpx = 8u * scale;
    if (c == 0u) c = ' ';
    if (c < 32u || c > 126u) c = '?';
    for (uint32_t r = 0u; r < 16u * scale; r++) {
        uint32_t gr = r / scale;
        uint64_t word = face_bits[2u * (c - 32u) + (gr >= 8u ? 1u : 0u)];
        uint8_t bits = (uint8_t)(word >> (8u * (7u - gr % 8u)));
        for (uint32_t x8 = 0u; x8 < wpx; x8++) px[x8] = ((bits >> (7u - x8 / scale)) & 1u) != 0u ? 0xFFFFFFFFu : 0u;
        uint64_t off = ((uint64_t)y * 16u * scale + r) * stride + (uint64_t)x * wpx * 4u;
        (void)rt_fb_put(off, (const uint8_t *)px, (int64_t)wpx * 4, 1);
    }
}

static void clear_row(uint32_t y)
{
    for (uint32_t x = 0u; x < cols; x++) cell(x, y, ' ');
}

static void screen_byte(uint8_t c)
{
    if (c == '\r') return;
    if (c == '\n' || col == cols) {
        col = 0u;
        row++;
        if (row == rows) {               /* the screen is full: cleared, and the text starts again at the top */
            for (uint32_t y = 0u; y < rows; y++) clear_row(y);
            row = 0u;
        }
        if (c == '\n') return;
    }
    cell(col, row, c);
    col++;
}
#endif

void rt_console_byte(uint8_t c)
{
    ring[written % CONSOLE_RING] = c;
    written++;
    if (uart_there()) {
        while ((port_in8(COM1 + 5u) & 0x20u) == 0u) {
        }
        port_out8(COM1, c);
    }
#ifdef RT_USER
    if (screen < 0) {
        if (screen_on()) replay();   /* this byte is in the ring already: the replay draws it */
        return;
    }
    if (screen == 1) screen_byte(c);
#endif
}
#endif
