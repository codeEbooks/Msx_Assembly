#!/usr/bin/env python3
"""meas32.py -- racing the beam on an MSX1, measured.

    python3 gen32.py && ./build.sh && python3 meas32.py
                                  python3 meas32.py poll split     only these

Every frame of every film, on both machines: the T-state of every write the
debugger stops on (the breakpoint on its OUT, and 8 T-states into it), the
line and the pixel where it shows (chapter 18's shows()), held against the
window gen32.py works out for it; the IN that found F or 5S, against chapter
19's signal and chapter 27's line; and the photograph of the frame, every
pixel of the drawn columns against vdpscreen.py's paper over a backdrop that
changes where the writes show.

  poll      poll.rom: the bars counted from the end of the paper (figures 32.1, 32.2)
  fifth     fifth.rom: the bars from the fifth sprite (figure 32.1)
  steady    steady.rom: the bars from the interrupt, the CPU halted (figure 32.1)
  split     split.rom: R#4 between two lines, from the handler (figures 32.2, 32.3)
  crowd     WHERE IT BREAKS: crowd.rom (figure 32.4)
  half      poll.rom with the display off: chapter 18's x on the border, and
            the half pixel that goes the other way behind the paper
  prices    walk.py's T-states for the paths the windows are counted from
  answers   the workshop, tried (for Appendix I)
  openmsx   all of it again with every other build (tools/versions.py)
"""
import json
import math
import sys
from fractions import Fraction
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "tools"))
import meas        # noqa: E402
import msxcap      # noqa: E402
import probe as dbg  # noqa: E402
import versions    # noqa: E402
sys.path.insert(0, str(HERE))
import gen32       # noqa: E402
sys.path.remove(str(HERE))
sys.path.insert(0, str(HERE))      # gen32 put chapters 26 and 30 first: this folder's files win
for mod in ("vdpscreen", "walk"):
    sys.modules.pop(mod, None)
import vdpscreen   # noqa: E402
import walk        # noqa: E402  (chapter 31's, with chapter 32's ED forms)

assert Path(vdpscreen.__file__).parent == HERE and Path(walk.__file__).parent == HERE

CAPS = HERE / "captures"
EU, JP = gen32.EU, gen32.JP
TAG = {EU: "eu", JP: "jp"}
L = gen32.LINE_T
PAPER0 = gen32.PAPER0
ROW0 = {m: PAPER0[m] - meas.PAPER_Y0 for m in (EU, JP)}     # the frame's line of capture row 0
POS = "[machine_info VDP_frame_count] [machine_info VDP_cycle_in_frame]"
REGS = " ".join(f"[debug read {{VDP regs}} {i}]" for i in range(8))
VRAM = 'binary scan [debug read_block {VRAM} 0 16384] H* h; L "vram $h"'
F0 = 'L "f0 [machine_info VDP_frame_count]"\n'
TOO_FAST = ('proc ::toofast_cb {args} { L "fast [machine_info time]" }\n'
            'set VDP.too_fast_vram_access_callback ::toofast_cb\n')
MARKS = [f"{k}{i}" for i in range(len(gen32.BARS)) for k in "be"]
COLOUR = {f"b{i}": c for i, (_, c) in enumerate(gen32.BARS)} | {f"e{i}": gen32.WHITE for i in range(3)}

PALETTE = [tuple(c) for c in json.loads((REPO / "ch01" / "meas01.json").read_text())["palette"]["rgb"]]
CODE = {rgb: n for n, rgb in enumerate(PALETTE) if n}


def rom(name):
    return HERE / f"{name}.rom"


def sym(name):
    return dbg.sym(HERE / f"{name}.sym")


def codes(png):
    im = Image.open(png).convert("RGB")
    px = im.load()
    return [[CODE.get(px[x, y]) for x in range(im.width)] for y in range(im.height)]


def run(name, frames, tcl, machine):
    lines = msxcap.run_tcl(rom(name), frames, F0 + TOO_FAST + tcl, machine=machine)
    w = [l.split() for l in lines]
    assert not [x for x in w if x[0] == "fast"], (name, machine, "an access too soon")
    return w


def t_of(fc, cyc, frame, machine):
    """a breakpoint's T-state, counted from the start of FRAME"""
    return (int(fc) - frame) * gen32.FRAME_T[machine] + Fraction(int(cyc), 6)


