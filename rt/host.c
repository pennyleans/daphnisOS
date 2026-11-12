/* rt/host.c: the host side of `extern`. Emitted C does not call an extern as a C symbol:
 * it calls cint_rt_host_call(ctx, site, k, ...), where k is the row of the module's import
 * table. rt_host_bind resolves each row once, by name and parameter count, to a row of the
 * table below (SPEC-03 A-10 as the hosted runtime does at context creation), and
 * cint_rt_host_call checks the argument and result types of the call against the row and
 * runs it. A new extern is one row here and, if it touches the machine, one stub in
 * arch/x86_64/. */
#include "rt.h"

typedef cint_status (*host_fn)(const cint_value *args, cint_value *result);

#define MAX_PARAMS 4u

/* A parameter's tag, or the tag of a view's elements with VIEW_IN (an `in` view, read by the
 * host) or VIEW_OUT (an `out` view, written by the host). */
#define VIEW_IN 0x100u
#define VIEW_OUT 0x200u

typedef struct host_entry {
    const char *name;
    uint32_t nparams;
    uint16_t params[MAX_PARAMS]; /* type tags of the parameters */
    uint16_t result;             /* type tag of the result, 0 for void */
    host_fn fn;
} host_entry;

extern uint32_t mb_info; /* the Multiboot info pointer boot.S saved */

#define U8_ CINT_TAG_U8
#define U16_ CINT_TAG_U16
#define U32_ CINT_TAG_U32
#define U64_ CINT_TAG_U64
#define I64_ CINT_TAG_I64

/* Row functions. The void-returning stubs share one wrapper shape. */
#define ROW(fname, body) \
    static cint_status fname(const cint_value *a, cint_value *r) \
    {                                                            \
        (void)a;                                                 \
        (void)r;                                                 \
        body;                                                    \
        return CINT_OK;                                          \
    }

#ifdef RT_CAPTURE
/* COM1's line control register as cint last wrote it, never read from the port (as in the #else below). */
static uint8_t com1_lcr;
static int capture_port_denied(uint64_t port, unsigned width, int writing)
{
    if (port < 0x51Cu && port + width > 0x510u) return 1;
    if (writing && width > 1u && port < 0x400u && port + width > 0x3F8u) return 1;
    return 0;
}
static cint_status hf_port_out8(const cint_value *a, cint_value *r)
{
    uint16_t port = (uint16_t)a[0].as.u64;
    (void)r;
    if (capture_port_denied(port, 1u, 1)) return CINT_REFUSED;
    if (port == 0x3FBu) com1_lcr = (uint8_t)a[1].as.u64;
    if (port == 0x3F8u && (com1_lcr & 0x80u) == 0u)
        rt_serial_byte((uint8_t)a[1].as.u64);
    else port_out8(port, (uint8_t)a[1].as.u64);
    return CINT_OK;
}
#define CAPTURE_IO(fname, width, writing, body) \
    static cint_status fname(const cint_value *a, cint_value *r) { \
        (void)r; \
        if (capture_port_denied((uint16_t)a[0].as.u64, width, writing)) return CINT_REFUSED; \
        body; return CINT_OK; \
    }
CAPTURE_IO(hf_port_in8, 1u, 0, r->as.u64 = port_in8((uint16_t)a[0].as.u64))
CAPTURE_IO(hf_port_out16, 2u, 1, port_out16((uint16_t)a[0].as.u64, (uint16_t)a[1].as.u64))
CAPTURE_IO(hf_port_in16, 2u, 0, r->as.u64 = port_in16((uint16_t)a[0].as.u64))
CAPTURE_IO(hf_port_out32, 4u, 1, port_out32((uint16_t)a[0].as.u64, (uint32_t)a[1].as.u64))
CAPTURE_IO(hf_port_in32, 4u, 0, r->as.u64 = port_in32((uint16_t)a[0].as.u64))
#else
/* HW-3: a byte cint writes to COM1's transmit register (DLAB clear) goes through rt/console.c, as capture builds
 * route it through their sink above: the ring, COM1 when it answers, the screen with daphnis.console=screen.
 * HW-14: with daphnis.uart=0 cint's COM1 driver never reaches the port: its register writes are dropped, and a read
 * answers without the port, the line status as ready to send with nothing received, every other register 0. */
/* COM1's line control register as cint last wrote it, never read from the port: a board without a 16550 reads 0xFF
 * at 0x3FB, which would say DLAB is set and send cint's bytes to the empty port instead of the console. */
static uint8_t com1_lcr;
static bool com1_port(uint16_t port) { return port >= 0x3F8u && port <= 0x3FFu; }

