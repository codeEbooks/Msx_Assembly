#!/usr/bin/env python3
"""meas42.py -- the frame budget, measured.

    python3 gen42.py && ./build.sh && python3 meas42.py
                                  python3 meas42.py films prices   only these

  films     budget.rom, over.rom and spread.rom for 900 frames on both
            machines. The debugger stops at the interrupt routine and where
            it gives the interrupts back, at each of the four R#7 marks and
            at each bump; it reads the RAM at the routine and at the first
            mark, and after the sends the attributes, the status line of
            both name tables, the patterns of the pairs and R#2. Every
            stretch of every loop is held against walk.py, run on the RAM
            the debugger read; every loop's game against the model in this
            file; the frames lost against the signals
  photos    frames of each film photographed, each against vdpscreen.py's
            picture of the VRAM the model gives, in a border coloured where
            chapter 18 puts each write of R#7 (figures 42.1 to 42.3)
  prices    what each routine costs, from walk.py, on the paths that matter
  voices    the longest loops item by item: walk.py from the RAM the
            debugger read at the first mark, each CALL to the next
  answers   the workshop, tried (for Appendix I)
  openmsx   all of it again with every other build (tools/versions.py)
"""
import json
import math
import shutil
import subprocess
import sys
import tempfile
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
import gen42       # noqa: E402
sys.path.remove(str(HERE))
sys.path.insert(0, str(HERE))      # gen42 put other chapters first: this folder's files win
for mod in ("vdpscreen", "walk"):
    sys.modules.pop(mod, None)
import vdpscreen   # noqa: E402
import walk        # noqa: E402

assert Path(vdpscreen.__file__).parent == HERE and Path(walk.__file__).parent == HERE

CAPS = HERE / "captures"
SHOTS = HERE / "shots"
EU, JP = gen42.EU, gen42.JP
MACHINES = gen42.MACHINES
TAG = {EU: "eu", JP: "jp"}
L = 228
FT = {EU: 71364, JP: 59736}
FLAG_LINE = {EU: 261, JP: 234}
PAPER0 = {EU: 69, JP: 42}                   # the paper's first line in the VDP's frame (chapter 33)
SIGNAL = Fraction(101, 3)                   # F rises at T-state 33 2/3 of its line (chapter 19)
ANSWER = 19 + 11                            # mode 2's answer and the JP (chapter 17)
BACK = 5 + 11                               # isr's EI and RET, after isrend
POS = "[machine_info VDP_frame_count] [machine_info VDP_cycle_in_frame]"
PROGRAMS = gen42.PROGRAMS
MARKS = {"m0": gen42.DARK_BLUE, "m1": gen42.LIGHT_GREEN, "m2": gen42.BLACK, "m3": gen42.WHITE}
ENGINE = (0xC100, 256)
GAME = (gen42.GAME, 0x110)
PALETTE = [tuple(c) for c in json.loads((REPO / "ch01" / "meas01.json").read_text())["palette"]["rgb"]]
CODE = {rgb: n for n, rgb in enumerate(PALETTE) if n}
REGS0 = [0x02, 0xE2, 0x06, 0x9F, 0x00, 0x36, 0x07, 0x0F]

STATE = r"""
proc M {tag addr n} {
    binary scan [debug read_block memory $addr $n] H* h
    L "$tag mem $h"
}
proc VR {tag addr n} {
    binary scan [debug read_block VRAM $addr $n] H* h
    L "$tag vram $h"
}
"""
TOO_FAST = ('proc ::toofast_cb {args} { L "fast [machine_info VDP_frame_count] '
            '[machine_info VDP_cycle_in_frame]" }\n'
            'set VDP.too_fast_vram_access_callback ::toofast_cb\n')
F0 = 'L "f0 [machine_info VDP_frame_count]"\n'


def rom(name):
    return HERE / f"{name}.rom"


def sym(name):
    return dbg.sym(HERE / f"{name}.sym")


def t_abs(fc, cyc):
    return int(fc), Fraction(int(cyc), 6)


def num(f):
    return int(f) if f == int(f) else round(float(f), 2)


def run(name, machine, frames, tcl, path=None):
    lines = msxcap.run_tcl(path or rom(name), frames, F0 + TOO_FAST + tcl, machine=machine,
                           tcl_setup=STATE, timeout=3600)
    return [l.split() for l in lines]


def codes(png):
    im = Image.open(png).convert("RGB")
    px = im.load()
    return [[CODE.get(px[x, y]) for x in range(im.width)] for y in range(im.height)]


# ---------------------------------------------------------------- the model of the game
def bcd_add(num_, points):
    """three BCD bytes plus POINTS, two BCD digits, the carry lost at the top"""
    v = int("".join(f"{b:02X}" for b in num_)) + int(f"{points:02X}")
    v %= 10 ** 6
    s = f"{v:06d}"
    return [int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)]


def signed(v):
    v &= 255
    return v - 256 if v & 128 else v


