#!/usr/bin/env python3
"""gen42.py - the programs of chapter 42: the frame budget.

    python3 gen42.py && ./build.sh

    budget.asm  a game's frame with nobody playing, made of the parts of the
                chapters before: chapter 29's scroll, a pixel a frame, with
                its pairs of tiles rewritten after the paper and the next
                window written all at once into the name table not shown
                when the scroll reaches a new column (pairs.asm); eight balls
                that bounce off the sky's edges and off each other, every
                two tested with boxed and touched (chapter 39); a bump is
                ten points, kept with addsc and best and sent with update
                (chapter 40) to the status line of both name tables, and an
                effect chosen by random (chapter 41) and started with sfx;
                the tune and the effects played by the interrupt (chapter
                37); row 8 of the keyboard and joystick 1 read every frame
                (chapters 34 and 35), though nobody presses them. R#7 marks
                each part of the frame in the border (chapter 33)
    spread.asm  budget.asm with the next window written a few rows a frame,
                over the frames before the scroll needs it

The level is chapter 29's, taken round: after its last column comes its
first. The status line is rows 21 to 23 of both name tables, in chapter 30's
characters, white on black. The sprites are chapter 26's ball, 16 x 16. The
interrupt is taken in mode 2 (chapter 17); every program ends with
asmparts.CART_END and build.sh assembles with --syntax=bFw.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
for ch in ("tools", "ch26", "ch29", "ch30", "ch33", "ch34", "ch35", "ch37", "ch39", "ch40", "ch41"):
    sys.path.insert(0, os.path.join(REPO, ch))
from asmparts import HEAD, CART_END, IM2, im2  # noqa: E402
from gen26 import tidy, db_rows, big, BALL  # noqa: E402  (chapter 26: the ball)
import gen29  # noqa: E402  (chapter 29: the level, its pairs, the scroll)
import shapes30  # noqa: E402  (chapter 30: the characters)
import gen33  # noqa: E402  (chapter 33: rate)
import gen35  # noqa: E402  (chapter 35: joy)
import gen37  # noqa: E402  (chapter 37: the sound engine)
import gen39  # noqa: E402  (chapter 39: boxed, touched)
import gen40  # noqa: E402  (chapter 40: addsc, best)
import gen41  # noqa: E402  (chapter 41: random)
sys.path.insert(0, HERE)

EU, JP = "MSXBOOK_EU16", "MSXBOOK_JP16"
MACHINES = [EU, JP]
BIOS = '        INCLUDE "bios.inc"\n'
BLACK, LIGHT_GREEN, DARK_BLUE, WHITE = 1, 3, 4, 15
NAME = {BLACK: "black", LIGHT_GREEN: "light green", DARK_BLUE: "dark blue", WHITE: "white"}

# ------------------------------------------------------------------ the level, round
ROWS = gen29.ROWS                       # 21 rows of names scroll
WIDTH = gen29.WIDTH                     # 64 columns, then the first again
PW = WIDTH + 31                         # a row of the pairs' map: 64 and the first 31 again
TABLES = gen29.TABLES                   # the two name tables, $1800 and $1C00
CHUNK = 3                               # spread.asm: rows of the next window a frame


def level():
    return gen29.level()


def pairs_round(lvl):
    """the pairs of tiles side by side in the level taken round, in the order
    met, and for each cell the number of its pair, the cell after the last
    column being the first column's"""
    pairs, pmap = [], []
    for row in lvl:
        out = []
        for c in range(WIDTH):
            p = (row[c], row[(c + 1) % WIDTH])
            if p not in pairs:
                pairs.append(p)
            out.append(pairs.index(p))
        pmap.append(out)
    return pairs, pmap


LVL = level()
PAIRS, PMAP = pairs_round(LVL)
NP = len(PAIRS)
NB = 8 * NP                             # bytes of the pairs' shapes at one shift


def shapes_at(s):
    return [b for a, b2 in PAIRS for b in gen29.shifted(a, b2, s)]


