#!/usr/bin/env python3
"""label56.py - the two cartridges' labels, made of openMSX's pictures alone.

    python3 label56.py      after meas56.py photos: captures/ holds the pictures

A label for a Konami-style cartridge, 88 x 78 mm, its top 16 mm folded over
the cartridge's top edge (the size two of msx.org's members measured on
Konami's labels: 86 x 75 with 14 on top, and 88 x 78 with 16). At 400 dots
an inch every part is a whole number of dots, the nearest to its size:

    top    LANTERN KEEP or GRIN ALLEY in the BIOS's letters, eight times
           enlarged, on the left; MSX1 CARTRIDGE and 32 KB ROM or 16 KB ROM
           three times enlarged on the right; all from label.rom's page
    front  the game's title screen, the paper's 256 x 192 pixels, four times
           enlarged, from the game's own run; under it CODE & BOOKS 2026

The rest is the black of label.rom's page, colour 1 as openMSX shows it, and
nothing but black is nearer than 3 mm to an edge. Each label is written as a
PNG and as a PDF page of the label's size, without loss, for a printer.
"""
import os
import sys

import img2pdf
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
sys.path.insert(0, HERE)
import meas  # noqa: E402
import gen56  # noqa: E402

CAP = os.path.join(HERE, "captures")
DPI = 400
MM = {"width": 88, "height": 78, "top": 16, "margin": 3}
TITLE_X = 4                     # the title's enlargement
NAME_X = 8                      # the name's, on the top
SMALL_X = 3                     # the other words'


def dots(mm):
    return round(mm * DPI / 25.4)


W, H, TOP, MARGIN = (dots(MM[k]) for k in ("width", "height", "top", "margin"))
FRONT = H - TOP


def words(page, key, k):
    """a line of label.rom's page, its cells cropped and enlarged K times"""
    row, col, text = gen56.WORDS[key]
    x, y = meas.PAPER_X0 + 8 * col, meas.PAPER_Y0 + 8 * row
    im = page.crop((x, y, x + 8 * len(text), y + 8))
    return im.resize((im.width * k, im.height * k), Image.NEAREST)


def layout(name):
    """where each part goes: (image, x, y), the whole label's size, and the
    black"""
    page = Image.open(os.path.join(CAP, "label_words.png")).convert("RGB")
    black = page.getpixel((meas.PAPER_X0, meas.PAPER_Y0))
    title = Image.open(os.path.join(CAP, f"title_{name}.png")).convert("RGB")
    paper = title.crop((meas.PAPER_X0, meas.PAPER_Y0, meas.PAPER_X0 + 256, meas.PAPER_Y0 + 192))
    big = paper.resize((256 * TITLE_X, 192 * TITLE_X), Image.NEAREST)
    kb = "kb32" if gen56.GAMES[name]["kb"] == 32 else "kb16"
    parts = []
    nm = words(page, name, NAME_X)
    parts.append((nm, MARGIN, (TOP - nm.height) // 2))
    cart, size = words(page, "cartridge", SMALL_X), words(page, kb, SMALL_X)
    y0 = (TOP - cart.height - size.height - 2 * 8) // 2
    parts.append((cart, W - MARGIN - cart.width, y0))
    parts.append((size, W - MARGIN - size.width, y0 + cart.height + 2 * 8))
    parts.append((big, (W - big.width) // 2, TOP + (FRONT - big.height) // 2))
    maker = words(page, "maker", SMALL_X)
    parts.append((maker, (W - maker.width) // 2, TOP + (FRONT + big.height) // 2
                  + (H - MARGIN - TOP - (FRONT + big.height) // 2 - maker.height) // 2))
    return parts, black


def compose(name):
    parts, black = layout(name)
    out = Image.new("RGB", (W, H), black)
    for im, x, y in parts:
        # nothing but the black within the margin, no two parts on each other
        assert MARGIN <= x and x + im.width <= W - MARGIN, (name, x)
        assert MARGIN <= y and y + im.height <= H - MARGIN, (name, y)
        assert y + im.height <= TOP or y >= TOP, (name, y)      # nothing across the fold
        out.paste(im, (x, y))
    boxes = [(x, y, x + im.width, y + im.height) for im, x, y in parts]
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            assert a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1], (name, a, b)
    return out, parts, black


def main():
    out = {}
    for name in gen56.GAMES:
        im, parts, black = compose(name)
        png = os.path.join(HERE, f"label_{name}.png")
        im.save(png, dpi=(DPI, DPI))
        pdf = os.path.join(HERE, f"label_{name}.pdf")
        layout_fun = img2pdf.get_fixed_dpi_layout_fun((DPI, DPI))
        with open(pdf, "wb") as f:
            f.write(img2pdf.convert(png, layout_fun=layout_fun, nodate=True,
                                    engine=img2pdf.Engine.internal))
        out[name] = {"png": png, "pdf": pdf, "dots": [W, H], "top": TOP, "margin": MARGIN,
                     "mm": [round(W * 25.4 / DPI, 3), round(H * 25.4 / DPI, 3)],
                     "parts": [[im.width, im.height, x, y] for im, x, y in parts]}
    return out


if __name__ == "__main__":
    for name, v in main().items():
        print(name, v["dots"], v["mm"], os.path.basename(v["pdf"]))
