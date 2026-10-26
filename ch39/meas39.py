#!/usr/bin/env python3
"""meas39.py -- collisions, measured.

    python3 gen39.py && ./build.sh && python3 meas39.py
                                  python3 meas39.py walls flags      only these

  walls     walls.rom, corners.rom and ytop.rom on both machines: where each
            ball stopped and in which frame, against the model of each
            walled; every call of walled timed by the debugger against
            walk.py; the pixels of the balls on the walls' cells, frame by
            frame; photos (figure 39.1)
  flags     flags.rom on both machines: the status after each scene against
            vdpscreen.py's rule 12
  shapes    shapes.rom on both machines: C, boxed and touched at each of
            1,369 places against the shapes' pixels; every call of boxed
            and touched timed against walk.py; the photo (figure 39.2)
  pairs     meet.rom and blame.rom on both machines: the places and the
            frames each pair stopped, against the model of the frame loop;
            the frames the tests ran and their T-states; photos (figure 39.3)
  prices    what each test costs, from the timed calls
  answers   the workshop, tried (for Appendix I)
  openmsx   all of it again with every other build (tools/versions.py)
"""
import json
import re
import sys
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
import gen39       # noqa: E402
sys.path.remove(str(HERE))
sys.path.insert(0, str(HERE))      # gen39 put chapters 26 and 27 first: this folder's files win
for mod in ("vdpscreen", "walk"):
    sys.modules.pop(mod, None)
import vdpscreen   # noqa: E402
import walk        # noqa: E402  (chapter 25's, with what chapters 28 to 32 added)

assert Path(vdpscreen.__file__).parent == HERE and Path(walk.__file__).parent == HERE

CAPS = HERE / "captures"
EU, JP = gen39.EU, gen39.JP
MACHINES = gen39.MACHINES
TAG = {EU: "eu", JP: "jp"}
CLOCK = dbg.CLOCK
PALETTE = [tuple(c) for c in json.loads((REPO / "ch01" / "meas01.json").read_text())["palette"]["rgb"]]
CODE = {rgb: n for n, rgb in enumerate(PALETTE) if n}
REGS = [2, 0xE2, 6, 0x9F, 0, 0x36, 7, 0x0F]
BALL = gen39.BALL
CORNERS_SHOT = 50               # corners.rom: the first ball half over the post
PAIR_SHOT = 45

# the VRAM and the registers, logged under a tag
STATE = r"""
proc V {tag} {
    binary scan [debug read_block VRAM 0 16384] H* h
    L "$tag vram $h"
    set v {}
    for {set i 0} {$i < 8} {incr i} { lappend v [debug read {VDP regs} $i] }
    L "$tag regs $v"
}
proc M {tag addr n} {
    binary scan [debug read_block memory $addr $n] H* h
    L "$tag mem $h"
}
"""


def rom(name):
    return HERE / f"{name}.rom"


def sym(name):
    return dbg.sym(HERE / f"{name}.sym")


def t_state(seconds):
    t = float(seconds) * CLOCK
    assert abs(t - round(t)) < 1e-3, seconds
    return round(t)


def run(name, machine, frames, at_init="", events=None):
    lines = msxcap.run_tcl(rom(name), frames, at_init, machine=machine, events=events or {},
                           tcl_setup=STATE, timeout=900)
    return [l.split() for l in lines]


def logged(w, tag, kind):
    x = next(x for x in w if x[0] == tag and x[1] == kind)
    if kind in ("vram", "mem"):
        return bytes.fromhex(x[2])
    return [int(v) for v in x[2:]]


def call_site(name, target):
    """the address of NAME's "call TARGET" (the first), from its listing"""
    for line in (HERE / f"{name}.lst").read_text().splitlines():
        m = dbg.LST.match(line)
        if m and "..." not in m.group(3)[1:13]:
            _, a, code, src = dbg.lst_fields(m)
            text = re.sub(r"^\s*[\w.]+:", "", src.split(";")[0]).strip().lower()
            if code and text == f"call {target.lower()}":
                return a
    raise KeyError(target)


