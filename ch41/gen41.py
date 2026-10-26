#!/usr/bin/env python3
"""gen41.py - the programs of chapter 41: random numbers, the R register,
and game states.

    python3 gen41.py && ./build.sh

    rreg.asm     R read 2,048 times in a loop, each number plotted against
                 the one before (figure 41.1); then R read on either side of
                 eight HALTs, with the interrupt on
    lcg.asm      5x + 1 in eight bits, 512 numbers from 0, each plotted
                 against the one before (figure 41.1)
    xorshift.asm a 16-bit xorshift (7, 9, 8), its whole period from the seed 1,
                 each high byte plotted against the one before (figure 41.2)
    bits.asm     the bits of lcg's first 256 numbers and of random's, a
                 column a number (figure 41.3)
    rows.asm     a row from 0 to 23 three ways, over random's period: the
                 rows counted in the RAM
    states.asm   a game of three states, the title, the play and game over,
                 with a table of routines for each; the seed is the frame
                 count when SPACE is pressed, and the keys come from
                 states.events (chapter 34) (figure 41.4)

The plotting programs draw on chapter 25's bitmap (Graphic II, names 0 to 255
in each third, black on white) with its plot, the display on and the
interrupts off. states.asm is Graphic II with one set for the three thirds,
chapter 30's characters at names 32 to 127 and a black cell at name 1, and
its interrupt in mode 2 counts the frames. Every line of lcg, random,
rowrej, rowmul and rowmod carries its price, which walk.py adds up along the
path it takes. Each program ends with asmparts.CART_END; build.sh assembles
with --syntax=bFw.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "tools"))
sys.path.insert(0, os.path.join(REPO, "ch25"))
sys.path.insert(0, os.path.join(REPO, "ch26"))
sys.path.insert(0, os.path.join(REPO, "ch30"))
from asmparts import HEAD, CART_END, GRAPHIC2, IM2, im2  # noqa: E402
from gen25 import VADDR, PLOT, MASKS  # noqa: E402  (chapter 25: plot)
from gen26 import db_rows  # noqa: E402
import shapes30  # noqa: E402  (chapter 30: the set)

EU, JP = "MSXBOOK_EU16", "MSXBOOK_JP16"
MACHINES = [EU, JP]
BIOS = '        INCLUDE "bios.inc"\n'
BLACK, WHITE = 1, 15

RREG_PASSES = 2048
LCG_STEPS = 512
HALTS = 8
LCG_TOP, RND_TOP = 16, 112      # bits.asm: the first line of each band
STRIP, STRIP_GAP = 5, 1         # a bit: 5 lines, and 1 of paper under it
PERIOD = 65535

# states.asm
TITLE, PLAY, OVER = 0, 1, 2
PLAY_FRAMES, OVER_FRAMES = 150, 100
BLOCK = 1                       # the name of a black cell
PRESS = "PRESS SPACE"
OVER_TEXT = "GAME OVER"
PRESS_AT = 0x1800 + 32 * 11 + 10
OVER_AT = 0x1800 + 32 * 11 + 11
FONT = shapes30.wide()
STATES_REGS = [0x02, 0xE0, 0x06, 0x9F, 0x00, 0x36, 0x07, WHITE]
PRESSES = [60, 340]             # the frames, from INIT, in which SPACE goes down
HELD = 4                        # and is held for this many
STATES_FRAMES = 620


def head(name, what):
    return HEAD.format(name=name, chapter=41, what=what) + BIOS


def say_lines(text):
    return "".join(f"; {l}\n" for l in text.strip().splitlines())


# ------------------------------------------------------------------ the generators
LCG = """
; lcg: the next of 256 numbers, 5 x seed8 + 1 -> seed8 and A. Uses A, B
lcg:    ld a, (seed8)           ; 14
        ld b, a                 ;  5
        add a, a                ;  5
        add a, a                ;  5  4 x
        add a, b                ;  5  5 x
        inc a                   ;  5  5 x + 1
        ld (seed8), a           ; 14
        ret                     ; 11
