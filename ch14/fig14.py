#!/usr/bin/env python3
"""fig14.py - the figure of chapter 14, from the capture.

The whole capture inside the columns the VDP draws (chapter 4): with the
display off, the border fills the screen. Enlargement is by a whole number,
nearest neighbour, to at least 300 dpi at the printed width. Nothing is added.
"""
import math
import os
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
import meas  # noqa: E402

CAP = os.path.join(HERE, "captures")
MIN_DPI = 300
WIDTH = {"fig14_1": 10.0}                # chapter14.py too


def enlarge(im, width_cm):
    f = math.ceil(MIN_DPI * width_cm / 2.54 / im.width)
    return im.resize((im.width * f, im.height * f), Image.NEAREST), f


def main():
    im = Image.open(os.path.join(CAP, "budget.png")).convert("RGB")
    made = {
        # 14.1 - budget.rom: every row, the drawn columns
        "fig14_1": im.crop((meas.DRAWN[0], 0, meas.DRAWN[1] + 1, im.height)),
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
