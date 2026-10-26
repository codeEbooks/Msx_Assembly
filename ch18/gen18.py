#!/usr/bin/env python3
"""gen18.py - the programs of chapter 18: the frame, mapped.

    python3 gen18.py && ./build.sh

    lines.asm      a loop of exactly one frame, 313 lines on a 50 Hz machine and
                   262 on a 60 Hz one, as bit 7 of $002B says, that gives the
                   border a colour of its own on every line, four colours in
                   turn (figure 18.1, both machines).
    ruler.asm      a loop of exactly one 50 Hz frame that changes the border
                   six times a line, every 38 T-states, black and white in
                   turn, on every line of the frame (figure 18.2).
    paper.asm      seven cells of a row of characters given a new name, one a
                   line, at the end of each line: the VDP reads the name
                   table again for every line it draws (figure 18.3).
    f71363.asm     a loop of 71,363, 71,364 or 71,365 T-states with interrupts
    f71364.asm     off and a white stripe on the border once a turn; the
    f71365.asm     frame's length from the photographs alone (figure 18.4)
    f59735.asm     the same on the 60 Hz machine, about a frame of 59,736
    f59736.asm
    f59737.asm
    box.asm        a loop of exactly one frame on either machine that paints a
                   white box in the border under the paper, at rows and columns
                   chosen from the map (figure 18.5).
    wrong.asm      WHERE IT BREAKS: f71364.asm with its wait priced by a slip,
                   every JR NZ at 13 T-states, the last one too (figure 18.6).

Every price is the MSX's: Zilog's plus one for every M1 (chapter 14). Every
program waits for one frame's interrupt in mode 2 (chapter 17), to start in
step with the picture, and then keeps the interrupts off and counts T-states.
Cartridges end with asmparts.CART_END and build.sh assembles with
--syntax=bFw (chapter 15).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
from asmparts import HEAD, CART_END, TEXT_PAGE, library, IM2, im2  # noqa: E402

BIOS = '        INCLUDE "bios.inc"\n'
LINE_T = 228
FRAME_T = {"MSXBOOK_EU16": 71364, "MSXBOOK_JP16": 59736}
IRQ_LINE = {"MSXBOOK_EU16": 261, "MSXBOOK_JP16": 234}      # chapter 17, measured
# after HALT the program goes on this many T-states into the interrupt's
# line: the answer, 0 to 4 T-states after the signal at 33 2/3, then 19 to
# answer, 11 for the JP and 51 for isr (chapter 17); meas18.py reads the real
# time, and every plan below leaves room for the HALT's step
BACK_W = 118
# MSX prices, chapter 14
P = {"nop": 5, "ld r,n": 8, "ld rr,nn": 11, "ld a,(hl)": 8, "out (n),a": 12,
     "out (c),r": 14, "xor r": 5, "inc r": 5, "res b,r": 10, "dec r": 5, "jr": 13,
     "jr_not": 8, "dec rr": 7, "ld r,r": 5, "or r": 5, "jp": 11, "jp (hl)": 5, "djnz": 14,
     "ld rr,(nn)": 22, "di": 5}
COLOURS = ["BLACK", "DARK_BLUE", "WHITE", "LIGHT_GREEN"]    # the four greys a print keeps

SYNC_ISR = """
; isr: the frame's interrupt, taken once, to start in step with the picture
isr:    push af
        in a, (VDP_CTRL)        ; the status: the VDP takes its signal down
        pop af
        ei
        ret
