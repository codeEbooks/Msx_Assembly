#!/usr/bin/env python3
"""gen02.py - the programs of chapter 2.

    python3 gen02.py && ./build.sh

    count.asm      numbers in decimal, hexadecimal and binary: 0 to 15
                   counted by INC A, then sixteen chosen values. The program
                   works out every digit from the byte, and prints it in the
                   BIOS's own characters.
    arith.asm      the processor adds and subtracts pairs of bytes, and the
                   program shows each result as 8 bits, in hexadecimal, as an
                   unsigned and as a signed number, with the carry and
                   overflow flags the processor set. The last line stores a
                   16-bit number and reads its two bytes back.
    addr_hex.asm   32 filled boxes into the name table at $1800: the top row
                   of the screen. Below them, characters $E0 to $EF as they are.
    addr_dec.asm   WHERE IT BREAKS: the same program with the $ left out.
                   1800 is a different number, and the bytes go somewhere else:
                   four of the sixteen characters below change shape.
    notation.asm   one byte written six ways, and a 16-bit number stored.
                   It is not run: the assembler's listing is the result.
    fields.asm     VDP status bytes taken apart with AND and rotations: the
                   frame flag, the fifth-sprite flag, the collision flag and
                   a sprite number, four numbers in one byte.
    shifts.asm     SLA A doubles, SRL A halves, and the bit that falls off
                   goes into the carry flag.
    chars.asm      the characters with codes 32 to 255, by code: letters
                   are numbers too.
    fixed.asm      fractions of a pixel with whole numbers: a 16-bit
                   position whose high byte is the pixel.

The routines come from tools/asmparts.py. Every number the programs print is
worked out by the Z80 when it runs, not by this generator: the generator
only writes the questions.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
from asmparts import (HEAD, TAIL, TEXT_PAGE, SHOW_PAGE, library, PUTDEC, FATBITS,  # noqa: E402
                      BOX_FULL)


def head(name, what):
    return HEAD.format(name=name, chapter=2, what=what)


# the right-hand column of count.asm: numbers worth looking at in binary
PICKS = [16, 17, 31, 32, 63, 64, 100, 127, 128, 129, 170, 192, 200, 240, 254, 255]
COUNT_ROW = 3               # first line of numbers; the headings go above
COUNT_COLS = (0, 17)        # the two columns of the table


def count():
    heads = "".join(f"""        ld c, {c0}
        ld hl, hd
        call puts
""" for c0 in COUNT_COLS)
    return head("count", "numbers in three notations") + TEXT_PAGE + f"""        ld b, {COUNT_ROW - 2}
{heads}        xor a                   ; the left column: 0, 1, 2 ... 15
        ld b, {COUNT_ROW}
left:   ld c, {COUNT_COLS[0]}
        call show
        inc a
        inc b
        cp 16
        jr nz, left
        ld ix, picks            ; the right column, from the table
        ld b, {COUNT_ROW}
right:  ld c, {COUNT_COLS[1]}
        ld a, (ix+0)
        call show
        inc ix
        inc b
        ld a, b
        cp {COUNT_ROW + len(PICKS)}
        jr nz, right
""" + SHOW_PAGE + """
; show: A = the number: decimal, space, hexadecimal, space, 8 bits. Keeps A.
show:   push af
        call putdec
        inc c
        pop af
        push af
        call puthex
        inc c
        pop af
        push af
        call fatbits
        pop af
        ret

hd:     db "dec hex bits", 0
picks:  db """ + ", ".join(str(p) for p in PICKS) + "\n" + library(PUTDEC, FATBITS) + TAIL


# the questions the processor is asked: (as printed, a, b, operation)
SUMS = [("3+5", 3, 5, "add"), ("200+100", 200, 100, "add"),
        ("255+1", 255, 1, "add"), ("127+1", 127, 1, "add"),
        ("128+128", 128, 128, "add"), ("100-30", 100, 30, "sub"),
        ("5-7", 5, 7, "sub"), ("0-1", 0, 1, "sub")]
ROW0, STEP = 4, 2           # first line of sums, and the spacing
COLS = {"sum": 0, "bits": 8, "hex": 17, "dec": 21, "sgn": 25, "C": 30, "V": 31}
HL_VALUE, STORE_AT = 0x1234, 0xC000


def arith():
    heads = "".join(f"""        ld c, {COLS[k]}
        ld hl, h_{k}
        call puts
