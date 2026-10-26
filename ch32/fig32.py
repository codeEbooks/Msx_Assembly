#!/usr/bin/env python3
"""fig32.py - the figures of chapter 32, from the captures.

Parts of captures, set side by side or one above another, and enlarged by a
whole number, nearest neighbour, to at least 300 dpi at the printed width.
Nothing is added but the white between two panels. Every capture is a frame
meas32.py checked against the model, pixel by pixel.
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
WIDTH = {"fig32_1": 12.0, "fig32_2": 12.0, "fig32_3": 12.0, "fig32_4": 12.0}
GAP, THIN = 16, 2
DRAWN = (meas.DRAWN[0], 0, meas.DRAWN[1] + 1, meas.CAPTURE_H)    # the columns the VDP draws
STRIP = (47, 50)                    # figure 32.1: lines 47 to 49 of the paper ...
STRIP_X = (8, 168)                  # ... columns 8 to 167
IN_A_ROW = 5                        # ... in five frames in a row
ROWS = (10, 14)                     # figure 32.3: split.rom's rows 10 to 13
CROWD = (4, 10)                     # figure 32.4: crowd.rom after these moves


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


def strip(im):
    """lines STRIP and columns STRIP_X of the paper"""
    return im.crop((meas.PAPER_X0 + STRIP_X[0], meas.PAPER_Y0 + STRIP[0],
                    meas.PAPER_X0 + STRIP_X[1], meas.PAPER_Y0 + STRIP[1]))


def main():
    m = json.load(open(os.path.join(HERE, "meas32.json")))

    def shots(name, k=None):
        s = m[name]["eu"]["shots"]
        return s[:IN_A_ROW] if k is None else s[k]
    k_crowd = [m["crowd"]["eu"]["k"].index(k) for k in CROWD]
    made = {
        # 32.1 - the first bar in five frames in a row: poll.rom, fifth.rom, steady.rom (50 Hz)
        "fig32_1": stacked([stacked([strip(frame(n, "eu", k)) for k in shots(n)], THIN)
                            for n in ("poll", "fifth", "steady")], 8),
        # 32.2 - poll.rom (left) and split.rom (right), 50 Hz, the drawn columns
        "fig32_2": side_by_side([frame(n, "eu", shots(n, 0)).crop(DRAWN) for n in ("poll", "split")]),
        # 32.3 - split.rom, 50 Hz: rows ROWS of the paper, the whole width
        "fig32_3": frame("split", "eu", shots("split", 0)).crop(
            (meas.PAPER_X0, meas.PAPER_Y0 + 8 * ROWS[0], meas.PAPER_X0 + 256, meas.PAPER_Y0 + 8 * ROWS[1])),
        # 32.4 - crowd.rom after CROWD moves, 50 Hz, the drawn columns
        "fig32_4": side_by_side([frame("crowd", "eu", shots("crowd", k)).crop(DRAWN) for k in k_crowd]),
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