class Game:
    """the game of budget.asm, over.asm and spread.asm as gen42.py writes it:
    the balls, the scroll, the score, random's state; the sounds are left to
    chapter 37"""

    def __init__(self, name, n=None, chunk=None):
        self.n = n or gen42.BALLS[name]
        self.chunk = chunk or gen42.CHUNK
        self.spread = name == "spread"
        self.balls = [list(b) for b in gen42.START_ALL[:self.n]]
        self.at, self.col, self.table, self.need = 0, 0, 0x1C, 0
        self.shown_table = 0x18
        self.wsrc_col = 1                       # INIT wrote window 1 into the table not shown
        self.score, self.hi = [0, 0, 0], list(gen42.HI0)
        self.seed = 1
        self.bumps = []                         # (loop, i, j, effect)
        self.calls = 0                          # bump's calls: pairs that touch
        self.loop = 0

    # the sends: what show leaves, at the start of a loop
    def show(self):
        c = (self.at >> 3) & 63
        if c != self.col:
            self.col = c
            self.shown_table = self.table
            self.table ^= 0x18 ^ 0x1C
            self.need = gen42.ROWS
            self.wsrc_col = (c + 1) & 63

    def move(self):
        self.at = (self.at + 1) & 511
        for b in self.balls:
            x = (b[0] + b[2]) & 255
            if x > gen42.XMAX:
                b[2] = -b[2]
                x = (b[0] + b[2]) & 255
            b[0] = x
            y = (b[1] + b[3]) & 255
            if y < gen42.YMIN or y > gen42.YMAX:
                b[3] = -b[3]
                y = (b[1] + b[3]) & 255
            b[1] = y

    def tests(self):
        for i in range(self.n - 1):
            for j in range(i + 1, self.n):
                a, b = self.balls[i], self.balls[j]
                dx, dy = signed(b[0] - a[0]), signed(b[1] - a[1])
                if not (-15 <= dx <= 15 and -15 <= dy <= 15):
                    continue
                if not gen42.gen39.pixels_meet(gen42.BALL, gen42.BALL, dx, dy):
                    continue
                self.calls += 1                 # bump is called
                part = 0
                for r, v in ((dx, b[2] - a[2]), (dy, b[3] - a[3])):
                    if v > 0:
                        part += r
                    elif v < 0:
                        part -= r
                if part >= 0:
                    continue                    # they part already
                b[2], b[3], a[2], a[3] = -b[2], -b[3], -a[2], -a[3]
                self.score = bcd_add(self.score, 0x10)
                if self.score > self.hi:
                    self.hi = list(self.score)
                self.seed = gen42.gen41.xorshift(self.seed)
                self.bumps.append((self.loop, i, j, (self.seed >> 8) & 3))

    def logic(self, counted):
        for _ in range(counted):
            self.move()
        self.tests()

    def window_rows(self, counted):
        """rows of the next window nextwin writes in this loop"""
        if self.need == 0:
            return 0
        rows = self.need if not self.spread else min(self.need, self.chunk * counted)
        self.need -= rows
        return rows

    def ram(self):
        """the game's state as the RAM keeps it"""
        out = {"at": self.at, "col": self.col, "table": self.table, "need": self.need,
               "score": self.score, "hi": self.hi, "seed": self.seed,
               "balls": [[b[0] & 255, b[1] & 255, b[2] & 255, b[3] & 255] for b in self.balls]}
        return out

    def copy(self):
        out = []
        for k, b in enumerate(self.balls):
            out += [b[1] & 255, b[0] & 255, 0, gen42.COLOURS[k]]
        return bytes(out + [0xD0])


def window_names(col):
    """the 672 names of the window whose first column is COL"""
    return [gen42.PMAP[r][(col + c) % gen42.WIDTH] for r in range(gen42.ROWS) for c in range(32)]


def ram_state(s, g, n):
    """the same, read from the game's RAM the debugger logged"""
    base = gen42.GAME

    def at(label, k=1):
        a = s[label] - base
        return g[a] if k == 1 else list(g[a:a + k])

    def word(label):
        return at(label) | g[s[label] - base + 1] << 8
    b0 = s["balls"] - base
    return {"at": word("at"), "col": at("col"), "table": at("table"), "need": at("need"),
            "score": at("score", 3), "hi": at("hi", 3), "seed": word("seed"),
            "balls": [list(g[b0 + 4 * k:b0 + 4 * k + 4]) for k in range(n)]}


# ---------------------------------------------------------------- walk
def walker(name, rate):
    wk = walk.Walk(HERE / name)
    psg = {"reg": 0}

    def read_port(port, t):
        if port == 0xA9:
            return 0xFF                     # no key down
        if port == 0xA2:                    # the PSG's register chosen last
            last = [v for _, p, v in wk.ports if p == 0xA0]
            psg["reg"] = last[-1] if last else 0
            return {14: 0xBF, 15: 0x8F}.get(psg["reg"], 0)
        if port == 0xAA:
            return 0x50                     # port C as C-BIOS leaves it
        return 0x80                         # the VDP's status: F
    wk.read_port = read_port
    wk.mem[0x2B] = rate
    return wk