def shows(t):
    """(line of the frame, x of the capture) where a change written at T-state
    T shows: x = ceil(1.5 w - 31) for whole T-state w of the line (chapter 18,
    whose T-states are the debugger's VDP cycles over 6, rounded down)"""
    line, w = divmod(math.floor(t), L)
    return line, math.ceil(1.5 * w - 31)


def shows_paper(t):
    """the same behind the paper, where the backdrop shows through a pattern's
    0s: the half pixel of an odd w goes the other way, floor(1.5 w - 31)
    (section half below)"""
    line, w = divmod(math.floor(t), L)
    return line, math.floor(1.5 * w - 31)


def num(f):
    return int(f) if f == int(f) else round(float(f), 2)


def in_paper(x, y):
    return meas.PAPER_X0 <= x < meas.PAPER_X0 + 256 and meas.PAPER_Y0 <= y < meas.PAPER_Y0 + 192


def raster(paper, changes, first, machine, paper_rule=True):
    """the capture the model expects: PAPER (192 x 256, 0 where the paper is
    transparent) over the backdrop, which is FIRST until the first of CHANGES,
    [line, x, x behind the paper, colour] in raster order, and each change's
    colour after it; PAPER_RULE False: chapter 18's x behind the paper too"""
    out = []
    for y in range(meas.CAPTURE_H):
        line = ROW0[machine] + y
        now = first
        for c in changes:
            if c[0] < line:
                now = c[3]
        here = [c for c in changes if c[0] == line]
        row = [None] * meas.CAPTURE_W
        for x in range(meas.DRAWN[0], meas.DRAWN[1] + 1):
            inside = in_paper(x, y)
            col = now
            for c in here:
                if x >= (c[2] if inside and paper_rule else c[1]):
                    col = c[3]
            px, py = x - meas.PAPER_X0, y - meas.PAPER_Y0
            p = paper[py][px] if inside else 0
            row[x] = p or col
        out.append(row)
    return out


def mismatch(model, photo):
    return sum(1 for y in range(meas.CAPTURE_H) for x in range(meas.DRAWN[0], meas.DRAWN[1] + 1)
               if model[y][x] != photo[y][x])


def transparent(regs):
    r = list(regs)
    r[7] = 0
    return r


SPANS = [(0, 0x1000), (0x1800, 0x1B00), (0x2000, 0x2020), (0x3800, 0x3810)]


def differ(vram, want, spans):
    return sum(1 for a, b in spans for i in range(a, b) if vram[i] != want[i])


# ---------------------------------------------------------------- the bars
def bars_film(name, machine, frames=40, setup=""):
    """every frame of poll.rom, fifth.rom, steady.rom or crowd.rom: the
    writes, the IN that found F (and 5S) or the handler's start, the VRAM and
    the registers at b0"""
    s = sym(name)
    tcl = setup + 'set ::inF "0 0"\nset ::in5 "0 0"\n'
    tcl += f'debug set_bp {s["isr" if name == "steady" else "frame"]} {{}} {{ set ::inF "{POS}" }}\n'
    if name in ("fifth", "crowd"):
        tcl += f'debug set_bp {s["loop.five"]} {{}} {{ set ::in5 "{POS}" }}\n'
    tcl += (f'debug set_bp {s["b0"]} {{}} {{ L "regs {REGS}"; {VRAM}; '
            f'L "in $::inF $::in5"; L "b0 {POS}" }}\n')
    for mk in MARKS[1:]:
        tcl += f'debug set_bp {s[mk]} {{}} {{ L "{mk} {POS}" }}\n'
    w = run(name, frames, tcl, machine)
    f0 = int(next(x for x in w if x[0] == "f0")[1])
    out, cur = [], None
    for x in w:
        if x[0] == "regs":
            cur = {"regs": [int(v) for v in x[1:]]}
        elif x[0] == "vram":
            cur["vram"] = bytes.fromhex(x[1])
        elif x[0] == "in":
            cur["in"] = [int(v) for v in x[1:]]
        elif x[0] in MARKS:
            cur[x[0]] = (int(x[1]), int(x[2]))
            if x[0] == MARKS[-1]:
                out.append(cur)
    assert len(out) == gen32.FRAMES, (name, machine, len(out))
    return f0, out


