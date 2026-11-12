/* Link address 1 MiB, identity mapped by boot.S. Two windows: the low one, [1 MiB, 2 MiB), holds everything
 * the CPU touches with a process's page tables loaded (the runtime's code and data, the stacks and the tables:
 * a user space maps only the low 2 MiB of the kernel, src/uvm.ci); the high one, [2 MiB, 6 MiB), holds what
 * only the kernel's own tables reach: all of the emitted cint (every em_*.o: code, read-only data, data,
 * bss). boot.S maps both with 4 KiB pages (pt, and pt_high and pt_high2 for the high window's two halves) and
 * clears both bss ranges; rt_wx_init gives each page its section's rights. Last comes the pool: every
 * `.high.data` input (the module-state pool of rt/ctx.c, the capture keys), data the kernel's own context
 * alone touches. It follows the high window and may run past 6 MiB into pd[3], boot.S's 2 MiB page over
 * [6 MiB, 8 MiB), which rt_wx_init makes no-execute: writable data either side. The high window was [2 MiB,
 * 4 MiB) until the emitted cint of gcc-hdesk passed 4 MiB (PR 499 with gcc 13, 3 KiB over; gcc 16, 93 KiB).
 * A K5 task space maps only the low 4 MiB, but a task holds its module state in a pool of its own
 * (rt/task.c), and the flavors big enough to cross 4 MiB run no kernel task (RT_MAX_TASKS 1); rt_task_create
 * refuses a task when the high window ends past 4 MiB. */
ENTRY(_start)
SECTIONS
{
    . = 1M;
    .multiboot : { KEEP(*(.multiboot)) }
    /* K5: code, read-only data and data each start on a page, so that rt_wx_init (rt/phys.c) can give each
     * page the rights of its section: code is readable and executable, nothing is writable and executable */
    . = ALIGN(4096);
    __text_start = .;
    .text : { EXCLUDE_FILE(*/em_*.o) *(.text .text.*) }
    . = ALIGN(4096);
    __text_end = .;
    .rodata : { EXCLUDE_FILE(*/em_*.o) *(.rodata .rodata.*) }
    . = ALIGN(4096);
    __rodata_end = .;
    .data : { EXCLUDE_FILE(*/em_*.o) *(.data .data.*) }
    .bss : ALIGN(4096) {
        __bss_start = .;
        EXCLUDE_FILE(*/em_*.o) *(.bss .bss.*) EXCLUDE_FILE(*/em_*.o) *(COMMON)
        . = ALIGN(4);
        __bss_end = .;
    }
    ASSERT(__bss_end < 2M, "the low window (code, data, tables, stacks) must end below 2 MiB, where a user space starts")
    . = 2M;
    __high_start = .;
    .high_text : { */em_*.o(.text .text.*) }
    . = ALIGN(4096);
    __high_text_end = .;
    .high_rodata : { */em_*.o(.rodata .rodata.*) }
    . = ALIGN(4096);
    __high_rodata_end = .;
    .high_data : { */em_*.o(.data .data.*) }
    .high_bss : ALIGN(16) {
        __high_bss_start = .;
        */em_*.o(.bss .bss.*) */em_*.o(COMMON)
        . = ALIGN(4);
        __high_bss_end = .;
    }
    __high_end = .;
    ASSERT(__high_end <= 6M, "the high window (the emitted cint) must end by 6 MiB, where pt_high2 ends")
    /* The pool after the high window, not inside its bound: with gcc 16 the emitted cint of gcc-user is about 80 KiB
     * larger than with gcc 13, and the window's 2 MiB held the 256 KiB pool too (Arch, PR 346, 0x403000). */
    .high_pool : ALIGN(16) { *(.high.data) }
    . = ALIGN(4096);
    __image_end = .;
    ASSERT(__image_end <= 8M, "the image (the state pool last) must end by 8 MiB, the end of pd[3]'s 2 MiB page")
    /DISCARD/ : { *(.eh_frame) *(.comment) *(.note.*) *(.got) *(.got.plt) *(.igot.plt) *(.iplt) *(.rela.*) }
}
