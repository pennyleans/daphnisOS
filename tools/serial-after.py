#!/usr/bin/env python3
"""Run QEMU, feeding serial input only after its transcript contains the kernel marker.

Called inside run-qemu.sh's watchdog, with stdout/stderr already redirected. The complete
transcript is retained. No bytes are filtered here. Firmware cannot consume the gate input.
"""
import pathlib
import signal
import subprocess
import sys
import time


def main():
    mark, source, transcript = sys.argv[1:4]
    stopped = 0
    starting = True
    def stop(signum, _frame):
        nonlocal stopped
        stopped = signum
        # Interrupt a blocked pipe write too; cleanup remains in ordinary control flow.
        if not starting:
            raise InterruptedError("serial input cancelled")
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    q = None
    sent = False
    try:
        q = subprocess.Popen(sys.argv[4:], stdin=subprocess.PIPE)
        starting = False
        if stopped:
            raise InterruptedError("serial input cancelled during startup")
        while q.poll() is None:
            if mark.encode() in pathlib.Path(transcript).read_bytes():
                q.stdin.write(pathlib.Path(source).read_bytes())
                q.stdin.close()
                sent = True
                break
            time.sleep(0.02)
        rc = q.wait()
        if not sent:
            print("serial-after: QEMU exited before the kernel marker", file=sys.stderr)
        return rc if sent else 1
    except (BrokenPipeError, InterruptedError, OSError) as e:
        print(f"serial-after: {e}", file=sys.stderr)
        return 128 + stopped if stopped else 1
    finally:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        if q is not None and q.poll() is None:
            q.terminate()
            try:
                q.wait(timeout=3)
            except subprocess.TimeoutExpired:
                q.kill()
                q.wait()
        if q is not None:
            try:
                q.stdin.close()
            except (BrokenPipeError, OSError):
                pass


if __name__ == "__main__":
    sys.exit(main())
