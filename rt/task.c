/* rt/task.c: kernel tasks, the mechanism only. A task is the program's cint `main` run on
 * a stack of its own with a cint_ctx of its own (depth, fuel, call stack and fault record are
 * per context). The scheduling policy is cint code (src/sched.ci): it creates tasks, runs one
 * at a time, and decides who is next; this file switches stacks (arch/x86_64/task.S), ends a
 * quantum from the timer interrupt when preemption is on, and answers the console service
 * for the running task according to the grants the task was created with. Grants are fixed
 * at task_create and nothing here changes them. */
#include "rt.h"

extern char __high_end[];   /* linker.ld: the end of the emitted cint, the high window */

#ifndef RT_MAX_TASKS
#define RT_MAX_TASKS 3u /* the user flavor runs ring 3 processes, not tasks, and keeps one (Makefile, F-1) */
#endif
#define MAX_TASKS RT_MAX_TASKS
/* 128 KiB of stack, as the boot stack has, under a guard of two pages: a frame holds at most a
 * 4,096 byte array and a few words, so it cannot step over a guard of two pages (docs/runtime.md,
 * stack budget). The shep flavor builds with a 16 KiB stack, so a test can overrun it. */
#ifndef RT_TASK_STACK
#define RT_TASK_STACK 131072u
#endif
#define TASK_STACK RT_TASK_STACK
#define GUARD_BYTES 8192u
#define OUT_BYTES 512u
#define EV_MAX 256u
#define TASK_POOL 4096u /* module state of one task */

void task_switch(uint64_t *save_rsp, uint64_t new_rsp);
void cpu_cli(void);
void cpu_sti(void);

/* What a turn ended with (the value task_run returns). 4 to 6 are K4.5: the task blocked on a
 * channel, its fuel quantum ran out at a host call, or it is still blocked and was not run. */
enum { TASK_YIELDED = 0, TASK_DONE = 1, TASK_PREEMPTED = 2, TASK_FAULTED = 3, TASK_BLOCKED = 4, TASK_QUANTUM = 5, TASK_NOTREADY = 6, TASK_STEPPED = 7 };

struct task {
    uint64_t rsp;
    bool created;
    bool done;
    int state;
    uint32_t caps;
    struct cint_ctx ctx;
    uint8_t args[16];
    size_t args_len;
    uint8_t out[OUT_BYTES];
    size_t out_len;
    /* K4.5: module state of its own (door 1: no state is shared between contexts), what it
     * waits for, the fuel at which its quantum next ends, and its event log */
    void *blocks[2u * RT_MAX_MODULES];
    uint8_t pool[TASK_POOL];
    bool blocked;
    uint32_t wait_send, wait_recv;
    int64_t next_fuel;
    /* K5: cumulative fuel over all steps, the page tables of its address space (0: the kernel's),
     * and the request its last step made */
    int64_t fuel_total;
    uint64_t root;
    bool req_set;
    int64_t req[4];
    uint8_t ev_kind[EV_MAX];
    int64_t ev_val[EV_MAX];
    size_t ev_len;
};

static struct task tasks[MAX_TASKS];
static struct {
    uint8_t guard[GUARD_BYTES]; /* not present once rt_task_setup has run */
    uint8_t mem[TASK_STACK];
} stacks[MAX_TASKS] __attribute__((aligned(4096)));
static uint64_t sched_rsp;
static int current = -1;
static const cint_program *task_program;
static cint_main_fn task_main;
static bool preempt_on;
static int64_t quantum, quantum_left, preemptions;
static int64_t quantum_fuel; /* K4.5: 0 off, else a quantum in fuel units, ended at a host call */
static int64_t net_digit = -1;
static int64_t stack_budget; /* usable bytes of the stack of tasks made next; 0: all of it */

void rt_task_setup(const cint_program *program, cint_main_fn main_fn)
{
    unsigned i;
    task_program = program;
    task_main = main_fn;
    for (i = 0u; i < MAX_TASKS; i++) rt_guard_pages(stacks[i].guard, GUARD_BYTES / 4096u);
}

const uint8_t *rt_task_args(const cint_ctx *ctx, size_t *length)
{
    unsigned i;
    for (i = 0u; i < MAX_TASKS; i++) {
        if (ctx == (const cint_ctx *)&tasks[i].ctx) {
            *length = tasks[i].args_len;
            return tasks[i].args;
        }
    }
    return NULL;
}

