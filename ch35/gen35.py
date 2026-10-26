#!/usr/bin/env python3
"""gen35.py - the programs of chapter 35: joysticks through the PSG.

    python3 gen35.py && ./build.sh

    sticks.asm    both joystick ports once a frame, from the PSG: register 15
                  chooses the port, register 14 gives its pins; each port as
                  eight boxes, its byte and the direction its four switches
                  make; and registers 15 and 7 as they read back (figure 35.1)
    gtstck.asm    the BIOS's GTSTCK for both ports and GTTRIG for the four
                  buttons, every frame, next to sticks.asm's own reading
    pins.asm      register 15 written fourteen ways, and register 14 read
                  after each: which of 15's bits the joystick feels
    leftover.asm  WHERE IT BREAKS: player 2 read with GTSTCK, player 1 read
                  from register 14 without choosing the port

Every program takes the interrupt in mode 2 (chapter 17), reads the PSG with
the interrupts off, prints in Graphic I, black ink on white, ends with
asmparts.CART_END, and build.sh assembles with --syntax=bFw. The joysticks'
moves are in NAME.events, written here: a frame counted from INIT, a port
and the switches held from that frame on (meas35.py turns them into
openMSX's key-joysticks).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "ch34"))
from asmparts import HEAD, CART_END, IM2, im2, BOX_EMPTY, BOX_FULL  # noqa: E402
import gen34  # noqa: E402  (chapter 34: the text screen, its shapes and its routines)
from gen26 import tidy, db_rows  # noqa: E402  (chapter 26)

BIOS = '        INCLUDE "bios.inc"\n'
EU, JP = "MSXBOOK_EU16", "MSXBOOK_JP16"
TEXT_REGS = gen34.TEXT_REGS
SWITCHES = ["up", "down", "left", "right", "a", "b"]        # bits 0 to 5 of register 14
PORT_BIT = {1: 0x00, 2: 0x40}                               # register 15, bit 6


def head(name, what):
    return HEAD.format(name=name, chapter=35, what=what) + BIOS


# ------------------------------------------------------------------ the direction
def direction(up, down, left, right):
    """the MSX's direction, 0 for none, 1 up and clockwise to 8 up-left: two
    opposite switches cancel each other"""
    dy = (1 if down else 0) - (1 if up else 0)
    dx = (1 if right else 0) - (1 if left else 0)
    return {(0, 0): 0, (0, -1): 1, (1, -1): 2, (1, 0): 3, (1, 1): 4,
            (0, 1): 5, (-1, 1): 6, (-1, 0): 7, (-1, -1): 8}[(dx, dy)]


def dirs_table():
    """16 bytes: the direction for each value of register 14's bits 0 to 3,
    a 0 for a switch closed"""
    return [direction(*[not n >> b & 1 for b in range(4)]) for n in range(16)]


# ------------------------------------------------------------------ the parts
RAM = """ticks   EQU VARS                ; frames counted by isr
port1   EQU VARS + 1            ; register 14 of port 1
port2   EQU VARS + 2            ; and of port 2
r15     EQU VARS + 3            ; register 15, read back
r7      EQU VARS + 4            ; register 7, read back
way1    EQU VARS + 5            ; the directions
way2    EQU VARS + 6
bios    EQU VARS + 8            ; gtstck.asm: GTSTCK 1 and 2, GTTRIG 1 to 4
iff     EQU VARS + 14           ; gtstck.asm: 4 if the interrupts are on
pins    EQU VARS + 16           ; pins.asm: register 14 after each write
"""

JOY = """
; joy: A = $00 for port 1, $40 for port 2 -> A = that port's register 14, a 0
; for each switch closed. Register 15's other seven bits are kept. The
; interrupts must be off. Uses A, B
joy:    ld b, a                 ;  5
        ld a, 15                ;  8
        out (PSG_ADDR), a       ; 12  register 15
        in a, (PSG_READ)        ; 12  as it is
        and $BF                 ;  8  bit 6: the port
        or b                    ;  5
        out (PSG_WRITE), a      ; 12
        ld a, 14                ;  8
        out (PSG_ADDR), a       ; 12  register 14
        in a, (PSG_READ)        ; 12  the port's pins
        ret                     ; 11
