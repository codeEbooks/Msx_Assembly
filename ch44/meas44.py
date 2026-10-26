#!/usr/bin/env python3
"""meas44.py -- GRIN ALLEY finished, measured.

    python3 gen44.py && ./build.sh && python3 model44.py && python3 meas44.py
                                  python3 meas44.py films prices   only these

  films     game.rom and extra.rom played on each machine from the events
            planned for it. The debugger stops where each loop wakes, after
            its sends and at its end, and in the interrupt routine; it reads
            the game's page, the player's page and the score where the loop
            wakes, and the name table and the sprites' attributes after the
            sends; a watchpoint logs every write to the PSG. Every loop is
            held against model44.py's game fed the same keys: the RAM, the
            player's page (player37.py, reading the cartridge), the status
            isr kept, the names and the attributes, the PSG's writes; and
            every loop's T-states against walk.py run on the RAM the
            debugger read
  photos    frames of the plays photographed, each against vdpscreen.py's
            picture of the VRAM the model gives (figures 44.1 to 44.4)
  prices    what each new routine costs, from walk.py
  speed     the game's steps and the player's ticks a second on each machine
  machines  the finished cartridge on every machine of the book: the play,
            and the title's photograph
  shares    the moments a crossing of alley 1 may begin, for each speed
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
import gen44       # noqa: E402
sys.path.remove(str(HERE))
sys.path.insert(0, str(HERE))      # gen44 put other chapters first: this folder's files win
for mod in ("vdpscreen", "walk", "player37"):
    sys.modules.pop(mod, None)
import vdpscreen   # noqa: E402
import walk        # noqa: E402
import player37    # noqa: E402
import model44     # noqa: E402

assert Path(vdpscreen.__file__).parent == HERE and Path(walk.__file__).parent == HERE
assert Path(player37.__file__).parent == HERE

CAPS = HERE / "captures"
SHOTS = HERE / "shots"
EU, JP = gen44.EU, gen44.JP
MACHINES = gen44.MACHINES
TAG = {EU: "eu", JP: "jp"}
L = 228
CLOCK = 3579545
FT = {EU: 71364, JP: 59736}
FLAG_LINE = {EU: 261, JP: 234}
PAPER0 = {EU: 69, JP: 42}                   # the paper's first line in the VDP's frame (chapter 33)
SIGNAL = Fraction(101, 3)                   # F rises at T-state 33 2/3 of its line (chapter 19)
TO_PAPER = {EU: 121 * L - SIGNAL, JP: 70 * L - SIGNAL}
BACK = 5 + 11                               # isr's EI and RET, after isrend
POS = "[machine_info VDP_frame_count] [machine_info VDP_cycle_in_frame]"
PROGRAMS = gen44.PROGRAMS
VARS = (gen44.VARS_AT, 256)
ENGINE = (gen44.ENGINE_AT, 256)
NUMS = (0xC700, 8)
SHOWN = (0xC800, 8)
NAMES_RAM = (0xC400, 768)
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
PSG_WP = ('debug set_watchpoint write_io {0xA0 0xA1} {} '
          '{ L "psg [expr {$::wp_last_address & 255}] $::wp_last_value ' + POS + '" }\n')


def rom(name):
    return HERE / f"{name}.rom"


def sym(name):
    return dbg.sym(HERE / f"{name}.sym")


def t_abs(fc, cyc):
    return int(fc), Fraction(int(cyc), 6)


def num(f):
    return int(f) if f == int(f) else round(float(f), 2)


def events(machine):
    return model44.read_events(model44.events_path(machine))


def run(name, machine, frames, tcl, path=None, ev=None, real=None):
    ev = events(real or machine) if ev is None else ev
    lines = msxcap.run_tcl(path or rom(name), frames, F0 + TOO_FAST + tcl, machine=machine,
                           tcl_setup=STATE, timeout=3600, events=model44.tcl_events(ev))
    return [l.split() for l in lines]


def codes(png):
    im = Image.open(png).convert("RGB")
    px = im.load()
    return [[CODE.get(px[x, y]) for x in range(im.width)] for y in range(im.height)]


def loops_planned(machine):
    keys, g, recs = model44.plan(machine)
    return len(recs)


PLAY_FRAMES = {m: loops_planned(m) + 2 for m in MACHINES}


# ---------------------------------------------------------------- what the RAM says
def ram_state(s, v, n, sh):
    def at(label, k=1):
        a = s[label] - VARS[0]
        return v[a] if k == 1 else list(v[a:a + k])
    nb = s["score"] - NUMS[0]
    return {"stat": at("stat"), "ticks": at("ticks") | at("ticks", 2)[1] << 8,
            "seed": at("seed") | at("seed", 2)[1] << 8, "state": at("state"), "left": at("left"),
            "lives": at("lives"), "gems": at("gems"), "roundno": at("roundno"), "stale": at("stale"),
            "shownl": at("shownl"), "queued": at("queued"), "copy": at("copy", 21),
            "steps": at("steps", 4), "due": at("due") | at("due", 2)[1] << 8, "value": at("value"),
            "bonus": at("bonus"), "tock": at("tock"), "awarded": at("awarded"),
            "score": list(n[nb:nb + 3]), "hi": list(n[nb + 3:nb + 6]),
            "held": at("held"), "shown": list(sh[:6])}


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
def walker(name, rate, row8=0xFF, path=None):
    wk = walk.Walk(path or HERE / name)
    psg = {"reg": 0}
    keys = {"row8": row8}

    def read_port(port, t):
        if port == 0xA9:
            return keys["row8"]
        if port == 0xA2:
            last = [v for _, p, v in wk.ports if p == 0xA0]
            psg["reg"] = last[-1] if last else 0
            return {14: model44.JOY_IDLE, 15: R15}.get(psg["reg"], 0)
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


def row8_of(keys):
    v = 0xFF
    for k in keys:
        v &= ~model44.ROW8[k] & 0xFF
    return v


# ---------------------------------------------------------------- the films
KINDS = ("isr", "isrend", "woke", "sent", "ran", "touch", "input", "arena", "title0")


def film(name, machine, frames, path=None, ev=None, light=False, real=None):
    """the debugger's log of a play"""
    s = dbg.sym(path.with_suffix(".sym")) if path else sym(name)
    if light:
        tcl = "".join(f'debug set_bp {s[k]} {{}} {{ L "{k} {POS}" }}\n'
                      for k in ("isr", "isrend", "woke", "sent", "ran", "touch", "input"))
        tcl += f'debug set_bp {s["woke"]} {{}} {{ M v {VARS[0]} 128; M n {NUMS[0]} {NUMS[1]} }}\n'
    else:
        tcl = (f'debug set_bp {s["isr"]} {{}} {{ L "isr {POS}"; M v {VARS[0]} {VARS[1]}; '
               f'M e {ENGINE[0]} {ENGINE[1]} }}\n'
               f'debug set_bp {s["isrend"]} {{}} {{ L "isrend {POS}" }}\n'
               f'debug set_bp {s["woke"]} {{}} {{ L "woke {POS}"; M v {VARS[0]} {VARS[1]}; '
               f'M e {ENGINE[0]} {ENGINE[1]}; '
               f'M n {NUMS[0]} {NUMS[1]}; M sh {SHOWN[0]} {SHOWN[1]}; M nm {NAMES_RAM[0]} {NAMES_RAM[1]} }}\n'
               f'debug set_bp {s["sent"]} {{}} {{ L "sent {POS}"; VR sat {model44.SAT} 21; '
               f'VR names {0x1800} 768 }}\n'
               f'debug set_bp {s["ran"]} {{}} {{ L "ran {POS}" }}\n'
               f'debug set_bp {s["touch"]} {{}} {{ L "touch {POS}" }}\n'
               f'debug set_bp {s["input"]} {{}} {{ L "input {POS}" }}\n'
               f'debug set_bp {s["arena"]} {{}} {{ L "arena {POS}" }}\n'
               f'debug set_bp {s["title0"]} {{}} {{ L "title0 {POS}" }}\n' + PSG_WP)
    w = run(name, machine, frames, tcl, path=path.with_suffix(".rom") if path else None, ev=ev,
            real=real)
    f0 = int(next(x for x in w if x[0] == "f0")[1])
    assert not [x for x in w if x[0] == "fast"], (name, machine, "an access too soon")
    out, pend = [], {}
    for x in w:
        k = x[0]
        if k in KINDS:
            f, c = t_abs(x[1], x[2])
            e = {"kind": k, "frame": f - f0, "t": f * FT[real or machine] + c}
            out.append(e)
            pend = e
        elif k == "psg":
            f, c = t_abs(x[3], x[4])
            out.append({"kind": "psg", "port": int(x[1]), "value": int(x[2]), "frame": f - f0,
                        "t": f * FT[real or machine] + c})
        elif len(x) == 3 and x[1] in ("mem", "vram"):
            pend[x[0]] = bytes.fromhex(x[2])
    return f0, out, s


