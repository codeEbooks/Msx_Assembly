#!/usr/bin/env python3
"""genD.py - the programs of Appendix D: the Graphic II address of every line
of the paper, in a table sjasmplus makes, and the latest moment a byte written
there still shows in the same frame.

    python3 genD.py && ./build.sh

    tables.inc  the tables every program includes, made by sjasmplus's DUP
                from one expression each: for every line y of the paper, 0
                to 191, the address of the pattern byte and of the colour
                byte of its first column (x = 0), with the names 0 to 255 in
                each third, as the BIOS leaves them (R#3 = $FF, R#4 = $03),
                and with one set of shapes and colours for the three thirds
                (R#3 = $9F, R#4 = $00, chapter 22); the address of each row
                of 32 names; and the same as two tables of single bytes, the
                high bytes and the low bytes, each on a page of its own
    addr.asm    the tables photographed: frame by frame, one byte written
                at one entry of a table and put back the frame after; six
                passes, the patterns, the colours and the names in each of
                the two layouts
    timep.asm   a loop of exactly one frame, 50 Hz or 60 Hz as $002B says,
                that writes the first pattern byte of every line of the
                paper during that line, at the same T-state of each line, a
                T-state later every frame over thirteen frames; black in one
                frame and white in the next
    timec.asm   the same with the colour byte
    beam.asm    the same loop writing the backdrop, R#7, instead, behind a
                transparent paper: where the VDP is on each line at each
                T-state, over eleven frames
    calls.asm   the routines: the pattern address computed, from the table
                of words, and from the two pages of bytes; the next line
                down; the name address computed and from two pages. Every
                one run for all 192 lines and 32 columns, its answers sent
                to the VRAM; then each timed once with the debugger

The loops price every instruction as the MSX does: Zilog's T-states and one
more for every M1 (chapter 14). They wait for one frame's interrupt in mode 2,
as chapter 18's programs do, and from then on keep the interrupts off and
count. build.sh assembles with --syntax=bFw (chapter 15).
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
for d in ("tools", "ch26"):
    sys.path.insert(0, os.path.join(REPO, d))
from asmparts import IM2, im2  # noqa: E402
from gen26 import tidy  # noqa: E402  (chapter 26)

EU, JP = "MSXBOOK_EU16", "MSXBOOK_JP16"
LINE_T = 228
FRAME_T = {EU: 71364, JP: 59736}
LINES = {EU: 313, JP: 262}
PAPER0 = {EU: 69, JP: 42}           # the paper's first line (chapter 18)
IRQ_LINE = {EU: 261, JP: 234}       # the line of the frame's signal (chapter 17)
BACK_W = 118                        # chapter 18: after HALT, this far into the
                                    # signal's line, give or take the HALT's step
WAIT_LINES = {EU: 119, JP: 68}      # the loops' wait in the border, in lines
assert all(LINES[m] - 192 - WAIT_LINES[m] == 2 for m in (EU, JP))

# the two layouts: R#3, R#4
BIOS, THIRD = "bios", "third"
REGS34 = {BIOS: (0xFF, 0x03), THIRD: (0x9F, 0x00)}


# ------------------------------------------------------------------ addresses
def pattern(x, y, layout=BIOS):
    """the model: the pattern byte of pixel (x, y), names 0 to 255 in each third"""
    third = y >> 6 if layout == BIOS else 0
    return third * 2048 + ((y >> 3) & 7) * 256 + (x & 0xF8) + (y & 7)


def colour(x, y, layout=BIOS):
    return 0x2000 + pattern(x, y, layout)


def name(x, y):
    return 0x1800 + (y >> 3) * 32 + (x >> 3)


# the expressions of tables.inc, one per table, with y the line
TABLES = [
    ("patrow", "dw", "((y & $F8) << 5) | (y & 7)", 192,
     "the pattern byte of (0, y), the BIOS's layout", lambda y: pattern(0, y)),
    ("colrow", "dw", "$2000 | ((y & $F8) << 5) | (y & 7)", 192,
     "its colour byte", lambda y: colour(0, y)),
    ("patrow3", "dw", "((y & $38) << 5) | (y & 7)", 192,
     "the pattern byte of (0, y), one set for the three thirds", lambda y: pattern(0, y, THIRD)),
    ("colrow3", "dw", "$2000 | ((y & $38) << 5) | (y & 7)", 192,
     "its colour byte", lambda y: colour(0, y, THIRD)),
    ("namerow", "dw", "$1800 + (y << 5)", 24,
     "the name of column 0 of row y, 0 to 23", lambda r: 0x1800 + 32 * r),
]
PAGES = [
    ("pathi", "high (((y & $F8) << 5) | (y & 7))", lambda y: pattern(0, y) >> 8),
    ("patlo", "low (((y & $F8) << 5) | (y & 7))", lambda y: pattern(0, y) & 0xFF),
    ("namhi", "high ($1800 + ((y & $F8) << 2))", lambda y: name(0, y) >> 8),
    ("namlo", "low ($1800 + ((y & $F8) << 2))", lambda y: name(0, y) & 0xFF),
]


def tables_inc():
    out = ["; tables.inc -- appendix D: the Graphic II addresses of every line of",
           "; the paper, y = 0 to 191, at x = 0; add x AND $F8 for any other column.",
           "; sjasmplus makes every entry with DUP, from one expression a table.",
           "; generated by genD.py", ""]
    for lab, kind, expr, n, what, _ in TABLES:
        out += [f"; {lab}: {what}", f"{lab}:", "y = 0", f"        DUP {n}",
                f"        {kind} {expr}", "y = y + 1", "        EDUP", ""]
    out += ["; the same as single bytes, the high bytes on one page and the low bytes",
            "; on the next: the routines go from one to the other with INC H", ""]
    for lab, expr, _ in PAGES:
        out += ["        ALIGN 256", f"{lab}:", "y = 0", "        DUP 192",
                f"        db {expr}", "y = y + 1", "        EDUP", ""]
    return "\n".join(out) + "\n"


# ------------------------------------------------------------------ prices
PRICE = [   # MSX T-states: Zilog's and one per M1 (chapter 14)
    (r"nop", 5), (r"ld a, i", 11), (r"ld [abcdehl], [abcdehl]", 5),
    (r"ld [abcdehl], (\$[0-9A-F]+|\d+|high \w+)", 8), (r"ld a, \(hl\)", 8), (r"inc hl", 7), (r"dec hl", 7),
    (r"out \(VDP_(DATA|CTRL)\), a", 12), (r"(or|xor|and) \$\w+", 8),
    (r"(dec|inc) [abcdehl]", 5), (r"jp (nz, )?\w+", 11), (r"ld hl, \w+", 11),
    (r"ld a, \(\w+\)", 14), (r"call \w+", 18), (r"ret", 11), (r"di", 5),
]


def price(instr):
    s = " ".join(instr.split(";")[0].split())
    for pat, t in PRICE:
        if re.fullmatch(pat, s):
            return t
    raise ValueError(f"no price for {instr!r}")


def cost(lines):
    """the T-states of LINES, straight through; a DUP n ... EDUP block n times"""
    total, times, inside = 0, 1, 0
    for l in lines:
        s = " ".join(l.split(";")[0].split())
        if not s:
            continue
        if s.startswith("DUP "):
            times, inside = int(s.split()[1]), 0
        elif s == "EDUP":
            total += times * inside
            times = 1
        elif times > 1:
            inside += price(s)
        else:
            total += price(s)
    return total


# fillers that touch nothing the loops keep: NOP (5), LD D,0 (8), LD A,I (11)
FILL = [("nop", 5), ("ld d, 0", 8), ("ld a, i", 11)]


def pad(t):
    """the fewest fillers that take exactly T T-states (all but A, D and the
    flags left alone)"""
    if t == 0:
        return []
    best = {0: []}
    for n in range(1, t + 1):
        cands = [best[n - c] + [s] for s, c in FILL if n - c in best]
        if cands:
            best[n] = min(cands, key=len)
    if t not in best:
        raise ValueError(f"no pad of {t}")
    out = best[t]
    # in order: the elevens, then the eights, then the fives
    return sorted(out, key=lambda s: -dict(FILL)[s])


def pad_lines(t, why):
    """the pad as lines: three or more of a filler as a DUP block"""
    p = pad(t)
    out = []
    for s, _ in FILL[::-1]:
        n = p.count(s)
        if n >= 3:
            out += [f"        DUP {n}", f"        {s}", "        EDUP"]
        else:
            out += [f"        {s}"] * n
    if out:
        out[0] = f"{out[0]:<32}; {why}: {t}"
    assert cost(out) == t, (t, out)
    return out


def head(name, what):
    return f"""; {name}.asm -- appendix D: {what}
