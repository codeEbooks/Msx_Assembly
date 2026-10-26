#!/usr/bin/env python3
"""gen31.py - the programs of chapter 31: fast transfers to VRAM.

    python3 gen31.py && ./build.sh

    picture.inc  a picture for the whole Graphic II screen: 6,144 bytes of
                 shapes and 6,144 of colours, in 96 blocks of 128
    blank.asm    the 96 blocks with the display off, OUTIs in a row
    otir.asm     a few blocks after every paper, with OTIR (figure 31.1)
    chain.asm    a few blocks after every paper, with OUTIs in a row
    paper.asm    chain.asm's, and more blocks while the paper is drawn, with
                 OUTI and JP NZ
    any.asm      OUTIs in a row for any count from 1 to 128: a jump into the
                 chain
    fill.asm     the colours painted after every paper with OUT (C),A in a
                 row, 14 T-states a byte; the shapes cleared so, the display off
    halt.asm     chain.asm with the BIOS's interrupt: each burst after HALT,
                 behind the BIOS's routine
    hook.asm     the same bursts from H.TIMI, ahead of the keyboard
    double.asm   a new screen of names every frame, written into the table
                 not shown from line 4 of the paper on, and shown with R#2
                 (figure 31.3)
    fixed.asm    WHERE IT BREAKS: chain.asm with the 50 Hz machine's count of
                 blocks on both machines (figure 31.4)

The picture programs use the whole of Graphic II: three sets of shapes and
colours, R#3 = $FF and R#4 = $03 (chapter 22), names 0 to 255 in each third.
double.asm uses chapter 24's tiles and screens. Every program keeps the
interrupts off, waits for the end of the paper on the status (chapter 19),
reads bit 7 of $002B for the machine's rate (chapter 4), ends with
asmparts.CART_END, and build.sh assembles with --syntax=bFw.
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "ch24"))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "ch26"))
from asmparts import HEAD, CART_END  # noqa: E402
from gen26 import tidy, db_rows  # noqa: E402  (chapter 26)
import gen24  # noqa: E402  (chapter 24)

BIOS = '        INCLUDE "bios.inc"\n'
BLACK, DARK_BLUE, LIGHT_GREEN, WHITE = 1, 4, 3, 15
INK = BLACK << 4 | WHITE
BLOCK, BLOCKS = 128, 96                 # the picture: 96 blocks of 128 bytes
PER = {   # blocks after the paper, by technique: 60 Hz, 50 Hz
    "otir": (5, 8),
    "chain": (6, 11),
}
PAPER_BLOCKS = 11                       # paper.asm: blocks while the paper is drawn
FILL_PER = (8, 14)                      # fill.asm: blocks of 128 painted after the paper
FILL_COLOUR = BLACK << 4 | DARK_BLUE    # ... dark blue paper
ANY = [1, 16, 77, 34, 128]              # any.asm: the counts sent, two blocks in all
REGS_PIC = [2, 0xC0, 6, 0xFF, 3, 0x36, 7, 0x0F]
EU, JP = "MSXBOOK_EU16", "MSXBOOK_JP16"


def head(name, what):
    return HEAD.format(name=name, chapter=31, what=what) + BIOS


# ------------------------------------------------------------------ the picture
def drawing():
    """the picture as drawn: 192 rows of 256 colour codes"""
    from PIL import Image, ImageDraw
    im = Image.new("P", (256, 192), WHITE)
    d = ImageDraw.Draw(im)
    d.ellipse((176, 20, 232, 76), fill=LIGHT_GREEN, outline=BLACK, width=2)       # the sun
    for k in range(12):
        a = k * math.pi / 6
        d.line((204 + 34 * math.cos(a), 48 + 34 * math.sin(a),
                204 + 44 * math.cos(a), 48 + 44 * math.sin(a)), fill=BLACK, width=2)
    d.polygon([(0, 140), (40, 84), (70, 112), (110, 64), (160, 124), (190, 100), (256, 140)],
              fill=DARK_BLUE)                                                       # hills
    d.line([(110, 64), (122, 79), (114, 77), (106, 82), (99, 77)], fill=WHITE, width=1)
    d.rectangle((0, 140, 255, 191), fill=LIGHT_GREEN)                              # a field
    for y in range(146, 192, 6):
        d.line((0, y, 255, y + (y - 140) // 3), fill=BLACK)
    for cx, cy in ((40, 30), (110, 22)):                                           # clouds
        d.ellipse((cx - 22, cy - 8, cx + 22, cy + 10), fill=WHITE, outline=BLACK)
    px = im.load()
    return [[px[x, y] for x in range(256)] for y in range(192)]


GREY = {BLACK: 0, DARK_BLUE: 1, LIGHT_GREEN: 2, WHITE: 3}     # dark to light


def graphic2(pic):
    """the drawing in Graphic II: for every 8 pixels of a line, the two
    colours most of them have; the darker is the ink, a 1 in the shape, and a
    pixel of a third colour takes the nearer of the two. Shapes and colours,
    6,144 bytes each, in the order of the VRAM: third, cell, line"""
    shapes, colours = bytearray(6144), bytearray(6144)
    for y in range(192):
        for c in range(32):
            seg = pic[y][8 * c:8 * c + 8]
            two = sorted(set(seg), key=lambda k: (-seg.count(k), GREY[k]))[:2]
            if len(two) == 2:
                ink, paper = sorted(two, key=GREY.get)
            else:
                ink, paper = BLACK, two[0]          # one colour: all paper
            at = (y // 64) * 2048 + ((y % 64) // 8 * 32 + c) * 8 + y % 8
            for i, k in enumerate(seg):     # a 1 where the ink is nearer
                near_ink = abs(GREY[k] - GREY[ink]) <= abs(GREY[k] - GREY[paper])
                if ink != paper and near_ink:
                    shapes[at] |= 0x80 >> i
            colours[at] = ink << 4 | paper
    return bytes(shapes), bytes(colours)


SHAPES, COLOURS = graphic2(drawing())
PICTURE = SHAPES + COLOURS              # the 96 blocks, in the order they are sent


def picture_inc():
    return ("; picture.inc -- chapter 31: the picture, generated by gen31.py: 6,144 bytes\n"
            "; of shapes for $0000 and 6,144 of colours for $2000, 96 blocks of 128\n"
            "picture:\n" + db_rows(PICTURE, 16))


def blocks_per_frame(kind, machine):
    return PER[kind][machine == EU]


def frames_of(kind, machine):
    """the blocks sent after each frame's paper, frame by frame"""
    if kind == "fill":
        per, out, done = FILL_PER[machine == EU], [], 0
        while done < 48:
            done = min(48, done + per)
            out.append(done)
        return out
    per = blocks_per_frame("chain" if kind in ("paper", "fixed", "halt", "hook") else kind, machine)
    if kind == "fixed":
        per = PER["chain"][1]
    if kind == "paper":
        per += PAPER_BLOCKS
    out, done = [], 0
    while done < BLOCKS:
        done = min(BLOCKS, done + per)
        out.append(done)
    return out


