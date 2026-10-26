#!/usr/bin/env python3
"""music37.py -- chapter 37's music and effects, and their bytes.

The tune is the book's own: sixteen bars in E minor for three voices, a
melody on channel A, a bass on B, and on C drums, with chords played as
arpeggios in the four bars of the middle (9 to 12). A row is SPEED ticks of
the player, a bar sixteen rows. The four effects are the book's own too: a
jump, a shot, a coin and a boom, each an instrument, a note, its length in
ticks and a priority.

    python3 music37.py      the tune's sizes and its lengths

gen37.py writes music.inc from what is here; player37.py, the player in
Python, reads the bytes back from the cartridges, and meas37.py checks that
they are these.
"""
CLOCK = 3579545
SPEED = 5                       # ticks to a row
ROWS = 16                       # rows to a bar
TONE, NOISE = 1, 2              # an instrument's mixer bits
LOOP, HOLD = 0x80, 0x81         # a pitch table's ends
END = 0xFF                      # a volume table's end, and a pattern's
NAMES = ["C", "Cs", "D", "Ds", "E", "F", "Fs", "G", "Gs", "A", "As", "B"]
LOWEST, HIGHEST = 1, 84         # C1 to B7; 0 is a rest


def note(name):
    """'E5' -> 53: C1 is 1, C2 13, C4 37"""
    pitch, octave = name[:-1], int(name[-1])
    return 1 + NAMES.index(pitch) + 12 * (octave - 1)


def name_of(n):
    return f"{NAMES[(n - 1) % 12]}{1 + (n - 1) // 12}"


def hz(n):
    """equal temperament, A4 (note 46) at 440 Hz"""
    return 440.0 * 2 ** ((n - 46) / 12)


def period(n):
    """the PSG's period for note N: a cycle is 32 x TP T-states"""
    return round(CLOCK / (32 * hz(n)))


