/* rt/trap.c: the C side of arch/x86_64/trap.S. It stores the IDT that cint builds, turns a
 * deliberate CPU exception into a fault record and resumes, and counts PIT ticks. A trap
 * record is a cint fault record of an extension kind (docs/traps.md): code E_UNSUPPORTED,
 * operation host.error.trap_<name>, operands vector (I64), error code (U64), CR2 (U64),
 * position the site of the extern call that ran the probe, stack the context's. It never
 * holds RIP (stub addresses differ between a gcc and a clang link). The record is kept apart
 * from rt_ctx.fault, which belongs to real cint faults and is single-use. */
#include "rt.h"
#include "pic.h"

/* vectors 0 to 47: the exceptions, then the remapped PICs (src/idt.ci installs the same count) */
#define IDT_VECTORS 48u

extern const uint64_t trap_stub_table[IDT_VECTORS];
extern char trap_probes[], trap_resume[];
extern uint64_t gdt[];
extern char stack_guard[];
void idt_load(const void *idtr);
uint64_t cr2_read(void);
void tss_load(void);

#define IST_BYTES 16384u
#define PAGE_BYTES 4096u
#define GUARD_BYTES 8192u

/* The IST stack each exception uses once the TSS is loaded (0: none): #NMI 2, #DF 1, #PF 3. */
static unsigned ist_of(uint64_t vector)
{
    return vector == 8u ? 1u : vector == 2u ? 2u : vector == 14u ? 3u : 0u;
}

/* The 64-bit TSS (104 bytes used) and the three IST stacks. IST1 #DF, IST2 #NMI's gate, IST3 #PF. */
static uint8_t tss[128] __attribute__((aligned(16)));
/* each under a guard of two pages, not present once the TSS is loaded (see task.c) */
static struct {
    uint8_t guard[GUARD_BYTES];
    uint8_t mem[IST_BYTES];
} ist_stacks[3] __attribute__((aligned(4096)));
static bool tss_loaded;
volatile bool rt_probe_active; /* set by host.c around a probe */
uint64_t trap_probe_rsp;       /* the RSP a probe saved at entry (probe.S) */

static uint64_t idt[2u * IDT_VECTORS];
static struct {
    uint16_t limit;
    uint64_t base;
} __attribute__((packed)) idtr;

static cint_fault_record trap_rec;
static uint8_t trap_buf[2048];
static size_t trap_len;
static volatile uint64_t ticks;
static uint64_t last_error; /* the error code of the last trap a probe took */

uint64_t rt_trap_stub(uint64_t vector)
{
    return vector < IDT_VECTORS ? trap_stub_table[vector] : 0u;
}

void rt_idt_set(uint64_t vector, uint64_t lo, uint64_t hi)
{
    if (vector >= IDT_VECTORS) rt_panic("idt_set: vector out of range");
    idt[2u * vector] = lo;
    idt[2u * vector + 1u] = hi;
}

void rt_idt_load(void)
{
    idtr.limit = (uint16_t)(sizeof idt - 1u);
    idtr.base = (uint64_t)(uintptr_t)idt;
    idt_load(&idtr);
}

void rt_trap_reset(void)
{
    trap_len = 0u;
    trap_probe_rsp = 0u;
}

int64_t rt_trap_record_len(void)
{
    return (int64_t)trap_len;
}

uint8_t rt_trap_record_byte(int64_t i)
{
    return i >= 0 && (uint64_t)i < trap_len ? trap_buf[i] : 0u;
}

uint64_t rt_tss_base(void)
{
    return (uint64_t)(uintptr_t)tss;
}

uint64_t rt_ist_top(uint64_t n)
{
    return n >= 1u && n <= 3u ? (uint64_t)(uintptr_t)ist_stacks[n - 1u].mem + IST_BYTES : 0u;
}

/* TSS.ist[n - 1] is at byte 36 + 8 * (n - 1) of the 64-bit TSS (SDM vol. 3, 8.7): not a
 * multiple of 8, so it is stored bytewise. */
void rt_tss_set_ist(uint64_t n, uint64_t top)
{
    if (n < 1u || n > 7u) rt_panic("tss_set_ist: no such IST");
    memcpy(tss + 36u + 8u * (n - 1u), &top, 8u);
}