def walk_from(wk, mem_blocks, start, stop):
    for addr, data in mem_blocks:
        wk.mem[addr:addr + len(data)] = data
    wk.ports.clear()
    return wk.run(start, stop)


# ---------------------------------------------------------------- the films
def film(name, machine, frames=gen42.FRAMES, path=None, n=None, light=False):
    """the debugger's log of a film; PATH and N for a variant, LIGHT without
    the RAM and the VRAM"""
    s = dbg.sym(path.with_suffix(".sym")) if path else sym(name)
    n = n or gen42.BALLS[name]
    if light:
        tcl = "".join(f'debug set_bp {s[k]} {{}} {{ L "{k} {POS}" }}\n'
                      for k in ("isr", "isrend", "m0", "m1", "m2", "m3", "bump"))
        tcl = tcl.replace('isrend {}', 'isrend {}').replace('L "isrend', 'L "ie')
    else:
        tcl = (f'debug set_bp {s["isr"]} {{}} {{ L "isr {POS}"; M e {ENGINE[0]} {ENGINE[1]} }}\n'
               f'debug set_bp {s["isrend"]} {{}} {{ L "ie {POS}" }}\n'
               f'debug set_bp {s["m0"]} {{}} {{ L "m0 {POS}"; M e {ENGINE[0]} {ENGINE[1]}; '
               f'M g {GAME[0]} {GAME[1]} }}\n'
               f'debug set_bp {s["m1"]} {{}} {{ L "m1 {POS}"; VR sat {gen42.SAT} {4 * n + 1}; '
               f'VR st0 {gen42.TABLES[0] + 32 * gen42.STATUS_ROW} 32; '
               f'VR st1 {gen42.TABLES[1] + 32 * gen42.STATUS_ROW} 32; VR pat 0 {gen42.NB}; '
               f'L "r2 [debug read {{VDP regs}} 2]" }}\n'
               f'debug set_bp {s["m2"]} {{}} {{ L "m2 {POS}" }}\n'
               f'debug set_bp {s["m3"]} {{}} {{ L "m3 {POS}"; VR n0 {gen42.TABLES[0]} {32 * gen42.ROWS}; '
               f'VR n1 {gen42.TABLES[1]} {32 * gen42.ROWS} }}\n'
               f'debug set_bp {s["bump"]} {{}} {{ L "bump {POS}" }}\n')
    w = run(name, machine, frames, tcl, path=path.with_suffix(".rom") if path else None)
    f0 = int(next(x for x in w if x[0] == "f0")[1])
    assert not [x for x in w if x[0] == "fast"], (name, machine, "an access too soon")
    ev, pend = [], {}
    for x in w:
        k = x[0]
        if k in ("isr", "ie", "m0", "m1", "m2", "m3", "bump"):
            f, c = t_abs(x[1], x[2])
            e = {"kind": k, "frame": f, "t": f * FT[machine] + c}
            ev.append(e)
            pend = e
        elif len(x) == 3 and x[1] in ("mem", "vram"):
            pend[x[0]] = bytes.fromhex(x[2])
        elif k == "r2":
            pend["r2"] = int(x[1])
    return f0, ev, s


def signal_of(frame, machine):
    return frame * FT[machine] + FLAG_LINE[machine] * L + SIGNAL


def loops_of(ev, s, machine, name):
    """the films cut into loops, each from the m0 after its HALT's interrupt
    to the HALT after its m3: the interrupt that woke it, those inside it,
    its marks and bumps"""
    wk = walker(name, 0x80 if machine == EU else 0)
    tail = wk.run("m3", "frame")                    # from the last mark to HALT
    marks = [i for i, e in enumerate(ev) if e["kind"] == "m0"]
    loops = []
    for a, b in zip(marks, marks[1:] + [len(ev)]):
        m0 = ev[a]
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
        isrs = [e for e in seg if e["kind"] == "isr"]
        for e in isrs:
            if e["t"] < halt:
                end = next(x for x in seg if x["kind"] == "ie" and x["t"] > e["t"])
                inside.append((e, end))
        loops.append({"m0": m0, "m1": next(e for e in seg if e["kind"] == "m1"),
                      "m2": next(e for e in seg if e["kind"] == "m2"), "m3": m3,
                      "wake": wake, "wake_end": wake_end, "inside": inside, "halt": halt,
                      "bumps": [e for e in seg if e["kind"] == "bump"]})
    return loops, tail


