/* arch/x86_64/rng.S: A-3, the CPU's random source, called from rt/host.c (SysV ABI). Reached from cint
 * through the rdrand rows src/rng.ci imports. */

    .section .text
    .global cpu_rdrand_present
    .type cpu_rdrand_present, @function
cpu_rdrand_present:              /* uint64_t cpu_rdrand_present(void): CPUID.1:ECX bit 30, 1 or 0 */
    pushq %rbx
    movl $1, %eax
    xorl %ecx, %ecx
    cpuid
    movl %ecx, %eax
    shrl $30, %eax
    andl $1, %eax
    popq %rbx
    ret

    .global cpu_rdrand64
    .type cpu_rdrand64, @function
cpu_rdrand64:                    /* uint64_t cpu_rdrand64(uint64_t *dst): one RDRAND; 1 with a value (CF), else 0 */
    rdrand %rax
    jnc 1f
    movq %rax, (%rdi)
    movl $1, %eax
    ret
1:  xorl %eax, %eax
    ret

    .global cpu_cpuid
    .type cpu_cpuid, @function
cpu_cpuid:                       /* void cpu_cpuid(uint32_t leaf, uint32_t out[4]): CPUID leaf, subleaf 0: EAX, EBX, ECX, EDX (KF-3a) */
    pushq %rbx
    movl %edi, %eax
    xorl %ecx, %ecx
    cpuid
    movl %eax, 0(%rsi)
    movl %ebx, 4(%rsi)
    movl %ecx, 8(%rsi)
    movl %edx, 12(%rsi)
    popq %rbx
    ret