static cint_status hf_port_out8(const cint_value *a, cint_value *r)
{
    uint16_t port = (uint16_t)a[0].as.u64;
    (void)r;
    if (port == 0x3FBu) com1_lcr = (uint8_t)a[1].as.u64;
    if (port == 0x3F8u && (com1_lcr & 0x80u) == 0u)
        rt_console_byte((uint8_t)a[1].as.u64);
    else if (!com1_port(port) || !rt_console_uart_off())
        port_out8(port, (uint8_t)a[1].as.u64);
    return CINT_OK;
}
static cint_status hf_port_in8(const cint_value *a, cint_value *r)
{
    uint16_t port = (uint16_t)a[0].as.u64;
    if (com1_port(port) && rt_console_uart_off()) r->as.u64 = port == 0x3FDu ? 0x60u : 0u;
    else r->as.u64 = port_in8(port);
    return CINT_OK;
}
/* N-1 (src/portwide.ci): the PCI configuration ports and the legacy virtio registers */
ROW(hf_port_out16, port_out16((uint16_t)a[0].as.u64, (uint16_t)a[1].as.u64))
ROW(hf_port_in16, r->as.u64 = port_in16((uint16_t)a[0].as.u64))
ROW(hf_port_out32, port_out32((uint16_t)a[0].as.u64, (uint32_t)a[1].as.u64))
ROW(hf_port_in32, r->as.u64 = port_in32((uint16_t)a[0].as.u64))
#endif
ROW(hf_trap_stub, r->as.u64 = rt_trap_stub((uint64_t)a[0].as.i64))
ROW(hf_idt_set, rt_idt_set((uint64_t)a[0].as.i64, a[1].as.u64, a[2].as.u64))
ROW(hf_idt_load, rt_idt_load())
ROW(hf_gdt_set, rt_gdt_set((uint64_t)a[0].as.i64, a[1].as.u64, a[2].as.u64))
ROW(hf_tss_base, r->as.u64 = rt_tss_base())
ROW(hf_tss_set_ist, rt_tss_set_ist((uint64_t)a[0].as.i64, a[1].as.u64))
ROW(hf_ist_top, r->as.u64 = rt_ist_top((uint64_t)a[0].as.i64))
ROW(hf_tss_load, rt_tss_load())
ROW(hf_probe_de, rt_probe(trap_probe_de, 0u, 0u))
ROW(hf_probe_ud, rt_probe(trap_probe_ud, 0u, 0u))
static cint_status vm_probe(uint64_t (*fn)(uint64_t, uint64_t), uint64_t addr, uint64_t b, cint_value *r)
{
    /* the probes dereference an integer: only the null page (a #PF by design) and the virtual
     * region src/paging.ci manages may be named, never the identity-mapped kernel */
    if (!(addr < 0x1000u || (addr >= 0x40000000u && addr < 0x80000000u))) return CINT_REFUSED;
    if (r != NULL) r->as.u64 = rt_probe(fn, addr, b);
    else (void)rt_probe(fn, addr, b);
    return CINT_OK;
}
#define VMROW(fname, fn, a1, with_result)                                          \
    static cint_status fname(const cint_value *a, cint_value *r)                   \
    {                                                                              \
        (void)a;                                                                   \
        return vm_probe(fn, a[0].as.u64, (a1), (with_result) ? r : NULL);          \
    }
VMROW(hf_probe_pf, trap_probe_pf, 0u, 0)
ROW(hf_probe_nmi, rt_probe(trap_probe_nmi, 0u, 0u))
ROW(hf_probe_stack, rt_probe(trap_probe_stack, 0u, 0u))
VMROW(hf_vm_store64, trap_probe_store, a[1].as.u64, 0)
VMROW(hf_vm_exec, trap_probe_exec, 0u, 0)
VMROW(hf_vm_load64, trap_probe_load, 0u, 1)
ROW(hf_vm_invlpg, vm_invlpg(a[0].as.u64))
ROW(hf_mb_info, r->as.u64 = mb_info)
/* RG-1: -3, the tags the kernel reads do not fit the reader's buffer: halt, never run half configured */
ROW(hf_boot_info, r->as.i64 = rt_boot_info(a[0].as.view.mem.u.host.ptr, a[0].as.view.shape[0]);
    if (r->as.i64 == -3) rt_panic("loader block: the tags the kernel reads do not fit a reader's buffer"))