def timing(name, targets):
    """Tcl: every call of each target, from the CALL to the instruction after
    it: the registers B, C, D, E at the CALL, the T-state and the answer (F)"""
    out = ""
    for t in targets:
        at = call_site(name, t)
        out += (f'debug set_bp {at} {{}} {{ set ::t_{t} [machine_info time]; '
                f'set ::r_{t} "[reg b] [reg c] [reg d] [reg e]" }}\n'
                f'debug set_bp {at + 3} {{}} {{ L "call {t} $::r_{t} '
                f'[format %.17g [expr {{[machine_info time] - $::t_{t}}}]] [reg f]" }}\n')
    return out


def calls(w, target):
    """[(B, C, D, E, T, F)] of every logged call of TARGET"""
    return [tuple(int(v) for v in x[2:6]) + (t_state(x[6]), int(x[7])) for x in w
            if x[0] == "call" and x[1] == target]


def walker(name, setup_to=None):
    wk = walk.Walk(HERE / name)
    if setup_to:
        wk.run("init", setup_to)
    return wk


def walk_call(wk, target, b, c, d=0, e=0):
    wk.r.update(a=0, f=0, h=0, l=0)
    t = wk.call(target, b=b, c=c, d=d, e=e)
    return t, wk.r["f"]


# ---------------------------------------------------------------- screens
def codes(png):
    im = Image.open(png).convert("RGB")
    px = im.load()
    return [[CODE.get(px[x, y]) for x in range(im.width)] for y in range(im.height)]


def mismatch(model, photo):
    return sum(1 for y in range(meas.CAPTURE_H) for x in range(meas.DRAWN[0], meas.DRAWN[1] + 1)
               if model[y][x] != photo[y][x])


def capture_of(paper, border):
    return [[(paper[y - meas.PAPER_Y0][x - meas.PAPER_X0]
              if 0 <= x - meas.PAPER_X0 < 256 and 0 <= y - meas.PAPER_Y0 < 192 else border)
             if meas.DRAWN[0] <= x <= meas.DRAWN[1] else None
             for x in range(meas.CAPTURE_W)] for y in range(meas.CAPTURE_H)]


def photo_checked(name, machine, frame, more=None):
    """a photo at FRAME, against the picture vdpscreen draws from the VRAM
    and the registers the debugger read at that frame; MORE, a dict, gets
    the VRAM, the registers and the program's ticks at that frame"""
    w = run(name, machine, frame + 1, events={frame: f"V at; M t {sym(name)['ticks']} 2"})
    vram, regs = logged(w, "at", "vram"), logged(w, "at", "regs")
    if more is not None:
        t = logged(w, "t", "mem")
        more.update(vram=vram, regs=regs, ticks=t[0] | t[1] << 8)
    png = msxcap.capture(rom(name), [frame], CAPS, f"{name}_{TAG[machine]}_f", machine=machine,
                         timeout=900)[frame]
    bad = mismatch(capture_of(vdpscreen.draw(bytearray(vram), regs), regs[7] & 15), codes(png))
    assert bad == 0, (name, machine, frame, bad)
    return png.name


# ---------------------------------------------------------------- walls
def ball_pixels(x, y):
    """the screen pixels of a ball whose attributes are X, Y"""
    return {(x + c, y + 1 + r) for r in range(16) for c in range(16) if BALL[r] & 0x8000 >> c}


def wall_pixels():
    """every pixel of the cells that are walls"""
    return {(8 * c + i, 8 * r + j) for c, r in gen39.ROOM for i in range(8) for j in range(8)}


def path(variant, frames):
    """each ball's place after each frame of the model"""
    return [gen39.walk_balls(variant, k) for k in range(frames + 1)]


