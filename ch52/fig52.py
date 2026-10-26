#!/usr/bin/env python3
"""fig52.py - the figures of chapter 52, from the captures meas52.py kept.

The drawn columns and all 240 lines of each capture (chapter 4), enlarged by
a whole number, nearest neighbour, to at least 300 dpi at the printed width.
Nothing is added but the white between them. meas52.py checked every capture
against the picture the model gives, the border too.

    fig52_1  the frame each program shows after loop 144, the window's, at
             60 Hz: over.rom (chapter 42), win, tests on the first row,
             sends, moves, patch on the second
    fig52_2  inrom.rom and patch.rom at 60 Hz, in the frame after the loop in
             which the last of inrom.rom's balls reached its corner
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
WIDTH = {"fig52_1": 14.0, "fig52_2": 14.0}
GAP = 16
ROWS = [["over", "win", "tests"], ["sends", "moves", "patch"]]


def enlarge(im, width_cm):
    f = math.ceil(MIN_DPI * width_cm / 2.54 / im.width)
    return im.resize((im.width * f, im.height * f), Image.NEAREST), f


def drawn(png):
    im = Image.open(os.path.join(CAP, png)).convert("RGB")
    return im.crop((meas.DRAWN[0], 0, meas.DRAWN[1] + 1, meas.CAPTURE_H))


def side_by_side(panels, gap=GAP):
    w = sum(p.width for p in panels) + gap * (len(panels) - 1)
    out = Image.new("RGB", (w, max(p.height for p in panels)), (255, 255, 255))
    x = 0
    for p in panels:
        out.paste(p, (x, 0))
        x += p.width + gap
    return out


def stacked(rows, gap=GAP):
    out = Image.new("RGB", (max(r.width for r in rows), sum(r.height for r in rows) + gap * (len(rows) - 1)),
                    (255, 255, 255))
    y = 0
    for r in rows:
        out.paste(r, (0, y))
        y += r.height + gap
    return out


def main():
    m = json.load(open(os.path.join(HERE, "meas52.json")))
    ph = m["photos"]
    made = {"fig52_1": stacked([side_by_side([drawn(ph["bands"][n]["png"]) for n in row]) for row in ROWS]),
            "fig52_2": side_by_side([drawn(ph["corners"][n]["png"]) for n in ("inrom", "patch")])}
    out = {}
    for fig, im in made.items():
        big, k = enlarge(im, WIDTH[fig])
        path = os.path.join(HERE, f"{fig}.png")
        big.save(path)
        out[fig] = (path, WIDTH[fig], k, big.size)
    return out


if __name__ == "__main__":
    for name, (path, w, k, size) in main().items():
        print(f"{name}: x{k} -> {size[0]} x {size[1]} px, {w} cm, {size[0] / (w / 2.54):.0f} dpi")
