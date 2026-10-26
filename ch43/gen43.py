#!/usr/bin/env python3
"""gen43.py - the programs of chapter 43: the first game, GRIN ALLEY.

    python3 gen43.py && ./build.sh

    game.asm    THE GAME. A runner, a black ball with two eyes, crosses four
                alleys where faces go to and fro, to pick up the gems in the
                corridors between them; a face that touches it takes a life.
                Eight gems a round, three lives, a title and GAME OVER. The
                screen is tiles: the walls, the alleys, the gems and the
                text; the runner and the faces are sprites, one face to an
                alley, so that no line of the paper has more than two
                sprites and the VDP's coincidence flag, C, can only mean
                that a face touches the runner. The interrupt keeps the
                status it reads; straight after HALT the frame sends the
                copy of the sprites' attributes, the names the frame before
                queued, and the status line's changes; then the state's work
    stale.asm   WHERE IT BREAKS: game.asm believing C in the first frame
                after the runner goes home, though that C is the frame drawn
                before it went

The pieces come from the chapters before: chapter 26's 16 x 16 sprites and
its ball, chapter 30's characters, chapter 33's frame loop and its count of
frames, chapter 35's keys and joy, chapter 39's cell and walled (a wall is
the brick's name here, not any name but 0), chapter 40's update, best,
addsc and say, chapter 41's random and its table of states, chapter 42's
putbcd. Every line of this chapter's own routines carries its price, the
MSX's T-states, which meas43.py checks with walk.py and the debugger. The
interrupt is taken in mode 2 (chapter 17); build.sh assembles with
--syntax=bFw.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
for ch in ("tools", "ch26", "ch30", "ch35", "ch39", "ch40", "ch41", "ch42"):
    sys.path.insert(0, os.path.join(REPO, ch))
from asmparts import HEAD, CART_END, IM2, im2  # noqa: E402
from gen26 import tidy, db_rows, big, BALL  # noqa: E402  (chapter 26: the ball, 16 x 16)
import shapes30  # noqa: E402  (chapter 30: the characters)
import gen35  # noqa: E402  (chapter 35: keys, joy)
import gen39  # noqa: E402  (chapter 39: cell, walled)
import gen40  # noqa: E402  (chapter 40: update, best, addsc, say)
import gen41  # noqa: E402  (chapter 41: random, the states)
import gen42  # noqa: E402  (chapter 42: putbcd)
sys.path.insert(0, HERE)

EU, JP = "MSXBOOK_EU16", "MSXBOOK_JP16"
MACHINES = [EU, JP]
BIOS = '        INCLUDE "bios.inc"\n'
BLACK, DARK_BLUE, CYAN, WHITE = 1, 4, 7, 15

# ------------------------------------------------------------------ the page of the game
NAME = "GRIN ALLEY"                         # on the title
LANES = [56, 88, 120, 152]                  # each alley's first line: rows 7, 11, 15 and 19
FACES = [(40, 1), (192, -2), (96, 2), (168, -1)]    # each alley's face: X, step a frame
HOME = (120, 23)                            # the runner's X and Y: lines 24 to 39
X_MIN, X_MAX = 8, 232                       # a face turns outside these, inside the walls
STEP = 2                                    # the runner's pixels a frame, each way
GEM_ROWS = [9, 10, 13, 14, 17, 18, 21, 22]  # the corridors' rows, where gems lie
GEMS = 8                                    # gems a round
LIVES = 3
HOLD = 50                                   # frames the game stands still at a touch
WAITS = 150                                 # frames of GAME OVER
POINTS = 0x10                               # a gem's points, two BCD digits
HI_START = [0x00, 0x01, 0x00]               # the best score at the start: 000100
STATES = ["TITLE", "PLAY", "HIT", "OVER"]

# the names of the four tiles; the characters are codes 32 to 127
PAPER, BRICK, ALLEY, GEM = 0, 1, 2, 3
DIGIT0 = 0x30                               # '0': a digit's name is its code
STATUS_ROW = 0
SCORE_AT, LIVES_AT, HI_AT = 7, 20, 26       # columns of row 0: the first digit of each
LABELS = [(1, "SCORE"), (14, "LIVES"), (23, "HI")]
TITLE_TEXT = [(11, 6, NAME), (10, 15, "PRESS SPACE"), (10, 18, "CURSOR KEYS"),
              (9, 19, "OR JOYSTICK 1")]
TITLE_SPRITES = [(56, 43), (184, 43)]       # the title's runner and face: X, Y
OVER_AT = (11, 4)                           # GAME OVER: column, row
OVER_TEXT = "GAME OVER"

# the colours: four greys at least 56 apart in print (chapter 5)
PAPER_C = BLACK << 4 | WHITE                # the paper, and the text
BRICK_C = BLACK << 4 | DARK_BLUE            # chapter 39's brick
ALLEY_C = BLACK << 4 | CYAN                 # an alley: cyan, no ink
GEM_C = DARK_BLUE << 4 | WHITE              # a gem
RUNNER_C, FACE_C = BLACK, DARK_BLUE         # the sprites
BORDER = BLACK

BRICK_SHAPE = gen39.BRICK
GEM_SHAPE = [0x18, 0x3C, 0x7E, 0xFF, 0x7E, 0x3C, 0x18, 0x00]
FONT = shapes30.wide()                      # codes 32 to 127, 8 bytes each

# the arena, rows 1 to 23: the name in columns 1 to 30, walls either side
MIDDLE = {1: BRICK, 23: BRICK}
for _y in LANES:
    MIDDLE[_y // 8] = MIDDLE[_y // 8 + 1] = ALLEY
ARENA = [MIDDLE.get(r, PAPER) for r in range(1, 24)]


def arena_names():
    """the 768 names of the play with no gems: the status line's labels on
    row 0 (its digits come with the first sends), the walls, the alleys"""
    out = [32] * 32
    for col, text in LABELS:
        out[col:col + len(text)] = [ord(c) for c in text]
    for mid in ARENA:
        out += [BRICK] + [mid] * 30 + [BRICK]
    return out


assert all(y % 8 == 0 for y in LANES) and all(b - a == 32 for a, b in zip(LANES, LANES[1:]))
assert all(ARENA[r - 1] == PAPER for r in GEM_ROWS)
assert all(X_MIN <= x <= X_MAX for x, _ in FACES)


# ------------------------------------------------------------------ the sprites
def rows16(*lines):
    return [int(l.replace(".", "0").replace("#", "1"), 2) for l in lines]


def ball_less(holes, dots=()):
    """chapter 26's ball with HOLES, (row, columns), cut out, and DOTS put
    back inside them"""
    rows = list(BALL)
    for r, cols in holes:
        for c in cols:
            rows[r] &= ~(0x8000 >> c)
    for r, cols in dots:
        for c in cols:
            rows[r] |= 0x8000 >> c
    return rows


# the runner: the ball, two eyes cut out of it, looking right
RUNNER = ball_less([(r, (4, 5, 6, 9, 10, 11)) for r in (4, 5, 6, 7)],
                   [(r, (6, 11)) for r in (5, 6)])
# a face: the ball, two eyes and a smile cut out of it
FACE = ball_less([(r, (4, 5, 10, 11)) for r in (4, 5)] +
                 [(9, (3, 12)), (10, (4, 11)), (11, range(5, 11))])
assert all(r & ~b == 0 for r, b in zip(RUNNER, BALL)) and all(f & ~b == 0 for f, b in zip(FACE, BALL))
SPRITE_PATTERNS = big(RUNNER) + big(FACE)   # patterns 0 to 3 the runner, 4 to 7 a face
RUNNER_P, FACE_P = 0, 4


def first_copy():
    """the copy of the sprites' attributes when a game begins: the runner at
    home, each face in its alley, and the end"""
    out = [HOME[1], HOME[0], RUNNER_P, RUNNER_C]
    for (x, _), y in zip(FACES, LANES):
        out += [y - 1, x, FACE_P, FACE_C]
    return out + [0xD0]


def title_copy():
    out = []
    for (x, y), (p, c) in zip(TITLE_SPRITES, ((RUNNER_P, RUNNER_C), (FACE_P, FACE_C))):
        out += [y, x, p, c]
    return out + [0xD0]


assert len(first_copy()) == 21


# ------------------------------------------------------------------ the RAM
VARS_AT = 0xC100
RAM = f"""stat    EQU VARS                ; the status isr read: F, 5S, C, a sprite's number
ticks   EQU VARS + 1            ; frames counted by isr, two bytes
seed    EQU VARS + 3            ; random's state, two bytes (chapter 41)
state   EQU VARS + 5            ; TITLE, PLAY, HIT or OVER
left    EQU VARS + 6            ; the frames left of HIT or of OVER
lives   EQU VARS + 7
gems    EQU VARS + 8            ; the gems of the round still lying
last    EQU VARS + 9            ; ticks' low byte, when the play last counted
held    EQU VARS + 10           ; the keys and the stick: a 0 for each held
stale   EQU VARS + 11           ; frames whose C play1 does not believe
shownl  EQU VARS + 12           ; the lives on the status line
queued  EQU VARS + 13           ; the names queued for the sends
queue   EQU VARS + $10          ; 16 names: the VRAM address, then the name
copy    EQU VARS + $40          ; the sprites' attributes: Y, X, pattern, colour
runner  EQU copy                ; the runner's Y and X
faces   EQU copy + 4            ; and the faces', four each
steps   EQU VARS + $60          ; each face's step, -2 to 2
names   EQU $C400               ; the copy of the 768 names
score   EQU $C700               ; three BCD bytes (chapter 40)
hi      EQU score + 3           ; the best, three more
shown   EQU score + $100        ; the six bytes last sent, a page on
"""
QUEUE_MAX = 16

CONSTS = f"""SAT     EQU $1B00               ; the sprites' attributes
SPAT    EQU $3800               ; and their patterns
TITLE   EQU 0                   ; the states
PLAY    EQU 1
HIT     EQU 2
OVER    EQU 3
PAPER   EQU {PAPER}                   ; the tiles' names
BRICK   EQU {BRICK}
ALLEY   EQU {ALLEY}
GEM     EQU {GEM}
DIGIT0  EQU ${DIGIT0:02X}                 ; '0'
X_MIN   EQU {X_MIN}                   ; a face's X: X_MIN to X_MAX
X_MAX   EQU {X_MAX}
HOME_X  EQU {HOME[0]}                 ; the runner's home
HOME_Y  EQU {HOME[1]}
GEMS    EQU {GEMS}                   ; gems a round
LIVES   EQU {LIVES}
HOLD    EQU {HOLD}                  ; frames held still at a touch
WAITS   EQU {WAITS}                 ; frames of GAME OVER
POINTS  EQU ${POINTS:02X}                 ; a gem's, two BCD digits
SCORE_AT EQU $1800 + {SCORE_AT}           ; row 0: the score's first digit
LIVES_AT EQU $1800 + {LIVES_AT}           ; the lives
HI_AT   EQU $1800 + {HI_AT}             ; and the best's first digit
"""

# ------------------------------------------------------------------ the frame
ISR = """
; isr: every frame. The status kept in stat, the signal let down; the frame
; counted. Keeps AF, HL
isr:    push af                 ; 12
        in a, (VDP_CTRL)        ; 12  the status: F, 5S, C, a sprite's number
        ld (stat), a            ; 14
        push hl                 ; 12
        ld hl, (ticks)          ; 17
        inc hl                  ;  7
        ld (ticks), hl          ; 17
        pop hl                  ; 11
        pop af                  ; 11
