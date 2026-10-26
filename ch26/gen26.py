#!/usr/bin/env python3
"""gen26.py - the programs of chapter 26: hardware sprites I.

    python3 gen26.py && ./build.sh

    one.asm        one sprite of 8 x 8: its shape in the pattern table, its
                   four bytes in the attribute table (figure 26.1)
    sizes.asm      four sprites, patterns 0 to 3, through the four sizes R#1
                   chooses: 8 x 8, 8 x 8 magnified, 16 x 16 and 16 x 16
                   magnified (figure 26.2)
    rows.asm       a sprite of 16 x 16 given every Y from 0 to 255, one a frame
    columns.asm    a sprite of 16 x 16 given every X from 0 to 255, and before
                   them X from 0 to 31 with the early clock (figure 26.3)
    edges.asm      four sprites cut by the four edges of the paper (figure 26.4)
    clock.asm      the early clock on sprites magnified to 32 x 32
    order.asm      sprites over one another and over the picture: which is on
                   top, and colour 0 (figure 26.5)
    modes.asm      four sprites through Graphic II, Graphic I, multicolour and
                   text mode (figure 26.6)
    march.asm      32 figures whose shape changes with R#6, between two pattern
                   tables (figure 26.8)
    tear.asm       a new X written while the beam is drawing the sprite (figure
                   26.9)
    herd.asm       32 sprites moved every frame from a copy of the attribute
                   table in the RAM, sent with OTIR after the paper (figure
                   26.7)
    flip.asm       the same, each frame's table sent at 29 T-states a byte to a
                   second table, the one not shown, and R#5 changed after the
                   paper
    fall.asm       WHERE IT BREAKS: a ball falls off the bottom of the paper,
                   and four figures above it are lost in one frame (figure 26.10)
    park.asm       the same, the ball parked at Y = 192
    last.asm       the same, the ball last in the table

Graphic II as a bitmap (chapter 22's GRAPHIC2: black ink on white), the
sprite attributes at $1B00 and the patterns at $3800, as the BIOS puts them
(chapter 21). Every program writes with the display off, then keeps the
interrupts off and waits for the end of the paper on the status (chapter 19);
each ends with asmparts.CART_END, and build.sh assembles with --syntax=bFw.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
from asmparts import HEAD, CART_END, GRAPHIC2  # noqa: E402

BIOS = '        INCLUDE "bios.inc"\n'
BLACK, LIGHT_GREEN, DARK_BLUE, WHITE = 1, 3, 4, 15
ATT, PAT = 0x1B00, 0x3800   # the attribute table and the pattern table
ATT2 = 0x1B80               # flip.asm's second attribute table: R#5 = $37
COPY = 0xC400               # herd.asm's and flip.asm's copy of the attributes
END = 0xD0                  # a Y of 208 ends the attribute table


def head(name, what):
    return HEAD.format(name=name, chapter=26, what=what) + BIOS


def db_rows(data, per=8):
    return "".join("        db " + ", ".join(f"${b:02X}" for b in data[i:i + per]) + "\n"
                   for i in range(0, len(data), per))


# ------------------------------------------------------------------ shapes
def rows8(*lines):
    return [int(l, 2) for l in lines]


DIGITS = [
    rows8("00111100", "01100110", "01101110", "01110110", "01100110", "01100110", "00111100", "00000000"),
    rows8("00011000", "00111000", "00011000", "00011000", "00011000", "00011000", "01111110", "00000000"),
    rows8("00111100", "01100110", "00000110", "00001100", "00110000", "01100000", "01111110", "00000000"),
    rows8("00111100", "01100110", "00000110", "00011100", "00000110", "01100110", "00111100", "00000000")]
ARROW = rows8("11111000", "11110000", "11111000", "11011100", "10001110", "00000111", "00000011",
              "00000001")


def rows16(*lines):
    return [int(l.replace(".", "0").replace("#", "1"), 2) for l in lines]


FIGURE = rows16(
    "......####......", ".....######.....", ".....#.##.#.....", ".....######.....",
    "......#..#......", "...##########...", "..############..", "..##.######.##..",
    "..##.######.##..", "..##.######.##..", ".....######.....", ".....##..##.....",
    ".....##..##.....", ".....##..##.....", "....###..###....", "....###..###....")
FIGURE2 = rows16(
    "..##..####..##..", "..##.######.##..", "..##.#.##.#.##..", "..##.######.##..",
    "..##..#..#..##..", "...##########...", ".....######.....", ".....######.....",
    ".....######.....", ".....######.....", ".....######.....", "....##....##....",
    "...##......##...", "..##........##..", ".###........###.", ".###........###.")
BALL = [sum(0x8000 >> x for x in range(16) if (x - 7.5) ** 2 + (y - 7.5) ** 2 <= 49)
        for y in range(16)]
RING = [sum(0x8000 >> x for x in range(16) if 16 <= (x - 7.5) ** 2 + (y - 7.5) ** 2 <= 56)
        for y in range(16)]
BLOCK = [0xFFFF] * 16


def big(rows):
    """a 16 x 16 shape as four patterns: its left half's 16 bytes, then its
    right half's: top left, bottom left, top right, bottom right"""
    return [r >> 8 for r in rows] + [r & 0xFF for r in rows]


