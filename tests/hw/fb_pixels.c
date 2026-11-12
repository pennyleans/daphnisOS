/* Native layout conversion is independent of PCI, mappings and the canonical digest. */
#include <assert.h>
#include <stdio.h>
#include "../../rt/rt.h"

int main(void)
{
    struct rt_fb_format formats[] = {
        {{16u, 8u, 0u}, {8u, 8u, 8u}},
        {{0u, 8u, 16u}, {8u, 8u, 8u}},
        {{11u, 5u, 0u}, {5u, 6u, 5u}},
        {{20u, 10u, 0u}, {10u, 10u, 10u}},
        {{19u, 10u, 1u}, {8u, 8u, 8u}}
    };
    for (unsigned i = 0u; i < sizeof formats / sizeof formats[0]; i++) {
        const struct rt_fb_format *f = &formats[i];
        assert(rt_fb_format_valid(f));
        assert(rt_fb_encode(f, 0u) == 0u);
        assert(rt_fb_encode(f, 0xFFFFFFFFu) == rt_fb_rgb_mask(f));
        for (unsigned channel = 0u; channel < 3u; channel++) {
            uint32_t old = 0u;
            uint32_t max = (uint32_t)(((uint64_t)1u << f->bits[channel]) - 1u);
            for (uint32_t v = 0u; v <= 255u; v++) {
                uint32_t in = v << (16u - 8u * channel);
                uint32_t out = rt_fb_encode(f, in);
                uint32_t field = out >> f->pos[channel];
                assert(field >= old && field <= max);
                assert(out == field << f->pos[channel]);
                if (v == 0u) assert(field == 0u);
                if (v == 255u) assert(field == max);
                if (f->bits[channel] == 8u) assert(field == v);
                old = field;
            }
        }
    }
    assert(rt_fb_format_xrgb(&formats[0]));
    assert(!rt_fb_format_xrgb(&formats[1]));
    assert(rt_fb_encode(&formats[1], 0x00123456u) == 0x00563412u);
    assert(rt_fb_encode(&formats[2], 0x00808080u) == 0x8410u);
    struct rt_fb_format bad = {{16u, 8u, 0u}, {8u, 8u, 8u}};
    bad.pos[0] = 8u; assert(!rt_fb_format_valid(&bad));
    bad = formats[0]; bad.bits[0] = 0u; assert(!rt_fb_format_valid(&bad));
    bad = formats[0]; bad.bits[0] = 33u; assert(!rt_fb_format_valid(&bad));
    bad = formats[0]; bad.pos[0] = 32u; assert(!rt_fb_format_valid(&bad));
    bad = formats[0]; bad.pos[0] = 31u; assert(!rt_fb_format_valid(&bad));
    puts("native pixels: PASS (XRGB/RGBX, RGB565, RGB10, unaligned fields, endpoints, monotonicity, refusals)");
    return 0;
}
