#!/usr/bin/env python3
"""meas27.py -- hardware sprites II, measured.

    python3 gen27.py && ./build.sh && python3 meas27.py
                                  python3 meas27.py five rotate    only these

Every photograph, on both machines, must be vdpscreen.py's drawing of the
VRAM and the registers the debugger reads for its frame, with chapter 27's
rule 10: four sprites on a line at most. Every status a program read must be
what the model's rule 11 says for the table it read it with. A film is checked
frame by frame, and the photograph read the other way: which figures are on
it, and which are not.

  five      five.rom: four figures and a ball, on lines it shares with them
            the ball not drawn; first.rom, the ball first (figure 27.1)
  stagger   stagger.rom: eight figures, four on a line (figure 27.3)
  status    status.rom: six tables, the status of every frame against rule 11
  rotate    rotate.rom: eight figures, the table sent as it is, then turned
            by four entries a frame (figure 27.4)
  hero      hero.rom: a ball first in every table and seven figures turned
            behind it, by one entry a frame and then by three
  layers    layers.rom: faces of two sprites each (figure 27.2)
  adaptive  WHERE IT BREAKS: poll.rom and keep.rom, the status every frame,
            and which figures every frame shows (figure 27.5)
  once      once.rom: the status read once a frame by the interrupt routine,
            six on a line and then three
  reads     every read of one of poll.rom's waits, and its line
  prices    walk.py's T-states for the sends, against the debugger's
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
import meas        # noqa: E402
import msxcap      # noqa: E402
import probe as dbg  # noqa: E402
import versions    # noqa: E402
import vdpslots    # noqa: E402  (chapter 20)
import walk        # noqa: E402  (chapter 25)
sys.path.insert(0, str(HERE))
import gen27       # noqa: E402
sys.path.remove(str(HERE))
sys.path.insert(0, str(HERE))      # gen27 put chapter 26 first: this folder's model wins
sys.modules.pop("vdpscreen", None)
import vdpscreen   # noqa: E402  (rules 10 and 11)

assert Path(vdpscreen.__file__).parent == HERE and hasattr(vdpscreen, "sprite_status")

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
BLACK, LIGHT_GREEN, DARK_BLUE, WHITE = gen27.BLACK, gen27.LIGHT_GREEN, gen27.DARK_BLUE, gen27.WHITE

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


def paper_px(photo, x, y):
    return photo[meas.PAPER_Y0 + y][meas.PAPER_X0 + x]


def once(addr, body, tag):
    return f'set ::{tag} [debug set_bp {addr} {{}} {{ {body}; debug remove_bp $::{tag} }}]\n'


def run(name, frames, tcl, machine, events=None):
    lines = msxcap.run_tcl(rom(name), frames, F0 + TOO_FAST + tcl, machine=machine, events=events)
    w = [l.split() for l in lines]
    assert not [x for x in w if x[0] == "fast"], (name, machine, "an access too soon")
    return w


def table_vram(table):
    """a VRAM holding TABLE at the attributes, for the model's rules 10 and 11"""
    v = bytearray(16384)
    b = gen27.table_bytes(table)
    v[gen27.ATT:gen27.ATT + len(b)] = bytes(b)
    return v


def seen(photo, table, shape_rows):
    """for each sprite of TABLE: how many of its pixels the photograph shows
    in its colour, and how many it has on the paper"""
    out = []
    for (y, x, p, c) in table:
        rows = shape_rows[p]
        on = [(x + i, y + 1 + j) for j in range(16) for i in range(16)
              if rows[j] & 0x8000 >> i and 0 <= y + 1 + j < 192 and x + i < 256]
        out.append([sum(1 for (a, b) in on if paper_px(photo, a, b) == (c & 15)), len(on)])
    return out


SHAPE_ROWS = {p: [gen27.PATTERNS[8 * p + r] << 8 | gen27.PATTERNS[8 * p + 16 + r] for r in range(16)]
              for p in gen27.SHAPES.values()}