def vram_of(done, painted=0):
    """the VRAM of a picture program once DONE blocks have arrived; of
    fill.asm, once PAINTED blocks of the colours are painted"""
    v = bytearray(16384)
    names = bytes(range(256)) * 3
    v[0x1800:0x1B00] = names
    v[0x1B00] = 0xD0
    v[0x2000:0x3800] = bytes([INK]) * 6144
    v[0x2000:0x2000 + BLOCK * painted] = bytes([FILL_COLOUR]) * (BLOCK * painted)
    sent = PICTURE[:BLOCK * done]
    v[0:min(6144, len(sent))] = sent[:6144]
    if len(sent) > 6144:
        v[0x2000:0x2000 + len(sent) - 6144] = sent[6144:]
    return v


# ------------------------------------------------------------------ routines
SETUP = """init:   di
        ld sp, SYS_AREA
        VDP_REG 1, $80          ; display off
        VDP_REG 0, $02          ; Graphic II
        VDP_REG 2, $06          ; names    $1800
        VDP_REG 3, $FF          ; colours  $2000, three sets
        VDP_REG 4, $03          ; shapes   $0000, three sets
        VDP_REG 5, $36          ; sprite attributes $1B00
        VDP_REG 6, $07          ; sprite patterns   $3800
        VDP_REG 7, $0F          ; border white
        VRAM_WRITE $1B00        ; no sprites
        ld a, $D0
        out (VDP_DATA), a
        VRAM_WRITE $1800        ; the names: 0 to 255 in each third
        ld e, 3
.names: xor a
.name:  out (VDP_DATA), a
        inc a
        jr nz, .name
        dec e
        jr nz, .names
        VRAM_WRITE $0000        ; the shapes: all paper
        xor a
        ld e, 24
        call fill
        VRAM_WRITE $2000        ; the colours: black on white
        ld a, ${ink:02X}
        ld e, 24
        call fill
        xor a
        ld (sent), a
        ld hl, picture
        ld (src), hl
"""