def analyse(name, machine):
    f0, ev, s = film(name, machine)
    loops, tail = loops_of(ev, s, machine, name)
    rate = 0x80 if machine == EU else 0
    wk = walker(name, rate)
    game = Game(name)
    rows, sent = [], []
    prev_frame = None
    for k, lp in enumerate(loops):
        m0, m1, m2, m3 = lp["m0"], lp["m1"], lp["m2"], lp["m3"]
        wake_frame = lp["wake"]["frame"]
        sig = signal_of(wake_frame, machine)
        assert sig <= lp["wake"]["t"] < sig + 40, (name, machine, k)
        counted = 1 if prev_frame is None else wake_frame - prev_frame
        # the game: the state at m0 is the model's
        got = ram_state(s, m0["g"], game.n)
        game.loop = k
        want = game.ram()
        assert got == want, (name, machine, k, got, want)
        game.show()
        # the sends: what the sprites, the status line and the patterns are after them
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
        # walk.py: the loop from m0 to m3, on the RAM the debugger read there
        t_walk = walk_from(wk, [(ENGINE[0], m0["e"]), (GAME[0], m0["g"])], "m0", "m3")
        isr_inside = 0
        for e, end in lp["inside"]:
            isr_inside += ANSWER + (end["t"] - e["t"]) + BACK
        took = m3["t"] - m0["t"]
        assert took == t_walk + isr_inside, (name, machine, k, took, t_walk, isr_inside)
        # walk.py: each interrupt routine, on the RAM read at its start
        for e, end in [(lp["wake"], lp["wake_end"])] + lp["inside"]:
            ti = walk_from(wk, [(ENGINE[0], e["e"])], "isr", "isrend")
            assert ti == end["t"] - e["t"], (name, machine, k, ti, end["t"] - e["t"])
        # the game moves on: the logic, and the rows of the next window
        calls0, scored0 = game.calls, len(game.bumps)
        game.logic(counted)
        assert game.calls - calls0 == len(lp["bumps"]), (name, machine, k, "bumps")
        scored = len(game.bumps) - scored0
        wrows = game.window_rows(counted)
        # the names after the window: the table shown is the window of the
        # column shown, and the rows written so far of the other are the next
        shown = m3["n0" if game.shown_table == 0x18 else "n1"]
        hidden = m3["n1" if game.shown_table == 0x18 else "n0"]
        assert list(shown) == window_names(game.col), (name, machine, k, "the table shown")
        done = 32 * (gen42.ROWS - game.need)
        assert list(hidden[:done]) == window_names(game.wsrc_col)[:done], (name, machine, k, "the next")
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
    # the bumps the debugger saw are the model's
    assert sum(r["bumps"] for r in rows) >= 0
    return {"f0": f0, "rows": rows, "tail": tail, "ev": ev, "loops": loops, "game": game, "sent": sent}


def summary(res, machine):
    rows = res["rows"][1:]          # the first loop starts from INIT's state
    lost = [r for r in rows if r["lost"]]
    out = {"loops": len(rows), "lost": sum(r["lost"] for r in rows if r["lost"]),
           "lost_loops": [r["loop"] for r in lost],
           "isr": [min(r["isr"] for r in rows), max(r["isr"] for r in rows)],
           "sends": [min(r["sends"] for r in rows), max(r["sends"] for r in rows)],
           "logic": [min(r["logic"] for r in rows), max(r["logic"] for r in rows)],
           "window": sorted({r["window"] for r in rows})[:1] + [max(r["window"] for r in rows)],
           "longest": max(r["halt"] for r in rows),
           "margin": FT[machine] - max(r["halt"] for r in rows),
           "sends_end": max(r["m1"] for r in rows),
           "bumps": sum(r["bumps"] for r in rows), "scored": sum(r["scored"] for r in rows)}
    return out


def films():
    out = {}
    for name in PROGRAMS:
        out[name] = {}
        for m in MACHINES:
            res = analyse(name, m)
            out[name][TAG[m]] = {"summary": summary(res, m),
                                 "rows": res["rows"],
                                 "f0": res["f0"], "tail": res["tail"]}
            print(name, TAG[m], out[name][TAG[m]]["summary"], flush=True)
    return out


# ---------------------------------------------------------------- the photos
def vram_of(st):
    """the VRAM a frame shows after sends that left ST: the pairs at the
    shift, the window of the column in the table shown, the status line, the
    balls"""
    v = bytearray(16384)
    pat = gen42.shapes_at(st["at"] & 7)
    v[0:len(pat)] = bytes(pat)
    cols = [b for a, b2 in gen42.PAIRS for b in gen42.gen29.pair_colours(a, b2)]
    v[0x2000:0x2000 + len(cols)] = bytes(cols)
    for k, ch in enumerate(gen42.LETTERS):
        n = gen42.LETTER0 + k
        v[8 * n:8 * n + 8] = bytes(gen42.glyph(ch))
        v[0x2000 + 8 * n:0x2000 + 8 * n + 8] = bytes([gen42.TEXT_C] * 8)
    for d in range(10):
        n = gen42.DIGIT0 + d
        v[8 * n:8 * n + 8] = bytes(gen42.glyph(str(d)))
        v[0x2000 + 8 * n:0x2000 + 8 * n + 8] = bytes([gen42.TEXT_C] * 8)
    names = []
    for r in range(gen42.ROWS):
        names += [gen42.PMAP[r][(st["col"] + c) % gen42.WIDTH] for c in range(32)]
    names += gen42.status_names(st["score"], st["hi"])
    base = st["table"] << 8
    v[base:base + 768] = bytes(names)
    v[gen42.SAT:gen42.SAT + len(st["copy"])] = st["copy"]
    v[gen42.SPAT:gen42.SPAT + 32] = bytes(gen42.big(gen42.BALL))
    return v


