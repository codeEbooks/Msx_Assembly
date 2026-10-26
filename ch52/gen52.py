#!/usr/bin/env python3
"""gen52.py - the programs of chapter 52: optimisation.

    python3 gen52.py && ./build.sh

The chapter starts from chapter 42's over.asm, the game's frame with nine
balls, which loses three frames at 60 Hz. Each program here is the one before
it with one more piece made faster; none changes what the game does:

    win.asm     the next window's names at 29 T-states, OUTI and JP NZ, the
                least the VDP takes while the paper is drawn (chapter 20),
                not 46; the balls in a page of their own, $C600, room for 31
    tests.asm   tests unrolled: for each first ball its X and Y less 15 in B
                and C, then for each ball after it four instructions, its X
                at a fixed address, a CALL only when the two are near in X
    sends.asm   show without the multiplication, each shift's patterns in a
                page of their own, and show's and sprites' bytes sent by
                OUTIs one after another, 18 T-states a byte, in the border
    moves.asm   move unrolled, each ball's Y and X kept in the copy of the
                attributes (build is gone), its DX and DY in dirs, a page
                walked with INC L
    patch.asm   move copied into the RAM at INIT, each ball's two
                directions kept as instructions, INC A or DEC A, which the
                bounces and the bumps rewrite
    inrom.asm   WHERE IT BREAKS. patch.asm with move left in the cartridge:
                the writes to its own code go nowhere

Every program ends with asmparts.CART_END; build.sh assembles them with
--syntax=bFw. program(name, n) makes any of them with n balls, 2 to 31, for
the count of meas52.py.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "ch42"))
import gen42  # noqa: E402  (chapter 42: the game's frame)
from gen42 import gen37, gen39, gen40, gen41, gen35, gen29  # noqa: E402,F401
from asmparts import HEAD, CART_END, IM2  # noqa: E402
from gen26 import tidy, db_rows, big, BALL  # noqa: E402
sys.path.insert(0, HERE)

EU, JP = gen42.EU, gen42.JP
MACHINES = gen42.MACHINES
VERSIONS = ["win", "tests", "sends", "moves", "patch"]
BROKEN = "inrom"
PROGRAMS = VERSIONS + [BROKEN]
LEVEL = {"over": 0, "win": 1, "tests": 2, "sends": 3, "moves": 4, "patch": 5, "inrom": 5}
NBALLS = 9                              # the balls of over.asm
MOST = 31                               # the most: 32 sprites, the last one $D0
START = gen42.more_balls(MOST)          # chapter 42's places, and more after the 24th
assert START[:len(gen42.START_ALL)] == gen42.START_ALL
COLOURS = [gen42.BLACK if k % 2 == 0 else gen42.DARK_BLUE for k in range(MOST)]
COPY = 0xC480                           # the sprites' attributes: 4 x 31 + 1 bytes
BALLS = 0xC600                          # X, Y, DX, DY of each ball, a page (win to sends)
DIRS = 0xC600                           # DX and DY of each ball, a page (moves)
MOVES = 0xC800                          # move's code in the RAM (patch)
INC_A, DEC_A = 0x3C, 0x3D               # a direction, as patch.asm keeps it


def xat(level, k):
    """where ball K's X is"""
    return f"balls + {4 * k}" if level < 4 else f"copy + {4 * k + 1}"


def yat(level, k):
    return f"balls + {4 * k + 1}" if level < 4 else f"copy + {4 * k}"


