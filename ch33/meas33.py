#!/usr/bin/env python3
"""meas33.py -- the frame loop, measured.

    python3 gen33.py && ./build.sh && python3 meas33.py
                                  python3 meas33.py order edge     only these

Every loop of every film, on both machines: the debugger stops on the
interrupt's routine, on each R#7 write that marks a part of the loop, and on
HALT; it reads the frames counted and, after each send, the attribute table
in the VRAM. A model built from walk.py's prices and chapter 19's signal
predicts, loop by loop, the frames lost and the pixels moved, and the
debugger must agree; the photograph of every frame is vdpscreen.py's paper
with the herd the VRAM held, and a border that changes where chapter 18 puts
each write of R#7.

  heartbeat  isr: walk.py's price, and where the debugger finds it
  order      order.rom (figures 33.1 and 33.2)
  nocount    nocount.rom (figure 33.2)
  edge       fits.rom and misses.rom: the loop at the frame's edge
  speed      speed.rom: pixels a second at 50 and at 60 Hz
  seconds    seconds.rom: ten minutes by openMSX's clock on each machine
  first      WHERE IT BREAKS: first.rom (figure 33.3)
  prices     walk.py's T-states for the parts of the loop
  answers    the workshop, tried (for Appendix I)
  openmsx    all of it again with every other build (tools/versions.py)
"""
import json
import math
import sys
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
import gen33       # noqa: E402
sys.path.remove(str(HERE))
sys.path.insert(0, str(HERE))      # gen33 put chapters 26 and 30 first: this folder's files win
for mod in ("vdpscreen", "walk"):
    sys.modules.pop(mod, None)
import vdpscreen   # noqa: E402
import walk        # noqa: E402  (chapter 32's)

assert Path(vdpscreen.__file__).parent == HERE and Path(walk.__file__).parent == HERE

CAPS = HERE / "captures"
EU, JP = gen33.EU, gen33.JP
TAG = {EU: "eu", JP: "jp"}
L = gen33.LINE_T
FT = gen33.FRAME_T
ROW0 = {m: gen33.PAPER0[m] - meas.PAPER_Y0 for m in (EU, JP)}
SIGNAL = Fraction(101, 3)          # F rises at T-state 33 2/3 of its line (chapter 19)
ANSWER = 19 + 11                   # mode 2's answer and the JP (chapter 17)
ISR_T = 84                         # isr, to its RET (walk.py; prices checks it)
POS = "[machine_info VDP_frame_count] [machine_info VDP_cycle_in_frame]"
REGS = " ".join(f"[debug read {{VDP regs}} {i}]" for i in range(8))
F0 = 'L "f0 [machine_info VDP_frame_count]"\n'
TOO_FAST = ('proc ::toofast_cb {args} { L "fast [machine_info VDP_frame_count] '
            '[machine_info VDP_cycle_in_frame]" }\n'
            'set VDP.too_fast_vram_access_callback ::toofast_cb\n')
MARKS = {"m0": gen33.SEND_MARK, "m1": gen33.LOGIC_MARK, "m2": gen33.WAIT_MARK}

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


def num(f):
    return int(f) if f == int(f) else round(float(f), 2)


def run(name, frames, tcl, machine, fast_ok=False):
    lines = msxcap.run_tcl(rom(name), frames, F0 + TOO_FAST + tcl, machine=machine)
    w = [l.split() for l in lines]
    assert fast_ok or not [x for x in w if x[0] == "fast"], (name, machine, "an access too soon")
    return w


def t_abs(fc, cyc, machine):
    """a breakpoint's T-state, counted from the start of the VDP's frame 0"""
    return int(fc) * FT[machine] + Fraction(int(cyc), 6)


def signal_of(frame, machine):
    return frame * FT[machine] + gen33.FLAG_LINE[machine] * L + SIGNAL


def shows(t, machine):
    """(frame, line, x) where a write of R#7 at T-state T shows: x = ceil(1.5 w
    - 31) for the whole T-state w of the line (chapter 18)"""
    frame, rest = divmod(math.floor(t), FT[machine])
    line, w = divmod(rest, L)
    return frame, line, math.ceil(1.5 * w - 31)


