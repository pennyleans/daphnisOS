/* rt/rt.h: internal header of the Daphnis freestanding runtime.
 *
 * cint_rt.h (from the pinned cint toolchain, see toolchain.pin) declares the entry points
 * the emitted C calls. rt/ implements the subset that emitted C uses (docs/runtime.md). */
#ifndef DAPHNIS_RT_H
#define DAPHNIS_RT_H

#include "cint_rt.h"
#include "fb_pixels.h"

void *memcpy(void *restrict dst, const void *restrict src, size_t n);
void *memmove(void *dst, const void *src, size_t n);
void *memset(void *dst, int c, size_t n);
int memcmp(const void *a, const void *b, size_t n);

/* Assembly stubs of arch/x86_64/portio.S (SysV ABI). */
void port_out8(uint16_t port, uint8_t value);
uint8_t port_in8(uint16_t port);
uint64_t cpu_rdrand_present(void); /* A-3, arch/x86_64/rng.S (RT_USER images) */
uint64_t cpu_rdrand64(uint64_t *dst);
void cpu_cpuid(uint32_t leaf, uint32_t out[4]); /* KF-3a, arch/x86_64/rng.S: CPUID leaf, subleaf 0 */
void port_out16(uint16_t port, uint16_t value);
uint16_t port_in16(uint16_t port);
void port_out32(uint16_t port, uint32_t value);
uint32_t port_in32(uint16_t port);
void cpu_halt(void);

/* The values written to the isa-debug-exit port 0xf4. QEMU exits with (value << 1) | 1. */
#define RT_EXIT_OK 0x10u
#define RT_EXIT_FAULT 0x11u
#define RT_EXIT_PANIC 0x1Fu

/* Physical memory (docs/memory.md, G-0): the loader's module window runs from the image's end to the
 * pool, the frame pool of src/frames.ci (16,384 frames, 64 MiB) follows, and the K5 run blob sits above
 * the pool. src/frames.ci POOL_BASE and src/kern.ci BLOB carry the same numbers. */
#define RT_POOL_BASE 0x2000000u /* 32 MiB */
#define RT_POOL_END 0x6000000u  /* 96 MiB: the pool of the gates; rt_pool_end is the live end (M-3) */
#define RT_POOL_CAP 0x200000000u /* 8 GiB: as far as boot.S identity maps and src/frames.ci's bitmap reaches */
extern uint64_t rt_pool_end;    /* [RT_POOL_BASE, rt_pool_end) is the pool: RT_POOL_END until src/pool.ci sets it once */
int64_t rt_phys_pool_window(uint64_t end);
#define RT_BLOB_BASE 0x6000000u /* 96 MiB: QEMU -device loader puts the run blob here, 1 MiB, read only */
#define RT_BLOB_END 0x6100000u

/* The frame arena (cint_mem_frame_*) charges local arrays by element. 4,096 elements of at most 8
 * bytes is 32 KiB of arrays, which with 256 frames fits the 128 KiB stack of boot.S. */
#define RT_FRAME_ARENA_ELEMENTS 4096

/* The one context of the kernel. Its head comes first (cint_rt.h 6e). */
struct cint_ctx {
    cint_rt_head head;
    const cint_program *program;
    int64_t config_depth;
    int64_t frame_charged;
    int64_t frame_arena_bytes;
    cint_site stack[CINT_RT_MAX_DEPTH];
    cint_fault_record fault;
    uint8_t *pool; /* where this context's module-state blocks come from (ctx.c) */
    size_t pool_bytes, pool_used;
    cint_site host_site; /* the site of the extern call this context is running (host.c); K5: per context, not a global */
};

extern struct cint_ctx rt_ctx;

/* The status a host row returns when a hardware trap during the call was recorded (trap.c) and
 * must become the context's fault record (K5: a page access that the page tables refused). */
#define RT_ST_TRAP 99

/* Module state (ctx.c): a table of two pointers per module, one table per context. The user flavor
 * holds 34 modules (N-3's tcp.ci, W-2's tile.ci, P's blk.ci and ext2.ci); deskplay 49 with FB's src/bits.ci, and
 * K-12's src/k12.ci in the user flavor. The user flavor holds 66 since RS-CLK (src/civil.ci, src/cmos.ci): past 64,
 * every user kernel stopped at its first context with "more modules than RT_MAX_MODULES". */
