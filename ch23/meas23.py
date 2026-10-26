#!/usr/bin/env python3
"""meas23.py -- colour clash on the MSX, measured.

    python3 gen23.py && ./build.sh && python3 meas23.py
                                  python3 meas23.py places ways    only these

Every frame of every film is checked against vdpscreen.py, given the VDP's
registers and the whole VRAM as the debugger read them after the move made
before it; and against the picture as it was meant, gen23.py's scene with the
ball on it, to count the pixels whose colour is not their own.

  places    places.rom: each ball's strips read off the photograph, two or
            three a line (figure 23.1)
  hill      hill.rom: the slope's pixels on the wrong side, in whole strips and
            in the strips' two colours (figure 23.5)
  ways      every moving program on both machines: each move's T-states, the
            bytes it writes to the shapes, the colours and the sprites, where
            in the frame it is made; every frame against the model, and its
            pixels in the wrong colour (figures 23.2 and 23.3)
  send      clash.rom: every call of send timed, against its price
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
sys.path.insert(0, str(REPO / "ch14"))
sys.path.insert(0, str(REPO / "ch20"))
sys.path.insert(0, str(HERE))
import meas        # noqa: E402
import msxcap      # noqa: E402
import probe as dbg  # noqa: E402
import versions    # noqa: E402
import cycles      # noqa: E402  (chapter 14: an instruction's price)
import vdpslots    # noqa: E402  (chapter 20: where the paper is in a frame)
import gen23       # noqa: E402
import vdpscreen   # noqa: E402

CAPS = HERE / "captures"
EU, JP = "MSXBOOK_EU16", "MSXBOOK_JP16"
TAG = {EU: "eu", JP: "jp"}
CLOCK = 3579545
SHOT = 30
POS = "[machine_info VDP_frame_count] [machine_info VDP_cycle_in_frame] [machine_info time]"
REGS = " ".join(f"[debug read {{VDP regs}} {i}]" for i in range(8))
VRAM = 'binary scan [debug read_block {VRAM} 0 16384] H* h; L "vram $h"'
F0 = 'L "f0 [machine_info VDP_frame_count]"\n'
WHITE = gen23.WHITE
FILM = 110                  # the film frames run: the last move is made by then
AFTER = 40                  # the moves before the photograph of figures 23.3 and 23.4
# every run: count the accesses to the VRAM that came too soon (chapter 19)
TOO_FAST = ('set ::toofast 0\nproc ::toofast_cb {args} { incr ::toofast; L "toofast" }\n'
            'set VDP.too_fast_vram_access_callback ::toofast_cb\n')
MOVING = ["clash", "sprite", "oneink", "plain", "steps", "mono", "backdrop", "blocks", "zero"]

# the colour codes as openMSX draws them: chapter 1's palette.rom, both machines
PALETTE = [tuple(c) for c in json.loads((REPO / "ch01" / "meas01.json").read_text())["palette"]["rgb"]]
CODE = {rgb: n for n, rgb in enumerate(PALETTE) if n}       # colour 0 is never drawn as itself


def rom(name):
    return HERE / f"{name}.rom"


def sym(name):
    return dbg.sym(HERE / f"{name}.sym")


def run(name, frames, tcl, machine=EU):
    lines = msxcap.run_tcl(rom(name), frames, TOO_FAST + tcl, machine=machine)
    assert "toofast" not in lines, f"{name}: an access to the VRAM came too soon"
    return [l.split() for l in lines]


def shots(name, frames, machine, prefix=None):
    return msxcap.capture(rom(name), frames, CAPS, prefix or f"{name}_{TAG[machine]}_f",
                          machine=machine)


def codes(png):
    """the photograph as colour codes, 240 rows of 320"""
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


def once(addr, body, tag):
    return f'set ::{tag} [debug set_bp {addr} {{}} {{ {body}; debug remove_bp $::{tag} }}]\n'


def paper(photo):
    """the photograph's paper: 192 rows of 256"""
    return [row[meas.PAPER_X0:meas.PAPER_X0 + 256] for row in photo[meas.PAPER_Y0:meas.PAPER_Y0 + 192]]


# ---------------------------------------------------------------- prices
JUMPS = {"djnz": (14, 9), "jr": (13, 8), "call": (18, 18), "ret": (11, 11),
         "jp": (11, 11)}                               # chapters 11 and 12