static void task_entry(void)
{
    struct task *t = &tasks[current];
    cint_status st;
    if (preempt_on) cpu_sti();
    st = task_main((cint_ctx *)&t->ctx, CINT_FUEL_UNBOUNDED);
    cpu_cli(); /* before the stores: a tick between them and the switch would overwrite the state */
    t->state = st == CINT_OK ? TASK_DONE : TASK_FAULTED;
    t->done = true;
    task_switch(&t->rsp, sched_rsp);
    for (;;) cpu_halt();
}

/* Puts a first frame on the task's stack: a first switch pops six registers, then returns to
 * `entry`; at entry RSP is 8 mod 16. */
static void arm(struct task *t, int id, void (*entry)(void))
{
    uint64_t *top = (uint64_t *)(void *)(stacks[id].mem + (stack_budget > 0 ? (size_t)stack_budget : (size_t)TASK_STACK));
    top[-1] = 0u;
    top[-2] = (uint64_t)(uintptr_t)entry;
    t->rsp = (uint64_t)(uintptr_t)(top - 8);
}

/* A K5 step: the program's main runs once, on a fresh stack, as one entry of the task's context
 * (fuel is per entry, so the task's total is summed here), and the stack is gone after it. */
static void step_entry(void)
{
    struct task *t = &tasks[current];
    cint_status st = task_main((cint_ctx *)&t->ctx, CINT_FUEL_UNBOUNDED);
    cpu_cli();
    t->fuel_total += t->ctx.head.fuel_used;
    t->state = st == CINT_OK ? TASK_STEPPED : TASK_FAULTED;
    task_switch(&t->rsp, sched_rsp);
    for (;;) cpu_halt();
}

/* Creates task id (0 to 2), or makes it anew (a task that blocked for good is dropped with its stack),
 * with a capability mask (1 console.input, 2 console.raw). The task
 * runs the program's main with the decimal id + 1 as its argument. Returns 0, or -1. */
int64_t rt_task_create(int64_t id, int64_t caps)
{
    struct task *t;
    if (id < 0 || id >= (int64_t)MAX_TASKS || current >= 0 || caps < 0 || caps > 3 || task_program == NULL) return -1;
    if ((uintptr_t)__high_end > 0x400000u) return -1;   /* a task space maps the low 4 MiB only (src/kspace.ci, linker.ld) */
    t = &tasks[id];
    memset(t, 0, sizeof *t);
    rt_ctx_init((struct cint_ctx *)&t->ctx, task_program);
    t->created = true;
    t->caps = (uint32_t)caps;
    t->args[0] = (uint8_t)('1' + id);
    if (net_digit >= 0) {
        t->args[1] = (uint8_t)('0' + net_digit);
        t->args[2] = 0u;
        t->args_len = 3u;
    } else {
        t->args[1] = 0u;
        t->args_len = 2u;
    }
    rt_ctx_pool((struct cint_ctx *)&t->ctx, t->blocks, t->pool, sizeof t->pool);
    t->next_fuel = quantum_fuel;
    arm(t, (int)id, task_entry);
    return 0;
}

/* Runs task id until it yields, is preempted, ends or faults. Returns the state: 0 yielded,
 * 1 done, 2 preempted, 3 faulted (its record is printed), 4 blocked on a channel, 5 its fuel
 * quantum ended, 6 still blocked (nothing ran), -1 no such task or already done. */
int64_t rt_task_run(int64_t id)
{
    struct task *t;
    if (id < 0 || id >= (int64_t)MAX_TASKS || !tasks[id].created || tasks[id].done || current >= 0) return -1;
    t = &tasks[id];
    if (t->blocked) {
        uint32_t full, nonempty;
        rt_chan_status(&full, &nonempty);
        if (((t->wait_send & ~full) | (t->wait_recv & nonempty)) == 0u) return TASK_NOTREADY;
        t->blocked = false;
    }
    current = (int)id;
    quantum_left = 0;
    task_switch(&sched_rsp, t->rsp);
    current = -1;
    if (t->state == TASK_FAULTED) {
        rt_puts("task ");
        rt_put_dec((uint64_t)id + 1u); /* the number its program sees as its argument */
        rt_puts(" faulted\n");
        rt_print_fault(&t->ctx.fault);
    }
    return t->state;
}

/* Ends the running task's turn with `state`; returns when the scheduler runs it again. */
static void turn_end(int state)
{
    struct task *t = &tasks[current];
    cpu_cli();
    t->state = state;
    task_switch(&t->rsp, sched_rsp);
    if (preempt_on) cpu_sti();
}

void rt_task_yield(void)
{
    if (current < 0) return;
    turn_end(TASK_YIELDED);
}

int rt_task_current(void)
{
    return current;
}

