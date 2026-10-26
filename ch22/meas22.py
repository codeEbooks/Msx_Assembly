#!/usr/bin/env python3
"""meas22.py -- Graphic II, measured.

    python3 gen22.py && ./build.sh && python3 meas22.py
                                  python3 meas22.py bytes masks    only these

The debugger reads the VDP's registers and the whole VRAM; vdpscreen.py,
given them, has to draw the photograph, pixel for pixel, paper and border.
Then the photographs are read the other way: what they show of each byte.

  bytes     lowbyte.rom and highbyte.rom on both machines: each of the 6,144
            bytes of the patterns read back off the two photographs, and its
            address against vdpscreen.address() (figure 22.1)
  colours   colours.rom: each of the 6,144 strips of 8 x 1, its two colours
            read off the photograph, against the colour byte gen22.py gave it
  diag      diag.rom: the two lines (figure 22.2); vaddr's T-states, at
            every call, against its price; the whole drawing against its price
  down      vline.rom: the line down the screen; down's T-states at every
            call, and the whole line, against their prices
  tiles     tiles3.rom and tiles1.rom: the same photograph (figure 22.3); the
            bytes each writes and their time, and the VRAM each makes the VDP read
  masks     masks.rom: nine states of R#0, R#1, R#3 and R#4; in each third of
            each Graphic II photograph, the digit and its ink (figure 22.4)
  leak      WHERE IT BREAKS: leak.rom, a Graphic I page and M3, then the fix,
            with and without vdpscreen's rule 6 (figure 22.5)
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
import gen22       # noqa: E402
import vdpscreen   # noqa: E402

CAPS = HERE / "captures"
EU, JP = "MSXBOOK_EU16", "MSXBOOK_JP16"
TAG = {EU: "eu", JP: "jp"}
CLOCK = 3579545
SHOT = 30                   # the film frame photographed: every page is finished by then
POS = "[machine_info VDP_frame_count]"
REGS = " ".join(f"[debug read {{VDP regs}} {i}]" for i in range(8))
VRAM = 'binary scan [debug read_block {VRAM} 0 16384] H* h; L "vram $h"'
F0 = 'L "f0 [machine_info VDP_frame_count]"\n'
BLACK, LIGHT_GREEN, DARK_BLUE, WHITE = gen22.BLACK, gen22.LIGHT_GREEN, gen22.DARK_BLUE, gen22.WHITE

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
    pixels). In text mode, and in M1 with M3, every first pixel from 0 to 16
    is tried, and the one that makes no pixel wrong is the measurement"""
    backdrop = regs[7] & 15
    if vdpscreen.mode(regs) not in ("text", "text+graphic2"):
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


def paper_px(photo, x, y):
    return photo[meas.PAPER_Y0 + y][meas.PAPER_X0 + x]


def page(name, machine):
    """the registers, the VRAM and the photograph of a finished page, and the
    photograph checked against the model"""
    regs, vram = state(name, machine, "done")
    photo = codes(shot(name, SHOT, machine))
    bad, _ = check(vram, regs, photo)
    assert bad == 0, (name, machine, bad)
    return regs, vram, photo


# ---------------------------------------------------------------- prices
JUMPS = {"djnz": (14, 9), "jr": (13, 8),               # taken, not taken (chapter 11)
         "call": (18, 18), "ret": (11, 11)}            # chapter 12, as chapter 19 prices them


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
    if op == "ret" and len(src.split()) > 1:
        return 12, 6                                    # RET cc (chapter 11)
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


def span(name, a0, a1):
    """the instructions from address A0 up to A1, each once, every jump taken"""
    return sum(price(src, c, 0)[0] for src, a, c in lst_lines(name) if a0 <= a < a1)


def routine(name, label, taken=True):
    """a routine from LABEL to its RET, once: its first RET cc taken, or every
    RET cc not taken"""
    t = 0
    for src, a, c in lst_lines(name):
        if a >= sym(name)[label]:
            op = src.lower().split()
            t += price(src, c, 0)[0 if taken or op[0] != "ret" else 1]
            if op == ["ret"] or op[0] == "ret" and taken:
                return t
    raise ValueError(label)


