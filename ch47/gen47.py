#!/usr/bin/env python3
"""gen47.py - the programs of chapter 47: three games, sketched.

    python3 gen47.py && ./build.sh

    cave.asm   A SHOOTER IN A CAVE: a ceiling, rows 1 to 4, and a ground,
               rows 17 to 23, a pixel to the left every frame, by chapter
               29's pairs: straight after HALT the patterns of the pairs of
               tiles side by side are rewritten at the new shift, and every
               eighth frame the next window's names go to the name table not
               shown; a ship, a sprite, flies in the sky between, as the
               demo's keys say
    jump.asm   A RUNNER THAT JUMPS: ledges of bricks on a Graphic II screen
               whose names run 0 to 255 in each third (chapter 22); a runner,
               a sprite, running and jumping as the demo's keys say, its
               height and its speed in 8.8; a landing on the top of a
               ledge's cell; and a dot at its feet every frame, with chapter
               25's plot, which draws its path
    maze.asm   A MAZE SEEN FROM INSIDE: the corridor ahead in perspective,
               four cells deep, drawn into a buffer laid out as the patterns
               (chapter 25); in the next frame sent to the window's set of
               patterns not shown, and in the one after shown by turning the
               window's 144 names to it; a map, with an arrow, a sprite,
               where the explorer stands; the demo's keys follow the
               right-hand wall

Nothing reads the keyboard: pad gives held, as chapter 43's input does, a 0
for each key held, from the demo: pairs of bytes, frames and keys, with a 0
at the end, after which the demo starts again. The frame is chapter 43's:
isr counts the frames in mode 2; straight after HALT, sends does what the
beam must not catch; then run does the frame's work. Every line of this
chapter's own routines carries its price, the MSX's T-states, which
meas47.py checks with walk.py and the debugger. build.sh assembles with
--syntax=bFw.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
for ch in ("tools", "ch25", "ch26", "ch39", "ch41", "ch43"):
    sys.path.insert(0, os.path.join(REPO, ch))
from asmparts import HEAD, CART_END, IM2, im2  # noqa: E402
from gen26 import tidy, db_rows, big  # noqa: E402  (chapter 26)
import gen25  # noqa: E402  (chapter 25: vaddr, masks, plot)
import gen39  # noqa: E402  (chapter 39: the brick)
import gen41  # noqa: E402  (chapter 41: xorshift)
import gen43  # noqa: E402  (chapter 43: isr)
sys.path.insert(0, HERE)

EU, JP = "MSXBOOK_EU16", "MSXBOOK_JP16"
MACHINES = [EU, JP]
BIOS = '        INCLUDE "bios.inc"\n'
BLACK, LIGHT_GREEN, DARK_BLUE, DARK_RED, CYAN, WHITE = 1, 3, 4, 6, 7, 15
FRAMES = 600                # the loops each film is measured for

# held's bits, as chapter 43's input gives them: a 0 for each key held
UP, DOWN, LEFT, RIGHT, FIRE = 1, 2, 4, 8, 16
KEY_NAMES = {UP: "UP", DOWN: "DOWN", LEFT: "LEFT", RIGHT: "RIGHT", FIRE: "SPACE"}


def held_of(keys):
    """keys, a 1 for each key held -> held, a 0 for each"""
    return ~keys & 0xFF


def rows16(art):
    assert len(art) == 16 and all(len(r) == 16 for r in art)
    return [int(r.replace("#", "1").replace(".", "0"), 2) for r in art]


def rows8(*lines):
    return [int(line.replace("#", "1").replace(".", "0"), 2) for line in lines]


def compress(keys):
    """keys, one a frame, a 1 for each held -> the demo's pairs: frames, held"""
    out = []
    for k in keys:
        if out and out[-1][1] == k and out[-1][0] < 255:
            out[-1][0] += 1
        else:
            out.append([1, k])
    return [(n, held_of(k)) for n, k in out]


def demo_data(pairs, what):
    out = [f"; the demo, {what}: pairs of frames and keys, a 0 for each key held,",
           "; and a 0 at the end"]
    for i, (n, held) in enumerate(pairs):
        keys = ~held & 0xFF
        names = " ".join(v for b, v in KEY_NAMES.items() if keys & b) or "none"
        lab = "demo:   " if i == 0 else "        "
        out.append(f"{lab}db {n}, %{held:08b}".ljust(32) + f"; {names}")
    out.append("        db 0                    ; the end: the first pair again")
    return "\n".join(out) + "\n"


def head(name, what):
    return HEAD.format(name=name, chapter=47, what=what) + BIOS


# ================================================================ common
RAM = """stat    EQU VARS                ; the status isr read
ticks   EQU VARS + 1            ; frames counted by isr, two bytes
held    EQU VARS + 3            ; the keys of the frame: a 0 for each held
dleft   EQU VARS + 4            ; the frames left of the demo's pair
dnext   EQU VARS + 5            ; the demo's next pair, two bytes
copy    EQU VARS + $20          ; the sprites' attributes: Y, X, pattern, colour
SAT     EQU $1B00               ; the sprites' attributes in the VRAM
SPAT    EQU $3800               ; and their patterns
"""
VARS_AT = 0xC100
COPY_AT = VARS_AT + 0x20

MAIN = """main:   ei
frame:  halt                    ; isr: the status kept, the frame counted
woke:   call sends              ; 18  what the beam must not catch
sent:   call run                ; 18  the frame's work
ran:    jr frame                ; 13
"""

PAD = """
; pad: the demo's keys for this frame -> A and held, as chapter 43's input
;      gives them, a 0 for each key held. The demo is pairs of bytes, frames
;      and keys, with a 0 at its end, after which it starts again. Uses A, HL
pad:    ld hl, dleft            ; 11
        dec (hl)                ; 12  a frame fewer of these keys
        jr nz, .same            ; 13, or 8
        ld hl, (dnext)          ; 17  none left: the next pair
        ld a, (hl)              ;  8  its frames
        or a                    ;  5
        jr nz, .pair            ; 13, or 8
        ld hl, demo             ; 11  the end: the first pair again
        ld a, (hl)              ;  8
.pair:  ld (dleft), a           ; 14
        inc hl                  ;  7
        ld a, (hl)              ;  8  its keys
        ld (held), a            ; 14
        inc hl                  ;  7
        ld (dnext), hl          ; 17
        ret                     ; 11
.same:  ld a, (held)            ; 14  the same keys as before
        ret                     ; 11
"""

SENDS_SAT = """        VRAM_WRITE SAT          ; 40
        ld hl, copy             ; 11
        ld bc, 5 << 8 | VDP_DATA ; 11  the sprite and the end
        otir                    ; 23 a byte, 18 the last
"""


def start_lines(regs, border):
    """the cartridge's first lines: the VDP's registers, the display off, the
    variables' page cleared"""
    r = "\n".join(f"        VDP_REG {n}, ${v:02X}          ; {say}" for n, v, say in regs)
    return f"""init:   di
        ld sp, SYS_AREA
        VDP_REG 1, $80          ; display off
{r}
        VDP_REG 7, ${border:02X}          ; the border
        VRAM_WRITE SAT          ; no sprites yet
        ld a, $D0
        out (VDP_DATA), a
        ld hl, VARS             ; the variables' page, all 0
        ld de, VARS + 1
        ld bc, 255
        ld (hl), 0
        ldir
        ld a, 1
        ld (dleft), a           ; the demo's first pair at the first frame
        ld hl, demo
        ld (dnext), hl
        ld hl, first            ; the sprite's attributes at the start
        ld de, copy
        ld bc, 5
        ldir
"""


def end_lines(r1):
    return im2("isr") + f"""        in a, (VDP_CTRL)        ; no signal left over
        VDP_REG 1, ${r1:02X}          ; display on, the frame's signal
"""


GRAPHIC2_ONE = [(0, 0x02, "Graphic II"), (2, 0x06, "names    $1800"),
                (3, 0x9F, "colours  $2000, one set for three thirds"),
                (4, 0x00, "shapes   $0000, one set for three thirds"),
                (5, 0x36, "sprite attributes $1B00"), (6, 0x07, "sprite patterns   $3800")]
GRAPHIC2_THREE = [(0, 0x02, "Graphic II"), (2, 0x06, "names    $1800"),
                  (3, 0xFF, "colours  $2000, a set for each third"),
                  (4, 0x03, "shapes   $0000, a set for each third"),
                  (5, 0x36, "sprite attributes $1B00"), (6, 0x07, "sprite patterns   $3800")]


def program(name, what, say, ram, consts, body, routines, data):
    return (head(name, what) + RAM + ram + consts + IM2 + say +
            tidy(body + MAIN + gen43.ISR + PAD + routines) + data + CART_END)


# ================================================================ the cave
W = 64                      # the world's columns of tiles, round: two screens
KNOT = 4                    # a height every four columns, a row a column between
CEIL_ROWS = (1, 4)          # the ceiling's rows of cells: lines 8 to 39
GROUND_ROWS = (17, 23)      # the ground's: lines 136 to 191
SCROLL_ROWS = list(range(CEIL_ROWS[0], CEIL_ROWS[1] + 1)) + \
    list(range(GROUND_ROWS[0], GROUND_ROWS[1] + 1))
