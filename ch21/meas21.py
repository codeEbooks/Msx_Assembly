#!/usr/bin/env python3
"""meas21.py -- the screen modes, measured.

    python3 gen21.py && ./build.sh && python3 meas21.py
                                  python3 meas21.py modes bits    only these

The debugger reads the VDP's registers and the whole VRAM; vdpscreen.py,
given them, has to draw the photograph, pixel for pixel, paper and border.

  modes     text.rom, graphic1.rom, graphic2.rom, multi.rom on both machines:
            the photograph against the model; text mode's first pixel fitted;
            the picture against the one it was meant to be (figure 21.1)
  keep      keep.rom: the bits each register keeps
  bios      bios.rom: the registers and table addresses of INITXT, INIT32,
            INIGRP and INIMLT, and what each costs: from the CALL to the
            return, less the frame interrupts that fell inside, each timed
            from the moment the processor took it to its return
  bits      WHERE IT BREAKS: bits.rom on both machines, five states of R#1
            and R#7 over one Graphic I page (figure 21.3)
  answers   the workshop, tried (for Appendix I)
  openmsx   all of it again with every other build (tools/versions.py)
"""
import json
import re
import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "ch14"))
sys.path.insert(0, str(HERE))
import meas        # noqa: E402
import msxcap      # noqa: E402
import probe as dbg  # noqa: E402
import versions    # noqa: E402
import cycles      # noqa: E402  (chapter 14: an instruction's price)
import gen21       # noqa: E402
import vdpscreen   # noqa: E402

CAPS = HERE / "captures"
EU, JP = "MSXBOOK_EU16", "MSXBOOK_JP16"
TAG = {EU: "eu", JP: "jp"}
CLOCK = 3579545
SHOT = 30                   # the film frame photographed: every page is finished by then
POS = "[machine_info VDP_frame_count]"
REGS = " ".join(f"[debug read {{VDP regs}} {i}]" for i in range(8))
VRAM = 'binary scan [debug read_block {VRAM} 0 16384] H* h; L "vram $h"'

# the colour codes as openMSX draws them: chapter 1's palette.rom, both machines
PALETTE = [tuple(c) for c in json.loads((REPO / "ch01" / "meas01.json").read_text())["palette"]["rgb"]]
CODE = {rgb: n for n, rgb in enumerate(PALETTE) if n}       # colour 0 is never drawn as itself


def rom(name):
    return HERE / f"{name}.rom"


def sym(name):
    return dbg.sym(HERE / f"{name}.sym")


def run(name, frames, tcl, machine=EU):
    lines = msxcap.run_tcl(rom(name), frames, tcl, machine=machine)
    return [l.split() for l in lines]


def shot(name, frame, machine, prefix=None, tcl_setup=""):
    got = msxcap.capture(rom(name), [frame], CAPS, prefix or f"{name}_{TAG[machine]}_f",
                         machine=machine, tcl_setup=tcl_setup)
    return got[frame]


def codes(png):
    """the photograph as colour codes, 240 rows of 320; None where a pixel is
    no colour of the palette"""
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


def once(addr, body, tag):
    """a breakpoint that logs once and removes itself: 'done: jr done' would
    stop at it for ever"""
    return f'set ::{tag} [debug set_bp {addr} {{}} {{ {body}; debug remove_bp $::{tag} }}]\n'


def check(vram, regs, photo):
    """the photograph against the model: (pixels wrong, text mode's first
    pixels). In text mode every first pixel from 0 to 16 is tried, and the
    one that makes no pixel wrong is the measurement; a text page with no ink
    fits them all, and says nothing about it"""
    backdrop = regs[7] & 15
    if vdpscreen.mode(regs) != "text":
        return against(vdpscreen.draw(vram, regs), photo, backdrop), None
    old, fits = vdpscreen.TEXT_X0, []
    try:
        for x0 in range(17):
            vdpscreen.TEXT_X0 = x0
            if against(vdpscreen.draw(vram, regs), photo, backdrop) == 0:
                fits.append(x0)
    finally:
        vdpscreen.TEXT_X0 = old
    if len(fits) == 17:
        return 0, None
    return (0, fits[0]) if len(fits) == 1 else (len(fits) or 1, fits)