# ------------------------------------------------------------------ the RAM
def game_ram(level):
    out = f"""score   EQU ${gen42.GAME:04X}               ; three BCD bytes (chapter 40)
hi      EQU score + 3           ; the best, three more
shown   EQU score + $100        ; the six bytes last sent, a page on
at      EQU ${gen42.GAME + 0x10:04X}               ; pixels the scroll has gone, 0 to 511, two bytes
col     EQU at + 2              ; the column shown, 0 to 63: at / 8
table   EQU at + 3              ; the name table not shown: $18 or $1C, its high byte
need    EQU at + 4              ; rows of the next window still to write
wsrc    EQU at + 5              ; where they come from in pmap, two bytes
wdst    EQU at + 7              ; and where they go in the VRAM, two bytes
last    EQU at + 9              ; frames, the last time the logic counted them
counted EQU at + 10             ; the frames it counted
seed    EQU at + 11             ; random's state, two bytes (chapter 41)
"""
    if level < 2:
        out += """left    EQU at + 13             ; tests: the balls after the first
other   EQU at + 14             ; tests: the second ball, two bytes
"""
    out += f"copy    EQU ${COPY:04X}               ; the sprites' attributes, and $D0\n"
    if level < 4:
        out += f"balls   EQU ${BALLS:04X}               ; X, Y, DX, DY of each ball, a page\n"
    elif level == 4:
        out += f"dirs    EQU ${DIRS:04X}               ; DX and DY of each ball, a page\n"
    else:
        out += f"MOVES   EQU ${MOVES:04X}               ; move's code, copied into the RAM at INIT\n"
    out += f"""ROWS    EQU {gen42.ROWS}
PW      EQU {gen42.PW}                ; a row of pmap
NB      EQU {gen42.NB}                ; the pairs' shapes at a shift, in bytes
"""
    return out


# ------------------------------------------------------------------ the window (win)
ROWS29 = """
; rows: B rows of the next window, from wsrc in pmap to wdst in the table not
; shown, at 29 T-states a name: OUTI and JP NZ, the least the VDP takes while
; the paper is drawn (chapter 20); both moved on for the rows after. Uses A,
; BC, DE, HL
rows:   ld e, b                 ;  5  E: the rows
        ld hl, (wdst)           ; 17
        di                      ;  5
        ld a, l                 ;  5
        out (VDP_CTRL), a       ; 12
        ld a, h                 ;  5
        or $40                  ;  8
        out (VDP_CTRL), a       ; 12  the first name, for writing
        ei                      ;  5
        ld bc, 32               ; 11
        ld d, e                 ;  5
.past:  add hl, bc              ; 12
        dec d                   ;  5
        jr nz, .past            ; 13, or 8
        ld (wdst), hl           ; 17  where the rows after will go
        ld hl, (wsrc)           ; 17
        ld a, e                 ;  5  A: the rows
        ld de, PW - 32          ; 11
        ld c, VDP_DATA          ;  8
.row:   ld b, 32                ;  8
.name:  outi                    ; 18
        jp nz, .name            ; 11: 29 T-states a name
        add hl, de              ; 12  the next row of pmap
        dec a                   ;  5
        jr nz, .row             ; 13, or 8
        ld (wsrc), hl           ; 17
        ret                     ; 11
"""


# ------------------------------------------------------------------ the tests, unrolled (tests)
def tests_code(level, n):
    """tests with no loop: a block for each first ball, four instructions for
    each ball after it; and the stubs and near"""
    out = ["",
           "; tests: every two balls, the first with each after it, unrolled: for each",
           "; first ball its X and Y less 15 in B and C and its number in D, then for",
           "; each ball after it its X at a fixed address, less B: the two are less than",
           "; 16 apart in X when that is below 31, and only then the CALL is taken. Uses",
           "; A, BC, D, and near and bump the others",
           "tests:"]
    for i in range(n - 1):
        out += [f"        ld a, ({xat(level, i)})        ; 14  ball {i}",
                "        sub 15                  ;  8",
                "        ld b, a                 ;  5  B: its X less 15",
                f"        ld a, ({yat(level, i)})        ; 14",
                "        sub 15                  ;  8",
                "        ld c, a                 ;  5  C: its Y less 15",
                f"        ld d, {i}                 ;  8  D: its number"]
        for j in range(i + 1, n):
            out += [f"        ld a, ({xat(level, j)})        ; 14  ball {j}",
                    "        sub b                   ;  5  its X less ours, plus 15",
                    "        cp 31                   ;  8",
                    f"        call c, .n{j}            ; 11, or 18  less than 16 apart in X"]
    out.append("        ret                     ; 11")
    out += ["; .n1 to .n{0}: ball j near the first in X -> its Y tested, and if it".format(n - 1),
            "; is near in Y too, near with E = j"]
    for j in range(1, n):
        out += [f".n{j}: ld a, ({yat(level, j)})        ; 14  ball {j}",
                "        sub c                   ;  5",
                "        cp 31                   ;  8",
                "        ret nc                  ; 12, or 6  16 or more apart in Y",
                f"        ld e, {j}                 ;  8",
                "        jp near                 ; 11"]
    return "\n".join(out) + "\n" + (NEAR_AOS if level < 4 else NEAR_COPY)


