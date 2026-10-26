#!/usr/bin/env python3
"""player37.py -- chapter 37's player, in Python, reading a cartridge's bytes.

It keeps what the Z80 player keeps, the ticks, the row's count, the song's
step, shadow and the four channels, and reads the music where play reads
it: the notes, the instruments and their tables, the effects, the song and
its patterns, from the .rom, at the addresses of the .sym. Nothing in it
comes from music37.py, so meas37.py can hold the two against each other.

    p = Player("ch37/tune")     the cartridge, as INIT leaves it
    p.play()                    one tick: shadow, as the next tick sends it
    p.sfx(effect)               an effect asked for: False if refused

    python3 player37.py ch37/tune   the first ticks' shadow
"""
import sys
from pathlib import Path

MIXER_OFF = 0xBF
END, LOOP, HOLD = 0xFF, 0x80, 0x81
SPEED = None                    # read from the .sym: the EQU is there
FIELDS = ["WAITS", "NOTE", "INSTR", "PATTERN", "VOLUME", "PITCHES", "FIRST", "MIXER",
          "NOISEP", "SHPER", "SHLEV", "TMASK", "NMASK", "PRIO"]
WORDS = {"PATTERN", "VOLUME", "PITCHES", "FIRST", "SHPER", "SHLEV"}


def symbols(path):
    out = {}
    for line in Path(path).read_text().splitlines():
        name, _, value = line.partition(": EQU ")
        if value:
            out[name.strip()] = int(value.split()[0], 16)
    return out


def s8(v):
    return v - 256 if v & 128 else v


class Player:
    def __init__(self, stem):
        stem = Path(stem)
        self.sym = symbols(stem.with_suffix(".sym"))
        self.mem = bytearray(65536)
        rom = stem.with_suffix(".rom").read_bytes()
        self.mem[0x4000:0x4000 + len(rom)] = rom
        s = self.sym
        self.speed = s["SPEED"]
        self.ticks, self.tick, self.barno, self.rowno = 0, 1, 0, 0
        self.step = s["song"] - 6
        # INIT copies shadow and the four channels from start
        at = s["start"]
        self.shadow = list(self.mem[at:at + 11])
        at += 11
        self.chans = []
        for _ in range(4):
            ch = {}
            for f in FIELDS:
                if f in WORDS:
                    ch[f] = self.word(at)
                    at += 2
                else:
                    ch[f] = self.mem[at]
                    at += 1
            self.chans.append(ch)
        self.shadow_at = s["shadow"]

    def word(self, a):
        return self.mem[a] | self.mem[a + 1] << 8

    # -------------------------------------------------------- the player
    def play(self):
        """one tick: shadow worked out for the next tick to send"""
        self.ticks = (self.ticks + 1) & 0xFFFF
        self.tick = (self.tick - 1) & 255
        if self.tick == 0:
            self.tick = self.speed
            self.rowno = (self.rowno + 1) & 255
            for ch in self.chans[:3]:
                self.row(ch)
        self.shadow[7] = MIXER_OFF
        for ch in self.chans[:3]:
            self.sound(ch)
        x = self.chans[3]
        if x["WAITS"]:
            x["WAITS"] -= 1
            self.shadow[7] |= 0b00100100
            self.sound(x)
        return list(self.shadow)

    def row(self, ch):
        ch["WAITS"] = (ch["WAITS"] - 1) & 255
        if ch["WAITS"]:
            return
        hl = ch["PATTERN"]
        a = self.mem[hl]
        hl += 1
        if a == END:
            hl = self.next(ch)
            a = self.mem[hl]
            hl += 1
        if a & 0x80:
            ch["INSTR"] = a & 0x7F
            a = self.mem[hl]
            hl += 1
        ch["NOTE"] = a
        ch["WAITS"] = self.mem[hl]
        hl += 1
        ch["PATTERN"] = hl
        self.voice(ch)

    def voice(self, ch):
        at = self.sym["instruments"] + 6 * ch["INSTR"]
        ch["VOLUME"] = self.word(at)
        ch["PITCHES"] = ch["FIRST"] = self.word(at + 2)
        ch["MIXER"] = self.mem[at + 4]
        ch["NOISEP"] = self.mem[at + 5]

    def next(self, ch):
        at = self.step + 6
        if self.word(at) == 0:
            at, self.barno = self.sym["song"], 0
        self.barno += 1
        self.step = at
        self.rowno = 0
        for k in range(3):
            self.chans[k]["PATTERN"] = self.word(at + 2 * k)
        return ch["PATTERN"]

    def put(self, at, v):
        self.shadow[at - self.shadow_at] = v

    def sound(self, ch):
        level = 0
        if ch["NOTE"]:
            v = self.mem[ch["VOLUME"]]
            if v == END:
                level = self.mem[ch["VOLUME"] - 1]
            else:
                level = v
                ch["VOLUME"] += 1
            p = self.mem[ch["PITCHES"]]
            if p == LOOP:
                ch["PITCHES"] = ch["FIRST"]
                p = self.mem[ch["PITCHES"]]
                ch["PITCHES"] += 1
            elif p == HOLD:
                p = self.mem[ch["PITCHES"] - 1]
            else:
                ch["PITCHES"] += 1
            n = (s8(p) + ch["NOTE"]) & 255
            per = self.word(self.sym["notes"] + 2 * n)
            self.put(ch["SHPER"], per & 255)
            self.put(ch["SHPER"] + 1, per >> 8)
        self.put(ch["SHLEV"], level)
        r7 = self.shadow[7]
        if ch["MIXER"] & 1:
            r7 &= ch["TMASK"]
        if ch["MIXER"] & 2:
            r7 &= ch["NMASK"]
            self.shadow[6] = ch["NOISEP"]
        self.shadow[7] = r7

    # -------------------------------------------------------- effects
    def sfx(self, effect):
        """True if the effect starts, False if the one sounding is higher"""
        at = self.sym["effects"] + 4 * effect
        prio, instr, note, ticks = self.mem[at:at + 4]
        x = self.chans[3]
        if x["WAITS"] and prio < x["PRIO"]:
            return False
        x["PRIO"], x["INSTR"], x["NOTE"], x["WAITS"] = prio, instr & 0x7F, note, ticks
        self.voice(x)
        return True


def run(stem, n, requests=()):
    """N ticks of the cartridge STEM: [the 11 bytes each tick sends], from the
    first, and the answers to REQUESTS, [(tick, effect)], each made once the
    player has counted its tick, as effects.asm's main program makes it"""
    p = Player(stem)
    sent, answers = [], []
    pending = list(requests)
    for _ in range(n):
        sent.append(list(p.shadow))
        p.play()
        while pending and p.ticks >= pending[0][0]:
            answers.append(p.sfx(pending.pop(0)[1]))
    return sent, answers, p


if __name__ == "__main__":
    sent, _, p = run(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).parent / "tune", 12)
    for k, s in enumerate(sent):
        print(k + 1, " ".join(f"{b:02X}" for b in s))
