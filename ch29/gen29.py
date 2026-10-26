#!/usr/bin/env python3
"""gen29.py - the programs of chapter 29: scrolling without hardware help.

    python3 gen29.py && ./build.sh

    coarse.asm     a level twice as wide as the screen, a column of tiles a
                   frame: the window's names built in the RAM while the paper
                   is drawn, sent with OTIR after it (figure 29.1)
    flip.asm       the same, with two name tables: the next window written to
                   the one not shown, during the paper, and R#2 changed after
    sets.asm       a pixel a frame: eight shifted sets of the level's pairs of
                   tiles, and every frame the names of the next set, written
                   to the table not shown (figure 29.2)
    pairs.asm      a pixel a frame: the pairs' patterns rewritten every frame,
                   the names only every eighth (figure 29.2)
    vertical.asm   chapter 24's screens, a line a frame upwards: pairs of
                   tiles one above the other, shapes and colours (figure 29.3)
    pillar.asm     WHERE IT BREAKS: pairs.asm's level with a pillar of bricks
                   in the sky, whose colours are not the sky's (figure 29.4)

Graphic II with one set of shapes and colours for the three thirds (R#3 =
$9F, R#4 = $00, chapter 24). Rows 0 to 20 of names scroll; rows 21 to 23, the
status line, never change. Every program draws with the display off first,
keeps the interrupts off and waits for the end of the paper on the status
(chapter 19), ends with asmparts.CART_END, and build.sh assembles with
--syntax=bFw.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "ch24"))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "ch26"))
from asmparts import HEAD, CART_END  # noqa: E402
import gen24  # noqa: E402  (chapter 24)
from gen26 import tidy, db_rows  # noqa: E402  (chapter 26)

BIOS = '        INCLUDE "bios.inc"\n'
BLACK, LIGHT_GREEN, DARK_BLUE, WHITE = 1, 3, 4, 15
ROWS = 21                   # rows of names that scroll; 21 to 23 are the status line
TABLES = (0x1800, 0x1C00)   # the two name tables: R#2 = 6 and 7
FIRST_TEXT = 240            # the status line's patterns, 240 to 255
WIN_RAM = 0xC400            # coarse.asm: the window's names, a copy


def head(name, what):
    return HEAD.format(name=name, chapter=29, what=what) + BIOS


def rows8(*lines):
    return [int(line.replace(".", "0").replace("#", "1"), 2) for line in lines]


# ------------------------------------------------------------------ the level
SKY = BLACK << 4 | WHITE
HILL = DARK_BLUE << 4 | WHITE
GRASS = [LIGHT_GREEN << 4 | WHITE] * 4 + [BLACK << 4 | LIGHT_GREEN] * 4
EARTH = [BLACK << 4 | LIGHT_GREEN] * 8
BRICK = BLACK << 4 | DARK_BLUE
TILES = [   # name, 8 shape bytes, 8 colour bytes: tile n is name n
    ("sky", [0] * 8, [SKY] * 8),
    ("cloud_tl", rows8("........", "........", "......##", ".....#..",
                       "....#...", "..##....", ".#......", "#......."), [SKY] * 8),
    ("cloud_tm", rows8("..####..", ".#....#.", "#......#", "........",
                       "........", "........", "........", "........"), [SKY] * 8),
    ("cloud_tr", rows8("........", "........", "##......", "..#.....",
                       "...#....", "....##..", "......#.", ".......#"), [SKY] * 8),
    ("cloud_bl", rows8("#.......", ".#......", "..######", "........",
                       "........", "........", "........", "........"), [SKY] * 8),
    ("cloud_bm", rows8("........", "........", "########", "........",
                       "........", "........", "........", "........"), [SKY] * 8),
    ("cloud_br", rows8(".......#", "......#.", "######..", "........",
                       "........", "........", "........", "........"), [SKY] * 8),
    ("bird", rows8("........", "........", "##....##", "..#..#..",
                   "...##...", "........", "........", "........"), [SKY] * 8),
    ("hsky", [0] * 8, [HILL] * 8),
    ("hill_l", rows8(".......#", "......##", ".....###", "....####",
                     "...#####", "..######", ".#######", "########"), [HILL] * 8),
    ("hill_r", rows8("#.......", "##......", "###.....", "####....",
                     "#####...", "######..", "#######.", "########"), [HILL] * 8),
    ("hill", [0xFF] * 8, [HILL] * 8),
    ("grass", rows8("........", ".#...#..", "##.#.##.", "########",
                    "........", "..#.....", "......#.", "........"), GRASS),
    ("flower", rows8("...#....", "..#.#...", "...#.#..", "####.###",
                     "...#....", "..#.....", "......#.", "........"), GRASS),
    ("earth", rows8("........", "..#.....", "........", "......#.",
                    "........", ".#......", "....#...", "........"), EARTH),
    ("stone", rows8("........", "..###...", ".#####..", ".######.",
                    "..####..", "........", "....#...", "........"), EARTH),
    ("brick", [0xFF, 0x80, 0x80, 0x80, 0xFF, 0x08, 0x08, 0x08], [BRICK] * 8),
]
TILE = {name: n for n, (name, _, _) in enumerate(TILES)}
WIDTH = 64                  # columns of the level: two screens


def level(pillar=False):
    """the level: 21 rows of 64 tile numbers"""
    m = ([["sky"] * WIDTH for _ in range(16)] +
         [["hsky"] * WIDTH for _ in range(2)] +
         [["grass"] * WIDTH] + [["earth"] * WIDTH for _ in range(2)])
    for r, c in ((2, 3), (5, 17), (3, 29), (8, 41), (2, 52)):
        m[r][c:c + 3] = ["cloud_tl", "cloud_tm", "cloud_tr"]
        m[r + 1][c:c + 3] = ["cloud_bl", "cloud_bm", "cloud_br"]
    for r, c in ((10, 9), (12, 24), (7, 35), (11, 47), (6, 60)):
        m[r][c] = "bird"
    for c, w in ((4, 2), (15, 4), (30, 1), (42, 3), (55, 2)):
        m[16][c], m[16][c + w + 1] = "hill_l", "hill_r"
        m[16][c + 1:c + w + 1] = ["hill"] * w
        m[17][c - 1], m[17][c + w + 2] = "hill_l", "hill_r"
        m[17][c:c + w + 2] = ["hill"] * (w + 2)
    for c in (3, 11, 19, 26, 34, 45, 53, 61):
        m[18][c] = "flower"
    for r, c in ((19, 7), (20, 14), (19, 22), (20, 33), (19, 39), (20, 50),
                 (19, 58)):
        m[r][c] = "stone"
    if pillar:
        for r in range(9, 16):
            m[r][PILLAR] = "brick"
    return [[TILE[t] for t in row] for row in m]


PILLAR = 21                 # pillar.asm: the column of the bricks


# ------------------------------------------------------------------ pairs
def pairs_of(lvl):
    """every pair of tiles side by side in the level, in the order met, and
    for each cell but the last column the number of its pair"""
    pairs, pmap = [], []
    for row in lvl:
        out = []
        for a, b in zip(row, row[1:]):
            if (a, b) not in pairs:
                pairs.append((a, b))
            out.append(pairs.index((a, b)))
        pmap.append(out)
    return pairs, pmap


def shifted(a, b, s):
    """the 8 shape bytes of tile a and tile b side by side, s pixels on: the
    window's cell when the level has moved s pixels left"""
    return [((ra << 8 | rb) << s >> 8) & 0xFF
            for ra, rb in zip(TILES[a][1], TILES[b][1])]


