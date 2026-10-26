#!/usr/bin/env python3
"""meas26.py -- hardware sprites I, measured.

    python3 gen26.py && ./build.sh && python3 meas26.py
                                  python3 meas26.py one rows    only these

Every photograph, on both machines, must be vdpscreen.py's drawing of the
VRAM and the registers the debugger reads for its frame: rule 9 draws the
sprites. A film is checked frame by frame: the attribute table is read after
each change, and the frame that shows it, 0, 1 or 2 frames on, is fitted
once for the film and must fit every frame. Then the photographs are read
the other way: where each sprite begins and ends, against what this file
expects of Y, X and the early clock.

  one       one.rom: one sprite of 8 x 8; its shape and place off the
            photograph (figure 26.1)
  sizes     sizes.rom: the four sizes of R#1 (figure 26.2)
  rows      rows.rom: Y from 0 to 255: the lines a block of 16 x 16 covers
  columns   columns.rom: X from 0 to 31 with the early clock, then 0 to 255
            (figure 26.3)
  edges     edges.rom: sprites cut by the four edges (figure 26.4)
  clock     clock.rom: the early clock on magnified sprites
  order     order.rom: sprites over sprites and over the picture (figure 26.5)
  modes     modes.rom: the sprites in Graphic II, Graphic I, multicolour, text
            (figure 26.6)
  march     march.rom: R#6 between two pattern tables (figure 26.8)
  tear      tear.rom: a new X written while the beam draws the sprite (figure 26.9)
  herd      herd.rom and flip.rom: 32 sprites moved every frame, from a copy
            sent with OTIR after the paper, or sent during the paper to the
            table not shown and R#5 changed (figure 26.7)
  fall      WHERE IT BREAKS: fall.rom, park.rom and last.rom (figure 26.10)
  prices    walk.py's T-states for the routines, against the debugger's
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
sys.path.insert(0, str(REPO / "ch25"))
sys.path.insert(0, str(HERE))
import meas        # noqa: E402
import msxcap      # noqa: E402
import probe as dbg  # noqa: E402
import versions    # noqa: E402
import vdpslots    # noqa: E402  (chapter 20)
import walk        # noqa: E402  (chapter 25: the listing's T-states)
import gen26       # noqa: E402
import vdpscreen   # noqa: E402  (rule 9: the sprites)

assert Path(vdpscreen.__file__).parent == HERE and Path(walk.__file__).parent == REPO / "ch25"

CAPS = HERE / "captures"
EU, JP = "MSXBOOK_EU16", "MSXBOOK_JP16"
TAG = {EU: "eu", JP: "jp"}
CLOCK = 3579545
POS = "[machine_info VDP_frame_count] [machine_info VDP_cycle_in_frame] [machine_info time]"
REGS = " ".join(f"[debug read {{VDP regs}} {i}]" for i in range(8))
VRAM = 'binary scan [debug read_block {VRAM} 0 16384] H* h; L "vram $h"'
ATTS = ('binary scan [debug read_block {VRAM} 6912 256] H* h; '
        f'L "atts {REGS} $h"')
F0 = 'L "f0 [machine_info VDP_frame_count]"\n'
TOO_FAST = ('proc ::toofast_cb {args} { L "fast [machine_info time]" }\n'
            'set VDP.too_fast_vram_access_callback ::toofast_cb\n')
RECORD = ('set ::on 0\n'
          'debug set_watchpoint write_io {0x98 0x99} {} { if {$::on} { L "w '
          '[machine_info VDP_frame_count] [machine_info VDP_cycle_in_frame] '
          '$::wp_last_address $::wp_last_value" } }\n')
BLACK, LIGHT_GREEN, DARK_BLUE, WHITE = gen26.BLACK, gen26.LIGHT_GREEN, gen26.DARK_BLUE, gen26.WHITE

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
    """pixels of the photograph that are not the model's: the paper, and the
    border inside the columns the VDP draws (chapter 4)"""
    bad = 0
    for y in range(240):
        for x in range(meas.DRAWN[0], meas.DRAWN[1] + 1):
            px, py = x - meas.PAPER_X0, y - meas.PAPER_Y0
            want = model[py][px] if 0 <= px < 256 and 0 <= py < 192 else backdrop
            bad += photo[y][x] != want
    return bad


def paper_px(photo, x, y):
    return photo[meas.PAPER_Y0 + y][meas.PAPER_X0 + x]


def once(addr, body, tag):
    return f'set ::{tag} [debug set_bp {addr} {{}} {{ {body}; debug remove_bp $::{tag} }}]\n'


def run(name, frames, tcl, machine):
    lines = msxcap.run_tcl(rom(name), frames, F0 + TOO_FAST + tcl, machine=machine)
    w = [l.split() for l in lines]
    assert not [x for x in w if x[0] == "fast"], (name, machine, "an access too soon")
    return w


def inked(photo, colour=BLACK):
    """the pixels of the paper in COLOUR"""
    return {(x, y) for y in range(192) for x in range(256) if paper_px(photo, x, y) == colour}


# ---------------------------------------------------------------- a still
def still(name, machine):
    """the registers and the VRAM at done, and the photograph two frames
    later, against the model"""
    s = sym(name)
    w = run(name, 40, once(s["done"], f'L "regs {REGS}"; {VRAM}; L "done {POS}"', "d"), machine)
    f0 = int(next(x for x in w if x[0] == "f0")[1])
    regs = [int(v) for v in next(x for x in w if x[0] == "regs")[1:]]
    vram = bytes.fromhex(next(x for x in w if x[0] == "vram")[1])
    shot = int(next(x for x in w if x[0] == "done")[1]) - f0 + 2
    png = msxcap.capture(rom(name), [shot], CAPS, f"{name}_{TAG[machine]}_f", machine=machine)[shot]
    photo = codes(png)
    assert against(vdpscreen.draw(vram, regs), photo, regs[7] & 15) == 0, (name, machine)
    return regs, vram, photo, shot


def box(pixels):
    xs, ys = [p[0] for p in pixels], [p[1] for p in pixels]
    return [min(xs), min(ys), max(xs), max(ys)] if pixels else None


# ---------------------------------------------------------------- one
def one():
    y, x, p, c = gen26.ONE[0]
    out = {}
    for m in (EU, JP):
        regs, vram, photo, shot = still("one", m)
        ink = inked(photo)
        b = box(ink)
        got = [sum(0x80 >> i for i in range(8) if (b[0] + i, b[1] + r) in ink) for r in range(8)]
        out[TAG[m]] = {"box": b, "pixels": len(ink), "bytes": got, "shot": shot,
                       "attributes": list(vram[gen26.ATT:gen26.ATT + 5]),
                       "pattern": list(vram[gen26.PAT + 8 * p:gen26.PAT + 8 * p + 8])}
        assert b[:2] == [x, y + 1] and got == gen26.ARROW, out[TAG[m]]
    return out


# ---------------------------------------------------------------- films
def film(name, machine, pairs, frames, record=False, held=False):
    """every change of the attribute table, from label A to label B of each
    pair: its frame and T-states, the table and R#1 and R#5 after it; and the
    photograph of each, fitted once"""
    s = sym(name)
    tcl = RECORD if record else ""
    for a, b in pairs:
        tcl += f'debug set_bp {s[a]} {{}} {{ {ATTS}; L "a {POS}"; set ::on {int(record)} }}\n'
        body = f'set ::on 0; L "b {POS}"'
        tcl += (once(s[b], body, f"b_{b}") if s[b] == s["done"] else    # done: jr done
                f'debug set_bp {s[b]} {{}} {{ {body} }}\n')
    tcl += once(s[pairs[0][0]], f'L "regs {REGS}"; {VRAM}', "v")
    tcl += once(s["done"], f'{ATTS}; L "end"', "e")
    w = run(name, frames, tcl, machine)
    f0 = int(next(x for x in w if x[0] == "f0")[1])
    regs = [int(v) for v in next(x for x in w if x[0] == "regs")[1:]]
    base = bytes.fromhex(next(x for x in w if x[0] == "vram")[1])
    a_s = [x for x in w if x[0] == "a"]
    b_s = [x for x in w if x[0] == "b"]
    # the table as each change left it: read when the next change begins, or
    # at done, a byte to $98 reaching the VRAM some T-states after its OUT
    # (chapter 19)
    tables = [x for x in w if x[0] == "atts"][1:]
    assert len(a_s) == len(b_s) == len(tables), (name, len(a_s), len(b_s), len(tables))
    states = []
    for t in tables:
        r = [int(x) for x in t[1:9]]
        v = bytearray(base)
        v[0x1B00:0x1C00] = bytes.fromhex(t[9])
        states.append((r, bytes(v)))
    frames_at = [int(a[1]) - f0 for a in a_s]
    cost = [round((float(b[3]) - float(a[3])) * CLOCK) for a, b in zip(a_s, b_s)]
    lines = [int(a[2]) // vdpslots.LINE for a in a_s]
    films = sorted({f + d for f in frames_at for d in (0, 1, 2)})
    pngs = msxcap.capture(rom(name), films, CAPS, f"{name}_{TAG[machine]}_f", machine=machine)

    def bad(k, d):
        r, v = states[k]
        return against(vdpscreen.draw(v, r), codes(pngs[frames_at[k] + d]), r[7] & 15)
    n = len(states)
    probe_k = sorted({0, n // 2, n - 1})
    fits = [d for d in (0, 1, 2) if all(bad(k, d) == 0 for k in probe_k)]
    if held:                    # each state stays for frames: the first that shows it
        fits = fits[:1]
    assert len(fits) == 1, (name, machine, fits)
    d = fits[0]
    photos = []
    for k in range(n):
        ph = codes(pngs[frames_at[k] + d])
        r, v = states[k]
        assert against(vdpscreen.draw(v, r), ph, r[7] & 15) == 0, (name, machine, k)
        photos.append(ph)
    keep = {f + d for f in frames_at}
    for f in films:
        if f not in keep:
            pngs[f].unlink()
    out = {"frames": [f + d for f in frames_at], "d": d, "cost": cost, "lines": lines,
           "n": n}
    if record:
        out["events"] = [x for x in w if x[0] == "w"]
    return out, states, photos


def lines_of(photo, x0, x1):
    """the lines of the paper with black between columns x0 and x1 - 1"""
    return sorted({y for y in range(192) for x in range(x0, x1) if paper_px(photo, x, y) == BLACK})


def cols_of(photo, y0, y1):
    return sorted({x for x in range(256) for y in range(y0, y1) if paper_px(photo, x, y) == BLACK})


# ---------------------------------------------------------------- sizes
def sizes():
    """each state's sprites read off the photograph, pixel by pixel from (X,
    Y + 1), against the shape the size should draw: digit k at 8 x 8, the
    four digits put together at 16 x 16, every pixel doubled when magnified"""
    out = {}
    for m in (EU, JP):
        res, states, photos = film("sizes", m, [(f"s{k}", f"e{k}") for k in range(4)], 60, held=True)
        per_state = []
        for (r, v), ph in zip(states, photos):
            size, scale = (16 if r[1] & 2 else 8), (2 if r[1] & 1 else 1)
            right, extents = 0, []
            for k, (y, x, p, c) in enumerate(gen26.SIZES):
                rows = (gen26.sprite16("digits") if size == 16 else
                        [d << 8 for d in gen26.DIGITS[k]])
                want = {(x + i, y + 1 + j) for j in range(size * scale) for i in range(size * scale)
                        if rows[j // scale] & 0x8000 >> (i // scale)}
                got = {(px, py) for py in range(y + 1, y + 1 + size * scale)
                       for px in range(x, x + size * scale) if paper_px(ph, px, py) == c}
                right += got == want
                extents.append(size * scale)
            per_state.append({"r1": r[1], "right": right, "pixels": extents[0]})
            assert right == 4, (m, r[1])
        out[TAG[m]] = {"states": per_state, "frames": res["frames"]}
    return out


# ---------------------------------------------------------------- rows
def expect_lines(y, size=16):
    return sorted({(y + 1 + r) & 0xFF for r in range(size)} & set(range(192)))


def rows():
    out = {}
    for m in (EU, JP):
        res, states, photos = film("rows", m, [("m0", "m1")], 300)
        ys = [v[0x1B00] for _, v in states]
        assert ys == list(range(256)), ys[:5]
        seen = [lines_of(ph, gen26.ROWS_X, gen26.ROWS_X + 16) for ph in photos]
        right = sum(s == expect_lines(y) for y, s in zip(ys, seen))
        assert right == 256, (m, right)
        kinds = {"whole": [], "top cut": [], "bottom cut": [], "none": []}
        for y, s in zip(ys, seen):
            k = ("none" if not s else "whole" if len(s) == 16 else
                 "top cut" if s[0] == 0 else "bottom cut")
            kinds[k].append(y)
        out[TAG[m]] = {"right": right, "frames": [res["frames"][0], res["frames"][-1]],
                       "d": res["d"], "cost": sorted(set(res["cost"])),
                       "kinds": {k: [v[0], v[-1], len(v)] if v else [] for k, v in kinds.items()},
                       "first_line": {str(y): s[0] for y, s in zip(ys, seen) if s and
                                      y in (0, 1, 100, 175, 190, 191, 239, 240, 254, 255)}}
    return out


# ---------------------------------------------------------------- columns
def expect_cols(p, size=16):
    return sorted(set(range(p, p + size)) & set(range(256)))


def columns():
    out = {}
    for m in (EU, JP):
        res, states, photos = film("columns", m, [("m0", "m1"), ("m2", "m3")], 380)
        pos = [v[0x1B01] - (32 if v[0x1B03] & 0x80 else 0) for _, v in states]
        assert pos == list(range(-32, 256)), pos[:5]
        seen = [cols_of(ph, gen26.COLS_Y + 1, gen26.COLS_Y + 17) for ph in photos]
        right = sum(s == expect_cols(p) for p, s in zip(pos, seen))
        assert right == len(pos), (m, right)
        out[TAG[m]] = {"right": right, "positions": len(pos), "d": res["d"],
                       "frames": [res["frames"][0], res["frames"][-1]],
                       "consecutive": res["frames"] == list(range(res["frames"][0],
                                                                  res["frames"][0] + len(pos))),
                       "cost": sorted(set(res["cost"])),
                       "first_seen": next(p for p, s in zip(pos, seen) if s),
                       "last_seen": max(p for p, s in zip(pos, seen) if s),
                       "visible": sum(1 for s in seen if s), "whole": sum(1 for s in seen if len(s) == 16)}
    return out


# ---------------------------------------------------------------- edges
def edges():
    out = {}
    for m in (EU, JP):
        regs, vram, photo, shot = still("edges", m)
        res = []
        for (y, x, p, c, where) in gen26.EDGES:
            px = x - (32 if c & 0x80 else 0)
            ink = {(a, b) for b in range(192) for a in range(256)
                   if paper_px(photo, a, b) == BLACK and
                   ((b - y - 1) & 0xFF) < 16 and ((a - px) & 0xFF) < 16 and
                   abs(a - (px + 8)) < 24}
            res.append({"where": where, "box": box(ink), "pixels": len(ink)})
        border = sum(1 for yy in range(240) for xx in range(meas.DRAWN[0], meas.DRAWN[1] + 1)
                     if not (0 <= xx - meas.PAPER_X0 < 256 and 0 <= yy - meas.PAPER_Y0 < 192)
                     and photo[yy][xx] == BLACK)
        out[TAG[m]] = {"sprites": res, "black_in_border": border, "shot": shot,
                       "backdrop": regs[7] & 15}
        assert border == 0
    return out


# ---------------------------------------------------------------- clock
def clock():
    out = {}
    for m in (EU, JP):
        regs, vram, photo, shot = still("clock", m)
        boxes = []
        for (y, x, p, c) in gen26.CLOCK:
            ink = {(a, b) for b in range(y + 1, y + 33) for a in range(256)
                   if paper_px(photo, a, b) == c & 15}
            boxes.append(box(ink))
        out[TAG[m]] = {"boxes": boxes, "shot": shot}
    return out


# ---------------------------------------------------------------- order
def order():
    out = {}
    for m in (EU, JP):
        regs, vram, photo, shot = still("order", m)
        # pair 1: sprite 0, colour 0, over sprite 1, black: a whole black block
        y, x = gen26.ORDER[1][0] + 1, gen26.ORDER[1][1]
        block = sum(paper_px(photo, x + i, y + j) == BLACK for i in range(16) for j in range(16))
        # pair 2: where the ring (sprite 2) and the block (sprite 3) meet
        ring = gen26.sprite16("ring")
        ry, rx = gen26.ORDER[2][0] + 1, gen26.ORDER[2][1]
        by, bx = gen26.ORDER[3][0] + 1, gen26.ORDER[3][1]
        both = [(rx + i, ry + j) for j in range(16) for i in range(16)
                if bx <= rx + i < bx + 16 and by <= ry + j < by + 16]
        ring_on_top = sum(1 for (a, b) in both if ring[b - ry] & 0x8000 >> (a - rx)
                          and paper_px(photo, a, b) == BLACK)
        ring_px = sum(1 for (a, b) in both if ring[b - ry] & 0x8000 >> (a - rx))
        green_through = sum(1 for (a, b) in both if not ring[b - ry] & 0x8000 >> (a - rx)
                            and paper_px(photo, a, b) == LIGHT_GREEN)
        # sprite 4: the band shows through the ring
        sy, sx = gen26.ORDER[4][0] + 1, gen26.ORDER[4][1]
        band_y0, band_y1 = gen26.BANDS[1]
        through = sum(1 for j in range(16) for i in range(16)
                      if not ring[j] & 0x8000 >> i and band_y0 <= sy + j < band_y1
                      and paper_px(photo, sx + i, sy + j) == DARK_BLUE)
        out[TAG[m]] = {"black_block": block, "ring_where_both": [ring_on_top, ring_px],
                       "green_through_ring": green_through, "band_through_ring": through,
                       "shot": shot}
        assert block == 256 and ring_on_top == ring_px
    return out


# ---------------------------------------------------------------- modes
def modes():
    """each mode's photograph: the four sprites read off it, against the four
    digits at 16 x 16, or nothing"""
    block = gen26.sprite16("digits")
    out = {}
    for m in (EU, JP):
        res, states, photos = film("modes", m, [(f"s{k}", f"e{k}") for k in range(4)], 60, held=True)
        per = []
        for (r, v), ph, mode in zip(states, photos, gen26.MODES):
            drawn, whole = 0, 0
            for (y, x, p, c) in gen26.SIZES:
                want = {(x + i, y + 1 + j) for j in range(16) for i in range(16)
                        if block[j] & 0x8000 >> i}
                got = {(px, py) for py in range(y + 1, y + 17) for px in range(x, x + 16)
                       if paper_px(ph, px, py) == c}
                drawn += len(got)
                whole += got == want
            per.append({"mode": mode[4], "mode_seen": vdpscreen.mode(r), "sprite_pixels": drawn,
                        "sprites_whole": whole})
        out[TAG[m]] = {"states": per, "frames": res["frames"], "block_pixels":
                       sum(bin(r).count("1") for r in block)}
        assert [p["sprites_whole"] for p in per] == [4, 4, 4, 0] and per[3]["sprite_pixels"] == 0
    return out


# ---------------------------------------------------------------- march
def march():
    """each state's figures read off the photograph, against the two poses"""
    poses = {"first": gen26.FIGURE, "second": gen26.FIGURE2}
    out = {}
    for m in (EU, JP):
        res, states, photos = film("march", m, [(f"s{k}", f"e{k}") for k in range(4)], 60, held=True)
        per = []
        for (r, v), ph in zip(states, photos):
            seen = []
            for (y, x, p, c) in gen26.march_table():
                got = [sum(0x8000 >> i for i in range(16)
                           if 0 <= x + i < 256 and paper_px(ph, x + i, y + 1 + j) == c)
                       for j in range(16)]
                clip = [sum(0x8000 >> i for i in range(16) if 0 <= x + i < 256) for _ in range(16)]
                seen.append(next((k for k, rows in poses.items()
                                  if [a & b for a, b in zip(rows, clip)] == got), None))
            per.append({"r6": r[6], "poses": sorted(set(map(str, seen))), "figures": len(seen)})
        out[TAG[m]] = {"states": per, "frames": res["frames"]}
        assert [p["poses"] for p in per] == [["second"], ["first"], ["second"], ["first"]], per
    return out


