#!/usr/bin/env python3
"""fig50.py - the figures of chapter 50, from the measurements.

50.1 is the tape as scope.rom sampled it, bit 7 of R14 every 55 T-states,
from the first start bit's second half on, 10 milliseconds of it: the
1,200 baud tape above, the .CAS as openMSX plays it below, on the same time
scale. A panel is a line through the samples, high or low, a pixel a
column, in a light grey frame; it is drawn a third of its printed size and
enlarged three times. 50.2 is two film frames of load.rom on the 1,200 baud
tape, the drawn columns and all 240 lines (chapter 4), enlarged by a whole
number, nearest neighbour: the page halfway through the data block, and the
picture once it is loaded; meas50.py read both back. 50.3 is every pulse
getbyte compared with D while load.rom read each tape: a column for each
count of turns from 0 to 40, a grey tick at the top every 10, each column as
tall as the logarithm of how many pulses counted that, from 1 (a pixel) at
the bottom to 100,000 at the top; a black mark under the threshold load.rom
found, between the counts that read as short and those that read as long,
and a grey one under fixed.rom's. All are of the 60 Hz
machine, whose numbers are the 50 Hz machine's.

    fig50_1  the start of the file on tape: screen.wav, and screen.cas
    fig50_2  load.rom: the page while it loads, and the picture
    fig50_3  the pulses getbyte measured: screen.wav, and screen.cas
"""
import json
import math
import os
import sys

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
import meas  # noqa: E402

CAP = os.path.join(HERE, "captures")
MIN_DPI = 300
WIDTH = {"fig50_1": 12.4, "fig50_2": 12.4, "fig50_3": 12.4}
SCALE = 3
GAP = 16
INK, MARK, FRAME, PAPER = 0, 128, 192, 255
WINDOW_MS = 10                          # figure 50.1: milliseconds across
SAMPLE_T = 55
CLOCK = 3579545
TURNS = 41                              # figure 50.3: counts 0 to 40
LOG_TOP = 5                             # 100,000


def frame(width, height):
    im = Image.new("L", (width, height), PAPER)
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, width - 1, height - 1), outline=FRAME)
    return im, d


def trace(bits, width, height):
    """samples as a line: high at the top, low at the bottom"""
    im, d = frame(width, height)
    n = len(bits)
    hi, lo = 3, height - 4
    last = None
    for col in range(1, width - 1):
        a = (col - 1) * n // (width - 2)
        b = max(a + 1, col * n // (width - 2))
        seg = bits[a:b] + ([last] if last is not None else [])
        ys = [hi if v else lo for v in seg]
        d.line((col, min(ys), col, max(ys)), fill=INK)
        last = bits[b - 1]
    return im


def columns(hist, d_load, d_fixed, width, height):
    """a column per count of turns, log10 of the pulses high; marks under"""
    im, d = frame(width, height)
    inner = height - 9
    per = (width - 2) // TURNS
    for k in range(TURNS):
        v = hist.get(str(k), 0)
        x0 = 1 + k * per + 1
        if v:
            h = max(1, round(inner * min(math.log10(v), LOG_TOP) / LOG_TOP))
            d.rectangle((x0, 1 + inner - h, x0 + per - 3, inner), fill=INK)
        if k % 10 == 0:
            xc = x0 + (per - 3) // 2
            d.line((xc, 1, xc, 3), fill=MARK)
    for dd, fill in ((d_fixed, MARK), (d_load, INK)):
        x = 1 + (dd + 1) * per - 1          # between dd (short) and dd + 1 (long)
        d.rectangle((x - 1, height - 7, x, height - 2), fill=fill)
    return im


def stack(panels, gap=GAP // SCALE + 2):
    w = max(p.width for p in panels)
    out = Image.new("L", (w, sum(p.height for p in panels) + gap * (len(panels) - 1)), PAPER)
    y = 0
    for p in panels:
        out.paste(p, (0, y))
        y += p.height + gap
    return out


def finish(im):
    return im.resize((im.width * SCALE, im.height * SCALE), Image.NEAREST).convert("RGB")


def drawn(png):
    im = Image.open(os.path.join(CAP, png)).convert("RGB")
    return im.crop((meas.DRAWN[0], 0, meas.DRAWN[1] + 1, meas.CAPTURE_H))


def side(panels, gap=GAP):
    w, h = panels[0].size
    out = Image.new("RGB", (len(panels) * w + (len(panels) - 1) * gap, h), (255, 255, 255))
    for i, p in enumerate(panels):
        out.paste(p, (i * (w + gap), 0))
    return out


def main():
    m = json.load(open(os.path.join(HERE, "meas50.json")))
    w = math.ceil(MIN_DPI * WIDTH["fig50_1"] / 2.54 / SCALE)
    n = round(WINDOW_MS / 1000 * CLOCK / SAMPLE_T)
    sc = m["scope"]
    f1 = finish(stack([trace(sc[t]["bits"][:n], w, 22) for t in ("wav", "cas")]))
    ld = m["load"]
    pair = side([drawn(f"load_wav_jp_{k}.png") for k in ("mid", "end")])
    f = math.ceil(MIN_DPI * WIDTH["fig50_2"] / 2.54 / pair.width)
    f2 = pair.resize((pair.width * f, pair.height * f), Image.NEAREST)
    hs = {t: {k: ld[t]["jp"]["hs"].get(k, 0) + ld[t]["jp"]["hb"].get(k, 0)
              for k in set(ld[t]["jp"]["hs"]) | set(ld[t]["jp"]["hb"])} for t in ("wav", "cas")}
    f3 = finish(stack([columns(hs[t], ld[t]["jp"]["d"], m["fixed"]["wav"]["jp"]["d"], w, 40)
                       for t in ("wav", "cas")]))
    made = {"fig50_1": f1, "fig50_2": f2, "fig50_3": f3}
    out = {}
    for name, im in made.items():
        path = os.path.join(HERE, f"{name}.png")
        im.save(path)
        out[name] = (path, WIDTH[name], im.size)
    return out


if __name__ == "__main__":
    for name, (path, w, size) in main().items():
        print(f"{name}: {size[0]} x {size[1]} px, {w} cm, {size[0] / (w / 2.54):.0f} dpi")
