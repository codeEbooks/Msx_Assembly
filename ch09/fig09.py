#!/usr/bin/env python3
"""fig09.py - the figures of chapter 9, cropped from the captures.

Crops are whole 8 x 8 character cells of the paper; enlargement is by a whole
number, nearest neighbour, to at least 300 dpi at the printed width. Nothing
is added. The digits were drawn by the MSX, in black ink on white paper.
"""
import math
import os
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
sys.path.insert(0, HERE)
import meas  # noqa: E402
import gen09  # noqa: E402

CAP = os.path.join(HERE, "captures")
MIN_DPI = 300
WIDTH = {"fig09_1": 12.0, "fig09_2": 9.0}      # chapter09.py uses the same numbers


def paper(name, col0, row0, cols, rows):
    x0, y0 = meas.paper(8 * col0, 8 * row0)
    im = Image.open(os.path.join(CAP, name)).convert("RGB")
    return im.crop((x0, y0, x0 + 8 * cols, y0 + 8 * rows))


def enlarge(im, width_cm):
    f = math.ceil(MIN_DPI * width_cm / 2.54 / im.width)
    return im.resize((im.width * f, im.height * f), Image.NEAREST), f


def main():
    last = gen09.SUM_ROW0 + gen09.SUM_STEP * (len(gen09.SUMS32) - 1)
    rows = gen09.SCORE_ROW0 + gen09.FRAMES
    made = {
        # 9.1 - add32: the first line to the last, all 30 columns used
        "fig09_1": paper("add32_f0010.png", 0, gen09.SUM_ROW0, gen09.CARRY_COL + 3,
                         last - gen09.SUM_ROW0 + 1),
        # 9.2 - score: the headings (row 0) to the last score, columns 0-23
        "fig09_2": paper(f"score_f{gen09.FRAMES + 15:04d}.png", 0, 0, gen09.COL_DEC + 7, rows),
    }
    out = {}
    for name, im in made.items():
        big, f = enlarge(im, WIDTH[name])
        path = os.path.join(HERE, f"{name}.png")
        big.save(path)
        out[name] = (path, WIDTH[name], f, big.size)
    return out


if __name__ == "__main__":
    for name, (path, w, f, size) in main().items():
        print(f"{name}: x{f} -> {size[0]} x {size[1]} px, {w} cm, {size[0] / (w / 2.54):.0f} dpi")
