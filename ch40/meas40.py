#!/usr/bin/env python3
"""meas40.py -- score, text, and a status line that never flickers, measured.

    python3 gen40.py && ./build.sh && python3 meas40.py
                                  python3 meas40.py films prices   only these

  films     status.rom, after.rom and blink.rom on both machines, every frame:
            the debugger's marks (woke, news, told) and every byte sent to
            the VDP, against gen40.py's model of the game and walk.py's
            T-states; each byte's moment, from vdpslots.py (chapter 20); a
            photograph of every frame against the picture the VRAM gives
            line by line, the status line's names as the bytes had reached
            them; the twelve digits read back from each photograph
  prices    what each routine costs with its CALL, by walk.py on the same
            bytes, and the cases the films timed
  order     BCD bytes are ordered like their numbers: best on walk.py for
            every pair of BCD bytes, in each of the three places
  answers   the workshop, tried (for Appendix I)
  openmsx   all of it again with every other build (tools/versions.py)
"""
import json
import shutil
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
import vdpslots    # noqa: E402  (chapter 20: when the VDP takes a byte)
import versions    # noqa: E402
sys.path.insert(0, str(HERE))
import gen40       # noqa: E402
sys.path.remove(str(HERE))
sys.path.insert(0, str(HERE))      # gen40 put chapters 26 and 30 first: this folder's files win
for mod in ("vdpscreen", "walk"):
    sys.modules.pop(mod, None)
import vdpscreen   # noqa: E402
import walk        # noqa: E402

assert Path(vdpscreen.__file__).parent == HERE and Path(walk.__file__).parent == HERE

CAPS = HERE / "captures"
SHOTS = HERE / "shots"              # every frame of the films: not in the delivery
EU, JP = gen40.EU, gen40.JP
MACHINES = gen40.MACHINES
TAG = {EU: "eu", JP: "jp"}
CLOCK = dbg.CLOCK
LINE = vdpslots.LINE
PALETTE = [tuple(c) for c in json.loads((REPO / "ch01" / "meas01.json").read_text())["palette"]["rgb"]]
CODE = {rgb: n for n, rgb in enumerate(PALETTE) if n}
REGS = gen40.REGS
KINDS = list(gen40.KINDS)
RUN_FRAMES = 150
POS = "[machine_info VDP_frame_count] [machine_info VDP_cycle_in_frame] [machine_info time]"
FIG_STRIP = range(17, 29)                      # figure 40.2: twelve pictures of each program, 50 Hz
STATUS_LINE0 = 8 * gen40.STATUS_ROW            # the paper's first line of the status line
CELLS = [gen40.SCORE_AT - gen40.NAMES - 32 * gen40.STATUS_ROW + i for i in range(6)] + \
        [gen40.HI_AT - gen40.NAMES - 32 * gen40.STATUS_ROW + i for i in range(6)]

STATE = r"""
proc V {tag} {
    binary scan [debug read_block VRAM 0 16384] H* h
    L "$tag vram $h"
    set v {}
    for {set i 0} {$i < 8} {incr i} { lappend v [debug read {VDP regs} $i] }
    L "$tag regs $v"
}
proc M {tag addr n} {
    binary scan [debug read_block memory $addr $n] H* h
    L "$tag mem $h"
}
"""


def rom(name):
    return HERE / f"{name}.rom"


def sym(name):
    return dbg.sym(HERE / f"{name}.sym")


def t_state(seconds):
    t = float(seconds) * CLOCK
    assert abs(t - round(t)) < 1e-3, seconds
    return round(t)


def run(name, machine, frames, at_init=""):
    lines = msxcap.run_tcl(rom(name), frames, at_init, machine=machine, tcl_setup=STATE, timeout=900)
    return [l.split() for l in lines]


def codes(png):
    im = Image.open(png).convert("RGB")
    px = im.load()
    return [[CODE.get(px[x, y]) for x in range(im.width)] for y in range(im.height)]


def once(addr, body, tag):
    return f'set ::{tag} [debug set_bp {addr} {{}} {{ {body}; debug remove_bp $::{tag} }}]\n'