; generated by genD.py
        INCLUDE "msx.inc"
        OUTPUT "{name}.rom"
        ORG $4000
        CART_HEADER init
VARS    EQU RAM_START + $100    ; the program's variables: the code is in ROM
"""


TAIL = """
        INCLUDE "tables.inc"
        ASSERT $ <= $8000, the program is longer than the cartridge
        ds $8000 - $, $FF       ; pad the cartridge to 16 KB
"""

ISR = """
; isr: the frame's interrupt; reading the status takes the signal down
isr:    push af
        in a, (VDP_CTRL)
        pop af
        ei
        ret
"""


def setup(r3, r4, patt, col, names="order", r7=0x0F, r1=0xE0):
    """Graphic II with the display off: every pattern byte PATT, every colour
    byte COL, names 0 to 255 in each third ("order") or all 0 ("zero"), no
    sprites, then R#1"""
    n = ("""        VRAM_WRITE $1800        ; names: 0 to 255 in each third
        ld b, 3
.n:     xor a
.n1:    out (VDP_DATA), a
        inc a
        jr nz, .n1
        djnz .n
""" if names == "order" else """        VRAM_WRITE $1800        ; names: all 0
        ld bc, 768
.n:     xor a
        out (VDP_DATA), a
        dec bc
        ld a, b
        or c
        jr nz, .n
""")
    return f"""        VDP_REG 1, $80          ; display off
        VDP_REG 0, $02          ; Graphic II
        VDP_REG 2, $06          ; names              $1800
        VDP_REG 3, ${r3:02X}          ; colours            $2000
        VDP_REG 4, ${r4:02X}          ; patterns           $0000
        VDP_REG 5, $36          ; sprite attributes  $1B00
        VDP_REG 6, $07          ; sprite patterns    $3800
        VDP_REG 7, ${r7:02X}          ; backdrop
        VRAM_WRITE $0000        ; patterns: ${patt:02X}
        ld bc, 6144
.p:     ld a, ${patt:02X}
        out (VDP_DATA), a
        dec bc
        ld a, b
        or c
        jr nz, .p
        VRAM_WRITE $2000        ; colours: ${col:02X}
        ld bc, 6144
.c:     ld a, ${col:02X}
        out (VDP_DATA), a
        dec bc
        ld a, b
        or c
        jr nz, .c
""" + n + f"""        VRAM_WRITE $1B00        ; no sprites
        ld a, $D0
        out (VDP_DATA), a
        VDP_REG 1, ${r1:02X}          ; display on{', the frame interrupt on' if r1 & 0x20 else ''}
"""