"""

DIR = """
; dir: A = register 14 -> A = the direction, 0 for none, 1 up and clockwise
; to 8 up-left, from its bits 0 to 3. Uses HL
dir:    and $0F                 ;  8
        ld hl, dirs             ; 11
        add a, l                ;  5
        ld l, a                 ;  5
        ld a, (hl)              ;  8
        ret                     ; 11
"""

READ_REG = """
; reg: A = a register of the PSG -> A = its value. Uses A
reg:    out (PSG_ADDR), a
        in a, (PSG_READ)
        ret
"""


def dirs_data():
    return ("        ALIGN 16\ndirs:                           ; the direction for bits 0-3 of register 14\n" +
            db_rows(dirs_table(), 16))


def text_tail(names):
    return ("names:                          ; 24 rows of 32\n" + db_rows(names, 16) +
            "shapes:                         ; codes 0 to 127\n" + db_rows(gen34.own_shapes(), 16))


def show(row, col, var, kind):
    """the lines that print VAR at ROW, COLUMN: kind "keys" as boxes (a 0
    filled) and its byte, "bits" as boxes (a 1 filled) and its byte, "way" as a
    digit, "flag" as two hexadecimal digits"""
    at = f"""        ld d, {row}
        ld e, {col}
        call at
        ld a, ({var})
"""
    if kind == "way":
        return at + """        add a, '0'
        out (VDP_DATA), a
"""
    if kind == "flag":
        return at + "        call hex\n"
    boxes = at + ("        cpl\n" if kind == "bits" else "") + "        call cells\n"
    return boxes + f"""        ld e, {col + 10}
        call at
        ld a, ({var})
        call hex
"""


FRAME = """        VDP_REG 1, $E0          ; the display on, and the frame's signal
        in a, (VDP_CTRL)
main:   ei
        halt                    ; wait for the frame
        di                      ; the interrupts off: the PSG, then the VDP
"""


# ------------------------------------------------------------------ sticks.asm
STICK_ROWS = {1: 3, 2: 5}
REG_ROWS = {15: 8, 7: 10}
BOX_COL, WAY_COL = 6, 22


def sticks_texts():
    t = [(1, 0, "port  76BARLDU  R#14  way")]
    for p, row in STICK_ROWS.items():
        t += [(row, 2, str(p)), (row, BOX_COL, [BOX_EMPTY] * 8), (row, BOX_COL + 10, "BF"),
              (row, WAY_COL, "0")]
    for r, row in REG_ROWS.items():
        t += [(row, 0, f"R#{r}"), (row, BOX_COL, [BOX_EMPTY] * 8), (row, BOX_COL + 10, "00")]
    return t


def sticks():
    body = gen34.setup(TEXT_REGS) + im2("isr") + FRAME + """        xor a                   ; port 1
        call joy
        ld (port1), a
        call dir
        ld (way1), a
        ld a, $40               ; port 2
        call joy
        ld (port2), a
        call dir
        ld (way2), a
        ld a, 15                ; registers 15 and 7, as they read back
        call reg
        ld (r15), a
        ld a, 7
        call reg
        ld (r7), a
read:
""" + "".join(show(STICK_ROWS[p], BOX_COL, f"port{p}", "keys") + show(STICK_ROWS[p], WAY_COL, f"way{p}", "way")
              for p in (1, 2)) + \
        "".join(show(REG_ROWS[r], BOX_COL, f"r{r}", "bits") for r in (15, 7)) + "        jp main\n"
    say = """; Both joystick ports once a frame: register 15 of the PSG chooses the port,
