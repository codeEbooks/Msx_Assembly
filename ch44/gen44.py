#!/usr/bin/env python3
"""gen44.py - the programs of chapter 44: GRIN ALLEY finished.

    python3 gen44.py && ./build.sh

    game.asm    THE GAME, FINISHED. Chapter 43's GRIN ALLEY with what its
                page left out. Chapter 37's tune plays from the interrupt in
                every state, and five sounds of the game's own go over its
                channel C. The score is worth chasing: a gem is worth ten
                points more each round, up to fifty; a bonus that drops while
                the round lasts is added when it ends; a life more, once a
                game, at 1,000 points. The faces go a pixel a frame faster
                each round, up to four. The game moves by steps 262 lines
                apart, the 60 Hz machine's frame, so that it runs as fast on
                the 50 Hz machine, where a loop takes one step or two. A
                title of big letters in bricks, the best score kept from game
                to game, all in a cartridge of 16 KB
    extra.asm   WHERE IT BREAKS: game.asm whose award forgets that a life
                is won once a game

The pieces are chapter 43's game (gen43.py) and chapter 37's sound engine
(gen37.py), whose tune is chapter 37's music37.py. The four tiles are
numbered again so that any name from the brick's up is a wall: the bricks,
and the letters of the bottom line. Every line of this chapter's own routines
carries its price, the MSX's T-states, which meas44.py checks with walk.py
and the debugger. The interrupt is taken in mode 2 (chapter 17); build.sh
assembles with --syntax=bFw.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
for ch in ("tools", "ch26", "ch30", "ch33", "ch35", "ch37", "ch39", "ch40", "ch41", "ch42", "ch43"):
    sys.path.insert(0, os.path.join(REPO, ch))
from asmparts import HEAD, CART_END, IM2, im2  # noqa: E402
from gen26 import tidy, db_rows  # noqa: E402  (chapter 26)
import gen35  # noqa: E402  (chapter 35: keys, joy)
import gen37  # noqa: E402  (chapter 37: the sound engine)
import gen39  # noqa: E402  (chapter 39: cell, walled)
import gen40  # noqa: E402  (chapter 40: update, best, addsc, say)
import gen41  # noqa: E402  (chapter 41: random)
import gen42  # noqa: E402  (chapter 42: putbcd)
import gen43  # noqa: E402  (chapter 43: the game)
import music37  # noqa: E402  (chapter 37: the tune)
sys.path.insert(0, HERE)

EU, JP = gen43.EU, gen43.JP
MACHINES = [EU, JP]
BIOS = gen43.BIOS
BLACK, DARK_BLUE, CYAN, WHITE = gen43.BLACK, gen43.DARK_BLUE, gen43.CYAN, gen43.WHITE

# ------------------------------------------------------------------ the page of the game
NAME = gen43.NAME
LANES, FACES, HOME = gen43.LANES, gen43.FACES, gen43.HOME
X_MIN, X_MAX, STEP = gen43.X_MIN, gen43.X_MAX, gen43.STEP
GEM_ROWS, GEMS, LIVES = gen43.GEM_ROWS, gen43.GEMS, gen43.LIVES
STILL = 50                  # steps the game stands still at a touch (chapter 43's HOLD)
ENDS = 150                  # steps of GAME OVER (chapter 43's WAITS)
STATES = gen43.STATES
LINES_A_STEP = 262          # a step of the game: the 60 Hz machine's frame, in lines
LINES = {EU: 313, JP: 262}
BONUS0 = 0x99               # a round's bonus at its start, in tens of points, BCD
EVERY = 8                   # steps for each ten the bonus drops
CAP = 5                     # the round from which a gem is worth the most
MAXS = 4                    # the fastest a face goes, pixels a step
MAX_LIVES = 9               # a digit's worth
EXTRA_AT = 0x10             # a life more at 1,000 points: the score's middle pair
HI_START = [0x00, 0x20, 0x00]   # the best score at the start: 002000

# the tiles, numbered so that a wall is any name from BRICK up
PAPER, ALLEY, GEM, BRICK = 0, 1, 2, 3
DIGIT0 = gen43.DIGIT0
SCORE_AT, LIVES_AT, HI_AT = gen43.SCORE_AT, gen43.LIVES_AT, gen43.HI_AT
LABELS = gen43.LABELS
BOTTOM = 23
BOTTOM_TEXT = [(2, "ROUND"), (21, "BONUS")]
ROUND_AT = 32 * BOTTOM + 8          # the cells of the round's two digits
BONUS_AT = 32 * BOTTOM + 27         # and of the bonus's, then a 0
OVER_AT, OVER_TEXT = gen43.OVER_AT, gen43.OVER_TEXT

PAPER_C, BRICK_C, ALLEY_C, GEM_C = gen43.PAPER_C, gen43.BRICK_C, gen43.ALLEY_C, gen43.GEM_C
RUNNER_C, FACE_C, BORDER = gen43.RUNNER_C, gen43.FACE_C, gen43.BORDER
BRICK_SHAPE, GEM_SHAPE, FONT = gen43.BRICK_SHAPE, gen43.GEM_SHAPE, gen43.FONT
SPRITE_PATTERNS, RUNNER_P, FACE_P = gen43.SPRITE_PATTERNS, gen43.RUNNER_P, gen43.FACE_P
TILE_SHAPES = [0] * 8 + [0] * 8 + list(GEM_SHAPE) + list(BRICK_SHAPE)
TILE_COLOURS = [PAPER_C] * 8 + [ALLEY_C] * 8 + [GEM_C] * 8 + [BRICK_C] * 8

# the arena: row 0 the status line, rows 1 to 22 a wall, 30 names, a wall,
# row 23 the bottom line: bricks, ROUND and its digits, BONUS and its
MIDDLE = {1: BRICK}
for _y in LANES:
    MIDDLE[_y // 8] = MIDDLE[_y // 8 + 1] = ALLEY
AROWS = [MIDDLE.get(r, PAPER) for r in range(1, 23)]


def row0():
    out = [32] * 32
    for col, text in LABELS:
        out[col:col + len(text)] = [ord(c) for c in text]
    return out


def row23():
    """the bottom line as a game begins: the round's and the bonus's digits
    come with its first round"""
    out = [BRICK] * 32
    for col, text in BOTTOM_TEXT:
        out[col:col + len(text) + 1] = [ord(c) for c in text + " "]
    out[ROUND_AT - 32 * BOTTOM:ROUND_AT - 32 * BOTTOM + 2] = [32, 32]
    out[BONUS_AT - 32 * BOTTOM:BONUS_AT - 32 * BOTTOM + 3] = [32, 32, DIGIT0]
    return out


def arena_names():
    out = row0()
    for mid in AROWS:
        out += [BRICK] + [mid] * 30 + [BRICK]
    return out + row23()


assert all(AROWS[r - 1] == PAPER for r in GEM_ROWS) and len(arena_names()) == 768
assert row23()[ROUND_AT % 32 - 1] == 32 and row23()[BONUS_AT % 32 - 1] == 32

# ------------------------------------------------------------------ the title
TITLE_WORDS = [(2, "GRIN"), (9, "ALLEY")]   # the first row of each word's letters
LETTER_W = 6                                # five columns and a gap
TITLE_ALLEY = (17, 18)                      # an alley across the title, with a face in it
TITLE_TEXT = [(10, 20, "PRESS SPACE"), (3, 22, "CURSOR KEYS OR JOYSTICK 1")]
TITLE_RUNNER = (24, 119)                    # X, Y: lines 120 to 135, above the alley
TITLE_FACE = (40, 135, 2)                   # X, Y and step: lines 136 to 151, in it


def glyph(ch):
    k = 8 * (ord(ch) - 32)
    return FONT[k:k + 8]


def title_names():
    """the title's 768 names: the status line's labels, the name in big
    letters, each pixel of chapter 30's character a brick, an alley, and
    the lines to read"""
    out = [PAPER] * 768
    out[0:32] = row0()
    for top, word in TITLE_WORDS:
        width = LETTER_W * len(word) - 1
        left = (32 - width) // 2
        for k, ch in enumerate(word):
            g = glyph(ch)
            for r in range(1, 7):           # its six rows of pixels
                for c in range(1, 6):       # and five columns
                    if g[r] >> (7 - c) & 1:
                        at = 32 * (top + r - 1) + left + LETTER_W * k + c - 1
                        out[at] = BRICK
    for r in TITLE_ALLEY:
        out[32 * r:32 * r + 32] = [ALLEY] * 32
    for col, row, text in TITLE_TEXT:
        out[32 * row + col:32 * row + col + len(text)] = [ord(c) for c in text]
    return out


def title_copy():
    (rx, ry), (fx, fy, _) = TITLE_RUNNER, TITLE_FACE
    return [ry, rx, RUNNER_P, RUNNER_C, fy, fx, FACE_P, FACE_C, 0xD0]


assert all(g[0] == 0 and g[7] == 0 and all(b & 0x81 == 0 for b in g) for g in map(glyph, "GRINALEY"))
assert TITLE_RUNNER[1] + 16 < TITLE_FACE[1] + 1 and TITLE_FACE[1] + 1 == 8 * TITLE_ALLEY[0]

# ------------------------------------------------------------------ the sounds
# chapter 37's tune, its instruments, and five sounds of the game's own, each
# an instrument, a note, its ticks and a priority (chapter 37's effects)
NEW_INSTRUMENTS = [
    ("FANFARE", [13] * 6 + [12] * 6 + [11] * 6 + [10] * 4 + [9, 8, 7, 6, 5, 4, 3, 2],
     [0] * 6 + [4] * 6 + [7] * 6 + [12, music37.HOLD], music37.TONE, 0),
    ("SINK", [14] * 8 + [13] * 8 + [12] * 8 + [11, 10, 10, 9, 9, 8, 8, 7, 7, 6, 5, 4, 3, 2, 1, 0],
     [7] * 8 + [5] * 8 + [3] * 8 + [0, music37.HOLD], music37.TONE, 0),
]
SOUNDS = [("S_GEM", 1, "BELL", "B5", 18),       # a gem taken
          ("S_ROUND", 2, "FANFARE", "C5", 30),  # a round cleared
          ("S_TOUCH", 3, "BLAST", "C2", 20),    # a face's touch
          ("S_EXTRA", 3, "UP", "C5", 14),       # a life won
          ("S_OVER", 4, "SINK", "G4", 40)]      # GAME OVER
SOUND = {name: k for k, (name, *_) in enumerate(SOUNDS)}


def music_inc():
    """chapter 37's music.inc with the game's sounds for its effects"""
    keep = music37.INSTRUMENTS, music37.EFFECTS, music37.INSTR
    try:
        music37.INSTRUMENTS = list(keep[0]) + NEW_INSTRUMENTS
        music37.INSTR = {name: k for k, (name, *_) in enumerate(music37.INSTRUMENTS)}
        music37.EFFECTS = SOUNDS
        text = gen37.music_inc()
    finally:
        music37.INSTRUMENTS, music37.EFFECTS, music37.INSTR = keep
    old = ("; music.inc -- chapter 37: the book's tune, its instruments and the\n"
           "; effects; generated by gen37.py from music37.py\n")
    assert text.startswith(old)
    return ("; music.inc -- chapter 44: chapter 37's tune and instruments, and the\n"
            "; game's five sounds; generated by gen44.py from music37.py\n") + text[len(old):]


# ------------------------------------------------------------------ the RAM
VARS_AT = 0xC100
ENGINE_AT = 0xC000
RAM = f"""stat    EQU VARS                ; the status isr read: F, 5S, C, a sprite's number
ticks   EQU VARS + 1            ; frames counted by isr, two bytes
seed    EQU VARS + 3            ; random's state, two bytes (chapter 41)
state   EQU VARS + 5            ; TITLE, PLAY, HIT or OVER
left    EQU VARS + 6            ; the steps left of HIT or of OVER
lives   EQU VARS + 7
gems    EQU VARS + 8            ; the gems of the round still lying
roundno EQU VARS + 9            ; the round, BCD
held    EQU VARS + 10           ; the keys and the stick: a 0 for each held
stale   EQU VARS + 11           ; frames whose C play1 does not believe
shownl  EQU VARS + 12           ; the lives on the status line
queued  EQU VARS + 13           ; the names queued for the sends
queue   EQU VARS + $10          ; 16 names: the VRAM address, then the name
copy    EQU VARS + $40          ; the sprites' attributes: Y, X, pattern, colour
runner  EQU copy                ; the runner's Y and X
faces   EQU copy + 4            ; and the faces', four each
steps   EQU VARS + $60          ; each face's step, -4 to 4
due     EQU VARS + $68          ; lines owed to the game's steps, two bytes
value   EQU VARS + $6A          ; a gem's points, BCD
bonus   EQU VARS + $6B          ; the round's bonus, in tens, BCD
tock    EQU VARS + $6C          ; steps to the bonus's next drop
awarded EQU VARS + $6D          ; 1 when the game's life more is won
ENGINE  EQU ${ENGINE_AT:04X}               ; chapter 37's player, in a page of its own:
beats   EQU ENGINE              ; its ticks, two bytes (chapter 37's ticks)
owed    EQU ENGINE + 2          ; lines owed to the player, two bytes
lines   EQU ENGINE + 4          ; the machine's lines a frame: 313 or 262
tick    EQU ENGINE + 6          ; ticks still to the next row
songp   EQU ENGINE + 7          ; the song's step, two bytes (chapter 37's step)
barno   EQU ENGINE + 9          ; the step's number
rowno   EQU ENGINE + 10         ; the row in the bar
shadow  EQU ENGINE + ${gen37.SHADOW_AT:02X}        ; R0 to R10, as the next tick sends them
chan_a  EQU shadow + {gen37.SHADOW_REGS}         ; the channels, CHAN bytes each
chan_b  EQU chan_a + CHAN
chan_c  EQU chan_b + CHAN
chan_x  EQU chan_c + CHAN       ; the effect: a fourth channel, on C's registers
names   EQU $C400               ; the copy of the 768 names
score   EQU $C700               ; three BCD bytes (chapter 40)
hi      EQU score + 3           ; the best, three more
shown   EQU score + $100        ; the six bytes last sent, a page on
"""
QUEUE_MAX = gen43.QUEUE_MAX

CONSTS = f"""SAT     EQU $1B00               ; the sprites' attributes
SPAT    EQU $3800               ; and their patterns
TITLE   EQU 0                   ; the states
PLAY    EQU 1
HIT     EQU 2
OVER    EQU 3
PAPER   EQU {PAPER}                   ; the tiles' names: from BRICK up, a wall
ALLEY   EQU {ALLEY}
GEM     EQU {GEM}
BRICK   EQU {BRICK}
DIGIT0  EQU ${DIGIT0:02X}                 ; '0'
X_MIN   EQU {X_MIN}                   ; a face's X: X_MIN to X_MAX
X_MAX   EQU {X_MAX}
HOME_X  EQU {HOME[0]}                 ; the runner's home
HOME_Y  EQU {HOME[1]}
GEMS    EQU {GEMS}                   ; gems a round
LIVES   EQU {LIVES}
STILL   EQU {STILL}                  ; steps held still at a touch
ENDS    EQU {ENDS}                 ; steps of GAME OVER
STEPL   EQU {LINES_A_STEP}                 ; the lines of a step: the 60 Hz frame
BONUS0  EQU ${BONUS0:02X}                 ; the bonus as a round begins, tens, BCD
EVERY   EQU {EVERY}                   ; steps for each ten it drops
CAP     EQU {CAP}                   ; the round from which a gem is worth the most
MAXS    EQU {MAXS}                   ; a face's fastest, pixels a step
MAX_LIVES EQU {MAX_LIVES}
EXTRA_AT EQU ${EXTRA_AT:02X}               ; the score's middle pair at 1,000 points
SCORE_AT EQU $1800 + {SCORE_AT}           ; row 0: the score's first digit
LIVES_AT EQU $1800 + {LIVES_AT}           ; the lives
HI_AT   EQU $1800 + {HI_AT}             ; and the best's first digit
ROUND_AT EQU {ROUND_AT}               ; the bottom line: the round's first digit
BONUS_AT EQU {BONUS_AT}               ; and the bonus's
"""

# ------------------------------------------------------------------ the frame
ISR = """
; isr: every frame. The status kept in stat, the signal let down; the frame
; counted, and its lines owed to the game's steps; the keys and the stick read
; while the frame is young; then chapter 37's player: when pace gives it a
; tick, last tick's registers to the PSG first, and the next tick worked out.
; Keeps every register it uses
isr:    push af                 ; 12
        in a, (VDP_CTRL)        ; 12  the status: F, 5S, C, a sprite's number
        ld (stat), a            ; 14
        push bc                 ; 12
        push de                 ; 12
        push hl                 ; 12
        push ix                 ; 17
        ld hl, (ticks)          ; 17
        inc hl                  ;  7
        ld (ticks), hl          ; 17
        ld hl, (due)            ; 17  the lines owed to the game ...
        ld de, (lines)          ; 22
        add hl, de              ; 12  ... and this frame's, 262 or 313
        ld (due), hl            ; 17
        call input              ; 18  held
        call pace               ; 18  carry: the player's tick (chapter 37)
        jr nc, .done            ; 13, or 8
        call tochip             ; 18
        call play               ; 18
