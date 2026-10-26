#!/usr/bin/env python3
"""gen20.py - the programs of chapter 20: how fast the VDP listens.

    python3 gen20.py && ./build.sh

    beat.asm       228 pairs of bytes, the second 20 T-states after the first,
                   one pair at every T-state of a line, in the paper's lines;
                   each pair in two cells of the name table, in the order of
                   their T-states (figure 20.1).
    beat12.asm ... beat26.asm
                   the same with 12, 17, 24, 25 and 26 T-states between the
                   two bytes (figure 20.2).
    probe.asm      13,312 pairs of bytes, 1,024 for each of thirteen gaps
                   from 12 to 27 T-states, at T-states that run through the
                   line and through the frame: which second bytes come too
                   soon.
    speeds.asm     96 bytes of text written in the paper's lines with six
                   loops, 23 to 31 T-states a byte, one a frame (figure 20.2).
    blank.asm      the same and unrolled OUTI, 18 T-states a byte, written just
                   after the frame's interrupt, in lines the VDP does not draw.
    off.asm        the same with the display off.
    edge.asm       128 bytes by unrolled OUTI, written across the top of the
                   paper (figure 20.4).
    bottom.asm     the same across the bottom of the paper (figure 20.4).
    window.asm     1,600 bytes by unrolled OUTI from just after the frame's
                   interrupt on: how many arrive before the paper begins.
    sprites.asm    three of the loops in lines with four sprites each
                   (figure 20.6).
    reads.asm      128 bytes read back into the RAM in the paper's lines, with
                   INIR and with INI and JP NZ, and shown (figure 20.4).
    modes.asm      256 bytes by unrolled OUTI and by OTIR in the paper's lines
                   in Graphic I, Graphic II and text mode.
    otir.asm       WHERE IT BREAKS: a page of 768 names copied with OTIR while
                   the VDP draws the paper (figure 20.5).
    outi.asm       the same page copied with OUTI and JP NZ (figure 20.5).

Every price is the MSX's (chapter 14). The programs that wait for a point of
the frame take one frame's interrupt in mode 2 and then count T-states, as
chapter 18's do, on either machine; the debugger records every byte written
to the VDP and the moment it was written, and meas20.py plays them to
vdpslots.py. Cartridges end with asmparts.CART_END and build.sh assembles
with --syntax=bFw (chapter 15).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "ch18"))
from asmparts import (HEAD, CART_END, TEXT_PAGE, SHOW_PAGE, library, IM2, im2,  # noqa: E402
                      BOX_EMPTY, BOX_FULL)
from gen18 import wait_code, SYNC_ISR  # noqa: E402

BIOS = '        INCLUDE "bios.inc"\n'
NAMES = 0x1800
EU, JP = "MSXBOOK_EU16", "MSXBOOK_JP16"
LINE_T = 228
LINES = {EU: 313, JP: 262}
IRQ_LINE = {EU: 261, JP: 234}           # chapter 17
PAPER0 = {EU: 69, JP: 42}               # chapter 18
# where each program goes on after its HALT, T-states into the signal's line:
# the HALT's step decides it (chapter 18), and meas20.py reads it
BACK = {"beat": {EU: 120, JP: 119}, "speeds": 119, "blank": 119, "edge": 119, "otir": 119,
        "outi": 119, "reads": 119, "modes": 119, "bottom": 119, "window": 119, "sprites": 119}
CHOOSE_T = 14 + 5 + 11                  # LD A,($002B), RLA, JP NC
P = {"nop": 5, "ld r,n": 8, "out (n),a": 12, "out (c),r": 14, "outi": 18, "otir": 23,
     "jp": 11, "djnz": 14, "ret c_not": 6, "inc hl": 7, "or a": 5, "di": 5, "ld rr,nn": 11}


def head(name, what):
    return HEAD.format(name=name, chapter=20, what=what) + BIOS + IM2 + \
        f"BOX_EMPTY EQU {BOX_EMPTY}             ; the library's two boxes, characters 1 and 2\n" + \
        f"BOX_FULL  EQU {BOX_FULL}\n"


def addr(row, col):
    return NAMES + 32 * row + col


def db(text):
    """a text ending in 0; a character below 32 (the boxes) as a number"""
    parts, run = [], ""
    for ch in text:
        if ord(ch) < 32:
            if run:
                parts.append(f'"{run}"')
                run = ""
            parts.append(str(ord(ch)))
        else:
            run += ch
    if run:
        parts.append(f'"{run}"')
    return "        db " + ", ".join(parts + ["0"]) + "\n"


def label(row, col, text, name):
    assert col + len(text) <= 32, text
    return f"        ld b, {row}\n        ld c, {col}\n        ld hl, {name}\n        call puts\n", \
        f"{name}:" + db(text)


def lines_to(machine, line):
    """lines from the signal's line to LINE of the next frame"""
    return LINES[machine] - IRQ_LINE[machine] + line if line < IRQ_LINE[machine] else \
        line - IRQ_LINE[machine]