NEAR_AOS = """
; near: D, E = the numbers of two balls whose boxes meet, B and C the first's
; X and Y less 15 -> touched, and if a pixel of one is a pixel of the other,
; bump (chapter 42's, IX the first, HL the second). Keeps BC and DE
near:   push bc                 ; 12
        push de                 ; 12
        ld a, b                 ;  5
        add a, 15               ;  8
        ld b, a                 ;  5  B: the first's X
        ld a, c                 ;  5
        add a, 15               ;  8
        ld c, a                 ;  5  C: its Y
        ld a, e                 ;  5
        add a, a                ;  5
        add a, a                ;  5
        ld l, a                 ;  5
        ld h, high balls        ;  8  HL: the second, the balls at a page's start
        ld d, (hl)              ;  8
        inc l                   ;  5
        ld e, (hl)              ;  8  D, E: its X and Y
        dec l                   ;  5
        push hl                 ; 12
        call touched            ; 18
        pop hl                  ; 11
        jr z, .apart            ; 13, or 8  the boxes meet, the pixels do not
        pop de                  ; 11
        push de                 ; 12
        ld a, d                 ;  5
        add a, a                ;  5
        add a, a                ;  5
        ld e, a                 ;  5
        ld d, 0                 ;  8
        ld ix, balls            ; 16
        add ix, de              ; 17  IX: the first
        call bump               ; 18
.apart: pop de                  ; 11
        pop bc                  ; 11
        ret                     ; 11
"""

NEAR_COPY = """
; near: D, E = the numbers of two balls whose boxes meet, B and C the first's
; X and Y less 15 -> touched, and if a pixel of one is a pixel of the other,
; bump. Keeps BC and DE
near:   push bc                 ; 12
        push de                 ; 12
        ld a, b                 ;  5
        add a, 15               ;  8
        ld b, a                 ;  5  B: the first's X
        ld a, c                 ;  5
        add a, 15               ;  8
        ld c, a                 ;  5  C: its Y
        ld a, e                 ;  5
        add a, a                ;  5
        add a, a                ;  5
        add a, low copy         ;  8
        ld l, a                 ;  5
        ld h, high copy         ;  8  HL: the second's Y and X, in the copy
        ld e, (hl)              ;  8
        inc l                   ;  5
        ld d, (hl)              ;  8  D, E: its X and Y
        call touched            ; 18
        jr z, .apart            ; 13, or 8  the boxes meet, the pixels do not
        pop de                  ; 11
        push de                 ; 12
        call bump               ; 18  D and E: the two
.apart: pop de                  ; 11
        pop bc                  ; 11
        ret                     ; 11
"""


# ------------------------------------------------------------------ the sends (sends)
SHOW3 = """
; show: the pairs' patterns at the scroll's shift, NB bytes after the paper
; (chapter 29), each shift in a page of its own: the page is high shifts plus
; the shift, and no multiplication. The NB bytes go by NB OUTIs one after
; another, 18 T-states a byte: the border takes them as fast as that (chapter
; 20). And when the scroll has reached a new column, the table that holds it
; shown with R#2, and the next window to be written
show:   VRAM_WRITE $0000        ; 40
        ld a, (at)              ; 14
        and 7                   ;  8  the shift
        add a, high shifts      ;  8
        ld h, a                 ;  5
        ld l, 0                 ;  8  HL: its page
        ld c, VDP_DATA          ;  8
        DUP NB
        outi                    ; 18
        EDUP
""" + gen42.SHOW.split("        otir                    ; 23 a byte, 18 the last\n")[1].split("\n; mul:")[0] + "\n"
assert SHOW3.count("ld hl, (at)") == 1 and "mul:" not in SHOW3 and "call mul" not in SHOW3

