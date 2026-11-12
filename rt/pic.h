/* rt/pic.h: what an interrupt on IRQ 7 or IRQ 15 is (review on PR 282). The 8259 raises a spurious interrupt on
 * the lowest line of each chip, vector 39 on the master and 47 on the slave, when a request goes before it is
 * acknowledged; a PCI NIC may also be routed to either line (pci.irq_line takes 3 to 15 but 12). The in-service
 * register (OCW3 0x0B, then a read of the command port) tells them apart: a genuine interrupt has the line's bit 7
 * set. A spurious IRQ 7 takes no EOI; a spurious IRQ 15 owes the master one, for the cascade (IRQ 2) the slave
 * raised there. */
#ifndef RT_PIC_H
#define RT_PIC_H
#include <stdint.h>

enum { RT_PIC_SPURIOUS = 0, RT_PIC_SPURIOUS_SLAVE = 1, RT_PIC_GENUINE = 2 };

/* Vector 39 or 47 with the master's and the slave's in-service registers. */
static inline int rt_pic_low_line(unsigned vector, uint8_t isr_master, uint8_t isr_slave)
{
    if (vector == 39u) return (isr_master & 0x80u) ? RT_PIC_GENUINE : RT_PIC_SPURIOUS;
    return (isr_slave & 0x80u) ? RT_PIC_GENUINE : RT_PIC_SPURIOUS_SLAVE;
}
#endif
