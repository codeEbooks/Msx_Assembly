#!/usr/bin/env python3
"""meas28.py -- software sprites in the tiles, measured.

    python3 gen28.py && ./build.sh && python3 meas28.py
                                  python3 meas28.py shifts walk     only these

Every photograph, on both machines, must be vdpscreen.py's drawing of the
VRAM and the registers the debugger reads for its frame. Every VRAM the
programs leave must be gen28.py's model of it, vram_of(), byte for byte: the
names, and each bug's four patterns and their colours. And every photograph
is held against the IDEAL: the tiles with each bug drawn over them pixel by
pixel, black where the bug is, the tile's paper where its mask clears; what
differs is counted.

  shifts    shifts.rom: eight bugs at every shift; the copies in the RAM
            (figure 28.1)
  cost      cost.rom: preshift, build and sbuild at the eight shifts, timed
            by the debugger, against walk.py
  edge      edge.rom: a bug at the right edge (figure 28.2)
  colours   under.rom and paint.rom: four bugs on four kinds of tile
            (figure 28.3)
  walk      walk.rom: a film of a bug across the screen (figure 28.4)
  swarm     swarm.rom: six bugs on the same lines (figure 28.5)
  cross     WHERE IT BREAKS: overlap.rom and stack.rom (figure 28.6)
  prices    walk.py's T-states for send and step, against the debugger's
  answers   the workshop, tried (for Appendix I)
  openmsx   all of it again with every other build (tools/versions.py)
"""
import json
import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "ch20"))
import meas        # noqa: E402
import msxcap      # noqa: E402
import probe as dbg  # noqa: E402
import versions    # noqa: E402
import vdpslots    # noqa: E402  (chapter 20)
sys.path.insert(0, str(HERE))
import gen28       # noqa: E402
sys.path.remove(str(HERE))
sys.path.insert(0, str(HERE))      # gen28 put chapters 24 and 26 first: this folder's files win
for mod in ("vdpscreen", "walk"):
    sys.modules.pop(mod, None)
import vdpscreen   # noqa: E402
import walk        # noqa: E402  (chapter 25's, with IX)

assert Path(vdpscreen.__file__).parent == HERE and Path(walk.__file__).parent == HERE

CAPS = HERE / "captures"
EU, JP = "MSXBOOK_EU16", "MSXBOOK_JP16"
TAG = {EU: "eu", JP: "jp"}
CLOCK = 3579545
POS = "[machine_info VDP_frame_count] [machine_info VDP_cycle_in_frame] [machine_info time]"
REGS = " ".join(f"[debug read {{VDP regs}} {i}]" for i in range(8))
VRAM = 'binary scan [debug read_block {VRAM} 0 16384] H* h; L "vram $h"'
TABLES = ('binary scan [debug read_block {VRAM} 6144 768] H* n; '
          'binary scan [debug read_block {VRAM} 1024 1024] H* p; '
          'binary scan [debug read_block {VRAM} 9216 1024] H* c; '
          f'L "tables {REGS} $n $p $c"')
F0 = 'L "f0 [machine_info VDP_frame_count]"\n'
TOO_FAST = ('proc ::toofast_cb {args} { L "fast [machine_info time]" }\n'
            'set VDP.too_fast_vram_access_callback ::toofast_cb\n')
BLACK = gen28.BLACK
REGS_TILES = [2, 0xC0, 6, 0x9F, 0, 0x36, 7, 0x0F]

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


def against(model, photo, backdrop):
    bad = 0
    for y in range(240):
        for x in range(meas.DRAWN[0], meas.DRAWN[1] + 1):
            px, py = x - meas.PAPER_X0, y - meas.PAPER_Y0
            want = model[py][px] if 0 <= px < 256 and 0 <= py < 192 else backdrop
            bad += photo[y][x] != want
    return bad


def once(addr, body, tag):
    return f'set ::{tag} [debug set_bp {addr} {{}} {{ {body}; debug remove_bp $::{tag} }}]\n'


def run(name, frames, tcl, machine):
    lines = msxcap.run_tcl(rom(name), frames, F0 + TOO_FAST + tcl, machine=machine)
    w = [l.split() for l in lines]
    assert not [x for x in w if x[0] == "fast"], (name, machine, "an access too soon")
    return w


