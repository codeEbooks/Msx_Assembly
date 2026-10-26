#!/usr/bin/env python3
"""gen11.py - the programs of chapter 11.

    python3 gen11.py && ./build.sh

    map.asm        two pictures of A < E, 64 by 64 pixels, every fourth value
                   of each: taken as unsigned with the carry, and taken as
                   signed with S and P/V. Each is a bitmap in the RAM, then
                   64 character shapes in the VDP (figure 11.1).
    cmp.asm        the same two answers for all 65,536 pairs, a bit for each:
                   a table of 8 KB, unsigned first, then signed over it (16
                   KB of RAM has room for one at a time).
    cost.asm       every kind of jump, call and return, taken and not taken,
                   a label on each instruction for the debugger to time.
    jrfar.asm      JR as far forward and as far back as it reaches. Read
                   through its listing, jrfar.lst; not a cartridge.
    loops.asm      DJNZ from B = 0, 1 and 255, counted; loops of DJNZ and of
                   a sixteen-bit count, timed.
    table.asm      eight routines reached by a table of addresses and JP
                   (HL), and by a chain of CP and JR Z: which ran, and how
                   long each way took.
    abs.asm        the size of a signed byte, with a jump and without, for
                   all 256 values: the answers and the time of every call.
    idioms.asm     five questions asked of A without CP, and one with it,
                   each with its jump, for every value of A.
    bounce.asm     a ball bouncing round the screen, a decision at every
                   edge (figure 11.2).
    search.asm     a loop with two ways out: a byte searched for in a list.

Results are kept in the RAM, from $C000 (chapter 8); the code and its
constant tables stay in the cartridge. build.sh assembles with --syntax=bF
(chapter 8).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
from asmparts import HEAD, TAIL, TEXT_PAGE, SHOW_PAGE, library, SHOWBLK, BLKVARS  # noqa: E402

RESULTS = "RESULTS EQU RAM_START          ; what the program found: the debugger reads it here\n"
TABLE = 0xD000              # the big tables, in the RAM
FIRST_CODE = 128            # the character codes the pictures use, 128 on


def head(name, what):
    return HEAD.format(name=name, chapter=11, what=what)


def cart(name, what, body, after="", results=True, equs=""):
    """a cartridge that runs `body` with the interrupts off and stops"""
    return head(name, what) + (RESULTS if results else "") + equs + f"""init:   di
        ld sp, SYS_AREA
{body}stop:   jr stop
{after}""" + TAIL


# the signed comparison, shared by map.asm and cmp.asm
SLT = """
; slt: the carry set if A < E, both taken as signed (-128 to 127). Uses A.
;      CP subtracts; without overflow S is the answer, and with overflow
;      it is upside down.
slt:    cp e                    ; A - E
        jp po, slt1             ; no overflow: S tells
        jp m, no                ; overflow, S = 1: A is not less
yes:    scf
        ret
slt1:   jp m, yes               ; no overflow, S = 1: A is less
no:     or a                    ; the carry clear
        ret
"""


# ----------------------------------------------------------------- map.asm
MAP_SIDE = 64                # pixels each way
MAP_STEP = 256 // MAP_SIDE   # A and E go up by 4 a pixel
MAP_ROW = 4                  # the character row of the maps' top line
MAP_COLS = (2, 18)           # the character columns of the two maps
MAP_LABELS = [(2, 2, "UNSIGNED: C"), (2, 18, "SIGNED: S, P/V")]
MAP_RAM = 0xC200             # two bitmaps of 8 x 64 bytes, 512 bytes apart


def map_():
    w = MAP_SIDE // 8
    labels = "".join(f"""        ld b, {r}
        ld c, {c}
        ld hl, m{k}
        call puts
""" for k, (r, c, _) in enumerate(MAP_LABELS))
    texts = "".join(f'm{k}:     db "{t}", 0\n' for k, (_, _, t) in enumerate(MAP_LABELS))
    steps = "".join("        inc d\n" for _ in range(MAP_STEP))
    shows = "".join(f"""        ld hl, MAPU + {512 * k}
        ld de, ${w:02X}{w:02X}            ; {w} bytes across, {w} rows of cells
        ld a, {FIRST_CODE + w * w * k}
        ld b, {MAP_ROW}
        ld c, {MAP_COLS[k]}
        call showblk            ; the picture, as {w * w} characters
