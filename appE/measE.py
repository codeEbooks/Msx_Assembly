#!/usr/bin/env python3
"""measE.py -- the fifteen colours of Appendix E, photographed on openMSX.

    python3 genE.py && ./build.sh && python3 measE.py [step ...]

    plate    plate.rom on both machines: the VRAM and the registers when it
             has finished, against the plate genE.py planned; the photograph
             against the picture vdpscreen.py (chapters 21 to 23) draws from
             them, colour code by colour code: each code one colour, fifteen
             different ones. That colour, its grey as the book's print file
             makes it (PIL's convert("L"), ITU-R 601), and the grey of
             openMSX's monochrome monitor (monitor_type monochrome_white, the
             same frame photographed again); kept: the two photographs of the
             50 Hz machine for figure E.1
    border   border.rom on both machines: the display off and the border in
             each code, 0 to 15, three times round: each frame one colour,
             the plate's for codes 1 to 15
    pairs    every ink against every paper, from the plate's photographs: how
             many levels of grey apart they print, and on the monitor
    ti       the greys against the luminance Texas Instruments gives each
             colour (data manual, table 2-3)
    before   the numbers against chapter 1's palette
    openmsx  the steps again with every other build (tools/versions.py)

Writes measE.json.
"""
import json
import sys
import tempfile
from itertools import combinations
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(HERE))
import meas        # noqa: E402
import msxcap      # noqa: E402
import probe       # noqa: E402
import versions    # noqa: E402
import vdpscreen   # noqa: E402  (chapters 21 to 23, copied)
import genE        # noqa: E402

OUT_JSON = HERE / "measE.json"
CAPS = HERE / "captures"
EU, JP = "MSXBOOK_EU16", "MSXBOOK_JP16"
MACHINES = (EU, JP)
TAG = {EU: "eu", JP: "jp"}
POS = "[machine_info VDP_frame_count] [machine_info VDP_cycle_in_frame]"
REGS = " ".join(f"[debug read {{VDP regs}} {i}]" for i in range(8))
VRAM = 'binary scan [debug read_block {VRAM} 0 16384] H* h; L "vram $h"'
F0 = 'L "f0 [machine_info VDP_frame_count]"\n'
SHOT = 60                       # the plate's photograph, frames after INIT
# openMSX's share/scripts/monitor.tcl: the colour matrix of monitor_type
# monochrome_white, each output channel from the input's red, green and blue
MONO = (0.257, 0.504, 0.098)
MONO_TCL = "set color_matrix {{ .257 .504 .098 } { .257 .504 .098 } { .257 .504 .098 }}"
GAMMA = 1.1                     # openMSX's default gamma, which the photographs carry
THRESHOLD = 56                  # the collection's rule: two greys to tell apart (plan, 5)
# Texas Instruments, TMS9918A/TMS9928A/TMS9929A Video Display Processors Data
# Manual, November 1982, table 2-3: the luminance of each colour, 0.00 black,
# 1.00 white, "eight different gray levels for displays on monochrome
# television". The column of the TMS9928A and TMS9929A, as MAME's
# tms9928a.cpp and Wikipedia's TMS9918 article copy it; the manual says the
# TMS9918A's levels "differ slightly".
TI_Y = {1: 0.00, 2: 0.53, 3: 0.67, 4: 0.40, 5: 0.53, 6: 0.47, 7: 0.73, 8: 0.53,
        9: 0.67, 10: 0.73, 11: 0.80, 12: 0.47, 13: 0.53, 14: 0.80, 15: 1.00}
NAMES = ["transparent", "black", "medium green", "light green", "dark blue", "light blue",
         "dark red", "cyan", "medium red", "light red", "dark yellow", "light yellow",
         "dark green", "magenta", "grey", "white"]


def rom(name):
    return HERE / f"{name}.rom"


def sym(name):
    return probe.sym(HERE / f"{name}.sym")


def run(name, frames, tcl, machine):
    return [l.split() for l in msxcap.run_tcl(rom(name), frames, F0 + tcl, machine=machine)]