"""


def head(name, what):
    return HEAD.format(name=name, chapter=18, what=what) + BIOS + IM2


def wait_code(total, label):
    """code that takes exactly TOTAL T-states: chapter 14's sixteen-bit count
    (11 to load, 30 a turn, 5 less for the last) and NOPs of 5 and LD C,0 of 8;
    or, for a short wait, NOPs and LD C,0 alone. Uses A, C, DE."""
    turn = P["dec rr"] + P["ld r,r"] + P["or r"] + P["jr"]
    best = None
    for eights in range(0, 6):
        for fives in range(0, 6):
            rest = total - P["ld rr,nn"] + (P["jr"] - P["jr_not"]) - 8 * eights - 5 * fives
            if rest > 0 and rest % turn == 0:
                cand = (eights + fives, rest // turn, eights, fives)
                best = min(best, cand) if best else cand
    if best:
        _, n, eights, fives = best
        return (f"{label + 's:':<8}ld de, {n}\n{label + ':':<8}dec de\n        ld a, d\n"
                f"        or e\n        jr nz, {label}\n" + "        ld c, 0\n" * eights +
                "        nop\n" * fives), n, eights, fives
    for eights in range(0, 12):
        rest = total - 8 * eights
        if rest >= 0 and rest % 5 == 0:
            return "        ld c, 0\n" * eights + "        nop\n" * (rest // 5), 0, eights, rest // 5
    raise ValueError(total)


def wrong_wait(total, label):
    """the same wait priced by a slip: every JR NZ at 13, the last one too"""
    turn = P["dec rr"] + P["ld r,r"] + P["or r"] + P["jr"]
    for eights in range(0, 6):
        for fives in range(0, 6):
            rest = total - P["ld rr,nn"] - 8 * eights - 5 * fives
            if rest > 0 and rest % turn == 0:
                n = rest // turn
                return (f"{label + 's:':<8}ld de, {n}\n{label + ':':<8}dec de\n        ld a, d\n"
                        f"        or e\n        jr nz, {label:<17}; 30 a turn, every turn\n"
                        + "        ld c, 0\n" * eights + "        nop\n" * fives), n, eights, fives
    raise ValueError(total)


def sync(label, total):
    """after setup: wait for one frame's interrupt, then the interrupts off
    and a wait of TOTAL T-states (from the instruction after HALT, DI
    included) before the loop"""
    code, *_ = wait_code(total - P["di"], label)
    return """        in a, (VDP_CTRL)        ; no signal left over from before
        ei
        halt                    ; one frame's interrupt: in step with the picture
        di                      ; and from here on, nothing but this program
go:
""" + code


def first_line(machine):
    return IRQ_LINE[machine] + 1


# ----------------------------------------------------------------- lines.asm
LINE_WAIT = ("        ld e, 7                 ;  8\n{l}:     dec e\n        jr nz, {l}               ; 7 x 18 - 5\n"
             "        ld d, 0                 ;  8\n        ld d, 0                 ;  8: 145\n",
             8 + 7 * 18 - 5 + 16)                          # 145: D and E are free here
LAST_WAIT = ("        ld e, 6\n{l}:     dec e\n        jr nz, {l}\n        ld d, 0\n        ld d, 0\n"
             "        nop\n", 8 + 6 * 18 - 5 + 16 + 5)      # 132
LINES_W = 12                # each change written at T-state 12 of its line
LINES_OUT = 8 + 12 + 8      # LD A,(HL), OUT, LD A,$87: the second OUT starts
LINES_SETUP = 22 + 8        # LD BC,(nn) and LD L,n, once a frame


def lines_sync():
    """from the instruction after HALT to the frame's start: the first
    change written at T-state LINES_W of the line after the interrupt's"""
    return (LINE_T - BACK_W) + LINES_W - 8 - LINES_OUT - LINES_SETUP