# ---------------------------------------------------------------- bytes
def read_byte(photo, x, y, ink):
    """the 8 pixels from (x, y) of the paper as a byte, bit 7 on the left:
    1 where the pixel is the ink"""
    return sum(0x80 >> i for i in range(8) if paper_px(photo, x + i, y) == ink)


EXAMPLES = [(0, 0), (8, 0), (0, 1), (7, 7), (0, 8), (255, 63), (0, 64), (100, 150), (255, 191)]


def bytes_():
    out = {}
    for machine in (EU, JP):
        photos = {}
        for name in ("lowbyte", "highbyte"):
            regs, vram, photos[name] = page(name, machine)
            assert vdpscreen.mode(regs) == "graphic2"
        right, seen = 0, set()
        for y in range(192):
            for x in range(0, 256, 8):
                lo = read_byte(photos["lowbyte"], x, y, BLACK)
                hi = read_byte(photos["highbyte"], x, y, BLACK)
                right += hi << 8 | lo == vdpscreen.address(x, y)
                seen.add(hi << 8 | lo)
        assert right == 6144 and seen == set(range(6144)), (machine, right, len(seen))
        out[TAG[machine]] = {"right": right, "different": len(seen),
                             "ink_low": sum(c == BLACK for r in photos["lowbyte"] for c in r),
                             "ink_high": sum(c == BLACK for r in photos["highbyte"] for c in r)}
    out["examples"] = [{"x": x, "y": y, "address": vdpscreen.address(x, y), "bit": 7 - x % 8}
                       for x, y in EXAMPLES]
    return out


# ---------------------------------------------------------------- colours
def colours():
    want = gen22.colour_bytes()
    out = {}
    for machine in (EU, JP):
        regs, vram, photo = page("colours", machine)
        right = vram_right = one_colour = 0
        for y in range(192):
            for x in range(0, 256, 8):
                a = vdpscreen.address(x, y)
                ink = {paper_px(photo, x + i, y) for i in range(4)}
                paper = {paper_px(photo, x + i, y) for i in range(4, 8)}
                one_colour += len(ink) == len(paper) == 1
                if len(ink) == len(paper) == 1:
                    right += (min(ink) << 4 | min(paper)) == want[a]
                vram_right += vram[0x2000 + a] == want[a]
        assert right == vram_right == 6144, (machine, right, vram_right)
        out[TAG[machine]] = {"strips_right": right, "one_colour_each_half": one_colour,
                             "vram_right": vram_right}
    out["pairs"] = len(set(want))
    return out


# ---------------------------------------------------------------- diag
def diag():
    s = sym("diag")
    lines = lst_lines("diag")
    jr = next(a for src, a, c in lines if a > s["line"] and src.lower().replace(" ", "") == "jrnz,line")
    after = next(a for src, a, c in lines if a > jr)
    want = {(y, y) for y in range(192)} | {(y + 64, y) for y in range(192)}
    tcl = (f'debug set_bp {s["pixel"]} {{}} {{ L "v0 [machine_info time]" }}\n'
           f'debug set_bp {s["v1"]} {{}} {{ L "v1 [machine_info time]" }}\n' +
           once(s["line"], 'L "line [machine_info time]"', "a") +
           once(s["done"], f'L "done [machine_info time] {POS}"', "b") + F0)
    out = {}
    for machine in (EU, JP):
        regs, vram, photo = page("diag", machine)
        ink = {(x, y) for y in range(192) for x in range(256) if paper_px(photo, x, y) != WHITE}
        w = run("diag", SHOT, tcl, machine)
        t0 = [float(x[1]) for x in w if x[0] == "v0"]
        t1 = [float(x[1]) for x in w if x[0] == "v1"]
        line = float(next(x for x in w if x[0] == "line")[1])
        done = next(x for x in w if x[0] == "done")
        ts = sorted({round((b - a) * CLOCK) for a, b in zip(t0, t1)})
        whole = round((float(done[1]) - line) * CLOCK)
        assert ink == want and len(t0) == len(t1) == 384, (machine, len(ink), len(t0))
        out[TAG[machine]] = {"ink": len(ink), "ink_right": ink == want, "calls": len(t0),
                             "vaddr_t": ts, "whole_t": whole,
                             "frames": round(whole / meas.T_PER_FRAME[machine], 2)}
    vaddr = routine("diag", "vaddr")
    call = span("diag", s["pixel"], s["v1"])
    pixel = routine("diag", "pixel")
    body = span("diag", s["line"], after)
    whole = 192 * body - 5 + 384 * (pixel + vaddr) + span("diag", after, s["done"])
    out["priced"] = {"vaddr": vaddr, "call": call, "vaddr_call": vaddr + call,
                     "pixel": pixel + vaddr, "loop": body, "whole": whole}
    for t in ("eu", "jp"):
        assert out[t]["vaddr_t"] == [vaddr + call], (out[t]["vaddr_t"], vaddr + call)
        assert out[t]["whole_t"] == whole, (out[t]["whole_t"], whole)
    return out


