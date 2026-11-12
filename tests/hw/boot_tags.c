/* HW-1: exercise the real loader parser, including the GOP path Bochs normally hides; HW-14: the console's COM1 word. */
#define _GNU_SOURCE
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>
#include "../../rt/boot.c"
#include "../../rt/console.c"

uint32_t mb_magic, mb_info;
uint8_t __image_end[1];
static size_t framebuffer_at;

static bool read_in_copy;      /* HW-14: what rt_boot_read() said while rt_boot_init was copying */

cint_status rt_phys_copy(bool to_phys, uint64_t base, void *buf, int64_t n, int64_t stride, unsigned width)
{
    (void)to_phys; (void)base; (void)buf; (void)n; (void)stride; (void)width;
    read_in_copy = rt_boot_read();
    return CINT_REFUSED;
}

static void put32(uint8_t *p, uint32_t v) { memcpy(p, &v, sizeof v); }
static void put64(uint8_t *p, uint64_t v) { memcpy(p, &v, sizeof v); }

/* HW-14: a 16550 at COM1 (or none), counted. Its transmit register is always empty. */
static bool board_uart;
static uint8_t scratch;
static unsigned port_ops, com1_bytes;

void port_out8(uint16_t port, uint8_t value)
{
    port_ops++;
    if (port == COM1 + 7u) scratch = value;
    if (port == COM1) com1_bytes++;
}

uint8_t port_in8(uint16_t port)
{
    port_ops++;
    if (!board_uart) return 0xFFu;
    if (port == COM1 + 7u) return scratch;
    return port == COM1 + 5u ? 0x20u : 0xFFu;
}

/* A Multiboot 2 block holding only the command line, read by rt_boot_init; the console's decision cleared. */
static void line_boot(uint8_t *blk, const char *line)
{
    size_t n = strlen(line) + 1u, at = 8u;
    memset(blk, 0, 4096u);
    put32(blk + at, 1u); put32(blk + at + 4, (uint32_t)(8u + n)); memcpy(blk + at + 8, line, n);
    at += (8u + n + 7u) & ~(size_t)7u;
    put32(blk + at, 0u); put32(blk + at + 4, 8u); at += 8u;
    put32(blk, (uint32_t)at);
    mb_magic = MB2_MAGIC; mb_info = (uint32_t)(uintptr_t)blk;
    rt_boot_init();
    assert(boot_status == 2);
    uart = off = -1;
    port_ops = com1_bytes = 0u;
}