"""

RANDOM = """
; random: the next of the 65,535 states of a 16-bit xorshift, x XOR x << 7,
; XOR x >> 9, XOR x << 8 -> seed, A = its high byte. Uses A, HL
random: ld hl, (seed)           ; 17
        ld a, h                 ;  5
        rra                     ;  5  bit 0 of H into the carry
        ld a, l                 ;  5
        rra                     ;  5  x << 7's high byte: that bit and L >> 1
        xor h                   ;  5
        ld h, a                 ;  5  H XOR it
        ld a, l                 ;  5
        rrca                    ;  5
        and $80                 ;  8  x << 7's low byte: L's bit 0 at bit 7
        xor l                   ;  5
        ld l, a                 ;  5  x XOR x << 7
        ld a, h                 ;  5
        srl a                   ; 10  x >> 9, which is H >> 1
        xor l                   ;  5
        ld l, a                 ;  5  x XOR x >> 9, which changes L alone
        xor h                   ;  5
        ld h, a                 ;  5  x XOR x << 8: H XOR L
        ld (seed), hl           ; 17
        ret                     ; 11
"""

ROWS = """
; rowrej: A = a row from 0 to 23, from random's numbers AND 31, until one is
; below 24. Uses A, HL
rowrej: call random             ; 18
        and 31                  ;  8
        cp 24                   ;  8
        jr nc, rowrej           ; 13, or 8  24 to 31: another
        ret                     ; 11

; rowmul: A = a number -> A = A x 24 / 256, a row from 0 to 23. Uses A, DE, HL
rowmul: ld l, a                 ;  5
        ld h, 0                 ;  8
        ld e, l                 ;  5
        ld d, h                 ;  5
        add hl, hl              ; 12
        add hl, de              ; 12  3 x
        add hl, hl              ; 12
        add hl, hl              ; 12
        add hl, hl              ; 12  24 x
        ld a, h                 ;  5  / 256
        ret                     ; 11

; rowmod: A = a number -> A = A MOD 24, a row from 0 to 23. Uses A
rowmod: sub 24                  ;  8
        jr nc, rowmod           ; 13, or 8
        add a, 24               ;  8  one 24 too many
        ret                     ; 11
"""


def graphic2_on():
    return GRAPHIC2 + "        VDP_REG 1, $C0          ; display on: the plotting is watched\n"


PLOTTING = VADDR + PLOT


# ------------------------------------------------------------------ rreg.asm
RREG_MAIN = f"""        ld a, r                 ; the first number
        ld b, a                 ; B: the number before
        ld hl, {RREG_PASSES}
pl1:    push hl
        ld a, r                 ; A: the next
        ld c, a                 ; C: this one
        cp 192
        jr nc, pl2              ; below the paper: not plotted
        call plot               ; x the one before, y this one
pl2:    ld b, c                 ; this one is the one before
        pop hl
        dec hl
        ld a, h
        or l
        jr nz, pl1
""" + im2("isr") + f"""        in a, (VDP_CTRL)        ; no signal left over
        VDP_REG 1, $E0          ; the frame's interrupt on
        ld b, {HALTS}
        ei
waits:  ld a, r
before: halt                    ; R on either side of HALT
after:  ld a, r
        djnz waits
        di
done:   jr done

; isr: the status read, which lets the signal down
isr:    push af
        in a, (VDP_CTRL)
        pop af
        ei
        ret
"""

# ------------------------------------------------------------------ lcg.asm
LCG_MAIN = f"""        xor a
        ld (seed8), a           ; the seed, 0
        ld b, a                 ; B: the number before
        ld hl, {LCG_STEPS}
lc1:    push hl
        push bc
        call lcg                ; A: the next
        pop bc
        ld c, a                 ; C: this one
        cp 192
        jr nc, lc2              ; below the paper: not plotted
        call plot
lc2:    ld b, c
        pop hl
        dec hl
        ld a, h
        or l
        jr nz, lc1
done:   jr done
"""

# ------------------------------------------------------------------ xorshift.asm
XOR_MAIN = f"""        ld hl, 1
        ld (seed), hl           ; the seed, 1
        ld b, 0                 ; B: the number before, the seed's high byte
        ld hl, {PERIOD}
xs1:    push hl
        call random             ; A: the next
        ld c, a
        cp 192
        jr nc, xs2              ; below the paper: not plotted
        call plot
xs2:    ld b, c
        pop hl
        dec hl
        ld a, h
        or l
        jr nz, xs1
done:   jr done
"""

# ------------------------------------------------------------------ bits.asm
BITS_MAIN = f"""        xor a
        ld (seed8), a           ; lcg from 0
        ld b, a                 ; column 0
bl1:    push bc
        call lcg
        pop bc
        {'ld c, ' + str(LCG_TOP):<24}; its band
        push bc
        call strips
        pop bc
        inc b
        jr nz, bl1              ; 256 columns
        ld hl, 1
        ld (seed), hl           ; random from 1
