#!/usr/bin/env python3
"""meas25.py -- plotting and drawing in Graphic II, measured.

    python3 gen25.py && ./build.sh && python3 meas25.py
                                  python3 meas25.py over fan    only these

Every program draws with the display on. Each is run on both machines; its
photograph, the frame after it finishes, must be vdpscreen.py's drawing of
the VRAM the debugger reads, and the patterns in that VRAM must be the
pixels gen25.bresenham() chooses. Every call's T-states, from the debugger's
clock, must be what walk.py finds walking the listing. Every byte to and
from the ports is logged and played through chapter 20's vdpslots.py, which
must end with the debugger's VRAM and lose what openMSX calls too soon.

  over      over.rom: a line drawn with pixel, which writes, and with plot,
            which reads, changes and writes (figure 25.1)
  cost      cost.rom: seven lines with line, rline and tline
  fan       fan.rom: 88 lines through the ports (figures 25.2 and 25.3);
            and tight.rom, the same with the IN 27 T-states after the read
            address
  buffer    buffer.rom: the lines in the RAM, then sent; and through.rom,
            in the RAM and written to the VRAM
  hidden    WHERE IT BREAKS: hidden.rom and shown.rom (figure 25.4)
  passes    one pass of each loop of line, rline and tline, each way it can
            go, priced by walk.py
  answers   the workshop, tried (for Appendix I)
  openmsx   all of it again with every other build (tools/versions.py)
"""
import json
import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "ch20"))
sys.path.insert(0, str(HERE))
import meas        # noqa: E402
import msxcap      # noqa: E402
import probe as dbg  # noqa: E402
import versions    # noqa: E402
import vdpslots    # noqa: E402  (chapter 20: when the VDP takes a byte)
import gen25       # noqa: E402
import vdpscreen   # noqa: E402  (chapters 21 to 23: the photograph from the VRAM)
import walk        # noqa: E402  (the listing's T-states)

CAPS = HERE / "captures"
EU, JP = "MSXBOOK_EU16", "MSXBOOK_JP16"
TAG = {EU: "eu", JP: "jp"}
CLOCK = 3579545
FRAMES = 60                 # long enough for every program to finish
POS = "[machine_info VDP_frame_count] [machine_info VDP_cycle_in_frame]"
REGS = " ".join(f"[debug read {{VDP regs}} {i}]" for i in range(8))
VRAM = 'binary scan [debug read_block {VRAM} 0 16384] H* h; L "vram $h"'
BUFFER = f'binary scan [debug read_block memory {gen25.BUF} 6144] H* h; L "buf $h"'
F0 = 'L "f0 [machine_info VDP_frame_count]"\n'
TOO_FAST = ('proc ::toofast_cb {args} { if {$::on} { L "fast ' + POS + '" } }\n'
            'set VDP.too_fast_vram_access_callback ::toofast_cb\n')
RECORD = ('set ::on 0\n'
          'debug set_watchpoint write_io {0x98 0x99} {} { if {$::on} { L "w ' + POS +
          ' $::wp_last_address $::wp_last_value" } }\n'
          'debug set_watchpoint read_io {0x98 0x99} {} { if {$::on} { L "r ' + POS +
          ' $::wp_last_address" } }\n')
BLACK, LIGHT_GREEN, DARK_BLUE, WHITE = gen25.BLACK, gen25.LIGHT_GREEN, gen25.DARK_BLUE, gen25.WHITE

PALETTE = [tuple(c) for c in json.loads((REPO / "ch01" / "meas01.json").read_text())["palette"]["rgb"]]
CODE = {rgb: n for n, rgb in enumerate(PALETTE) if n}


def rom(name):
    return HERE / f"{name}.rom"


def sym(name):
    return dbg.sym(HERE / f"{name}.sym")


def codes(png):
    im = Image.open(png).convert("RGB")
    px = im.load()
    return [[CODE.get(px[x, y]) for x in range(im.width)] for y in range(im.height)]


def against(model, photo, backdrop):
    """pixels of the photograph that are not the model's: the paper, and the
    border inside the columns the VDP draws (chapter 4)"""
    bad = 0
    for y in range(240):
        for x in range(meas.DRAWN[0], meas.DRAWN[1] + 1):
            px, py = x - meas.PAPER_X0, y - meas.PAPER_Y0
            want = model[py][px] if 0 <= px < 256 and 0 <= py < 192 else backdrop
            bad += photo[y][x] != want
    return bad