# ---------------------------------------------------------------- down
def down():
    s = sym("vline")
    lines = lst_lines("vline")
    jr = next(a for src, a, c in lines if a > s["vl"] and src.lower().replace(" ", "") == "jrnz,vl")
    after = next(a for src, a, c in lines if a > jr)
    x = gen22.VLINE_X
    tcl = (f'debug set_bp {s["d0"]} {{}} {{ L "d0 [machine_info time]" }}\n'
           f'debug set_bp {s["d1"]} {{}} {{ L "d1 [machine_info time]" }}\n' +
           once(s["vl"], 'L "vl [machine_info time]"', "a") +
           once(s["done"], 'L "done [machine_info time]"', "b"))
    out = {}
    for machine in (EU, JP):
        regs, vram, photo = page("vline", machine)
        ink = {(px, y) for y in range(192) for px in range(256) if paper_px(photo, px, y) != WHITE}
        assert ink == {(x, y) for y in range(192)}, (machine, len(ink))
        w = run("vline", SHOT, tcl, machine)
        t0 = [float(v[1]) for v in w if v[0] == "d0"]
        t1 = [float(v[1]) for v in w if v[0] == "d1"]
        ts = [round((b - a) * CLOCK) for a, b in zip(t0, t1)]
        vl = float(next(v for v in w if v[0] == "vl")[1])
        done = float(next(v for v in w if v[0] == "done")[1])
        out[TAG[machine]] = {"ink": len(ink), "calls": len(ts),
                             "down_t": {str(t): ts.count(t) for t in sorted(set(ts))},
                             "whole_t": round((done - vl) * CLOCK)}
    call = span("vline", s["d0"], s["d1"])
    inside, below = routine("vline", "down"), routine("vline", "down", taken=False)
    body = span("vline", s["vl"], after) - call                # the loop, but down
    whole = 192 * (body + call) - 5 + 168 * inside + 24 * below + span("vline", after, s["done"])
    out["priced"] = {"inside": inside, "below": below, "call": call, "loop": body,
                     "whole": whole, "with_vaddr": 192 * routine("vline", "vaddr")}
    for t in ("eu", "jp"):
        assert out[t]["down_t"] == {str(call + inside): 168, str(call + below): 24}, out[t]
        assert out[t]["whole_t"] == whole, (out[t]["whole_t"], whole)
    return out


# ---------------------------------------------------------------- tiles
def tiles():
    out = {}
    for machine in (EU, JP):
        res, photos = {}, {}
        for name in ("tiles3", "tiles1"):
            regs, vram, photos[name] = page(name, machine)
            s = sym(name)
            tcl = ("set ::n 0\ndebug set_watchpoint write_io 0x98 {} { incr ::n }\n" +
                   once(s["set0"], 'set ::n 0; L "s0 [machine_info time]"', "a") +
                   once(s["set1"], 'L "s1 [machine_info time] $::n"', "b"))
            w = run(name, SHOT, tcl, machine)
            s0 = float(next(x for x in w if x[0] == "s0")[1])
            s1 = next(x for x in w if x[0] == "s1")
            res[name] = {"regs": [regs[3], regs[4]], "bytes": int(s1[2]),
                         "t": round((float(s1[1]) - s0) * CLOCK), "reads": vdpscreen.reads(regs),
                         "colours_used": sorted({c for r in photos[name] for c in r[32:288]})}
        res["same_photo"] = photos["tiles3"] == photos["tiles1"]
        assert res["same_photo"]
        out[TAG[machine]] = res
    out["priced"] = {n: run_price(n, "set0", "set1", 1, 64) for n in ("tiles3", "tiles1")}
    for t in ("eu", "jp"):
        for n in ("tiles3", "tiles1"):
            assert out[t][n]["t"] == out["priced"][n], (t, n, out[t][n]["t"], out["priced"][n])
    pats, cols = gen22.tile_set()
    out["tile_bytes"] = {"patterns": len(pats), "colours": len(cols), "tiles": len(gen22.TILES)}
    return out