SHAPES = {"digits": 0, "figure": 4, "ball": 8, "ring": 12, "block": 16, "arrow": 20}
PATTERNS = (sum(DIGITS, []) + big(FIGURE) + big(BALL) + big(RING) + big(BLOCK) + ARROW)
assert len(PATTERNS) == 8 * 21


def sprite16(name):
    """the 16 x 16 rows of shape NAME, as the VDP puts its four patterns
    together"""
    p = SHAPES[name] * 8
    return [PATTERNS[p + r] << 8 | PATTERNS[p + 16 + r] for r in range(16)]


# ------------------------------------------------------------------ the parts
SPRITES = f"""        VRAM_WRITE ${PAT:04X}        ; the sprite patterns
        ld hl, patterns
        ld c, VDP_DATA
        ld b, {len(PATTERNS)}
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

DONE = "done:   jr done\n"


def attributes(table, label="atts"):
    """the attribute bytes, (Y, X, pattern, colour) each, and the closing Y"""
    data = [b for s in table for b in s] + ([END] if len(table) < 32 else [])
    return f"{label}:\n" + db_rows(data, 4)


def send_atts(table, label="atts"):
    n = 4 * len(table) + (len(table) < 32)
    return f"""        VRAM_WRITE ${ATT:04X}        ; the attributes
        ld hl, {label}
        ld c, VDP_DATA
        ld b, {n}
        otir
"""


LINE_RE = re.compile(r"^([\w.]+:)?(\s+)(\S.*?)\s*(;.*)?$")


def tidy(text):
    """every instruction at column 8 and its comment at column 32"""
    lines = text.splitlines()
    joined = []
    for line in lines:                  # a label alone goes on the next instruction
        if joined and re.fullmatch(r"[\w.]+:", joined[-1]) and line[:1] == " " and line.strip() \
                and not line.lstrip().startswith(";"):
            joined[-1] = joined[-1] + " " + line.strip()
        else:
            joined.append(line)
    out = []
    for line in joined:
        m = LINE_RE.match(line)
        if not m or not line.strip() or line.lstrip().startswith(";"):
            out.append(line)
            continue
        label, _, code, comment = m.groups()
        lab = (label or "").ljust(8) if len(label or "") < 8 else label + " "
        row = lab + code
        if comment:
            row = row.ljust(31) + " " + comment
        out.append(row)
    return "\n".join(out) + "\n"


def program(name, what, say, body, data="", border=WHITE):
    setup = GRAPHIC2.replace("VDP_REG 7, $0F          ; border white",
                             f"VDP_REG 7, ${border:02X}          ; border "
                             f"{'white' if border == WHITE else 'light green'}")
    assert border == WHITE or setup != GRAPHIC2
    return (head(name, what) + say + setup + tidy(SPRITES + body + DONE + FRAME) +
            "patterns:\n" + db_rows(PATTERNS) + data + CART_END)


def on(r1):
    return f"        VDP_REG 1, ${r1:02X}          ; the display on{SIZE_SAY[r1 & 3]}\n"


CLEAR_F = """        in a, (VDP_CTRL)        ; F cleared: the first wait is for a whole paper
"""


SIZE_SAY = {0: "", 1: ", magnified", 2: ", sprites of 16 x 16",
            3: ", 16 x 16 magnified"}


# ------------------------------------------------------------------ one.asm
ONE = [(87, 120, SHAPES["arrow"], BLACK)]


def one():
    return program("one", "one sprite", f"""; One sprite of 8 x 8: pattern {SHAPES['arrow']}, an arrow, at X = {ONE[0][1]} and Y = {ONE[0][0]}, black;
