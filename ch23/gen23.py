#!/usr/bin/env python3
"""gen23.py - the programs of chapter 23: colour clash on the MSX.

    python3 gen23.py && ./build.sh

    places.asm     the ball in its eight places in a byte, each with its strips
                   painted: two or three strips a line (figure 23.1)
    clash.asm      the ball moved over the grass, its strips painted white
    sprite.asm     the same picture, the ball a hardware sprite (figure 23.2)
    oneink.asm     way 1: the ball the grass's ink, the colour in the paper
    plain.asm      way 2: nothing in the shapes but the ball; it paints the ink
                   of its strips and keeps their paper
    steps.asm      way 3: a byte across at a time, and any line down
    mono.asm       way 4: two colours for the whole picture
    backdrop.asm   way 5: every paper colour 0, and R#7 the colour of the third
                   the ball is in (figure 23.3, with ways 1 to 3)
    blocks.asm     way 3 at its limit: a block of colour alone, moved a byte
                   across and two lines down (figure 23.4)
    hill.asm       a slope between two colours, in whole strips on the left
                   and in the strips' two colours on the right (figure 23.5)
    zero.asm       WHERE IT BREAKS: plain.asm painting with paper 0 (figure 23.6)

The moving programs share one path: MOVES moves of the ball, two lines down
and a pixel right each, one a frame, all made in the lines the VDP does not
draw. Every program draws with the display off first, ends with
asmparts.CART_END, and build.sh assembles with --syntax=bFw.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
from asmparts import HEAD, CART_END, GRAPHIC2  # noqa: E402

BIOS = '        INCLUDE "bios.inc"\n'
BLACK, LIGHT_GREEN, DARK_BLUE, WHITE = 1, 3, 4, 15
GRASS = [0x10, 0x54, 0x00, 0x00, 0x01, 0x45, 0x00, 0x00]    # a cell of grass
MOVES = 64
START = (24, 8)             # the ball's top left pixel before the first move
STEP = (1, 2)               # each move: a pixel right, two lines down


def head(name, what):
    return HEAD.format(name=name, chapter=23, what=what) + BIOS


def db_rows(data, per=16):
    return "".join("        db " + ", ".join(f"${b:02X}" for b in data[i:i + per]) + "\n"
                   for i in range(0, len(data), per))


# ------------------------------------------------------------------ the ball
def ball_rows():
    """the ball, 16 x 16: a disc, as 16 rows of 16 bits, bit 15 on the left"""
    rows = []
    for y in range(16):
        r = 0
        for x in range(16):
            if (x - 7.5) ** 2 + (y - 7.5) ** 2 <= 60:
                r |= 0x8000 >> x
        rows.append(r)
    return rows


def ball_pixels():
    return {(x, y) for y, r in enumerate(ball_rows()) for x in range(16) if r & 0x8000 >> x}


def shifted(s):
    """the ball shifted S pixels right in three bytes: three columns of 16"""
    rows = [r << (8 - s) for r in ball_rows()]
    return [(r >> 16 - 8 * k) & 0xFF for k in range(3) for r in rows]


def sprite_pattern():
    """the ball as a sprite of 16 x 16: its left half's 16 bytes, then its
    right half's (chapter 26)"""
    rows = ball_rows()
    return [r >> 8 for r in rows] + [r & 0xFF for r in rows]