ROW(hf_vm_root, r->as.u64 = cr3_read())
ROW(hf_poweroff_set, rt_poweroff_set(a[0].as.u64, a[1].as.u64, a[2].as.u64, a[3].as.u64)) /* HW-2 (src/acpi.ci) */
ROW(hf_poweroff_acpi, rt_poweroff_acpi(a[0].as.u64, a[1].as.u64)) /* HW-2: SMI_CMD, ACPI_ENABLE */
ROW(hf_poweroff_events, rt_poweroff_events(a[0].as.u64, a[1].as.u64, a[2].as.u64)) /* HW-2: PM1 event blocks */
ROW(hf_poweroff_gpe, rt_poweroff_gpe(a[0].as.u64, a[1].as.u64, a[2].as.u64, a[3].as.u64)) /* HW-2: GPE blocks */
ROW(hf_boot_cmdline, r->as.i64 = (int64_t)rt_boot_cmdline((char *)a[0].as.view.mem.u.host.ptr, (size_t)a[0].as.view.shape[0])) /* G-5, every flavor since M-3 (src/bootarg.ci) */
ROW(hf_boot_net, r->as.i64 = (int64_t)rt_boot_net((char *)a[0].as.view.mem.u.host.ptr, (size_t)a[0].as.view.shape[0])) /* NW-5 (src/bootarg.ci): daphnis.net=... */
ROW(hf_pool_window, r->as.i64 = rt_phys_pool_window(a[0].as.u64)) /* M-3 (src/pool.ci) */
ROW(hf_pool_floor, r->as.u64 = rt_boot_pool_floor()) /* AU-5 (src/pool.ci): the play image past 32 MiB */
#ifdef RT_USER /* ring 3 (U1-1, rt/user.c): only the user image has it */
ROW(hf_user_init, rt_user_init())
static cint_status hf_user_setup(const cint_value *a, cint_value *r) { (void)r; return rt_user_setup(a[0].as.i64, a[1].as.u64, a[2].as.u64); }
ROW(hf_user_enter, r->as.i64 = rt_user_enter(a[0].as.i64, a[1].as.u64))
ROW(hf_user_reg, r->as.u64 = rt_user_reg(a[0].as.i64, a[1].as.i64))
static cint_status hf_user_set_reg(const cint_value *a, cint_value *r) { (void)r; return rt_user_set_reg(a[0].as.i64, a[1].as.i64, a[2].as.u64); }
static cint_status hf_user_copy(const cint_value *a, cint_value *r) { (void)r; return rt_user_copy(a[0].as.i64, a[1].as.i64); }
ROW(hf_user_fx, r->as.u64 = rt_user_fx(a[0].as.i64, a[1].as.i64))
static cint_status hf_user_set_fx(const cint_value *a, cint_value *r) { (void)r; return rt_user_set_fx(a[0].as.i64, a[1].as.i64, a[2].as.u64); }
ROW(hf_initrd_size, r->as.i64 = rt_initrd_size())
ROW(hf_initrd_read, r->as.i64 = rt_initrd_read(a[0].as.i64, a[1].as.view.mem.u.host.ptr, a[1].as.view.shape[0]))
#ifdef RT_CAPTURE
static bool journal_view(const cint_arg_view *v)
{
    int64_t n = v->shape[0], stride = v->byte_stride[0];
    if (v->mem.kind != CINT_MEM_HOST || n < 0 || n > 4096 || stride == INT64_MIN) return false;
    if (n == 0) return true;
    uint64_t step = (uint64_t)(stride < 0 ? -stride : stride);
    if (!v->mem.u.host.ptr || v->reachable_bytes < 1 ||
        (n > 1 && step > ((uint64_t)v->reachable_bytes - 1u) / (uint64_t)(n - 1))) return false;
    uint64_t span = (uint64_t)(n - 1) * step;
    uintptr_t address = (uintptr_t)v->mem.u.host.ptr;
    return stride < 0 ? span <= address : span <= UINTPTR_MAX - address;
}
static void journal_wipe(uint8_t *p, size_t n)
{
    volatile uint8_t *q = p;
    while (n--) *q++ = 0u;
}
static cint_status hf_journal_record(const cint_value *a, cint_value *r)
{
    const cint_arg_view *v = &a[1].as.view;
    uint8_t bytes[4096];
    (void)r;
    if ((a[0].as.i64 != 1 && a[0].as.i64 != 2) || !journal_view(v)) return CINT_REFUSED;
    const uint8_t *p = v->mem.u.host.ptr;
    for (int64_t i = 0; i < v->shape[0]; i++) bytes[i] = p[i * v->byte_stride[0]];
    rt_journal_record(a[0].as.i64, bytes, (size_t)v->shape[0]);
    journal_wipe(bytes, (size_t)v->shape[0]);
    return CINT_OK;
}
ROW(hf_journal_size, r->as.i64 = rt_journal_size(a[0].as.i64))
static cint_status hf_journal_read(const cint_value *a, cint_value *r)
{
    const cint_arg_view *v = &a[2].as.view;
    uint8_t bytes[4096];
    if ((a[0].as.i64 != 1 && a[0].as.i64 != 2) || a[1].as.i64 < 0 || !journal_view(v)) return CINT_REFUSED;
    int64_t n = rt_journal_read(a[0].as.i64, a[1].as.i64, bytes, (size_t)v->shape[0]);
    if (n < 0 || n > v->shape[0]) { journal_wipe(bytes, (size_t)v->shape[0]); return CINT_REFUSED; }
    uint8_t *p = v->mem.u.host.ptr;
    for (int64_t i = 0; i < n; i++) p[i * v->byte_stride[0]] = bytes[i];
    journal_wipe(bytes, (size_t)n);
    r->as.i64 = n;
    return CINT_OK;
}
#else
ROW(hf_journal_record, (void)0)
ROW(hf_journal_size, r->as.i64 = -1)
ROW(hf_journal_read, r->as.i64 = -1)
#endif
ROW(hf_fb_init, r->as.i64 = rt_fb_init())
ROW(hf_fb_prepare, r->as.i64 = rt_fb_prepare())
ROW(hf_fb_need, r->as.i64 = rt_fb_need())
ROW(hf_fb_backing_add, r->as.i64 = rt_fb_backing_add(a[0].as.u64, a[1].as.i64))
ROW(hf_fb_mode_need, r->as.i64 = rt_fb_mode_need(a[0].as.u64, a[1].as.u64))
ROW(hf_fb_page, r->as.u64 = rt_fb_page(a[0].as.u64))
ROW(hf_fb_present, rt_fb_present_pending())
ROW(hf_fb_word, r->as.u64 = rt_fb_word(a[0].as.i64))
ROW(hf_fb_mode, r->as.i64 = rt_fb_mode(a[0].as.u64, a[1].as.u64))
ROW(hf_fb_get, r->as.i64 = rt_fb_get(a[0].as.u64, a[1].as.view.mem.u.host.ptr, a[1].as.view.shape[0]))
static cint_status hf_fb_put(const cint_value *a, cint_value *r)
{
    (void)r;
    return rt_fb_put(a[0].as.u64, (const uint8_t *)a[1].as.view.mem.u.host.ptr, a[1].as.view.shape[0], a[1].as.view.byte_stride[0]);
}
static cint_status hf_px_spread(const cint_value *a, cint_value *r)
{
    (void)r;
    return rt_px_spread(a[0].as.view.mem.u.host.ptr, a[0].as.view.shape[0], a[1].as.i64, a[2].as.i64, a[3].as.i64);
}
/* AU-1 (src/mmio.ci, rt/mmio.c): device registers inside a window rt_mmio_map opened; anything else is refused */
ROW(hf_mmio_map, r->as.i64 = rt_mmio_map(a[0].as.u64, a[1].as.u64))
static cint_status hf_mmio_in8(const cint_value *a, cint_value *r) { return rt_mmio_in(a[0].as.u64, 1u, &r->as.u64); }
static cint_status hf_mmio_in16(const cint_value *a, cint_value *r) { return rt_mmio_in(a[0].as.u64, 2u, &r->as.u64); }
static cint_status hf_mmio_in32(const cint_value *a, cint_value *r) { return rt_mmio_in(a[0].as.u64, 4u, &r->as.u64); }
static cint_status hf_mmio_out8(const cint_value *a, cint_value *r) { (void)r; return rt_mmio_out(a[0].as.u64, 1u, a[1].as.u64); }
static cint_status hf_mmio_out16(const cint_value *a, cint_value *r) { (void)r; return rt_mmio_out(a[0].as.u64, 2u, a[1].as.u64); }
static cint_status hf_mmio_out32(const cint_value *a, cint_value *r) { (void)r; return rt_mmio_out(a[0].as.u64, 4u, a[1].as.u64); }
ROW(hf_ps2_init, r->as.i64 = rt_ps2_init())
ROW(hf_ps2_absent, rt_ps2_absent()) /* HW-3 (src/acpi.ci): the FADT says no 8042 */
ROW(hf_ps2_get, r->as.i64 = rt_ps2_get(a[0].as.i64))
ROW(hf_ps2_dropped, r->as.i64 = rt_ps2_dropped())
ROW(hf_ps2_stamp, r->as.i64 = rt_ps2_stamp())
ROW(hf_us_now, r->as.i64 = rt_us_now())
/* A-3 (src/rng.ci): the CPU's random source. rdrand_fill fills the view a word at a time, each word
 * tried ten times (the vendor's advice for a transient underflow); the bytes filled, -1 without RDRAND,
 * -2 when a word failed ten times. */