def signal_of(frame, machine):
    return frame * FT[machine] + FLAG_LINE[machine] * L + SIGNAL


def loops_of(ev):
    """the films cut into loops: the interrupt that woke each, where it woke,
    its sends' end, its end, the PSG's writes in its interrupt and in its
    logic, and any interrupt inside"""
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
                      "psg_isr": [(e["port"], e["value"]) for e in ev[j:a] if e["kind"] == "psg"],
                      "psg_logic": [(e["port"], e["value"]) for e in seg
                                    if e["kind"] == "psg" and e["t"] < ran["t"]],
                      "touch": [e for e in seg if e["kind"] == "touch"],
                      "input": [e for e in ev[j:a] if e["kind"] == "input"],
                      "arena": [e for e in seg if e["kind"] == "arena"],
                      "title0": [e for e in seg if e["kind"] == "title0"]})
    return loops


def tochip(shadow):
    out = []
    for r, v in enumerate(shadow):
        out += [(0xA0, r), (0xA1, v)]
    return out


JOY_WRITES = [(0xA0, 15), (0xA1, R15), (0xA0, 14)]


def model_for(name, machine, **kw):
    return model44.Grin(machine, once=(name != "extra"), **kw)


def analyse(name, machine, ev=None, frames=None, path=None, **kw):
    """a play of NAME on MACHINE against the model fed the same keys"""
    ev = events(machine) if ev is None else ev
    nloops = frames or PLAY_FRAMES[machine]
    f0, evs, s = film(name, machine, nloops, path=path, ev=ev)
    loops = loops_of(evs)
    g = model_for(name, machine, rom=str(path) if path else None, **kw)
    rate = 0x80 if machine == EU else 0
    wk = walker(name, rate, path=path)
    rows, sent = [], []
    tail = wk.run("ran", "frame")
    for k, lp in enumerate(loops):
        wake_frame = lp["wake"]["frame"]
        sig = signal_of(wake_frame + f0, machine)
        assert sig <= lp["wake"]["t"] < sig + 40, (name, machine, k)
        # the interrupt: the PSG's writes, and the RAM it read
        g.loop += 1
        ticked = len(g.psg)
        keys = model44.keys_at(ev, g.ticks + 1 + model44.EVENT_AHEAD)
        g.isr(keys)
        tick = len(g.psg) > ticked
        want_isr = JOY_WRITES + (tochip(g.psg[-1][1]) if tick else [])
        assert lp["psg_isr"] == want_isr, (name, machine, k, "the PSG in the interrupt",
                                           lp["psg_isr"][:8], want_isr[:8])
        got = ram_state(s, lp["woke"]["v"], lp["woke"]["n"], lp["woke"]["sh"])
        want = model_ram(g)
        if g.held is None:
            got["held"] = None
        assert got == want, (name, machine, k, {x: (got[x], want[x]) for x in got if got[x] != want[x]})
        diff = engine_same(lp["woke"]["e"], g)
        assert not diff, (name, machine, k, "the player's page", diff)
        if g.names is not None:
            assert list(lp["woke"]["nm"]) == g.names, (name, machine, k, "the copy of the names")
        assert got["ticks"] == wake_frame - 1, (name, machine, k, "ticks", got["ticks"], wake_frame)
        g.sends()
        assert list(lp["sent"]["sat"]) == g.vsat[:21], (name, machine, k, "the attributes")
        assert list(lp["sent"]["names"]) == g.vnames, (name, machine, k, "the names",
                                                       [(i, a, b) for i, (a, b) in
                                                        enumerate(zip(lp["sent"]["names"], g.vnames)) if a != b][:8])
        sent.append((lp["sent"]["t"], {"vnames": list(g.vnames), "vsat": list(g.vsat)}))
        wk.keys["row8"] = row8_of(keys)
        state0 = g.state
        blocks = [(VARS[0], lp["woke"]["v"]), (ENGINE[0], lp["woke"]["e"]), (NUMS[0], lp["woke"]["n"]),
                  (SHOWN[0], lp["woke"]["sh"]), (NAMES_RAM[0], lp["woke"]["nm"])]
        t_walk = walk_from(wk, blocks, "woke", "ran")
        took = lp["ran"]["t"] - lp["woke"]["t"]
        assert not lp["inside"], (name, machine, k, "an interrupt inside")
        assert all(e["frame"] == wake_frame for e in lp["input"]), (name, machine, k, "keys late")
        assert took == t_walk, (name, machine, k, took, t_walk)
        t_sends = walk_from(wk, blocks, "woke", "sent")
        assert t_sends == lp["sent"]["t"] - lp["woke"]["t"], (name, machine, k, "sends")
        ti = walk_from(wk, [(VARS[0], lp["wake"]["v"]), (ENGINE[0], lp["wake"]["e"])], "isr", "isrend")
        assert ti == lp["wake_end"]["t"] - lp["wake"]["t"], (name, machine, k, "isr")
        nsteps = len(g.steps_taken)
        g.run()
        steps = g.steps_taken[-1][1] if len(g.steps_taken) > nsteps else 0
        assert len(g.steps_taken) - nsteps <= 1
        assert lp["psg_logic"] == [], (name, machine, k, "the PSG in the logic", lp["psg_logic"])
        assert bool(lp["touch"]) == (g.state == model44.HIT and state0 == model44.PLAY), (name, machine, k)
        nxt = loops[k + 1]["wake"]["frame"] if k + 1 < len(loops) else None
        rows.append({"loop": k, "frame": wake_frame, "ticks": got["ticks"], "state": state0,
                     "wake": num(lp["wake"]["t"] - sig),
                     "isr": num(lp["wake_end"]["t"] - lp["wake"]["t"] + BACK),
                     "tick": tick,
                     "sends": num(lp["sent"]["t"] - lp["woke"]["t"]),
                     "logic": num(lp["ran"]["t"] - lp["sent"]["t"]),
                     "woke": num(lp["woke"]["t"] - sig), "sent": num(lp["sent"]["t"] - sig),
                     "halt": num(lp["ran"]["t"] + tail - sig),
                     "lost": None if nxt is None else nxt - wake_frame - 1,
                     "stat": got["stat"], "held": got["held"], "screen": g.screen, "steps": steps,
                     "arena": num(lp["arena"][0]["t"] - sig) if lp["arena"] else None,
                     "title0": num(lp["title0"][0]["t"] - sig) if lp["title0"] else None})
    return {"f0": f0, "rows": rows, "tail": tail, "ev": evs, "game": g, "sent": sent}