; sprite 1's Y is 208, the end of the table.
""", send_atts(ONE) + on(0xC0), attributes(ONE))


# ------------------------------------------------------------------ sizes.asm
SIZES_XY = [(79, 16 + 64 * k) for k in range(4)]
SIZES = [(y, x, k, c) for k, ((y, x), c) in enumerate(zip(SIZES_XY, (BLACK, DARK_BLUE, LIGHT_GREEN,
                                                                     BLACK)))]
SIZE_FRAMES = 8             # frames in each size
SIZE_R1 = [0xC0, 0xC1, 0xC2, 0xC3]


def sizes():
    steps = ""
    for k, r1 in enumerate(SIZE_R1):
        steps += f"""        ld b, {SIZE_FRAMES}
w{k}:     call frame
        djnz w{k}
s{k}:
""" + on(r1) + f"e{k}:\n"
    return program("sizes", "the four sizes", f"""; Four sprites, patterns 0 to 3: the digits 0 to 3. Every {SIZE_FRAMES} frames R#1 changes
; the size of all of them: 8 x 8, magnified, 16 x 16, 16 x 16 magnified.
""", send_atts(SIZES) + CLEAR_F + steps, attributes(SIZES))


# ------------------------------------------------------------------ rows.asm
ROWS_X = 120


def rows():
    return program("rows", "every Y", f"""; A sprite of 16 x 16, a block, at X = {ROWS_X}, given every Y from 0 to
; 255, one a frame, after the paper.
""", f"""        VRAM_WRITE ${ATT:04X}        ; sprite 0: Y 0, X {ROWS_X}, a block, black
        xor a
        out (VDP_DATA), a
        ld a, {ROWS_X}
        out (VDP_DATA), a
        ld a, {SHAPES['block']}
        out (VDP_DATA), a
        ld a, {BLACK}
        out (VDP_DATA), a
        ld a, ${END:02X}
        out (VDP_DATA), a       ; sprite 1: the end of the table
""" + on(0xC2) + CLEAR_F + """        ld e, 0                 ; Y
next:   call frame              ; the paper has ended
m0:     VRAM_WRITE $1B00        ; 40  sprite 0's Y
        ld a, e                 ;  5
        out (VDP_DATA), a       ; 12
m1:     inc e
        jr nz, next             ; 256 frames
""")


# ------------------------------------------------------------------ columns.asm
COLS_Y = 87


def columns():
    return program("columns", "every X, and the early clock", f"""; A sprite of 16 x 16, a block, at Y = {COLS_Y}, given X from 0 to 31 with
; the early clock, bit 7 of its colour byte, which draws it 32 pixels left;
; then every X from 0 to 255 without it. One X a frame, after the paper.
""", f"""        VRAM_WRITE ${ATT:04X}        ; sprite 0: Y {COLS_Y}, X 0, a block, black
        ld a, {COLS_Y}
        out (VDP_DATA), a
        xor a
        out (VDP_DATA), a
        ld a, {SHAPES['block']}
        out (VDP_DATA), a
        ld a, {BLACK}
        out (VDP_DATA), a
        ld a, ${END:02X}
        out (VDP_DATA), a       ; sprite 1: the end of the table
""" + on(0xC2) + CLEAR_F + f"""        ld d, ${0x80 | BLACK:02X}               ; the colour byte: black, the early clock on
        ld e, 0                 ; X
early:  call frame
m0:     call place
m1:     inc e
        ld a, e
        cp 32
        jr nz, early
        ld d, {BLACK}                 ; the early clock off
        ld e, 0
late:   call frame
m2:     call place
m3:     inc e
        jr nz, late
""").replace("done:   jr done\n", f"""done:   jr done