""" for k in range(2))
    return head("map", "A < E, unsigned and signed, as two pictures") + f"""MAPU    EQU ${MAP_RAM:04X}               ; the unsigned picture; the signed one 512 bytes on
""" + BLKVARS + f"""; A < E drawn for A = 0, {MAP_STEP} ... {256 - MAP_STEP} across and E = 0, {MAP_STEP} ... {256 - MAP_STEP} down:
; a pixel wherever the answer is yes. On the left the carry after CP
; answers, the numbers taken as unsigned; on the right slt answers, the
; numbers taken as signed (figure 11.1).
""" + TEXT_PAGE + labels + f"""        ld hl, MAPU             ; HL: a line of the unsigned picture
        ld e, 0                 ; E: the second number
mline:  push hl
        call uline              ; the line of the unsigned picture
        pop hl
        push hl
        inc h
        inc h                   ; the same line, 512 bytes on
        call sline              ; the line of the signed picture
        pop hl
        ld bc, {w}
        add hl, bc              ; the next line
        ld a, e
        add a, {MAP_STEP}
        ld e, a                 ; the next second number
        jr nc, mline            ; until E goes round past {256 - MAP_STEP}
""" + shows + SHOW_PAGE + f"""
; uline: {w} bytes from HL for the second number E: a pixel for each first
;        number D = 0, {MAP_STEP} ... {256 - MAP_STEP} below E, taken as unsigned
uline:  ld d, 0
ul1:    ld b, 8                 ; eight pixels to a byte
ul2:    ld a, d
        cp e                    ; the carry: D < E
        rl c                    ; the answer into C
{steps}        djnz ul2
        ld (hl), c
        inc hl
        ld a, d
        or a
        jr nz, ul1              ; until D goes round to 0
        ret

; sline: the same, with the numbers taken as signed
sline:  ld d, 0
sl1:    ld b, 8
sl2:    ld a, d
        call slt                ; the carry: D < E, signed
        rl c
{steps}        djnz sl2
        ld (hl), c
        inc hl
        ld a, d
        or a
        jr nz, sl1
        ret
""" + SLT + SHOWBLK + texts + library() + TAIL


# ----------------------------------------------------------------- cmp.asm
def cmp_():
    passes = []
    for name, test, end in (("u", "cp e                    ; the carry: D < E, unsigned", ""),
                            ("s", "call slt                ; the carry: D < E, signed",
                             "half:   ")):
        passes.append(f"""{end or '        '}ld hl, TABLE
        ld d, 0                 ; D: the first number
{name}1:     ld e, 0                 ; E: the second
{name}2:     ld b, 8                 ; eight answers to a byte
{name}3:     ld a, d
        {test}
        rl c
        inc e
        djnz {name}3
        ld (hl), c
        inc hl
        ld a, e
        or a
        {f'jr nz, {name}2':<24}; all 256 values of E
        inc d
        {f'jr nz, {name}1':<24}; for all 256 values of D
""")
    return cart("cmp", "A < E for every pair, unsigned and signed", "".join(passes), after=SLT,
                results=False, equs=f"""TABLE   EQU ${TABLE:04X}               ; 8 KB: D x 32 + E / 8 the byte, bit 7 first
; D < E for all 65,536 pairs, a bit each: first taken as unsigned, the carry
; after CP; the debugger reads the table at half. Then taken as signed, slt,
; into the same 8 KB: a 16 KB machine has room for one table at a time.
""")


# ---------------------------------------------------------------- cost.asm
# (label, instruction, comment); Z is set throughout
COST = [("c1", "jp z, c2", "JP cc, taken"), (None, "halt", ""),
        ("c2", "jp nz, never", "JP cc, not taken"),
        ("c3", "jp c4", "JP"), (None, "halt", ""),
        ("c4", "jr z, c5", "JR cc, taken"), (None, "halt", ""),
        ("c5", "jr nz, never", "JR cc, not taken"),
        ("c6", "jr c7", "JR"), (None, "halt", ""),
        ("c7", "ld b, 2", ""),
        ("c8", "djnz c8", "DJNZ, taken once and then not"),
        ("c9", "call z, sub", "CALL cc, taken"),
        ("c10", "call nz, never", "CALL cc, not taken"),
        ("c11", "call sub2", "CALL"),
        ("c12", "ld hl, c14", ""),
        ("c13", "jp (hl)", "JP (HL)"), (None, "halt", ""),
        ("c14", "ld ix, c16", ""),
        ("c15", "jp (ix)", "JP (IX)"), (None, "halt", ""),
        ("c16", "nop", "")]
COST_SUBS = [("sub", "ret nz", "RET cc, not taken"), ("s2", "ret z", "RET cc, taken"),
             ("sub2", "ret", "RET"), ("never", "halt", "")]


def cost_line(label, ins, comment):
    code = f"{(label + ':') if label else '':<8}{ins}"
    return (f"{code:<32}; {comment}" if comment else code) + "\n"


def cost():
    return cart("cost", "every kind of jump, call and return, taken and not",
                "        xor a                   ; Z = 1\n" + "".join(cost_line(*c) for c in COST),
                after="\n" + "".join(cost_line(*c) for c in COST_SUBS), results=False,
                equs="""; Every jump, call and return, taken and not, each instruction with a