CEIL_H = (1, 4)             # the ceiling's last row of rock, at a column's edge
GROUND_H = (17, 21)         # the ground's first row
CAVE_SEED = 1
SHIP_AT = (40, 80)          # the ship's first place: x, its top line
SHIP_X = (16, 160)          # x from 16 to 160
SHIP_Y = (40, 120)          # its top line from 40 to 120: lines 40 to 135, the sky
CEIL_C = DARK_BLUE << 4 | BLACK     # the ceiling's rock, dark blue on black
GROUND_C = LIGHT_GREEN << 4 | BLACK  # the ground's, light green
SHIP_COLOUR = WHITE
CAVE_BORDER = BLACK


def knots(seed, n, lo, hi):
    """N heights from LO to HI, from chapter 41's xorshift; and its state"""
    x, out = seed, []
    for _ in range(n):
        x = gen41.xorshift(x)
        out.append(lo + (x >> 8) % (hi - lo + 1))
    return out, x


def edges(ks):
    """the height at each column's left edge: from each knot to the next, a
    row a column, then level"""
    out = []
    for k, a in enumerate(ks):
        b, h = ks[(k + 1) % len(ks)], a
        for _ in range(KNOT):
            out.append(h)
            h += (h < b) - (h > b)
        assert h == b
    return out