FILL = """
; fill: E blocks of 256 bytes of A to the VDP, after an address is set
fill:   ld b, 0
.out:   out (VDP_DATA), a
        djnz .out
        dec e
        jr nz, .out
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

PLACE = """
; place: the VDP's address, for writing, of block A of the picture: A x 128,
; and $800 more for the colours, from block 48: $2000 and not $1800
place:  ld d, a
        rrca
        and $80                 ; bit 0 of A, x 128: the low byte
        out (VDP_CTRL), a
        ld a, d
        srl a                   ; A / 2: the high byte
        cp 24
        jr c, .shapes
        add a, 8                ; the colours
.shapes: or $40
        out (VDP_CTRL), a
        ret
"""

BLOCKS_R = """
; {name}: up to E blocks of the picture with {send}, from block (sent) on:
; its address set first, and the colours' at block 48
{name}: ld a, (sent)
        call place
        ld hl, (src)
.block: ld a, (sent)
        cp 96
        jr z, .end              ; the picture is all sent
        cp 48
        call z, colours         ; the shapes sent: on to $2000
        call {send}             ; 128 bytes from HL
        ld a, (sent)
        inc a
        ld (sent), a
        dec e
        jr nz, .block
.end:   ld (src), hl
        ret

; colours: the address of the colours, $2000
colours: VRAM_WRITE $2000
        ret
"""

SENDS = {
    "otir": """
; otir128: 128 bytes from HL with OTIR, 23 T-states a byte: after the paper
otir128: ld c, VDP_DATA
        ld b, 128
        otir
        ret
""",
    "chain": """
; chain128: 128 bytes from HL with 128 OUTIs in a row, 18 T-states a byte:
; after the paper, or with the display off
chain128: ld c, VDP_DATA
""" + "        outi\n" * 128 + "        ret\n",
    "loop": """
; loop128: 128 bytes from HL with OUTI and JP NZ, 29 T-states a byte: safe
; while the paper is drawn (chapter 20)
loop128: ld c, VDP_DATA
        ld b, 128
.byte:  outi                    ; 18
        jp nz, .byte            ; 11
        ret
""",
}
SEND_NAME = {"otir": "otir128", "chain": "chain128", "loop": "loop128"}

RAM = """sent    EQU VARS                ; the blocks sent
per     EQU VARS + 1            ; the blocks after each paper, on this machine
src     EQU VARS + 2            ; the next block's bytes
"""


def rate(n60, n50):
    return f"""        ld a, ($002B)           ; bit 7 is 1 on a 50 Hz machine (chapter 4)
        rla
        ld a, {n60}                 ; blocks after the paper at 60 Hz ...
        jr nc, .sixty
        ld a, {n50}                 ; ... and at 50 Hz
.sixty: ld (per), a
"""


ON = """        VDP_REG 1, $C0          ; the display on
        in a, (VDP_CTRL)        ; F cleared: the first wait ends with a paper
"""
DONE = "done:   jr done\n"


def loop(paper=False):
    inner = f"""        ld e, {PAPER_BLOCKS}
        call during             ; more, while the paper is drawn
""" if paper else ""
    return f"""loop:   call frame              ; the end of the paper
m0:     ld a, (per)
        ld e, a
        call after              ; the blocks that fit before the next paper
m1:
{inner}s1:     ld a, (sent)
        cp 96
        jr nz, loop
"""


def program(name, what, say, body, routines):
    return (head(name, what) + RAM + say +
            tidy(SETUP.format(ink=INK) + body + DONE + FRAME + PLACE + FILL + routines) +
            '        INCLUDE "picture.inc"\n' + CART_END)


def after_prog(name, kind, what, say, n60, n50):
    return program(name, what, say, rate(n60, n50) + ON + loop(),
                   BLOCKS_R.format(name="after", send=SEND_NAME[kind]) + SENDS[kind])


def blank():
    return program("blank", "the picture with the display off", """; The 96 blocks of the picture with the display off, 128 OUTIs a block, and
