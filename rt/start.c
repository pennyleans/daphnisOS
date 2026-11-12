/* rt/start.c: from the boot stub to the emitted main, and out to QEMU. */
#include "rt.h"

int main(int argc, char **argv);

/* HW-2: the S5 values src/acpi.ci found (PM1a and PM1b control ports, SLP_TYPa and SLP_TYPb); none until it ran. With
 * them, the FADT's SMI_CMD port and ACPI_ENABLE value (0 for none): the handshake to ACPI mode. */
static uint16_t s5_pm1a, s5_pm1b, s5_typa, s5_typb, s5_smi;
static uint8_t s5_enable;
static bool s5_set;
/* And the FADT's PM1 event blocks and GPE blocks (0 for none): what rt_exit quiets before S5. */
static uint16_t s5_evta, s5_evtb, s5_gpe[2];
static uint8_t s5_gpe_len[2];

void rt_poweroff_set(uint64_t pm1a, uint64_t pm1b, uint64_t typa, uint64_t typb)
{
    if (pm1a == 0u || pm1a > 0xFFFFu || pm1b > 0xFFFFu || typa > 7u || typb > 7u) return;
    s5_pm1a = (uint16_t)pm1a;
    s5_pm1b = (uint16_t)pm1b;
    s5_typa = (uint16_t)typa;
    s5_typb = (uint16_t)typb;
    s5_set = true;
}

void rt_poweroff_acpi(uint64_t smi_cmd, uint64_t enable)
{
    if (smi_cmd == 0u || smi_cmd > 0xFFFFu || enable == 0u || enable > 0xFFu) return;
    s5_smi = (uint16_t)smi_cmd;
    s5_enable = (uint8_t)enable;
}

/* PM1 event blocks of 4 bytes or more, an even length (PM1_STS then PM1_EN, ACPI 6.5 section 4.8.3.1). */
void rt_poweroff_events(uint64_t pm1a_evt, uint64_t pm1b_evt, uint64_t len)
{
    if (pm1a_evt > 0xFFFFu || pm1b_evt > 0xFFFFu || len < 4u || len > 0xFFu || len % 2u != 0u) return;
    s5_evta = (uint16_t)pm1a_evt;
    s5_evtb = (uint16_t)pm1b_evt;
}

/* GPE blocks of an even length below the end of I/O space (status bytes then enable bytes, section 4.8.4.1); a block
 * that is not is left alone. */
void rt_poweroff_gpe(uint64_t gpe0, uint64_t gpe0_len, uint64_t gpe1, uint64_t gpe1_len)
{
    uint64_t port[2] = {gpe0, gpe1}, len[2] = {gpe0_len, gpe1_len};
    for (unsigned k = 0u; k < 2u; k++) {
        s5_gpe[k] = 0u;
        s5_gpe_len[k] = 0u;
        if (port[k] == 0u || len[k] == 0u || len[k] > 0xFFu || len[k] % 2u != 0u || port[k] + len[k] > 0x10000u)
            continue;
        s5_gpe[k] = (uint16_t)port[k];
        s5_gpe_len[k] = (uint8_t)len[k];
    }
}

/* As ACPICA's legacy sleep before SLP_TYP: every fixed status bit of PM1_STS written 1 to clear it, in PM1a and PM1b
 * (ACPICA's ACPI_BITMASK_ALL_FIXED_STATUS, 0x8731: WAK_STS, RTC_STS, SLPBTN_STS, PWRBTN_STS, GBL_STS, BM_STS and
 * TMR_STS; section 4.8.3.1.1), every GPE enable byte written 0, then every GPE status byte written 1s, so no wake
 * event is pending or armed when SLP_EN goes in. PM1_EN is left as it is: the power button still wakes the machine
 * from S5. */
#define RT_PM1_FIXED_STATUS 0x8731u
static void rt_acpi_quiet(void)
{
    if (s5_evta != 0u) port_out16(s5_evta, RT_PM1_FIXED_STATUS);
    if (s5_evtb != 0u) port_out16(s5_evtb, RT_PM1_FIXED_STATUS);
    for (unsigned k = 0u; k < 2u; k++) {
        unsigned half = s5_gpe_len[k] / 2u;
        for (unsigned i = 0u; i < half; i++) port_out8((uint16_t)(s5_gpe[k] + half + i), 0u);
    }
    for (unsigned k = 0u; k < 2u; k++) {
        unsigned half = s5_gpe_len[k] / 2u;
        for (unsigned i = 0u; i < half; i++) port_out8((uint16_t)(s5_gpe[k] + i), 0xFFu);
    }
}