# ---------------------------------------------------------------- the screen
def vram_of(table):
    """the VRAM of the herd's programs: Graphic II all paper, black on white,
    the figure's patterns and the attribute table TABLE (128 bytes)"""
    v = bytearray(16384)
    v[0x2000:0x3800] = bytes([0x1F]) * 6144
    v[0x1800:0x1B00] = bytes(range(256)) * 3
    v[gen33.PAT:gen33.PAT + 32] = bytes(gen33.FIGURE)
    v[gen33.ATT:gen33.ATT + 128] = table
    return v


def capture_model(paper, writes, frame, machine):
    """the capture of FRAME: PAPER (192 x 256) and a border whose colour each
    write of R#7, (T-state, colour), sets from where it shows"""
    row0 = ROW0[machine]
    start = (frame, row0, meas.DRAWN[0])
    now, changes = gen33.WHITE, []
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


def mismatch(model, photo):
    return sum(1 for y in range(meas.CAPTURE_H) for x in range(meas.DRAWN[0], meas.DRAWN[1] + 1)
               if model[y][x] != photo[y][x])


# ---------------------------------------------------------------- the films
def film(name, machine, frames=56, fast_ok=False):
    """every loop of a herd program: the interrupts, the marks, HALT, the
    frames counted at m1 and the attribute table after the send"""
    s = sym(name)
    after_send = "m2" if name == "first" else "m1"
    tcl = ""
    for k in ("isr", "m0", "m1", "m2", "main"):
        extra = ""
        if k == "m1":
            extra += f'L "v [debug read memory {s["ticks"]}] [debug read memory {s["last"]}]"; '
        if k == after_send:
            extra += ('binary scan [debug read_block {VRAM} 0x1B00 128] H* h; L "att $h"; '
                      f'L "regs {REGS}"; ')
        if k == "isr":
            extra += 'L "ret [debug read memory [reg sp]] [debug read memory [expr {[reg sp] + 1}]]"; '
        tcl += f'debug set_bp {s[k]} {{}} {{ {extra}L "{k} {POS}" }}\n'
    w = run(name, frames, tcl, machine, fast_ok)
    f0 = int(next(x for x in w if x[0] == "f0")[1])
    ev, pend = [], {}
    for x in w:
        if x[0] == "v":
            pend["ticks"], pend["last"] = int(x[1]), int(x[2])
        elif x[0] == "att":
            pend["att"] = bytes.fromhex(x[1])
        elif x[0] == "regs":
            pend["regs"] = [int(v) for v in x[1:]]
        elif x[0] == "ret":
            pend["ret"] = int(x[1]) | int(x[2]) << 8
        elif x[0] in ("isr", "m0", "m1", "m2", "main"):
            ev.append({"kind": x[0], "t": t_abs(x[1], x[2], machine), "frame": int(x[1]), **pend})
            pend = {}
        elif x[0] == "fast":
            ev.append({"kind": "fast", "t": t_abs(x[1], x[2], machine), "frame": int(x[1])})
    return f0, ev, s


def loops_of(ev, s, first=False):
    """the film cut into loops, each from its HALT's interrupt to the next
    HALT: when it woke, the interrupts during it, its marks"""
    loops = []
    cur = None
    for e in ev:
        if e["kind"] == "main":
            if cur is not None:
                cur["halt"] = e["t"]
                loops.append(cur)
            cur = {"isrs": [], "marks": {}}
        elif cur is None:
            continue
        elif e["kind"] == "isr":
            cur["isrs"].append(e)
        elif e["kind"] in MARKS:
            cur["marks"][e["kind"]] = e
        elif e["kind"] == "fast":
            cur.setdefault("fast", []).append(e)
    out = []
    for lp in loops:
        if not lp["isrs"] or "m0" not in lp["marks"]:
            continue
        wake = lp["isrs"][0]
        assert wake["ret"] == s["main"] + 1 or wake["ret"] == s["main"], (wake["ret"], s["main"])
        m1 = lp["marks"]["m1"]
        lp.update(wake=wake, steps=(m1["ticks"] - m1["last"]) & 0xFF,
                  inside=lp["isrs"][1:], att=lp["marks"]["m2" if first else "m1"]["att"],
                  regs=lp["marks"]["m2" if first else "m1"]["regs"])
        out.append(lp)
    return out


