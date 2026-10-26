#!/usr/bin/env python3
"""meas29.py -- scrolling without hardware help, measured.

    python3 gen29.py && ./build.sh && python3 meas29.py
                                  python3 meas29.py coarse pairs     only these

Every program is filmed, and every frame of the film checked three ways. The
photograph must be vdpscreen.py's drawing of the VRAM and the registers the
debugger reads for it; the shapes, the colours, the names of the table R#2
shows and R#2 itself must be gen29.py's model of them, vram_of(), byte for
byte; and the photograph is held against the IDEAL, the level itself drawn
pixel by pixel at the place the window has reached, with the status line
under it: what differs is counted.

  coarse    coarse.rom: a column a frame, names sent with OTIR (figure 29.1)
  flip      flip.rom: the same, with two name tables
  sets      sets.rom: a pixel a frame, eight shifted sets (figure 29.2)
  pairs     pairs.rom: a pixel a frame, the pairs rewritten (figure 29.2)
  vertical  vertical.rom: a line a frame upwards (figure 29.3)
  pillar    WHERE IT BREAKS: pillar.rom (figure 29.4)
  prices    walk.py's T-states for show and step, against the debugger's
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
import gen29       # noqa: E402
sys.path.remove(str(HERE))
sys.path.insert(0, str(HERE))      # gen29 put chapters 24 and 26 first: this folder's files win
for mod in ("vdpscreen", "walk"):
    sys.modules.pop(mod, None)
import vdpscreen   # noqa: E402
import walk        # noqa: E402  (chapter 28's, with IX)

assert Path(vdpscreen.__file__).parent == HERE and Path(walk.__file__).parent == HERE

CAPS = HERE / "captures"
EU, JP = "MSXBOOK_EU16", "MSXBOOK_JP16"
TAG = {EU: "eu", JP: "jp"}
CLOCK = 3579545
POS = "[machine_info VDP_frame_count] [machine_info VDP_cycle_in_frame] [machine_info time]"
REGS = " ".join(f"[debug read {{VDP regs}} {i}]" for i in range(8))
VRAM = 'binary scan [debug read_block {VRAM} 0 16384] H* h; L "vram $h"'
F0 = 'L "f0 [machine_info VDP_frame_count]"\n'
TOO_FAST = ('proc ::toofast_cb {args} { L "fast [machine_info time]" }\n'
            'set VDP.too_fast_vram_access_callback ::toofast_cb\n')

PALETTE = [tuple(c) for c in json.loads((REPO / "ch01" / "meas01.json").read_text())["palette"]["rgb"]]
CODE = {rgb: n for n, rgb in enumerate(PALETTE) if n}
PATH = {"coarse": gen29.coarse_path, "flip": gen29.flip_path, "sets": gen29.fine_path,
        "pairs": gen29.fine_path, "vertical": gen29.fine_path, "pillar": gen29.fine_path}


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


def paper_of(photo):
    return [[photo[meas.PAPER_Y0 + y][meas.PAPER_X0 + x] for x in range(256)] for y in range(192)]


def once(addr, body, tag):
    return f'set ::{tag} [debug set_bp {addr} {{}} {{ {body}; debug remove_bp $::{tag} }}]\n'


def run(name, frames, tcl, machine):
    lines = msxcap.run_tcl(rom(name), frames, F0 + TOO_FAST + tcl, machine=machine)
    w = [l.split() for l in lines]
    assert not [x for x in w if x[0] == "fast"], (name, machine, "an access too soon")
    return w


def spans(kind, regs):
    """what the program writes and the screen shows: the shapes and colours
    it uses, the status line's, the names of the table R#2 shows"""
    if kind in ("coarse", "flip"):
        n = len(gen29.TILES)
    elif kind == "sets":
        n = 8 * len(gen29.pairs_of(gen29.level())[0])
    elif kind == "vertical":
        n = len(gen29.vpairs_of(gen29.V_ROWS)[0])
    else:
        n = len(gen29.pairs_of(gen29.level(pillar=kind == "pillar"))[0])
    t, g = 8 * n, 8 * gen29.FIRST_TEXT
    table = (regs[2] & 0x0F) * 0x400
    return [(0, t), (g, g + 8 * len(gen29.GLYPHS)), (0x2000, 0x2000 + t),
            (0x2000 + g, 0x2000 + g + 8 * len(gen29.GLYPHS)), (table, table + 768)]


