#!/usr/bin/env python3
"""meas01.py -- every number of chapter 1, measured again.

Films the programs of this folder with tools/msxcap.py, times them with the
openMSX debugger, and writes meas01.json. The chapter's text reads its numbers
from that file and from nowhere else.

    python3 meas01.py
"""
import json
import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools"))
import msxcap  # noqa: E402
import gen01   # noqa: E402

CAPS = HERE / "captures"
CLOCK = 3579545.4545454546
PX, PY = 32, 24                          # top-left pixel of the paper in a capture


def bright(p):
    return sum(p) > 600                  # white (15) against everything else


def film(name, frames, machine=msxcap.DEFAULT_MACHINE, prefix=None):
    return msxcap.capture(HERE / f"{name}.rom", frames, CAPS, prefix or f"{name}_f", machine=machine)


def symbols(name):
    out = {}
    for line in (HERE / f"{name}.sym").read_text().splitlines():
        lab, _, val = line.partition(": EQU 0x")
        if val:
            out[lab.strip()] = int(val, 16)
    return out


# ---------------------------------------------------------------- 1. the order of the bytes
def cell_order():
    """cells in the order of their first pattern byte: third, cell row, column"""
    return [(t * 8 + r, c) for t in range(3) for r in range(8) for c in range(32)]


def fill_order():
    import shutil
    import tempfile
    frames = range(1, 260)               # film frame 0 is never used (msxcap.py)
    tmp = Path(tempfile.mkdtemp(prefix="fill_order_"))
    shots = msxcap.capture(HERE / "fill_order.rom", frames, tmp, "fill_order_f")
    order = cell_order()
    lit_counts, agree = [], 0
    for n in frames:
        im = Image.open(shots[n]).convert("RGB")
        lit = {(cy, cx) for cy in range(24) for cx in range(32)
               if bright(im.getpixel((PX + cx * 8 + 4, PY + cy * 8 + 4)))}
        k = len(lit)
        lit_counts.append(k)
        agree += lit == set(order[:k])
    want = {8: None, 64: None, 72: None}
    for g in want:
        want[g] = next(n for n, k in zip(frames, lit_counts) if k == 4 * g)
    first = next(n for n, k in zip(frames, lit_counts) if k > 0)
    steps = sorted({b - a for a, b in zip(lit_counts, lit_counts[1:]) if b != a})
    for f in want.values():              # keep only the frames the figure uses
        shutil.copy(shots[f], CAPS / shots[f].name)
    shutil.rmtree(tmp, ignore_errors=True)
    return {"frames_for_groups": {str(g): f for g, f in want.items()},
            "first_lit_frame": first, "frames_checked": len(frames),
            "frames_agreeing_with_cell_order": agree, "cells_per_frame": steps,
            "full_frame": frames[lit_counts.index(768)]}


# ---------------------------------------------------------------- 2. clash
def clash():
    _, rows = gen01.ball_pattern()
    ball = {(gen01.BALL_X + x, gen01.BALL_Y + y) for y in range(16) for x in range(16)
            if rows[y] & (0x8000 >> x)}
    out = {"ball_pixels": len(ball)}
    for name in ("clash_none", "clash_ball"):
        im = Image.open(film(name, [30])[30]).convert("RGB")
        white = {(x - PX, y - PY) for y in range(PY, PY + 192) for x in range(PX, PX + 256)
                 if bright(im.getpixel((x, y)))}
        grass_white = white - ball
        out[name] = {"white": len(white), "white_grass": len(grass_white)}
        if grass_white:
            xs = [p[0] for p in grass_white]
            ys = [p[1] for p in grass_white]
            out[name]["grass_box"] = [min(xs), min(ys), max(xs), max(ys)]
    out["strips_made_white"] = len([1 for (cy, cx) in gen01.ball_cells() for line in range(8)
                                    if gen01.BALL_Y <= cy * 8 + line < gen01.BALL_Y + 16])
    out["ball_xy"] = [gen01.BALL_X, gen01.BALL_Y]
    return out


# ---------------------------------------------------------------- 3. sprites
def balls_visible(png, xs_ys):
    im = Image.open(png).convert("RGB")
    return [bright(im.getpixel((PX + x + 8, PY + y + 1 + 8))) for y, x, _ in xs_ys]


def status_of(name):
    lines = msxcap.run_tcl(HERE / f"{name}.rom", 31, "#",
                           events={30: 'L "status [debug read memory 0xC000]"'})
    s = next(int(l.split()[1]) for l in lines if l.startswith("status "))
    # the program keeps the last status read with the fifth-sprite flag set,
    # or 0 if it never saw one
    return {"byte": s, "5S": s >> 6 & 1, "number": s & 31}


def sprites():
    out = {}
    row = gen01.SPRITE_ROW
    down = row[:4] + [(row[4][0] + 32, row[4][1], 15)]
    stack = [(24, 32, 15), (56, 80, 15), (208, 128, 15), (88, 176, 15), (120, 224, 15)]
    for name, spr in (("sprites5", row), ("sprites5_down", down)):
        vis = balls_visible(film(name, [30])[30], spr)
        out[name] = {"visible": vis, "status": status_of(name)}
    for name, y in (("y208", 208), ("y209", 209)):
        s = list(stack)
        s[2] = (y, s[2][1], 15)
        shown = [sp for sp in s if sp[0] < 191]
        vis = balls_visible(film(name, [30])[30], shown)
        out[name] = {"visible_of_on_screen": vis, "planes_on_screen": [s.index(sp) for sp in shown]}
    return out


