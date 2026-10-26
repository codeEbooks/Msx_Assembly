#!/usr/bin/env python3
"""gen48.py - the programs of chapter 48: MegaROMs.

    python3 gen48.py && ./build.sh

    long.asm    THE LONG CAVE: chapter 47's cave, its world in seven banks of
                an ASCII16 cartridge of 128 KB. Bank 0, at $4000 from INIT on,
                holds the code; each of banks 1 to 7, shown at $8000 when it
                is needed, holds a stretch of the world, five segments of 224
                columns, with its own rock, its own colours, its own pairs
                and the routine that sends them, bshow, at the same address
                in every bank. window maps the bank of the window it writes;
                sends maps the bank of the window shown before it calls
                bshow. The bank of page 2 is written at $77FF, an address
                openMSX counts for ASCII16 alone when it guesses the type
    far.asm     WHERE IT BREAKS: long.asm with sends calling bshow without
                mapping the bank of the window shown: for seven frames at the
                end of each bank, the next bank's routine runs
    guess.asm   long.asm with the bank written at $7000, inside the same
                register's range: openMSX takes the cartridge for a Konami
                SCC one, whose register at $7000 maps $6000-$7FFF
    banks.asm   the mappers measured: a cartridge of 128 KB, each 8 KB block
                with its number in its last byte; a program copied to the RAM
                writes to the addresses mappers listen at and reads, after
                each write, which block each 8 KB window of pages 1 and 2
                shows. Run with -romtype ascii16, ascii8, konami and
                konamiscc

Every cartridge is one source: each bank after the first is a new OUTPUT
of the same file, in append mode, at ORG $8000, filled to its end with ds;
banks.asm's program is assembled with DISP for the RAM it runs in. The
frame is chapter 47's, and so are the ship, the demo, pad, steer and the
pairs (chapter 29). Every line of this chapter's own routines carries its
price, the MSX's T-states. build.sh assembles with --syntax=bFw.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
for ch in ("tools", "ch38", "ch41", "ch47"):
    sys.path.insert(0, os.path.join(REPO, ch))
import gen47  # noqa: E402  (chapter 47: the cave, the frame, pad, the ship)
import gen38  # noqa: E402  (chapter 38: here, setpage2, subreg)
import gen41  # noqa: E402  (chapter 41: xorshift)
from gen47 import tidy, db_rows, big  # noqa: E402
sys.path.insert(0, HERE)

EU, JP = gen47.EU, gen47.JP
MACHINES = [EU, JP]
FRAMES = 600
BLACK, MEDIUM_GREEN, LIGHT_BLUE, MEDIUM_RED, MAGENTA, WHITE = 1, 2, 5, 8, 13, 15
BIOS = gen47.BIOS

# ================================================================ the world
BANKS = 7                   # banks 1 to 7 hold the world
SEGS = 5                    # segments a bank
SEGW = 224                  # columns a segment: seven screens
COLS = BANKS * SEGS * SEGW  # the world's columns, round
KNOT = gen47.KNOT
CEIL_ROWS, GROUND_ROWS = gen47.CEIL_ROWS, gen47.GROUND_ROWS
SCROLL_ROWS = gen47.SCROLL_ROWS
CEIL_H, GROUND_H = gen47.CEIL_H, gen47.GROUND_H
CAVE_SEED = gen47.CAVE_SEED
START = (1, 4, 200)         # the first window: bank 1's last segment, column 200
PMAP_AT = 0x8000            # each bank's segments: 11 pages each, from $8000
BSHOW_AT = 0xB700           # and its routine, the same in every bank
BANK2 = 0x77FF              # where page 2's bank is written (ASCII16: $7000-$77FF)
BANK2_GUESS = 0x7000        # guess.asm's
SKY_C = BLACK << 4 | BLACK

_ck, _x = gen47.knots(CAVE_SEED, COLS // KNOT, *CEIL_H)
_gk, _x = gen47.knots(_x, COLS // KNOT, *GROUND_H)
CEIL = gen47.edges(_ck)
GROUND = gen47.edges(_gk)


def col_of(bank, seg, off):
    """the world's column of a window's place"""
    return ((bank - 1) * SEGS + seg) * SEGW + off


def place_of(col):
    """a world's column -> (bank, segment, column in the segment)"""
    col %= COLS
    return col // (SEGS * SEGW) + 1, col // SEGW % SEGS, col % SEGW


