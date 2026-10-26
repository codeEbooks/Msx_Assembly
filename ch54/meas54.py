#!/usr/bin/env python3
"""meas54.py -- LANTERN KEEP's title and demo, measured.

    python3 gen54.py && ./build.sh && python3 model54.py && python3 meas54.py
                                  python3 meas54.py films photos   only these

  films     three plays on each machine: attract (game.rom, no key pressed:
            the title, the demo, the title again), play (game.rom, a game
            from play_jp.events or play_eu.events) and broken (frames.rom,
            no key pressed). The debugger stops where each loop wakes, after
            its sends and at its end, and in the interrupt routine; it reads
            the variables, the player's page, the copy of the names, the
            map's page and the rooms' pictures where the loop wakes, and the
            name table, the sprites' attributes and R#3, R#4 and R#1 after
            the sends; watchpoints log every byte to and from the VDP's ports
            and to the PSG's, from INIT. Every loop is held against
            model54.py's game fed the same keys, the PSG's writes in its
            interrupt against the player's, and its T-states against walk.py
            run on the RAM the debugger read. The VDP's bytes are played
            through vdpslots.py (chapter 20): none lost, the VRAM at the end
            the debugger's and the model's
  demo      what the films say of the demo: at 60 Hz every loop of the demo
            is a loop of the game played with its keys, but for the demo's
            own bytes; at 50 Hz, after every step, the explorer, the guards,
            the lanterns and the score are where they are after as many
            steps at 60 Hz; frames.rom at 50 Hz, where it leaves the demo
  photos    the figures' frames and others, each against vdpscreen.py's
            picture of the VRAM line by line, as the bytes reached it
            (figures 54.1 to 54.3)
  prices    what each new routine costs, from walk.py
  answers   the workshop, tried (for Appendix I)
  openmsx   all of it again with every other build (tools/versions.py)
"""
import json
import shutil
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
import model54     # noqa: E402
gen54 = model54.gen54
gen46, gen45 = gen54.gen46, gen54.gen45
model46 = model54.model46
sys.path.remove(str(HERE))
sys.path.insert(0, str(HERE))      # other chapters came first: this folder's files win
for mod in ("vdpscreen", "walk", "vdpslots"):
    sys.modules.pop(mod, None)
import vdpscreen   # noqa: E402
import walk        # noqa: E402
import vdpslots    # noqa: E402

assert Path(vdpscreen.__file__).parent == HERE and Path(walk.__file__).parent == HERE
assert Path(vdpslots.__file__).parent == HERE
assert Path(vdpscreen.__file__).read_bytes() == Path(model46.vdpscreen.__file__).read_bytes()

CAPS = HERE / "captures"
SHOTS = HERE / "shots"
EU, JP = gen54.EU, gen54.JP
MACHINES = gen54.MACHINES
TAG = {EU: "eu", JP: "jp"}
L = 228
LINE = vdpslots.LINE
FT = {EU: 71364, JP: 59736}
FLAG_LINE = {EU: 261, JP: 234}
PAPER0 = {EU: 69, JP: 42}
SIGNAL = Fraction(101, 3)                   # F rises at T-state 33 2/3 of its line (chapter 19)
BACK = 5 + 11                               # isr's EI and RET, after isrend
POS = "[machine_info VDP_frame_count] [machine_info VDP_cycle_in_frame]"
PLAYS = {"attract": "game", "play": "game", "broken": "frames"}     # each play's cartridge
FILMS = [(p, m) for p in ("attract", "play", "broken") for m in (JP, EU)]
VARS = (gen46.VARS_AT, 256)
ENGINE = (gen46.ENGINE_AT, 128)
NAMES_RAM = (gen45.NAMES_AT, 768)
MAPN = (gen45.MAPN_AT, 736)
MINIS = (gen45.MINIS_AT, 16 * 96)
PALETTE = [tuple(c) for c in json.loads((REPO / "ch01" / "meas01.json").read_text())["palette"]["rgb"]]
CODE = {rgb: n for n, rgb in enumerate(PALETTE) if n}
R15 = 0x8F                                  # register 15 as joy leaves it: port 1, pins 6-7 high
EVENT_AHEAD = model54.EVENT_AHEAD
AFTER_SHOWN = 30                            # loops filmed after the title is shown again
OUT_JSON = HERE / "meas54.json"

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
F0 = 'L "i0 [machine_info VDP_frame_count]"\n'
VDP_WP = ('debug set_watchpoint write_io {0x98 0x99} {} '
          '{ L "w [expr {$::wp_last_address & 255}] $::wp_last_value ' + POS + '" }\n'
          'debug set_watchpoint read_io 0x98 {} { L "r 152 - ' + POS + '" }\n')
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
    if play != "play":
        return {}
    return model54.read_events(model54.events_path("play", machine))