# ------------------------------------------------------------------ the status line
FONT = shapes30.wide()                  # codes 32 to 127, 8 bytes each
DIGIT0 = 0xF0                           # patterns 240 to 249: the digits
LETTERS = " SCOREHI"                    # patterns $E0 to $E7
LETTER0 = 0xE0
TEXT_C = WHITE << 4 | BLACK
STATUS_ROW = 22
SCORE_AT = 32 * STATUS_ROW + 8          # the score's first digit, in a table
HI_AT = 32 * STATUS_ROW + 24
LABELS = [(32 * STATUS_ROW + 2, "SCORE"), (32 * STATUS_ROW + 21, "HI")]
HI0 = [0x00, 0x02, 0x00]                # the best score before the game


def glyph(ch):
    return list(FONT[(ord(ch) - 32) * 8:(ord(ch) - 31) * 8])


def status_names(score=(0, 0, 0), hi=HI0):
    """rows 21 to 23 of names: the labels, the score and the best"""
    names = [LETTER0] * 96
    base = 32 * ROWS
    for at, text in LABELS:
        for k, ch in enumerate(text):
            names[at - base + k] = LETTER0 + LETTERS.index(ch)
    for at, num in ((SCORE_AT, score), (HI_AT, hi)):
        for k, b in enumerate(num):
            names[at - base + 2 * k] = DIGIT0 + (b >> 4)
            names[at - base + 2 * k + 1] = DIGIT0 + (b & 15)
    return names


# ------------------------------------------------------------------ the balls
BALLS = {"budget": 8, "over": 9, "spread": 9}     # balls in each program
XMAX = 240                              # a ball's X, 0 to 240
YMIN, YMAX = 8, 104                     # and its Y: in the sky, under the top
START = [(16, 16, 1, 1), (72, 40, -1, 1), (120, 24, 1, -1), (176, 72, -1, -1),
         (224, 48, -1, 1), (40, 88, 1, -1), (144, 96, -1, 1), (200, 8, 1, 1),
         (96, 64, 1, -1)]



def more_balls(upto=24):
    """the balls after the ninth, for the workshop's variants: each where no
    box of the ones before meets its box"""
    out = list(START)
    k = 0
    while len(out) < upto:
        k += 1
        x, y = (37 * k) % (XMAX + 1), YMIN + (29 * k) % (YMAX - YMIN + 1)
        if all(abs(x - b[0]) >= 16 or abs(y - b[1]) >= 16 for b in out):
            out.append((x, y, 1 if k % 2 else -1, -1 if k % 3 else 1))
    return out


START_ALL = more_balls()
COLOURS = [BLACK if k % 2 == 0 else DARK_BLUE for k in range(len(START_ALL))]
SAT = 0x1B00
SPAT = 0x3800
FRAMES = 900                            # frames a film is watched for

# ------------------------------------------------------------------ the RAM
ENGINE_RAM = f"""ticks   EQU VARS                ; the player's ticks, two bytes (chapter 37)
owed    EQU VARS + 2            ; lines owed to the player, two bytes
lines   EQU VARS + 4            ; the machine's lines a frame: 313 or 262
tick    EQU VARS + 6            ; ticks still to the next row
step    EQU VARS + 7            ; the song's step, two bytes
barno   EQU VARS + 9            ; the step's number
rowno   EQU VARS + 10           ; the row in the bar
frames  EQU VARS + 11           ; frames counted by isr
shadow  EQU VARS + ${gen37.SHADOW_AT:02X}          ; R0 to R10, as the next tick sends them
chan_a  EQU shadow + {gen37.SHADOW_REGS}         ; the channels, CHAN bytes each
chan_b  EQU chan_a + CHAN
chan_c  EQU chan_b + CHAN
chan_x  EQU chan_c + CHAN       ; the effect: a fourth channel, on C's registers
"""
GAME = 0xC400
GAME_RAM = f"""score   EQU ${GAME:04X}               ; three BCD bytes (chapter 40)
hi      EQU score + 3           ; the best, three more
shown   EQU score + $100        ; the six bytes last sent, a page on
at      EQU ${GAME + 0x10:04X}               ; pixels the scroll has gone, 0 to 511, two bytes
col     EQU at + 2              ; the column shown, 0 to 63: at / 8
table   EQU at + 3              ; the name table not shown: $18 or $1C, its high byte
need    EQU at + 4              ; rows of the next window still to write
wsrc    EQU at + 5              ; where they come from in pmap, two bytes
wdst    EQU at + 7              ; and where they go in the VRAM, two bytes
last    EQU at + 9              ; frames, the last time the logic counted them
counted EQU at + 10             ; the frames it counted
seed    EQU at + 11             ; random's state, two bytes (chapter 41)
left    EQU at + 13             ; tests: the balls after the first
other   EQU at + 14             ; tests: the second ball, two bytes
balls   EQU ${GAME + 0x40:04X}               ; X, Y, DX, DY of each ball
copy    EQU ${GAME + 0x80:04X}               ; the sprites' attributes, and $D0
ROWS    EQU {ROWS}
PW      EQU {PW}                ; a row of pmap
NB      EQU {NB}                ; the pairs' shapes at a shift, in bytes
"""

