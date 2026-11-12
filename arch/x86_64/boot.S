/* arch/x86_64/boot.S: Multiboot 1 and Multiboot 2 entry, 32-bit protected mode to 64-bit long mode.
 *
 * QEMU's -kernel loads a Multiboot 1 image in 32-bit protected mode (the ELF is converted
 * to elf32-i386 by the build, docs/boot.md). GRUB's multiboot2 command loads the same
 * kernel.elf (ELF64) through the Multiboot 2 header below, also in 32-bit protected mode.
 * Either way the stub saves the magic (mb_magic) and ebx, the address of the loader's information
 * block (mb_info); rt/boot.c copies the block once before main (docs/memory.md).
 * This stub: clears both bss ranges (.bss and .high_bss), builds an identity
 * map of the first 1 GiB and of 2 to 8 GiB with 2 MiB pages (the first three 2 MiB with 4 KiB pages: the image's low window and its high window of 4 MiB; 1 to 2 GiB left to src/paging.ci), enables PAE and long mode, loads a flat GDT, and
 * jumps to rt_start (rt/start.c) in 64-bit mode. No interrupts: IF stays clear. CR0.WP and
 * EFER.NXE are set so read-only and no-execute pages bind the kernel too. The null page and
 * the stack guard page are left not present. The GDT has a free 16-byte slot at 0x18 for the
 * TSS, which cint code fills (src/tss.ci) before ltr, then the ring 3 data and code segments
 * at 0x28 and 0x30, in the order syscall and sysretq expect (U1-1).
 * Build with -DBOOT_TRACE to write 'B' (entry) and 'L' (long mode) to COM1, to place a
 * triple fault; the default image writes nothing before cint code runs. */

#define MB_MAGIC 0x1BADB002
#define MB_FLAGS 0x00000002          /* bit 1: ask for the memory map (src/memmap.ci reads it) */

    .section .multiboot, "a"
    .align 4
    .long MB_MAGIC
    .long MB_FLAGS
    .long -(MB_MAGIC + MB_FLAGS)

#define MB2_MAGIC 0xE85250D6
#define MB2_ARCH 0                   /* i386 protected mode */
    .align 8                         /* Multiboot 2: 8-byte aligned, in the first 32 KiB */
mb2_header:
    .long MB2_MAGIC
    .long MB2_ARCH
    .long mb2_header_end - mb2_header
    .long -(MB2_MAGIC + MB2_ARCH + (mb2_header_end - mb2_header))
#ifdef RT_USER
    .word 5, 1                       /* framebuffer tag (F-1, rt/fb.c): type 5, flags 1 (optional), size 20 */
    .long 20
    .long 0, 0, 32                   /* HX-0 A: no width or height asked; the loader's or the firmware's mode */
    .align 8
#endif
    .word 0, 0                       /* end tag: type 0, flags 0, size 8 */
    .long 8
mb2_header_end:

    .section .text
    .code32
    .global _start
_start:
    cli
    cld                          /* DF is undefined at entry; the SysV ABI wants it clear */
    movl %eax, mb_magic          /* which loader: rt/boot.c reads the block by its protocol */
    cmpl $0x2BADB002, %eax       /* Multiboot 1 */
    je 4f
    cmpl $0x36D76289, %eax       /* Multiboot 2 */
    jne 3f                       /* not entered by a Multiboot loader: stop */
4:  movl %ebx, mb_info           /* the loader's information block, either protocol (rt/boot.c) */
    movl $stack_top, %esp
#if defined(BOOT_TRACE) && !defined(RT_CAPTURE)
    movw $0x3F8, %dx
    movb $'B', %al
    outb %al, %dx
#endif

    movl $__bss_start, %edi
    movl $__bss_end, %ecx
    subl %edi, %ecx
    shrl $2, %ecx
    xorl %eax, %eax
    rep stosl
    movl $__high_bss_start, %edi /* the emitted cint's bss, in the high window (linker.ld) */
    movl $__high_bss_end, %ecx
    subl %edi, %ecx
    shrl $2, %ecx
    rep stosl

    /* PML4[0] -> PDPT; PDPT[0] -> PD; PD[0] -> PT (4 KiB pages over the first 2 MiB, which
     * hold the image and the stack, with the stack's guard page left not present);
     * PD[1..511] = i * 2 MiB, present, writable, huge. */
    movl $pdpt, %eax
    orl $3, %eax
    movl %eax, pml4
    movl $pd, %eax
    orl $3, %eax
    movl %eax, pdpt
    movl $pt, %eax
    orl $3, %eax
    movl %eax, pd
    movl $pd + 8, %edi
    movl $0x200083, %eax
    movl $511, %ecx
1:  movl %eax, (%edi)
    movl $0, 4(%edi)
    addl $0x200000, %eax
    addl $8, %edi
    loop 1b
    movl $pt, %edi
    movl $3, %eax
    movl $512, %ecx