SPRITES3 = """
; sprites: the balls' attributes from the copy, after the paper, by OUTIs one
; after another. Uses BC, HL
sprites: VRAM_WRITE SAT         ; 40
        ld hl, copy             ; 11
        ld c, VDP_DATA          ;  8
        DUP 4 * NBALLS + 1
        outi                    ; 18
        EDUP
        ret                     ; 11
"""


def shifts_data():
    """chapter 29's eight copies of the pairs, each at a page's start"""
    out = "        ALIGN 256, $FF\nshifts:                         ; the pairs at shifts 0 to 7, a page each\n"
    for s in range(8):
        if s:
            out += "        ALIGN 256, $FF\n"
        out += db_rows(gen42.shapes_at(s), 16)
    return out


# ------------------------------------------------------------------ the balls (moves, patch)
SCROLL = """        ld hl, (at)             ; 17
        inc hl                  ;  7
        ld a, h                 ;  5
        and 1                   ;  8  512 pixels, then 0 again
        ld h, a                 ;  5
        ld (at), hl             ; 17
"""


def move4(n):
    out = """
; move: a frame of the game: the scroll a pixel on, the level round, and each
; ball a step, back off the sky's edges. Unrolled: each ball's X and Y are
; where sprites sends them from, in the copy of the attributes, and its DX and
; DY in dirs, a page, HL walking it with INC L. Uses A, B, HL
move:
""" + SCROLL + "        ld hl, dirs             ; 11\n"
    for k in range(n):
        x, y = xat(4, k), yat(4, k)
        out += f"""        ld a, ({x})        ; 14  ball {k}: its X
        add a, (hl)             ;  8  plus DX
        cp XMAX + 1             ;  8
        call nc, bounce         ; 11, or 18  past the left or the right edge
        ld ({x}), a        ; 14
        inc l                   ;  5
        ld a, ({y})        ; 14  its Y
        add a, (hl)             ;  8  plus DY
        cp YMIN                 ;  8
        call c, bounce          ; 11, or 18  above the sky's top
        cp YMAX + 1             ;  8
        call nc, bounce         ; 11, or 18  below its bottom
        ld ({y}), a        ; 14
        inc l                   ;  5
"""
    out += """        ret                     ; 11

; bounce: A = a place plus its direction, past an edge, HL = the direction ->
; the direction turned, and A the place plus the new one. Uses B
bounce: ld b, a                 ;  5
        ld a, (hl)              ;  8
        neg                     ; 10
        ld (hl), a              ;  8  the other way
        add a, a                ;  5
        add a, b                ;  5  back by the old step, on by the new
        ret                     ; 11
"""
    return out


def op(d):
    return "inc a" if d == 1 else "dec a"


