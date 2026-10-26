#!/usr/bin/env python3
"""meas43.py -- GRIN ALLEY, measured.

    python3 gen43.py && ./build.sh && python3 model43.py && python3 meas43.py
                                  python3 meas43.py films prices   only these

  films     game.rom and stale.rom played from game.events on both machines.
            The debugger stops where each loop wakes, after its sends and at
            its end, and in the interrupt routine; it reads the RAM where
            the loop wakes and the name table and the sprites' attributes
            after the sends. Every loop is held against model43.py's game
            fed the same keys: the RAM, the status isr kept (C and the
            sprite's number, by vdpscreen.py's rules 11 and 12), the names
            and the attributes; and every loop's T-states against walk.py
            run on the RAM the debugger read
  photos    frames of the play photographed, each against vdpscreen.py's
            picture of the VRAM the model gives (figures 43.1 to 43.4)
  prices    what each routine costs, from walk.py, on the paths that matter
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
import gen43       # noqa: E402
sys.path.remove(str(HERE))
sys.path.insert(0, str(HERE))      # gen43 put other chapters first: this folder's files win
for mod in ("vdpscreen", "walk"):
    sys.modules.pop(mod, None)
import vdpscreen   # noqa: E402
import walk        # noqa: E402
import model43     # noqa: E402

assert Path(vdpscreen.__file__).parent == HERE and Path(walk.__file__).parent == HERE

CAPS = HERE / "captures"
SHOTS = HERE / "shots"
EU, JP = gen43.EU, gen43.JP
MACHINES = gen43.MACHINES
TAG = {EU: "eu", JP: "jp"}
L = 228
FT = {EU: 71364, JP: 59736}
FLAG_LINE = {EU: 261, JP: 234}
PAPER0 = {EU: 69, JP: 42}                   # the paper's first line in the VDP's frame (chapter 33)
SIGNAL = Fraction(101, 3)                   # F rises at T-state 33 2/3 of its line (chapter 19)
TO_PAPER = {m: (PAPER0[m] + 313 - FLAG_LINE[m] if m == EU else PAPER0[m] + 262 - FLAG_LINE[m]) * L - SIGNAL
            for m in MACHINES}              # from the signal to the paper's first line
ANSWER = 19 + 11                            # mode 2's answer and the JP (chapter 17)
BACK = 5 + 11                               # isr's EI and RET, after isrend
POS = "[machine_info VDP_frame_count] [machine_info VDP_cycle_in_frame]"
PROGRAMS = gen43.PROGRAMS
VARS = (gen43.VARS_AT, 256)
NUMS = (0xC700, 8)
SHOWN = (0xC800, 8)
NAMES_RAM = (0xC400, 768)
PALETTE = [tuple(c) for c in json.loads((REPO / "ch01" / "meas01.json").read_text())["palette"]["rgb"]]
CODE = {rgb: n for n, rgb in enumerate(PALETTE) if n}

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
assert TO_PAPER[JP] == 70 * L - SIGNAL and TO_PAPER[EU] == 121 * L - SIGNAL


def rom(name):
    return HERE / f"{name}.rom"


def sym(name):
    return dbg.sym(HERE / f"{name}.sym")


def t_abs(fc, cyc):
    return int(fc), Fraction(int(cyc), 6)


def num(f):
    return int(f) if f == int(f) else round(float(f), 2)


def events():
    return model43.read_events(HERE / "game.events")


def run(name, machine, frames, tcl, path=None, ev=None):
    ev = events() if ev is None else ev
    lines = msxcap.run_tcl(path or rom(name), frames, F0 + TOO_FAST + tcl, machine=machine,
                           tcl_setup=STATE, timeout=3600, events=model43.tcl_events(ev))
    return [l.split() for l in lines]


def codes(png):
    im = Image.open(png).convert("RGB")
    px = im.load()
    return [[CODE.get(px[x, y]) for x in range(im.width)] for y in range(im.height)]


def loops_planned():
    """the loops of the planned play"""
    keys, g, recs = model43.plan()
    return len(recs)


PLAY_FRAMES = loops_planned() + 2           # the film: the play, from INIT


# ---------------------------------------------------------------- what the RAM says
def ram_state(s, v, n, sh):
    """the game's state from the VARS page and the score's page the debugger
    read where a loop wakes"""
    def at(label, k=1):
        a = s[label] - VARS[0]
        return v[a] if k == 1 else list(v[a:a + k])
    nb = s["score"] - NUMS[0]
    return {"stat": at("stat"), "ticks": at("ticks") | at("ticks", 2)[1] << 8,
            "seed": at("seed") | at("seed", 2)[1] << 8, "state": at("state"), "left": at("left"),
            "lives": at("lives"), "gems": at("gems"), "last": at("last"), "stale": at("stale"),
            "shownl": at("shownl"), "queued": at("queued"), "copy": at("copy", 21),
            "steps": at("steps", 4), "score": list(n[nb:nb + 3]), "hi": list(n[nb + 3:nb + 6]),
            "held": at("held"), "shown": list(sh[:6])}


def model_ram(g):
    r = g.ram()
    r["held"] = g.held
    return r


# ---------------------------------------------------------------- walk
def walker(name, rate, row8=0xFF, path=None):
    wk = walk.Walk(path or HERE / name)
    psg = {"reg": 0}
    keys = {"row8": row8}

    def read_port(port, t):
        if port == 0xA9:
            return keys["row8"]             # row 8 of the keyboard
        if port == 0xA2:                    # the PSG's register chosen last
            last = [v for _, p, v in wk.ports if p == 0xA0]
            psg["reg"] = last[-1] if last else 0
            return {14: model43.JOY_IDLE, 15: 0x8F}.get(psg["reg"], 0)
        if port == 0xAA:
            return 0x50                     # port C as C-BIOS leaves it
        return 0x80                         # the VDP's status: F
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
        v &= ~model43.ROW8[k] & 0xFF
    return v


# ---------------------------------------------------------------- the films
def film(name, machine, frames, path=None, ev=None, light=False):
    """the debugger's log of a play: stops where each loop wakes, after its
    sends and at its end, and in the interrupt routine"""
    s = dbg.sym(path.with_suffix(".sym")) if path else sym(name)
    if light:
        tcl = "".join(f'debug set_bp {s[k]} {{}} {{ L "{k} {POS}" }}\n'
                      for k in ("isr", "isrend", "woke", "sent", "ran", "touch", "input"))
        tcl += f'debug set_bp {s["woke"]} {{}} {{ M v {VARS[0]} 16 }}\n'
    else:
        tcl = (f'debug set_bp {s["isr"]} {{}} {{ L "isr {POS}"; M v {VARS[0]} {VARS[1]} }}\n'
               f'debug set_bp {s["isrend"]} {{}} {{ L "isrend {POS}" }}\n'
               f'debug set_bp {s["woke"]} {{}} {{ L "woke {POS}"; M v {VARS[0]} {VARS[1]}; '
               f'M n {NUMS[0]} {NUMS[1]}; M sh {SHOWN[0]} {SHOWN[1]}; M nm {NAMES_RAM[0]} {NAMES_RAM[1]} }}\n'
               f'debug set_bp {s["sent"]} {{}} {{ L "sent {POS}"; VR sat {gen43.gen42.SAT} 21; '
               f'VR names {0x1800} 768 }}\n'
               f'debug set_bp {s["ran"]} {{}} {{ L "ran {POS}" }}\n'
               f'debug set_bp {s["touch"]} {{}} {{ L "touch {POS}" }}\n'
               f'debug set_bp {s["input"]} {{}} {{ L "input {POS}" }}\n'
               f'debug set_bp {s["arena"]} {{}} {{ L "arena {POS}" }}\n')
    w = run(name, machine, frames, tcl, path=path.with_suffix(".rom") if path else None, ev=ev)
    f0 = int(next(x for x in w if x[0] == "f0")[1])
    assert not [x for x in w if x[0] == "fast"], (name, machine, "an access too soon")
    out, pend = [], {}
    for x in w:
        k = x[0]
        if k in ("isr", "isrend", "woke", "sent", "ran", "touch", "input", "arena"):
            f, c = t_abs(x[1], x[2])
            e = {"kind": k, "frame": f - f0, "t": f * FT[machine] + c}
            out.append(e)
            pend = e
        elif len(x) == 3 and x[1] in ("mem", "vram"):
            pend[x[0]] = bytes.fromhex(x[2])
    return f0, out, s


def signal_of(frame, machine):
    return frame * FT[machine] + FLAG_LINE[machine] * L + SIGNAL


def loops_of(ev):
    """the films cut into loops: the interrupt that woke each, where it woke,
    its sends' end, its end, and any interrupt inside"""
    loops = []
    idx = [i for i, e in enumerate(ev) if e["kind"] == "woke"]
    for a, b in zip(idx, idx[1:] + [len(ev)]):
        seg = ev[a:b]
        kinds = [e["kind"] for e in seg]
        if "ran" not in kinds:
            continue
        before = [e for e in ev[:a] if e["kind"] in ("isr", "isrend")][-2:]
        wake, wake_end = before
        assert wake["kind"] == "isr" and wake_end["kind"] == "isrend"
        ran = next(e for e in seg if e["kind"] == "ran")
        inside = [e for e in seg if e["kind"] == "isr" and e["t"] < ran["t"]]
        loops.append({"woke": ev[a], "sent": next(e for e in seg if e["kind"] == "sent"), "ran": ran,
                      "wake": wake, "wake_end": wake_end, "inside": inside,
                      "touch": [e for e in seg if e["kind"] == "touch"],
                      "input": [e for e in seg if e["kind"] == "input"],
                      "arena": [e for e in seg if e["kind"] == "arena"]})
    return loops


