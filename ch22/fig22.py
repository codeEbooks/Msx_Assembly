#!/usr/bin/env python3
"""fig22.py - the figures of chapter 22, from the captures.

Parts of captures, set side by side or one under the other, and enlarged by
a whole number, nearest neighbour, to at least 300 dpi at the printed width.
Nothing is added but the white between two panels.
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
WIDTH = {"fig22_1": 14.0, "fig22_2": 8.0, "fig22_3": 10.0, "fig22_4": 14.0, "fig22_5": 10.0}
GAP = 16
MASKS_SHOWN = (0, 1, 4, 7)  # figure 22.4: every bit set, R#4 = $00, R#3 = $9F, M1 and M3
MASKS_COLS = (0, 10)        # ... columns of characters 0 to 9 of each, all 24 rows
LEAK_ROWS = (0, 6)          # figure 22.5: rows 0 to 5 of each state


def side_by_side(panels):
    w = sum(p.width for p in panels) + GAP * (len(panels) - 1)
    out = Image.new("RGB", (w, max(p.height for p in panels)), (255, 255, 255))
    x = 0
    for p in panels:
        out.paste(p, (x, 0))
        x += p.width + GAP
    return out


def one_under_other(panels):
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


def shot(name):
    return Image.open(os.path.join(CAP, name)).convert("RGB")


def film(prefix):
    """the one capture whose name starts with PREFIX"""
    got = [f for f in sorted(os.listdir(CAP)) if f.startswith(prefix)]
    assert len(got) == 1, (prefix, got)
    return got[0]


def paper_rows(im, rows):
    """character rows rows[0] to rows[1] - 1 of the paper, all its columns"""
    x0, y0 = meas.paper(0, 0)
    return im.crop((x0, y0 + 8 * rows[0], x0 + meas.PAPER_W, y0 + 8 * rows[1]))


def paper_cols(im, cols):
    """columns of characters cols[0] to cols[1] - 1 of the paper, all its rows"""
    x0, y0 = meas.paper(0, 0)
    return im.crop((x0 + 8 * cols[0], y0, x0 + 8 * cols[1], y0 + meas.PAPER_H))


def main():
    made = {
        # 22.1 - lowbyte.rom (left) and highbyte.rom (right): each byte of the
        # patterns showing the low byte and the high byte of its own address
        "fig22_1": side_by_side([paper_rows(shot(f"{n}_eu_f0030.png"), (0, 24))
                                 for n in ("lowbyte", "highbyte")]),
        # 22.2 - diag.rom: the two lines drawn with vaddr
        "fig22_2": paper_rows(shot("diag_eu_f0030.png"), (0, 24)),
        # 22.3 - tiles3.rom: the picture of eight tiles (tiles1.rom's is the same)
        "fig22_3": paper_rows(shot("tiles3_eu_f0030.png"), (0, 24)),
        # 22.4 - masks.rom: four states, the first ten columns of each
        "fig22_4": side_by_side([paper_cols(shot(film(f"masks{k}_eu_f")), MASKS_COLS)
                                 for k in MASKS_SHOWN]),
        # 22.5 - leak.rom: the Graphic I page, the same page with M3 set, the fix
        "fig22_5": one_under_other([paper_rows(shot(film(f"leak_{t}_eu_f")), LEAK_ROWS)
                                    for t in ("gi", "m3", "fix")]),
    }
    out = {}
    for name, im in made.items():
        big, k = enlarge(im, WIDTH[name])
        path = os.path.join(HERE, f"{name}.png")
        big.save(path)
        out[name] = (path, WIDTH[name], k, big.size)
    return out


if __name__ == "__main__":
    for name, (path, w, k, size) in main().items():
        print(f"{name}: x{k} -> {size[0]} x {size[1]} px, {w} cm, {size[0] / (w / 2.54):.0f} dpi")
