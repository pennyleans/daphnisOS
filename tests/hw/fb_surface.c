/* Exercise the actual fb.c implementation with modeled ports and host RAM. No QEMU,
 * disk, or privileged instruction. QEMU separately exercises the real page tables. */
#define _GNU_SOURCE
#include <assert.h>
#include <stdlib.h>
#include <stdio.h>
#include <sys/mman.h>
#include "../../rt/rt.h"
static uint8_t *host_shadow;
#define SHADOW_BASE ((uint64_t)(uintptr_t)host_shadow)
#include "../../rt/fb.c"

uint64_t pml4[512], pdpt[512];
uint64_t rt_pool_end = 0x200000000u;
static uint16_t index_reg, regs[16];
static uint32_t bad_width, bad_pitch;
static int64_t now;
static bool restore_broken, said_error;
static uint8_t *native;
static uint64_t free_lo, free_hi, reserved_page, metadata_page;
static bool wake_tick;
static uint8_t before_wake;
cint_status test_idle_boundary(void);

void cpu_wait_irq(void)
{
    assert(native[0] == before_wake); /* the host shim must wait before draining */
    if (wake_tick) now++;
}

void port_out16(uint16_t port, uint16_t v)
{
    if (port == DISPI_INDEX) index_reg = v;
    else if (port == DISPI_DATA && index_reg < 16u) regs[index_reg] = v;
}
uint16_t port_in16(uint16_t port)
{
    (void)port;
    if (index_reg == DISPI_XRES && (regs[DISPI_XRES] == bad_width || (restore_broken && regs[DISPI_XRES] == 640u))) return 0u;
    if (index_reg == DISPI_VIRT_WIDTH && regs[DISPI_XRES] == bad_pitch) return (uint16_t)(regs[index_reg] + 1u);
    return regs[index_reg];
}
void port_out32(uint16_t port, uint32_t v) { (void)port; (void)v; }
uint32_t port_in32(uint16_t port) { (void)port; return 0xFFFFFFFFu; }
uint64_t cr3_read(void) { return 0u; }
void cr3_write(uint64_t v) { (void)v; }
uint64_t pat_read(void) { return 0u; }
void pat_write(uint64_t v) { (void)v; }
void fb_fence(void) { }
int64_t rt_timer_ticks(void) { return now; }
void rt_puts(const char *s) { (void)s; said_error = true; }
void rt_phys_window_fb(uint64_t lo, uint64_t hi) { (void)lo; (void)hi; }
bool rt_boot_pool_max(void) { return true; }
bool rt_boot_shadow_free(uint64_t lo, uint64_t n)
{
    if (free_hi == 0u || lo < free_lo || lo > free_hi || n > free_hi - lo) return false;
    return !(lo < reserved_page + PAGE_4K && reserved_page < lo + n) &&
           !(lo < metadata_page + PAGE_4K && metadata_page < lo + n);
}
size_t rt_boot_cmdline(char *dst, size_t n) { if (n != 0u) dst[0] = 0; return 0u; }
bool rt_boot_framebuffer(uint64_t *a, uint32_t *p, uint32_t *w, uint32_t *h, struct rt_fb_format *f)
{ (void)a; (void)p; (void)w; (void)h; (void)f; return false; }

static void setup(uint64_t w, uint64_t h, uint64_t pitch)
{
    memset(pml4, 0, sizeof pml4); memset(pdpt, 0, sizeof pdpt);
    memset(shadow_pdpt, 0, sizeof shadow_pdpt); memset(shadow_pd, 0, sizeof shadow_pd);
    memset(shadow_pt, 0, sizeof shadow_pt); memset(native, 0xA5, 4u * 1048576u);
    shadow_pages = 0u; prepared = true; fb_source = fb_status = 1;
    presenting = direct_seen = pending = false; presented_tick = -1;
    dirty_reset();
    free_lo = free_hi = reserved_page = metadata_page = 0u;
    said_error = restore_broken = false; bad_width = bad_pitch = 0u; now = 0;
    fb_format = (struct rt_fb_format){{16u, 8u, 0u}, {8u, 8u, 8u}};
    native_base = (uint64_t)(uintptr_t)native;
    fb_word_[0] = w; fb_word_[1] = h; fb_word_[2] = pitch;
    fb_word_[3] = SHADOW_BASE; fb_word_[4] = pitch * h; fb_mapped = 4u * 1048576u;
    assert(rt_fb_backing_add(RT_POOL_BASE, 512) == 0);
}

