#!/usr/bin/env python3
"""gen27.py - the programs of chapter 27: hardware sprites II.

    python3 gen27.py && ./build.sh

    five.asm       four figures on a line and a ball half on it: the ball is
                   not drawn on the lines it shares with them (figure 27.1)
    first.asm      the same, the ball first in the table: the last figure is
                   the one cut (figure 27.1)
    stagger.asm    eight figures in two rows, four on a line (figure 27.3)
    status.asm     six tables of sprites in turn, 8 frames each, and the
                   status read once a frame by an interrupt routine: 5S and
                   the number it leaves
    rotate.asm     eight figures on a line: the table sent as it is, then
                   turned by four entries every frame (figure 27.4)
    hero.asm       a ball kept first in the table and seven figures turned
                   behind it, by one entry a frame and then by three
    layers.asm     faces of two colours, each two sprites, three on a line
                   (figure 27.2)
    poll.asm       WHERE IT BREAKS: six figures on a line, and the table
                   turned by two entries only when the status that ended the
                   wait says 5S (figure 27.5)
    keep.asm       the same, 5S taken from every read of the wait
    once.asm       the same six, 5S read once a frame by the interrupt routine;
                   then the six in two rows, and the table stands

Graphic II as a bitmap (chapter 22's GRAPHIC2, black ink on white), the
sprite attributes at $1B00 and the patterns at $3800 (chapter 26); sprites of
16 x 16. Every program writes with the display off first; status.asm takes
the interrupt in mode 2 (chapter 17), the others keep the interrupts off and
wait for the end of the paper on the status. Each ends with
asmparts.CART_END, and build.sh assembles with --syntax=bFw.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "ch26"))
from asmparts import HEAD, CART_END, GRAPHIC2, IM2, im2  # noqa: E402
from gen26 import tidy, db_rows, big, rows16, FIGURE, BALL, BLOCK  # noqa: E402  (chapter 26)

BIOS = '        INCLUDE "bios.inc"\n'
BLACK, LIGHT_GREEN, DARK_BLUE, WHITE = 1, 3, 4, 15
ATT, PAT = 0x1B00, 0x3800
END = 0xD0
COPY = 0xC400               # a copy of the attributes, in the RAM
LOG = 0xC600                # status.asm, poll.asm, keep.asm: what each frame read


def head(name, what):
    return HEAD.format(name=name, chapter=27, what=what) + BIOS


# ------------------------------------------------------------------ shapes
FACE = rows16(               # a face of two colours: the outline, black...
    ".....######.....", "...##......##...", "..#..........#..", ".#............#.",
    ".#...##..##...#.", "#....##..##....#", "#..............#", "#..............#",
    "#..............#", "#...#......#...#", ".#...######...#.", ".#............#.",
    "..#..........#..", "...##......##...", ".....######.....", "................")


def inside(rows):
    """the pixels between each row's first and last, not in the row"""
    out = []
    for r in rows:
        xs = [x for x in range(16) if r & 0x8000 >> x]
        fill = 0
        if xs:
            for x in range(min(xs) + 1, max(xs)):
                if not r & 0x8000 >> x:
                    fill |= 0x8000 >> x
        out.append(fill)
    return out


FILL = inside(FACE)          # ... and what is inside it, light green
for _o, _f in zip(FACE, FILL):
    assert not _o & _f, "the two share no pixel: no coincidence (chapter 39)"
SHAPES = {"figure": 0, "ball": 4, "block": 8, "face": 12, "fill": 16}
PATTERNS = big(FIGURE) + big(BALL) + big(BLOCK) + big(FACE) + big(FILL)


# ------------------------------------------------------------------ parts
SPRITES = f"""        VRAM_WRITE ${PAT:04X}        ; the sprite patterns
        ld hl, patterns
        ld c, VDP_DATA
        ld b, {len(PATTERNS)}
        otir
"""
FRAME = """
; frame: wait for the end of the paper: F, bit 7 of the status, read with the
; interrupts off (chapter 19)
frame:  in a, (VDP_CTRL)
        rla
        jr nc, frame
        ret
"""
CLEAR_F = "        in a, (VDP_CTRL)        ; F cleared: the first wait ends with a paper\n"
WHOLE = CLEAR_F + "        call frame              ; to the end of this paper: the next wait is whole\n"
DONE = "done:   jr done\n"


def table_bytes(table):
    return [b for s in table for b in s] + ([END] if len(table) < 32 else [])


def send(table, label="atts"):
    return f"""        VRAM_WRITE ${ATT:04X}        ; the attributes
        ld hl, {label}
        ld c, VDP_DATA
        ld b, {len(table_bytes(table))}
        otir
"""


