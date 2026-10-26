#!/usr/bin/env python3
"""gen24.py - the programs of chapter 24: tiles and the name table.

    python3 gen24.py && ./build.sh

    meta.asm       a screen of tiles from a map of 2 x 2 metatiles: the map
                   expanded into a copy of the 768 names in the RAM, and the
                   copy sent to the VDP (figure 24.1)
    full.asm       a player who walks and coins that blink: the RAM copy
                   changed during the paper, and all 768 names sent with OTIR
                   as soon as the paper ends (WHERE IT BREAKS at 60 Hz,
                   figure 24.2)
    paper.asm      the same, the 768 names sent at 29 T-states a byte
    dirty.asm      the same, only the rows of names that changed sent
    late.asm       two screens sent in turn at 29 T-states a byte, each send
                   begun while the beam is in row 4 of the paper (figure 24.3)
    spin.asm       the coins spun by rewriting their four tiles' shapes, and no
                   name (figure 24.4)
    peek.asm       every name read back three ways: RDVRM, an address and an IN,
                   and the copy in the RAM

Graphic II with one set of shapes and colours for the three thirds (R#3 =
$9F, R#4 = $00, chapter 22). Every program draws with the display off first,
keeps the interrupts off and waits for the end of the paper on the status
(chapter 19), ends with asmparts.CART_END, and build.sh assembles with
--syntax=bFw.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
from asmparts import HEAD, CART_END  # noqa: E402

BIOS = '        INCLUDE "bios.inc"\n'
BLACK, LIGHT_GREEN, DARK_BLUE, WHITE = 1, 3, 4, 15
FRAMES = 64                 # frames of walking and blinking
NAMES_RAM = 0xC400          # the copy of the 768 names
DIRTY_RAM = 0xC700          # a byte for each of the 24 rows of names: not 0, changed


def head(name, what):
    return HEAD.format(name=name, chapter=24, what=what) + BIOS


def db_rows(data, per=16):
    return "".join("        db " + ", ".join(f"${b:02X}" for b in data[i:i + per]) + "\n"
                   for i in range(0, len(data), per))


# ------------------------------------------------------------------ the tiles
def quarters(rows):
    """16 rows of 16 bits cut into four tiles: top left, top right, bottom
    left, bottom right"""
    return [[r >> 8 for r in rows[:8]], [r & 0xFF for r in rows[:8]],
            [r >> 8 for r in rows[8:]], [r & 0xFF for r in rows[8:]]]


COIN = [sum(0x8000 >> x for x in range(16) if (x - 7.5) ** 2 + (y - 7.5) ** 2 <= 36)
        for y in range(16)]
PLAYER = [int(r, 2) for r in (
    "0000011111100000", "0000111111110000", "0000110110110000", "0000111111110000",
    "0000011111100000", "0000001111000000", "0001111111111000", "0011111111111100",
    "0110011111100110", "0110011111100110", "0000011111100000", "0000011001100000",
    "0000011001100000", "0000011001100000", "0000111001110000", "0001111001111000")]

SKY_C, BRICK_C = BLACK << 4 | WHITE, BLACK << 4 | DARK_BLUE
TILES = [   # name, 8 shape bytes, 8 colour bytes: tile n is name n
    ("sky", [0] * 8, [SKY_C] * 8),
    ("brick", [0xFF, 0x80, 0x80, 0x80, 0xFF, 0x08, 0x08, 0x08], [BRICK_C] * 8),
    ("grass", [0x00, 0x22, 0x77, 0xFF, 0x00, 0x44, 0x00, 0x11],
     [LIGHT_GREEN << 4 | WHITE] * 4 + [BLACK << 4 | LIGHT_GREEN] * 4),
    ("earth", [0x00, 0x44, 0x00, 0x11, 0x00, 0x44, 0x00, 0x11], [BLACK << 4 | LIGHT_GREEN] * 8),
    ("ladder_l", [0x20, 0x3F, 0x20, 0x20, 0x20, 0x3F, 0x20, 0x20], [SKY_C] * 8),
    ("ladder_r", [0x04, 0xFC, 0x04, 0x04, 0x04, 0xFC, 0x04, 0x04], [SKY_C] * 8),
] + [(f"coin_{k}", q, [DARK_BLUE << 4 | WHITE] * 8) for k, q in enumerate(quarters(COIN))] \
  + [(f"player_{k}", q, [SKY_C] * 8) for k, q in enumerate(quarters(PLAYER))]
TILE = {name: n for n, (name, _, _) in enumerate(TILES)}

# the metatiles: four names each, top left, top right, bottom left, bottom right
METAS = [("sky", ["sky"] * 4), ("wall", ["brick"] * 4),
         ("ground", ["grass", "grass", "earth", "earth"]),
         ("ladder", ["ladder_l", "ladder_r"] * 2),
         ("coin", [f"coin_{k}" for k in range(4)]),
         ("player", [f"player_{k}" for k in range(4)])]
META = {name: n for n, (name, _) in enumerate(METAS)}

# the map: 12 rows of 16 metatiles, a character each
MAP_ROWS = ["WWWWWWWWWWWWWWWW",
            "W..............W",
            "W..o........o..W",
            "W.GGGGH...GGGG.W",
            "W.....H........W",
            "W.....H..o.....W",
            "W.....H.GGGGG..W",
            "W..o..H........W",
            "W.....H......o.W",
            "W.....H........W",
            "WGGGGGGGGGGGGGGW",
            "WWWWWWWWWWWWWWWW"]
CHARS = {"W": "wall", ".": "sky", "G": "ground", "H": "ladder", "o": "coin"}
MAP = [META[CHARS[c]] for row in MAP_ROWS for c in row]
MAP2_ROWS = ["WWWWWWWWWWWWWWWW",        # late.asm's second screen
             "W..............W",
             "W.......o......W",
             "W.....GGGGG....W",
             "W..H...........W",
             "W..H........o..W",
             "W..H..GGG....GGW",
             "W..H...........W",
             "W..H...o.......W",
             "WGGGGG....GGGGGW",
             "W..............W",
             "WWWWWWWWWWWWWWWW"]
MAP2 = [META[CHARS[c]] for row in MAP2_ROWS for c in row]
TEARS = 16                  # late.asm's sends
TEAR_ROW = 4                # ... each begun as the beam reaches this row of names
WAIT = {"MSXBOOK_EU16": 27588, "MSXBOOK_JP16": 15960}   # the lines not drawn, in T-states
SPINS = 8                   # spin.asm's changes of the coins' shapes
SPIN_FRAMES = 4             # ... one every this many frames


def coin_phases():
    """the coin turning: four drawings of 16 x 16, a disc and ellipses"""
    out = []
    for rx in (6, 4, 1.5, 4):
        rows = [sum(0x8000 >> x for x in range(16)
                    if ((x - 7.5) / rx) ** 2 + ((y - 7.5) / 6) ** 2 <= 1) for y in range(16)]
        out.append([b for q in quarters(rows) for b in q])
    return out
COINS = [(r, c) for r, row in enumerate(MAP_ROWS) for c, ch in enumerate(row) if ch == "o"]
PROW = 9                    # the player walks along this row of the map
PSTART = 1                  # from this column


def names_of(meta_map):
    """the 768 names of a map of metatiles"""
    names = [0] * 768
    for r in range(12):
        for c in range(16):
            tl, tr, bl, br = METAS[meta_map[16 * r + c]][1]
            a = 64 * r + 2 * c
            names[a], names[a + 1], names[a + 32], names[a + 33] = (TILE[t] for t in (tl, tr, bl, br))
    return names


def frames():
    """the metatile map as sent after each frame's send: frame 0 is the one
    the set-up sends"""
    m, px, tick, shown = list(MAP), PSTART, 0, META["coin"]
    m[16 * PROW + px] = META["player"]
    out = [list(m)]
    for _ in range(FRAMES):
        out.append(list(m))                 # sent at the start of the frame
        m[16 * PROW + px] = MAP[16 * PROW + px]
        px = px + 1 if px < 14 else 1
        m[16 * PROW + px] = META["player"]
        tick = (tick + 1) & 0xFF
        if tick % 16 == 0:
            shown ^= META["coin"] ^ META["sky"]
            for r, c in COINS:
                m[16 * r + c] = shown
    return out


# ------------------------------------------------------------------ routines
SETUP = """init:   di
        ld sp, SYS_AREA
        VDP_REG 1, $80          ; display off
        VDP_REG 0, $02          ; Graphic II
        VDP_REG 2, $06          ; names    $1800
        VDP_REG 3, $9F          ; colours  $2000, one set for three thirds
        VDP_REG 4, $00          ; shapes   $0000, one set for three thirds
        VDP_REG 5, $36          ; sprite attributes $1B00
        VDP_REG 6, $07          ; sprite patterns   $3800
        VDP_REG 7, $0F          ; border white
        VRAM_WRITE $1B00        ; no sprites
        ld a, $D0
        out (VDP_DATA), a
        VRAM_WRITE $0000        ; the tiles' shapes
        ld hl, shapes
        ld c, VDP_DATA
        ld b, {nbytes}
        otir
        VRAM_WRITE $2000        ; and their colours
        ld hl, colours
        ld b, {nbytes}
        otir
        ld hl, dirty            ; the RAM is not cleared at power-on
        ld b, 24 + 8            ; (chapter 13): the dirty marks and VARS