#define RT_MAX_MODULES 96u

/* fault.c */
/* Encodes r. With buf, copies up to cap bytes (0 returned if cap is too small); with sink,
 * passes each byte to sink; with neither, only counts. Returns the length, 0 if r does not
 * encode. */
size_t rt_fault_encode(const cint_fault_record *r, uint8_t *buf, size_t cap, void (*sink)(uint8_t));
cint_fault_record *rt_record_begin(cint_ctx *ctx, cint_site site, uint16_t code);
void rt_record_op(cint_fault_record *rec, const char *part);
void rt_record_operand(cint_fault_record *rec, uint32_t tag, uint64_t bits);
void rt_record_limit_i64(cint_fault_record *rec, int64_t limit);
bool rt_fault_host(cint_ctx *ctx, cint_site site, const char *op, bool has_status, int64_t status);
/* A site that always encodes (the first of the root module), for a record made where no cint call is
 * live: a stack overflow in a task's entry frame, an exhausted state pool. */
cint_site rt_placeholder_site(const cint_program *program);

/* Shared serial sink and confidential capture boot boundary. */
void rt_serial_byte(uint8_t byte);
void rt_console_byte(uint8_t byte);
uint64_t rt_console_written(void);
uint8_t rt_console_at(uint64_t at);
void rt_capture_boot(void);
void rt_capture_byte(uint8_t byte);
void rt_capture_finish(void);
void rt_journal_record(int64_t kind, const uint8_t *bytes, size_t n);
int64_t rt_journal_size(int64_t kind);
int64_t rt_journal_read(int64_t kind, int64_t offset, uint8_t *bytes, size_t n);
void rt_puts(const char *s);
void rt_put_hex_byte(uint8_t b);
void rt_put_dec(uint64_t v);

/* host.c */
bool rt_host_bind(const cint_program *program, const cint_host_desc *imports);

/* ctx.c, task.c: kernel tasks (docs/runtime.md) */
const char *rt_program_requires(void);
void rt_ctx_init(struct cint_ctx *ctx, const cint_program *program);
void rt_ctx_pool(struct cint_ctx *ctx, void **blocks, uint8_t *pool, size_t pool_bytes);
void rt_print_fault(const cint_fault_record *rec);
void rt_task_setup(const cint_program *program, cint_main_fn main_fn);
const uint8_t *rt_task_args(const cint_ctx *ctx, size_t *length);
int64_t rt_task_create(int64_t id, int64_t caps);
int64_t rt_task_run(int64_t id);
void rt_task_yield(void);
void rt_task_preempt_enable(int64_t ticks);
int64_t rt_task_preemptions(void);
void rt_sched_tick(void);
int64_t rt_task_out_len(int64_t id);
uint8_t rt_task_out_byte(int64_t id, int64_t i);
bool rt_task_covered(uint32_t cap);
bool rt_task_preemptible(void);
cint_status rt_task_write(const uint8_t *bytes, int64_t n);

/* task.c, chan.c: K4.5 (docs/runtime.md). The fuel quantum, the event log and channels. */
void rt_task_quantum_set(int64_t fuel);
void rt_task_quantum_point(cint_ctx *ctx);
void rt_task_net_set(int64_t net);
void rt_task_stack_budget(int64_t bytes);
int rt_task_current(void);
uint64_t rt_task_guard(int64_t id);
const struct cint_ctx *rt_task_ctx(void);
int rt_task_guard_hit(uint64_t addr, uint64_t *base);
void rt_task_stack_overflow(int id);
void rt_task_block(uint32_t send_mask, uint32_t recv_mask);
cint_status rt_task_emit(int64_t kind, int64_t value);
int64_t rt_task_log_len(int64_t id);
int64_t rt_task_log_kind(int64_t id, int64_t i);
int64_t rt_task_log_val(int64_t id, int64_t i);
int64_t rt_task_fuel(int64_t id);
int64_t rt_chan_open(int64_t id, int64_t sender, int64_t receiver);
void rt_chan_close(int64_t id);
void rt_chan_status(uint32_t *full, uint32_t *nonempty);
cint_status rt_chan_send(int64_t id, int64_t value);
cint_status rt_chan_recv(int64_t id, int64_t *value);
cint_status rt_chan_recv_any(int64_t a, int64_t b, int64_t *value);
void cpu_cli(void);
void cpu_sti(void);