def regs_of(st):
    r = list(REGS0)
    r[2] = st["table"] >> 2
    return r


def shows(t, machine):
    """(frame, line, x) where a write of R#7 at T-state T shows: x = ceil(1.5 w
    - 31) for the whole T-state w of the line (chapter 18)"""
    frame, rest = divmod(math.floor(t), FT[machine])
    line, w = divmod(rest, L)
    return frame, line, math.ceil(1.5 * w - 31)


def capture_model(paper, writes, frame, machine):
    """the capture of FRAME: PAPER (192 x 256) and a border whose colour each
    write of R#7, (T-state, colour), sets from where it shows (chapter 33)"""
    row0 = PAPER0[machine] - meas.PAPER_Y0
    start = (frame, row0, meas.DRAWN[0])
    now, changes = gen42.WHITE, []
    for t, c in sorted(writes):
        f, line, x = shows(t, machine)
        if (f, line, x) <= start:
            now = c
        elif f == frame and line < row0 + meas.CAPTURE_H:
            changes.append((line, x, c))
    out = []
    k = 0
    for y in range(meas.CAPTURE_H):
        line = row0 + y
        row = [None] * meas.CAPTURE_W
        for x in range(meas.DRAWN[0], meas.DRAWN[1] + 1):
            while k < len(changes) and changes[k][:2] <= (line, x):
                now = changes[k][2]
                k += 1
            px, py = x - meas.PAPER_X0, y - meas.PAPER_Y0
            row[x] = paper[py][px] if 0 <= px < 256 and 0 <= py < 192 else now
        out.append(row)
    return out


def mismatch(model, photo_):
    return sum(1 for y in range(meas.CAPTURE_H) for x in range(meas.DRAWN[0], meas.DRAWN[1] + 1)
               if model[y][x] != photo_[y][x])


def frame_models(res, machine, frames):
    """the model of each VDP frame in FRAMES: the state the last sends before
    its paper left, and the border from every write of R#7"""
    writes = [(e["t"] + 8, MARKS[e["kind"]]) for e in res["ev"] if e["kind"] in MARKS]
    out = {}
    for c in frames:
        start = c * FT[machine] + PAPER0[machine] * L
        done = [st for t, st in res["sent"] if t < start]
        paper = vdpscreen.draw(vram_of(done[-1]), regs_of(done[-1]))
        out[c] = (capture_model(paper, writes, c, machine), done[-1])
    return out


def photo_set(name, machine, res, loop, n=4, keep=()):
    """film frames from the one loop LOOP woke in, N of them, each against
    its model; the ones in KEEP stay in captures/, the others in shots/"""
    f0 = res["f0"]
    w = res["rows"][loop]["frame"]
    want = list(range(w, w + n))
    models = frame_models(res, machine, [f0 + f for f in want])
    shots = sorted({f + d for f in want for d in (-1, 0, 1)})
    tmp = Path(tempfile.mkdtemp(prefix="ph42_"))
    pngs = msxcap.capture(rom(name), shots, tmp, f"{name}_{TAG[machine]}_f", machine=machine,
                          timeout=1800)
    ph = {f: codes(pngs[f]) for f in shots}
    fits = [d for d in (-1, 0, 1) if all(mismatch(models[f0 + f][0], ph[f + d]) == 0 for f in want)]
    assert len(fits) == 1, (name, machine, fits,
                            [(f, d, mismatch(models[f0 + f][0], ph[f + d])) for f in want for d in (-1, 0, 1)])
    d = fits[0]
    out = {}
    for f in want:
        dest = (CAPS if f in keep else SHOTS) / pngs[f + d].name.replace(f"_f{f + d:04d}", f"_f{f:04d}")
        dest.parent.mkdir(exist_ok=True)
        shutil.copy(pngs[f + d], dest)
        st = models[f0 + f][1]
        out[f] = {"png": dest.name, "at": st["at"], "col": st["col"]}
    shutil.rmtree(tmp)
    return d, out


def paper_of(photo_):
    return [row[meas.PAPER_X0:meas.PAPER_X0 + 256] for row in photo_[meas.PAPER_Y0:meas.PAPER_Y0 + 192]]


def photos():
    out = {}
    for name in PROGRAMS:
        out[name] = {}
        for m in MACHINES:
            res = analyse(name, m)
            rows = res["rows"]
            if name == "over" and m == JP:
                loop = next(r["loop"] for r in rows if r["lost"])
            elif name == "spread":
                loop = next(r["loop"] for r in analyse("over", JP)["rows"] if r["lost"]) if m == JP else \
                    max(rows[1:], key=lambda r: r["halt"])["loop"]
            else:
                loop = max(rows[1:], key=lambda r: r["halt"])["loop"]
            w = rows[loop]["frame"]
            keep = (w + 1, w + 2) if m == JP or name == "budget" else ()
            d, shots = photo_set(name, m, res, loop, keep=keep)
            out[name][TAG[m]] = {"loop": loop, "offset": d, "frames": shots}
            if name == "over" and m == JP:      # the frame lost shows the one before it
                a_, b_ = (codes((CAPS if f in keep else SHOTS) / shots[f]["png"]) for f in (w + 1, w + 2))
                out[name][TAG[m]]["same_paper"] = paper_of(a_) == paper_of(b_)
                assert out[name][TAG[m]]["same_paper"]
            print(name, TAG[m], loop, d, flush=True)
    return out