# ---------------------------------------------------------------- the walk
def walker(kind, rate):
    """walk.py on KIND, from INIT to the first HALT; RATE: the byte at $002B,
    as the debugger read it"""
    wk = walk.Walk(HERE / kind)
    wk.mem[0x2B] = rate
    wk.run("init", "frame")
    return wk


def walk_frames(kind, rate):
    """the program's frames on walk.py: for each loop, the T-states from woke
    to news and from news to told, and the bytes sent between news and told
    with their T-states from news"""
    wk = walker(kind, rate)
    out = []
    for k in range(gen40.FRAMES):
        a = wk.run("woke", "news") if "woke" in wk.sym else 0
        n0 = len(wk.ports)
        b = wk.run("news", "told")
        sent = [(t, p, v) for t, p, v in wk.ports[n0:]]
        t0 = wk.t - b
        if k < gen40.FRAMES - 1:
            wk.run("told", "frame")
        out.append({"woke_news": a, "news_told": b, "sent": [(t - t0, p, v) for t, p, v in sent]})
    return out


# ---------------------------------------------------------------- the films
def log_film(kind, machine):
    """the debugger: the marks and every byte to the VDP from the first frame"""
    s = sym(kind)
    tcl = ('set ::on 0\nproc ::toofast_cb {args} { L "fast [machine_info time]" }\n'
           'set VDP.too_fast_vram_access_callback ::toofast_cb\n'
           f'debug set_bp {s["frame"]} {{}} {{ set ::on 1; L "halt {POS}" }}\n'
           'debug set_watchpoint write_io {0x98 0x99} {} { if {$::on} { L "w '
           '[machine_info VDP_frame_count] [machine_info VDP_cycle_in_frame] '
           '$::wp_last_address $::wp_last_value" } }\n'
           f'debug set_bp {s["isr"]} {{}} {{ L "irq {POS}" }}\n'
           'L "rate [debug read memory 0x2B]"\n')
    marks = ["news", "told"] + (["woke"] if "woke" in s else [])
    for mk in marks:
        tcl += f'debug set_bp {s[mk]} {{}} {{ L "{mk} {POS}" }}\n'
    tcl += once(s["done"], f'V end; M nums {gen40.NUMS} 6; M shown {gen40.SHOWN} 6; '
                           f'M ticks {s["ticks"]} 2; L "end {POS}"', "e")
    return run(kind, machine, RUN_FRAMES, tcl)


def addresses(writes):
    """[(cycle, port, value)] -> [(cycle, VRAM address, value)] of the bytes
    to $98, the address set by the pairs to $99 (chapter 19)"""
    out, held, addr = [], None, None
    for c, port, v in writes:
        if port == 0x99:
            if held is None:
                held = v
            else:
                assert v & 0xC0 == 0x40, "only addresses for writing"
                addr, held = (v & 0x3F) << 8 | held, None
        else:
            out.append((c, addr, v))
            addr += 1
    return out


def film(kind, machine):
    w = log_film(kind, machine)
    s = sym(kind)
    s_woke_is_news = "woke" not in s
    fast = [x for x in w if x[0] == "fast"]
    f0 = int(next(x for x in w if x[0] == "f0")[1])
    frame_len = vdpslots.LINES[machine] * LINE
    base = f0                       # cycles counted from the start of film frame 0

    def cyc(fc, c):
        return (int(fc) - base) * frame_len + int(c)

    marks = [(x[0], cyc(x[1], x[2]), t_state(x[3])) for x in w if x[0] in ("woke", "news", "told", "irq", "end", "halt") and x[1].isdigit()]
    writes = [(cyc(x[1], x[2]), int(x[3]) & 0xFF, int(x[4])) for x in w if x[0] == "w"]  # the port: the low byte
    # the segments: the bytes between each news and its told, and those after
    # the last told (the last status line, GAME OVER)
    # a breakpoint just after HALT is met while the CPU halts too (chapter
    # 31): the wake is the mark that follows the interrupt routine's
    kept, after_irq = [], False
    for m in marks:
        if m[0] == "irq":
            after_irq = True
        elif m[0] in ("woke", "news") and m[1] is not None:
            first = s_woke_is_news or m[0] == "woke"
            if first and not after_irq:
                continue                    # met while halting
            if first:
                after_irq = False
        kept.append(m)
    marks = kept
    news = [m for m in marks if m[0] == "news"]
    told = [m for m in marks if m[0] == "told"]
    assert len(news) == len(told) == gen40.FRAMES, (kind, machine, len(news), len(told))
    segs = []
    for (_, a, _), (_, b, _) in zip(news, told):
        segs.append([x for x in writes if a <= x[0] <= b])
    tail = [x for x in writes if x[0] > told[-1][1]]
    # every byte against vdpslots: the cycle it reached the VRAM, none lost
    taken = {}
    events = [(c, p, v) for c, p, v in writes]
    vram, _, lost = vdpslots.play(events, machine, vram=gen40.vram_start(), regs=REGS, taken=taken)
    end_vram = bytes.fromhex(next(x for x in w if x[0] == "end" and x[1] == "vram")[2])
    rate = int(next(x for x in w if x[0] == "rate")[1])
    return {"w": w, "f0": f0, "rate": rate, "marks": marks, "segs": segs, "tail": tail, "writes": writes,
            "taken": taken, "lost": lost, "fast": len(fast), "vram_model": vram, "end_vram": end_vram,
            "frame_len": frame_len}