.clr:   ld (hl), 0
        inc hl
        djnz .clr
"""

PUT = """
; put: the metatile in A at row D, column E of the map, 0 to 11 and 0 to 15:
; its four names into the copy, and its two rows of names marked dirty
put:    push de
        add a, a
        add a, a                ; four names a metatile
        ld c, a
        ld b, 0
        ld hl, metas
        add hl, bc
        ex de, hl               ; DE: its names; H, L: row and column
        ld a, l
        add a, a
        ld c, a                 ; BC: 2 x column
        ld l, h
        ld h, 0
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl              ; 64 x row: two rows of 32 names
        add hl, bc
        ld bc, names
        add hl, bc              ; HL: its top left name in the copy
        ex de, hl
        ldi
        ldi                     ; the top two names
        ld a, e
        add a, 30
        ld e, a
        jr nc, .low
        inc d
.low:   ldi
        ldi                     ; and the two below them
        pop de
        ld a, d
        add a, a                ; its first row of names
        ld l, a
        ld h, high dirty
        ld (hl), 1
        inc l
        ld (hl), 1              ; and the second: both dirty
        ret
"""

EXPAND = """
; expand: the map's 192 metatiles into the copy of the names
expand: ld hl, map
        ld d, 0                 ; row
.row:   ld e, 0                 ; column
.col:   ld a, (hl)
        push hl
        call put
        pop hl
        inc hl
        inc e
        ld a, e
        cp 16
        jr nz, .col
        inc d
        ld a, d
        cp 12
        jr nz, .row
        ret