isrend: ei                      ;  5
        ret                     ; 11
"""

MAIN = """main:   ei
frame:  halt                    ; isr: the status kept, the frame counted
woke:   call sends              ; 18  sprites, names queued, the status line
sent:   call run                ; 18  the state's work
ran:    jr frame                ; 13

; run: this frame's routine for the state held in state.
; go: A = a state -> it is the state, and its start routine has run.
;     Both use every register that routine uses (chapter 41)
run:    ld a, (state)           ; 14
        ld hl, frames           ; 11
        jr table                ; 13
go:     ld (state), a           ; 14
        ld hl, starts           ; 11
table:  add a, a                ;  5  two bytes a state
        add a, l                ;  5
        ld l, a                 ;  5  the tables do not cross a page
        ld a, (hl)              ;  8
        inc l                   ;  5
        ld h, (hl)              ;  8
        ld l, a                 ;  5
        jp (hl)                 ;  5  and its RET goes back to the caller
"""

SENDS = """
; sends: straight after HALT, before the paper: the copy of the sprites'
; attributes, the names the frame before queued, and the status line's
; digits that changed. Uses A, BC, DE, HL
sends:  VRAM_WRITE SAT          ; 40
        ld hl, copy             ; 11
        ld bc, 21 << 8 | VDP_DATA ; 11  five sprites and the end
        otir                    ; 23 a byte, 18 the last
        ld hl, queued           ; 11
        ld a, (hl)              ;  8
        or a                    ;  5
        jr z, status            ; 13, or 8  none queued
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
; status: the score, the best and the lives, what changed (chapter 40)
status: ld hl, score            ; 11
        ld de, SCORE_AT | $4000 ; 11
        call update             ; 18
        ld hl, hi               ; 11
        ld de, HI_AT | $4000    ; 11
        call update             ; 18
        ld a, (lives)           ; 14
        ld hl, shownl           ; 11
        cp (hl)                 ;  8
        ret z                   ; 12, or 6  shown already
        ld (hl), a              ;  8
        ld c, a                 ;  5
        ld a, low LIVES_AT      ;  8
        out (VDP_CTRL), a       ; 12
        ld a, high LIVES_AT | $40 ;  8
        out (VDP_CTRL), a       ; 12
        ld a, c                 ;  5
        or DIGIT0               ;  8  its digit
        out (VDP_DATA), a       ; 12
        ret                     ; 11
