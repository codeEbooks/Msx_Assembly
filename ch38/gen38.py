#!/usr/bin/env python3
"""gen38.py - the programs of chapter 38: slots and memory.

    python3 gen38.py && ./build.sh

    pages.asm    where each page is: port $A8, the BIOS's tables EXPTBL and
                 SLTTBL, the register of every expanded slot read at $FFFF
                 through page 3, and the slot ID of each page (figure 38.1)
    cart32.asm   a cartridge of 32 KB that finds its own slot at INIT, with
                 RSLREG, EXPTBL and SLTTBL, and has the BIOS's ENASLT show it
                 in page 2 as well; then calls a routine in its second half
                 (figure 38.2)
    own32.asm    the same without the BIOS's routines: the slot read from
                 the hardware, and page 2 switched by its own setpage2
    quick32.asm  WHERE IT BREAKS: page 1's primary slot copied into page 2
                 through port $A8 alone, which is right until the cartridge
                 sits in an expanded slot (figure 38.3)
    stay32.asm   WHERE IT BREAKS: no switch at all; the call into the second
                 half lands in whatever page 2 shows (figure 38.3)

The programs print in Graphic I, black ink on white, with the display off,
and then switch it on, the frame interrupt left off; they keep the
interrupts off from INIT on. The four of 32 KB keep their first half for
INIT and the routines, and their second half, from $8000, for `second`, the
routine that prints a line of its own, and the line. build.sh assembles them
with --syntax=bFw.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "tools"))
sys.path.insert(0, os.path.join(REPO, "ch34"))
sys.path.insert(0, os.path.join(REPO, "ch35"))
from asmparts import HEAD, CART_END  # noqa: E402
import gen34  # noqa: E402  (chapter 34: the text screen and its routines)
import gen35  # noqa: E402  (chapter 35: text_tail)
from gen26 import tidy  # noqa: E402  (chapter 26)

EU, JP = "MSXBOOK_EU16", "MSXBOOK_JP16"
EXP_RAM = "MSXBOOK_EU16X"       # slot 3 expanded, the RAM in 3-2
EXPANDER = "MSXBOOK_EU16E"      # a slot expander in slot 1, the cartridge in 1-1
BIG = "MSXBOOK_EU64"            # 64 KB in slot 3 (chapter 3): page 2 is RAM at INIT
MACHINES = [EU, EXP_RAM, EXPANDER, BIG, JP]
TEXT_REGS = gen34.TEXT_REGS
SSLOT = 0xFFFF                  # the secondary slot register of page 3's slot

RAM = """a8      EQU VARS                ; port $A8 as INIT finds it
a8now   EQU VARS + 1            ; and after page 2 is switched
myslot  EQU VARS + 2            ; the cartridge's slot ID
sltwas  EQU VARS + 3            ; SLTTBL for its slot at INIT
sltnow  EQU VARS + 4            ; and after the switch
sum     EQU VARS + 6            ; page 2's 16 KB added up, two bytes
regs    EQU VARS + 8            ; pages.asm: the four secondary registers
ids     EQU VARS + 12           ; pages.asm: the slot ID of each page
SSLOT   EQU $FFFF               ; the secondary slot register, in page 3
"""

# ------------------------------------------------------------------ routines
SUBREG = """
; subreg: A = an expanded primary slot -> A = its secondary slot register,
; read at $FFFF through page 3, which hands it back complemented. The
; interrupts must be off: while page 3 shows that slot the RAM is gone, and
; the stack with it. Uses A, B, C
subreg: rrca                    ;  5
        rrca                    ;  5  the slot into bits 6-7
        ld b, a                 ;  5
        in a, (PPI_A)           ; 12
        ld c, a                 ;  5  the slots as they are
        and $3F                 ;  8
        or b                    ;  5
        out (PPI_A), a          ; 12  page 3 shows the slot: no RAM
        ld a, (SSLOT)           ; 14  its register, complemented
        cpl                     ;  5
        ld b, a                 ;  5
        ld a, c                 ;  5
        out (PPI_A), a          ; 12  page 3 back: the RAM again
        ld a, b                 ;  5
        ret                     ; 11
