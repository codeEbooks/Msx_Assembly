#!/usr/bin/env python3
"""gen09.py - the programs of chapter 9.

    python3 gen09.py && ./build.sh

    cost.asm       one of each arithmetic instruction, timed by the debugger.
    hist.asm       every sum and difference of two bytes: ADD A,E, ADC A,E
                   with the carry set, SUB E and SBC A,E with the carry set,
                   each for all 65,536 pairs, and how many times each value
                   of F came out. The counters are in the RAM.
    neg.asm        NEG on every value of A.
    times10.asm    HL x 10 from ADD HL,HL and ADD HL,DE alone.
    add32.asm      thirty-two-bit sums and differences, a byte at a time with
                   ADC and SBC, printed on the screen (figure 9.1).
    hl16.asm       ADD HL,DE, ADC HL,DE and SBC HL,DE on chosen pairs, and
                   the sixteen-bit comparison OR A, SBC HL,DE, ADD HL,DE; the
                   console stopped after the first (listing 9.3).
    stale.asm      WHERE IT BREAKS: SBC HL,DE with a carry left over from a
                   CP before it.
    widen.asm      a signed byte added to a sixteen-bit number, and the same
                   byte added as if it were unsigned.
    daa.asm        DAA on every value of A, from every mix of N, H and C:
                   2,048 cases.
    score.asm      a score kept in BCD, 37 points a frame, next to the same
                   total kept in binary, and both turned into digits
                   (figure 9.2).

Every program keeps what it finds in the RAM, from $C000: the cartridge is
ROM (chapter 8). build.sh assembles with --syntax=bF (chapter 8).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
from asmparts import HEAD, TAIL, TEXT_PAGE, SHOW_PAGE, library  # noqa: E402

RESULTS = "RESULTS EQU RAM_START          ; what the program found: the debugger reads it here\n"
TABLE = 0xD000                      # the big tables: counters, DAA, NEG


def head(name, what):
    return HEAD.format(name=name, chapter=9, what=what)


def cart(name, what, body, after="", results=True):
    """a cartridge that runs `body` with the interrupts off and stops"""
    return head(name, what) + (RESULTS if results else "") + f"""init:   di
        ld sp, SYS_AREA
{body}stop:   jr stop
{after}""" + TAIL


# ---------------------------------------------------------------- cost.asm
COST = ["add a,b", "adc a,(hl)", "sub $12", "daa", "neg", "add hl,de",
        "adc hl,de", "sbc hl,de", "add ix,de", "inc hl"]


def cost():
    body = "".join(f"t{k}:     {i}\n" for k, i in enumerate(COST)) + f"t{len(COST)}:\n"
    return cart("cost", "one of each arithmetic instruction", """        ld hl, value            ; a byte of the cartridge, to read
        ld de, $1234
        ld ix, $5678
""" + body, after="value:  db $21\n", results=False)


# ---------------------------------------------------------------- hist.asm
# (the name, how the sum is done)
HIST_OPS = [("add", ["add a, e"]),
            ("adc", ["scf", "adc a, e"]),
            ("sub", ["sub e"]),
            ("sbc", ["scf", "sbc a, e"])]


def hist():
    blocks = []
    for k, (name, code) in enumerate(HIST_OPS):
        page = (TABLE >> 8) + 2 * k
        ops = "".join(f"        {c:<24}; {'the carry in' if c == 'scf' else 'the operation counted'}\n"
                      for c in code)
        blocks.append(f"""; {name}: counters at ${page:02X}00 (low bytes) and ${page + 1:02X}00 (high bytes)
        ld d, 0                 ; D: the first number
{name + '1:':<8}ld e, 0                 ; E: the second
{name + '2:':<8}ld a, d
{ops}        push af
        pop bc                  ; C = F
        {f'ld h, ${page:02X}':<24}; the page of low bytes
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
    return cart("hist", "every sum of two bytes, counted by F", f"""COUNTS  EQU ${TABLE:04X}             ; in the RAM: 256 counters of two bytes for each operation
        ld hl, COUNTS
        ld de, COUNTS + 1
        ld (hl), 0
        ld bc, {2 * 256 * len(HIST_OPS)} - 1
        ldir                    ; every counter to 0 (LDIR: chapter 13)
""" + "".join(blocks), results=False)


# ----------------------------------------------------------------- neg.asm
def neg():
    return cart("neg", "NEG on every value of A", f"""TABLE   EQU ${TABLE:04X}             ; A and F after NEG, two bytes a case
        ld hl, TABLE
        ld b, 0                 ; B: A before NEG, 0 to 255
next:   ld a, b
        neg                     ; A = 0 - A
        push af
        pop de                  ; D = A after, E = F after
        ld (hl), d
        inc hl
        ld (hl), e
        inc hl
        inc b
        jr nz, next
""", results=False)


