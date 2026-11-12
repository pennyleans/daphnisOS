/* rt/user.c: ring 3 (U1-1, U1-2; docs/user.md). The saved frame, FPU state and FS base of each
 * process, the entry stack, one user turn (rt_user_enter), the path back from ring 3
 * (rt_user_trap), and the user image (a loader module since U1-5).
 *
 * A process is its saved frame, its 512-byte fxsave area and its FS base here plus the pages
 * src/uvm.ci mapped for it; everything else about it (its table, its system calls, its end) is
 * cint, src/proc.ci. A turn returns one kind:
 *   1  a system call: the frame's RAX is the number, RDI RSI RDX R10 R8 R9 the arguments
 *   2  an exception: vector, error code and, for #PF, the address are the event words
 *   3  an interrupt (the timer, or a spurious one): the turn simply ended
 * cint reads the frame with user_reg and writes back only the general registers, RIP, RSP and
 * the FS base; rt_user_enter forces the selectors and the system bits of RFLAGS, so no value cint
 * writes can make the iretq run anything but ring 3 with interrupts on. */
#include "rt.h"

#define MAX_PROCS 64
#define ENTRY_STACK_BYTES 16384u
#define FX_BYTES 512
#define USER_CS 0x33u
#define USER_SS 0x2Bu
#define USER_TOP 0x0000800000000000u /* the first non-canonical address of the lower half */
/* RFLAGS a process may keep: CF PF AF ZF SF DF OF. IF and bit 1 are always set, IOPL, TF, NT, AC,
 * VM and the rest always clear. */
#define RFLAGS_USER 0x0CD5u
#define RFLAGS_FIXED 0x0202u

void user_cpu_init(void);
void fx_save(void *area);
uint64_t user_enter(const struct rt_trap_frame *f, uint64_t root, const void *fx, uint64_t fs);
_Noreturn void user_leave(uint64_t kind);
uint64_t cr2_read(void);
extern const uint8_t initrd_start[], initrd_end[];

static struct rt_trap_frame frames[MAX_PROCS];
static uint64_t events[MAX_PROCS][3]; /* vector, error code, address of the last exception */
static uint8_t fx[MAX_PROCS][FX_BYTES] __attribute__((aligned(16)));
static uint64_t fs_base[MAX_PROCS];
static uint8_t entry_stack[ENTRY_STACK_BYTES] __attribute__((aligned(16)));
uint64_t user_entry_top; /* read by user.S */
static int64_t running = -1;
static bool ready;

void rt_user_init(void)
{
    user_cpu_init();
    user_entry_top = (uint64_t)(uintptr_t)entry_stack + ENTRY_STACK_BYTES;
    rt_tss_set_rsp0(user_entry_top);
    ready = true;
}

static bool pid_ok(int64_t pid)
{
    return pid >= 0 && pid < MAX_PROCS;
}

cint_status rt_user_setup(int64_t pid, uint64_t rip, uint64_t rsp)
{
    struct rt_trap_frame *f;
    if (!pid_ok(pid) || rip >= USER_TOP || rsp >= USER_TOP) return CINT_REFUSED;
    f = &frames[pid];
    memset(f, 0, sizeof *f);
    f->rip = rip;
    f->rsp = rsp;
    f->cs = USER_CS;
    f->ss = USER_SS;
    f->rflags = RFLAGS_FIXED;
    memset(events[pid], 0, sizeof events[pid]);
    /* the state Linux starts a process in: FCW 0x37F, MXCSR 0x1F80, every register 0 */
    memset(fx[pid], 0, FX_BYTES);
    fx[pid][0] = 0x7Fu;
    fx[pid][1] = 0x03u;
    fx[pid][24] = 0x80u;
    fx[pid][25] = 0x1Fu;
    fs_base[pid] = 0u;
    return CINT_OK;
}

/* One turn of process pid in the address space whose PML4 is at root (a frame of the pool). */
int64_t rt_user_enter(int64_t pid, uint64_t root)
{
    struct rt_trap_frame *f;
    uint64_t kind;
    if (!ready || !pid_ok(pid) || root % 4096u != 0u || root < RT_POOL_BASE || root >= rt_pool_end) return -1;
    f = &frames[pid];
    if (f->rip >= USER_TOP || f->rsp >= USER_TOP) return -1;
    f->cs = USER_CS;
    f->ss = USER_SS;
    f->rflags = (f->rflags & RFLAGS_USER) | RFLAGS_FIXED;
    running = pid;
    kind = user_enter(f, root, fx[pid], fs_base[pid]);
    running = -1;
    rt_fb_collect(root); /* before syscall/fault dispatch can unmap or destroy this inactive root */
    if (kind == 3u) rt_fb_timer_present(); /* user_leave restored the kernel CR3 first */
    return (int64_t)kind;
}