; register 14 gives its pins, a 0 for each switch closed. Each port as eight
; boxes from bit 7, a filled box for a 0, its byte and its direction; then
; registers 15 and 7 as they read back, a filled box for a 1.
"""
    return (head("sticks", "both joysticks, from the PSG") + RAM + IM2 + say +
            tidy(body + JOY + DIR + READ_REG + gen34.ISR + gen34.PRINT) + dirs_data() +
            text_tail(gen34.page(sticks_texts())) + CART_END)


# ------------------------------------------------------------------ gtstck.asm
BIOS_LINES = [(3, "GTSTCK 1", "bios"), (4, "GTSTCK 2", "bios + 1"), (5, "own 1", "way1"),
              (6, "own 2", "way2"), (8, "GTTRIG 1", "bios + 2"), (9, "GTTRIG 2", "bios + 3"),
              (10, "GTTRIG 3", "bios + 4"), (11, "GTTRIG 4", "bios + 5")]
BIOS_COL = 10


def gtstck_texts():
    t = [(1, 0, "the BIOS, and sticks.asm's way")]
    for row, label, _ in BIOS_LINES:
        t += [(row, 0, label), (row, BIOS_COL, "0" if "TRIG" not in label else "00")]
    return t


def gtstck():
    calls = ""
    for k in (1, 2):
        calls += f"""        ld a, {k}
s{k}:     call GTSTCK             ; port {k}: its direction
        ld (bios + {k - 1}), a
"""
    for k in (1, 2, 3, 4):
        calls += f"""        ld a, {k}
g{k}:     call GTTRIG             ; {"AB"[k > 2]} of port {2 - k % 2}: $FF if held
        ld (bios + {k + 1}), a
"""
    body = gen34.setup(TEXT_REGS) + im2("isr") + FRAME + calls + """after:  ld a, i                  ; P/V: the interrupts on or off (chapter 17)
        ld a, 0
        jp po, .off
        ld a, 4
.off:   ld (iff), a
        di
        xor a                   ; and the same two ports, read here
        call joy
        call dir
        ld (way1), a
        ld a, $40
        call joy
        call dir
        ld (way2), a
read:
""" + "".join(show(row, BIOS_COL, var, "flag" if "TRIG" in label else "way")
              for row, label, var in BIOS_LINES) + "        jp main\n"
    say = """; The BIOS's GTSTCK for ports 1 and 2 and GTTRIG for their four buttons every
; frame, and the same two ports read from the PSG with joy and dir.
"""
    return (head("gtstck", "GTSTCK and GTTRIG") + RAM + IM2 + say +
            tidy(body + JOY + DIR + gen34.ISR + gen34.PRINT) + dirs_data() +
            text_tail(gen34.page(gtstck_texts())) + CART_END)


# ------------------------------------------------------------------ pins.asm
PIN_VALUES = [0x8F, 0x00, 0x03, 0x0F, 0x80, 0x10, 0x9F, 0x20, 0xAF, 0xBF, 0xCF, 0x40, 0x4C, 0xFF]
PIN_TOP = 3


def pins_texts():
    t = [(1, 0, "R#15  R#14")]
    for k, v in enumerate(PIN_VALUES):
        t += [(PIN_TOP + k, 0, f"{v:02X}"), (PIN_TOP + k, 6, "BF")]
    return t


def pins():
    body = gen34.setup(TEXT_REGS) + im2("isr") + FRAME + f"""        ld hl, values
        ld de, pins
        ld b, {len(PIN_VALUES)}
value:  ld a, 15
        out (PSG_ADDR), a
        ld a, (hl)
written:
        out (PSG_WRITE), a      ; register 15, one of the values
        ld a, 14
        out (PSG_ADDR), a
        in a, (PSG_READ)        ; register 14
        ld (de), a
        inc hl
        inc de
        djnz value
        ld a, 15                ; register 15 back as the BIOS left it
        out (PSG_ADDR), a
        ld a, ${PIN_VALUES[0]:02X}
        out (PSG_WRITE), a
read:   ld hl, pins
        ld d, {PIN_TOP}