def pair_colours(a, b):
    """a pair takes its left tile's colours: the same as the right one's,
    in a level whose colours do not change along a row"""
    return list(TILES[a][2])


def vpairs_of(rows):
    """pairs of tiles one above the other, for vertical.asm: the pairs, and
    for each cell but the last row the number of its pair"""
    pairs, pmap = [], []
    for top, below in zip(rows, rows[1:]):
        out = []
        for a, b in zip(top, below):
            if (a, b) not in pairs:
                pairs.append((a, b))
            out.append(pairs.index((a, b)))
        pmap.append(out)
    return pairs, pmap


V_TILES = gen24.TILES       # vertical.asm: chapter 24's tiles ...
V_ROWS = [gen24.names_of(gen24.MAP)[32 * r:32 * r + 32] for r in range(24)] + \
         [gen24.names_of(gen24.MAP2)[32 * r:32 * r + 32] for r in range(24)]   # ... and screens


def vshifted(a, b, s):
    """tile a above tile b, s lines on: their shapes and their colours"""
    sa, ca = V_TILES[a][1], V_TILES[a][2]
    sb, cb = V_TILES[b][1], V_TILES[b][2]
    return list(sa[s:]) + list(sb[:s]), list(ca[s:]) + list(cb[:s])


# ------------------------------------------------------------------ the status line
FONT = {    # 6 x 7 letters, white on black
    " ": [0] * 8,
    "S": rows8("..###...", ".#...#..", ".#......", "..###...", ".....#..", ".#...#..", "..###...", "........"),
    "C": rows8("..###...", ".#...#..", ".#......", ".#......", ".#......", ".#...#..", "..###...", "........"),
    "O": rows8("..###...", ".#...#..", ".#...#..", ".#...#..", ".#...#..", ".#...#..", "..###...", "........"),
    "R": rows8(".####...", ".#...#..", ".#...#..", ".####...", ".#.#....", ".#..#...", ".#...#..", "........"),
    "E": rows8(".#####..", ".#......", ".#......", ".####...", ".#......", ".#......", ".#####..", "........"),
    "0": rows8("..###...", ".#...#..", ".#..##..", ".#.#.#..", ".##..#..", ".#...#..", "..###...", "........"),
    "1": rows8("...#....", "..##....", "...#....", "...#....", "...#....", "...#....", "..###...", "........"),
    "2": rows8("..###...", ".#...#..", ".....#..", "....#...", "...#....", "..#.....", ".#####..", "........"),
    "5": rows8(".#####..", ".#......", ".####...", ".....#..", ".....#..", ".#...#..", "..###...", "........"),
}
TEXT_C = WHITE << 4 | BLACK
STATUS = "SCORE 001250"
GLYPHS = list(FONT)