/* task.c, state.c: K5 (docs/runtime.md, docs/snapshot.md). A task is a step function: the kernel runs
 * one step on a fresh stack, the step ends by recording one request, and between steps no stack
 * exists, so a task's state is its module variables, its pages and its fuel count. */
int64_t rt_task_step(int64_t id);
cint_status rt_task_request(int64_t kind, int64_t a, int64_t b, int64_t v);
int64_t rt_task_req(int64_t id, int64_t i);
void rt_task_args_set(int64_t id, const uint8_t *src, int64_t n);
int64_t rt_task_fuel_total(int64_t id);
void rt_task_fuel_set(int64_t id, int64_t v);
cint_status rt_task_space(int64_t id, int64_t root);
cint_status rt_page_op(int64_t slot, int64_t idx, bool store, int64_t v, int64_t *out);
struct cint_ctx *rt_task_ctx_of(int64_t id);
void rt_state_register(const cint_state_table *t);
int64_t rt_state_size(int64_t id);
int64_t rt_state_read(int64_t id, int64_t off, uint8_t *dst, int64_t n);
void rt_state_stage(int64_t off, const uint8_t *src, int64_t n);
int64_t rt_state_apply(int64_t id, int64_t len);
uint8_t rt_rev_byte(int64_t i);
void cr3_write(uint64_t root);

/* The frame trap_common (arch/x86_64/trap.S) builds: the registers it pushes, the vector and
 * error code of the stub, and the five words the CPU pushes. The syscall entry (user.S) builds the
 * same, vector 256. */
struct rt_trap_frame {
    uint64_t r15, r14, r13, r12, r11, r10, r9, r8, rbp, rdi, rsi, rdx, rcx, rbx, rax;
    uint64_t vector, error;
    uint64_t rip, cs, rflags, rsp, ss;
};
#define RT_FRAME_WORDS 22

/* trap.c: the IDT, the trap record and the tick counter, reached from cint as externs */
void rt_tss_set_rsp0(uint64_t top);
bool rt_trap_adopt(cint_ctx *ctx);
uint64_t rt_trap_stub(uint64_t vector);
void rt_idt_set(uint64_t vector, uint64_t lo, uint64_t hi);
void rt_idt_load(void);
void rt_trap_reset(void);
int64_t rt_trap_record_len(void);
uint8_t rt_trap_record_byte(int64_t i);
int64_t rt_timer_ticks(void);
int64_t rt_us_now(void);
uint64_t rt_tss_base(void);
uint64_t rt_ist_top(uint64_t n);
void rt_tss_set_ist(uint64_t n, uint64_t top);
void rt_gdt_set(uint64_t slot, uint64_t lo, uint64_t hi);
void rt_tss_load(void);
/* The probes of arch/x86_64/probe.S all take two integers and return one, so rt_probe can run
 * any of them: it clears the trap record, marks a probe active, runs it, and returns its
 * value, or 0 if it faulted (then rt_trap_record_len() is not 0). */
uint64_t trap_probe_de(uint64_t, uint64_t);
uint64_t trap_probe_ud(uint64_t, uint64_t);
uint64_t trap_probe_pf(uint64_t, uint64_t);
uint64_t trap_probe_nmi(uint64_t, uint64_t);
uint64_t trap_probe_stack(uint64_t, uint64_t);
uint64_t trap_probe_load(uint64_t, uint64_t);
uint64_t trap_probe_store(uint64_t, uint64_t);
uint64_t trap_probe_exec(uint64_t, uint64_t);
uint64_t rt_probe(uint64_t (*fn)(uint64_t, uint64_t), uint64_t a, uint64_t b);
void vm_invlpg(uint64_t va);
uint64_t cr3_read(void);
uint64_t pat_read(void);
void pat_write(uint64_t pat);