def run(path, machine, frames, tcl, ev, at_end=None):
    tev = model54.tcl_events(ev)
    if at_end:
        tev[frames - 1] = (tev[frames - 1] + "; " if frames - 1 in tev else "") + at_end
    lines = msxcap.run_tcl(path, frames, F0 + TOO_FAST + tcl, machine=machine,
                           tcl_setup=STATE, timeout=7200, events=tev)
    return [line.split() for line in lines]


def codes(png):
    im = Image.open(png).convert("RGB")
    px = im.load()
    return [[CODE.get(px[x, y]) for x in range(im.width)] for y in range(im.height)]


# ---------------------------------------------------------------- the plays, as the model has them
def model_run(play, machine):
    """the model of a play, to its end: the loops it takes and the game"""
    g = model54.Keep(machine, PLAYS[play])
    ev = events(play, machine)
    shown = 0
    while True:
        g.step_loop(model54.keys_at(ev, g.ticks + 1 + EVENT_AHEAD[machine]))
        if g.events and g.events[-1][1] == "SHOWN" and g.events[-1][0] == g.loop:
            shown += 1
        if shown == 2 and g.loop >= g.events[-1][0] + AFTER_SHOWN or g.loop > 20000:
            break
    assert shown == 2, (play, machine)
    return g.loop + 1, g


LOOPS = {}


def play_frames(play, machine):
    if (play, machine) not in LOOPS:
        LOOPS[(play, machine)] = model_run(play, machine)[0]
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
            "score": at("score", 3), "hi": at("hi", 3),
            "pkeys": at("pkeys"), "demo": at("demo"), "dleft": at("dleft"), "dnext": w("dnext"),
            "idle": w("idle"), "part": at("part"), "pnext": w("pnext"), "pvram": w("pvram"),
            "cnext": w("cnext"), "cvram": w("cvram"), "upto": at("upto")}


def model_ram(g):
    r = g.ram()
    r["held"] = g.held
    return r


def engine_same(page, g):
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
         "hit0", "over0", "win0", "title0", "box", "lamps", "greset", "shown", "draw0")
MARKS = ("show", "flip0", "map0", "mini", "hit0", "over0", "win0", "title0", "box", "lamps", "greset",
         "shown", "draw0")


def film(name, machine, frames, ev):
    """the debugger's log of a play"""
    s = sym(name)
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
           "".join(f'debug set_bp {s[k]} {{}} {{ L "{k} {POS}" }}\n' for k in KINDS[5:]) +
           VDP_WP + PSG_WP)
    w = run(rom(name), machine, frames, tcl, ev, at_end='VR end 0 16384')
    f0 = int(next(x for x in w if x[0] == "i0")[1])
    fast = [x for x in w if x[0] == "fast"]
    out, pend, ops = [], {}, []
    for x in w:
        k = x[0]
        if k in KINDS:
            f, c = t_abs(x[1], x[2])
            e = {"kind": k, "frame": f - f0, "t": f * FT[machine] + c}
            out.append(e)
            pend = e
        elif k in ("w", "r"):
            ops.append((int(x[3]) - f0, int(x[4]), int(x[1]), None if x[2] == "-" else int(x[2])))
        elif k == "psg":
            f, c = t_abs(x[3], x[4])
            out.append({"kind": "psg", "port": int(x[1]), "value": int(x[2]), "frame": f - f0,
                        "t": f * FT[machine] + c})
        elif k == "regs":
            pend["regs"] = [int(v) for v in x[1:]]
        elif len(x) == 3 and x[1] in ("mem", "vram"):
            pend[x[0]] = bytes.fromhex(x[2])
    end = next((x for x in w if x[0] == "end"), None)
    return f0, out, s, ops, (bytes.fromhex(end[2]) if end else None), fast


def signal_of(frame, machine):
    return frame * FT[machine] + FLAG_LINE[machine] * L + SIGNAL


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


