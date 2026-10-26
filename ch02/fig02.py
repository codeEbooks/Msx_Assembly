#!/usr/bin/env python3
"""fig02.py - the figures of chapter 2, cropped from the captures.

Crops are whole 8 x 8 character cells of the paper; enlargement is by a whole
number, nearest neighbour, to at least 300 dpi at the printed width. Nothing
is added but the white gaps between panels and, in figure 2.7, a thin grey
line round each of the two screens, so that the empty top row of the second
can be seen on a white page. The digits and the boxes in these figures were
drawn by the MSX, in black ink on white paper, which is what a page printed
in black and white wants.
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
GAP = 12
# the print width of each figure, in cm; chapter02.py uses the same numbers
WIDTH = {"fig02_1": 10.5, "fig02_2": 13.0, "fig02_3": 10.5, "fig02_4": 10.0,
         "fig02_5": 9.5, "fig02_6": 9.5, "fig02_7": 10.5}


def paper(name, col0, row0, cols, rows, border=0):
    """a crop of whole cells of the paper, with `border` pixels around"""
    x0, y0 = meas.paper(8 * col0, 8 * row0)
    im = Image.open(os.path.join(CAP, name)).convert("RGB")
    return im.crop((x0 - border, y0 - border, x0 + 8 * cols + border, y0 + 8 * rows + border))


def framed(im, grey=(128, 128, 128)):
    """a one-pixel grey line round a panel, outside it: no pixel of the
    capture is covered"""
    out = Image.new("RGB", (im.width + 2, im.height + 2), grey)
    out.paste(im, (1, 1))
    return out


def joined(panels, across, gap=GAP):
    """panels side by side (across) or one above the other, white between"""
    if across:
        size = (sum(p.width for p in panels) + gap * (len(panels) - 1), max(p.height for p in panels))
    else:
        size = (max(p.width for p in panels), sum(p.height for p in panels) + gap * (len(panels) - 1))
    out = Image.new("RGB", size, (255, 255, 255))
    at = 0
    for p in panels:
        out.paste(p, (at, 0) if across else (0, at))
        at += (p.width if across else p.height) + gap
    return out


def enlarge(im, width_cm):
    f = math.ceil(MIN_DPI * width_cm / 2.54 / im.width)
    return im.resize((im.width * f, im.height * f), Image.NEAREST), f


def main():
    made = {
        # 2.1 - count: the headings (row 1) to the last number (row 18)
        "fig02_1": paper("count_f0030.png", 0, 1, 32, 18),
        # 2.2 - chars on the two machines: the column digits (row 1) to the
        # last row (row 15), from the row digits (column 6)
        "fig02_2": joined([paper(f"{n}_f0030.png", 6, 1, 18, 15, border=4)
                           for n in ("chars", "chars_jp")], across=True),
        # 2.3 - arith: the headings (row 2) to the stored number (row 21)
        "fig02_3": paper("arith_f0030.png", 0, 2, 32, 20),
        # 2.4 - shifts: the headings (row 2) to the ninth line (row 20)
        "fig02_4": paper("shifts_f0030.png", 0, 2, 31, 19),
        # 2.5 - fields: the headings (row 2) to the last byte (row 16)
        "fig02_5": paper("fields_f0030.png", 0, 2, 30, 15),
        # 2.6 - fixed: the headings (row 2) to the ninth line (row 20)
        "fig02_6": paper("fixed_f0030.png", 1, 2, 28, 19),
        # 2.7 - the top six character rows of the two screens, 8 pixels of
        # white border around them, and a grey line round each
        "fig02_7": joined([framed(paper(f"{n}_f0030.png", 0, 0, 32, 6, border=8))
                           for n in ("addr_hex", "addr_dec")], across=False),
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
