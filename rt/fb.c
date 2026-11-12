/* rt/fb.c: the surface (F-1 and HW-1 ruling B): canonical XRGB RAM for every writer,
 * converted at presentation to one native linear framebuffer.
 *
 * Under QEMU's -kernel (Multiboot 1 brings no framebuffer) the standard VGA is found on PCI bus 0
 * (vendor 0x1234, device 0x1111; BAR 0 is the linear framebuffer, which the firmware assigned) and the
 * Bochs display interface at ports 0x1CE and 0x1CF is programmed to W x H x 32 with the linear
 * framebuffer on; the stride is the virtual width it reports, times 4. W x H is 640 x 480 unless the
 * loader's command line says daphnis.mode=WxH (HX-0 A, docs/specs/2026-11-05-h-hybrid.md, as RES-1 amends it):
 * W a multiple of 8 in [640, 5120], H in [480, 3840], W x H at most 3840 x 2160 (rt/fbmode.h); another value, or
 * a mode the device does not take (its memory), leaves 640 x 480. Without that device the loader's Multiboot 2
 * framebuffer tag is used as it is (the size the loader or the firmware chose), if it describes valid 32-bit
 * direct-color pixels.
 *
 * The canonical read window (rt/phys.c) never exposes VRAM. Native presentation still needs its gigabyte,
 * so the framebuffer's gigabyte
 * gets a page directory of its own under a free slot of the boot PDPT: 2 MiB pages over the
 * framebuffer only, present, writable, no-execute, write-combining (DS D-FB,
 * docs/specs/2026-11-07-ds-desk-speed.md: PAT entry 1, which PWT alone selects, is set to WC before the map; no
 * other mapping sets PWT alone). Uncached, each store was its own bus write, and a host that honors the guest's
 * memory type (KVM on AMD, a nested hypervisor) paid that for every byte of the screen. A framebuffer in the boot
 * gigabyte, or across two, or under a slot in use, is not mapped: status -1, no surface.
 *
 * HX-13: rt_fb_mode switches the Bochs display's size while the system runs; the bytes of the largest mode (the
 * pixel cap of rt/fbmode.h, 3840 x 2160 x 4) are mapped at the start for it.
 *
 * W-2 (src/tile.ci): rt_fb_put writes a client's row into its tile, the one kernel write to the surface;
 * a range outside the framebuffer is refused, as the phys window refuses one. */
#include "rt.h"
#include "fbmode.h"

#define PCI_ADDR 0xCF8u
#define PCI_DATA 0xCFCu
#define STDVGA_ID 0x11111234u
#define DISPI_INDEX 0x1CEu
#define DISPI_DATA 0x1CFu
#define DISPI_ID 0u
#define DISPI_XRES 1u
#define DISPI_YRES 2u
#define DISPI_BPP 3u
#define DISPI_ENABLE 4u
#define DISPI_VIRT_WIDTH 6u
#define DISPI_ID_MASK 0xFFF0u
#define DISPI_ID_BASE 0xB0C0u
#define DISPI_ON_LFB 0x41u
#define PAGE_2M (1u << 21)
#define PD_FLAGS (0x8Bu | 0x8000000000000000u) /* present, writable, PWT (PAT entry 1: WC), 2 MiB, no-execute */
#define PAT_WC 0x01u
#define PAT_1 8u                 /* entry 1's byte of IA32_PAT: PWT=1, PCD=0, PAT=0 */

extern uint64_t pdpt[]; /* boot.S: the PDPT of the boot tables, slot 0 the boot gigabyte, slot 1 src/paging.ci's */

static uint64_t pd_fb[512] __attribute__((aligned(4096)));
static uint64_t fb_word_[5]; /* w, h, stride, base, len */
static int64_t fb_status;    /* 1 the Bochs device, 2 the loader's tag, 0 none, -1 found but not mappable */
static uint64_t fb_mapped;   /* bytes mapped from the base: the largest mode on the Bochs device (HX-13), else len */
static struct rt_fb_format fb_format = {{16u, 8u, 0u}, {8u, 8u, 8u}};
/* HW-1 ruling B: all writers see canonical WB RAM. Only presentation reaches VRAM.
 * The kernel-only virtual range is in PML4 slot 1; process roots do not inherit it.
 * Outside-pool RAM is tried first. Any remaining backing is allocated by cint frames,
 * never taken from the allocator invisibly. Stable PTEs survive live mode changes. */
