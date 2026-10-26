#!/usr/bin/env python3
"""fig39.py - the figures of chapter 39, from the captures.

Parts of captures, set side by side, and enlarged by a whole number, nearest
neighbour, to at least 300 dpi at the printed width. Nothing is added but the
white between two panels. meas39.py checked every capture against the
picture vdpscreen.py draws from the VRAM and the registers the debugger read
at that frame, pixel by pixel.
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
WIDTH = {"fig39_1": 12.0, "fig39_2": 7.0, "fig39_3": 10.0}
GAP = 16
ROOM = (0, 0, 256, 192)             # figure 39.1: the whole paper
MAP = (72, 40, 184, 152)            # figure 39.2: the map, rows 5 to 18, columns 9 to 22
PAIRS = (40, 24, 112, 152)          # figure 39.3: the two pairs


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


def paper(png, box):
    """part of a capture: BOX, in pixels of the paper"""
    im = Image.open(os.path.join(CAP, png)).convert("RGB")
    x0, y0, x1, y1 = box
    return im.crop((meas.PAPER_X0 + x0, meas.PAPER_Y0 + y0, meas.PAPER_X0 + x1, meas.PAPER_Y0 + y1))


def main():
    # the captures meas39.py took and checked, by the names it kept
    m = json.load(open(os.path.join(HERE, "meas39.json")))
    photos = m["walls"]["photos"]
    made = {
        # 39.1 - walls.asm, every ball stopped; corners.asm, the first ball over the post
        "fig39_1": side_by_side([paper(photos["walls"], ROOM), paper(photos["corners"], ROOM)]),
        # 39.2 - shapes.asm: the map
        "fig39_2": paper(m["shapes"]["photo"], MAP),
        # 39.3 - meet.asm and blame.asm, every pair stopped
        "fig39_3": side_by_side([paper(m["pairs"][n]["photo"], PAIRS) for n in ("meet", "blame")]),
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
