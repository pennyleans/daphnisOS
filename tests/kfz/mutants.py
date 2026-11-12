#!/usr/bin/env python3
# tests/kfz/mutants.py: whether the kfz tests have teeth. Each mutant breaks one check of an entry in a copy of the
# hosted root (tests/kfz/hostroot.py), never in src/; a test of the suite must then fail. One line a mutant: CAUGHT
# (a test failed), MISSED (none did) or BROKEN (the mutant did not build, which proves nothing). Exit status 1 unless
# every mutant is caught. Not part of the gate: about a minute a mutant.
#   python3 tests/kfz/mutants.py OUT [--jobs N] [--only TEXT]   (OUT must not exist; cint as for tests/kfz/run.sh;
#   --only runs the mutants whose name holds TEXT)
import concurrent.futures
import os
import pathlib
import shutil
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent

# (name, file in the root, text, its replacement): each text occurs once. A file of rt/ is a mutant of this tree's
# copy, run by tests/kfz/console.sh.
MUTANTS = [
    ('image: a name past 64 bytes stops the scan, unsaid', 'src/fs.ci',
     '        } else if (trailer(at, ns)) {', '        } else if (ns > 64 || trailer(at, ns)) {'),
    ('image: a name of exactly 4096 bytes refused', 'src/fs.ci', '            if (ns > PATH_BYTES) {',
     '            if (ns >= PATH_BYTES) {'),
    ('image: any ten-byte name that starts with T ends the scan', 'src/fs.ci',
     '    return bytes_equal(t, "TRAILER!!!");', '    return t[0] == 84;'),
    ('image: a refused member is not named', 'src/fs.ci',
     '    refused += 1;\n    if (why == WHY_HEADER) {', '    refused += 1;\n    if (why > 0) {\n        return;\n    }\n    if (why == WHY_HEADER) {'),
    ('image: a refused member does not fail the boot', 'src/fs.ci',
     '    if (past > 0 || refused > 0) {', '    if (past > 0) {'),
    ('image: the scan stops at a refused member', 'src/fs.ci',
     '            if (why != 0) {\n                refuse(at, ns, why);',
     '            if (why != 0) {\n                refuse(at, ns, why);\n                more = false;'),
    ('image: a member under no directory left out unsaid', 'src/fs.ci',
     '            if (why != 0) {\n                refuse(at, ns, why);\n            } else if',
     '            if (why == WHY_NODIR) {\n                past += 0;\n            } else if (why != 0) {\n                refuse(at, ns, why);\n            } else if'),
    ('image: a last part of 256 taken', 'src/fs.ci',
     '                    } else if (cl > NAME_MAX) {', '                    } else if (cl > NAME_MAX + 1) {'),
    ('image: a part of 256 before the last taken as a directory', 'src/fs.ci',
     '                } else if (j > NAME_MAX) {\n                    why = WHY_PART;',
     '                } else if (j > NAME_MAX + 1) {\n                    why = WHY_PART;'),
    ('image: an empty part skipped', 'src/fs.ci',
     '                } else if (j < 1) {\n                    why = WHY_EMPTY;', '                } else if (j < 1) {\n                    s0 += 1;'),
    ('image: a header that does not read ends the scan unsaid', 'src/fs.ci',
     '            refuse(at, 0, WHY_HEADER);\n            more = false;', '            more = false;'),
    ('revoke: any caller', 'src/proc.ci',
     'I64 sys_revoke(I64 pid, I64 vp, U64 word) {\n    if (pid != tile.tiler_pid() || fs.uid_of(pid) != 0) {',
     'I64 sys_revoke(I64 pid, I64 vp, U64 word) {\n    if (false) {'),
    ('revoke: ring 0 revocable', 'src/proc.ci',
     '    if (!grants.revocable(word)) {', '    if (!grants.revocable(word & 7)) {'),
    ('login: after execve', 'src/proc.ci',
     'parent[pid] != d || exec_at[pid] != exec_at[d] ||', 'parent[pid] != d ||'),
    ('home: any caller', 'src/proc.ci',
     'I64 sys_home(I64 pid, U64 path, I64 uid, I64 gid) {\n    if (pid != tile.tiler_pid() || fs.uid_of(pid) != 0) {',
     'I64 sys_home(I64 pid, U64 path, I64 uid, I64 gid) {\n    if (false) {'),
    ('facts: kind 2 shows every process', 'src/proc.ci',
     'facts.sees(fs.uid_of(pid), kern, facts.is_parent(pid), fs.uid_of(s))', 'true'),
    ('facts: writes n bytes, not the share', 'src/proc.ci',
     '    I64 k = facts.share(full, n);', '    I64 k = full;'),
    ('sysinfo: into read-only memory', 'src/proc.ci',
     '    return uvm.poke(pid, va, b, 8 * n, true);', '    return uvm.poke(pid, va, b, 8 * n, false);'),
    ('statfs: into read-only memory', 'src/fs.ci',
     'uvm.poke(pid, buf, b, statfs.BYTES, true)', 'uvm.poke(pid, buf, b, statfs.BYTES, false)'),
    ('prctl: a 16-byte name', 'src/proc.ci',
     '    while (k < m && k < 15 && name[k] != 0) {', '    while (k < m && k < 16 && name[k] != 0) {'),
    ('O_NOFOLLOW: a link opens', 'src/fs.ci',
     '        if (link) {\n            return 0 - ELOOP;\n        }',
     '        if (false) {\n            return 0 - ELOOP;\n        }'),
    ('rename: no sticky rule', 'src/fs.ci',
     '    return (dm & 512) == 0 || owns(pid, du) || owns(pid, ou);', '    return true;'),
    ('tile KERN: any caller', 'src/proc.ci',
     'I64 sys_tile_kern(I64 pid, U64 arg) {\n    if (pid != tile.tiler_pid()) {',
     'I64 sys_tile_kern(I64 pid, U64 arg) {\n    if (false) {'),
    ('tile FOCUS: a 4-byte read', 'src/proc.ci',
     '    U8[8] b;\n    if (arg >= uvm.USER_HI || uvm.peek(pid, arg, b, 8) != 8) {\n        return 0 - EFAULT;\n    }\n'
     '    I64 kind = (b[0] as I64)',
     '    U8[8] b;\n    if (arg >= uvm.USER_HI || uvm.peek(pid, arg, b, 8) < 4) {\n        return 0 - EFAULT;\n    }\n'
     '    I64 kind = (b[0] as I64)'),
    # M-2: a promise backed inside a call (tests/kfz/k8_promise.ci, and every test in the promised mode)
    ('uvm: a backed promise counted and taken again', 'src/uvm.ci',
     'U64 frame = take_frame(pid, f);',
     'U64 frame = take_frame(pid, -1);'),
    ("uvm: the kernel's touch backs nothing", 'src/uvm.ci',
     'if (back(pid, va & 0xFFFFFFFFFFFFF000) < 0) {',
     'if (true) {'),
    ('frames: a backed promise left in the hold', 'src/frames.ci',
     '    free_frames -= 1;\n    held -= 1;',
     '    free_frames -= 1;'),
    # G2: bytes no one wrote (tests/kfz/k6_unwritten.ci, and kz_call's POISON check on every call)
    ('uvm: a frame taken without zeroing', 'src/uvm.ci',
     '    for k in 0..8 {\n        phys.phys_write64(pa + (512 * k) as U64, z);\n    }\n    return pa;',
     '    return pa;'),
    ('fs: a file page taken without zeroing', 'src/fs.ci', 'I64 nd = zeroed();', 'I64 nd = frames.alloc(1);'),
    ('fs: a cut page keeps its tail', 'src/fs.ci',
     '    if (sz % PAGE != 0) {\n        I64 p = page_of(f, sz / PAGE, false);',
     '    if (false) {\n        I64 p = page_of(f, sz / PAGE, false);'),
    ('pipe: a read past the bytes written', 'src/fs.ci',
     '    I64 want = pcount[p];\n    if (n < want as U64) {', '    I64 want = PIPE_BYTES;\n    if (n < want as U64) {'),
    # G5: rt/fb.c's rows refusing (tests/kfz/k4_tile.ci's tile mode and fb_init)
    ('fb: a refused hand-over keeps the frames', 'src/user.ci', '        _ = frames.release(first, pages);\n', ''),
    ("fb: the display's frames not counted", 'src/user.ci', '    fb_pool_frames += pages;\n', ''),
    ('fb: a mode committed after its pages were refused', 'src/user.ci',
     '    I64 ready = fb_back(fb_mode_need(w, h));\n    if (ready < 0) {\n        return ready;\n    }',
     '    I64 ready = fb_back(fb_mode_need(w, h));\n    _ = ready;'),
    # G4: a slot taken again (tests/kfz/k6_slots.ci, and the fuzz's processes made by fork and reaped)
    ('finish: a vfork wait left in the slot', 'src/proc.ci',
     '    vfork_child[pid] = 0;\n    digest_now(pid);', '    digest_now(pid);'),
    ("fork: the slot's timed poll kept", 'src/proc.ci',
     '    poll_wait[c] = 0;\n    poll_spent[c] = false;', '    poll_spent[c] = false;'),
    ("fork: the slot's capture length kept", 'src/proc.ci', '    capture[c] = false;\n    caplen[c] = 0;',
     '    capture[c] = false;'),
    ("fork: the slot's turns kept", 'src/proc.ci',
     '    ticks[c] = 0;\n    facts.tick_fresh(c);', '    facts.tick_fresh(c);'),
    ('exit: a download left running', 'src/proc.ci',
     "the desk's icon stays as it is\n        dlrun[pid] = false;\n", "the desk's icon stays as it is\n"),
    ("exit: ring 0's hold left", 'src/proc.ci', '    hold_end[pid] = 0;\n', ''),
    # HW-4m (src/usbms.ci, src/usbscsi.ci) and src/xhci.ci's third place, against tests/kfz/xhc.ci
    ('usbscsi: a CSW of another tag taken', 'src/usbscsi.ci',
     'get_le32(b, 0) != 0x53425355 || get_le32(b, 4) != (tag & 0xFFFFFFFF) || b[12] > 2',
     'get_le32(b, 0) != 0x53425355 || b[12] > 2'),
    ('usbscsi: a CSW of another signature taken', 'src/usbscsi.ci',
     'get_le32(b, 0) != 0x53425355 || get_le32(b, 4) != (tag & 0xFFFFFFFF) || b[12] > 2',
     'get_le32(b, 4) != (tag & 0xFFFFFFFF) || b[12] > 2'),
    ('usbscsi: blocks of any length', 'src/usbscsi.ci',
     'if (blen != 512 || last == 0xFFFFFFFF) {',
     'if (last == 0xFFFFFFFF) {'),
    ('usbscsi: a last block of all ones', 'src/usbscsi.ci',
     'if (blen != 512 || last == 0xFFFFFFFF) {',
     'if (blen != 512) {'),
    ('usbscsi: endpoint 0 taken', 'src/usbscsi.ci',
     'if ((ea & 0x80) == 0 && !has_out && (ea & 15) != 0) {',
     'if ((ea & 0x80) == 0 && !has_out) {'),
    ('usbms: fewer than 8 sectors', 'src/usbms.ci',
     'if (total < SECTORS_PER_REQUEST) {',
     'if (total < 1) {'),
    ('usbms: a read past the end', 'src/usbms.ci',
     'sector > sectors - SECTORS_PER_REQUEST) {',
     'sector > sectors - 1) {'),
    ('usbscsi: a data stage the CSW disagrees with taken', 'src/usbscsi.ci',
     'residue <= nbytes && moved == nbytes - residue;',
     'residue <= nbytes;'),
    ('usbms: a short block taken', 'src/usbms.ci',
     'if (r == usbscsi.PASSED && moved == nbytes) {',
     'if (r == usbscsi.PASSED) {'),
    ('usbms: INQUIRY short of its product taken', 'src/usbms.ci',
     'if (r != usbscsi.PASSED || moved < 32) {',
     'if (r != usbscsi.PASSED) {'),
    ('usbms: READ CAPACITY short taken', 'src/usbms.ci',
     'if (r != usbscsi.PASSED || moved != usbscsi.CAPACITY_BYTES) {',
     'if (r != usbscsi.PASSED) {'),
    ("usbms: the caller's frame in a TRB", 'src/usbms.ci',
     'I64 r = run(c, n, !wr, data, nbytes);',
     'I64 r = run(c, n, !wr, addr, nbytes);'),
    # RS-SLEEP (U1-2 edition 2): tests/kfz/k6_clock.ci
    ('RS-SLEEP: a live sleep returns at once', 'src/proc.ci',
     '    if (r != 0 || !sleep_wall || clock[pid] <= c0) {', '    if (true) {'),
    ('RS-SLEEP: a parked nanosleep moves the clock again', 'src/proc.ci',
     '    if (sleep_until[pid] != 0) {\n        return sleep_on(pid);\n    }\n    U64 c0 = clock[pid];\n'
     '    return sleep_park(pid, c0, nanosleep_clock(pid, req));',
     '    U64 c0 = clock[pid];\n    return sleep_park(pid, c0, nanosleep_clock(pid, req));'),
    ('RS-SLEEP: a sleep ends a tick early', 'src/proc.ci',
     '    if (wall_ns() < sleep_until[pid]) {', '    if (wall_ns() + 10000000 < sleep_until[pid]) {'),
    ('RS-SLEEP: a replay or a date without RDRAND waits', 'src/proc.ci',
     '    sleep_wall = rng.mode() == rng.LIVE;', '    sleep_wall = true;'),
    ('RS-SLEEP: WAIT_MAX ends a sleeper', 'src/proc.ci',
     '    return sleep_until[dev] != 0 || waited < WAIT_MAX', '    return waited < WAIT_MAX'),
    ('RS-SLEEP: a sleeper chosen before a device wait', 'src/proc.ci',
     '            if (on_device[p] && sleep_until[p] != 0) {', '            if (false) {'),
    ('RS-SLEEP: an ended sleeper leaves its sleep parked', 'src/proc.ci',
     '    sleep_until[pid] = 0;              // RS-SLEEP: a sleeper ended', '    // RS-SLEEP: a sleeper ended'),
    ('usbms: no SYNCHRONIZE CACHE before the end', 'src/usbms.ci',
     '    if (!unsynced || !xhci.ms_on()) {', '    if (true) {'),
    ('usbms: a failed SYNCHRONIZE CACHE taken as done', 'src/usbms.ci',
     '    if (r == usbscsi.PASSED || (why >= 0 && why / 65536 == 5)) {', '    if (true) {'),
    ('usbms: a write that fails is not synced', 'src/usbms.ci',
     '        unsynced = true;                                     // set before the CBW: a write that failed may have landed\n', ''),
    ('blk: no flush of the USB disk', 'src/blk.ci', '        return usbms.flush();', '        return true;'),
    ('usbms: SYNCHRONIZE CACHE waited for 5 s only', 'src/usbms.ci',
     'run_wait(c, n, false, io, 0, xhci.SYNC_MS)', 'run(c, n, false, io, 0)'),
    ('usbms: every command waited for 30 s', 'src/usbms.ci',
     'return run_wait(cdb, cdb_len, data_in, addr, nbytes, xhci.BULK_MS);',
     'return run_wait(cdb, cdb_len, data_in, addr, nbytes, xhci.SYNC_MS);'),
    ('xhci: a bulk wait that ignores its limit', 'src/xhci.ci',
     '    while (clock_ms() < ms && t < SPIN * ms / 500) {', '    while (clock_ms() < BULK_MS && t < SPIN * ms / 500) {'),
    ('usbms: a write to a disk not named', 'src/usbms.ci',
     '    if (!may_write) {\n        return false;\n    }\n    return move(true, sector, addr);',
     '    return move(true, sector, addr);'),
    ('usbms: not ready without end', 'src/usbms.ci',
     'while (r == usbscsi.FAILED && tries < READY_TRIES) {',
     'while (r == usbscsi.FAILED && tries < 2 * READY_TRIES) {'),
    ('xhci: no Stop Endpoint when a bulk transfer is not answered', 'src/xhci.ci',
     '    _ = command(0, 0, 0x3C00 | ((b_dci[e] as U64) << 16) | ((d_slot[2] as U64) << 24));       // Stop Endpoint\n'
     '    disk_on = false;',
     '    disk_on = false;'),
    ('xhci: a bulk transfer waited on past 5 s', 'src/xhci.ci',
     'while (clock_ms() < BULK_MS && t < 10 * SPIN) {',
     'while (clock_ms() < 2 * BULK_MS && t < 10 * SPIN) {'),
    ("xhci: another endpoint's event taken", 'src/xhci.ci',
     'tx_code >= 0 && tx_slot == d_slot[2] && tx_dci == b_dci[e]) {',
     'tx_code >= 0) {'),
    ('xhci: a slot id past the slots taken', 'src/xhci.ci',
     'if (code != 1 || cc_slot <= 0 || cc_slot > slots) {',
     'if (code != 1 || cc_slot <= 0) {'),
    ('xhci: an Enable Slot naming a slot in use taken', 'src/xhci.ci',
     '    if (held[s]) {', '    if (false) {'),
    ('xhci: a slot given back still held', 'src/xhci.ci',
     '    held[s] = false;\n    return true;', '    return true;'),
    ('xhci: a slot not confirmed given back', 'src/xhci.ci',
     ': Disable Slot not confirmed; the slot stays out of use\\n");\n        return false;',
     ': Disable Slot not confirmed; the slot stays out of use\\n");\n        held[s] = false;\n        return false;'),
    ('xhci: capability registers past a short BAR read', 'src/xhci.ci',
     'if (span < 0x20) {', 'if (false) {'),
    ('xhci: port registers past the BAR read', 'src/xhci.ci',
     'caplen + 0x400 + (16 * ports) as U64 > span', 'false'),
    ('xhci: CAPLENGTH left out of the bound', 'src/xhci.ci',
     'caplen + 0x400 + (16 * ports) as U64 > span', '0x400 + (16 * ports) as U64 > span'),
    ('xhci: doorbells past the BAR rung', 'src/xhci.ci',
     'dboff + (4 * (slots + 1)) as U64 > span', 'dboff > span'),
    ('xhci: runtime registers past the BAR read', 'src/xhci.ci',
     'rtoff + 0x40 > span', 'rtoff > span'),
    ('xhci: runtime registers to the BAR end refused', 'src/xhci.ci',
     'rtoff + 0x40 > span', 'rtoff + 0x40 >= span'),
    ('xhci: an extended capability past the BAR read', 'src/xhci.ci',
     '        if (x + 8 > span) {', '        if (x > span) {'),
    ('xhci P3-3: a report pointer subtracted before its range check', 'src/xhci.ci',
     '    if (at < lo || at >= lo + (16 * IRING) as U64) {', '    if (((at - lo) / 16) as I64 >= IRING) {'),
    ('xhci P3-3: a report outside the ring posts its TRB again', 'src/xhci.ci',
     '        return;                                              // no TRB of its ring: none completed, none to post',
     '        post(d);\n        return;                                              // no TRB of its ring: none'),
    ('xhci P3-1: bus mastering before the bounds', 'src/xhci.ci',
     '    pci_command(dev, 2, 0);', '    pci.enable_mem_dma(dev);'),
    ('xhci P3-1: bus mastering left on when given up', 'src/xhci.ci',
     '        pci_command(dev, 0, 4);', '        pci_command(dev, 0, 0);'),
    # RS-CLK2 (a review's P1 4), a program's CLOCK_REALTIME on the stamp time's line
    ("clock: a program starts at the boot's second", 'src/proc.ci',
     '    zero_at[pid] = now_rel() as I64;', '    zero_at[pid] = 0;'),
    ("clock: a fork's child off its parent's line", 'src/proc.ci', '    zero_at[c] = zero_at[pid];\n', ''),
    ('clock: CLOCK_REALTIME the bare clock again', 'src/proc.ci',
     '        t = real_rel(pid);\n    }\n    if (clk == 7) {', '    }\n    if (clk == 7) {'),
    ("clock: a set leaves each process's run since its start", 'src/proc.ci',
     '        zero_at[q] = 0 - clock[q] as I64;', '        zero_at[q] = zero_at[q];'),
    ("clock: an absolute sleep ignores the process's line", 'src/proc.ci',
     '        I64 z = zero_at[pid];\n        if (z >= 0) {', '        I64 z = 0;\n        if (z >= 0) {'),
    ("clock: the system's time the furthest bare clock", 'src/proc.ci',
     '    }\n    far = stamp.further(far, time_line(pid));', '    }\n    far = stamp.further(far, clock[pid]);'),
    ("clock: a dated boot's time ignores the machine's clock", 'src/proc.ci',
     '    return rng.wall_take(s) as U64 * NS;', '    return far - far_set;'),
    ("clock: a dated boot's time takes the furthest line (any sleep moves it)", 'src/proc.ci',
     '    if (!dated) {\n        return far - far_set;', '    if (!dated || far - far_set > wall_ns() - wall_set) {\n        return far - far_set;'),
    ('clock: a set leaves the wall seconds where they were', 'src/proc.ci', '    rng.wall_reset();\n', ''),
    ("clock: a replay reads the machine's clock", 'src/rng.ci',
     '    if (journaled) {\n        v = wall_last;', '    if (false) {\n        v = wall_last;'),
    ("clock: a replay ignores its wal lines", 'src/rng.ci',
     '            if (w >= 0) {\n                v = w;', '            if (false) {\n                v = w;'),
    ('clock: a wal line not printed', 'src/rng.ci', '        serial.serial_write(record[0..end + 1]);\n', ''),
    ('clock: a replay takes the next wal line at any call', 'src/rng.ci',
     '                if (n != wall_calls || parse_end != line_len) {', '                if (n < 0 || parse_end != line_len) {'),
    ("clock: a record printed on a program's open line", 'src/rng.ci',
     '    if (!serial.at_line_start()) {', '    if (false) {'),
    ('clock: a running process never catches up', 'src/proc.ci',
     '            zero_at[pid] = zero_at[pid] + (n - r) as I64;\n', ''),
    ("clock: a set leaves the machine's clock running from the boot's", 'src/proc.ci',
     '    wall_set = wall_ns();              // RS-CLK2: the machine', '    // RS-CLK2: the machine'),
    ("clock: a stamp ignores the machine's clock", 'src/proc.ci',
     '    stamped = stamp.time(now_rel(), realtime_s, stamped);', '    stamped = stamp.time(far - far_set, realtime_s, stamped);'),
    ('clock: a timespec of 10^9 s or more -EINVAL again', 'src/proc.ci',
     '    if (s >= 0x8000000000000000 || n >= NS) {', '    if (s > NS || n >= NS) {'),
    ('clock: a negative timespec taken', 'src/proc.ci',
     '    if (s >= 0x8000000000000000 || n >= NS) {', '    if (n >= NS) {'),
    # PR 365: DN-69 item 5, KF edition 14, KF-R1 (PR 342), RS-CLK (PR 357)
    ('facts: a Parent sees no other account', 'src/facts.ci',
     'caller_uid == 0 || caller_kern || caller_parent;', 'caller_uid == 0 || caller_kern;'),
    ("kill: -EPERM, not -ESRCH, for a pid a Child may not see", 'src/facts.ci',
     '    if (!sees(caller_uid, caller_kern, caller_parent, slot_uid)) {\n        return -3;',
     '    if (!sees(caller_uid, caller_kern, caller_parent, slot_uid)) {\n        return -1;'),
    ('getpgid: any pid of the family', 'src/proc.ci',
     'if (t < 0 || !facts.sees(fs.uid_of(pid), (fs.grant_of(pid)', 'if (t < 0 || !facts.sees(0, (fs.grant_of(pid)'),
    ('login: a bit past 32 taken', 'src/proc.ci',
     '    U64 g = c & ~facts.LOGIN_PARENT;', '    U64 g = c & 0xFFFFFFFF;'),
    ("facts: a fork's child is a Child", 'src/proc.ci', '    facts.role_fork(c, pid);', ''),
    ('facts: ticks given to no slot', 'src/facts.ci', '        ran_sum[slot] += n;', ''),
    ("facts: a fork's child takes the slot's old ticks", 'src/proc.ci', '    facts.tick_fresh(c);', ''),
    ('clock_settime: any caller', 'src/proc.ci',
     '    if (fs.uid_of(pid) != 0 && (fs.grant_of(pid) & fs.GRANT_KERN) == 0) {\n        return 0 - EPERM;\n    }\n'
     '    I64 t = s as I64;',
     '    I64 t = s as I64;'),
    ('clock_settime: nanoseconds unchecked', 'src/proc.ci',
     'if (n >= NS || s >= civil.SETTOD_MAX as U64) {', 'if (s >= civil.SETTOD_MAX as U64) {'),
    # LO-1 (PR 399): the sweep's three tests of a slot (src/seat.ci ends), its caller and range, and the seat's gate
    ('LO-1 sweep: any uid of the family', 'src/seat.ci',
     'live && family && slot_uid == target;', 'live && family;'),
    ('LO-1 sweep: an ended process too', 'src/seat.ci',
     'target <= 65535 && live && family', 'target <= 65535 && family'),
    ('LO-1 sweep: another family too', 'src/seat.ci',
     'live && family && slot_uid', 'live && slot_uid'),
    ('LO-1 sweep: any uid 0 caller', 'src/proc.ci',
     'I64 sys_sweep(I64 pid, I64 uid) {\n    if (pid != tile.tiler_pid() || fs.uid_of(pid) != 0) {',
     'I64 sys_sweep(I64 pid, I64 uid) {\n    if (fs.uid_of(pid) != 0) {'),
    ('LO-1 sweep: the tiler at any uid', 'src/proc.ci',
     'I64 sys_sweep(I64 pid, I64 uid) {\n    if (pid != tile.tiler_pid() || fs.uid_of(pid) != 0) {',
     'I64 sys_sweep(I64 pid, I64 uid) {\n    if (pid != tile.tiler_pid()) {'),
    ('LO-1 sweep: uid 0 asked', 'src/proc.ci',
     '    if (uid < 1 || uid > 65535) {', '    if (uid < 0 || uid > 65535) {'),
    ('LO-1 seat: any uid 0 caller', 'src/proc.ci',
     'I64 sys_seat(I64 pid, I64 uid) {\n    if (pid != tile.tiler_pid() || fs.uid_of(pid) != 0) {',
     'I64 sys_seat(I64 pid, I64 uid) {\n    if (fs.uid_of(pid) != 0) {'),
    ('LO-1 seat: any process takes the offered tile', 'src/tile.ci',
     'if (next_w == 0 || !seat.binds(uid)) {', 'if (next_w == 0) {'),
    # the desk's corner (tests/kfz/k4_tile.ci's two pixel clients): a placed window is off it, one not placed holds it
    ('W-4 x H-2: a placed window still holds the offered tile', 'src/tile.ci',
     'if (bound[p] && !placed(p) && tx[p] == next_x', 'if (bound[p] && tx[p] == next_x'),
    ('W-4 x H-2: no client holds the offered tile', 'src/tile.ci',
     'if (bound[p] && !placed(p) && tx[p] == next_x', 'if (false && tx[p] == next_x'),
    ('W-4 x H-2: a WANT leaves the window placed', 'src/tile.ci',
     '    swait[pid] = sonce[pid];        // a resize; a program\'s first ask before its first map shows as before\n    unplace(pid);\n',
     '    swait[pid] = sonce[pid];        // a resize; a program\'s first ask before its first map shows as before\n'),
    ('LO-1 seat: OPEN named again', 'src/seat.ci',
     'if (uid < NONE || uid > 65535) {', 'if (uid < OPEN || uid > 65535) {'),
    ('LO-1 seat: a named seat binds every uid', 'src/seat.ci',
     '(named >= 0 && uid == named)', '(named >= 0)'),
    # AC-D4: the kernel's cooldown (src/proc.ci cool, ask, new_child, kern_forget; tests/kfz/k2_cool.ci)
    ('AC-D4: a no cools nothing', 'src/proc.ci',
     '                    kq_state[k] = KQ_NO;\n                    cool(p);',
     '                    kq_state[k] = KQ_NO;'),
    ('AC-D4: an ask ignores the cool', 'src/proc.ci',
     'if (cool_end[pid] > 0 && trap.timer_ticks() < cool_end[pid]) {', 'if (false) {'),
    ('AC-D4: the cool ends a second early', 'src/proc.ci',
     'if (cool_end[pid] > 0 && trap.timer_ticks() < cool_end[pid]) {',
     'if (cool_end[pid] > 0 && trap.timer_ticks() + 100 < cool_end[pid]) {'),
    ('AC-D4: under 30 s', 'src/proc.ci',
     '(COOL_S * pit.INPUT_HZ + pit.USER_DIVISOR - 1) / pit.USER_DIVISOR', 'COOL_S * pit.INPUT_HZ / pit.USER_DIVISOR'),
    ('AC-D4: a fork drops the mark', 'src/proc.ci',
     '    cool_end[c] = cool_end[pid];', '    cool_end[c] = 0;'),
    ('AC-D4: the asker alone', 'src/proc.ci',
     '(q == p || (window[p] != 0 && window[q] == window[p]))', 'q == p'),
    ('AC-D4: every window of the family', 'src/proc.ci',
     '(q == p || (window[p] != 0 && window[q] == window[p]))', '(q == p || window[p] != 0)'),
    ('AC-D4: no window is one tree', 'src/proc.ci',
     '(q == p || (window[p] != 0 && window[q] == window[p]))', '(q == p || window[q] == window[p])'),
    ('AC-D4: uid 0 cooled', 'src/proc.ci',
     '    if (fs.uid_of(p) == 0) {\n        return;\n    }\n    I64 e = trap.timer_ticks() + cool_ticks();',
     '    I64 e = trap.timer_ticks() + cool_ticks();'),
    ('AC-D4: the tree\'s waiting requests kept', 'src/proc.ci',
     '                if (kq_pid[k] == q && kq_state[k] == KQ_ASKED) {', '                if (false) {'),
    ('AC-D4: an end keeps its mark', 'src/proc.ci',
     '    hold_end[pid] = 0;\n    cool_end[pid] = 0;', '    hold_end[pid] = 0;'),
    # RS-KR (PR 372, the kernel's wiring): the repeat as the desk reads it, and who sets its values
    ('RS-KR: a read asks no repeat', 'src/input.ci', '    _ = inq.repeat(now);\n', ''),
    ('RS-KR: USB keys at tick 0', 'src/input.ci',
     'inq.usb_key(code, value, trap.timer_ticks())', 'inq.usb_key(code, value, 0)'),
    ('RS-KR: PS/2 keys at tick 0', 'src/input.ci', 'inq.decode(b, now)', 'inq.decode(b, 0)'),
    ("RS-KR: the keyboard's own repeat reaches the reader", 'src/keyrep.ci',
     '        if (is_down(code)) {\n            return false;\n        }',
     '        if (is_down(code)) {\n            return true;\n        }'),
    ('RS-KR: a held modifier repeats', 'src/keyrep.ci', '        if (!modifier(code)) {', '        if (true) {'),
    ('RS-KR: the delay is the period', 'src/keyrep.ci', '    if (ms < delay_ms) {', '    if (ms < period_ms) {'),
    ('RS-KR EVIOCSREP: any holder sets', 'src/proc.ci',
     '    if (pid != tile.tiler_pid() || fs.uid_of(pid) != 0) {\n        return 0 - EPERM;\n    }\n'
     '    if (arg >= uvm.USER_HI || uvm.peek(pid, arg, b, 8) != 8) {',
     '    if (arg >= uvm.USER_HI || uvm.peek(pid, arg, b, 8) != 8) {'),
    ('RS-KR EVIOCSREP: the tiler at any uid', 'src/proc.ci',
     '    if (pid != tile.tiler_pid() || fs.uid_of(pid) != 0) {\n        return 0 - EPERM;\n    }\n'
     '    if (arg >= uvm.USER_HI || uvm.peek(pid, arg, b, 8) != 8) {',
     '    if (pid != tile.tiler_pid()) {\n        return 0 - EPERM;\n    }\n'
     '    if (arg >= uvm.USER_HI || uvm.peek(pid, arg, b, 8) != 8) {'),
    ('RS-KR EVIOCSREP: values past the top taken', 'src/keyrep.ci',
     'if (d < DELAY_MIN || d > DELAY_MAX || p < PERIOD_MIN || p > PERIOD_MAX) {',
     'if (d < DELAY_MIN || p < PERIOD_MIN) {'),
    ('RS-KR EVIOCGREP: into read-only memory', 'src/proc.ci',
     'if (arg >= uvm.USER_HI || uvm.poke(pid, arg, b, 8, true) != 8) {',
     'if (arg >= uvm.USER_HI || uvm.poke(pid, arg, b, 8, false) != 8) {'),
    ('RS-KR: the repeat asked before the ring drains', 'src/input.ci',
     '    I64 now = trap.timer_ticks();\n    Bool more = true;\n',
     '    I64 now = trap.timer_ticks();\n    _ = inq.repeat(now);\n    Bool more = true;\n'),
    ('RS-KR: a repeat while a keyboard byte waits in its ring (KFZ-9)', 'src/input.ci',
     '    if (drained) {\n        _ = inq.repeat(now);\n    }', '    _ = inq.repeat(now);'),
    ('RS-KR EVIOCSREP: a set mid-hold restarts the count', 'src/keyrep.ci',
     '    delay_ms = d;\n    period_ms = p;\n    return true;',
     '    delay_ms = d;\n    period_ms = p;\n    sent = 0;\n    return true;'),
    ('RS-KR EVIOCSREP: a set mid-hold is lost', 'src/keyrep.ci',
     '    delay_ms = d;\n    period_ms = p;\n    return true;',
     '    if (held != 0) {\n        return true;\n    }\n    delay_ms = d;\n    period_ms = p;\n    return true;'),
    # AC-D4, the KFZ lane's cases (tests/kfz/k8_cool.ci)
    ('AC-D4: the cool ends a tick late', 'src/proc.ci',
     'trap.timer_ticks() < cool_end[pid]', 'trap.timer_ticks() <= cool_end[pid]'),
    ('AC-D4: the cool ends a tick early', 'src/proc.ci',
     'trap.timer_ticks() < cool_end[pid]', 'trap.timer_ticks() + 1 < cool_end[pid]'),
    ('AC-D4: a waiting process of the tree unmarked', 'src/proc.ci',
     'if ((state[q] == READY || state[q] == WAITING) && root[q] == root[p] &&',
     'if (state[q] == READY && root[q] == root[p] &&'),
    ('AC-D4: execve clears the mark', 'src/proc.ci',
     '    execs += 1;\n    exec_at[pid] = execs;',
     '    cool_end[pid] = 0;\n    execs += 1;\n    exec_at[pid] = execs;'),
    ('AC-D4: execve forgets as an end does', 'src/proc.ci',
     '    fs.proc_exec(pid);\n', '    fs.proc_exec(pid);\n    kern_forget(pid);\n'),
    ('AC-D4: grant_ask not cooled', 'src/proc.ci',
     '    if (cool_end[pid] > 0 && trap.timer_ticks() < cool_end[pid]) {',
     '    if (want == fs.GRANT_KERN && cool_end[pid] > 0 && trap.timer_ticks() < cool_end[pid]) {'),
    # HW-12, the KFZ lane's cases (tests/kfz/k5_usb.ci): a disk with a GUID table, written by its volume's GUID only
    ("HW-12: a write at the device's sector, not the volume's", 'src/usbms.ci',
     '    I64 n = usbscsi.cdb_rw(c, wr, base + sector, SECTORS_PER_REQUEST);',
     '    I64 at = base + sector;\n    if (wr) {\n        at = sector;\n    }\n'
     '    I64 n = usbscsi.cdb_rw(c, wr, at, SECTORS_PER_REQUEST);'),
    ("HW-12: the volume's GUID taken from the first entry used, the ESP's", 'src/usbms.ci',
     '                if (k == 1 && pick < 0) {\n                    pick = used;\n'
     '                    pick_n = 4 * s + e + 1;\n                    for j in 0..16 {\n'
     '                        uid[j] = u[j];\n                    }\n                }',
     '                if (used == 0) {\n                    for j in 0..16 {\n'
     '                        uid[j] = u[j];\n                    }\n                }\n'
     '                if (k == 1 && pick < 0) {\n                    pick = used;\n'
     '                    pick_n = 4 * s + e + 1;\n                }'),
    ('HW-12: a model names a disk with a GUID table', 'src/usbms.ci',
     '        may_write = gpt.names(line, line_n, "daphnis.disk.write=", uid);',
     '        may_write = gpt.names(line, line_n, "daphnis.disk.write=", uid) ||\n'
     '            usbscsi.names(line, line_n, "daphnis.disk.write=", name, name_n);'),
    ("HW-12: a raw device keeps the last table's partition and GUID", 'src/usbms.ci',
     '    base = 0;\n    parted = false;\n    for j in 0..16 {\n        uid[j] = 0;\n    }\n', '    base = 0;\n'),
    ('HW-12: a header that is not sound read as a raw device', 'src/usbms.ci',
     '    if (t == 0 && !gpt.protective(mbr)) {', '    if (t <= 0) {'),
    ('HW-12: a protective MBR with no header read as a raw device', 'src/usbms.ci',
     '    if (t == 0 && !gpt.protective(mbr)) {', '    if (t == 0) {'),
    ("HW-12: the partition entries' CRC not checked", 'src/usbms.ci',
     '    if (!sound || gpt.crc_final(crc) != g[2] as U64) {', '    if (!sound) {'),
    ('HW-12: a volume sharing a sector with the ESP taken', 'src/usbms.ci',
     'if (i != pick && gpt.overlap(first, last,', 'if (i == -1 && gpt.overlap(first, last,'),
    # HW-14 (daphnis.uart=0), the KFZ lane's console cases (tests/kfz/console_user.c, C on the host)
    ('HW-14: the word not read', 'rt/console.c',
     '        uart = rt_console_uart_off() ? 0 : uart_probe();', '        uart = uart_probe();'),
    ('HW-14: COM1 probed under the word', 'rt/console.c',
     '        uart = rt_console_uart_off() ? 0 : uart_probe();',
     '        uart = uart_probe();\n        if (rt_console_uart_off()) uart = 0;'),
    ('HW-14: decided before the line is read', 'rt/console.c',
     '        if (!rt_boot_read()) return uart_probe() == 1;\n', ''),
    ('HW-14: nothing to COM1 before the line is read', 'rt/console.c',
     '        if (!rt_boot_read()) return uart_probe() == 1;', '        if (!rt_boot_read()) return false;'),
    ('HW-14: the word drops the byte', 'rt/console.c',
     '    ring[written % CONSOLE_RING] = c;\n    written++;\n    if (uart_there()) {',
     '    if (rt_console_uart_off()) return;\n    ring[written % CONSOLE_RING] = c;\n'
     '    written++;\n    if (uart_there()) {'),
    ('HW-14: the word turns the screen off too', 'rt/console.c',
     '    screen = cmdline_word("daphnis.console=screen") ? 1 : 0;',
     '    screen = cmdline_word("daphnis.console=screen") && !rt_console_uart_off() ? 1 : 0;'),
    ('HW-14: the hooks decide before the line is read', 'rt/console.c',
     '        if (!rt_boot_read()) return false;\n        off = ', '        off = '),
    ('HW-14: rt_boot_read true before rt_boot_init finishes', 'rt/boot.c',
     'bool rt_boot_read(void) { return boot_done; }', 'bool rt_boot_read(void) { return true; }'),
    ('HW-14: a boot word read without its end', 'rt/boot.c',
     "(i + k == n || line[i + k] == ' ') && memcmp(line + i, w, k) == 0", 'memcmp(line + i, w, k) == 0'),
    ('HW-14: a boot word read without its start', 'rt/boot.c',
     "if ((i == 0u || line[i - 1u] == ' ') && (i + k == n", 'if ((i + k == n'),
    ("HW-14 hooks: LCR read from the port again", 'rt/host.c',
     '    if (port == 0x3F8u && (com1_lcr & 0x80u) == 0u)\n        rt_console_byte(',
     '    if (port == 0x3F8u && (port_in8(0x3FBu) & 0x80u) == 0u)\n        rt_console_byte('),
    ("HW-14 hooks: LCR's shadow not kept", 'rt/host.c',
     '    if (port == 0x3FBu) com1_lcr = (uint8_t)a[1].as.u64;\n    if (port == 0x3F8u && (com1_lcr & 0x80u) == 0u)\n'
     '        rt_console_byte(',
     '    if (port == 0x3F8u && (com1_lcr & 0x80u) == 0u)\n        rt_console_byte('),
    ("HW-14 hooks: COM1's register writes reach the port under the word", 'rt/host.c',
     '    else if (!com1_port(port) || !rt_console_uart_off())\n', '    else\n'),
    ("HW-14 hooks: COM1's reads reach the port under the word", 'rt/host.c',
     '    if (com1_port(port) && rt_console_uart_off()) r->as.u64 = port == 0x3FDu ? 0x60u : 0u;',
     '    if (com1_port(port) && rt_console_uart_off()) r->as.u64 = port_in8(port);'),
    ('HW-14 hooks: LSR not ready to send under the word', 'rt/host.c',
     'r->as.u64 = port == 0x3FDu ? 0x60u : 0u;', 'r->as.u64 = port == 0x3FDu ? 0x40u : 0u;'),
    ('HW-14 hooks: LSR says a byte came under the word', 'rt/host.c',
     'r->as.u64 = port == 0x3FDu ? 0x60u : 0u;', 'r->as.u64 = port == 0x3FDu ? 0x61u : 0u;'),
    ("HW-14 hooks: COM1's range one port short", 'rt/host.c',
     'return port >= 0x3F8u && port <= 0x3FFu;', 'return port >= 0x3F8u && port <= 0x3FEu;'),
    ("HW-14 hooks: COM1's range one port wide", 'rt/host.c',
     'return port >= 0x3F8u && port <= 0x3FFu;', 'return port >= 0x3F7u && port <= 0x3FFu;'),
    ('HW-17 dev: /dev/null is no name', 'src/fs.ci',
     'if (k == 8 && name_at(w_raw, at, "dev/null")) {', 'if (k == 8 && name_at(w_raw, at, "dev/nulx")) {'),
    ('HW-17 dev: a read of /dev/null takes a byte', 'src/fs.ci',
     '        return 0;                      // /dev/null: the end at once', '        return 1;                      // /dev/null: the end at once'),
    ('HW-17 dev: a write-only /dev/null reads', 'src/fs.ci',
     """    if (o_kind(o) == KIND_NULL) {
        if ((o_flags(o) & O_ACCMODE) == 1) {
            return 0 - EBADF;
        }
        return 0;                      // /dev/null""", """    if (o_kind(o) == KIND_NULL) {
        if ((o_flags(o) & O_ACCMODE) == 9) {
            return 0 - EBADF;
        }
        return 0;                      // /dev/null"""),
    ('HW-17 dev: a read-only /dev/null writes', 'src/fs.ci',
     '        if ((o_flags(o) & O_ACCMODE) == 0) {\n            return 0 - EBADF;\n        }\n        if (n > 0x7FFFF000) {',
     '        if ((o_flags(o) & O_ACCMODE) == 9) {\n            return 0 - EBADF;\n        }\n        if (n > 0x7FFFF000) {'),
    ('HW-17 dev: /dev/null is a file of no device', 'src/fs.ci',
     '        w[5] = NULL_RDEV;', '        w[5] = 0;'),
    ('HW-17 dev: /dev/tty without a terminal opens', 'src/fs.ci',
     '                return 0 - ENXIO;      // no controlling terminal', '                dev_pty = 0;      // no controlling terminal'),
    ('HW-17 dev: /dev/tty is any session\'s terminal', 'src/pty.ci',
     '    if (i >= 0 && i < PTYS && controls(pid, i)) {', '    if (i >= 0 && i < PTYS) {'),
    # AM-4: a pixel program's own rows (src/tile.ci FBIO_TILE_MENU, src/proc.ci FBIO_TILE_INFO 15 and 16;
    # tests/kfz/k4_tile_rows.ci)
    ("AM-4 rows: a child's child taken", 'src/tile.ci',
     'if (jid == par && jpar == 0) { rooted = true; }', 'if (jid == par) { rooted = true; }'),
    ('AM-4 rows: an id twice taken', 'src/tile.ci',
     '                    if (jid == id) { return 0 - EINVAL; }\n', ''),
    ("AM-4 rows: the Settings item's id taken", 'src/tile.ci',
     'if (jid == sid) { return 0 - EINVAL; }', 'if (jid == sid + 65536) { return 0 - EINVAL; }'),
    ('AM-4 rows: a mark past the three taken', 'src/tile.ci', '(mk & (0xFF - 7)) != 0', '(mk & (0xFF - 15)) != 0'),
    ('AM-4 rows: a 17th row taken', 'src/tile.ci', 'nr == MROWS ||', 'nr == MROWS + 1 ||'),
    ('AM-4 rows: an empty label taken', 'src/tile.ci', 'mk & (0xFF - 7)) != 0 || ln < 1)', 'mk & (0xFF - 7)) != 0 || ln < 0)'),
    ("AM-4 rows: ';' taken", 'src/tile.ci', 'c == 0x7F || c == 59', 'c == 0x7F'),
    ('AM-4 rows: a byte after the NUL taken', 'src/tile.ci',
     '    for k in n..cap {\n        if (e[at + k] != 0) { return -1; }\n    }\n', ''),
    ('AM-4 rows: a three-byte overlong taken', 'src/tile.ci', '            lo = 0xA0;', '            lo = 0x80;'),
    ('AM-4 rows: a surrogate taken', 'src/tile.ci', '            hi = 0x9F;', '            hi = 0xBF;'),
    ('AM-4 rows: past U+10FFFF taken', 'src/tile.ci', '            hi = 0x8F;', '            hi = 0xBF;'),
    ('AM-4 rows: a sequence cut at the 24th byte read past the record', 'src/tile.ci',
     '        if (i + 1 + more > n) { return -1; }\n', ''),
    ('AM-4 rows: keys twice taken', 'src/tile.ci',
     'if (at < 0 || mrow_in[ROW * at + 7] != 0) { return 0 - EINVAL; }', 'if (at < 0) { return 0 - EINVAL; }'),
    ('AM-4 rows: keys past 16 bytes taken', 'src/tile.ci',
     'if (id == 0 || ln < 0 || ln > 16) { return 0 - EINVAL; }', 'if (id == 0 || ln < 0) { return 0 - EINVAL; }'),
    ('AM-4 rows: Settings takes any mark', 'src/tile.ci',
     '(kd >> 8) != MARK_DIM && (kd >> 8) != 0) {', '(kd >> 8) > 0xFF) {'),
    ('AM-4 rows: a refused table changes the declaration', 'src/tile.ci',
     '            if (t < 0) { return 0 - ENOSPC; }   // every table is a window\'s: nothing changed',
     '            if (t < 0) {\n                for k in 0..112 { tmenu[112 * pid + k] = m[k]; }\n                return 0 - ENOSPC;\n            }'),
    ('AM-4 rows: the rows stay after execve', 'src/tile.ci',
     '        rows_free(pid);                // AM-4: and the rows\n', ''),
    ('AM-4 rows: the table stays after the end', 'src/tile.ci', '    rows_free(pid);\n    unplace(pid);', '    unplace(pid);'),
    ('AM-4 rows: a declaration with no row keeps them', 'src/tile.ci',
     '        if (nr == 0) {\n            rows_free(pid);\n            return 0;\n        }',
     '        if (nr == 0) {\n            return 0;\n        }'),
    ('AM-4 rows: the desk reads the next row', 'src/proc.ci',
     'b[8 + k] = tile.row_byte(p, row, k);', 'b[8 + k] = tile.row_byte(p, row + 1, k);'),
    ('AM-4 rows: a program with no window takes a table', 'src/tile.ci',
     'if (nr > 0 && !(kind[pid] == PRIVATE && bound[pid])) {', 'if (nr > 0 && !(kind[pid] == PRIVATE || true)) {'),
    ('AM-4 rows: the count not given', 'src/proc.ci',
     'b[4] = tile.rows_of(p) as U8;', 'b[4] = 16;'),
]


