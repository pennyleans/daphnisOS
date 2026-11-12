"""tools/guestlines.py: the lines of a guest's transcript, or of a file a guest wrote, as a gate reads them.

lines(text) ends a line at "\n", "\r\n" and a lone "\r", as Python's universal newlines read a file, and drops the
empty piece after the last line end, as str.splitlines() does. str.splitlines() also ends a line at \v, \f, \x1c to
\x1e, U+0085, U+2028 and U+2029. A program can put those in text the desk logs (a terminal's title, RS-TTL), so a gate
that split with it could read a line the desk never wrote (docs/specs/2026-11-11-rs-ttl-bartitle.md section 2a).

find, has and count look for MARK at a line's start, where the desk and the kernel begin their lines, never after
other text on the line, where a program's title can stand (AC-R1). Use them for what a gate needs to see. What a gate
needs not to see stays `MARK not in text`: found anywhere, it can only fail more often, never pass on less. Each takes
str or bytes."""


def lines(text):
    out = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if out[-1] == "":
        out.pop()
    return out


def _ends(text):
    return ("\n", "\r") if isinstance(text, str) else (b"\n", b"\r")


def find(text, mark, at=0):
    """The offset of the first line at or after offset at that starts with mark, or -1."""
    if at <= 0 and text.startswith(mark):
        return 0
    best = -1
    for end in _ends(text):
        k = text.find(end + mark, max(at - 1, 0))
        if k >= 0 and (best < 0 or k + 1 < best):
            best = k + 1
    return best


def has(text, mark):
    """Whether a line of text starts with mark."""
    return find(text, mark) >= 0


def count(text, mark):
    """The lines of text that start with mark."""
    nl, cr = _ends(text)
    return int(text.startswith(mark)) + text.count(nl + mark) + text.count(cr + mark)