/* The address of the first guard page of task id's stack (0 if no such task): for the kernel to
 * check, in the page table, that the page is not present. Nothing is printed from it. */
uint64_t rt_task_guard(int64_t id)
{
    return id >= 0 && id < (int64_t)MAX_TASKS ? (uint64_t)(uintptr_t)stacks[id].guard : 0u;
}

/* The context of the code that is running: the task's own, or the kernel's. A trap record is
 * made from this one, so that its stack is the task's and not the kernel's at that moment. */
const struct cint_ctx *rt_task_ctx(void)
{
    return current >= 0 ? &tasks[current].ctx : &rt_ctx;
}

/* The task whose guard pages hold addr (-1 if none), and the address of its first guard page. */
int rt_task_guard_hit(uint64_t addr, uint64_t *base)
{
    unsigned i;
    for (i = 0u; i < MAX_TASKS; i++) {
        uint64_t lo = (uint64_t)(uintptr_t)stacks[i].guard;
        if (addr >= lo && addr < lo + GUARD_BYTES) {
            *base = lo;
            return (int)i;
        }
    }
    return -1;
}

/* A task ran off its stack into its guard pages, outside a probe (called by rt_trap_dispatch, on
 * the IST stack of the #PF, interrupts off). The task faults: the record names the task and
 * nothing else, since where the first touch lands depends on the size of the compiler's frames.
 * It does not return: the scheduler's turn ends, and this IST stack is free again. */
void rt_task_stack_overflow(int id)
{
    struct task *t;
    cint_fault_record *rec;
    if (id != current) rt_panic("stack guard hit by a task that is not running");
    t = &tasks[id];
    /* The position is the first call of the task's entry, the one site every compiler agrees on
     * (how many frames were live when the first touch fell in the guard depends on inlining), or,
     * if no call is live, a placeholder site of the root module. */
    rec = rt_record_begin((cint_ctx *)&t->ctx, t->ctx.head.stack_count > 0u ? t->ctx.stack[0] : rt_placeholder_site(t->ctx.program), (uint16_t)CINT_E_UNSUPPORTED);
    if (rec != NULL) {
        rec->stack_count = 0u;
        rt_record_op(rec, "host");
        rt_record_op(rec, "error");
        rt_record_op(rec, "task_stack");
        rt_record_operand(rec, CINT_TAG_I64, (uint64_t)id + 1u);
    }
    /* where the first touch fell depends on the compiler's frames, so the fuel the task had used
     * does too: it is stamped as 0, outside what the schedule digest claims */
    t->ctx.head.fuel_used = 0;
    t->state = TASK_FAULTED;
    t->done = true;
    task_switch(&t->rsp, sched_rsp);
    rt_panic("a task that overflowed its stack was resumed");
}
/* The task waits until a channel in send_mask has room or one in recv_mask has a message. */
void rt_task_block(uint32_t send_mask, uint32_t recv_mask)
{
    struct task *t;
    if (current < 0) rt_panic("block outside a task");
    cpu_cli(); /* the three stores below and the switch are one step: a tick between them would see half of it */
    t = &tasks[current];
    t->blocked = true;
    t->wait_send = send_mask;
    t->wait_recv = recv_mask;
    turn_end(TASK_BLOCKED);
}

void rt_task_quantum_set(int64_t fuel)
{
    quantum_fuel = fuel < 0 ? 0 : fuel;
}

/* How much of its stack a task made next may use, from the top (0: all). The least that the first
 * switch needs is 64 bytes, and with exactly that the first call of the task falls in its guard,
 * before its program has begun: the test of a stack overflow where no cint call is live. */
void rt_task_stack_budget(int64_t bytes)
{
    stack_budget = bytes >= 64 && bytes <= (int64_t)TASK_STACK && bytes % 16 == 0 ? bytes : 0;
}

void rt_task_net_set(int64_t net)
{
    net_digit = net >= 0 && net <= 9 ? net : -1;
}

/* The fuel quantum (K4.5). Called by cint_rt_host_call before it charges a call, so the count
 * in the context is exact (a leaf function keeps its count in locals, and has no host call). When
 * the task has used at least `next_fuel` units its turn ends here, and the call is charged and
 * made when the scheduler runs the task again. Fuel is charged by cint's semantics, so a turn
 * ends at the same source point and the same count on every compiler and optimization level.
 * fuel_limit is never touched: a real E_FUEL fault is the record it always was. */
void rt_task_quantum_point(cint_ctx *ctx)
{
    struct task *t;
    if (current < 0 || quantum_fuel <= 0) return;
    t = &tasks[current];
    if (ctx != (cint_ctx *)&t->ctx || ctx->head.fuel_used < t->next_fuel) return;
    t->next_fuel = (ctx->head.fuel_used / quantum_fuel + 1) * quantum_fuel;
    turn_end(TASK_QUANTUM);
}