def status_names():
    """the 96 names of rows 21 to 23: the text in the middle row"""
    blank = FIRST_TEXT + GLYPHS.index(" ")
    names = [blank] * 96
    at = 32 + (32 - len(STATUS)) // 2
    for k, ch in enumerate(STATUS):
        names[at + k] = FIRST_TEXT + GLYPHS.index(ch)
    return names


# ------------------------------------------------------------------ paths
COARSE_FRAMES, FINE_FRAMES = 32, 64


def coarse_path():
    """the window's first column, send by send"""
    return list(range(COARSE_FRAMES))


def flip_path():
    return list(range(1, COARSE_FRAMES + 1))


def fine_path():
    """the level's pixels gone past the left edge, send by send"""
    return list(range(1, FINE_FRAMES + 1))


# ------------------------------------------------------------------ the model
def vram_of(kind, at, pillar=False):
    """the 16 KB of VRAM a program shows, at window column, pixel or line AT:
    the shapes, the colours and the names of the table R#2 shows, the status
    line, and R#2"""
    v = bytearray(16384)
    names = [0] * 768
    if kind in ("coarse", "flip"):
        lvl = level()
        for n, (_, s, c) in enumerate(TILES):
            v[8 * n:8 * n + 8], v[0x2000 + 8 * n:0x2000 + 8 * n + 8] = bytes(s), bytes(c)
        for r in range(ROWS):
            names[32 * r:32 * r + 32] = lvl[r][at:at + 32]
    elif kind in ("sets", "pairs", "pillar"):
        lvl = level(pillar=kind == "pillar")
        pairs, pmap = pairs_of(lvl)
        w, s = divmod(at, 8)
        sets = range(8) if kind == "sets" else [s]
        for t in sets:
            for p, (a, b) in enumerate(pairs):
                n = (t * len(pairs) if kind == "sets" else 0) + p
                v[8 * n:8 * n + 8] = bytes(shifted(a, b, t))
                v[0x2000 + 8 * n:0x2000 + 8 * n + 8] = bytes(pair_colours(a, b))
        for r in range(ROWS):
            names[32 * r:32 * r + 32] = [(s * len(pairs) if kind == "sets" else 0) + p
                                         for p in pmap[r][w:w + 32]]
    elif kind == "vertical":
        pairs, pmap = vpairs_of(V_ROWS)
        w, s = divmod(at, 8)
        for p, (a, b) in enumerate(pairs):
            sh, co = vshifted(a, b, s)
            v[8 * p:8 * p + 8], v[0x2000 + 8 * p:0x2000 + 8 * p + 8] = bytes(sh), bytes(co)
        for r in range(ROWS):
            names[32 * r:32 * r + 32] = pmap[w + r]
    names[ROWS * 32:] = status_names()
    for k, ch in enumerate(GLYPHS):
        n = FIRST_TEXT + k
        v[8 * n:8 * n + 8] = bytes(FONT[ch])
        v[0x2000 + 8 * n:0x2000 + 8 * n + 8] = bytes([TEXT_C] * 8)
    table = TABLES[shown_table(kind, at)]
    v[table:table + 768] = bytes(names)
    v[0x1B00] = 0xD0
    return v