# ---------------------------------------------------------------- a still
def still(name, machine, extra=""):
    s = sym(name)
    w = run(name, 40, once(s["done"], f'L "regs {REGS}"; {VRAM}; L "done {POS}"', "d"), machine,
            events={34: 'L "status [debug read {VDP status regs} 0]"'})
    f0 = int(next(x for x in w if x[0] == "f0")[1])
    regs = [int(v) for v in next(x for x in w if x[0] == "regs")[1:]]
    vram = bytes.fromhex(next(x for x in w if x[0] == "vram")[1])
    shot = int(next(x for x in w if x[0] == "done")[1]) - f0 + 2
    png = msxcap.capture(rom(name), [shot], CAPS, f"{name}_{TAG[machine]}_f", machine=machine)[shot]
    photo = codes(png)
    assert against(vdpscreen.draw(vram, regs), photo, regs[7] & 15) == 0, (name, machine)
    st = [int(x[1]) for x in w if x[0] == "status"]
    return regs, vram, photo, shot, st


def no_limit(vram, regs):
    """the model with no limit on a line: what rule 10 takes away"""
    old = vdpscreen.LIMIT
    try:
        vdpscreen.LIMIT = 32
        return vdpscreen.draw(vram, regs)
    finally:
        vdpscreen.LIMIT = old


# ---------------------------------------------------------------- five
def five():
    out = {}
    for m in (EU, JP):
        regs, vram, photo, shot, st = still("five", m)
        ball = gen27.FIVE[4]
        rows = SHAPE_ROWS[ball[2]]
        lines = sorted({ball[0] + 1 + j for j in range(16) for i in range(16)
                        if rows[j] & 0x8000 >> i and paper_px(photo, ball[1] + i, ball[0] + 1 + j) == DARK_BLUE})
        lost = sum(1 for a, b in zip(sum(no_limit(vram, regs), []), sum(vdpscreen.draw(vram, regs), []))
                   if a != b)
        out[TAG[m]] = {"ball_lines": [lines[0], lines[-1]], "seen": seen(photo, gen27.FIVE, SHAPE_ROWS),
                       "status_peek": st, "model_status": list(vdpscreen.sprite_status(vram, regs)),
                       "model_status_f": list(vdpscreen.sprite_status(vram, regs, f=1)),
                       "rule10_pixels": lost, "shot": shot}
        # nothing reads the status: F stays set, and the VDP never sets 5S
        f5, n = vdpscreen.sprite_status(vram, regs, f=1)
        assert lines[0] == 96 and st and st[0] == 0x80 | f5 << 6 | n, out[TAG[m]]
    # first.rom: the ball first in the table; the last figure is the fifth
    out["first"] = {}
    for m in (EU, JP):
        regs, vram, photo, shot, st = still("first", m)
        last = gen27.FIRST[4]
        rows = SHAPE_ROWS[last[2]]
        lines = sorted({last[0] + 1 + j for j in range(16) for i in range(16)
                        if rows[j] & 0x8000 >> i and paper_px(photo, last[1] + i, last[0] + 1 + j) == BLACK})
        f5, n = vdpscreen.sprite_status(vram, regs, f=1)
        out["first"][TAG[m]] = {"seen": seen(photo, gen27.FIRST, SHAPE_ROWS), "last_lines": [lines[0], lines[-1]],
                                "status_peek": st, "model_status_f": [f5, n], "shot": shot}
        assert st and st[0] == 0x80 | f5 << 6 | n
    return out


# ---------------------------------------------------------------- stagger
def stagger():
    out = {}
    for m in (EU, JP):
        regs, vram, photo, shot, st = still("stagger", m)
        sn = seen(photo, gen27.STAGGER, SHAPE_ROWS)
        lines, end = vdpscreen.on_lines(vram, regs)
        f5, n = vdpscreen.sprite_status(vram, regs, f=1)
        out[TAG[m]] = {"seen": sn, "most_on_a_line": max(len(v) for v in lines.values()),
                       "status_peek": st, "model_status": list(vdpscreen.sprite_status(vram, regs)),
                       "model_status_f": [f5, n], "shot": shot}
        assert all(a == b for a, b in sn) and st and st[0] == 0x80 | f5 << 6 | n, out[TAG[m]]
    return out


