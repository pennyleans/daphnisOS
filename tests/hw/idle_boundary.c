/* Compile this fixture without sanitizers and with function/data sections. Only
 * the actual wait host shim is retained by --gc-sections; unrelated host-table
 * bindings require the real machine. Framebuffer code remains ASan/UBSan tested. */
#include "../../rt/host.c"

cint_status test_idle_boundary(void)
{
    return hf_wait_irq(NULL, NULL);
}
