#!/usr/bin/env python3
"""measD.py -- the tables of Appendix D, photographed and timed on openMSX.

    python3 genD.py && ./build.sh && python3 measD.py [step ...]

    tables   the bytes of every table in each cartridge against two models:
             chapter 22's masks, worked out here from R#3 and R#4, and the
             picture vdpscreen.py (chapters 21 to 23) draws when that one
             byte is set: one line's column 0, or the same line of each third
    addr     addr.rom on both machines: every frame's photograph against the
             picture vdpscreen.py draws from the VRAM with the frame's byte
             written, and the pixels it changes against the rule
    times    timep.rom and timec.rom on both machines: every write to $98 in
             the paper, at the frame and the cycle the debugger saw it; every
             line's column 0 in every frame's photograph, new or old, and the
             whole photograph against vdpscreen.py; for each line the last
             T-state that showed, against vdpslots.py (chapter 20) and the
             cycle of pixel 0 that beam measures
    beam     beam.rom on both machines: every write of R#7, and where on its
             line the photograph changes colour, against chapter 18's
             x = 1.5w - 31 and chapter 32's half pixel behind the paper
    calls    calls.rom: each routine's answers for every line and column
             against the models; each one timed with its CALL on both
             machines, against its listing priced as chapter 14 prices
    rows     the appendix's table, a row a line, from the steps above
    before   the numbers against chapters 17, 18, 20, 22 and 32
    openmsx  the steps again with every other build (tools/versions.py)

The photographs are read and thrown away: measD.json keeps what they showed.
"""
import hashlib
import json
import math
import os
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "ch14"))
sys.path.insert(0, str(HERE))
import meas        # noqa: E402
import msxcap      # noqa: E402
import probe       # noqa: E402
import versions    # noqa: E402
import cycles      # noqa: E402  (chapter 14: an instruction's price)
import vdpslots    # noqa: E402  (chapter 20, copied)
import vdpscreen   # noqa: E402  (chapters 21 to 23, copied)
import genD        # noqa: E402

OUT_JSON = HERE / "measD.json"
EU, JP = genD.EU, genD.JP
MACHINES = (EU, JP)
TAG = {EU: "eu", JP: "jp"}
CLOCK = probe.CLOCK
LINE = vdpslots.LINE
POS = "[machine_info VDP_frame_count] [machine_info VDP_cycle_in_frame]"
TOO_FAST = ('set ::toofast 0\nproc ::toofast_cb {args} { incr ::toofast; L "toofast" }\n'
            'set VDP.too_fast_vram_access_callback ::toofast_cb\n')
F0 = 'L "f0 [machine_info VDP_frame_count]"\n'
REGS = " ".join(f"[debug read {{VDP regs}} {i}]" for i in range(8))
VRAM = 'binary scan [debug read_block {VRAM} 0 16384] H* h; L "vram $h"'
STRICT = "MSXCAP_OPENMSX" not in os.environ     # the book's openMSX: every rule asserted

PALETTE = [tuple(c) for c in json.loads((REPO / "ch01" / "meas01.json").read_text())["palette"]["rgb"]]
KEYS = np.array([(r << 16) | (g << 8) | b for r, g, b in PALETTE[1:]])
ORDER = np.argsort(KEYS)
WHITE, BLACK = 15, 1
# the cycle of a line at which the VDP draws paper pixel 0, capture x 32: a
# change written up to it shows there. beam measures it on every line: 258,
# T-state 43, as the debugger counts. Chapter 18 has T-state 42: chapter 8
# counts an OUT's write 8 T-states into it, the debugger 9 (see beam)
PIXEL0 = 258
OUT_N_WRITES = 9                # the debugger's watchpoint, into an OUT (n),A


def rom(name):
    return HERE / f"{name}.rom"


def sym(name):
    return probe.sym(HERE / f"{name}.sym")


def run(name, frames, tcl, machine):
    lines = msxcap.run_tcl(rom(name), frames, TOO_FAST + F0 + tcl, machine=machine)
    return [l.split() for l in lines]


def codes(png):
    """the photograph as 240 rows of 320 colour codes (0 for none of them)"""
    a = np.asarray(Image.open(png).convert("RGB")).astype(np.int64)
    k = (a[:, :, 0] << 16) | (a[:, :, 1] << 8) | a[:, :, 2]
    i = np.searchsorted(KEYS[ORDER], k)
    i = np.clip(i, 0, len(KEYS) - 1)
    hit = KEYS[ORDER][i] == k
    return np.where(hit, ORDER[i] + 1, 0)


