#!/usr/bin/env python3
"""gen33.py - the programs of chapter 33: the frame loop.

    python3 gen33.py && ./build.sh

    order.asm    the frame loop: an interrupt of mode 2 that counts frames, and
                 a main loop of HALT, the herd of chapter 26 sent to the VDP,
                 and the logic: the herd moved a pixel for every frame counted,
                 and a work of eight lengths in turn; the border shows each
                 part (figures 33.1 and 33.2)
    nocount.asm  the same, the herd moved a pixel each time round, whatever
                 the frames counted (figure 33.2)
    fits.asm     one work, the longest that still lets the loop reach HALT
                 before the next frame's signal, counted for the machine
    misses.asm   the same work and one turn of its wait more
    speed.asm    order.asm's loop with the herd moved by the time and not by
                 the frames: 306/256 of a pixel a frame at 50 Hz, 1 at 60 Hz
    seconds.asm  two clocks kept by the interrupt: chapter 17's, 50 or 60
                 frames a second, and one that keeps time, 2,207 frames to 44
                 seconds at 50 Hz and 779 to 13 at 60 Hz (chapter 18)
    first.asm    WHERE IT BREAKS: order.asm with the logic first and the herd
                 sent after it (figure 33.3)

The herd's programs draw in Graphic II, all paper, black ink on white, so
that R#7 shows only in the border; seconds.asm prints in Graphic I with
chapter 30's set. Every program takes the interrupt in mode 2 (chapter 17),
reads bit 7 of $002B where the machine's rate matters (chapter 4), ends with
asmparts.CART_END, and build.sh assembles with --syntax=bFw.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "ch26"))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "ch30"))
from asmparts import HEAD, CART_END, GRAPHIC2, IM2, im2  # noqa: E402
import gen26  # noqa: E402  (chapter 26: the figure, tidy, db_rows)
import shapes30  # noqa: E402  (chapter 30's set)
from gen26 import tidy, db_rows  # noqa: E402

BIOS = '        INCLUDE "bios.inc"\n'
BLACK, DARK_BLUE, CYAN, WHITE = 1, 4, 7, 15
NAME = {BLACK: "black", DARK_BLUE: "dark blue", CYAN: "cyan", WHITE: "white"}
SEND_MARK, LOGIC_MARK, WAIT_MARK = DARK_BLUE, CYAN, WHITE
EU, JP = "MSXBOOK_EU16", "MSXBOOK_JP16"
CLOCK = 3579545
LINE_T = 228
FRAME_T = {EU: 71364, JP: 59736}
LINES = {EU: 313, JP: 262}
PAPER0 = {EU: 69, JP: 42}
FLAG_LINE = {EU: 261, JP: 234}
ATT, PAT, COPY = 0x1B00, 0x3800, 0xC400
REGS = [2, 0xE2, 6, 0xFF, 3, 0x36, 7, 0x0F]        # Graphic II, the signal on, 16 x 16 sprites
TEXT_REGS = [0, 0xE0, 6, 0x80, 0, 0x36, 7, 0x0F]   # seconds.asm: Graphic I


def head(name, what):
    return HEAD.format(name=name, chapter=33, what=what) + BIOS


# ------------------------------------------------------------------ the herd
FIGURE = gen26.big(gen26.FIGURE)        # chapter 26's figure: four patterns, 32 bytes
ROWS, COLS = 8, 4


def herd(steps=0):
    """chapter 26's herd after STEPS moves: 32 figures in eight rows of four,
    23 lines apart, even rows a pixel right a move and odd rows a pixel left"""
    out = []
    for r in range(ROWS):
        for c in range(COLS):
            x = (64 * c + 16 * r + (steps if r % 2 == 0 else -steps)) & 0xFF
            out.append((6 + 23 * r, x, 0, (BLACK, DARK_BLUE)[(r + c) % 2]))
    return out


def herd_bytes(steps=0):
    return bytes(b for s in herd(steps) for b in s)


# ------------------------------------------------------------------ the works
# order.asm's eight works, in turns of 30 T-states, taken in turn: short ones
# between long ones, and the longest more than a frame on both machines
WORKS = [100, 1000, 100, 1500, 100, 1900, 100, 2600]


# ------------------------------------------------------------------ the parts
RAM = f"""ticks   EQU VARS                ; frames counted by isr
last    EQU VARS + 1            ; ticks, the last time the logic looked
k       EQU VARS + 2            ; the work last done, 0 to 7
turns   EQU VARS + 3            ; fits.asm, misses.asm: the work's turns
acc     EQU VARS + 5            ; speed.asm: 256ths of a pixel not yet moved
speed   EQU VARS + 7            ; speed.asm: 256ths of a pixel a frame
copy    EQU ${COPY:04X}               ; the herd's attributes, 128 bytes
"""

ISR = """
; isr: every frame, a frame counted. Keeps AF
isr:    push af                 ; 12
        in a, (VDP_CTRL)        ; 12  the status: the signal down
        ld a, (ticks)           ; 14
        inc a                   ;  5
        ld (ticks), a           ; 14
        pop af                  ; 11
        ei                      ;  5
        ret                     ; 11
