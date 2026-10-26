#!/usr/bin/env python3
"""fig31.py - the figures of chapter 31, from the captures.

Parts of captures, set side by side or one above another, and enlarged by a
whole number, nearest neighbour, to at least 300 dpi at the printed width.
Nothing is added but the white between two panels. Every capture is a frame
meas31.py checked against the model.
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
WIDTH = {"fig31_1": 12.0, "fig31_2": 12.0, "fig31_3": 12.0, "fig31_4": 12.0}
GAP = 16
WHOLE = (0, 0, 256, 192)
LOADING = (5, 10, 15, 20)               # figure 31.1: otir.rom at 60 Hz after these bursts


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


def race(m):
    """paper.rom at 60 Hz: the frame that showed most pixels as they were
    before its paper's blocks, and the frame after it"""
    mixed = max(m["paper"]["jp"]["mixed"], key=lambda x: x["old"])
    return mixed["frame"], mixed["frame"] + 1


def main():
    m = json.load(open(os.path.join(HERE, "meas31.json")))
    of = m["otir"]["jp"]["frames"]
    load = [paper(frame("otir", "jp", of[k - 1]), WHOLE) for k in LOADING]
    made = {
        # 31.1 - otir.rom, 60 Hz machine: the picture after 5, 10, 15 and 20 bursts
        "fig31_1": stacked([side_by_side(load[:2]), side_by_side(load[2:])]),
        # 31.2 - paper.rom, 60 Hz machine: a frame written into while drawn, and the next
        "fig31_2": side_by_side([paper(frame("paper", "jp", k), WHOLE) for k in race(m)]),
        # 31.3 - halt.rom (left) and hook.rom (right) at the end, 60 Hz machine
        "fig31_3": side_by_side([paper(frame(n, "jp", m["irq"][n]["jp"]["shot"]), WHOLE)
                                 for n in ("halt", "hook")]),
        # 31.4 - fixed.rom at the end: the 50 Hz machine (left), the 60 Hz machine (right)
        "fig31_4": side_by_side([paper(frame("fixed", t, m["fixed"][t]["shot"]), WHOLE)
                                 for t in ("eu", "jp")]),
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
