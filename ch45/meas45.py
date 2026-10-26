#!/usr/bin/env python3
"""meas45.py -- LANTERN KEEP's world, measured.

    python3 gen45.py && ./build.sh && python3 model45.py && python3 meas45.py
                                  python3 meas45.py films prices   only these

  films     game.rom and torn.rom walked on each machine from the events
            planned for it. The debugger stops where each loop wakes, after
            its sends and at its end, and in the interrupt routine; it reads
            the game's page, the copy of the names, the map's page and the
            rooms' pictures where the loop wakes, and the name table, the
            explorer's attributes and R#3 and R#4 after the sends; a
            watchpoint logs every byte to the VDP's two ports, from INIT. Every
            loop is held against model45.py's game fed the same keys, and its
            T-states against walk.py run on the RAM the debugger read. The
            bytes are played through vdpslots.py (chapter 20): none lost, the
            VRAM at the end the debugger's and the model's, and the moment
            each name of each page reached the VRAM against the moment the
            VDP starts drawing its row
  photos    frames of the walks photographed, each against vdpscreen.py's
            picture of the VRAM line by line, as the bytes reached it
            (figures 45.1 to 45.3)
  prices    what each new routine costs, from walk.py
  machines  the cartridge on every machine of the book: page 2 found, the
            walk the same, and the title's photograph
  answers   the workshop, tried (for Appendix I)
  openmsx   all of it again with every other build (tools/versions.py)
"""
import json
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
import gen45       # noqa: E402
sys.path.remove(str(HERE))
sys.path.insert(0, str(HERE))      # gen45 put other chapters first: this folder's files win
for mod in ("vdpscreen", "walk", "vdpslots"):
    sys.modules.pop(mod, None)
import vdpscreen   # noqa: E402
import walk        # noqa: E402
import vdpslots    # noqa: E402
import model45     # noqa: E402

assert Path(vdpscreen.__file__).parent == HERE and Path(walk.__file__).parent == HERE
assert Path(vdpslots.__file__).parent == HERE

CAPS = HERE / "captures"
SHOTS = HERE / "shots"
EU, JP = gen45.EU, gen45.JP
MACHINES = gen45.MACHINES
TAG = {EU: "eu", JP: "jp"}
L = 228
LINE = vdpslots.LINE
CLOCK = 3579545
FT = {EU: 71364, JP: 59736}
FLAG_LINE = {EU: 261, JP: 234}
PAPER0 = {EU: 69, JP: 42}                   # the paper's first line in the VDP's frame (chapter 33)
SIGNAL = Fraction(101, 3)                   # F rises at T-state 33 2/3 of its line (chapter 19)
TO_PAPER = {EU: 121 * L - SIGNAL, JP: 70 * L - SIGNAL}
BACK = 5 + 11                               # isr's EI and RET, after isrend
POS = "[machine_info VDP_frame_count] [machine_info VDP_cycle_in_frame]"
PROGRAMS = gen45.PROGRAMS
VARS = (gen45.VARS_AT, 128)
NAMES_RAM = (gen45.NAMES_AT, 768)
MAPN = (gen45.MAPN_AT, 736)
MINIS = (gen45.MINIS_AT, 16 * 96)
PALETTE = [tuple(c) for c in json.loads((REPO / "ch01" / "meas01.json").read_text())["palette"]["rgb"]]
CODE = {rgb: n for n, rgb in enumerate(PALETTE) if n}
R15 = 0x8F                                  # register 15 as joy leaves it: port 1, pins 6-7 high

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
VDP_WP = ('debug set_watchpoint write_io {0x98 0x99} {} '
          '{ L "w [expr {$::wp_last_address & 255}] $::wp_last_value ' + POS + '" }\n')
REGS_READ = ('L "regs [debug read {VDP regs} 3] [debug read {VDP regs} 4] '
             '[debug read {VDP regs} 1]"')


def rom(name):
    return HERE / f"{name}.rom"


def sym(name):
    return dbg.sym(HERE / f"{name}.sym")


def t_abs(fc, cyc):
    return int(fc), Fraction(int(cyc), 6)


def num(f):
    return int(f) if f == int(f) else round(float(f), 2)


def events(machine):
    return model45.read_events(model45.events_path(machine))


def run(name, machine, frames, tcl, path=None, ev=None, at_end=None):
    ev = events(machine) if ev is None else ev
    tev = model45.tcl_events(ev)
    if at_end:
        tev[frames - 1] = (tev[frames - 1] + "; " if frames - 1 in tev else "") + at_end
    lines = msxcap.run_tcl(path or rom(name), frames, F0 + TOO_FAST + tcl, machine=machine,
                           tcl_setup=STATE, timeout=3600, events=tev)
    return [l.split() for l in lines]


def codes(png):
    im = Image.open(png).convert("RGB")
    px = im.load()
    return [[CODE.get(px[x, y]) for x in range(im.width)] for y in range(im.height)]


def loops_planned(machine):
    keys, g, recs = model45.plan(machine)
    return len(recs)


PLAY_FRAMES = {m: loops_planned(m) + model45.EVENT_AHEAD + 1 for m in MACHINES}


# ---------------------------------------------------------------- what the RAM says
def ram_state(s, v):
    def at(label, k=1):
        a = s[label] - VARS[0]
        return v[a] if k == 1 else list(v[a:a + k])
    return {"stat": at("stat"), "ticks": at("ticks") | at("ticks", 2)[1] << 8, "state": at("state"),
            "was": at("was"), "room": at("room"), "seen": at("seen"), "fresh": at("fresh"),
            "queued": at("queued"), "keepy": at("keepy"), "whole": at("whole"),
            "wsrc": at("wsrc") | at("wsrc", 2)[1] << 8, "wr3": at("wr3"), "wr4": at("wr4"),
            "copy": at("copy", 5), "due": at("due") | at("due", 2)[1] << 8,
            "lines": at("lines") | at("lines", 2)[1] << 8, "been": at("been", 16), "held": at("held")}


def model_ram(g):
    r = g.ram()
    r["held"] = g.held
    return r


# ---------------------------------------------------------------- walk
def walker(name, rate, keys_=frozenset(), path=None):
    wk = walk.Walk(path or HERE / name)
    psg = {"reg": 0}
    keys = {"held": set(keys_)}

    def read_port(port, t):
        if port == 0xA9:
            sel = [v for _, p, v in wk.ports if p == 0xAA]
            row = (sel[-1] if sel else 0) & 15
            v = 0xFF
            for k in keys["held"]:
                if row == 8:
                    v &= ~model45.ROW8.get(k, 0) & 0xFF
                elif row == 4:
                    v &= ~model45.ROW4.get(k, 0) & 0xFF
            return v
        if port == 0xA2:
            last = [v for _, p, v in wk.ports if p == 0xA0]
            psg["reg"] = last[-1] if last else 0
            return {14: model45.JOY_IDLE, 15: R15}.get(psg["reg"], 0)
        if port == 0xAA:
            return 0x50
        return 0x80
    wk.read_port = read_port
    wk.keys = keys
    wk.mem[0x2B] = rate
    return wk