def frame_wait(prog, label, target, tail):
    """after `halt`: DI, then a wait chosen by the machine (bit 7 of $002B),
    so that the instruction TAIL T-states before the event runs at TARGET[m],
    (line, T-state) on each machine. Uses A, C, DE."""
    totals = {}
    for m in (EU, JP):
        line, t = target[m]
        back = BACK[prog][m] if isinstance(BACK[prog], dict) else BACK[prog]
        totals[m] = lines_to(m, line) * LINE_T + t - back - P["di"] - CHOOSE_T - tail
    w50, *_ = wait_code(totals[EU] - P["jp"], label + "5")
    w60, *_ = wait_code(totals[JP], label + "6")
    return f"""        di
        ld a, ($002B)           ; 14: bit 7 is 1 on a 50 Hz machine
        rla                     ;  5
        jp nc, {label}j         ; 11
""" + w50 + f"""        jp {label}g             ; 11
{label}j:
""" + w60 + f"""{label}g:
"""


def sync_frame():
    return """        in a, (VDP_CTRL)        ; no signal left over from before
        ei
        halt                    ; the frame's interrupt
"""


# ------------------------------------------------------------------ beat.asm
BEAT_ROW0 = 2               # the pairs from row 2, sixteen to a row
BEAT_LINE = 3               # the first pair in the paper's fourth line
BEAT_P0 = 0                 # ... at T-state 0 of it
BEAT_TURN = 115             # T-states a pair: 228 / 2 + 1, so that 228 pairs
BEAT_GAP = 20               # take every T-state of a line once
BEAT_FIRST = 8 + 12 + 7 + 8 + 12 + 7 + 8 + 10       # the turn's start to the first write


def beat_cells(turn=BEAT_TURN):
    """the address of each pair's two cells, in the order the pairs are made:
    the pair at T-state p goes to cells 2p and 2p + 1"""
    out = []
    for k in range(228):
        p = (BEAT_P0 + turn * k) % LINE_T
        out.append(addr(BEAT_ROW0, 0) + 2 * p)
    return out


# the gap's filler, and the T-states after the second byte that make the
# turn; a turn with no factor in common with 228 visits every T-state once
BEAT_FILL = {12: ([], ["nop", "ld e, 0"]), 17: (["nop"], ["ld e, 0"]), 20: (["ld e, 0"], ["nop"]),
             22: (["nop", "nop"], ["nop", "ld e, 0"]), 24: (["inc ix"], ["nop"]),
             25: (["nop", "ld e, 0"], ["nop", "nop"]), 26: (["inc sp", "dec sp"], ["nop"])}
BEAT_GAPS = [12, 17, 24, 25, 26]        # beat12.asm to beat26.asm; 22 is the workshop's


def beat_turn(gap):
    fill, tail = BEAT_FILL[gap]
    return 102 + sum(FILL_T[x] for x in fill + tail)


