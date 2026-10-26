#!/usr/bin/env python3
"""meas47.py -- the three sketches, measured.

    python3 gen47.py && ./build.sh && python3 meas47.py
                                  python3 meas47.py films prices   only these

  films     cave.rom, jump.rom and maze.rom for gen47.FRAMES loops on each
            machine. The debugger stops where each loop wakes, after its
            sends, at its end, at the routines that matter and in the
            interrupt routine; it reads the variables where the loop wakes,
            and the VRAM at the first; watchpoints log every byte to the
            VDP's two ports from INIT. Every loop is held against model47.py:
            the variables, and every byte to the ports, in order; its
            T-states against walk.py run on the RAM the debugger read. The
            bytes are played through vdpslots.py (chapter 20): none lost, the
            VRAM at the end the debugger's and the model's; each byte the
            sends wrote against the moment the beam first reads it; and every
            frame of the film, line by line as the bytes reached the VRAM,
            against the picture model47.py works out from the world
  photos    the figures' frames and a few more photographed, each against
            vdpscreen.py's picture of the VRAM line by line (figures 47.1 to
            47.3)
  prices    what each routine costs, from walk.py, on the paths that matter
  answers   the workshop, tried (for Appendix I)
  openmsx   all of it again with every other build (tools/versions.py)
"""
import bisect
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
import model47     # noqa: E402
gen47 = model47.gen47
sys.path.remove(str(HERE))
sys.path.insert(0, str(HERE))      # other chapters came first: this folder's files win
for mod in ("vdpscreen", "walk", "vdpslots"):
    sys.modules.pop(mod, None)
import vdpscreen   # noqa: E402
import walk        # noqa: E402
import vdpslots    # noqa: E402

assert Path(vdpscreen.__file__).parent == HERE and Path(walk.__file__).parent == HERE
assert Path(vdpslots.__file__).parent == HERE and Path(model47.vdpscreen.__file__).parent == HERE

CAPS = HERE / "captures"
SHOTS = HERE / "shots"
EU, JP = gen47.EU, gen47.JP
TAG = {EU: "eu", JP: "jp"}
L = 228
LINE = vdpslots.LINE
FT = {EU: 71364, JP: 59736}
FLAG_LINE = {EU: 261, JP: 234}
PAPER0 = {EU: 69, JP: 42}                   # the paper's first line in the VDP's frame (chapter 33)
SIGNAL = Fraction(101, 3)                   # F rises at T-state 33 2/3 of its line (chapter 19)
TO_PAPER = {EU: 121 * L - SIGNAL, JP: 70 * L - SIGNAL}
BACK = 5 + 11                               # isr's EI and RET, after isrend
POS = "[machine_info VDP_frame_count] [machine_info VDP_cycle_in_frame]"
PROGS = ["cave", "jump", "maze"]
VARS = (gen47.VARS_AT, 64)
PALETTE = [tuple(c) for c in json.loads((REPO / "ch01" / "meas01.json").read_text())["palette"]["rgb"]]
CODE = {rgb: n for n, rgb in enumerate(PALETTE) if n}
FRAMES = gen47.FRAMES

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

# where the debugger stops besides the loop's own: the routines that matter
MARKS = {"cave": {"show": "show", "steer": "steer", "window": "window", "stepped": "step.on"},
         "jump": {"trail": "trail", "walk": "walk", "fall": "fall", "place": "place"},
         "maze": {"flip": "flip", "send": "send", "view": "view", "viewed": ("step.draw", 3)}}
KINDS = ("isr", "isrend", "woke", "sent", "ran")


def rom(name):
    return HERE / f"{name}.rom"


def sym(name):
    return dbg.sym(HERE / f"{name}.sym")


def t_abs(fc, cyc):
    return int(fc), Fraction(int(cyc), 6)


def num(f):
    return int(f) if f == int(f) else round(float(f), 2)


def codes(png):
    im = Image.open(png).convert("RGB")
    px = im.load()
    return [[CODE.get(px[x, y]) for x in range(im.width)] for y in range(im.height)]


def mark_addr(s, m):
    return s[m[0]] + m[1] if isinstance(m, tuple) else s[m]


# ---------------------------------------------------------------- walk
def walker(path, rate):
    wk = walk.Walk(path)
    wk.read_port = lambda port, t: 0x80 if port == 0x99 else 0
    wk.mem[0x2B] = rate
    return wk


def walk_from(wk, mem_blocks, start, stop):
    for addr, data in mem_blocks:
        wk.mem[addr:addr + len(data)] = data
    wk.ports.clear()
    return wk.run(start, stop)