; label for the debugger to stop at. A HALT marks a place no jump should
; land: with the interrupts off it would stop the program for good.
""")


# --------------------------------------------------------------- jrfar.asm
JRFAR = """; jrfar.asm -- chapter 11: JR as far as it goes. The distance counts from
; the byte after the JR, and it is one signed byte: 127 forward, 128 back.
; Not a cartridge: build.sh assembles it into a listing, jrfar.lst.
        ORG $4000
fwd:    jr ahead                ; 127 bytes on from the next instruction
        ds 127
ahead:  nop
behind: nop
        ds 125
back:   jr behind               ; 128 bytes back from the next instruction
"""


# --------------------------------------------------------------- loops.asm
LOOP_COUNTS = [0, 1, 255]
LOOP_TIMED = [1, 10, 0]
BIG_LOOP = 1000


def loops():
    counts = "".join(f"""        ld b, {n}
        ld hl, 0
k{k}:     inc hl                  ; one more turn
        djnz k{k}
        {f'ld (turns + {2 * k}), hl':<24}; how many turns B = {n} made
""" for k, n in enumerate(LOOP_COUNTS))
    timed = "".join(f"""{f'd{k}:':<8}ld b, {n}
{f'e{k}:':<8}nop                     ; the body of the loop
        djnz e{k}
{f'f{k}:':<8}nop
""" for k, n in enumerate(LOOP_TIMED))
    return cart("loops", "DJNZ counted and timed", counts + timed + f"""g0:     ld bc, {BIG_LOOP}
g1:     dec bc
        ld a, b
        or c                    ; Z only when B and C are both 0
        jr nz, g1
g2:     nop
""", results=False, equs=f"""turns   EQU RAM_START          ; {len(LOOP_COUNTS)} counts of two bytes
; How many turns DJNZ makes from B = 0, 1 and 255; the time of a loop of one
; NOP from B = 1, 10 and 0; and the time of a loop that counts {BIG_LOOP} in BC,
; the way chapter 7 mended it.
""")


# --------------------------------------------------------------- table.asm
ROUTINES = 8


def table(n=ROUTINES):
    calls = "".join(f"""        ld a, {k}
{f'a{k}:':<8}call dispatch
        {f'ld (which + {k}), a':<24}; the routine that ran
        ld a, {k}
{f'b{k}:':<8}call chain
        {f'ld (which + {n + k}), a':<24}
""" for k in range(n))
    chain = "".join(f"""        cp {k}
        jr z, r{k}
""" for k in range(1, n))
    routines = "".join(f"""{f'r{k}:':<8}{f'ld a, {k * 17}':<24}; routine {k} answers {k * 17}
        ret
""" for k in range(n))
    return cart("table", f"one of {n} routines, by a table and by a chain", calls, after=f"""
; dispatch: the routine whose number is in A, through the table
dispatch:
        add a, a                ; two bytes to an address
        ld l, a
        ld h, 0
        ld de, routines
        add hl, de              ; HL: the routine's place in the table
        ld e, (hl)
        inc hl
        ld d, (hl)              ; DE: its address, low byte first
        ex de, hl
        jp (hl)                 ; and there; its RET comes back to the CALL

; chain: the same routine, by asking about each number in turn
chain:  or a
        jr z, r0
""" + chain + """        ret

