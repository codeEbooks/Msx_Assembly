#!/usr/bin/env python3
"""gen34.py - the programs of chapter 34: reading the keyboard.

    python3 gen34.py && ./build.sh

    matrix.asm   the whole matrix once a frame from the ports, rows 0 to 15,
                 each row drawn as eight boxes and its byte, and port C read
                 back; on the book's two machines and on MSXBOOK_EU16G, the
                 same machine with key ghosting on (figure 34.2)
    legend.asm   the BIOS's interrupt reads the keyboard and types; the
                 program finds which key went down from the ports and prints
                 the BIOS's character for it in that key's place: rows 0 to 5
                 of the matrix as each machine types them (figure 34.1)
    snsmat.asm   row 8 read three ways every frame: from the ports, with the
                 BIOS's SNSMAT, and from NEWKEY, the BIOS's copy of the matrix
                 (figure 34.3)
    define.asm   five keys chosen by the player, by place in the matrix, and
                 a figure moved with them (figure 34.4)
    rowonly.asm  WHERE IT BREAKS: matrix.asm with a scan that writes the row
                 number alone to port C

The programs that read the matrix themselves take the interrupt in mode 2
(chapter 17) and read it with the interrupts off; legend.asm and snsmat.asm
leave the interrupt to the BIOS, whose routine reads the keyboard. Every
program prints in Graphic I, black ink on white, ends with
asmparts.CART_END, and build.sh assembles with --syntax=bFw. Each program's
keys are in an events file, NAME.events, written here: a frame and an
openMSX command a line, the frame counted from INIT (tools/msxcap.py).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "ch26"))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "ch30"))
from asmparts import HEAD, CART_END, IM2, im2, BOX_EMPTY, BOX_FULL, BOX_SHAPES  # noqa: E402
import gen26  # noqa: E402  (chapter 26: the figure, tidy, db_rows)
import shapes30  # noqa: E402  (chapter 30's set)
from gen26 import tidy, db_rows  # noqa: E402

BIOS = '        INCLUDE "bios.inc"\n'
BLACK, DARK_BLUE, WHITE = 1, 4, 15
EU, JP, EUG = "MSXBOOK_EU16", "MSXBOOK_JP16", "MSXBOOK_EU16G"
FRAME_T = {EU: 71364, JP: 59736, EUG: 71364}
FONT = shapes30.wide()                  # codes 32 to 127
FIGURE = gen26.big(gen26.FIGURE)        # chapter 26's figure, 16 x 16
TEXT_REGS = [0, 0xE0, 6, 0x80, 0, 0x36, 7, 0x0F]   # Graphic I, the signal on
SPRITE_REGS = [0, 0xE2, 6, 0x80, 0, 0x36, 7, 0x0F]  # and sprites of 16 x 16
ROWS = 11                               # the MSX1's keyboard: rows 0 to 10
ALL = 16                                # the four bits of the row: 0 to 15


def head(name, what):
    return HEAD.format(name=name, chapter=34, what=what) + BIOS


# ------------------------------------------------------------------ the keys
# The names define.asm gives the 88 keys, row by row and bit 0 first: a
# key's legend where the book's two machines have the same one, and its
# place where they do not (legend.asm and figure 34.1 show which)
NAMES = [
    "0", "1", "2", "3", "4", "5", "6", "7",
    "8", "9", "-", "(1,3)", "(1,4)", "(1,5)", "(1,6)", ";",
    "(2,0)", "(2,1)", ",", ".", "/", "(2,5)", "A", "B",
    "C", "D", "E", "F", "G", "H", "I", "J",
    "K", "L", "M", "N", "O", "P", "Q", "R",
    "S", "T", "U", "V", "W", "X", "Y", "Z",
    "SHIFT", "CTRL", "GRAPH", "CAPS", "CODE", "F1", "F2", "F3",
    "F4", "F5", "ESC", "TAB", "STOP", "BS", "SELECT", "RETURN",
    "SPACE", "HOME", "INS", "DEL", "LEFT", "UP", "DOWN", "RIGHT",
    "PAD *", "PAD +", "PAD /", "PAD 0", "PAD 1", "PAD 2", "PAD 3", "PAD 4",
    "PAD 5", "PAD 6", "PAD 7", "PAD 8", "PAD 9", "PAD -", "PAD ,", "PAD .",
]
NAME_LEN = 6
assert len(NAMES) == 8 * ROWS and all(len(n) <= NAME_LEN for n in NAMES)


def key(name):
    """(row, mask) of a key, by its name in NAMES"""
    k = NAMES.index(name)
    return k // 8, 1 << (k % 8)


# ------------------------------------------------------------------ the parts
ISR = """
; isr: every frame, a frame counted. Keeps AF
isr:    push af
        in a, (VDP_CTRL)        ; the status: the signal down
        ld a, (ticks)
        inc a
        ld (ticks), a
        pop af
        ei
        ret
