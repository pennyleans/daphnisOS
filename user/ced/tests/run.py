"""tests/run.py: ced's checks (SPEC.md TEST-1).

    python tests/run.py [--quick]

Runs `cint test` over the modules (skipped with --quick), builds tests/replay.ci, replays every
golden of tests/golden/ through the core (TEST-2) and prints `ced: N of N pass`. The cint on
PATH is used; build outputs go under CINT_BUILD.
"""

import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = ROOT / "tests" / "golden"


def build_dir():
    base = os.environ.get("CINT_BUILD") or os.path.join(tempfile.gettempdir(), "cint-build")
    return Path(base) / "ced-tests"


def cint():
    path = shutil.which("cint")
    if path is None:
        sys.exit("ced: cint is not on PATH")
    return path


def unit_tests():
    """`cint test` over every module; returns (passed, total, output)."""
    run = subprocess.run([cint(), "test", "ced.ci"], cwd=ROOT,
                         capture_output=True, text=True)
    out = run.stdout + run.stderr
    lines = [line for line in out.splitlines() if line.startswith("test ")]
    passed = sum(1 for line in lines if line.endswith(" ok"))
    if run.returncode != 0 and passed == len(lines):
        return passed, len(lines) + 1, out
    return passed, len(lines), out


def pack(cases):
    """The case file of tests/replay.ci: little-endian 8-byte numbers and bytes."""
    out = bytearray(struct.pack("<q", len(cases)))
    for case in cases:
        text = case["text"].encode("utf-8") * case.get("repeat", 1)
        chunks = [bytes.fromhex(c) for c in case["chunks"]]
        rows, cols = case["size"]
        anchor, head = case.get("sel", [0, 0])
        new = 2 if case.get("untitled") else 1 if case.get("new") else 0
        on_desk = 1 if case.get("desk") else 0
        out += struct.pack("<8q", rows, cols, anchor, head, new, on_desk, len(text), len(chunks))
        for c in chunks:
            out += struct.pack("<q", len(c))
        out += text
        for c in chunks:
            out += c
    return bytes(out)


def parse(out, cases):
    """Splits replay's output into one result per case."""
    results = []
    p = 0
    for i, case in enumerate(cases):
        eol = out.index(b"\n", p)
        words = out[p:eol].decode("ascii").split()
        p = eol + 1
        if words[2] == "refused":
            results.append({"refused": int(words[3])})
            continue
        n, anchor, head, rows = (int(w) for w in words[2:6])
        text = out[p:p + n]
        p += n + 1
        screen = []
        for _ in range(rows):
            eol = out.index(b"\n", p)
            screen.append(out[p:eol].decode("utf-8").rstrip(" "))
            p = eol + 1
        results.append({"text": text.decode("utf-8"), "sel": [anchor, head], "screen": screen})
    return results


def check(case, got):
    """The differences between a golden's expectations and the replay, as lines."""
    want = case["expect"]
    diffs = []
    if "refused" in want or "refused" in got:
        if want.get("refused") != got.get("refused"):
            diffs.append(f"refused: want {want.get('refused')}, got {got.get('refused')}")
        return diffs
    if got["text"] != want["text"]:
        diffs.append(f"text: want {want['text']!r}, got {got['text']!r}")
    if "sel" in want and got["sel"] != want["sel"]:
        diffs.append(f"sel: want {want['sel']}, got {got['sel']}")
    if "screen" in want:
        rows = max(len(want["screen"]), len(got["screen"]))
        for row in range(rows):
            w = want["screen"][row].rstrip(" ") if row < len(want["screen"]) else None
            g = got["screen"][row] if row < len(got["screen"]) else None
            if w != g:
                diffs.append(f"screen row {row}: want {w!r}, got {g!r}")
    return diffs


def replay(cases):
    out_dir = build_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    build = subprocess.run([cint(), "build", "--root", ".", "--out", str(out_dir),
                            "tests/replay.ci"], cwd=ROOT, capture_output=True, text=True)
    if build.returncode != 0:
        sys.exit("ced: tests/replay.ci does not build\n" + build.stdout + build.stderr)
    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, "all").write_bytes(pack(cases))
        run = subprocess.run([str(out_dir / "replay"), "--grant", f"fs.read:/case={tmp}"],
                             capture_output=True)
    if run.returncode != 0:
        sys.exit("ced: replay failed\n" + run.stderr.decode("utf-8", "replace"))
    return parse(run.stdout, cases)


def lint():
    run = subprocess.run([sys.executable, str(ROOT / "tools" / "lint.py")], capture_output=True, text=True)
    print(run.stdout.strip())
    return run.returncode == 0


def version_text():
    """RUN-6: the version ced.ci names in its About is VERSION's."""
    import re
    src = (ROOT / "ced.ci").read_text(encoding="utf-8")
    m = re.search(r"VERSION_TEXT = \[([0-9, ]+)\]", src)
    got = bytes(int(v) for v in m.group(1).split(",")).decode() if m else None
    want = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    ok = got == want
    print(f"{'ok  ' if ok else 'FAIL'} about-version (RUN-6)" + ("" if ok else f": {got!r}, VERSION {want!r}"))
    return int(ok)


def main():
    quick = "--quick" in sys.argv[1:]
    passed = total = 0
    passed += lint()
    total += 1
    passed += version_text()
    total += 1
    if not quick:
        p, t, out = unit_tests()
        if p != t:
            print(out)
        print(f"unit tests: {p} of {t} pass")
        passed += p
        total += t
    files = sorted(GOLDEN.glob("*.json"))
    cases = [json.loads(f.read_text(encoding="utf-8")) for f in files]
    for case, got in zip(cases, replay(cases)):
        diffs = check(case, got)
        rules = " ".join(case["rules"])
        print(f"{'ok  ' if not diffs else 'FAIL'} {case['id']} ({rules})")
        for d in diffs:
            print(f"     {d}")
        passed += not diffs
        total += 1
    print(f"ced: {passed} of {total} pass")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
