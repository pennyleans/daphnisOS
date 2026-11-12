/* user/segv.S: writes one line, then loads from address 0: SIGSEGV. */
    .text
    .global _start
_start:
    movl $1, %eax
    movl $1, %edi
    leaq msg(%rip), %rsi
    movl $len, %edx
    syscall
    xorl %ecx, %ecx
    movq (%rcx), %rax
    movl $60, %eax               /* not reached */
    xorl %edi, %edi
    syscall

    .section .rodata
msg: .ascii "about to fault\n"
    len = . - msg