# ------------------------------------------------------------- times10.asm
TIMES10 = [0, 1, 1234, 6553, 6554]


def times10():
    body = "".join(f"""        ld hl, {x}
{f'c{k}:':<8}call times10
        {f'ld (RESULTS+{4 * k}), hl':<24}; HL after
        ld a, 0
        adc a, 0                ; the carry out of the last ADD HL,HL
        {f'ld (RESULTS+{4 * k + 2}), a':<24}
""" for k, x in enumerate(TIMES10))
    return cart("times10", "HL x 10 with no multiplication", body, after="""
; times10: HL = HL x 10: twice, twice again, plus itself, and twice again
times10:
        ld d, h
        ld e, l                 ; DE = x
        add hl, hl              ; 2x
        add hl, hl              ; 4x
        add hl, de              ; 5x
        add hl, hl              ; 10x
        ret
""")


# --------------------------------------------------------------- add32.asm
# (A, the operation, B), each a 32-bit number
SUMS32 = [(0x000000FF, "+", 0x00000001), (0x0000FFFF, "+", 0x00000001),
          (0x00FFFFFF, "+", 0x00000001), (0xFFFFFFFF, "+", 0x00000001),
          (0x12345678, "+", 0x9ABCDEF0), (0x7FFFFFFF, "+", 0x00000001),
          (0x00010000, "-", 0x00000001), (0x00000000, "-", 0x00000001),
          (0xACF13568, "-", 0x9ABCDEF0)]
SUM_ROW0, SUM_STEP = 1, 2           # the first line, and the rows between lines
CARRY_COL = 27


def add32():
    body = []
    for k, (a, op, b) in enumerate(SUMS32):
        row = SUM_ROW0 + SUM_STEP * k
        body.append(f"""        ld hl, a{k}
        ld de, acc
        ld bc, 4
        ldir                    ; acc = A
        ld de, acc
        ld hl, b{k}
{f'c{k}:':<8}{'call add32' if op == '+' else 'call sub32':<24}; acc = A {op} B
        ld a, 0
        adc a, 0                ; A = the carry out of the top byte
        ld (cy), a
        ld b, {row}
        ld c, 0
        ld hl, a{k}
        call put32
        ld a, '{op}'
        call putc
        inc c
        ld hl, b{k}
        call put32
        ld a, '='
        call putc
        inc c
        ld hl, acc
        call put32
        ld c, {CARRY_COL}
        ld hl, ctext
        call puts
        ld a, (cy)
        add a, '0'
        call putc
""")
    data = "".join(f"""a{k}:     dd ${a:08X}
b{k}:     dd ${b:08X}
""" for k, (a, _, b) in enumerate(SUMS32))
    return head("add32", "32-bit sums, a byte at a time") + """acc     EQU RAM_START + $10     ; four bytes of RAM: the sum
cy      EQU RAM_START + $14     ; the carry out of it
; Numbers of 32 bits, four bytes each, low byte first. ADC carries from one
; byte into the next, SBC borrows, and the carry out of the top byte is the
; carry of the whole sum (figure 9.1).
""" + TEXT_PAGE + "".join(body) + SHOW_PAGE + """
; add32: the four bytes at DE = those at DE + those at HL, low byte first.
;        The carry out of the top byte is left in the carry flag.
add32:  ld b, 4
        or a                    ; nothing to carry into the lowest byte
ad1:    ld a, (de)
        adc a, (hl)             ; this byte, and the carry from the last
        ld (de), a
        inc de
        inc hl                  ; INC of a pair touches no flag ...
        djnz ad1                ; ... and DJNZ none either
        ret

; sub32: the four bytes at DE = those at DE - those at HL, the same way
sub32:  ld b, 4
        or a                    ; nothing to borrow into the lowest byte
sb1:    ld a, (de)
        sbc a, (hl)             ; this byte, less the borrow from the last
        ld (de), a
        inc de
        inc hl
        djnz sb1
        ret

; put32: the four bytes at HL, printed as eight hexadecimal digits, the top
;        byte first. B = row, C = column; C moves on by 8.
put32:  push hl
        inc hl
        inc hl
        inc hl                  ; the top byte
        ld e, 4
p32:    ld a, (hl)
        call puthex
        dec hl
        dec e
        jr nz, p32
        pop hl
        ret

ctext:  db "C=", 0
""" + data + library() + TAIL