def state(name, machine, label, frames=SHOT):
    """the registers and the VRAM at LABEL"""
    s = sym(name)
    w = run(name, frames, once(s[label], f'L "regs {REGS}"; {VRAM}; L "at {POS}"', "b"), machine)
    regs = [int(v) for v in next(x for x in w if x[0] == "regs")[1:]]
    vram = bytes.fromhex(next(x for x in w if x[0] == "vram")[1])
    return regs, vram


# ---------------------------------------------------------------- modes
BOX = (64, 48, 192, 168)    # the disc's square, x0, y0, x1, y1, with a margin


def fidelity(photo):
    """the photograph against the picture as it was meant (gen21.ideal), in
    the disc's square: pixels of the wrong shape (ink for paper or paper for
    ink), and pixels of ink in the wrong colour"""
    shape = colour = ink = 0
    for y in range(BOX[1], BOX[3]):
        for x in range(BOX[0], BOX[2]):
            got = photo[y + meas.PAPER_Y0][x + meas.PAPER_X0]
            want = gen21.ideal(x, y)
            if (got == gen21.WHITE) != (want == gen21.WHITE):
                shape += 1
            elif want != gen21.WHITE:
                ink += 1
                colour += got != want
    return {"shape": shape, "colour": colour, "ink": ink}


def modes():
    out = {}
    for name in ("text", "graphic1", "graphic2", "multi"):
        res = {}
        for machine in (EU, JP):
            regs, vram = state(name, machine, "done")
            assert regs == gen21.MODES[name]["regs"], (name, regs)
            photo = codes(shot(name, SHOT, machine))
            bad, x0 = check(vram, regs, photo)
            r = {"wrong": bad, "mode": vdpscreen.mode(regs), "bases": vdpscreen.bases(regs),
                 "fidelity": fidelity(photo),
                 "bios_bytes": sum(1 for a in range(16384) if vram[a] == BIOS_ROM[machine][a])}
            if name == "text":
                r["text_x0"] = x0               # text mode's first pixel, fitted
            assert bad == 0, (name, machine, bad, x0)
            res[TAG[machine]] = r
        assert res["eu"]["fidelity"] == res["jp"]["fidelity"]
        res["reads"] = vdpscreen.reads(gen21.MODES[name]["regs"])
        out[name] = res
    assert out["text"]["eu"]["text_x0"] == out["text"]["jp"]["text_x0"]
    return out


def bios_rom(machine):
    import screentext
    return (msxcap.CBIOS / screentext.bios_file(machine)).read_bytes()


BIOS_ROM = {EU: None, JP: None}


# ---------------------------------------------------------------- keep
def keep():
    s = sym("keep")
    w = run("keep", 8, f'debug set_bp {s["kept"]} {{}} {{ L "kept {REGS}" }}\n'
                       f'debug set_bp {s["zero"]} {{}} {{ L "zero {REGS}" }}\n')
    kept = [int(v) for v in next(x for x in w if x[0] == "kept")[1:]]
    zero = [int(v) for v in next(x for x in w if x[0] == "zero")[1:]]
    assert zero == [0] * 8
    return {"kept": kept, "bits": [bin(k).count("1") for k in kept]}


# ---------------------------------------------------------------- bios
SYSVARS = {mode: [f"{mode}{t}" for t in ("NAM", "COL", "CGP", "ATR", "PAT")]
           for mode in ("TXT", "T32", "GRP", "MLT")}
SYSVAR_AT = {"TXT": 0xF3B3, "T32": 0xF3BD, "GRP": 0xF3C7, "MLT": 0xF3D1}


# the registers a mode uses: text mode has no colour table and no sprites,
# multicolour no colour table; the others it leaves as they were
USED = {"text": (0, 1, 2, 4, 7), "graphic1": tuple(range(8)), "graphic2": tuple(range(8)),
        "multicolour": (0, 1, 2, 4, 5, 6, 7)}


