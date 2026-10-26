#!/usr/bin/env python3
"""gen25.py - the programs of chapter 25: plotting and drawing in Graphic II.

    python3 gen25.py && ./build.sh

    over.asm       a line of the paper drawn with chapter 22's pixel, which
                   writes a byte without reading it, and one drawn with plot,
                   which reads the byte, sets the pixel and writes it back
                   (figure 25.1)
    cost.asm       line, rline and tline on seven lines, each call timed
    fan.asm        88 lines from the middle of the paper with line: every
                   pixel read, changed and written through the ports
                   (figure 25.2)
    tight.asm      fan.asm without the NOP that keeps 29 T-states between the
                   read address and the IN
    buffer.asm     the same lines drawn with rline into 6,144 bytes of the
                   RAM laid out as the patterns, then sent to the VRAM
    through.asm    the same lines drawn with tline: each byte changed in the
                   RAM and written to the VRAM, never read from it
    hidden.asm     WHERE IT BREAKS: fan.asm's lines over blocks painted with
                   ink and paper of one colour (figure 25.4)
    shown.asm      the same blocks painted as paper under a black ink

Graphic II as a bitmap (chapter 22's GRAPHIC2: names 0 to 255 in each third,
black ink on white). Every program draws with the display on and the
interrupts off, ends with asmparts.CART_END, and build.sh assembles with
--syntax=bFw.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
from asmparts import HEAD, CART_END, GRAPHIC2  # noqa: E402

BIOS = '        INCLUDE "bios.inc"\n'
BLACK, LIGHT_GREEN, DARK_BLUE, WHITE = 1, 3, 4, 15
BUF = 0xC800                # rline's and tline's 6,144 bytes: the patterns' layout
BUF_H = BUF >> 8
OVER_Y = (44, 52)           # over.asm: the line drawn with pixel, and with plot
CENTRE = (128, 96)          # the fan's lines start here, (x, y)
FAN = ([(x, 8) for x in range(40, 216, 8)] + [(216, y) for y in range(8, 184, 8)]
       + [(x, 184) for x in range(216, 40, -8)] + [(40, y) for y in range(184, 8, -8)])
                            # and end on a square 176 pixels wide, every 8 pixels
COST_LINES = [(10, 60, 10, 60), (10, 64, 73, 64), (80, 40, 80, 103), (90, 40, 153, 103),
              (250, 40, 170, 70), (200, 120, 180, 60), (0, 0, 255, 191)]
                            # (x0, y0, x1, y1): a point, across, down, at 45
                            # degrees, flat and to the left, steep and upwards,
                            # and the paper's diagonal
SCENE = [(0, 9, 32, 6, DARK_BLUE), (4, 2, 6, 4, LIGHT_GREEN), (22, 18, 6, 4, LIGHT_GREEN)]
                            # hidden.asm's blocks: first column and row of
                            # cells, columns, rows, colour


def head(name, what):
    return HEAD.format(name=name, chapter=25, what=what) + BIOS


# ------------------------------------------------------------------ routines
VADDR = """
; vaddr: B = x, C = y -> HL = the address of the byte that holds pixel (x, y),
; in the patterns of a Graphic II screen whose names run 0 to 255 in each
; third (chapter 22). Uses A.
vaddr:  ld a, c                 ;  5
        rrca                    ;  5
        rrca                    ;  5
        rrca                    ;  5
        and $1F                 ;  8: y / 8, the row of characters
        ld h, a                 ;  5
        ld a, b                 ;  5
        and $F8                 ;  8: the column of characters, x 8
        ld l, a                 ;  5
        ld a, c                 ;  5
        and 7                   ;  8: the line in the cell
        or l                    ;  5
        ld l, a                 ;  5
        ret                     ; 11
"""

MASKS = """
        ALIGN 256
