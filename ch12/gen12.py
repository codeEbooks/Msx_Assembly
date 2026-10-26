#!/usr/bin/env python3
"""gen12.py - the programs of chapter 12.

    python3 gen12.py && ./build.sh

    stack.asm      three pairs pushed and popped: where PUSH writes, what
                   SP does, and in what order POP gives them back.
    calls.asm      a call inside a call inside a call, stopped at the
                   deepest point for a session in the console.
    lost.asm       a routine that pushes and does not pop: where its RET goes.
    cost.asm       every stack instruction and exchange, for the debugger to
                   time.
    keep.asm       two routines that keep the caller's registers, one with
                   PUSH and POP, one with the second set.
    frame.asm      three numbers passed to a routine on the stack and read
                   there through IX.
    say.asm        text placed after the CALL, printed by a routine that
                   takes it from the return address and returns past it.
    where.asm      256 calls with the stack at SYS_AREA and low in the RAM,
                   with the display off and while the VDP draws the picture.
    irq.asm        C-BIOS's interrupt routine, run on a painted stack: how
                   far down it writes.
    top.asm        the stack at the top of memory, where a program for another
                   machine might put it, and deep: what the next interrupt does.
    fill.asm       a routine that calls itself: the cells inside a ring
                   blackened, and how deep the stack went (figure 12.1).
    fillall.asm    the same routine on an empty screen.
    fast.asm       6,144 bytes filled one at a time, and two at a time with
                   PUSH.
    popsum.asm     a table added up with POP, four times with the interrupt
                   off and four times with it on.

Every program sets SP to SYS_AREA, $F380, the edge of the BIOS's work area
(chapter 3); results are kept in the RAM, from $C000 (chapter 8). build.sh
assembles with --syntax=bF (chapter 8).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
from asmparts import HEAD, TAIL, TEXT_PAGE, SHOW_PAGE, library  # noqa: E402

RESULTS = "RESULTS EQU RAM_START          ; what the program found: the debugger reads it here\n"
STACK_TOP = 0xF380          # SYS_AREA: the stack grows down from here
BLOCK, WALL = 128, 129      # the characters the pictures use: all ink, and a chequer
CHECK = [0xAA, 0x55] * 4    # the chequer
JIFFY = 0xFC9E              # the BIOS's count of frame interrupts (chapter 3)


def head(name, what):
    return HEAD.format(name=name, chapter=12, what=what)


def cart(name, what, body, after="", results=True, equs=""):
    """a cartridge that runs `body` with the interrupts off and stops"""
    return head(name, what) + (RESULTS if results else "") + equs + f"""init:   di
        ld sp, SYS_AREA         ; the stack below the BIOS's work area
{body}stop:   jr stop
{after}""" + TAIL


def chars(*codes):
    """the shapes of the picture characters, sent to the VDP (display off)"""
    out = ""
    for code in codes:
        shape = [0xFF] * 8 if code == BLOCK else CHECK
        out += f"""        VRAM_WRITE ${8 * code:04X}        ; character {code}: {'every pixel ink' if code == BLOCK else 'a fine chequer'}
        ld hl, {'full' if code == BLOCK else 'check'}
        ld b, 8
{f'ch{code}:':<8}ld a, (hl)
        out (VDP_DATA), a
        inc hl
        djnz ch{code}
"""
    return out


SHAPES = ("full:   db " + ", ".join("$FF" for _ in range(8)) + "\n" +
          "check:  db " + ", ".join(f"${b:02X}" for b in CHECK) + "\n")


# --------------------------------------------------------------- stack.asm
STACK_PAIRS = [("bc", 0x1234), ("de", 0x5678), ("hl", 0x9ABC)]


def stack():
    body = "".join(f"        ld {r}, ${v:04X}\n" for r, v in STACK_PAIRS)
    body += "".join(f"p{k}:     push {r}\n" for k, (r, _) in enumerate(STACK_PAIRS))
    body += f"full:   pop {STACK_PAIRS[0][0]}                  ; the last in comes out first\n"
    body += "".join(f"        pop {r}\n" for r, _ in STACK_PAIRS[1:])
    return cart("stack", "three pairs pushed and popped", body, results=False, equs="""; Three pairs pushed and popped again. The stack starts at SYS_AREA and
