#!/usr/bin/env python3
"""fig33.py - the figures of chapter 33, from the captures.

Parts of captures, set side by side or one above another, and enlarged by a
whole number, nearest neighbour, to at least 300 dpi at the printed width.
Nothing is added but the white between two panels. Every capture is a frame
meas33.py checked against the model, pixel by pixel.
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
WIDTH = {"fig33_1": 12.0, "fig33_2": 12.0, "fig33_3": 12.0}
GAP, THIN = 16, 2
DRAWN = (meas.DRAWN[0], 0, meas.DRAWN[1] + 1, meas.CAPTURE_H)    # the columns the VDP draws
ORDER_FRAMES = (16, 17, 18)         # figure 33.1: order.rom at 50 Hz, a frame lost between two
TRACK = (13, 15)                    # figure 33.2: lines 13 and 14 of the paper, the herd's first row ...
TRACK_X = (0, 64)                   # ... its first figure, in every frame of the film, at 60 Hz
TORN_X = 16                         # figure 33.3: first.rom's paper from column 16, and the border


def side_by_side(panels, gap=GAP):
    w = sum(p.width for p in panels) + gap * (len(panels) - 1)
    out = Image.new("RGB", (w, max(p.height for p in panels)), (255, 255, 255))
    x = 0
    for p in panels:
        out.paste(p, (x, 0))
        x += p.width + gap
    return out


def stacked(panels, gap=GAP):
    h = sum(p.height for p in panels) + gap * (len(panels) - 1)
    out = Image.new("RGB", (max(p.width for p in panels), h), (255, 255, 255))
    y = 0
    for p in panels:
        out.paste(p, (0, y))
        y += p.height + gap
    return out


def enlarge(im, width_cm):
    f = math.ceil(MIN_DPI * width_cm / 2.54 / im.width)
    return im.resize((im.width * f, im.height * f), Image.NEAREST), f


def frame(name, tag, k):
    return Image.open(os.path.join(CAP, f"{name}_{tag}_f{k:04d}.png")).convert("RGB")


def paper(im, x0, y0, x1, y1):
    return im.crop((meas.PAPER_X0 + x0, meas.PAPER_Y0 + y0, meas.PAPER_X0 + x1, meas.PAPER_Y0 + y1))


def track(name, shots):
    """lines TRACK of the paper, columns TRACK_X, one frame under another"""
    return stacked([paper(frame(name, "jp", k), TRACK_X[0], TRACK[0], TRACK_X[1], TRACK[1])
                    for k in shots], 0)


def main():
    m = json.load(open(os.path.join(HERE, "meas33.json")))
    o, n = m["order"]["jp"]["shots"], m["nocount"]["jp"]["shots"]
    both = [k for k in o if k in n]
    torn = m["first"]["eu"]["torn"][0]["shot"]
    made = {
        # 33.1 - order.rom at 50 Hz: three frames in a row, the middle one lost
        "fig33_1": side_by_side([frame("order", "eu", k).crop(DRAWN) for k in ORDER_FRAMES]),
        # 33.2 - order.rom (left) and nocount.rom (right): the herd's first figure, frame after frame
        "fig33_2": side_by_side([track("order", both), track("nocount", both)]),
        # 33.3 - first.rom at 50 Hz: the frame before the first send into the paper, and its frame
        "fig33_3": side_by_side([frame("first", "eu", k).crop((meas.PAPER_X0 + TORN_X, 0, DRAWN[2],
                                                               meas.CAPTURE_H))
                                 for k in (torn - 1, torn)]),
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