#ifndef SHADOW_BASE
#define SHADOW_BASE 0x8000000000u /* 512 GiB, kernel CR3 only */
#endif
#define SHADOW_CAP (64u * 1048576u)
#define PAGE_4K 4096u
#define LEAF_WB_NX 0x8000000000000003u
extern uint64_t pml4[];
static uint64_t shadow_pdpt[512] __attribute__((aligned(4096)));
static uint64_t shadow_pd[512] __attribute__((aligned(4096)));
static uint64_t shadow_pt[32][512] __attribute__((aligned(4096)));
static uint64_t shadow_pages, native_base;
/* Membership index only; shadow PTEs remain the translation authority. Every backing
 * page lies below RT_POOL_CAP (8 GiB), so its physical page number fits in U32. */
static uint32_t shadow_index[SHADOW_CAP / PAGE_4K];
static uint16_t shadow_canonical[SHADOW_CAP / PAGE_4K];
static uint8_t dirty_pages[SHADOW_CAP / PAGE_4K / 8u];
static uint64_t dirty_count, dirty_cursor;
static int64_t fb_source;
static bool prepared, presenting, direct_seen, pending;
static uint32_t staged_w, staged_h, staged_pitch;
static int64_t presented_tick = -1;

static uint32_t native_read(const volatile uint8_t *p)
{
    if ((uintptr_t)p % 4u == 0u) return *(const volatile uint32_t *)(const void *)p;
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

static void native_write(volatile uint8_t *p, uint32_t v)
{
    if ((uintptr_t)p % 4u == 0u) {
        *(volatile uint32_t *)(void *)p = v;
    } else {
        for (unsigned i = 0u; i < 4u; i++) p[i] = (uint8_t)(v >> (8u * i));
    }
}

static uint64_t shadow_pa(uint64_t page)
{
    return shadow_pt[page / 512u][page % 512u] & 0x000FFFFFFFFFF000u;
}

static uint64_t index_lower(uint32_t page)
{
    uint64_t lo = 0u, hi = shadow_pages;
    while (lo < hi) {
        uint64_t mid = lo + (hi - lo) / 2u;
        if (shadow_index[mid] < page) lo = mid + 1u;
        else hi = mid;
    }
    return lo;
}

static uint64_t shadow_lookup(uint64_t pa)
{
    if (pa >= RT_POOL_CAP || pa % PAGE_4K != 0u) return shadow_pages;
    uint32_t page = (uint32_t)(pa / PAGE_4K);
    uint64_t at = index_lower(page);
    return at < shadow_pages && shadow_index[at] == page ? shadow_canonical[at] : shadow_pages;
}

static bool append_backing(uint64_t pa, uint64_t pages)
{
    uint64_t bytes;
    if (pages == 0u || pages > SHADOW_CAP / PAGE_4K - shadow_pages || pa % PAGE_4K != 0u) return false;
    bytes = pages * PAGE_4K;
    if (pa > RT_POOL_CAP || bytes > RT_POOL_CAP - pa) return false;
    if (pml4[1] != 0u && (pml4[1] & 0x000FFFFFFFFFF000u) != (uint64_t)(uintptr_t)shadow_pdpt) return false;
    uint32_t first = (uint32_t)(pa / PAGE_4K);
    uint64_t insert = index_lower(first);
    if (insert < shadow_pages && shadow_index[insert] < first + pages) return false;
    /* No failure after this point: ownership transfers only on a complete append. */
    memmove(shadow_index + insert + pages, shadow_index + insert, (size_t)(shadow_pages - insert) * sizeof shadow_index[0]);
    memmove(shadow_canonical + insert + pages, shadow_canonical + insert,
            (size_t)(shadow_pages - insert) * sizeof shadow_canonical[0]);
    for (uint64_t i = 0u; i < pages; i++) {
        shadow_index[insert + i] = first + (uint32_t)i;
        shadow_canonical[insert + i] = (uint16_t)(shadow_pages + i);
    }
    for (uint64_t i = 0u; i < pages; i++) {
        uint64_t page = shadow_pages + i, pd_index = page / 512u;
        shadow_pt[pd_index][page % 512u] = (pa + i * PAGE_4K) | LEAF_WB_NX;
        shadow_pd[pd_index] = (uint64_t)(uintptr_t)shadow_pt[pd_index] | 3u;
    }
    shadow_pdpt[0] = (uint64_t)(uintptr_t)shadow_pd | 3u;
    pml4[1] = (uint64_t)(uintptr_t)shadow_pdpt | 3u;
    cr3_write(cr3_read());
    memset((void *)(uintptr_t)(SHADOW_BASE + shadow_pages * PAGE_4K), 0, (size_t)bytes);
    shadow_pages += pages;
    return true;
}

static void reserve_outside_pool(void)
{
    for (uint64_t pa = 0x400000u; pa < RT_POOL_BASE && shadow_pages < SHADOW_CAP / PAGE_4K; pa += PAGE_2M) {
        if (rt_boot_shadow_free(pa, PAGE_2M)) (void)append_backing(pa, PAGE_2M / PAGE_4K);
    }
    /* A large loader module can intersect every 2-MiB candidate while leaving
     * enough page-sized RAM for the initial surface. Verify each page, exclude
     * existing backing, and coalesce only adjacent accepted pages. The allocator
     * still owns everything at and above RT_POOL_BASE under pool=max. */
    uint64_t need = (fb_word_[4] + PAGE_4K - 1u) / PAGE_4K;
    for (uint64_t pa = 0x400000u; pa < RT_POOL_BASE && shadow_pages < need;) {
        if (shadow_lookup(pa) != shadow_pages || !rt_boot_shadow_free(pa, PAGE_4K)) {
            pa += PAGE_4K;
            continue;
        }
        uint64_t first = pa, pages = 0u;
        do {
            pages++;
            pa += PAGE_4K;
        } while (pa < RT_POOL_BASE && pages < need - shadow_pages &&
                 shadow_lookup(pa) == shadow_pages && rt_boot_shadow_free(pa, PAGE_4K));
        if (!append_backing(first, pages)) break;
    }
    if (rt_boot_pool_max()) return;
    for (uint64_t pa = (RT_BLOB_END + PAGE_2M - 1u) & ~(uint64_t)(PAGE_2M - 1u);
         pa < 0x40000000u && shadow_pages < SHADOW_CAP / PAGE_4K; pa += PAGE_2M) {
        if (rt_boot_shadow_free(pa, PAGE_2M)) (void)append_backing(pa, PAGE_2M / PAGE_4K);
    }
}

int64_t rt_fb_backing_add(uint64_t pa, int64_t pages)
{
    if (!prepared || fb_source <= 0 || pages <= 0 || (uint64_t)pages > SHADOW_CAP / PAGE_4K ||
        pa < RT_POOL_BASE || pa > rt_pool_end || (uint64_t)pages * PAGE_4K > rt_pool_end - pa) return -1;
    return append_backing(pa, (uint64_t)pages) ? 0 : -1;
}

static int64_t pages_needed(uint64_t bytes)
{
    if (bytes == 0u || bytes > SHADOW_CAP) return -1;
    uint64_t pages = (bytes + PAGE_4K - 1u) / PAGE_4K;
    return pages > shadow_pages ? (int64_t)(pages - shadow_pages) : 0;
}

int64_t rt_fb_need(void) { return fb_source > 0 ? pages_needed(fb_word_[4]) : -1; }

uint64_t rt_fb_page(uint64_t off)
{
    if (fb_status <= 0 || off % PAGE_4K != 0u || off >= (fb_word_[4] + PAGE_4K - 1u) / PAGE_4K * PAGE_4K) return 0u;
    direct_seen = true;
    return shadow_pa(off / PAGE_4K);
}

static bool present_range(uint64_t off, uint64_t bytes)
{
    if (fb_status <= 0 || presenting || off > fb_word_[4] || bytes > fb_word_[4] - off || bytes == 0u) return false;
    presenting = true;
    uint64_t pitch = fb_word_[2], end = off + bytes;
    for (uint64_t row = off / pitch; row <= (end - 1u) / pitch; row++) {
        uint64_t first = off > row * pitch ? off - row * pitch : 0u;
        uint64_t last = end < (row + 1u) * pitch ? end - row * pitch : pitch;
        uint64_t visible = fb_word_[0] * 4u;
        if (last > visible) last = visible;
        if (first >= last) continue;
        first &= ~(uint64_t)3u;
        last = (last + 3u) & ~(uint64_t)3u;
        const uint8_t *src = (const uint8_t *)(uintptr_t)(SHADOW_BASE + row * pitch + first);
        uint8_t *dst = (uint8_t *)(uintptr_t)(native_base + row * pitch + first);
        if (rt_fb_format_xrgb(&fb_format)) {
            memcpy(dst, src, (size_t)(last - first));
        } else {
            for (uint64_t x = 0u; x < last - first; x += 4u) {
                uint32_t pixel;
                memcpy(&pixel, src + x, 4u);
                native_write(dst + x, rt_fb_encode(&fb_format, pixel));
            }
        }
    }
    presenting = false;
    return true;
}

static void dirty_reset(void)
{
    memset(dirty_pages, 0, sizeof dirty_pages);
    dirty_count = dirty_cursor = 0u;
    pending = false;
}

static bool dirty_has(uint64_t page)
{
    return (dirty_pages[page / 8u] & (1u << (page % 8u))) != 0u;
}

static void dirty_mark(uint64_t page)
{
    if (page >= (fb_word_[4] + PAGE_4K - 1u) / PAGE_4K || page >= shadow_pages || dirty_has(page)) return;
    dirty_pages[page / 8u] |= (uint8_t)(1u << (page % 8u));
    dirty_count++;
    pending = true;
}

void rt_fb_present(void)
{
    if (present_range(0u, fb_word_[4])) dirty_reset();
}

/* One CPU: no writer runs during this drain. Clean pages cost no native writes.
 * A wrapping cursor prevents repeated low-page writes from starving higher pages.
 * The page budget bounds canonical bytes; odd pitch can expand a boundary pixel. */
static uint64_t dirty_drain(uint64_t budget)
{
    if (!pending || fb_status <= 0 || presenting || fb_word_[4] == 0u) return 0u;
    uint64_t pages = (fb_word_[4] + PAGE_4K - 1u) / PAGE_4K;
    uint64_t at = dirty_cursor % pages, visited = 0u, done = 0u;
    while (visited < pages && done < budget && dirty_count != 0u) {
        if (!dirty_has(at)) {
            at = (at + 1u) % pages;
            visited++;
            continue;
        }
        uint64_t run = 1u;
        while (at + run < pages && visited + run < pages && done + run < budget && dirty_has(at + run)) run++;
        uint64_t off = at * PAGE_4K, bytes = run * PAGE_4K;
        if (bytes > fb_word_[4] - off) bytes = fb_word_[4] - off;
        if (!present_range(off, bytes)) break;
        for (uint64_t i = at; i < at + run; i++) dirty_pages[i / 8u] &= (uint8_t)~(1u << (i % 8u));
        dirty_count -= run;
        done += run;
        visited += run;
        at = (at + run) % pages;
        dirty_cursor = at;
    }
    pending = dirty_count != 0u;
    return done;
}

/* Every user return collects writes before .ci dispatch; kernel puts present their
 * spans separately and must not clear unrelated dirty-page evidence. */
void rt_fb_present_pending(void) { (void)dirty_drain(SHADOW_CAP / PAGE_4K); }

static bool user_table(uint64_t pa)
{
    return pa % PAGE_4K == 0u && pa >= RT_POOL_BASE && pa <= rt_pool_end &&
           PAGE_4K <= rt_pool_end - pa && !(pa >= 0x40000000u && pa < 0x80000000u);
}

static bool marked_table(uint64_t entry)
{
    const uint64_t need = 1u | 4u | 1024u; /* present, user, marked subtree */
    return (entry & need) == need && (entry & 128u) == 0u && user_table(entry & 0x000FFFFFFFFFF000u);
}

/* One CPU, no PCID and non-global user mappings: user_leave switched CR3 before this
 * call, so clearing D cannot be hidden in an active user TLB. Inspect EVERY returning
 * root, including syscall returns: a writer may block while another process gets the
 * next timer. Retain exact canonical pages until their successful presentation. */
void rt_fb_collect(uint64_t root)
{
    if (fb_status <= 0 || !direct_seen || !user_table(root)) return;
    uint64_t *l4 = (uint64_t *)(uintptr_t)root;
    for (unsigned a = 0u; a < 256u; a++) {
        if (!marked_table(l4[a])) continue;
        uint64_t *l3 = (uint64_t *)(uintptr_t)(l4[a] & 0x000FFFFFFFFFF000u);
        for (unsigned b = 0u; b < 512u; b++) {
            if (!marked_table(l3[b])) continue;
            uint64_t *l2 = (uint64_t *)(uintptr_t)(l3[b] & 0x000FFFFFFFFFF000u);
            for (unsigned c = 0u; c < 512u; c++) {
                if (!marked_table(l2[c])) continue;
                uint64_t *l1 = (uint64_t *)(uintptr_t)(l2[c] & 0x000FFFFFFFFFF000u);
                for (unsigned d = 0u; d < 512u; d++) {
                    uint64_t e = l1[d], need = 1u | 4u | 64u | 1024u;
                    if ((e & need) == need && (e & 256u) == 0u) {
                        uint64_t page = shadow_lookup(e & 0x000FFFFFFFFFF000u);
                        if (page == shadow_pages) continue;
                        l1[d] = e & ~(uint64_t)64u;
                        dirty_mark(page); /* inactive old-mode aliases lose D without scheduling a copy */
                    }
                }
            }
        }
    }
}
void rt_fb_timer_present(void)
{
    int64_t tick = rt_timer_ticks();
    if (tick != presented_tick && dirty_drain(64u) != 0u) presented_tick = tick;
}

/* Final readback only: compare native channel fields, not undefined X bits or padding.
 * The surface digest never reads VRAM. One volatile read per visible native pixel. */
static bool verify_native(void)
{
    if (fb_status <= 0) return true;
    fb_fence();
    uint32_t mask = rt_fb_rgb_mask(&fb_format);
    for (uint64_t y = 0u; y < fb_word_[1]; y++) {
        for (uint64_t x = 0u; x < fb_word_[0]; x++) {
            uint64_t off = y * fb_word_[2] + 4u * x;
            uint32_t pixel;
            memcpy(&pixel, (const void *)(uintptr_t)(SHADOW_BASE + off), 4u);
            uint32_t got = native_read((const volatile uint8_t *)(uintptr_t)(native_base + off));
            if ((got & mask) != rt_fb_encode(&fb_format, pixel)) return false;
        }
    }
    return true;
}

bool rt_fb_verify(void)
{
    rt_fb_present();
    return verify_native();
}

static uint32_t pci_read(unsigned dev, unsigned reg)
{
    port_out32(PCI_ADDR, 0x80000000u | (dev << 11) | (reg & 0xFCu));
    return port_in32(PCI_DATA);
}

static void pci_write(unsigned dev, unsigned reg, uint32_t v)
{
    port_out32(PCI_ADDR, 0x80000000u | (dev << 11) | (reg & 0xFCu));
    port_out32(PCI_DATA, v);
}

static void dispi_write(uint16_t index, uint16_t v)
{
    port_out16(DISPI_INDEX, index);
    port_out16(DISPI_DATA, v);
}

static uint16_t dispi_read(uint16_t index)
{
    port_out16(DISPI_INDEX, index);
    return port_in16(DISPI_DATA);
}

/* daphnis.mode=WxH as a word of the loader's command line, into *w and *h; false, and both untouched, if
 * it is absent or out of range. */
static bool mode_of(uint32_t *w, uint32_t *h)
{
    static const char key[] = "daphnis.mode=";
    char line[256];
    size_t n = rt_boot_cmdline(line, sizeof line), i, k;
    for (i = 0; i + sizeof key - 1u <= n; i++) {
        uint32_t a = 0u, b = 0u;
        if (i > 0u && line[i - 1u] != ' ') continue;
        for (k = 0; k < sizeof key - 1u && line[i + k] == key[k]; k++) {
        }
        if (k != sizeof key - 1u) continue;
        i += k;
        for (k = 0; k < 4u && line[i] >= '0' && line[i] <= '9'; k++, i++) a = 10u * a + (uint32_t)(line[i] - '0');
        if (k == 0u || line[i] != 'x') return false;
        i++;
        for (k = 0; k < 4u && line[i] >= '0' && line[i] <= '9'; k++, i++) b = 10u * b + (uint32_t)(line[i] - '0');
        if (k == 0u || (line[i] != '\0' && line[i] != ' ')) return false;
        if (!fb_mode_fits(a, b)) return false;
        *w = a;
        *h = b;
        return true;
    }
    return false;
}

/* Programs the Bochs display to w x h x 32; false if it reads back another size. */
static bool dispi_mode(uint16_t w, uint16_t h)
{
    dispi_write(DISPI_ENABLE, 0u);
    dispi_write(DISPI_XRES, w);
    dispi_write(DISPI_YRES, h);
    dispi_write(DISPI_BPP, 32u);
    dispi_write(DISPI_VIRT_WIDTH, w);
    dispi_write(DISPI_ENABLE, DISPI_ON_LFB);
    return dispi_read(DISPI_XRES) == w && dispi_read(DISPI_YRES) == h && dispi_read(DISPI_BPP) == 32u;
}

/* The old descriptor is not operational unless the actual device restored it, including
 * pitch. Failure is explicit and disables the surface rather than writing with stale metadata. */
static bool restore_mode(uint64_t w, uint64_t h)
{
    if (!dispi_mode((uint16_t)w, (uint16_t)h) || (uint64_t)dispi_read(DISPI_VIRT_WIDTH) * 4u != fb_word_[2]) {
        fb_status = -1;
        rt_phys_window_fb(0u, 0u);
        rt_puts("daphnis: framebuffer mode restore failed\n");
        return false;
    }
    rt_fb_present();
    return true;
}

static bool bochs_find(void)
{
    unsigned dev;
    uint32_t w = FB_W, h = FB_H;
    for (dev = 0u; dev < 32u; dev++) {
        uint64_t bar0;
        uint16_t vw;
        if (pci_read(dev, 0u) != STDVGA_ID) continue;
        bar0 = pci_read(dev, 0x10u) & ~(uint64_t)0xFu;
        if (bar0 == 0u || (dispi_read(DISPI_ID) & DISPI_ID_MASK) != DISPI_ID_BASE) return false;
        pci_write(dev, 4u, pci_read(dev, 4u) | 2u); /* memory space on */
        if (!mode_of(&w, &h) || !dispi_mode((uint16_t)w, (uint16_t)h)) {
            w = FB_W;
            h = FB_H;
            (void)dispi_mode((uint16_t)w, (uint16_t)h);
        }
        vw = dispi_read(DISPI_VIRT_WIDTH);
        if (vw < w) vw = (uint16_t)w;
        fb_word_[0] = w;
        fb_word_[1] = h;
        fb_word_[2] = (uint64_t)vw * 4u;
        fb_word_[3] = bar0;
        return true;
    }
    return false;
}

static bool fb_map(void)
{
    uint64_t base = native_base, last = base + fb_mapped - 1u, gig = base >> 30, i;
    if (fb_mapped == 0u || last < base || gig == 0u || gig >= 512u || (last >> 30) != gig) return false;
    pat_write((pat_read() & ~((uint64_t)0xFFu << PAT_1)) | ((uint64_t)PAT_WC << PAT_1));
    if ((pdpt[gig] & 1u) != 0u) {
        /* M-3: boot.S identity maps 2 to 8 GiB; the framebuffer's entries of that directory get the device bits */
        uint64_t *pd = (uint64_t *)(uintptr_t)(pdpt[gig] & 0x000FFFFFFFFFF000u);
        if (gig < 2u || gig >= 8u) return false;
        for (i = base >> 21; i <= (last >> 21); i++) pd[i & 511u] = (i << 21) | PD_FLAGS;
    } else {
        for (i = base >> 21; i <= (last >> 21); i++) pd_fb[i & 511u] = (i << 21) | PD_FLAGS;
        pdpt[gig] = (uint64_t)(uintptr_t)pd_fb | 3u;
    }
    cr3_write(cr3_read());
    return true;
}

int64_t rt_fb_prepare(void)
{
    uint32_t pitch, w, h;
    if (prepared) return fb_source;
    prepared = true;
    fb_status = 0;
    bool use_bochs = true;
#ifdef RT_FB_FORCE_GOP
    use_bochs = false; /* diagnostic build only: prove the real firmware tag fallback */
#endif
    if (use_bochs && bochs_find()) {
        fb_source = 1;
    } else if (rt_boot_framebuffer(&fb_word_[3], &pitch, &w, &h, &fb_format)) {
        fb_word_[0] = w;
        fb_word_[1] = h;
        fb_word_[2] = pitch;
        fb_source = 2;
    }
    if (fb_source > 0) {
        native_base = fb_word_[3];
        fb_word_[4] = fb_word_[2] * fb_word_[1];
        if (native_base % 4u != 0u || fb_word_[4] == 0u || fb_word_[4] > SHADOW_CAP) return fb_source = -1;
        fb_mapped = fb_word_[4];
        if (fb_source == 1 && fb_mapped < 4u * (uint64_t)MODE_PX_MAX) {
            uint64_t end = ((fb_word_[3] >> 30) + 1u) << 30;   /* the map stays in the base's gigabyte */
            fb_mapped = 4u * (uint64_t)MODE_PX_MAX;   /* RES-1: the pixel cap, not the widest by the tallest */
            if (fb_word_[3] + fb_mapped > end) fb_mapped = end - fb_word_[3];
            if (fb_mapped < fb_word_[4]) fb_mapped = fb_word_[4];
        }
        if (!fb_map()) return fb_source = -1;
        reserve_outside_pool();
    }
    return fb_source;
}

int64_t rt_fb_init(void)
{
    if (fb_source <= 0) return fb_source;
    if (rt_fb_need() != 0) return -1;
    fb_word_[3] = SHADOW_BASE;
    fb_status = fb_source;
    rt_phys_window_fb(SHADOW_BASE, SHADOW_BASE + fb_word_[4]);
    rt_fb_present();
    return fb_status;
}

uint64_t rt_fb_word(int64_t i)
{
    if (i == 5) return fb_status > 0 ? (uint64_t)fb_source : 0u;   /* KF-3d: 1 the Bochs display, 2 the loader's framebuffer */
    return (fb_status > 0 && i >= 0 && i < 5) ? fb_word_[i] : 0u;
}

cint_status rt_fb_put(uint64_t off, const uint8_t *src, int64_t len, int64_t stride)
{
    uint8_t *dst;
    if (fb_status <= 0 || len < 0 || off > fb_word_[4] || (uint64_t)len > fb_word_[4] - off) return CINT_REFUSED;
    dst = (uint8_t *)(uintptr_t)(fb_word_[3] + off);
    if (stride == 1) {
        memcpy(dst, src, (size_t)len);   /* D-FB: eight bytes a store (rt/mem.c) */
        present_range(off, (uint64_t)len);
        return CINT_OK;
    }
    for (int64_t i = 0; i < len; i++) dst[i] = src[i * stride];
    present_range(off, (uint64_t)len);
    return CINT_OK;
}

/* H-4: len bytes of the framebuffer at byte offset off into dst (the cursor's save-under); len, or -1. */
int64_t rt_fb_get(uint64_t off, uint8_t *dst, int64_t len)
{
    const uint8_t *src;
    if (fb_status <= 0 || len < 0 || off > fb_word_[4] || (uint64_t)len > fb_word_[4] - off) return -1;
    src = (const uint8_t *)(uintptr_t)(fb_word_[3] + off);
    memcpy(dst, src, (size_t)len);
    return len;
}

/* H-4b (src/tile.ci place_row): buf's first m pixels spread over the whole of it, in place from the right, each
 * pixel s times, pixel i becoming old pixel (phase + i) / s; the run is scaled here once, not pixel by pixel in
 * checked code. A refusal when m pixels do not hold the last one taken, or s or phase is out of range. */
cint_status rt_px_spread(uint8_t *buf, int64_t blen, int64_t m, int64_t s, int64_t phase)
{
    int64_t n = blen / 4;
    if (s < 1 || s > 6 || phase < 0 || phase >= s || m < 0 || 4 * m > blen) return CINT_REFUSED;
    if (n > 0 && (phase + n - 1) / s >= m) return CINT_REFUSED;
    for (int64_t i = n - 1; i >= 0; i--) {
        int64_t j = 4 * ((phase + i) / s);
        for (int k = 0; k < 4; k++) buf[4 * i + k] = buf[j + k];
    }
    return CINT_OK;
}

/* HX-13: the Bochs display reprogrammed to w x h x 32 while the system runs; 0, -22 for a size out of range
 * (rt/fbmode.h, RES-1) or one the device does not take (it is left at the size it had), -95 without the Bochs
 * device. */
int64_t rt_fb_mode_need(uint64_t w, uint64_t h)
{
    uint16_t vw;
    uint64_t ow = fb_word_[0], oh = fb_word_[1];
    if (fb_status != 1) return -95;
    if (!fb_mode_fits(w, h)) return -22;
    staged_w = staged_h = staged_pitch = 0u;
    if (!dispi_mode((uint16_t)w, (uint16_t)h)) {
        if (!restore_mode(ow, oh)) return -5;
        return -22;
    }
    vw = dispi_read(DISPI_VIRT_WIDTH);
    if (vw < w) vw = (uint16_t)w;
    if (!restore_mode(ow, oh)) return -5;
    if ((uint64_t)vw * 4u * h > fb_mapped) return -22;
    int64_t need = pages_needed((uint64_t)vw * 4u * h);
    if (need < 0) return -22;
    staged_w = (uint32_t)w;
    staged_h = (uint32_t)h;
    staged_pitch = (uint32_t)vw * 4u;
    return need;
}

int64_t rt_fb_mode(uint64_t w, uint64_t h)
{
    uint64_t ow = fb_word_[0], oh = fb_word_[1];
    if (fb_status != 1) return -95;
    if (w != staged_w || h != staged_h || staged_pitch == 0u || pages_needed((uint64_t)staged_pitch * h) != 0) return -22;
    bool ok = dispi_mode((uint16_t)w, (uint16_t)h);
    uint16_t vw = dispi_read(DISPI_VIRT_WIDTH);
    if (!ok || (uint32_t)vw * 4u != staged_pitch) {
        if (!restore_mode(ow, oh)) return -5;
        return -22;
    }
    fb_word_[0] = w;
    fb_word_[1] = h;
    fb_word_[2] = staged_pitch;
    fb_word_[4] = fb_word_[2] * h;
    rt_phys_window_fb(fb_word_[3], fb_word_[3] + fb_word_[4]);
    staged_w = staged_h = staged_pitch = 0u;
    rt_fb_present();
    return 0;
}
