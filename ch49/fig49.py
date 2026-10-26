#!/usr/bin/env python3
"""fig49.py - the figures of chapter 49, from the recordings.

49.1 and 49.3 are pieces of recordings that meas49.py cut and checked
against psg36.py, as chapter 36's figures were: each panel is a channel's
samples, or the three channels added up, the time across and the level
upward, a black line through them, in a light grey frame whose top is the
highest level the panel can hold (32,767 a channel, 98,301 for three) and
whose bottom is 0. 49.2 is the whole of the sounds the same way, each
column the lowest and the highest level of its slice of the recording,
which meas49.py worked out. 49.4 is how strong each frequency is in the vowel's middle 0.4
seconds, which meas49.py worked out from the recordings: 0 to 12,000 Hz
across, in slices of 40 Hz, and upward the strongest component of each, from
the strongest of all at the top to 80 dB below it at the bottom. 49.5 is
the T-states from each sample's writes to the next sample's, as the debugger logged them: a dot for each sample
that writes, the sample's number across and the T-states upward, from 0 at
the bottom to 1,200 at the top, where the few gaps longer than that are
drawn. A panel is drawn a third of its printed size, a pixel to a column,
and enlarged three times; nothing is smoothed. All are of the 60 Hz
machine, whose recordings are the 50 Hz machine's, sample for sample.

    fig49_1  four samples of the hi-hat in three.rom: channels A, B and C, and
             their sum
    fig49_2  the whole of the sounds: one.rom, and three.rom
    fig49_3  the kick's first 25 milliseconds and the vowel, two of its periods:
             one.rom's channel A, and three.rom's three channels added up
    fig49_4  the vowel's frequencies: one.rom, and three.rom
    fig49_5  the ramp and the kick, the first 1,346 samples: three.rom, and skip.rom
"""
import json
import math
import os
import sys
import wave

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))

CAP = os.path.join(HERE, "captures")
MIN_DPI = 300
WIDTH = {"fig49_1": 12.4, "fig49_2": 12.4, "fig49_3": 12.4, "fig49_4": 12.4, "fig49_5": 12.4}
DB_FLOOR = -80                      # figure 49.4: the bottom of a frequency panel's frame, in dB
GAP = 16
SCALE = 3                           # a plot is drawn at a third and enlarged three times
INK, FRAME, PAPER = 0, 192, 255     # black, the light grey of the frames, white
ONE_TOP = 32767
THREE_TOP = 3 * 32767
GAPS_TOP = 1200


def samples(name):
    w = wave.open(os.path.join(CAP, name))
    return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(int)


def frame(width, height):
    im = Image.new("L", (width, height), PAPER)
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, width - 1, height - 1), outline=FRAME)
    return im, d


def trace(x, top, width, height):
    """the samples X as a line, WIDTH columns by HEIGHT rows, in its frame"""
    im, d = frame(width, height)
    n = len(x)

    def row(v):
        return 1 + round((height - 3) * (1 - v / top))
    last = None
    for col in range(1, width - 1):
        a = (col - 1) * n // (width - 2)
        b = max(a + 1, col * n // (width - 2))
        seg = list(x[a:b]) + ([last] if last is not None else [])
        d.line((col, row(max(seg)), col, row(min(seg))), fill=INK)
        last = x[b - 1]
    return im


def bands(slices, top, width, height):
    """(lowest, highest) slices as columns: each column the slices it covers"""
    im, d = frame(width, height)
    n = len(slices)

    def row(v):
        return 1 + round((height - 3) * (1 - v / top))
    for col in range(1, width - 1):
        a = (col - 1) * n // (width - 2)
        b = max(a + 1, col * n // (width - 2))
        lo = min(s[0] for s in slices[a:b])
        hi = max(s[1] for s in slices[a:b])
        d.line((col, row(hi), col, row(lo)), fill=INK)
    return im


def freqs(bins, width, height):
    """strengths, a dB a bin, 0 at the top and DB_FLOOR at the bottom, a line"""
    im, d = frame(width, height)
    n = len(bins)

    def row(v):
        return 1 + round((height - 3) * max(v, DB_FLOOR) / DB_FLOOR)
    last = None
    for col in range(1, width - 1):
        a = (col - 1) * n // (width - 2)
        b = max(a + 1, col * n // (width - 2))
        seg = bins[a:b] + ([last] if last is not None else [])
        d.line((col, row(max(seg)), col, row(min(seg))), fill=INK)
        last = bins[b - 1]
    return im


def dots(points, upto, top, width, height):
    """(sample, T-states) as dots"""
    im, d = frame(width, height)
    for k, g in points:
        col = 1 + round((width - 3) * k / upto)
        row = 1 + round((height - 3) * (1 - min(g, top) / top))
        d.point((col, row), fill=INK)
    return im


def side(panels, gap=GAP // SCALE + 2):
    out = Image.new("L", (sum(p.width for p in panels) + gap * (len(panels) - 1),
                          max(p.height for p in panels)), PAPER)
    x = 0
    for p in panels:
        out.paste(p, (x, 0))
        x += p.width + gap
    return out


def stack(panels, gap=GAP // SCALE + 2):
    w = max(p.width for p in panels)
    out = Image.new("L", (w, sum(p.height for p in panels) + gap * (len(panels) - 1)), PAPER)
    y = 0
    for p in panels:
        out.paste(p, (0, y))
        y += p.height + gap
    return out


def finish(im):
    return im.resize((im.width * SCALE, im.height * SCALE), Image.NEAREST).convert("RGB")


def main():
    m = json.load(open(os.path.join(HERE, "meas49.json")))["pieces"]["jp"]
    w = math.ceil(MIN_DPI * WIDTH["fig49_1"] / 2.54 / SCALE)
    one = samples(m["vowel_one"][0])
    three = sum(samples(p) for p in m["vowel_three"])
    hat = [samples(p) for p in m["hat_three"]]
    k_one = samples(m["kick_one"][0])
    k_three = sum(samples(p) for p in m["kick_three"])
    hw = (w - (GAP // SCALE + 2)) // 2
    upto = 1346
    made = {
        "fig49_1": finish(stack([trace(h, ONE_TOP, w, 26) for h in hat] +
                                [trace(sum(hat), THREE_TOP, w, 60)])),
        "fig49_2": finish(stack([bands(m["whole_one"], ONE_TOP, w, 50),
                                 bands(m["whole_three"], THREE_TOP, w, 50)])),
        "fig49_3": finish(stack([side([trace(k_one, ONE_TOP, hw, 44), trace(one, ONE_TOP, hw, 44)]),
                                 side([trace(k_three, THREE_TOP, hw, 44), trace(three, THREE_TOP, hw, 44)])])),
        "fig49_4": finish(stack([freqs(m["freqs_one"], w, 50), freqs(m["freqs_three"], w, 50)])),
        "fig49_5": finish(stack([dots(m["gaps_three"], upto, GAPS_TOP, w, 48),
                                 dots(m["gaps_skip"], upto, GAPS_TOP, w, 48)])),
    }
    out = {}
    for name, im in made.items():
        path = os.path.join(HERE, f"{name}.png")
        im.save(path)
        out[name] = (path, WIDTH[name], SCALE, im.size)
    return out


if __name__ == "__main__":
    for name, (path, w, k, size) in main().items():
        print(f"{name}: x{k} -> {size[0]} x {size[1]} px, {w} cm, {size[0] / (w / 2.54):.0f} dpi")
