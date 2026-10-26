#!/usr/bin/env python3
"""fig16.py - the figures of chapter 16, from the captures.

16.1: the paper of the capture, rows 0 to 13 of characters, and a little
border. 16.2: the whole capture inside the columns the VDP draws (chapter 4),
the border's bands and all. Enlarged by a whole number, nearest neighbour, to
at least 300 dpi at the printed width. Nothing is added.
"""
import math
import os
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
sys.path.insert(0, HERE)
import meas  # noqa: E402
import meas16  # noqa: E402

CAP = os.path.join(HERE, "captures")
MIN_DPI = 300
WIDTH = {"fig16_1": 10.0, "fig16_2": 10.0}     # chapter16.py too
EDGE = 8                                # pixels of border kept round the paper
ROWS = 14                               # character rows shown, from the top


def enlarge(im, width_cm):
    f = math.ceil(MIN_DPI * width_cm / 2.54 / im.width)
    return im.resize((im.width * f, im.height * f), Image.NEAREST), f


def main():
    x0, y0 = meas.paper(0, 0)
    shot = Image.open(os.path.join(CAP, f"print_f{meas16.PRINT_FRAME:04d}.png")).convert("RGB")
    hook = Image.open(os.path.join(CAP, f"hook_f{meas16.HOOK_FRAMES:04d}.png")).convert("RGB")
    made = {
        # 16.1 - print.rom: the page CHPUT printed, and the border round it
        "fig16_1": shot.crop((x0 - EDGE, y0 - EDGE, x0 + 256 + EDGE, y0 + 8 * ROWS)),
        # 16.2 - hook.rom: every row, the drawn columns
        "fig16_2": hook.crop((meas.DRAWN[0], 0, meas.DRAWN[1] + 1, hook.height)),
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