def lst_lines(name):
    """[(source, address, bytes)] of the instructions of a listing (chapter 19's reader)"""
    out = []
    for line in (HERE / f"{name}.lst").read_text().splitlines():
        m = dbg.LST.match(line)
        if not m or "..." in m.group(3)[1:13] or not m.group(3)[1:13].strip():
            continue
        _, a, code, src = dbg.lst_fields(m)
        src = re.sub(r"^\s*[\w.]+:", "", src.split(";")[0].lstrip(">")).strip()
        if src and not src.lower().startswith(("db", "dw", "ds", "align")):
            out.append((src, a, code))
    return out


def price(src, code, moved=0):
    """the MSX price of one instruction (taken, not taken); OTIR moving MOVED
    bytes: 23 a byte, 18 the last (chapter 13)"""
    op = src.split()[0].lower()
    if op == "ret" and len(src.split()) > 1:
        return 12, 6
    if op in JUMPS:
        return JUMPS[op]
    if op == "otir":
        t = 23 * (moved - 1) + 18
        return t, t
    t = cycles.msx(code)
    return t, t


def runs(y):
    """the runs in which send puts 16 lines from line Y: one for each cell"""
    first = 8 - y % 8
    out = [first]
    while sum(out) < 16:
        out.append(min(8, 16 - sum(out)))
    return out


def send_price(name, y):
    """send's T-states for a column from line Y, from the listing, up to .done
    (pop bc and ret not included)"""
    s = sym(name)
    seg = [(src, a, c) for src, a, c in lst_lines(name) if s["send"] <= a < s["send.done"]]
    head = sum(price(src, c)[0] for src, a, c in seg if a < s["send.run"])
    body = [(src, a, c) for src, a, c in seg if s["send.run"] <= a]
    jz = next(i for i, (src, a, c) in enumerate(body) if src.replace(" ", "").lower() == "jrz,.done")
    jnc = next(i for i, (src, a, c) in enumerate(body) if src.replace(" ", "").lower() == "jrnc,.full")
    rs = runs(y)
    t, left = head, 16 - rs[0]
    for k, n in enumerate(rs):
        last = k == len(rs) - 1
        t += sum(price(src, c, n)[0] for src, a, c in body[:jz])         # the run, to OTIR and on
        t += price(*body[jz][::2])[0 if last else 1]                      # jr z, .done
        if last:
            break
        t += sum(price(src, c)[0] for src, a, c in body[jz + 1:jnc])     # ld b, 8 and cp b
        full = left >= 8
        t += price(*body[jnc][::2])[0 if full else 1]                     # jr nc, .full
        rest = body[jnc + 1:]
        if full:
            rest = [r for r in rest if r[1] >= s["send.full"]]
        t += sum(price(src, c)[0] for src, a, c in rest)                  # (ld b, a), sub b, jr .run
        left -= rs[k + 1]
    return t


# ---------------------------------------------------------------- places
def places():
    pix = gen23.ball_pixels()
    out = {}
    for machine in (EU, JP):
        s = sym("places")
        w = run("places", SHOT, once(s["done"], f'L "regs {REGS}"; {VRAM}', "b"), machine)
        regs = [int(v) for v in next(x for x in w if x[0] == "regs")[1:]]
        vram = bytes.fromhex(next(x for x in w if x[0] == "vram")[1])
        photo = codes(shots("places", [SHOT], machine)[SHOT])
        assert against(vdpscreen.draw(vram, regs), photo, regs[7] & 15) == 0
        p = paper(photo)
        balls = []
        for k, (x, y) in enumerate(gen23.PLACES):
            per_line = []
            for line in range(y - 2, y + 18):
                n = sum(1 for c in range(32) if any(p[line][8 * c + i] != WHITE for i in range(8))
                        and 8 * c + 8 > x - 8 and 8 * c < x + 24)
                per_line.append(n)
            ink = {(px - x, py - y) for py in range(y, y + 16) for px in range(x, x + 16)
                   if p[py][px] == gen23.BLACK}
            assert ink == pix, (k, len(ink))
            assert per_line[:2] == per_line[-2:] == [0, 0]
            strips = per_line[2:18]
            assert len(set(strips)) == 1
            balls.append({"x": x, "y": y, "shift": x % 8, "strips_per_line": strips[0],
                          "strips": sum(strips), "pixels": 8 * sum(strips), "ball": len(ink)})
        out[TAG[machine]] = balls
    assert out["eu"] == out["jp"]
    b = out["eu"]
    out["mean_strips"] = sum(x["strips"] for x in b) / 8
    out["mean_pixels"] = sum(x["pixels"] for x in b) / 8
    out["ball"] = len(pix)
    return out


