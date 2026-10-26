#!/usr/bin/env python3
"""fig20.py - the figures of chapter 20, from the captures.

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

CAP = os.path.join(HERE, "captures")
MIN_DPI = 300
WIDTH = {"fig20_1": 10.0, "fig20_2": 14.0, "fig20_3": 10.0, "fig20_4": 10.0, "fig20_5": 10.0,
         "fig20_6": 10.0, "fig20_7": 10.0, "fig20_8": 14.0}
BEAT_ROWS = (0, 20)         # figure 20.1: the label, the 228 pairs, the key
BEATS_ROWS = (0, 17)        # figure 20.2: the label and the 228 pairs
BEATS = (12, 17, 24, 25)    # ... of these four cartridges, two by two
EDGE_ROWS = (0, 5)          # figure 20.4: the label and the four rows
READ_ROWS = (0, 17)         # figure 20.5: the three texts and their labels
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


def paper_rows(im, rows):
    """character rows rows[0] to rows[1] - 1 of the paper, all its columns"""
    x0, y0 = meas.paper(0, 0)
    return im.crop((x0, y0 + 8 * rows[0], x0 + meas.PAPER_W, y0 + 8 * rows[1]))


def main():
    made = {
        # 20.1 - beat.rom: the pairs, sixteen to a row, in the order of their T-states
        "fig20_1": paper_rows(shot("beat_eu_f0008.png"), BEAT_ROWS),
        # 20.2 - beat12.rom, beat17.rom (above), beat24.rom, beat25.rom (below)
        "fig20_2": one_under_other([side_by_side([paper_rows(shot(f"beat{g}_eu_f0008.png"),
                                                             BEATS_ROWS) for g in pair])
                                    for pair in (BEATS[:2], BEATS[2:])]),
        # 20.3 - speeds.rom: the six loops
        "fig20_3": paper_rows(shot("speeds_eu_f0012.png"), (0, 24)),
        # 20.4 - edge.rom (above) and bottom.rom (below): unrolled OUTI across
        # the top and across the bottom of the paper
        "fig20_4": one_under_other([paper_rows(shot(f"{p}_eu_f0008.png"), EDGE_ROWS)
                                    for p in ("edge", "bottom")]),
        # 20.5 - reads.rom: the text, what INIR read, what INI and JP NZ read
        "fig20_5": paper_rows(shot("reads_eu_f0008.png"), READ_ROWS),
        # 20.6 - sprites.rom: three loops, and four sprites in every line from 128
        "fig20_6": paper_rows(shot("sprites_eu_f0012.png"), (0, 24)),
        # 20.7 - speeds.rom with too_fast_vram_access set to ignore
        "fig20_7": paper_rows(shot("speeds_ignore_eu_f0012.png"), (0, 24)),
        # 20.8 - otir.rom (left) and outi.rom (right): the page
        "fig20_8": side_by_side([paper_rows(shot(f"{p}_eu_f0010.png"), (0, 24))
                                 for p in ("otir", "outi")]),
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
