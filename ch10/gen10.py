#!/usr/bin/env python3
"""gen10.py - the programs of chapter 10.

    python3 gen10.py && ./build.sh

    logic.asm      AND E, OR E and XOR E on all 65,536 pairs, and how many
                   times each value of F came out.
    sprite.asm     a shape drawn on a background four ways: OR, AND with a
                   mask and then OR, XOR, and XOR twice. Each panel is a
                   bitmap in the RAM, then sixteen character shapes in the
                   VDP (figure 10.1).
    bits.asm       BIT b,A for every bit and every value of A, from F = $00
                   and from F = $FF; and SET and RES on three values of A,
                   from both.
    cost.asm       one of each logic, bit, shift and rotate instruction,
                   timed by the debugger.
    rotate.asm     the twelve shifts and rotates, each on the same byte with
                   the carry clear and set, drawn bit by bit (figure 10.2).
    shifts.asm     the same twelve on every value of A, from F = $00 and
                   from F = $FF: A and F after each.
    mul.asm        eight bits times eight bits with shifts and adds: a few
                   products timed, and all 65,536 summed and mixed together.
    friction.asm   WHERE IT BREAKS: halving a speed with SRA, from 100 and
                   from -100, and mended.
    scroll.asm     words moved right a pixel at a time with RR through the
                   carry, 0 to 7 pixels, in a bitmap in the RAM (figure 10.3).
    mirror.asm     an arrow turned round by reversing the bits of each byte
                   (figure 10.4), and every byte reversed.
    div.asm        sixteen bits divided by eight with shifts and
                   subtractions: a few divisions timed, and 0 to 65,535
                   divided by 10.
    bcd.asm        a six-digit BCD score times ten with RLD, and divided by
                   ten with RRD.

The screen of the MSX is in the VDP's memory, where no instruction of this
chapter reaches: the pictures are made in the RAM, a bitmap a line at a
time, and sent to the VDP as character shapes by showblk (chapter 24 builds
screens this way). Results are kept in the RAM, from $C000 (chapter 8).
build.sh assembles with --syntax=bF (chapter 8).
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
from asmparts import (HEAD, TAIL, TEXT_PAGE, SHOW_PAGE, library, FATBITS, BOX_EMPTY,  # noqa: E402
                      BOX_FULL, SHOWBLK, BLKVARS)

RESULTS = "RESULTS EQU RAM_START          ; what the program found: the debugger reads it here\n"
TABLE = 0xD000              # the big tables
FIRST_CODE = 128            # the character codes the pictures use, 128 on


def head(name, what):
    return HEAD.format(name=name, chapter=10, what=what)


def cart(name, what, body, after="", results=True):
    """a cartridge that runs `body` with the interrupts off and stops"""
    return head(name, what) + (RESULTS if results else "") + f"""init:   di
        ld sp, SYS_AREA
{body}stop:   jr stop
{after}""" + TAIL


# --------------------------------------------------------------- logic.asm
LOGIC_OPS = ["and", "or", "xor"]


def logic():
    blocks = []
    for k, name in enumerate(LOGIC_OPS):
        pg = (TABLE >> 8) + 2 * k
        blocks.append(f"""; {name}: counters at ${pg:02X}00 (low bytes) and ${pg + 1:02X}00 (high bytes)
        ld d, 0                 ; D: the first number
{name + '1:':<8}ld e, 0                 ; E: the second
{name + '2:':<8}ld a, d
        {f'{name} e':<24}; the operation counted
        push af
        pop bc                  ; C = F
        {f'ld h, ${pg:02X}':<24}; the page of low bytes
        ld l, c                 ; the counter for this value of F
        inc (hl)
        jr nz, {name}3
        inc h
        inc (hl)                ; the carry into its high byte
{name + '3:':<8}inc e
        {f'jr nz, {name}2':<24}; all 256 values of E
        inc d
        {f'jr nz, {name}1':<24}; for all 256 values of D