def paper_px(photo, x, y):
    return photo[meas.PAPER_Y0 + y][meas.PAPER_X0 + x]


def once(addr, body, tag):
    """a breakpoint that logs once and removes itself"""
    return f'set ::{tag} [debug set_bp {addr} {{}} {{ {body}; debug remove_bp $::{tag} }}]\n'


def patterns(pixels):
    """the 6,144 pattern bytes with PIXELS set, the rest paper"""
    out = bytearray(6144)
    for x, y in pixels:
        out[vdpscreen.address(x, y)] |= 0x80 >> (x & 7)
    return bytes(out)


def events(w, machine):
    """[(cycle from the first frame's start, port, value or None)], and the
    first frame, from the watchpoints' log (chapter 20)"""
    frame = vdpslots.LINES[machine] * vdpslots.LINE
    ev = [(int(x[1]), int(x[2]), int(x[3]) & 0xFF, int(x[4]) if x[0] == "w" else None)
          for x in w if x[0] in ("w", "r")]
    f0 = ev[0][0]
    return [((f - f0) * frame + c, p, v) for f, c, p, v in ev], f0


def session(name, machine, timed=(), record=False, buffer_at=()):
    """run NAME; log the time at each label of TIMED every time it is reached,
    the registers and the VRAM at go and at done, the buffer at each label of
    BUFFER_AT, and, if RECORD, every port operation from go to done. Then the
    photograph of the frame after done, against the model."""
    s = sym(name)
    tcl = F0 + RECORD + TOO_FAST
    for lab in timed:
        tcl += f'debug set_bp {s[lab]} {{}} {{ L "t {lab} [machine_info time]" }}\n'
    for lab in buffer_at:
        tcl += once(s[lab], BUFFER.replace('"buf', f'"buf {lab}'), f"b_{lab}")
    tcl += once(s["go"], f'L "regs {REGS}"; {VRAM.replace(chr(34) + "vram", chr(34) + "vram0")}; '
                         f'L "go {POS} [machine_info time]"; set ::on {int(record)}', "g")
    tcl += once(s["done"], f'set ::on 0; L "regs {REGS}"; {VRAM}; '
                           f'L "done {POS} [machine_info time]"', "d")
    lines = msxcap.run_tcl(rom(name), FRAMES, tcl, machine=machine)
    w = [l.split() for l in lines]
    f0 = int(next(x for x in w if x[0] == "f0")[1])
    regs = [int(v) for v in [x for x in w if x[0] == "regs"][-1][1:]]
    regs0 = [int(v) for v in [x for x in w if x[0] == "regs"][0][1:]]
    vram0 = bytes.fromhex(next(x for x in w if x[0] == "vram0")[1])
    vram = bytes.fromhex(next(x for x in w if x[0] == "vram")[1])
    go = next(x for x in w if x[0] == "go")
    done = next(x for x in w if x[0] == "done")
    shot = int(done[1]) - f0 + 2
    png = msxcap.capture(rom(name), [shot], CAPS, f"{name}_{TAG[machine]}_f", machine=machine)[shot]
    photo = codes(png)
    bad = against(vdpscreen.draw(vram, regs), photo, regs[7] & 15)
    assert bad == 0, (name, machine, bad)
    times = {}
    for x in w:
        if x[0] == "t":
            times.setdefault(x[1], []).append(float(x[2]))
    out = {"w": w, "regs": regs, "regs0": regs0, "vram0": vram0, "vram": vram, "photo": photo,
           "shot": shot, "times": times,
           "buffers": {x[1]: bytes.fromhex(x[2]) for x in w if x[0] == "buf"},
           "fast": [x for x in w if x[0] == "fast"],
           "whole": round((float(done[3]) - float(go[3])) * CLOCK),
           "go": [int(go[1]) - f0, int(go[2])], "done": [int(done[1]) - f0, int(done[2])]}
    assert not out["fast"], (name, machine, len(out["fast"]))
    if record:
        ev, ef0 = events(w, machine)
        taken = {}
        got, reads, lost = vdpslots.play(ev, machine, out["vram0"], regs=regs0, taken=taken)
        assert bytes(got) == vram, (name, machine, "the model's VRAM is not the debugger's")
        assert not lost, (name, machine, len(lost))
        out["events"] = ev
        out["taken"] = taken
        out["counts"] = {"out98": sum(1 for _, p, v in ev if p == 0x98 and v is not None),
                         "in98": sum(1 for _, p, v in ev if p == 0x98 and v is None),
                         "out99": sum(1 for _, p, v in ev if p == 0x99 and v is not None)}
    return out