"""

STEP = """
; step: the next frame's changes, made in the copy while the paper is drawn:
; the player a metatile on, the map put back where he was, and every
; sixteenth frame the coins shown or hidden
step:   ld a, (px)
        ld e, a
        ld d, PROW
        call under              ; A: the map's metatile where he was
        call put
        ld a, (px)
        inc a
        cp 15
        jr nz, .in
        ld a, 1                 ; from the right wall back to the left
.in:    ld (px), a
        ld e, a
        ld d, PROW
        ld a, PLAYER
        call put
        ld hl, tick
        inc (hl)
        ld a, (hl)
        and 15
        ret nz                  ; fifteen frames in sixteen, no more
        ld a, (shown)
        xor COIN ^ SKY
        ld (shown), a           ; coin or sky
        ld hl, coins
        ld b, NCOINS
.coin:  push bc
        ld d, (hl)
        inc hl
        ld e, (hl)
        inc hl
        push hl
        ld a, (shown)
        call put
        pop hl
        pop bc
        djnz .coin
        ret

; under: A = the map's metatile at row D, column E
under:  ld a, d
        add a, a
        add a, a
        add a, a
        add a, a                ; 16 x row
        add a, e
        ld c, a
        ld b, 0
        ld hl, map
        add hl, bc
        ld a, (hl)
        ret
