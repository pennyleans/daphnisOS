/* user/args.S: writes argv[0] and a newline, exits with argc. Reads the Linux initial stack:
 * argc at (%rsp), argv[0] at 8(%rsp). */
    .text
    .global _start
_start:
    movq (%rsp), %r12            /* argc */
    movq 8(%rsp), %rsi           /* argv[0] */
    xorl %edx, %edx
1:  cmpb $0, (%rsi,%rdx)         /* strlen */
    je 2f
    incq %rdx
    jmp 1b
2:  movl $1, %eax
    movl $1, %edi
    syscall
    movl $1, %eax
    movl $1, %edi
    leaq nl(%rip), %rsi
    movl $1, %edx
    syscall
    movl $60, %eax
    movq %r12, %rdi
    syscall

    .section .rodata
nl: .ascii "\n"