bl2:    push bc
        call random
        pop bc
        {'ld c, ' + str(RND_TOP):<24}; its band
        push bc
        call strips
        pop bc
        inc b
        jr nz, bl2
done:   jr done

; strips: A = a number, B = its column, C = its band's first line -> each bit
; that is 1 drawn as {STRIP} pixels down the column, bit 7 at the top
strips: ld (num), a
        ld a, 8
st1:    ld (left), a
        ld a, (num)
        rlca                    ; the next bit, from bit 7, into the carry
        ld (num), a
        jr nc, st3
        push bc
        ld a, {STRIP}
st2:    push af
        call plot
        inc c
        pop af
        dec a
        jr nz, st2
        pop bc
st3:    ld a, c
        add a, {STRIP + STRIP_GAP}
        ld c, a                 ; the next bit's strip
        ld a, (left)
        dec a
        jr nz, st1
        ret
"""

# ------------------------------------------------------------------ rows.asm
ROWS_MAIN = f"""        ld hl, counts           ; the counts: 3 x 24 rows, two bytes each
        ld de, counts + 1
        ld bc, 3 * 48 - 1
        ld (hl), 0
        ldir
        ld hl, 1
        ld (seed), hl
        ld hl, {PERIOD}
rj1:    push hl
        call rowrej
        ld hl, counts
        call count
        pop hl
        dec hl
        ld a, h
        or l
        jr nz, rj1
rejected:
        ld hl, 1
        ld (seed), hl
        ld hl, {PERIOD}
mu1:    push hl
        call random
        call rowmul
        ld hl, counts + 48
        call count
        pop hl
        dec hl
        ld a, h
        or l
        jr nz, mu1
multiplied:
        ld hl, 1
        ld (seed), hl
        ld hl, {PERIOD}
mo1:    push hl
        call random
        call rowmod
        ld hl, counts + 96
        call count
        pop hl
        dec hl
        ld a, h
        or l
        jr nz, mo1
done:   jr done

; count: A = a row, HL = its table -> the row's count, two bytes, one more
count:  add a, a
        add a, l
        ld l, a                 ; the table does not cross a page
        inc (hl)
        ret nz
        inc l
        inc (hl)
        ret
"""

RAM = """seed    EQU VARS                ; random's state, two bytes
seed8   EQU VARS + 2            ; lcg's
num     EQU VARS + 3            ; strips: the number, and the bits left
left    EQU VARS + 4
counts  EQU $C400               ; rows.asm: 3 x 24 counts of two bytes
"""

# ------------------------------------------------------------------ states.asm
STATES_RAM = f"""ticks   EQU VARS                ; frames, counted by isr, two bytes
seed    EQU VARS + 2            ; random's state, two bytes
state   EQU VARS + 4            ; TITLE, PLAY or OVER
left    EQU VARS + 5            ; the frames left of the play or of game over
TITLE   EQU {TITLE}
PLAY    EQU {PLAY}
OVER    EQU {OVER}
{'PRESS_AT EQU $' + format(PRESS_AT, '04X'):<32}; row 11, column {PRESS_AT % 32}
{'OVER_AT EQU $' + format(OVER_AT, '04X'):<32}; row 11, column {OVER_AT % 32}
{'BLOCK   EQU ' + str(BLOCK):<32}; the name of a black cell
"""


def states_setup():
    return f"""init:   di
        ld sp, SYS_AREA
        VDP_REG 1, $80          ; display off
        VDP_REG 0, $02          ; Graphic II
        VDP_REG 2, $06          ; names    $1800
        VDP_REG 3, $9F          ; colours  $2000, one set for three thirds
        VDP_REG 4, $00          ; shapes   $0000, one set for three thirds
        VDP_REG 5, $36          ; sprite attributes $1B00
        VDP_REG 6, $07          ; sprite patterns   $3800
        VDP_REG 7, ${WHITE:02X}          ; border white
        VRAM_WRITE $1B00        ; no sprites
        ld a, $D0
        out (VDP_DATA), a
        VRAM_WRITE $0000        ; the shapes: name 0 paper,
        ld b, 8
        xor a
sh0:    out (VDP_DATA), a
        djnz sh0
        ld b, 8                 ; name {BLOCK} a black cell
        ld a, $FF
sh1:    out (VDP_DATA), a
        djnz sh1
        VRAM_WRITE $0100        ; names 32-127 chapter 30's set
        ld hl, font
        ld bc, 768