def spans(nbugs):
    """what the programs write: the tiles' shapes and colours, the bugs', the
    names, and the end of the sprites"""
    t, b = 8 * len(gen28.TILES), 8 * gen28.FIRST
    return [(0, t), (b, b + 32 * nbugs), (0x1800, 0x1B01), (0x2000, 0x2000 + t),
            (0x2000 + b, 0x2000 + b + 32 * nbugs)]


def tables_differ(vram, want, nbugs):
    """bytes of the shapes, the names and the colours that are not the model's"""
    return sum(1 for a, b in spans(nbugs) for i in range(a, b) if vram[i] != want[i])


# ---------------------------------------------------------------- the ideal
def ideal(bugs):
    """the tiles, and each bug in turn drawn over them: black where the bug
    is, the paper of the tile's row where only its mask is"""
    pic = vdpscreen.draw(gen28.vram_of([]), REGS_TILES)
    for x, y in bugs:
        for j in range(8):
            for i in range(8):
                px, py = x + i, y + j
                bit = 0x80 >> i
                if px > 255:
                    continue                    # past the right edge: not on the screen
                if gen28.BUG[j] & bit:
                    pic[py][px] = BLACK
                elif not gen28.MASK[j] & bit:
                    n = gen28.NAMES[32 * (py // 8) + px // 8]
                    pic[py][px] = vdpscreen.colour(gen28.TILES[n][2][py % 8] & 15, REGS_TILES)
    return pic


def paper_of(photo):
    return [[photo[meas.PAPER_Y0 + y][meas.PAPER_X0 + x] for x in range(256)] for y in range(192)]


def off_ideal(photo, bugs):
    """the pixels of the paper that are not the ideal's: the bugs' own
    pixels, the rest of their 8 x 8 boxes, and the rest of their cells"""
    pic, pp = ideal(bugs), paper_of(photo)
    boxes = {(x + i, y + j) for x, y in bugs for i in range(8) for j in range(8)}
    ink = {(x + i, y + j) for x, y in bugs for j in range(8) for i in range(8)
           if gen28.BUG[j] & 0x80 >> i}
    out = {"bug": 0, "mask": 0, "outside": 0}   # bugs past the right edge: see edge()
    for y in range(192):
        for x in range(256):
            if pp[y][x] != pic[y][x]:
                out["bug" if (x, y) in ink else "mask" if (x, y) in boxes else "outside"] += 1
    return out


def off_each(photo, bugs):
    """off_ideal, counted bug by bug over each bug's 2 x 2 cells"""
    pic, pp = ideal(bugs), paper_of(photo)
    out = []
    for x, y in bugs:
        cx, cy = x // 8 * 8, y // 8 * 8
        o = {"bug": 0, "mask": 0, "cells": 0}
        for py in range(cy, cy + 16):
            for px in range(cx, cx + 16):
                if pp[py][px] != pic[py][px]:
                    i, j = px - x, py - y
                    inside = 0 <= i < 8 and 0 <= j < 8
                    o["bug" if inside and gen28.BUG[j] & 0x80 >> i else "mask" if inside else "cells"] += 1
        out.append(o)
    return out


# ---------------------------------------------------------------- a still
def still(name, machine, bugs, paint=False):
    s = sym(name)
    w = run(name, 40, once(s["done"], f'L "regs {REGS}"; {VRAM}; L "done {POS}"', "d"), machine)
    f0 = int(next(x for x in w if x[0] == "f0")[1])
    regs = [int(v) for v in next(x for x in w if x[0] == "regs")[1:]]
    vram = bytes.fromhex(next(x for x in w if x[0] == "vram")[1])
    shot = int(next(x for x in w if x[0] == "done")[1]) - f0 + 2
    png = msxcap.capture(rom(name), [shot], CAPS, f"{name}_{TAG[machine]}_f", machine=machine)[shot]
    photo = codes(png)
    assert regs == REGS_TILES, regs
    assert against(vdpscreen.draw(vram, regs), photo, regs[7] & 15) == 0, (name, machine)
    differ = tables_differ(vram, gen28.vram_of(bugs, paint=paint), len(bugs))
    assert differ == 0, (name, machine, differ)
    return vram, photo, shot


# ---------------------------------------------------------------- shifts
def shifts():
    out = {}
    s = sym("shifts")
    for m in (EU, JP):
        vram, photo, shot = still("shifts", m, gen28.SHIFTS)
        w = run("shifts", 40, once(s["p1"], 'binary scan [debug read_block memory '
                                   f'{gen28.COPIES_RAM} 256] H* h; L "copies $h"', "c"), m)
        copies = list(bytes.fromhex(next(x for x in w if x[0] == "copies")[1]))
        assert copies == gen28.COPIES, m
        out[TAG[m]] = {"shot": shot, "off_ideal": off_ideal(photo, gen28.SHIFTS),
                       "copies_right": sum(a == b for a, b in zip(copies, gen28.COPIES))}
        assert out[TAG[m]]["off_ideal"] == {"bug": 0, "mask": 0, "outside": 0}, out[TAG[m]]
    return out


# ---------------------------------------------------------------- cost
def cost():
    s = sym("cost")
    labels = ["p0", "p1"] + [f"{a}{k}" for k in range(8) for a in "becd"]
    out = {}
    for m in (EU, JP):
        tcl = "".join(once(s[l], f'L "t {l} [machine_info time]"', f"t{l}") for l in labels)
        w = run("cost", 30, tcl, m)
        t = {x[1]: float(x[2]) for x in w if x[0] == "t"}
        pre = round((t["p1"] - t["p0"]) * CLOCK)
        bld = [round((t[f"e{k}"] - t[f"b{k}"]) * CLOCK) for k in range(8)]
        sbl = [round((t[f"d{k}"] - t[f"c{k}"]) * CLOCK) for k in range(8)]
        out[TAG[m]] = {"preshift": pre, "build": bld, "sbuild": sbl}
    wk = walk.Walk(HERE / "cost")
    wk.run("init", "p0")
    pw = wk.run("p0", "p1")
    prev, bw, sw = "p1", [], []
    for k in range(8):
        wk.run(prev, f"b{k}")
        bw.append(wk.run(f"b{k}", f"e{k}"))
        wk.run(f"e{k}", f"c{k}")
        sw.append(wk.run(f"c{k}", f"d{k}"))
        prev = f"d{k}"
    out["walk"] = {"preshift": pw, "build": bw, "sbuild": sw}
    for tg in ("eu", "jp"):
        assert out[tg] == out["walk"], (tg, out[tg], out["walk"])
    return out


# ---------------------------------------------------------------- edge
def edge():
    """the bug at the right edge: where the pixels past column 255 went"""
    out = {}
    (x, y), = gen28.EDGE
    past = [(x + i, y + j) for j in range(8) for i in range(8)
            if x + i > 255 and gen28.BUG[j] & 0x80 >> i]
    for m in (EU, JP):
        vram, photo, shot = still("edge", m, gen28.EDGE)
        pp = paper_of(photo)
        moved = [(px - 256, py + 8) for px, py in past]
        found = sum(1 for px, py in moved if pp[py][px] == BLACK)
        out[TAG[m]] = {"shot": shot, "past": len(past), "found": found,
                       "at": [min(p[0] for p in moved), max(p[0] for p in moved),
                              min(p[1] for p in moved), max(p[1] for p in moved)],
                       "off_ideal": off_ideal(photo, gen28.EDGE)}
        assert found == len(past), out[TAG[m]]
    return out


# ---------------------------------------------------------------- colours
def colours():
    out = {}
    for name in ("under", "paint"):
        for m in (EU, JP):
            vram, photo, shot = still(name, m, gen28.COLOURS, paint=name == "paint")
            per = off_each(photo, gen28.COLOURS)
            out.setdefault(name, {})[TAG[m]] = {"shot": shot, "per_bug": per,
                                                "all": off_ideal(photo, gen28.COLOURS)}
    return out


# ---------------------------------------------------------------- films
def film(name, machine, frames, path, stacked=False):
    """every send, m0 to m1, and every step, m1 to s1: frame and T-states; the
    tables the send left, read when the next send begins or at done; and the
    photograph of each, the frame after the send's"""
    s = sym(name)
    tcl = (f'debug set_bp {s["m0"]} {{}} {{ {TABLES}; L "a {POS}" }}\n'
           f'debug set_bp {s["m1"]} {{}} {{ L "b {POS}" }}\n'
           f'debug set_bp {s["s1"]} {{}} {{ L "c {POS}" }}\n' +
           once(s["m0"], VRAM, "v") +
           once(s["done"], f'{TABLES}; L "end"', "e"))
    w = run(name, frames + 40, tcl, machine)
    f0 = int(next(x for x in w if x[0] == "f0")[1])
    base = bytearray(bytes.fromhex(next(x for x in w if x[0] == "vram")[1]))
    a_s = [x for x in w if x[0] == "a"]
    b_s = [x for x in w if x[0] == "b"]
    c_s = [x for x in w if x[0] == "c"]
    tables = [x for x in w if x[0] == "tables"][1:]
    assert len(a_s) == len(b_s) == len(c_s) == len(tables) == len(path), (name, len(a_s), len(tables))
    states = []
    for t in tables:
        r = [int(x) for x in t[1:9]]
        v = bytearray(base)
        v[0x1800:0x1B00] = bytes.fromhex(t[9])
        v[0x0400:0x0800] = bytes.fromhex(t[10])
        v[0x2400:0x2800] = bytes.fromhex(t[11])
        states.append((r, bytes(v)))
    bad_tables = [tables_differ(v, gen28.vram_of(bugs, stacked), len(bugs)) for (_, v), bugs in zip(states, path)]
    assert not any(bad_tables), (name, machine, bad_tables[:8])
    frames_at = [int(a[1]) - f0 for a in a_s]
    send = [round((float(b[3]) - float(a[3])) * CLOCK) for a, b in zip(a_s, b_s)]
    step = [round((float(c[3]) - float(b[3])) * CLOCK) for b, c in zip(b_s, c_s)]
    shots = sorted({f + d for f in frames_at for d in (0, 1, 2)})
    pngs = msxcap.capture(rom(name), shots, CAPS, f"{name}_{TAG[machine]}_f", machine=machine)
    photos = {f: codes(pngs[f]) for f in shots}
    fits = [d for d in (0, 1, 2)
            if all(against(vdpscreen.draw(v, r), photos[f + d], r[7] & 15) == 0
                   for (r, v), f in zip(states, frames_at))]
    assert 1 in fits, (name, machine, fits)
    keep = {f + 1 for f in frames_at}
    for f in shots:
        if f not in keep:
            pngs[f].unlink()
    lines = [int(a[2]) // vdpslots.LINE for a in a_s]
    ends = [int(b[2]) // vdpslots.LINE + (int(b[1]) - int(a[1])) * vdpslots.LINES[machine]
            for a, b in zip(a_s, b_s)]
    return ({"frames": [f + 1 for f in frames_at], "fits": fits, "send": sorted(set(send)),
             "step": sorted(set(step)), "steps": step, "lines": sorted(set(lines)),
             "ends": [min(ends), max(ends)]},
            [photos[f + 1] for f in frames_at])


def walk_film():
    out = {}
    path = gen28.walk_path()
    for m in (EU, JP):
        res, photos = film("walk", m, gen28.WALK_FRAMES, path)
        offs = [off_ideal(ph, bugs) for ph, bugs in zip(photos, path)]
        res["off_ideal"] = offs
        out[TAG[m]] = res
    return out


def swarm_film():
    out = {}
    path = gen28.swarm_path()
    for m in (EU, JP):
        res, photos = film("swarm", m, gen28.SWARM_FRAMES, path)
        res["off_ideal"] = [off_ideal(ph, bugs) for ph, bugs in zip(photos, path)]
        assert all(o == {"bug": 0, "mask": 0, "outside": 0} for o in res["off_ideal"])
        res["off_ideal"] = "none"
        out[TAG[m]] = res
    return out


def cross():
    out = {}
    path = gen28.cross_path()
    for name, stacked in (("overlap", False), ("stack", True)):
        for m in (EU, JP):
            res, photos = film(name, m, gen28.CROSS_FRAMES, path, stacked)
            offs = [off_ideal(ph, bugs) for ph, bugs in zip(photos, path)]
            res["off_ideal"] = offs
            shared = [k for k, bugs in enumerate(path)
                      if abs(bugs[0][0] // 8 - bugs[1][0] // 8) <= 1]
            res["shared"] = [shared[0], shared[-1]] if shared else []
            out.setdefault(name, {})[TAG[m]] = res
    return out


# ---------------------------------------------------------------- prices
def prices():
    m = json.loads((HERE / "meas28.json").read_text())
    out = {}
    for name in ("walk", "swarm", "overlap", "stack"):
        wk = walk.Walk(HERE / name, read_port=lambda port, t: 0x80 if port == 0x99 else 0)
        wk.run("init", "m0")
        sends, steps = set(), set()
        for _ in range(3):
            sends.add(wk.run("m0", "m1"))
            steps.add(wk.run("m1", "s1"))
            wk.run("s1", "m0")
        out[name] = {"send": sorted(sends), "step": sorted(steps)}
    # the pieces, each called once, on walk.rom's bug where it starts
    wk = walk.Walk(HERE / "walk", read_port=lambda port, t: 0x80 if port == 0x99 else 0)
    wk.run("init", "m0")
    sy = wk.sym
    wk.ix = sy["bugs"]
    pieces = {n: wk.call(n) for n in ("build", "cells", "where", "buffer", "look", "place",
                                      "mark", "unmark")}
    pieces["tile"] = wk.call("tile", a=1)
    pieces["cell"] = wk.call("cell", a=1, d=gen28.PATS_RAM >> 8, e=0)
    pieces["column"] = wk.call("column", b=8, d=gen28.COPIES_RAM >> 8, e=0,
                               h=gen28.PATS_RAM >> 8, l=0)
    pieces["two"] = wk.call("two", h=0, l=70, d=sy["names"] >> 8, e=sy["names"] & 255)
    out["pieces"] = pieces
    for t in ("eu", "jp"):
        for name in ("walk", "swarm"):
            assert out[name] == {"send": m[name][t]["send"], "step": m[name][t]["step"]}, (name, t)
        for name in ("overlap", "stack"):
            assert out[name]["send"] == m["cross"][name][t]["send"]
            assert set(out[name]["step"]) <= set(m["cross"][name][t]["step"])
    return out


# ---------------------------------------------------------------- answers
def answers():
    m = json.loads((HERE / "meas28.json").read_text())
    out = {}
    # 1: ten bugs: their patterns, and what chapter 24's tiles leave of the 256
    out["q1"] = {"bugs": 4 * 10, "with_tiles": len(gen28.TILES) + 4 * 10, "free": 256 - len(gen28.TILES) - 40}
    # 2: a bug of 16 x 16: its cells, and the bytes of a send
    cells = 3 * 3
    out["q2"] = {"cells": cells, "bytes": 8 * cells + 8 * cells + cells + cells}
    # 3: how many bugs a 60 Hz frame's lines not drawn take, at send's price
    one, six = m["walk"]["eu"]["send"][0], m["swarm"]["eu"]["send"][0]
    each = (six - one) // 5
    fixed = one - each
    out["q3"] = {"each": each, "fixed": fixed, "jp": (15960 - fixed) // each, "eu": (27588 - fixed) // each}
    # 4: the eight copies of a bug of 16 x 16 with its mask
    out["q4"] = {"copy": 3 * 16 * 2, "eight": 8 * 3 * 16 * 2}
    # 5: stack.asm's step, dearer in some frames: B's cells named after A's patterns
    path = gen28.cross_path()
    extra = {}
    for t in ("eu", "jp"):
        steps = m["cross"]["stack"][t]["steps"]
        base = min(steps)
        for k, st in enumerate(steps[:-1]):          # step k builds the bugs of send k + 1
            shown, _ = gen28.build_model(path[k + 1][:1], stacked=True)
            h = gen28.where(*path[k + 1][1])
            mine = sum(1 for c in (h, h + 1, h + 32, h + 33) if shown[c] >= gen28.FIRST)
            assert st - base == 5 * mine, (t, k, st, mine)
            extra[st - base] = extra.get(st - base, 0) + (t == "eu")
    out["q5"] = {"base": min(m["cross"]["stack"]["eu"]["steps"]), "extra_frames": extra}
    return out


# ---------------------------------------------------------------- openmsx
OPENMSX_SECTIONS = ["shifts", "cost", "edge", "colours", "walk", "swarm", "cross"]


def openmsx():
    if not versions.builds():
        return {"skipped": "OPENMSX_BUILDS not set"}
    return versions.every_build(["ch28"], OPENMSX_SECTIONS)


SECTIONS = {"shifts": shifts, "cost": cost, "edge": edge, "colours": colours, "walk": walk_film,
            "swarm": swarm_film, "cross": cross, "prices": prices, "answers": answers,
            "openmsx": openmsx}


def main(names=()):
    CAPS.mkdir(exist_ok=True)
    path = HERE / "meas28.json"
    m = json.loads(path.read_text()) if names and path.exists() else {}
    for name in names or SECTIONS:
        print(name, flush=True)
        m[name] = SECTIONS[name]()
        m = {k: m[k] for k in SECTIONS if k in m}
        path.write_text(json.dumps(m, indent=1) + "\n")
    return m


if __name__ == "__main__":
    main(sys.argv[1:])
