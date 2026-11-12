/* user/spin.S: counts down from 2^27 (long enough that a timer tick always ends a turn
 * first), then writes one line and exits 0. */
    .text
    .global _start
_start:
    movl $0x8000000, %ecx
1:  decl %ecx
    jnz 1b
    movl $1, %eax
    movl $1, %edi
    leaq msg(%rip), %rsi
    movl $len, %edx
    syscall
    movl $231, %eax              /* exit_group(0) */
    xorl %edi, %edi
    syscall

    .section .rodata
msg: .ascii "spin done\n"
    len = . - msg
