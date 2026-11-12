#!/usr/bin/env python3
"""tools/check-tiler.py TILER: the W-1 gate (docs/specs/2026-11-05-w-tiler.md section 5). Draws what
user/ci/tiler.ci draws from the same rules in Python (the grid of section 3, the terminal's JetBrains Mono cells of
tools/textwin.py for the titles and the terminal (FONT-1), the face of tools/face.py for --face-only, the mark of
tools/mark.py, the words of user/ci/kit/tokens.ci) and runs TILER, a build of it, on each case:

  face        user/ci/kit/face.ci and mark.ci are what tools/face.py and tools/mark.py write
  2x2         --cols 2 --rows 2 --surface-out F: every line, the digest and F's bytes are the Python's
  3x2         --cols 3 --rows 2 (640 mod 3 = 1 px to the last column)
  3x7         --cols 3 --rows 7 (the remainder on both axes)
  mark        --mark-only (the mark at 1x and 2x)
  glyphs      --face-only: each glyph's 16 rows as the tiler prints them, any glyph that differs named
  term        --term-only with TERM_CASE on its standard input: the rows, the cursor and the surface of a
              terminal of 72 x 26 cells are those of vt(), the model of docs/specs/2026-11-06-e-editor.md section 5
  region      --term-only with TERM_REGION: the scroll region of BU-3 (section 5 too), every row and edge, as vt()
  style       --term-only with TERM_STYLE: bold and the colors of BU-3 (E-2b-2, D-1 B), every row and edge, as vt()
  motion      --term-only with TERM_MOTION: the cursor moves of K-9 (CUU, CUD, CUF, CUB), every edge, as vt()
  usage       --cols 17 is refused with status 2
  pins        the Python's nine digests are tests/expected/tiler.digests (frozen at ruling W-2 A and MK-1; term at E-2
              and again at E-2b-2, which draws its bold and color, and at K-2b, whose UTF-8 decode makes the stray
              continuation bytes two U+FFFD cells; region and style at BU-3; motion at K-9; the FONT-1 swap moves
              2x2, 3x2, 3x7, term, region, style and motion, refrozen on hyde in the batch pass)

One PASS or FAIL line a case; exits 1 on any FAIL. Then a `digest CASE HEX` line a case, the digest the tiler
printed, for check-tiler.sh to compare across builds.

tools/check-tiler.py --boot TRANSCRIPT: the W-2 gate (section 5) on a boot of the tile flavor (src/main_tile.ci):

  fullscreen  mcifb alone draws its pattern on the screen: the surface digest is F-1's, from the same rule
  frame       the tiler, on the screen, draws the 2x2 case: its digest is the frozen one
  client      mcifb in the tile: its private surface's digest is its pattern at the size the tiler set
  screen      the surface digest after the tiler is the 2x2 frame with the client's pattern in its tile
  input       three mkeys clients, keys and chords typed through the monitor: what each read, the focus moves, the
              end by Super+q, the tile queues' counts
  chords      no client read Super, an arrow, Enter or q
  screen      after the input run, the frame with the focus on tile 0,1
  ends        the runs end with status 0, nothing dropped, and the pool is whole after each run

tools/check-tiler.py --desk TRANSCRIPT FRAME WAD TICS: the W-4 gate (section 5) on a boot of the desk flavor
(src/main_desk.ci), where `ls; ./doom --sealed; exit` was typed into the shell as one line; FRAME is the last frame of
a Linux run of `doom --sealed --headless --frame-out FRAME`, TICS tests/expected/doom.tics:

  desk        the terminal is 79 x 13 cells in tile 0,0's client area of the 1 x 2 grid; tile 1 is 320 x 200,
              centered in tile 0,1's client area
  chain       the terminal's last rows are doom.tics' last lines, wrapped at 79 columns, then an empty row: the chain's
              tic 350 is the reference's, and each H_t holds H_(t-1), so every tic's is
  doom        doom's private surface in its tile is FRAME 1x through the WAD's PLAYPAL
  screen      the surface after the desk is the 1 x 2 frame, the terminal's rows in the face with the cursor at
              the start of the last row, and FRAME 1x in tile 1
  ends        the shell and the tiler end with status 0, nothing dropped, the pool whole

tools/check-tiler.py --place TRANSCRIPT: the H-2 gate (docs/specs/2026-11-05-h-hybrid.md section 7) on a boot of
the hyb flavor (src/main_hyb.ci), `tiler --place` over three mcifb in the 2 x 2 grid:

  place       each client placed before it starts: 0 at 2x with its client area, 1 at 1x with the area less its
              bottom right quarter in two rectangles, 2 with none; the settle returns 0
  clients     each private surface is the pattern at its size (placement never changes a client's surface)
  screen      the surface after the tiler is the 2x2 frame, client 0's top left quarter doubled in its area,
              client 1 in its two rectangles, tile 0,1 the frame's own
  ends        the clients and the tiler end with status 0, nothing dropped, the pool whole

tools/check-tiler.py --hosted OUTPUT: the terminal twin on the host (FONT-1 swap) against OUTPUT, a run of
tests/k/term_twin.ci: its case's bytes through vt() and term_pixels() at 1x and 2x equal the rows terms.ci drew."""
import array
import codecs
import hashlib
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.join(HERE, "..", "user", "ci", "kit")
sys.path.insert(0, HERE)
import face  # noqa: E402
import guestlines  # noqa: E402
import mark  # noqa: E402
import textwin  # noqa: E402

W, H = 640, 480          # the screen; --boot and --desk take it from the transcript's framebuffer line (H-R3)
# RES-1: the tiler offers at most the screen's W x H, as the kernel's FBIO_TILE_WANT takes (HX-0's 1920 x 1080 cap went)
MIN_W, MIN_H, PAD, TOP, BAND, GAP, FOCUS = 32, 24, 4, 2, 20, 8, 2
GLYPHS = face.table()
MARK = mark.figure()
MW = len(MARK[0])


def pools(text):
    """Strict reports: (free, total, filesystem-held, display-held), never inferred allowances.

    Malformed, orphaned or incomplete accounting anywhere invalidates the transcript.
    The display line is absent when no pool frames were transferred to the display.
    """
    records, display, tables = [], None, None
    for line_ in guestlines.lines(text):
        if line_.startswith("daphnis: display backing"):
            m = re.fullmatch(r"daphnis: display backing ([1-9][0-9]*) frames held", line_)
            if not m or display is not None or tables is not None:
                return []
            display = int(m[1])
        elif line_.startswith("daphnis: fs tables"):
            m = re.fullmatch(r"daphnis: fs tables ([0-9]+) frames held", line_)
            if not m or tables is not None:
                return []
            tables = int(m[1])
        elif line_.startswith("daphnis: pool frames free"):
            m = re.fullmatch(r"daphnis: pool frames free ([0-9]+) of ([0-9]+)", line_)
            if not m or tables is None:
                return []
            records.append((int(m[1]), int(m[2]), tables, display or 0))
            display = tables = None
        elif display is not None or tables is not None:
            return []
    return [] if display is not None or tables is not None else records