def kind(r, c):
    """the kind of tile at row R, column C of the world, as chapter 47's"""
    if CEIL_ROWS[0] <= r <= CEIL_ROWS[1]:
        a, b = CEIL[c % COLS], CEIL[(c + 1) % COLS]
        if a == b:
            return "rc" if r < a else "bc" if r == a else "sc"
        if b == a + 1:
            return "rc" if r <= a else "dc" if r == a + 1 else "sc"
        return "rc" if r < a else "uc" if r == a else "sc"
    if GROUND_ROWS[0] <= r <= GROUND_ROWS[1]:
        a, b = GROUND[c % COLS], GROUND[(c + 1) % COLS]
        if a == b:
            return "sg" if r < a else "tg" if r == a else "rg"
        if b == a - 1:
            return "sg" if r < a - 1 else "ug" if r == a - 1 else "rg"
        return "sg" if r < a else "dg" if r == a else "rg"
    return None


R8 = gen47.rows8
ROCKS = [                   # each bank's rock: its texture, 8 x 8
    R8("########", "##.#####", "########", "######.#", "########", "#.######", "########",
       "####.###"),                                                     # 1: stones
    R8("########", "#.......", "#.......", "#.......", "########", "....#...", "....#...",
       "....#..."),                                                     # 2: bricks
    R8("#..##..#", "##..##..", ".##..##.", "..##..##", "#..##..#", "##..##..", ".##..##.",
       "..##..##"),                                                     # 3: slants
    R8("##..##..", "##..##..", "..##..##", "..##..##", "##..##..", "##..##..", "..##..##",
       "..##..##"),                                                     # 4: checks
    R8("........", ".##...##", "#..#.#..", "....#...", "........", ".##...##", "#..#.#..",
       "....#..."),                                                     # 5: waves
    R8("...#....", "...#....", ".#####..", "...#....", "...#....", "........", "........",
       "........"),                                                     # 6: crosses
    R8("#.#.#.#.", "#.#.#.#.", "#.#.#.#.", "#.#.#.#.", "#.#.#.#.", "#.#.#.#.", "#.#.#.#.",
       "#.#.#.#."),                                                     # 7: bars
]
INKS = [(LIGHT_BLUE, MEDIUM_GREEN), (MEDIUM_RED, LIGHT_BLUE), (MAGENTA, MEDIUM_RED),
        (MEDIUM_GREEN, MAGENTA), (LIGHT_BLUE, MEDIUM_RED), (MAGENTA, MEDIUM_GREEN),
        (MEDIUM_RED, MAGENTA)]  # each bank's ceiling and ground: four colours of one grey


def tiles(bank):
    """bank's tiles: kind -> (shape, colour byte)"""
    rock = ROCKS[bank - 1]
    ci, gi = INKS[bank - 1]
    cc, gc = ci << 4 | BLACK, gi << 4 | BLACK
    return {"sc": ([0] * 8, cc), "rc": (rock, cc), "bc": (rock[:7] + [0xFF], cc),
            "dc": ([0xFF >> i for i in range(8)], cc),
            "uc": ([(0xFF << i) & 0xFF for i in range(8)], cc),
            "sg": ([0] * 8, gc), "rg": (rock, gc), "tg": ([0xFF] + rock[1:], gc),
            "ug": ([0xFF >> (7 - i) for i in range(8)], gc),
            "dg": ([(0xFF << (7 - i)) & 0xFF for i in range(8)], gc)}


SKIES = ("sc", "sg")


def bank_pairs(bank):
    """the pairs of bank's segments, in the order met, and for each segment
    and scrolling row the pair at each of SEGW + 31 columns: the window at
    the segment's last column reaches 31 more, the next segment's first"""
    pairs, pmap = [], []
    for seg in range(SEGS):
        c0 = col_of(bank, seg, 0)
        rows = []
        for r in SCROLL_ROWS:
            out = []
            for c in range(c0, c0 + SEGW + 31):
                p = (kind(r, c), kind(r, c + 1))
                if p[0] in SKIES and p[1] in SKIES:
                    out.append(0)
                    continue
                if p not in pairs:
                    pairs.append(p)
                out.append(pairs.index(p) + 1)
            rows.append(out)
        pmap.append(rows)
    return pairs, pmap