def walls():
    out = {}
    walls_px = wall_pixels()
    s = sym("walls")
    for v in gen39.WALL_VARIANTS:
        model = gen39.walk_balls(v)
        res = {}
        for m in MACHINES:
            w = run(v, m, gen39.WALL_FRAMES + 1, at_init=timing(v, ["walled"]),
                    events={gen39.WALL_FRAMES: f"M balls {s['balls']} 24"})
            mem = logged(w, "balls", "mem")
            got = [(mem[6 * i], mem[6 * i + 1], mem[6 * i + 5] or None) for i in range(4)]
            assert got == model, (v, m, got, model)
            cl = calls(w, "walled")
            if m == EU:
                wk = walker(v, "main")
                for b, c, d, e, t, f in cl:
                    tw, fw = walk_call(wk, "walled", b, c)
                    assert (tw, fw & 0x40) == (t, f & 0x40), (v, b, c, t, tw)
                res["walk_checked"] = len(cl)
            res[TAG[m]] = {"calls": len(cl)}
        # the balls' pixels on the walls' cells, frame by frame
        p = path(v, gen39.WALL_FRAMES)
        on = [[len(ball_pixels(x, y) & walls_px) for x, y, _ in frame] for frame in p]
        res["stops"] = [{"place": [x, y], "frame": f} for x, y, f in model]
        res["frames_on_wall"] = [sum(1 for fr in on if fr[i]) for i in range(4)]
        res["most_on_wall"] = [max(fr[i] for fr in on) for i in range(4)]
        # the box's edge against the wall: lines or columns between them
        res["box_gap"] = box_gaps(model)
        out[v] = res
    shot = {}
    out["photos"] = {"walls": photo_checked("walls", EU, gen39.WALL_FRAMES),
                     "corners": photo_checked("corners", EU, CORNERS_SHOT, shot)}
    # the first ball in the photo: sprite 0 of the attribute table in the VRAM
    att = (shot["regs"][5] & 0x7F) * 0x80
    y, x = shot["vram"][att], shot["vram"][att + 1]
    # the program's frame whose places the photo shows: ticks is counted at
    # the interrupt that sends them, one frame after they were worked out
    k = shot["ticks"] - 1
    assert gen39.walk_balls("corners", k)[0][:2] == (x, y), (x, y, k)
    out["corners_shot"] = {"place": [x, y], "ticks": shot["ticks"], "program_frame": k,
                           "on_post": len(ball_pixels(x, y) & post_pixels())}
    out["walls_px"] = len(walls_px)
    return out


def post_pixels():
    c, r = gen39.POST
    return {(8 * c + i, 8 * r + j) for i in range(8) for j in range(8)}