# ------------------------------------------------------------------ the parts
# chapter 37's interrupt routine, with a label where it gives the interrupts
# back, for the debugger
ISR = gen37.ISR.replace("""        ei                      ;  5
        ret                     ; 11
""", """isrend: ei                      ;  5
        ret                     ; 11
""")
assert ISR != gen37.ISR


def mark(colour, label, say):
    """R#7 written, the interrupts off for the two bytes (chapter 33)"""
    return f"""        di
        ld a, {NAME[colour].upper().replace(' ', '_')}
        out (VDP_CTRL), a
        ld a, $87
{label}:{' ' * (7 - len(label))}out (VDP_CTRL), a       ; R#7: {say}
        ei
"""


def main_loop(spread):
    return ("""main:   ei
frame:  halt                    ; the interrupt: the frame counted, the tune
""" + mark(DARK_BLUE, "m0", "the sends") + """        call show               ; the scroll: patterns, and R#2 at a new column
        call sprites            ; the balls' attributes
        call status             ; the score and the best
""" + mark(LIGHT_GREEN, "m1", "the logic") + """        call input              ; the keys and the joystick
        ld a, (frames)          ; the frames counted by isr ...
        ld hl, last
        ld b, a
        sub (hl)                ; ... since the logic last counted them
        ld (hl), b
        ld (counted), a
        ld b, a
.steps: push bc
        call move               ; a frame of the game for each
        pop bc
        djnz .steps
        call tests              ; every two balls
        call build              ; the attributes, in the copy
""" + mark(BLACK, "m2", "the window") + """        call nextwin            ; the next window, into the table not shown
""" + mark(WHITE, "m3", "waiting") + """        jp frame
""")


SHOW = """
; show: the pairs' patterns at the scroll's shift, NB bytes after the paper
; (chapter 29); and when the scroll has reached a new column, the table that
; holds it shown with R#2, and the next window to be written
show:   VRAM_WRITE $0000        ; 40
        ld a, (at)              ; 14
        and 7                   ;  8  the shift
        ld l, a                 ;  5
        ld h, 0                 ;  8
        ld de, NB               ; 11
        call mul                ; 18  HL: the shift x NB
        ld de, shifts           ; 11
        add hl, de              ; 12  the patterns at that shift
        ld c, VDP_DATA          ;  8
        ld b, NB                ;  8
        otir                    ; 23 a byte, 18 the last
        ld hl, (at)             ; 17
        ld a, l                 ;  5
        rrca                    ;  5
        rrca                    ;  5
        rrca                    ;  5
        and $1F                 ;  8  at / 8 ...
        bit 0, h                ; 10
        jr z, .col              ; 13, or 8
        or $20                  ;  8  ... with at's ninth bit
.col:   ld hl, col              ; 11
        cp (hl)                 ;  8
        ret z                   ; 12, or 6  the same column
        ld (hl), a              ;  8  a new one
        inc a                   ;  5
        and 63                  ;  8  the next window's column
        ld e, a                 ;  5
        ld d, 0                 ;  8
        ld hl, pmap             ; 11
        add hl, de              ; 12
        ld (wsrc), hl           ; 17  its first pair
        ld a, (table)           ; 14  the table not shown, which has the new one
        ld h, a                 ;  5
        rrca                    ;  5
        rrca                    ;  5  $18 or $1C: 6 or 7
        out (VDP_CTRL), a       ; 12
        ld a, $82               ;  8
        out (VDP_CTRL), a       ; 12  R#2: shown
        ld a, h                 ;  5
        xor $18 ^ $1C           ;  8
        ld (table), a           ; 14  the other table is not shown now
        ld h, a                 ;  5
        ld l, 0                 ;  8
        ld (wdst), hl           ; 17  where the next window goes
        ld a, ROWS              ;  8
        ld (need), a            ; 14  all its rows to write
        ret                     ; 11

; mul: HL = HL x DE, HL below 8. Uses B
mul:    ld b, l                 ;  5
        ld hl, 0                ; 11
        inc b                   ;  5
.add:   dec b                   ;  5
        ret z                   ; 12, or 6
        add hl, de              ; 12
        jr .add                 ; 13
"""

