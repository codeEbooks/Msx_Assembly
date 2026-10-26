#!/usr/bin/env python3
"""meas46.py -- LANTERN KEEP finished, measured.

    python3 gen46.py && ./build.sh && python3 model46.py && python3 meas46.py
                                  python3 meas46.py films prices   only these

  films     the three plays planned by model46.py, game (every lantern lit),
            over (three touches) and late (late.asm's walk), on each machine.
            The debugger stops where each loop wakes, after its sends and at
            its end, and in the interrupt routine; it reads the variables,
            the player's page, the copy of the names, the map's page and the
            rooms' pictures where the loop wakes, and the name table, the
            sprites' attributes and R#3 and R#4 after the sends; watchpoints
            log every byte to the VDP's two ports and to the PSG's, from
            INIT. Every loop is held against model46.py's game fed the same
            keys, the PSG's writes in its interrupt against the player's, and
            its T-states against walk.py run on the RAM the debugger read.
            The VDP's bytes are played through vdpslots.py (chapter 20): none
            lost, the VRAM at the end the debugger's and the model's, and the
            moment each name of each page reached the VRAM against the moment
            the VDP starts drawing its row
  photos    the figures' frames, and the first frame of every room, each
            against vdpscreen.py's picture of the VRAM line by line, as the
            bytes reached it (figures 46.1 to 46.4)
  prices    what each new routine costs, from walk.py
  machines  the cartridge on every machine of the book: the play the same
            loop for loop, and the title's photograph
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
import model46     # noqa: E402
gen46 = model46.gen46
gen45 = gen46.gen45
sys.path.remove(str(HERE))
sys.path.insert(0, str(HERE))      # other chapters came first: this folder's files win
for mod in ("vdpscreen", "walk", "vdpslots"):
    sys.modules.pop(mod, None)
import vdpscreen   # noqa: E402
import walk        # noqa: E402
import vdpslots    # noqa: E402

assert Path(vdpscreen.__file__).parent == HERE and Path(walk.__file__).parent == HERE
assert Path(vdpslots.__file__).parent == HERE and Path(model46.vdpscreen.__file__).parent == HERE

CAPS = HERE / "captures"
SHOTS = HERE / "shots"
EU, JP = gen46.EU, gen46.JP
MACHINES = gen46.MACHINES
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
PLAYS = {"game": "game", "over": "game", "late": "late"}     # each play's cartridge
VARS = (gen46.VARS_AT, 256)
ENGINE = (gen46.ENGINE_AT, 128)
NAMES_RAM = (gen45.NAMES_AT, 768)
MAPN = (gen45.MAPN_AT, 736)
MINIS = (gen45.MINIS_AT, 16 * 96)
PALETTE = [tuple(c) for c in json.loads((REPO / "ch01" / "meas01.json").read_text())["palette"]["rgb"]]
CODE = {rgb: n for n, rgb in enumerate(PALETTE) if n}
R15 = 0x8F                                  # register 15 as joy leaves it: port 1, pins 6-7 high
EVENT_AHEAD = model46.EVENT_AHEAD

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
PSG_WP = ('debug set_watchpoint write_io {0xA0 0xA1} {} '
          '{ L "psg [expr {$::wp_last_address & 255}] $::wp_last_value ' + POS + '" }\n')
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


def events(play, machine):
    return model46.read_events(model46.events_path(play, machine))


def run(path, machine, frames, tcl, ev, at_end=None):
    tev = model46.tcl_events(ev)
    if at_end:
        tev[frames - 1] = (tev[frames - 1] + "; " if frames - 1 in tev else "") + at_end
    lines = msxcap.run_tcl(path, frames, F0 + TOO_FAST + tcl, machine=machine,
                           tcl_setup=STATE, timeout=7200, events=tev)
    return [l.split() for l in lines]


def codes(png):
    im = Image.open(png).convert("RGB")
    px = im.load()
    return [[CODE.get(px[x, y]) for x in range(im.width)] for y in range(im.height)]


def model_for(name, machine, rom_=None):
    return model46.Keep(machine, late=(name == "late"), rom=rom_)


def loops_planned(play, machine):
    ev = events(play, machine)
    player = model46.PLAYS[play]()
    keys, g, recs = model46.plan(machine, player=player, game=model_for(PLAYS[play], machine))
    assert model46.events_of(keys, machine) == ev, (play, machine, "the events are not the plan's")
    return len(recs)


LOOPS = {}


def play_frames(play, machine):
    if (play, machine) not in LOOPS:
        LOOPS[(play, machine)] = loops_planned(play, machine)
    return LOOPS[(play, machine)] + EVENT_AHEAD[machine] + 1


# ---------------------------------------------------------------- what the RAM says
def ram_state(s, v, e):
    def at(label, k=1):
        a = s[label] - VARS[0]
        return v[a] if k == 1 else list(v[a:a + k])

    def w(label):
        a = s[label] - VARS[0]
        return v[a] | v[a + 1] << 8
    gd = at("gd", 8)
    la = s["lines"] - ENGINE[0]
    return {"stat": at("stat"), "ticks": w("ticks"), "state": at("state"), "was": at("was"),
            "room": at("room"), "fresh": at("fresh"), "queued": at("queued"), "keepy": at("keepy"),
            "whole": at("whole"), "wsrc": w("wsrc"), "wr3": at("wr3"), "wr4": at("wr4"),
            "copy": at("copy", 13), "due": w("due"), "lines": e[la] | e[la + 1] << 8,
            "been": at("been", 16), "held": at("held"), "lives": at("lives"), "nlit": at("nlit"),
            "time": at("time", 2), "tock": at("tock"), "left": at("left"), "dimmed": at("dimmed"),
            "back": at("back", 2), "lit": at("lit", 32), "gd": [gd[:4], gd[4:]],
            "score": at("score", 3), "hi": at("hi", 3)}


def model_ram(g):
    r = g.ram()
    r["held"] = g.held
    return r


def engine_same(page, g):
    """the player's page the debugger read, against the model's: the
    differences"""
    out = []
    for off, want in g.engine():
        got = list(page[off:off + len(want)])
        if got != want:
            out.append((off, [(i, a, b) for i, (a, b) in enumerate(zip(got, want)) if a != b][:6]))
    return out


# ---------------------------------------------------------------- walk
def walker(path, rate, keys_=frozenset()):
    wk = walk.Walk(path)
    psg = {"reg": 0}
    keys = {"held": set(keys_)}

    def read_port(port, t):
        if port == 0xA9:
            sel = [v for _, p, v in wk.ports if p == 0xAA]
            row = (sel[-1] if sel else 0) & 15
            v = 0xFF
            for k in keys["held"]:
                if row == 8:
                    v &= ~model46.model45.ROW8.get(k, 0) & 0xFF
                elif row == 4:
                    v &= ~model46.model45.ROW4.get(k, 0) & 0xFF
            return v
        if port == 0xA2:
            last = [v for _, p, v in wk.ports if p == 0xA0]
            psg["reg"] = last[-1] if last else 0
            return {14: model46.model45.JOY_IDLE, 15: R15}.get(psg["reg"], 0)
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
KINDS = ("isr", "isrend", "woke", "sent", "ran", "input", "show", "flip0", "map0", "mini",
         "hit0", "over0", "win0", "title0", "box", "lamps", "greset")


def film(name, machine, frames, ev, path=None, light=False):
    """the debugger's log of a play"""
    path = path or HERE / name
    s = dbg.sym(path.with_suffix(".sym"))
    if light:
        tcl = "".join(f'debug set_bp {s[k]} {{}} {{ L "{k} {POS}" }}\n'
                      for k in ("isr", "isrend", "woke", "sent", "ran", "input"))
        tcl += f'debug set_bp {s["woke"]} {{}} {{ M v {VARS[0]} {VARS[1]}; M e {ENGINE[0]} {ENGINE[1]} }}\n'
    else:
        tcl = (f'debug set_bp {s["isr"]} {{}} {{ L "isr {POS}"; M v {VARS[0]} {VARS[1]}; '
               f'M e {ENGINE[0]} {ENGINE[1]} }}\n'
               f'debug set_bp {s["isrend"]} {{}} {{ L "isrend {POS}" }}\n'
               f'debug set_bp {s["woke"]} {{}} {{ L "woke {POS}"; M v {VARS[0]} {VARS[1]}; '
               f'M e {ENGINE[0]} {ENGINE[1]}; '
               f'M nm {NAMES_RAM[0]} {NAMES_RAM[1]}; M mp {MAPN[0]} {MAPN[1]}; '
               f'M mi {MINIS[0]} {MINIS[1]} }}\n'
               f'debug set_bp {s["sent"]} {{}} {{ L "sent {POS}"; VR sat {model46.SAT} 13; '
               f'VR names {0x1800} 768; {REGS_READ} }}\n'
               f'debug set_bp {s["ran"]} {{}} {{ L "ran {POS}" }}\n' +
               "".join(f'debug set_bp {s[k]} {{}} {{ L "{k} {POS}" }}\n'
                       for k in KINDS[5:]) + VDP_WP + PSG_WP)
    w = run(path.with_suffix(".rom"), machine, frames, tcl, ev,
            at_end=None if light else 'VR end 0 16384')
    f0 = int(next(x for x in w if x[0] == "f0")[1])
    assert not [x for x in w if x[0] == "fast"], (name, machine, "an access too soon")
    out, pend, writes = [], {}, []
    for x in w:
        k = x[0]
        if k in KINDS:
            f, c = t_abs(x[1], x[2])
            e = {"kind": k, "frame": f - f0, "t": f * FT[machine] + c}
            out.append(e)
            pend = e
        elif k == "w":
            writes.append((int(x[3]) - f0, int(x[4]), int(x[1]), int(x[2])))
        elif k == "psg":
            f, c = t_abs(x[3], x[4])
            out.append({"kind": "psg", "port": int(x[1]), "value": int(x[2]), "frame": f - f0,
                        "t": f * FT[machine] + c})
        elif k == "regs":
            pend["regs"] = [int(v) for v in x[1:]]
        elif len(x) == 3 and x[1] in ("mem", "vram"):
            pend[x[0]] = bytes.fromhex(x[2])
    end = next((x for x in w if x[0] == "end"), None)
    return f0, out, s, writes, (bytes.fromhex(end[2]) if end else None)