# ------------------------------------------------------------------ addr.asm
# the passes: label, table, entries, layout, patterns, colours, names, old, new
PASSES = [
    ("pb", "patrow", 192, BIOS, 0x00, 0x1F, "order", 0x00, 0xFF),
    ("cb", "colrow", 192, BIOS, 0xF0, 0xFF, "order", 0xFF, 0x1F),
    ("p3", "patrow3", 192, THIRD, 0x00, 0x1F, "order", 0x00, 0xFF),
    ("c3", "colrow3", 192, THIRD, 0xF0, 0xFF, "order", 0xFF, 0x1F),
    ("nb", "namerow", 24, BIOS, 0x00, 0x1F, "zero", 0x00, 0x01),
    ("n3", "namerow", 24, THIRD, 0x00, 0x1F, "zero", 0x00, 0x01),
]
NAME_SHAPE = 1                  # the names passes: shape 1 of each third is solid ink


def write_at_de(value):
    return f"""        ld a, e
        out (VDP_CTRL), a
        ld a, d
        or $40
        out (VDP_CTRL), a       ; write at DE
        ld a, ${value:02X}
        out (VDP_DATA), a
"""


def addr():
    body = ""
    for lab, table, n, layout, patt, col, names, old, new in PASSES:
        r3, r4 = REGS34[layout]
        what = {"patrow": "patterns", "colrow": "colours", "patrow3": "patterns",
                "colrow3": "colours", "namerow": "names"}[table]
        body += f"""
; pass {lab}: the {what}, {'the BIOS layout' if layout == BIOS else 'one set for the three thirds'}
; ({n} entries of {table}: ${new:02X} written at one a frame, ${old:02X} put back)
{lab}:
        di
""" + setup(r3, r4, patt, col, names, r1=0xE0)
        if names == "zero":
            for third in range(3):
                a = third * 2048 + NAME_SHAPE * 8
                body += f"""        VRAM_WRITE ${a:04X}        ; shape {NAME_SHAPE} of third {third}: solid
        ld b, 8
.s{third}:    ld a, $FF
        out (VDP_DATA), a
        djnz .s{third}
"""
        body += f"""        ld hl, {table}
        ld e, (hl)              ; DE: the first entry, for the first put-back
        inc hl
        ld d, (hl)
        dec hl
        ld b, {n}
        in a, (VDP_CTRL)
        ei
        halt                    ; a frame of the screen as it is
{lab}s:    halt                    ; the end of a frame's paper
        di
""" + write_at_de(old).replace("; write at DE", "; the last entry back") + \
            """        ld e, (hl)
        inc hl
        ld d, (hl)
        inc hl
""" + write_at_de(new).replace("; write at DE", "; this entry") + f"""        nop                     ; the VDP takes it meanwhile
        nop
{lab}m:    ei                      ; measD.py's mark: the frame after shows it
        djnz {lab}s
        halt
        di
""" + write_at_de(old).replace("; write at DE", "; the last entry back")
    return head("addr", "every entry of the tables, photographed") + IM2 + """; Six passes, each with the screen set up again with the display off. In
; each frame one byte is written at the address one entry of a table gives,
; and the one before is put back, so that the next frame's photograph shows
; where that address is on the screen, and nothing else.
init:   di
        ld sp, SYS_AREA
""" + im2("isr") + body + """done:   jr done
""" + ISR + TAIL


