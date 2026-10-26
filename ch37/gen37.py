#!/usr/bin/env python3
"""gen37.py - the programs of chapter 37: a sound engine in the interrupt.

    python3 gen37.py && ./build.sh

    tune.asm     the book's tune, from patterns, played by the interrupt;
                 the main program prints the bar, the row, the ticks and the
                 three levels (figure 37.1)
    effects.asm  the same, and ten requests for the four effects, made by
                 the main program at ticks set in advance: taken, refused,
                 started again, or put over a lower one (figure 37.3)
    fast.asm     tune.asm with the player ticked in every frame, at 60 Hz
                 too: the tune a sixth faster
    sixth.asm    tune.asm with one frame in six left out at 60 Hz
    latch.asm    WHERE IT BREAKS: tune.asm, and a main program that reads
                 joystick 1 again and again with the interrupts on (figure
                 37.5)

The interrupt routine is the same in all of them: pace says whether the
player ticks in this frame, and when it does, tochip writes R0 to R10 from
shadow, last tick's, and play works out the next. The music is in music.inc,
written here from music37.py. The programs take the interrupt in mode 2
(chapter 17), print in Graphic I, black ink on white, end with
asmparts.CART_END, and build.sh assembles them with --syntax=bFw.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "tools"))
sys.path.insert(0, os.path.join(REPO, "ch34"))
sys.path.insert(0, os.path.join(REPO, "ch35"))
sys.path.insert(0, os.path.join(REPO, "ch33"))
from asmparts import HEAD, CART_END, IM2, im2, BOX_EMPTY, BOX_FULL  # noqa: E402
import gen34  # noqa: E402  (chapter 34: the text screen and its routines)
import gen35  # noqa: E402  (chapter 35: joy, show)
import gen33  # noqa: E402  (chapter 33: rate)
from gen26 import tidy, db_rows  # noqa: E402  (chapter 26)
sys.path.insert(0, HERE)
import music37 as m  # noqa: E402

EU, JP = "MSXBOOK_EU16", "MSXBOOK_JP16"
TEXT_REGS = gen34.TEXT_REGS
LINES = {EU: 313, JP: 262}      # lines a frame (chapter 18), 228 T-states each
MIXER_OFF = 0xBF                # R7: every tone and noise shut; port A in, B out
SHADOW_REGS = 11                # R0 to R10

# ------------------------------------------------------------------ the RAM
FIELDS = [("WAITS", 1, "rows to wait; an effect: ticks to sound"),
          ("NOTE", 1, "the note, 0 for a rest"),
          ("INSTR", 1, "the instrument"),
          ("PATTERN", 2, "the next event"),
          ("VOLUME", 2, "this tick's level in the volume table"),
          ("PITCHES", 2, "this tick's semitones"),
          ("FIRST", 2, "the pitch table's first byte"),
          ("MIXER", 1, "the instrument's TONE and NOISE"),
          ("NOISEP", 1, "its noise's period"),
          ("SHPER", 2, "where in shadow its period goes"),
          ("SHLEV", 2, "and its level"),
          ("TMASK", 1, "R7 with its tone bit at 0"),
          ("NMASK", 1, "R7 with its noise bit at 0"),
          ("PRIO", 1, "an effect's priority")]
OFFSET = {}
_at = 0
for _name, _n, _ in FIELDS:
    OFFSET[_name] = _at
    _at += _n
CHAN = _at                      # bytes a channel


def fields():
    out = []
    for name, n, say in FIELDS:
        out.append(f"{name:<8}EQU {OFFSET[name]:<20}; {say}")
    out.append(f"{'CHAN':<8}EQU {CHAN:<20}; bytes a channel")
    return "\n".join(out) + "\n"


SHADOW_AT = 0x20
RAM = f"""ticks   EQU VARS                ; the player's ticks, two bytes
owed    EQU VARS + 2            ; lines owed to the player, two bytes
lines   EQU VARS + 4            ; the machine's lines a frame: 313 or 262
tick    EQU VARS + 6            ; ticks still to the next row
step    EQU VARS + 7            ; the song's step, two bytes
barno   EQU VARS + 9            ; the step's number, 1 to {m.BARS}
rowno   EQU VARS + 10           ; the row in the bar, 0 to {m.ROWS - 1}
frames  EQU VARS + 11           ; frames counted by isr
skip    EQU VARS + 12           ; sixth.asm: frames to the next one left out
seen    EQU VARS + 13           ; latch.asm: the frame read in
port1   EQU VARS + 14           ; latch.asm: register 14 of port 1
nextrq  EQU VARS + 15           ; effects.asm: the next request, two bytes
saidp   EQU VARS + 17           ; and where its answer goes, two bytes
said    EQU VARS + 19           ; the answers: 0 taken, $FF refused
shadow  EQU VARS + ${SHADOW_AT:02X}          ; R0 to R10, as the next tick sends them
chan_a  EQU shadow + {SHADOW_REGS}         ; the channels, CHAN bytes each
chan_b  EQU chan_a + CHAN
chan_c  EQU chan_b + CHAN
chan_x  EQU chan_c + CHAN       ; the effect: a fourth channel, on C's registers
"""
VARS_AT = 0xC100
SAID_AT = 19
assert SHADOW_AT + SHADOW_REGS + 4 * CHAN <= 0x100      # all in VARS's page, below the IM 2 table


def shadow_template():
    return [0] * 7 + [MIXER_OFF] + [0] * 3


CHANNELS = [  # (shadow's period, shadow's level, tone bit, noise bit)
    (0, 8, 0, 3), (2, 9, 1, 4), (4, 10, 2, 5), (4, 10, 2, 5)]


def start_data():
    """shadow and the four channels as INIT copies them into the RAM"""
    out = ["start:                          ; shadow, the channels A, B and C, the effect",
           "        db " + ", ".join(f"${b:02X}" for b in shadow_template())]
    for k, (per, lev, tb, nb) in enumerate(CHANNELS):
        waits = 0 if k == 3 else 1
        pattern = "started" if k < 3 else "0"
        tm, nm = 255 & ~(1 << tb), 255 & ~(1 << nb)
        out.append(f"        db {waits}, 0, 0              ; {'ABCX'[k]}: WAITS, NOTE, INSTR")
        out.append(f"        dw {pattern}, 0, 0, 0     ; PATTERN, VOLUME, PITCHES, FIRST")
        out.append("        db 0, 0                 ; MIXER, NOISEP")
        out.append(f"        dw shadow + {per}, shadow + {lev} ; SHPER, SHLEV")
        out.append(f"        db ${tm:02X}, ${nm:02X}, 0          ; TMASK, NMASK, PRIO")
    out.append(f"started: db END                 ; a pattern's end: the first row reads the song")
    return "\n".join(out) + "\n"


START_BYTES = SHADOW_REGS + 4 * CHAN

# ------------------------------------------------------------------ the parts
ISR = """
; isr: every frame. When pace gives the player a tick, last tick's
; registers are sent first, so that every tick's writes land at the same
; T-states after the interrupt, and the next tick is worked out after.
; Keeps every register it uses
isr:    push af                 ; 12
        push bc                 ; 12
        push de                 ; 12
        push hl                 ; 12
        push ix                 ; 17
        in a, (VDP_CTRL)        ; 12  the status: the signal down
        ld hl, frames           ; 11
        inc (hl)                ; 12
        call pace               ; 18  carry: the player's tick
        jr nc, .done            ; 13, or 8
        call tochip             ; 18
        call play               ; 18
