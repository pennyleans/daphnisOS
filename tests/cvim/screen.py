"""CV-3 frame checks (docs/specs/2026-11-07-cv-cvim.md section 14: frame digests).

Each case types a key script into cvim on a screen of rows x cols. After every key the replay composes the grid
(view.ci) and writes the frame term.ci makes of it: the first frame full, every later one only the cells that changed.
Three checks per case:
  1. the frames, played in order through a small terminal model (CUP, ED 2, SGR, DECTCEM, DECSCUSR, UTF-8, the
     model ignores nothing else), leave exactly the last grid on the screen, roles and cursor included;
  2. no later frame is longer than a full frame of the same grid;
  3. the SHA-256 of all frame bytes, and of the last grid, equal the frozen ones in screen_golden.json.

    python3 tests/cvim/screen.py --out DIR [--cc clang]
    python3 tests/cvim/screen.py --freeze --out DIR      record digests after reviewing the printed screens

There is no Vim oracle for frames: --freeze records cvim's own output, to be read before it is committed.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import keys
from screen_cases import CASES

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
GOLDEN = HERE / 'screen_golden.json'
ROLE = 2097152


def role_table():
    """Role to SGR parameters, read from term.ci's sgr() so the two never drift; roles it does not name are plain."""
    src = (ROOT / 'user/ci/cvim/term.ci').read_text()
    names = {m[1]: int(m[2]) for m in re.finditer(r'export const I64 (\w+) = (\d+);',
                                                 (ROOT / 'user/ci/cvim/view.ci').read_text())}
    table = {}
    body = src[src.index('export void sgr('):src.index('// One frame of g')]
    for line in body.splitlines():
        found = re.findall(r'view\.(R_\w+)', line)
        m = re.search(r'b"\\x1b\[([0-9;]*)m"', line)
        if m:
            for name in found:
                table[names[name]] = m[1]
            if not found:
                plain = m[1]
    # DN-45: line numbers and the selection come from theme.ci's mark(), as term.ci draws them
    theme = (ROOT / 'user/ci/cvim/theme.ci').read_text()
    theme = theme[theme.index('export I64 mark('):theme.index('export I64 mono(')]   # the color forms only
    marks = {m[1]: m[2] for m in re.finditer(r'if \(m == (MARK_\w+)\) \{ return put\(o, b"([0-9;]*)"\); \}', theme)}
    table[names['R_GUTTER']] = '0' + marks['MARK_LINE_NUMBER']
    table[names['R_SELECTION']] = '0' + marks['MARK_SELECTION']
    return {r: table.get(r, plain) for r in range(names['ROLES'] if 'ROLES' in names else 64)}


class Screen:
    """A terminal model: a grid of (code point, SGR parameters), a cursor, its visibility and form."""

    def __init__(self, rows, cols):
        self.rows, self.cols = rows, cols
        self.cells = [[(' ', '0')] * cols for _ in range(rows)]
        self.row = self.col = 0
        self.sgr = '0'
        self.visible = True
        self.form = 0

    def feed(self, data):
        i = 0
        while i < len(data):
            b = data[i]
            if b == 0x1b:
                m = re.compile(rb'\x1b\[(\??)([0-9;]*)( ?)([A-Za-z])').match(data, i)
                if not m:
                    raise AssertionError('unknown escape at %d: %r' % (i, data[i:i + 12]))
                private, params, space, final = m[1], m[2].decode(), m[3], m[4]
                if final == b'H':
                    r, c = (params.split(';') + ['1', '1'])[:2]
                    self.row, self.col = int(r or 1) - 1, int(c or 1) - 1
                elif final == b'J' and params == '2':
                    self.cells = [[(' ', self.sgr)] * self.cols for _ in range(self.rows)]
                elif final == b'm':
                    self.sgr = params or '0'
                elif private == b'?' and params == '25' and final in (b'l', b'h'):
                    self.visible = final == b'h'
                elif space == b' ' and final == b'q':
                    self.form = int(params)
                else:
                    raise AssertionError('unhandled sequence %r' % m[0])
                i = m.end()
                continue
            n = 1 if b < 0x80 else 2 if b < 0xe0 else 3 if b < 0xf0 else 4
            ch = data[i:i + n].decode('utf-8')
            assert 0 <= self.row < self.rows and 0 <= self.col < self.cols, 'a write outside the screen'
            self.cells[self.row][self.col] = (ch, self.sgr)
            self.col += 1
            i += n


def pack(cases):
    out = bytearray(struct.pack('<q', len(cases)))
    for c in cases:
        name = c['name'].encode()
        t = c['text'].encode()
        kk = keys.codes(c['keys'])
        out += struct.pack('<qqq', c['rows'], c['cols'], len(name)) + name
        out += struct.pack('<qq', len(t), len(kk)) + t + struct.pack('<' + 'q' * len(kk), *kk)
    return bytes(out)


