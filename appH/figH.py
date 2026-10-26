#!/usr/bin/env python3
"""figH.py - figure H.1, the gallery of broken screens, from captures/.

The twelve photographs measH.py filmed again (step gallery), whole, four to a
row in the order of measH.GALLERY, enlarged by a whole number, nearest
neighbour, to at least 300 dpi at the printed width. Nothing is added but the
white between two panels.

    python3 measH.py gallery && python3 figH.py
"""
import math
import os
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import measH  # noqa: E402

CAP = os.path.join(HERE, "captures")
MIN_DPI = 300
WIDTH_CM = 14.4             # the printed width of the figure
PER_ROW = 4
GAP = 16                    # white between two panels, in pixels of the figure


def gallery():
    names = list(measH.GALLERY)
    shots = [Image.open(os.path.join(CAP, f"{n}.png")).convert("RGB") for n in names]
    w, h = shots[0].size
    assert all(s.size == (w, h) for s in shots), [s.size for s in shots]
    rows = math.ceil(len(shots) / PER_ROW)
    # the smallest whole factor that keeps each panel at 300 dpi or more
    panel_cm = (WIDTH_CM - 0) / PER_ROW
    f = 1
    while (w * f) / (panel_cm / 2.54) < MIN_DPI or \
            (PER_ROW * w * f + (PER_ROW - 1) * GAP) / (WIDTH_CM / 2.54) < MIN_DPI:
        f += 1
    out = Image.new("RGB", (PER_ROW * w * f + (PER_ROW - 1) * GAP, rows * h * f + (rows - 1) * GAP),
                    (255, 255, 255))
    for k, s in enumerate(shots):
        x, y = (k % PER_ROW) * (w * f + GAP), (k // PER_ROW) * (h * f + GAP)
        out.paste(s.resize((w * f, h * f), Image.NEAREST), (x, y))
    dpi = out.width / (WIDTH_CM / 2.54)
    assert dpi >= MIN_DPI, dpi
    path = os.path.join(HERE, "figH_1.png")
    out.save(path, optimize=False)
    return path, f, round(dpi)


if __name__ == "__main__":
    print(gallery())
