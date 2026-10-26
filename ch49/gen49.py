#!/usr/bin/env python3
"""gen49.py - the programs of chapter 49: samples through the PSG.

    python3 gen49.py && ./build.sh

    one.asm     the sounds on one channel: each sample a volume of channel
                A, 0 to 15, two to a byte, written into R8 every 452
                T-states (7,919 a second)
    three.asm   the same sounds on three channels: each sample a byte, the
                row of a table whose three runs of 256 bytes hold A's, B's and C's
                volumes, 256 sums of three levels as evenly spread as
                sixteen levels a channel allow
    skip.asm    WHERE IT BREAKS: three.asm, but a sample the same as the one
                before writes nothing: that way through the loop is shorter

The sounds are made here, in Python, and are the book's own: a kick drum, a
hi-hat, a snare drum and the hi-hat again, 0.15 seconds each, then the vowel
a, 0.6 seconds, three formants over a pulse; 20 milliseconds of ramp before
and after, from silence to the middle level and back. The noise is chapter
41's xorshift. Each program shuts every tone and noise in R7, so that a
channel's output is its volume, and plays the sounds once with the
interrupts off; then it stops. build.sh assembles with --syntax=bFw.
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
for ch in ("tools", "ch26", "ch41"):
    sys.path.insert(0, os.path.join(REPO, ch))
from asmparts import HEAD, CART_END  # noqa: E402
from gen26 import tidy, db_rows  # noqa: E402  (chapter 26)
import gen41  # noqa: E402  (chapter 41: xorshift)
sys.path.insert(0, HERE)
import psg36  # noqa: E402  (chapter 36: the PSG's levels)

EU, JP = "MSXBOOK_EU16", "MSXBOOK_JP16"
CLOCK = 3579545                 # the processor's T-states in a second
PERIOD = 452                    # T-states from a sample to the next
FS = CLOCK / PERIOD             # samples a second: 7,919.35
MIXER_OFF = 0xBF                # R7: every tone and noise shut; port A in, B out
VOLUME = psg36.VOLUME           # the sixteen levels of a channel (chapter 36)
TOP = VOLUME[15]


# ================================================================ the sounds
def seconds(s):
    return round(s * FS)


STEP = seconds(0.15)            # a drum: 1,188 samples
VOWEL_N = seconds(0.6)          # the vowel: 4,752
RAMP = seconds(0.02)            # silence to the middle level: 158
F0 = (125.0, 110.0)             # the vowel's pitch, from start to end
FORMANTS = [(730, 80), (1090, 90), (2440, 120)]     # a as in father: Hz, bandwidth
NOISE_SEED = 1


def noise(n, seed=NOISE_SEED):
    """N numbers from -1 to 1 from chapter 41's xorshift"""
    out, x = [], seed
    for _ in range(n):
        x = gen41.xorshift(x)
        out.append(x / 32768 - 1)
    return out


def peak(xs, p):
    m = max(abs(v) for v in xs)
    return [v * p / m for v in xs]


def kick():
    """a sine falling from 160 to 50 Hz, dying away"""
    out, phase = [], 0.0
    for k in range(STEP):
        t = k / FS
        phase += 2 * math.pi * (50 + 110 * math.exp(-t / 0.025)) / FS
        out.append(math.sin(phase) * math.exp(-t / 0.08))
    return peak(out, 1.0)


def snare():
    """noise and a 190 Hz tone, dying away"""
    nz = noise(STEP, 7)
    out = []
    for k in range(STEP):
        t = k / FS
        noisy = 0.7 * nz[k] * math.exp(-t / 0.045)
        tone = 0.5 * math.sin(2 * math.pi * 190 * t) * math.exp(-t / 0.03)
        out.append(noisy + tone)
    return peak(out, 0.9)


def hat():
    """the noise's steps, its highest part, dying away fast"""
    nz = noise(STEP + 1, 3)
    out = [(nz[k + 1] - nz[k]) * math.exp(-(k / FS) / 0.012) for k in range(STEP)]
    return peak(out, 0.6)


def resonator(xs, f, bw):
    """a formant: a filter ringing at F Hz, BW Hz wide, a gain of 1 at 0 Hz"""
    r = math.exp(-math.pi * bw / FS)
    b, c = 2 * r * math.cos(2 * math.pi * f / FS), -r * r
    a = 1 - b - c
    y1 = y2 = 0.0
    out = []
    for x in xs:
        y = a * x + b * y1 + c * y2
        out.append(y)
        y1, y2 = y, y1
    return out


def vowel():
    """a: a pulse at 125 falling to 110 Hz, through three formants"""
    src, phase = [], 0.0
    for k in range(VOWEL_N):
        f0 = F0[0] + (F0[1] - F0[0]) * k / VOWEL_N
        phase += f0 / FS
        p = phase % 1.0                 # a pulse of the glottis: open 40% of a period
        src.append(0.5 * (1 - math.cos(2 * math.pi * p / 0.4)) if p < 0.4 else 0.0)
    m = sum(src) / len(src)
    y = [v - m for v in src]
    for f, bw in FORMANTS:
        y = resonator(y, f, bw)
    attack, release = seconds(0.03), seconds(0.08)
    for k in range(VOWEL_N):
        g = min(1.0, k / attack, (VOWEL_N - 1 - k) / release)
        y[k] *= g
    return peak(y, 0.95)


