"""tests/cvim/hl_gate.py [--corpus DIR] [--out DIR]: CV-6's gate (docs/specs/2026-11-07-cv-cvim.md section 7). Every
.ci file of cint's conformance corpus (by default the pinned public cint's, ~/cint-work/cint-pub-0218/conformance)
that the vendored scan.ci (user/cvim/scan/, cint v0.2.18) accepts must lex the same in user/ci/cvim/hl.ci: the same
tokens, kind, start and length, in order (comments aside). scan.ci imports `limits` from its own root, so the gate
builds in a root of its own: the two vendored files, hl.ci and tests/cvim/hl_gate.ci. Prints PASS or FAIL with the
counts, and the lexing time of hl.ci over the accepted files. Status 1 on a FAIL.
"""
import argparse
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

GATE_TOKENS = b'''
// tests/cvim/hl_gate.py's: src's tokens (kind, start, length) into dst through scan.ci's own next_token, the final
// EOF left out; -1 when a token is an error (a diagnostics table of limits' struct cannot be made outside limits.ci
// yet, C9102, so scan() itself is not called; check_text's refusals are left to the harness, which skips such files).
export I64 gate_tokens[n](in U8[n] src, inout I64[_] dst) {
    Token[1] tk;
    Lex[1] lx;
    lx[0].i = 0;
    lx[0].end = n;
    lx[0].line = 1;
    lx[0].col = 1;
    I64 k = 0;
    while (true) {
        I64 e = next_token(src, lx, tk, 0);
        if (e != 0) {
            return -1;
        }
        if (tk[0].kind == TK_EOF) {
            return k;
        }
        if (3 * k + 2 >= len(dst)) {
            return -1;
        }
        dst[3 * k] = tk[0].kind as I64;
        dst[3 * k + 1] = tk[0].start as I64;
        dst[3 * k + 2] = tk[0].len as I64;
        k += 1;
    }
    return k;
}
'''


def text_ok(data):
    """scan.ci's check_text in short: UTF-8 with no BOM, no NUL or other control byte but tab and line feed, and a
    CR only before a line feed."""
    if data.startswith(b'\xef\xbb\xbf'):
        return False
    try:
        data.decode('utf-8')
    except UnicodeDecodeError:
        return False
    for i, b in enumerate(data):
        if b == 13 and data[i + 1:i + 2] != b'\n':
            return False
        if (b < 32 and b not in (9, 10, 13)) or b == 127:
            return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--corpus', type=Path, default=Path.home() / 'cint-work/cint-pub-0218/conformance')
    ap.add_argument('--out', type=Path, default=Path(os.environ.get('CINT_BUILD', '/tmp/cint-build')) / 'cvim-hl')
    args = ap.parse_args()
    files = sorted(p for p in args.corpus.rglob('*.ci'))
    if not files:
        sys.exit('hl_gate: no .ci files under ' + str(args.corpus))
    args.out.mkdir(parents=True, exist_ok=True)
    refused_text = []
    with tempfile.TemporaryDirectory(dir=args.out) as tmp:
        tmp = str(Path(tmp).resolve())       # cint's reader refuses a path through a link (/var, /tmp on macOS)
        root = Path(tmp) / 'root'
        (root / 'user/ci/cvim').mkdir(parents=True)
        # the gate's copy of scan.ci gains one function at its end, its tokens as integers (a struct array cannot be
        # declared in another module yet, C9102); the vendored file itself stays byte for byte
        (root / 'scan.ci').write_bytes((ROOT / 'user/cvim/scan/scan.ci').read_bytes() + GATE_TOKENS)
        shutil.copy(ROOT / 'user/cvim/scan/limits.ci', root / 'limits.ci')
        shutil.copy(ROOT / 'user/ci/cvim/hl.ci', root / 'user/ci/cvim/hl.ci')
        shutil.copy(ROOT / 'tests/cvim/hl_gate.ci', root / 'hl_gate.ci')
        cmd = [shutil.which('cint') or 'cint', 'build', '--root', str(root), '--out', str(args.out),
               '--frame-arena', '134217728']
        if os.environ.get('CINT_CACHE'):
            cmd += ['--cache', os.environ['CINT_CACHE']]
        if os.environ.get('CINT_TOOLCHAIN'):
            cmd += ['--toolchain', os.environ['CINT_TOOLCHAIN']]
        b = subprocess.run(cmd + ['hl_gate.ci'], cwd=root, capture_output=True)
        if b.returncode:
            sys.exit((b.stdout + b.stderr).decode())
        packed = bytearray(struct.pack('<q', len(files)))
        for f in files:
            data = f.read_bytes()
            if not text_ok(data):
                data = b''            # check_text would refuse it (C1002 to C1004): an empty file, counted apart
                refused_text.append(f)
            packed += struct.pack('<q', len(data)) + data
        case = Path(tmp) / 'case'
        case.mkdir()
        (case / 'all').write_bytes(packed)
        t0 = time.monotonic()
        p = subprocess.run([str(args.out / 'hl_gate'), '--grant', 'fs.read:/case=' + str(case)], capture_output=True,
                           timeout=600)
        took = time.monotonic() - t0
    if p.returncode:
        sys.exit(p.stderr.decode() + p.stdout.decode(errors='replace'))
    ok = skip = 0
    bad = []
    for line in p.stdout.decode().splitlines():
        w = line.split()
        if len(w) < 3 or w[0] != 'F':
            continue
        if w[2] == 'ok' and files[int(w[1])] in refused_text:
            skip += 1
        elif w[2] == 'ok':
            ok += 1
        elif w[2] == 'skip':
            skip += 1
        else:
            bad.append((files[int(w[1])].relative_to(args.corpus), ' '.join(w[3:])))
    for f, why in bad[:20]:
        print('DIFF', f, why)
    total = sum(f.stat().st_size for f in files)
    print(('FAIL' if bad else 'PASS') + '  cvim hl gate: %d files scan.ci accepts lex the same, %d differ, %d refused '
          'by scan.ci (of %d; %.1f s for %d KiB, scan.ci and hl.ci both)' % (ok, len(bad), skip, len(files), took,
                                                                           total // 1024))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