# ------------------------------------------------------------------ instruments
# name: (levels a tick, then the last held; semitones a tick, then LOOP or
# HOLD; mixer bits; the noise's period)
INSTRUMENTS = [
    ("LEAD", [15, 14, 13, 12, 12, 11, 11, 10], [0, HOLD], TONE, 0),
    ("BASS", [15, 13, 12, 11, 10, 10, 9], [0, HOLD], TONE, 0),
    ("KICK", [15, 14, 12, 10, 8, 6, 4, 2, 0], [12, 7, 3, 0, -3, -6, -9, HOLD], TONE, 0),
    ("SNARE", [15, 13, 11, 9, 8, 7, 6, 5, 4, 3, 2, 1, 0], [0, HOLD], TONE | NOISE, 6),
    ("HAT", [11, 7, 4, 2, 0], [0, HOLD], NOISE, 1),
    ("MAJOR", [12, 11, 10, 9, 8, 7, 7, 6], [0, 4, 7, LOOP], TONE, 0),
    ("MINOR", [12, 11, 10, 9, 8, 7, 7, 6], [0, 3, 7, LOOP], TONE, 0),
    # the effects' own
    ("UP", [13, 13, 12, 12, 11, 11, 10, 9, 8, 7, 6, 5, 4, 3],
     [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, HOLD], TONE, 0),
    ("DOWN", [14, 14, 13, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2],
     [24, 21, 18, 15, 12, 10, 8, 6, 4, 3, 2, 1, 0, HOLD], TONE, 0),
    ("BELL", [13, 13, 13, 13, 14, 13, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1],
     [0, 0, 0, 0, 5, HOLD], TONE, 0),
    ("BLAST", [15, 15, 14, 14, 13, 13, 12, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
     [0, HOLD], TONE | NOISE, 24),
]
INSTR = {name: k for k, (name, *_) in enumerate(INSTRUMENTS)}

# ------------------------------------------------------------------ effects
# name: (priority, instrument, note, ticks); a request is taken if no effect
# plays, or if the one playing has no higher priority
EFFECTS = [
    ("JUMP", 1, "UP", "G4", 14),
    ("SHOT", 1, "DOWN", "C5", 14),
    ("COIN", 2, "BELL", "B5", 18),
    ("BOOM", 3, "BLAST", "C2", 20),
]
FX = {name: k for k, (name, *_) in enumerate(EFFECTS)}

# ------------------------------------------------------------------ patterns
# a pattern: one bar of one channel, (instrument or None, note or None for a
# rest, rows); the instrument is written only where it changes


def bar(instr, text):
    """'B4 2 E5 2 - 2' -> events, the first with INSTR"""
    words = text.split()
    out = []
    for k in range(0, len(words), 2):
        n = None if words[k] == "-" else words[k]
        out.append([instr if k == 0 else None, n, int(words[k + 1])])
    return out


MELODY = {
    "mel1": "B4 2 E5 2 G5 4 Fs5 2 E5 2 B4 4",
    "mel2": "C5 2 E5 2 G5 4 A5 2 G5 2 E5 4",
    "mel3": "D5 2 Fs5 2 A5 4 G5 2 Fs5 2 D5 4",
    "mel4": "Ds5 4 Fs5 4 B4 8",
    "mel6": "C5 2 E5 2 G5 2 C6 2 B5 2 G5 2 E5 4",
    "mel7": "A5 4 G5 2 Fs5 2 E5 4 C5 4",
    "mel8": "B4 4 Ds5 4 Fs5 4 A5 4",
    "mel9": "G5 6 E5 2 C5 4 E5 4",
    "mel10": "Fs5 6 D5 2 A4 4 D5 4",
    "mel11": "G5 4 B5 4 A5 2 G5 2 Fs5 2 D5 2",
    "mel12": "E5 8 B4 4 E5 4",
    "mel13": "C5 2 E5 2 A5 4 G5 2 E5 2 C5 4",
    "mel14": "Ds5 2 Fs5 2 B5 4 A5 2 Fs5 2 Ds5 4",
    "mel15": "E5 4 G5 4 Fs5 2 E5 2 Ds5 2 E5 2",
    "mel16": "Fs5 4 Ds5 4 B4 6 - 2",
}


def octaves(root):
    """the bass: eighths, the root and its octave, the fifth on the seventh"""
    r = note(root)
    seq = [r, r + 12, r, r + 12, r, r + 12, r + 7, r + 12]
    return " ".join(f"{name_of(n)} 2" for n in seq)


BASS = {f"bass{root[:-1]}": octaves(root) for root in ("E2", "C2", "D2", "B1", "A1", "G1")}

DRUMS = {
    "beat": [["KICK", "C3", 2], ["HAT", "C5", 2], ["SNARE", "G3", 2], ["HAT", "C5", 2],
             ["KICK", "C3", 2], ["KICK", "C3", 2], ["SNARE", "G3", 2], ["HAT", "C5", 2]],
    "fill": [["KICK", "C3", 2], ["HAT", "C5", 2], ["SNARE", "G3", 2], ["HAT", "C5", 2],
             ["SNARE", "G3", 2], ["SNARE", "G3", 2], ["SNARE", "G3", 1], ["SNARE", "G3", 1],
             ["SNARE", "G3", 2]],
}
CHORDS = {"arpC": ("MAJOR", "C4"), "arpD": ("MAJOR", "D4"), "arpG": ("MAJOR", "G3"),
          "arpEm": ("MINOR", "E4")}


def patterns():
    """{name: [(instrument number or None, note number, rows)]} in the order they are kept"""
    raw = {}
    for name, text in MELODY.items():
        raw[name] = bar("LEAD", text)
    for name, text in BASS.items():
        raw[name] = bar("BASS", text)
    for name, events in DRUMS.items():
        raw[name] = [list(e) for e in events]
    for name, (instr, n) in CHORDS.items():
        raw[name] = [[instr, n, 4], [None, n, 4], [None, n, 4], [None, n, 4]]
    out = {}
    for name, events in raw.items():
        last, evs = None, []
        for instr, n, rows in events:
            k = None if instr is None or instr == last else INSTR[instr]
            if instr is not None:
                last = instr
            evs.append((k, 0 if n is None else note(n), rows))
        assert sum(r for _, _, r in evs) == ROWS, (name, sum(r for _, _, r in evs))
        out[name] = evs
    return out


SONG = [("mel1", "bassE", "beat"), ("mel2", "bassC", "beat"), ("mel3", "bassD", "beat"),
        ("mel4", "bassB", "beat"), ("mel1", "bassE", "beat"), ("mel6", "bassC", "beat"),
        ("mel7", "bassA", "beat"), ("mel8", "bassB", "fill"),
        ("mel9", "bassC", "arpC"), ("mel10", "bassD", "arpD"), ("mel11", "bassG", "arpG"),
        ("mel12", "bassE", "arpEm"),
        ("mel13", "bassA", "beat"), ("mel14", "bassB", "beat"), ("mel15", "bassE", "beat"),
        ("mel16", "bassB", "fill")]
BARS = len(SONG)
TICKS = BARS * ROWS * SPEED     # the tune, once through


# ------------------------------------------------------------------ bytes
def s8(v):
    return v & 255


def pattern_bytes(evs):
    out = []
    for k, n, rows in evs:
        if k is not None:
            out.append(0x80 | k)
        out += [n, rows]
    return out + [END]


def volume_bytes(levels):
    return list(levels) + [END]


def pitch_bytes(steps):
    return [s8(v) for v in steps]


def sizes():
    """the bytes of each part, as music.inc lays them out"""
    pats = patterns()
    return {
        "notes": 2 * (HIGHEST + 1),
        "instruments": 6 * len(INSTRUMENTS),
        "tables": sum(len(volume_bytes(v)) + len(pitch_bytes(p)) for _, v, p, _, _ in INSTRUMENTS),
        "effects": 4 * len(EFFECTS),
        "song": 6 * len(SONG) + 2,
        "patterns": sum(len(pattern_bytes(e)) for e in pats.values()),
    }


def check():
    """every note the tune and the effects can reach is in the table"""
    pats = patterns()
    for name, evs in pats.items():
        for k, n, rows in evs:
            assert n == 0 or LOWEST <= n <= HIGHEST, (name, n)
    for name, prio, instr, n, ticks in EFFECTS:
        _, levels, pitches, _, _ = INSTRUMENTS[INSTR[instr]]
        steps = [p for p in pitches if p not in (LOOP, HOLD)]
        assert all(LOWEST <= note(n) + p <= HIGHEST for p in steps), name
        assert ticks == len(levels), (name, ticks, len(levels))
    used = {name for step in SONG for name in step}
    assert used == set(pats), set(pats) ^ used
    for name, levels, pitches, mix, noisep in INSTRUMENTS:
        assert pitches[-1] in (LOOP, HOLD) and all(0 <= v <= 15 for v in levels), name
        assert all(-64 < p < 64 for p in pitches[:-1]), name
    for k, (n, p) in enumerate((n, period(n)) for n in range(LOWEST, HIGHEST + 1)):
        assert 1 <= p <= 4095, (n, p)
    return True


if __name__ == "__main__":
    check()
    s = sizes()
    print(s, "in all", sum(s.values()))
    print(f"{BARS} bars, {TICKS} ticks, {TICKS * 71364 / CLOCK:.3f} s at the 50 Hz machine's rate")
    print("periods:", period(note("C1")), period(note("A4")), period(note("B7")))
