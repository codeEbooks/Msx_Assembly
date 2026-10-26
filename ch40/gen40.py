#!/usr/bin/env python3
"""gen40.py - the programs of chapter 40: score, text, and a status line
that never flickers.

    python3 gen40.py && ./build.sh

    status.asm   the score and the best score, HI, on a status line of their
                 own, in the bottom third of the screen, which has its own
                 shapes and colours: a BCD digit is its own name there. In
                 each of 128 frames: HALT, the status line at once (only the
                 pairs of digits that changed, update), then the frame's
                 points, the best score and the frame's other work (turn);
                 GAME OVER after the last (figure 40.1)
    after.asm    the same, the status line after the work, wherever the
                 work ends
    blink.asm    WHERE IT BREAKS: after.asm with no copy of what is shown:
                 each number blanked with six spaces and printed again in
                 full, after the work (redraw)
    after50.asm  the Workshop's, question 6: after.asm with the table of the
                 50 Hz machine on any machine

Graphic II with its masks (chapter 22): R#4 = $02 and R#3 = $DF give the
first two thirds one set of shapes and colours, the game's, and the third
one of its own, the status line's. Name 0 is the paper and name 1 chapter
24's brick in the first two thirds; in the third, names 0 to 9 are the
digits and names 32 to 127 chapter 30's set. The interrupt comes in mode 2
(chapter 17): its routine reads the status, which lets the signal down, and
counts the frame. Every line of putbcd, update, show, best, addsc and say
carries its price, which walk.py adds up along the path it takes. Each
program ends with asmparts.CART_END; build.sh assembles with --syntax=bFw.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "tools"))
sys.path.insert(0, os.path.join(REPO, "ch26"))
sys.path.insert(0, os.path.join(REPO, "ch30"))
from asmparts import HEAD, CART_END, IM2, im2  # noqa: E402
from gen26 import db_rows  # noqa: E402
import shapes30  # noqa: E402  (chapter 30: the set)

EU, JP = "MSXBOOK_EU16", "MSXBOOK_JP16"
MACHINES = [EU, JP]
BIOS = '        INCLUDE "bios.inc"\n'
BLACK, DARK_BLUE, WHITE = 1, 4, 15

# the registers: Graphic II, display and interrupt on, 8 x 8 sprites (none)
REGS = [0x02, 0xE0, 0x06, 0xDF, 0x02, 0x36, 0x07, WHITE]
NAMES, ATT = 0x1800, 0x1B00
GAME_SHAPES, GAME_COLOURS = 0x0000, 0x2000      # thirds 0 and 1
STATUS_SHAPES, STATUS_COLOURS = 0x1000, 0x3000  # third 2, its own

FONT = shapes30.wide()                          # codes 32 to 127, 8 bytes each
DIGIT_SHAPES = FONT[(48 - 32) * 8:(58 - 32) * 8]  # '0' to '9'
BRICK = [0xFF, 0x80, 0x80, 0x80, 0xFF, 0x08, 0x08, 0x08]
BRICK_C = BLACK << 4 | DARK_BLUE
PAPER_C = BLACK << 4 | WHITE
STATUS_C = WHITE << 4 | DARK_BLUE               # white on dark blue
SPACE = 32

STATUS_ROW = 16                                 # the third's first row
SCORE_AT = NAMES + 32 * STATUS_ROW + 7          # the score's first digit
HI_AT = NAMES + 32 * STATUS_ROW + 24
LABELS = [(NAMES + 32 * STATUS_ROW + 1, "SCORE"), (NAMES + 32 * STATUS_ROW + 21, "HI")]
OVER_AT = NAMES + 32 * 20 + 11
OVER = "GAME OVER"

FRAMES = 128
HI0 = [0x00, 0x15, 0x00]                        # the best score before the game
# the frame's points, in BCD, at the frame's number AND 15
POINTS = [0x10, 0x00, 0x25, 0x00, 0x50, 0x75, 0x00, 0x05,
          0x00, 0x90, 0x15, 0x00, 0x40, 0x00, 0x65, 0x00]
# the frame's other work: passes of a loop of 30 T-states, at the same place;
# at 60 Hz the same part of the time from the interrupt to the status line,
# 198 lines of 249 (bit 7 of $002B chooses, chapter 33)
WORK50 = [100, 1500, 400, 1880, 700, 1000, 1520, 250,
          1300, 1888, 1465, 1150, 1495, 850, 1872, 1700]
WORK60 = [round(p * 198 / 249) for p in WORK50]
PASS_T = 30

NUMS = 0xC400                                   # score, then hi, three bytes each
SHOWN = NUMS + 0x100                            # the copies on the screen


def head(name, what):
    return HEAD.format(name=name, chapter=40, what=what) + BIOS


def say_lines(text):
    return "".join(f"; {l}\n" for l in text.strip().splitlines())


# ------------------------------------------------------------------ the routines
PUTBCD = """
; putbcd: A = a BCD byte, the VRAM address set -> its two digits sent: in the
; status third a digit is its own name. Uses A, C
putbcd: ld c, a                 ;  5  kept for the second digit
        rrca                    ;  5
        rrca                    ;  5
        rrca                    ;  5
        rrca                    ;  5  the first digit to bits 3 to 0
        and $0F                 ;  8  and nothing else: its own name
        out (VDP_DATA), a       ; 12
        ld a, c                 ;  5
        and $0F                 ;  8  the second digit
        nop                     ;  5  30 T-states after the first OUT
        out (VDP_DATA), a       ; 12
        ret                     ; 11
