#!/usr/bin/env python3
"""gen45.py - the programs of chapter 45: the second game, LANTERN KEEP, its
world: sixteen rooms in the cartridge, the flip from one to the next, and a
map, in a cartridge of 32 KB.

    python3 gen45.py && ./build.sh

    game.asm    THE GAME, SO FAR. An explorer walks the sixteen rooms of a
                keep, four by four, through the doors between them. Each room
                is a list of runs of tiles in the cartridge's second half,
                which INIT shows in page 2 with chapter 38's setpage2. The
                room the explorer walks into is unpacked into the copy of the
                names in the frame it leaves the last one, and the next
                frame's sends give the VDP the whole page, ahead of the beam,
                with the explorer at its new place. M, or the joystick's
                button B, shows a map of the rooms seen, made from what was
                unpacked, in two thirds of the VRAM that the play's screen
                never looks at
    torn.asm    WHERE IT BREAKS: game.asm whose flip0 sends the page itself,
                as soon as the room is unpacked, in the same frame, instead
                of leaving it to the next frame's sends

The world is designed here, in Python: each room its doors and a few
rectangles of tiles, which runs() below turns into runs, and the checks
below hold for every door. The explorer, the frame, the queue and the
steps of 262 lines are chapter 44's ways; walled chapter 39's, with a wall
any name from the brick's up, as chapter 44 has it; here, setpage2 and
subreg chapter 38's. Every line of this chapter's own routines carries its
price, the MSX's T-states, which meas45.py checks with walk.py and the
debugger. The interrupt is taken in mode 2 (chapter 17); build.sh
assembles with --syntax=bFw.
"""
import os
import sys
from collections import deque

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
for ch in ("tools", "ch26", "ch30", "ch33", "ch35", "ch38", "ch39", "ch40", "ch42", "ch43", "ch44"):
    sys.path.insert(0, os.path.join(REPO, ch))
from asmparts import IM2, im2  # noqa: E402
from gen26 import tidy, db_rows, big  # noqa: E402  (chapter 26)
import gen33  # noqa: E402  (chapter 33: rate)
import gen35  # noqa: E402  (chapter 35: keys, joy)
import gen38  # noqa: E402  (chapter 38: here, setpage2, subreg)
import gen39  # noqa: E402  (chapter 39: cell, the brick)
import gen43  # noqa: E402  (chapter 43: the queue, post, the states)
import gen44  # noqa: E402  (chapter 44: walled, paced, post2, input)
sys.path.insert(0, HERE)

EU, JP = gen43.EU, gen43.JP
MACHINES = [EU, JP]
BLACK, DARK_BLUE, CYAN, WHITE = gen43.BLACK, gen43.DARK_BLUE, gen43.CYAN, gen43.WHITE
NAME = "LANTERN KEEP"

# ---------------------------------------------------------------- the world
# the tiles, numbered so that a wall is any name from BRICK up (chapter 44)
FLOOR, FLAG, RUG, BRICK, STONE, LANTERN = 0, 1, 2, 3, 4, 5
TILE_NAMES = ["FLOOR", "FLAG", "RUG", "BRICK", "STONE", "LANTERN"]
SOLID = {BRICK, STONE, LANTERN}
DARK = 8                                # the map's dark: no ink, no paper
N, E, S, W = 1, 2, 4, 8                 # a room's doors, a bit each
WAY = {N: 0, E: 1, S: 2, W: 3}          # the ways out, as walk gives them in D
TOP, BOTTOM = 1, 23                     # the room's rows; row 0 is the status line
DOOR_COLS = range(14, 18)               # the doors in the top and bottom walls
DOOR_ROWS = range(11, 15)               # and in the left and right walls
X_LAST, Y_FIRST, Y_LAST = 240, 7, 175   # the explorer's edges: X 0 to 240, Y 7 to 175
STEP = 2                                # its pixels a step, each way
EXITS = [E | S, W | S, E | S, W | S,
         N | S, N | E, N | W | S, N | S,
         N | E, W | E | S, N | W, N | S,
         E, N | W, E, N | W]
START = 13                              # the gate hall, B4
HOME = (120, 103)                       # where the explorer starts in it: X, Y


def rect(t, c0, r0, c1, r1):
    return (t, c0, r0, c1, r1)


# each room's tiles beyond its walls and doors: rectangles, columns c0 to
# c1, rows r0 to r1
FEATURES = [
    # 0 A1: four pillars round a rug
    [rect(STONE, 6, 5, 8, 7), rect(STONE, 23, 5, 25, 7), rect(STONE, 6, 17, 8, 19),
     rect(STONE, 23, 17, 25, 19), rect(RUG, 12, 9, 19, 16)],
    # 1 B1: a wall with a gap, flagstones below
    [rect(BRICK, 3, 7, 11, 7), rect(BRICK, 20, 7, 28, 7), rect(FLAG, 3, 16, 28, 21)],
    # 2 C1: steps of stone either side of a flagged path
    [rect(STONE, 4, 4, 6, 5), rect(STONE, 8, 7, 10, 8), rect(STONE, 21, 15, 23, 16),
     rect(STONE, 25, 18, 27, 19), rect(FLAG, 13, 3, 18, 21)],
    # 3 D1: the library, shelves of stone
    [rect(STONE, 3, 4, 10, 4), rect(STONE, 3, 8, 10, 8), rect(STONE, 3, 17, 10, 17),
     rect(STONE, 3, 20, 10, 20), rect(STONE, 21, 4, 28, 4), rect(STONE, 21, 8, 28, 8),
     rect(STONE, 21, 17, 28, 17), rect(STONE, 21, 20, 28, 20)],
    # 4 A2: a long hall between two walls
    [rect(BRICK, 8, 2, 8, 8), rect(BRICK, 8, 17, 8, 22), rect(BRICK, 23, 2, 23, 8),
     rect(BRICK, 23, 17, 23, 22), rect(FLAG, 11, 2, 20, 22)],
    # 5 B2: the great rug
    [rect(RUG, 4, 4, 27, 20), rect(STONE, 9, 9, 10, 10), rect(STONE, 21, 9, 22, 10),
     rect(STONE, 9, 15, 10, 16), rect(STONE, 21, 15, 22, 16)],
    # 6 C2: the crossing, a ring of stones
    [rect(STONE, 5, 4, 9, 5), rect(STONE, 22, 4, 26, 5), rect(STONE, 5, 19, 9, 20),
     rect(STONE, 22, 19, 26, 20), rect(FLAG, 11, 8, 20, 17)],
    # 7 D2: the gallery, pillars in two lines
    [rect(STONE, 9, 4, 10, 5), rect(STONE, 9, 9, 10, 10), rect(STONE, 9, 16, 10, 17),
     rect(STONE, 9, 20, 10, 21), rect(STONE, 21, 4, 22, 5), rect(STONE, 21, 9, 22, 10),
     rect(STONE, 21, 16, 22, 17), rect(STONE, 21, 20, 22, 21)],
    # 8 A3: a room in the room
    [rect(BRICK, 6, 5, 25, 5), rect(BRICK, 6, 6, 6, 19), rect(BRICK, 25, 6, 25, 8),
     rect(BRICK, 25, 17, 25, 19), rect(BRICK, 6, 19, 25, 19), rect(RUG, 9, 8, 22, 16)],
    # 9 B3: the cellar steps
    [rect(FLAG, 1, 2, 30, 6), rect(STONE, 4, 9, 8, 10), rect(STONE, 23, 9, 27, 10),
     rect(STONE, 4, 17, 8, 18), rect(STONE, 23, 17, 27, 18)],
    # 10 C3: a maze of walls
    [rect(BRICK, 6, 4, 6, 18), rect(BRICK, 6, 18, 20, 18), rect(BRICK, 25, 6, 25, 22),
     rect(BRICK, 11, 6, 25, 6)],
    # 11 D3: the well, between two rugs
    [rect(STONE, 13, 10, 18, 15), rect(RUG, 4, 4, 8, 20), rect(RUG, 23, 4, 27, 20)],
    # 12 A4: the store, crates of stone
    [rect(STONE, 3, 3, 5, 5), rect(STONE, 8, 3, 10, 5), rect(STONE, 3, 18, 5, 20),
     rect(STONE, 8, 18, 10, 20), rect(STONE, 20, 3, 22, 5), rect(STONE, 25, 3, 27, 5),
     rect(STONE, 20, 18, 22, 20), rect(STONE, 25, 18, 27, 20)],
    # 13 B4: the gate hall, where the explorer starts
    [rect(FLAG, 3, 3, 28, 21), rect(RUG, 13, 15, 18, 21), rect(STONE, 5, 5, 6, 6),
     rect(STONE, 25, 5, 26, 6)],
    # 14 C4: the chapel, rows of benches
    [rect(STONE, 5, 6, 12, 6), rect(STONE, 19, 6, 26, 6), rect(STONE, 5, 10, 12, 10),
     rect(STONE, 19, 10, 26, 10), rect(STONE, 5, 16, 12, 16), rect(STONE, 19, 16, 26, 16),
     rect(RUG, 13, 3, 18, 21)],
    # 15 D4: the last tower
    [rect(STONE, 4, 4, 9, 9), rect(STONE, 22, 15, 27, 20), rect(RUG, 13, 9, 18, 15)],
]
# two lanterns on each room's walls: (column, row); chapter 46 lights them
LANTERNS = [((10, 1), (21, 1)), ((5, 1), (26, 1)), ((10, 1), (21, 1)), ((0, 6), (31, 6)),
            ((0, 6), (31, 18)), ((10, 23), (21, 23)), ((31, 6), (31, 18)), ((0, 6), (0, 18)),
            ((10, 23), (21, 23)), ((10, 1), (21, 1)), ((31, 18), (10, 23)), ((0, 6), (31, 18)),
            ((10, 1), (0, 18)), ((10, 23), (21, 23)), ((10, 1), (21, 1)), ((10, 23), (31, 18))]
