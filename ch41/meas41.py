#!/usr/bin/env python3
"""meas41.py -- random numbers, the R register, and game states, measured.

    python3 gen41.py && ./build.sh && python3 meas41.py
                                  python3 meas41.py rreg states   only these

  rreg      rreg.rom on both machines: the 2,048 numbers R gave, against
            walk.py's count of opcode fetches in a pass; the T-states of a
            pass; R on either side of eight HALTs against the time the
            processor waited; the photo against the pairs plotted (figure 41.1)
  lcg       lcg.rom: the 512 numbers against 5x + 1; the photo (figure 41.1)
  xorshift  xorshift.rom: the state after the whole period; the T-states of
            the first passes against walk.py; photos at a frame of the way
            and at the end, against the pairs plotted (figure 41.2); the
            rule the pairs keep, found by elimination over XOR
  bits      bits.rom: the photo against the bits of both generators; the
            bands read back, column by column (figure 41.3)
  rows      rows.rom: the counts of the rows in the RAM against the three
            ways worked out in Python; the T-states of each way against
            walk.py
  states    states.rom with states.events on both machines: the key seen,
            the seed, the play's and game over's frames, the cells of each
            game read from the photos against the generator; each frame's
            work against walk.py (figure 41.4)
  prices    what each routine costs, from walk.py, on the paths that matter
  answers   the workshop, tried (for Appendix I)
  openmsx   all of it again with every other build (tools/versions.py)
"""
import json
import shutil
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
import gen41       # noqa: E402
sys.path.remove(str(HERE))
sys.path.insert(0, str(HERE))      # gen41 put chapters 25, 26 and 30 first: this folder's files win
for mod in ("vdpscreen", "walk"):
    sys.modules.pop(mod, None)
import vdpscreen   # noqa: E402
import walk        # noqa: E402

assert Path(vdpscreen.__file__).parent == HERE and Path(walk.__file__).parent == HERE

CAPS = HERE / "captures"
EU, JP = gen41.EU, gen41.JP
MACHINES = gen41.MACHINES
TAG = {EU: "eu", JP: "jp"}
CLOCK = dbg.CLOCK
PALETTE = [tuple(c) for c in json.loads((REPO / "ch01" / "meas01.json").read_text())["palette"]["rgb"]]
CODE = {rgb: n for n, rgb in enumerate(PALETTE) if n}
POS = "[machine_info VDP_frame_count] [machine_info VDP_cycle_in_frame] [machine_info time]"
BITMAP_REGS = [0x02, 0xC0, 0x06, 0xFF, 0x03, 0x36, 0x07, 0x0F]
IM2_ANSWER, JP_T = 19, 11           # chapter 17: IM 2 from the interrupt taken to the vector; the JP
HALT_STEP = 5                       # chapters 17 and 32: a HALT waits in steps of 5 T-states

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
    lines = msxcap.run_tcl(rom(name), frames, at_init, machine=machine, tcl_setup=STATE,
                           events=events or {}, timeout=1800)
    return [l.split() for l in lines]


def logged(w, tag, kind):
    x = next(x for x in w if x[0] == tag and x[1] == kind)
    if kind in ("vram", "mem"):
        return bytes.fromhex(x[2])
    return [int(v) for v in x[2:]]


def once(addr, body, tag):
    return f'set ::{tag} [debug set_bp {addr} {{}} {{ {body}; debug remove_bp $::{tag} }}]\n'


def codes(png):
    im = Image.open(png).convert("RGB")
    px = im.load()
    return [[CODE.get(px[x, y]) for x in range(im.width)] for y in range(im.height)]


def against(model, photo, backdrop):
    """pixels of the drawn columns that differ from the model"""
    bad = 0
    for y in range(meas.CAPTURE_H):
        for x in range(meas.DRAWN[0], meas.DRAWN[1] + 1):
            px, py = x - meas.PAPER_X0, y - meas.PAPER_Y0
            want = model[py][px] if 0 <= px < 256 and 0 <= py < 192 else backdrop
            bad += photo[y][x] != want
    return bad