def bios():
    s = sym("bios")
    words = " ".join(f"[debug read memory {a}] [debug read memory {a + 1}]"
                     for a in range(0xF3B3, 0xF3DB, 2))
    # every byte written to $98 inside a call is counted; every frame
    # interrupt is timed from the moment the processor takes it (the probe)
    # to its return to the address it left, at the same stack depth
    tcl = ("set ::n 0\ndebug set_watchpoint write_io 0x98 {} { incr ::n }\n"
           "debug probe set_bp z80.acceptIRQ {} { set ::acc [machine_info time] }\n"
           "debug set_bp 0x0038 {} {\n"
           '    L "take [machine_info time]"\n'
           "    set ::isp [reg sp]\n"
           "    set ::iacc $::acc\n"
           "    set ::rbp [debug set_bp [peek16 [reg sp]] {[reg sp] == $::isp + 2} {\n"
           '        L "isr $::iacc [machine_info time]"\n'
           "        debug remove_bp $::rbp\n"
           "    }]\n"
           "}\n")
    # each call is timed from the CALL to its return, the DI after it left out
    for i in range(4):
        assert s[f"r{i}"] == s[f"c{i}"] + 4 and s[f"m{i}"] == s[f"g{i}"] + 4   # CALL nn, DI
        tcl += (f'debug set_bp {s[f"c{i}"]} {{}} {{ set ::n 0; L "call {i} [machine_info time]" }}\n'
                f'debug set_bp {s[f"c{i}"] + 3} {{}} {{ L "ret {i} [machine_info time]" }}\n'
                f'debug set_bp {s[f"r{i}"]} {{}} {{ L "back {i} {REGS}"; '
                f'L "vars {i} {words}"; L "bytes {i} $::n" }}\n')
    for i in range(4):
        tcl += (f'debug set_bp {s[f"g{i}"]} {{}} {{ L "chg {i} [machine_info time]" }}\n'
                f'debug set_bp {s[f"g{i}"] + 3} {{}} {{ L "cret {i} [machine_info time]" }}\n'
                f'debug set_bp {s[f"m{i}"]} {{}} {{ L "mode {i} {REGS}" }}\n')

    def first(w, tag, i):
        return next(x for x in w if x[0] == tag and x[1] == str(i))

    def timed(w, isrs, t0, t1):
        """the T-states from T0 to T1, the frame interrupts taken inside, and
        the T-states of each"""
        inside = [(a, r) for a, r in isrs if t0 <= a < t1]
        assert all(r <= t1 for _, r in inside)
        costs = [round((r - a) * CLOCK) for a, r in inside]
        return round((t1 - t0) * CLOCK), costs

    out = {}
    for machine in (EU, JP):
        w = run("bios", 700, tcl, machine)
        isrs = [(float(x[1]), float(x[2])) for x in w if x[0] == "isr"]
        # every interrupt taken came back, and none ran across a window's start
        assert len(isrs) == sum(1 for x in w if x[0] == "take")
        starts = [float(x[2]) for x in w if x[0] in ("call", "chg")]
        assert not any(a < t < r for a, r in isrs for t in starts)
        res = {}
        for i, call in enumerate(gen21.BIOS_CALLS):
            t0 = float(first(w, "call", i)[2])
            t1 = float(first(w, "ret", i)[2])
            window, costs = timed(w, isrs, t0, t1)
            back = first(w, "back", i)
            v = [int(b) for b in first(w, "vars", i)[2:]]
            var = [v[2 * k] | v[2 * k + 1] << 8 for k in range(20)]
            regs = [int(b) for b in back[2:]]
            m = list(SYSVAR_AT)[i]
            k = (SYSVAR_AT[m] - 0xF3B3) // 2
            table = dict(zip(("names", "colours", "patterns", "attributes", "sprites"), var[k:k + 5]))
            nbytes = int(first(w, "bytes", i)[2])
            res[call] = {"t": window - sum(costs), "window": window, "interrupts": len(costs),
                         "isr_t": costs, "regs": regs, "bytes": nbytes,
                         "vars": table, "mode": vdpscreen.mode(regs), "bases": vdpscreen.bases(regs)}
            # the BIOS's own variables and the registers it wrote say the same
            b = vdpscreen.bases(regs)
            assert table["names"] == b["names"] and table["patterns"] == b["patterns"], (call, table, b)
            if res[call]["mode"] in ("graphic1",):
                assert table["colours"] == b["colours"]
            if res[call]["mode"] != "text":
                assert table["attributes"] == (regs[5] & 0x7F) * 0x80
                assert table["sprites"] == (regs[6] & 7) * 0x800
        # CHGMOD with A = 0 to 3: the same registers as the routine for the mode
        for i, call in enumerate(gen21.BIOS_CALLS):
            window, costs = timed(w, isrs, float(first(w, "chg", i)[2]), float(first(w, "cret", i)[2]))
            r = res[call]
            r["chgmod_t"], r["chgmod_window"] = window - sum(costs), window
            r["chgmod_interrupts"], r["chgmod_isr_t"] = len(costs), costs
            used = USED[r["mode"]]
            got = [int(v) for v in first(w, "mode", i)[2:]]
            r["chgmod_same"] = all(got[n] == r["regs"][n] for n in used)
            assert r["chgmod_same"], (machine, call)
        out[TAG[machine]] = res
    for call in gen21.BIOS_CALLS:
        assert out["eu"][call]["vars"] == out["jp"][call]["vars"]
    # each routine's own time is the same on both machines, and CHGMOD's own
    # part the same before every routine
    m = [out[t][c] for t in ("eu", "jp") for c in gen21.BIOS_CALLS]
    dispatch = {r["chgmod_t"] - r["t"] for r in m}
    assert len(dispatch) == 1, dispatch
    for call in gen21.BIOS_CALLS:
        own = {out[t][call]["t"] for t in ("eu", "jp")}
        assert len(own) == 1, (call, own)
        out[call] = {"t": own.pop()}
    out["chgmod_dispatch"] = dispatch.pop()
    # every interrupt inside was chapter 17's C-BIOS routine in a frame it
    # does not read the keyboard
    irq = json.loads((REPO / "ch17" / "meas17.json").read_text())["bios"]["plain"]
    costs = {c for r in m for c in r["isr_t"] + r["chgmod_isr_t"]}
    assert costs <= {irq}, costs
    out["irq"] = irq
    out["interrupts"] = sum(r["interrupts"] for r in m)
    return out