routines:
        dw """ + ", ".join(f"r{k}" for k in range(n)) + "\n" + routines, results=False,
                equs=f"""which   EQU RAM_START          ; {2 * n} bytes: what each call answered
; One of {n} routines chosen by the number in A: through a table of their
; addresses and JP (HL), and through a chain of CP and JR Z. Each routine
; answers with its own number times 17, and the answers go into which.
""")


# ----------------------------------------------------------------- abs.asm
ABS_J, ABS_N = TABLE, TABLE + 0x100


def abs_():
    return cart("abs", "the size of a signed byte, with a jump and without", f"""        ld hl, ABSJ
        ld d, 0                 ; D: 0 to 255
j1:     ld a, d
j2:     call absj
j3:     ld (hl), a
        inc hl
        inc d
        jr nz, j1
        ld hl, ABSN
n1:     ld a, d
n2:     call absn
n3:     ld (hl), a
        inc hl
        inc d
        jr nz, n1
""", after="""
; absj: A = the size of A, taken as signed, with a jump
absj:   or a                    ; S from A
        jp p, aj1               ; 0 or positive: as it is
        neg                     ; negative: turned round
aj1:    ret

; absn: the same with no jump. Uses B and C.
absn:   ld b, a
        add a, a                ; the sign into the carry
        sbc a, a                ; $00, or $FF for a negative number
        ld c, a
        xor b                   ; negative: every bit turned over ...
        sub c                   ; ... and 1 added, since 0 - $FF is 1
        ret
""", results=False, equs=f"""ABSJ    EQU ${ABS_J:04X}               ; 256 answers of absj
ABSN    EQU ${ABS_N:04X}               ; and of absn
; The size of a signed byte, for all 256 values: with a jump (absj) and with
; no jump (absn).
""")


# -------------------------------------------------------------- idioms.asm
IDIOM_TABLE = TABLE
# (the test, the jump, what a yes means)
IDIOMS = [("or a", "jp m", "negative"),
          ("and %00001111", "jr z", "a multiple of 16"),
          ("bit 0, a", "jr nz", "odd"),
          ("dec a", "jr z", "it was 1"),
          ("inc a", "jr z", "it was 255"),
          ("cp 100", "jr nc", "100 or more")]


def idioms():
    tests = []
    for k, (test, jump, meaning) in enumerate(IDIOMS):
        tests.append(f"""        ld a, d
        {test:<24}; {meaning}?
        {f'{jump}, y{k}':<24}
        or a                    ; no: the carry clear
        {f'jr done{k}':<24}
{f'y{k}:':<8}scf                     ; yes: the carry set
{f'done{k}:':<8}rr c                    ; the answer into C, from the top
""")
    return cart("idioms", "questions asked of A, each with its jump", """        ld hl, ANSWERS
        ld d, 0                 ; D: every value of A
next:   ld c, 0
""" + "".join(tests) + """        ld (hl), c
        inc hl
        inc d
        jr nz, next
""", results=False, equs=f"""ANSWERS EQU ${IDIOM_TABLE:04X}               ; a byte for each value of A
; Five ways to ask about A without CP, and one with it, each followed by its
; jump, for every value of A. The answers, one bit each, go into a byte for
; each A, the first test in bit {8 - len(IDIOMS)} and the last in bit 7.
""")


# -------------------------------------------------------------- bounce.asm
BOUNCE_STEPS = 150
BOUNCE_W, BOUNCE_H = 32, 24
BLOCK = FIRST_CODE          # a character all ink


def bounce():
    return head("bounce", "a ball that turns round at every edge") + f"""NAMES   EQU $1800               ; the name table: a byte for each cell
dx      EQU VARS + $10          ; the steps across and down, 1 or -1, and
dy      EQU VARS + $11          ; the count of turns: in the RAM, since the
bounces EQU VARS + $12          ; cartridge is ROM (chapter 8)
; A ball of one cell in the box of the screen, a step across and a step down
; at each move, turning back at every edge: {BOUNCE_STEPS} moves, each cell it
; passes made black (figure 11.2).
""" + TEXT_PAGE + f"""        VDP_REG 7, LIGHT_GREEN  ; a border of another colour: the box shows
        VRAM_WRITE ${8 * BLOCK:04X}        ; character {BLOCK}: every pixel ink
        ld b, 8
        ld a, $FF