def photos(name, frames, machine):
    """{frame: codes} for FRAMES of the film from INIT; the PNGs thrown away"""
    tmp = Path(tempfile.mkdtemp(prefix="appD_"))
    try:
        pngs = msxcap.capture(rom(name), frames, tmp, f"{name}_", machine=machine)
        return {f: codes(p) for f, p in pngs.items()}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def against(model, photo, backdrop):
    """pixels of the photograph inside the columns the VDP draws that are not
    the model's: MODEL the paper, BACKDROP the border"""
    want = np.full((240, meas.DRAWN[1] - meas.DRAWN[0] + 1), backdrop)
    x0 = meas.PAPER_X0 - meas.DRAWN[0]
    want[meas.PAPER_Y0:meas.PAPER_Y0 + 192, x0:x0 + 256] = np.asarray(model)
    return int((photo[:, meas.DRAWN[0]:meas.DRAWN[1] + 1] != want).sum())


def paper(photo):
    return photo[meas.PAPER_Y0:meas.PAPER_Y0 + 192, meas.PAPER_X0:meas.PAPER_X0 + 256]


# ---------------------------------------------------------------- the models
def masked(x, y, r3, r4, table):
    """chapter 22: the address of pixel (x, y)'s byte in Graphic II, names 0 to
    255 in each third. The name and its third make a 10-bit index; R#4 bits
    1-0 keep its top two bits for the patterns, R#3 bits 6-0 keep bits 9-3
    for the colours (the low five, bits 7-3, for the patterns too: chapter
    22's leak); R#4 bit 2 and R#3 bit 7 give A13."""
    index = (y >> 6) * 256 + ((y >> 3) & 7) * 32 + (x >> 3)
    if table == "patterns":
        keep = (((r4 & 3) << 8) | 0xFF) & (0x300 | ((r3 & 0x1F) << 3) | 7)
        return ((r4 & 4) << 11) | ((index & keep) << 3) | (y & 7)
    keep = ((r3 & 0x7F) << 3) | 7
    return ((r3 & 0x80) << 6) | ((index & keep) << 3) | (y & 7)


def name_of(x, y):
    return 0x1800 + (y >> 3) * 32 + (x >> 3)


def base_vram(patt, col, names):
    v = bytearray(16384)
    v[0:6144] = bytes([patt]) * 6144
    v[0x2000:0x3800] = bytes([col]) * 6144
    v[0x1800:0x1B00] = bytes(range(256)) * 3 if names == "order" else bytes(768)
    v[0x1B00] = 0xD0
    return v


def regs_of(layout, r7=0x0F, r1=0xE0):
    r3, r4 = genD.REGS34[layout]
    return [0x02, r1, 0x06, r3, r4, 0x36, 0x07, r7]


def lit(picture, base):
    """the pixels of PICTURE that differ from BASE: {(x, y)}"""
    d = np.argwhere(np.asarray(picture) != np.asarray(base))
    return {(int(x), int(y)) for y, x in d}


# ---------------------------------------------------------------- tables
def rom_words(name, label, n, s):
    data = rom(name).read_bytes()
    a = s[label] - 0x4000
    return [data[a + 2 * i] | data[a + 2 * i + 1] << 8 for i in range(n)]


def rom_bytes(name, label, n, s):
    data = rom(name).read_bytes()
    a = s[label] - 0x4000
    return list(data[a:a + n])


