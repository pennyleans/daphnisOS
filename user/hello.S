/* user/hello.S: writes one line to stdout and exits 0. No libc: Linux x86-64 system calls. */
    .text
    .global _start
_start:
    movl $1, %eax                /* write(1, msg, len) */
    movl $1, %edi
    leaq msg(%rip), %rsi
    movl $len, %edx
    syscall
    movl $60, %eax               /* exit(0) */
    xorl %edi, %edi
    syscall

    .section .rodata
msg: .ascii "hello from ring 3\n"
    len = . - msg