def rgb_array(png):
    return np.asarray(Image.open(png).convert("RGB")).astype(int)


def grey_of(rgb):
    """the print file's grey of one colour: PIL's convert("L")"""
    return Image.new("RGB", (1, 1), tuple(int(v) for v in rgb)).convert("L").getpixel((0, 0))


def by_code(model, photo):
    """{code: the set of colours the photograph has where the model has code}"""
    paper = photo[meas.PAPER_Y0:meas.PAPER_Y0 + 192, meas.PAPER_X0:meas.PAPER_X0 + 256]
    out = {}
    m = np.asarray(model)
    for code in sorted(set(m.flatten().tolist())):
        px = paper[m == code]
        out[code] = sorted({tuple(int(v) for v in p) for p in px})
    return out


# ---------------------------------------------------------------- plate
def planned_vram():
    """the VRAM genE.py's plate means: the BIOS's Graphic II screen, black ink on
    white, and the plate's characters"""
    v = bytearray(16384)
    v[0x2000:0x3800] = b"\x1f" * 6144
    v[0x1800:0x1B00] = bytes(range(256)) * 3
    v[0x1B00] = 0xD0
    for row, col, digit, byte in genE.plate_cells():
        a = row * 256 + col * 8
        v[a:a + 8] = bytes(genE.glyph("0123456789ABCDEF"[digit]))
        v[0x2000 + a:0x2000 + a + 8] = bytes([byte]) * 8
    return v


def plate_run(machine):
    s = sym("plate")
    tcl = (f'set ::d [debug set_bp {s["done"]} {{}} {{ L "regs {REGS}"; {VRAM}; L "done {POS}"; '
           'debug remove_bp $::d }]\n'
           'L "settings $::gamma $::brightness $::contrast"\n'
           'L "matrix [join [join $::color_matrix]]"\n')
    w = run("plate", SHOT + 5, tcl, machine)
    f0 = int(next(x for x in w if x[0] == "f0")[1])
    done = next(x for x in w if x[0] == "done")
    regs = [int(v) for v in next(x for x in w if x[0] == "regs")[1:]]
    vram = bytearray(bytes.fromhex(next(x for x in w if x[0] == "vram")[1]))
    assert int(done[1]) - f0 < SHOT - 2, (machine, "the plate is not finished before the photograph")
    settings = [float(v) for v in next(x for x in w if x[0] == "settings")[1:]]
    matrix = [float(v) for v in next(x for x in w if x[0] == "matrix")[1:]]
    return regs, vram, settings, matrix