# ---------------------------------------------------------------- 4. BIOS against ports
def bios_fill():
    s = symbols("bios_fill")
    labels = ["by_bios_byte", "by_bios_block", "by_ports", "finished"]
    tcl = "\n".join(
        f'debug set_bp {s[lab]:#06x} {{}} {{ L "{lab} [machine_info time] '
        f'[binary encode hex [debug read_block VRAM 0x1800 768]]" }}' for lab in labels)
    lines = msxcap.run_tcl(HERE / "bios_fill.rom", 60, tcl)
    t, vram = {}, {}
    for l in lines:
        p = l.split()
        if p[0] in labels and p[0] not in t:
            t[p[0]] = float(p[1])
            vram[p[0]] = bytes.fromhex(p[2])
    out = {}
    for a, b, value, key in (("by_bios_byte", "by_bios_block", 1, "wrtvrm"),
                             ("by_bios_block", "by_ports", 2, "ldirvm"),
                             ("by_ports", "finished", 3, "outi")):
        T = round((t[b] - t[a]) * CLOCK)
        out[key] = {"T": T, "T_per_byte": round(T / 768, 1),
                    "bytes_right": sum(1 for v in vram[b] if v == value)}
    return out


# ---------------------------------------------------------------- 5. the beam
def beam():
    out = {}
    for k in (0, 16, 228):
        name = f"beam_{k:03d}"
        got = film(name, range(30, 35))
        # the stripe stands still: frames 31 to 34 are frame 30 again
        still = all(got[n].read_bytes() == got[30].read_bytes() for n in range(31, 35))
        assert still, f"{name}: the stripe moves"
        for n in range(31, 35):
            got[n].unlink()
        im = Image.open(got[30]).convert("RGB")
        hits = [(x, y) for y in range(240) for x in range(320) if bright(im.getpixel((x, y)))]
        rows = sorted({y for _, y in hits})
        out[str(k)] = {"rows": rows, "x_first": min(x for x, y in hits if y == rows[0]),
                       "x_last": max(x for x, y in hits if y == rows[-1]), "pixels": len(hits),
                       "same_in_frames": [30, 34]}
    b0, b16, b228 = out["0"], out["16"], out["228"]
    out["px_per_t"] = (b16["x_first"] - b0["x_first"]) / 16
    out["write_gap_t"] = 14 + 20 + 14          # OUT (C),D + 4 NOPs + OUT (C),E, M1 model
    return out


# ---------------------------------------------------------------- 6. 50 and 60 Hz
def frame_length(name, machine):
    lines = msxcap.run_tcl(HERE / f"{name}.rom", 71, "#", machine=machine,
                           events={20: 'L "t20 [machine_info time]"', 70: 'L "t70 [machine_info time]"'})
    t = {l.split()[0]: float(l.split()[1]) for l in lines if l.startswith("t")}
    return (t["t70"] - t["t20"]) * CLOCK / 50


def tick():
    out = {}
    for machine, frame in (("MSXBOOK_EU16", 200), ("MSXBOOK_JP16", 240)):
        tag = machine[8:10]
        png = film("tick", [frame], machine, prefix=f"tick_{tag}_f")[frame]
        im = Image.open(png).convert("RGB")
        xs = [x for y in range(PY, PY + 192) for x in range(PX, PX + 256) if bright(im.getpixel((x, y)))]
        T = frame_length("tick", machine)
        out[tag] = {"frame": frame, "ball_left_x": min(xs) - PX, "T_per_frame": round(T, 2),
                    "seconds": round(frame * T / CLOCK, 3)}
    return out


# ---------------------------------------------------------------- 7. the palette
def palette():
    png = film("palette", [30])[30]
    im = Image.open(png).convert("RGB")
    rgb, grey = [], []
    for c in range(16):
        r, k = divmod(c, 4)
        p = im.getpixel((PX + (8 * k + 3) * 8 + 4, PY + (6 * r + 3) * 8))
        rgb.append(p)
        grey.append(Image.new("RGB", (1, 1), p).convert("L").getpixel((0, 0)))
    groups = {}
    for c in range(1, 16):
        groups.setdefault(grey[c], []).append(c)
    return {"rgb": rgb, "grey": grey, "greys_distinct": len(groups),
            "largest_group": max(groups.values(), key=len)}


def main():
    CAPS.mkdir(exist_ok=True)
    m = {"fill_order": fill_order(), "clash": clash(), "sprites": sprites(),
         "bios_fill": bios_fill(), "beam": beam(), "tick": tick(), "palette": palette()}
    (HERE / "meas01.json").write_text(json.dumps(m, indent=1) + "\n")
    print(json.dumps(m, indent=1))


if __name__ == "__main__":
    main()
