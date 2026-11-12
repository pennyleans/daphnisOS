/* tests/kfz/console_user.c: HW-14 (daphnis.uart=0) in the user flavor (RT_USER, the desk's images), the cases the KFZ
 * lane holds. The hosted kernel cannot see this: the console's ring, its COM1 choice and the port hooks cint's COM1
 * driver goes through are C, and tests/kfz/machine.ci stands in for rt/host.c. So this file runs the real rt/boot.c,
 * rt/console.c and rt/host.c's port hooks on the host, with a 16550 at COM1 (or none) and a surface (or none) kept by
 * counting stubs, and src/serial.ci's driver replayed through the hooks as the emitted C calls them. With the word,
 * nothing reaches COM1, the line status answers ready, and the ring and the screen take every byte; with a port that
 * reads 0xFF and no word, cint's bytes still reach the ring; without the word on a 16550, as before; before
 * rt_boot_init can read the line, each byte asks COM1 again, and the first byte after it decides once.
 * tests/hw/boot_tags.c holds the word in the kernel flavor. Each case runs in its own process, so it starts as a boot
 * does: nothing decided, nothing written. Built and run by tests/kfz/console.sh; exit status 1 if a case failed. */
#define _GNU_SOURCE
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/wait.h>
#include <unistd.h>
#include "../../rt/boot.c"
#include "../../rt/console.c"
#include "../../rt/host.c"

uint32_t mb_magic, mb_info;
uint8_t __image_end[1];

cint_status rt_phys_copy(bool to_phys, uint64_t base, void *buf, int64_t n, int64_t stride, unsigned width)
{
    (void)to_phys; (void)base; (void)buf; (void)n; (void)stride; (void)width;
    return CINT_REFUSED;
}

static void put32(uint8_t *p, uint32_t v) { memcpy(p, &v, sizeof v); }

/* The board: a 16550 at COM1, its registers as they are written and its transmit register always empty, or none
 * (every read 0xFF); every port access counted, COM1's (0x3F8 to 0x3FF) apart. Another port reads its low byte. */
static bool board_uart;
static uint8_t scratch, lcr, dll, fcr, mcr;
static unsigned port_ops, com1_ops, probes, com1_bytes, lcr_reads, lsr_reads;

static bool is_com1(uint16_t port) { return port >= COM1 && port <= COM1 + 7u; }

void port_out8(uint16_t port, uint8_t value)
{
    port_ops++;
    if (is_com1(port)) com1_ops++;
    if (port == COM1 + 7u) {
        scratch = value;
        if (value == 0xA5u) probes++;     /* a probe's first write */
    }
    if (port == COM1 + 3u) lcr = value;
    if (port == COM1 && (lcr & 0x80u) != 0u) dll = value;
    if (port == COM1 && (lcr & 0x80u) == 0u) com1_bytes++;
    if (port == COM1 + 2u) fcr = value;
    if (port == COM1 + 4u) mcr = value;
}

uint8_t port_in8(uint16_t port)
{
    port_ops++;
    if (is_com1(port)) com1_ops++;
    if (port == COM1 + 3u) lcr_reads++;
    if (port == COM1 + 5u) lsr_reads++;
    if (!is_com1(port)) return (uint8_t)(port & 0xFFu);
    if (!board_uart) return 0xFFu;
    if (port == COM1 + 7u) return scratch;
    if (port == COM1 + 3u) return lcr;
    return port == COM1 + 5u ? 0x60u : 0u;
}

/* The surface: none until fb_w is set; each row of a glyph the console draws is one put. */
static uint64_t fb_w, fb_h;
static unsigned fb_puts;

uint64_t rt_fb_word(int64_t i)
{
    if (i == 0) return fb_w;
    if (i == 1) return fb_h;
    return i == 2 ? fb_w * 4u : 0u;
}

cint_status rt_fb_put(uint64_t off, const uint8_t *src, int64_t len, int64_t stride)
{
    (void)off; (void)src; (void)len; (void)stride;
    fb_puts++;
    return CINT_OK;
}

