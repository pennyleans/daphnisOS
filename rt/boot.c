/* rt/boot.c: the loader's information block, copied once (docs/memory.md, Multiboot 2 information).
 *
 * The block is the loader's and sits where the loader chose: QEMU's -kernel (Multiboot 1) at 0x9500,
 * GRUB (Multiboot 2) at 0x100068, in the image's own header page. Rather than a read window per loader,
 * rt_start calls rt_boot_init before main, which copies the block into one buffer here; cint reads the
 * copy through one extern, boot_info (rt/host.c, src/bootinfo.ci).
 *
 *   Multiboot 1: 128 bytes from mb_info, through rt_phys_copy (the window rules of rt/phys.c); the map
 *                it points at stays where it is, read through phys_read8 as before.
 *   Multiboot 2: total_size bytes from mb_info. The source must lie in [0x1000, 1 GiB): the null page is
 *                not mapped, and boot.S identity maps the first 1 GiB only. The copy is 64 KiB, in this image's
 *                BSS: GRUB's block under OVMF is 8,304 bytes at 512 MiB (an EFI memory map tag of about 6 KiB),
 *                past the 8 KiB this copy had, which dropped the whole block, boot line, module, framebuffer and
 *                map with it (RG-1, 2026-11-12). A larger block is fitted into the copy from the source
 *                (mb2_fit), and rt_start says so; when the tags the kernel reads do not fit, the status is -3
 *                and rt_start halts. */
#include "rt.h"

#ifndef RT_BOOT_INFO_BYTES
#define RT_BOOT_INFO_BYTES 65536u
#endif
#define MB1_MAGIC 0x2BADB002u
#define MB2_MAGIC 0x36D76289u
#define MB1_COPY 128u
#define SRC_LO 0x1000u
#define SRC_HI 0x40000000u

extern uint32_t mb_magic, mb_info; /* boot.S */
extern uint8_t __image_end[];      /* linker.ld: the end of the image's high window */

static uint8_t boot_copy[RT_BOOT_INFO_BYTES] __attribute__((aligned(8)));
static uint32_t boot_bytes;
static int64_t boot_status; /* 1 or 2 the protocol, -1 no loader block, -3 the tags the kernel reads do not fit */
static uint32_t boot_source; /* the loader's block as it lies at mb_info, whole: total_size, or MB1_COPY */
static uint32_t boot_fitted; /* total_size of a Multiboot 2 block larger than boot_copy, fitted or not; else 0 */
static bool boot_done;      /* rt_boot_init has finished: boot_status is final */
static uint64_t module_base, module_bytes; /* the first loader module: the user image (U1-5) */

static bool source_ok(uint64_t base, uint64_t bytes)
{
    return base >= SRC_LO && base <= SRC_HI && bytes <= SRC_HI - base;
}

static uint32_t u32_at(const void *p, size_t off)
{
    uint32_t v;
    memcpy(&v, (const uint8_t *)p + off, sizeof v);
    return v;
}

static void put32_le(uint8_t *p, uint32_t v) { memcpy(p, &v, sizeof v); }

/* The Multiboot 2 tags the kernel reads: the command line (1), the modules (3), the memory map (6), the framebuffer
 * (8) and the RSDP (14, 15; src/acpi.ci). Every other tag (the EFI memory map, 17, the large one) may be left out. */
static bool tag_read(uint32_t type)
{
    return type == 1u || type == 3u || type == 6u || type == 8u || type == 14u || type == 15u;
}

/* The Multiboot 2 block src, total bytes, fitted into dst, room bytes (room >= 16): whole tags in their order, then
 * the end tag, and total_size the fitted size, which it returns. A tag is never cut. Every tag the kernel reads is
 * kept; any other is kept while it fits beside the end tag and every read tag still to come, so a large tag ahead of
 * the ACPI tags cannot push them out. 0, and dst untouched, when the read tags alone do not fit. */