.done:  pop ix                  ; 16
        pop hl                  ; 11
        pop de                  ; 11
        pop bc                  ; 11
        pop af                  ; 11
        ei                      ;  5
        ret                     ; 11
"""

PACE = """
; pace: carry if the player ticks in this frame. Its ticks are 313 lines
; apart, a frame of the 50 Hz machine: each frame adds its own lines to
; owed, and a tick pays 313 of them back. Uses DE, HL
pace:   ld hl, (owed)           ; 17
        ld de, (lines)          ; 22  313 or 262, from INIT
        add hl, de              ; 12
        ld de, -313             ; 11
        add hl, de              ; 12  carry: 313 lines are owed
        jr c, .paid             ; 13, or 8
        sbc hl, de              ; 17  not yet: the 313 given back, no carry
.paid:  ld (owed), hl           ; 17
        ret                     ; 11
"""

PACE_FAST = """
; pace: fast.asm's: a tick in every frame, 50 or 60 a second
pace:   scf                     ;  5
        ret                     ; 11
"""

PACE_SIXTH = """
; pace: sixth.asm's: at 60 Hz one frame in six left out, none at 50 Hz.
; skip is the frames to the next one left out, 0 on a 50 Hz machine. Uses A
pace:   ld a, (skip)            ; 14
        or a                    ;  5
        scf                     ;  5
        ret z                   ; 12, or 6  50 Hz: every frame
        dec a                   ;  5
        ld (skip), a            ; 14
        scf                     ;  5
        ret nz                  ; 12, or 6
        ld a, 6                 ;  8  the sixth: left out
        ld (skip), a            ; 14
        or a                    ;  5  no carry
        ret                     ; 11
