#!/usr/bin/env python3
"""fig48.py - the figures of chapter 48, from the captures.

Film frames, each the drawn columns and all 240 lines (chapter 4), enlarged
by a whole number, nearest neighbour, to at least 300 dpi at the printed
width. Nothing is added but the white between them. meas48.py checked every
capture against the picture of the VRAM as the bytes reached it, line by
line, and kept the ones the figures use; their frames are in meas48.json.
All are of the 60 Hz machine.

    fig48_1  long.rom: the last frame of bank 1's world and the first of bank 2's
    fig48_2  long.rom round its world: a frame near the start, the first of each
             bank after it, and bank 1's again, clipped from a run of 53,958 frames
    fig48_3  guess.rom: the last frame before the mapper serves the wrong bytes,
             and the first
    fig48_4  long.rom and far.rom in the same frame, the first far.rom gets wrong
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
WIDTH = {f"fig48_{k}": 12.4 for k in range(1, 5)}
WIDTH["fig48_2"] = 15.2
GAP = 16


def enlarge(im, width_cm):
    f = math.ceil(MIN_DPI * width_cm / 2.54 / im.width)
    return im.resize((im.width * f, im.height * f), Image.NEAREST), f


def drawn(png):
    im = Image.open(os.path.join(CAP, png)).convert("RGB")
    return im.crop((meas.DRAWN[0], 0, meas.DRAWN[1] + 1, meas.CAPTURE_H))


def grid(panels, cols, gap=GAP):
    rows = math.ceil(len(panels) / cols)
    w, h = panels[0].size
    out = Image.new("RGB", (cols * w + (cols - 1) * gap, rows * h + (rows - 1) * gap), (255, 255, 255))
    for i, p in enumerate(panels):
        out.paste(p, ((i % cols) * (w + gap), (i // cols) * (h + gap)))
    return out


def panels():
    """each figure's frames: [(program, frame)]"""
    ph = json.load(open(os.path.join(HERE, "meas48.json")))["photos"]
    lg, fr, gs = ph["long"]["jp"]["figs"], ph["far"]["jp"]["figs"], ph["guess"]["jp"]["figs"]
    assert lg[2] == fr[0]
    return ph, {"fig48_1": [("long", lg[0]), ("long", lg[1])],
                "fig48_3": [("guess", gs[0]), ("guess", gs[1])],
                "fig48_4": [("long", fr[0]), ("far", fr[0])]}


def main():
    ph, figs = panels()
    wd = json.load(open(os.path.join(HERE, "meas48.json")))["world"]["jp"]
    figs["fig48_2"] = [("world", f) for f in wd["frames"]]
    out = {}
    for fig, pl in figs.items():
        if fig == "fig48_2":
            im = grid([drawn(wd["photos"][str(f)]) for _, f in pl], 4)
        else:
            im = grid([drawn(ph[name]["jp"]["frames"][str(f)]) for name, f in pl], 2)
        big, k = enlarge(im, WIDTH[fig])
        path = os.path.join(HERE, f"{fig}.png")
        big.save(path)
        out[fig] = (path, WIDTH[fig], k, big.size)
    return out


if __name__ == "__main__":
    for name, (path, w, k, size) in main().items():
        print(f"{name}: x{k} -> {size[0]} x {size[1]} px, {w} cm, {size[0] / (w / 2.54):.0f} dpi")
