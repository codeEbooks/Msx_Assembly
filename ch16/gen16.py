#!/usr/bin/env python3
"""gen16.py - the programs of chapter 16.

    python3 gen16.py && ./build.sh

    print.asm      CHGMOD with the colours of FORCLR, BAKCLR and BDRCLR, then a
                   page printed by CHPUT, control codes and all (figure 16.1).
    calls.asm      five BIOS calls, CHGMOD, CHPUT, WRTVDP, LDIRVM and GTSTCK,
                   each with every register marked before it, and the same
                   jobs done through the ports: what each costs, and what it
                   changes.
    copies.asm     a VDP register written through the port, then DISSCR and
                   ENASCR, which work from the BIOS's copy of it; and the same
                   through WRTVDP.
    hook.asm       a routine of the program's own in H.CHPU: the border changes
                   colour before every character CHPUT prints (figure 16.2).
    stick.asm      the cursor keys read by GTSTCK and straight from the
                   keyboard, both timed.
    chget.asm      CHGET called as INIT leaves the machine, interrupts off.
    ints.asm       WHERE IT BREAKS: a loop timed before and after one call of
                   CHPUT, in a program that keeps the interrupts off.

Every program includes bios.inc, the names of the BIOS's entry points and
system variables, from this chapter on. Cartridges end with asmparts.CART_END
and build.sh assembles with --syntax=bFw (chapter 15).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
from asmparts import HEAD, CART_END, TEXT_PAGE, library  # noqa: E402

RESULTS = "RESULTS EQU RAM_START          ; what the program found: the debugger reads it here\n"
BIOS = '        INCLUDE "bios.inc"\n'


def head(name, what):
    return HEAD.format(name=name, chapter=16, what=what) + BIOS


def cart(name, what, body, after="", results=True, comment=""):
    """a cartridge that runs `body` with the interrupts off and stops"""
    return head(name, what) + (RESULTS if results else "") + comment + f"""init:   di
        ld sp, SYS_AREA
{body}stop:   jr stop
{after}""" + CART_END


COLOURS = """        ld a, BLACK
        ld (FORCLR), a          ; ink
        ld a, WHITE
        ld (BAKCLR), a          ; paper
        ld a, LIGHT_GREEN
        ld (BDRCLR), a          ; border
"""

# ---------------------------------------------------------------- print.asm
PRINT_TEXT = [
    '12, 27, "Y", 32+2, 32+3, "Printed by CHPUT,", 13, 10',
    '"a character at a time.", 27, "Y", 32+6, 32+3, "TAB:", 9, "next stop"',
    '27, "Y", 32+8, 32+3, "BS: abc", 8, 8, "X"',
    '27, "Y", 32+10, 32+0, "A line longer than the "',
    '"twenty-nine columns wraps.", 7, 0',
]


def print_():
    text = "".join(f"        db {t}\n" for t in PRINT_TEXT).replace("        db ", "text:   db ", 1)
    return cart("print", "a page printed by the BIOS", COLOURS + """        ld a, 1                 ; screen 1: 32 x 24 characters
c0:     call CHGMOD
c1:     ld hl, text
p0:     ld a, (hl)
        or a
        jr z, p3                ; the 0 at the end
p1:     call CHPUT              ; one character, or one control code
p2:     inc hl
        jr p0
p3:     nop
""", after=text, comment="""; CHGMOD with the colours of FORCLR, BAKCLR and BDRCLR, then a page printed
; by CHPUT: 12 clears it, ESC Y and two bytes move the cursor, 13 and 10 end
; a line, 9 is a tab, 8 a step back, and 7 asks for a beep.
""")


# ---------------------------------------------------------------- calls.asm
MARKS = {"bc": 0xB0B0, "de": 0xD0D0, "hl": 0xE0E0, "ix": 0x1E1E, "iy": 0x1F1F,
         "bc'": 0xB1B1, "de'": 0xD1D1, "hl'": 0xE1E1, "a'": 0xA1}
CALLS = [  # (number, name, the inputs, what it does)
    (1, "CHGMOD", "        ld a, 1                 ; screen 1\n", "screen 1, cleared"),
    (2, "CHPUT", "        ld a, 'A'\n", "one letter"),
    (3, "WRTVDP", "        ld b, LIGHT_GREEN\n        ld c, 7                 ; the border\n",
     "the border's register"),
    (4, "LDIRVM", "        ld hl, cells\n        ld de, $1800            ; the name table\n"
                  "        ld bc, 768\n", "768 bytes to the name table"),
    (5, "GTSTCK", "        xor a                   ; the cursor keys\n", "the cursor keys"),
]


def calls():
    body = "".join(f"""        call marks
{inputs}b{n}:     call {name}
a{n}:     di                      ; the interrupts off again, whatever the call did
""" for n, name, inputs, _ in CALLS)
    ports = """q3:     VDP_REG 7, LIGHT_GREEN  ; WRTVDP's job, through the port