def analyse(play, machine):
    """a play on MACHINE against the model fed the same keys, loop by loop"""
    name = PLAYS[play]
    ev = events(play, machine)
    f0, evs, s, ops, end_vram, fast = film(name, machine, play_frames(play, machine), ev)
    assert not fast, (play, machine, "an access too soon", fast[:3])
    loops = loops_of(evs)
    g = model54.Keep(machine, name)
    wk = walker(HERE / name, 0x80 if machine == EU else 0)
    rows, rams = [], []
    tail = wk.run("ran", "frame")
    for k, lp in enumerate(loops):
        wake_frame = lp["wake"]["frame"]
        sig = signal_of(wake_frame + f0, machine)
        assert sig <= lp["wake"]["t"] < sig + 40, (play, machine, k)
        g.loop += 1
        ticked = len(g.psg)
        keys = model54.keys_at(ev, g.ticks + 1 + EVENT_AHEAD[machine])
        g.isr(keys)
        tick = len(g.psg) > ticked
        want_isr = JOY_WRITES + (tochip(g.psg[-1][1]) if tick else [])
        assert lp["psg_isr"] == want_isr, (play, machine, k, "the PSG in the interrupt", lp["psg_isr"][:12], want_isr[:12], tick)
        got = ram_state(s, lp["woke"]["v"], lp["woke"]["e"])
        want = model_ram(g)
        assert got == want, (play, machine, k, {x: (got[x], want[x]) for x in got if got[x] != want[x]})
        assert not engine_same(lp["woke"]["e"], g), (play, machine, k, "the player's page")
        assert list(lp["woke"]["nm"]) == g.names, (play, machine, k, "the copy of the names")
        assert list(lp["woke"]["mp"]) == g.mapn or g.mapn == [0] * 736 and not any(lp["woke"]["mp"]), \
            (play, machine, k, "the map's page")
        assert list(lp["woke"]["mi"]) == sum(g.minis, []), (play, machine, k, "the pictures")
        assert got["ticks"] == wake_frame - EVENT_AHEAD[machine], (play, machine, k, "ticks",
                                                                   got["ticks"], wake_frame)
        state0 = g.state
        g.sends()
        assert list(lp["sent"]["sat"]) == g.copy, (play, machine, k, "the attributes")
        assert g.vnames is None or list(lp["sent"]["names"]) == g.vnames, (play, machine, k, "the names")
        assert lp["sent"]["regs"] == [g.r3, g.r4, g.r1], (play, machine, k, "R#3, R#4, R#1",
                                                         lp["sent"]["regs"], [g.r3, g.r4, g.r1])
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
        g.run()
        steps = g.steps_taken[-1][1] if len(g.steps_taken) > nsteps else 0
        assert lp["psg_logic"] == [], (play, machine, k, "the PSG in the logic")
        nxt = loops[k + 1]["wake"]["frame"] if k + 1 < len(loops) else None
        rows.append({"loop": k, "frame": wake_frame, "state": state0, "steps": steps,
                     "isr": num(lp["wake_end"]["t"] - lp["wake"]["t"] + BACK),
                     "sends": num(lp["sent"]["t"] - lp["woke"]["t"]),
                     "logic": num(lp["ran"]["t"] - lp["sent"]["t"]),
                     "halt": num(lp["ran"]["t"] + tail - sig),
                     "lost": None if nxt is None else nxt - wake_frame - 1,
                     "marks": {kk: [num(e["t"] - sig) for e in v] for kk, v in lp["marks"].items() if v}})
        rams.append((got, list(lp["woke"]["nm"]), list(lp["sent"]["sat"]), list(lp["sent"]["names"])))
    return {"f0": f0, "rows": rows, "rams": rams, "tail": tail, "ev": evs, "game": g, "ops": ops,
            "end_vram": end_vram}


# ---------------------------------------------------------------- the bytes to the VDP
def taken_writes(res, machine):
    """the film's port operations played through vdpslots: (data, regs,
    lost, vram): data [(cycle taken, address, value)], regs [(cycle, reg,
    value)], the cycles counted from the start of film frame 0"""
    flen = vdpslots.LINES[machine] * LINE
    evs = [(fr * flen + cyc, port, val) for fr, cyc, port, val in res["ops"]]
    assert evs == sorted(evs, key=lambda e: e[0])
    written = []
    vram, _, lost = vdpslots.play(evs, machine, vram=bytes(16384), regs=[0, 0xE0, 0, 0, 0, 0, 0, 0],
                                  written=written)
    regs_, held = [], None
    for c, port, v in evs:
        if port != 0x99 or v is None:
            held = None
        elif held is None:
            held = v
        else:
            if v & 0x80:
                regs_.append((c, v & 7, held))
            held = None
    return written, regs_, lost, vram


SPANS = [(0, 0x1B0D), (0x2000, 0x3800), (0x3800, 0x3840)]


def summary(rows):
    rows = rows[1:]
    out = {"loops": len(rows), "lost": sum(r["lost"] or 0 for r in rows),
           "halt_max": max(r["halt"] for r in rows), "states": {},
           "steps": {str(b): sum(1 for r in rows if r["steps"] == b) for b in sorted({r["steps"] for r in rows})}}
    for i, st in enumerate(gen54.STATES):
        rs = [r for r in rows if r["state"] == i]
        if rs:
            out["states"][st] = {"loops": len(rs), "logic": [min(r["logic"] for r in rs),
                                                              max(r["logic"] for r in rs)],
                                 "halt": max(r["halt"] for r in rs)}
    return out


def jsonable(e):
    return [list(x) if isinstance(x, tuple) else x for x in e]


CACHE = {}


