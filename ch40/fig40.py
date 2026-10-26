#!/usr/bin/env python3
"""fig40.py - the figures of chapter 40, from the captures.

Parts of captures, set side by side or one under another, and enlarged by a
whole number, nearest neighbour, to at least 300 dpi at the printed width.
Nothing is added but the white between two panels. meas40.py checked every
capture against the picture the VRAM gives, line by line, and kept the ones
the figures use; their names are in meas40.json.
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
WIDTH = {"fig40_1": 10.0, "fig40_2": 9.0}
GAP = 16                    # between two columns
ROW_GAP = 4                 # between two pictures, one under the other
ROOM = (0, 0, 256, 192)     # figure 40.1: the whole paper
SCORE = (48, 128, 112, 136)  # figure 40.2: the score's six cells and one each side, row 16


def enlarge(im, width_cm):
    f = math.ceil(MIN_DPI * width_cm / 2.54 / im.width)
    return im.resize((im.width * f, im.height * f), Image.NEAREST), f


def paper(png, box):
    """part of a capture: BOX, in pixels of the paper"""
    im = Image.open(os.path.join(CAP, png)).convert("RGB")
    x0, y0, x1, y1 = box
    return im.crop((meas.PAPER_X0 + x0, meas.PAPER_Y0 + y0, meas.PAPER_X0 + x1, meas.PAPER_Y0 + y1))


def column(pngs):
    parts = [paper(p, SCORE) for p in pngs]
    w, h = parts[0].size
    out = Image.new("RGB", (w, len(parts) * h + (len(parts) - 1) * ROW_GAP), (255, 255, 255))
    for i, p in enumerate(parts):
        out.paste(p, (0, i * (h + ROW_GAP)))
    return out


def side_by_side(panels, gap=GAP):
    w = sum(p.width for p in panels) + gap * (len(panels) - 1)
    out = Image.new("RGB", (w, max(p.height for p in panels)), (255, 255, 255))
    x = 0
    for p in panels:
        out.paste(p, (x, 0))
        x += p.width + gap
    return out


def main():
    m = json.load(open(os.path.join(HERE, "meas40.json")))
    f = m["films"]
    strips = [[p for p in f[k]["eu"]["captures"] if int(p.rsplit("_f", 1)[1][:4]) != f[k]["eu"]["last_picture"]
               or k != "status"][:12] for k in ("status", "after", "blink")]
    last = f"status_eu_f{f['status']['eu']['last_picture']:04d}.png"
    made = {
        # 40.1 - status.asm, the last picture: the game's two thirds and the status line's
        "fig40_1": paper(last, ROOM),
        # 40.2 - the score in twelve pictures of each program
        "fig40_2": side_by_side([column(s) for s in strips]),
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