def paper_of(photo):
    return [row[meas.PAPER_X0:meas.PAPER_X0 + 256] for row in photo[meas.PAPER_Y0:meas.PAPER_Y0 + 192]]


def photo(name, machine, frame, keep=True, events=None):
    """the film frame FRAME; kept in captures/ when KEEP"""
    out = CAPS if keep else HERE / "shots"
    out.mkdir(exist_ok=True)
    return msxcap.capture(rom(name), [frame], out, f"{name}_{TAG[machine]}_f", machine=machine,
                          events=events or {}, timeout=1800)[frame]


# ---------------------------------------------------------------- the bitmap model
def bitmap_vram(pixels):
    """chapter 25's bitmap with PIXELS set: (x, y) pairs"""
    v = bytearray(16384)
    for x, y in pixels:
        v[vdpscreen.address(x, y)] |= 0x80 >> (x & 7)
    v[0x2000:0x3800] = bytes([0x1F]) * 6144
    v[0x1800:0x1B00] = bytes(range(256)) * 3
    v[0x1B00] = 0xD0
    return v


def bitmap_picture(pixels):
    return vdpscreen.draw(bitmap_vram(pixels), BITMAP_REGS)


def pairs_plotted(numbers, first_before):
    """the pixels a plotting loop sets: (the one before, this one) below 192"""
    out, before = set(), first_before
    for n in numbers:
        if n < 192:
            out.add((before, n))
        before = n
    return out


def black(photo_):
    pp = paper_of(photo_)
    return {(x, y) for y in range(192) for x in range(256) if pp[y][x] == gen41.BLACK}


# ---------------------------------------------------------------- walk
def walker(name, rate=0x80, read_port=None):
    wk = walk.Walk(HERE / name, read_port=read_port)
    wk.mem[0x2B] = rate
    return wk


def fetch_count(wk, start, stop):
    """R's count, by walk.py, from label START to label STOP"""
    r0, t0 = wk.rreg, wk.t
    wk.run(start, stop)
    return (wk.rreg - r0) & 0x7F, wk.t - t0


# ---------------------------------------------------------------- rreg
def rreg():
    s = sym("rreg")
    out = {}
    # one pass, by walk.py: from pl2 to pl2, R's count and the T-states
    wk = walker("rreg")
    wk.run("init", "pl1")
    wk.run("pl1", "pl2")
    r0, t0 = wk.rreg, wk.t
    wk.run("pl2", "pl1")
    wk.run("pl1", "pl2")
    k, t_pass = (wk.rreg - r0) & 0x7F, wk.t - t0
    for m in MACHINES:
        tcl = (once(s["pl1"], 'L "first [reg b]"', "f1") +
               f'debug set_bp {s["pl2"]} {{}} {{ L "n [reg c] [machine_info time]" }}\n'
               f'debug set_bp {s["before"]} {{}} {{ L "before [reg a] [reg r] {POS}" }}\n'
               f'debug set_bp {s["after"]} {{}} {{ L "after [reg r] {POS}" }}\n'
               f'debug set_bp {s["isr"]} {{}} {{ L "irq [reg r] {POS}" }}\n'
               + once(s["done"], f'V end; L "done {POS}"', "d"))
        w = run("rreg", m, 60, tcl)
        first = int(next(x for x in w if x[0] == "first")[1])
        nums = [int(x[1]) for x in w if x[0] == "n"]
        times = [t_state(x[2]) for x in w if x[0] == "n"]
        assert len(nums) == gen41.RREG_PASSES
        steps = {(b - a) & 0x7F for a, b in zip(nums, nums[1:])}
        gaps = {b - a for a, b in zip(times, times[1:])}
        assert steps == {k} and gaps == {t_pass}, (m, steps, k, gaps, t_pass)
        assert all(n < 128 for n in nums + [first])
        # R on either side of the HALTs: the wake is the 'after' that follows
        # the interrupt routine's mark (a breakpoint after HALT is met while
        # the processor halts too, chapter 31)
        halts, pend, seen_irq = [], None, False
        for x in w:
            if x[0] == "before":
                pend = {"r_before": int(x[2]), "t_before": t_state(x[5])}
            elif x[0] == "irq" and pend is not None:
                pend["t_irq"] = t_state(x[4])
                seen_irq = True
            elif x[0] == "after" and seen_irq and pend is not None:
                pend["r_after"] = int(x[1])
                halts.append(pend)
                pend, seen_irq = None, False
        assert len(halts) == gen41.HALTS, (m, len(halts))
        isr_fetches = 5                 # push af, in a,(n), pop af, ei, ret
        for h in halts:
            waited = h["t_irq"] - h["t_before"] - HALT_STEP - IM2_ANSWER - JP_T
            assert waited % HALT_STEP == 0, (m, h)
            h["waited"] = waited
            h["steps"] = waited // HALT_STEP
            h["r_up"] = (h["r_after"] - h["r_before"]) & 0x7F
            h["model"] = (1 + h["steps"] + 1 + 1 + isr_fetches) & 0x7F
            assert h["r_up"] == h["model"], (m, h)
        f0 = int(next(x for x in w if x[0] == "f0")[1])
        done = int(next(x for x in w if x[0] == "done")[1]) - f0
        pixels = pairs_plotted(nums, first)
        assert logged(w, "end", "vram")[:0x1800] == bytes(bitmap_vram(pixels)[:0x1800]), m
        png = photo("rreg", m, done + 2, keep=(m == EU))
        assert against(bitmap_picture(pixels), codes(png), 15) == 0, m
        lines = sorted({(y - x) & 0x7F for x, y in pixels})
        out[TAG[m]] = {"first": first, "numbers": nums[:16], "count": len(nums),
                       "different": len(set(nums)), "step": k, "pass_T": t_pass,
                       "pixels": len(pixels), "differences": lines, "halts": halts,
                       "done_frame": done, "photo": png.name}
    assert out["eu"]["numbers"] != out["jp"]["numbers"] or True
    return out