"""

FIELD = """
; field: A = a byte of four fields of two bits, one a page, B = a page ->
; A = that page's field. Uses A, C
field:  ld c, b
        inc c
.shift: dec c
        jr z, .done
        rrca
        rrca
        jr .shift
.done:  and 3
        ret
"""

PAGEID = """
; pageid: B = a page, 0 to 3 -> A = the slot ID it shows, E000SSPP: the
; primary slot from port $A8 and, if EXPTBL says it is expanded, the
; secondary from the slot's own register. Uses A, C, D, E, HL
pageid: in a, (PPI_A)
        call field              ; page B's primary slot
        ld d, a
        ld hl, EXPTBL
        add a, l
        ld l, a
        ld a, (hl)
        and $80                 ; expanded?
        jr z, .primary
        or d
        ld e, a                 ; 1000 00PP
        ld a, d
        push bc
        call subreg             ; the slot's register
        pop bc
        call field              ; page B's secondary slot
        rlca
        rlca                    ; in bits 2-3
        or e
        ret
.primary: ld a, d
        ret
"""

HERE_BIOS = """
; here: -> A = the slot ID of page 1, where INIT runs: the primary slot from
; RSLREG and, if EXPTBL says it is expanded, the secondary from SLTTBL, the
; BIOS's copy of the slot's register. Uses A, BC, HL
here:   call RSLREG             ; 18  A = port $A8
        rrca                    ;  5
        rrca                    ;  5
        and 3                   ;  8  page 1's primary slot
        ld c, a                 ;  5
        ld b, 0                 ;  8
        ld hl, EXPTBL           ; 11
        add hl, bc              ; 12
        or (hl)                 ;  8  bit 7 if the slot is expanded
        ret p                   ; 12, or 6  it is not: that is the ID
        ld c, a                 ;  5  1000 00PP
        inc hl                  ;  7
        inc hl                  ;  7
        inc hl                  ;  7
        inc hl                  ;  7  SLTTBL, the same slot
        ld a, (hl)              ;  8
        and %00001100           ;  8  page 1's secondary slot
        or c                    ;  5
        ret                     ; 11
"""

HERE_OWN = """
; here: -> A = the slot ID of page 1, where INIT runs: the primary slot from
; port $A8 and, if EXPTBL says it is expanded, the secondary from the
; slot's own register. The interrupts must be off. Uses A, BC, HL
here:   in a, (PPI_A)           ; 12
        rrca                    ;  5
        rrca                    ;  5
        and 3                   ;  8  page 1's primary slot
        ld c, a                 ;  5
        ld b, 0                 ;  8
        ld hl, EXPTBL           ; 11
        add hl, bc              ; 12
        or (hl)                 ;  8  bit 7 if the slot is expanded
        ret p                   ; 12, or 6  it is not: that is the ID
        ld l, a                 ;  5  1000 00PP
        and 3                   ;  8
        call subreg             ; 18  the slot's register
        and %00001100           ;  8  page 1's secondary slot
        or l                    ;  5
        ret                     ; 11
"""

PAGE2 = """
; setpage2: A = a slot ID -> page 2 shows that slot: its primary slot in
; port $A8 and, for an expanded slot, its secondary slot in the slot's
; register, written at $FFFF through page 3 and copied into SLTTBL for the
; BIOS. The interrupts must be off. Uses A, BC, DE, HL
setpage2: ld e, a               ;  5  the slot ID
        and 3                   ;  8
        rrca                    ;  5
        rrca                    ;  5
        ld d, a                 ;  5  the primary slot in bits 6-7
        rrca                    ;  5
        rrca                    ;  5
        ld b, a                 ;  5  and in bits 4-5
        in a, (PPI_A)           ; 12
        ld c, a                 ;  5  the slots as they are
        bit 7, e                ; 10  expanded?
        jr z, .primary          ; 13, or 8
        and $3F                 ;  8
        or d                    ;  5
        out (PPI_A), a          ; 12  page 3 shows the slot: no RAM
        ld a, (SSLOT)           ; 14
        cpl                     ;  5  its register, as it stands
        and %11001111           ;  8  page 2's secondary slot cleared
        ld d, a                 ;  5
        ld a, e                 ;  5
        and %00001100           ;  8  the new one, in bits 2-3
        rlca                    ;  5
        rlca                    ;  5  and in bits 4-5
        or d                    ;  5
        ld (SSLOT), a           ; 14  written
        ld d, a                 ;  5
        ld a, c                 ;  5
        out (PPI_A), a          ; 12  page 3 back: the RAM again
        ld a, e                 ;  5
        and 3                   ;  8
        add a, low SLTTBL       ;  8
        ld l, a                 ;  5
        ld h, high SLTTBL       ;  8
        ld (hl), d              ;  8  SLTTBL for that slot, as the BIOS keeps it