# ---------------------------------------------------------------- status
def status():
    """the list of statuses, a frame each: the first group with no sprites,
    then the six states; each against rule 11 for the table of the frame"""
    s = sym("status")
    n = 8 * (len(gen27.STATES) + 1)
    out = {}
    for m in (EU, JP):
        w = run("status", 130, once(s["done"], f'binary scan [debug read_block memory {gen27.LOG} {n}] '
                                                'H* h; L "log $h"', "d"), m)
        log = list(bytes.fromhex(next(x for x in w if x[0] == "log")[1]))
        regs = [2, 0xE2, 6, 0xFF, 3, 0x36, 7, 0x0F]
        want = [0x80] * 8                    # no sprites: the table ends at sprite 0
        rows = []
        for what, table in gen27.STATES:
            five_s, number = vdpscreen.sprite_status(table_vram(table), regs)
            want += [0x80 | five_s << 6 | number] * 8
            rows.append({"what": what, "model": [five_s, number]})
        for k, r in enumerate(rows):
            got = sorted(set(log[8 * (k + 1):8 * (k + 2)]))
            r["status"] = got
        out[TAG[m]] = {"log": log, "states": rows, "right": sum(a == b for a, b in zip(log, want))}
        assert log == want, (m, log, want)
    # a photograph of each state, against the model
    films = {}
    for m in (EU, JP):
        w = run("status", 130, "".join(f'debug set_bp {s[f"e{k}"]} {{}} {{ L "e{k} {POS}" }}\n'
                                       for k in range(len(gen27.STATES))) + once(s["s0"], f'L "regs {REGS}"; {VRAM}', "v"), m)
        f0 = int(next(x for x in w if x[0] == "f0")[1])
        regs = [int(v) for v in next(x for x in w if x[0] == "regs")[1:]]
        base = bytearray(bytes.fromhex(next(x for x in w if x[0] == "vram")[1]))
        at = [int(next(x for x in w if x[0] == f"e{k}")[1]) - f0 + 2 for k in range(len(gen27.STATES))]
        pngs = msxcap.capture(rom("status"), at, CAPS, f"status_{TAG[m]}_f", machine=m)
        bad = []
        for k, (what, table) in enumerate(gen27.STATES):
            v = bytearray(base)
            b = gen27.table_bytes(table)
            v[gen27.ATT:gen27.ATT + len(b)] = bytes(b)
            bad.append(against(vdpscreen.draw(v, regs), codes(pngs[at[k]]), regs[7] & 15))
        films[TAG[m]] = {"frames": at, "bad": bad}
        assert not any(bad), (m, bad)
    out["photos"] = films
    return out