def beat(gap=BEAT_GAP, name="beat"):
    from math import gcd
    fill, tail = BEAT_FILL[gap]
    turn = beat_turn(gap)
    assert gcd(turn, LINE_T) == 1 and 12 + sum(FILL_T[x] for x in fill) == gap
    setup = P["ld rr,nn"] + 3 * P["ld r,n"]
    target = {m: (PAPER0[m] + BEAT_LINE, BEAT_P0) for m in (EU, JP)}
    l1, t1 = label(0, 0, f"PAIRS OF BYTES, {gap} T APART:", "t1")
    l2, t2 = label(18, 0, "\x02\x01 BOTH ARRIVED", "t2")
    l3, t3 = label(19, 0, "\x01  THE FIRST WAS LOST", "t3")
    cells = beat_cells(turn)
    table = "".join(f"        dw ${a | 0x4000:04X}\n" for a in cells)
    fills = "".join(f"        {x:<24}; {FILL_T[x]:2}\n" for x in fill)
    tails = "".join(f"        {x:<24}; {FILL_T[x]:2}\n" for x in tail)
    return head(name, "a pair of bytes at every T-state of a line") + f"""; 228 pairs of bytes, the filled box and then the empty one {gap} T-states after,
; {turn} T-states apart: the first pair's first byte at T-state {BEAT_P0} of the paper's
; line {BEAT_LINE}, the others at every other T-state of a line once. Each pair goes to
; two cells of the name table: the pair made at T-state p, to cells 2p and 2p + 1.
""" + TEXT_PAGE + l1 + l2 + l3 + im2("isr") + """        VDP_REG 1, $E0          ; display on, and the frame's signal on
""" + sync_frame() + frame_wait("beat", "w", target, setup + BEAT_FIRST) + f"""        ld hl, cells            ; 11
        ld b, 228               ;  8
        ld c, VDP_DATA          ;  8
        ld d, BOX_FULL          ;  8: the first byte
bt:     ld a, (hl)              ;  8
        out (VDP_CTRL), a       ; 12
        inc hl                  ;  7
        ld a, (hl)              ;  8
        out (VDP_CTRL), a       ; 12: the pair's two cells
        inc hl                  ;  7
        ld a, BOX_EMPTY         ;  8: the second byte
b1:     out (c), d              ; 14: the first, written 10 T-states in
""" + fills + f"""b2:     out (VDP_DATA), a       ; 12: the second, written 8 in: {gap} after the first
""" + tails + f"""        djnz bt                 ; 14: {turn} a pair
done:   jr done
""" + SYNC_ISR + t1 + t2 + t3 + "cells:\n" + table + library() + CART_END


# ----------------------------------------------------------------- probe.asm
PROBE_AT = addr(12, 15)
PROBE_TRIALS = 1024
PROBE_TURN = 229            # a line and a T-state: the pairs run through the line
FILL = {0: [], 5: ["nop"], 6: ["ret c"], 7: ["inc hl"], 8: ["ld h, 0"], 10: ["nop", "nop"],
        11: ["nop", "ret c"], 12: ["nop", "inc hl"], 13: ["nop", "ld h, 0"],
        14: ["inc hl", "inc hl"], 15: ["inc hl", "ld h, 0"]}
FILL_T = {"nop": 5, "ret c": 6, "inc hl": 7, "ld h, 0": 8, "ld e, 0": 8, "inc ix": 12,
          "inc sp": 7, "dec sp": 7}
# the gaps, and how each is made: (first OUT, filler): OUT (C),D writes 10
# T-states after it starts and OUT (n),A 8 (chapter 8)
GAPS = {12: ("c", 0), 14: ("n", 0), 17: ("c", 5), 18: ("c", 6), 19: ("c", 7), 20: ("c", 8),
        21: ("n", 7), 22: ("c", 10), 23: ("c", 11), 24: ("c", 12), 25: ("c", 13),
        26: ("c", 14), 27: ("c", 15)}


def gap_of(first, fill):
    if first == "c":                    # OUT (C),D, then OUT (n),A
        return (14 - 10) + fill + 8
    return (12 - 8) + fill + 10         # OUT (n),A, then OUT (C),D


