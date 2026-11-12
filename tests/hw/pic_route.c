/* tests/hw/pic_route.c: rt/pic.h's answer for vectors 39 and 47 (review on PR 282): a NIC routed to IRQ 7 or 15
 * is genuine when its in-service bit is set and gets the routed path's mask and EOI; a spurious IRQ 7 takes no EOI;
 * a spurious IRQ 15 owes the master its cascade's EOI. check.sh builds it with gcc and clang. */
#include <assert.h>
#include <stdio.h>
#include "../../rt/pic.h"

int main(void)
{
    assert(rt_pic_low_line(39u, 0x80u, 0x00u) == RT_PIC_GENUINE);       /* IRQ 7 in service: the NIC's */
    assert(rt_pic_low_line(39u, 0x7Fu, 0xFFu) == RT_PIC_SPURIOUS);      /* not in service: spurious, no EOI */
    assert(rt_pic_low_line(39u, 0x00u, 0x80u) == RT_PIC_SPURIOUS);      /* the slave's bit is not IRQ 7's */
    assert(rt_pic_low_line(47u, 0x04u, 0x80u) == RT_PIC_GENUINE);       /* IRQ 15 in service on the slave */
    assert(rt_pic_low_line(47u, 0x84u, 0x00u) == RT_PIC_SPURIOUS_SLAVE);  /* spurious: the master's EOI only */
    printf("pic_route: 5 checks, 0 failed\n");
    return 0;
}