"""

SEND = f"""
; tochip: R0 to R{SHADOW_REGS - 1} from shadow, in order. Uses A, BC, HL
tochip: ld hl, shadow           ; 11
        ld bc, {SHADOW_REGS} << 8 | PSG_WRITE ; 11  B: the registers; C: the port
        xor a                   ;  5  R0 first
.reg:   out (PSG_ADDR), a       ; 12  the register
        inc a                   ;  5
        outi                    ; 18  its byte; HL on, and B down
        jr nz, .reg             ; 13, or 8
        ret                     ; 11
"""

PLAY = f"""
; play: the next tick into shadow: every SPEED ticks a row of each channel,
; then each channel's level, period and mixer bits, and an effect, if one
; is sounding, over channel C. Uses A, BC, DE, HL, IX
play:   ld hl, (ticks)          ; 17  one tick more
        inc hl                  ;  7
        ld (ticks), hl          ; 17
        ld hl, tick             ; 11
        dec (hl)                ; 12
        jr nz, .sounds          ; 13, or 8
        ld (hl), SPEED          ; 11  a row
        ld hl, rowno            ; 11
        inc (hl)                ; 12  next sets it to 0 at a new bar
        ld ix, chan_a           ; 16
        call row                ; 18
        ld ix, chan_b           ; 16
        call row                ; 18
        ld ix, chan_c           ; 16
        call row                ; 18
.sounds: ld a, ${MIXER_OFF:02X}             ;  8  all shut; bit 7 at 1, bit 6 at 0
        ld (shadow + 7), a      ; 14
        ld ix, chan_a           ; 16
        call sound              ; 18
        ld ix, chan_b           ; 16
        call sound              ; 18
        ld ix, chan_c           ; 16
        call sound              ; 18
        ld ix, chan_x           ; 16  an effect?
        ld a, (ix + WAITS)      ; 21  its ticks still to sound
        or a                    ;  5
        ret z                   ; 12, or 6  none: channel C is the music's
        dec (ix + WAITS)        ; 25
        ld a, (shadow + 7)      ; 14  the music's tone and noise on C shut
        or %00100100            ;  8
        ld (shadow + 7), a      ; 14
        jp sound                ; 11  the effect's, whose RET is play's
"""

ROW = """
; row: IX = a channel -> a row: one less to wait, and at none, its pattern's
; next event, and its instrument's tables from their first byte. Uses A,
; BC, DE, HL
row:    dec (ix + WAITS)        ; 25
        ret nz                  ; 12, or 6
        ld l, (ix + PATTERN)    ; 21
        ld h, (ix + PATTERN + 1) ; 21
        ld a, (hl)              ;  8
        inc hl                  ;  7
        cp END                  ;  8  the pattern's end?
        jr nz, .event           ; 13, or 8
        call next               ; 18  the song's next step
        ld a, (hl)              ;  8
        inc hl                  ;  7
.event: bit 7, a                ; 10  an instrument first?
        jr z, .note             ; 13, or 8
        and $7F                 ;  8
        ld (ix + INSTR), a      ; 21
        ld a, (hl)              ;  8
        inc hl                  ;  7
.note:  ld (ix + NOTE), a       ; 21  0 for a rest
        ld a, (hl)              ;  8  the rows it lasts
        inc hl                  ;  7
        ld (ix + WAITS), a      ; 21
        ld (ix + PATTERN), l    ; 21
        ld (ix + PATTERN + 1), h ; 21
"""

VOICE = """
; voice: IX = a channel -> its instrument's two tables from their first
; byte, its mixer bits and its noise's period, from instruments, 6 bytes
; each. Leaves the carry clear. Uses A, DE, HL
voice:  ld a, (ix + INSTR)      ; 21
        ld l, a                 ;  5
        add a, a                ;  5
        add a, l                ;  5  three times
        add a, a                ;  5  six times
        ld l, a                 ;  5
        ld h, 0                 ;  8
        ld de, instruments      ; 11
        add hl, de              ; 12  no carry: the table is in the ROM
        ld a, (hl)              ;  8  the volume table
        ld (ix + VOLUME), a     ; 21
        inc hl                  ;  7
        ld a, (hl)              ;  8
        ld (ix + VOLUME + 1), a ; 21
        inc hl                  ;  7
        ld a, (hl)              ;  8  the pitch table
        ld (ix + PITCHES), a    ; 21
        ld (ix + FIRST), a      ; 21
        inc hl                  ;  7
        ld a, (hl)              ;  8
        ld (ix + PITCHES + 1), a ; 21
        ld (ix + FIRST + 1), a  ; 21
        inc hl                  ;  7
        ld a, (hl)              ;  8  the mixer's bits
        ld (ix + MIXER), a      ; 21
        inc hl                  ;  7
        ld a, (hl)              ;  8  the noise's period
        ld (ix + NOISEP), a     ; 21
        ret                     ; 11
"""

NEXT = f"""
; next: the song's next step, or its first after the last: each channel's
; new pattern, and IX's in HL; the bar counted, and its row 0. Uses A, BC,
; DE, HL
next:   ld hl, (step)           ; 17
        ld de, 6                ; 11
        add hl, de              ; 12
        ld a, (hl)              ;  8
        inc hl                  ;  7
        or (hl)                 ;  8  a word 0: the end
        dec hl                  ;  7
        ld a, (barno)           ; 14
        jr nz, .keep            ; 13, or 8
        ld hl, song             ; 11  the first step again
        xor a                   ;  5
.keep:  inc a                   ;  5
        ld (barno), a           ; 14
        ld (step), hl           ; 17
        xor a                   ;  5
        ld (rowno), a           ; 14
        ld de, chan_a + PATTERN ; 11
        ldi                     ; 18
        ldi                     ; 18
        ld de, chan_b + PATTERN ; 11
        ldi                     ; 18
        ldi                     ; 18
        ld de, chan_c + PATTERN ; 11
        ldi                     ; 18
        ldi                     ; 18
        ld l, (ix + PATTERN)    ; 21
        ld h, (ix + PATTERN + 1) ; 21
        ret                     ; 11
"""

SOUND = """
; sound: IX = a channel -> its level, and for a note its period, in
; shadow, its tables a tick on; its tone and noise opened in R7, and R6
; its noise's period. Uses A, BC, DE, HL
sound:  ld c, 0                 ;  8  a rest's level
        ld a, (ix + NOTE)       ; 21
        or a                    ;  5
        jr z, .level            ; 13, or 8
        ld l, (ix + VOLUME)     ; 21
        ld h, (ix + VOLUME + 1) ; 21
        ld a, (hl)              ;  8  this tick's level
        cp END                  ;  8  the table's end?
        jr nz, .vstep           ; 13, or 8
        dec hl                  ;  7  the last level again
        ld c, (hl)              ;  8
        jr .pitch               ; 13
.vstep: ld c, a                 ;  5
        inc hl                  ;  7
        ld (ix + VOLUME), l     ; 21
        ld (ix + VOLUME + 1), h ; 21
.pitch: ld l, (ix + PITCHES)    ; 21
        ld h, (ix + PITCHES + 1) ; 21
        ld a, (hl)              ;  8  this tick's semitones
        cp LOOP                 ;  8
        jr nz, .hold            ; 13, or 8
        ld l, (ix + FIRST)      ; 21  the first again
        ld h, (ix + FIRST + 1)  ; 21
        ld a, (hl)              ;  8
        jr .pstep               ; 13
.hold:  cp HOLD                 ;  8
        jr nz, .pstep           ; 13, or 8
        dec hl                  ;  7  the last again
        ld a, (hl)              ;  8
        jr .pnote               ; 13
.pstep: inc hl                  ;  7
        ld (ix + PITCHES), l    ; 21
        ld (ix + PITCHES + 1), h ; 21
.pnote: add a, (ix + NOTE)      ; 21  the note they move it to
        add a, a                ;  5
        ld l, a                 ;  5
        ld h, high notes        ;  8  its period, in a page of its own
        ld e, (hl)              ;  8
        inc l                   ;  5
        ld d, (hl)              ;  8
        ld l, (ix + SHPER)      ; 21
        ld h, (ix + SHPER + 1)  ; 21
        ld (hl), e              ;  8
        inc hl                  ;  7
        ld (hl), d              ;  8
.level: ld l, (ix + SHLEV)      ; 21
        ld h, (ix + SHLEV + 1)  ; 21
        ld (hl), c              ;  8
        ld b, (ix + MIXER)      ; 21
        ld a, (shadow + 7)      ; 14
        bit 0, b                ; 10  a tone?
        jr z, .noise            ; 13, or 8
        and (ix + TMASK)        ; 21
.noise: bit 1, b                ; 10  a noise?
        jr z, .mixer            ; 13, or 8
        and (ix + NMASK)        ; 21
        ld (shadow + 7), a      ; 14
        ld a, (ix + NOISEP)     ; 21
        ld (shadow + 6), a      ; 14
        ret                     ; 11
.mixer: ld (shadow + 7), a      ; 14
        ret                     ; 11
"""

SFX = """
; sfx: A = an effect -> it starts on channel C, unless the effect still
; sounding has a higher priority: then carry, and nothing changes. The
; interrupts must be off. Uses A, DE, HL, IX
sfx:    add a, a                ;  5
        add a, a                ;  5  4 bytes an effect
        ld e, a                 ;  5
        ld d, 0                 ;  8
        ld hl, effects          ; 11
        add hl, de              ; 12  its priority, instrument, note, ticks
        ld ix, chan_x           ; 16
        ld a, (ix + WAITS)      ; 21  an effect sounding?
        or a                    ;  5
        ld a, (hl)              ;  8  the new one's priority
        jr z, .take             ; 13, or 8  none
        cp (ix + PRIO)          ; 21
        ret c                   ; 12, or 6  lower: refused
.take:  ld (ix + PRIO), a       ; 21
        inc hl                  ;  7
        ld a, (hl)              ;  8  the instrument, $80 and its number
        and $7F                 ;  8
        ld (ix + INSTR), a      ; 21
        inc hl                  ;  7
        ld a, (hl)              ;  8
        ld (ix + NOTE), a       ; 21
        inc hl                  ;  7
        ld a, (hl)              ;  8
        ld (ix + WAITS), a      ; 21  the ticks it sounds
        jp voice                ; 11  its tables, and no carry
"""

REQUEST = """
; request: the next request, if its tick has come: the effect asked for
; with sfx, and its answer kept, 0 taken or $FF refused. Uses A, BC, DE,
; HL, IX
request: ld hl, (nextrq)        ; 17
        ld e, (hl)              ;  8
        inc hl                  ;  7
        ld d, (hl)              ;  8  its tick
        inc hl                  ;  7
        ld a, d                 ;  5
        and e                   ;  5
        inc a                   ;  5
        ret z                   ; 12, or 6  $FFFF: no more
        push hl                 ; 12
        ld hl, (ticks)          ; 17
        or a                    ;  5
        sbc hl, de              ; 17
        pop hl                  ; 11
        ret c                   ; 12, or 6  not yet
        ld a, (hl)              ;  8  the effect
        inc hl                  ;  7
        ld (nextrq), hl         ; 17
        call sfx                ; 18
        sbc a, a                ;  5  $FF if refused
        ld hl, (saidp)          ; 17
        ld (hl), a              ;  8
        inc hl                  ;  7
        ld (saidp), hl          ; 17
        ret                     ; 11
"""

# the screen: a title, the bar and row, the ticks, a meter for each channel
SCREEN = {"bar": (3, 0, 6), "row": (3, 10, 15), "tick": (4, 0, 6),
          "A": (6, 0, 3), "B": (7, 0, 3), "C": (8, 0, 3)}
LEVEL_COL = 19
FX_ROW, FX_COLS = 10, (0, 6, 10, 15)       # "fx", ticks left, "prio", priority
JOY_ROW, JOY_COL = 10, 6


def screen_texts(title, fx=False, joy=False):
    t = [(1, 0, title)]
    for key, (row, col, _) in SCREEN.items():
        t.append((row, col, key))
    if fx:
        t += [(FX_ROW, FX_COLS[0], "fx"), (FX_ROW, FX_COLS[2], "prio")]
    if joy:
        t += [(JOY_ROW, 0, "joy")]
    return t


PRINTS = """
; dec2: A, 0 to 99, as two decimal digits from the address set. Uses A, B, C
dec2:   ld c, -1                ;  8  the tens, counted
.tens:  inc c                   ;  5
        sub 10                  ;  8
        jr nc, .tens            ; 13, or 8
        add a, 10               ;  8  the ones
        ld b, a                 ;  5
        ld a, c                 ;  5
        call .digit             ; 18
        ld a, b                 ;  5
.digit: add a, '0'              ;  8
        out (VDP_DATA), a       ; 12
        ret                     ; 11

; meter: A = a level, 0 to 15 -> fifteen boxes from the address set, as
; many of them filled as the level. Uses A, B, C
meter:  ld c, a                 ;  5
        ld b, 15                ;  8
.cell:  ld a, {full}             ;  8  a filled box ...
        dec c                   ;  5
        jp p, .put              ; 11
        ld a, {empty}             ;  8  ... or, past the level, an empty one
.put:   out (VDP_DATA), a       ; 12
        djnz .cell              ; 14, or 9
        ret                     ; 11
""".format(full=BOX_FULL, empty=BOX_EMPTY)


def show_lines(fx=False, joy=False):
    b, r, t = SCREEN["bar"], SCREEN["row"], SCREEN["tick"]
    out = f"""
; show: the bar, the row and the ticks, and channel A's, B's and C's levels
; in shadow, as meters and as numbers. Uses A, B, C, D, E
show:   ld d, {b[0]}
        ld e, {b[2]}
        call at
        ld a, (barno)
        call dec2
        ld e, {r[2]}
        call at
        ld a, (rowno)
        call dec2
        ld d, {t[0]}
        ld e, {t[2]}
        call at
        ld a, (ticks + 1)
        call hex
        ld a, (ticks)
        call hex
"""
    for k, ch in enumerate("ABC"):
        row, _, col = SCREEN[ch]
        out += f"""        ld d, {row}
        ld e, {col}
        call at
        ld a, (shadow + {8 + k})
        call meter
        ld e, {LEVEL_COL}
        call at
        ld a, (shadow + {8 + k})
        call dec2
"""
    if fx:
        out += f"""        ld d, {FX_ROW}
        ld e, {FX_COLS[1]}
        call at
        ld a, (chan_x + WAITS)
        call dec2
        ld e, {FX_COLS[3]}
        call at
        ld a, (chan_x + PRIO)
        call dec2
"""
    if joy:
        out += gen35.show(JOY_ROW, JOY_COL, "port1", "keys")
    return out + "        ret\n"


def init_lines(pace="owed"):
    out = gen33.rate("lines", LINES[JP], LINES[EU])
    if pace == "sixth":
        out += """        ld a, ($002B)           ; and sixth.asm's count: 6 at 60 Hz, 0 at 50
        rla
        ld a, 6
        jr nc, .six
        xor a
.six:   ld (skip), a
"""
    out += f"""        ld hl, 0
        ld (owed), hl
        ld (ticks), hl
        ld a, 1                 ; the first tick reads a row
        ld (tick), a
        xor a
        ld (barno), a
        ld (rowno), a
        ld (frames), a
        ld hl, song - 6         ; the step before the first
        ld (step), hl
        ld hl, start            ; shadow and the four channels
        ld de, shadow
        ld bc, {START_BYTES}
        ldir
"""
    return out


FRAME_ON = """        VDP_REG 1, $E0          ; the display on, and the frame's signal
        in a, (VDP_CTRL)
"""

SAY = {
    "tune": "the book's tune, played by the interrupt",
    "effects": "the tune, and four effects over channel C",
    "fast": "the tune ticked in every frame, at 60 Hz too",
    "sixth": "the tune with one frame in six left out at 60 Hz",
    "latch": "the joystick read with the interrupts on",
}
PACES = {"tune": PACE, "effects": PACE, "latch": PACE, "fast": PACE_FAST, "sixth": PACE_SIXTH}


def head(name):
    return HEAD.format(name=name, chapter=37, what=SAY[name])


ENGINE_INC = '        INCLUDE "music.inc"\n'


def requests_data():
    out = ["requests:                       ; a tick, then the effect asked for"]
    for tick, fx in REQUESTS:
        out.append(f"        dw {tick}")
        out.append(f"        db {fx}")
    out.append("        dw $FFFF                ; no more")
    return "\n".join(out) + "\n"


# effects.asm's requests: (the tick, the effect)
REQUESTS = [(30, "JUMP"), (90, "SHOT"), (96, "SHOT"), (150, "COIN"), (156, "JUMP"),
            (220, "BOOM"), (230, "COIN"), (236, "BOOM"), (300, "COIN"), (306, "BOOM")]


def program(name):
    fx, joy = name == "effects", name == "latch"
    pace = "sixth" if name == "sixth" else "owed"
    body = gen34.setup(TEXT_REGS) + init_lines(pace)
    if fx:
        body += """        ld hl, requests
        ld (nextrq), hl
        ld hl, said
        ld (saidp), hl
"""
    body += im2("isr") + FRAME_ON
    if joy:
        body += """main:   ei
        halt                    ; the first frame
loop:   di
        call show               ; the screen, with the interrupts off
        ld a, (frames)
        ld (seen), a
        ei                      ; WHERE IT BREAKS: then, till the next frame,
.poll:  xor a                   ; joystick 1 again and again, with the
        call joy                ; interrupts on
        ld (port1), a
        ld a, (seen)
        ld hl, frames
        cp (hl)
        jr z, .poll             ; the same frame: again
        jp loop                 ; the next one has begun
"""
    else:
        body += """main:   ei
        halt                    ; wait for the frame
        di                      ; the interrupts off: the VDP, the effects
""" + ("        call request            ; an effect, if its tick has come\n" if fx else "") + \
            """        call show
        jp main
"""
    parts = ISR + PACES[name] + SEND + PLAY + ROW + VOICE + NEXT + SOUND
    if fx:
        parts += SFX + REQUEST
    if joy:
        parts += gen35.JOY
    parts += show_lines(fx, joy) + PRINTS + gen34.PRINT
    say = ""
    if joy:
        say = """; WHERE IT BREAKS. The tune, and a main program that reads joystick 1
; between frames with the interrupts on: when the interrupt comes between
; its choice of a register and its use of it, tochip has chosen another.
"""
    data = start_data() + (requests_data() if fx else "")
    return (head(name) + RAM + fields() + IM2 + say + tidy(body + parts) + data + ENGINE_INC +
            gen35.text_tail(gen34.page(screen_texts(f"{name}.asm", fx, joy))) + CART_END)


PROGRAMS = ["tune", "effects", "fast", "sixth", "latch"]


# ------------------------------------------------------------------ music.inc
def wrap(label, words, width=76):
    """a label and its bytes, in db lines no longer than WIDTH"""
    line, lines = label.ljust(7) + " db ", []
    for w in words:
        if len(line) + len(w) + 2 > width:
            lines.append(line.rstrip().rstrip(","))
            line = "        db "
        line += w + ", "
    lines.append(line.rstrip().rstrip(","))
    return lines


def music_inc():
    m.check()
    pats = m.patterns()
    used = sorted({n for evs in pats.values() for _, n, _ in evs if n} |
                  {m.note(e[3]) for e in m.EFFECTS})
    out = ["; music.inc -- chapter 37: the book's tune, its instruments and the",
           "; effects; generated by gen37.py from music37.py",
           f"SPEED   EQU {m.SPEED:<16}; ticks to a row",
           f"TONE    EQU {m.TONE:<16}; an instrument's mixer bits",
           f"NOISE   EQU {m.NOISE}",
           f"LOOP    EQU ${m.LOOP:02X}             ; a pitch table's ends: from its first again,",
           f"HOLD    EQU ${m.HOLD:02X}             ; or its last again",
           f"END     EQU ${m.END:02X}             ; a volume table's end, and a pattern's"]
    for k, (name, *_) in enumerate(m.INSTRUMENTS):
        say = "; an instrument: $80 and its number" if k == 0 else ""
        out.append(f"{name:<8}EQU ${0x80 | k:02X}             {say}".rstrip())
    for k, (name, *_) in enumerate(m.EFFECTS):
        out.append(f"{name:<8}EQU {k}")
    for n in used:
        out.append(f"{m.name_of(n):<8}EQU {n}")
    out.append("")
    out.append("        ALIGN 256")
    out.append("notes:                          ; a period for each note, 0 a rest:")
    out.append("        dw 0                    ; 3,579,545 / (32 x f)")
    for octave in range(1, 8):
        ns = range(1 + 12 * (octave - 1), 13 + 12 * (octave - 1))
        per = [m.period(n) for n in ns]
        out.append(f"        dw {', '.join(str(p) for p in per[:6])}")
        out.append(f"        dw {', '.join(str(p) for p in per[6:])} ; C{octave}-B{octave}")
    out.append("")
    out.append("instruments:                    ; volume table, pitch table, mixer, noise")
    for name, levels, pitches, mix, noisep in m.INSTRUMENTS:
        low = name.lower()
        mixer = {1: "TONE", 2: "NOISE", 3: "TONE | NOISE"}[mix]
        out.append(f"        dw vol_{low}, pitch_{low} ; {name}")
        out.append(f"        db {mixer}, {noisep}")
    out.append("")
    for name, levels, pitches, mix, noisep in m.INSTRUMENTS:
        low = name.lower()
        out += wrap(f"vol_{low}:", [str(v) for v in levels] + ["END"])
        out += wrap(f"pitch_{low}:", [{m.LOOP: "LOOP", m.HOLD: "HOLD"}.get(p, str(p)) for p in pitches])
    out.append("")
    out.append("effects:                        ; priority, instrument, note, ticks")
    for name, prio, instr, n, ticks in m.EFFECTS:
        out.append(f"        db {prio}, {instr}, {n}, {ticks}".ljust(32) + f"; {name}")
    out.append("")
    out.append("song:                           ; patterns for A, B and C, a bar each")
    for a, b, c in m.SONG:
        out.append(f"        dw {a}, {b}, {c}")
    out.append("        dw 0                    ; back to the first bar")
    out.append("")
    names = {k: name for k, (name, *_) in enumerate(m.INSTRUMENTS)}
    for pname, evs in pats.items():
        words = []
        for k, n, rows in evs:
            if k is not None:
                words.append(names[k])
            words += ["0" if n == 0 else m.name_of(n), str(rows)]
        words.append("END")
        out += wrap(f"{pname}:", words)
    text = "\n".join(out) + "\n"
    assert max(len(l) for l in text.splitlines()) <= 78
    return text


def main():
    with open(os.path.join(HERE, "music.inc"), "w") as f:
        f.write(music_inc())
    for name in PROGRAMS:
        with open(os.path.join(HERE, f"{name}.asm"), "w") as f:
            f.write(program(name))
    print("music.inc " + " ".join(f"{n}.asm" for n in PROGRAMS))


if __name__ == "__main__":
    main()