def analyse(name, machine, ev=None, holds=gen43.HOLD, steps=None, path=None, frames=None):
    """a play of NAME on MACHINE against the model fed the same keys"""
    ev = events() if ev is None else ev
    nloops = frames or PLAY_FRAMES
    f0, evs, s = film(name, machine, nloops, path=path, ev=ev)
    loops = loops_of(evs)
    g = model43.Grin(stale_bug=(name == "stale"), holds=holds, steps=steps)
    rate = 0x80 if machine == EU else 0
    wk = walker(name, rate, path=path)
    rows, sent = [], []
    tail = wk.run("ran", "frame")
    for k, lp in enumerate(loops):
        wake_frame = lp["wake"]["frame"]
        sig = signal_of(wake_frame + f0, machine)
        assert sig <= lp["wake"]["t"] < sig + 40, (name, machine, k)
        # the model's loop: the interrupt, then what the RAM holds where the loop wakes
        g.loop += 1
        g.isr()
        got = ram_state(s, lp["woke"]["v"], lp["woke"]["n"], lp["woke"]["sh"])
        want = model_ram(g)
        if g.held is None:
            got["held"] = None
        assert got == want, (name, machine, k, {x: (got[x], want[x]) for x in got if got[x] != want[x]})
        if g.names is not None:
            assert list(lp["woke"]["nm"]) == g.names, (name, machine, k, "the copy of the names")
        assert got["ticks"] == wake_frame - 1, (name, machine, k, "ticks", got["ticks"], wake_frame)
        # the sends
        g.sends()
        assert list(lp["sent"]["sat"]) == g.vsat[:21], (name, machine, k, "the attributes")
        assert list(lp["sent"]["names"]) == g.vnames, (name, machine, k, "the names",
                                                       [(i, a, b) for i, (a, b) in
                                                        enumerate(zip(lp["sent"]["names"], g.vnames)) if a != b][:8])
        sent.append((lp["sent"]["t"], {"vnames": list(g.vnames), "vsat": list(g.vsat)}))
        # walk.py: from where the loop wakes to its end, on the RAM read there,
        # with the keys the model gives this loop
        keys = model43.keys_at(ev, g.ticks + model43.EVENT_AHEAD)
        wk.keys["row8"] = row8_of(keys)
        state0 = g.state
        t_walk = walk_from(wk, [(VARS[0], lp["woke"]["v"]), (NUMS[0], lp["woke"]["n"]),
                                (SHOWN[0], lp["woke"]["sh"]), (NAMES_RAM[0], lp["woke"]["nm"])], "woke", "ran")
        took = lp["ran"]["t"] - lp["woke"]["t"]
        assert not lp["inside"], (name, machine, k, "an interrupt inside")
        # the keys are read before the next frame begins, when its events come
        assert all(e["frame"] == wake_frame for e in lp["input"]), (name, machine, k, "keys late")
        assert took == t_walk, (name, machine, k, took, t_walk)
        t_sends = walk_from(wk, [(VARS[0], lp["woke"]["v"]), (NUMS[0], lp["woke"]["n"]),
                                 (SHOWN[0], lp["woke"]["sh"]), (NAMES_RAM[0], lp["woke"]["nm"])], "woke", "sent")
        assert t_sends == lp["sent"]["t"] - lp["woke"]["t"], (name, machine, k, "sends")
        # the interrupt routine
        ti = walk_from(wk, [(VARS[0], lp["wake"]["v"])], "isr", "isrend")
        assert ti == lp["wake_end"]["t"] - lp["wake"]["t"], (name, machine, k, "isr")
        # the model's logic
        g.run(keys)
        assert bool(lp["touch"]) == (g.state == model43.HIT and state0 == model43.PLAY), (name, machine, k)
        nxt = loops[k + 1]["wake"]["frame"] if k + 1 < len(loops) else None
        rows.append({"loop": k, "frame": wake_frame, "ticks": got["ticks"], "state": state0,
                     "wake": num(lp["wake"]["t"] - sig),
                     "isr": num(lp["wake_end"]["t"] - lp["wake"]["t"] + BACK),
                     "sends": num(lp["sent"]["t"] - lp["woke"]["t"]),
                     "logic": num(lp["ran"]["t"] - lp["sent"]["t"]),
                     "woke": num(lp["woke"]["t"] - sig), "sent": num(lp["sent"]["t"] - sig),
                     "halt": num(lp["ran"]["t"] + tail - sig),
                     "lost": None if nxt is None else nxt - wake_frame - 1,
                     "stat": got["stat"], "held": got["held"], "screen": g.screen,
                     "arena": num(lp["arena"][0]["t"] - sig) if lp["arena"] else None})
    return {"f0": f0, "rows": rows, "tail": tail, "ev": evs, "game": g, "sent": sent}