# ------------------------------------------------------------------ the loops
# A loop of exactly one frame per turn (WAIT_LINES[m] + 2 lines in the
# border, 192 in the paper), in COPIES turns of the same length that differ
# only in where the paper's lines fall in them: turn k's writes are k
# T-states later in every line than turn 0's, and its pad after the paper
# k shorter. Turn k jumps to turn k + 1, the last to the first.
#
#   tK:   call vwait              48 + WAIT_LINES x 228
#         pad P0 + k
#         call lines              18 + lines' set-up + 192 x 228 + 11
#         pad Q0 - k
#         jp tK+1                 11
VWAIT_FIXED = 18 + 14 + 5 + 11      # CALL, LD A,(nn), LD E,A, RET


def vwait():
    inner = 228 - 5 - 11
    return """
; vwait: WAIT_LINES lines of 228 T-states, as many as the machine needs
vwait:  ld a, (nwait)           ; 14
        ld e, a                 ;  5
vw:
""" + "\n".join(pad_lines(inner, "the rest of a line")) + """
        dec e                   ;  5
        jp nz, vw               ; 11: 228 a turn
        ret                     ; 11
"""


def loop_program(name, what, say, setup_text, lines_setup, line_body, write_at, copies, w_min,
                 first_value):
    """LINES_SETUP: the lines before the first turn of LINES, LINE_BODY its
    turn of exactly 228 T-states (the label lp on the first), WRITE_AT: the
    T-state of the turn at which the write that counts happens"""
    cs = cost([l for l in lines_setup if l.strip() and not l.strip().startswith(";")])
    body = [l for l in line_body if l.strip() and not l.strip().startswith(";")]
    t = cost([re.sub(r"^\w+:\s*", "", l) for l in body])
    assert t == LINE_T, (name, t)
    p0 = 20
    q0 = 2 * LINE_T - VWAIT_FIXED - 18 - 11 - 11 - cs - p0
    s = 2 * LINE_T + w_min - BACK_W - 5 - VWAIT_FIXED - p0 - 18 - cs - write_at
    assert q0 - (copies - 1) >= 20 and s >= 20, (name, q0, s)
    turns = ""
    for k in range(copies):
        turns += f"t{k}:     call vwait\n" + "\n".join(pad_lines(p0 + k, f"turn {k}: {p0} + {k}")) + \
            "\n        call lines\n" + "\n".join(pad_lines(q0 - k, f"{q0} - {k}")) + \
            f"\n        jp t{(k + 1) % copies}\n"
    return head(name, what) + IM2 + f"""nwait   EQU VARS                ; lines of vwait: {WAIT_LINES[EU]} at 50 Hz, {WAIT_LINES[JP]} at 60 Hz
{say}init:   di
        ld sp, SYS_AREA
""" + setup_text + f"""        ld a, ($002B)           ; bit 7 is 1 on a 50 Hz machine (chapter 4)
        rlca
        ld a, {WAIT_LINES[EU]}
        jr c, hz50
        ld a, {WAIT_LINES[JP]}
hz50:   ld (nwait), a
""" + im2("isr") + f"""        ld b, ${first_value:02X}               ; the value before the first turn's
        in a, (VDP_CTRL)        ; no signal left over from before
        ei
        halt                    ; one frame's interrupt: in step with the picture
        di
""" + "\n".join(pad_lines(s, "to turn 0")) + "\n" + turns + """
; lines: the paper's 192 lines, one turn of 228 T-states each
lines:
""" + "\n".join(lines_setup) + "\n" + "\n".join(line_body) + """
        ret                     ; 11
""" + vwait() + ISR + TAIL, {"p0": p0, "q0": q0, "s": s, "cs": cs, "write_at": write_at,
                             "copies": copies, "w_min": w_min}