SPRITES = """
; sprites: the balls' attributes from the copy, after the paper. Uses A, BC,
; HL
sprites: VRAM_WRITE SAT         ; 40
        ld hl, copy             ; 11
        ld bc, (4 * NBALLS + 1) << 8 | VDP_DATA ; 11
        otir                    ; 23 a byte, 18 the last
        ret                     ; 11
"""

PUTBCD = """
; putbcd: A = a BCD byte, the VRAM address set -> its two digits sent, as
; the patterns from DIGIT0 (chapter 40's, with an OR). Uses A, C
putbcd: ld c, a                 ;  5
        rrca                    ;  5
        rrca                    ;  5
        rrca                    ;  5
        rrca                    ;  5  the first digit to bits 3 to 0
        and $0F                 ;  8
        or DIGIT0               ;  8  its pattern
        out (VDP_DATA), a       ; 12
        ld a, c                 ;  5
        and $0F                 ;  8  the second digit
        or DIGIT0               ;  8
        out (VDP_DATA), a       ; 12
        ret                     ; 11
"""

UPDATE = """
; update: HL = a number, three BCD bytes, with a copy of the three last sent
; 256 bytes on; DE = the VRAM address of its first digit in the table at
; $1800, bit 6 set -> each byte that differs from its copy sent to both
; tables, and copied (chapter 40). Uses A, BC, DE, HL
update: ld b, 3                 ;  8  three bytes
.byte:  ld a, (hl)              ;  8  a byte of the number
        inc h                   ;  5  the page of the bytes sent
        cp (hl)                 ;  8
        jr z, .same             ; 13, or 8  on the screen already
        ld (hl), a              ;  8  it will be
        call putpair            ; 18  in the table at $1800
        ld a, d                 ;  5
        xor $04                 ;  8
        ld d, a                 ;  5  and in the one at $1C00
        ld a, (hl)              ;  8
        call putpair            ; 18
        ld a, d                 ;  5
        xor $04                 ;  8
        ld d, a                 ;  5
.same:  inc e                   ;  5
        inc e                   ;  5  past its two names
        dec h                   ;  5  back to the number
        inc l                   ;  5  and its next byte
        djnz .byte              ; 14, or 9
        ret                     ; 11

; putpair: A = a BCD byte, DE = the address of its first digit -> sent.
; Uses A, C
putpair: ld c, a                 ;  5
        ld a, e                 ;  5
        out (VDP_CTRL), a       ; 12
        ld a, d                 ;  5
        out (VDP_CTRL), a       ; 12
        ld a, c                 ;  5
        jp putbcd               ; 11
"""

STATUS = """
; status: the score and the best on the status line, the pairs that changed
status: ld hl, score            ; 11
        ld de, SCORE_AT | $4000 ; 11
        call update             ; 18
        ld hl, hi               ; 11
        ld de, HI_AT | $4000    ; 11
        jp update               ; 11
"""

INPUT = """
; input: row 8 of the keyboard and joystick 1, with the interrupts off
; (chapters 34, 35 and 37): LEFT or the stick to the left sends the first
; ball left, RIGHT or the stick to the right sends it right. Uses A, B, C, HL
input:  di                      ;  5
        in a, (PPI_C)           ; 12
        and $F0                 ;  8  the top four bits kept
        or 8                    ;  8
        out (PPI_C), a          ; 12  row 8
        in a, (PPI_B)           ; 12  LEFT is bit 4, RIGHT bit 7
        ld c, a                 ;  5
        xor a                   ;  5  port 1
        call joy                ; 18  left is bit 2, right bit 3
        ei                      ;  5
        ld hl, balls + 2        ; 11  the first ball's DX
        bit 4, c                ; 10
        jr z, .left             ; 13, or 8  LEFT
        bit 2, a                ; 10
        jr nz, .right           ; 13, or 8  nor the stick to the left
.left:  ld (hl), -1             ; 11
        ret                     ; 11
.right: bit 7, c                ; 10
        jr z, .go               ; 13, or 8  RIGHT
        bit 3, a                ; 10
        ret nz                  ; 12, or 6  nor the stick to the right
.go:    ld (hl), 1              ; 11
        ret                     ; 11
"""

