#!/usr/bin/env python3
"""fig26.py - the figures of chapter 26, from the captures.

Parts of captures, set side by side or one above another, and enlarged by a
whole number, nearest neighbour, to at least 300 dpi at the printed width.
Nothing is added but the white between two panels. Every capture is a frame
meas26.py checked against the model, on the 50 Hz machine.
"""
import json
import math
import os
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
import meas  # noqa: E402
import gen26  # noqa: E402

CAP = os.path.join(HERE, "captures")
MIN_DPI = 300
WIDTH = {"fig26_1": 6.0, "fig26_2": 11.0, "fig26_3": 10.0, "fig26_4": 8.0, "fig26_5": 10.0,
         "fig26_6": 9.0, "fig26_7": 8.0, "fig26_8": 11.0, "fig26_9": 10.0, "fig26_10": 12.0}
GAP = 16
ONE = (104, 80, 144, 104)               # figure 26.1: x0, y0, x1, y1 of the paper
SIZES = (0, 78, 256, 113)               # figure 26.2: each state
ORDER = (24, 32, 232, 140)              # figure 26.5
FALL = (0, 56, 256, 80)                 # figure 26.10: the four figures
TEAR = (48, 72, 208, 120)               # figure 26.9: the block, torn
MODES = (0, 78, 256, 98)                # figure 26.6: the four sprites, in each mode
MARCH = (0, 0, 128, 54)                 # figure 26.8: the top left figures
ENTER = (0, 84, 40, 108)                # figure 26.3: the left edge
ENTER_AT = (-12, -4, 0)                 # ... with the block at these x


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
    m = json.load(open(os.path.join(HERE, "meas26.json")))
    lost = m["fall"]["fall"]["eu"]["lost_frames"][0]
    c0 = m["columns"]["eu"]["frames"][0]
    assert m["columns"]["eu"]["consecutive"]
    made = {
        # 26.1 - one.rom: the sprite and the paper round it
        "fig26_1": paper(frame("one", m["one"]["eu"]["shot"]), ONE),
        # 26.2 - sizes.rom: the four sizes, one above another
        "fig26_2": stacked([paper(frame("sizes", k), SIZES) for k in m["sizes"]["eu"]["frames"]]),
        # 26.3 - columns.rom: the block coming in at the left edge
        "fig26_3": side_by_side([paper(frame("columns", c0 + 32 + x), ENTER) for x in ENTER_AT]),
        # 26.4 - edges.rom: all of the picture, the border light green
        "fig26_4": frame("edges", m["edges"]["eu"]["shot"]).crop(
            (meas.DRAWN[0], 0, meas.DRAWN[1] + 1, 240)),
        # 26.5 - order.rom
        "fig26_5": paper(frame("order", m["order"]["eu"]["shot"]), ORDER),
        # 26.6 - modes.rom: Graphic II, Graphic I, multicolour and text, from the top
        "fig26_6": stacked([paper(frame("modes", k), MODES) for k in m["modes"]["eu"]["frames"]]),
        # 26.7 - herd.rom: its last frame
        "fig26_7": paper(frame("herd", m["herd"]["herd"]["eu"]["frames"][1]), (0, 0, 256, 192)),
        # 26.8 - march.rom: R#6 at 7 (left) and at 3 (right)
        "fig26_8": side_by_side([paper(frame("march", m["march"]["eu"]["frames"][k]), MARCH)
                                 for k in (1, 0)]),
        # 26.9 - tear.rom: its first new X
        "fig26_9": paper(frame("tear", m["tear"]["eu"]["frames"][0]), TEAR),
        # 26.10 - fall.rom: the frames before, at and after Y = 208
        "fig26_10": stacked([paper(frame("fall", k), FALL) for k in (lost - 1, lost, lost + 1)]),
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