BANK_DATA = {b: bank_pairs(b) for b in range(1, BANKS + 1)}
NPS = {b: len(BANK_DATA[b][0]) for b in BANK_DATA}
assert max(NPS.values()) * 8 <= 255, NPS


def shifted(bank, a, b, s):
    t = tiles(bank)
    return [((ra << 8 | rb) << s >> 8) & 0xFF for ra, rb in zip(t[a][0], t[b][0])]


def pair_colours(bank, a, b):
    t = tiles(bank)
    assert t[a][1] == t[b][1]
    return [t[a][1]] * 8


def pixel(wx, y, bank):
    """1 if the world's pixel (WX, Y) is rock, with bank's tiles; and its ink"""
    k = kind(y >> 3, wx >> 3)
    if k is None:
        return 0, BLACK
    shape, c = tiles(bank)[k]
    return shape[y & 7] >> (7 - (wx & 7)) & 1, c >> 4


# ================================================================ the programs
RAM = gen47.RAM + """shift   EQU VARS + 9            ; the pixels on, 0 to 7
table   EQU VARS + 10           ; the name table shown: $18 or $1C
wbank   EQU VARS + 11           ; the next window to write: its bank,
wseg    EQU VARS + 12           ; its segment in the bank,
woff    EQU VARS + 13           ; and its column in the segment
pending EQU VARS + 14           ; the bank of the window last written
shown   EQU VARS + 15           ; the bank of the window shown
fresh   EQU VARS + 16           ; 1 when shown has just changed: its colours to send
SSLOT   EQU $FFFF               ; the secondary slot register, in page 3
"""


def consts(bank2):
    return f"""BANK2   EQU ${bank2:04X}             ; page 2's bank is written here (ASCII16)
BSHOW   EQU ${BSHOW_AT:04X}             ; every bank's bshow
PMAP    EQU ${PMAP_AT >> 8:02X}                 ; the first page of every bank's segments
SEGS    EQU {SEGS}                   ; segments a bank
SEGW    EQU {SEGW}                 ; columns a segment
BANKS   EQU {BANKS}                   ; banks of the world: 1 to 7
X_MIN   EQU {gen47.SHIP_X[0]}                  ; the ship's X
X_MAX   EQU {gen47.SHIP_X[1]}
Y_MIN   EQU {gen47.SHIP_Y[0] - 1}                  ; its Y, a line above its top
Y_MAX   EQU {gen47.SHIP_Y[1] - 1}
"""


SENDS = """
; sends: straight after HALT, before the paper: the ship's attributes; at a
;        turn, the bank of the window now shown; that bank in page 2, and its
;        bshow: its pairs at the new shift, and its colours if it is new; at a
;        turn, R#2 to the other table. Uses A, BC, HL
sends:  VRAM_WRITE SAT          ; 40
        ld hl, copy             ; 11
        ld bc, 5 << 8 | VDP_DATA ; 11  the ship and the end
        otir                    ; 23 a byte, 18 the last
        ld a, (shift)           ; 14
        or a                    ;  5
        jr nz, .pairs           ; 13, or 8
        ld hl, shown            ; 11  a turn: the bank shown is now
        ld a, (pending)         ; 14  the bank of the window written last
        cp (hl)                 ;  8
        ld (hl), a              ;  8
        ld a, 0                 ;  8  LD, not XOR: the flags are CP's
        jr z, .same             ; 13, or 8
        inc a                   ;  5  a new bank: its colours too
.same:  ld (fresh), a           ; 14
.pairs: ld a, (shown)           ; 14
        ld (BANK2), a           ; 14  page 2 shows the bank of the window shown
        call BSHOW              ; 18  and its routine sends its pairs
        ld a, (shift)           ; 14
        or a                    ;  5
        ret nz                  ; 12, or 6  seven frames in eight, no more
        ld a, (table)           ; 14
        xor $18 ^ $1C           ;  8  the other table: the next window
        ld (table), a           ; 14
        rrca                    ;  5
        rrca                    ;  5  $06 or $07, R#2's
        out (VDP_CTRL), a       ; 12
        ld a, $80 | 2           ;  8
        out (VDP_CTRL), a       ; 12
        ret                     ; 11
"""