; place: sprite 0's X from E, its pattern, and its colour byte from D
place:  VRAM_WRITE $1B01        ; 40
        ld a, e                 ;  5
        out (VDP_DATA), a       ; 12  X
        ld a, {SHAPES['block']}                ;  8
        out (VDP_DATA), a       ; 12  the pattern
        ld a, d                 ;  5
        out (VDP_DATA), a       ; 12  the colour, and the early clock
        ret                     ; 11
""")


# ------------------------------------------------------------------ edges.asm
EDGES = [(247, 40, 0, BLACK, "top"), (183, 200, 0, BLACK, "bottom"),
         (87, 24, 0, BLACK | 0x80, "left, the early clock"), (87, 248, 0, BLACK, "right")]


def edges():
    table = [e[:4] for e in EDGES]
    return program("edges", "four sprites cut by the edges", """; Four sprites of 16 x 16 cut by the edges of the paper: Y = 247 (lines 248
; to 255, then 0 to 7), Y = 183, X = 24 with the early clock (x = -8), and
; X = 248. The border is light green, to show where the paper ends.
""", send_atts(table) + on(0xC2), attributes(table), border=LIGHT_GREEN)


# ------------------------------------------------------------------ clock.asm
CLOCK = [(87, 40, SHAPES["digits"], BLACK | 0x80), (87, 40, SHAPES["digits"], DARK_BLUE),
         (127, 16, SHAPES["digits"], BLACK | 0x80)]


def clock():
    return program("clock", "the early clock, magnified", """; Three sprites of 16 x 16, magnified to 32 x 32: X = 40 with the early clock,
; X = 40 without it, and X = 16 with it.
""", send_atts(CLOCK) + on(0xC3), attributes(CLOCK))


# ------------------------------------------------------------------ order.asm
BANDS = [(40, 56), (120, 136)]          # order.asm: dark blue bands, lines y0 to y1 - 1
ORDER = [(39, 40, SHAPES["block"], 0),               # colour 0, over sprite 1
         (39, 40, SHAPES["block"], BLACK),
         (39, 120, SHAPES["ring"], BLACK),            # over sprite 3
         (43, 128, SHAPES["block"], LIGHT_GREEN),
         (119, 200, SHAPES["ring"], LIGHT_GREEN)]     # over the band


def order():
    bands = ""
    for k, (y0, y1) in enumerate(BANDS):
        bands += f"""        ld c, {y0}                ; lines {y0} to {y1 - 1}: a dark blue band
        ld b, {y1 - y0}
        call band
"""
    return program("order", "sprites over sprites and the picture", """; Two dark blue bands across the paper, and five sprites of 16 x 16: sprite 0,
; colour 0, over sprite 1; sprite 2, a ring, over sprite 3; sprite 4, a ring,
; over the second band.
""", bands + send_atts(ORDER) + on(0xC2), attributes(ORDER)).replace(
        "done:   jr done\n", """done:   jr done

; band: B lines from line C of the paper: every pattern byte $FF and every
; colour byte dark blue on white
band:   push bc
        ld a, c                 ; the byte of (0, y): (y / 8) x 256 + (y AND 7)
        and 7
        ld l, a
        ld a, c
        rrca
        rrca
        rrca
        and $1F
        ld h, a
        ld e, 32                ; 32 strips across, 8 bytes apart
.strip: ld a, l
        out (VDP_CTRL), a
        ld a, h
        or $40
        out (VDP_CTRL), a
        ld a, $FF
        out (VDP_DATA), a       ; the pattern: all ink
        ld a, l
        out (VDP_CTRL), a
        ld a, h
        or $60
        out (VDP_CTRL), a
        ld a, $4F
        out (VDP_DATA), a       ; the colour: dark blue ink on white
        ld a, l
        add a, 8
        ld l, a
        dec e
        jr nz, .strip
        pop bc
        inc c
        djnz band
        ret
