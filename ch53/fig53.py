#!/usr/bin/env python3
"""fig53.py - the figures of chapter 53, from the captures meas53.py kept.

The drawn columns and all 240 lines of each capture (chapter 4), enlarged by
a whole number, nearest neighbour, to at least 300 dpi at the printed width.
Nothing is added but the white between them. meas53.py checked every capture
against the picture vdpscreen.py makes of the VRAM line by line, the border
too.

    fig53_1  lz.rom on the 50 Hz machine, two frames after the picture is
             whole
    fig53_2  lz.rom on the 50 Hz machine, four frames while it unpacks: two
             while the patterns arrive, two while the colours do
    fig53_3  otir.rom on the 50 Hz machine, two frames after the picture is
             whole: WHERE IT BREAKS
"""
import json
import math
import os
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
import meas  # noqa: E402

CAP = os.path.join(HERE, "captures")
MIN_DPI = 300
WIDTH = {"fig53_1": 11.0, "fig53_2": 14.0, "fig53_3": 11.0}
GAP = 16


def enlarge(im, width_cm):
    f = math.ceil(MIN_DPI * width_cm / 2.54 / im.width)
    return im.resize((im.width * f, im.height * f), Image.NEAREST), f


def drawn(png):
    im = Image.open(os.path.join(CAP, png)).convert("RGB")
    return im.crop((meas.DRAWN[0], 0, meas.DRAWN[1] + 1, meas.CAPTURE_H))


def side_by_side(panels, gap=GAP):
    w = sum(p.width for p in panels) + gap * (len(panels) - 1)
    out = Image.new("RGB", (w, max(p.height for p in panels)), (255, 255, 255))
    x = 0
    for p in panels:
        out.paste(p, (x, 0))
        x += p.width + gap
    return out


def stacked(rows, gap=GAP):
    out = Image.new("RGB", (max(r.width for r in rows), sum(r.height for r in rows) + gap * (len(rows) - 1)),
                    (255, 255, 255))
    y = 0
    for r in rows:
        out.paste(r, (0, y))
        y += r.height + gap
    return out


def plan(m):
    """the frames of the figures, from meas53.json"""
    ph = m["photos"]
    lz, otir = ph["lz"]["eu"], ph["otir"]["eu"]
    fr = m["films"]["lz"]["eu"]["frames"]
    whole = fr["whole"] + 2
    composing = [k for k in lz["kept"] if k != whole]
    assert len(composing) == 4 and whole in lz["kept"]
    broken = m["films"]["otir"]["eu"]["frames"]["whole"] + 2
    assert otir["kept"] == [broken]
    return {"fig53_1": [lz["frames"][str(whole)]], "fig53_2": [lz["frames"][str(k)] for k in composing],
            "fig53_3": [otir["frames"][str(broken)]], "frames": {"whole": whole, "composing": composing,
                                                                 "broken": broken}}


def main():
    m = json.load(open(os.path.join(HERE, "meas53.json")))
    p = plan(m)
    c = [drawn(f) for f in p["fig53_2"]]
    made = {"fig53_1": drawn(p["fig53_1"][0]),
            "fig53_2": stacked([side_by_side(c[:2]), side_by_side(c[2:])]),
            "fig53_3": drawn(p["fig53_3"][0])}
    out = {}
    for fig, im in made.items():
        big, k = enlarge(im, WIDTH[fig])
        path = os.path.join(HERE, f"{fig}.png")
        big.save(path)
        out[fig] = (path, WIDTH[fig], k, big.size)
    return out


if __name__ == "__main__":
    for name, (path, w, k, size) in main().items():
        print(f"{name}: x{k} -> {size[0]} x {size[1]} px, {w} cm, {size[0] / (w / 2.54):.0f} dpi")