def plate(res):
    out = {}
    CAPS.mkdir(exist_ok=True)
    want = planned_vram()
    for machine in MACHINES:
        regs, vram, settings, matrix = plate_run(machine)
        # openMSX's defaults: gamma 1.1, brightness 0, contrast 0, no colour matrix
        assert settings == [GAMMA, 0.0, 0.0] and matrix == [1, 0, 0, 0, 1, 0, 0, 0, 1], \
            (machine, settings, matrix)
        tables = list(range(0, 0x1B01)) + list(range(0x2000, 0x3800))
        wrong_vram = sum(1 for a in tables if vram[a] != want[a])
        assert wrong_vram == 0 and regs == [0x02, 0xC0, 0x06, 0xFF, 0x03, 0x36, 0x07, 0x0F], machine
        model = vdpscreen.draw(vram, regs)
        keep = machine == EU
        pngs = {}
        for kind, setup in (("colour", ""), ("mono", MONO_TCL), ("colour10", "set gamma 1.0"),
                            ("mono10", "set gamma 1.0\n" + MONO_TCL)):
            dst = CAPS if keep and kind in ("colour", "mono") else Path(tempfile.mkdtemp(prefix="appE_"))
            p = msxcap.capture(rom("plate"), [SHOT], dst, f"plate_{TAG[machine]}_{kind}_f",
                               machine=machine, tcl_setup=setup)[SHOT]
            pngs[kind] = rgb_array(p)
            if dst != CAPS:
                p.unlink()
                dst.rmdir()
        colour = by_code(model, pngs["colour"])
        mono = by_code(model, pngs["mono"])
        colour10 = by_code(model, pngs["colour10"])
        mono10 = by_code(model, pngs["mono10"])
        assert all(len(v) == 1 for d in (colour10, mono10) for v in d.values()), machine
        assert sorted(colour) == list(range(1, 16)), (machine, sorted(colour))
        assert all(len(v) == 1 for v in colour.values()), (machine, colour)
        assert len({v[0] for v in colour.values()}) == 15, machine
        assert all(len(v) == 1 and len(set(v[0])) == 1 for v in mono.values()), (machine, mono)
        # the border: the backdrop, white, in every drawn column
        for kind in ("colour", "mono"):
            ph = pngs[kind]
            border = np.ones((240, 320), bool)
            border[meas.PAPER_Y0:meas.PAPER_Y0 + 192, meas.PAPER_X0:meas.PAPER_X0 + 256] = False
            cols = slice(meas.DRAWN[0], meas.DRAWN[1] + 1)
            seen = {tuple(p) for p in ph[:, cols][border[:, cols]].tolist()}
            want_b = colour[15][0] if kind == "colour" else mono[15][0]
            assert seen == {tuple(want_b)}, (machine, kind, seen)
        rgb = {c: list(colour[c][0]) for c in range(1, 16)}
        out[TAG[machine]] = {
            "rgb": rgb,
            "print": {c: grey_of(rgb[c]) for c in range(1, 16)},
            "monitor": {c: mono[c][0][0] for c in range(1, 16)},
            "pixels": {c: int((np.asarray(model) == c).sum()) for c in range(1, 16)},
            "gamma": settings[0],
            "rgb_gamma10": {c: list(colour10[c][0]) for c in range(1, 16)},
            "print_gamma10": {c: grey_of(colour10[c][0]) for c in range(1, 16)},
            "monitor_gamma10": {c: mono10[c][0][0] for c in range(1, 16)},
            "vram_wrong": wrong_vram}
    e, j = out["eu"], out["jp"]
    out["same_on_both"] = e["rgb"] == j["rgb"] and e["monitor"] == j["monitor"]
    # the monitor against the print, and against the matrix applied to the
    # photographed colours
    for t in ("eu", "jp"):
        o = out[t]
        sums = {c: sum(k * v for k, v in zip(MONO, o["rgb"][c])) for c in range(1, 16)}
        o["monitor_minus_sum"] = [round(min(o["monitor"][c] - sums[c] for c in sums), 2),
                                  round(max(o["monitor"][c] - sums[c] for c in sums), 2)]
        o["monitor_over_print"] = [round(min(o["monitor"][c] / o["print"][c] for c in range(2, 16)), 3),
                                   round(max(o["monitor"][c] / o["print"][c] for c in range(2, 16)), 3)]
        # the matrix applied before the gamma: the photographed colour taken
        # back through gamma 1.1, the matrix, and gamma 1.1 again
        lin = {c: [(v / 255) ** GAMMA for v in o["rgb"][c]] for c in range(1, 16)}
        model = {c: 255 * sum(k * v for k, v in zip(MONO, lin[c])) ** (1 / GAMMA) for c in range(1, 16)}
        o["monitor_model_far"] = round(max(abs(o["monitor"][c] - model[c]) for c in model), 2)
        # gamma 1.0: the greys against TI's luminance times 255, the monitor
        # against the matrix's sums
        o["gamma10_print_far"] = max(abs(o["print_gamma10"][c] - round(255 * TI_Y[c])) for c in range(2, 15))
        o["gamma10_ends"] = [o["print_gamma10"][1], o["print_gamma10"][15]]
        o["gamma10_monitor_far"] = round(max(abs(o["monitor_gamma10"][c] - sum(
            k * v for k, v in zip(MONO, o["rgb_gamma10"][c]))) for c in range(1, 16)), 2)
        o["gamma10_under"] = sum(1 for a in range(1, 16) for b in range(a + 1, 16)
                                 if abs(o["print_gamma10"][a] - o["print_gamma10"][b]) < THRESHOLD)
    res["plate"] = out


