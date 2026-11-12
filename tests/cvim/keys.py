"""tests/cvim/keys.py: a case's key script, read once for both legs of the oracle.

A script is text: every character is that key, and a name in angle brackets is a special key: <Esc> <C-[> <CR>
<BS> <Del> <Tab> <Up> <Down> <Left> <Right> <Home> <End> <C-r> <C-v> <C-d> <C-u> <C-f> <C-b> and <lt> for a literal
`<`. cvim's leg takes the key
codes of user/ced/keys.ci (read from that file, so the two never drift); Vim's leg takes the bytes an xterm sends.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
TOKEN = re.compile(r"<(Esc|C-\[|CR|BS|Del|Tab|Up|Down|Left|Right|Home|End|C-[rvdufb]|lt)>")

# name: (constant in keys.ci or a code point, bytes for Vim)
SPECIAL = {
    "Esc": ("K_ESC", b"\x1b"),
    "C-[": ("K_ESC", b"\x1b"),
    "CR": ("K_ENTER", b"\r"),
    "BS": ("K_BACKSPACE", b"\x7f"),
    "Del": ("K_DELETE", b"\x1b[3~"),
    "Tab": ("K_TAB", b"\t"),
    "Up": ("K_UP", b"\x1bOA"),
    "Down": ("K_DOWN", b"\x1bOB"),
    "Right": ("K_RIGHT", b"\x1bOC"),
    "Left": ("K_LEFT", b"\x1bOD"),
    "Home": ("K_HOME", b"\x1bOH"),
    "End": ("K_END", b"\x1bOF"),
    "C-r": ("M_CTRL+r", b"\x12"),
    "C-v": ("M_CTRL+v", b"\x16"),
    "C-d": ("M_CTRL+d", b"\x04"),
    "C-u": ("M_CTRL+u", b"\x15"),
    "C-f": ("M_CTRL+f", b"\x06"),
    "C-b": ("M_CTRL+b", b"\x02"),
    "lt": (ord("<"), b"<"),
}


def constants():
    """The exported I64 constants of user/ced/keys.ci."""
    src = (ROOT / "user" / "ced" / "keys.ci").read_text(encoding="utf-8")
    return {m[0]: int(m[1]) for m in re.findall(r"export const I64 (\w+) = (\d+);", src)}


def tokens(script):
    """The script as a list of ("char", code point) and ("key", name)."""
    out = []
    p = 0
    while p < len(script):
        m = TOKEN.match(script, p)
        if m:
            out.append(("key", m[1]))
            p = m.end()
        else:
            out.append(("char", ord(script[p])))
            p += 1
    return out


def codes(script, k=None):
    """cvim's leg: one key code per key."""
    k = k or constants()
    out = []
    for kind, v in tokens(script):
        if kind == "char":
            out.append(v)
            continue
        name = SPECIAL[v][0]
        if isinstance(name, int):
            out.append(name)
        elif name.startswith("M_CTRL+"):
            out.append(k["M_CTRL"] + ord(name[-1]))
        else:
            out.append(k[name])
    return out


def vim_bytes(script):
    """Vim's leg: (bytes, lone Esc) per key; a lone Esc is followed by a pause so Vim cannot read a key code."""
    out = []
    for kind, v in tokens(script):
        if kind == "char":
            out.append((chr(v).encode("utf-8"), False))
        else:
            b = SPECIAL[v][1]
            out.append((b, b == b"\x1b"))
    return out