; grows down; POP gives the pairs back last first.
""")


# --------------------------------------------------------------- calls.asm
def calls():
    return cart("calls", "a call inside a call inside a call", """        ld bc, $1111
        call first
back0:  jr back0                ; back here at the end, for good
""", after="""
first:  push bc                 ; the caller's BC kept on the stack
        ld bc, $2222
        call second
back1:  pop bc                  ; BC as the caller had it
        ret

second: call third
back2:  ret

third:  nop                     ; the console stops here
        ret
""", results=False, equs="""; A call inside a call inside a call. The console stops at third, three
; calls deep.
""")


# ---------------------------------------------------------------- lost.asm
def lost():
    return cart("lost", "a routine that pushes and does not pop", """        ld bc, lost
        call keep
back:   jr back                 ; where the program should come back to
""", after="""
keep:   push bc                 ; kept for later, and never taken back
        ret                     ; RET takes BC for the way back

lost:   jr lost                 ; where the program ends up
""", results=False, equs="; A routine that pushes a pair and returns without popping it.\n")


# ---------------------------------------------------------------- cost.asm
# (label, instruction, comment)
COST = [("c1", "push bc", "PUSH"),
        ("c2", "ex (sp), hl", "HL and the top of the stack swapped ..."),
        ("c3", "ex (sp), hl", "... and swapped back"),
        ("c4", "pop bc", "POP"),
        ("c5", "push ix", ""), ("c6", "ex (sp), ix", ""), ("c7", "pop ix", ""),
        ("c8", "call sub", "CALL"),
        ("c9", "ex af, af'", "AF and AF' swapped ..."), ("c10", "ex af, af'", "... and back"),
        ("c11", "exx", "BC, DE and HL and the second set swapped ..."),
        ("c12", "exx", "... and back"),
        ("c13", "ex de, hl", ""),
        ("c14", "ld (keep), sp", "SP into memory"),
        ("c15", "ld hl, $C800", ""), ("c16", "ld sp, hl", "SP from HL"),
        ("c17", "inc sp", ""), ("c18", "dec sp", ""), ("c19", "add hl, sp", ""),
        ("c20", "ld ix, $C800", ""), ("c21", "ld sp, ix", ""),
        ("c22", "ld sp, $C800", ""),
        ("c23", "ld sp, (keep)", "SP from memory"),
        ("c24", "nop", "")]


def cost_line(label, ins, comment):
    code = f"{(label + ':') if label else '':<8}{ins}"
    return (f"{code:<32}; {comment}" if comment else code) + "\n"


def cost():
    return cart("cost", "every stack instruction and exchange",
                "".join(cost_line(*c) for c in COST),
                after="\nsub:    ret                     ; RET\n", results=False,
                equs="""keep    EQU VARS               ; a word of RAM for SP
; Every instruction that works the stack or swaps registers, one after
; another, each with a label for the debugger to stop at.
""")


# ---------------------------------------------------------------- keep.asm
KEEP_IN = {"af": 0x1234, "bc": 0x5678, "de": 0x9ABC, "hl": 0xDEF0}
WORK = [("a", 0xAA), ("bc", 0xBBBB), ("de", 0xDDDD), ("hl", 0x4444)]


def keep():
    return cart("keep", "the caller's registers kept two ways", f"""        ld hl, ${KEEP_IN['af']:04X}
        push hl
        pop af                  ; AF = ${KEEP_IN['af']:04X} (chapter 8)
        ld bc, ${KEEP_IN['bc']:04X}
        ld de, ${KEEP_IN['de']:04X}
        ld hl, ${KEEP_IN['hl']:04X}