"""

FRAME = """
; frame: wait for the end of the paper: F, bit 7 of the status, read with the
; interrupts off (chapter 19)
frame:  in a, (VDP_CTRL)
        rla
        jr nc, frame
        ret
"""

SENDS = {
    "full": """
; send: the 768 names of the copy to the VDP, with OTIR, 23 T-states a byte
send:   VRAM_WRITE $1800
        ld hl, names
        ld c, VDP_DATA
        ld b, 0                 ; 256
        otir
        otir
        otir
        ret
""",
    "paper": """
; send: the 768 names of the copy to the VDP at 29 T-states a byte, safe while
; the paper is drawn (chapter 20)
send:   VRAM_WRITE $1800
        ld hl, names
        ld c, VDP_DATA
        ld d, 3
.page:  ld b, 0                 ; 256
.byte:  outi                    ; 18
        jp nz, .byte            ; 11
        dec d
        jr nz, .page
        ret
""",
    "dirty": """
; send: each row of names marked dirty, 32 bytes with OTIR, and its mark cleared
send:   ld de, $1800 | $4000    ; row 0's VRAM address, and the write bit
        ld hl, dirty
.row:   ld a, (hl)
        or a
        jr z, .next             ; clean: nothing to send
        ld (hl), 0
        push hl
        ld a, e
        out (VDP_CTRL), a
        ld a, d
        out (VDP_CTRL), a
        ld hl, names - ($1800 | $4000)
        add hl, de              ; the row in the copy
        ld bc, 32 << 8 | VDP_DATA
        otir
        pop hl
.next:  ld a, e
        add a, 32
        ld e, a
        jr nc, .same
        inc d                   ; the next row: 32 bytes on
.same:  inc l
        ld a, l
        cp 24
        jr nz, .row
        ret
""",
}

RAM = f"""names   EQU ${NAMES_RAM:04X}               ; the copy of the 768 names
dirty   EQU ${DIRTY_RAM:04X}               ; a mark for each of the 24 rows of names
px      EQU dirty + 24          ; the player's column of the map
tick    EQU dirty + 25          ; frames, counted
shown   EQU dirty + 26          ; the coins' metatile now: coin or sky
count   EQU dirty + 27          ; the frames left
next    EQU dirty + 28          ; late.asm's next screen, spin.asm's next drawing
wait    EQU dirty + 30          ; late.asm's wait into the paper, in turns of 30 T
PROW    EQU {PROW}                   ; the player's row of the map
SKY     EQU {META['sky']}
COIN    EQU {META['coin']}
PLAYER  EQU {META['player']}
NCOINS  EQU {len(COINS)}
COINT   EQU {TILE['coin_0']}                   ; the coin's first tile
"""


def data():
    shapes = [b for _, s, _ in TILES for b in s]
    cols = [b for _, _, c in TILES for b in c]
    out = "shapes:\n" + db_rows(shapes) + "colours:\n" + db_rows(cols)
    out += "metas:                          ; " + ", ".join(n for n, _ in METAS) + "\n"
    out += "".join(f"        db {', '.join(str(TILE[t]) for t in ts)}" + f"{'':>8}; {n}\n"
                   for n, ts in METAS)
    out += "map:                            ; 12 rows of 16 metatiles\n" + db_rows(MAP)
    out += "coins:  db " + ", ".join(f"{r}, {c}" for r, c in COINS) + "   ; row, column\n"
    return out


def moving(name, what, say):
    return head(name, what) + RAM + say + SETUP.format(nbytes=8 * len(TILES)) + f"""        call expand             ; the map into the copy
        ld a, {PSTART}
        ld (px), a
        ld d, PROW
        ld e, a
        ld a, PLAYER
        call put                ; the player in his first place
        ld a, COIN
        ld (shown), a
        call send               ; the copy to the VDP, the display off
        VDP_REG 1, $C0          ; the display on
        in a, (VDP_CTRL)        ; a flag left from before, cleared
        ld a, {FRAMES}
        ld (count), a