""")


# ------------------------------------------------------------------ modes.asm
MODES = [   # R#0, R#1, R#3, R#4, the mode
    (0x02, 0xC2, 0xFF, 0x03, "Graphic II"), (0x00, 0xC2, 0x80, 0x00, "Graphic I"),
    (0x00, 0xCA, 0x80, 0x00, "multicolour"), (0x00, 0xD2, 0x80, 0x00, "text")]
MODE_FRAMES = 8


def modes():
    steps = ""
    for k, (r0, r1, r3, r4, what) in enumerate(MODES):
        steps += f"""        ld b, {MODE_FRAMES}
w{k}:     call frame
        djnz w{k}
s{k}:     VDP_REG 0, ${r0:02X}          ; {what}
        VDP_REG 3, ${r3:02X}
        VDP_REG 4, ${r4:02X}
        VDP_REG 1, ${r1:02X}
e{k}:
"""
    return program("modes", "the sprites in four modes", f"""; sizes.asm's four sprites at 16 x 16, and every {MODE_FRAMES} frames another mode from the
; same tables: Graphic II, Graphic I, multicolour and text. Every pattern byte
; is 0, so the picture is the paper alone, white, in each.
""", send_atts(SIZES) + """        VDP_REG 7, $1F          ; text mode's ink black on white; the border white
""" + CLEAR_F + steps, attributes(SIZES))


# ------------------------------------------------------------------ march.asm
MARCH_PAT = 112             # the figure's four patterns, in both pattern tables
MARCH_TABLES = (0x07, 0x03)  # R#6: $3800, and $1800, whose patterns 112 on are free
MARCH_FRAMES = 8


def march_table():
    return [(y, x, MARCH_PAT, c) for (y, x, p, c) in herd_start()]


def march():
    steps = ""
    for k in range(4):
        r6 = MARCH_TABLES[(k + 1) % 2]
        steps += f"""        ld b, {MARCH_FRAMES}
w{k}:     call frame
        djnz w{k}
s{k}:     VDP_REG 6, ${r6:02X}          ; the patterns at ${r6 * 0x800:04X}
e{k}:
"""
    return program("march", "two pattern tables", f"""; herd.asm's 32 figures, standing, all with pattern {MARCH_PAT}. The pattern table at
; $3800 has one figure there, the one at $1800 another: patterns {MARCH_PAT} on are past
; the names and the attributes. Every {MARCH_FRAMES} frames R#6 changes table.
""", f"""        VRAM_WRITE ${PAT + 8 * MARCH_PAT:04X}        ; pattern {MARCH_PAT} of the table at $3800
        ld hl, pose1
        ld c, VDP_DATA
        ld b, 32
        otir
        VRAM_WRITE ${0x1800 + 8 * MARCH_PAT:04X}        ; pattern {MARCH_PAT} of the table at $1800
        ld hl, pose2
        ld b, 32
        otir
""" + send_atts(march_table()) + on(0xC2) + CLEAR_F + steps,
        attributes(march_table()) + "pose1:\n" + db_rows(big(FIGURE)) + "pose2:\n" +
        db_rows(big(FIGURE2)))


# ------------------------------------------------------------------ tear.asm
TEAR_XS = (64, 160)         # the block's two places
TEAR_Y = 79                 # its first line is 80; magnified, it is 32 lines tall
TEAR_LINE = 96              # the new X is written as the beam draws this line
TEAR_FRAMES = 16
WAIT = {"MSXBOOK_EU16": 27588, "MSXBOOK_JP16": 15960}   # the lines not drawn (chapter 24)


def tear_turns(machine):
    """the wait from the end of the paper to line TEAR_LINE of the next one,
    in turns of 30 T-states"""
    return (WAIT[machine] + 228 * TEAR_LINE) // 30


def tear_table():
    return [(TEAR_Y, TEAR_XS[0], SHAPES["block"], BLACK)]


def tear():
    eu, jp = tear_turns("MSXBOOK_EU16"), tear_turns("MSXBOOK_JP16")
    x0, x1 = TEAR_XS
    return program("tear", "a new X while the beam draws the sprite", f"""; A black block of 16 x 16, magnified, at Y = {TEAR_Y}: lines {TEAR_Y + 1} to {TEAR_Y + 32} of the paper.
