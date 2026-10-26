#!/usr/bin/env python3
"""gen13.py - the programs of chapter 13.

    python3 gen13.py && ./build.sh

    copy.asm       256 bytes copied three ways: a loop, LDIR, and sixteen
                   LDIs at a time; the registers and flags LDIR and LDI
                   leave; and a block filled by LDIR copying it onto itself.
    overlap.asm    a line of text in a bitmap moved one cell to the right
                   with LDIR and with LDDR (figure 13.1).
    cpir.asm       a byte searched for with CPIR in chapter 11's list: where
                   it stopped, the flags, and the time.
    flip.asm       a table of all 256 bytes with their bits reversed, made
                   once, and 32 bytes turned round with it and without it.
    lines.asm      a table of the address of every pixel line in Graphic II's
                   patterns, made once; all 192 looked up, and all 192 worked
                   out, timed.
    sine.asm       a curve drawn in Graphic II with three tables: heights,
                   line addresses and the bits of a byte (figure 13.2).
    qsmul.asm      a table of n*n/4 made with additions only, a multiplication
                   of two bytes worked out from it, and all 65,536 products
                   added up, the loop's counters in IX's two halves.
    moire.asm      bit 9 of a x e drawn in Graphic II for every pixel, a across
                   and e down, by the same multiplication (figure 13.3).
    cost.asm       every block instruction, and the halves of IX, for the
                   debugger to time.
    otir.asm       256 bytes sent to the VDP by one OTIR, with the display off.

Graphic II, the screen of 256 x 192 pixels each its own bit, is chapter 22's;
sine.asm and moire.asm set it up the plain way, with the display off. Results
and tables are kept in the RAM, from $C000 (chapter 8). build.sh assembles
with --syntax=bF (chapter 8).
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
from asmparts import (HEAD, TAIL, TEXT_PAGE, SHOW_PAGE, library, SHOWBLK, BLKVARS,  # noqa: E402
                      GRAPHIC2)

RESULTS = "RESULTS EQU RAM_START          ; what the program found: the debugger reads it here\n"
FIRST_CODE = 128


def head(name, what):
    return HEAD.format(name=name, chapter=13, what=what)


def cart(name, what, body, after="", results=True, equs=""):
    """a cartridge that runs `body` with the interrupts off and stops"""
    return head(name, what) + (RESULTS if results else "") + equs + f"""init:   di
        ld sp, SYS_AREA
{body}stop:   jr stop
{after}""" + TAIL




# ---------------------------------------------------------------- copy.asm
SRC = 0xD000                # 256 bytes to copy, in the RAM
DST = [0xD100, 0xD200, 0xD300]
FLAGS_AT = 0xD400
FILL_AT, FILL_LEN, FILL_BYTE = 0xD800, 1024, 0xAA
STEP = 37                   # byte k of the source is 37 x k: all 256 different


def copy():
    return cart("copy", "256 bytes copied three ways, and a block filled", f"""        ld hl, ${SRC:04X}            ; the source: byte k is {STEP} x k
        xor a
mk:     ld (hl), a
        add a, {STEP}
        inc l
        jr nz, mk
c1:     call loopcp             ; one byte at a time, in a loop
c2:     call ldircp             ; with LDIR
c3:     call ldicp              ; with LDI, sixteen at a time
c4:     ld bc, $00FF
        push bc
        pop af                  ; every flag set, to see which LDIR changes
        ld hl, ${SRC:04X}
        ld de, ${FLAGS_AT:04X}
f1:     ld bc, 4
        ldir
f2:     ld bc, 2
l1:     ldi                     ; BC from 2 to 1
l2:     ldi                     ; and from 1 to 0
l3:     ld hl, ${FILL_AT:04X}
        ld (hl), ${FILL_BYTE:02X}           ; the first byte ...
        ld de, ${FILL_AT + 1:04X}
fl1:    ld bc, {FILL_LEN - 1}
        ldir                    ; ... copied onto the next, and on
fl2:    nop
""", after=f"""
; loopcp: 256 bytes from ${SRC:04X} to ${DST[0]:04X}, one at a time
loopcp: ld hl, ${SRC:04X}
        ld de, ${DST[0]:04X}
        ld b, 0                 ; 256 turns
lc1:    ld a, (hl)
        ld (de), a
        inc hl
        inc de
        djnz lc1
        ret

; ldircp: the same bytes to ${DST[1]:04X} with LDIR
ldircp: ld hl, ${SRC:04X}
        ld de, ${DST[1]:04X}
        ld bc, 256
        ldir
        ret