def tables_differ(kind, vram, regs, at):
    want = gen29.vram_of(kind, at)
    bad = sum(1 for a, b in spans(kind, regs) for i in range(a, b) if vram[i] != want[i])
    return bad + (regs != gen29.regs_of(kind, at))


# ---------------------------------------------------------------- the ideal
def ideal(kind, at):
    """the level drawn pixel by pixel where the window has reached, and the
    status line under it"""
    regs = gen29.regs_of(kind, at)
    pic = [[0] * 256 for _ in range(192)]
    if kind == "vertical":
        rows, tiles = gen29.V_ROWS, gen29.V_TILES
        for y in range(8 * gen29.ROWS):
            ly = at + y
            for x in range(256):
                _, s, c = tiles[rows[ly // 8][x // 8]]
                bit = s[ly % 8] >> (7 - x % 8) & 1
                pic[y][x] = vdpscreen.colour(c[ly % 8] >> 4 if bit else c[ly % 8] & 15, regs)
    else:
        lvl = gen29.level(pillar=kind == "pillar")
        off = 8 * at if kind in ("coarse", "flip") else at
        for y in range(8 * gen29.ROWS):
            for x in range(256):
                lx = off + x
                _, s, c = gen29.TILES[lvl[y // 8][lx // 8]]
                bit = s[y % 8] >> (7 - lx % 8) & 1
                pic[y][x] = vdpscreen.colour(c[y % 8] >> 4 if bit else c[y % 8] & 15, regs)
    names = gen29.status_names()
    for y in range(8 * gen29.ROWS, 192):
        for x in range(256):
            ch = gen29.GLYPHS[names[32 * (y // 8 - gen29.ROWS) + x // 8] - gen29.FIRST_TEXT]
            bit = gen29.FONT[ch][y % 8] >> (7 - x % 8) & 1
            pic[y][x] = vdpscreen.colour(gen29.TEXT_C >> 4 if bit else gen29.TEXT_C & 15, regs)
    return pic


def off_ideal(photo, kind, at):
    pic, pp = ideal(kind, at), paper_of(photo)
    rows = 8 * gen29.ROWS
    level_off = sum(1 for y in range(rows) for x in range(256) if pp[y][x] != pic[y][x])
    status_off = sum(1 for y in range(rows, 192) for x in range(256) if pp[y][x] != pic[y][x])
    return {"level": level_off, "status": status_off}


# ---------------------------------------------------------------- films
def film(name, machine):
    """every show, m0 to m1, and every step, m1 to s1: frame and T-states; the
    VRAM and registers the show left, read when the next show begins or at
    done; and the photograph of each, the frame after the show's"""
    path = PATH[name]()
    s = sym(name)
    read = f'L "regs {REGS}"; {VRAM}'
    tcl = (f'debug set_bp {s["m0"]} {{}} {{ {read}; L "a {POS}" }}\n'
           f'debug set_bp {s["m1"]} {{}} {{ L "b {POS}" }}\n'
           f'debug set_bp {s["s1"]} {{}} {{ L "c {POS}" }}\n' +
           once(s["done"], f'{read}; L "end"', "e"))
    w = run(name, len(path) + 40, tcl, machine)
    f0 = int(next(x for x in w if x[0] == "f0")[1])
    a_s = [x for x in w if x[0] == "a"]
    b_s = [x for x in w if x[0] == "b"]
    c_s = [x for x in w if x[0] == "c"]
    regs = [[int(v) for v in x[1:]] for x in w if x[0] == "regs"][1:]
    vrams = [bytes.fromhex(x[1]) for x in w if x[0] == "vram"][1:]
    assert len(a_s) == len(b_s) == len(c_s) == len(regs) == len(vrams) == len(path), \
        (name, len(a_s), len(regs), len(path))
    bad = [tables_differ(name, v, r, at) for v, r, at in zip(vrams, regs, path)]
    assert not any(bad), (name, machine, bad[:8])
    frames_at = [int(a[1]) - f0 for a in a_s]
    assert frames_at == list(range(frames_at[0], frames_at[0] + len(path))), (name, machine)
    show = [round((float(b[3]) - float(a[3])) * CLOCK) for a, b in zip(a_s, b_s)]
    step = [round((float(c[3]) - float(b[3])) * CLOCK) for b, c in zip(b_s, c_s)]
    shots = sorted({f + d for f in frames_at for d in (0, 1, 2)})
    pngs = msxcap.capture(rom(name), shots, CAPS, f"{name}_{TAG[machine]}_f", machine=machine)
    photos = {f: codes(pngs[f]) for f in shots}
    fits = [d for d in (0, 1, 2)
            if all(against(vdpscreen.draw(v, r), photos[f + d], r[7] & 15) == 0
                   for v, r, f in zip(vrams, regs, frames_at))]
    assert 1 in fits, (name, machine, fits)
    keep = {f + 1 for f in frames_at}
    for f in shots:
        if f not in keep:
            pngs[f].unlink()
    lines = [int(a[2]) // vdpslots.LINE for a in a_s]
    ends = [int(b[2]) // vdpslots.LINE + (int(b[1]) - int(a[1])) * vdpslots.LINES[machine]
            for a, b in zip(a_s, b_s)]
    step_ends = [int(c[2]) // vdpslots.LINE + (int(c[1]) - int(a[1])) * vdpslots.LINES[machine]
                 for a, c in zip(a_s, c_s)]
    offs = [off_ideal(photos[f + 1], name, at) for f, at in zip(frames_at, path)]
    return {"frames": [f + 1 for f in frames_at], "fits": fits, "show": show, "step": step,
            "lines": sorted(set(lines)), "ends": [min(ends), max(ends)],
            "step_ends": [min(step_ends), max(step_ends)], "off_ideal": offs}


def section(name):
    def go():
        out = {}
        for m in (EU, JP):
            out[TAG[m]] = film(name, m)
        return out
    return go


# ---------------------------------------------------------------- prices
def prices():
    out = {}
    for name in ("coarse", "flip", "sets", "pairs", "vertical"):
        wk = walk.Walk(HERE / name, read_port=lambda port, t: 0x80 if port == 0x99 else 0)
        wk.run("init", "m0")
        shows, steps = [], []
        for _ in range(16):
            shows.append(wk.run("m0", "m1"))
            steps.append(wk.run("m1", "s1"))
            wk.run("s1", "m0")
        out[name] = {"show": shows, "step": steps}
    m = json.loads((HERE / "meas29.json").read_text())
    for name in out:
        for t in ("eu", "jp"):
            assert m[name][t]["show"][:16] == out[name]["show"], (name, t)
            assert m[name][t]["step"][:16] == out[name]["step"], (name, t)
    return out


# ---------------------------------------------------------------- answers
def answers():
    m = json.loads((HERE / "meas29.json").read_text())
    np_ = len(gen29.pairs_of(gen29.level())[0])
    out = {}
    # 1: the most pairs whose eight sets fit below the status line's letters
    out["q1"] = {"pairs": gen29.FIRST_TEXT // 8, "level": np_}
    # 2: two pixels a frame: shifts 0, 2, 4, 6
    out["q2"] = {"sets": 4, "patterns": 4 * np_}
    # 3: coarse.asm with 22 rows that scroll: 32 more bytes for OTIR, 23 T-states each
    show = m["coarse"]["jp"]["show"][0]
    out["q3"] = {"show": show + 32 * 23, "room": 15960, "over": show + 32 * 23 - 15960}
    # 4: pairs.asm's next window written an eighth a frame
    out["q4"] = {"names": 21 * 32 // 8, "t": 21 * 32 // 8 * 46}
    # 5: the eight copies in the cartridge
    nv = len(gen29.vpairs_of(gen29.V_ROWS)[0])
    out["q5"] = {"pairs": 8 * 8 * np_, "vertical": 2 * 8 * 8 * nv}
    return out


# ---------------------------------------------------------------- openmsx
OPENMSX_SECTIONS = ["coarse", "flip", "sets", "pairs", "vertical", "pillar"]


def openmsx():
    if not versions.builds():
        return {"skipped": "OPENMSX_BUILDS not set"}
    return versions.every_build(["ch29"], OPENMSX_SECTIONS)


SECTIONS = {"coarse": section("coarse"), "flip": section("flip"), "sets": section("sets"),
            "pairs": section("pairs"), "vertical": section("vertical"),
            "pillar": section("pillar"), "prices": prices, "answers": answers,
            "openmsx": openmsx}


def main(names=()):
    CAPS.mkdir(exist_ok=True)
    path = HERE / "meas29.json"
    m = json.loads(path.read_text()) if names and path.exists() else {}
    for name in names or SECTIONS:
        print(name, flush=True)
        m[name] = SECTIONS[name]()
        m = {k: m[k] for k in SECTIONS if k in m}
        path.write_text(json.dumps(m, indent=1) + "\n")
    return m


if __name__ == "__main__":
    main(sys.argv[1:])