# ---------------------------------------------------------------- masks
def third_cell(photo, t, row=3, col=5):
    """the 8 x 8 cell at ROW and COL of third T: its shape as 8 bytes (1:
    not white) and the colours of its ink"""
    y0, x0 = 64 * t + 8 * row, 8 * col
    shape = tuple(sum(0x80 >> i for i in range(8) if paper_px(photo, x0 + i, y0 + j) != WHITE)
                  for j in range(8))
    inks = {paper_px(photo, x0 + i, y0 + j) for i in range(8) for j in range(8)} - {WHITE}
    return shape, inks


def masks():
    import screentext
    s = sym("masks")
    n = len(gen22.MASK_STATES)
    tcl = "".join(once(s[f"t{k}"], f'L "state {k} {POS} {REGS}"', f"t{k}") for k in range(n))
    tcl += once(s["t0"], VRAM, "v") + F0
    out = {}
    for machine in (EU, JP):
        glyphs = screentext.font(machine)[0]
        digit_of = {glyphs[ord("0") + d]: d for d in range(10)}
        w = run("masks", 140, tcl, machine)
        f0 = int(next(x for x in w if x[0] == "f0")[1])
        vram = bytes.fromhex(next(x for x in w if x[0] == "vram")[1])
        res = []
        for k in range(n):
            x = next(x for x in w if x[0] == "state" and x[1] == str(k))
            frame, regs = int(x[2]) - f0, [int(v) for v in x[3:]]
            r0, r1, r3, r4, what = gen22.MASK_STATES[k]
            assert [regs[0], regs[1], regs[3], regs[4]] == [r0, r1, r3, r4], (k, regs)
            film = frame + 3
            photo = codes(shot("masks", film, machine, prefix=f"masks{k}_{TAG[machine]}_f"))
            bad, x0 = check(vram, regs, photo)
            assert bad == 0, (k, machine, bad, x0)
            r = {"frame": frame, "film": film, "regs": regs, "mode": vdpscreen.mode(regs),
                 "wrong": bad, "text_x0": x0}
            if r["mode"] == "graphic2":
                r["reads"] = vdpscreen.reads(regs)
                got = []
                for t in range(3):
                    shape, inks = third_cell(photo, t)
                    got.append({"digit": digit_of.get(shape), "ink": sorted(inks)})
                r["thirds"] = got
                r["rule"] = [{"digit": t & r4 & 3, "ink": [gen22.MASK_INKS[t & (r3 >> 5 & 3)]]}
                             for t in range(3)]
                assert got == r["rule"], (k, machine, got, r["rule"])
            res.append(r)
        out[TAG[machine]] = res
    return out


# ---------------------------------------------------------------- leak
def drawn_with(vram, regs, photo, leak):
    old = vdpscreen.LEAK
    try:
        vdpscreen.LEAK = leak
        return check(vram, regs, photo)[0], vdpscreen.reads(regs)
    finally:
        vdpscreen.LEAK = old