/* The event log (K4.5): what a task did that the world can see, in the order the task did it.
 * An event is (kind, value); its place is (task, sequence number), which no schedule changes. */
cint_status rt_task_emit(int64_t kind, int64_t value)
{
    struct task *t;
    if (current < 0 || kind < 0 || kind > 255) return CINT_REFUSED;
    t = &tasks[current];
    if (t->ev_len >= EV_MAX) return CINT_REFUSED;
    t->ev_kind[t->ev_len] = (uint8_t)kind;
    t->ev_val[t->ev_len] = value;
    t->ev_len++;
    return CINT_OK;
}

int64_t rt_task_log_len(int64_t id)
{
    return id >= 0 && id < (int64_t)MAX_TASKS ? (int64_t)tasks[id].ev_len : 0;
}

int64_t rt_task_log_kind(int64_t id, int64_t i)
{
    return id >= 0 && id < (int64_t)MAX_TASKS && i >= 0 && (size_t)i < tasks[id].ev_len ? tasks[id].ev_kind[i] : -1;
}

int64_t rt_task_log_val(int64_t id, int64_t i)
{
    return id >= 0 && id < (int64_t)MAX_TASKS && i >= 0 && (size_t)i < tasks[id].ev_len ? tasks[id].ev_val[i] : 0;
}

int64_t rt_task_fuel(int64_t id)
{
    return id >= 0 && id < (int64_t)MAX_TASKS ? tasks[id].ctx.head.fuel_used : -1;
}

/* True while a preemptible task runs: code that keeps state in globals shared by every context
 * (probes, first access of module state) must not run then. */
bool rt_task_preemptible(void)
{
    return preempt_on && current >= 0;
}

void rt_task_preempt_enable(int64_t ticks)
{
    if (ticks < 1) rt_panic("preempt quantum");
    quantum = ticks;
    preempt_on = true;
}

int64_t rt_task_preemptions(void)
{
    return preemptions;
}

/* Called from the timer interrupt (vector 32, interrupts off, on the running task's stack),
 * after the EOI: a quantum of `quantum` ticks ends the task's turn. The switch saves this
 * handler's frame on the task's own stack, so a later switch back finishes the handler and
 * irets to the interrupted instruction. */
void rt_sched_tick(void)
{
    struct task *t;
    if (current < 0 || !preempt_on || tasks[current].done) return;
    if (++quantum_left < quantum) return;
    quantum_left = 0;
    preemptions++;
    t = &tasks[current];
    t->state = TASK_PREEMPTED;
    task_switch(&t->rsp, sched_rsp);
}

int64_t rt_task_out_len(int64_t id)
{
    return id >= 0 && id < (int64_t)MAX_TASKS ? (int64_t)tasks[id].out_len : 0;
}

uint8_t rt_task_out_byte(int64_t id, int64_t i)
{
    return id >= 0 && id < (int64_t)MAX_TASKS && i >= 0 && (size_t)i < tasks[id].out_len ? tasks[id].out[i] : 0u;
}

/* The console service for the running task (SPEC-07 SEC-CAP-13). `write` has no covering
 * capability (OQ-299), so it never returns denied; read, read_line and window need
 * console.input (1) and raw needs console.raw (2). A call no grant covers returns the error
 * alternative `denied` (tag 1 of console.ConsoleError), not a fault. */
bool rt_task_covered(uint32_t cap)
{
    return current >= 0 && (tasks[current].caps & cap) != 0u;
}

cint_status rt_task_write(const uint8_t *bytes, int64_t n)
{
    struct task *t;
    if (current < 0 || n < 0) return CINT_REFUSED;
    t = &tasks[current];
    if ((uint64_t)n > OUT_BYTES - t->out_len) return CINT_REFUSED; /* the service's `closed` */
    memcpy(t->out + t->out_len, bytes, (size_t)n);
    t->out_len += (size_t)n;
    return CINT_OK;
}

/* ---- K5: steps ---- */

/* Runs one step of task id in its own address space (CR3 is the kernel's again when this
 * returns). Returns 0 when the step ended with a request, 3 when the task faulted (its record is
 * printed here, as task_run does), -1 when it cannot run. A step that ends without a request is
 * a fault, host.error.step: a task that says nothing has not said it is done. */