"""

UPDATE = """
; update: HL = a number, three BCD bytes, with a copy of the three last sent
; 256 bytes on; DE = the VRAM address of its first digit, bit 6 set -> each
; byte that differs from its copy sent, and copied. Uses A, BC, DE, HL
update: ld b, 3                 ;  8  three bytes
.byte:  ld a, (hl)              ;  8  a byte of the number
        inc h                   ;  5  the page of the bytes sent
        cp (hl)                 ;  8
        jr z, .same             ; 13, or 8  on the screen already
        ld (hl), a              ;  8  it will be
        ld c, a                 ;  5
        ld a, e                 ;  5
        out (VDP_CTRL), a       ; 12
        ld a, d                 ;  5
        out (VDP_CTRL), a       ; 12  the address of its first digit
        ld a, c                 ;  5
        call putbcd             ; 18  its two names
.same:  inc e                   ;  5
        inc e                   ;  5  past its two names
        dec h                   ;  5  back to the number
        inc l                   ;  5  and its next byte
        djnz .byte              ; 14, or 9
        ret                     ; 11
"""

SHOW = """
; show: HL = a number, three BCD bytes, DE = the VRAM address of its first
; digit, bit 6 set -> its six digits sent. Uses A, BC, HL
show:   ld a, e                 ;  5
        out (VDP_CTRL), a       ; 12
        ld a, d                 ;  5
        out (VDP_CTRL), a       ; 12  the address of the first digit
        ld b, 3                 ;  8
.byte:  ld a, (hl)              ;  8
        call putbcd             ; 18
        inc l                   ;  5
        djnz .byte              ; 14, or 9
        ret                     ; 11
"""

BEST = """
; best: score against hi, the first digits first -> hi is score when score
; is higher. Uses A, BC, DE, HL
best:   ld hl, score            ; 11
        ld de, hi               ; 11
        ld b, 3                 ;  8  three bytes
.byte:  ld a, (de)              ;  8  a byte of hi
        cp (hl)                 ;  8  less the same byte of score
        jr c, .new              ; 13, or 8  score's is higher: a new best
        ret nz                  ; 12, or 6  hi's is higher
        inc l                   ;  5
        inc e                   ;  5  the same: the next byte decides
        djnz .byte              ; 14, or 9
        ret                     ; 11  the same number
