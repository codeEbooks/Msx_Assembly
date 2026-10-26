#!/usr/bin/env python3
"""fig41.py - the figures of chapter 41, from the captures.

Parts of captures, set side by side or one under another, and enlarged by a
whole number, nearest neighbour, to at least 300 dpi at the printed width.
Nothing is added but the white between two panels. meas41.py checked every
capture against the picture the model gives, and kept the ones the figures
use; their names are in meas41.json.
"""
import json
import math
import os
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
sys.path.insert(0, HERE)
import meas  # noqa: E402
import gen41  # noqa: E402

CAP = os.path.join(HERE, "captures")
MIN_DPI = 300
WIDTH = {"fig41_1": 12.0, "fig41_2": 12.0, "fig41_3": 9.0, "fig41_4": 14.0}
GAP = 16
PAPER = (0, 0, 256, 192)
BAND = 8 * (gen41.STRIP + gen41.STRIP_GAP)
BANDS = [(0, gen41.LCG_TOP, 256, gen41.LCG_TOP + BAND), (0, gen41.RND_TOP, 256, gen41.RND_TOP + BAND)]


def enlarge(im, width_cm):
    f = math.ceil(MIN_DPI * width_cm / 2.54 / im.width)
    return im.resize((im.width * f, im.height * f), Image.NEAREST), f


def paper(png, box):
    im = Image.open(os.path.join(CAP, png)).convert("RGB")
    x0, y0, x1, y1 = box
    return im.crop((meas.PAPER_X0 + x0, meas.PAPER_Y0 + y0, meas.PAPER_X0 + x1, meas.PAPER_Y0 + y1))


def side_by_side(panels, gap=GAP):
    w = sum(p.width for p in panels) + gap * (len(panels) - 1)
    out = Image.new("RGB", (w, max(p.height for p in panels)), (255, 255, 255))
    x = 0
    for p in panels:
        out.paste(p, (x, 0))
        x += p.width + gap
    return out


def one_under(panels, gap=GAP):
    h = sum(p.height for p in panels) + gap * (len(panels) - 1)
    out = Image.new("RGB", (max(p.width for p in panels), h), (255, 255, 255))
    y = 0
    for p in panels:
        out.paste(p, (0, y))
        y += p.height + gap
    return out


def main():
    m = json.load(open(os.path.join(HERE, "meas41.json")))
    st = m["states"]["eu"]
    made = {
        # 41.1 - rreg.asm and lcg.asm: each number against the one before
        "fig41_1": side_by_side([paper(m["rreg"]["eu"]["photo"], PAPER), paper(m["lcg"]["eu"]["photo"], PAPER)]),
        # 41.2 - xorshift.asm on the way and at the end
        "fig41_2": side_by_side([paper(m["xorshift"]["eu"]["early"], PAPER),
                                 paper(m["xorshift"]["eu"]["photo"], PAPER)]),
        # 41.3 - bits.asm: the two bands
        "fig41_3": one_under([paper(m["bits"]["eu"]["photo"], b) for b in BANDS]),
        # 41.4 - states.asm: the title, and game over after each play
        "fig41_4": side_by_side([paper(st[k + "_photo"], PAPER) for k in ("title", "over1", "over2")]),
    }
    out = {}
    for name, im in made.items():
        big, k = enlarge(im, WIDTH[name])
        path = os.path.join(HERE, f"{name}.png")
        big.save(path)
        out[name] = (path, WIDTH[name], k, big.size)
    return out


if __name__ == "__main__":
    for name, (path, w, k, size) in main().items():
        print(f"{name}: x{k} -> {size[0]} x {size[1]} px, {w} cm, {size[0] / (w / 2.54):.0f} dpi")