static size_t mb2_fit(const uint8_t *src, size_t total, uint8_t *dst, size_t room)
{
    size_t at = 8u, out = 8u, rest = 8u;   /* rest: the end tag and the read tags not yet placed */
    while (at + 8u <= total) {
        uint32_t type = u32_at(src, at), size = u32_at(src, at + 4u);
        size_t step = ((size_t)size + 7u) & ~(size_t)7u;
        if (type == 0u || size < 8u || size > total - at) break;
        if (tag_read(type)) rest += step;
        at += step;
    }
    if (rest > room - out) return 0u;
    memcpy(dst, src, 8u);
    for (at = 8u; at + 8u <= total;) {
        uint32_t type = u32_at(src, at), size = u32_at(src, at + 4u);
        size_t step = ((size_t)size + 7u) & ~(size_t)7u;
        if (type == 0u || size < 8u || size > total - at) break;
        if (tag_read(type)) rest -= step;
        if (tag_read(type) || step <= room - out - rest) {
            memcpy(dst + out, src + at, size);
            memset(dst + out + size, 0, step - size);
            out += step;
        }
        at += step;
    }
    memset(dst + out, 0, 8u);
    dst[out + 4u] = 8u;
    out += 8u;
    put32_le(dst, (uint32_t)out);
    return out;
}

/* True when the loader's command line holds word w (a word: bounded by the line's ends or spaces). */
static bool cmdline_has(const char *w, size_t k)
{
    char line[256];
    size_t n = rt_boot_cmdline(line, sizeof line), i;
    for (i = 0; i + k <= n; i++)
        if ((i == 0u || line[i - 1u] == ' ') && (i + k == n || line[i + k] == ' ') && memcmp(line + i, w, k) == 0) return true;
    return false;
}

bool rt_boot_pool_max(void) { return cmdline_has("daphnis.pool=max", 16u); }
bool rt_boot_poweroff(void) { return cmdline_has("daphnis.poweroff=1", 18u); }
bool rt_boot_uart_off(void) { return cmdline_has("daphnis.uart=0", 14u); }   /* HW-14 (rt/console.c) */

/* True once rt_boot_init has finished: the command line reads as the loader gave it, or as none. */
bool rt_boot_read(void) { return boot_done; }

/* NW-5: the value after `daphnis.net=` in the loader's command line (`dhcp` or `ADDR/PREFIX,GATEWAY,DNS`),
 * at most n - 1 bytes and a NUL; the count, 0 when absent, empty, or too long for dst. When repeated,
 * the last occurrence wins. */
size_t rt_boot_net(char *dst, size_t n)
{
    char line[256];
    size_t len, i, val = 0u, vlen = 0u;
    bool seen = false;
    if (n == 0u) return 0u;
    dst[0] = '\0';
    len = rt_boot_cmdline(line, sizeof line);
    for (i = 0u; i + 12u <= len; i++) {
        if ((i == 0u || line[i - 1u] == ' ') && memcmp(line + i, "daphnis.net=", 12u) == 0) {
            size_t s = i + 12u, e = s;
            while (e < len && line[e] != ' ') e++;
            seen = true;
            val = s;
            vlen = e - s;
        }
    }
    if (!seen || vlen == 0u || vlen >= n) return 0u;
    memcpy(dst, line + val, vlen);
    dst[vlen] = '\0';
    return vlen;
}

/* The module is taken only where nothing else is: above the image (its high window ends at
 * __image_end) and below the pool at 32 MiB (RT_POOL_BASE). QEMU's -initrd and GRUB's module2 both put it right
 * after the image. Under daphnis.pool=max (M-3, src/pool.ci) it may run on to the run blob at 96 MiB
 * (RT_BLOB_BASE): pool.init starts the pool at its end (rt_boot_pool_floor), so no frame under it is handed out.
 * AU-5: the play image (tools/play.sh) is 38 MB with the core set and the episode, past the 28 MiB below the pool.
 * g24 (unit 4b): GRUB under UEFI does not put a large module right after the image. OVMF holds 8 to 9 MiB, so the
 * 12 MB user image lands where GRUB's own memory was, 23.5 to 35.3 MiB, across the pool's base. A module outside
 * the window that fits in it is moved into it, once, before anything else runs (module_room). */
