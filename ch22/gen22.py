#!/usr/bin/env python3
"""gen22.py - the programs of chapter 22: Graphic II, the screen of the games.

    python3 gen22.py && ./build.sh

    lowbyte.asm    every byte of the 6,144 of the patterns set to the low byte
    highbyte.asm   of its own address, and to the high byte (figure 22.1)
    colours.asm    every pattern byte $F0, every colour byte a colour of its
                   own: the 6,144 colour bytes read back off the photograph
    diag.asm       vaddr, x and y to an address, and two lines drawn with it
                   (figure 22.2)
    vline.asm      down, the byte one line below, and a line down the screen
    tiles3.asm     a picture of tiles: eight shapes and their colours written
                   into each of the three thirds (figure 22.3)
    tiles1.asm     the same picture, the shapes and colours written once, and
                   R#3 and R#4 telling the three thirds to share them
    masks.asm      three thirds of three digits, and R#3 and R#4 changed every
                   eight frames; then M3 with M1 and with M2 (figure 22.4)
    leak.asm       WHERE IT BREAKS: a Graphic I page and M3 set; then the fix
                   (figure 22.5)

Every program writes with the display off, ends with asmparts.CART_END, and
build.sh assembles with --syntax=bFw.
"""
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
from asmparts import HEAD, CART_END, TEXT_PAGE, GRAPHIC2, library  # noqa: E402

BIOS = '        INCLUDE "bios.inc"\n'
BLACK, LIGHT_GREEN, DARK_BLUE, WHITE = 1, 3, 4, 15


def head(name, what):
    return HEAD.format(name=name, chapter=22, what=what) + BIOS


def db_rows(data, per=12):
    return "".join("        db " + ", ".join(f"${b:02X}" for b in data[i:i + per]) + "\n"
                   for i in range(0, len(data), per))


SHOW = """        VDP_REG 1, $C0          ; the display on
done:   jr done
"""

NOISE = """        VRAM_WRITE $0000        ; every byte of the VRAM: noise, the
        ld hl, $0000            ; BIOS's first 16 KB (chapter 21)
        ld c, VDP_DATA
        ld d, 64
noise:  ld b, 0
        otir
        dec d
        jr nz, noise
"""

FRAMES = """
; frames: wait for B frame flags, the interrupts off (chapter 19's status)
frames: in a, (VDP_CTRL)        ; bit 7, F: a frame has ended
        rla
        jr nc, frames
        djnz frames
        ret
"""


# ------------------------------------------------------------ lowbyte, highbyte
def byte_page(name, reg, what):
    return head(name, f"each pattern byte, the {what} of its address") + f"""; GRAPHIC2's screen: names 0 to 255 in each third, black on white. Then
; each of the 6,144 bytes of the patterns set to the {what} of its own address.
""" + GRAPHIC2 + f"""        VRAM_WRITE $0000
        ld hl, $0000            ; the address of the byte
        ld bc, 6144
fill:   ld a, {reg}                 ; its {what}
        out (VDP_DATA), a
        inc hl
        dec bc
        ld a, b
        or c
        jr nz, fill
""" + SHOW + CART_END


# ------------------------------------------------------------------ colours.asm
def colour_bytes():
    """6,144 colour bytes, ink and paper each 1 to 15, never 0 (transparent)"""
    rnd = random.Random(22)
    return [rnd.randrange(1, 16) << 4 | rnd.randrange(1, 16) for _ in range(6144)]


def colours():
    return head("colours", "6,144 colour bytes of their own") + """; Every pattern byte $F0: the left four pixels ink, the right four paper. Every
; colour byte a pair of colours of its own, from gen22.py, so that each strip
; of 8 x 1 on the screen shows which colour byte the VDP took for it.
""" + GRAPHIC2 + """        VRAM_WRITE $0000        ; patterns: $F0
        ld bc, 6144
pat:    ld a, $F0
        out (VDP_DATA), a
        dec bc
        ld a, b
        or c
        jr nz, pat
        VRAM_WRITE $2000        ; colours: 6,144 bytes from the table
        ld hl, table
        ld c, VDP_DATA
        ld d, 24                ; 24 x 256
col:    ld b, 0
        otir
        dec d
        jr nz, col
""" + SHOW + "table:\n" + db_rows(colour_bytes()) + CART_END