/* rt_boot_init on a Multiboot 2 block holding only the command line line. */
static void line_boot(const char *line)
{
    uint8_t *blk = mmap((void *)0x10040000u, 4096u, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    assert(blk != MAP_FAILED && (uintptr_t)blk < SRC_HI - 4096u);
    size_t n = strlen(line) + 1u, at = 8u;
    assert(8u + n + 16u <= 4096u);
    memset(blk, 0, 4096u);
    put32(blk + at, 1u);
    put32(blk + at + 4, (uint32_t)(8u + n));
    memcpy(blk + at + 8, line, n);
    at += (8u + n + 7u) & ~(size_t)7u;
    put32(blk + at, 0u);
    put32(blk + at + 4, 8u);
    at += 8u;
    put32(blk, (uint32_t)at);
    mb_magic = MB2_MAGIC;
    mb_info = (uint32_t)(uintptr_t)blk;
    rt_boot_init();
    assert(boot_status == 2 && rt_boot_read());
}

static void say(const char *s)
{
    for (; *s != '\0'; s++) rt_console_byte((uint8_t)*s);
}

/* True when the ring's last bytes are s. */
static bool ring_ends(const char *s)
{
    uint64_t n = strlen(s), w = rt_console_written();
    if (w < n) return false;
    for (uint64_t i = 0u; i < n; i++)
        if (rt_console_at(w - n + i) != (uint8_t)s[i]) return false;
    return true;
}

/* A glyph at 2x (1920 pixels wide) is 32 rows, so 32 puts a cell. */
#define CELL_PUTS 32u

static void word_with_screen(void)
{
    board_uart = true;
    fb_w = 1920u;
    fb_h = 1080u;
    line_boot("console=ttyS0 daphnis.uart=0 daphnis.console=screen quiet");
    say("daphnis: up\nok\n");
    assert(port_ops == 0u && probes == 0u && com1_bytes == 0u);
    assert(ring_ends("daphnis: up\nok\n") && rt_console_written() == 15u);
    assert(fb_puts == 13u * CELL_PUTS);   /* every printing byte drawn; a newline draws nothing */
}

static void word_alone(void)
{
    board_uart = true;
    fb_w = 1920u;
    fb_h = 1080u;
    line_boot("daphnis.uart=0");
    say("daphnis: up\n");
    assert(port_ops == 0u && fb_puts == 0u && ring_ends("daphnis: up\n"));
}

static void word_before_the_surface(void)
{
    board_uart = true;
    line_boot("daphnis.console=screen daphnis.uart=0");
    say("ab\n");                          /* no surface yet: the ring alone */
    assert(port_ops == 0u && fb_puts == 0u);
    fb_w = 1920u;
    fb_h = 1080u;
    say("c");                             /* the surface up: the ring's last screenful drawn, then c */
    assert(port_ops == 0u && fb_puts == 3u * CELL_PUTS && ring_ends("ab\nc"));
}

static void no_word(void)
{
    board_uart = true;
    fb_w = 1920u;
    fb_h = 1080u;
    line_boot("console=ttyS0 daphnis.console=screen quiet");
    say("ab\n");
    assert(probes == 1u && com1_bytes == 3u && fb_puts == 2u * CELL_PUTS && ring_ends("ab\n"));
}

static const char *near_word;

static void not_the_word(void)
{
    board_uart = true;
    line_boot(near_word);
    assert(!rt_boot_uart_off());
    say("ab");
    assert(probes == 1u && com1_bytes == 2u && ring_ends("ab"));
}

static void window_with_uart(void)
{
    board_uart = true;
    assert(!rt_boot_read());
    say("ab");                            /* a panic in rt_boot_init: each byte asks COM1 again */
    assert(probes == 2u && com1_bytes == 2u && uart == -1);
    line_boot("daphnis.uart=0");
    port_ops = 0u;
    say("cd");                            /* the first byte after decides, once */
    assert(port_ops == 0u && uart == 0 && ring_ends("abcd"));
}

static void window_without_uart(void)
{
    board_uart = false;
    say("ab");
    assert(probes == 2u && com1_bytes == 0u && uart == -1);
    line_boot("quiet");
    say("c");
    assert(probes == 3u && com1_bytes == 0u && uart == 0);
    board_uart = true;                    /* decided: a 16550 that answers later is not asked */
    say("d");
    assert(probes == 3u && com1_bytes == 0u && ring_ends("abcd"));
}

static void word_past_the_read(void)
{
    char line[300];
    memset(line, 'a', 244u);
    strcpy(line + 244, " daphnis.uart=0");   /* 259 bytes: the read takes 255, which cut the word */
    board_uart = true;
    line_boot(line);
    assert(!rt_boot_uart_off());
    say("ab");
    assert(probes == 1u && com1_bytes == 2u);
}

static void word_at_the_read_end(void)
{
    char line[300];
    memset(line, 'a', 240u);
    strcpy(line + 240, " daphnis.uart=0");   /* 255 bytes: all read */
    board_uart = true;
    line_boot(line);
    say("ab");
    assert(port_ops == 0u && ring_ends("ab"));
}

/* cint's side: a port access as the emitted C makes it, through rt/host.c's row. */
static void cint_out8(uint16_t port, uint8_t v)
{
    cint_value a[2], r;
    memset(a, 0, sizeof a);
    memset(&r, 0, sizeof r);
    a[0].as.u64 = port;
    a[1].as.u64 = v;
    assert(hf_port_out8(a, &r) == CINT_OK);
}

static uint8_t cint_in8(uint16_t port)
{
    cint_value a[1], r;
    memset(a, 0, sizeof a);
    memset(&r, 0, sizeof r);
    a[0].as.u64 = port;
    assert(hf_port_in8(a, &r) == CINT_OK);
    return (uint8_t)r.as.u64;
}

/* src/serial.ci serial_init: 115200 8N1 (the divisor 1 written with DLAB set), the FIFO, the modem control. */
static void cint_serial_init(void)
{
    cint_out8(COM1 + 1u, 0u);
    cint_out8(COM1 + 3u, 0x80u);
    cint_out8(COM1, 1u);
    cint_out8(COM1 + 1u, 0u);
    cint_out8(COM1 + 3u, 3u);
    cint_out8(COM1 + 2u, 0xC7u);
    cint_out8(COM1 + 4u, 0x0Bu);
}

/* src/serial.ci serial_write: each byte waits for the transmit register to be empty, then goes to it. */
static void cint_write(const char *s)
{
    for (; *s != '\0'; s++) {
        unsigned spins = 0u;
        while ((cint_in8(COM1 + 5u) & 0x20u) == 0u) assert(++spins < 1000u);
        cint_out8(COM1, (uint8_t)*s);
    }
}

static void hooks_word(void)
{
    board_uart = true;
    line_boot("console=ttyS0 daphnis.uart=0");
    cint_serial_init();
    cint_write("hi\n");
    assert(port_ops == 0u && com1_ops == 0u);
    assert(ring_ends("hi\n") && rt_console_written() == 3u);   /* the divisor, written with DLAB set, is no byte */
    uint8_t lsr = cint_in8(COM1 + 5u);
    assert(lsr == 0x60u);                                        /* ready to send, nothing received */
    for (uint16_t p = COM1; p <= COM1 + 7u; p++)
        if (p != COM1 + 5u) assert(cint_in8(p) == 0u);
    cint_out8(COM1 + 3u, 0x80u);                                 /* the shadow follows LCR with the word too */
    cint_out8(COM1, 'Z');
    cint_out8(COM1 + 3u, 3u);
    cint_out8(COM1, 'z');
    assert(port_ops == 0u && ring_ends("hi\nz") && rt_console_written() == 4u);
}

static void hooks_word_other_ports(void)
{
    static const uint16_t ports[] = {COM1 - 1u, COM1 + 8u, 0x2F8u, 0x2FFu, 0x60u, 0x71u};
    board_uart = true;
    line_boot("daphnis.uart=0");
    for (unsigned i = 0u; i < sizeof ports / sizeof ports[0]; i++) {
        unsigned before = port_ops;
        assert(cint_in8(ports[i]) == (uint8_t)(ports[i] & 0xFFu));
        cint_out8(ports[i], 7u);
        assert(port_ops == before + 2u);
    }
    assert(com1_ops == 0u);
}

static void hooks_no_uart(void)
{
    board_uart = false;
    line_boot("quiet");
    cint_serial_init();
    cint_write("ok\n");
    assert(ring_ends("ok\n") && rt_console_written() == 3u && lcr_reads == 0u && com1_bytes == 0u);
}

static void hooks_uart(void)
{
    board_uart = true;
    line_boot("console=ttyS0 quiet");
    cint_serial_init();
    assert(lcr == 3u && dll == 1u && fcr == 0xC7u && mcr == 0x0Bu);   /* every register reached the 16550 */
    cint_write("ok\n");
    assert(com1_bytes == 3u && ring_ends("ok\n") && rt_console_written() == 3u);
    unsigned before = com1_ops;
    assert(lsr_reads >= 3u && lcr_reads == 0u && cint_in8(COM1 + 5u) == 0x60u && com1_ops == before + 1u);
}

static void hooks_window(void)
{
    board_uart = true;
    assert(!rt_boot_read());
    cint_serial_init();                                          /* before the line is read: the port, as before */
    assert(lcr == 3u && dll == 1u);
    cint_write("a");
    assert(com1_bytes == 1u && ring_ends("a"));
    line_boot("daphnis.uart=0");
    port_ops = com1_ops = 0u;
    cint_serial_init();
    cint_write("b");
    assert(port_ops == 0u && com1_ops == 0u && ring_ends("ab"));
}

static unsigned passed, total;

static void run(const char *name, void (*f)(void))
{
    int st = 0;
    fflush(stdout);
    pid_t p = fork();
    assert(p >= 0);
    if (p == 0) {
        f();
        _exit(0);
    }
    assert(waitpid(p, &st, 0) == p);
    bool ok = WIFEXITED(st) && WEXITSTATUS(st) == 0;
    total++;
    if (ok) passed++;
    printf("test console: %s ... %s\n", name, ok ? "ok" : "FAILED");
}

int main(void)
{
    static const char *const near[] = {"daphnis.uart=", "daphnis.uart", "daphnis.uart=0,", "Daphnis.uart=0",
                                       "daphnis.uart=O", "daphnis.uart=0=0", "daphnis.uart.0", "daphnis.uart==0",
                                       "daphnis.uart=0daphnis.uart=0", "console=daphnis.uart=0",
                                       "daphnis.uart=1"};
    run("HW-14: with daphnis.uart=0, COM1 is never probed or written; the ring and the screen take every byte",
        word_with_screen);
    run("HW-14: with daphnis.uart=0 and no daphnis.console=screen, the ring alone", word_alone);
    run("HW-14: with daphnis.uart=0, the bytes before the surface reach the screen from the ring",
        word_before_the_surface);
    run("HW-14: without the word, COM1 probed once and written every byte, as before; the screen too", no_word);
    for (unsigned i = 0u; i < sizeof near / sizeof near[0]; i++) {
        char name[160];
        near_word = near[i];
        snprintf(name, sizeof name, "HW-14: `%s` is not the word: COM1 as before", near[i]);
        run(name, not_the_word);
    }
    run("HW-14: before rt_boot_init reads the line, each byte asks COM1 again; the first byte after decides",
        window_with_uart);
    run("HW-14: before rt_boot_init with no 16550, each byte probes and none is written; then decided once",
        window_without_uart);
    run("HW-14: a word the 255-byte read cuts is not the word: COM1 as before", word_past_the_read);
    run("HW-14: the word ending on the read's last byte is read", word_at_the_read_end);
    run("HW-14 hooks: with the word, cint's COM1 driver reaches no port; LSR ready; THR bytes in the ring only",
        hooks_word);
    run("HW-14 hooks: with the word, every port outside 0x3F8 to 0x3FF still reaches its device",
        hooks_word_other_ports);
    run("HW-14 hooks: no 16550 (0xFF) and no word: cint's bytes reach the ring, LCR never read from the port",
        hooks_no_uart);
    run("HW-14 hooks: a 16550 and no word: every register reaches it, THR bytes the ring and COM1, as before",
        hooks_uart);
    run("HW-14 hooks: before the line is read, the port as before; after it, the word drops COM1", hooks_window);
    printf("%u of %u tests passed\n", passed, total);
    return passed == total ? 0 : 1;
}