def move5(n, in_ram):
    """move with each ball's directions as instructions: INC A or DEC A. In
    patch.asm it is assembled for MOVES and copied there at INIT; in
    inrom.asm it runs where the cartridge has it"""
    if in_ram:
        head = """
; move: a frame of the game: the scroll a pixel on, the level round, and each
; ball a step, back off the sky's edges. Unrolled, its places in the copy of
; the attributes, and each ball's DX and DY kept in the code itself: the
; instruction that steps its X or Y is INC A or DEC A, and a bounce or a bump
; rewrites it. Code that writes itself cannot stay in the cartridge: this is
; assembled for MOVES, in the RAM, and INIT copies it there. Uses A, B, HL
moving: DISP MOVES              ; for the RAM; here, up to moved
move:
"""
    else:
        head = """
; move: patch.asm's, left in the cartridge
move:
"""
    out = head + SCROLL
    for k in range(n):
        x, y = xat(5, k), yat(5, k)
        bx, by = START[k][2], START[k][3]
        out += f"""        ld a, ({x})        ; 14  ball {k}: its X
.dx{k}: {op(bx)}                   ;  5  its direction, INC A or DEC A
        cp XMAX + 1             ;  8
        call nc, tx{k}           ; 11, or 18  past the left or the right edge
        ld ({x}), a        ; 14
        ld a, ({y})        ; 14  its Y
.dy{k}: {op(by)}                   ;  5
        cp YMIN                 ;  8
        call c, ty{k}            ; 11, or 18  above the sky's top
        cp YMAX + 1             ;  8
        call nc, ty{k}           ; 11, or 18  below its bottom
        ld ({y}), a        ; 14
"""
    out += "        ret                     ; 11\n"
    if in_ram:
        out += "        ENT\nmoved:\n"
    out += """
; tx0, ty0 and the others: a ball past an edge -> its direction turned, and A
; its place after a step the new way
"""
    for k in range(n):
        x, y = xat(5, k), yat(5, k)
        out += f"""tx{k}: ld hl, move.dx{k}         ; 11
        ld a, ({x})        ; 14  the X before the step
        jp turn                 ; 11
ty{k}: ld hl, move.dy{k}         ; 11
        ld a, ({y})        ; 14
        jp turn                 ; 11
"""
    out += """
; turn: HL = where a direction is, INC A or DEC A, A = a place -> the
; direction the other way from now on, and A the place after a step that way.
; INC A is $3C and DEC A $3D: bit 0 is the way. Uses B
turn:   ld b, a                 ;  5  the place
        ld a, (hl)              ;  8
        xor 1                   ;  8  INC A becomes DEC A, DEC A INC A
        ld (hl), a              ;  8  written into move's code
        rrca                    ;  5  carry: DEC A, to the left or up
        ld a, b                 ;  5
        jr c, .back             ; 13, or 8
        inc a                   ;  5
        ret                     ; 11
.back:  dec a                   ;  5
        ret                     ; 11
"""
    return out


BUMP_TAIL = """        ld a, $10               ;  8  ten points
        call addsc              ; 18
        call best               ; 18
        call random             ; 18
        and 3                   ;  8  one of the four effects
        di                      ;  5  sfx and the interrupt share chan_x
        call sfx                ; 18
        ei                      ;  5
        ret                     ; 11
; .part: A = the sign of the directions' difference, B = a distance -> A
; the distance, less it, or 0
.part:  or a                    ;  5
        ret z                   ; 12, or 6
        ld a, b                 ;  5
        ret p                   ; 12, or 6
        neg                     ; 10
        ret                     ; 11
"""

BUMP_PLACES = """        ld h, high copy         ;  8
        ld a, d                 ;  5
        add a, a                ;  5
        add a, a                ;  5
        add a, low copy         ;  8
        ld l, a                 ;  5  HL: the first's Y and X
        ld c, (hl)              ;  8
        inc l                   ;  5
        ld b, (hl)              ;  8  B, C: its X and Y
        ld a, e                 ;  5
        add a, a                ;  5
        add a, a                ;  5
        add a, low copy         ;  8
        ld l, a                 ;  5  the second's
        ld a, (hl)              ;  8
        sub c                   ;  5
        ld c, a                 ;  5  C: the second's Y less the first's
        inc l                   ;  5
        ld a, (hl)              ;  8
        sub b                   ;  5
        ld b, a                 ;  5  B: and the Xs
"""