def bars_frame(name, machine, fr, k=0):
    """one frame's numbers: every write's T-state in its frame, where it shows,
    and the IN before it"""
    c = fr["b0"][0]
    t = {mk: t_of(*fr[mk], c, machine) + 8 for mk in MARKS}
    assert all(fr[mk][0] == c for mk in MARKS), (name, machine, "a bar in another frame")
    where = {mk: shows(v) for mk, v in t.items()}
    gaps = [t[b] - t[a] for a, b in zip(MARKS, MARKS[1:])]
    lo, hi = gen32.windows(name, machine, k)
    inside = lo <= t["b0"] < hi
    fc, cyc = fr["in"][:2]
    t_in = t_of(fc, cyc, c, machine)
    # the IN that found F, from the signal of its own frame
    since_f = Fraction(cyc, 6) - gen32.SIGNAL_T[machine]
    row = {"frame": c, "t": num(t["b0"]), "line": where["b0"][0] - PAPER0[machine],
           "x": where["b0"][1], "inside": inside, "gaps": [int(g) for g in gaps],
           "in_after_f": num(since_f), "in_to_write": num(t["b0"] - t_in), "exact_f": since_f,
           "changes": [[where[mk][0], where[mk][1], shows_paper(t[mk])[1], COLOUR[mk]] for mk in MARKS],
           "odd_w": int(math.floor(t["b0"]) % L % 2)}
    if name in ("fifth", "crowd"):
        fc5, cyc5 = fr["in"][2:]
        t5 = t_of(fc5, cyc5, c, machine)
        first = first_five_of(fr["vram"], fr["regs"])
        row["five_line"] = first
        row["exact_5s"] = t5 - (PAPER0[machine] + first) * L
        row["in_after_5s"] = num(row["exact_5s"])
        row["in5_to_write"] = num(t["b0"] - t5)
    return row


def first_five_of(vram, regs):
    on = vdpscreen.on_lines(vram, regs)[0]
    hit = [line for line, v in on.items() if len(v) > 4]
    return min(hit) if hit else None


def bar_photos(name, machine, f0, film, rows, prefix=None, setup="", paper_rule=True):
    """the photograph of every frame of the film, against the model; the
    capture number that fits, counted from the frame the debugger names"""
    frames = [r["frame"] - f0 for r in rows]
    shots = sorted({f + d for f in frames for d in (-1, 0, 1)})
    pngs = msxcap.capture(rom(name), shots, CAPS, f"{prefix or name}_{TAG[machine]}_f", machine=machine,
                          tcl_setup=setup)
    ph = {f: codes(pngs[f]) for f in shots}
    models = [raster(vdpscreen.draw(fr["vram"], transparent(fr["regs"])), r["changes"], gen32.WHITE, machine,
                     paper_rule) for fr, r in zip(film, rows)]
    fits = [d for d in (-1, 0, 1) if all(mismatch(mo, ph[f + d]) == 0 for mo, f in zip(models, frames))]
    assert len(fits) == 1, (name, machine, fits)
    keep = {f + fits[0] for f in frames}
    for f in shots:
        if f not in keep:
            pngs[f].unlink()
    return fits[0], {f + fits[0]: ph[f + fits[0]] for f in frames}, models


def loop_t(name, machine):
    """walk.py: poll.asm from the IN that finds F round to the next call's first
    IN; steady.asm from the handler's first instruction to the HALT it returns
    to (the answer and the JP, 30, the rest of the way, change nothing modulo 5)"""
    rate = 0x80 if machine == EU else 0x00
    wk = walker(name, rate, 0x80)
    if name == "poll":
        wk.run("init", "loop")
        wk.run("loop", "frame")
        return wk.lap("frame")
    wk.run("init", "main")
    t = wk.call("isr") - 18                     # to the instruction after HALT
    wk.sym["main.after"] = wk.sym["main"] + 1
    return t + wk.run("main.after", "main")