"""

STEP = f"""
; step: the herd a pixel on, in the copy: even rows of four a pixel right, odd
; rows a pixel left
step:   ld hl, copy + 1         ; sprite 0's X
        ld de, 4
        ld c, {ROWS // 2}
.row:   ld b, {COLS}
.right: inc (hl)                ; X + 1
        add hl, de
        djnz .right
        ld b, {COLS}
.left:  dec (hl)                ; X - 1
        add hl, de
        djnz .left
        dec c
        jr nz, .row
        ret
"""


def mark(colour, label, say):
    """R#7 written, the interrupts off for the two bytes (chapter 19)"""
    return f"""        di
        ld a, {colour:<18}; {NAME[colour]}
        out (VDP_CTRL), a
        ld a, $87
{label}:{' ' * (7 - len(label))}out (VDP_CTRL), a       ; R#7: {say}
        ei
"""


SEND = f"""        di
        ld a, low ${ATT:04X}
        out (VDP_CTRL), a
        ld a, high ${ATT:04X} | $40
        out (VDP_CTRL), a       ; the attribute table, for writing
        ei
        ld hl, copy
        ld c, VDP_DATA
        ld b, 128
        otir                    ; the herd: 127 x 23 + 18 T-states
s1:
"""

COUNT = """        ld a, (ticks)           ; the frames counted by isr ...
        ld hl, last
        ld b, a
        sub (hl)                ; ... since the last time: A
        ld (hl), b              ; and this is the last time now
        ld b, a
.steps: push bc
        call step               ; a pixel for every frame
        pop bc
        djnz .steps
"""

ONCE = """        call step               ; a pixel, whatever the frames
"""

SPEED = """        ld a, (ticks)           ; the frames counted by isr ...
        ld hl, last
        ld b, a
        sub (hl)                ; ... since the last time
        ld (hl), b
        ld b, a
        ld hl, (acc)            ; 256ths of a pixel not yet moved
        ld de, (speed)          ; and 256ths a frame
.add:   add hl, de
        djnz .add
        ld b, h                 ; the whole pixels ...
        ld h, 0
        ld (acc), hl            ; ... and the 256ths left over
        ld a, b
        or a
        jr z, .moved
.steps: push bc
        call step
        pop bc
        djnz .steps
.moved:
"""

WORK_TABLE = """        ld a, (k)               ; the next of the eight works
        inc a
        and 7
        ld (k), a
        add a, a
        ld e, a
        ld d, 0
        ld hl, works
        add hl, de
        ld c, (hl)
        inc hl
        ld b, (hl)              ; BC: its turns
.work:  dec bc                  ;  7
        ld a, b                 ;  5
        or c                    ;  5
        jr nz, .work            ; 13: 30 T-states a turn
"""

WORK_FIXED = """        ld bc, (turns)          ; the work's turns, for the machine
.work:  dec bc                  ;  7
        ld a, b                 ;  5
        or c                    ;  5
        jr nz, .work            ; 13: 30 T-states a turn
"""


def rate(var, n60, n50):
    return f"""        ld a, ($002B)           ; bit 7 is 1 on a 50 Hz machine (chapter 4)
        rla
        ld hl, {n60}{' ' * (15 - len(str(n60)))}; 60 Hz ...
        jr nc, .r{var}
        ld hl, {n50}{' ' * (15 - len(str(n50)))}; ... and 50 Hz
.r{var}:{' ' * (5 - len(var))}ld ({var}), hl
"""


SETUP = f"""        VRAM_WRITE ${PAT:04X}        ; the figure's four patterns
        ld hl, figure
        ld c, VDP_DATA
        ld b, 32
        otir
        ld hl, herd             ; the herd's attributes, to the copy ...
        ld de, copy
        ld bc, 128
        ldir
        VRAM_WRITE ${ATT:04X}        ; ... and to the VDP
        ld hl, copy
        ld c, VDP_DATA
        ld b, 128
        otir
        xor a
        ld (ticks), a
        ld (last), a
        ld a, 7
        ld (k), a               ; the first work is the first of the eight
"""

ON = """        VDP_REG 1, $E2          ; the display on, the frame's signal, 16 x 16
        in a, (VDP_CTRL)        ; no signal left over
        ei
"""


def loop(logic, work, first=False):
    send = mark(SEND_MARK, "m0", "the herd sent") + SEND
    think = mark(LOGIC_MARK, "m1", "the logic") + logic + work
    body = (think + send) if first else (send + think)
    return ("main:   halt                    ; wait for the frame\n" + body +
            mark(WAIT_MARK, "m2", "waiting") + "        jr main\n")


def program(name, what, say, before, logic, work, first=False, data=""):
    return (head(name, what) + RAM + IM2 + say +
            tidy(GRAPHIC2 + SETUP + before + im2("isr") + ON + loop(logic, work, first) +
                 ISR + STEP) +
            "figure:                         ; chapter 26's figure, 16 x 16\n" + db_rows(FIGURE) +
            "herd:                           ; 32 figures, eight rows of four\n" +
            db_rows(herd_bytes(), 4) + data + CART_END)


def works_data():
    return "works:                          ; turns of 30 T-states\n" + \
        "".join(f"        dw {n}\n" for n in WORKS)


def order():
    return program("order", "a frame loop", f"""; The frame loop: isr counts the frames; the main loop waits with HALT, sends
; the herd after the paper, moves it a pixel for every frame counted, and does
; a work in turn of these T-states:
; {', '.join(f'{30 * n:,}' for n in WORKS)}.
; The border: {NAME[SEND_MARK]} while the herd is sent, {NAME[LOGIC_MARK]} for the logic,
; {NAME[WAIT_MARK]} while the loop waits.
""", "", COUNT, WORK_TABLE, data=works_data())


def nocount():
    return program("nocount", "a frame loop that does not count", """; order.asm, the herd moved one pixel each time round the loop, however many
; frames have passed.
""", "", ONCE, WORK_TABLE, data=works_data())


def first():
    return program("first", "the logic first, the herd after it", """; WHERE IT BREAKS. order.asm with its two parts the other way round: after HALT
; the logic and its work, and the herd sent after them.
""", "", COUNT, WORK_TABLE, first=True, data=works_data())


# fits.asm and misses.asm: the loop's T-states from the interrupt's answer to
# its HALT, the work's turns aside (walked by meas33.py): the answer and the
# JP, isr, the marks, the send, the count with one step, the work's LD BC,(nn)
# and its last turn 5 short. HALT answers within a step of 5 T-states, so the
# loop that fits reaches HALT at least 5 T-states before the frame is over;
# a turn more, 30 T-states, and it does not
LOOP_T = 4759
EDGE_TURN, HALT_STEP = 30, 5


def edge_turns(machine):
    return (FRAME_T[machine] - LOOP_T - HALT_STEP) // EDGE_TURN


def edge(name):
    extra = 1 if name == "misses" else 0
    n60, n50 = (edge_turns(m) + extra for m in (JP, EU))
    say = (f"""; The frame loop with one work, the longest whose loop still reaches HALT before
; the next frame's signal: {n50:,} turns at 50 Hz and {n60:,} at 60 Hz.
""" if name == "fits" else f"""; fits.asm with one turn more: {n50:,} turns at 50 Hz and {n60:,} at 60 Hz.
""")
    return program(name, "a work at the frame's edge" if name == "fits" else "a turn too many",
                   say, rate("turns", n60, n50), COUNT, WORK_FIXED)


SPEED_K = {EU: 306, JP: 256}    # 256ths of a pixel a frame: about 60 pixels a second


def speed():
    return program("speed", "a speed in pixels a second", f"""; order.asm with the herd moved by the time: {SPEED_K[EU]}/256 of a pixel a
; frame at 50 Hz and {SPEED_K[JP]}/256 at 60 Hz, kept in 256ths, about 60 pixels a
; second on both.
""", rate("speed", SPEED_K[JP], SPEED_K[EU]) + """        ld hl, 0
        ld (acc), hl
""", SPEED, WORK_TABLE, data=works_data())


# ------------------------------------------------------------------ seconds.asm
PER = {EU: (44, 2207), JP: (13, 779)}   # a frame's share of a second, and a second
FONT = shapes30.wide()                  # codes 32 to 127
TEXT_ROWS = [(8, "frames"), (10, "seconds, chapter 17"), (12, "seconds, kept")]
NUM_COL = 24


def text_names():
    n = [32] * 768
    for row, text in TEXT_ROWS:
        for i, ch in enumerate(text):
            n[32 * row + 2 + i] = ord(ch)
    return n


SECONDS_RAM = """frames  EQU VARS + 16           ; frames counted by isr
secs17  EQU VARS + 18           ; chapter 17's seconds: 50 or 60 frames each
count   EQU VARS + 20           ; frames left in chapter 17's second
rate    EQU VARS + 21           ; 50 or 60
secs    EQU VARS + 22           ; the seconds kept
part    EQU VARS + 24           ; a second's worth gathered, in shares
per     EQU VARS + 26           ; the shares of a frame: 44 or 13
full    EQU VARS + 28           ; the shares of a second: 2,207 or 779
"""

SECONDS_ISR = """
; isr: every frame. The frames; chapter 17's clock, a second every 50 or 60
; frames; and the clock that keeps time, PER shares a frame and a second every
; FULL shares. Keeps AF, DE and HL
isr:    push af
        push hl
        push de
        in a, (VDP_CTRL)        ; the status: the signal down
        ld hl, (frames)
        inc hl
        ld (frames), hl
        ld hl, count            ; chapter 17's clock
        dec (hl)
        jr nz, .kept
        ld a, (rate)
        ld (hl), a
        ld hl, (secs17)
        inc hl
.t17:   ld (secs17), hl         ; a second, chapter 17's
.kept:  ld hl, (part)           ; the clock that keeps time
        ld de, (per)
        add hl, de
        ld de, (full)
        or a
        sbc hl, de
        jr c, .not
        ld (part), hl           ; a second's shares taken off
        ld hl, (secs)
        inc hl
.tk:    ld (secs), hl           ; a second, kept
        jr .out
.not:   add hl, de              ; not a second yet
        ld (part), hl
.out:   pop de
        pop hl
        pop af
        ei
        ret
"""

PRINT = """
; at: the next characters go to row D, column E (chapter 30)
at:     ld a, d
        rrca
        rrca
        rrca
        ld c, a
        and $E0
        or e
        out (VDP_CTRL), a
        ld a, c
        and $03
        or $18 | $40
        out (VDP_CTRL), a
        ret

; digits: HL as five decimal digits to the address set (chapter 30)
digits: ld bc, tens
.digit: ld a, (bc)
        ld e, a
        inc bc
        ld a, (bc)
        ld d, a
        inc bc
        ld a, '0' - 1
.count: inc a
        or a
        sbc hl, de
        jr nc, .count
        add hl, de
        out (VDP_DATA), a
        ld a, e
        dec a
        jr nz, .digit
        ret
tens:   dw 10000, 1000, 100, 10, 1

; fill: E blocks of 256 bytes of A to the VDP, after an address is set
fill:   ld b, 0
.out:   out (VDP_DATA), a
        djnz .out
        dec e
        jr nz, .out
        ret

; send: E blocks of 256 bytes from HL to the VDP
send:   ld c, VDP_DATA
        ld b, 0
.otir:  otir
        dec e
        jr nz, .otir
        ret
"""


def show(row, var):
    return f"""        ld d, {row}
        ld e, {NUM_COL}
        call at
        ld hl, ({var})
        call digits
"""


def seconds():
    p50, f50 = PER[EU]
    p60, f60 = PER[JP]
    body = f"""init:   di
        ld sp, SYS_AREA
        VDP_REG 1, $80          ; display off
        VDP_REG 0, $00          ; Graphic I
        VDP_REG 2, $06          ; names    $1800
        VDP_REG 3, $80          ; colours  $2000
        VDP_REG 4, $00          ; patterns $0000
        VDP_REG 5, $36          ; sprite attributes $1B00
        VDP_REG 6, $07          ; sprite patterns   $3800
        VDP_REG 7, $0F          ; border white
        VRAM_WRITE $0000        ; patterns: none, chapter 30's set at 32
        xor a
        ld e, 1
        call fill
        ld hl, font
        ld e, 3
        call send
        VRAM_WRITE $2000        ; black ink on white paper
        ld a, $1F
        ld b, 32
.col:   out (VDP_DATA), a
        djnz .col
        VRAM_WRITE $1800        ; the names: the three labels
        ld hl, names
        ld e, 3
        call send
        VRAM_WRITE $1B00        ; no sprites
        ld a, $D0
        out (VDP_DATA), a
        ld a, ($002B)           ; bit 7 is 1 on a 50 Hz machine (chapter 4)
        rla
        ld a, 60
        ld hl, {p60}
        ld de, {f60}
        jr nc, .hz
        ld a, 50
        ld hl, {p50}
        ld de, {f50}
.hz:    ld (rate), a
        ld (count), a
        ld (per), hl
        ld (full), de
        ld hl, 0
        ld (frames), hl
        ld (secs17), hl
        ld (secs), hl
        ld (part), hl
""" + im2("isr") + """        VDP_REG 1, $E0          ; the display on, and the frame's signal
        in a, (VDP_CTRL)
main:   ei
        halt                    ; wait for the frame
        di                      ; the interrupts off while the VDP is written
""" + show(TEXT_ROWS[0][0], "frames") + show(TEXT_ROWS[1][0], "secs17") + \
        show(TEXT_ROWS[2][0], "secs") + "        jr main\n"
    return (head("seconds", "a clock that keeps time") + SECONDS_RAM + IM2 + f"""; Two clocks kept by the interrupt: chapter 17's, which counts 50 or 60 frames
; to a second, and one that counts {f50:,} frames as {p50} seconds at 50 Hz
; and {f60} as {p60} at 60 Hz (chapter 18). The main loop prints the frames and
; both clocks.
""" + tidy(body + SECONDS_ISR + PRINT) +
        "names:                          ; 24 rows of 32\n" + db_rows(text_names(), 16) +
        "font:                           ; chapter 30's set, codes 32 to 127\n" + db_rows(FONT, 16) +
        CART_END)


PROGRAMS = {"order": order, "nocount": nocount, "fits": lambda: edge("fits"),
            "misses": lambda: edge("misses"), "speed": speed, "seconds": seconds, "first": first}


def main():
    for name, make in PROGRAMS.items():
        with open(os.path.join(HERE, f"{name}.asm"), "w") as f:
            f.write(make())
    print(" ".join(f"{n}.asm" for n in PROGRAMS))


if __name__ == "__main__":
    main()