def walk_from(wk, mem_blocks, start, stop):
    for addr, data in mem_blocks:
        wk.mem[addr:addr + len(data)] = data
    wk.ports.clear()
    return wk.run(start, stop)


# ---------------------------------------------------------------- the films
KINDS = ("isr", "isrend", "woke", "sent", "ran", "input", "show", "flip0", "map0", "mini")


def film(name, machine, frames, path=None, ev=None, light=False):
    """the debugger's log of a walk"""
    s = dbg.sym(path.with_suffix(".sym")) if path else sym(name)
    if light:
        tcl = "".join(f'debug set_bp {s[k]} {{}} {{ L "{k} {POS}" }}\n'
                      for k in ("isr", "isrend", "woke", "sent", "ran", "input"))
        tcl += f'debug set_bp {s["woke"]} {{}} {{ M v {VARS[0]} {VARS[1]} }}\n'
    else:
        tcl = (f'debug set_bp {s["isr"]} {{}} {{ L "isr {POS}"; M v {VARS[0]} {VARS[1]} }}\n'
               f'debug set_bp {s["isrend"]} {{}} {{ L "isrend {POS}" }}\n'
               f'debug set_bp {s["woke"]} {{}} {{ L "woke {POS}"; M v {VARS[0]} {VARS[1]}; '
               f'M nm {NAMES_RAM[0]} {NAMES_RAM[1]}; M mp {MAPN[0]} {MAPN[1]}; '
               f'M mi {MINIS[0]} {MINIS[1]} }}\n'
               f'debug set_bp {s["sent"]} {{}} {{ L "sent {POS}"; VR sat {model45.SAT} 5; '
               f'VR names {0x1800} 768; {REGS_READ} }}\n'
               f'debug set_bp {s["ran"]} {{}} {{ L "ran {POS}" }}\n' +
               "".join(f'debug set_bp {s[k]} {{}} {{ L "{k} {POS}" }}\n'
                       for k in ("input", "show", "flip0", "map0", "mini")) + VDP_WP)
    w = run(name, machine, frames, tcl, path=path.with_suffix(".rom") if path else None, ev=ev,
            at_end=None if light else f'VR end 0 16384')
    f0 = int(next(x for x in w if x[0] == "f0")[1])
    assert not [x for x in w if x[0] == "fast"], (name, machine, "an access too soon")
    out, pend, writes, regs = [], {}, [], []
    for x in w:
        k = x[0]
        if k in KINDS:
            f, c = t_abs(x[1], x[2])
            e = {"kind": k, "frame": f - f0, "t": f * FT[machine] + c}
            out.append(e)
            pend = e
        elif k == "w":
            writes.append((int(x[3]) - f0, int(x[4]), int(x[1]), int(x[2])))
        elif k == "regs":
            pend["regs"] = [int(v) for v in x[1:]]
        elif len(x) == 3 and x[1] in ("mem", "vram"):
            pend[x[0]] = bytes.fromhex(x[2])
    end = next((x for x in w if x[0] == "end"), None)
    return f0, out, s, writes, (bytes.fromhex(end[2]) if end else None)


def signal_of(frame, machine):
    return frame * FT[machine] + FLAG_LINE[machine] * L + SIGNAL


def loops_of(ev):
    """the films cut into loops: the interrupt that woke each, where it woke,
    its sends' end, its end, and the marks inside"""
    loops = []
    idx = [i for i, e in enumerate(ev) if e["kind"] == "woke"]
    for a, b in zip(idx, idx[1:] + [len(ev)]):
        seg = ev[a:b]
        kinds = [e["kind"] for e in seg]
        if "ran" not in kinds:
            continue
        j = max(i for i in range(a) if ev[i]["kind"] == "isr")
        wake = ev[j]
        wake_end = next(e for e in ev[j:a] if e["kind"] == "isrend")
        ran = next(e for e in seg if e["kind"] == "ran")
        sent = next(e for e in seg if e["kind"] == "sent")
        inside = [e for e in seg if e["kind"] == "isr" and e["t"] < ran["t"]]
        loops.append({"woke": ev[a], "sent": sent, "ran": ran, "wake": wake, "wake_end": wake_end,
                      "inside": inside,
                      "input": [e for e in ev[j:a] if e["kind"] == "input"],
                      "marks": {k: [e for e in seg if e["kind"] == k and e["t"] < ran["t"]]
                                for k in ("show", "flip0", "map0", "mini")}})
    return loops


def model_for(name, machine, **kw):
    return model45.Keep(machine, torn=(name == "torn"), **kw)


