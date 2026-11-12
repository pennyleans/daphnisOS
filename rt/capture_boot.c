/* QEMU fixture provisioning. This is not a physical key-file loader. */
#include "rt.h"
#include "capture_sink.h"
#include "capture_replay.h"
#include "../vendor/monocypher/monocypher.h"

extern const cint_program cg_program;
static uint64_t kernel_root;
static int ready;
static uint8_t key_file[56] __attribute__((section(".high.data")));
static uint8_t replay_key[56] __attribute__((section(".high.data")));
struct capture_file { uint32_t size; uint16_t selector; uint64_t position; };
static struct capture_file replay_file __attribute__((section(".high.data")));
static int replay_present;

static void stop(void)
{
    /* No panic encoder or serial fallback is permitted on this path. */
    cpu_cli();
    if (ready && cr3_read() == kernel_root) {
        ready = 0;
        daph_capture_sink_abort();
        daph_capture_replay_close();
    }
    port_out8(0xF4u, RT_EXIT_PANIC);
    for (;;) cpu_halt();
}

static int emit(void *user, const uint8_t *bytes, size_t n)
{
    (void)user;
    for (size_t i = 0u; i < n; i++) {
        if ((port_in8(0x3FBu) & 0x80u) != 0u) return -1;
        unsigned spins = 0u;
        while ((port_in8(0x3FDu) & 0x20u) == 0u) {
            if (++spins == 100000u) return -1;
        }
        port_out8(0x3F8u, bytes[i]);
    }
    /* FIFO reset and runtime exit must not discard the header or final tag. */
    unsigned spins = 0u;
    while ((port_in8(0x3FDu) & 0x40u) == 0u) {
        if (++spins == 100000u) return -1;
    }
    return 0;
}

static void read_bytes(uint8_t *dst, size_t n)
{
    for (size_t i = 0u; i < n; i++) dst[i] = port_in8(0x511u);
}

static uint32_t be32(const uint8_t *p)
{
    return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) |
           ((uint32_t)p[2] << 8) | p[3];
}

static int find_file(const char *name, size_t name_size, struct capture_file *file)
{
    uint8_t entry[64];
    uint16_t selected = 0u;
    uint32_t size = 0u;
    if (name_size > 56u) return -1;
    port_out16(0x510u, 0u);
    read_bytes(entry, 4u);
    if (memcmp(entry, "QEMU", 4u) != 0) return -1;
    port_out16(0x510u, 0x19u);
    read_bytes(entry, 4u);
    uint32_t n = be32(entry);
    if (n > 256u) return -1;
    for (uint32_t i = 0u; i < n; i++) {
        read_bytes(entry, sizeof entry);
        if (memcmp(entry + 8u, name, name_size) != 0) continue;
        if (selected != 0u || entry[6] || entry[7]) return -1;
        selected = (uint16_t)(((uint16_t)entry[4] << 8) | entry[5]);
        if (selected < 0x20u || selected >= 0x4000u) return -1;
        size = be32(entry);
    }
    if (selected == 0u) return 0;
    file->selector = selected;
    file->size = size;
    file->position = UINT64_MAX;
    return 1;
}

static int read_file(void *user, uint64_t offset, uint8_t *dst, size_t n)
{
    struct capture_file *file = user;
    if (offset > file->size || n > file->size - offset) return -1;
    if (file->position == UINT64_MAX || offset < file->position) {
        port_out16(0x510u, file->selector);
        file->position = 0u;
    }
    while (file->position < offset) { (void)port_in8(0x511u); file->position++; }
    read_bytes(dst, n);
    file->position += n;
    return 0;
}

static int load_fixture(void)
{
    static const char name[] = "opt/dev.integerc/daphnis-capture";
    struct capture_file file;
    if (find_file(name, sizeof name, &file) != 1 || file.size != sizeof key_file) return -1;
    if (read_file(&file, 0u, key_file, sizeof key_file) != 0) return -1;
    return memcmp(key_file, "DAPHKEY1", 8u) == 0 ? 0 : -1;
}

static int load_replay(void)
{
    static const char archive_name[] = "opt/dev.integerc/daphnis-replay";
    static const char key_name[] = "opt/dev.integerc/daphnis-replay-key";
    struct capture_file file;
    int archive = find_file(archive_name, sizeof archive_name, &replay_file);
    int key = find_file(key_name, sizeof key_name, &file);
    if (archive == 0 && key == 0) return 0;
    if (archive != 1 || key != 1 || file.size != sizeof replay_key) return -1;
    if (read_file(&file, 0u, replay_key, sizeof replay_key) != 0) return -1;
    if (memcmp(replay_key, "DAPHKEY1", 8u) != 0) return -1;
    /* A replay output is a new recording, never another use of its input key. */
    if (crypto_verify32(replay_key + 8u, key_file + 8u) == 0) return -1;
    if (daph_capture_replay_open(replay_key + 8u, replay_key + 40u, cg_program.revision,
                                read_file, &replay_file, replay_file.size) != 0) return -1;
    replay_present = 1;
    return 0;
}

void rt_capture_boot(void)
{
    kernel_root = cr3_read();
    /* Initialize the UART before the authenticated header is emitted. */
    port_out8(0x3F9u, 0u);
    port_out8(0x3FBu, 0x80u);
    port_out8(0x3F8u, 1u);
    port_out8(0x3F9u, 0u);
    port_out8(0x3FBu, 3u);
    port_out8(0x3FAu, 0xC7u);
    port_out8(0x3FCu, 0x0Bu);
    if (load_fixture() != 0 || load_replay() != 0) {
        crypto_wipe(key_file, sizeof key_file);
        crypto_wipe(replay_key, sizeof replay_key);
        daph_capture_replay_close();
        stop();
    }
    crypto_wipe(replay_key, sizeof replay_key);
    int rc = daph_capture_sink_begin(key_file + 8u, key_file + 40u,
                                    cg_program.revision, emit, NULL);
    crypto_wipe(key_file, sizeof key_file);
    if (rc != 0) { daph_capture_replay_close(); stop(); }
    ready = 1;
}

void rt_capture_byte(uint8_t byte)
{
    if (!ready || cr3_read() != kernel_root) stop();
    if (daph_capture_sink_put(byte) != 0) stop();
}

void rt_capture_finish(void)
{
    if (!ready || cr3_read() != kernel_root) stop();
    if (daph_capture_sink_finish() != 0) stop();
    daph_capture_replay_close();
    replay_present = 0;
    ready = 0;
}

void rt_journal_record(int64_t kind, const uint8_t *bytes, size_t n)
{
    if (!ready || cr3_read() != kernel_root || (kind != 1 && kind != 2)) stop();
    if (daph_capture_sink_record((int)kind, bytes, n) != 0) stop();
}

int64_t rt_journal_size(int64_t kind)
{
    if (!ready || cr3_read() != kernel_root || (kind != 1 && kind != 2)) stop();
    if (!replay_present) return -1;
    return daph_capture_replay_size((int)kind);
}

int64_t rt_journal_read(int64_t kind, int64_t offset, uint8_t *bytes, size_t n)
{
    if (!ready || cr3_read() != kernel_root || !replay_present || offset < 0 || (kind != 1 && kind != 2)) stop();
    int64_t result = daph_capture_replay_read((int)kind, (uint64_t)offset, bytes, n);
    if (result < 0) stop();
    return result;
}