.new:   ld c, b                 ;  5  the bytes from here on, this one too;
        ld b, 0                 ;  8  the ones before are the same
        ldir                    ; 23, and 18 the last time
        ret                     ; 11
"""

ADDSC = """
; addsc: A = points, two BCD digits -> added to score, the carry taken into
; the digits before with ADC and DAA (chapter 9). Uses A, HL
addsc:  ld hl, score + 2        ; 11  the last two digits
        add a, (hl)             ;  8
        daa                     ;  5
        ld (hl), a              ;  8
        dec l                   ;  5  DEC L leaves the carry alone
        ld a, (hl)              ;  8
        adc a, 0                ;  8
        daa                     ;  5
        ld (hl), a              ;  8
        dec l                   ;  5
        ld a, (hl)              ;  8
        adc a, 0                ;  8
        daa                     ;  5
        ld (hl), a              ;  8
        ret                     ; 11
"""

SAY = """
; say: HL = a text ending in a 0 byte, DE = the VRAM address of its first
; character, bit 6 set -> the text sent, HL on its 0. Uses A, HL
say:    ld a, e                 ;  5
        out (VDP_CTRL), a       ; 12
        ld a, d                 ;  5
        out (VDP_CTRL), a       ; 12  the address of the first character
.char:  ld a, (hl)              ;  8  the next character
        or a                    ;  5
        ret z                   ; 12, or 6  the 0: the end
        out (VDP_DATA), a       ; 12
        inc hl                  ;  7
        jr .char                ; 13
"""

STATUS = """
; status: the score and hi on the status line, the pairs that changed
status: ld hl, score
        ld de, SCORE_AT | $4000
        call update
        ld hl, hi
        ld de, HI_AT | $4000
        jp update
"""

TURN = """
; turn: the frame's points from the table, at its number AND 15, the best
; score kept, and the frame's other work: passes of a loop, from the table
turn:   ld a, (count)
        and 15
        ld e, a
        ld d, 0
        ld hl, points
        add hl, de
        ld a, (hl)              ; the frame's points
        call addsc
        call best
        ld a, (count)
        and 15
        add a, a
        ld e, a
        ld d, 0
        ld hl, (worktab)        ; this machine's table
        add hl, de
        ld c, (hl)
        inc hl
        ld b, (hl)              ; the frame's passes
.wait:  dec bc                  ;  7
        ld a, b                 ;  5
        or c                    ;  5
        jr nz, .wait            ; 13: 30 T-states a pass
        ret
"""

REDRAW = """
; redraw: WHERE IT BREAKS - the two numbers of the status line blanked with
; six spaces each and sent again in full, as a program that keeps no copy
; of what is shown would do. Uses A, BC, DE, HL
redraw: ld hl, blanks           ; 11
        ld de, SCORE_AT | $4000 ; 11
        call say                ; 18  six spaces over the score
        ld hl, score            ; 11
        ld de, SCORE_AT | $4000 ; 11
        call show               ; 18  and its six digits
        ld hl, blanks           ; 11
        ld de, HI_AT | $4000    ; 11
        call say                ; 18  the same for hi
        ld hl, hi               ; 11
        ld de, HI_AT | $4000    ; 11
        jp show                 ; 11
"""

ISR = """
; isr: every frame. The status read, which lets the signal down; the frame
; counted. Keeps AF, HL
isr:    push af
        in a, (VDP_CTRL)        ; the status: the signal down
        push hl
        ld hl, (ticks)
        inc hl
        ld (ticks), hl
        pop hl
        pop af
        ei
        ret