k1:     call keep1
k2:     call keep2
k3:     nop
""", after=f"""
; keep1: changes every register and gives the caller its own back
keep1:  push af
        push bc
        push de
        push hl
        ld a, ${WORK[0][1]:02X}               ; the work: every register changed
        or a                    ; F too
        ld bc, ${WORK[1][1]:04X}
        ld de, ${WORK[2][1]:04X}
        ld hl, ${WORK[3][1]:04X}
        pop hl                  ; the last pushed comes back first
        pop de
        pop bc
        pop af
        ret

; keep2: the same work, with the caller's registers in the second set
keep2:  ex af, af'
        exx
        ld a, ${WORK[0][1]:02X}
        or a
        ld bc, ${WORK[1][1]:04X}
        ld de, ${WORK[2][1]:04X}
        ld hl, ${WORK[3][1]:04X}
        exx
        ex af, af'
        ret
""", results=False, equs="""; Two routines that do the same work and give the caller back its
; registers: keep1 with PUSH and POP, keep2 with the second set.
""")


# --------------------------------------------------------------- frame.asm
FRAME_ARGS = [1000, 2000, 3000]


def frame():
    pushes = "".join(f"""        ld hl, {v}
        push hl
""" for v in FRAME_ARGS)
    return cart("frame", "three numbers passed on the stack", pushes + """f1:     call sum3               ; HL: the sum of the three
f2:     pop de                  ; the caller takes them off again
        pop de
        pop de
f3:     ld (result), hl
""", after="""
; sum3: HL = the sum of the three words pushed before the CALL. Uses IX, DE.
sum3:   ld ix, 0
        add ix, sp              ; IX = SP: the way back is at IX+0
read:   ld l, (ix+2)
        ld h, (ix+3)            ; the last pushed
        ld e, (ix+4)
        ld d, (ix+5)            ; the one before
        add hl, de
        ld e, (ix+6)
        ld d, (ix+7)            ; the first pushed
        add hl, de
        ret
""", results=False, equs="""result  EQU RAM_START          ; the sum, for the debugger
; Three numbers passed to a routine on the stack, read there through IX, and
; taken off again by the caller.
""")


# ----------------------------------------------------------------- say.asm
SAY_HL = 0x1234
SAY_TEXTS = [(2, 1, "The text comes after the CALL,"),
             (4, 1, "and say returns past it,"),
             (6, 1, "so the program goes on here.")]


def say():
    calls_ = "".join(f"""        ld bc, ${r:02X}{c:02X}            ; row {r}, column {c}
        call say
        db "{t}", 0
""" for r, c, t in SAY_TEXTS)
    return head("say", "text placed after the CALL") + """; Text placed in the program right after the CALL that prints it.
""" + TEXT_PAGE + f"""        ld hl, ${SAY_HL:04X}            ; say gives HL back as it was
""" + calls_ + """s_end:  nop
""" + SHOW_PAGE + """
; say: prints the text after the CALL, ending in 0, from row B, column C,
;      and returns to the byte after the 0. Keeps HL; C moves on.
say:    ex (sp), hl             ; HL: the text; the caller's HL on the stack
say1:   ld a, (hl)
        inc hl
        or a
        jr z, say2              ; the 0 at the end of the text
        call putc
        inc c
        jr say1
say2:   ex (sp), hl             ; the byte after the 0 is the way back
        ret
""" + library() + TAIL


# --------------------------------------------------------------- where.asm
WHERE_CALLS = 256
WAIT_TURNS = 1000           # 30,000 T-states: from the interrupt into the picture
LOW_STACK = 0xC800


def where():
    return head("where", "256 calls, timed with the stack in two places") + f"""; {WHERE_CALLS} calls of an empty routine, timed three times: with the stack at
; SYS_AREA and the display off; with the stack at SYS_AREA while the VDP
; draws the picture; and with the stack at ${LOW_STACK:04X}, low in the RAM, while it
; draws the picture.
""" + TEXT_PAGE + f"""w1:     call calls              ; the display off, the stack at SYS_AREA
w2:     VDP_REG 1, $E0          ; the display on, and its interrupt
        im 1
        ei
        halt                    ; the picture has just ended
        di
        call wait               ; on into the next one