def filler(t, regs_free):
    """NOPs and LD H,0 (H is free) that take T T-states"""
    for eights in range(0, t // 8 + 1):
        if (t - 8 * eights) % 5 == 0:
            return ["ld h, 0"] * eights + ["nop"] * ((t - 8 * eights) // 5)
    raise ValueError(t)


def probe():
    out = ""
    for g, (first, f) in GAPS.items():
        assert gap_of(first, f) == g and sum(FILL_T[x] for x in FILL[f]) == f
        body = 40 + P["or a"] + P["ld r,n"] + 14 + 12 + f + P["djnz"]
        wait = filler(PROBE_TURN - body, "h")
        pair = (["out (c), d", *FILL[f], "out (VDP_DATA), a"] if first == "c" else
                ["out (VDP_DATA), a", *FILL[f], "out (c), d"])
        a_val, d_val = ("BOX_EMPTY", "BOX_FULL") if first == "c" else ("BOX_FULL", "BOX_EMPTY")
        lines = "\n".join(f"        {x}" for x in pair[1:])
        out += f"""; the second byte {g} T-states after the first
        ld e, {PROBE_TRIALS // 256}
        ld d, {d_val}
p{g}:    VRAM_WRITE ${PROBE_AT:04X}        ; 40: the pair's two cells
        or a                    ;  5: the carry clear, for RET C
        ld a, {a_val}
q{g}:    {pair[0]}
{lines}
""" + "".join(f"        {x}\n" for x in wait) + f"""e{g}:    djnz p{g}               ; 14: {PROBE_TURN} a pair
        dec e
        jp nz, p{g}
"""
    return head("probe", "pairs of bytes at thirteen gaps") + f"""; {PROBE_TRIALS} pairs of bytes for each of thirteen gaps, the filled box first and the
; empty one second, to the same two cells; a pair every {PROBE_TURN} T-states, so that
; the pairs fall at every T-state of the line, in every line of the frame.
""" + TEXT_PAGE + """        VDP_REG 1, $C0          ; display on, no frame interrupt
        ld b, 0                 ; 256 pairs a turn of E
        ld c, VDP_DATA
""" + out + "done:   jr done\n" + library() + CART_END


# ---------------------------------------------------------------- the loops
TEXT = "ABCDEFGHIJKLMNOPQRSTUVWXYZ012345"       # a row of 32
assert len(TEXT) == 32
LOOPS = {   # T-states a byte: (label, kind)
    18: ("OUTI, UNROLLED: 18 T A BYTE", "outi"),
    23: ("OTIR: 23 T A BYTE", "otir"),
    25: ("LD A,(HL)/INC L/OUT: 25 T", "lio"),
    26: ("OUTI/LD A,(HL), UNROLLED: 26 T", "outi_ld"),
    27: ("LD A,(HL)/INC HL/OUT: 27 T", "lhio"),
    29: ("OUTI/JP NZ: 29 T A BYTE", "outi_jp"),
    31: ("OUTI/JR NZ: 31 T A BYTE", "outi_jr"),
}


def loop_code(speed, n, tag):
    """N bytes from HL (C = VDP_DATA, B free) to the VDP, SPEED T-states a byte"""
    kind = LOOPS[speed][1]
    b = n % 256                         # B = 0 makes 256 turns
    if kind == "outi":
        return f"        DUP {n}\n        outi                    ; 18\n        EDUP\n"
    if kind == "otir":
        return f"        ld b, {b}\n        otir                    ; 23 a byte, 18 the last\n"
    if kind == "lio":
        return (f"        DUP {n}\n        ld a, (hl)              ;  8\n        inc l                   ;  5\n"
                "        out (VDP_DATA), a       ; 12: 25\n        EDUP\n")
    if kind == "outi_ld":
        return (f"        DUP {n}\n        outi                    ; 18\n"
                "        ld a, (hl)              ;  8: 26, and A is not used\n        EDUP\n")
    if kind == "lhio":
        return (f"        DUP {n}\n        ld a, (hl)              ;  8\n        inc hl                  ;  7\n"
                "        out (VDP_DATA), a       ; 12: 27\n        EDUP\n")
    if kind == "outi_jp":
        return f"        ld b, {b}\n{tag}:   outi                    ; 18\n        jp nz, {tag}           ; 11: 29\n"
    if kind == "outi_jr":
        return f"        ld b, {b}\n{tag}:   outi                    ; 18\n        jr nz, {tag}           ; 13: 31\n"
    raise ValueError(kind)


def text_rows(rows):
    return TEXT * rows


SPEEDS = [23, 25, 26, 27, 29, 31]
SPEED_ROWS = 3              # 96 bytes a loop
SPEED_LINE = 40             # each loop starts in the paper's line 40...
SPEED_T = 60                # ... at about this T-state
BLANK = [18, 23, 25, 26, 27, 29, 31]
BLANK_ROWS = 2              # 64 bytes a loop
BLANK_DOWN = 1              # in the line after the signal's...
BLANK_T = 120               # ... at about this T-state


def tests(prog, speeds, rows, target=None, sync=True):
    """one loop a frame: block k is a label row and ROWS rows of text"""
    labels, texts, code = "", "", ""
    per = rows + 1
    for k, sp in enumerate(speeds):
        lab, txt = label(per * k, 0, LOOPS[sp][0], f"l{sp}")
        labels += lab
        texts += txt
        to = addr(per * k + 1, 0)
        start = f"""        ld hl, text             ; 11
        ld c, VDP_DATA          ;  8
        VRAM_WRITE ${to:04X}        ; 40
"""
        tail = 11 + 8 + 40
        if sync:
            code += sync_frame() + frame_wait(prog, f"f{sp}", target, tail)
        code += f"s{sp}:\n" + start + loop_code(sp, 32 * rows, f"x{sp}") + f"z{sp}:\n"
    return labels, texts, code


def speeds():
    target = {m: (PAPER0[m] + SPEED_LINE, SPEED_T) for m in (EU, JP)}
    labels, texts, code = tests("speeds", SPEEDS, SPEED_ROWS, target)
    return head("speeds", "six loops, in the paper's lines") + f"""; {32 * SPEED_ROWS} bytes of text written with six loops, 23 to 31 T-states a byte, one
; loop a frame, each started in the paper's line {SPEED_LINE}.
""" + TEXT_PAGE + labels + im2("isr") + """        VDP_REG 1, $E0          ; display on, and the frame's signal on
""" + code + "done:   jr done\n" + SYNC_ISR + texts + \
        "        ALIGN 256\ntext:   db \"" + text_rows(SPEED_ROWS) + "\"\n" + library() + CART_END


def blank():
    target = {m: (IRQ_LINE[m] + BLANK_DOWN, BLANK_T) for m in (EU, JP)}
    labels, texts, code = tests("blank", BLANK, BLANK_ROWS, target)
    return head("blank", "seven loops, in lines the VDP does not draw") + f"""; {32 * BLANK_ROWS} bytes of text written with seven loops, 18 to 31 T-states a byte, one
; loop a frame, each started in the line after the frame's signal.
""" + TEXT_PAGE + labels + im2("isr") + """        VDP_REG 1, $E0          ; display on, and the frame's signal on
""" + code + "done:   jr done\n" + SYNC_ISR + texts + \
        "        ALIGN 256\ntext:   db \"" + text_rows(BLANK_ROWS) + "\"\n" + library() + CART_END


def off():
    labels, texts, code = tests("off", BLANK, BLANK_ROWS, sync=False)
    return head("off", "seven loops, the display off") + f"""; {32 * BLANK_ROWS} bytes of text written with seven loops, 18 to 31 T-states a byte, with
; the display off; then the display on, to show them.
""" + TEXT_PAGE + labels + code + SHOW_PAGE + texts + \
        "        ALIGN 256\ntext:   db \"" + text_rows(BLANK_ROWS) + "\"\n" + library() + CART_END


# ------------------------------------------------------------------ edge.asm
EDGE_ROWS = 4               # 128 bytes
EDGE_T = 100                # started at about this T-state of a line...
EDGE = {    # ... of this line of the paper
    "edge": (-5, "OUTI, UNROLLED, ACROSS THE TOP:", "the top of the paper",
             "; the paper: the first ones in lines the VDP does not draw, the rest in the paper."),
    "bottom": (187, "UNROLLED OUTI ACROSS THE BOTTOM:", "the bottom of the paper",
               "; its last lines: the first ones in the paper, the rest in lines it does not draw."),
}


def edge(name="edge"):
    line, text, where, then = EDGE[name]
    target = {m: (PAPER0[m] + line, EDGE_T) for m in (EU, JP)}
    lab, txt = label(0, 0, text, "l1")
    to = addr(1, 0)
    started = f"{-line} lines above" if line < 0 else f"in line {line} of the paper,"
    return head(name, f"unrolled OUTI across {where}") + f"""; {32 * EDGE_ROWS} bytes by unrolled OUTI, 18 T-states a byte, started {started}
{then}
""" + TEXT_PAGE + lab + im2("isr") + """        VDP_REG 1, $E0          ; display on, and the frame's signal on
""" + sync_frame() + frame_wait(name, "w", target, 11 + 8 + 40) + f"""s1:     ld hl, text             ; 11
        ld c, VDP_DATA          ;  8
        VRAM_WRITE ${to:04X}        ; 40
""" + loop_code(18, 32 * EDGE_ROWS, "x1") + "z1:\ndone:   jr done\n" + SYNC_ISR + txt + \
        "        ALIGN 256\ntext:   db \"" + text_rows(EDGE_ROWS) + "\"\n" + library() + CART_END


# ------------------------------------------------------- otir.asm, outi.asm
PAGE_LINE = 0               # the copy starts in the paper's first line
PAGE_T = 40


def page_rows():
    return [f"{r:02d} " + "THE VDP TAKES A BYTE WHEN IT CAN"[:29] for r in range(24)]


def page_copy(name):
    otir = name == "otir"
    target = {m: (PAPER0[m] + PAGE_LINE, PAGE_T) for m in (EU, JP)}
    rows = page_rows()
    assert all(len(r) == 32 for r in rows)
    loop = ("""        ld d, 3                 ;  8: three times 256
x1:     otir                    ; 21 + 2: 23 a byte, 18 the last
        dec d                   ;  5
        jp nz, x1               ; 11
""" if otir else """        ld d, 3                 ;  8: three times 256
x1:     outi                    ; 18
        jp nz, x1               ; 11: 29 a byte
        dec d                   ;  5
        jp nz, x1               ; 11
""")
    what = ("WHERE IT BREAKS: a page copied with OTIR while the paper is drawn" if otir else
            "a page copied with OUTI and JP NZ while the paper is drawn")
    return head(name, what) + f"""; A page of 768 names copied to the name table in the paper's lines, from its
; first line, with {'OTIR, 23 T-states a byte' if otir else 'OUTI and JP NZ, 29 T-states a byte'}.
""" + TEXT_PAGE + im2("isr") + """        VDP_REG 1, $E0          ; display on, and the frame's signal on
""" + sync_frame() + frame_wait(name, "w", target, 11 + 8 + 40 + 8 + 8) + f"""s1:     ld hl, page             ; 11
        ld c, VDP_DATA          ;  8
        VRAM_WRITE ${NAMES:04X}        ; 40
        ld b, 0                 ;  8: 256
""" + loop + "z1:\ndone:   jr done\n" + SYNC_ISR + "page:\n" + \
        "".join(f'        db "{r}"\n' for r in rows) + library() + CART_END


# ----------------------------------------------------------------- reads.asm
READ_LINE = 40              # the reads start in the paper's line 40
READ_ROWS = 4               # 128 bytes
READ_AT = {"orig": 1, "inir": 7, "ini": 13}         # the rows of the three texts
READ_LABELS = {"orig": "WRITTEN:", "inir": "READ WITH INIR, 23 T A BYTE:",
               "ini": "READ WITH INI/JP NZ, 29 T:"}


def reads():
    n = 32 * READ_ROWS
    target = {m: (PAPER0[m] + READ_LINE, 60) for m in (EU, JP)}
    labs, txts = "", ""
    for k, r in READ_AT.items():
        a, b = label(r - 1, 0, READ_LABELS[k], f"l_{k}")
        labs += a
        txts += b
    src = addr(READ_AT["orig"], 0)
    lo, hi = src & 0xFF, src >> 8          # bit 6 is 0: an address to read from
    read_addr = f"""        ld a, ${lo:02X}               ;  8
        out (VDP_CTRL), a       ; 12
        ld a, ${hi:02X}               ;  8: bit 6 is 0, a read
        out (VDP_CTRL), a       ; 12: and the VDP reads ahead
"""
    return head("reads", "reading the VRAM in the paper's lines") + f"""; {n} bytes of text read back into the RAM in the paper's lines, with INIR and
; with INI and JP NZ, one a frame; then, with the display off, both shown.
buf1    EQU VARS + $20          ; what INIR read
buf2    EQU buf1 + {n}          ; what INI and JP NZ read
""" + TEXT_PAGE + labs + f"""        VRAM_WRITE ${src:04X}        ; the text, the display off
        ld hl, text
        ld b, {n}
        ld c, VDP_DATA
        otir
""" + im2("isr") + """        VDP_REG 1, $E0          ; display on, and the frame's signal on
""" + sync_frame() + frame_wait("reads", "u", target, 40) + "r1:\n" + read_addr + f"""        ld hl, buf1             ; 11
        ld bc, {n} * 256 + VDP_DATA   ; 11
        inir                    ; 23 a byte, 18 the last
z1:
""" + sync_frame() + frame_wait("reads", "v", target, 40) + "r2:\n" + read_addr + f"""        ld hl, buf2             ; 11
        ld bc, {n} * 256 + VDP_DATA   ; 11
x2:     ini                     ; 18
        jp nz, x2               ; 11: 29 a byte
z2:
""" + sync_frame() + f"""        di
        VDP_REG 1, $A0          ; display off, to show what was read
        VRAM_WRITE ${addr(READ_AT["inir"], 0):04X}
        ld hl, buf1
        ld b, {n}
        otir
        VRAM_WRITE ${addr(READ_AT["ini"], 0):04X}
        ld hl, buf2
        ld b, {n}
        otir
        VDP_REG 1, $C0          ; and on again
done:   jr done
""" + SYNC_ISR + txts + '        ALIGN 256\ntext:   db "' + text_rows(READ_ROWS) + '"\n' + \
        library() + CART_END


# ----------------------------------------------------------------- modes.asm
MODES = [("graphic1", 0x00, 0xE0), ("graphic2", 0x02, 0xE0), ("text", 0x00, 0xF0)]
MODE_LINE = 40
MODE_DEST = 0x3000          # six blocks of 256 from here: sprite patterns' room


def modes():
    target = {m: (PAPER0[m] + MODE_LINE, 60) for m in (EU, JP)}
    code, k = "", 0
    for name, r0, r1 in MODES:
        for loop in (18, 23):
            dest = MODE_DEST + 256 * k
            code += sync_frame() + f"""        di
m{k}:     VDP_REG 0, ${r0:02X}          ; {name}
        VDP_REG 1, ${r1:02X}
""" + frame_wait("modes", f"w{k}", target, 11 + 8 + 40) + f"""s{k}:     ld hl, ramp             ; 11
        ld c, VDP_DATA          ;  8
        VRAM_WRITE ${dest:04X}        ; 40
""" + loop_code(loop, 256, f"x{k}") + f"z{k}:\n"
            k += 1
    return head("modes", "OUTI and OTIR in three screen modes") + """; 256 bytes, unrolled OUTI and then OTIR, in the paper's lines of Graphic I,
; Graphic II and text mode, one a frame, to the VRAM from $3000. Nothing is
; shown: the debugger reads what arrived.
""" + TEXT_PAGE + im2("isr") + """        VDP_REG 1, $E0          ; display on, and the frame's signal on
""" + code + "done:   jr done\n" + SYNC_ISR + \
        "        ALIGN 256\nramp:\n" + "".join(f"        db {', '.join(str(v) for v in range(i, i + 16))}\n"
                                       for i in range(0, 256, 16)) + library() + CART_END


# --------------------------------------------------------------- window.asm
WINDOW_N = 1600             # more than the free lines of either machine take
WINDOW_DEST = 0x3000        # the sprite patterns' room, as in modes.asm


def window():
    target = {m: (IRQ_LINE[m] + BLANK_DOWN, BLANK_T) for m in (EU, JP)}
    data = "".join(f"        db {', '.join(str((i + k) % 256) for k in range(16))}\n"
                   for i in range(0, WINDOW_N, 16))
    return head("window", "unrolled OUTI from the frame's interrupt into the paper") + f"""; {WINDOW_N} bytes by unrolled OUTI, 18 T-states a byte, to the VRAM from ${WINDOW_DEST:04X},
; started in the line after the frame's signal: how many arrive before the
; VDP starts on the paper. Nothing is shown: the debugger reads what arrived.
""" + TEXT_PAGE + im2("isr") + """        VDP_REG 1, $E0          ; display on, and the frame's signal on
""" + sync_frame() + frame_wait("window", "w", target, 11 + 8 + 40) + f"""s1:     ld hl, bytes            ; 11
        ld c, VDP_DATA          ;  8
        VRAM_WRITE ${WINDOW_DEST:04X}        ; 40
""" + loop_code(18, WINDOW_N, "x1") + "z1:\ndone:   jr done\n" + SYNC_ISR + \
        "bytes:  ; 0 to 255, and on again\n" + data + library() + CART_END


# -------------------------------------------------------------- sprites.asm
SPRITE_LOOPS = [23, 25, 26]
SPRITE_LINE = 130           # the loops start in the paper's line 130, where...
SPRITE_TOP = 128            # ... four sprites are drawn in every line from 128 to 191


def sprites():
    target = {m: (PAPER0[m] + SPRITE_LINE, SPEED_T) for m in (EU, JP)}
    labels, texts, code = tests("sprites", SPRITE_LOOPS, SPEED_ROWS, target)
    rows = "".join(f"        db {SPRITE_TOP - 1 + 8 * (k // 4)}, {32 + 64 * (k % 4)}, 0, 1\n"
                   for k in range(32))
    return head("sprites", "three loops in lines with four sprites") + f"""; {32 * SPEED_ROWS} bytes of text written with three of speeds.asm's loops, one a frame,
; each started in the paper's line {SPRITE_LINE}, at the same T-state as there; four
; sprites, black squares, are drawn in each line from {SPRITE_TOP} to 191.
""" + TEXT_PAGE + labels + f"""        VRAM_WRITE $3800        ; sprite pattern 0: a filled square
        ld a, $FF
        ld b, 8
sq:     out (VDP_DATA), a
        djnz sq
        VRAM_WRITE $1B00        ; 32 sprites: Y, X, pattern 0, colour 1 (black)
        ld hl, sprite_table
        ld b, 128
        ld c, VDP_DATA
        otir
""" + im2("isr") + """        VDP_REG 1, $E0          ; display on, and the frame's signal on
""" + code + "done:   jr done\n" + SYNC_ISR + texts + "sprite_table:  ; a sprite is drawn from line Y + 1\n" + rows + \
        "        ALIGN 256\ntext:   db \"" + text_rows(SPEED_ROWS) + "\"\n" + library() + CART_END


PROGRAMS = {"beat": beat, **{f"beat{g}": (lambda g=g: beat(g, f"beat{g}")) for g in BEAT_GAPS},
            "probe": probe, "speeds": speeds, "blank": blank, "off": off,
            "edge": edge, "bottom": lambda: edge("bottom"), "window": window, "sprites": sprites,
            "reads": reads, "modes": modes, "otir": lambda: page_copy("otir"),
            "outi": lambda: page_copy("outi")}


def main():
    for name, make in PROGRAMS.items():
        with open(os.path.join(HERE, f"{name}.asm"), "w") as f:
            f.write(make())
    print(" ".join(f"{n}.asm" for n in PROGRAMS))


if __name__ == "__main__":
    main()
