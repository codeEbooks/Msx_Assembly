#!/usr/bin/env python3
"""gen28.py - the programs of chapter 28: software sprites in the tiles.

    python3 gen28.py && ./build.sh

    shifts.asm     eight bugs on the sky, at every x AND 7 and every y AND 7
                   (figure 28.1)
    cost.asm       preshift, and build at the eight shifts, from the copies
                   and shifted as it goes (sbuild): nothing on the screen
    edge.asm       a bug at the right edge: its right column at the left edge,
                   a row of cells lower (figure 28.2)
    under.asm      four bugs, on the sky, the bricks, a coin and the grass,
                   in the colours of the tiles under them (figure 28.3)
    paint.asm      the same, the rows of the bug painted black
    walk.asm       a bug that walks across the screen, a pixel right and a
                   line down each frame (figure 28.4)
    swarm.asm      six bugs on the same lines, each a pixel right each frame
                   (figure 28.5)
    overlap.asm    WHERE IT BREAKS: two bugs that cross, each built from the
                   tiles under it (figure 28.6)
    stack.asm      the same, each built from what the screen shows

Chapter 24's screen of tiles: Graphic II with one set of shapes and colours
for the three thirds (R#3 = $9F, R#4 = $00), its tiles and its map. A bug is
8 x 8 pixels; wherever it is, it covers 2 x 2 cells, and has four patterns of
its own, 128 + 4i to 131 + 4i, made in the RAM from the tiles under it and
the bug through its mask, and sent to the VDP after the paper. Every program
draws with the display off first, keeps the interrupts off and waits for the
end of the paper on the status (chapter 19), ends with asmparts.CART_END, and
build.sh assembles with --syntax=bFw.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "ch24"))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "ch26"))
from asmparts import HEAD, CART_END  # noqa: E402
from gen24 import TILES, MAP, names_of  # noqa: E402  (chapter 24)
from gen26 import tidy, db_rows  # noqa: E402  (chapter 26)

BIOS = '        INCLUDE "bios.inc"\n'
BLACK, LIGHT_GREEN, DARK_BLUE, WHITE = 1, 3, 4, 15
NAMES = names_of(MAP)       # chapter 24's screen: 768 names
FIRST = 128                 # the first pattern of the bugs
NAMES_RAM = 0xC400          # the tiles' names, a copy
SHOWN_RAM = 0xC800          # the names on the screen: the tiles', and the bugs'
PATS_RAM = 0xCC00           # the bugs' patterns, 8 bytes each, from pattern 128 ...
COLS_RAM = PATS_RAM + 0x400  # ... and their colours, $400 on
COPIES_RAM = 0xD400         # the eight copies of the bug, 32 bytes each
REC = 16                    # bytes a bug's record
X, Y, PAT, DX, DY, HERE_, WAS = 0, 1, 2, 3, 4, 5, 7


def head(name, what):
    return HEAD.format(name=name, chapter=28, what=what) + BIOS


# ------------------------------------------------------------------ the bug
def rows8(*lines):
    return [int(line.replace(".", "0").replace("#", "1"), 2) for line in lines]


BUG = rows8("..#..#..",
            "...##...",
            "..####..",
            ".#.##.#.",
            "..####..",
            ".#.##.#.",
            "..####..",
            ".#....#.")


def grow(rows):
    """the rows with every pixel's eight neighbours added, inside 8 x 8"""
    out = []
    for y in range(8):
        v = 0
        for dy in (-1, 0, 1):
            if 0 <= y + dy < 8:
                r = rows[y + dy]
                v |= r | (r << 1 & 0xFF) | r >> 1
        out.append(v)
    return out


MASK = [~r & 0xFF for r in grow(BUG)]      # 1 where the tiles show through


