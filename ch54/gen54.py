#!/usr/bin/env python3
"""gen54.py - the programs of chapter 54: LANTERN KEEP with a title of its
own and a demo that plays itself.

    python3 gen54.py && ./build.sh

    game.asm    LANTERN KEEP, chapter 46's, with what a cartridge shows while
                nobody plays: the ATTRACT MODE. The title is chapter 53's
                picture, the keep at night, with the game's name, PRESS SPACE
                and the best score; it is drawn a row of cells a frame, with
                the display off, from chapter 53's packed bytes, by chapter
                53's unlz made to stop at the end of a row. SPACE or button A
                begins a game; IDLE steps with neither begin the DEMO: the
                game of chapter 46 planned by model46.py on the 60 Hz machine,
                every lantern lit, kept as pairs of bytes, steps and keys,
                which pad gives the explorer a step at a time. A key ends the
                demo; at its end the title comes back. The demo's score is
                not the best. Between the title and the game the VDP's tables
                go back to the game's sets, a block of 2,048 bytes a frame
    frames.asm  WHERE IT BREAKS: game.asm whose pad gives the demo's keys a
                frame at a time, as chapter 47's demos do, instead of a step
                at a time

Everything that decides the game is done a step at a time: the walk, the
guards, the time, and here the lanterns too, which chapter 46 looked at once
a frame. The steps are chapter 44's, 262 lines apart, one a frame on the
60 Hz machine and one or two on the 50 Hz one, so that the game runs as fast
on both; the demo, counted in steps, is then the same game on both. Every
line of this chapter's own routines carries its price, the MSX's T-states,
which meas54.py checks with walk.py and the debugger. build.sh assembles
with --syntax=bFw.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
for ch in ("tools", "ch26", "ch37", "ch45", "ch46", "ch53"):
    sys.path.insert(0, os.path.join(REPO, ch))
from gen26 import tidy, db_rows  # noqa: E402  (chapter 26)
import gen46  # noqa: E402  (chapter 46: LANTERN KEEP finished)
import gen53  # noqa: E402  (chapter 53: unlz)
import pic53  # noqa: E402  (chapter 53: the keep at night)
import pack53  # noqa: E402  (chapter 53: lz)
sys.path.insert(0, HERE)

gen45, gen44, gen37 = gen46.gen45, gen46.gen44, gen46.gen37
EU, JP = gen46.EU, gen46.JP
MACHINES = gen46.MACHINES
PROGRAMS = ["game", "frames"]
BLACK, WHITE = pic53.BLACK, pic53.WHITE
STATES = gen46.STATES + ["DRAW"]
DRAW = 7
IDLE = 600                  # steps of the title before the demo: ten seconds
ROWS = 24                   # the title's rows of cells, one a frame
BLOCKS = 6                  # the game's sets: three thirds' shapes and colours
BUFFER_AT = 0xD000          # unrow's copies: a page above the rooms' pictures
FONT = gen45.FONT           # chapter 30's characters, codes 32 to 127

# ---------------------------------------------------------------- the title
# the words on the picture: (column, row, text), white on black, where the
# picture is black sky or black hill (checked below)
TITLE_WORDS = [(10, 1, "LANTERN KEEP"), (2, 22, "PRESS SPACE"), (22, 22, "HI")]
HI_CELL = (25, 22)          # the best's six digits, written when the title is drawn


def glyph(c):
    return FONT[8 * (ord(c) - 32):8 * (ord(c) - 32) + 8]


def title_picture():
    """chapter 53's picture with the words on it: each word's cells black,
    its characters white"""
    rows = pic53.picture()
    cells = [(col + i, row, ch) for col, row, text in TITLE_WORDS for i, ch in enumerate(text)]
    cells += [(HI_CELL[0] + i, HI_CELL[1], " ") for i in range(6)]
    for col, row, ch in cells:
        for line, bits in enumerate(glyph(ch)):
            for b in range(8):
                rows[8 * row + line][8 * col + b] = WHITE if bits >> (7 - b) & 1 else BLACK
    return rows


def under_words():
    """the picture's colours under the words before they were put there:
    black, or the stars' white, only"""
    rows = pic53.picture()
    out = set()
    for col, row, text in TITLE_WORDS + [(HI_CELL[0], HI_CELL[1], "      ")]:
        for y in range(8 * row, 8 * row + 8):
            out |= set(rows[y][8 * col:8 * (col + len(text))])
    return out