# ---------------------------------------------------------------- lcg
def lcg():
    s = sym("lcg")
    out = {}
    want = gen41.lcg_numbers(0, gen41.LCG_STEPS)
    # walk.py: the T-states from lc2 to lc2, as the debugger stops
    wk = walker("lcg")
    wk.run("init", "lc1")
    wk.run("lc1", "lc2")
    walk_t = []
    for _ in range(gen41.LCG_STEPS - 1):
        t0 = wk.t
        wk.run("lc2", "lc1")
        wk.run("lc1", "lc2")
        walk_t.append(wk.t - t0)
    for m in MACHINES:
        tcl = (f'debug set_bp {s["lc2"]} {{}} {{ L "n [reg c] [machine_info time]" }}\n'
               + once(s["done"], f'V end; L "done {POS}"', "d"))
        w = run("lcg", m, 60, tcl)
        nums = [int(x[1]) for x in w if x[0] == "n"]
        assert nums == want, m
        times = [t_state(x[2]) for x in w if x[0] == "n"]
        assert [b - a for a, b in zip(times, times[1:])] == walk_t, m
        f0 = int(next(x for x in w if x[0] == "f0")[1])
        done = int(next(x for x in w if x[0] == "done")[1]) - f0
        pixels = pairs_plotted(nums, 0)
        assert logged(w, "end", "vram")[:0x1800] == bytes(bitmap_vram(pixels)[:0x1800]), m
        png = photo("lcg", m, done + 2, keep=(m == EU))
        assert against(bitmap_picture(pixels), codes(png), 15) == 0, m
        period = want.index(want[0], 1)
        # each pixel's line: y = 5x + 1 - 256k
        ks = sorted({(5 * x + 1 - y) // 256 for x, y in pixels})
        out[TAG[m]] = {"period": period, "pixels": len(pixels), "lines": ks, "done_frame": done,
                       "photo": png.name, "pass_T": sorted(set(walk_t))}
    return out


# ---------------------------------------------------------------- xorshift
XOR_EARLY = 40                      # a frame of the way, from INIT


def xorshift_():
    s = sym("xorshift")
    out = {}
    states = gen41.random_states(1, gen41.PERIOD)
    highs = [x >> 8 for x in states]
    assert states[-1] == 1 and 1 not in states[:-1]
    # the first passes, by walk.py: the T-states and the numbers
    wk = walker("xorshift")
    wk.run("init", "xs1")
    wk.run("xs1", "xs2")
    walk_t, walk_n = [], [wk.r["c"]]
    for _ in range(256):                # from xs2 to xs2, as the debugger stops
        t0 = wk.t
        wk.run("xs2", "xs1")
        wk.run("xs1", "xs2")
        walk_n.append(wk.r["c"])
        walk_t.append(wk.t - t0)
    assert walk_n == highs[:257]
    for m in MACHINES:
        tcl = (f'set ::k 0\ndebug set_bp {s["xs2"]} {{}} {{ incr ::k; if {{$::k <= 257}} '
               f'{{ L "n [reg c] [machine_info time]" }} }}\n'
               + once(s["done"], f'V end; M seed {s["seed"]} 2; L "done {POS}"', "d"))
        ev = {XOR_EARLY: f"M s0 {s['seed']} 2", XOR_EARLY + 1: f"M s1 {s['seed']} 2"}
        w = run("xorshift", m, 700, tcl, events=ev)
        nums = [int(x[1]) for x in w if x[0] == "n"]
        times = [t_state(x[2]) for x in w if x[0] == "n"]
        assert nums == highs[:257], m
        assert [b - a for a, b in zip(times, times[1:])] == walk_t, m
        seed = logged(w, "seed", "mem")
        assert seed[0] | seed[1] << 8 == 1, m
        f0 = int(next(x for x in w if x[0] == "f0")[1])
        done = int(next(x for x in w if x[0] == "done")[1]) - f0
        pixels = pairs_plotted(highs, 0)
        assert logged(w, "end", "vram")[:0x1800] == bytes(bitmap_vram(pixels)[:0x1800]), m
        png = photo("xorshift", m, done + 2, keep=(m == EU))
        assert against(bitmap_picture(pixels), codes(png), 15) == 0, m
        early = photo("xorshift", m, XOR_EARLY, keep=(m == EU))
        seen = black(codes(early))
        # the early photo: every pair plotted before its frame began, and
        # none plotted after it ended
        n0, n1 = (states.index(int.from_bytes(logged(w, t, "mem"), "little")) + 1 for t in ("s0", "s1"))
        assert pairs_plotted(highs[:n0], 0) <= seen <= pairs_plotted(highs[:n1], 0), m
        res = {"pixels": len(pixels), "done_frame": done, "photo": png.name,
               "early": early.name, "early_pixels": len(seen), "early_passes": [n0, n1]}
        out[TAG[m]] = res
    counts = [0] * 256
    for h in highs:
        counts[h] += 1
    out["counts"] = {"most": max(counts), "least": min(counts), "zero": counts[0]}
    out["first_T"] = sorted(set(walk_t))
    out["rule"] = parity_rule(highs)
    return out


def parity_rule(highs):
    """the XOR rules a number and the next keep, for every pair of the
    period: the masks (m1, m2) for which parity(a AND m1) = parity(b AND
    m2), by elimination over GF(2)"""
    pairs = list(zip(highs, highs[1:] + highs[:1]))
    # each pair is a 16-bit vector a | b << 8; the rules are the vectors c
    # with parity(c AND v) = 0 for every v: the null space of the pairs' span
    basis = []                                  # rows of the pairs' span, reduced
    for a, b in pairs:
        v = a | b << 8
        for r in basis:
            v = min(v, v ^ r)
        if v:
            basis.append(v)
            basis.sort(reverse=True)
    rank = len(basis)
    rules = [c for c in range(1, 1 << 16)
             if all(bin(c & (a | b << 8)).count("1") % 2 == 0 for a, b in pairs[:64])]
    rules = [c for c in rules if all(bin(c & (a | b << 8)).count("1") % 2 == 0 for a, b in pairs)]
    distinct = len(set(pairs))
    return {"rank": rank, "rules": [[c & 255, c >> 8] for c in rules], "pairs": distinct}


# ---------------------------------------------------------------- bits
def strip_lines(top, i):
    return range(top + i * (gen41.STRIP + gen41.STRIP_GAP), top + i * (gen41.STRIP + gen41.STRIP_GAP) + gen41.STRIP)


def bits_pixels(lcg_nums, rnd_nums):
    px = set()
    for top, nums in ((gen41.LCG_TOP, lcg_nums), (gen41.RND_TOP, rnd_nums)):
        for k, n in enumerate(nums):
            for i in range(8):
                if n & (0x80 >> i):
                    px |= {(k, y) for y in strip_lines(top, i)}
    return px


def read_band(seen, top):
    """the 256 numbers of a band, read from the photo: a strip's middle line"""
    return [sum(0x80 >> i for i in range(8) if (k, strip_lines(top, i)[2]) in seen) for k in range(256)]


def period(bits):
    """the shortest period up to 128 of a list of 256 bits, or None"""
    for p in range(1, 129):
        if all(bits[i] == bits[i + p] for i in range(256 - p)):
            return p
    return None


def bits():
    s = sym("bits")
    lcg_nums = gen41.lcg_numbers(0, 256)
    rnd_nums = [x >> 8 for x in gen41.random_states(1, 256)]
    pixels = bits_pixels(lcg_nums, rnd_nums)
    out = {}
    for m in MACHINES:
        w = run("bits", m, 200, once(s["done"], f'V end; L "done {POS}"', "d"))
        f0 = int(next(x for x in w if x[0] == "f0")[1])
        done = int(next(x for x in w if x[0] == "done")[1]) - f0
        assert logged(w, "end", "vram")[:0x1800] == bytes(bitmap_vram(pixels)[:0x1800]), m
        png = photo("bits", m, done + 2, keep=(m == EU))
        ph = codes(png)
        assert against(bitmap_picture(pixels), ph, 15) == 0, m
        seen = black(ph)
        assert read_band(seen, gen41.LCG_TOP) == lcg_nums and read_band(seen, gen41.RND_TOP) == rnd_nums, m
        out[TAG[m]] = {"done_frame": done, "photo": png.name}
    out["lcg_periods"] = [period([(n >> b) & 1 for n in lcg_nums]) for b in range(8)]
    out["random_periods"] = [period([(n >> b) & 1 for n in rnd_nums]) for b in range(8)]
    out["lcg_and31_period"] = period([n & 31 for n in lcg_nums])
    return out


# ---------------------------------------------------------------- rows
ROWS_FRAMES = 1600


def rows():
    s = sym("rows")
    numbers = [x >> 8 for x in gen41.random_states(1, gen41.PERIOD)]
    rej, took, _ = gen41.rowrej_rows(1, gen41.PERIOD)
    want = {"rej": [rej.count(r) for r in range(24)],
            "mul": [sum(1 for n in numbers if gen41.rowmul(n) == r) for r in range(24)],
            "mod": [sum(1 for n in numbers if gen41.rowmod(n) == r) for r in range(24)]}
    # walk.py: the T-states of each way's 65,535 rows, loop and counting included
    wk = walker("rows")
    wk.run("init", "rj1")
    walk_t = [wk.run("rj1", "rejected"), wk.run("rejected", "multiplied"), wk.run("multiplied", "done")]
    out = {}
    marks = ("rj1", "rejected", "multiplied", "done")
    for m in MACHINES:
        tcl = once(s["rj1"], f'L "rj1 {POS}"', "a") + once(s["rejected"], f'L "rejected {POS}"', "b") + \
            once(s["multiplied"], f'L "multiplied {POS}"', "c") + \
            once(s["done"], f'M counts {s["counts"]} 144; L "end {POS}"', "d")
        w = run("rows", m, ROWS_FRAMES, tcl)
        t = {mk: t_state(next(x for x in w if x[0] == (mk if mk != "done" else "end") and len(x) == 4)[3])
             for mk in marks}
        got = [b - a for a, b in zip([t[mk] for mk in marks], [t[mk] for mk in marks][1:])]
        assert got == walk_t, (m, got, walk_t)
        c = logged(w, "counts", "mem")
        counts = [[c[48 * k + 2 * r] | c[48 * k + 2 * r + 1] << 8 for r in range(24)] for k in range(3)]
        assert counts == [want["rej"], want["mul"], want["mod"]], m
        out[TAG[m]] = {"T": got}
    out["counts"] = want
    out["took"] = {"numbers": sum(took), "most": max(took), "rows": len(took),
                   "once": took.count(1)}
    return out


# ---------------------------------------------------------------- states
def events(name):
    """NAME.events: {frame: Tcl}, the frame counted from INIT (chapter 34)"""
    ev = {}
    for line in (HERE / f"{name}.events").read_text().splitlines():
        line = line.split("#")[0].strip()
        if line:
            n, cmd = line.split(None, 1)
            ev[int(n)] = (ev[int(n)] + "; " + cmd) if int(n) in ev else cmd
    return ev


def states_vram(cells=(), text=None):
    """the VRAM of states.rom: the shapes and colours of its set-up, the names
    spaces but for the black CELLS and TEXT, (address, string)"""
    v = bytearray(16384)
    v[8:16] = bytes([0xFF]) * 8
    v[0x100:0x400] = gen41.FONT
    v[0x2000:0x2800] = bytes([gen41.BLACK << 4 | gen41.WHITE]) * 0x800
    v[0x1800:0x1B00] = bytes([32]) * 768
    v[0x1B00] = 0xD0
    for c, r in cells:
        v[0x1800 + 32 * r + c] = gen41.BLOCK
    if text:
        a, t = text
        v[a:a + len(t)] = t.encode()
    return v


def black_cells(photo_):
    pp = paper_of(photo_)
    return {(c, r) for r in range(24) for c in range(32)
            if all(pp[8 * r + y][8 * c + x] == gen41.BLACK for y in range(8) for x in range(8))}


def states():
    s = sym("states")
    ev = events("states")
    out = {}
    for m in MACHINES:
        tcl = (f'debug set_bp {s["work"]} {{}} {{ L "work [debug read memory {s["state"]}] '
               f'[debug read memory {s["ticks"]}] [debug read memory {s["ticks"] + 1}] {POS}" }}\n'
               f'debug set_bp {s["worked"]} {{}} {{ L "worked {POS}" }}\n'
               f'debug set_bp {s["isr"]} {{}} {{ L "irq {POS}" }}\n'
               f'debug set_bp {s["keyed"]} {{}} {{ L "key [reg a]" }}\n'
               f'debug set_bp {s["pressed"]} {{}} {{ L "pressed [debug read memory {s["seed"]}] '
               f'[debug read memory {s["seed"] + 1}] {POS}" }}\n'
               f'debug set_bp {s["ended"]} {{}} {{ L "ended {POS}" }}\n'
               f'debug set_bp {s["again"]} {{}} {{ L "again {POS}" }}\n')
        w = run("states", m, gen41.STATES_FRAMES, tcl, events=ev)
        f0 = int(next(x for x in w if x[0] == "f0")[1])
        # the frames' work: the 'work' that follows the interrupt routine's mark
        frames, after_irq = [], False
        for x in w:
            if x[0] == "irq":
                after_irq = True
            elif x[0] == "work" and after_irq:
                frames.append({"state": int(x[1]), "ticks": int(x[2]) | int(x[3]) << 8,
                               "frame": int(x[4]) - f0, "t0": t_state(x[6])})
                after_irq = False
            elif x[0] == "worked" and frames and "t1" not in frames[-1]:
                frames[-1]["t1"] = t_state(x[3])
        frames = [f for f in frames if "t1" in f]
        keys = [int(x[1]) for x in w if x[0] == "key"]
        pressed = [x for x in w if x[0] == "pressed"]
        ended = [int(x[1]) - f0 for x in w if x[0] == "ended"]
        again = [int(x[1]) - f0 for x in w if x[0] == "again"]
        seeds = [int(x[1]) | int(x[2]) << 8 for x in pressed]
        press_frames = [int(x[3]) - f0 for x in pressed]
        assert len(seeds) == 2 and len(ended) == 2 and len(again) == 2, (m, seeds, ended, again)
        # walk.py: every frame's work from the same memory, the ticks and the
        # keys the debugger saw
        kq = list(keys)
        wk = walker("states", read_port=lambda port, t: kq.pop(0) if port == 0xA9 else 0)
        wk.run("init", "frame")
        for f in frames:
            wk.mem[s["ticks"]], wk.mem[s["ticks"] + 1] = f["ticks"] & 255, f["ticks"] >> 8
            assert wk.mem[s["state"]] == f["state"], (m, f)
            f["walk"] = wk.run("work", "worked")
            assert f["walk"] == f["t1"] - f["t0"], (m, f)
        assert not kq, (m, len(kq))
        # the photos: the title, and game over after each play
        shots = {"title": press_frames[0] - 10,
                 "over1": again[0] - 1, "over2": again[1] - 1}
        res = {"seeds": seeds, "pressed": press_frames, "ended": ended, "again": again,
               "frames": len(frames)}
        for name, n in shots.items():
            png = photo("states", m, n, keep=(m == EU), events=ev)
            ph = codes(png)
            if name == "title":
                model = states_vram(text=(gen41.PRESS_AT, gen41.PRESS))
                assert against(vdpscreen.draw(model, gen41.STATES_REGS), ph, 15) == 0, (m, name)
            else:
                k = int(name[-1]) - 1
                cells = gen41.play_cells(seeds[k])
                model = states_vram(cells, (gen41.OVER_AT, gen41.OVER_TEXT))
                assert against(vdpscreen.draw(model, gen41.STATES_REGS), ph, 15) == 0, (m, name)
                got = black_cells(ph)
                under = {(c, 11) for c in range(gen41.OVER_AT % 32, gen41.OVER_AT % 32 + len(gen41.OVER_TEXT))}
                assert got == set(cells) - under, (m, name)
                res[name] = {"black": len(got), "different": len(set(cells)), "under_text": len(set(cells) & under)}
            res[name + "_photo"] = png.name
            res[name + "_frame"] = n
        both = set(gen41.play_cells(seeds[0])) & set(gen41.play_cells(seeds[1]))
        res["both"] = len(both)
        # each frame's work by the state it began in, and whether it changed state
        kinds = {}
        for i, f in enumerate(frames):
            nxt = frames[i + 1]["state"] if i + 1 < len(frames) else f["state"]
            key = f"{f['state']}{'>' + str(nxt) if nxt != f['state'] else ''}"
            kinds.setdefault(key, []).append(f["walk"])
        res["work"] = {k: [len(v), min(v), max(v)] for k, v in sorted(kinds.items())}
        out[TAG[m]] = res
    return out


# ---------------------------------------------------------------- prices
def prices():
    out = {}
    wl = walker("lcg")
    wl.mem[sym("lcg")["seed8"]] = 0
    out["lcg"] = wl.call("lcg")
    wx = walker("xorshift")
    sx = sym("xorshift")
    ts = set()
    for seed in (1, 0x1234, 0xFFFF, 0x8000):
        wx.mem[sx["seed"]], wx.mem[sx["seed"] + 1] = seed & 255, seed >> 8
        ts.add(wx.call("random"))
        assert wx.mem[sx["seed"]] | wx.mem[sx["seed"] + 1] << 8 == gen41.xorshift(seed)
    assert len(ts) == 1
    out["random"] = ts.pop()
    # rowrej, by the numbers it takes: walk.py from seeds that need k of them
    st = sym("states")
    wr = walker("states")
    rej = {}
    for seed in range(1, 4000):
        x, k = seed, 0
        while True:
            x = gen41.xorshift(x)
            k += 1
            if (x >> 8) & 31 < 24:
                break
        if k in rej:
            continue
        wr.mem[st["seed"]], wr.mem[st["seed"] + 1] = seed & 255, seed >> 8
        rej[k] = wr.call("rowrej")
        if len(rej) == 4:
            break
    ks = sorted(rej)
    step = rej[ks[1]] - rej[ks[0]]
    assert all(rej[k] == rej[ks[0]] + (k - ks[0]) * step for k in ks)
    out["rowrej"] = {"one": rej[1], "each_more": step}
    took = gen41.rowrej_rows(1, gen41.PERIOD)[1]
    out["rowrej"]["most"] = rej[1] + (max(took) - 1) * step
    out["rowrej"]["average"] = round(rej[1] + step * (sum(took) - len(took)) / len(took), 1)
    out["rowmul"] = {v: wr.call("rowmul", a=v) for v in (0, 255)}
    assert len(set(out["rowmul"].values())) == 1
    out["rowmul"] = out["rowmul"][0]
    mods = {v: wr.call("rowmod", a=v) for v in range(256)}
    numbers = [x >> 8 for x in gen41.random_states(1, gen41.PERIOD)]
    out["rowmod"] = {"least": min(mods.values()), "most": max(mods.values()),
                     "average": round(sum(mods[n] for n in numbers) / len(numbers), 1)}
    return out


# ---------------------------------------------------------------- answers
def answers():
    m = json.loads((HERE / "meas41.json").read_text())
    rr, st, pr, rw = m["rreg"], m["states"], m["prices"], m["rows"]
    out = {}
    # 1: 15 NOPs more after LD B,C: 64 fetches a pass
    q1 = {}
    for t in ("eu", "jp"):
        k = rr[t]["step"] + 15
        first = rr[t]["first"]
        nums = [(first + 5 + k * i) & 0x7F for i in range(gen41.RREG_PASSES)]
        q1[t] = {"fetches": k, "pixels": sorted(pairs_plotted(nums, first)), "numbers": sorted(set(nums))}
    out["q1"] = q1
    # 2: 4x + 1
    x, seq = 0, []
    for _ in range(8):
        x = (4 * x + 1) & 255
        seq.append(x)
    out["q2"] = seq
    # 3: the seed 0
    highs = [x >> 8 for x in gen41.random_states(1, gen41.PERIOD)]
    plotted = sum(1 for h in highs if h < 192)
    t1 = plotted * max(m["xorshift"]["first_T"]) + (len(highs) - plotted) * min(m["xorshift"]["first_T"])
    t0 = len(highs) * max(m["xorshift"]["first_T"])
    out["q3"] = {"pixels": 1, "plotted_seed1": plotted, "T_seed1": t1, "T_seed0": t0, "later": t0 - t1}
    # 4: the numbers rowrej took
    out["q4"] = {"numbers": rw["took"]["numbers"], "most": rw["took"]["most"]}
    # 5: the second play a frame later: the seed one more
    s2 = st["eu"]["seeds"][1]
    a, b = set(gen41.play_cells(s2)), set(gen41.play_cells(s2 + 1))
    out["q5"] = {"seed": s2 + 1, "both": len(a & b), "cells": len(b)}
    # 6: the rows rowmul gives 11 bytes
    cnt = [sum(1 for v in range(256) if gen41.rowmul(v) == r) for r in range(24)]
    out["q6"] = {"eleven": [r for r in range(24) if cnt[r] == 11], "ten": [r for r in range(24) if cnt[r] == 10]}
    return out


OPENMSX_SECTIONS = ["rreg", "lcg", "xorshift", "bits", "rows", "states"]


def openmsx():
    if not versions.builds():
        return {"skipped": "OPENMSX_BUILDS not set"}
    return versions.every_build(["ch41"], OPENMSX_SECTIONS)


SECTIONS = {"rreg": rreg, "lcg": lcg, "xorshift": xorshift_, "bits": bits, "rows": rows,
            "states": states, "prices": prices, "answers": answers, "openmsx": openmsx}


def main(names=()):
    CAPS.mkdir(exist_ok=True)
    path_ = HERE / "meas41.json"
    m = json.loads(path_.read_text()) if names and path_.exists() else {}
    for name in names or SECTIONS:
        print(name, flush=True)
        m[name] = SECTIONS[name]()
        m = {k: m[k] for k in SECTIONS if k in m}
        path_.write_text(json.dumps(m, indent=1) + "\n")
    return m


if __name__ == "__main__":
    main(sys.argv[1:])
