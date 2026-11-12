#!/usr/bin/env python3
"""tools/check-state-pool.py KERNEL.elf [...]: KP-1, the module state of a kernel image against its state pool.

The kernel's context gives each module with module-level variables one block, cut from `state_pool` (rt/ctx.c) at
the module's first access and never given back. A block is the module's `bytes` rounded up to 16. When the blocks
of an image do not fit, the access that asks for the block past the end faults at boot. This check reads both
numbers from the linked image itself and fails the build instead:

  need   every `*_state_desc` record's `bytes` (cint_rt.h `cint_state`, the u32 at byte 8), each rounded up to 16
  pool   the size of the object `state_pool`

`need <= pool` passes. The sum is over every module that has a state, so it is the most the kernel's context can
ask for; an image that passes cannot run out, whichever modules it reaches. A task's own pool (rt/task.c
`TASK_POOL`) is not checked here: what a task asks for depends on the modules its code reaches.

Exit status: 0 every image fits; 1 an image does not fit; 2 a file is not a kernel image this check can read (no
symbol table, no `state_pool`, a record outside its section). On stdout, one line an image, then each of its
modules with its block, the largest first: a pull request that adds kernel state quotes the lines it moves.
"""
import re
import struct
import sys

DESC_BYTES = 32      # sizeof(cint_state)
BYTES_AT = 8         # cint_state.bytes
BLOCK = 16           # cint_rt_state_slow rounds a block up to this


class Unreadable(Exception):
    pass


def module_name(symbol):
    """`cg_10_src_x2Fblk_state_desc` -> `src/blk`."""
    m = re.fullmatch(r"cg_\d+_(.*)_state_desc", symbol)
    if m is None:
        return symbol
    return re.sub(r"_x([0-9A-F]{2})", lambda h: chr(int(h.group(1), 16)), m.group(1))


def read(path):
    """(pool bytes, {module: state bytes}) of the ELF64 little-endian image at path."""
    with open(path, "rb") as f:
        data = f.read()
    if len(data) < 64 or data[:6] != b"\x7fELF\x02\x01":
        raise Unreadable("not an ELF64 little-endian file")
    shoff, = struct.unpack_from("<Q", data, 0x28)
    shentsize, shnum = struct.unpack_from("<HH", data, 0x3A)
    if shentsize != 64 or shoff + 64 * shnum > len(data):
        raise Unreadable("section headers out of the file")
    # (type, address, offset, size, link) of each section; the header is name, type, flags, address, offset, size, link
    sections = [struct.unpack_from("<4xI8xQQQI", data, shoff + 64 * i) for i in range(shnum)]
    symtabs = [s for s in sections if s[0] == 2]
    if len(symtabs) != 1:
        raise Unreadable("no symbol table (a stripped image cannot be checked)")
    _, _, sym_off, sym_size, strndx = symtabs[0]
    if strndx >= shnum or sym_off + sym_size > len(data):
        raise Unreadable("symbol table out of the file")
    _, _, str_off, str_size, _ = sections[strndx]
    pool = None
    modules = {}
    for at in range(sym_off, sym_off + sym_size - 23, 24):
        name_at, _, _, shndx, value, size = struct.unpack_from("<IBBHQQ", data, at)
        if name_at >= str_size:
            raise Unreadable("symbol name out of the string table")
        end = data.index(b"\0", str_off + name_at)
        name = data[str_off + name_at:end].decode("ascii", "replace")
        if name == "state_pool":
            if pool is not None:
                raise Unreadable("two objects named state_pool")
            pool = size
        elif name.endswith("_state_desc"):
            if shndx == 0 or shndx >= shnum or size != DESC_BYTES:
                raise Unreadable(f"{name}: not a {DESC_BYTES}-byte record in a section")
            kind, addr, off, sec_size, _ = sections[shndx]
            if kind != 1 or value < addr or value - addr + DESC_BYTES > sec_size:
                raise Unreadable(f"{name}: outside its section")
            where = off + (value - addr)
            if where + DESC_BYTES > len(data):
                raise Unreadable(f"{name}: outside the file")
            if module_name(name) in modules:
                raise Unreadable(f"{name}: two records for one module")
            modules[module_name(name)], = struct.unpack_from("<I", data, where + BYTES_AT)
    if pool is None:
        raise Unreadable("no object named state_pool")
    return pool, modules


def block(n):
    return (n + BLOCK - 1) // BLOCK * BLOCK


def main(argv):
    if len(argv) < 2:
        print(__doc__.split("\n")[0], file=sys.stderr)
        return 2
    status = 0
    for path in argv[1:]:
        try:
            pool, modules = read(path)
        except (OSError, Unreadable, ValueError, struct.error) as e:
            print(f"state pool: {path}: cannot check: {e}")
            status = 2
            continue
        need = sum(block(n) for n in modules.values())
        if need <= pool:
            print(f"state pool: {path}: {len(modules)} modules need {need} of {pool} bytes, {pool - need} free")
        else:
            if status == 0:
                status = 1
            print(f"state pool: {path}: {len(modules)} modules need {need} bytes, the pool is {pool}: "
                  f"{need - pool} bytes over. Raise RT_STATE_POOL_BYTES for this flavor (Makefile) or cut state")
        for name, n in sorted(modules.items(), key=lambda kv: (-kv[1], kv[0])):
            print(f"state pool:   {block(n):8d}  {name}")
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv))