def tables(res):
    out = {"roms": {}, "where": {}}
    want = {}
    for lab, _, _, n, _, _ in genD.TABLES:
        if lab == "namerow":
            want[lab] = [0x1800 + 32 * r for r in range(n)]
        else:
            layout = genD.BIOS if lab in ("patrow", "colrow") else genD.THIRD
            r3, r4 = genD.REGS34[layout]
            t = "patterns" if lab.startswith("pat") else "colours"
            want[lab] = [masked(0, y, r3, r4, t) for y in range(n)]
    pages = {"pathi": [a >> 8 for a in want["patrow"]], "patlo": [a & 0xFF for a in want["patrow"]],
             "namhi": [name_of(0, y) >> 8 for y in range(192)],
             "namlo": [name_of(0, y) & 0xFF for y in range(192)]}
    for name in genD.PROGRAMS:
        s = sym(name)
        got = {lab: rom_words(name, lab, n, s) for lab, _, _, n, _, _ in genD.TABLES}
        got.update({lab: rom_bytes(name, lab, 192, s) for lab, _, _ in genD.PAGES})
        bad = {lab: sum(1 for a, b in zip(got[lab], want.get(lab) or pages[lab]) if a != b)
               for lab in got}
        assert not any(bad.values()), (name, bad)
        assert all(s[lab] & 0xFF == 0 for lab, _, _ in genD.PAGES), name
        assert s["patlo"] == s["pathi"] + 256 and s["namlo"] == s["namhi"] + 256, name
        out["roms"][name] = {"wrong": sum(bad.values()), "at": {lab: s[lab] for lab in got}}
    # where each entry shows, as vdpscreen.py draws it: one byte set to ink
    seen = {}
    for lab in ("patrow", "colrow", "patrow3", "colrow3", "namerow"):
        layout = genD.BIOS if lab in ("patrow", "colrow", "namerow") else genD.THIRD
        regs = regs_of(layout)
        if lab.startswith("pat"):
            base, new = base_vram(0x00, 0x1F, "order"), 0xFF
        elif lab.startswith("col"):
            base, new = base_vram(0xF0, 0xFF, "order"), 0x1F
        else:
            base, new = base_vram(0x00, 0x1F, "zero"), genD.NAME_SHAPE
            for third in range(3):
                base[third * 2048 + 8 * genD.NAME_SHAPE:third * 2048 + 8 * genD.NAME_SHAPE + 8] = b"\xFF" * 8
        b0 = vdpscreen.draw(base, regs)
        rows = []
        for i, a in enumerate(want[lab]):
            v = bytearray(base)
            v[a] = new
            px = lit(vdpscreen.draw(v, regs), b0)
            rows.append(sorted({y for _, y in px}))
            xs = sorted({x for x, _ in px})
            if lab == "namerow":
                assert rows[-1] == list(range(8 * i, 8 * i + 8)) and xs == list(range(8)), (lab, i)
            else:
                lines = [i] if layout == genD.BIOS else [i % 64, i % 64 + 64, i % 64 + 128]
                assert rows[-1] == lines and xs == (list(range(8)) if lab.startswith("pat")
                                                    else list(range(4))), (lab, i, rows[-1], xs)
        seen[lab] = {"entries": len(rows), "lines_each": sorted({len(r) for r in rows})}
    out["where"] = seen
    # the same addresses from vdpscreen.address, the BIOS's layout, any x
    assert all(vdpscreen.address(x, y) == masked(x, y, 0xFF, 0x03, "patterns")
               for y in range(192) for x in range(0, 256, 3))
    res["tables"] = out


# ---------------------------------------------------------------- addr
def addr_run(machine):
    s = sym("addr")
    tcl = ""
    for p in genD.PASSES:
        lab, n = p[0], p[2]
        tcl += (f'debug set_bp {s[lab + "m"]} {{}} {{ if {{[reg b] == {n}}} {{ L "regs {REGS}"; {VRAM} }}; '
                f'L "m {lab} [reg b] [reg de] [debug read VRAM [reg de]] {POS}" }}\n')
    frames = 60 + sum(p[2] for p in genD.PASSES) + 12 * len(genD.PASSES)
    w = run("addr", frames, tcl, machine)
    f0 = int(next(x for x in w if x[0] == "f0")[1])
    marks, dumps = [], {}
    pend = {}
    for x in w:
        if x[0] == "regs":
            pend["regs"] = [int(v) for v in x[1:]]
        elif x[0] == "vram":
            pend["vram"] = bytearray(bytes.fromhex(x[1]))
        elif x[0] == "m":
            if pend:
                dumps[x[1]] = pend
                pend = {}
            marks.append({"pass": x[1], "i": None, "b": int(x[2]), "de": int(x[3]), "byte": int(x[4]),
                          "frame": int(x[5]), "cycle": int(x[6])})
    for mk in marks:
        p = next(q for q in genD.PASSES if q[0] == mk["pass"])
        mk["i"] = p[2] - mk["b"]
    fast = sum(1 for x in w if x[0] == "toofast")
    return f0, marks, dumps, fast