SOUNDS = [("kick", kick()), ("hat", hat()), ("snare", snare()), ("hat", hat()), ("vowel", vowel())]


def wave():
    """every sample of the sequence, from -1 to 1, with the ramps; and where
    each sound starts"""
    out = [-1 + k / RAMP for k in range(RAMP)]
    starts = []
    for name, xs in SOUNDS:
        starts.append((name, len(out), len(xs)))
        out += xs
    out += [-k / RAMP for k in range(1, RAMP + 1)]
    return out, starts


WAVE, STARTS = wave()
SAMPLES = len(WAVE)
assert SAMPLES % 2 == 0


def level(x):
    """a sample from -1 to 1 -> the level it means, 0 to the top"""
    return (x + 1) / 2


def one_volumes():
    """each sample as channel A's nearest volume"""
    out = []
    for x in WAVE:
        want = level(x) * TOP
        out.append(min(range(16), key=lambda v: abs(VOLUME[v] - want)))
    return out


def table():
    """256 rows, each three volumes whose levels add up nearest to row/255 of
    three channels' top"""
    combos = sorted(((VOLUME[a] + VOLUME[b] + VOLUME[c], a, b, c)
                     for a in range(16) for b in range(16) for c in range(16)))
    rows = []
    for i in range(256):
        want = i * 3 * TOP / 255
        best = min(combos, key=lambda s: (abs(s[0] - want), s[1:]))
        rows.append(best[1:])
    return rows


VOLS = table()
SUMS = [sum(VOLUME[v] for v in r) for r in VOLS]


def three_rows():
    return [round(level(x) * 255) for x in WAVE]


ONE = one_volumes()
THREE = three_rows()


# ================================================================ the programs
def head(name, what):
    return HEAD.format(name=name, chapter=49, what=what)


PSG = """
; psg: A = a register, E = a byte -> the byte in that register. Uses A
psg:    out (PSG_ADDR), a       ; 12  the register
        ld a, e                 ;  5
        out (PSG_WRITE), a      ; 12  the byte
        ret                     ; 11
"""


def setup(play):
    return f"""init:   di                      ; the interrupts off, the whole time
        ld sp, SYS_AREA
        ld a, 7
        ld e, ${MIXER_OFF:02X}
        call psg                ; tones and noise shut: a channel is its volume
        ld e, 0
        ld a, 8
        call psg
        ld a, 9
        call psg
        ld a, 10
        call psg                ; the three silent
{play}done:   jr done                 ; played: nothing more
"""


WAIT1 = (PERIOD - 116) // 14 + 1
assert 116 + 14 * (WAIT1 - 1) == PERIOD

PLAY1 = f"""
; play1: HL = the sound, two volumes a byte, the first in the high four bits;
;        DE = its samples, an even number -> each volume into R8, channel
;        A's, one every {PERIOD} T-states. The interrupts must be off.
;        Uses A, B, DE, HL
play1:  ld a, 8                 ;  8
        out (PSG_ADDR), a       ; 12  R8 chosen, and left chosen
.next:  bit 0, e                ; 10  an odd count left: the low four bits
        jr z, .high             ; 13, or 8
        ld a, (hl)              ;  8
        and 15                  ;  8  the low volume
        inc hl                  ;  7  and the next byte after it
        nop                     ;  5  this way as long as the other
        jr .out                 ; 13
.high:  ld a, (hl)              ;  8
        rrca                    ;  5
        rrca                    ;  5
        rrca                    ;  5
        rrca                    ;  5
        and 15                  ;  8  the high volume
.out:   out (PSG_WRITE), a      ; 12  heard from here
        dec de                  ;  7
        ld a, d                 ;  5
        or e                    ;  5
        ld b, {WAIT1}                ;  8
.wait:  djnz .wait              ; 14, or 9
        jp nz, .next            ; 11  DJNZ leaves the flags OR E set
        ret                     ; 11
"""

WAIT3 = (PERIOD - 212) // 16
assert 212 + 16 * WAIT3 == PERIOD

PLAY3 = f"""
; play3: BC = the sound, a byte a sample; DE = its samples -> each byte's
;        three volumes, from vols' three runs of 256, into R8, R9 and R10, a
;        sample every {PERIOD} T-states. The interrupts must be off.
;        Uses A, BC, DE, HL
play3:  ld hl, vols             ; 11  L = 0: the row the setup wrote
.next:  ld a, (bc)              ;  8  the sample: a row of vols
        ld l, a                 ;  5
        ld a, 8                 ;  8
        out (PSG_ADDR), a       ; 12
        ld a, (hl)              ;  8
        out (PSG_WRITE), a      ; 12  channel A's volume
        inc h                   ;  5
        ld a, 9                 ;  8
        out (PSG_ADDR), a       ; 12
        ld a, (hl)              ;  8
        out (PSG_WRITE), a      ; 12  B's
        inc h                   ;  5
        ld a, 10                ;  8
        out (PSG_ADDR), a       ; 12
        ld a, (hl)              ;  8
        out (PSG_WRITE), a      ; 12  C's
        dec h                   ;  5
        dec h                   ;  5
        inc bc                  ;  7
        dec de                  ;  7
        ld a, d                 ;  5
        or e                    ;  5
        ret z                   ; 12, or 6
        nop                     ;  5
        nop                     ;  5
        ld a, {WAIT3}               ;  8
.wait:  dec a                   ;  5
        jp nz, .wait            ; 11  16 T-states a turn
        jp .next                ; 11
"""