; Every frame it gets a new X, {x0} or {x1}, written when the beam is at line {TEAR_LINE},
; inside the block, and not after the paper.
""", send_atts(tear_table()) + on(0xC3) + f"""        ld a, ($002B)           ; bit 7 is 1 on a 50 Hz machine (chapter 4)
        rla
        ld hl, {jp}
        jr nc, sixty
        ld hl, {eu}
sixty:  ld (wait), hl           ; the lines not drawn and {TEAR_LINE} more, in turns
""" + CLEAR_F + f"""        ld d, {x1}                ; the next X
        ld e, {TEAR_FRAMES}                ; frames
next:   call frame              ; the end of the paper
        ld bc, (wait)
turn:   dec bc                  ;  7
        ld a, b                 ;  5
        or c                    ;  5
        jr nz, turn             ; 13: 30 T-states a turn
m0:     VRAM_WRITE $1B01        ; sprite 0's X, with the beam at line {TEAR_LINE}
        ld a, d
        out (VDP_DATA), a
m1:     ld a, d                 ; and the other X next time
        xor {x0} ^ {x1}
        ld d, a
        dec e
        jr nz, next
""", attributes(tear_table())).replace(
        "INCLUDE \"bios.inc\"\n", "INCLUDE \"bios.inc\"\nwait    EQU VARS                ; the wait into the paper, in turns of 30 T\n", 1)


# ------------------------------------------------------------------ herd, flip
HERD_ROWS, HERD_COLS = 8, 4
HERD_FRAMES = 64


def herd_start():
    """32 figures: 8 rows of 4, 22 lines apart, so that no line of the paper
    crosses more than 4 sprites (chapter 27)"""
    out = []
    for r in range(HERD_ROWS):
        for c in range(HERD_COLS):
            out.append((6 + 23 * r, (64 * c + 16 * r) & 0xFF, SHAPES["figure"],
                        (BLACK, DARK_BLUE)[(r + c) % 2]))
    return out


def herd_frames():
    """the attribute table after each move: even rows a pixel right, odd
    rows a pixel left"""
    t = [list(s) for s in herd_start()]
    out = []
    for _ in range(HERD_FRAMES):
        for k, s in enumerate(t):
            s[1] = (s[1] + (1 if (k // HERD_COLS) % 2 == 0 else -1)) & 0xFF
        out.append([b for s in t for b in s])
    return out


STEP = f"""
; step: the copy's 32 sprites moved: even rows of four a pixel right, odd rows
; a pixel left
step:   ld hl, copy + 1         ; sprite 0's X
        ld c, {HERD_ROWS // 2}
.row:   ld b, {HERD_COLS}
.right: inc (hl)                ; X + 1
        ld de, 4
        add hl, de
        djnz .right
        ld b, {HERD_COLS}
.left:  dec (hl)                ; X - 1
        add hl, de
        djnz .left
        dec c
        jr nz, .row
        ret
"""


# ------------------------------------------------------------------ fall, park
FIGS_Y = 60                 # the four figures' Y
FIGS_X = (24, 80, 152, 208)
BALL_X, BALL_Y0, BALL_Y1 = 120, 150, 232    # the ball falls from Y0 to Y1
PARK_Y = 192


def fall_table(last=False):
    ball = [(BALL_Y0, BALL_X, SHAPES["ball"], DARK_BLUE)]
    figs = [(FIGS_Y, x, SHAPES["figure"], BLACK) for x in FIGS_X]
    return figs + ball if last else ball + figs


def fall_ys(park):
    """the ball's Y after each move"""
    out, y = [], BALL_Y0
    while y < BALL_Y1:
        y += 1
        out.append(min(y, PARK_Y) if park else y)
    return out


def fall(name):
    park, last = name == "park", name == "last"
    table = fall_table(last)
    at = ATT + 4 * (len(table) - 1 if last else 0)
    move = """        inc e                   ;  5  a line down
""" if not park else f"""        ld a, e                 ;  5
        cp {PARK_Y}                  ;  8  below the paper:
        jr nc, still            ; 13, or 8  parked, at {PARK_Y}
        inc e                   ;  5  else a line down
still:
"""
    say = {"fall": f"""; WHERE IT BREAKS. Four figures stand at Y = {FIGS_Y}, sprites 1 to 4; sprite 0, a
; ball, falls from Y = {BALL_Y0} a line a frame, past the bottom of the paper, to
; Y = {BALL_Y1}.
""", "park": f"""; fall.asm, with the ball parked at Y = {PARK_Y} once it is below the paper.
""", "last": """; fall.asm, with the ball last in the table: the figures are sprites 0 to 3,
; the ball sprite 4.
"""}[name]
    what = {"fall": "a ball falls off the paper", "park": "the ball parked",
            "last": "the ball last in the table"}[name]
    return program(name, what, say, send_atts(table) + on(0xC2) + CLEAR_F + f"""        ld e, {BALL_Y0}               ; the ball's Y
        ld d, {len(fall_ys(park))}                ; frames
next:
""" + move + f"""        call frame              ; the paper has ended
m0:     VRAM_WRITE ${at:04X}        ; the ball's Y
        ld a, e
        out (VDP_DATA), a
m1:     dec d
        jr nz, next
""", attributes(table))


def herd(name):
    flip = name == "flip"
    what = ("32 sprites moved from a copy, with OTIR" if not flip else
            "32 sprites, two attribute tables")
    say = (f"""; 32 figures of 16 x 16, eight rows of four, moved {HERD_FRAMES} times, a frame each: even
; rows a pixel right, odd rows a pixel left. The moves are made in a copy of
; the attribute table in the RAM, and the copy is sent with OTIR after the paper.
""" if not flip else """; herd.asm's 32 figures and moves. Each frame's table is sent at 29 T-states a
; byte, safe at any time, to the attribute table that is not shown, $1B00 or
; $1B80; after the paper, R#5 shows it.
""")
    body = """        ld hl, atts             ; the copy of the attributes, in the RAM
        ld de, copy
        ld bc, 128
        ldir
""" + send_atts(herd_start()) + on(0xC2) + CLEAR_F
    if not flip:
        body += f"""        ld e, {HERD_FRAMES}
next:   push de
k0:     call step               ; the moves, in the copy
k1:
        call frame              ; the paper has ended
m0:     VRAM_WRITE ${ATT:04X}        ; the copy to the attribute table
        ld hl, copy
        ld c, VDP_DATA
        ld b, 128
        otir
m1:     pop de
        dec e
        jr nz, next
"""
    else:
        body += f"""        ld e, {HERD_FRAMES}
        ld d, $37               ; R#5 of the table not shown: $1B80
next:   push de
k0:     call step               ; the moves, in the copy
k1:
        pop de
        push de
        ld a, d                 ; the copy to the table not shown,
        rrca                    ; $1B00 or $1B80
        and $80
        out (VDP_CTRL), a
        ld a, ${(ATT >> 8) | 0x40:02X}
        out (VDP_CTRL), a
t0:     ld hl, copy
        ld c, VDP_DATA
        ld b, 128
sbyte:  outi                    ; 18
        jp nz, sbyte            ; 11: 29 T-states a byte (chapter 20)
t1:     call frame              ; the paper has ended
m0:     pop de
        ld a, d                 ; that table shown: R#5
        out (VDP_CTRL), a
        ld a, $85
        out (VDP_CTRL), a
m1:     ld a, d                 ; and the other one next
        xor 1
        ld d, a
        dec e
        jr nz, next
"""
    return (head(name, what) + say +
            f"copy    EQU ${COPY:04X}               ; the copy of the attributes, 128 bytes\n" +
            GRAPHIC2 + tidy(SPRITES + body + DONE + FRAME + STEP) +
            "patterns:\n" + db_rows(PATTERNS) + attributes(herd_start()) + CART_END)


PROGRAMS = {"one": one, "sizes": sizes, "rows": rows, "columns": columns, "edges": edges,
            "clock": clock, "order": order, "modes": modes, "march": march, "tear": tear,
            "herd": lambda: herd("herd"), "flip": lambda: herd("flip"),
            "fall": lambda: fall("fall"), "park": lambda: fall("park"),
            "last": lambda: fall("last")}


def main():
    for name, make in PROGRAMS.items():
        with open(os.path.join(HERE, f"{name}.asm"), "w") as f:
            f.write(make())
    print(" ".join(f"{n}.asm" for n in PROGRAMS))


if __name__ == "__main__":
    main()