.done:  pop ix                  ; 16
        pop hl                  ; 11
        pop de                  ; 11
        pop bc                  ; 11
        pop af                  ; 11
isrend: ei                      ;  5
        ret                     ; 11
"""

PACED = """
; paced: B = the game's steps owed, one for each STEPL lines that isr has
; added to due, which keeps what is left over. Uses B, DE, HL
paced:  ld hl, (due)            ; 17
        ld de, -STEPL           ; 11
        ld b, 0                 ;  8
.more:  add hl, de              ; 12  carry: STEPL lines more
        jr nc, .rest            ; 13, or 8
        inc b                   ;  5  a step
        jr .more                ; 13
.rest:  sbc hl, de              ; 17  the last STEPL given back: no carry
        ld (due), hl            ; 17
        ret                     ; 11
"""

INPUT = """
; input: in the interrupt, the cursor keys and joystick 1 together (chapters
; 34 and 35) -> held, in register 14's way: bits 0 to 3 up, down, left,
; right, bit 4 SPACE or button A, a 0 for each held. Uses A, BC, HL
input:  call keys               ; 18  row 8 in register 14's way
        ld c, a                 ;  5
        xor a                   ;  5  port 1
        call joy                ; 18  its register 14
        and c                   ;  5  held on either
        ld (held), a            ; 14
        ret                     ; 11