.primary: ld a, c               ;  5
        and %11001111           ;  8  page 2's primary slot cleared
        or b                    ;  5  and set
        out (PPI_A), a          ; 12
        ret                     ; 11
"""

QUICK = """
; quick: page 2 shows page 1's primary slot: port $A8 alone. Uses A, B, C
quick:  in a, (PPI_A)           ; 12
        ld b, a                 ;  5
        and %00001100           ;  8  page 1's primary slot
        add a, a                ;  5
        add a, a                ;  5  moved to page 2's bits
        ld c, a                 ;  5
        ld a, b                 ;  5
        and %11001111           ;  8
        or c                    ;  5
        out (PPI_A), a          ; 12  page 2 = this cartridge, too
        ret                     ; 11
"""

PUTSLOT = """
; putslot: A = a slot ID -> "P", or "P-S" for an expanded slot, from the
; address set. Uses A, B
putslot: ld b, a
        and 3
        add a, '0'
        out (VDP_DATA), a       ; the primary slot
        bit 7, b
        ret z
        ld a, '-'
        out (VDP_DATA), a
        ld a, b
        rrca
        rrca
        and 3
        add a, '0'
        out (VDP_DATA), a       ; the secondary
        ret
"""

SUM2 = """
; sum2: -> HL = page 2's 16 KB, $8000 to $BFFF, added up as bytes, modulo
; 65,536. Uses A, BC, DE, HL
sum2:   ld de, $8000
        ld bc, $4000
        ld hl, 0
.byte:  ld a, (de)
        add a, l
        ld l, a
        jr nc, .next
        inc h
.next:  inc de
        dec bc
        ld a, b
        or c
        jr nz, .byte
        ret
"""

HEX16 = """
; hex16: HL as four hexadecimal digits, from the address set. Uses A, C
hex16:  ld a, h
        call hex
        ld a, l
        jp hex
"""

DISPLAY_ON = """        VDP_REG 1, $C0          ; the display on, no frame interrupt
"""

# ------------------------------------------------------------------ pages.asm
P_ROWS = {"a8": 3, "pages": 5, "slots": 11}
P_COLS = {"a8": 10, "slot": 14, "id": 20, "exp": 8, "slt": 15, "reg": 22}


def pages_texts():
    t = [(1, 0, "pages.asm"), (P_ROWS["a8"], 0, "port $A8"),
         (P_ROWS["pages"], 0, "page  from    slot  ID"),
         (P_ROWS["slots"], 0, "slot  EXPTBL SLTTBL  register")]
    for p in range(4):
        t.append((P_ROWS["pages"] + 1 + p, 1, f"{p}   ${0x4000 * p:04X}"))
        t.append((P_ROWS["slots"] + 1 + p, 1, f"{p}"))
    return t


def pages_program():
    r0, c = P_ROWS, P_COLS
    body = gen34.setup(TEXT_REGS) + f"""        in a, (PPI_A)
        ld (a8), a
        ld b, 0                 ; the register of every expanded slot
.slot:  ld hl, EXPTBL
        ld a, l
        add a, b
        ld l, a
        bit 7, (hl)
        jr z, .snext
        ld a, b
        push bc
        call subreg
        pop bc
        ld hl, regs
        ld e, b
        ld d, 0
        add hl, de
        ld (hl), a