def lines():
    assert 55 + LINE_WAIT[1] + 7 + 5 + 5 + 11 == LINE_T
    assert LINES_SETUP + 55 + LAST_WAIT[1] + P["jp"] == LINE_T
    return head("lines", "every line of the frame in a colour of its own") + \
        """nlines  EQU VARS + 16           ; the lines of a frame, less one
; A loop of exactly one frame, as many lines as the machine draws, that changes
; the border's colour once a line, four colours in turn.
""" + TEXT_PAGE + """        ld a, ($002B)           ; bit 7 is 1 on a 50 Hz machine (chapter 4)
        rlca
        ld hl, 313 - 1
        jr c, hz50
        ld hl, 262 - 1
hz50:   ld (nlines), hl
""" + im2("isr") + """        VDP_REG 1, $E0          ; display on, and the frame's signal on
        ld h, high colours
""" + sync("w0", lines_sync()) + """frame:  ld bc, (nlines)         ; 22
        ld l, low colours       ;  8: the first colour
line:   ld a, (hl)              ;  8
        out (VDP_CTRL), a       ; 12
        ld a, $87               ;  8
o1:     out (VDP_CTRL), a       ; 12: the border in this line's colour
        inc l                   ;  5
        res 2, l                ; 10: 0, 1, 2, 3, and 0 again
""" + LINE_WAIT[0].format(l="w1") + """        dec bc                  ;  7
        ld a, b                 ;  5
        or c                    ;  5
        jp nz, line             ; 11: 228 a line
        ld a, (hl)              ; the frame's last line
        out (VDP_CTRL), a
        ld a, $87
o2:     out (VDP_CTRL), a
        inc l
        res 2, l
""" + LAST_WAIT[0].format(l="w2") + """        jp frame                ; 30 + 198 for this line: 228
""" + SYNC_ISR + """
        ALIGN 256
colours:
        db """ + ", ".join(COLOURS) + "\n" + library() + CART_END


# ----------------------------------------------------------------- ruler.asm
RULER_PER_LINE = 6
RULER_T = LINE_T // RULER_PER_LINE          # 38: OUT, OUT, XOR D, NOP
RULER_W = 10                # the first change of each line written at T-state 10
RULER_LINES = 313
RULER_SETUP = 8 + 8 + 8 + 8 + 11       # the registers, after the wait


def ruler_sync():
    """from the instruction after HALT: the first change of the line after
    the interrupt's written at T-state RULER_W (OUT (C),r writes 10 T-states
    after it starts; the value's OUT comes 14 before)"""
    return (LINE_T - BACK_W) + RULER_W - 10 - 14


def ruler():
    assert RULER_T * RULER_PER_LINE == LINE_T and RULER_T == 14 + 14 + 5 + 5
    n = RULER_LINES * RULER_PER_LINE
    return head("ruler", "the border six times a line") + \
        """; A loop of exactly one 50 Hz frame, 313 lines, that changes the border's
; colour six times a line, every 38 T-states, black and white in turn.
""" + TEXT_PAGE + im2("isr") + """        VDP_REG 1, $E0          ; display on, and the frame's signal on
""" + sync("w0", ruler_sync() - RULER_SETUP) + f"""        ld c, VDP_CTRL          ;  8
        ld e, $87               ;  8: register 7
        ld d, BLACK ^ WHITE     ;  8: XOR D, black to white and back
        ld a, BLACK             ;  8
        ld hl, frame            ; 11
frame:  DUP {n - 1}
        out (c), a              ; 14: the colour
        out (c), e              ; 14: into register 7
        xor d                   ;  5: the other colour
        nop                     ;  5: 38 a change, 6 a line
        EDUP
        out (c), a
        out (c), e
        xor d
        jp (hl)                 ;  5, where the last NOP was
""" + SYNC_ISR + library() + CART_END


# ----------------------------------------------------------------- paper.asm
PAPER_ROW = 10              # the row of characters
PAPER_CELLS = 7
PAPER_W = 12                # each name written at T-state 12 of the line after
BOX_FULL = 2                # asmparts: the filled box


PAPER_LOOP = 5 + 12 + 5 + 12 + 8 + 12 + 5 + 155 + 14        # 228


def paper_plan():
    """the T-states from the instruction after HALT to the first OUT that
    writes a name, and the wait that makes them up"""
    first = 69 + 8 * PAPER_ROW                  # the row's first line, 50 Hz
    lines_on = (313 - 261) + first              # from the interrupt's line
    # the first name is written at T-state PAPER_W of the row's first line:
    # its OUT starts 8 before; before it in the loop, 5 + 12 + 5 + 12 + 8
    start = lines_on * LINE_T + PAPER_W - 8 - (5 + 12 + 5 + 12 + 8) - BACK_W
    return start