"""

RAM = f"""ticks   EQU VARS                ; frames counted by isr, two bytes
count   EQU VARS + 2            ; the frames of the game
worktab EQU VARS + 3            ; the work table for 50 or 60 Hz
score   EQU ${NUMS:04X}               ; six BCD digits, the first two first
hi      EQU ${NUMS + 3:04X}               ; the best score
shown   EQU ${SHOWN:04X}               ; the copies of score and hi on the screen
SCORE_AT EQU ${SCORE_AT:04X}            ; the score's first digit: row {STATUS_ROW}, column {SCORE_AT % 32}
HI_AT   EQU ${HI_AT:04X}               ; hi's: column {HI_AT % 32}
OVER_AT EQU ${OVER_AT:04X}               ; GAME OVER: row 20, column {OVER_AT % 32}
FRAMES  EQU {FRAMES}
"""


def setup():
    """display off; Graphic II with the third third its own; the shapes,
    colours and names; the labels; the numbers; mode 2; display on"""
    return f"""init:   di
        ld sp, SYS_AREA
        VDP_REG 1, $80          ; display off
        VDP_REG 0, $02          ; Graphic II
        VDP_REG 2, $06          ; names    $1800
        VDP_REG 3, $DF          ; colours  $2000 for thirds 0 and 1, $3000 for 2
        VDP_REG 4, $02          ; shapes   $0000 for thirds 0 and 1, $1000 for 2
        VDP_REG 5, $36          ; sprite attributes $1B00
        VDP_REG 6, $07          ; sprite patterns   $3800
        VDP_REG 7, ${WHITE:02X}          ; border white
        VRAM_WRITE $1B00        ; no sprites
        ld a, $D0
        out (VDP_DATA), a
        VRAM_WRITE $0000        ; every shape all paper: both sets
        ld bc, $1800
        xor a
        call fill
        VRAM_WRITE $0008        ; the game's name 1, the brick
        ld hl, brick
        ld b, 8
        call send
        VRAM_WRITE $1000        ; the status third: names 0-9 the digits
        ld hl, font + (48 - 32) * 8
        ld b, 80
        call send
        VRAM_WRITE $1100        ; and names 32-127 chapter 30's set
        ld hl, font
        ld b, 0
        call send
        ld b, 0
        call send
        ld b, 0
        call send
        VRAM_WRITE $2000        ; the game's colours: black on white ...
        ld bc, $0800
        ld a, ${PAPER_C:02X}
        call fill
        VRAM_WRITE $2008        ; ... but the brick's
        ld bc, $0008
        ld a, ${BRICK_C:02X}
        call fill
        VRAM_WRITE $3000        ; the status third's: white on dark blue
        ld bc, $0800
        ld a, ${STATUS_C:02X}
        call fill
        VRAM_WRITE $1800        ; the names: the room ...
        ld hl, room
        ld b, 0
        call send
        ld b, 0
        call send
        VRAM_WRITE $1A00        ; ... and the status third all spaces
        ld bc, $0100
        ld a, {SPACE}
        call fill
""" + "".join(f"""        ld hl, label{i}
        ld de, ${addr | 0x4000:04X}
        call say
""" for i, (addr, _) in enumerate(LABELS)) + f"""        ld hl, start            ; score, hi, and the copies of both: $FF,
        ld de, score            ; which no BCD byte is, so that the first
        ld bc, 6                ; frame sends every digit
        ldir
        ld hl, shown
        ld de, shown + 1
        ld (hl), $FF
        ld bc, 5
        ldir
        xor a
        ld (count), a
        ld a, ($002B)           ; bit 7 is 1 on a 50 Hz machine (chapter 4)
        rla
        ld hl, work60           ; 60 Hz ...
        jr nc, .rate
        ld hl, work50           ; ... and 50 Hz
.rate:  ld (worktab), hl
        ld hl, 0
        ld (ticks), hl
""" + im2("isr") + """        in a, (VDP_CTRL)        ; the status read: no signal left over
        VDP_REG 1, $E0          ; display on, the frame's interrupt on
        ei
"""


COMMON = """
; send: B bytes (256 for 0) from HL to the VDP, the address set; HL after
; them. The display is off
send:   ld a, (hl)
        out (VDP_DATA), a
        inc hl
        djnz send
        ret

; fill: BC bytes of A to the VDP, the address set. The display is off
fill:   ld e, a
.byte:  ld a, e
        out (VDP_DATA), a
        dec bc
        ld a, b
        or c
        jr nz, .byte
        ret
