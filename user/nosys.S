/* user/nosys.S: system call 9999 does not exist: -ENOSYS (-38); exits with 38. */
    .text
    .global _start
_start:
    movl $9999, %eax
    syscall
    negq %rax
    movq %rax, %rdi
    movl $60, %eax
    syscall