def films(which=FILMS):
    out = {}
    for play, m in which:
        res = analyse(play, m)
        CACHE[(play, m)] = res
        g = res["game"]
        data, regs_, lost, vram = taken_writes(res, m)
        assert not lost, (play, m, "bytes lost", len(lost))
        ev_ = res["end_vram"]
        assert all(ev_[a:b] == vram[a:b] for a, b in SPANS), (play, m, "the VRAM played")
        assert all(ev_[a:b] == bytes(g.vram[a:b]) for a, b in SPANS), (play, m, "the VRAM modelled")
        title = [r for r in res["rows"] if r["state"] == model54.TITLE]
        out.setdefault(play, {})[TAG[m]] = {
            "f0": res["f0"], "tail": res["tail"], "loops": len(res["rows"]), "planned": LOOPS[(play, m)],
            "events": [jsonable(e) for e in g.events if e[1] not in ("MINI",)],
            "summary": summary(res["rows"]), "ops": len(res["ops"]),
            "reads": sum(1 for o in res["ops"] if o[3] is None),
            "title_halt": max(r["halt"] for r in title)}
        print("films", play, TAG[m], out[play][TAG[m]]["summary"], flush=True)
    return out


def result(play, machine, cache=CACHE):
    if (play, machine) not in cache:
        cache[(play, machine)] = analyse(play, machine)
    return cache[(play, machine)]


OWN = ("ticks", "was", "held", "demo", "dleft", "dnext", "idle")    # the demo's own bytes, and the keys


def first_loop(res, kind):
    return next(e[0] for e in res["game"].events if e[1] == kind)


def same_loops(a, b, a0, b0, n):
    """loops A0.. of film A against B0.. of film B, N of them: the RAM but
    the demo's own bytes and the keys, the copy of the names, the sprites'
    attributes and the name table -> the first that differs, or None"""
    for k in range(n):
        ra, rb = a["rams"][a0 + k], b["rams"][b0 + k]
        va = {x: v for x, v in ra[0].items() if x not in OWN}
        vb = {x: v for x, v in rb[0].items() if x not in OWN}
        if va != vb or ra[1:] != rb[1:]:
            return k, sorted(x for x in va if va[x] != vb[x])
    return None


PLACE = ("room", "copy", "gd", "lit", "nlit", "score", "time", "tock", "lives", "been")


CUM = [0]
for _n, _k in gen54.DEMO:
    CUM.append(CUM[-1] + _n)


def walked(ram, dpairs):
    """the steps the demo has walked, from where pad is in its pairs"""
    k = (ram["dnext"] - dpairs) // 2
    return 0 if k == 0 else CUM[k] - ram["dleft"] + 1


def by_step(res, start, dpairs):
    """from loop START of a film on: at each loop's wake, the steps the demo
    has walked and what the RAM holds: {steps: place}, the first loop of each"""
    out = {}
    for k in range(start, len(res["rams"])):
        r = res["rams"][k][0]
        if not r["demo"] or r["state"] not in (model54.PLAY, model54.FLIP, model54.WIN):
            continue
        out.setdefault(walked(r, dpairs), {x: r[x] for x in PLACE})
    return out


def keys_by_step(name, machine, until):
    """the keys each step of the demo walked by in NAME's cartridge with no
    key pressed, up to the loop of the first UNTIL, from model54.py's game,
    which the films matched loop by loop"""
    given = []

    class Log(model54.Keep):
        def walk(self):
            if self.demo:
                given.append(self.pkeys)
            return model54.Keep.walk(self)
    g = Log(machine, name)
    while not any(e[1] == until for e in g.events):
        g.step_loop(model54.keys_at({}, g.ticks + 1 + EVENT_AHEAD[machine]))
    return given


