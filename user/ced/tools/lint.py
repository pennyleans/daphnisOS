"""tools/lint.py: ced's lint (SPEC.md BLD-4, BLD-6). python tools/lint.py"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP = {".git", "history"}
MAX_COMMENT = 48
MAX_PER_FILE = 8


def files():
    return [p for p in sorted(ROOT.rglob("*")) if p.is_file() and not SKIP & set(p.relative_to(ROOT).parts)]


def split(line):
    q = None
    i = 0
    while i < len(line):
        c = line[i]
        if q:
            i += c == "\\"
            q = None if c == q else q
        elif c in "\"'":
            q = c
        elif line.startswith("//", i):
            return line[:i], line[i + 2:].strip()
        i += 1
    return line, None


def main():
    bad = []
    for p in files():
        rel = p.relative_to(ROOT).as_posix()
        if p.suffix in (".c", ".h", ".sh", ".bash"):
            bad.append(f"BLD-4 {rel}: no C or shell files")
        data = p.read_bytes()
        if b"\r" in data:
            bad.append(f"BLD-4 {rel}: CR byte")
        if p.suffix != ".ci":
            continue
        n = 0
        for no, line in enumerate(data.decode("utf-8").split("\n"), 1):
            code, com = split(line)
            if re.search(r"\b\d+\.\d+\b", code):
                bad.append(f"BLD-4 {rel}:{no}: floating literal")
            if com is None:
                continue
            n += 1
            if com != com.lower():
                bad.append(f"BLD-6 {rel}:{no}: comment is not lowercase")
            if len(com) > MAX_COMMENT:
                bad.append(f"BLD-6 {rel}:{no}: comment over {MAX_COMMENT} characters")
        if n > MAX_PER_FILE:
            bad.append(f"BLD-6 {rel}: {n} comments, at most {MAX_PER_FILE}")
    for b in bad:
        print("FAIL " + b)
    print(f"lint: {'ok' if not bad else str(len(bad)) + ' findings'}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
