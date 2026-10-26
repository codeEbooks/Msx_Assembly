#!/usr/bin/env python3
"""gen46.py - the programs of chapter 46: the second game, LANTERN KEEP,
finished: guards on their rounds, thirty-two lanterns to light, three lives,
the time, the score, an end, and a tune at the title, in a cartridge of 32 KB.

    python3 gen46.py && ./build.sh

    game.asm    THE GAME, FINISHED. Chapter 45's keep with what it was built
                for. Two lanterns in each room's walls are lit by walking up
                to them, a hundred points each; the twenty-eight guards walk
                their rounds, one or two in a room, and a guard's touch,
                which the VDP's C bit tells, costs a life of three; the time
                falls from 999, a unit every sixteen steps. With every
                lantern lit the keep is lit, and the time left is added to
                the score; with no lives or no time left, the game is over.
                The map shows the rooms whose two lanterns are lit. A tune of
                the game's own plays at the title, from chapter 37's player
                in the interrupt; in the play the music is silent, and four
                sounds go over channel C
    late.asm    WHERE IT BREAKS: game.asm whose flip places the room's guards
                a loop late, in flip1 instead of flip0

The guards' rounds and the lanterns are designed here, in Python, and the
checks below hold for every place of every round. The world, the flip, the
map and the queue are chapter 45's (gen45.py); the steps of 262 lines, post2,
addten and the sounds' instruments chapter 44's; the player chapter 37's.
Every line of this chapter's own routines carries its price, the MSX's
T-states, which meas46.py checks with walk.py and the debugger. The
interrupt is taken in mode 2 (chapter 17); build.sh assembles with
--syntax=bFw.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
for ch in ("tools", "ch26", "ch30", "ch33", "ch35", "ch37", "ch38", "ch39", "ch40", "ch42",
           "ch43", "ch44", "ch45"):
    sys.path.insert(0, os.path.join(REPO, ch))
from asmparts import IM2, im2  # noqa: E402
from gen26 import tidy, db_rows, big  # noqa: E402  (chapter 26)
import gen35  # noqa: E402  (chapter 35: joy)
import gen37  # noqa: E402  (chapter 37: the player)
import gen38  # noqa: E402  (chapter 38: here, setpage2, subreg)
import gen39  # noqa: E402  (chapter 39: cell)
import gen40  # noqa: E402  (chapter 40: best, addsc)
import gen42  # noqa: E402  (chapter 42: putbcd)
import gen44  # noqa: E402  (chapter 44: walled, paced, post2, addten, fx, the instruments)
import gen45  # noqa: E402  (chapter 45: the world, the flip, the map)
import music37  # noqa: E402  (chapter 37: the music's bytes)
sys.path.insert(0, HERE)

EU, JP = gen45.EU, gen45.JP
MACHINES = [EU, JP]
BLACK, DARK_BLUE, CYAN, WHITE = gen45.BLACK, gen45.DARK_BLUE, gen45.CYAN, gen45.WHITE
NAME = gen45.NAME
grid, solid_at, reach, room_name = gen45.grid, gen45.solid_at, gen45.reach, gen45.room_name
ROOMS, START, HOME, LANTERNS, EXITS = gen45.ROOMS, gen45.START, gen45.HOME, gen45.LANTERNS, gen45.EXITS
N, E, S, W = gen45.N, gen45.E, gen45.S, gen45.W
X_LAST, Y_FIRST, Y_LAST, STEP = gen45.X_LAST, gen45.Y_FIRST, gen45.Y_LAST, gen45.STEP

# ---------------------------------------------------------------- the rules
LIVES = 3
STILL = 50                  # steps the game stands still at a touch (chapter 44's name)
ENDS = 150                  # steps of GAME OVER, or of the keep lit
TIME0 = (0x09, 0x99)        # the time at the start: 999, its hundreds, then a BCD pair
TICKS = 16                  # steps of play for each unit of time
LAMPS = 2 * ROOMS           # 32 lanterns
HI_START = [0x00, 0x20, 0x00]   # the best score at the start: 002000
STATES = ["TITLE", "PLAY", "FLIP", "MAP", "HIT", "OVER", "WIN"]

# ---------------------------------------------------------------- the guards
H, V = 0, 1                 # a guard's round: along X, or along Y
# each room's guards, the higher first: (the way it goes, the Y or the X it
# keeps to, the least and the most of the other, where it starts on it, and
# its step, in pixels a step of the game)
GUARDS = [
    [(H, 63, 24, 200, 112, 1), (H, 135, 72, 168, 120, -2)],     # A1
    [(H, 63, 40, 216, 160, -1), (H, 119, 48, 200, 64, 2)],      # B1
    [(V, 112, 47, 127, 63, 1)],                                 # C1
    [(H, 47, 8, 224, 200, -1), (V, 128, 95, 127, 111, 1)],      # D1
    [(V, 32, 47, 79, 55, 1), (V, 200, 135, 167, 149, -1)],      # A2
    [(H, 47, 32, 208, 64, 2), (H, 159, 16, 224, 200, -1)],      # B2
    [(V, 200, 47, 135, 95, 1)],                                 # C2
    [(V, 24, 47, 159, 79, 1)],                                  # D2
    [(H, 95, 64, 176, 120, 2), (H, 159, 8, 224, 40, 1)],        # A3
    [(H, 47, 8, 224, 120, 2), (H, 119, 72, 168, 96, -1)],       # B3
    [(V, 208, 47, 95, 59, 1), (H, 167, 8, 176, 140, -1)],       # C3
    [(V, 8, 47, 79, 55, 1), (V, 224, 135, 167, 149, -1)],       # D3
    [(H, 71, 8, 176, 100, 1), (V, 120, 119, 151, 135, 1)],      # A4
    [(H, 159, 16, 224, 40, 1)],                                 # B4
    [(H, 55, 8, 200, 200, -1), (V, 136, 103, 151, 119, 1)],     # C4
    [(V, 224, 47, 119, 59, 1), (H, 167, 8, 224, 120, -1)],      # D4
]
assert len(GUARDS) == ROOMS and all(1 <= len(g) <= 2 for g in GUARDS)
GUARD_COUNT = sum(len(g) for g in GUARDS)
assert GUARD_COUNT == 28
DISTANCE = 40               # a round's least distance, along X or along Y, from an entry


def place_of(gd, v):
    """the guard GD's place, (X, Y), where the coordinate it goes along is V"""
    axis, fixed = gd[0], gd[1]
    return (v, fixed) if axis == H else (fixed, v)


def rounds(gd):
    """every place on the guard GD's round"""
    return [place_of(gd, v) for v in range(gd[2], gd[3] + 1)]


def patrol(gd, v, step):
    """a step of the guard: patrol's rule -> its new coordinate and step"""
    n = v + step
    if not gd[2] <= n <= gd[3]:
        step = -step
        n = v + step
    return n, step


def lines_of(y):
    """the lines of the screen a sprite at Y covers: Y + 1 to Y + 16"""
    return set(range(y + 1, y + 17))


def entries(k):
    """the places the explorer comes into room K at: each door's steps,
    and the gate hall's home"""
    out = [p for v in gen45.door_steps(k).values() for p in v]
    return out + [HOME] if k == START else out


