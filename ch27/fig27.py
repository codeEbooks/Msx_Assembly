#!/usr/bin/env python3
"""fig27.py - the figures of chapter 27, from the captures.

Parts of captures, set one above another, and enlarged by a whole number,
nearest neighbour, to at least 300 dpi at the printed width. Nothing is added
but the white between two panels. Every capture is a frame meas27.py checked
against the model, on the 50 Hz machine.
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
WIDTH = {"fig27_1": 11.0, "fig27_2": 8.0, "fig27_3": 12.0, "fig27_4": 12.0, "fig27_5": 12.0}
GAP = 16
FIVE = (16, 76, 240, 108)               # figure 27.1: x0, y0, x1, y1 of the paper
LAYERS = (32, 84, 192, 156)             # figure 27.2
STAGGER = (0, 76, 248, 116)             # figure 27.3
ROTATE = (0, 84, 244, 108)              # figure 27.4: each frame
SIX = (8, 84, 240, 108)                 # figure 27.5: each frame
KEEP_FRAMES = 3                         # figure 27.5: keep.rom's frames, after poll.rom's one


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
    m = json.load(open(os.path.join(HERE, "meas27.json")))
    r0 = m["rotate"]["eu"]["frames"][0]
    p0 = m["adaptive"]["poll"]["eu"]["film"][0]
    k0 = m["adaptive"]["keep"]["eu"]["film"][0]
    made = {
        # 27.1 - five.rom, then first.rom: the ball last, then first
        "fig27_1": stacked([paper(frame("five", m["five"]["eu"]["shot"]), FIVE),
                            paper(frame("first", m["five"]["first"]["eu"]["shot"]), FIVE)]),
        # 27.2 - layers.rom
        "fig27_2": paper(frame("layers", m["layers"]["eu"]["shot"]), LAYERS),
        # 27.3 - stagger.rom
        "fig27_3": paper(frame("stagger", m["stagger"]["eu"]["shot"]), STAGGER),
        # 27.4 - rotate.rom: its first two turned frames
        "fig27_4": stacked([paper(frame("rotate", r0 + k), ROTATE) for k in (0, 1)]),
        # 27.5 - poll.rom's first frame, then keep.rom's first three
        "fig27_5": stacked([paper(frame("poll", p0), SIX)] +
                           [paper(frame("keep", k0 + k), SIX) for k in range(KEEP_FRAMES)]),
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
