#!/usr/bin/env python3
"""fig35.py - the figures of chapter 35, from the captures.

Parts of captures, set side by side, and enlarged by a whole number, nearest
neighbour, to at least 300 dpi at the printed width. Nothing is added but the
white between two panels. Every capture is a frame meas35.py checked against
the model, pixel by pixel.
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
WIDTH = {"fig35_1": 12.0, "fig35_2": 6.0, "fig35_3": 6.0}
GAP = 16
STICKS = (0, 4, 208, 92)            # figure 35.1: text rows 1 to 10, columns 0 to 25
PLAYERS = (88, 76, 184, 148)        # figure 35.2: the two figures
LEFTOVER = (0, 4, 96, 52)           # figure 35.3: text rows 1 to 5, columns 0 to 11
STICKS_SHOTS = (25, 77)             # up and right on port 1; port 1 left and B, port 2 right and A
PLAYERS_SHOT = 53                   # player 1 swapped once, player 2 twice
LEFTOVER_SHOT = 21                  # joystick 1 right, joystick 2 up


def side_by_side(panels, gap=GAP):
    w = sum(p.width for p in panels) + gap * (len(panels) - 1)
    out = Image.new("RGB", (w, max(p.height for p in panels)), (255, 255, 255))
    x = 0
    for p in panels:
        out.paste(p, (x, 0))
        x += p.width + gap
    return out


def enlarge(im, width_cm):
    f = math.ceil(MIN_DPI * width_cm / 2.54 / im.width)
    return im.resize((im.width * f, im.height * f), Image.NEAREST), f


def paper(name, tag, k, box):
    im = Image.open(os.path.join(CAP, f"{name}_{tag}_f{k:04d}.png")).convert("RGB")
    x0, y0, x1, y1 = box
    return im.crop((meas.PAPER_X0 + x0, meas.PAPER_Y0 + y0, meas.PAPER_X0 + x1, meas.PAPER_Y0 + y1))


def main():
    made = {
        # 35.1 - sticks.rom at 50 Hz, two frames
        "fig35_1": side_by_side([paper("sticks", "eu", k, STICKS) for k in STICKS_SHOTS]),
        # 35.2 - players.rom at 50 Hz
        "fig35_2": paper("players", "eu", PLAYERS_SHOT, PLAYERS),
        # 35.3 - leftover.rom at 50 Hz
        "fig35_3": paper("leftover", "eu", LEFTOVER_SHOT, LEFTOVER),
    }
    out = {}
    for name, im in made.items():
        big, f = enlarge(im, WIDTH[name])
        path = os.path.join(HERE, f"{name}.png")
        big.save(path)
        out[name] = (path, WIDTH[name], f, big.size)
    return out


if __name__ == "__main__":
    for name, (path, w, k, size) in main().items():
        print(f"{name}: x{k} -> {size[0]} x {size[1]} px, {w} cm, {size[0] / (w / 2.54):.0f} dpi")