"""


def room():
    """the 512 names of the first two thirds: a ring of bricks"""
    names = []
    for r in range(16):
        for c in range(32):
            names.append(1 if r in (0, 15) or c in (0, 31) else 0)
    return names


def data():
    out = "brick:  db " + ", ".join(f"${b:02X}" for b in BRICK) + "\n"
    out += "points:                         ; the frame's points, BCD, at its number AND 15\n"
    out += db_rows(POINTS)
    for hz, table in ((50, WORK50), (60, WORK60)):
        out += f"work{hz}:                         ; the frame's passes of 30 T-states at {hz} Hz\n"
        out += "".join("        dw " + ", ".join(str(w) for w in table[i:i + 8]) + "\n" for i in range(0, 16, 8))
    out += "start:  db " + ", ".join(f"${b:02X}" for b in [0, 0, 0] + HI0) + "  ; score 000000, hi " + \
        "".join(f"{b:02X}" for b in HI0) + "\n"
    for i, (_, text) in enumerate(LABELS):
        out += f'label{i}: db "{text}", 0\n'
    out += f'over:   db "{OVER}", 0\n'
    out += 'blanks: db "      ", 0         ; six spaces\n'
    out += "room:                           ; the first two thirds' names\n" + db_rows(room(), 16)
    out += "font:                           ; chapter 30's set, codes 32 to 127\n" + db_rows(FONT)
    return out


# ------------------------------------------------------------------ the frames
STATUS_MAIN = """frame:  halt                    ; the frame begins
news:   call status             ; the status line, before anything else
told:   call turn               ; the points, and the other work
        ld hl, count
        inc (hl)
        ld a, (hl)
        cp FRAMES
        jr nz, frame            ; 128 frames
        halt
        call status             ; the last frame's points too
"""

AFTER_MAIN = """frame:  halt                    ; the frame begins
woke:   call turn               ; the points, and the other work
news:   call status             ; then the status line
told:   ld hl, count
        inc (hl)
        ld a, (hl)
        cp FRAMES
        jr nz, frame            ; 128 frames
        halt
"""

BLINK_MAIN = """frame:  halt                    ; the frame begins
woke:   call turn               ; the points, and the other work
news:   call redraw             ; then the status line, cleared and sent
told:   ld hl, count
        inc (hl)
        ld a, (hl)
        cp FRAMES
        jr nz, frame            ; 128 frames
        halt
"""

END = """        ld hl, over
        ld de, OVER_AT | $4000  ; row 20, column 11
        call say                ; once
        di
done:   jr done                 ; nothing more to do
"""

KINDS = {
    "status": ("the status line straight after HALT, only what changed", STATUS_MAIN,
               STATUS + UPDATE + PUTBCD),
    "after": ("the status line after the frame's work", AFTER_MAIN, STATUS + UPDATE + PUTBCD),
    "blink": ("where it breaks: the numbers blanked and sent again, after the work", BLINK_MAIN,
              REDRAW + SHOW + PUTBCD),
}
SAYS = {
    "status": """status.asm: the score and HI on a status line in a third of the screen of
its own, where a BCD digit is its own name. In each of 128 frames, after
HALT, the pairs of digits that changed are sent at once, then the points
and the frame's other work; GAME OVER after the last.""",
    "after": """after.asm: status.asm with the status line sent after the frame's work,
wherever the work ends.""",
    "blink": """blink.asm: WHERE IT BREAKS. after.asm with no copy of what is shown: each
number blanked with six spaces and sent again in full, after the work.""",
}


# the Workshop's program, not printed: after.asm with the 50 Hz table on
# every machine (question 6)
EXTRA = {"after50": "after"}
SAYS["after50"] = """after50.asm: after.asm with the table of 50 Hz on any machine (Workshop,
question 6)."""
RATE = """        ld a, ($002B)           ; bit 7 is 1 on a 50 Hz machine (chapter 4)
        rla
        ld hl, work60           ; 60 Hz ...
        jr nc, .rate
        ld hl, work50           ; ... and 50 Hz
.rate:  ld (worktab), hl
"""