def analyse(name, machine, ev=None, frames=None, path=None, **kw):
    """a walk of NAME on MACHINE against the model fed the same keys"""
    ev = events(machine) if ev is None else ev
    nloops = frames or PLAY_FRAMES[machine]
    f0, evs, s, writes, end_vram = film(name, machine, nloops, path=path, ev=ev)
    loops = loops_of(evs)
    g = model_for(name, machine, **kw)
    rate = 0x80 if machine == EU else 0
    wk = walker(name, rate, path=path)
    rows, pages = [], []
    tail = wk.run("ran", "frame")
    for k, lp in enumerate(loops):
        wake_frame = lp["wake"]["frame"]
        sig = signal_of(wake_frame + f0, machine)
        assert sig <= lp["wake"]["t"] < sig + 40, (name, machine, k)
        g.loop += 1
        keys = model45.keys_at(ev, g.ticks + 1 + model45.EVENT_AHEAD)
        g.isr(keys)
        got = ram_state(s, lp["woke"]["v"])
        want = model_ram(g)
        assert got == want, (name, machine, k, {x: (got[x], want[x]) for x in got if got[x] != want[x]})
        assert list(lp["woke"]["nm"]) == g.names, (name, machine, k, "the copy of the names")
        assert list(lp["woke"]["mp"]) == g.mapn or g.mapn == [0] * 736 and not any(lp["woke"]["mp"]), \
            (name, machine, k, "the map's page")
        assert list(lp["woke"]["mi"]) == sum(g.minis, []), (name, machine, k, "the pictures")
        assert got["ticks"] == wake_frame - model45.EVENT_AHEAD, (name, machine, k, "ticks", got["ticks"], wake_frame)
        state0, room0 = g.state, g.room
        g.sends()
        assert list(lp["sent"]["sat"]) == g.copy, (name, machine, k, "the attributes")
        assert list(lp["sent"]["names"]) == g.vnames, (name, machine, k, "the names",
                                                       [(i, a, b) for i, (a, b) in
                                                        enumerate(zip(lp["sent"]["names"], g.vnames)) if a != b][:8])
        assert lp["sent"]["regs"][:2] == [g.r3, g.r4], (name, machine, k, "R#3, R#4")
        wk.keys["held"] = set(keys)
        blocks = [(VARS[0], lp["woke"]["v"]), (NAMES_RAM[0], lp["woke"]["nm"]), (MAPN[0], lp["woke"]["mp"]),
                  (MINIS[0], lp["woke"]["mi"])]
        t_walk = walk_from(wk, blocks, "woke", "ran")
        took = lp["ran"]["t"] - lp["woke"]["t"]
        assert not lp["inside"], (name, machine, k, "an interrupt inside")
        assert all(e["frame"] == wake_frame for e in lp["input"]), (name, machine, k, "keys late")
        assert took == t_walk, (name, machine, k, took, t_walk)
        t_sends = walk_from(wk, blocks, "woke", "sent")
        assert t_sends == lp["sent"]["t"] - lp["woke"]["t"], (name, machine, k, "sends")
        ti = walk_from(wk, [(VARS[0], lp["wake"]["v"])], "isr", "isrend")
        assert ti == lp["wake_end"]["t"] - lp["wake"]["t"], (name, machine, k, "isr")
        nsteps = len(g.steps_taken)
        screen_sends = g.screen
        g.run()
        steps = g.steps_taken[-1][1] if len(g.steps_taken) > nsteps else 0
        for kk in ("show",):
            for e in lp["marks"][kk]:
                kind = ("room" if lp["marks"]["flip0"] or state0 == model45.FLIP else
                        "map" if state0 == model45.MAP and g.wsrc == "mapn" else "back")
                pages.append({"loop": k, "frame": wake_frame, "t": num(e["t"] - sig),
                              "room": g.room, "kind": kind})
        nxt = loops[k + 1]["wake"]["frame"] if k + 1 < len(loops) else None
        rows.append({"loop": k, "frame": wake_frame, "ticks": got["ticks"], "state": state0,
                     "room": room0, "wake": num(lp["wake"]["t"] - sig),
                     "isr": num(lp["wake_end"]["t"] - lp["wake"]["t"] + BACK),
                     "sends": num(lp["sent"]["t"] - lp["woke"]["t"]),
                     "logic": num(lp["ran"]["t"] - lp["sent"]["t"]),
                     "woke": num(lp["woke"]["t"] - sig), "sent": num(lp["sent"]["t"] - sig),
                     "halt": num(lp["ran"]["t"] + tail - sig),
                     "lost": None if nxt is None else nxt - wake_frame - 1,
                     "held": got["held"], "page": screen_sends, "steps": steps,
                     "marks": {kk: [num(e["t"] - sig) for e in v] for kk, v in lp["marks"].items() if v}})
    return {"f0": f0, "rows": rows, "tail": tail, "ev": evs, "game": g, "writes": writes,
            "end_vram": end_vram, "pages": pages}


# ---------------------------------------------------------------- the bytes to the VDP
def taken_writes(res, machine):
    """the film's bytes to the VDP played through vdpslots: (data, regs,
    lost): data [(cycle taken, address, value)], regs [(cycle, reg, value)],
    the cycles counted from the start of film frame 0"""
    flen = vdpslots.LINES[machine] * LINE
    evs = [(fr * flen + cyc, port, val) for fr, cyc, port, val in res["writes"]]
    assert evs == sorted(evs, key=lambda e: e[0])
    taken = {}
    vram, _, lost = vdpslots.play(evs, machine, vram=bytes(16384), regs=[0, 0xE0, 0, 0, 0, 0, 0, 0],
                                  taken=taken)
    data, regs_, held, addr = [], [], None, 0
    for i, (c, port, v) in enumerate(evs):
        if port == 0x99:
            if held is None:
                held = v
            else:
                if v & 0x80:
                    regs_.append((c, v & 7, held))
                else:
                    addr = (v & 0x3F) << 8 | held
                held = None
        else:
            held = None
            if i not in lost:
                data.append((taken[i], addr, v))
            addr = (addr + 1) & 0x3FFF
    data.sort()
    return data, regs_, lost, vram


def row_start(frame, row, machine):
    """the cycle at which the VDP starts drawing row ROW of the paper in film
    frame FRAME"""
    flen = vdpslots.LINES[machine] * LINE
    return frame * flen + (PAPER0[machine] + 8 * row) * LINE + vdpslots.BORDER_IN


def sig_cycle(frame, machine):
    """the cycle of film frame FRAME's signal, from the start of film frame 0"""
    return frame * vdpslots.LINES[machine] * LINE + FLAG_LINE[machine] * LINE + vdpslots.BORDER_IN