def summary(rows, machine):
    rows = rows[1:]
    out = {"loops": len(rows), "lost": sum(r["lost"] or 0 for r in rows),
           "isr": [min(r["isr"] for r in rows), max(r["isr"] for r in rows)],
           "isr_quiet": ([min(r["isr"] for r in rows if not r["tick"]),
                          max(r["isr"] for r in rows if not r["tick"])]
                         if any(not r["tick"] for r in rows) else None),
           "ticks": sum(r["tick"] for r in rows),
           "sent_max": max(r["sent"] for r in rows),
           "halt_max": max(r["halt"] for r in rows), "states": {},
           "steps": {str(b): sum(1 for r in rows if r["steps"] == b) for b in sorted({r["steps"] for r in rows})}}
    for i, st in enumerate(gen44.STATES):
        rs = [r for r in rows if r["state"] == i]
        quiet = [r for r in rs if not r["screen"]]
        if not rs:
            continue
        out["states"][st] = {"loops": len(rs),
                             "sends": [min(r["sends"] for r in rs), max(r["sends"] for r in rs)],
                             "logic": [min(r["logic"] for r in rs), max(r["logic"] for r in rs)],
                             "halt": max(r["halt"] for r in rs),
                             "quiet_halt": max(r["halt"] for r in quiet) if quiet else None,
                             "screen": [r["loop"] for r in rs if r["screen"]]}
    out["to_paper"] = num(TO_PAPER[machine])
    out["left"] = num(FT[machine] - out["halt_max"])
    return out


