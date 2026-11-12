/* user/efault.S: write(1, NULL, 5) must fail with -EFAULT (-14); exits with 14. */
    .text
    .global _start
_start:
    movl $1, %eax
    movl $1, %edi
    xorl %esi, %esi
    movl $5, %edx
    syscall
    negq %rax
    movq %rax, %rdi
    movl $60, %eax
    syscall