""" for k in COLS)
    rows = []
    for i, (text, a, b, op) in enumerate(SUMS):
        r = ROW0 + STEP * i
        rows.append(f"""; {text}
        ld a, {a}
        ld e, {b}
        {"add a, e" if op == "add" else "sub e"}
        push af
        pop hl                  ; H: the result, L: the flags
        ld (result), hl
        ld b, {r}
        ld c, {COLS['sum']}
        ld hl, t{i}
        call puts
        ld c, {COLS['bits']}
        ld a, (result + 1)
        call fatbits
        ld c, {COLS['hex']}
        ld a, (result + 1)
        call puthex
        ld c, {COLS['dec']}
        ld a, (result + 1)
        call putdec
        ld c, {COLS['sgn']}
        ld a, (result + 1)
        call putsgn
        call flags
""")
    texts = "\n".join(f"t{i}:     db \"{t}\", 0" for i, (t, *_) in enumerate(SUMS))
    return head("arith", "eight sums, and a 16-bit number in memory") + f"""result  EQU VARS + 4              ; the result and the flags of the last sum
""" + TEXT_PAGE + f"""        ld b, {ROW0 - STEP}
{heads}""" + "".join(rows) + f"""; a 16-bit number stored in memory, and its two bytes read back
        ld hl, ${HL_VALUE:04X}
        ld (${STORE_AT:04X}), hl
        ld b, {ROW0 + STEP * len(SUMS) + 1}
        ld c, 0
        ld hl, t_hl
        call puts
        ld a, ${HL_VALUE >> 8:02X}
        call puthex
        ld a, ${HL_VALUE & 0xFF:02X}
        call puthex
        ld hl, t_lo
        call puts
        ld a, (${STORE_AT:04X})
        call puthex
        ld hl, t_hi
        call puts
        ld a, (${STORE_AT + 1:04X})
        call puthex
""" + SHOW_PAGE + f"""
; flags: the carry flag (bit 0 of F) and the overflow flag (bit 2), as the
;        letters C and V, or a dash
flags:  ld c, {COLS['C']}
        ld a, (result)
        and %00000001
        ld a, '-'
        jr z, .noc
        ld a, 'C'
.noc:   call putc
        ld c, {COLS['V']}
        ld a, (result)
        and %00000100
        ld a, '-'
        jr z, .nov
        ld a, 'V'
.nov:   jp putc

{texts}
""" + "\n".join(f"h_{k}:{' ' * (6 - len(k))}db \"{k}\", 0" for k in COLS) + f"""
t_hl:   db "HL=$", 0
t_lo:   db "  ${STORE_AT:04X}:", 0
t_hi:   db "  ${STORE_AT + 1:04X}:", 0
""" + library(PUTDEC, FATBITS) + TAIL


WITNESS_ROW, WITNESS_FIRST = 5, 0xE0    # sixteen characters shown as they are


def addr(hexa):
    target = "$1800" if hexa else "1800"
    name = "addr_hex" if hexa else "addr_dec"
    why = ("the name table: the top row of the screen" if hexa else
           "WHERE IT BREAKS: 1800 without the $ is decimal 1800, which is\n"
           "; $0708 -- the shapes of characters 225 to 228")
    return head(name, f"32 filled boxes from VRAM address {target}") + f"""; {why}.
; Both programs also show the characters ${WITNESS_FIRST:02X} to ${WITNESS_FIRST + 15:02X}, as witnesses.
""" + TEXT_PAGE + f"""        ld b, {WITNESS_ROW - 2}
        ld c, 0
        ld hl, wtext
        call puts
        ld b, {WITNESS_ROW}
        ld c, 0
        ld a, ${WITNESS_FIRST:02X}
wit:    call putc               ; (putc keeps A)
        inc c
        inc c
        inc a
        cp ${(WITNESS_FIRST + 16) & 0xFF:02X}
        jr nz, wit
        VRAM_WRITE {target}
        ld b, 32
        ld a, {BOX_FULL}                 ; the filled box
fill:   out (VDP_DATA), a
        djnz fill
""" + SHOW_PAGE + f"""wtext:  db "characters ${WITNESS_FIRST:02X} to ${WITNESS_FIRST + 15:02X}:", 0
""" + library() + TAIL


def notation():
    # the comments are short on purpose: the listing sjasmplus writes puts a
    # long prefix in front of each line, and the book's column holds 82
    return """; notation.asm - one byte, written six ways, and a 16-bit number.