; ldicp: the same bytes to ${DST[2]:04X}, sixteen LDIs to a turn
ldicp:  ld hl, ${SRC:04X}
        ld de, ${DST[2]:04X}
        ld bc, 256
li1:    DUP 16                  ; sjasmplus writes the next line 16 times
        ldi
        EDUP
        jp pe, li1              ; P/V: BC is not 0 yet
        ret
""", results=False, equs="""; 256 bytes copied three ways, each call timed by the debugger; then what
; LDIR and LDI leave in the registers and flags; then a block filled by LDIR.
""")


# ------------------------------------------------------------- overlap.asm
SAMPLE = "Move this line one place right."
OV_LABELS = [(1, "The line:"), (4, "Moved with LDIR, forwards:"),
             (7, "Moved with LDDR, backwards:")]
OV_ROWS = [2, 5, 8]
OV_W = 32                   # bytes across a row of the bitmap
OV_RAM = 0xC200             # three rows of 8 lines of 32 bytes


def overlap():
    assert len(SAMPLE) == OV_W - 1
    labels = "".join(f"""        ld b, {r}
        ld c, 0
        ld hl, lab{k}
        call puts
""" for k, (r, _) in enumerate(OV_LABELS))
    rows = "".join(f"""        ld hl, ROW{k}
        ld de, sample
        call text               ; the line, into row {k} of the bitmap
""" for k in range(3))
    shows = "".join(f"""        ld hl, ROW{k}
        ld de, ${OV_W:02X}01            ; {OV_W} bytes across, one row of cells
        ld a, {FIRST_CODE + OV_W * k}
        ld b, {OV_ROWS[k]}
        ld c, 0
        call showblk
""" for k in range(3))
    texts = "".join(f'lab{k}:   db "{t}", 0\n' for k, (_, t) in enumerate(OV_LABELS))
    return head("overlap", "a line moved with LDIR and with LDDR") + f"""ROW0    EQU ${OV_RAM:04X}               ; three rows of a bitmap: 8 lines of {OV_W} bytes each
ROW1    EQU ROW0 + {8 * OV_W}
ROW2    EQU ROW1 + {8 * OV_W}
""" + BLKVARS + f"""; The same line of text three times, in a bitmap in the RAM; the second
; copy moved one cell to the right with LDIR, the third with LDDR (figure
; 13.1). showblk sends the bitmap to the VDP (chapter 10).
""" + TEXT_PAGE + f"""        ld hl, ROW0
        ld de, ROW0 + 1
        ld (hl), 0
        ld bc, {3 * 8 * OV_W} - 1
        ldir                    ; the bitmap clear
""" + labels + rows + """        ld hl, ROW1
        call fwd                ; row 1, with LDIR
        ld hl, ROW2
        call back               ; row 2, with LDDR
""" + shows + SHOW_PAGE + f"""
; fwd: the row of the bitmap at HL moved one byte right, each line with LDIR
fwd:    ld a, 8                 ; eight lines
fw1:    push hl
        ld d, h
        ld e, l
        inc de                  ; DE: one byte on
        ld bc, {OV_W - 1}
        ldir                    ; from the left end, forwards
        pop hl
        ld bc, {OV_W}
        add hl, bc              ; the next line
        dec a
        jr nz, fw1
        ret

; back: the row at HL moved one byte right with LDDR, from the right end
back:   ld a, 8
bk1:    push hl
        ld bc, {OV_W - 2}
        add hl, bc              ; HL: the next to last byte
        ld d, h
        ld e, l
        inc de                  ; DE: the last
        ld bc, {OV_W - 1}
        lddr                    ; from the right end, backwards
        pop hl
        ld bc, {OV_W}
        add hl, bc
        dec a
        jr nz, bk1
        ret

; text: the characters from DE (ending in 0) into the eight lines of a row
;       of the bitmap from HL, a byte across for each, from the BIOS's
;       character set
text:   ld a, (de)
        or a
        ret z
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
        add a, {OV_W}
        ld e, a                 ; one line down the bitmap
        jr nc, tx2
        inc d
tx2:    djnz tx1
        pop hl
        inc hl                  ; the next byte across
        pop de
        inc de                  ; the next character
        jr text
