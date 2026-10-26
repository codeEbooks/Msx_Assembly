#!/usr/bin/env python3
"""fig42.py - the figures of chapter 42, from the captures.

Two film frames side by side, of the 60 Hz machine but in fig42_2: the
drawn columns and all 240 lines of each (chapter 4), enlarged by a whole
number, nearest neighbour, to at least 300 dpi at the printed width. Nothing is added but the white
between them. meas42.py checked every capture against the picture the model
gives, the border too, and kept the ones the figures use; their names are in
meas42.json.

    fig42_1  budget.rom: the frame of the window, and the frame after it
    fig42_2  the same on the 50 Hz machine
    fig42_3  over.rom: the frame of a lost loop, and the frame lost
    fig42_4  spread.rom: the same two frames
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
WIDTH = {"fig42_1": 14.0, "fig42_2": 14.0, "fig42_3": 14.0, "fig42_4": 14.0}
GAP = 16
SOURCE = {"fig42_1": ("budget", "jp"), "fig42_2": ("budget", "eu"), "fig42_3": ("over", "jp"),
          "fig42_4": ("spread", "jp")}


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


def frames_of(m, name, tag):
    """the two frames each figure shows: those after the loop's wake"""
    ph = m["photos"][name][tag]
    w = m["films"][name][tag]["rows"][ph["loop"]]["frame"]
    return [w + 1, w + 2], ph


def main():
    m = json.load(open(os.path.join(HERE, "meas42.json")))
    out = {}
    for fig, (name, tag) in SOURCE.items():
        frames, ph = frames_of(m, name, tag)
        im = side_by_side([drawn(ph["frames"][str(f)]["png"]) for f in frames])
        big, k = enlarge(im, WIDTH[fig])
        path = os.path.join(HERE, f"{fig}.png")
        big.save(path)
        out[fig] = (path, WIDTH[fig], k, big.size)
    return out


if __name__ == "__main__":
    for name, (path, w, k, size) in main().items():
        print(f"{name}: x{k} -> {size[0]} x {size[1]} px, {w} cm, {size[0] / (w / 2.54):.0f} dpi")