def touches(g, ev, machine):
    g2 = model_for("extra" if not g.once else "game", machine)
    copies, hits = [], []
    for k in range(g.loop + 1):
        g2.loop += 1
        g2.isr(model44.keys_at(ev, g2.ticks + 1 + model44.EVENT_AHEAD))
        g2.sends()
        st0 = g2.state
        g2.run()
        copies.append(list(g2.copy))
        if st0 == model44.PLAY and g2.state == model44.HIT:
            hits.append(k)

    def c_of(copy):
        return (g2.status_of(copy + [0] * 11) >> 5) & 1
    out = []
    for h in hits:
        j = max(i for i in range(h) if not c_of(copies[i])) + 1
        out.append({"loop": h, "met": j, "lag": h - j, "runner": copies[j][0:2], "faces": copies[j][4:20]})
    return out


def jsonable(e):
    return [list(x) if isinstance(x, tuple) else x for x in e]


def films():
    out = {}
    for name in PROGRAMS:
        out[name] = {}
        for m in MACHINES:
            res = analyse(name, m)
            rows, g = res["rows"], res["game"]
            out[name][TAG[m]] = {"rows": rows, "f0": res["f0"], "tail": res["tail"],
                                 "events": [jsonable(e) for e in g.events],
                                 "fx": [list(x) for x in g.fx_asked],
                                 "psg_ticks": len(g.psg),
                                 "summary": summary(rows, m), "touches": touches(g, events(m), m)}
            print(name, TAG[m], out[name][TAG[m]]["summary"], flush=True)
    return out


# ---------------------------------------------------------------- the photos
def vram_of(st):
    g = model44.Grin.__new__(model44.Grin)
    g.vnames, g.vsat = st["vnames"], st["vsat"]
    return model44.Grin.vram(g)


def picture(st):
    paper = vdpscreen.draw(vram_of(st), model44.REGS)
    out = []
    for y in range(meas.CAPTURE_H):
        row = [None] * meas.CAPTURE_W
        for x in range(meas.DRAWN[0], meas.DRAWN[1] + 1):
            px, py = x - meas.PAPER_X0, y - meas.PAPER_Y0
            row[x] = paper[py][px] if 0 <= px < 256 and 0 <= py < 192 else gen44.BORDER
        out.append(row)
    return out


def mismatch(model, photo_):
    return sum(1 for y in range(meas.CAPTURE_H) for x in range(meas.DRAWN[0], meas.DRAWN[1] + 1)
               if model[y][x] != photo_[y][x])