# ---------------------------------------------------------------- the films
def film(name, machine, frames, path=None):
    """the debugger's log of a film: (f0, events, sym, writes, VRAM at the end)"""
    path = path or HERE / name
    s = dbg.sym(path.with_suffix(".sym"))
    marks = MARKS[name]
    tcl = (f'debug set_bp {s["isr"]} {{}} {{ L "isr {POS}" }}\n'
           f'debug set_bp {s["isrend"]} {{}} {{ L "isrend {POS}" }}\n'
           f'debug set_bp {s["woke"]} {{}} {{ L "woke {POS}"; M v {VARS[0]} {VARS[1]}; '
           f'if {{![info exists ::vinit]}} {{ set ::vinit 1; VR vi 0 16384 }} }}\n'
           f'debug set_bp {s["sent"]} {{}} {{ L "sent {POS}" }}\n'
           f'debug set_bp {s["ran"]} {{}} {{ L "ran {POS}" }}\n' +
           "".join(f'debug set_bp {mark_addr(s, m)} {{}} {{ L "{k} {POS}" }}\n' for k, m in marks.items()) +
           VDP_WP)
    lines = msxcap.run_tcl(path.with_suffix(".rom"), frames, F0 + TOO_FAST + tcl, machine=machine,
                           tcl_setup=STATE, timeout=7200)
    w = [x.split() for x in lines]
    end_t = frames - 1
    f0 = int(next(x for x in w if x[0] == "f0")[1])
    assert not [x for x in w if x[0] == "fast"], (name, machine, "an access too soon")
    out, pend, writes = [], {}, []
    for x in w:
        k = x[0]
        if k in KINDS or k in marks:
            f, c = t_abs(x[1], x[2])
            e = {"kind": k, "frame": f - f0, "t": f * FT[machine] + c}
            out.append(e)
            pend = e
        elif k == "w":
            writes.append((int(x[3]) - f0, int(x[4]), int(x[1]), int(x[2])))
        elif len(x) == 3 and x[1] in ("mem", "vram"):
            pend[x[0]] = bytes.fromhex(x[2])
    del end_t
    return f0, out, s, writes


def end_vram(name, machine, frames, path=None):
    path = path or HERE / name
    lines = msxcap.run_tcl(path.with_suffix(".rom"), frames, "", machine=machine, tcl_setup=STATE,
                           timeout=1200, events={frames - 1: "VR end 0 16384"})
    x = next(l.split() for l in lines if l.startswith("end vram"))
    return bytes.fromhex(x[2])


def signal_of(frame, machine):
    return frame * FT[machine] + FLAG_LINE[machine] * L + SIGNAL


def loops_of(ev, marks):
    loops = []
    idx = [i for i, e in enumerate(ev) if e["kind"] == "woke"]
    for a, b in zip(idx, idx[1:] + [len(ev)]):
        seg = ev[a:b]
        kinds = [e["kind"] for e in seg]
        if "ran" not in kinds:
            continue
        j = max(i for i in range(a) if ev[i]["kind"] == "isr")
        ran = next(e for e in seg if e["kind"] == "ran")
        loops.append({"woke": ev[a], "sent": next(e for e in seg if e["kind"] == "sent"), "ran": ran,
                      "wake": ev[j], "wake_end": next(e for e in ev[j:a] if e["kind"] == "isrend"),
                      "inside": [e for e in seg if e["kind"] == "isr" and e["t"] < ran["t"]],
                      "marks": {k: [e for e in seg if e["kind"] == k and e["t"] < ran["t"]] for k in marks}})
    return loops


def ram_of(name, s, v):
    def at(label, n=1):
        a = s[label] - VARS[0]
        return v[a] if n == 1 else list(v[a:a + n])

    def w(label):
        return at(label) | v[s[label] - VARS[0] + 1] << 8
    out = {"stat": at("stat"), "ticks": w("ticks"), "held": at("held"), "dleft": at("dleft"),
           "dnext": w("dnext"), "copy": at("copy", 5)}
    if name == "cave":
        out.update(col=at("col"), shift=at("shift"), table=at("table"))
    elif name == "jump":
        out.update(rx=at("rx"), ry=at("ry"), yfrac=at("yfrac"), vy=w("vy"), landed=at("landed"))
    else:
        out.update(pos=at("pos"), face=at("face"), stage=at("stage"), wset=at("wset"), was=at("was"),
                   here=at("here"), fwd=at("fwd"), lft=at("lft"), rgt=at("rgt"))
    return out


def write_times(writes, f0, machine):
    return [(f + f0) * FT[machine] + Fraction(c, 6) for f, c, _, _ in writes]


def ports_between(writes, times, lo, hi):
    """the port writes from T-state LO up to HI: [(port, value)]"""
    a, b = bisect.bisect_left(times, lo), bisect.bisect_left(times, hi)
    return [(p, v) for _, _, p, v in writes[a:b]]


def picture_state(m):
    """what model M's picture needs, as the sends left it"""
    if m.name == "cave":
        return (m.offsets[-1], list(m.copy))
    if m.name == "jump":
        return (frozenset(m.dots), list(m.copy))
    return (m.shown_view, list(m.copy))


