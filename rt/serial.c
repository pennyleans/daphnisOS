/* Shared COM1 output for CINT, faults and panics. Capture builds encrypt here;
 * development builds retain direct serial output. This path works after a
 * fault, when CINT cannot run. UART initialization remains in src/serial.ci. */
#include "rt.h"

void rt_serial_byte(uint8_t c)
{
#ifdef RT_CAPTURE
    rt_capture_byte(c);
#else
    rt_console_byte(c);   /* HW-3: the ring, COM1 when it answers, the screen with daphnis.console=screen */
#endif
}

void rt_puts(const char *s)
{
    while (*s != '\0') rt_serial_byte((uint8_t)*s++);
}

void rt_put_hex_byte(uint8_t b)
{
    static const char digits[] = "0123456789abcdef";
    rt_serial_byte((uint8_t)digits[b >> 4]);
    rt_serial_byte((uint8_t)digits[b & 15u]);
}

void rt_put_dec(uint64_t v)
{
    char buf[20];
    unsigned n = 0u;
    do {
        buf[n++] = (char)('0' + (unsigned)(v % 10u));
        v /= 10u;
    } while (v != 0u);
    while (n > 0u) rt_serial_byte((uint8_t)buf[--n]);
}