"""

SCAN = """
; scan: B rows of the keyboard, from row 0, into the bytes from HL; a bit at 0
; is a key held down. Port C's top four bits drive the cassette motor and its
; output, the CAPS lamp and the click (chapter 3): they go back as they were.
; The interrupts must be off. Uses A, B, C, HL
scan:   in a, (PPI_C)           ; 12
        and $F0                 ;  8  the top four bits
        ld c, a                 ;  5  and row 0
.row:   ld a, c                 ;  5
        out (PPI_C), a          ; 12  the row
        in a, (PPI_B)           ; 12  its eight keys
        ld (hl), a              ;  8
        inc hl                  ;  7
        inc c                   ;  5  the next row
        djnz .row               ; 14 / 9
        ret                     ; 11
"""

# rowonly.asm's scan: the same loop, with the row alone written to port C
SCAN_ROW_ONLY = """
; scan: B rows of the keyboard, from row 0, into the bytes from HL. The row is
; written to port C as it is: its top four bits go out as 0
scan:   ld c, 0                 ;  8  row 0, and nothing else
.row:   ld a, c                 ;  5
        out (PPI_C), a          ; 12  the row
        in a, (PPI_B)           ; 12  its eight keys
        ld (hl), a              ;  8
        inc hl                  ;  7
        inc c                   ;  5  the next row
        djnz .row               ; 14 / 9
        ret                     ; 11
"""

PRINT = f"""
; at: the next characters go to row D, column E (chapter 30)
at:     ld a, d
        rrca
        rrca
        rrca
        ld c, a
        and $E0
        or e
        out (VDP_CTRL), a
        ld a, c
        and $03
        or $18 | $40
        out (VDP_CTRL), a
        ret

; cells: A as eight boxes from bit 7, a filled box for a 0 (a key held) and
; an empty one for a 1, from the address set. Uses A, B, L
cells:  ld l, a
        ld b, 8
.cell:  ld a, {BOX_FULL}
        rlc l                   ; the next bit, into the carry
        jr nc, .put             ; 0: held
        ld a, {BOX_EMPTY}
.put:   out (VDP_DATA), a
        djnz .cell
        ret

; hex: A as two hexadecimal digits, from the address set. Uses A, C
hex:    ld c, a
        rrca
        rrca
        rrca
        rrca
        call .digit
        ld a, c
.digit: and $0F
        add a, '0'
        cp '9' + 1
        jr c, .out
        add a, 'A' - '9' - 1
.out:   out (VDP_DATA), a
        ret

; send: E blocks of 256 bytes from HL to the VDP
send:   ld c, VDP_DATA
        ld b, 0
.otir:  otir
        dec e
        jr nz, .otir
        ret