# ---------------------------------------------------------------- hl16.asm
# (the instructions, HL, DE, F before)
HL16 = [(["add hl,de"], 0xFFFF, 0x0001, 0x00),
        (["add hl,de"], 0x0FFF, 0x0001, 0x00),
        (["add hl,de"], 0x0FFF, 0x0001, 0xFF),
        (["adc hl,de"], 0xFFFF, 0x0001, 0x00),
        (["adc hl,de"], 0x7FFF, 0x0001, 0x00),
        (["sbc hl,de"], 0x1000, 0x0001, 0x00),
        (["sbc hl,de"], 0x1000, 0x0001, 0x01),
        (["sbc hl,de"], 0x0000, 0x0001, 0x00),
        (["sbc hl,de"], 0x1234, 0x1234, 0x00),
        (["or a", "sbc hl,de", "add hl,de"], 0x1234, 0x1235, 0x00),
        (["or a", "sbc hl,de", "add hl,de"], 0x1234, 0x1234, 0x00),
        (["or a", "sbc hl,de", "add hl,de"], 0x1235, 0x1234, 0x00)]


def hl16():
    body = []
    for k, (code, hl, de, f) in enumerate(HL16):
        ops = "".join(f"        {c.replace(',', ', ')}\n" for c in code)
        if k == 0:
            ops += "first:                          ; the console stops here: listing 9.3\n"
        body.append(f"""        ld bc, ${f:04X}
        push bc
        pop af                  ; F = ${f:02X}
        ld hl, ${hl:04X}
        ld de, ${de:04X}
{ops}        {f'ld (RESULTS+{4 * k}), hl':<24}; HL after
        push af
        pop bc
        ld a, c
        {f'ld (RESULTS+{4 * k + 2}), a':<24}; F after
""")
    return cart("hl16", "sixteen-bit sums from a chosen F", "".join(body))


# --------------------------------------------------------------- stale.asm
def stale():
    return cart("stale", "WHERE IT BREAKS: SBC HL,DE and a carry left over", """        ld a, 2
        cp 3                    ; 2 < 3: the carry is set
        ld hl, $1000
        ld de, $0001
        sbc hl, de              ; $1000 - $0001 - carry
p1:     or a                    ; the carry cleared first
        ld hl, $1000
        sbc hl, de              ; $1000 - $0001
p2:
""", results=False)


# --------------------------------------------------------------- widen.asm
# (a position, a velocity from -128 to 127)
WIDEN = [(0x1000, 3), (0x1000, -3), (0x10FF, 1), (0x1000, -128), (0x0000, -1)]


def widen():
    body = "".join(f"""        ld hl, ${p:04X}
        ld a, {v}
        call move
        {f'ld (RESULTS+{4 * k}), hl':<24}; the new position
        ld hl, ${p:04X}
        ld a, {v}
        ld e, a
        ld d, 0                 ; the velocity taken as unsigned
        add hl, de
        {f'ld (RESULTS+{4 * k + 2}), hl':<24}; and the wrong position
""" for k, (p, v) in enumerate(WIDEN))
    return cart("widen", "a signed byte added to sixteen bits", body, after="""
; move: HL = HL + A, with A taken as signed (-128 to 127)
move:   ld e, a                 ; E: the velocity
        add a, a                ; its sign bit, bit 7, into the carry
        sbc a, a                ; 0 - carry: $00, or $FF if it was negative
        ld d, a                 ; DE: the velocity in sixteen bits
        add hl, de
        ret
""")


# ----------------------------------------------------------------- daa.asm
# F before DAA: every mix of N (bit 1), H (bit 4) and C (bit 0), all else 0
DAA_FLAGS = [0x00, 0x01, 0x10, 0x11, 0x02, 0x03, 0x12, 0x13]


def daa():
    return cart("daa", "DAA in all 2,048 cases", f"""TABLE   EQU ${TABLE:04X}             ; A and F after DAA, two bytes a case
        ld hl, TABLE
        ld ix, before
nextf:  ld c, (ix+0)            ; C: F before DAA
        ld b, 0                 ; B: A before DAA, 0 to 255
nexta:  push bc
        pop af                  ; A = B, F = C
        daa
        push af
        pop de                  ; D = A after, E = F after
        ld (hl), d
        inc hl
        ld (hl), e
        inc hl
        inc b
        jr nz, nexta
        inc ix
        ld a, (ix+0)
        cp $FF                  ; the end of the list
        jr nz, nextf
""", after="before: db " + ", ".join(f"${f:02X}" for f in DAA_FLAGS) + ", $FF\n", results=False)


# --------------------------------------------------------------- score.asm
POINTS = 37                 # a frame, in decimal: $37 in BCD
FRAMES = 20
SCORE_ROW0 = 2              # the row of the first score
COL_BCD, COL_HEX, COL_DEC = 1, 10, 17


