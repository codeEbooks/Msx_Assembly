#!/usr/bin/env python3
"""gen19.py - the programs of chapter 19: talking to the VDP.

    python3 gen19.py && ./build.sh

    ports.asm      the ports the BIOS names at $0006 and $0007, printed, and
                   the same 26 letters written three ways: OUT (n),A to $98;
                   OUT (C),A with C read from $0007; OUTI.
    regs.asm       the eight registers as TEXT_PAGE leaves them; R#7 written
                   with the second byte $87, $8F, $C7 and $FF; a byte sent to
                   $98 with no address after a register write; and a first
                   byte forgotten when the status is read, or a byte is
                   written, before the second.
    address.asm    a text at an address of two bytes; 64 bytes after one
                   address; and eight bytes from $3FFC, four of them past the
                   top of the VRAM, that land on character 0 (figure 19.1).
    readback.asm   reading the VRAM: a copy through the RAM; a loop that reads
                   a byte and writes it back with one address; and the same
                   with an address for every byte (figure 19.2).
    status.asm     the status read in a loop with the interrupts off and the
                   VDP's interrupt off too: the frame flag still comes, and
                   the border shows where the loop saw it (figure 19.3, both
                   machines).
    split.asm      WHERE IT BREAKS: three texts printed over and over with the
                   library's at and the interrupts on; an interrupt between
                   the two bytes of an address (figure 19.4).
    fixed.asm      the same with the at of asmparts.AT_ON: the interrupts off
                   round the two bytes (figure 19.4).
    share.asm      fixed.asm with an interrupt routine that prints the frame
                   count on the screen too: the texts' bytes after the address
                   (figure 19.5).
    whole.asm      share.asm with the interrupts off round each text, the
                   address and every byte (figure 19.5).
    bios.asm       the BIOS's routines for the VRAM, WRTVRM, SETWRT, RDVRM and
                   FILVRM, each called once with the interrupts off.

Every price is the MSX's: Zilog's plus one for every M1 (chapter 14). Every
write to the VRAM comes at least 29 T-states after the access before it, the
rule chapter 20 measures. Cartridges end with asmparts.CART_END and build.sh
assembles with --syntax=bFw (chapter 15).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
from asmparts import HEAD, CART_END, TEXT_PAGE, SHOW_PAGE, library, IM2, im2  # noqa: E402

BIOS = '        INCLUDE "bios.inc"\n'
NAMES = 0x1800              # the name table of TEXT_PAGE
# MSX prices, chapter 14
P = {"nop": 5, "ld r,n": 8, "ld a,(hl)": 8, "out (n),a": 12, "out (c),r": 14, "outi": 18,
     "inc hl": 7, "djnz": 14, "djnz_not": 9, "jp": 11, "in a,(n)": 12, "and a": 5,
     "ld a,i": 11, "or n": 8, "or a": 5, "ret z_not": 6, "jr": 13, "inc r": 5}

ABC = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def head(name, what):
    return HEAD.format(name=name, chapter=19, what=what) + BIOS


def addr(row, col):
    return NAMES + 32 * row + col


def db(text):
    return '        db "' + text + '", 0\n'


# ----------------------------------------------------------------- ports.asm
PORT_ROWS = (6, 8, 10)      # the three copies of the alphabet, from column 3
PORT_COL = 3


def ports():
    r1, r2, r3 = (addr(r, PORT_COL) for r in PORT_ROWS)

    def by_c(a):
        """the write address A sent through port C + 1"""
        return (f"        inc c                   ; the next port: registers and addresses\n"
                f"        ld a, ${a & 0xFF:02X}\n        out (c), a\n"
                f"        ld a, ${a >> 8 | 0x40:02X}\n        out (c), a\n        dec c\n")
    return head("ports", "the ports, written in the code or read from the BIOS") + """; The two bytes at $0006 and $0007, printed; then the alphabet written three
; times, with three ways of reaching the port.
""" + TEXT_PAGE + """        ld b, 2
        ld c, 2
        ld hl, t_dr
        call puts
        ld a, (VDP_DR)          ; the port the VRAM is read from
        call puthex
        ld b, 3
        ld c, 2
        ld hl, t_dw
        call puts
        ld a, (VDP_DW)          ; the port it is written to
        call puthex