.row:   ld e, 6
        push hl
        call at
        pop hl
        ld a, (hl)
        call hex
        inc hl
        inc d
        ld a, d
        cp {PIN_TOP + len(PIN_VALUES)}
        jr nz, .row
        jp main
"""
    say = f"""; Register 15 written {len(PIN_VALUES)} ways in a row, and register 14 read after each:
; which of 15's bits joystick port 1 feels. Then 15 back as the BIOS left it.
"""
    return (head("pins", "register 15, bit by bit") + RAM + IM2 + say +
            tidy(body + gen34.ISR + gen34.PRINT) +
            "values:                         ; written to register 15\n" + db_rows(PIN_VALUES, 14) +
            text_tail(gen34.page(pins_texts())) + CART_END)


# ------------------------------------------------------------------ leftover.asm
LEFT_LINES = [(3, "player 1", "way1"), (5, "player 2", "way2")]


def leftover_texts():
    t = [(1, 0, "player   way")]
    for row, label, _ in LEFT_LINES:
        t += [(row, 0, label), (row, 9, "0")]
    return t


def leftover():
    body = gen34.setup(TEXT_REGS) + im2("isr") + FRAME + """        ld a, 14                ; player 1: register 14, port 1 assumed
        out (PSG_ADDR), a
        in a, (PSG_READ)
        call dir
        ld (way1), a
        ld a, 2                 ; player 2: the BIOS
        call GTSTCK
        di
        ld (way2), a
read:
""" + "".join(show(row, 9, var, "way") for row, _, var in LEFT_LINES) + "        jp main\n"
    say = """; WHERE IT BREAKS. Player 2 read with GTSTCK, which chooses port 2 in register
; 15 and leaves it chosen; player 1 read from register 14 without choosing.
"""
    return (head("leftover", "the port the BIOS left chosen") + RAM + IM2 + say +
            tidy(body + DIR + gen34.ISR + gen34.PRINT) + dirs_data() +
            text_tail(gen34.page(leftover_texts())) + CART_END)


# ------------------------------------------------------------------ players.asm
DARK_BLUE, CYAN, BLACK = 4, 7, 1
COLOURS = {1: (BLACK, DARK_BLUE), 2: (CYAN, DARK_BLUE)}    # a press of A swaps the two
STARTS = {1: (80, 96), 2: (160, 96)}                        # X, Y
SPRITE_REGS = gen34.SPRITE_REGS


def kbd_table():
    """16 bytes: register 14's bits 0-3 for the cursor keys' bits in row 8,
    LEFT, UP, DOWN, RIGHT in bits 0 to 3 of the index, a 0 when held"""
    out = []
    for n in range(16):
        left, up, down, right = [not n >> b & 1 for b in range(4)]
        out.append(sum(1 << b for b, h in enumerate((up, down, left, right)) if not h))
    return out


PLAYERS_RAM = """last1   EQU VARS + 8            ; each player's bits, the last frame
last2   EQU VARS + 9
fig1    EQU VARS + 16           ; the two figures: Y, X, pattern, colour
fig2    EQU VARS + 20
"""

KEYS = """
; keys: row 8 of the keyboard -> A in register 14's way: the cursor keys as
; the four switches, SPACE as button A, a 0 for each held. The interrupts
; must be off. Uses A, C, HL
keys:   in a, (PPI_C)           ; 12
        and $F0                 ;  8  port C's top bits kept (chapter 34)
        or 8                    ;  8
        out (PPI_C), a          ; 12  row 8
        in a, (PPI_B)           ; 12  bits 7-4: RIGHT DOWN UP LEFT; bit 0: SPACE
        ld c, a                 ;  5
        rrca                    ;  5
        rrca                    ;  5
        rrca                    ;  5
        rrca                    ;  5
        and $0F                 ;  8
        ld hl, kbdjoy           ; 11
        add a, l                ;  5
        ld l, a                 ;  5
        ld a, c                 ;  5
        and 1                   ;  8  SPACE
        rlca                    ;  5
        rlca                    ;  5
        rlca                    ;  5
        rlca                    ;  5  into bit 4, button A's
        or (hl)                 ;  8  and the cursor keys as the switches
        or $E0                  ;  8
        ret                     ; 11