def addr(res):
    out = {}
    for machine in MACHINES:
        f0, marks, dumps, fast = addr_run(machine)
        assert len(marks) == sum(p[2] for p in genD.PASSES) and not fast, (machine, len(marks), fast)
        r = {"marks": len(marks), "fast": fast, "passes": {}}
        # the photograph after each mark: frame F + d - f0, d found once for all
        shots = sorted({mk["frame"] - f0 + d for mk in marks for d in (0, 1, 2)})
        ph = photos("addr", shots, machine)
        fits = []
        models = []
        for mk in marks:
            lab, table, n, layout, patt, col, names, old, new = next(q for q in genD.PASSES
                                                                     if q[0] == mk["pass"])
            d = dumps[lab]
            want = rom_words("addr", table, n, sym("addr"))
            assert mk["de"] == want[mk["i"]] and mk["byte"] == new, (machine, mk)
            # the VRAM the pass set up: the dump at its first mark, entry 0 back to OLD
            base = bytearray(d["vram"])
            base[want[0]] = old
            ref = base_vram(patt, col, names)
            if names == "zero":
                for third in range(3):
                    a = third * 2048 + 8 * genD.NAME_SHAPE
                    ref[a:a + 8] = b"\xFF" * 8
            assert base[:0x1B01] == ref[:0x1B01] and base[0x2000:0x3800] == ref[0x2000:0x3800] \
                and d["regs"] == regs_of(layout), (machine, lab)
            v = bytearray(base)
            v[mk["de"]] = new
            models.append((mk, v, d["regs"], vdpscreen.draw(base, d["regs"])))
        for dd in (0, 1, 2):
            if all(against(vdpscreen.draw(v, rg), ph[mk["frame"] - f0 + dd], rg[7] & 15) == 0
                   for mk, v, rg, _ in models[:12]):
                fits.append(dd)
        assert len(fits) == 1, (machine, fits)
        dd = fits[0]
        for mk, v, rg, b0 in models:
            lab = mk["pass"]
            layout = next(q for q in genD.PASSES if q[0] == lab)[3]
            pic = vdpscreen.draw(v, rg)
            photo = ph[mk["frame"] - f0 + dd]
            wrong = against(pic, photo, rg[7] & 15)
            px = lit(paper(photo), b0)
            i = mk["i"]
            if lab.startswith("n"):
                rule = {(x, y) for x in range(8) for y in range(8 * i, 8 * i + 8)}
            else:
                lines = [i] if layout == genD.BIOS else [i % 64, i % 64 + 64, i % 64 + 128]
                xs = range(8) if lab[0] == "p" else range(4)
                rule = {(x, y) for x in xs for y in lines}
            pr = r["passes"].setdefault(lab, {"frames": 0, "wrong": 0, "rule_misses": 0,
                                              "lines_lit": set(), "pixels": set()})
            pr["frames"] += 1
            pr["wrong"] += wrong
            pr["rule_misses"] += px != rule
            pr["lines_lit"].add(len({y for _, y in px}))
            pr["pixels"].add(len(px))
        for pr in r["passes"].values():
            assert pr["wrong"] == 0 and pr["rule_misses"] == 0, (machine, pr)
            pr["lines_lit"], pr["pixels"] = sorted(pr["lines_lit"]), sorted(pr["pixels"])
        r["fit"] = dd
        r["photos"] = len(models)
        out[TAG[machine]] = r
    res["addr"] = out


# ---------------------------------------------------------------- times
def shows(cycle_in_frame, y, machine, regs):
    """chapter 20: the cycle at which the VDP takes the byte; it shows on line
    y's column 0 if that is no later than pixel 0 of the line"""
    taken = vdpslots.slot_after(cycle_in_frame, vdpslots.moments(cycle_in_frame, machine, regs))
    return taken <= (vdpslots.PAPER0[machine] + y) * LINE + PIXEL0