# ---------------------------------------------------------------- border
def border(res):
    out = {}
    s = sym("border")
    for machine in MACHINES:
        w = run("border", 16 * genE.BORDER_FRAMES * genE.BORDER_ROUNDS + 40,
                f'debug set_bp {s["mark"]} {{}} {{ L "m [reg d] {POS}" }}\n', machine)
        f0 = int(next(x for x in w if x[0] == "f0")[1])
        marks = [(int(x[1]), int(x[2])) for x in w if x[0] == "m"]
        assert [d for d, _ in marks] == list(range(16)) * genE.BORDER_ROUNDS, (machine, marks)
        frames = sorted({f - f0 + d for _, f in marks for d in (1, 2)})
        tmp = Path(tempfile.mkdtemp(prefix="appE_"))
        pngs = msxcap.capture(rom("border"), frames, tmp, "b_f", machine=machine)
        seen = {}
        cols = slice(meas.DRAWN[0], meas.DRAWN[1] + 1)
        whole = 0
        for d, f in marks:
            for k in (1, 2):
                ph = rgb_array(pngs[f - f0 + k])[:, cols]
                colours = {tuple(p) for p in ph.reshape(-1, 3).tolist()}
                whole += len(colours) == 1
                if len(colours) == 1:
                    seen.setdefault(d, set()).add(colours.pop())
        for p in pngs.values():
            p.unlink()
        assert whole == 2 * len(marks) and all(len(v) == 1 for v in seen.values()), (machine, seen)
        rgb = {d: list(seen[d].pop()) for d in range(16)}
        pl = {int(k): v for k, v in res["plate"][TAG[machine]]["rgb"].items()}
        assert all(rgb[c] == pl[c] for c in range(1, 16)), machine
        out[TAG[machine]] = {"rgb": rgb, "frames": 2 * len(marks)}
    res["border"] = out


# ---------------------------------------------------------------- pairs
def pairs(res):
    out = {}
    for t in ("eu", "jp"):
        pl = res["plate"][t]
        pr = {int(k): v for k, v in pl["print"].items()}
        mo = {int(k): v for k, v in pl["monitor"].items()}
        table = [[abs(pr[i] - pr[p]) for p in range(1, 16)] for i in range(1, 16)]
        mono = [[abs(mo[i] - mo[p]) for p in range(1, 16)] for i in range(1, 16)]
        under = sorted({tuple(sorted((i, p))) for i in range(1, 16) for p in range(1, 16)
                        if i != p and table[i - 1][p - 1] < THRESHOLD})
        apart = lambda g, q: all(abs(g[a] - g[b]) >= THRESHOLD for a, b in combinations(q, 2))  # noqa: E731
        fours = [q for q in combinations(range(1, 16), 4) if apart(pr, q)]
        fives = [q for q in combinations(range(1, 16), 5) if apart(pr, q)]
        gap = lambda g, q: min(abs(g[a] - g[b]) for a, b in combinations(q, 2))  # noqa: E731
        best = max(gap(pr, q) for q in fours)
        out[t + "_sets"] = {
            "partners": {c: sum(1 for d in range(1, 16) if d != c and abs(pr[c] - pr[d]) >= THRESHOLD)
                         for c in range(1, 16)},
            "fours": len(fours), "fives": len(fives), "best_gap": best,
            "best": [list(q) for q in fours if gap(pr, q) == best],
            "book_four": [1, 4, 3, 15], "book_gap": gap(pr, (1, 4, 3, 15)),
            "book_gap_monitor": gap(mo, (1, 4, 3, 15))}
        out[t] = {"print": table, "monitor": mono, "under": [list(u) for u in under],
                  "under_count": len(under), "pairs": 15 * 14 // 2,
                  "monitor_under": sum(1 for i in range(1, 16) for p in range(i + 1, 16)
                                       if mono[i - 1][p - 1] < THRESHOLD)}
    res["pairs"] = out