static uint64_t module_room(uint64_t lo, uint64_t hi, uint64_t floor, uint64_t ceiling);
static void module_take(uint64_t lo, uint64_t hi)
{
    uint64_t floor = ((uint64_t)(uintptr_t)__image_end + 0xFFFu) & ~(uint64_t)0xFFFu;
    uint64_t ceiling = cmdline_has("daphnis.pool=max", 16u) ? RT_BLOB_BASE : RT_POOL_BASE;
    if (module_bytes != 0u || hi <= lo) return;
    if (lo < floor || hi > ceiling) {
        uint64_t to;
        if (hi - lo > ceiling - floor || !source_ok(lo, hi - lo) || (to = module_room(lo, hi, floor, ceiling)) == 0u) return;
        memmove((void *)(uintptr_t)to, (const void *)(uintptr_t)lo, (size_t)(hi - lo));
        hi = to + (hi - lo);
        lo = to;
    }
    module_base = lo;
    module_bytes = hi - lo;
}

/* Multiboot 1: flags bit 3, mods_count and mods_addr; an entry is mod_start, mod_end, string,
 * reserved. Multiboot 2: a tag of type 3 is type, size, mod_start, mod_end, string. */
static void module_find(void)
{
    if (boot_status == 1) {
        uint32_t flags = u32_at(boot_copy, 0), count = u32_at(boot_copy, 20), addr = u32_at(boot_copy, 24);
        if ((flags & 8u) != 0u && count >= 1u && source_ok(addr, 16u))
            module_take(u32_at((const void *)(uintptr_t)addr, 0), u32_at((const void *)(uintptr_t)addr, 4));
    } else if (boot_status == 2) {
        size_t at = 8;
        while (at + 8 <= boot_bytes) {
            uint32_t type = u32_at(boot_copy, at), size = u32_at(boot_copy, at + 4);
            if (type == 0u || size < 8u || at + size > boot_bytes) break;
            if (type == 3u && size >= 16u) module_take(u32_at(boot_copy, at + 8), u32_at(boot_copy, at + 12));
            at = (at + size + 7u) & ~(size_t)7u;
        }
    }
}

/* The loader's framebuffer (F-1): a Multiboot 2 tag of type 8 is type, size, addr (u64), pitch, width,
 * height, bpp (u8), type (u8), reserved, then for type 1 the position and size of each color field. Only
 * 32-bit direct color with disjoint, nonempty RGB fields is taken; Multiboot 1 brings none.
 * HW-1: reserved is u16, so the color fields start at byte 32, not byte 31. The complete
 * loader block, including ACPI (14, 15) and EFI (12, 17) tags, is retained in boot_copy. */
bool rt_boot_framebuffer(uint64_t *addr, uint32_t *pitch, uint32_t *w, uint32_t *h, struct rt_fb_format *format)
{
    size_t at = 8;
    if (boot_status != 2) return false;
    while (at + 8 <= boot_bytes) {
        uint32_t type = u32_at(boot_copy, at), size = u32_at(boot_copy, at + 4);
        if (type == 0u || size < 8u || at + size > boot_bytes) break;
        if (type == 8u && size >= 38u) {
            const uint8_t *t = boot_copy + at;
            uint64_t a;
            memcpy(&a, t + 8, sizeof a);
            if (t[28] == 32u && t[29] == 1u) {
                for (unsigned i = 0u; i < 3u; i++) {
                    format->pos[i] = t[32u + 2u * i];
                    format->bits[i] = t[33u + 2u * i];
                }
                if (!rt_fb_format_valid(format)) return false;
                *addr = a;
                *pitch = u32_at(t, 16);
                *w = u32_at(t, 20);
                *h = u32_at(t, 24);
                return *w != 0u && *h != 0u && (uint64_t)*pitch >= 4u * (uint64_t)*w;
            }
            return false;
        }
        at = (at + size + 7u) & ~(size_t)7u;
    }
    return false;
}

static uint64_t u64_at(const void *p, size_t off)
{
    uint64_t v;
    memcpy(&v, (const uint8_t *)p + off, sizeof v);
    return v;
}

