#!/usr/bin/env python3
"""figE.py - figure E.1, composed from the capture.

The plate of plate.rom, rows 5 to 19 and columns 1 to 30 of the paper's
characters, cut from the photograph of the 50 Hz machine and enlarged by a
whole number, nearest neighbour: one MSX pixel becomes an exact square. The
only things added are the white margin and, in it, the numbers of the inks
(down the left) and of the papers (along the top), and a thin black frame
round the photograph, so that the white of paper 15 does not run into the
page.
"""
import math
import os
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import genE  # noqa: E402

CAP = os.path.join(HERE, "captures", "plate_eu_colour_f0060.png")
MIN_DPI = 300
PX, PY = 32, 24                     # the paper's top-left pixel in a capture
WIDTH = 14.0                        # cm, as printed; appendixE.py uses the same
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
PT = 7.5                            # the numbers' size, printed


def plate():
    im = Image.open(CAP).convert("RGB")
    x0, y0 = PX + 8 * genE.COL0, PY + 8 * genE.ROW0
    return im.crop((x0, y0, x0 + 8 * 2 * 15, y0 + 8 * 15))


def main():
    crop = plate()
    # the numbers take a margin of about two digits on the left and one line
    # on top: the plate is enlarged to fill the rest of the width
    probe = ImageFont.truetype(FONT, 100)
    digits_w = probe.getlength("15") / 100 * PT / 72 * 2.54          # cm
    plate_cm = WIDTH - digits_w * 1.6
    f = math.ceil(MIN_DPI * plate_cm / 2.54 / crop.width)
    big = crop.resize((crop.width * f, crop.height * f), Image.NEAREST)
    dpi = big.width / (plate_cm / 2.54)
    size = round(PT / 72 * dpi)
    font = ImageFont.truetype(FONT, size)
    left = round(WIDTH / 2.54 * dpi) - big.width - max(2, f // 3)
    top = round(size * 1.6) + max(2, f // 3)
    frame = max(2, f // 3)                  # a thin black frame round the photograph
    out = Image.new("RGB", (left + big.width + frame, top + big.height + frame), (255, 255, 255))
    d = ImageDraw.Draw(out)
    d.rectangle((left - frame, top - frame, left + big.width + frame - 1, top + big.height + frame - 1),
                fill=(0, 0, 0))
    out.paste(big, (left, top))
    d = ImageDraw.Draw(out)
    cell_w, cell_h = 16 * f, 8 * f
    for k in range(15):                     # the papers, along the top
        s = str(k + 1)
        w = d.textlength(s, font=font)
        d.text((left + cell_w * k + (cell_w - w) / 2, top - size * 1.35), s, fill=(0, 0, 0), font=font)
    for k in range(15):                     # the inks, down the left
        s = str(k + 1)
        w = d.textlength(s, font=font)
        d.text((left - w - size * 0.45, top + cell_h * k + (cell_h - size) / 2 - size * 0.1), s,
               fill=(0, 0, 0), font=font)
    path = os.path.join(HERE, "figE_1.png")
    out.save(path)
    return path, f, out.size, out.width / (WIDTH / 2.54)


if __name__ == "__main__":
    path, f, size, dpi = main()
    print(f"{os.path.basename(path)}: x{f} -> {size[0]} x {size[1]} px, {WIDTH} cm, {dpi:.0f} dpi")