def frame_model(res, machine, c):
    f0 = res["f0"]
    start = (f0 + c) * FT[machine] + PAPER0[machine] * L
    end = start + 192 * L
    done = [st for t, st in res["sent"] if t < start]
    for r, (t, _) in zip(res["rows"], res["sent"]):
        lp_end = signal_of(r["frame"] + f0, machine) + Fraction(r["halt"]).limit_denominator(3)
        if r["screen"]:
            assert lp_end < start or t > end, (machine, c, "names written while the paper is drawn")
    return picture(done[-1]), done[-1]


def photo_set(name, machine, res, frames, keep=(), ev=None):
    want = sorted(frames)
    models = {c: frame_model(res, machine, c) for c in want}
    shots = sorted({c + d for c in want for d in (-1, 0, 1)})
    tmp = Path(tempfile.mkdtemp(prefix="ph44_"))
    pngs = msxcap.capture(rom(name), shots, tmp, f"{name}_{TAG[machine]}_f", machine=machine,
                          events=model44.tcl_events(ev or events(machine)), timeout=1800)
    ph = {c: codes(pngs[c]) for c in shots}
    fits = [d for d in (-1, 0, 1) if all(mismatch(models[c][0], ph[c + d]) == 0 for c in want)]
    assert len(fits) == 1, (name, machine, fits,
                            [(c, d, mismatch(models[c][0], ph[c + d])) for c in want for d in (-1, 0, 1)])
    d = fits[0]
    out = {}
    for c in want:
        dest = (CAPS if c in keep else SHOTS) / pngs[c + d].name.replace(f"_f{c + d:04d}", f"_f{c:04d}")
        dest.parent.mkdir(exist_ok=True)
        shutil.copy(pngs[c + d], dest)
        out[c] = dest.name
    shutil.rmtree(tmp)
    return d, out


def loop_frame(res, loop):
    return res["rows"][loop]["frame"] + 1


def photo_plan(res):
    ev = res["game"].events
    rounds = [e for e in ev if e[1] == "ROUND"]
    clr = [e for e in ev if e[1] == "CLEARED"]
    life = next(e[0] for e in ev if e[1] == "LIFE")
    over = next(e[0] for e in ev if e[1] == "OVER")
    assert life == clr[1][0] and rounds[2][0] == life
    return {"title": loop_frame(res, 40), "cleared": [loop_frame(res, life), loop_frame(res, life + 1)],
            "life": life, "over": loop_frame(res, over + 30)}


def photos():
    out = {}
    for m in MACHINES:
        res = analyse("game", m)
        plan_ = photo_plan(res)
        frames = [plan_["title"], plan_["over"]] + plan_["cleared"]
        res_x = analyse("extra", m)
        lives_x = [(r["loop"], r["frame"]) for r in res_x["rows"]]
        # the frame both plays show, a while after the extra's lives reach their most
        gx = res_x["game"]
        nine = next(e[0] for e in gx.events if e[1] == "LIFE" and e[2] == gen44.MAX_LIVES)
        plan_["nine"] = nine
        plan_["after"] = loop_frame(res, nine + 30)
        assert lives_x[nine + 30][1] == res["rows"][nine + 30]["frame"]
        frames.append(plan_["after"])
        keep = set(frames) if m == EU else set()
        d, shots = photo_set("game", m, res, frames, keep=keep)
        dx, shots_x = photo_set("extra", m, res_x, [plan_["after"]], keep=keep)
        out[TAG[m]] = {"plan": plan_, "offset": d, "frames": shots, "extra_offset": dx, "extra": shots_x}
        print("photos", TAG[m], plan_, d, dx, flush=True)
    return out


# ---------------------------------------------------------------- prices
def fresh(name="game", machine=JP, row8=0xFF):
    wk = walker(name, 0x80 if machine == EU else 0, row8)
    wk.run("init", "main")
    return wk


def poke(wk, label, vals, off=0):
    a = wk.sym[label] + off
    for i, v in enumerate(vals):
        wk.mem[a + i] = v & 255


def peek(wk, label, n=1, off=0):
    a = wk.sym[label] + off
    return list(wk.mem[a:a + n])


def playing(row8=0xFF, machine=JP):
    wk = fresh(row8=row8, machine=machine)
    poke(wk, "seed", [1, 0])
    wk.call("setup")
    wk.call("round")
    poke(wk, "state", [model44.PLAY])
    wk.call("sends")
    return wk


