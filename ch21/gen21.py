#!/usr/bin/env python3
"""gen21.py - the programs of chapter 21: the screen modes.

    python3 gen21.py && ./build.sh

    text.asm       one picture, a disc in two colours and two lines of
    graphic1.asm   words, drawn in each of the four modes the TMS9918A
    graphic2.asm   knows (figure 21.1), each mode set from the registers,
    multi.asm      with the BIOS's tables; every other byte of the VRAM is
                   noise, the BIOS's first 16 KB
    keep.asm       $FF written to each of the eight registers: the bits the
                   VDP keeps
    bios.asm       INITXT, INIT32, INIGRP and INIMLT called in turn: the
                   registers and the table addresses the BIOS chooses
    bits.asm       WHERE IT BREAKS: a Graphic I page, and only R#1 changed,
                   and R#7 (figure 21.3)

The picture is described once, as pixels of the paper (ideal()), and gen21.py
works out each mode's tables from it: its names, its patterns and its colours.
Programs end with asmparts.CART_END and build.sh assembles with --syntax=bFw.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
from asmparts import HEAD, CART_END, TEXT_PAGE, library  # noqa: E402

BIOS = '        INCLUDE "bios.inc"\n'
BLACK, LIGHT_GREEN, DARK_BLUE, WHITE = 1, 3, 4, 15

# ------------------------------------------------------------------ the picture
DISC_X, DISC_Y, DISC_R = 128, 108, 56   # a disc: centre and radius, in pixels
SPLIT = 108                             # above this line dark blue, from it light green
TEXT_X0 = 9                             # text mode's 240 pixels: from x = 9 (measured, meas21.py)


def inside(x, y):
    """is the point (x, y) of the paper inside the disc? (pixel centres at + 0.5)"""
    return (x - DISC_X) ** 2 + (y - DISC_Y) ** 2 < DISC_R ** 2


def ideal(x, y):
    """the colour of pixel (x, y) of the picture, words left out"""
    if not inside(x + 0.5, y + 0.5):
        return WHITE
    return DARK_BLUE if y < SPLIT else LIGHT_GREEN


# each mode: R#0 to R#7 as the program sets them, and the two lines of words
MODES = {
    "text": {"regs": [0x00, 0xD0, 0x00, 0x00, 0x01, 0x00, 0x00, 0x1F],
             "words": ["TEXT MODE: 40 X 24 CHARACTERS OF 6 X 8", "TWO COLOURS, BOTH FROM R#7"]},
    "graphic1": {"regs": [0x00, 0xC0, 0x06, 0x80, 0x00, 0x36, 0x07, 0x0F],
                 "words": ["GRAPHIC I: 32 X 24 OF 8 X 8", "TWO COLOURS FOR EIGHT CHARACTERS"]},
    "graphic2": {"regs": [0x02, 0xC0, 0x06, 0xFF, 0x03, 0x36, 0x07, 0x0F],
                 "words": ["GRAPHIC II: 256 X 192 PIXELS", "TWO COLOURS FOR EVERY 8 X 1"]},
    "multi": {"regs": [0x00, 0xC8, 0x02, 0x00, 0x00, 0x36, 0x07, 0x0F], "words": []},
}
REG_NOTE = {
    "text": ["mode: M3 = 0", "16 KB, M1: text mode", "names    $0000",
             "no colour table in text mode", "patterns $0800", "no sprites in text mode",
             "no sprites in text mode", "ink black (1), backdrop white (15)"],
    "graphic1": ["mode: M3 = 0", "16 KB: Graphic I", "names    $1800",
                 "colours  $2000, 32 bytes", "patterns $0000", "sprite attributes $1B00",
                 "sprite patterns   $3800", "backdrop white (15)"],
    "graphic2": ["mode: M3 = 1, Graphic II", "16 KB", "names    $1800",
                 "colours  $2000, 6,144 bytes", "patterns $0000, 6,144 bytes",
                 "sprite attributes $1B00", "sprite patterns   $3800", "backdrop white (15)"],
    "multi": ["mode: M3 = 0", "16 KB, M2: multicolour", "names    $0800",
              "no colour table in multicolour", "patterns $0000", "sprite attributes $1B00",
              "sprite patterns   $3800", "backdrop white (15)"],
}
DISPLAY_OFF = 0xBF          # R#1 AND this: the display off while the tables are written


def cell_rows(width, x0, cols, ink_of):
    """the picture cut into COLS cells of WIDTH x 8 a row from paper x X0: for
    each cell (col, row) with ink in it, its 8 pattern bytes (bit 7 on the
    left) and the ink of each of its lines"""
    cells = {}
    for row in range(24):
        for col in range(cols):
            pat, inks = [], []
            for line in range(8):
                y, byte, ink = 8 * row + line, 0, None
                for i in range(width):
                    c = ideal(x0 + width * col + i, y)
                    if c != WHITE:
                        byte |= 0x80 >> i
                        ink = c
                pat.append(byte)
                inks.append(ink_of(y, ink))
            if any(pat):
                cells[col, row] = (tuple(pat), tuple(inks))
    return cells


def label_names(words, cols):
    names = [32] * (24 * cols)
    for r, w in enumerate(words):
        assert len(w) <= cols, w
        for i, ch in enumerate(w):
            names[r * cols + i] = ord(ch)
    return names


def text_tables():
    """text mode: 40 x 24 names at $0000, the BIOS's characters at $0800 and
    the disc's cells from character 128"""
    cells = cell_rows(6, TEXT_X0, 40, lambda y, ink: BLACK)
    shapes = sorted({p for p, _ in cells.values()})
    code = {p: 128 + i for i, p in enumerate(shapes)}
    assert len(shapes) <= 128
    names = label_names(MODES["text"]["words"], 40)
    for (col, row), (p, _) in cells.items():
        names[row * 40 + col] = code[p]
    pats = [b for p in shapes for b in p]
    return [(0x0000, names), (0x0800 + 128 * 8, pats)], {"shapes": len(shapes), "cells": len(cells)}