# ------------------------------------------------------------------ the scenes
def third(colours):
    """a table of a colour for every line: one for each third"""
    return [colours[y // 64] for y in range(192)]


# the scenes: grass in the shapes or not; the colour byte of each third; the
# paint of the ball's strips, by third (None: no paint); the ball's colour
SCENE_TABLE = {
    "clash":    (True,  (0x13, 0x13, 0x13), (0xF3, 0xF3, 0xF3), WHITE),
    "sprite":   (True,  (0x13, 0x13, 0x13), None,               WHITE),
    "oneink":   (True,  (0x1F, 0x13, 0x14), None,               BLACK),
    "plain":    (False, (0x33, 0x44, 0x11), (0xF3, 0xF4, 0xF1), WHITE),
    "steps":    (True,  (0x13, 0x13, 0x13), (0xF3, 0xF3, 0xF3), WHITE),
    "mono":     (True,  (0x13, 0x13, 0x13), None,               BLACK),
    "backdrop": (True,  (0x10, 0x10, 0x10), None,               BLACK),
    "zero":     (False, (0x33, 0x44, 0x11), (0xF0, 0xF0, 0xF0), WHITE),
    "blocks":   (True,  (0x13, 0x13, 0x13), (0x14, 0x14, 0x14), None),
}
BACKS = {"backdrop": (0x0F, 0x03, 0x04)}       # R#7 for each third
SCENES = {n: dict(grass=g, colours=c, paint=p, ball=b, backs=BACKS.get(n))
          for n, (g, c, p, b) in SCENE_TABLE.items()}
WIPES_COLOURS = {"clash", "steps"}          # the programs that paint the scene's colours back


def path(name):
    """the ball's top left pixel after each move"""
    x, y = START
    out = []
    for k in range(MOVES):
        if name in ("steps", "blocks"):
            if (MOVES - k) % 8 == 0:
                x += 8
        else:
            x += STEP[0]
        y += STEP[1]
        out.append((x, y))
    return out


# ------------------------------------------------------------------ routines
FRAME = """
; frame: wait for the end of the paper: F, bit 7 of the status, read with the
; interrupts off (chapter 19)
frame:  in a, (VDP_CTRL)
        rla
        jr nc, frame
        ret
"""

VADDR = """
; vaddr: B = x, C = y -> HL = the address of the byte that holds pixel (x, y),
; in the patterns of a Graphic II screen whose names run 0 to 255 in each
; third; add $2000 for its colours. Uses A. (Chapter 22.)
vaddr:  ld a, c
        rrca
        rrca
        rrca
        and $1F                 ; y / 8, the row of characters
        ld h, a
        ld a, b
        and $F8                 ; the column of characters, x 8
        ld l, a
        ld a, c
        and 7                   ; the line in the cell
        or l
        ld l, a
        ret
"""

SEND = """
; send: 16 bytes from HL down the screen, from the VRAM address in DE (the
; write bit and the table in D); C: the line of the first. Inside a cell the
; next line is the next byte (chapter 22): the bytes go in runs, one for each
; cell, and between runs the address moves to line 0 of the cell below.
send:   push bc
        ld a, c
        or $F8
        neg                     ; the first run: 8 - (y AND 7), 1 to 8
        ld b, a
        ld a, 16
        sub b                   ; the bytes after it
        ld c, VDP_DATA
.run:   push af
        ld a, e
        out (VDP_CTRL), a
        ld a, d
        out (VDP_CTRL), a       ; the run's address
        otir                    ; its bytes, off the paper (chapter 20)
        inc d                   ; the cell below: 256 bytes on,
        ld a, e
        and $F8
        ld e, a                 ; at its line 0
        pop af
        or a
        jr z, .done             ; no bytes left
        ld b, 8
        cp b
        jr nc, .full
        ld b, a                 ; the last run: what is left
.full:  sub b
        jr .run
.done:  pop bc
        ret
"""


def wipe(colours):
    return """
; wipe: the scene back in the ball's three columns at (B, C): its shapes""" + (
        ",\n; and its colours" if colours else "") + """
wipe:   call vaddr
        set 6, h                ; the write bit
        ld (vptr), hl           ; the first column's first byte
        ld a, 3
.col:   push af
        ld de, (vptr)
        ld hl, scpat
        ld l, c                 ; the scene's shapes from line C
        call send
""" + ("""        ld de, (vptr)
        set 5, d                ; $2000 on: the colours
        ld hl, sccol
        ld l, c
        call send
""" if colours else "") + """        ld hl, vptr
        ld a, (hl)
        add a, 8
        ld (hl), a              ; the next column: 8 bytes on
        pop af
        dec a
        jr nz, .col
        ret
"""


def put(paint):
    return """
; put: the ball at (B, C): in each of its three columns its shapes ORed into
; the scene's""" + (", and in its strips its colours" if paint else "") + """
put:    ld a, b
        and 7                   ; how far the ball is shifted in its bytes
        ld (shift), a
        add a, a
        ld e, a
        ld d, 0
        ld hl, shifts
        add hl, de
        ld e, (hl)
        inc hl
        ld d, (hl)
        ld (bptr), de           ; its first column: 16 bytes
        call vaddr
        set 6, h
        ld (vptr), hl
        ld a, 3
.col:   push af
        push bc
        ld hl, scpat
        ld l, c                 ; the scene's shapes from line C,
        ld de, (bptr)           ; the ball's column,
        ld bc, buf
        DUP 16
        ld a, (de)
        or (hl)
        ld (bc), a              ; and their OR, into buf
        inc e
        inc l
        inc c
        EDUP
        ld (bptr), de           ; the ball's next column
        pop bc
        ld de, (vptr)
        ld hl, buf
        call send
""" + ("""        pop af
        push af
        dec a                   ; the third column, with the ball not
        jr nz, .paint           ; shifted, has none of it: no paint
        ld a, (shift)
        or a
        jr z, .next
.paint: ld de, (vptr)
        set 5, d
        ld hl, paint
        ld l, c                 ; the paint of the ball's strips
        call send
""" if paint else "") + """.next:  ld hl, vptr
        ld a, (hl)
        add a, 8
        ld (hl), a
        pop af
        dec a
        jp nz, .col             ; JP: the loop is too long for JR
        ret
"""


TINT = """
; tint: the block's two columns at (B, C), from line C down, in the colours of
; the table at HL: the scene's, or the block's own
tint:   push hl
        call vaddr
        ld a, h
        or $60                  ; the colours, and the write bit
        ld d, a
        ld e, l
        pop hl
        ld l, c                 ; the table from line C
        push hl
        push de
        call send               ; the first column
        pop de
        pop hl
        ld a, e
        add a, 8
        ld e, a                 ; the second, 8 bytes on
        jp send
"""

STEP8 = """        ld a, (count)
        and 7
        jr nz, .same            ; x: on seven moves in eight it stays,
        ld a, (hl)
        add a, 8
        ld (hl), a              ; on the eighth a byte right
.same:  ld bc, (pos)
"""


def move(name):
    s = SCENES[name]
    if name == "blocks":
        return """
; move: the block from where it is to its next place: colours alone
move:   ld bc, (pos)            ; C = y, B = x: where it is
        ld hl, sccol
        call tint               ; the scene's colours back
        ld hl, pos
        inc (hl)
        inc (hl)                ; y: two lines down
        inc hl
""" + STEP8 + """        ld hl, paint
        jp tint                 ; the block's colours
"""
    if name == "sprite":
        return """
; move: the sprite two lines down and a pixel right: its Y and X
move:   ld hl, pos
        inc (hl)
        inc (hl)                ; y: two lines down
        inc hl
        inc (hl)                ; x: a pixel right
        VRAM_WRITE $1B00        ; sprite 0's Y and X
        ld a, (pos)
        dec a                   ; it shows a line below its Y (chapter 26)
        out (VDP_DATA), a
        ld a, (pos + 1)
        out (VDP_DATA), a
        ret
"""
    step = """        ld hl, pos
        inc (hl)
        inc (hl)                ; y: two lines down
        inc hl
""" + (STEP8 if name == "steps" else """        inc (hl)                ; x: a pixel right
        ld bc, (pos)
""")
    back = """        call put
        ld a, (pos)             ; y
        rlca
        rlca
        and 3                   ; the third the ball's top is in
        ld e, a
        ld d, 0
        ld hl, backs
        add hl, de
        ld a, (hl)
        out (VDP_CTRL), a
        ld a, $87
        out (VDP_CTRL), a       ; R#7: the border, and every colour 0
        ret
""" if s["backs"] else "        jp put\n"
    return """
; move: the ball from where it is to its next place
move:   ld bc, (pos)            ; C = y, B = x: where it is
        call wipe
""" + step + back


def tables(name):
    s = SCENES[name]
    pat = [GRASS[y % 8] if s["grass"] else 0 for y in range(192 + 16)]
    col = third(s["colours"]) + [s["colours"][2]] * 16
    out = """
; the scene: for every line of the screen a byte of shape and a byte of colour,
; the same in every column; each table a page of its own, so that L = y
        ALIGN 256
scpat:
""" + db_rows(pat) + """        ALIGN 256
sccol:
""" + db_rows(col)
    if s["paint"]:
        out += """        ALIGN 256
paint:                          ; the colours of the ball's strips, by line
""" + db_rows(third(s["paint"]) + [s["paint"][2]] * 16)
    if s["backs"]:
        out += "backs:  db " + ", ".join(f"${b:02X}" for b in s["backs"]) + \
            "                ; R#7 for each third\n"
    if name not in ("sprite", "blocks"):
        out += "        ALIGN 256               ; no column of the ball crosses a page\n"
        out += "shifts: dw " + ", ".join(f"ball{k}" for k in range(8)) + "\n"
        for k in range(8):
            out += f"ball{k}:                          ; shifted {k}: three columns of 16\n" + \
                db_rows(shifted(k))
    return out


RAM = """pos     EQU VARS                ; the ball: y, then x
count   EQU VARS + 2            ; the moves left
shift   EQU VARS + 3            ; put's: x AND 7
bptr    EQU VARS + 4            ; put's: the next column of the ball
vptr    EQU VARS + 6            ; wipe's and put's: the column's VRAM address
buf     EQU VARS + $10          ; put's: a column of 16 shapes
"""

def fill():
    return """
; fill: the 192 bytes of a scene table, one a line, into all 32 columns of the
; table at the VRAM address in DE (write bit included); the display is off
fill:   ld a, e
        out (VDP_CTRL), a
        ld a, d
        out (VDP_CTRL), a
        ld c, VDP_DATA
        ld d, 24                ; 24 rows of cells
.row:   ld e, 32                ; of 32 cells
.cell:  push hl
        ld b, 8
        otir                    ; a cell's eight lines
        pop hl
        dec e
        jr nz, .cell
        ld a, l
        add a, 8
        ld l, a                 ; the next row's lines (L = y)
        dec d
        jr nz, .row
        ret
"""


def moving(name, what, say):
    s = SCENES[name]
    x0, y0 = START
    sprite = name == "sprite"
    setup = """        ld hl, scpat
        ld de, $4000
        call fill               ; the scene's shapes
        ld hl, sccol
        ld de, $6000
        call fill               ; and its colours
"""
    if sprite:
        setup += """        VRAM_WRITE $3800        ; sprite pattern 0: the ball
        ld hl, ballspr
        ld b, 32
        ld c, VDP_DATA
        otir
        VRAM_WRITE $1B00        ; sprite 0: Y, X, pattern 0, white; then the end
        ld hl, attrs
        ld b, 5
        otir
        VDP_REG 1, $C2          ; the display on, sprites of 16 x 16
"""
    elif name == "blocks":
        setup += """        ld bc, ${:02X}{:02X}           ; x, y
        ld (pos), bc
        ld hl, paint
        call tint               ; the block in its first place
        VDP_REG 1, $C0          ; the display on
""".format(x0, y0)
    else:
        setup += """        ld bc, ${:02X}{:02X}           ; x, y
        ld (pos), bc
        call put                ; the ball in its first place
        VDP_REG 1, $C0          ; the display on
""".format(x0, y0)
    if sprite:
        setup = setup.replace("        VDP_REG 1, $C2", f"""        ld bc, ${x0:02X}{y0:02X}           ; x, y
        ld (pos), bc
        VDP_REG 1, $C2""")
    data = tables(name)
    if sprite:
        data += "ballspr:                        ; the ball as a sprite (chapter 26)\n" + \
            db_rows(sprite_pattern()) + \
            f"attrs:  db ${y0 - 1:02X}, ${x0:02X}, 0, ${s['ball']:02X}, $D0\n"
    return head(name, what) + RAM + say + GRAPHIC2 + setup + f"""        in a, (VDP_CTRL)        ; a flag left from before, cleared
        ld a, {MOVES}
        ld (count), a
loop:   call frame              ; the end of the paper
m0:     call move
m1:     ld hl, count
        dec (hl)
        jr nz, loop
done:   jr done
""" + FRAME + move(name) + routines(name) + fill() + data + CART_END


def routines(name):
    if name == "sprite":
        return ""
    if name == "blocks":
        return TINT + SEND + VADDR
    return wipe(name in WIPES_COLOURS) + put(SCENES[name]["paint"] is not None) + SEND + VADDR


SAY = {
    "clash": """; The ball, white, moved over the grass, black on light green: each move puts
; the scene back where the ball was, shapes and colours, and puts the ball in
; its next place, its strips painted white ink on light green paper.
""",
    "sprite": """; clash.asm's picture with the ball a hardware sprite: a move writes its Y and
; X, and nothing of the picture under it.
""",
    "oneink": """; WAY 1: the ball is black, as the grass is, and the colour is in the paper:
; white, light green and dark blue thirds. No colour is ever written.
""",
    "plain": """; WAY 2: nothing in the shapes but the ball. It paints its strips white ink
; and keeps their paper: light green, dark blue or black, by third. A strip
; it leaves keeps its white ink, which has nothing to colour.
""",
    "steps": """; WAY 3: clash.asm with the ball a byte across at a time, every eighth move,
; and two lines down every move: always in two strips a line, its own.
""",
    "mono": """; WAY 4: the grass and the ball black on light green, and nothing else.
""",
    "backdrop": """; WAY 5: every colour byte black ink on paper 0, which shows the backdrop, and
; each move sets R#7 to the colour of the third the ball's top is in.
""",
    "blocks": """; WAY 3 AT ITS LIMIT: a block of 2 x 16 strips, black ink on dark blue, moved
; over clash.asm's grass by its colours alone, as steps.asm moves its ball.
""",
    "zero": """; WHERE IT BREAKS: plain.asm, with the ball's strips painted white ink on
; paper 0 instead of on their own paper.
""",
}
WHAT = {"clash": "the ball's colour in its strips", "sprite": "the ball as a sprite",
        "oneink": "way 1, one ink", "plain": "way 2, the background empty of ink",
        "steps": "way 3, a byte across at a time", "mono": "way 4, monochrome",
        "backdrop": "way 5, the backdrop", "zero": "paper 0",
        "blocks": "a block of colour alone"}


# ------------------------------------------------------------------ places
PLACES = [(33 * k, 40 + 3 * k) for k in range(8)]     # x AND 7 = k; y as it comes


def places():
    calls = "".join(f"        ld bc, ${x:02X}{y:02X}\n        call put\n" for x, y in PLACES)
    pat = [0] * (192 + 16)
    return head("places", "the ball in its eight places in a byte") + RAM + \
        """; The ball black, in eight places along the screen: ball k is k pixels right of
; a byte's left edge, and some lines lower than the one before. put paints
; each ball's strips black ink on dark blue paper.
""" + GRAPHIC2 + calls + """        VDP_REG 1, $C0          ; the display on
done:   jr done
""" + put(True) + SEND + VADDR + """
        ALIGN 256
scpat:
""" + db_rows(pat) + """        ALIGN 256
paint:                          ; the ball's strips: black on dark blue
""" + db_rows([0x14] * (192 + 16)) + "        ALIGN 256\nshifts: dw " + ", ".join(f"ball{k}" for k in range(8)) + "\n" + \
        "".join(f"ball{k}:\n" + db_rows(shifted(k)) for k in range(8)) + CART_END


# ------------------------------------------------------------------ hill
HILL_SPLIT = 128            # left of it whole strips; right of it both colours


def edge(x):
    """the hill's top line at pixel x: a line up for every two pixels across"""
    return 40 + (255 - x) // 2


def hill_tables():
    """the 6,144 shape bytes and the 6,144 colour bytes, in the VRAM's order:
    on the left a strip is all hill or all sky, by its pixel 4; on the right
    its bits are the hill's pixels, light green ink, and white paper the sky"""
    shapes, colours = [0] * 6144, [0] * 6144
    for y in range(192):
        for c in range(32):
            a = (y // 8) * 256 + c * 8 + y % 8
            if 8 * c < HILL_SPLIT:
                colours[a] = BLACK << 4 | (LIGHT_GREEN if y >= edge(8 * c + 4) else WHITE)
            else:
                shapes[a] = sum(0x80 >> i for i in range(8) if y >= edge(8 * c + i))
                colours[a] = LIGHT_GREEN << 4 | WHITE
    return shapes, colours


def hill():
    shapes, colours = hill_tables()
    return head("hill", "a slope between two colours") + """; A green hill under a white sky, its edge a line up for every two pixels across.
; Left of x = """ + str(HILL_SPLIT) + """ each strip is one colour, the paper; right of it each strip on
; the edge has the hill in its ink and the sky in its paper.
""" + GRAPHIC2 + """        VRAM_WRITE $0000        ; the shapes
        ld hl, shapes
        call copy
        VRAM_WRITE $2000        ; the colours
        ld hl, colours
        call copy
        VDP_REG 1, $C0          ; the display on
done:   jr done

; copy: 6,144 bytes from HL to the VDP, the display off
copy:   ld c, VDP_DATA
        ld d, 24                ; 24 x 256
.page:  ld b, 0
        otir
        dec d
        jr nz, .page
        ret
shapes:
""" + db_rows(shapes) + "colours:\n" + db_rows(colours) + CART_END


PROGRAMS = {"places": places, "hill": hill}
for _n in ("clash", "sprite", "oneink", "plain", "steps", "mono", "backdrop", "blocks", "zero"):
    PROGRAMS[_n] = (lambda n: lambda: moving(n, WHAT[n], SAY[n]))(_n)


def main():
    for name, make in PROGRAMS.items():
        with open(os.path.join(HERE, f"{name}.asm"), "w") as f:
            f.write(make())
    print(" ".join(f"{n}.asm" for n in PROGRAMS))


if __name__ == "__main__":
    main()
