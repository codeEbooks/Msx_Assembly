#!/usr/bin/env python3
"""fig06.py - the figure of chapter 6, from the captures.

Two captures side by side, every line of each, in the columns the VDP draws
(19 to 302, tools/meas.py), enlarged by a whole number, nearest neighbour, to
at least 300 dpi at the printed width. The only thing added is the white gap
between the two panels.
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
GAP = 12
FULL = 15.29                        # the column is 15.2976 cm
WIDTH = {"fig06_1": FULL}           # chapter06.py uses the same numbers


def cap(name):
    im = Image.open(os.path.join(CAP, name)).convert("RGB")
    return im.crop((meas.DRAWN[0], 0, meas.DRAWN[1] + 1, im.height))


def side_by_side(panels, gap=GAP):
    out = Image.new("RGB", (sum(p.width for p in panels) + gap * (len(panels) - 1),
                            max(p.height for p in panels)), (255, 255, 255))
    x = 0
    for p in panels:
        out.paste(p, (x, 0))
        x += p.width + gap
    return out


def enlarge(im, width_cm):
    f = math.ceil(MIN_DPI * width_cm / 2.54 / im.width)
    return im.resize((im.width * f, im.height * f), Image.NEAREST), f


def main():
    # 6.1 - border.rom, frame 60 after INIT (left) and frame 62 (right): in
    # frame 61 the console wrote register 7 and the VRAM
    made = {"fig06_1": side_by_side([cap("write_f0060.png"), cap("write_f0062.png")])}
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