def calls(times, a, b):
    """T-states from each time at label A to the next at label B"""
    return [round((t1 - t0) * CLOCK) for t0, t1 in zip(times[a], times[b])]


def busy_share(ev, machine):
    """of the operations on $98, how many came while the paper was drawn"""
    on98 = [c for c, p, v in ev if p == 0x98]
    return sum(1 for c in on98 if vdpslots.busy(c, machine)), len(on98)


def read_margins(ev, taken, machine):
    """for every IN of $98 that follows a read address: VDP cycles from the
    moment the VDP read the byte ahead to the IN, the least of them, and how
    many of the INs came while the paper was drawn"""
    out, in_paper, last_ask = [], 0, None
    for i, (c, p, v) in enumerate(ev):
        if p == 0x99 and v is not None and not v & 0xC0 and i in taken:
            last_ask = i                        # a read address: the VDP reads ahead
        elif p == 0x98 and v is None and last_ask is not None:
            out.append(c - taken[last_ask])
            in_paper += vdpslots.busy(c, machine)
            last_ask = None
    return min(out), len(out), in_paper


# ---------------------------------------------------------------- over
def over():
    y0, y1 = gen25.OVER_Y
    want = patterns([(x, y0) for x in range(7, 256, 8)] + [(x, y1) for x in range(256)])
    out = {}
    for m in (EU, JP):
        r = session("over", m, timed=("p0", "p1", "q0", "q1"), record=True)
        assert r["vram"][:6144] == want, m
        ink = [sum(1 for x in range(256) if paper_px(r["photo"], x, y) == BLACK) for y in (y0, y1)]
        out[TAG[m]] = {"ink": ink, "pixel_t": sorted(set(calls(r["times"], "p0", "p1"))),
                       "plot_t": sorted(set(calls(r["times"], "q0", "q1"))), "shot": r["shot"],
                       "calls": [len(r["times"]["p0"]), len(r["times"]["q0"])],
                       "counts": r["counts"], "in_paper": busy_share(r["events"], m),
                       "read_margin": read_margins(r["events"], r["taken"], m)}
    wk = walk.Walk(HERE / "over")
    wk.run("init", "go")
    priced = {"pixel": wk.call("pixel", b=100, c=y0), "plot": wk.call("plot", b=100, c=y1),
              "vaddr": wk.call("vaddr", b=100, c=y1)}
    for t in ("eu", "jp"):
        assert out[t]["ink"] == [32, 256] and out[t]["calls"] == [256, 256], out[t]
        assert out[t]["pixel_t"] == [priced["pixel"]] and out[t]["plot_t"] == [priced["plot"]], \
            (out[t], priced)
    out["priced"] = priced
    return out


# ---------------------------------------------------------------- cost
ROUTINES = (("line", "a", "b"), ("rline", "c", "d"), ("tline", "e", "f"))


def cost():
    n = len(gen25.COST_LINES)
    labels = [f"{t}{k}" for _, a, b in ROUTINES for t in (a, b) for k in range(n)]
    want = patterns({p for ln in gen25.COST_LINES for p in gen25.bresenham(*ln)})
    out = {}
    for m in (EU, JP):
        r = session("cost", m, timed=labels, record=True, buffer_at=("done",))
        assert r["vram"][:6144] == want and r["buffers"]["done"] == want, m
        out[TAG[m]] = {name: [calls(r["times"], f"{a}{k}", f"{b}{k}")[0] for k in range(n)]
                       for name, a, b in ROUTINES}
        out[TAG[m]]["in_paper"] = busy_share(r["events"], m)
        out[TAG[m]]["read_margin"] = read_margins(r["events"], r["taken"], m)
    wk = walk.Walk(HERE / "cost")
    wk.run("init", "go")
    wk.call("clear")
    priced = {}
    for name, _, _ in ROUTINES:
        priced[name] = [wk.call(name, b=x0, c=y0, d=x1, e=y1) for x0, y0, x1, y1 in gen25.COST_LINES]
    for t in ("eu", "jp"):
        for name, _, _ in ROUTINES:
            assert out[t][name] == priced[name], (t, name, out[t][name], priced[name])
    out["priced"] = priced
    out["pixels"] = [len(gen25.bresenham(*ln)) for ln in gen25.COST_LINES]
    return out