def summary(rows, machine):
    rows = rows[1:]                         # the first loop starts from INIT's state
    out = {"loops": len(rows), "lost": sum(r["lost"] or 0 for r in rows),
           "isr": [min(r["isr"] for r in rows), max(r["isr"] for r in rows)],
           "sent_max": max(r["sent"] for r in rows),
           "halt_max": max(r["halt"] for r in rows), "states": {}}
    for i, st in enumerate(gen43.STATES):
        rs = [r for r in rows if r["state"] == i]
        quiet = [r for r in rs if not r["screen"]]
        out["states"][st] = {"loops": len(rs),
                             "sends": [min(r["sends"] for r in rs), max(r["sends"] for r in rs)],
                             "logic": [min(r["logic"] for r in rs), max(r["logic"] for r in rs)],
                             "halt": max(r["halt"] for r in rs),
                             "quiet_halt": max(r["halt"] for r in quiet) if quiet else None,
                             "screen": [r["loop"] for r in rs if r["screen"]]}
    out["to_paper"] = num(TO_PAPER[machine])
    out["left"] = num(FT[machine] - out["halt_max"])
    return out


def touches(g, ev):
    """each touch play1 believed: the loop whose logic first put the runner's
    pixels on a face's, and the loops between"""
    g2 = model43.Grin(stale_bug=g.stale_bug)
    copies, hits = [], []
    for k in range(g.loop + 1):
        g2.loop += 1
        g2.isr()
        g2.sends()
        st0 = g2.state
        g2.run(model43.keys_at(ev, g2.ticks + model43.EVENT_AHEAD))
        copies.append(list(g2.copy))
        if st0 == model43.PLAY and g2.state == model43.HIT:
            hits.append(k)

    def c_of(copy):
        return (g2.status_of(copy + [0] * 11) >> 5) & 1
    out = []
    for h in hits:
        j = max(i for i in range(h) if not c_of(copies[i])) + 1
        out.append({"loop": h, "met": j, "lag": h - j, "runner": copies[j][0:2], "faces": copies[j][4:20],
                    "held_still": copies[h][0:2]})
    return out