# ------------------------------------------------------------------ diag.asm
VADDR = """
; vaddr: B = x, C = y -> HL = the address of the byte that holds pixel (x, y),
; in the patterns of a Graphic II screen whose names run 0 to 255 in each
; third; add $2000 for its colours. Uses A.
vaddr:  ld a, c                 ;  5
        rrca                    ;  5
        rrca                    ;  5
        rrca                    ;  5
        and $1F                 ;  8: y / 8, the row of characters
        ld h, a                 ;  5
        ld a, b                 ;  5
        and $F8                 ;  8: the column of characters, x 8
        ld l, a                 ;  5
        ld a, c                 ;  5
        and 7                   ;  8: the line in the cell
        or l                    ;  5
        ld l, a                 ;  5
        ret                     ; 11
"""


def diag():
    return head("diag", "two lines drawn with vaddr") + """; Two lines, x = y and x = y + 64, for y = 0 to 191: for each pixel vaddr
; finds its byte, and the byte gets the pixel's bit. One pixel a byte, so no
; byte is read back (chapter 25 draws over what is there).
""" + GRAPHIC2 + """        ld c, 0                 ; y
line:   ld b, c                 ; x = y
        call pixel
        ld a, c
        add a, 64
        ld b, a                 ; x = y + 64
        call pixel
        inc c
        ld a, c
        cp 192
        jr nz, line
""" + SHOW + """
; pixel: B = x, C = y: the byte of pixel (x, y) set to that pixel alone
pixel:  call vaddr
v1:     ld a, l                 ; the write address
        out (VDP_CTRL), a
        ld a, h
        or $40
        out (VDP_CTRL), a
        ld a, b
        and 7
        ld e, a
        ld d, 0
        ld hl, bit
        add hl, de
        ld a, (hl)              ; $80 >> (x AND 7)
        out (VDP_DATA), a
        ret
bit:    db $80, $40, $20, $10, $08, $04, $02, $01
""" + VADDR + CART_END


# ------------------------------------------------------------------ vline.asm
DOWN = """
; down: HL = the address of a byte -> HL = the byte one line below it, in
; the patterns of a Graphic II screen whose names run 0 to 255 in each third.
; Uses A.
down:   inc l                   ;  5: one line down, inside the cell
        ld a, l                 ;  5
        and 7                   ;  8
        ret nz                  ; 12, 6 if not taken
        ld a, l                 ;  5: it was the cell's last line, and L
        sub 8                   ;  8  went on to the next column: back
        ld l, a                 ;  5  to this column, line 0
        inc h                   ;  5: of the next row of cells
        ret                     ; 11
"""
VLINE_X = 100


def vline():
    return head("vline", "a line down the screen with down") + f"""; A line down the screen at x = {VLINE_X}: vaddr finds the byte of its top pixel,
; and down the byte below, 191 times.
""" + GRAPHIC2 + f"""        ld b, {VLINE_X}               ; x
        ld c, 0                 ; y
        call vaddr              ; HL: the byte of ({VLINE_X}, 0)
        ld d, 192
vl:     ld a, l                 ; the write address
        out (VDP_CTRL), a
        ld a, h
        or $40
        out (VDP_CTRL), a
        ld a, ${0x80 >> VLINE_X % 8:02X}               ; pixel {VLINE_X}: bit {7 - VLINE_X % 8} of its byte
        out (VDP_DATA), a
d0:     call down
d1:     dec d
        jr nz, vl
""" + SHOW + DOWN + VADDR + CART_END


# ------------------------------------------------------------ tiles3, tiles1
# eight tiles: (pattern, colour of each line)
T = {"sky": ([0] * 8, [BLACK << 4 | WHITE] * 8),
     "cloud_l": ([0x03, 0x0F, 0x1F, 0x7F, 0xFF, 0xFF, 0x7F, 0x00],
                 [DARK_BLUE << 4 | WHITE] * 8),
     "cloud": ([0xC3, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0x00],
               [DARK_BLUE << 4 | WHITE] * 8),
     "cloud_r": ([0xC0, 0xF0, 0xF8, 0xFE, 0xFF, 0xFF, 0xFE, 0x00],
                 [DARK_BLUE << 4 | WHITE] * 8),
     "grass": ([0x00, 0x22, 0x77, 0xFF, 0x00, 0x44, 0x00, 0x11],
               [LIGHT_GREEN << 4 | WHITE] * 4 + [BLACK << 4 | LIGHT_GREEN] * 4),
     "brick": ([0xFF, 0x80, 0x80, 0x80, 0xFF, 0x08, 0x08, 0x08],
               [BLACK << 4 | DARK_BLUE] * 8),
     "water": ([0x00, 0x66, 0x99, 0x00, 0x00, 0x66, 0x99, 0x00],
               [DARK_BLUE << 4 | WHITE] * 4 + [WHITE << 4 | DARK_BLUE] * 4),
     "post": ([0x18] * 8, [BLACK << 4 | WHITE] * 8)}
