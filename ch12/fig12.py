#!/usr/bin/env python3
"""fig12.py - the figure of chapter 12, cropped from the capture.

Crops are whole 8 x 8 character cells of the paper; enlargement is by a whole
number, nearest neighbour, to at least 300 dpi at the printed width. Nothing
is added. Every pixel was drawn by the MSX, in black ink on white paper.
"""
import math
import os
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
sys.path.insert(0, HERE)
import meas  # noqa: E402
import gen12  # noqa: E402
import meas12  # noqa: E402

CAP = os.path.join(HERE, "captures")
MIN_DPI = 300
WIDTH = {"fig12_1": 8.0}            # chapter12.py uses the same number


def paper(name, col0, row0, col1, row1):
    """the paper of a capture from cell (col0, row0) up to, not including,
    cell (col1, row1)"""
    x0, y0 = meas.paper(8 * col0, 8 * row0)
    im = Image.open(os.path.join(CAP, name)).convert("RGB")
    return im.crop((x0, y0, x0 + 8 * (col1 - col0), y0 + 8 * (row1 - row0)))


def enlarge(im, width_cm):
    f = math.ceil(MIN_DPI * width_cm / 2.54 / im.width)
    return im.resize((im.width * f, im.height * f), Image.NEAREST), f


def main():
    made = {
        # 12.1 - fill: the whole paper, every cell of the screen
        "fig12_1": paper(f"fill_f{meas12.FILL_FRAME:04d}.png", 0, 0, gen12.W, gen12.H),
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