.snext: inc b
        ld a, b
        cp 4
        jr nz, .slot
        ld b, 0                 ; the slot ID of every page
.page:  push bc
        call pageid
        pop bc
        ld hl, ids
        ld e, b
        ld d, 0
        add hl, de
        ld (hl), a
        inc b
        ld a, b
        cp 4
        jr nz, .page
        ld d, {r0['a8']}                 ; port $A8
        ld e, {c['a8']}
        call at
        ld a, (a8)
        call hex
        ld b, 0                 ; each page: its slot, and the ID
.ppr:   ld a, b
        add a, {r0['pages'] + 1}
        ld d, a
        ld e, {c['slot']}
        call at
        ld hl, ids
        ld a, l
        add a, b
        ld l, a
        ld a, (hl)
        push bc
        call putslot
        pop bc
        ld e, {c['id']}
        call at
        ld hl, ids
        ld a, l
        add a, b
        ld l, a
        ld a, (hl)
        call hex
        inc b
        ld a, b
        cp 4
        jr nz, .ppr
        ld b, 0                 ; each slot: EXPTBL, SLTTBL, the register
.spr:   ld a, b
        add a, {r0['slots'] + 1}
        ld d, a
        ld e, {c['exp']}
        call at
        ld hl, EXPTBL
        ld a, l
        add a, b
        ld l, a
        ld a, (hl)
        call hex
        ld e, {c['slt']}
        call at
        ld hl, SLTTBL
        ld a, l
        add a, b
        ld l, a
        ld a, (hl)
        call hex
        ld e, {c['reg']}
        call at
        ld hl, EXPTBL
        ld a, l
        add a, b
        ld l, a
        bit 7, (hl)
        ld a, '-'
        jr nz, .reg
        out (VDP_DATA), a       ; not expanded: no register
        out (VDP_DATA), a
        jr .snx
.reg:   ld hl, regs
        ld a, l
        add a, b
        ld l, a
        ld a, (hl)
        call hex
.snx:   inc b
        ld a, b
        cp 4
        jr nz, .spr
""" + DISPLAY_ON + """.end:   jr .end
"""
    head = HEAD.format(name="pages", chapter=38, what="where each page is")
    return (head + '        INCLUDE "bios.inc"\n' + RAM +
            tidy("init:   di\n        ld sp, SYS_AREA\n" + body[len("init:   di\n        ld sp, SYS_AREA\n"):] +
                 SUBREG + FIELD + PAGEID + PUTSLOT + gen34.PRINT) +
            gen35.text_tail(gen34.page(pages_texts())) + CART_END)


# ------------------------------------------------------------------ the 32 KB cartridges
C_ROWS = {"slot": 3, "a8": 4, "slt": 5, "line": 7, "sum": 9}
C_COLS = {"value": 11, "after": 17, "name": 15}
LINE = "printed by page 2, from $8000"


def cart_texts(name):
    return [(1, 0, f"{name}.asm"), (C_ROWS["slot"], 0, "slot ID"),
            (C_ROWS["a8"], 0, "port $A8"), (C_ROWS["a8"], C_COLS["after"] - 3, "->"),
            (C_ROWS["slt"], 0, "SLTTBL"), (C_ROWS["slt"], C_COLS["after"] - 3, "->"),
            (C_ROWS["sum"], 0, "page 2 sum")]


SWITCH = {
    "cart32": """        call here               ; this cartridge's slot ID
        ld (myslot), a
        call slt                ; SLTTBL for it, at INIT
        ld (sltwas), a
        ld a, (myslot)
        ld h, $80               ; page 2 ...
        call ENASLT             ; ... shows the cartridge too
""",
    "own32": """        call here               ; this cartridge's slot ID
        ld (myslot), a
        call slt                ; SLTTBL for it, at INIT
        ld (sltwas), a
        ld a, (myslot)
        call setpage2           ; page 2 shows the cartridge too