# ---------------------------------------------------------------- chars
def ink(photo, backdrop):
    return sum(c != backdrop for row in photo[24:216] for c in row[32:288])


def chars():
    import asmparts
    import screentext
    s = sym("chars")
    tcl = (once(s["tx"], f'L "g1 {POS} {REGS}"; {VRAM}', "a") +
           once(s["done"], f'L "tx {POS} {REGS}"', "b") +
           'L "f0 [machine_info VDP_frame_count]"\n')
    out = {}
    for machine in (EU, JP):
        w = run("chars", 60, tcl, machine)
        f0 = int(next(x for x in w if x[0] == "f0")[1])
        vram = bytes.fromhex(next(x for x in w if x[0] == "vram")[1])
        res = {}
        for tag, film_back in (("g1", 4), ("tx", -4)):
            x = next(x for x in w if x[0] == tag)
            frame, regs = int(x[1]) - f0, [int(v) for v in x[2:]]
            # Graphic I: some frames before the switch; text mode: after it
            film = frame - 4 if tag == "g1" else frame + 4
            photo = codes(shot("chars", film, machine, prefix=f"chars_{tag}_{TAG[machine]}_f"))
            bad, x0 = check(vram, regs, photo)
            assert bad == 0, (tag, machine, bad)
            res[tag] = {"film": film, "mode": vdpscreen.mode(regs), "ink": ink(photo, regs[7] & 15),
                        "text_x0": x0}
        # the shapes, from the BIOS's own file and the book's two boxes: the
        # pixels in their two right columns, which text mode does not draw
        shapes, _ = screentext.font(machine)
        shapes = [list(p) for p in shapes]
        for code, rows in asmparts.BOX_SHAPES.items():
            shapes[code] = rows
        cut = sum(bin(b & 3).count("1") for p in shapes for b in p)
        res["cut_from_font"] = cut
        res["chars_cut"] = sum(1 for p in shapes if any(b & 3 for b in p))
        res["chars_cut_32_127"] = sum(1 for c in range(32, 128) if any(b & 3 for b in shapes[c]))
        assert res["g1"]["ink"] - res["tx"]["ink"] == cut
        out[TAG[machine]] = res
    return out


