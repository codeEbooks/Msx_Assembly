#!/usr/bin/env python3
"""fig07.py - the figure of chapter 7, cropped from the capture.

The crop is whole 8 x 8 character cells of the paper, from the headings to the
last line; enlargement is by a whole number, nearest neighbour, to at least
300 dpi at the printed width. Nothing is added. The digits and the boxes were
drawn by the MSX, in black ink on white paper.
"""
import math
import os
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
sys.path.insert(0, HERE)
import meas  # noqa: E402
import gen07  # noqa: E402

CAP = os.path.join(HERE, "captures")
MIN_DPI = 300
WIDTH = {"fig07_1": 10.5}           # chapter07.py uses the same numbers


def paper(name, col0, row0, cols, rows):
    x0, y0 = meas.paper(8 * col0, 8 * row0)
    im = Image.open(os.path.join(CAP, name)).convert("RGB")
    return im.crop((x0, y0, x0 + 8 * cols, y0 + 8 * rows))


def enlarge(im, width_cm):
    f = math.ceil(MIN_DPI * width_cm / 2.54 / im.width)
    return im.resize((im.width * f, im.height * f), Image.NEAREST), f


def main():
    first = gen07.FLAG_ROW0 - 2                                  # the headings
    last = gen07.FLAG_ROW0 + gen07.FLAG_STEP * (len(gen07.FLAGS) - 1)
    # 7.1 - flags.rom: the headings to the last line, column 0 to the F column
    made = {"fig07_1": paper("flags_f0010.png", 0, first, gen07.FLAG_COLS["F"] + 2,
                             last - first + 1)}
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