BUMP4 = """
; bump: D, E = the numbers of two balls that touch -> if they come together,
; both go back the way they came, ten points are scored, and an effect chosen
; by random starts. Uses A, BC, DE, HL
bump:
""" + BUMP_PLACES + """        ld h, high dirs         ;  8
        ld a, e                 ;  5
        add a, a                ;  5
        ld e, a                 ;  5
        ld a, d                 ;  5
        add a, a                ;  5
        ld l, a                 ;  5  HL: the first's DX
        ld d, h                 ;  5  DE: the second's
        ld a, (de)              ;  8
        sub (hl)                ;  8  its DX less the first's: -2, 0 or 2
        call .part              ; 18
        ld b, c                 ;  5  B: the Ys' distance
        ld c, a                 ;  5  C: what the Xs give
        inc l                   ;  5
        inc e                   ;  5  the DYs
        ld a, (de)              ;  8
        sub (hl)                ;  8
        call .part              ; 18
        add a, c                ;  5  how fast they part
        ret p                   ; 12, or 6  0 or more: they part already
        ld a, (hl)              ;  8
        neg                     ; 10
        ld (hl), a              ;  8  the first's DY
        dec l                   ;  5
        ld a, (hl)              ;  8
        neg                     ; 10
        ld (hl), a              ;  8  and DX
        ex de, hl               ;  5
        ld a, (hl)              ;  8
        neg                     ; 10
        ld (hl), a              ;  8  the second's DY
        dec l                   ;  5
        ld a, (hl)              ;  8
        neg                     ; 10
        ld (hl), a              ;  8  and DX
""" + BUMP_TAIL

BUMP5 = """
; bump: D, E = the numbers of two balls that touch -> if they come together,
; both go back the way they came, ten points are scored, and an effect chosen
; by random starts. The directions are move's INC A and DEC A: xops says where
; each ball's X direction is, and its Y direction is 12 bytes on. INC A, $3C,
; is the smaller, so the first's less the second's has the sign of the
; second's direction less the first's. Uses A, BC, DE, HL, IX
bump:
""" + BUMP_PLACES + """        ld h, high xops         ;  8
        ld a, d                 ;  5
        add a, a                ;  5
        ld l, a                 ;  5
        ld a, (hl)              ;  8
        inc l                   ;  5
        ld h, (hl)              ;  8
        ld l, a                 ;  5
        push hl                 ; 12
        pop ix                  ; 16  IX: the first's X direction, its Y 12 on
        ld h, high xops         ;  8
        ld a, e                 ;  5
        add a, a                ;  5
        ld l, a                 ;  5
        ld a, (hl)              ;  8
        inc l                   ;  5
        ld h, (hl)              ;  8
        ld l, a                 ;  5  HL: the second's
        ld a, (ix + 0)          ; 21
        sub (hl)                ;  8  the sign of the DXs' difference
        call .part              ; 18
        ld b, c                 ;  5  B: the Ys' distance
        ld c, a                 ;  5  C: what the Xs give
        ld de, 12               ; 11
        add hl, de              ; 12  HL: the second's Y direction
        ld a, (ix + 12)         ; 21
        sub (hl)                ;  8
        call .part              ; 18
        add a, c                ;  5  how fast they part
        ret p                   ; 12, or 6  0 or more: they part already
        ld a, (hl)              ;  8
        xor 1                   ;  8
        ld (hl), a              ;  8  the second's Y direction turned
        or a                    ;  5
        sbc hl, de              ; 17
        ld a, (hl)              ;  8
        xor 1                   ;  8
        ld (hl), a              ;  8  and its X
        ld a, (ix + 0)          ; 21
        xor 1                   ;  8
        ld (ix + 0), a          ; 21  the first's X
        ld a, (ix + 12)         ; 21
        xor 1                   ;  8
        ld (ix + 12), a         ; 21  and Y
""" + BUMP_TAIL


def ops_tables(n):
    out = "        ALIGN 256, $FF\nxops:                           ; where each ball's X direction is, in move\n"
    out += "".join(f"        dw move.dx{k}\n" for k in range(n))
    return out