; the display on after them.
""", """c0:     ld e, 96
        call after              ; all of it, the display off
c1:     VDP_REG 1, $C0          ; the display on
""", BLOCKS_R.format(name="after", send="chain128") + SENDS["chain"])


def otir():
    n60, n50 = PER["otir"]
    return after_prog("otir", "otir", "OTIR after the paper", f"""; After every paper, as many blocks of the picture as OTIR sends before the
; next paper: {n60} at 60 Hz, {n50} at 50 Hz.
""", n60, n50)


def chain():
    n60, n50 = PER["chain"]
    return after_prog("chain", "chain", "OUTIs in a row after the paper", f"""; After every paper, as many blocks of the picture as 128 OUTIs in a row send
; before the next paper: {n60} at 60 Hz, {n50} at 50 Hz.
""", n60, n50)


def paper():
    n60, n50 = PER["chain"]
    return program("paper", "after the paper and during it", f"""; chain.asm's blocks after every paper, and {PAPER_BLOCKS} more while the paper is
; drawn, with OUTI and JP NZ, 29 T-states a byte.
""", rate(n60, n50) + ON + loop(paper=True),
        BLOCKS_R.format(name="after", send="chain128") +
        BLOCKS_R.format(name="during", send="loop128").replace(
            "\n; colours: the address of the colours, $2000\ncolours: VRAM_WRITE $2000\n        ret\n", "") +
        SENDS["chain"] + SENDS["loop"])


def fixed():
    n50 = PER["chain"][1]
    return program("fixed", "the 50 Hz count of blocks everywhere", f"""; WHERE IT BREAKS. chain.asm with the 50 Hz machine's count, {n50} blocks after
; every paper, whatever bit 7 of $002B says.
""", f"""        ld a, {n50}                 ; the 50 Hz count, on every machine
        ld (per), a
""" + ON + loop(), BLOCKS_R.format(name="after", send="chain128") + SENDS["chain"])


# ------------------------------------------------------------------ any.asm
OUTIS = """
; outis: A bytes, 1 to 128, from HL with OUTIs in a row: a jump into the
; chain, two bytes an OUTI, past the 128 - A it does not need
outis:  ld c, VDP_DATA
        neg
        add a, 128              ; 128 - A: the OUTIs to skip
        add a, a                ; two bytes each
        ld e, a
        ld d, 0
        ld ix, chain
        add ix, de
        jp (ix)                 ; into the chain
chain:
""" + "        outi\n" * 128 + "        ret\n"


def any_prog():
    calls = "".join(f"""        ld a, {n}
a{i}:     call outis
""" for i, n in enumerate(ANY))
    return program("any", "OUTIs in a row, any count", f"""; The first two blocks of the picture in pieces of {', '.join(str(n) for n in ANY[:-1])} and
; {ANY[-1]} bytes, each sent by a jump into a chain of 128 OUTIs; the display off.
""", """        VRAM_WRITE $0000
        ld hl, picture
""" + calls + f"""a{len(ANY)}:     ld a, 2
        ld (sent), a
        VDP_REG 1, $C0          ; the display on
""", OUTIS)


# ------------------------------------------------------------------ fill.asm
OUT128 = """
; out128: 128 bytes of A with OUT (C),A in a row, 14 T-states a byte, the
; same byte every time: after the paper, or with the display off
out128: ld c, VDP_DATA
""" + "        out (c), a\n" * 128 + "        ret\n"

PAINT = f"""
; paint: up to E blocks of the colours painted ${FILL_COLOUR:02X}, from block (sent) on
paint:  ld a, (sent)
        add a, 48               ; the colours' blocks are 48 to 95
        call place
.block: ld a, (sent)
        cp 48
        ret z                   ; all painted
        ld a, ${FILL_COLOUR:02X}
        call out128
        ld hl, sent
        inc (hl)
        dec e
        jr nz, .block
        ret
"""


def fill_prog():
    n60, n50 = FILL_PER
    return program("fill", "OUT (C),A in a row", f"""; The shapes cleared with the display off by OUT (C),A in a row, 14 T-states a
; byte; then after every paper the colours painted ${FILL_COLOUR:02X}, dark blue paper, {n60}
; blocks at 60 Hz and {n50} at 50 Hz.
""", f"""c0:     VRAM_WRITE $0000        ; the shapes, all paper, again
        xor a
        ld e, 48