def analyse(name, machine, frames=FRAMES, path=None, model=None):
    """a film against the model, loop by loop"""
    f0, evs, s, writes = film(name, machine, frames, path=path)
    marks = MARKS[name]
    loops = loops_of(evs, marks)
    m = model or model47.MODELS[name](s)
    first = next(e for e in evs if e["kind"] == "woke")
    vi = first["vi"]
    assert all(vi[a:b] == bytes(m.vram[a:b]) for a, b in m.spans), (name, machine, "the VRAM at the first loop")
    wk = walker(path or HERE / name, 0x80 if machine == EU else 0)
    tail = wk.run("ran", "frame")
    times = write_times(writes, f0, machine)
    rows, states, spans = [], [], []
    compared = 0
    for k, lp in enumerate(loops):
        wake_frame = lp["wake"]["frame"]
        sig = signal_of(wake_frame + f0, machine)
        assert sig <= lp["wake"]["t"] < sig + 40, (name, machine, k)
        m.loop += 1
        m.isr()
        got, want = ram_of(name, s, lp["woke"]["v"]), m.ram()
        assert got == want, (name, machine, k, {x: (got[x], want[x]) for x in got if got[x] != want[x]})
        nxt = loops[k + 1]["woke"]["t"] if k + 1 < len(loops) else None
        m.ports = []
        m.sends()
        sent_ports = m.ports
        states.append((wake_frame + 1, picture_state(m)))
        spans.append((lp["woke"]["t"], lp["sent"]["t"]))
        m.ports = []
        m.run()
        run_ports = m.ports
        got_s = ports_between(writes, times, lp["woke"]["t"], lp["sent"]["t"])
        assert got_s == sent_ports, (name, machine, k, "the sends' bytes", len(got_s), len(sent_ports))
        compared += len(got_s)
        if nxt is not None:
            got_r = ports_between(writes, times, lp["sent"]["t"], nxt)
            assert got_r == run_ports, (name, machine, k, "the run's bytes", len(got_r), len(run_ports))
            compared += len(got_r)
        blocks = [(VARS[0], lp["woke"]["v"])]
        t_walk = walk_from(wk, blocks, "woke", "ran")
        took = lp["ran"]["t"] - lp["woke"]["t"]
        assert not lp["inside"], (name, machine, k, "an interrupt inside")
        assert took == t_walk, (name, machine, k, took, t_walk)
        t_sends = walk_from(wk, blocks, "woke", "sent")
        assert t_sends == lp["sent"]["t"] - lp["woke"]["t"], (name, machine, k, "sends")
        ti = walk_from(wk, [], "isr", "isrend")
        assert ti == lp["wake_end"]["t"] - lp["wake"]["t"], (name, machine, k, "isr")
        nf = loops[k + 1]["wake"]["frame"] if k + 1 < len(loops) else None
        rows.append({"loop": k, "frame": wake_frame,
                     "wake": num(lp["wake"]["t"] - sig),
                     "isr": num(lp["wake_end"]["t"] - lp["wake"]["t"] + BACK),
                     "woke": num(lp["woke"]["t"] - sig), "sent": num(lp["sent"]["t"] - sig),
                     "sends": num(lp["sent"]["t"] - lp["woke"]["t"]),
                     "logic": num(lp["ran"]["t"] - lp["sent"]["t"]),
                     "halt": num(lp["ran"]["t"] + tail - sig),
                     "lost": None if nf is None else nf - wake_frame - 1,
                     "marks": {kk: [num(e["t"] - sig) for e in v] for kk, v in lp["marks"].items() if v}})
        if name == "maze" and m.stage == 1:
            rows[-1]["drew"] = list(m.drawn_view)
    return {"f0": f0, "rows": rows, "tail": tail, "writes": writes, "model": m, "states": states,
            "spans": spans, "sym": s, "compared": compared}


