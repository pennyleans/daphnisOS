/* user/ud.S: an invalid opcode: SIGILL. */
    .text
    .global _start
_start:
    ud2