""" + f"""l1:     VRAM_WRITE ${r1:04X}        ; 1: OUT (n),A, the port in the code
        ld hl, abc
        ld b, 26
w1:     ld a, (hl)              ;  8
        out (VDP_DATA), a       ; 12
        inc hl                  ;  7
        djnz w1                 ; 14: 41 a byte
l2:     ld a, (VDP_DW)          ; 2: OUT (C),A, the port from the BIOS
        ld c, a
""" + by_c(r2) + """        ld hl, abc
        ld b, 26
w2:     ld a, (hl)              ;  8
        out (c), a              ; 14
        inc hl                  ;  7
        djnz w2                 ; 14: 43 a byte
l3:     ld a, (VDP_DW)          ; 3: OUTI, which takes the port from C
        ld c, a
""" + by_c(r3) + """        ld hl, abc
        ld b, 26
w3:     outi                    ; 18: (HL) to port C, HL + 1, B - 1
        jp nz, w3               ; 11: 29 a byte
l4:
""" + SHOW_PAGE + """
t_dr:""" + db("VDP_DR ($0006): $") + "t_dw:" + db("VDP_DW ($0007): $") + \
        'abc:    db "' + ABC + '"\n' + library() + CART_END


# ------------------------------------------------------------------ regs.asm
# R#7 written with four second bytes; each pair's first byte a colour
SECOND = [(0x87, "LIGHT_GREEN"), (0x8F, "DARK_BLUE"), (0xC7, "BLACK"), (0xFF, "DARK_RED")]
STRAY = "'*'"


def regs():
    pairs = ""
    for k, (b2, colour) in enumerate(SECOND, 1):
        pairs += f"""r{k}:     ld a, {colour}
        out (VDP_CTRL), a
        ld a, ${b2:02X}               ; bit 7: a register; bits 2-0: which
        out (VDP_CTRL), a
"""
    return head("regs", "the eight registers, and the bytes that write them") + """; TEXT_PAGE writes the eight registers. Then R#7, the border, four times, with
; four second bytes; a byte sent to $98 with no address of its own; and two
; first bytes that the VDP forgets.
""" + TEXT_PAGE + "r0:\n" + pairs + """r5:     ld a, WHITE
        out (VDP_CTRL), a
        ld a, $87
        out (VDP_CTRL), a       ; the border white again
        ld a, """ + STRAY + """
        out (VDP_DATA), a       ; a byte and no address: where does it go?
        nop
        nop
        nop
r6:     ld a, LIGHT_GREEN       ; a first byte...
        out (VDP_CTRL), a
        in a, (VDP_CTRL)        ; ...the status read...
        ld a, $87
        out (VDP_CTRL), a       ; ...and the second byte
r7:     in a, (VDP_CTRL)        ; the status again: the $87 forgotten too
r8:     ld a, LIGHT_GREEN       ; a first byte...
        out (VDP_CTRL), a
        ld a, ' '
        out (VDP_DATA), a       ; ...a byte to the VRAM...
        nop
        nop
        nop
        ld a, $87
        out (VDP_CTRL), a       ; ...and the second byte
r9:     in a, (VDP_CTRL)        ; forgotten: back in step
r10:
""" + SHOW_PAGE + library() + CART_END


# --------------------------------------------------------------- address.asm
TITLE_AT = (2, 2)
TITLE = "$1842: TWO BYTES, $42 THEN $58"
LONG_AT = (5, 0)
LONG = ("ONE ADDRESS AND 64 BYTES: AFTER "      # row 5: 32 characters
        "EACH BYTE THE VDP ADDS ONE TO IT")     # row 6: 32 more
WRAP_FROM = 0x3FFC          # eight bytes from here: four at the top, four at $0000
WRAP_N = 8
CHAR0_AT = (10, 4)          # a row of character 0, whose shape the wrap writes
CHAR0_N = 24
CHAR0_LABEL = (8, 4, "24 CELLS OF CHARACTER 0:")


def address():
    assert addr(*TITLE_AT) == 0x1842 and len(TITLE) <= 30
    text = LONG
    assert len(text) == 64, len(text)
    return head("address", "an address of fourteen bits, and the VDP adding one") + """; A text at an address of two bytes; 64 bytes after one address, over two rows