TILES = list(T)
for _p, _c in T.values():
    assert len(_p) == len(_c) == 8


def tile_map():
    """the picture: 24 rows of 32 tile numbers"""
    rows = []
    for r in range(24):
        row = ["sky"] * 32
        if r == 3:
            for c0, w in ((3, 5), (16, 3), (24, 6)):
                row[c0:c0 + w] = ["cloud_l"] + ["cloud"] * (w - 2) + ["cloud_r"]
        if 7 <= r < 13:
            row[22] = "post"
        if r == 13:
            row = ["grass"] * 32
        elif 14 <= r < 19:
            row = ["brick"] * 32
        elif r >= 19:
            row = ["water"] * 32
        rows.append([TILES.index(t) for t in row])
    return [n for row in rows for n in row]


def tile_set():
    pats = [b for t in TILES for b in T[t][0]]
    cols = [b for t in TILES for b in T[t][1]]
    return pats, cols


def tiles(name, thirds):
    pats, cols = tile_set()
    once = thirds == 1
    r3, r4 = ("$9F", "$00") if once else ("$FF", "$03")
    writes = ""
    for t in range(thirds):
        writes += f"""        VRAM_WRITE ${0x0000 + 2048 * t:04X}        ; the shapes, in third {t}
        ld hl, shapes
        ld b, {len(pats)}
        otir
        VRAM_WRITE ${0x2000 + 2048 * t:04X}        ; their colours, in third {t}
        ld hl, colours
        ld b, {len(cols)}
        otir
"""
    what = ("the tiles written once; R#3 and R#4 share them" if once else
            "the tiles written into each third")
    say = ("""; map of 768 names. The tiles are written once, at $0000 and $2000: R#3 = $9F
; and R#4 = $00 make the three thirds take their shapes and colours from there.
""" if once else """; map of 768 names. The tiles are written into each of the three thirds.
""")
    return head(name, what) + f"""; A picture of {len(TILES)} tiles, 8 x 8 each with a colour for every line, and a
""" + say + f"""init:   di
        ld sp, SYS_AREA
        VDP_REG 1, $80          ; display off
        VDP_REG 0, $02          ; Graphic II
        VDP_REG 2, $06          ; names    $1800
        VDP_REG 3, {r3}          ; colours  $2000{', one set for three thirds' if once else ''}
        VDP_REG 4, {r4}          ; patterns $0000{', one set for three thirds' if once else ''}
        VDP_REG 5, $36          ; sprite attributes $1B00
        VDP_REG 6, $07          ; sprite patterns   $3800
        VDP_REG 7, $0F          ; backdrop white
""" + NOISE + """        VRAM_WRITE $1B00        ; no sprites
        ld a, $D0
        out (VDP_DATA), a
        VRAM_WRITE $1800        ; the map: 768 names
        ld hl, map
        ld c, VDP_DATA
        ld d, 3
nm:     ld b, 0
        otir
        dec d
        jr nz, nm
set0:
""" + writes + """set1:
""" + SHOW + "shapes:\n" + db_rows(pats) + "colours:\n" + db_rows(cols) + "map:\n" + \
        db_rows(tile_map()) + CART_END


# ------------------------------------------------------------------ masks.asm
MASK_STATES = [     # R#0, R#1, R#3, R#4
    (0x02, 0xC0, 0xFF, 0x03, "Graphic II, every mask bit set"),
    (0x02, 0xC0, 0xFF, 0x00, "R#4 = $00: one set of shapes"),
    (0x02, 0xC0, 0xFF, 0x01, "R#4 = $01"),
    (0x02, 0xC0, 0xFF, 0x02, "R#4 = $02"),
    (0x02, 0xC0, 0x9F, 0x03, "R#3 = $9F: one set of colours"),
    (0x02, 0xC0, 0xBF, 0x03, "R#3 = $BF"),
    (0x02, 0xC0, 0xDF, 0x03, "R#3 = $DF"),
    (0x02, 0xD0, 0xFF, 0x03, "M1 and M3"),
    (0x02, 0xC8, 0xFF, 0x03, "M2 and M3"),
]
MASK_FRAMES = 8
MASK_INKS = [BLACK, DARK_BLUE, LIGHT_GREEN]     # third t: the digit t, in this ink


