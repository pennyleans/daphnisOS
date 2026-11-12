/* tests/hosted/fbmode_test.c: RES-1 (amends HX-0 A, docs/specs/2026-11-05-h-hybrid.md section 4), hosted. The
 * screen sizes rt/fb.c programs, through rt/fbmode.h as the kernel includes it: every size of the Settings list is
 * taken, 1366 x 768 (W not a multiple of 8) and 5120 x 2160 (past the pixel cap) are refused, and so is each side
 * past its range. Run by check.sh with gcc and with clang:
 *   cc -std=c11 -Irt tests/hosted/fbmode_test.c -o fbmode_test && ./fbmode_test
 * One line for each case that fails, then "fbmode: N checks, F failed"; exit status 1 if any failed. */
#include <stdio.h>

#include "fbmode.h"

static unsigned checks, failed;

static void expect(uint64_t w, uint64_t h, bool want)
{
    checks++;
    if (fb_mode_fits(w, h) != want) {
        failed++;
        printf("FAIL %llux%llu: %s\n", (unsigned long long)w, (unsigned long long)h, want ? "refused" : "taken");
    }
}

int main(void)
{
    /* RES-1's list: landscape, ultrawide, portrait, legacy */
    static const uint64_t list[][2] = {
        {1280, 720}, {1360, 768}, {1600, 900}, {1920, 1080}, {1920, 1200}, {2560, 1440}, {2560, 1600}, {3840, 2160},
        {2560, 1080}, {3440, 1440}, {3840, 1600}, {5120, 1440},
        {720, 1280}, {1080, 1920}, {1200, 1920}, {1440, 2560}, {1600, 2560}, {2160, 3840},
        {1024, 768}, {800, 600}, {640, 480},
    };
    size_t k;
    for (k = 0; k < sizeof list / sizeof list[0]; k++) expect(list[k][0], list[k][1], true);

    expect(5120, 1440, true);   /* ultrawide at the widest */
    expect(2160, 3840, true);   /* 4K portrait at the tallest, exactly the pixel cap */
    expect(5120, 1620, true);   /* exactly the pixel cap at the widest */
    expect(5120, 1624, false);  /* one row of 8 past it */
    expect(1366, 768, false);   /* W not a multiple of 8 */
    expect(5120, 2160, false);  /* past the pixel cap */
    expect(3840, 2168, false);  /* 4K one row of 8 past the cap */
    expect(5128, 1440, false);  /* past the widest */
    expect(2160, 3848, false);  /* past the tallest */
    expect(632, 480, false);    /* below the narrowest */
    expect(640, 479, false);    /* below the shortest */
    expect(0, 0, false);
    expect(UINT64_MAX & ~(uint64_t)7, 480, false); /* range checked before the product */
    expect(640, UINT64_MAX, false);

    /* the pixel cap is the map rt/fb.c makes at boot: 4 x 3840 x 2160 bytes, 31.64 MiB, as before RES-1 */
    checks++;
    if (4u * (uint64_t)MODE_PX_MAX != 33177600u) {
        failed++;
        printf("FAIL the pixel cap is %llu bytes\n", (unsigned long long)(4u * (uint64_t)MODE_PX_MAX));
    }

    printf("fbmode: %u checks, %u failed\n", checks, failed);
    return failed == 0u ? 0 : 1;
}