; of the name table; eight bytes from $3FFC; and a row of character 0.
""" + TEXT_PAGE + f"""        VRAM_WRITE ${addr(*TITLE_AT):04X}        ; two bytes: ${addr(*TITLE_AT) & 0xFF:02X}, then ${addr(*TITLE_AT) >> 8 | 0x40:02X}
        ld hl, title
        call send
        VRAM_WRITE ${addr(*LONG_AT):04X}        ; one address for all 64 bytes
        ld hl, long
        call send
        VRAM_WRITE ${addr(*CHAR0_LABEL[:2]):04X}
        ld hl, label
        call send
        VRAM_WRITE ${addr(*CHAR0_AT):04X}        ; a row of character 0
        ld b, {CHAR0_N}
        xor a
c0:     out (VDP_DATA), a       ; 12
        nop                     ;  5
        nop                     ;  5
        djnz c0                 ; 14: 36 a byte
wr:     VRAM_WRITE ${WRAP_FROM:04X}        ; eight bytes from the top of the VRAM
        ld b, {WRAP_N}
        ld a, $FF               ; every pixel ink
w8:     out (VDP_DATA), a
        nop
        nop
        djnz w8
w9:
""" + SHOW_PAGE + """
; send: the text at HL, ending in 0, to the VRAM from its current address
send:   ld a, (hl)              ;  8
        or a                    ;  5
        ret z                   ;  6
        out (VDP_DATA), a       ; 12
        inc hl                  ;  7
        jr send                 ; 13: 51 a byte
title:""" + db(TITLE) + "long:" + db(text) + "label:" + db(CHAR0_LABEL[2]) + \
        library() + CART_END


# -------------------------------------------------------------- readback.asm
WORD = "ABCDEFGHIJ"
RB_COL = 2
RB_ROWS = {"orig": 2, "copy": 5, "naive": 8, "right": 11}      # the texts
RB_LABELS = {"orig": "WRITTEN:", "copy": "READ INTO THE RAM, WRITTEN:",
             "naive": "ONE ADDRESS: IN, OR $20, OUT:", "right": "AN ADDRESS FOR EVERY IN, OUT:"}
INS = "VARS + $20"          # the bytes the naive loop's INs gave


def setaddr(a, write):
    hi = (a >> 8) | (0x40 if write else 0)
    return (f"        ld a, ${a & 0xFF:02X}\n        out (VDP_CTRL), a\n"
            f"        ld a, ${hi:02X}               ; {'write' if write else 'read: bit 6 is 0'}\n"
            f"        out (VDP_CTRL), a\n")


def readback():
    n = len(WORD)
    o, c, v, r = (addr(RB_ROWS[k], RB_COL) for k in ("orig", "copy", "naive", "right"))
    labels = "".join(f"        ld b, {RB_ROWS[k] - 1}\n        ld c, {RB_COL}\n        ld hl, l_{k}\n"
                     "        call puts\n" for k in RB_ROWS)
    return head("readback", "reading the VRAM, and the byte read ahead") + f"""; A word; a copy made through the RAM; then two loops that turn letters into
; small letters where they are: one sets one address, the other one for every
; byte.
buf     EQU VARS + $10          ; {n} bytes
ins     EQU {INS}           ; the {n} bytes the first loop's INs gave
""" + TEXT_PAGE + labels + f"""        VRAM_WRITE ${o:04X}        ; the word
        ld hl, word
        call send
""" + f"""cp1:    ; the copy: read {n} bytes into the RAM, write them {3} rows down
""" + setaddr(o, False) + f"""        ld hl, buf
        ld b, {n}
cp2:    nop                     ;  5
        nop                     ;  5
        in a, (VDP_DATA)        ; 12
        ld (hl), a              ;  8
        inc hl                  ;  7
        djnz cp2                ; 14: 51 a byte
        ld (hl), 0              ; the end of the text: the RAM is not cleared
""" + setaddr(c, True) + f"""        ld hl, buf
        call send
        VRAM_WRITE ${v:04X}        ; the word again, twice more
        ld hl, word
        call send
        VRAM_WRITE ${r:04X}
        ld hl, word
        call send
nv:     ; one address, then IN, OR $20, OUT, {n} times
""" + setaddr(v, False) + f"""        ld hl, ins
        ld b, {n}