# ---------------------------------------------------------------- prices
def fresh(name, machine=JP):
    wk = walker(name, 0x80 if machine == EU else 0)
    wk.run("init", "main")
    return wk


def poke(wk, label, vals, off=0):
    a = wk.sym[label] + off
    for i, v in enumerate(vals):
        wk.mem[a + i] = v & 255


def balls_far(wk, n, y=50):
    """N balls in a row, 24 pixels apart, moving right and down: no two boxes
    meet, and none is near an edge"""
    for k in range(n):
        poke(wk, "balls", [16 + 24 * k, y, 1, 1], 4 * k)


def prices():
    out = {}
    wk = fresh("over")
    out["show"] = []
    for at in range(8):
        poke(wk, "at", [at, 0])
        poke(wk, "col", [0])
        out["show"].append(wk.call("show"))
    poke(wk, "at", [8, 0])
    poke(wk, "col", [0])
    out["show_flip"] = wk.call("show")
    out["sprites"] = {}
    for name in PROGRAMS:
        out["sprites"][name] = fresh(name).call("sprites")
    poke(wk, "score", [0, 0, 0])
    poke(wk, "hi", [0, 2, 0])
    poke(wk, "shown", [0, 0, 0, 0, 2, 0])
    out["status"] = [wk.call("status")]
    for pairs in range(1, 7):
        sc = [0x11 if k < pairs else 0 for k in range(6)]
        poke(wk, "shown", sc)
        poke(wk, "score", [0, 0, 0])
        poke(wk, "hi", [0, 0, 0])
        out["status"].append(wk.call("status"))
    out["input"] = wk.call("input")
    out["move"], out["tests"], out["build"] = {}, {}, {}
    for name in ("budget", "over"):
        n = gen42.BALLS[name]
        w2 = fresh(name)
        balls_far(w2, n)
        out["move"][n] = w2.call("move")
        balls_far(w2, n)
        out["tests"][n] = w2.call("tests")
        out["build"][n] = w2.call("build")
    out["move_bounce"] = {}
    for edge, ball in (("right", [240, 50, 1, 1]), ("left", [0, 50, -1, 1]),
                       ("top", [100, gen42.YMIN, 1, -1]), ("bottom", [100, gen42.YMAX, 1, 1])):
        w2 = fresh("over")
        balls_far(w2, 9)
        poke(w2, "balls", ball, 0)                  # the first ball at an edge
        out["move_bounce"][edge] = w2.call("move") - out["move"][9]
    # one pair more in tests: nine balls against eight
    out["tests_pair"] = (out["tests"][9] - out["tests"][8]) / 8
    # bump: two balls that touch, coming together, then parting
    w2 = fresh("over")
    balls_far(w2, 9)
    poke(w2, "balls", [100, 50, 1, 0], 0)
    poke(w2, "balls", [110, 50, -1 & 255, 0], 4)
    w2.r["h"], w2.r["l"] = (w2.sym["balls"] + 4) >> 8, (w2.sym["balls"] + 4) & 255
    w2.ix = w2.sym["balls"]
    out["bump_taken"] = w2.call("bump", h=(w2.sym["balls"] + 4) >> 8, l=(w2.sym["balls"] + 4) & 255)
    w2.ix = w2.sym["balls"]
    out["bump_parting"] = w2.call("bump", h=(w2.sym["balls"] + 4) >> 8, l=(w2.sym["balls"] + 4) & 255)
    # the window: all at once, and three rows a frame
    wb = fresh("budget")
    poke(wb, "need", [gen42.ROWS])
    out["nextwin_once"] = wb.call("nextwin")
    ws = fresh("spread")
    poke(ws, "need", [gen42.ROWS])
    poke(ws, "counted", [1])
    out["nextwin_chunk"] = ws.call("nextwin")
    out["chunks"] = math.ceil(gen42.ROWS / gen42.CHUNK)
    wb = fresh("budget")
    poke(wb, "need", [1])
    one = wb.call("nextwin")
    poke(wb, "need", [2])
    out["window_row"] = wb.call("nextwin") - one
    out["window_one_row"] = one
    # the marks, and the rest of the loop around the calls
    w3 = fresh("over")
    out["mark"] = 5 + 8 + 12 + 8 + 12 + 5
    return out