"""

INPUT = """
; input: the cursor keys and joystick 1 together, with the interrupts off
; (chapters 34 and 35) -> held, in register 14's way: bits 0 to 3 up, down,
; left, right, bit 4 SPACE or button A, a 0 for each held. Uses A, BC, HL
input:  di                      ;  5
        call keys               ; 18  row 8 in register 14's way
        ld c, a                 ;  5
        xor a                   ;  5  port 1
        call joy                ; 18  its register 14
        ei                      ;  5
        and c                   ;  5  held on either
        ld (held), a            ; 14
        ret                     ; 11
"""

WALK = """
; walk: held -> the runner two pixels along X for LEFT or RIGHT, then two
; along Y for UP or DOWN, each where walled finds no wall (chapter 39), so
; that it slides along a wall it meets at a slant. Uses A, BC, DE, HL
walk:   ld bc, (runner)         ; 22  C = Y, B = X
        ld a, (held)            ; 14
        bit 2, a                ; 10  LEFT
        jr nz, .right           ; 13, or 8
        dec b                   ;  5
        dec b                   ;  5  two to the left
.right: bit 3, a                ; 10  RIGHT
        jr nz, .x               ; 13, or 8
        inc b                   ;  5
        inc b                   ;  5  two to the right
.x:     push bc                 ; 12
        call walled             ; 18  NZ: a wall there
        pop bc                  ; 11
        jr nz, .y               ; 13, or 8
        ld a, b                 ;  5
        ld (runner + 1), a      ; 14  the new X