def shots(kind, machine, frames):
    """the film's frames, photographed; kept in shots/"""
    SHOTS.mkdir(exist_ok=True)
    return msxcap.capture(rom(kind), frames, SHOTS, f"{kind}_{TAG[machine]}_f", machine=machine,
                          timeout=900)


def paper_of(photo):
    return [row[meas.PAPER_X0:meas.PAPER_X0 + 256] for row in photo[meas.PAPER_Y0:meas.PAPER_Y0 + 192]]


def border_ok(photo, colour):
    """every pixel of the drawn columns outside the paper is the border's"""
    for y in range(meas.CAPTURE_H):
        for x in range(meas.DRAWN[0], meas.DRAWN[1] + 1):
            inside = 0 <= x - meas.PAPER_X0 < 256 and 0 <= y - meas.PAPER_Y0 < 192
            if not inside and photo[y][x] != colour:
                return False
    return True


SHAPE_ROWS = {c: list(gen40.FONT[(c - 32) * 8:(c - 31) * 8]) for c in range(32, 128)}
for d in range(10):
    SHAPE_ROWS[d] = list(gen40.DIGIT_SHAPES[8 * d:8 * d + 8])


def cell_row(photo_paper, cell, line):
    """the eight pixels of a status cell's line, as a byte: ink 1"""
    y = STATUS_LINE0 + line
    row = photo_paper[y][8 * cell:8 * cell + 8]
    assert set(row) <= {gen40.WHITE, gen40.DARK_BLUE}, (cell, line, row)
    return sum(0x80 >> i for i, c in enumerate(row) if c == gen40.WHITE)


def read_cell(photo_paper, cell):
    """what a cell shows: ("digit", d), ("blank",), or ("torn", [the
    characters each line agrees with])"""
    rows = [cell_row(photo_paper, cell, l) for l in range(8)]
    fits = [{c for c in list(range(10)) + [gen40.SPACE] if SHAPE_ROWS[c][l] == r} for l, r in enumerate(rows)]
    whole = set.intersection(*fits)
    if gen40.SPACE in whole and all(r == 0 for r in rows):
        return ("blank",)
    digits = sorted(c for c in whole if c < 10)
    if digits:
        assert len(digits) == 1, digits
        return ("digit", digits[0])
    return ("torn", [sorted(f) for f in fits])


def film_frames(fl):
    """the film frames from the first status line's to two after the last"""
    first = min(c for c, _, _ in fl["writes"]) // fl["frame_len"]
    last = max(c for c, _, _ in fl["writes"]) // fl["frame_len"]
    return list(range(first + 1, last + 3))       # from the first whole picture


