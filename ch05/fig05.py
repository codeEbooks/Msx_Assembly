#!/usr/bin/env python3
"""fig05.py - the figures of chapter 5, from the captures.

Captures side by side, every line of each, in the columns the VDP draws
(19 to 302, tools/meas.py: chapter 4 found that openMSX 20.0 and later show
the columns outside them differently), enlarged by a whole number, nearest
neighbour, to at least 300 dpi at the printed width. The only thing added is
the white gap between the two panels of each figure.
"""
import json
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
# the print width of each figure, in cm; chapter05.py uses the same numbers
WIDTH = {"fig05_1": FULL, "fig05_2": FULL}


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
    st = json.load(open(os.path.join(HERE, "meas05.json")))["start"]
    made = {
        # 5.1 - border.rom from power-on: the frame in which INIT runs (left),
        # and the next one (right)
        "fig05_1": side_by_side([cap(f"border_p{st['split_frame']:04d}.png"),
                                 cap(f"border_p{st['whole_frame']:04d}.png")]),
        # 5.2 - frame 400 after power-on: ba.rom (left) and noend.rom (right)
        "fig05_2": side_by_side([cap("ba_p0400.png"), cap("noend_p0400.png")]),
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
