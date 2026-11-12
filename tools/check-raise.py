#!/usr/bin/env python3
"""tools/check-raise.py: HX-1 ("focusing a window raises it", docs/specs/2026-11-05-h-hybrid.md) in user/ci/hdesk.ci.
Every way a window takes the focus goes through raise(), which gives a float or a monocle window the top rank
(user/ci/kit/stack.ci, tested hosted in tests/rs/raise_test.ci). layout.focus is called only by raise() and where a
window opens, its rank given on the lines before, the next one, so it opens on top. Each path below must call
raise()."""
import os
import re
import sys

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "user", "ci", "hdesk.ci")

# path: (function, raise() calls at least)
PATHS = {
    "a press on a window, and a Super drag": ("button", 2),
    "a press on a float's bar": ("bar_press", 1),
    "Alt+Tab and the switcher": ("switcher_close", 1),
    "the plane's window list": ("pl_window", 1),
    "the menu's window list": ("menu_choose", 1),
    "the tray": ("tray_restore", 1),
    "Super+Arrow, Super+Shift+m, the next after a minimize, Super+z": ("chord", 4),
    "Settings brought forward": ("settings_open", 1),
}
OPENS = {"new_term", "bound", "settings_open", "raise"}   # a new window's rank is the newest already


def functions(text):
    out = {}
    name = None
    for line in text.split("\n"):
        m = re.match(r"^[A-Za-z][\w\[\]]* (\w+)\(.*\) \{$", line)
        if m:
            name = m.group(1)
            out[name] = []
        elif line == "}":
            name = None
        elif name:
            out[name].append(line)
    return out


def main():
    fn = functions(open(SRC, encoding="utf-8").read())
    bad = []
    for path, (f, want) in PATHS.items():
        got = sum(len(re.findall(r"\braise\(", l)) for l in fn.get(f, []))
        if got < want:
            bad.append(f"{path}: {f}() calls raise() {got} times, wants {want}")
    chord = "\n".join(fn.get("chord", []))
    if chord.count("stack.unfull(") < 2:             # Super+z off and minimize give a fullscreen tile its cell back
        bad.append("chord() does not give a fullscreen tile its cell back on both Super+z and minimize")
    for f in ("new_term", "bound", "settings_open"):   # a new window takes the next rank: it opens on top
        text = "\n".join(fn.get(f, []))
        if not re.search(r"ranks = ranks \+ 1;\n\s*wrank\[i\] = ranks;", text):
            bad.append(f"{f}() does not give its new window the next rank")
    for f, body in fn.items():
        if f not in OPENS and any("layout.focus(" in l for l in body):
            bad.append(f"{f}() calls layout.focus without raise()")
    for b in bad:
        print("FAIL " + b)
    if bad:
        return 1
    print(f"every focus path raises ({len(PATHS)} paths); new_term, bound and settings_open open on top")
    return 0


if __name__ == "__main__":
    sys.exit(main())
