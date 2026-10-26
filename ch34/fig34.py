#!/usr/bin/env python3
"""fig34.py - the figures of chapter 34, from the captures.

Parts of captures, set side by side, and enlarged by a whole number, nearest
neighbour, to at least 300 dpi at the printed width. Nothing is added but the
white between two panels. Every capture is a frame meas34.py checked against
the model, pixel by pixel.
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
import gen34  # noqa: E402

CAP = os.path.join(HERE, "captures")
MIN_DPI = 300
WIDTH = {"fig34_1": 12.0, "fig34_2": 11.0, "fig34_3": 12.0, "fig34_4": 9.0}
GAP = 16
LEGEND = (0, 4, 168, 116)           # figure 34.1: text rows 1 to 13, columns 0 to 20
MATRIX = (0, 4, 144, 116)           # figure 34.2: text rows 1 to 13, columns 0 to 17
SNSMAT = (0, 4, 168, 68)            # figure 34.3: text rows 1 to 7, columns 0 to 20
DEFINE = (0, 0, 184, 104)           # figure 34.4: text rows 0 to 12, columns 0 to 22
GHOST_SHOT = gen34.COMBOS[-1][0] + 2
DEFINE_SHOT = 185
SNSMAT_SHOTS = (151, 152)


def side_by_side(panels, gap=GAP):
    w = sum(p.width for p in panels) + gap * (len(panels) - 1)
    out = Image.new("RGB", (w, max(p.height for p in panels)), (255, 255, 255))
    x = 0
    for p in panels:
        out.paste(p, (x, 0))
        x += p.width + gap
    return out


def enlarge(im, width_cm):
    f = math.ceil(MIN_DPI * width_cm / 2.54 / im.width)
    return im.resize((im.width * f, im.height * f), Image.NEAREST), f


def paper(name, tag, k, box):
    im = Image.open(os.path.join(CAP, f"{name}_{tag}_f{k:04d}.png")).convert("RGB")
    x0, y0, x1, y1 = box
    return im.crop((meas.PAPER_X0 + x0, meas.PAPER_Y0 + y0, meas.PAPER_X0 + x1, meas.PAPER_Y0 + y1))


def main():
    m = json.load(open(os.path.join(HERE, "meas34.json")))
    shot = m["legend"]["eu"]["shot"]
    made = {
        # 34.1 - legend.rom: rows 0 to 5 as the BIOS types them, 50 Hz (left), 60 Hz (right)
        "fig34_1": side_by_side([paper("legend", t, shot, LEGEND) for t in ("eu", "jp")]),
        # 34.2 - matrix.rom: RIGHT, SPACE and S held; MSXBOOK_EU16 (left), _EU16G (right)
        "fig34_2": side_by_side([paper("matrix", t, GHOST_SHOT, MATRIX) for t in ("eu", "eug")]),
        # 34.3 - snsmat.rom at 50 Hz: a tap of one frame, and the frame after it
        "fig34_3": side_by_side([paper("snsmat", "eu", k, SNSMAT) for k in SNSMAT_SHOTS]),
        # 34.4 - define.rom at 50 Hz: the keys chosen, the figure moved, FIRE held
        "fig34_4": paper("define", "eu", DEFINE_SHOT, DEFINE),
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