for _k, _gs in enumerate(GUARDS):       # the rounds checked
    _g, _ents = grid(_k), entries(_k)
    for _gd in _gs:
        _axis, _fixed, _lo, _hi, _start, _step = _gd
        assert _lo <= _start <= _hi and abs(_step) in (1, 2) and (_start - _lo) % _step == 0, (_k, _gd)
        for _x, _y in rounds(_gd):
            assert not solid_at(_g, _x, _y), (_k, _gd, "in a wall")
            assert 0 <= _x <= X_LAST and Y_FIRST <= _y <= Y_LAST, (_k, _gd)
            assert all(max(abs(_x - _ex), abs(_y - _ey)) >= DISTANCE for _ex, _ey in _ents), (_k, _gd)
    if len(_gs) == 2:                   # the first's lines all above the second's
        _l0 = set().union(*(lines_of(_y) for _x, _y in rounds(_gs[0])))
        _l1 = set().union(*(lines_of(_y) for _x, _y in rounds(_gs[1])))
        assert max(_l0) < min(_l1), _k

# ---------------------------------------------------------------- the lanterns


def touch(x, y, c, r):
    """lamp's test: do the explorer's 16 x 16 pixels at (X, Y), lines Y + 1
    to Y + 16, reach lantern (C, R)'s cell, or a pixel round it?"""
    return 0 <= x - 8 * c + 16 < 25 and 0 <= y + 1 - 8 * r + 16 < 25


def ltab():
    """lamp's four bytes a lantern: what X and Y are added to, its cell in
    the copy of the names"""
    out = []
    for k in range(ROOMS):
        for c, r in LANTERNS[k]:
            cell = gen45.NAMES_AT + 32 * r + c
            out += [(16 - 8 * c) & 255, (17 - 8 * r) & 255, cell & 255, cell >> 8]
    return out


for _k in range(ROOMS):                  # every lantern reached, by walls alone, and the
    _g = grid(_k)                        # byte-wide test is touch; no place reaches both
    _r = set()
    for _e in entries(_k):
        if _e not in _r:
            _r |= reach(_g, _e)
    for _c, _rr in LANTERNS[_k]:
        assert any(touch(_x, _y, _c, _rr) for _x, _y in _r), (_k, _c, _rr)
    for _x, _y in _r:
        _t = [touch(_x, _y, _c, _rr) for _c, _rr in LANTERNS[_k]]
        assert not all(_t), (_k, _x, _y)
        for (_c, _rr), _h in zip(LANTERNS[_k], _t):
            assert (((_x + (16 - 8 * _c)) & 255) < 25 and ((_y + (17 - 8 * _rr)) & 255) < 25) == _h
    assert not any(touch(_x, _y, _c, _rr) for _x, _y in entries(_k) for _c, _rr in LANTERNS[_k])

# ---------------------------------------------------------------- the shapes and colours
FLOOR, FLAG, RUG, BRICK, STONE, LANTERN = 0, 1, 2, 3, 4, 5
LIT = 6                                 # a lantern lit: a wall too
DARK = gen45.DARK
LIT_SHAPE = [0x54, 0x38, 0x7C, 0x7C, 0x7C, 0x7C, 0x7C, 0x00]
LIT_C = WHITE << 4 | DARK_BLUE          # white in the wall, where an unlit one is cyan
GLOW_C = WHITE << 4 | BLACK             # the map: a room with both lanterns lit, white on black
GUARD_C = DARK_BLUE                     # the explorer is black: two greys apart in print
PAPER_C, DARK_C = gen45.PAPER_C, gen45.DARK_C
MINI0, CURRENT = gen45.MINI0, gen45.CURRENT


_SHAPE_SET, _COLOUR_SET = gen45.shape_set, gen45.colour_set     # chapter 45's


def shape_set():
    """chapter 45's shapes, and the lantern lit's"""
    out = _SHAPE_SET()
    out[8 * LIT:8 * LIT + 8] = LIT_SHAPE
    return out


def colour_set():
    """chapter 45's colours, and the lantern lit's"""
    out = _COLOUR_SET()
    out[8 * LIT:8 * LIT + 8] = [LIT_C] * 8
    return out


def picture_colours(c):
    """a room's 12 names' colours on the map, the last line of the bottom
    four dark, as gen45.colour_set has them"""
    out = [c] * 96
    for n in range(8, 12):
        out[8 * n + 7] = DARK_C
    return out


assert colour_set()[8 * MINI0:8 * MINI0 + 96] == picture_colours(PAPER_C)


def d2(i, j):
    return (i - 7.5) ** 2 + (j - 7.5) ** 2


def guard_rows():
    """a guard seen from above: a helmet with a crest, a visor and its eyes,
    and a grille, 16 x 16"""
    rows = []
    for j in range(16):
        v = 0
        for i in range(16):
            ink = d2(i, j) <= 7.0 ** 2          # the helmet
            if i in (7, 8) and j <= 4:
                ink = False                     # the crest
            if j in (6, 7) and 3 <= i <= 12:
                ink = i in (5, 10)              # the visor, the eyes
            if j == 11 and 5 <= i <= 10:
                ink = False                     # the grille
            v |= ink << (15 - i)
        rows.append(v)
    return rows


GUARD = guard_rows()
EXPLORER = gen45.EXPLORER
SPRITE_PATTERNS = big(EXPLORER) + big(GUARD)    # patterns 0 to 3 the explorer, 4 to 7 a guard
GUARD_P = 4


def overlaps(a, b):
    """{(dx, dy)}: where sprite B, DX pixels right of A and DY lines below
    it, shares a pixel with it"""
    out = set()
    for dy in range(-15, 16):
        for dx in range(-15, 16):
            for j in range(16):
                jb = j - dy
                if 0 <= jb < 16:
                    ra = a[j] << 16
                    rb = b[jb] << (16 - dx)
                    if ra & rb:
                        out.add((dx, dy))
                        break
    return out


MEETS = overlaps(EXPLORER, GUARD)       # where a guard touches the explorer

# ---------------------------------------------------------------- the screens
STATUS = [(1, "LIT"), (7, "/32"), (11, "LIVES"), (19, "TIME")]
LIT_AT, LIVES_AT, TIME_AT, ROOM_AT = 5, 17, 24, 29
TITLE_BOX = gen45.TITLE_BOX
TITLE_TEXT = [(10, 6, NAME), (5, 14, "LIGHT ALL 32 LANTERNS"), (11, 16, "HI"),
              (10, 18, "PRESS SPACE"), (3, 20, "CURSOR KEYS OR JOYSTICK 1"),
              (5, 22, "M OR BUTTON B: THE MAP")]
TITLE_HI = (14, 16)                     # the best score's six digits
TITLE_LAMPS = gen45.TITLE_LAMPS
TITLE_EXPLORER = (56, 87)               # X, Y: lines 88 to 103, below the wall
TITLE_GUARD = (H, 87, 104, 200, 152, 1)  # and a guard walking its round beside it
BOX_COL, BOX_ROW, BOX_W, BOX_H = 4, 9, 24, 5   # the end's box: bricks round 22 x 3 cells
OVER_TEXT, WIN_TEXT = "GAME OVER", "THE KEEP IS LIT"
SCORE_TEXT = "SCORE        HI       "   # the box's third row: six digits after each word
SCORE_DIG, HI_DIG = (BOX_COL + 7, BOX_ROW + 3), (BOX_COL + 17, BOX_ROW + 3)
assert abs(TITLE_GUARD[2] - TITLE_EXPLORER[0]) > 16


