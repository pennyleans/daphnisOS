#!/usr/bin/env python3
# tests/hw/i219_mutants.py: whether tests/hw/i219_test.ci has teeth. Each mutant breaks one rule of src/e1000.ci's PCH
# layer in a copy of the tree, never in the tree itself (a review's P1 and P2, named);
# a test of i219_test.ci must then fail. One line a mutant: CAUGHT (a test failed), MISSED (none did) or BROKEN (the
# mutant did not build, which proves nothing). Exit status 1 unless every mutant is caught. Not part of the gate.
#   python3 tests/hw/i219_mutants.py OUT      (OUT must not exist; cint on PATH, CINT_TOOLCHAIN as for check.sh)
import pathlib
import shutil
import subprocess
import sys

TREE = pathlib.Path(__file__).resolve().parent.parent.parent

# (name, text in src/e1000.ci, its replacement): each text occurs once.
MUTANTS = [
    ('P1-1: a register read in the 20 ms after CTRL.RST',
     '    w(R_CTRL, c | CTRL_RST);\n    wait_ms(20);', '    w(R_CTRL, c | CTRL_RST);\n    flush();\n    wait_ms(20);'),
    ('P1-1: waits counted short (a millisecond taken as a microsecond)',
     'void wait_ms(I64 ms) {\n    wait_us(1000 * ms);', 'void wait_ms(I64 ms) {\n    wait_us(ms);'),
    ('P1-2: open is false with the link down',
     '            i219_say("opened; no link yet (no cable, or the far end is still negotiating)");',
     '            i219_say("opened; no link yet (no cable, or the far end is still negotiating)");\n            return false;'),
    ("P1-3: 305's ULP mask, 0x00F5", 'const U64 ULP_CLEAR = 0x1D74;', 'const U64 ULP_CLEAR = 0x00F5;'),
    ('P1-3: ULP cleared, never committed with START',
     '        _ = phy_write(PG_ULP, RG_ULP_CONFIG1, v | ULP_START);', ''),
    ('P2-4: the MAC never unforced from SMBus after the LANPHYPC toggle',
     '        if (!ok) {\n            w(R_CTRL_EXT, r(R_CTRL_EXT) & (0xFFFFFFFF ^ CTRL_EXT_FORCE_SMBUS));\n            ok = phy_answers();\n        }\n',
     ''),
    ('P2-5: the page select written at PHY address 2',
     'return mdic(1, 31, MDIC_OP_WRITE, sel << 5);', 'return mdic(2, 31, MDIC_OP_WRITE, sel << 5);'),
    ('P2-7: the descriptor flush check dropped',
     '    if (r(R_TDLEN) != 0 && ((pci.read32(dev, PCI_DESC_RING_STATUS) as U64) & FLUSH_DESC_REQUIRED) != 0) {',
     '    if (false) {'),
    ('P2-8: 128 multicast words on the PCH',
     '        for k in 0..32 {                                     // a PCH has 32',
     '        for k in 0..128 {                                     // a PCH has 32'),
    ('P2-9: RAR0 read before the NVM autoload is done',
     '    lan_init_done();\n    U64 s = r(R_STATUS);', '    U64 s = r(R_STATUS);'),
    ('a PHY access after its reset without the semaphore',
     '    if (!swflag_take()) {                                        // e1e_rphy takes the semaphore itself',
     '    if (false) {                                        // e1e_rphy takes the semaphore itself'),
    ("the ME's enforce bit left set",
     '        w(R_H2ME, r(R_H2ME) & (0xFFFFFFFF ^ H2ME_ENFORCE_SETTINGS));\n        return true;', '        return true;'),
    ('opened with a PIT that does not count',
     '        if (!pit_moves()) {', '        if (false) {'),
    ('opened with no PIT to time a wait',
     '        if (!pit.pit_is_programmed(pit.USER_DIVISOR)) {', '        if (false) {'),
]


def main():
    if len(sys.argv) != 2:
        sys.exit('usage: tests/hw/i219_mutants.py OUT')
    out = pathlib.Path(sys.argv[1]).resolve()
    if out.exists():
        sys.exit('OUT exists: %s' % out)
    caught = 0
    for n, (name, text, repl) in enumerate(MUTANTS):
        root = out / ('m%02d' % n)
        shutil.copytree(TREE / 'src', root / 'src', ignore=shutil.ignore_patterns('*.c', '*.h'))
        shutil.copytree(TREE / 'tests' / 'hw', root / 'tests' / 'hw', ignore=shutil.ignore_patterns('*.py'))
        shutil.copytree(TREE / 'tests' / 'hosted', root / 'tests' / 'hosted')
        f = root / 'src' / 'e1000.ci'
        body = f.read_text()
        if body.count(text) != 1:
            sys.exit('mutant %r: its text occurs %d times in src/e1000.ci' % (name, body.count(text)))
        f.write_text(body.replace(text, repl))
        r = subprocess.run(['bash', str(TREE / 'tests' / 'hw' / 'run-hosted.sh'), str(out / ('b%02d' % n)), str(root)],
                           capture_output=True, text=True)
        (out / ('m%02d.log' % n)).write_text(r.stdout + r.stderr)
        last = (r.stdout.strip().splitlines() or [''])[-1]
        if r.returncode != 0 and 'tests passed' in last:
            verdict = 'CAUGHT'
            caught += 1
        elif r.returncode == 0:
            verdict = 'MISSED'
        else:
            verdict = 'BROKEN'
        print('%-7s %s (%s)' % (verdict, name, last or 'no result line'))
    print('%d of %d mutants caught' % (caught, len(MUTANTS)))
    return 0 if caught == len(MUTANTS) else 1


if __name__ == '__main__':
    sys.exit(main())
# SPDX-License-Identifier: Apache-2.0