MOVE = """
; move: a frame of the game: the scroll a pixel on, the level round, and
; each ball a step, back off the sky's edges. Uses A, B, DE, HL, IX
move:   ld hl, (at)             ; 17
        inc hl                  ;  7
        ld a, h                 ;  5
        and 1                   ;  8  512 pixels, then 0 again
        ld h, a                 ;  5
        ld (at), hl             ; 17
        ld ix, balls            ; 16
        ld de, 4                ; 11
        ld b, NBALLS            ;  8
.ball:  ld a, (ix + 0)          ; 21
        add a, (ix + 2)         ; 21  X + DX
        cp XMAX + 1             ;  8
        jr c, .x                ; 13, or 8  0 to XMAX
        ld a, (ix + 2)          ; 21
        neg                     ; 10
        ld (ix + 2), a          ; 21  the other way
        add a, (ix + 0)         ; 21
.x:     ld (ix + 0), a          ; 21
        ld a, (ix + 1)          ; 21
        add a, (ix + 3)         ; 21  Y + DY
        cp YMIN                 ;  8
        jr c, .back             ; 13, or 8  above the sky's top
        cp YMAX + 1             ;  8
        jr c, .y                ; 13, or 8
.back:  ld a, (ix + 3)          ; 21
        neg                     ; 10
        ld (ix + 3), a          ; 21
        add a, (ix + 1)         ; 21
.y:     ld (ix + 1), a          ; 21
        add ix, de              ; 17
        djnz .ball              ; 14, or 9
        ret                     ; 11
"""

TESTS = """
; tests: every two balls, the first with each after it: boxed, and where
; their boxes meet, touched (chapter 39); two that touch bump. Uses A, BC,
; DE, HL, IX
tests:  ld ix, balls            ; 16  the first of the two
        ld a, NBALLS - 1        ;  8
.first: ld (left), a            ; 14  the balls after it
        push ix                 ; 17
        pop hl                  ; 11
        ld de, 4                ; 11
.second: add hl, de             ; 12  the next ball
        ld (other), hl          ; 17
        ld b, (ix + 0)          ; 21
        ld c, (ix + 1)          ; 21  the first's X and Y
        ld d, (hl)              ;  8
        inc hl                  ;  7
        ld e, (hl)              ;  8  the second's
        call boxed              ; 18
        jr nc, .next            ; 13, or 8  their boxes are apart
        call touched            ; 18
        jr z, .next             ; 13, or 8  the boxes meet, the pixels do not
        ld hl, (other)          ; 17
        call bump               ; 18
.next:  ld hl, (other)          ; 17
        ld de, 4                ; 11
        ld a, (left)            ; 14
        dec a                   ;  5
        ld (left), a            ; 14
        jr nz, .second          ; 13, or 8
        add ix, de              ; 17  the next first
        push ix                 ; 17
        pop hl                  ; 11
        ld a, l                 ;  5
        sub low balls           ;  8
        rrca                    ;  5
        rrca                    ;  5  its number
        sub NBALLS - 1          ;  8
        neg                     ; 10  the balls after it
        jr nz, .first           ; 13, or 8
        ret                     ; 11
"""