def films():
    out = {}
    ev = events()
    for name in PROGRAMS:
        out[name] = {}
        for m in MACHINES:
            res = analyse(name, m)
            rows = res["rows"]
            out[name][TAG[m]] = {"rows": rows, "f0": res["f0"], "tail": res["tail"],
                                 "events": [list(e) for e in res["game"].events],
                                 "summary": summary(rows, m), "touches": touches(res["game"], ev)}
            print(name, TAG[m], out[name][TAG[m]]["summary"], flush=True)
    return out


# ---------------------------------------------------------------- the photos
def vram_of(st):
    """the VRAM a frame shows after sends that left ST"""
    g = model43.Grin.__new__(model43.Grin)
    g.vnames, g.vsat = st["vnames"], st["vsat"]
    return model43.Grin.vram(g)


def picture(st, machine):
    """the capture of a frame drawn after sends that left ST: the paper by
    vdpscreen.py, the border black all round"""
    paper = vdpscreen.draw(vram_of(st), model43.REGS)
    out = []
    for y in range(meas.CAPTURE_H):
        row = [None] * meas.CAPTURE_W
        for x in range(meas.DRAWN[0], meas.DRAWN[1] + 1):
            px, py = x - meas.PAPER_X0, y - meas.PAPER_Y0
            row[x] = paper[py][px] if 0 <= px < 256 and 0 <= py < 192 else gen43.BORDER
        out.append(row)
    return out