/* boot.c: the loader's information block, copied once before main (docs/memory.md) */
void rt_boot_init(void);
int64_t rt_boot_info(uint8_t *dst, int64_t n);
int64_t rt_boot_status(void);
uint32_t rt_boot_fitted(void);
uint64_t rt_boot_module(uint64_t *bytes);
size_t rt_boot_cmdline(char *dst, size_t n);
size_t rt_boot_net(char *dst, size_t n);
uint64_t rt_boot_pool_floor(void);
bool rt_boot_framebuffer(uint64_t *addr, uint32_t *pitch, uint32_t *w, uint32_t *h, struct rt_fb_format *format);
bool rt_boot_shadow_free(uint64_t base, uint64_t bytes);
bool rt_boot_firmware_range(uint64_t base, uint64_t end);
bool rt_boot_pool_max(void);
bool rt_boot_poweroff(void);
bool rt_boot_uart_off(void);
bool rt_boot_read(void);
bool rt_console_uart_off(void);
void rt_poweroff_set(uint64_t pm1a, uint64_t pm1b, uint64_t typa, uint64_t typb);
void rt_poweroff_acpi(uint64_t smi_cmd, uint64_t enable);
void rt_poweroff_events(uint64_t pm1a_evt, uint64_t pm1b_evt, uint64_t len);
void rt_poweroff_gpe(uint64_t gpe0, uint64_t gpe0_len, uint64_t gpe1, uint64_t gpe1_len);
void rt_ps2_absent(void);

/* phys.c: the physical windows cint may read and write through phys_read/phys_write */
void rt_guard_pages(const void *addr, unsigned pages);
void rt_wx_init(void);
int64_t rt_wx_probe(int64_t kind);
uint64_t rt_trap_last_error(void);
cint_status rt_phys_copy(bool to_phys, uint64_t base, void *buf, int64_t extent, int64_t byte_stride, unsigned width);
void rt_phys_window_fb(uint64_t lo, uint64_t hi);
void cpu_wait_irq(void);

/* fb.c: canonical shadow surface; word i is w, h, stride, kernel virtual base, len.
 * rt_fb_page resolves a page-aligned offset to physical backing for application mappings. */
int64_t rt_fb_init(void);
int64_t rt_fb_prepare(void);
int64_t rt_fb_need(void);
int64_t rt_fb_backing_add(uint64_t pa, int64_t pages);
int64_t rt_fb_mode_need(uint64_t w, uint64_t h);
uint64_t rt_fb_page(uint64_t off);
void rt_fb_present(void);
void rt_fb_present_pending(void);
void rt_fb_collect(uint64_t root);
void rt_fb_timer_present(void);
bool rt_fb_verify(void);
void fb_fence(void);
uint64_t rt_fb_word(int64_t i);
int64_t rt_fb_mode(uint64_t w, uint64_t h);
cint_status rt_fb_put(uint64_t off, const uint8_t *src, int64_t len, int64_t stride);
int64_t rt_fb_get(uint64_t off, uint8_t *dst, int64_t len);
cint_status rt_px_spread(uint8_t *buf, int64_t blen, int64_t m, int64_t s, int64_t phase);

/* mmio.c: device registers (AU-1); a window is a BAR, mapped uncached */
int64_t rt_mmio_map(uint64_t base, uint64_t len);
cint_status rt_mmio_in(uint64_t addr, unsigned width, uint64_t *v);
cint_status rt_mmio_out(uint64_t addr, unsigned width, uint64_t v);

/* ps2.c: the 8042's bytes (F-2, F-3): ring 0 the keyboard, 1 the mouse */
int64_t rt_ps2_init(void);
void rt_ps2_irq(void);
int64_t rt_ps2_get(int64_t which);
int64_t rt_ps2_dropped(void);
int64_t rt_ps2_stamp(void);

/* user.c, arch/x86_64/user.S: ring 3 (U1-1, docs/user.md) */
void rt_user_init(void);
cint_status rt_user_setup(int64_t pid, uint64_t rip, uint64_t rsp);
int64_t rt_user_enter(int64_t pid, uint64_t root);
uint64_t rt_user_reg(int64_t pid, int64_t i);
cint_status rt_user_set_reg(int64_t pid, int64_t i, uint64_t v);
cint_status rt_user_copy(int64_t src, int64_t dst);
uint64_t rt_user_fx(int64_t pid, int64_t i);
cint_status rt_user_set_fx(int64_t pid, int64_t i, uint64_t v);
_Noreturn void rt_user_trap(struct rt_trap_frame *f);
int64_t rt_initrd_size(void);
int64_t rt_initrd_read(int64_t off, uint8_t *dst, int64_t n);

/* start.c */
void rt_exit(unsigned value);
void rt_panic(const char *why);

#endif