TIME_COPIES = 13                # turns: writes at T-states w_min to w_min + 12
TIME_W = 24
BEAM_COPIES = 11
BEAM_W = 37
PLANS = {}


def time_program(kind):
    """timep (the pattern byte) or timec (the colour byte) of column 0"""
    table = "patrow" if kind == "p" else "colrow"
    old, new = (0x00, 0xFF) if kind == "p" else (0xFF, 0x1F)
    toggle = old ^ new
    what = "pattern" if kind == "p" else "colour"
    setup_text = setup(0xFF, 0x03, 0x00 if kind == "p" else 0xFF,
                       0x1F if kind == "p" else 0xFF, r1=0xE0)
    lines_setup = [
        f"        ld hl, {table}{' ' * (15 - len(table))}; 11: line 0's address",
        "        ld a, (hl)              ;  8",
        "        inc hl                  ;  7",
        "        out (VDP_CTRL), a       ; 12",
        "        ld a, (hl)              ;  8",
        "        inc hl                  ;  7",
        "        or $40                  ;  8",
        "        out (VDP_CTRL), a       ; 12: write from there",
        "        ld c, 192               ;  8",
        "        ld a, b                 ;  5",
        f"        xor ${toggle:02X}               ;  8: this turn's value, ${old:02X} or ${new:02X}",
        "        ld b, a                 ;  5",
    ]
    line_body = [
        "lp:     ld a, b                 ;  5",
        f"wr:     out (VDP_DATA), a       ; 12: the {what} byte",
    ] + pad_lines(40, "until the VDP has taken it") + [
        "        ld a, (hl)              ;  8: the next line's address",
        "        inc hl                  ;  7",
        "        out (VDP_CTRL), a       ; 12",
        "        ld a, (hl)              ;  8",
        "        inc hl                  ;  7",
        "        or $40                  ;  8",
        "        out (VDP_CTRL), a       ; 12",
    ] + pad_lines(93, "the rest of the line") + [
        "        dec c                   ;  5",
        "        jp nz, lp               ; 11: 228 a line",
    ]
    say = f"""; The {what} byte of column 0 of each line of the paper written while the
; VDP draws that line: turn k writes it k T-states later in the line than turn 0
; does, for k = 0 to {TIME_COPIES - 1} (measD.py reads the T-state of every write), and the
; value is ${new:02X} in one turn and ${old:02X} in the next ({'black, then white' if kind == 'p' else 'black ink, then white'}):
; where the write is in time, the frame's photograph shows the new value.
"""
    text, plan = loop_program(f"time{kind}", f"the {what} byte of every line, written late",
                              say, setup_text, lines_setup, line_body, 13, TIME_COPIES, TIME_W, old)
    PLANS[f"time{kind}"] = plan
    return text


