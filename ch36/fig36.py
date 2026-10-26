#!/usr/bin/env python3
"""fig36.py - the figures of chapter 36, from the captures and the recordings.

36.1 and 36.6 are parts of captures, enlarged by a whole number, nearest
neighbour, to at least 300 dpi at the printed width. 36.2 to 36.5 are pieces
of recordings that meas36.py cut and checked against psg36.py: each panel is
a channel's samples, the time across and the sample upward, a black line
through them, in a light grey frame whose top is 32,767 and whose bottom is
0. A panel is drawn a third of its printed size, a pixel to a column, and
enlarged three times; nothing is smoothed.
"""
import json
import math
import os
import sys
import wave

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
import meas  # noqa: E402

CAP = os.path.join(HERE, "captures")
MIN_DPI = 300
WIDTH = {"fig36_1": 12.0, "fig36_2": 12.0, "fig36_3": 12.0, "fig36_4": 12.0, "fig36_5": 12.0,
         "fig36_6": 12.0}
GAP = 16
SCALE = 3                           # a plot is drawn at a third and enlarged three times
INK, FRAME, PAPER = 0, 192, 255     # black, the light grey of the frames, white
TOP = 32767
REGS = (0, 4, 256, 92)              # figure 36.1: text rows 1 to 10, all 32 columns
MIXER = (0, 4, 152, 76)             # figure 36.5: text rows 1 to 8, columns 0 to 18
REGS_SHOT = 41                      # tones.asm: the chord's three channels written
MIXER_SHOT = 115                    # mixer.asm: register 7 right again


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


def samples(name):
    w = wave.open(os.path.join(CAP, name))
    return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(int)


def trace(x, width, height):
    """the samples X as a line, WIDTH columns by HEIGHT rows, in its frame"""
    im = Image.new("L", (width, height), PAPER)
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, width - 1, height - 1), outline=FRAME)
    n = len(x)

    def row(v):
        return 1 + round((height - 3) * (1 - v / TOP))
    last = None
    for col in range(1, width - 1):
        a = (col - 1) * n // (width - 2)
        b = max(a + 1, col * n // (width - 2))
        seg = x[a:b].tolist() + ([last] if last is not None else [])
        d.line((col, row(max(seg)), col, row(min(seg))), fill=INK)
        last = x[b - 1]
    return im


def stack(rows, gap=GAP // SCALE + 2):
    """panels (lists of images) in rows, a gap between them"""
    lines = [side_by_side_l(r, gap) for r in rows]
    w = max(l.width for l in lines)
    out = Image.new("L", (w, sum(l.height for l in lines) + gap * (len(lines) - 1)), PAPER)
    y = 0
    for l in lines:
        out.paste(l, (0, y))
        y += l.height + gap
    return out


def side_by_side_l(panels, gap):
    w = sum(p.width for p in panels) + gap * (len(panels) - 1)
    out = Image.new("L", (w, max(p.height for p in panels)), PAPER)
    x = 0
    for p in panels:
        out.paste(p, (x, 0))
        x += p.width + gap
    return out


def plot(rows, width_cm, height):
    """ROWS of pieces' names: each row's panels share its width"""
    full = math.ceil(MIN_DPI * width_cm / 2.54 / SCALE)
    gap = GAP // SCALE + 2
    panels = []
    for r in rows:
        w = (full - gap * (len(r) - 1)) // len(r)
        panels.append([trace(samples(p), w, height) for p in r])
    im = stack(panels, gap)
    return im.resize((im.width * SCALE, im.height * SCALE), Image.NEAREST).convert("RGB")


def main():
    m = json.load(open(os.path.join(HERE, "meas36.json")))
    tones, noise, env = m["tones"]["eu"]["pieces"], m["noise"]["pieces"], m["env"]
    made = {
        # 36.1 - tones.rom's registers, 50 Hz machine
        "fig36_1": enlarge(paper("tones", "eu", REGS_SHOT, REGS), WIDTH["fig36_1"]),
        # 36.2 - levels.asm: 15 down to 0, a frame each, and the steps that follow
        "fig36_2": (plot([m["levels"]["pieces"]], WIDTH["fig36_2"], 60), SCALE),
        # 36.3 - the chord, channel by channel; A shut and opened; A across the cut
        "fig36_3": (plot([[p] for p in tones], WIDTH["fig36_3"], 38), SCALE),
        # 36.4 - the noise at period 31, at 1, with a tone, and beside one
        "fig36_4": (plot([[p] for p in noise], WIDTH["fig36_4"], 38), SCALE),
        # 36.5 - R13 = 8 to 15, a frame each; then the first ramp of 8 on the YM2149 and the AY-3-8910
        "fig36_5": (plot([env["eu"]["pieces"][k:k + 2] for k in range(0, 8, 2)] +
                         [[env["eu"]["ramp"], env["ay"]["ramp"]]], WIDTH["fig36_5"], 44), SCALE),
        # 36.6 - mixer.rom on the book's machine and on MSXBOOK_EU16P
        "fig36_6": enlarge(side_by_side([paper("mixer", t, MIXER_SHOT, MIXER) for t in ("eu", "p")]),
                           WIDTH["fig36_6"]),
    }
    out = {}
    for name, (im, f) in made.items():
        path = os.path.join(HERE, f"{name}.png")
        im.save(path)
        out[name] = (path, WIDTH[name], f, im.size)
    return out


if __name__ == "__main__":
    for name, (path, w, k, size) in main().items():
        print(f"{name}: x{k} -> {size[0]} x {size[1]} px, {w} cm, {size[0] / (w / 2.54):.0f} dpi")
