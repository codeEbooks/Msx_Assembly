#!/usr/bin/env python3
"""fig51.py - the figures of chapter 51, from the captures meas51.py kept.

51.1 is which.rom's page on all 22 machines, the book's ten first and then the
twelve C-BIOS machines of openMSX, three to a row: of each, the paper's
columns 1 to 30 and rows 0 to 12, where the program writes, frame 130,
enlarged twice, nearest neighbour, in a light grey frame. 51.2 is the page on
two of them, the columns the VDP draws (chapter 4) and the lines from the top
of the capture to the row under the program's last, each enlarged three
times: the book's European MSX1 (MSXBOOK_EU16) and the C-BIOS Japanese MSX2.
51.3 is blind.rom's page, as 51.2, on the European MSX1 and the C-BIOS
European MSX2.

    fig51_1  which.rom on the 22 machines
    fig51_2  which.rom: MSXBOOK_EU16 and C-BIOS_MSX2_JP
    fig51_3  blind.rom: MSXBOOK_EU16 and C-BIOS_MSX2_EU
"""
import os
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
sys.path.insert(0, HERE)
import meas  # noqa: E402
import gen51  # noqa: E402
import meas51  # noqa: E402

CAP = os.path.join(HERE, "captures")
MIN_DPI = 300
WIDTH = {"fig51_1": 12.4, "fig51_2": 12.4, "fig51_3": 12.4}
SCALE = {"pair": 3, "card": 2}
GAP = 24
FRAME = (192, 192, 192)
PAIRS = {"fig51_2": ("which", "MSXBOOK_EU16", "C-BIOS_MSX2_JP"),
         "fig51_3": ("blind", "MSXBOOK_EU16", "C-BIOS_MSX2_EU")}


def framed(im, k):
    """enlarged k times, nearest neighbour, in a frame one enlarged pixel wide"""
    big = im.resize((im.width * k, im.height * k), Image.NEAREST)
    out = Image.new("RGB", (big.width + 2 * k, big.height + 2 * k), FRAME)
    out.paste(big, (k, k))
    return out


TOP = meas.PAPER_Y0 + 8 * (gen51.ROWS + 1)     # the border above, the program's rows, one more


def whole(name, machine):
    im = Image.open(os.path.join(CAP, f"{name}_{machine}.png")).convert("RGB")
    return framed(im.crop((meas.DRAWN[0], 0, meas.DRAWN[1] + 1, TOP)), SCALE["pair"])


def card(machine):
    im = Image.open(os.path.join(CAP, f"which_{machine}.png")).convert("RGB")
    x0, y0 = meas.paper(8, 0)
    return framed(im.crop((x0, y0, x0 + 8 * gen51.WIDTH, y0 + 8 * gen51.ROWS)), SCALE["card"])


def side(panels, gap=GAP):
    w = sum(p.width for p in panels) + gap * (len(panels) - 1)
    out = Image.new("RGB", (w, max(p.height for p in panels)), (255, 255, 255))
    x = 0
    for p in panels:
        out.paste(p, (x, 0))
        x += p.width + gap
    return out


def grid(panels, per_row, gap=GAP // 2):
    rows = [side(panels[i:i + per_row], gap) for i in range(0, len(panels), per_row)]
    w = max(r.width for r in rows)
    out = Image.new("RGB", (w, sum(r.height for r in rows) + gap * (len(rows) - 1)), (255, 255, 255))
    y = 0
    for r in rows:
        out.paste(r, (0, y))
        y += r.height + gap
    return out


def main():
    made = {}
    for name, (prog, a, b) in PAIRS.items():
        made[name] = side([whole(prog, a), whole(prog, b)])
    made["fig51_1"] = grid([card(m) for m in meas51.MACHINES], 3)
    out = {}
    for name, im in made.items():
        assert im.width / (WIDTH[name] / 2.54) >= MIN_DPI, name
        path = os.path.join(HERE, f"{name}.png")
        im.save(path)
        out[name] = (path, WIDTH[name], im.size)
    return out


if __name__ == "__main__":
    for name, (path, w, size) in main().items():
        print(f"{name}: {size[0]} x {size[1]} px, {w} cm, {size[0] / (w / 2.54):.0f} dpi")
