/* HW-2 and the reads of PR 489 and PR 493: rt_exit ends the machine through ACPI S5 only for RT_EXIT_OK; a fault or a
 * panic writes the exit port and halts, so its lines stay on the screen. Before S5: with SCI_EN clear and the FADT's
 * SMI_CMD, ACPI_ENABLE is written there and SCI_EN polled for, bounded; then SLP_TYP and SLP_TYP | SLP_EN into PM1a
 * and PM1b, each the register's own bits kept; before them the fixed status cleared, the GPEs disabled and their status
 * cleared. rt/start.c with the ports, the console and the halt stubbed: the halt
 * jumps back here. */
#include <assert.h>
#include <setjmp.h>
#include <stdio.h>
#include <string.h>
#include "../../rt/start.c"

#define PM1A 0x604u
#define PM1B 0x804u
#define SMI 0xB2u
#define EVTA 0x600u
#define EVTB 0x800u
#define GPE0 0x620u
#define GPE1 0x640u

static jmp_buf halted;
static bool poweroff_word;
static unsigned exit_port, exit_lines, legacy_lines, smi_writes, polls, delays;
static uint16_t pm1a, pm1b;             /* the PM1 control registers as read */
static long sci_after;                  /* SCI_EN sets this many reads after ACPI_ENABLE; -1 never */
static uint16_t writes[8];              /* PM1 writes in order: port's bit 15 set for PM1b */
static unsigned nwrites;
static uint32_t out[64];                /* every write but the delays, in order: port << 16 | value, bit 31 for 16 bits */
static unsigned nout;

static void logw(uint16_t port, uint16_t value, bool wide)
{
    if (nout < 64u) out[nout++] = (wide ? 0x80000000u : 0u) | (uint32_t)port << 16 | value;
}

void port_out8(uint16_t port, uint8_t value)
{
    if (port == 0xF4u) exit_port = value;
    if (port == SMI) { assert(value == 0xA0u); smi_writes++; }
    if (port == 0x80u) delays++;
    else logw(port, value, false);
}

uint16_t port_in16(uint16_t port)
{
    if (port == PM1A) {
        polls++;
        if (smi_writes > 0u && sci_after >= 0 && (long)polls > sci_after) pm1a |= 1u;
        return pm1a;
    }
    if (port == PM1B) return pm1b;
    return 0xFFFFu;
}

void port_out16(uint16_t port, uint16_t value)
{
    logw(port, value, true);
    if ((port == PM1A || port == PM1B) && nwrites < 8u)
        writes[nwrites++] = (uint16_t)(value | (port == PM1B ? 0x8000u : 0u));
}

void rt_puts(const char *s)
{
    if (strcmp(s, "daphnis: exit ") == 0) exit_lines++;
    if (strstr(s, "SCI_EN is clear") != NULL) legacy_lines++;
}

bool rt_boot_poweroff(void) { return poweroff_word; }
void rt_boot_init(void) {}
uint32_t rt_boot_fitted(void) { return 0u; }      /* rt_start's (PR 495, PR 498), not reached here */
int64_t rt_boot_status(void) { return 2; }
void rt_put_dec(uint64_t v) { (void)v; }
void rt_wx_init(void) {}
void cpu_halt(void) { longjmp(halted, 1); }

/* rt_exit(value) on a machine whose FADT gave S5 (or not) and SMI_CMD (or not), with the boot word (or not), PM1a and
 * PM1b reading a and b: the PM1 writes it made. */
static unsigned end(unsigned value, bool word, bool s5, bool smi, uint16_t a, uint16_t b, long after)
{
    s5_set = false; s5_smi = 0u; s5_enable = 0u; s5_evta = s5_evtb = 0u;
    rt_poweroff_gpe(0u, 0u, 0u, 0u);
    if (s5) rt_poweroff_set(PM1A, PM1B, 5u, 7u);
    if (smi) rt_poweroff_acpi(SMI, 0xA0u);
    poweroff_word = word;
    pm1a = a; pm1b = b; sci_after = after;
    exit_port = exit_lines = legacy_lines = smi_writes = polls = delays = nwrites = nout = 0u;
    memset(writes, 0, sizeof writes);
    if (setjmp(halted) == 0) rt_exit(value);
    assert(exit_port == (value & 0xFFu));       /* QEMU's exit port, whatever the end */
    return nwrites;
}