def program(name, what, say, body, data="", extra="", sub=""):
    return (head(name, what) + say + extra + GRAPHIC2 + tidy(SPRITES + body + DONE + sub + FRAME) +
            "patterns:\n" + db_rows(PATTERNS) + data + CART_END)


def row(y, xs, shape, colour=BLACK):
    return [(y, x, SHAPES[shape], colour) for x in xs]


# ------------------------------------------------------------------ five.asm
FIVE = row(79, (24, 72, 120, 168), "figure") + [(87, 216, SHAPES["ball"], DARK_BLUE)]


def five():
    return program("five", "four on a line, and a fifth", """; Four figures of 16 x 16, sprites 0 to 3, on lines 80 to 95, and a ball,
; sprite 4, on lines 88 to 103: on lines 88 to 95 it is the fifth.
""", send(FIVE) + "        VDP_REG 1, $C2          ; the display on, sprites of 16 x 16\n",
        "atts:\n" + db_rows(table_bytes(FIVE), 4))


FIRST = FIVE[4:] + FIVE[:4]     # the ball first in the table


def first():
    return program("first", "the same five, the ball first", """; five.asm's ball and four figures, the ball first in the table, sprite 0, and
; the figures sprites 1 to 4: on lines 88 to 95 the fifth is the last figure.
""", send(FIRST) + "        VDP_REG 1, $C2          ; the display on, sprites of 16 x 16\n",
        "atts:\n" + db_rows(table_bytes(FIRST), 4))


# ------------------------------------------------------------------ stagger.asm
STAGGER = [(79 + 16 * (k % 2), 8 + 30 * k, SHAPES["figure"], BLACK) for k in range(8)]


def stagger():
    return program("stagger", "eight figures, four on a line", """; rotate.asm's eight figures in two rows: the even ones on lines 80 to 95,
; the odd ones on lines 96 to 111. No line has more than four.
""", send(STAGGER) + "        VDP_REG 1, $C2          ; the display on, sprites of 16 x 16\n",
        "atts:\n" + db_rows(table_bytes(STAGGER), 4))


# ------------------------------------------------------------------ status.asm
def herd32():
    """32 figures in eight rows of four, 23 lines apart (chapter 26)"""
    return [(6 + 23 * r, (64 * c + 16 * r) & 0xFF, SHAPES["block"], BLACK)
            for r in range(8) for c in range(4)]


XS6 = [8 + 40 * k for k in range(6)]
STATES = [  # what, the table
    ("four on a line", row(99, XS6[:4], "block")),
    ("six on a line", row(99, XS6, "block")),
    ("five on two lines", row(149, XS6[:5], "block") + row(49, XS6[:5], "block")),
    ("a fifth in colour 0", row(99, XS6[:4], "block") + row(99, XS6[4:5], "block", 0)),
    ("five below the paper", row(194, XS6[:5], "block")),
    ("thirty-two, none fifth", herd32())]
STATE_FRAMES = 8


def status():
    tables = ""
    for k, (what, table) in enumerate(STATES):
        tables += f"state{k}:                         ; {what}\n" + db_rows(table_bytes(table), 4)
    states = ""
    for k, (what, table) in enumerate(STATES):
        states += f"""        ld b, {STATE_FRAMES}                ; {what}
w{k}:     halt                    ; the paper ended: the routine read the status
        djnz w{k}
s{k}:     VRAM_WRITE ${ATT:04X}
        ld hl, state{k}
        ld c, VDP_DATA
        ld b, {len(table_bytes(table))}
        otir
e{k}:
"""
    return program("status", "the status, read once a frame", f"""; Six tables of sprites in turn, {STATE_FRAMES} frames each. The interrupt routine, in
; mode 2, reads the status at the end of every paper, once, and keeps it in
; a list at log; the program sends each table after a paper has ended.
""", f"""        ld hl, log
        ld (next), hl
""" + im2("irq") + f"""        VDP_REG 1, $E2          ; the display on, sprites of 16 x 16, the interrupt on
        in a, (VDP_CTRL)        ; nothing left from before
        ei
""" + states + f"""        ld b, {STATE_FRAMES}
last:   halt
        djnz last
        di
""", tables, extra=IM2 + f"""log     EQU ${LOG:04X}               ; a status a frame
next    EQU VARS                ; where the next one goes
""").replace("done:   jr done\n", """done:   jr done

; irq: the status, read once at the end of the paper, into the list
irq:    push af
        in a, (VDP_CTRL)        ; 12  the status: F, 5S, C and the number
        push hl
        ld hl, (next)
        ld (hl), a
        inc hl
        ld (next), hl
        pop hl
        pop af
        ei
        ret
""")