BUMP = """
; bump: IX = a ball, HL = another that touches it -> if they come together,
; both go back the way they came, ten points are scored, and an effect
; chosen by random starts. Uses A, BC, DE, HL
bump:   ex de, hl               ;  5  DE: the second ball
        ld c, 0                 ;  8  C: how fast they part
        ld a, (de)              ;  8
        sub (ix + 0)            ; 21  the second's X less the first's
        ld b, a                 ;  5
        inc de                  ;  7
        inc de                  ;  7
        ld a, (de)              ;  8
        sub (ix + 2)            ; 21  its DX less the first's: -2, 0 or 2
        call .part              ; 18
        dec de                  ;  7
        ld a, (de)              ;  8
        sub (ix + 1)            ; 21  the Ys
        ld b, a                 ;  5
        inc de                  ;  7
        inc de                  ;  7
        ld a, (de)              ;  8
        sub (ix + 3)            ; 21  and the DYs
        call .part              ; 18
        bit 7, c                ; 10
        ret z                   ; 12, or 6  0 or more: they part already
        ld a, (de)              ;  8
        neg                     ; 10
        ld (de), a              ;  8  the second's DY
        dec de                  ;  7
        ld a, (de)              ;  8
        neg                     ; 10
        ld (de), a              ;  8  and DX
        ld a, (ix + 2)          ; 21
        neg                     ; 10
        ld (ix + 2), a          ; 21  the first's
        ld a, (ix + 3)          ; 21
        neg                     ; 10
        ld (ix + 3), a          ; 21
        ld a, $10               ;  8  ten points
        call addsc              ; 18
        call best               ; 18
        call random             ; 18
        and 3                   ;  8  one of the four effects
        push ix                 ; 17
        di                      ;  5  sfx and the interrupt share chan_x
        call sfx                ; 18
        ei                      ;  5
        pop ix                  ; 16
        ret                     ; 11
; .part: A = -2, 0 or 2, B = a distance -> C plus B, minus B, or nothing
.part:  or a                    ;  5
        ret z                   ; 12, or 6
        ld a, c                 ;  5
        jp m, .less             ; 11
        add a, b                ;  5
        ld c, a                 ;  5
        ret                     ; 11
.less:  sub b                   ;  5
        ld c, a                 ;  5
        ret                     ; 11
"""

BUILD = """
; build: the balls' X and Y into the copy of the attributes. Uses A, B, DE,
; HL, IX
build:  ld ix, balls            ; 16
        ld hl, copy             ; 11
        ld de, 4                ; 11
        ld b, NBALLS            ;  8
.ball:  ld a, (ix + 1)          ; 21
        ld (hl), a              ;  8  Y
        inc hl                  ;  7
        ld a, (ix + 0)          ; 21
        ld (hl), a              ;  8  X
        inc hl                  ;  7
        inc hl                  ;  7
        inc hl                  ;  7  the pattern and the colour stay
        add ix, de              ; 17
        djnz .ball              ; 14, or 9
        ret                     ; 11
"""

STEP_AT_ONCE = """
; nextwin: the next window, all its rows at once, when show has asked for it
; (pairs.asm's step, chapter 29). Uses A, BC, DE, HL
nextwin: ld a, (need)            ; 14
        or a                    ;  5
        ret z                   ; 12, or 6
        ld b, a                 ;  5  all of them
        xor a                   ;  5
        ld (need), a            ; 14
        jp rows                 ; 11
"""

STEP_SPREAD = """
; nextwin: the next window, CHUNK rows for each frame counted, when show
; has asked for it: all of it in the frames before the scroll reaches its
; column. Uses A, BC, DE, HL
nextwin: ld a, (need)            ; 14
        or a                    ;  5
        ret z                   ; 12, or 6
        ld b, a                 ;  5
        ld a, (counted)         ; 14
        ld c, a                 ;  5
        xor a                   ;  5
.chunk: add a, CHUNK            ;  8  CHUNK rows a frame counted
        dec c                   ;  5
        jr nz, .chunk           ; 13, or 8
        cp b                    ;  5
        jr c, .some             ; 13, or 8
        ld a, b                 ;  5  no more than are left
.some:  ld b, a                 ;  5
        ld a, (need)            ; 14
        sub b                   ;  5
        ld (need), a            ; 14
        jp rows                 ; 11
"""

ROWS_RT = """
; rows: B rows of the next window, from wsrc in pmap to wdst in the table not
; shown, at 46 T-states a name (chapter 29); both moved on for the rows
; after. Uses A, BC, DE, HL
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
.row:   ld b, 32                ;  8
.name:  ld a, (hl)              ;  8
        out (VDP_DATA), a       ; 12
        inc hl                  ;  7
        nop                     ;  5
        djnz .name              ; 14: 46 T-states a name
        ld bc, PW - 32          ; 11
        add hl, bc              ; 12  the next row of pmap
        dec e                   ;  5
        jr nz, .row             ; 13, or 8
        ld (wsrc), hl           ; 17
        ret                     ; 11
"""