def demo():
    """the demo, from the films"""
    out = {}
    aj, pj = result("attract", JP), result("play", JP)
    a0, p0 = first_loop(aj, "DEMO"), first_loop(pj, "PRESSED")
    end = first_loop(aj, "ENDED") - a0
    assert first_loop(pj, "ENDED") - p0 == end
    diff = same_loops(aj, pj, a0, p0, end + 1)
    assert diff is None, diff
    after = same_loops(aj, pj, a0 + end + 1, p0 + end + 1, 3)
    names = {i: n for i, n in enumerate(gen54.STATES)}
    by_state = {}
    for r in aj["rows"][a0:a0 + end + 1]:
        by_state[names[r["state"]]] = by_state.get(names[r["state"]], 0) + 1
    out["jp_same"] = {"from_demo": a0, "from_play": p0, "loops": end + 1, "then": after,
                      "states": by_state, "walked": sum(r["steps"] for r in aj["rows"][a0:a0 + end + 1]
                                                        if r["state"] == model54.PLAY),
                      "still": sum(1 for r in aj["rows"][a0:a0 + end + 1]
                                   if r["state"] == model54.PLAY and not r["steps"])}
    # the 50 Hz demo, step by step, against the 60 Hz one
    ae = result("attract", EU)
    e0 = first_loop(ae, "DEMO")
    dp = sym("game")["dpairs"]
    assert sym("frames")["dpairs"] == dp
    sj, se = by_step(aj, a0, dp), by_step(ae, e0, dp)
    common = sorted(set(sj) & set(se))
    bad = [n for n in common if sj[n] != se[n]]
    assert not bad, bad[:5]
    out["eu_steps"] = {"compared": len(common), "steps": max(common), "eu_loops": first_loop(ae, "ENDED") - e0 + 1,
                       "jp_loops": end + 1,
                       "ended": [e for e in ae["game"].events if e[1] == "ENDED"][0][2:],
                       "two_steps": sum(1 for r in ae["rows"][e0:first_loop(ae, "ENDED") + 1]
                                        if r["steps"] == 2)}
    # frames.rom: on the 60 Hz machine game.rom's demo, loop for loop; on the
    # 50 Hz machine, where it leaves it
    bj, be = result("broken", JP), result("broken", EU)
    n = min(len(bj["rams"]), len(aj["rams"]))
    assert same_loops(bj, aj, 0, 0, n) is None
    b0 = first_loop(be, "DEMO")
    assert b0 == e0
    k = next(k for k in range(b0, len(be["rams"])) if be["rams"][k][0]["copy"] != ae["rams"][k][0]["copy"])
    first = walked(ae["rams"][k][0], dp)
    ev = be["game"].events
    out["broken"] = {"jp_loops_same": n, "eu_first_step": first, "eu_first_loop": k - b0,
                     "touches": [e[0] - b0 for e in ev if e[1] == "TOUCH"],
                     "ended": [e[2:] for e in ev if e[1] == "ENDED"][0],
                     "ended_loop": first_loop(be, "ENDED") - b0}
    # the first pair, step by step: game.rom gives its keys for as many steps
    # as it has, frames.rom for as many frames
    right, wrong = keys_by_step("game", EU, "ENDED"), keys_by_step("frames", EU, "TOUCH")
    assert right == gen54.DEMO_KEYS
    n0, k0 = gen54.DEMO[0]
    out["broken"]["first_pair"] = {"steps": n0, "keys": k0, "frames_rom": next(
        i for i, k in enumerate(wrong) if k != k0)}
    assert right[:n0] == [k0] * n0 and right[n0] != k0
    # figure 54.3: the frame of the first touch, drawn from the RAM of the loop before
    t = first_loop(be, "TOUCH")
    kk = t - 1
    assert loop_frame(be, kk) == be["rows"][t]["frame"] == loop_frame(ae, kk)
    rb, ra = be["rams"][kk][0], ae["rams"][kk][0]
    assert ra["copy"][4:12] == rb["copy"][4:12] and ra["state"] == rb["state"] == model54.PLAY
    out["broken"]["photo"] = {"frame": be["rows"][t]["frame"], "loop": kk - b0,
                              "steps": walked(ra, dp), "explorer": {"frames": rb["copy"][:2],
                                                                    "game": ra["copy"][:2]},
                              "guard": ra["copy"][4:6], "guards": sum(1 for y in (ra["copy"][4], ra["copy"][8])
                                                                      if y != 0xD0)}
    # the best: after the demo the title shows 002000; after a game, the game's
    out["best"] = {"attract": model46.bcd3(aj["game"].hi), "play": model46.bcd3(pj["game"].hi)}
    print("demo", out, flush=True)
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


def row_start(frame, machine):
    """the cycle at which the VDP starts drawing the paper's first line in
    film frame FRAME"""
    return (frame * vdpslots.LINES[machine] + PAPER0[machine]) * LINE + vdpslots.BORDER_IN


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
            ls = row_start(n, machine) + y * LINE
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
        out[n] = (rows, mixed, regs[7] & 15)
    return out


def full_picture(paper, border):
    out = []
    for y in range(meas.CAPTURE_H):
        row = [None] * meas.CAPTURE_W
        for x in range(meas.DRAWN[0], meas.DRAWN[1] + 1):
            px, py = x - meas.PAPER_X0, y - meas.PAPER_Y0
            row[x] = paper[py][px] if 0 <= px < 256 and 0 <= py < 192 else border
        out.append(row)
    return out


def against(photo, pic, mixed, border):
    """pixels of the capture's drawn part that are neither the model's line
    nor, in a line where a byte reached the VRAM, the line after it"""
    full = full_picture(pic, border)
    bad = 0
    for y in range(meas.CAPTURE_H):
        py = y - meas.PAPER_Y0
        for x in range(meas.DRAWN[0], meas.DRAWN[1] + 1):
            p = photo[y][x]
            if p != full[y][x]:
                px = x - meas.PAPER_X0
                if not (py in mixed and 0 <= px < 256 and p == mixed[py][px]):
                    bad += 1
    return bad