.y:     ld bc, (runner)         ; 22  X as it is now, and Y
        ld a, (held)            ; 14
        bit 0, a                ; 10  UP
        jr nz, .down            ; 13, or 8
        dec c                   ;  5
        dec c                   ;  5  two up
.down:  bit 1, a                ; 10  DOWN
        jr nz, .w               ; 13, or 8
        inc c                   ;  5
        inc c                   ;  5  two down
.w:     push bc                 ; 12
        call walled             ; 18
        pop bc                  ; 11
        ret nz                  ; 12, or 6  a wall
        ld a, c                 ;  5
        ld (runner), a          ; 14  the new Y
        ret                     ; 11
"""

# chapter 39's walled, with the brick's name for a wall: here the paper is
# not the only name that is not one
WALLED = gen39.WALLED.replace(
    """; 26). A name that is not 0 is a wall. Uses A, BC, DE, HL""",
    """; 26). A wall is the brick's name. Uses A, BC, DE, HL""").replace(
    """.cell:  ld a, (hl)              ;  8
        or a                    ;  5  0: the paper
        jr nz, .wall            ; 13, or 8""",
    """.cell:  ld a, (hl)              ;  8
        cp BRICK                ;  8  the walls' name
        jr z, .wall             ; 13, or 8""").replace(
    """.wall:  pop hl                  ; 11
        ret                     ; 11  NZ: a wall""",
    """.wall:  pop hl                  ; 11
        or a                    ;  5  A is BRICK
        ret                     ; 11  NZ: a wall""")
assert WALLED.count("cp BRICK") == 1 and WALLED.count("or a                    ;  5  A is BRICK") == 1

PATROL = """
; patrol: IX = a face's attributes in the copy, HL = its step -> X a step
; on; a step that would take it outside X_MIN to X_MAX, the walls' inside,
; turns it, and it steps the other way instead. Uses A
patrol: ld a, (ix + 1)          ; 21  X
        add a, (hl)             ;  8  and its step
        sub X_MIN               ;  8
        cp X_MAX - X_MIN + 1    ;  8  carry from X_MIN to X_MAX
        jr c, .x                ; 13, or 8
        ld a, (hl)              ;  8
        neg                     ; 10
        ld (hl), a              ;  8  the other way
        add a, (ix + 1)         ; 21
        sub X_MIN               ;  8
.x:     add a, X_MIN            ;  8
        ld (ix + 1), a          ; 21
        ret                     ; 11
"""

STEP_RT = """
; step: a frame of the play: the runner, then each face. Uses A, BC, DE,
; HL, IX
step:   call walk               ; 18
        ld ix, faces            ; 16
        ld hl, steps            ; 11
        ld de, 4                ; 11
        ld b, 4                 ;  8  four faces
.face:  call patrol             ; 18
        add ix, de              ; 17  the next face's attributes
        inc l                   ;  5  and its step
        djnz .face              ; 14, or 9
        ret                     ; 11
"""