def one(out, i, m):
    name, path, old, new = m
    root = out / ('m%02d' % i)
    c_case = path.startswith('rt/')
    if c_case:
        # HW-14's console cases are C on the host (tests/kfz/console.sh): a copy of rt/ and the case file
        shutil.copytree(REPO / 'rt', root / 'rt')
        (root / 'tests' / 'kfz').mkdir(parents=True)
        shutil.copy(HERE / 'console_user.c', root / 'tests' / 'kfz' / 'console_user.c')
    else:
        shutil.copytree(out / 'root', root)
    f = root / path
    text = f.read_text()
    if text.count(old) != 1:
        return '%-8s %s (its text is not in %s once)' % ('STALE', name, path)
    f.write_text(text.replace(old, new))
    if c_case:
        r = subprocess.run(['bash', str(HERE / 'console.sh'), str(root)], capture_output=True, text=True)
    else:
        cmd = ['cint', 'test'] + (['--toolchain', os.environ['CINT_TOOLCHAIN']] if os.environ.get('CINT_TOOLCHAIN')
                                  else [])
        r = subprocess.run(cmd + ['--cache', str(root / '.cache'), '--root', '.', 'src/proc.ci'], cwd=root,
                           capture_output=True, text=True)
    shutil.rmtree(root)
    if r.returncode == 0:
        return '%-8s %s' % ('MISSED', name)
    if '... FAILED' not in r.stdout + r.stderr:
        return '%-8s %s (the mutant did not build: %s)' % ('BROKEN', name, (r.stdout + r.stderr).strip()[:160])
    return '%-8s %s' % ('CAUGHT', name)


def main():
    args = sys.argv[1:]
    jobs = 2
    if '--jobs' in args:
        k = args.index('--jobs')
        jobs = int(args[k + 1])
        del args[k:k + 2]
    only = ''
    if '--only' in args:
        k = args.index('--only')
        only = args[k + 1]
        del args[k:k + 2]
    if len(args) != 1:
        sys.exit('usage: mutants.py OUT [--jobs N] [--only TEXT]')
    out = pathlib.Path(args[0])
    subprocess.run([sys.executable, str(HERE / 'hostroot.py'), str(out / 'root')], check=True)
    picked = [(i, m) for i, m in enumerate(MUTANTS) if only in m[0]]
    with concurrent.futures.ThreadPoolExecutor(jobs) as ex:
        lines = list(ex.map(lambda im: one(out, *im), picked))
    print('\n'.join(lines))
    bad = [x for x in lines if not x.startswith('CAUGHT')]
    print('mutants: %d of %d caught' % (len(lines) - len(bad), len(lines)))
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