""" + SHOWBLK + library() + texts + f'sample: db "{SAMPLE}", 0\n' + TAIL


# ---------------------------------------------------------------- cpir.asm
LIST_LEN = 32
LIST = [(0x11 + 0x0F * i) & 0xFF for i in range(LIST_LEN)]    # chapter 11's list
FIND = [LIST[0], LIST[10], LIST[31], 0x07]


def cpir():
    assert len(set(LIST)) == LIST_LEN and FIND[3] not in LIST
    tests = "".join(f"""        ld a, ${v:02X}
        ld hl, list
{f's{k}:':<8}ld bc, {LIST_LEN}
        cpir
{f'e{k}:':<8}nop
""" for k, v in enumerate(FIND))
    return cart("cpir", "a byte searched for with CPIR", """        scf                     ; the carry set: CPIR leaves it alone
""" + tests, after="\nlist:   db " + ", ".join(f"${d:02X}" for d in LIST) + "\n", results=False,
                equs=f"""; Chapter 11's list of {LIST_LEN} bytes searched with CPIR for the first, the
; eleventh, the last, and a byte that is not there. The debugger reads HL,
; BC and the flags after each search, and the time.
""")


# ---------------------------------------------------------------- flip.asm
MIRRORS = 0xD000            # the table: a whole page, so its address is H only
SPRITE_RAM = 0xC200         # the 32 bytes, twice, in the RAM
SPRITE = [0x01, 0x03, 0x07, 0x0F, 0x1F, 0x3F, 0x7F, 0xFF,
          0x80, 0xC0, 0xE0, 0xF0, 0xF8, 0xFC, 0xFE, 0xFF,
          0x18, 0x3C, 0x7E, 0xFF, 0xFF, 0x7E, 0x3C, 0x18,
          0xAA, 0x55, 0xAA, 0x55, 0x0F, 0xF0, 0x33, 0xCC]


def flip():
    return cart("flip", "a table of every byte turned round", f"""        ld hl, sprite
        ld de, ONE
        ld bc, 32
        ldir
        ld hl, sprite
        ld de, TWO
        ld bc, 32
        ldir                    ; the 32 bytes, twice, into the RAM
t0:     call mktab              ; the table, made once
t1:     ld de, ONE
        ld b, 32
t2:     call byrout             ; 32 bytes, with mirror
t3:     ld de, TWO
        ld b, 32
t4:     call bytab              ; the same 32, with the table
t5:     nop
""", after=f"""
; mktab: the 256-byte table at ${MIRRORS:04X}: byte n holds n mirrored
mktab:  ld hl, MIRRORS
mk1:    ld a, l                 ; n
        call mirror
        ld (hl), a
        inc l
        jr nz, mk1              ; L back round to 0: all 256 done
        ret

; byrout: the B bytes at DE turned round, each by a call of mirror
byrout: ld a, (de)
        push bc                 ; mirror uses B and C
        call mirror
        pop bc
        ld (de), a
        inc de
        djnz byrout
        ret

; bytab: the B bytes at DE turned round with the table
bytab:  ld h, high MIRRORS      ; H: the table's page
bt1:    ld a, (de)
        ld l, a                 ; L: the byte, so HL points at its answer
        ld a, (hl)
        ld (de), a
        inc de
        djnz bt1
        ret

; mirror: A = A with its bits in the opposite order. Uses B and C.
;         (chapter 10)
mirror: ld c, a
        ld b, 8
mr1:    rr c
        rla
        djnz mr1
        ret

sprite: db """ + ", ".join(f"${b:02X}" for b in SPRITE) + "\n", results=False,
                equs=f"""MIRRORS EQU ${MIRRORS:04X}               ; the table, a whole page of the RAM
ONE     EQU ${SPRITE_RAM:04X}               ; 32 bytes turned round by mirror
TWO     EQU ${SPRITE_RAM + 32:04X}               ; the same 32, turned round by the table
; A table of every byte with its bits in the opposite order, made once with
; chapter 10's mirror; then 32 bytes turned round by mirror and the same 32
; turned round by the table.
""")


# --------------------------------------------------------------- lines.asm
LINES = 0xD000              # low bytes of the 192 line addresses; high bytes
                            # in the page after
MKLINES = """
; mklines: the address in Graphic II's patterns of each pixel line, 0 to 191,
;          into two tables: low bytes at LINES + y, high bytes one page on.
;          Uses A, DE, HL.
mklines:
        ld e, 0                 ; E: y
ml1:    ld a, e
        call calc               ; HL: line y's address, worked out
        ld d, high LINES
        ld a, l
        ld (de), a              ; the low byte
        inc d
        ld a, h
        ld (de), a              ; the high byte, a page on
        inc e
        ld a, e
        cp 192
        jr nz, ml1
        ret

