#!/usr/bin/env python3
"""meas48.py -- the long cave and the mappers, measured.

    python3 gen48.py && ./build.sh && python3 meas48.py
                                  python3 meas48.py films prices   only these

  films     long.rom, far.rom and guess.rom for gen48.FRAMES loops on each
            machine, with no -romtype: openMSX picks the mapper itself. The
            debugger stops where each loop wakes, after its sends, at its
            end, at the routines that matter and in the interrupt routine;
            it reads the variables where the loop wakes, the block each
            window of pages 1 and 2 shows, and the VRAM at the first;
            watchpoints log every byte to the VDP's two ports from INIT.
            Every loop is held against model48.py: the variables, the
            mapper, and every byte to the ports, in order; its T-states
            against walk.py run on the RAM and the banks the debugger read.
            The bytes are played through vdpslots.py (chapter 20): none
            lost, the VRAM at the end the model's; each byte the sends wrote
            against the moment the beam first reads it; and every frame of
            the film, line by line as the bytes reached the VRAM, against
            the picture model48.py works out from the world: the one the
            cartridge means, and for guess.rom the one the mapper serves;
            far.rom's frames that are neither, against the model's VRAM
  mappers   banks.rom run with no -romtype and with -romtype ascii16,
            ascii8, konami and konamiscc: the block each 8 KB window shows
            after each write, against a Python mapper of each type; the
            writes the BIOS makes into the cartridge's slot before INIT; the
            type openMSX gives each cartridge of this chapter, and cartridges
            of LD (nn),A instructions only, each against a count of them
  photos    the figures' frames and a few more photographed, each against
            the line by line picture of the film's bytes (figures 48.1 to
            48.3)
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
import model48     # noqa: E402
gen48 = model48.gen48
gen47 = gen48.gen47
sys.path.remove(str(HERE))
sys.path.insert(0, str(HERE))      # other chapters came first: this folder's files win
for mod in ("vdpscreen", "walk", "vdpslots"):
    sys.modules.pop(mod, None)
import vdpscreen   # noqa: E402
import walk        # noqa: E402
import vdpslots    # noqa: E402

assert Path(vdpscreen.__file__).parent == HERE and Path(walk.__file__).parent == HERE
assert Path(vdpslots.__file__).parent == HERE and Path(model48.vdpscreen.__file__).parent == HERE

CAPS = HERE / "captures"
SHOTS = HERE / "shots"
EU, JP = gen48.EU, gen48.JP
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
PROGS = ["long", "far", "guess"]
VARS = (gen47.VARS_AT, 64)
PALETTE = [tuple(c) for c in json.loads((REPO / "ch01" / "meas01.json").read_text())["palette"]["rgb"]]
CODE = {rgb: n for n, rgb in enumerate(PALETTE) if n}
FRAMES = gen48.FRAMES
MAPPER = {"long": "ascii16", "far": "ascii16", "guess": "konamiscc"}
WINDOWS = (0x4000, 0x6000, 0x8000, 0xA000)

STATE = r"""
proc M {tag addr n} {
    binary scan [debug read_block memory $addr $n] H* h
    L "$tag mem $h"
}
proc VR {tag addr n} {
    binary scan [debug read_block VRAM $addr $n] H* h
    L "$tag vram $h"
}
proc BLK {rom} {
    set s "blk"
    foreach a {0x4000 0x6000 0x8000 0xA000} { append s " [debug read [list $rom romblocks] $a]" }
    L $s
}
proc TYPE {rom} { L "type [dict get [machine_info device $rom] mappertype]" }
"""
TOO_FAST = ('proc ::toofast_cb {args} { L "fast [machine_info VDP_frame_count] '
            '[machine_info VDP_cycle_in_frame]" }\n'
            'set VDP.too_fast_vram_access_callback ::toofast_cb\n')
F0 = 'L "f0 [machine_info VDP_frame_count]"\n'
VDP_WP = ('debug set_watchpoint write_io {0x98 0x99} {} '
          '{ L "w [expr {$::wp_last_address & 255}] $::wp_last_value ' + POS + '" }\n')

# where the debugger stops besides the loop's own: the routines that matter
MARKS = {"window": "window", "stepped": "step.on", "bshow": "BSHOW", "steer": "steer"}
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


def blocks8(kind, rb):
    """the debugger's romblocks at the four windows -> the 8 KB block of each"""
    if kind == "ascii16":
        return [2 * rb[0], 2 * rb[1] + 1, 2 * rb[2], 2 * rb[3] + 1]
    return list(rb)


# ---------------------------------------------------------------- walk
def walker(path, rate, mapper):
    wk = walk.Walk(path, mapper=mapper)
    wk.read_port = lambda port, t: 0x80 if port == 0x99 else 0
    wk.mem[0x2B] = rate
    return wk


def walk_from(wk, mem_blocks, start, stop, blocks=None):
    for addr, data in mem_blocks:
        wk.mem[addr:addr + len(data)] = data
    if blocks is not None:
        wk.set_blocks(blocks)
    wk.ports.clear()
    return wk.run(start, stop)