static int64_t rt_rdrand_fill(uint8_t *dst, uint64_t n)
{
    if (cpu_rdrand_present() == 0u) return -1;
    for (uint64_t at = 0u; at < n; at += 8u) {
        uint64_t w = 0u, ok = 0u;
        for (int k = 0; k < 10 && ok == 0u; k++) ok = cpu_rdrand64(&w);
        if (ok == 0u) return -2;
        for (uint64_t b = 0u; b < 8u && at + b < n; b++) dst[at + b] = (uint8_t)(w >> (8u * b));
    }
    return (int64_t)n;
}
ROW(hf_rdrand_present, r->as.i64 = (int64_t)cpu_rdrand_present())
ROW(hf_rdrand_fill, r->as.i64 = rt_rdrand_fill((uint8_t *)a[0].as.view.mem.u.host.ptr, (uint64_t)a[0].as.view.shape[0]))
/* KF-3a (docs/specs/2026-11-11-kf-facts.md section 2, src/proc.ci sys_facts): the processor's brand string, the 48
 * bytes of CPUID leaves 0x80000002 to 0x80000004 (EAX, EBX, ECX, EDX of each, low byte first), into a view of at least
 * 48 bytes: 48, 0 with the view zeroed when the CPU has no brand leaves, -1 for a shorter view. */
static int64_t rt_cpu_brand(uint8_t *dst, uint64_t n)
{
    uint32_t r4[4];
    if (n < 48u) return -1;
    for (uint64_t i = 0u; i < 48u; i++) dst[i] = 0u;
    cpu_cpuid(0x80000000u, r4);
    if (r4[0] < 0x80000004u) return 0;
    for (uint32_t leaf = 0u; leaf < 3u; leaf++) {
        cpu_cpuid(0x80000002u + leaf, r4);
        for (uint32_t w = 0u; w < 4u; w++)
            for (uint32_t b = 0u; b < 4u; b++) dst[16u * leaf + 4u * w + b] = (uint8_t)(r4[w] >> (8u * b));
    }
    return 48;
}
ROW(hf_cpu_brand, r->as.i64 = rt_cpu_brand((uint8_t *)a[0].as.view.mem.u.host.ptr, (uint64_t)a[0].as.view.shape[0]))
/* KF-3a, spec edition 4 (design note 59): the processor's base speed in MHz, CPUID leaf 0x16 EAX bits 15 to 0; 0 when
 * the CPU's highest basic leaf is below 0x16 (QEMU's TCG among them) or the leaf reports none. */
static int64_t rt_cpu_mhz(void)
{
    uint32_t r4[4];
    cpu_cpuid(0u, r4);
    if (r4[0] < 0x16u) return 0;
    cpu_cpuid(0x16u, r4);
    return (int64_t)(r4[0] & 0xFFFFu);
}
ROW(hf_cpu_mhz, r->as.i64 = rt_cpu_mhz())
#endif
ROW(hf_record_len, r->as.i64 = rt_trap_record_len())
ROW(hf_record_byte, r->as.u64 = rt_trap_record_byte(a[0].as.i64))
#ifdef RT_USER
/* All processes may be blocked after their last framebuffer write. cpu_wait_irq
 * returns on the kernel CR3 with interrupts disabled; drain the same tick budget
 * here as on a user-mode interrupt return, including any previous remainder. */
ROW(hf_wait_irq, cpu_wait_irq(); rt_fb_timer_present())
#else
ROW(hf_wait_irq, cpu_wait_irq())
#endif
ROW(hf_timer_ticks, r->as.i64 = rt_timer_ticks())

#ifndef RT_TASK_MODE
#define RT_TASK_MODE 0
#endif
ROW(hf_task_mode, r->as.i64 = RT_TASK_MODE)
ROW(hf_task_create, r->as.i64 = rt_task_create(a[0].as.i64, a[1].as.i64))
ROW(hf_task_run, r->as.i64 = rt_task_run(a[0].as.i64))
ROW(hf_task_yield, rt_task_yield())
ROW(hf_task_preempt_on, rt_task_preempt_enable(a[0].as.i64))
ROW(hf_task_preemptions, r->as.i64 = rt_task_preemptions())
ROW(hf_task_out_len, r->as.i64 = rt_task_out_len(a[0].as.i64))
ROW(hf_task_out_byte, r->as.u64 = rt_task_out_byte(a[0].as.i64, a[1].as.i64))

/* K4.5: the fuel quantum, channels and the event log. A refusal is a status the caller turns
 * into the record host.error.<name> (RT-OQ-70). */