"""

FX = """
; fx: A = a sound -> chapter 37's sfx, with the interrupts off, for sfx and
; the player share chan_x. Uses A, DE, HL, IX
fx:     di                      ;  5
        call sfx                ; 18
        ei                      ;  5
        ret                     ; 11
"""

# chapter 43's walled, with a wall any name from the brick's up
WALLED = gen43.WALLED.replace(
    """; 26). A wall is the brick's name. Uses A, BC, DE, HL""",
    """; 26). A wall is any name from the brick's up. Uses A, BC, DE, HL""").replace(
    """        cp BRICK                ;  8  the walls' name
        jr z, .wall             ; 13, or 8""",
    """        cp BRICK                ;  8  the bricks and the letters
        jr nc, .wall            ; 13, or 8""").replace(
    """        or a                    ;  5  A is BRICK""",
    """        or a                    ;  5  A is BRICK or more""")
assert WALLED.count("jr nc, .wall") == 1 and WALLED.count("A is BRICK or more") == 1

STEP_RT = gen43.STEP_RT
PATROL = gen43.PATROL
WALK = gen43.WALK

PICK = gen43.PICK.replace(
    """; took: HL = a gem's cell in the copy of the names -> the cell paper again,
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
        pop hl                  ; 11""",
    """; took: HL = a gem's cell in the copy of the names -> the cell paper again,
; queued; the gem's points, its sound, and a life if one is due; a gem
; fewer. Keeps BC, DE, HL. Uses A, IX
took:   push bc                 ; 12
        push de                 ; 12
        push hl                 ; 12
        xor a                   ;  5  PAPER
        call post               ; 18
        ld a, (value)           ; 14  the round's points for a gem
        call addsc              ; 18
        ld hl, gems             ; 11
        dec (hl)                ; 12  a gem fewer
        ld a, S_GEM             ;  8
        call fx                 ; 18
        call award              ; 18
        pop hl                  ; 11""")