def whole(text):
    """Every report must reconcile with the independently named lifetime owners."""
    records = pools(text)
    return records if all(free + fs + display == total for free, total, fs, display in records) else []


def table(name, text):
    return [int(v, 16) for v in re.search(r"U32\[\d+\] %s = \[([^\]]*)\]" % name, text).group(1).replace(",", " ")
            .split()]


def tokens(theme=0):
    """K-3: theme's words of user/ci/kit/tokens.ci (0 Gruvbox Dark, the default; 1 Warm Paper), TOKENS each."""
    with open(os.path.join(KIT, "tokens.ci")) as f:
        text = f.read()
    n = int(re.search(r"export const I64 TOKENS = (\d+);", text).group(1))
    return table("words", text)[n * theme:n * (theme + 1)]


def token_ids():
    """The token names of tokens.ci and their indices."""
    with open(os.path.join(KIT, "tokens.ci")) as f:
        text = f.read()
    return {m.group(1): int(m.group(2)) for m in re.finditer(r"export const I64 ([A-Z_0-9]+) = (\d+);", text)
            if m.group(1) not in ("TOKENS", "DARK", "LIGHT")}


def lockup():
    """The lockup's words by tokens 0 to 5 (the mark's, in both themes)."""
    with open(os.path.join(KIT, "tokens.ci")) as f:
        return table("lockup_words", f.read())


def term_words():
    """The terminal's ground and ink (term_words), the same in both themes."""
    with open(os.path.join(KIT, "tokens.ci")) as f:
        return table("term_words", f.read())


WORDS = tokens()
DARK_WORDS = tokens(0)                 # the terminal's ANSI colors, dark in both themes (l, 20261108T005653Z)
TERM_PAPER, TERM_INK = term_words()
with open(os.path.join(KIT, "tokens.ci")) as _f:     # DN-45 B: bright black, its own word after the dark eight
    DARK_WORDS = list(DARK_WORDS) + [table("term_bright", _f.read())[0]]
BRIGHT_BLACK = len(DARK_WORDS) - 1
TOK = {k: WORDS[i] for k, i in token_ids().items()}
LOCKUP = lockup()
PAPER, INK, ULTRAMARINE = WORDS[0], WORDS[1], WORDS[2]


def use_theme(n):
    """K-3: theme n's words from now on, as the desk's live switch."""
    global WORDS, TOK, PAPER, INK, ULTRAMARINE
    WORDS = tokens(n)
    TOK = {k: WORDS[i] for k, i in token_ids().items()}
    PAPER, INK, ULTRAMARINE = WORDS[0], WORDS[1], WORDS[2]
PINS = os.path.join(HERE, "..", "tests", "expected", "tiler.digests")