static bool overlaps(uint64_t lo, uint64_t hi, uint64_t base, uint64_t bytes)
{
    return bytes > UINT64_MAX - base || (lo < base + bytes && base < hi);
}

/* HW-1 display backing: true only for a completely usable range, outside kernel and
 * every loader module/metadata range. Reserved map entries veto overlapping usable ones.
 * Allocation policy (pool and blob exclusions) belongs to fb.c, not this map predicate. */
bool rt_boot_shadow_free(uint64_t base, uint64_t bytes)
{
    const uint8_t *map = NULL;
    uint32_t length = 0u, stride = 0u;
    bool mb1 = boot_status == 1, covered = false, terminated = false;
    uint64_t end;
    if (bytes == 0u || !source_ok(base, bytes) || base < (uint64_t)(uintptr_t)__image_end) return false;
    end = base + bytes;
    if (overlaps(base, end, mb_info, boot_source)) return false;
    if (module_bytes != 0u && overlaps(base, end, module_base, module_bytes)) return false;   /* where module_take put it */
    if (mb1) {
        uint32_t flags = u32_at(boot_copy, 0), addr = u32_at(boot_copy, 48);
        length = u32_at(boot_copy, 44);
        if ((flags & 64u) == 0u || length < 24u || !source_ok(addr, length) || overlaps(base, end, addr, length)) return false;
        map = (const uint8_t *)(uintptr_t)addr;
        if ((flags & 4u) != 0u && overlaps(base, end, u32_at(boot_copy, 16), 4096u)) return false;
        if ((flags & 8u) != 0u) {
            uint32_t count = u32_at(boot_copy, 20), mods = u32_at(boot_copy, 24);
            uint64_t n = (uint64_t)count * 16u;
            if (count > 1024u || (count != 0u && (!source_ok(mods, n) || overlaps(base, end, mods, n)))) return false;
            for (uint32_t i = 0u; i < count; i++) {
                const uint8_t *m = (const uint8_t *)(uintptr_t)mods + 16u * (uint64_t)i;
                uint32_t lo = u32_at(m, 0), hi = u32_at(m, 4), name = u32_at(m, 8);
                if (hi < lo || overlaps(base, end, lo, (uint64_t)hi - lo) ||
                    (name != 0u && overlaps(base, end, name, 4096u))) return false;
            }
        }
    } else if (boot_status == 2) {
        size_t at = 8;
        while (at + 8u <= boot_bytes) {
            uint32_t type = u32_at(boot_copy, at), size = u32_at(boot_copy, at + 4u);
            if (size < 8u || size > boot_bytes - at) return false;
            if (type == 0u) {
                if (size != 8u || at + 8u != boot_bytes) return false;
                terminated = true;
                break;
            }
            if (type == 3u) {
                if (size < 16u) return false;
                uint32_t lo = u32_at(boot_copy, at + 8u), hi = u32_at(boot_copy, at + 12u);
                if (hi < lo || overlaps(base, end, lo, (uint64_t)hi - lo)) return false;
            }
            if (type == 6u) {
                if (map != NULL || size < 16u) return false;
                stride = u32_at(boot_copy, at + 8u);
                if (stride < 24u || (size - 16u) % stride != 0u) return false;
                map = boot_copy + at + 16u;
                length = size - 16u;
            }
            at = (at + size + 7u) & ~(size_t)7u;
        }
        if (!terminated) return false;
    }
    if (map == NULL) return false;
    for (uint32_t at = 0u; at < length;) {
        uint32_t step = stride, off = 0u;
        if (mb1) {
            if (length - at < 4u) return false;
            step = u32_at(map, at);
            if (step < 20u || step > length - at - 4u) return false;
            step += 4u;
            off = 4u;
        }
        if (step == 0u || step > length - at) return false;
        uint64_t lo = u64_at(map, at + off), span = u64_at(map, at + off + 8u);
        uint32_t kind = u32_at(map, at + off + 16u);
        if (span > UINT64_MAX - lo) return false;
        if (kind == 1u) {
            if (lo <= base && end <= lo + span) covered = true;
        } else if (overlaps(base, end, lo, span)) {
            return false;
        }
        at += step;
    }
    return covered;
}