w3:     call calls              ; while it is drawn, the stack at SYS_AREA
w4:     ld sp, ${LOW_STACK:04X}            ; the stack low in the RAM
        ei
        halt
        di
        call wait
w5:     call calls              ; while it is drawn, the stack at ${LOW_STACK:04X}
w6:     nop
stop:   jr stop

; calls: {WHERE_CALLS} calls of a routine that returns at once
calls:  ld b, 0
ca1:    call empty
        djnz ca1
        ret
empty:  ret

; wait: {WAIT_TURNS} turns of 30 T-states
wait:   ld bc, {WAIT_TURNS}
wa1:    dec bc
        ld a, b
        or c
        jr nz, wa1
        ret
""" + library() + TAIL


# ----------------------------------------------------------------- irq.asm
IRQ_LOW = STACK_TOP - 256   # painted from here up to SYS_AREA
IRQ_PAINT = (0x00, 0xFF)


def irq():
    def paint(v):
        return f"""        ld hl, ${IRQ_LOW:04X}
        ld b, 0                 ; 256 bytes
{f'p{v:02X}:':<8}ld (hl), ${v:02X}            ; the stack's memory painted ${v:02X}
        inc hl
        djnz p{v:02X}
"""
    return cart("irq", "the BIOS's interrupt routine on a painted stack", """        VDP_REG 1, $A0          ; the display off, its interrupt on
        im 1
""" + paint(IRQ_PAINT[0]) + """        ei
        halt                    ; one interrupt, on this stack
        di
m1:     nop                     ; the debugger reads the painted bytes here ...
""" + paint(IRQ_PAINT[1]) + """        ei
        halt
        di
m2:     nop                     ; ... and here
""", results=False, equs=f"""; C-BIOS's interrupt routine run with the stack at SYS_AREA, whose last 256
; bytes are painted first with ${IRQ_PAINT[0]:02X} and then with ${IRQ_PAINT[1]:02X}: the bytes the routine
; changed show how far down it wrote.
""")


# ----------------------------------------------------------------- top.asm
TOP_DEPTH = 320             # calls deep: 640 bytes down from the top of memory


def top():
    return cart("top", "the stack at the top of memory", f"""        VDP_REG 1, $A0          ; the display off, its interrupt on
        im 1
        ld sp, 0                ; the stack at the top of memory
        ld de, {TOP_DEPTH}
        call dig                ; {TOP_DEPTH} calls deep, and waits there
back:   jr back                 ; never reached
""", after=f"""
; dig: calls itself until DE runs out, then waits for interrupts at the
;      bottom, {TOP_DEPTH} ways back on the stack above it
dig:    dec de
        ld a, d
        or e
        jr z, deep
        call dig
        ret
deep:   ei                      ; interrupts on, the stack {2 * TOP_DEPTH} bytes deep
wait:   halt
        jr wait
""", results=False, equs=f"""; The stack where a program for another machine might put it, at the top of
; memory, and {TOP_DEPTH} calls deep, with the interrupt on. The BIOS's work
; area and its hooks are up there (chapter 3).
""")


# ---------------------------------------------------------------- fill.asm
W, H = 32, 24
FILL_SEED = (6, 11)
PAINT = 0xE5                # the stack's memory painted with this byte
PAINT_LOW = STACK_TOP - 2048   # from here up to SYS_AREA
MAP = 0xC400                # the screen's 768 cells, a copy in the RAM


def ring():
    """the walls: a ring round the middle of the screen, and a square island
    inside it"""
    cx, cy, r = 15.5, 11.5, 10.1
    inside = {(x, y) for x in range(W) for y in range(H)
              if (x - cx) ** 2 + (y - cy) ** 2 < r * r}
    wall = set()
    for x in range(W):
        for y in range(H):
            if (x, y) not in inside and any((x + dx, y + dy) in inside
                                            for dx in (-1, 0, 1) for dy in (-1, 0, 1)):
                wall.add((x, y))
    for x in range(13, 19):
        for y in range(9, 15):
            if x in (13, 18) or y in (9, 14):
                wall.add((x, y))
    return sorted(wall, key=lambda c: (c[1], c[0]))


FILL = f"""
; fill: D = column, E = row. Blackens the cell if it is white, and then,
;       calling itself, every white cell joined to it. Keeps DE; uses A, HL.
fill:   ld a, d
        cp {W}
        ret nc                  ; off the screen to the side (-1 is 255)
        ld a, e
        cp {H}
        ret nc                  ; off the top or the bottom
        call cell               ; HL: the cell in the map
        ld a, (hl)
        cp ' '
        ret nz                  ; a wall, or black already
        ld (hl), BLOCK          ; black
        inc d
        call fill               ; the cell to the right
        dec d
        dec d
        call fill               ; to the left
        inc d
        inc e
        call fill               ; below
        dec e
        dec e
        call fill               ; above
        inc e
        ret