def edge(span, n, i):
    return span if i == n else i * (span // n)


def cell(span, n, p):
    return min(p // (span // n), n - 1)


def hairline(span, n, p):
    return p == edge(span, n, cell(span, n, p) + 1) - 1


def paint(row, x0, x1, c):
    for x in range(max(x0, 0), min(x1, len(row))):
        row[x] = c


def frame(row, y, x0, y0, x1, y1, t, c):
    if y0 <= y < y1:
        if y < y0 + t or y >= y1 - t:
            paint(row, x0, x1, c)
        else:
            paint(row, x0, x0 + t, c)
            paint(row, x1 - t, x1, c)


def text(row, y, x0, y0, x1, s, c):
    x = x0
    for ch in s:
        if x + 8 > x1:
            return
        if y0 <= y < y0 + 16:
            bits = GLYPHS[ch if 32 <= ch <= 126 else 63][y - y0]
            for b in range(8):
                if bits >> (7 - b) & 1:
                    paint(row, x + b, x + b + 1, c)
        x += 8


def cells(row, y, x0, y0, x1, s, fg, bg):
    """user/ci/tiler.ci title_cells: s as terminal cells (kit/mtext.ci at 1x, textwin.py's twin), ink fg on ground
    bg, whole cells only, none past x1."""
    if not y0 <= y < y0 + 16:
        return
    x = x0
    for ch in s:
        if x + 8 > x1:
            return
        textwin.cell_row(row, x, y - y0, textwin.cell_index(ch), False, fg, bg, 1)
        x += 8


def mark_at(row, y, x0, y0, s, c):
    if y0 <= y < y0 + s * 16:
        my = (y - y0) // s
        for mx in range(MW):
            if MARK[my][mx]:
                paint(row, x0 + s * mx, x0 + s * mx + s, c)


def tile(row, y, c, r, x0, y0, x1, y1, lit):
    if y == y0 + BAND:
        paint(row, x0, x1, INK)
    tx = x0 + PAD
    first = c == 0 and r == 0
    if first and x0 + PAD + MW <= x1 - PAD:
        mark_at(row, y, x0 + PAD, y0 + TOP, 1, INK)
        tx = x0 + PAD + MW + GAP
    cells(row, y, tx, y0 + TOP, x1 - PAD, b"%d,%d %dx%d" % (c, r, x1 - x0, y1 - y0), INK, PAPER)
    if lit:
        frame(row, y, x0, y0, x1, y1, FOCUS, ULTRAMARINE)


def surface(mode, cols=2, rows=2, focus=0):
    """The surface's bytes, 4 * W a row, XRGB8888 little endian; the focus frame on tile c + cols * r == focus."""
    out = bytearray()
    if mode in TERM_INPUT:
        grid, x, y_, shown = vt(TERM_INPUT[mode], TERM_COLS, TERM_ROWS)
        pixels = term_pixels(grid, TERM_COLS, TERM_ROWS, x, y_, shown, 1, vt.form)
    for y in range(H):
        row = [PAPER] * W
        if mode == "mark":
            mark_at(row, y, 16, 16, 1, INK)
            mark_at(row, y, 16, 32 + 16, 2, INK)
        elif mode in TERM_INPUT:
            if TERM_AT <= y < TERM_AT + 16 * TERM_ROWS:
                row[TERM_AT:TERM_AT + 8 * TERM_COLS] = pixels[y - TERM_AT]
        elif mode == "face":
            for k in range(3):
                text(row, y, 16, 16 + 16 * k, W, bytes(range(32 + 32 * k, min(64 + 32 * k, 127))), INK)
        elif hairline(H, rows, y):
            row = [INK] * W
        else:
            r = cell(H, rows, y)
            y0, y1 = edge(H, rows, r), edge(H, rows, r + 1) - 1
            for c in range(cols):
                x0, x1 = edge(W, cols, c), edge(W, cols, c + 1) - 1
                row[x1] = INK
                tile(row, y, c, r, x0, y0, x1, y1, c + cols * r == focus)
        a = array.array("I", row)
        if sys.byteorder == "big":
            a.byteswap()
        out += a.tobytes()
    return bytes(out)


def expected(mode, cols=2, rows=2):
    """The tiler's lines and the surface's bytes."""
    lines = []
    if mode == "tiles":
        for r in range(rows):
            for c in range(cols):
                x0, y0 = edge(W, cols, c), edge(H, rows, r)
                lines.append("tiler: tile %d,%d at %d,%d inside %dx%d" % (
                    c, r, x0, y0, edge(W, cols, c + 1) - 1 - x0, edge(H, rows, r + 1) - 1 - y0))
    if mode == "face":
        lines += ["tiler: face %02x %s" % (c, bytes(GLYPHS[c]).hex()) for c in range(32, 127)]
    if mode in TERM_INPUT:
        grid, x, y, shown = vt(TERM_INPUT[mode], TERM_COLS, TERM_ROWS)
        lines += ["tiler: term %02d |%s|" % (r, bytes(g for g, *_ in grid[r]).decode("ascii").rstrip(" "))
                  for r in range(TERM_ROWS)]
        lines.append("tiler: cursor %d,%d %s" % (x, y, "shown" if shown else "hidden"))
    data = surface(mode, cols, rows)
    lines.append("tiler: surface %dx%d stride %d sha256 %s" % (W, H, 4 * W, hashlib.sha256(data).hexdigest()))
    return lines, data


def run(tiler, args, out=None, data=b""):
    argv = [tiler] + args + (["--surface-out", out] if out else [])
    try:
        p = subprocess.run(argv, input=data, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        return -1, [str(e)]
    return p.returncode, p.stdout.decode("ascii", "replace").splitlines()


def pattern(w, h):
    """mcifb's pattern (user/ci/mcifb.ci, F-1's rule) at w x h, 4 * w bytes a row."""
    out = bytearray()
    for y in range(h):
        for x in range(w):
            out += bytes(((x ^ y) & 255, y * 255 // (h - 1), x * 255 // (w - 1), 0))
    return bytes(out)


def screen_of(text):
    """Sets W, H from `daphnis: framebuffer WxH stride S` (H-R3: the tile and desk at any size); the
    surface line's regular expression at that size."""
    global W, H
    m = re.search(r"^daphnis: framebuffer (\d+)x(\d+) stride (\d+)$", text, re.M)
    if m:
        W, H = int(m.group(1)), int(m.group(2))
    return r"^daphnis: surface %dx%d stride %d sha256 ([0-9a-f]{64})$" % (W, H, 4 * W)


def client_area(x0, y0, x1, y1):
    """The client area of a tile whose inside is [x0, x1) x [y0, y1): x, y, w, h (user/ci/tiler.ci client_area)."""
    cx, cy = x0 + FOCUS, y0 + BAND + 1
    cw, ch = x1 - FOCUS - cx, y1 - FOCUS - cy
    if cw > W:
        cx, cw = cx + (cw - W) // 2, W
    if ch > H:
        cy, ch = cy + (ch - H) // 2, H
    return cx, cy, cw, ch


def boot(path):
    text = open(path, encoding="ascii", errors="replace").read()
    lines = guestlines.lines(text)
    results = []
    at_size = screen_of(text)

    def line(ok, label, detail=""):
        results.append(ok)
        print("%s  %s%s" % ("PASS" if ok else "FAIL", label, "" if ok else ": " + detail))

    def found(pattern_):
        return re.findall(pattern_, text, re.M)

    shots = found(at_size)
    full = hashlib.sha256(pattern(W, H)).hexdigest()
    line(len(shots) == 3 and shots[0] == full, "fullscreen: mcifb alone draws its pattern, surface %s" % full[:16],
         "surfaces %r" % shots)
    pins = dict(l.split() for l in open(PINS).read().splitlines())
    frame_pin = pins["2x2"] if (W, H) == (640, 480) else hashlib.sha256(surface("tiles", 2, 2)).hexdigest()
    own = found(at_size.replace("daphnis: surface", "tiler: surface"))
    line(own == [frame_pin] * 2, "frame: the tiler draws the 2x2 case on the screen, %s" % frame_pin[:16], "%r" % own)
    m = re.search(r"^tiler: start client 0 in tile 0,0 at (\d+),(\d+) inside (\d+)x(\d+)$", text, re.M)
    x0, y0, w, h = (int(v) for v in m.groups()) if m else (0, 0, 0, 0)
    tile_ = found(r"^daphnis: tile surface (\d+)x(\d+) at (\d+),(\d+) sha256 ([0-9a-f]{64})$")
    want = (x0, y0, w, h) == client_area(0, 0, edge(W, 2, 1) - 1, edge(H, 2, 1) - 1)
    client = pattern(w, h) if w > 1 and h > 1 else b""
    line(want and tile_ == [(str(w), str(h), str(x0), str(y0), hashlib.sha256(client).hexdigest())],
         "client: mcifb's private surface in tile 0,0 (%dx%d at %d,%d) is its pattern at that size" % (w, h, x0, y0),
         "start %r, tile %r" % (m and m.group(0), tile_))
    screen = bytearray(surface("tiles", 2, 2))
    for y in range(h):
        at = (y0 + y) * 4 * W + 4 * x0
        screen[at:at + 4 * w] = client[4 * w * y:4 * w * (y + 1)]
    composed = hashlib.sha256(bytes(screen)).hexdigest()
    line(len(shots) == 3 and shots[1] == composed and want,
         "screen: after the tiler, the 2x2 frame with the client's pattern in its tile, %s" % composed[:16],
         "surfaces %r" % shots)
    # W-3: three mkeys clients; what each read and what the tiler did, in order
    keys = ["key %d %d" % (k, v) for k in (30, 48, 46) for v in (1, 0)] + ["syn 6", "keys: nothing more queued, EAGAIN"]
    starts = ["tiler: start client %d in tile %d,%d at %d,%d inside %dx%d" % ((k, k % 2, k // 2) + client_area(
        edge(W, 2, k % 2), edge(H, 2, k // 2), edge(W, 2, k % 2 + 1) - 1, edge(H, 2, k // 2 + 1) - 1)) for k in range(3)]
    run3 = starts + keys + ["daphnis: tile queue 12 events given, 0 unread",
                            "tiler: client 0 in tile 0,0 ended, status 0", "tiler: focus 1,0"] + keys + [
        "daphnis: tile queue 12 events given, 0 unread", "tiler: client 1 in tile 1,0 ended, status 0",
        "tiler: focus 0,0", "tiler: focus 0,1", "key 30 1", "tiler: end client 2 in tile 0,1",
        "daphnis: tile queue 4 events given, 0 unread", "tiler: client 2 in tile 0,1 ended, status 15"]
    at = len(lines) - 1 - lines[::-1].index(starts[0]) if starts[0] in lines else -1   # the input run's
    got = lines[at:at + len(run3)] if at >= 0 else []
    line(got == run3, "input: a, b, c reach client 0 only; after Super+Right, a, b, c reach client 1 only; after "
         "Super+Left, Super+Down, a reaches client 2 (4 events) and Super+q ends it with SIGTERM",
         "first difference %r" % (next(((g, r) for g, r in zip(got + [None] * len(run3), run3) if g != r), None),))
    chords = [l for l in lines if re.match(r"^key (16|28|103|105|106|108|125|126) ", l)]
    line(not chords, "chords: no client read Super, an arrow, Enter or q", "%r" % chords)
    focused = hashlib.sha256(surface("tiles", 2, 2, focus=2)).hexdigest()
    line(len(shots) == 3 and shots[2] == focused,
         "screen: after the input run, the 2x2 frame with the focus on tile 0,1, %s" % focused[:16], "surfaces %r" % shots)
    ends = ["daphnis: exit 0"]
    line(lines.count(ends[0]) == 3 and len(whole(text)) == 3 and len(pools(text)) == 3 and lines[-1:] == ["daphnis: done"] and
         "daphnis: input dropped" not in lines and "tiler: client 0 in tile 0,0 ended, status 0" in lines,
         "ends: mcifb and the tilers end with status 0, nothing dropped; the pool is whole after each run",
         "see %s" % path)
    return 0 if all(results) else 1


def wad_lump(wad, name):
    count, offset = int.from_bytes(wad[4:8], "little"), int.from_bytes(wad[8:12], "little")
    for i in range(count):
        e = wad[offset + 16 * i:offset + 16 * i + 16]
        if e[8:16].rstrip(b"\0").upper() == name:
            o, n = int.from_bytes(e[0:4], "little"), int.from_bytes(e[4:8], "little")
            return wad[o:o + n]
    raise SystemExit("no lump %r" % name)


def frame_1x(frame, playpal):
    """doom's 320 x 200 frame 1x through its palette, 4 * 320 bytes a row (freedoom-ci src/client.c)."""
    pal = playpal[768 * (frame[64000] % 14):][:768]
    return b"".join(bytes((pal[3 * c + 2], pal[3 * c + 1], pal[3 * c], 0)) for c in frame[:64000])


def term_pixels(grid, tc, tr, cx, cy, shown, z=1, form=0):
    """The terminal (user/ci/terms.ci): grid[r][c] = (byte, reverse, color, background, bold, code point), a color
    a token of WORDS or None for the default (ink, paper); reverse swaps the two, and so does the shown cursor's cell
    when its form (DECSCUSR) is a block, 0 to 2 (both: not swapped); a bar (5, 6) is the cell's left 2 * z pixels in
    its ink, an underline (3, 4) its bottom 2 * z rows. Each cell is kit/mtext.ci's cell of its code point
    (tools/textwin.py cell_row, FONT-1), JetBrains Mono 600 when bold, 8 x 16 when z is 1 and 16 x 32 when z is 2.
    Pixel rows of 8 * z * tc words."""
    cw, ch = 8 * z, 16 * z
    out = []
    for y in range(ch * tr):
        r = y // ch
        row = [TERM_PAPER] * (cw * tc)
        for c, (_, rev, fg, bg, bold, cp) in enumerate(grid[r]):
            ink = TERM_INK if fg is None else DARK_WORDS[fg]
            paper = TERM_PAPER if bg is None else DARK_WORDS[bg]
            cursor = shown and (r, c) == (cy, cx)
            if rev != (cursor and form <= 2):
                ink, paper = paper, ink
            textwin.cell_row(row, cw * c, y - ch * r, textwin.cell_index(cp), bold, ink, paper, z)
            if cursor and form >= 5:
                row[cw * c:cw * c + 2 * z] = [ink] * (2 * z)
            elif cursor and form >= 3 and y - ch * r >= ch - 2 * z:
                row[cw * c:cw * c + cw] = [ink] * cw
        out.append(row)
    return out


def term_rows(rows, tc, tr, cx, cy, z=1):
    """Rows of plain text as the terminal draws them, the cursor shown; pixel rows of 4 * 8 * z * tc bytes."""
    grid = [[(ord(ch), False, None, None, False, ord(ch)) for ch in (rows[r] if r < len(rows) else "").ljust(tc)[:tc]] for r in range(tr)]
    out = []
    for row in term_pixels(grid, tc, tr, cx, cy, True, z):
        a = array.array("I", row)
        if sys.byteorder == "big":
            a.byteswap()
        out.append(a.tobytes())
    return out


BLANK = (32, False, None, None, False, 32)
ANSI = [token_ids()["ANSI"] + k for k in range(8)]   # ANSI 0 to 7 as tokens.ANSI + k, the dark theme's in both (KD-5 B, K-8)


def vt(data, tc, tr):
    """The terminal subset of docs/specs/2026-11-06-e-editor.md section 5 on data, in a grid of tc x tr cells:
    the grid, the cursor (x is tc while a wrap is pending) and whether it is shown; the cursor's form (DECSCUSR,
    ESC [ n SP q) is left in vt.form. The scroll region (BU-3) is rows top to bot - 1."""
    grid = [[BLANK] * tc for _ in range(tr)]
    st = {"x": 0, "y": 0, "rev": False, "shown": True, "top": 0, "bot": tr, "fg": None, "bg": None, "bold": False}
    vt.form = 0

    def shift(t, b, n):
        n = max(min(n, b - t), t - b)
        rows_ = grid[t:b]
        blanks = [[BLANK] * tc for _ in range(abs(n))]
        grid[t:b] = rows_[n:] + blanks if n > 0 else blanks + rows_[:len(rows_) + n]

    def down():
        if st["y"] == st["bot"] - 1:
            shift(st["top"], st["bot"], 1)
        elif st["y"] + 1 < tr:
            st["y"] += 1

    def up():
        if st["y"] == st["top"]:
            shift(st["top"], st["bot"], -1)
        elif st["y"] > 0:
            st["y"] -= 1

    def erase(r, c0, c1):
        grid[r][c0:c1] = [BLANK] * (c1 - c0)

    def csi(body, final):
        mark = body[:1] if body[:1] in (b"<", b"=", b">", b"?") else b""
        body = body[len(mark):]
        if body.endswith(b" ") and len(body) + len(mark) + 1 <= 64:
            # DECSCUSR: one SP after the parameters, then q; any other use of the SP is dropped
            digits = body[:-1]
            if not mark and final == ord("q") and all(48 <= b <= 57 for b in digits) and min(int(digits or b"0"), 9999) <= 6:
                vt.form = min(int(digits or b"0"), 9999)
            return
        if len(body) + len(mark) + 1 > 64 or any(b not in b"0123456789;:" for b in body):
            return
        ps = [min(int(p or b"0"), 9999) for p in re.split(rb"[;:]", body)][:16]
        arg = lambda k: ps[k] if k < len(ps) else 0          # noqa: E731
        x = min(st["x"], tc - 1)
        y = st["y"]
        if mark == b"?":
            if final in b"hl" and 25 in ps:
                st["shown"] = final == ord("h")
        elif mark:
            pass
        elif final in b"Hf":
            st["y"] = min(max(arg(0), 1), tr) - 1
            st["x"] = min(max(arg(1), 1), tc) - 1
        elif final == ord("J"):
            rows_ = {0: [(y, x, tc)] + [(r, 0, tc) for r in range(y + 1, tr)],
                     1: [(r, 0, tc) for r in range(y)] + [(y, 0, x + 1)], 2: [(r, 0, tc) for r in range(tr)]}
            for a in rows_.get(arg(0), []):
                erase(*a)
        elif final == ord("K"):
            erase(*{0: (y, x, tc), 1: (y, 0, x + 1), 2: (y, 0, tc)}.get(arg(0), (y, 0, 0)))
        elif final in b"ABCD":
            n = max(arg(0), 1)
            if final == ord("A"):
                st["y"] = max(y - n, st["top"] if y >= st["top"] else 0)
            elif final == ord("B"):
                st["y"] = min(y + n, st["bot"] - 1 if y < st["bot"] else tr - 1)
            st["x"] = {ord("C"): min(x + n, tc - 1), ord("D"): max(x - n, 0)}.get(final, x)
        elif final == ord("r"):
            t = min(max(arg(0), 1), tr) - 1
            b = arg(1) if 1 <= arg(1) < tr else tr
            if t + 1 < b:
                st.update(top=t, bot=b, x=0, y=0)
        elif final == ord("S") or (final == ord("T") and len(ps) == 1):
            shift(st["top"], st["bot"], max(arg(0), 1) * (1 if final == ord("S") else -1))
        elif final in b"LM":
            if st["top"] <= y < st["bot"]:
                shift(y, st["bot"], max(arg(0), 1) * (-1 if final == ord("L") else 1))
                st["x"] = 0
        elif final == ord("m"):
            k = 0
            while k < len(ps):
                p = ps[k]
                if p == 0:
                    st.update(rev=False, fg=None, bg=None, bold=False)
                elif p in (1, 22):
                    st["bold"] = p == 1
                elif p in (7, 27):
                    st["rev"] = p == 7
                elif p in (90, 100):
                    st["fg" if p == 90 else "bg"] = BRIGHT_BLACK   # DN-45 B
                elif 30 <= p <= 37 or 91 <= p <= 97:
                    st["fg"] = ANSI[p % 10]
                elif 40 <= p <= 47 or 101 <= p <= 107:
                    st["bg"] = ANSI[p % 10]
                elif p in (39, 49):
                    st["fg" if p == 39 else "bg"] = None
                elif p in (38, 48):
                    if arg(k + 1) == 5 and arg(k + 2) == 8:
                        st["fg" if p == 38 else "bg"] = BRIGHT_BLACK
                    elif arg(k + 1) == 5 and arg(k + 2) < 16:
                        st["fg" if p == 38 else "bg"] = ANSI[arg(k + 2) % 8]
                    k += {5: 2, 2: 4}.get(arg(k + 1), 0)
                k += 1

    def glyph(p):
        if st["x"] >= tc:
            st["x"] = 0
            down()
        grid[st["y"]][st["x"]] = (p if p <= 126 else ord("?"), st["rev"], st["fg"], st["bg"], st["bold"], p)
        st["x"] += 1

    # K-2b: text is UTF-8, a code point a cell; Python's "replace" is U+FFFD for each maximal ill-formed subpart,
    # and a byte below 0x80 that cuts a sequence comes out after its U+FFFD, to be read as text below
    utf8 = codecs.getincrementaldecoder("utf-8")("replace")
    i = 0
    while i < len(data):
        b = data[i]
        i += 1
        if b >= 0x80 or utf8.getstate()[0]:
            for ch in utf8.decode(bytes([b])):
                if ord(ch) >= 0x80:
                    glyph(ord(ch))
            if b >= 0x80:
                continue
        if b == 27:
            if i == len(data):
                break
            c = data[i]
            if c == ord("["):
                j = i + 1
                while j < len(data) and not 0x40 <= data[j] <= 0x7E and data[j] != 27:
                    j += 1
                if j < len(data) and data[j] != 27:
                    csi(data[i + 1:j], data[j])
                    j += 1
                i = j
            elif c == ord("]"):
                j = i + 1
                while j < len(data) and data[j] not in (7, 27):
                    j += 1
                i = j + 1 if j < len(data) and data[j] == 7 else j + 2
            elif c in b"DME":
                if c == ord("E"):
                    st["x"] = 0
                up() if c == ord("M") else down()
                i += 1
            elif 0x20 <= c <= 0x2F:
                while i < len(data) and 0x20 <= data[i] <= 0x2F:
                    i += 1
                i += 1
            elif c != 27:
                i += 1
        elif b == 13:
            st["x"] = 0
        elif b == 10:
            down()
        elif b == 8:
            st["x"] = max(min(st["x"], tc - 1) - 1, 0)
        elif b == 9:
            st["x"] = min((st["x"] // 8 + 1) * 8, tc - 1)
        elif 32 <= b <= 126:
            glyph(b)
    return grid, st["x"], st["y"], st["shown"]


TERM_COLS, TERM_ROWS, TERM_AT = 72, 26, 16       # user/ci/tiler.ci --term-only
TERM_CASE = b"".join((                           # every row of section 5's table, and its edges
    b"cleared by ED 2\x1b[2J\x1b[H" + b"above " * 30 + b"\x1b[3;5H\x1b[1J",
    b"\x1b[4;1Hplain text, then a wrap: " + b"0123456789" * 5 + b"wrapped\r\n",
    b"tab\tstops\tat 8\x08\x08BS\x07 bell\x7f del\r\n",
    b"\x1b[7mreverse\x1b[27m plain \x1b[1;7mbold reverse\x1b[m \x1b[38;5;7mcolor 7\x1b[0m \x1b[48;2;7;7;7mrgb\x1b[0m\r\n",
    b"utf-8: caf\xc3\xa9, \xe2\x82\xac10, \xf0\x9f\x98\x80!, a stray \x80\xbf continuation",
    b"\x1b[9;40Hat 9,40\x1b[f\x1b[0;0f\x1b[999;999H\x1b[;20H\x1b[10;1Hhome, corner, then 10,1",
    b"\x1b[11;1H" + b"to the end erased " * 3 + b"\x1b[11;30H\x1b[K",
    b"\x1b[12;1H" + b"to the start erased " * 3 + b"\x1b[12;30H\x1b[1K",
    b"\x1b[13;1Hwhole line erased\x1b[2K\x1b[13;1Hline 13 rewritten",
    b"\x1b[14;1H" + b"x" * 72 + b"\x1b[K\x1b[15;1H" + b"y" * 72 + b"\x1b[1Kpending wrap",
    b"\x1b]0;a title\x07\x1b]2;st title\x1b\\\x1b(B\x1b)0\x1b7\x1b8\x1b=\x1b>",
    b"\x1b[17;1Hosc and esc dropped\x1b[?2004h\x1b[?1049l\x1b[>4;1m\x1b[ 2q\x1b[1$p, private and intermediates too",
    b"\x1b[18;1H\x1b[" + b"1;" * 40 + b"7mlong csi dropped\x1b[18;99999999999999999999H!",
    b"\x1b[19;1H\x1b[1;2;3;4;5;6;8;9;10;11;12;13;14;15;16;7msixteen\x1b[0;1;2;3;4;5;6;8;9;10;11;12;13;14;15;0;7m kept",
    b"\x1b[20;1Hrestart \x1b[12\x1b[7min csi\x1b[0m, \x1b[3\rx a csi with a CR dropped",
    b"\x1b[24;5H\x1b[7m\x1b[?25l\x1b[?1;25;7h\x1b[?25;1l inverse, cursor hidden \x1b[0m",
    b"\x1b[25;1H" + b"below " * 20 + b"\x1b[25;10H\x1b[J\x1b[23;1Hrow 23\x1b[24;3H",
))
TERM_REGION = b"".join((                         # BU-3: the scroll region, each row of section 5 and its edges
    b"\x1b[2;1Hreset: the grid scrolls\x1b[5;10r\x1b[;r\x1b[26;1H\n",   # a missing b is the last row: row 2 to 1
    b"".join(b"\x1b[%d;1Hrow %02d" % (r, r) for r in range(2, 27)),
    b"\x1b[3;8r\t\t\t\thome after DECSTBM",                          # region 3 to 8, the cursor to 1,1
    b"\x1b[8;1H\n\n\nthree NL at the bottom",                         # the region scrolls up three
    b"\x1b[3;1H\x1bM\x1bMtwo RI at the top",                           # and down two
    b"\x1b[8;40H\x1bDone IND\x1bEnel",                                 # IND and NEL at the bottom
    b"\x1b[4;9H\x1b[M\tone DL\x1b[5;1H\x1b[L\tone IL",                  # DL and IL inside, the cursor to column 0
    b"\x1b[8;3r\x1b[6;6r\x1b[?5r\x1b[8;1H\x1bDstill 3 to 8",             # t >= b and a private r: refused
    b"\x1b[12;16r\x1b[0S\x1b[S\x1b[T\x1b[1;2;3;4;5T\x1b[13;1HSU 0, SU, SD",   # S 0 is 1; T of five: mouse, ignored
    b"\x1b[20;1H\x1b[3Lno IL outside\x1b[21;1H\x1b[MDL outside too",     # the cursor outside the region
    b"\x1b[24;99r\x1b[999T\x1b[25;1Hclamped",                           # b past the grid is its last row; T clamps
    b"\x1b[18;22r\x1b[22;1H" + b"w" * 72 + b"wrapped at the bottom",    # a pending wrap scrolls the region
    b"\x1b[26;1H\nbelow: no scroll\x1b[1;55H\x1bMabove: no scroll",     # outside it, at the grid's edges
))
TERM_STYLE = b"".join((                          # E-2b-2, K-8 (KD-5 B): bold and the theme's eight ANSI colors
    b"".join(b"\x1b[%dm fg %d \x1b[39m|" % (30 + a, a) for a in range(8)) + b"\r\n",
    b"".join(b"\x1b[%dm bg %d \x1b[49m|" % (40 + a, a) for a in range(8)) + b"\r\n",
    b"".join(b"\x1b[%d;%dm %d,%d \x1b[m" % (90 + a, 107 - a, a, 7 - a) for a in range(8)) + b"\r\n",
    b"\x1b[1mbold\x1b[22m plain \x1b[1;31mbold red\x1b[0m \x1b[1;7;34mbold reverse blue\x1b[m\r\n",
    b"\x1b[38;5;1m256 1\x1b[38;5;12m 256 12\x1b[38;5;200m 256 200 kept\x1b[38;2;9;9;9m rgb kept\x1b[m\r\n",
    b"\x1b[48;5;3m bg 256 3 \x1b[48;5;16m 16 kept \x1b[0;33;44myellow on blue\x1b[7m reversed\x1b[27m\x1b[K\r\n",
    b"\x1b[32;43m" + b"g" * 72 + b"\x1b[m wrapped plain\r\n",
    b"\x1b[8;1H\x1b[31mred then erased\x1b[1K\x1b[m plain after",       # an erase writes plain blanks
    b"\x1b[9;1H\x1b[1;35mmagenta is its own\x1b[m",
    b"\x1b[10;1H\x1b[4;5;9;53mother SGR read and ignored\x1b[m",
    b"\x1b[12;14r\x1b[12;1H\x1b[34mrow 12 blue\x1b[m\x1b[12;1H\x1b[L\x1b[S\x1b[T\x1b[r",  # scrolls move the style
    b"\x1b[16;1H\x1b[36;41mcursor on color\x1b[16;3H\x1b[4 q",      # an underline cursor (DECSCUSR) in the cell's ink
))
TERM_MOTION = b"".join((                         # K-9: CUU, CUD, CUF and CUB (the line editor's moves), a letter a move
    b"\x1b[3;10H\x1b[2Aa\x1b[3;20H\x1b[9Ab",          # up 2; up past the top, held at row 1
    b"\x1b[5;10H\x1b[2Bc\x1b[25;10H\x1b[9Bd",         # down 2; down past the last row, held
    b"\x1b[8;10H\x1b[5Ce\x1b[8;60H\x1b[99Cf",         # right 5; right past the last column, held there
    b"\x1b[9;10H\x1b[5Dg\x1b[9;3H\x1b[99Dh",          # left 5; left past column 1, held
    b"\x1b[10;5H\x1b[0Ci\x1b[10;20H\x1b[Dj",          # 0 is 1; none is 1
    b"\x1b[11;1H" + b"p" * 72 + b"\x1b[Dk",           # from a pending wrap: left of the last column, the wrap gone
    b"\x1b[12;1H" + b"q" * 72 + b"\x1b[Bl",           # down from a pending wrap: the last column of the next row
    b"\x1b[17;21r\x1b[19;5H\x1b[9Am\x1b[19;10H\x1b[9Bn",   # inside the region 17 to 21: held at its edges
    b"\x1b[24;15H\x1b[9Ao\x1b[15;5H\x1b[9BP",         # from below it, up to its top; from above it, down to its bottom
    b"\x1b[23;20H\x1b[9BQ\x1b[2;5H\x1b[9AR",          # outside it, away from it: the grid's edges
    b"\x1b[r\x1b[1;2;3A\x1b[5;1;9B\x1b[3;7C\x1b[?2DS",   # the first parameter only; a private CSI ignored
))
TERM_INPUT = {"term": TERM_CASE, "region": TERM_REGION, "style": TERM_STYLE, "motion": TERM_MOTION}


def desk(path, frame_path, wad_path, tics_path):
    text_ = open(path, encoding="ascii", errors="replace").read()
    lines = guestlines.lines(text_)
    results = []
    at_size = screen_of(text_)

    def line(ok, label, detail=""):
        results.append(ok)
        print("%s  %s%s" % ("PASS" if ok else "FAIL", label, "" if ok else ": " + detail))

    cols, rows = 1, 2
    cx0, cy0 = FOCUS, BAND + 1
    cw, ch = edge(W, 1, 1) - 1 - FOCUS - cx0, edge(H, 2, 1) - 1 - FOCUS - cy0
    tc, tr = min(cw // 8, 480), min(ch // 16, 135)       # user/ci/terms.ci MAX_COLS, MAX_ROWS (H-R2)
    ax, ay, aw, ah = client_area(0, edge(H, 2, 1), edge(W, 1, 1) - 1, edge(H, 2, 2) - 1)
    ox, oy = ax + (aw - 320) // 2, ay + (ah - 200) // 2
    want = ["tiler: desk terminal %dx%d in tile 0,0 at %d,%d" % (tc, tr, cx0, cy0),
            "tiler: desk tile 1 at %d,%d inside 320x200 for the next client (0)" % (ox, oy)]
    line(all(w in lines for w in want), "desk: a terminal of %dx%d cells at %d,%d; tile 1 is 320x200 at %d,%d" % (
        tc, tr, cx0, cy0, ox, oy), "want %r" % want)
    tail = []
    for l in open(tics_path).read().splitlines() + [""]:
        tail += [l[i:i + tc] for i in range(0, max(len(l), 1), tc)]
    expect_rows = tail[-tr:]
    got_rows = [m for m in re.findall(r"^tiler: term \d+ \|(.*)\|$", text_, re.M)]
    line(got_rows == expect_rows, "chain: the terminal's last rows are doom.tics' last lines, wrapped at %d, then "
         "an empty row; tic 350's chain is the reference's" % tc,
         "first difference %r" % (next(((g, e) for g, e in zip(got_rows + [None] * tr, expect_rows) if g != e), None),))
    frame = open(frame_path, "rb").read()
    wad = open(wad_path, "rb").read()
    pic = frame_1x(frame, wad_lump(wad, b"PLAYPAL")) if len(frame) == 64001 else b""
    tile_ = re.findall(r"^daphnis: tile surface (\d+)x(\d+) at (\d+),(\d+) sha256 ([0-9a-f]{64})$", text_, re.M)
    line(tile_ == [("320", "200", str(ox), str(oy), hashlib.sha256(pic).hexdigest())],
         "doom: its private surface in tile 1 is the Linux run's last frame 1x through PLAYPAL, %s" %
         hashlib.sha256(pic).hexdigest()[:16], "tile %r" % tile_)
    screen = bytearray(surface("tiles", cols, rows, focus=0))
    for y, px in enumerate(term_rows(expect_rows, tc, tr, 0, tr - 1)):
        at = (cy0 + y) * 4 * W + 4 * cx0
        screen[at:at + len(px)] = px
    for y in range(200 if pic else 0):
        at = (oy + y) * 4 * W + 4 * ox
        screen[at:at + 4 * 320] = pic[4 * 320 * y:4 * 320 * (y + 1)]
    composed = hashlib.sha256(bytes(screen)).hexdigest()
    shots = re.findall(at_size, text_, re.M)
    line(shots == [composed], "screen: the 1x2 frame, the terminal's rows with the cursor on the last, the frame in "
         "tile 1, %s" % composed[:16], "surfaces %r" % shots)
    line("tiler: desk shell ended, status 0" in lines and lines.count("daphnis: exit 0") == 1 and
         whole(text_) and "daphnis: input dropped" not in lines and
         lines[-1:] == ["daphnis: done"], "ends: the shell and the tiler end with status 0, nothing dropped, the pool "
         "whole", "see %s" % path)
    return 0 if all(results) else 1


def placed(path):
    text = open(path, encoding="ascii", errors="replace").read()
    lines = guestlines.lines(text)
    results = []
    at_size = screen_of(text)

    def line(ok, label, detail=""):
        results.append(ok)
        print("%s  %s%s" % ("PASS" if ok else "FAIL", label, "" if ok else ": " + detail))

    areas = [client_area(edge(W, 2, k % 2), edge(H, 2, k // 2), edge(W, 2, k % 2 + 1) - 1, edge(H, 2, k // 2 + 1) - 1)
             for k in range(3)]
    plan = []
    for k, (cx, cy, cw, ch) in enumerate(areas):
        if k % 3 == 0:
            plan.append((2, [(cx, cy, cw, ch)]))
        elif k % 3 == 1:
            plan.append((1, [(cx, cy, cw, ch // 2), (cx, cy + ch // 2, cw // 2, ch - ch // 2)]))
        else:
            plan.append((1, []))
    want = []
    for k, (cx, cy, cw, ch) in enumerate(areas):
        want += ["tiler: start client %d in tile %d,%d at %d,%d inside %dx%d" % (k, k % 2, k // 2, cx, cy, cw, ch),
                 "tiler: place client %d at %d,%d scale %d rects %d" % (k, cx, cy, plan[k][0], len(plan[k][1]))]
    got = [l for l in lines if l.startswith(("tiler: start client", "tiler: place client"))]
    line(got == want and "tiler: settle 0" in lines, "place: 0 at 2x, 1 at 1x in two rectangles, 2 hidden; the settle "
         "returns 0", "got %r" % got)
    tiles = re.findall(r"^daphnis: tile surface (\d+)x(\d+) at (\d+),(\d+) sha256 ([0-9a-f]{64})$", text, re.M)
    want_t = sorted((str(cw), str(ch), str(cx), str(cy), hashlib.sha256(pattern(cw, ch)).hexdigest())
                    for cx, cy, cw, ch in areas)
    line(sorted(tiles) == want_t, "clients: each private surface is mcifb's pattern at its size", "%r" % tiles)
    screen = bytearray(surface("tiles", 2, 2))
    for k, (cx, cy, cw, ch) in enumerate(areas):
        s, rects = plan[k]
        src = pattern(cw, ch)
        for (x0, y0, w, h) in rects:
            for y in range(y0, y0 + h):
                sy = (y - cy) // s
                for x in range(x0, x0 + w):
                    sx = (x - cx) // s
                    screen[4 * (W * y + x):4 * (W * y + x) + 4] = src[4 * (cw * sy + sx):4 * (cw * sy + sx) + 4]
    composed = hashlib.sha256(bytes(screen)).hexdigest()
    shots = re.findall(at_size, text, re.M)
    line(shots == [composed], "screen: the 2x2 frame, client 0's top left quarter at 2x, client 1 in two rectangles, "
         "client 2 hidden, %s" % composed[:16], "surfaces %r" % shots)
    ends = ["tiler: client %d in tile %d,%d ended, status 0" % (k, k % 2, k // 2) for k in range(3)]
    line(all(e in lines for e in ends) and lines.count("daphnis: exit 0") == 1 and
         whole(text) and lines[-1:] == ["daphnis: done"] and
         "daphnis: input dropped" not in lines, "ends: the clients and the tiler end with status 0, nothing dropped, "
         "the pool whole", "see %s" % path)
    return 0 if all(results) else 1


def hosted(path):
    """--hosted OUTPUT: a run of tests/k/term_twin.ci against vt() and term_pixels() on its own case."""
    data, tc, tr = b"", 0, 0
    with open(path) as f:
        for l in f:
            p = l.split()
            if p[:1] == ["case"]:
                data = bytes.fromhex(p[1])
            elif p[:1] == ["grid"]:
                tc, tr = int(p[1]), int(p[2])
    frames = textwin.check_proof(path)
    grid, x, y, shown = vt(data, tc, tr)
    bad = 0
    for z in (1, 2):
        w, h, rows = frames.get("term-%dx" % z, (0, 0, []))
        want = term_pixels(grid, tc, tr, x, y, shown, z, vt.form)
        ok = data and (w, h) == (8 * z * tc, 16 * z * tr) and rows == want
        bad += not ok
        first = next((k for k in range(min(len(rows), len(want))) if rows[k] != want[k]), None)
        print("%s  hosted: terms.ci's %dx%d case at %dx draws vt() and term_pixels()' %d rows (tools/textwin.py)%s" % (
            "PASS" if ok else "FAIL", tc, tr, z, 16 * z * tr, "" if ok else ": first row that differs %r" % first))
    return 1 if bad else 0


def main(argv):
    if argv[:1] == ["--hosted"]:
        return hosted(argv[1])
    if argv[:1] == ["--place"]:
        return placed(argv[1])
    if argv[:1] == ["--boot"]:
        return boot(argv[1])
    if argv[:1] == ["--desk"]:
        return desk(*argv[1:5])
    tiler = argv[0]
    results, digests, computed = [], [], []

    def line(ok, label, detail=""):
        results.append(ok)
        print("%s  %s%s" % ("PASS" if ok else "FAIL", label, "" if ok else ": " + detail))

    same = face.emit() == open(os.path.join(KIT, "face.ci")).read() and \
        face.emit2() == open(os.path.join(KIT, "face2.ci")).read() and \
        mark.emit(mark.figure()) == open(os.path.join(KIT, "mark.ci")).read()
    line(same, "face: user/ci/kit/face.ci, face2.ci and mark.ci are what tools/face.py and tools/mark.py write",
         "regenerate them with tools/face.py and tools/mark.py")
    cases = [("2x2", "tiles", 2, 2), ("3x2", "tiles", 3, 2), ("3x7", "tiles", 3, 7), ("mark", "mark", 0, 0),
             ("glyphs", "face", 0, 0), ("term", "term", 0, 0), ("region", "region", 0, 0), ("style", "style", 0, 0),
             ("motion", "motion", 0, 0)]
    with tempfile.TemporaryDirectory() as tmp:
        for name, mode, cols, rows in cases:
            args = ["--mark-only"] if mode == "mark" else ["--face-only"] if mode == "face" else \
                ["--term-only"] if mode in TERM_INPUT else ["--cols", str(cols), "--rows", str(rows)]
            want, data = expected(mode, cols, rows)
            computed.append("%s %s" % (name, want[-1].split()[-1]))
            out = os.path.join(tmp, name + ".surface")
            rc, got = run(tiler, args, out, TERM_INPUT.get(mode, b""))
            file_ok = os.path.exists(out) and open(out, "rb").read() == data
            digests.append("%s %s" % (name, got[-1].split()[-1] if got and " sha256 " in got[-1] else "none"))
            if mode == "face" and rc == 0 and got != want:
                bad = sorted({l.split()[2] for l in set(got) ^ set(want) if l.startswith("tiler: face ")})
                line(False, "glyphs: tiler %s" % " ".join(args), "glyphs %s differ from tools/face.py's" % " ".join(bad)
                     if bad else "the lines differ")
                continue
            detail = "status %d" % rc if rc else "the lines differ: %r" % sorted(set(got) ^ set(want))[:4] \
                if got != want else "the surface file differs from the digest's bytes"
            line(rc == 0 and got == want and file_ok, "%s: tiler %s draws the Python's surface, %s" % (
                name, " ".join(args), want[-1].split()[-1][:16]), detail)
    pinned = open(PINS).read().splitlines() if os.path.exists(PINS) else []
    line(pinned == computed, "pins: the nine digests are tests/expected/tiler.digests",
         "differ: %r" % sorted(set(pinned) ^ set(computed))[:4])
    rc, got = run(tiler, ["--cols", "17"])
    line(rc == 2 and bool(got) and got[-1].startswith("tiler: usage:"), "usage: tiler --cols 17 is refused with status 2",
         "status %d" % rc)
    for d in digests:
        print("digest " + d)
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