def page_margins(res, machine, data):
    """for each page sent, the names of rows 1 to 23 and the moment each
    reached the VRAM, against the moment the VDP starts drawing its row in
    the picture after the signal that woke the loop: the least margin, in
    T-states, and its row; the names the beam had passed; the last name's
    moment after the signal"""
    out = []
    for p in res["pages"]:
        fr = p["frame"]
        lo = sig_cycle(fr, machine)
        hi = sig_cycle(fr + 1, machine)
        names = [(c, a) for c, a, _ in data if lo <= c < hi and 0x1820 <= a < 0x1B00]
        assert len(names) == 736, (machine, p, len(names))
        marg = [(Fraction(row_start(fr + 1, (a - 0x1800) // 32, machine) - c, 6), (a - 0x1800) // 32)
                for c, a in names]
        least = min(marg)
        last = max(c for c, _ in names)
        out.append(dict(p, least=num(least[0]), least_row=least[1], behind=sum(1 for m, _ in marg if m <= 0),
                        last=num(Fraction(last - lo, 6))))
    return out


def jsonable(e):
    return [list(x) if isinstance(x, tuple) else x for x in e]


def summary(rows, machine):
    rows = rows[1:]
    out = {"loops": len(rows), "lost": sum(r["lost"] or 0 for r in rows),
           "isr": [min(r["isr"] for r in rows), max(r["isr"] for r in rows)],
           "sent_max": max(r["sent"] for r in rows), "halt_max": max(r["halt"] for r in rows),
           "states": {},
           "steps": {str(b): sum(1 for r in rows if r["steps"] == b) for b in sorted({r["steps"] for r in rows})}}
    for i, st in enumerate(gen45.STATES):
        rs = [r for r in rows if r["state"] == i]
        if not rs:
            continue
        out["states"][st] = {"loops": len(rs),
                             "sends": [min(r["sends"] for r in rs), max(r["sends"] for r in rs)],
                             "logic": [min(r["logic"] for r in rs), max(r["logic"] for r in rs)],
                             "halt": max(r["halt"] for r in rs)}
    out["to_paper"] = num(TO_PAPER[machine])
    out["left"] = num(FT[machine] - out["halt_max"])
    return out


CACHE = {}


def films():
    out = {}
    for name in PROGRAMS:
        out[name] = {}
        for m in MACHINES:
            res = analyse(name, m)
            CACHE[(name, m)] = res
            rows, g = res["rows"], res["game"]
            data, regs_, lost, vram = taken_writes(res, m)
            assert not lost, (name, m, "bytes lost", len(lost))
            ev_ = res["end_vram"]
            spans = [(0, 0x1B05), (0x2000, 0x3800), (0x3800, 0x3820)]
            assert all(ev_[a:b] == vram[a:b] for a, b in spans), (name, m, "the VRAM played")
            gv = g.vram
            assert all(ev_[a:b] == bytes(gv[a:b]) for a, b in spans), (name, m, "the VRAM modelled")
            margins = page_margins(res, m, data)
            out[name][TAG[m]] = {"rows": rows, "f0": res["f0"], "tail": res["tail"],
                                 "events": [jsonable(e) for e in g.events],
                                 "summary": summary(rows, m), "pages": margins,
                                 "writes": len(res["writes"])}
            print(name, TAG[m], out[name][TAG[m]]["summary"], flush=True)
    return out


# ---------------------------------------------------------------- the photos
class Rows(dict):
    """a frame's rows where only one is kept: sprites() draws into the others
    and nothing looks at them"""
    def __missing__(self, k):
        return [0] * 256


def render_line(vram, regs, y):
    row = vdpscreen.graphic2_line(vram, regs, vdpscreen.bases(regs), y) if regs[1] & 0x40 else \
        [vdpscreen.colour(0, regs)] * 256
    if regs[1] & 0x40:
        rows = Rows({y: row})
        vdpscreen.sprites(vram, regs, rows)
    return row


def line_pictures(data, regs_changes, machine, frames):
    """for each film frame of FRAMES, the paper line by line: the VRAM and the
    registers as they stand where the VDP starts drawing the line, and, for a
    line during which a byte reached the VRAM, the line after it too (chapter
    40): {frame: (picture, {line: the other picture})}"""
    vram = bytearray(16384)
    regs = [0] * 8
    j = k = 0
    out = {}
    for n in sorted(frames):
        rows, mixed = [], {}
        for y in range(192):
            ls = row_start(n, 0, machine) + y * LINE
            while j < len(data) and data[j][0] < ls:
                vram[data[j][1]] = data[j][2]
                j += 1
            while k < len(regs_changes) and regs_changes[k][0] < ls:
                regs[regs_changes[k][1]] = regs_changes[k][2]
                k += 1
            rows.append(render_line(vram, regs, y))
            inside = [d for d in data[j:j + 64] if d[0] < ls + LINE]
            if inside:
                after = bytearray(vram)
                for _, a, v in inside:
                    after[a] = v
                mixed[y] = render_line(after, regs, y)
        out[n] = (rows, mixed)
    return out


def full_picture(paper):
    out = []
    for y in range(meas.CAPTURE_H):
        row = [None] * meas.CAPTURE_W
        for x in range(meas.DRAWN[0], meas.DRAWN[1] + 1):
            px, py = x - meas.PAPER_X0, y - meas.PAPER_Y0
            row[x] = paper[py][px] if 0 <= px < 256 and 0 <= py < 192 else gen45.BORDER
        out.append(row)
    return out


def against(photo, pic, mixed):
    """pixels of the capture's drawn part that are neither the model's line
    nor, in a line where a byte reached the VRAM, the line after it"""
    full = full_picture(pic)
    alt = {y: full_picture_line(mixed[y]) for y in mixed}
    bad = 0
    for y in range(meas.CAPTURE_H):
        py = y - meas.PAPER_Y0
        for x in range(meas.DRAWN[0], meas.DRAWN[1] + 1):
            if photo[y][x] != full[y][x] and not (py in alt and photo[y][x] == alt[py][x]):
                bad += 1
    return bad


def full_picture_line(line):
    row = [None] * meas.CAPTURE_W
    for x in range(meas.DRAWN[0], meas.DRAWN[1] + 1):
        px = x - meas.PAPER_X0
        row[x] = line[px] if 0 <= px < 256 else gen45.BORDER
    return row


def photo_set(name, machine, res, frames, keep=(), tag=None):
    """FRAMES of NAME's film photographed and held against the line by line
    model; the one offset that fits"""
    data, regs_, lost, _ = taken_writes(res, machine)
    want = sorted(frames)
    models = line_pictures(data, regs_, machine, want)
    shots = sorted({c + d for c in want for d in (-1, 0, 1)})
    tmp = Path(tempfile.mkdtemp(prefix="ph45_"))
    pngs = msxcap.capture(rom(name), shots, tmp, f"{name}_{TAG[machine]}_f", machine=machine,
                          events=model45.tcl_events(events(machine)), timeout=3600)
    ph = {c: codes(pngs[c]) for c in shots}
    fits = [d for d in (-1, 0, 1) if all(against(ph[c + d], *models[c]) == 0 for c in want[:3])]
    assert len(fits) == 1, (name, machine, fits,
                            [(c, d, against(ph[c + d], *models[c])) for c in want[:3] for d in (-1, 0, 1)])
    d = fits[0]
    bad = {c: against(ph[c + d], *models[c]) for c in want}
    assert not any(bad.values()), (name, machine, {c: b for c, b in bad.items() if b})
    out = {}
    for c in want:
        dest = (CAPS if c in keep else SHOTS) / pngs[c + d].name.replace(f"_f{c + d:04d}", f"_f{c:04d}")
        dest.parent.mkdir(exist_ok=True)
        shutil.copy(pngs[c + d], dest)
        out[c] = dest.name
    shutil.rmtree(tmp)
    return d, out, {c: sorted(models[c][1]) for c in want}


def rows_shown(data, machine, page, old, new):
    """a page's picture, row by row: for each of rows 1 to 23, the lines of
    its eight that showed the old room's names, the new room's, or a mix"""
    fr = page["frame"] + 1
    names = {}
    out = []
    lo = sig_cycle(page["frame"], machine)
    arrive = {a - 0x1800: c for c, a, _ in data if lo <= c < sig_cycle(fr, machine) and 0x1820 <= a < 0x1B00}
    for r in range(1, 24):
        kinds = []
        for k in range(8):
            ls = row_start(fr, r, machine) + k * LINE
            got = [arrive[32 * r + c] < ls for c in range(32)]
            kinds.append("new" if all(got) else "old" if not any(got) else "mix")
        out.append(kinds)
    return out


FIG_FLIP = 1                 # figure 45.2: the second flip, out of the gate hall


def photo_plan(pages):
    """the frames the figures use, from a film's pages: each room's first
    picture, the flip of figure 45.2 (the frame before its page and the
    page's), and each map"""
    rooms, seen = {}, set()
    for p in pages:
        if p["kind"] == "room" and p["room"] not in seen:
            seen.add(p["room"])
            rooms[p["room"]] = p["frame"] + 1
    flip = [p for p in pages if p["kind"] == "room"][FIG_FLIP]
    return {"rooms": [rooms[k] for k in range(gen45.ROOMS)], "flip": [flip["frame"], flip["frame"] + 1],
            "flip_room": flip["room"], "maps": [p["frame"] + 1 for p in pages if p["kind"] == "map"]}


def photos(cache=CACHE):
    """every page's picture and the frame before it, on both machines, for
    both programs; the figures' frames kept in captures/"""
    out = {}
    for m in MACHINES:
        for name in PROGRAMS:
            res = cache.get((name, m)) or analyse(name, m)
            cache[(name, m)] = res
            pages = res["pages"]
            frames = sorted({p["frame"] + 1 for p in pages} | {p["frame"] for p in pages})
            plan = photo_plan(pages)
            keep = set()
            if name == "game" and m == EU:
                keep = set(plan["rooms"]) | set(plan["maps"])
            if name == "game" and m == JP:
                keep = set(plan["flip"])
            if name == "torn":
                keep = {plan["flip"][1]}
            d, shots, mixed = photo_set(name, m, res, frames, keep=keep)
            data, _, _, _ = taken_writes(res, m)
            fp = [p for p in pages if p["kind"] == "room"][FIG_FLIP]
            out.setdefault(name, {})[TAG[m]] = {"offset": d, "frames": shots, "plan": plan,
                                               "flip_rows": rows_shown(data, m, fp, None, None),
                                               "mixed": {str(c): len(v) for c, v in mixed.items() if v}}
            print("photos", name, TAG[m], d, len(shots), plan, flush=True)
    return out


# ---------------------------------------------------------------- prices
def fresh(name="game", machine=JP):
    wk = walker(name, 0x80 if machine == EU else 0)
    wk.init_t = wk.run("init", "main")
    return wk


def poke(wk, label, vals, off=0):
    a = wk.sym[label] + off
    for i, v in enumerate(vals):
        wk.mem[a + i] = v & 255


def peek(wk, label, n=1, off=0):
    a = wk.sym[label] + off
    return list(wk.mem[a:a + n])


def in_room(k, name="game", seen_all=False):
    """a walker in room K, its page sent, the explorer at its first place"""
    wk = fresh(name)
    wk.call("setup")
    poke(wk, "room", [k])
    if seen_all:
        poke(wk, "been", [1] * 16)
    wk.call("flip0")
    poke(wk, "queued", [0])
    poke(wk, "whole", [0])
    poke(wk, "state", [model45.PLAY])
    poke(wk, "fresh", [0])
    return wk


def held_of(keys):
    return model45.keys_byte(set(keys))


def prices():
    out = {}
    wk = fresh()
    out["init"] = wk.init_t
    out["isr"] = fresh().call("isr")
    # unpack, room by room, and flip0 with the room seen for the first time
    out["unpack"], out["flip0_new"], out["flip0_old"] = [], [], []
    for k in range(gen45.ROOMS):
        wk = fresh()
        wk.call("setup")
        out["unpack"].append(wk.call("unpack", a=k))
        assert list(wk.mem[gen45.NAMES_AT + 32:gen45.NAMES_AT + 768]) == sum(gen45.grid(k), [])
        wk = fresh()
        wk.call("setup")
        poke(wk, "room", [k])
        out["flip0_new"].append(wk.call("flip0"))
        poke(wk, "queued", [0])
        out["flip0_old"].append(wk.call("flip0"))
    out["runs"] = [len(r) for r in gen45.RUN_BYTES]
    wk = in_room(gen45.START)
    out["rname"] = wk.call("rname")
    poke(wk, "queued", [0])
    poke(wk, "been", [0] * 16)
    out["visit_new"] = wk.call("visit")
    poke(wk, "queued", [0])
    out["visit_old"] = wk.call("visit")
    # the picture
    wk = in_room(gen45.START)
    out["mini"] = wk.call("mini")
    want = model45.picture_bytes(list(wk.mem[gen45.NAMES_AT:gen45.NAMES_AT + 768]))
    assert peek(wk, "minis", 96, 96 * gen45.START) == want
    pic = wk.sym["minis"] + 96 * gen45.START
    out["picture"] = wk.call("picture", h=pic >> 8, l=pic & 255, d=0x40, e=0)
    out["picat"] = wk.call("picat", a=gen45.START)
    # the map: one room seen, six, sixteen
    out["mapbuild"] = {}
    for n in (1, 6, 16):
        wk = in_room(gen45.START)
        poke(wk, "been", [1] * n + [0] * (16 - n))
        out["mapbuild"][str(n)] = wk.call("mapbuild")
    wk = in_room(gen45.START, seen_all=True)
    out["map0"] = wk.call("map0")
    out["page"] = in_room(gen45.START).call("page", h=0xC4, l=0x20, d=0, e=0x9F)
    # the sends: nothing queued; four names; a whole page
    wk = in_room(gen45.START)
    out["sends"] = wk.call("sends")
    for c in range(4):
        wk.call("post", a=0x30, h=(gen45.NAMES_AT + c) >> 8, l=(gen45.NAMES_AT + c) & 255)
    out["sends_four"] = wk.call("sends")
    poke(wk, "whole", [1])
    poke(wk, "wsrc", [0x20, gen45.NAMES_AT >> 8])
    poke(wk, "wr3", [gen45.GAME_R3, gen45.GAME_R4])
    out["sends_page"] = wk.call("sends")
    out["show"] = in_room(gen45.START).call("show", h=(gen45.NAMES_AT + 32) >> 8, l=0x20, e=0x9F, d=0)
    # presses, paced
    wk = in_room(gen45.START)
    out["presses"] = wk.call("presses")
    poke(wk, "due", [262 & 255, 262 >> 8])
    out["paced_one"] = wk.call("paced")
    # walk: no keys; LEFT on the floor; LEFT into a wall; out by the left door;
    # LEFT and UP on the floor
    walks = {}
    for tag, keys, place in (("none", (), gen45.HOME), ("left", ("left",), gen45.HOME),
                             ("wall", ("left",), (8, 39)), ("out", ("left",), (0, 103)),
                             ("diagonal", ("left", "up"), gen45.HOME)):
        wk = in_room(gen45.START)
        poke(wk, "held", [held_of(keys)])
        poke(wk, "copy", [place[1], place[0]])
        walks[tag] = wk.call("walk")
        walks[tag + "_xy"] = peek(wk, "copy", 2)[::-1]
    out["walk"] = walks
    assert walks["wall_xy"] == [8, 39] and walks["left_xy"] == [118, 103]
    wk = in_room(gen45.START)
    poke(wk, "copy", [103, 0])
    wk.r["d"] = 3
    out["leave"] = wk.run("leave", "go")
    out["title0"] = fresh().call("title0")
    out["setup"] = fresh().call("setup")
    wk = fresh()
    out["sets"] = wk.call("sets")
    return out


# ---------------------------------------------------------------- every machine
OTHERS = ["MSXBOOK_EU32", "MSXBOOK_EU64", "MSXBOOK_EU16X", "MSXBOOK_EU16E", "MSXBOOK_EU16AY",
          "MSXBOOK_EU16P", "MSXBOOK_EU16G"]


def light_loops(name, machine, real=EU, frames=None):
    """the walk planned for REAL's rate on MACHINE: at each wake the game's
    page and the copy of the names; at the end of INIT the slots"""
    s = sym(name)
    tcl = "".join(f'debug set_bp {s[k]} {{}} {{ L "{k} {POS}" }}\n'
                  for k in ("isr", "isrend", "woke", "sent", "ran", "input"))
    tcl += f'debug set_bp {s["woke"]} {{}} {{ M v {VARS[0]} {VARS[1]}; M nm {NAMES_RAM[0]} {NAMES_RAM[1]} }}\n'
    tcl += (f'set ::m [debug set_bp {s["main"]} {{}} {{ L "slots [string map {{"\n" "|"}} [slotselect]]"; '
            f'debug remove_bp $::m }}]\n')
    w = run(name, machine, frames or PLAY_FRAMES[real], tcl, ev=events(real))
    f0 = int(next(x for x in w if x[0] == "f0")[1])
    slots = " ".join(next(x for x in w if x[0] == "slots")[1:])
    evs, pend = [], {}
    for x in w:
        if x[0] in KINDS:
            f, c = t_abs(x[1], x[2])
            pend = {"kind": x[0], "frame": f - f0, "t": f * FT[real] + c}
            evs.append(pend)
        elif len(x) == 3 and x[1] == "mem":
            pend[x[0]] = bytes.fromhex(x[2])
    out = []
    for lp in loops_of(evs):
        out.append({"frame": lp["wake"]["frame"], "v": lp["woke"]["v"], "nm": lp["woke"]["nm"]})
    return out, slots, s


def machines():
    """the cartridge on every machine: the walk planned for the 50 Hz
    machine, loop for loop against the model, and the title's photograph"""
    out = {}
    for m in OTHERS:
        rows, slots, s = light_loops("game", m)
        g = model_for("game", EU)
        bad = []
        for k, r in enumerate(rows):
            g.loop += 1
            g.isr(model45.keys_at(events(EU), g.ticks + 1 + model45.EVENT_AHEAD))
            if ram_state(s, r["v"]) != model_ram(g) or list(r["nm"]) != g.names:
                bad.append(k)
            g.sends()
            g.run()
        d, mism = title_photo(m)
        out[m] = {"loops": len(rows), "wrong": bad[:10], "slots": slots, "title_offset": d,
                  "title_mismatch": mism}
        print("machine", m, out[m], flush=True)
    # the 8 KB machine: no RAM at $C000
    tmp = Path(tempfile.mkdtemp(prefix="mc45_"))
    pngs = msxcap.capture(rom("game"), [TITLE_FRAME, 200], tmp, "eu8_f", machine="MSXBOOK_EU8", timeout=600)
    a, b = codes(pngs[TITLE_FRAME]), codes(pngs[200])
    SHOTS.mkdir(exist_ok=True)
    shutil.copy(pngs[200], SHOTS / "eu8_f0200.png")
    shutil.rmtree(tmp)
    probe = 'after time 2 { L "pc [format %04X [reg pc]] sp [format %04X [reg sp]] iff [reg iff]" }\n'
    regs = {}
    for m in ("MSXBOOK_EU8", "MSXBOOK_EU16"):
        lines = msxcap.run_tcl(rom("game"), 200, probe, machine=m, timeout=600)
        regs[m] = next(l for l in lines if l.startswith("pc")).split()[1::2]
    title = full_picture(title_paper())
    out["MSXBOOK_EU8"] = {"still": sum(1 for y in range(meas.CAPTURE_H) for x in range(meas.CAPTURE_W)
                                       if a[y][x] != b[y][x]),
                          "title_at_200": sum(1 for y in range(meas.CAPTURE_H)
                                              for x in range(meas.DRAWN[0], meas.DRAWN[1] + 1)
                                              if title[y][x] != b[y][x]),
                          "regs": regs}
    print("machine EU8", out["MSXBOOK_EU8"], flush=True)
    return out


TITLE_FRAME = 43


def title_paper():
    """the title as the model leaves it before any key: the names, the
    explorer"""
    g = model_for("game", EU)
    v = g.vram
    v[model45.SAT:model45.SAT + 5] = bytes(g.copy)
    return vdpscreen.draw(v, g.regs())


def title_photo(machine, frame=TITLE_FRAME):
    tmp = Path(tempfile.mkdtemp(prefix="mc45_"))
    pngs = msxcap.capture(rom("game"), [frame - 1, frame, frame + 1], tmp, f"title_{machine}_f",
                          machine=machine, timeout=600)
    model = full_picture(title_paper())
    ph = {d: codes(pngs[frame + d]) for d in (-1, 0, 1)}
    fits = {d: sum(1 for y in range(meas.CAPTURE_H) for x in range(meas.DRAWN[0], meas.DRAWN[1] + 1)
                   if model[y][x] != ph[d][y][x]) for d in (-1, 0, 1)}
    shutil.rmtree(tmp)
    best = min(fits, key=lambda d: fits[d])
    return best, fits[best]


# ---------------------------------------------------------------- the workshop
def build_variant(name="game", **kw):
    d = Path(tempfile.mkdtemp(prefix="v45_"))
    for f in ("msx.inc", "bios.inc"):
        shutil.copy(HERE / f, d / f)
    stem = name + "_" + "_".join(f"{k}" for k in sorted(kw))
    (d / f"{stem}.asm").write_text(gen45.program(name, **kw).replace(f'OUTPUT "{name}.rom"',
                                                                    f'OUTPUT "{stem}.rom"'))
    subprocess.run(["sjasmplus", "--nologo", "--msg=err", "--syntax=bFw", f"--sym={stem}.sym",
                    f"--lst={stem}.lst", f"{stem}.asm"], cwd=d, check=True)
    return d / stem


def flowing(k):
    """room K's runs if a run could go on into the next row: 1 to 32 cells"""
    cells = sum(gen45.grid(k), [])
    out, c = [], 0
    while c < 736:
        t, n = cells[c], 1
        while c + n < 736 and cells[c + n] == t and n < 32:
            n += 1
        out.append((t, n))
        c += n
    return out


def answers():
    out = {}
    # 1: runs that carry on into the next row: the bytes, and unpack on them
    fl = [flowing(k) for k in range(gen45.ROOMS)]
    q1 = {"bytes": sum(len(r) for r in fl), "rows_bytes": sum(len(r) for r in gen45.RUN_BYTES),
          "per_room": [len(r) for r in fl]}
    wrong = []
    for k in range(gen45.ROOMS):
        wk = fresh()
        wk.call("setup")
        at = wk.mem[0x8000 + 2 * k] | wk.mem[0x8001 + 2 * k] << 8
        bytes_ = [gen45.run_byte(t, n) for t, n in fl[k]]
        wk.mem[at:at + len(bytes_)] = bytes(bytes_)
        try:
            wk.call("unpack", a=k)
            got = list(wk.mem[gen45.NAMES_AT + 32:gen45.NAMES_AT + 768])
            want = sum(gen45.grid(k), [])
            wrong.append(sum(1 for a, b in zip(got, want) if a != b))
        except Exception as e:
            wrong.append(str(e)[:40])
    q1["wrong_cells"] = wrong
    q1["crossing"] = [sum(1 for t, n in _crossings(fl[k])) for k in range(gen45.ROOMS)]
    out["q1"] = q1
    # 2: the map a row up, MAP_Y 3, with gen45.py's assert that a room's three
    # rows of names lie in one third taken out: built, walked on the 50 Hz
    # machine, the last map photographed, and each room's three rows of names
    # read from the model's VRAM: whose picture each shows
    keep = gen45.MAP_Y, gen45.MAP_DIGITS
    try:
        gen45.MAP_Y = 3
        gen45.MAP_DIGITS = [(4, gen45.MAP_Y + 1 + 4 * k, str(k + 1)) for k in range(4)]
        d = Path(tempfile.mkdtemp(prefix="v45_"))
        for f in ("msx.inc", "bios.inc"):
            shutil.copy(HERE / f, d / f)
        (d / "game_mapy3.asm").write_text(gen45.program("game").replace('OUTPUT "game.rom"',
                                                                      'OUTPUT "game_mapy3.rom"'))
        subprocess.run(["sjasmplus", "--nologo", "--msg=err", "--syntax=bFw", "--sym=game_mapy3.sym",
                        "--lst=game_mapy3.lst", "game_mapy3.asm"], cwd=d, check=True)
        path = d / "game_mapy3"
        res = analyse("game", EU, path=path)
        page = [p_ for p_ in res["pages"] if p_["kind"] == "map"][-1]
        c = page["frame"] + 1
        data, regs_, lost, _ = taken_writes(res, EU)
        pics = line_pictures(data, regs_, EU, [c])
        tmp = Path(tempfile.mkdtemp(prefix="q2_"))
        png = msxcap.capture(path.with_suffix(".rom"), [c], tmp, "q2_f", machine=EU,
                             events=model45.tcl_events(events(EU)), timeout=3600)[c]
        bad = against(codes(png), *pics[c])
        shutil.copy(png, SHOTS / "mapy3_eu_map.png")
        shutil.rmtree(tmp)
        g = model_for("game", EU)
        ev = events(EU)
        for _ in range(page["loop"] + 1):
            g.step_loop(model45.keys_at(ev, g.ticks + 1 + model45.EVENT_AHEAD))
        own = {k: bytes(model45.picture_order(g.minis[k])) for k in range(16)}
        shows = {}
        for k in range(16):
            first = gen45.CURRENT if k == g.room else gen45.mini_name(k)
            r0 = gen45.map_cell(k)[1]
            rows = []
            for i in range(3):
                t = (r0 + i) // 8
                got = bytes(g.vram[0x800 * t + 8 * (first + 4 * i):0x800 * t + 8 * (first + 4 * i) + 32])
                # the room whose picture picture() wrote to these names of third t
                owner = [j for j in range(16) if g.been[j] and gen45.third_of(j) == t and
                         (j == g.room if first == gen45.CURRENT else gen45.mini_name(j) == first)]
                if owner:
                    assert own[owner[0]][32 * i:32 * i + 32] == got
                    rows.append(gen45.room_name(owner[0]))
                else:
                    assert not any(got)
                    rows.append("blank")
            shows[gen45.room_name(k)] = rows
        out["q2"] = {"frame": c, "mismatch": bad, "room": gen45.room_name(g.room), "shows": shows,
                     "straddle": [gen45.room_name(k) for k in range(16)
                                  if len({(gen45.map_cell(k)[1] + i) // 8 for i in range(3)}) > 1]}
        shutil.rmtree(d)
    finally:
        gen45.MAP_Y, gen45.MAP_DIGITS = keep
    # the places on an edge the explorer can stand on (the text's): all in doors
    places = sides = 0
    for k in range(gen45.ROOMS):
        g = gen45.grid(k)
        for x in range(0, gen45.X_LAST + 1, 2):
            for y in range(gen45.Y_FIRST, gen45.Y_LAST + 1, 2):
                if (x in (0, gen45.X_LAST) or y in (gen45.Y_FIRST, gen45.Y_LAST)) and \
                        not gen45.solid_at(g, x, y):
                    places += 1
        sides += bin(gen45.EXITS[k]).count("1")
    out["edges"] = {"places": places, "sides": sides}
    # 3: the two walks in seconds, from the frame of the loop that saw SPACE
    # to the last; the loops that walk and the loops that do not
    fl_ = json.loads((HERE / "meas45.json").read_text())["films"]
    q3 = {}
    for m in MACHINES:
        f = fl_["game"][TAG[m]]
        rows = f["rows"]
        start = next(r for r in rows if "flip0" in r["marks"])      # the loop that saw SPACE
        after = [r for r in rows if r["loop"] >= start["loop"]]
        still = [r for r in after if r["steps"] == 0]
        frames = rows[-1]["frame"] - start["frame"] + 1
        assert frames == len(after)
        q3[TAG[m]] = {"seconds": round(frames * FT[m] / CLOCK, 2), "frames": frames,
                      "steps": sum(r["steps"] for r in after), "stepping": len(after) - len(still),
                      "still": len(still), "still_s": round(len(still) * FT[m] / CLOCK, 2)}
    for m in MACHINES:                  # the lines play0 lets go, from the model, which the
        g = model_for("game", m)        # films hold loop for loop
        drops = []

        def play0(g=g, drops=drops):
            drops.append(g.due)
            g.due, g.was = 0, g.held
        g.play0 = play0
        ev = events(m)
        for _ in range(len(fl_["game"][TAG[m]]["rows"])):
            g.step_loop(model45.keys_at(ev, g.ticks + 1 + model45.EVENT_AHEAD))
        q3[TAG[m]]["restarts"] = len(drops)
        q3[TAG[m]]["left_over"] = sum(d % model45.STEPL for d in drops)
    out["q3"] = q3
    out["margins"] = {TAG[m]: min(p["least"] for p in fl_["game"][TAG[m]]["pages"]) for m in MACHINES}
    # 4: the map with the play's one set: the first look, photographed on the
    # 50 Hz machine
    path = build_variant("game", onethird=True)
    res = analyse("game", EU, path=path, onethird=True)
    page = next(p for p in res["pages"] if p["kind"] == "map")
    data, regs_, lost, _ = taken_writes(res, EU)
    pics = line_pictures(data, regs_, EU, [page["frame"] + 5])
    tmp = Path(tempfile.mkdtemp(prefix="q4_"))
    c = page["frame"] + 5
    png = msxcap.capture(path.with_suffix(".rom"), [c], tmp, "q4_f", machine=EU,
                         events=model45.tcl_events(events(EU)), timeout=3600)[c]
    bad = against(codes(png), *pics[c])
    shutil.copy(png, SHOTS / "onethird_eu_map.png")
    g = model_for("game", EU, onethird=True)
    ev = events(EU)
    while not (g.state == model45.MAP and g.whole == 0 and g.r3 == gen45.GAME_R3 and g.vnames[32:] == g.mapn):
        g.step_loop(model45.keys_at(ev, g.ticks + 1 + model45.EVENT_AHEAD))
    seen = [k for k in range(16) if g.been[k]]
    shows = {}
    for k in seen:
        first = gen45.CURRENT if k == g.room else gen45.mini_name(k)
        pic = bytes(g.vram[8 * first:8 * first + 96])          # table 0: the one the play's set is
        own = bytes(model45.picture_order(g.minis[k]))
        others = [j for j in seen if bytes(model45.picture_order(g.minis[j])) == pic]
        shows[gen45.room_name(k)] = ("its own" if pic == own else
                                     gen45.room_name(others[0]) + "'s" if others else
                                     "blank" if not any(pic) else "another")
    out["q4"] = {"frame": c, "mismatch": bad, "seen": [gen45.room_name(k) for k in seen],
                 "room": gen45.room_name(g.room), "shows": shows}
    shutil.rmtree(tmp)
    shutil.rmtree(path.parent)
    # 5: the picture in flip1, in the frame of the page: planned again on the
    # 60 Hz machine and walked
    p = model45.Player()
    keys, gp, recs = model45.plan(JP, player=p, game=model45.Keep(JP, pic_flip1=True))
    ev5 = model45.events_of(keys)
    path = build_variant("game", pic_flip1=True)
    res = analyse("game", JP, ev=ev5, path=path, frames=len(recs) + model45.EVENT_AHEAD + 1, pic_flip1=True)
    rows = res["rows"]
    flips = [r for r in rows if r["state"] == model45.FLIP]
    out["q5"] = {"loops": len(rows), "flip_halt": max(r["halt"] for r in flips),
                 "flip_halt_new": max(r["halt"] for r in flips if r["marks"].get("mini")),
                 "left": num(FT[JP] - max(r["halt"] for r in flips)), "lost": sum(r["lost"] or 0 for r in rows)}
    shutil.rmtree(path.parent)
    # 6: torn.asm's two flips into D3 on the 50 Hz machine: when each page
    # began, the names behind, and whether the room was new
    te_ = fl_["torn"]["eu"]
    d3 = [p_ for p_ in te_["pages"] if p_["kind"] == "room" and p_["room"] == 11]
    new_ = {e[0]: e[3] for e in te_["events"] if e[1] == "ROOM"}
    out["q6"] = {"flips": [{"loop": p_["loop"], "t": p_["t"], "behind": p_["behind"], "new": new_[p_["loop"]],
                            "flip0": te_["rows"][p_["loop"]]["marks"]["flip0"][0]} for p_ in d3],
                 "behind": [[p_["room"], p_["behind"]] for p_ in te_["pages"] if p_["kind"] == "room"],
                 "runs": [len(r) for r in gen45.RUN_BYTES]}
    return out


def _crossings(runs):
    c = 0
    for t, n in runs:
        if c // 32 != (c + n - 1) // 32:
            yield t, n
        c += n


def openmsx():
    if not versions.builds():
        return {"skipped": "OPENMSX_BUILDS not set"}
    return versions.every_build(["ch45"], OPENMSX_SECTIONS)


OPENMSX_SECTIONS = ["films", "photos", "prices", "machines", "answers"]


SECTIONS = {"films": films, "photos": photos, "prices": prices, "machines": machines,
            "answers": answers, "openmsx": openmsx}


def main(names=()):
    CAPS.mkdir(exist_ok=True)
    path_ = HERE / "meas45.json"
    m = json.loads(path_.read_text()) if names and path_.exists() else {}
    for name in names or SECTIONS:
        print(name, flush=True)
        m[name] = SECTIONS[name]()
        m = {k: m[k] for k in SECTIONS if k in m}
        path_.write_text(json.dumps(m, indent=1) + "\n")
    return m


if __name__ == "__main__":
    main(sys.argv[1:])