def shown_table(kind, at):
    """which name table R#2 shows: 0 for $1800, 1 for $1C00"""
    if kind == "coarse":
        return 0
    if kind == "flip":
        return at % 2              # window 1 in table 1, 2 in table 0, ...
    if kind == "sets":
        return at % 2              # a table a frame, as flip.asm
    return (at // 8) % 2           # pairs, pillar, vertical: a table every eighth frame


def regs_of(kind, at):
    return [2, 0xC0, 6 + shown_table(kind, at), 0x9F, 0, 0x36, 7, 0x0F]


# ------------------------------------------------------------------ routines
SETUP = """init:   di
        ld sp, SYS_AREA
        VDP_REG 1, $80          ; display off
        VDP_REG 0, $02          ; Graphic II
        VDP_REG 2, $06          ; names    $1800, and $1C00 with R#2 = 7
        VDP_REG 3, $9F          ; colours  $2000, one set for three thirds
        VDP_REG 4, $00          ; shapes   $0000, one set for three thirds
        VDP_REG 5, $36          ; sprite attributes $1B00
        VDP_REG 6, $07          ; sprite patterns   $3800
        VDP_REG 7, $0F          ; border white
        VRAM_WRITE $1B00        ; no sprites
        ld a, $D0
        out (VDP_DATA), a
        VRAM_WRITE {text_pat}        ; the status line's letters
        ld hl, glyphs
        ld c, VDP_DATA
        ld b, {nglyph}
        otir
        VRAM_WRITE {text_col}        ; white on black
        ld b, {nglyph}
.tc:    ld a, {text_c}
        out (VDP_DATA), a
        djnz .tc
        VRAM_WRITE {status0}        ; the status line, in both tables
        ld hl, status
        ld b, 96
        otir
        VRAM_WRITE {status1}
        ld hl, status
        ld b, 96
        otir
"""

FRAME = """
; frame: wait for the end of the paper: F, bit 7 of the status, read with the
; interrupts off (chapter 19)
frame:  in a, (VDP_CTRL)
        rla
        jr nc, frame
        ret
"""
ON = """        VDP_REG 1, $C0          ; the display on
        in a, (VDP_CTRL)        ; F cleared: the first wait ends with a paper
"""
DONE = "done:   jr done\n"


def loop(frames):
    return f"""        ld a, {frames}
        ld (count), a
loop:   call frame              ; the end of the paper
m0:     call show               ; what must change after the paper
m1:     call step               ; the next frame's work, while the paper is drawn
s1:     ld hl, count
        dec (hl)
        jr nz, loop
"""


def shapes_block(name, tiles):
    return (f"{name}:\n" + db_rows([b for _, s, _ in tiles for b in s]) +
            f"{name}_c:\n" + db_rows([b for _, _, c in tiles for b in c]))


def common_data():
    return ("glyphs:                         ; the status line's letters: " +
            "".join(GLYPHS).replace(" ", "space ") + "\n" +
            db_rows([b for ch in GLYPHS for b in FONT[ch]]) +
            "status:                         ; rows 21 to 23 of names\n" + db_rows(status_names(), 16))


def program(name, what, say, ram, body, routines, data):
    setup = SETUP.format(text_pat=f"${8 * FIRST_TEXT:04X}", text_col=f"${0x2000 + 8 * FIRST_TEXT:04X}",
                         nglyph=8 * len(GLYPHS), text_c=f"${TEXT_C:02X}",
                         status0=f"${TABLES[0] + 32 * ROWS:04X}", status1=f"${TABLES[1] + 32 * ROWS:04X}")
    return (head(name, what) + ram + say + tidy(setup + body + DONE + FRAME + routines) +
            data + common_data() + CART_END)


RAM = f"""count   EQU VARS                ; the frames left
at      EQU VARS + 1            ; the window's column, or the pixels gone by
table   EQU VARS + 3            ; the name table not shown: $18 or $1C, the high byte
ROWS    EQU {ROWS}
WIDTH   EQU {WIDTH}
"""


# ------------------------------------------------------------------ coarse.asm
COARSE = f"""
; show: the window's names from the copy, 672 bytes with OTIR, after the paper
show:   VRAM_WRITE $1800
        ld hl, win
        ld c, VDP_DATA
        ld b, 0
        otir                    ; 256
        otir                    ; 256
        ld b, ROWS * 32 - 512
        otir                    ; and 160
        ret

; step: the window a column on, its names built in the copy: a row of 32
; from each row of the level
step:   ld hl, at
        inc (hl)
build:  ld a, (at)
        ld e, a
        ld d, 0
        ld hl, level
        add hl, de              ; the level's column at the window's left
        ld de, win
        ld a, ROWS
.row:   ld bc, 32
        ldir                    ; a row of the window
        ld bc, WIDTH - 32
        add hl, bc              ; the level's next row
        dec a
        jr nz, .row
        ret
"""


def coarse():
    lvl = level()
    return program("coarse", "a column of tiles a frame", f"""; A level of {WIDTH} columns, twice the screen. Every frame the window moves a column:
; its 672 names are built in a copy in the RAM while the paper is drawn, and
; sent with OTIR after the paper. Rows 21 to 23, the status line, never change.
win     EQU ${WIN_RAM:04X}               ; the window's 672 names, a copy
""", RAM, f"""        VRAM_WRITE $0000        ; the tiles
        ld hl, tiles
        ld b, {8 * len(TILES)}
        otir
        VRAM_WRITE $2000
        ld hl, tiles_c
        ld b, {8 * len(TILES)}
        otir
        xor a
        ld (at), a
        call build              ; the first window
        call show
""" + ON + loop(COARSE_FRAMES), COARSE,
        shapes_block("tiles", TILES) + "level:                          ; 21 rows of 64 tiles\n" +
        db_rows([t for row in lvl for t in row], 16))


# ------------------------------------------------------------------ flip.asm
FLIP = """
; show: the table written during the paper shown, with R#2, and the other
; one taken for the next window
show:   ld a, (table)
        cp $18
        ld a, 6                 ; R#2 = 6: $1800
        jr z, .r2
        inc a                   ; R#2 = 7: $1C00
.r2:    out (VDP_CTRL), a
        ld a, $80 | 2
        out (VDP_CTRL), a
        ld a, (table)
        xor $18 ^ $1C
        ld (table), a           ; the other table, now not shown
        ret

; step: the window a column on, written into the table not shown, at 29
; T-states a byte, which the paper allows (chapter 20)
step:   ld hl, at
        inc (hl)
write:  xor a
        out (VDP_CTRL), a
        ld a, (table)
        or $40
        out (VDP_CTRL), a       ; the table's first name, for writing
        ld a, (at)
        ld e, a
        ld d, 0
        ld hl, level
        add hl, de              ; the level's column at the window's left
        ld c, VDP_DATA
        ld e, ROWS
.row:   ld b, 32
.name:  outi                    ; 18
        jp nz, .name            ; 11
        ld a, l
        add a, WIDTH - 32
        ld l, a
        jr nc, .next
        inc h                   ; the level's next row
.next:  dec e
        jr nz, .row
        ret
"""


def flip():
    lvl = level()
    return program("flip", "two name tables", """; coarse.asm with two name tables, at $1800 and $1C00: each window written to
; the one not shown while the paper is drawn, and shown with R#2 after it.
""", RAM, f"""        VRAM_WRITE $0000        ; the tiles
        ld hl, tiles
        ld b, {8 * len(TILES)}
        otir
        VRAM_WRITE $2000
        ld hl, tiles_c
        ld b, {8 * len(TILES)}
        otir
        xor a
        ld (at), a
        ld a, $18
        ld (table), a
        call write              ; window 0 in the table at $1800
        ld a, $1C
        ld (table), a
        call step               ; window 1 in the table at $1C00, not shown
""" + ON + loop(COARSE_FRAMES), FLIP,
        shapes_block("tiles", TILES) + "level:                          ; 21 rows of 64 tiles\n" +
        db_rows([t for row in lvl for t in row], 16))


# ------------------------------------------------------------------ sets.asm
SETS = """
; show: the table written during the paper shown, with R#2
show:   ld a, (table)
        cp $18
        ld a, 6
        jr z, .r2
        inc a
.r2:    out (VDP_CTRL), a
        ld a, $80 | 2
        out (VDP_CTRL), a
        ld a, (table)
        xor $18 ^ $1C
        ld (table), a
        ret

; step: a pixel on; into the table not shown, the names of the set of the
; new shift: pair + shift x {np}, the shift the pixels AND 7
step:   ld hl, (at)
        inc hl
        ld (at), hl
names:  xor a
        out (VDP_CTRL), a
        ld a, (table)
        or $40
        out (VDP_CTRL), a       ; the table's first name, for writing
        ld hl, (at)
        ld a, l
        and 7
        ld b, a
        xor a
.set:   dec b
        jp m, .x
        add a, {np}
        jr .set
.x:     ld d, a                 ; D: the shift x {np}, the set's first pattern
        srl h
        rr l
        srl h
        rr l
        srl h
        rr l                    ; HL: the window's column, the pixels / 8
        ld bc, pmap
        add hl, bc              ; its first pair
        ld e, ROWS
.row:   ld b, 32
.name:  ld a, (hl)              ;  8  the pair
        add a, d                ;  5  in the set of the shift
        out (VDP_DATA), a       ; 12
        inc hl                  ;  7
        djnz .name              ; 14: 46 T-states a name
        ld bc, WIDTH - 1 - 32
        add hl, bc              ; the next row of pairs
        dec e
        jr nz, .row
        ret
"""


def sets():
    lvl = level()
    pairs, pmap = pairs_of(lvl)
    np_ = len(pairs)
    pats = [b for s in range(8) for a, b2 in pairs for b in shifted(a, b2, s)]
    cols = [b for s in range(8) for a, b2 in pairs for b in pair_colours(a, b2)]
    return program("sets", "eight shifted sets of pairs", f"""; A pixel a frame. The level's {np_} pairs of tiles side by side, shifted 0 to 7
; pixels: eight sets of {np_} patterns, {8 * np_} in all. Every frame the names of the
; next set go to the table not shown, during the paper, and R#2 shows them.
""", RAM, f"""        VRAM_WRITE $0000        ; the eight sets: {8 * np_} patterns
        ld hl, sets
        ld de, {8 * len(pats) // 8}
        call many
        VRAM_WRITE $2000        ; their colours
        ld hl, sets_c
        ld de, {len(cols)}
        call many
        ld hl, 0
        ld (at), hl
        ld a, $18
        ld (table), a
        call names              ; pixel 0 in the table at $1800
        ld a, $1C
        ld (table), a
        call step               ; pixel 1 in the table at $1C00, not shown
""" + ON + loop(FINE_FRAMES), SETS.replace("{np}", str(np_)) + MANY,
        f"sets:                           ; {8 * np_} patterns: set s, pair p at {8 * np_ // 8} x s + p\n" +
        db_rows(pats, 16) + "sets_c:\n" + db_rows(cols, 16) +
        "pmap:                           ; the pairs: 21 rows of 63\n" +
        db_rows([p for row in pmap for p in row], 16))


MANY = """
; many: DE bytes from HL to the VDP, after an address is set (the display off)
many:   ld c, VDP_DATA
.byte:  outi
        dec de
        ld a, d
        or e
        jr nz, .byte
        ret
"""


# ------------------------------------------------------------------ pairs.asm
PAIRS = """
; show: the pairs' patterns at the new shift, {nb} bytes with OTIR, after the
; paper; at shift 0, the table with the next window shown, with R#2
show:   VRAM_WRITE $0000
        ld a, (at)
        and 7
        ld l, a
        ld h, 0
        ld de, {nb}
        call mul                ; HL: the shift x {nb}
        ld de, shifts
        add hl, de              ; the patterns at that shift
        ld c, VDP_DATA
        ld b, {nb}
        otir
        ld a, (at)
        and 7
        ret nz                  ; seven frames in eight, no more
        ld a, (table)
        cp $18
        ld a, 6
        jr z, .r2
        inc a
.r2:    out (VDP_CTRL), a
        ld a, $80 | 2
        out (VDP_CTRL), a
        ld a, (table)
        xor $18 ^ $1C
        ld (table), a
        ret

; step: after a new table is shown, the next window's pairs written into the
; other one, at 46 T-states a name; then a pixel on
step:   ld a, (at)
        and 7
        jr nz, .on
        ld a, (at)
        rrca
        rrca
        rrca
        and 31
        inc a                   ; the next window's column
        call window
.on:    ld hl, at
        inc (hl)
        ret

; window: the pairs of the window at column A into the table not shown
window: ld e, a
        ld d, 0
        ld hl, pmap
        add hl, de              ; its first pair
        xor a
        out (VDP_CTRL), a
        ld a, (table)
        or $40
        out (VDP_CTRL), a       ; the table's first name, for writing
        ld e, ROWS
.row:   ld b, 32
.name:  ld a, (hl)              ;  8
        out (VDP_DATA), a       ; 12
        inc hl                  ;  7
        nop                     ;  5
        djnz .name              ; 14: 46 T-states a name
        ld bc, WIDTH - 1 - 32
        add hl, bc
        dec e
        jr nz, .row
        ret

; mul: HL = HL x DE, HL below 8
mul:    ld b, l
        ld hl, 0
        inc b
.add:   dec b
        ret z
        add hl, de
        jr .add
"""


def pairs_prog(name="pairs"):
    pillar = name == "pillar"
    lvl = level(pillar=pillar)
    pairs, pmap = pairs_of(lvl)
    np_ = len(pairs)
    shp = [b for s in range(8) for a, b2 in pairs for b in shifted(a, b2, s)]
    cols = [b for a, b2 in pairs for b in pair_colours(a, b2)]
    say = (f"""; A pixel a frame, with only {np_} patterns: the level's pairs of tiles side by
; side, rewritten every frame at the new shift from eight copies in the
; cartridge; the names change every eighth frame, written to the table not
; shown during the paper before, and shown with R#2.
""" if not pillar else f"""; WHERE IT BREAKS. pairs.asm's level with a pillar of bricks in the sky, at
; column {PILLAR}: its pairs with the sky take the colours of their left tile.
""")
    return program(name, "pairs rewritten every frame" if not pillar else "a pillar in the sky",
                   say, RAM, f"""        VRAM_WRITE $0000        ; the pairs at shift 0
        ld hl, shifts
        ld b, {8 * np_}
        otir
        VRAM_WRITE $2000        ; their colours, which no shift changes
        ld hl, pcols
        ld b, {8 * np_}
        otir
        ld a, $18
        ld (table), a
        xor a
        call window             ; window 0 in the table at $1800
        ld a, $1C
        ld (table), a
        ld a, 1
        call window             ; window 1 in the table at $1C00, not shown
        ld a, 1
        ld (at), a
""" + ON + loop(FINE_FRAMES), PAIRS.replace("{nb}", str(8 * np_)),
        f"shifts:                         ; the {np_} pairs at shifts 0 to 7, {8 * np_} bytes each\n" +
        db_rows(shp, 16) + "pcols:                          ; their colours\n" + db_rows(cols, 16) +
        "pmap:                           ; the pairs: 21 rows of 63\n" +
        db_rows([p for row in pmap for p in row], 16))


# ------------------------------------------------------------------ vertical.asm
VERT = """
; show: the pairs' shapes and colours at the new line, {nb} bytes of each with
; OTIR, after the paper; at line 0, the table with the next window shown
show:   ld a, (at)
        and 7
        ld l, a
        ld h, 0
        ld de, {nb}
        call mul                ; HL: the line x {nb}
        push hl
        VRAM_WRITE $0000
        ld de, vshapes
        add hl, de
        ld c, VDP_DATA
        ld b, {nb}
        otir                    ; the shapes
        VRAM_WRITE $2000
        pop hl
        ld de, vcols
        add hl, de
        ld b, {nb}
        otir                    ; and the colours, which move with them
        ld a, (at)
        and 7
        ret nz                  ; seven frames in eight, no more
        ld a, (table)
        cp $18
        ld a, 6
        jr z, .r2
        inc a
.r2:    out (VDP_CTRL), a
        ld a, $80 | 2
        out (VDP_CTRL), a
        ld a, (table)
        xor $18 ^ $1C
        ld (table), a
        ret

; step: after a new table is shown, the next window's pairs written into the
; other one; then a line on
step:   ld a, (at)
        and 7
        jr nz, .on
        ld a, (at)
        rrca
        rrca
        rrca
        and 31
        inc a                   ; the next window's first row
        call window
.on:    ld hl, at
        inc (hl)
        ret

; window: the pairs of the window from row A, 21 rows of 32, into the table
; not shown, at 46 T-states a name
window: ld l, a
        ld h, 0
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl              ; 32 x the row
        ld de, vpmap
        add hl, de
        xor a
        out (VDP_CTRL), a
        ld a, (table)
        or $40
        out (VDP_CTRL), a
        ld e, ROWS
.row:   ld b, 32
.name:  ld a, (hl)              ;  8
        out (VDP_DATA), a       ; 12
        inc hl                  ;  7
        nop                     ;  5
        djnz .name              ; 14: 46 T-states a name
        dec e
        jr nz, .row
        ret

; mul: HL = HL x DE, HL below 8
mul:    ld b, l
        ld hl, 0
        inc b
.add:   dec b
        ret z
        add hl, de
        jr .add
"""


def vertical():
    pairs, pmap = vpairs_of(V_ROWS)
    np_ = len(pairs)
    shp, cols = [], []
    for s in range(8):
        for a, b in pairs:
            sh, co = vshifted(a, b, s)
            shp += sh
            cols += co
    return program("vertical", "a line a frame upwards", f"""; Chapter 24's two screens one above the other, a line a frame upwards: the
; {np_} pairs of tiles one above the other, shapes and colours, rewritten every
; frame from eight copies in the cartridge; the names every eighth frame.
""", RAM, f"""        VRAM_WRITE $0000        ; the pairs at line 0
        ld hl, vshapes
        ld b, {8 * np_}
        otir
        VRAM_WRITE $2000
        ld hl, vcols
        ld b, {8 * np_}
        otir
        ld a, $18
        ld (table), a
        xor a
        call window             ; window 0 in the table at $1800
        ld a, $1C
        ld (table), a
        ld a, 1
        call window             ; window 1 in the table at $1C00, not shown
        ld a, 1
        ld (at), a
""" + ON + loop(FINE_FRAMES), VERT.replace("{nb}", str(8 * np_)),
        f"vshapes:                        ; the {np_} pairs at lines 0 to 7, {8 * np_} bytes each\n" +
        db_rows(shp, 16) + "vcols:                          ; and their colours\n" + db_rows(cols, 16) +
        "vpmap:                          ; the pairs: 47 rows of 32\n" +
        db_rows([p for row in pmap for p in row], 16))


def main():
    for name, make in PROGRAMS.items():
        with open(os.path.join(HERE, f"{name}.asm"), "w") as f:
            f.write(make())
    print(" ".join(f"{n}.asm" for n in PROGRAMS))


PROGRAMS = {"coarse": coarse, "flip": flip, "sets": sets, "pairs": pairs_prog,
            "vertical": vertical, "pillar": lambda: pairs_prog("pillar")}

if __name__ == "__main__":
    main()
