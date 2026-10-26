#!/usr/bin/env python3
"""gen39.py - the programs of chapter 39: collisions.

    python3 gen39.py && ./build.sh

    walls.asm    four balls walking into the walls of a room of tiles, one to
                 each side, and a post of one cell in the path of the first;
                 before each step walled reads, in the copy of the names in
                 the RAM, the cells the ball would cover (figure 39.1)
    corners.asm  the same, walled reading only the cells under the four
                 corners of the ball's box (figure 39.1)
    ytop.asm     the same as walls.asm, the ball's first line taken as its Y
                 and not as Y + 1
    flags.asm    ten scenes of sprites, each shown for two frames, and the
                 status the interrupt routine read after it: C, bit 5, where
                 two sprites' pixels meet, and where it does not come
    shapes.asm   THE SHAPE OF A COLLISION: ball B at every place from 18
                 pixels left of ball A to 18 right and from 18 above to 18
                 below, two frames each: C read for each, and boxed and
                 touched asked; the map drawn (figure 39.2)
    meet.asm     two pairs of balls walking into each other, one on the
                 diagonal and one level: after a frame whose status says C,
                 boxed and then touched asked of each pair still moving, and
                 a pair that touches stopped
    blame.asm    WHERE IT BREAKS: meet.asm with boxed alone (figure 39.3)

Graphic II with one set of shapes and colours for the three thirds (chapter
24): name 0 is the paper, name 1 chapter 24's brick; the copy of the names
at $C400 (chapter 24), the copy of the sprites' attributes at $C800, sprites
of 16 x 16 (chapter 26's ball, chapter 27's face). The interrupt comes in
mode 2 (chapter 17): its routine keeps the status, sends the copy of the
attributes and counts the frame. Every line of walled, cell, boxed and
touched carries its price, which walk.py adds up along the path it takes.
Each program ends with asmparts.CART_END; build.sh assembles with
--syntax=bFw.
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "tools"))
sys.path.insert(0, os.path.join(REPO, "ch26"))
sys.path.insert(0, os.path.join(REPO, "ch27"))
from asmparts import HEAD, CART_END, IM2, im2, library, SHOWBLK, BLKVARS  # noqa: E402
from gen26 import tidy, db_rows, big, BALL  # noqa: E402  (chapter 26: the ball)
from gen27 import FACE, FILL  # noqa: E402  (chapter 27: the face of two colours)

EU, JP = "MSXBOOK_EU16", "MSXBOOK_JP16"
MACHINES = [EU, JP]
BIOS = '        INCLUDE "bios.inc"\n'
BLACK, DARK_BLUE, WHITE = 1, 4, 15
ATT, PAT = 0x1B00, 0x3800
END = 0xD0
NAMES_RAM = 0xC400          # the copy of the 768 names (chapter 24)
COPY = 0xC800               # the copy of the sprites' attributes
EC = 0x80                   # the early clock: bit 7 of the colour (chapter 26)

# the tiles: name 0 the paper, name 1 chapter 24's brick
BRICK = [0xFF, 0x80, 0x80, 0x80, 0xFF, 0x08, 0x08, 0x08]
BRICK_C = BLACK << 4 | DARK_BLUE
PAPER_C = BLACK << 4 | WHITE

# the sprite patterns: the ball 0-3, the face's outline 4-7 and inside 8-11
SHAPES = {"ball": 0, "face": 4, "fill": 8}
PATTERNS = big(BALL) + big(FACE) + big(FILL)


def head(name, what):
    return HEAD.format(name=name, chapter=39, what=what) + BIOS


def rows_of(shape):
    """the 16 rows of 16 bits of a shape, as the VDP draws them"""
    return {"ball": BALL, "face": FACE, "fill": FILL}[shape]


# ------------------------------------------------------------------ the room
POST = (24, 6)              # (column, row): a post of one cell
ROOM = sorted({(c, r) for c in range(1, 31) for r in range(1, 23) if c in (1, 30) or r in (1, 22)}
              | {POST})


def room_names():
    names = [0] * 768
    for c, r in ROOM:
        names[32 * r + c] = 1
    return names


# the four balls of walls.asm: X, Y, step in X, step in Y
BALLS = [(150, 43, 1, 0),           # right, three rows of cells: the post in the middle one
         (68, 122, -1, 0),          # left
         (150, 101, 0, 1),          # down, three columns of cells
         (40, 73, 0, -1)]           # up, two columns
WALL_VARIANTS = ["walls", "corners", "ytop"]
WALL_FRAMES = 90                    # frames the balls are watched for


def cells_under(x, y, first_dy=1):
    """the cells a ball's box covers at (x, y): its first line is y + first_dy"""
    top = (y + first_dy) & 0xFF
    return {(c, r) for c in range(x // 8, (x + 15) // 8 + 1) for r in range(top // 8, (top + 15) // 8 + 1)}


def walled_model(variant, x, y):
    """what each variant of walled answers for a ball at (x, y)"""
    names = room_names()
    if variant == "corners":
        top = y + 1
        cells = {((x + dx) // 8, (top + dy) // 8) for dx in (0, 15) for dy in (0, 15)}
    else:
        cells = cells_under(x, y, 0 if variant == "ytop" else 1)
    return any(names[32 * r + c] for c, r in cells if 0 <= c < 32 and 0 <= r < 24)


def walk_balls(variant, frames=WALL_FRAMES):
    """[(x, y, the frame it stopped in or None)] after FRAMES frames: in
    frame k the main loop, after the k-th interrupt, moves each ball still
    moving to its next place unless walled says a wall"""
    balls = [[x, y, sx, sy, None] for x, y, sx, sy in BALLS]
    for k in range(1, frames + 1):
        for b in balls:
            if b[4] is not None:
                continue
            nx, ny = b[0] + b[2], b[1] + b[3]
            if walled_model(variant, nx, ny):
                b[4] = k
            else:
                b[0], b[1] = nx, ny
    return [tuple(b[:2]) + (b[4],) for b in balls]


# ------------------------------------------------------------------ the pixel test
def shifted_table(rows):
    """touched's table: the shape moved 0 to 7 pixels right, each of its 16
    rows in four bytes, the fourth 0; copy s from byte 64 x s"""
    out = []
    for s in range(8):
        for r in rows:
            v = (r << 8) >> s
            out += [v >> 16 & 255, v >> 8 & 255, v & 255, 0]
    return out


def pixels_meet(rows_a, rows_b, dx, dy):
    """do two 16 x 16 shapes share a pixel, the second dx right and dy down?"""
    for y in range(16):
        yb = y - dy
        if 0 <= yb < 16:
            a = rows_a[y] << 16
            b = (rows_b[yb] << 16) >> dx if dx >= 0 else (rows_b[yb] << 16) << -dx
            if a & b:
                return True
    return False


# ------------------------------------------------------------------ routines
ISR = """
; isr: every frame. The status kept in stat, the copy of the sprites'
; attributes sent (the paper is over: at full speed, chapter 20), the frame
; counted. Keeps AF, BC, HL
isr:    push af
        push bc
        push hl
        in a, (VDP_CTRL)        ; the status: F, 5S and C; the signal down
        ld (stat), a
        VRAM_WRITE ATT_TABLE
        ld hl, copy
        ld bc, ({n} << 8) | VDP_DATA
        otir
        ld hl, (ticks)
        inc hl
        ld (ticks), hl
        pop hl
        pop bc
        pop af
        ei
        ret
"""

CELL = """
; cell: B = X, C = a line -> HL: the cell of the copy of the names that holds
; the pixel. Keeps BC. Uses A, DE
cell:   ld a, c                 ;  5
        and $F8                 ;  8  the row x 8
        ld l, a                 ;  5
        ld h, 0                 ;  8
        add hl, hl              ; 12
        add hl, hl              ; 12  the row x 32
        ld a, b                 ;  5
        rrca                    ;  5
        rrca                    ;  5
        rrca                    ;  5
        and $1F                 ;  8  the column
        add a, l                ;  5
        ld l, a                 ;  5
        ld de, names            ; 11
        add hl, de              ; 12
        ret                     ; 11
"""

WALLED = """
; walled: B = X, C = Y of a ball's place -> NZ if a wall is under any of its
; 16 x 16 pixels: the cells from column X / 8 to (X + 15) / 8 and from row
; (Y + 1) / 8 to (Y + 16) / 8, for a sprite's first line is Y + 1 (chapter
; 26). A name that is not 0 is a wall. Uses A, BC, DE, HL
walled: inc c                   ;  5  the first line
        call cell               ; 18  HL: the cell of the top left pixel
        ld a, b                 ;  5
        and 7                   ;  8
        ld d, 2                 ;  8  two columns on a column's edge,
        jr z, .cols             ; 13, or 8
        inc d                   ;  5  three anywhere else
.cols:  ld a, c                 ;  5
        and 7                   ;  8
        ld e, 2                 ;  8  and two rows, or three
        jr z, .rows             ; 13, or 8
        inc e                   ;  5
.rows:  ld b, d                 ;  5
        push hl                 ; 12
.cell:  ld a, (hl)              ;  8
        or a                    ;  5  0: the paper
        jr nz, .wall            ; 13, or 8
        inc hl                  ;  7
        djnz .cell              ; 14, or 9
        pop hl                  ; 11
        ld bc, 32               ; 11
        add hl, bc              ; 12  the row of cells below
        dec e                   ;  5
        jr nz, .rows            ; 13, or 8
        ret                     ; 11  Z: no wall
.wall:  pop hl                  ; 11
        ret                     ; 11  NZ: a wall
"""

# ytop.asm: the same, the first line taken as Y
WALLED_YTOP = WALLED.replace("""; (Y + 1) / 8 to (Y + 16) / 8, for a sprite's first line is Y + 1 (chapter
; 26). A name that is not 0 is a wall. Uses A, BC, DE, HL
walled: inc c                   ;  5  the first line
        call cell               ; 18  HL: the cell of the top left pixel""", """; Y / 8 to (Y + 15) / 8: WHERE IT BREAKS, the first line taken as Y. A name
; that is not 0 is a wall. Uses A, BC, DE, HL
walled: call cell               ; 18  HL: the cell of the top left pixel""")
assert WALLED_YTOP != WALLED

WALLED_CORNERS = """
; walled: B = X, C = Y of a ball's place -> NZ if a wall is under one of the
; four corners of its box of 16 x 16: the pixels (X, Y + 1), (X + 15, Y + 1),
; (X + 15, Y + 16) and (X, Y + 16). Uses A, BC, DE, HL
walled: inc c                   ;  5  the first line
        call corner             ; 18  top left
        ret nz                  ; 12, or 6
        ld a, b                 ;  5
        add a, 15               ;  8
        ld b, a                 ;  5
        call corner             ; 18  top right
        ret nz                  ; 12, or 6
        ld a, c                 ;  5
        add a, 15               ;  8
        ld c, a                 ;  5
        call corner             ; 18  bottom right
        ret nz                  ; 12, or 6
        ld a, b                 ;  5
        sub 15                  ;  8
        ld b, a                 ;  5  and bottom left, below
; corner: B = X, C = a line -> NZ if the cell that holds the pixel is a wall
corner: call cell               ; 18
        ld a, (hl)              ;  8
        or a                    ;  5
        ret                     ; 11
"""

BOXED = """
; boxed: B, C = X, Y of one ball and D, E of the other -> carry if their
; boxes of 16 x 16 share a pixel: X and Y both less than 16 apart. Uses A
boxed:  ld a, d                 ;  5
        sub b                   ;  5  the difference of the X
        add a, 15               ;  8  -15 to 15 become 0 to 30
        cp 31                   ;  8
        ret nc                  ; 12, or 6  16 or more apart
        ld a, e                 ;  5
        sub c                   ;  5  the difference of the Y
        add a, 15               ;  8
        cp 31                   ;  8
        ret                     ; 11  carry: the boxes meet
"""

TOUCHED = """
; touched: B, C = X, Y of one ball and D, E of the other, whose boxes meet ->
; NZ if a pixel of one is a pixel of the other. The ball's rows are in
; shifted, four bytes each, moved 0 to 7 pixels right: copy s at 64 x s.
; Uses A, BC, DE, HL
touched: ld a, d                ;  5
        sub b                   ;  5  dx: the second ball's X less the first's
        jr nc, .order           ; 13, or 8
        push bc                 ; 12  the second ball is on the left:
        push de                 ; 12  the two change places
        pop bc                  ; 11
        pop de                  ; 11
        neg                     ; 10
.order: ld l, a                 ;  5  L: dx, 0 to 15. (B, C) is the left ball
        ld a, e                 ;  5
        sub c                   ;  5  dy: the right ball's Y less the left's
        ld e, 0                 ;  8  the right ball lower: its row 0 ...
        jr nc, .lower           ; 13, or 8
        neg                     ; 10  higher: its row -dy ...
        ld e, a                 ;  5
        xor a                   ;  5  ... meets the left ball's row 0
.lower: ld c, a                 ;  5  C: the left ball's first row
        add a, e                ;  5
        sub 16                  ;  8
        neg                     ; 10
        ld b, a                 ;  5  B: the rows both cover, 16 - |dy|
        ld a, l                 ;  5
        and 3                   ;  8
        rrca                    ;  5
        rrca                    ;  5  (dx AND 3) x 64
        sla e                   ; 10
        sla e                   ; 10  + 4 x the right ball's first row
        add a, e                ;  5
        ld e, a                 ;  5
        ld d, high shifted      ;  8  DE: that row of copy dx AND 7
        bit 2, l                ; 10
        jr z, .page             ; 13, or 8
        inc d                   ;  5  copies 4 to 7 are in the next page
.page:  bit 3, l                ; 10
        jr z, .near             ; 13, or 8
        dec de                  ;  7  dx of 8 or more: a byte to the left
.near:  ld a, c                 ;  5
        add a, a                ;  5
        add a, a                ;  5
        ld l, a                 ;  5
        ld h, high shifted      ;  8  HL: the left ball's first row, copy 0
.row:   ld a, (de)              ;  8
        and (hl)                ;  8  the first byte of the two
        ret nz                  ; 12, or 6  a pixel of both: they touch
        inc de                  ;  7
        inc l                   ;  5
        ld a, (de)              ;  8
        and (hl)                ;  8  the second
        ret nz                  ; 12, or 6
        inc de                  ;  7
        inc de                  ;  7
        inc de                  ;  7
        inc l                   ;  5
        inc l                   ;  5
        inc l                   ;  5  the next row of each
        djnz .row               ; 14, or 9
        xor a                   ;  5
        ret                     ; 11  Z: no pixel in common
"""


def shifted_data():
    """the table touched reads, at a page that is a multiple of two, the byte
    before it 0 (a row at dx of 8 or more begins a byte early)"""
    return ("        db 0                    ; the byte before the table: touched may read it\n"
            "        ALIGN 512, 0\n"
            "shifted:                        ; the ball moved 0-7 pixels, 4 bytes a row\n" +
            db_rows(shifted_table(BALL)))


def setup(names_label, nsprites):
    """Graphic II with one set for the three thirds (chapter 24), the names
    from NAMES_LABEL sent from their copy, the sprite patterns, mode 2"""
    return f"""init:   di
        ld sp, SYS_AREA
        VDP_REG 1, $80          ; display off
        VDP_REG 0, $02          ; Graphic II
        VDP_REG 2, $06          ; names    $1800
        VDP_REG 3, $9F          ; colours  $2000, one set for three thirds
        VDP_REG 4, $00          ; shapes   $0000, one set for three thirds
        VDP_REG 5, $36          ; sprite attributes $1B00
        VDP_REG 6, $07          ; sprite patterns   $3800
        VDP_REG 7, $0F          ; border white
        VRAM_WRITE $1B00        ; no sprites
        ld a, END_MARK
        out (VDP_DATA), a
        VRAM_WRITE $0000        ; the shapes: all paper ...
        ld bc, 2048
.shp:   xor a
        out (VDP_DATA), a
        dec bc
        ld a, b
        or c
        jr nz, .shp
        VRAM_WRITE $0008        ; ... but name 1, the brick
        ld hl, brick
        ld bc, (8 << 8) | VDP_DATA
        otir
        VRAM_WRITE $2000        ; the colours: black on white ...
        ld bc, 2048
.col:   ld a, ${PAPER_C:02X}
        out (VDP_DATA), a
        dec bc
        ld a, b
        or c
        jr nz, .col
        VRAM_WRITE $2008        ; ... but the brick's
        ld hl, brick + 8
        ld bc, (8 << 8) | VDP_DATA
        otir
        VRAM_WRITE PAT_TABLE    ; the sprite patterns
        ld hl, patterns
        ld bc, ({len(PATTERNS)} << 8) | VDP_DATA
        otir
        ld hl, {names_label}    ; the names, into their copy ...
        ld de, names
        ld bc, 768
        ldir
        VRAM_WRITE $1800        ; ... and from there to the VDP
        ld hl, names
        ld bc, 768
.nam:   ld a, (hl)
        out (VDP_DATA), a
        inc hl
        dec bc
        ld a, b
        or c
        jr nz, .nam
        ld hl, 0
        ld (ticks), hl
        ld a, END_MARK          ; no sprites in the copy yet
        ld (copy), a
""" + im2("isr")


COMMON_RAM = f"""stat    EQU VARS                ; the status the interrupt routine read
ticks   EQU VARS + 1            ; frames, two bytes
names   EQU ${NAMES_RAM:04X}               ; the copy of the 768 names
copy    EQU ${COPY:04X}               ; the copy of the sprites' attributes
ATT_TABLE EQU ${ATT:04X}
PAT_TABLE EQU ${PAT:04X}
END_MARK EQU ${END:02X}                ; a Y of 208 ends the table
"""


def program(name, what, say, ram, body, routines, data, nsprites, names_label="room"):
    """the whole source: head, RAM, set-up, main, routines, data"""
    return (head(name, what) + say + COMMON_RAM + ram + IM2 +
            tidy(setup(names_label, nsprites) + body + ISR.format(n=4 * nsprites + 1) + routines) +
            "brick:  db " + ", ".join(f"${b:02X}" for b in BRICK) + "\n" +
            "        db " + ", ".join(f"${BRICK_C:02X}" for _ in range(8)) + "\n" +
            "patterns:                       ; ball 0, face 4, inside of the face 8\n" + db_rows(PATTERNS) +
            data + ("blank:  ds 768, 0               ; no tiles: every name 0, the paper\n"
                    if names_label == "blank" else "") + CART_END)


def say(text):
    return "".join(f"; {l}\n" for l in text.strip().splitlines())


# ------------------------------------------------------------------ walls.asm, corners.asm, ytop.asm
BALL_RAM = """balls   EQU VARS + 3            ; four balls, 6 bytes each: X, Y, the steps
                                ; in X and Y, moving, the frame it stopped
"""

MOVE = """
; move: each ball still moving a step on, unless walled finds a wall at the
; next place: then it stops, and the frame is kept
move:   ld ix, balls
        ld a, 4
.ball:  push af
        ld a, (ix+4)            ; moving?
        or a
        jr z, .next
        ld a, (ix+0)
        add a, (ix+2)
        ld b, a                 ; B: the next X
        ld a, (ix+1)
        add a, (ix+3)
        ld c, a                 ; C: the next Y
        push bc
        call walled
        pop bc
        jr nz, .stop
        ld (ix+0), b            ; no wall: the ball goes there
        ld (ix+1), c
        jr .next
.stop:  ld (ix+4), 0            ; a wall: it stops where it is
        ld a, (ticks)
        ld (ix+5), a            ; in this frame
.next:  ld de, 6
        add ix, de
        pop af
        dec a
        jr nz, .ball
        ret

; build: the copy of the attributes from the balls: Y, X, pattern 0, black
build:  ld ix, balls
        ld hl, copy
        ld b, 4
.spr:   ld a, (ix+1)
        ld (hl), a
        inc hl
        ld a, (ix+0)
        ld (hl), a
        inc hl
        ld (hl), 0
        inc hl
        ld (hl), BLACK
        inc hl
        ld de, 6
        add ix, de
        djnz .spr
        ld (hl), END_MARK
        ret
"""

WALL_SAY = {
    "walls": "four balls walking into the walls of a room of tiles",
    "corners": "the same, walled reading the four corners only",
    "ytop": "the same, the ball's first line taken as its Y",
}


def walls_program(variant):
    body = """        ld hl, start            ; the balls
        ld de, balls
        ld bc, 24
        ldir
        call build
        in a, (VDP_CTRL)        ; F cleared: the first interrupt ends a frame
        VDP_REG 1, $E2          ; display on, interrupt on, sprites 16 x 16
        ei
main:   halt                    ; the copy sent, the frame counted
        call move
        call build
        jr main
"""
    walled = {"walls": WALLED, "corners": WALLED_CORNERS, "ytop": WALLED_YTOP}[variant]
    start = "start:  " + "\n        ".join(
        f"db {x}, {y}, {sx & 255}, {sy & 255}, 1, 0" for x, y, sx, sy in BALLS) + "\n"
    data = "room:                           ; the names: a ring of bricks and a post\n" + \
        db_rows(room_names(), 16) + start
    text = {"walls": WALL_TEXT, "corners": WALL_TEXT + "\nWALLED HERE: THE FOUR CORNERS ONLY.",
            "ytop": WALL_TEXT + "\nWALLED HERE: THE FIRST LINE TAKEN AS Y."}[variant]
    return program(variant, WALL_SAY[variant], say(text), BALL_RAM, body, MOVE + walled + CELL, data, 4)


WALL_TEXT = """Four balls walk a pixel a frame, one towards each wall of the room; before
each step walled is asked about the next place."""


# ------------------------------------------------------------------ flags.asm
def sprite(x, y, shape="ball", colour=BLACK, ec=False):
    """an entry of the attribute table for a ball whose box's top left pixel
    is (x, y): Y is y - 1 (chapter 26); with the early clock X is x + 32"""
    return (y - 1) & 255, x + 32 if ec else x, SHAPES[shape], colour | (EC if ec else 0)


SCENES = [
    ("apart", [sprite(100, 88), sprite(120, 88, colour=DARK_BLUE)]),
    ("overlap", [sprite(100, 88), sprite(108, 88, colour=DARK_BLUE)]),
    ("one colour 0", [sprite(100, 88), sprite(108, 88, colour=0)]),
    ("both colour 0", [sprite(100, 88, colour=0), sprite(108, 88, colour=0)]),
    ("below the paper", [sprite(100, 192), sprite(108, 192, colour=DARK_BLUE)]),
    ("fifth and sixth", [sprite(0, 88), sprite(24, 88), sprite(48, 88), sprite(72, 88),
                         sprite(100, 88), sprite(108, 88, colour=DARK_BLUE)]),
    ("left of the paper", [sprite(-22, 88, ec=True), sprite(-14, 88, colour=DARK_BLUE, ec=True)]),
    ("right of the paper", [sprite(250, 88), sprite(255, 88, colour=DARK_BLUE)]),
    ("after the end", [(END, 0, 0, 0), sprite(100, 88), sprite(108, 88, colour=DARK_BLUE)]),
    ("the face's two", [sprite(100, 88, "face"), sprite(100, 88, "fill", colour=3)]),
]
FLAG_SPRITES = max(len(s) for _, s in SCENES)       # the copy sent: this many and the end
FLAG_REPEAT = 2                                      # each scene's frames


WAIT = """
; wait: until the interrupt routine has counted a frame. Keeps BC, DE
wait:   push hl
        ld hl, ticks
        ld a, (hl)
.same:  cp (hl)                 ; the same frame: wait on
        jr z, .same
        pop hl
        ret
"""

FLAG_RAM = f"""log     EQU VARS + 3            ; the status after each scene, {len(SCENES)} bytes
"""


def flags_program():
    n = 4 * FLAG_SPRITES + 1
    tables = "scenes:\n"
    for k, (what, sp) in enumerate(SCENES):
        flat = [b for e in sp for b in e]
        flat += [END] + [0] * (n - 1 - len(flat))
        tables += f"; scene {k}: {what}\n" + db_rows(flat, n)
    body = f"""        in a, (VDP_CTRL)        ; F cleared: the first interrupt ends a frame
        VDP_REG 1, $E2          ; display on, interrupt on, sprites 16 x 16
        ei
        ld hl, scenes
        ld de, log
        ld b, {len(SCENES)}
.scene: push bc
        push de
        ld de, copy             ; the scene's sprites into the copy
        ld bc, {n}
        ldir
        ld b, {FLAG_REPEAT}                 ; two frames: the first sends the scene, the
.frame: call wait               ; second reads the status of a picture of it
        djnz .frame
        pop de
        ld a, (stat)
        ld (de), a              ; the status after the scene
        inc de
        pop bc
        djnz .scene
        ld a, END_MARK          ; no sprites
        ld (copy), a
done:   jr done
"""
    text = """Ten scenes of sprites, two frames each, and the status read after each:
C, bit 5, says that two sprites' pixels met in the picture."""
    return program("flags", "where the coincidence flag comes", say(text), FLAG_RAM, body,
                   WAIT, tables, FLAG_SPRITES, names_label="blank")


# ------------------------------------------------------------------ shapes.asm
AX, AY = 100, 88            # ball A's box: its top left pixel
REACH = 18                  # ball B from -REACH to REACH pixels off it, each way
SIDE = 2 * REACH + 1        # 37 places a side
BLOCK = 3                   # pixels of the map a place
MAP_C, MAP_T, BITMAP = 0xD000, 0xD600, 0xDC00
MAP_W = (SIDE * BLOCK + 7) // 8         # the map's bytes across: 14
MAP_ROW, MAP_COL, MAP_CODE = 5, 9, 16   # where showblk puts it, and its first character

SHAPES_RAM = f"""dx      EQU VARS + 3            ; ball B's place, off ball A
dy      EQU VARS + 4
mapc    EQU VARS + 5            ; the place's byte in map_c, two bytes
map_c   EQU ${MAP_C:04X}               ; each place: C after it, $20 or 0
map_t   EQU ${MAP_T:04X}               ; 0 boxes apart, 1 boxes meet, 2 pixels meet
bitmap  EQU ${BITMAP:04X}               ; the map drawn, {MAP_W} bytes x {MAP_W * 8} lines
""" + BLKVARS

SWEEP = f"""        ld hl, start            ; ball A, and ball B
        ld de, copy
        ld bc, 9
        ldir
        in a, (VDP_CTRL)        ; F cleared: the first interrupt ends a frame
        VDP_REG 1, $E2          ; display on, interrupt on, sprites 16 x 16
        ei
        ld hl, map_c
        ld (mapc), hl
        ld a, -{REACH}
        ld (dy), a
.dy:    ld a, -{REACH}
        ld (dx), a
.dx:    ld a, (dy)              ; ball B at A's place + (dx, dy)
        add a, {(AY - 1) & 255}
        ld (copy + 4), a
        ld a, (dx)
        add a, {AX}
        ld (copy + 5), a
        halt                    ; the first interrupt sends it,
        halt                    ; the second reads the status of a picture of it
        ld a, (stat)
        and $20                 ; C
        ld hl, (mapc)
        ld (hl), a
        ld a, (copy + 1)
        ld b, a
        ld a, (copy)
        ld c, a                 ; B, C: ball A
        ld a, (copy + 5)
        ld d, a
        ld a, (copy + 4)
        ld e, a                 ; D, E: ball B
        call boxed
        ld a, 0
        jr nc, .keep            ; 0: the boxes are apart
        call touched
        ld a, 1
        jr z, .keep             ; 1: the boxes meet, the pixels do not
        inc a                   ; 2: the pixels meet
.keep:  ld hl, (mapc)
        ld de, map_t - map_c
        add hl, de
        ld (hl), a
        ld hl, (mapc)
        inc hl
        ld (mapc), hl
        ld a, (dx)
        inc a
        ld (dx), a
        cp {REACH + 1}
        jr nz, .dx
        ld a, (dy)
        inc a
        ld (dy), a
        cp {REACH + 1}
        jr nz, .dy
        di                      ; the sweep is over
        VDP_REG 1, $82          ; display off
        VRAM_WRITE ATT_TABLE    ; no sprites
        ld a, END_MARK
        out (VDP_DATA), a
        call draw               ; the map, in the RAM
        ld hl, bitmap
        ld de, ({MAP_W} << 8) | {MAP_W}
        ld bc, ({MAP_ROW} << 8) | {MAP_COL}
        ld a, {MAP_CODE}
        call showblk            ; and as characters
        VDP_REG 1, $C2          ; display on
done:   jr done
"""

DRAW = f"""
; draw: the map in bitmap, a block of 3 x 3 pixels a place: all ink where C
; came, a chequer where only the boxes meet, paper where they are apart
draw:   ld hl, bitmap           ; all paper
        ld de, bitmap + 1
        ld bc, {MAP_W * MAP_W * 8 - 1}
        ld (hl), 0
        ldir
        ld hl, map_c
        ld c, 0                 ; C: the place's top line in the map
.row:   ld b, 0                 ; B: its left column
.place: ld a, (hl)
        or a
        ld e, %111              ; C came: three pixels on each line
        ld d, %111
        jr nz, .put
        push hl
        ld de, map_t - map_c
        add hl, de
        ld a, (hl)
        pop hl
        or a
        jr z, .skip             ; the boxes apart: paper
        ld e, %101              ; the boxes meet: a chequer
        ld d, %010
.put:   call block
.skip:  inc hl
        ld a, b
        add a, {BLOCK}
        ld b, a
        cp {SIDE * BLOCK}
        jr nz, .place
        ld a, c
        add a, {BLOCK}
        ld c, a
        cp {SIDE * BLOCK}
        jr nz, .row
        ret

; block: the place at (B, C) of the bitmap, three lines of three pixels: the
; bits of E on the first and the third, of D on the second. Keeps BC, DE, HL
block:  push hl
        push de
        ld a, e
        call three
        inc c
        pop de
        push de
        ld a, d
        call three
        inc c
        pop de
        push de
        ld a, e
        call three
        dec c
        dec c
        pop de
        pop hl
        ret

; three: A's three low bits as pixels (B, C), (B + 1, C), (B + 2, C). Keeps
; BC. Uses A, DE, HL
three:  push bc
        ld e, a
        ld d, 3
.bit:   srl e                   ; the next bit
        jr nc, .no
        push de
        call plot
        pop de
.no:    inc b
        dec d
        jr nz, .bit
        pop bc
        ret

; plot: the pixel (B, C) of the bitmap set, B across and C down. Uses A,
; DE, HL
plot:   ld l, c
        ld h, 0
        add hl, hl              ; the line x 2
        ld e, l
        ld d, h
        add hl, hl
        add hl, hl
        add hl, hl              ; x 16
        or a
        sbc hl, de              ; x 14: the bytes of a line
        ld a, b
        rrca
        rrca
        rrca
        and $1F
        ld e, a
        ld d, 0
        add hl, de              ; + the byte across
        ld de, bitmap
        add hl, de
        ld a, b
        and 7
        ld e, a
        ld a, $80
        jr z, .set
.shift: rrca                    ; the pixel's bit
        dec e
        jr nz, .shift
.set:   or (hl)
        ld (hl), a
        ret
"""
assert MAP_W == 14, "plot multiplies by 14"


def shapes_program():
    start = [b for e in (sprite(AX, AY), sprite(AX, AY, colour=DARK_BLUE)) for b in e] + [END]
    data = "start:  db " + ", ".join(f"${b:02X}" for b in start) + "   ; ball A, ball B\n" + shifted_data()
    text = f"""Ball B at every place from {REACH} pixels left of ball A to {REACH} right, and
from {REACH} above to {REACH} below, two frames each: C read for each place, and
boxed and touched asked; then the map drawn."""
    return program("shapes", "the shape of a collision", say(text), SHAPES_RAM, SWEEP,
                   BOXED + TOUCHED + DRAW + library(SHOWBLK), data, 2, names_label="blank")


# ------------------------------------------------------------------ meet.asm, blame.asm
# two pairs: one on the diagonal, one level; X, Y of each ball (attributes)
# and its step. The level pair's pixels first meet 13 pixels apart, the
# diagonal pair's 9 apart each way (pixels_meet); the level pair starts so
# that it first touches in the picture of frame 20, and the diagonal pair so
# that its boxes first meet in frame 21
PAIRS = [((40, 15, 1, 1), (97, 72, -1, -1)),       # on the diagonal
         ((40, 127, 1, 0), (93, 127, -1, 0))]       # level
PAIR_FRAMES = 40
PAIR_RAM = """pairs   EQU VARS + 3            ; two pairs, 10 bytes each: X, Y of A and of
                                ; B, the steps of A and of B, moving, the frame
"""

TESTS = """
; tests: each pair still moving asked boxed and then touched where it is; a
; pair that touches stops, and the frame is kept
tests:  ld ix, pairs
        ld a, 2
.pair:  push af
        ld a, (ix+8)            ; moving?
        or a
        jr z, .next
        ld b, (ix+0)
        ld c, (ix+1)            ; B, C: ball A
        ld d, (ix+2)
        ld e, (ix+3)            ; D, E: ball B
        call boxed
        jr nc, .next            ; the boxes are apart
        call touched
        jr z, .next             ; the boxes meet, the pixels do not
        ld (ix+8), 0            ; they touch: the pair stops
        ld a, (ticks)
        ld (ix+9), a            ; in this frame
.next:  ld de, 10
        add ix, de
        pop af
        dec a
        jr nz, .pair
        ret
"""
TESTS_BLAME = TESTS.replace("""; tests: each pair still moving asked boxed and then touched where it is; a
; pair that touches stops, and the frame is kept""", """; tests: each pair still moving asked boxed where it is: WHERE IT BREAKS,
; boxed alone. A pair whose boxes meet stops, and the frame is kept""").replace(
    """        jr nc, .next            ; the boxes are apart
        call touched
        jr z, .next             ; the boxes meet, the pixels do not
        ld (ix+8), 0            ; they touch: the pair stops""",
    """        jr nc, .next            ; the boxes are apart
        ld (ix+8), 0            ; the boxes meet: the pair stops""")
assert TESTS_BLAME.count("touched") == 0

PAIR_MOVE = """
; move: each pair still moving, both balls a step on
move:   ld ix, pairs
        ld b, 2
.pair:  ld a, (ix+8)
        or a
        jr z, .next
        ld a, (ix+0)
        add a, (ix+4)
        ld (ix+0), a
        ld a, (ix+1)
        add a, (ix+5)
        ld (ix+1), a
        ld a, (ix+2)
        add a, (ix+6)
        ld (ix+2), a
        ld a, (ix+3)
        add a, (ix+7)
        ld (ix+3), a
.next:  ld de, 10
        add ix, de
        djnz .pair
        ret

; build: the copy of the attributes from the pairs: each ball's Y, X,
; pattern 0, A black and B dark blue
build:  ld ix, pairs
        ld hl, copy
        ld b, 2
.pair:  ld a, (ix+1)
        ld (hl), a
        inc hl
        ld a, (ix+0)
        ld (hl), a
        inc hl
        ld (hl), 0
        inc hl
        ld (hl), BLACK
        inc hl
        ld a, (ix+3)
        ld (hl), a
        inc hl
        ld a, (ix+2)
        ld (hl), a
        inc hl
        ld (hl), 0
        inc hl
        ld (hl), DARK_BLUE
        inc hl
        ld de, 10
        add ix, de
        djnz .pair
        ld (hl), END_MARK
        ret
"""

PAIR_MAIN = """        ld hl, start            ; the two pairs
        ld de, pairs
        ld bc, 20
        ldir
        call build
        in a, (VDP_CTRL)        ; F cleared: the first interrupt ends a frame
        VDP_REG 1, $E2          ; display on, interrupt on, sprites 16 x 16
        ei
main:   halt                    ; the interrupt: the status kept, the copy sent
        ld a, (stat)
        and $20                 ; C: two sprites' pixels met in the last picture
        call nz, tests
        call move
        call build
        jr main
"""


def pairs_program(name):
    start = "start:  " + "\n        ".join(
        "db " + ", ".join(str(v & 255) for v in (a[0], a[1], b[0], b[1], a[2], a[3], b[2], b[3])) + ", 1, 0"
        for a, b in PAIRS) + "\n"
    tests = TESTS if name == "meet" else TESTS_BLAME
    routines = tests + PAIR_MOVE + BOXED + (TOUCHED if name == "meet" else "")
    data = start + (shifted_data() if name == "meet" else "")
    text = {"meet": """Two pairs of balls walk into each other, one on the diagonal and one level.
After a frame whose status says C, boxed and then touched are asked of each
pair still moving, and a pair that touches stops.""",
            "blame": """meet.asm with boxed alone: WHERE IT BREAKS. After a frame whose status says
C, each pair whose boxes meet stops."""}[name]
    what = {"meet": "two pairs, C and then boxed and touched", "blame": "two pairs, C and then boxed alone"}[name]
    return program(name, what, say(text), PAIR_RAM, PAIR_MAIN, routines, data, 4, names_label="blank")


def pairs_model(name, frames=PAIR_FRAMES, c_of=None):
    """[(the four balls' places, stopped frames)] by the frame loop: in
    iteration k (after the k-th interrupt) the status says whether the
    picture of the places of iteration k - 2 had two pixels meet; if it did,
    the pairs still moving are tested where they are (the places of k - 1);
    then the moving ones move. c_of(places) -> C of a picture"""
    pos = [[list(a), list(b)] for a, b in PAIRS]
    moving, stopped = [True, True], [None, None]
    hist = [[tuple(p[0][:2]) + tuple(p[1][:2]) for p in pos]]      # the places of iteration 0
    for k in range(1, frames + 1):
        shown = hist[k - 2] if k >= 2 else None
        c = bool(shown) and c_of(shown)
        if c:
            for i in range(2):
                if not moving[i]:
                    continue
                ax, ay, bx, by = pos[i][0][0], pos[i][0][1], pos[i][1][0], pos[i][1][1]
                dx, dy = bx - ax, by - ay
                if abs(dx) < 16 and abs(dy) < 16 and (name == "blame" or pixels_meet(BALL, BALL, dx, dy)):
                    moving[i], stopped[i] = False, k
        for i in range(2):
            if moving[i]:
                for ball in pos[i]:
                    ball[0] += ball[2]
                    ball[1] += ball[3]
        hist.append([tuple(p[0][:2]) + tuple(p[1][:2]) for p in pos])
    return hist, stopped


def pictures_c(places):
    """C of a picture of the four balls: any two whose pixels meet"""
    balls = [(p[0], p[1]) for p in places] + [(p[2], p[3]) for p in places]
    for i in range(4):
        for j in range(i + 1, 4):
            dx, dy = balls[j][0] - balls[i][0], balls[j][1] - balls[i][1]
            if abs(dx) < 16 and abs(dy) < 16 and pixels_meet(BALL, BALL, dx, dy):
                return True
    return False


PROGRAMS = WALL_VARIANTS + ["flags", "shapes", "meet", "blame"]


def main():
    out = {v: walls_program(v) for v in WALL_VARIANTS}
    out["flags"] = flags_program()
    out["shapes"] = shapes_program()
    out["meet"] = pairs_program("meet")
    out["blame"] = pairs_program("blame")
    for name, text in out.items():
        with open(os.path.join(HERE, f"{name}.asm"), "w") as f:
            f.write(text)
    print(" ".join(f"{n}.asm" for n in out))


if __name__ == "__main__":
    main()
