#!/usr/bin/env python3
"""meas31.py -- fast transfers to VRAM, measured.

    python3 gen31.py && ./build.sh && python3 meas31.py
                                  python3 meas31.py otir chain     only these

Every frame of every film, on both machines: the VRAM and the registers the
debugger reads, held against gen31.py's model, byte for byte; the photograph
of the frame after, vdpscreen.py's drawing of them (paper.asm's are checked
at the end only: it writes while the paper is drawn); the line where each
burst starts and ends; and openMSX's callback for a VRAM access too soon,
which must never fire but in fixed.asm.

  blank     blank.rom: the picture with the display off
  otir      otir.rom: OTIR after the paper (figure 31.1)
  chain     chain.rom: OUTIs in a row after the paper
  paper     paper.rom: and OUTI with JP NZ while the paper is drawn
  any       any.rom: OUTIs in a row for any count, a jump into the chain
  fill      fill.rom: OUT (C),A in a row, the display off and after the paper
  irq       halt.rom and hook.rom: the bursts with the BIOS's interrupt
  double    double.rom: a new screen every frame, two name tables (figure 31.3)
  fixed     WHERE IT BREAKS: fixed.rom (figure 31.4)
  prices    walk.py's T-states for a block of each kind and for the bursts
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
import meas        # noqa: E402
import msxcap      # noqa: E402
import probe as dbg  # noqa: E402
import versions    # noqa: E402
import vdpslots    # noqa: E402  (chapter 20)
sys.path.insert(0, str(HERE))
import gen31       # noqa: E402
sys.path.remove(str(HERE))
sys.path.insert(0, str(HERE))      # gen31 put chapters 24 and 26 first: this folder's files win
for mod in ("vdpscreen", "walk"):
    sys.modules.pop(mod, None)
import vdpscreen   # noqa: E402
import walk        # noqa: E402  (chapter 30's)

assert Path(vdpscreen.__file__).parent == HERE and Path(walk.__file__).parent == HERE

CAPS = HERE / "captures"
EU, JP = gen31.EU, gen31.JP
TAG = {EU: "eu", JP: "jp"}
CLOCK = 3579545
POS = "[machine_info VDP_frame_count] [machine_info VDP_cycle_in_frame] [machine_info time]"
REGS = " ".join(f"[debug read {{VDP regs}} {i}]" for i in range(8))
VRAM = 'binary scan [debug read_block {VRAM} 0 16384] H* h; L "vram $h"'
F0 = 'L "f0 [machine_info VDP_frame_count]"\n'
TOO_FAST = ('proc ::toofast_cb {args} { L "fast [machine_info time]" }\n'
            'set VDP.too_fast_vram_access_callback ::toofast_cb\n')
PAPER0 = {EU: 69, JP: 42}               # the first line of the paper (chapter 18)

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
    bad = 0
    for y in range(240):
        for x in range(meas.DRAWN[0], meas.DRAWN[1] + 1):
            px, py = x - meas.PAPER_X0, y - meas.PAPER_Y0
            want = model[py][px] if 0 <= px < 256 and 0 <= py < 192 else backdrop
            bad += photo[y][x] != want
    return bad


def paper_of(photo):
    return [[photo[meas.PAPER_Y0 + y][meas.PAPER_X0 + x] for x in range(256)] for y in range(192)]


def once(addr, body, tag):
    return f'set ::{tag} [debug set_bp {addr} {{}} {{ {body}; debug remove_bp $::{tag} }}]\n'


def run(name, frames, tcl, machine, fast_ok=False):
    lines = msxcap.run_tcl(rom(name), frames, F0 + TOO_FAST + tcl, machine=machine)
    w = [l.split() for l in lines]
    fast = [x for x in w if x[0] == "fast"]
    assert fast_ok or not fast, (name, machine, "an access too soon")
    return w


PIC_SPANS = [(0, 0x1800), (0x1800, 0x1B01), (0x2000, 0x3800)]


def differ(vram, want, spans=PIC_SPANS):
    return sum(1 for a, b in spans for i in range(a, b) if vram[i] != want[i])


# ---------------------------------------------------------------- films
def film(name, machine, photos=True, fast_ok=False, marks=("m0", "m1", "s1"), mid=None, irq=False,
         frames=60):
    """every frame of a picture program: the VRAM at m0 (the last frame's
    work done), the T-states between the marks and their lines"""
    s = sym(name)
    read = f'L "regs {REGS}"; {VRAM}'
    tcl = f'debug set_bp {s[marks[0]]} {{}} {{ {read}; L "{marks[0]} {POS}" }}\n'
    for mk in marks[1:]:
        extra = f'{VRAM.replace("vram", "mid")}; ' if mk == mid else ""
        tcl += f'debug set_bp {s[mk]} {{}} {{ {extra}L "{mk} {POS}" }}\n'
    if irq:
        tcl += f'debug set_bp 0x0038 {{}} {{ L "irq {POS}" }}\n'
    tcl += once(s["done"], f'{read}; L "end {POS}"', "e")
    w = run(name, frames, tcl, machine, fast_ok)
    f0 = int(next(x for x in w if x[0] == "f0")[1])
    fast = [float(x[1]) for x in w if x[0] == "fast"]
    events, pend = [], {}           # each mark with the reads its breakpoint made
    for x in w:
        if x[0] == "regs":
            pend["regs"] = [int(v) for v in x[1:]]
        elif x[0] in ("vram", "mid"):
            pend[x[0]] = bytes.fromhex(x[1])
        elif x[0] in marks or x[0] in ("end", "irq"):
            events.append((x, pend))
            pend = {}
    if irq:
        # the breakpoint after a HALT is met while the CPU halts, too: the
        # burst's is the one a burst's end follows
        kinds = [x[0] for x, _ in events if x[0] in ("irq", marks[0], marks[1])]
        keep, k = [], 0
        for x, rd in events:
            if x[0] in ("irq", marks[0], marks[1]):
                nxt = kinds[k + 1] if k + 1 < len(kinds) else None
                k += 1
                if x[0] == marks[0] and nxt != marks[1]:
                    continue
            keep.append((x, rd))
        events = keep
    at = {mk: [x for x, _ in events if x[0] == mk] for mk in marks}
    reads = [rd for x, rd in events if x[0] in (marks[0], "end")][1:]
    regs = [rd["regs"] for rd in reads]
    vrams = [rd["vram"] for rd in reads]
    n = len(at[marks[0]])
    assert all(len(v) == n for v in at.values()) and len(regs) == len(vrams) == n, (name, machine)
    frames_at = [int(x[1]) - f0 for x in at[marks[0]]]
    assert irq or frames_at == list(range(frames_at[0], frames_at[0] + n)), (name, machine)
    lines = {mk: [int(x[2]) // vdpslots.LINE + (int(x[1]) - int(a[1])) * vdpslots.LINES[machine]
                  for a, x in zip(at[marks[0]], v)] for mk, v in at.items()}
    t = {f"{a}-{b}": [round((float(y[3]) - float(x[3])) * CLOCK) for x, y in zip(at[a], at[b])]
         for a, b in zip(marks, marks[1:])}
    out = {"frames": [f + 1 for f in frames_at], "t": t, "lines": lines, "fast": len(fast),
           "regs": regs, "vrams": vrams, "f0": f0, "fast_at": fast, "at": at,
           "mids": [rd["mid"] for x, rd in events if x[0] == mid]}
    if irq:
        out["irq"] = [x for x, _ in events if x[0] == "irq"]
    if photos:
        shots = sorted({f + d for f in frames_at for d in (0, 1, 2)})
        pngs = msxcap.capture(rom(name), shots, CAPS, f"{name}_{TAG[machine]}_f", machine=machine)
        ph = {f: codes(pngs[f]) for f in shots}
        fits = [d for d in (0, 1, 2)
                if all(against(vdpscreen.draw(v, r), ph[f + d], r[7] & 15) == 0
                       for v, r, f in zip(vrams, regs, frames_at))]
        for f in shots:
            if f not in {f + 1 for f in frames_at}:
                pngs[f].unlink()
        out["fits"] = fits
        out["photos"] = {f + 1: ph[f + 1] for f in frames_at}
    return out


def last_photo(name, machine, frame):
    png = msxcap.capture(rom(name), [frame], CAPS, f"{name}_{TAG[machine]}_f", machine=machine)[frame]
    return codes(png)


def picture(kind):
    def go():
        out = {}
        for m in (EU, JP):
            paper = kind == "paper"
            fl = film(kind, m, photos=True, marks=("m0", "m1", "s1"), mid="m1" if paper else None)
            want = gen31.frames_of(kind, m)
            assert len(fl["vrams"]) == len(want), (kind, m, len(fl["vrams"]), len(want))
            bad = [differ(v, gen31.vram_of(d)) + (r != gen31.REGS_PIC)
                   for v, r, d in zip(fl["vrams"], fl["regs"], want)]
            assert not any(bad), (kind, m, bad)
            mixed = None
            if paper:
                last = fl["frames"][-1] + 2
                ph = last_photo(kind, m, last)
                assert against(vdpscreen.draw(fl["vrams"][-1], fl["regs"][-1]), ph, 15) == 0
                # the frame whose paper paper.asm writes into: the photograph
                # against the VRAM before those blocks and after them
                mixed = []
                for k, f in enumerate(fl["frames"]):
                    if k + 1 >= len(fl["mids"]):
                        break
                    before, after_ = fl["mids"][k + 1], fl["vrams"][k + 1]
                    pp = paper_of(fl["photos"][f + 1]) if f + 1 in fl["photos"] else \
                        paper_of(last_photo(kind, m, f + 1))
                    b = vdpscreen.draw(before, gen31.REGS_PIC)
                    a = vdpscreen.draw(after_, gen31.REGS_PIC)
                    mixed.append({"frame": f + 1,
                                  "old": sum(1 for y in range(192) for x in range(256)
                                             if pp[y][x] == b[y][x] != a[y][x]),
                                  "new": sum(1 for y in range(192) for x in range(256)
                                             if pp[y][x] == a[y][x] != b[y][x]),
                                  "other": sum(1 for y in range(192) for x in range(256)
                                               if pp[y][x] != a[y][x] and pp[y][x] != b[y][x])})
            else:
                assert 1 in fl["fits"], (kind, m, fl["fits"])
            ends = fl["lines"]["m1"]
            after = [e - vdpslots.LINES[m] for e in ends]          # in the next frame
            full = [d - p for d, p in zip(want, [0] + want[:-1])]
            out[TAG[m]] = {"frames": fl["frames"], "blocks": full, "sent": want,
                           "after": fl["t"]["m0-m1"], "during": fl["t"]["m1-s1"],
                           "start": sorted(set(fl["lines"]["m0"])),
                           "end_line": max(after[:-1]) if len(after) > 1 else after[0],
                           "margin": PAPER0[m] - max(after),
                           "end_during": max(fl["lines"]["s1"]) - vdpslots.LINES[m],
                           "fits": fl.get("fits"), "mixed": mixed}
            assert out[TAG[m]]["margin"] > 0, (kind, m, "the burst ran into the paper")
            if paper:
                assert out[TAG[m]]["end_during"] < PAPER0[m] + 192, (m, "past the paper")
        return out
    return go


# ---------------------------------------------------------------- blank
def blank():
    out = {}
    for m in (EU, JP):
        s = sym("blank")
        tcl = (once(s["c0"], f'L "c0 {POS}"', "c0") + once(s["c1"], f'L "c1 {POS}"', "c1") +
               once(s["done"], f'L "regs {REGS}"; {VRAM}; L "end {POS}"', "d"))
        w = run("blank", 40, tcl, m)
        f0 = int(next(x for x in w if x[0] == "f0")[1])
        c0, c1, end = (next(x for x in w if x[0] == k) for k in ("c0", "c1", "end"))
        regs = [int(v) for v in next(x for x in w if x[0] == "regs")[1:]]
        vram = bytes.fromhex(next(x for x in w if x[0] == "vram")[1])
        assert regs == gen31.REGS_PIC and differ(vram, gen31.vram_of(96)) == 0, m
        shot = int(end[1]) - f0 + 2
        ph = last_photo("blank", m, shot)
        assert against(vdpscreen.draw(vram, regs), ph, 15) == 0
        out[TAG[m]] = {"t": round((float(c1[3]) - float(c0[3])) * CLOCK),
                       "frames_off": int(c1[1]) - int(c0[1]), "shot": shot}
    return out


# ---------------------------------------------------------------- any
def any_():
    out = {}
    labels = [f"a{i}" for i in range(len(gen31.ANY) + 1)]
    for m in (EU, JP):
        s = sym("any")
        tcl = "".join(once(s[l], f'L "{l} {POS}"', l) for l in labels)
        tcl += once(s["done"], f'L "regs {REGS}"; {VRAM}; L "end {POS}"', "d")
        w = run("any", 40, tcl, m)
        f0 = int(next(x for x in w if x[0] == "f0")[1])
        at = {x[0]: float(x[3]) for x in w if x[0] in labels}
        regs = [int(v) for v in next(x for x in w if x[0] == "regs")[1:]]
        vram = bytes.fromhex(next(x for x in w if x[0] == "vram")[1])
        assert regs == gen31.REGS_PIC and differ(vram, gen31.vram_of(2)) == 0, m
        end = next(x for x in w if x[0] == "end")
        ph = last_photo("any", m, int(end[1]) - f0 + 2)
        assert against(vdpscreen.draw(vram, regs), ph, 15) == 0
        # each call: from its CALL to the next count's LD A,n (8 T-states) and
        # its CALL, or to the label after the last
        out[TAG[m]] = [round((at[b] - at[a]) * CLOCK) - (8 if k < len(labels) - 2 else 0)
                       for k, (a, b) in enumerate(zip(labels, labels[1:]))]
    out["counts"] = gen31.ANY
    return out


# ---------------------------------------------------------------- fill
def fill():
    out = {}
    for m in (EU, JP):
        s = sym("fill")
        fl = film("fill", m)
        want = gen31.frames_of("fill", m)
        assert len(fl["vrams"]) == len(want), (m, len(fl["vrams"]))
        bad = [differ(v, gen31.vram_of(0, d)) + (r != gen31.REGS_PIC)
               for v, r, d in zip(fl["vrams"], fl["regs"], want)]
        assert not any(bad), (m, bad)
        assert 1 in fl["fits"], fl["fits"]
        ends = [e - vdpslots.LINES[m] for e in fl["lines"]["m1"]]
        w = run("fill", 40, once(s["c0"], f'L "c0 {POS}"', "c0") + once(s["c1"], f'L "c1 {POS}"', "c1"), m)
        c0, c1 = (float(next(x for x in w if x[0] == k)[3]) for k in ("c0", "c1"))
        out[TAG[m]] = {"frames": fl["frames"], "after": fl["t"]["m0-m1"], "sent": want,
                       "start": sorted(set(fl["lines"]["m0"])),
                       "margin": PAPER0[m] - max(ends), "end_line": max(ends[:-1]),
                       "clear": round((c1 - c0) * CLOCK)}
        assert out[TAG[m]]["margin"] > 0
    return out


# ---------------------------------------------------------------- irq
def irq():
    out = {}
    for name in ("halt", "hook"):
        out[name] = {}
        for m in (EU, JP):
            fl = film(name, m, photos=False, fast_ok=True, marks=("m0", "m1"), irq=True, frames=260)
            want = gen31.frames_of(name, m)
            n = len(fl["vrams"])
            # the interrupt before each burst, and the T-states from it to the burst
            irqs = fl["irq"]
            starts, start_lines, ends, end_t = [], [], [], []
            for a, b in zip(fl["at"]["m0"], fl["at"]["m1"]):
                prev = [x for x in irqs if float(x[3]) <= float(a[3])][-1]
                starts.append(round((float(a[3]) - float(prev[3])) * CLOCK))

                def line(x):        # counted from the interrupt's frame
                    return int(x[2]) // vdpslots.LINE + (int(x[1]) - int(prev[1])) * vdpslots.LINES[m]
                start_lines.append(line(a))
                ends.append(line(b) - vdpslots.LINES[m])
                end_t.append(round(int(b[2]) % vdpslots.LINE / 6))
            wrong = [differ(v, gen31.vram_of(d)) for v, d in zip(fl["vrams"], want)]
            fast_frames = sorted({int(x[1]) for x in fl["at"]["m0"]
                                  if any(float(x[3]) <= ft < float(x[3]) + 0.02 for ft in fl["fast_at"])})
            last = int(fl["at"]["m1"][-1][1]) - fl["f0"] + 3
            ph = last_photo(name, m, last)
            assert against(vdpscreen.draw(fl["vrams"][-1], fl["regs"][-1]), ph, 15) == 0
            ideal = vdpscreen.draw(gen31.vram_of(96), gen31.REGS_PIC)
            pp = paper_of(ph)
            off = sum(1 for y in range(192) for x in range(256) if pp[y][x] != ideal[y][x])
            out[name][TAG[m]] = {"shot": last, "off": off,
                                 "bursts": n, "isr_to_burst": starts, "end_lines": ends,
                                 "fast": fl["fast"], "wrong": wrong, "into_paper":
                                 sum(1 for e in ends if e >= PAPER0[m]),
                                 "start_lines": start_lines, "end_t_in_line": end_t}
    return out


# ---------------------------------------------------------------- double
def double():
    out = {}
    for m in (EU, JP):
        fl = film("double", m, marks=("m0", "m1", "w0", "w1"))
        n = len(fl["vrams"])
        assert n == gen31.DOUBLE_FRAMES, n
        spans = [(0, 8 * len(gen31.gen24.TILES)), (0x2000, 0x2000 + 8 * len(gen31.gen24.TILES)),
                 (0x1B00, 0x1B01)]
        bad = []
        for k, (v, r) in enumerate(zip(fl["vrams"], fl["regs"])):
            want = gen31.double_vram(k)
            t = (0x1800, 0x1C00)[gen31.double_shown(k)]
            bad.append(differ(v, want, spans + [(t, t + 768)]) + (r != gen31.double_regs(k)))
        assert not any(bad), (m, bad[:6])
        assert 1 in fl["fits"], fl["fits"]
        # every photograph a whole window: none of it the window before
        torn = 0
        for k, f in enumerate(fl["frames"]):
            ideal = vdpscreen.draw(gen31.double_vram(k), gen31.double_regs(k))
            pp = paper_of(fl["photos"][f])
            torn += any(pp[y][x] != ideal[y][x] for y in range(192) for x in range(256))
        out[TAG[m]] = {"frames": fl["frames"], "show": fl["t"]["m0-m1"], "write": fl["t"]["w0-w1"],
                       "write_start": sorted(set(l - vdpslots.LINES[m] - PAPER0[m] for l in fl["lines"]["w0"])),
                       "write_end": sorted(set(l - vdpslots.LINES[m] - PAPER0[m] for l in fl["lines"]["w1"])),
                       "torn": torn}
    return out


# ---------------------------------------------------------------- fixed
def fixed():
    out = {}
    for m in (EU, JP):
        fl = film("fixed", m, photos=False, fast_ok=True)
        want = gen31.frames_of("fixed", m)
        wrong = [differ(v, gen31.vram_of(d)) for v, d in zip(fl["vrams"], want)]
        last = fl["frames"][-1] + 2
        ph = paper_of(last_photo("fixed", m, last))
        ideal = vdpscreen.draw(gen31.vram_of(96), gen31.REGS_PIC)
        assert against(vdpscreen.draw(fl["vrams"][-1], fl["regs"][-1]), last_photo("fixed", m, last), 15) == 0
        off = sum(1 for y in range(192) for x in range(256) if ph[y][x] != ideal[y][x])
        after = [e - vdpslots.LINES[m] for e in fl["lines"]["m1"]]
        out[TAG[m]] = {"frames": fl["frames"], "fast": fl["fast"], "wrong": wrong,
                       "wrong_end": wrong[-1], "off": off, "shot": last,
                       "end_line": max(after[:-1]), "after": fl["t"]["m0-m1"]}
    return out


# ---------------------------------------------------------------- prices
def prices():
    m = json.loads((HERE / "meas31.json").read_text())
    out = {}
    for kind, send in (("otir", "otir128"), ("chain", "chain128"), ("paper", "loop128"),
                       ("fill", "out128")):
        out[send] = walk.Walk(HERE / kind).call(send, h=0x40, l=0)
    out["outis"] = [walk.Walk(HERE / "any").call("outis", a=n, h=0x40, l=0) for n in gen31.ANY]
    assert out["outis"] == m["any"]["eu"] == m["any"]["jp"], (out["outis"], m["any"])
    for kind in ("otir", "chain", "paper"):
        out[kind] = {}
        for t, mach in (("eu", EU), ("jp", JP)):
            wk = walk.Walk(HERE / kind, read_port=lambda port, tt: 0x80 if port == 0x99 else 0)
            if mach == JP:
                wk.mem[0x2B] = 0x00
            else:
                wk.mem[0x2B] = 0x80
            wk.run("init", "m0")
            bursts, during = [], []
            while True:
                bursts.append(wk.run("m0", "m1"))
                during.append(wk.run("m1", "s1"))
                if wk.mem[0xC100] == 96:
                    break
                wk.run("s1", "m0")
            out[kind][t] = {"after": bursts, "during": during}
            assert bursts == m[kind][t]["after"] and during == m[kind][t]["during"], (kind, t)
    wk = walk.Walk(HERE / "blank")
    wk.run("init", "c0")
    out["blank"] = wk.run("c0", "c1")
    assert out["blank"] == m["blank"]["eu"]["t"] == m["blank"]["jp"]["t"]
    return out


# ---------------------------------------------------------------- answers
def answers():
    m = json.loads((HERE / "meas31.json").read_text())
    pr = m["prices"]
    out = {}
    # 1: a 60 Hz frame's lines not drawn, by the price of a byte alone
    out["q1"] = {"otir": 15960 // 23, "chain": 15960 // 18, "eu_otir": 27588 // 23, "eu_chain": 27588 // 18}
    # 2: the sprites' 128 bytes of attributes every frame, with OTIR
    out["q2"] = {"t": 127 * 23 + 18, "left_jp": 15960 - (127 * 23 + 18)}
    # 3: the picture with OTIR and the display off: frames at 60 Hz
    out["q3"] = {"t": 96 * (127 * 23 + 18), "frames_jp": 96 * (127 * 23 + 18) / 59736}
    # 4: double.asm's 768 names at 29 T-states: the part of a 60 Hz frame
    out["q4"] = {"t": 768 * 29, "part": 768 * 29 / 59736}
    # 5: fixed.asm at 60 Hz: the blocks that fit, and from where the rest runs into the paper
    blk = pr["chain128"]
    out["q5"] = {"block": blk, "fit": 15960 // blk}
    # 6: halt.asm kept, the bursts sized for the frames the BIOS reads the keyboard
    scan = max(m["irq"]["halt"]["eu"]["isr_to_burst"]) + 13
    out["q6"] = {t: (dark - scan - 206) // (blk + 100) for t, dark in (("jp", 15960), ("eu", 27588))}
    # 7: outis with A = 0: 128 - 0, doubled, is 256, and ADD A,A leaves 0: no OUTI skipped
    wk = walk.Walk(HERE / "any")
    t = wk.call("outis", a=0, h=0x40, l=0)
    out["q7"] = {"t": t, "bytes": sum(1 for _, port, v in wk.ports if port == 0x98)}
    # 8: the paper's blocks: where eleven end, and where twelve would, in lines of the paper
    pj = m["paper"]["jp"]
    per_block = pr["loop128"] + 100
    out["q8"] = {"eleven_end": pj["end_during"] - 42, "twelve_end": round(pj["end_during"] - 42 +
                 per_block / 228, 1)}
    # 9: double.asm's write, 23,781 T-states: the latest line it may begin at
    wr = m["double"]["jp"]["write"][0]
    out["q9"] = {"write_lines": round(wr / 228, 1), "latest": int(192 - wr / 228)}
    return out


# ---------------------------------------------------------------- openmsx
OPENMSX_SECTIONS = ["blank", "otir", "chain", "paper", "any", "fill", "irq", "double", "fixed"]


def openmsx():
    if not versions.builds():
        return {"skipped": "OPENMSX_BUILDS not set"}
    return versions.every_build(["ch31"], OPENMSX_SECTIONS)


SECTIONS = {"blank": blank, "otir": picture("otir"), "chain": picture("chain"),
            "paper": picture("paper"), "any": any_, "fill": fill, "irq": irq, "double": double,
            "fixed": fixed, "prices": prices,
            "answers": answers, "openmsx": openmsx}


def main(names=()):
    CAPS.mkdir(exist_ok=True)
    path = HERE / "meas31.json"
    m = json.loads(path.read_text()) if names and path.exists() else {}
    for name in names or SECTIONS:
        print(name, flush=True)
        m[name] = SECTIONS[name]()
        m = {k: m[k] for k in SECTIONS if k in m}
        path.write_text(json.dumps(m, indent=1) + "\n")
    return m


if __name__ == "__main__":
    main(sys.argv[1:])