# ---------------------------------------------------------------- fan
def fan_run(name, routine, buffer_at=()):
    """NAME on both machines: each line's T-states, the photograph, the
    patterns, the ports played through the model"""
    want = patterns(gen25.fan_pixels())
    res = {}
    for m in (EU, JP):
        r = session(name, m, timed=("l0", "l1") + tuple(b for b in buffer_at if b != "done"),
                    record=True,
                    buffer_at=buffer_at)
        assert r["vram"][:6144] == want, (name, m)
        res[TAG[m]] = {"lines": calls(r["times"], "l0", "l1"), "whole": r["whole"],
                       "go": r["go"], "done": r["done"], "shot": r["shot"],
                       "counts": r["counts"], "in_paper": busy_share(r["events"], m)}
        if routine == "line":
            res[TAG[m]]["read_margin"] = read_margins(r["events"], r["taken"], m)
        if buffer_at:
            res[TAG[m]]["buffer"] = {k: v == want for k, v in r["buffers"].items()}
            res[TAG[m]]["marks"] = {lab: calls(r["times"], a, b) for lab, a, b in
                                    (("clear", "c0", "c1"), ("send", "s0", "s1")) if a in r["times"]}
        res[TAG[m]]["_r"] = r
    wk = walk.Walk(HERE / name)
    wk.run("init", "go")
    if "c0" in sym(name):
        res["clear_priced"] = wk.call("clear")
    res["priced"] = [wk.call(routine, b=gen25.CENTRE[0], c=gen25.CENTRE[1], d=x, e=y)
                     for x, y in gen25.FAN]
    if "s0" in sym(name):
        res["send_priced"] = wk.call("send")
    whole = walk.Walk(HERE / name)
    whole.run("init", "go")
    res["whole_priced"] = whole.run("go", "done")
    for t in ("eu", "jp"):
        assert res[t]["lines"] == res["priced"], (name, t)
        assert res[t]["whole"] == res["whole_priced"], (name, t, res[t]["whole"], res["whole_priced"])
    res["pixels"] = [len(gen25.bresenham(*gen25.CENTRE, *e)) for e in gen25.FAN]
    res["different"] = len(set(gen25.fan_pixels()))
    return res


def strip(res):
    for t in ("eu", "jp"):
        res[t].pop("_r", None)
    return res


def fan():
    out = {}
    out["fan"] = fan_run("fan", "line")
    photo = out["fan"]["eu"]["_r"]["photo"]
    out["fan"]["ink"] = sum(1 for y in range(192) for x in range(256) if paper_px(photo, x, y) == BLACK)
    out["tight"] = fan_run("tight", "line")
    for t in ("eu", "jp"):
        assert out["tight"][t]["_r"]["photo"] == out["fan"][t]["_r"]["photo"], t
    out["tight"]["saved"] = [a - b for a, b in zip(out["fan"]["priced"], out["tight"]["priced"])]
    return {k: strip(v) for k, v in out.items()}


# ---------------------------------------------------------------- buffer
def buffer():
    out = {"buffer": fan_run("buffer", "rline", buffer_at=("c0", "c1", "s0", "s1")),
           "through": fan_run("through", "tline", buffer_at=("c0", "c1", "done"))}
    for name in ("buffer", "through"):
        for t in ("eu", "jp"):
            b = out[name][t]["buffer"]
            assert b.get("s0", b.get("done")), (name, t)
    return {k: strip(v) for k, v in out.items()}


