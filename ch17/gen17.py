#!/usr/bin/env python3
"""gen17.py - the programs of chapter 17: the interrupt, taken over.

    python3 gen17.py && ./build.sh

    modes.asm      one interrupt in each of the three modes, 2, 1 and 0, each
                   after a HALT: where it goes, how long it takes, what it
                   leaves on the stack, and which bytes of the table mode 2
                   reads.
    bios.asm       a program that only waits for the next frame, with the
                   BIOS's routine taking the interrupts: what that routine
                   costs, frame after frame.
    timi.asm       the same, with a routine of the program's own in the hook
                   H.TIMI.
    clock.asm      a frame of the program's own: mode 2, a routine that counts
                   frames and seconds, 50 or 60 frames to the second as the
                   machine says, and a main loop that prints them (figure
                   17.1).
    saved.asm      a routine that saves AF, while the main loop paints the
    unsaved.asm    name table with the character in A; and one that does not
                   (figure 17.2).
    iff.asm        LD A,I, which tells a routine whether the interrupts were
                   on: called as usual, and with the frame's signal coming while
                   it runs.
    late.asm       interrupts switched off across the frame's signal, for
                   less than a frame, for more than two, and with the status
                   read while they were off: when is the interrupt taken?
    nokeys.asm     mode 2, and then CHGET: the keyboard, which the BIOS's
                   routine reads, is never read.
    chain.asm      a routine of the program's own that goes on into the
                   BIOS's: CHGET gets its key.
    steal.asm      the same routine, but it reads the status first.
    forgot.asm     WHERE IT BREAKS: a routine that does not read the status
                   (figure 17.3).

Every program includes bios.inc (chapter 16). Cartridges end with
asmparts.CART_END and build.sh assembles with --syntax=bFw (chapter 15).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
from asmparts import (HEAD, CART_END, TEXT_PAGE, library, PUTD16,  # noqa: E402
                      IM2, IM2_TABLE_AT, IM2_VECTOR, im2)

RESULTS = "RESULTS EQU RAM_START          ; what the program found: the debugger reads it here\n"
BIOS = '        INCLUDE "bios.inc"\n'

# mode 2: the table and its jump, as tools/asmparts.py builds them
TABLE = IM2_TABLE_AT
VECTOR = IM2_VECTOR
T_TAKE = {0: 13, 1: 13, 2: 19}      # Zilog: taking an interrupt, by mode
FRAME_T = 71364             # a frame of the 50 Hz machine (tools/meas.py)


def head(name, what):
    return HEAD.format(name=name, chapter=17, what=what) + BIOS


def write(name, text):
    with open(os.path.join(HERE, f"{name}.asm"), "w") as f:
        f.write("\n".join(l.rstrip() for l in text.split("\n")))      # no spaces at line ends


# ----------------------------------------------------------------- modes.asm
def modes():
    return head("modes", "one interrupt in each mode") + IM2 + """; The same interrupt taken in the three modes, one frame each: mode 2
; through the table, mode 1 to the BIOS's routine at $0038, and mode 0, which
; runs the instruction it finds on the bus. Each waits with HALT.
init:   di
        ld sp, SYS_AREA
""" + im2("isr2") + """e2:     in a, (VDP_CTRL)        ; no signal left over from before
        ei
        halt                    ; mode 2: the address in the table
        di
        im 1
e1:     in a, (VDP_CTRL)
        ei
        halt                    ; mode 1: $0038
        di
        im 0
e0:     in a, (VDP_CTRL)
        ei
        halt                    ; mode 0: the byte on the bus
        di
stop:   jr stop

; isr2: mode 2's routine: the status read, and back
isr2:   in a, (VDP_CTRL)        ; the VDP takes its signal down
        ei
        ret
""" + CART_END


# ------------------------------------------------------------------ bios.asm
def bios(name="bios", hook=False):
    what = "the BIOS's routine, with a hook of the program's own" if hook else \
        "the BIOS's routine, every frame"
    text = head(name, what) + (RESULTS + "ticks   EQU RESULTS             ; frames tick has counted\n"
                               if hook else "") + f"""; A program that does nothing but wait for the next frame, in mode 1: the
; BIOS's routine takes every interrupt{', and calls tick through H.TIMI' if hook else ''}.
init:   di
        ld sp, SYS_AREA
        im 1
