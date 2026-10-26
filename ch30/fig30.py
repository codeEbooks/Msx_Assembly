#!/usr/bin/env python3
"""fig30.py - the figures of chapter 30, from the captures.

Parts of captures, set side by side or one above another, and enlarged by a
whole number, nearest neighbour, to at least 300 dpi at the printed width.
Nothing is added but the white between two panels. Every capture is a frame
meas30.py checked against the model.
"""
import json
import math
import os
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
import meas  # noqa: E402
sys.path.insert(0, HERE)
import gen30  # noqa: E402

CAP = os.path.join(HERE, "captures")
MIN_DPI = 300
WIDTH = {"fig30_1": 12.0, "fig30_2": 12.0, "fig30_3": 9.0, "fig30_4": 12.0}
GAP = 16
r0, c0 = gen30.GRID
GRID = (8 * c0, 8 * r0, 8 * c0 + 128, 8 * r0 + 128)                 # figure 30.1: each panel
OWN = (0, 8 * gen30.OWN_ROW, 256, 8 * gen30.OWN_ROW + 24)             # figure 30.2
WHOLE = (0, 0, 256, 192)                                              # figure 30.3
BAR = (0, 8 * gen30.BAR_ROW, 8 * (gen30.BAR_AT + gen30.BAR_LEN + 1), 8 * gen30.BAR_ROW + 8)  # 30.4


def side_by_side(panels):
    w = sum(p.width for p in panels) + GAP * (len(panels) - 1)
    out = Image.new("RGB", (w, max(p.height for p in panels)), (255, 255, 255))
    x = 0
    for p in panels:
        out.paste(p, (x, 0))
        x += p.width + GAP
    return out


def stacked(panels):
    h = sum(p.height for p in panels) + GAP * (len(panels) - 1)
    out = Image.new("RGB", (max(p.width for p in panels), h), (255, 255, 255))
    y = 0
    for p in panels:
        out.paste(p, (0, y))
        y += p.height + GAP
    return out


def enlarge(im, width_cm):
    f = math.ceil(MIN_DPI * width_cm / 2.54 / im.width)
    return im.resize((im.width * f, im.height * f), Image.NEAREST), f


def frame(name, tag, k):
    return Image.open(os.path.join(CAP, f"{name}_{tag}_f{k:04d}.png")).convert("RGB")


def paper(im, box):
    x0, y0 = meas.paper(0, 0)
    return im.crop((x0 + box[0], y0 + box[1], x0 + box[2], y0 + box[3]))


def main():
    m = json.load(open(os.path.join(HERE, "meas30.json")))
    made = {
        # 30.1 - bios.rom: the 256 shapes, 50 Hz machine (left) and 60 Hz (right)
        "fig30_1": side_by_side([paper(frame("bios", t, m["bios"][t]["shot"]), GRID)
                                 for t in ("eu", "jp")]),
        # 30.2 - own.rom: the 96 characters
        "fig30_2": paper(frame("own", "eu", m["own"]["eu"]["shot"]), OWN),
        # 30.3 - page.rom: the last frame of the film
        "fig30_3": paper(frame("page", "eu", m["page"]["eu"]["frames"][-1]), WHOLE),
        # 30.4 - bar.rom: the status line, 50 Hz machine (above) and 60 Hz (below)
        "fig30_4": stacked([paper(frame("bar", t, m["bar"][t]["shot"]), BAR) for t in ("eu", "jp")]),
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
