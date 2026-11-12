/* rt/chan.c: channels between tasks (K4.5). A channel has one sender task and one receiver
 * task, fixed when it is opened, and holds up to CAP values in order. A send to a full channel
 * and a receive from an empty one block the task (it is not run again until the channel can
 * serve it), so a task's results do not depend on how turns interleave: this is a Kahn process
 * network. A task that touches a channel it is not the end of is refused, and the refusal is a
 * fault record like any other. recv_any is the one operation a network must not use: it takes
 * whichever of two channels has a value, which depends on the schedule. It is here so a test can
 * show that the checks catch a program that uses it. */
#include "rt.h"

#define CHANS 4u
#define CAP 2u
#define TASKS 3

static struct chan {
    bool open;
    int sender, receiver;
    int64_t buf[CAP];
    unsigned head, count;
} chans[CHANS];

int64_t rt_chan_open(int64_t id, int64_t sender, int64_t receiver)
{
    struct chan *c;
    if (id < 0 || id >= (int64_t)CHANS || sender < 0 || sender >= TASKS || receiver < 0 || receiver >= TASKS || sender == receiver)
        return -1;
    c = &chans[id];
    memset(c, 0, sizeof *c);
    c->open = true;
    c->sender = (int)sender;
    c->receiver = (int)receiver;
    return 0;
}

void rt_chan_close(int64_t id)
{
    if (id >= 0 && id < (int64_t)CHANS) memset(&chans[id], 0, sizeof chans[id]);
}

void rt_chan_status(uint32_t *full, uint32_t *nonempty)
{
    unsigned i;
    *full = 0u;
    *nonempty = 0u;
    for (i = 0u; i < CHANS; i++) {
        if (chans[i].count == CAP) *full |= 1u << i;
        if (chans[i].count > 0u) *nonempty |= 1u << i;
    }
}

static struct chan *end_of(int64_t id, bool sending)
{
    struct chan *c;
    int cur = rt_task_current();
    if (cur < 0 || id < 0 || id >= (int64_t)CHANS) return NULL;
    if (rt_task_preemptible()) rt_panic("channel operation in a preemptible task"); /* the rings are not tick safe */
    c = &chans[id];
    if (!c->open || (sending ? c->sender : c->receiver) != cur) return NULL;
    return c;
}

cint_status rt_chan_send(int64_t id, int64_t value)
{
    struct chan *c = end_of(id, true);
    if (c == NULL) return CINT_REFUSED;
    while (c->count == CAP) rt_task_block(1u << id, 0u);
    c->buf[(c->head + c->count) % CAP] = value;
    c->count++;
    return CINT_OK;
}

static int64_t take(struct chan *c)
{
    int64_t v = c->buf[c->head];
    c->head = (c->head + 1u) % CAP;
    c->count--;
    return v;
}

cint_status rt_chan_recv(int64_t id, int64_t *value)
{
    struct chan *c = end_of(id, false);
    if (c == NULL) return CINT_REFUSED;
    while (c->count == 0u) rt_task_block(0u, 1u << id);
    *value = take(c);
    return CINT_OK;
}

cint_status rt_chan_recv_any(int64_t a, int64_t b, int64_t *value)
{
    struct chan *ca = end_of(a, false), *cb = end_of(b, false);
    if (ca == NULL || cb == NULL || a == b) return CINT_REFUSED;
    while (ca->count == 0u && cb->count == 0u) rt_task_block(0u, (1u << a) | (1u << b));
    *value = take(ca->count > 0u ? ca : cb);
    return CINT_OK;
}