"""

MOVE = """
; move: A = a player's bits, a 0 for each switch held; IX = its figure's Y,
; X, pattern and colour; HL = its bits of the last frame. A pixel for each
; switch held, so that two opposite ones cancel; a press of A, held now and
; not the last frame, swaps the figure's two colours. Uses A, B, C
move:   ld b, a
        ld c, (hl)              ; the last frame's bits
        ld (hl), a              ; this frame's, for the next
        rrca                    ; up
        jr c, .down
        dec (ix + 0)
.down:  rrca
        jr c, .left
        inc (ix + 0)
.left:  rrca
        jr c, .right
        dec (ix + 1)
.right: rrca
        jr c, .fire
        inc (ix + 1)
.fire:  ld a, b                 ; A: held now (a 0) and not before (a 1)
        cpl
        and c
        and $10
        ret z
        ld a, (ix + 3)          ; the other colour: the two XORed
        xor {xor1}
        ld (ix + 3), a
        ret
"""


def players_texts():
    return [(1, 0, "two players")]


def players():
    figs = ""
    for p in (1, 2):
        x, y = STARTS[p]
        figs += f"""        ld hl, fig{p}           ; figure {p}: Y, X, pattern 0, its first colour
        ld (hl), {y}
        inc hl
        ld (hl), {x}
        inc hl
        ld (hl), 0
        inc hl
        ld (hl), {COLOURS[p][0]}
"""
    body = gen34.setup(SPRITE_REGS, sprite=True) + figs + """        ld a, $FF
        ld (last1), a
        ld (last2), a
""" + im2("isr") + """        VDP_REG 1, $E2          ; the display on, the signal, sprites of 16 x 16
        in a, (VDP_CTRL)
main:   ei
        halt                    ; wait for the frame
        di                      ; the interrupts off: VDP, PSG and PPI
frame:  VRAM_WRITE $1B00        ; the two figures, in the lines not drawn
        ld hl, fig1
        ld bc, 8 << 8 | VDP_DATA
        otir
        ld a, $D0
        out (VDP_DATA), a
        call keys               ; player 1: the cursor keys and SPACE ...
        ld d, a
        xor a                   ; ... and joystick 1, together
        call joy
        and d
read:   ld ix, fig1
        ld hl, last1
        call move
        ld a, $40               ; player 2: joystick 2
        call joy
        ld ix, fig2
        ld hl, last2
        call move
        jp main
"""
    say = """; Two players: two figures, player 1 moved by joystick 1 and by the cursor
