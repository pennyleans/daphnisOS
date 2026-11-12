/* arch/x86_64/portio.S: port I/O and halt, called from rt/ (SysV ABI). Reached from cint
 * through rt/host.c, which binds the externs of src/portio.ci to these. */

    .section .text
    .global port_out8
    .type port_out8, @function
port_out8:                       /* void port_out8(uint16_t port, uint8_t value) */
    movw %di, %dx
    movb %sil, %al
    outb %al, %dx
    ret

    .global port_in8
    .type port_in8, @function
port_in8:                        /* uint8_t port_in8(uint16_t port) */
    movw %di, %dx
    inb %dx, %al
    movzbl %al, %eax
    ret

    .global cpu_halt
    .type cpu_halt, @function
cpu_halt:                        /* void cpu_halt(void): one hlt, interrupts stay off */
    hlt
    ret

    .global cpu_cli
    .type cpu_cli, @function
cpu_cli:                         /* void cpu_cli(void): interrupts off */
    cli
    ret

    .global cpu_sti
    .type cpu_sti, @function
cpu_sti:                         /* void cpu_sti(void): interrupts on */
    sti
    ret

    /* F-1 (rt/fb.c): the 16-bit Bochs display registers and the 32-bit PCI configuration ports */
    .global port_out16
    .type port_out16, @function
port_out16:                      /* void port_out16(uint16_t port, uint16_t value) */
    movw %di, %dx
    movw %si, %ax
    outw %ax, %dx
    ret

    .global port_in16
    .type port_in16, @function
port_in16:                       /* uint16_t port_in16(uint16_t port) */
    movw %di, %dx
    inw %dx, %ax
    movzwl %ax, %eax
    ret

    .global port_out32
    .type port_out32, @function
port_out32:                      /* void port_out32(uint16_t port, uint32_t value) */
    movw %di, %dx
    movl %esi, %eax
    outl %eax, %dx
    ret

    .global port_in32
    .type port_in32, @function
port_in32:                       /* uint32_t port_in32(uint16_t port) */
    movw %di, %dx
    inl %dx, %eax
    ret
    .text
    .global fb_fence
fb_fence:
    sfence
    mfence
    ret