static void test_presentation(void)
{
    setup(3u, 2u, 13u); /* second row is intentionally unaligned */
    fb_format = (struct rt_fb_format){{0u, 8u, 16u}, {8u, 8u, 8u}};
    const uint8_t pixels[] = {0x56u, 0x34u, 0x12u, 0xFFu};
    assert(rt_fb_put(13u, pixels, 4, 1) == CINT_OK);
    assert(native_read(native + 13u) == 0x00563412u);
    assert(native[12] == 0xA5u && native[25] == 0xA5u); /* padding untouched */
    uint8_t change = 0xABu;
    assert(rt_fb_put(14u, &change, 1, 1) == CINT_OK);
    assert(native_read(native + 13u) == 0x0056AB12u); /* whole pixel reconverted */
    uint8_t out[4];
    assert(rt_fb_get(13u, out, 4) == 4 && out[1] == 0xABu && out[3] == 0xFFu);
    uint8_t cross[] = {0u, 0xFFu, 0u, 0u, 0x11u, 0x22u, 0x33u, 0x44u};
    assert(rt_fb_put(10u, cross, sizeof cross, 1) == CINT_OK);
    assert(native[12] == 0xA5u);
    rt_fb_present(); assert(verify_native());
    native[13] ^= 1u; assert(!verify_native());
    assert(rt_fb_verify()); /* final verification performs the documented final flush */
    for (unsigned i = 0u; i < 2u; i++) {
        fb_format = i == 0u ? (struct rt_fb_format){{11u, 5u, 0u}, {5u, 6u, 5u}} :
                              (struct rt_fb_format){{19u, 10u, 1u}, {8u, 8u, 8u}};
        rt_fb_present(); assert(verify_native());
    }
    /* A direct user store is invisible natively until a presentation boundary. */
    assert(rt_fb_page(0u) == RT_POOL_BASE);
    host_shadow[0] = 77u;
    dirty_mark(0u); /* collection is exercised separately below */
    rt_fb_timer_present(); assert(verify_native());
    uint32_t old = native_read(native);
    host_shadow[0] = 55u;
    dirty_mark(0u);
    rt_fb_timer_present(); assert(native_read(native) == old); /* same tick, no duplicate copy */
    assert(pending);
    now++; rt_fb_timer_present(); assert(verify_native());
    host_shadow[0] = 33u; rt_fb_present(); assert(verify_native()); /* SYNC boundary, no timer */
}

static void test_backing(void)
{
    setup(640u, 480u, 2560u);
    assert(rt_fb_need() == 0);
    assert(rt_fb_backing_add(RT_POOL_BASE + 3u * 1048576u, 1) == 0); /* crosses the PT boundary */
    fb_word_[4] = 513u * PAGE_4K;
    assert(rt_fb_page(512u * PAGE_4K) == RT_POOL_BASE + 3u * 1048576u);
    uint64_t count = shadow_pages, first = shadow_pt[0][0];
    host_shadow[0] = 0xFAu;
    assert(rt_fb_backing_add(RT_POOL_BASE, 1) == -1); /* overlap */
    assert(rt_fb_backing_add(RT_POOL_BASE + 1u, 1) == -1);
    assert(rt_fb_backing_add(RT_POOL_BASE, 0) == -1);
    assert(rt_fb_backing_add(UINT64_MAX - 4095u, 2) == -1);
    assert(shadow_pages == count && shadow_pt[0][0] == first && host_shadow[0] == 0xFAu);
    assert(rt_fb_page(513u * PAGE_4K) == 0u && rt_fb_page(1u) == 0u);
    assert(rt_fb_backing_add(RT_POOL_BASE + 2u * 1048576u, 1) == 0); /* insert between runs */
    assert(append_backing(0x1000000u, 1u)); /* validated outside-pool range, before the pool run */
    assert(shadow_lookup(0x1000000u) == 514u && shadow_lookup(RT_POOL_BASE + 2u * 1048576u) == 513u);
    for (uint64_t i = 1u; i < shadow_pages; i++) assert(shadow_index[i - 1u] < shadow_index[i]);
    for (uint64_t i = 0u; i < shadow_pages; i++) assert(shadow_pa(shadow_canonical[i]) / PAGE_4K == shadow_index[i]);
}

