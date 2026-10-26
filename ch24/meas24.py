#!/usr/bin/env python3
"""meas24.py -- tiles and the name table, measured.

    python3 gen24.py && ./build.sh && python3 meas24.py
                                  python3 meas24.py meta copies    only these

  meta      meta.rom: the screen against the model, its 768 names against the
            map's, and what expanding the map costs (figure 24.1)
  copies    full.rom, paper.rom and dirty.rom on both machines, every frame:
            the send's T-states and bytes, where in the frame it starts and
            ends, the accesses too soon, the names in the VRAM against the
            copy in the RAM and against the names meant; every frame's
            photograph against the model (figure 24.2)
  late      late.rom: sends begun while the beam draws row 4; in every frame,
            the lines showing the old screen, the new one or both, against the
            times each row was written (figure 24.3)
  spin      spin.rom: the coins turned by 32 bytes of shapes (figure 24.4)
  peek      peek.rom: all the names read back with RDVRM, with an address and an
            IN each, and from the copy: the T-states of each
  prices    each send's T-states from its listing, against the debugger's
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
sys.path.insert(0, str(REPO / "ch20"))
sys.path.insert(0, str(HERE))
import meas        # noqa: E402
import msxcap      # noqa: E402
import probe as dbg  # noqa: E402
import versions    # noqa: E402
import cycles      # noqa: E402  (chapter 14: an instruction's price)
import vdpslots    # noqa: E402  (chapter 20: where the paper is in a frame)
import vdpscreen   # noqa: E402  (chapter 23's model, copied)
import gen24       # noqa: E402

CAPS = HERE / "captures"
EU, JP = "MSXBOOK_EU16", "MSXBOOK_JP16"
TAG = {EU: "eu", JP: "jp"}
CLOCK = 3579545
SHOT = 30
FILM = 110
POS = "[machine_info VDP_frame_count] [machine_info VDP_cycle_in_frame] [machine_info time]"
REGS = " ".join(f"[debug read {{VDP regs}} {i}]" for i in range(8))
VRAM = 'binary scan [debug read_block {VRAM} 0 16384] H* h; L "vram $h"'
NAMES = 'binary scan [debug read_block {VRAM} 6144 768] H* h; L "vnames $h"'
COPY = (f'binary scan [debug read_block memory {gen24.NAMES_RAM} 768] H* h; L "copy $h"; '
        f'binary scan [debug read_block memory {gen24.DIRTY_RAM} 24] H* h; L "dirty $h"')
F0 = 'L "f0 [machine_info VDP_frame_count]"\n'
SENDS = ["full", "paper", "dirty"]
# every access to the VRAM too soon, counted and logged with its frame
TOO_FAST = ('set ::toofast 0\nproc ::toofast_cb {args} { incr ::toofast; '
            'L "toofast [machine_info time]" }\n'
            'set VDP.too_fast_vram_access_callback ::toofast_cb\n')

PALETTE = [tuple(c) for c in json.loads((REPO / "ch01" / "meas01.json").read_text())["palette"]["rgb"]]
CODE = {rgb: n for n, rgb in enumerate(PALETTE) if n}


def rom(name):
    return HERE / f"{name}.rom"


def sym(name):
    return dbg.sym(HERE / f"{name}.sym")


def run(name, frames, tcl, machine=EU):
    lines = msxcap.run_tcl(rom(name), frames, TOO_FAST + tcl, machine=machine)
    return [l.split() for l in lines]


def shots(name, frames, machine):
    return msxcap.capture(rom(name), frames, CAPS, f"{name}_{TAG[machine]}_f", machine=machine)


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


def once(addr, body, tag):
    return f'set ::{tag} [debug set_bp {addr} {{}} {{ {body}; debug remove_bp $::{tag} }}]\n'


# ---------------------------------------------------------------- prices
JUMPS = {"djnz": (14, 9), "jr": (13, 8), "call": (18, 18), "ret": (11, 11), "jp": (11, 11)}


def lst_lines(name):
    out = []
    for line in (HERE / f"{name}.lst").read_text().splitlines():
        m = dbg.LST.match(line)
        if not m or "..." in m.group(3)[1:13] or not m.group(3)[1:13].strip():
            continue
        _, a, code, src = dbg.lst_fields(m)
        src = re.sub(r"^\s*[\w.]+:", "", src.split(";")[0].lstrip(">")).strip()
        if src and not src.lower().startswith(("db", "dw", "ds", "align")):
            out.append((src, a, code))
    return out


def price(src, code, moved=0):
    op = src.split()[0].lower()
    if op == "ret" and len(src.split()) > 1:
        return 12, 6
    if op in JUMPS:
        return JUMPS[op]
    if op == "otir":
        t = 23 * (moved - 1) + 18
        return t, t
    if op == "outi":
        return 18, 18                                   # chapter 19
    if op == "ldi":
        return 18, 18                                   # Zilog's 16, and two M1s
    t = cycles.msx(code)
    return t, t


def routine(name, label, upto=None):
    """[(source, taken, not taken)] of the instructions from LABEL to UPTO, or
    to the routine's first plain RET, included"""
    s = sym(name)
    out = []
    for src, a, c in lst_lines(name):
        if a < s[label]:
            continue
        if upto and a >= s[upto]:
            break
        out.append((src.replace(" ", "").lower(), c, src))
        if src.strip().lower() == "ret" and not upto:
            break
    return out


