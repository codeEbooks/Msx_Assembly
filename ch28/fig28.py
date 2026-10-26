#!/usr/bin/env python3
"""fig28.py - the figures of chapter 28, from the captures.

Parts of captures, set side by side or one above another, and enlarged by a
whole number, nearest neighbour, to at least 300 dpi at the printed width.
Nothing is added but the white between two panels. Every capture is a frame
meas28.py checked against the model, on the 50 Hz machine.
"""
import json
import math
import os
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
import meas  # noqa: E402

CAP = os.path.join(HERE, "captures")
MIN_DPI = 300
WIDTH = {"fig28_1": 12.0, "fig28_2": 6.0, "fig28_3": 12.0, "fig28_4": 12.0, "fig28_5": 12.0,
         "fig28_6": 8.0}
GAP = 16
SHIFTS = (16, 12, 216, 36)              # figure 28.1: x0, y0, x1, y1 of the paper
EDGE = ((232, 96, 256, 120), (0, 96, 24, 120))  # figure 28.2: the right edge, the left
COLOURS = (40, 0, 136, 64)              # figure 28.3: each panel
WALK = (32, 24, 96, 72)                 # figure 28.4: each frame ...
WALK_AT = (24, 34, 50)                  # ... after these steps
SWARM = (8, 8, 248, 36)                 # figure 28.5
SWARM_AT = 24
CROSS = (88, 16, 120, 32)               # figure 28.6: each panel ...
CROSS_AT = (42, 44)                     # ... after these steps


def side_by_side(panels):
    w = sum(p.width for p in panels) + GAP * (len(panels) - 1)
    out = Image.new("RGB", (w, max(p.height for p in panels)), (255, 255, 255))
    x = 0
    for p in panels:
        out.paste(p, (x, 0))
        x += p.width + GAP
    return out


def stacked(panels):
    h = sum(p.height for p in panels) + GAP * (len(panels) - 1)
    out = Image.new("RGB", (max(p.width for p in panels), h), (255, 255, 255))
    y = 0
    for p in panels:
        out.paste(p, (0, y))
        y += p.height + GAP
    return out


def enlarge(im, width_cm):
    f = math.ceil(MIN_DPI * width_cm / 2.54 / im.width)
    return im.resize((im.width * f, im.height * f), Image.NEAREST), f


def frame(name, k):
    return Image.open(os.path.join(CAP, f"{name}_eu_f{k:04d}.png")).convert("RGB")


def paper(im, box):
    x0, y0 = meas.paper(0, 0)
    return im.crop((x0 + box[0], y0 + box[1], x0 + box[2], y0 + box[3]))


def main():
    m = json.load(open(os.path.join(HERE, "meas28.json")))
    wf, sf = m["walk"]["eu"]["frames"], m["swarm"]["eu"]["frames"]
    of, kf = m["cross"]["overlap"]["eu"]["frames"], m["cross"]["stack"]["eu"]["frames"]
    made = {
        # 28.1 - shifts.rom: the eight bugs
        "fig28_1": paper(frame("shifts", m["shifts"]["eu"]["shot"]), SHIFTS),
        # 28.2 - edge.rom: the right edge and the left
        "fig28_2": side_by_side([paper(frame("edge", m["edge"]["eu"]["shot"]), b) for b in EDGE]),
        # 28.3 - under.rom (left) and paint.rom (right)
        "fig28_3": side_by_side([paper(frame(n, m["colours"][n]["eu"]["shot"]), COLOURS)
                                 for n in ("under", "paint")]),
        # 28.4 - walk.rom: three frames
        "fig28_4": side_by_side([paper(frame("walk", wf[k]), WALK) for k in WALK_AT]),
        # 28.5 - swarm.rom: one frame
        "fig28_5": paper(frame("swarm", sf[SWARM_AT]), SWARM),
        # 28.6 - overlap.rom (above) and stack.rom (below), two frames each
        "fig28_6": stacked([side_by_side([paper(frame(n, fr[k]), CROSS) for k in CROSS_AT])
                            for n, fr in (("overlap", of), ("stack", kf))]),
    }
    out = {}
    for name, im in made.items():
        big, f = enlarge(im, WIDTH[name])
        path = os.path.join(HERE, f"{name}.png")
        big.save(path)
        out[name] = (path, WIDTH[name], f, big.size)
    return out


if __name__ == "__main__":
    for name, (path, w, k, size) in main().items():
        print(f"{name}: x{k} -> {size[0]} x {size[1]} px, {w} cm, {size[0] / (w / 2.54):.0f} dpi")
