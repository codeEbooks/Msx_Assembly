#!/usr/bin/env python3
"""fig18.py - the figures of chapter 18, from the captures.

Parts of captures, set side by side or one under the other, and enlarged by
a whole number, nearest neighbour, to at least 300 dpi at the printed width.
Nothing is added but the white between two panels.
"""
import json
import math
import os
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
sys.path.insert(0, HERE)
import meas  # noqa: E402
import meas18  # noqa: E402

CAP = os.path.join(HERE, "captures")
MIN_DPI = 300
WIDTH = {"fig18_1": 14.0, "fig18_2": 9.0, "fig18_3": 9.0, "fig18_4": 14.0, "fig18_5": 10.0,
         "fig18_6": 9.0}
BOX_ROWS = (208, 240)       # figure 18.5: the capture's last 32 rows
GAP = 16
DRIFT_X = (40, 120)         # figure 18.4: the columns round the stripes' starts
WRONG_X = (100, 303)        # figure 18.6


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


def stacked(panels):
    out = Image.new("RGB", (max(p.width for p in panels), sum(p.height for p in panels)))
    y = 0
    for p in panels:
        out.paste(p, (0, y))
        y += p.height
    return out


def enlarge(im, width_cm):
    f = math.ceil(MIN_DPI * width_cm / 2.54 / im.width)
    return im.resize((im.width * f, im.height * f), Image.NEAREST), f


def shot(name):
    return Image.open(os.path.join(CAP, name)).convert("RGB")


def drawn(im):
    return im.crop((meas.DRAWN[0], 0, meas.DRAWN[1] + 1, im.height))


def film(name, xs):
    """the stripe's row and two rows either side of it, in each frame of the
    film, one frame under the other"""
    m = json.load(open(os.path.join(HERE, "meas18.json")))
    r = m["wrong"] if name == "wrong" else m["drift"][name]
    rows = []
    for sn in r["seen"]:
        im = shot(f"{name}_f{sn['frame']:04d}.png")
        rows.append(im.crop((xs[0], sn["row"] - 2, xs[1], sn["row"] + 3)))
    return stacked(rows)


def main():
    f = meas18.SHOT
    x0, y0 = meas.paper(0, 0)
    row = 8 * meas18.gen18.PAPER_ROW
    made = {
        # 18.1 - lines.rom on the 50 Hz machine (left) and the 60 Hz one (right)
        "fig18_1": side_by_side([drawn(shot(f"lines_eu_f{f:04d}.png")),
                                 drawn(shot(f"lines_jp_f{f:04d}.png"))]),
        # 18.2 - ruler.rom: every row, the drawn columns
        "fig18_2": drawn(shot(f"ruler_eu_f{f:04d}.png")),
        # 18.3 - paper.rom: the row of characters, the rows either side, and
        #        the border left of them
        "fig18_3": shot(f"paper_eu_f{f:04d}.png").crop(
            (meas.DRAWN[0], y0 + row - 8, x0 + 8 * 12, y0 + row + 16)),
        # 18.5 - box.rom on the 50 Hz machine (top) and the 60 Hz one (bottom):
        #        the capture's last 32 rows, the drawn columns
        "fig18_5": one_under_other([drawn(shot(f"box_{t}_f{f:04d}.png")).crop(
            (0, BOX_ROWS[0], meas.DRAWN[1] + 1 - meas.DRAWN[0], BOX_ROWS[1])) for t in ("eu", "jp")]),
        # 18.4 - f71363, f71364, f71365: the stripe in twelve frames
        "fig18_4": side_by_side([film(n, DRIFT_X) for n in ("f71363", "f71364", "f71365")]),
        # 18.6 - wrong.rom: the stripe in twelve frames
        "fig18_6": film("wrong", WRONG_X),
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