assert PICK != gen43.PICK

SOW = gen43.SOW.replace(
    """; round: GEMS gems sown, and as many to take. Uses A, BC, DE, HL
round:  ld b, GEMS              ;  8
""",
    """; round: the next round: its number; a gem's points, ten for each round up
; to CAP; the faces' speeds; the bonus full; the two numbers on the bottom
; line through the queue; GEMS gems sown, and as many to take. Uses A, BC,
; DE, HL
round:  ld a, (roundno)         ; 14
        add a, 1                ;  8
        daa                     ;  5  one more, in BCD
        ld (roundno), a         ; 14
        ld hl, names + ROUND_AT ; 11
        call post2              ; 18  its two digits
        ld a, (roundno)         ; 14
        cp CAP                  ;  8  from round CAP on ...
        jr c, .value            ; 13, or 8
        ld a, CAP               ;  8  ... the most
.value: add a, a                ;  5
        add a, a                ;  5
        add a, a                ;  5
        add a, a                ;  5  a digit on: tens of points
        ld (value), a           ; 14
        call speeds             ; 18
        ld a, BONUS0            ;  8
        ld (bonus), a           ; 14
        ld hl, names + BONUS_AT ; 11
        call post2              ; 18
        ld a, EVERY             ;  8
        ld (tock), a            ; 14
        ld b, GEMS              ;  8
""")
assert SOW != gen43.SOW