def turns_of(w, machine, port_value=None):
    """the turns of a loop program: {frame: [cycle of each line's write]},
    the frames with 192 writes, one on each line of the paper"""
    by = {}
    for x in w:
        if x[0] == "w" and (port_value is None or int(x[1]) == port_value):
            f, c = int(x[-2]), int(x[-1])
            by.setdefault(f, []).append(c)
    p0 = vdpslots.PAPER0[machine]
    turns = {}
    for f, cs in sorted(by.items()):
        if len(cs) == 192 and [c // LINE for c in cs] == list(range(p0, p0 + 192)):
            inl = {c % LINE for c in cs}
            assert len(inl) == 1, (machine, f, inl)
            turns[f] = cs
    return turns


def ref_t(machine):
    """the T-states are counted from T-state 34 of the signal's line: the
    signal comes 33 2/3 into it (chapter 17), and the CPU can answer it from
    the next T-state on (chapter 32)"""
    return genD.IRQ_LINE[machine] * 228 + 34


def after_signal(line, w, machine):
    """T-state W of frame line LINE, in the next frame, after ref_t"""
    return genD.FRAME_T[machine] + line * 228 + w - ref_t(machine)


def time_run(kind, machine):
    name = f"time{kind}"
    tcl = f'debug set_watchpoint write_io 0x98 {{}} {{ L "w {POS}" }}\n'
    once = (f'set ::r [debug set_bp {sym(name)["t0"]} {{}} {{ L "regs {REGS}"; {VRAM}; '
            'debug remove_bp $::r }]\n')
    w = run(name, 75, tcl + once, machine)
    f0 = int(next(x for x in w if x[0] == "f0")[1])
    regs = [int(v) for v in next(x for x in w if x[0] == "regs")[1:]]
    vram = bytearray(bytes.fromhex(next(x for x in w if x[0] == "vram")[1]))
    fast = sum(1 for x in w if x[0] == "toofast")
    return f0, regs, vram, turns_of(w, machine), fast


def times(res):
    out = {}
    for kind in ("p", "c"):
        table = "patrow" if kind == "p" else "colrow"
        old, new = (0x00, 0xFF) if kind == "p" else (0xFF, 0x1F)
        addrs = rom_words(f"time{kind}", table, 192, sym(f"time{kind}"))
        for machine in MACHINES:
            f0, regs, vram, turns, fast = time_run(kind, machine)
            frames = sorted(turns)[:2 * genD.TIME_COPIES]
            assert len(frames) == 2 * genD.TIME_COPIES and not fast, (kind, machine, len(frames), fast)
            assert frames == list(range(frames[0], frames[0] + len(frames)))
            ws = [turns[f][0] % LINE // 6 for f in frames]
            assert all(turns[f][0] % LINE % 6 == 0 for f in frames)
            assert ws == [ws[0] + (k % genD.TIME_COPIES) for k in range(len(frames))], ws
            values = [new if k % 2 == 0 else old for k in range(len(frames))]
            # the VRAM before the first turn: everything as set up, column 0 OLD
            ph = photos(f"time{kind}", sorted({f - f0 + d for f in frames for d in (-1, 0, 1)}), machine)
            fits, found = [], {}
            for d in (-1, 0, 1):
                seen, ok = [], True
                for f, val in zip(frames, values):
                    p = paper(ph[f - f0 + d])
                    row = []
                    for y in range(192):
                        c0 = p[y, 0:8]
                        want_new = BLACK if val == new else WHITE
                        if (c0 == want_new).all():
                            row.append(1)
                        elif (c0 == (WHITE if want_new == BLACK else BLACK)).all():
                            row.append(0)
                        else:
                            row.append(None)
                    seen.append(row)
                # each line: shown for the early writes, not for the late
                for k, f in enumerate(frames):
                    if any(v is None for v in seen[k]):
                        ok = False
                if ok:
                    early = [k for k, wv in enumerate(ws) if wv <= ws[0] + 2]
                    ok = all(all(seen[k]) for k in early)
                if ok:
                    fits.append(d)
                    found[d] = seen
            assert len(fits) == 1, (kind, machine, fits)
            d = fits[0]
            seen = found[d]
            # the whole photograph against vdpscreen.py: column 0 as seen, the rest as set up
            wrong = 0
            for k, f in enumerate(frames):
                v = bytearray(vram)
                for y in range(192):
                    prev = values[k - 1] if k else old
                    v[addrs[y]] = values[k] if seen[k][y] else prev
                wrong += against(vdpscreen.draw(v, regs), ph[f - f0 + d], regs[7] & 15)
            assert wrong == 0, (kind, machine, wrong)
            # the last T-state that showed, line by line, and the model's
            last, model_last, misses = [], [], 0
            for y in range(192):
                shown = sorted({ws[k] for k in range(len(frames)) if seen[k][y]})
                hidden = sorted({ws[k] for k in range(len(frames)) if not seen[k][y]})
                assert shown and hidden and max(shown) < min(hidden), (kind, machine, y, shown, hidden)
                assert max(shown) + 1 == min(hidden)
                last.append(max(shown))
                line = vdpslots.PAPER0[machine] + y
                mod = [wv for wv in range(ws[0], ws[0] + genD.TIME_COPIES)
                       if shows(line * LINE + 6 * wv, y, machine, regs)]
                model_last.append(max(mod))
                misses += last[-1] != model_last[-1]
                for k in range(len(frames)):
                    misses += seen[k][y] != shows(line * LINE + 6 * ws[k], y, machine, regs)
            if STRICT:
                assert misses == 0, (kind, machine, misses)
            out[f"{kind}_{TAG[machine]}"] = {
                "frames": len(frames), "fit": d, "fast": fast, "w": sorted(set(ws)),
                "photos_wrong": wrong, "model_misses": misses,
                "last": last, "last_kinds": {str(v): [y for y in range(192) if last[y] == v][:3] +
                                             [last.count(v)] for v in sorted(set(last))},
                "last_after": [after_signal(vdpslots.PAPER0[machine] + y, last[y], machine)
                               for y in range(192)],
                "taken": [vdpslots.slot_after(6 * wv, vdpslots.GFX_SLOTS) - 6 * wv
                          for wv in (32, 33)]}
    res["times"] = out


# ---------------------------------------------------------------- beam
def x_of(w, paper=True):
    """chapters 18 and 32: a change of the backdrop written at T-state w of a
    line shows from capture x = 1.5w - 31, w counted as chapter 8 counts, 8
    T-states into an OUT (n),A; when that is a half, from the pixel after it
    on the border, and the pixel before it behind a transparent paper (PAPER
    False: a line all border). Here w is the debugger's, a T-state later:
    1.5w - 32.5"""
    v = 1.5 * w - 32.5
    up = math.ceil(v)
    if v == up or not paper or up < meas.PAPER_X0:
        return up
    return math.floor(v)


def beam_run(machine):
    tcl = (f'debug set_watchpoint write_io 0x99 {{}} {{ L "w $::wp_last_value {POS}" }}\n'
           f'debug set_bp {sym("beam")["wr"]} {{}} {{ L "bp {POS}" }}\n')
    w = run("beam", 50, tcl, machine)
    f0 = int(next(x for x in w if x[0] == "f0")[1])
    fast = sum(1 for x in w if x[0] == "toofast")
    # each OUT of R#7's number: from its start to the debugger's write
    per = LINE * vdpslots.LINES[machine]
    gaps, start = set(), None
    for x in w:
        if x[0] == "bp":
            start = int(x[1]) * per + int(x[2])
        elif x[0] == "w" and int(x[1]) == 0x87 and start is not None:
            gaps.add(int(x[2]) * per + int(x[3]) - start)
            start = None
    return f0, turns_of(w, machine, port_value=0x87), fast, sorted(gaps)


def beam(res):
    out = {}
    for machine in MACHINES:
        f0, turns, fast, gaps = beam_run(machine)
        if STRICT:
            assert gaps == [6 * OUT_N_WRITES], (machine, gaps)
        frames = sorted(turns)[:2 * genD.BEAM_COPIES]
        assert len(frames) == 2 * genD.BEAM_COPIES and not fast, (machine, len(frames))
        assert frames == list(range(frames[0], frames[0] + len(frames)))
        ws = [turns[f][0] % LINE / 6 for f in frames]
        assert all(wv == int(wv) for wv in ws)
        ws = [int(wv) for wv in ws]
        assert ws == [ws[0] + (k % genD.BEAM_COPIES) for k in range(len(frames))], ws
        ph = photos("beam", sorted({f - f0 + d for f in frames for d in (-1, 0, 1)}), machine)
        colour = [genD.BEAM_COLOURS[y % 2] for y in range(192)]
        before = [colour[191]] + colour[:191]
        # the photograph of each turn: the one where every line changes once,
        # from the line before's colour to its own, at an x that is the same
        # for every line and every turn with the same w, and grows with w
        fits = []
        for d in (-1, 0, 1):
            bad, xw = 0, {}
            for f, wv in zip(frames, ws):
                p = ph[f - f0 + d]
                for y in range(192):
                    row = p[meas.PAPER_Y0 + y, meas.DRAWN[0]:meas.DRAWN[1] + 1]
                    xs = [x for x in range(len(row) - 1) if row[x] != row[x + 1]]
                    if len(xs) == 1 and row[0] == before[y] and row[-1] == colour[y]:
                        xw.setdefault(wv, set()).add(xs[0])
                    else:
                        bad += 1
            order = [min(xw[k]) for k in sorted(xw)]
            if bad == 0 and all(len(v) == 1 for v in xw.values()) and order == sorted(set(order)):
                fits.append(d)
        assert len(fits) == 1, (machine, fits)
        d = fits[0]
        at, misses, other = {}, 0, 0
        for f, wv in zip(frames, ws):
            p = ph[f - f0 + d]
            xs_frame = set()
            for y in range(192):
                row = p[meas.PAPER_Y0 + y, meas.DRAWN[0]:meas.DRAWN[1] + 1]
                ch = [x for x in range(len(row) - 1) if row[x] != row[x + 1]]
                assert len(ch) == 1 and row[0] == before[y] and row[-1] == colour[y], (machine, f, y)
                xs_frame.add(ch[0] + 1 + meas.DRAWN[0])
            assert len(xs_frame) == 1, (machine, wv, xs_frame)
            x = xs_frame.pop()
            at[wv] = x
            misses += x != x_of(wv)
            # the border above and under the paper: the last line's colour
            top = p[:meas.PAPER_Y0, meas.DRAWN[0]:meas.DRAWN[1] + 1]
            bottom = p[meas.PAPER_Y0 + 192:, meas.DRAWN[0]:meas.DRAWN[1] + 1]
            other += int((top != colour[191]).sum() + (bottom != colour[191]).sum())
        if STRICT:
            assert misses == 0 and other == 0, (machine, misses, other)
        first = min(wv for wv, x in at.items() if x >= meas.PAPER_X0)
        assert at[first] == meas.PAPER_X0 and at[first - 1] < meas.PAPER_X0, (machine, at)
        p0 = vdpslots.PAPER0[machine]
        if STRICT:
            assert first * 6 == PIXEL0, (machine, first)
        out[TAG[machine]] = {"frames": len(frames), "fit": d, "fast": fast, "out_writes": gaps[0] // 6,
                             "x": {str(k): v for k, v in sorted(at.items())},
                             "rule_misses": misses, "border_wrong": other, "pixel0_w": first,
                             "drawn_after": [after_signal(p0 + y, first, machine) for y in range(192)]}
    res["beam"] = out


# ---------------------------------------------------------------- calls
JUMPS = {"call": 18, "ret": 11}


def priced(name, label):
    """the T-states of routine LABEL from calls.lst, chapter 14's prices for
    every instruction that does not jump, chapter 12's for RET: a list, one
    total for each way out (RET NZ: 12 out, 6 on)"""
    lst = []
    for line in (HERE / f"{name}.lst").read_text().splitlines():
        m = probe.LST.match(line)
        if not m or "..." in line:          # a block of padding, shortened
            continue
        _, at, code, src = probe.lst_fields(m)
        if code:
            lst.append((src.split(";")[0].strip(), at, code))
    s = sym(name)
    rows = [r for r in lst if r[1] >= s[label]]
    t, ways = 0, []
    for src, _, code in rows:
        words = src.split()
        if words[0].endswith(":"):
            words = words[1:]
        op, text = words[0], " ".join(words)
        if text.startswith("ret nz"):
            ways.append(t + 12)
            t += 6
        elif text.startswith("ret"):
            ways.append(t + 11)
            break
        else:
            assert op not in JUMPS, src
            t += cycles.msx(code)
    return ways


def calls_run(machine):
    s = sym("calls")
    tcl = ""
    for r in genD.CALLS:
        n = genD.LAST_Y.get(r, 192) * 64
        tcl += (f'set ::e{r} [debug set_bp {s["e_" + r]} {{}} {{ binary scan [debug read_block {{VRAM}} '
                f'{genD.RESULTS_AT} {n}] H* h; L "res {r} $h"; debug remove_bp $::e{r} }}]\n')
    w = run("calls", 230, tcl, machine)
    got = {x[1]: bytes.fromhex(x[2]) for x in w if x[0] == "res"}
    labels = {}
    for k in range(len(genD.TIMED)):
        labels[f"a{k}"] = s[f"a{k}"]
        labels[f"b{k}"] = s[f"b{k}"]
    t = probe.times(rom("calls"), labels, frames=230, machine=machine)
    took = [round((t[f"b{k}"][0][0] - t[f"a{k}"][0][0]) * CLOCK) for k in range(len(genD.TIMED))]
    return got, took


def calls(res):
    out = {"answers": {}, "times": {}}
    want = {}
    for r in genD.CALLS:
        last = genD.LAST_Y.get(r, 192)
        vals = []
        for y in range(last):
            for c in range(32):
                x = genD.CALL_X(c, y)
                if r in ("pcalc", "ptab", "ppage"):
                    vals.append(masked(x, y, 0xFF, 0x03, "patterns"))
                elif r == "pdown":
                    vals.append(masked(x, y + 1, 0xFF, 0x03, "patterns"))
                else:
                    vals.append(name_of(x, y))
        want[r] = vals
    for machine in MACHINES:
        got, took = calls_run(machine)
        ans = {}
        for r in genD.CALLS:
            g = got[r]
            vals = [g[2 * i] | g[2 * i + 1] << 8 for i in range(len(g) // 2)]
            ans[r] = {"answers": len(vals), "wrong": sum(1 for a, b in zip(vals, want[r]) if a != b)}
            assert len(vals) == len(want[r]) and ans[r]["wrong"] == 0, (machine, r, ans[r])
        out["answers"][TAG[machine]] = ans
        out["times"][TAG[machine]] = took
    assert out["times"]["eu"] == out["times"]["jp"]
    # the listing's prices, with the CALL
    model = []
    for r, x, y in genD.TIMED:
        ways = priced("calls", r)
        if r == "pdown":
            model.append(18 + (ways[0] if (y & 7) != 7 else ways[1]))
        else:
            assert len(ways) == 1
            model.append(18 + ways[0])
    assert model == out["times"]["eu"], (model, out["times"]["eu"])
    out["model"] = model
    out["timed"] = [list(t) for t in genD.TIMED]
    res["calls"] = out


# ---------------------------------------------------------------- rows
def rows(res):
    t, b = res["times"], res["beam"]
    out = []
    for kind in ("p", "c"):
        for m in ("eu", "jp"):
            assert t[f"{kind}_{m}"]["last"] == t[f"p_{m}"]["last"]
    s = sym("addr")              # the tables as sjasmplus made them, photographed in addr
    tab = {lab: rom_words("addr", lab, n, s) for lab, _, _, n, _, _ in genD.TABLES}
    for y in range(192):
        out.append({
            "y": y,
            "pattern": tab["patrow"][y], "colour": tab["colrow"][y],
            "pattern3": tab["patrow3"][y], "colour3": tab["colrow3"][y],
            "name": tab["namerow"][y >> 3],
            "drawn_eu": b["eu"]["drawn_after"][y], "last_eu": t["p_eu"]["last_after"][y],
            "drawn_jp": b["jp"]["drawn_after"][y], "last_jp": t["p_jp"]["last_after"][y]})
    # the table's addresses are the ROM's, every one photographed
    tb = res["tables"]["roms"]["addr"]
    assert tb["wrong"] == 0
    steps = {m: sorted({out[y + 1][f"last_{m}"] - out[y][f"last_{m}"] for y in range(191)})
             for m in ("eu", "jp")}
    res["rows"] = {"rows": out, "last_steps": steps,
                   "lead": {m: sorted({r[f"drawn_{m}"] - r[f"last_{m}"] for r in out})
                            for m in ("eu", "jp")}}


# ---------------------------------------------------------------- before
def chapter(n):
    return json.loads((REPO / f"ch{n:02d}" / f"meas{n:02d}.json").read_text())


def before(res):
    out = {}
    c17, c18, c22, c32 = chapter(17), chapter(18), chapter(22), chapter(32)
    for m in MACHINES:
        sg = c17["signal"][m]
        assert sg["line"] == genD.IRQ_LINE[m] and sg["in_line_vdp"] == 202
        assert abs(sg["t"] - (genD.IRQ_LINE[m] * 228 + 33 + 2 / 3)) < 1e-6
        ln = c18["lines"][m]
        assert ln["paper_line"] == genD.PAPER0[m] == vdpslots.PAPER0[m]
        assert ln["frame"] == genD.FRAME_T[m] and ln["lines"] == genD.LINES[m]
        assert ln["paper_line"] - ln["row0"] == meas.PAPER_Y0
    out["ch17_signal"] = {TAG[m]: c17["signal"][m]["t"] for m in MACHINES}
    out["ch18_paper_line"] = {TAG[m]: c18["lines"][m]["paper_line"] for m in MACHINES}
    # chapter 18's ruler: every change at x = ceil(1.5w - 31), on the border too
    ru = c18["ruler"]
    assert all(x_of(ru["first_w"] + 1 + ru["step"] * k, paper=False) == e
               for k, e in enumerate(ru["edges"]))
    out["ch18_ruler"] = ru["edges"]
    # chapter 22: R#3 = $9F and R#4 = $00, one set for three thirds
    for tag in ("eu", "jp"):
        one = c22["tiles"][tag]["tiles1"]
        assert one["regs"] == [0x9F, 0x00] and one["reads"] == {"names": 768, "patterns": 2048,
                                                                "colours": 2048}
        assert c22["tiles"][tag]["same_photo"]
        for st in c22["masks"][tag]:
            if st["regs"][3:5] in ([0xFF, 0x00], [0x9F, 0x03]):
                assert st["wrong"] == 0 and 2048 in (st["reads"]["patterns"], st["reads"]["colours"])
    out["ch22_one_set"] = {tag: c22["tiles"][tag]["tiles1"]["reads"] for tag in ("eu", "jp")}
    # chapter 32: the half pixel behind the paper
    for tag in ("eu", "jp"):
        h = c32["half"][tag]
        assert h["paper_rule_misses"] == h["odd_w"]
    out["ch32_half"] = {tag: c32["half"][tag]["odd_w"] for tag in ("eu", "jp")}
    # chapter 20's model gives every line of times
    for k, v in res["times"].items():
        assert v["model_misses"] == 0, k
    out["ch20_model_misses"] = 0
    res["before"] = out


# ---------------------------------------------------------------- openmsx
def openmsx(res):
    if not versions.builds():
        res["openmsx"] = {"skipped": "OPENMSX_BUILDS not set"}
        return
    # the cartridges the builds ran, so that the record says which they were
    roms = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()[:16] for p in sorted(HERE.glob("*.rom"))}
    out = versions.every_build(["appD"], [s for s in STEPS if s not in ("openmsx",)],
                               keep=None, values=True)
    res["openmsx"] = {"roms": roms, **out}


# ---------------------------------------------------------------- the main
STEPS = ["tables", "addr", "times", "beam", "calls", "rows", "before", "openmsx"]


def main(names=()):
    res = json.loads(OUT_JSON.read_text()) if names and OUT_JSON.exists() else {}
    for name in STEPS:
        if names and name not in names:
            continue
        sub = dict(res)                 # a step sees the steps before it
        globals()[name](sub)
        res[name] = sub[name]
        res = {k: res[k] for k in STEPS if k in res}
        OUT_JSON.write_text(json.dumps(res, indent=1) + "\n")
        print(" ", name, "ok", flush=True)
    return res


if __name__ == "__main__":
    main(sys.argv[1:])
