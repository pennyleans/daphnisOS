/* user/c/mrng.c: A-3's draw (docs/specs/2026-11-06-a-agent.md section 5). One getrandom of 64 bytes, printed in
 * hex, then the CLOCK_REALTIME seconds; with no source, the error. Its own static musl binary (user/c/build.sh,
 * ruling DU-2 A), committed as user/bin/mrng and pinned in tests/expected/agent.sha256, so musltest's bytes and
 * the user flavor's goldens stay. Exit status 0 when 64 bytes came. */
#define _GNU_SOURCE
#include <errno.h>
#include <stdio.h>
#include <sys/syscall.h>
#include <time.h>
#include <unistd.h>

int main(void)
{
    unsigned char b[64];
    struct timespec ts;
    long n = syscall(SYS_getrandom, b, sizeof b, 0);
    if (n < 0) {
        printf("mrng: getrandom -%d\n", errno);
    } else {
        printf("mrng: getrandom %ld ", n);
        for (long i = 0; i < n; i++) printf("%02x", b[i]);
        printf("\n");
    }
    if (clock_gettime(CLOCK_REALTIME, &ts) == 0) printf("mrng: realtime %lld\n", (long long)ts.tv_sec);
    return n == (long)sizeof b ? 0 : 1;
}