def bars(name):
    def go():
        out = {}
        for m in (EU, JP):
            f0, film = bars_film(name, m)
            want = gen32.vram_of(name)
            for fr in film:
                assert fr["regs"] == gen32.REGS[name], (name, m, fr["regs"])
                if name != "crowd":
                    assert differ(fr["vram"], want, SPANS + [(0x1B00, 0x1B00 + 4 * len(gen32.sprites(name)) + 1)]) == 0
            rows = [bars_frame(name, m, fr) for fr in film]
            for r in rows:
                assert r["inside"], (name, m, r)
                assert r["gaps"] == [8 * L, 40 * L] * 2 + [8 * L], (name, m, r["gaps"])
                assert r["line"] == gen32.BARS[0][0], (name, m, r)
            fit, photos, _ = bar_photos(name, m, f0, film, rows)
            # chapter 18's x behind the paper too: the frames whose photograph it misses
            ceil_misses = sum(1 for fr, r in zip(film, rows) if mismatch(raster(
                vdpscreen.draw(fr["vram"], transparent(fr["regs"])), r["changes"], gen32.WHITE, m, False),
                photos[r["frame"] - f0 + fit]))
            assert ceil_misses == sum(r["odd_w"] for r in rows), (name, m, ceil_misses)
            xs = [r["x"] for r in rows]
            lo, hi = gen32.windows(name, m)
            res = {"frames": len(rows), "x": xs, "x_span": [min(xs), max(xs)], "different_x": len(set(xs)),
                   "t_in_line": [num(r["t"] - (PAPER0[m] + gen32.BARS[0][0]) * L) for r in rows],
                   "window": [num(lo - (PAPER0[m] + gen32.BARS[0][0]) * L), num(hi - (PAPER0[m] + gen32.BARS[0][0]) * L)],
                   "window_x": [shows(lo)[1], shows(hi - Fraction(1, 6))[1]],
                   "x_paper": [r["changes"][0][2] for r in rows],
                   "odd_w": sum(r["odd_w"] for r in rows),
                   "ends": [[c[0] - PAPER0[m], c[1]] for c in rows[0]["changes"]],
                   "fit": fit, "shots": sorted(photos), "in_to_write": sorted({r["in_to_write"] for r in rows})}
            if name == "poll":
                res["in_after_f"] = [r["in_after_f"] for r in rows]
                assert all(-gen32.IN_SEES <= r["exact_f"] < -gen32.IN_SEES + gen32.POLL_TURN for r in rows)
                assert res["in_to_write"] == [gen32.POLL_AFTER + gen32.POLL_TURN * gen32.poll_turns(m)]
                # from frame to frame the IN that finds F moves by the loop, the walk
                # from it round to the next frame's first IN, less the frame, modulo a turn
                lap = loop_t("poll", m)
                step = (lap - gen32.FRAME_T[m]) % gen32.POLL_TURN
                assert all((b["exact_f"] - a["exact_f"] - step) % gen32.POLL_TURN == 0
                           for a, b in zip(rows, rows[1:]))
                res["lap"], res["step"] = lap, step
            elif name == "steady":
                # the handler's first instruction: the answer and the JP after the signal,
                # and up to a step of HALT
                res["isr_after_f"] = [r["in_after_f"] for r in rows]
                res.pop("in_to_write")
                res["isr_to_write"] = sorted({r["in_to_write"] for r in rows})
                assert all(19 + 11 <= r["exact_f"] < 19 + 11 + gen32.HALT_STEP for r in rows)
                assert res["isr_to_write"] == [gen32.STEADY_AFTER - 30 + gen32.POLL_TURN * gen32.steady_turns(m)]
                # the handler's start moves by its trip back to HALT, less the frame,
                # modulo the HALT's step
                lap = loop_t("steady", m)
                step = (lap - gen32.FRAME_T[m]) % gen32.HALT_STEP
                assert all((b["exact_f"] - a["exact_f"] - step) % gen32.HALT_STEP == 0
                           for a, b in zip(rows, rows[1:]))
                res["lap"], res["step"] = lap, step
            else:
                res.pop("in_to_write")
                res["in_after_5s"] = [r["in_after_5s"] for r in rows]
                res["in5_to_write"] = sorted({r["in5_to_write"] for r in rows})
                assert res["in5_to_write"] == [gen32.FIVE_AFTER]
                assert all(-gen32.IN_SEES - gen32.FIVE_EDGE <= r["exact_5s"] <
                           -gen32.IN_SEES + gen32.FIVE_TURN + gen32.FIVE_EDGE for r in rows)
                assert all(r["five_line"] == gen32.BARS[0][0] for r in rows)
            out[TAG[m]] = res
        return out
    return go