PICK = """
; pick: the cells under the runner's 16 x 16 pixels, as walled finds them ->
; each with a gem taken by took. Uses A, BC, DE, HL
pick:   ld bc, (runner)         ; 22  C = Y, B = X
        inc c                   ;  5  the first line
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
        cp GEM                  ;  8
        call z, took            ; 18, or 11  a gem
        inc hl                  ;  7
        djnz .cell              ; 14, or 9
        pop hl                  ; 11
        ld bc, 32               ; 11
        add hl, bc              ; 12  the row of cells below
        dec e                   ;  5
        jr nz, .rows            ; 13, or 8
        ret                     ; 11

; took: HL = a gem's cell in the copy of the names -> the cell paper again,
; queued; ten points; a gem fewer. Keeps BC, DE, HL. Uses A
took:   push bc                 ; 12
        push de                 ; 12
        push hl                 ; 12
        xor a                   ;  5  PAPER
        call post               ; 18
        ld a, POINTS            ;  8
        call addsc              ; 18
        ld hl, gems             ; 11
        dec (hl)                ; 12  a gem fewer
        pop hl                  ; 11
        pop de                  ; 11
        pop bc                  ; 11
        ret                     ; 11

; post: HL = a cell of the copy of the names, A = a name -> the name written
; there and queued for the next frame's sends. Uses A, BC, DE, HL
post:   ld (hl), a              ;  8
        ld c, a                 ;  5  the name
        ld de, ($1800 + $4000 - names) & $FFFF ; 11
        add hl, de              ; 12  its VRAM address, plus $4000 for writing
        ex de, hl               ;  5  in DE
        ld hl, queued           ; 11
        ld a, (hl)              ;  8
        inc (hl)                ; 12  one more
        ld b, a                 ;  5
        add a, a                ;  5
        add a, b                ;  5  three bytes each
        add a, low queue        ;  8
        ld l, a                 ;  5  the queue in queued's page
        ld (hl), e              ;  8
        inc l                   ;  5
        ld (hl), d              ;  8
        inc l                   ;  5
        ld (hl), c              ;  8
        ret                     ; 11
"""

SOW = """
; sow: a gem in a free cell of a corridor: one of its eight rows and a
; column from 1 to 30, chosen by random, again while the cell is a wall, is
; not paper, or lies under the runner or where a step takes it: its 3 x 3
; cells and one more all round. Uses A, BC, DE, HL
sow:    call random             ; 18
        and 7                   ;  8  one of the eight rows
        ld e, a                 ;  5
        ld d, 0                 ;  8
        ld hl, rows             ; 11
        add hl, de              ; 12
        ld c, (hl)              ;  8  C: the row
        call random             ; 18
        and 31                  ;  8  the column
        jr z, sow               ; 13, or 8  0, the left wall: again
        cp 31                   ;  8
        jr z, sow               ; 13, or 8  31, the right wall
        ld b, a                 ;  5  B: the column
        ld a, (runner)          ; 14  the runner's Y
        inc a                   ;  5  its first line
        rrca                    ;  5
        rrca                    ;  5
        rrca                    ;  5
        and 31                  ;  8  its first row
        ld e, a                 ;  5
        ld a, c                 ;  5
        sub e                   ;  5
        inc a                   ;  5  from the row above its first
        cp 5                    ;  8  carry: one of those five rows
        jr nc, .free            ; 13, or 8
        ld a, (runner + 1)      ; 14  its X
        rrca                    ;  5
        rrca                    ;  5
        rrca                    ;  5
        and 31                  ;  8  its first column
        ld e, a                 ;  5
        ld a, b                 ;  5
        sub e                   ;  5
        inc a                   ;  5
        cp 5                    ;  8
        jr c, sow               ; 13, or 8  near the runner: again
.free:  ld l, c                 ;  5
        ld h, 0                 ;  8
        add hl, hl              ; 12
        add hl, hl              ; 12
        add hl, hl              ; 12
        add hl, hl              ; 12
        add hl, hl              ; 12  the row x 32
        ld a, l                 ;  5
        or b                    ;  5  and the column
        ld l, a                 ;  5
        ld de, names            ; 11
        add hl, de              ; 12  HL: the cell in the copy
        ld a, (hl)              ;  8
        cp PAPER                ;  8
        jr nz, sow              ; 13, or 8  a gem there already: again
        ld a, GEM               ;  8
        jp post                 ; 11  the gem, queued

; round: GEMS gems sown, and as many to take. Uses A, BC, DE, HL
round:  ld b, GEMS              ;  8
.gem:   push bc                 ; 12
        call sow                ; 18
        pop bc                  ; 11
        djnz .gem               ; 14, or 9
        ld a, GEMS              ;  8
        ld (gems), a            ; 14
        ret                     ; 11
"""