int64_t rt_task_step(int64_t id)
{
    struct task *t;
    uint64_t kroot;
    if (id < 0 || id >= (int64_t)MAX_TASKS || !tasks[id].created || tasks[id].done || current >= 0) return -1;
    t = &tasks[id];
    arm(t, (int)id, step_entry);
    t->req_set = false;
    current = (int)id;
    kroot = cr3_read();
    if (t->root != 0u) cr3_write(t->root);
    task_switch(&sched_rsp, t->rsp);
    cr3_write(kroot);
    current = -1;
    if (t->state == TASK_STEPPED && !t->req_set) {
        cint_fault_record *rec = rt_record_begin((cint_ctx *)&t->ctx, rt_placeholder_site(t->ctx.program), (uint16_t)CINT_E_UNSUPPORTED);
        if (rec != NULL) {
            rec->stack_count = 0u;
            rt_record_op(rec, "host");
            rt_record_op(rec, "error");
            rt_record_op(rec, "step");
            rt_record_operand(rec, CINT_TAG_I64, (uint64_t)id + 1u);
        }
        t->state = TASK_FAULTED;
    }
    if (t->state == TASK_FAULTED) {
        t->done = true;
        rt_puts("task ");
        rt_put_dec((uint64_t)id + 1u);
        rt_puts(" faulted\n");
        rt_print_fault(&t->ctx.fault);
        return 3;
    }
    return 0;
}

/* The one request of the running step: kind 0 to 15, three arguments. The kernel serves it. */
cint_status rt_task_request(int64_t kind, int64_t a, int64_t b, int64_t v)
{
    struct task *t;
    if (current < 0 || kind < 0 || kind > 15) return CINT_REFUSED;
    t = &tasks[current];
    if (t->req_set) return CINT_REFUSED;
    t->req[0] = kind;
    t->req[1] = a;
    t->req[2] = b;
    t->req[3] = v;
    t->req_set = true;
    return CINT_OK;
}

int64_t rt_task_req(int64_t id, int64_t i)
{
    return id >= 0 && id < (int64_t)MAX_TASKS && i >= 0 && i < 4 ? tasks[id].req[i] : -1;
}

/* What the next step sees in its args after the role and network digits: up to 14 bytes. */
void rt_task_args_set(int64_t id, const uint8_t *src, int64_t n)
{
    struct task *t;
    if (id < 0 || id >= (int64_t)MAX_TASKS || n < 0 || n > 14) return;
    t = &tasks[id];
    memcpy(t->args + 2, src, (size_t)n);
    t->args_len = 2u + (size_t)n;
}

int64_t rt_task_fuel_total(int64_t id)
{
    return id >= 0 && id < (int64_t)MAX_TASKS ? tasks[id].fuel_total : -1;
}

void rt_task_fuel_set(int64_t id, int64_t v)
{
    if (id >= 0 && id < (int64_t)MAX_TASKS && v >= 0) tasks[id].fuel_total = v;
}

/* The root of the page tables of task id (0: the kernel's own). Only a frame of the pool (32 to 96
 * MiB, which the kernel builds the tables in) is accepted. */
cint_status rt_task_space(int64_t id, int64_t root)
{
    if (id < 0 || id >= (int64_t)MAX_TASKS) return CINT_REFUSED;
    if (root != 0 && (root % 4096 != 0 || root < (int64_t)RT_POOL_BASE || root >= (int64_t)rt_pool_end)) return CINT_REFUSED;
    tasks[id].root = (uint64_t)root;
    return CINT_OK;
}

struct cint_ctx *rt_task_ctx_of(int64_t id)
{
    return id >= 0 && id < (int64_t)MAX_TASKS ? (struct cint_ctx *)&tasks[id].ctx : NULL;
}

/* A task reaches its private pages through these two: slot 0 to 7 of the region at 0x40000000, a
 * 64-bit word index 0 to 511. The access is made by the hardware through the CR3 that rt_task_step
 * loaded, so a page that is not in this task's tables is a #PF, and the trap record becomes the
 * task's fault (RT_ST_TRAP). The task never holds an address. */
cint_status rt_page_op(int64_t slot, int64_t idx, bool store, int64_t v, int64_t *out)
{
    uint64_t va;
    uint64_t r;
    if (current < 0 || slot < 0 || slot > 7 || idx < 0 || idx > 511) return CINT_REFUSED;
    va = 0x40000000u + (uint64_t)slot * 4096u + (uint64_t)idx * 8u;
    if (store)
        r = rt_probe(trap_probe_store, va, (uint64_t)v);
    else
        r = rt_probe(trap_probe_load, va, 0u);
    if (rt_trap_record_len() != 0) return RT_ST_TRAP;
    if (!store) *out = (int64_t)r;
    return CINT_OK;
}