def photo_set(play, machine, res, frames, keep=()):
    """FRAMES of a play's film photographed and held against the line by line
    model; the offsets that fit"""
    name = PLAYS[play]
    data, regs_, lost, _ = taken_writes(res, machine)
    want = sorted(frames)
    models = line_pictures(data, regs_, machine, want)
    shots = sorted({c + d for c in want for d in (-1, 0, 1)})
    tmp = Path(tempfile.mkdtemp(prefix="ph54_"))
    pngs = msxcap.capture(rom(name), shots, tmp, f"{play}_{TAG[machine]}_f", machine=machine,
                          events=model54.tcl_events(events(play, machine)), timeout=7200)
    ph = {c: codes(pngs[c]) for c in shots}
    fits = [d for d in (-1, 0, 1) if all(against(ph[c + d], *models[c]) == 0 for c in want)]
    assert fits, (play, machine, [(c, d, against(ph[c + d], *models[c])) for c in want for d in (-1, 0, 1)])
    d = 0 if 0 in fits else fits[0]
    out = {}
    for c in want:
        dest = (CAPS if c in keep else SHOTS) / pngs[c + d].name.replace(f"_f{c + d:04d}", f"_f{c:04d}")
        dest.parent.mkdir(exist_ok=True)
        shutil.copy(pngs[c + d], dest)
        out[c] = dest.name
    shutil.rmtree(tmp)
    return fits, out


def loop_frame(res, k):
    """the film frame that shows what the RAM held at loop K's wake: the
    sends of loop K, in the frame after its signal"""
    return res["rows"][k]["frame"] + 1


def photo_plan():
    """the figures' frames: 54.1 the title on the 50 Hz machine; 54.2 the
    game on the 60 Hz machine and the demo on the 50 Hz one, at the same step,
    the explorer in A1 with both lanterns lit; 54.3 frames.rom and game.rom on
    the 50 Hz machine, at the frame of frames.rom's first touch"""
    dp = sym("game")["dpairs"]
    ae, pj, be = result("attract", EU), result("play", JP), result("broken", EU)
    shown = first_loop(ae, "SHOWN")
    p0, e0 = first_loop(pj, "PRESSED"), first_loop(ae, "DEMO")
    steps_j = {}
    for k in range(p0, len(pj["rams"])):
        r = pj["rams"][k][0]
        if r["state"] == model54.PLAY and r["room"] == FIG_ROOM and r["lit"][2 * FIG_ROOM] and \
                r["lit"][2 * FIG_ROOM + 1]:
            steps_j.setdefault(sum(rw["steps"] for rw in pj["rows"][p0 + 1:k]), k)
    steps_e = {}
    for k in range(e0, len(ae["rams"])):
        r = ae["rams"][k][0]
        if r["demo"] and r["state"] == model54.PLAY:
            steps_e.setdefault(walked(r, dp), k)
    s = min(n for n in steps_j if n in steps_e and n >= min(steps_j) + FIG_AFTER)
    kj, ke = steps_j[s], steps_e[s]
    assert pj["rams"][kj][0]["copy"] == ae["rams"][ke][0]["copy"]
    t = first_loop(be, "TOUCH")
    return {"title": loop_frame(ae, shown) + 1, "same_step": s,
            "game_jp": loop_frame(pj, kj), "demo_eu": loop_frame(ae, ke),
            "touch": be["rows"][t]["frame"]}


FIG_ROOM = 0                # figure 54.2: A1
FIG_AFTER = 40              # steps after the explorer first stands there with both lit
SAMPLE = 400                # and a frame every so many loops of every film


def photos():
    plan = photo_plan()
    out = {"plan": plan}
    keep = {("attract", EU): {plan["title"], plan["demo_eu"], plan["touch"]},
            ("play", JP): {plan["game_jp"]}, ("broken", EU): {plan["touch"]}}
    for play, m in FILMS:
        res = result(play, m)
        frames = set(keep.get((play, m), set()))
        frames.add(loop_frame(res, first_loop(res, "SHOWN")) + 1)
        frames.add(loop_frame(res, first_loop(res, "FLIP")) + 1)
        frames |= {loop_frame(res, k) for k in range(SAMPLE, len(res["rows"]) - 1, SAMPLE)}
        fits, shots = photo_set(play, m, res, frames, keep=keep.get((play, m), set()))
        out.setdefault(play, {})[TAG[m]] = {"fits": fits, "frames": {str(k): v for k, v in shots.items()}}
        print("photos", play, TAG[m], fits, len(shots), flush=True)
    return out


# ---------------------------------------------------------------- prices
def fresh(name="game", machine=JP):
    """a walker at main, INIT done: the title's first row next"""
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


def word(wk, label):
    a, b = peek(wk, label, 2)
    return a | b << 8