def signal_of(frame, machine):
    return frame * FT[machine] + FLAG_LINE[machine] * L + SIGNAL


MARKS = ("show", "flip0", "map0", "mini", "hit0", "over0", "win0", "title0", "box", "lamps", "greset")


def loops_of(ev):
    """the films cut into loops: the interrupt that woke each, where it woke,
    its sends' end, its end, the marks inside, and the PSG's writes in its
    interrupt and in its logic"""
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
                      "psg_isr": [(e["port"], e["value"]) for e in ev[j:a] if e["kind"] == "psg"],
                      "psg_logic": [(e["port"], e["value"]) for e in seg
                                    if e["kind"] == "psg" and e["t"] < ran["t"]],
                      "marks": {k: [e for e in seg if e["kind"] == k and e["t"] < ran["t"]]
                                for k in MARKS}})
    return loops


def tochip(shadow):
    out = []
    for r, v in enumerate(shadow):
        out += [(0xA0, r), (0xA1, v)]
    return out


JOY_WRITES = [(0xA0, 15), (0xA1, R15), (0xA0, 14)]


def analyse(play, machine, ev=None, frames=None, path=None, name=None, game=None):
    """a play on MACHINE against the model fed the same keys"""
    name = name or PLAYS[play]
    ev = events(play, machine) if ev is None else ev
    nloops = frames or play_frames(play, machine)
    f0, evs, s, writes, end_vram = film(name, machine, nloops, ev, path=path)
    loops = loops_of(evs)
    g = game or model_for(name, machine, rom_=str(path) if path else None)
    rate = 0x80 if machine == EU else 0
    wk = walker(path or HERE / name, rate)
    rows, pages = [], []
    tail = wk.run("ran", "frame")
    for k, lp in enumerate(loops):
        wake_frame = lp["wake"]["frame"]
        sig = signal_of(wake_frame + f0, machine)
        assert sig <= lp["wake"]["t"] < sig + 40, (play, machine, k)
        g.loop += 1
        ticked = len(g.psg)
        keys = model46.keys_at(ev, g.ticks + 1 + EVENT_AHEAD[machine])
        g.isr(keys)
        tick = len(g.psg) > ticked
        want_isr = JOY_WRITES + (tochip(g.psg[-1][1]) if tick else [])
        assert lp["psg_isr"] == want_isr, (play, machine, k, "the PSG in the interrupt",
                                           lp["psg_isr"][:8], want_isr[:8])
        got = ram_state(s, lp["woke"]["v"], lp["woke"]["e"])
        want = model_ram(g)
        assert got == want, (play, machine, k, {x: (got[x], want[x]) for x in got if got[x] != want[x]})
        diff = engine_same(lp["woke"]["e"], g)
        assert not diff, (play, machine, k, "the player's page", diff)
        assert list(lp["woke"]["nm"]) == g.names, (play, machine, k, "the copy of the names")
        assert list(lp["woke"]["mp"]) == g.mapn or g.mapn == [0] * 736 and not any(lp["woke"]["mp"]), \
            (play, machine, k, "the map's page")
        assert list(lp["woke"]["mi"]) == sum(g.minis, []), (play, machine, k, "the pictures")
        assert got["ticks"] == wake_frame - EVENT_AHEAD[machine], (play, machine, k, "ticks", got["ticks"], wake_frame)
        state0, room0 = g.state, g.room
        g.sends()
        assert list(lp["sent"]["sat"]) == g.copy, (play, machine, k, "the attributes")
        assert list(lp["sent"]["names"]) == g.vnames, (play, machine, k, "the names",
                                                       [(i, a, b) for i, (a, b) in
                                                        enumerate(zip(lp["sent"]["names"], g.vnames)) if a != b][:8])
        assert lp["sent"]["regs"][:2] == [g.r3, g.r4], (play, machine, k, "R#3, R#4")
        wk.keys["held"] = set(keys)
        blocks = [(VARS[0], lp["woke"]["v"]), (ENGINE[0], lp["woke"]["e"]), (NAMES_RAM[0], lp["woke"]["nm"]),
                  (MAPN[0], lp["woke"]["mp"]), (MINIS[0], lp["woke"]["mi"])]
        t_walk = walk_from(wk, blocks, "woke", "ran")
        took = lp["ran"]["t"] - lp["woke"]["t"]
        assert not lp["inside"], (play, machine, k, "an interrupt inside")
        assert all(e["frame"] == wake_frame for e in lp["input"]), (play, machine, k, "keys late")
        assert took == t_walk, (play, machine, k, took, t_walk)
        t_sends = walk_from(wk, blocks, "woke", "sent")
        assert t_sends == lp["sent"]["t"] - lp["woke"]["t"], (play, machine, k, "sends")
        ti = walk_from(wk, [(VARS[0], lp["wake"]["v"]), (ENGINE[0], lp["wake"]["e"])], "isr", "isrend")
        assert ti == lp["wake_end"]["t"] - lp["wake"]["t"], (play, machine, k, "isr")
        nsteps = len(g.steps_taken)
        screen_sends = g.screen
        g.run()
        steps = g.steps_taken[-1][1] if len(g.steps_taken) > nsteps else 0
        assert lp["psg_logic"] == [], (play, machine, k, "the PSG in the logic", lp["psg_logic"])
        for e in lp["marks"]["show"]:
            kind = ("room" if lp["marks"]["flip0"] or state0 == model46.FLIP else
                    "map" if state0 == model46.MAP and g.wsrc == "mapn" else "back")
            pages.append({"loop": k, "frame": wake_frame, "t": num(e["t"] - sig),
                          "room": g.room, "kind": kind})
        nxt = loops[k + 1]["wake"]["frame"] if k + 1 < len(loops) else None
        rows.append({"loop": k, "frame": wake_frame, "ticks": got["ticks"], "state": state0,
                     "room": room0, "wake": num(lp["wake"]["t"] - sig),
                     "isr": num(lp["wake_end"]["t"] - lp["wake"]["t"] + BACK), "tick": tick,
                     "sends": num(lp["sent"]["t"] - lp["woke"]["t"]),
                     "logic": num(lp["ran"]["t"] - lp["sent"]["t"]),
                     "woke": num(lp["woke"]["t"] - sig), "sent": num(lp["sent"]["t"] - sig),
                     "halt": num(lp["ran"]["t"] + tail - sig),
                     "lost": None if nxt is None else nxt - wake_frame - 1,
                     "stat": got["stat"], "held": got["held"], "page": screen_sends, "steps": steps,
                     "marks": {kk: [num(e["t"] - sig) for e in v] for kk, v in lp["marks"].items() if v}})
    return {"f0": f0, "rows": rows, "tail": tail, "ev": evs, "game": g, "writes": writes,
            "end_vram": end_vram, "pages": pages}