ROUNDS = """
; speeds: each face's speed for the round: its first speed and one more for
; each round after the first, never more than MAXS, the way it goes now
; kept. Uses A, BC, DE, HL
speeds: ld a, (roundno)         ; 14
        dec a                   ;  5  the rounds before this one
        ld c, a                 ;  5
        ld hl, fsteps           ; 11  the first steps
        ld de, steps            ; 11
        ld b, 4                 ;  8
.face:  ld a, (hl)              ;  8
        bit 7, a                ; 10
        jr z, .up               ; 13, or 8
        neg                     ; 10  its first speed
.up:    add a, c                ;  5  one more a round
        cp MAXS + 1             ;  8
        jr c, .way              ; 13, or 8
        ld a, MAXS              ;  8
.way:   ex de, hl               ;  5
        bit 7, (hl)             ; 14  the way it goes now
        jr z, .put              ; 13, or 8
        neg                     ; 10
.put:   ld (hl), a              ;  8
        ex de, hl               ;  5
        inc hl                  ;  7
        inc de                  ;  7
        djnz .face              ; 14, or 9
        ret                     ; 11

; cleared: the round's last gem gone: its sound, what is left of the bonus
; added, a life if one is due, and the next round. Uses every register but IY
cleared: ld a, S_ROUND          ;  8
        call fx                 ; 18
        ld a, (bonus)           ; 14
        call addten             ; 18
        call award              ; 18
        jp round                ; 11

; drop: a step of the bonus's count: every EVERY steps a ten fewer, down to
; none, its two digits queued. Uses A, BC, DE, HL
drop:   ld hl, tock             ; 11
        dec (hl)                ; 12
        ret nz                  ; 12, or 6
        ld (hl), EVERY          ; 11
        ld a, (bonus)           ; 14
        or a                    ;  5
        ret z                   ; 12, or 6  none left
        sub 1                   ;  8
        daa                     ;  5  a ten fewer, in BCD (chapter 9)
        ld (bonus), a           ; 14
        ld hl, names + BONUS_AT ; 11  its first digit's cell
        jp post2                ; 11

; post2: A = a BCD byte, HL = the cell of its first digit in the copy of the
; names -> its two digits posted. Uses A, BC, DE, HL
post2:  push hl                 ; 12
        push af                 ; 12
        rrca                    ;  5
        rrca                    ;  5
        rrca                    ;  5
        rrca                    ;  5
        and 15                  ;  8  the first digit
        add a, DIGIT0           ;  8
        call post               ; 18
        pop af                  ; 11
        pop hl                  ; 11
        inc hl                  ;  7  the next cell
        and 15                  ;  8  the second
        add a, DIGIT0           ;  8
        jp post                 ; 11

; addten: A = points in tens, two BCD digits -> added to score: its second
; digit to the tens, its first to the hundreds, the carry taken on with ADC
; and DAA (chapter 9). Uses A, BC, HL
addten: ld c, a                 ;  5
        rrca                    ;  5
        rrca                    ;  5
        rrca                    ;  5
        rrca                    ;  5
        and 15                  ;  8  the first digit, as hundreds
        ld b, a                 ;  5
        ld a, c                 ;  5
        add a, a                ;  5
        add a, a                ;  5
        add a, a                ;  5
        add a, a                ;  5  the second, as tens
        ld hl, score + 2        ; 11  the tens and the units
        add a, (hl)             ;  8
        daa                     ;  5
        ld (hl), a              ;  8
        dec hl                  ;  7  the thousands and the hundreds
        ld a, b                 ;  5
        adc a, (hl)             ;  8  with the tens' carry
        daa                     ;  5
        ld (hl), a              ;  8
        dec hl                  ;  7  and the first two digits
        ld a, (hl)              ;  8
        adc a, 0                ;  8
        daa                     ;  5
        ld (hl), a              ;  8
        ret                     ; 11
"""