"""
    if hook:
        text += """        ld hl, 0
        ld (ticks), hl
        ld hl, tick             ; H.TIMI: JP tick, written with the
        ld (H_TIMI + 1), hl     ; interrupts off, so that no interrupt
        ld a, $C3               ; can find half a jump there
        ld (H_TIMI), a
"""
    text += """        in a, (VDP_CTRL)        ; no signal left over from before
        ei
main:   halt                    ; the BIOS's routine runs, and comes back here
        jr main
"""
    if hook:
        text += """
; tick: called by the BIOS through H.TIMI every frame, with A = the status it
;       read. The BIOS has saved every register: tick may use any.
tick:   ld hl, (ticks)
        inc hl
        ld (ticks), hl
        ret
"""
    return text + CART_END


# ----------------------------------------------------------------- clock.asm
CLOCK_ROW = 10
CLOCK_ISR = """
; isr: every frame. Counts the frames, and the seconds: 50 frames to the
;      second on a 50 Hz machine, 60 on a 60 Hz one. Keeps AF and HL.
isr:    push af
        push hl
        in a, (VDP_CTRL)        ; the status: the VDP takes its signal down
        ld hl, (frames)
        inc hl
        ld (frames), hl
        ld hl, count
        dec (hl)                ; frames left in this second
        jr nz, isr1
        ld a, (rate)
        ld (hl), a              ; a new second
        ld hl, (seconds)
        inc hl
        ld (seconds), hl
isr1:   pop hl
        pop af
        ei
        ret
"""


def clock():
    return head("clock", "a frame of the program's own") + IM2 + \
        """frames  EQU VARS + 16           ; frames counted by isr
seconds EQU VARS + 18           ; and seconds
count   EQU VARS + 20           ; frames left in this second
rate    EQU VARS + 21           ; frames in a second: 50 or 60
; A routine of the program's own counts frames and seconds; the main loop
; waits for each frame and prints them.
""" + TEXT_PAGE + f"""        ld b, {CLOCK_ROW}
        ld c, 8
        ld hl, t_fr
        call puts
        ld b, {CLOCK_ROW + 2}
        ld c, 8
        ld hl, t_sec
        call puts
        ld a, ($002B)           ; bit 7 is 1 on a 50 Hz machine (chapter 4)
        rlca                    ; bit 7 into the carry
        ld a, 60
        jr nc, hz60
        ld a, 50
hz60:   ld (rate), a
        ld (count), a
        ld hl, 0
        ld (frames), hl
        ld (seconds), hl
""" + im2("isr") + f"""        VDP_REG 1, $E0          ; display on, and the frame's signal on
        in a, (VDP_CTRL)        ; no signal left over from before
        ei
main:   halt                    ; wait for the frame
        ld hl, (frames)         ; and print, a frame from the next interrupt
        ld b, {CLOCK_ROW}
        ld c, 18
        call putd16
        ld hl, (seconds)
        ld b, {CLOCK_ROW + 2}
        ld c, 18
        call putd16
        jr main
""" + CLOCK_ISR + """
t_fr:   db "frames", 0
t_sec:  db "seconds", 0
""" + library(PUTD16) + CART_END


# ------------------------------------------------------- saved.asm, unsaved.asm
SLOW = 40                   # turns of the wait between two cells
FIRST = "."                 # what the main loop paints until the first interrupt


def paint(name, save):
    if save:
        isr = """isr:    push af                 ; A is the main loop's: keep it
        in a, (VDP_CTRL)        ; the status: the VDP takes its signal down
        ld a, (ticks)
        inc a
        ld (ticks), a
        pop af
"""
    else:
        isr = """isr:    in a, (VDP_CTRL)        ; the status: the VDP takes its signal down
        ld a, (ticks)
        inc a
        ld (ticks), a
"""
    return head(name, "a routine that " + ("saves" if save else "does not save") + " AF") + \
        IM2 + """ticks   EQU VARS + 16           ; frames counted, as characters from '0'
; The main loop paints the 768 cells of the name table with the character in
; A, slowly; the routine counts the frames, in A.
""" + TEXT_PAGE + """        ld a, '0'
        ld (ticks), a
""" + im2("isr") + f"""        VDP_REG 1, $E0          ; display on, and the frame's signal on
        VRAM_WRITE $1800        ; the name table, from its first cell
        ld c, 3                 ; 3 x 256 cells
        ld b, 0
        in a, (VDP_CTRL)        ; no signal left over from before
        ld a, '{FIRST}'               ; the character the loop paints
        ei