void rt_gdt_set(uint64_t slot, uint64_t lo, uint64_t hi)
{
    if (slot != 3u) rt_panic("gdt_set: only slot 3 (the TSS) is writable");
    gdt[3] = lo;
    gdt[4] = hi;
}

void rt_tss_load(void) /* ltr marks the descriptor busy: a second ltr would be a #GP, so once */
{
    unsigned i;
    if (tss_loaded) return;
    for (i = 0u; i < 3u; i++) rt_guard_pages(ist_stacks[i].guard, GUARD_BYTES / PAGE_BYTES);
    tss_load();
    tss_loaded = true;
}

/* A trap that a probe recorded becomes the running context's fault (the page access of K5): the
 * record is the one a probe would have returned, with the task's call stack and the call site. */
bool rt_trap_adopt(cint_ctx *ctx)
{
    if (trap_len == 0u || ctx->head.faulted != 0u) return false;
    memcpy(&ctx->fault, &trap_rec, sizeof ctx->fault);
    ctx->head.faulted = 1u;
    trap_len = 0u; /* the record is the task's fault now: another task must not read it with trap_record_len */
    return true;
}

uint64_t rt_trap_last_error(void)
{
    return last_error;
}

uint64_t rt_probe(uint64_t (*fn)(uint64_t, uint64_t), uint64_t a, uint64_t b)
{
    uint64_t v;
    if (rt_task_preemptible()) rt_panic("probe in a preemptible task"); /* trap_len, trap_probe_rsp are global */
    rt_trap_reset();
    rt_probe_active = true;
    v = fn(a, b);
    rt_probe_active = false;
    return trap_len == 0u ? v : 0u;
}

#ifdef RT_USER
/* K-12 (docs/specs/2026-11-07-ds-desk-speed.md section 4): microseconds since the PIT started, from the tick count
 * and channel 0's latched count (11,932 a tick, src/pit.ci USER_DIVISOR). A tick whose interrupt is still pending
 * (the PIC's request register, bit 0) is counted when the count shows the reload was recent (more than half a tick
 * left), as the i8253 clocks of old did: a pending request with the count near its end is the wrap that came after
 * the latch. The value never goes back. A tick lost while interrupts were off longer than a tick is lost here too
 * (under TCG a long kernel copy; the KVM run the bar is judged on keeps a copy inside half a tick, D-ROW). Only the
 * k12 lines read it; it never enters a digest. */
int64_t rt_us_now(void)
{
    static int64_t last;
    uint64_t t = ticks;
    unsigned lo, hi, c, irr;
    int64_t v;
    port_out8(0x43u, 0x00u);
    lo = port_in8(0x40u);
    hi = port_in8(0x40u);
    port_out8(0x20u, 0x0Au);
    irr = port_in8(0x20u);
    c = lo | (hi << 8);
    if (c > 11932u) c = 11932u;
    if ((irr & 1u) != 0u && c > 11932u / 2u) t++;
    v = (int64_t)(t * 10000u + (uint64_t)(11932u - c) * 10000u / 11932u);
    if (v < last) v = last;
    last = v;
    return v;
}
#endif

int64_t rt_timer_ticks(void)
{
    return (int64_t)ticks;
}

static void put_dec_line(const char *label, uint64_t v)
{
    rt_puts(label);
    rt_put_dec(v);
    rt_puts("\n");
}

static void trap_record(const struct rt_trap_frame *f, const char *name, uint64_t cr2, unsigned ist)
{
    const struct cint_ctx *c = rt_task_ctx();
    cint_fault_record *rec = &trap_rec;
    memset(rec, 0, sizeof *rec);
    rec->program = c->program;
    rec->code = (uint16_t)CINT_E_UNSUPPORTED;
    rec->position = c->host_site;
    if (c->program != NULL && c->program->revision != NULL) {
        rec->has_revision = 1u;
        memcpy(rec->revision, c->program->revision, sizeof rec->revision);
    }
    rec->stack_count = c->head.stack_count;
    memcpy(rec->stack, c->stack, (size_t)c->head.stack_count * sizeof c->stack[0]);
    rt_record_op(rec, "host");
    rt_record_op(rec, "error");
    rt_record_op(rec, name);
    rt_record_operand(rec, CINT_TAG_I64, f->vector);
    rt_record_operand(rec, CINT_TAG_U64, f->error);
    rt_record_operand(rec, CINT_TAG_U64, cr2);
    if (tss_loaded) rt_record_operand(rec, CINT_TAG_U64, ist); /* with a TSS: the IST stack the frame was on */
    trap_len = rt_fault_encode(rec, trap_buf, sizeof trap_buf, NULL);
}