ROOMS = len(EXITS)
assert ROOMS == 16 == len(FEATURES) == len(LANTERNS)
ROOM_TITLES = ["four pillars round a rug", "a wall with a gap", "steps of stone",
               "the library", "a long hall", "the great rug", "the crossing", "the gallery",
               "a room in the room", "the cellar steps", "a maze of walls", "the well",
               "the store", "the gate hall", "the chapel", "the last tower"]


def room_name(k):
    return "ABCD"[k % 4] + str(k // 4 + 1)


def neighbour(k, way):
    return k + {N: -4, E: 1, S: 4, W: -1}[way]


for _k in range(ROOMS):                  # every door leads to a door
    for _w, _back in ((N, S), (E, W), (S, N), (W, E)):
        if EXITS[_k] & _w:
            _n = neighbour(_k, _w)
            assert 0 <= _n < ROOMS and EXITS[_n] & _back, (_k, _w)
            assert not (_w in (E, W) and _n // 4 != _k // 4), (_k, _w)


def grid(k):
    """room k's tiles: 23 rows, rows 1 to 23 of the screen, of 32 cells"""
    g = [[FLOOR] * 32 for _ in range(BOTTOM - TOP + 1)]
    ex = EXITS[k]
    for c in range(32):
        g[0][c] = g[-1][c] = BRICK
    for row in g:
        row[0] = row[31] = BRICK
    for c in DOOR_COLS:
        if ex & N:
            g[0][c] = FLOOR
        if ex & S:
            g[-1][c] = FLOOR
    for r in DOOR_ROWS:
        if ex & W:
            g[r - TOP][0] = FLOOR
        if ex & E:
            g[r - TOP][31] = FLOOR
    for t, c0, r0, c1, r1 in FEATURES[k]:
        for r in range(r0, r1 + 1):
            for c in range(c0, c1 + 1):
                g[r - TOP][c] = t
    for c, r in LANTERNS[k]:
        assert g[r - TOP][c] == BRICK, (k, c, r)
        g[r - TOP][c] = LANTERN
    return g


def runs(g):
    """a room's runs, row by row, none crossing the end of a row: (tile,
    cells), 1 to 32 cells"""
    out = []
    for row in g:
        c = 0
        while c < 32:
            t, n = row[c], 1
            while c + n < 32 and row[c + n] == t:
                n += 1
            out.append((t, n))
            c += n
    return out


def run_byte(t, n):
    """a run as a byte: the tile in bits 7 to 5, its cells less one in bits
    4 to 0"""
    return t << 5 | (n - 1)


def cells_of(x, y):
    """the cells (row, column) under the explorer's 16 x 16 pixels at X, Y,
    as walled finds them: its first line is Y + 1"""
    line = y + 1
    return [(r, c) for r in range(line >> 3, (line + 15 >> 3) + 1)
            for c in range(x >> 3, (x + 15 >> 3) + 1)]


def solid_at(g, x, y):
    """walled's test: does a wall's cell lie under the explorer at (X, Y)?"""
    return any(g[r - TOP][c] in SOLID for r, c in cells_of(x, y))


def door_steps(k):
    """for each way out of room k, the places from which a step goes out"""
    ex, out = EXITS[k], {}
    if ex & N:
        out[N] = [(x, Y_FIRST) for x in range(0, X_LAST + 1, STEP)]
    if ex & S:
        out[S] = [(x, Y_LAST) for x in range(0, X_LAST + 1, STEP)]
    if ex & W:
        out[W] = [(0, y) for y in range(Y_FIRST, Y_LAST + 1, STEP)]
    if ex & E:
        out[E] = [(X_LAST, y) for y in range(Y_FIRST, Y_LAST + 1, STEP)]
    g = grid(k)
    return {w: [p for p in v if not solid_at(g, *p)] for w, v in out.items()}


def reach(g, start):
    """every place the explorer can walk to from START, a step at a time"""
    seen, q = {start}, deque([start])
    while q:
        x, y = q.popleft()
        for dx, dy in ((STEP, 0), (-STEP, 0), (0, STEP), (0, -STEP)):
            nx, ny = x + dx, y + dy
            if 0 <= nx <= X_LAST and Y_FIRST <= ny <= Y_LAST and (nx, ny) not in seen \
                    and not solid_at(g, nx, ny):
                seen.add((nx, ny))
                q.append((nx, ny))
    return seen


def entry(way, x, y):
    """where the explorer stands after a step out by WAY from (X, Y): the
    same line or column, at the other edge of the next room"""
    return {N: (x, Y_LAST), S: (x, Y_FIRST), E: (0, y), W: (X_LAST, y)}[way]


for _k in range(ROOMS):                  # every door of every room reached, and a step
    _g = grid(_k)                        # out puts the explorer where it can stand
    _ds = door_steps(_k)
    assert all(_ds.values()), _k
    _from = HOME if _k == START else next(iter(next(iter(_ds.values()))))
    _r = reach(_g, _from)
    assert all(any(p in _r for p in v) for v in _ds.values()), _k
    for _w, _v in _ds.items():
        for x, y in _v:
            assert not solid_at(grid(neighbour(_k, _w)), *entry(_w, x, y)), (_k, _w, x, y)
        # and the edge is a wall but for the door: walled lets the explorer
        # onto it only there
        for x in range(0, X_LAST + 1, STEP):
            for y in range(Y_FIRST, Y_LAST + 1, STEP):
                if (x in (0, X_LAST) or y in (Y_FIRST, Y_LAST)) and not solid_at(_g, x, y):
                    on = {W: x == 0, E: x == X_LAST, N: y == Y_FIRST, S: y == Y_LAST}
                    assert all(EXITS[_k] & w for w, b in on.items() if b), (_k, x, y)
assert not solid_at(grid(START), *HOME)

ROOM_RUNS = [runs(grid(k)) for k in range(ROOMS)]
RUN_BYTES = [[run_byte(t, n) for t, n in rr] for rr in ROOM_RUNS]
assert all(sum(n for _, n in rr) == 736 for rr in ROOM_RUNS)
assert all(t < 8 for rr in ROOM_RUNS for t, _ in rr)

# ---------------------------------------------------------------- the shapes and colours
PAPER_C = gen43.PAPER_C                 # black ink on white paper: the floor, the text
BRICK_C = gen43.BRICK_C                 # black on dark blue: chapter 39's brick
RUG_C = gen43.ALLEY_C                   # cyan paper, no ink
LAMP_C = CYAN << 4 | DARK_BLUE          # a lantern, cyan in the wall
DARK_C = BLACK << 4 | BLACK
HERE_C = BLACK << 4 | CYAN              # the map: the room the explorer is in
EXPLORER_C = BLACK
BORDER = BLACK
SHAPES = {
    FLOOR: [0] * 8,
    FLAG: [0x80, 0x00, 0x00, 0x00, 0x08, 0x00, 0x00, 0x00],
    RUG: [0] * 8,
    BRICK: list(gen39.BRICK),
    STONE: [0xFF, 0x81, 0xBD, 0xA5, 0xA5, 0xBD, 0x81, 0xFF],
    LANTERN: [0x10, 0x38, 0x7C, 0x44, 0x54, 0x44, 0x7C, 0x00],
}
COLOURS = {FLOOR: PAPER_C, FLAG: PAPER_C, RUG: RUG_C, BRICK: BRICK_C, STONE: BRICK_C, LANTERN: LAMP_C}
FONT = gen43.FONT                       # chapter 30's characters, codes 32 to 127
MINI0 = 128                             # the rooms' pictures: 12 names each, 128 to 223
CURRENT = 224                           # and the explorer's room's: twelve from 224


def shape_set():
    """the 2,048 bytes of a third's shapes: the tiles, the dark, the
    characters; the pictures' names clear"""
    out = [0] * 2048
    for t, rows in SHAPES.items():
        out[8 * t:8 * t + 8] = rows
    out[8 * 32:8 * 128] = FONT
    return out


def colour_set():
    """the 2,048 bytes of a third's colours"""
    out = [0] * 2048
    for t, c in COLOURS.items():
        out[8 * t:8 * t + 8] = [c] * 8
    out[8 * DARK:8 * DARK + 8] = [DARK_C] * 8
    out[8 * 32:8 * 128] = [PAPER_C] * 768
    out[8 * MINI0:8 * CURRENT] = [PAPER_C] * (8 * (CURRENT - MINI0))
    out[8 * CURRENT:8 * (CURRENT + 12)] = [HERE_C] * 96
    for first in [mini_name(k) for k in range(8)] + [CURRENT]:
        for n in range(first + 8, first + 12):      # a picture's last line, under the room:
            out[8 * n + 7] = DARK_C                 # dark
    return out


def d2(i, j):
    return (i - 7.5) ** 2 + (j - 7.5) ** 2


def explorer_rows():
    """the explorer seen from above: a hood round a face, 16 x 16"""
    rows = []
    for j in range(16):
        v = 0
        for i in range(16):
            ink = 4.9 ** 2 < d2(i, j) <= 7.4 ** 2              # the hood
            if j in (6, 7) and i in (5, 6, 9, 10):
                ink = True                                     # the eyes
            if j == 10 and 6 <= i <= 9:
                ink = True                                     # the mouth
            v |= ink << (15 - i)
        rows.append(v)
    return rows


EXPLORER = explorer_rows()
SPRITE_PATTERNS = big(EXPLORER)         # patterns 0 to 3
assert len(SPRITE_PATTERNS) == 32

# ---------------------------------------------------------------- the screens
STATUS = [(1, NAME), (15, "ROOM"), (24, "SEEN")]
ROOM_AT, SEEN_AT = 20, 29               # row 0: the room's name, and the rooms seen
STATES = ["TITLE", "PLAY", "FLIP", "MAP"]
GAME_R3, GAME_R4 = 0x9F, 0x00           # one set of shapes and colours for three thirds
MAP_R3, MAP_R4 = 0xFF, 0x03             # the map: a set for each third
MAP_X, MAP_Y = 6, 4                     # the map: room A1's first cell, a room 4 x 3 cells
MAP_TEXTS = [(12, 2, "THE KEEP"), (7, 3, "A"), (12, 3, "B"), (17, 3, "C"), (22, 3, "D"),
             (8, 21, "PRESS M TO GO ON")]
MAP_DIGITS = [(4, MAP_Y + 1 + 4 * k, str(k + 1)) for k in range(4)]
TITLE_BOX = (6, 3, 25, 9)               # the title's wall: columns 6 to 25, rows 3 to 9
TITLE_TEXT = [(10, 6, NAME), (10, 15, "PRESS SPACE"), (3, 17, "CURSOR KEYS OR JOYSTICK 1"),
              (5, 19, "M OR BUTTON B: THE MAP")]
TITLE_LAMPS = [(8, 6), (23, 6)]         # a lantern either side of the name
TITLE_EXPLORER = (120, 87)              # X, Y: lines 88 to 103, below the wall
MAP_BIT = 0x20                          # held's bit 5: M or button B


def row0():
    out = [32] * 32
    for col, text in STATUS:
        out[col:col + len(text)] = [ord(c) for c in text]
    return out


def map_cell(k):
    """room k's top left cell on the map: column, row"""
    return MAP_X + 5 * (k % 4), MAP_Y + 4 * (k // 4)


def third_of(k):
    return map_cell(k)[1] // 8


def mini_name(k):
    """the first of room k's 12 names on the map, in its third"""
    return MINI0 + 12 * (k % 8)


for _k in range(ROOMS):                  # a room's three rows of names in one third, and
    _c, _r = map_cell(_k)                # no two rooms of a third with the same names
    assert _r // 8 == (_r + 2) // 8
assert all(len({mini_name(k) for k in range(ROOMS) if third_of(k) == t}) ==
           sum(1 for k in range(ROOMS) if third_of(k) == t) for t in range(3))


def map_names():
    """the map's page, rows 1 to 23: the dark, the texts and the digits;
    the rooms' places dark too, for mapbuild fills those seen"""
    out = [DARK] * 768
    for col, row, text in MAP_TEXTS + MAP_DIGITS:
        out[32 * row + col:32 * row + col + len(text)] = [ord(c) for c in text]
    return out[32:]


def title_names():
    """the title's 768 names: the status line's labels, a wall with the name
    and two lanterns inside it, and the lines to read"""
    out = [FLOOR] * 768
    out[0:32] = row0()
    c0, r0, c1, r1 = TITLE_BOX
    for r in range(r0, r1 + 1):
        for c in range(c0, c1 + 1):
            if r in (r0, r1) or c in (c0, c1):
                out[32 * r + c] = BRICK
    for col, row, text in TITLE_TEXT:
        out[32 * row + col:32 * row + col + len(text)] = [ord(c) for c in text]
    for col, row in TITLE_LAMPS:
        out[32 * row + col] = LANTERN
    return out


def first_copy():
    return [HOME[1], HOME[0], 0, EXPLORER_C, 0xD0]


def title_copy():
    return [TITLE_EXPLORER[1], TITLE_EXPLORER[0], 0, EXPLORER_C, 0xD0]


def ways():
    """leave's table, three bytes a way: the room's change, the place in the
    explorer's attributes it sets (0 for Y, 1 for X), and its value"""
    out = []
    for w in (N, E, S, W):
        out += [{N: -4, E: 1, S: 4, W: -1}[w] & 255, {N: 0, S: 0, E: 1, W: 1}[w],
                {N: Y_LAST, S: Y_FIRST, E: 0, W: X_LAST}[w]]
    return out


# ---------------------------------------------------------------- the RAM
VARS_AT = 0xC100
NAMES_AT = 0xC400
MAPN_AT = 0xC700
MINIS_AT = 0xCA00
MINI_BYTES = 96                         # a room's picture: 24 rows of 4 bytes
RAM = f"""stat    EQU VARS                ; the status isr read: F, 5S, C, a sprite's number
ticks   EQU VARS + 1            ; frames counted by isr, two bytes
state   EQU VARS + 3            ; TITLE, PLAY, FLIP or MAP
held    EQU VARS + 4            ; the keys and the stick: a 0 for each held
was     EQU VARS + 5            ; held as the loop before found it
room    EQU VARS + 6            ; the room the explorer is in, 0 to 15
seen    EQU VARS + 7            ; the rooms seen, BCD
fresh   EQU VARS + 8            ; 1: the room just come into had not been seen
queued  EQU VARS + 9            ; the names queued for the sends
keepy   EQU VARS + 10           ; the explorer's Y while the map is shown
whole   EQU VARS + 11           ; 1: the sends send a whole page
wsrc    EQU VARS + 12           ; its rows 1 to 23, two bytes
wr3     EQU VARS + 14           ; and R#3 and R#4 to show it with
wr4     EQU VARS + 15
queue   EQU VARS + $10          ; 16 names: the VRAM address, then the name
copy    EQU VARS + $40          ; the explorer's Y, X, pattern and colour,
explorer EQU copy               ; and the end
due     EQU VARS + $48          ; lines owed to the game's steps, two bytes
lines   EQU VARS + $4A          ; the machine's lines a frame: 313 or 262
been    EQU VARS + $50          ; a byte a room: 1 when seen
names   EQU ${NAMES_AT:04X}               ; the copy of the 768 names
mapn    EQU ${MAPN_AT:04X}               ; the map's page, rows 1 to 23
minis   EQU ${MINIS_AT:04X}               ; the rooms' pictures, 96 bytes each
"""
QUEUE_MAX = gen43.QUEUE_MAX

CONSTS = f"""SAT     EQU $1B00               ; the sprites' attributes
SPAT    EQU $3800               ; and their patterns
TITLE   EQU 0                   ; the states
PLAY    EQU 1
FLIP    EQU 2
MAP     EQU 3
FLOOR   EQU {FLOOR}                   ; the tiles' names: from BRICK up, a wall
FLAG    EQU {FLAG}
RUG     EQU {RUG}
BRICK   EQU {BRICK}
STONE   EQU {STONE}
LANTERN EQU {LANTERN}
DARK    EQU {DARK}                   ; the map's dark
DIGIT0  EQU $30                 ; '0': a digit's name is its code
CURRENT EQU {CURRENT}                 ; the names of the explorer's room on the map
X_LAST  EQU {X_LAST}                 ; the explorer's edges: X 0 to X_LAST,
Y_FIRST EQU {Y_FIRST}                   ; Y Y_FIRST to Y_LAST
Y_LAST  EQU {Y_LAST}
WAY_N   EQU 0                   ; the ways out
WAY_E   EQU 1
WAY_S   EQU 2
WAY_W   EQU 3
START   EQU {START}                  ; the gate hall
STEPL   EQU {gen44.LINES_A_STEP}                 ; the lines of a step: the 60 Hz frame
GAME_R3 EQU ${GAME_R3:02X}               ; R#3 and R#4 of the play: one set for three thirds
GAME_R4 EQU ${GAME_R4:02X}
MAP_R3  EQU ${MAP_R3:02X}               ; and of the map: a set for each
MAP_R4  EQU ${MAP_R4:02X}
ROOM_AT EQU {ROOM_AT}                  ; row 0: the room's name
SEEN_AT EQU {SEEN_AT}                  ; and the rooms seen
"""

# ---------------------------------------------------------------- the frame
ISR = """
; isr: every frame. The status kept in stat, the signal let down; the frame
; counted, and its lines owed to the game's steps; the keys and the stick
; read while the frame is young (chapter 44). Keeps every register it uses
isr:    push af                 ; 12
        in a, (VDP_CTRL)        ; 12  the status: F, 5S, C, a sprite's number
        ld (stat), a            ; 14
        push bc                 ; 12
        push hl                 ; 12
        ld hl, (ticks)          ; 17
        inc hl                  ;  7
        ld (ticks), hl          ; 17
        ld hl, (due)            ; 17  the lines owed to the game ...
        ld bc, (lines)          ; 22
        add hl, bc              ; 12  ... and this frame's, 262 or 313
        ld (due), hl            ; 17
        call input              ; 18  held
        pop hl                  ; 11
        pop bc                  ; 11
        pop af                  ; 11
isrend: ei                      ;  5
        ret                     ; 11
"""

# chapter 35's keys with row 4's M as button B
KEYS = gen35.KEYS.replace(
    """; keys: row 8 of the keyboard -> A in register 14's way: the cursor keys as
; the four switches, SPACE as button A, a 0 for each held. The interrupts
; must be off. Uses A, C, HL
keys:   in a, (PPI_C)           ; 12
        and $F0                 ;  8  port C's top bits kept (chapter 34)
        or 8                    ;  8
        out (PPI_C), a          ; 12  row 8""",
    """; keys: rows 4 and 8 of the keyboard -> A in register 14's way: the cursor
; keys as the four switches, SPACE as button A, M as button B, a 0 for each
; held. The interrupts must be off. Uses A, BC, HL
keys:   in a, (PPI_C)           ; 12
        and $F0                 ;  8  port C's top bits kept (chapter 34)
        ld c, a                 ;  5
        or 4                    ;  8
        out (PPI_C), a          ; 12  row 4
        in a, (PPI_B)           ; 12  bit 2: M
        or $FB                  ;  8  M alone
        rlca                    ;  5
        rlca                    ;  5
        rlca                    ;  5  into bit 5, button B's
        ld b, a                 ;  5
        ld a, c                 ;  5
        or 8                    ;  8
        out (PPI_C), a          ; 12  row 8""").replace(
    """        or (hl)                 ;  8  and the cursor keys as the switches
        or $E0                  ;  8
        ret                     ; 11""",
    """        or (hl)                 ;  8  and the cursor keys as the switches
        or $E0                  ;  8
        and b                   ;  5  and M
        ret                     ; 11""")
assert KEYS.count("row 4") == 1 and KEYS.count("and b ") == 1

INPUT = gen44.INPUT.replace("; input: in the interrupt, the cursor keys and joystick 1 together (chapters\n"
                            "; 34 and 35) -> held, in register 14's way: bits 0 to 3 up, down, left,\n"
                            "; right, bit 4 SPACE or button A, a 0 for each held. Uses A, BC, HL",
                            "; input: in the interrupt, the keys and joystick 1 together (chapters 34\n"
                            "; and 35) -> held, in register 14's way: bits 0 to 3 up, down, left, right,\n"
                            "; bit 4 SPACE or button A, bit 5 M or button B, a 0 for each held. Uses A,\n"
                            "; BC, HL")
INPUT = INPUT.replace("call keys               ; 18  row 8 in register 14's way",
                      "call keys               ; 18  rows 4 and 8 in register 14's way")
assert INPUT != gen44.INPUT and "rows 4 and 8 in" in INPUT

MAIN = gen43.MAIN.replace("; 18  sprites, names queued, the status line",
                          "; 18  the explorer, the names queued, a page")
assert MAIN != gen43.MAIN

SENDS = """
; sends: straight after HALT, before the paper: the explorer's attributes,
; the names the frame before queued, and the whole page if one was left.
; Uses A, BC, DE, HL
sends:  VRAM_WRITE SAT          ; 40
        ld hl, copy             ; 11
        ld bc, 5 << 8 | VDP_DATA ; 11  the explorer and the end
        otir                    ; 23 a byte, 18 the last
        ld hl, queued           ; 11
        ld a, (hl)              ;  8
        or a                    ;  5
        jr z, .page             ; 13, or 8  none queued
        ld b, a                 ;  5
        ld (hl), 0              ; 11  none from now on
        ld l, low queue         ;  8  the queue in queued's page
.name:  ld a, (hl)              ;  8
        out (VDP_CTRL), a       ; 12
        inc l                   ;  5
        ld a, (hl)              ;  8
        out (VDP_CTRL), a       ; 12  its address
        inc l                   ;  5
        ld a, (hl)              ;  8
        out (VDP_DATA), a       ; 12  and its name
        inc l                   ;  5
        djnz .name              ; 14, or 9
.page:  ld hl, whole            ; 11
        ld a, (hl)              ;  8
        or a                    ;  5
        ret z                   ; 12, or 6  no page
        ld (hl), 0              ; 11
        ld hl, (wsrc)           ; 17
        ld de, (wr3)            ; 22  E: R#3, D: R#4
; show: HL = rows 1 to 23 of a page, E = R#3 and D = R#4 -> the registers
; set and the 736 names sent at 29 T-states a name (chapter 20), from row 1
; down: ahead of the beam, if they start before the paper does. Uses A, BC,
; D, HL
show:   di                      ;  5
        ld a, e                 ;  5
        out (VDP_CTRL), a       ; 12
        ld a, $83               ;  8
        out (VDP_CTRL), a       ; 12  R#3
        ld a, d                 ;  5
        out (VDP_CTRL), a       ; 12
        ld a, $84               ;  8
        out (VDP_CTRL), a       ; 12  R#4
        VRAM_WRITE $1820        ; 40  row 1
        ei                      ;  5
        ld bc, VDP_DATA         ; 11  B: 0, a run of 256
        ld d, 2                 ;  8  two runs
.run:   outi                    ; 18
        jp nz, .run             ; 11
        dec d                   ;  5
        jr nz, .run             ; 13, or 8
        ld b, 224               ;  8  and 224 more
.end:   outi                    ; 18
        jp nz, .end             ; 11
        ret                     ; 11
"""

PAGE = """
; page: HL = rows 1 to 23 of a page of names, E = R#3 and D = R#4 to show it
; with -> all left for the next frame's sends. Uses A
page:   ld (wsrc), hl           ; 17
        ld (wr3), de            ; 22  R#3, then R#4
        ld a, 1                 ;  8
        ld (whole), a           ; 14
        ret                     ; 11
"""

PRESSES = """
; presses: -> A = the keys held now and not the loop before, a 1 for each;
; was keeps held for the next time. Uses A, B, HL
presses: ld hl, was             ; 11
        ld a, (held)            ; 14
        ld b, (hl)              ;  8  the loop before's
        ld (hl), a              ;  8  and this loop's, for the next
        cpl                     ;  5  a 1 for each held now
        and b                   ;  5  and not then
        ret                     ; 11
"""

WALK = """
; walk: held -> the explorer two pixels along X for LEFT or RIGHT, then two
; along Y for UP or DOWN, each where walled finds no wall (chapter 39); a
; step past an edge, where only a door lets the explorer stand, goes out:
; the carry, D = the way out. Uses A, BC, DE, HL
walk:   ld bc, (explorer)       ; 22  C = Y, B = X
        ld hl, held             ; 11
        bit 2, (hl)             ; 14  LEFT
        jr nz, .right           ; 13, or 8
        ld d, WAY_W             ;  8
        ld a, b                 ;  5
        or a                    ;  5
        jr z, .out              ; 13, or 8  at the left edge: out
        dec b                   ;  5
        dec b                   ;  5
.right: bit 3, (hl)             ; 14  RIGHT
        jr nz, .x               ; 13, or 8
        ld d, WAY_E             ;  8
        ld a, b                 ;  5
        cp X_LAST               ;  8
        jr z, .out              ; 13, or 8  at the right edge: out
        inc b                   ;  5
        inc b                   ;  5
.x:     push bc                 ; 12
        call walled             ; 18  NZ: a wall there
        pop bc                  ; 11
        jr nz, .y               ; 13, or 8
        ld a, b                 ;  5
        ld (explorer + 1), a    ; 14  the new X
.y:     ld bc, (explorer)       ; 22  X as it is now, and Y
        ld hl, held             ; 11
        bit 0, (hl)             ; 14  UP
        jr nz, .down            ; 13, or 8
        ld d, WAY_N             ;  8
        ld a, c                 ;  5
        cp Y_FIRST              ;  8
        jr z, .out              ; 13, or 8  at the top: out
        dec c                   ;  5
        dec c                   ;  5
.down:  bit 1, (hl)             ; 14  DOWN
        jr nz, .w               ; 13, or 8
        ld d, WAY_S             ;  8
        ld a, c                 ;  5
        cp Y_LAST               ;  8
        jr z, .out              ; 13, or 8  at the bottom: out
        inc c                   ;  5
        inc c                   ;  5
.w:     push bc                 ; 12
        call walled             ; 18
        pop bc                  ; 11
        jr nz, .in              ; 13, or 8  a wall
        ld a, c                 ;  5
        ld (explorer), a        ; 14  the new Y
.in:    or a                    ;  5  no carry: still in the room
        ret                     ; 11
.out:   scf                     ;  5  the carry: out by D's way
        ret                     ; 11
"""

LEAVE = """
; leave: D = the way out -> the room on that side, the explorer at its edge
; on the side it comes in by, on the same line or column, and the flip.
; Uses A, DE, HL
leave:  ld a, d                 ;  5
        add a, a                ;  5
        add a, d                ;  5  three bytes a way
        add a, low ways         ;  8
        ld l, a                 ;  5
        ld h, high ways         ;  8  the table in one page
        ld a, (room)            ; 14
        add a, (hl)             ;  8
        ld (room), a            ; 14  the room on that side
        inc l                   ;  5
        ld e, (hl)              ;  8  0 for Y, 1 for X
        inc l                   ;  5
        ld a, (hl)              ;  8  the edge it comes in at
        ld d, 0                 ;  8
        ld hl, explorer         ; 11
        add hl, de              ; 12
        ld (hl), a              ;  8
        ld a, FLIP              ;  8
        jp go                   ; 11
"""

UNPACK = """
; unpack: A = a room -> its runs, from the table rooms in the cartridge's
; second half, into rows 1 to 23 of the copy of the names. A run is a byte:
; the tile in bits 7 to 5, its cells less one in bits 4 to 0; no run goes
; past the end of a row, so that a run that ends a page of the copy ends a
; row too. Uses A, BC, DE, HL
unpack: add a, a                ;  5  two bytes a room
        ld l, a                 ;  5
        ld h, high rooms        ;  8  the table at the start of a page
        ld a, (hl)              ;  8
        inc l                   ;  5
        ld h, (hl)              ;  8
        ld l, a                 ;  5  HL: the room's runs
        ld de, names + 32       ; 11  DE: row 1 of the copy
.run:   ld a, (hl)              ;  8  a run
        inc hl                  ;  7
        ld c, a                 ;  5
        and 31                  ;  8
        ld b, a                 ;  5
        inc b                   ;  5  B: its cells
        ld a, c                 ;  5
        rlca                    ;  5
        rlca                    ;  5
        rlca                    ;  5
        and 7                   ;  8  A: its tile, the name
.cell:  ld (de), a              ;  8
        inc e                   ;  5  Z: the end of a page of the copy
        djnz .cell              ; 14, or 9
        jr nz, .run             ; 13, or 8
        inc d                   ;  5  the next page
        ld a, d                 ;  5
        cp high (names + 768)   ;  8
        jr nz, .run             ; 13, or 8
        ret                     ; 11  the room's 736 cells
"""

FLIP_RT = """
; flip0: THE ROOM CHANGES. Its runs unpacked into the copy of the names, its
; name and the rooms seen posted for row 0, and the whole page left for the
; next frame's sends, which go ahead of the beam
flip0:  ld a, (room)            ; 14
        call unpack             ; 18  rows 1 to 23 of the copy
        call rname              ; 18  row 0: its name
        call visit              ; 18  and the rooms seen
        ld hl, names + 32       ; 11
        ld de, GAME_R4 << 8 | GAME_R3 ; 11
        jp page                 ; 11  for the next sends

; flip1: the page sent: the play again
flip1:  ld a, PLAY              ;  8
        jp go                   ; 11

; rname: the room's name, its column's letter and its row's digit, posted
; for row 0. Uses A, BC, DE, HL
rname:  ld a, (room)            ; 14
        and 3                   ;  8
        add a, 'A'              ;  8
        ld hl, names + ROOM_AT  ; 11
        call post               ; 18
        ld a, (room)            ; 14
        rrca                    ;  5
        rrca                    ;  5
        and 3                   ;  8
        add a, '1'              ;  8
        ld hl, names + ROOM_AT + 1 ; 11
        jp post                 ; 11

; visit: the room seen: the first time, one more seen, posted, and fresh
; for play1 to make its picture. Uses A, BC, DE, HL
visit:  ld a, (room)            ; 14
        ld hl, been             ; 11
        add a, l                ;  5
        ld l, a                 ;  5  been in one page
        xor a                   ;  5
        ld (fresh), a           ; 14
        or (hl)                 ;  8
        ret nz                  ; 12, or 6  seen before
        inc (hl)                ; 12  seen now
        inc a                   ;  5
        ld (fresh), a           ; 14
        ld a, (seen)            ; 14
        add a, 1                ;  8
        daa                     ;  5  one more, in BCD
        ld (seen), a            ; 14
        ld hl, names + SEEN_AT  ; 11
        jp post2                ; 11  its two digits
"""

PLAY_RT = """
; play0: no steps owed yet, and no keys pressed
play0:  ld hl, 0                ; 11
        ld (due), hl            ; 17
        ld a, (held)            ; 14
        ld (was), a             ; 14
        ret                     ; 11

; play1: THE FRAME OF THE PLAY. A room seen for the first time gets its
; picture for the map, a frame of its own; M or button B pressed shows the
; map; else, for each step owed, a step of the explorer, and out of the room
; when a step goes through a door. Uses every register but IY
play1:  ld a, (fresh)           ; 14
        or a                    ;  5
        jr z, .keys             ; 13, or 8
        call mini               ; 18  its picture
        jp play0                ; 11  and the frame counts as none
.keys:  call presses            ; 18
        and $20                 ;  8  M or button B
        jr nz, tomap            ; 13, or 8
        call paced              ; 18  B: the steps owed (chapter 44)
.step:  push bc                 ; 12
        call walk               ; 18  carry: out, by D's way
        pop bc                  ; 11
        jp c, leave             ; 11  through a door
        djnz .step              ; 14, or 9
        ret                     ; 11
tomap:  ld a, MAP               ;  8
        jp go                   ; 11
"""


MINI = """
; mini: the room's picture for the map, from the copy of the names, rows 1
; to 23: a bit a cell, 1 for a wall, eight cells a byte, four bytes a row,
; into minis, and a row of none under them; then sent to its names in its
; third of the VRAM, where the play's screen never looks. Uses every
; register but IY
mini:   xor a                   ;  5
        ld (fresh), a           ; 14  made now
        ld a, (room)            ; 14
        call picat              ; 18  DE: the room's picture in minis
        push de                 ; 12
        ld hl, names + 32       ; 11  the copy's row 1
        ld c, 23 * 4            ;  8  rows 1 to 23, four bytes each
.byte:  DUP 8                   ; sjasmplus writes the next four lines 8 times
        ld a, (hl)              ;  8  a cell
        add a, $100 - BRICK     ;  8  carry: BRICK or more, a wall
        rl b                    ; 10  into the byte
        inc hl                  ;  7
        EDUP
        ld a, b                 ;  5
        ld (de), a              ;  8
        inc de                  ;  7
        dec c                   ;  5
        jr nz, .byte            ; 13, or 8
        xor a                   ;  5  row 24, under the room
        ld b, 4                 ;  8
.none:  ld (de), a              ;  8
        inc de                  ;  7
        djnz .none              ; 14, or 9
        ld a, (room)            ; 14
        add a, a                ;  5  two bytes a room
        add a, low picvram      ;  8
        ld l, a                 ;  5
        ld h, high picvram      ;  8  the table in one page
        ld e, (hl)              ;  8
        inc l                   ;  5
        ld d, (hl)              ;  8  DE: its names' shapes in its third
        pop hl                  ; 11  HL: the picture
; picture: HL = a room's picture in minis, DE = the VRAM address of the
; shapes of its first name, plus $4000 for writing -> its 12 names' 96 bytes
; sent: a name's eight lines are a column of the picture, eight of its
; bytes, four apart. Uses A, BC, DE, HL
picture: di                     ;  5
        ld a, e                 ;  5
        out (VDP_CTRL), a       ; 12
        ld a, d                 ;  5
        out (VDP_CTRL), a       ; 12  the address
        ei                      ;  5
        ld c, VDP_DATA          ;  8
        ld e, 3                 ;  8  three rows of names
.rowof: ld d, 4                 ;  8  four names in a row
.name:  push hl                 ; 12  its first line
        ld b, 8                 ;  8  eight lines
.line:  outi                    ; 18
        inc hl                  ;  7
        inc hl                  ;  7
        inc hl                  ;  7  the line below: four bytes on
        jp nz, .line            ; 11
        pop hl                  ; 11
        inc hl                  ;  7  the next name: a byte on
        dec d                   ;  5
        jr nz, .name            ; 13, or 8
        ld a, l                 ;  5
        add a, 32 - 4           ;  8  the next row of names: eight lines on
        ld l, a                 ;  5
        jr nc, .page            ; 13, or 8
        inc h                   ;  5
.page:  dec e                   ;  5
        jr nz, .rowof           ; 13, or 8
        ret                     ; 11

; picat: A = a room -> DE: its picture in minis, 96 bytes a room. Uses A,
; DE, HL
picat:  ld l, a                 ;  5
        ld h, 0                 ;  8
        add hl, hl              ; 12
        add hl, hl              ; 12
        add hl, hl              ; 12
        add hl, hl              ; 12
        add hl, hl              ; 12  x 32
        ld d, h                 ;  5
        ld e, l                 ;  5
        add hl, hl              ; 12  x 64
        add hl, de              ; 12  x 96
        ld de, minis            ; 11
        add hl, de              ; 12
        ex de, hl               ;  5
        ret                     ; 11
"""

MAP_RT = """
; map0: THE MAP. The explorer's Y kept and the explorer hidden, the map's
; page built in mapn and left for the next frame's sends, with a set of
; shapes and colours for each third
map0:   ld a, (explorer)        ; 14
        ld (keepy), a           ; 14
        ld a, $D0               ;  8
        ld (explorer), a        ; 14  the end of the sprites: none shown
        call mapbuild           ; 18
        ld hl, mapn             ; 11
        ld de, MAP_R4 << 8 | MAP_R3 ; 11
        jp page                 ; 11

; map1: M or button B pressed again: the explorer back, the room's page
; left for the next sends, and the play again
map1:   call presses            ; 18
        and $20                 ;  8  M or button B
        ret z                   ; 12, or 6
        ld a, (keepy)           ; 14
        ld (explorer), a        ; 14
        ld hl, names + 32       ; 11
        ld de, GAME_R4 << 8 | GAME_R3 ; 11
        call page               ; 18
        ld a, PLAY              ;  8
        jp go                   ; 11

; mapbuild: the map's 736 names in mapn: its page from the cartridge, then
; for each room seen its 4 x 3 names, the explorer's room's from CURRENT,
; whose shapes in that room's third get its picture now. Uses every
; register but IY
mapbuild: ld hl, mapbase        ; 11  the map's page, in the second half
        ld de, mapn             ; 11
        ld bc, 736              ; 11
        ldir                    ; 23 a byte, 18 the last
        ld c, 0                 ;  8  room 0
.room:  ld hl, been             ; 11
        ld a, l                 ;  5
        add a, c                ;  5
        ld l, a                 ;  5  been in one page
        ld a, (hl)              ;  8
        or a                    ;  5
        jr z, .next             ; 13, or 8  not seen: dark
        ld a, (room)            ; 14
        cp c                    ;  5
        ld b, CURRENT           ;  8
        jr z, .put              ; 13, or 8  the explorer's room
        ld hl, mapnm            ; 11
        ld a, l                 ;  5
        add a, c                ;  5
        ld l, a                 ;  5
        ld b, (hl)              ;  8  B: the room's first name
.put:   ld hl, mapat            ; 11
        ld a, c                 ;  5
        add a, a                ;  5
        add a, l                ;  5
        ld l, a                 ;  5
        ld a, (hl)              ;  8
        inc l                   ;  5
        ld h, (hl)              ;  8
        ld l, a                 ;  5  HL: its first cell in mapn
        call put4               ; 18  its three rows of four names
        call put4               ; 18
        call put4               ; 18
.next:  inc c                   ;  5
        ld a, c                 ;  5
        cp 16                   ;  8
        jr nz, .room            ; 13, or 8
        ld a, (room)            ; 14  the explorer's room's picture, for CURRENT
        call picat              ; 18  DE: in minis
        ld a, (room)            ; 14
        add a, a                ;  5
        add a, low curvram      ;  8
        ld l, a                 ;  5
        ld h, high curvram      ;  8
        ld a, (hl)              ;  8
        inc l                   ;  5
        ld h, (hl)              ;  8
        ld l, a                 ;  5  HL: CURRENT's shapes in its third
        ex de, hl               ;  5
        jp picture              ; 11

; put4: B = a name, HL = a cell of mapn -> B to B + 3 in it and the three
; after it; HL the cell below, B the name after. Uses B, DE, HL
put4:   ld (hl), b              ;  8
        inc hl                  ;  7
        inc b                   ;  5
        ld (hl), b              ;  8
        inc hl                  ;  7
        inc b                   ;  5
        ld (hl), b              ;  8
        inc hl                  ;  7
        inc b                   ;  5
        ld (hl), b              ;  8
        inc b                   ;  5
        ld de, 32 - 3           ; 11
        add hl, de              ; 12  the row below
        ret                     ; 11
"""

STATES_RT = """
; title0: the title's 768 names at 29 T-states a name (chapter 20), and the
; explorer below its wall
title0: di                      ;  5
        VRAM_WRITE $1800        ; 40
        ei                      ;  5
        ld hl, tnames           ; 11  in the second half
        ld bc, VDP_DATA         ; 11  B: 0, a run of 256; C: the port
        ld d, 3                 ;  8  three runs
.run:   outi                    ; 18
        jp nz, .run             ; 11
        dec d                   ;  5
        jr nz, .run             ; 13, or 8
        ld hl, tcopy            ; 11  the explorer, and the end
        ld de, copy             ; 11
        ld bc, 5                ; 11
        ldir                    ; 23 a byte, 18 the last
        ret                     ; 11

; title1: SPACE or button A held? A walk begins, with the flip into its
; first room
title1: ld a, (held)            ; 14  isr read them
        and $10                 ;  8  SPACE, button A
        ret nz                  ; 12, or 6
pressed: call setup             ; 18  none seen, the gate hall
        ld a, FLIP              ;  8
        jp go                   ; 11

; setup: a new walk. No rooms seen, none queued, the explorer in the gate
; hall at its first place
setup:  xor a                   ;  5
        ld (seen), a            ; 14
        ld (queued), a          ; 14
        ld hl, been             ; 11
        ld b, 16                ;  8
.none:  ld (hl), a              ;  8
        inc l                   ;  5
        djnz .none              ; 14, or 9
        ld a, START             ;  8
        ld (room), a            ; 14
        ld hl, first            ; 11  the explorer's first place
        ld de, copy             ; 11
        ld bc, 5                ; 11
        ldir                    ; 23 a byte, 18 the last
        ret                     ; 11

; sets: the shapes and colours of every name into each third's tables, the
; display off: the tiles, the dark, chapter 30's characters, the colours of
; the rooms' pictures, black on white, and of the explorer's room's, black
; on cyan. Uses A, BC, DE, HL
sets:   ld de, $0000 | $4000    ; 11  third 0's shapes
.third: ld hl, vshapes          ; 11
        call set2k              ; 18
        ld a, d                 ;  5
        add a, $20              ;  8  its colours, $2000 on
        ld d, a                 ;  5
        ld hl, vcolours         ; 11
        call set2k              ; 18
        ld a, d                 ;  5
        sub $20 - 8             ;  8  the next third's shapes, $800 on
        ld d, a                 ;  5
        cp $18 | $40            ;  8
        jr nz, .third           ; 13, or 8
        ret                     ; 11

; set2k: HL = 2,048 bytes, DE = a VRAM address plus $4000 -> sent, with the
; display off. Uses A, BC, HL
set2k:  ld a, e                 ;  5
        out (VDP_CTRL), a       ; 12
        ld a, d                 ;  5
        out (VDP_CTRL), a       ; 12  the address
        ld bc, VDP_DATA         ; 11  B: 0, a run of 256
        ld a, 8                 ;  8  eight runs
.run:   otir                    ; 23 a byte, 18 the last
        dec a                   ;  5
        jr nz, .run             ; 13, or 8
        ret                     ; 11
"""

POST = gen43.PICK[gen43.PICK.index("; post:"):]
POST2 = gen44.ROUNDS[gen44.ROUNDS.index("; post2:"):gen44.ROUNDS.index("; addten:")]
assert POST.startswith("; post:") and POST2.startswith("; post2:")


def setup_lines():
    """the cartridge's start: page 2 switched to its second half, the VDP,
    the RAM cleared, the machine's lines, the three sets, the explorer's
    patterns, mode 2, and the title"""
    return f"""init:   di
        ld sp, SYS_AREA
        call here               ; page 1's slot ID: this cartridge's (chapter 38)
        call setpage2           ; page 2 shows it too: the second half
        VDP_REG 1, $80          ; display off
        VDP_REG 0, $02          ; Graphic II
        VDP_REG 2, $06          ; names    $1800
        VDP_REG 3, GAME_R3      ; colours  $2000, one set for three thirds
        VDP_REG 4, GAME_R4      ; shapes   $0000, one set for three thirds
        VDP_REG 5, $36          ; sprite attributes $1B00
        VDP_REG 6, $07          ; sprite patterns   $3800
        VDP_REG 7, ${BORDER:02X}          ; border black
        VRAM_WRITE SAT          ; no sprites yet
        ld a, $D0
        out (VDP_DATA), a
        ld hl, VARS             ; the variables' page, all 0
        ld de, VARS + 1
        ld bc, 255
        ld (hl), 0
        ldir
        ld hl, names            ; and the copy of the names, the map's page
        ld de, names + 1        ; and the pictures
        ld bc, minis + 16 * 96 - names - 1
        ld (hl), 0
        ldir
""" + gen33.rate("lines", 262, 313) + """        call sets               ; the shapes and colours of the three thirds
        VRAM_WRITE SPAT         ; the explorer, patterns 0 to 3
        ld hl, sprites
        ld bc, 32 << 8 | VDP_DATA
        otir
""" + im2("isr") + """        ld a, TITLE
        call go                 ; the first state: title0 ends with EI
        di
        in a, (VDP_CTRL)        ; no signal left over (chapter 39)
        VDP_REG 1, $E2          ; display on, the frame's signal, sprites 16 x 16
"""


def word_rows(words, per=8):
    return "".join("        dw " + ", ".join(f"${w:04X}" for w in words[i:i + per]) + "\n"
                   for i in range(0, len(words), per))


def mapat():
    return [MAPN_AT + 32 * (map_cell(k)[1] - 1) + map_cell(k)[0] for k in range(ROOMS)]


def picvram():
    return [third_of(k) * 0x800 + 8 * mini_name(k) | 0x4000 for k in range(ROOMS)]


def curvram():
    return [third_of(k) * 0x800 + 8 * CURRENT | 0x4000 for k in range(ROOMS)]


def data():
    return ("""codeend:                        ; the code ends here
        ALIGN 16
starts: dw title0, play0, flip0, map0 ; each state's first frame
frames: dw title1, play1, flip1, map1 ; and every frame of it
ways:                           ; leave's: the room's change, Y or X, the edge
""" + db_rows(ways(), 3) +
            "        ALIGN 32\nmapat:                          ; each room's first cell in mapn\n" +
            word_rows(mapat()) +
            "picvram:                        ; each room's names' shapes in its third, + $4000\n" +
            word_rows(picvram()) +
            "curvram:                        ; and those of CURRENT in its third, + $4000\n" +
            word_rows(curvram()) +
            "mapnm:                          ; each room's first name on the map\n" +
            db_rows([mini_name(k) for k in range(ROOMS)]) +
            "first:                          ; the explorer at its first place, and the end\n" +
            db_rows(first_copy()) +
            "tcopy:                          ; and on the title\n" + db_rows(title_copy()) +
            "sprites:                        ; the explorer, 16 x 16 (chapter 26)\n" +
            db_rows(SPRITE_PATTERNS) +
            "        ALIGN 16\nkbdjoy:                         ; register 14's bits 0-3 for "
            "the cursor keys\n" + db_rows(gen35.kbd_table(), 16))


def second_half():
    """the cartridge's second half, page 2 from $8000: the keep's rooms, the
    title's page, the map's page and the VDP's two tables"""
    out = ["""; ---------------------------------------------------------------- the second half
; page 2, from $8000: setpage2 shows it from INIT on
rooms:                          ; each room's runs: the table, at a page's start
""" + word_rows([0] * 0, 8)]
    out[0] += "        dw " + ", ".join(f"room{k}" for k in range(8)) + "\n"
    out[0] += "        dw " + ", ".join(f"room{k}" for k in range(8, 16)) + "\n"
    for k in range(ROOMS):
        out.append(f"room{k}:                          ; {room_name(k)}: {ROOM_TITLES[k]}, "
                   f"{len(RUN_BYTES[k])} runs\n"[:80] if False else
                   f"room{k}:{' ' * (24 - len(f'room{k}:'))}; {room_name(k)}: {ROOM_TITLES[k]}, "
                   f"{len(RUN_BYTES[k])} runs\n" + db_rows(RUN_BYTES[k], 12))
    out.append("tnames:                         ; the title's 768 names\n" + db_rows(title_names(), 16))
    out.append("mapbase:                        ; the map's page, rows 1 to 23\n" + db_rows(map_names(), 16))
    out.append("vshapes:                        ; a third's shapes: tiles, dark, characters\n" +
               db_rows(shape_set(), 16))
    out.append("vcolours:                       ; and its colours\n" + db_rows(colour_set(), 16))
    return "".join(out)


SAY = {
    "game": """; LANTERN KEEP, its world: an explorer walks the sixteen rooms of a keep,
; through the doors between them. A room is unpacked from its runs in the
; cartridge's second half, and shown whole the frame after, ahead of the
; beam; M or button B shows a map of the rooms seen.
""",
    "torn": """; WHERE IT BREAKS. game.asm whose flip0 sends the page itself, as soon as
; the room is unpacked, instead of leaving it to the next frame's sends.
""",
}
WHAT = {"game": "LANTERN KEEP, its world", "torn": "a page sent behind the beam"}
HEAD = '''; {name}.asm -- chapter 45: {what}
; generated by gen45.py
        INCLUDE "msx.inc"
        OUTPUT "{name}.rom"
        ORG $4000
        CART_HEADER init
VARS    EQU RAM_START + $100    ; the program's variables: the code is in ROM
'''


def flip_rt(name):
    if name == "game":
        return FLIP_RT
    old = """        ld hl, names + 32       ; 11
        ld de, GAME_R4 << 8 | GAME_R3 ; 11
        jp page                 ; 11  for the next sends"""
    assert FLIP_RT.count(old) == 1
    return FLIP_RT.replace(
        """; flip0: THE ROOM CHANGES. Its runs unpacked into the copy of the names, its
; name and the rooms seen posted for row 0, and the whole page left for the
; next frame's sends, which go ahead of the beam""",
        """; flip0: THE ROOM CHANGES. Its runs unpacked into the copy of the names, its
; name and the rooms seen posted for row 0, and WHERE IT BREAKS: the whole
; page sent now, behind the beam""").replace(old, """        ld hl, names + 32       ; 11
        ld de, GAME_R4 << 8 | GAME_R3 ; 11
        jp show                 ; 11  now""")


def program(name, onethird=False, pic_flip1=False):
    """the program NAME; the workshop's variants show the map with the
    play's one set of shapes, ONETHIRD; or make a room's picture in flip1,
    the frame of its page, PIC_FLIP1"""
    flip, play, maps = flip_rt(name), PLAY_RT, MAP_RT
    if onethird:
        old = """        call mapbuild           ; 18
        ld hl, mapn             ; 11
        ld de, MAP_R4 << 8 | MAP_R3 ; 11"""
        assert maps.count(old) == 1
        maps = maps.replace(old, old.replace("MAP_R4 << 8 | MAP_R3", "GAME_R4 << 8 | GAME_R3"))
    if pic_flip1:
        old = """flip1:  ld a, PLAY              ;  8"""
        assert flip.count(old) == 1
        flip = flip.replace(old, """flip1:  ld a, (fresh)           ; 14
        or a                    ;  5
        call nz, mini           ; 18, or 11  a new room's picture, now
        ld a, PLAY              ;  8""")
    parts = (ISR + INPUT + KEYS + gen35.JOY + SENDS + PAGE + PRESSES + gen44.PACED + WALK +
             gen39.CELL + gen44.WALLED + LEAVE + UNPACK + flip + play + MINI + maps +
             STATES_RT + POST + POST2 + gen38.HERE_OWN + gen38.PAGE2 + gen38.SUBREG)
    body = setup_lines() + MAIN
    src = (HEAD.format(name=name, what=WHAT[name]) + '        INCLUDE "bios.inc"\n' + RAM +
           "SSLOT   EQU $FFFF               ; the secondary slot register, in page 3\n" + CONSTS + IM2 +
           SAY[name] + tidy(body + parts) + data() +
           "        ASSERT $ <= $8000, the first half is too long\n"
           "        ds $8000 - $, $FF       ; the first half ends at $7FFF\n" + second_half() +
           "romend:                         ; the cartridge's last byte, and one\n"
           "        ASSERT low rooms == 0 && rooms == $8000\n"
           "        ASSERT $ <= $C000, the program is longer than the cartridge\n"
           "        ds $C000 - $, $FF       ; the rest of the second half\n")
    return src


PROGRAMS = ["game", "torn"]


def main():
    for name in PROGRAMS:
        with open(os.path.join(HERE, f"{name}.asm"), "w") as f:
            f.write(program(name))
    print(" ".join(f"{n}.asm" for n in PROGRAMS))


if __name__ == "__main__":
    main()