def play1(stale_bug):
    """play0, play1, hit0 and hit1; hit1 in game.asm leaves C not believed in
    the first frame of the play, and in stale.asm (STALE_BUG) believes it"""
    stale_lines = "" if stale_bug else """        ld a, 1                 ;  8
        ld (stale), a           ; 14  its C is the frame before it went
"""
    return """
; play0: no frame counted yet
play0:  ld a, (ticks)           ; 14
        ld (last), a            ; 14
        ret                     ; 11

; play1: THE FRAME OF THE PLAY. The keys; eight gems more when the last is
; gone; a step of the runner and of every face for each frame counted
; (chapter 33); the gems under the runner; the best score; and a touch: C,
; which isr kept from the frame just drawn, where only the runner can meet a
; face. Uses every register but IY
play1:  call input              ; 18  held, first, while the frame is young
        ld a, (gems)            ; 14
        or a                    ;  5
        call z, round           ; 18, or 11  the last gem gone: eight more
        ld hl, last             ; 11
        ld a, (ticks)           ; 14
        ld b, a                 ;  5
        sub (hl)                ;  8  the frames gone by
        ld (hl), b              ;  8  and ticks, for the next time
        ld b, a                 ;  5
.step:  push bc                 ; 12
        call step               ; 18  the runner and the faces
        pop bc                  ; 11
        djnz .step              ; 14, or 9
        call pick               ; 18  its gems
        call best               ; 18  hi kept the best
        ld hl, stale            ; 11
        ld a, (hl)              ;  8
        or a                    ;  5
        jr z, .look             ; 13, or 8
        dec (hl)                ; 12  a frame whose C is not believed
        ret                     ; 11
.look:  ld a, (stat)            ; 14
        and $20                 ;  8  C
        ret z                   ; 12, or 6  no sprites met
touch:  ld a, HIT               ;  8
        jp go                   ; 11  a face touched the runner

; hit0: a life fewer, and the game held still
hit0:   ld hl, lives            ; 11
        dec (hl)                ; 12  the status line shows it next frame
        ld a, HOLD              ;  8
        ld (left), a            ; 14
        ret                     ; 11

; hit1: at the end of the wait, GAME OVER, or the runner home again
hit1:   ld hl, left             ; 11
        dec (hl)                ; 12
        ret nz                  ; 12, or 6
        ld a, (lives)           ; 14
        or a                    ;  5
        ld a, OVER              ;  8
        jp z, go                ; 11  no lives left
        ld hl, HOME_X << 8 | HOME_Y ; 11
        ld (runner), hl         ; 17  home again, Y and X
""" + stale_lines + """home:   ld a, PLAY              ;  8
        jp go                   ; 11
"""


STATES_RT = """
; title0: the title on a clear screen, with the runner and a face
title0: call wipe
        ld hl, ttext            ; the title's lines, each its address and text
        ld b, {nlines}
.line:  push bc
        ld e, (hl)
        inc hl
        ld d, (hl)
        inc hl
        di
        call say                ; HL to the line's 0
        ei
        inc hl
        pop bc
        djnz .line
        ld hl, tcopy            ; the two sprites
        ld de, copy
        ld bc, 9
        ldir
        ret

; title1: SPACE or button A held? The seed is the frame count, 1 for 0
; (chapter 41), and a game begins
title1: call input              ; held
        and $10                 ; SPACE, button A
        ret nz
        ld hl, (ticks)          ; the seed
        ld a, h
        or l
        jr nz, .seed
        inc hl
.seed:  ld (seed), hl
pressed: call setup             ; the arena, the status line, the sprites
        call round              ; the first round's gems
        ld a, PLAY
        jp go

; over0: GAME OVER, and WAITS frames of it
over0:  ld hl, otext
        ld de, $1800 + 32 * {orow} + {ocol} | $4000
        di
        call say
        ei
        ld a, WAITS
        ld (left), a
        ret

; over1: at the end of the wait, the title again
over1:  ld hl, left
        dec (hl)
        ret nz
again:  ld a, TITLE
        jp go

; setup: a new game. The arena into the copy of the names and to the VDP;
; score 0, none of its digits shown; three lives; the sprites at their
; first places, the faces' steps; no names queued
setup:  call arena
        ld hl, score
        ld b, 3
.zero:  ld (hl), 0
        inc l
        djnz .zero
        ld hl, shown
        ld b, 6
.none:  ld (hl), $FF            ; none of its digits shown: the sends send all
        inc l
        djnz .none
        ld a, LIVES
        ld (lives), a
        ld a, $FF
        ld (shownl), a
        ld hl, first            ; the sprites' first places
        ld de, copy
        ld bc, 21
        ldir
        ld hl, fsteps           ; and the faces' steps
        ld de, steps
        ld bc, 4
        ldir
        xor a
        ld (queued), a
        ld (stale), a
        ret

; arena: the names of the play, from the table arena's rows, into the copy
; of the names and to the VDP at once, 41 T-states a name in its rows: row
; 0 the status line's labels, rows 1 to 23 a wall, 30 names, a wall
arena:  di                      ;  5
        VRAM_WRITE $1800        ; 40
        ei                      ;  5
        ld hl, row0             ; 11  row 0
        ld de, names            ; 11
        ld b, 32                ;  8
.top:   ld a, (hl)              ;  8
        ld (de), a              ;  8
        out (VDP_DATA), a       ; 12
        inc hl                  ;  7
        inc de                  ;  7
        djnz .top               ; 14, or 9
        ex de, hl               ;  5  HL: the copy's row 1
        ld de, arows            ; 11  DE: the table
        ld c, 23                ;  8  rows 1 to 23
.row:   ld a, (de)              ;  8  the row's middle name
        inc de                  ;  7
        push af                 ; 12
        ld a, BRICK             ;  8
        ld (hl), a              ;  8
        inc hl                  ;  7
        out (VDP_DATA), a       ; 12  the wall on the left
        pop af                  ; 11
        ld b, 30                ;  8
.mid:   ld (hl), a              ;  8
        inc hl                  ;  7
        out (VDP_DATA), a       ; 12
        djnz .mid               ; 14, or 9: 41 T-states a name
        ld a, BRICK             ;  8
        ld (hl), a              ;  8
        inc hl                  ;  7
        out (VDP_DATA), a       ; 12  and on the right
        dec c                   ;  5
        jr nz, .row             ; 13, or 8
        ret                     ; 11

; wipe: the 768 names spaces (chapter 41). Uses A, BC
wipe:   di
        VRAM_WRITE $1800
        ei
        ld bc, 768
.sp:    ld a, 32
        out (VDP_DATA), a
        dec bc
        ld a, b
        or c
        jr nz, .sp
        ret
"""