# ---------------------------------------------------------------- bands
def bands():
    out = {}
    for machine in (EU, JP):
        regs, vram = state("bands", machine, "done")
        photo = codes(shot("bands", SHOT, machine))
        bad, _ = check(vram, regs, photo)
        assert bad == 0
        # each row of the screen: its first two blocks against the pair of
        # pattern 0's bytes its row picks, read off the photograph
        rows = []
        for r in range(24):
            y0 = meas.PAPER_Y0 + 8 * r
            got = [photo[y0][meas.PAPER_X0], photo[y0][meas.PAPER_X0 + 4],
                   photo[y0 + 4][meas.PAPER_X0], photo[y0 + 4][meas.PAPER_X0 + 4]]
            b0, b1 = gen21.BANDS[2 * (r % 4)], gen21.BANDS[2 * (r % 4) + 1]
            rows.append(got == [b0 >> 4, b0 & 15, b1 >> 4, b1 & 15])
        out[TAG[machine]] = {"wrong": bad, "rows_right": sum(rows)}
    return out


# ---------------------------------------------------------------- flip
def flip():
    s = sym("flip")
    tcl = (f'debug set_bp {s["p7"]} {{}} {{ L "p7 {POS}" }}\n'
           f'debug set_bp {s["p6"]} {{}} {{ L "p6 {POS}" }}\n'
           f'debug set_bp {s["turn"]} {{}} {{ L "turn {POS} {REGS}" }}\n' +
           once(s["turn"], VRAM, "v") + 'L "f0 [machine_info VDP_frame_count]"\n')
    out = {}
    for machine in (EU, JP):
        w = run("flip", 80, tcl, machine)
        f0 = int(next(x for x in w if x[0] == "f0")[1])
        vram = bytes.fromhex(next(x for x in w if x[0] == "vram")[1])
        regs0 = [int(v) for v in next(x for x in w if x[0] == "turn")[2:]]
        p7 = [int(x[1]) - f0 for x in w if x[0] == "p7"]
        p6 = [int(x[1]) - f0 for x in w if x[0] == "p6"]
        assert len(p7) == len(p6) == 2
        res = []
        for film, r2 in ((p7[0] - 4, 6), (p7[0] + 4, 7), (p6[0] + 4, 6)):
            regs = regs0[:2] + [r2] + regs0[3:]
            photo = codes(shot("flip", film, machine, prefix=f"flip_{TAG[machine]}_f"))
            bad, _ = check(vram, regs, photo)
            assert bad == 0, (machine, film, bad)
            res.append({"film": film, "r2": r2, "names": vdpscreen.bases(regs)["names"]})
        out[TAG[machine]] = {"shots": res, "p7": p7, "p6": p6}
    return out


# ---------------------------------------------------------------- prices
JUMPS = {"djnz": (14, 9), "jr": (13, 8)}               # taken, not taken (chapter 11)


def lst_lines(name):
    """[(source, address, bytes)] of the instructions of a listing (the
    padding's ds, shown with "...", left out: chapter 19's reader)"""
    out = []
    for line in (HERE / f"{name}.lst").read_text().splitlines():
        m = dbg.LST.match(line)
        if not m or "..." in m.group(3)[1:13] or not m.group(3)[1:13].strip():
            continue
        _, a, code, src = dbg.lst_fields(m)
        src = re.sub(r"^\s*[\w.]+:", "", src.split(";")[0].lstrip(">")).strip()
        if src and not src.lower().startswith(("db", "dw", "ds")):
            out.append((src, a, code))
    return out


def price(src, code, moved):
    """the MSX price of one instruction (taken, not taken); OTIR and INIR
    moving MOVED bytes: 23 a byte, 18 the last (chapter 13)"""
    op = src.split()[0].lower()
    if op in JUMPS:
        return JUMPS[op]
    if op in ("otir", "inir"):
        t = 23 * (moved - 1) + 18
        return t, t
    t = cycles.msx(code)
    return t, t


def run_price(name, first, last, times=1, moved=0):
    """the T-states of the lines from label FIRST to label LAST run TIMES
    times, the closing jump taken every time but the last"""
    s = sym(name)
    seg = [(src, c) for src, a, c in lst_lines(name) if s[first] <= a < s[last]]
    taken = sum(price(src, c, moved)[0] for src, c in seg)
    last_t, last_not = price(*seg[-1], moved)
    return times * taken - (last_t - last_not) * (times > 1 or seg[-1][0].split()[0] in JUMPS)