# ---------------------------------------------------------------- the bytes to the VDP
def taken_writes(res, machine):
    """the film's bytes to the VDP played through vdpslots: (data, regs,
    lost, vram): data [(cycle taken, address, value)], regs [(cycle, reg,
    value)], the cycles counted from the start of film frame 0"""
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
    return frame * vdpslots.LINES[machine] * LINE + FLAG_LINE[machine] * LINE + vdpslots.BORDER_IN


def page_margins(res, machine, data):
    """for each page sent, the least margin of its names against the rows
    the beam draws in the picture after the signal that woke the loop, its
    row, the names behind, and the last name's moment after the signal"""
    out = []
    for p in res["pages"]:
        fr = p["frame"]
        lo, hi = sig_cycle(fr, machine), sig_cycle(fr + 1, machine)
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
           "isr_title": [min(r["isr"] for r in rows if r["state"] == 0),
                         max(r["isr"] for r in rows if r["state"] == 0)],
           "isr_play": [min(r["isr"] for r in rows if r["state"] != 0),
                        max(r["isr"] for r in rows if r["state"] != 0)],
           "sent_max": max(r["sent"] for r in rows), "halt_max": max(r["halt"] for r in rows),
           "states": {},
           "steps": {str(b): sum(1 for r in rows if r["steps"] == b) for b in sorted({r["steps"] for r in rows})}}
    for i, st in enumerate(gen46.STATES):
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
FILMS = [("game", JP), ("game", EU), ("over", JP), ("over", EU), ("late", JP), ("late", EU)]