def p_of(ins, moved=0, taken=True):
    t, n = price(ins[2], ins[1], moved)
    return t if taken else n


def send_prices(name):
    """each send's T-states from its listing, the CALL included: full and paper
    as a sum; dirty as A + B x dirty rows"""
    ins = routine(name, "send")
    call = 18
    if name == "full":
        return {"t": call + sum(p_of(i, 256) for i in ins)}
    if name == "paper":
        head = sum(p_of(i) for i in ins if not i[0].startswith(("ldb,0", "outi", "jpnz", "decd", "jrnz", "ret")))
        get = {i[0]: i for i in ins}
        page = p_of(get["ldb,0"]) + 256 * (p_of(get["outi"]) + p_of(get["jpnz,.byte"])) + p_of(get["decd"])
        return {"t": call + head + 3 * page + 2 * p_of(get["jrnz,.page"]) +
                p_of(get["jrnz,.page"], taken=False) + p_of(get["ret"])}
    # dirty: the instructions of a clean row, and the more of a dirty one
    get = {}
    for i in ins:
        get.setdefault(i[0], i)
    head = p_of(get["ldde,$1800|$4000"]) + p_of(get["ldhl,dirty"])
    clean = (p_of(get["lda,(hl)"]) + p_of(get["ora"]) + p_of(get["jrz,.next"]) +
             p_of(get["lda,e"]) + p_of(get["adda,32"]) + p_of(get["lde,a"]) + p_of(get["jrnc,.same"]) +
             p_of(get["incl"]) + p_of(get["lda,l"]) + p_of(get["cp24"]) + p_of(get["jrnz,.row"]))
    body = ins[[k for k, i in enumerate(ins) if i[0] == "jrz,.next"][0] + 1:
               [k for k, i in enumerate(ins) if i[0] == "pophl"][0] + 1]
    dirty = sum(p_of(i, 32) for i in body) - (p_of(get["jrz,.next"]) - p_of(get["jrz,.next"], taken=False))
    carry = p_of(get["jrnc,.same"], taken=False) + p_of(get["incd"]) - p_of(get["jrnc,.same"])
    last = p_of(get["jrnz,.row"], taken=False) - p_of(get["jrnz,.row"])
    a = call + head + 24 * clean + 3 * carry + last + p_of(get["ret"])
    return {"a": a, "b": dirty, "clean_row": clean, "carry": carry}


