#!/usr/bin/env python3
"""fig01.py - the plates of chapter 1, composed from the captures.

Every pixel inside a panel is a pixel of a capture in captures/; the only
things added are the white gaps between panels and, in figure 1.7, the colour
codes in the white margin. Crops on the paper are whole 8 x 8 cells.
Enlargement is by a whole number, nearest neighbour: one MSX pixel becomes an
exact square.
"""
import math
import os
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
CAP = os.path.join(HERE, "captures")
MIN_DPI = 300
GAP = 12
PX, PY = 32, 24                     # the paper's top-left pixel in a capture

# the print width of each figure, in cm; chapter01.py uses the same numbers
FULL = 15.29                        # the column is 15.2976 cm
WIDTH = {"fig01_1": FULL, "fig01_2": FULL, "fig01_3": FULL, "fig01_4": FULL,
         "fig01_5": FULL, "fig01_6": FULL, "fig01_7": 13.5}
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def cap(name):
    return Image.open(os.path.join(CAP, name)).convert("RGB")


def paper(name, col0, row0, cols, rows, border=0):
    """a crop of whole cells of the paper, with `border` pixels around"""
    x0, y0 = PX + 8 * col0, PY + 8 * row0
    return cap(name).crop((x0 - border, y0 - border, x0 + 8 * cols + border, y0 + 8 * rows + border))


def side_by_side(panels, gap=GAP):
    w = sum(p.width for p in panels) + gap * (len(panels) - 1)
    out = Image.new("RGB", (w, max(p.height for p in panels)), (255, 255, 255))
    x = 0
    for p in panels:
        out.paste(p, (x, 0))
        x += p.width + gap
    return out


def stacked(panels, gap=GAP):
    h = sum(p.height for p in panels) + gap * (len(panels) - 1)
    out = Image.new("RGB", (max(p.width for p in panels), h), (255, 255, 255))
    y = 0
    for p in panels:
        out.paste(p, (0, y))
        y += p.height + gap
    return out


def enlarge(im, width_cm):
    f = math.ceil(MIN_DPI * width_cm / 2.54 / im.width)
    return im.resize((im.width * f, im.height * f), Image.NEAREST), f


def codes(big, width_cm):
    """The colour codes of the sixteen swatches of palette.rom, written in a
    white margin to the right of each swatch row, at 7.5 pt of the printed
    figure: the only thing in figure 1.7 that is not a photograph."""
    dpi = big.width / (width_cm / 2.54)
    size = round(7.5 / 72 * dpi)
    font = ImageFont.truetype(FONT, size)
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    rows = ["  ".join(f"{4 * r + k:2d}" for k in range(4)) for r in range(4)]
    margin = int(max(probe.textlength(s, font=font) for s in rows) + size * 1.2)
    out = Image.new("RGB", (big.width + margin, big.height), (255, 255, 255))
    out.paste(big, (0, 0))
    d = ImageDraw.Draw(out)
    row_h = big.height / 4
    for r, text in enumerate(rows):
        d.text((big.width + size * 0.6, row_h * r + row_h / 2 - size / 2), text,
               fill=(0, 0, 0), font=font)
    return out


def main():
    made = {}
    # 1.1 - the pattern table filled in address order: groups 8, 64 and 72,
    # the top two thirds of the paper (16 cell rows), border around
    made["fig01_1"] = side_by_side([paper(f"fill_order_f{f:04d}.png", 0, 0, 32, 17, border=8)
                                    for f in (23, 79, 87)], gap=8)
    # 1.2 - the ball, without and with white ink under it: 8 x 5 cells
    made["fig01_2"] = side_by_side([paper(f"clash_{k}_f0030.png", 12, 10, 8, 5)
                                    for k in ("none", "ball")])
    # 1.3 - five sprites on one line, and the fifth one 32 lines lower
    made["fig01_3"] = stacked([paper(f"{n}_f0030.png", 0, 9, 32, 7)
                               for n in ("sprites5", "sprites5_down")])
    # 1.4 - Where it breaks: a sprite parked at Y = 208, and at Y = 209
    made["fig01_4"] = side_by_side([paper(f"{n}_f0030.png", 0, 0, 32, 20) for n in ("y208", "y209")])
    # 1.5 - the beam: rows 214-223 of the capture (the bottom border), full width
    made["fig01_5"] = stacked([cap(f"beam_{k:03d}_f0030.png").crop((0, 214, 320, 224))
                               for k in (0, 16, 228)], gap=6)
    # 1.6 - the same cartridge about four seconds after it started, 50 Hz and 60 Hz
    made["fig01_6"] = stacked([paper(f"tick_{m}_f{f:04d}.png", 0, 10, 32, 4, border=0)
                               for m, f in (("EU", 200), ("JP", 240))])
    # 1.7 - the palette: the whole paper
    made["fig01_7"] = paper("palette_f0030.png", 0, 0, 32, 24)
    out = {}
    for name, im in made.items():
        big, f = enlarge(im, WIDTH[name])
        if name == "fig01_7":
            big = codes(big, WIDTH[name])
        path = os.path.join(HERE, f"{name}.png")
        big.save(path)
        out[name] = (path, WIDTH[name], f, big.size)
    return out


if __name__ == "__main__":
    for name, (path, w, f, size) in main().items():
        print(f"{name}: x{f} -> {size[0]} x {size[1]} px, {w} cm, "
              f"{size[0] / (w / 2.54):.0f} dpi")