# ---------------------------------------------------------------- switch
def switch():
    s = sym("switch")
    tcl = (f'debug set_bp {s["sw"]} {{}} {{ L "sw {POS} [machine_info time]" }}\n'
           f'debug set_bp {s["on"]} {{}} {{ L "on {POS} [machine_info time]" }}\n' +
           once(s["done"], f'L "regs {REGS}"; {VRAM}', "d") +
           'L "f0 [machine_info VDP_frame_count]"\n')
    out = {}
    for machine in (EU, JP):
        w = run("switch", 60, tcl, machine)
        f0 = int(next(x for x in w if x[0] == "f0")[1])
        sw = next(x for x in w if x[0] == "sw")
        on = next(x for x in w if x[0] == "on")
        regs = [int(v) for v in next(x for x in w if x[0] == "regs")[1:]]
        vram = bytes.fromhex(next(x for x in w if x[0] == "vram")[1])
        film = int(on[1]) - f0 + 4
        before = int(sw[1]) - f0 - 2
        res = {"t": round((float(on[2]) - float(sw[2])) * CLOCK), "film": film,
               "before": before, "mode": vdpscreen.mode(regs), "regs": regs}
        photo = codes(shot("switch", film, machine))
        res["wrong"], res["text_x0"] = check(vram, regs, photo)
        assert res["wrong"] == 0 and res["mode"] == "text"
        shot("switch", before, machine)                 # the page before, for the figure
        res["frames"] = res["t"] / meas.T_PER_FRAME[machine]
        out[TAG[machine]] = res
    # the same T-states, priced line by line from the listing
    parts = {"start": run_price("switch", "sw", "font"),
             "shapes": run_price("switch", "font", "clr", 8, 256),
             "spaces": run_price("switch", "clr", "sp") + run_price("switch", "sp", "names", 960),
             "names": run_price("switch", "names", "row") + run_price("switch", "row", "regs", 24, 32),
             "registers": run_price("switch", "regs", "on")}
    out["priced"] = parts
    assert sum(parts.values()) == out["eu"]["t"] == out["jp"]["t"], (parts, sum(parts.values()))
    return out


# ---------------------------------------------------------------- bits
def bits():
    s = sym("bits")
    n = len(gen21.BITS_STATES)
    tcl = "".join(once(s[f"t{k}"], f'L "state {k} {POS} {REGS}"', f"t{k}") for k in range(n))
    tcl += once(s["t0"], VRAM, "v")
    out = {}
    for machine in (EU, JP):
        w = run("bits", 80, tcl + 'L "f0 [machine_info VDP_frame_count]"\n', machine)
        f0 = int(next(x for x in w if x[0] == "f0")[1])
        vram = bytes.fromhex(next(x for x in w if x[0] == "vram")[1])
        res = []
        for k in range(n):
            x = next(x for x in w if x[0] == "state" and x[1] == str(k))
            frame, regs = int(x[2]) - f0, [int(v) for v in x[3:]]
            r1, r7, what = gen21.BITS_STATES[k]
            assert regs[1] == r1 and regs[7] == r7
            film = frame + 3
            photo = codes(shot("bits", film, machine, prefix=f"bits{k}_{TAG[machine]}_f"))
            bad, x0 = check(vram, regs, photo)
            assert bad == 0, (k, machine, bad)
            res.append({"frame": frame, "film": film, "regs": regs, "mode": vdpscreen.mode(regs),
                        "wrong": bad, "text_x0": x0, "ink_pixels": sum(c != regs[7] & 15 for row in photo[24:216]
                                                        for c in row[32:288])})
        out[TAG[machine]] = res
    return out