def graphic1_tables():
    """Graphic I: a cell takes one ink for its eight lines, and a pattern
    shares its colour with the seven others of its group: the disc's cells
    above the line SPLIT runs through take dark blue, as do the cells it
    cuts; the rest light green"""
    cells = cell_rows(8, 0, 32, lambda y, ink: ink)
    top = sorted({p for (col, row), (p, _) in cells.items() if 8 * row < SPLIT})
    bottom = sorted({p for (col, row), (p, _) in cells.items() if 8 * row >= SPLIT})
    first_bottom = 128 + 8 * ((len(top) + 7) // 8)
    assert first_bottom + len(bottom) <= 256
    names = label_names(MODES["graphic1"]["words"], 32)
    for (col, row), (p, _) in cells.items():
        names[row * 32 + col] = (128 + top.index(p) if 8 * row < SPLIT
                                 else first_bottom + bottom.index(p))
    colours = [0x10 | WHITE] * 32
    for g in range(16, first_bottom // 8):
        colours[g] = DARK_BLUE << 4 | WHITE
    for g in range(first_bottom // 8, (first_bottom + len(bottom) + 7) // 8):
        colours[g] = LIGHT_GREEN << 4 | WHITE
    pats = [b for p in top for b in p] + [0] * (8 * (first_bottom - 128 - len(top))) + \
        [b for p in bottom for b in p]
    return ([(0x1800, names), (0x2000, colours), (0x0000 + 128 * 8, pats)],
            {"shapes": len(top) + len(bottom), "cells": len(cells),
             "groups": (first_bottom + len(bottom) + 7) // 8 - 16})


def graphic2_tables():
    """Graphic II: names 0 to 255 in each third, so that every cell has its
    own pattern and its own colours, eight bytes each; the label's patterns
    come from the BIOS at run time (glyphs)"""
    cells = cell_rows(8, 0, 32, lambda y, ink: (ink if ink else BLACK) << 4 | WHITE)
    blocks = []
    for row in range(24):
        run = sorted(col for (col, r) in cells if r == row)
        if not run:
            continue
        lo, hi = run[0], run[-1]
        assert run == list(range(lo, hi + 1))
        at = (row // 8) * 2048 + (row % 8) * 256 + lo * 8
        pats, cols = [], []
        for col in range(lo, hi + 1):
            p, inks = cells[col, row]
            pats += p
            cols += inks
        blocks += [(0x0000 + at, pats), (0x2000 + at, cols)]
    glyphs = [((r // 8) * 2048 + (r % 8) * 256 + 8 * i, ord(ch))
              for r, w in enumerate(MODES["graphic2"]["words"]) for i, ch in enumerate(w)
              if ch != " "]
    return blocks, glyphs, {"cells": len(cells)}


def multi_tables():
    """multicolour: the BIOS's names, 32 x 24 at $0800, row r showing names
    32 x (r / 4) to that + 31; each block of 4 x 4 the colour at its middle"""
    names = [32 * (row // 4) + col for row in range(24) for col in range(32)]
    pats = [0] * (192 * 8)
    for by in range(48):
        for bx in range(64):
            x, y = 4 * bx + 2, 4 * by + 2
            c = (DARK_BLUE if y < SPLIT else LIGHT_GREEN) if inside(x, y) else WHITE
            row, col = by // 2, bx // 2
            at = (32 * (row // 4) + col) * 8 + 2 * (row % 4) + by % 2
            pats[at] |= c << 4 if bx % 2 == 0 else c
    return [(0x0800, names), (0x0000, pats)], {"blocks": 64 * 48}


def blocks_db(blocks):
    out = ""
    for addr, data in blocks:
        out += f"        dw ${addr:04X}, {len(data)}\n"
        for i in range(0, len(data), 12):
            out += "        db " + ", ".join(f"${b:02X}" for b in data[i:i + 12]) + "\n"
    return out + "        dw 0, 0                 ; the end\n"


WRITE_BLOCKS = """
; write_blocks: HL = a list of blocks, each the VRAM address (2 bytes) and the
; number of bytes (2 bytes, 0 ends the list), then the bytes. Display off.
write_blocks:
        ld e, (hl)
        inc hl
        ld d, (hl)
        inc hl
        ld c, (hl)
        inc hl
        ld b, (hl)
        inc hl
        ld a, b
        or c
        ret z
        ld a, e
        out (VDP_CTRL), a
        ld a, d
        or $40
        out (VDP_CTRL), a
.byte:  ld a, (hl)
        out (VDP_DATA), a
        inc hl
        dec bc
        ld a, b
        or c
        jr nz, .byte
        jr write_blocks
"""

GLYPHS = """
; glyphs: HL = a count, then for each character the VRAM address of its eight
; pattern bytes (2 bytes) and its code (1 byte): its shape from the BIOS's set.
glyphs: ld b, (hl)
        inc hl
.next:  push bc
        ld e, (hl)
        inc hl
        ld d, (hl)
        inc hl
        ld a, e
        out (VDP_CTRL), a
        ld a, d
        or $40
        out (VDP_CTRL), a
        ld a, (hl)              ; the code: its shape is at CGTABL + 8 x code
        inc hl
        push hl
        ld l, a
        ld h, 0
        add hl, hl
        add hl, hl
        add hl, hl
        ld de, (CGTABL)
        add hl, de
        ld b, 8
.byte:  ld a, (hl)
        out (VDP_DATA), a
        inc hl
        djnz .byte
        pop hl
        pop bc
        djnz .next
        ret
"""


def head(name, what):
    return HEAD.format(name=name, chapter=21, what=what) + BIOS


def regs_code(name):
    r, notes = MODES[name]["regs"], REG_NOTE[name]
    out = ""
    for n in (1, 0, 2, 3, 4, 5, 6, 7):
        v = r[n] & DISPLAY_OFF if n == 1 else r[n]
        note = notes[n] + (", display off" if n == 1 else "")
        out += f"        VDP_REG {n}, ${v:02X}          ; {note}\n"
    return out


NOISE = """        VRAM_WRITE $0000        ; every byte of the VRAM: noise, the
        ld hl, $0000            ; BIOS's first 16 KB
        ld c, VDP_DATA
        ld d, 64                ; 64 x 256 bytes
noise:  ld b, 0
        otir
        dec d
        jr nz, noise
"""


def font_to(addr):
    return f"""        VRAM_WRITE ${addr:04X}        ; the BIOS's 256 characters, 2,048 bytes
        ld hl, (CGTABL)
        ld c, VDP_DATA
        ld d, 8
font:   ld b, 0
        otir
        dec d
        jr nz, font
"""


def fill(addr, n, value, tag):
    return f"""        VRAM_WRITE ${addr:04X}        ; {n} bytes of ${value:02X}
        ld bc, {n}
{tag + ':':<8}ld a, ${value:02X}
        out (VDP_DATA), a
        dec bc
        ld a, b
        or c
        jr nz, {tag}
"""


NO_SPRITES = """        VRAM_WRITE $1B00        ; the sprite attribute table ends at once
        ld a, $D0
        out (VDP_DATA), a
"""


def mode_program(name):
    r = MODES[name]["regs"]
    what = {"text": "the picture in text mode", "graphic1": "the picture in Graphic I",
            "graphic2": "the picture in Graphic II", "multi": "the picture in multicolour"}[name]
    body = ""
    data = ""
    if name == "text":
        blocks, info = text_tables()
        body = font_to(0x0800)
    elif name == "graphic1":
        blocks, info = graphic1_tables()
        body = font_to(0x0000) + NO_SPRITES
    elif name == "graphic2":
        blocks, glyph_list, info = graphic2_tables()
        body = (fill(0x0000, 6144, 0x00, "pat") + fill(0x2000, 6144, 0x10 | WHITE, "col") +
                """        VRAM_WRITE $1800        ; names: 0 to 255 in each third
        ld b, 3
nam:    xor a
nam1:   out (VDP_DATA), a
        inc a
        jr nz, nam1
        djnz nam
        ld hl, label            ; the words: the BIOS's shapes in their cells
        call glyphs
""" + NO_SPRITES)
        data = "label:  db " + str(len(glyph_list)) + "\n" + "".join(
            f"        dw ${a:04X}\n        db {c}\n" for a, c in glyph_list)
    else:
        blocks, info = multi_tables()
        body = NO_SPRITES
    return head(name, what) + f"""; The picture of figure 21.1 in this mode. The registers first, with the
; display off; then the whole VRAM filled with noise; then the mode's tables,
; and nothing else; then the display on.
init:   di
        ld sp, SYS_AREA
""" + regs_code(name) + NOISE + body + """        ld hl, blocks           ; the tables gen21.py worked out
        call write_blocks
""" + f"""shown:  VDP_REG 1, ${r[1]:02X}          ; the display on
done:   jr done
""" + WRITE_BLOCKS + (GLYPHS if name == "graphic2" else "") + data + "blocks:\n" + \
        blocks_db(blocks) + CART_END


# ------------------------------------------------------------------ keep.asm
def keep():
    writes = "".join(f"        VDP_REG {n}, $FF\n" for n in range(8))
    return head("keep", "the bits each register keeps") + """; $FF written to each of the eight registers, the interrupts off; the debugger
; reads them back at 'kept'. Then 0 to each, read at 'zero'.
init:   di
        ld sp, SYS_AREA
""" + writes + """kept:   nop
""" + "".join(f"        VDP_REG {n}, $00\n" for n in range(8)) + """zero:   nop
done:   jr done
""" + CART_END


# ------------------------------------------------------------------ bios.asm
BIOS_CALLS = ["INITXT", "INIT32", "INIGRP", "INIMLT"]


def bios():
    calls = "".join(f"""c{i}:     call {c}
        di                      ; the BIOS leaves the interrupts on (chapter 16)
r{i}:     nop                     ; the debugger reads the registers here
""" for i, c in enumerate(BIOS_CALLS))
    modes = "".join(f"""        ld a, {i}
g{i}:     call CHGMOD             ; screen mode {i}
        di
m{i}:     nop                     ; the registers again
""" for i in range(4))
    return head("bios", "the BIOS's four screen modes") + """; INITXT, INIT32, INIGRP and INIMLT in turn. At r0 to r3 the debugger reads
; the VDP's registers and the BIOS's table addresses (TXTNAM to MLTPAT). Then
; CHGMOD with A = 0 to 3, read at m0 to m3.
init:   di
        ld sp, SYS_AREA
""" + calls + modes + """done:   jr done
""" + CART_END


FRAMES = """
; frames: wait for B frame flags, the interrupts off (chapter 19's status)
frames: in a, (VDP_CTRL)        ; bit 7, F: a frame has ended
        rla
        jr nc, frames
        djnz frames
        ret
"""


# ------------------------------------------------------------------ bits.asm
BITS_STATES = [     # (R#1, R#7, what): one every BITS_FRAMES frames
    (0xC0, 0x1F, "Graphic I, as the page was drawn"),
    (0xD0, 0x1F, "M1: text mode"),
    (0xC8, 0x1F, "M2: multicolour"),
    (0xD8, 0x1F, "M1 and M2"),
    (0xD0, 0x0F, "M1, and R#7 as TEXT_PAGE left it"),
]
BITS_FRAMES = 8
BITS_ROWS = ["{:02d} THE VDP READS WHAT R#1 SAYS".format(r) for r in range(2, 24)]


def bits():
    page = ""
    texts = ""
    words = [(0, "A GRAPHIC I PAGE: ONLY R#1 MOVES")] + [(r + 2, t[:32]) for r, t in
                                                         enumerate(BITS_ROWS)]
    for i, (row, t) in enumerate(words):
        assert len(t) <= 32, t
        page += f"        ld b, {row}\n        ld c, 0\n        ld hl, w{i}\n        call puts\n"
        texts += f'w{i}:     db "{t}", 0\n'
    states = ""
    for k, (r1, r7, what) in enumerate(BITS_STATES):
        states += f"""        call frames             ; {BITS_FRAMES} frames of the state before
s{k}:     VDP_REG 1, ${r1:02X}          ; {what}
        VDP_REG 7, ${r7:02X}
t{k}:
"""
    return head("bits", "a Graphic I page, and only R#1 changed") + f"""; WHERE IT BREAKS. A page drawn by TEXT_PAGE for Graphic I; then every
; {BITS_FRAMES} frames a new value of R#1 (and of R#7), nothing else: the VDP reads the
; same tables as the mode bits tell it to.
""" + TEXT_PAGE + page + """        VDP_REG 7, $1F          ; ink black, for text mode; backdrop white
        VDP_REG 1, $C0          ; the page on
""" + states + f"""done:   jr done

; frames: wait for {BITS_FRAMES} frame flags, the interrupts off (chapter 19's status)
frames: ld b, {BITS_FRAMES}
.wait:  in a, (VDP_CTRL)        ; bit 7, F: a frame has ended
        rla
        jr nc, .wait
        djnz .wait
        ret
""" + texts + library() + CART_END


# ------------------------------------------------------------------ chars.asm
CHARS_FRAMES = 10


def chars():
    return head("chars", "the BIOS's 256 characters in Graphic I and in text mode") + f"""; The BIOS's 256 shapes, names 0 to 255 from $1800: in Graphic I, 32 to a
; line; then, from the same tables, in text mode, 40 to a line. The sprite
; attribute table moves to $3F80, out of the way of text mode's 960 names.
""" + TEXT_PAGE + """        VDP_REG 5, $7F          ; sprite attributes $3F80
        VRAM_WRITE $3F80        ; and no sprites there
        ld a, $D0
        out (VDP_DATA), a
        VRAM_WRITE $1800        ; names 0 to 255
        xor a
nm:     out (VDP_DATA), a
        inc a
        jr nz, nm
        ld bc, 960 - 256        ; and spaces to the end of text mode's 960
sp:     ld a, ' '
        out (VDP_DATA), a
        dec bc
        ld a, b
        or c
        jr nz, sp
        VDP_REG 7, $1F          ; ink black for text mode, backdrop white
g1:     VDP_REG 1, $C0          ; Graphic I, the display on
        ld b, """ + str(CHARS_FRAMES) + """
        call frames
tx:     VDP_REG 1, $D0          ; text mode: the same names, the same shapes
done:   jr done
""" + FRAMES + library() + CART_END


# ------------------------------------------------------------------ bands.asm
BANDS = [0x14, 0x41, 0x3F, 0xF3, 0x11, 0x44, 0x1F, 0x4F]     # pattern 0's eight bytes


def bands():
    return head("bands", "every name 0, in multicolour") + """; Multicolour with every one of the 768 names 0: each row of the screen shows
; two of pattern 0's eight bytes, the two its row picks, counted in fours.
init:   di
        ld sp, SYS_AREA
""" + regs_code("multi") + """        VRAM_WRITE $0800        ; 768 names, all 0
        ld bc, 768
nm:     xor a
        out (VDP_DATA), a
        dec bc
        ld a, b
        or c
        jr nz, nm
        VRAM_WRITE $0000        ; pattern 0: four pairs of bytes
        ld hl, pattern
        ld b, 8
        ld c, VDP_DATA
        otir
""" + NO_SPRITES + f"""shown:  VDP_REG 1, $C8          ; the display on
done:   jr done
pattern:
        db {", ".join(f"${b:02X}" for b in BANDS)}
""" + CART_END


# ------------------------------------------------------------------ flip.asm
FLIP_FRAMES = 8
FLIP_B = ["THE SECOND PAGE, AT $1C00",
          "R#2 = 7: ONE REGISTER, TWO OUTS"]


def flip():
    page_b = "".join(f"        VRAM_WRITE ${0x1C00 + 32 * (2 * r):04X}\n        ld hl, b{r}\n"
                     "        call send\n" for r in range(len(FLIP_B)))
    texts = "".join(f'b{r}:     db "{t}", 0\n' for r, t in enumerate(FLIP_B))
    return head("flip", "two pages of names, and R#2 between them") + f"""; Two name tables: TEXT_PAGE's at $1800 (R#2 = 6) and a second at $1C00
; (R#2 = 7). Every {FLIP_FRAMES} frames R#2 changes, and the whole screen with it.
""" + TEXT_PAGE + """        ld b, 0
        ld c, 0
        ld hl, a0
        call puts
        ld b, 2
        ld c, 0
        ld hl, a1
        call puts
        VRAM_WRITE $1C00        ; the second page: 768 spaces
        ld bc, 768
sp:     ld a, ' '
        out (VDP_DATA), a
        dec bc
        ld a, b
        or c
        jr nz, sp
""" + page_b + """        VDP_REG 1, $C0          ; the first page on
        ld d, 2                 ; twice each way
turn:   ld b, """ + str(FLIP_FRAMES) + """
        call frames
p7:     VDP_REG 2, $07          ; names at $1C00
        ld b, """ + str(FLIP_FRAMES) + """
        call frames
p6:     VDP_REG 2, $06          ; names at $1800
        dec d
        jr nz, turn
done:   jr done

; send: the text at HL, ending in 0, to the VRAM at the address set
send:   ld a, (hl)
        or a
        ret z
        out (VDP_DATA), a
        inc hl
        jr send
""" + FRAMES + 'a0:     db "THE FIRST PAGE, AT $1800", 0\na1:     db "R#2 = 6", 0\n' + texts + \
        library() + CART_END


# ------------------------------------------------------------------ switch.asm
SWITCH_WORDS = ["A PAGE MOVED TO TEXT MODE:", "THE NAMES COPIED FOUR COLUMNS IN",
                "THE SHAPES TO $0800, R#7 AN INK,", "AND R#1 WRITTEN WHOLE."]


def switch():
    page = "".join(f"        ld b, {2 * r}\n        ld c, 0\n        ld hl, w{r}\n        call puts\n"
                   for r in range(len(SWITCH_WORDS)))
    texts = "".join(f'w{r}:     db "{t}", 0\n' for r, t in enumerate(SWITCH_WORDS))
    assert all(len(t) <= 32 for t in SWITCH_WORDS)
    return head("switch", "a Graphic I page moved into text mode") + """; The fix for bits.asm: a Graphic I page, shown; then, with the display off,
; text mode's tables written from it, R#7 given an ink, and all of R#1.
buf     EQU VARS + $20          ; a row of names on its way
""" + TEXT_PAGE + page + """        VDP_REG 1, $C0          ; the Graphic I page on
        ld b, 8
        call frames
sw:     VDP_REG 1, $90          ; 16 KB, M1: text mode, the display off
""" + font_to(0x0800) + """clr:    VRAM_WRITE $0000        ; text mode's 960 names: spaces
        ld bc, 960
sp:     ld a, ' '
        out (VDP_DATA), a
        dec bc
        ld a, b
        or c
        jr nz, sp
names:  ld hl, $1800            ; the page's names, a row at a time,
        ld de, $0004            ; to text mode's, four columns in
        ld b, 24
row:    push bc
        ld a, l                 ; HL: an address to read (bit 6 at 0)
        out (VDP_CTRL), a
        ld a, h
        out (VDP_CTRL), a
        push hl
        ld hl, buf
        ld bc, 32 * 256 + VDP_DATA
        inir                    ; the display off: as fast as it goes
        ld a, e                 ; DE: an address to write
        out (VDP_CTRL), a
        ld a, d
        or $40
        out (VDP_CTRL), a
        ld hl, buf
        ld b, 32
        otir
        pop hl
        ld bc, 32
        add hl, bc              ; the next row of 32
        ex de, hl
        ld bc, 40
        add hl, bc              ; the next row of 40
        ex de, hl
        pop bc
        djnz row
regs:   VDP_REG 2, $00          ; names    $0000
        VDP_REG 4, $01          ; patterns $0800
        VDP_REG 7, $1F          ; ink black, backdrop white
on:     VDP_REG 1, $D0          ; text mode, the display on
done:   jr done
""" + FRAMES + texts + library() + CART_END


PROGRAMS = {"text": lambda: mode_program("text"), "graphic1": lambda: mode_program("graphic1"),
            "graphic2": lambda: mode_program("graphic2"), "multi": lambda: mode_program("multi"),
            "keep": keep, "bios": bios, "chars": chars, "bands": bands, "flip": flip,
            "bits": bits, "switch": switch}


def main():
    for name, make in PROGRAMS.items():
        with open(os.path.join(HERE, f"{name}.asm"), "w") as f:
            f.write(make())
    print(" ".join(f"{n}.asm" for n in PROGRAMS))


if __name__ == "__main__":
    main()