# ------------------------------------------------------------------ the program
def input_code(level):
    """chapter 42's input, which writes the first ball's DX where the
    program keeps it: in moves.asm in dirs, in patch.asm as move's INC A or
    DEC A"""
    text = gen42.INPUT
    if level == 4:
        text = text.replace("        ld hl, balls + 2        ; 11  the first ball's DX\n",
                            "        ld hl, dirs             ; 11  the first ball's DX\n")
    elif level == 5:
        text = text.replace("        ld hl, balls + 2        ; 11  the first ball's DX\n",
                            "        ld hl, move.dx0         ; 11  the first ball's X direction\n")
        text = text.replace(".left:  ld (hl), -1             ; 11\n", ".left:  ld (hl), $3D             ; 11  DEC A\n")
        text = text.replace(".go:    ld (hl), 1              ; 11\n", ".go:    ld (hl), $3C              ; 11  INC A\n")
        assert "$3D" in text and "$3C" in text
    assert level < 4 or "balls" not in text
    return text


def main_loop(level):
    text = gen42.main_loop(False)
    if level >= 4:
        text = text.replace("        call build              ; the attributes, in the copy\n", "")
        assert "build" not in text
    return text


def setup(level, n, in_ram=True):
    text = gen42.setup()
    old = """        ld hl, starts           ; the balls
        ld de, balls
        ld bc, 4 * NBALLS
        ldir
"""
    assert old in text
    if level == 4:
        new = """        ld hl, dirs0            ; the balls' directions: their places are in atts
        ld de, dirs
        ld bc, 2 * NBALLS
        ldir
"""
    elif level == 5:
        new = "" if not in_ram else """        ld hl, moving           ; move's code into the RAM, where it may change
        ld de, MOVES
        ld bc, moved - moving
        ldir
"""
    else:
        new = old
    return text.replace(old, new)


def data(level, n):
    shp_all = [b for s in range(8) for b in gen42.shapes_at(s)]
    cols = [b for a, b2 in gen42.PAIRS for b in gen29.pair_colours(a, b2)]
    pm = [p for row in gen42.PMAP for p in (row + row[:31])]
    atts = []
    for k in range(n):
        atts += [START[k][1], START[k][0], 0, COLOURS[k]]
    atts.append(0xD0)
    out = ""
    if level < 3:
        out += "shifts:                         ; the pairs at shifts 0 to 7, NB bytes each\n" + db_rows(shp_all, 16)
    out += ("pcols:                          ; their colours\n" + db_rows(cols, 16) +
            f"pmap:                           ; the pairs: {gen42.ROWS} rows of {gen42.WIDTH}, and their first 31 again\n" +
            db_rows(pm, 16) +
            f"letters:                        ; the status line's: {gen42.LETTERS!r}\n" +
            db_rows([b for ch in gen42.LETTERS for b in gen42.glyph(ch)]) +
            "digits:                         ; and its digits\n" +
            db_rows([b for ch in "0123456789" for b in gen42.glyph(ch)]) +
            "statusn:                        ; rows 21 to 23 of names\n" + db_rows(gen42.status_names(), 16) +
            "ball:                           ; chapter 26's ball, 16 x 16\n" + db_rows(big(BALL)) +
            "atts:                           ; the balls' attributes at the start, and the end\n" +
            db_rows(atts))
    if level < 4:
        start = [v & 255 for b in START[:n] for v in b]
        out += "starts:                         ; X, Y, DX, DY of each ball\n" + db_rows(start)
    elif level == 4:
        dirs = [v & 255 for b in START[:n] for v in b[2:]]
        out += "dirs0:                          ; DX and DY of each ball\n" + db_rows(dirs)
    out += ("nums:                           ; score and hi at the start\n" + db_rows([0, 0, 0] + gen42.HI0) +
            gen37.start_data() + gen39.shifted_data())
    if level >= 3:
        out += shifts_data()
    if level == 5:
        out += ops_tables(n)
    return out