# ---------------------------------------------------------------- hidden
def hidden():
    want = patterns(gen25.fan_pixels())
    px = set(gen25.fan_pixels())
    out = {}
    for name, painted in (("hidden", False), ("shown", True)):
        cells = gen25.scene_cells(painted)
        res = {}
        for m in (EU, JP):
            r = session(name, m, timed=("l0", "l1"))
            v = r["vram"]
            assert v[:6144] == want, (name, m)
            for (c, row), byte in cells.items():
                assert all(v[0x2000 + row * 256 + c * 8 + k] == byte for k in range(8))
            inside = {(x, y) for x, y in px if (x // 8, y // 8) in cells}
            seen = {(x, y) for x, y in px if paper_px(r["photo"], x, y) == BLACK}
            res[TAG[m]] = {"set": len(px), "inside": len(inside), "seen": len(seen),
                           "seen_inside": len(seen & inside), "lines": calls(r["times"], "l0", "l1"),
                           "shot": r["shot"],
                           "colours": sorted({c for row in r["photo"] for c in row if c})}
        res["cells"] = len(cells)
        out[name] = res
    fan_lines = json.loads((HERE / "meas25.json").read_text())["fan"]["fan"]["priced"]
    for name in ("hidden", "shown"):
        for t in ("eu", "jp"):
            assert out[name][t]["lines"] == fan_lines, (name, t)
    h, s = out["hidden"]["eu"], out["shown"]["eu"]
    assert h["seen"] == h["set"] - h["inside"] and h["seen_inside"] == 0
    assert s["seen"] == s["set"]
    return out


# ---------------------------------------------------------------- passes
def passes():
    """one pass of each loop, priced by walk.py, for each way it can go: the
    loops to the right (those to the left cost the same), B = 2 so that DJNZ
    jumps back"""
    wk = walk.Walk(HERE / "cost")
    wk.run("init", "go")
    wk.call("clear")
    out = {}
    for kind, p in (("line", ""), ("rline", "r"), ("tline", "t")):
        base = 0 if kind == "line" else gen25.BUF
        res = {}
        for mask, side in ((0x80, "same byte"), (0x01, "next byte")):
            for low, err, minor, down in ((0, 0x50, 1, "no line down"), (0, 0, 1, "down, in the cell"),
                                          (7, 0, 1, "down, to the next row")):
                res[f"flat, {side}, {down}"] = wk.lap(
                    f"{p}frpx", b=2, c=mask, d=40, e=minor, a_=err, h=(base >> 8) + 3, l=0x40 | low)
        for low, down in ((0, "in the cell"), (7, "to the next row")):
            for mask, err, side in ((0x80, 0x50, "no pixel across"), (0x80, 0, "across, same byte"),
                                    (0x01, 0, "across, next byte")):
                res[f"steep, down {down}, {side}"] = wk.lap(
                    f"{p}srpx", b=2, c=mask, d=1, e=40, a_=err, h=(base >> 8) + 3, l=0x40 | low)
        out[kind] = res
    return out


# ---------------------------------------------------------------- answers
def answers():
    m = json.loads((HERE / "meas25.json").read_text())
    out = {}
    # 1: the bytes plot reads and writes for (100, 150)
    a = vdpscreen.address(100, 150)
    out["q1"] = {"address": a, "read": [a & 0xFF, a >> 8], "write": [a & 0xFF, (a >> 8) | 0x40],
                 "mask": 0x80 >> (100 & 7)}
    # 2: line across the whole paper, by the walk
    wk = walk.Walk(HERE / "cost")
    wk.run("init", "go")
    wk.call("clear")
    out["q2"] = {r: wk.call(r, b=0, c=100, d=255, e=100) for r in ("line", "rline", "tline")}
    # 4: the pixels at which the buffer pays: its clear and send against the
    # T-states a pixel saved, at the fan's rates
    f, b = m["fan"]["fan"], m["buffer"]["buffer"]
    px = sum(f["pixels"])
    fixed = b["clear_priced"] + b["send_priced"]
    rate_port, rate_ram = sum(f["priced"]) / px, sum(b["priced"]) / px
    out["q4"] = {"fixed": fixed, "rate_port": rate_port, "rate_ram": rate_ram,
                 "pixels": fixed / (rate_port - rate_ram),
                 "for_1000": {"line": 1000 * rate_port, "rline": fixed + 1000 * rate_ram}}
    return out


# ---------------------------------------------------------------- openmsx
OPENMSX_SECTIONS = ["over", "cost", "fan", "buffer", "hidden"]


def openmsx():
    if not versions.builds():
        return {"skipped": "OPENMSX_BUILDS not set"}
    return versions.every_build(["ch25"], OPENMSX_SECTIONS)


SECTIONS = {"over": over, "cost": cost, "fan": fan, "buffer": buffer, "hidden": hidden,
            "passes": passes, "answers": answers, "openmsx": openmsx}


def main(names=()):
    CAPS.mkdir(exist_ok=True)
    path = HERE / "meas25.json"
    m = json.loads(path.read_text()) if names and path.exists() else {}
    for name in names or SECTIONS:
        print(name, flush=True)
        m[name] = SECTIONS[name]()
        m = {k: m[k] for k in SECTIONS if k in m}
        path.write_text(json.dumps(m, indent=1) + "\n")
    return m


if __name__ == "__main__":
    out = main(sys.argv[1:])
    print(json.dumps({k: out[k] for k in (sys.argv[1:] or out) if k in out}, indent=1)[:6000])
