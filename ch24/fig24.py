#!/usr/bin/env python3
"""fig24.py - the figures of chapter 24, from the captures.

Parts of captures, set side by side, and enlarged by a whole number, nearest
neighbour, to at least 300 dpi at the printed width. Nothing is added but the
white between two panels. The film frames are the ones meas24.py checked.
"""
import json
import math
import os
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
sys.path.insert(0, HERE)
import meas  # noqa: E402
import gen24  # noqa: E402

CAP = os.path.join(HERE, "captures")
MIN_DPI = 300
WIDTH = {"fig24_1": 10.0, "fig24_2": 11.0, "fig24_3": 12.0, "fig24_4": 11.0, "fig24_5": 8.0}
GAP = 16
CORNER = (160, 144, 256, 192)   # figure 24.3: x0, y0, x1, y1 of the paper: rows 18 to 23
COIN = (44, 28, 68, 52)         # figure 24.5: the paper round the coin at row 2, column 3
TEAR = 0                        # figure 24.4: late.rom's first send
METAS = ((1, 1), (3, 2), (3, 6), (2, 3), (0, 0))   # figure 24.1: row and column of the
                                # map: sky, ground, ladder, coin, wall; then the player


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
    return Image.open(os.path.join(CAP, name)).convert("RGB")


def paper(im, box):
    x0, y0 = meas.paper(0, 0)
    return im.crop((x0 + box[0], y0 + box[1], x0 + box[2], y0 + box[3]))


def worst():
    """the first frame of full.rom with the most names wrong at 60 Hz, and its
    two photographs, 50 Hz and 60 Hz"""
    m = json.load(open(os.path.join(HERE, "meas24.json")))["copies"]["full"]
    wrong = m["jp"]["wrong_names"]
    k = wrong.index(max(wrong))
    return k, f"full_eu_f{m['eu']['films'][k]:04d}.png", f"full_jp_f{m['jp']['films'][k]:04d}.png"


def cell(r, c):
    """the paper of the metatile at row R, column C of the map"""
    return (16 * c, 16 * r, 16 * c + 16, 16 * r + 16)


def first_full():
    return json.load(open(os.path.join(HERE, "meas24.json")))["copies"]["full"]["eu"]["films"][0]


def film(name, k):
    m = json.load(open(os.path.join(HERE, "meas24.json")))[name]["eu"]
    return f"{name}_eu_f{m['films'][k]:04d}.png"


def main():
    k, eu, jp = worst()
    made = {
        # 24.1 - the six metatiles: sky, ground, ladder, coin and wall from
        # meta.rom, and the player from full.rom's first frame
        "fig24_1": side_by_side([paper(shot("meta_eu_f0030.png"), cell(r, c)) for r, c in METAS] +
                                [paper(shot(f"full_eu_f{first_full():04d}.png"),
                                       cell(gen24.PROW, gen24.PSTART))]),
        # 24.2 - meta.rom: the screen of the map
        "fig24_2": paper(shot("meta_eu_f0030.png"), (0, 0, 256, 192)),
        # 24.3 - full.rom, the same frame at 50 Hz (left) and 60 Hz (right):
        # the bottom right corner of the paper
        "fig24_3": side_by_side([paper(shot(eu), CORNER), paper(shot(jp), CORNER)]),
        # 24.4 - late.rom, the frame of its first send: the paper
        "fig24_4": paper(shot(film("late", TEAR)), (0, 0, 256, 192)),
        # 24.5 - spin.rom after its first four changes: one coin
        "fig24_5": side_by_side([paper(shot(film("spin", k)), COIN) for k in range(4)]),
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