def prices():
    out = {}
    # the interrupt: no tick of the player, and ticks with and without a row
    wk = fresh()
    seen = {}
    for _ in range(400):
        owed = peek(wk, "owed", 2)
        o = owed[0] | owed[1] << 8
        tick = peek(wk, "tick")[0]
        t = wk.call("isr")
        kind = "quiet" if o + 262 < 313 else ("row" if tick == 1 else "tick")
        seen.setdefault(kind, []).append(t)
    out["isr"] = {k: [min(v), max(v)] for k, v in seen.items()}
    # paced: one step, two steps
    wk = playing()
    poke(wk, "due", [262 & 255, 262 >> 8])
    out["paced_one"] = wk.call("paced")
    poke(wk, "due", [600 & 255, 600 >> 8])
    out["paced_two"] = wk.call("paced")
    assert wk.r["b"] == 2
    # drop: the count on; a ten fewer
    poke(wk, "tock", [5])
    out["drop_none"] = wk.call("drop")
    poke(wk, "tock", [1])
    poke(wk, "queued", [0])
    out["drop_ten"] = wk.call("drop")
    poke(wk, "queued", [0])
    cell = wk.sym["names"] + gen44.BONUS_AT
    out["post2"] = wk.call("post2", a=0x42, h=cell >> 8, l=cell & 255)
    poke(wk, "score", [0, 0, 0])
    out["addten"] = wk.call("addten", a=0x99)
    assert peek(wk, "score", 3) == [0, 0x09, 0x90]
    # fx: nothing sounding, the sound taken; a sound of a higher priority
    # sounding, refused
    wk = playing()
    out["fx_taken"] = wk.call("fx", a=model44.SOUND["S_GEM"])
    wk.call("fx", a=model44.SOUND["S_OVER"])
    out["fx_refused"] = wk.call("fx", a=model44.SOUND["S_GEM"])
    # award: won already; below 1,000; a life, its sound taken
    wk = playing()
    poke(wk, "awarded", [1])
    out["award_won"] = wk.call("award")
    poke(wk, "awarded", [0])
    poke(wk, "score", [0, 0x09, 0x90])
    out["award_below"] = wk.call("award")
    poke(wk, "score", [0, 0x10, 0x00])
    out["award_life"] = wk.call("award")
    assert peek(wk, "lives") == [gen44.LIVES + 1]
    # took, a gem at the start of a game: its sound taken, no life
    wk = playing()
    cell = wk.sym["names"] + 32 * 9 + 15
    poke(wk, "queued", [0])
    out["took"] = wk.call("took", h=cell >> 8, l=cell & 255)
    # speeds, and round 2 and cleared from the first round of a game
    wk = playing()
    out["speeds"] = wk.call("speeds")
    poke(wk, "queued", [0])
    out["round"] = wk.call("round")
    wk = playing()
    poke(wk, "queued", [0])
    out["cleared"] = wk.call("cleared")
    out["sends"] = playing().call("sends")
    out["input"] = playing().call("input")
    w2 = playing()
    w2.call("input")
    out["step"] = w2.call("step")
    out["title0"] = fresh().call("title0")
    out["arena"] = fresh().call("arena")
    out["setup"] = fresh().call("setup")
    out["over0"] = playing().call("over0")
    out["hit0"] = playing().call("hit0")
    return out


# ---------------------------------------------------------------- the speed
def speed(fl=None):
    """steps and the player's ticks a second, from the films; and when each
    round was cleared, in seconds from the loop that saw SPACE"""
    fl = fl or json.loads((HERE / "meas44.json").read_text())["films"]
    out = {}
    for m in MACHINES:
        f = fl["game"][TAG[m]]
        rows = f["rows"][1:]
        frames = rows[-1]["frame"] - rows[0]["frame"] + 1
        steps = sum(r["steps"] for r in rows)
        ticks = sum(r["tick"] for r in rows)
        secs = frames * FT[m] / CLOCK
        frame_of = {r["loop"]: r["frame"] for r in f["rows"]}
        start = frame_of[next(e[0] for e in f["events"] if e[1] == "PRESSED")]
        out[TAG[m]] = {"frames": frames, "steps": steps, "ticks": ticks, "seconds": round(secs, 4),
                       "steps_a_second": round(steps / secs, 3), "ticks_a_second": round(ticks / secs, 3),
                       "two": sum(1 for r in rows if r["steps"] == 2),
                       "one": sum(1 for r in rows if r["steps"] == 1),
                       "cleared": [round((frame_of[e[0]] - start) * FT[m] / CLOCK, 2)
                                   for e in f["events"] if e[1] == "CLEARED"],
                       "over": round((frame_of[next(e[0] for e in f["events"] if e[1] == "OVER")] - start)
                                     * FT[m] / CLOCK, 2)}
    return out


# ---------------------------------------------------------------- every machine
OTHERS = ["MSXBOOK_EU32", "MSXBOOK_EU64", "MSXBOOK_EU16X", "MSXBOOK_EU16E", "MSXBOOK_EU16AY",
          "MSXBOOK_EU16P", "MSXBOOK_EU16G"]


