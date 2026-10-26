#!/usr/bin/env python3
"""psg36.py -- chapter 36's model of the PSG, as openMSX makes it heard.

openMSX records each of the PSG's three channels on its own, one sample
every 16 T-states (223,721.6 a second, the chip's clock divided by 8), and
a sample is a number: 0, or one of the levels below. This model works out
every sample of every channel from the register writes alone, each write
at the T-state the debugger logged for it; meas36.py compares it with the
recordings, sample by sample, and takes the rules out one at a time.

    python3 psg36.py        the levels and the envelope's shapes
"""
CLOCK = 3579545                 # the processor's T-states in a second
SAMPLE_T = 16                   # T-states from one sample to the next
FIRST = 6                       # T-states to a recording's first sample
SEED = 0x08A4                   # the noise register as a recording starts

# the envelope's 32 levels, 1.5 dB apart, 0 silent (env.asm); a channel's
# own volume v is the envelope's level 2v + 1 (levels.asm)
LEVELS = [0] + [min(32767, round(32768 * 2 ** ((e - 31) / 4)))
                 for e in range(1, 32)]
VOLUME = [0] + [LEVELS[2 * v + 1] for v in range(1, 16)]


def envelope(shape, n):
    """the envelope's level, 0 to 31, n steps after R13 = SHAPE was written"""
    attack, hold, alt, cont = shape & 4, shape & 1, shape & 2, shape & 8
    if n < 32:
        return n if attack else 31 - n
    if not cont:
        return 0
    if hold:
        return 31 if bool(attack) != bool(alt) else 0
    up = bool(attack) != bool(alt and n // 32 % 2)
    return n % 32 if up else 31 - n % 32


class PSG:
    """the chip from the moment a recording starts: every count at 0,
    every tone low, the noise register at SEED"""

    def __init__(self, regs, kind="YM2149"):
        self.r = list(regs)
        self.kind = kind
        self.count, self.high = [0, 0, 0], [0, 0, 0]
        self.ncount, self.noise = 0, SEED
        self.ecount, self.estep = 0, 0

    def period(self, c):                # a period of 0 counts as 1
        return max(1, self.r[2 * c] | (self.r[2 * c + 1] & 15) << 8)

    def nperiod(self):                  # the noise moves at half the rate
        return 2 * max(1, self.r[6] & 31)

    def eperiod(self):
        return max(1, self.r[11] | self.r[12] << 8)

    def write(self, reg, value):
        self.r[reg] = value
        if reg == 13:                   # R13 starts the envelope again, always
            self.ecount = self.estep = 0
        for c in range(3):              # a count past a new period stops short
            self.count[c] = min(self.count[c], self.period(c) - 1)
        self.ncount = min(self.ncount, self.nperiod() - 1)
        self.ecount = min(self.ecount, self.eperiod() - 1)

    def level(self):
        e = envelope(self.r[13], self.estep)
        if self.kind == "AY8910":       # sixteen levels, each held two steps
            return VOLUME[e >> 1]
        return LEVELS[e]

    def sample(self):
        """the three channels' samples now; then a sample's time goes by"""
        r, out = self.r, []
        for c in range(3):
            v = r[8 + c]
            heard = self.level() if v & 16 else VOLUME[v & 15]
            tone = self.high[c] or r[7] >> c & 1
            noise = self.noise & 1 or r[7] >> (c + 3) & 1
            out.append(heard if tone and noise else 0)
        self.move()
        return out

    def move(self):
        for c in range(3):              # a shut tone's count goes on
            self.count[c] += 1
            if self.count[c] >= self.period(c):
                self.count[c] = 0
                self.high[c] ^= 1
        self.ncount += 1
        if self.ncount >= self.nperiod():
            self.ncount = 0             # 17 bits: bit 0 XOR bit 3 in at the top
            n = self.noise
            self.noise = n >> 1 | ((n ^ n >> 3) & 1) << 16
        self.ecount += 1
        if self.ecount >= self.eperiod():
            self.ecount = 0
            self.estep += 1
            if self.estep == 96:        # after the first ramp, 64 steps repeat
                self.estep = 32


def run(writes, start, n, kind="YM2149", chip=PSG):
    """WRITES: (T-state, register, byte), T-states from power-on; START: the
    T-state the recording starts at -> the three channels' first N samples"""
    writes = sorted(writes)
    regs, k = [0] * 16, 0
    while k < len(writes) and writes[k][0] <= start:
        regs[writes[k][1]] = writes[k][2]
        k += 1
    psg = chip(regs, kind)
    out = [[], [], []]
    for j in range(n):
        t = start + FIRST + SAMPLE_T * j    # a write counts from this sample on
        while k < len(writes) and writes[k][0] <= t:
            psg.write(writes[k][1], writes[k][2])
            k += 1
        for c, v in enumerate(psg.sample()):
            out[c].append(v)
    return out


if __name__ == "__main__":
    print("the envelope's levels:", LEVELS)
    print("the volumes:", VOLUME)
    steps = "0123456789ABCDEFGHIJKLMNOPQRSTUV"
    for s in range(16):
        line = "".join(steps[envelope(s, n)] for n in range(96))
        print(f"R13 = {s:2}:", line)