def setup():
    lt, ld = 8 * LETTER0, 8 * DIGIT0
    return f"""init:   di
        ld sp, SYS_AREA
        VDP_REG 1, $80          ; display off
        VDP_REG 0, $02          ; Graphic II
        VDP_REG 2, $06          ; names    $1800, and $1C00 with R#2 = 7
        VDP_REG 3, $9F          ; colours  $2000, one set for three thirds
        VDP_REG 4, $00          ; shapes   $0000, one set for three thirds
        VDP_REG 5, $36          ; sprite attributes $1B00
        VDP_REG 6, $07          ; sprite patterns   $3800
        VDP_REG 7, $0F          ; border white
        VRAM_WRITE $0000        ; the pairs at shift 0
        ld hl, shifts
        ld bc, NB << 8 | VDP_DATA
        otir
        VRAM_WRITE $2000        ; their colours, which no shift changes
        ld hl, pcols
        ld b, NB
        otir
        VRAM_WRITE ${lt:04X}        ; the status line's letters
        ld hl, letters
        ld b, {8 * len(LETTERS)}
        otir
        VRAM_WRITE ${ld:04X}        ; and digits
        ld hl, digits
        ld b, 80
        otir
        VRAM_WRITE ${0x2000 + lt:04X}        ; white on black
        ld b, {8 * len(LETTERS)}
.lc:    ld a, ${TEXT_C:02X}
        out (VDP_DATA), a
        djnz .lc
        VRAM_WRITE ${0x2000 + ld:04X}
        ld b, 80
.dc:    ld a, ${TEXT_C:02X}
        out (VDP_DATA), a
        djnz .dc
        VRAM_WRITE ${TABLES[0] + 32 * ROWS:04X}        ; the status line, in both tables
        ld hl, statusn
        ld b, 96
        otir
        VRAM_WRITE ${TABLES[1] + 32 * ROWS:04X}
        ld hl, statusn
        ld b, 96
        otir
        VRAM_WRITE SPAT         ; the ball, sprite patterns 0 to 3
        ld hl, ball
        ld b, 32
        otir
        ld hl, starts           ; the balls
        ld de, balls
        ld bc, 4 * NBALLS
        ldir
        ld hl, atts             ; their attributes
        ld de, copy
        ld bc, 4 * NBALLS + 1
        ldir
        ld hl, nums             ; score and hi
        ld de, score
        ld bc, 6
        ldir
        ld hl, nums             ; as the status line has them
        ld de, shown
        ld bc, 6
        ldir
        ld hl, 0
        ld (at), hl
        xor a
        ld (col), a
        ld (need), a
        ld hl, 1
        ld (seed), hl
        ld hl, pmap             ; window 0 into the table at $1800, shown
        ld (wsrc), hl
        ld hl, $1800
        ld (wdst), hl
        ld b, ROWS
        di
        call rows
        ld hl, pmap + 1         ; window 1 into the one at $1C00
        ld (wsrc), hl
        ld hl, $1C00
        ld (wdst), hl
        ld b, ROWS
        di
        call rows
        di
        ld a, $1C
        ld (table), a           ; not shown
""" + gen37.init_lines() + f"""        ld a, (frames)
        ld (last), a
""" + im2("isr") + """        in a, (VDP_CTRL)        ; no signal left over (chapter 39)
        VDP_REG 1, $E2          ; display on, the frame's signal, sprites 16 x 16
"""