; Not a program: assemble it with --lst and read the listing.
        OUTPUT "notation.bin"
        ORG $4000
        db 255          ; decimal
        db $FF          ; hex, as in this book
        db #FF          ; hex, another prefix
        db 0FFh         ; hex, a suffix
        db 0xFF         ; hex, as in C
        db %11111111    ; binary
        dw $1234        ; 16 bits: 2 bytes
        ld hl,$1234     ; an instruction too
"""


STATUS_SHOWN = [0x00, 0x80, 0x44, 0xC4, 0xA0, 0xE7, 0x5F]
FIELD_ROW = 4
FIELD_COLS = {"hex": 0, "bits": 4, "F": 14, "5S": 17, "C": 21, "spr": 24}


def fields():
    heads = "".join(f"""        ld c, {FIELD_COLS[k]}
        ld hl, fh_{k}
        call puts
""" for k in FIELD_COLS)
    return head("fields", "VDP status bytes taken apart") + TEXT_PAGE + f"""        ld b, {FIELD_ROW - 2}
{heads}        ld ix, values
        ld b, {FIELD_ROW}
next:   ld a, (ix+0)
        ld c, {FIELD_COLS['hex']}
        push af
        call puthex
        pop af
        ld c, {FIELD_COLS['bits']}
        push af
        call fatbits
        pop af
        ld c, {FIELD_COLS['F']}
        push af
        rlca                    ; bit 7 into bit 0: the frame flag
        and %00000001
        call hexdig
        pop af
        ld c, {FIELD_COLS['5S']}
        push af
        rlca
        rlca                    ; bit 6 into bit 0: the fifth-sprite flag
        and %00000001
        call hexdig
        pop af
        ld c, {FIELD_COLS['C']}
        push af
        rlca
        rlca
        rlca                    ; bit 5 into bit 0: the collision flag
        and %00000001
        call hexdig
        pop af
        ld c, {FIELD_COLS['spr']}
        and %00011111           ; bits 4-0 as they are: a sprite number
        call putdec
        inc ix
        inc b
        inc b
        ld a, b
        cp {FIELD_ROW + 2 * len(STATUS_SHOWN)}
        jr nz, next
""" + SHOW_PAGE + f"""
values: db {", ".join(f"${v:02X}" for v in STATUS_SHOWN)}
""" + "\n".join(f"fh_{k}:{' ' * (6 - len(k))}db \"{ {'hex': 'hex', 'bits': 'bits', 'F': 'F', '5S': '5S', 'C': 'C', 'spr': 'sprite'}[k] }\", 0"
                for k in FIELD_COLS) + "\n" + library(PUTDEC, FATBITS) + TAIL


SHIFT_START = (13, 200)     # doubled by SLA A, halved by SRL A
SHIFT_ROW = 4
SHIFT_STEPS = 8
SHIFT_COLS = (0, 17)


def shifts():
    return head("shifts", "doubling with SLA A, halving with SRL A") + f"""op      EQU VARS + 4              ; the shift to use: SLA or SRL
col     EQU VARS + 6              ; column, then row
num     EQU VARS + 8
cy      EQU VARS + 9
cnt     EQU VARS + 10
""" + TEXT_PAGE + f"""        ld b, {SHIFT_ROW - 2}
        ld c, {SHIFT_COLS[0]}
        ld hl, h_sla
        call puts
        ld c, {SHIFT_COLS[1]}
        ld hl, h_srl
        call puts
        ld hl, left
        ld (op), hl
        ld a, {SHIFT_START[0]}
        ld c, {SHIFT_COLS[0]}
        call column
        ld hl, right
        ld (op), hl
        ld a, {SHIFT_START[1]}
        ld c, {SHIFT_COLS[1]}
        call column
""" + SHOW_PAGE + f"""
; column: A = the first number, C = the column. Prints it, then shifts it
; {SHIFT_STEPS} times with the routine at (op), printing each result and the
; carry. The number and the carry live in memory: the printing routines use
; every register the loop could have kept them in.
column: ld b, {SHIFT_ROW}
        ld (col), bc            ; C at col, the row at col + 1
        ld (num), a
        xor a
        ld (cy), a              ; no carry before the first shift
        ld a, {SHIFT_STEPS + 1}
        ld (cnt), a