BEAM_COLOURS = (0x01, 0x0F)     # the backdrop: black, white, a line each


def beam():
    setup_text = setup(0xFF, 0x03, 0x00, 0x00, r7=BEAM_COLOURS[1], r1=0xE0)
    toggle = BEAM_COLOURS[0] ^ BEAM_COLOURS[1]
    lines_setup = ["        ld c, 192               ;  8"]
    line_body = [
        "lp:     ld a, b                 ;  5: this line's backdrop",
        "        out (VDP_CTRL), a       ; 12",
        "        ld a, $87               ;  8",
        "wr:     out (VDP_CTRL), a       ; 12: R#7",
        "        ld a, b                 ;  5",
        f"        xor ${toggle:02X}               ;  8: black, white",
        "        ld b, a                 ;  5",
    ] + pad_lines(228 - 5 - 12 - 8 - 12 - 5 - 8 - 5 - 5 - 11, "the rest of the line") + [
        "        dec c                   ;  5",
        "        jp nz, lp               ; 11: 228 a line",
    ]
    say = f"""; The paper transparent: every pattern byte 0, every colour 0, so that the
; backdrop shows on the whole line. Each line of the paper gets a backdrop of
; its own, black and white in turn, written k T-states later in the line in
; turn k than in turn 0, k = 0 to {BEAM_COPIES - 1} (measD.py reads the T-state of every
; write): the photograph shows where the VDP was.
"""
    text, plan = loop_program("beam", "where the VDP is on every line of the paper", say,
                              setup_text, lines_setup, line_body, 33, BEAM_COPIES, BEAM_W,
                              BEAM_COLOURS[0])
    PLANS["beam"] = plan
    return text


# ------------------------------------------------------------------ calls.asm
ROUTINES = '''
; pcalc: B = x, C = y -> HL = the pattern byte of (x, y), the BIOS's layout:
; H = y >> 3, L = (x AND $F8) OR (y AND 7). Uses A.
pcalc:  ld a, c                 ;  5
        rrca                    ;  5
        rrca                    ;  5
        rrca                    ;  5
        and $1F                 ;  8: y >> 3
        ld h, a                 ;  5
        ld a, b                 ;  5
        xor c                   ;  5
        and $F8                 ;  8
        xor c                   ;  5: x's bits 7-3, y's 2-0
        ld l, a                 ;  5
        ret                     ; 11

; ptab: the same from patrow, a word a line. Uses A, DE.
ptab:   ld l, c                 ;  5
        ld h, 0                 ;  8
        add hl, hl              ; 12: y x 2
        ld de, patrow           ; 11
        add hl, de              ; 12
        ld a, (hl)              ;  8
        inc hl                  ;  7
        ld h, (hl)              ;  8
        ld l, a                 ;  5: patrow's entry for y
        ld a, b                 ;  5
        and $F8                 ;  8
        or l                    ;  5
        ld l, a                 ;  5
        ret                     ; 11

; ppage: the same from pathi and patlo, a byte a line on two pages. Uses A.
ppage:  ld h, high pathi        ;  8
        ld l, c                 ;  5
        ld a, b                 ;  5
        and $F8                 ;  8
        inc h                   ;  5: patlo
        or (hl)                 ;  8
        dec h                   ;  5: pathi
        ld h, (hl)              ;  8
        ld l, a                 ;  5
        ret                     ; 11

; pdown: HL = the pattern byte of (x, y) -> of (x, y + 1), the BIOS's
; layout, y < 191. Uses A.
pdown:  inc l                   ;  5
        ld a, l                 ;  5
        and 7                   ;  8
        ret nz                  ; 12 out, 6 on: seven lines in eight
        ld a, l                 ;  5: the next row of characters
        sub 8                   ;  8
        ld l, a                 ;  5
        inc h                   ;  5
        ret                     ; 11

; ncalc: B = x, C = y -> HL = where the name of (x, y) is: $1800 + (y >> 3) x 32 +
; (x >> 3). Uses A.
ncalc:  ld a, c                 ;  5
        and $F8                 ;  8
        ld l, a                 ;  5
        ld h, 6                 ;  8: $0600 + (y AND $F8)
        add hl, hl              ; 12
        add hl, hl              ; 12: x 4, $1800 + (y >> 3) x 32
        ld a, b                 ;  5
        rrca                    ;  5
        rrca                    ;  5
        rrca                    ;  5
        and $1F                 ;  8: x >> 3
        or l                    ;  5
        ld l, a                 ;  5
        ret                     ; 11

; npage: the same from namhi and namlo. Uses A.
npage:  ld h, high namhi        ;  8
        ld l, c                 ;  5
        ld a, b                 ;  5
        rrca                    ;  5
        rrca                    ;  5
        rrca                    ;  5
        and $1F                 ;  8
        inc h                   ;  5: namlo
        or (hl)                 ;  8
        dec h                   ;  5: namhi
        ld h, (hl)              ;  8
        ld l, a                 ;  5
        ret                     ; 11
'''
CALLS = ["pcalc", "ptab", "ppage", "pdown", "ncalc", "npage"]
LAST_Y = {"pdown": 191}         # pdown: lines 0 to 190
CALL_X = lambda c, y: 8 * c + ((c + y) & 7)     # noqa: E731 the x of column c on line y
TIMED = [("pcalc", 77, 133), ("ptab", 77, 133), ("ppage", 77, 133), ("pdown", 77, 133),
         ("pdown", 77, 135), ("ncalc", 77, 133), ("npage", 77, 133)]