_steer = gen47.CAVE_RUN[gen47.CAVE_RUN.index("; steer:"):gen47.CAVE_RUN.index("; step:")]

RUN = """
; run: the frame's work: the demo's keys, the ship steered, the scroll.
;      Uses every register
run:    call pad                ; 18  A: the keys
        call steer              ; 18
                                ;     on into step

; step: after a turn, the next window's names into the other table; then a
;       pixel on. Uses every register
step:   ld a, (shift)           ; 14
        or a                    ;  5
        call z, window          ; 18, or 11
.on:    ld a, (shift)           ; 14
        inc a                   ;  5
        and 7                   ;  8
        ld (shift), a           ; 14
        ret                     ; 11

""" + _steer + """
; window: the next window, its bank wbank, its segment wseg, its column woff,
;         into the name table not shown: its bank in page 2, then rows 1 to
;         4 and 17 to 23, each row's pairs in a page of the segment's 11; then
;         the place of the window after it. Uses A, BC, DE, HL
window: ld a, (wbank)           ; 14
        ld (pending), a         ; 14  the bank of the window written
        ld (BANK2), a           ; 14  page 2 shows it
        ld a, (wseg)            ; 14
        ld b, a                 ;  5
        add a, a                ;  5
        ld c, a                 ;  5  2 x the segment
        add a, a                ;  5
        add a, a                ;  5
        add a, c                ;  5
        add a, b                ;  5  11 x the segment
        add a, PMAP             ;  8
        ld h, a                 ;  5  its first page
        ld a, (woff)            ; 14
        ld e, a                 ;  5  E: the column
        ld l, a                 ;  5  HL: row 1's pair there
        ld a, (table)           ; 14
        xor $18 ^ $1C           ;  8  the table not shown
        ld d, a                 ;  5  D: its high byte
        ld a, 32                ;  8
        out (VDP_CTRL), a       ; 12
        ld a, d                 ;  5
        or $40                  ;  8
        out (VDP_CTRL), a       ; 12  its row 1, for writing
        ld c, 4                 ;  8  four rows
        call names              ; 18
        ld a, low (32 * 17)     ;  8
        out (VDP_CTRL), a       ; 12
        ld a, d                 ;  5
        or high (32 * 17) | $40 ;  8
        out (VDP_CTRL), a       ; 12  its row 17
        ld c, 7                 ;  8  seven rows
        call names              ; 18
        ld hl, woff             ; 11  the next window: a column on,
        inc (hl)                ; 12
        ld a, (hl)              ;  8
        cp SEGW                 ;  8
        ret c                   ; 12, or 6
        ld (hl), 0              ; 11  or the next segment's first,
        ld hl, wseg             ; 11
        inc (hl)                ; 12
        ld a, (hl)              ;  8
        cp SEGS                 ;  8
        ret c                   ; 12, or 6
        ld (hl), 0              ; 11  or the next bank's,
        ld hl, wbank            ; 11
        inc (hl)                ; 12
        ld a, (hl)              ;  8
        cp BANKS + 1            ;  8
        ret c                   ; 12, or 6
        ld (hl), 1              ; 11  or, past bank 7, bank 1's again
        ret                     ; 11

; names: HL = a row's pair at the column E, C = rows -> C rows of 32 names,
;        one after another in the VRAM, 39 T-states a name. Uses A, BC, HL
names:  ld b, 32                ;  8
.name:  ld a, (hl)              ;  8
        out (VDP_DATA), a       ; 12
        inc l                   ;  5
        djnz .name              ; 14, or 9
        inc h                   ;  5  the next row's page
        ld l, e                 ;  5
        dec c                   ;  5
        jr nz, names            ; 13, or 8
        ret                     ; 11
"""