# ---------------------------------------------------------------- split
def split():
    out = {}
    s = sym("split")
    for m in (EU, JP):
        tcl = (f'debug set_bp {s["isr"]} {{}} {{ L "isr {POS}" }}\n'
               f'debug set_bp {s["s0"]} {{}} {{ L "s0 {POS}" }}\n'
               f'debug set_bp {s["s1"]} {{}} {{ L "regs {REGS}"; {VRAM}; L "s1 {POS}" }}\n')
        w = run("split", 40, tcl, m)
        f0 = int(next(x for x in w if x[0] == "f0")[1])
        isr = [x for x in w if x[0] == "isr"]
        s0 = [x for x in w if x[0] == "s0"]
        s1 = [x for x in w if x[0] == "s1"]
        regs = [[int(v) for v in x[1:]] for x in w if x[0] == "regs"]
        vrams = [bytes.fromhex(x[1]) for x in w if x[0] == "vram"]
        assert len(isr) == len(s0) == len(s1) == gen32.FRAMES, (m, len(isr), len(s1))
        rows = []
        for a, b, c, r, v in zip(isr, s0, s1, regs, vrams):
            fc = int(c[1])                                  # the frame s1 writes in
            t_isr = Fraction(int(a[2]), 6)
            t0 = t_of(b[1], b[2], int(a[1]), m) + 8
            t1 = t_of(c[1], c[2], fc, m) + 8
            line, x = shows(t1)
            lo, hi = gen32.windows("split", m)
            rows.append({"frame": fc, "isr_after_f": num(t_isr - gen32.SIGNAL_T[m]),
                         "s0": shows(t0), "s1_line": line - PAPER0[m], "s1_x": x,
                         "s1_t": num(t1 - (PAPER0[m] + gen32.SPLIT) * L),
                         "inside": lo <= t1 < hi,
                         "gap": (line == PAPER0[m] + gen32.SPLIT - 1 and x >= 288) or
                                (line == PAPER0[m] + gen32.SPLIT and x < 32),
                         "s0_to_s1": num(t_of(c[1], c[2], int(a[1]), m) + 8 - t0)})
            assert r == gen32.REGS["split"], (m, r)
            assert differ(v, gen32.vram_of("split"), SPANS + [(0x1B00, 0x1B01)]) == 0
        for r in rows:
            assert r["inside"] and r["gap"], (m, r)
            assert 19 + 11 <= r["isr_after_f"] < 19 + 11 + gen32.HALT_STEP, (m, r)
            assert r["s0"][0] == gen32.FLAG_LINE[m]
            assert r["s0_to_s1"] == gen32.SPLIT_AFTER - (19 + 11 + 37 + 8) + gen32.POLL_TURN * gen32.split_turns(m), r
        # the photographs: the rows above line 96 in the set at $0000, the rest in the bold one
        vram, rg = vrams[0], regs[0]
        r1 = list(rg)
        r1[4] = 1
        top, bottom = vdpscreen.draw(vram, rg), vdpscreen.draw(vram, r1)
        paper = top[:gen32.SPLIT] + bottom[gen32.SPLIT:]
        model = raster(paper, [], gen32.WHITE, m)
        frames = [r["frame"] - f0 for r in rows]
        after = frames[-1] + 3            # the program done: no handler, R#4 left at 1
        shots = sorted({f + d for f in frames for d in (-1, 0, 1)} | {after})
        pngs = msxcap.capture(rom("split"), shots, CAPS, f"split_{TAG[m]}_f", machine=m)
        ph = {f: codes(pngs[f]) for f in shots}
        fits = [d for d in (-1, 0, 1) if all(mismatch(model, ph[f + d]) == 0 for f in frames)]
        assert len(fits) == 1, (m, fits)
        for f in shots:
            if f - fits[0] not in frames and f != after:
                pngs[f].unlink()
        whole = raster(top, [], gen32.WHITE, m)
        bold = raster(bottom, [], gen32.WHITE, m)
        assert mismatch(bold, ph[after]) == 0, (m, "the frames after the film")
        xs = [r["s1_x"] for r in rows]
        out[TAG[m]] = {"frames": len(rows), "turns": gen32.split_turns(m),
                       "isr_after_f": [r["isr_after_f"] for r in rows],
                       "s0": sorted({tuple(r["s0"]) for r in rows}),
                       "s1_lines": sorted({r["s1_line"] for r in rows}), "s1_x": xs,
                       "s1_t": [r["s1_t"] for r in rows],
                       "s1_t_span": [min(r["s1_t"] for r in rows), max(r["s1_t"] for r in rows)],
                       "s0_to_s1": sorted({r["s0_to_s1"] for r in rows}),
                       "fit": fits[0], "shots": [f + fits[0] for f in frames], "after": after,
                       "off_if_one_set": mismatch(whole, ph[frames[0] + fits[0]]),
                       "off_if_all_bold": mismatch(bold, ph[frames[0] + fits[0]])}
        assert out[TAG[m]]["off_if_one_set"] > 0 and out[TAG[m]]["off_if_all_bold"] > 0
    return out