RESULTS_AT = 0x0000             # the answers in the VRAM, two bytes each


def calls():
    sweeps = ""
    for r in CALLS:
        last = LAST_Y.get(r, 192)
        call = "        call pcalc\n        call pdown\n" if r == "pdown" else f"        call {r}\n"
        sweeps += f"""
; {r}: every line, 0 to {last - 1}, and 32 columns, x = 8c + ((c + y) AND 7)
s_{r}:  VRAM_WRITE ${RESULTS_AT:04X}
        ld c, 0                 ; y
y_{r}:  ld b, 0                 ; 8c
x_{r}:  ld a, b
        rrca
        rrca
        rrca                    ; c
        add a, c
        and 7
        or b
        ld b, a                 ; x
        push bc
{call}        ld a, l
        out (VDP_DATA), a
        ld a, h
        out (VDP_DATA), a       ; HL, low byte first
        pop bc
        ld a, b
        and $F8
        add a, 8
        ld b, a
        jr nz, x_{r}
        inc c
        ld a, c
        cp {last}
        jr nz, y_{r}
e_{r}:  nop                     ; measD.py reads the VRAM here
"""
    timed = "\n; each routine once, with its CALL, between two labels the debugger times\n"
    for k, (r, x, y) in enumerate(TIMED):
        pre = "        call pcalc\n" if r == "pdown" else ""
        timed += f"""        ld bc, ${x:02X}{y:02X}            ; x = {x}, y = {y}
{pre}a{k}:     call {r}
b{k}:     nop
"""
    return head("calls", "the routines, for every line and column") + """; The display off, so that the answers can go to the VRAM at any speed.
init:   di
        ld sp, SYS_AREA
        VDP_REG 1, $80          ; display off
""" + sweeps + timed + """done:   jr done
""" + ROUTINES + TAIL


# ------------------------------------------------------------------ main
PROGRAMS = {"addr": addr, "timep": lambda: time_program("p"), "timec": lambda: time_program("c"),
            "beam": beam, "calls": calls}


def main():
    with open(os.path.join(HERE, "tables.inc"), "w") as f:
        f.write(tables_inc())
    for n, fn in PROGRAMS.items():
        text = fn()
        with open(os.path.join(HERE, f"{n}.asm"), "w") as f:
            f.write(tidy(text))
    for f in ("msx.inc", "bios.inc"):
        src = os.path.join(REPO, f)
        with open(src) as a, open(os.path.join(HERE, f), "w") as b:
            b.write(a.read())
    print("appendix D:", len(PROGRAMS), "programs and tables.inc")


if __name__ == "__main__":
    main()
