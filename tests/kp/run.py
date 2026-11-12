#!/usr/bin/env python3
"""tests/kp/run.py --inc DIR --out DIR [--cc CC ...]: KP-1, tools/check-state-pool.py against images made here.

Each case is a C file with a `state_pool` and module state records written as cint emits them (`cint_state` of the
pinned cint_rt.h under --inc, `bytes` from sizeof), compiled to an object by each compiler. So the offsets the
check reads are tied to the header the kernel is built against: a `cint_state` whose layout moves fails here.
Every case must give its exit status and its words; a case that cannot be built fails the run.
"""
import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CHECK = os.path.join(HERE, "..", "..", "tools", "check-state-pool.py")

HEAD = '#include "cint_rt.h"\n'
POOL = '__attribute__((aligned(16))) unsigned char state_pool[%du] = {1};\n'
# one module's state as the emitted C writes it: a struct, its image, its record
MODULE = ('typedef struct { unsigned char b[%(n)du]; } %(s)s_state;\n'
          'const %(s)s_state %(s)s_state_init = {{0}};\n'
          'const cint_state %(s)s_state_desc = {%(i)du, 0u, (uint32_t)sizeof(%(s)s_state), 0u, '
          '&%(s)s_state_init, 0};\n')


def source(pool, sizes):
    text = HEAD
    if pool is not None:
        text += POOL % pool
    names = ["cg_9_src_x2Ffs", "cg_11_src_x2Fproc", "cg_14_src_x2Fkey_x5Frep"]
    for i, n in enumerate(sizes):
        text += MODULE % {"n": n, "s": names[i], "i": i}
    return text


# name, pool bytes (None: no pool), each module's state bytes, exit status, words the output must hold
CASES = [
    ("fits", 4096, [100, 2000], 0, ["2 modules need 2112 of 4096 bytes, 1984 free"]),
    ("fits exactly", 2112, [100, 2000], 0, ["need 2112 of 2112 bytes, 0 free"]),
    ("one block over", 2096, [100, 2000], 1, ["need 2112 bytes, the pool is 2096: 16 bytes over", "2000  src/proc",
                                              "112  src/fs"]),
    ("a byte takes a block", 32, [1, 1, 1], 1, ["3 modules need 48 bytes, the pool is 32", "src/key_rep"]),
    ("a byte takes a block, fits", 48, [1, 1, 1], 0, ["need 48 of 48 bytes"]),
    ("no modules", 16, [], 0, ["0 modules need 0 of 16 bytes"]),
    ("no pool", None, [100], 2, ["cannot check: no object named state_pool"]),
]


def run(args):
    return subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inc", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--cc", action="append")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    bad = 0
    ran = 0
    for cc in a.cc or ["gcc", "clang"]:
        made = []
        for k, (name, pool, sizes, want, words) in enumerate(CASES):
            c = os.path.join(a.out, f"{cc}-{k}.c")
            o = os.path.join(a.out, f"{cc}-{k}.o")
            with open(c, "w") as f:
                f.write(source(pool, sizes))
            r = run([cc, "-std=c17", "-Wall", "-Wextra", "-Werror", "-I", a.inc, "-c", c, "-o", o])
            if r.returncode != 0:
                print(f"FAIL {cc} {name}: does not compile\n{r.stdout}")
                bad += 1
                continue
            made.append(o)
            r = run([sys.executable, "-B", CHECK, o])
            ran += 1
            if r.returncode != want or any(w not in r.stdout for w in words):
                print(f"FAIL {cc} {name}: exit {r.returncode}, want {want} and {words}\n{r.stdout}")
                bad += 1
        # a stripped image has no symbol table: the check must say so, never pass it
        if made:
            s = os.path.join(a.out, f"{cc}-stripped.o")
            r = run(["objcopy", "--strip-all", made[0], s])
            r = run([sys.executable, "-B", CHECK, s])
            ran += 1
            if r.returncode != 2 or "no symbol table" not in r.stdout:
                print(f"FAIL {cc} stripped: exit {r.returncode}, want 2\n{r.stdout}")
                bad += 1
        # several images: the worst status wins, and every image gets its line
        if len(made) >= 3:
            r = run([sys.executable, "-B", CHECK, made[0], made[2], CHECK])
            ran += 1
            if r.returncode != 2 or r.stdout.count("state pool: ") < 3 or "16 bytes over" not in r.stdout:
                print(f"FAIL {cc} several: exit {r.returncode}, want 2\n{r.stdout}")
                bad += 1
            r = run([sys.executable, "-B", CHECK, made[0], made[2]])
            ran += 1
            if r.returncode != 1:
                print(f"FAIL {cc} two: exit {r.returncode}, want 1\n{r.stdout}")
                bad += 1
    want_ran = len(a.cc or ["gcc", "clang"]) * (len(CASES) + 3)
    if ran != want_ran:
        print(f"FAIL ran {ran} checks, want {want_ran}")
        bad += 1
    print(f"{ran} checks, {bad} failed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