# ---------------------------------------------------------------- the films
def film(name, machine, frames, path=None, extra=()):
    """the debugger's log of a film: (f0, events, sym, writes, mapper type)"""
    path = path or HERE / name
    s = dbg.sym(path.with_suffix(".sym"))
    rname = path.with_suffix(".rom").name
    tcl = (f'TYPE {rname}\n'
           f'debug set_bp {s["isr"]} {{}} {{ L "isr {POS}" }}\n'
           f'debug set_bp {s["isrend"]} {{}} {{ L "isrend {POS}" }}\n'
           f'debug set_bp {s["woke"]} {{}} {{ L "woke {POS}"; M v {VARS[0]} {VARS[1]}; BLK {rname}; '
           f'if {{![info exists ::vinit]}} {{ set ::vinit 1; VR vi 0 16384 }} }}\n'
           f'debug set_bp {s["sent"]} {{}} {{ L "sent {POS}" }}\n'
           f'debug set_bp {s["ran"]} {{}} {{ L "ran {POS}" }}\n' +
           "".join(f'debug set_bp {s[m]} {{}} {{ L "{k} {POS}" }}\n' for k, m in MARKS.items()) +
           VDP_WP)
    lines = msxcap.run_tcl(path.with_suffix(".rom"), frames, F0 + TOO_FAST + tcl, machine=machine,
                           tcl_setup=STATE, timeout=7200, extra_args=extra)
    w = [x.split() for x in lines]
    f0 = int(next(x for x in w if x[0] == "f0")[1])
    mtype = next(x[1] for x in w if x[0] == "type")
    assert not [x for x in w if x[0] == "fast"], (name, machine, "an access too soon")
    out, pend, writes = [], {}, []
    for x in w:
        k = x[0]
        if k in KINDS or k in MARKS:
            f, c = t_abs(x[1], x[2])
            e = {"kind": k, "frame": f - f0, "t": f * FT[machine] + c}
            out.append(e)
            pend = e
        elif k == "w":
            writes.append((int(x[3]) - f0, int(x[4]), int(x[1]), int(x[2])))
        elif k == "blk":
            pend["blk"] = [int(v) for v in x[1:]]
        elif len(x) == 3 and x[1] in ("mem", "vram"):
            pend[x[0]] = bytes.fromhex(x[2])
    return f0, out, s, writes, mtype


def signal_of(frame, machine):
    return frame * FT[machine] + FLAG_LINE[machine] * L + SIGNAL


def loops_of(ev):
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
                      "marks": {k: [e for e in seg if e["kind"] == k and e["t"] < ran["t"]] for k in MARKS}})
    return loops


def ram_of(s, v, blk):
    def at(label, n=1):
        a = s[label] - VARS[0]
        return v[a] if n == 1 else list(v[a:a + n])

    def w(label):
        return at(label) | v[s[label] - VARS[0] + 1] << 8
    out = {"stat": at("stat"), "ticks": w("ticks"), "held": at("held"), "dleft": at("dleft"),
           "dnext": w("dnext"), "copy": at("copy", 5), "blocks": list(blk)}
    for k in ("shift", "table", "wbank", "wseg", "woff", "pending", "shown", "fresh"):
        out[k] = at(k)
    return out


def write_times(writes, f0, machine):
    return [(f + f0) * FT[machine] + Fraction(c, 6) for f, c, _, _ in writes]


def ports_between(writes, times, lo, hi):
    """the port writes from T-state LO up to HI: [(port, value)]"""
    a, b = bisect.bisect_left(times, lo), bisect.bisect_left(times, hi)
    return [(p, v) for _, _, p, v in writes[a:b]]


def analyse(name, machine, frames=FRAMES, path=None, model=None, extra=(), kind=None):
    """a film against the model, loop by loop"""
    f0, evs, s, writes, mtype = film(name, machine, frames, path=path, extra=extra)
    loops = loops_of(evs)
    m = model or model48.MODELS[name](s)
    mk = kind or MAPPER.get(name, "ascii16")
    first = next(e for e in evs if e["kind"] == "woke")
    vi = first["vi"]
    assert all(vi[a:b] == bytes(m.vram[a:b]) for a, b in m.spans), (name, machine, "the VRAM at the first loop")
    wk = walker(path or HERE / name, 0x80 if machine == EU else 0, mk)
    tail = wk.run("ran", "frame")
    times = write_times(writes, f0, machine)
    rows, spans = [], []
    compared = 0
    for k, lp in enumerate(loops):
        wake_frame = lp["wake"]["frame"]
        sig = signal_of(wake_frame + f0, machine)
        assert sig <= lp["wake"]["t"] < sig + 40, (name, machine, k)
        m.loop += 1
        m.isr()
        got, want = ram_of(s, lp["woke"]["v"], lp["woke"]["blk"]), m.ram()
        assert got == want, (name, machine, k, {x: (got[x], want[x]) for x in got if got[x] != want[x]})
        nxt = loops[k + 1]["woke"]["t"] if k + 1 < len(loops) else None
        m.ports = []
        m.sends()
        sent_ports = m.ports
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
        blk = blocks8(mk, lp["woke"]["blk"])
        mem = [(VARS[0], lp["woke"]["v"])]
        t_walk = walk_from(wk, mem, "woke", "ran", blk)
        took = lp["ran"]["t"] - lp["woke"]["t"]
        assert not lp["inside"], (name, machine, k, "an interrupt inside")
        assert took == t_walk, (name, machine, k, took, t_walk)
        t_sends = walk_from(wk, mem, "woke", "sent", blk)
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
    states = [(r["frame"] + 1, st) for r, st in zip(rows, m.states)]
    return {"f0": f0, "rows": rows, "tail": tail, "writes": writes, "model": m, "states": states,
            "spans": spans, "sym": s, "compared": compared, "type": mtype}


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