# ---------------------------------------------------------------- films
def film(name, machine, frames):
    """every send, m0 to m1: its frame and T-states; the table it left, read
    when the next send begins or at done; and the photograph of each, the
    frame after the send's (fitted over the whole film)"""
    s = sym(name)
    tcl = (f'debug set_bp {s["m0"]} {{}} {{ {ATTS}; L "a {POS}" }}\n'
           f'debug set_bp {s["m1"]} {{}} {{ L "b {POS}" }}\n' +
           once(s["m0"], f'L "regs {REGS}"; {VRAM}', "v") +
           once(s["done"], f'{ATTS}; L "end"', "e"))
    w = run(name, frames, tcl, machine)
    f0 = int(next(x for x in w if x[0] == "f0")[1])
    base = bytes.fromhex(next(x for x in w if x[0] == "vram")[1])
    a_s = [x for x in w if x[0] == "a"]
    b_s = [x for x in w if x[0] == "b"]
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
    films = sorted({f + d for f in frames_at for d in (0, 1, 2)})
    pngs = msxcap.capture(rom(name), films, CAPS, f"{name}_{TAG[machine]}_f", machine=machine)
    photos = {f: codes(pngs[f]) for f in films}
    fits = [d for d in (0, 1, 2)
            if all(against(vdpscreen.draw(v, r), photos[f + d], r[7] & 15) == 0
                   for (r, v), f in zip(states, frames_at))]
    assert 1 in fits, (name, machine, fits)    # the frame after the send's, as in chapter 26
    keep = {f + 1 for f in frames_at}
    for f in films:
        if f not in keep:
            pngs[f].unlink()
    return ({"frames": [f + 1 for f in frames_at], "fits": fits, "cost": cost,
             "lines": [int(a[2]) // vdpslots.LINE for a in a_s]},
            states, [photos[f + 1] for f in frames_at])


def shown(states, photos, table_of):
    """for each frame, the sprites of its table the photograph shows whole,
    by their place in the first table"""
    out = []
    for (r, v), ph in zip(states, photos):
        t = [tuple(v[gen27.ATT + 4 * i:gen27.ATT + 4 * i + 4]) for i in range(len(table_of))]
        got = seen(ph, t, SHAPE_ROWS)
        out.append(sorted(table_of.index(e) for e, (a, b) in zip(t, got) if a == b))
    return out


# ---------------------------------------------------------------- rotate
def rotate():
    want = gen27.rotate_tables()
    out = {}
    for m in (EU, JP):
        res, states, photos = film("rotate", m, 120)
        tables = [[tuple(v[gen27.ATT + 4 * i:gen27.ATT + 4 * i + 4]) for i in range(len(gen27.ROT))]
                  for _, v in states]
        assert tables == want[gen27.STILL_FRAMES:], m
        sh = shown(states, photos, gen27.ROT)
        model = [sorted(gen27.ROT.index(e) for e in t[:4]) for t in tables]
        assert sh == model, (m, sh[:4], model[:4])
        counts = [sum(1 for s in sh if k in s) for k in range(len(gen27.ROT))]
        assert res["frames"] == list(range(res["frames"][0], res["frames"][-1] + 1))
        out[TAG[m]] = {"sends": len(states), "cost": sorted(set(res["cost"])), "fits": res["fits"],
                       "lines": sorted(set(res["lines"])), "frames": [res["frames"][0], res["frames"][-1]],
                       "shown_per_figure": counts, "shown_first": sh[:4]}
    # the still frames before the first turned send: figures 0 to 3 only
    for m in (EU, JP):
        regs, vram, photo, shot, st = still_at("rotate", m, "still")
        out[TAG[m]]["still"] = {"seen": [a == b for a, b in seen(photo, gen27.ROT, SHAPE_ROWS)],
                                "shot": shot}
    return out


def still_at(name, machine, label):
    """the photograph two frames after LABEL is first reached, against the
    model of the VRAM then"""
    s = sym(name)
    w = run(name, 40, once(s[label], f'L "regs {REGS}"; {VRAM}; L "at {POS}"', "d"), machine)
    f0 = int(next(x for x in w if x[0] == "f0")[1])
    regs = [int(v) for v in next(x for x in w if x[0] == "regs")[1:]]
    vram = bytes.fromhex(next(x for x in w if x[0] == "vram")[1])
    shot = int(next(x for x in w if x[0] == "at")[1]) - f0 + 4
    png = msxcap.capture(rom(name), [shot], CAPS, f"{name}_{TAG[machine]}_f", machine=machine)[shot]
    photo = codes(png)
    assert against(vdpscreen.draw(vram, regs), photo, regs[7] & 15) == 0, (name, machine)
    return regs, vram, photo, shot, []


# ---------------------------------------------------------------- hero
def absent_runs(frames_shown, k):
    """the longest run of frames without K"""
    best = run_ = 0
    for sh in frames_shown:
        run_ = 0 if k in sh else run_ + 1
        best = max(best, run_)
    return best


def hero():
    want = gen27.hero_tables()
    table_of = [gen27.HERO] + gen27.FOES
    n = len(table_of)
    out = {}
    for m in (EU, JP):
        res, states, photos = film("hero", m, 110)
        assert res["frames"] == list(range(res["frames"][0], res["frames"][-1] + 1))
        tables = [[tuple(v[gen27.ATT + 4 * i:gen27.ATT + 4 * i + 4]) for i in range(n)]
                  for _, v in states]
        assert tables == want, m
        sh = shown(states, photos, table_of)
        assert sh == [sorted(table_of.index(e) for e in t[:4]) for t in tables], m
        phases = []
        for ph, step in enumerate(gen27.HERO_STEPS):
            part = sh[ph * gen27.HERO_FRAMES:(ph + 1) * gen27.HERO_FRAMES]
            phases.append({"step": step, "frames": len(part),
                           "shown_per_sprite": [sum(1 for x in part if k in x) for k in range(n)],
                           "longest_absent": [absent_runs(part, k) for k in range(n)],
                           "first": part[:len(gen27.FOES)]})
        out[TAG[m]] = {"phases": phases, "cost": sorted(set(res["cost"])), "fits": res["fits"],
                       "lines": sorted(set(res["lines"])), "film": [res["frames"][0], res["frames"][-1]]}
    return out


# ---------------------------------------------------------------- layers
def layers():
    out = {}
    t = gen27.layer_table()
    for m in (EU, JP):
        regs, vram, photo, shot, st = still("layers", m)
        sn = seen(photo, t, SHAPE_ROWS)
        faces = [[a == b for a, b in sn[2 * k:2 * k + 2]] for k in range(len(t) // 2)]
        f5, n = vdpscreen.sprite_status(vram, regs, f=1)
        out[TAG[m]] = {"faces": faces, "seen": sn, "status_peek": st,
                       "model_status": list(vdpscreen.sprite_status(vram, regs)),
                       "model_status_f": [f5, n], "shot": shot}
        assert faces == [[True, True]] * 2 + [[False, False]] + [[True, True]] * 2, faces
        assert st and st[0] == 0x80 | f5 << 6 | n, out[TAG[m]]
    return out


# ---------------------------------------------------------------- adaptive
def adaptive():
    out = {}
    for name, keep in (("poll", False), ("keep", True)):
        want = gen27.adaptive_tables(keep)
        res_m = {}
        for m in (EU, JP):
            res, states, photos = film(name, m, 120)
            tables = [[tuple(v[gen27.ATT + 4 * i:gen27.ATT + 4 * i + 4]) for i in range(len(gen27.SIX))]
                      for _, v in states]
            assert tables == want, (name, m)
            sh = shown(states, photos, gen27.SIX)
            assert sh == [sorted(gen27.SIX.index(e) for e in t[:4]) for t in tables], (name, m)
            s = sym(name)
            w = run(name, 120, once(s["done"], f'binary scan [debug read_block memory {gen27.LOG} '
                                                f'{2 * gen27.SIX_FRAMES}] H* h; L "log $h"', "d"), m)
            log = list(bytes.fromhex(next(x for x in w if x[0] == "log")[1]))
            found = log[0::2]
            ored = log[1::2]
            res_m[TAG[m]] = {"found_f": sorted(set(found[1:])), "ored": sorted(set(ored[1:])),
                             "first": [found[0], ored[0]],
                             "shown_per_figure": [sum(1 for s_ in sh if k in s_) for k in range(6)],
                             "frames": len(sh), "fits": res["fits"], "cost": sorted(set(res["cost"])),
                             "film": [res["frames"][0], res["frames"][-1]], "shown_first": sh[:4],
                             "lines": sorted(set(res["lines"]))}
            assert res["frames"] == list(range(res["frames"][0], res["frames"][-1] + 1))
        out[name] = res_m
    for t in ("eu", "jp"):
        assert out["poll"][t]["shown_per_figure"][4:] == [0, 0]
        assert min(out["keep"][t]["shown_per_figure"]) > 0
    return out


# ---------------------------------------------------------------- once
def once_tables():
    """the table each send of once.asm leaves: turned by SIX_TURN entries more
    after a frame whose table, by rule 11, leaves 5S"""
    regs = [2, 0xE2, 6, 0xFF, 3, 0x36, 7, 0x0F]
    n, k, shown_ = len(gen27.SIX), 0, gen27.SIX
    out = []
    for entries in (gen27.SIX, gen27.SIX2):
        for _ in range(gen27.ONCE_FRAMES):
            if vdpscreen.sprite_status(table_vram(shown_), regs)[0]:
                k = (k + gen27.SIX_TURN) % n
            shown_ = [entries[(k + i) % n] for i in range(n)]
            out.append(shown_)
    return out


def once_a_frame():
    want = once_tables()
    n, fr = len(gen27.SIX), gen27.ONCE_FRAMES
    xs = [x for _, x, _, _ in gen27.SIX]
    s = sym("once")
    out = {}
    for m in (EU, JP):
        res, states, photos = film("once", m, 120)
        assert res["frames"] == list(range(res["frames"][0], res["frames"][-1] + 1))
        tables = [[tuple(v[gen27.ATT + 4 * i:gen27.ATT + 4 * i + 4]) for i in range(n)] for _, v in states]
        assert tables == want, m
        sh = []
        for t, ph in zip(tables, photos):
            sh.append(sorted(xs.index(e[1]) for e, (a, b) in zip(t, seen(ph, t, SHAPE_ROWS)) if a == b))
        model = []
        for t in tables:               # rule 10: whole if among the first four on all its lines
            lines, _ = vdpscreen.on_lines(table_vram(t), [2, 0xE2, 6, 0xFF, 3, 0x36, 7, 0x0F])
            model.append(sorted(xs.index(t[i][1]) for i in range(n)
                                if all(i in v[:4] for v in lines.values() if i in v)))
        assert sh == model, (m, sh[:3], model[:3])
        w = run("once", 120, f'debug set_bp {s["m0"]} {{}} {{ L "st [debug read memory {s["status"]}]" }}\n', m)
        st = [int(x[1]) for x in w if x[0] == "st"]
        assert len(st) == 2 * fr
        ks = [0] + [xs.index(t[0][1]) for t in tables]      # k before each send, and after
        phases = []
        for ph in range(2):
            part = slice(ph * fr, (ph + 1) * fr)
            turned = [a != b for a, b in zip(ks, ks[1:])][part]
            phases.append({"with_5s": sum(1 for v in st[part] if v & 0x40), "turns": sum(turned),
                           "statuses": sorted(set(st[part])),
                           "shown_per_figure": [sum(1 for x in sh[part] if k in x) for k in range(n)]})
        out[TAG[m]] = {"phases": phases, "cost": sorted(set(res["cost"])), "fits": res["fits"],
                       "film": [res["frames"][0], res["frames"][-1]]}
    return out


# ---------------------------------------------------------------- reads
def reads():
    """every read of one of poll.rom's waits, the fifth: its value, and the
    line of the paper it came on (counted from the paper's first line of the
    frame whose F it found), against rule 10's lines with five sprites"""
    s = sym("poll")
    regs = [2, 0xC2, 6, 0xFF, 3, 0x36, 7, 0x0F]
    on = vdpscreen.on_lines(table_vram(gen27.SIX), regs)[0]
    lines5 = sorted(k for k, v in on.items() if len(v) > 4)
    out = {}
    for m in (EU, JP):
        tcl = ('set ::n 0\nset ::on 0\n'
               f'debug set_bp {s["m0"]} {{}} {{ incr ::n; set ::on [expr {{$::n == 4}}] }}\n'
               'debug set_watchpoint read_io 0x99 {$::on} '
               '{ L "io [machine_info VDP_frame_count] [machine_info VDP_cycle_in_frame]" }\n'
               f'debug set_bp {s["wait"] + 2} {{$::on}} {{ L "rd [reg a]" }}\n')
        w = run("poll", 30, tcl, m)
        io = [x for x in w if x[0] == "io"]
        rd = [x for x in w if x[0] == "rd"]
        assert len(io) == len(rd) > 0
        f_found = int(io[-1][1])
        runs = []
        at = [((int(a[1]) - f_found) * vdpslots.LINES[m] - vdpslots.PAPER0[m]) * vdpslots.LINE + int(a[2])
              for a in io]                  # VDP cycles from the start of the paper's line 0
        vals = [int(b[1]) for b in rd]
        # when the VDP changed the status: between a read and the next that differs,
        # in cycles from the start of the later read's line
        won = [-10 ** 6, 10 ** 6]
        num_ = [-10 ** 6, 10 ** 6]
        for i in range(1, len(at)):
            start = at[i] // vdpslots.LINE * vdpslots.LINE
            if vals[i] & 0x40 and not vals[i - 1] & 0x40:
                won = [max(won[0], at[i - 1] - start), min(won[1], at[i] - start)]
            if vals[i] & 31 != vals[i - 1] & 31:
                num_ = [max(num_[0], at[i - 1] - start), min(num_[1], at[i] - start)]
        for a, b in zip(io, rd):
            line = ((int(a[1]) - f_found) * vdpslots.LINES[m] + int(a[2]) // vdpslots.LINE
                    - vdpslots.PAPER0[m])
            v = int(b[1])
            if runs and runs[-1][0] == v:
                runs[-1][2] = line
                runs[-1][3] += 1
            else:
                runs.append([v, line, line, 1])
        with5 = [r for r in runs if r[0] & 0x40]
        assert all(r[1] == r[2] and r[3] == 1 for r in with5)      # one read a line
        assert [r[1] for r in with5] == lines5, (m, with5)
        assert runs[-1][0] == 0x86 and runs[-1][3] == 1 and runs[-1][1] == 192
        assert won[0] < 0 <= won[1] and num_[0] < 0 <= num_[1]
        out[TAG[m]] = {"reads": len(io), "runs": runs, "with_5s": len(with5),
                       "lines_5s": [with5[0][1], with5[-1][1]], "first_line": runs[0][1],
                       "set_5s_window": won, "number_window": num_}
    return out


# ---------------------------------------------------------------- prices
def walker(name, status=0xC0):
    """the listing walked, every read of the status port finding STATUS"""
    return walk.Walk(HERE / name, read_port=lambda port, t: status if port == 0x99 else 0)


def prices():
    """each send, m0 to m1, priced from the listing: rotate's, and three frames
    of poll's and keep's, the status found as the films found it"""
    m = json.loads((HERE / "meas27.json").read_text())
    out = {}
    wk = walker("rotate")
    wk.run("init", "m0")
    out["rotate_send"] = [wk.run("m0", "m1")]
    for name, st in (("poll", 0x86), ("keep", 0xC6)):
        wk = walker(name, st)
        wk.run("init", "m0")
        costs = []
        for _ in range(3):
            costs.append(wk.run("m0", "m1"))
            wk.run("m1", "m0")
        out[f"{name}_send"] = sorted(set(costs))
    wk = walker("hero")
    wk.run("init", "m0")
    out["hero_send"] = [wk.run("m0", "m1")]
    wk = walker("once")
    out["once_send"] = [wk.run("m0", "m1")]
    for t in ("eu", "jp"):
        assert m["hero"][t]["cost"] == out["hero_send"]
        assert m["once"][t]["cost"] == out["once_send"]
        assert m["rotate"][t]["cost"] == out["rotate_send"]
        assert m["adaptive"]["poll"][t]["cost"] == out["poll_send"]
        assert m["adaptive"]["keep"][t]["cost"] == out["keep_send"], (m["adaptive"]["keep"][t]["cost"], out)
    return out


# ---------------------------------------------------------------- answers
def answers():
    out = {}
    regs = [2, 0xE2, 6, 0xFF, 3, 0x36, 7, 0x0F]
    # 1: seven sprites, 0 to 6, on one line: the status at the end of the frame
    t = gen27.row(99, [8 + 34 * k for k in range(7)], "block")
    f, n = vdpscreen.sprite_status(table_vram(t), regs)
    out["q1"] = 0x80 | f << 6 | n
    # 2: ten figures on a line, the table turned by four a frame: how often each
    lines = 10
    shown_ = [0] * lines
    for f_ in range(lines):
        k = (4 * f_) % lines
        for i in range(4):
            shown_[(k + i) % lines] += 1
    out["q2"] = shown_
    # 3: a ship of two sprites, 0 and 1, and three enemies, 2 to 4, on lines 120 to 135
    t = ([(119, 40, gen27.SHAPES["face"], gen27.BLACK), (119, 40, gen27.SHAPES["fill"], gen27.LIGHT_GREEN)]
         + gen27.row(119, [80, 120, 160], "figure"))
    lines, _ = vdpscreen.on_lines(table_vram(t), regs)
    f, n = vdpscreen.sprite_status(table_vram(t), regs)
    out["q3"] = {"left_out": sorted({i for v in lines.values() for i in v[4:]}), "status": 0x80 | f << 6 | n}
    return out


# ---------------------------------------------------------------- openmsx
OPENMSX_SECTIONS = ["five", "stagger", "status", "rotate", "hero", "layers", "adaptive", "once", "reads"]


def openmsx():
    if not versions.builds():
        return {"skipped": "OPENMSX_BUILDS not set"}
    return versions.every_build(["ch27"], OPENMSX_SECTIONS)


SECTIONS = {"five": five, "stagger": stagger, "status": status, "rotate": rotate, "hero": hero, "layers": layers,
            "adaptive": adaptive, "once": once_a_frame, "reads": reads, "prices": prices, "answers": answers,
            "openmsx": openmsx}


def main(names=()):
    CAPS.mkdir(exist_ok=True)
    path = HERE / "meas27.json"
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