def setup_lines():
    """the cartridge's start: the VDP, the tiles, the characters, the
    sprites' patterns, the best score, mode 2, the title"""
    return f"""init:   di
        ld sp, SYS_AREA
        VDP_REG 1, $80          ; display off
        VDP_REG 0, $02          ; Graphic II
        VDP_REG 2, $06          ; names    $1800
        VDP_REG 3, $9F          ; colours  $2000, one set for three thirds
        VDP_REG 4, $00          ; shapes   $0000, one set for three thirds
        VDP_REG 5, $36          ; sprite attributes $1B00
        VDP_REG 6, $07          ; sprite patterns   $3800
        VDP_REG 7, ${BORDER:02X}          ; border black
        VRAM_WRITE SAT          ; no sprites yet
        ld a, $D0
        out (VDP_DATA), a
        ld hl, VARS             ; the variables' page, all 0: ticks,
        ld de, VARS + 1         ; the lives, the queue, stale and the rest
        ld bc, 255
        ld (hl), 0
        ldir
        VRAM_WRITE $0000        ; the four tiles' shapes
        ld hl, tiles
        ld bc, 32 << 8 | VDP_DATA
        otir
        VRAM_WRITE $0100        ; chapter 30's characters, codes 32 to 127
        ld hl, font
        ld b, 3                 ; three runs of 256 bytes
.font:  push bc
        ld b, 0
        otir
        pop bc
        djnz .font
        VRAM_WRITE $2000        ; the tiles' colours
        ld hl, tcols
        ld b, 32
        otir
        VRAM_WRITE $2100        ; the characters', black on white
        ld bc, 768
.fc:    ld a, ${PAPER_C:02X}
        out (VDP_DATA), a
        dec bc
        ld a, b
        or c
        jr nz, .fc
        VRAM_WRITE SPAT         ; the runner, patterns 0 to 3, and a face, 4 to 7
        ld hl, sprites
        ld bc, 64 << 8 | VDP_DATA
        otir
        ld hl, nums             ; score 000000 and the best at the start,
        ld de, score
        ld bc, 6
        ldir
        ld hl, nums             ; as if on the screen: the title shows neither
        ld de, shown
        ld bc, 6
        ldir
""" + im2("isr") + """        ld a, TITLE
        call go                 ; the first state: title0 ends with EI
        di
        in a, (VDP_CTRL)        ; no signal left over (chapter 39)
        VDP_REG 1, $E2          ; display on, the frame's signal, sprites 16 x 16
"""


def ttext_lines():
    out = []
    for col, row, text in TITLE_TEXT:
        out.append(f"        dw $1800 + 32 * {row} + {col} | $4000\n        db \"{text}\", 0\n")
    return "".join(out)