/* TSS.rsp0 is at byte 4 (SDM vol. 3, 8.7): the stack the CPU loads on an interrupt from ring 3. */
void rt_tss_set_rsp0(uint64_t top)
{
    memcpy(tss + 4u, &top, 8u);
}

/* Vector 39 or 47 (rt/pic.h): the in-service registers read, both chips back to IRR; a spurious IRQ 15 gets the
 * master's EOI it owes for the cascade here, a spurious IRQ 7 nothing. In ring 0 or ring 3 alike (review on PR
 * 282: a cascade latched between cpu_wait_irq's cli and the mask can arrive as 47 after the iretq to ring 3). */
static int pic_low_line(unsigned vector)
{
    port_out8(0x20u, 0x0Bu);
    uint8_t isr_m = port_in8(0x20u);
    port_out8(0xA0u, 0x0Bu);
    uint8_t isr_s = port_in8(0xA0u);
    port_out8(0x20u, 0x0Au);
    port_out8(0xA0u, 0x0Au);
    int a = rt_pic_low_line(vector, isr_m, isr_s);
    if (a == RT_PIC_SPURIOUS_SLAVE) port_out8(0x20u, 0x20u);
    return a;
}

#ifdef RT_USER
/* A routed line (NW-1: virtio-net or e1000 INTx, or IRQ 7 or 15 found genuine) masked, so iretq cannot re-enter
 * before cli on the level-triggered line, then the PIC's EOI (the slave's too above IRQ 7). */
static void pic_mask_eoi(unsigned vector)
{
    if (vector >= 40u) {
        uint8_t m = (uint8_t)(port_in8(0xA1u) | (1u << (vector - 40u)));
        port_out8(0xA1u, m);
        if (m == 0xFFu) port_out8(0x21u, (uint8_t)(port_in8(0x21u) | 4u));
        port_out8(0xA0u, 0x20u);
    } else {
        port_out8(0x21u, (uint8_t)(port_in8(0x21u) | (1u << (vector - 32u))));
    }
    port_out8(0x20u, 0x20u);
}
#endif