; cell: HL = the cell of the map at column D, row E. Uses A.
cell:   ld l, e
        ld h, 0
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl              ; the row times 32
        ld a, l
        or d                    ; plus the column
        ld l, a
        ld a, h
        or high MAP             ; plus ${MAP:04X}
        ld h, a
        ret
"""


def fill(name, walls, seed):
    draw = "" if not walls else f"""        ld hl, walls            ; the walls: {len(walls)} cells
        ld b, {len(walls)}
dw1:    push bc
        ld d, (hl)              ; the column
        inc hl
        ld e, (hl)              ; the row
        inc hl
        push hl
        call cell
        ld (hl), WALL           ; a wall in the map
        pop hl
        pop bc
        djnz dw1
"""
    data = "" if not walls else ("walls:\n" + "".join(
        "        db " + ", ".join(f"{c}, {r}" for c, r in walls[i:i + 8]) + "\n"
        for i in range(0, len(walls), 8)))
    what = (f"the white cells inside a ring of\n; walls blackened, starting from column {seed[0]}, row {seed[1]}"
            if walls else "every cell of an empty screen\n; blackened, starting from the top left corner")
    return head(name, "a routine that calls itself") + f"""MAP     EQU ${MAP:04X}               ; the screen's 768 cells, a copy in the RAM
BLOCK   EQU {BLOCK}                 ; black
WALL    EQU {WALL}                 ; a wall
; A routine that calls itself: {what}.
; The map is a copy of the screen in the RAM, sent to the VDP at the end. The
; {STACK_TOP - PAINT_LOW} bytes below SYS_AREA are painted ${PAINT:02X} first, so that the bytes the
; stack changed show how deep it went.
""" + TEXT_PAGE + chars(BLOCK, WALL) + f"""        ld hl, MAP
        ld de, MAP + 1
        ld (hl), ' '
        ld bc, {W * H} - 1
        ldir                    ; the map all white
""" + draw + f"""        ld hl, ${PAINT_LOW:04X}
        ld de, ${PAINT_LOW + 1:04X}
        ld (hl), ${PAINT:02X}
        ld bc, {STACK_TOP - PAINT_LOW} - 1
        ldir                    ; the stack's memory painted
        {f'ld d, {seed[0]}':<24}; the column
        {f'ld e, {seed[1]}':<24}; the row
        call fill
filled: VRAM_WRITE $1800        ; the map into the name table
        ld hl, MAP
        ld bc, {W * H}
put:    ld a, (hl)
        out (VDP_DATA), a
        inc hl
        dec bc
        ld a, b
        or c
        jr nz, put
""" + SHOW_PAGE + FILL + library() + SHAPES + data + TAIL


# ---------------------------------------------------------------- fast.asm
BUFFER = 0xD000             # 6,144 bytes of RAM, the size of Graphic II's pattern table
BUF_LEN = 6144
SLOW_BYTE, QUICK_WORD = 0xAA, 0x5555


def fast():
    return cart("fast", "6,144 bytes filled, one at a time and with PUSH", """f1:     call slow