assert under_words() <= {BLACK, WHITE}, under_words()
TPAT, TCOL = pic53.graphic2(title_picture())
assert pic53.shown(TPAT, TCOL) == title_picture()
TPAT_LZ, TCOL_LZ = pack53.lz(TPAT), pack53.lz(TCOL)
assert pack53.unlz(TPAT_LZ) == TPAT and pack53.unlz(TCOL_LZ) == TCOL
THI = (HI_CELL[1] // 8 * 256 + HI_CELL[1] % 8 * 32 + HI_CELL[0]) * 8      # the first digit's shape


# ---------------------------------------------------------------- the demo
def demo_keys(machine=None):
    """the keys of each step the explorer walked in chapter 46's game on the
    60 Hz machine, game_jp.events replayed on model46.py (or on MACHINE, its
    events): the cursor keys only, M (the map) left out; a 0 for each key
    held"""
    sys.path.insert(0, os.path.join(REPO, "ch46"))
    import model46
    keys = []

    class Count(model46.Keep):
        def walk(self):
            keys.append(self.held | 0x20)
            return model46.Keep.walk(self)
    m = JP if machine is None else machine
    ev = model46.read_events(model46.events_path("game", m))
    g = Count(m)
    while not any(e[1] == "ENDED" for e in g.events):
        g.step_loop(model46.keys_at(ev, g.ticks + 1 + model46.EVENT_AHEAD[m]))
    assert [e for e in g.events if e[1] == "ENDED"][0][2:5] == ("THE KEEP IS LIT", 3946, 3946)
    return keys


def pairs_of(keys):
    """the keys, one a step -> pairs: the steps, 1 to 255, and the keys"""
    out = []
    for k in keys:
        if out and out[-1][1] == k and out[-1][0] < 255:
            out[-1][0] += 1
        else:
            out.append([1, k])
    return [tuple(p) for p in out]


GCOPY = gen46.first_copy() + [0xD0, 0, gen46.GUARD_P, gen46.GUARD_C] * 2 + [0xD0]
assert len(GCOPY) == 13 and gen46.title_copy()[6:8] == GCOPY[6:8] == GCOPY[10:12]
KEY_NAMES = {1: "up", 2: "down", 4: "left", 8: "right"}
DEMO_KEYS = demo_keys()
DEMO = pairs_of(DEMO_KEYS)


def demo_data():
    out = ["dpairs:                         ; the demo: pairs of steps and keys, a 0 for each",
           "                                ; key held, and a 0 at the end"]
    for n, held in DEMO:
        names = " ".join(v for b, v in KEY_NAMES.items() if not held & b) or "none"
        out.append(f"        db {n}, %{held:08b}".ljust(32) + f"; {names}")
    out.append("        db 0                    ; the end: no keys from then on")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- the RAM
_STATE = "; TITLE, PLAY, FLIP, MAP, HIT, OVER or WIN\n"
assert gen46.RAM.count(_STATE) == 1
RAM = gen46.RAM.replace(_STATE, "; TITLE, PLAY, FLIP, MAP, HIT, OVER, WIN or DRAW\n") + f"""pkeys   EQU VARS + $B0          ; the keys a step walks by: held, or the demo's
demo    EQU VARS + $B1          ; 1 while the demo plays
dleft   EQU VARS + $B2          ; the steps left of the demo's pair
dnext   EQU VARS + $B3          ; the demo's next pair, two bytes
idle    EQU VARS + $B5          ; the title's steps, two bytes
part    EQU VARS + $B7          ; the title's next row of cells; DRAW's next block
pnext   EQU VARS + $B8          ; the title's patterns: the next packed byte,
pvram   EQU VARS + $BA          ; and the VRAM address it unpacks to
cnext   EQU VARS + $BC          ; its colours: the same two
cvram   EQU VARS + $BE
upto    EQU VARS + $C0          ; unrow's last page
BUFFER  EQU ${BUFFER_AT:04X}               ; unrow's copies: a page of their own
"""
CONSTS = gen46.CONSTS.replace("WIN     EQU 6\n", f"""WIN     EQU 6
DRAW    EQU {DRAW}                   ; the game's sets drawn again
""") + f"""IDLE    EQU {IDLE}                 ; steps of the title before the demo
ROWS    EQU {ROWS}                  ; the title's rows of cells
BLOCKS  EQU {BLOCKS}                   ; the game's sets: blocks of 2,048 bytes
THI     EQU ${THI:04X}               ; the shape of the best's first digit on the title
"""
assert "DRAW    EQU" in CONSTS

# ---------------------------------------------------------------- the routines
TITLE_RT = """
; totitle: the display off, which INIT leaves off, and the title
totitle: di                     ;  5
        VDP_REG 1, $A2          ; 40  display off; the signal, sprites 16 x 16
        ei                      ;  5
        ld a, TITLE             ;  8
        jp go                   ; 11

; title0: THE TITLE. The picture to be drawn from its first row of cells,
; from its packed bytes; no demo; no key pressed until one is let go; no
; sprites; the tune from its first bar, with the interrupts off for retune
title0: di                      ;  5
        call retune             ; 18  the tune again
        ei                      ;  5
        xor a                   ;  5
        ld (part), a             ; 14  the first row of cells
        ld (demo), a            ; 14  no demo
        ld hl, tpat             ; 11  the patterns' packed bytes
        ld (pnext), hl          ; 17
        ld hl, $0000            ; 11  and where they go
        ld (pvram), hl          ; 17
        ld hl, tcol             ; 11  the colours'
        ld (cnext), hl          ; 17
        ld hl, $2000            ; 11
        ld (cvram), hl          ; 17
        ld (was), a             ; 14  every key held before: one still down is no press
        ld a, $D0               ;  8
        ld (explorer), a        ; 14  the end of the sprites: none shown
        ret                     ; 11

; title1: THE FRAME OF THE TITLE. A row of cells of the picture, its patterns
; and then its colours, with the interrupts off, until the last; then the
; names, the best and the display on; then the steps counted: SPACE or button
; A pressed begins a game, and IDLE steps with neither the demo
title1: ld a, (part)             ; 14
        cp ROWS                 ;  8
        jr nc, .drawn           ; 13, or 8
        di                      ;  5
        ld hl, (pnext)          ; 17
        ld de, (pvram)          ; 22
        inc a                   ;  5  the patterns up to the next row's page
        call unrow              ; 18
        ld (pnext), hl          ; 17
        ld (pvram), de          ; 22
        ld hl, (cnext)          ; 17
        ld de, (cvram)          ; 22
        ld a, (part)             ; 14
        add a, $21              ;  8  the colours up to theirs
        call unrow              ; 18
        ld (cnext), hl          ; 17
        ld (cvram), de          ; 22
        ei                      ;  5
        ld hl, part             ; 11
        inc (hl)                ; 12  the next row, the next frame
        ret                     ; 11
.drawn: jr nz, .count           ; 13, or 8  shown already
        ld hl, part             ; 11
        inc (hl)                ; 12  ROWS + 1 from now on
        di                      ;  5
        call shown              ; 18
        ei                      ;  5
        ld hl, 0                ; 11
        ld (idle), hl           ; 17
        ld (due), hl            ; 17  no steps owed yet
        ret                     ; 11
.count: call paced              ; 18  B: the steps owed (chapter 44)
        ld hl, (idle)           ; 17
        ld c, b                 ;  5
        ld b, 0                 ;  8
        add hl, bc              ; 12
        ld (idle), hl           ; 17
        call presses            ; 18
        and $10                 ;  8  SPACE or button A pressed now
        jr nz, .game            ; 13, or 8
        ld hl, (idle)           ; 17
        ld de, -IDLE            ; 11
        add hl, de              ; 12  carry: IDLE steps or more
        ret nc                  ; 12, or 6
        ld a, 1                 ;  8  the demo
        jr .begin               ; 13
.game:  xor a                   ;  5  a game
.begin: ld (demo), a            ; 14
        ld a, DRAW              ;  8
        jp go                   ; 11

; shown: the title's names, 0 to 255 in each third; the best's six digits on
; it; a set of shapes and colours for each third; and the display on. The
; interrupts off. Uses A, BC, DE, HL
shown:  VRAM_WRITE $1800        ; 40
        xor a                   ;  5
        ld d, 3                 ;  8
.name:  out (VDP_DATA), a       ; 12
        inc a                   ;  5
        jr nz, .name            ; 13, or 8
        dec d                   ;  5
        jr nz, .name            ; 13, or 8
        ld de, THI | $4000      ; 11  the first digit's shape
        ld hl, hi               ; 11
        ld b, 3                 ;  8  three BCD bytes
.byte:  ld a, (hl)              ;  8
        rrca                    ;  5
        rrca                    ;  5
        rrca                    ;  5
        rrca                    ;  5
        call digit              ; 18  the first digit
        ld a, (hl)              ;  8
        call digit              ; 18  the second
        inc hl                  ;  7
        djnz .byte              ; 14, or 9
        VDP_REG 3, MAP_R3       ; 40  colours $2000: a set for each third
        VDP_REG 4, MAP_R4       ; 40  shapes $0000: a set for each third
        VDP_REG 1, $E2          ; 40  the display on
        ret                     ; 11

; digit: A's low four bits = a digit, DE = its cell's shape, + $4000 -> its
; character's eight lines there, white on black; DE the next cell's. Keeps
; B and HL. Uses A, C, DE
digit:  push hl                 ; 12
        push bc                 ; 12
        and 15                  ;  8
        add a, DIGIT0           ;  8  its character
        ld l, a                 ;  5
        ld h, 0                 ;  8
        add hl, hl              ; 12
        add hl, hl              ; 12
        add hl, hl              ; 12  eight bytes a character
        ld bc, vshapes          ; 11  chapter 46's shapes, in the second half
        add hl, bc              ; 12
        ld a, e                 ;  5
        out (VDP_CTRL), a       ; 12
        ld a, d                 ;  5
        out (VDP_CTRL), a       ; 12  its cell's shape
        ld bc, 8 << 8 | VDP_DATA ; 11
        otir                    ; 23 a byte, 18 the last
        ld a, e                 ;  5
        out (VDP_CTRL), a       ; 12
        ld a, d                 ;  5
        add a, $20              ;  8
        out (VDP_CTRL), a       ; 12  and its colours
        ld a, WHITE << 4 | BLACK ;  8
        ld b, 8                 ;  8
.colour: out (VDP_DATA), a      ; 12
        djnz .colour            ; 14, or 9
        ld a, e                 ;  5
        add a, 8                ;  8  the next cell, in the same page
        ld e, a                 ;  5
        pop bc                  ; 11
        pop hl                  ; 11
        ret                     ; 11
"""

WAS_LINE = "        ld (was), a             ; 14  every key held before: one still down is no press\n"
assert TITLE_RT.count(WAS_LINE) == 1

UNROW = gen53.UNLZ.replace(
    """; unlz: HL = packed bytes, copies; DE = the VRAM address they unpack to ->
; unpacked there, 29 T-states a byte or more. A count, then: 1 to 127, that
; many bytes as they are; 128 to 255, a byte, a distance back less one, and
; (count - 128) + 3 bytes copied from 1 to 256 bytes back, never more than
; the distance: read from the VRAM into a page of the RAM, then written
; again; 0, the end. Uses A, BC, DE, HL
unlz:   ld c, VDP_DATA          ;  8
""", """; unrow: chapter 53's unlz, which stops where a row of cells ends. HL =
; packed bytes, copies; DE = the VRAM address they unpack to; A = the page
; of the VRAM after the row -> unpacked until DE is in that page; HL the
; next count, DE the next address. Uses A, BC, DE, HL
unrow:  ld (upto), a            ; 14
        ld c, VDP_DATA          ;  8
""").replace(""".next:  ld a, (hl)              ;  8  a count
""", """.next:  ld a, (upto)            ; 14
        cp d                    ;  5
        ret z                   ; 12, or 6  the row is whole
        ld a, (hl)              ;  8  a count
""")
assert "unrow:  ld (upto), a" in UNROW and "unlz" not in UNROW.replace("unlz,", "") and "ret z                   ; 12, or 6  the row is whole" in UNROW

DRAW_RT = """
; draw0: A GAME, OR THE DEMO. The display off while the game's sets go back
; into the tables the title used, a block a frame
draw0:  di                      ;  5
        VDP_REG 1, $A2          ; 40  display off
        ei                      ;  5
        xor a                   ;  5
        ld (part), a             ; 14  the first block
        ret                     ; 11

; draw1: THE FRAME OF DRAW. The next of the six blocks of 2,048 bytes of
; chapter 46's sets, a third's shapes and then its colours, with the
; interrupts off; after the sixth, row 0, the status line, then the game set
; up and the flip into its first room, whose page the next sends show
draw1:  ld a, (part)             ; 14
        cp BLOCKS               ;  8
        jr z, .names            ; 13, or 8
        inc a                   ;  5
        ld (part), a             ; 14  the next, the frame after
        dec a                   ;  5  this block's number
        rrca                    ;  5  carry: a third's colours
        ld hl, vshapes          ; 11
        ld d, $00 | $40         ;  8
        jr nc, .third           ; 13, or 8
        ld hl, vcolours         ; 11
        ld d, $20 | $40         ;  8
.third: and $7F                 ;  8  the third
        add a, a                ;  5
        add a, a                ;  5
        add a, a                ;  5  eight pages a third
        add a, d                ;  5
        ld d, a                 ;  5
        ld e, 0                 ;  8
        di                      ;  5
        call set2k              ; 18  (chapter 45)
        ei                      ;  5
        ret                     ; 11
.names: di                      ;  5
        VRAM_WRITE $1800        ; 40
        ld hl, trow0            ; 11  row 0
        ld bc, 32 << 8 | VDP_DATA ; 11
        otir                    ; 23 a byte, 18 the last
        ei                      ;  5
        call setup              ; 18  the game, or the demo
        ld a, FLIP              ;  8
        jp go                   ; 11
"""
SET2K = gen46.SETS[gen46.SETS.index("; set2k:"):]
assert SET2K.startswith("; set2k:") and "sets:" not in SET2K

PAD = """
; pad: the keys for a step -> pkeys: in a game held, as isr read them; in the
; demo the next of its pairs of bytes, steps and keys, a 0 for each key held,
; and none held after the last. Uses A, HL
pad:    ld a, (demo)            ; 14
        or a                    ;  5
        ld a, (held)            ; 14
        jr z, .keys             ; 13, or 8  a game: the keys held
        ld hl, dleft            ; 11
        dec (hl)                ; 12  a step fewer of these keys
        ld a, (pkeys)            ; 14
        ret nz                  ; 12, or 6  the same keys as before
        ld hl, (dnext)          ; 17  none left: the next pair
        ld a, (hl)              ;  8  its steps
        or a                    ;  5
        jr z, .none             ; 13, or 8  the end
        ld (dleft), a           ; 14
        inc hl                  ;  7
        ld a, (hl)              ;  8  its keys
        inc hl                  ;  7
        ld (dnext), hl          ; 17
.keys:  ld (pkeys), a            ; 14
        ret                     ; 11
.none:  inc (hl)?               ;
"""

# pad's end: dleft back to 1, so that each step after reads the 0 again
PAD = PAD.replace(""".none:  inc (hl)?               ;
""", """.none:  inc a                   ;  5
        ld (dleft), a           ; 14  1: the end read again at the next step
        ld a, $FF               ;  8  no keys
        jr .keys                ; 13
""")


def play_rt(frames=False, lamps_frame=False):
    """play1 a step at a time: pad, walk, the guards, the time and the
    lanterns, each step; the demo's keys from pad, which FRAMES (frames.asm)
    calls once a frame instead; LAMPS_FRAME (the workshop): the lanterns once
    a frame, after the steps, as chapter 46 had them"""
    pad_frame = "        call pad                ; 18  WHERE IT BREAKS: the keys for the frame\n" if frames else ""
    pad_step = "" if frames else "        call pad                ; 18  the keys for the step\n"
    return """
; play0: no steps owed yet, and no keys pressed
play0:  ld hl, 0                ; 11
        ld (due), hl            ; 17
        ld a, (held)            ; 14
        ld (was), a             ; 14
        ret                     ; 11

; play1: THE FRAME OF THE PLAY. A room seen for the first time gets its
; picture for the map, a frame of its own; C, which isr kept from the frame
; the sends before drew, is a guard's touch; in a game, M or button B
; pressed shows the map, and in the demo any key ends it; else, for each
; step owed, the keys for it, a step of the explorer, out of the room when
; it goes through a door, a step of each guard, of the time, which at none
; ends the game, and the lanterns the explorer reaches, which with the last
; end it too. Uses every register but IY
play1:  ld a, (fresh)           ; 14
        or a                    ;  5
        jr z, .look             ; 13, or 8
        call mini               ; 18  its picture
        jp play0                ; 11  and the frame counts as none
.look:  ld a, (stat)            ; 14
        and $20                 ;  8  C: two sprites met
        ld a, HIT               ;  8
        jp nz, go               ; 11  a guard touched the explorer
        ld a, (demo)            ; 14
        or a                    ;  5
        jr z, .map              ; 13, or 8
        ld a, (held)            ; 14  the demo: a key held?
        or $C0                  ;  8
        inc a                   ;  5  Z: none
        jp nz, totitle          ; 11  a key ends the demo
        jr .owed                ; 13
.map:   call presses            ; 18
        and $20                 ;  8  M or button B
        jr nz, tomap            ; 13, or 8
.owed:
""" + pad_frame + """        call paced              ; 18  B: the steps owed (chapter 44)
.step:  push bc                 ; 12
""" + pad_step + """        call walk               ; 18  carry: out, by D's way
        pop bc                  ; 11
        jp c, leave             ; 11  through a door
        push bc                 ; 12
        call guards             ; 18
        call clock              ; 18  Z: no time left
        pop bc                  ; 11
        jr z, timeup            ; 13, or 8
""" + ("""        djnz .step              ; 14, or 9
        jp lamps                ; 11  once a frame, as in chapter 46
""" if lamps_frame else """        push bc                 ; 12
        call lamps              ; 18  WIN with the last
        pop bc                  ; 11
        ld a, (state)           ; 14
        cp PLAY                 ;  8
        ret nz                  ; 12, or 6  the keep lit
        djnz .step              ; 14, or 9
        ret                     ; 11
""") + """timeup: ld a, OVER              ;  8
        jp go                   ; 11
tomap:  ld a, MAP               ;  8
        jp go                   ; 11
"""


def check_play():
    old = gen46.PLAY_RT[:gen46.PLAY_RT.index("; hit0:")]
    for frag in ("play0:  ld hl, 0", "jp lamps                ; 11", "djnz .step              ; 14, or 9"):
        assert frag in old, frag


check_play()
HIT_ETC = gen46.PLAY_RT[gen46.PLAY_RT.index("; hit0:"):]

WALK = gen45.WALK.replace("""; walk: held -> the explorer""", """; walk: pkeys -> the explorer""")
assert WALK.count("        ld hl, held             ; 11\n") == 2
WALK = WALK.replace("        ld hl, held             ; 11\n", "        ld hl, pkeys            ; 11\n")

END_RT = gen46.END_RT.replace("""; over1: the end's frame, OVER's and WIN's: a room of the map unlit, the
; steps owed off the wait, and at its end the title again
over1:  call dim                ; 18
        call countdown          ; 18
        ret nz                  ; 12, or 6
        ld a, TITLE             ;  8
        jp go                   ; 11
""", """; over1: the end's frame, OVER's and WIN's: a room of the map unlit, the
; steps owed off the wait, and at its end the title again
over1:  call dim                ; 18
        call countdown          ; 18
        ret nz                  ; 12, or 6
        jp totitle              ; 11
""").replace("""; ending: HL = the end's box -> the sprites hidden, hi kept the best, the box
; on the screen with the score and the best, and ENDS steps of it, while
; the map's rooms are unlit again. Uses every register but IY
ending: ld a, $D0               ;  8
        ld (explorer), a        ; 14  the end of the sprites: none shown
        push hl                 ; 12
        call best               ; 18  hi kept the best (chapter 40)
        pop hl                  ; 11
""", """; ending: HL = the end's box -> the sprites hidden, hi kept the best but
; not after the demo, the box on the screen with the score and the best,
; and ENDS steps of it, while the map's rooms are unlit again. Uses every
; register but IY
ending: ld a, $D0               ;  8
        ld (explorer), a        ; 14  the end of the sprites: none shown
        push hl                 ; 12
        ld a, (demo)            ; 14
        or a                    ;  5
        call z, best            ; 18, or 11  hi kept the best (chapter 40)
        pop hl                  ; 11
""")
assert END_RT != gen46.END_RT

FLIP_RT = gen46.flip_rt().replace("""
; flip1: the page sent, with the sprites: the play again
flip1:  ld a, PLAY              ;  8
        jp go                   ; 11
""", """
; flip1: the page sent, with the sprites: the display on, which DRAW left
; off, and the play again
flip1:  di                      ;  5
        VDP_REG 1, $E2          ; 40  the display on
        ei                      ;  5
        ld a, PLAY              ;  8
        jp go                   ; 11
""")
assert FLIP_RT != gen46.flip_rt()

SETUP = gen46.STATES_RT[gen46.STATES_RT.index("; setup:"):]
old = """        ld bc, 4                ; 11
        ldir                    ; 23 a byte, 18 the last
        ret                     ; 11
"""
assert SETUP.count(old) == 1 and SETUP.rstrip().endswith("ret                     ; 11")
SETUP = SETUP.replace("""; setup: a new game. No names queued, no rooms seen, no lantern lit; score
; 0, LIVES lives, the time full; the explorer in the gate hall at its first
; place
""", """; setup: a new game, or the demo. No names queued, no rooms seen, no
; lantern lit; score 0, LIVES lives, the time full; the explorer in the gate
; hall at its first place, the guards' sprites ready for greset; and the
; demo, if it is one, from its first pair
""").replace("""        ld hl, first            ; 11  the explorer's first place
""", """        ld hl, gcopy            ; 11  the explorer's first place
""").replace(old, """        ld bc, 13               ; 11  and the guards' patterns and colours
        ldir                    ; 23 a byte, 18 the last
        ld a, 1                 ;  8
        ld (dleft), a           ; 14  the first pair at the first step
        ld hl, dpairs           ; 11
        ld (dnext), hl          ; 17
        ret                     ; 11
""")


def setup_lines():
    """chapter 46's start, without its sets, which the title would cover,
    and with the display left off: the title shows itself when drawn"""
    out = gen46.setup_lines()
    for old, new in (("        call sets               ; the shapes and colours of the three thirds\n", ""),
                     ("        VDP_REG 1, $E2          ; display on, the frame's signal, sprites 16 x 16\n",
                      "        VDP_REG 1, $A2          ; display off, the frame's signal, sprites 16 x 16\n")):
        assert out.count(old) == 1, old
        out = out.replace(old, new)
    return out


def data():
    out = gen46.data()
    old = """starts:                         ; each state's first frame
        dw title0, play0, flip0, map0, hit0, over0, win0
        ALIGN 16
frames:                         ; and every frame of it
        dw title1, play1, flip1, map1, hit1, over1, over1
"""
    assert out.count(old) == 1
    out = out.replace(old, """starts:                         ; each state's first frame
        dw title0, play0, flip0, map0, hit0, over0, win0, draw0
        ALIGN 16
frames:                         ; and every frame of it
        dw title1, play1, flip1, map1, hit1, over1, over1, draw1
""")
    out += (f"tpat:                           ; the title's patterns, lz (chapter 53): {len(TPAT_LZ):,} bytes\n" +
            db_rows(TPAT_LZ) +
            f"tcol:                           ; and its colours: {len(TCOL_LZ):,} bytes\n" + db_rows(TCOL_LZ) +
            "gcopy:                          ; the sprites as a game begins: the explorer, two\n"
            "                                ; guards greset places, the end\n" + db_rows(GCOPY) +
            "trow0:                          ; row 0 as a game begins: the status line\n" +
            db_rows(gen46.row0()) + demo_data())
    return out


SAY = {
    "game": """; LANTERN KEEP, chapter 46's, with a title of its own and a demo that plays
; itself. The title is chapter 53's picture, drawn a row of cells a frame;
; IDLE steps of it begin the demo, chapter 46's game played back a step at a
; time from pairs of steps and keys; SPACE or button A begins a game.
""",
    "frames": """; WHERE IT BREAKS. game.asm with the demo's keys given a frame at a time.
""",
}
WHAT = {"game": "LANTERN KEEP with its title and its demo",
        "frames": "the demo's keys a frame at a time"}
HEAD = '''; {name}.asm -- chapter 54: {what}
; generated by gen54.py
        INCLUDE "msx.inc"
        OUTPUT "{name}.rom"
        ORG $4000
        CART_HEADER init
VARS    EQU RAM_START + $100    ; the program's variables: the code is in ROM
'''


def program(name, lamps_frame=False, keep_was=False):
    """the program NAME; the workshop's variants look at the lanterns once a
    frame, LAMPS_FRAME, or leave was as it is at the title, KEEP_WAS"""
    frames = name == "frames"
    stt = gen46.STATES_RT
    stt = stt[stt.index("; setup:"):]
    assert stt.startswith("; setup:")
    parts = (gen46.ISR + gen46.HUSH + gen45.INPUT + gen45.KEYS + gen46.gen35.JOY + gen46.SENDS +
             gen45.PAGE + gen45.PRESSES + gen44.PACED + WALK + gen46.gen39.CELL + gen44.WALLED +
             gen45.LEAVE + gen45.UNPACK + FLIP_RT + gen46.GUARD_RT + gen46.LAMP_RT + gen46.CLOCK +
             play_rt(frames, lamps_frame) + PAD + HIT_ETC + END_RT + gen45.MINI + gen45.MAP_RT +
             (TITLE_RT.replace(WAS_LINE, "") if keep_was else TITLE_RT) +
             UNROW + DRAW_RT + "\n" + SETUP + SET2K + gen46.POST + gen46.POST2 + gen46.ADDTEN +
             gen44.FX + gen46.gen40.BEST + gen46.gen40.ADDSC + gen46.gen42.PUTBCD +
             gen46.gen38.HERE_OWN + gen46.gen38.PAGE2 + gen46.gen38.SUBREG + gen46.engine_parts())
    body = setup_lines() + gen45.MAIN
    src = (HEAD.format(name=name, what=WHAT[name]) + '        INCLUDE "bios.inc"\n' + RAM +
           "SSLOT   EQU $FFFF               ; the secondary slot register, in page 3\n" + CONSTS +
           gen37.fields() + gen46.IM2 + SAY[name] + tidy(body + parts) + data() + gen37.ENGINE_INC +
           "        ASSERT $ <= $8000, the first half is too long\n"
           "        ds $8000 - $, $FF       ; the first half ends at $7FFF\n" + gen46.second_half() +
           "romend:                         ; the cartridge's last byte, and one\n"
           "        ASSERT low rooms == 0 && rooms == $8000\n"
           "        ASSERT low ltab == 0 && low gtab == 0\n"
           "        ASSERT high (piccol + 31) == high piccol\n"
           "        ASSERT $ <= $C000, the program is longer than the cartridge\n"
           "        ds $C000 - $, $FF       ; the rest of the second half\n")
    return src


def music_inc():
    text = gen46.music_inc()
    old = ("; music.inc -- chapter 46: the title's tune, chapter 37's instruments and\n"
           "; chapter 44's, and the game's four sounds; generated by gen46.py\n")
    assert text.startswith(old)
    return ("; music.inc -- chapter 54: chapter 46's tune, chapter 37's instruments and\n"
            "; chapter 44's, and the game's four sounds; generated by gen54.py\n") + text[len(old):]


def main():
    with open(os.path.join(HERE, "music.inc"), "w") as f:
        f.write(music_inc())
    for name in PROGRAMS:
        with open(os.path.join(HERE, f"{name}.asm"), "w") as f:
            f.write(program(name))
    print("music.inc " + " ".join(f"{n}.asm" for n in PROGRAMS))


if __name__ == "__main__":
    main()