# ---------------------------------------------------------------- answers
def answers():
    out = {}
    # 1: a text screen against a Graphic I screen
    out["q1"] = {"characters": 40 * 24 - 32 * 24, "names": 960 - 768}
    # 2: R#2 = $1E: where the names are, with the bits keep.rom found R#2 keeps
    kept = json.loads((HERE / "meas21.json").read_text())["keep"]["kept"]
    out["q2"] = (0x1E & kept[2]) * 0x400
    # 3: bits.rom's last state: the ink pixels in its photograph
    b = json.loads((HERE / "meas21.json").read_text())["bits"]
    out["q3"] = {m: b[m][-1]["ink_pixels"] for m in ("eu", "jp")}
    # 4: the colours split at line 112: Graphic I's tables worked out again,
    #    drawn by the model, against the picture as meant
    old = gen21.SPLIT
    try:
        gen21.SPLIT = 112
        blocks, _ = gen21.graphic1_tables()
        vram = bytearray(16384)
        vram[0:2048] = bytes(range(256)) * 8                # anything: the font's place
        for addr, data in blocks:
            vram[addr:addr + len(data)] = bytes(data)
        model = vdpscreen.draw(vram, gen21.MODES["graphic1"]["regs"])
        wrong = sum(1 for y in range(BOX[1], BOX[3]) for x in range(BOX[0], BOX[2])
                    if gen21.ideal(x, y) != gen21.WHITE and model[y][x] != gen21.WHITE
                    and model[y][x] != gen21.ideal(x, y))
    finally:
        gen21.SPLIT = old
    out["q4"] = wrong
    # 5: multicolour, a name in row 13: the two bytes of its pattern it shows
    out["q5"] = [2 * (13 % 4), 2 * (13 % 4) + 1]
    # 6: INIGRP against INIT32: the bytes each wrote to $98, and the T-states a byte
    bi = json.loads((HERE / "meas21.json").read_text())["bios"]
    out["q6"] = {c: {"bytes": bi["eu"][c]["bytes"], "t": bi[c]["t"],
                     "t_per_byte": round(bi[c]["t"] / bi["eu"][c]["bytes"], 1)}
                 for c in ("INIT32", "INIGRP")}
    return out


# ---------------------------------------------------------------- builds
def builds():
    """text.rom photographed by every build of OPENMSX_BUILDS, and text mode's
    first pixel fitted to each photograph"""
    import os
    import tempfile
    if not versions.builds():
        return {"skipped": "OPENMSX_BUILDS not set"}
    regs, vram = state("text", EU, "done")
    out = {}
    old = msxcap.OPENMSX, os.environ.get("OPENMSX_SYSTEM_DATA")
    tmp = Path(tempfile.mkdtemp(prefix="builds21_"))
    try:
        for label, binary, share in versions.builds():
            msxcap.OPENMSX, os.environ["OPENMSX_SYSTEM_DATA"] = binary, share
            png = msxcap.capture(rom("text"), [SHOT], tmp, f"{label.split()[0]}_f", machine=EU)[SHOT]
            bad, x0 = check(vram, regs, codes(png))
            assert bad == 0, (label, bad, x0)
            out[label.split()[0]] = x0
    finally:
        msxcap.OPENMSX = old[0]
        if old[1] is None:
            os.environ.pop("OPENMSX_SYSTEM_DATA", None)
        else:
            os.environ["OPENMSX_SYSTEM_DATA"] = old[1]
    return out


# ---------------------------------------------------------------- openmsx
OPENMSX_SECTIONS = ["modes", "keep", "bios", "chars", "bands", "flip", "bits", "switch",
                    "answers"]


def openmsx():
    if not versions.builds():
        return {"skipped": "OPENMSX_BUILDS not set"}
    return versions.every_build(["ch21"], OPENMSX_SECTIONS)


SECTIONS = {"modes": modes, "keep": keep, "bios": bios, "chars": chars, "bands": bands,
            "flip": flip, "bits": bits, "switch": switch, "answers": answers,
            "builds": builds, "openmsx": openmsx}


def main(names=()):
    CAPS.mkdir(exist_ok=True)
    for m in (EU, JP):
        BIOS_ROM[m] = bios_rom(m)
    path = HERE / "meas21.json"
    m = json.loads(path.read_text()) if names and path.exists() else {}
    for name in names or SECTIONS:
        print(name, flush=True)
        m[name] = SECTIONS[name]()
        m = {k: m[k] for k in SECTIONS if k in m}
        path.write_text(json.dumps(m, indent=1) + "\n")
    return m


if __name__ == "__main__":
    out = main(sys.argv[1:])
    print(json.dumps({k: out[k] for k in (sys.argv[1:] or out) if k in out}, indent=1)[:5000])
