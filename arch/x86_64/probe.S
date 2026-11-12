/* arch/x86_64/probe.S: instructions that fault on purpose, for the trap flavors and the
 * memory checks (docs/traps.md, docs/memory.md), and the few privileged instructions cint
 * cannot express: ltr, invlpg, a CR3 read, the PAT. Reached from cint through rt/host.c. */

/* The probes fault on purpose. Each saves RSP in trap_probe_rsp first. rt_trap_dispatch
 * recognizes a fault raised while a probe runs (rt_probe_active), records it, and resumes at
 * trap_resume, a ret, with RSP set back to trap_probe_rsp: the probes return to their caller
 * even after a stack overflow or a failed fetch. A probe that does not fault just returns. */
    .macro PROBE name
    .global \name
\name:
    movq %rsp, trap_probe_rsp(%rip)
    .endm
    .section .text
    .global trap_probes
trap_probes:
    PROBE trap_probe_de              /* void trap_probe_de(void): divide error, vector 0 */
    xorl %ecx, %ecx
    xorl %edx, %edx
    movl $1, %eax
    divl %ecx
    PROBE trap_probe_ud              /* invalid opcode, vector 6 */
    ud2
    PROBE trap_probe_pf              /* void (uint64_t addr): a write at addr + 0x18, vector 14 */
    movq %rax, 0x18(%rdi)
    PROBE trap_probe_nmi             /* int 2: the NMI gate, taken on its IST stack */
    int $2
    ret
    PROBE trap_probe_stack           /* push until the guard page: a stack overflow */
1:  pushq $0
    jmp 1b
    PROBE trap_probe_load            /* uint64_t (uint64_t addr): a load through the page tables */
    movq (%rdi), %rax
    ret
    PROBE trap_probe_store           /* void (uint64_t addr, uint64_t v): a store */
    movq %rsi, (%rdi)
    ret
    PROBE trap_probe_exec            /* void (uint64_t addr): a call, so a fetch can fault */
    call *%rdi
    .global trap_resume
trap_resume:
    ret

    .global tss_load
tss_load:                        /* void tss_load(void): ltr, the TSS descriptor is at 0x18 */
    movw $0x18, %ax
    ltr %ax
    ret

    .global vm_invlpg
vm_invlpg:                       /* void vm_invlpg(uint64_t va): drop one TLB entry */
    invlpg (%rdi)
    ret

    .global cr3_write
cr3_write:                       /* void cr3_write(uint64_t root): load another address space (K5) */
    movq %rdi, %cr3
    ret

    .global cr3_read
cr3_read:                        /* uint64_t cr3_read(void): the physical address of the PML4 */
    movq %cr3, %rax
    ret

    .global pat_read
pat_read:                        /* uint64_t pat_read(void): IA32_PAT (rt/fb.c, DS D-FB) */
    movl $0x277, %ecx
    rdmsr
    shlq $32, %rdx
    orq %rdx, %rax
    ret

    .global pat_write
pat_write:                       /* void pat_write(uint64_t pat) */
    movl $0x277, %ecx
    movl %edi, %eax
    movq %rdi, %rdx
    shrq $32, %rdx
    wrmsr
    ret