# ---------------------------------------------------------------- the model
def main_price(name, machine, frames, work, acc=0):
    """walk.py: from the instruction after HALT to HALT again, with FRAMES
    frames counted, the work WORK of the eight (fits.asm and misses.asm have
    one, the machine's) and, in speed.asm, ACC 256ths of a pixel left over"""
    wk = walker(name, 0x80 if machine == EU else 0x00)
    wk.run("init", "main")
    s = wk.sym
    wk.mem[s["last"]] = (wk.mem[s["ticks"]] - frames) & 0xFF
    wk.mem[s["k"]] = (work - 1) & 7
    wk.mem[s["acc"]], wk.mem[s["acc"] + 1] = acc & 0xFF, acc >> 8
    s["main.after"] = s["main"] + 1
    return wk.run("main.after", "main")


def walker(name, rate, status=0x80):
    wk = walk.Walk(HERE / name, read_port=lambda port, t: status if port == 0x99 else 0)
    wk.mem[0x2B] = rate
    return wk


def model(name, machine, loops):
    """loop by loop, from the T-state the debugger found it waking (HALT's
    step is read, not worked out: chapter 18): walk.py's price of the loop;
    each signal that rises before it is back at HALT is answered on the way;
    the next loop wakes at the first signal after its HALT"""
    out = []
    frames, work, acc, cache = 1, 0, 0, {}
    for lp in loops:
        frame = lp["wake"]["frame"]
        key = (frames, work, acc if name == "speed" else 0)
        if key not in cache:
            cache[key] = main_price(name, machine, *key)
        if name == "speed":
            k = gen33.SPEED_K[machine]
            whole, acc = divmod(acc + frames * k, 256)
        else:
            whole = 1 if name == "nocount" else frames
        end = lp["wake"]["t"] + ISR_T + cache[key]
        n, inside = frame + 1, 0
        while signal_of(n, machine) < end:      # a signal before HALT
            end += ANSWER + ISR_T
            inside += 1
            n += 1
        out.append({"frame": frame, "frames": frames, "pixels": whole,
                    "work": work, "inside": inside, "main": cache[key],
                    "next": n})
        frames = n - frame
        work = (work + 1) % 8
    return out


# ---------------------------------------------------------------- herd films
def herd_film(name, machine, frames=56, photos=True, fast_ok=False):
    f0, ev, s = film(name, machine, frames, fast_ok)
    first = name == "first"
    loops = loops_of(ev, s, first)
    pred = model(name, machine, loops)
    moved = 0
    rows = []
    for k, (lp, p) in enumerate(zip(loops, pred)):
        if k + 1 < len(loops):
            assert loops[k + 1]["wake"]["frame"] == p["next"], (name, machine, k, p)
        assert len(lp["inside"]) == p["inside"], (name, machine, p)
        assert name == "nocount" or lp["steps"] == p["frames"], (name, machine, lp["steps"], p)
        # the send shows the herd as the loops before this one left it; in
        # first.asm, as this one's logic leaves it
        want = gen33.herd_bytes(moved + (p["pixels"] if first else 0))
        wrong = sum(a != b for a, b in zip(lp["att"], want))
        assert first or wrong == 0, (name, machine, "the table sent")
        took = lp["halt"] - lp["wake"]["t"]
        assert took == ISR_T + p["main"] + (ANSWER + ISR_T) * p["inside"], (name, machine, took, p)
        nxt = signal_of(lp["wake"]["frame"] + 1, machine)
        rows.append({"frame": lp["wake"]["frame"] - f0, "pixels": p["pixels"],
                     "counted": p["frames"], "inside": len(lp["inside"]),
                     "wake": num(lp["wake"]["t"] - signal_of(lp["wake"]["frame"], machine)),
                     "send": [shows(lp["marks"]["m0"]["t"] + 8, machine)[1],
                              shows(lp["marks"]["m1" if not first else "m2"]["t"], machine)[1]],
                     "logic": shows(lp["marks"]["m1"]["t"] + 8, machine)[1],
                     "work_end": [shows(lp["marks"]["m2"]["t"] + 8, machine)[0] - lp["wake"]["frame"],
                                  shows(lp["marks"]["m2"]["t"] + 8, machine)[1]],
                     "halt_after_signal": num(lp["halt"] - nxt),
                     "interrupted": [i["ret"] for i in lp["inside"]],
                     "took": num(took), "moved_before": moved, "att": lp["att"], "wrong": wrong,
                     "fast": len(lp.get("fast", []))})
        moved += p["pixels"]
    out = {"f0": f0, "rows": rows, "ev": ev, "loops": loops}
    if photos:
        out["fit"], out["photos"] = herd_photos(name, machine, f0, ev, loops, first)
    return out


