/* user/user.ld: the layout of the U1-1 test programs, fixed here so it does not depend on how the
 * host's binutils was configured (a default .note.gnu.property adds program headers and moves
 * .text; Arch's binutils 2.47 does that, Ubuntu's 2.42 does not). One PT_LOAD, read and execute,
 * holding the ELF header, the one program header, .text and .rodata, at 0x400000. */
ENTRY(_start)
PHDRS
{
    text PT_LOAD FILEHDR PHDRS FLAGS(5);
}
SECTIONS
{
    . = 0x400000 + SIZEOF_HEADERS;
    .text : { *(.text) } :text
    .rodata : { *(.rodata) } :text
    /DISCARD/ : { *(.note*) *(.comment) }
    .data : { *(.data) } :text
    .bss : { *(.bss) } :text
    ASSERT(SIZEOF(.data) == 0 && SIZEOF(.bss) == 0, "the U1-1 test programs have no writable data")
}