def masks():
    thirds = ""
    for t in range(3):
        thirds += f"""        ld de, ${0x0000 + 2048 * t:04X}
        ld a, '{t}'
        call digit              ; all 256 shapes of third {t}: the digit {t}
        VRAM_WRITE ${0x2000 + 2048 * t:04X}        ; and all its colours: ink {MASK_INKS[t]} on white
        ld bc, 2048
c{t}:     ld a, ${MASK_INKS[t] << 4 | WHITE:02X}
        out (VDP_DATA), a
        dec bc
        ld a, b
        or c
        jr nz, c{t}
"""
    states = ""
    for k, (r0, r1, r3, r4, what) in enumerate(MASK_STATES):
        states += f"""        ld b, {MASK_FRAMES}
        call frames
s{k}:     VDP_REG 0, ${r0:02X}          ; {what}
        VDP_REG 3, ${r3:02X}
        VDP_REG 4, ${r4:02X}
        VDP_REG 1, ${r1:02X}
t{k}:
"""
    return head("masks", "R#3 and R#4 as masks") + f"""; Three thirds, each of its own 256 shapes and 2,048 colours: every shape of
; third t is the digit t, and its ink colour {MASK_INKS}[t]. Then every
; {MASK_FRAMES} frames new values of R#3 and R#4, and at the end M1 and M2 with M3.
""" + GRAPHIC2 + thirds + """        VDP_REG 7, $1F          ; ink black for M1, backdrop white
""" + states + """done:   jr done

; digit: A = a character, DE = a third's shapes: its shape, 256 times over
digit:  ld l, a
        ld h, 0
        add hl, hl
        add hl, hl
        add hl, hl
        push de
        ld de, (CGTABL)
        add hl, de              ; HL: the BIOS's shape of A
        pop de
        ld a, e
        out (VDP_CTRL), a
        ld a, d
        or $40
        out (VDP_CTRL), a
        ld e, 0                 ; 256 times
.next:  push hl
        ld b, 8
        ld c, VDP_DATA
        otir
        pop hl
        dec e
        jr nz, .next
        ret
""" + FRAMES + CART_END


# ------------------------------------------------------------------ leak.asm
LEAK_WORDS = ["A GRAPHIC I PAGE, AND THEN M3", "THE SAME NAMES, THE SAME SHAPES",
              "R#3 = $80 AND R#4 = $00 STILL"]
LEAK_FRAMES = 8


def leak():
    page = "".join(f"        ld b, {2 * r}\n        ld c, 0\n        ld hl, w{r}\n        call puts\n"
                   for r in range(len(LEAK_WORDS)))
    texts = "".join(f'w{r}:     db "{t}", 0\n' for r, t in enumerate(LEAK_WORDS))
    assert all(len(t) <= 32 for t in LEAK_WORDS)
    return head("leak", "a Graphic I page, and M3") + f"""; WHERE IT BREAKS. A Graphic I page drawn by TEXT_PAGE (R#3 = $80, R#4 = $00).
; After {LEAK_FRAMES} frames, M3: Graphic II, nothing else changed. After {LEAK_FRAMES} more,
; the fix: 2,048 colours written at $2000, R#3 = $9F and R#4 = $00, so that the
; three thirds share the page's shapes, and each line of a name has a colour.
""" + TEXT_PAGE + page + """        VDP_REG 1, $C0          ; the Graphic I page on
        ld b, """ + str(LEAK_FRAMES) + """
        call frames
m3:     VDP_REG 0, $02          ; M3: Graphic II, and nothing else
        ld b, """ + str(LEAK_FRAMES) + """
        call frames
fix:    VDP_REG 1, $80          ; display off
        VRAM_WRITE $2000        ; 256 names x 8 lines of colours: lines 0 to 3
        ld d, 0                 ; black on white, lines 4 to 7 light blue
fx:     ld b, 4
        ld a, $1F
fx1:    out (VDP_DATA), a
        djnz fx1
        ld b, 4
        ld a, $5F
fx2:    out (VDP_DATA), a
        djnz fx2
        dec d
        jr nz, fx
        VDP_REG 3, $9F          ; colours $2000: one set for three thirds
        VDP_REG 4, $00          ; patterns $0000: one set for three thirds
on:     VDP_REG 1, $C0          ; display on
done:   jr done
""" + FRAMES + texts + library() + CART_END


PROGRAMS = {"lowbyte": lambda: byte_page("lowbyte", "l", "low byte"),
            "highbyte": lambda: byte_page("highbyte", "h", "high byte"),
            "colours": colours, "diag": diag, "vline": vline,
            "tiles3": lambda: tiles("tiles3", 3), "tiles1": lambda: tiles("tiles1", 1),
            "masks": masks, "leak": leak}


def main():
    for name, make in PROGRAMS.items():
        with open(os.path.join(HERE, f"{name}.asm"), "w") as f:
            f.write(make())
    print(" ".join(f"{n}.asm" for n in PROGRAMS))


if __name__ == "__main__":
    main()
