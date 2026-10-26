#!/usr/bin/env python3
"""fig04.py - the figures of chapter 4, cropped from the captures.

Crops are whole 8 x 8 character cells of the paper, or whole lines of the
capture; enlargement is by a whole number, nearest neighbour, to at least
300 dpi at the printed width. The only thing added is the white gap between
the two panels of figure 4.3; the text was drawn by the MSX, black ink on
white paper.
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
# the print width of each figure, in cm; chapter04.py uses the same numbers
FULL = 15.29                        # the column is 15.2976 cm
WIDTH = {"fig04_1": 10.5, "fig04_2": 10.5, "fig04_3": FULL}
GAP = 12


def paper(name, col0, row0, cols, rows):
    x0, y0 = meas.paper(8 * col0, 8 * row0)
    im = Image.open(os.path.join(CAP, name)).convert("RGB")
    return im.crop((x0, y0, x0 + 8 * cols, y0 + 8 * rows))


def lines(name, y0, y1):
    """whole lines of a capture, the full width"""
    im = Image.open(os.path.join(CAP, name)).convert("RGB")
    return im.crop((0, y0, im.width, y1))


def stacked(panels, gap=GAP):
    out = Image.new("RGB", (max(p.width for p in panels), sum(p.height for p in panels) +
                            gap * (len(panels) - 1)), (255, 255, 255))
    y = 0
    for p in panels:
        out.paste(p, (0, y))
        y += p.height + gap
    return out


def enlarge(im, width_cm):
    f = math.ceil(MIN_DPI * width_cm / 2.54 / im.width)
    return im.resize((im.width * f, im.height * f), Image.NEAREST), f


def main():
    made = {
        # 4.1 - check.rom on the book's machine, frame 60: the title (row 1)
        # to the turns (row 12)
        "fig04_1": paper("check_book_eu_f0060.png", 0, 1, 32, 12),
        # 4.2 - the same cartridge on openMSX's default machine
        "fig04_2": paper("check_default_f0060.png", 0, 1, 32, 12),
        # 4.3 - edge.rom, frame 30, on the book's openMSX (top) and on 21.0
        # (below): capture lines 214 to 239, the bottom border, full width
        "fig04_3": stacked([lines(f"edge_{v}_f0030.png", 214, 240) for v in ("book", "210")]),
    }
    out = {}
    for name, im in made.items():
        big, f = enlarge(im, WIDTH[name])
        path = os.path.join(HERE, f"{name}.png")
        big.save(path)
        out[name] = (path, WIDTH[name], f, big.size)
    return out


if __name__ == "__main__":
    for name, (path, w, f, size) in main().items():
        print(f"{name}: x{f} -> {size[0]} x {size[1]} px, {w} cm, {size[0] / (w / 2.54):.0f} dpi")
