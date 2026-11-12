/* arch/x86_64/user.S: ring 3 (U1-1, U1-2; docs/user.md). The syscall MSRs, SSE, the syscall entry,
 * and the two halves of a user turn: user_enter leaves the kernel for ring 3, user_leave comes back.
 *
 * A user turn is a call: rt/user.c calls user_enter(frame, root, fx, fs), which saves the kernel's
 * callee-saved registers and stack pointer, restores the process's FPU and SSE state from fx and
 * its FS base, loads its page tables, copies the saved frame (struct rt_trap_frame, rt/rt.h) onto
 * the entry stack and iretqs to ring 3. Interrupts are on in ring 3 only. Whatever brings the CPU
 * back to ring 0 (a syscall, an exception, an interrupt) lands in trap_common (trap.S) with a frame
 * of the same layout, and rt_trap_dispatch hands a ring 3 frame to rt/user.c, which saves it and
 * the FPU state (fx_save; the kernel is built -mgeneral-regs-only, so it has not touched it) and
 * calls user_leave(kind): the kernel's page tables and stack come back and user_enter returns kind.
 * The entry stack is abandoned each time, so nothing of a turn is left on it. One CPU, interrupts
 * off in ring 0: the three words below need no lock. */

    .section .text

    .global user_cpu_init
user_cpu_init:                   /* void user_cpu_init(void) */
    movl $0xC0000080, %ecx       /* EFER.SCE: syscall enabled */
    rdmsr
    orl $1, %eax
    wrmsr
    movl $0xC0000081, %ecx       /* STAR: syscall CS 0x08 (SS 0x10); bits 63:48 0x20 for a later sysretq */
    xorl %eax, %eax
    movl $0x00200008, %edx
    wrmsr
    movl $0xC0000082, %ecx       /* LSTAR: the entry below */
    leaq syscall_entry(%rip), %rax
    movq %rax, %rdx
    shrq $32, %rdx
    wrmsr
    movl $0xC0000084, %ecx       /* FMASK: clear TF, IF, DF, IOPL, NT and AC on entry */
    movl $0x47700, %eax
    xorl %edx, %edx
    wrmsr
    movq %cr0, %rax              /* SSE for ring 3: CR0.EM and TS off, MP on */
    andq $-13, %rax
    orq $2, %rax
    movq %rax, %cr0
    movq %cr4, %rax
    orq $0x600, %rax             /* CR4.OSFXSR, OSXMMEXCPT: fxsave, fxrstor and #XM */
    movq %rax, %cr4
    ret

    .global fx_save
fx_save:                         /* void fx_save(void *area): 512 bytes, 16-aligned */
    fxsave64 (%rdi)
    ret

/* syscall: RCX holds the user RIP, R11 the user RFLAGS, RSP is still the user's. Build the frame
 * an interrupt from ring 3 would push, vector 256, and go the trap path. */
syscall_entry:
    movq %rsp, user_rsp_scratch(%rip)
    movq user_entry_top(%rip), %rsp
    pushq $0x2B                  /* SS */
    pushq user_rsp_scratch(%rip) /* RSP */
    pushq %r11                   /* RFLAGS */
    pushq $0x33                  /* CS */
    pushq %rcx                   /* RIP */
    pushq $0                     /* error code */
    pushq $256                   /* vector: a system call */
    jmp trap_common

    .global user_enter
user_enter:                      /* uint64_t user_enter(const struct rt_trap_frame *f, uint64_t root, const void *fx, uint64_t fs) */
    pushq %rbp
    pushq %rbx
    pushq %r12
    pushq %r13
    pushq %r14
    pushq %r15
    movq %rsp, user_kernel_rsp(%rip)
    movq %cr3, %rax
    movq %rax, user_kernel_cr3(%rip)
    fxrstor64 (%rdx)             /* the process's x87, MXCSR and XMM state */
    movq %rcx, %rax              /* MSR_FS_BASE = fs */
    movq %rcx, %rdx
    shrq $32, %rdx
    movl $0xC0000100, %ecx
    wrmsr
    movq %rsi, %rdx              /* the process's root */
    movq user_entry_top(%rip), %rsp
    subq $176, %rsp              /* the frame: 22 words */
    movq %rdi, %rsi              /* copy it onto the entry stack, so a fault in iretq lands there */
    movq %rsp, %rdi
    movl $22, %ecx
    rep movsq
    movq %rdx, %cr3              /* the image and the entry stack are mapped in every user space */
    popq %r15
    popq %r14
    popq %r13
    popq %r12
    popq %r11
    popq %r10
    popq %r9
    popq %r8
    popq %rbp
    popq %rdi
    popq %rsi
    popq %rdx
    popq %rcx
    popq %rbx
    popq %rax
    addq $16, %rsp               /* vector and error code */
    iretq

    .global user_leave
user_leave:                      /* void user_leave(uint64_t kind): returns from user_enter */
    movq user_kernel_cr3(%rip), %rax
    movq %rax, %cr3
    movq user_kernel_rsp(%rip), %rsp
    movq %rdi, %rax
    popq %r15
    popq %r14
    popq %r13
    popq %r12
    popq %rbx
    popq %rbp
    ret

    .section .bss
    .align 8
user_rsp_scratch: .skip 8
user_kernel_rsp:  .skip 8
user_kernel_cr3:  .skip 8