# ---------------------------------------------------------------- the workshop
def build_variant(name, n=None, chunk=None):
    """the program NAME with N balls or CHUNK rows a frame, assembled in a
    folder of its own; its stem"""
    d = Path(tempfile.mkdtemp(prefix="v42_"))
    for f in ("msx.inc", "bios.inc", "music.inc"):
        shutil.copy(HERE / f, d / f)
    stem = f"{name}_{n or 0}_{chunk or 0}"
    (d / f"{stem}.asm").write_text(gen42.program(name, n, chunk).replace(f'OUTPUT "{name}.rom"',
                                                                          f'OUTPUT "{stem}.rom"'))
    subprocess.run(["sjasmplus", "--nologo", "--msg=err", "--syntax=bFw", f"--sym={stem}.sym",
                    f"--lst={stem}.lst", f"{stem}.asm"], cwd=d, check=True)
    return d / stem


def lost_frames(name, machine, path, n):
    """the frames a variant loses: a loop that is not back at HALT before the
    next signal"""
    f0, ev, s = film(name, machine, path=path, n=n, light=True)
    tail = walker(name, 0).run("m3", "frame")
    lost, longest = 0, 0
    marks = [e for e in ev if e["kind"] in ("isr", "m3")]
    wake = None
    for e in marks:
        if e["kind"] == "isr":
            if wake is None:
                wake = e
        else:
            halt = e["t"] + tail
            sig = signal_of(wake["frame"], machine)
            longest = max(longest, halt - sig)
            nxt = [x for x in marks if x["kind"] == "isr" and x["t"] > e["t"]]
            if nxt and nxt[0]["frame"] > wake["frame"] + 1:
                lost += nxt[0]["frame"] - wake["frame"] - 1
            wake = nxt[0] if nxt else None
    return lost, num(longest)


def answers():
    m = json.loads((HERE / "meas42.json").read_text())
    fl, pr = m["films"], m["prices"]
    out = {}
    # 1: spread.asm with more balls, at 60 Hz
    q1 = {}
    for n in range(10, len(gen42.START_ALL) + 1):
        path = build_variant("spread", n=n)
        q1[n] = lost_frames("spread", JP, path, n)
        shutil.rmtree(path.parent)
        print("q1", n, q1[n], flush=True)
    keep = [n for n, (lost, _) in q1.items() if lost == 0]
    out["q1"] = {"runs": q1, "most": max(n for n in keep if all(q1[k][0] == 0 for k in range(10, n + 1)))}
    # 2: spread.asm with two rows a frame: rows 16 to 20 of the table shown
    path = build_variant("spread", chunk=2)
    s2 = dbg.sym(path.with_suffix(".sym"))
    tcl = (f'debug set_bp {s2["m1"]} {{}} {{ L "m1 {POS}"; VR t0 {0x1800 + 32 * 16} 160; '
           f'VR t1 {0x1C00 + 32 * 16} 160; M g {gen42.GAME} 32; '
           f'L "r2 [debug read {{VDP regs}} 2]" }}\n')
    w = run("spread", JP, 300, tcl, path=path.with_suffix(".rom"))
    shutil.rmtree(path.parent)
    loops, bad, rows_bad = 0, 0, set()
    cur = {}
    for x in w:
        if x[0] == "m1":
            cur = {}
            loops += 1
        elif len(x) == 3 and x[1] in ("vram", "mem"):
            cur[x[0]] = bytes.fromhex(x[2])
        elif x[0] == "r2":
            g = cur["g"]
            at = g[0x10] | g[0x11] << 8
            col = (at >> 3) & 63
            shown = cur["t0" if int(x[1]) == 6 else "t1"]
            ideal = [gen42.PMAP[r][(col + c) % gen42.WIDTH] for r in range(16, 21) for c in range(32)]
            wrong = [r for r in range(5) if list(shown[32 * r:32 * r + 32]) != ideal[32 * r:32 * r + 32]]
            if wrong:
                bad += 1
                rows_bad |= {16 + r for r in wrong}
    out["q2"] = {"loops": loops, "wrong": bad, "rows": sorted(rows_bad)}
    # 3: over.asm at 60 Hz: the loops that wrote the window, and the ones of
    # them that lost a frame, with what else each of these had
    rows = fl["over"]["jp"]["rows"][1:]
    no_tick = min(r["isr"] for r in rows)
    window = [r for r in rows if r["rows"]]
    out["q3"] = {"window_loops": len(window), "lost": [r["loop"] for r in window if r["lost"]],
                 "lost_rows": [{"loop": r["loop"], "isr": r["isr"], "tick": r["isr"] > no_tick,
                                "bumps": r["bumps"], "sends": r["sends"], "logic": r["logic"],
                                "halt": r["halt"]} for r in window if r["lost"]],
                 "kept_most": max(r["halt"] for r in window if not r["lost"])}
    # 4: status when the score goes from 290 to 300 and the best follows
    wk = fresh("over")
    poke(wk, "shown", [0, 0x02, 0x90, 0, 0x02, 0x90])
    poke(wk, "score", [0, 0x03, 0x00])
    poke(wk, "hi", [0, 0x03, 0x00])
    out["q4"] = {"status": wk.call("status"), "pairs": 4}
    assert out["q4"]["status"] == pr["status"][4]
    # 5: loops without a tick at 60 Hz
    q5 = {}
    for name in PROGRAMS:
        rs = fl[name]["jp"]["rows"][1:]
        q5[name] = {"loops": len(rs), "no_tick": sum(1 for r in rs if r["isr"] == no_tick)}
    q5["eu_no_tick"] = sum(1 for r in fl["budget"]["eu"]["rows"][1:] if r["isr"] < 1000)
    out["q5"] = q5
    # 6: the window spread, against all at once
    out["q6"] = {"chunks": pr["chunks"], "spread_total": pr["chunks"] * pr["nextwin_chunk"],
                 "once": pr["nextwin_once"]}
    return out