loop:   call frame              ; the end of the paper
m0:     call send               ; the copy to the VDP
m1:     call step               ; and the next frame's changes into it
        ld hl, count
        dec (hl)
        jr nz, loop
done:   jr done
""" + FRAME + SENDS[name] + STEP + PUT + EXPAND + data() + CART_END


SAY = {
    "full": """; Each frame, as soon as the paper ends, all 768 names of the copy go to the
; VDP with OTIR; then, while the paper is drawn, the next frame's changes are
; made in the copy.
""",
    "paper": """; full.asm with the 768 names sent at 29 T-states a byte, OUTI and JP NZ.
""",
    "dirty": """; full.asm sending only the rows of names that put marked dirty.
""",
}


def meta():
    return head("meta", "a screen from a map of metatiles") + RAM + \
        """; The map's 192 metatiles expanded into the copy of the names, the copy sent
; to the VDP, and the display turned on.
""" + SETUP.format(nbytes=8 * len(TILES)) + """e0:     call expand             ; the map into the copy
e1:     call send               ; the copy to the VDP, the display off
        VDP_REG 1, $C0          ; the display on
done:   jr done
""" + SENDS["full"] + PUT + EXPAND + data() + CART_END


LATE_SEND = """
; send: the 768 names at (next) to the VDP at 29 T-states a byte
send:   VRAM_WRITE $1800
        ld hl, (next)
        ld c, VDP_DATA
        ld d, 3
.page:  ld b, 0                 ; 256
.byte:  outi                    ; 18
        jp nz, .byte            ; 11
        dec d
        jr nz, .page
        ret
"""


def turns(machine):
    """late.asm's wait from the end of the paper to row TEAR_ROW of the next
    paper, in turns of 30 T-states"""
    return (WAIT[machine] + 8 * 228 * TEAR_ROW) // 30


def late():
    eu, jp = turns("MSXBOOK_EU16"), turns("MSXBOOK_JP16")
    return head("late", "a screen sent while the beam draws") + RAM + f"""; Two screens, the map and a second one, sent in turn at 29 T-states a byte, each
; send begun when the beam has drawn rows 0 to {TEAR_ROW - 1} of the paper.
""" + SETUP.format(nbytes=8 * len(TILES)) + f"""        call expand             ; the first screen into the copy
        ld hl, names
        ld (next), hl
        call send               ; and to the VDP, the display off
        VDP_REG 1, $C0          ; the display on
        ld a, ($002B)           ; bit 7 is 1 on a 50 Hz machine (chapter 4)
        rla
        ld hl, {jp}
        jr nc, .sixty
        ld hl, {eu}
.sixty: ld (wait), hl           ; the lines not drawn and {TEAR_ROW} rows, in turns
        ld hl, screen2
        ld (next), hl
        in a, (VDP_CTRL)        ; a flag left from before, cleared
        ld a, {TEARS}
        ld (count), a
loop:   call frame              ; the end of the paper
        ld bc, (wait)
.w:     dec bc                  ;  7
        ld a, b                 ;  5
        or c                    ;  5
        jr nz, .w               ; 13: 30 T-states a turn
m0:     call send
m1:     ld hl, (next)           ; the other screen, next time
        ld de, names
        or a
        sbc hl, de
        ld hl, names
        jr nz, .a
        ld hl, screen2
.a:     ld (next), hl
        ld hl, count
        dec (hl)
        jr nz, loop
done:   jr done
""" + FRAME + LATE_SEND + PUT + EXPAND + data() + "screen2:                        ; the second screen's 768 names\n" + \
        db_rows(names_of(MAP2)) + CART_END


def spin():
    return head("spin", "the coins turned by their shapes") + RAM + f"""; The map's screen; then every {SPIN_FRAMES} frames the four tiles of the coin get the