def light_loops(name, machine, path=None, ev=None, frames=None, real=None):
    f0, evs, s = film(name, machine, frames or PLAY_FRAMES[real or machine], path=path, ev=ev,
                      light=True, real=real)
    out = []
    for lp in loops_of(evs):
        v = lp["woke"]["v"]
        n = lp["woke"]["n"]
        out.append({"frame": lp["wake"]["frame"], "input": [e["frame"] for e in lp["input"]],
                    "touch": len(lp["touch"]), "ram": list(v[:16]) + list(v[0x40:0x55]) + list(n[:6])})
    return out


def model_light(g):
    """what light_loops reads, from the model"""
    r = g.ram()
    v = bytearray(16)
    v[0] = r["stat"]
    v[1], v[2] = r["ticks"] & 255, r["ticks"] >> 8
    v[3], v[4] = r["seed"] & 255, r["seed"] >> 8
    v[5], v[6], v[7], v[8], v[9] = r["state"], r["left"], r["lives"], r["gems"], r["roundno"]
    v[10] = g.held if g.held is not None else 0
    v[11], v[12], v[13] = r["stale"], r["shownl"], r["queued"]
    return list(v[:16]), r["copy"] + r["score"] + r["hi"]


TITLE_FRAME = 43


def title_state(frame, machine=EU):
    """what the sends before capture frame FRAME left, with no key held: the
    loop that wakes in frame f shows its sends in frame f + 1, and loop k
    wakes in frame k + 2"""
    g = model_for("game", machine)
    for _ in range(frame - 3):
        g.step_loop(set())
    g.loop += 1
    g.isr(set())
    g.sends()
    return {"vnames": list(g.vnames), "vsat": list(g.vsat)}


def title_photo(machine, frame):
    """the title on MACHINE photographed, frames FRAME - 1 to FRAME + 1,
    against the model: the one offset that fits, and its mismatch"""
    tmp = Path(tempfile.mkdtemp(prefix="mc44_"))
    pngs = msxcap.capture(rom("game"), [frame - 1, frame, frame + 1], tmp, f"title_{machine}_f",
                          machine=machine, timeout=600)
    model = picture(title_state(frame, EU if machine != JP else JP))
    fits = {d: mismatch(model, codes(pngs[frame + d])) for d in (-1, 0, 1)}
    shutil.rmtree(tmp)
    best = min(fits, key=lambda d: fits[d])
    return best, fits[best]


def machines():
    """the finished cartridge on every machine: the play planned for its
    rate, loop for loop against the model, and the title's photograph"""
    out = {}
    for m in OTHERS:
        rows = light_loops("game", m, real=EU)
        g = model_for("game", EU)
        bad = []
        for k, r in enumerate(rows):
            g.loop += 1
            g.isr(model44.keys_at(events(EU), g.ticks + 1 + model44.EVENT_AHEAD))
            got = r["ram"]
            head, tail = model_light(g)
            if k > 0 and (got[:16] != head or got[16:] != tail):
                bad.append(k)
            g.sends()
            g.run()
        title = TITLE_FRAME
        d, mism = title_photo(m, title)
        out[m] = {"loops": len(rows), "wrong": bad[:10], "title_offset": d, "title_mismatch": mism}
        print("machine", m, out[m], flush=True)
    # the 8 KB machine: no RAM at $C000: the title's photographs, frames apart,
    # against the model's title, and where the processor is two seconds on
    tmp = Path(tempfile.mkdtemp(prefix="mc44_"))
    pngs = msxcap.capture(rom("game"), [TITLE_FRAME, 200], tmp, "eu8_f", machine="MSXBOOK_EU8", timeout=600)
    a, b = codes(pngs[TITLE_FRAME]), codes(pngs[200])
    names = gen44.title_names()
    bare = picture({"vnames": names, "vsat": [0xD0] + [0] * 31})
    SHOTS.mkdir(exist_ok=True)
    shutil.copy(pngs[200], SHOTS / "eu8_f0200.png")
    shutil.rmtree(tmp)
    probe = 'after time 2 { L "pc [format %04X [reg pc]] sp [format %04X [reg sp]] iff [reg iff]" }\n'
    regs = {}
    for m in ("MSXBOOK_EU8", "MSXBOOK_EU16"):
        lines = msxcap.run_tcl(rom("game"), 200, probe, machine=m, timeout=600)
        regs[m] = next(l for l in lines if l.startswith("pc")).split()[1::2]
    out["MSXBOOK_EU8"] = {"still": mismatch(a, b), "bare_title": mismatch(bare, b), "regs": regs}
    print("machine EU8", out["MSXBOOK_EU8"], flush=True)
    return out


# ---------------------------------------------------------------- the shares
def shares():
    """the moments a crossing of alley 1 may begin, for each speed of its
    face: the runner at every other X of the corridor above, the face at
    each place, going either way, one step each loop"""
    p = model44.Player()
    out = {}
    y0, y1 = model44.ZONE_Y[1], model44.ZONE_Y[2]
    fy = gen44.LANES[1] - 1
    for sp in range(1, gen44.MAXS + 1):
        ok = total = 0
        for x in range(gen44.X_MIN, gen44.X_MAX + 1, 2):
            for fx in range(gen44.X_MIN, gen44.X_MAX + 1):
                for way in (1, -1):
                    total += 1
                    ok += p.safe(x, y0, y1, [(fy, fx, way * sp)], [1] * 64)
        out[str(sp)] = [ok, total]
    return out