; calc: HL = the address of pixel line A (0-191) in Graphic II's patterns, at
;       the left edge: the row of cells times 256, and the line in the cell.
;       Uses A, D.
calc:   ld d, a                 ; y, kept
        and %00000111
        ld l, a                 ; the line in the cell
        ld a, d
        rrca
        rrca
        rrca
        and %00011111
        ld h, a                 ; the row of cells, times 256
        ret
"""

LINE = """
; line: HL = the address of pixel line A (0-191), from the tables
line:   ld l, a
        ld h, high LINES
        ld a, (hl)              ; the low byte
        inc h
        ld h, (hl)              ; the high byte, a page on
        ld l, a
        ret
"""


def lines():
    return cart("lines", "a table of the address of every pixel line", """l0:     call mklines
l1:     ld e, 0
lk1:    ld a, e
        call line               ; from the table
        inc e
        ld a, e
        cp 192
        jr nz, lk1
l2:     ld e, 0
lk2:    ld a, e
        call calc               ; worked out
        inc e
        ld a, e
        cp 192
        jr nz, lk2
l3:     nop
""", after=MKLINES + LINE, results=False, equs=f"""LINES   EQU ${LINES:04X}               ; two pages of the RAM
; The address of every pixel line in Graphic II's patterns kept in a table,
; made once; then all 192 lines looked up in it, and all 192 worked out
; again, timed.
""")


# ---------------------------------------------------------------- sine.asm
SINE = [96 - round(88 * math.sin(2 * math.pi * x / 256)) for x in range(256)]


def sine():
    return head("sine", "a curve drawn with three tables") + f"""LINES   EQU ${LINES:04X}               ; the second table, made by mklines
; A curve drawn with three tables: the height of the curve for each column,
; worked out in Python when this file was written, since the Z80 has no
; sine; the address of each pixel line; and the bit of each of the eight
; pixels in a byte (figure 13.2).
""" + GRAPHIC2 + """        call mklines
        ld e, 0                 ; E: x, 0 to 255
sn1:    ld l, e
        ld h, high sines
        ld a, (hl)              ; y, from the first table
        ld l, a
        ld h, high LINES
        ld c, (hl)
        inc h
        ld b, (hl)              ; BC: line y, from the second
        ld a, e
        and %11111000           ; eight bytes to a cell across
        add a, c
        ld c, a                 ; BC: the byte
        ld a, e
        and %00000111
        ld l, a
        ld h, high masks
        ld d, (hl)              ; D: the pixel's bit, from the third
        call vor                ; the pixel set
        inc e
        jr nz, sn1
""" + SHOW_PAGE + """
; vor: the byte at BC in the VRAM ORed with D: read through the ports,
;      changed, and written back (chapter 19). Display off. Uses A.
vor:    ld a, c
        out (VDP_CTRL), a
        ld a, b
        out (VDP_CTRL), a       ; the address, to read
        in a, (VDP_DATA)
        or d
        push af
        ld a, c
        out (VDP_CTRL), a
        ld a, b
        or $40
        out (VDP_CTRL), a       ; the same address, to write
        pop af
        out (VDP_DATA), a
        ret
""" + MKLINES + """
        ALIGN 256               ; each table a page of its own
sines:
""" + "".join("        db " + ", ".join(str(v) for v in SINE[i:i + 16]) + "\n"
              for i in range(0, 256, 16)) + """        ALIGN 256
masks:  db $80, $40, $20, $10, $08, $04, $02, $01
""" + TAIL


# --------------------------------------------------------------- qsmul.asm
SQ = 0xD000                 # n*n/4, n from 0 to 510: low bytes in two pages
                            # from here, high bytes in the two pages after them
MUL_PAIRS = [(0, 0), (255, 255), (200, 100), (100, 200), (13, 17), (255, 1),
             (1, 255), (128, 128)]

MULSQ = """
; mul: HL = A x E, both taken as unsigned. Uses A, BC, DE.
mul:    ld d, a
        add a, e                ; a + e: the carry is its ninth bit
        ld l, a
        ld a, high SQ
        adc a, 0                ; the page: the first or the second
        ld h, a
        ld c, (hl)              ; the low byte of (a + e)(a + e)/4
        inc h
        inc h                   ; the high bytes are two pages on
        ld b, (hl)
        ld a, d
        sub e                   ; a - e
        jr nc, mu1
        neg                     ; its size, if it was negative