def films(which=FILMS):
    out = {}
    for play, m in which:
        res = analyse(play, m)
        CACHE[(play, m)] = res
        rows, g = res["rows"], res["game"]
        data, regs_, lost, vram = taken_writes(res, m)
        assert not lost, (play, m, "bytes lost", len(lost))
        ev_ = res["end_vram"]
        spans = [(0, 0x1B00), (0x2000, 0x3800), (0x3800, 0x3840)]     # the SAT: at every loop
        assert all(ev_[a:b] == vram[a:b] for a, b in spans), (play, m, "the VRAM played")
        gv = g.vram
        assert all(ev_[a:b] == bytes(gv[a:b]) for a, b in spans), (play, m, "the VRAM modelled")
        margins = page_margins(res, m, data)
        out.setdefault(play, {})[TAG[m]] = {
            "rows": rows, "f0": res["f0"], "tail": res["tail"],
            "events": [jsonable(e) for e in g.events], "fx": [list(x) for x in g.fx_asked],
            "psg_ticks": len(g.psg), "summary": summary(rows, m), "pages": margins,
            "planned": LOOPS[(play, m)],
            "writes": len(res["writes"])}
        print(play, TAG[m], out[play][TAG[m]]["summary"], flush=True)
    return out


# ---------------------------------------------------------------- the photos
class Rows(dict):
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
    """for each film frame of FRAMES, the paper line by line, as the VRAM and
    the registers stand where the VDP starts drawing each line, and for a
    line during which a byte reached the VRAM, the line after it too"""
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


def full_picture(paper, border=gen46.gen45.BORDER):
    out = []
    for y in range(meas.CAPTURE_H):
        row = [None] * meas.CAPTURE_W
        for x in range(meas.DRAWN[0], meas.DRAWN[1] + 1):
            px, py = x - meas.PAPER_X0, y - meas.PAPER_Y0
            row[x] = paper[py][px] if 0 <= px < 256 and 0 <= py < 192 else border
        out.append(row)
    return out


def full_picture_line(line):
    row = [None] * meas.CAPTURE_W
    for x in range(meas.DRAWN[0], meas.DRAWN[1] + 1):
        px = x - meas.PAPER_X0
        row[x] = line[px] if 0 <= px < 256 else gen46.gen45.BORDER
    return row


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


def photo_set(play, machine, res, frames, keep=()):
    """FRAMES of a play's film photographed and held against the line by line
    model; the one offset that fits"""
    name = PLAYS[play]
    data, regs_, lost, _ = taken_writes(res, machine)
    want = sorted(frames)
    models = line_pictures(data, regs_, machine, want)
    shots = sorted({c + d for c in want for d in (-1, 0, 1)})
    tmp = Path(tempfile.mkdtemp(prefix="ph46_"))
    pngs = msxcap.capture(rom(name), shots, tmp, f"{play}_{TAG[machine]}_f", machine=machine,
                          events=model46.tcl_events(events(play, machine)), timeout=7200)
    ph = {c: codes(pngs[c]) for c in shots}
    fits = [d for d in (-1, 0, 1) if all(against(ph[c + d], *models[c]) == 0 for c in want)]
    assert fits, (play, machine, [(c, d, against(ph[c + d], *models[c])) for c in want for d in (-1, 0, 1)])
    d = 0 if 0 in fits else fits[0]         # several: frames that do not change, the same either way
    bad = {c: against(ph[c + d], *models[c]) for c in want}
    assert not any(bad.values()), (play, machine, {c: b for c, b in bad.items() if b})
    out = {}
    for c in want:
        dest = (CAPS if c in keep else SHOTS) / pngs[c + d].name.replace(f"_f{c + d:04d}", f"_f{c:04d}")
        dest.parent.mkdir(exist_ok=True)
        shutil.copy(pngs[c + d], dest)
        out[c] = dest.name
    shutil.rmtree(tmp)
    return fits, out, {c: sorted(models[c][1]) for c in want}


def frame_of_loop(res, loop):
    """the film frame drawn from what loop LOOP's run left: the frame after the
    next loop's sends"""
    return res["rows"][loop + 1]["frame"] + 1


