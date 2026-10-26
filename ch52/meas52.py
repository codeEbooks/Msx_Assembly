#!/usr/bin/env python3
"""meas52.py -- chapter 42's frame, made faster piece by piece, measured.

    python3 gen52.py && ./build.sh && python3 meas52.py
                                  python3 meas52.py films prices   only these

  films     ch42/over.rom and the six programs here for 900 frames on both
            machines, as meas42.py watches them: the debugger stops at the
            interrupt routine and where it gives the interrupts back, at the
            four R#7 marks and at each bump, and reads the RAM (and patch.rom's
            code in the RAM) at the first mark, the attributes, the status
            line, the patterns and R#2 after the sends, both name tables at the
            last mark. Every stretch of every loop is held against walk.py, run
            on the RAM the debugger read; every loop's game against chapter
            42's model of it (inrom.rom against the same model with the
            directions that never change); the frames lost against the signals
  photos    the frame each program shows after the loop over.rom loses its
            first frame in, at 60 Hz, and inrom.rom and patch.rom when every
            ball of inrom.rom is in its corner: each against vdpscreen.py's
            picture of the model's VRAM in a border coloured where each write
            of R#7 shows (figures 52.1 and 52.2)
  prices    what each routine costs in each program, from walk.py; the bytes
            of each cartridge; the copy patch.rom's INIT makes
  count     every program with 9 to 31 balls for 900 frames at 60 Hz: the
            frames each loses, and its longest loop
  voices    the loop of figure 52.1 in each program, item by item
  monitor   patch.rom and inrom.rom: the byte of each direction a bounce
            rewrites, before and after, read by the debugger
  machines  ch42/over.rom and patch.rom on the 22 machines of chapter 51
  answers   the workshop, tried (for Appendix I)
  openmsx   all of it again with every other build (tools/versions.py)
"""
import atexit
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "tools"))
import meas        # noqa: E402
import msxcap      # noqa: E402
import probe as dbg  # noqa: E402
import versions    # noqa: E402
sys.path.insert(0, str(HERE))
import gen52       # noqa: E402
gen42 = gen52.gen42
import meas42      # noqa: E402  (chapter 42's model of the game, and its photographs' model)
for mod in ("vdpscreen", "walk"):
    sys.modules.pop(mod, None)
while str(HERE) in sys.path:
    sys.path.remove(str(HERE))
sys.path.insert(0, str(HERE))
import vdpscreen   # noqa: E402
import walk        # noqa: E402
assert Path(vdpscreen.__file__).parent == HERE and Path(walk.__file__).parent == HERE