void rt_user_trap(struct rt_trap_frame *f)
{
    uint64_t kind;
    if (running < 0) rt_panic("ring 3 frame with no process running");
    fx_save(fx[running]);
    frames[running] = *f;
    if (f->vector == 256u) {
        kind = 1u;
    } else if (f->vector < 32u) {
        events[running][0] = f->vector;
        events[running][1] = f->error;
        events[running][2] = f->vector == 14u ? cr2_read() : 0u;
        kind = 2u;
    } else {
        kind = 3u; /* the timer (trap.c counted and acknowledged it) or a spurious PIC interrupt */
    }
    user_leave(kind);
}

/* Words 0 to 21 are the frame (struct rt_trap_frame order), 22 to 24 the event words, 25 the FS base. */
uint64_t rt_user_reg(int64_t pid, int64_t i)
{
    if (!pid_ok(pid)) return 0u;
    if (i >= 0 && i < RT_FRAME_WORDS) return ((const uint64_t *)(const void *)&frames[pid])[i];
    if (i >= RT_FRAME_WORDS && i < RT_FRAME_WORDS + 3) return events[pid][i - RT_FRAME_WORDS];
    if (i == RT_FRAME_WORDS + 3) return fs_base[pid];
    return 0u;
}

/* The general registers (0 to 14), RIP (17), RSP (20) and the FS base (25) only. */
cint_status rt_user_set_reg(int64_t pid, int64_t i, uint64_t v)
{
    if (!pid_ok(pid) || !((i >= 0 && i <= 14) || i == 17 || i == 20 || i == RT_FRAME_WORDS + 3)) return CINT_REFUSED;
    if ((i == 17 || i == 20 || i == RT_FRAME_WORDS + 3) && v >= USER_TOP) return CINT_REFUSED;
    if (i == RT_FRAME_WORDS + 3) {
        fs_base[pid] = v;
        return CINT_OK;
    }
    ((uint64_t *)(void *)&frames[pid])[i] = v;
    return CINT_OK;
}

/* fork (U1-4): dst gets src's registers, FPU state and FS base; the event words start clear. */
cint_status rt_user_copy(int64_t src, int64_t dst)
{
    if (!pid_ok(src) || !pid_ok(dst) || src == dst) return CINT_REFUSED;
    frames[dst] = frames[src];
    memcpy(fx[dst], fx[src], FX_BYTES);
    fs_base[dst] = fs_base[src];
    memset(events[dst], 0, sizeof events[dst]);
    return CINT_OK;
}

/* Word i (0 to 63) of the process's fxsave area. */
uint64_t rt_user_fx(int64_t pid, int64_t i)
{
    uint64_t v;
    if (!pid_ok(pid) || i < 0 || i >= FX_BYTES / 8) return 0u;
    memcpy(&v, fx[pid] + 8 * i, sizeof v);
    return v;
}

/* Word 3 holds MXCSR in its low half: its reserved bits stay clear, or fxrstor would fault. */
cint_status rt_user_set_fx(int64_t pid, int64_t i, uint64_t v)
{
    if (!pid_ok(pid) || i < 0 || i >= FX_BYTES / 8) return CINT_REFUSED;
    if (i == 3) v &= 0xFFFFFFFF0000FFFFu;
    memcpy(fx[pid] + 8 * i, &v, sizeof v);
    return CINT_OK;
}

/* The image: the first loader module (U1-5: QEMU's -initrd, GRUB's module2), else what initrd.S
 * embeds (nothing unless the build passes INITRD). */
static const uint8_t *image(int64_t *size)
{
    uint64_t bytes, base = rt_boot_module(&bytes);
    if (bytes != 0u) {
        *size = (int64_t)bytes;
        return (const uint8_t *)(uintptr_t)base;
    }
    *size = (int64_t)(initrd_end - initrd_start);
    return initrd_start;
}

int64_t rt_initrd_size(void)
{
    int64_t size;
    (void)image(&size);
    return size;
}

/* Copies up to n bytes of the image from offset off; returns the count, 0 past the end. */
int64_t rt_initrd_read(int64_t off, uint8_t *dst, int64_t n)
{
    int64_t size, k;
    const uint8_t *src = image(&size);
    if (off < 0 || n < 0 || off >= size) return 0;
    k = size - off < n ? size - off : n;
    memcpy(dst, src + off, (size_t)k);
    return k;
}