def herd_photos(name, machine, f0, ev, loops, first):
    """every frame from the first loop's to the last's, against the model:
    the herd the VRAM held when the frame's paper began, and the marks"""
    writes = [(e["t"] + 8, MARKS[e["kind"]]) for e in ev if e["kind"] in MARKS]
    sends = [(lp["marks"]["m1" if not first else "m2"]["t"], lp["att"]) for lp in loops]
    frames = list(range(loops[0]["wake"]["frame"] + 1, loops[-1]["wake"]["frame"]))
    models = {}
    for c in frames:
        start = c * FT[machine] + gen33.PAPER0[machine] * L
        end = start + 192 * L
        done = [a for t, a in sends if t < start]
        during = [a for t, a in sends if start <= t < end]
        if not done or during:
            continue            # a send while this paper is drawn: first.asm
        paper = vdpscreen.draw(vram_of(done[-1]), gen33.REGS)
        models[c] = capture_model(paper, writes, c, machine)
    shots = sorted({c - f0 + d for c in models for d in (-1, 0, 1)})
    pngs = msxcap.capture(rom(name), shots, CAPS, f"{name}_{TAG[machine]}_f", machine=machine)
    ph = {f: codes(pngs[f]) for f in shots}
    fits = [d for d in (-1, 0, 1) if all(mismatch(mo, ph[c - f0 + d]) == 0 for c, mo in models.items())]
    assert len(fits) == 1, (name, machine, fits)
    keep = {c - f0 + fits[0] for c in frames}
    for f in shots:
        if f not in keep:
            pngs[f].unlink()
    return fits[0], {c - f0 + fits[0]: ph[c - f0 + fits[0]] for c in models}


def summary(fl, machine):
    rows = fl["rows"]
    return {"loops": len(rows), "frames": rows[-1]["frame"] - rows[0]["frame"],
            "lost": sum(r["inside"] for r in rows),
            "counted": [r["counted"] for r in rows], "pixels": [r["pixels"] for r in rows],
            "inside": [r["inside"] for r in rows],
            "wake": sorted({r["wake"] for r in rows}), "send": sorted({tuple(r["send"]) for r in rows}),
            "logic": sorted({r["logic"] for r in rows}),
            "work_end": [r["work_end"] for r in rows[:8]], "took": [r["took"] for r in rows[:8]],
            "first_frame": rows[0]["frame"], "fit": fl.get("fit"), "shots": sorted(fl.get("photos", {}))}


def order():
    out = {}
    for m in (EU, JP):
        fl = herd_film("order", m)
        rows = fl["rows"]
        out[TAG[m]] = summary(fl, m)
        # a pixel a frame: the herd the last loop sent had moved a pixel for
        # every frame since the first loop's
        assert rows[-1]["moved_before"] == rows[-1]["frame"] - rows[0]["frame"]
        out[TAG[m]]["moved"] = rows[-1]["moved_before"]
        out[TAG[m]]["table"] = [{k: r[k] for k in ("frame", "counted", "inside", "work_end", "took")}
                                for r in rows[:10]]
    return out


def nocount():
    out = {}
    for m in (EU, JP):
        fl = herd_film("nocount", m)
        rows = fl["rows"]
        out[TAG[m]] = summary(fl, m)
        assert rows[-1]["moved_before"] == len(rows) - 1
        out[TAG[m]]["moved"] = rows[-1]["moved_before"]
    return out


