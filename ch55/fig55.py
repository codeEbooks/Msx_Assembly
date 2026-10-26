#!/usr/bin/env python3
"""fig55.py - the figures of chapter 55, from the captures meas55.py kept.

Each figure is one page or two, one above the other: of each capture, the columns
the VDP draws (chapter 4) and the lines from the top of the capture to the row
under the program's last, enlarged five times, nearest neighbour, in a light
grey frame one enlarged pixel wide, since the page is white (chapter 51). meas55.py
checked every capture against vdpscreen.py's picture of the VRAM the debugger
read, frame 58 after INIT.

    fig55_1  check.rom on MSXBOOK_EU16 (50 Hz) and MSXBOOK_JP16 (60 Hz)
    fig55_2  dirty.rom on MSXBOOK_EU16B, whose RAM starts as a real MSX1's:
             WHERE IT BREAKS
"""
import os
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
import meas  # noqa: E402

CAP = os.path.join(HERE, "captures")
WIDTH = {"fig55_1": 10.5, "fig55_2": 10.5}
SCALE = 5
GAP = 24
FRAME = (192, 192, 192)
ROWS = 13                                       # the page's rows 0 to 12
TOP = meas.PAPER_Y0 + 8 * (ROWS + 1)            # the border above, the rows, one more
PAGES = {"fig55_1": ("check", ["MSXBOOK_EU16", "MSXBOOK_JP16"]),
         "fig55_2": ("dirty", ["MSXBOOK_EU16B"])}


def framed(im, k):
    """enlarged k times, nearest neighbour, in a frame one enlarged pixel wide"""
    big = im.resize((im.width * k, im.height * k), Image.NEAREST)
    out = Image.new("RGB", (big.width + 2 * k, big.height + 2 * k), FRAME)
    out.paste(big, (k, k))
    return out


def page(name, machine):
    im = Image.open(os.path.join(CAP, f"{name}_{machine}.png")).convert("RGB")
    return framed(im.crop((meas.DRAWN[0], 0, meas.DRAWN[1] + 1, TOP)), SCALE)


def stacked(panels, gap=GAP):
    h = sum(p.height for p in panels) + gap * (len(panels) - 1)
    out = Image.new("RGB", (max(p.width for p in panels), h), (255, 255, 255))
    y = 0
    for p in panels:
        out.paste(p, (0, y))
        y += p.height + gap
    return out


def main():
    out = {}
    for fig, (name, machines) in PAGES.items():
        im = stacked([page(name, m) for m in machines])
        path = os.path.join(HERE, f"{fig}.png")
        im.save(path)
        out[fig] = (path, WIDTH[fig], SCALE, im.size)
    return out


if __name__ == "__main__":
    for name, (path, w, k, size) in main().items():
        print(f"{name}: x{k} -> {size[0]} x {size[1]} px, {w} cm, {size[0] / (w / 2.54):.0f} dpi")