def photo_plan(play, machine, res):
    """the frames the figures use, and every room's first picture"""
    g = res["game"]
    ev = g.events
    plan = {}
    rooms, seen = {}, set()
    for p in res["pages"]:
        if p["kind"] == "room" and p["room"] not in seen:
            seen.add(p["room"])
            rooms[p["room"]] = p["frame"] + 1
    plan["rooms"] = [rooms[k] for k in sorted(rooms)]
    if play == "game":
        first = [p for p in res["pages"] if p["kind"] == "room"][0]
        plan["first"] = first["frame"] + 1
        plan["a1_loop"] = between(machine, FIG_ROOM)
        plan["a1"] = frame_of_loop(res, plan["a1_loop"])
        maps = [p for p in res["pages"] if p["kind"] == "map"]
        plan["map"] = maps[0]["frame"] + 1 + MAP_SETTLE
        ended = next(e[0] for e in ev if e[1] == "ENDED")
        plan["win"] = frame_of_loop(res, ended)
        plan["title"] = TITLE_FRAME
        again = next(e[0] for e in ev if e[1] == "TITLE" and e[0] > ended)
        plan["again"] = frame_of_loop(res, again) + MAP_SETTLE
    if play == "over":
        touch = [e for e in ev if e[1] == "TOUCH"]
        plan["touch"] = frame_of_loop(res, touch[0][0])
        plan["over"] = frame_of_loop(res, next(e[0] for e in ev if e[1] == "ENDED"))
    if play == "late":
        flips = [p for p in res["pages"] if p["kind"] == "room"]
        plan["first"] = flips[0]["frame"] + 1
        touch = next(e for e in ev if e[1] == "TOUCH")
        last = [p for p in flips if p["loop"] < touch[0]][-1]
        plan["wrong"] = last["frame"] + 1
    return plan


FIG_ROOM = 0                # figure 46.2: A1, both lanterns lit, the explorer between its guards


def between(machine, k):
    """the first loop of the planned game after which the explorer, in room K
    with both its lanterns lit, has its lines between its two guards'"""
    g = model_for("game", machine)
    ev = events("game", machine)
    while True:
        g.step_loop(model46.keys_at(ev, g.ticks + 1 + EVENT_AHEAD[machine]))
        c = g.copy
        if g.state == model46.PLAY and g.room == k and g.lit[2 * k] and g.lit[2 * k + 1] and \
                c[4] + 16 < c[0] and c[0] + 16 < c[8]:
            return g.loop
MAP_SETTLE = 4              # the map's frame: a few frames after its page
TITLE_FRAME = 60


def photos(cache=CACHE):
    """the figures' frames and every room's first picture, held against the
    model, on both machines"""
    out = {}
    for play, m in FILMS:
        res = cache.get((play, m)) or analyse(play, m)
        cache[(play, m)] = res
        plan = photo_plan(play, m, res)
        frames = set(plan["rooms"])
        figs = {v for k, v in plan.items() if isinstance(v, int) and not k.endswith("_loop")}
        frames |= figs
        keep = figs if m == JP else set()
        d, shots, mixed = photo_set(play, m, res, frames, keep=keep)
        out.setdefault(play, {})[TAG[m]] = {"offsets": d, "frames": {str(k): v for k, v in shots.items()},
                                           "plan": plan,
                                           "mixed": {str(c): len(v) for c, v in mixed.items() if v}}
        print("photos", play, TAG[m], d, len(shots), plan, flush=True)
    return out


