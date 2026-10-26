#!/usr/bin/env python3
"""fig45.py - the figures of chapter 45, from the captures.

Film frames, each the drawn columns and all 240 lines (chapter 4), enlarged
by a whole number, nearest neighbour, to at least 300 dpi at the printed
width. Nothing is added but the white between them. meas45.py checked every
capture against the picture of the VRAM as the bytes reached it, line by
line, and kept the ones the figures use; their frames are in meas45.json.

    fig45_1  game.rom, 50 Hz: each of the sixteen rooms in the first frame
             that shows it, as the map lays them out
    fig45_2  the flip out of the gate hall: game.rom at 60 Hz, the frame
             before the page and the page's; torn.rom's page, at 60 Hz and
             at 50 Hz
    fig45_3  game.rom, 50 Hz: the map at the sixth room, and at the last
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
WIDTH = {"fig45_1": 12.4, "fig45_2": 12.4, "fig45_3": 14.0}
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


def main():
    m = json.load(open(os.path.join(HERE, "meas45.json")))
    ph = m["photos"]
    ge, gj = ph["game"]["eu"], ph["game"]["jp"]
    tj, te = ph["torn"]["jp"], ph["torn"]["eu"]
    figs = {
        "fig45_1": grid([drawn(ge["frames"][str(c)]) for c in ge["plan"]["rooms"]], 4),
        "fig45_2": grid([drawn(gj["frames"][str(gj["plan"]["flip"][0])]),
                         drawn(gj["frames"][str(gj["plan"]["flip"][1])]),
                         drawn(tj["frames"][str(tj["plan"]["flip"][1])]),
                         drawn(te["frames"][str(te["plan"]["flip"][1])])], 2),
        "fig45_3": grid([drawn(ge["frames"][str(c)]) for c in ge["plan"]["maps"]], 2),
    }
    out = {}
    for fig, im in figs.items():
        big, k = enlarge(im, WIDTH[fig])
        path = os.path.join(HERE, f"{fig}.png")
        big.save(path)
        out[fig] = (path, WIDTH[fig], k, big.size)
    return out


if __name__ == "__main__":
    for name, (path, w, k, size) in main().items():
        print(f"{name}: x{k} -> {size[0]} x {size[1]} px, {w} cm, {size[0] / (w / 2.54):.0f} dpi")