# ---------------------------------------------------------------- crowd
def crowd():
    out = {}
    for m in (EU, JP):
        f0, film = bars_film("crowd", m)
        rows = []
        for fr in film:
            assert fr["regs"] == gen32.REGS["crowd"]
            k = (fr["vram"][0x1B00 + 4 * 5] - (gen32.CROWD_Y0 - 1)) // gen32.CROWD_STEP
            want = gen32.vram_of("crowd", k)
            assert differ(fr["vram"], want, SPANS + [(0x1B00, 0x1B00 + 41)]) == 0, (m, k)
            r = bars_frame("crowd", m, fr, k)
            r["k"] = k
            r["balls_from"] = gen32.CROWD_Y0 + gen32.CROWD_STEP * k
            assert r["five_line"] == gen32.first_five("crowd", k) == r["line"], (m, r)
            assert r["inside"], (m, r)
            # the balls rule 10 hides: the paper with four sprites a line, and with any number
            lim = vdpscreen.LIMIT
            vdpscreen.LIMIT = 32
            free = vdpscreen.draw(fr["vram"], transparent(fr["regs"]))
            vdpscreen.LIMIT = lim
            kept = vdpscreen.draw(fr["vram"], transparent(fr["regs"]))
            r["hidden_px"] = sum(1 for y in range(192) for x in range(256) if free[y][x] != kept[y][x])
            r["hidden_lines"] = sorted({y for y in range(192) for x in range(256) if free[y][x] != kept[y][x]})
            rows.append(r)
        fit, photos, models = bar_photos("crowd", m, f0, film, rows)
        out[TAG[m]] = {"frames": len(rows), "k": [r["k"] for r in rows],
                       "balls_from": [r["balls_from"] for r in rows],
                       "bar_line": [r["line"] for r in rows], "x": [r["x"] for r in rows],
                       "jumped": sum(1 for r in rows if r["line"] != gen32.BARS[0][0]),
                       "hidden_px": [r["hidden_px"] for r in rows],
                       "hidden_lines": [[min(r["hidden_lines"]), max(r["hidden_lines"])] if r["hidden_lines"]
                                        else None for r in rows],
                       "in5_to_write": sorted({r["in5_to_write"] for r in rows}),
                       "fit": fit, "shots": sorted(photos)}
        assert out[TAG[m]]["in5_to_write"] == [gen32.FIVE_AFTER]
    return out


# ---------------------------------------------------------------- half
def half():
    """poll.rom again, the display put off by the debugger once the picture
    is set up: the whole frame is border, and chapter 18's x holds for every
    change, the odd w's as well"""
    out = {}
    s = sym("poll")
    off = (f'set ::off [debug set_bp {s["loop"]} {{}} '
           f'{{ debug write {{VDP regs}} 1 0x80; debug remove_bp $::off }}]\n')
    for m in (EU, JP):
        f0, film = bars_film("poll", m, setup=off)
        assert all(fr["regs"][1] == 0x80 for fr in film)
        rows = [bars_frame("poll", m, fr) for fr in film]
        fit, photos, _ = bar_photos("poll", m, f0, film, rows, prefix="half", setup=off, paper_rule=False)
        paper_rule_misses = sum(1 for fr, r in zip(film, rows) if mismatch(raster(
            vdpscreen.draw(fr["vram"], transparent(fr["regs"])), r["changes"], gen32.WHITE, m, True),
            photos[r["frame"] - f0 + fit]))
        out[TAG[m]] = {"frames": len(rows), "odd_w": sum(r["odd_w"] for r in rows), "fit": fit,
                       "x": [r["x"] for r in rows], "paper_rule_misses": paper_rule_misses,
                       "shots": sorted(photos)}
    return out


# ---------------------------------------------------------------- prices
def walker(name, rate, status):
    wk = walk.Walk(HERE / name, read_port=lambda port, t: status if port == 0x99 else 0)
    wk.mem[0x2B] = rate
    return wk