# ---------------------------------------------------------------- the tune
def tune():
    """the title's tune as the player plays it from the cartridge's bytes,
    twice through: each channel's notes, read back from the registers it
    sends, a period to a note, at each row's first tick, against the tune
    in gen46.py"""
    mu = model46.Music(str(HERE / "game"))
    per = {}
    for n in range(1, 85):
        per[mu.word(mu.sym["notes"] + 2 * n)] = n
    sent = []
    for _ in range(2 * gen46.TUNE_TICKS + 1):
        sent.append(list(mu.shadow))
        mu.play()
    rows = []
    for t in range(1, 2 * gen46.TUNE_TICKS + 1, gen46.SPEED):     # tick t sends row (t - 1) / SPEED's
        s_ = sent[t]
        rows.append([per.get(s_[2 * ch] | s_[2 * ch + 1] << 8) if s_[8 + ch] else None for ch in range(3)])
    want = []                           # each row: a channel's note where one begins, None in a
    pats = gen46.patterns()             # rest, "held" where a note goes on (its pitch may move)
    for a, b, c in gen46.SONG:
        evs = {ch: [] for ch in range(3)}
        for ch, name in enumerate((a, b, c)):
            for _, n, r in pats[name]:
                evs[ch] += [n or None] + [(None if not n else "held")] * (r - 1)
        want += [[evs[ch][i] for ch in range(3)] for i in range(gen46.BAR_ROWS)]
    want = want + want
    rows = [[w if w == "held" and g is not None else g for g, w in zip(r, ws)] for r, ws in zip(rows, want)]
    # the melody as it sounds: a note where channel A's changes, and its rows
    mel = []
    for r in rows[:len(rows) // 2]:
        if r[0] not in (None, "held"):
            mel.append([r[0], 1, False])
        elif r[0] == "held":
            mel[-1][1] += 1
    return {"rows": len(rows), "same": rows == want, "differ": [i for i, (a, b) in enumerate(zip(rows, want))
                                                                if a != b][:8],
            "ticks": gen46.TUNE_TICKS,
            "seconds": round(gen46.TUNE_TICKS * 313 * L / CLOCK, 3),
            "melody": [music_name(n) for n, _, _ in mel], "rows_of": [k for _, k, _ in mel]}


def music_name(n):
    return gen46.music37.name_of(n)


# ---------------------------------------------------------------- prices
def fresh(name="game", machine=JP):
    wk = walker(HERE / name, 0x80 if machine == EU else 0)
    wk.init_t = wk.run("init", "main")
    return wk


def poke(wk, label, vals, off=0):
    a = wk.sym[label] + off
    for i, v in enumerate(vals):
        wk.mem[a + i] = v & 255


def peek(wk, label, n=1, off=0):
    a = wk.sym[label] + off
    return list(wk.mem[a:a + n])


def in_room(k, name="game"):
    """a walker in room K as play1 finds it: the game set up, the room
    flipped, its page sent, the play's state"""
    wk = fresh(name)
    wk.call("setup")
    poke(wk, "room", [k])
    poke(wk, "been", [1] * 16)
    wk.call("flip0")
    poke(wk, "queued", [0])
    poke(wk, "whole", [0])
    poke(wk, "state", [model46.PLAY])
    poke(wk, "fresh", [0])
    return wk


def lantern_place(k, j):
    """a place in room K from which lamp lights its lantern J"""
    c, r = gen46.LANTERNS[k][j]
    g = gen46.grid(k)
    for e in gen46.entries(k):
        for x, y in sorted(gen46.reach(g, e)):
            if gen46.touch(x, y, c, r):
                return x, y
    raise AssertionError((k, j))


def prices():
    out = {}
    wk = fresh()
    out["init"] = wk.init_t
    # the guards: greset in a room of two; patrol, a step and a turn
    wk = in_room(0)
    out["greset"] = wk.call("greset")
    gd = wk.sym["gd"]
    out["patrol_step"] = wk.call("patrol", h=gd >> 8, l=gd & 255)
    poke(wk, "copy", [200], off=5)                  # guard 0 at its most: a turn
    poke(wk, "gd", [1], off=3)
    out["patrol_turn"] = wk.call("patrol", h=gd >> 8, l=gd & 255)
    assert peek(wk, "copy", 1, 5) == [199] and peek(wk, "gd", 1, 3) == [255]
    wk = in_room(0)
    out["guards"] = wk.call("guards")
    # the clock: a step, and a unit
    wk = in_room(gen46.START)
    poke(wk, "tock", [5])
    out["clock_step"] = wk.call("clock")
    poke(wk, "tock", [1])
    out["clock_unit"] = wk.call("clock")
    assert peek(wk, "time", 2) == [0x09, 0x98] and peek(wk, "tock", 1) == [gen46.TICKS]
    # the lanterns: none in reach; the first lit; the second, with the map's room
    wk = in_room(gen46.START)
    out["lamps_none"] = wk.call("lamps")
    x, y = lantern_place(gen46.START, 0)
    poke(wk, "copy", [y, x])
    out["lamps_one"] = wk.call("lamps")
    assert peek(wk, "lit", 2, 2 * gen46.START) == [1, 0] and peek(wk, "nlit") == [1]
    x, y = lantern_place(gen46.START, 1)
    poke(wk, "copy", [y, x])
    poke(wk, "queued", [0])
    out["lamps_two"] = wk.call("lamps")
    assert peek(wk, "lit", 2, 2 * gen46.START) == [1, 1]
    wk = in_room(gen46.START)                   # neither in reach: both lit already; both
    poke(wk, "lit", [1, 1], off=2 * gen46.START)    # reached along X and missed along Y, in D2
    out["lamps_lit"] = wk.call("lamps")
    wk = in_room(7)
    poke(wk, "copy", [87, 8])
    assert [((8 + 16 - 8 * c) & 255 < 25, (87 + 17 - 8 * r) & 255 < 25) for c, r in gen46.LANTERNS[7]] == \
        [(True, False), (True, False)] and not gen46.solid_at(gen46.grid(7), 8, 87)
    out["lamps_missed"] = wk.call("lamps")
    assert peek(wk, "lit", 2, 14) == [0, 0]
    wk = in_room(gen46.START)
    out["lights_none"] = wk.call("lights")
    poke(wk, "lit", [1, 1], off=2 * gen46.START)
    out["lights_two"] = wk.call("lights")
    out["glow"] = wk.call("glow", a=gen46.START)
    poke(wk, "dimmed", [0])
    out["dim"] = wk.call("dim")
    # a touch, and the ends
    wk = in_room(gen46.START)
    out["hit0"] = wk.call("hit0")
    wk = in_room(gen46.START)
    out["over0"] = wk.call("over0")
    wk = in_room(gen46.START)
    out["win0"] = wk.call("win0")
    wk = in_room(gen46.START)
    out["box"] = wk.call("box", h=wk.sym["obox"] >> 8, l=wk.sym["obox"] & 255)
    # the player: hush with no sound and with one; retune
    wk = fresh()
    out["hush_silent"] = wk.call("hush")
    wk.call("fx", a=gen46.SOUND["S_TOUCH"])
    out["hush_sound"] = wk.call("hush")
    out["retune"] = fresh().call("retune")
    out["title0"] = fresh().call("title0")
    out["setup"] = fresh().call("setup")
    # flip0 in each room, the room seen for the first time
    out["flip0"] = []
    for k in range(gen46.ROOMS):
        wk = fresh()
        wk.call("setup")
        poke(wk, "room", [k])
        out["flip0"].append(wk.call("flip0"))
    # play1: a step in the gate hall with no keys held, nothing to light
    wk = in_room(gen46.START)
    poke(wk, "held", [0xFF])
    poke(wk, "was", [0xFF])
    poke(wk, "stat", [0x80])
    poke(wk, "due", [262 & 255, 262 >> 8])
    out["play1_step"] = wk.call("play1")
    return out


# ---------------------------------------------------------------- every machine
OTHERS = ["MSXBOOK_EU32", "MSXBOOK_EU64", "MSXBOOK_EU16X", "MSXBOOK_EU16E", "MSXBOOK_EU16AY",
          "MSXBOOK_EU16P", "MSXBOOK_EU16G"]


def light_loops(name, machine, play="game", real=EU):
    """the play planned for REAL's rate on MACHINE: at each wake the
    variables, the player's page and the copy of the names; at the end of
    INIT the slots"""
    s = sym(name)
    tcl = "".join(f'debug set_bp {s[k]} {{}} {{ L "{k} {POS}" }}\n'
                  for k in ("isr", "isrend", "woke", "sent", "ran", "input"))
    tcl += (f'debug set_bp {s["woke"]} {{}} {{ M v {VARS[0]} {VARS[1]}; M e {ENGINE[0]} {ENGINE[1]}; '
            f'M nm {NAMES_RAM[0]} {NAMES_RAM[1]} }}\n')
    tcl += (f'set ::m [debug set_bp {s["main"]} {{}} {{ L "slots [string map {{"\n" "|"}} [slotselect]]"; '
            f'debug remove_bp $::m }}]\n')
    w = run(rom(name), machine, play_frames(play, real), tcl, events(play, real))
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
        out.append({"frame": lp["wake"]["frame"], "v": lp["woke"]["v"], "e": lp["woke"]["e"],
                    "nm": lp["woke"]["nm"]})
    return out, slots, s


def title_paper(machine=EU):
    """the title as the model leaves it before any key: the names, the
    explorer and the guard where they start"""
    g = model_for("game", machine)
    v = g.vram
    v[model46.SAT:model46.SAT + 13] = bytes(g.copy)
    return vdpscreen.draw(v, g.regs())


def title_photo(machine, frame=TITLE_FRAME):
    """the title's frame on MACHINE, and the frames either side, against the
    model after each loop of the 50 Hz machine's play round it: the pixels
    that differ at the best, and how many loops the frame is after the loop
    whose copy it shows"""
    tmp = Path(tempfile.mkdtemp(prefix="mc46_"))
    pngs = msxcap.capture(rom("game"), [frame - 1, frame, frame + 1], tmp, f"title_{machine}_f",
                          machine=machine, timeout=600)
    ph = {d: codes(pngs[frame + d]) for d in (-1, 0, 1)}
    shutil.rmtree(tmp)
    g = model_for("game", EU)
    ev = events("game", EU)
    best = None
    while g.loop < frame:
        g.step_loop(model46.keys_at(ev, g.ticks + 1 + EVENT_AHEAD[EU]))
        if g.loop < frame - 12:
            continue
        v = g.vram
        v[model46.SAT:model46.SAT + 13] = bytes(g.copy)
        model = full_picture(vdpscreen.draw(v, g.regs()))
        for d in (-1, 0, 1):
            bad = sum(1 for y in range(meas.CAPTURE_H) for x in range(meas.DRAWN[0], meas.DRAWN[1] + 1)
                      if model[y][x] != ph[d][y][x])
            if best is None or bad < best[0]:
                best = (bad, frame + d - g.loop)
    return best[1], best[0]


def machines():
    """the cartridge on every machine: the game planned for the 50 Hz
    machine, loop for loop against the model, and the title's photograph"""
    out = {}
    for m in OTHERS:
        rows, slots, s = light_loops("game", m)
        g = model_for("game", EU)
        bad = []
        ev = events("game", EU)
        for k, r in enumerate(rows):
            g.loop += 1
            g.isr(model46.keys_at(ev, g.ticks + 1 + EVENT_AHEAD[EU]))
            if ram_state(s, r["v"], r["e"]) != model_ram(g) or list(r["nm"]) != g.names or \
                    engine_same(r["e"], g):
                bad.append(k)
            g.sends()
            g.run()
        d, mism = title_photo(m)
        out[m] = {"loops": len(rows), "wrong": bad[:10], "slots": slots, "title_offset": d,
                  "title_mismatch": mism, "ended": [list(e) for e in g.events if e[1] == "ENDED"]}
        print("machine", m, out[m], flush=True)
    # the 8 KB machine: no RAM at $C000
    tmp = Path(tempfile.mkdtemp(prefix="mc46_"))
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


# ---------------------------------------------------------------- the workshop
def build_variant(name="game", **kw):
    d = Path(tempfile.mkdtemp(prefix="v46_"))
    for f in ("msx.inc", "bios.inc", "music.inc"):
        shutil.copy(HERE / f, d / f)
    stem = name + "_" + "_".join(f"{k}" for k in sorted(kw))
    (d / f"{stem}.asm").write_text(gen46.program(name, **kw).replace(f'OUTPUT "{name}.rom"',
                                                                    f'OUTPUT "{stem}.rom"'))
    subprocess.run(["sjasmplus", "--nologo", "--msg=err", "--syntax=bFw", f"--sym={stem}.sym",
                    f"--lst={stem}.lst", f"{stem}.asm"], cwd=d, check=True)
    return d / stem


def meeting_guards():
    """the sixth question's rounds: A1's second guard eight lines below the
    first, its lines meeting the first's"""
    gs = [list(x) for x in gen46.GUARDS]
    axis, y, lo, hi, start, step = gs[0][1]
    gs[0][1] = (axis, gs[0][0][1] + 8, lo, hi, start, step)
    return gs


def answers():
    out = {}
    fl = json.loads((HERE / "meas46.json").read_text())["films"]
    # 1: lamp with CP 24: the lanterns no place can light, and the planned game
    # replayed on the model with it
    q1 = {"never": [], "sides": {}}
    for k in range(gen46.ROOMS):
        g = gen46.grid(k)
        places = set()
        for e in gen46.entries(k):
            if e not in places:
                places |= gen46.reach(g, e)
        for j, (c, r) in enumerate(gen46.LANTERNS[k]):
            side = "left" if c == 0 else "right" if c == 31 else "top" if r == 1 else "bottom"
            ok = any(((x + 16 - 8 * c) & 255) < 24 and ((y + 17 - 8 * r) & 255) < 24 for x, y in places)
            q1["sides"].setdefault(side, [0, 0])
            q1["sides"][side][0] += 1
            q1["sides"][side][1] += ok
            if not ok:
                q1["never"].append([gen46.room_name(k), c, r])
    ev = events("game", JP)
    g, _ = model46.replay(ev, LOOPS.get(("game", JP)) or loops_planned("game", JP), JP, cp=24)
    q1["lit_replayed"] = bcd_of(g.nlit)
    out["q1"] = q1
    # 2: the planned game's time and its steps of play
    q2 = {}
    for m in MACHINES:
        rows = fl["game"][TAG[m]]["rows"]
        evs = fl["game"][TAG[m]]["events"]
        play_steps = sum(r["steps"] for r in rows if r["state"] == model46.PLAY)
        start = next(r for r in rows if "flip0" in r["marks"])
        win = next(e for e in evs if e[1] == "ENDED")
        lit_frame = rows[win[0]]["frame"]
        gq = model_for("game", m)              # the steps the clock counted, on the model,
        clocked = []                            # which the films hold loop for loop
        clock0 = gq.clock

        def clock(clock0=clock0, clocked=clocked):
            clocked.append(1)
            return clock0()
        gq.clock = clock
        evq = events("game", m)
        for _ in range(win[0] + 1):
            gq.step_loop(model46.keys_at(evq, gq.ticks + 1 + EVENT_AHEAD[m]))
        outs = [e for e in gq.events if e[1] == "OUT"]
        q2[TAG[m]] = {"play_steps": play_steps, "clocked": len(clocked), "outs": len(outs),
                      "out_loops_two": sum(1 for e in outs if rows[e[0]]["steps"] == 2),
                      "time_left": win[6],
                      "play_loops": sum(1 for r in rows if r["state"] == model46.PLAY),
                      "seconds": round((lit_frame - start["frame"]) * FT[m] / CLOCK, 2),
                      "units": 999 - win[6]}
    out["q2"] = q2
    # 3: over: the loops from the first of play to GAME OVER, and its steps
    q3 = {}
    for m in MACHINES:
        rows = fl["over"][TAG[m]]["rows"]
        evs = fl["over"][TAG[m]]["events"]
        first = next(r for r in rows if r["state"] == model46.PLAY)
        over = next(e for e in evs if e[1] == "ENDED")
        span = [r for r in rows if first["loop"] <= r["loop"] <= over[0]]
        q3[TAG[m]] = {"loops": over[0] - first["loop"], "time": over[6],
                      "by_state": {gen46.STATES[i]: [sum(1 for r in span if r["state"] == i),
                                                     sum(r["steps"] for r in span if r["state"] == i)]
                                   for i in sorted({r["state"] for r in span})}}
    out["q3"] = q3
    # 4: hit1 back to PLAY with greset and no flip: over_jp.events walked
    path = build_variant("game", hit_play=True)
    res = analyse("over", JP, path=path, game=model46.Keep(JP, rom=str(path), hit_play=True))
    gv = res["game"]
    out["q4"] = {"touches": [[e[0], e[2]] for e in gv.events if e[1] == "TOUCH"],
                 "plays": [e[0] for e in gv.events if e[1] == "PLAY"],
                 "ended": [list(e) for e in gv.events if e[1] == "ENDED"],
                 "loops": len(res["rows"])}
    shutil.rmtree(path.parent)
    # 5: the tune in every state: over_jp.events walked, the pages' margins
    path = build_variant("game", tune_always=True)
    res = analyse("over", JP, path=path, game=model46.Keep(JP, rom=str(path), tune_always=True))
    data, regs_, lost, _ = taken_writes(res, JP)
    marg = page_margins(res, JP, data)
    rows = res["rows"]
    out["q5"] = {"least": min(p["least"] for p in marg), "pages": [p["least"] for p in marg],
                 "game_least": [p["least"] for p in fl["over"]["jp"]["pages"]],
                 "isr_play": [min(r["isr"] for r in rows if r["state"] != 0),
                              max(r["isr"] for r in rows if r["state"] != 0)],
                 "lost": len(lost), "halt_max": max(r["halt"] for r in rows)}
    shutil.rmtree(path.parent)
    # 6: A1's two guards on lines that meet: game_jp.events walked to its end
    gs = meeting_guards()
    path = build_variant("game", guards=gs)
    gm = model46.Keep(JP, rom=str(path), guards=gs)
    gr, _ = model46.replay(events("game", JP), 4000, JP, guards=gs)
    end = next(e for e in gr.events if e[1] == "ENDED")
    res = analyse("game", JP, path=path, game=gm, frames=end[0] + 20 + EVENT_AHEAD[JP])
    gv = res["game"]
    touches = [e for e in gv.events if e[1] == "TOUCH"]
    came = [e[0] for e in gv.events if e[1] == "ROOM" and e[2] == 0]
    out["q6"] = {"touches": [[e[0], e[2], e[3][1], e[3][0], e[3][5], e[3][4], e[3][9], e[3][8]]
                             for e in touches],
                 "came": came, "ended": [list(e) for e in gv.events if e[1] == "ENDED"],
                 "lines": [gs[0][0][1] + 1, gs[0][0][1] + 16, gs[0][1][1] + 1, gs[0][1][1] + 16]}
    shutil.rmtree(path.parent)
    return out


def bcd_of(b):
    return int(f"{b:02X}")


def openmsx():
    if not versions.builds():
        return {"skipped": "OPENMSX_BUILDS not set"}
    return versions.every_build(["ch46"], OPENMSX_SECTIONS)


OPENMSX_SECTIONS = ["films", "photos", "tune", "prices", "machines", "answers"]
SECTIONS = {"films": films, "photos": photos, "tune": tune, "prices": prices, "machines": machines,
            "answers": answers, "openmsx": openmsx}


def main(names=()):
    CAPS.mkdir(exist_ok=True)
    path_ = HERE / "meas46.json"
    m = json.loads(path_.read_text()) if names and path_.exists() else {}
    for name in names or SECTIONS:
        print(name, flush=True)
        m[name] = SECTIONS[name]()
        m = {k: m[k] for k in SECTIONS if k in m}
        path_.write_text(json.dumps(m, indent=1) + "\n")
    return m


if __name__ == "__main__":
    main(sys.argv[1:])