def program(kind):
    what, main, routines = KINDS[EXTRA.get(kind, kind)]
    body = setup()
    if kind == "after50":
        what = "the status line after the work, the 50 Hz table at any rate"
        assert RATE in body
        body = body.replace(RATE, "        ld hl, work50           ; the table of 50 Hz, at any rate\n"
                                  "        ld (worktab), hl\n")
    return (head(kind, what) + say_lines(SAYS[kind]) + RAM + IM2 + body + main + END +
            TURN + routines + BEST + ADDSC + SAY + ISR + COMMON + data() + CART_END)


# ------------------------------------------------------------------ the model
def bcd_add(num, points):
    """score + points, three BCD bytes, as addsc leaves them (999,999 wraps)"""
    value = int("".join(f"{b:02X}" for b in num)) + int(f"{points:02X}")
    s = f"{value % 1000000:06d}"
    return [int(s[i:i + 2], 16) for i in (0, 2, 4)]


def value(num):
    return int("".join(f"{b:02X}" for b in num))


def game():
    """the frames of the game: for each, the points, the score and hi after
    turn, in the order the programs see them"""
    score, hi = [0, 0, 0], list(HI0)
    out = []
    for k in range(FRAMES):
        pts = POINTS[k & 15]
        score = bcd_add(score, pts)
        if value(score) > value(hi):
            hi = list(score)
        out.append({"frame": k, "points": pts, "score": list(score), "hi": list(hi)})
    return out


def digits_of(num):
    return [d for b in num for d in (b >> 4, b & 15)]


def sends(kind):
    """for each status line the program sends, from its first to the one
    after the last frame: the VRAM writes, (address, name), in order"""
    kind = EXTRA.get(kind, kind)
    g = game()
    before = [{"score": [0, 0, 0], "hi": list(HI0)}] + g    # what status sees
    shown = {"score": [None] * 3, "hi": [None] * 3}
    out = []
    lines = before[:FRAMES + 1] if kind == "status" else g
    for st in lines:
        w = []
        for name, at in (("score", SCORE_AT), ("hi", HI_AT)):
            num = st[name]
            if kind == "blink":
                w += [(at + i, SPACE) for i in range(6)]
                w += [(at + i, d) for i, d in enumerate(digits_of(num))]
                continue
            for i, b in enumerate(num):
                if shown[name][i] != b:
                    shown[name][i] = b
                    w += [(at + 2 * i, b >> 4), (at + 2 * i + 1, b & 15)]
        out.append(w)
    return out


def vram_start():
    """the VRAM after the set-up, before the first frame"""
    v = bytearray(16384)
    v[0x0008:0x0010] = bytes(BRICK)
    v[0x1000:0x1050] = DIGIT_SHAPES
    v[0x1100:0x1400] = FONT
    v[0x2000:0x2800] = bytes([PAPER_C]) * 0x800
    v[0x2008:0x2010] = bytes([BRICK_C]) * 8
    v[0x3000:0x3800] = bytes([STATUS_C]) * 0x800
    v[0x1800:0x1A00] = bytes(room())
    v[0x1A00:0x1B00] = bytes([SPACE]) * 0x100
    v[ATT] = 0xD0
    for addr, text in LABELS:
        v[addr:addr + len(text)] = text.encode()
    return v


def vram_end(kind):
    kind = EXTRA.get(kind, kind)
    v = vram_start()
    for w in sends(kind):
        for a, n in w:
            v[a] = n
    v[OVER_AT:OVER_AT + len(OVER)] = OVER.encode()
    return v


def main():
    for kind in list(KINDS) + list(EXTRA):
        with open(os.path.join(HERE, f"{kind}.asm"), "w") as f:
            f.write(program(kind))
    print(" ".join(f"{k}.asm" for k in list(KINDS) + list(EXTRA)))


if __name__ == "__main__":
    main()