masks:  db $80, $40, $20, $10, $08, $04, $02, $01   ; pixel n of a byte: bit 7 - n
"""

PIXEL = """
; pixel: B = x, C = y: the byte of pixel (x, y) written with that pixel
; alone (chapter 22's diag). Uses A, DE, HL.
pixel:  call vaddr              ; 18  HL: the byte
        ld a, l                 ;  5
        out (VDP_CTRL), a       ; 12  the write address
        ld a, h                 ;  5
        or $40                  ;  8
        out (VDP_CTRL), a       ; 12
        ld d, high masks        ;  8
        ld a, b                 ;  5
        and 7                   ;  8
        ld e, a                 ;  5
        ld a, (de)              ;  8  $80 >> (x AND 7)
        out (VDP_DATA), a       ; 12  the byte: the pixel, and seven paper
        ret                     ; 11
"""

PLOT = """
; plot: B = x, C = y: pixel (x, y) set, the other seven of its byte kept:
; the byte read, changed and written back. Uses A, DE, HL.
plot:   call vaddr              ; 18  HL: the byte
        ld a, l                 ;  5
        out (VDP_CTRL), a       ; 12  the read address
        ld a, h                 ;  5
        out (VDP_CTRL), a       ; 12  ... and the VDP reads the byte ahead
        ld d, high masks        ;  8  while it reads, the pixel's mask
        ld a, b                 ;  5
        and 7                   ;  8
        ld e, a                 ;  5
        ld a, (de)              ;  8
        ld e, a                 ;  5  E: $80 >> (x AND 7)
        in a, (VDP_DATA)        ; 12  the byte
        or e                    ;  5  and the pixel
        ld e, a                 ;  5
        ld a, l                 ;  5
        out (VDP_CTRL), a       ; 12  the write address
        ld a, h                 ;  5
        or $40                  ;  8
        out (VDP_CTRL), a       ; 12
        ld a, e                 ;  5
        out (VDP_DATA), a       ; 12  the byte, with the pixel
        ret                     ; 11
"""

# the pixel of a line: HL its byte, C its mask; the error's step (A' less
# the shorter way, the carry kept in F') goes inside it
SET = {
    "port": """{b}px:   ld a, l                 ;  5
        out (VDP_CTRL), a       ; 12  the read address
        ld a, h                 ;  5
        out (VDP_CTRL), a       ; 12  ... and the VDP reads the byte ahead
        ex af, af'              ;  5  while it reads, the error,
        sub {minor}                   ;  5  less {mname}: carry, below zero,
        ex af, af'              ;  5  kept with its carry
{nop}        in a, (VDP_DATA)        ; 12  the byte
        or c                    ;  5  and the pixel
        push af                 ; 12
        ld a, l                 ;  5
        out (VDP_CTRL), a       ; 12  the write address
        ld a, h                 ;  5
        or $40                  ;  8
        out (VDP_CTRL), a       ; 12
        pop af                  ; 11
        out (VDP_DATA), a       ; 12  the byte, with the pixel
""",
    "ram": """{b}px:   ex af, af'              ;  5  the error,
        sub {minor}                   ;  5  less {mname}: carry, below zero,
        ex af, af'              ;  5  kept with its carry
        ld a, c                 ;  5  the pixel
        or (hl)                 ;  8  into its byte
        ld (hl), a              ;  8
""",
    "through": """{b}px:   ex af, af'              ;  5  the error,
        sub {minor}                   ;  5  less {mname}: carry, below zero,
        ex af, af'              ;  5  kept with its carry
        ld a, c                 ;  5  the pixel
        or (hl)                 ;  8  into its byte, in the RAM
        ld (hl), a              ;  8
        ld a, l                 ;  5  and the byte to the VRAM:
        out (VDP_CTRL), a       ; 12  the write address
        ld a, h                 ;  5
        sub BUF_H - $40         ;  8  ... the RAM's page less BUF's, and $40
        out (VDP_CTRL), a       ; 12
        ld a, (hl)              ;  8
        out (VDP_DATA), a       ; 12
"""}
NOP = "        nop                     ;  5  29 T-states from the address to the IN\n"

ACROSS = {"r": ("rrc c", "add a, 8", "right", "on"), "l": ("rlc c", "sub 8", "left", "back")}
DOWN_IN_LINE = """        inc l                   ;  5  {say} (chapter 22's down)
        ld a, l                 ;  5
        and 7                   ;  8
        jr nz, {to}            ; 13, or 8
        ld a, l                 ;  5
        sub 8                   ;  8
        ld l, a                 ;  5
        inc h                   ;  5
"""


def across(d, to, say):
    rot, step, way, on = ACROSS[d]
    return f"""        {rot}                   ; 10  {say} {way}:
        jr nc, {to}            ; 13, or 8  in the same byte, or
        ld a, l                 ;  5  in the next, 8 {on}
        {step}{' ' * (16 - len(step))};  8
        ld l, a                 ;  5
"""


def loop(kind, p, shape, d, nop=True):
    """one of a line routine's four loops: SHAPE f (flat) or s (steep), D r or
    l, KIND port, ram or through, its labels from P"""
    b = f"{p}{shape}{d}"
    flat = shape == "f"
    minor, mname, major, Mname = ("e", "dy", "d", "dx") if flat else ("d", "dx", "e", "dy")
    out = SET[kind].format(b=b, minor=minor, mname=mname,
                           nop=NOP if (kind == "port" and nop) else "")
    first = (across(d, f"{b}sm", "a pixel") if flat else
             DOWN_IN_LINE.format(say="a line down", to=f"{b}sm"))
    then = (DOWN_IN_LINE.format(say="and a line down", to=f"{b}nx") if flat else
            across(d, f"{b}nx", "and a pixel"))
    return out + first + f"""{b}sm:   ex af, af'              ;  5  the error, and its carry
        jr c, {b}dn            ; 13, or 8
        ex af, af'              ;  5
        djnz {b}px             ; 14, or 9
        ret                     ; 11
{b}dn:   add a, {major}               ;  5  below zero: {Mname} back,
        ex af, af'              ;  5
""" + then + f"""{b}nx:   djnz {b}px             ; 14, or 9
        ret                     ; 11
"""


def setup(p, d, shape):
    """the start of one of the four loops: B the pixels, A' the error"""
    b = f"{p}{shape}{d}"
    if shape == "f":
        return f"""{b}:    ld b, d                 ;  5  flat: dx + 1 pixels
        inc b                   ;  5
        srl a                   ; 10  the error: dx / 2
        ex af, af'              ;  5
"""
    return f"""{b}:    ld b, e                 ;  5  steep: dy + 1 pixels
        inc b                   ;  5
        ld a, e                 ;  5
        srl a                   ; 10  the error: dy / 2
        ex af, af'              ;  5
"""


def first(kind, p):
    ram = "" if kind == "port" else """        ld a, h                 ;  5  in the buffer
        add a, BUF_H            ;  8
        ld h, a                 ;  5
"""
    return f"""
; {p}first: B = x, C = y -> HL: the byte of pixel (x, y), C: its mask
{p}first: call vaddr             ; 18
""" + ram + """        ld a, b                 ;  5
        and 7                   ;  8
        ld c, a                 ;  5
        ld b, high masks        ;  8
        ld a, (bc)              ;  8
        ld c, a                 ;  5
        ret                     ; 11
"""


SAY = {"port": "every pixel's byte read from the VRAM, changed and written back",
       "ram": "every pixel set in the buffer, BUF, which is laid out as the patterns",
       "through": "every pixel set in the buffer, and its byte written to the VRAM"}


def line_routine(kind, nop=True):
    p = {"port": "", "ram": "r", "through": "t"}[kind]
    name = f"{p}line"
    return f"""
; {name}: B = x0, C = y0, D = x1, E = y1: the line from (x0, y0) to (x1, y1),
;        {SAY[kind]},
;        from its top end down. Uses A, AF', BC, DE, HL.
{name}: ld a, e                 ;  5
        cp c                    ;  5  y1 against y0
        jr nc, {p}top           ; 13, or 8
        ld a, b                 ;  5  (x1, y1) is above: the ends change places
        ld b, d                 ;  5
        ld d, a                 ;  5
        ld a, c                 ;  5
        ld c, e                 ;  5
        ld e, a                 ;  5
{p}top: ld a, e                 ;  5
        sub c                   ;  5
        ld e, a                 ;  5  E: dy
        ld a, d                 ;  5
        sub b                   ;  5  x1 - x0
        jp c, {p}left           ; 11  to the left
        ld d, a                 ;  5  D: dx
        call {p}first           ; 18  HL: the byte of (x0, y0), C: its mask
        ld a, d                 ;  5
        cp e                    ;  5
        jp c, {p}sr             ; 11  steeper than 45 degrees
""" + setup(p, "r", "f") + loop(kind, p, "f", "r", nop) + \
        setup(p, "r", "s") + loop(kind, p, "s", "r", nop) + f"""{p}left: neg                     ; 10  to the left: dx = x0 - x1
        ld d, a                 ;  5  D: dx
        call {p}first           ; 18
        ld a, d                 ;  5
        cp e                    ;  5
        jp c, {p}sl             ; 11
""" + setup(p, "l", "f") + loop(kind, p, "f", "l", nop) + \
        setup(p, "l", "s") + loop(kind, p, "s", "l", nop) + first(kind, p)


CLEAR = """
; clear: the 6,144 bytes of the buffer set to 0
clear:  ld hl, BUF              ; 11
        ld de, BUF + 1          ; 11
        ld bc, 6143             ; 11
        ld (hl), 0              ; 11
        ldir                    ; 23 a byte, 18 the last
        ret                     ; 11
"""

SEND = """
; send: the buffer to the patterns, 29 T-states a byte (chapter 20)
send:   VRAM_WRITE $0000        ; 34  the patterns
        ld hl, BUF              ; 11
        ld c, VDP_DATA          ;  8
        ld d, 24                ;  8  24 x 256 bytes
sendp:  ld b, 0                 ;  8
sendb:  outi                    ; 18
        jp nz, sendb            ; 11
        dec d                   ;  5
        jr nz, sendp            ; 13, or 8
        ret                     ; 11
"""

PAINT = """
; paint: B = the first column of cells, C = the first row, D = the columns,
;        E = the rows, A = a colour byte: the colours of a block of whole
;        cells. The display is off.
paint:  ld h, a                 ; H: the colour byte
prow:   push bc
        push de
pcell:  ld a, b                 ; the cell's eight colour bytes: column x 8,
        add a, a
        add a, a
        add a, a
        out (VDP_CTRL), a
        ld a, c                 ; and the row, of the colours ($2000)
        or $60
        out (VDP_CTRL), a
        ld a, h
        ld l, 8
pbyte:  out (VDP_DATA), a
        dec l
        jr nz, pbyte
        inc b
        dec d
        jr nz, pcell
        pop de
        pop bc
        inc c
        dec e
        jr nz, prow
        ret
"""

ON = """        VDP_REG 1, $C0          ; the display on: what follows is drawn on it
"""
DONE = "done:   jr done\n"
EQUS = f"""BUF     EQU ${BUF:04X}               ; 6,144 bytes, laid out as the patterns
BUF_H   EQU ${BUF_H:02X}
togo    EQU VARS                ; the fan's lines left to draw
"""


def fan_loop(routine, ends=FAN, first_pt=CENTRE):
    x, y = first_pt
    return f"""go:     ld hl, ends             ; the far end of each line: x, then y
        ld a, {len(ends)}
        ld (togo), a
next:   push hl
        ld b, {x}                ; x0
        ld c, {y}                 ; y0
        ld d, (hl)              ; x1
        inc hl
        ld e, (hl)              ; y1
l0:     call {routine}
l1:     pop hl
        inc hl
        inc hl
        ld a, (togo)
        dec a
        ld (togo), a
        jr nz, next
"""


def ends_data(ends=FAN):
    return "ends:\n" + "".join(f"        db {ex}, {ey}\n" for ex, ey in ends)


LINE_RE = re.compile(r"^([\w.]+:)?(\s+)(\S.*?)\s*(;.*)?$")


def tidy(text):
    """every instruction at column 8 and its comment at column 32, as in the
    rest of the book"""
    out = []
    for line in text.splitlines():
        m = LINE_RE.match(line)
        if not m or not line.strip() or line.lstrip().startswith(";"):
            out.append(line)
            continue
        label, _, code, comment = m.groups()
        lab = (label or "").ljust(8) if len(label or "") < 8 else label + " "
        row = lab + code
        if comment:
            row = row.ljust(31) + " " + comment
        out.append(row)
    return "\n".join(out) + "\n"


def program(name, what, say, body, routines):
    return head(name, what) + say + EQUS + GRAPHIC2 + tidy(body + DONE + "".join(routines))


# ------------------------------------------------------------------ programs
def over():
    y0, y1 = OVER_Y
    return program("over", "pixel and plot along a line", f"""; A line of the paper, y = {y0}, drawn left to right with chapter 22's pixel,
; which writes each pixel's byte without reading it; then y = {y1} with plot,
; which reads the byte, sets the pixel and writes the byte back.
""", ON + f"""go:     ld b, 0                 ; x
        ld c, {y0}                ; y
row0:
p0:     call pixel
p1:     inc b
        jr nz, row0
        ld c, {y1}
row1:
q0:     call plot
q1:     inc b
        jr nz, row1
""", [PIXEL, PLOT, VADDR, MASKS + CART_END])


def cost():
    body = ON + "go:     call clear\n"
    for tag, routine in (("a", "line"), ("c", "rline"), ("e", "tline")):
        after = chr(ord(tag) + 1)
        for k, (x0, y0, x1, y1) in enumerate(COST_LINES):
            body += f"""        ld b, {x0}
        ld c, {y0}
        ld d, {x1}
        ld e, {y1}
{tag}{k}:     call {routine}
{after}{k}:
"""
    return program("cost", "line, rline and tline, timed", """; Seven lines drawn with line, through the ports; with rline, in the
; buffer; and with tline, in the buffer and written to the VRAM. Each call
; is timed by meas25.py.
""", body, [line_routine("port"), line_routine("ram"), line_routine("through"),
            CLEAR, VADDR, MASKS + CART_END])


def fan(name="fan", nop=True):
    what = f"{len(FAN)} lines with line" if nop else "fan.asm without the NOP"
    say = (f"""; {len(FAN)} lines from the middle of the paper to every eighth pixel round a
; square 176 pixels wide, drawn with line: each pixel's byte read through the
; ports, changed and written back, with the display on.
""" if nop else """; fan.asm's lines, with line's IN 27 T-states after the read address,
; not 32: the NOP that keeps the 29 T-states taken out.
""")
    return program(name, what, say, ON + fan_loop("line"),
                   [line_routine("port", nop), VADDR, ends_data(), MASKS + CART_END])


def buffer():
    return program("buffer", "the lines in the RAM, then sent", """; fan.asm's lines drawn with rline into BUF, 6,144 bytes of the RAM laid out
; as the patterns: cleared first, and sent to the VRAM at the end.
""", ON + "c0:     call clear\nc1:\n" + fan_loop("rline") + "s0:     call send\ns1:\n",
        [line_routine("ram"), CLEAR, SEND, VADDR, ends_data(), MASKS + CART_END])


def through():
    return program("through", "the lines in the RAM and the VRAM", """; fan.asm's lines drawn with tline: each pixel set in BUF, a copy of the
; patterns, and its byte written to the VRAM; nothing is read from the VRAM.
""", ON + "c0:     call clear\nc1:\n" + fan_loop("tline"),
        [line_routine("through"), CLEAR, VADDR, ends_data(), MASKS + CART_END])


def colour_byte(colour, painted):
    """a block's colour byte: ink and paper of its colour (hidden.asm), or a
    black ink on it (shown.asm)"""
    return colour << 4 | colour if not painted else BLACK << 4 | colour


def scene(name, painted):
    blocks = ""
    for c, r, w, h, colour in SCENE:
        blocks += f"""        ld b, {c}
        ld c, {r}
        ld d, {w}
        ld e, {h}
        ld a, ${colour_byte(colour, painted):02X}
        call paint
"""
    what = "blocks of one colour, and the fan" if not painted else "the blocks as paper"
    say = ("""; WHERE IT BREAKS. Three blocks painted with the colour bytes alone, ink and
; paper of the same colour, as chapter 23 painted its plain areas; then
; fan.asm's lines drawn over them with line.
""" if not painted else """; hidden.asm's blocks painted as paper, under a black ink: the same picture
; before the lines, and fan.asm's lines over it.
""")
    return program(name, what, say, blocks + ON + fan_loop("line"),
                   [line_routine("port"), PAINT, VADDR, ends_data(), MASKS + CART_END])


PROGRAMS = {"over": over, "cost": cost, "fan": fan, "tight": lambda: fan("tight", nop=False),
            "buffer": buffer, "through": through,
            "hidden": lambda: scene("hidden", False), "shown": lambda: scene("shown", True)}


# ------------------------------------------------------------------ the model
def bresenham(x0, y0, x1, y1):
    """the pixels line chooses, in the order it sets them: the top end
    first; along the longer way a pixel each time, and along the shorter
    one when the error, which starts at half the longer way and loses the
    shorter way each time, goes below zero and gets the longer way back"""
    if y1 < y0:
        x0, y0, x1, y1 = x1, y1, x0, y0
    dx, dy, sx = abs(x1 - x0), y1 - y0, (1 if x1 >= x0 else -1)
    flat = dx >= dy
    major, minor = (dx, dy) if flat else (dy, dx)
    err, x, y, out = major // 2, x0, y0, []
    for _ in range(major + 1):
        out.append((x, y))
        if flat:
            x += sx
        else:
            y += 1
        err -= minor
        if err < 0:
            err += major
            if flat:
                y += 1
            else:
                x += sx
    return out


def fan_pixels(ends=FAN, first_pt=CENTRE):
    return [p for e in ends for p in bresenham(*first_pt, *e)]


def scene_cells(painted):
    """{(column, row): colour byte} of hidden.asm's or shown.asm's blocks"""
    out = {}
    for c, r, w, h, colour in SCENE:
        for cc in range(c, c + w):
            for rr in range(r, r + h):
                out[(cc, rr)] = colour_byte(colour, painted)
    return out


def main():
    for name, make in PROGRAMS.items():
        with open(os.path.join(HERE, f"{name}.asm"), "w") as f:
            f.write(make())
    print(" ".join(f"{n}.asm" for n in PROGRAMS))


if __name__ == "__main__":
    main()