q3e:    VDP_REG 1, $A0          ; display off: OTIR is too fast for it on (chapter 20)
q4:     VRAM_WRITE $1800        ; LDIRVM's, with OTIR (chapter 13)
        ld hl, cells
        ld c, VDP_DATA
        ld b, 0
        otir
        otir
        otir                    ; 3 x 256 bytes
q5:     call stick              ; GTSTCK's, from the keyboard
q2:     ld a, 'A'
        ld b, 0
        ld c, 0
        call putc               ; CHPUT's, with chapter 14's putc
q6:     nop
"""
    after = f"""
; marks: every register a call does not take, set to a value of its own, so
; that what the call changes shows
marks:  exx
        ld bc, ${MARKS["bc'"]:04X}
        ld de, ${MARKS["de'"]:04X}
        ld hl, ${MARKS["hl'"]:04X}
        exx
        ex af, af'
        ld a, ${MARKS["a'"]:02X}
        ex af, af'
        ld ix, ${MARKS["ix"]:04X}
        ld iy, ${MARKS["iy"]:04X}
        ld bc, ${MARKS["bc"]:04X}
        ld de, ${MARKS["de"]:04X}
        ld hl, ${MARKS["hl"]:04X}
        ret
""" + STICK + STICKS + """
cells:  DUP 768, n              ; 768 characters for the name table
        db 32 + n % 96
        EDUP
""" + library()
    return head("calls", "five BIOS calls, and the ports") + RESULTS + """; Five BIOS calls, each with every register it does not take set to a mark
; first; then the same jobs through the ports. The debugger stops before and
; after each call and reads the registers and the system variables.
""" + TEXT_PAGE + "pg:     nop                     ; the page set up through the ports\n" + \
        COLOURS + body + ports + "stop:   jr stop\n" + after + CART_END


# stick: the cursor keys straight from the keyboard, as GTSTCK reports them
STICK = """
; stick: A = the direction of the cursor keys, 0 to 8, as GTSTCK gives it:
;        row 8 of the keyboard, read through the PPI (chapter 3), and its four
;        top bits, which are 0 for a key held down, looked up in a table.
;        Uses A, H, L.
stick:  in a, (PPI_C)
        and $F0                 ; keep the PPI's other outputs
        or 8                    ; row 8: the cursor keys in bits 4 to 7
        out (PPI_C), a
        in a, (PPI_B)
        rrca
        rrca
        rrca
        rrca
        and $0F                 ; right, down, up, left: 0 when held
        ld l, a
        ld h, high sticks
        ld a, (hl)
        ret
"""


def stick_table():
    """the 16 bytes of `sticks`: the direction GTSTCK reports for each state
    of the four keys, bit 0 left, 1 up, 2 down, 3 right, 0 when held"""
    out = []
    for v in range(16):
        left, up, down, right = (not (v >> b) & 1 for b in range(4))
        dx = (1 if right else 0) - (1 if left else 0)
        dy = (1 if down else 0) - (1 if up else 0)
        out.append(DIRECTION[(dx, dy)])
    return out


DIRECTION = {(0, 0): 0, (0, -1): 1, (1, -1): 2, (1, 0): 3, (1, 1): 4, (0, 1): 5, (-1, 1): 6,
             (-1, 0): 7, (-1, -1): 8}
STICKS = """
        ALIGN 256               ; stick puts the four bits in L
sticks: db """ + ", ".join(str(d) for d in stick_table()) + "\n"


# --------------------------------------------------------------- copies.asm
def copies():
    return cart("copies", "the copies the BIOS keeps", """        ld a, 1
        call CHGMOD
r0:     di
        ld a, (RG0SAV + 1)      ; what CHGMOD put in register 1
        or 2                    ; and bit 1: sprites of 16 x 16
        out (VDP_CTRL), a
        ld a, $81
        out (VDP_CTRL), a       ; through the port: the copy is not told
r1:     call DISSCR             ; the display off, from the copy
r2:     call ENASCR             ; and on again
r3:     di
        ld a, (RG0SAV + 1)
        or 2                    ; the same bit, through the BIOS
        ld b, a
        ld c, 1
        call WRTVDP