# ------------------------------------------------------------------ rotate.asm
XS8 = [8 + 30 * k for k in range(8)]
ROT = row(87, XS8, "figure")
STILL_FRAMES, TURN_FRAMES, TURN = 16, 48, 4


def rotate_tables():
    """the table each frame shows: STILL_FRAMES as it is, then turned by
    TURN entries more every frame"""
    out = []
    for f in range(STILL_FRAMES + TURN_FRAMES):
        k = 0 if f < STILL_FRAMES else (TURN * (f - STILL_FRAMES + 1)) % len(ROT)
        out.append([ROT[(k + i) % len(ROT)] for i in range(len(ROT))])
    return out


def rotate():
    n = len(ROT)
    return program("rotate", "eight on a line, the table turned", f"""; Eight figures on lines 88 to 103. For {STILL_FRAMES} frames the table is sent as it is;
; then, for {TURN_FRAMES} frames, it is sent from entry k, k going up by {TURN} each frame
; and round from {n - 1} to 0: the figures the VDP leaves out change places.
""", f"""        ld hl, atts             ; the copy: the eight entries twice, so that
        ld de, copy             ; eight from any of them are in a row
        ld bc, {4 * n}
        ldir
        ld hl, atts
        ld bc, {4 * n}
        ldir
""" + send(ROT) + """        VDP_REG 1, $C2          ; the display on, sprites of 16 x 16
""" + CLEAR_F + f"""        ld e, {STILL_FRAMES}
still:  call frame
        dec e
        jr nz, still
        ld e, {TURN_FRAMES}
        ld d, 0                 ; k, times 4: the first entry sent
next:   ld a, d                 ;  5  k + {TURN}, round {n}: times 4, round {4 * n}
        add a, {4 * TURN}               ;  8
        and {4 * n - 1}                  ;  8
        ld d, a                 ;  5
        call frame              ; the paper has ended
m0:     VRAM_WRITE ${ATT:04X}        ; 40
        ld hl, copy             ; 11  the copy from entry k
        ld b, 0                 ;  8
        ld c, d                 ;  5
        add hl, bc              ; 12
        ld c, VDP_DATA          ;  8
        ld b, {4 * n}                ;  8  eight entries
        otir                    ; 23 a byte, 18 the last
m1:     dec e
        jr nz, next
""", "atts:\n" + db_rows(table_bytes(ROT), 4),
        extra=f"copy    EQU ${COPY:04X}               ; the entries twice ($D0 sent once)\n")


# ------------------------------------------------------------------ hero.asm
HERO = (87, 8, SHAPES["ball"], DARK_BLUE)       # sprite 0, never turned
FOES = row(87, [38 + 30 * k for k in range(7)], "figure")
HERO_STEPS, HERO_FRAMES = (1, 3), 42            # by one entry, then by three


def hero_tables():
    """the table each frame shows: the ball first, then the seven figures
    from entry k, k going up by HERO_STEPS[0] for HERO_FRAMES frames, then by
    HERO_STEPS[1]"""
    out, k = [], 0
    for step in HERO_STEPS:
        for _ in range(HERO_FRAMES):
            k = (k + step) % len(FOES)
            out.append([HERO] + [FOES[(k + i) % len(FOES)] for i in range(len(FOES))])
    return out


