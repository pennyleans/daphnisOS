#!/usr/bin/env python3
"""HW-1 ruling A: retain the firmware prefix; compare every kernel byte unchanged."""
import pathlib
import sys


def split(raw, golden):
    if not golden:
        raise ValueError("empty golden")
    mark = golden.partition(b"\n")[0] + b"\n"
    at = raw.find(mark)
    if at < 0:
        raise ValueError("kernel's first line not found")
    return raw[:at], raw[at:]


def main():
    transcript, golden = map(pathlib.Path, sys.argv[1:])
    try:
        prefix, kernel = split(transcript.read_bytes(), golden.read_bytes())
    except ValueError as e:
        print(f"fw-split: {e}", file=sys.stderr)
        return 1
    pathlib.Path(str(transcript) + ".firmware").write_bytes(prefix)
    pathlib.Path(str(transcript) + ".kernel").write_bytes(kernel)
    return 0


if __name__ == "__main__":
    sys.exit(main())