r4:     call DISSCR
r5:     call ENASCR
r6:     di
""", results=False, comment="""; The BIOS keeps a copy of every VDP register it writes, and works from the
; copy. Bit 1 of register 1 set through the port, then DISSCR and ENASCR; and
; the same bit set through WRTVDP, then the same two calls.
""")


# ----------------------------------------------------------------- hook.asm
HOOK_TEXT = '27, "Y", 32+11, 32+0, "H.CHPU SEES EVERY CHARACTER.", 0'
WAIT_TOP = 700              # turns of wait: the first band starts above the picture


def hook():
    return head("hook", "a hook on CHPUT") + """band    EQU RAM_START       ; the colour of the band the border is in
; A routine of the program's own in H.CHPU, the hook CHPUT calls before every
; character: it changes the colour of the border, so that every character
; CHPUT prints is one band of the border. The page is printed again every
; frame, from the same point of the frame.
init:   di
        ld sp, SYS_AREA
""" + COLOURS + """        ld a, 1
        call CHGMOD
        ld hl, hook             ; H.CHPU: JP hook
        ld (H_CHPU + 1), hl
        ld a, $C3               ; JP
        ld (H_CHPU), a
frame:  ld a, BLACK
        ld (band), a            ; every frame the same bands
        ei
        halt                    ; the frame interrupt, and the BIOS's routine
h1:     call wait               ; down to the top of the picture
        ld hl, text
h2:     ld a, (hl)
        or a
        jr z, frame             ; the 0 at the end: the page again
        call CHPUT              ; and CHPUT calls H.CHPU
        inc hl
        jr h2

; hook: called by CHPUT through H.CHPU, before every character, with the
;       character in A. The border in the other colour. Keeps every register.
hook:   push af
        ld a, (band)
        xor BLACK ^ LIGHT_GREEN ; the other colour
        ld (band), a
        di                      ; the two bytes together (chapter 19)
        out (VDP_CTRL), a
        ld a, $87               ; register 7: the border
o1:     out (VDP_CTRL), a
        pop af
        ret

; wait: """ + f"""{WAIT_TOP:,} turns of chapter 14's loop. Uses A, DE.
wait:   ld de, {WAIT_TOP}
wt:     dec de
        ld a, d
        or e
        jr nz, wt
        ret

text:   db {HOOK_TEXT}
""" + CART_END


# ---------------------------------------------------------------- stick.asm
def stick():
    return cart("stick", "the cursor keys, two ways", """s1:     xor a
        call GTSTCK             ; the BIOS's way
s2:     ld (RESULTS), a
s3:     call stick              ; straight from the keyboard
s4:     ld (RESULTS+1), a
""", after=STICK + STICKS,
                comment="""; The cursor keys read twice, by GTSTCK and by stick, which asks the keyboard
; itself; the debugger holds keys down from INIT on and compares.
""")


# ---------------------------------------------------------------- chget.asm
CHGET_ASM = cart("chget", "waiting for a key", """c1:     call CHGET              ; wait for a key
c2:     ld (RESULTS), a         ; its code
        VDP_REG 7, LIGHT_GREEN  ; the border light green: a key came
""", comment="""; CHGET waits for a key in the buffer that the BIOS's interrupt routine
; fills. The program calls it as INIT leaves the machine: interrupts off.
""")

# ----------------------------------------------------------------- ints.asm
WAIT_TURNS = 4757           # 30 x 4,757 + 35 = 142,745 T-states: two frames


def ints():
    return cart("ints", "WHERE IT BREAKS: the interrupts come back", f"""        im 1
w1:     call wait               ; two frames, priced
w2:     ld a, 'A'
        call CHPUT              ; one character, through the BIOS
w3:     call wait               ; the same two frames again
w4:     nop
""", after=f"""
; wait: {WAIT_TURNS:,} turns of chapter 14's loop. Uses A, DE.
wait:   ld de, {WAIT_TURNS}
wt:     dec de
        ld a, d
        or e
        jr nz, wt
        ret
""", comment="""; WHERE IT BREAKS. The program keeps the interrupts off, as every program in
; this book has since chapter 5, and times the same loop before and after a
; single call of CHPUT.
""")


def main():
    files = {"print.asm": print_(), "calls.asm": calls(), "copies.asm": copies(),
             "hook.asm": hook(), "stick.asm": stick(), "chget.asm": CHGET_ASM, "ints.asm": ints()}
    for name, text in files.items():
        with open(os.path.join(HERE, name), "w") as f:
            f.write("\n".join(l.rstrip() for l in text.split("\n")))    # no spaces at line ends
    print(len(files), "sources written")


if __name__ == "__main__":
    main()