def paper():
    assert PAPER_LOOP == LINE_T
    name0 = 0x1800 + 32 * PAPER_ROW
    restore = f"""        VRAM_WRITE ${name0:04X}        ; the seven cells blank again: the VDP
        ld a, ' '               ; is not drawing the paper now
        ld b, {PAPER_CELLS}
blank:  out (VDP_DATA), a
        djnz blank
"""
    restore_t = 8 + 12 + 8 + 12 + 8 + 8 + PAPER_CELLS * (12 + 14) - 5
    total = paper_plan() - P["di"] - restore_t - (8 + 11)       # LD B,n and LD DE,nn after
    code, *_ = wait_code(total, "w0")
    return head("paper", "a row of names changed one line at a time") + \
        f"""; Seven cells of character row {PAPER_ROW} get a new name, the filled box, one
; a line, at the start of each of the row's lines. Every frame the program
; puts them back to blank while the VDP draws no paper, and does it again.
""" + TEXT_PAGE + im2("isr") + f"""        VDP_REG 1, $E0          ; display on, and the frame's signal on
        in a, (VDP_CTRL)        ; no signal left over from before
frame:  ei
        halt                    ; the frame's interrupt
        di
""" + restore + code + f"""        ld b, {PAPER_CELLS}                 ; seven cells
        ld de, ${name0 | 0x4000:04X}            ; the first cell's address, for writing
cell:   ld a, e                 ;  5
        out (VDP_CTRL), a       ; 12
        ld a, d                 ;  5
        out (VDP_CTRL), a       ; 12: the cell's address
        ld a, {BOX_FULL}                 ;  8: the filled box
n1:     out (VDP_DATA), a       ; 12: its new name
        inc e                   ;  5: the next cell
        ld c, 8                 ;  8
w1:     dec c
        jr nz, w1               ; 8 x 18 - 5
        ld h, 0                 ;  8: 155 in all
        djnz cell               ; 14: 228 a cell
        jr frame
""" + SYNC_ISR + library() + CART_END


# --------------------------------------------------------- the frame's length
STRIPE_NOPS = 8
STRIPE_FIXED = 4 * 8 + 4 * 12 + 5 * STRIPE_NOPS + P["jp"]     # 131
STRIPE_LINE = {"MSXBOOK_EU16": 50, "MSXBOOK_JP16": 26}           # a line of the top border
STRIPE_W = 70               # the white written at about this T-state of it
DRIFT = {"MSXBOOK_EU16": [71363, 71364, 71365], "MSXBOOK_JP16": [59735, 59736, 59737]}


WRONG_W = 150               # wrong.asm's stripe, further right: it moves left


def stripe_sync(machine, w=STRIPE_W):
    lines_on = FRAME_T[machine] // LINE_T - IRQ_LINE[machine] + STRIPE_LINE[machine]
    return lines_on * LINE_T + w - 8 - 28 - BACK_W


def stripe(name, machine, turn_t, wrong=False):
    rest = turn_t - STRIPE_FIXED
    code, n, eights, fives = (wrong_wait if wrong else wait_code)(rest, "w1")
    what = ("WHERE IT BREAKS: a wait priced by a slip" if wrong else
            f"a loop of {turn_t:,} T-states and a stripe")
    hz = "50" if machine.endswith("EU16") else "60"
    comment = (f"""; WHERE IT BREAKS. f{turn_t}.asm with its wait worked out by a slip: every
; JR NZ priced at 13 T-states, the last one too, which does not jump.
""" if wrong else f"""; A loop of {turn_t:,} T-states, with the interrupts off, that draws a white
; stripe on the black border once a turn. On a {hz} Hz machine a frame is
; {FRAME_T[machine]:,} T-states; if the loop is longer or shorter the stripe moves.
""")
    return head(name, what) + comment + TEXT_PAGE + im2("isr") + """        VDP_REG 7, BLACK        ; the border black
        VDP_REG 1, $E0          ; display on, and the frame's signal on
""" + sync("w0", stripe_sync(machine, WRONG_W if wrong else STRIPE_W)) + """turn:   ld a, WHITE             ;  8
        out (VDP_CTRL), a       ; 12
        ld a, $87               ;  8
s1:     out (VDP_CTRL), a       ; 12: white from here
""" + "        nop\n" * STRIPE_NOPS + """        ld a, BLACK             ;  8
        out (VDP_CTRL), a       ; 12
        ld a, $87               ;  8
s2:     out (VDP_CTRL), a       ; 12: and black again
""" + code + """        jp turn                 ; 11
""" + SYNC_ISR + library() + CART_END