static void test_dirty(void)
{
    setup(3u, 2u, 13u);
    assert(rt_fb_page(0u) == RT_POOL_BASE);
    uint64_t *tables = mmap((void *)0x10000000u, 8u * PAGE_4K, PROT_READ | PROT_WRITE,
                            MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    assert(tables != MAP_FAILED && user_table((uintptr_t)tables) && (uintptr_t)tables < 0x40000000u);
    uint64_t *a4 = tables, *a3 = tables + 512u, *a2 = tables + 1024u, *a1 = tables + 1536u;
    uint64_t *b4 = tables + 2048u, *b3 = tables + 2560u, *b2 = tables + 3072u, *b1 = tables + 3584u;
    const uint64_t mark = 7u | 1024u, dirty = 64u;
    a4[0] = (uintptr_t)a3 | mark; a3[0] = (uintptr_t)a2 | mark; a2[0] = (uintptr_t)a1 | mark;
    b4[0] = (uintptr_t)b3 | mark; b3[0] = (uintptr_t)b2 | mark; b2[0] = (uintptr_t)b1 | mark;
    a1[0] = RT_POOL_BASE | mark; b1[0] = RT_POOL_BASE | mark;
    uint32_t old_native = native_read(native);
    rt_fb_collect((uintptr_t)a4); rt_fb_timer_present();
    assert(!pending && native_read(native) == old_native); /* clean mmap: no native copy */
    host_shadow[0] = 77u;
    a1[0] |= dirty;
    a1[1] = (RT_POOL_BASE + PAGE_4K) | mark | dirty;
    a1[2] = (RT_POOL_BASE + 2u * PAGE_4K) | 7u | dirty; /* private page: untouched */
    a1[3] = (RT_POOL_BASE + 3u * 1048576u) | mark | dirty; /* unrelated external page */
    a1[4] = RT_POOL_BASE | mark | dirty; /* alias */
    rt_fb_collect((uintptr_t)a4); /* A returns via a syscall and blocks */
    assert(pending && (a1[0] & dirty) == 0u && (a1[1] & dirty) == 0u && (a1[4] & dirty) == 0u);
    assert(dirty_count == 1u); /* aliases deduplicate; inactive page 1 loses D but is not pending */
    assert((a1[2] & dirty) != 0u && (a1[3] & dirty) != 0u);
    uint8_t part = 22u;
    assert(rt_fb_put(13u, &part, 1, 1) == CINT_OK && pending); /* partial put cannot lose A's pending update */
    rt_fb_collect((uintptr_t)b4); /* another process has no dirty mapping */
    rt_fb_present_pending(); assert(!pending && native[0] == 77u); /* explicit .ci SYNC flush */
    native[0] = 0xA5u;
    rt_fb_present_pending(); assert(native[0] == 0xA5u); /* clean explicit flush must not copy */
    assert(rt_fb_verify() && native[0] == 77u); /* final verification is forceful even when clean */
    old_native = native_read(native);
    rt_fb_collect((uintptr_t)b4); now++; rt_fb_timer_present();
    assert(native_read(native) == old_native && !pending); /* following clean return does not copy */
    host_shadow[0] = 55u; b1[0] |= dirty; /* fork alias writes shared shadow later */
    rt_fb_collect((uintptr_t)b4); rt_fb_timer_present();
    assert(native[0] == 55u && !pending && (b1[0] & dirty) == 0u);
    host_shadow[0] = 33u; a1[0] |= dirty;
    rt_fb_collect((uintptr_t)a4); rt_fb_timer_present(); assert(pending && native[0] == 55u);
    now++; rt_fb_timer_present(); assert(!pending && native[0] == 33u);
    host_shadow[0] = 44u; a1[0] |= dirty;
    rt_fb_collect((uintptr_t)a4); /* vfork/shared root, same tables */
    now++; rt_fb_timer_present(); assert(!pending && native[0] == 44u);
    a1[0] = a1[1] = a1[4] = b1[0] = 0u; /* unmap, ancestors intentionally remain marked */
    rt_fb_collect((uintptr_t)a4); assert(!pending);
    rt_fb_collect(rt_pool_end); rt_fb_collect(0x40000000u); rt_fb_collect((uintptr_t)a4 + 1u);
    a4[0] |= 128u; rt_fb_collect((uintptr_t)a4); assert(!pending); /* unsupported huge entry */
    assert(munmap(tables, 8u * PAGE_4K) == 0);
}

static void test_page_drain(void)
{
    setup(1024u, 128u, PAGE_4K); /* exactly 128 pages, one row per page */
    for (uint64_t i = 0u; i < 65u; i++) {
        host_shadow[i * PAGE_4K] = (uint8_t)i;
        dirty_mark(i); dirty_mark(i);
    }
    assert(dirty_count == 65u);
    rt_fb_timer_present();
    assert(dirty_count == 1u && pending && dirty_cursor == 64u && presented_tick == now);
    for (uint64_t i = 0u; i < 64u; i++) assert(native[i * PAGE_4K] == (uint8_t)i);
    assert(native[64u * PAGE_4K] == 0xA5u && native[66u * PAGE_4K] == 0xA5u);
    rt_fb_timer_present(); assert(dirty_count == 1u); /* same tick preserves budget remainder */
    dirty_mark(0u); dirty_mark(127u);
    now++; rt_fb_timer_present();
    assert(!pending && dirty_count == 0u && dirty_cursor == 1u); /* wraps, low page cannot starve high */
    assert(native[64u * PAGE_4K] == 64u && native[66u * PAGE_4K] == 0xA5u);

    dirty_mark(42u);
    uint64_t cursor = dirty_cursor;
    int64_t tick = presented_tick;
    now++;
    presenting = true;
    rt_fb_timer_present(); rt_fb_present_pending(); rt_fb_present();
    assert(pending && dirty_count == 1u && dirty_has(42u) && dirty_cursor == cursor && presented_tick == tick);
    presenting = false; fb_status = -1;
    rt_fb_timer_present(); rt_fb_present_pending(); rt_fb_present();
    assert(pending && dirty_count == 1u && dirty_has(42u) && dirty_cursor == cursor && presented_tick == tick);
    fb_status = 1;
    uint64_t len = fb_word_[4]; fb_word_[4] = 0u;
    rt_fb_timer_present(); rt_fb_present_pending(); rt_fb_present();
    assert(pending && dirty_count == 1u && dirty_has(42u) && dirty_cursor == cursor && presented_tick == tick);
    fb_word_[4] = len;
    rt_fb_timer_present(); assert(!pending && presented_tick == now); /* blocked attempts did not consume tick */

    for (uint64_t i = 0u; i < 128u; i++) dirty_mark(i);
    rt_fb_present_pending(); assert(!pending && dirty_count == 0u); /* explicit flush has no timer budget */

    setup(1024u, 2u, 4097u); /* pixel at 4097..4100 crosses neither row padding nor active tail */
    host_shadow[4097u] = 77u;
    dirty_mark(1u); rt_fb_present_pending();
    assert(native[4096u] == 0xA5u && native[4097u] == 77u && native[8193u] == 0xA5u);
    assert(native[8194u] == 0xA5u); /* final page is clipped to active length */
    setup(1024u, 2u, 4095u + 4u); /* row 1 pixel at 4099; row 1 pixel at 8191 straddles page 2 */
    host_shadow[8191u] = 91u;
    dirty_mark(2u); rt_fb_present_pending();
    assert(native[8191u] == 91u && native[8195u] == 0xA5u); /* expands a pixel, never row padding */
}

static void test_modes(void)
{
    setup(640u, 480u, 2560u);
    assert(rt_fb_mode_need(800u, 600u) == 0);
    assert(fb_word_[0] == 640u && fb_word_[2] == 2560u && fb_status == 1);
    assert(rt_fb_mode(800u, 600u) == 0 && fb_word_[2] == 3200u);
    assert(rt_fb_mode_need(640u, 480u) == 0 && rt_fb_mode(640u, 480u) == 0);
    assert(rt_fb_mode_need(1024u, 768u) > 0);
    assert(rt_fb_mode(1024u, 768u) == -22 && fb_word_[0] == 640u); /* backing not yet available */
    int64_t need = rt_fb_mode_need(1024u, 768u);
    assert(need > 0 && rt_fb_backing_add(RT_POOL_BASE + 4u * 1048576u, need) == 0);
    assert(rt_fb_mode(1024u, 768u) == 0 && fb_word_[0] == 1024u && fb_word_[2] == 4096u);
    dirty_mark(700u); assert(pending);
    assert(rt_fb_mode_need(640u, 480u) == 0 && rt_fb_mode(640u, 480u) == 0);
    assert(!pending && dirty_count == 0u); /* forceful mode presentation retires old visible work */
    dirty_mark(700u); assert(!pending); /* backed but inactive page */
    assert(rt_fb_mode_need(1024u, 768u) == 0 && rt_fb_mode(1024u, 768u) == 0);
    dirty_mark(700u); assert(pending); rt_fb_present_pending(); assert(!pending);
    assert(rt_fb_mode_need(640u, 480u) == 0 && rt_fb_mode(640u, 480u) == 0);
    assert(rt_fb_mode_need(800u, 600u) == 0);
    bad_pitch = 800u;
    assert(rt_fb_mode(800u, 600u) == -22 && fb_word_[0] == 640u && fb_status == 1);
    bad_pitch = 0u; bad_width = 800u;
    assert(rt_fb_mode_need(800u, 600u) == -22 && fb_word_[0] == 640u && fb_status == 1);
    restore_broken = true;
    assert(rt_fb_mode_need(800u, 600u) == -5 && fb_status == -1 && said_error);
}

static void test_idle(void)
{
    setup(1024u, 128u, PAGE_4K);
    uint64_t *tables = mmap((void *)0x10000000u, 4u * PAGE_4K, PROT_READ | PROT_WRITE,
                            MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    assert(tables != MAP_FAILED && user_table((uintptr_t)tables));
    uint64_t *l4 = tables, *l3 = tables + 512u, *l2 = tables + 1024u, *l1 = tables + 1536u;
    const uint64_t mark = 7u | 1024u;
    l4[0] = (uintptr_t)l3 | mark; l3[0] = (uintptr_t)l2 | mark; l2[0] = (uintptr_t)l1 | mark;
    assert(rt_fb_page(0u) != 0u);
    for (uint64_t i = 0u; i < 65u; i++) {
        host_shadow[i * PAGE_4K] = 73u;
        l1[i] = shadow_pa(i) | mark | 64u;
    }
    rt_fb_collect((uintptr_t)l4); /* last client returns through read and blocks, no SYNC */
    assert(dirty_count == 65u && native[0] == 0xA5u);
    before_wake = 0xA5u; wake_tick = true;
    assert(test_idle_boundary() == CINT_OK);
    assert(dirty_count == 1u && pending && native[0] == 73u && native[64u * PAGE_4K] == 0xA5u);
    before_wake = 73u; wake_tick = false; /* keyboard wake in the same timer tick */
    assert(test_idle_boundary() == CINT_OK);
    assert(dirty_count == 1u && native[64u * PAGE_4K] == 0xA5u);
    wake_tick = true;
    assert(test_idle_boundary() == CINT_OK);
    assert(!pending && native[64u * PAGE_4K] == 73u);
    native[0] = 0xA5u; before_wake = 0xA5u;
    assert(test_idle_boundary() == CINT_OK && native[0] == 0xA5u); /* clean idle: no native copy */
    assert(munmap(tables, 4u * PAGE_4K) == 0);
}

static void test_small_gaps(void)
{
    setup(640u, 480u, 2560u);
    shadow_pages = 0u;
    memset(shadow_pt, 0, sizeof shadow_pt);
    /* A module occupies every whole 2-MiB candidate. Its tail leaves 302 pages,
     * with one reserved page and one loader-metadata page that must not be used. */
    free_lo = 30u * 1048576u + PAGE_4K;
    free_hi = free_lo + 302u * PAGE_4K;
    reserved_page = free_lo + 50u * PAGE_4K;
    metadata_page = free_lo + 200u * PAGE_4K;
    reserve_outside_pool();
    assert(shadow_pages == 300u && rt_fb_need() == 0);
    assert(shadow_lookup(reserved_page) == shadow_pages && shadow_lookup(metadata_page) == shadow_pages);
    for (uint64_t i = 0u; i < shadow_pages; i++) {
        uint64_t pa = shadow_pa(i);
        assert(pa >= free_lo && pa < free_hi && pa < RT_POOL_BASE && pa != reserved_page && pa != metadata_page);
        assert(shadow_pa(shadow_canonical[i]) / PAGE_4K == shadow_index[i]);
    }
    reserve_outside_pool(); assert(shadow_pages == 300u); /* no duplicate ownership */
}

int main(void)
{
    host_shadow = calloc(1u, SHADOW_CAP);
    native = malloc(4u * 1048576u);
    assert(host_shadow != NULL && native != NULL);
    test_presentation(); test_backing(); test_modes(); test_dirty(); test_page_drain(); test_idle(); test_small_gaps();
    free(native); free(host_shadow);
    puts("shadow surface: PASS (presentation, padding, native layouts, backing, mode rollback, dirty aliases, bounded timer and actual idle host boundary)");
    return 0;
}