def bshow_text(bank):
    nb = 8 * NPS[bank]
    return f"""
; bshow, bank {bank}'s: its pairs at the shift, {NPS[bank]} patterns from 1, with OTIR;
; and when fresh says the bank is new, their colours. Uses A, BC, HL
bshow{bank}: VRAM_WRITE $0008        ; 40  pair 1's pattern, the first
        ld a, (shift)           ; 14
        add a, a                ;  5  two bytes a shift
        add a, low stab{bank}       ;  8
        ld l, a                 ;  5
        ld h, high stab{bank}       ;  8  HL: the shift's place in stab
        ld a, (hl)              ;  8
        inc l                   ;  5
        ld h, (hl)              ;  8
        ld l, a                 ;  5  HL: the pairs at this shift
        ld bc, {nb} << 8 | VDP_DATA ; 11
        otir                    ; 23 a byte, 18 the last
        ld a, (fresh)           ; 14
        or a                    ;  5
        ret z                   ; 12, or 6  the same bank as before
        xor a                   ;  5
        ld (fresh), a           ; 14  sent once
        VRAM_WRITE $2008        ; 40  pair 1's colours
        ld hl, pcols{bank}          ; 11
        ld b, {nb}                ;  8
        otir                    ; 23 a byte, 18 the last
        ret                     ; 11
"""


def bank_source(bank, name):
    """the source of bank BANK: its segments' pages from $8000, its bshow at
    BSHOW, its pairs and their colours"""
    pairs, pmap = BANK_DATA[bank]
    nb = 8 * len(pairs)
    shp = [b for s in range(8) for a, b2 in pairs for b in shifted(bank, a, b2, s)]
    cols = [b for a, b2 in pairs for b in pair_colours(bank, a, b2)]
    out = [f"""
; ================================================================ bank {bank}
        OUTEND
        OUTPUT "{name}.rom", a  ; bank {bank}, seen at $8000 when page 2 shows it
        ORG $8000
"""]
    for seg in range(SEGS):
        c0 = col_of(bank, seg, 0)
        for i, r in enumerate(SCROLL_ROWS):
            out.append(f"seg{bank}_{seg}_{r}:".ljust(32) +
                       f"; segment {seg}, columns {c0}-{c0 + SEGW - 1}, row {r}\n" if i == 0 else "")
            out.append(f"        ; row {r}\n" if i else "")
            out.append(db_rows(pmap[seg][i] + [0] * (256 - len(pmap[seg][i])), 16))
    out.append("""        ASSERT $ == BSHOW, the segments must end where bshow starts
""")
    out.append(tidy(bshow_text(bank)))
    out.append(f"""        ALIGN 16
stab{bank}:                          ; where each shift's patterns start
""" + "".join(f"        dw shifts{bank} + {s * nb}\n" for s in range(8)) +
               f"pcols{bank}:                         ; the {len(pairs)} pairs' colours\n" + db_rows(cols, 16) +
               f"shifts{bank}:                        ; the {len(pairs)} pairs at shifts 0 to 7, {nb} bytes each\n" +
               db_rows(shp, 16) + """        ASSERT $ <= $C000, the bank is longer than 16 KB
        ds $C000 - $, $FF
""")
    return "".join(out)


def setup(bank2, start=START):
    b, s, o = start
    return gen47.start_lines(gen47.GRAPHIC2_ONE, gen47.CAVE_BORDER) + f"""        call here               ; page 1's slot: the cartridge
        call setpage2           ; page 2 shows it too
        VRAM_WRITE $0000        ; pattern 0, the sky
        ld c, VDP_DATA
        xor a
        ld b, 8
.sky:   out (c), a
        djnz .sky
        VRAM_WRITE $2000        ; and its colours
        ld a, ${SKY_C:02X}
        ld b, 8
.skyc:  out (c), a
        djnz .skyc
        VRAM_WRITE $1800        ; both name tables all sky
        call sky
        VRAM_WRITE $1C00
        call sky
; the first two windows, the bank shown, and its pairs
        ld a, {b}
        ld (wbank), a           ; the first window's place
        ld a, {s}
        ld (wseg), a
        ld a, {o}
        ld (woff), a
        ld a, $1C
        ld (table), a
        call window             ; the first, into the table not shown: $1800
        ld a, (pending)
        ld (shown), a           ; its bank, shown
        ld a, $18
        ld (table), a
        call window             ; the second, into $1C00: $1800 will be shown
        ld a, 1
        ld (fresh), a           ; the shown bank's colours, and its pairs
        ld a, (shown)
        ld (BANK2), a
        call BSHOW              ; at shift 0
        ld a, 1
        ld (shift), a           ; the first frame: a pixel on
        VRAM_WRITE SPAT         ; the ship's patterns
        ld hl, sprite
        ld bc, 32 << 8 | VDP_DATA
        otir
        jp on

; sky: 768 names of the sky, 0, to the VRAM, with the display off
sky:    ld de, 768
.name:  xor a
        out (VDP_DATA), a
        dec de
        ld a, d
        or e
        jr nz, .name
        ret
on:
""" + gen47.end_lines(0xE2)


