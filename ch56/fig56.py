#!/usr/bin/env python3
"""fig56.py - the figures of chapter 56, from the captures meas56.py kept.

    fig56_1  LANTERN KEEP's label, as label56.py made it: 1,386 x 1,228 dots
             at 400 an inch, printed at its own size, 88 x 78 mm
    fig56_2  GRIN ALLEY's, the same way
    fig56_3  lantern_keep_a14.bin, the image for a board that drives the
             EPROM's A14 from the slot's A14: given to openMSX as a cartridge
             file, which openMSX places by guessing (left), and on the other
             board, the mapping openMSX is told with -romtype page12 (right).
             WHERE IT BREAKS

Film frames, each the drawn columns and all 240 lines (chapter 4), enlarged
by a whole number, nearest neighbour, to at least 300 dpi at the printed
width; meas56.py checked every capture against vdpscreen.py's picture of the
VRAM the debugger read in that frame.
"""
import math
import os
import shutil
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
import meas  # noqa: E402

CAP = os.path.join(HERE, "captures")
MIN_DPI = 300
WIDTH = {"fig56_1": 8.8, "fig56_2": 8.8, "fig56_3": 14.0}
GAP = 16


def drawn(png):
    im = Image.open(os.path.join(CAP, png)).convert("RGB")
    return im.crop((meas.DRAWN[0], 0, meas.DRAWN[1] + 1, meas.CAPTURE_H))


def main():
    out = {}
    # 56.1 and 56.2: the labels themselves
    for fig, name in (("fig56_1", "lantern_keep"), ("fig56_2", "grin_alley")):
        path = os.path.join(HERE, f"{fig}.png")
        shutil.copy(os.path.join(HERE, f"label_{name}.png"), path)
        out[fig] = (path, WIDTH[fig], 1, Image.open(path).size)
    # 56.3: two frames side by side
    panels = [drawn("wrong_guessed.png"), drawn("wrong_board.png")]
    w = sum(p.width for p in panels) + GAP
    pair = Image.new("RGB", (w, max(p.height for p in panels)), (255, 255, 255))
    pair.paste(panels[0], (0, 0))
    pair.paste(panels[1], (panels[0].width + GAP, 0))
    k = math.ceil(MIN_DPI * WIDTH["fig56_3"] / 2.54 / pair.width)
    big = pair.resize((pair.width * k, pair.height * k), Image.NEAREST)
    path = os.path.join(HERE, "fig56_3.png")
    big.save(path)
    out["fig56_3"] = (path, WIDTH["fig56_3"], k, big.size)
    return out


if __name__ == "__main__":
    for name, (path, w, k, size) in main().items():
        print(f"{name}: x{k} -> {size[0]} x {size[1]} px, {w} cm, {size[0] / (w / 2.54):.0f} dpi")