def mismatch(model, photo_):
    return sum(1 for y in range(meas.CAPTURE_H) for x in range(meas.DRAWN[0], meas.DRAWN[1] + 1)
               if model[y][x] != photo_[y][x])


def frame_model(res, machine, c):
    """the model of capture frame C (from INIT): the state the last sends
    before its paper left; no loop writes names while its paper is drawn"""
    f0 = res["f0"]
    start = (f0 + c) * FT[machine] + PAPER0[machine] * L
    end = start + 192 * L
    done = [st for t, st in res["sent"] if t < start]
    for r, (t, _) in zip(res["rows"], res["sent"]):
        lp_end = signal_of(r["frame"] + f0, machine) + Fraction(r["halt"]).limit_denominator(3)
        if r["screen"]:
            assert lp_end < start or t > end, (machine, c, "names written while the paper is drawn")
    return picture(done[-1], machine), done[-1]


def photo_set(name, machine, res, frames, keep=()):
    """capture FRAMES of a play, each against its model; the ones in KEEP
    stay in captures/, the others in shots/"""
    want = sorted(frames)
    models = {c: frame_model(res, machine, c) for c in want}
    shots = sorted({c + d for c in want for d in (-1, 0, 1)})
    tmp = Path(tempfile.mkdtemp(prefix="ph43_"))
    pngs = msxcap.capture(rom(name), shots, tmp, f"{name}_{TAG[machine]}_f", machine=machine,
                          events=model43.tcl_events(events()), timeout=1800)
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
    """the capture frame that shows what loop LOOP's sends sent"""
    return res["rows"][loop]["frame"] + 1


