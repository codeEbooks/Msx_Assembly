#!/usr/bin/env python3
"""fig23.py - the figures of chapter 23, from the captures.

Parts of captures, set side by side, and enlarged by a whole number, nearest
neighbour, to at least 300 dpi at the printed width. Nothing is added but the
white between two panels. The film frames are the ones meas23.py checked.
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
WIDTH = {"fig23_1": 14.0, "fig23_2": 12.0, "fig23_3": 14.0, "fig23_4": 4.0,
         "fig23_5": 7.0, "fig23_6": 5.0}
GAP = 16
PLACES_ROWS = (36, 80)          # figure 23.1: these lines of the paper
NEAR = (48, 82, 96, 114)        # figure 23.2: x0, y0, x1, y1 of the paper round the ball
NEAR_MOVES = (40, 41)           # ... after these moves: two strips a line, then three
WAYS = ("oneink", "plain", "steps", "backdrop")     # figure 23.3
AFTER = 40                      # ... and 23.4 and 23.6: after this many moves
HALF = (0, 0, 128, 192)         # the left half of the paper
EDGE = (96, 88, 160, 120)       # figure 23.5: the paper round the hill's edge at x = 128


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


def film(name, move):
    """the photograph meas23.py checked after move MOVE (counted from 1)"""
    m = json.load(open(os.path.join(HERE, "meas23.json")))
    return f"{name}_eu_f{m['ways'][name]['eu']['films'][move - 1]:04d}.png"


def main():
    made = {
        # 23.1 - places.rom: the ball in its eight places in a byte
        "fig23_1": paper(shot("places_eu_f0030.png"), (0, PLACES_ROWS[0], 256, PLACES_ROWS[1])),
        # 23.2 - clash.rom after moves 39 and 40, and sprite.rom after move 40
        "fig23_2": side_by_side([paper(shot(film("clash", k)), NEAR) for k in NEAR_MOVES] +
                                [paper(shot(film("sprite", NEAR_MOVES[1])), NEAR)]),
        # 23.3 - ways 1, 2, 3 and 5 after 40 moves: the left half of the paper
        "fig23_3": side_by_side([paper(shot(film(n, AFTER)), HALF) for n in WAYS]),
        # 23.4 - blocks.rom after 40 moves: the paper round the block
        "fig23_4": paper(shot(film("blocks", AFTER)), NEAR),
        # 23.5 - hill.rom: the edge where whole strips (left) meet both colours (right)
        "fig23_5": paper(shot("hill_eu_f0030.png"), EDGE),
        # 23.6 - zero.rom after 40 moves
        "fig23_6": paper(shot(film("zero", AFTER)), HALF),
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