""")
    return cart("logic", "AND, OR and XOR on every pair, counted by F", f"""COUNTS  EQU ${TABLE:04X}               ; in the RAM: 256 counters of two bytes for each operation
        ld hl, COUNTS
        ld de, COUNTS + 1
        ld (hl), 0
        ld bc, {2 * 256 * len(LOGIC_OPS)} - 1
        ldir                    ; every counter to 0
""" + "".join(blocks), results=False)


# -------------------------------------------------------------- sprite.asm
SIZE = 32                   # a panel is 32 x 32 pixels, 4 x 4 cells
RING = (9.5, 13.5)          # the shape: a ring, from this radius to this
PANELS = [  # (label, the passes that draw it, column, row)
    ("BACK", ["back"], 2, 2),
    ("SHAPE", ["shape"], 11, 2),
    ("OR", ["back", "or"], 20, 2),
    ("MASK", ["back", "mask"], 2, 11),
    ("XOR", ["back", "xor"], 11, 11),
    ("XOR XOR", ["back", "xor", "xor"], 20, 11),
]
PASSES = {  # the byte the pass puts in the panel, from HL (the panel) and IX
    "back": ["ld a, (ix+0)            ; the background"],
    "shape": ["ld a, (ix+1)            ; the shape alone"],
    "or": ["ld a, (hl)", "or (ix+1)               ; the shape's 1s added"],
    "mask": ["ld a, (hl)", "and (ix+2)              ; a hole where the shape goes ...",
             "or (ix+1)               ; ... and the shape in it"],
    "xor": ["ld a, (hl)", "xor (ix+1)              ; every pixel under a 1 turned over"],
}
PANEL_RAM = 0xC200          # six panels of 128 bytes
PANEL_BYTES = SIZE * SIZE // 8


def sprite_rows():
    """background, shape and mask: 32 rows of 32 bits each"""
    c = (SIZE - 1) / 2
    back, shape, mask = [], [], []
    for y in range(SIZE):
        b = s = m = 0
        for x in range(SIZE):
            bit = 1 << (SIZE - 1 - x)
            if (x + y) % 8 < 2:
                b |= bit                        # diagonal stripes
            r = math.hypot(x - c, y - c)
            if RING[0] <= r <= RING[1]:
                s |= bit                        # the ring
            if r > RING[1]:
                m |= bit                        # 1 outside the ring's disc
        back.append(b)
        shape.append(s)
        mask.append(m)
    return back, shape, mask


def sprite():
    back, shape, mask = sprite_rows()
    data = []
    for y in range(SIZE):
        for i in range(SIZE // 8):
            sh = 8 * (SIZE // 8 - 1 - i)
            data.append(f"%{(back[y] >> sh) & 255:08b}, %{(shape[y] >> sh) & 255:08b}, "
                        f"%{(mask[y] >> sh) & 255:08b}")
    routines = []
    for name, code in PASSES.items():
        t = "p" + name[0] + ("x" if name == "xor" else "")
        routines.append(f"""
; put{name}: one pass over the panel at HL, a byte at a time
put{name}:
        ld ix, data             ; three bytes for each byte of the panel
        ld b, {PANEL_BYTES}
{t + '1:':<8}{code[0]}
""" + "".join(f"        {c}\n" for c in code[1:]) + f"""        ld (hl), a
        inc hl                  ; the next byte of the panel
        inc ix
        inc ix
        inc ix                  ; the next three bytes of data
        djnz {t}1
        ret
""")
    calls = []
    for k, (label, passes, col, row) in enumerate(PANELS):
        for p in passes:
            calls.append(f"""        ld hl, PANELS + {PANEL_BYTES * k}
        call put{p}