# ---------------------------------------------------------------- the bytes to the VDP
def taken_writes(res, machine):
    """the film's bytes played through vdpslots: (data, regs, lost, vram):
    data [(cycle taken, address, value, index)], regs [(cycle, reg, value)],
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
                data.append((taken[i], addr, v, i))
            addr = (addr + 1) & 0x3FFF
    data.sort()
    return data, regs_, lost, vram


def row_start(frame, row, machine):
    flen = vdpslots.LINES[machine] * LINE
    return frame * flen + (PAPER0[machine] + 8 * row) * LINE + vdpslots.BORDER_IN


def sig_cycle(frame, machine):
    return frame * vdpslots.LINES[machine] * LINE + FLAG_LINE[machine] * LINE + vdpslots.BORDER_IN


class Rows(dict):
    def __missing__(self, k):
        return [0] * 256


def render_line(vram, regs, y):
    if not regs[1] & 0x40:
        return [vdpscreen.colour(0, regs)] * 256
    row = vdpscreen.graphic2_line(vram, regs, vdpscreen.bases(regs), y)
    rows = Rows({y: row})
    vdpscreen.sprites(vram, regs, rows)
    return row


def first_reads(vram, regs):
    """{address: the first line of the paper that reads it}: the names, the
    patterns and the colours each line draws; the sprites' attributes, and
    the patterns of the sprites on the paper, at line -1, where the VDP
    looks for the first line's sprites"""
    b = vdpscreen.bases(regs)
    p_mask = (regs[4] & 3) << 11 | 0x7FF
    c_mask = (regs[3] & 0x7F) << 6 | 0x3F
    out = {}
    for y in range(192):
        for col in range(32):
            na = b["names"] + y // 8 * 32 + col
            out.setdefault(na, y)
            index = (y // 64 * 256 + vram[na]) * 8 + y % 8
            out.setdefault(b["patterns"] | index & p_mask, y)
            out.setdefault(b["colours"] | index & c_mask, y)
    att = (regs[5] & 0x7F) * 0x80
    for a in range(att, att + 128):
        out.setdefault(a, -1)
    pat = (regs[6] & 7) * 0x800
    for a in range(pat, pat + 2048):
        out.setdefault(a, -1)
    return out


def line_pictures(data, regs_changes, machine, frames, sends_at=None):
    """for each film frame of FRAMES, the paper line by line, as the VRAM and
    the registers stand where the VDP starts drawing each line; and, for the
    writes SENDS_AT lists for a frame ({frame: [index of a write]}), each
    one's lead: T-states from its reaching the VRAM to the start of the
    first line of that frame's paper that reads its byte"""
    vram = bytearray(16384)
    regs = [0] * 8
    j = k = 0
    out, leads, cache = {}, {}, {}
    sends_at = sends_at or {}
    wanted = set(frames) | set(sends_at)
    where = {d[3]: d for d in data}
    for n in sorted(wanted):
        p0 = row_start(n, 0, machine)
        while j < len(data) and data[j][0] < p0:
            vram[data[j][1]] = data[j][2]
            j += 1
        while k < len(regs_changes) and regs_changes[k][0] < p0:
            regs[regs_changes[k][1]] = regs_changes[k][2]
            k += 1
        if n in sends_at:
            nb = (regs[2] & 15) * 0x400
            key = (bytes(vram[nb:nb + 768]), tuple(regs))
            if key not in cache:
                cache[key] = first_reads(vram, regs)
            fr = cache[key]
            for i in sends_at[n]:
                c, a, _, _ = where[i]
                if a in fr:
                    leads[i] = (Fraction(p0 + fr[a] * LINE - c, 6), a)
        if n in frames:
            rows = []
            for y in range(192):
                ls = p0 + y * LINE
                while j < len(data) and data[j][0] < ls:
                    vram[data[j][1]] = data[j][2]
                    j += 1
                while k < len(regs_changes) and regs_changes[k][0] < ls:
                    regs[regs_changes[k][1]] = regs_changes[k][2]
                    k += 1
                rows.append(render_line(vram, regs, y))
            out[n] = rows
    return out, leads


def jsonable(e):
    return [list(x) if isinstance(x, tuple) else x for x in e]


PARTS = {"cave": [("sends", "woke", "sent"), ("show", "show", "sent"), ("logic", "sent", "ran"),
                  ("window", "window", "stepped")],
         "jump": [("sends", "woke", "sent"), ("trail", "trail", "sent"), ("logic", "sent", "ran")],
         "maze": [("sends", "woke", "sent"), ("flip", "flip", "sent"), ("logic", "sent", "ran"),
                  ("send", "send", "ran"), ("view", "view", "viewed")]}


def parts(name, rows):
    """each part of the loop: where it begins after the signal, and what it
    takes, the least and the most"""
    out = {}
    for part, a, b in PARTS[name]:
        begins, takes = [], []
        for r in rows[1:]:
            at = {"woke": [r["woke"]], "sent": [r["sent"]], "ran": [r["sent"] + r["logic"]]}
            at.update(r["marks"])
            if a not in at or b not in at:
                continue
            begins.append(at[a][0])
            takes.append(round(at[b][0] - at[a][0], 2))
        out[part] = {"loops": len(begins), "begins": [min(begins), max(begins)],
                     "takes": [min(takes), max(takes)]}
    return out


def views_of(rows):
    """the views the film drew: by the first wall ahead, how many and what
    view took with its CALL"""
    out = {}
    for r in rows:
        if "drew" in r and "view" in r["marks"]:
            pos, face = r["drew"]
            d = gen47.depth(pos >> 4, pos & 15, face)
            took = round(r["marks"]["viewed"][0] - r["marks"]["view"][0] + 18, 2)
            out.setdefault(str(d), []).append(took)
    return {k: [len(v), min(v), max(v)] for k, v in sorted(out.items())}


def summary(rows, machine):
    rows = rows[1:]
    return {"loops": len(rows), "lost": sum(r["lost"] or 0 for r in rows),
            "isr": [min(r["isr"] for r in rows), max(r["isr"] for r in rows)],
            "sends": [min(r["sends"] for r in rows), max(r["sends"] for r in rows)],
            "sent_max": max(r["sent"] for r in rows),
            "logic": [min(r["logic"] for r in rows), max(r["logic"] for r in rows)],
            "halt_max": max(r["halt"] for r in rows), "to_paper": num(TO_PAPER[machine]),
            "left": num(FT[machine] - max(r["halt"] for r in rows))}


CACHE = {}
FILMS = [(p, m) for p in PROGS for m in (JP, EU)]


def ideal_check(name, machine, res, data, regs_):
    """every frame of the film, line by line, against the model's picture of
    the world -> the frames with a pixel wrong; and the lead of every byte
    the sends wrote, {index: (lead, address)}"""
    frames = {f for f, _ in res["states"]}
    sends_at = {}
    times = write_times(res["writes"], res["f0"], machine)
    ports = [p for _, _, p, _ in res["writes"]]
    for (lo, hi), r in zip(res["spans"], res["rows"]):
        a, b = bisect.bisect_left(times, lo), bisect.bisect_left(times, hi)
        sends_at[r["frame"] + 1] = [i for i in range(a, b) if ports[i] == 0x98]
    pics, leads = line_pictures(data, regs_, machine, frames, sends_at)
    m = res["model"]
    bad = {}
    for f, st in res["states"]:
        want = m.picture(*st)
        got = pics[f]
        nb = sum(1 for y in range(192) for x in range(256) if got[y][x] != want[y][x])
        if nb:
            bad[f] = nb
    return bad, leads


def lead_summary(name, leads):
    """the least lead of the sends' bytes, by what they are"""
    def kind(a):
        if 0x1B00 <= a < 0x1B80:
            return "attributes"
        if 0x1800 <= a < 0x1B00 or 0x1C00 <= a < 0x1F00:
            return "names"
        if a < 0x1800:
            return "patterns"
        return "other"
    out = {}
    for i, (ld, a) in leads.items():
        kd = kind(a)
        out[kd] = min(out.get(kd, ld), ld)
    return {k: num(v) for k, v in out.items()}


def films(which=FILMS):
    out = {}
    for name, mc in which:
        res = analyse(name, mc)
        CACHE[(name, mc)] = res
        data, regs_, lost, vram = taken_writes(res, mc)
        assert not lost, (name, mc, "bytes lost", len(lost))
        mv = res["model"].vram
        assert all(vram[a:b] == bytes(mv[a:b]) for a, b in res["model"].spans), \
            (name, mc, "the VRAM played against the model's")
        bad, leads = ideal_check(name, mc, res, data, regs_)
        assert not bad, (name, mc, "pixels against the world", sorted(bad.items())[:8])
        assert all(ld > 0 for ld, _ in leads.values()), (name, mc, "a byte behind the beam")
        rows = res["rows"]
        out.setdefault(name, {})[TAG[mc]] = {"rows": rows, "f0": res["f0"], "tail": res["tail"],
                                            "summary": summary(rows, mc), "writes": len(res["writes"]),
                                            "compared": res["compared"],
                                            "frames_checked": len(res["states"]),
                                            "leads": lead_summary(name, leads), "sent_bytes": len(leads),
                                            "parts": parts(name, rows)}
        if name == "maze":
            out[name][TAG[mc]]["views"] = views_of(rows)
        print(name, TAG[mc], out[name][TAG[mc]]["summary"], flush=True)
    return out


# ---------------------------------------------------------------- the photos
BORDERS = {"cave": gen47.CAVE_BORDER, "jump": gen47.JUMP_BORDER, "maze": gen47.MAZE_BORDER}
FIG_LOOPS = {"cave": (40, 136),     # figure 47.1: 96 frames apart
             "jump": None,          # figure 47.2: the second jump's top, and the lap done
             "maze": None}          # figure 47.3: two views
EXTRA = 2                           # frames more photographed in each film, not in a figure


def fig_loops(name):
    """the loops whose frames the figures show"""
    if name == "cave":
        return FIG_LOOPS["cave"]
    if name == "jump":
        path = gen47.JUMP_PATH
        lands = gen47.jump_landings(path)
        left = lands[0][0] + 1                   # the second jump leaves the first ledge
        top = min(range(left, lands[1][0]), key=lambda j: path[j][1])
        return (top + 1, len(path))              # a loop's frame shows the place the loop before worked out
    moves = gen47.maze_moves()
    want = [i for i, (mv, r, c, f) in enumerate(moves) if (r, c, f) == (3, 5, gen47.WEST)][0], \
        [i for i, (mv, r, c, f) in enumerate(moves) if gen47.depth(r, c, f) == 5 and mv == "F"][0]
    return tuple(gen47.IDLE + gen47.MOVE_FRAMES * i + 2 for i in want)


def full_picture(paper, border):
    out = []
    for y in range(meas.CAPTURE_H):
        row = [None] * meas.CAPTURE_W
        for x in range(meas.DRAWN[0], meas.DRAWN[1] + 1):
            px, py = x - meas.PAPER_X0, y - meas.PAPER_Y0
            row[x] = paper[py][px] if 0 <= px < 256 and 0 <= py < 192 else border
        out.append(row)
    return out


def against(photo, pic, border):
    full = full_picture(pic, border)
    return sum(1 for y in range(meas.CAPTURE_H) for x in range(meas.DRAWN[0], meas.DRAWN[1] + 1)
               if photo[y][x] != full[y][x])


def photo_set(name, machine, res, frames, keep=()):
    """FRAMES of a film photographed and held against the line by line
    model; the one offset that fits"""
    data, regs_, lost, _ = taken_writes(res, machine)
    want = sorted(frames)
    models, _ = line_pictures(data, regs_, machine, set(want))
    shots = sorted({c + d for c in want for d in (-1, 0, 1)})
    tmp = Path(tempfile.mkdtemp(prefix="ph47_"))
    pngs = msxcap.capture(rom(name), shots, tmp, f"{name}_{TAG[machine]}_f", machine=machine, timeout=3600)
    ph = {c: codes(pngs[c]) for c in shots}
    b = BORDERS[name]
    fits = [d for d in (-1, 0, 1) if all(against(ph[c + d], models[c], b) == 0 for c in want)]
    assert fits, (name, machine, [(c, d, against(ph[c + d], models[c], b)) for c in want for d in (-1, 0, 1)])
    d = 0 if 0 in fits else fits[0]
    out = {}
    for c in want:
        dest = (CAPS if c in keep else SHOTS) / pngs[c + d].name.replace(f"_f{c + d:04d}", f"_f{c:04d}")
        dest.parent.mkdir(exist_ok=True)
        shutil.copy(pngs[c + d], dest)
        out[c] = dest.name
    shutil.rmtree(tmp)
    return fits, out


def photos(cache=CACHE):
    out = {}
    for name, mc in FILMS:
        res = cache.get((name, mc)) or analyse(name, mc)
        cache[(name, mc)] = res
        rows = res["rows"]
        loops = fig_loops(name)
        figs = [rows[k]["frame"] + 1 for k in loops]
        n = len(rows)
        extra = [rows[n // 3]["frame"] + 1, rows[2 * n // 3]["frame"] + 1]
        keep = set(figs) if mc == JP else set()
        fits, shots = photo_set(name, mc, res, set(figs) | set(extra), keep=keep)
        out.setdefault(name, {})[TAG[mc]] = {"offsets": fits, "frames": {str(k): v for k, v in shots.items()},
                                            "figs": figs, "loops": list(loops)}
        print("photos", name, TAG[mc], fits, figs, flush=True)
    return out


# ---------------------------------------------------------------- the prices
def fresh(name, machine=JP):
    return walker(HERE / name, 0x80 if machine == EU else 0)


def poke(wk, label, vals, off=0):
    a = wk.sym[label] + off
    for i, v in enumerate(vals if isinstance(vals, list) else [vals]):
        wk.mem[a + i] = v & 255


def model_ram_into(wk, m):
    """the model's variables into walk's memory"""
    r = m.ram()
    s = wk.sym
    poke(wk, "ticks", [r["ticks"] & 255, r["ticks"] >> 8])
    poke(wk, "held", r["held"])
    poke(wk, "dleft", r["dleft"])
    poke(wk, "dnext", [r["dnext"] & 255, r["dnext"] >> 8])
    poke(wk, "copy", r["copy"])
    for k, v in r.items():
        if k in ("stat", "ticks", "held", "dleft", "dnext", "copy"):
            continue
        if k == "vy":
            poke(wk, k, [v & 255, v >> 8])
        else:
            poke(wk, k, v)
    del s


def prices():
    out = {}
    g = gen47
    # ---- pad
    wk = fresh("cave")
    poke(wk, "dleft", 5)
    same = wk.call("pad")
    poke(wk, "dleft", 1)
    poke(wk, "dnext", [wk.sym["demo"] & 255, wk.sym["demo"] >> 8])
    pair = wk.call("pad")
    end = wk.sym["demo"] + 2 * len(g.CAVE_DEMO)
    poke(wk, "dleft", 1)
    poke(wk, "dnext", [end & 255, end >> 8])
    again = wk.call("pad")
    out["pad"] = {"same": same, "pair": pair, "again": again}
    # ---- cave
    wk = fresh("cave")
    poke(wk, "copy", [79, 80, 0, 15, 0xD0])
    poke(wk, "table", 0x18)
    st = {}
    for keys, lab in ((0, "none"), (g.UP, "one"), (g.UP | g.RIGHT, "two")):
        poke(wk, "copy", [79, 80])
        st[lab] = wk.call("steer", a=g.held_of(keys))
    poke(wk, "copy", [g.SHIP_Y[0] - 1, g.SHIP_X[0]])
    st["edge"] = wk.call("steer", a=g.held_of(g.UP | g.LEFT))
    out["steer"] = st
    sends = {}
    for sh in (1, 0):
        poke(wk, "shift", sh)
        poke(wk, "table", 0x18)
        sends[f"shift {sh}"] = wk.call("sends")
    out["cave_sends"] = sends
    poke(wk, "table", 0x18)
    out["window"] = wk.call("window", a=5)
    out["window_names"] = 32 * len(g.SCROLL_ROWS)
    stp = {}
    for sh, lab in ((3, "a pixel"), (7, "a column"), (0, "a window")):
        poke(wk, "shift", sh)
        poke(wk, "col", 5)
        poke(wk, "table", 0x18)
        stp[lab] = wk.call("step")
    out["step"] = stp
    # the price of show, from its lines (the Count the T-states)
    out["show_bytes"] = 8 * g.NP
    # ---- jump
    wk = fresh("jump")
    m = model47.Jump(wk.sym)
    model_ram_into(wk, m)
    out["jump_sends"] = wk.call("sends")
    wl = {}
    for keys, lab, x in ((0, "none", 100), (g.LEFT, "left", 100), (g.RIGHT, "right", 100),
                         (g.LEFT, "at the edge", 0)):
        poke(wk, "rx", x)
        wl[lab] = wk.call("walk", a=g.held_of(keys))
    out["walk"] = wl
    # fall's paths, from the lap: the model's state before each, walked
    fl = {}
    r = g.Runner()
    for j, k in enumerate(g.JUMP_KEYS):
        before = (r.x, r.y, r.vy, r.ground)
        r.step(k)
        kind = ("on a ledge" if before[3] and r.ground else
                "a jump" if before[3] and k & g.FIRE else
                "off a ledge's end" if before[3] else
                "rising" if before[2] >= 0x8000 and not r.ground else
                "a landing" if r.ground else "falling")
        poke(wk, "rx", r.x)
        poke(wk, "ry", before[1] >> 8)
        poke(wk, "yfrac", before[1] & 255)
        poke(wk, "vy", [before[2] & 255, before[2] >> 8])
        poke(wk, "landed", int(before[3]))
        t = wk.call("fall", a=g.held_of(k))
        assert (wk.mem[wk.sym["ry"]], wk.mem[wk.sym["yfrac"]]) == (r.y >> 8, r.y & 255), (j, k)
        lo, hi = fl.get(kind, (t, t))
        fl[kind] = (min(lo, t), max(hi, t))
    out["fall"] = {k: list(v) for k, v in fl.items()}
    und = {}
    for x, lab in ((16, "two cells"), (20, "three cells")):
        poke(wk, "rx", x)
        und[lab] = wk.call("under", c=8 * 20)
    poke(wk, "rx", 16)
    und["a ledge at once"] = wk.call("under", c=8 * 23)
    out["under"] = und
    poke(wk, "rx", 16)
    poke(wk, "ry", 168)
    out["trail"] = wk.call("trail")
    # ---- maze
    wk = fresh("maze")
    m = model47.Maze(wk.sym)
    model_ram_into(wk, m)
    out["maze_sends"] = wk.call("sends")
    poke(wk, "stage", 2)
    out["maze_sends_flip"] = wk.call("sends")
    poke(wk, "stage", 1)
    poke(wk, "wset", 0)
    out["send"] = wk.call("send")
    out["blank"] = wk.call("blank")
    views = {}
    for r_ in range(16):
        for c_ in range(16):
            if g.MAZE[r_][c_]:
                continue
            for f in range(4):
                poke(wk, "pos", 16 * r_ + c_)
                poke(wk, "face", f)
                t = wk.call("view")
                dd = g.depth(r_, c_, f)
                lo, hi = views.get(dd, (t, t))
                views[dd] = (min(lo, t), max(hi, t))
    out["view_all"] = {str(k): list(v) for k, v in sorted(views.items())}
    out["mark"] = wk.call("mark")
    return out


# ---------------------------------------------------------------- the workshop
def build_variant(kind):
    name, src = gen47.variant(kind)
    d = Path(tempfile.mkdtemp(prefix=f"var47_{kind}_"))
    for f in ("msx.inc", "bios.inc"):
        shutil.copy(HERE / f, d)
    (d / f"{name}.asm").write_text(src)
    subprocess.run(["sjasmplus", "--nologo", "--msg=err", "--syntax=bFw", f"--sym={name}.sym",
                    f"--lst={name}.lst", f"{name}.asm"], cwd=d, check=True)
    return name, d / name


def light(name, machine, path, frames=FRAMES):
    """a variant's film: its loops, writes and variables, no model"""
    f0, evs, s, writes = film(name, machine, frames, path=path)
    loops = loops_of(evs, MARKS[name])
    return {"f0": f0, "loops": loops, "writes": writes, "sym": s,
            "frames": [lp["wake"]["frame"] for lp in loops]}


def against_world(name, machine, lt, states):
    """a variant's frames, line by line, against the model's pictures of the
    world, STATES a loop each; and its sends' leads"""
    res = {"writes": lt["writes"], "f0": lt["f0"]}
    data, regs_, lost, _ = taken_writes(res, machine)
    assert not lost
    times = write_times(lt["writes"], lt["f0"], machine)
    ports = [p for _, _, p, _ in lt["writes"]]
    sends_at = {}
    for lp in lt["loops"]:
        a, b = bisect.bisect_left(times, lp["woke"]["t"]), bisect.bisect_left(times, lp["sent"]["t"])
        sends_at[lp["wake"]["frame"] + 1] = [i for i in range(a, b) if ports[i] == 0x98]
    frames = {lp["wake"]["frame"] + 1 for lp in lt["loops"]}
    pics, leads = line_pictures(data, regs_, machine, frames, sends_at)
    m = model47.MODELS[name](lt["sym"])
    bad = 0
    for lp, st in zip(lt["loops"], states):
        want = m.picture(*st)
        got = pics[lp["wake"]["frame"] + 1]
        bad += any(got[y] != want[y] for y in range(192))
    return bad, leads


def model_states(name, sym_, n):
    m = model47.MODELS[name](sym_)
    out = []
    for _ in range(n):
        m.loop += 1
        m.isr()
        m.ports = []
        m.sends()
        out.append(picture_state(m))
        m.run()
    return out


def runner_path(lt):
    """the runner's place at each loop's wake, from the RAM: (frame, x, y)"""
    s = lt["sym"]
    return [(lp["wake"]["frame"], lp["woke"]["v"][s["rx"] - VARS[0]], lp["woke"]["v"][s["ry"] - VARS[0]])
            for lp in lt["loops"]]


def answers():
    out = {}
    g = gen47
    films_ = json.loads((HERE / "meas47.json").read_text())["films"]
    # 1. one name table: the new window's names straight after show, with OTIR
    q1 = {}
    name, path = build_variant("one")
    for mc in (JP, EU):
        lt = light(name, mc, path)
        sends = [lp for lp in lt["loops"] if lp["sent"]["t"] - lp["woke"]["t"] > 6000]
        sig = [signal_of(lp["wake"]["frame"] + lt["f0"], mc) for lp in sends]
        states = model_states(name, lt["sym"], len(lt["loops"]))
        bad, leads = against_world(name, mc, lt, states)
        lost = sum(b - a - 1 for a, b in zip(lt["frames"], lt["frames"][1:]))
        q1[TAG[mc]] = {"loops": len(lt["loops"]), "lost": lost, "frames_wrong": bad,
                       "sends_long": [num(min(lp["sent"]["t"] - lp["woke"]["t"] for lp in sends)),
                                      num(max(lp["sent"]["t"] - lp["woke"]["t"] for lp in sends))],
                       "ends": num(max(lp["sent"]["t"] - sg for lp, sg in zip(sends, sig))),
                       "least_lead": num(min(ld for ld, _ in leads.values())),
                       "behind": sum(1 for ld, _ in leads.values() if ld <= 0)}
    out["q1"] = q1
    # 2. how many pairs show could send before the beam reads line 8
    q2 = {}
    for mc in (JP, EU):
        lt = light("cave", mc, HERE / "cave", frames=24)
        lp = lt["loops"][5]
        sg = signal_of(lp["wake"]["frame"] + lt["f0"], mc)
        times = write_times(lt["writes"], lt["f0"], mc)
        data = [times[i] for i in range(len(times))
                if lp["woke"]["t"] <= times[i] < lp["sent"]["t"] and lt["writes"][i][2] == 0x98]
        assert len(data) == 5 + 8 * g.NP
        t_first, t_last = data[5] - sg, data[-1] - sg
        line8 = TO_PAPER[mc] + 8 * L
        n = int((line8 - t_first) // 23) + 1
        q2[TAG[mc]] = {"first_byte": num(t_first), "last_byte": num(t_last), "line8": num(line8),
                       "bytes": n, "pairs": n // 8}
    out["q2"] = q2
    # 3 and 4: the runner's variants, held against Runner with the same change
    for q, kind in (("q3", "gravity"), ("q4", "keep")):
        name, path = build_variant(kind)
        lt = light(name, JP, path, frames=160)
        got = runner_path(lt)
        romb = path.with_suffix(".rom").read_bytes()
        base = lt["sym"]["ledges"]

        def cell(r_, c_):
            """what under reads for row R_, column C_: the map, or past its
            end the cartridge's bytes after it"""
            return romb[base + ((32 * r_) & 0x3FF) + c_ - 0x4000]
        r = g.Runner()
        if kind == "gravity":
            grav = g.GRAVITY // 2
        want, keep = [], kind == "keep"
        x, y, vy, ground = r.x, r.y, r.vy, r.ground
        for j, (frame, gx, gy) in enumerate(got):
            want.append((frame, x, y >> 8))
            k = g.JUMP_KEYS[j % len(g.JUMP_KEYS)]
            if k & g.LEFT and x > 0:
                x -= g.RUN
            if k & g.RIGHT and x < g.X_LAST:
                x += g.RUN
            v = vy
            if k & g.FIRE and ground:
                v = -g.JUMP & 0xFFFF
            v = (v + (grav if kind == "gravity" else g.GRAVITY)) & 0xFFFF
            if v < 0x8000 and v >> 8 >= g.MAXFALL >> 8:
                v = g.MAXFALL
            ny = (y + v) & 0xFFFF
            landed = False
            if v < 0x8000:
                old, new = ((y >> 8) + 16) & 255, ((ny >> 8) + 16) & 255
                t = new & 0xF8
                if old <= t and any(cell(t // 8, c) for c in range(x // 8, (x + 15) // 8 + 1)):
                    y, vy, ground, landed = (ny if keep else (t - 16) << 8), 0, True, True
            if not landed:
                y, vy, ground = ny, v, False
        assert got == want, (q, [(a, b) for a, b in zip(got, want) if a != b][:5])
        f1 = [(f, x_, y_) for f, x_, y_ in got]
        out[q] = {"path": f1}
        if kind == "gravity":
            s_ = lt["sym"]
            landed = [lp["woke"]["v"][s_["landed"] - VARS[0]] for lp in lt["loops"]]
            up = landed.index(0)
            down = landed.index(1, up)
            top = min(range(up, down), key=lambda i: (f1[i][2], i))
            out[q].update(leaves=f1[up - 1], top=f1[top], lands=f1[down], row=(f1[down][2] + 16) // 8,
                          rise=f1[up - 1][2] - f1[top][2])
        else:
            deep = next(t for t in f1 if t[2] > 168)
            under = next(t for t in f1 if t[2] >= 176)
            out[q].update(sinks=deep, beneath=under, lowest=max(f1, key=lambda t: t[2]))
        print(q, "the runner as Runner says", flush=True)
    # 5. a view sent in the frame that draws it
    q5 = {}
    name, path = build_variant("now")
    for mc in (JP, EU):
        lt = light(name, mc, path)
        lost = sum(b - a - 1 for a, b in zip(lt["frames"], lt["frames"][1:]))
        longest = max(lp["ran"]["t"] - signal_of(lp["wake"]["frame"] + lt["f0"], mc) for lp in lt["loops"])
        inside = sum(1 for lp in lt["loops"] if lp["inside"])
        q5[TAG[mc]] = {"loops": len(lt["loops"]), "lost": lost, "longest": num(longest), "inside": inside}
    out["q5"] = q5
    # 6. blank with LDIR
    name, path = build_variant("ldir")
    wk = walk.Walk(path)
    wk.read_port = lambda port, t: 0
    q6 = {"blank": wk.call("blank")}
    views = {}
    for r_ in range(16):
        for c_ in range(16):
            if g.MAZE[r_][c_]:
                continue
            for f in range(4):
                poke(wk, "pos", 16 * r_ + c_)
                poke(wk, "face", f)
                t = wk.call("view")
                dd = g.depth(r_, c_, f)
                lo, hi = views.get(dd, (t, t))
                views[dd] = (min(lo, t), max(hi, t))
    q6["views"] = {str(k): list(v) for k, v in sorted(views.items())}
    out["q6"] = q6
    return out


def openmsx():
    if not versions.builds():
        return {"skipped": "OPENMSX_BUILDS not set"}
    return versions.every_build(["ch47"], OPENMSX_SECTIONS)


OPENMSX_SECTIONS = ["films", "photos", "prices", "answers"]
SECTIONS = {"films": films, "photos": photos, "prices": prices, "answers": answers, "openmsx": openmsx}



def main(names=()):
    path = HERE / "meas47.json"
    old = json.loads(path.read_text()) if path.exists() else {}
    for n in (names or SECTIONS):
        old[n] = SECTIONS[n]()
        path.write_text(json.dumps(old, indent=1, sort_keys=True))


if __name__ == "__main__":
    main(sys.argv[1:])
