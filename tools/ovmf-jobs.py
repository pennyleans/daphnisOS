#!/usr/bin/env python3
"""Own one process group per OVMF case, including its QEMU, feeder and input typer."""
import os
import signal
import subprocess
import sys
import time


def run(commands):
    children = []
    stopped = 0

    def stop(signum, _frame):
        nonlocal stopped
        stopped = signum

    old = {sig: signal.signal(sig, stop) for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        for command in commands:
            if stopped:
                break
            children.append(subprocess.Popen(command, start_new_session=True))
        while not stopped and any(p.poll() is None for p in children):
            time.sleep(0.05)
        return 128 + stopped if stopped else int(any(p.returncode != 0 for p in children))
    finally:
        # A shell exiting does not prove its children exited. Clean every owned group, even
        # when its direct child finished, without names, recursive PID discovery or pkill.
        groups = [p.pid for p in children]
        for pg in groups:
            try:
                os.killpg(pg, signal.SIGTERM)
            except ProcessLookupError:
                pass
        deadline = time.monotonic() + 5
        while groups and time.monotonic() < deadline:
            alive = []
            for pg in groups:
                try:
                    os.killpg(pg, 0)
                    alive.append(pg)
                except ProcessLookupError:
                    pass
            groups = alive
            if groups:
                time.sleep(0.05)
        for pg in groups:
            try:
                os.killpg(pg, signal.SIGKILL)
            except ProcessLookupError:
                pass
        for p in children:
            p.wait()
        for sig, handler in old.items():
            signal.signal(sig, handler)


def main():
    b = sys.argv[1]
    cases = [(cc, fl, kind, "128") for cc in ("gcc", "clang")
             for fl in ("hello", "user") for kind in ("iso", "esp")]
    cases += [(cc, "user", kind, "2048") for cc in ("gcc", "clang") for kind in ("iso", "esp")]
    return run([["bash", "tools/check-ovmf.sh", b, "--case", *case] for case in cases])


if __name__ == "__main__":
    sys.exit(main())
