/* arch/x86_64/trap.S: exception and interrupt entry, IDT load, CR2 read, and a wait-for-interrupt
 * (the fault probes are in probe.S). Vectors 0 to 31 and the PIC's 32 to 47 (the PIT is 32) each have a stub that
 * normalizes the frame (a dummy error code where the CPU pushes none, then the vector), saves
 * every general register, and calls rt_trap_dispatch (rt/trap.c) with a pointer to the frame.
 * IF is clear everywhere except between the sti and the cli of cpu_wait_irq, and while a task
 * runs in the preemptive image (rt/task.c). Long mode
 * interrupts always push SS, RSP, RFLAGS, CS, RIP, so iretq restores the stack too.
 * Stack at the call: 15 registers (120) + vector (8) + error code (8) + 5 words (40) = 176,
 * a multiple of 16, and the CPU aligns RSP to 16 before pushing, as the SysV ABI wants. */

    .section .text

    .macro TRAP v, err=0
trap_\v:
    .if \err == 0
    pushq $0
    .endif
    pushq $\v
    jmp trap_common
    .endm

    .irp v, 0,1,2,3,4,5,6,7,9,15,16,18,19,20,22,23,24,25,26,27,28,31,32,33,34,35,36,37,38,39,40,41,42,43,44,45,46,47
    TRAP \v
    .endr
    .irp v, 8,10,11,12,13,14,17,21,29,30
    TRAP \v, 1
    .endr

    .global trap_common          /* also the tail of the syscall entry (user.S) */
trap_common:
    pushq %rax
    pushq %rbx
    pushq %rcx
    pushq %rdx
    pushq %rsi
    pushq %rdi
    pushq %rbp
    pushq %r8
    pushq %r9
    pushq %r10
    pushq %r11
    pushq %r12
    pushq %r13
    pushq %r14
    pushq %r15
    cld
    movq %rsp, %rdi
    call rt_trap_dispatch
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

    .global idt_load
idt_load:                        /* void idt_load(const void *idtr) */
    lidt (%rdi)
    ret

    .global cr2_read
cr2_read:                        /* uint64_t cr2_read(void) */
    movq %cr2, %rax
    ret

    .global cpu_wait_irq
cpu_wait_irq:                    /* void cpu_wait_irq(void): returns after one interrupt */
    sti                          /* the instruction after sti runs before any interrupt */
    hlt
    cli
    ret

    .section .rodata
    .align 8
    .global trap_stub_table
trap_stub_table:                 /* the entry address of each stub, indexed by vector 0..47 */
    .irp v, 0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32,33,34,35,36,37,38,39,40,41,42,43,44,45,46,47
    .quad trap_\v
    .endr