def bank0_data():
    return ("first:                          ; the ship's attributes at the start, and the end\n" +
            db_rows([gen47.CAVE_Y0 - 1, gen47.SHIP_AT[0], 0, gen47.SHIP_COLOUR, 0xD0]) +
            "sprite:                         ; the ship, 16 x 16 (chapter 26)\n" + db_rows(big(gen47.SHIP)) +
            gen47.demo_data(gen47.CAVE_DEMO, "chapter 47's flight"))


WHAT = {"long": "the long cave", "far": "a routine in a bank switched off",
        "guess": "a cartridge openMSX takes for another",
        "round": "the long cave from bank 7", "once": "page 2 mapped at a turn only"}
SAY = {"long": """; THE LONG CAVE: chapter 47's cave in an ASCII16 cartridge of 128 KB. Bank 0, at
; $4000, holds the code; banks 1 to 7 the world, 7,840 columns, each bank a
; stretch of it with its own rock and colours, its pairs and bshow, the
; routine that sends them. Page 2's bank is written at $77FF.
""",
       "far": """; WHERE IT BREAKS. long.asm with sends calling bshow without mapping the bank
; of the window shown: the bank in page 2 is the one window last mapped.
""",
       "guess": """; long.asm with page 2's bank written at $7000, inside the ASCII16 register's
; range: openMSX guesses Konami SCC, whose register at $7000 maps $6000-$7FFF.
""",
       "round": """; The workshop: long.asm starting in bank 7's last segment.
""",
       "once": """; The workshop: far.asm put right with less: sends maps page 2 at a turn only,
; and window gives page 2 back to the bank shown when it has written.
"""}

ONCE_SENDS = (("""        ld (hl), a              ;  8
        ld a, 0                 ;  8  LD, not XOR: the flags are CP's
""", """        ld (hl), a              ;  8
        ld (BANK2), a           ; 14  a turn: page 2 shows the bank now shown
        ld a, 0                 ;  8  LD, not XOR: the flags are CP's
"""), (""".pairs: ld a, (shown)           ; 14
        ld (BANK2), a           ; 14  page 2 shows the bank of the window shown
        call BSHOW              ; 18  and its routine sends its pairs
""", """.pairs: call BSHOW              ; 18  the routine of the bank shown
"""))
ONCE_RUN = (("""        ld c, 7                 ;  8  seven rows
        call names              ; 18
""", """        ld c, 7                 ;  8  seven rows
        call names              ; 18
        ld a, (shown)           ; 14
        ld (BANK2), a           ; 14  page 2 back to the bank shown
"""),)


def patched(text, pairs):
    for old, new in pairs:
        assert text.count(old) == 1, old
        text = text.replace(old, new)
    return text


def program(name="long", start=START):
    bank2 = BANK2_GUESS if name == "guess" else BANK2
    head = gen47.HEAD.format(name=name, chapter=48, what=WHAT[name]) + BIOS
    sends, run = SENDS, RUN
    if name == "once":
        sends, run = patched(SENDS, ONCE_SENDS), patched(RUN, ONCE_RUN)
    if name == "far":
        old = """.pairs: ld a, (shown)           ; 14
        ld (BANK2), a           ; 14  page 2 shows the bank of the window shown
        call BSHOW              ; 18  and its routine sends its pairs
"""
        assert sends.count(old) == 1
        sends = sends.replace(old, """.pairs: call BSHOW              ; 18  the routine of the bank in page 2
""")
    code = tidy(setup(bank2, start) + gen47.MAIN + gen47.gen43.ISR + gen47.PAD + sends + run +
                gen38.HERE_OWN + gen38.PAGE2 + gen38.SUBREG)
    src = (head + RAM + consts(bank2) + gen47.IM2 + SAY[name] + code + bank0_data() +
           """        ASSERT $ <= $8000, bank 0 is longer than 16 KB
        ds $8000 - $, $FF
""")
    for b in range(1, BANKS + 1):
        src += bank_source(b, name)
    return src