def score():
    heads = "".join(f"""        ld b, 0
        ld c, {col}
        ld hl, h{k}
        call puts
""" for k, col in enumerate((COL_BCD, COL_HEX, COL_DEC)))
    return head("score", "a score in BCD and in binary") + f"""row     EQU RAM_START + $10     ; the row to print on
score   EQU RAM_START + $11     ; six BCD digits, the first two first
total   EQU RAM_START + $14     ; the same points in binary
txt     EQU RAM_START + $16     ; six characters and a 0
txt2    EQU RAM_START + $1D     ; five characters and a 0
; {POINTS} points a frame, added to a score of six BCD digits and to a binary
; total, each turned into digits and printed on the next row: the BCD score,
; the binary total in hexadecimal, and the binary total in decimal (figure
; 9.2). The display stays off while the frames go by, and comes on at the end.
""" + TEXT_PAGE + heads + f"""        xor a
        ld (score), a
        ld (score + 1), a
        ld (score + 2), a
        ld (txt + 6), a
        ld (txt2 + 5), a        ; the ends of the two texts
        ld h, a
        ld l, a
        ld (total), hl
        ld a, {SCORE_ROW0}
        ld (row), a
        VDP_REG 1, $A0          ; display still off, frame interrupt on
        im 1
        ei
frame:  halt                    ; one frame, {POINTS} points (C-BIOS's routine runs)
bcdsum: ld hl, score + 2        ; the last two digits
        ld a, (hl)
        add a, ${POINTS:02d}              ; {POINTS} points, written in BCD
        daa                     ; two decimal digits again, and a carry
        ld (hl), a
        dec hl                  ; DEC of a pair keeps the carry
        ld a, (hl)
        adc a, 0                ; the carry into the next two digits
        daa
        ld (hl), a
        dec hl
        ld a, (hl)
        adc a, 0                ; and into the first two
        daa
        ld (hl), a
binsum: ld hl, (total)
        ld de, {POINTS}
        add hl, de
        ld (total), hl          ; the same points, counted in binary
t1:     call bcdtxt             ; the BCD score as text
t2:     call bintxt             ; the binary total as text
t3:     ld a, (row)
        ld b, a
        ld c, {COL_BCD}
        ld hl, txt
        call puts
        ld c, {COL_HEX}
        ld a, (total + 1)
        call puthex
        ld a, (total)
        call puthex
        ld c, {COL_DEC}
        ld hl, txt2
        call puts
        ld a, (row)
        inc a
        ld (row), a
        cp {SCORE_ROW0 + FRAMES}
        jr nz, frame
        di
""" + SHOW_PAGE + f"""
; bcdtxt: the six BCD digits at score, into six characters at txt. Each
;         digit is four bits of a byte: no arithmetic at all.
bcdtxt: ld hl, score
        ld de, txt
        ld b, 3
bt1:    ld a, (hl)
        rrca
        rrca
        rrca
        rrca                    ; the high four bits first
        and %00001111
        add a, '0'
        ld (de), a
        inc de
        ld a, (hl)
        and %00001111           ; then the low four bits
        add a, '0'
        ld (de), a
        inc de
        inc hl
        djnz bt1
        ret

; bintxt: the binary total (0-65535) into five characters at txt2, by
;         counting how many times each power of ten goes into it
bintxt: ld hl, (total)
        ld de, txt2
        ld bc, -10000
        call digit
        ld bc, -1000
        call digit
        ld bc, -100
        call digit
        ld bc, -10
        call digit
        ld a, l                 ; what is left is the last digit
        add a, '0'
        ld (de), a
        ret
digit:  ld a, '0' - 1
dg1:    inc a
        add hl, bc              ; take the power of ten away once more ...
        jr c, dg1               ; ... as long as it went
        sbc hl, bc              ; one time too many: put it back
        ld (de), a
        inc de
        ret

h0:     db "BCD", 0
h1:     db "HEX", 0
h2:     db "DECIMAL", 0
""" + library() + TAIL


def sources():
    return {"cost.asm": cost(), "hist.asm": hist(), "neg.asm": neg(), "times10.asm": times10(),
            "add32.asm": add32(), "hl16.asm": hl16(), "stale.asm": stale(),
            "widen.asm": widen(), "daa.asm": daa(), "score.asm": score()}


CARTS = [n[:-4] for n in sources()]


def main():
    files = sources()
    for name, text in files.items():
        with open(os.path.join(HERE, name), "w") as f:
            f.write(text)
    print(len(files), "sources written")


if __name__ == "__main__":
    main()