/* ACPI 6.5 section 4.8.3.2.1: firmware may hand the machine over in legacy mode, SCI_EN (bit 0 of PM1_CNT) clear, where
 * a chipset may take SLP_EN to its SMI handler and not to the sleep logic. As ACPICA's acpi_enable: with SCI_EN clear
 * and the FADT giving SMI_CMD, ACPI_ENABLE is written there and SCI_EN polled for up to 3 s (each poll an I/O write
 * to port 0x80, about 1 us). True when SCI_EN is set. */
#define RT_ACPI_ENABLE_POLLS 3000000u
static bool rt_acpi_mode(void)
{
    if ((port_in16(s5_pm1a) & 1u) != 0u) return true;
    if (s5_smi == 0u) return false;
    port_out8(s5_smi, s5_enable);
    for (uint32_t i = 0u; i < RT_ACPI_ENABLE_POLLS; i++) {
        if ((port_in16(s5_pm1a) & 1u) != 0u) return true;
        port_out8(0x80u, 0u);
    }
    return false;
}

/* A PM1 control register's value for S5: what it reads, SLP_TYP (bits 10 to 12) set to typ and SLP_EN (bit 13) and
 * GBL_RLS (bit 2, write-only: a 1 raises an SMI) clear, so SCI_EN and the other bits keep their state. */
static uint16_t rt_pm1_s5(uint16_t port, uint16_t typ)
{
    return (uint16_t)((port_in16(port) & ~0x3C04u) | (uint16_t)(typ << 10));
}

static void rt_put_exit(unsigned value)
{
    char d[12];
    int k = 0;
    rt_puts("daphnis: exit ");
    do { d[k++] = (char)('0' + value % 10u); value /= 10u; } while (value != 0u && k < 11);
    while (k > 0) { char c[2] = {d[--k], '\0'}; rt_puts(c); }
    rt_puts("\n");
}

void rt_exit(unsigned value)
{
#ifdef RT_CAPTURE
    rt_capture_finish();
#endif
#ifdef RT_USER
    static bool exiting;
    if (!exiting) {
        exiting = true;
        if (!rt_fb_verify()) {
            rt_puts("daphnis: framebuffer readback mismatch\n");
            value = RT_EXIT_PANIC;
        }
    }
#endif
    port_out8(0xF4u, (uint8_t)value);
    /* HW-2: a board has no exit port; with daphnis.poweroff=1 the machine ends through ACPI S5 (SLP_TYP, SLP_EN). Only
     * an end the system asked for (RT_EXIT_OK: the desk's Shut Down, a main that returned): a fault or a panic halts
     * with its lines on the screen, so a person sees it (the read of PR 489). */
    if (s5_set && rt_boot_poweroff() && value == RT_EXIT_OK) {
        if (!rt_acpi_mode()) rt_puts("daphnis: acpi: SCI_EN is clear, S5 is written in legacy mode\n");
        rt_put_exit(value);    /* the last line when S5 does not take: on a board, how a failed power-off shows */
        rt_acpi_quiet();
        /* As ACPICA's legacy sleep: SLP_TYP into PM1a and PM1b, then SLP_TYP and SLP_EN, each read, changed, written */
        uint16_t a = rt_pm1_s5(s5_pm1a, s5_typa), b = 0u;
        if (s5_pm1b != 0u) b = rt_pm1_s5(s5_pm1b, s5_typb);
        port_out16(s5_pm1a, a);
        if (s5_pm1b != 0u) port_out16(s5_pm1b, b);
        port_out16(s5_pm1a, (uint16_t)(a | 0x2000u));
        if (s5_pm1b != 0u) port_out16(s5_pm1b, (uint16_t)(b | 0x2000u));
    }
    for (;;) cpu_halt();
}

void rt_panic(const char *why)
{
    rt_puts("daphnis: panic: ");
    rt_puts(why);
    rt_puts("\n");
    rt_exit(RT_EXIT_PANIC);
}

/* Called by arch/x86_64/boot.S in 64-bit mode on a 16-byte aligned stack, bss cleared. */
void rt_start(void)
{
#ifdef RT_CAPTURE
    rt_capture_boot();
#endif
    rt_boot_init();
    if (rt_boot_fitted() != 0u) {   /* RG-1: a block past the copy, fitted (rt/boot.c mb2_fit), or not */
        rt_puts("daphnis: loader block ");
        rt_put_dec(rt_boot_fitted());
        rt_puts(" bytes, over the copy's 65536, fitted\n");
    }
    if (rt_boot_status() == -3) rt_panic("loader block: the tags the kernel reads do not fit its copy");
    rt_wx_init();
    int rc = main(0, NULL);
    rt_exit(rc == 0 ? RT_EXIT_OK : rc == 1 ? RT_EXIT_FAULT : RT_EXIT_PANIC);
}
