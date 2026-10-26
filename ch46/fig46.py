#!/usr/bin/env python3
"""fig46.py - the figures of chapter 46, from the captures.

Film frames, each the drawn columns and all 240 lines (chapter 4), enlarged
by a whole number, nearest neighbour, to at least 300 dpi at the printed
width. Nothing is added but the white between them. meas46.py checked every
capture against the picture of the VRAM as the bytes reached it, line by
line, and kept the ones the figures use; their frames are in meas46.json.
All are of the 60 Hz machine.

    fig46_1  game.rom: the title, and the gate hall in the first frame of play
    fig46_2  game.rom played from over_jp.events: the first touch, and GAME
             OVER
    fig46_3  game.rom: A1 with both lanterns lit, the explorer between its two
             guards; the map with sixteen lanterns lit
    fig46_4  late.rom: the gate hall's first frame, and C2's after the flip
             out of C3
    fig46_5  game.rom: the keep lit, and the title again
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
WIDTH = {f"fig46_{k}": 12.4 for k in range(1, 6)}
GAP = 16
FIGS = {"fig46_1": [("game", "title"), ("game", "first")],
        "fig46_2": [("over", "touch"), ("over", "over")],
        "fig46_3": [("game", "a1"), ("game", "map")],
        "fig46_4": [("late", "first"), ("late", "wrong")],
        "fig46_5": [("game", "win"), ("game", "again")]}


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


def frame(ph, play, key):
    p = ph[play]["jp"]
    return p["plan"][key], p["frames"][str(p["plan"][key])]


def main():
    ph = json.load(open(os.path.join(HERE, "meas46.json")))["photos"]
    out = {}
    for fig, keys in FIGS.items():
        im = grid([drawn(frame(ph, play, key)[1]) for play, key in keys], 2)
        big, k = enlarge(im, WIDTH[fig])
        path = os.path.join(HERE, f"{fig}.png")
        big.save(path)
        out[fig] = (path, WIDTH[fig], k, big.size)
    return out


if __name__ == "__main__":
    for name, (path, w, k, size) in main().items():
        print(f"{name}: x{k} -> {size[0]} x {size[1]} px, {w} cm, {size[0] / (w / 2.54):.0f} dpi")