def prices():
    out = {"init": {TAG[m]: fresh(machine=m).init_t for m in MACHINES}}
    # the title: each row, then shown, then a frame of the count
    wk = fresh()
    out["title_rows"] = [wk.call("title1") for _ in range(gen54.ROWS)]
    assert peek(wk, "part") == [gen54.ROWS] and word(wk, "pvram") == 0x1800 and word(wk, "cvram") == 0x3800
    assert word(wk, "pnext") == wk.sym["tpat"] + len(gen54.TPAT_LZ) - 1 == wk.sym["tcol"] - 1
    out["shown"] = wk.call("title1")
    poke(wk, "due", [262 & 255, 262 >> 8])
    poke(wk, "held", [0xBF])
    out["title_count"] = wk.call("title1")
    out["title0"] = fresh().call("title0")
    # DRAW: the display off, six blocks, and the last frame: row 0, setup, the first flip
    wk = fresh()
    out["draw0"] = wk.call("draw0")
    out["draw_blocks"] = [wk.call("draw1") for _ in range(gen54.BLOCKS)]
    out["draw_last"] = wk.call("draw1")
    assert peek(wk, "state") == [model54.FLIP]
    # pad: a game; the demo's first pair; the same keys; the end
    wk = fresh()
    wk.call("setup")
    poke(wk, "held", [0xB7])
    out["pad_game"] = wk.call("pad")
    assert peek(wk, "pkeys") == [0xB7]
    poke(wk, "demo", [1])
    out["pad_pair"] = wk.call("pad")
    assert peek(wk, "pkeys") == [gen54.DEMO[0][1]] and peek(wk, "dleft") == [gen54.DEMO[0][0]]
    assert gen54.DEMO[0][0] > 1
    out["pad_same"] = wk.call("pad")
    poke(wk, "dleft", [1])
    end = wk.sym["dpairs"] + 2 * len(gen54.DEMO)
    poke(wk, "dnext", [end & 255, end >> 8])
    out["pad_end"] = wk.call("pad")
    assert peek(wk, "pkeys") == [0xFF] and peek(wk, "dleft") == [1]
    out["demo_bytes"] = 2 * len(gen54.DEMO) + 1
    out["demo_pairs"] = len(gen54.DEMO)
    out["demo_steps"] = len(gen54.DEMO_KEYS)
    out["title_bytes"] = {"patterns": len(gen54.TPAT_LZ), "colours": len(gen54.TCOL_LZ)}
    print("prices", out, flush=True)
    return out


# ---------------------------------------------------------------- the workshop
def variant(name, **kw):
    """gen54.program(NAME, **KW) assembled in a folder of its own: its .rom
    and .sym"""
    import subprocess
    tmp = Path(tempfile.mkdtemp(prefix="var54_"))
    for f in ("msx.inc", "bios.inc", "music.inc"):
        shutil.copy(HERE / f, tmp / f)
    (tmp / f"{name}.asm").write_text(gen54.program(name, **kw))
    subprocess.run(["sjasmplus", "--nologo", "--msg=err", "--syntax=bFw", f"--sym={name}.sym",
                    f"{name}.asm"], cwd=tmp, check=True)
    return tmp / f"{name}.rom", tmp / f"{name}.sym"


def light(path, symp, machine, frames, ev, g):
    """a light film: the variables where each loop wakes, against the model G
    fed the same keys, loop by loop; the model at the end"""
    s = dbg.sym(symp)
    tcl = (f'debug set_bp {s["isrend"]} {{}} {{ L "isrend" }}\n'
           f'debug set_bp {s["woke"]} {{}} {{ L "woke {POS}"; M v {VARS[0]} {VARS[1]}; '
           f'M e {ENGINE[0]} {ENGINE[1]} }}\n')
    w = run(path, machine, frames, tcl, ev)
    vs, es, last = [], [], None
    for i, x in enumerate(w):         # a woke after isrend: the loop's; HALT's own start logs one too
        if x[0] == "woke" and last == "isrend":
            vs.append(bytes.fromhex(w[i + 1][2]))
            es.append(bytes.fromhex(w[i + 2][2]))
        if x[0] in ("woke", "isrend"):
            last = x[0]
    wakes = vs
    for k in range(len(wakes)):
        g.loop += 1
        g.isr(model54.keys_at(ev, g.ticks + 1 + EVENT_AHEAD[machine]))
        got, want = ram_state(s, vs[k], es[k]), model_ram(g)
        assert got == want, (k, {x: (got[x], want[x]) for x in got if got[x] != want[x]})
        g.sends()
        g.run()
    return len(wakes)


STOP_AT = 300               # the demo's loop at which SPACE is pressed (question 2)
STOP_FOR = 40               # and the frames it is held: longer than the title takes to draw


