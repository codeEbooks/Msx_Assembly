#!/usr/bin/env python3
"""fig21.py - the figures of chapter 21, from the captures.

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
WIDTH = {"fig21_1": 10.0, "fig21_2": 14.0, "fig21_3": 14.0, "fig21_4": 14.0,
         "fig21_5": 10.0, "fig21_6": 10.0, "fig21_7": 9.0}
GAP = 16
BITS_SHOWN = (0, 1, 3)      # figure 21.6: Graphic I, text mode, M1 and M2
BITS_ROWS = (0, 8)          # ... rows 0 to 7 of each


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


def film(prefix):
    """the one capture whose name starts with PREFIX"""
    got = [f for f in sorted(os.listdir(CAP)) if f.startswith(prefix)]
    assert len(got) == 1, (prefix, got)
    return got[0]


def bits_film(k):
    return film(f"bits{k}_eu_f")


def flip_films():
    """flip.rom's photographs, in the order of their film frames"""
    return sorted(f for f in os.listdir(CAP) if f.startswith("flip_eu_f"))


def switch_films():
    """switch.rom's two photographs: before the switch, and after it"""
    got = sorted(f for f in os.listdir(CAP) if f.startswith("switch_eu_f"))
    assert len(got) == 2, got
    return got


def main():
    made = {
        # 21.1 - flip.rom: the page with R#2 = 6 (above) and with R#2 = 7 (below)
        "fig21_1": one_under_other([paper_rows(shot(f), (0, 4)) for f in flip_films()[:2]]),
        # 21.2 - the picture in text mode and Graphic I (above), Graphic II and
        # multicolour (below)
        "fig21_2": one_under_other([side_by_side([paper_rows(shot(f"{n}_eu_f0030.png"), (0, 24))
                                                  for n in pair])
                                    for pair in (("text", "graphic1"), ("graphic2", "multi"))]),
        # 21.3 - the two lines of words in text mode (above) and Graphic I (below)
        "fig21_3": one_under_other([paper_rows(shot(f"{n}_eu_f0030.png"), (0, 2))
                                    for n in ("text", "graphic1")]),
        # 21.4 - chars.rom: the 256 characters in Graphic I (above) and text mode (below)
        "fig21_4": one_under_other([paper_rows(shot(film("chars_g1_eu_f")), (0, 8)),
                                    paper_rows(shot(film("chars_tx_eu_f")), (0, 7))]),
        # 21.5 - bands.rom: every name 0 in multicolour
        "fig21_5": paper_rows(shot("bands_eu_f0030.png"), (0, 8)),
        # 21.6 - bits.rom: the same page in three states of R#1
        "fig21_6": one_under_other([paper_rows(shot(bits_film(k)), BITS_ROWS)
                                    for k in BITS_SHOWN]),
        # 21.7 - switch.rom: the page in Graphic I (above), then moved to text mode
        "fig21_7": one_under_other([paper_rows(shot(f), (0, 7)) for f in switch_films()]),
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