CAPS = HERE / "captures"
EU, JP = gen42.EU, gen42.JP
MACHINES = gen42.MACHINES
TAG = {EU: "eu", JP: "jp"}
FT, FLAG_LINE, PAPER0, L = meas42.FT, meas42.FLAG_LINE, meas42.PAPER0, meas42.L
SIGNAL, ANSWER, BACK, POS = meas42.SIGNAL, meas42.ANSWER, meas42.BACK, meas42.POS
TO_PAPER = {m: (PAPER0[m] + (FT[m] // L) - FLAG_LINE[m]) * L - SIGNAL for m in MACHINES}
MARKS = meas42.MARKS
NAMES = ["over"] + gen52.VERSIONS + [gen52.BROKEN]     # over is chapter 42's
SHOWN = ["over"] + gen52.VERSIONS                       # figure 52.1
LEVEL = gen52.LEVEL
ENGINE = (0xC100, 256)
GAME = (gen42.GAME, 0x110)
PAGE = (0xC600, 256)
FRAMES = gen42.FRAMES
F0 = meas42.F0
STATE = meas42.STATE
TOO_FAST = meas42.TOO_FAST
MOST = gen52.MOST


def stem(name):
    return REPO / "ch42" / "over" if name == "over" else HERE / name


def sym_of(st):
    return dbg.sym(Path(st).with_suffix(".sym"))


def num(f):
    return meas42.num(f)


def run(st, machine, frames, tcl):
    lines = msxcap.run_tcl(Path(st).with_suffix(".rom"), frames, F0 + TOO_FAST + tcl, machine=machine,
                           tcl_setup=STATE, timeout=3600)
    return [l.split() for l in lines]


# ---------------------------------------------------------------- the model
class Game(meas42.Game):
    """chapter 42's game with N balls, from gen52's places (the first 24 are
    chapter 42's)"""

    def __init__(self, n=gen52.NBALLS):
        super().__init__("over", n=n)
        self.balls = [list(b) for b in gen52.START[:n]]

    def copy(self):
        out = []
        for k, b in enumerate(self.balls):
            out += [b[1] & 255, b[0] & 255, 0, gen52.COLOURS[k]]
        return bytes(out + [0xD0])


class Stuck(Game):
    """inrom.rom's game: move's code is in the cartridge, so no direction a
    bounce or a bump writes is kept. A ball past an edge is put back by a step
    the other way, and goes on its old way the next frame; two that bump keep
    coming together"""

    def move(self):
        self.at = (self.at + 1) & 511
        for b in self.balls:
            x = (b[0] + b[2]) & 255
            if x > gen42.XMAX:
                x = (b[0] - b[2]) & 255
            b[0] = x
            y = (b[1] + b[3]) & 255
            if y < gen42.YMIN or y > gen42.YMAX:
                y = (b[1] - b[3]) & 255
            b[1] = y

    def tests(self):
        for i in range(self.n - 1):
            for j in range(i + 1, self.n):
                a, b = self.balls[i], self.balls[j]
                dx, dy = meas42.signed(b[0] - a[0]), meas42.signed(b[1] - a[1])
                if not (-15 <= dx <= 15 and -15 <= dy <= 15):
                    continue
                if not gen42.gen39.pixels_meet(gen42.BALL, gen42.BALL, dx, dy):
                    continue
                self.calls += 1
                part = 0
                for r, v in ((dx, b[2] - a[2]), (dy, b[3] - a[3])):
                    if v > 0:
                        part += r
                    elif v < 0:
                        part -= r
                if part >= 0:
                    continue
                self.score = meas42.bcd_add(self.score, 0x10)
                if self.score > self.hi:
                    self.hi = list(self.score)
                self.seed = gen42.gen41.xorshift(self.seed)
                self.bumps.append((self.loop, i, j, (self.seed >> 8) & 3))


def model(name, n=gen52.NBALLS):
    return Stuck(n) if name == gen52.BROKEN else Game(n)


def code_block(s):
    """patch.rom's move in the RAM: where it is and how long"""
    return (gen52.MOVES, s["moved"] - s["moving"])


def blocks_of(name, s):
    """the RAM the debugger reads at the first mark: (tag, address, bytes)"""
    out = [("e",) + ENGINE, ("g",) + GAME]
    if 1 <= LEVEL[name] <= 4:
        out.append(("p",) + PAGE)
    if name == "patch":
        out.append(("c",) + code_block(s))
    return out


def ram_state(name, s, blk, n, rom=None):
    """the game's state as the RAM keeps it, from the blocks the debugger
    read: the shape of meas42.Game.ram()"""
    g, base = blk["g"], GAME[0]
    level = LEVEL[name]

    def at(label, k=1):
        a = s[label] - base
        return g[a] if k == 1 else list(g[a:a + k])

    def word(label):
        return at(label) | g[s[label] - base + 1] << 8
    if level == 0:
        b0 = s["balls"] - base
        balls = [list(g[b0 + 4 * k:b0 + 4 * k + 4]) for k in range(n)]
    elif level < 4:
        balls = [list(blk["p"][4 * k:4 * k + 4]) for k in range(n)]
    else:
        c0 = s["copy"] - base
        if level == 4:
            dirs = [(blk["p"][2 * k], blk["p"][2 * k + 1]) for k in range(n)]
        else:
            def opcode(label):
                a = s[label]
                if name == "patch":
                    return blk["c"][a - gen52.MOVES]
                return rom[a - 0x4000]
            way = {gen52.INC_A: 1, gen52.DEC_A: 255}
            dirs = [(way[opcode(f"move.dx{k}")], way[opcode(f"move.dy{k}")]) for k in range(n)]
        balls = [[g[c0 + 4 * k + 1], g[c0 + 4 * k], dirs[k][0], dirs[k][1]] for k in range(n)]
    return {"at": word("at"), "col": at("col"), "table": at("table"), "need": at("need"),
            "score": at("score", 3), "hi": at("hi", 3), "seed": word("seed"), "balls": balls}


# ---------------------------------------------------------------- walk
def walker(st, rate):
    """walk.py on a program, its ports answering as meas42.walker's do"""
    wk = walk.Walk(st)

    def read_port(port, t):
        if port == 0xA9:
            return 0xFF                     # no key down
        if port == 0xA2:                    # the PSG's register chosen last
            last = [v for _, p, v in wk.ports if p == 0xA0]
            reg = last[-1] if last else 0
            return {14: 0xBF, 15: 0x8F}.get(reg, 0)
        if port == 0xAA:
            return 0x50                     # port C as C-BIOS leaves it
        return 0x80                         # the VDP's status: F
    wk.read_port = read_port
    wk.mem[0x2B] = rate
    return wk


def walk_from(wk, blocks, start, stop):
    for addr, data in blocks:
        wk.mem[addr:addr + len(data)] = data
    wk.ports.clear()
    return wk.run(start, stop)


# ---------------------------------------------------------------- the films
def film(name, machine, frames=FRAMES, st=None, n=None, light=False):
    """the debugger's log of a film; ST and N for a variant, LIGHT without
    the RAM and the VRAM"""
    st = st or stem(name)
    s = sym_of(st)
    n = n or gen52.NBALLS
    if light:
        tcl = "".join(f'debug set_bp {s[k]} {{}} {{ L "{k} {POS}" }}\n'
                      for k in ("isr", "m0", "m1", "m2", "m3", "bump"))
        tcl += f'debug set_bp {s["isrend"]} {{}} {{ L "ie {POS}" }}\n'
    else:
        reads = "; ".join(f"M {t} {a} {k}" for t, a, k in blocks_of(name, s))
        tcl = (f'debug set_bp {s["isr"]} {{}} {{ L "isr {POS}"; M e {ENGINE[0]} {ENGINE[1]} }}\n'
               f'debug set_bp {s["isrend"]} {{}} {{ L "ie {POS}" }}\n'
               f'debug set_bp {s["m0"]} {{}} {{ L "m0 {POS}"; {reads} }}\n'
               f'debug set_bp {s["m1"]} {{}} {{ L "m1 {POS}"; VR sat {gen42.SAT} {4 * n + 1}; '
               f'VR st0 {gen42.TABLES[0] + 32 * gen42.STATUS_ROW} 32; '
               f'VR st1 {gen42.TABLES[1] + 32 * gen42.STATUS_ROW} 32; VR pat 0 {gen42.NB}; '
               f'L "r2 [debug read {{VDP regs}} 2]" }}\n'
               f'debug set_bp {s["m2"]} {{}} {{ L "m2 {POS}" }}\n'
               f'debug set_bp {s["m3"]} {{}} {{ L "m3 {POS}"; VR n0 {gen42.TABLES[0]} {32 * gen42.ROWS}; '
               f'VR n1 {gen42.TABLES[1]} {32 * gen42.ROWS} }}\n'
               f'debug set_bp {s["bump"]} {{}} {{ L "bump {POS}" }}\n')
    w = run(st, machine, frames, tcl)
    f0 = int(next(x for x in w if x[0] == "f0")[1])
    fast = [x for x in w if x[0] == "fast"]
    ev, pend = [], {}
    for x in w:
        k = x[0]
        if k in ("isr", "ie", "m0", "m1", "m2", "m3", "bump"):
            f, c = meas42.t_abs(x[1], x[2])
            e = {"kind": k, "frame": f, "t": f * FT[machine] + c if machine in FT else None,
                 "cycle": (f, c)}
            ev.append(e)
            pend = e
        elif len(x) == 3 and x[1] in ("mem", "vram"):
            pend[x[0]] = bytes.fromhex(x[2])
        elif k == "r2":
            pend["r2"] = int(x[1])
    return f0, ev, s, len(fast)


def signal_of(frame, machine):
    return frame * FT[machine] + FLAG_LINE[machine] * L + SIGNAL


def tail_of(st):
    """T-states from the last mark to the HALT: the same in every program"""
    return walker(st, 0).run("m3", "frame")


def loops_of(ev, tail):
    """the films cut into loops, as meas42.loops_of"""
    marks = [i for i, e in enumerate(ev) if e["kind"] == "m0"]
    loops = []
    for a, b in zip(marks, marks[1:] + [len(ev)]):
        seg = ev[a:b]
        kinds = [e["kind"] for e in seg]
        if "m3" not in kinds:
            continue
        before = [e for e in ev[:a] if e["kind"] in ("isr", "ie")][-2:]
        wake, wake_end = before
        assert wake["kind"] == "isr" and wake_end["kind"] == "ie"
        m3 = next(e for e in seg if e["kind"] == "m3")
        halt = m3["t"] + tail
        inside = []
        for e in [e for e in seg if e["kind"] == "isr"]:
            if e["t"] < halt:
                end = next(x for x in seg if x["kind"] == "ie" and x["t"] > e["t"])
                inside.append((e, end))
        loops.append({"m0": seg[0], "m1": next(e for e in seg if e["kind"] == "m1"),
                      "m2": next(e for e in seg if e["kind"] == "m2"), "m3": m3,
                      "wake": wake, "wake_end": wake_end, "inside": inside, "halt": halt,
                      "bumps": [e for e in seg if e["kind"] == "bump"]})
    return loops


ANALYSED = {}


def analyse(name, machine):
    """every loop of the film against walk.py and the model, as meas42.analyse"""
    if (name, machine) in ANALYSED:
        return ANALYSED[(name, machine)]
    st = stem(name)
    f0, ev, s, fast = film(name, machine)
    assert fast == 0, (name, machine, "an access too soon")
    tail = tail_of(st)
    loops = loops_of(ev, tail)
    rate = 0x80 if machine == EU else 0
    wk = walker(st, rate)
    rom = Path(st).with_suffix(".rom").read_bytes()
    game = model(name)
    blocks = blocks_of(name, s)
    rows, sent, states = [], [], []
    prev_frame = None
    for k, lp in enumerate(loops):
        m0, m1, m2, m3 = lp["m0"], lp["m1"], lp["m2"], lp["m3"]
        wake_frame = lp["wake"]["frame"]
        sig = signal_of(wake_frame, machine)
        assert sig <= lp["wake"]["t"] < sig + 40, (name, machine, k)
        counted = 1 if prev_frame is None else wake_frame - prev_frame
        got = ram_state(name, s, m0, game.n, rom)
        game.loop = k
        want = game.ram()
        assert got == want, (name, machine, k, got, want)
        states.append(want)
        game.show()
        assert m1["sat"] == game.copy(), (name, machine, k, "sat")
        digits = [gen42.DIGIT0 + d for b in game.score for d in (b >> 4, b & 15)]
        hdigits = [gen42.DIGIT0 + d for b in game.hi for d in (b >> 4, b & 15)]
        for t in ("st0", "st1"):
            row = list(m1[t])
            assert row[gen42.SCORE_AT % 32:gen42.SCORE_AT % 32 + 6] == digits, (name, machine, k, t)
            assert row[gen42.HI_AT % 32:gen42.HI_AT % 32 + 6] == hdigits, (name, machine, k, t)
        assert m1["pat"] == bytes(gen42.shapes_at(game.at & 7)), (name, machine, k, "patterns")
        assert m1["r2"] == (6 if game.shown_table == 0x18 else 7), (name, machine, k, "R#2")
        sent.append((m1["t"], {"at": game.at, "col": game.col, "table": game.shown_table,
                               "copy": game.copy(), "score": list(game.score), "hi": list(game.hi)}))
        t_walk = walk_from(wk, [(a, m0[t]) for t, a, _ in blocks], "m0", "m3")
        isr_inside = sum(ANSWER + (end["t"] - e["t"]) + BACK for e, end in lp["inside"])
        took = m3["t"] - m0["t"]
        assert took == t_walk + isr_inside, (name, machine, k, took, t_walk, isr_inside)
        for e, end in [(lp["wake"], lp["wake_end"])] + lp["inside"]:
            ti = walk_from(wk, [(ENGINE[0], e["e"])], "isr", "isrend")
            assert ti == end["t"] - e["t"], (name, machine, k, ti, end["t"] - e["t"])
        calls0, scored0 = game.calls, len(game.bumps)
        game.logic(counted)
        assert game.calls - calls0 == len(lp["bumps"]), (name, machine, k, "bumps")
        scored = len(game.bumps) - scored0
        wrows = game.window_rows(counted)
        shown = m3["n0" if game.shown_table == 0x18 else "n1"]
        hidden = m3["n1" if game.shown_table == 0x18 else "n0"]
        assert list(shown) == meas42.window_names(game.col), (name, machine, k, "the table shown")
        done = 32 * (gen42.ROWS - game.need)
        assert list(hidden[:done]) == meas42.window_names(game.wsrc_col)[:done], (name, machine, k, "next")
        nxt = loops[k + 1]["wake"]["frame"] if k + 1 < len(loops) else None
        rows.append({
            "loop": k, "frame": wake_frame - f0, "counted": counted,
            "wake": num(lp["wake"]["t"] - sig),
            "isr": num(lp["wake_end"]["t"] - lp["wake"]["t"] + BACK),
            "sends": num(m1["t"] - m0["t"]), "logic": num(m2["t"] - m1["t"]),
            "window": num(m3["t"] - m2["t"]), "rows": wrows,
            "m0": num(m0["t"] - sig), "m1": num(m1["t"] - sig), "m2": num(m2["t"] - sig),
            "m3": num(m3["t"] - sig), "halt": num(lp["halt"] - sig),
            "inside": [num(e["t"] - sig) for e, _ in lp["inside"]],
            "bumps": len(lp["bumps"]), "scored": scored,
            "lost": None if nxt is None else nxt - wake_frame - 1,
        })
        prev_frame = wake_frame
    res = {"f0": f0, "rows": rows, "tail": tail, "ev": ev, "loops": loops, "game": game,
           "sent": sent, "states": states, "s": s}
    ANALYSED[(name, machine)] = res
    return res


def summary(res, machine):
    out = meas42.summary(res, machine)
    out["score"] = "".join(f"{b:02X}" for b in res["game"].score)
    return out


def films():
    out = {}
    for name in NAMES:
        out[name] = {}
        for m in MACHINES:
            res = analyse(name, m)
            out[name][TAG[m]] = {"summary": summary(res, m), "rows": res["rows"], "f0": res["f0"],
                                 "tail": res["tail"]}
            print(name, TAG[m], out[name][TAG[m]]["summary"], flush=True)
    # the game is the same in every program that loses no frame
    for m in MACHINES:
        ref = None
        for name in gen52.VERSIONS:
            res = ANALYSED[(name, m)]
            if out[name][TAG[m]]["summary"]["lost"]:
                continue
            if ref is None:
                ref = res["states"]
            assert res["states"] == ref, (name, m)
        out["same_game_" + TAG[m]] = len(ref)
    return out


# ---------------------------------------------------------------- the photos
def frame_models(res, machine, frames):
    """as meas42.frame_models, with this folder's vdpscreen"""
    writes = [(e["t"] + 8, MARKS[e["kind"]]) for e in res["ev"] if e["kind"] in MARKS]
    out = {}
    for c in frames:
        start = c * FT[machine] + PAPER0[machine] * L
        done = [st for t, st in res["sent"] if t < start]
        paper = vdpscreen.draw(meas42.vram_of(done[-1]), meas42.regs_of(done[-1]))
        out[c] = (meas42.capture_model(paper, writes, c, machine), done[-1])
    return out


def photo(name, machine, res, frame, keep_as):
    """the capture of FRAME (counted from INIT) against its model; the
    debugger's frames and the captures' may differ by one, so the three
    around it are taken and exactly one must fit"""
    f0 = res["f0"]
    models = frame_models(res, machine, [f0 + frame])
    tmp = Path(tempfile.mkdtemp(prefix="ph52_"))
    shots = [frame - 1, frame, frame + 1]
    pngs = msxcap.capture(stem(name).with_suffix(".rom"), shots, tmp, "f", machine=machine, timeout=1800)
    fits = [d for d in (-1, 0, 1) if meas42.mismatch(models[f0 + frame][0], meas42.codes(pngs[frame + d])) == 0]
    assert len(fits) == 1, (name, machine, frame, [(d, meas42.mismatch(models[f0 + frame][0],
                                                                       meas42.codes(pngs[frame + d])))
                                                   for d in (-1, 0, 1)])
    CAPS.mkdir(exist_ok=True)
    dest = CAPS / f"{keep_as}.png"
    shutil.copy(pngs[frame + fits[0]], dest)
    shutil.rmtree(tmp)
    st = models[f0 + frame][1]
    return {"png": dest.name, "offset": fits[0], "at": st["at"], "col": st["col"]}


def band_loop():
    """the loop over.rom loses its first frame in, at 60 Hz"""
    return next(r["loop"] for r in analyse("over", JP)["rows"] if r["lost"])


def settled(state):
    """every ball of inrom.rom pressed into a corner of the sky"""
    xs = (0, 1, gen42.XMAX - 1, gen42.XMAX)
    ys = (gen42.YMIN, gen42.YMIN + 1, gen42.YMAX - 1, gen42.YMAX)
    return all(b[0] in xs and b[1] in ys for b in state["balls"])


def photos():
    out = {"bands": {}, "corners": {}}
    k = band_loop()
    for name in SHOWN:
        res = analyse(name, JP)
        row = res["rows"][k]
        out["bands"][name] = dict(photo(name, JP, res, row["frame"] + 1, f"bands_{name}"),
                                  loop=k, woke=row["frame"], halt=row["halt"], m1=row["m1"],
                                  m2=row["m2"], m3=row["m3"], rows=row["rows"])
        print("bands", name, out["bands"][name], flush=True)
    res = analyse(gen52.BROKEN, JP)
    first = next(i for i, st in enumerate(res["states"]) if settled(st))
    assert all(settled(st) for st in res["states"][first:])
    frame = res["rows"][first]["frame"] + 1
    out["corners"]["settled_loop"] = first
    out["corners"]["frame"] = frame
    piles = {}
    for b in res["states"][first]["balls"]:
        key = ("left" if b[0] < 128 else "right") + (" top" if b[1] < 64 else " bottom")
        piles[key] = piles.get(key, 0) + 1
    out["corners"]["piles"] = piles
    scores = [st["score"] for st in res["states"]]
    out["corners"]["last_score_loop"] = max(k for k in range(1, len(scores)) if scores[k] != scores[k - 1])
    out["corners"]["final_score"] = "".join(f"{b:02X}" for b in scores[-1])
    reached = []
    for k in range(gen52.NBALLS):
        reached.append(next(i for i, st in enumerate(res["states"])
                            if all(settled({"balls": [s2["balls"][k]]}) for s2 in res["states"][i:])))
    out["corners"]["reached"] = reached
    for name in (gen52.BROKEN, "patch"):
        r = analyse(name, JP)
        out["corners"][name] = photo(name, JP, r, frame, f"corners_{name}")
        out["corners"][name]["score"] = "".join(f"{b:02X}" for b in r["sent"][first][1]["score"])
    print("corners", out["corners"], flush=True)
    return out


# ---------------------------------------------------------------- prices
def fresh(st, machine=JP):
    wk = walker(st, 0x80 if machine == EU else 0)
    wk.run("init", "main")
    return wk


def init_price(st):
    wk = walker(st, 0)
    return wk.run("init", "main")


def place(wk, name, k, x, y):
    """ball K at X, Y, where the program keeps its place"""
    s = wk.sym
    if LEVEL[name] == 0:
        a = s["balls"] + 4 * k
        wk.mem[a], wk.mem[a + 1] = x, y
    elif LEVEL[name] < 4:
        a = s["balls"] + 4 * k
        wk.mem[a], wk.mem[a + 1] = x, y
    else:
        a = s["copy"] + 4 * k
        wk.mem[a], wk.mem[a + 1] = y, x


def balls_far(wk, name, n, y=50):
    """N balls in a row, 24 pixels apart, far from the edges: no two boxes
    meet, and no ball bounces, whichever way it goes"""
    assert n <= 10
    for k in range(n):
        place(wk, name, k, 16 + 24 * k, y)


def balls_mid(wk, name, n, y=50):
    """N balls away from the sky's edges, for move alone: none bounces"""
    for k in range(n):
        place(wk, name, k, 16 + (208 * k) // max(1, n - 1), y)


def code_end(st):
    """the cartridge's first byte not used, from the listing"""
    for line in Path(st).with_suffix(".lst").read_text().splitlines():
        if "ASSERT $ <= $8000" in line:
            return int(line.split()[1], 16)
    raise ValueError(st)


def variant(name, n):
    """the program NAME with N balls, assembled in a folder of its own; its
    stem, or None if it does not fit in the cartridge"""
    d = Path(tempfile.mkdtemp(prefix="v52_"))
    atexit.register(shutil.rmtree, d, True)
    for f in ("msx.inc", "bios.inc", "music.inc"):
        shutil.copy(HERE / f, d / f)
    st = f"{name}_{n}"
    (d / f"{st}.asm").write_text(gen52.program(name, n).replace(f'OUTPUT "{name}.rom"', f'OUTPUT "{st}.rom"'))
    r = subprocess.run(["sjasmplus", "--nologo", "--msg=err", "--syntax=bFw", f"--sym={st}.sym",
                        f"--lst={st}.lst", f"{st}.asm"], cwd=d, capture_output=True, text=True)
    if r.returncode:
        assert "longer than the cartridge" in r.stdout + r.stderr, r.stdout + r.stderr
        return None
    return d / st


def prices():
    out = {}
    for name in NAMES:
        st = stem(name)
        level = LEVEL[name]
        wk = fresh(st)
        p = {"init": init_price(st), "end": code_end(st), "free": 0x8000 - code_end(st)}
        p["show"] = []
        for at in range(8):
            wk.mem[wk.sym["at"]], wk.mem[wk.sym["at"] + 1], wk.mem[wk.sym["col"]] = at, 0, 0
            p["show"].append(wk.call("show"))
        wk.mem[wk.sym["at"]], wk.mem[wk.sym["at"] + 1], wk.mem[wk.sym["col"]] = 8, 0, 0
        p["show_flip"] = wk.call("show")
        p["sprites"] = fresh(st).call("sprites")
        p["input"] = fresh(st).call("input")
        w2 = fresh(st)
        balls_far(w2, name, gen52.NBALLS)
        p["move"] = w2.call("move")
        balls_far(w2, name, gen52.NBALLS)
        p["tests"] = w2.call("tests")
        if level < 4:
            p["build"] = w2.call("build")
        wb = fresh(st)
        wb.mem[wb.sym["need"]] = gen42.ROWS
        p["nextwin"] = wb.call("nextwin")
        if name == "patch":
            p["copy_bytes"] = wk.sym["moved"] - wk.sym["moving"]
            p["copy"] = 23 * p["copy_bytes"] - 5
        sy = wk.sym
        p["bytes"] = {"tests": sy["near" if level >= 2 else "bump"] - sy["tests"],
                      "move": sy["tests"] - sy["moving" if name == "patch" else "move"],
                      "sends": sy["putbcd"] - sy["show"]}
        out[name] = p
        print(name, p, flush=True)
    # a ball and a pair more: the programs with 8 and 10 balls
    for name in gen52.VERSIONS + [gen52.BROKEN]:
        per = {}
        for n in (8, 10):
            st = variant(name, n)
            w2 = fresh(st)
            balls_far(w2, name, n)
            mv = w2.call("move")
            balls_far(w2, name, n)
            sy = w2.sym
            per[n] = (mv, w2.call("tests"), sy["near" if LEVEL[name] >= 2 else "bump"] - sy["tests"])
        out[name]["move_ball"] = (per[10][0] - per[8][0]) / 2
        out[name]["tests_10"], out[name]["tests_8"] = per[10][1], per[8][1]
        out[name]["tests_bytes_10"], out[name]["tests_bytes_8"] = per[10][2], per[8][2]
    # the parts that do not change: the same in every program
    out["same"] = {k: sorted({out[n][k] for n in NAMES}) for k in ("input",)}
    # bump, two balls coming together and two parting: chapter 42's (tests.rom),
    # moves.rom's and patch.rom's
    for name in ("tests", "moves", "patch"):
        got = []
        for d0, d1 in ((1, 255), (255, 1)):
            w2 = fresh(stem(name))
            balls_far(w2, name, gen52.NBALLS)
            place(w2, name, 0, 100, 50)
            place(w2, name, 1, 110, 50)
            if LEVEL[name] < 4:
                for k, d in ((0, d0), (1, d1)):
                    a = w2.sym["balls"] + 4 * k
                    w2.mem[a + 2], w2.mem[a + 3] = d, 1
                w2.ix = w2.sym["balls"]
                b = w2.sym["balls"] + 4
                got.append(w2.call("bump", h=b >> 8, l=b & 255))
            else:
                for k, d in ((0, d0), (1, d1)):
                    if LEVEL[name] == 4:
                        a = w2.sym["dirs"] + 2 * k
                        w2.mem[a], w2.mem[a + 1] = d, 1
                    else:
                        w2.mem[w2.sym[f"move.dx{k}"]] = gen52.INC_A if d == 1 else gen52.DEC_A
                        w2.mem[w2.sym[f"move.dy{k}"]] = gen52.INC_A
                got.append(w2.call("bump", d=0, e=1))
        out[name]["bump_taken"], out[name]["bump_parting"] = got
    return out


# ---------------------------------------------------------------- how many balls
def lost_frames(st, machine, n, frames=FRAMES):
    """the frames a program loses and its longest loop, from a light film"""
    f0, ev, s, fast = film(None, machine, frames=frames, st=st, n=n, light=True)
    tail = tail_of(st)
    lost, longest = 0, 0
    marks = [e for e in ev if e["kind"] in ("isr", "m3")]
    wake = None
    loops = 0
    for e in marks:
        if e["kind"] == "isr":
            if wake is None:
                wake = e
        else:
            halt = e["t"] + tail
            sig = signal_of(wake["frame"], machine)
            longest = max(longest, halt - sig)
            loops += 1
            nxt = [x for x in marks if x["kind"] == "isr" and x["t"] > e["t"]]
            if nxt and nxt[0]["frame"] > wake["frame"] + 1:
                lost += nxt[0]["frame"] - wake["frame"] - 1
            wake = nxt[0] if nxt else None
    return {"lost": lost, "longest": num(longest), "loops": loops, "fast": fast}


def count():
    out = {"over": {}}
    for nm, n in (("budget", 8), ("over", 9)):
        out["over"][n] = lost_frames(REPO / "ch42" / nm, JP, n)
    for name in gen52.VERSIONS:
        out[name] = {}
        for n in range(gen52.NBALLS, MOST + 1):
            st = variant(name, n)
            out[name][n] = lost_frames(st, JP, n) if st else None
            if st:
                out[name][n]["end"] = code_end(st)
            print("count", name, n, out[name][n], flush=True)
    most = {}
    for name in out:
        k = gen52.NBALLS - 1 if name == "over" else gen52.NBALLS
        while k + 1 in out[name] and out[name][k + 1] and out[name][k + 1]["lost"] == 0:
            k += 1
        most[name] = k
    out["most"] = most
    return out


# ---------------------------------------------------------------- voices
def voices_of(name, machine, res, k):
    lp, row = res["loops"][k], res["rows"][k]
    st = stem(name)
    wk = walker(st, 0x80 if machine == EU else 0)
    for t, a, _ in blocks_of(name, res["s"]):
        wk.mem[a:a + len(lp["m0"][t])] = lp["m0"][t]
    calls = ["show", "sprites", "status", "input", "move", "tests"] + \
        (["build"] if LEVEL[name] < 4 else []) + ["nextwin"]
    sites = {}
    for line in Path(st).with_suffix(".lst").read_text().splitlines():
        mt = dbg.LST.match(line)
        if not mt or "..." in mt.group(3)[1:13] or not mt.group(3)[1:13].strip():
            continue
        _, a, c, src = dbg.lst_fields(mt)
        code = src.split(";")[0].split()
        if len(code) == 2 and code[0] == "call" and code[1] in calls and code[1] not in sites:
            sites[code[1]] = a
    assert set(sites) == set(calls), sites

    def to(addr):
        t0 = wk.t
        while wk.pc != addr:
            wk.step()
        return wk.t - t0
    wk.pc = wk.sym["m0"]
    v = {"wake": row["wake"], "isr": row["isr"], "marks": num(row["m0"] - row["wake"] - row["isr"])}
    v["marks"] += to(sites["show"])
    v["show"] = to(sites["sprites"])
    v["sprites"] = to(sites["status"])
    v["status"] = to(sites["status"] + 3)
    v["marks"] += to(sites["input"])
    v["input"] = to(sites["input"] + 3)
    v["count"] = to(sites["move"] - 1)
    v["moves"] = to(sites["tests"])
    if "build" in sites:
        v["tests"] = to(sites["build"])
        v["build"] = to(sites["build"] + 3)
    else:
        v["tests"] = to(sites["tests"] + 3)
        v["build"] = 0
    v["marks"] += to(sites["nextwin"])
    v["nextwin"] = to(sites["nextwin"] + 3)
    v["marks"] += to(wk.sym["m3"]) + res["tail"]
    v["inside"] = num(sum(ANSWER + (end["t"] - e["t"]) + BACK for e, end in lp["inside"]))
    parts = ("wake", "isr", "marks", "show", "sprites", "status", "input", "count", "moves",
             "tests", "build", "nextwin", "inside")
    assert num(sum(v[x] for x in parts)) == row["halt"], (name, machine, k, v, row["halt"])
    v.update(frame=row["frame"], loop=k, bumps=row["bumps"], counted=row["counted"], halt=row["halt"])
    return v


def voices():
    out = {}
    k = band_loop()
    for name in SHOWN:
        out[name] = voices_of(name, JP, analyse(name, JP), k)
        print("voices", name, out[name], flush=True)
    # and the longest loop of moves.rom and patch.rom at 60 Hz
    for name in ("moves", "patch"):
        res = analyse(name, JP)
        kk = max(res["rows"][1:], key=lambda r: r["halt"])["loop"]
        out["longest_" + name] = voices_of(name, JP, res, kk)
        print("voices longest", name, out["longest_" + name], flush=True)
    return out


# ---------------------------------------------------------------- the monitor
def monitor():
    """each time turn rewrites a direction: the byte there before and after,
    read by the debugger, in the first 300 frames"""
    out = {}
    for name in ("patch", gen52.BROKEN):
        st = stem(name)
        s = sym_of(st)
        after = s["turn"] + 5                   # LD B,A, LD A,(HL), XOR 1, LD (HL),A: the next
        assert walk.Walk(st).code.get(after) == bytes([0x0F])   # RRCA
        tcl = (f'debug set_bp {s["turn"]} {{}} {{ L "before {POS} [reg hl] [peek [reg hl]]" }}\n'
               f'debug set_bp {after} {{}} {{ L "after {POS} [reg hl] [peek [reg hl]]" }}\n')
        w = run(st, JP, 300, tcl)
        f0 = int(next(x for x in w if x[0] == "f0")[1])
        rows = []
        for x in w:
            if x[0] == "before":
                rows.append({"frame": int(x[1]) - f0, "at": int(x[3]), "before": int(x[4])})
            elif x[0] == "after":
                assert rows[-1]["at"] == int(x[3])
                rows[-1]["after"] = int(x[4])
        label = {v: k for k, v in s.items() if k.startswith("move.d")}
        for r in rows:
            r["label"] = label[r["at"]]
        out[name] = rows[:12]
        out[name + "_turns"] = len(rows)
        out[name + "_changed"] = sum(1 for r in rows if r["before"] != r["after"])
    return out


# ---------------------------------------------------------------- the 22 machines
BOOK = ["MSXBOOK_EU16", "MSXBOOK_JP16", "MSXBOOK_EU8", "MSXBOOK_EU32", "MSXBOOK_EU64",
        "MSXBOOK_EU16AY", "MSXBOOK_EU16X", "MSXBOOK_EU16E", "MSXBOOK_EU16G", "MSXBOOK_EU16P"]
STOCK = [f"C-BIOS_{v}{r}" for v in ("MSX1", "MSX2", "MSX2+") for r in ("", "_EU", "_JP", "_BR")]
ALL = BOOK + STOCK
STOCK_FROM = Path(os.environ.get("MEAS51_STOCK_MACHINES", "/usr/share/openmsx/machines"))


def machines_folder():
    """the book's machines and openMSX's twelve C-BIOS ones, in a folder
    msxcap uses (chapter 51)"""
    d = Path(tempfile.mkdtemp(prefix="machines52_"))
    atexit.register(shutil.rmtree, d, True)
    for xml in sorted((REPO / "machines").glob("*.xml")):
        shutil.copy(xml, d)
    for name in STOCK:
        shutil.copy(STOCK_FROM / f"{name}.xml", d)
    os.environ["MSXCAP_MACHINES"] = str(d)
    msxcap.MACHINES = d
    return d


def on_machine(st, machine, frames=FRAMES):
    """a light film on any machine: the loops, the frames lost between the
    wakes, and the longest loop from the start of the interrupt routine that
    woke it to its HALT. The machine's frame is 313 or 262 lines of 228
    T-states, as bit 7 of its BIOS's $002B says (chapter 51)"""
    s = sym_of(st)
    tcl = 'L "rate [peek 0x2B]"\n' + "".join(f'debug set_bp {s[k]} {{}} {{ L "{k} {POS}" }}\n'
                                            for k in ("isr", "m3"))
    w = run(st, machine, frames, tcl)
    ft = 313 * L if int(next(x for x in w if x[0] == "rate")[1]) & 0x80 else 262 * L
    fast = sum(1 for x in w if x[0] == "fast")
    ev = [(x[0], int(x[1]), int(x[1]) * ft + int(x[2]) / 6) for x in w if x[0] in ("isr", "m3")]
    if not any(k == "m3" for k, _, _ in ev):
        return {"loops": 0, "hz": 50 if ft == 313 * L else 60, "fast": fast}
    tail = tail_of(st)
    lost, longest, loops, wake = 0, 0, 0, None
    for k, f, t in ev:
        if k == "isr":
            if wake is None:
                wake = (f, t)
        else:
            loops += 1
            longest = max(longest, t + tail - wake[1])
            nxt = next(((f2, t2) for k2, f2, t2 in ev if k2 == "isr" and t2 > t), None)
            if nxt and nxt[0] > wake[0] + 1:
                lost += nxt[0] - wake[0] - 1
            wake = nxt
    return {"loops": loops, "lost": lost, "longest": num(longest), "hz": 50 if ft == 313 * L else 60,
            "fast": fast}


def machines():
    machines_folder()
    out = {}
    for name in ("over", "patch"):
        out[name] = {}
        for m in ALL:
            out[name][m] = on_machine(stem(name), m)
            print("machines", name, m, out[name][m], flush=True)
    return out


# ---------------------------------------------------------------- the workshop
def answers():
    m = json.loads((HERE / "meas52.json").read_text())
    pr, fl, cn = m["prices"], m["films"], m["count"]
    out = {}
    # 1: at 50 Hz, how many balls fit in moves.rom and patch.rom
    q1 = {}
    for name in ("moves", "patch"):
        q1[name] = {}
        for n in range(cn["most"][name], MOST + 1):
            st = variant(name, n)
            q1[name][n] = lost_frames(st, EU, n)
            print("q1", name, n, q1[name][n], flush=True)
    out["q1"] = q1
    # 2: patch.rom with the window spread, chapter 42's three rows a frame, at 60 Hz
    q2 = {}
    for n in range(cn["most"]["patch"], MOST + 1):
        d = Path(tempfile.mkdtemp(prefix="s52_"))
        atexit.register(shutil.rmtree, d, True)
        for f in ("msx.inc", "bios.inc", "music.inc"):
            shutil.copy(HERE / f, d / f)
        st = f"spread_{n}"
        (d / f"{st}.asm").write_text(gen52.program("patch", n, spread=True).replace(
            'OUTPUT "patch.rom"', f'OUTPUT "{st}.rom"'))
        subprocess.run(["sjasmplus", "--nologo", "--msg=err", "--syntax=bFw", f"--sym={st}.sym",
                        f"--lst={st}.lst", f"{st}.asm"], cwd=d, check=True)
        q2[n] = lost_frames(d / st, JP, n)
        print("q2", n, q2[n], flush=True)
    out["q2"] = q2
    # 3: a direction as INC A and DEC A, as ADD A,n, and as moves.rom keeps it
    sys.path.insert(0, str(REPO / "ch14"))
    import cycles
    t = {"inc a": cycles.msx([0x3C]), "add a,n": cycles.msx([0xC6, 1]),
         "add a,(hl)": cycles.msx([0x86]), "inc l": cycles.msx([0x2C])}
    out["q3"] = {"prices": t, "moves_axis": t["add a,(hl)"] + t["inc l"],
                 "gain_inc": 2 * (t["add a,(hl)"] + t["inc l"] - t["inc a"]),
                 "gain_add": 2 * (t["add a,(hl)"] + t["inc l"] - t["add a,n"]),
                 "measured": pr["moves"]["move_ball"] - pr["patch"]["move_ball"]}
    # 4: with the most balls patch.rom keeps at 60 Hz: its copy, and when it has paid for itself
    n = cn["most"]["patch"]
    st_p, st_m = variant("patch", n), variant("moves", n)
    w_p, w_m = fresh(st_p), fresh(st_m)
    balls_mid(w_p, "patch", n)
    balls_mid(w_m, "moves", n)
    mp, mm = w_p.call("move"), w_m.call("move")
    nbytes = w_p.sym["moved"] - w_p.sym["moving"]
    out["q4"] = {"balls": n, "bytes": nbytes, "copy": 23 * nbytes - 5, "move_patch": mp, "move_moves": mm,
                 "gain": mm - mp, "frames": -(-(23 * nbytes - 5) // (mm - mp)),
                 "init_patch": init_price(st_p), "init_moves": init_price(st_m)}
    # 5: the names the border still has room for after the sends, at 60 Hz
    se = fl["patch"]["jp"]["summary"]["sends_end"]
    out["q5"] = {"sends_end": se, "to_paper": num(TO_PAPER[JP]), "names": int((TO_PAPER[JP] - se) // 18)}
    print("answers", out, flush=True)
    return out


def openmsx():
    """every section again with every build, in two runs of meas52.py: each run
    in versions.rerun() must end within its time limit"""
    if not versions.builds():
        return {"skipped": "OPENMSX_BUILDS not set"}
    out = {}
    for part in OPENMSX_SECTIONS:
        for label, r in versions.every_build(["ch52"], part).items():
            o = out.setdefault(label, {"values": 0, "same_values": 0, "captures": 0,
                                       "same_captures": 0, "same_in_drawn": 0, "failed": [],
                                       "different": []})
            for k in ("values", "same_values", "failed", "different"):
                o[k] += r[k]
            for k in ("captures", "same_captures", "same_in_drawn"):
                o[k] = max(o[k], r[k])          # the captures are compared in each part
            o["version"], o["sha256"] = r["version"], r["sha256"]
    return out


OPENMSX_SECTIONS = [["films", "prices", "count", "answers"], ["photos", "voices", "monitor", "machines"]]
SECTIONS = {"films": films, "photos": photos, "prices": prices, "count": count, "voices": voices,
            "monitor": monitor, "machines": machines, "answers": answers, "openmsx": openmsx}


def main(names=()):
    CAPS.mkdir(exist_ok=True)
    path_ = HERE / "meas52.json"
    m = json.loads(path_.read_text()) if names and path_.exists() else {}
    for name in names or SECTIONS:
        print(name, flush=True)
        m[name] = SECTIONS[name]()
        m = {k: m[k] for k in SECTIONS if k in m}
        path_.write_text(json.dumps(m, indent=1) + "\n")
    return m


if __name__ == "__main__":
    main(sys.argv[1:])