nv1:    nop                     ;  5
        in a, (VDP_DATA)        ; 12: the byte...
        ld (hl), a              ;  8: (kept, for meas19.py)
        inc hl                  ;  7
        or $20                  ;  8: ...as a small letter...
        out (VDP_DATA), a       ; 12: ...written back
        djnz nv1                ; 14
rt:     ; an address for every IN and every OUT
        ld hl, ${v + (r - v):04X}
        ld b, {n}
rt1:    ld a, l
        out (VDP_CTRL), a
        ld a, h                 ; read
        out (VDP_CTRL), a
        nop
        nop
        nop
        nop
        in a, (VDP_DATA)        ; the byte...
        or $20                  ; ...as a small letter...
        ld c, a
        ld a, l
        out (VDP_CTRL), a
        ld a, h
        or $40                  ; write
        out (VDP_CTRL), a
        ld a, c
        out (VDP_DATA), a       ; ...written back where it was
        inc hl
        djnz rt1
rt2:
""" + SHOW_PAGE + """
; send: the text at HL, ending in 0, to the VRAM from its current address
send:   ld a, (hl)              ;  8
        or a                    ;  5
        ret z                   ;  6
        out (VDP_DATA), a       ; 12
        inc hl                  ;  7
        jr send                 ; 13: 51 a byte
word:""" + db(WORD) + "".join(f"l_{k}:" + db(RB_LABELS[k]) for k in RB_ROWS) + \
        library() + CART_END


# ---------------------------------------------------------------- status.asm
BAND = 8                    # lines of black after the flag is seen
BAND_TURNS = (BAND * 228) // 14


def status():
    return head("status", "the frame flag, read with the interrupts off") + f"""; The VDP's interrupt off (R#1 bit 5 = 0) and the processor's too: the status
; read in a loop. When bit 7, the frame flag, comes, the border goes black for
; {BAND} lines. The border is light green, to tell it from the paper.
seen1   EQU VARS + $10          ; the status that had the flag
seen2   EQU VARS + $11          ; the status read just after it
""" + TEXT_PAGE + f"""        VDP_REG 7, LIGHT_GREEN  ; the border
        VDP_REG 1, $C0          ; display on; bit 5, the frame interrupt, off
        in a, (VDP_CTRL)        ; a flag left over from before: gone
poll:   in a, (VDP_CTRL)        ; 12
        and a                   ;  5: S is bit 7
        jp p, poll              ; 11: 28 a turn, until the flag comes
seen:   ld (seen1), a           ; 14
        VDP_REG 7, BLACK        ; 40: the border black from here...
        in a, (VDP_CTRL)
        ld (seen2), a
        ld b, {BAND_TURNS}
band:   djnz band
        VDP_REG 7, LIGHT_GREEN  ; ...to here
        jp poll
""" + library() + CART_END


# ------------------------------------------------------------------ bios.asm
BIOS_AT = (5, 2)            # WRTVRM's letter, and SETWRT's after it
FILL_AT = (7, 2)            # FILVRM's row of dashes
FILL_N = 28


def bios():
    a = addr(*BIOS_AT)
    return head("bios", "the BIOS's routines for the VRAM") + f"""; WRTVRM, SETWRT, RDVRM and FILVRM, each called with the interrupts off; the
; debugger times each call and reads the interrupts after it.
got     EQU VARS + $10          ; what RDVRM gave
""" + TEXT_PAGE + f"""        ld hl, ${a:04X}
        ld a, 'W'
c1:     call WRTVRM             ; A to the VRAM at HL
a1:     di
        ld hl, ${a + 1:04X}
c2:     call SETWRT             ; the address, to write
a2:     di
        ld a, 'S'
        out (VDP_DATA), a
        nop
        nop
        nop
        ld hl, ${a:04X}
c3:     call RDVRM              ; A = the byte at HL
a3:     di
        ld (got), a
        ld hl, ${addr(*FILL_AT):04X}
        ld bc, {FILL_N}
        ld a, '-'