/* HW-14: daphnis.uart=0 keeps every byte in the ring and never probes or writes COM1; without it, COM1 as before. */
static void uart_word(void)
{
    uint8_t *blk = mmap((void *)0x10020000u, 4096u, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    assert(blk != MAP_FAILED && (uintptr_t)blk < SRC_HI - 4096u);
    /* Before rt_boot_init the line cannot be read: COM1 when it answers, and nothing decided. */
    assert(!rt_boot_read() && !rt_console_uart_off());
    board_uart = true;
    rt_console_byte('a');
    assert(com1_bytes == 1u && uart == -1);
    /* The word: no port touched, the bytes in the ring, the decision kept. */
    line_boot(blk, "console=ttyS0 daphnis.uart=0 quiet");
    assert(rt_boot_read() && rt_boot_uart_off() && rt_console_uart_off());
    rt_console_byte('b');
    rt_console_byte('c');
    assert(port_ops == 0u && uart == 0);
    assert(rt_console_at(rt_console_written() - 2u) == 'b' && rt_console_at(rt_console_written() - 1u) == 'c');
    line_boot(blk, "daphnis.uart=0");
    rt_console_byte('d');
    assert(port_ops == 0u && uart == 0);
    /* Not the word: probed once, every byte to COM1. */
    const char *other[] = {"", "quiet", "daphnis.uart=1", "daphnis.uart=00", "xdaphnis.uart=0", "daphnis.uart=0x"};
    for (unsigned i = 0u; i < 6u; i++) {
        line_boot(blk, other[i]);
        assert(!rt_boot_uart_off() && !rt_console_uart_off());
        rt_console_byte('e');
        rt_console_byte('f');
        assert(uart == 1 && com1_bytes == 2u);
    }
    /* No 16550 and no word: probed, nothing written. */
    board_uart = false;
    line_boot(blk, "quiet");
    rt_console_byte('g');
    assert(uart == 0 && com1_bytes == 0u && port_ops > 0u);
    assert(rt_console_at(rt_console_written() - 1u) == 'g');
    /* No loader block: no line, so no word; decided once, COM1 when it answers. */
    board_uart = true;
    mb_magic = 0u; mb_info = 0u;
    rt_boot_init();
    assert(boot_status == -1 && rt_boot_read() && !rt_boot_uart_off());
    uart = off = -1;
    com1_bytes = 0u;
    rt_console_byte('h');
    assert(uart == 1 && com1_bytes == 1u);
    /* While rt_boot_init copies the loader's block the line is not yet readable (a review's P3). */
    boot_done = false;
    mb_magic = MB1_MAGIC;
    rt_boot_init();
    assert(!read_in_copy && rt_boot_read() && boot_status == -1);
    mb_magic = 0u;
    assert(munmap(blk, 4096u) == 0);
    boot_status = 0;
    boot_done = false;
    uart = off = -1;
}

static void framebuffer(uint8_t *t)
{
    memset(t, 0, 40);
    put32(t, 8u); put32(t + 4, 38u);
    put64(t + 8, 0x1234000000u);
    put32(t + 16, 2560u); put32(t + 20, 640u); put32(t + 24, 480u);
    t[28] = 32u; t[29] = 1u;
    t[32] = 16u; t[33] = 8u; t[34] = 8u; t[35] = 8u; t[36] = 0u; t[37] = 8u;
}

static bool found(void)
{
    uint64_t a = 0;
    uint32_t p = 0, w = 0, h = 0;
    struct rt_fb_format format;
    bool ok = rt_boot_framebuffer(&a, &p, &w, &h, &format);
    if (ok) {
        assert(a == 0x1234000000u && p == 2560u && w == 640u && h == 480u);
        assert(format.pos[0] == boot_copy[framebuffer_at + 32u] && format.pos[1] == boot_copy[framebuffer_at + 34u] &&
               format.pos[2] == boot_copy[framebuffer_at + 36u]);
        assert(format.bits[0] == 8u && format.bits[1] == 8u && format.bits[2] == 8u);
    }
    return ok;
}

/* g24 (unit 4b): a module GRUB put outside [__image_end, 32 MiB), as under OVMF, is moved into it. A block of
 * one module tag and a map of usable and NVS ranges; the RAM is real host pages at fixed low addresses. */
static uint8_t *ram(uint64_t pa, size_t n)
{
    void *p = mmap((void *)(uintptr_t)pa, n, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0);
    assert(p == (void *)(uintptr_t)pa);
    return p;
}

static void pattern(uint64_t pa, size_t n, unsigned seed)
{
    for (size_t i = 0; i < n; i++) ((uint8_t *)(uintptr_t)pa)[i] = (uint8_t)((i * 131u + seed) >> 3);
}

static bool same(uint64_t pa, size_t n, unsigned seed)
{
    for (size_t i = 0; i < n; i++)
        if (((const uint8_t *)(uintptr_t)pa)[i] != (uint8_t)((i * 131u + seed) >> 3)) return false;
    return true;
}

static uint64_t g24_boot(uint8_t *blk, uint32_t lo, uint32_t hi, const uint64_t (*map)[3], unsigned n, uint64_t *bytes)
{
    size_t at = 8;
    put32(blk + at, 3u); put32(blk + at + 4, 16u); put32(blk + at + 8, lo); put32(blk + at + 12, hi); at += 16u;
    put32(blk + at, 6u); put32(blk + at + 4, 16u + 24u * n); put32(blk + at + 8, 24u); put32(blk + at + 12, 0u);
    for (unsigned i = 0; i < n; i++) {
        put64(blk + at + 16 + 24u * i, map[i][0]); put64(blk + at + 24 + 24u * i, map[i][1]);
        put32(blk + at + 32 + 24u * i, (uint32_t)map[i][2]); put32(blk + at + 36 + 24u * i, 0u);
    }
    at += 16u + 24u * n;
    put32(blk + at, 0u); put32(blk + at + 4, 8u); at += 8u;
    put32(blk, (uint32_t)at);
    mb_magic = MB2_MAGIC; mb_info = (uint32_t)(uintptr_t)blk;
    rt_boot_init();
    assert(boot_status == 2);
    return rt_boot_module(bytes);
}

static void g24_moves(void)
{
    uint8_t *blk = mmap((void *)0x10010000u, 4096u, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    assert(blk != MAP_FAILED && (uintptr_t)blk < SRC_HI - 4096u);
    uint64_t bytes = 0;
    /* 1. Above the pool's base, RAM at 28 to 30 MiB, NVS at 30 MiB: moved to 28 MiB, the bytes intact. */
    uint8_t *dst = ram(0x1C00000u, 0x200000u), *src = ram(0x2100000u, 0x180000u);
    const uint64_t above[][3] = {{0x1C00000u, 0x200000u, 1u}, {0x1E00000u, 0x1000u, 4u}, {0x1E01000u, 0x1FF000u, 1u},
                                 {0x2000000u, 0x400000u, 1u}};
    pattern(0x2100000u, 0x180000u, 7u);
    assert(g24_boot(blk, 0x2100000u, 0x2280000u, above, 4u, &bytes) == 0x1C00000u && bytes == 0x180000u);
    assert(same(0x1C00000u, 0x180000u, 7u));
    assert(!rt_boot_shadow_free(0x1C00000u, 4096u) && !rt_boot_shadow_free(0x1D7F000u, 4096u)); /* the moved module */
    assert(rt_boot_shadow_free(0x1D80000u, 4096u));
    /* 2. No run of its size: 2.5 MiB against 2 MiB, NVS, 2 MiB less a page. Not taken, nothing written. */
    memset(dst, 0x5A, 0x200000u);
    assert(g24_boot(blk, 0x2100000u, 0x2380000u, above, 4u, &bytes) == 0u && bytes == 0u);
    for (size_t i = 0; i < 0x200000u; i++) assert(dst[i] == 0x5A);
    /* 3. Across 32 MiB, RAM from 30 MiB: the run starts below the source and covers part of it (memmove). */
    assert(munmap(dst, 0x200000u) == 0 && munmap(src, 0x180000u) == 0);
    uint8_t *over = ram(0x1E00000u, 0x280000u);
    const uint64_t across[][3] = {{0x1E00000u, 0x300000u, 1u}};
    pattern(0x1F00000u, 0x180000u, 11u);
    assert(g24_boot(blk, 0x1F00000u, 0x2080000u, across, 1u, &bytes) == 0x1E00000u && bytes == 0x180000u);
    assert(same(0x1E00000u, 0x180000u, 11u));
    /* 4. Inside the window it stays where the loader put it. */
    pattern(0x1F00000u, 0x100000u, 13u);
    assert(g24_boot(blk, 0x1F00000u, 0x2000000u, across, 1u, &bytes) == 0x1F00000u && bytes == 0x100000u);
    assert(same(0x1F00000u, 0x100000u, 13u));
    assert(munmap(over, 0x280000u) == 0 && munmap(blk, 4096u) == 0);
}

/* RG-1: GRUB's Multiboot 2 block under OVMF at 512 MiB, 8,304 bytes (an EFI memory map tag of 6,192), past the 8 KiB
 * the copy had: now copied whole, and fitted for the kernel's 8 KiB readers with the EFI map left out. A block past
 * RT_BOOT_INFO_BYTES is fitted into the copy from the source, and rt_boot_fitted gives rt_start its size. */
static void ovmf_block(void)
{
    uint8_t *blk = mmap((void *)0x10040000u, 2u * RT_BOOT_INFO_BYTES, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    assert(blk != MAP_FAILED && (uintptr_t)blk < SRC_HI - 2u * RT_BOOT_INFO_BYTES);
    const char *line = "daphnis.pool=max daphnis.uart=0 daphnis.disk.write=6461706e-6869-7300-0000-000000000005 daphnis.poweroff=1";
    size_t n = strlen(line) + 1u, at = 8u;
    memset(blk, 0, 2u * RT_BOOT_INFO_BYTES);
    put32(blk + at, 1u); put32(blk + at + 4, (uint32_t)(8u + n)); memcpy(blk + at + 8, line, n);
    at += (8u + n + 7u) & ~(size_t)7u;
    put32(blk + at, 3u); put32(blk + at + 4, 24u);                          /* the release image, as module2 names it */
    put32(blk + at + 8, 0x1800000u); put32(blk + at + 12, 0x1900000u); memcpy(blk + at + 16, "initrd", 7u);
    at += 24u;
    size_t map = at;                                                         /* the map: one usable range */
    put32(blk + at, 6u); put32(blk + at + 4, 40u); put32(blk + at + 8, 24u);
    put64(blk + at + 16, 0u); put64(blk + at + 24, SRC_HI); put32(blk + at + 32, 1u);
    at += 40u;
    put32(blk + at, 15u); put32(blk + at + 4, 44u); memcpy(blk + at + 8, "RSD PTR ", 8u);   /* ACPI, new RSDP */
    at += 48u;
    size_t efi = at, efi_size = 8304u - 8u - 8u - at;                        /* the EFI memory map, the large one */
    put32(blk + at, 17u); put32(blk + at + 4, (uint32_t)efi_size); memset(blk + at + 16, 0xA5, efi_size - 16u);
    at += efi_size;
    put32(blk + at, 20u); put32(blk + at + 4, 8u); at += 8u;               /* an image handle tag after it, kept */
    put32(blk + at, 0u); put32(blk + at + 4, 8u); at += 8u;
    assert(at == 8304u && efi_size % 8u == 0u);
    put32(blk, (uint32_t)at);
    mb_magic = MB2_MAGIC; mb_info = (uint32_t)(uintptr_t)blk;
    rt_boot_init();
    assert(boot_status == 2 && boot_bytes == 8304u && memcmp(boot_copy, blk, 8304u) == 0 && rt_boot_fitted() == 0u);
    assert(rt_boot_pool_max() && rt_boot_poweroff() && rt_boot_uart_off());
    uint64_t bytes = 0;
    assert(rt_boot_module(&bytes) == 0x1800000u && bytes == 0x100000u);
    uint8_t whole[RT_BOOT_INFO_BYTES], fit[8192];
    assert(rt_boot_info(whole, sizeof whole) == 2 && memcmp(whole, blk, 8304u) == 0);
    memset(fit, 0xEE, sizeof fit);
    assert(rt_boot_info(fit, sizeof fit) == 2);
    uint32_t total = u32_at(fit, 0);
    assert(total == 8304u - efi_size && total <= sizeof fit);
    assert(memcmp(fit, blk + 0, 4) != 0 && memcmp(fit + 4, blk + 4, 4) == 0);
    assert(memcmp(fit + 8, blk + 8, efi - 8u) == 0);                        /* every tag before the EFI map, as it was */
    assert(u32_at(fit, efi) == 20u && u32_at(fit, efi + 4) == 8u);          /* the EFI map left out, the next tag kept */
    assert(u32_at(fit, efi + 8) == 0u && u32_at(fit, efi + 12) == 8u && efi + 16u == total);
    assert(u32_at(fit, map) == 6u && u32_at(fit, map + 8) == 24u);
    uint8_t tiny[12];
    memset(tiny, 0xEE, sizeof tiny);                                         /* no reader is that small: -3, untouched */
    assert(rt_boot_info(tiny, sizeof tiny) == -3 && tiny[0] == 0xEEu && tiny[11] == 0xEEu);

    /* Kernel read P2 (1): a tag the kernel reads is never left out. A 6,000-byte EFI map ahead of the RSDP and a 3,856-byte
     * map, 10,064 bytes in all with the loader's name: an 8 KiB reader gets them with the EFI map left out, not the RSDP; a 2 KiB reader, which the read tags
     * alone overrun, gets -3 with dst untouched (rt/host.c's row then halts); a 64 KiB reader takes it whole. */
    memset(blk, 0, 2u * RT_BOOT_INFO_BYTES);
    at = 8u;
    put32(blk + at, 1u); put32(blk + at + 4, (uint32_t)(8u + n)); memcpy(blk + at + 8, line, n);
    at += (8u + n + 7u) & ~(size_t)7u;
    size_t big = at;                                                         /* a large EFI map AHEAD of the read tags */
    put32(blk + at, 17u); put32(blk + at + 4, 6000u); at += 6000u;
    put32(blk + at, 2u); put32(blk + at + 4, 13u); memcpy(blk + at + 8, "GRUB", 5u); at += 16u;   /* the loader's name */
    put32(blk + at, 15u); put32(blk + at + 4, 44u); memcpy(blk + at + 8, "RSD PTR ", 8u); at += 48u;
    put32(blk + at, 6u); put32(blk + at + 4, 16u + 24u * 160u); put32(blk + at + 8, 24u);   /* a 3,856-byte map */
    put64(blk + at + 16, 0u); put64(blk + at + 24, SRC_HI); put32(blk + at + 32, 1u);
    at += 16u + 24u * 160u;
    put32(blk + at, 0u); put32(blk + at + 4, 8u); at += 8u;
    put32(blk, (uint32_t)at);
    rt_boot_init();
    assert(boot_status == 2 && boot_bytes == at && rt_boot_fitted() == 0u);
    memset(fit, 0xEE, sizeof fit);
    assert(rt_boot_info(fit, sizeof fit) == 2);                              /* 8 KiB: the read tags fit, the EFI map not */
    assert(u32_at(fit, big) == 2u && u32_at(fit, big + 16u) == 15u && u32_at(fit, big + 64u) == 6u);   /* behind the gap */
    assert(u32_at(fit, 0) == at - 6000u && at > sizeof fit);
    size_t tight = at - 6000u - 16u;                                         /* room for the read tags only: the name, */
    uint8_t exact[8192];                                                    /* which fits, gives way to the RSDP after it */
    assert(rt_boot_info(exact, (int64_t)tight) == 2 && u32_at(exact, 0) == tight);
    assert(u32_at(exact, big) == 15u && u32_at(exact, big + 48u) == 6u && u32_at(exact, tight - 8u) == 0u);
    uint8_t small[2048];                                                    /* the read tags alone overrun 2 KiB: -3 */
    memset(small, 0xEE, sizeof small);
    assert(rt_boot_info(small, sizeof small) == -3 && small[0] == 0xEEu && small[sizeof small - 1u] == 0xEEu);
    assert(rt_boot_info(whole, sizeof whole) == 2 && memcmp(whole, blk, at) == 0);

    /* Kernel read P2 (2): a block past the copy is fitted into it from the source, not refused. The EFI map grown so
     * the block is 65,544 bytes: the copy keeps the boot line, RSDP and map, and the size reaches rt_start's line. */
    memmove(blk + big + RT_BOOT_INFO_BYTES + 8u, blk + big + 6000u, at - big - 6000u);
    put32(blk + big + 4, RT_BOOT_INFO_BYTES + 8u);
    at += RT_BOOT_INFO_BYTES + 8u - 6000u;
    put32(blk, (uint32_t)at);
    assert(at > RT_BOOT_INFO_BYTES && at <= 2u * RT_BOOT_INFO_BYTES);
    rt_boot_init();
    assert(boot_status == 2 && rt_boot_fitted() == at && boot_bytes == at - (RT_BOOT_INFO_BYTES + 8u));
    assert(rt_boot_pool_max() && rt_boot_poweroff() && u32_at(boot_copy, big + 16u) == 15u);
    assert(rt_boot_info(fit, sizeof fit) == 2 && u32_at(fit, 0) == boot_bytes);
    /* ... and when the read tags alone overrun the copy: -3, no boot line, no module (rt_start halts on it). */
    put32(blk + big, 6u);                                                    /* the large tag is now a read one */
    rt_boot_init();
    assert(boot_status == -3 && rt_boot_fitted() == at && !rt_boot_pool_max());
    assert(rt_boot_info(fit, sizeof fit) == -3 && rt_boot_module(&bytes) == 0u && bytes == 0u);
    assert(munmap(blk, 2u * RT_BOOT_INFO_BYTES) == 0);
}

int main(void)
{
    uart_word();
    uint8_t *info = mmap((void *)0x10000000u, 16384u, PROT_READ | PROT_WRITE,
                         MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    assert(info != MAP_FAILED && (uintptr_t)info < SRC_HI - 16384u);
    size_t at = 8;
    const unsigned tags[] = {12u, 14u, 15u, 17u};
    for (unsigned i = 0; i < 4u; i++) {
        put32(info + at, tags[i]); put32(info + at + 4, 19u);
        memset(info + at + 8, (int)(i + 1u), 11u);
        at += 24u;
    }
    size_t fb = at;
    framebuffer_at = at;
    framebuffer(info + at); at += 40u;
    put32(info + at, 3u); put32(info + at + 4, 16u);
    /* Clang's statically linked sanitizer runtime can put host BSS above 8 MiB. */
    assert((((uintptr_t)__image_end + 0xFFFu) & ~(uintptr_t)0xFFFu) <= 0x1800000u);
    assert(0x1900000u <= RT_POOL_BASE);
    put32(info + at + 8, 0x1800000u); put32(info + at + 12, 0x1900000u); at += 16u;
    put32(info + at, 3u); put32(info + at + 4, 16u);
    put32(info + at + 8, 0x1A00000u); put32(info + at + 12, 0x1B00000u); at += 16u;
    size_t mmap_at = at;
    put32(info + at, 6u); put32(info + at + 4, 64u); put32(info + at + 8, 24u);
    put64(info + at + 16, 0u); put64(info + at + 24, SRC_HI); put32(info + at + 32, 1u);
    put64(info + at + 40, 0x1C00000u); put64(info + at + 48, 0x200000u); put32(info + at + 56, 2u);
    at += 64u;
    put32(info + at, 0u); put32(info + at + 4, 8u); at += 8u;
    put32(info, (uint32_t)at);
    mb_magic = MB2_MAGIC; mb_info = (uint32_t)(uintptr_t)info;
    rt_boot_init();
    assert(boot_status == 2 && boot_bytes == at && found());
    uint8_t copy[8192];
    assert(rt_boot_info(copy, sizeof copy) == 2 && memcmp(copy, info, at) == 0);
    uint64_t bytes = 0;
    assert(rt_boot_module(&bytes) == 0x1800000u && bytes == 0x100000u);
    assert(rt_boot_shadow_free(0x1400000u, 0x200000u));
    put32(boot_copy + at - 4u, 16u); assert(!rt_boot_shadow_free(0x1400000u, 4096u));
    put32(boot_copy + at - 4u, 8u);
    boot_bytes -= 8u; assert(!rt_boot_shadow_free(0x1400000u, 4096u)); boot_bytes += 8u;
    assert(!rt_boot_shadow_free(0x1800000u, 4096u)); /* first module */
    assert(!rt_boot_shadow_free(0x1A00000u, 4096u)); /* every other module */
    assert(!rt_boot_shadow_free(0x1C00000u, 4096u)); /* reserved veto, despite overlapping RAM */
    assert(!rt_boot_shadow_free((uintptr_t)info, 4096u)); /* original loader block */
    assert(!rt_boot_shadow_free(SRC_HI - 4096u, 8192u));
    assert(!rt_boot_shadow_free(UINT64_MAX - 4095u, 8192u));
    put32(boot_copy + mmap_at + 8u, 0u); assert(!rt_boot_shadow_free(0x1400000u, 4096u));
    put32(boot_copy + mmap_at + 8u, 24u);
    uint8_t *t = boot_copy + fb;
    put32(t + 4, 37u); assert(!found()); put32(t + 4, 38u);
    t[32] = 0u; t[36] = 16u; assert(found()); framebuffer(t);
    t[28] = 24u; assert(!found()); framebuffer(t);
    t[29] = 0u; assert(!found()); framebuffer(t);
    t[29] = 2u; assert(!found()); framebuffer(t);
    for (unsigned i = 33u; i <= 37u; i += 2u) {
        t[i] = 0u; assert(!found()); framebuffer(t);
    }
    put32(t + 16, 2559u); assert(!found()); framebuffer(t);
    put32(t + 20, 0u); assert(!found()); framebuffer(t);
    put32(t + 24, 0u); assert(!found()); framebuffer(t);
    put32(t + 20, 0x40000001u); assert(!found()); framebuffer(t);
    put32(t + 4, (uint32_t)at); assert(!found()); framebuffer(t);
    for (unsigned i = 0; i < 3u; i++) {
        const uint32_t sizes[] = {0u, 7u, 0xFFFFFFFFu};
        put32(boot_copy + 12, sizes[i]); assert(!found());
    }
    put32(boot_copy + 12, 19u); assert(found());
    boot_status = 1; assert(!found());
    g24_moves();
    ovmf_block();
    mb_info = (uint32_t)(uintptr_t)info;
    put32(info, RT_BOOT_INFO_BYTES + 8u); rt_boot_init();   /* past the copy: fitted from the source, the walk ends at */
    assert(boot_status == 2 && rt_boot_fitted() == RT_BOOT_INFO_BYTES + 8u && boot_bytes == at);   /* the end tag */
    assert(rt_boot_info(copy, sizeof copy) == 2 && memcmp(copy + 4, info + 4, at - 4u) == 0);
    /* MB1 references the original map and module array rather than carrying inline tags. */
    memset(info, 0, 16384u);
    put32(info, 64u | 8u | 4u);
    put32(info + 16u, 0x1600000u);
    put32(info + 20u, 2u); put32(info + 24u, (uint32_t)(uintptr_t)(info + 512u));
    put32(info + 44u, 48u); put32(info + 48u, (uint32_t)(uintptr_t)(info + 1024u));
    put32(info + 512u, 0x1800000u); put32(info + 516u, 0x1900000u);
    put32(info + 528u, 0x1A00000u); put32(info + 532u, 0x1B00000u);
    put32(info + 1024u, 20u); put64(info + 1028u, 0u); put64(info + 1036u, SRC_HI); put32(info + 1044u, 1u);
    put32(info + 1048u, 20u); put64(info + 1052u, 0x1C00000u); put64(info + 1060u, 4096u); put32(info + 1068u, 2u);
    memcpy(boot_copy, info, MB1_COPY); boot_status = 1; boot_bytes = MB1_COPY;
    assert(rt_boot_shadow_free(0x1400000u, 4096u));
    assert(!rt_boot_shadow_free(0x1600000u, 4096u)); /* command line */
    assert(!rt_boot_shadow_free(0x1800000u, 4096u) && !rt_boot_shadow_free(0x1A00000u, 4096u));
    assert(!rt_boot_shadow_free((uintptr_t)info + 512u, 4096u)); /* descriptors and map */
    assert(!rt_boot_shadow_free(0x1C00000u, 4096u));
    put32(info + 1024u, 0xFFFFFFFFu); assert(!rt_boot_shadow_free(0x1400000u, 4096u));
    /* NW-5: daphnis.net=... extraction from Multiboot 1 command line */
    char *cmd = (char *)(info + 2048u), netarg[64];
    put32(boot_copy + 16u, (uint32_t)(uintptr_t)cmd);
    memcpy(cmd, "daphnis.pool=max", sizeof "daphnis.pool=max");
    assert(rt_boot_net(netarg, sizeof netarg) == 0u && netarg[0] == '\0');
    memcpy(cmd, "daphnis.pool=max daphnis.net=dhcp daphnis.poweroff=1", sizeof "daphnis.pool=max daphnis.net=dhcp daphnis.poweroff=1");
    assert(rt_boot_net(netarg, sizeof netarg) == 4u && memcmp(netarg, "dhcp", 5u) == 0);
    memcpy(cmd, "xdaphnis.net=dhcp daphnis.net=10.0.2.15/24,10.0.2.2,10.0.2.3", sizeof "xdaphnis.net=dhcp daphnis.net=10.0.2.15/24,10.0.2.2,10.0.2.3");
    assert(rt_boot_net(netarg, sizeof netarg) == 30u && memcmp(netarg, "10.0.2.15/24,10.0.2.2,10.0.2.3", 31u) == 0);
    assert(rt_boot_net(netarg, 5u) == 0u && netarg[0] == '\0');
    memcpy(cmd, "daphnis.net=10.0.2.9/24 daphnis.net=dhcp", sizeof "daphnis.net=10.0.2.9/24 daphnis.net=dhcp");
    assert(rt_boot_net(netarg, sizeof netarg) == 4u && memcmp(netarg, "dhcp", 5u) == 0);
    memcpy(cmd, "daphnis.net=", sizeof "daphnis.net=");
    assert(rt_boot_net(netarg, sizeof netarg) == 0u && netarg[0] == '\0');
    assert(munmap(info, 16384u) == 0);
    puts("boot tags: PASS (GOP offsets, bounds, high address, retained ACPI/EFI, module, a module moved into the window, copy cap, RG-1 OVMF's 8,304-byte block whole and fitted, read tags kept or -3, a block past the copy fitted, HW-14 daphnis.uart=0)");
    return 0;
}