f2:     call quick
f3:     nop
""", after=f"""
; slow: the bytes filled with ${SLOW_BYTE:02X}, one at a time
slow:   ld hl, ${BUFFER:04X}
        ld a, ${SLOW_BYTE:02X}
        ld c, {BUF_LEN // 256}                ; {BUF_LEN // 256} x 256 bytes
sl1:    ld b, 0
sl2:    ld (hl), a
        inc hl
        djnz sl2
        dec c
        jr nz, sl1
        ret

; quick: the bytes filled with ${QUICK_WORD & 0xFF:02X}, two at a time, from the end down
quick:  ld (keep), sp           ; the real stack, for later
        ld sp, ${BUFFER + BUF_LEN:04X}            ; SP just past the end of the bytes
        ld hl, ${QUICK_WORD:04X}
        ld b, {BUF_LEN // 32}               ; {BUF_LEN // 32} x 32 bytes
qu1:    DUP 16                  ; sjasmplus writes the next line 16 times
        push hl
        EDUP
        djnz qu1
        ld sp, (keep)           ; the real stack back
        ret
""", results=False, equs=f"""keep    EQU VARS               ; a word of RAM for SP
; {BUF_LEN:,} bytes from ${BUFFER:04X} filled twice: one byte at a time by slow, and two
; at a time with PUSH by quick. The interrupts are off throughout.
""")


# -------------------------------------------------------------- popsum.asm
TABLE = 0xD000
TABLE_WORDS = 2048
PASSES = 4


def popsum():
    return cart("popsum", "a table added up with POP", f"""        VDP_REG 1, $A0          ; the display off, its interrupt on
        im 1
        ld hl, TABLE            ; the table: word k is k
        ld de, 0
        ld bc, {TABLE_WORDS}
mk1:    ld (hl), e
        inc hl
        ld (hl), d
        inc hl
        inc de
        dec bc
        ld a, b
        or c
        jr nz, mk1
        ld ix, sums
        ld b, {PASSES}
off:    call sumup              ; the interrupt off
        djnz off
        ei
e0:     ld b, {PASSES}
on:     call sumup              ; the interrupt on
        djnz on
        di
e1:     nop
""", after=f"""
; sumup: the {TABLE_WORDS:,} words added up with POP; the sum stored at IX,
;        IX moved on. Keeps B.
sumup:  ld (keep), sp           ; the real stack, for later
        ld sp, TABLE            ; SP at the start of the table
        ld hl, 0
        ld c, {TABLE_WORDS // 256}
        ld a, b
        ld b, 0                 ; {TABLE_WORDS // 256} x 256 words
su1:    pop de                  ; the next word, and SP moves on by 2
        add hl, de
        djnz su1
        dec c
        jr nz, su1
        ld b, a
        ld sp, (keep)           ; the real stack back
        ld (ix+0), l
        ld (ix+1), h
        inc ix
        inc ix
        ret
""", equs=f"""sums    EQU RAM_START          ; {2 * PASSES} sums of two bytes
keep    EQU VARS               ; a word of RAM for SP
TABLE   EQU ${TABLE:04X}
; A table of {TABLE_WORDS:,} words (0, 1, 2 ...) added up with POP, {PASSES} times with
; the interrupt off and {PASSES} times with it on.
""", results=False)


def sources():
    return {"stack.asm": stack(), "calls.asm": calls(), "lost.asm": lost(), "cost.asm": cost(),
            "keep.asm": keep(), "frame.asm": frame(), "say.asm": say(), "where.asm": where(),
            "irq.asm": irq(), "top.asm": top(),
            "fill.asm": fill("fill", ring(), FILL_SEED),
            "fillall.asm": fill("fillall", [], (0, 0)),
            "fast.asm": fast(), "popsum.asm": popsum()}


def main():
    files = sources()
    for name, text in files.items():
        with open(os.path.join(HERE, name), "w") as f:
            f.write("\n".join(l.rstrip() for l in text.split("\n")))    # no spaces at line ends
    print(len(files), "sources written")


if __name__ == "__main__":
    main()
