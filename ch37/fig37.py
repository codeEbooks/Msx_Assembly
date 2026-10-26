#!/usr/bin/env python3
"""fig37.py - the figures of chapter 37, from the recordings and the captures.

37.1, 37.2, 37.4 and 37.5 are pieces of recordings that meas37.py cut and
checked against chapter 36's psg36.py: each panel is a channel's samples,
the time across and the sample upward, a black line through them, in a light
grey frame whose top is 32,767 and whose bottom is 0. A panel is drawn a
third of its printed size, a pixel to a column, and enlarged three times;
nothing is smoothed. 37.3 is three captures, side by side, enlarged by a
whole number, nearest neighbour, to at least 300 dpi at the printed width.
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
import meas  # noqa: E402

CAP = os.path.join(HERE, "captures")
MIN_DPI = 300
WIDTH = {"fig37_1": 12.0, "fig37_2": 12.0, "fig37_3": 12.0, "fig37_4": 12.0, "fig37_5": 12.0}
GAP = 16
SCALE = 3                           # a plot is drawn at a third and enlarged three times
INK, FRAME, PAPER = 0, 192, 255     # black, the light grey of the frames, white
TOP = 32767
SCREEN = (0, 8, 176, 72)            # figure 37.3: text rows 1 to 8, columns 0 to 21


def side_by_side(panels, gap=GAP):
    w = sum(p.width for p in panels) + gap * (len(panels) - 1)
    out = Image.new("RGB", (w, max(p.height for p in panels)), (255, 255, 255))
    x = 0
    for p in panels:
        out.paste(p, (x, 0))
        x += p.width + gap
    return out


def enlarge(im, width_cm):
    f = math.ceil(MIN_DPI * width_cm / 2.54 / im.width)
    return im.resize((im.width * f, im.height * f), Image.NEAREST), f


def paper(name, k, box):
    im = Image.open(os.path.join(CAP, f"{name}_f{k:04d}.png")).convert("RGB")
    x0, y0, x1, y1 = box
    return im.crop((meas.PAPER_X0 + x0, meas.PAPER_Y0 + y0, meas.PAPER_X0 + x1, meas.PAPER_Y0 + y1))


def samples(name):
    w = wave.open(os.path.join(CAP, name))
    return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(int)


def trace(x, width, height):
    """the samples X as a line, WIDTH columns by HEIGHT rows, in its frame"""
    im = Image.new("L", (width, height), PAPER)
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, width - 1, height - 1), outline=FRAME)
    n = len(x)

    def row(v):
        return 1 + round((height - 3) * (1 - v / TOP))
    last = None
    for col in range(1, width - 1):
        a = (col - 1) * n // (width - 2)
        b = max(a + 1, col * n // (width - 2))
        seg = x[a:b].tolist() + ([last] if last is not None else [])
        d.line((col, row(max(seg)), col, row(min(seg))), fill=INK)
        last = x[b - 1]
    return im


def side_by_side_l(panels, gap):
    w = sum(p.width for p in panels) + gap * (len(panels) - 1)
    out = Image.new("L", (w, max(p.height for p in panels)), PAPER)
    x = 0
    for p in panels:
        out.paste(p, (x, 0))
        x += p.width + gap
    return out


def stack(rows, gap):
    lines = [side_by_side_l(r, gap) for r in rows]
    w = max(l.width for l in lines)
    out = Image.new("L", (w, sum(l.height for l in lines) + gap * (len(lines) - 1)), PAPER)
    y = 0
    for l in lines:
        out.paste(l, (0, y))
        y += l.height + gap
    return out


def plot(rows, width_cm, height):
    """ROWS of pieces' names: each row's panels share its width"""
    full = math.ceil(MIN_DPI * width_cm / 2.54 / SCALE)
    gap = GAP // SCALE + 2
    panels = []
    for r in rows:
        w = (full - gap * (len(r) - 1)) // len(r)
        panels.append([trace(samples(p), w, height) for p in r])
    im = stack(panels, gap)
    return im.resize((im.width * SCALE, im.height * SCALE), Image.NEAREST).convert("RGB")


def main():
    m = json.load(open(os.path.join(HERE, "meas37.json")))
    p, ph = m["pieces"], m["photos"]
    made = {
        # 37.1 - the first bar, channel by channel; below, the kick and the snare close up
        "fig37_1": (plot([[n] for n in p["bar"]] + [[p["kick"], p["snare"]]], WIDTH["fig37_1"], 30), SCALE),
        # 37.2 - channel C: the tune alone, and effects.asm's COIN and BOOM over it
        "fig37_2": (plot([[n] for n in p["fx"]], WIDTH["fig37_2"], 40), SCALE),
        # 37.3 - thirteen seconds in: tune.asm at 50 Hz and at 60 Hz, fast.asm at 60 Hz
        "fig37_3": enlarge(side_by_side([paper(f"{name}_{tag}", ph[f"{name}_{tag}"]["at"], SCREEN)
                                         for name, tag in (("tune", "eu"), ("tune", "jp"), ("fast", "jp"))]),
                           WIDTH["fig37_3"]),
        # 37.4 - channel A, the first five seconds: tune.asm at 50 and 60 Hz, fast.asm at 60 Hz
        "fig37_4": (plot([[n] for n in p["hz"]], WIDTH["fig37_4"], 30), SCALE),
        # 37.5 - channel C: tune.asm and latch.asm, the first sixty ticks; a burst close up
        "fig37_5": (plot([[n] for n in p["latch"]] + [[p["burst"]]], WIDTH["fig37_5"], 30), SCALE),
    }
    out = {}
    for name, (im, f) in made.items():
        path = os.path.join(HERE, f"{name}.png")
        im.save(path)
        out[name] = (path, WIDTH[name], f, im.size)
    return out


if __name__ == "__main__":
    for name, (path, w, k, size) in main().items():
        print(f"{name}: x{k} -> {size[0]} x {size[1]} px, {w} cm, {size[0] / (w / 2.54):.0f} dpi")