mu1:    ld l, a
        ld h, high SQ           ; under 256: the first page
        ld e, (hl)
        inc h
        inc h
        ld d, (hl)              ; DE = (a - e)(a - e)/4
        ld h, b
        ld l, c
        or a                    ; the carry clear for SBC
        sbc hl, de
        ret

; sqinit: n*n/4 for n = 0 to 510, each from the one before by adding
;         (n + 1)/2, rounded down
sqinit: ld de, SQ               ; DE: where n's low byte goes
        ld hl, 0                ; HL: n*n/4, from n = 0
        ld bc, 1                ; BC: n + 1
sq1:    ld a, l
        ld (de), a
        inc d
        inc d
        ld a, h
        ld (de), a              ; the high byte, two pages on
        dec d
        dec d
        inc de
        push bc
        srl b
        rr c                    ; (n + 1)/2
        add hl, bc              ; the next quarter square
        pop bc
        inc bc
        ld a, b
        cp 2                    ; n + 1 = 512: n = 510 was the last
        jr nz, sq1
        ret
"""


def qsmul():
    prods = "".join(f"""        ld a, {a}
        ld e, {e}
{f'm{k}:':<8}call mul
{f'n{k}:':<8}{f'ld (res + {2 * k}), hl':<24}
""" for k, (a, e) in enumerate(MUL_PAIRS))
    return cart("qsmul", "multiplication by a table of quarter squares", """q0:     call sqinit
q1:     nop
""" + prods + """        ld hl, 0
        ld (total), hl
        ld (total + 2), hl      ; the total from 0: the RAM is not cleared
s0:     call sumall
s1:     nop
""", after=MULSQ + """
; sumall: every product A x E, A and E from 0 to 255, added up in 32 bits
;         at total. mul uses A, BC, DE and HL, so the two counters are the
;         halves of IX, and IY points at the total.
sumall: ld iy, total
        ld ixh, 0               ; A: 0 to 255, in IX's high half
sa1:    ld ixl, 0               ; E: 0 to 255, in the low half
sa2:    ld a, ixh
        ld e, ixl
        call mul
        ld a, (iy+0)
        add a, l
        ld (iy+0), a
        ld a, (iy+1)
        adc a, h
        ld (iy+1), a
        jr nc, sa3              ; no carry out of the low word
        inc (iy+2)
        jr nz, sa3
        inc (iy+3)
sa3:    inc ixl
        jr nz, sa2
        inc ixh
        jr nz, sa1
        ret
""", results=False, equs=f"""SQ      EQU ${SQ:04X}               ; the table: four pages of the RAM
total   EQU RAM_START          ; 32 bits: every product added up
res     EQU RAM_START + 4      ; the eight products timed
; Multiplication by a table of quarter squares:
;     a x e = (a + e) x (a + e) / 4 - (a - e) x (a - e) / 4
; with each quarter square rounded down (a + e and a - e are both even or
; both odd, so the two parts thrown away are the same). The table is made
; first, with additions only; then eight products are timed, and all
; 65,536 are added up. The interrupts are off: IX and IY are the program's.
""")


# --------------------------------------------------------------- moire.asm
MOIRE_BIT = 9               # the bit of each product that makes the picture


def moire():
    return head("moire", "a picture of multiplication") + f"""SQ      EQU ${SQ:04X}               ; the table of quarter squares
acc     EQU VARS               ; the byte being built, eight pixels
; A picture of multiplication: for every pixel, a across (0 to 255) and e
; down (0 to 191), bit {MOIRE_BIT} of a x e worked out by mul, 1 for ink (figure
; 13.3). The bytes go to the VDP in the order of Graphic II's patterns: a
; cell's eight lines, then the next cell. mul uses A, BC, DE and HL: the
; halves of IY and IX count.
""" + GRAPHIC2 + f"""        call sqinit
        VRAM_WRITE $0000        ; the patterns, from the first
        ld iyh, 0               ; the cell's top line: 0, 8 ... 184