/* g24: the lowest page from floor that starts a run of hi - lo bytes ending by ceiling, every page of it usable RAM
 * by the loader's map outside the image, the block and the loader's other ranges (rt_boot_shadow_free), or a page of
 * the module's own source that holds no part of the block; 0 with none. The loader is done once the kernel runs,
 * so its memory is free; a run over the source is fine, module_take moves the bytes with memmove. */
static uint64_t module_room(uint64_t lo, uint64_t hi, uint64_t floor, uint64_t ceiling)
{
    uint64_t start = floor;
    for (uint64_t pa = floor; pa < ceiling; pa += 0x1000u) {
        bool own = overlaps(pa, pa + 0x1000u, lo, hi - lo);
        if (own ? overlaps(pa, pa + 0x1000u, mb_info, boot_source) : !rt_boot_shadow_free(pa, 0x1000u)) {
            start = pa + 0x1000u;
        } else if (pa + 0x1000u - start >= hi - lo) {
            return start;
        }
    }
    return 0u;
}

/* HW-2: the loader's memory map, Multiboot 1 or 2: its bytes, the stride of an entry (0 for Multiboot 1, whose
 * entries carry their own size) and its length; NULL without one. */
static const uint8_t *boot_map(uint32_t *stride, uint32_t *length)
{
    if (boot_status == 1) {
        uint32_t flags = u32_at(boot_copy, 0), addr = u32_at(boot_copy, 48);
        *length = u32_at(boot_copy, 44);
        *stride = 0u;
        if ((flags & 64u) == 0u || *length < 24u || !source_ok(addr, *length)) return NULL;
        return (const uint8_t *)(uintptr_t)addr;
    }
    if (boot_status == 2) {
        size_t at = 8;
        while (at + 8u <= boot_bytes) {
            uint32_t type = u32_at(boot_copy, at), size = u32_at(boot_copy, at + 4u);
            if (type == 0u || size < 8u || size > boot_bytes - at) return NULL;
            if (type == 6u) {
                if (size < 16u) return NULL;
                *stride = u32_at(boot_copy, at + 8u);
                *length = size - 16u;
                if (*stride < 24u || *length % *stride != 0u) return NULL;
                return boot_copy + at + 16u;
            }
            at = (at + size + 7u) & ~(size_t)7u;
        }
    }
    return NULL;
}

/* HW-2: true when [base, end) lies inside one entry of the loader's map of kind 2 (reserved: SeaBIOS keeps its ACPI
 * tables there), 3 (ACPI reclaimable) or 4 (ACPI NVS), below 512 GiB. rt/phys.c reads such a range for src/acpi.ci,
 * never writes it. MMIO is not in the map, so it is never read. */
bool rt_boot_firmware_range(uint64_t base, uint64_t end)
{
    uint32_t stride = 0u, length = 0u;
    const uint8_t *map = boot_map(&stride, &length);
    if (map == NULL || end <= base) return false;
    if (end > 0x8000000000u) return false;
    for (uint32_t at = 0u; at < length;) {
        uint32_t step = stride, off = 0u;
        if (stride == 0u) {
            if (length - at < 4u) return false;
            step = u32_at(map, at);
            if (step < 20u || step > length - at - 4u) return false;
            step += 4u;
            off = 4u;
        }
        uint64_t lo = u64_at(map, at + off), span = u64_at(map, at + off + 8u);
        uint32_t kind = u32_at(map, at + off + 16u);
        if (span <= UINT64_MAX - lo && (kind == 2u || kind == 3u || kind == 4u) && base >= lo && end <= lo + span)
            return true;
        at += step;
    }
    return false;
}

uint64_t rt_boot_module(uint64_t *bytes)
{
    *bytes = module_bytes;
    return module_base;
}