# ---------------------------------------------------------------- hill
def hill():
    out = {}
    for machine in (EU, JP):
        s = sym("hill")
        w = run("hill", SHOT, once(s["done"], f'L "regs {REGS}"; {VRAM}', "b"), machine)
        regs = [int(v) for v in next(x for x in w if x[0] == "regs")[1:]]
        vram = bytes.fromhex(next(x for x in w if x[0] == "vram")[1])
        photo = codes(shots("hill", [SHOT], machine)[SHOT])
        assert against(vdpscreen.draw(vram, regs), photo, regs[7] & 15) == 0
        p = paper(photo)
        left = right = 0
        for y in range(192):
            for x in range(256):
                want = gen23.LIGHT_GREEN if y >= gen23.edge(x) else WHITE
                if p[y][x] != want:
                    if x < gen23.HILL_SPLIT:
                        left += 1
                    else:
                        right += 1
        out[TAG[machine]] = {"wrong_left": left, "wrong_right": right}
    assert out["eu"] == out["jp"] and out["eu"]["wrong_right"] == 0
    shapes, colours = gen23.hill_tables()
    out["edge_strips"] = sum(1 for b in shapes if b not in (0, 0xFF))
    return out


# ---------------------------------------------------------------- ways
def ideal(name, place, backdrop):
    """the picture as meant: the scene, and the ball in its colour; or, for
    blocks.asm, the scene with the block's 16 x 16 in the block's colours"""
    s = gen23.SCENES[name]
    bx, by = place
    rows = []
    for y in range(192):
        pat = gen23.GRASS[y % 8] if s["grass"] else 0
        row = []
        for x in range(256):
            col = s["colours"][y // 64]
            if s["ball"] is None and bx <= x < bx + 16 and by <= y < by + 16:
                col = s["paint"][y // 64]
            ink, pap = col >> 4 or backdrop, col & 15 or backdrop
            row.append(ink if pat & 0x80 >> x % 8 else pap)
        rows.append(row)
    if s["ball"] is not None:
        for dx, dy in gen23.ball_pixels():
            rows[by + dy][bx + dx] = s["ball"]
    return rows


def kind(addr):
    return "colours" if 0x2000 <= addr < 0x3800 else "sprites" if 0x1B00 <= addr < 0x1B80 else \
        "shapes" if addr < 0x1800 else "other"


def way(name, machine):
    s = sym(name)
    tcl = (f'debug set_bp {s["m0"]} {{}} {{ set ::n {{}}; L "m0 {POS}" }}\n'
           f'debug set_bp {s["m1"]} {{}} {{ L "m1 {POS}"; L "regs {REGS}"; L "pos '
           f'[debug read memory {0xC100}] [debug read memory {0xC101}]"; L "out $::n"; {VRAM} }}\n'
           'set ::n {}\n'
           'debug set_watchpoint write_io 0x98 {} { lappend ::n [expr {[debug read {VRAM pointer} 0] '
           '+ 256 * [debug read {VRAM pointer} 1]}] }\n' + F0)
    w = run(name, FILM, tcl, machine)
    f0 = int(next(x for x in w if x[0] == "f0")[1])
    m0 = [x for x in w if x[0] == "m0"]
    m1 = [x for x in w if x[0] == "m1"]
    regs = [[int(v) for v in x[1:]] for x in w if x[0] == "regs"]
    pos = [(int(x[2]), int(x[1])) for x in w if x[0] == "pos"]           # (x, y)
    outs = [[int(v) for v in x[1:]] for x in w if x[0] == "out"]
    vrams = [bytes.fromhex(x[1]) for x in w if x[0] == "vram"]
    n = len(m1)
    assert n == len(m0) == len(vrams) == gen23.MOVES, (name, n)
    assert pos == gen23.path(name), name
    frame_len = vdpslots.LINES[machine] * vdpslots.LINE
    paper0 = vdpslots.PAPER0[machine] * vdpslots.LINE + vdpslots.BORDER_IN
    res = {"cost": [], "bytes": [], "lines": [], "spare": [], "wrong": [], "model": []}
    for a, b, o in zip(m0, m1, outs):
        res["cost"].append(round((float(b[3]) - float(a[3])) * CLOCK))
        counts = {}
        for addr in o:
            counts[kind(addr)] = counts.get(kind(addr), 0) + 1
        assert "other" not in counts, (name, counts)
        res["bytes"].append(counts)
        # the move, start and end, in the lines the VDP does not draw, and no
        # paper begun between them
        c0, c1 = int(a[2]), int(b[2])
        start = int(a[1]) * frame_len + c0
        end = int(b[1]) * frame_len + c1
        nxt = int(a[1]) * frame_len + paper0 + (frame_len if c0 >= paper0 else 0)
        assert not vdpslots.busy(c0, machine) and not vdpslots.busy(c1, machine) and end < nxt, \
            (name, machine, c0, c1)
        res["lines"].append([c0 // vdpslots.LINE, c1 // vdpslots.LINE])
        res["spare"].append((nxt - end) // vdpslots.PER_T)       # T-states left before the paper
    # the film: the frame after each move against the model of the VRAM after
    # it; the frame is fitted, one or two after the move's own
    ends = [int(b[1]) - f0 for b in m1]
    films = sorted({e + d for e in ends for d in (0, 1, 2)})
    pngs = shots(name, films, machine)
    # (and for the sprite, the line it begins on, fitted too: rule 9)
    fits = []
    for dy in ((0, 1, 2, 3) if name == "sprite" else (vdpscreen.SPRITE_DY,)):
        vdpscreen.SPRITE_DY = dy
        for d in (0, 1, 2):
            ok = True
            for k in (0, n // 2, n - 1):
                photo = codes(pngs[ends[k] + d])
                if against(vdpscreen.draw(vrams[k], regs[k]), photo, regs[k][7] & 15):
                    ok = False
                    break
            if ok:
                fits.append((d, dy))
    assert len(fits) == 1, (name, machine, fits)
    d, dy = fits[0]
    vdpscreen.SPRITE_DY = dy
    if name == "sprite":
        res["sprite_dy"] = dy
    for k in range(n):
        photo = codes(pngs[ends[k] + d])
        res["model"].append(against(vdpscreen.draw(vrams[k], regs[k]), photo, regs[k][7] & 15))
        want = ideal(name, pos[k], regs[k][7] & 15)
        p = paper(photo)
        res["wrong"].append(sum(a != b for ra, rb in zip(p, want) for a, b in zip(ra, rb)))
        if k == AFTER - 1:
            res["after40"] = {"film": ends[k] + d,
                              "colours": sorted({c for row in p for c in row})}
    for f in films:                                         # only the frames used are kept
        if f not in [e + d for e in ends]:
            pngs[f].unlink()
    assert all(v == 0 for v in res["model"]), (name, machine, res["model"])
    res["film_after_move"] = d
    res["films"] = [e + d for e in ends]
    return res


def ways():
    out = {}
    for name in MOVING:
        r = {}
        for machine in (EU, JP):
            r[TAG[machine]] = way(name, machine)
        e, j = r["eu"], r["jp"]
        assert e["cost"] == j["cost"] and e["bytes"] == j["bytes"] and e["wrong"] == j["wrong"], name
        r["summary"] = {"cost": [min(e["cost"]), max(e["cost"])],
                        "colours_bytes": sorted({b.get("colours", 0) for b in e["bytes"]}),
                        "shapes_bytes": sorted({b.get("shapes", 0) for b in e["bytes"]}),
                        "sprites_bytes": sorted({b.get("sprites", 0) for b in e["bytes"]}),
                        "wrong": [min(e["wrong"]), max(e["wrong"])],
                        "spare": {t: min(r[t]["spare"]) for t in ("eu", "jp")}}
        out[name] = r
    # the colour work: clash.asm's moves against mono.asm's, on the same path
    out["colour_work"] = sorted({a - b for a, b in zip(out["clash"]["eu"]["cost"],
                                                       out["mono"]["eu"]["cost"])})
    # clash.asm's pixels in the wrong colour, by the ball's shift in its bytes
    by = {}
    for (x, y), wr in zip(gen23.path("clash"), out["clash"]["eu"]["wrong"]):
        by.setdefault(x % 8, set()).add(wr)
    out["clash_by_shift"] = {str(k): sorted(v) for k, v in sorted(by.items())}
    return out


# ---------------------------------------------------------------- send
def send():
    s = sym("clash")
    tcl = (f'debug set_bp {s["send"]} {{}} {{ L "s0 [machine_info time] [reg C]" }}\n'
           f'debug set_bp {s["send.done"]} {{}} {{ L "s1 [machine_info time]" }}\n')
    out = {}
    for machine in (EU, JP):
        w = run("clash", FILM, tcl, machine)
        s0 = [x for x in w if x[0] == "s0"]
        s1 = [float(x[1]) for x in w if x[0] == "s1"]
        got = {}
        for a, b in zip(s0, s1):
            y = int(a[2])
            t = round((b - float(a[1])) * CLOCK)
            got.setdefault(len(runs(y)), set()).add(t)
        out[TAG[machine]] = {"calls": len(s1), "t": {str(k): sorted(v) for k, v in got.items()}}
    priced = {str(r): send_price("clash", y) for r, y in ((2, 0), (3, 3))}
    for t in ("eu", "jp"):
        assert out[t]["t"] == {k: [v] for k, v in priced.items()}, (out[t]["t"], priced)
    out["priced"] = priced
    done = sym("clash")["send.done"]
    out["done"] = sum(price(src, c)[0] for src, a, c in lst_lines("clash") if done <= a < done + 2)
    return out


# ---------------------------------------------------------------- answers
def answers():
    m = json.loads((HERE / "meas23.json").read_text())
    out = {}
    # 1: a ball whose top left pixel is (100, 70): the strips it touches
    x, y = 100, 70
    cols = list(range(x // 8, (x + 15) // 8 + 1))
    out["q1"] = {"columns": cols, "lines": [y, y + 15], "strips": 16 * len(cols)}
    # 2: a sprite 8 pixels wide and 16 tall drawn in the shapes: strips a line,
    #    in each of the eight places, and on average
    per = [1 if s == 0 else 2 for s in range(8)]
    out["q2"] = {"per_line": per, "mean_strips": 16 * sum(per) / 8}
    # 3: clash.asm's colour work, measured: the most and the least of a move
    out["q3"] = m["ways"]["colour_work"]
    # 4: the moves of oneink.asm and of sprite.asm that fit in the lines a
    #    60 Hz frame does not draw, at their longest
    gap = (vdpslots.LINES[JP] - 192) * 228
    out["q4"] = {"gap": gap, **{n: gap // max(m["ways"][n]["eu"]["cost"]) for n in ("oneink", "sprite")}}
    # 5: backdrop.asm: R#7 when the ball's top is on line 100
    out["q5"] = gen23.SCENES["backdrop"]["backs"][100 // 64]
    return out


# ---------------------------------------------------------------- openmsx
OPENMSX_SECTIONS = ["places", "hill", "ways", "send"]


def openmsx():
    if not versions.builds():
        return {"skipped": "OPENMSX_BUILDS not set"}
    return versions.every_build(["ch23"], OPENMSX_SECTIONS)


SECTIONS = {"places": places, "hill": hill, "ways": ways, "send": send, "answers": answers, "openmsx": openmsx}


def main(names=()):
    CAPS.mkdir(exist_ok=True)
    path = HERE / "meas23.json"
    m = json.loads(path.read_text()) if names and path.exists() else {}
    for name in names or SECTIONS:
        print(name, flush=True)
        m[name] = SECTIONS[name]()
        m = {k: m[k] for k in SECTIONS if k in m}
        path.write_text(json.dumps(m, indent=1) + "\n")
    return m


if __name__ == "__main__":
    out = main(sys.argv[1:])
    print(json.dumps({k: out[k] for k in (sys.argv[1:] or out) if k in out}, indent=1)[:6000])
