#!/usr/bin/env python3
"""fig54.py - the figures of chapter 54, from the captures meas54.py kept.

Film frames, each the drawn columns and all 240 lines (chapter 4), enlarged
by a whole number, nearest neighbour, to at least 300 dpi at the printed
width. Nothing is added but the white between them. meas54.py checked every
capture against the picture of the VRAM as the bytes reached it, line by
line, the border too; the frames are in meas54.json ("photos", "plan").

    fig54_1  game.rom on the 50 Hz machine: the title, the frame after it
             is shown
    fig54_2  the same step of the planned game: game.rom played on the
             60 Hz machine (left) and its demo on the 50 Hz machine (right)
    fig54_3  frames.rom (left) and game.rom (right) on the 50 Hz machine, in
             the same frame of the demo: frames.rom's first touch. WHERE IT
             BREAKS
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
WIDTH = {"fig54_1": 9.0, "fig54_2": 14.0, "fig54_3": 14.0}
GAP = 16


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


def plan(m):
    """the captures of the figures, from meas54.json"""
    ph = m["photos"]
    p = ph["plan"]

    def frame(play, tag, f):
        return ph[play][tag]["frames"][str(f)]
    return {"fig54_1": [frame("attract", "eu", p["title"])],
            "fig54_2": [frame("play", "jp", p["game_jp"]), frame("attract", "eu", p["demo_eu"])],
            "fig54_3": [frame("broken", "eu", p["touch"]), frame("attract", "eu", p["touch"])]}


def main():
    m = json.load(open(os.path.join(HERE, "meas54.json")))
    out = {}
    for fig, pngs in plan(m).items():
        im = side_by_side([drawn(f) for f in pngs])
        big, k = enlarge(im, WIDTH[fig])
        path = os.path.join(HERE, f"{fig}.png")
        big.save(path)
        out[fig] = (path, WIDTH[fig], k, big.size)
    return out


if __name__ == "__main__":
    for name, (path, w, k, size) in main().items():
        print(f"{name}: x{k} -> {size[0]} x {size[1]} px, {w} cm, {size[0] / (w / 2.54):.0f} dpi")