def award(once=True):
    """award; in extra.asm (ONCE false) the test of awarded is left out"""
    test = """        ld a, (awarded)         ; 14
        or a                    ;  5
        ret nz                  ; 12, or 6  won already
""" if once else ""
    return """
; award: a life more, once a game, when the score reaches 1,000 points, and
; its sound; never past MAX_LIVES, the most a digit shows. Uses A, DE, HL, IX
award:
""" + test + """        ld hl, score            ; 11
        ld a, (hl)              ;  8  the first two digits
        or a                    ;  5
        jr nz, .life            ; 13, or 8  10,000 or more
        inc hl                  ;  7
        ld a, (hl)              ;  8  the thousands and the hundreds
        cp EXTRA_AT             ;  8
        ret c                   ; 12, or 6  below 1,000
.life:  ld a, 1                 ;  8
        ld (awarded), a         ; 14
        ld hl, lives            ; 11
        ld a, (hl)              ;  8
        cp MAX_LIVES            ;  8
        jr nc, .sound           ; 13, or 8  as many as a digit shows
        inc (hl)                ; 12  the status line shows it next frame
.sound: ld a, S_EXTRA           ;  8
        jp fx                   ; 11
"""


def play1(once=True):
    return """
; play0: nothing to set: the steps come from due
play0:  ret                     ; 11

; play1: THE FRAME OF THE PLAY. The next round when the last gem is gone;
; for each step owed, a step of the runner and of every face, and of the
; bonus's count; the gems under the runner; the best score; and a touch: C,
; which isr kept from the frame just drawn. Uses every register but IY
play1:  ld a, (gems)            ; 14
        or a                    ;  5
        call z, cleared         ; 18, or 11  the last gem gone: the next round
        call paced              ; 18  B: the steps owed
.step:  push bc                 ; 12
        call step               ; 18  the runner and the faces
        call drop               ; 18  the bonus
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

; hit0: a life fewer, its sound, and the game held still
hit0:   ld hl, lives            ; 11
        dec (hl)                ; 12  the status line shows it next frame
        ld a, STILL             ;  8
        ld (left), a            ; 14
        ld a, S_TOUCH           ;  8
        jp fx                   ; 11

; hit1: the steps owed off the wait, and at its end GAME OVER, or the
; runner home again
hit1:   call countdown          ; 18
        ret nz                  ; 12, or 6
        ld a, (lives)           ; 14
        or a                    ;  5
        ld a, OVER              ;  8
        jp z, go                ; 11  no lives left
        ld hl, HOME_X << 8 | HOME_Y ; 11
        ld (runner), hl         ; 17  home again, Y and X
        ld a, 1                 ;  8
        ld (stale), a           ; 14  its C is the frame before it went
home:   ld a, PLAY              ;  8
        jp go                   ; 11

; countdown: left less the steps owed, down to 0 -> Z at 0. Uses A, B, DE, HL
countdown: call paced           ; 18  B: the steps owed
        ld hl, left             ; 11
        ld a, (hl)              ;  8
        sub b                   ;  5
        jr nc, .left            ; 13, or 8
        xor a                   ;  5  no less than none
.left:  ld (hl), a              ;  8
        or a                    ;  5
        ret                     ; 11
""" + award(once)