def data():
    tiles = [0] * 8 + list(BRICK_SHAPE) + [0] * 8 + list(GEM_SHAPE)
    tcols = [PAPER_C] * 8 + [BRICK_C] * 8 + [ALLEY_C] * 8 + [GEM_C] * 8
    row0 = arena_names()[:32]
    return ("""        ALIGN 16
starts: dw title0, play0, hit0, over0 ; each state's first frame
frames: dw title1, play1, hit1, over1 ; and every frame of it
""" + "tiles:                          ; paper, brick (chapter 39), alley, gem\n" + db_rows(tiles) +
            "tcols:                          ; their colours\n" + db_rows(tcols) +
            "row0:                           ; the status line's labels\n" + db_rows(row0, 16) +
            "arows:                          ; rows 1 to 23: the name between the walls\n" +
            db_rows(ARENA, 23) +
            "rows:                           ; the corridors' rows, where sow puts gems\n" +
            db_rows(GEM_ROWS) +
            "first:                          ; the sprites' attributes when a game begins\n" +
            db_rows(first_copy(), 4) +
            "fsteps:                         ; the faces' steps\n" +
            db_rows([s & 255 for _, s in FACES]) +
            "tcopy:                          ; the title's runner and face, and the end\n" +
            db_rows(title_copy()) +
            "nums:                           ; score and the best score at the start\n" +
            db_rows([0, 0, 0] + HI_START) +
            f"ttext:                          ; the title's lines, each its address and text\n" +
            ttext_lines() +
            f"otext:  db \"{OVER_TEXT}\", 0\n" +
            "sprites:                        ; the runner and a face, 16 x 16 (chapter 26)\n" +
            db_rows(SPRITE_PATTERNS) +
            "font:                           ; chapter 30's characters, codes 32 to 127\n" +
            db_rows(FONT))


SAY = {
    "game": """; GRIN ALLEY: a runner crosses four alleys of faces to pick up gems. The
; screen is tiles, the runner and the faces are sprites, one face to an
; alley, so that C, the VDP's coincidence, can only be a face meeting the
; runner. Four states: TITLE, PLAY, HIT and OVER.
""",
    "stale": """; WHERE IT BREAKS. game.asm believing C in the first frame of the play
; after the runner is put home again.
""",
}
WHAT = {"game": "GRIN ALLEY", "stale": "a touch believed twice"}


def program(name, holds=HOLD, steps_of=None, keys_late=False, peek=False):
    """the program NAME; the workshop's variants change the frames held at a
    touch, HOLDS, the faces' steps, STEPS_OF; read the keys after round,
    KEYS_LATE; or read C from the port in play1, PEEK"""
    parts = (ISR + SENDS + gen40.UPDATE + gen42.PUTBCD + INPUT + gen35.KEYS + gen35.JOY + WALK +
             gen39.CELL + WALLED + PATROL + STEP_RT + PICK + SOW + play1(name == "stale") +
             STATES_RT.format(nlines=len(TITLE_TEXT), orow=OVER_AT[1], ocol=OVER_AT[0]) +
             gen40.BEST + gen40.ADDSC + gen40.SAY + gen41.RANDOM)
    body = setup_lines() + MAIN
    src = (HEAD.format(name=name, chapter=43, what=WHAT[name]) + BIOS + RAM + CONSTS + IM2 + SAY[name] +
           tidy(body + parts) + data() + "        ALIGN 16\nkbdjoy:                         ; "
           "register 14's bits 0-3 for the cursor keys (chapter 35)\n" + db_rows(gen35.kbd_table(), 16) +
           CART_END)
    if keys_late:
        old = """play1:  call input              ; 18  held, first, while the frame is young
        ld a, (gems)            ; 14
        or a                    ;  5
        call z, round           ; 18, or 11  the last gem gone: eight more
"""
        assert src.count(tidy(old)) == 1
        src = src.replace(tidy(old), tidy("""play1:  ld a, (gems)            ; 14
        or a                    ;  5
        call z, round           ; 18, or 11  the last gem gone: eight more
        call input              ; 18  held
"""))
    if peek:
        old = tidy(""".look:  ld a, (stat)            ; 14
""")
        assert src.count(old) == 1
        src = src.replace(old, tidy(""".look:  in a, (VDP_CTRL)        ; 12  the status, read here
"""))
    if holds != HOLD:
        src = src.replace(f"HOLD    EQU {HOLD}", f"HOLD    EQU {holds}")
    if steps_of:
        src = src.replace("fsteps:                         ; the faces' steps\n" +
                          db_rows([s & 255 for _, s in FACES]),
                          "fsteps:                         ; the faces' steps\n" +
                          db_rows([s & 255 for s in steps_of]))
    return src


PROGRAMS = ["game", "stale"]


def main():
    for name in PROGRAMS:
        with open(os.path.join(HERE, f"{name}.asm"), "w") as f:
            f.write(program(name))
    print(" ".join(f"{n}.asm" for n in PROGRAMS))


if __name__ == "__main__":
    main()
