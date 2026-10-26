#!/usr/bin/env python3
"""fig29.py - the figures of chapter 29, from the captures.

Parts of captures, set side by side or one above another, and enlarged by a
whole number, nearest neighbour, to at least 300 dpi at the printed width.
Nothing is added but the white between two panels. Every capture is a frame
meas29.py checked against the model and the ideal, on the 50 Hz machine.
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
import gen29  # noqa: E402

CAP = os.path.join(HERE, "captures")
MIN_DPI = 300
WIDTH = {"fig29_1": 12.0, "fig29_2": 12.0, "fig29_3": 12.0, "fig29_4": 12.0}
GAP = 16
WHOLE = (0, 0, 256, 192)                # figures 29.1 and 29.3: the whole paper
COARSE_AT = (0, 16)                     # figure 29.1: the window at these columns
FINE = (88, 120, 152, 184)              # figure 29.2: each frame ...
FINE_AT = tuple(range(8, 16))           # ... with these pixels gone by: shifts 0 to 7
VERT_AT = (4, 60)                       # figure 29.3: these lines gone by
PILLAR = (144, 68, 176, 132)            # figure 29.4: each frame ...
PILLAR_AT = tuple(range(8, 16))         # ... with these pixels gone by


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


def frame(name, k):
    return Image.open(os.path.join(CAP, f"{name}_eu_f{k:04d}.png")).convert("RGB")


def paper(im, box):
    x0, y0 = meas.paper(0, 0)
    return im.crop((x0 + box[0], y0 + box[1], x0 + box[2], y0 + box[3]))


def shot(m, name, at):
    """the photograph of the frame whose window is AT"""
    path = {"coarse": gen29.coarse_path}.get(name, gen29.fine_path)()
    return frame(name, m[name]["eu"]["frames"][path.index(at)])


def main():
    m = json.load(open(os.path.join(HERE, "meas29.json")))
    made = {
        # 29.1 - coarse.rom: the window at column 0 and at column 16
        "fig29_1": side_by_side([paper(shot(m, "coarse", a), WHOLE) for a in COARSE_AT]),
        # 29.2 - sets.rom: a hill, a pixel a frame, over the status line, which stays:
        #        shifts 0 to 3 above, 4 to 7 below
        "fig29_2": stacked([side_by_side([paper(shot(m, "sets", a), FINE) for a in FINE_AT[:4]]),
                            side_by_side([paper(shot(m, "sets", a), FINE) for a in FINE_AT[4:]])]),
        # 29.3 - vertical.rom: two frames
        "fig29_3": side_by_side([paper(shot(m, "vertical", a), WHOLE) for a in VERT_AT]),
        # 29.4 - pillar.rom: the pillar at shifts 0 to 7
        "fig29_4": side_by_side([paper(shot(m, "pillar", a), PILLAR) for a in PILLAR_AT]),
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