# ------------------------------------------------------------------- box.asm
BOX_LINES = 8
BOX_DOWN = 4                # the box's first line: four lines after the signal's
BOX_W = 87                  # white written at T-state 87: x = 100
BOX_GAP = 6                 # NOPs between the two OUTs: black at T-state 157, x = 205
BOX_REST = ("        ld e, 4\n{l}:     dec e\n        jr nz, {l}               ; 8 + 4 x 18 - 5\n"
            "        ld d, 0\n        ld d, 0\n        ld d, 0\n        nop                     ; 104\n",
            8 + 4 * 18 - 5 + 24 + 5)
BOX_TAIL = 14 + 5 + 11      # LD A,($002B), RLA, JP NC: which wait
BOX_BACK = 119              # where box.asm goes on after its HALT: the step its HALT
                            # ends at, read from the debugger (meas18.py checks it)


def box_line_t():
    return 40 + 5 * BOX_GAP + 40 + BOX_REST[1] + P["djnz"]


def box():
    assert box_line_t() == LINE_T
    lines_t = 8 + BOX_LINES * LINE_T - (P["djnz"] - 9)          # LD B,n; the last DJNZ: 9
    waits = {m: FRAME_T[m] - lines_t - BOX_TAIL - P["jp"] for m in FRAME_T}
    w50, *_ = wait_code(waits["MSXBOOK_EU16"], "w50")
    w60, *_ = wait_code(waits["MSXBOOK_JP16"], "w60")
    # from the instruction after HALT to the frame: the white's OUT starts
    # 8 + 28 T-states into the frame, and writes 8 after that
    first = BOX_DOWN * LINE_T + BOX_W - 8 - 28 - 8 - BOX_BACK
    return head("box", "a box aimed at, in the border") + \
        f"""; A loop of exactly one frame, as many lines as the machine draws, that paints
; a white box on the black border under the paper: {BOX_LINES} lines from the {BOX_DOWN}th after the
; one with the frame's signal, white from T-state {BOX_W} of each to T-state {BOX_W + 70}.
""" + TEXT_PAGE + im2("isr") + """        VDP_REG 7, BLACK        ; the border black
        VDP_REG 1, $E0          ; display on, and the frame's signal on
""" + sync("w0", first) + f"""frame:  ld b, {BOX_LINES}                 ;  8
bl:     ld a, WHITE             ;  8
        out (VDP_CTRL), a       ; 12
        ld a, $87               ;  8
bw:     out (VDP_CTRL), a       ; 12: white from x 100
""" + "        nop\n" * BOX_GAP + """        ld a, BLACK             ;  8
        out (VDP_CTRL), a       ; 12
        ld a, $87               ;  8
bk:     out (VDP_CTRL), a       ; 12: black from x 205
""" + BOX_REST[0].format(l="w1") + """        djnz bl                 ; 14: 228 a line
        ld a, ($002B)           ; 14: bit 7 is 1 on a 50 Hz machine (chapter 4)
        rla                     ;  5
        jp nc, w60s             ; 11: 60 Hz, the shorter wait
""" + w50 + """        jp frame
""" + w60 + """        jp frame
""" + SYNC_ISR + library() + CART_END


def main():
    files = {"lines": lines(), "ruler": ruler(), "paper": paper(), "box": box()}
    for machine, ns in DRIFT.items():
        for n in ns:
            files[f"f{n}"] = stripe(f"f{n}", machine, n)
    files["wrong"] = stripe("wrong", "MSXBOOK_EU16", 71364, wrong=True)
    for name, text in files.items():
        with open(os.path.join(HERE, f"{name}.asm"), "w") as f:
            f.write("\n".join(l.rstrip() for l in text.split("\n")))
    print(len(files), "sources written")


if __name__ == "__main__":
    main()