# ---------------------------------------------------------------- ti
def groups(values):
    """the codes in groups of values no more than 1 apart, in order"""
    out = []
    for c in sorted(values, key=lambda c: (values[c], c)):
        if out and values[c] - values[out[-1][-1]] <= 1:
            out[-1].append(c)
        else:
            out.append([c])
    return out


def ti(res):
    out = {}
    ty = {c: round(TI_Y[c] * 100) for c in TI_Y}
    ti_groups = [sorted(g) for g in groups({c: v for c, v in ty.items()})]
    exact = []
    for y in sorted(set(TI_Y.values())):
        exact.append(sorted(c for c in TI_Y if TI_Y[c] == y))
    for t in ("eu", "jp"):
        pr = {int(k): v for k, v in res["plate"][t]["print"].items()}
        mo = {int(k): v for k, v in res["plate"][t]["monitor"].items()}
        pg = [sorted(g) for g in groups(pr)]
        mg = [sorted(g) for g in groups(mo)]
        out[t] = {"print_groups": pg, "monitor_groups": mg, "same_as_ti": pg == exact,
                  "monitor_same_as_ti": mg == exact,
                  "order": all(pr[a] <= pr[b] for a in TI_Y for b in TI_Y if TI_Y[a] < TI_Y[b]),
                  "spread": max(max(pr[c] for c in g) - min(pr[c] for c in g) for g in pg)}
    out["ti_levels"] = len(exact)
    out["ti_groups"] = exact
    assert ti_groups == exact
    res["ti"] = out


# ---------------------------------------------------------------- before
def before(res):
    c01 = json.loads((REPO / "ch01" / "meas01.json").read_text())["palette"]
    e = res["plate"]["eu"]
    rgb = {int(k): v for k, v in e["rgb"].items()}
    pr = {int(k): v for k, v in e["print"].items()}
    assert all(list(c01["rgb"][c]) == rgb[c] for c in range(1, 16))
    assert all(c01["grey"][c] == pr[c] for c in range(1, 16))
    assert c01["largest_group"] == [2, 5, 8, 13]
    b0 = res["border"]["eu"]["rgb"]["0"]
    # code 0 as the backdrop: code 1's black (chapter 1's code 0 was a paper
    # letting a backdrop of code 1 through)
    assert b0 == list(c01["rgb"][1]) == list(c01["rgb"][0])
    res["before"] = {"ch01_rgb": True, "ch01_grey": True, "ch01_code0": c01["rgb"][0],
                     "border_code0": b0}


# ---------------------------------------------------------------- openmsx
def openmsx(res):
    if not versions.builds():
        res["openmsx"] = {"skipped": "OPENMSX_BUILDS not set"}
        return
    import hashlib
    roms = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()[:16] for p in sorted(HERE.glob("*.rom"))}
    out = versions.every_build(["appE"], [s for s in STEPS if s != "openmsx"], keep=None, values=True)
    res["openmsx"] = {"roms": roms, **out}


# ---------------------------------------------------------------- the main
STEPS = ["plate", "border", "pairs", "ti", "before", "openmsx"]


def main(names=()):
    res = json.loads(OUT_JSON.read_text()) if names and OUT_JSON.exists() else {}
    for name in STEPS:
        if names and name not in names:
            continue
        sub = json.loads(json.dumps(res))      # a step sees the steps before it, as saved
        globals()[name](sub)
        res[name] = json.loads(json.dumps(sub[name]))
        res = {k: res[k] for k in STEPS if k in res}
        OUT_JSON.write_text(json.dumps(res, indent=1) + "\n")
        print(" ", name, "ok", flush=True)
    return res


if __name__ == "__main__":
    main(sys.argv[1:])
