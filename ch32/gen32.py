#!/usr/bin/env python3
"""gen32.py - the programs of chapter 32: racing the beam on an MSX1.

    python3 gen32.py && ./build.sh

    poll.asm     three bars of cyan, R#7 changed at three lines of the paper,
                 counted from the end of the paper found by reading the status
                 (figures 32.1 and 32.2)
    fifth.asm    the same bars, counted from the line where five sprites,
                 transparent, set 5S in the status (figure 32.1)
    steady.asm   the same bars from the handler of an interrupt of mode 2,
                 the CPU halted when it comes (figure 32.1)
    split.asm    the patterns' base, R#4, changed in the border before line 96
                 from an interrupt of mode 2: two sets of characters on one
                 screen (figures 32.2 and 32.3)
    crowd.asm    WHERE IT BREAKS: fifth.asm with five sprites of the game's own
                 moving down the screen (figure 32.4)

Graphic I, 32 x 24 characters, the set of chapter 30 at codes 32 to 127,
black ink on transparent paper, so that the backdrop, R#7, shows round the
letters. Every program keeps the interrupts off but steady.asm and split.asm;
poll.asm, steady.asm and split.asm read bit 7 of $002B for the machine's rate
(chapter 4), fifth.asm and crowd.asm need no count. Every program ends with
asmparts.CART_END, and build.sh assembles with --syntax=bFw.
"""
import os
import sys
from fractions import Fraction

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "ch26"))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "ch30"))
from asmparts import HEAD, CART_END, IM2, im2  # noqa: E402
from gen26 import tidy, db_rows  # noqa: E402  (chapter 26)
import shapes30  # noqa: E402  (chapter 30's set)

BIOS = '        INCLUDE "bios.inc"\n'
BLACK, DARK_BLUE, CYAN, WHITE = 1, 4, 7, 15
EU, JP = "MSXBOOK_EU16", "MSXBOOK_JP16"
LINE_T = 228
LINES = {EU: 313, JP: 262}
PAPER0 = {EU: 69, JP: 42}               # the frame's line of paper line 0 (chapter 18)
FLAG_LINE = {EU: 261, JP: 234}          # where F rises, the first line under the paper
BARS = [(48, CYAN), (96, CYAN), (144, CYAN)]   # paper line, colour: one, for print in grey
BAR_LINES = 8
SPLIT = 96                              # split.asm: the bold set from this paper line
FRAMES = 16
SIGNAL_X = [0, 24, 48, 72, 96]          # the five transparent sprites, at line 48
CROWD_X = [120, 144, 168, 192, 216]     # crowd.asm: the game's five, dark blue
CROWD_Y0, CROWD_STEP = 8, 4             # ... from paper line 8, 4 lines a frame
REGS = {"poll": [0, 0xC0, 6, 0x80, 0, 0x36, 7, 0x0F], "fifth": [0, 0xC0, 6, 0x80, 0, 0x36, 7, 0x0F],
        "steady": [0, 0xE0, 6, 0x80, 0, 0x36, 7, 0x0F], "split": [0, 0xE0, 6, 0x80, 0, 0x36, 7, 0x0F],
        "crowd": [0, 0xC0, 6, 0x80, 0, 0x36, 7, 0x0F]}


def head(name, what):
    return HEAD.format(name=name, chapter=32, what=what) + BIOS


# ------------------------------------------------------------------ the screen
FONT = shapes30.wide()                          # 768 bytes, codes 32 to 127
BOLD = bytes(b | b >> 1 for b in FONT)          # the same letters a pixel wider


def text_rows():
    """24 rows of 32 names: each row says which lines of the paper it covers"""
    rows = []
    for r in range(24):
        t = f"  row {r:2d}: lines {8 * r:3d} to {8 * r + 7:3d}"
        rows.append([ord(c) for c in t.ljust(32)])
    return rows


NAMES = [n for row in text_rows() for n in row]


def sprites(name, k=0):
    """the sprite attributes: the five signals at line 48 for fifth.asm and
    crowd.asm, and crowd.asm's own five after k moves; then $D0"""
    att = []
    if name in ("fifth", "crowd"):
        att += [[BARS[0][0] - 1, x, 0, 0] for x in SIGNAL_X]         # colour 0: not seen
    if name == "crowd":
        y = CROWD_Y0 + CROWD_STEP * k
        att += [[y - 1, x, 1, DARK_BLUE] for x in CROWD_X]
    return att


