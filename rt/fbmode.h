/* rt/fbmode.h: the screen sizes the Bochs display is programmed to (RES-1, which amends HX-0 A,
 * docs/specs/2026-11-05-h-hybrid.md section 4): W a multiple of 8 in [640, 5120], H in [480, 3840], and W x H at
 * most 3840 x 2160 pixels, so the window rt/fb.c maps for every mode (4 x 3840 x 2160 bytes, 31.64 MiB) is the one
 * it mapped before RES-1. 5120 x 1440 (ultrawide) and 2160 x 3840 (4K portrait) fit; 5120 x 2160 does not.
 * rt/fb.c checks both the boot line's daphnis.mode and a switch from Settings (rt_fb_mode) with it; the hosted test
 * tests/hosted/fbmode_test.c includes this header as it is. */
#ifndef DAPH_FBMODE_H
#define DAPH_FBMODE_H

#include <stdbool.h>
#include <stdint.h>

#define FB_W 640u                /* the size without daphnis.mode, and the least width */
#define FB_H 480u                /* the least height */
#define MODE_W_MAX 5120u
#define MODE_H_MAX 3840u
#define MODE_PX_MAX (3840u * 2160u) /* the pixel cap: what fb_mapped holds at 4 bytes a pixel */

/* true when w x h x 32 is a size the kernel programs; each side is range checked before the product */
static inline bool fb_mode_fits(uint64_t w, uint64_t h)
{
    if (w < FB_W || w > MODE_W_MAX || w % 8u != 0u || h < FB_H || h > MODE_H_MAX) return false;
    return w * h <= (uint64_t)MODE_PX_MAX;
}

#endif