def row0():
    """the status line as a game begins: LIT 00/32, LIVES 3, TIME 999"""
    out = [32] * 32
    for col, text in STATUS:
        out[col:col + len(text)] = [ord(c) for c in text]
    out[LIT_AT:LIT_AT + 2] = [0x30, 0x30]
    out[LIVES_AT] = 0x30 + LIVES
    out[TIME_AT:TIME_AT + 3] = [0x30 + 9] * 3
    return out


def title_names():
    """the title's 768 names: the status line, a wall with the name and two
    lit lanterns inside it, and the lines to read"""
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
        out[32 * row + col] = LIT
    return out


def box_names(text):
    """the end's box, 5 rows of 24 names: a wall of bricks round three rows,
    TEXT in the first, the score's and the best's words in the third"""
    out = []
    inner = BOX_W - 2
    for r in range(BOX_H):
        if r in (0, BOX_H - 1):
            out += [BRICK] * BOX_W
            continue
        line = {1: (" " * ((inner - len(text)) // 2) + text).ljust(inner), 2: " " * inner,
                3: SCORE_TEXT}[r]
        out += [BRICK] + [ord(c) for c in line] + [BRICK]
    return out


assert len(box_names(OVER_TEXT)) == 120 == len(box_names(WIN_TEXT)) and len(SCORE_TEXT) == BOX_W - 2
assert SCORE_TEXT[SCORE_DIG[0] - BOX_COL - 1 - 1] == " " and SCORE_TEXT.index("HI") == HI_DIG[0] - BOX_COL - 4
assert SCORE_TEXT[HI_DIG[0] - BOX_COL - 1:] == " " * 6 and SCORE_TEXT[6:12] == " " * 6


def first_copy():
    """the explorer at its first place"""
    return [HOME[1], HOME[0], 0, gen45.EXPLORER_C]


def title_copy():
    """the title's sprites: the explorer, a guard, guard 1 hidden, the end"""
    return [TITLE_EXPLORER[1], TITLE_EXPLORER[0], 0, gen45.EXPLORER_C,
            TITLE_GUARD[1], TITLE_GUARD[4], GUARD_P, GUARD_C,
            0xD0, 0, GUARD_P, GUARD_C, 0xD0]


# ---------------------------------------------------------------- the RAM
VARS_AT = 0xC100
COPY_AT = VARS_AT + 0x40
ENGINE_AT = 0xC000
RAM = f"""stat    EQU VARS                ; the status isr read: F, 5S, C, a sprite's number
ticks   EQU VARS + 1            ; frames counted by isr, two bytes
state   EQU VARS + 3            ; TITLE, PLAY, FLIP, MAP, HIT, OVER or WIN
held    EQU VARS + 4            ; the keys and the stick: a 0 for each held
was     EQU VARS + 5            ; held as the loop before found it
room    EQU VARS + 6            ; the room the explorer is in, 0 to 15
lives   EQU VARS + 7            ; the lives left
fresh   EQU VARS + 8            ; 1: the room just come into had not been seen
queued  EQU VARS + 9            ; the names queued for the sends
keepy   EQU VARS + 10           ; the explorer's Y while the map is shown
whole   EQU VARS + 11           ; 1: the sends send a whole page
wsrc    EQU VARS + 12           ; its rows 1 to 23, two bytes
wr3     EQU VARS + 14           ; and R#3 and R#4 to show it with
wr4     EQU VARS + 15
queue   EQU VARS + $10          ; 16 names: the VRAM address, then the name
copy    EQU VARS + $40          ; the sprites' attributes: Y, X, pattern, colour
explorer EQU copy               ; the explorer's,
guard0  EQU copy + 4            ; the room's two guards',
guard1  EQU copy + 8
gd      EQU VARS + $50          ; and the guards' rounds, four bytes each
due     EQU VARS + $58          ; lines owed to the game's steps, two bytes
nlit    EQU VARS + $5A          ; the lanterns lit, BCD
time    EQU VARS + $5B          ; the time: its hundreds, then a BCD pair
tock    EQU VARS + $5D          ; steps to the next unit of time
left    EQU VARS + $5E          ; the steps left of HIT, OVER or WIN
dimmed  EQU VARS + $5F          ; the rooms of the map unlit again at the end
back    EQU VARS + $60          ; where the explorer came into the room: Y, X
been    EQU VARS + $70          ; a byte a room: 1 when seen
lit     EQU VARS + $80          ; a byte a lantern: 1 when lit
score   EQU VARS + $A0          ; three BCD bytes (chapter 40)
hi      EQU score + 3           ; the best, three more
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
names   EQU ${gen45.NAMES_AT:04X}               ; the copy of the 768 names
mapn    EQU ${gen45.MAPN_AT:04X}               ; the map's page, rows 1 to 23
minis   EQU ${gen45.MINIS_AT:04X}               ; the rooms' pictures, 96 bytes each
"""
QUEUE_MAX = gen45.QUEUE_MAX

CONSTS = f"""SAT     EQU $1B00               ; the sprites' attributes
SPAT    EQU $3800               ; and their patterns
TITLE   EQU 0                   ; the states
PLAY    EQU 1
FLIP    EQU 2
MAP     EQU 3
HIT     EQU 4
OVER    EQU 5
WIN     EQU 6
FLOOR   EQU {FLOOR}                   ; the tiles' names: from BRICK up, a wall
FLAG    EQU {FLAG}
RUG     EQU {RUG}
BRICK   EQU {BRICK}
STONE   EQU {STONE}
LANTERN EQU {LANTERN}
LIT     EQU {LIT}                   ; a lantern lit
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
GAME_R3 EQU ${gen45.GAME_R3:02X}               ; R#3 and R#4 of the play: one set for three thirds
GAME_R4 EQU ${gen45.GAME_R4:02X}
MAP_R3  EQU ${gen45.MAP_R3:02X}               ; and of the map: a set for each
MAP_R4  EQU ${gen45.MAP_R4:02X}
LIVES   EQU {LIVES}
STILL   EQU {STILL}                  ; steps held still at a touch
ENDS    EQU {ENDS}                 ; steps of the end
TICKS   EQU {TICKS}                  ; steps for each unit of time
LAMPS   EQU ${LAMPS:02}                 ; the lanterns, BCD
LIT_AT  EQU {LIT_AT}                   ; row 0: the lanterns lit,
LIVES_AT EQU {LIVES_AT}                 ; the lives,
TIME_AT EQU {TIME_AT}                  ; the time
ROOM_AT EQU {ROOM_AT}                  ; and the room's name
BOX_AT  EQU $1800 + 32 * {BOX_ROW} + {BOX_COL}  ; the end's box
SCORE_AT EQU $1800 + 32 * {SCORE_DIG[1]} + {SCORE_DIG[0]} ; and the score's digits in it,
HI_AT   EQU $1800 + 32 * {HI_DIG[1]} + {HI_DIG[0]} ; the best's,
THI_AT  EQU $1800 + 32 * {TITLE_HI[1]} + {TITLE_HI[0]} ; and the best's on the title
"""

# ---------------------------------------------------------------- the frame
ISR = """
; isr: every frame. The status kept in stat, the signal let down; the frame
; counted, and its lines owed to the game's steps; the keys and the stick read
; while the frame is young; then chapter 37's player: when pace gives it a
; tick, last tick's registers to the PSG first, then the next tick: at the
; title the tune, and in every other state hush, the sounds alone. Keeps
; every register it uses
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
        ld a, (state)           ; 14
        or a                    ;  5  TITLE?
        jr nz, .hush            ; 13, or 8
        call play               ; 18  the tune
        jr .done                ; 13
.hush:  call hush               ; 18  the sounds alone
.done:  pop ix                  ; 16
        pop hl                  ; 11
        pop de                  ; 11
        pop bc                  ; 11
        pop af                  ; 11
isrend: ei                      ;  5
        ret                     ; 11
"""

HUSH = """
; hush: a tick with the music silent: the three channels' levels 0, every
; tone and noise shut, and a sound of the game's, if one is sounding, over
; channel C, as play has it. Uses A, BC, DE, HL, IX
hush:   ld a, $BF               ;  8  all shut; bit 7 at 1, bit 6 at 0
        ld hl, shadow + 7       ; 11
        ld (hl), a              ;  8
        xor a                   ;  5
        inc l                   ;  5
        ld (hl), a              ;  8  R8, A's level
        inc l                   ;  5
        ld (hl), a              ;  8  R9, B's
        inc l                   ;  5
        ld (hl), a              ;  8  R10, C's
        ld ix, chan_x           ; 16  a sound?
        ld a, (ix + WAITS)      ; 21  its ticks still to sound
        or a                    ;  5
        ret z                   ; 12, or 6  none
        dec (ix + WAITS)        ; 25
        jp sound                ; 11  whose RET is hush's

; retune: the tune from its first bar, as INIT leaves the player, and no
; sound of the game's: shadow and the four channels from start. The
; interrupts must be off. Uses A, BC, DE, HL
retune: ld a, 1                 ;  8  the first tick reads a row
        ld (tick), a            ; 14
        xor a                   ;  5
        ld (barno), a           ; 14
        ld (rowno), a           ; 14
        ld hl, song - 6         ; 11  the step before the first
        ld (songp), hl          ; 17
        ld hl, start            ; 11  shadow and the four channels
        ld de, shadow           ; 11
        ld bc, {start_bytes}           ; 11
        ldir                    ; 23 a byte, 18 the last
        ret                     ; 11
""".format(start_bytes=gen37.START_BYTES)
assert "(shadow + 7)" not in HUSH and gen37.SHADOW_REGS == 11

SENDS = gen45.SENDS.replace(
    """; sends: straight after HALT, before the paper: the explorer's attributes,
; the names the frame before queued, and the whole page if one was left.""",
    """; sends: straight after HALT, before the paper: the sprites' attributes,
; the names the frame before queued, and the whole page if one was left.""").replace(
    """        ld bc, 5 << 8 | VDP_DATA ; 11  the explorer and the end""",
    """        ld bc, 13 << 8 | VDP_DATA ; 11  the explorer, the guards, the end""")
assert SENDS.count("13 << 8") == 1 and "sprites' attributes,\n; the names" in SENDS

GUARD_RT = """
; greset: the room's guards at the start of their rounds, from gtab, twelve
; bytes a room: for each guard its Y and X, then its round. Uses A, BC, DE,
; HL
greset: ld a, (room)            ; 14
        add a, a                ;  5
        add a, a                ;  5
        ld c, a                 ;  5
        add a, a                ;  5
        add a, c                ;  5  twelve bytes a room
        ld l, a                 ;  5
        ld h, high gtab         ;  8  the table at a page's start
        ld de, guard0           ; 11
        ldi                     ; 18
        ldi                     ; 18  guard 0's Y and X
        ld de, gd               ; 11
        ldi                     ; 18
        ldi                     ; 18
        ldi                     ; 18
        ldi                     ; 18  and its round
        ld de, guard1           ; 11
        ldi                     ; 18
        ldi                     ; 18  guard 1's
        ld de, gd + 4           ; 11
        ldi                     ; 18
        ldi                     ; 18
        ldi                     ; 18
        ldi                     ; 18
        ret                     ; 11

; guards: a step of the room's two guards, each on its round. Uses A, BC,
; DE, HL
guards: ld hl, gd               ; 11  guard 0's round
        call patrol             ; 18
        ld hl, gd + 4           ; 11  and guard 1's
; patrol: HL = a guard's round, four bytes: where in the copy its Y or its X
; is, the least, the places of the round and its step -> a step on; a step
; past either end turns it, and it steps the other way instead. Uses A, BC,
; DE, HL
patrol: ld e, (hl)              ;  8  its Y or its X, in the copy's page
        ld d, high copy         ;  8
        inc l                   ;  5
        ld b, (hl)              ;  8  B: the least
        inc l                   ;  5
        ld c, (hl)              ;  8  C: the places, most - least + 1
        inc l                   ;  5  HL: its step
        ld a, (de)              ;  8  where it is
        add a, (hl)             ;  8  a step on
        sub b                   ;  5
        cp c                    ;  5  carry: still on its round
        jr c, .put              ; 13, or 8
        ld a, (hl)              ;  8
        neg                     ; 10
        ld (hl), a              ;  8  the other way
        ex de, hl               ;  5
        add a, (hl)             ;  8  from where it is
        ex de, hl               ;  5
        sub b                   ;  5
.put:   add a, b                ;  5
        ld (de), a              ;  8
        ret                     ; 11
"""


def flip_rt(late=False):
    """flip0 and flip1; in late.asm (LATE) greset is called by flip1"""
    reset0 = "" if late else "        call greset             ; 18  its guards at their first places\n"
    say0 = ("; flip0: THE ROOM CHANGES. Its runs unpacked into the copy of the names, and\n"
            "; its lanterns that are lit lit there; its name posted for row 0; seen;\n"
            + ("; WHERE IT BREAKS: its guards left where they were; " if late else
               "; its guards at their first places; ") +
            "the explorer's place kept for\n; a touch; and the whole page left for "
            "the next frame's sends\n")
    if late:
        flip1 = """
; flip1: the page sent: WHERE IT BREAKS, the room's guards at their first
; places only now, and the play again
flip1:  call greset             ; 18  a loop late
        ld a, PLAY              ;  8
        jp go                   ; 11
"""
    else:
        flip1 = """
; flip1: the page sent, with the sprites: the play again
flip1:  ld a, PLAY              ;  8
        jp go                   ; 11
"""
    return ("\n" + say0 + """flip0:  ld a, (room)            ; 14
        call unpack             ; 18  rows 1 to 23 of the copy
        call lights             ; 18  its lanterns lit
        call rname              ; 18  row 0: its name
        call visit              ; 18
""" + reset0 + """        ld hl, (explorer)       ; 17  Y, then X
        ld (back), hl           ; 17  where it came in
        ld hl, names + 32       ; 11
        ld de, GAME_R4 << 8 | GAME_R3 ; 11
        jp page                 ; 11  for the next sends
""" + flip1 + RNAME + VISIT)


RNAME = gen45.FLIP_RT[gen45.FLIP_RT.index("; rname:"):gen45.FLIP_RT.index("; visit:")]
VISIT = """; visit: the room seen, and the first time fresh, for play1 to make its
; picture. Uses A, HL
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
        ret                     ; 11
"""
assert RNAME.startswith("; rname:") and "ROOM_AT" in RNAME

LAMP_RT = """
; lights: the room's lanterns that are lit, LIT in the copy of the names.
; Uses A, C, HL
lights: ld a, (room)            ; 14
        add a, a                ;  5  its first lantern's number
        ld c, a                 ;  5
        call .one               ; 18
        inc c                   ;  5  and its second
.one:   ld hl, lit              ; 11
        ld a, l                 ;  5
        add a, c                ;  5
        ld l, a                 ;  5  lit in one page
        ld a, (hl)              ;  8
        or a                    ;  5
        ret z                   ; 12, or 6  not lit
        ld a, c                 ;  5
        add a, a                ;  5
        add a, a                ;  5  four bytes a lantern
        add a, 2                ;  8  the third: its cell
        ld l, a                 ;  5
        ld h, high ltab         ;  8  the table at a page's start
        ld a, (hl)              ;  8
        inc l                   ;  5
        ld h, (hl)              ;  8
        ld l, a                 ;  5
        ld (hl), LIT            ; 11
        ret                     ; 11

; lamps: the room's two lanterns against the explorer, and the keep lit
; when the last is. Uses every register but IY
lamps:  ld a, (room)            ; 14
        add a, a                ;  5
        ld c, a                 ;  5  its first lantern
        call lamp               ; 18
        inc c                   ;  5  and its second
        call lamp               ; 18
        ld a, (nlit)            ; 14
        cp LAMPS                ;  8
        ret nz                  ; 12, or 6
        ld a, WIN               ;  8
        jp go                   ; 11  every lantern lit

; lamp: C = a lantern's number -> lit, if it is not yet and the explorer's
; pixels reach its cell or a pixel round it: its cell LIT, posted; a hundred
; points; one more lit, posted; its sound; and its room lit on the map when
; its other lantern is lit too. Keeps C. Uses A, B, DE, HL, IX
lamp:   ld hl, lit              ; 11
        ld a, l                 ;  5
        add a, c                ;  5
        ld l, a                 ;  5  lit in one page
        ld a, (hl)              ;  8
        or a                    ;  5
        ret nz                  ; 12, or 6  lit already
        ex de, hl               ;  5  DE: its byte in lit
        ld a, c                 ;  5
        add a, a                ;  5
        add a, a                ;  5  four bytes a lantern
        ld l, a                 ;  5
        ld h, high ltab         ;  8
        ld a, (explorer + 1)    ; 14  X
        add a, (hl)             ;  8  X - 8 x its column + 16
        cp 25                   ;  8
        ret nc                  ; 12, or 6  too far left or right
        inc l                   ;  5
        ld a, (explorer)        ; 14  Y, the first line less 1
        add a, (hl)             ;  8  Y + 1 - 8 x its row + 16
        cp 25                   ;  8
        ret nc                  ; 12, or 6  too far up or down
        inc l                   ;  5
        ld a, (hl)              ;  8
        inc l                   ;  5
        ld h, (hl)              ;  8
        ld l, a                 ;  5  HL: its cell in the copy
        ld a, 1                 ;  8
        ld (de), a              ;  8  lit
        push bc                 ; 12
        ld a, LIT               ;  8
        call post               ; 18  its cell, queued
        ld a, $10               ;  8  ten tens
        call addten             ; 18  a hundred points (chapter 44)
        ld a, (nlit)            ; 14
        add a, 1                ;  8
        daa                     ;  5  one more, in BCD
        ld (nlit), a            ; 14
        ld hl, names + LIT_AT   ; 11
        call post2              ; 18  its two digits
        ld a, S_LAMP            ;  8
        call fx                 ; 18  its sound
        pop bc                  ; 11
        ld a, c                 ;  5
        and $FE                 ;  8  the room's first lantern
        ld hl, lit              ; 11
        add a, l                ;  5
        ld l, a                 ;  5
        ld a, (hl)              ;  8
        inc l                   ;  5
        and (hl)                ;  8  NZ: both lit
        ret z                   ; 12, or 6
        ld a, (room)            ; 14
; glow: A = a room -> its twelve names on the map lit. Uses A, BC, DE, HL
glow:   ld hl, glowc            ; 11  a lit room's colours
; colours: A = a room, HL = 96 colours -> its twelve names' colours on the
; map, in its third, at 29 T-states a byte (chapter 20): where the play's
; screen never looks. Uses A, BC, DE, HL
colours: add a, a               ;  5  two bytes a room
        add a, low piccol       ;  8
        ld e, a                 ;  5
        ld d, high piccol       ;  8  the table in one page
        ld a, (de)              ;  8
        di                      ;  5
        out (VDP_CTRL), a       ; 12
        inc e                   ;  5
        ld a, (de)              ;  8
        out (VDP_CTRL), a       ; 12  the address
        ei                      ;  5
        ld bc, 96 << 8 | VDP_DATA ; 11
.byte:  outi                    ; 18
        jp nz, .byte            ; 11
        ret                     ; 11

; dim: a room more of the map back to unlit, one a loop, sixteen in all,
; while the end is shown. Uses A, BC, DE, HL
dim:    ld a, (dimmed)          ; 14
        cp 16                   ;  8
        ret nc                  ; 12, or 6  all sixteen
        inc a                   ;  5
        ld (dimmed), a          ; 14
        dec a                   ;  5
        ld hl, dimc             ; 11  an unlit room's colours
        jr colours              ; 13
"""

CLOCK = """
; clock: a step of the time: every TICKS steps a unit fewer, its three
; digits posted -> Z when none is left. Uses A, BC, DE, HL
clock:  ld hl, tock             ; 11
        dec (hl)                ; 12
        ret nz                  ; 12, or 6  NZ: no unit yet
        ld (hl), TICKS          ; 11
        ld hl, time + 1         ; 11  the tens and the units
        ld a, (hl)              ;  8
        sub 1                   ;  8
        daa                     ;  5  a unit fewer, in BCD (chapter 9)
        ld (hl), a              ;  8
        dec hl                  ;  7  the hundreds
        ld a, (hl)              ;  8
        sbc a, 0                ;  8  less the borrow
        ld (hl), a              ;  8
        add a, DIGIT0           ;  8
        ld hl, names + TIME_AT  ; 11
        call post               ; 18  its digit
        ld a, (time + 1)        ; 14
        ld hl, names + TIME_AT + 1 ; 11
        call post2              ; 18  and the other two
        ld a, (time)            ; 14
        ld hl, time + 1         ; 11
        or (hl)                 ;  8  Z: 000
        ret                     ; 11
"""

PLAY_RT = """
; play0: no steps owed yet, and no keys pressed
play0:  ld hl, 0                ; 11
        ld (due), hl            ; 17
        ld a, (held)            ; 14
        ld (was), a             ; 14
        ret                     ; 11

; play1: THE FRAME OF THE PLAY. A room seen for the first time gets its
; picture for the map, a frame of its own; C, which isr kept from the frame
; the sends before drew, is a guard's touch; M or button B pressed shows the
; map; else, for each step owed, a step of the explorer, out of the room
; when it goes through a door, a step of each guard, and of the time, which
; at none ends the game; then the lanterns the explorer reaches. Uses every
; register but IY
play1:  ld a, (fresh)           ; 14
        or a                    ;  5
        jr z, .look             ; 13, or 8
        call mini               ; 18  its picture
        jp play0                ; 11  and the frame counts as none
.look:  ld a, (stat)            ; 14
        and $20                 ;  8  C: two sprites met
        ld a, HIT               ;  8
        jp nz, go               ; 11  a guard touched the explorer
        call presses            ; 18
        and $20                 ;  8  M or button B
        jr nz, tomap            ; 13, or 8
        call paced              ; 18  B: the steps owed (chapter 44)
.step:  push bc                 ; 12
        call walk               ; 18  carry: out, by D's way
        pop bc                  ; 11
        jp c, leave             ; 11  through a door
        push bc                 ; 12
        call guards             ; 18
        call clock              ; 18  Z: no time left
        pop bc                  ; 11
        jr z, timeup            ; 13, or 8
        djnz .step              ; 14, or 9
        jp lamps                ; 11
timeup: ld a, OVER              ;  8
        jp go                   ; 11
tomap:  ld a, MAP               ;  8
        jp go                   ; 11

; hit0: A TOUCH. A life fewer, posted; its sound; and the game held still
hit0:   ld hl, lives            ; 11
        dec (hl)                ; 12
        ld a, (hl)              ;  8
        add a, DIGIT0           ;  8
        ld hl, names + LIVES_AT ; 11
        call post               ; 18  its digit
        ld a, STILL             ;  8
        ld (left), a            ; 14
        ld a, S_TOUCH           ;  8
        jp fx                   ; 11

; hit1: the steps owed off the wait, and at its end GAME OVER with no lives
; left, or else the explorer back where it came into the room, which is
; flipped again: its guards at their first places
hit1:   call countdown          ; 18
        ret nz                  ; 12, or 6
        ld a, (lives)           ; 14
        or a                    ;  5
        ld a, OVER              ;  8
        jp z, go                ; 11  no lives left
        ld hl, (back)           ; 17
        ld (explorer), hl       ; 17  Y and X
        ld a, FLIP              ;  8
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
"""

END_RT = """
; over0: GAME OVER: its sound, then the end
over0:  ld a, S_OVER            ;  8
        call fx                 ; 18
        ld hl, obox             ; 11  its box
        jr ending               ; 13

; win0: THE KEEP IS LIT: the time left added to the score, its tens and
; units, then its hundreds; its sound; then the end
win0:   ld a, (time + 1)        ; 14
        call addsc              ; 18  the tens and the units (chapter 40)
        ld a, (time)            ; 14  the hundreds, as tens of tens
        add a, a                ;  5
        add a, a                ;  5
        add a, a                ;  5
        add a, a                ;  5
        call addten             ; 18
        ld a, S_WIN             ;  8
        call fx                 ; 18
        ld hl, wbox             ; 11
; ending: HL = the end's box -> the sprites hidden, hi kept the best, the box
; on the screen with the score and the best, and ENDS steps of it, while
; the map's rooms are unlit again. Uses every register but IY
ending: ld a, $D0               ;  8
        ld (explorer), a        ; 14  the end of the sprites: none shown
        push hl                 ; 12
        call best               ; 18  hi kept the best (chapter 40)
        pop hl                  ; 11
        call box                ; 18
        ld a, ENDS              ;  8
        ld (left), a            ; 14
        xor a                   ;  5
        ld (dimmed), a          ; 14
        ret                     ; 11

; over1: the end's frame, OVER's and WIN's: a room of the map unlit, the
; steps owed off the wait, and at its end the title again
over1:  call dim                ; 18
        call countdown          ; 18
        ret nz                  ; 12, or 6
        ld a, TITLE             ;  8
        jp go                   ; 11

; box: HL = five rows of 24 names -> on the screen at BOX_AT, 29 T-states a
; name (chapter 20); then the score's six digits and the best's. Uses A, BC,
; DE, HL
box:    ld de, BOX_AT | $4000   ; 11
        ld a, 5                 ;  8  five rows
.row:   push af                 ; 12
        di                      ;  5
        ld a, e                 ;  5
        out (VDP_CTRL), a       ; 12
        ld a, d                 ;  5
        out (VDP_CTRL), a       ; 12  the row's first cell
        ei                      ;  5
        ld bc, 24 << 8 | VDP_DATA ; 11
.name:  outi                    ; 18
        jp nz, .name            ; 11
        ld a, e                 ;  5
        add a, 32               ;  8  the row below
        ld e, a                 ;  5
        jr nc, .page            ; 13, or 8
        inc d                   ;  5
.page:  pop af                  ; 11
        dec a                   ;  5
        jr nz, .row             ; 13, or 8
        ld hl, score            ; 11
        ld de, SCORE_AT | $4000 ; 11
        call put3               ; 18
        ld hl, hi               ; 11
        ld de, HI_AT | $4000    ; 11
; put3: HL = three BCD bytes, DE = the VRAM address of the first digit, plus
; $4000 -> the six digits sent (chapter 42's putbcd). Uses A, BC, HL
put3:   di                      ;  5
        ld a, e                 ;  5
        out (VDP_CTRL), a       ; 12
        ld a, d                 ;  5
        out (VDP_CTRL), a       ; 12
        ei                      ;  5
        ld b, 3                 ;  8
.byte:  ld a, (hl)              ;  8
        call putbcd             ; 18
        inc hl                  ;  7
        djnz .byte              ; 14, or 9
        ret                     ; 11
"""

STATES_RT = """
; title0: the title's 768 names at 29 T-states a name (chapter 20) and the
; best score in them; the explorer, and a guard on its round; and the tune
; from its first bar
title0: di                      ;  5
        call retune             ; 18  the tune again
        VRAM_WRITE $1800        ; 40
        ei                      ;  5
        ld hl, tnames           ; 11  in the second half
        ld bc, VDP_DATA         ; 11  B: 0, a run of 256; C: the port
        ld d, 3                 ;  8  three runs
.run:   outi                    ; 18
        jp nz, .run             ; 11
        dec d                   ;  5
        jr nz, .run             ; 13, or 8
        ld hl, hi               ; 11
        ld de, THI_AT | $4000   ; 11
        call put3               ; 18  the best's six digits
        ld hl, tcopy            ; 11  the sprites, and the end
        ld de, copy             ; 11
        ld bc, 13               ; 11
        ldir                    ; 23 a byte, 18 the last
        ld hl, tround           ; 11  and the guard's round
        ld de, gd               ; 11
        ld bc, 4                ; 11
        ldir                    ; 23 a byte, 18 the last
        ret                     ; 11

; title1: the guard a step on its round for each step owed; SPACE or button
; A held? A game begins, with the flip into its first room
title1: call paced              ; 18
.step:  push bc                 ; 12
        ld hl, gd               ; 11
        call patrol             ; 18
        pop bc                  ; 11
        djnz .step              ; 14, or 9
        ld a, (held)            ; 14  isr read them
        and $10                 ;  8  SPACE, button A
        ret nz                  ; 12, or 6
pressed: call setup             ; 18  a new game
        ld a, FLIP              ;  8
        jp go                   ; 11

; setup: a new game. No names queued, no rooms seen, no lantern lit; score
; 0, LIVES lives, the time full; the explorer in the gate hall at its first
; place
setup:  xor a                   ;  5
        ld (queued), a          ; 14
        ld (nlit), a            ; 14
        ld hl, been             ; 11  been and lit, 48 bytes
        ld b, 48                ;  8
.none:  ld (hl), a              ;  8
        inc l                   ;  5
        djnz .none              ; 14, or 9
        ld hl, score            ; 11
        ld (hl), a              ;  8
        inc l                   ;  5
        ld (hl), a              ;  8
        inc l                   ;  5
        ld (hl), a              ;  8
        ld a, LIVES             ;  8
        ld (lives), a           ; 14
        ld hl, {time0}           ; 11  the hundreds 9, then 99
        ld (time), hl           ; 17
        ld a, TICKS             ;  8
        ld (tock), a            ; 14
        ld a, START             ;  8
        ld (room), a            ; 14
        ld hl, first            ; 11  the explorer's first place
        ld de, copy             ; 11
        ld bc, 4                ; 11
        ldir                    ; 23 a byte, 18 the last
        ret                     ; 11
""".format(time0=f"${TIME0[1]:02X}{TIME0[0]:02X}")
SETS = gen45.STATES_RT[gen45.STATES_RT.index("; sets:"):]
assert SETS.startswith("; sets:") and "set2k:" in SETS


def setup_lines():
    """the cartridge's start: chapter 45's, the player set up too (chapter
    44's way), the guard's patterns, and the best score to beat"""
    base = gen45.setup_lines()
    rate = gen45.gen33.rate("lines", 262, 313)
    assert base.count(rate) == 1
    engine = (gen37.init_lines().replace("ld (ticks), hl", "ld (beats), hl")
              .replace("ld (step), hl", "ld (songp), hl")
              .replace("        ld (frames), a\n", ""))
    assert "(frames)" not in engine and "(beats)" in engine and "(songp)" in engine
    out = base.replace(rate, """        ld hl, ENGINE           ; the player's page, all 0
        ld de, ENGINE + 1
        ld bc, 255
        ld (hl), 0
        ldir
""" + engine + """        ld hl, hstart           ; the best to beat
        ld de, hi
        ld bc, 3
        ldir
""")
    old = """        VRAM_WRITE SPAT         ; the explorer, patterns 0 to 3
        ld hl, sprites
        ld bc, 32 << 8 | VDP_DATA
        otir
"""
    assert out.count(old) == 1
    out = out.replace(old, """        VRAM_WRITE SPAT         ; the explorer, patterns 0 to 3, a guard 4 to 7
        ld hl, sprites
        ld bc, 64 << 8 | VDP_DATA
        otir
""")
    return out


def gtab(guards=None):
    """greset's table: for each room, for each guard its Y and X at the
    start, then its round: the low byte of its Y's or its X's place in the
    copy, the least, the places of the round, its step; a room with one
    guard has a second at Y $D0, the end of the sprites, that never moves"""
    out = []
    for k, gs in enumerate(guards or GUARDS):
        for slot in range(2):
            at = COPY_AT + 4 + 4 * slot
            if slot < len(gs):
                axis, fixed, lo, hi, start, step = gs[slot]
                x, y = place_of(gs[slot], start)
                out += [y, x, (at + (1 if axis == H else 0)) & 255, lo, hi - lo + 1, step & 255]
            else:
                out += [0xD0, 0, at & 255, 0xD0, 1, 0]
    assert len(out) == 12 * ROOMS
    return out


def tround():
    axis, fixed, lo, hi, start, step = TITLE_GUARD
    return [(COPY_AT + 4 + (1 if axis == H else 0)) & 255, lo, hi - lo + 1, step & 255]


def piccol():
    """each room's twelve names' colours on the map, + $4000"""
    return [0x2000 + a for a in gen45.picvram()]


def data(guards=None):
    word_rows = gen45.word_rows
    return ("""codeend:                        ; the code ends here
        ALIGN 16
starts:                         ; each state's first frame
        dw title0, play0, flip0, map0, hit0, over0, win0
        ALIGN 16
frames:                         ; and every frame of it
        dw title1, play1, flip1, map1, hit1, over1, over1
        ALIGN 16
ways:                           ; leave's: the room's change, Y or X, the edge
""" + db_rows(gen45.ways(), 3) +
            "        ALIGN 32\nmapat:                          ; each room's first cell in mapn\n" +
            word_rows(gen45.mapat()) +
            "picvram:                        ; each room's names' shapes in its third, + $4000\n" +
            word_rows(gen45.picvram()) +
            "curvram:                        ; and those of CURRENT in its third, + $4000\n" +
            word_rows(gen45.curvram()) +
            "piccol:                         ; each room's names' colours in its third, + $4000\n" +
            word_rows(piccol()) +
            "mapnm:                          ; each room's first name on the map\n" +
            db_rows([gen45.mini_name(k) for k in range(ROOMS)]) +
            "first:                          ; the explorer at its first place\n" +
            db_rows(first_copy()) +
            "tcopy:                          ; the title's sprites, and the end\n" + db_rows(title_copy()) +
            "tround:                         ; and its guard's round\n" + db_rows(tround()) +
            "hstart:                         ; the best score at the start\n" + db_rows(HI_START) +
            "glowc:                          ; a lit room's colours on the map\n" +
            db_rows(picture_colours(GLOW_C), 16) +
            "dimc:                           ; and an unlit room's\n" +
            db_rows(picture_colours(PAPER_C), 16) +
            "obox:                           ; GAME OVER's box\n" + db_rows(box_names(OVER_TEXT), 12) +
            "wbox:                           ; and THE KEEP IS LIT's\n" + db_rows(box_names(WIN_TEXT), 12) +
            "sprites:                        ; the explorer and a guard, 16 x 16 (chapter 26)\n" +
            db_rows(SPRITE_PATTERNS) +
            "        ALIGN 16\nkbdjoy:                         ; register 14's bits 0-3 for "
            "the cursor keys\n" + db_rows(gen35.kbd_table(), 16) +
            "        ALIGN 256\nltab:                           ; lamp's: X's and Y's sums, the "
            "cell\n" + db_rows(ltab()) +
            "        ALIGN 256\ngtab:                           ; greset's: each room's two guards\n" +
            db_rows(gtab(guards), 12) + gen37.start_data())


def second_half():
    """chapter 45's second half, with this chapter's title and sets"""
    keep = gen45.title_names, gen45.shape_set, gen45.colour_set
    try:
        gen45.title_names, gen45.shape_set, gen45.colour_set = title_names, shape_set, colour_set
        return gen45.second_half()
    finally:
        gen45.title_names, gen45.shape_set, gen45.colour_set = keep


# ---------------------------------------------------------------- the tune
# the title's tune, the book's own: sixteen notes in A minor in seven bars of
# three beats and a bar's rest, for the melody on channel A; a bass on B,
# the root, the fifth and the octave, and in the last bar E's chord, leading
# back to the A of the first; and on C the chord as an arpeggio on the second
# beat and the third. A beat is two rows of SPEED ticks
SPEED = 6
BAR_ROWS = 6
MELODY = {"m1": "A5 2 C6 2 E6 2", "m2": "A6 4 G6 2", "m3": "E6 2 D6 4",
          "m4": "E6 2 C6 2 A5 2", "m5": "B5 2 C6 4", "m6": "E6 2 D6 2 B5 2",
          "m7": "A5 6", "m8": "- 6"}
BASS = {"bAm": "A2 2 E3 2 A3 2", "bC": "C3 2 G3 2 C4 2", "bG": "G2 2 D3 2 G3 2",
        "bF": "F2 2 C3 2 F3 2", "bE": "E2 2 B2 2 E3 2", "bE7": "E2 2 Gs2 2 B2 2"}
CHORDS = {"cAm": ("MINOR", "A3"), "cC": ("MAJOR", "C4"), "cG": ("MAJOR", "G3"),
          "cF": ("MAJOR", "F3"), "cE": ("MAJOR", "E3")}
SONG = [("m1", "bAm", "cAm"), ("m2", "bC", "cC"), ("m3", "bG", "cG"),
        ("m4", "bAm", "cAm"), ("m5", "bF", "cF"), ("m6", "bE", "cE"),
        ("m7", "bAm", "cAm"), ("m8", "bE7", "cE")]
# the game's four sounds: an instrument, a note, its ticks and a priority
# (chapter 37's effects), with chapter 44's fanfare and sink
SOUNDS = [("S_LAMP", 1, "BELL", "G6", 18),       # a lantern lit
          ("S_TOUCH", 3, "BLAST", "C2", 20),     # a guard's touch
          ("S_WIN", 4, "FANFARE", "C5", 30),     # the keep lit
          ("S_OVER", 4, "SINK", "G4", 40)]       # GAME OVER
SOUND = {name: k for k, (name, *_) in enumerate(SOUNDS)}
TUNE_NOTES = [n for k in sorted(MELODY, key=lambda s: int(s[1:])) for n in MELODY[k].split()[::2]
              if n != "-"]
assert len(TUNE_NOTES) == 16 and TUNE_NOTES[0] == "A5" and TUNE_NOTES[-1] == "A5"


def patterns():
    """{name: [(instrument or None, note, rows)]}, music37's form"""
    raw = {}
    for name, text in MELODY.items():
        raw[name] = music37.bar("LEAD", text)
    for name, text in BASS.items():
        raw[name] = music37.bar("BASS", text)
    for name, (instr, n) in CHORDS.items():
        raw[name] = [[instr, None, 2], [None, n, 2], [None, n, 2]]
    out = {}
    for name, events in raw.items():
        last, evs = None, []
        for instr, n, rows in events:
            k = None if instr is None or instr == last else music37.INSTR[instr]
            if instr is not None:
                last = instr
            evs.append((k, 0 if n is None else music37.note(n), rows))
        assert sum(r for _, _, r in evs) == BAR_ROWS, (name, evs)
        out[name] = evs
    return out


TUNE_TICKS = len(SONG) * BAR_ROWS * SPEED       # the tune, once through


def with_music(fn):
    """FN run with music37 holding this chapter's music"""
    keep = (music37.INSTRUMENTS, music37.EFFECTS, music37.INSTR, music37.SPEED,
            music37.SONG, music37.patterns)
    try:
        music37.INSTRUMENTS = list(keep[0]) + gen44.NEW_INSTRUMENTS
        music37.INSTR = {name: k for k, (name, *_) in enumerate(music37.INSTRUMENTS)}
        music37.EFFECTS = SOUNDS
        music37.SPEED = SPEED
        music37.SONG = SONG
        music37.patterns = patterns
        return fn()
    finally:
        (music37.INSTRUMENTS, music37.EFFECTS, music37.INSTR, music37.SPEED,
         music37.SONG, music37.patterns) = keep


def music_inc():
    """music.inc: this chapter's tune and sounds, chapter 37's way"""
    text = with_music(gen37.music_inc)
    old = ("; music.inc -- chapter 37: the book's tune, its instruments and the\n"
           "; effects; generated by gen37.py from music37.py\n")
    assert text.startswith(old)
    return ("; music.inc -- chapter 46: the title's tune, chapter 37's instruments and\n"
            "; chapter 44's, and the game's four sounds; generated by gen46.py\n") + text[len(old):]


# ---------------------------------------------------------------- the program
SAY = {
    "game": """; LANTERN KEEP, finished: thirty-two lanterns to light in the sixteen rooms,
; twenty-eight guards on their rounds, whose touch the C bit tells, three
; lives, the time, the score and the best, and a tune at the title.
""",
    "late": """; WHERE IT BREAKS. game.asm whose flip places the room's guards a loop late,
; in flip1 instead of flip0.
""",
}
WHAT = {"game": "LANTERN KEEP, finished", "late": "guards placed a loop late"}
HEAD = '''; {name}.asm -- chapter 46: {what}
; generated by gen46.py
        INCLUDE "msx.inc"
        OUTPUT "{name}.rom"
        ORG $4000
        CART_HEADER init
VARS    EQU RAM_START + $100    ; the program's variables: the code is in ROM
'''
POST = gen45.POST
POST2 = gen45.POST2
ADDTEN = gen44.ROUNDS[gen44.ROUNDS.index("; addten:"):]
assert ADDTEN.startswith("; addten:")


def engine_parts():
    """chapter 37's player, its ticks and its song's step renamed (chapter 44)"""
    return gen44.engine_parts()


def program(name, hit_play=False, tune_always=False, guards=None, cp=25):
    """the program NAME; the workshop's variants send hit1 back to the play
    with greset and no flip, HIT_PLAY; play the tune in every state,
    TUNE_ALWAYS; take other rounds, GUARDS; or compare with CP in lamp"""
    late = name == "late"
    isr, play_rt, lamp_rt = ISR, PLAY_RT, LAMP_RT
    if tune_always:
        old = """        ld a, (state)           ; 14
        or a                    ;  5  TITLE?
        jr nz, .hush            ; 13, or 8
        call play               ; 18  the tune
        jr .done                ; 13
.hush:  call hush               ; 18  the sounds alone
"""
        assert isr.count(old) == 1
        isr = isr.replace(old, """        call play               ; 18  the tune, in every state
""")
    if hit_play:
        old = """        ld (explorer), hl       ; 17  Y and X
        ld a, FLIP              ;  8
        jp go                   ; 11
"""
        assert play_rt.count(old) == 1
        play_rt = play_rt.replace(old, """        ld (explorer), hl       ; 17  Y and X
        call greset             ; 18  the guards at their first places
        ld a, PLAY              ;  8  and no flip
        jp go                   ; 11
""")
    if cp != 25:
        assert lamp_rt.count("        cp 25                   ;  8") == 2
        lamp_rt = lamp_rt.replace("        cp 25                   ;  8", f"        cp {cp}                   ;  8")
    parts = (isr + HUSH + gen45.INPUT + gen45.KEYS + gen35.JOY + SENDS + gen45.PAGE +
             gen45.PRESSES + gen44.PACED + gen45.WALK + gen39.CELL + gen44.WALLED + gen45.LEAVE +
             gen45.UNPACK + flip_rt(late) + GUARD_RT + lamp_rt + CLOCK + play_rt + END_RT +
             gen45.MINI + gen45.MAP_RT + STATES_RT + SETS + POST + POST2 + ADDTEN +
             gen44.FX + gen40.BEST + gen40.ADDSC + gen42.PUTBCD + gen38.HERE_OWN + gen38.PAGE2 +
             gen38.SUBREG + engine_parts())
    body = setup_lines() + gen45.MAIN
    src = (HEAD.format(name=name, what=WHAT[name]) + '        INCLUDE "bios.inc"\n' + RAM +
           "SSLOT   EQU $FFFF               ; the secondary slot register, in page 3\n" + CONSTS +
           gen37.fields() + IM2 + SAY[name] + tidy(body + parts) + data(guards) + gen37.ENGINE_INC +
           "        ASSERT $ <= $8000, the first half is too long\n"
           "        ds $8000 - $, $FF       ; the first half ends at $7FFF\n" + second_half() +
           "romend:                         ; the cartridge's last byte, and one\n"
           "        ASSERT low rooms == 0 && rooms == $8000\n"
           "        ASSERT low ltab == 0 && low gtab == 0\n"
           "        ASSERT high (piccol + 31) == high piccol\n"
           "        ASSERT $ <= $C000, the program is longer than the cartridge\n"
           "        ds $C000 - $, $FF       ; the rest of the second half\n")
    return src


PROGRAMS = ["game", "late"]


def main():
    with open(os.path.join(HERE, "music.inc"), "w") as f:
        f.write(music_inc())
    for name in PROGRAMS:
        with open(os.path.join(HERE, f"{name}.asm"), "w") as f:
            f.write(program(name))
    print("music.inc " + " ".join(f"{n}.asm" for n in PROGRAMS))


if __name__ == "__main__":
    main()