PARTS = [("sends", "woke", "sent"), ("bshow", "bshow", "sent"), ("logic", "sent", "ran"),
         ("window", "window", "stepped")]


def parts(rows):
    """each part of the loop: where it begins after the signal, and what it
    takes, the least and the most"""
    out = {}
    for part, a, b in PARTS:
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


def picture_check(res, data, regs_, machine):
    """every frame of the film, line by line, against the model's pictures ->
    {"meant": frames wrong against the picture the cartridge means,
     "served": frames wrong against the picture of the bytes the mapper
     served, "vram": frames wrong against the model's VRAM, for those whose
     pairs were another bank's}; and the lead of every byte the sends wrote"""
    frames = {f for f, _ in res["states"]}
    sends_at = {}
    times = write_times(res["writes"], res["f0"], machine)
    ports = [p for _, _, p, _ in res["writes"]]
    for (lo, hi), r in zip(res["spans"], res["rows"]):
        a, b = bisect.bisect_left(times, lo), bisect.bisect_left(times, hi)
        sends_at[r["frame"] + 1] = [i for i in range(a, b) if ports[i] == 0x98]
    pics, leads = line_pictures(data, regs_, machine, frames, sends_at)
    m = res["model"]
    meant, served, vram_bad, by_vram = {}, {}, {}, []
    for k, (f, st) in enumerate(res["states"]):
        got = pics[f]
        want = m.picture(*st)
        nb = sum(1 for y in range(192) for x in range(256) if got[y][x] != want[y][x])
        if nb:
            meant[f] = nb
        sp = m.served_picture(*st)
        if sp is not None:
            ns = sum(1 for y in range(192) for x in range(256) if got[y][x] != sp[y][x])
            if ns:
                served[f] = ns
        elif k in m.snaps:
            v, rg = m.snaps[k]
            by_vram.append(f)
            nv = sum(1 for y in range(192) if render_line(v, rg, y) != got[y])
            if nv:
                vram_bad[f] = nv
        else:
            raise AssertionError(("a frame with no picture to hold it against", f))
    return {"meant": meant, "served": served, "vram": vram_bad, "by_vram": by_vram}, leads


def lead_summary(leads):
    """the least lead of the sends' bytes, by what they are"""
    def kind(a):
        if 0x1B00 <= a < 0x1B80:
            return "attributes"
        if 0x2000 <= a < 0x3800:
            return "colours"
        if a < 0x1800:
            return "patterns"
        return "other"
    out = {}
    for i, (ld, a) in leads.items():
        kd = kind(a)
        out[kd] = min(out.get(kd, ld), ld)
    return {k: num(v) for k, v in out.items()}


def runs_of(frames):
    """[first, last] of each run of consecutive frames"""
    out = []
    for f in sorted(frames):
        if out and f == out[-1][1] + 1:
            out[-1][1] = f
        else:
            out.append([f, f])
    return out


def bank_turns(res):
    """the frames where the bank whose world is shown changes: (frame, from, to)"""
    out, last = [], None
    for f, st in res["states"]:
        b = st[0][1]
        if last is not None and b != last:
            out.append([f, last, b])
        last = b
    return out


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
        bad, leads = picture_check(res, data, regs_, mc)
        assert not bad["served"] and not bad["vram"], (name, mc, bad["served"], bad["vram"])
        if name == "long":
            assert not bad["meant"], (name, mc, sorted(bad["meant"].items())[:8])
        assert all(ld > 0 for ld, _ in leads.values()), (name, mc, "a byte behind the beam")
        rows = res["rows"]
        out.setdefault(name, {})[TAG[mc]] = {
            "rows": rows, "f0": res["f0"], "tail": res["tail"], "type": res["type"],
            "summary": summary(rows, mc), "writes": len(res["writes"]), "compared": res["compared"],
            "frames_checked": len(res["states"]), "leads": lead_summary(leads), "sent_bytes": len(leads),
            "parts": parts(rows), "turns": bank_turns(res),
            "wrong": {"runs": runs_of(bad["meant"]), "frames": len(bad["meant"]),
                      "pixels": [min(bad["meant"].values()), max(bad["meant"].values())] if bad["meant"] else [],
                      "by_vram": len(bad["by_vram"]),
                      "served_checked": sum(1 for _, st in res["states"]
                                            if res["model"].served_picture(*st) is not None)}}
        print(name, TAG[mc], res["type"], out[name][TAG[mc]]["summary"], out[name][TAG[mc]]["wrong"]["runs"],
              flush=True)
    return out


