#!/usr/bin/env python3
"""fig10.py - the figures of chapter 10, cropped from the captures.

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
import gen10  # noqa: E402

CAP = os.path.join(HERE, "captures")
MIN_DPI = 300
WIDTH = {"fig10_1": 10.0, "fig10_2": 10.0, "fig10_3": 8.5, "fig10_4": 4.5}   # chapter10.py too


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
    last = gen10.PANELS[-1]
    lab_row = max(r for _, _, _, r in gen10.PANELS) + gen10.SIZE // 8 + 1
    (c0, r0), (c1, r1) = gen10.MIRROR_AT
    made = {
        # 10.1 - sprite: the six panels and their labels, a cell of paper round them
        "fig10_1": paper("sprite_f0012.png", 1, 1, last[2] + len(last[0]) + 1, lab_row + 2),
        # 10.2 - rotate: the thirteen rows, to the last carry box and a cell after it
        "fig10_2": paper("rotate_f0010.png", 0, 0, gen10.COL_C1 + 10, gen10.ROT_ROWS[-1] + 1),
        # 10.3 - scroll: the eight rows, to a cell after the bitmap
        "fig10_3": paper("scroll_f0012.png", 0, gen10.SCROLL_ROW0 - 1,
                         gen10.SCROLL_COL + gen10.SCROLL_W + 1,
                         gen10.SCROLL_ROW0 + gen10.SCROLL_ROWS + 1),
        # 10.4 - mirror: the arrow and its mirror image, a cell of paper round them
        "fig10_4": paper("mirror_f0010.png", c0 - 1, r0 - 1, c1 + 3, r1 + 3),
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