blk:    out (VDP_DATA), a
        djnz blk
        ld a, 1
        ld (dx), a
        ld (dy), a              ; down and to the right
        xor a
        ld (bounces), a
        ld d, 0                 ; D: the column, 0 to {BOUNCE_W - 1}
        ld e, 0                 ; E: the row, 0 to {BOUNCE_H - 1}
        ld b, {BOUNCE_STEPS}
move:   push bc
        call plot               ; the ball's cell, black
        ld a, (dx)
        add a, d
        ld d, a                 ; a step across
        or a
        jr z, flipx             ; at the left edge ...
        cp {BOUNCE_W - 1}
        jr nz, okx              ; ... or the right: turn round
flipx:  ld a, (dx)
        neg                     ; 1 becomes -1, -1 becomes 1
        ld (dx), a
        call count
okx:    ld a, (dy)
        add a, e
        ld e, a                 ; a step down
        or a
        jr z, flipy             ; at the top ...
        cp {BOUNCE_H - 1}
        jr nz, oky              ; ... or the bottom: turn round
flipy:  ld a, (dy)
        neg
        ld (dy), a
        call count
oky:    pop bc
        djnz move
        call plot               ; where the ball stopped
""" + SHOW_PAGE + f"""
; plot: the cell at column D, row E made black. Uses A, BC, HL.
plot:   ld l, e
        ld h, 0
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl              ; the row times 32
        ld a, l
        or d                    ; plus the column
        ld l, a
        ld bc, NAMES
        add hl, bc              ; HL: the cell in the name table
        ld a, l
        out (VDP_CTRL), a
        ld a, h
        or $40                  ; a write
        out (VDP_CTRL), a
        ld a, {BLOCK}
        out (VDP_DATA), a       ; the black character
        ret

; count: one more turn
count:  ld hl, bounces
        inc (hl)
        ret
""" + library() + TAIL


# -------------------------------------------------------------- search.asm
SEARCH_LEN = 32
SEARCH_DATA = [(0x11 + 0x0F * i) & 0xFF for i in range(SEARCH_LEN)]   # 32 different bytes
SEARCH = [SEARCH_DATA[0], SEARCH_DATA[10], SEARCH_DATA[31], 0x07]   # the first, the 11th,
                                                                    # the last, and none


def search():
    data = SEARCH_DATA
    assert len(set(data)) == SEARCH_LEN and SEARCH[3] not in data
    tests = "".join(f"""        ld a, ${v:02X}
        ld hl, list
        ld b, {SEARCH_LEN}
{f's{k}:':<8}call find
        {f'ld (where + {2 * k}), hl':<24}; where it stopped
        ld a, 0
        jr nz, {f'm{k}':<17}; not found: 0
        inc a                   ; found: 1
{f'm{k}:':<8}{f'ld (found + {k}), a':<24}
""" for k, v in enumerate(SEARCH))
    return cart("search", "a byte in a list: a loop with two ways out", tests, after="""
; find: the first of the B bytes from HL that equals A. Found: Z set, HL
;       on it. Not found: Z clear, since the last CP said not equal.
find:   cp (hl)
        ret z                   ; the way out when it is found
        inc hl
        djnz find               ; the way out when the list ends
        ret

list:   db """ + ", ".join(f"${d:02X}" for d in data) + "\n", results=False,
                equs=f"""where   EQU RAM_START          ; {len(SEARCH)} addresses: where HL stopped
found   EQU RAM_START + {2 * len(SEARCH)}      ; {len(SEARCH)} bytes: 1 found, 0 not
; A list of {SEARCH_LEN} bytes searched for four values: the first, the eleventh,
; the last, and one that is not there. For each, whether it was found, where
; HL stopped, and, for the debugger, the time.
""")


def sources():
    return {"map.asm": map_(), "cmp.asm": cmp_(), "cost.asm": cost(), "jrfar.asm": JRFAR,
            "loops.asm": loops(), "table.asm": table(), "abs.asm": abs_(),
            "idioms.asm": idioms(), "bounce.asm": bounce(), "search.asm": search()}


def main():
    files = sources()
    for name, text in files.items():
        with open(os.path.join(HERE, name), "w") as f:
            f.write("\n".join(l.rstrip() for l in text.split("\n")))    # no spaces at line ends
    print(len(files), "sources written")


if __name__ == "__main__":
    main()