""",
    "quick32": """        call here               ; this cartridge's slot ID, for the screen
        ld (myslot), a
        call slt
        ld (sltwas), a
        call quick              ; WHERE IT BREAKS: port $A8 alone
""",
    "stay32": """        call here               ; this cartridge's slot ID, for the screen
        ld (myslot), a
        call slt
        ld (sltwas), a
                                ; WHERE IT BREAKS: page 2 left as it is
""",
}

SLT = """
; slt: -> A = SLTTBL for the slot in myslot. Uses A, HL
slt:    ld a, (myslot)
        and 3
        add a, low SLTTBL
        ld l, a
        ld h, high SLTTBL
        ld a, (hl)
        ret
"""

SAY = {
    "cart32": "a cartridge of 32 KB, page 2 switched by the BIOS",
    "own32": "a cartridge of 32 KB, page 2 switched by its own routine",
    "quick32": "a cartridge of 32 KB, page 2 switched through port $A8 alone",
    "stay32": "a cartridge of 32 KB that leaves page 2 alone",
}


def cart_program(name):
    r, c = C_ROWS, C_COLS
    body = """init:   di
        ld sp, SYS_AREA
        in a, (PPI_A)           ; the slots as INIT finds them
        ld (a8), a
""" + SWITCH[name] + """        in a, (PPI_A)
        ld (a8now), a
        call slt
        ld (sltnow), a
""" + gen34.setup(TEXT_REGS)[len("init:   di\n        ld sp, SYS_AREA\n"):] + f"""        ld d, {r['slot']}
        ld e, {c['value']}
        call at
        ld a, (myslot)
        call hex
        ld e, {c['name']}
        call at
        ld a, (myslot)
        call putslot
        ld d, {r['a8']}
        ld e, {c['value']}
        call at
        ld a, (a8)
        call hex
        ld e, {c['after']}
        call at
        ld a, (a8now)
        call hex
        ld d, {r['slt']}
        ld e, {c['value']}
        call at
        ld a, (sltwas)
        call hex
        ld e, {c['after']}
        call at
        ld a, (sltnow)
        call hex
""" + DISPLAY_ON + f"""        call second             ; the routine in the second half
        call sum2               ; and page 2 added up
        ld (sum), hl
        ld d, {r['sum']}
        ld e, {c['value']}
        call at
        ld hl, (sum)
        call hex16
.end:   jr .end
"""
    here = HERE_OWN if name == "own32" else HERE_BIOS
    parts = here + SLT
    if name == "own32":
        parts += PAGE2 + SUBREG
    elif name == "quick32":
        parts += QUICK
    parts += PUTSLOT + SUM2 + HEX16 + gen34.PRINT
    second = f"""
; ------------------------------------------------ the second half, page 2
second: ld d, {r['line']}                 ; the line, printed by code that is
        ld e, 0                 ; here, in the second half
        call at
        ld hl, line
        ld b, {len(LINE)}
.char:  ld a, (hl)
        out (VDP_DATA), a
        inc hl
        djnz .char
        ret
line:   db "{LINE}"
"""
    head = HEAD.format(name=name, chapter=38, what=SAY[name])
    return (head + '        INCLUDE "bios.inc"\n' + RAM + tidy(body + parts) +
            gen35.text_tail(gen34.page(cart_texts(name))) +
            "        ASSERT $ <= $8000, the first half is too long\n"
            "        ds $8000 - $, $FF       ; the first half ends at $7FFF\n" +
            tidy(second) +
            "        ASSERT $ <= $C000, the program is longer than the cartridge\n"
            "        ds $C000 - $, 0         ; the rest of the second half: zeros\n")


CARTS = ["cart32", "own32", "quick32", "stay32"]
PROGRAMS = ["pages"] + CARTS


def main():
    with open(os.path.join(HERE, "pages.asm"), "w") as f:
        f.write(pages_program())
    for name in CARTS:
        with open(os.path.join(HERE, f"{name}.asm"), "w") as f:
            f.write(cart_program(name))
    print(" ".join(f"{n}.asm" for n in PROGRAMS))


if __name__ == "__main__":
    main()