def data(n):
    shp = [b for s in range(8) for b in shapes_at(s)]
    cols = [b for a, b2 in PAIRS for b in gen29.pair_colours(a, b2)]
    pm = [p for row in PMAP for p in (row + row[:31])]
    atts = []
    for k in range(n):
        x, y = START_ALL[k][0], START_ALL[k][1]
        atts += [y, x, 0, COLOURS[k]]
    atts.append(0xD0)
    start = [v & 255 for b in START_ALL[:n] for v in b]
    return ("shifts:                         ; the pairs at shifts 0 to 7, NB bytes each\n" +
            db_rows(shp, 16) + "pcols:                          ; their colours\n" + db_rows(cols, 16) +
            f"pmap:                           ; the pairs: {ROWS} rows of {WIDTH}, and their first 31 again\n" +
            db_rows(pm, 16) +
            f"letters:                        ; the status line's: {LETTERS!r}\n" +
            db_rows([b for ch in LETTERS for b in glyph(ch)]) +
            "digits:                         ; and its digits\n" +
            db_rows([b for ch in "0123456789" for b in glyph(ch)]) +
            "statusn:                        ; rows 21 to 23 of names\n" + db_rows(status_names(), 16) +
            "ball:                           ; chapter 26's ball, 16 x 16\n" + db_rows(big(BALL)) +
            "atts:                           ; the balls' attributes at the start, and the end\n" +
            db_rows(atts) +
            "starts:                         ; X, Y, DX, DY of each ball\n" + db_rows(start) +
            "nums:                           ; score and hi at the start\n" + db_rows([0, 0, 0] + HI0) +
            gen37.start_data() + gen39.shifted_data())


SAY = {
    "budget": """; A game's frame with nobody playing: chapter 29's scroll, eight balls that
; bump, the score, the tune and the effects, the keys and the joystick. R#7
; marks each part: dark blue the sends, light green the logic, black the
; window, white waiting. The next window is written all at once.
""",
    "over": """; WHERE IT BREAKS. budget.asm with a ninth ball.
""",
    "spread": """; over.asm with the next window written CHUNK rows a frame, over the frames
; before the scroll needs it.
""",
}
WHAT = {"budget": "a game's frame, measured", "over": "one ball too many",
        "spread": "the window spread over the frames"}


def program(name, n=None, chunk=None):
    """the program NAME; the workshop's variants change its balls, N, or the
    rows of the window a frame, CHUNK"""
    spread = name == "spread"
    n = n or BALLS[name]
    chunk = chunk or CHUNK
    consts = f"""NBALLS  EQU {n}                   ; the balls
SAT     EQU ${SAT:04X}               ; the sprites' attributes
SPAT    EQU ${SPAT:04X}               ; and patterns
DIGIT0  EQU ${DIGIT0:02X}                 ; the status line's digits: patterns $F0 to $F9
SCORE_AT EQU ${TABLES[0] + SCORE_AT:04X}             ; the score's first digit, in the table at $1800
HI_AT   EQU ${TABLES[0] + HI_AT:04X}               ; and the best's
XMAX    EQU {XMAX}                 ; a ball's X: 0 to XMAX
YMIN    EQU {YMIN}                   ; and its Y: YMIN to YMAX
YMAX    EQU {YMAX}
CHUNK   EQU {chunk}                   ; spread.asm: rows of the next window a frame
"""
    body = setup() + main_loop(spread)
    parts = (SHOW + SPRITES + PUTBCD + UPDATE + STATUS + INPUT + MOVE + TESTS + BUMP + BUILD +
             (STEP_SPREAD if spread else STEP_AT_ONCE) + ROWS_RT +
             gen39.BOXED + gen39.TOUCHED + gen40.ADDSC + gen40.BEST + gen41.RANDOM + gen35.JOY +
             ISR + gen37.PACE + gen37.SEND + gen37.PLAY + gen37.ROW + gen37.VOICE +
             gen37.NEXT + gen37.SOUND + gen37.SFX)
    return (HEAD.format(name=name, chapter=42, what=WHAT[name]) + BIOS + ENGINE_RAM + GAME_RAM +
            consts + gen37.fields() + IM2 + SAY[name] + tidy(body + parts) + data(n) +
            gen37.ENGINE_INC + CART_END)


PROGRAMS = ["budget", "over", "spread"]


def main():
    with open(os.path.join(HERE, "music.inc"), "w") as f:
        f.write(gen37.music_inc())
    for name in PROGRAMS:
        with open(os.path.join(HERE, f"{name}.asm"), "w") as f:
            f.write(program(name))
    print("music.inc " + " ".join(f"{n}.asm" for n in PROGRAMS))


if __name__ == "__main__":
    main()