SAY = {
    "win": """; over.asm (chapter 42) with the next window's names at 29 T-states, not
; 46, and the balls in a page of their own.
""",
    "tests": """; win.asm with tests unrolled.
""",
    "sends": """; tests.asm with each shift's patterns in a page of their own, and the sends
; by OUTIs one after another.
""",
    "moves": """; sends.asm with move unrolled, the balls' places in the copy of the
; attributes and their directions in a page.
""",
    "patch": """; moves.asm with move copied into the RAM, each ball's directions kept as
; instructions that the bounces and the bumps rewrite.
""",
    "inrom": """; WHERE IT BREAKS. patch.asm with move left in the cartridge.
""",
}
WHAT = {"win": "the window at 29 T-states", "tests": "tests unrolled",
        "sends": "the sends, a page a shift and OUTIs in a row",
        "moves": "move unrolled, the balls in the copy", "patch": "move rewrites itself, in the RAM",
        "inrom": "self-modifying code left in the ROM"}


def program(name, n=NBALLS, spread=False):
    """the program NAME with N balls; SPREAD: the next window written
    chapter 42's CHUNK rows a frame, as spread.asm does (for the workshop)"""
    level = LEVEL[name]
    assert 1 <= level and 2 <= n <= MOST
    consts = f"""NBALLS  EQU {n}                   ; the balls
SAT     EQU ${gen42.SAT:04X}               ; the sprites' attributes
SPAT    EQU ${gen42.SPAT:04X}               ; and patterns
DIGIT0  EQU ${gen42.DIGIT0:02X}                 ; the status line's digits: patterns $F0 to $F9
SCORE_AT EQU ${gen42.TABLES[0] + gen42.SCORE_AT:04X}             ; the score's first digit, in the table at $1800
HI_AT   EQU ${gen42.TABLES[0] + gen42.HI_AT:04X}               ; and the best's
XMAX    EQU {gen42.XMAX}                 ; a ball's X: 0 to XMAX
YMIN    EQU {gen42.YMIN}                   ; and its Y: YMIN to YMAX
YMAX    EQU {gen42.YMAX}
""" + (f"CHUNK   EQU {gen42.CHUNK}                   ; rows of the next window a frame\n" if spread else "")
    body = setup(level, n, name != BROKEN) + main_loop(level)
    parts = ((SHOW3 + SPRITES3) if level >= 3 else (gen42.SHOW + gen42.SPRITES))
    parts += gen42.PUTBCD + gen42.UPDATE + gen42.STATUS + input_code(level)
    if level < 4:
        parts += gen42.MOVE
    elif level == 4:
        parts += move4(n)
    else:
        parts += move5(n, name != BROKEN)
    parts += gen42.TESTS if level < 2 else tests_code(level, n)
    parts += gen42.BUMP if level < 4 else (BUMP4 if level == 4 else BUMP5)
    if level < 4:
        parts += gen42.BUILD
    parts += (gen42.STEP_SPREAD if spread else gen42.STEP_AT_ONCE) + ROWS29
    if level < 2:
        parts += gen39.BOXED
    parts += (gen39.TOUCHED + gen40.ADDSC + gen40.BEST + gen41.RANDOM + gen35.JOY +
              gen42.ISR + gen37.PACE + gen37.SEND + gen37.PLAY + gen37.ROW + gen37.VOICE +
              gen37.NEXT + gen37.SOUND + gen37.SFX)
    return (HEAD.format(name=name, chapter=52, what=WHAT[name]) + gen42.BIOS + gen42.ENGINE_RAM +
            game_ram(level) + consts + gen37.fields() + IM2 + SAY[name] + tidy(body + parts) +
            data(level, n) + gen37.ENGINE_INC + CART_END)


def main():
    with open(os.path.join(HERE, "music.inc"), "w") as f:
        f.write(gen37.music_inc())
    for name in PROGRAMS:
        with open(os.path.join(HERE, f"{name}.asm"), "w") as f:
            f.write(program(name))
    print("music.inc " + " ".join(f"{n}.asm" for n in PROGRAMS))


if __name__ == "__main__":
    main()
