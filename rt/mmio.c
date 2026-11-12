/* rt/mmio.c: memory-mapped device registers (AU-1, docs/specs/2026-11-06-au-audio.md section 8; the piece HW-4,
 * HW-5 and HW-7 of docs/specs/2026-11-06-hw-hardware.md take as built). cint has no pointers, so a register is
 * reached through the rows mmio_in8/16/32 and mmio_out8/16/32, and only inside a window rt_mmio_map opened.
 *
 * A window is a device's BAR. Its 2 MiB pages get caching off (PCD, PWT) and no-execute, the mechanism of rt/fb.c
 * made general: in 2 to 8 GiB, where boot.S already maps every 2 MiB page, the entries of that gigabyte's directory
 * change in place; above 8 GiB (a 64-bit BAR on a board) a free slot of the boot PDPT gets a directory of its own,
 * MMIO_DIRS of them. The boot gigabyte and 1 to 2 GiB (src/paging.ci's) are refused. A window crossing a gigabyte
 * is refused. Every other address is a CINT_REFUSED status, as rt/phys.c's are.
 * HW-4: a BAR at 512 GiB or above (OVMF puts 64-bit BARs there, past the boot PML4 entry's reach, and PML4 slot 1 is
 * rt/fb.c's shadow) is not mapped where it is: it gets a gigabyte of its own at 1 TiB and up (PML4 slot 2, ALIAS_DIRS
 * of them), and the rows reach it there. cint still names the register by its bus address. */
#include "rt.h"

#define PD_DEV (0x9Bu | 0x8000000000000000u) /* present, writable, PWT, PCD, 2 MiB, no-execute */
#define MMIO_WINDOWS 8u
#define MMIO_DIRS 4u

extern uint64_t pdpt[];

static uint64_t pd_mmio[MMIO_DIRS][512] __attribute__((aligned(4096)));
static unsigned dirs_used;
static uint64_t win_lo[MMIO_WINDOWS], win_hi[MMIO_WINDOWS]; /* [lo, hi) */
static uint64_t win_va[MMIO_WINDOWS];                         /* where [lo, hi) is reached: lo itself, or its alias */
static unsigned windows;
#define ALIAS_DIRS 2u
#define ALIAS_VA 0x10000000000u                               /* 1 TiB: PML4 slot 2 */
extern uint64_t pml4[];
static uint64_t pdpt_alias[512] __attribute__((aligned(4096)));
static uint64_t pd_alias[ALIAS_DIRS][512] __attribute__((aligned(4096)));
static unsigned alias_used;

/* HW-4: [base, last] past 512 GiB, inside one gigabyte, mapped at the next alias gigabyte; its virtual base, or 0. */
static uint64_t alias(uint64_t base, uint64_t last)
{
    uint64_t gig = base >> 30, i;
    if (alias_used == ALIAS_DIRS || windows == MMIO_WINDOWS) return 0u;
    if (pml4[2] == 0u) {
        pml4[2] = (uint64_t)(uintptr_t)pdpt_alias | 3u;
    } else if ((pml4[2] & 0x000FFFFFFFFFF000u) != (uint64_t)(uintptr_t)pdpt_alias) {
        return 0u;
    }
    for (i = base >> 21; i <= (last >> 21); i++) pd_alias[alias_used][i & 511u] = (i << 21) | PD_DEV;
    pdpt_alias[alias_used] = (uint64_t)(uintptr_t)pd_alias[alias_used] | 3u;
    cr3_write(cr3_read());
    alias_used++;
    return ALIAS_VA + ((uint64_t)(alias_used - 1u) << 30) + (base - (gig << 30));
}

/* Maps [base, base + len) uncached and opens it to the rows; 0, or -1 (no window left, a range refused). A range
 * inside an open window is 0 at once. */
int64_t rt_mmio_map(uint64_t base, uint64_t len)
{
    uint64_t last = base + len - 1u, gig = base >> 30, i;
    unsigned k;
    if (len == 0u || last < base || (last >> 30) != gig || gig < 2u) return -1;
    for (k = 0u; k < windows; k++)
        if (base >= win_lo[k] && last < win_hi[k]) return 0;
    if (windows == MMIO_WINDOWS) return -1;
    if (gig >= 512u) {
        uint64_t va = alias(base, last);
        if (va == 0u) return -1;
        win_lo[windows] = base;
        win_hi[windows] = last + 1u;
        win_va[windows] = va;
        windows++;
        return 0;
    }
    if (gig < 8u) {
        uint64_t *pd = (uint64_t *)(uintptr_t)(pdpt[gig] & 0x000FFFFFFFFFF000u);
        if ((pdpt[gig] & 1u) == 0u) return -1;
        for (i = base >> 21; i <= (last >> 21); i++) pd[i & 511u] = (i << 21) | PD_DEV;
    } else if ((pdpt[gig] & 1u) == 0u) {
        if (dirs_used == MMIO_DIRS) return -1;
        for (i = base >> 21; i <= (last >> 21); i++) pd_mmio[dirs_used][i & 511u] = (i << 21) | PD_DEV;
        pdpt[gig] = (uint64_t)(uintptr_t)pd_mmio[dirs_used] | 3u;
        dirs_used++;
    } else {
        uint64_t *pd = (uint64_t *)(uintptr_t)(pdpt[gig] & 0x000FFFFFFFFFF000u);
        for (i = base >> 21; i <= (last >> 21); i++) pd[i & 511u] = (i << 21) | PD_DEV;
    }
    cr3_write(cr3_read());
    win_lo[windows] = base;
    win_hi[windows] = last + 1u;
    win_va[windows] = base;
    windows++;
    return 0;
}

/* The virtual address of register addr (width bytes, aligned, inside an open window), or 0. */
static uint64_t in_window(uint64_t addr, unsigned width)
{
    unsigned k;
    if ((addr & (width - 1u)) != 0u) return 0u;
    for (k = 0u; k < windows; k++)
        if (addr >= win_lo[k] && addr <= win_hi[k] - width) return win_va[k] + (addr - win_lo[k]);
    return 0u;
}

cint_status rt_mmio_in(uint64_t addr, unsigned width, uint64_t *v)
{
    addr = in_window(addr, width);
    if (addr == 0u) return CINT_REFUSED;
    if (width == 1u) *v = *(volatile uint8_t *)(uintptr_t)addr;
    else if (width == 2u) *v = *(volatile uint16_t *)(uintptr_t)addr;
    else *v = *(volatile uint32_t *)(uintptr_t)addr;
    return CINT_OK;
}

/* x86 keeps stores in order, and an uncached store is not passed by an earlier one, so a doorbell written here
 * follows the ring entries cint wrote to pool frames before it; the asm keeps the compiler from moving them. */
cint_status rt_mmio_out(uint64_t addr, unsigned width, uint64_t v)
{
    addr = in_window(addr, width);
    if (addr == 0u) return CINT_REFUSED;
    __asm__ volatile("" ::: "memory");
    if (width == 1u) *(volatile uint8_t *)(uintptr_t)addr = (uint8_t)v;
    else if (width == 2u) *(volatile uint16_t *)(uintptr_t)addr = (uint16_t)v;
    else *(volatile uint32_t *)(uintptr_t)addr = (uint32_t)v;
    return CINT_OK;
}