sh2:    ld a, (hl)
        out (VDP_DATA), a
        inc hl
        dec bc
        ld a, b
        or c
        jr nz, sh2
        VRAM_WRITE $2000        ; the colours: black on white
        ld bc, 2048
sh3:    ld a, ${BLACK << 4 | WHITE:02X}
        out (VDP_DATA), a
        dec bc
        ld a, b
        or c
        jr nz, sh3
        ld hl, 0
        ld (ticks), hl
""" + im2("isr") + """        ld a, TITLE
        call go                 ; the first state
        in a, (VDP_CTRL)        ; no signal left over
        VDP_REG 1, $E0          ; display on, the frame's interrupt on
        ei
"""


STATES_MAIN = """frame:  halt                    ; the frame begins
work:   call run                ; the state's work for this frame
worked: jr frame

; run: this frame's routine for the state held in state. Uses every
; register that routine uses
run:    ld a, (state)
        ld hl, frames
        jr table

; go: A = a state -> it is the state, and its start routine has run. Uses
; every register that routine uses
go:     ld (state), a
        ld hl, starts
table:  add a, a                ; two bytes a state
        add a, l
        ld l, a                 ; the tables do not cross a page
        ld a, (hl)
        inc l
        ld h, (hl)
        ld l, a
        jp (hl)                 ; and its RET goes back to the caller

; title0: the screen cleared, PRESS SPACE
title0: call wipe
        ld hl, press
        ld de, PRESS_AT | $4000
        jp say

; title1: SPACE held? Then the seed is the frame count, and the play begins
title1: in a, (PPI_C)
        and $F0                 ; the top four bits kept (chapter 34)
        or 8
        out (PPI_C), a          ; row 8
        in a, (PPI_B)
keyed:  and 1                   ; SPACE: 0 when held
        ret nz
        ld hl, (ticks)          ; the seed, the frame count
        ld a, h
        or l
        jr nz, seeded
        inc hl                  ; but 1 for 0, which random keeps at 0
seeded: ld (seed), hl
pressed: ld a, PLAY
        jp go

; play0: the screen cleared, and 150 frames to play
play0:  call wipe
        ld a, PLAY_FRAMES
        ld (left), a
        ret

; play1: a cell chosen by random blackened; at the end, game over
play1:  call random
        and 31
        ld c, a                 ; the column, 0 to 31
        call rowrej             ; the row, 0 to 23
        ld l, a
        ld h, 0
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl              ; the row times 32
        ld a, l
        or c
        out (VDP_CTRL), a       ; plus the column
        ld a, h
        or $58
        out (VDP_CTRL), a       ; plus $1800, for writing
        ld a, BLOCK
        out (VDP_DATA), a       ; black
        ld hl, left
        dec (hl)
        ret nz
ended:  ld a, OVER
        jp go

; over0: GAME OVER, and 100 frames of it
over0:  ld hl, over
        ld de, OVER_AT | $4000
        call say
        ld a, OVER_FRAMES
        ld (left), a
        ret

; over1: the frames counted down, then the title again
over1:  ld hl, left
        dec (hl)
        ret nz
again:  ld a, TITLE
        jp go

; wipe: the 768 names spaces. Uses A, BC
wipe:   VRAM_WRITE $1800
        ld bc, 768
wp1:    ld a, 32
        out (VDP_DATA), a
        dec bc
        ld a, b
        or c
        jr nz, wp1
        ret

; say: HL = a text ending in a 0 byte, DE = the VRAM address of its first
; character, bit 6 set -> the text sent. Uses A, HL
say:    ld a, e
        out (VDP_CTRL), a
        ld a, d
        out (VDP_CTRL), a
sy1:    ld a, (hl)
        or a
        ret z
        out (VDP_DATA), a
        inc hl
        jr sy1

; isr: every frame. The status read, which lets the signal down; the frame
; counted. Keeps AF, HL
isr:    push af
        push hl
        in a, (VDP_CTRL)
        ld hl, (ticks)
        inc hl
        ld (ticks), hl
        pop hl
        pop af
        ei
        ret
"""


def states_data():
    return (f"""PLAY_FRAMES EQU {PLAY_FRAMES}
OVER_FRAMES EQU {OVER_FRAMES}
        ALIGN 16