# ================================================================ banks.asm
RUN_AT = 0xC100             # where banks.asm's program runs
RESULTS_AT = 0xC400         # and where it keeps what it read
PROBE_WRITES = [(0x6000, 3), (0x6800, 4), (0x7000, 5), (0x77FF, 6), (0x7800, 7),
                (0x77FF, 9), (0x77FF, 0xFF),
                (0x5000, 9), (0x9000, 10), (0xB000, 11), (0x8000, 12), (0xA000, 13)]
MARKS = [0x5FFF, 0x7FFF, 0x9FFF, 0xBFFF]    # the last byte of each 8 KB window


def banks_program():
    tests = "".join(f"        dw ${a:04X}\n        db {v}\n" for a, v in PROBE_WRITES)
    marks = "".join(f"        ld a, (${m:04X})\n        ld (hl), a\n        inc hl\n" for m in MARKS)
    src = gen47.HEAD.format(name="banks", chapter=48, what="the mappers measured") + BIOS + f"""SSLOT   EQU $FFFF               ; the secondary slot register, in page 3
RUN_AT  EQU ${RUN_AT:04X}               ; where the program runs
RESULTS EQU ${RESULTS_AT:04X}               ; 4 bytes a write, and 4 before any
; The mappers measured: each 8 KB block of this cartridge holds its number
; in its last byte. The program, copied to the RAM, reads the four 8 KB
; windows of pages 1 and 2 at the start, then after each write of a list.
""" + tidy(f"""init:   di
        ld sp, SYS_AREA
        call here               ; page 1's slot: the cartridge
        call setpage2           ; page 2 shows it too
        ld hl, probe            ; the program into the RAM
        ld de, RUN_AT
        ld bc, probe_end - probe
        ldir
        jp RUN_AT
""") + tidy(gen38.HERE_OWN + gen38.PAGE2 + gen38.SUBREG) + f"""
probe:                          ; assembled for the RAM it runs in
        DISP RUN_AT
""" + tidy(f"""run:    ld hl, RESULTS
        call look               ; the windows before any write
        ld ix, tests
        ld b, {len(PROBE_WRITES)}
.test:  ld e, (ix+0)
        ld d, (ix+1)            ; DE: the address
        ld a, (ix+2)            ; A: the value
        ld (de), a              ; written
        call look               ; and the windows after it
        inc ix
        inc ix
        inc ix
        djnz .test
done:   jr done

; look: the block each 8 KB of pages 1 and 2 shows, read at its last byte, to HL
look:
{marks}        ret
tests:
{tests}""") + """        ENT
probe_end:
        ASSERT $ <= $5FFF, the program must leave block 0's last byte
        ds $5FFF - $, $FF
        db 0                    ; block 0's number
        ds $7FFF - $, $FF
        db 1                    ; block 1's
"""
    for blk in range(2, 16, 2):
        src += f"""        OUTEND
        OUTPUT "banks.rom", a   ; blocks {blk} and {blk + 1}
        ORG $8000
        ds $9FFF - $, $FF
        db {blk}
        ds $BFFF - $, $FF
        db {blk + 1}
"""
    return src


def variant(kind):
    """the workshop's programs: (name, source)"""
    if kind == "round":
        return "round", program("round", start=(BANKS, SEGS - 1, START[2]))
    return kind, program(kind)


PROGRAMS = {"long": lambda: program("long"), "far": lambda: program("far"),
            "guess": lambda: program("guess"), "banks": banks_program}


def main():
    for name, make in PROGRAMS.items():
        with open(os.path.join(HERE, f"{name}.asm"), "w") as f:
            f.write(make())
    print(" ".join(f"{n}.asm" for n in PROGRAMS), "pairs", NPS, "columns", COLS)


if __name__ == "__main__":
    main()