SKIP = (("""        ld l, a                 ;  5
        ld a, 8                 ;  8""", """        cp l                    ;  5  the same as the sample before?
        jr z, .same             ; 13, or 8  then nothing to write
        ld l, a                 ;  5
        ld a, 8                 ;  8"""),
        ("""        dec h                   ;  5
        inc bc                  ;  7""", """        dec h                   ;  5
.same:  inc bc                  ;  7"""),
        (f""";        three volumes, from vols' three runs of 256, into R8, R9 and R10, a
;        sample every {PERIOD} T-states. The interrupts must be off.""",
         f""";        three volumes, from vols' three runs of 256, into R8, R9 and R10: a
;        new sample in {PERIOD + 13} T-states, one the same as the one before
;        in {PERIOD + 18 - 145}. The interrupts must be off."""))


def patched(text, pairs):
    for old, new in pairs:
        assert text.count(old) == 1, old
        text = text.replace(old, new)
    return text


def pack(vols):
    return [vols[k] << 4 | vols[k + 1] for k in range(0, len(vols), 2)]


def sound_data(rows, what):
    return f"sound:                          ; {what}\n" + db_rows(rows, 12)


def vols_data():
    out = "        ALIGN 256\nvols:                           ; 256 rows: A's volumes, then B's, then C's\n"
    for c, who in enumerate("ABC"):
        out += f"        ; channel {who}\n" + db_rows([r[c] for r in VOLS], 16)
    return out


SAY = {
    "one": f"""; The sounds on one channel: kick, hi-hat, snare, hi-hat, the vowel a,
; {SAMPLES:,} samples, {FS:,.0f} a second, each a volume of channel A, two to a byte.
""",
    "three": f"""; The same sounds on three channels: each sample a row of vols, three volumes
; whose levels add up to one of 256 steps, {FS:,.0f} samples a second.
""",
    "skip": """; WHERE IT BREAKS. three.asm with a short way through the loop: a sample the
; same as the one before writes nothing, and comes sooner.
"""}
WHAT = {"one": "samples on one channel", "three": "samples on three channels",
        "skip": "a loop with two ways of different lengths"}


def program(name):
    if name == "one":
        play = f"""        ld hl, sound
        ld de, SAMPLES
        call play1
"""
        code = setup(play) + PLAY1 + PSG
        data = sound_data(pack(ONE), f"{SAMPLES:,} volumes, two to a byte")
    else:
        play = f"""        ld bc, sound
        ld de, SAMPLES
        call play3
"""
        p3 = PLAY3 if name == "three" else patched(PLAY3, SKIP)
        code = setup(play) + p3 + PSG
        data = vols_data() + sound_data(THREE, f"{SAMPLES:,} rows of vols")
    return (head(name, WHAT[name]) + f"SAMPLES EQU {SAMPLES}             ; the samples of the sounds\n" +
            SAY[name] + tidy(code) + data + CART_END)


VARIANTS = {
    # one.asm without the NOP that makes play1's two ways as long
    "nonop": ("one", {"nop": 1}),
    # play1 and play3 without their waits: what is left is the loop's own work
    "nowait1": ("one", {f"ld b, {WAIT1}": 1, ".wait:  djnz .wait": 1}),
    "nowait3": ("three", {"nop": 2, f"ld a, {WAIT3}": 1, ".wait:  dec a": 1, "jp nz, .wait": 1}),
}


def variant(kind):
    """the workshop's programs: (name, source), a program with lines taken
    out, each line as many times as VARIANTS says"""
    base, cut = VARIANTS[kind]
    src = program(base).replace(f"; {base}.asm -- chapter 49", f"; {kind}.asm -- chapter 49", 1)
    lines, seen = [], dict.fromkeys(cut, 0)
    for line in src.split("\n"):
        code = line.split(";")[0].strip()
        if code in cut:
            seen[code] += 1
        else:
            lines.append(line)
    assert seen == cut, (kind, seen)
    src = "\n".join(lines).replace(f'OUTPUT "{base}.rom"', f'OUTPUT "{kind}.rom"')
    return kind, src


PROGRAMS = ["one", "three", "skip"]


def main():
    for name in PROGRAMS:
        with open(os.path.join(HERE, f"{name}.asm"), "w") as f:
            f.write(program(name))
    print(" ".join(f"{n}.asm" for n in PROGRAMS), "samples", SAMPLES, "rate", round(FS, 2),
          "starts", STARTS)


if __name__ == "__main__":
    main()