.clr:   call out128
        dec e
        jr nz, .clr
c1:
""" + rate(n60, n50) + ON + """loop:   call frame              ; the end of the paper
m0:     ld a, (per)
        ld e, a
        call paint              ; the blocks that fit before the next paper
m1:
s1:     ld a, (sent)
        cp 48
        jr nz, loop
""", PAINT + OUT128)


# ------------------------------------------------------------------ halt.asm, hook.asm
IDLE = 150                              # halt.asm, hook.asm: frames of waiting first
IRQ_ON = f"""        im 1
        VDP_REG 1, $E0          ; the display on, and its interrupt
        in a, (VDP_CTRL)        ; no signal left over
        ei
        ld b, {IDLE}                ; {IDLE} frames first: by then the BIOS's routine
.idle:  halt                    ; reads the keyboard one frame in three
        djnz .idle              ; (chapter 17)
"""


def halt_prog():
    n60, n50 = PER["chain"]
    return program("halt", "bursts after HALT", """; chain.asm with the BIOS's interrupt: HALT waits for it, and every burst
; starts when the BIOS's routine has come back.
""", rate(n60, n50) + IRQ_ON + """loop:   halt                    ; the BIOS's routine runs, and comes back here
m0:     ld a, (per)
        ld e, a
        call after
m1:     ld a, (sent)
        cp 96
        jr nz, loop
        di
""", BLOCKS_R.format(name="after", send="chain128") + SENDS["chain"])


def hook_prog():
    n60, n50 = PER["chain"]
    return program("hook", "bursts from H.TIMI", """; chain.asm's bursts from H.TIMI: the BIOS's routine calls tick every frame
; before it reads the keyboard.
""", rate(n60, n50) + IRQ_ON + """        di
        ld hl, tick             ; H.TIMI: JP tick, written with the
        ld (H_TIMI + 1), hl     ; interrupts off (chapter 17)
        ld a, $C3
        ld (H_TIMI), a
        ei
idle:   ld a, (sent)
        cp 96
        jr nz, idle             ; the bursts are tick's
        di
""", """
; tick: through H.TIMI every frame; the BIOS has saved every register
tick:
m0:     ld a, (per)
        ld e, a
        call after
m1:     ret
""" + BLOCKS_R.format(name="after", send="chain128") + SENDS["chain"])


# ------------------------------------------------------------------ double.asm
WORLD_W = 64                            # double.asm: chapter 24's two screens side by side
DOUBLE_FRAMES = 31


def world():
    """chapter 24's map and its second screen side by side: 24 rows of 64 names"""
    a, b = gen24.names_of(gen24.MAP), gen24.names_of(gen24.MAP2)
    return [a[32 * r:32 * r + 32] + b[32 * r:32 * r + 32] for r in range(24)]


def window(k):
    """the 768 names of the window at column k"""
    w = world()
    return [n for r in range(24) for n in w[r][k:k + 32]]


def double_shown(k):
    """the table R#2 shows after the k-th show: 0 for $1800, 1 for $1C00"""
    return (k + 1) % 2


def double_vram(k):
    """the VRAM double.asm shows after its k-th show (from 0): window k + 1 in
    the table shown, the tiles, the end of the sprites"""
    v = bytearray(16384)
    for n, (_, s, c) in enumerate(gen24.TILES):
        v[8 * n:8 * n + 8], v[0x2000 + 8 * n:0x2000 + 8 * n + 8] = bytes(s), bytes(c)
    t = (0x1800, 0x1C00)[double_shown(k)]
    v[t:t + 768] = bytes(window(k + 1))
    v[0x1B00] = 0xD0
    return v


def double_regs(k):
    return [2, 0xC0, 6 + double_shown(k), 0x9F, 0, 0x36, 7, 0x0F]