def answers():
    out = {}
    fl = json.loads(OUT_JSON.read_text())
    # 1. the lanterns once a frame, as in chapter 46: the demo at 50 Hz, until its keys end
    g = model54.Keep(EU, lamps_frame=True)
    loops = None
    while g.loop < 20000:
        g.step_loop(set())
        if g.demo and g.dnext is not None and g.dnext >= len(gen54.DEMO) and loops is None:
            loops = g.loop
            break
    rom_, symp = variant("game", lamps_frame=True)
    g2 = model54.Keep(EU, lamps_frame=True, sym_path=str(symp))
    n = light(rom_, symp, EU, loops + 3 + EVENT_AHEAD[EU], {}, g2)
    lit_eu = model46.bcd(g2.nlit)
    g3 = model54.Keep(JP, lamps_frame=True)
    while not any(e[1] == "ENDED" for e in g3.events):
        g3.step_loop(set())
    out["q1"] = {"eu_lit": lit_eu, "eu_loops": n, "lit_model": model46.bcd(g.nlit),
                 "jp_ended": [e[2:] for e in g3.events if e[1] == "ENDED"][0]}
    # what the 50 Hz demo then does: the model, to its end
    while not any(e[1] == "ENDED" for e in g.events) and g.loop < 40000:
        g.step_loop(set())
    out["q1"]["eu_ended"] = [list(e[2:]) for e in g.events if e[1] == "ENDED"][0]
    out["q1"]["eu_ended_loop"] = [e[0] for e in g.events if e[1] == "ENDED"][0] - \
        [e[0] for e in g.events if e[1] == "DEMO"][0]
    # 2. SPACE held 40 frames to stop the demo: game.rom, and title0 without LD (was),A
    q2 = {}
    for keep in (False, True):
        g = model54.Keep(JP, keep_was=keep)
        start = None
        ev = {}
        while g.loop < 3000:
            g.step_loop(model54.keys_at(ev, g.ticks + 1 + EVENT_AHEAD[JP]))
            if g.demo and start is None:
                start = g.loop
                f = g.ticks + EVENT_AHEAD[JP] + STOP_AT
                ev = {f: frozenset({"space"}), f + STOP_FOR: frozenset()}
            if any(e[1] in ("PRESSED", "DEMO") and e[0] > start + STOP_AT for e in g.events) if start else False:
                break
        what = [e for e in g.events if e[1] in ("STOPPED", "SHOWN", "PRESSED", "DEMO") and start and e[0] >= start]
        frames = what[-1][0] + 5 + EVENT_AHEAD[JP]
        rom_, symp = (variant("game", keep_was=True) if keep else (rom("game"), HERE / "game.sym"))
        g2 = model54.Keep(JP, keep_was=keep, sym_path=str(symp))
        nloops = light(rom_, symp, JP, frames, ev, g2)
        q2["keep_was" if keep else "game"] = {"events": [[e[0] - start, e[1]] for e in what], "loops": nloops}
    out["q2"] = q2
    # 3. the demo's length, in frames and seconds, at both rates
    out["q3"] = {}
    for m in MACHINES:
        evs = fl["films"]["attract"][TAG[m]]["events"]
        a = next(e[0] for e in evs if e[1] == "DEMO")
        b = next(e[0] for e in evs if e[1] == "ENDED")
        out["q3"][TAG[m]] = {"frames": b - a + 1, "seconds": round((b - a + 1) * FT[m] / 3579545, 1)}
    # 4. a demo kept, a step at a time, from chapter 46's game planned on the
    # 50 Hz machine, game_eu.events, and played back on both
    keys = gen54.demo_keys(EU)
    pairs = gen54.pairs_of(keys)
    old = gen54.DEMO, gen54.DEMO_KEYS
    gen54.DEMO, gen54.DEMO_KEYS = pairs, keys
    ended = {}
    try:
        for m in MACHINES:
            g = model54.Keep(m)
            while not any(e[1] == "ENDED" for e in g.events) and g.loop < 20000:
                g.step_loop(set())
            ended[TAG[m]] = [e[2:] for e in g.events if e[1] == "ENDED"][0]
    finally:
        gen54.DEMO, gen54.DEMO_KEYS = old
    out["q4"] = {"steps": len(keys), "pairs": len(pairs), "bytes": 2 * len(pairs) + 1,
                 "jp_ended": ended["jp"], "eu_ended": ended["eu"]}
    print("answers", out, flush=True)
    return out


# ---------------------------------------------------------------- openMSX's builds
def openmsx():
    """all the other sections again with every build: each run in
    versions.rerun() must end within its time limit"""
    if not versions.builds():
        return {"skipped": "OPENMSX_BUILDS not set"}
    out = {}
    for part in OPENMSX_SECTIONS:
        for label, r in versions.every_build(["ch54"], part).items():
            o = out.setdefault(label, {"values": 0, "same_values": 0, "captures": 0,
                                       "same_captures": 0, "same_in_drawn": 0, "failed": [],
                                       "different": []})
            for k in ("values", "same_values", "failed", "different"):
                o[k] += r[k]
            for k in ("captures", "same_captures", "same_in_drawn"):
                o[k] = max(o[k], r[k])
            o["version"], o["sha256"] = r["version"], r["sha256"]
    return out


def main(names=()):
    CAPS.mkdir(exist_ok=True)
    m = json.loads(OUT_JSON.read_text()) if names and OUT_JSON.exists() else {}
    for name in names or SECTIONS:
        print(name, flush=True)
        m[name] = SECTIONS[name]()
        m = {k: m[k] for k in SECTIONS if k in m}
        OUT_JSON.write_text(json.dumps(m, indent=1) + "\n")
    return m


OPENMSX_SECTIONS = [["films", "demo", "photos", "prices", "answers"]]
SECTIONS = {"films": films, "demo": demo, "photos": photos, "prices": prices, "answers": answers,
            "openmsx": openmsx}

if __name__ == "__main__":
    main(sys.argv[1:])