# ---------------------------------------------------------------- voices
MAIN_CALLS = ["show", "sprites", "status", "input", "move", "tests", "build", "nextwin"]


def call_sites(name):
    """the address of each CALL of the frame's loop, from the listing"""
    out = {}
    for line in (HERE / f"{name}.lst").read_text().splitlines():
        mt = dbg.LST.match(line)
        if not mt or "..." in mt.group(3)[1:13] or not mt.group(3)[1:13].strip():
            continue
        _, a, c, src = dbg.lst_fields(mt)
        code = src.split(";")[0].split()
        if len(code) == 2 and code[0] == "call" and code[1] in MAIN_CALLS and code[1] not in out:
            out[code[1]] = a
    assert set(out) == set(MAIN_CALLS), out
    return out


def run_to(wk, addr):
    t0 = wk.t
    while wk.pc != addr:
        wk.step()
    return wk.t - t0


def voices_of(name, machine, res, k):
    """a loop part by part, by walk.py on the RAM the debugger read at its
    first mark: each CALL with its routine, and the marks and the counting
    apart; the routine and the interrupts inside from the debugger"""
    lp, row = res["loops"][k], res["rows"][k]
    wk = walker(name, 0x80 if machine == EU else 0)
    for addr, data in [(ENGINE[0], lp["m0"]["e"]), (GAME[0], lp["m0"]["g"])]:
        wk.mem[addr:addr + len(data)] = data
    c = call_sites(name)
    wk.pc = wk.sym["m0"]
    v = {"wake": row["wake"], "isr": row["isr"],
         "marks": num(row["m0"] - row["wake"] - row["isr"])}   # from the RET to the first mark
    v["marks"] += run_to(wk, c["show"])
    v["show"] = run_to(wk, c["sprites"])
    v["sprites"] = run_to(wk, c["status"])
    v["status"] = run_to(wk, c["status"] + 3)
    v["marks"] += run_to(wk, c["input"])
    v["input"] = run_to(wk, c["input"] + 3)
    v["count"] = run_to(wk, c["move"] - 1)          # .steps: PUSH BC, then the CALL
    v["moves"] = run_to(wk, c["tests"])
    v["tests"] = run_to(wk, c["build"])
    v["build"] = run_to(wk, c["build"] + 3)
    v["marks"] += run_to(wk, c["nextwin"])
    v["nextwin"] = run_to(wk, c["nextwin"] + 3)
    v["marks"] += run_to(wk, wk.sym["m3"]) + res["tail"]
    v["inside"] = num(sum(ANSWER + (end["t"] - e["t"]) + BACK for e, end in lp["inside"]))
    parts = ("wake", "isr", "marks", "show", "sprites", "status", "input", "count", "moves",
             "tests", "build", "nextwin", "inside")
    total = sum(v[x] for x in parts)
    assert num(total) == row["halt"], (name, machine, k, total, row["halt"], v)
    v.update(frame=row["frame"], loop=k, bumps=row["bumps"], counted=row["counted"],
             halt=row["halt"])
    return v


def voices():
    out = {}
    for name, m, pick in (("budget", JP, "longest"), ("budget", EU, "longest"),
                          ("over", JP, "lost"), ("spread", JP, "longest")):
        res = analyse(name, m)
        rows = res["rows"]
        if pick == "lost":
            k = next(r["loop"] for r in rows if r["lost"])
        else:
            k = max(rows[1:], key=lambda r: r["halt"])["loop"]
        out[f"{name}_{TAG[m]}"] = voices_of(name, m, res, k)
        print(name, TAG[m], out[f"{name}_{TAG[m]}"], flush=True)
    return out


OPENMSX_SECTIONS = ["films", "photos", "prices", "voices", "answers"]


def openmsx():
    if not versions.builds():
        return {"skipped": "OPENMSX_BUILDS not set"}
    return versions.every_build(["ch42"], OPENMSX_SECTIONS)


SECTIONS = {"films": films, "photos": photos, "prices": prices, "voices": voices, "answers": answers,
            "openmsx": openmsx}


def main(names=()):
    CAPS.mkdir(exist_ok=True)
    path_ = HERE / "meas42.json"
    m = json.loads(path_.read_text()) if names and path_.exists() else {}
    for name in names or SECTIONS:
        print(name, flush=True)
        m[name] = SECTIONS[name]()
        m = {k: m[k] for k in SECTIONS if k in m}
        path_.write_text(json.dumps(m, indent=1) + "\n")
    return m


if __name__ == "__main__":
    main(sys.argv[1:])