def double():
    w = world()
    nt = len(gen24.TILES)
    return head("double", "a new screen every frame, two name tables") + f"""count   EQU VARS                ; the frames left
at      EQU VARS + 1            ; the window's column in the world
table   EQU VARS + 2            ; the name table not shown: $18 or $1C, the high byte
wait    EQU VARS + 3            ; the wait into the paper, in turns of 30 T
; Chapter 24's two screens side by side, a world of 64 columns, and a window on
; it a column further every frame: its 768 names written into the table not
; shown, begun at line 32 of the paper, as chapter 24's late.asm did, and
; shown with R#2 after the paper.
""" + tidy(f"""init:   di
        ld sp, SYS_AREA
        VDP_REG 1, $80          ; display off
        VDP_REG 0, $02          ; Graphic II
        VDP_REG 2, $06          ; names    $1800, and $1C00 with R#2 = 7
        VDP_REG 3, $9F          ; colours  $2000, one set for three thirds
        VDP_REG 4, $00          ; shapes   $0000, one set for three thirds
        VDP_REG 5, $36          ; sprite attributes $1B00
        VDP_REG 6, $07          ; sprite patterns   $3800
        VDP_REG 7, $0F          ; border white
        VRAM_WRITE $1B00        ; no sprites
        ld a, $D0
        out (VDP_DATA), a
        VRAM_WRITE $0000        ; chapter 24's tiles
        ld hl, shapes
        ld c, VDP_DATA
        ld b, {8 * nt}
        otir
        VRAM_WRITE $2000
        ld hl, colours
        ld b, {8 * nt}
        otir
        xor a
        ld (at), a
        ld a, $18
        ld (table), a
        call write              ; window 0 in the table at $1800
        ld a, $1C
        ld (table), a
        ld hl, at
        inc (hl)
        call write              ; window 1 in the table at $1C00, not shown
        ld a, ($002B)           ; bit 7 is 1 on a 50 Hz machine (chapter 4)
        rla
        ld hl, 775
        jr nc, .sixty
        ld hl, 1162
.sixty: ld (wait), hl           ; the lines not drawn and 4 rows, in turns
""" + ON + f"""        ld a, {DOUBLE_FRAMES}
        ld (count), a
loop:   call frame              ; the end of the paper
m0:     call show               ; the table written last shown
m1:     ld bc, (wait)
.w:     dec bc                  ;  7
        ld a, b                 ;  5
        or c                    ;  5
        jr nz, .w               ; 13: 30 T-states a turn
        ld hl, at
        inc (hl)
w0:     call write              ; the next window, from line 32 of the paper
w1:     ld hl, count
        dec (hl)
        jr nz, loop
""" + DONE + FRAME + """
; show: R#2 to the table written last, and the other one taken for the next
show:   ld a, (table)
        cp $18
        ld a, 6                 ; R#2 = 6: $1800
        jr z, .r2
        inc a                   ; R#2 = 7: $1C00
.r2:    out (VDP_CTRL), a
        ld a, $80 | 2
        out (VDP_CTRL), a
        ld a, (table)
        xor $18 ^ $1C
        ld (table), a
        ret

; write: the window at column (at) into the table not shown, 29 T-states a
; name: 24 rows of 32 from the world's rows of 64
write:  xor a
        out (VDP_CTRL), a
        ld a, (table)
        or $40
        out (VDP_CTRL), a       ; the table's first name, for writing
        ld a, (at)
        ld e, a
        ld d, 0
        ld hl, world
        add hl, de              ; the world's column at the window's left
        ld c, VDP_DATA
        ld e, 24
.row:   ld b, 32
.name:  outi                    ; 18
        jp nz, .name            ; 11
        ld a, l
        add a, 32               ; the world's next row: 64 on, 32 already
        ld l, a
        jr nc, .next
        inc h
.next:  dec e
        jr nz, .row
        ret
""") + ("shapes:\n" + db_rows([b for _, s, _ in gen24.TILES for b in s]) +
        "colours:\n" + db_rows([b for _, _, c in gen24.TILES for b in c]) +
        "world:                          ; 24 rows of 64 names\n" +
        db_rows([n for row in w for n in row], 16)) + CART_END


PROGRAMS = {"blank": blank, "otir": otir, "chain": chain, "paper": paper, "any": any_prog,
            "fill": fill_prog, "halt": halt_prog, "hook": hook_prog, "double": double,
            "fixed": fixed}


def main():
    with open(os.path.join(HERE, "picture.inc"), "w") as f:
        f.write(picture_inc())
    for name, make in PROGRAMS.items():
        with open(os.path.join(HERE, f"{name}.asm"), "w") as f:
            f.write(make())
    print("picture.inc " + " ".join(f"{n}.asm" for n in PROGRAMS))


if __name__ == "__main__":
    main()