def build(outdir, cc):
    cmd = [shutil.which('cint'), 'build', '--root', '.', '--out', str(outdir), '--frame-arena', '67108864']
    if os.environ.get('CINT_CACHE'):
        cmd += ['--cache', os.environ['CINT_CACHE']]
    toolchain = os.environ.get('CINT_TOOLCHAIN')
    if cc:
        path = shutil.which(cc)
        version = subprocess.check_output([path, '-dumpversion'], text=True).strip()
        rows = Path(toolchain).read_text().splitlines()
        rows = [('cc ' + path if r.startswith('cc ') else 'cc_version ' + version if r.startswith('cc_version ')
                 else 'leg ' + cc if r.startswith('leg ') else r) for r in rows]
        alt = outdir / 'host.toolchain'
        alt.write_text('\n'.join(rows) + '\n')
        toolchain = str(alt)
    if toolchain:
        cmd += ['--toolchain', toolchain]
    b = subprocess.run(cmd + ['tests/cvim/screen.ci'], cwd=ROOT, capture_output=True)
    if b.returncode:
        raise RuntimeError((b.stdout + b.stderr).decode())


def run(cases, outdir, cc=None):
    outdir.mkdir(parents=True, exist_ok=True)
    build(outdir, cc)
    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, 'all').write_bytes(pack(cases))
        p = subprocess.run([str(outdir / 'screen'), '--grant', 'fs.read:/case=' + tmp], capture_output=True, timeout=60)
    if p.returncode:
        raise RuntimeError(p.stderr.decode() + p.stdout[-2000:].decode(errors='replace'))
    out = p.stdout
    pos = 0
    results = []
    for c in cases:
        end = out.index(b'\n', pos)
        head = out[pos:end].split()
        assert head[0] == b'case', head
        pos = end + 1
        frames = []
        while out[pos:pos + 2] == b'F ':
            end = out.index(b'\n', pos)
            n = int(out[pos + 2:end])
            pos = end + 1
            frames.append(out[pos:pos + n])
            pos += n
        assert out[pos:pos + 2] == b'G\n'
        pos += 2
        grid = []
        for row in range(c['rows']):
            end = out.index(b'\n', pos)
            grid.append([int(v) for v in out[pos:end].split()])
            pos = end + 1
        results.append((frames, grid))
    assert pos == len(out)
    return results


def text_of(grid):
    return '\n'.join(''.join(chr(v % ROLE) for v in row).rstrip() for row in grid)


def check(case, frames, grid, table):
    """The terminal-model checks; a list of problems."""
    bad = []
    s = Screen(case['rows'], case['cols'])
    for f in frames:
        s.feed(f)
        if not s.visible:
            bad.append('a frame leaves the cursor hidden')
    for r in range(case['rows']):
        for c in range(case['cols']):
            ch, sgr = s.cells[r][c]
            want = grid[r][c]
            if ch != chr(want % ROLE) or table.get(want // ROLE) != sgr:
                bad.append('cell %d,%d: screen %r %s, grid %r role %d' % (r, c, ch, sgr, chr(want % ROLE), want // ROLE))
                break
    full = len(frames[0])
    for k, f in enumerate(frames[1:]):
        if len(f) > full + 64:
            bad.append('frame %d is %d bytes, more than a full frame (%d)' % (k + 1, len(f), full))
    return bad, s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--cc', choices=['gcc', 'clang'])
    ap.add_argument('--freeze', action='store_true')
    args = ap.parse_args()
    table = role_table()
    got = run(CASES, args.out, args.cc)
    frozen = json.loads(GOLDEN.read_text()) if GOLDEN.exists() and not args.freeze else {}
    records = {}
    failures = 0
    groups = {}
    for case, (frames, grid) in zip(CASES, got):
        bad, screen = check(case, frames, grid, table)
        rec = dict(frames=hashlib.sha256(b''.join(frames)).hexdigest(),
                   grid=hashlib.sha256(json.dumps(grid).encode()).hexdigest(),
                   bytes=[len(f) for f in frames], cursor=[screen.row, screen.col], form=screen.form,
                   screen=text_of(grid).split('\n'))
        records[case['id']] = rec
        if not args.freeze and frozen.get(case['id']) != rec:
            bad.append('differs from screen_golden.json')
            if case['id'] in frozen:
                old = frozen[case['id']]
                for k in rec:
                    if rec[k] != old.get(k):
                        bad.append('  %s: frozen %r, got %r' % (k, old.get(k), rec[k]))
        for b in bad:
            print('DIFF', case['id'], b)
        groups.setdefault(case['group'], []).append(not bad)
        failures += bool(bad)
    if args.freeze:
        for case in CASES:
            print('==', case['id'], case['rows'], 'x', case['cols'], repr(case['keys']))
            print('\n'.join(records[case['id']]['screen']))
        GOLDEN.write_text(json.dumps(records, ensure_ascii=False, indent=1, sort_keys=True) + '\n')
        print('froze', len(records), 'screen records')
        return 0
    for group, oks in groups.items():
        print(('PASS' if all(oks) else 'FAIL') + '  cvim screen ' + group + ': ' + str(len(oks)) + ' cases')
    total = sum(len(v) for v in groups.values())
    print('cvim screen:', total - failures, 'of', total, 'pass')
    return bool(failures)


if __name__ == '__main__':
    sys.exit(main())
