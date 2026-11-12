/* rt/phys.c: the view shim. cint has no pointers, so cint code reaches physical memory only
 * through phys_read8/64 and phys_write8/64: copy a physical range into an `out` view or from
 * an `in` view (SPEC-03 A-15: a view is valid for the call only). The ranges allowed are fixed
 * here and checked with overflow-safe arithmetic; anything else is a CINT_REFUSED status,
 * which cint_rt_host_call turns into a canonical host.error.<name> fault record.
 *
 *   read only   [0x1000, 1 MiB)  the Multiboot info and memory map (boot.S saves its address)
 *               the first page is not allowed: it is not mapped (a null access is a #PF)
 *   read/write  [32 MiB, 96 MiB) the frame pool of src/frames.ci (docs/memory.md)
 *   read        [96 MiB, 97 MiB) the run descriptor and blob a loader put there (K5)
 *   read        the six boot page-table pages (pml4, pdpt, pd, pt, pt_high, pt_high2 of boot.S, contiguous)
 *   read/write  the boot PDPT page only: all src/paging.ci edits there is slot 1 (a window that
 *               could write pml4, pd or pt could unmap the kernel's own mappings)
 *   read        the canonical shadow's narrow virtual-backed window (HW-1): surface digest;
 *               VRAM is not exposed through this window
 *   read        HW-2: a range inside one reserved, ACPI or NVS entry of the loader's map
 *               (rt_boot_firmware_range): the ACPI tables src/acpi.ci reads, through a 2 MiB alias at
 *               510 GiB where boot.S does not map them */
#include "rt.h"

#define LOW_BASE 0x1000u
#define LOW_END 0x100000u
#define PAGE 4096u

extern char pml4[], pt[];
extern uint64_t pd[];
extern char __text_start[], __text_end[], __rodata_end[], __high_text_end[], __high_rodata_end[];
extern uint64_t pt_high[], pt_high2[]; /* boot.S: 4 KiB pages over 2 to 4 and 4 to 6 MiB, the image's high window (linker.ld) */

/* A page of ones that can be called: a ret. It is in .data, so no-execute once rt_wx_init has run, and
 * rt_wx_probe(1) jumps to it to show the hardware refuses (a fetch fault, error code 0x11). */
static uint8_t wx_page[4096] __attribute__((aligned(4096), section(".data"))) = {0xC3};

/* Gives the first 2 MiB the rights of their sections (K5, docs/memory.md): boot.S maps them all writable
 * and executable. Code is present and read only (CR0.WP binds ring 0), everything above it is no-execute,
 * data, bss, the tables and the stacks are writable, the Multiboot header and low memory are read only. A
 * page that is not present (the null page, a guard page) stays so. The 2 MiB entries of the rest of RAM
 * become no-execute. */
void rt_wx_init(void)
{
    uint64_t *e = (uint64_t *)(void *)pt;
    const uint64_t nx = 0x8000000000000000u;
    uint64_t ts = (uint64_t)(uintptr_t)__text_start >> 12, te = (uint64_t)(uintptr_t)__text_end >> 12;
    uint64_t re = (uint64_t)(uintptr_t)__rodata_end >> 12;
    unsigned i;
    for (i = 1u; i < 512u; i++) {
        uint64_t f;
        if ((e[i] & 1u) == 0u) continue;
        if (i >= ts && i < te) f = 1u;
        else if (i >= te && i < re) f = 1u | nx;
        else if (i >= re) f = 3u | nx;
        else f = 1u | nx;
        e[i] = (e[i] & 0x000FFFFFFFFFF000u) | f;
    }
    for (i = 0u; i < 1024u; i++) {   /* the high window, 2 to 6 MiB: the emitted code read and execute, its read-only data read, the rest writable */
        uint64_t a = 0x200000u + ((uint64_t)i << 12), f;
        uint64_t *leaf = i < 512u ? &pt_high[i] : &pt_high2[i - 512u];
        if (a < (uint64_t)(uintptr_t)__high_text_end) f = 1u;
        else if (a < (uint64_t)(uintptr_t)__high_rodata_end) f = 1u | nx;
        else f = 3u | nx;
        *leaf = (*leaf & 0x000FFFFFFFFFF000u) | f;
    }
    for (i = 3u; i < 512u; i++) pd[i] |= nx;   /* pd[1] and pd[2] point at pt_high and pt_high2, whose leaves say what executes */
    cr3_write(cr3_read());
}

/* The evidence that the rights are enforced, not only set: kind 0 stores a word of the code onto itself (a
 * write the hardware must refuse: error code 3), kind 1 calls a page of data and kind 2 the first page of the read-only data (a fetch the
 * hardware must refuse: error code 0x11). Returns the error code of the trap, or 0 if nothing trapped. Needs the IDT and TSS. */
int64_t rt_wx_probe(int64_t kind)
{
    if (kind == 0) {
        uint64_t a = (uint64_t)(uintptr_t)__text_start;
        (void)rt_probe(trap_probe_store, a, *(const volatile uint64_t *)(uintptr_t)a);
    } else if (kind == 1) {
        (void)rt_probe(trap_probe_exec, (uint64_t)(uintptr_t)wx_page, 0u);
    } else if (kind == 2) {
        (void)rt_probe(trap_probe_exec, (uint64_t)(uintptr_t)__text_end, 0u); /* the first page of the read-only data */
    } else {
        return -1;
    }
    {
        int64_t e = rt_trap_record_len() != 0 ? (int64_t)rt_trap_last_error() : 0;
        rt_trap_reset(); /* nothing of the probe is left for a task to read */
        return e;
    }
}