cell:   out (VDP_DATA), a       ; one cell, with the character in A
        ld d, {SLOW}
slow:   dec d
        jr nz, slow             ; a while, so that the painting takes frames
        djnz cell
        dec c
        jr nz, cell
stop:   jr stop

; isr: counts the frames, in A
""" + isr + """        ei
        ret
""" + library() + CART_END


# ------------------------------------------------------------------ late.asm
# the waits, in turns of chapter 14's loop (30 T-states a turn, 35 more for
# the CALL, the LD and the RET): interrupts off from just after one frame's
# interrupt, for about half a frame past the next signal; for about two and a
# half frames; and for half a frame again, with the status read before EI
LATE_WAITS = {"w1": 3600, "w2": 6000, "w3": 3600}


def late():
    return head("late", "the interrupts off across the frame's signal") + IM2 + RESULTS + \
        """ticks   EQU RESULTS             ; interrupts taken
; Three times the interrupts are switched off just after a frame's interrupt
; and on again later: past the next signal, past two more, and past the next
; with the status read before EI.
init:   di
        ld sp, SYS_AREA
        xor a
        ld (ticks), a
""" + im2("isr") + """        in a, (VDP_CTRL)        ; no signal left over from before
        ei
        halt                    ; a frame's interrupt
        di
        ld de, {w1}
        call wait               ; past the next signal
l1:     ei
        nop
        nop
        halt                    ; and the next frame's interrupt
        di
        ld de, {w2}
        call wait               ; past two more
l2:     ei
        nop
        nop
        halt
        di
        ld de, {w3}
        call wait               ; past the next, and then
        in a, (VDP_CTRL)        ; the status read
l3:     ei
        nop
        nop
        halt
        di
stop:   jr stop

; isr: counts the interrupts taken
isr:    push af
        in a, (VDP_CTRL)        ; the status: the VDP takes its signal down
        ld a, (ticks)
        inc a
        ld (ticks), a
        pop af
        ei
        ret

; wait: DE turns of chapter 14's loop, 30 T-states each. Uses A, DE.
wait:   dec de
        ld a, d
        or e
        jr nz, wait
        ret
""".format(**LATE_WAITS) + CART_END


# ------------------------------------------------------------------- iff.asm
# keep and keep2 are called a third time and a fourth just as a frame's signal
# comes, so that the interrupt is taken right after their first LD A,I: the
# waits, in turns of chapter 14's loop and NOPs, from the instruction after a
# HALT; meas17.py checks where the signal fell
IFF_WAITS = {"w3": (2372, 4), "w4": (2372, 4)}


def iff():
    def wait(k):
        turns, nops = IFF_WAITS[k]
        return f"        ld de, {turns}\n        call wait\n" + "        nop\n" * nops
    return head("iff", "LD A,I: the interrupts on or off") + IM2 + RESULTS + \
        """ticks   EQU RESULTS             ; interrupts taken
; keep writes the border's register with the interrupts off and leaves them as
; it found them; keep2 asks twice. Both are called with the interrupts on and
; off, and then with the frame's signal coming while their LD A,I runs.
init:   di
        ld sp, SYS_AREA
        xor a
        ld (ticks), a
""" + im2("isr") + """        in a, (VDP_CTRL)        ; no signal left over from before
        ei
        halt
        ld b, LIGHT_GREEN
        call keep               ; 1: the interrupts on
a1:     di
        ld b, BLACK
        call keep               ; 2: off
a2:     ei
        halt
""" + wait("w3") + """        ld b, LIGHT_GREEN
        call keep               ; 3: on, and the signal comes during LD A,I
a3:     ei
        halt
""" + wait("w4") + """        ld b, BLACK
        call keep2              ; 4: the same, with keep2
a4:     di
stop:   jr stop

; keep: B into VDP register 7, the border, with the interrupts off; and then
;       the interrupts as they were. Uses A, F.
keep:   ld a, i                 ; P/V: IFF2, the interrupts on or off
        di
k1:     ld a, b
        out (VDP_CTRL), a
        ld a, $87
        out (VDP_CTRL), a
        ret po                  ; they were off: leave them off
        ei
        ret

; keep2: the same, but asks twice when the answer is off
keep2:  ld a, i
        jp pe, k2on             ; on: that answer is sure
k2ask:  ld a, i                 ; off, or an interrupt came just after the first
k2on:   di
        ld a, b
        out (VDP_CTRL), a
        ld a, $87
        out (VDP_CTRL), a
        ret po
        ei
        ret

; isr: counts the interrupts
isr:    push af
        in a, (VDP_CTRL)        ; the status: the VDP takes its signal down
        ld a, (ticks)
        inc a
        ld (ticks), a
        pop af
        ei
        ret

; wait: DE turns of chapter 14's loop, 30 T-states each. Uses A, DE.
wait:   dec de
        ld a, d
        or e
        jr nz, wait
        ret
""" + CART_END


# ------------------------------------------------- nokeys, chain and steal
KEY_FRAME = 140             # the space bar goes down: after the BIOS's first look (127)
KEY_UP = 150
KEY_FRAMES = 200


def keys(name, what, isr, comment):
    return head(name, what) + IM2 + RESULTS + """ticks   EQU RESULTS             ; frames the program's routine counted
key     EQU RESULTS + 2         ; what CHGET gave
""" + comment + """init:   di
        ld sp, SYS_AREA
        ld hl, 0
        ld (ticks), hl
        ld a, $FF
        ld (key), a
""" + im2("isr") + """        in a, (VDP_CTRL)        ; no signal left over from before
        ei
k1:     call CHGET              ; a key, through the BIOS
k2:     ld (key), a
stop:   jr stop
""" + isr + CART_END


NOKEYS_ISR = """
; isr: counts the frames
isr:    push af
        push hl
        in a, (VDP_CTRL)        ; the status: the VDP takes its signal down
        ld hl, (ticks)
        inc hl
        ld (ticks), hl
        pop hl
        pop af
        ei
        ret
"""
CHAIN_ISR = """
; isr: counts the frames, and goes on into the BIOS's routine, which reads
;      the status, reads the keyboard and returns from the interrupt
isr:    push hl
        ld hl, (ticks)
        inc hl
        ld (ticks), hl
        pop hl
        jp $0038
"""
STEAL_ISR = """
; isr: reads the status, counts the frames, and goes on into the BIOS's
;      routine
isr:    push af
        in a, (VDP_CTRL)        ; the status: the VDP takes its signal down
        pop af
        push hl
        ld hl, (ticks)
        inc hl
        ld (ticks), hl
        pop hl
        jp $0038
"""


# ---------------------------------------------------------------- forgot.asm
def forgot():
    return head("forgot", "WHERE IT BREAKS: a routine that does not read the status") + IM2 + \
        RESULTS + """turns   EQU RESULTS             ; turns of the main loop
band    EQU RESULTS + 2         ; the border's colour
; WHERE IT BREAKS. The routine changes the colour of the border and returns,
; and never reads the status. The display is off: the border is the screen.
init:   di
        ld sp, SYS_AREA
        ld hl, 0
        ld (turns), hl
        ld a, BLACK
        ld (band), a
        VDP_REG 7, BLACK
""" + im2("isr") + """        VDP_REG 1, $A0          ; display off, and the frame's signal on
        in a, (VDP_CTRL)        ; no signal left over from before
        ei
main:   ld hl, (turns)
        inc hl
        ld (turns), hl          ; the main loop counts its turns
        jr main

; isr: the border in the other colour. It does not read the status.
isr:    push af
        ld a, (band)
        xor BLACK ^ LIGHT_GREEN
        ld (band), a
        out (VDP_CTRL), a
        ld a, $87               ; register 7: the border
o1:     out (VDP_CTRL), a
        pop af
        ei
        ret
""" + CART_END


def main():
    files = {
        "modes": modes(), "bios": bios(), "timi": bios("timi", hook=True), "clock": clock(),
        "saved": paint("saved", True), "unsaved": paint("unsaved", False), "late": late(),
        "nokeys": keys("nokeys", "mode 2, and then CHGET", NOKEYS_ISR, """; Mode 2 and a routine of the program's own; then CHGET, which waits for the
; key that the BIOS's routine would have read.
"""),
        "chain": keys("chain", "a routine that goes on into the BIOS's", CHAIN_ISR, """; Mode 2, and a routine that counts the frames and goes on into the BIOS's
; routine; then CHGET.
"""),
        "steal": keys("steal", "a routine that reads the status, then the BIOS's", STEAL_ISR,
                      """; The same, but the program's routine reads the status before it goes on
; into the BIOS's.
"""),
        "forgot": forgot(), "iff": iff()}
    for name, text in files.items():
        write(name, text)
    print(len(files), "sources written")


if __name__ == "__main__":
    main()