def hero():
    n = len(FOES)
    t = [HERO] + FOES
    return program("hero", "one sprite kept, seven turned", f"""; A dark blue ball, sprite 0, and seven figures on lines 88 to 103: the
; ball first in every table, the figures turned behind it, for {HERO_FRAMES} frames by
; {HERO_STEPS[0]} entry, then for {HERO_FRAMES} by {HERO_STEPS[1]}. Three places are left for seven figures.
""", f"""        ld hl, atts + 4         ; the copy: the seven figures twice
        ld de, copy
        ld bc, {4 * n}
        ldir
        ld hl, atts + 4
        ld bc, {4 * n}
        ldir
""" + send(t) + """        VDP_REG 1, $C2          ; the display on, sprites of 16 x 16
""" + CLEAR_F + f"""        ld d, 0                 ; k, times 4: the first figure sent
        ld a, {4 * HERO_STEPS[0]}                 ; by {HERO_STEPS[0]} entry
        ld (step), a
        ld e, {HERO_FRAMES}
        call turns
        ld a, {4 * HERO_STEPS[1]}                ; by {HERO_STEPS[1]} entries
        ld (step), a
        ld e, {HERO_FRAMES}
        call turns
""", sub=f"""
; turns: E frames, each the ball and the figures from entry k, k going up by
; step / 4 entries, round {n}
turns:  ld a, (step)            ; 14
        add a, d                ;  5
        cp {4 * n}                   ;  8
        jr c, round             ; 13, or 8
        sub {4 * n}                  ;  8
round:  ld d, a                 ;  5
        call frame              ; the paper has ended
m0:     VRAM_WRITE ${ATT:04X}        ; 40
        ld hl, atts             ; 11  the ball, from the cartridge
        ld c, VDP_DATA          ;  8
        ld b, 4                 ;  8
        otir                    ; 23 a byte, 18 the last
        ld hl, copy             ; 11  the figures, from entry k
        ld c, d                 ;  5  B is 0: OTIR left it so
        add hl, bc              ; 12
        ld c, VDP_DATA          ;  8
        ld b, {4 * n}                ;  8  seven entries
        otir                    ; 23 a byte, 18 the last
m1:     dec e
        jr nz, turns
        ret
""", data="atts:\n" + db_rows(table_bytes(t), 4),
        extra=f"""copy    EQU ${COPY:04X}               ; the figures twice ($D0 sent once)
step    EQU VARS                ; 4 x the entries to turn by
""")


# ------------------------------------------------------------------ layers.asm
LAYER_XS = (40, 104, 168)


def layer_table():
    """three faces on lines 88 to 103, each the outline and then its fill,
    and two more on lines 136 to 151"""
    out = []
    for y, xs in ((87, LAYER_XS), (135, LAYER_XS[:2])):
        for x in xs:
            out += [(y, x, SHAPES["face"], BLACK),
                    (y, x, SHAPES["fill"], LIGHT_GREEN)]
    return out


def layers():
    t = layer_table()
    return program("layers", "faces of two sprites", """; Faces of two colours, each a black outline and a light green fill, two
; sprites: three faces on lines 88 to 103, sprites 0 to 5, and two on lines
; 136 to 151, sprites 6 to 9.
""", send(t) + "        VDP_REG 1, $C2          ; the display on, sprites of 16 x 16\n",
        "atts:\n" + db_rows(table_bytes(t), 4))


# ------------------------------------------------------------------ poll, keep
XS6B = [16 + 40 * k for k in range(6)]
SIX = row(87, XS6B, "figure")
SIX_FRAMES, SIX_TURN = 48, 2


def adaptive(name):
    keep = name == "keep"
    n = len(SIX)
    wait = f"""wait:   in a, (VDP_CTRL)        ; 12  the status
        ld c, a                 ;  5
        or b                    ;  5  every read's bits, kept in B
        ld b, a                 ;  5
        bit 7, c                ; 10  F: the paper has ended
        jr z, wait              ; 13, or 8
        ld a, {'b' if keep else 'c'}                 ;  5  {'5S from any read of the wait' if keep else 'the status that ended the wait'}
"""
    say = (f"""; WHERE IT BREAKS. Six figures on lines 88 to 103. Every frame the program
; waits for F, and if the status that ended the wait says 5S, a sprite was
; left out, it sends the table turned by {SIX_TURN} entries more; else as before.
""" if not keep else f"""; poll.asm's six figures, with 5S taken from every read of the wait, whose
; bits are ORed together in B, and not only from the one that found F.
""")
    return program(name, "5S from the read that found F" if not keep else "5S from every read",
                   say, f"""        ld hl, atts             ; the copy: the six entries twice
        ld de, copy
        ld bc, {4 * n}
        ldir
        ld hl, atts
        ld bc, {4 * n}
        ldir
        ld hl, log
        ld (next), hl
""" + send(SIX) + """        VDP_REG 1, $C2          ; the display on, sprites of 16 x 16
""" + WHOLE + f"""        ld e, {SIX_FRAMES}
        ld d, 0                 ; k, times 4: the first entry sent
frame6: ld b, 0                 ; nothing seen yet
""" + wait + f"""m0:     ld hl, (next)           ; the status, and the OR of the wait, kept
        ld (hl), c
        inc hl
        ld (hl), b
        inc hl
        ld (next), hl
        and $40                 ; 5S?
        jr z, same
        ld a, d                 ; a sprite left out: k + {SIX_TURN}, round {n}
        add a, {4 * SIX_TURN}
        cp {4 * n}
        jr c, inside
        sub {4 * n}
inside: ld d, a
same:   VRAM_WRITE ${ATT:04X}        ; the copy from entry k
        ld hl, copy
        ld b, 0
        ld c, d
        add hl, bc
        ld c, VDP_DATA
        ld b, {4 * n}
        otir
m1:     dec e
        jr nz, frame6
""",
        "atts:\n" + db_rows(table_bytes(SIX), 4),
        extra=f"""copy    EQU ${COPY:04X}               ; the entries twice ($D0 sent once)
log     EQU ${LOG:04X}               ; the status that ended each wait, and the OR
next    EQU VARS                ; where the next two go
""")