mo1:    ld iyl, 0               ; the cell's left column: 0, 8 ... 248
mo2:    ld ixh, 0               ; the line in the cell: 0 to 7
mo3:    ld ixl, 0               ; the pixel in the line: 0 to 7
mo4:    ld a, iyh
        add a, ixh
        ld e, a                 ; e: the pixel's line
        ld a, iyl
        add a, ixl              ; a: its column
        call mul                ; HL = a x e
        ld a, h
        rra
        rra                     ; bit {MOIRE_BIT} of the product into the carry
        ld hl, acc
        rl (hl)                 ; and in at the right of the byte
        inc ixl
        ld a, ixl
        cp 8
        jr nz, mo4              ; eight pixels to a byte
        ld a, (acc)
        out (VDP_DATA), a       ; the byte, to the next place in the VRAM
        inc ixh
        ld a, ixh
        cp 8
        jr nz, mo3              ; eight lines to a cell
        ld a, iyl
        add a, 8
        ld iyl, a
        jr nz, mo2              ; 32 cells across
        ld a, iyh
        add a, 8
        ld iyh, a
        cp 192
        jr nz, mo1              ; 24 rows of cells
""" + SHOW_PAGE + MULSQ + TAIL


# ---------------------------------------------------------------- cost.asm
# (label, instruction, comment)
COST = [("c1", "ldi", ""), ("c2", "ldd", ""), ("c3", "ldir", "two turns"),
        (None, "ld bc, 2", ""), ("c4", "lddr", ""), (None, "ld bc, 4", ""),
        ("c5", "cpi", ""), ("c6", "cpd", ""), ("c7", "cpir", "two turns"),
        (None, "ld bc, 2", ""), ("c8", "cpdr", ""),
        (None, "ld bc, $0498", "B: 4, C: the VDP's data port"),
        ("c9", "ini", ""), ("c10", "ind", ""), ("c11", "inir", "two turns"),
        (None, "ld b, 2", ""), ("c12", "indr", ""), (None, "ld b, 4", ""),
        ("c13", "outi", ""), ("c14", "outd", ""), ("c15", "otir", "two turns"),
        (None, "ld b, 2", ""), ("c16", "otdr", ""),
        ("c17", "ld ixh, $12", ""), ("c18", "ld ixl, $34", ""), ("c19", "ld a, ixh", ""),
        ("c20", "ld e, ixl", ""), ("c21", "inc ixh", ""), ("c22", "dec ixl", ""),
        ("c23", "add a, ixl", ""), ("c24", "cp ixh", ""), ("c25", "nop", "")]


def cost_line(label, ins, comment):
    code = f"{(label + ':') if label else '':<8}{ins}"
    return (f"{code:<32}; {comment}" if comment else code) + "\n"


def cost():
    return cart("cost", "every block instruction, and the halves of IX", """        ld hl, $D000
        ld de, $D001
        ld (hl), 0
        ld bc, 511
        ldir                    ; the bytes they work on: all 0
        ld hl, $D000
        ld de, $D100
        ld bc, 4
        ld a, $FF               ; a byte that is not there: no CP stops early
""" + "".join(cost_line(*c) for c in COST),
                results=False, equs="""; Every block instruction, and the halves of IX, one after another, each
; with a label for the debugger to stop at. The repeating ones run two
; turns; the debugger stops at each turn. The port is the VDP's, with the
; display off: what goes in and out is harmless here.
""")


# ---------------------------------------------------------------- otir.asm
OTIR_AT = 0x2800            # unused VRAM in this book's Graphic I page


def otir():
    return head("otir", "256 bytes sent to the VDP by one OTIR") + """; 256 bytes sent to the VDP by one OTIR, with the display off; the debugger
; stops at every turn.
""" + TEXT_PAGE + f"""        VRAM_WRITE ${OTIR_AT:04X}        ; unused VRAM
        ld hl, block
        ld bc, VDP_DATA         ; B: 0, 256 turns; C: the VDP's data port
o1:     otir
o2:     nop
stop:   jr stop

block:                          ; 256 bytes: 0, 1, 2 ... 255
""" + "".join("        db " + ", ".join(str(v) for v in range(i, i + 16)) + "\n"
              for i in range(0, 256, 16)) + library() + TAIL


def sources():
    return {"copy.asm": copy(), "overlap.asm": overlap(), "cpir.asm": cpir(), "flip.asm": flip(),
            "lines.asm": lines(), "sine.asm": sine(), "qsmul.asm": qsmul(), "moire.asm": moire(),
            "cost.asm": cost(), "otir.asm": otir()}


def main():
    files = sources()
    for name, text in files.items():
        with open(os.path.join(HERE, name), "w") as f:
            f.write("\n".join(l.rstrip() for l in text.split("\n")))    # no spaces at line ends
    print(len(files), "sources written")


if __name__ == "__main__":
    main()