def photo_plan(res):
    """the frames the figures want, from the play"""
    g = res["game"]
    ev = g.events
    took = next(e for e in ev if e[1] == "TOOK")
    hit = next(e[0] for e in ev if e[1] == "HIT")
    over = next(e[0] for e in ev if e[1] == "OVER")
    play = next(e[0] for e in ev if e[1] == "PLAY")
    title_loop = 40
    round_loop = play + 30
    k = took[0]
    return {"title": loop_frame(res, title_loop), "round": loop_frame(res, round_loop),
            "gem": [loop_frame(res, k - 1), loop_frame(res, k), loop_frame(res, k + 1)],
            "touch": [loop_frame(res, hit - 1), loop_frame(res, hit), loop_frame(res, hit + 1)],
            "over": loop_frame(res, over + 30), "took": list(took), "hit": hit,
            "after": loop_frame(res, next(e[0] for e in ev if e[1] == "PLAY" and e[0] > hit) + 12)}


def photos():
    out = {}
    for m in MACHINES:
        res = analyse("game", m)
        plan_ = photo_plan(res)
        frames = [plan_["title"], plan_["round"], plan_["over"], plan_["after"]] + plan_["gem"] + plan_["touch"]
        keep = set(frames) if m == EU else set()
        d, shots = photo_set("game", m, res, frames, keep=keep)
        res_s = analyse("stale", m)
        again = [e[0] for e in res_s["game"].events if e[1] == "HIT"][1]     # the second HIT
        stale_frames = [loop_frame(res_s, again - 1), loop_frame(res_s, again),
                        loop_frame(res_s, again + 1), plan_["after"]]
        plan_["stale_hit"] = again
        ds, shots_s = photo_set("stale", m, res_s, stale_frames, keep=keep)
        out[TAG[m]] = {"plan": plan_, "offset": d, "frames": shots, "stale_offset": ds, "stale": shots_s}
        print("photos", TAG[m], plan_, d, ds, flush=True)
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


def playing(row8=0xFF):
    """a walker in a game just set up, the first round's gems sown, its
    sends done"""
    wk = fresh(row8=row8)
    poke(wk, "seed", [1, 0])
    wk.call("setup")
    wk.call("round")
    poke(wk, "state", [model43.PLAY])
    wk.call("sends")
    return wk


def prices():
    out = {}
    wk = playing()
    out["sends"] = wk.call("sends")                     # nothing queued, nothing changed
    names = model43.gen43.arena_names()
    # a name queued: the cell of a corridor's first column
    wk.call("pick")
    poke(wk, "copy", [gen43.HOME[1], gen43.HOME[0]])
    hl = wk.sym["names"] + 32 * 9 + 1
    wk.r["h"], wk.r["l"] = hl >> 8, hl & 255
    out["post"] = wk.call("post", a=gen43.PAPER, h=hl >> 8, l=hl & 255)
    out["sends_one_name"] = wk.call("sends")
    for k in range(4):
        wk.call("post", a=gen43.PAPER, h=hl >> 8, l=hl & 255)
    out["sends_four_names"] = wk.call("sends")
    out["queued_name"] = (out["sends_four_names"] - out["sends_one_name"]) / 3
    poke(wk, "score", [0, 0, 0x10])
    out["sends_score_pair"] = wk.call("sends")
    poke(wk, "score", [0, 0x01, 0x00])
    out["sends_score_two"] = wk.call("sends")
    poke(wk, "lives", [2])
    out["sends_lives"] = wk.call("sends")
    out["input"] = wk.call("input")
    # walk: no key; LEFT and DOWN; UP into the wall at home
    for key, row8, pos in (("walk_none", 0xFF, (71, 120)), ("walk_left_down", 0xFF & ~0x10 & ~0x40, (71, 120)),
                           ("walk_up_wall", 0xFF & ~0x20, (15, 120))):
        w2 = playing(row8)
        poke(w2, "copy", list(pos))
        w2.call("input")
        out[key] = w2.call("walk")
    out["walled_two_two"] = None
    w2 = playing()
    out["walled"] = {}
    for label, (x, y) in (("2 x 2", (120, 71)), ("3 x 2", (121, 71)), ("2 x 3", (120, 72)), ("3 x 3", (121, 72))):
        out["walled"][label] = w2.call("walled", b=x, c=y)
    del out["walled_two_two"]
    # patrol: a step, and a turn
    w2 = playing()
    ix = w2.sym["faces"]
    w2.ix = ix
    st = w2.sym["steps"]
    out["patrol"] = w2.call("patrol", h=st >> 8, l=st & 255)
    poke(w2, "faces", [gen43.LANES[0] - 1, gen43.X_MAX])
    poke(w2, "steps", [1])
    w2.ix = ix
    out["patrol_turn"] = w2.call("patrol", h=st >> 8, l=st & 255)
    w2 = playing()
    w2.call("input")
    out["step"] = w2.call("step")
    # pick: nothing under the runner; one gem
    w2 = playing()
    poke(w2, "copy", [71, 120])
    out["pick_none"] = w2.call("pick")
    poke(w2, "names", [gen43.GEM], 32 * 9 + 15)
    out["pick_gem"] = w2.call("pick")
    out["took"] = out["pick_gem"] - out["pick_none"]
    out["best"] = playing().call("best")
    # the states' routines that write the screen
    w2 = fresh()
    out["arena"] = w2.call("arena")
    out["setup"] = fresh().call("setup")
    out["title0"] = fresh().call("title0")
    w2 = playing()
    out["over0"] = w2.call("over0")
    out["isr"] = walker("game", 0).call("isr")
    return out