""")
        calls.append(f"""        ld hl, PANELS + {PANEL_BYTES * k}
        ld de, ${SIZE // 8:02X}{SIZE // 8:02X}            ; 4 bytes across, 4 rows of cells
        ld a, {FIRST_CODE + 16 * k}
        ld b, {row}
        ld c, {col}
        call showblk            ; the panel, as 16 characters
        ld b, {row + SIZE // 8 + 1}
        ld c, {col}
        ld hl, t{k}
        call puts
""")
    texts = "".join(f'''t{k}:     db "{label}", 0
''' for k, (label, _, _, _) in enumerate(PANELS))
    return head("sprite", "a shape put on a background four ways") + RESULTS + f"""PANELS  EQU ${PANEL_RAM:04X}               ; six panels of 32 x 32 pixels, 128 bytes each
""" + BLKVARS + """; The data is three bytes for each byte of a panel: the background, the
; shape, and the mask, which has a 0 wherever the shape covers. Last, AND
; counts the bytes where the shape and the background touch.
""" + TEXT_PAGE + "".join(calls) + f"""        ld ix, data
        ld b, {PANEL_BYTES}               ; every byte of the panel
        ld c, 0                 ; C: the bytes where the two meet
hit:    ld a, (ix+0)
        and (ix+1)              ; background AND shape: 0 unless they share a 1
        jr z, miss
        inc c
miss:   inc ix
        inc ix
        inc ix
        djnz hit
        ld a, c
        ld (RESULTS), a
""" + SHOW_PAGE + "".join(routines) + SHOWBLK + texts + """
data:
""" + "".join(f"        db {d}\n" for d in data) + library() + TAIL


# ---------------------------------------------------------------- bits.asm
SETRES = 0xE000
SETRES_PAIRS = [(a, f) for a in (0x00, 0xFF, 0x5A) for f in (0x00, 0xFF)]


def bits():
    blocks = "".join(f"""; bit {b}: F after BIT {b},A, at TABLE+{512 * b}: all A from F = $00, then from F = $FF
        ld hl, TABLE + {512 * b}
        ld c, $00
bt{b}f:   ld b, 0
bt{b}a:   push bc
        pop af                  ; A = B, F = C
        bit {b}, a
        push af
        pop de
        ld (hl), e              ; F after
        inc hl
        inc b
        jr nz, bt{b}a
        ld a, c
        cpl                     ; $00, then $FF
        ld c, a
        or a
        jr nz, bt{b}f
""" for b in range(8))
    setres = "".join(f"""; {op} {b}: A and F after {op.upper()} {b},A, into SETRES
        ld ix, pairs
{f'{op}{b}:':<8}ld b, (ix+0)            ; A before
        ld c, (ix+1)            ; F before
        push bc
        pop af
        {op} {b}, a
        push af
        pop de
        ld (hl), d              ; A after
        inc hl
        ld (hl), e              ; F after
        inc hl
        inc ix
        inc ix
        ld a, (ix+0)
        cp $33                  ; the end of the pairs
        jr nz, {op}{b}
""" for b in range(8) for op in ("set", "res"))
    pairs = ", ".join(f"${a:02X}, ${f:02X}" for a, f in SETRES_PAIRS)
    return cart("bits", "BIT, SET and RES in every case", f"""TABLE   EQU ${TABLE:04X}               ; F after BIT, a byte a case
SETRES  EQU ${SETRES:04X}               ; A and F after SET and RES, two bytes a case
""" + blocks + """        ld hl, SETRES
""" + setres, after=f"pairs:  db {pairs}, $33\n", results=False)


# ---------------------------------------------------------------- cost.asm
COST = ["and b", "or $0f", "xor (hl)", "cpl", "scf", "ccf",
        "bit 3,a", "set 3,a", "bit 3,(hl)", "set 3,(hl)", "res 3,(ix+2)",
        "rlca", "rrca", "rla", "rra", "rlc a", "rrc a", "rl a", "rr a",
        "sla a", "sra a", "srl a", "sll a", "sra (hl)", "rld", "rrd"]


def cost():
    body = "".join(f"t{k}:{' ' * (5 if k < 10 else 4)}{i.replace(',', ', ')}\n"
                   for k, i in enumerate(COST)) + f"t{len(COST)}:\n"
    return cart("cost", "one of each logic, bit, shift and rotate instruction", """        ld hl, RESULTS          ; three bytes in the RAM, for the
        ld (hl), $5A            ; instructions that write
        ld ix, RESULTS
        ld (ix+2), $A5
""" + body)


# -------------------------------------------------------------- rotate.asm
ROTATES = ["rlca", "rrca", "rla", "rra", "rlc a", "rrc a", "rl a", "rr a",
           "sla a", "sra a", "srl a", "sll a"]
START = 0b10110010
ROT_ROWS = [0, 2, 3, 4, 5, 7, 8, 9, 10, 11, 12, 13, 14]   # start, then each
COL_C0, COL_C1 = 6, 18      # the byte from carry 0, and from carry 1


def shown(ins):
    """the instruction as the book writes it"""
    return ins.upper()


def rotate():
    rows = []
    for k, ins in enumerate(ROTATES):
        rows.append(f"""        ld b, {ROT_ROWS[k + 1]}
        ld c, 0
        ld hl, r{k}
        call puts
        ld c, {COL_C0}
        ld a, %{START:08b}
        or a                    ; the carry clear
        {ins:<24}; the instruction shown
        call show
        ld c, {COL_C1}
        ld a, %{START:08b}
        scf                     ; the carry set
        {ins}
        call show
""")
    texts = "".join(f'r{k}:     db "{shown(ins)}", 0\n' for k, ins in enumerate(ROTATES))
    return head("rotate", "the twelve shifts and rotates, bit by bit") + f"""; %{START:08b} put through each of the twelve shifts and rotates, once with
; the carry clear and once with it set: the byte bit by bit, and the carry
; after it (figure 10.2).
""" + TEXT_PAGE + f"""        ld b, {ROT_ROWS[0]}
        ld c, 0
        ld hl, r0s
        call puts
        ld c, {COL_C0}
        ld a, %{START:08b}
        or a                    ; the byte, and the carry clear
        call show
        ld c, {COL_C1}
        ld a, %{START:08b}
        scf                     ; the byte, and the carry set
        call show
""" + "".join(rows) + SHOW_PAGE + f"""
; show: A bit by bit at row B from column C, and the carry as one box after
;       a gap. Keeps B.
show:   push af
        call fatbits            ; the eight bits of A; C moves on by 8
        inc c                   ; a gap
        pop af
        ld a, {BOX_EMPTY}
        jr nc, sh1
        ld a, {BOX_FULL}
sh1:    jp putc                 ; the carry, as one box
""" + 'r0s:    db "START", 0\n' + texts + library(FATBITS) + TAIL


# -------------------------------------------------------------- shifts.asm
def shifts():
    blocks = "".join(f"""; {shown(ins)}: A and F after it, at TABLE+{1024 * k}: all A from F = $00, then from F = $FF
        ld hl, TABLE + {1024 * k}
        ld c, $00
{f'sh{k}f:':<8}ld b, 0
{f'sh{k}a:':<8}push bc
        pop af                  ; A = B, F = C
        {ins}
        push af
        pop de                  ; D = A after, E = F after
        ld (hl), d
        inc hl
        ld (hl), e
        inc hl
        inc b
        jr nz, sh{k}a
        ld a, c
        cpl                     ; $00, then $FF
        ld c, a
        or a
        jr nz, sh{k}f
""" for k, ins in enumerate(ROTATES))
    return cart("shifts", "the twelve on every value of A", f"""TABLE   EQU ${SHIFT_TABLE:04X}               ; 12 KB of the RAM: A and F, two bytes a case
""" + blocks, results=False)


SHIFT_TABLE = 0xC000


# ----------------------------------------------------------------- mul.asm
MUL_TIMED = [(0x00, 0xC8), (0x01, 0xC8), (0x55, 0xC8), (0xFF, 0xC8)]


def mul():
    timed = "".join(f"""        ld h, ${h:02X}
        ld e, ${e:02X}
m{k}:     call mul8               ; ${h:02X} x ${e:02X}
        {f'ld (prod+{2 * k}), hl':<24}
""" for k, (h, e) in enumerate(MUL_TIMED))
    return cart("mul", "eight bits times eight", """second  EQU RAM_START          ; the second number
total   EQU RAM_START + 1      ; 32 bits: the sum of all the products
check   EQU RAM_START + 5      ; 16 bits: the products mixed with XOR
prod    EQU RAM_START + 7      ; the timed products, two bytes each
        xor a
        ld hl, total
        ld b, 6
clr:    ld (hl), a
        inc hl
        djnz clr                ; total and check start at 0
""" + timed + """        ld c, 0                 ; C: the first number, 0 to 255
outer:  xor a
        ld (second), a
inner:  ld h, c
        ld a, (second)
        ld e, a
        call mul8               ; HL = C x the second number
        call tally
        ld a, (second)
        inc a
        ld (second), a
        jr nz, inner            ; all 256 second numbers
        inc c
        jr nz, outer            ; for all 256 first numbers
""", after="""
; mul8: HL = H x E, both taken as unsigned. Uses B and D.
mul8:   ld d, 0                 ; DE = E, sixteen bits wide
        ld l, d                 ; HL = H x 256: H is the multiplier
        ld b, 8
ml1:    add hl, hl              ; the result doubles, and the top bit
        jr nc, ml2              ; of the multiplier falls into the carry
        add hl, de              ; a 1: add E once more
ml2:    djnz ml1
        ret

; tally: the product in HL added into total (32 bits, low byte first) and
;        mixed into check (16 bits) with XOR
tally:  ex de, hl               ; DE = the product
        ld hl, (total)
        add hl, de
        ld (total), hl          ; the low sixteen bits
        jr nc, ty1
        ld hl, (total + 2)
        inc hl
        ld (total + 2), hl      ; and the carry into the high sixteen
ty1:    ld a, (check)
        xor e
        ld (check), a
        ld a, (check + 1)
        xor d
        ld (check + 1), a
        ret
""", results=False)


# ------------------------------------------------------------ friction.asm
FRICTION = (100, -100)
FRAMES = 10


def friction():
    return cart("friction", "WHERE IT BREAKS: a speed halved with SRA", f"""v1      EQU RAM_START          ; three speeds
v2      EQU RAM_START + 1
v3      EQU RAM_START + 2
list1   EQU RAM_START + $10    ; and the speeds after each halving
list2   EQU RAM_START + $20
list3   EQU RAM_START + $30
        ld a, {FRICTION[0]}
        ld (v1), a
        ld a, {FRICTION[1]}
        ld (v2), a
        ld (v3), a
        ld hl, list1
        ld de, list2
        ld ix, list3
        ld b, {FRAMES}
halve:  ld a, (v1)
        sra a                   ; half, keeping the sign
        ld (v1), a
        ld (hl), a
        inc hl
        ld a, (v2)
        sra a
        ld (v2), a
        ld (de), a
        inc de
        ld a, (v3)
        bit 7, a                ; negative?
        jr z, v3pos
        inc a                   ; then one nearer to 0 first
v3pos:  sra a
        ld (v3), a
        ld (ix+0), a
        inc ix
        djnz halve
""", results=False)


# -------------------------------------------------------------- scroll.asm
SCROLL_TEXT = "SCROLLING RIGHT"
SCROLL_ROW0, SCROLL_COL = 1, 2      # the first row, and where the bitmap starts
SCROLL_ROWS = 8                     # moved 0 to 7 pixels
SCROLL_W = 16                       # bytes across the bitmap
SCROLL_RAM = 0xC600                 # 8 rows x 8 lines x 16 bytes


def scroll():
    return head("scroll", "words moved right a pixel at a time") + f"""BITMAP  EQU ${SCROLL_RAM:04X}               ; 8 rows of 8 lines of {SCROLL_W} bytes
""" + BLKVARS + f"""; The same words on eight rows of a bitmap in the RAM, each row then moved
; right by one pixel more than the one above: 0 to 7 (figure 10.3). A line
; moves one pixel with RR on each of its {SCROLL_W} bytes, the carry taking the bit
; that falls off one byte into the next.
""" + TEXT_PAGE + f"""        ld hl, BITMAP
        ld de, BITMAP + 1
        ld (hl), 0
        ld bc, {8 * SCROLL_ROWS * SCROLL_W} - 1
        ldir                    ; the bitmap clear
        ld hl, BITMAP
t1:     call scroll1            ; timed by meas10.py: one line
t2:     ld hl, BITMAP           ; HL: the top line of the row
        ld b, 0                 ; B: the row, and how far it moves
row:    push bc
        push hl
        ld de, words
        call text               ; the words into the row's eight lines
        pop hl
        push hl
        ld a, b
        or a
        jr z, label             ; the first row stays
        ld d, 8                 ; D: the row's eight lines
line:   push bc
move:   push bc
        push hl
        call scroll1            ; one pixel right
        pop hl
        pop bc
        djnz move               ; B times
        pop bc
        ld a, l
        add a, {SCROLL_W}
        ld l, a                 ; the next line ({SCROLL_W} bytes on, in the same page)
        jr nc, nopage
        inc h
nopage: dec d
        jr nz, line
label:  pop hl
        pop bc
        push bc
        ld a, b
        add a, '0'
        ld c, 0
        push af
        ld a, b
        add a, {SCROLL_ROW0}
        ld b, a
        pop af
        call putc               ; how far the row moved, at the left
        pop bc
        ld de, {8 * SCROLL_W}
        add hl, de              ; the next row of the bitmap
        inc b
        ld a, b
        cp {SCROLL_ROWS}
        jr nz, row
        ld hl, BITMAP
        ld de, ${SCROLL_W:02X}{SCROLL_ROWS:02X}            ; {SCROLL_W} bytes across, {SCROLL_ROWS} rows of cells
        ld a, {FIRST_CODE}
        ld b, {SCROLL_ROW0}
        ld c, {SCROLL_COL}
        call showblk            ; the bitmap, as {SCROLL_W * SCROLL_ROWS} characters
""" + SHOW_PAGE + f"""
; scroll1: the {SCROLL_W} bytes of a line from HL move one pixel right. Each byte
;          rotates right through the carry, the left one first, so the bit
;          that falls out of one byte comes in at the top of the next.
scroll1:
        or a                    ; a 0 comes in at the left edge
        ld b, {SCROLL_W}
sc1:    rr (hl)
        inc l
        djnz sc1
        ret

; text: the characters from DE (ending in 0) into the eight lines of a row
;       of the bitmap from HL, a byte across for each, from the BIOS's
;       character set. Keeps B.
text:   ld a, (de)
        or a
        ret z
        push bc
        push de
        push hl
        ld l, a
        ld h, 0
        add hl, hl
        add hl, hl
        add hl, hl              ; the character x 8 ...
        ld bc, (CGTABL)
        add hl, bc              ; ... in the BIOS's set: its eight lines
        pop de                  ; DE: the bitmap
        push de
        ld b, 8
tx1:    ld a, (hl)
        ld (de), a
        inc hl
        ld a, e
        add a, {SCROLL_W}
        ld e, a                 ; one line down the bitmap
        jr nc, tx2
        inc d
tx2:    djnz tx1
        pop hl
        inc hl                  ; the next byte across
        pop de
        inc de                  ; the next character
        pop bc
        jr text
""" + SHOWBLK + f"""
words:  db "{SCROLL_TEXT}", 0
""" + library() + TAIL


# -------------------------------------------------------------- mirror.asm
ARROW = [  # 16 x 16: an arrow pointing right
    "0000000000000000",
    "0000000011000000",
    "0000000011100000",
    "0000000011110000",
    "0000000011111000",
    "0000000011111100",
    "0111111111111110",
    "0111111111111111",
    "0111111111111111",
    "0111111111111110",
    "0000000011111100",
    "0000000011111000",
    "0000000011110000",
    "0000000011100000",
    "0000000011000000",
    "0000000000000000"]
MIRROR_AT = [(2, 2), (7, 2)]        # the arrow, and its mirror image (column, row)
MIRROR_TABLE = 0xD000


def mirror():
    data = "".join(f"        db %{r[:8]}, %{r[8:]}\n" for r in ARROW)
    (c0, r0), (c1, r1) = MIRROR_AT
    return head("mirror", "an arrow turned round") + f"""TABLE   EQU ${MIRROR_TABLE:04X}               ; every byte, mirrored
flip    EQU RAM_START + $40    ; the arrow turned round: 16 lines of 2 bytes
""" + BLKVARS + """; An arrow, and the same arrow turned to face the other way: the two bytes
; of each line change places, and the bits of each byte are put in the
; opposite order (figure 10.4). Then every byte mirrored, into TABLE.
""" + TEXT_PAGE + f"""        ld hl, arrow
        ld de, flip
        ld b, 16                ; the arrow's sixteen lines
fl1:    push bc
        inc hl
        ld a, (hl)              ; the right byte ...
        call mirror
        ld (de), a              ; ... mirrored, on the left
        inc de
        dec hl
        ld a, (hl)              ; the left byte ...
        call mirror
        ld (de), a              ; ... mirrored, on the right
        inc de
        inc hl
        inc hl                  ; the next line
        pop bc
        djnz fl1
        ld hl, arrow
        ld de, $0202            ; 2 bytes across, 2 rows of cells
        ld a, {FIRST_CODE}
        ld b, {r0}
        ld c, {c0}
        call showblk            ; the arrow as it is
        ld hl, flip
        ld de, $0202
        ld a, {FIRST_CODE + 4}
        ld b, {r1}
        ld c, {c1}
        call showblk            ; the arrow turned round
        ld hl, TABLE
        ld e, 0                 ; every byte, 0 to 255
all:    ld a, e
t1:     call mirror
t2:     ld (hl), a
        inc hl
        inc e
        jr nz, all
""" + SHOW_PAGE + """
; mirror: A = A with its bits in the opposite order. Uses B and C.
mirror: ld c, a
        ld b, 8
mr1:    rr c                    ; the lowest bit of C into the carry ...
        rla                     ; ... and in at the bottom of A
        djnz mr1
        ret
""" + SHOWBLK + """
arrow:                          ; 16 lines of 2 bytes, pointing right
""" + data + library() + TAIL


# ----------------------------------------------------------------- div.asm
DIV_TIMED = [(65535, 10), (740, 10), (1000, 7), (65535, 255), (40000, 200)]
DIVISOR = 10


def div():
    timed = "".join(f"""        ld hl, {n}
        ld c, {d}
d{k}:     call div                ; {n} / {d}
        {f'ld (quo+{2 * k}), hl':<24}
        {f'ld (rem+{k}), a':<24}
""" for k, (n, d) in enumerate(DIV_TIMED))
    return cart("div", "sixteen bits divided by eight", f"""n       EQU RAM_START          ; the number divided, 0 to 65,535
qsum    EQU RAM_START + 2      ; 32 bits: the quotients added up
rsum    EQU RAM_START + 6      ; 32 bits: the remainders added up
qmix    EQU RAM_START + 10     ; 16 bits: the quotients mixed with XOR
quo     EQU RAM_START + 12     ; the timed quotients, two bytes each
rem     EQU RAM_START + {12 + 2 * len(DIV_TIMED)}     ; and their remainders
        xor a
        ld hl, n
        ld b, 12
clr:    ld (hl), a
        inc hl
        djnz clr                ; n and the sums start at 0
""" + timed + f"""every:  ld hl, (n)
        ld c, {DIVISOR}
        call div
        call tally
        ld hl, (n)
        inc hl
        ld (n), hl
        ld a, h
        or l
        jr nz, every            ; until n has gone round to 0
""", after="""
; div: HL = HL / C, and A = the remainder. C from 1 to 255. Uses B.
div:    xor a                   ; A: the remainder, built up a bit at a time
        ld b, 16
dv1:    add hl, hl              ; the top bit of HL into the carry ...
        rla                     ; ... and in at the bottom of the remainder
        jr c, dv2               ; nine bits: certainly C goes
        cp c
        jr c, dv3               ; C does not go
dv2:    sub c                   ; C goes: take it away,
        inc l                   ; and a 1 into the quotient
dv3:    djnz dv1
        ret

; tally: the quotient in HL added into qsum (32 bits) and mixed into qmix
;        with XOR; the remainder in A added into rsum (32 bits)
tally:  ex de, hl
        ld hl, (qsum)
        add hl, de
        ld (qsum), hl
        jr nc, ty1
        ld hl, (qsum + 2)
        inc hl
        ld (qsum + 2), hl
ty1:    ld l, a
        ld h, 0                 ; HL = the remainder
        ld bc, (rsum)
        add hl, bc
        ld (rsum), hl
        jr nc, ty3
        ld hl, (rsum + 2)
        inc hl
        ld (rsum + 2), hl
ty3:    ld a, (qmix)
        xor e
        ld (qmix), a
        ld a, (qmix + 1)
        xor d
        ld (qmix + 1), a
        ret
""", results=False)


# ----------------------------------------------------------------- bcd.asm
BCD_TESTS = [0x012345, 0x999999, 0x000740, 0x100000]


def bcd():
    body = []
    for k, v in enumerate(BCD_TESTS):
        digits = [(v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF]
        for op, name in (("bcd10", "up"), ("bcd01", "down")):
            body.append(f"""        ld hl, score
        ld (hl), ${digits[0]:02X}
        inc hl
        ld (hl), ${digits[1]:02X}
        inc hl
        {f'ld (hl), ${digits[2]:02X}':<24}; the score: {v:06X}
{f'{name}{k}:':<8}call {op}
        {f'ld (out+{8 * k + (0 if op == "bcd10" else 4)}), a':<24}; the digit that fell off
        ld hl, (score)
        {f'ld (out+{8 * k + (1 if op == "bcd10" else 5)}), hl':<24}
        ld a, (score + 2)
        {f'ld (out+{8 * k + (3 if op == "bcd10" else 7)}), a':<24}
""")
    return cart("bcd", "a BCD score times ten and divided by ten", """score   EQU RAM_START          ; six BCD digits, the first two first
out     EQU RAM_START + 3      ; for each score: digit and score, both ways
""" + "".join(body), after="""
; bcd10: the six digits at score, first digits first, one digit to the
;        left: the score times ten, with 0 coming in at the right. A = the
;        digit that falls off the left.
bcd10:  ld hl, score + 2        ; the last two digits
        xor a                   ; the digit that comes in: 0
        rld                     ; A's digit in at the bottom of (HL), the
        dec hl                  ; top digit of (HL) out into A
        rld
        dec hl
        rld
        ret

; bcd01: the six digits one digit to the right: the score divided by ten.
;        A = the digit that falls off the right, the remainder.
bcd01:  ld hl, score            ; the first two digits
        xor a                   ; 0 comes in at the left
        rrd                     ; A's digit in at the top of (HL), the
        inc hl                  ; bottom digit of (HL) out into A
        rrd
        inc hl
        rrd
        ret
""", results=False)


def sources():
    return {"logic.asm": logic(), "sprite.asm": sprite(), "bits.asm": bits(),
            "cost.asm": cost(), "rotate.asm": rotate(), "shifts.asm": shifts(),
            "mul.asm": mul(), "friction.asm": friction(), "scroll.asm": scroll(),
            "mirror.asm": mirror(), "div.asm": div(), "bcd.asm": bcd()}


def main():
    files = sources()
    for name, text in files.items():
        with open(os.path.join(HERE, name), "w") as f:
            f.write("\n".join(l.rstrip() for l in text.split("\n")))    # no spaces at line ends
    print(len(files), "sources written")


if __name__ == "__main__":
    main()
