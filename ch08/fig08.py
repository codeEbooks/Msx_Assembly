#!/usr/bin/env python3
"""fig08.py - the figures of chapter 8, cropped from the captures.

Crops are whole character cells of the paper (figure 8.1) or whole rows of
the capture inside the columns the VDP draws (figure 8.2, chapter 4);
enlargement is by a whole number, nearest neighbour, to at least 300 dpi at
the printed width. Nothing is added.
"""
import math
import os
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
sys.path.insert(0, HERE)
import meas  # noqa: E402
import gen08  # noqa: E402

CAP = os.path.join(HERE, "captures")
MIN_DPI = 300
WIDTH = {"fig08_1": 10.5, "fig08_2": 13.0}      # chapter08.py uses the same numbers
BAND_ROWS = (210, 240)                            # the rows of the capture in figure 8.2


def paper(name, col0, row0, cols, rows):
    x0, y0 = meas.paper(8 * col0, 8 * row0)
    im = Image.open(os.path.join(CAP, name)).convert("RGB")
    return im.crop((x0, y0, x0 + 8 * cols, y0 + 8 * rows))


def enlarge(im, width_cm):
    f = math.ceil(MIN_DPI * width_cm / 2.54 / im.width)
    return im.resize((im.width * f, im.height * f), Image.NEAREST), f


def main():
    rows = [r for _, r, _ in gen08.OBJECTS]
    band = Image.open(os.path.join(CAP, "copy4_f0012.png")).convert("RGB")
    made = {
        # 8.1 - records.rom: the row above the first bar to the row below the last
        "fig08_1": paper("records_f0010.png", 0, min(rows) - 1, 32, max(rows) - min(rows) + 3),
        # 8.2 - copy4.rom: the bottom border, columns 19 to 302
        "fig08_2": band.crop((meas.DRAWN[0], BAND_ROWS[0], meas.DRAWN[1] + 1, BAND_ROWS[1])),
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
