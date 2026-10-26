#!/usr/bin/env python3
"""fig38.py - the figures of chapter 38, from the captures.

Parts of captures, set side by side, and enlarged by a whole number, nearest
neighbour, to at least 300 dpi at the printed width. Nothing is added but the
white between two panels. meas38.py checked every capture: against the screen
drawn from the debugger's values (pages.asm), from the program's variables
(the cartridges that print their line), and from the VRAM read at that frame
(all of them), pixel by pixel.
"""
import math
import os
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
import meas  # noqa: E402

CAP = os.path.join(HERE, "captures")
MIN_DPI = 300
WIDTH = {"fig38_1": 12.0, "fig38_2": 12.0, "fig38_3": 12.0}
GAP = 16
PAGES = (0, 8, 240, 128)            # figure 38.1: text rows 1 to 15, columns 0 to 29
CART = (0, 8, 240, 80)              # figure 38.2: text rows 1 to 9, columns 0 to 29
BROKEN = (0, 8, 240, 128)           # figure 38.3: text rows 1 to 15, columns 0 to 29
SHOT = 30


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
    made = {
        # 38.1 - pages.asm with the RAM in 3-2, and with the cartridge in 1-1
        "fig38_1": side_by_side([paper("pages", t, 10, PAGES) for t in ("eux", "eue")]),
        # 38.2 - the cartridge in 1-1: own32.asm, and cart32.asm with C-BIOS's ENASLT
        "fig38_2": side_by_side([paper(n, "eue", SHOT, CART) for n in ("own32", "cart32")]),
        # 38.3 - stay32.asm on the reference machine, quick32.asm in 1-1
        "fig38_3": side_by_side([paper("stay32", "eu", SHOT, BROKEN), paper("quick32", "eue", SHOT, BROKEN)]),
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