STATES_RT = """
; title0: the title's 768 names at 29 T-states a name (chapter 20); the score
; of the last game, the lives a game begins with and the best, all to be
; sent; the runner and a face
title0: di                      ;  5
        VRAM_WRITE $1800        ; 40
        ei                      ;  5
        ld hl, tnames           ; 11
        ld bc, VDP_DATA         ; 11  B: 0, a run of 256; C: the port
        ld d, 3                 ;  8  three runs
.run:   outi                    ; 18
        jp nz, .run             ; 11
        dec d                   ;  5
        jr nz, .run             ; 13, or 8
        ld hl, shown            ; 11
        ld b, 6                 ;  8
.none:  ld (hl), $FF            ; 11  none of the digits shown
        inc l                   ;  5
        djnz .none              ; 14, or 9
        ld a, LIVES             ;  8
        ld (lives), a           ; 14
        ld a, $FF               ;  8
        ld (shownl), a          ; 14
        ld hl, tcopy            ; 11  the two sprites, and the face's step
        ld de, copy             ; 11
        ld bc, 9                ; 11
        ldir                    ; 23 a byte, 18 the last
        ld a, {tstep}             ;  8
        ld (steps), a           ; 14
        ret                     ; 11

; title1: the face a step on for each step owed; SPACE or button A held? The
; seed is the frame count, 1 for 0 (chapter 41), and a game begins
title1: call paced              ; 18
.step:  push bc                 ; 12
        ld ix, faces            ; 16  the title's face
        ld hl, steps            ; 11
        call patrol             ; 18
        pop bc                  ; 11
        djnz .step              ; 14, or 9
        ld a, (held)            ; 14  isr read them
        and $10                 ;  8  SPACE, button A
        ret nz                  ; 12, or 6
        ld hl, (ticks)          ; 17  the seed
        ld a, h                 ;  5
        or l                    ;  5
        jr nz, .seed            ; 13, or 8
        inc hl                  ;  7
.seed:  ld (seed), hl           ; 17
pressed: call setup             ; 18  the arena, the status line, the sprites
        call round              ; 18  the first round
        ld a, PLAY              ;  8
        jp go                   ; 11

; over0: GAME OVER, its sound, and ENDS steps of it
over0:  ld hl, otext            ; 11
        ld de, $1800 + 32 * {orow} + {ocol} | $4000 ; 11
        di                      ;  5
        call say                ; 18
        ei                      ;  5
        ld a, ENDS              ;  8
        ld (left), a            ; 14
        ld a, S_OVER            ;  8
        jp fx                   ; 11

; over1: the steps owed off the wait, and at its end the title again
over1:  call countdown          ; 18
        ret nz                  ; 12, or 6
again:  ld a, TITLE             ;  8
        jp go                   ; 11

; setup: a new game. The arena into the copy of the names and to the VDP;
; score 0, none of its digits shown; three lives, none won; round 0; the
; sprites at their first places, the faces' first steps; no names queued
setup:  call arena              ; 18
        ld hl, score            ; 11
        ld b, 3                 ;  8
.zero:  ld (hl), 0              ; 11
        inc l                   ;  5
        djnz .zero              ; 14, or 9
        ld hl, shown            ; 11
        ld b, 6                 ;  8
.none:  ld (hl), $FF            ; 11  none of its digits shown: the sends send all
        inc l                   ;  5
        djnz .none              ; 14, or 9
        ld a, LIVES             ;  8
        ld (lives), a           ; 14
        ld a, $FF               ;  8
        ld (shownl), a          ; 14
        ld hl, first            ; 11  the sprites' first places
        ld de, copy             ; 11
        ld bc, 21               ; 11
        ldir                    ; 23 a byte, 18 the last
        ld hl, fsteps           ; 11  and the faces' first steps
        ld de, steps            ; 11
        ld bc, 4                ; 11
        ldir                    ; 23 a byte, 18 the last
        xor a                   ;  5
        ld (queued), a          ; 14
        ld (stale), a           ; 14
        ld (roundno), a         ; 14
        ld (awarded), a         ; 14
        ret                     ; 11

; arena: the names of the play into the copy of the names and to the VDP at
; once, 41 T-states a name in its rows: row 0 the status line's labels from
; row0, rows 1 to 22 a wall, 30 names from arows and a wall, and row 23 the
; bottom line from row23
arena:  di                      ;  5
        VRAM_WRITE $1800        ; 40
        ei                      ;  5
        ld hl, row0             ; 11  row 0
        ld de, names            ; 11
        call row32              ; 18
        ex de, hl               ;  5  HL: the copy's row 1
        ld de, arows            ; 11  DE: the table
        ld c, 22                ;  8  rows 1 to 22
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
        ex de, hl               ;  5  DE: the copy's row 23
        ld hl, row23            ; 11  the bottom line
; row32: HL = 32 names, DE = where in the copy -> both there and to the VDP.
; Uses A, B, DE, HL
row32:  ld b, 32                ;  8
.name:  ld a, (hl)              ;  8
        ld (de), a              ;  8
        out (VDP_DATA), a       ; 12
        inc hl                  ;  7
        inc de                  ;  7
        djnz .name              ; 14, or 9
        ret                     ; 11
"""


def setup_lines():
    """the cartridge's start: chapter 43's, with the player set up too"""
    base = gen43.setup_lines()
    old_tiles = """        VRAM_WRITE $0000        ; the four tiles' shapes"""
    assert old_tiles in base
    engine = (gen37.init_lines().replace("ld (ticks), hl", "ld (beats), hl")
              .replace("ld (step), hl", "ld (songp), hl")
              .replace("        ld (frames), a\n", ""))
    assert "(frames)" not in engine and "(beats)" in engine and "(songp)" in engine
    out = base
    old = """""" + im2("isr")
    assert out.count(old) == 1
    out = out.replace(old, """        ld hl, ENGINE           ; the player's page, all 0
        ld de, ENGINE + 1
        ld bc, 255
        ld (hl), 0
        ldir
""" + engine + im2("isr"))
    return out


def engine_parts():
    """chapter 37's player, its ticks and its song's step renamed"""
    play = gen37.PLAY.replace("ld hl, (ticks)          ; 17", "ld hl, (beats)          ; 17").replace(
        "ld (ticks), hl          ; 17", "ld (beats), hl          ; 17")
    nxt = gen37.NEXT.replace("ld hl, (step)           ; 17", "ld hl, (songp)          ; 17").replace(
        "ld (step), hl           ; 17", "ld (songp), hl          ; 17")
    assert "(ticks)" not in play and "(step)" not in nxt and play != gen37.PLAY and nxt != gen37.NEXT
    return gen37.PACE + gen37.SEND + play + gen37.ROW + gen37.VOICE + nxt + gen37.SOUND + gen37.SFX


