#!/usr/bin/env python3
"""fig25.py - the figures of chapter 25, from the captures.

Parts of captures, set side by side, and enlarged by a whole number, nearest
neighbour, to at least 300 dpi at the printed width. Nothing is added but the
white between two panels. Each capture is the frame meas25.py checked, the
one after the program finished, on the 50 Hz machine.
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
WIDTH = {"fig25_1": 11.0, "fig25_2": 10.0, "fig25_3": 10.0, "fig25_4": 12.0}
GAP = 16
OVER = (0, 40, 128, 56)         # figure 25.1: x0, y0, x1, y1 of the paper
CROPS = ((40, 72, 88, 120), (40, 8, 88, 56))    # figure 25.3: flat lines, and lines
                                # near 45 degrees


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


def shot(name):
    """the frame meas25.py photographed, 50 Hz"""
    m = json.load(open(os.path.join(HERE, "meas25.json")))
    k = {"over": m["over"]["eu"], "fan": m["fan"]["fan"]["eu"],
         "hidden": m["hidden"]["hidden"]["eu"], "shown": m["hidden"]["shown"]["eu"]}[name]["shot"]
    return Image.open(os.path.join(CAP, f"{name}_eu_f{k:04d}.png")).convert("RGB")


def paper(im, box):
    x0, y0 = meas.paper(0, 0)
    return im.crop((x0 + box[0], y0 + box[1], x0 + box[2], y0 + box[3]))


ALL = (0, 0, 256, 192)


def main():
    made = {
        # 25.1 - over.rom: the line drawn with pixel (above) and with plot
        "fig25_1": paper(shot("over"), OVER),
        # 25.2 - fan.rom: the paper
        "fig25_2": paper(shot("fan"), ALL),
        # 25.3 - fan.rom: two parts of the paper
        "fig25_3": side_by_side([paper(shot("fan"), c) for c in CROPS]),
        # 25.4 - hidden.rom (left) and shown.rom (right): the paper
        "fig25_4": side_by_side([paper(shot("hidden"), ALL), paper(shot("shown"), ALL)]),
    }
    out = {}
    for name, im in made.items():
        big, f = enlarge(im, WIDTH[name])
        path = os.path.join(HERE, f"{name}.png")
        big.save(path)
        out[name] = (path, WIDTH[name], f, big.size)
    return out


if __name__ == "__main__":
    for name, (path, w, k, size) in main().items():
        print(f"{name}: x{k} -> {size[0]} x {size[1]} px, {w} cm, {size[0] / (w / 2.54):.0f} dpi")