starts: dw title0, play0, over0 ; each state's first frame
frames: dw title1, play1, over1 ; and every frame of it
press:  db "{PRESS}", 0
over:   db "{OVER_TEXT}", 0
font:                           ; chapter 30's set, codes 32 to 127
""" + db_rows(FONT))


def states_events():
    lines = ["# states.events -- chapter 41: the keys states.rom is given, generated by gen41.py",
             "# frame (from INIT) and openMSX command; keymatrixdown 8 0x01 holds SPACE down"]
    for f in PRESSES:
        lines += [f"{f} keymatrixdown 8 0x01", f"{f + HELD} keymatrixup 8 0x01"]
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------ the programs
SAYS = {
    "rreg": """rreg.asm: R read 2,048 times in a loop, each number plotted against the
one before; then R on either side of eight HALTs.""",
    "lcg": """lcg.asm: 5x + 1 in eight bits from 0, 512 numbers, each plotted against
the one before.""",
    "xorshift": """xorshift.asm: a 16-bit xorshift from 1, its whole period of 65,535,
each high byte plotted against the one before.""",
    "bits": """bits.asm: the bits of lcg's first 256 numbers and of random's, a column
a number, bit 7 at the top.""",
    "rows": """rows.asm: a row from 0 to 23 three ways, over random's period: by
rejection, by multiplication and by remainder; the rows counted.""",
    "states": """states.asm: a game of three states, the title, the play and game over;
the seed is the frame count when SPACE is pressed.""",
}
WHAT = {"rreg": "the R register as a source of numbers", "lcg": "a linear congruential generator",
        "xorshift": "a 16-bit xorshift", "bits": "the bits of two generators",
        "rows": "a row from 0 to 23, three ways", "states": "a game of three states"}


def program(name):
    if name == "states":
        return (head(name, WHAT[name]) + say_lines(SAYS[name]) + STATES_RAM + IM2 + states_setup() +
                STATES_MAIN + RANDOM + ROWS + states_data() + CART_END)
    main = {"rreg": RREG_MAIN, "lcg": LCG_MAIN, "xorshift": XOR_MAIN, "bits": BITS_MAIN,
            "rows": ROWS_MAIN}[name]
    routines = {"rreg": "", "lcg": LCG, "xorshift": RANDOM, "bits": LCG + RANDOM,
                "rows": RANDOM + ROWS}[name]
    setup = graphic2_on() if name != "rows" else "init:   di\n        ld sp, SYS_AREA\n"
    ram = RAM + (IM2 if name == "rreg" else "")
    plotting = PLOTTING if name != "rows" else ""
    tail = MASKS if name != "rows" else ""
    return (head(name, WHAT[name]) + say_lines(SAYS[name]) + ram + setup + main + routines +
            plotting + tail + CART_END)


# ------------------------------------------------------------------ the models
def lcg_numbers(seed=0, n=256):
    out, x = [], seed
    for _ in range(n):
        x = (5 * x + 1) & 255
        out.append(x)
    return out


def xorshift(x):
    x ^= (x << 7) & 0xFFFF
    x ^= x >> 9
    x ^= (x << 8) & 0xFFFF
    return x


def random_states(seed=1, n=PERIOD):
    out, x = [], seed
    for _ in range(n):
        x = xorshift(x)
        out.append(x)
    return out


def rowrej_rows(seed=1, n=PERIOD):
    """rowrej n times from SEED: the rows, and the numbers each took"""
    x, rows, took = seed, [], []
    for _ in range(n):
        k = 0
        while True:
            x = xorshift(x)
            k += 1
            v = (x >> 8) & 31
            if v < 24:
                break
        rows.append(v)
        took.append(k)
    return rows, took, x


def rowmul(a):
    return (a * 24) >> 8


def rowmod(a):
    return a % 24


def play_cells(seed, n=PLAY_FRAMES):
    """the cells play1 blackens from SEED, in order: (column, row)"""
    x, cells = seed, []
    for _ in range(n):
        x = xorshift(x)
        col = (x >> 8) & 31
        while True:
            x = xorshift(x)
            v = (x >> 8) & 31
            if v < 24:
                break
        cells.append((col, v))
    return cells


def main():
    names = ["rreg", "lcg", "xorshift", "bits", "rows", "states"]
    for name in names:
        with open(os.path.join(HERE, f"{name}.asm"), "w") as f:
            f.write(program(name))
    with open(os.path.join(HERE, "states.events"), "w") as f:
        f.write(states_events())
    print(" ".join(f"{n}.asm" for n in names), "states.events")


if __name__ == "__main__":
    main()
