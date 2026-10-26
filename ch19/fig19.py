#!/usr/bin/env python3
"""fig19.py - the figures of chapter 19, from the captures.

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
sys.path.insert(0, HERE)
import meas  # noqa: E402
import meas19  # noqa: E402

CAP = os.path.join(HERE, "captures")
MIN_DPI = 300
WIDTH = {"fig19_1": 9.0, "fig19_2": 9.0, "fig19_3": 10.0, "fig19_4": 14.0, "fig19_5": 14.0}
ADDRESS_ROWS = (1, 12)      # figure 19.1: rows of characters, the first and one past the last
READBACK_ROWS = (0, 13)     # figure 19.2
STATUS_ROWS = (200, 232)    # figure 19.3: capture rows round the band
SHARE_ROWS = (19, 24)       # figure 19.5: the last third's text and the last row
GAP = 16


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


def drawn(im):
    return im.crop((meas.DRAWN[0], 0, meas.DRAWN[1] + 1, im.height))


def paper_rows(im, rows):
    """character rows rows[0] to rows[1] - 1 of the paper, all its columns"""
    x0, y0 = meas.paper(0, 0)
    return im.crop((x0, y0 + 8 * rows[0], x0 + meas.PAPER_W, y0 + 8 * rows[1]))


def paper(im):
    x0, y0 = meas.paper(0, 0)
    return im.crop((x0, y0, x0 + meas.PAPER_W, y0 + meas.PAPER_H))


def main():
    f = meas19.SHOT
    n = meas19.N_FRAMES
    made = {
        # 19.1 - address.rom: the rows of characters it wrote
        "fig19_1": paper_rows(shot(f"address_eu_f{f:04d}.png"), ADDRESS_ROWS),
        # 19.2 - readback.rom: the four words and their labels
        "fig19_2": paper_rows(shot(f"readback_eu_f{f:04d}.png"), READBACK_ROWS),
        # 19.3 - status.rom on the 50 Hz machine (top) and the 60 Hz one
        #        (bottom): the rows round the band, the drawn columns
        "fig19_3": one_under_other([drawn(shot(f"status_{t}_f{f:04d}.png")).crop(
            (0, STATUS_ROWS[0], meas.DRAWN[1] + 1 - meas.DRAWN[0], STATUS_ROWS[1]))
            for t in ("eu", "jp")]),
        # 19.4 - split.rom (left) and fixed.rom (right): the paper
        "fig19_4": side_by_side([paper(shot(f"{p}_eu_f{n:04d}.png")) for p in ("split", "fixed")]),
        # 19.5 - share.rom (left) and whole.rom (right): the paper's last five rows
        "fig19_5": side_by_side([paper_rows(shot(f"{p}_eu_f{n:04d}.png"), SHARE_ROWS)
                                 for p in ("share", "whole")]),
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