# ------------------------------------------------------------------ once.asm
SIX2 = [(79 + 16 * (k % 2), x, p, c) for k, (y, x, p, c) in enumerate(SIX)]   # three on a line
ONCE_FRAMES = 48
COPY2 = COPY + 0x80


def once():
    n = len(SIX)
    return program("once", "5S read once a frame, by the routine", f"""; poll.asm's six figures, with the status read as status.asm reads it: once a
; frame, by the interrupt routine. For {ONCE_FRAMES} frames the six are on lines 88 to
; 103, then for {ONCE_FRAMES} the same six in two rows, three on a line; every frame
; the table is turned by {SIX_TURN} entries more only if the routine found 5S.
""", f"""        ld hl, atts             ; the two copies: each six entries twice
        ld de, copy
        ld bc, {4 * n}
        ldir
        ld hl, atts
        ld bc, {4 * n}
        ldir
        ld hl, rows
        ld de, copy2
        ld bc, {4 * n}
        ldir
        ld hl, rows
        ld bc, {4 * n}
        ldir
""" + send(SIX) + im2("irq") + """        VDP_REG 1, $E2          ; the display on, sprites of 16 x 16, the interrupt on
""" + WHOLE + f"""        ei
        ld d, 0                 ; k, times 4: the first entry sent
        ld hl, copy             ; six on a line
        ld (base), hl
        ld e, {ONCE_FRAMES}
        call frames
        ld hl, copy2            ; three on a line
        ld (base), hl
        ld e, {ONCE_FRAMES}
        call frames
        di
""", data="atts:\n" + db_rows(table_bytes(SIX), 4) + "rows:\n" + db_rows(table_bytes(SIX2), 4),
        extra=IM2 + f"""copy    EQU ${COPY:04X}               ; six on a line, twice ($D0 sent once)
copy2   EQU ${COPY2:04X}               ; three on a line, twice
status  EQU VARS                ; what the routine read
base    EQU VARS + 1            ; the copy in use
""", sub=f"""
; frames: E frames, each the table from base + 4k, k going up by {SIX_TURN},
; round {n}, after a frame whose status had 5S
frames: halt                    ; the paper ended: the routine read the status
        ld a, (status)          ; 14
        and $40                 ;  8  5S?
        jr z, m0                ; 13, or 8
        ld a, d                 ;  5  a sprite left out: k + {SIX_TURN}, round {n}
        add a, {4 * SIX_TURN}                ;  8
        cp {4 * n}                   ;  8
        jr c, inside            ; 13, or 8
        sub {4 * n}                  ;  8
inside: ld d, a                 ;  5
m0:     VRAM_WRITE ${ATT:04X}        ; 40
        ld hl, (base)           ; 17  the copy from entry k
        ld b, 0                 ;  8
        ld c, d                 ;  5
        add hl, bc              ; 12
        ld c, VDP_DATA          ;  8
        ld b, {4 * n}                ;  8  six entries
        otir                    ; 23 a byte, 18 the last
m1:     dec e
        jr nz, frames
        ret

; irq: the status, read once at the end of the paper
irq:    push af
        in a, (VDP_CTRL)        ; 12  the status: F, 5S, C and the number
        ld (status), a          ; 14
        pop af
        ei
        ret
""")


def adaptive_tables(keep):
    """the table each frame shows, if every frame's status says 5S (keep) or
    none does (poll)"""
    out, k = [], 0
    for _ in range(SIX_FRAMES):
        if keep:
            k = (k + SIX_TURN) % len(SIX)
        out.append([SIX[(k + i) % len(SIX)] for i in range(len(SIX))])
    return out


PROGRAMS = {"five": five, "first": first, "stagger": stagger, "status": status, "rotate": rotate, "hero": hero, "layers": layers,
            "poll": lambda: adaptive("poll"), "keep": lambda: adaptive("keep"), "once": once}


def main():
    for name, make in PROGRAMS.items():
        with open(os.path.join(HERE, f"{name}.asm"), "w") as f:
            f.write(make())
    print(" ".join(f"{n}.asm" for n in PROGRAMS))


if __name__ == "__main__":
    main()
