#!/usr/bin/env python3
"""fig17.py - the figures of chapter 17, from the captures.

17.1: clock.rom, the paper's character rows 8 to 14. 17.2: unsaved.rom, all
the paper. 17.3: forgot.rom, the whole capture inside the columns the VDP
draws (chapter 4): the display is off, and the border is the screen.
Enlarged by a whole number, nearest neighbour, to at least 300 dpi at the
printed width. Nothing is added.
"""
import math
import os
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
sys.path.insert(0, HERE)
import meas  # noqa: E402
import meas17  # noqa: E402

CAP = os.path.join(HERE, "captures")
MIN_DPI = 300
WIDTH = {"fig17_1": 10.0, "fig17_2": 9.0, "fig17_3": 9.0}      # chapter17.py too
CLOCK_ROWS = (8, 15)                    # character rows of figure 17.1, the last not included


def enlarge(im, width_cm):
    f = math.ceil(MIN_DPI * width_cm / 2.54 / im.width)
    return im.resize((im.width * f, im.height * f), Image.NEAREST), f


def shot(name, frame):
    return Image.open(os.path.join(CAP, f"{name}_f{frame:04d}.png")).convert("RGB")


def main():
    x0, y0 = meas.paper(0, 0)
    clock = shot("clock", meas17.CLOCK_SHOT)
    unsaved = shot("unsaved", meas17.PAINT_FRAMES)
    forgot = shot("forgot", meas17.FORGOT_FRAMES)
    made = {
        # 17.1 - clock.rom: the two lines the main loop prints
        "fig17_1": clock.crop((x0, y0 + 8 * CLOCK_ROWS[0], x0 + 256, y0 + 8 * CLOCK_ROWS[1])),
        # 17.2 - unsaved.rom: the 768 cells
        "fig17_2": unsaved.crop((x0, y0, x0 + 256, y0 + 192)),
        # 17.3 - forgot.rom: every row, the drawn columns
        "fig17_3": forgot.crop((meas.DRAWN[0], 0, meas.DRAWN[1] + 1, forgot.height)),
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