def box_gaps(model):
    """for each ball where it stopped: the pixels of paper between its box
    (16 x 16 from X, Y + 1) and the wall it walked to"""
    names = gen39.room_names()

    def wall(x, y):
        return 0 <= x < 256 and 0 <= y < 192 and names[32 * (y // 8) + x // 8]
    out = []
    for (x, y, _), (_, _, sx, sy) in zip(model, gen39.BALLS):
        top, gap = y + 1, 0
        # the box's own lines or columns on a wall, from its leading edge in:
        # a negative gap
        inside = 0
        while True:
            if sx > 0:
                edge = [(x + 15 - inside, top + r) for r in range(16)]
            elif sx < 0:
                edge = [(x + inside, top + r) for r in range(16)]
            elif sy > 0:
                edge = [(x + c, top + 15 - inside) for c in range(16)]
            else:
                edge = [(x + c, top + inside) for c in range(16)]
            if not any(wall(*e) for e in edge):
                break
            inside += 1
        if inside:
            out.append(-inside)
            continue
        while True:
            if sx > 0:
                edge = [(x + 16 + gap, top + r) for r in range(16)]
            elif sx < 0:
                edge = [(x - 1 - gap, top + r) for r in range(16)]
            elif sy > 0:
                edge = [(x + c, top + 16 + gap) for c in range(16)]
            else:
                edge = [(x + c, top - 1 - gap) for c in range(16)]
            if any(wall(*e) for e in edge):
                break
            gap += 1
        out.append(gap)
    return out


# ---------------------------------------------------------------- flags
def scene_vram(sprites):
    v = bytearray(16384)
    v[0x3800:0x3800 + len(gen39.PATTERNS)] = bytes(gen39.PATTERNS)
    flat = [b for e in sprites for b in e] + [gen39.END]
    v[0x1B00:0x1B00 + len(flat)] = bytes(flat)
    return v


def flags():
    s = sym("flags")
    n = len(gen39.SCENES)
    frames = 4 + gen39.FLAG_REPEAT * n
    model = [vdpscreen.coincidence(scene_vram(sp), REGS) for _, sp in gen39.SCENES]
    out = {"scenes": [what for what, _ in gen39.SCENES],
           "model_c": [c for c, _ in model], "model_line": [ln for _, ln in model]}
    for m in MACHINES:
        w = run("flags", m, frames + 1, events={frames: f"M log {s['log']} {n}"})
        log = logged(w, "log", "mem")
        assert [bool(b & 0x20) for b in log] == [bool(c) for c, _ in model], (m, log.hex())
        out[TAG[m]] = [f"{b:02X}" for b in log]
    return out


# ---------------------------------------------------------------- shapes
SHAPES_FRAMES = 2 * gen39.SIDE ** 2 + 120


def shapes_model():
    r = gen39.REACH
    places = [(dx, dy) for dy in range(-r, r + 1) for dx in range(-r, r + 1)]
    box = [abs(dx) < 16 and abs(dy) < 16 for dx, dy in places]
    pix = [gen39.pixels_meet(BALL, BALL, dx, dy) for dx, dy in places]
    vc = []
    for dx, dy in places:
        sp = [gen39.sprite(gen39.AX, gen39.AY), gen39.sprite(gen39.AX + dx, gen39.AY + dy)]
        vc.append(bool(vdpscreen.coincidence(scene_vram(sp), REGS)[0]))
    return places, box, pix, vc


def shapes():
    places, box, pix, vc = shapes_model()
    assert vc == pix            # rule 12 and the pixels of the two shapes say the same
    n = len(places)
    out = {"places": n, "box": sum(box), "pixels": sum(pix),
           "box_not_pixels": sum(1 for b, p in zip(box, pix) if b and not p)}
    for m in MACHINES:
        w = run("shapes", m, SHAPES_FRAMES + 1,
                at_init=timing("shapes", ["boxed", "touched"]) if m == EU else "",
                events={SHAPES_FRAMES: f"M mc {gen39.MAP_C} {n}; M mt {gen39.MAP_T} {n}"})
        mc, mt = logged(w, "mc", "mem"), logged(w, "mt", "mem")
        assert [v == 0x20 for v in mc] == pix and set(mc) <= {0, 0x20}, m
        assert [v >= 1 for v in mt] == box and [v == 2 for v in mt] == pix, m
        out[TAG[m]] = {"c": sum(v == 0x20 for v in mc), "boxed": sum(v >= 1 for v in mt),
                       "touched": sum(v == 2 for v in mt)}
        if m == EU:
            out["timed"] = timed_tests(w, "shapes")
    out["photo"] = photo_checked("shapes", EU, SHAPES_FRAMES)
    # the false hits of smaller boxes, counted on the map
    out["smaller_boxes"] = {}
    for size in (16, 15, 14, 13, 12, 11, 10):
        says = [abs(dx) < size and abs(dy) < size for dx, dy in places]
        out["smaller_boxes"][str(size)] = {
            "says": sum(says), "false": sum(1 for s, p in zip(says, pix) if s and not p),
            "missed": sum(1 for s, p in zip(says, pix) if p and not s)}
    return out


def timed_tests(w, name):
    """every call of boxed and touched, against walk.py: T-states and answer"""
    wk = walker(name)
    res = {}
    for t, flag in (("boxed", 0x01), ("touched", 0x40)):
        cl = calls(w, t)
        ts = []
        for b, c, d, e, tt, f in cl:
            tw, fw = walk_call(wk, t, b, c, d, e)
            assert (tw, fw & flag) == (tt, f & flag), (name, t, b, c, d, e, tt, tw)
            ts.append(tt)
        yes = [tt for (_, _, _, _, tt, f) in cl if (f & flag) == (0x01 if t == "boxed" else 0)]
        no = [tt for (_, _, _, _, tt, f) in cl if (f & flag) != (0x01 if t == "boxed" else 0)]
        res[t] = {"calls": len(cl), "hit": [min(yes), max(yes)] if yes else None,
                  "miss": [min(no), max(no)] if no else None}
    return res


# ---------------------------------------------------------------- the pairs
def pairs():
    out = {}
    s = sym("meet")
    for name in ("meet", "blame"):
        hist, stopped = gen39.pairs_model(name, PAIR_SHOT, gen39.pictures_c)
        res = {}
        for m in MACHINES:
            tcl = ('set ::runs 0\n'
                   f'debug set_bp {s["tests"]} {{}} {{ incr ::runs; set ::t0 [machine_info time] }}\n' +
                   (timing(name, ["boxed", "touched"] if name == "meet" else ["boxed"]) if m == EU else ""))
            # the frames the tests ran, and how long they took
            at = call_site(name, "move")
            tcl += (f'debug set_bp {at} {{}} {{ if {{[info exists ::t0]}} {{ L "tests '
                    f'[format %.17g [expr {{[machine_info time] - $::t0}}]] [debug read memory {s["ticks"]}]"; unset ::t0 }} }}\n')
            w = run(name, m, PAIR_SHOT + 1, at_init=tcl,
                    events={PAIR_SHOT: f"M pairs {s['pairs']} 20"})
            mem = logged(w, "pairs", "mem")
            got = [(mem[10 * i], mem[10 * i + 1], mem[10 * i + 2], mem[10 * i + 3]) for i in range(2)]
            frames = [mem[10 * i + 9] or None for i in range(2)]
            assert got == hist[PAIR_SHOT] and frames == stopped, (name, m, got, hist[PAIR_SHOT], frames, stopped)
            runs = [(int(x[2]), t_state(x[1])) for x in w if x[0] == "tests"]
            res[TAG[m]] = {"tested_frames": [r[0] for r in runs], "tests_T": [r[1] for r in runs]}
            if m == EU:
                res["timed"] = timed_tests(w, name) if name == "meet" else None
        res["stopped"] = stopped
        res["places"] = [list(p) for p in hist[PAIR_SHOT]]
        res["photo"] = photo_checked(name, EU, PAIR_SHOT)
        # the first picture in which each pair's pixels met, by the model
        first = []
        for i in range(2):
            k = next((k for k, h in enumerate(hist) if pair_touch(h[i])), None)
            first.append(k)
        res["first_touch"] = first
        res["apart_at_stop"] = [[h[2] - h[0], h[3] - h[1]] for h in hist[PAIR_SHOT]]
        out[name] = res
    return out


def pair_touch(p):
    dx, dy = p[2] - p[0], p[3] - p[1]
    return abs(dx) < 16 and abs(dy) < 16 and gen39.pixels_meet(BALL, BALL, dx, dy)


# ---------------------------------------------------------------- prices
def prices():
    m = json.loads((HERE / "meas39.json").read_text())
    wk = walker("walls", "main")
    out = {"walled": {}}
    for label, (x, y) in {"4 cells": (96, 79), "6 cells": (100, 79), "6 cells, rows": (96, 83),
                          "9 cells": (100, 83), "wall at the first cell": (200, 7)}.items():
        t, f = walk_call(wk, "walled", x, y)
        out["walled"][label] = {"T": t, "wall": not f & 0x40}
    wc = walker("corners", "main")
    out["corners"] = {}
    for label, (x, y) in {"no wall": (100, 83), "wall at the first corner": (200, 7)}.items():
        t, f = walk_call(wc, "walled", x, y)
        out["corners"][label] = {"T": t, "wall": not f & 0x40}
    out["boxed"] = m["shapes"]["timed"]["boxed"]
    out["touched"] = m["shapes"]["timed"]["touched"]
    wt = walker("shapes")
    # main's test of C, the status without it: LD A,(stat), AND, CALL NZ not taken
    wm = walker("meet", "main")
    wm.poke(sym("meet")["stat"], 0)
    wm.pc = wm.sym["main"] + 1
    t0, stop = wm.t, call_site("meet", "move")
    assert wm.sym["main"] < stop < wm.sym["main"] + 12
    while wm.pc != stop:
        wm.step()
    out["c_test"] = wm.t - t0
    out["touched_cases"] = {}
    for label, (dx, dy) in {"same place": (0, 0), "level, 13 apart": (13, 0), "level, 14 apart": (14, 0),
                            "diagonal, 9": (9, 9), "diagonal, 10": (10, 10), "15 and 15": (15, 15)}.items():
        t, f = walk_call(wt, "touched", gen39.AX, gen39.AY - 1, gen39.AX + dx, gen39.AY - 1 + dy)
        out["touched_cases"][label] = {"T": t, "touch": not f & 0x40}
    return out


# ---------------------------------------------------------------- answers
def spans(values):
    """[[first, last]] of the runs of consecutive integers in VALUES"""
    out = []
    for v in sorted(values):
        if out and v == out[-1][1] + 1:
            out[-1][1] = v
        else:
            out.append([v, v])
    return out


def answers():
    m = json.loads((HERE / "meas39.json").read_text())
    wl, fl, sh, pr, pa = (m[k] for k in ("walls", "flags", "shapes", "prices", "pairs"))
    out = {}
    cells = sorted(gen39.cells_under(100, 83))
    out["q1"] = {"cells": len(cells), "columns": sorted({c for c, _ in cells}),
                 "rows": sorted({r for _, r in cells}), "T": pr["walled"]["9 cells"]["T"]}
    # the first ball at other Y: where walls.asm and corners.asm stop it at the post
    save, at_post = gen39.BALLS, {"walls": [], "corners": []}
    for y in range(16, 80):
        gen39.BALLS = [(save[0][0], y, 1, 0)] + save[1:]
        for v in at_post:
            if gen39.walk_balls(v)[0][0] == wl["walls"]["stops"][0]["place"][0]:
                at_post[v].append(y)
    gen39.BALLS = save
    out["q2"] = {"frames_on_post": wl["corners"]["frames_on_wall"][0],
                 "corner_rows": sorted({(44 + d) // 8 for d in (0, 15)}), "post_row": gen39.POST[1],
                 "walls_find_post_at_y": spans(at_post["walls"]),
                 "corners_find_post_at_y": spans(at_post["corners"])}
    down = wl["ytop"]["stops"][2]["place"][1]
    out["q3"] = {"stop": wl["ytop"]["stops"][2], "box_gap": wl["ytop"]["box_gap"][2],
                 "pixels_on_wall": wl["ytop"]["most_on_wall"][2], "box_last_line": down + 16,
                 "wall_first_line": 8 * max(r for _, r in gen39.ROOM)}
    assert out["q3"]["box_last_line"] == out["q3"]["wall_first_line"]
    wk = walker("shapes")
    t, f = walk_call(wk, "boxed", 250, 87, 2, 87)
    out["q4"] = {"carry": bool(f & 1), "T": t, "difference": (2 - 250) & 255}
    c_of = dict(zip(fl["scenes"], fl["model_c"]))
    out["q5"] = {"with_c": [w for w, c in c_of.items() if c],
                 "without": [w for w, c in c_of.items() if not c],
                 "colour 0": c_of["one colour 0"], "below": c_of["below the paper"],
                 "after the end": c_of["after the end"]}
    out["q6"] = {"eu": pa["meet"]["eu"]["tested_frames"][0], "jp": pa["meet"]["jp"]["tested_frames"][0],
                 "first_touch": pa["meet"]["first_touch"], "stopped": pa["meet"]["stopped"]}
    out["q7"] = pr["touched_cases"]
    lo, hi = pr["boxed"]["miss"][0], pr["boxed"]["hit"][1]
    out["q8"] = {"pairs": 28, "least": 28 * lo, "most": 28 * hi}
    # blame.asm with the diagonal pair started nearer or further apart, the
    # same distance each way: where boxed stopped it, and whether its balls touch
    start = gen39.PAIRS[0][1][0] - gen39.PAIRS[0][0][0]
    runs = []
    for extra in range(-45, 4):
        save = gen39.PAIRS
        (a_, b_) = save[0]
        gen39.PAIRS = [(a_, (b_[0] + extra, b_[1] + extra, b_[2], b_[3])), save[1]]
        hist, stopped = gen39.pairs_model("blame", 60, gen39.pictures_c)
        gen39.PAIRS = save
        h = hist[-1][0]
        runs.append({"extra": extra, "start": start + extra, "stopped": stopped[0],
                     "apart": [h[2] - h[0], h[3] - h[1]], "touch": bool(pair_touch(h))})
    touching = [r["start"] for r in runs if r["touch"]]
    assert touching == list(range(min(touching), max(touching) + 1))
    out["q9"] = {"start": start, "further": [r for r in runs if r["extra"] > 0],
                 "nearer": [r for r in runs if -9 <= r["extra"] < 0],
                 "touching_starts": [min(touching), max(touching)]}
    sb = sh["smaller_boxes"]
    clean = min((int(k) for k, v in sb.items() if v["false"] == 0), key=lambda k: -k)
    # a box of the ball's own size: where its false hits are on the map
    places, _, pix, _ = shapes_model()
    false14 = [(dx, dy) for (dx, dy), p in zip(places, pix) if abs(dx) < 14 and abs(dy) < 14 and not p]
    out["q10"] = {"size": 14, "false": len(false14), "says": sb["14"]["says"],
                  "on_the_axes": sum(1 for dx, dy in false14 if dx == 0 or dy == 0),
                  "least_off_axis": min(min(abs(dx), abs(dy)) for dx, dy in false14),
                  "largest_without_false": clean, "missed": sb[str(clean)]["missed"],
                  "pixels": sh["pixels"]}
    assert out["q10"]["false"] == sb["14"]["false"]
    return out


OPENMSX_SECTIONS = ["walls", "flags", "shapes", "pairs"]


def openmsx():
    if not versions.builds():
        return {"skipped": "OPENMSX_BUILDS not set"}
    return versions.every_build(["ch39"], OPENMSX_SECTIONS)


SECTIONS = {"walls": walls, "flags": flags, "shapes": shapes, "pairs": pairs, "prices": prices,
            "answers": answers, "openmsx": openmsx}


def main(names=()):
    CAPS.mkdir(exist_ok=True)
    path_ = HERE / "meas39.json"
    m = json.loads(path_.read_text()) if names and path_.exists() else {}
    for name in names or SECTIONS:
        print(name, flush=True)
        m[name] = SECTIONS[name]()
        m = {k: m[k] for k in SECTIONS if k in m}
        path_.write_text(json.dumps(m, indent=1) + "\n")
    return m


if __name__ == "__main__":
    main(sys.argv[1:])
