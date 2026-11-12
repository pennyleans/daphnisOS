"""tests/cvim/hl_proof.py OUT.png: CV-6's proof, cvim on tests/cvim/hl_sample.txt (as sample.ci) at 80 x 24: the
frame's bytes from tests/cvim/hl_proof.ci, drawn by the terminal's twin (tools/check-tiler.py: vt and term_pixels,
user/ci/terms.ci's cells in the dark theme's eight ANSI colors). Under K-DT a terminal is dark in both themes, so
the Warm Paper desk draws the same pixels: the sheet has both, left Gruvbox Nocturne, right Warm Paper.
"""
import importlib.util
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


def tiler():
    spec = importlib.util.spec_from_file_location('ct', ROOT / 'tools/check-tiler.py')
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def png(path, w, h, rows):
    raw = b''.join(b'\x00' + b''.join(struct.pack('>BBB', (p >> 16) & 255, (p >> 8) & 255, p & 255) for p in r)
                   for r in rows)
    chunk = lambda t, d: struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    Path(path).write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)) +
                           chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))


def main(out):
    build = Path(os.environ.get('CINT_BUILD', '/tmp/cint-build')) / 'cvim-hl-proof'
    build.mkdir(parents=True, exist_ok=True)
    cmd = [shutil.which('cint') or 'cint', 'build', '--root', '.', '--out', str(build), '--frame-arena', '33554432']
    if os.environ.get('CINT_CACHE'):
        cmd += ['--cache', os.environ['CINT_CACHE']]
    if os.environ.get('CINT_TOOLCHAIN'):
        cmd += ['--toolchain', os.environ['CINT_TOOLCHAIN']]
    b = subprocess.run(cmd + ['tests/cvim/hl_proof.ci'], cwd=ROOT, capture_output=True)
    if b.returncode:
        sys.exit((b.stdout + b.stderr).decode())
    with tempfile.TemporaryDirectory(dir=build) as tmp:
        (Path(tmp) / 'sample').write_bytes((ROOT / 'tests/cvim/hl_sample.txt').read_bytes())
        p = subprocess.run([str(build / 'hl_proof'), '--grant', 'fs.read:/case=' + str(Path(tmp).resolve())],
                           capture_output=True)
    if p.returncode:
        sys.exit(p.stderr.decode())
    ct = tiler()
    sheet = []
    panels = []
    for theme in (0, 1):
        ct.use_theme(theme)
        grid, cx, cy, shown = ct.vt(p.stdout, 80, 24)
        panels.append(ct.term_pixels(grid, 80, 24, cx, cy, shown, 2))
    gap = [0x808080] * 16
    for a, b in zip(*panels):
        sheet.append(list(a) + gap + list(b))
    png(out, len(sheet[0]), len(sheet), sheet)
    print('hl proof:', out, len(sheet[0]), 'x', len(sheet))


if __name__ == '__main__':
    main(sys.argv[1])