def prices():
    out = {}
    for tag, rate in (("eu", 0x80), ("jp", 0x00)):
        wk = walker("poll", rate, 0x80)
        wk.run("init", "loop")
        wk.run("loop", "frame")
        n = wk.word(wk.sym["wait"])
        to_b0 = wk.run("frame", "b0") + 8
        spacing = [wk.run(a, b) for a, b in zip(MARKS, MARKS[1:])]
        out[f"poll_{tag}"] = {"turns": n, "in_to_write": to_b0, "after": to_b0 - gen32.POLL_TURN * n,
                              "gaps": spacing}
        wk = walker("steady", rate, 0x80)
        wk.run("init", "main")
        n = wk.word(wk.sym["wait"])
        to_b0 = wk.run("isr", "b0") + 8
        out[f"steady_{tag}"] = {"turns": n, "isr_to_write": to_b0,
                                "after": 19 + 11 + to_b0 - gen32.POLL_TURN * n,
                                "gaps": [wk.run(a, b) for a, b in zip(MARKS, MARKS[1:])]}
        # the whole handler, from the signal to its return, the HALT's step aside
        wk = walker("steady", rate, 0x80)
        wk.run("init", "main")
        out[f"steady_{tag}"]["handler"] = 19 + 11 + wk.call("isr") - 18
        wk = walker("split", rate, 0x80)
        wk.run("init", "main")
        n = wk.word(wk.sym["wait"])
        a, b = wk.run("isr", "s0"), wk.run("s0", "s1")
        out[f"split_{tag}"] = {"turns": n, "isr_to_s0": a, "s0_to_s1": b,
                               "after": 19 + 11 + a + b + 8 - gen32.POLL_TURN * n}
    # a turn of each loop that reads the status: from the IN to the write, the
    # first read finding nothing and the second the flag, less the same with
    # the first read finding it
    def turn(name, mark, flag):
        t = []
        for first in ([flag], [0, flag]):
            wk = walker(name, 0x80, 0xC0)
            wk.run("init", "loop")
            wk.run("loop", mark)
            wk.read_port = lambda port, tt, it=iter(first): next(it) if port == 0x99 else 0
            t.append(wk.run(mark, "b0"))
        return t[1] - t[0]
    out["frame_turn"] = turn("poll", "frame", 0x80)
    out["five_turn"] = turn("fifth", "loop.five", 0x40)
    for name in ("fifth", "crowd"):
        wk = walker(name, 0x80, 0xC0)
        wk.run("init", "loop")
        out[f"{name}_loop_to_five"] = wk.run("loop", "loop.five")
        out[f"{name}_after"] = wk.run("loop.five", "b0") + 8
    out["place"] = walker("crowd", 0x80, 0xC0).call("place")
    assert out["poll_eu"]["after"] == out["poll_jp"]["after"] == gen32.POLL_AFTER
    assert out["split_eu"]["after"] == out["split_jp"]["after"] == gen32.SPLIT_AFTER
    assert out["steady_eu"]["after"] == out["steady_jp"]["after"] == gen32.STEADY_AFTER
    assert out["steady_eu"]["gaps"] == out["poll_eu"]["gaps"]
    assert out["fifth_after"] == out["crowd_after"] == gen32.FIVE_AFTER
    assert out["frame_turn"] == gen32.POLL_TURN and out["five_turn"] == gen32.FIVE_TURN
    assert out["poll_eu"]["gaps"] == [8 * L, 40 * L] * 2 + [8 * L]
    assert out["poll_eu"]["turns"] == gen32.poll_turns(EU) and out["poll_jp"]["turns"] == gen32.poll_turns(JP)
    return out