ROW(hf_task_quantum, rt_task_quantum_set(a[0].as.i64))
ROW(hf_chan_close, rt_chan_close(a[0].as.i64))
ROW(hf_task_budget, rt_task_stack_budget(a[0].as.i64))
ROW(hf_task_guard, r->as.u64 = rt_task_guard(a[0].as.i64))
ROW(hf_task_net, rt_task_net_set(a[0].as.i64))
ROW(hf_task_fuel, r->as.i64 = rt_task_fuel(a[0].as.i64))
ROW(hf_log_len, r->as.i64 = rt_task_log_len(a[0].as.i64))
ROW(hf_log_kind, r->as.i64 = rt_task_log_kind(a[0].as.i64, a[1].as.i64))
ROW(hf_log_val, r->as.i64 = rt_task_log_val(a[0].as.i64, a[1].as.i64))
ROW(hf_chan_open, r->as.i64 = rt_chan_open(a[0].as.i64, a[1].as.i64, a[2].as.i64))
static cint_status hf_emit(const cint_value *a, cint_value *r) { (void)r; return rt_task_emit(a[0].as.i64, a[1].as.i64); }
static cint_status hf_chan_send(const cint_value *a, cint_value *r) { (void)r; return rt_chan_send(a[0].as.i64, a[1].as.i64); }
static cint_status hf_chan_recv(const cint_value *a, cint_value *r) { return rt_chan_recv(a[0].as.i64, &r->as.i64); }
static cint_status hf_chan_recv_any(const cint_value *a, cint_value *r) { return rt_chan_recv_any(a[0].as.i64, a[1].as.i64, &r->as.i64); }

/* K5: the step interface. Task side: request, page_load, page_store. Kernel side: the rest. */
static cint_status hf_request(const cint_value *a, cint_value *r) { (void)r; return rt_task_request(a[0].as.i64, a[1].as.i64, a[2].as.i64, a[3].as.i64); }
static cint_status hf_page_load(const cint_value *a, cint_value *r) { return rt_page_op(a[0].as.i64, a[1].as.i64, false, 0, &r->as.i64); }
static cint_status hf_page_store(const cint_value *a, cint_value *r) { (void)r; return rt_page_op(a[0].as.i64, a[1].as.i64, true, a[2].as.i64, NULL); }
ROW(hf_task_step, r->as.i64 = rt_task_step(a[0].as.i64))
ROW(hf_task_req, r->as.i64 = rt_task_req(a[0].as.i64, a[1].as.i64))
ROW(hf_task_args_set, rt_task_args_set(a[0].as.i64, a[1].as.view.mem.u.host.ptr, a[1].as.view.shape[0]))
ROW(hf_fuel_total, r->as.i64 = rt_task_fuel_total(a[0].as.i64))
ROW(hf_fuel_set, rt_task_fuel_set(a[0].as.i64, a[1].as.i64))
static cint_status hf_task_space(const cint_value *a, cint_value *r) { (void)r; return rt_task_space(a[0].as.i64, a[1].as.i64); }
ROW(hf_state_size, r->as.i64 = rt_state_size(a[0].as.i64))
ROW(hf_state_read, r->as.i64 = rt_state_read(a[0].as.i64, a[1].as.i64, a[2].as.view.mem.u.host.ptr, a[2].as.view.shape[0]))
ROW(hf_state_stage, rt_state_stage(a[0].as.i64, a[1].as.view.mem.u.host.ptr, a[1].as.view.shape[0]))
ROW(hf_state_apply, r->as.i64 = rt_state_apply(a[0].as.i64, a[1].as.i64))
ROW(hf_wx_probe, r->as.i64 = rt_wx_probe(a[0].as.i64))
ROW(hf_rev_byte, r->as.u64 = rt_rev_byte(a[0].as.i64))

/* The console/1 service rows (lib/console.ci). Error alternatives of console.ConsoleError:
 * denied 1, closed 2, unavailable 3. console.input is capability bit 1, console.raw bit 2. */
#define CAP_INPUT 1u
#define CAP_RAW 2u
static cint_status svc_error(cint_value *r, int64_t tag)
{
    r->is_error = 1u;
    r->error = tag;
    return CINT_OK;
}
static cint_status hf_console_raw(const cint_value *a, cint_value *r)
{
    (void)a;
    return rt_task_covered(CAP_RAW) ? CINT_OK : svc_error(r, 1);
}
static cint_status hf_console_read(const cint_value *a, cint_value *r)
{
    (void)a;
    if (!rt_task_covered(CAP_INPUT)) return svc_error(r, 1);
    r->as.i64 = 0; /* nothing arrived within the wait: the kernel has no input device yet */
    return CINT_OK;
}
static cint_status hf_console_window(const cint_value *a, cint_value *r)
{
    (void)a;
    if (!rt_task_covered(CAP_INPUT)) return svc_error(r, 1);
    r->as.i64 = ((int64_t)25 << 32) | 80;
    return CINT_OK;
}
static cint_status hf_console_read_line(const cint_value *a, cint_value *r)
{
    static const char line[] = "daphnis"; /* the kernel's one canned input line, without its line end */
    int64_t n = a[1].as.view.shape[0], i;
    uint8_t *dst = a[1].as.view.mem.u.host.ptr;
    if (!rt_task_covered(CAP_INPUT)) return svc_error(r, 1);
    if (n > 7) n = 7;
    for (i = 0; i < n; i++) dst[i] = (uint8_t)line[i];
    r->as.i64 = n;
    return CINT_OK;
}
static cint_status hf_console_write(const cint_value *a, cint_value *r)
{
    if (rt_task_write(a[1].as.view.mem.u.host.ptr, a[1].as.view.shape[0]) != CINT_OK) return svc_error(r, 2);
    return CINT_OK;
}