/* Makes `pages` pages at addr not present in the boot page table: a guard page (K4.5). The
 * page table is boot.S's `pt` (4 KiB pages over the first 2 MiB), which cint reads and never
 * writes (above), so a guard is made here, by rt/, once, before the memory is used. */
void rt_guard_pages(const void *addr, unsigned pages)
{
    uint64_t *e = (uint64_t *)(void *)pt;
    uint64_t first = (uint64_t)(uintptr_t)addr >> 12;
    unsigned i;
    if (((uintptr_t)addr & (PAGE - 1u)) != 0u || first + pages > 512u) rt_panic("guard page outside the boot page table");
    for (i = 0u; i < pages; i++) {
        e[first + i] = 0u;
        vm_invlpg(((first + i) << 12));
    }
}

static bool within(uint64_t base, uint64_t end, uint64_t lo, uint64_t hi)
{
    return base >= lo && end <= hi;
}

/* HW-2: firmware tables outside boot.S's identity map (1 to 2 GiB, which src/paging.ci owns, or above 8 GiB) are
 * read through one 2 MiB alias at 510 GiB: a directory of its own in PDPT slot 510, read only and no-execute. */
#define FW_SLOT 510u
#define FW_VA ((uint64_t)FW_SLOT << 30)
extern uint64_t pdpt[];
static uint64_t pd_fw[512] __attribute__((aligned(4096)));

static bool identity(uint64_t base, uint64_t end)
{
    return end <= 0x40000000u || (base >= 0x80000000u && end <= 0x200000000u);
}

static cint_status fw_copy(void *buf, uint64_t base, uint64_t bytes)
{
    uint8_t *out = buf;
    if ((pdpt[FW_SLOT] & 1u) == 0u) {
        pdpt[FW_SLOT] = (uint64_t)(uintptr_t)pd_fw | 3u;
    } else if ((pdpt[FW_SLOT] & 0x000FFFFFFFFFF000u) != (uint64_t)(uintptr_t)pd_fw) {
        return CINT_REFUSED;   /* the slot is someone else's (rt/mmio.c's above 8 GiB) */
    }
    while (bytes != 0u) {
        uint64_t page = base & ~(uint64_t)0x1FFFFFu, off = base - page, n = 0x200000u - off;
        if (n > bytes) n = bytes;
        pd_fw[0] = page | 0x81u | 0x8000000000000000u;   /* present, read only, 2 MiB, no-execute */
        vm_invlpg(FW_VA);
        memcpy(out, (const void *)(uintptr_t)(FW_VA + off), (size_t)n);
        out += n;
        base += n;
        bytes -= n;
    }
    pd_fw[0] = 0u;
    vm_invlpg(FW_VA);
    return CINT_OK;
}

static uint64_t fb_lo, fb_hi; /* [fb_lo, fb_hi): the framebuffer's bytes, none until rt_fb_init mapped them */
uint64_t rt_pool_end = RT_POOL_END;

/* M-3: the pool's end, set once by src/pool.ci from the memory map: 0, or -1 when it is set already, below the
 * gates' pool or past what boot.S maps. */
int64_t rt_phys_pool_window(uint64_t end)
{
    if (rt_pool_end != RT_POOL_END || end < RT_POOL_END || end > RT_POOL_CAP || end % 4096u != 0u) return -1;
    rt_pool_end = end;
    return 0;
}

void rt_phys_window_fb(uint64_t lo, uint64_t hi)
{
    fb_lo = lo;
    fb_hi = hi;
}

cint_status rt_phys_copy(bool to_phys, uint64_t base, void *buf, int64_t extent, int64_t byte_stride, unsigned width)
{
    uint64_t bytes, end, tl = (uint64_t)(uintptr_t)pml4, th = (uint64_t)(uintptr_t)pt_high2 + PAGE;
    uint64_t pdpt_lo = tl + PAGE, pdpt_hi = tl + 2u * PAGE;
    bool rw;
    if (extent <= 0 || byte_stride != (int64_t)width || (uint64_t)extent > UINT64_MAX / width) return CINT_REFUSED;
    bytes = (uint64_t)extent * width;
    if (base > UINT64_MAX - bytes || base % width != 0u) return CINT_REFUSED;
    end = base + bytes;
    if (!to_phys && within(base, end, RT_BLOB_BASE, RT_BLOB_END)) goto copy; /* the run descriptor and blob (K5) */
    if (!to_phys && fb_hi != 0u && within(base, end, fb_lo, fb_hi)) goto copy; /* the surface (F-1) */
    if (!to_phys && rt_boot_firmware_range(base, end)) {   /* HW-2: the firmware's tables, read only */
        if (identity(base, end)) goto copy;
        return fw_copy(buf, base, bytes);
    }
    rw = within(base, end, RT_POOL_BASE, rt_pool_end) || within(base, end, pdpt_lo, pdpt_hi);
    if (!rw && (to_phys || !(within(base, end, LOW_BASE, LOW_END) || within(base, end, tl, th)))) return CINT_REFUSED;
copy:
    if (to_phys)
        memcpy((void *)(uintptr_t)base, buf, (size_t)bytes);
    else
        memcpy(buf, (const void *)(uintptr_t)base, (size_t)bytes);
    return CINT_OK;
}
