#!/usr/bin/env python3
"""fig43.py - the figures of chapter 43, from the captures.

Film frames of the 50 Hz machine, each the drawn columns and all 240 lines
(chapter 4), or a piece of the paper, enlarged by a whole number, nearest
neighbour, to at least 300 dpi at the printed width. Nothing is added but the
white between them. meas43.py checked every capture against the picture the
model gives and kept the ones the figures use; their names are in
meas43.json.

    fig43_1  game.rom: the title, and a frame of the first round
    fig43_2  game.rom: the first gem taken, three frames of a piece
    fig43_3  game.rom: the frame that set C, a frame of the hold, GAME OVER
    fig43_4  game.rom and stale.rom, the same frame after the first touch
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
WIDTH = {"fig43_1": 14.0, "fig43_2": 14.0, "fig43_3": 14.0, "fig43_4": 14.0}
GAP = 16
CUT = (160, 56, 64, 48)             # fig43_2: x, y, width, height of the paper shown


def enlarge(im, width_cm):
    f = math.ceil(MIN_DPI * width_cm / 2.54 / im.width)
    return im.resize((im.width * f, im.height * f), Image.NEAREST), f


def drawn(png):
    im = Image.open(os.path.join(CAP, png)).convert("RGB")
    return im.crop((meas.DRAWN[0], 0, meas.DRAWN[1] + 1, meas.CAPTURE_H))


def piece(png, cut=CUT):
    x, y, w, h = cut
    im = Image.open(os.path.join(CAP, png)).convert("RGB")
    return im.crop((meas.PAPER_X0 + x, meas.PAPER_Y0 + y, meas.PAPER_X0 + x + w, meas.PAPER_Y0 + y + h))


def side_by_side(panels, gap=GAP):
    w = sum(p.width for p in panels) + gap * (len(panels) - 1)
    out = Image.new("RGB", (w, max(p.height for p in panels)), (255, 255, 255))
    x = 0
    for p in panels:
        out.paste(p, (x, 0))
        x += p.width + gap
    return out


def main():
    m = json.load(open(os.path.join(HERE, "meas43.json")))
    ph = m["photos"]["eu"]
    fr, plan = ph["frames"], ph["plan"]
    figs = {
        "fig43_1": side_by_side([drawn(fr[str(plan["title"])]), drawn(fr[str(plan["round"])])]),
        "fig43_2": side_by_side([piece(fr[str(c)]) for c in plan["gem"]], gap=4),
        "fig43_3": side_by_side([drawn(fr[str(plan["touch"][0])]), drawn(fr[str(plan["touch"][2])]),
                                 drawn(fr[str(plan["over"])])]),
        "fig43_4": side_by_side([drawn(fr[str(plan["after"])]), drawn(ph["stale"][str(plan["after"])])]),
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
