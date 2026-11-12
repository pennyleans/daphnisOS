/* arch/x86_64/initrd.S: an embedded user image, a cpio newc archive (tools/mkcpio.py), when the
 * build passes its path as INITRD; empty otherwise. Since U1-5 the image is a loader module
 * (QEMU -initrd, GRUB module2; rt/boot.c finds it) and the build embeds nothing, so a kernel's
 * bytes do not depend on the programs it runs. rt/user.c reads whichever is there for cint
 * through initrd_read. Only the user flavor links this file (Makefile ASM_user). */
    .section .rodata
    .balign 16
    .global initrd_start, initrd_end
initrd_start:
#ifdef INITRD
    .incbin INITRD
#endif
initrd_end:
