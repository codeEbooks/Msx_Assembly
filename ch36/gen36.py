#!/usr/bin/env python3
"""gen36.py - the programs of chapter 36: the PSG.

    python3 gen36.py && ./build.sh

    levels.asm   channel A's level on its own, the mixer shut: 15 down to 0,
                 a frame each; then 0 and 15 in turn, a few frames apart
    tones.asm    C4 on channel A; E4 added on B; G4 on C; channel A's tone
                 shut in the mixer for three frames and opened again; A two
                 octaves up, to C6 (figure 36.2)
    scale.asm    the table of notes, C4 to C5, eight frames each, on A
    noise.asm    the noise on its own at four periods; with a tone on the
                 same channel; and beside one, on another (figure 36.3)
    env.asm      the envelope as channel A's level: R13 = 0, 1, ..., 15, two
                 frames each, and 15 once more (figure 36.4)
    buzz.asm     the envelope as a wave: R13 = 8 at a short period, R13 = 10;
                 and R13 = 8 again with channel A's tone open
    mixer.asm    WHERE IT BREAKS: a note and joystick 1, with register 7
                 written without its top two bits, and then with both set

Every sound program runs a script, a frame at a time: after HALT, step
counts the script's frames down and writes its registers when the count
runs out, and show prints R0 to R13 as they read back, eight boxes and a
byte each (figure 36.1). The programs take the interrupt in mode 2
(chapter 17), touch the PSG with the interrupts off, print in Graphic I,
black ink on white, end with asmparts.CART_END, and build.sh assembles them
with --syntax=bFw. mixer.asm's joystick moves are in mixer.events (chapter
35's form: a frame, a port, the switches held from then on).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "tools"))
sys.path.insert(0, os.path.join(REPO, "ch34"))
sys.path.insert(0, os.path.join(REPO, "ch35"))
from asmparts import HEAD, CART_END, IM2, im2  # noqa: E402
import gen34  # noqa: E402  (chapter 34: the text screen and its routines)
import gen35  # noqa: E402  (chapter 35: joy)
from gen26 import tidy, db_rows  # noqa: E402  (chapter 26)

EU, JP = "MSXBOOK_EU16", "MSXBOOK_JP16"
AY = "MSXBOOK_EU16AY"           # the book's machine with an AY-3-8910 (chapter 3)
PORTS = "MSXBOOK_EU16P"         # the book's machine with a PSG that minds register 7's top bits
TEXT_REGS = gen34.TEXT_REGS

CLOCK = 3579545                 # the processor's T-states in a second
A4 = 440.0
NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
MIXER_OFF = 0xBF                # R7: every tone and noise shut; port A in, B out
REG_NAMES = [f"R{r}" for r in range(14)]


def hz(note):
    """note: 0 is C4 -> its frequency, equal temperament, A4 = 440 Hz"""
    return A4 * 2 ** ((note - 9) / 12)


def period(f):
    """the nearest tone period: a cycle lasts 32 x TP T-states"""
    return round(CLOCK / (32 * f))


def name(note):
    return f"{NAMES[note % 12]}{4 + note // 12}"


SCALE = list(range(13))                     # C4 to C5
C4, E4, G4, C6 = 0, 4, 7, 24


def mixer(tones=(), noises=()):
    """R7's byte: a 0 opens a channel's tone (bits 0-2) or noise (3-5); bits
    6 and 7 stay 1 and 0, port A in and port B out"""
    v = MIXER_OFF
    for c in tones:
        v &= ~(1 << c)
    for c in noises:
        v &= ~(8 << c)
    return v & 255


def tone(ch, tp):
    return [(2 * ch, tp & 255), (2 * ch + 1, tp >> 8)]


# ------------------------------------------------------------------ scripts
# a script: steps of (frames to count, [(register, byte), ...]): the count
# runs down a frame at a time, and at 0 the registers are written, in order

LEVELS = ([(10, [(7, MIXER_OFF), (8, 15)])]
          + [(1, [(8, v)]) for v in range(14, -1, -1)]
          + [(3 + k % 4, [(8, 15 if k % 2 == 0 else 0)]) for k in range(16)]
          + [(4, [(8, 0)])])

TONES = [
    (10, [(7, MIXER_OFF)]),
    (10, tone(0, period(hz(C4))) + [(8, 15), (7, mixer((0,)))]),
    (10, tone(1, period(hz(E4))) + [(9, 13), (7, mixer((0, 1)))]),
    (10, tone(2, period(hz(G4))) + [(10, 11), (7, mixer((0, 1, 2)))]),
    (10, [(7, mixer((1, 2)))]),                 # A's tone shut: its level
    (3, [(7, mixer((0, 1, 2)))]),               # and open again
    (4, tone(0, period(hz(C6)))),               # A two octaves up, its count past the new period
    (5, [(8, 0), (9, 0), (10, 0)]),
]

SCALE_HOLD = 8
SCALE_STEPS = ([(10, [(7, MIXER_OFF)])]
               + [(10 if k == 0 else SCALE_HOLD,
                   tone(0, period(hz(n))) + ([(8, 15), (7, mixer((0,)))] if k == 0 else []))
                  for k, n in enumerate(SCALE)]
               + [(SCALE_HOLD, [(8, 0)])])

NOISE_PERIODS = (31, 15, 1, 0)
NOISE = ([(10, [(7, MIXER_OFF), (8, 15)])]
         + [(10, [(6, NOISE_PERIODS[0]), (7, mixer((), (0,)))])]
         + [(10, [(6, p)]) for p in NOISE_PERIODS[1:]]
         + [(10, tone(0, period(hz(C4))) + [(6, 15), (7, mixer((0,), (0,)))]),
            (10, [(9, 10), (6, 4), (7, mixer((0,), (1,)))]),
            (10, [(8, 0), (9, 0)])])

ENV_PERIOD = 70
ENV_HOLD = 2
ENV = ([(10, [(7, MIXER_OFF), (11, ENV_PERIOD), (12, 0)])]
       + [(10 if s == 0 else ENV_HOLD, ([(8, 16)] if s == 0 else []) + [(13, s)])
          for s in range(16)]
       + [(ENV_HOLD, [(13, 15)])]              # 15 again: the same value starts it again
       + [(ENV_HOLD, [(8, 0)])])

SAW_PERIOD, TRI_PERIOD = 17, 8
BUZZ = [(10, [(7, MIXER_OFF), (8, 16)]),
        (10, [(11, SAW_PERIOD), (12, 0), (13, 8)]),             # a sawtooth
        (10, [(11, TRI_PERIOD), (13, 10)]),                     # a triangle
        (10, tone(0, 8 * SAW_PERIOD) + [(7, mixer((0,))), (11, SAW_PERIOD), (13, 8)]),
        (10, [(8, 0)])]

# WHERE IT BREAKS: a note on A, and register 7 written as if it had six bits
MIX_WRONG = [(0x3E, "bits 6 and 7 at 0"), (0xFE, "bits 6 and 7 at 1")]
MIX_HOLD = 30
MIXER = [(10, tone(0, period(hz(C4))) + [(8, 12), (7, mixer((0,)))]),
         (MIX_HOLD, [(7, MIX_WRONG[0][0])]),
         (MIX_HOLD, [(7, MIX_WRONG[1][0])]),
         (MIX_HOLD, [(7, mixer((0,)))]),
         (MIX_HOLD, [(8, 0)])]

SCRIPTS = {"levels": LEVELS, "tones": TONES, "scale": SCALE_STEPS, "noise": NOISE,
           "env": ENV, "buzz": BUZZ, "mixer": MIXER}
SOUNDS = ["levels", "tones", "scale", "noise", "env", "buzz"]
PROGRAMS = SOUNDS + ["mixer"]


def frames_of(steps):
    """the frame of each step's writes, counted from the first frame step runs in"""
    out, f = [], 0
    for count, writes in steps:
        f += count
        out.append((f, writes))
    return out


def length(steps):
    return frames_of(steps)[-1][0]


def script_data(steps):
    out = ["script:                         ; frames to count, then register, byte ..., $FF"]
    for count, writes in steps:
        pairs = ", ".join(f"{r}, ${v:02X}" for r, v in writes)
        out.append(f"        db {count}, {pairs}, $FF")
    out.append("        db 0                    ; the end")
    return "\n".join(out) + "\n"


# ------------------------------------------------------------------ the parts
RAM = """ticks   EQU VARS                ; frames counted by isr
count   EQU VARS + 1            ; the script's frames still to count
next    EQU VARS + 2            ; and where its next writes are
byte    EQU VARS + 4            ; show: the register just read
port1   EQU VARS + 5            ; mixer.asm: register 14 of port 1
r7      EQU VARS + 6            ; register 7, read back
r15     EQU VARS + 7            ; register 15, read back
"""

PSG = """
; psg: A = a register, E = a byte -> the byte in that register. Uses A
psg:    out (PSG_ADDR), a       ; 12  the register
        ld a, e                 ;  5
        out (PSG_WRITE), a      ; 12  the byte
        ret                     ; 11
"""

STEP = """
; step: the script's count down by one; when it runs out, its registers
; written, pair after pair, and the next count read. A count of 0 is the
; end. Uses A, E, HL
step:   ld hl, count            ; 11
        ld a, (hl)              ;  8
        or a                    ;  5
        ret z                   ; 12, or 6   the script is over
        dec (hl)                ; 12
        ret nz                  ; 12, or 6   not yet
        ld hl, (next)           ; 17
.pair:  ld a, (hl)              ;  8  a register, or $FF
        inc hl                  ;  7
        cp $FF                  ;  8
        jr z, .end              ; 13, or 8
        ld e, (hl)              ;  8  its byte
        inc hl                  ;  7
        call psg                ; 18
        jr .pair                ; 13
.end:   ld a, (hl)              ;  8  the next count
        inc hl                  ;  7
        ld (count), a           ; 14
        ld (next), hl           ; 17
        ret                     ; 11
"""

TOP = 4                         # the screen row of R0 and of R7
LABEL_COL = (0, 17)             # R0-R6 on the left, R7-R13 on the right
BOX_COL = (4, 21)
HEX_COL = (13, 30)

SHOW = f"""
; show: R0 to R13 as they read back, each as eight boxes from bit 7, a
; filled box for a 1, and its byte. Uses A, B, C, D, E, H, L
show:   ld h, 0                 ; R0
.reg:   ld a, h
        ld e, {BOX_COL[0]}
        cp 7
        jr c, .left
        sub 7                   ; R7 to R13: the right-hand column
        ld e, {BOX_COL[1]}
.left:  add a, {TOP}
        ld d, a
        call at
        ld a, h
        out (PSG_ADDR), a
        in a, (PSG_READ)        ; the register, as it reads back
        ld (byte), a
        cpl
        call cells
        ld a, e
        add a, {HEX_COL[0] - BOX_COL[0]}
        ld e, a
        call at
        ld a, (byte)
        call hex
        inc h
        ld a, h
        cp 14
        jr nz, .reg
        ret
"""


def head(name, what):
    return HEAD.format(name=name, chapter=36, what=what)


def regs_texts(title):
    t = [(1, 0, title)]
    for r in range(14):
        side = r // 7
        t.append((TOP + r % 7, LABEL_COL[side], REG_NAMES[r]))
    return t


START = """        ld hl, script           ; the first count
        ld a, (hl)
        inc hl
        ld (count), a
        ld (next), hl
        VDP_REG 1, $E0          ; the display on, and the frame's signal
        in a, (VDP_CTRL)
main:   ei
        halt                    ; wait for the frame
        di                      ; the interrupts off: the PSG, then the VDP
        call step               ; this frame's writes, if any
"""

SAY = {
    "levels": "channel A's level on its own, 15 down to 0",
    "tones": "a chord, built a channel at a time",
    "scale": "C4 to C5 on channel A",
    "noise": "the noise, alone and with tones",
    "env": "the sixteen shapes of the envelope",
    "buzz": "the envelope as a wave",
}


def sound(name):
    body = gen34.setup(TEXT_REGS) + im2("isr") + START + "read:   call show\n        jp main\n"
    return (head(name, SAY[name]) + RAM + IM2 +
            tidy(body + STEP + PSG + SHOW + gen34.ISR + gen34.PRINT) +
            script_data(SCRIPTS[name]) +
            gen35.text_tail(gen34.page(regs_texts(f"{name}.asm"))) + CART_END)


# ------------------------------------------------------------------ mixer.asm
MIX_ROWS = {"port1": 4, "r7": 6, "r15": 8}
MIX_COL = 6


def mixer_texts():
    return [(1, 0, "mixer.asm"),
            (MIX_ROWS["port1"], 0, "R14"), (MIX_ROWS["r7"], 0, "R7"), (MIX_ROWS["r15"], 0, "R15")]


def mixer_program():
    body = gen34.setup(TEXT_REGS) + im2("isr") + START + """        xor a                   ; joystick 1
        call joy
        ld (port1), a
        ld a, 7                 ; registers 7 and 15, as they read back
        call reg
        ld (r7), a
        ld a, 15
        call reg
        ld (r15), a
read:
""" + gen35.show(MIX_ROWS["port1"], MIX_COL, "port1", "keys") + \
        gen35.show(MIX_ROWS["r7"], MIX_COL, "r7", "bits") + \
        gen35.show(MIX_ROWS["r15"], MIX_COL, "r15", "bits") + "        jp main\n"
    say = """; WHERE IT BREAKS. A note on channel A, and joystick 1 read every frame; the
; script writes register 7 as if it had six bits, then with bits 6 and 7 set.
"""
    return (head("mixer", "register 7's top two bits") + RAM + IM2 + say +
            tidy(body + STEP + PSG + gen35.JOY + gen35.READ_REG + gen34.ISR + gen34.PRINT) +
            script_data(MIXER) + gen35.text_tail(gen34.page(mixer_texts())) + CART_END)


# ------------------------------------------------------------------ events
MIX_HELD = [(5, 1, "right")]                 # joystick 1 held right from frame 5


def write_events():
    lines = ["# mixer.events -- written by gen36.py: a frame counted from INIT, a port,",
             "# and the switches held from that frame on (- for none)"]
    lines += [f"{f} {p} {held}" for f, p, held in MIX_HELD]
    with open(os.path.join(HERE, "mixer.events"), "w") as f:
        f.write("\n".join(lines) + "\n")


def main():
    for name in SOUNDS:
        with open(os.path.join(HERE, f"{name}.asm"), "w") as f:
            f.write(sound(name))
    with open(os.path.join(HERE, "mixer.asm"), "w") as f:
        f.write(mixer_program())
    write_events()
    print(" ".join(f"{n}.asm" for n in PROGRAMS))


if __name__ == "__main__":
    main()