# ---------------------------------------------------------------- answers
def answers():
    m = json.loads((HERE / "meas32.json").read_text())
    out = {}
    # 1: the window of poll.asm's first bar, in pixels, with frame's loop of 30
    # T-states and with chapter 19's of 28
    out["q1"] = {"px30": num(Fraction(3, 2) * gen32.POLL_TURN), "px28": num(Fraction(3, 2) * 28)}
    # 2: (wait) at 50 Hz for the middle of the window on line 100 of the paper
    aim = (gen32.FRAME_T[EU] + (PAPER0[EU] + 100) * L + gen32.MIDDLE_W - Fraction(gen32.POLL_TURN, 2))
    n = round((aim - gen32.SIGNAL_T[EU] + gen32.IN_SEES - gen32.POLL_AFTER) / gen32.POLL_TURN)
    out["q2"] = {"turns": n, "more": n - gen32.poll_turns(EU), "lines": 52, "per_line": num(Fraction(L, 30))}
    # 3: the lines from the signal to line 48 of the paper, on each machine
    out["q3"] = {t: gen32.LINES[mc] - gen32.FLAG_LINE[mc] + PAPER0[mc] + gen32.BARS[0][0]
                 for t, mc in (("eu", EU), ("jp", JP))}
    # 4: the frames modulo the HALT's step
    out["q4"] = {t: gen32.FRAME_T[mc] % gen32.HALT_STEP for t, mc in (("eu", EU), ("jp", JP))}
    # 5: split.asm: how far its writes may move and still fall in the gap
    gap0, gap1 = gen32.GAP_W, gen32.GAP_END
    out["q5"] = {}
    for t, mc in (("eu", EU), ("jp", JP)):
        lo, hi = (v - (PAPER0[mc] + gen32.SPLIT) * L for v in gen32.windows("split", mc))
        out["q5"][t] = {"early": num(lo - gap0), "late": num(gap1 - hi), "gap": num(gap1 - gap0)}
    # 6: steady.asm's handler at 50 Hz, from the signal to its return, and the lines left
    wk = walker("steady", 0x80, 0x80)
    wk.run("init", "main")
    t = 19 + 11 + wk.call("isr") - 18
    assert t == m["prices"]["steady_eu"]["handler"]
    out["q6"] = {"t": t, "lines": num(Fraction(t, L)), "left": gen32.FRAME_T[EU] - t,
                 "left_lines": (gen32.FRAME_T[EU] - t - 4) // L}
    # 7 and 8: crowd.asm
    c = m["crowd"]["eu"]
    out["q7"] = {"frames": [k for k, line in zip(c["k"], c["bar_line"]) if line != gen32.BARS[0][0]],
                 "lines": [line for line in c["bar_line"] if line != gen32.BARS[0][0]],
                 "balls_from": c["balls_from"]}
    ball = sum(bin(b).count("1") for b in gen32.BALL)
    worst = max(c["hidden_px"])
    out["q8"] = {"ball_px": ball, "worst": worst, "balls": worst // ball,
                 "frame": c["k"][c["hidden_px"].index(worst)]}
    assert out["q8"]["balls"] == 5 and min(c["hidden_px"]) == ball
    # 9: fifth.asm's signals at Y = 99: the bars' lines, and the paper's last line
    first = 99 + 1
    out["q9"] = {"y": 99, "bars": [[first + d, first + d + gen32.BAR_LINES - 1] for d in (0, 48, 96)],
                 "paper_last": 191}
    # 10: split.asm once its frames are done: the photograph, all bold
    out["q10"] = {t: m["split"][t]["after"] for t in ("eu", "jp")}
    # 11: the frames before the first bar begins again where it began: the turn
    # (or HALT's step) over its greatest common divisor with the step a frame
    out["q11"] = {name: {t: turn // math.gcd(m[name][t]["step"], turn) for t in ("eu", "jp")}
                  for name, turn in (("poll", gen32.POLL_TURN), ("steady", gen32.HALT_STEP))}
    st = m["steady"]["eu"]["x"]
    assert st[:11] == st[5:16] and len(set(st[:5])) == 5          # steady.asm: every 5, seen
    return out


# ---------------------------------------------------------------- openmsx
OPENMSX_SECTIONS = ["poll", "fifth", "steady", "split", "crowd", "half"]


def openmsx():
    if not versions.builds():
        return {"skipped": "OPENMSX_BUILDS not set"}
    return versions.every_build(["ch32"], OPENMSX_SECTIONS)


SECTIONS = {"poll": bars("poll"), "fifth": bars("fifth"), "steady": bars("steady"), "split": split,
            "crowd": crowd,
            "half": half, "prices": prices, "answers": answers, "openmsx": openmsx}


def main(names=()):
    CAPS.mkdir(exist_ok=True)
    path = HERE / "meas32.json"
    m = json.loads(path.read_text()) if names and path.exists() else {}
    for name in names or SECTIONS:
        print(name, flush=True)
        m[name] = SECTIONS[name]()
        m = {k: m[k] for k in SECTIONS if k in m}
        path.write_text(json.dumps(m, indent=1) + "\n")
    return m


if __name__ == "__main__":
    main(sys.argv[1:])
