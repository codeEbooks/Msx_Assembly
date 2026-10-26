#!/usr/bin/env python3
"""fig15.py - the figures of chapter 15, from the captures.

Parts of captures, set side by side and enlarged by a whole number, nearest
neighbour, to at least 300 dpi at the printed width. Nothing is added but
the white between two panels.
"""
import math
import os
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
sys.path.insert(0, HERE)
import meas  # noqa: E402
import meas15  # noqa: E402

CAP = os.path.join(HERE, "captures")
MIN_DPI = 300
WIDTH = {"fig15_1": 12.0, "fig15_2": 8.0}       # chapter15.py too
GAP = 24
EDGE = 8                    # pixels of border kept round the paper


def side_by_side(panels):
    w = sum(p.width for p in panels) + GAP * (len(panels) - 1)
    out = Image.new("RGB", (w, max(p.height for p in panels)), (255, 255, 255))
    x = 0
    for p in panels:
        out.paste(p, (x, 0))
        x += p.width + GAP
    return out


def enlarge(im, width_cm):
    f = math.ceil(MIN_DPI * width_cm / 2.54 / im.width)
    return im.resize((im.width * f, im.height * f), Image.NEAREST), f


def paper(path):
    """the paper of a capture, all of it, and a little border"""
    x0, y0 = meas.paper(0, 0)
    return Image.open(path).convert("RGB").crop(
        (x0 - EDGE, y0 - EDGE, x0 + 256 + EDGE, y0 + 192 + EDGE))


def main():
    f = meas15.PICTURE_FRAME
    made = {
        # 15.1 - picture.rom (left) and rowwise.rom (right): the same picture,
        #        in the order of the patterns and row after row
        "fig15_1": side_by_side([paper(os.path.join(CAP, f"picture_f{f:04d}.png")),
                                 paper(os.path.join(CAP, f"rowwise_f{f:04d}.png"))]),
        # 15.2 - big.rom: the page C-BIOS left, after its logo ROM has run
        "fig15_2": paper(os.path.join(CAP, "big.png")),
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