def copy(s):
    """copy s of the bug, s pixels to the right: the left column's eight rows,
    mask and shape, then the right column's"""
    left, right = [], []
    for m, b in zip(MASK, BUG):
        m16 = ((m << 8 | 0xFF) >> s | (0xFFFF << (16 - s))) & 0xFFFF
        b16 = (b << 8) >> s
        left += [m16 >> 8, b16 >> 8]
        right += [m16 & 0xFF, b16 & 0xFF]
    return left + right


COPIES = [b for s in range(8) for b in copy(s)]
assert copy(0)[16:] == [0xFF, 0x00] * 8


# ------------------------------------------------------------------ the model
def where(x, y):
    """the offset of the name under the bug's top left: 32 x (y / 8) + x / 8"""
    return 32 * (y // 8) + x // 8


def tile_bytes(n, pats):
    """name n's 8 shape bytes and 8 colour bytes: a tile's, or a bug's pattern"""
    if n < FIRST:
        return TILES[n][1], TILES[n][2]
    return pats[n][0], pats[n][1]


def build_model(bugs, stacked=False, paint=False):
    """what the programs leave: the names on the screen, and each bug's four
    patterns, shapes and colours. bugs: [(x, y), ...] in the order drawn;
    stacked: each built from the names on the screen (stack.asm), else from
    the tiles' (every other program)"""
    shown = list(NAMES)
    pats = {}
    for i, (x, y) in enumerate(bugs):
        p, h = FIRST + 4 * i, where(x, y)
        src = shown if stacked else NAMES
        cells = [src[h], src[h + 32], src[h + 1], src[h + 33]]   # TL, BL, TR, BR
        shape, col = [], []
        for n in cells:
            s, c = tile_bytes(n, pats)
            shape += list(s)
            col += list(c)
        cp = copy(x & 7)
        for k in range(8):
            t = (y & 7) + k
            for j in (0, 1):                     # the left column, the right
                at = 16 * j + t
                m, b = cp[16 * j + 2 * k], cp[16 * j + 2 * k + 1]
                shape[at] = shape[at] & m | b
                if paint:
                    col[at] = col[at] & 0x0F | BLACK << 4
        for q in range(4):
            pats[p + q] = (shape[8 * q:8 * q + 8], col[8 * q:8 * q + 8])
        for c, q in ((h, 0), (h + 32, 1), (h + 1, 2), (h + 33, 3)):
            shown[c] = p + q
    return shown, pats


def vram_of(bugs, stacked=False, paint=False):
    """the 16 KB of VRAM the programs leave"""
    v = bytearray(16384)
    for n, (_, s, c) in enumerate(TILES):
        v[8 * n:8 * n + 8] = bytes(s)
        v[0x2000 + 8 * n:0x2000 + 8 * n + 8] = bytes(c)
    shown, pats = build_model(bugs, stacked, paint)
    v[0x1800:0x1B00] = bytes(shown)
    v[0x1B00] = 0xD0
    for n, (s, c) in pats.items():
        v[8 * n:8 * n + 8] = bytes(s)
        v[0x2000 + 8 * n:0x2000 + 8 * n + 8] = bytes(c)
    return v


# ------------------------------------------------------------------ places
SHIFTS = [(24 + 25 * k, 16 + k) for k in range(8)]             # x AND 7 = y AND 7 = k
COLOURS = [(100, 4), (52, 37), (68, 50), (120, 36)]            # bricks, coin, grass, sky
EDGE = [(252, 100)]                                            # x + 8 past the right edge
WALK_FROM, WALK_FRAMES = (16, 4), 64
SWARM_FROM, SWARM_FRAMES = [(24 + 30 * i, 22) for i in range(6)], 48
CROSS_FROM, CROSS_FRAMES = [(60, 20, 1), (140, 20, -1)], 64   # x, y, dx
COST_AT = (24, 20)          # cost.asm's bug: x = 24 + shift


def walk_path():
    x0, y0 = WALK_FROM
    return [[(x0 + k, y0 + k)] for k in range(WALK_FRAMES)]


def swarm_path():
    return [[(x + k, y) for x, y in SWARM_FROM] for k in range(SWARM_FRAMES)]


def cross_path():
    return [[(x + d * k, y) for x, y, d in CROSS_FROM] for k in range(CROSS_FRAMES)]


# ------------------------------------------------------------------ routines
SETUP = """init:   di
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
        ld a, $D0
        out (VDP_DATA), a
        VRAM_WRITE $0000        ; the tiles' shapes
        ld hl, shapes
        ld c, VDP_DATA
        ld b, {nbytes}
        otir
        VRAM_WRITE $2000        ; and their colours
        ld hl, colours
        ld b, {nbytes}
        otir
        ld hl, map              ; chapter 24's screen: its names, a copy
        ld de, names
        ld bc, 768
        ldir
        ld hl, map              ; and the names on the screen, to begin with
        ld de, shown
        ld bc, 768
        ldir
        VRAM_WRITE $1800
        ld hl, names
        ld c, VDP_DATA          ; LDIR left C at 0
        ld b, 0                 ; 256
        otir
        otir
        otir
        ld hl, recs             ; the bugs' records
        ld de, bugs
        ld bc, {nrec}
        ldir
        ld hl, copy0            ; the bug as drawn: copy 0
        ld de, copies
        ld bc, 32
        ldir
p0:     call preshift           ; and copies 1 to 7
p1:     call step               ; every bug built where it starts
"""

PRESHIFT = """
; preshift: copies 1 to 7 of the bug, each the one before a pixel to the
; right. A copy is 32 bytes: the left column's eight rows, mask and shape,
; then the right column's, 16 bytes on; bit 4 of the address says which.
preshift:
        ld hl, copies           ; from copy 0
        ld de, copies + 32      ; to copy 1
        ld b, 7 * 8             ; seven copies of eight rows
.row:   scf                     ; the mask: 1 comes in at the left
        ld a, (hl)
        rra                     ; the left byte, a pixel right
        ld (de), a
        set 4, l
        set 4, e
        ld a, (hl)
        rra                     ; the right byte takes what left the left one
        ld (de), a
        res 4, l
        res 4, e
        inc l
        inc e
        or a                    ; the shape: 0 comes in at the left
        ld a, (hl)
        rra
        ld (de), a
        set 4, l
        set 4, e
        ld a, (hl)
        rra
        ld (de), a
        res 4, l
        res 4, e
        inc l
        inc e
        ld a, l
        and 15
        jr nz, .same            ; a row of the copy done; the copy done?
        ld a, l
        add a, 16
        ld l, a                 ; the next copy, past the right column
        ld a, e
        add a, 16
        ld e, a
.same:  djnz .row
        ret
"""

CELLS = """
; cells: the four tiles under the bug of the record at IX into its four
; patterns in the RAM, shapes and colours; its place kept at HERE
cells:  call where
        ld (ix + HERE), l
        ld (ix + HERE + 1), h
        ld bc, {src}
        add hl, bc              ; the name under its top left
        push hl
        call buffer
        ex de, hl               ; DE: its first pattern in the RAM
        pop hl
        push hl
        ld a, (hl)
        call cell               ; top left
        pop hl
        push hl
        ld bc, 32
        add hl, bc
        ld a, (hl)
        call cell               ; bottom left
        pop hl
        inc hl
        push hl
        ld a, (hl)
        call cell               ; top right
        pop hl
        ld bc, 32
        add hl, bc
        ld a, (hl)
        jr cell                 ; bottom right

; cell: the 8 shape bytes of name A to DE, and its 8 colour bytes to
; DE + $400; DE comes back 8 on
cell:   push de
        call tile               ; HL: the shape bytes
        DUP 8
        ldi
        EDUP
        ld bc, $400 - 8         ; the colours are $400 on, in both places
        add hl, bc
        ex de, hl
        add hl, bc
        ex de, hl
        DUP 8
        ldi
        EDUP
        pop de
        ld a, e
        add a, 8
        ld e, a                 ; no bug's patterns cross a page
        ret

; tile: HL = the shape bytes of name A: a tile's, in the cartridge, below
; 128; a bug's pattern, in the RAM, from 128
tile:   ld l, a
        ld h, 0
        add hl, hl
        add hl, hl
        add hl, hl              ; 8 x A
        cp {first}
        jr nc, .bug
        ld bc, shapes
        add hl, bc
        ret
.bug:   ld bc, pats - {first} * 8
        add hl, bc
        ret

; where: HL = the offset of the name under the bug's top left, 0 to 767:
; 32 x (y / 8) + x / 8
where:  ld a, (ix + Y)
        and $F8
        ld l, a
        ld h, 0
        add hl, hl
        add hl, hl              ; 32 x (y / 8)
        ld a, (ix + X)
        rrca
        rrca
        rrca
        and 31                  ; x / 8
        or l
        ld l, a
        ret

; buffer: HL = the RAM's copy of the bug's first pattern
buffer: ld l, (ix + PAT)
        ld h, 0
        add hl, hl
        add hl, hl
        add hl, hl
        ld bc, pats - {first} * 8
        add hl, bc
        ret
"""

BUILD = """
; build: the bug of the record at IX into its four patterns in the RAM: the
; tiles under it, then the bug from copy x AND 7, through its mask
build:  call cells
        call buffer
        ld a, (ix + Y)
        and 7
        or l
        ld l, a                 ; HL: the left column's row for its top
        ld a, (ix + X)
        and 7
        rrca
        rrca
        rrca                    ; 32 x (x AND 7)
        ld e, a
        ld d, high copies       ; DE: its copy
        ld b, 8
        call column             ; the left column
        set 4, l                ; and the right, 16 bytes on
        res 3, l
        ld b, 8

; column: eight rows of a column of the bug's patterns: the tiles AND the
; mask, OR the bug
column: ld a, (de)              ;  8  the mask
        and (hl)                ;  8  what of the tiles stays
        inc e                   ;  5
        ex de, hl               ;  5
        or (hl)                 ;  8  and the bug
        ex de, hl               ;  5
        inc e                   ;  5
        ld (hl), a              ;  8
        inc l                   ;  5
        djnz column             ; 14, or 9
        ret
"""

SBUILD = """
; sbuild: build, with the bug's rows shifted as they are drawn, not taken
; from a copy: x AND 7 times a row, the mask and the shape
sbuild: call cells
        call buffer
        ld a, (ix + Y)
        and 7
        or l
        ld l, a                 ; HL: the left column's row for its top
        ld de, rows             ; the bug: mask and shape, a row at a time
        ld b, 8
.row:   push bc
        ld a, (de)
        inc de
        ld b, a
        ld c, $FF               ; B, C: the mask, 1s on the right
        ld a, (de)
        inc de
        push de
        ld d, a
        ld e, 0                 ; D, E: the shape, 0s on the right
        ld a, (ix + X)
        and 7
        jr z, .put
.shift: scf
        rr b
        rr c                    ; the mask a pixel right, 1 in at the left
        srl d
        rr e                    ; the shape a pixel right, 0 in at the left
        dec a
        jr nz, .shift
.put:   ld a, (hl)
        and b
        or d
        ld (hl), a              ; the left column
        set 4, l
        ld a, (hl)
        and c
        or e
        ld (hl), a              ; the right column, 16 bytes on
        res 4, l
        inc l
        pop de
        pop bc
        djnz .row
        ret
"""

PAINT = """
; paint: the rows of the bug's patterns it covers, in both columns, given
; black ink: the high four bits of their colour bytes
paint:  call buffer
        ld bc, $400
        add hl, bc              ; the colours
        ld a, (ix + Y)
        and 7
        or l
        ld l, a
        ld b, 8
.row:   ld a, (hl)
        and $0F
        or BLACK << 4
        ld (hl), a              ; the left column
        set 4, l
        ld a, (hl)
        and $0F
        or BLACK << 4
        ld (hl), a              ; the right column
        res 4, l
        inc l
        djnz .row
        ret
"""

STEP = """
; step: every bug a step on and built again. First the names the bugs left
; in shown go back to the tiles', for all of them; then each bug moves, is
; built and puts its four names in shown
step:   ld ix, bugs
        ld a, NBUGS
.clear: push af
        call unmark
        ld bc, {rec}
        add ix, bc
        pop af
        dec a
        jr nz, .clear
        ld ix, bugs
        ld a, NBUGS
.move:  push af
        ld a, (ix + X)
        add a, (ix + DX)
        ld (ix + X), a
        ld a, (ix + Y)
        add a, (ix + DY)
        ld (ix + Y), a
        call build{paint}
        call mark
        ld bc, {rec}
        add ix, bc
        pop af
        dec a
        jr nz, .move
        ret

; unmark: the tiles' four names back in shown, where the bug is
unmark: ld l, (ix + HERE)
        ld h, (ix + HERE + 1)
        ld bc, names
        add hl, bc
        ld de, shown - names
        ex de, hl
        add hl, de
        ex de, hl               ; DE: the same name in shown
        ldi
        ldi
        ld bc, 30
        add hl, bc
        ex de, hl
        add hl, bc
        ex de, hl
        ldi
        ldi
        ret

; mark: the bug's four names in shown, where it is
mark:   ld l, (ix + HERE)
        ld h, (ix + HERE + 1)
        ld bc, shown
        add hl, bc
        ld a, (ix + PAT)
        ld (hl), a              ; top left: its first pattern
        inc hl
        add a, 2
        ld (hl), a              ; top right: the third
        ld bc, 31
        add hl, bc
        dec a
        ld (hl), a              ; bottom left: the second
        inc hl
        add a, 2
        ld (hl), a              ; bottom right: the fourth
        ret
"""

SEND = """
; send: after the paper, the tiles' names back where every bug was; then
; each bug's four patterns, their colours, and its names where it is
send:   ld ix, bugs
        ld a, NBUGS
.old:   push af
        ld l, (ix + WAS)
        ld h, (ix + WAS + 1)
        ld de, names
        call two                ; the top two
        ld bc, 32
        add hl, bc
        call two                ; and the two below
        ld bc, {rec}
        add ix, bc
        pop af
        dec a
        jr nz, .old
        ld ix, bugs
        ld a, NBUGS
.new:   push af
        call look
        call place
        ld bc, {rec}
        add ix, bc
        pop af
        dec a
        jr nz, .new
        ret

; two: the names (DE + HL) and (DE + HL + 1) to the VDP, at $1800 + HL
two:    ld a, l
        out (VDP_CTRL), a
        ld a, h
        or $58                  ; + $1800, and the bit that says write
        out (VDP_CTRL), a
        push hl
        add hl, de
        ld a, (hl)
        out (VDP_DATA), a
        inc hl
        ld a, (hl)
        out (VDP_DATA), a
        pop hl
        ret

; look: the bug's four patterns and their colours, from the RAM to the VDP
look:   ld l, (ix + PAT)
        ld h, 0
        add hl, hl
        add hl, hl
        add hl, hl              ; 8 x its first pattern: its VRAM address
        ld e, l
        ld d, h
        ld a, e
        out (VDP_CTRL), a
        ld a, d
        or $40
        out (VDP_CTRL), a
        ld bc, pats - {first} * 8
        add hl, bc              ; and the RAM's
        ld bc, 32 << 8 | VDP_DATA
        otir                    ; the four patterns
        ld a, e
        out (VDP_CTRL), a
        ld a, d
        or $60                  ; $2000 on: the colours
        out (VDP_CTRL), a
        ld bc, $400 - 32
        add hl, bc
        ld bc, 32 << 8 | VDP_DATA
        otir                    ; their colours
        ret

; place: the bug's four names to the VDP where it is, and that place kept
; as where it was, for the next send
place:  ld l, (ix + HERE)
        ld h, (ix + HERE + 1)
        ld (ix + WAS), l
        ld (ix + WAS + 1), h
        ld a, l
        out (VDP_CTRL), a
        ld a, h
        or $58
        out (VDP_CTRL), a
        ld a, (ix + PAT)
        out (VDP_DATA), a       ; top left
        add a, 2
        out (VDP_DATA), a       ; top right
        ld bc, 32
        add hl, bc
        ld a, l
        out (VDP_CTRL), a
        ld a, h
        or $58
        out (VDP_CTRL), a
        ld a, (ix + PAT)
        inc a
        out (VDP_DATA), a       ; bottom left
        add a, 2
        out (VDP_DATA), a       ; bottom right
        ret
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
"""
CLEAR_F = "        in a, (VDP_CTRL)        ; F cleared: the first wait ends with a paper\n"
DONE = "done:   jr done\n"


def ram(nbugs):
    return f"""names   EQU ${NAMES_RAM:04X}               ; the tiles' names, a copy
shown   EQU ${SHOWN_RAM:04X}               ; the names on the screen
pats    EQU ${PATS_RAM:04X}               ; the bugs' patterns; colours $400 on
copies  EQU ${COPIES_RAM:04X}               ; the eight copies of the bug
bugs    EQU VARS                ; the bugs' records, {REC} bytes each
count   EQU VARS + $F0          ; the frames left
NBUGS   EQU {nbugs}
X       EQU {X}                       ; a record: x and y, its top left pixel
Y       EQU {Y}
PAT     EQU {PAT}                       ; its first pattern
DX      EQU {DX}                       ; its step, each frame
DY      EQU {DY}
HERE    EQU {HERE_}                       ; the offset of its top left name now
WAS     EQU {WAS}                       ; and when last sent
"""


def records(bugs, steps):
    """the records as the cartridge holds them: each bug one step back, as
    step moves it before it builds"""
    out = []
    for i, ((x, y), (dx, dy)) in enumerate(zip(bugs, steps)):
        out += [(x - dx) & 0xFF, (y - dy) & 0xFF, FIRST + 4 * i, dx & 0xFF, dy & 0xFF, 0, 0, 0, 0]
        out += [0] * (REC - 9)
    return out


def data(bugs, steps):
    shapes = [b for _, s, _ in TILES for b in s]
    cols = [b for _, _, c in TILES for b in c]
    rows_ = [b for m, s in zip(MASK, BUG) for b in (m, s)]
    return ("shapes:                         ; the tiles' shapes, name 0 on\n" + db_rows(shapes) +
            "        ds shapes + $400 - $, 0 ; their colours, $400 on\n" +
            "colours:\n" + db_rows(cols) +
            "map:                            ; chapter 24's screen\n" + db_rows(NAMES, 16) +
            "copy0:                          ; the bug: left column, mask and shape a row\n" +
            db_rows(copy(0)[:16]) +
            "        db $FF, $00, $FF, $00, $FF, $00, $FF, $00   ; the right column: nothing\n" * 2 +
            "rows:                           ; the bug's rows, mask and shape, for sbuild\n" +
            db_rows(rows_) +
            "recs:                           ; x, y, the first pattern, dx, dy\n" +
            db_rows(records(bugs, steps), REC))


def program(name, what, say, bugs, steps, body, src="names", paint=False, extra=""):
    nbytes = 8 * len(TILES)
    code = (SETUP.format(nbytes=nbytes, nrec=REC * len(bugs)) + body + DONE + FRAME +
            PRESHIFT + BUILD + extra + CELLS.format(src=src, first=FIRST) +
            (PAINT if paint else "") +
            STEP.format(rec=REC, paint="\n        call paint" if paint else "") +
            SEND.format(rec=REC, first=FIRST))
    return head(name, what) + ram(len(bugs)) + say + tidy(code) + data(bugs, steps) + CART_END


STILL = """        call send               ; the bugs to the VDP, the display off
""" + ON


def film(frames):
    return ON + CLEAR_F + f"""        ld a, {frames}
        ld (count), a
loop:   call frame              ; the end of the paper
m0:     call send               ; the bugs to the VDP
m1:     call step               ; the next step, while the paper is drawn
s1:     ld hl, count
        dec (hl)
        jr nz, loop
"""


def shifts():
    return program("shifts", "a bug at every shift", """; Eight bugs on the sky, bug k at x AND 7 = k and y AND 7 = k.
""", SHIFTS, [(0, 0)] * 8, STILL)


def edge():
    return program("edge", "a bug at the right edge", f"""; A bug at ({EDGE[0][0]}, {EDGE[0][1]}): its right column is past the last column of names.
""", EDGE, [(0, 0)], STILL)


def colours(name):
    paint = name == "paint"
    say = ("""; Four bugs: on the bricks, a coin, the grass and the sky, each in the
; colours of the tiles under it.
""" if not paint else """; under.asm's four bugs, the rows each covers given black ink.
""")
    return program(name, "the colours under the bug" if not paint else "the bug's rows painted black",
                   say, COLOURS, [(0, 0)] * 4, STILL, paint=paint)


def walk():
    return program("walk", "a bug across the screen", f"""; A bug that walks across chapter 24's screen, from ({WALK_FROM[0]}, {WALK_FROM[1]}), a pixel right and a
; line down each frame, for {WALK_FRAMES} frames.
""", [WALK_FROM], [(1, 1)], film(WALK_FRAMES))


def swarm():
    return program("swarm", "six bugs on the same lines", f"""; Six bugs on lines {SWARM_FROM[0][1]} to {SWARM_FROM[0][1] + 7}, each a pixel right each frame, for {SWARM_FRAMES} frames:
; more than the four hardware sprites a line takes (chapter 27).
""", SWARM_FROM, [(1, 0)] * len(SWARM_FROM), film(SWARM_FRAMES))


def cross(name):
    stacked = name == "stack"
    say = (f"""; WHERE IT BREAKS. Two bugs on lines {CROSS_FROM[0][1]} to {CROSS_FROM[0][1] + 7} that cross: A from x = {CROSS_FROM[0][0]} to the
; right, B from x = {CROSS_FROM[1][0]} to the left, for {CROSS_FRAMES} frames. Each is built from the tiles under it.
""" if not stacked else """; overlap.asm's two bugs, each built from the names on the screen: where B
; shares a cell with A, from A's pattern.
""")
    return program(name, "two bugs, each from the tiles" if not stacked else "two bugs, each from the screen",
                   say, [(x, y) for x, y, _ in CROSS_FROM], [(d, 0) for _, _, d in CROSS_FROM],
                   film(CROSS_FRAMES), src="shown" if stacked else "names")


def cost():
    body = ""
    x0, y0 = COST_AT
    for k in range(8):
        body += f"""        ld (ix + X), {x0 + k}
b{k}:     call build              ; shift {k}, from the copy
e{k}:     ld (ix + X), {x0 + k}
c{k}:     call sbuild             ; shift {k}, shifted as it goes
d{k}:
"""
    return program("cost", "build and sbuild, timed", """; preshift, then build and sbuild at the eight shifts, one after another;
; nothing is shown.
""", [COST_AT], [(0, 0)], "        ld ix, bugs\n" + body, extra=SBUILD)


PROGRAMS = {"shifts": shifts, "cost": cost, "edge": edge, "under": lambda: colours("under"),
            "paint": lambda: colours("paint"), "walk": walk, "swarm": swarm,
            "overlap": lambda: cross("overlap"), "stack": lambda: cross("stack")}


def main():
    for name, make in PROGRAMS.items():
        with open(os.path.join(HERE, f"{name}.asm"), "w") as f:
            f.write(make())
    print(" ".join(f"{n}.asm" for n in PROGRAMS))


if __name__ == "__main__":
    main()