1:  movl %eax, (%edi)
    movl $0, 4(%edi)
    addl $0x1000, %eax
    addl $8, %edi
    loop 1b
    /* M-3: PDPT[2..7] -> pd_hi[k]: 2 MiB pages over 2 to 8 GiB, the reach of the pool (src/pool.ci). PDPT[1]
     * stays empty: 1 to 2 GiB is src/paging.ci's and the fault probes' region. */
    movl $pdpt + 16, %edi
    movl $pd_hi, %eax
    orl $3, %eax
    movl $6, %ecx
1:  movl %eax, (%edi)
    movl $0, 4(%edi)
    addl $0x1000, %eax
    addl $8, %edi
    loop 1b
    movl $pd_hi, %edi
    movl $0x80000083, %eax       /* 2 GiB, present, writable, huge */
    movl $0, %edx
    movl $3072, %ecx
1:  movl %eax, (%edi)
    movl %edx, 4(%edi)
    addl $0x200000, %eax
    adcl $0, %edx
    addl $8, %edi
    loop 1b
    movl $pt_high, %edi          /* PD[1] -> PT_HIGH: 4 KiB pages over 2 to 4 MiB, the image's high window (linker.ld) */
    movl $0x200003, %eax
    movl $512, %ecx
1:  movl %eax, (%edi)
    movl $0, 4(%edi)
    addl $0x1000, %eax
    addl $8, %edi
    loop 1b
    movl $pt_high, %eax
    orl $3, %eax
    movl %eax, pd + 8
    movl $pt_high2, %edi         /* PD[2] -> PT_HIGH2: 4 KiB pages over 4 to 6 MiB, the high window's second half */
    movl $0x400003, %eax
    movl $512, %ecx
1:  movl %eax, (%edi)
    movl $0, 4(%edi)
    addl $0x1000, %eax
    addl $8, %edi
    loop 1b
    movl $pt_high2, %eax
    orl $3, %eax
    movl %eax, pd + 16
    movl $stack_guard, %eax      /* a stack overflow faults instead of corrupting the tables */
    shrl $12, %eax
    movl $0, pt(,%eax,8)
    movl $0, pt                  /* the null page is not present: a null access is a #PF */

    movl $pml4, %eax
    movl %eax, %cr3
    movl %cr4, %eax
    orl $0x20, %eax              /* CR4.PAE */
    movl %eax, %cr4
    movl $0xC0000080, %ecx       /* EFER */
    rdmsr
    orl $0x900, %eax             /* LME | NXE */
    wrmsr
    movl %cr0, %eax
    orl $0x80010001, %eax        /* PG | WP | PE */
    movl %eax, %cr0
    lgdt gdt_ptr
    ljmp $0x08, $long_entry

    .code64
long_entry:
    movw $0x10, %ax
    movw %ax, %ds
    movw %ax, %es
    movw %ax, %fs
    movw %ax, %gs
    movw %ax, %ss
    movq $stack_top, %rsp
    xorl %ebp, %ebp
#if defined(BOOT_TRACE) && !defined(RT_CAPTURE)
    movw $0x3F8, %dx
    movb $'L', %al
    outb %al, %dx
#endif
    call rt_start
2:  hlt
    jmp 2b

    .code32
3:  hlt                          /* wrong loader */
    jmp 3b
    .code64

    .section .data
    .align 8
    .global gdt
    .global mb_info
    .global mb_magic
mb_info: .long 0
mb_magic: .long 0
    .align 8
gdt:
    .quad 0                      /* null */
    .quad 0x00AF9A000000FFFF     /* 0x08: 64-bit code, DPL 0 */
    .quad 0x00CF92000000FFFF     /* 0x10: data, DPL 0 */
    .quad 0, 0                   /* 0x18: 64-bit TSS descriptor, filled by cint, then ltr */
    .quad 0x00CFF2000000FFFF     /* 0x28: user data, DPL 3 (selector 0x2B; arch/x86_64/user.S) */
    .quad 0x00AFFA000000FFFF     /* 0x30: user 64-bit code, DPL 3 (selector 0x33) */
gdt_ptr:
    .word gdt_ptr - gdt - 1
    .long gdt

    .section .bss
    .align 4096
    .global pml4, pdpt, pd, pt, pt_high, pt_high2   /* contiguous: rt/ lets cint read these six pages (rt/phys.c) */
pml4:   .skip 4096
pdpt:   .skip 4096
pd:     .skip 4096
pt:     .skip 4096
pt_high: .skip 4096              /* 4 KiB pages over 2 to 4 MiB, the image's high window; rt_wx_init gives them their rights */
pt_high2: .skip 4096             /* and over 4 to 6 MiB, its second half (the emitted cint passed 4 MiB: PR 499, gcc 16) */
    .global pd_hi
pd_hi:  .skip 24576              /* M-3: six page directories, 2 MiB pages over 2 to 8 GiB (after the six pages rt/phys.c reads) */
    .global stack_guard
stack_guard: .skip 4096          /* not present, see above */
    .skip 131072                 /* the C stack: 128 KiB (docs/runtime.md, stack budget) */
stack_top:
