#!/usr/bin/env python3
"""gen04.py - the programs of chapter 4.

    python3 gen04.py && ./build.sh

    check.asm    the first program to run on your own tools. It prints the
                 version of the assembler that built it (sjasmplus writes it
                 in, from __VERSION__), the sum of the BIOS in page 0, the
                 two bytes in which every MSX BIOS describes its machine
                 ($002B and $002D), the lowest address of RAM the BIOS found,
                 and how many turns of a 37 T-state loop fit between two
                 frame flags of the VDP.
    case.asm     includes "MSX.INC" while the file is msx.inc: an error on
                 Linux, not on Windows. It writes no file; it is assembled
                 only to see whether it can be.
    edge.asm     the stripes of chapter 3's nops.asm, three of them moved: one
                 starts left of the border a TMS9918 draws, one inside it, one
                 ends right of it. openMSX 20.0 and later show only the border
                 the chip draws, and paint what lies outside it the colour of
                 its edge.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "ch03"))
from asmparts import HEAD, TAIL, TEXT_PAGE, library, PUTD16  # noqa: E402
import gen03  # noqa: E402

TURN_T = 37                 # INC HL 7, IN A,(n) 12, RLCA 5, JR NC taken 13
ROWS = {"title": 1, "asm": 3, "sum": 5, "hz": 7, "msx": 8, "ram": 10, "turns": 12}
VALUE_COL = 11
MSX_NAMES = ["MSX1", "MSX2", "MSX2+", "turbo R"]
# edge.asm: (T-states later than nops.asm's stripes start, NOPs) for each stripe
EDGE = [(-8, 0), (0, 16), (82, 16)]
# the columns of the capture a TMS9918 draws: the paper is 32-287, and the
# data sheet's border is 13 pixels on the left and 15 on the right
DRAWN = (32 - 13, 32 + 256 + 15 - 1)
LAST_X = 319


def check():
    return HEAD.format(name="check", chapter=4, what="what runs this cartridge") + f"""turns   EQU VARS + 16           ; the turns of the loop in one frame
sum     EQU VARS + 18           ; the sum of page 0
BOTTOM  EQU $FC48               ; BIOS work area: the lowest address of RAM
""" + TEXT_PAGE + f"""        VDP_REG 1, $C0          ; display on, no interrupts: the program polls
        in a, (VDP_CTRL)        ; clear a flag left from before
.sync:  in a, (VDP_CTRL)        ; wait for the frame flag ...
        rlca
        jr nc, .sync
        ld hl, 0
turn:   inc hl                  ; ... then count until it comes up again
        in a, (VDP_CTRL)
        rlca
        jr nc, turn
        ld (turns), hl
        ld hl, 0                ; the sum of $0000-$3FFF, the BIOS's page
        ld ix, 0
        ld b, 0
.add:   ld c, (hl)
        add ix, bc
        inc hl
        ld a, h
        cp $40
        jr nz, .add
        ld (sum), ix
        ld b, {ROWS['title']}
        ld c, 0
        ld hl, t_title
        call puts
        ld b, {ROWS['asm']}
        ld c, 0
        ld hl, t_asm
        call puts
        ld c, {VALUE_COL}
        ld hl, t_ver            ; written by the assembler, not by the program
        call puts
        ld b, {ROWS['sum']}
        ld c, 0
        ld hl, t_sum
        call puts
        ld c, {VALUE_COL}
        ld a, (sum + 1)
        call puthex
        ld a, (sum)
        call puthex
        ld b, {ROWS['hz']}      ; $002B, bit 7: 1 for 50 Hz, 0 for 60
        ld c, 0
        ld hl, t_2b
        call puts
        ld c, {VALUE_COL}
        ld a, ($002B)
        call puthex
        inc c
        inc c
        ld hl, t_60
        ld a, ($002B)
        rlca
        jr nc, .hz
        ld hl, t_50
.hz:    call puts
        ld b, {ROWS['msx']}     ; $002D: 0 MSX1, 1 MSX2, 2 MSX2+, 3 turbo R
        ld c, 0
        ld hl, t_2d
        call puts
        ld c, {VALUE_COL}
        ld a, ($002D)
        call puthex
        inc c
        inc c
        ld a, ($002D)
        cp {len(MSX_NAMES)}
        jr c, .known
        ld a, {len(MSX_NAMES)}
.known: add a, a
        ld e, a
        ld d, 0
        ld hl, names
        add hl, de
        ld a, (hl)
        inc hl
        ld h, (hl)
        ld l, a
        call puts
        ld b, {ROWS['ram']}
        ld c, 0
        ld hl, t_ram
        call puts
        ld c, {VALUE_COL}
        ld a, (BOTTOM + 1)
        call puthex
        ld a, (BOTTOM)
        call puthex
        ld b, {ROWS['turns']}
        ld c, 0
        ld hl, t_turns
        call puts
        ld c, {VALUE_COL}
        ld hl, (turns)
        call putd16
        ld hl, t_of
        call puts
done:   jr done

t_title: db "check: what runs this cartridge", 0
t_asm:  db "assembler", 0
t_ver:  db "sjasmplus ", __VERSION__, 0
t_sum:  db "BIOS sum", 0
t_2b:   db "$002B", 0
t_50:   db "50 Hz", 0
t_60:   db "60 Hz", 0
t_2d:   db "$002D", 0
t_ram:  db "RAM from", 0
t_turns: db "turns", 0
t_of:   db " of {TURN_T} T", 0
names:  dw {", ".join(f"n{k}" for k in range(len(MSX_NAMES) + 1))}
""" + "\n".join(f'n{k}:     db "{n}", 0' for k, n in enumerate(MSX_NAMES + ["?"])) + "\n" + \
        library(PUTD16) + TAIL


def case():
    return """; case.asm -- chapter 4: a file name in the wrong letter case
; generated by gen04.py
        INCLUDE "MSX.INC"       ; the file in this folder is msx.inc
        ORG $4000
        ld a, VDP_DATA
"""


def edge():
    return gen03.nops(stripes=EDGE, name="edge", chapter=4,
                      what="border stripes at the edges of the picture")


def main():
    files = {"check.asm": check(), "case.asm": case(), "edge.asm": edge()}
    for name, text in files.items():
        with open(os.path.join(HERE, name), "w") as f:
            f.write(text)
    print(len(files), "sources written")


if __name__ == "__main__":
    main()