static cint_status view_copy(const cint_value *a, bool to_phys, unsigned width)
{
    return rt_phys_copy(to_phys, a[0].as.u64, a[1].as.view.mem.u.host.ptr, a[1].as.view.shape[0], a[1].as.view.byte_stride[0], width);
}
static cint_status hf_phys_read8(const cint_value *a, cint_value *r) { (void)r; return view_copy(a, false, 1u); }
static cint_status hf_phys_write8(const cint_value *a, cint_value *r) { (void)r; return view_copy(a, true, 1u); }
static cint_status hf_phys_read64(const cint_value *a, cint_value *r) { (void)r; return view_copy(a, false, 8u); }
static cint_status hf_phys_write64(const cint_value *a, cint_value *r) { (void)r; return view_copy(a, true, 8u); }

/* What a task may call (K4.5): the console service, its channels and event log, the yield, and
 * its own stack-overflow probe. Every other row is the kernel's; a task that calls one is refused,
 * with the record host.error.<name> and status 2, whatever the schedule. This is what makes it
 * true that a task shares nothing with the others but the channels and the logs. */
static bool task_allowed(const char *name)
{
    static const char *const ok[] = {"task_mode", "task_yield", "console/1.raw", "console/1.read", "console/1.write", "console/1.window",
                                     "console/1.read_line", "request", "page_load", "page_store", "chan_send", "chan_recv", "chan_recv_any", "emit", "trap_probe_stack",
                                     "trap_record_len", "trap_record_byte"};
    unsigned i;
    for (i = 0u; i < sizeof ok / sizeof ok[0]; i++) {
        const char *a = ok[i], *b = name;
        while (*a != '\0' && *a == *b) a++, b++;
        if (*a == '\0' && *b == '\0') return true;
    }
    return false;
}

