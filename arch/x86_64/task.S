/* arch/x86_64/task.S: the context switch of the kernel tasks (rt/task.c). A task's whole
 * saved state is its callee-saved registers on its own stack plus the stack pointer, so
 * switching is: push them, store RSP, load the other RSP, pop them, ret. The ret goes to
 * wherever the other context last called task_switch, or, for a new task, to the address
 * rt/task.c put at the top of its stack. Interrupts are not touched here: the callers decide
 * (a yield disables them first, the timer handler runs with them off). */

    .section .text
    .global task_switch
    .type task_switch, @function
task_switch:                     /* void task_switch(uint64_t *save_rsp, uint64_t new_rsp) */
    pushq %rbp
    pushq %rbx
    pushq %r12
    pushq %r13
    pushq %r14
    pushq %r15
    movq %rsp, (%rdi)
    movq %rsi, %rsp
    popq %r15
    popq %r14
    popq %r13
    popq %r12
    popq %rbx
    popq %rbp
    ret