def model_pictures(fl, machine, frames):
    """for each film frame: the paper as the VRAM gives it line by line, and
    for each line of the status line the names that reach the VRAM in it"""
    data = []                       # (taken cycle, address, value)
    held, addr = None, None
    for i, (c, port, v) in enumerate(fl["writes"]):
        if port == 0x99:
            if held is None:
                held = v
            else:
                addr, held = (v & 0x3F) << 8 | held, None
        else:
            if i not in fl["lost"]:
                data.append((fl["taken"][i], addr, v))
            addr += 1
    data.sort()
    p0 = vdpslots.PAPER0[machine]
    vram = bytearray(gen40.vram_start())
    j = 0
    out = {}
    b = vdpscreen.bases(REGS)
    for n in frames:
        start = n * fl["frame_len"] + p0 * LINE + vdpslots.BORDER_IN
        while j < len(data) and data[j][0] < start:
            vram[data[j][1]] = data[j][2]
            j += 1
        pic = vdpscreen.draw(vram, REGS)
        mixed = {}
        state = bytearray(vram)
        k = j
        for y in range(192):
            ls = start + y * LINE
            le = ls + LINE
            while k < len(data) and data[k][0] < ls:
                state[data[k][1]] = data[k][2]
                k += 1
            if y // 8 == gen40.STATUS_ROW:
                pic[y] = vdpscreen.graphic2_line(state, REGS, b, y)
                inside = [d for d in data[k:] if d[0] < le]
                if inside:
                    after = bytearray(state)
                    for d in inside:
                        after[d[1]] = d[2]
                    mixed[y] = vdpscreen.graphic2_line(after, REGS, b, y)
        out[n] = (pic, mixed)
    return out


def against(photo, pic, mixed):
    """pixels of the paper that are neither the line's model nor, in a line
    where a byte reached the VRAM, the line after it"""
    pp = paper_of(photo)
    bad = 0
    for y in range(192):
        for x in range(256):
            if pp[y][x] != pic[y][x] and not (y in mixed and pp[y][x] == mixed[y][x]):
                bad += 1
    return bad


def data_writes(fl, seg):
    """[(address, value)] of the bytes to $98 in SEG, the address set by $99"""
    return [(a, v) for _, a, v in addresses(seg)]


def check_film(kind, machine, fl):
    """the debugger's film against the model of the game and walk.py"""
    # one interrupt between two wakes: no frame lost
    kinds = [m[0] for m in fl["marks"] if m[0] in ("irq", "news")]
    loop = [m for m in fl["marks"] if m[0] == "news"]
    first = kinds.index("news")
    pairs = "".join("i" if k == "irq" else "n" for k in kinds[first:])
    assert pairs.count("n") == gen40.FRAMES and "nn" not in pairs and "ii" not in pairs, (kind, machine)
    # the bytes of each status line, and the end
    want = gen40.sends(kind)
    for k, seg in enumerate(fl["segs"]):
        assert data_writes(fl, seg) == want[k], (kind, machine, k)
    over = [(gen40.OVER_AT + i, ord(c)) for i, c in enumerate(gen40.OVER)]
    tail = want[gen40.FRAMES] + over if kind == "status" else over
    assert data_writes(fl, fl["tail"]) == tail, (kind, machine)
    assert not fl["lost"] and not fl["fast"], (kind, machine)
    end = gen40.vram_end(kind)
    spans = [(0, 0x1B01), (0x2000, 0x3800)]
    assert all(fl["end_vram"][a:b] == end[a:b] for a, b in spans), (kind, machine)
    assert all(fl["vram_model"][a:b] == end[a:b] for a, b in spans), (kind, machine)
    # walk.py: the T-states between the marks, and of every byte from news
    wf = walk_frames(kind, fl["rate"])
    t = {m[0]: [] for m in fl["marks"]}
    for m in fl["marks"]:
        t[m[0]].append(m)
    offsets = set()
    for k in range(gen40.FRAMES):
        nw, td = t["news"][k], t["told"][k]
        assert td[2] - nw[2] == wf[k]["news_told"], (kind, machine, k, td[2] - nw[2], wf[k]["news_told"])
        if "woke" in t:
            wk_ = t["woke"][k]
            assert nw[2] - wk_[2] == wf[k]["woke_news"], (kind, machine, k)
        for (c, port, v), (tw, pw, vw) in zip(fl["segs"][k], wf[k]["sent"]):
            assert (port, v) == (pw, vw), (kind, machine, k)
            d = c - nw[1] - vdpslots.PER_T * tw
            offsets.add(d)
        assert len(fl["segs"][k]) == len(wf[k]["sent"])
    return {"walk_frames": wf, "offsets": sorted(offsets)}


