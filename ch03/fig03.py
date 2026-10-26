#!/usr/bin/env python3
"""fig03.py - the figures of chapter 3, cropped from the captures.

Crops of the paper are whole 8 x 8 character cells; enlargement is by a whole
number, nearest neighbour, to at least 300 dpi at the printed width. Nothing
is added but white gaps between panels and a thin grey line round panels
whose edge would otherwise vanish into a white page. The pages are black ink
on white paper, and the stripes of figure 3.4 white on a black border: two
greys in print.
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
FULL = 15.29
# the print width of each figure, in cm; chapter03.py uses the same numbers
WIDTH = {"fig03_1": 10.5, "fig03_2": FULL, "fig03_3": 10.0, "fig03_4": FULL,
         "fig03_5": 10.0, "fig03_6": 11.0, "fig03_7": 10.5, "fig03_8": 9.0}


def cap(name):
    return Image.open(os.path.join(CAP, name)).convert("RGB")


def paper(name, col0, row0, cols, rows, border=0):
    """a crop of whole cells of the paper, with `border` pixels around"""
    x0, y0 = meas.paper(8 * col0, 8 * row0)
    return cap(name).crop((x0 - border, y0 - border, x0 + 8 * cols + border, y0 + 8 * rows + border))


def framed(im, grey=(128, 128, 128)):
    """a one-pixel grey line round a panel, outside it"""
    out = Image.new("RGB", (im.width + 2, im.height + 2), grey)
    out.paste(im, (1, 1))
    return out


def joined(panels, across, gap=GAP):
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
        # 3.1 - memmap: the heading (row 1) to the total (row 11), 30 columns
        "fig03_1": paper("memmap_f0160.png", 0, 1, 30, 11),
        # 3.2 - slots, as every capture in the book runs it (left) and with the
        # cartridge declared an ordinary one (right): heading to page numbers
        "fig03_2": joined([framed(paper(f"{n}_f0600.png", 0, 1, 32, 17, border=4))
                           for n in ("slots", "slots_normal")], across=True),
        # 3.3 - sysvars: the heading (row 1) to the interrupt flag (row 21)
        "fig03_3": paper("sysvars_f0030.png", 0, 1, 30, 21),
        # 3.4 - nops: capture rows 214 to 239, the whole width: the bottom
        # border, with the three stripes, four lines each
        "fig03_4": cap("nops_f0030.png").crop((0, 214, 320, 240)),
        # 3.5 - vdp: rows 2 to 8, 29 columns
        "fig03_5": paper("vdp_f0030.png", 0, 2, 29, 7),
        # 3.6 - keys: frame 40 (nothing held) and 60 (Q held), heading to $A8
        "fig03_6": joined([framed(paper(f"keys_f{n:04d}.png", 0, 1, 16, 19, border=4))
                           for n in (40, 60)], across=True),
        # 3.7 - psg: the YM2149 of the book's machine (above) and an AY-3-8910
        # (below), rows 1 to 11
        "fig03_7": joined([framed(paper(f"{n}_f0030.png", 0, 1, 32, 11, border=4))
                           for n in ("psg", "psg_ay")], across=False),
        # 3.8 - page 0 switched with interrupts off (above) and on (below),
        # frame 100: rows 0 to 6
        "fig03_8": joined([framed(paper(f"{n}_f0100.png", 0, 0, 32, 7, border=8))
                           for n in ("page0_di", "page0_ei")], across=False),
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