int main(int argc, char **argv)
{
    (void)argc; (void)argv;
    /* ACPI mode already (SCI_EN set): no SMI; SLP_TYP then SLP_TYP | SLP_EN, PM1a then PM1b, SCI_EN and bit 1 kept,
     * the old SLP_TYP bits (0x1C00) and GBL_RLS (bit 2) cleared */
    assert(end(RT_EXIT_OK, true, true, true, 0x1C07u, 0x0001u, 0) == 4u && smi_writes == 0u && exit_lines == 1u);
    assert(writes[0] == ((5u << 10) | 0x0003u) && writes[1] == (0x8000u | (7u << 10) | 0x0001u));
    assert(writes[2] == ((5u << 10) | 0x2003u) && writes[3] == (0x8000u | (7u << 10) | 0x2001u));
    assert(legacy_lines == 0u);
    /* legacy mode (SCI_EN clear): ACPI_ENABLE to SMI_CMD, SCI_EN polled until it sets, then S5 with SCI_EN kept */
    assert(end(RT_EXIT_OK, true, true, true, 0x0000u, 0x0000u, 40) == 4u && smi_writes == 1u && legacy_lines == 0u);
    assert(delays >= 39u && delays < 100u && (writes[2] & 0x2001u) == 0x2001u);
    /* SCI_EN never sets: the poll is bounded (3 s of port 0x80 writes), one line says so, S5 is written anyway, and
     * "daphnis: exit 16" stays the last line, as a board that does not power off shows it */
    assert(end(RT_EXIT_OK, true, true, true, 0x0000u, 0x0000u, -1) == 4u && smi_writes == 1u && legacy_lines == 1u);
    assert(delays == RT_ACPI_ENABLE_POLLS && exit_lines == 1u);
    /* legacy mode and no SMI_CMD in the FADT: nothing to ask; the line, then S5 */
    assert(end(RT_EXIT_OK, true, true, false, 0x0000u, 0x0000u, 0) == 4u && smi_writes == 0u && legacy_lines == 1u);
    /* no PM1b: PM1a alone, twice */
    s5_set = false;
    assert(end(RT_EXIT_OK, true, false, false, 0x0001u, 0u, 0) == 0u);
    rt_poweroff_set(PM1A, 0u, 5u, 0u);
    poweroff_word = true; pm1a = 0x0001u; nwrites = 0u; smi_writes = 0u;
    if (setjmp(halted) == 0) rt_exit(RT_EXIT_OK);
    assert(nwrites == 2u && writes[0] == ((5u << 10) | 1u) && writes[1] == ((5u << 10) | 0x2001u));
    /* before SLP_TYP, as ACPICA: every fixed status bit (0x8731, WAK_STS and PWRBTN_STS among them) written to
     * PM1a_STS and PM1b_STS, every GPE enable byte (a block's
     * second half) 0, then every GPE status byte (its first half) 1s; GPE0 of 8 bytes, GPE1 of 4 */
    s5_set = false;
    rt_poweroff_set(PM1A, PM1B, 5u, 7u);
    rt_poweroff_events(EVTA, EVTB, 4u);
    rt_poweroff_gpe(GPE0, 8u, GPE1, 4u);
    poweroff_word = true; pm1a = 0x0001u; pm1b = 0x0001u; nwrites = nout = 0u; smi_writes = exit_lines = 0u;
    if (setjmp(halted) == 0) rt_exit(RT_EXIT_OK);
    {
        static const uint32_t want[] = {
            0xF4u << 16 | RT_EXIT_OK,                                      /* QEMU's exit port */
            0x80000000u | EVTA << 16 | 0x8731u, 0x80000000u | EVTB << 16 | 0x8731u,
            (GPE0 + 4u) << 16, (GPE0 + 5u) << 16, (GPE0 + 6u) << 16, (GPE0 + 7u) << 16,
            (GPE1 + 2u) << 16, (GPE1 + 3u) << 16,
            GPE0 << 16 | 0xFFu, (GPE0 + 1u) << 16 | 0xFFu, (GPE0 + 2u) << 16 | 0xFFu, (GPE0 + 3u) << 16 | 0xFFu,
            GPE1 << 16 | 0xFFu, (GPE1 + 1u) << 16 | 0xFFu,
            0x80000000u | PM1A << 16 | (5u << 10) | 1u, 0x80000000u | PM1B << 16 | (7u << 10) | 1u,
            0x80000000u | PM1A << 16 | (5u << 10) | 0x2001u, 0x80000000u | PM1B << 16 | (7u << 10) | 0x2001u,
        };
        assert(nout == sizeof want / sizeof want[0] && exit_lines == 1u);
        for (unsigned k = 0u; k < nout; k++) assert(out[k] == want[k]);
    }
    /* blocks the FADT gives wrong are left alone: a PM1 event block under 4 bytes, an odd GPE length, a GPE block past
     * the end of I/O space; GPE1 alone */
    rt_poweroff_events(EVTA, EVTB, 2u);
    assert(s5_evta == EVTA);                      /* the good values stay */
    s5_evta = s5_evtb = 0u;
    rt_poweroff_events(EVTA, EVTB, 2u);
    rt_poweroff_gpe(GPE0, 7u, 0xFFFEu, 4u);
    assert(s5_evta == 0u && s5_gpe_len[0] == 0u && s5_gpe_len[1] == 0u);
    rt_poweroff_gpe(0u, 0u, GPE1, 2u);
    nout = 0u;
    if (setjmp(halted) == 0) rt_exit(RT_EXIT_OK);
    assert(nout == 7u && out[1] == (GPE1 + 1u) << 16 && out[2] == (GPE1 << 16 | 0xFFu));
    /* the read of PR 489: S5 for RT_EXIT_OK only */
    rt_poweroff_events(EVTA, EVTB, 4u);
    rt_poweroff_gpe(GPE0, 8u, GPE1, 4u);
    s5_set = true;
    poweroff_word = true; nout = 0u;
    if (setjmp(halted) == 0) rt_exit(RT_EXIT_FAULT);
    assert(nout == 1u);                           /* the exit port alone: no clear for a fault */
    assert(end(RT_EXIT_FAULT, true, true, true, 0x0001u, 0u, 0) == 0u && exit_lines == 0u && polls == 0u);
    assert(end(RT_EXIT_PANIC, true, true, true, 0x0001u, 0u, 0) == 0u && exit_lines == 0u && smi_writes == 0u);
    assert(end(0x12u, true, true, true, 0x0001u, 0u, 0) == 0u);
    assert(end(RT_EXIT_OK, false, true, true, 0x0000u, 0u, 0) == 0u && smi_writes == 0u);   /* no daphnis.poweroff=1 */
    assert(end(RT_EXIT_OK, true, false, true, 0x0000u, 0u, 0) == 0u && smi_writes == 0u);   /* no S5 from the firmware */
    puts("exit s5: PASS (S5 for RT_EXIT_OK only; ACPI mode first, bounded; the fixed status and the GPEs cleared; "
         "SLP_TYP then SLP_EN on PM1a and PM1b, their bits kept)");
    return 0;
}
/* SPDX-License-Identifier: Apache-2.0 */