# ---------------------------------------------------------------- the workshop
def build_variant(name="game", **kw):
    """a variant of NAME (gen43.program's keywords), assembled in a folder
    of its own; its stem"""
    d = Path(tempfile.mkdtemp(prefix="v43_"))
    for f in ("msx.inc", "bios.inc"):
        shutil.copy(HERE / f, d / f)
    stem = name + "_" + "_".join(f"{k}" for k in sorted(kw))
    (d / f"{stem}.asm").write_text(gen43.program(name, **kw).replace(f'OUTPUT "{name}.rom"',
                                                                    f'OUTPUT "{stem}.rom"'))
    subprocess.run(["sjasmplus", "--nologo", "--msg=err", "--syntax=bFw", f"--sym={stem}.sym",
                    f"--lst={stem}.lst", f"{stem}.asm"], cwd=d, check=True)
    return d / stem


def light_loops(name, machine, path, ev=None):
    """a play of a variant with the breakpoints alone: each loop's wake frame,
    the frames its keys were read in, and its touches"""
    f0, evs, s = film(name, machine, PLAY_FRAMES, path=path, ev=ev, light=True)
    out = []
    for lp in loops_of(evs):
        v = lp["woke"]["v"]
        out.append({"frame": lp["wake"]["frame"], "input": [e["frame"] for e in lp["input"]],
                    "touch": len(lp["touch"]), "state": v[5], "lives": v[7], "gems": v[8]})
    return out


def gems_as_sprites(ev, loops):
    """for each loop of the play, the most sprites on a line of the paper if
    each gem lying were a 16 x 16 sprite too, its first line its cell's"""
    g = model43.Grin()
    worst, frames = 0, []
    for k in range(loops):
        g.loop += 1
        g.isr()
        g.sends()
        g.run(model43.keys_at(ev, g.ticks + model43.EVENT_AHEAD))
        if g.state not in (model43.PLAY, model43.HIT):
            continue
        tops = [(g.copy[4 * i] + 1) & 255 for i in range(5)]
        tops += [8 * row for row, _ in g.gem_cells()]
        per = {}
        for t in tops:
            for line in range(t, t + 16):
                if 0 <= line < 192:
                    per[line] = per.get(line, 0) + 1
        most = max(per.values())
        worst = max(worst, most)
        if most > 4:
            frames.append(k)
    return worst, frames