def first():
    out = {}
    for m in (EU, JP):
        fl = herd_film("first", m, fast_ok=True)
        rows = fl["rows"]
        res = summary(fl, m)
        res.update(wrong=[r["wrong"] for r in rows], fast=[r["fast"] for r in rows],
                   send_lines=[r["send"] for r in rows],
                   table=[{k: r[k] for k in ("frame", "counted", "send", "fast", "wrong")} for r in rows[:9]])
        paper = (gen33.PAPER0[m], gen33.PAPER0[m] + 191)
        for r in rows:          # bytes go wrong exactly when the send meets the paper
            meets = r["send"][0] <= paper[1] and r["send"][1] >= paper[0]
            assert (r["wrong"] > 0) == meets == (r["fast"] > 0), (m, r["send"], r["wrong"], r["fast"])
        # the frame whose paper the send ran into: above the line where it
        # began, the herd the VDP held before it; below the line after its end,
        # the table as the debugger read it when the send was over, its lost
        # bytes and all; in between, the send
        torn = []
        prev = None
        for k, (r, lp) in enumerate(zip(rows, fl["loops"])):
            c = shows(lp["marks"]["m0"]["t"] + 8, m)[0]
            if r["wrong"] and prev is not None and c < fl["loops"][-1]["wake"]["frame"]:
                shot = c - fl["f0"] + fl["fit"]
                if shot not in fl["photos"]:
                    png = CAPS / f"first_{TAG[m]}_f{shot:04d}.png"
                    photo = codes(png)
                else:
                    photo = fl["photos"][shot]
                got = paper_of(photo)
                top, bottom = r["send"][0] - gen33.PAPER0[m], r["send"][1] - gen33.PAPER0[m] + 2
                old = vdpscreen.draw(vram_of(prev), gen33.REGS)
                new = vdpscreen.draw(vram_of(r["att"]), gen33.REGS)
                meant = vdpscreen.draw(vram_of(gen33.herd_bytes(r["moved_before"] + r["pixels"])),
                                       gen33.REGS)
                above = sum(1 for y in range(max(0, top)) for x in range(256) if got[y][x] != old[y][x])
                below = sum(1 for y in range(max(0, bottom), 192) for x in range(256) if got[y][x] != new[y][x])
                assert above == below == 0, (m, k, above, below)
                torn.append({"shot": shot, "send": r["send"], "wrong": r["wrong"], "fast": r["fast"],
                             "off": sum(1 for y in range(max(0, bottom), 192) for x in range(256)
                                        if got[y][x] != meant[y][x])})
            prev = r["att"]
        res["torn"] = torn
        out[TAG[m]] = res
    return out


def paper_of(photo):
    return [[photo[meas.PAPER_Y0 + y][meas.PAPER_X0 + x] for x in range(256)] for y in range(192)]


# ---------------------------------------------------------------- edge
def edge():
    out = {}
    s = {n: sym(n) for n in ("fits", "misses")}
    for name in ("fits", "misses"):
        out[name] = {}
        for m in (EU, JP):
            fl = herd_film(name, m, frames=24, photos=False)
            rows = fl["rows"]
            res = {"turns": gen33.edge_turns(m) + (name == "misses"),
                   "loops": len(rows), "frames": rows[-1]["frame"] - rows[0]["frame"],
                   "counted": [r["counted"] for r in rows],
                   "halt_after_signal": [r["halt_after_signal"] for r in rows],
                   "wake": [r["wake"] for r in rows], "took": [r["took"] for r in rows],
                   "interrupted": sorted({a for r in rows for a in r["interrupted"]})}
            if name == "fits":
                assert all(r["counted"] == 1 and r["halt_after_signal"] < 0 for r in rows), m
            else:
                assert rows[0]["interrupted"] == [s[name]["main"]]      # the first: just before HALT
                assert all(r["counted"] == 2 for r in rows[1:]), m
            out[name][TAG[m]] = res
    return out


# ---------------------------------------------------------------- speed
def speed():
    out = {}
    for m in (EU, JP):
        fl = herd_film("speed", m)
        rows = fl["rows"]
        res = summary(fl, m)
        frames = rows[-1]["frame"] - rows[0]["frame"]
        moved = rows[-1]["moved_before"]
        res.update(moved=moved, film_frames=frames,
                   per_second=round(moved * CLOCK / (frames * FT[m]), 2),
                   order_per_second=round(CLOCK / FT[m], 3),
                   k=gen33.SPEED_K[m], k_per_second=round(gen33.SPEED_K[m] / 256 * CLOCK / FT[m], 2))
        out[TAG[m]] = res
    return out


CLOCK = gen33.CLOCK


# ---------------------------------------------------------------- seconds
SECONDS_FRAMES = {EU: 30110, JP: 36010}     # both clocks to their 600th second, after INIT