def data():
    first = gen43.first_copy()
    return ("""codeend:                        ; the code ends here
        ALIGN 16
starts: dw title0, play0, hit0, over0 ; each state's first frame
frames: dw title1, play1, hit1, over1 ; and every frame of it
""" + "tiles:                          ; paper, alley, gem, brick (chapter 39)\n" + db_rows(TILE_SHAPES) +
            "tcols:                          ; their colours\n" + db_rows(TILE_COLOURS) +
            "row0:                           ; the status line's labels\n" + db_rows(row0(), 16) +
            "arows:                          ; rows 1 to 22: the name between the walls\n" +
            db_rows(AROWS, 22) +
            "row23:                          ; the bottom line\n" + db_rows(row23(), 16) +
            "rows:                           ; the corridors' rows, where sow puts gems\n" +
            db_rows(GEM_ROWS) +
            "first:                          ; the sprites' attributes when a game begins\n" +
            db_rows(first, 4) +
            "fsteps:                         ; the faces' first steps\n" +
            db_rows([s & 255 for _, s in FACES]) +
            "tcopy:                          ; the title's runner and face, and the end\n" +
            db_rows(title_copy()) +
            "nums:                           ; score and the best score at the start\n" +
            db_rows([0, 0, 0] + HI_START) +
            f"otext:  db \"{OVER_TEXT}\", 0\n" +
            "tnames:                         ; the title's 768 names\n" + db_rows(title_names(), 16) +
            "sprites:                        ; the runner and a face, 16 x 16 (chapter 26)\n" +
            db_rows(SPRITE_PATTERNS) +
            "font:                           ; chapter 30's characters, codes 32 to 127\n" +
            db_rows(FONT) + gen37.start_data())


SAY = {
    "game": """; GRIN ALLEY, finished: chapter 43's game with chapter 37's tune and five
; sounds of its own, a score worth chasing, rounds that grow harder, steps
; 262 lines apart on both machines, and a title.
""",
    "extra": """; WHERE IT BREAKS. game.asm whose award forgets that the life more is won
; once a game.
""",
}
WHAT = {"game": "GRIN ALLEY, finished", "extra": "a life too many"}


def program(name, every=EVERY, award_first=False, careful=None, frames_paced=False):
    """the program NAME; the workshop's variants change the steps for each
    ten the bonus drops, EVERY; ask award before addten in cleared,
    AWARD_FIRST; or count a step for each frame, FRAMES_PACED"""
    sends = gen43.SENDS
    parts = (ISR + PACED + INPUT + FX + sends + gen40.UPDATE + gen42.PUTBCD + gen35.KEYS +
             gen35.JOY + WALK + gen39.CELL + WALLED + PATROL + STEP_RT + PICK + SOW + ROUNDS +
             play1(name != "extra") +
             STATES_RT.format(tstep=TITLE_FACE[2], orow=OVER_AT[1], ocol=OVER_AT[0]) +
             gen40.BEST + gen40.ADDSC + gen40.SAY + gen41.RANDOM + engine_parts())
    body = setup_lines() + gen43.MAIN
    src = (HEAD.format(name=name, chapter=44, what=WHAT[name]) + BIOS + RAM + CONSTS + gen37.fields() +
           IM2 + SAY[name] + tidy(body + parts) + data() + "        ALIGN 16\nkbdjoy:                         ; "
           "register 14's bits 0-3 for the cursor keys (chapter 35)\n" + db_rows(gen35.kbd_table(), 16) +
           gen37.ENGINE_INC + "romend:                         ; the cartridge's last byte, and one\n" +
           CART_END)
    if every != EVERY:
        src = src.replace(f"EVERY   EQU {EVERY} ", f"EVERY   EQU {every} ")
    if award_first:
        old = tidy("""cleared: ld a, S_ROUND          ;  8
        call fx                 ; 18
        ld a, (bonus)           ; 14
        call addten             ; 18
        call award              ; 18
""")
        assert src.count(old) == 1
        src = src.replace(old, tidy("""cleared: ld a, S_ROUND          ;  8
        call fx                 ; 18
        call award              ; 18
        ld a, (bonus)           ; 14
        call addten             ; 18
"""))
    if frames_paced:
        old = tidy("""        ld de, (lines)          ; 22
""")
        assert src.count(old) == 1
        src = src.replace(old, tidy("""        ld de, STEPL            ; 11  a step a frame
"""))
    return src


PROGRAMS = ["game", "extra"]


def main():
    with open(os.path.join(HERE, "music.inc"), "w") as f:
        f.write(music_inc())
    for name in PROGRAMS:
        with open(os.path.join(HERE, f"{name}.asm"), "w") as f:
            f.write(program(name))
    print("music.inc " + " ".join(f"{n}.asm" for n in PROGRAMS))


if __name__ == "__main__":
    main()