def answers():
    out = {}
    ev = events()
    # 1: the keys read after round
    path = build_variant("game", keys_late=True)
    q1 = {}
    for m in MACHINES:
        rows = light_loops("game", m, path)
        late = [k for k, r in enumerate(rows) if any(f != r["frame"] for f in r["input"])]
        wrong = [k for k in late if model43.keys_at(ev, rows[k]["input"][0]) != model43.keys_at(ev, rows[k]["frame"])]
        sown = [k for k in range(1, len(rows)) if rows[k]["gems"] > rows[k - 1]["gems"]]
        q1[TAG[m]] = {"late": late, "wrong": wrong, "rounds_seen": sown,
                      "touches": [k for k, r in enumerate(rows) if r["touch"]],
                      "over": [k for k in range(1, len(rows)) if rows[k]["state"] == 3 and rows[k - 1]["state"] != 3]}
    shutil.rmtree(path.parent)
    out["q1"] = q1
    # 2: C in the play
    m_ = json.loads((HERE / "meas43.json").read_text())["films"]["game"]["eu"]["rows"]
    c_loops = [r for r in m_ if r["stat"] & 0x20]
    keys, g, recs = model43.plan()
    looked = [e[0] for e in g.events if e[1] == "HIT"]
    out["q2"] = {"c_loops": len(c_loops), "by_state": {s_: sum(1 for r in c_loops if r["state"] == i)
                                                        for i, s_ in enumerate(gen43.STATES)},
                 "believed": looked, "stale": [r["loop"] for r in c_loops if r["state"] == model43.PLAY
                                               and r["loop"] not in looked]}
    # 3: C read from the port in play1
    path = build_variant("game", peek=True)
    q3 = {}
    for m in MACHINES:
        rows = light_loops("game", m, path)
        q3[TAG[m]] = {"touches": sum(r["touch"] for r in rows),
                      "states": sorted({r["state"] for r in rows})}
    shutil.rmtree(path.parent)
    out["q3"] = q3
    # 4: alley 1's face at 4 pixels a frame; 5: no margin. Planned again,
    # and the plays held against the machine
    for q, steps, margin in (("q4", [1, -4, 2, -1], model43.MARGIN), ("q5", None, 0)):
        player = model43.Player(margin=margin)
        keys, g2, recs2 = model43.plan(player=player, game=model43.Grin(steps=steps))
        ev2 = model43.events_of(keys)
        careful = [e[0] for e in g2.events if e[1] == "HIT" and e[0] < (player.reckless_from or 10 ** 6)]
        path = build_variant("game", steps_of=steps) if steps else None
        res = analyse("game", EU, ev=ev2, steps=steps, path=path, frames=len(recs2) + 2)
        assert len(res["rows"]) >= len(recs2)
        out[q] = {"careful_touches": careful, "touches": [e[0] for e in g2.events if e[1] == "HIT"],
                  "rounds": [e[0] for e in g2.events if e[1] == "ROUND"], "loops": len(recs2),
                  "reckless_from": player.reckless_from, "machine_loops": len(res["rows"])}
        if path:
            shutil.rmtree(path.parent)
    # 6: the gems as sprites
    worst, frames = gems_as_sprites(ev, len(recs))
    out["q6"] = {"most": worst, "loops_over_four": len(frames), "first": frames[:1]}
    return out


def openmsx():
    if not versions.builds():
        return {"skipped": "OPENMSX_BUILDS not set"}
    return versions.every_build(["ch43"], OPENMSX_SECTIONS)


OPENMSX_SECTIONS = ["films", "photos", "prices", "answers"]
SECTIONS = {"films": films, "photos": photos, "prices": prices, "answers": answers, "openmsx": openmsx}


def main(names=()):
    CAPS.mkdir(exist_ok=True)
    path_ = HERE / "meas43.json"
    m = json.loads(path_.read_text()) if names and path_.exists() else {}
    for name in names or SECTIONS:
        print(name, flush=True)
        m[name] = SECTIONS[name]()
        m = {k: m[k] for k in SECTIONS if k in m}
        path_.write_text(json.dumps(m, indent=1) + "\n")
    return m


if __name__ == "__main__":
    main(sys.argv[1:])