def leak():
    s = sym("leak")
    tcl = (once(s["m3"], f'L "gi {POS} {REGS}"; {VRAM}', "a") +
           once(s["fix"], f'L "m3 {POS} {REGS}"', "b") +
           once(s["done"], f'L "fix {POS} {REGS}"; {VRAM}', "c") + F0)
    out = {}
    for machine in (EU, JP):
        w = run("leak", 80, tcl, machine)
        f0 = int(next(x for x in w if x[0] == "f0")[1])
        vrams = [bytes.fromhex(x[1]) for x in w if x[0] == "vram"]
        assert len(vrams) == 2
        res = {}
        photos = {}
        for tag, vram, back in (("gi", vrams[0], -2), ("m3", vrams[0], -2), ("fix", vrams[1], 3)):
            x = next(x for x in w if x[0] == tag)
            frame, regs = int(x[1]) - f0, [int(v) for v in x[2:]]
            film = frame + back
            photos[tag] = photo = codes(shot("leak", film, machine, prefix=f"leak_{tag}_{TAG[machine]}_f"))
            r = {"frame": frame, "film": film, "regs": regs, "mode": vdpscreen.mode(regs)}
            r["wrong"], r["reads"] = drawn_with(vram, regs, photo, True)
            r["wrong_no_rule6"], r["reads_no_rule6"] = drawn_with(vram, regs, photo, False)
            r["ink"] = sum(c != WHITE for row in photo[24:216] for c in row[32:288])
            r["colours"] = sorted({c for row in photo[24:216] for c in row[32:288]})
            assert r["wrong"] == 0, (tag, machine, r["wrong"])
            res[tag] = r
        # the M3 page's state: rule 6 or not, the regs are those of the M3 frames
        assert res["m3"]["mode"] == "graphic2" and res["gi"]["mode"] == "graphic1"
        shape = lambda p, q: sum((a != WHITE) != (b != WHITE)
                                 for ra, rb in zip(p[24:216], q[24:216])
                                 for a, b in zip(ra[32:288], rb[32:288]))
        # the 32 bytes after the Graphic I colours, which M3 with R#3 = $80 reads
        res["after_table"] = sorted(set(vrams[0][0x2020:0x2040]))
        res["shape_differs"] = {"m3": shape(photos["gi"], photos["m3"]),
                                "fix": shape(photos["gi"], photos["fix"])}
        assert res["shape_differs"]["fix"] == 0 and res["m3"]["wrong_no_rule6"] > 0
        out[TAG[machine]] = res
    return out


# ---------------------------------------------------------------- answers
def answers():
    m = json.loads((HERE / "meas22.json").read_text())
    out = {}
    # 1: pixel (100, 150): its byte in the patterns and the colours, and its bit
    a = vdpscreen.address(100, 150)
    out["q1"] = {"patterns": a, "colours": 0x2000 + a, "mask": 0x80 >> 100 % 8}
    # 2: vaddr, a call included, for each of the 49,152 pixels: the frames
    t = m["diag"]["priced"]["vaddr_call"]
    out["q2"] = {"t": t, "eu": round(49152 * t / meas.T_PER_FRAME[EU], 1),
                 "jp": round(49152 * t / meas.T_PER_FRAME[JP], 1)}
    # 3 and 4: masks.rom's states 3 (R#4 = $02) and 5 (R#3 = $BF), as measured
    out["q3"] = [d["digit"] for d in m["masks"]["eu"][3]["thirds"]]
    out["q4"] = [d["ink"][0] for d in m["masks"]["eu"][5]["thirds"]]
    # 5: tiles1.rom: the bytes of the two tables the VDP never reads
    r = m["tiles"]["eu"]["tiles1"]["reads"]
    out["q5"] = {"free": 2 * 6144 - r["patterns"] - r["colours"]}
    # 6: leak.rom's M3 state: the bytes of the patterns the VDP can draw from,
    #    and so the characters whose shapes it draws
    regs = m["leak"]["eu"]["m3"]["regs"]
    p_mask = ((regs[4] & 3) << 11 | 0x7FF) & (~0x7C0 | (regs[3] & 0x1F) << 6)
    read = sorted({vdpscreen.bases(regs)["patterns"] | i & p_mask for i in range(6144)})
    out["q6"] = {"bytes": len(read), "first": read[0], "last": read[-1],
                 "characters": sorted({a // 8 for a in read})}
    return out


# ---------------------------------------------------------------- openmsx
OPENMSX_SECTIONS = ["bytes", "colours", "diag", "down", "tiles", "masks", "leak"]


def openmsx():
    if not versions.builds():
        return {"skipped": "OPENMSX_BUILDS not set"}
    return versions.every_build(["ch22"], OPENMSX_SECTIONS)


SECTIONS = {"bytes": bytes_, "colours": colours, "diag": diag, "down": down, "tiles": tiles, "masks": masks,
            "leak": leak, "answers": answers, "openmsx": openmsx}


def main(names=()):
    CAPS.mkdir(exist_ok=True)
    path = HERE / "meas22.json"
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