.line:  ld bc, (col)
        ld a, (num)
        call putdec
        inc c
        ld a, (num)
        call fatbits
        inc c
        ld a, (cy)
        or a
        ld a, '-'
        jr z, .flag
        ld a, 'C'
.flag:  call putc
        ld a, (col + 1)
        add a, 2
        ld (col + 1), a         ; two character rows down
        ld a, (num)
        ld hl, (op)
        call jphl               ; shift A, one way or the other
        ld (num), a
        ld a, 0
        rla                     ; the carry flag, as 0 or 1
        ld (cy), a
        ld hl, cnt
        dec (hl)
        jr nz, .line
        ret
jphl:   jp (hl)
left:   sla a                   ; double: bit 7 goes into the carry
        ret
right:  srl a                   ; halve: bit 0 goes into the carry
        ret
h_sla:  db "sla a", 0
h_srl:  db "srl a", 0
""" + library(PUTDEC, FATBITS) + TAIL


CHAR_ROW, CHAR_COL = 2, 8   # the first character; one row of sixteen per line


def chars():
    return head("chars", "the characters with codes 32 to 255") + TEXT_PAGE + f"""        ld a, 32                ; the first code after the control codes
        ld b, {CHAR_ROW}
crow:   ld c, {CHAR_COL}
ccell:  call putc               ; (putc keeps A)
        inc a
        inc c
        ld e, a
        and $0F
        ld a, e
        jr nz, ccell            ; sixteen to a row
        inc b
        or a
        jr nz, crow             ; until the code wraps round to 0
; the low digit above each column
        ld b, {CHAR_ROW - 1}
        ld c, {CHAR_COL}
        xor a
top:    push af
        call hexdig
        pop af
        inc a
        cp 16
        jr nz, top
; the high digit left of each row
        ld b, {CHAR_ROW}
        ld a, 2
side:   ld c, {CHAR_COL - 2}
        push af
        call hexdig
        pop af
        inc b
        inc a
        cp 16
        jr nz, side
""" + SHOW_PAGE + library() + TAIL


FIX_STEPS = (0x0040, 0x00C0, 0x0180)    # a quarter, three quarters, one and a half
FIX_ROW, FIX_N = 4, 9
FIX_COLS = (1, 11, 21)


def fixed():
    return head("fixed", "fractions of a pixel with whole numbers") + f"""col     EQU VARS + 4              ; column, then row
step    EQU VARS + 6
pos     EQU VARS + 8
cnt     EQU VARS + 10
""" + TEXT_PAGE + "".join(f"""        ld b, {FIX_ROW - 2}
        ld c, {c0}
        ld hl, fh
        call puts
        ld de, ${st:04X}
        ld c, {c0}
        call column
""" for c0, st in zip(FIX_COLS, FIX_STEPS)) + SHOW_PAGE + f"""
; column: DE = the step, C = the column. The position starts at 0.
column: ld b, {FIX_ROW}
        ld (col), bc
        ld (step), de
        ld hl, 0
        ld (pos), hl
        ld a, {FIX_N}
        ld (cnt), a
.line:  ld bc, (col)
        ld a, (pos + 1)
        call puthex             ; the high byte: the pixel
        ld a, (pos)
        call puthex             ; the low byte: the fraction
        inc c
        ld a, (pos + 1)
        call putdec             ; the whole part, in decimal
        ld hl, (pos)
        ld de, (step)
        add hl, de              ; sixteen-bit addition: the fraction carries
        ld (pos), hl
        ld a, (col + 1)
        add a, 2
        ld (col + 1), a
        ld hl, cnt
        dec (hl)
        jr nz, .line
        ret
fh:     db "pos   px", 0
""" + library(PUTDEC) + TAIL


def main():
    files = {"count.asm": count(), "arith.asm": arith(), "fields.asm": fields(),
             "shifts.asm": shifts(), "chars.asm": chars(), "fixed.asm": fixed(),
             "addr_hex.asm": addr(True), "addr_dec.asm": addr(False),
             "notation.asm": notation()}
    for name, text in files.items():
        with open(os.path.join(HERE, name), "w") as f:
            f.write(text)
    print(len(files), "sources written")


if __name__ == "__main__":
    main()