def seconds():
    out = {}
    s = sym("seconds")
    for m in (EU, JP):
        tcl = (f'debug set_bp {s["isr"]} {{}} {{ if {{![info exists ::t0]}} {{ set ::t0 1; '
               f'L "start {POS} [machine_info time]" }} }}\n'
               f'debug set_bp {s["isr.t17"]} {{}} {{ L "t17 [reg hl] {POS} [machine_info time]" }}\n'
               f'debug set_bp {s["isr.tk"]} {{}} {{ L "tk [reg hl] {POS} [machine_info time]" }}\n')
        w = run("seconds", SECONDS_FRAMES[m], tcl, m)
        start = next(x for x in w if x[0] == "start")
        c0 = int(start[1])
        ticks = {k: [(int(x[1]), int(x[2]) - c0 + 1, float(x[4]) - float(start[3])) for x in w if x[0] == k]
                 for k in ("t17", "tk")}
        per, full = gen33.PER[m]
        rate = 50 if m == EU else 60
        # the clocks against the frames: second k of each comes at frame
        # rate x k, and at the first frame whose shares reach k x FULL
        assert [(sec, n) for sec, n, _ in ticks["t17"]] == [(k, rate * k) for k in range(1, len(ticks["t17"]) + 1)]
        assert [(sec, n) for sec, n, _ in ticks["tk"]] == \
            [(k, -(-k * full // per)) for k in range(1, len(ticks["tk"]) + 1)]
        # and against openMSX's clock: the true time of each second's frame,
        # from a frame before the first
        frame_s = FT[m] / CLOCK
        late = [t + frame_s - k for k, (sec, n, t) in enumerate(ticks["tk"], 1)]
        late17 = [t + frame_s - k for k, (sec, n, t) in enumerate(ticks["t17"], 1)]
        k600 = 600
        out[TAG[m]] = {"frames": SECONDS_FRAMES[m], "kept": len(ticks["tk"]), "ch17": len(ticks["t17"]),
                       "kept_late": [round(min(late), 4), round(max(late), 4)],
                       "ch17_at_600": round(late17[k600 - 1], 3) if len(late17) >= k600 else None,
                       "ch17_frame_600": rate * k600, "kept_frame_600": -(-k600 * full // per),
                       "frame_s": round(frame_s, 7),
                       "true_at_kept_600": round(ticks["tk"][k600 - 1][2] + frame_s, 4),
                       "true_at_ch17_600": round(ticks["t17"][k600 - 1][2] + frame_s, 4),
                       "per": per, "full": full,
                       "ch17_when_kept_600": max(sec for sec, n, _ in ticks["t17"] if n <= -(-k600 * full // per))}
        # openMSX's clock at each second is the frames' T-states, to within the
        # breakpoint's place in isr and the HALT's step: well under a millisecond
        for k, (sec, n, t) in enumerate(ticks["tk"], 1):
            assert abs(t + frame_s - n * frame_s) < 1e-4, (m, k, t, n)
        assert 0 <= min(late), (m, min(late))
    # the screen: the frames and the two clocks printed, a few seconds in
    out["photo"] = seconds_photo()
    return out


SECONDS_SHOT = 300


def seconds_photo():
    out = {}
    s = sym("seconds")
    for m in (EU, JP):
        tcl = (f'debug set_bp {s["main"]} {{}} {{ L "v {POS} [debug read memory {s["frames"]}] '
               f'[debug read memory {s["frames"] + 1}] [debug read memory {s["secs17"]}] '
               f'[debug read memory {s["secs17"] + 1}] [debug read memory {s["secs"]}] '
               f'[debug read memory {s["secs"] + 1}]" }}\n')
        w = run("seconds", SECONDS_SHOT + 4, tcl, m)
        f0 = int(next(x for x in w if x[0] == "f0")[1])
        vals = {}
        for x in w:
            if x[0] == "v":
                b = [int(v) for v in x[3:]]
                vals[int(x[1]) - f0] = (b[0] | b[1] << 8, b[2] | b[3] << 8, b[4] | b[5] << 8)
        shots = [SECONDS_SHOT + d for d in (-1, 0, 1)]
        pngs = msxcap.capture(rom("seconds"), shots, CAPS, f"seconds_{TAG[m]}_f", machine=m)
        ph = {f: codes(pngs[f]) for f in shots}
        fits = []
        for d in (-1, 0, 1):
            # the numbers printed after the frame's interrupt show in the next paper
            v = vals.get(SECONDS_SHOT - d - 1)
            if v and mismatch(seconds_model(v), ph[SECONDS_SHOT]) == 0:
                fits.append(d)
        assert len(fits) == 1, (m, fits)
        for f in shots:
            if f != SECONDS_SHOT:
                pngs[f].unlink()
        out[TAG[m]] = {"shot": SECONDS_SHOT, "values": vals[SECONDS_SHOT - fits[0] - 1], "fit": fits[0]}
    return out


def seconds_model(values):
    names = gen33.text_names()
    for (row, _), v in zip(gen33.TEXT_ROWS, values):
        for i, ch in enumerate(f"{v:05d}"):
            names[32 * row + gen33.NUM_COL + i] = ord(ch)
    v = bytearray(16384)
    v[0x100:0x400] = gen33.FONT
    v[0x1800:0x1B00] = bytes(names)
    v[0x2000:0x2020] = bytes([0x1F]) * 32
    v[0x1B00] = 0xD0
    paper = vdpscreen.draw(v, gen33.TEXT_REGS)
    return [[(paper[y - meas.PAPER_Y0][x - meas.PAPER_X0]
              if 0 <= x - meas.PAPER_X0 < 256 and 0 <= y - meas.PAPER_Y0 < 192 else 15)
             if meas.DRAWN[0] <= x <= meas.DRAWN[1] else None
             for x in range(meas.CAPTURE_W)] for y in range(meas.CAPTURE_H)]


# ---------------------------------------------------------------- answers etc
def prices():
    out = {}
    wk = walker("order", 0x80)
    wk.run("init", "main")
    out["isr"] = wk.call("isr") - 18
    assert out["isr"] == ISR_T
    out["step"] = walker("order", 0x80).call("step") - 18
    # order.asm's loop, a part at a time, one frame counted and the first work
    wk = walker("order", 0x80)
    wk.run("init", "main")
    s = wk.sym
    wk.mem[s["last"]] = (wk.mem[s["ticks"]] - 1) & 0xFF
    wk.mem[s["k"]] = 7
    s["main.after"] = s["main"] + 1
    parts = [("main.after", "m0"), ("m0", "s1"), ("s1", "m1"), ("m1", "m2"), ("m2", "main")]
    out["parts"] = {f"{a}-{b}": wk.run(a, b) for a, b in parts}
    # the logic's own parts: the count, a step with its PUSH, CALL, POP and
    # DJNZ, and the choice of the work, without the work's turns
    wk = walker("order", 0x80)
    wk.run("init", "main")
    wk.mem[s["last"]] = (wk.mem[s["ticks"]] - 1) & 0xFF
    wk.mem[s["k"]] = 7
    out["logic_to_work"] = wk.run("m1", "m1.work")
    assert out["logic_to_work"] + 30 * gen33.WORKS[0] - 5 + 33 == out["parts"]["m1-m2"]
    for m in (EU, JP):
        out[TAG[m]] = {f"{f}_{w}": main_price("order", m, f, w) for f in (1, 2) for w in range(8)}
    loop0 = ANSWER + ISR_T + main_price("fits", EU, 1, 0) - 30 * gen33.edge_turns(EU)
    assert loop0 == gen33.LOOP_T, loop0
    out["loop_t"] = loop0
    return out


def answers():
    m = json.loads((HERE / "meas33.json").read_text())
    pr = m["prices"]
    out = {}
    # 1: the heartbeat's share of a frame
    beat = ANSWER + ISR_T
    out["q1"] = {"t": beat, "eu": round(100 * beat / FT[EU], 2), "jp": round(100 * beat / FT[JP], 2)}
    # 2: which of order.asm's eight works lose a frame, by walk.py's prices: the
    # loop from the answer to HALT against the frame, less the HALT's step
    out["q2"] = {}
    for m_ in (EU, JP):
        loops = {w: ANSWER + ISR_T + pr[TAG[m_]][f"1_{w}"] for w in range(8)}
        out["q2"][TAG[m_]] = {"loops": loops, "lose": [w for w, t in loops.items() if t > FT[m_]]}
    assert out["q2"]["eu"]["lose"] == [7] and out["q2"]["jp"]["lose"] == [5, 7]
    # 3: fits.asm's loop and the frame, modulo the HALT's step
    fe = m["edge"]["fits"]
    out["q3"] = {t: {"loop": ANSWER + fe[t]["took"][0], "short": FT[mm] - ANSWER - fe[t]["took"][0],
                     "mod5": (FT[mm] - ANSWER - fe[t]["took"][0]) % 5}
                 for t, mm in (("eu", EU), ("jp", JP))}
    # 4: misses.asm after its first loop
    me = m["edge"]["misses"]
    out["q4"] = {t: {"frames_a_loop": 2, "pixels": sorted(set(me[t]["counted"][1:])),
                     "pictures_s": round(CLOCK / FT[mm] / 2, 2)} for t, mm in (("eu", EU), ("jp", JP))}
    # 5: nocount.asm at 60 Hz against order.asm
    o, n = m["order"]["jp"], m["nocount"]["jp"]
    out["q5"] = {"behind": o["moved"] - n["moved"], "frames": o["frames"],
                 "px_s": round(n["moved"] / o["frames"] * CLOCK / FT[JP], 1)}
    # 6: speed.asm's 256ths for exactly 60 pixels a second at 50 Hz
    exact = 60 * 256 * FT[EU] / CLOCK
    out["q6"] = {"exact": round(exact, 2), "k": gen33.SPEED_K[EU],
                 "px_s": round(gen33.SPEED_K[EU] / 256 * CLOCK / FT[EU], 2)}
    # 7: the two clocks an hour in, by openMSX's time
    out["q7"] = {}
    for t, mm, rate in (("eu", EU, 50), ("jp", JP, 60)):
        per, full = gen33.PER[mm]
        n = -(-3600 * CLOCK // FT[mm])
        out["q7"][t] = {"frames": n, "ch17": n // rate, "kept": n * per // full}
    # 8: the works whose send, in first.asm, runs into the paper
    out["q8"] = {}
    for t, mm in (("eu", EU), ("jp", JP)):
        f = m["first"][t]
        paper = (gen33.PAPER0[mm], gen33.PAPER0[mm] + 191)
        hit = sorted({k % 8 for k, (a, b) in enumerate(f["send_lines"]) if a <= paper[1] and b >= paper[0]})
        out["q8"][t] = hit
    # 9: fits.asm's 60 Hz turns on the 50 Hz machine: the loop and what it leaves
    loop60 = gen33.LOOP_T + gen33.EDGE_TURN * gen33.edge_turns(JP)
    out["q9"] = {"loop": loop60, "spare": FT[EU] - loop60, "part": round(100 * (FT[EU] - loop60) / FT[EU], 1)}
    # 11: the herd back where it began: X is a byte
    assert gen33.herd_bytes(256) == gen33.herd_bytes(0) and gen33.herd_bytes(128) != gen33.herd_bytes(0)
    out["q11"] = {"frames": 256, "eu_s": round(256 * FT[EU] / CLOCK, 2), "jp_s": round(256 * FT[JP] / CLOCK, 2)}
    # 12: first.asm at 60 Hz, the work of 78,000: where its send begins, and what it loses
    f = m["first"]["jp"]
    k = next(k for k in range(len(f["send_lines"])) if k % 8 == 7)
    out["q12"] = {"send": f["send_lines"][k], "fast": f["fast"][k], "wrong": f["wrong"][k]}
    return out


OPENMSX_SECTIONS = ["order", "nocount", "edge", "speed", "seconds", "first"]


def openmsx():
    if not versions.builds():
        return {"skipped": "OPENMSX_BUILDS not set"}
    return versions.every_build(["ch33"], OPENMSX_SECTIONS)


SECTIONS = {"order": order, "nocount": nocount, "edge": edge, "speed": speed, "seconds": seconds,
            "first": first, "prices": prices, "answers": answers, "openmsx": openmsx}


def main(names=()):
    CAPS.mkdir(exist_ok=True)
    path = HERE / "meas33.json"
    m = json.loads(path.read_text()) if names and path.exists() else {}
    for name in names or SECTIONS:
        print(name, flush=True)
        m[name] = SECTIONS[name]()
        m = {k: m[k] for k in SECTIONS if k in m}
        path.write_text(json.dumps(m, indent=1) + "\n")
    return m


if __name__ == "__main__":
    main(sys.argv[1:])