# ---------------------------------------------------------------- tear
def tear():
    """every frame of tear.rom: the lines of the block at the old X and at
    the new, against the moment the new X reached the VRAM; and the
    photograph against the model's two pictures, the old one above the
    first line at the new X and the new one from there"""
    s = sym("tear")
    out = {}
    for m in (EU, JP):
        tcl = (RECORD + f'debug set_bp {s["m0"]} {{}} {{ set ::on 1 }}\n'
               f'debug set_bp {s["m1"]} {{}} {{ set ::on 0 }}\n' +
               once(s["m0"], f'L "regs {REGS}"; {VRAM}', "v"))
        w = run("tear", 60, tcl, m)
        f0 = int(next(x for x in w if x[0] == "f0")[1])
        regs = [int(v) for v in next(x for x in w if x[0] == "regs")[1:]]
        base = bytearray(bytes.fromhex(next(x for x in w if x[0] == "vram")[1]))
        outs = [x for x in w if x[0] == "w" and int(x[3]) & 0xFF == 0x98]
        assert len(outs) == gen26.TEAR_FRAMES, len(outs)
        xs = [gen26.TEAR_XS[0]] + [int(x[4]) for x in outs]
        frames_at = [int(x[1]) - f0 for x in outs]
        films = sorted({f + d for f in frames_at for d in (0, 1, 2)})
        pngs = msxcap.capture(rom("tear"), films, CAPS, f"tear_{TAG[m]}_f", machine=m)
        p0 = vdpslots.PAPER0[m]

        def picture(x):
            v = bytearray(base)
            v[0x1B01] = x
            return vdpscreen.draw(bytes(v), regs)

        def split(ph, old, new):
            """the first line of the block at the new X, if the lines above it
            are all at the old X and those from it all at the new"""
            kinds = []
            for y in range(gen26.TEAR_Y + 1, gen26.TEAR_Y + 33):
                cols = {x for x in range(256) if paper_px(ph, x, y) == BLACK}
                kinds.append("old" if cols == set(range(old, old + 32)) else
                             "new" if cols == set(range(new, new + 32)) else "?")
            if "?" in kinds or "new" not in kinds or "old" not in kinds:
                return None
            n = kinds.index("new")
            return gen26.TEAR_Y + 1 + n if all(k == "new" for k in kinds[n:]) else None
        fits = [d for d in (0, 1, 2) if all(split(codes(pngs[frames_at[k] + d]), xs[k], xs[k + 1])
                                            for k in (0, len(outs) - 1))]
        assert len(fits) == 1, (m, fits)
        d = fits[0]
        res = {"write_line": [], "write_t": [], "taken_line": [], "taken_t": [], "first_new": [],
               "model": []}
        for k, x in enumerate(outs):
            ph = codes(pngs[frames_at[k] + d])
            n = split(ph, xs[k], xs[k + 1])
            cyc = int(x[2])
            taken = vdpslots.slot_after(cyc, vdpslots.moments(cyc, m, regs))
            res["write_line"].append(cyc // vdpslots.LINE - p0)
            res["write_t"].append(round((cyc % vdpslots.LINE) / vdpslots.PER_T, 2))
            res["taken_line"].append(taken // vdpslots.LINE - p0)
            res["taken_t"].append(round((taken % vdpslots.LINE) / vdpslots.PER_T, 2))
            res["first_new"].append(n)
            old, new = picture(xs[k]), picture(xs[k + 1])
            both = [old[y] if y < n else new[y] for y in range(192)]
            res["model"].append(against(both, ph, regs[7] & 15))
        for f in films:
            if f not in [f_ + d for f_ in frames_at]:
                pngs[f].unlink()
        assert all(v == 0 for v in res["model"]), res["model"]
        res["frames"] = [f + d for f in frames_at]
        out[TAG[m]] = {k: sorted(set(v)) if k != "frames" else [v[0], v[-1]]
                       for k, v in res.items()}
    return out


# ---------------------------------------------------------------- herd
def herd():
    out = {}
    want = gen26.herd_frames()
    for name in ("herd", "flip"):
        res = {}
        for m in (EU, JP):
            r, states, photos = film(name, m, [("m0", "m1")], 100)
            tables = []
            for reg, v in states:
                at = (reg[5] & 0x7F) * 0x80
                tables.append(list(v[at:at + 128]))
            assert tables == want, (name, m)
            entry = {"frames": [r["frames"][0], r["frames"][-1]], "d": r["d"],
                     "cost": sorted(set(r["cost"])), "lines": sorted(set(r["lines"])),
                     "r5": sorted({reg[5] for reg, _ in states})}
            if name == "flip":
                s = sym(name)
                tm = run(name, 100, f'debug set_bp {s["t0"]} {{}} {{ L "t0 [machine_info time] '
                                    f'[machine_info VDP_cycle_in_frame]" }}\n'
                                    f'debug set_bp {s["t1"]} {{}} {{ L "t1 [machine_info time] '
                                    f'[machine_info VDP_cycle_in_frame]" }}\n', m)
                t0 = [x for x in tm if x[0] == "t0"]
                t1 = [x for x in tm if x[0] == "t1"]
                entry["send"] = sorted({round((float(b[1]) - float(a[1])) * CLOCK)
                                        for a, b in zip(t0, t1)})
                entry["send_in_paper"] = sum(1 for a in t0 if vdpslots.busy(int(a[2]), m))
            s = sym(name)
            tm = run(name, 100, f'debug set_bp {s["k0"]} {{}} {{ L "k0 [machine_info time]" }}\n'
                                f'debug set_bp {s["k1"]} {{}} {{ L "k1 [machine_info time]" }}\n', m)
            entry["step"] = sorted({round((float(b[1]) - float(a[1])) * CLOCK) for a, b in
                                    zip([x for x in tm if x[0] == "k0"], [x for x in tm if x[0] == "k1"])})
            res[TAG[m]] = entry
        out[name] = res
    return out


# ---------------------------------------------------------------- fall
def fall():
    out = {}
    figs = sum(bin(r).count("1") for r in gen26.FIGURE) * len(gen26.FIGS_X)
    for name in ("fall", "park", "last"):
        ys_want = gen26.fall_ys(name == "park")
        at = 0x1B00 + (16 if name == "last" else 0)
        res = {}
        for m in (EU, JP):
            r, states, photos = film(name, m, [("m0", "m1")], 140)
            ys = [v[at] for _, v in states]
            assert ys == ys_want, (name, m)
            fy = gen26.FIGS_Y + 1
            seen = [sum(1 for y in range(fy, fy + 16) for x in range(256)
                        if paper_px(ph, x, y) == BLACK) for ph in photos]
            lost = [y for y, n in zip(ys, seen) if n != figs]
            res[TAG[m]] = {"frames": len(ys), "figure_pixels": figs, "lost_at_y": lost,
                           "film": [r["frames"][0], r["frames"][-1]],
                           "lost_frames": [f for f, n in zip(r["frames"], seen) if n != figs],
                           "seen_when_lost": sorted({n for n in seen if n != figs}),
                           "cost": sorted(set(r["cost"]))}
        out[name] = res
    for t in ("eu", "jp"):
        assert out["fall"][t]["lost_at_y"] == [208]
        assert out["park"][t]["lost_at_y"] == out["last"][t]["lost_at_y"] == []
    return out


# ---------------------------------------------------------------- prices
def walker(name):
    """walk.py on NAME: the status always says that the paper has ended"""
    return walk.Walk(HERE / name, read_port=lambda port, t: 0x80 if port == 0x99 else 0)


def prices():
    m = json.loads((HERE / "meas26.json").read_text())
    out = {}
    wk = walker("columns")
    out["place"] = wk.call("place", d=1, e=40)
    wk = walker("herd")
    wk.run("init", "next")
    out["step"] = wk.run("k0", "k1")
    wk = walker("herd")
    wk.run("init", "next")
    wk.pc = wk.sym["m0"]
    out["herd_send"] = wk.run("m0", "m1")
    wk = walker("flip")
    wk.run("init", "t0")
    out["flip_send"] = wk.run("t0", "t1")
    wk.pc = wk.sym["m0"]
    out["flip_show"] = wk.run("m0", "m1")
    wk = walker("rows")
    wk.run("init", "m0")
    out["rows_move"] = wk.run("m0", "m1")
    wk = walker("fall")
    wk.run("init", "m0")
    out["fall_move"] = wk.run("m0", "m1")
    measured = {"place": m["columns"]["eu"]["cost"], "step": m["herd"]["herd"]["eu"]["step"],
                "herd_send": m["herd"]["herd"]["eu"]["cost"],
                "flip_send": m["herd"]["flip"]["eu"]["send"],
                "flip_show": m["herd"]["flip"]["eu"]["cost"], "rows_move": m["rows"]["eu"]["cost"],
                "fall_move": m["fall"]["fall"]["eu"]["cost"]}
    for t in ("eu", "jp"):
        assert m["herd"]["herd"][t]["cost"] == [out["herd_send"]]
        assert m["herd"]["herd"][t]["step"] == [out["step"]] == m["herd"]["flip"][t]["step"]
        assert m["herd"]["flip"][t]["send"] == [out["flip_send"]]
        assert m["herd"]["flip"][t]["cost"] == [out["flip_show"]]
        assert m["rows"][t]["cost"] == [out["rows_move"]]
        assert m["fall"]["fall"][t]["cost"] == [out["fall_move"]]
    out["measured"] = measured
    return out


# ---------------------------------------------------------------- answers
def answers():
    m = json.loads((HERE / "meas26.json").read_text())
    out = {}
    # 1: sprite 5's four bytes, for a ball of 16 x 16 from (100, 50), dark blue
    out["q1"] = {"at": gen26.ATT + 4 * 5, "bytes": [50 - 1, 100, gen26.SHAPES["ball"], DARK_BLUE]}
    # 2: the lines of a sprite of 16 x 16 at Y = 250, and its rows shown
    lines = expect_lines(250)
    out["q2"] = {"lines": [lines[0], lines[-1]], "rows": [16 - len(lines), 15]}
    # 3: X and the colour byte for a black sprite whose left edge is at -5
    out["q3"] = {"x": -5 + 32, "colour": 0x80 | BLACK}
    # 4: the four patterns of pattern number 22 at 16 x 16
    out["q4"] = [22 & 0xFC, (22 & 0xFC) + 1, (22 & 0xFC) + 2, (22 & 0xFC) + 3]
    # 5: herd.asm's sends in the lines a 60 Hz frame does not draw
    gap = (vdpslots.LINES[JP] - 192) * 228
    send = m["herd"]["herd"]["jp"]["cost"][0]
    out["q5"] = {"gap": gap, "send": send, "sends": gap // send}
    # 6: patterns 112 to 115 of a table at $1800, and patterns 0 to 3 there
    out["q6"] = {"bytes": [0x1800 + 8 * 112, 0x1800 + 8 * 116 - 1],
                 "patterns_0_3": [0x1800, 0x1800 + 31], "names_end": 0x1AFF,
                 "attributes": [0x1B00, 0x1B7F]}
    return out


# ---------------------------------------------------------------- openmsx
OPENMSX_SECTIONS = ["one", "sizes", "rows", "columns", "edges", "clock", "order", "modes", "march",
                    "tear", "herd", "fall"]


def openmsx():
    if not versions.builds():
        return {"skipped": "OPENMSX_BUILDS not set"}
    return versions.every_build(["ch26"], OPENMSX_SECTIONS)


SECTIONS = {"one": one, "sizes": sizes, "rows": rows, "columns": columns, "edges": edges,
            "clock": clock, "order": order, "modes": modes, "march": march, "tear": tear,
            "herd": herd, "fall": fall, "prices": prices, "answers": answers,
            "openmsx": openmsx}


def main(names=()):
    CAPS.mkdir(exist_ok=True)
    path = HERE / "meas26.json"
    m = json.loads(path.read_text()) if names and path.exists() else {}
    for name in names or SECTIONS:
        print(name, flush=True)
        m[name] = SECTIONS[name]()
        m = {k: m[k] for k in SECTIONS if k in m}
        path.write_text(json.dumps(m, indent=1) + "\n")
    return m


if __name__ == "__main__":
    out = main(sys.argv[1:])
    print(json.dumps({k: out[k] for k in (sys.argv[1:] or out) if k in out}, indent=1)[:5000])