c4:     call FILVRM             ; BC bytes of A from HL
a4:     di
""" + SHOW_PAGE + library() + CART_END


# ------------------------------------------------------- split.asm, fixed.asm
TEXTS = [(4, 4, "FIRST THIRD"), (12, 4, "SECOND THIRD"), (20, 4, "LAST THIRD")]


ISR_PLAIN = """
; isr: every frame
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
COUNT_AT = (23, 0)          # where share.asm's and whole.asm's routine prints
ISR_PRINTS = f"""
; isr: every frame, and the count of frames, two hexadecimal digits, printed
isr:    push af
        push bc
        push hl
        in a, (VDP_CTRL)        ; the status: the VDP takes its signal down
        ld hl, (ticks)
        inc hl
        ld (ticks), hl
        ld a, l
        ld b, {COUNT_AT[0]}
        ld c, {COUNT_AT[1]}
        call puthex             ; its own address, and two bytes
        pop hl
        pop bc
        pop af
        ei
        ret
"""
PRINT = """
; print: HL = a text ending in 0, B = row, C = column
print:  push hl
        call at                 ; the address: two OUTs
        pop hl
.next:  ld a, (hl)              ;  8
        or a                    ;  5
        ret z                   ;  6
        out (VDP_DATA), a       ; 12
        inc hl                  ;  7
        jr .next                ; 13: 51 a byte
"""
PRINT_WHOLE = """
; print: HL = a text ending in 0, B = row, C = column; the interrupts off for
;        the address and every byte, and then as they were
print:  ld a, i                 ; P/V: the interrupts on or off (chapter 17)
        jp pe, .on
        ld a, i                 ; off, or one came just now: ask again
.on:    push af                 ; kept for the end
        di
        push hl
        call at                 ; with them off, at leaves them off
        pop hl
.next:  ld a, (hl)              ;  8
        or a                    ;  5
        jr z, .end              ;  8
        out (VDP_DATA), a       ; 12
        inc hl                  ;  7
        jr .next                ; 13: 53 a byte
.end:   pop af
        ret po                  ; they were off: leave them off
        ei
        ret
"""
WHAT = {"split": "three texts printed over and over, the interrupts on: the library's at",
        "fixed": "the same, with the interrupts off round the address",
        "share": "the same, and the interrupt routine prints too",
        "whole": "the same, with the interrupts off round each whole text"}
NOTE = {"split": "at is the library one: two OUTs, the interrupts on.",
        "fixed": "This at sets the address with the interrupts off.",
        "share": "This at sets the address with the interrupts off, and the routine\n"
                 "; prints the count of frames on the last row.",
        "whole": "The interrupts are off for the address and every byte of a text,\n"
                 "; and the routine prints the count of frames on the last row."}


def printer(name, on):
    what = WHAT[name]
    calls = ""
    for k, (row, col, _) in enumerate(TEXTS, 1):
        calls += f"""        ld a, {k}
        ld (which), a           ; which text is being printed
        ld b, {row}
        ld c, {col}
        ld hl, text{k}
        call print
"""
    return head(name, what) + IM2 + f"""; Three texts, one in each third of the screen, printed again and again while
; the frame's interrupt comes in mode 2; its routine reads the status and
; counts the frames.
; {NOTE[name]}
ticks   EQU VARS + $10          ; frames, counted by the interrupt routine
turns   EQU VARS + $12          ; turns of the main loop
which   EQU VARS + $14          ; the text being printed, 1 to 3
""" + TEXT_PAGE + """        ld hl, 0
        ld (ticks), hl
        ld (turns), hl
""" + im2("isr") + """        VDP_REG 1, $E0          ; display on, and the frame's interrupt
        in a, (VDP_CTRL)
        ei
main:
""" + calls + """        ld hl, (turns)
        inc hl
        ld (turns), hl
        jp main
""" + (PRINT_WHOLE if name == "whole" else PRINT) + \
        (ISR_PRINTS if name in ("share", "whole") else ISR_PLAIN) + \
        """""" + "".join(f"text{k}:" + db(t) for k, (_, _, t) in enumerate(TEXTS, 1)) + \
        library(interrupts=on) + CART_END


PROGRAMS = {"ports": ports, "regs": regs, "address": address, "readback": readback,
            "status": status, "split": lambda: printer("split", False),
            "fixed": lambda: printer("fixed", True), "share": lambda: printer("share", True),
            "whole": lambda: printer("whole", True), "bios": bios}


def main():
    for name, make in PROGRAMS.items():
        with open(os.path.join(HERE, f"{name}.asm"), "w") as f:
            f.write(make())
    print(" ".join(f"{n}.asm" for n in PROGRAMS))


if __name__ == "__main__":
    main()