; keys, with SPACE for button A, player 2 by joystick 2. A pixel a frame for
; each switch held; each press of button A swaps the figure's two colours.
"""
    xor = {p: COLOURS[p][0] ^ COLOURS[p][1] for p in (1, 2)}
    assert xor[1] != xor[2]
    # the colour swap is written for each player: the XOR of its two colours
    move1 = MOVE.replace("move:", "move1:").replace("{xor1}", str(xor[1]))
    move2 = MOVE.replace("move:", "move2:").replace("{xor1}", str(xor[2]))
    body = body.replace("call move\n        ld a, $40", "call move1\n        ld a, $40").replace(
        "ld hl, last2\n        call move\n", "ld hl, last2\n        call move2\n")
    return (head("players", "two players, a joystick and the keys") + RAM + PLAYERS_RAM + IM2 + say +
            tidy(body + KEYS + move1 + move2 + JOY + gen34.ISR + gen34.PRINT) +
            "        ALIGN 16\nkbdjoy:                         ; register 14's bits 0-3 for the cursor keys\n" +
            db_rows(kbd_table(), 16) + text_tail(gen34.page(players_texts())) +
            "figure:                         ; chapter 26's figure\n" + db_rows(gen34.FIGURE, 16) + CART_END)


# ------------------------------------------------------------------ the moves
# (frame, port, switches held from then on); "-" is none
STICK_MOVES = [(20, 1, "up"), (24, 1, "up right"), (28, 1, "right"), (32, 1, "down right"),
               (36, 1, "down"), (40, 1, "down left"), (44, 1, "left"), (48, 1, "up left"),
               (52, 1, "a"), (56, 1, "b"), (60, 1, "a b"), (64, 1, "-"),
               (68, 2, "up"), (72, 2, "right a"), (76, 1, "left b"), (80, 1, "-"), (80, 2, "-"),
               (84, 2, "b"), (86, 2, "-")]
# every one of the sixteen ways to hold the four switches, on each port
COMBOS_FROM, COMBOS_EVERY = 90, 3


def combo_moves():
    out = []
    for p in (1, 2):
        for n in range(16):
            held = " ".join(s for b, s in enumerate(SWITCHES[:4]) if n >> b & 1) or "-"
            out.append((COMBOS_FROM + COMBOS_EVERY * (16 * (p - 1) + n), p, held))
        out.append((COMBOS_FROM + COMBOS_EVERY * 16 * p, p, "-"))
    return out


STICKS_FRAMES = COMBOS_FROM + COMBOS_EVERY * 32 + 6
PIN_MOVES = [(10, 1, "a"), (14, 1, "b"), (18, 1, "up"), (22, 1, "up a b"), (26, 1, "-")]
PINS_FRAMES = 30
LEFT_MOVES = [(10, 1, "right"), (20, 2, "up"), (30, 1, "-"), (34, 2, "-")]
LEFTOVER_FRAMES = 40

# "k" is the keyboard: the cursor keys and SPACE, as a joystick's switches and button A
PLAYER_MOVES = [(10, 1, "right"), (30, 1, "right up"), (40, 1, "-"), (44, 1, "a"), (48, 1, "-"),
                (52, "k", "left"), (62, "k", "left down a"), (66, "k", "left down"), (72, "k", "-"),
                (76, 1, "right"), (76, "k", "left"), (86, 1, "-"), (86, "k", "up"), (96, "k", "-"),
                (20, 2, "down"), (40, 2, "down left a"), (44, 2, "down left"), (50, 2, "a"),
                (54, 2, "-"), (100, 2, "up")]
PLAYERS_FRAMES = 110

MOVES = {"sticks": lambda: STICK_MOVES + combo_moves(), "gtstck": lambda: STICK_MOVES + combo_moves(),
         "players": lambda: PLAYER_MOVES,
         "pins": lambda: PIN_MOVES, "leftover": lambda: LEFT_MOVES}
FRAMES = {"sticks": STICKS_FRAMES, "gtstck": STICKS_FRAMES, "pins": PINS_FRAMES, "players": PLAYERS_FRAMES,
          "leftover": LEFTOVER_FRAMES}


def write_events(name):
    lines = [f"# {name}.events -- chapter 35: the joysticks {name}.rom is given, generated by gen35.py",
             "# frame (from INIT), port, and the switches held from that frame on (- for none);",
             "# port k is the keyboard: the cursor keys as the switches, SPACE as button A"]
    lines += [f"{f} {p} {held}" for f, p, held in sorted(MOVES[name](), key=lambda m: (m[0], str(m[1])))]
    with open(os.path.join(HERE, f"{name}.events"), "w") as f:
        f.write("\n".join(lines) + "\n")


PROGRAMS = {"sticks": sticks, "gtstck": gtstck, "pins": pins, "players": players, "leftover": leftover}


def main():
    for name, make in PROGRAMS.items():
        with open(os.path.join(HERE, f"{name}.asm"), "w") as f:
            f.write(make())
        write_events(name)
    print(" ".join(f"{n}.asm" for n in PROGRAMS))


if __name__ == "__main__":
    main()