_ck, _x = knots(CAVE_SEED, W // KNOT, *CEIL_H)
_gk, _x = knots(_x, W // KNOT, *GROUND_H)
CEIL = edges(_ck)           # the ceiling's last row of rock at each column's left edge
GROUND = edges(_gk)         # the ground's first row

ROCK = rows8("########", "##.#####", "########", "######.#",
             "########", "#.######", "########", "####.###")
FULL = [0xFF] * 8
CAVE_TILES = {              # name: shape, colours
    "sc": ([0] * 8, CEIL_C),                    # the sky in the ceiling's rows
    "rc": (ROCK, CEIL_C),                       # the ceiling's rock
    "bc": (ROCK[:7] + [0xFF], CEIL_C),          # its last row, level
    "dc": ([0xFF >> i for i in range(8)], CEIL_C),          # deeper to the right
    "uc": ([(0xFF << i) & 0xFF for i in range(8)], CEIL_C),  # shallower
    "sg": ([0] * 8, GROUND_C),                  # the sky in the ground's rows
    "rg": (ROCK, GROUND_C),                     # the ground's rock
    "tg": ([0xFF] + ROCK[1:], GROUND_C),        # its top row, level
    "ug": ([0xFF >> (7 - i) for i in range(8)], GROUND_C),  # higher to the right
    "dg": ([(0xFF << (7 - i)) & 0xFF for i in range(8)], GROUND_C),  # lower
}
SKIES = ("sc", "sg")


def cave_tile(r, c):
    """the tile of row R, column C of the world"""
    if CEIL_ROWS[0] <= r <= CEIL_ROWS[1]:
        a, b = CEIL[c % W], CEIL[(c + 1) % W]
        if a == b:
            return "rc" if r < a else "bc" if r == a else "sc"
        if b == a + 1:
            return "rc" if r <= a else "dc" if r == a + 1 else "sc"
        return "rc" if r < a else "uc" if r == a else "sc"
    if GROUND_ROWS[0] <= r <= GROUND_ROWS[1]:
        a, b = GROUND[c % W], GROUND[(c + 1) % W]
        if a == b:
            return "sg" if r < a else "tg" if r == a else "rg"
        if b == a - 1:
            return "sg" if r < a - 1 else "ug" if r == a - 1 else "rg"
        return "sg" if r < a else "dg" if r == a else "rg"
    return None


def cave_pairs():
    """the pairs of tiles side by side in the scrolling rows, in the order
    met, two skies left out (name 0, the sky, is theirs); and for each
    scrolling row the name of the pair at each column, 0 for the sky's"""
    pairs, pmap = [], []
    for r in SCROLL_ROWS:
        out = []
        for c in range(W):
            p = (cave_tile(r, c), cave_tile(r, c + 1))
            if p[0] in SKIES and p[1] in SKIES:
                out.append(0)
                continue
            if p not in pairs:
                pairs.append(p)
            out.append(pairs.index(p) + 1)
        pmap.append(out)
    return pairs, pmap


PAIRS, PMAP = cave_pairs()
NP = len(PAIRS)
assert NP * 8 <= 255, NP


def shifted(a, b, s):
    """the 8 shape bytes of tile A and tile B side by side, S pixels on"""
    return [((ra << 8 | rb) << s >> 8) & 0xFF for ra, rb in zip(CAVE_TILES[a][0], CAVE_TILES[b][0])]


def pair_colours(a, b):
    """a pair takes its left tile's colours: the same as the right one's,
    since the ceiling's tiles share theirs and the ground's theirs"""
    assert CAVE_TILES[a][1] == CAVE_TILES[b][1]
    return [CAVE_TILES[a][1]] * 8


def cave_pixel(wx, y):
    """1 if the world's pixel (WX, Y) is rock: its tile's shape"""
    t = cave_tile(y >> 3, wx >> 3)
    return 0 if t is None else CAVE_TILES[t][0][y & 7] >> (7 - (wx & 7)) & 1


def ceiling_line(wx):
    """the first line of sky below the ceiling at world column WX"""
    y = 8 * CEIL_ROWS[0]
    while cave_pixel(wx % (8 * W), y):
        y += 1
    return y


def ground_line(wx):
    """the ground's first line of rock at world column WX"""
    y = 8 * GROUND_ROWS[1] + 7
    while cave_pixel(wx % (8 * W), y):
        y -= 1
    return y + 1


SHIP_ART = [
    "................",
    "..##............",
    "..###...........",
    "..####..........",
    "...#####........",
    "..#########.....",
    ".####...######..",
    ".####...#######.",
    ".##############.",
    ".#############..",
    "..#########.....",
    "...#####........",
    "..####..........",
    "..###...........",
    "..##............",
    "................"]
SHIP = rows16(SHIP_ART)


def ship_step(x, y, keys):
    """steer in Python: x and the top line, after the keys of a frame"""
    if keys & UP and y > SHIP_Y[0]:
        y -= 2
    if keys & DOWN and y < SHIP_Y[1]:
        y += 2
    if keys & LEFT and x > SHIP_X[0]:
        x -= 2
    if keys & RIGHT and x < SHIP_X[1]:
        x += 2
    return x, y


FLIGHT = [(20, DOWN | RIGHT), (12, RIGHT), (20, UP | RIGHT), (12, 0),
          (20, UP | LEFT), (12, LEFT), (20, DOWN | LEFT), (12, 0)]


def cave_keys():
    """the demo: a lap of the world, 512 frames, four times the same flight:
    down and up to the right, up and down to the left, back where it began"""
    keys = [k for _ in range(4) for n, k in FLIGHT for _ in range(n)]
    assert len(keys) == 8 * W
    x, y = SHIP_AT
    for k in keys:
        x, y = ship_step(x, y, k)
    assert (x, y) == SHIP_AT
    return keys, SHIP_AT[1]


CAVE_KEYS, CAVE_Y0 = cave_keys()
CAVE_DEMO = compress(CAVE_KEYS)

CAVE_RAM = """col     EQU VARS + 8            ; the window's column of the world, 0 to 63
shift   EQU VARS + 9            ; and its pixels on, 0 to 7
table   EQU VARS + 10           ; the name table shown: $18 or $1C
"""
CAVE_CONSTS = f"""W       EQU {W}                  ; the world's columns, round
NB      EQU {8 * NP}                 ; the pairs' patterns: {NP} of 8 bytes
X_MIN   EQU {SHIP_X[0]}                  ; the ship's X
X_MAX   EQU {SHIP_X[1]}
Y_MIN   EQU {SHIP_Y[0] - 1}                  ; its Y, a line above its top
Y_MAX   EQU {SHIP_Y[1] - 1}
"""

CAVE_SENDS = """
; sends: straight after HALT, before the paper: the ship's attributes, then
;        the pairs' patterns at the new shift; at shift 0, the table with the
;        next window shown, with R#2. Uses A, BC, HL
sends:  VRAM_WRITE SAT          ; 40
        ld hl, copy             ; 11
        ld bc, 5 << 8 | VDP_DATA ; 11  the ship and the end
        otir                    ; 23 a byte, 18 the last
show:   VRAM_WRITE $0008        ; 40  pair 1's pattern, the first
        ld a, (shift)           ; 14
        add a, a                ;  5  two bytes a shift
        add a, low stab         ;  8
        ld l, a                 ;  5
        ld h, high stab         ;  8  HL: the shift's place in stab
        ld a, (hl)              ;  8
        inc l                   ;  5
        ld h, (hl)              ;  8
        ld l, a                 ;  5  HL: the pairs at this shift
        ld b, NB                ;  8
        otir                    ; 23 a byte, 18 the last
        ld a, (shift)           ; 14
        or a                    ;  5
        ret nz                  ; 12, or 6  seven frames in eight, no more
        ld a, (table)           ; 14
        xor $18 ^ $1C           ;  8  the other table: the next window
        ld (table), a           ; 14
        rrca                    ;  5
        rrca                    ;  5  $06 or $07, R#2's
        out (VDP_CTRL), a       ; 12
        ld a, $80 | 2           ;  8
        out (VDP_CTRL), a       ; 12
        ret                     ; 11
"""

CAVE_RUN = """
; run: the frame's work: the demo's keys, the ship steered, the scroll.
;      Uses every register
run:    call pad                ; 18  A: the keys
        call steer              ; 18
        jp step                 ; 11  whose RET is run's

; steer: A = the keys -> the ship two pixels up, down, left or right for each
;        key held, kept in the sky. Uses A, B, HL
steer:  ld b, a                 ;  5
        ld hl, copy             ; 11  the ship's Y
        bit 0, b                ; 10  UP?
        jr nz, .down            ; 13, or 8
        ld a, (hl)              ;  8
        cp Y_MIN + 1            ;  8
        jr c, .down             ; 13, or 8  at the top
        sub 2                   ;  8
        ld (hl), a              ;  8
.down:  bit 1, b                ; 10  DOWN?
        jr nz, .left            ; 13, or 8
        ld a, (hl)              ;  8
        cp Y_MAX                ;  8
        jr nc, .left            ; 13, or 8  at the bottom
        add a, 2                ;  8
        ld (hl), a              ;  8
.left:  inc hl                  ;  7  its X
        bit 2, b                ; 10  LEFT?
        jr nz, .right           ; 13, or 8
        ld a, (hl)              ;  8
        cp X_MIN + 1            ;  8
        jr c, .right            ; 13, or 8  at the left
        sub 2                   ;  8
        ld (hl), a              ;  8
.right: bit 3, b                ; 10  RIGHT?
        ret nz                  ; 12, or 6
        ld a, (hl)              ;  8
        cp X_MAX                ;  8
        ret nc                  ; 12, or 6  at the right
        add a, 2                ;  8
        ld (hl), a              ;  8
        ret                     ; 11

; step: after a new table is shown, the next window's names written into the
;       other one; then a pixel on: shift, and at 8 the next column. Uses
;       every register
step:   ld a, (shift)           ; 14
        or a                    ;  5
        jr nz, .on              ; 13, or 8
        ld a, (col)             ; 14
        inc a                   ;  5
        and W - 1               ;  8  the next window's column, round
        call window             ; 18
.on:    ld hl, shift            ; 11
        ld a, (hl)              ;  8
        inc a                   ;  5
        and 7                   ;  8
        ld (hl), a              ;  8
        ret nz                  ; 12, or 6
        ld hl, col              ; 11  eight pixels: a column on
        ld a, (hl)              ;  8
        inc a                   ;  5
        and W - 1               ;  8
        ld (hl), a              ;  8
        ret                     ; 11

; window: A = a column -> the scrolling rows of the window at that column
;         into the name table not shown: rows 1 to 4, then 17 to 23, each
;         row's pairs in a page of pmap. Uses A, BC, DE, HL
window: ld e, a                 ;  5  E: the column
        ld l, a                 ;  5
        ld h, high pmap         ;  8  HL: row 1's pair there
        ld a, (table)           ; 14
        xor $18 ^ $1C           ;  8  the table not shown
        ld d, a                 ;  5  D: its high byte
        ld a, 32                ;  8
        out (VDP_CTRL), a       ; 12
        ld a, d                 ;  5
        or $40                  ;  8
        out (VDP_CTRL), a       ; 12  its row 1, for writing
        ld c, 4                 ;  8  four rows
        call names              ; 18
        ld a, low (32 * 17)     ;  8
        out (VDP_CTRL), a       ; 12
        ld a, d                 ;  5
        or high (32 * 17) | $40 ;  8
        out (VDP_CTRL), a       ; 12  its row 17
        ld c, 7                 ;  8  seven rows: on into names

; names: HL = a row's pair at the column E, C = rows -> C rows of 32 names,
;        one after another in the VRAM, 39 T-states a name. Uses A, BC, HL
names:  ld b, 32                ;  8
.name:  ld a, (hl)              ;  8
        out (VDP_DATA), a       ; 12
        inc l                   ;  5
        djnz .name              ; 14, or 9
        inc h                   ;  5  the next row's page
        ld l, e                 ;  5
        dec c                   ;  5
        jr nz, names            ; 13, or 8
        ret                     ; 11
"""


def cave_setup():
    return start_lines(GRAPHIC2_ONE, CAVE_BORDER) + f"""        VRAM_WRITE $0000        ; pattern 0, the sky
        ld c, VDP_DATA
        xor a
        ld b, 8
.sky:   out (c), a
        djnz .sky
        ld hl, shifts           ; and the pairs at shift 0
        ld b, NB
        otir
        VRAM_WRITE $2000        ; the sky's colours, and the pairs'
        ld b, 8
        ld a, ${CEIL_C:02X}
.skyc:  out (c), a
        djnz .skyc
        ld hl, pcols
        ld b, NB
        otir
        VRAM_WRITE $1800        ; both name tables all sky
        call sky
        VRAM_WRITE $1C00
        call sky
        ld a, $1C
        ld (table), a
        xor a
        call window             ; window 0 in the table at $1800
        ld a, $18
        ld (table), a
        ld a, 1
        call window             ; window 1 in the table at $1C00, not shown
        ld a, 1
        ld (shift), a           ; the first frame: a pixel on
        VRAM_WRITE SPAT         ; the ship's patterns
        ld hl, sprite
        ld bc, 32 << 8 | VDP_DATA
        otir
        jp on

; sky: 768 names of the sky, 0, to the VRAM, with the display off
sky:    ld de, 768
.name:  xor a
        out (VDP_DATA), a
        dec de
        ld a, d
        or e
        jr nz, .name
        ret
on:
""" + end_lines(0xE2)


def cave_data():
    stab = "".join(f"        dw shifts + {s * 8 * NP}\n" for s in range(8))
    shp = [b for s in range(8) for a, b2 in PAIRS for b in shifted(a, b2, s)]
    cols = [b for a, b2 in PAIRS for b in pair_colours(a, b2)]
    out = ("        ALIGN 16\nstab:                           ; where each shift's patterns start\n" + stab +
           f"shifts:                         ; the {NP} pairs at shifts 0 to 7, {8 * NP} bytes each\n" +
           db_rows(shp, 16) + "pcols:                          ; their colours\n" + db_rows(cols, 16) +
           "first:                          ; the ship's attributes at the start, and the end\n" +
           db_rows([CAVE_Y0 - 1, SHIP_AT[0], 0, SHIP_COLOUR, 0xD0]) +
           "sprite:                         ; the ship, 16 x 16 (chapter 26)\n" + db_rows(big(SHIP)) +
           demo_data(CAVE_DEMO, "the ship along the cave"))
    out += "        ALIGN 256\npmap:                           ; rows 1 to 4 and 17 to 23: each row's pairs in a page\n"
    for r, row in zip(SCROLL_ROWS, PMAP):
        out += f"        ; row {r}\n" + db_rows(row + row[:31], 16)
        if r != SCROLL_ROWS[-1]:
            out += "        ALIGN 256\n"
    return out


def cave():
    say = f"""; A cave that scrolls a pixel a frame, with {NP} patterns: the pairs of tiles side
; by side in its {len(SCROLL_ROWS)} rows of rock, rewritten every frame at the new shift
; straight after HALT; the names change every eighth frame: written into the
; table not shown in the loop that turns R#2, and shown by the next turn,
; eight frames later (chapter 29).
; A ship, a sprite, flies the sky between, as the demo's keys say.
"""
    return program("cave", "a shooter in a cave", say, CAVE_RAM, CAVE_CONSTS, cave_setup(),
                   CAVE_SENDS + CAVE_RUN, cave_data())


# ================================================================ the ledges
LEDGES = {23: (0, 31), 20: (12, 17), 17: (20, 25), 14: (26, 31), 11: (15, 20), 8: (5, 10)}
JUMP = 0x0380               # the speed up at the start of a jump: 3.5 lines a frame
GRAVITY = 0x0028            # added every frame: 40/256 of a line
MAXFALL = 0x0400            # down at most 4 lines a frame: less than a cell
RUN = 2                     # pixels a frame, left or right
X_LAST = 240                # the runner's x from 0 to 240
RUNNER_AT = (16, 168)       # its first place, on the floor: x, its top line
BRICK_C = BLACK << 4 | DARK_RED     # a ledge: chapter 39's brick, black on dark red
SKY_C = WHITE << 4 | BLACK          # the sky: white ink, for the dots, on black
RUNNER_COLOUR = CYAN
JUMP_BORDER = BLACK
assert MAXFALL < 0x0800

RUNNER_ART = [
    "......####......",
    ".....######.....",
    ".....#.##.#.....",
    ".....######.....",
    "......####......",
    ".......##.......",
    "...##########...",
    "..#.########.#..",
    "..#..######..#..",
    ".....######.....",
    ".....##..##.....",
    ".....##..##.....",
    ".....##..##.....",
    ".....##..##.....",
    "....###..###....",
    "....###..###...."]
RUNNER = rows16(RUNNER_ART)


def ledge(c, r):
    return r in LEDGES and LEDGES[r][0] <= c <= LEDGES[r][1]


class Runner:
    """jump.asm's walk and fall, in Python: x, y in 8.8, the speed in 8.8,
    on a ledge or not"""
    def __init__(self):
        self.x, self.y, self.vy, self.ground = RUNNER_AT[0], RUNNER_AT[1] << 8, 0, True

    def under(self, line):
        r = line // 8
        return any(ledge(c, r) for c in range(self.x // 8, (self.x + 15) // 8 + 1))

    def step(self, k):
        if k & LEFT and self.x > 0:
            self.x -= RUN
        if k & RIGHT and self.x < X_LAST:
            self.x += RUN
        vy = self.vy
        if k & FIRE and self.ground:
            vy = -JUMP & 0xFFFF
        vy = (vy + GRAVITY) & 0xFFFF
        if vy < 0x8000 and vy >> 8 >= MAXFALL >> 8:
            vy = MAXFALL
        ny = (self.y + vy) & 0xFFFF
        if vy < 0x8000:
            old, new = ((self.y >> 8) + 16) & 255, ((ny >> 8) + 16) & 255
            t = new & 0xF8
            if old <= t and self.under(t):
                self.y, self.vy, self.ground = (t - 16) << 8, 0, True
                return
        self.y, self.vy, self.ground = ny, vy, False


def jump_lap():
    """a lap of the ledges, planned on Runner: up to the right from the
    floor, ledge to ledge, back up to the left, off the top ledge's end and
    down to the floor where it began -> the keys, a frame each, and the
    runner's place after each"""
    r, keys, path = Runner(), [], []

    def go(k):
        keys.append(k)
        r.step(k)
        path.append((r.x, r.y >> 8, r.y & 255, r.vy, r.ground))
    while r.x < 36:
        go(RIGHT)
    for way, hold in ((RIGHT, None), (RIGHT, None), (RIGHT, 14), (LEFT, None), (LEFT, None)):
        go(way | FIRE)
        n = 0
        while not r.ground:
            go(way if hold is None or n < hold else 0)
            n += 1
    while r.ground:
        go(LEFT)
    while r.x > RUNNER_AT[0]:
        go(LEFT)
    while not r.ground:
        go(0)
    assert (r.x, r.y >> 8, r.vy, r.ground) == (RUNNER_AT[0], RUNNER_AT[1], 0, True)
    return keys, path


def jump_landings(path):
    """each landing of a lap: frame, x, the ledge's row"""
    return [(f, x, (y + 16) // 8) for f, (x, y, frac, vy, g) in enumerate(path)
            if g and f > 0 and not path[f - 1][4]]


JUMP_KEYS, JUMP_PATH = jump_lap()
JUMP_DEMO = compress(JUMP_KEYS)
_lands = jump_landings(JUMP_PATH)
assert [row for _, _, row in _lands] == [20, 17, 14, 11, 8, 23], _lands

JUMP_RAM = """rx      EQU VARS + 8            ; the runner's x
ry      EQU VARS + 9            ; its top line: y's whole lines
yfrac   EQU VARS + 10           ; and y's 256ths
vy      EQU VARS + 11           ; the speed, 8.8, down positive: two bytes
landed  EQU VARS + 13           ; 1 on a ledge, 0 in the air
"""
JUMP_CONSTS = f"""JUMP    EQU ${JUMP:04X}             ; the speed up at a jump's start: 3.5 lines a frame
GRAVITY EQU ${GRAVITY:04X}             ; added every frame: 40/256 of a line
MAXFALL EQU ${MAXFALL:04X}             ; down at most 4 lines a frame
RUN     EQU {RUN}                   ; pixels a frame, left or right
X_LAST  EQU {X_LAST}                 ; the runner's x from 0 to X_LAST
"""

JUMP_SENDS = """
; sends: straight after HALT, before the paper: the runner's attributes, and
;        a dot at its feet, both for the place the frame before worked out.
;        Uses A, BC, DE, HL
sends:  VRAM_WRITE SAT          ; 40
        ld hl, copy             ; 11
        ld bc, 5 << 8 | VDP_DATA ; 11  the runner and the end
        otir                    ; 23 a byte, 18 the last

; trail: a dot between the runner's feet, on their last line, at x + 7,
;        y + 15, with chapter 25's plot. Uses A, BC, DE, HL
trail:  ld a, (rx)              ; 14
        add a, 7                ;  8
        ld b, a                 ;  5  B: x
        ld a, (ry)              ; 14
        add a, 15               ;  8
        ld c, a                 ;  5  C: y
        jp plot                 ; 11  whose RET is sends'
"""

JUMP_RUN = """
; run: the frame's work: the demo's keys, a walk, a fall or a jump, and the
;      runner's attributes for the next frame. Uses every register
run:    call pad                ; 18  A: the keys
        call walk               ; 18
        ld a, (held)            ; 14
        call fall               ; 18
place:  ld a, (ry)              ; 14  the copy: Y, a line above the top
        dec a                   ;  5
        ld (copy), a            ; 14
        ld a, (rx)              ; 14  and X
        ld (copy + 1), a        ; 14
        ret                     ; 11

; walk: A = the keys -> the runner two pixels left for LEFT, right for
;       RIGHT, x from 0 to X_LAST. Uses A, B, HL
walk:   ld b, a                 ;  5
        ld hl, rx               ; 11
        bit 2, b                ; 10  LEFT?
        jr nz, .right           ; 13, or 8
        ld a, (hl)              ;  8
        or a                    ;  5
        jr z, .right            ; 13, or 8  at the left edge
        sub RUN                 ;  8
        ld (hl), a              ;  8
.right: bit 3, b                ; 10  RIGHT?
        ret nz                  ; 12, or 6
        ld a, (hl)              ;  8
        cp X_LAST               ;  8
        ret nc                  ; 12, or 6  at the right edge
        add a, RUN              ;  8
        ld (hl), a              ;  8
        ret                     ; 11

; fall: A = the keys -> SPACE on a ledge starts a jump, the speed JUMP up;
;       gravity adds GRAVITY to the speed, down at most MAXFALL, and the
;       speed is added to y. Both are 8.8: the high byte whole lines, the
;       low byte 256ths of a line. Going down, feet that reach the top of a
;       ledge's cell stop there. Uses A, BC, DE, HL
fall:   ld hl, (vy)             ; 17  the speed, down positive
        bit 4, a                ; 10  SPACE?
        jr nz, .grav            ; 13, or 8
        ld a, (landed)          ; 14
        or a                    ;  5
        jr z, .grav             ; 13, or 8  in the air: no jump
        ld hl, -JUMP            ; 11  a jump
.grav:  ld de, GRAVITY          ; 11
        add hl, de              ; 12  gravity
        bit 7, h                ; 10
        jr nz, .fast            ; 13, or 8  going up
        ld a, h                 ;  5
        cp high MAXFALL         ;  8
        jr c, .fast             ; 13, or 8
        ld hl, MAXFALL          ; 11  no faster
.fast:  ld (vy), hl             ; 17
        ex de, hl               ;  5  DE: the speed
        ld a, (ry)              ; 14  y's whole lines
        ld h, a                 ;  5
        ld a, (yfrac)           ; 14  and its 256ths
        ld l, a                 ;  5
        add hl, de              ; 12  HL: the new y
        bit 7, d                ; 10
        jr nz, .air             ; 13, or 8  going up: in the air
        ld a, h                 ;  5
        add a, 16               ;  8  the line under the new feet
        and $F8                 ;  8  the top line of its cell
        ld c, a                 ;  5  C
        ld a, (ry)              ; 14
        add a, 16               ;  8  the line under the feet before
        cp c                    ;  5
        jr z, .look             ; 13, or 8  on that top already
        jr nc, .air             ; 13, or 8  below it: not reached
.look:  call under              ; 18  a ledge in that row?
        jr z, .air              ; 13, or 8  none: on in the air
        ld a, c                 ;  5
        sub 16                  ;  8
        ld (ry), a              ; 14  the feet on the ledge's top
        xor a                   ;  5
        ld (yfrac), a           ; 14
        ld h, a                 ;  5
        ld l, a                 ;  5
        ld (vy), hl             ; 17  still
        inc a                   ;  5
        ld (landed), a          ; 14  on a ledge
        ret                     ; 11
.air:   ld a, h                 ;  5
        ld (ry), a              ; 14  the new y
        ld a, l                 ;  5
        ld (yfrac), a           ; 14
        xor a                   ;  5
        ld (landed), a          ; 14  in the air
        ret                     ; 11

; under: C = the top line of a row of cells -> NZ if a ledge's cell is in
;        that row under the runner's 16 pixels: two cells, or three when x
;        is not a multiple of 8; ledges, the cartridge's map of the cells,
;        holds 1 for a ledge's. Uses A, B, DE
under:  ld a, c                 ;  5  the line, 8 times the row
        rlca                    ;  5
        rlca                    ;  5  the row times 32, its high bits low
        ld b, a                 ;  5
        and $E0                 ;  8  the low byte
        ld e, a                 ;  5
        ld a, b                 ;  5
        and 3                   ;  8
        add a, high ledges      ;  8  and the high
        ld d, a                 ;  5  DE: the row's first cell
        ld a, (rx)              ; 14  x
        rrca                    ;  5
        rrca                    ;  5
        rrca                    ;  5
        and 31                  ;  8  its column
        or e                    ;  5
        ld e, a                 ;  5  DE: the cell under its left
        ld a, (de)              ;  8
        or a                    ;  5
        ret nz                  ; 12, or 6  a ledge
        inc e                   ;  5
        ld a, (de)              ;  8  the next cell
        or a                    ;  5
        ret nz                  ; 12, or 6
        ld a, (rx)              ; 14
        and 7                   ;  8
        ret z                   ; 12, or 6  two cells only: none
        inc e                   ;  5
        ld a, (de)              ;  8  the third
        or a                    ;  5
        ret                     ; 11

"""


def jump_setup():
    return start_lines(GRAPHIC2_THREE, JUMP_BORDER) + f"""        ld a, {RUNNER_AT[0]}
        ld (rx), a
        ld a, {RUNNER_AT[1]}
        ld (ry), a
        ld a, 1
        ld (landed), a          ; on the floor
        VRAM_WRITE $0000        ; the patterns, cell by cell: a ledge's brick
        ld de, ledges           ; or nothing
        ld hl, brick
        call cells
        VRAM_WRITE $2000        ; the colours: the brick's, or the sky's
        ld de, ledges
        ld hl, bcols
        call cells
        VRAM_WRITE $1800        ; the names: 0 to 255 in each third
        ld b, 3
.third: xor a
.name:  out (VDP_DATA), a
        inc a
        jr nz, .name
        djnz .third
        VRAM_WRITE SPAT         ; the runner's patterns
        ld hl, sprite
        ld bc, 32 << 8 | VDP_DATA
        otir
        jp on

; cells: DE = the map, HL = 8 bytes for a ledge's cell, 8 more for the sky's
;        -> 768 cells' bytes to the VRAM, with the display off
cells:  ld bc, 768
.cell:  push bc
        push hl
        ld a, (de)
        or a
        jr nz, .put             ; a ledge: the first 8
        ld bc, 8
        add hl, bc              ; the sky: the next 8
.put:   ld bc, 8 << 8 | VDP_DATA
        otir
        pop hl
        pop bc
        inc de
        dec bc
        ld a, b
        or c
        jr nz, .cell
        ret
on:
""" + end_lines(0xE2)


def jump_data():
    mp = [1 if ledge(c, r) else 0 for r in range(24) for c in range(32)]
    return ("brick:                          ; a ledge's cell: chapter 39's brick; the sky's\n" +
            db_rows(list(gen39.BRICK) + [0] * 8) +
            "bcols:                          ; their colours\n" + db_rows([BRICK_C] * 8 + [SKY_C] * 8) +
            "first:                          ; the runner's attributes at the start, and the end\n" +
            db_rows([RUNNER_AT[1] - 1, RUNNER_AT[0], 0, RUNNER_COLOUR, 0xD0]) +
            "sprite:                         ; the runner, 16 x 16 (chapter 26)\n" + db_rows(big(RUNNER)) +
            demo_data(JUMP_DEMO, "a lap of the ledges") + gen25.MASKS +
            "        ALIGN 256\nledges:                         ; the cells: 1 for a ledge's, 24 rows of 32\n" +
            db_rows(mp, 16))


def jump():
    say = """; A runner on ledges of bricks, a sprite, running and jumping as the demo's
; keys say: y and the speed in 8.8, gravity every frame, a landing on the
; top of a ledge's cell; and a dot at its feet every frame, with chapter 25's
; plot, on a screen whose names run 0 to 255 in each third.
"""
    return program("jump", "a runner that jumps", say, JUMP_RAM, JUMP_CONSTS, jump_setup(),
                   JUMP_SENDS + JUMP_RUN + gen25.VADDR + gen25.PLOT, jump_data())


# ================================================================ the maze
MAZE_SEED = 7
NORTH, EAST, SOUTH, WEST = range(4)
DIRS = [(-1, 0), (0, 1), (1, 0), (0, -1)]
START = (1, 1, EAST)        # the explorer's first cell and way
MOVE_FRAMES = 12            # a move every 12 frames
IDLE = 12                   # frames before the first
MOVES = 50                  # 612 frames: past the film's 600
WIN_COL, WIN_ROW = 2, 6     # the window: columns 2 to 13, rows 6 to 17
WIN = 96                    # its pixels across and down: lines 48 to 143
XS = [0, 24, 32, 36, 38]    # the edge of each depth: 48 - 48 / (k + 1)
MAP_COL, MAP_ROW = 17, 4    # the map's top left cell: cells 0 to 14 of the maze
BUF_AT = 0xC800             # the buffer: a page for each row of the window's cells
BUF_H = BUF_AT >> 8
INK_PAPER = BLACK << 4 | WHITE      # every colour: black ink on white paper
ARROW_COLOUR = DARK_BLUE
MAZE_BORDER = WHITE
BLANK, OPEN, WALLP = 255, 254, 253  # the patterns of the rest, in each third
FRAME_P = {"t": 248, "tl": 249, "tr": 250, "l": 251, "r": 252, "b": 243, "bl": 244, "br": 245}
ARROWS = {
    NORTH: ["...##...", "..####..", ".######.", "...##...", "...##...", "...##...",
            "...##...", "........"],
    EAST: ["....#...", "....##..", "#######.", "########", "#######.", "....##..",
           "....#...", "........"],
    SOUTH: ["...##...", "...##...", "...##...", "...##...", ".######.", "..####..",
            "...##...", "........"],
    WEST: ["...#....", "..##....", ".#######", "########", ".#######", "..##....",
           "...#....", "........"]}


def maze():
    """16 x 16 cells, 1 a wall: a maze dug by chapter 41's xorshift between
    the cells at odd rows and columns 1 to 13; rows and columns 14 and 15
    walls, like row and column 0"""
    m = [[1] * 16 for _ in range(16)]
    x = MAZE_SEED
    stack = [(1, 1)]
    m[1][1] = 0
    while stack:
        r, c = stack[-1]
        nb = [(r + dr, c + dc, dr, dc) for dr, dc in ((-2, 0), (0, 2), (2, 0), (0, -2))
              if 1 <= r + dr <= 13 and 1 <= c + dc <= 13 and m[r + dr][c + dc]]
        if not nb:
            stack.pop()
            continue
        x = gen41.xorshift(x)
        r2, c2, dr, dc = nb[(x >> 8) % len(nb)]
        m[r + dr // 2][c + dc // 2] = 0
        m[r2][c2] = 0
        stack.append((r2, c2))
    return m


MAZE = maze()


def maze_moves():
    """the demo's moves, along the right-hand wall: where the wall on the
    right gives way, a turn to the right and then a step forward; else a step
    forward if the cell ahead is open; else a turn to the left -> the moves,
    each with the cell and the way after it"""
    r, c, f = START
    out = []
    for _ in range(MOVES):
        dr, dc = DIRS[(f + 1) % 4]
        if out and out[-1][0] == "R":
            dr, dc = DIRS[f]
            assert not MAZE[r + dr][c + dc]
            r, c = r + dr, c + dc
            out.append(("F", r, c, f))
        elif not MAZE[r + dr][c + dc]:
            f = (f + 1) % 4
            out.append(("R", r, c, f))
        else:
            dr, dc = DIRS[f]
            if not MAZE[r + dr][c + dc]:
                r, c = r + dr, c + dc
                out.append(("F", r, c, f))
            else:
                f = (f + 3) % 4
                out.append(("L", r, c, f))
    return out


def maze_keys():
    key = {"F": UP, "L": LEFT, "R": RIGHT}
    ks = [0] * IDLE
    for m, *_ in maze_moves():
        ks += [key[m]] + [0] * (MOVE_FRAMES - 1)
    return ks


MAZE_KEYS = maze_keys()
MAZE_DEMO = compress(MAZE_KEYS)


def buf_at(x, y):
    """the buffer's byte for pixel (x, y) of the view, and its mask: a page
    for each row of cells, laid out as the patterns (chapter 25)"""
    return BUF_AT + (y >> 3) * 256 + (x & 0xF8) + (y & 7), 0x80 >> (x & 7)


VLINE, HLINE, DOWNR, UPR = range(4)     # the kinds of line in a piece
KIND_NAMES = {VLINE: "down", HLINE: "right", DOWNR: "right and down", UPR: "right and up"}


def piece_lines(k, side, wall):
    """segment k's left (side -1) or right (side 1) side: a wall, its two
    edges slanting in; or an opening, the far wall's top and bottom of the
    corridor that turns off; and the corner where the segment ends.
    -> lines: (kind, x, y, pixels), drawn left to right and downwards"""
    a, b = XS[k], XS[k + 1]
    n = b - a
    if side < 0:
        out = ([(DOWNR, a, a, n), (UPR, a, WIN - 1 - a, n)] if wall else
               [(HLINE, a, b, n), (HLINE, a, WIN - 1 - b, n)])
        out.append((VLINE, b, b, WIN - 2 * b))
    else:
        out = ([(UPR, WIN - b, b - 1, n), (DOWNR, WIN - b, WIN - b, n)] if wall else
               [(HLINE, WIN - b, b, n), (HLINE, WIN - b, WIN - 1 - b, n)])
        out.append((VLINE, WIN - 1 - b, b, WIN - 2 * b))
    return out


def front_lines(d):
    """the wall ahead at depth d: its top and its bottom"""
    b = XS[d]
    return [(HLINE, b, b, WIN - 2 * b), (HLINE, b, WIN - 1 - b, WIN - 2 * b)]


def line_pixels(kind, x, y, n):
    return [{VLINE: (x, y + i), HLINE: (x + i, y), DOWNR: (x + i, y + i),
             UPR: (x + i, y - i)}[kind] for i in range(n)]


def view_lines(r, c, f):
    """the lines of the view from cell (r, c) facing f, as view draws them"""
    out = []
    fr, fc = DIRS[f]
    for k in range(4):
        hr, hc = r + k * fr, c + k * fc
        for side in (-1, 1):
            sr, sc = DIRS[(f + side) % 4]
            out += piece_lines(k, side, MAZE[hr + sr][hc + sc])
        if MAZE[hr + fr][hc + fc] or k == 3:
            out += front_lines(k + 1)
            break
    return out


def view_pixels(r, c, f):
    img = [[0] * WIN for _ in range(WIN)]
    for line in view_lines(r, c, f):
        for px, py in line_pixels(*line):
            img[py][px] = 1
    return img


def depth(r, c, f):
    """the first wall ahead of cell (r, c) facing f: 1 to 4, or 5 if none"""
    dr, dc = DIRS[f]
    return next((k for k in range(1, 5) if MAZE[r + k * dr][c + k * dc]), 5)


# the window's two sets of patterns, in each third: the rows of the window
# that third holds, twelve patterns a row; set 1 after set 0
def window_rows():
    """for each row of the window: its third, its row in that third's part
    of the window, and that third's patterns a set"""
    out = []
    for i in range(12):
        row = WIN_ROW + i
        t = row >> 3
        rows_t = [WIN_ROW + j for j in range(12) if (WIN_ROW + j) >> 3 == t]
        out.append((t, rows_t.index(row), 12 * len(rows_t)))
    return out


def window_pattern(s, i, c):
    """set S's pattern for the window's cell at row I, column C: its number
    in its third"""
    t, j, per = window_rows()[i]
    return s * per + 12 * j + c


def screen_names(s=0):
    """the 768 names, the window showing set S"""
    names = [BLANK] * 768
    for i in range(12):
        for c in range(12):
            names[32 * (WIN_ROW + i) + WIN_COL + c] = window_pattern(s, i, c)
    top, bot = WIN_ROW - 1, WIN_ROW + 12
    left, right = WIN_COL - 1, WIN_COL + 12
    for c in range(WIN_COL, WIN_COL + 12):
        names[32 * top + c] = FRAME_P["t"]
        names[32 * bot + c] = FRAME_P["b"]
    for r in range(WIN_ROW, WIN_ROW + 12):
        names[32 * r + left] = FRAME_P["l"]
        names[32 * r + right] = FRAME_P["r"]
    names[32 * top + left], names[32 * top + right] = FRAME_P["tl"], FRAME_P["tr"]
    names[32 * bot + left], names[32 * bot + right] = FRAME_P["bl"], FRAME_P["br"]
    for r in range(15):
        for c in range(15):
            names[32 * (MAP_ROW + r) + MAP_COL + c] = WALLP if MAZE[r][c] else OPEN
    return names


FRAME_SHAPES = {"t": [0] * 7 + [0xFF], "tl": [0] * 7 + [0x01], "tr": [0] * 7 + [0x80],
                "l": [0x01] * 8, "r": [0x80] * 8, "b": [0xFF] + [0] * 7,
                "bl": [0x01] + [0] * 7, "br": [0x80] + [0] * 7}


def fixed_patterns():
    """the patterns that never change, in every third: number -> 8 bytes"""
    out = {WALLP: [0xFF] * 8, OPEN: [0] * 8, BLANK: [0] * 8}
    for k, p in FRAME_P.items():
        out[p] = FRAME_SHAPES[k]
    return out


def ways():
    """for each way faced: the steps to the cell ahead, on the left and on the
    right, a cell being 16 times its row plus its column"""
    out = []
    for f in range(4):
        for d in (f, (f + 3) % 4, (f + 1) % 4):
            dr, dc = DIRS[d]
            out.append((16 * dr + dc) & 255)
    return out


MAZE_RAM = """pos     EQU VARS + 8            ; the explorer's cell: 16 times its row plus its column
face    EQU VARS + 9            ; the way faced: 0 north, 1 east, 2 south, 3 west
stage   EQU VARS + 10           ; 0, or 1 a view drawn into BUF, or 2 a view sent
wset    EQU VARS + 11           ; the window's set of patterns shown, 0 or 1
was     EQU VARS + 12           ; the keys of the frame before
here    EQU VARS + 13           ; view's cell
fwd     EQU VARS + 14           ; view's steps: ahead,
lft     EQU VARS + 15           ; to the left
rgt     EQU VARS + 16           ; and to the right
savesp  EQU VARS + $18          ; blank's stack, two bytes
"""
MAZE_CONSTS = f"""BUF     EQU ${BUF_AT:04X}               ; the view: a page for each row of cells, 96 bytes each
BUF_H   EQU ${BUF_H:02X}
MAP_COL EQU {MAP_COL}                  ; the map's top left cell
MAP_ROW EQU {MAP_ROW}
"""

MAZE_SENDS = """
; sends: straight after HALT, before the paper: a view sent the frame before
;        shown, by flip; then the arrow's attributes. Uses A, BC, DE, HL
sends:  ld a, (stage)           ; 14
        cp 2                    ;  8
        call z, flip            ; 18, or 11
        VRAM_WRITE SAT          ; 40
        ld hl, copy             ; 11
        ld bc, 5 << 8 | VDP_DATA ; 11  the arrow and the end
        otir                    ; 23 a byte, 18 the last
        ret                     ; 11
"""


def flip_routine():
    rows = "".join(f"""        VRAM_WRITE $1800 + 32 * {WIN_ROW + i} + {WIN_COL} ; 40  row {WIN_ROW + i}
        ld b, 12                ;  8
        otir                    ; 23 a byte, 18 the last
""" for i in range(12))
    return """
; flip: the window's 144 names turned to the set just sent, a row of 12 at a
;       time; then the arrow moved. Uses A, BC, HL
flip:   ld a, (wset)             ; 14
        xor 1                   ;  8
        ld (wset), a             ; 14  the set just sent
        ld hl, wnames           ; 11  set 0's names: 12 rows of 12
        jr z, .rows             ; 13, or 8
        ld hl, wnames + 144     ; 11  set 1's
.rows:  ld c, VDP_DATA          ;  8
""" + rows + """        xor a                   ;  5
        ld (stage), a           ; 14  shown

; mark: the arrow's attributes for the cell pos and the way faced: its cell
;       on the map, and the way's pattern. Uses A, B
mark:   ld a, (pos)             ; 14  16 times the row, plus the column
        ld b, a                 ;  5
        and $F0                 ;  8
        rrca                    ;  5  the row times 8
        add a, 8 * MAP_ROW - 1  ;  8  Y: a line above its cell's top
        ld (copy), a            ; 14
        ld a, b                 ;  5
        and 15                  ;  8  the column
        add a, a                ;  5
        add a, a                ;  5
        add a, a                ;  5
        add a, 8 * MAP_COL      ;  8
        ld (copy + 1), a        ; 14  X
        ld a, (face)            ; 14
        ld (copy + 2), a        ; 14  the pattern: the way faced
        ret                     ; 11
"""


MAZE_RUN = """
; run: the frame's work: the demo's keys; a view drawn the frame before sent;
;      or, for a key down this frame and not the one before, a step and a
;      new view. Uses every register but IY
run:    call pad                ; 18  A: the keys, a 0 for each held
        ld hl, was              ; 11
        ld b, (hl)              ;  8  the keys of the frame before
        ld (hl), a              ;  8
        cpl                     ;  5  a 1 for each held now
        and b                   ;  5  and not before: down this frame
        ld c, a                 ;  5
        ld a, (stage)           ; 14
        dec a                   ;  5
        jp z, send              ; 11  a view drawn: sent now
        inc a                   ;  5
        ret nz                  ; 12, or 6  one sent, to be shown first
        ld a, c                 ;  5
        or a                    ;  5
        ret z                   ; 12, or 6  no key down

; step: C = the keys down -> a quarter turn to the left for LEFT, to the
;       right for RIGHT, a step forward for UP if the cell ahead is open;
;       then the view drawn again into BUF. Uses every register but IY
step:   ld hl, face             ; 11
        bit 2, c                ; 10  LEFT
        jr z, .r                ; 13, or 8
        dec (hl)                ; 12  a quarter turn
.r:     bit 3, c                ; 10  RIGHT
        jr z, .f                ; 13, or 8
        inc (hl)                ; 12
.f:     ld a, (hl)              ;  8
        and 3                   ;  8  north, east, south or west
        ld (hl), a              ;  8
        bit 0, c                ; 10  UP
        jr z, .draw             ; 13, or 8
        ld b, a                 ;  5
        add a, a                ;  5
        add a, b                ;  5  three bytes a way
        add a, low ways         ;  8
        ld l, a                 ;  5
        ld h, high ways         ;  8  HL: the step ahead
        ld a, (pos)             ; 14
        add a, (hl)             ;  8  the cell ahead
        ld l, a                 ;  5
        ld h, high cells        ;  8
        ld b, (hl)              ;  8
        dec b                   ;  5  Z if a wall
        jr z, .draw             ; 13, or 8
        ld (pos), a             ; 14  open: a step into it
.draw:  call view               ; 18  the view from there
        ld a, 1                 ;  8
        ld (stage), a           ; 14  to be sent
        ret                     ; 11

; send: BUF to the set of the window's patterns not shown, a row of its
;       cells at a time: 96 bytes at 29 T-states each (chapter 31's OUTI and
;       JP NZ), before the paper and on into it: the set is not shown, and
;       when does not matter. Uses A, BC, DE, HL
send:   ld a, (wset)             ; 14  the set shown
        ld de, at1              ; 11  set 1's twelve addresses
        or a                    ;  5
        jr z, .go               ; 13, or 8  set 0 shown: set 1 sent
        ld de, at0              ; 11
.go:    ld hl, BUF              ; 11
        ld c, VDP_DATA          ;  8
.row:   ld a, (de)              ;  8
        out (VDP_CTRL), a       ; 12
        inc de                  ;  7
        ld a, (de)              ;  8
        out (VDP_CTRL), a       ; 12  the row's first pattern, for writing
        inc de                  ;  7
        ld b, 96                ;  8  its twelve patterns
.byte:  outi                    ; 18
        jp nz, .byte            ; 11  29 T-states a byte
        ld l, 0                 ;  8
        inc h                   ;  5  BUF's next page
        ld a, h                 ;  5
        cp BUF_H + 12           ;  8
        jr nz, .row             ; 13, or 8
        ld a, 2                 ;  8
        ld (stage), a           ; 14  to be shown
        ret                     ; 11

; view: the view from cell pos, facing face, drawn into BUF: for each of four
;       cells ahead, from the explorer's own, the wall or the opening on its
;       left and on its right; then, if the next cell ahead is a wall, that
;       wall, and the view is done. After the fourth cell the wall ahead is
;       drawn anyway, a square far off. Uses every register but IY
view:   call blank              ; 18  BUF all paper
        ld a, (face)            ; 14  the way faced, 0 to 3
        ld b, a                 ;  5
        add a, a                ;  5
        add a, b                ;  5  three bytes a way
        add a, low ways         ;  8
        ld l, a                 ;  5
        ld h, high ways         ;  8  HL: its steps
        ld de, fwd              ; 11
        ldi                     ; 18
        ldi                     ; 18
        ldi                     ; 18  ahead, to the left and to the right
        ld a, (pos)             ; 14
        ld (here), a            ; 14  the first cell, the explorer's
        ld ix, pieces           ; 16  its segment's pieces
        ld b, 4                 ;  8  four segments
.seg:   push bc                 ; 12
        ld a, (lft)             ; 14
        call side               ; 18  the cell on the left
        ld l, (ix+0)            ; 21
        ld h, (ix+1)            ; 21  open: the opening's piece
        jr z, .left             ; 13, or 8
        ld l, (ix+2)            ; 21
        ld h, (ix+3)            ; 21  a wall: the wall's
.left:  call piece              ; 18
        ld a, (rgt)             ; 14
        call side               ; 18  the cell on the right
        ld l, (ix+4)            ; 21
        ld h, (ix+5)            ; 21
        jr z, .right            ; 13, or 8
        ld l, (ix+6)            ; 21
        ld h, (ix+7)            ; 21
.right: call piece              ; 18
        ld a, (fwd)             ; 14
        call side               ; 18  the next cell ahead
        ld l, (ix+8)            ; 21
        ld h, (ix+9)            ; 21  the wall at the next depth
        pop bc                  ; 11
        jp nz, piece            ; 11  a wall: drawn, and done
        dec b                   ;  5
        jp z, piece             ; 11  the fourth: drawn far off anyway
        ld a, e                 ;  5
        ld (here), a            ; 14  open: on to it
        ld de, 10               ; 11
        add ix, de              ; 17  and its segment's pieces
        jr .seg                 ; 13

; side: A = a step -> E = the cell that step from here, NZ if it is a wall,
;       Z if open. Uses A, E, HL
side:   ld hl, here             ; 11
        add a, (hl)             ;  8  the cell
        ld e, a                 ;  5
        ld l, a                 ;  5
        ld h, high cells        ;  8
        ld a, (hl)              ;  8  0 open, 1 a wall
        or a                    ;  5
        ret                     ; 11

; piece: HL = a piece, its lines five bytes each: the kind, the mask of its
;        first pixel, its pixels, and the byte of BUF where it starts; a
;        kind of 4 ends the piece -> its lines drawn into BUF. Kind 0 goes
;        down, 1 right, 2 right and down, 3 right and up. Uses A, BC, DE, HL
piece:  ld a, (hl)              ;  8  the kind
        cp 4                    ;  8
        ret nc                  ; 12, or 6  the end
        inc hl                  ;  7
        ld c, (hl)              ;  8  C: the mask
        inc hl                  ;  7
        ld b, (hl)              ;  8  B: the pixels
        inc hl                  ;  7
        ld e, (hl)              ;  8
        inc hl                  ;  7
        ld d, (hl)              ;  8  DE: the first byte
        inc hl                  ;  7
        push hl                 ; 12  the next line
        ex de, hl               ;  5  HL: this one's first byte
        or a                    ;  5
        jr nz, .k1              ; 13, or 8
        call vert               ; 18  kind 0
        jr .next                ; 13
.k1:    dec a                   ;  5
        jr nz, .k2              ; 13, or 8
        call across             ; 18  kind 1
        jr .next                ; 13
.k2:    dec a                   ;  5
        jr nz, .k3              ; 13, or 8
        call downr              ; 18  kind 2
        jr .next                ; 13
.k3:    call upr                ; 18  kind 3
.next:  pop hl                  ; 11
        jr piece                ; 13

; vert: HL = a byte of BUF, C = a pixel's mask, B = pixels -> a line of
;       them downwards, from cell to cell as chapter 22's down goes. Uses
;       A, B, HL
vert:   ld a, (hl)              ;  8
        or c                    ;  5  the pixel
        ld (hl), a              ;  8
        inc l                   ;  5  a line down
        ld a, l                 ;  5
        and 7                   ;  8
        jr nz, .on              ; 13, or 8  in the same cell
        ld a, l                 ;  5
        sub 8                   ;  8
        ld l, a                 ;  5
        inc h                   ;  5  the cell below
.on:    djnz vert               ; 14, or 9
        ret                     ; 11

; across: HL, C and B as vert's -> a line of pixels to the right. Uses A,
;         BC, HL
across: ld a, (hl)              ;  8
        or c                    ;  5  the pixel
        ld (hl), a              ;  8
        rrc c                   ; 10  a pixel to the right
        jr nc, .on              ; 13, or 8  in the same byte
        ld a, l                 ;  5
        add a, 8                ;  8  or in the next cell's
        ld l, a                 ;  5
.on:    djnz across             ; 14, or 9
        ret                     ; 11

; downr: HL, C and B as vert's -> a line of pixels each a pixel to the right
;        of the one before and a line below it. Uses A, BC, HL
downr:  ld a, (hl)              ;  8
        or c                    ;  5  the pixel
        ld (hl), a              ;  8
        rrc c                   ; 10  a pixel to the right
        jr nc, .down            ; 13, or 8
        ld a, l                 ;  5
        add a, 8                ;  8
        ld l, a                 ;  5
.down:  inc l                   ;  5  and a line down
        ld a, l                 ;  5
        and 7                   ;  8
        jr nz, .on              ; 13, or 8
        ld a, l                 ;  5
        sub 8                   ;  8
        ld l, a                 ;  5
        inc h                   ;  5  the cell below
.on:    djnz downr              ; 14, or 9
        ret                     ; 11

; upr: HL, C and B as vert's -> a line of pixels each a pixel to the right
;      of the one before and a line above it. Uses A, BC, HL
upr:    ld a, (hl)              ;  8
        or c                    ;  5  the pixel
        ld (hl), a              ;  8
        rrc c                   ; 10  a pixel to the right
        jr nc, .up              ; 13, or 8
        ld a, l                 ;  5
        add a, 8                ;  8
        ld l, a                 ;  5
.up:    ld a, l                 ;  5
        and 7                   ;  8
        jr z, .cell             ; 13, or 8  the cell's first line
        dec l                   ;  5  a line up
        djnz upr                ; 14, or 9
        ret                     ; 11
.cell:  ld a, l                 ;  5
        add a, 7                ;  8  the last line of the cell above
        ld l, a                 ;  5
        dec h                   ;  5
        djnz upr                ; 14, or 9
        ret                     ; 11

; blank: BUF all paper: 96 bytes in each of its twelve pages, by PUSH from
;        each page's 96th byte down; the interrupt off while SP points into
;        it. Uses BC, DE, HL
blank:  di                      ;  5
        ld (savesp), sp         ; 22  the stack, for the way out
        ld de, 0                ; 11  paper
        ld hl, BUF + 96         ; 11  past the first page's 96 bytes
        ld c, 12                ;  8  twelve pages
.page:  ld sp, hl               ;  7
        ld b, 6                 ;  8  six times 16 bytes
.push:  push de                 ; 12
        push de                 ; 12
        push de                 ; 12
        push de                 ; 12
        push de                 ; 12
        push de                 ; 12
        push de                 ; 12
        push de                 ; 12
        djnz .push              ; 14, or 9
        inc h                   ;  5  the next page
        dec c                   ;  5
        jr nz, .page            ; 13, or 8
        ld sp, (savesp)         ; 22  the stack again
        ei                      ;  5
        ret                     ; 11
"""


def maze_setup():
    fixed = fixed_patterns()
    return start_lines(GRAPHIC2_THREE, MAZE_BORDER) + f"""        ld a, {16 * START[0] + START[1]}
        ld (pos), a
        ld a, {START[2]}
        ld (face), a
        ld a, 1
        ld (wset), a             ; set 0 to be sent first
        ld a, $FF
        ld (was), a             ; no key held before
        VRAM_WRITE $2000        ; all the colours black on white: the
        ld c, VDP_DATA          ; patterns the names use are written below
        ld a, ${INK_PAPER:02X}
        ld d, 24                ; pages of 256 bytes: 24
.col:   ld b, 0
.cb:    out (c), a
        djnz .cb
        dec d
        jr nz, .col
        ld hl, fixed            ; the patterns that never change, in each
        ld d, {3 * len(fixed)}                 ; third: each its address and 8 bytes
.fix:   ld a, (hl)
        out (VDP_CTRL), a
        inc hl
        ld a, (hl)
        out (VDP_CTRL), a
        inc hl
        ld bc, 8 << 8 | VDP_DATA
        otir
        dec d
        jr nz, .fix
        VRAM_WRITE $1800        ; the names: the window, its frame, the map
        ld hl, screen
        ld c, VDP_DATA
        ld b, 0
        otir
        otir
        otir
        VRAM_WRITE SPAT         ; the four arrows, 8 x 8
        ld hl, arrows
        ld b, 32
        otir
        call view               ; the first view
        call send               ; into set 0
        call flip               ; and shown, with the arrow
        jp on

on:
""" + end_lines(0xE0)


def piece_data(label, lines):
    out = [f"{label}:"]
    for kind, x, y, n in lines:
        addr, mask = buf_at(x, y)
        out.append(f"        db {kind}, ${mask:02X}, {n}".ljust(32) +
                   f"; {KIND_NAMES[kind]} from ({x}, {y}), {n} pixels")
        out.append(f"        dw ${addr:04X}")
    out.append("        db 4")
    return "\n".join(out) + "\n"


def pieces_data():
    table, body = [], ""
    for k in range(4):
        names = []
        for side in (-1, 1):
            for wall in (0, 1):
                lab = f"p{k}{'lr'[side > 0]}{'ow'[wall]}"
                body += piece_data(lab, piece_lines(k, side, wall))
                names.append(lab)
        lab = f"front{k + 1}"
        body += piece_data(lab, front_lines(k + 1))
        names.append(lab)
        table.append(f"        dw {', '.join(names)}".ljust(32) + f"; segment {k}")
    return ("pieces:                         ; each segment's: open left, wall left, open right,\n"
            "                                ; wall right, the wall ahead after it\n" +
            "\n".join(table) + "\n" + body)


def maze_data():
    fixed = fixed_patterns()
    at = []
    for s in (0, 1):
        lab = f"at{s}:".ljust(32) + f"; set {s}: each row's first pattern, for writing\n"
        rows = []
        for i in range(12):
            t, _, _ = window_rows()[i]
            rows.append((0x800 * t + 8 * window_pattern(s, i, 0)) | 0x4000)
        at.append(lab + "".join(f"        dw ${a:04X}\n" for a in rows))
    wn = [window_pattern(s, i, c) for s in (0, 1) for i in range(12) for c in range(12)]
    return ("        ALIGN 256\ncells:                          ; the maze: 1 a wall, 16 x 16\n" +
            db_rows([v for row in MAZE for v in row], 16) +
            "ways:                           ; each way's steps: ahead, left, right\n" +
            db_rows(ways(), 12) + "".join(at) +
            "wnames:                         ; the window's names: set 0's, then set 1's\n" +
            db_rows(wn, 12) +
            "fixed:                          ; the patterns that never change: address, 8 bytes\n" +
            "".join(f"        dw ${(0x800 * t + 8 * p) | 0x4000:04X}\n" + db_rows(b)
                    for t in range(3) for p, b in fixed.items()) +
            "screen:                         ; the 768 names at the start\n" + db_rows(screen_names(0), 16) +
            "arrows:                         ; the arrow for each way, 8 x 8\n" +
            db_rows([v for f in range(4) for v in rows8(*ARROWS[f])]) +
            "first:                          ; the arrow's attributes before mark, and the end\n" +
            db_rows([0xD1, 0, 0, ARROW_COLOUR, 0xD0]) +
            demo_data(MAZE_DEMO, "along the right-hand wall") + pieces_data())


def maze_prog():
    say = """; A maze seen from inside: the corridor ahead in perspective, four cells deep,
; drawn into BUF, laid out as the patterns (chapter 25); sent in the next
; frame into the set of the window's patterns not shown, and shown in the one
; after by turning the window's names to it. A map, and an arrow, a sprite,
; where the explorer stands. The demo's keys follow the right-hand wall.
"""
    return program("maze", "a maze seen from inside", say, MAZE_RAM, MAZE_CONSTS, maze_setup(),
                   MAZE_SENDS + flip_routine() + MAZE_RUN, maze_data())


# ================================================================ the workshop's variants
WINDOW1 = """
; window1: A = a column -> the scrolling rows of the window at that column
;          into the table shown, straight after show, with OTIR
window1: ld e, a
        ld l, a
        ld h, high pmap
        VRAM_WRITE $1800 + 32
        ld c, VDP_DATA
        ld d, 4
.r1:    ld b, 32
        otir
        inc h
        ld l, e
        dec d
        jr nz, .r1
        VRAM_WRITE $1800 + 32 * 17
        ld d, 7
.r2:    ld b, 32
        otir
        inc h
        ld l, e
        dec d
        jr nz, .r2
        ret
"""


def swap(src, old, new):
    old, new = tidy(old), tidy(new)
    assert src.count(old) == 1, old[:60]
    return src.replace(old, new)


def variant(kind):
    """the workshop's variants: (program, source)"""
    if kind == "one":           # question 1: one name table
        src = cave()
        src = swap(src, """        ld a, (table)           ; 14
        xor $18 ^ $1C           ;  8  the other table: the next window
        ld (table), a           ; 14
        rrca                    ;  5
        rrca                    ;  5  $06 or $07, R#2's
        out (VDP_CTRL), a       ; 12
        ld a, $80 | 2           ;  8
        out (VDP_CTRL), a       ; 12
        ret                     ; 11
""", """        ld a, (col)             ; 14  the new window, into the table shown
        jp window1              ; 11
""")
        src = swap(src, """        ld a, (col)             ; 14
        inc a                   ;  5
        and W - 1               ;  8  the next window's column, round
        call window             ; 18
""", "")
        at = tidy("""        jr nz, names            ; 13, or 8
        ret                     ; 11
""")
        assert src.count(at) == 1
        src = src.replace(at, at + tidy(WINDOW1))
        return "cave", src
    if kind == "gravity":       # question 3: half the gravity
        src = jump().replace(f"GRAVITY EQU ${GRAVITY:04X}", f"GRAVITY EQU ${GRAVITY // 2:04X}")
        return "jump", src
    if kind == "keep":          # question 4: the new y kept at a landing
        src = swap(jump(), """        ld a, c                 ;  5
        sub 16                  ;  8
        ld (ry), a              ; 14  the feet on the ledge's top
        xor a                   ;  5
        ld (yfrac), a           ; 14
        ld h, a                 ;  5
        ld l, a                 ;  5
        ld (vy), hl             ; 17  still
        inc a                   ;  5
""", """        ld a, h                 ;  5
        ld (ry), a              ; 14  the new y kept
        ld a, l                 ;  5
        ld (yfrac), a           ; 14
        ld hl, 0                ; 11
        ld (vy), hl             ; 17  still
        ld a, 1                 ;  8
""")
        return "jump", src
    if kind == "now":           # question 5: a view sent in the frame that draws it
        src = swap(maze_prog(), """.draw:  call view               ; 18  the view from there
        ld a, 1                 ;  8
        ld (stage), a           ; 14  to be sent
        ret                     ; 11
""", """.draw:  call view               ; 18  the view from there
        jp send                 ; 11  and sent at once
""")
        return "maze", src
    if kind == "ldir":          # question 6: blank with LDIR
        old = MAZE_RUN[MAZE_RUN.index("blank:  di"):]
        src = swap(maze_prog(), old, """blank:  ld hl, BUF              ; 11
        ld a, 12                ;  8  twelve pages
.page:  ld (hl), 0              ; 11  the first byte paper,
        ld d, h                 ;  5
        ld e, 1                 ;  8
        ld bc, 95               ; 11
        ldir                    ; 23 a byte, 18 the last  and copied on 95 times
        ld l, 0                 ;  8
        inc h                   ;  5  the next page
        dec a                   ;  5
        jr nz, .page            ; 13, or 8
        ret                     ; 11
""")
        return "maze", src
    raise KeyError(kind)


VARIANTS = ["one", "gravity", "keep", "now", "ldir"]


# ================================================================ main
PROGRAMS = {"cave": cave, "jump": jump, "maze": maze_prog}


def main():
    for name, make in PROGRAMS.items():
        with open(os.path.join(HERE, f"{name}.asm"), "w") as f:
            f.write(make())
    print(" ".join(f"{n}.asm" for n in PROGRAMS), f"pairs {NP}",
          f"demo pairs {len(CAVE_DEMO)}/{len(JUMP_DEMO)}/{len(MAZE_DEMO)}")


if __name__ == "__main__":
    main()