"""


def setup(regs, font="own", sprite=False):
    """Graphic I with the display off: the shapes (chapter 30's set at 32 and
    the two boxes at 1 and 2, or the BIOS's own 256), black ink on white, the
    names from the table at `names`, no sprites"""
    if font == "own":
        shapes = """        VRAM_WRITE $0000        ; patterns: chapter 30's set at 32
        ld hl, shapes
        ld e, 4
        call send
"""
    else:
        shapes = """        VRAM_WRITE $0000        ; patterns: the BIOS's set, from CGTABL
        ld hl, (CGTABL)
        ld e, 8
        call send
        VRAM_WRITE $0008        ; and the two boxes at 1 and 2
        ld hl, boxes
        ld bc, 16 << 8 | VDP_DATA
        otir
"""
    spr = """        VRAM_WRITE $3800        ; sprite pattern 0: chapter 26's figure
        ld hl, figure
        ld bc, 32 << 8 | VDP_DATA
        otir
""" if sprite else ""
    return f"""init:   di
        ld sp, SYS_AREA
        VDP_REG 1, $80          ; display off
        VDP_REG 0, ${regs[0]:02X}          ; Graphic I
        VDP_REG 2, ${regs[2]:02X}          ; names    $1800
        VDP_REG 3, ${regs[3]:02X}          ; colours  $2000
        VDP_REG 4, ${regs[4]:02X}          ; patterns $0000
        VDP_REG 5, ${regs[5]:02X}          ; sprite attributes $1B00
        VDP_REG 6, ${regs[6]:02X}          ; sprite patterns   $3800
        VDP_REG 7, ${regs[7]:02X}          ; border white
{shapes}        VRAM_WRITE $2000        ; black ink on white paper
        ld a, $1F
        ld b, 32
.col:   out (VDP_DATA), a
        djnz .col
        VRAM_WRITE $1800        ; the names
        ld hl, names
        ld e, 3
        call send
        VRAM_WRITE $1B00        ; no sprites
        ld a, $D0
        out (VDP_DATA), a
{spr}"""


def own_shapes():
    """codes 0 to 127: nothing, the two boxes, chapter 30's set"""
    out = [0] * 1024
    for k in (BOX_EMPTY, BOX_FULL):
        out[8 * k:8 * k + 8] = BOX_SHAPES[k]
    out[256:1024] = FONT
    return out


def boxes_data():
    return "boxes:                          ; characters 1 (empty box) and 2 (filled)\n" + \
        db_rows(BOX_SHAPES[BOX_EMPTY] + BOX_SHAPES[BOX_FULL], 8)


def page(texts):
    """the 768 names: TEXTS is [(row, column, text)]; codes 1 and 2 pass"""
    n = [32] * 768
    for row, col, text in texts:
        for i, ch in enumerate(text):
            n[32 * row + col + i] = ch if isinstance(ch, int) else ord(ch)
    return n


# ------------------------------------------------------------------ matrix.asm
TOP = 3                     # the screen row of matrix row 0
BOX_COL, HEX_COL = 5, 15    # the boxes, bit 7 first, and the byte
PORT_ROW = TOP + ALL + 1    # port C, read back


def matrix_texts():
    t = [(1, 0, "row  76543210  $A9")]
    for r in range(ALL):
        t.append((TOP + r, 0, f"{r:3d}"))
        t.append((TOP + r, BOX_COL, [BOX_EMPTY] * 8))
        t.append((TOP + r, HEX_COL, "FF"))
    t.append((PORT_ROW, 0, "$AA"))
    t.append((PORT_ROW, BOX_COL, [BOX_EMPTY] * 8))
    return t


def matrix_names():
    return page(matrix_texts())


DRAW = f"""
; draw: the 16 rows as boxes and bytes, and port C as it reads back
draw:   ld hl, rows
        ld d, {TOP}
.row:   ld e, {BOX_COL}
        call at
        ld a, (hl)
        push hl
        call cells
        pop hl
        ld e, {HEX_COL}
        call at
        ld a, (hl)
        call hex
        inc hl
        inc d
        ld a, d
        cp {TOP + ALL}
        jr nz, .row
        ld d, {PORT_ROW}
        ld e, {BOX_COL}
        call at
        in a, (PPI_C)           ; port C: the last value written to it
        ld (portc), a
        cpl                     ; a 1 drawn filled, as the rows' 0s
        call cells
        ld e, {HEX_COL}
        call at
        ld a, (portc)
        jp hex
"""

MATRIX_RAM = """ticks   EQU VARS                ; frames counted by isr
portc   EQU VARS + 1            ; port C, read back
rows    EQU VARS + 16           ; the matrix: 16 bytes
"""


def matrix(name="matrix", scan=SCAN):
    say = ("""; The keyboard matrix once a frame from the ports: rows 0 to 15, each as eight
; boxes from bit 7 and its byte, a filled box for a key held, and port C as
; it reads back. Rows 11 to 15 have no keys on an MSX1.
""" if name == "matrix" else """; WHERE IT BREAKS. matrix.asm with a scan that writes the row number alone to
; port C, and with it 0 to the cassette motor, the CAPS lamp and the click.
""")
    body = setup(TEXT_REGS) + im2("isr") + f"""        VDP_REG 1, $E0          ; the display on, and the frame's signal
        in a, (VDP_CTRL)
main:   ei
        halt                    ; wait for the frame
        di                      ; the interrupts off: the ports, then the VDP
        ld hl, rows
        ld b, {ALL}
        call scan
scanned:
        call draw
        jr main
"""
    return (head(name, "the matrix, from the ports" if name == "matrix" else
                 "a scan that forgets port C's top bits") + MATRIX_RAM + IM2 + say +
            tidy(body + scan + DRAW + ISR + PRINT) +
            "names:                          ; 24 rows of 32\n" + db_rows(matrix_names(), 16) +
            "shapes:                         ; codes 0 to 127\n" + db_rows(own_shapes(), 16) +
            CART_END)


# ------------------------------------------------------------------ legend.asm
LEG_TOP, LEG_COL = 3, 5     # matrix row 0's line, and bit 7's column
LEG_ROWS = 6                # rows 0 to 5: the keys that type characters


def leg_cell(r, b):
    """the screen row and column of key (row r, bit b)"""
    return LEG_TOP + 2 * r, LEG_COL + 2 * (7 - b)


def legend_texts():
    t = [(1, 0, "row  7 6 5 4 3 2 1 0")]
    for r in range(LEG_ROWS):
        t.append((LEG_TOP + 2 * r, 0, f"{r:3d}"))
        for b in range(8):
            row, col = leg_cell(r, b)
            t.append((row, col, [BOX_EMPTY]))
    return t


LEGEND_RAM = """rows    EQU VARS                ; rows 0 to 5 of the matrix, this frame
before  EQU VARS + 8            ; and the last frame
cell    EQU VARS + 16           ; the place of the last key gone down
"""


def legend():
    body = setup(TEXT_REGS, font="bios") + f"""        ld hl, before           ; nothing held before the first frame
        ld b, {LEG_ROWS}
.none:  ld (hl), $FF
        inc hl
        djnz .none
        ld hl, $1800
        ld (cell), hl
        im 1                    ; the interrupt: the BIOS's routine at $0038
        VDP_REG 1, $E0          ; the display on, and the frame's signal
main:   ei
        halt                    ; the frame, and the BIOS's interrupt routine
        di
        ld hl, rows
        ld b, {LEG_ROWS}
        call scan
        call fresh
        call CHSNS              ; a character in the BIOS's buffer? (EI)
        jr z, main
        call CHGET              ; take it
got:    di
        ld c, a
        ld hl, (cell)
        ld a, l
        out (VDP_CTRL), a
        ld a, h
        or $40
        out (VDP_CTRL), a
        ld a, c
        out (VDP_DATA), a       ; the character, in the place of its key
        jr main

; fresh: a key of rows 0-5 that was up last frame and is down now: its place
; on the screen into cell; and this frame's rows into before. Uses A, B, C,
; D, E, HL
fresh:  ld hl, rows
        ld de, before
        ld c, 0                 ; the row
.row:   ld a, (de)              ; last frame's keys
        ld b, a
        ld a, (hl)              ; this frame's
        ld (de), a
        cpl
        and b                   ; 1: down now, up before
        call nz, place
        inc hl
        inc de
        inc c
        ld a, c
        cp {LEG_ROWS}
        jr nz, .row
        ret

; place: A = a key's bit (a 1), C = its row: the key's place on the screen
; into cell, $1800 + 32 x line + column. Keeps C, DE, HL
place:  push hl
        ld b, {LEG_COL + 14}             ; bit 0's column; bit 7's is {LEG_COL}
.bit:   rrca
        jr c, .col
        dec b
        dec b
        jr .bit
.col:   ld a, c                 ; the line: {LEG_TOP} + 2 x row
        add a, a
        add a, {LEG_TOP}
        ld h, 0
        ld l, a
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        ld a, b
        add a, l
        ld l, a
        ld a, h
        add a, $18
        ld h, a
        ld (cell), hl
        pop hl
        ret
"""
    say = """; The BIOS's interrupt reads the keyboard every third frame and puts the
; characters of the keys in its buffer. The program reads rows 0 to 5 from
; the ports every frame, keeps the place of the last key gone down, and
; prints each character the BIOS gives in that key's place.
"""
    return (head("legend", "the keys as the BIOS types them") + LEGEND_RAM + say +
            tidy(body + SCAN + PRINT) +
            "names:                          ; 24 rows of 32\n" + db_rows(page(legend_texts()), 16) +
            boxes_data() + CART_END)


# ------------------------------------------------------------------ snsmat.asm
SNS_LINES = [(3, "PORTS"), (5, "SNSMAT"), (7, "NEWKEY")]
SNS_BOX, SNS_HEX = 9, 19


def snsmat_texts():
    t = [(1, 0, "row 8"), (1, SNS_BOX, "76543210")]
    for row, label in SNS_LINES:
        t += [(row, 0, label), (row, SNS_BOX, [BOX_EMPTY] * 8), (row, SNS_HEX, "FF")]
    return t


SNSMAT_RAM = """byport  EQU VARS                ; row 8, from the ports
bybios  EQU VARS + 1            ; from SNSMAT
bycopy  EQU VARS + 2            ; from NEWKEY
iff     EQU VARS + 3            ; after SNSMAT: 4 if the interrupts are on
"""


def snsmat():
    show = ""
    for (row, _), var in zip(SNS_LINES, ("byport", "bybios", "bycopy")):
        show += f"""        ld d, {row}
        ld e, {SNS_BOX}
        call at
        ld a, ({var})
        call cells
        ld e, {SNS_HEX}
        call at
        ld a, ({var})
        call hex
"""
    body = setup(TEXT_REGS) + """        im 1                    ; the interrupt: the BIOS's routine at $0038
        VDP_REG 1, $E0          ; the display on, and the frame's signal
main:   ei
        halt                    ; the frame, and the BIOS's interrupt routine
        di
row8:   in a, (PPI_C)           ; 12  row 8 from the ports
        and $F0                 ;  8
        or 8                    ;  8
        out (PPI_C), a          ; 12
        in a, (PPI_B)           ; 12
        ld (byport), a
bios:   ld a, 8                 ;  8  row 8 from the BIOS
        call SNSMAT             ; 18 + the routine
sbios:  ld (bybios), a
        ld a, i                 ; P/V: the interrupts on or off (chapter 17)
        ld a, 0
        jp po, .off
        ld a, 4
.off:   ld (iff), a
        di
copy:   ld a, (NEWKEY + 8)      ; 14  row 8 from the BIOS's copy
        ld (bycopy), a
stored:
""" + show + """        jr main
"""
    say = """; Row 8 of the keyboard read three ways every frame: from the ports, with the
; BIOS's SNSMAT, and from NEWKEY + 8, the copy the BIOS's interrupt keeps.
"""
    return (head("snsmat", "row 8, three ways") + SNSMAT_RAM + say +
            tidy(body + PRINT) +
            "names:                          ; 24 rows of 32\n" + db_rows(page(snsmat_texts()), 16) +
            "shapes:                         ; codes 0 to 127\n" + db_rows(own_shapes(), 16) +
            CART_END)


# ------------------------------------------------------------------ define.asm
ACTIONS = ["UP", "DOWN", "LEFT", "RIGHT", "FIRE"]
ACT_TOP, ACT_STEP, MARK_COL, ACT_COL, NAME_COL = 3, 2, 1, 3, 10
START = (120, 112)          # the figure's X and Y when the game begins
FIRE_COLOUR, COLOUR = DARK_BLUE, BLACK


def define_texts():
    t = [(1, 0, "Press a key for each")]
    for k, a in enumerate(ACTIONS):
        t.append((ACT_TOP + ACT_STEP * k, ACT_COL, a))
    return t


DEFINE_RAM = """ticks   EQU VARS                ; frames counted by isr
rows    EQU VARS + 16           ; the matrix: 11 bytes
keys    EQU VARS + 32           ; the five keys: a row and a mask each
spr     EQU VARS + 48           ; the figure: Y, X, pattern, colour
index   EQU VARS + 52           ; the key chosen: 8 x row + bit
"""


def define():
    body = setup(SPRITE_REGS, sprite=True) + im2("isr") + f"""        VDP_REG 1, $E2          ; the display on, the signal, sprites of 16 x 16
        in a, (VDP_CTRL)
        ld b, 0                 ; action 0: UP
ask:    push bc
        ld a, b                 ; the mark at the action asked for
        add a, a
        add a, {ACT_TOP}
        ld d, a
        ld e, {MARK_COL}
        call at
        ld a, '>'
        out (VDP_DATA), a
again:  call choose             ; D = the row, E = the mask
        pop hl                  ; H: the action
        push hl
        ld a, h
        or a
        jr z, .new              ; the first: nothing to compare
        ld b, h
        ld hl, keys
.same:  ld a, (hl)              ; a key taken already?
        inc hl
        cp d
        jr nz, .next
        ld a, (hl)
        cp e
        jr z, again             ; taken: wait for another
.next:  inc hl
        djnz .same
.new:   pop bc
        push bc
        ld a, b                 ; keys + 2 x action: the row and the mask
        add a, a
        ld hl, keys
        add a, l
        ld l, a
        ld (hl), d
        inc hl
        ld (hl), e
taken:  ld a, (index)            ; the name: names6 + 6 x (8 x row + bit)
        ld l, a
        ld h, 0
        add hl, hl
        ld e, l
        ld d, h
        add hl, hl
        add hl, de
        ld de, names6
        add hl, de
        pop bc
        push bc
        push hl
        ld a, b
        add a, a
        add a, {ACT_TOP}
        ld d, a
        ld e, {MARK_COL}
        call at
        ld a, ' '               ; the mark off
        out (VDP_DATA), a
        ld e, {NAME_COL}
        call at
        pop hl
        ld b, {NAME_LEN}
.name:  ld a, (hl)
        out (VDP_DATA), a
        inc hl
        djnz .name
        pop bc
        inc b
        ld a, b
        cp {len(ACTIONS)}
        jr nz, ask
        ld hl, spr              ; the game: the figure at its start
        ld (hl), {START[1]}
        inc hl
        ld (hl), {START[0]}
        inc hl
        ld (hl), 0
        inc hl
        ld (hl), {COLOUR}
play:   call frame
        VRAM_WRITE $1B00        ; the figure, in the lines not drawn
        ld hl, spr
        ld b, 4
        ld c, VDP_DATA
        otir
        ld a, $D0
        out (VDP_DATA), a
        ld hl, rows
        ld b, {ROWS}
        call scan
logic:  ld ix, spr
        ld hl, keys             ; UP
        call held
        jr nz, .down
        dec (ix + 0)
.down:  ld hl, keys + 2
        call held
        jr nz, .left
        inc (ix + 0)
.left:  ld hl, keys + 4
        call held
        jr nz, .right
        dec (ix + 1)
.right: ld hl, keys + 6
        call held
        jr nz, .fire
        inc (ix + 1)
.fire:  ld hl, keys + 8
        call held
        ld a, {COLOUR}
        jr nz, .colour
        ld a, {FIRE_COLOUR}
.colour:
        ld (ix + 3), a
        jr play

; held: HL = an action's row and mask; Z if its key is held down. Uses A, DE, HL
held:   ld a, (hl)              ; the row
        inc hl
        ld e, (hl)              ; the mask
        ld hl, rows
        add a, l
        ld l, a
        ld a, (hl)              ; the row's keys
        and e                   ; 0: held
        ret

; frame: wait for the next frame, then the interrupts off
frame:  ei
        halt
        di
        ret

; anykey: the 11 rows into rows; Z if no key is held. Uses A, B, C, HL
anykey: ld hl, rows
        ld b, {ROWS}
        call scan
        ld hl, rows
        ld b, {ROWS}
        ld a, $FF
.and:   and (hl)
        inc hl
        djnz .and
        cp $FF
        ret

; choose: every key up, then one down: D = its row, E = its mask, and index
; (in the first row with a key held, the lowest). Uses A, B, C, HL
choose: call frame
        call anykey
        jr nz, choose           ; something still held: wait
.wait:  call frame
        call anykey
        jr z, .wait             ; nothing yet
        ld hl, rows
        ld d, 0
.row:   ld a, (hl)
        cp $FF
        jr nz, .bit
        inc hl
        inc d
        jr .row
.bit:   ld e, 1
        ld c, 0
.find:  rrca
        jr nc, .got             ; a 0: this one
        sla e
        inc c
        jr .find
.got:   ld a, d
        add a, a
        add a, a
        add a, a
        add a, c
        ld (index), a
        ret
"""
    say = """; Five keys chosen by the player: for each action, every key up, then the
; first one down, kept as its row and mask; a key taken already is refused.
; Then a figure moved with them: a pixel a frame, dark blue while FIRE is held.
"""
    names6 = []
    for n in NAMES:
        names6 += [ord(ch) for ch in n.ljust(NAME_LEN)]
    return (head("define", "keys the player chooses") + DEFINE_RAM + IM2 + say +
            tidy(body + SCAN + ISR + PRINT) +
            "names:                          ; 24 rows of 32\n" + db_rows(page(define_texts()), 16) +
            "shapes:                         ; codes 0 to 127\n" + db_rows(own_shapes(), 16) +
            "figure:                         ; chapter 26's figure\n" + db_rows(FIGURE, 16) +
            "names6:                         ; the 88 keys' names, 6 letters each\n" +
            db_rows(names6, 12) + CART_END)


# ------------------------------------------------------------------ the keys pressed
def down(f, row, mask, frames):
    return {f: f"keymatrixdown {row} 0x{mask:02X}", f + frames: f"keymatrixup {row} 0x{mask:02X}"}


def merge(*evs):
    out = {}
    for ev in evs:
        for f, cmd in ev.items():
            out[f] = (out[f] + "; " + cmd) if f in out else cmd
    return out


MATRIX_FROM, MATRIX_EVERY, MATRIX_HOLD = 20, 3, 2      # every key alone
COMBOS = [                                  # (frame, held for, keys)
    (290, 4, ["LEFT", "UP"]),               # two keys of one row
    (296, 4, ["SHIFT", "A"]),               # two of two rows
    (302, 6, ["RIGHT", "SPACE", "S"]),      # three keys and, with ghosting, a fourth: Z
]
MATRIX_FRAMES = 312


def matrix_events():
    evs = [down(MATRIX_FROM + MATRIX_EVERY * k, k // 8, 1 << (k % 8), MATRIX_HOLD)
           for k in range(8 * ROWS)]
    for f, n, names in COMBOS:
        for name in names:
            evs.append(down(f, *key(name), n))
    return merge(*evs)


LEGEND_FROM, LEGEND_EVERY, LEGEND_HOLD = 150, 8, 4      # after C-BIOS's first 127 frames
LEGEND_FRAMES = LEGEND_FROM + LEGEND_EVERY * 8 * LEG_ROWS + 8


def legend_events():
    return merge(*[down(LEGEND_FROM + LEGEND_EVERY * k, k // 8, 1 << (k % 8), LEGEND_HOLD)
                   for k in range(8 * LEG_ROWS)])


TAPS = [(150, 1), (160, 1), (170, 1), (180, 2), (190, 2), (200, 2),
        (210, 3), (220, 3), (230, 3), (240, 20)]           # SPACE: (frame, frames held)
SNSMAT_FRAMES = 270


def snsmat_events():
    return merge(*[down(f, *key("SPACE"), n) for f, n in TAPS])


CHOICES = [(30, "Q"), (40, "Q"), (50, "A"), (60, "O"), (70, "P"), (80, "SPACE")]  # Q twice
CHOICE_HOLD = 4
PLAY = [(100, 40, ["P"]), (140, 20, ["Q"]), (160, 20, ["Q", "O"]), (180, 10, ["SPACE"]),
        (190, 20, ["A", "P", "SPACE"])]                      # (frame, frames held, keys)
DEFINE_FRAMES = 220


def define_events():
    evs = [down(f, *key(n), CHOICE_HOLD) for f, n in CHOICES]
    for f, n, names in PLAY:
        for name in names:
            evs.append(down(f, *key(name), n))
    return merge(*evs)


ROWONLY_FRAMES = 40


def rowonly_events():
    return merge(down(20, *key("Q"), 10))


EVENTS = {"matrix": matrix_events, "legend": legend_events, "snsmat": snsmat_events,
          "define": define_events, "rowonly": rowonly_events}


def write_events(name):
    ev = EVENTS[name]()
    lines = [f"# {name}.events -- chapter 34: the keys {name}.rom is given, generated by gen34.py",
             "# frame (from INIT) and openMSX command; keymatrixdown ROW MASK holds keys down"]
    lines += [f"{f} {cmd}" for f, cmd in sorted(ev.items())]
    with open(os.path.join(HERE, f"{name}.events"), "w") as f:
        f.write("\n".join(lines) + "\n")


PROGRAMS = {"matrix": matrix, "legend": legend, "snsmat": snsmat, "define": define,
            "rowonly": lambda: matrix("rowonly", SCAN_ROW_ONLY)}


def main():
    for name, make in PROGRAMS.items():
        with open(os.path.join(HERE, f"{name}.asm"), "w") as f:
            f.write(make())
        write_events(name)
    print(" ".join(f"{n}.asm" for n in PROGRAMS))


if __name__ == "__main__":
    main()
