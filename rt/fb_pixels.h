/* Native direct-color encoding. Canonical application bytes remain XRGB8888. */
#ifndef DAPHNIS_FB_PIXELS_H
#define DAPHNIS_FB_PIXELS_H

struct rt_fb_format {
    uint8_t pos[3], bits[3]; /* red, green, blue */
};

static inline bool rt_fb_format_valid(const struct rt_fb_format *f)
{
    uint64_t used = 0u;
    for (unsigned i = 0; i < 3u; i++) {
        if (f->bits[i] == 0u || f->bits[i] > 32u || f->pos[i] >= 32u || f->bits[i] > 32u - f->pos[i]) return false;
        uint64_t mask = (((uint64_t)1u << f->bits[i]) - 1u) << f->pos[i];
        if ((mask & used) != 0u) return false;
        used |= mask;
    }
    return true;
}

static inline bool rt_fb_format_xrgb(const struct rt_fb_format *f)
{
    return f->pos[0] == 16u && f->pos[1] == 8u && f->pos[2] == 0u &&
           f->bits[0] == 8u && f->bits[1] == 8u && f->bits[2] == 8u;
}

static inline uint32_t rt_fb_rgb_mask(const struct rt_fb_format *f)
{
    uint64_t mask = 0u;
    for (unsigned i = 0; i < 3u; i++) mask |= (((uint64_t)1u << f->bits[i]) - 1u) << f->pos[i];
    return (uint32_t)mask;
}

/* Nearest native intensity, ties rounded upward. Wide intermediates avoid overflow even
 * for non-byte-aligned fields. The encoder zeroes unused bits; the XRGB copy fast path
 * may preserve the canonical X byte. Unused native bits are ignored on readback. */
static inline uint32_t rt_fb_encode(const struct rt_fb_format *f, uint32_t pixel)
{
    uint64_t out = 0u;
    for (unsigned i = 0; i < 3u; i++) {
        uint64_t v = (pixel >> (16u - 8u * i)) & 255u;
        uint64_t max = ((uint64_t)1u << f->bits[i]) - 1u;
        out |= ((v * max + 127u) / 255u) << f->pos[i];
    }
    return (uint32_t)out;
}
#endif