static const host_entry host_table[] = {
    {"port_out8", 2u, {U16_, U8_}, 0u, hf_port_out8},
    {"port_in8", 1u, {U16_}, U8_, hf_port_in8},
    {"port_out16", 2u, {U16_, U16_}, 0u, hf_port_out16},
    {"port_in16", 1u, {U16_}, U16_, hf_port_in16},
    {"port_out32", 2u, {U16_, U32_}, 0u, hf_port_out32},
    {"port_in32", 1u, {U16_}, U32_, hf_port_in32},
    {"trap_stub", 1u, {I64_}, U64_, hf_trap_stub},
    {"idt_set", 3u, {I64_, U64_, U64_}, 0u, hf_idt_set},
    {"idt_load", 0u, {0}, 0u, hf_idt_load},
    {"gdt_set", 3u, {I64_, U64_, U64_}, 0u, hf_gdt_set},
    {"tss_base", 0u, {0}, U64_, hf_tss_base},
    {"tss_set_ist", 2u, {I64_, U64_}, 0u, hf_tss_set_ist},
    {"ist_top", 1u, {I64_}, U64_, hf_ist_top},
    {"tss_load", 0u, {0}, 0u, hf_tss_load},
    {"trap_probe_de", 0u, {0}, 0u, hf_probe_de},
    {"trap_probe_ud", 0u, {0}, 0u, hf_probe_ud},
    {"trap_probe_pf", 1u, {U64_}, 0u, hf_probe_pf},
    {"trap_probe_nmi", 0u, {0}, 0u, hf_probe_nmi},
    {"trap_probe_stack", 0u, {0}, 0u, hf_probe_stack},
    {"vm_load64", 1u, {U64_}, U64_, hf_vm_load64},
    {"vm_store64", 2u, {U64_, U64_}, 0u, hf_vm_store64},
    {"vm_exec", 1u, {U64_}, 0u, hf_vm_exec},
    {"vm_invlpg", 1u, {U64_}, 0u, hf_vm_invlpg},
    {"vm_root", 0u, {0}, U64_, hf_vm_root},
#ifdef RT_USER
    {"user_init", 0u, {0}, 0u, hf_user_init},
    {"user_setup", 3u, {I64_, U64_, U64_}, 0u, hf_user_setup},
    {"user_enter", 2u, {I64_, U64_}, I64_, hf_user_enter},
    {"user_reg", 2u, {I64_, I64_}, U64_, hf_user_reg},
    {"user_set_reg", 3u, {I64_, I64_, U64_}, 0u, hf_user_set_reg},
    {"user_copy", 2u, {I64_, I64_}, 0u, hf_user_copy},
    {"user_fx", 2u, {I64_, I64_}, U64_, hf_user_fx},
    {"user_set_fx", 3u, {I64_, I64_, U64_}, 0u, hf_user_set_fx},
    {"initrd_size", 0u, {0}, I64_, hf_initrd_size},
    {"initrd_read", 2u, {I64_, U8_ | VIEW_OUT}, I64_, hf_initrd_read},
    {"journal_record", 2u, {I64_, U8_ | VIEW_IN}, 0u, hf_journal_record},
    {"journal_size", 1u, {I64_}, I64_, hf_journal_size},
    {"journal_read", 3u, {I64_, I64_, U8_ | VIEW_OUT}, I64_, hf_journal_read},
    {"fb_prepare", 0u, {0}, I64_, hf_fb_prepare},
    {"fb_need", 0u, {0}, I64_, hf_fb_need},
    {"fb_finish", 0u, {0}, I64_, hf_fb_init},
    {"fb_backing_add", 2u, {U64_, I64_}, I64_, hf_fb_backing_add},
    {"fb_mode_need", 2u, {U64_, U64_}, I64_, hf_fb_mode_need},
    {"fb_page", 1u, {U64_}, U64_, hf_fb_page},
    {"fb_present", 0u, {0}, 0u, hf_fb_present},
    {"fb_word", 1u, {I64_}, U64_, hf_fb_word},
    {"fb_mode_commit", 2u, {U64_, U64_}, I64_, hf_fb_mode},
    {"fb_put", 2u, {U64_, U8_ | VIEW_IN}, 0u, hf_fb_put},
    {"fb_get", 2u, {U64_, U8_ | VIEW_OUT}, I64_, hf_fb_get},
    {"px_spread", 4u, {U8_ | VIEW_OUT, I64_, I64_, I64_}, 0u, hf_px_spread},
    {"mmio_map", 2u, {U64_, U64_}, I64_, hf_mmio_map},
    {"mmio_in8", 1u, {U64_}, U8_, hf_mmio_in8},
    {"mmio_in16", 1u, {U64_}, U16_, hf_mmio_in16},
    {"mmio_in32", 1u, {U64_}, U32_, hf_mmio_in32},
    {"mmio_out8", 2u, {U64_, U8_}, 0u, hf_mmio_out8},
    {"mmio_out16", 2u, {U64_, U16_}, 0u, hf_mmio_out16},
    {"mmio_out32", 2u, {U64_, U32_}, 0u, hf_mmio_out32},
    {"ps2_init", 0u, {0}, I64_, hf_ps2_init},
    {"ps2_absent", 0u, {0}, 0u, hf_ps2_absent},
    {"ps2_get", 1u, {I64_}, I64_, hf_ps2_get},
    {"ps2_dropped", 0u, {0}, I64_, hf_ps2_dropped},
    {"ps2_stamp", 0u, {0}, I64_, hf_ps2_stamp},
    {"us_now", 0u, {0}, I64_, hf_us_now},
    {"rdrand_present", 0u, {0}, I64_, hf_rdrand_present},
    {"rdrand_fill", 1u, {U8_ | VIEW_OUT}, I64_, hf_rdrand_fill},
    {"cpu_brand", 1u, {U8_ | VIEW_OUT}, I64_, hf_cpu_brand},
    {"cpu_mhz", 0u, {0}, I64_, hf_cpu_mhz},
#endif
    {"mb_info", 0u, {0}, U64_, hf_mb_info},
    {"boot_info", 1u, {U8_ | VIEW_OUT}, I64_, hf_boot_info},
    {"boot_cmdline", 1u, {U8_ | VIEW_OUT}, I64_, hf_boot_cmdline},
    {"boot_net", 1u, {U8_ | VIEW_OUT}, I64_, hf_boot_net},
    {"poweroff_set", 4u, {U64_, U64_, U64_, U64_}, 0u, hf_poweroff_set},
    {"poweroff_acpi", 2u, {U64_, U64_}, 0u, hf_poweroff_acpi},
    {"poweroff_events", 3u, {U64_, U64_, U64_}, 0u, hf_poweroff_events},
    {"poweroff_gpe", 4u, {U64_, U64_, U64_, U64_}, 0u, hf_poweroff_gpe},
    {"pool_window", 1u, {U64_}, I64_, hf_pool_window},
    {"pool_floor", 0u, {0}, U64_, hf_pool_floor},
    {"phys_read8", 2u, {U64_, U8_ | VIEW_OUT}, 0u, hf_phys_read8},
    {"phys_write8", 2u, {U64_, U8_ | VIEW_IN}, 0u, hf_phys_write8},
    {"phys_read64", 2u, {U64_, U64_ | VIEW_OUT}, 0u, hf_phys_read64},
    {"phys_write64", 2u, {U64_, U64_ | VIEW_IN}, 0u, hf_phys_write64},
    {"task_mode", 0u, {0}, I64_, hf_task_mode},
    {"task_create", 2u, {I64_, I64_}, I64_, hf_task_create},
    {"task_run", 1u, {I64_}, I64_, hf_task_run},
    {"task_yield", 0u, {0}, 0u, hf_task_yield},
    {"task_preempt_on", 1u, {I64_}, 0u, hf_task_preempt_on},
    {"task_preemptions", 0u, {0}, I64_, hf_task_preemptions},
    {"task_out_len", 1u, {I64_}, I64_, hf_task_out_len},
    {"task_out_byte", 2u, {I64_, I64_}, U8_, hf_task_out_byte},
    {"task_quantum", 1u, {I64_}, 0u, hf_task_quantum},
    {"task_net", 1u, {I64_}, 0u, hf_task_net},
    {"task_guard", 1u, {I64_}, U64_, hf_task_guard},
    {"chan_close", 1u, {I64_}, 0u, hf_chan_close},
    {"task_stack_budget", 1u, {I64_}, 0u, hf_task_budget},
    {"task_fuel", 1u, {I64_}, I64_, hf_task_fuel},
    {"log_len", 1u, {I64_}, I64_, hf_log_len},
    {"log_kind", 2u, {I64_, I64_}, I64_, hf_log_kind},
    {"log_val", 2u, {I64_, I64_}, I64_, hf_log_val},
    {"chan_open", 3u, {I64_, I64_, I64_}, I64_, hf_chan_open},
    {"emit", 2u, {I64_, I64_}, 0u, hf_emit},
    {"chan_send", 2u, {I64_, I64_}, 0u, hf_chan_send},
    {"chan_recv", 1u, {I64_}, I64_, hf_chan_recv},
    {"chan_recv_any", 2u, {I64_, I64_}, I64_, hf_chan_recv_any},
    {"request", 4u, {I64_, I64_, I64_, I64_}, 0u, hf_request},
    {"page_load", 2u, {I64_, I64_}, I64_, hf_page_load},
    {"page_store", 3u, {I64_, I64_, I64_}, 0u, hf_page_store},
    {"task_step", 1u, {I64_}, I64_, hf_task_step},
    {"task_req", 2u, {I64_, I64_}, I64_, hf_task_req},
    {"task_args_set", 2u, {I64_, U8_ | VIEW_IN}, 0u, hf_task_args_set},
    {"task_fuel_total", 1u, {I64_}, I64_, hf_fuel_total},
    {"task_fuel_set", 2u, {I64_, I64_}, 0u, hf_fuel_set},
    {"task_space", 2u, {I64_, I64_}, 0u, hf_task_space},
    {"task_state_size", 1u, {I64_}, I64_, hf_state_size},
    {"task_state_read", 3u, {I64_, I64_, U8_ | VIEW_OUT}, I64_, hf_state_read},
    {"task_state_stage", 2u, {I64_, U8_ | VIEW_IN}, 0u, hf_state_stage},
    {"task_state_apply", 2u, {I64_, I64_}, I64_, hf_state_apply},
    {"rev_byte", 1u, {I64_}, U8_, hf_rev_byte},
    {"wx_probe", 1u, {I64_}, I64_, hf_wx_probe},
    {"console/1.raw", 2u, {I64_, CINT_TAG_BOOL}, 0u, hf_console_raw},
    {"console/1.read", 3u, {I64_, U8_ | VIEW_OUT, I64_}, I64_, hf_console_read},
    {"console/1.write", 2u, {I64_, U8_ | VIEW_IN}, 0u, hf_console_write},
    {"console/1.window", 1u, {I64_}, I64_, hf_console_window},
    {"console/1.read_line", 2u, {I64_, U8_ | VIEW_OUT}, I64_, hf_console_read_line},
    {"trap_record_len", 0u, {0}, I64_, hf_record_len},
    {"trap_record_byte", 1u, {I64_}, U8_, hf_record_byte},
    {"cpu_wait_irq", 0u, {0}, 0u, hf_wait_irq},
    {"timer_ticks", 0u, {0}, I64_, hf_timer_ticks},
};
#define HOST_ENTRIES (sizeof host_table / sizeof host_table[0])