# ---------------------------------------------------------------- the workshop
def build_variant(name="game", **kw):
    d = Path(tempfile.mkdtemp(prefix="v44_"))
    for f in ("msx.inc", "bios.inc", "music.inc"):
        shutil.copy(HERE / f, d / f)
    stem = name + "_" + "_".join(f"{k}" for k in sorted(kw))
    (d / f"{stem}.asm").write_text(gen44.program(name, **kw).replace(f'OUTPUT "{name}.rom"',
                                                                    f'OUTPUT "{stem}.rom"'))
    subprocess.run(["sjasmplus", "--nologo", "--msg=err", "--syntax=bFw", f"--sym={stem}.sym",
                    f"--lst={stem}.lst", f"{stem}.asm"], cwd=d, check=True)
    return d / stem


def answers():
    out = {}
    ev = events(JP)
    # 1: EVERY 4, the 60 Hz machine's play
    path = build_variant("game", every=4)
    g = analyse("game", JP, ev=ev, path=path, every=4)["game"]
    out["q1"] = {"cleared": [[e[2], e[3], e[4]] for e in g.events if e[1] == "CLEARED"]}
    shutil.rmtree(path.parent)
    # 2: award before addten in cleared
    path = build_variant("game", award_first=True)
    g = analyse("game", JP, ev=ev, path=path, award_first=True)["game"]
    life = next(e for e in g.events if e[1] == "LIFE")
    clr2 = [e for e in g.events if e[1] == "CLEARED"][1]
    took = [e for e in g.events if e[1] == "TOOK" and e[0] == life[0]]
    out["q2"] = {"life": [life[0], life[3]], "life_took": [list(t) for t in took],
                 "cleared2": [clr2[0], clr2[4]],
                 "fx_at_clear": [x[1:] for x in g.fx_asked if x[0] == clr2[0]],
                 "fx_at_life": [x[1:] for x in g.fx_asked if x[0] == life[0]]}
    shutil.rmtree(path.parent)
    # 3: the player careful in every round, for ten rounds or 9,000 loops
    for m in MACHINES:
        p = model44.Player(careful=99)
        g = model_for("game", m)
        while g.loop < 9000 and model44.bcd(g.roundno) < 10:
            g.loop += 1
            g.isr_head()
            keys = p.choose(g)
            g.isr_tail(keys)
            g.sends()
            g.run()
        out.setdefault("q3", {})[TAG[m]] = {"loops": g.loop, "round": model44.bcd(g.roundno),
                                           "touches": sum(1 for e in g.events if e[1] == "HIT"),
                                           "score": g.score}
    # 4: a step a frame, as chapter 43 counted, on the 50 Hz machine: planned
    # again, and played by a cartridge that counts so
    p = model44.Player()
    keys, g, recs = model44.plan(EU, player=p, game=model44.Grin(EU, frames_paced=True))
    ev4 = model44.events_of(keys)
    path = build_variant("game", frames_paced=True)
    res = analyse("game", EU, ev=ev4, path=path, frames=len(recs) + 2, frames_paced=True)
    shutil.rmtree(path.parent)
    rows = res["rows"]
    frame_of = {r["loop"]: r["frame"] for r in rows}
    start = frame_of[next(e[0] for e in g.events if e[1] == "PRESSED")]
    out["q4"] = {"loops": len(recs), "machine_loops": len(rows),
                 "cleared": [round((frame_of[e[0]] - start) * FT[EU] / CLOCK, 2)
                             for e in g.events if e[1] == "CLEARED"],
                 "steps": sorted({r["steps"] for r in rows[1:]})}
    return out


def openmsx():
    if not versions.builds():
        return {"skipped": "OPENMSX_BUILDS not set"}
    return versions.every_build(["ch44"], OPENMSX_SECTIONS)


OPENMSX_SECTIONS = ["films", "photos", "prices", "machines", "answers"]
SECTIONS = {"films": films, "photos": photos, "prices": prices, "speed": speed, "machines": machines,
            "shares": shares, "answers": answers, "openmsx": openmsx}


def main(names=()):
    CAPS.mkdir(exist_ok=True)
    path_ = HERE / "meas44.json"
    m = json.loads(path_.read_text()) if names and path_.exists() else {}
    for name in names or SECTIONS:
        print(name, flush=True)
        m[name] = SECTIONS[name]()
        m = {k: m[k] for k in SECTIONS if k in m}
        path_.write_text(json.dumps(m, indent=1) + "\n")
    return m


if __name__ == "__main__":
    main(sys.argv[1:])