void rt_trap_dispatch(struct rt_trap_frame *f)
{
    if (((uintptr_t)f & 15u) != 0u) rt_panic("trap frame");
#ifdef RT_USER
    if (f->cs == 0x33u) { /* from ring 3 (U1-1): a syscall (vector 256), an exception or an interrupt */
        if (f->vector == 32u) {
            ticks++;
            port_out8(0x20u, 0x20u);
        } else if (f->vector == 33u || f->vector == 44u) {
            rt_ps2_irq(); /* the keyboard or the mouse (F-2, F-3): one byte into its ring, then the turn ends as a tick does */
            if (f->vector == 44u) port_out8(0xA0u, 0x20u);
            port_out8(0x20u, 0x20u);
        } else if (f->vector == 39u || f->vector == 47u) {
            if (pic_low_line(f->vector) == RT_PIC_GENUINE) pic_mask_eoi(f->vector); /* a routed line, masked */
        }
        rt_user_trap(f); /* does not return: the turn ends */
    }
    if (f->cs == 0x08u && (f->vector == 33u || f->vector == 44u)) {
        rt_ps2_irq(); /* inside cpu_wait_irq: the halt wakes and the scheduler retries the read */
        if (f->vector == 44u) port_out8(0xA0u, 0x20u);
        port_out8(0x20u, 0x20u);
        return;
    }
    if (f->cs == 0x08u && (f->vector == 39u || f->vector == 47u) && pic_low_line(f->vector) != RT_PIC_GENUINE) {
        return; /* IRQ 7 or 15 spurious (rt/pic.h); a genuine one is a routed line, below */
    }
    if (f->cs == 0x08u && f->vector >= 34u && f->vector < 48u) {
        /* NW-1: a routed PCI INTx (virtio-net or e1000) unmasked across cpu_wait_irq. */
        pic_mask_eoi(f->vector);
        return;
    }
#endif
    if (f->cs != 0x08u) rt_panic("trap frame");
    if (f->vector == 39u || f->vector == 47u) { /* spurious PIC interrupt: IRQ 15's owes the master its EOI */
        (void)pic_low_line(f->vector);
        return;
    }
    if (f->vector == 32u) {
        ticks++;
        port_out8(0x20u, 0x20u); /* EOI to the master PIC */
        rt_sched_tick();         /* may switch tasks; returns when this task runs again */
        return;
    }
    if (f->vector == 14u && !rt_probe_active) {
        uint64_t base;
        int g = rt_task_guard_hit(cr2_read(), &base);
        if (g >= 0) rt_task_stack_overflow(g); /* a task ran off its stack: it faults, the kernel goes on */
    }
    if (f->vector == 14u && !rt_probe_active && cr2_read() >= (uint64_t)(uintptr_t)stack_guard &&
        cr2_read() < (uint64_t)(uintptr_t)stack_guard + PAGE_BYTES)
        rt_panic("kernel stack overflow (guard page) outside a probe");
    if (rt_probe_active && f->vector <= 14u) {
        /* A fault, or the int 2, raised by a probe. Its RIP is inside the probe block, except for
         * a failed instruction fetch (error code bit 4), whose RIP is the address the probe
         * called, and a #DF, whose RIP is architecturally undefined. */
        uint64_t cr2 = f->vector == 14u ? cr2_read() : 0u;
        bool fetch = f->vector == 14u && (f->error & 0x10u) != 0u;
        bool in_probe = (char *)(uintptr_t)f->rip >= trap_probes && (char *)(uintptr_t)f->rip < trap_resume;
        unsigned ist = tss_loaded ? ist_of(f->vector) : 0u;
        const char *name = f->vector == 0u ? "trap_de" : f->vector == 2u ? "trap_nmi" : f->vector == 6u ? "trap_ud" :
                           f->vector == 8u ? "trap_df" : f->vector == 14u ? "trap_pf" : "trap";
        if (f->vector != 8u && !fetch && !in_probe) rt_panic("fault outside a probe");
        if (fetch && (f->rip != cr2 || trap_probe_rsp == 0u || f->rsp != trap_probe_rsp - 8u ||
                      *(const uint64_t *)(uintptr_t)f->rsp != (uint64_t)(uintptr_t)trap_resume))
            rt_panic("failed fetch that is not a probe's call");
        if (trap_len != 0u || trap_probe_rsp == 0u) rt_panic("second fault in one probe");
        if ((f->rflags & 0x200u) != 0u) rt_panic("interrupts enabled outside cpu_wait_irq");
        if (ist != 0u) {
            uintptr_t lo = (uintptr_t)ist_stacks[ist - 1u].mem;
            if ((uintptr_t)f < lo || (uintptr_t)f >= lo + IST_BYTES) rt_panic("exception not on its IST stack");
        }
        if (f->vector == 14u && cr2 >= (uint64_t)(uintptr_t)stack_guard && cr2 < (uint64_t)(uintptr_t)stack_guard + PAGE_BYTES) {
            name = "trap_stack";
            cr2 -= (uint64_t)(uintptr_t)stack_guard; /* the offset in the guard page: no image address in the record */
        } else if (f->vector == 14u) {
            uint64_t base;
            if (rt_task_guard_hit(cr2, &base) >= 0) { /* a probe ran a task off its stack */
                name = "trap_stack";
                cr2 -= base;
            }
        }
        last_error = f->error;
        trap_record(f, name, cr2, ist);
        if (trap_len == 0u) rt_panic("trap record does not encode");
        f->rip = (uint64_t)(uintptr_t)trap_resume;
        f->rsp = trap_probe_rsp;
        return;
    }
    put_dec_line("daphnis: unexpected trap, vector ", f->vector);
    put_dec_line("daphnis: error code ", f->error);
    rt_panic("unexpected trap");
}