#define HOST_MAX_ROWS 256u /* bound import rows over every module: the user flavor passed 128 at M-3 */

static const cint_host_desc *bound_imports;
static const host_entry *bound_rows[HOST_MAX_ROWS];
static uint32_t bound_base[HOST_MAX_ROWS];

static bool name_is(const cint_name *n, const char *s)
{
    uint32_t i;
    for (i = 0u; i < n->len; i++)
        if (s[i] == '\0' || s[i] != n->bytes[i]) return false;
    return s[n->len] == '\0';
}

bool rt_host_bind(const cint_program *program, const cint_host_desc *imports)
{
    uint32_t m, k, total = 0u;
    bound_imports = imports;
    if (imports == NULL) return true;
    if (imports->module_count != program->module_count || program->module_count > HOST_MAX_ROWS) return false;
    for (m = 0u; m < imports->module_count; m++) {
        const cint_host_table *t = imports->tables[m];
        bound_base[m] = total;
        if (t == NULL) continue;
        for (k = 0u; k < t->count; k++) {
            const cint_host_import *row = &t->imports[k];
            unsigned e;
            const host_entry *found = NULL;
            for (e = 0u; e < HOST_ENTRIES; e++)
                if (name_is(&row->name, host_table[e].name) && row->param_count == host_table[e].nparams) found = &host_table[e];
            if (found == NULL || total >= HOST_MAX_ROWS) return false;
            bound_rows[total++] = found;
        }
    }
    return true;
}

bool cint_rt_host_call(cint_ctx *ctx, cint_site site, uint32_t k, cint_value *args, uint32_t nargs, cint_value *result,
                       uint32_t error_count)
{
    const cint_host_table *t;
    const host_entry *e;
    uint32_t i;
    cint_status st;
    (void)error_count;
    if (ctx->head.faulted != 0u) return false;
    if (bound_imports == NULL || site.module >= bound_imports->module_count || (t = bound_imports->tables[site.module]) == NULL ||
        k >= t->count || nargs != t->imports[k].param_count || result == NULL)
        return rt_fault_host(ctx, site, "host.call", false, 0);
    e = bound_rows[bound_base[site.module] + k];
    for (i = 0u; i < nargs; i++) {
        uint16_t want = e->params[i];
        if ((want & (VIEW_IN | VIEW_OUT)) != 0u) {
            uint8_t perm = (want & VIEW_OUT) != 0u ? CINT_VIEW_WRITE : CINT_VIEW_READ;
            if (args[i].kind != CINT_VAL_VIEW || args[i].type.code != (want & 0xFFu) || args[i].as.view.perm != perm ||
                args[i].as.view.rank != 1u)
                return rt_fault_host(ctx, site, "host.call", false, 0);
        } else if (args[i].kind != CINT_VAL_SCALAR || args[i].type.code != want) {
            return rt_fault_host(ctx, site, "host.call", false, 0);
        }
    }
    if (result->type.code != e->result) return rt_fault_host(ctx, site, "host.call", false, 0);
    rt_task_quantum_point(ctx);
    if (!cint_fuel_charge(ctx, site, 1u)) return false;
    ctx->host_site = site;
    st = rt_task_current() >= 0 && !task_allowed(e->name) ? CINT_REFUSED : e->fn(args, result);
    if (st == RT_ST_TRAP) return rt_trap_adopt(ctx) ? false : rt_fault_host(ctx, site, "host.call", false, 0);
    if (st != CINT_OK) {
        /* the shape the hosted runtime writes for a host function that does not return OK:
         * host.error.<name> with the status as one I64 operand (RT-OQ-70) */
        cint_fault_record *rec = rt_record_begin(ctx, site, (uint16_t)CINT_E_UNSUPPORTED);
        if (rec != NULL) {
            rt_record_op(rec, "host");
            rt_record_op(rec, "error");
            rt_record_op(rec, e->name);
            rt_record_operand(rec, CINT_TAG_I64, (uint64_t)(int64_t)st);
        }
        return false;
    }
    return true;
}
