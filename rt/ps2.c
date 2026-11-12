/* rt/ps2.c: the 8042's bytes (F-2 and F-3, docs/specs/2026-11-05-f-surface.md section 4). IRQ 1 (vector
 * 33) and IRQ 12 (vector 44, rt/trap.c) read one byte from the controller's output buffer into one of two
 * rings of 256: the keyboard's, or the auxiliary device's (the mouse: status bit 5); cint drains them
 * through ps2_get and decodes the bytes (src/input.ci). A byte that finds its ring full is dropped and
 * counted. The rings are only touched with interrupts off (cint code) or inside the interrupt, so they need
 * no lock. */
#include "rt.h"

#define PS2_DATA 0x60u
#define PS2_STATUS 0x64u
#define PS2_CMD 0x64u
#define ST_OUT_FULL 1u
#define ST_IN_FULL 2u
#define ST_AUX 0x20u
#define CMD_READ_CB 0x20u
#define CMD_WRITE_CB 0x60u
#define CMD_AUX_ON 0xA8u
#define CMD_AUX_WRITE 0xD4u
#define CB_KBD_IRQ 1u
#define CB_AUX_IRQ 2u
#define CB_KBD_OFF 0x10u
#define CB_AUX_OFF 0x20u
#define CB_TRANSLATE 0x40u
#define MOUSE_DEFAULTS 0xF6u
#define MOUSE_STREAM 0xF4u
#define MOUSE_ACK 0xFAu
#define RING 256u
#define SPIN 100000u

static uint8_t rings[2][RING]; /* 0 the keyboard, 1 the auxiliary device */
static int64_t stamps[RING];   /* K-12: the keyboard bytes' interrupt times, rt_us_now */
static int64_t got_stamp;      /* K-12: the stamp of the keyboard byte rt_ps2_get gave last */
static unsigned heads[2], counts[2], dropped;

static void wait_input_empty(void)
{
    unsigned i;
    for (i = 0u; i < SPIN && (port_in8(PS2_STATUS) & ST_IN_FULL) != 0u; i++) {}
}

static int read_byte(uint8_t *st)
{
    unsigned i;
    for (i = 0u; i < SPIN; i++) {
        *st = port_in8(PS2_STATUS);
        if ((*st & ST_OUT_FULL) != 0u) return port_in8(PS2_DATA);
    }
    return -1;
}

/* A command to the mouse through the controller, answered by its acknowledgement byte: true on the ack. */
static bool mouse_command(uint8_t cmd)
{
    uint8_t st;
    int b;
    wait_input_empty();
    port_out8(PS2_CMD, CMD_AUX_WRITE);
    wait_input_empty();
    port_out8(PS2_DATA, cmd);
    b = read_byte(&st);
    return b == (int)MOUSE_ACK && (st & ST_AUX) != 0u;
}

/* Drains what the firmware left, turns the auxiliary device on, sets the command byte (both interrupts on,
 * both clocks on, translation to set 1 on: QEMU's firmware leaves the keyboard so; this makes it true on any
 * machine), then the mouse's defaults and streaming. Returns 1 when the mouse acknowledged both, else 0. */
/* HW-3: the FADT says the board has no 8042 (src/acpi.ci): nothing here touches ports 0x60 and 0x64 again. */
static bool absent;

void rt_ps2_absent(void) { absent = true; }

int64_t rt_ps2_init(void)
{
    unsigned i;
    uint8_t cb, st;
    int b;
    if (absent) return 0;
    for (i = 0u; i < 64u && (port_in8(PS2_STATUS) & ST_OUT_FULL) != 0u; i++) (void)port_in8(PS2_DATA);
    wait_input_empty();
    port_out8(PS2_CMD, CMD_AUX_ON);
    wait_input_empty();
    port_out8(PS2_CMD, CMD_READ_CB);
    b = read_byte(&st);
    cb = b < 0 ? 0u : (uint8_t)b;
    cb = (uint8_t)((cb | CB_KBD_IRQ | CB_AUX_IRQ | CB_TRANSLATE) & ~(CB_KBD_OFF | CB_AUX_OFF));
    wait_input_empty();
    port_out8(PS2_CMD, CMD_WRITE_CB);
    wait_input_empty();
    port_out8(PS2_DATA, cb);
    heads[0] = heads[1] = counts[0] = counts[1] = dropped = 0u;
    return mouse_command(MOUSE_DEFAULTS) && mouse_command(MOUSE_STREAM) ? 1 : 0;
}

void rt_ps2_irq(void)
{
    uint8_t st, b;
    if (absent) return;
    st = port_in8(PS2_STATUS);
    unsigned which;
    if ((st & ST_OUT_FULL) == 0u) return;
    b = port_in8(PS2_DATA);
    which = (st & ST_AUX) != 0u ? 1u : 0u;
    if (counts[which] == RING) {
        dropped++;
        return;
    }
    rings[which][(heads[which] + counts[which]) % RING] = b;
    if (which == 0u) stamps[(heads[0] + counts[0]) % RING] = rt_us_now();
    counts[which]++;
}

int64_t rt_ps2_get(int64_t which)
{
    uint8_t b;
    unsigned w = which == 1 ? 1u : 0u;
    if (counts[w] == 0u) return -1;
    b = rings[w][heads[w]];
    if (w == 0u) got_stamp = stamps[heads[0]];
    heads[w] = (heads[w] + 1u) % RING;
    counts[w]--;
    return b;
}

int64_t rt_ps2_stamp(void)
{
    return got_stamp;
}

int64_t rt_ps2_dropped(void)
{
    return dropped;
}