# ---------------------------------------------------------------- the mappers
ROMTYPES = [None, "ascii16", "ascii8", "konami", "konamiscc"]
TYPE_NAMES = {"ascii16": "ASCII16", "ascii8": "ASCII8", "konami": "Konami", "konamiscc": "KonamiSCC",
              "8kb": "8kB"}


NONE = 0xFF                 # a window that shows no block reads $FF


class PyMapper:
    """a mapper as this chapter describes it: the 8 KB block of each window
    from $4000, at the start and after a write"""
    START = {"ascii16": [0, 1, 0, 1], "ascii8": [0, 0, 0, 0], "konami": [0, 1, 2, 3],
             "konamiscc": [0, 1, 2, 3], "8kb": [0, 1, 2, 3]}

    def __init__(self, kind, count=16):
        self.kind, self.count = kind, count
        self.blocks = list(self.START[kind])

    def write(self, a, v):
        k = self.kind
        if k == "ascii16":
            for w, lo in ((0, 0x6000), (2, 0x7000)):
                if lo <= a < lo + 0x800:
                    b = v % (self.count // 2)
                    self.blocks[w:w + 2] = [2 * b, 2 * b + 1]
            return
        regs = {"ascii8": [(0x6000, 0x800), (0x6800, 0x800), (0x7000, 0x800), (0x7800, 0x800)],
                "konamiscc": [(0x5000, 0x800), (0x7000, 0x800), (0x9000, 0x800), (0xB000, 0x800)],
                "konami": [None, (0x6000, 0x2000), (0x8000, 0x2000), (0xA000, 0x2000)],
                "8kb": [(0x4000, 0x2000), (0x6000, 0x2000), (0x8000, 0x2000), (0xA000, 0x2000)]}[k]
        for w, r in enumerate(regs):
            if r and r[0] <= a < r[0] + r[1]:
                if k == "konami" and v >= self.count:
                    self.blocks[w] = NONE       # measured: Konami shows no block, the window reads $FF
                else:
                    self.blocks[w] = v % self.count


def probe_run(rt, machine=JP):
    """banks.rom with -romtype RT (None: openMSX's guess): the type and the
    block each window shows before any write and after each"""
    s = sym("banks")
    tcl = (f'TYPE banks.rom\n'
           f'debug set_bp {s["done"]} {{![info exists ::seen]}} {{ set ::seen 1; '
           f'M res {gen48.RESULTS_AT} {4 * (len(gen48.PROBE_WRITES) + 1)} }}\n')
    lines = msxcap.run_tcl(rom("banks"), 10, tcl, machine=machine, tcl_setup=STATE,
                           extra_args=["-romtype", rt] if rt else [])
    w = [x.split() for x in lines]
    res = bytes.fromhex(next(x[2] for x in w if x[0] == "res"))
    return next(x[1] for x in w if x[0] == "type"), [list(res[i:i + 4]) for i in range(0, len(res), 4)]


def boot_writes(machine):
    """the writes into pages 1 and 2 from power-on to INIT: the cartridge's
    slot, {(address, value, pc): times} in it, and the same for each other
    slot"""
    setup = ('set ::wr [dict create]\n'
             'debug set_watchpoint write_mem {0x4000 0xBFFF} {![info exists ::f0]} {\n'
             '  set k "[format %04X $::wp_last_address] [format %02X $::wp_last_value] '
             '[format %04X [reg PC]] [lindex [get_selected_slot [expr {$::wp_last_address >> 14}]] 0]"\n'
             '  dict incr ::wr $k\n'
             '}\n')
    tcl = ('L "slot [lindex [get_selected_slot 1] 0]"\n'
           'dict for {k v} $::wr { L "bw $k $v" }\n')
    lines = msxcap.run_tcl(rom("banks"), 2, tcl, machine=machine, tcl_setup=STATE + setup)
    w = [x.split() for x in lines]
    slot = next(x[1] for x in w if x[0] == "slot")
    out, others = {}, {}
    for x in w:
        if x[0] == "bw":
            k = (int(x[1], 16), int(x[2], 16), int(x[3], 16))
            if x[4] == slot:
                out[k] = int(x[5])
            else:
                others.setdefault(x[4], {})[k] = int(x[5])
    return slot, out, others


VOTES = {0x5000: ["konamiscc"], 0x9000: ["konamiscc"], 0xB000: ["konamiscc"],
         0x4000: ["konami"], 0x8000: ["konami"], 0xA000: ["konami"],
         0x6800: ["ascii8"], 0x7800: ["ascii8"],
         0x6000: ["konami", "ascii8", "ascii16"], 0x7000: ["konamiscc", "ascii8", "ascii16"],
         0x77FF: ["ascii16"]}
ORDER = ["8kb", "ascii8", "ascii16", "konami", "konamiscc"]   # of equal votes, the later wins


def lds(data):
    """every LD (nn),A in a cartridge's bytes, $32 and an address of VOTES,
    wherever it stands: {address: times}"""
    out = {}
    for i in range(len(data) - 3):
        if data[i] == 0x32:
            a = data[i + 1] | data[i + 2] << 8
            if a in VOTES:
                out[a] = out.get(a, 0) + 1
    return out


def guess(data):
    """the type a count of LD (nn),A gives: a vote for each type that has a
    register at the address, ASCII8 one vote fewer, the most votes winning,
    of equal votes the later in ORDER, and none at all 8kB"""
    votes = dict.fromkeys(ORDER, 0)
    for a, n in lds(data).items():
        for t in VOTES[a]:
            votes[t] += n
    if votes["ascii8"]:
        votes["ascii8"] -= 1
    best = "8kb"
    for t in ORDER:
        if votes[t] and votes[t] >= votes[best]:
            best = t
    return best, votes


CRAFTED = {"none": [], "77FF": [0x77FF], "7000": [0x7000], "6000": [0x6000], "7800": [0x7800],
           "7800 7800": [0x7800, 0x7800], "5000": [0x5000], "8000": [0x8000],
           "6000 77FF": [0x6000, 0x77FF], "8000 77FF": [0x8000, 0x77FF], "5000 8000": [0x5000, 0x8000],
           "6800 6800 77FF": [0x6800, 0x6800, 0x77FF], "7000 7000 6000": [0x7000, 0x7000, 0x6000],
           "6800 6800": [0x6800, 0x6800], "4000": [0x4000], "9000": [0x9000], "A000": [0xA000],
           "B000": [0xB000], "6000 7000 77FF": [0x6000, 0x7000, 0x77FF],
           "7000 7800 7800": [0x7000, 0x7800, 0x7800], "6000 7800 7800": [0x6000, 0x7800, 0x7800]}


def crafted_rom(addrs, path):
    """128 KB: a header whose INIT stops, and an LD (nn),A for each address"""
    data = bytearray(0x20000)
    data[0:4] = b"AB\x10\x40"
    data[0x10:0x13] = bytes([0xF3, 0x18, 0xFE])         # di / jr $
    for i, a in enumerate(addrs):
        data[0x100 + 3 * i:0x103 + 3 * i] = bytes([0x32, a & 255, a >> 8])
    path.write_bytes(bytes(data))
    return bytes(data)


def type_of(path, extra=()):
    lines = msxcap.run_tcl(path, 2, f"TYPE {Path(path).name}\n", tcl_setup=STATE, extra_args=extra)
    return next(x.split()[1] for x in lines if x.startswith("type "))


def mappers():
    out = {}
    # ---- the probe
    pr = {}
    slot, bw, oth = boot_writes(JP)
    slot_eu, bw_eu, oth_eu = boot_writes(EU)
    assert bw == bw_eu and oth == oth_eu, "the BIOS writes the same on both machines"
    boot = [(a, v) for (a, v, pc), n in sorted(bw.items())]
    for rt in ROMTYPES:
        mtype, res = probe_run(rt)
        kind = rt or next(k for k, v in TYPE_NAMES.items() if v == mtype)
        pm = PyMapper(kind)
        for a, v in boot:
            pm.write(a, v)
        want = [list(pm.blocks)]
        for a, v in gen48.PROBE_WRITES:
            pm.write(a, v)
            want.append(list(pm.blocks))
        assert res == want, (rt, res, want)
        if rt:
            assert mtype == TYPE_NAMES[rt], (rt, mtype)
        pr[rt or "guessed"] = {"type": mtype, "blocks": res}
        print("probe", rt, mtype, flush=True)
    out["probe"] = pr
    out["writes"] = [list(w) for w in gen48.PROBE_WRITES]
    out["boot"] = {"slot": slot, "writes": [[a, v, pc, n] for (a, v, pc), n in sorted(bw.items())],
                   "others": {sl: [[a, v, pc, n] for (a, v, pc), n in sorted(x.items())]
                              for sl, x in sorted(oth.items())}}
    # ---- what openMSX takes each cartridge for
    tp = {}
    for name in ("long", "far", "guess", "banks"):
        data = rom(name).read_bytes()
        got = type_of(rom(name))
        want, votes = guess(data)
        assert got == TYPE_NAMES[want], (name, got, want, votes)
        tp[name] = {"type": got, "lds": {f"{a:04X}": n for a, n in sorted(lds(data).items())},
                    "votes": votes}
    tmp = Path(tempfile.mkdtemp(prefix="votes48_"))
    for label, addrs in CRAFTED.items():
        p = tmp / ("v_" + label.replace(" ", "_") + ".rom")
        data = crafted_rom(addrs, p)
        got = type_of(p)
        want, votes = guess(data)
        assert got == TYPE_NAMES[want], (label, got, want, votes)
        tp["lds " + label] = {"type": got, "votes": votes}
        print("type", label, got, flush=True)
    shutil.rmtree(tmp)
    out["types"] = tp
    return out


# ---------------------------------------------------------------- the photos
BORDER = gen47.CAVE_BORDER
EXTRA = 2                           # frames more photographed in each film, not in a figure


def model_states(name, n=FRAMES):
    m = model48.MODELS[name](sym(name))
    for _ in range(n):
        m.step_loop()
    return m.states


def fig_loops():
    """the loops whose frames the figures show, from the models: long.rom's
    last frame of bank 1 and first of bank 2, and the frame far.rom gets
    wrong first (figures 48.1 and 48.2); far.rom's; guess.rom's last frame
    before the mapper serves another column, and the first (figure 48.3)"""
    lg, fr, gs = model_states("long"), model_states("far"), model_states("guess")
    t = next(k for k, st in enumerate(lg) if st[0][1] == 2)
    f = next(k for k, st in enumerate(fr) if st[2] != st[0][1])
    g = next(k for k, st in enumerate(gs) if st[1][0] != st[0][0])
    return {"long": (t - 1, t, f), "far": (f,), "guess": (g - 1, g)}


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
    picture of its bytes; the one offset that fits"""
    data, regs_, lost, _ = taken_writes(res, machine)
    want = sorted(frames)
    models, _ = line_pictures(data, regs_, machine, set(want))
    shots = sorted({c + d for c in want for d in (-1, 0, 1)})
    tmp = Path(tempfile.mkdtemp(prefix="ph48_"))
    pngs = msxcap.capture(rom(name), shots, tmp, f"{name}_{TAG[machine]}_f", machine=machine, timeout=3600)
    ph = {c: codes(pngs[c]) for c in shots}
    fits = [d for d in (-1, 0, 1) if all(against(ph[c + d], models[c], BORDER) == 0 for c in want)]
    assert fits, (name, machine, [(c, d, against(ph[c + d], models[c], BORDER)) for c in want for d in (-1, 0, 1)])
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
    fl = fig_loops()
    for name, mc in FILMS:
        res = cache.get((name, mc)) or analyse(name, mc)
        cache[(name, mc)] = res
        rows = res["rows"]
        loops = fl[name]
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
def fresh_walk(name="long", machine=JP):
    return walker(HERE / name, 0x80 if machine == EU else 0, MAPPER.get(name, "ascii16"))


def poke(wk, label, vals, off=0):
    a = wk.sym[label] + off
    for i, v in enumerate(vals if isinstance(vals, list) else [vals]):
        wk.mem[a + i] = v & 255


def place(wk, **v):
    for k, x in v.items():
        poke(wk, k, x)


def prices():
    out = {}
    for name in ("long", "far"):
        wk = fresh_walk(name)
        wk.set_blocks([0, 1, 2, 3])
        place(wk, copy=[79, 80, 0, 15, 0xD0], table=0x18)
        sd = {}
        for lab, sh, shown, pending in (("a frame", 1, 1, 1), ("a turn", 0, 1, 1), ("a turn, a new bank", 0, 1, 2)):
            place(wk, shift=sh, shown=shown, pending=pending, fresh=0, table=0x18)
            wk.set_blocks([0, 1, 2 * pending, 2 * pending + 1])
            sd[lab] = wk.call("sends")
        out[f"{name}_sends"] = sd
    wk = fresh_walk("long")
    wk.set_blocks([0, 1, 2, 3])
    place(wk, shift=3, fresh=0)
    bs = {"pairs": wk.call("BSHOW")}
    place(wk, fresh=1)
    bs["pairs and colours"] = wk.call("BSHOW")
    out["bshow"] = bs
    out["bshow_bytes"] = 8 * gen48.NPS[1]
    wn = {}
    for lab, b, sg, o in (("in a segment", 1, 2, 5), ("a segment's last", 1, 2, gen48.SEGW - 1),
                          ("a bank's last", 1, gen48.SEGS - 1, gen48.SEGW - 1),
                          ("the world's last", gen48.BANKS, gen48.SEGS - 1, gen48.SEGW - 1)):
        place(wk, wbank=b, wseg=sg, woff=o, table=0x18)
        wn[lab] = wk.call("window")
        wn[lab + " -> next"] = [wk.mem[wk.sym[k]] for k in ("wbank", "wseg", "woff")]
    out["window"] = wn
    out["window_names"] = 32 * len(gen48.SCROLL_ROWS)
    stp = {}
    for sh, lab in ((3, "a pixel"), (0, "a window")):
        place(wk, shift=sh, wbank=1, wseg=2, woff=5, table=0x18)
        stp[lab] = wk.call("step")
    out["step"] = stp
    out["switch"] = 14                      # LD (nn),A, from the listing: the mapper's write
    return out


# ---------------------------------------------------------------- the workshop
def build_variant(kind):
    name, src = gen48.variant(kind)
    d = Path(tempfile.mkdtemp(prefix=f"var48_{kind}_"))
    for f in ("msx.inc", "bios.inc"):
        shutil.copy(HERE / f, d)
    (d / f"{name}.asm").write_text(src)
    subprocess.run(["sjasmplus", "--nologo", "--msg=err", "--syntax=bFw", f"--sym={name}.sym",
                    f"--lst={name}.lst", f"{name}.asm"], cwd=d, check=True)
    return name, d / name


def checked(name, machine, path=None, model=None, extra=(), kind=None):
    """a film held against its model as films() holds the book's: the
    frames wrong against the picture meant, the summary"""
    res = analyse(name, machine, path=path, model=model, extra=extra, kind=kind)
    data, regs_, lost, _ = taken_writes(res, machine)
    assert not lost
    bad, leads = picture_check(res, data, regs_, machine)
    assert all(ld > 0 for ld, _ in leads.values())
    return res, bad


def answers():
    out = {}
    fl = json.loads((HERE / "meas48.json").read_text())
    films_, mp = fl["films"], fl["mappers"]
    # 1. the cave from bank 7: after its last column, bank 1's first
    name, path = build_variant("round")
    s_ = dbg.sym(path.with_suffix(".sym"))
    res, bad = checked(name, JP, path=path, model=model48.MODELS["round"](s_))
    assert not bad["meant"]
    out["q1"] = {"turns": bank_turns(res), "frames_wrong": len(bad["meant"]), "loops": len(res["rows"]),
                 "type": res["type"]}
    print("q1", out["q1"], flush=True)
    # 2. guess.rom told it is ASCII16
    s_ = sym("guess")
    res, bad = checked("guess", JP, model=model48.Long(s_, "guess", mapper="ascii16"),
                       extra=["-romtype", "ascii16"], kind="ascii16")
    out["q2"] = {"type": res["type"], "frames_wrong": len(bad["meant"]), "turns": bank_turns(res),
                 "loops": len(res["rows"])}
    assert not bad["meant"]
    print("q2", out["q2"], flush=True)
    # 3. far.asm put right with less: page 2 mapped at a turn, and given back by window
    name, path = build_variant("once")
    s_ = dbg.sym(path.with_suffix(".sym"))
    q3 = {}
    for mc in (JP, EU):
        res, bad = checked(name, mc, path=path, model=model48.MODELS["once"](s_))
        assert not bad["meant"]
        rows = res["rows"]
        lg = films_["long"][TAG[mc]]["rows"]
        assert len(rows) == len(lg)
        diffs = {}
        for a, b in zip(lg[1:], rows[1:]):
            d = num(a["sends"] + a["logic"] - b["sends"] - b["logic"])
            diffs[str(d)] = diffs.get(str(d), 0) + 1
        q3[TAG[mc]] = {"frames_wrong": len(bad["meant"]), "summary": summary(rows, mc), "saved": diffs,
                       "sends": summary(rows, mc)["sends"], "sends_long": films_["long"][TAG[mc]]["summary"]["sends"]}
    out["q3"] = q3
    print("q3", q3["jp"]["saved"], flush=True)
    # 4. LD ($6000),A, LD ($7000),A and LD ($77FF),A: the votes, measured in mappers
    out["q4"] = mp["types"]["lds 6000 7000 77FF"]
    # 5. how many pairs a bank could have before a turn into a new bank meets the paper
    q5 = {}
    for mc in (JP, EU):
        res = CACHE.get(("long", mc)) or analyse("long", mc)
        CACHE[("long", mc)] = res
        times = write_times(res["writes"], res["f0"], mc)
        k = next(i for i, (f, st) in enumerate(res["states"]) if i and st[0][1] != res["states"][i - 1][1][0][1])
        r = res["rows"][k]
        lo, hi = res["spans"][k]
        sig = signal_of(r["frame"] + res["f0"], mc)
        idx = [i for i in range(len(times)) if lo <= times[i] < hi]
        last = max(idx)
        assert res["writes"][last][2] == 0x99 and res["writes"][last][3] == 0x82   # R#2's
        r2 = times[last] - sig
        per = 16 * 23                       # a pair more: 8 patterns and 8 colours, 23 T a byte
        np_ = gen48.NPS[1]
        s_ = sym("long")
        free = 0xC000 - (s_["shifts1"] + 8 * 8 * np_)
        room = free // (8 * 8 + 8)          # a pair more: 8 bytes at each shift, 8 of colours
        assert 8 * (np_ + room) <= 255      # still one OTIR each
        q5[TAG[mc]] = {"r2": num(r2), "to_paper": num(TO_PAPER[mc]), "per_pair": per, "free": free,
                       "more": room, "pairs": np_ + room, "r2_then": num(r2 + room * per),
                       "before_paper": num(TO_PAPER[mc] - (r2 + room * per))}
    out["q5"] = q5
    print("q5", q5, flush=True)
    return out


# ---------------------------------------------------------------- the world round
def world_loops():
    """the loops of figure 48.4, from the model: one at the start, the first
    turn's, and the turn that first shows each bank after it, bank 2 to bank 7
    and bank 1 again"""
    out, last = [7], None
    m = model48.Long(sym("long"))
    k = 0
    while len(out) < 1 + gen48.BANKS:
        m.step_loop()
        b = m.states[-1][0][1]
        if last is not None and b != last:
            out.append(k)
        last, k = b, k + 1
    return out, m


def world(cache=CACHE):
    """long.rom for a turn round its world on each machine, not filmed but
    clipped: five frames recorded round each frame of figure 48.4, the last
    four held against the model's picture of the world (the first is the
    frame under way when the recording starts, never whole); and the
    variables where a loop of that frame wakes, against the model's"""
    loops, _ = world_loops()
    out = {"loops": loops}
    for mc in (JP, EU):
        m = model48.Long(sym("long"))
        rams, pics = {}, {}
        s_ = sym("long")
        want_frames = [k + 3 for k in loops]       # a loop's frame: chapter 48's films say 3 on
        need = {f + d for f in want_frames for d in range(-4, 5)}
        k = 0
        while k <= max(loops) + 4:
            m.loop += 1
            m.isr()
            if k + 3 in need:
                rams[m.ram()["ticks"]] = (k, m.ram())
            m.ports = []
            m.sends()
            st = m.states[-1]
            if k + 3 in need:
                pics[k + 3] = m.picture(*st)
            m.ports = []
            m.run()
            k += 1
        tmp = Path(tempfile.mkdtemp(prefix="world48_"))
        ev = {}
        for f in want_frames:
            ev[max(f - 2, 1)] = (f"record start -videoonly {{{tmp}/c{f}.avi}}; "
                                 f"set ::want 1")
            ev[f + 3] = "record stop"
        tcl = (f'set ::want 0\n'
               f'debug set_bp {s_["isrend"]} {{$::want == 1}} {{ set ::want 2 }}\n'
               f'debug set_bp {s_["woke"]} {{$::want == 2}} {{ set ::want 0; '
               f'L "woke [machine_info VDP_frame_count]"; M v {VARS[0]} {VARS[1]}; BLK long.rom }}\n')
        lines = msxcap.run_tcl(rom("long"), max(want_frames) + 4, F0 + tcl, machine=mc, tcl_setup=STATE,
                               events=ev, timeout=3600)
        w = [x.split() for x in lines]
        got_ram, blk = [], None
        for x in w:
            if x[0] == "v" and x[1] == "mem":
                got_ram.append(bytes.fromhex(x[2]))
            elif x[0] == "blk":
                blk = [int(v) for v in x[1:]]
                got_ram[-1] = (got_ram[-1], blk)
        assert len(got_ram) == len(loops), (mc, len(got_ram))
        read_at = []
        for v, b in got_ram:
            got = ram_of(s_, v, b)
            k, want = rams[got["ticks"]]
            assert got == want, (TAG[mc], k, {x: (got[x], want[x]) for x in got if got[x] != want[x]})
            read_at.append(k)
        fits, kept = {}, {}
        for f in want_frames:
            clip = tmp / f"c{f}.avi"
            pd = tmp / f"p{f}"
            pd.mkdir()
            subprocess.run([msxcap.FFMPEG, "-v", "error", "-i", str(clip), "-start_number", "0",
                            str(pd / "%02d.png")], check=True)
            shots = sorted(pd.glob("*.png"))
            first = max(f - 2, 1)
            ph = [codes(x) for x in shots]
            ok = [d for d in range(-2, 3)       # the clip's first frame is the one under way
                  if all(first + i + d in pics and against(ph[i], pics[first + i + d], BORDER) == 0
                         for i in range(1, len(ph)))]
            assert len(ok) == 1, (TAG[mc], f, ok)
            fits[str(f)] = ok[0]
            i = f - first - ok[0]
            dest = (CAPS if mc == JP else SHOTS) / f"long_{TAG[mc]}_w{f:05d}.png"
            dest.parent.mkdir(exist_ok=True)
            msxcap.clean_png(shots[i], dest)
            kept[str(f)] = dest.name
        shutil.rmtree(tmp)
        out[TAG[mc]] = {"frames": want_frames, "clip_offsets": fits, "photos": kept,
                        "ram_loops": read_at}
        print("world", TAG[mc], fits, flush=True)
    return out


# ---------------------------------------------------------------- main
def openmsx():
    if not versions.builds():
        return {"skipped": "OPENMSX_BUILDS not set"}
    return versions.every_build(["ch48"], OPENMSX_SECTIONS)


OPENMSX_SECTIONS = ["films", "mappers", "photos", "world", "prices", "answers"]
SECTIONS = {"films": films, "mappers": mappers, "photos": photos, "world": world, "prices": prices,
            "answers": answers, "openmsx": openmsx}


def main(names=()):
    path = HERE / "meas48.json"
    old = json.loads(path.read_text()) if path.exists() else {}
    for n in (names or SECTIONS):
        old[n] = SECTIONS[n]()
        path.write_text(json.dumps(old, indent=1, sort_keys=True))


if __name__ == "__main__":
    main(sys.argv[1:])