/* The pool's first byte: 32 MiB, or the page after the module when it runs past 32 MiB (daphnis.pool=max only). */
uint64_t rt_boot_pool_floor(void)
{
    uint64_t end = (module_base + module_bytes + 0xFFFu) & ~(uint64_t)0xFFFu;
    return module_bytes != 0u && end > RT_POOL_BASE ? end : RT_POOL_BASE;
}

void rt_boot_init(void)
{
    uint64_t base = mb_info;
    boot_status = -1;
    boot_bytes = boot_source = boot_fitted = 0u;
    module_base = module_bytes = 0u;
    if (mb_magic == MB1_MAGIC) {
        if (rt_phys_copy(false, base, boot_copy, MB1_COPY, 1, 1u) == CINT_OK) {
            boot_bytes = boot_source = MB1_COPY;
            boot_status = 1;
        }
    } else if (mb_magic == MB2_MAGIC && base % 8u == 0u && source_ok(base, 8u)) {
        uint32_t total = *(const volatile uint32_t *)(uintptr_t)base;
        if (total >= 8u && source_ok(base, total)) {
            boot_source = total;
            if (total <= RT_BOOT_INFO_BYTES) {
                memcpy(boot_copy, (const void *)(uintptr_t)base, total);
                boot_bytes = total;
            } else {
                boot_fitted = total;
                boot_bytes = (uint32_t)mb2_fit((const uint8_t *)(uintptr_t)base, total, boot_copy, RT_BOOT_INFO_BYTES);
            }
            boot_status = boot_bytes != 0u ? 2 : -3;
        }
    }
    module_find();
    boot_done = true;
}

/* The loader's command line, at most n - 1 bytes and a NUL; the count, 0 with none. Multiboot 1: flags bit 2,
 * the string's address at offset 16 (QEMU's -append); Multiboot 2: a tag of type 1, the string in the tag
 * (GRUB's multiboot2 line after the kernel's path). HX-0: daphnis.mode=WxH is read from it (rt/fb.c). */
size_t rt_boot_cmdline(char *dst, size_t n)
{
    const char *src = NULL;
    size_t limit = 0, k = 0;
    if (n == 0u) return 0u;
    if (boot_status == 1) {
        uint32_t flags = u32_at(boot_copy, 0), addr = u32_at(boot_copy, 16);
        if ((flags & 4u) != 0u && source_ok(addr, n)) {
            src = (const char *)(uintptr_t)addr;
            limit = n - 1u;
        }
    } else if (boot_status == 2) {
        size_t at = 8;
        while (at + 8 <= boot_bytes) {
            uint32_t type = u32_at(boot_copy, at), size = u32_at(boot_copy, at + 4);
            if (type == 0u || size < 8u || at + size > boot_bytes) break;
            if (type == 1u) {
                src = (const char *)boot_copy + at + 8;
                limit = size - 8u < n - 1u ? size - 8u : n - 1u;
                break;
            }
            at = (at + size + 7u) & ~(size_t)7u;
        }
    }
    while (src != NULL && k < limit && src[k] != '\0') {
        dst[k] = src[k];
        k++;
    }
    dst[k] = '\0';
    return k;
}

/* The copy into dst, n bytes, and the status. A Multiboot 2 copy larger than dst is fitted (mb2_fit): src/pool.ci
 * and src/acpi.ci read 8 KiB, their state pool's room. -3, dst untouched, when the tags the kernel reads do not fit
 * dst; rt/host.c's boot_info row then halts the kernel, which never runs half configured. */
int64_t rt_boot_info(uint8_t *dst, int64_t n)
{
    size_t room = n > 0 ? (size_t)n : 0u;
    if (boot_status <= 0) return boot_status;
    if (boot_status == 1 || room >= boot_bytes) {
        memcpy(dst, boot_copy, room < boot_bytes ? room : boot_bytes);
        return boot_status;
    }
    return room >= 16u && mb2_fit(boot_copy, boot_bytes, dst, room) != 0u ? boot_status : -3;
}

int64_t rt_boot_status(void) { return boot_status; }

/* The total_size of a Multiboot 2 block larger than the copy (fitted, or -3), for rt_start's line; else 0. */
uint32_t rt_boot_fitted(void) { return boot_fitted; }