BALL = [0x3C, 0x7E, 0xFF, 0xFF, 0xFF, 0xFF, 0x7E, 0x3C]


def vram_of(name, k=0, r4=0):
    """the VRAM a program shows: the set (and split.asm's bold one at $0800),
    the colours, the names, the sprites"""
    v = bytearray(16384)
    v[0x100:0x400] = FONT
    if name == "split":
        v[0x900:0xC00] = BOLD
    v[0x2000:0x2020] = bytes([BLACK << 4]) * 32
    v[0x1800:0x1B00] = bytes(NAMES)
    at = 0x1B00
    for y, x, p, c in sprites(name, k):
        v[at:at + 4] = bytes([y & 0xFF, x, p, c])
        at += 4
    v[at] = 0xD0
    v[0x3800:0x3808] = bytes([0xFF] * 8)
    v[0x3808:0x3810] = bytes(BALL)
    return v


def first_five(name, k=0):
    """the first line of the paper with five sprites on it: where 5S rises"""
    lines = {}
    for y, x, p, c in sprites(name, k):
        for line in range(y + 1, y + 9):
            lines[line] = lines.get(line, 0) + 1
    hit = [line for line, n in lines.items() if n >= 5 and 0 <= line < 192]
    return min(hit) if hit else None


# ------------------------------------------------------------------ exact waits
def wait(t):
    """lines that take exactly T T-states (T >= 41), touching A, BC and F:
    a loop of 30 T-states a turn, and NOPs and LD A,(HL)s for the rest"""
    out = []
    turns = (t - 11 - 6 - 15) // 30 if t >= 77 else 0
    rest = t
    if turns > 0:
        out += [f"        ld bc, {turns:<17}; {t:,} T-states in all",
                ".w{k}:   dec bc                  ;  7",
                "        ld a, b                 ;  5", "        or c                    ;  5",
                "        jr nz, .w{k}            ; 13"]
        rest -= 11 + 30 * turns - 5
    for b in range(0, rest // 8 + 1):            # rest = 8b + 5n
        if (rest - 8 * b) % 5 == 0:
            return out + pad("ld a, (hl)", b, 8) + pad("nop", (rest - 8 * b) // 5, 5)
    raise ValueError(t)


def pad(op, n, t):
    """N times OP, of T T-states each: a DUP from two on"""
    if n < 2:
        return [f"        {op:<24}; {t:2d}"] * n
    return [f"        DUP {n:<20}; {n} x {t}", f"        {op}", "        EDUP"]


def waited(lines, k):
    return "\n".join(l.replace("{k}", str(k)) for l in lines) + "\n"


R7 = """        ld a, {colour:<18}; {name}
        out (VDP_CTRL), a
        ld a, $87
{label}:     out (VDP_CTRL), a       ; R#7: {say}
"""
NAME = {CYAN: "cyan", WHITE: "white"}


def bars():
    """the three bars, each BAR_LINES long: a write of R#7 every bar's top and
    bottom, exactly that many lines apart. The writes are 28 T-states each:
    LD A,n 8 and OUT 12, LD A,n 8; the label is on the second OUT, 12"""
    out, k = "", 0
    for i, (line, c) in enumerate(BARS):
        out += R7.format(colour=c, name=NAME[c], label=f"b{i}", say=f"the bar from line {line}")
        out += waited(wait(BAR_LINES * LINE_T - 40), k)
        k += 1
        out += R7.format(colour=WHITE, name=NAME[WHITE], label=f"e{i}", say="white again")
        if i + 1 < len(BARS):
            gap = (BARS[i + 1][0] - line - BAR_LINES) * LINE_T - 40
            out += waited(wait(gap), k)
            k += 1
    return out


SETUP = """init:   di
        ld sp, SYS_AREA
        VDP_REG 1, $80          ; display off
        VDP_REG 0, $00          ; Graphic I
        VDP_REG 2, $06          ; names    $1800
        VDP_REG 3, $80          ; colours  $2000
        VDP_REG 4, $00          ; patterns $0000
        VDP_REG 5, $36          ; sprite attributes $1B00
        VDP_REG 6, $07          ; sprite patterns   $3800
        VDP_REG 7, $0F          ; the backdrop white
        VRAM_WRITE $0000        ; the patterns: none first
        xor a
        ld e, 16
        call fill
        VRAM_WRITE $0100        ; the set of chapter 30 at code 32
        ld hl, font
        ld e, 3
        call send
{bold}        VRAM_WRITE $2000        ; black ink on transparent paper
        ld a, $10
        ld b, 32
.col:   out (VDP_DATA), a
        djnz .col
        VRAM_WRITE $1800        ; the names
        ld hl, names
        ld e, 3
        call send
        VRAM_WRITE $3800        ; sprite patterns: a block and a ball
        ld hl, shapes
        ld b, 16
        otir
        VRAM_WRITE $1B00        ; the sprites
        ld hl, attributes
        ld b, {natt}
        otir
"""
BOLD_COPY = """        VRAM_WRITE $0900        ; split.asm: the bold set at $0800, code 32
        ld hl, bold
        ld e, 3
        call send
"""

COMMON = """
; frame: wait for the end of the paper: F, bit 7 of the status, read with the
; interrupts off (chapter 19)
frame:  in a, (VDP_CTRL)
        rla
        jr nc, frame
        ret

; send: E blocks of 256 bytes from HL with OTIR, the display off (chapter 31)
send:   ld c, VDP_DATA
        ld b, 0
.otir:  otir
        dec e
        jr nz, .otir
        ret

; fill: E blocks of 256 bytes of A, the display off
fill:   ld b, 0
.out:   out (VDP_DATA), a
        djnz .out
        dec e
        jr nz, .out
        ret
"""

RAM = """count   EQU VARS                ; the frames left
wait    EQU VARS + 1            ; the turns of 30 T-states to the first bar
crowd   EQU VARS + 3            ; crowd.asm: its sprites' line, less 1
"""


def data(name):
    att = [b for a in sprites(name) for b in a] + [0xD0]
    out = ("names:                          ; 24 rows of 32\n" + db_rows(NAMES, 16) +
           "shapes:                         ; a block, for the signals, and a ball\n" +
           db_rows([0xFF] * 8 + BALL) + "attributes:\n" + db_rows(att, 4) +
           "font:                           ; chapter 30's set\n" + db_rows(FONT, 16))
    if name == "split":
        out += "bold:                           ; the same, a pixel wider\n" + db_rows(BOLD, 16)
    return out


def rate(n60, n50, var="wait"):
    return f"""        ld a, ($002B)           ; bit 7 is 1 on a 50 Hz machine (chapter 4)
        rla
        ld hl, {n60}                ; 60 Hz ...
        jr nc, .sixty
        ld hl, {n50}               ; ... and 50 Hz
.sixty: ld ({var}), hl
"""


def program(name, what, say, body, routines=""):
    natt = 4 * len(sprites(name)) + 1
    setup = SETUP.format(bold=BOLD_COPY if name == "split" else "", natt=natt)
    return (head(name, what) + RAM + (IM2 if name in ("steady", "split") else "") + say +
            tidy(setup + body + "done:   jr done\n" + COMMON + routines) + data(name) + CART_END)


# ------------------------------------------------------------------ the counts
# Where a write lands, worked out from chapter 19's signal and the listings'
# T-states (meas32.py walks the listings for the sums and the debugger checks
# every frame's).
FRAME_T = {EU: 71364, JP: 59736}
SIGNAL_T = {m: FLAG_LINE[m] * LINE_T + Fraction(101, 3) for m in (EU, JP)}   # F rises (chapter 19)
IN_SEES = Fraction(26, 3)   # an IN begun this long before the change finds it (chapter 19)
POLL_AFTER = 89             # from the IN that finds F to the write of R#7, the turns aside:
#                             IN 12, RLA 5, JR NC 8, RET 11, LD BC,(nn) 22, the last turn's
#                             JR NZ 5 short, LD A,n 8, OUT 12, LD A,n 8 and 8 into the OUT
FIVE_AFTER = 64             # from the IN that finds 5S: IN 12, AND 8, JR Z 8, LD A,n 8,
#                             OUT 12, LD A,n 8 and 8 into the OUT
STEADY_AFTER = 95           # from the signal to the write of R#7, the HALT's 0 to 4 and
#                             the turns aside: the answer 19, the JP 11, IN 12, LD BC,(nn)
#                             22, the last JR NZ 5 short, LD A,n 8, OUT 12, LD A,n 8 and 8
SPLIT_AFTER = 132           # from the signal to the write of R#4 = 1, the HALT's 0 to 4
#                             and the turns aside: the answer 19, the JP 11, IN 12, XOR 5,
#                             OUT 12, LD A,n 8, OUT 12, LD BC,(nn) 22, the last JR NZ 5
#                             short, LD A,n 8, OUT 12, LD A,n 8 and 8 into the OUT
POLL_TURN, FIVE_TURN, HALT_STEP = 30, 33, 5
FIVE_EDGE = 1               # 5S rises within 6 VDP cycles of its line's start (chapter 27)
MIDDLE_W = Fraction(160 + 31) * 2 / 3          # the T-state of a line whose change shows mid-paper
GAP_W = Fraction(288 + 31) * 2 / 3 - LINE_T     # the paper of the line before ends here ...
GAP_END = Fraction(32 + 31) * 2 / 3             # ... and the next line's begins: 57 1/3 T-states later


def poll_turns(m):
    """the turns that put the middle of poll.asm's 30 T-states of writes in
    the middle of paper line 48"""
    line = PAPER0[m] + BARS[0][0]               # paper line 48 in the frame
    aim = FRAME_T[m] + line * LINE_T + MIDDLE_W  # its middle, a frame on
    first = aim - Fraction(POLL_TURN, 2)        # where the window begins
    return round((first - SIGNAL_T[m] + IN_SEES - POLL_AFTER) / POLL_TURN)


def steady_turns(m):
    """the turns that put the middle of steady.asm's 5 T-states of writes in
    the middle of paper line 48"""
    line = PAPER0[m] + BARS[0][0]
    first = FRAME_T[m] + line * LINE_T + MIDDLE_W - Fraction(HALT_STEP, 2)
    return round((first - SIGNAL_T[m] - STEADY_AFTER) / POLL_TURN)


def split_turns(m):
    """the turns that put split.asm's 5 T-states of writes in the middle of the
    gap between the paper of line SPLIT - 1 and the paper of line SPLIT"""
    line = PAPER0[m] + SPLIT
    first = FRAME_T[m] + line * LINE_T + (GAP_W + GAP_END) / 2 - Fraction(HALT_STEP, 2)
    return round((first - SIGNAL_T[m] - SPLIT_AFTER) / POLL_TURN)


def windows(name, m, k=0):
    """the frame T-states (of the frame drawn) between which the program's first
    write may land: [first, last)"""
    if name == "poll":
        a = SIGNAL_T[m] - IN_SEES + POLL_AFTER + POLL_TURN * poll_turns(m) - FRAME_T[m]
        return a, a + POLL_TURN
    if name in ("fifth", "crowd"):
        a = (PAPER0[m] + first_five(name, k)) * LINE_T - FIVE_EDGE - IN_SEES + FIVE_AFTER
        return a, a + FIVE_TURN + 2 * FIVE_EDGE
    if name == "steady":
        a = SIGNAL_T[m] + STEADY_AFTER + POLL_TURN * steady_turns(m) - FRAME_T[m]
        return a, a + HALT_STEP
    a = SIGNAL_T[m] + SPLIT_AFTER + POLL_TURN * split_turns(m) - FRAME_T[m]
    return a, a + HALT_STEP


def poll():
    n60, n50 = poll_turns(JP), poll_turns(EU)
    return program("poll", "bars counted from the end of the paper", f"""; Three bars of cyan behind the text, R#7 changed at lines {', '.join(str(b[0]) for b in BARS)} of the
; paper and {BAR_LINES} lines later: the first counted from the end of the paper, found by
; reading the status; the others {BARS[1][0] - BARS[0][0]} lines apart, to the T-state.
""", rate(n60, n50) + f"""        VDP_REG 1, $C0          ; the display on
        in a, (VDP_CTRL)        ; F cleared: the first wait ends with a paper
        ld a, {FRAMES}
        ld (count), a
loop:   call frame              ; the end of the paper
m0:     ld bc, (wait)
.t:     dec bc                  ;  7
        ld a, b                 ;  5
        or c                    ;  5
        jr nz, .t               ; 13: 30 T-states a turn
""" + bars() + """        ld hl, count
        dec (hl)
        jp nz, loop
""")


FIVE = """.five:  in a, (VDP_CTRL)        ; 12  the status: F cleared ...
        and $40                 ;  8  ... and 5S, the fifth sprite
        jr z, .five             ; 13: 33 T-states a read
"""


def fifth():
    return program("fifth", "bars counted from the fifth sprite", f"""; fifth.asm: poll.asm's bars, the first begun as soon as 5S is read: five
; sprites of colour 0, unseen, cover lines {BARS[0][0]} to {BARS[0][0] + 7} of the paper.
""", f"""        VDP_REG 1, $C0          ; the display on
        in a, (VDP_CTRL)
        ld a, {FRAMES}
        ld (count), a
loop:   call frame              ; the end of the paper
""" + FIVE + bars() + """        ld hl, count
        dec (hl)
        jp nz, loop
""")


def crowd():
    return program("crowd", "the fifth sprite, and the game's", f"""; WHERE IT BREAKS. fifth.asm with five sprites of the game's own, a row of balls
; moving down the screen from line {CROWD_Y0}, {CROWD_STEP} lines a frame.
""", f"""        ld a, {CROWD_Y0 - 1}
        ld (crowd), a
        VDP_REG 1, $C0          ; the display on
        in a, (VDP_CTRL)
        ld a, {FRAMES}
        ld (count), a
loop:   call frame              ; the end of the paper
        ld a, (crowd)           ; the balls {CROWD_STEP} lines down
        add a, {CROWD_STEP}
        ld (crowd), a
        call place
""" + FIVE + bars() + """        ld hl, count
        dec (hl)
        jp nz, loop
""", f"""
; place: the Y of the game's five sprites, 5 to 9, from (crowd)
place:  ld hl, $1B00 + 4 * 5    ; sprite 5's Y
        ld de, 4
        ld b, 5
.y:     ld a, l
        out (VDP_CTRL), a
        ld a, h
        or $40
        out (VDP_CTRL), a
        ld a, (crowd)
        out (VDP_DATA), a
        add hl, de
        djnz .y
        ret
""")


def steady():
    n60, n50 = steady_turns(JP), steady_turns(EU)
    return program("steady", "bars counted from the interrupt", f"""; steady.asm: poll.asm's bars, from the handler of the frame's interrupt, in
; mode 2: the CPU halts before it comes, and answers it within a step of HALT.
""", rate(n60, n50) + im2("isr") + f"""        VDP_REG 1, $E0          ; the display on, and the frame's signal
        in a, (VDP_CTRL)
        ld a, {FRAMES}
        ld (count), a
        ei
main:   halt                    ; the handler runs, and comes back here
        ld a, (count)
        or a
        jr nz, main
        di
""", """
; isr: every frame. A wait from the signal to line 48 of the paper, and the bars
isr:    in a, (VDP_CTRL)        ; the status: the signal down
        ld bc, (wait)
.t:     dec bc                  ;  7
        ld a, b                 ;  5
        or c                    ;  5
        jr nz, .t               ; 13: 30 T-states a turn
""" + bars() + """        ld hl, count
        dec (hl)
        ei
        ret
""")


def split():
    n60, n50 = split_turns(JP), split_turns(EU)
    return program("split", "two sets on one screen", f"""; The set of chapter 30 from $0000, R#4 = 0, and a bold copy of it from $0800,
; R#4 = 1: the handler of the frame's interrupt puts R#4 to 0, waits, and puts
; it to 1 in the border after line {SPLIT - 1}: the rows from {SPLIT // 8} on are bold.
""", rate(n60, n50) + im2("isr") + f"""        VDP_REG 1, $E0          ; the display on, and the frame's signal
        in a, (VDP_CTRL)
        ld a, {FRAMES}
        ld (count), a
        ei
main:   halt                    ; the handler runs, and comes back here
        ld a, (count)
        or a
        jr nz, main
        di
""", """
; isr: every frame. R#4 back to 0, a wait, R#4 to 1 between two lines
isr:    in a, (VDP_CTRL)        ; the status: the signal down
        xor a
        out (VDP_CTRL), a
        ld a, $84
s0:     out (VDP_CTRL), a       ; R#4 = 0: the set at $0000
        ld bc, (wait)
.t:     dec bc                  ;  7
        ld a, b                 ;  5
        or c                    ;  5
        jr nz, .t               ; 13: 30 T-states a turn
        ld a, 1
        out (VDP_CTRL), a
        ld a, $84
s1:     out (VDP_CTRL), a       ; R#4 = 1: the bold set at $0800
        ld hl, count
        dec (hl)
        ei
        ret
""")


PROGRAMS = {"poll": poll, "fifth": fifth, "steady": steady, "split": split, "crowd": crowd}


def main():
    for name, make in PROGRAMS.items():
        with open(os.path.join(HERE, f"{name}.asm"), "w") as f:
            f.write(make())
    print(" ".join(f"{n}.asm" for n in PROGRAMS))


if __name__ == "__main__":
    main()