; next of four drawings, 32 bytes, and every coin on the screen turns.
""" + SETUP.format(nbytes=8 * len(TILES)) + f"""        call expand             ; the map into the copy
        call send               ; and to the VDP, the display off
        VDP_REG 1, $C0          ; the display on
        ld hl, phases + 32
        ld (next), hl           ; the second drawing first
        in a, (VDP_CTRL)        ; a flag left from before, cleared
        ld a, {SPINS}
        ld (count), a
loop:   ld b, {SPIN_FRAMES}
.f:     call frame              ; {SPIN_FRAMES} ends of the paper
        djnz .f
m0:     call turn
m1:     ld hl, count
        dec (hl)
        jr nz, loop
done:   jr done
""" + FRAME + f"""
; turn: the coin's four tiles, 32 bytes of shapes, from the next drawing
turn:   VRAM_WRITE COINT * 8
        ld hl, (next)
        ld bc, 32 << 8 | VDP_DATA
        otir
        ld de, phases + 4 * 32  ; past the fourth drawing,
        or a
        sbc hl, de
        add hl, de
        jr nz, .keep
        ld hl, phases           ; back to the first
.keep:  ld (next), hl
        ret
""" + SENDS["full"] + PUT + EXPAND + data() + "phases:                         ; the coin's four drawings, 32 bytes each\n" + \
        "".join(db_rows(ph) for ph in coin_phases()) + CART_END


BUF1, BUF2, BUF3 = 0xC800, 0xCB00, 0xCE00     # peek.asm's three copies read back


def peek():
    return head("peek", "a name read back three ways") + RAM + f"""buf1    EQU ${BUF1:04X}               ; the names read with RDVRM
buf2    EQU ${BUF2:04X}               ; ... with an address and an IN
buf3    EQU ${BUF3:04X}               ; ... from the copy in the RAM
; meta.asm's screen; then, the display off, all 768 names read back from the
; VRAM with C-BIOS's RDVRM, from the VRAM with an address and an IN each, and
; from the copy in the RAM, into three buffers.
""" + SETUP.format(nbytes=8 * len(TILES)) + """        call expand             ; the map into the copy
        call send               ; and to the VDP, the display off
p0:     ld hl, $1800
        ld de, buf1
        ld bc, 768
.a:     push bc
        push de
        call RDVRM              ; A: the byte at HL of the VRAM (chapter 19)
        di                      ; RDVRM turns the interrupts on (chapter 16)
        pop de
        ld (de), a
        inc de
        inc hl
        pop bc
        dec bc
        ld a, b
        or c
        jr nz, .a
p1:     ld hl, $1800
        ld de, buf2
        ld bc, 768
.b:     ld a, l
        out (VDP_CTRL), a
        ld a, h
        out (VDP_CTRL), a       ; the read address: bit 6 clear
        in a, (VDP_DATA)
        ld (de), a
        inc de
        inc hl
        dec bc
        ld a, b
        or c
        jr nz, .b
p2:     ld hl, names
        ld de, buf3
        ld bc, 768
.c:     ld a, (hl)              ; the copy
        ld (de), a
        inc de
        inc hl
        dec bc
        ld a, b
        or c
        jr nz, .c
p3:     VDP_REG 1, $C0          ; the display on
done:   jr done
""" + SENDS["full"] + PUT + EXPAND + data() + CART_END


PROGRAMS = {"meta": meta}
for _n in ("full", "paper", "dirty"):
    PROGRAMS[_n] = (lambda n: lambda: moving(n, {"full": "all the names with OTIR",
                                                  "paper": "all the names at 29 T-states a byte",
                                                  "dirty": "the dirty rows"}[n], SAY[n]))(_n)
PROGRAMS["late"] = late
PROGRAMS["spin"] = spin
PROGRAMS["peek"] = peek


def main():
    for name, make in PROGRAMS.items():
        with open(os.path.join(HERE, f"{name}.asm"), "w") as f:
            f.write(make())
    print(" ".join(f"{n}.asm" for n in PROGRAMS))


if __name__ == "__main__":
    main()