# ---------------------------------------------------------------- meta
def meta_():
    s = sym("meta")
    tcl = (once(s["e0"], 'L "e0 [machine_info time]"', "a") +
           once(s["e1"], 'L "e1 [machine_info time]"', "b") +
           once(s["done"], f'L "regs {REGS}"; {VRAM}', "c"))
    out = {}
    want = gen24.names_of(gen24.MAP)
    for machine in (EU, JP):
        w = run("meta", SHOT, tcl, machine)
        assert not [x for x in w if x[0] == "toofast"]
        regs = [int(v) for v in next(x for x in w if x[0] == "regs")[1:]]
        vram = bytes.fromhex(next(x for x in w if x[0] == "vram")[1])
        photo = codes(shots("meta", [SHOT], machine)[SHOT])
        bad = against(vdpscreen.draw(vram, regs), photo, regs[7] & 15)
        assert bad == 0 and list(vram[0x1800:0x1B00]) == want
        e0 = float(next(x for x in w if x[0] == "e0")[1])
        e1 = float(next(x for x in w if x[0] == "e1")[1])
        out[TAG[machine]] = {"wrong": bad, "names_right": 768, "expand_t": round((e1 - e0) * CLOCK)}
    assert out["eu"]["expand_t"] == out["jp"]["expand_t"]
    out["bytes"] = {"map": len(gen24.MAP), "metas": 4 * len(gen24.METAS), "names": 768,
                    "tiles": len(gen24.TILES), "tile_bytes": 16 * len(gen24.TILES)}
    used = {}
    for n in want:
        used[n] = used.get(n, 0) + 1
    out["names_used"] = len(used)
    return out