def read_film(kind, machine, fl, frames):
    """the photographs: each against the model, and the twelve digits read"""
    pics = model_pictures(fl, machine, frames)
    pngs = shots(kind, machine, frames)
    reads = {}
    for n in frames:
        ph = codes(pngs[n])
        pic, mixed = pics[n]
        assert border_ok(ph, gen40.WHITE), (kind, machine, n)
        bad = against(ph, pic, mixed)
        assert bad == 0, (kind, machine, n, bad)
        pp = paper_of(ph)
        reads[n] = {"cells": [read_cell(pp, c) for c in CELLS], "mixed": sorted(mixed)}
    return reads, pngs


def score_of(cells):
    """the six digits of the score's cells, or None if one is not whole"""
    if all(c[0] == "digit" for c in cells):
        return int("".join(str(c[1]) for c in cells))
    return None


def films():
    out = {}
    game = gen40.game()
    reached = [gen40.value(g["score"]) for g in game]
    for kind in KINDS:
        res = {}
        for m in MACHINES:
            fl = film(kind, m)
            chk = check_film(kind, m, fl)
            frames = film_frames(fl)
            reads, pngs = read_film(kind, m, fl, frames)
            p0 = vdpslots.PAPER0[m]
            fr = fl["frame_len"]
            news = [x for x in fl["marks"] if x[0] == "news"]
            told = [x for x in fl["marks"] if x[0] == "told"]
            # where each status line was sent: the frame line of news, the
            # line at which its last byte reached the VRAM, from the paper's first
            sent_lines = []
            for k, seg in enumerate(fl["segs"]):
                idx = [i for i, x in enumerate(fl["writes"]) if x in seg and x[1] == 0x98]
                land = [fl["taken"][i] for i in idx]
                start = news[k][1]
                sent_lines.append({"news_line": (start % fr) // LINE,
                                   "lines": [(c % fr) // LINE - p0 for c in land],
                                   "first": ((min(land) % fr) // LINE - p0) if land else None,
                                   "last": ((max(land) % fr) // LINE - p0) if land else None,
                                   "pairs": sum(1 for x in seg if x[1] == 0x98) // 2})
            torn, blank_cells, torn_cells, spaced = [], 0, 0, 0
            seen = {}
            whole = 0
            for n in frames:
                cells = reads[n]["cells"]
                t = [c for c in cells if c[0] == "torn"]
                if t:
                    torn.append(n)
                torn_cells += len(t)
                spaced += sum(1 for c in t if any(f == [gen40.SPACE] for f in c[1]))
                blank_cells += sum(1 for c in cells if c[0] == "blank")
                if all(c[0] == "digit" for c in cells):
                    whole += 1
                sc = score_of(cells[:6])
                if sc is not None:
                    seen[sc] = seen.get(sc, 0) + 1
            never = sorted(set(reached) - set(seen))
            assert set(seen) <= set(reached) | {0}, (kind, m)
            # the loop frame whose bytes a torn picture shows, by its place in the tables
            loop_of = {}
            for k, seg in enumerate(fl["segs"]):
                for x in seg:
                    i = fl["writes"].index(x)
                    if x[1] == 0x98:
                        loop_of.setdefault(fl["taken"][i] // fr, set()).add(k)
            torn_places = sorted({k & 15 for n in torn for k in loop_of.get(n, ())})
            t_told = [b[2] - a[2] for a, b in zip(news, told)]
            # the T-states each frame had left: from its HALT to the interrupt
            left, last_halt = [], None
            for mk in fl["marks"]:
                if mk[0] == "halt" and last_halt is None:
                    last_halt = mk
                elif mk[0] == "irq" and last_halt is not None:
                    left.append(mk[2] - last_halt[2])
                    last_halt = None
                elif mk[0] == "irq":
                    pass
            # the pictures of the figures, kept with the chapter
            keep = []
            if m == EU:
                keep = list(FIG_STRIP) + ([frames[-1]] if kind == "status" else [])
                for n in keep:
                    shutil.copyfile(pngs[n], CAPS / pngs[n].name)
            res[TAG[m]] = {
                "rate": fl["rate"], "pictures": len(frames), "first_picture": frames[0],
                "whole": whole, "torn": len(torn), "torn_frames": torn, "torn_cells": torn_cells,
                "cells_with_space_lines": spaced, "blank_cells": blank_cells,
                "torn_places": torn_places, "scores_reached": len(set(reached)),
                "scores_never_whole": len(never), "never": never,
                "seen_once": sum(1 for v in seen.values() if v == 1),
                "seen_twice": sum(1 for v in seen.values() if v == 2),
                "seen_more": sum(1 for v in seen.values() if v > 2),
                "news_told": t_told, "sent": sent_lines, "offsets": chk["offsets"],
                "woke_news": [w["woke_news"] for w in chk["walk_frames"]],
                "walk_checked": len(chk["walk_frames"]), "lost": len(fl["lost"]), "fast": fl["fast"],
                "frame_of_news": [x[1] // fr for x in news],
                "captures": [pngs[n].name for n in keep], "last_picture": frames[-1],
                "least_left": min(left[1:])}
        out[kind] = res
    return out


# ---------------------------------------------------------------- prices
def put(wk, addr, data):
    wk.mem[addr:addr + len(data)] = bytes(data)


def prices():
    s = sym("status")
    score, hi, shown = s["score"], s["hi"], s["shown"]
    out = {}
    wk = walker("status", 0x80)
    out["putbcd"] = wk.call("putbcd", a=0x37)
    upd = {}
    for n in range(4):                      # the last n bytes differ from the copy
        put(wk, score, [0x00, 0x12, 0x34])
        put(wk, shown, [0x00, 0x12, 0x34])
        for i in range(n):
            wk.mem[shown + 2 - i] ^= 0x01
        upd[n] = wk.call("update", h=score >> 8, l=score & 0xFF,
                         d=(gen40.SCORE_AT | 0x4000) >> 8, e=gen40.SCORE_AT & 0xFF)
        assert bytes(wk.mem[shown:shown + 3]) == bytes([0x00, 0x12, 0x34])
    out["update"] = upd
    out["update_pair"] = upd[1] - upd[0]
    assert all(upd[n] == upd[0] + n * out["update_pair"] for n in range(4))
    # status: both numbers, nothing changed and everything changed
    put(wk, score, [0, 0x12, 0x34]); put(wk, hi, [0, 0x15, 0])
    put(wk, shown, [0, 0x12, 0x34, 0, 0x15, 0])
    out["status_none"] = wk.call("status")
    put(wk, shown, [0xFF] * 6)
    out["status_all"] = wk.call("status")
    # best: four cases (score, hi -> hi after)
    cases = {"hi higher, first byte": ([0x00, 0x99, 0x99], [0x01, 0x00, 0x00]),
             "the same": ([0x00, 0x15, 0x00], [0x00, 0x15, 0x00]),
             "score higher, first byte": ([0x01, 0x00, 0x00], [0x00, 0x99, 0x99]),
             "score higher, last byte": ([0x00, 0x15, 0x05], [0x00, 0x15, 0x00])}
    out["best"] = {}
    for label, (sc, h) in cases.items():
        put(wk, score, sc); put(wk, hi, h)
        t = wk.call("best")
        want = sc if gen40.value(sc) > gen40.value(h) else h
        assert list(wk.mem[hi:hi + 3]) == want, label
        out["best"][label] = t
    # addsc: no branch, one price
    ts = set()
    for start, pts in (([0, 0, 0], 0x75), ([0, 0x99, 0x99], 0x01), ([0x99, 0x99, 0x99], 0x75)):
        put(wk, score, start)
        ts.add(wk.call("addsc", a=pts))
        assert list(wk.mem[score:score + 3]) == gen40.bcd_add(start, pts)
    assert len(ts) == 1
    out["addsc"] = ts.pop()
    # say: a character, and a text
    t5 = wk.call("say", h=s["label0"] >> 8, l=s["label0"] & 0xFF, d=0x5A, e=0x01)
    t9 = wk.call("say", h=s["over"] >> 8, l=s["over"] & 0xFF, d=0x5A, e=0x8B)
    per = (t9 - t5) // 4
    assert t5 == t5 - 5 * per + 5 * per and t9 - t5 == 4 * per
    out["say"] = {"char": per, "text": t5 - 5 * per}
    # turn: the frame's work, passes of 30 T-states
    put(wk, score, [0, 0, 0]); put(wk, hi, gen40.HI0)
    s_count = s["count"]
    base = {}
    for place in (1, 3):                    # no points: the price of turn less its work
        wk.mem[s_count] = place
        put(wk, score, [0, 0, 0]); put(wk, hi, gen40.HI0)
        t = wk.call("turn")
        base[place] = t - gen40.PASS_T * gen40.WORK50[place]
    assert base[1] == base[3]
    out["turn_without_work"] = base[1]
    # show and redraw, in blink.asm
    wb = walker("blink", 0x80)
    sb = sym("blink")
    put(wb, sb["score"], [0, 0x12, 0x34])
    out["show"] = wb.call("show", h=sb["score"] >> 8, l=sb["score"] & 0xFF,
                          d=(gen40.SCORE_AT | 0x4000) >> 8, e=gen40.SCORE_AT & 0xFF)
    out["redraw"] = wb.call("redraw")
    # the bytes of putbcd and say: T-states between two OUTs to $98
    wk.ports.clear()
    wk.call("putbcd", a=0x37)
    outs = [t for t, p, v in wk.ports if p == 0x98]
    out["putbcd_gap"] = outs[1] - outs[0]
    wk.ports.clear()
    wk.call("say", h=s["over"] >> 8, l=s["over"] & 0xFF, d=0x5A, e=0x8B)
    outs = [t for t, p, v in wk.ports if p == 0x98]
    out["say_gap"] = min(b - a for a, b in zip(outs, outs[1:]))
    return out


# ---------------------------------------------------------------- order
def order():
    """best on walk.py for every pair of BCD bytes, in each of the three
    places: hi becomes score exactly when score's number is higher"""
    s = sym("status")
    wk = walker("status", 0x80)
    bcd = [int(f"{n:02d}", 16) for n in range(100)]
    pairs = 0
    for place in range(3):
        for a in bcd:
            for b in bcd:
                sc, h = [0, 0, 0], [0, 0, 0]
                sc[place], h[place] = a, b
                put(wk, s["score"], sc); put(wk, s["hi"], h)
                wk.call("best")
                want = sc if gen40.value(sc) > gen40.value(h) else h
                assert list(wk.mem[s["hi"]:s["hi"] + 3]) == want, (place, a, b)
                pairs += 1
    return {"pairs": pairs, "wrong": 0}


# ---------------------------------------------------------------- answers
def variant_putbcd():
    """putbcd for a set whose digits are only at '0' to '9': OR '0' for each
    digit, and no NOP (the OR keeps the two OUTs 33 T-states apart)"""
    import subprocess
    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix="ch40q2_"))
    try:
        for f in ("msx.inc", "bios.inc"):
            shutil.copyfile(HERE / f, tmp / f)
        src = (HERE / "status.asm").read_text()
        old = ("        and $0F                 ;  8  and nothing else: its own name\n"
               "        out (VDP_DATA), a       ; 12\n"
               "        ld a, c                 ;  5\n"
               "        and $0F                 ;  8  the second digit\n"
               "        nop                     ;  5  30 T-states after the first OUT\n")
        new = ("        and $0F                 ;  8\n"
               "        or '0'                  ;  8  the name of its character\n"
               "        out (VDP_DATA), a       ; 12\n"
               "        ld a, c                 ;  5\n"
               "        and $0F                 ;  8  the second digit\n"
               "        or '0'                  ;  8\n")
        assert src.count(old) == 1
        (tmp / "q2.asm").write_text(src.replace(old, new).replace('OUTPUT "status.rom"', 'OUTPUT "q2.rom"'))
        subprocess.run(["sjasmplus", "--nologo", "--msg=err", "--syntax=bFw", "--sym=q2.sym", "--lst=q2.lst",
                        "q2.asm"], cwd=tmp, check=True)
        wk = walk.Walk(tmp / "q2")
        t = wk.call("putbcd", a=0x37)
        outs = [x for x in wk.ports if x[1] == 0x98]
        assert [v for _, _, v in outs] == [ord("3"), ord("7")]
        return {"putbcd": t, "gap": outs[1][0] - outs[0][0]}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def answers():
    m = json.loads((HERE / "meas40.json").read_text())
    fl, pr = m["films"], m["prices"]
    s = sym("status")
    out = {}
    # 1: 999,990 and 75 points
    wk = walker("status", 0x80)
    put(wk, s["score"], [0x99, 0x99, 0x90]); put(wk, s["hi"], [0x99, 0x99, 0x90])
    put(wk, s["shown"], [0x99, 0x99, 0x90, 0x99, 0x99, 0x90])
    wk.call("addsc", a=0x75)
    after = list(wk.mem[s["score"]:s["score"] + 3])
    wk.call("best")
    hi = list(wk.mem[s["hi"]:s["hi"] + 3])
    wk.ports.clear()
    t = wk.call("update", h=s["score"] >> 8, l=s["score"] & 0xFF,
                d=(gen40.SCORE_AT | 0x4000) >> 8, e=gen40.SCORE_AT & 0xFF)
    out["q1"] = {"score": "".join(f"{b:02X}" for b in after), "hi": "".join(f"{b:02X}" for b in hi),
                 "pairs": sum(1 for x in wk.ports if x[1] == 0x98) // 2, "update": t}
    # 2: the digits only at '0' to '9'
    out["q2"] = variant_putbcd()
    out["q2"]["more_a_pair"] = out["q2"]["putbcd"] - pr["putbcd"]
    # 3: after.asm's status line on row 23: the bytes that reached the VRAM in its lines
    q3 = {}
    for t_ in ("eu", "jp"):
        lines = sorted({l for x in fl["after"][t_]["sent"] for l in x["lines"]})
        q3[t_] = {"in_row_23": sum(1 for x in fl["after"][t_]["sent"]
                                   if any(184 <= l <= 191 for l in x["lines"])),
                  "nearest_above": max(l for l in lines if l < 184),
                  "nearest_below": min(l for l in lines if l > 191)}
    out["q3"] = q3
    # 4: the time left between told and the next interrupt, the least
    out["q4"] = {k: {t_: v[t_]["least_left"] for t_ in ("eu", "jp")} for k, v in fl.items()}
    # 5: a new game with the old copies: what update sends
    shown = {"score": [0x00, 0x30, 0x00], "hi": [0x00, 0x30, 0x00]}
    last = gen40.game()[-1]
    assert last["score"] == shown["score"] and last["hi"] == shown["hi"]
    new = {"score": [0, 0, 0], "hi": last["hi"]}
    line = {}
    for name in ("score", "hi"):
        cells = [" "] * 6
        for i in range(3):
            if new[name][i] != shown[name][i]:
                cells[2 * i:2 * i + 2] = f"{new[name][i]:02X}"
        line[name] = "".join(cells)
    out["q5"] = line
    # 6: after50.rom at 60 Hz: the table of 50 Hz
    f6 = film("after50", JP)
    check_film("after50", JP, f6)
    frames = film_frames(f6)
    reads, _ = read_film("after50", JP, f6, frames)
    torn = [n for n in frames if any(c[0] == "torn" for c in reads[n]["cells"])]
    fr = f6["frame_len"]
    loop_of = {}
    for k, seg in enumerate(f6["segs"]):
        for x in seg:
            if x[1] == 0x98:
                loop_of.setdefault(f6["taken"][f6["writes"].index(x)] // fr, set()).add(k)
    out["q6"] = {"torn": len(torn), "places": sorted({k & 15 for n in torn for k in loop_of.get(n, ())})}
    return out


OPENMSX_SECTIONS = ["films"]


def openmsx():
    if not versions.builds():
        return {"skipped": "OPENMSX_BUILDS not set"}
    return versions.every_build(["ch40"], OPENMSX_SECTIONS)


SECTIONS = {"films": films, "prices": prices, "order": order, "answers": answers, "openmsx": openmsx}


def main(names=()):
    CAPS.mkdir(exist_ok=True)
    path_ = HERE / "meas40.json"
    m = json.loads(path_.read_text()) if names and path_.exists() else {}
    for name in names or SECTIONS:
        print(name, flush=True)
        m[name] = SECTIONS[name]()
        m = {k: m[k] for k in SECTIONS if k in m}
        path_.write_text(json.dumps(m, indent=1) + "\n")
    return m


if __name__ == "__main__":
    main(sys.argv[1:])