# ---------------------------------------------------------------- copies
def copy_run(name, machine):
    s = sym(name)
    tcl = (f'debug set_bp {s["m0"]} {{}} {{ set ::n 0; L "m0 {POS}"; {COPY} }}\n'
           f'debug set_bp {s["m1"]} {{}} {{ L "m1 {POS} $::n"; {NAMES} }}\n'
           'set ::n 0\ndebug set_watchpoint write_io 0x98 {} { incr ::n }\n' +
           once(s["m0"], f'L "regs {REGS}"; {VRAM}', "v") + F0)
    w = run(name, FILM, tcl, machine)
    f0 = int(next(x for x in w if x[0] == "f0")[1])
    regs = [int(v) for v in next(x for x in w if x[0] == "regs")[1:]]
    base = bytearray(bytes.fromhex(next(x for x in w if x[0] == "vram")[1]))
    m0 = [x for x in w if x[0] == "m0"]
    m1 = [x for x in w if x[0] == "m1"]
    copies = [list(bytes.fromhex(x[1])) for x in w if x[0] == "copy"]
    dirties = [list(bytes.fromhex(x[1])) for x in w if x[0] == "dirty"]
    vnames = [list(bytes.fromhex(x[1])) for x in w if x[0] == "vnames"]
    fast = [float(x[1]) for x in w if x[0] == "toofast"]
    assert len(m0) == len(m1) == len(copies) == len(vnames) == gen24.FRAMES, (name, len(m0))
    want = [gen24.names_of(m) for m in gen24.frames()[1:]]
    frame_len = vdpslots.LINES[machine] * vdpslots.LINE
    paper0 = vdpslots.PAPER0[machine] * vdpslots.LINE + vdpslots.BORDER_IN
    res = {"cost": [], "bytes": [], "rows": [], "start": [], "end_in_paper": [],
           "fast": [], "wrong_names": [], "model": []}
    for k, (a, b) in enumerate(zip(m0, m1)):
        assert copies[k] == want[k], (name, k)                # the copy is what was meant
        res["cost"].append(round((float(b[3]) - float(a[3])) * CLOCK))
        res["bytes"].append(int(b[4]))
        res["rows"].append(sum(1 for d in dirties[k] if d))
        c0, c1 = int(a[2]), int(b[2])
        res["start"].append(c0 // vdpslots.LINE)
        # how far into the paper the send ran: T-states after the paper began
        end = (int(b[1]) - int(a[1])) * frame_len + c1
        start_paper = paper0 + (frame_len if c0 >= paper0 else 0)
        res["end_in_paper"].append(max(0, (end - start_paper) // vdpslots.PER_T))
        res.setdefault("spare", []).append((start_paper - end) // vdpslots.PER_T)
        res["fast"].append(sum(1 for f in fast if float(a[3]) <= f <= float(b[3])))
        res["wrong_names"].append(sum(1 for x, y in zip(vnames[k], want[k]) if x != y))
        res.setdefault("wrong_at", []).append([i for i, (x, y) in enumerate(zip(vnames[k], want[k]))
                                               if x != y])
    # the photographs: the frame after each send, counted from the frame its
    # send began in, and fitted (0, 1 or 2 frames on)
    ends = [int(a[1]) - f0 for a in m0]
    films = sorted({e + d for e in ends for d in (0, 1, 2)})
    pngs = shots(name, films, machine)

    def model(k):
        v = bytearray(base)
        v[0x1800:0x1B00] = bytes(vnames[k])
        return vdpscreen.draw(v, regs)
    fits = [d for d in (0, 1, 2)
            if all(against(model(k), codes(pngs[ends[k] + d]), regs[7] & 15) == 0
                   for k in (0, gen24.FRAMES // 2, gen24.FRAMES - 1))]
    assert len(fits) == 1, (name, machine, fits)
    d = fits[0]
    for k in range(gen24.FRAMES):
        res["model"].append(against(model(k), codes(pngs[ends[k] + d]), regs[7] & 15))
    for f in films:
        if f not in [e + d for e in ends]:
            pngs[f].unlink()
    assert all(v == 0 for v in res["model"]), (name, machine, res["model"])
    res["films"] = [e + d for e in ends]
    res["fast_total"] = len(fast)
    return res


def copies():
    out = {}
    for name in SENDS:
        r = {TAG[m]: copy_run(name, m) for m in (EU, JP)}
        e, j = r["eu"], r["jp"]
        assert e["cost"] == j["cost"] and e["bytes"] == j["bytes"], name
        r["summary"] = {t: {"cost": [min(r[t]["cost"]), max(r[t]["cost"])],
                            "bytes": sorted(set(r[t]["bytes"])),
                            "into_paper": max(r[t]["end_in_paper"]),
                            "spare": min(r[t]["spare"]),
                            "fast": r[t]["fast_total"],
                            "fast_per_send": [min(r[t]["fast"]), max(r[t]["fast"])],
                            "frames_wrong": sum(1 for v in r[t]["wrong_names"] if v),
                            "wrong_names": [min(r[t]["wrong_names"]), max(r[t]["wrong_names"])]}
                        for t in ("eu", "jp")}
        out[name] = r
    # the dirty rows: the cost against the rows sent
    d = out["dirty"]["eu"]
    by = {}
    for rows, t in zip(d["rows"], d["cost"]):
        by.setdefault(rows, set()).add(t)
    out["dirty_by_rows"] = {str(k): sorted(v) for k, v in sorted(by.items())}
    return out


# ---------------------------------------------------------------- late
def late():
    """each send begun in the paper: the lines of each frame that show the
    old screen, the new one, or some of each, against the times at which the
    debugger saw each row's first and last name written"""
    s = sym("late")
    tcl = (f'debug set_bp {s["m0"]} {{}} {{ set ::n 0; L "m0 {POS}"; {NAMES} }}\n'
           f'debug set_bp {s["m1"]} {{}} {{ L "m1 {POS}"; {NAMES} }}\n'
           'set ::n 0\ndebug set_watchpoint write_io 0x98 {} { incr ::n; '
           'if {$::n % 32 == 1 || $::n % 32 == 0} { L "w $::n [machine_info VDP_frame_count] '
           '[machine_info VDP_cycle_in_frame]" } }\n' +
           once(s["m0"], f'L "regs {REGS}"; {VRAM}', "v") + F0)
    out = {}
    for machine in (EU, JP):
        w = run("late", 40, tcl, machine)
        f0 = int(next(x for x in w if x[0] == "f0")[1])
        regs = [int(v) for v in next(x for x in w if x[0] == "regs")[1:]]
        base = bytearray(bytes.fromhex(next(x for x in w if x[0] == "vram")[1]))
        m0 = [x for x in w if x[0] == "m0"]
        m1 = [x for x in w if x[0] == "m1"]
        names = [list(bytes.fromhex(x[1])) for x in w if x[0] == "vnames"]
        fast = [x for x in w if x[0] == "toofast"]
        assert len(m0) == len(m1) == gen24.TEARS and not fast
        segs, cur = [], None                    # the writes between each m0 and its m1
        for x in w:
            if x[0] == "m0":
                cur = []
            elif x[0] == "w" and cur is not None:
                cur.append(x)
            elif x[0] == "m1":
                segs.append(cur)
                cur = None
        frame_len = vdpslots.LINES[machine] * vdpslots.LINE
        p0 = vdpslots.PAPER0[machine]
        res = {"start_line": [], "lines": [], "first_new": [], "last_old": [], "mixed": [],
               "predicted": [], "cost": []}
        frames = [int(a[1]) - f0 for a in m0]
        pngs = shots("late", sorted({f + d for f in frames for d in (0, 1)}), machine)
        for k, (a, b) in enumerate(zip(m0, m1)):
            old, new = names[2 * k], names[2 * k + 1]
            res["cost"].append(round((float(b[3]) - float(a[3])) * CLOCK))
            c0 = int(a[2])
            res["start_line"].append(c0 // vdpslots.LINE - p0)     # the paper's line
            # each row's first and last name: written at which cycle of the frame
            ws = segs[k]
            first = {(int(x[1]) - 1) // 32: (int(x[2]) - int(a[1])) * frame_len + int(x[3])
                     for x in ws if int(x[1]) % 32 == 1}
            last = {(int(x[1]) - 1) // 32: (int(x[2]) - int(a[1])) * frame_len + int(x[3])
                    for x in ws if int(x[1]) % 32 == 0}
            assert len(first) == len(last) == 24, (machine, k, len(first), len(last))
            pred = []
            for line in range(192):
                r = line // 8
                begin, end = (p0 + line) * vdpslots.LINE, (p0 + line + 1) * vdpslots.LINE
                pred.append("new" if last[r] < begin else "old" if first[r] >= end else "mixed")
            vo, vn = bytearray(base), bytearray(base)
            vo[0x1800:0x1B00], vn[0x1800:0x1B00] = bytes(old), bytes(new)
            mo, mn = vdpscreen.draw(vo, regs), vdpscreen.draw(vn, regs)
            best = None
            for d in (0, 1):
                photo = codes(pngs[frames[k] + d])
                paper = [row[meas.PAPER_X0:meas.PAPER_X0 + 256]
                         for row in photo[meas.PAPER_Y0:meas.PAPER_Y0 + 192]]
                cls = []
                for line in range(192):
                    if mo[line] == mn[line]:
                        cls.append("same" if paper[line] == mo[line] else "wrong")
                    else:
                        cls.append("old" if paper[line] == mo[line] else
                                   "new" if paper[line] == mn[line] else "mixed")
                if "old" in cls and "new" in cls and \
                        max(i for i, c in enumerate(cls) if c == "old") < cls.index("new"):
                    best = (d, cls)                     # old above, new below
            assert best, (machine, k)
            d, cls = best
            assert "wrong" not in cls
            # every line the times say is old or new is so in the photograph
            for line in range(192):
                if pred[line] != "mixed" and cls[line] in ("old", "new"):
                    assert cls[line] == pred[line], (machine, k, line, cls[line], pred[line])
            res["lines"].append(cls)
            res["first_new"].append(min(i for i, c in enumerate(cls) if c == "new"))
            res["last_old"].append(max(i for i, c in enumerate(cls) if c == "old"))
            res["mixed"].append([i for i, c in enumerate(cls) if c == "mixed"])
            res["predicted"].append([i for i, c in enumerate(pred) if c == "mixed"])
            res.setdefault("films", []).append(frames[k] + d)
        for f in {f + d for f in frames for d in (0, 1)} - set(res["films"]):
            pngs[f].unlink()
        out[TAG[machine]] = res
    for t in ("eu", "jp"):
        r = out[t]
        out[t + "_summary"] = {"start_line": sorted(set(r["start_line"])),
                               "first_new": sorted(set(r["first_new"])),
                               "last_old": sorted(set(r["last_old"])),
                               "mixed": sorted({tuple(x) for x in r["mixed"]}),
                               "predicted_mixed": sorted({tuple(x) for x in r["predicted"]}),
                               "cost": sorted(set(r["cost"]))}
    return out


# ---------------------------------------------------------------- spin
def spin():
    s = sym("spin")
    shapes = 'binary scan [debug read_block {VRAM} 48 32] H* h; L "vshapes $h"'
    tcl = (f'debug set_bp {s["m0"]} {{}} {{ set ::n 0; L "m0 {POS}" }}\n'
           f'debug set_bp {s["m1"]} {{}} {{ L "m1 {POS} $::n"; {shapes} }}\n'
           'set ::n 0\ndebug set_watchpoint write_io 0x98 {} { incr ::n }\n' +
           once(s["m0"], f'L "regs {REGS}"; {VRAM}', "v") + F0)
    phases = gen24.coin_phases()
    out = {}
    for machine in (EU, JP):
        w = run("spin", 60, tcl, machine)
        assert not [x for x in w if x[0] == "toofast"]
        f0 = int(next(x for x in w if x[0] == "f0")[1])
        regs = [int(v) for v in next(x for x in w if x[0] == "regs")[1:]]
        base = bytearray(bytes.fromhex(next(x for x in w if x[0] == "vram")[1]))
        m0 = [x for x in w if x[0] == "m0"]
        m1 = [x for x in w if x[0] == "m1"]
        vs = [list(bytes.fromhex(x[1])) for x in w if x[0] == "vshapes"]
        assert len(m0) == gen24.SPINS
        frames = [int(a[1]) - f0 for a in m0]
        pngs = shots("spin", sorted({f + d for f in frames for d in (0, 1, 2)}), machine)
        res = {"cost": [], "bytes": [], "phase": [], "model": [], "films": []}

        def model(k):
            v = bytearray(base)
            v[48:80] = bytes(vs[k])
            return vdpscreen.draw(v, regs)
        fits = [d for d in (0, 1, 2) if all(against(model(k), codes(pngs[frames[k] + d]),
                                                    regs[7] & 15) == 0 for k in (0, 3, 7))]
        # the drawing stays for four frames: the first frame that shows it
        assert fits and 0 not in fits, (machine, fits)
        d = fits[0]
        for k, (a, b) in enumerate(zip(m0, m1)):
            res["cost"].append(round((float(b[3]) - float(a[3])) * CLOCK))
            res["bytes"].append(int(b[4]))
            res["phase"].append(vs[k] == phases[(k + 1) % 4])    # the drawing meant
            res["model"].append(against(model(k), codes(pngs[frames[k] + d]), regs[7] & 15))
            res["films"].append(frames[k] + d)
        for f in {f + dd for f in frames for dd in (0, 1, 2)} - set(res["films"]):
            pngs[f].unlink()
        assert all(v == 0 for v in res["model"])
        assert all(res["phase"]), res["phase"]
        res["gaps"] = sorted({b - a for a, b in zip(frames, frames[1:])})
        out[TAG[machine]] = res
    assert out["eu"]["cost"] == out["jp"]["cost"]
    out["coin_names"] = 4 * len(gen24.COINS)
    return out


# ---------------------------------------------------------------- peek
def peek():
    s = sym("peek")
    tcl = "".join(once(s[f"p{i}"], f'L "p{i} [machine_info time]"', f"p{i}") for i in range(4))
    dump = "; ".join(f'binary scan [debug read_block memory {b} 768] H* h; L "buf{i} $h"'
                     for i, b in enumerate((gen24.BUF1, gen24.BUF2, gen24.BUF3)))
    tcl += once(s["done"], dump, "d")
    want = gen24.names_of(gen24.MAP)
    out = {}
    for machine in (EU, JP):
        w = run("peek", SHOT, tcl, machine)
        assert not [x for x in w if x[0] == "toofast"]
        t = [float(next(x for x in w if x[0] == f"p{i}")[1]) for i in range(4)]
        bufs = [list(bytes.fromhex(next(x for x in w if x[0] == f"buf{i}")[1])) for i in range(3)]
        assert all(b == want for b in bufs), machine
        cost = [round((t[i + 1] - t[i]) * CLOCK) for i in range(3)]
        out[TAG[machine]] = {"rdvrm": cost[0], "in": cost[1], "copy": cost[2]}
    assert out["eu"] == out["jp"]
    e = out["eu"]
    out["per_name"] = {k: round(v / 768, 1) for k, v in e.items()}
    return out


def expand_price():
    """expand's T-states, the CALL included, from meta.asm's listing: put's JR NC
    jumps unless the copy's low address byte carries"""
    put = routine("meta", "put")
    ex = routine("meta", "expand")

    def p_put(carry):
        t = 0
        for i in put:
            if i[0] == "jrnc,.low":
                t += p_of(i, taken=not carry)
            elif i[0] == "incd":
                t += p_of(i) if carry else 0
            else:
                t += p_of(i)
        return t
    get = {i[0]: i for i in ex}
    col = sum(p_of(get[k]) for k in ("lda,(hl)", "pushhl", "callput", "pophl", "inchl", "ince",
                                     "lda,e", "cp16", "jrnz,.col"))
    row = sum(p_of(get[k]) for k in ("lde,0", "incd", "lda,d", "cp12", "jrnz,.row"))
    last = p_of(get["jrnz,.col"]) - p_of(get["jrnz,.col"], taken=False)
    t = 18 + p_of(get["ldhl,map"]) + p_of(get["ldd,0"]) + p_of(get["ret"])
    for r in range(12):
        t += row - last
        for c in range(16):
            low = (gen24.NAMES_RAM + 64 * r + 2 * c) & 0xFF
            t += col + p_put(low + 30 > 255)
    t -= p_of(get["jrnz,.row"]) - p_of(get["jrnz,.row"], taken=False)
    return {"t": t, "put": p_put(False), "put_carry": p_put(True)}


# ---------------------------------------------------------------- prices
def prices():
    m = json.loads((HERE / "meas24.json").read_text())["copies"]
    out = {n: send_prices(n) for n in SENDS}
    out["expand"] = expand_price()
    meta = json.loads((HERE / "meas24.json").read_text())["meta"]
    assert meta["eu"]["expand_t"] == out["expand"]["t"], (meta["eu"]["expand_t"], out["expand"])
    assert set(m["full"]["eu"]["cost"]) == {out["full"]["t"]}, (m["full"]["eu"]["cost"][:3], out["full"])
    assert set(m["paper"]["eu"]["cost"]) == {out["paper"]["t"]}, (m["paper"]["eu"]["cost"][:3], out["paper"])
    for rows, ts in m["dirty_by_rows"].items():
        assert ts == [out["dirty"]["a"] + int(rows) * out["dirty"]["b"]], (rows, ts, out["dirty"])
    return out


# ---------------------------------------------------------------- answers
def answers():
    m = json.loads((HERE / "meas24.json").read_text())
    p = m["prices"]
    out = {}
    # 1: the map's 192 bytes and the metatiles' 4 each, against 768 names
    b = m["meta"]["bytes"]
    out["q1"] = {"metatile_bytes": b["map"] + b["metas"], "names": b["names"]}
    # 2: the lines a frame does not draw, against a full copy with OTIR
    out["q2"] = {t: (vdpslots.LINES[mc] - 192) * 228 for t, mc in (("eu", EU), ("jp", JP))}
    out["q2"]["full"] = p["full"]["t"]
    # 3: dirty.asm with every row dirty, by the prices
    out["q3"] = p["dirty"]["a"] + 24 * p["dirty"]["b"]
    # 4: the rows dirty.asm can send in the lines a 60 Hz frame does not draw
    out["q4"] = (out["q2"]["jp"] - p["dirty"]["a"]) // p["dirty"]["b"]
    # 5: a name of the copy, row 18, column 7: its address in the RAM and the VRAM
    out["q5"] = {"ram": gen24.NAMES_RAM + 32 * 18 + 7, "vram": 0x1800 + 32 * 18 + 7}
    return out


# ---------------------------------------------------------------- openmsx
OPENMSX_SECTIONS = ["meta", "copies", "late", "spin", "peek"]


def openmsx():
    if not versions.builds():
        return {"skipped": "OPENMSX_BUILDS not set"}
    return versions.every_build(["ch24"], OPENMSX_SECTIONS)


SECTIONS = {"meta": meta_, "copies": copies, "late": late, "spin": spin, "peek": peek,
            "prices": prices,
            "answers": answers,
            "openmsx": openmsx}


def main(names=()):
    CAPS.mkdir(exist_ok=True)
    path = HERE / "meas24.json"
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
