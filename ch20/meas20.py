#!/usr/bin/env python3
"""meas20.py -- how fast the VDP listens, measured.

    python3 gen20.py && ./build.sh && python3 meas20.py
                                  python3 meas20.py beat probe    only these
                                  python3 meas20.py --missing      those not measured yet

The debugger records every byte the program writes to the VDP, $98 and $99,
with the frame and the VDP cycle at which it was written, and reads the VRAM
before and after. vdpslots.py, played those writes, has to give the VRAM the
debugger reads, byte for byte, and the photograph has to show it.

  beat      beat.rom on both machines: 228 pairs of bytes 20 T-states apart,
            one at every T-state of a line; which lost their first byte
            (figure 20.1)
  beats     beat12.rom to beat26.rom on both machines: the same at five
            other gaps (figure 20.2)
  probe     probe.rom on both machines: 13,312 pairs at thirteen gaps; every
            one against the model; the model's REACH and the start of the
            VDP's busy lines, fitted from the pairs alone; and the data
            sheet's 8 microseconds, tried as a rule
  speeds    speeds.rom on both machines: six loops in the paper (figure 20.2)
  blank     blank.rom on both machines: seven loops just after the frame's
            interrupt
  off       off.rom on both machines: seven loops with the display off
  edge      edge.rom and bottom.rom on both machines: unrolled OUTI across
            the top and the bottom of the paper (figure 20.4)
  window    window.rom on both machines: how many bytes unrolled OUTI gets in
            from the frame's interrupt to the paper
  sprites   sprites.rom on both machines: three loops in lines with sprites
            (figure 20.6)
  ignore    speeds.rom with openMSX's too_fast_vram_access set to ignore
            (figure 20.7)
  page      WHERE IT BREAKS: otir.rom and outi.rom, a page copied in the
            paper's lines (figure 20.8); OTIR's first bytes, one by one
  answers   the workshop, tried (for Appendix I)
  openmsx   all of it again with every other build (tools/versions.py)

Every run also counts the writes openMSX calls too soon (its
too_fast_vram_access_callback): for every program they are the bytes the
model says were lost, no more and no fewer.
"""
import json
import math
import re
import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(HERE))
import meas        # noqa: E402
import msxcap      # noqa: E402
import probe as dbg  # noqa: E402  (tools/probe.py; probe() is a section here)
import screentext  # noqa: E402
import versions    # noqa: E402
import gen20       # noqa: E402
import vdpslots    # noqa: E402

CAPS = HERE / "captures"
EU, JP = "MSXBOOK_EU16", "MSXBOOK_JP16"
TAG = {EU: "eu", JP: "jp"}
LINE = vdpslots.LINE
PER_T = vdpslots.PER_T
FRAME = {m: vdpslots.LINES[m] * LINE for m in (EU, JP)}
POS = "[machine_info VDP_frame_count] [machine_info VDP_cycle_in_frame]"
SHOT = 12                   # the film frame photographed, after every test
NAMES = gen20.NAMES

# the writes, recorded while ::on is set; the too-soon callback, counted
RECORD = """set ::on 0
set ::toofast 0
proc ::toofast_cb {args} { if {$::on} { incr ::toofast; L "fast %POS%" } }
set VDP.too_fast_vram_access_callback ::toofast_cb
debug set_watchpoint write_io {0x98 0x99} {} { if {$::on} { L "w %POS% $::wp_last_address $::wp_last_value" } }
debug set_watchpoint read_io 0x98 {} { if {$::on} { L "r %POS% $::wp_last_address" } }
""".replace("%POS%", POS)
REGS = " ".join(f"[debug read {{VDP regs}} {i}]" for i in range(8))


def rom(name):
    return HERE / f"{name}.rom"


def sym(name):
    return dbg.sym(HERE / f"{name}.sym")


def dump(label, addr, n, space="VRAM"):
    return f'binary scan [debug read_block {{{space}}} {addr} {n}] H* h; L "{label} $h"'


def dumps(w, label):
    return [bytes.fromhex(x[1]) for x in w if x[0] == label]


def run(name, frames, tcl, machine=EU, events=None):
    lines = msxcap.run_tcl(rom(name), frames, RECORD + tcl, machine=machine, events=events)
    return [l.split() for l in lines]


def writes(w, machine):
    """[(cycle from the first frame's start, port, value)] and the frame
    number of the first, from the log; value None for a read"""
    ev = [(int(x[1]), int(x[2]), int(x[3]), int(x[4]) if x[0] == "w" else None)
          for x in w if x[0] in ("w", "r")]
    if not ev:
        return [], 0
    f0 = ev[0][0]
    # the watchpoint's address is the whole of the I/O address: the port in
    # the low byte, and A (OUT (n),A) or B (OUT (C),r, OUTI) in the high one
    return [((f - f0) * FRAME[machine] + c, port & 0xFF, v) for f, c, port, v in ev], f0


def start_regs(w):
    return [int(v) for v in next(x for x in w if x[0] == "regs")[1:]]


def fast(w, machine, f0):
    return [(int(x[1]) - f0) * FRAME[machine] + int(x[2]) for x in w if x[0] == "fast"]


def where(cycle, machine):
    """(line, T-state) of a cycle of the frame"""
    line, c = divmod(cycle % FRAME[machine], LINE)
    return line, c / PER_T


def shot(name, frame, machine):
    got = msxcap.capture(rom(name), [frame], CAPS, f"{name}_{TAG[machine]}_f", machine=machine)
    return got[frame]


def page_text(png, machine, rows=24):
    pg = screentext.Page(png, machine)
    return "".join(pg.line(r) for r in range(rows))


def screen_of(nt):
    """the name table as screentext reads it: the boxes as 0 and 1"""
    table = {1: "0", 2: "1"}
    return "".join(table.get(b, chr(b)) for b in nt)


def recorded(name, machine, start, stop, frames, extra="", where_from=None, area=(NAMES, 768),
             extra_after="L end"):
    """record the writes from label START to label STOP, with the name table
    read at START and again at the end of the run; WHERE_FROM: another folder
    with the cartridge and its symbols"""
    folder = where_from or HERE
    s = dbg.sym(folder / f"{name}.sym")
    tcl = (f'set ::bs [debug set_bp {s[start]} {{}} {{ set ::on 1; {dump("before", *area)}; '
           f'L "regs {REGS}"; debug remove_bp $::bs }}]\n'
           f'debug set_bp {s[stop]} {{}} {{ set ::on 0 }}\n' + extra)
    events = {frames: dump("after", *area) + "; " + extra_after}
    lines = msxcap.run_tcl(folder / f"{name}.rom", frames + 1, RECORD + tcl, machine=machine,
                           events=events)
    w = [l.split() for l in lines]
    ev, f0 = writes(w, machine)
    return w, ev, f0


def check_model(ev, w, machine, f0, area=(NAMES, 768)):
    """the model, played the operations from the VRAM as it was, with the
    registers as the debugger read them at the start, must give the VRAM the
    debugger read after; and the bytes it loses must be as many as openMSX
    called too soon. Returns the model's lost operations, the area after and
    the bytes the model's reads gave."""
    start, n = area
    before, after = dumps(w, "before")[0], dumps(w, "after")[0]
    vram = bytearray(16384)
    vram[start:start + n] = before
    got, reads, lost = vdpslots.play(ev, machine, vram, regs=start_regs(w))
    assert bytes(got[start:start + n]) == after, "the VRAM is not the debugger's"
    too_soon = fast(w, machine, f0)
    assert len(too_soon) == len(lost), (len(too_soon), len(lost))
    return lost, after, reads


# ---------------------------------------------------------------- beat
def beat():
    out = {}
    for machine in (EU, JP):
        out[machine] = beat_one(machine)
    assert out[EU]["lost"] == out[JP]["lost"]
    return out


def beat_one(machine, gap=gen20.BEAT_GAP, name="beat", where_from=None, photo=True):
    cells = gen20.beat_cells(gen20.beat_turn(gap))
    if True:
        w, ev, f0 = recorded(name, machine, "bt", "done", 8, where_from=where_from)
        lost, after, _ = check_model(ev, w, machine, f0)
        data = [e for e in ev if e[1] == 0x98]
        assert len(data) == 2 * 228
        firsts = data[0::2]
        assert all(b[0] - a[0] == gap * PER_T for a, b in zip(firsts, data[1::2]))
        phases = []
        for k in range(228):
            line, t = where(firsts[k][0], machine)
            phases.append((line, t))
        # the pairs in order: the k-th made at T-state p of its line, in cells 2p, 2p + 1
        ts = [t for _, t in phases]
        assert ts[0] == gen20.BEAT_P0 and phases[0][0] == vdpslots.PAPER0[machine] + gen20.BEAT_LINE, phases[0]
        assert sorted(ts) == list(range(228)), "a pair at every T-state of a line"
        assert all(vdpslots.active(e[0], machine) for e in ev if e[1] == 0x98)
        lost_t = sorted(int(ts[ev_index_pair(ev, i)]) for i in lost)
        # what the cells say: the filled box first if both arrived
        res = {}
        for k, a in enumerate(cells):
            c = a - NAMES
            res[int(ts[k])] = "ok" if after[c] == gen20.BOX_FULL else "lost"
        meas_lost = sorted(t for t, r in res.items() if r == "lost")
        assert meas_lost == lost_t, (meas_lost, lost_t)
        if photo:
            png = shot(name, 8, machine)
            assert page_text(png, machine) == screen_of(after)
        runs = []
        for t in meas_lost:
            if runs and runs[-1][1] == t - 1:
                runs[-1][1] = t
            else:
                runs.append([t, t])
        return {"first_line": phases[0][0], "lost": meas_lost, "runs": runs,
                "pairs": 228, "lines": [phases[0][0], max(l for l, _ in phases)]}


def beats():
    out = {}
    for g in gen20.BEAT_GAPS:
        r = {m: beat_one(m, g, f"beat{g}") for m in (EU, JP)}
        assert r[EU]["lost"] == r[JP]["lost"]
        out[str(g)] = {"lost": len(r[EU]["lost"]), "runs": r[EU]["runs"],
                       "lines": {TAG[m]: r[m]["lines"] for m in (EU, JP)}}
    return out


def ev_index_pair(ev, i):
    """the pair (0-227) the data write with event index I belongs to"""
    data_idx = [j for j, e in enumerate(ev) if e[1] == 0x98]
    return data_idx.index(i) // 2


# ---------------------------------------------------------------- probe
def pair_lost(w1, w2, machine, reach=vdpslots.REACH, border=vdpslots.BORDER_IN):
    """the model for one pair alone, with REACH and the busy lines' start
    point BORDER as given"""
    old = vdpslots.REACH, vdpslots.BORDER_IN
    vdpslots.REACH, vdpslots.BORDER_IN = reach, border
    try:
        _, _, lost = vdpslots.play([(w1, 0x98, 2), (w2, 0x98, 1)], machine)
        return bool(lost)
    finally:
        vdpslots.REACH, vdpslots.BORDER_IN = old


def probe_run(machine):
    s = sym("probe")
    ends = {g: s[f"e{g}"] for g in gen20.GAPS}
    first = s[f"p{min(gen20.GAPS)}"]
    tcl = (f'set ::bs [debug set_bp {first} {{}} {{ set ::on 1; debug remove_bp $::bs }}]\n'
           f'debug set_bp {s["done"]} {{}} {{ set ::on 0 }}\n' +
           "\n".join(f'debug set_bp {a} {{}} {{ L "e {g} [debug read VRAM {gen20.PROBE_AT}]" }}'
                     for g, a in ends.items()))
    frames = 13 * gen20.PROBE_TRIALS * gen20.PROBE_TURN // (FRAME[machine] // PER_T) + 6
    w = run("probe", frames, tcl, machine)
    ev, f0 = writes(w, machine)
    data = [e for e in ev if e[1] == 0x98]
    checks = [(int(x[1]), int(x[2])) for x in w if x[0] == "e"]
    assert len(data) == 2 * len(checks) == 2 * 13 * gen20.PROBE_TRIALS, (len(data), len(checks))
    trials = []
    for k, (g, v) in enumerate(checks):
        w1, w2 = data[2 * k][0], data[2 * k + 1][0]
        assert w2 - w1 == g * PER_T
        trials.append((w1, w2, g, v == 1))     # the empty box in the first cell: lost
    assert len(fast(w, machine, f0)) == sum(t[3] for t in trials)     # openMSX agrees
    return trials


def probe():
    out = {}
    for machine in (EU, JP):
        trials = probe_run(machine)
        bad = [t for t in trials if pair_lost(t[0], t[1], machine) != t[3]]
        assert not bad, bad[:5]
        by_gap = {}
        for w1, w2, g, l in trials:
            a = vdpslots.active(w1, machine)
            d = by_gap.setdefault(g, {"paper": 0, "paper_lost": 0, "other": 0, "other_lost": 0})
            d["paper" if a else "other"] += 1
            d["paper_lost" if a else "other_lost"] += l
        # the fits: REACH from 0 to 60 cycles, and the T-state of the line at
        # which the VDP starts and stops its busy lines, every cycle of a line
        reach_ok = [r for r in range(0, 61)
                    if all(pair_lost(t[0], t[1], machine, reach=r) == t[3] for t in trials)]
        near = [t for t in trials if abs(t[0] % FRAME[machine] -
                                         (vdpslots.PAPER0[machine] * LINE + 202)) < 2 * LINE
                or abs(t[0] % FRAME[machine] - ((vdpslots.PAPER0[machine] + 192) * LINE + 202)) < 2 * LINE]
        border_ok = [b for b in range(0, LINE)
                     if all(pair_lost(t[0], t[1], machine, border=b) == t[3] for t in near)]
        # the data sheet's figure as a rule: a byte at least 8 microseconds
        # after the one before it, in the paper's lines
        rule_t = 8e-6 * dbg.CLOCK
        sheet = sum(1 for w1, w2, g, l in trials
                    if vdpslots.active(w1, machine) and (g < rule_t) != l)
        out[machine] = {"pairs": len(trials), "by_gap": by_gap, "reach_ok": [min(reach_ok), max(reach_ok)],
                        "reach_all": reach_ok == list(range(min(reach_ok), max(reach_ok) + 1)),
                        "border_ok": [min(border_ok), max(border_ok)], "near": len(near),
                        "sheet_wrong": sheet, "sheet_t": round(rule_t, 2)}
    return out


# ---------------------------------------------------------------- the loops
def block_lost(after, row, n):
    """the bytes of a block of N that never arrived: the text runs short,
    and as many cells at its end keep the space they had"""
    c = 32 * row
    seg = after[c:c + n]
    return len(seg) - len(seg.rstrip(b" "))


def loops(name, speeds, rows, machines, display_on=True, shown=24):
    out = {}
    for machine in machines:
        s = sym(name)
        first, last = f"s{speeds[0]}", f"z{speeds[-1]}"
        w, ev, f0 = recorded(name, machine, first, last, SHOT)
        lost, after, _ = check_model(ev, w, machine, f0)
        data = [e for e in ev if e[1] == 0x98]
        per, res = rows + 1, {}
        n = 32 * rows
        # the data writes of each loop, in order: n each
        for k, sp in enumerate(speeds):
            mine = data[k * n:(k + 1) * n]
            gaps = {mine[i + 1][0] - mine[i][0] for i in range(n - 1)}
            m_lost = sum(1 for i in lost if ev[i] in mine)
            row = per * k + 1
            res[sp] = {"lost": block_lost(after, row, n), "model": m_lost,
                       "gaps_t": sorted({g / PER_T for g in gaps}),
                       "start": list(where(mine[0][0], machine)),
                       "end": list(where(mine[-1][0], machine)),
                       "in_paper": sum(vdpslots.active(e[0], machine, display_on) for e in mine)}
            assert res[sp]["lost"] == m_lost, (sp, res[sp])
        png = shot(name, SHOT, machine)
        assert page_text(png, machine, shown) == screen_of(after)[:32 * shown]
        out[machine] = res
    return out


def speeds():
    return loops("speeds", gen20.SPEEDS, gen20.SPEED_ROWS, (EU, JP))


def blank():
    out = loops("blank", gen20.BLANK, gen20.BLANK_ROWS, (EU, JP))
    assert all(r["lost"] == 0 and r["in_paper"] == 0 for m in out for r in out[m].values())
    return out


def off():
    out = loops("off", gen20.BLANK, gen20.BLANK_ROWS, (EU, JP), display_on=False)
    assert all(r["lost"] == 0 for m in out for r in out[m].values())
    return out


# ---------------------------------------------------------------- edge
def edge():
    return {"top": edge_one("edge"), "bottom": edge_one("bottom")}


def edge_one(name):
    out = {}
    for machine in (EU, JP):
        w, ev, f0 = recorded(name, machine, "s1", "z1", 8)
        lost, after, _ = check_model(ev, w, machine, f0)
        data = [e for e in ev if e[1] == 0x98]
        idx = [data.index(ev[i]) for i in lost]
        inside = [vdpslots.active(e[0], machine) for e in data]
        # the byte at which the run crosses the edge of the busy lines
        cross = next(k for k in range(1, len(data)) if inside[k] != inside[0])
        assert inside[cross:] == [inside[cross]] * (len(data) - cross)
        if inside[0]:
            assert max(idx) < cross         # bottom: lost only in the paper
        else:
            assert min(idx) >= cross        # top: lost only in the paper
        png = shot(name, 8, machine)
        assert page_text(png, machine) == screen_of(after)
        # the point of the line at which the VDP's busy lines begin, fitted
        # from these writes alone: every cycle of the line tried
        before = dumps(w, "before")[0]
        vram = bytearray(16384)
        vram[NAMES:NAMES + 768] = before
        old = vdpslots.BORDER_IN
        fit = []
        try:
            for b in range(LINE):
                vdpslots.BORDER_IN = b
                got = vdpslots.play(ev, machine, vram)[0]
                if bytes(got[NAMES:NAMES + 768]) == after:
                    fit.append(b)
        finally:
            vdpslots.BORDER_IN = old
        out[machine] = {"border_ok": [min(fit), max(fit)],
                        "border_all": fit == list(range(min(fit), max(fit) + 1)), "bytes": len(data),
                        "starts_in_paper": inside[0], "cross": cross,
                        "cross_at": list(where(data[cross][0], machine)),
                        "before_cross_at": list(where(data[cross - 1][0], machine)),
                        "first_lost": min(idx), "first_lost_at": list(where(data[min(idx)][0], machine)),
                        "last_lost": max(idx), "last_lost_at": list(where(data[max(idx)][0], machine)),
                        "lost": len(lost), "start": list(where(data[0][0], machine)),
                        "end": list(where(data[-1][0], machine))}
    return out


# ---------------------------------------------------------------- window
def window():
    out = {}
    area = (gen20.WINDOW_DEST, gen20.WINDOW_N)
    for machine in (EU, JP):
        w, ev, f0 = recorded("window", machine, "s1", "z1", 8, area=area)
        lost, after, _ = check_model(ev, w, machine, f0, area=area)
        data = [i for i, e in enumerate(ev) if e[1] == 0x98]
        assert len(data) == gen20.WINDOW_N
        first_in = next(k for k, i in enumerate(data) if vdpslots.active(ev[i][0], machine))
        assert all(vdpslots.active(ev[i][0], machine) for i in data[first_in:])
        idx = sorted(data.index(i) for i in lost)
        assert idx and idx[0] >= first_in       # every byte before the paper arrived
        t0 = ev[data[0]][0]
        busy = (vdpslots.LINES[machine] + vdpslots.PAPER0[machine]) * LINE + vdpslots.BORDER_IN
        out[machine] = {"before_paper": first_in, "first_lost": idx[0], "lost": len(idx),
                        "start": list(where(t0, machine)),
                        "first_in_paper_at": list(where(ev[data[first_in]][0], machine)),
                        "free_t": round((busy - t0) / PER_T, 3)}
        # the bytes before the paper: as many as fit in the free T-states
        assert first_in == math.ceil(out[machine]["free_t"] / 18)
    return out


# ---------------------------------------------------------------- sprites
def sprites():
    out = loops("sprites", gen20.SPRITE_LOOPS, gen20.SPEED_ROWS, (EU, JP), shown=16)
    # the photograph: a black square at each of the 32 sprites, white beside it
    for machine in (EU, JP):
        im = Image.open(CAPS / f"sprites_{TAG[machine]}_f{SHOT:04d}.png").convert("L")
        for k in range(32):
            x, y = meas.paper(32 + 64 * (k % 4), gen20.SPRITE_TOP + 8 * (k // 4))
            assert im.getpixel((x + 4, y + 4)) < 64 and im.getpixel((x + 12, y + 4)) > 192, k
        out[machine]["drawn"] = 32
    return out


# ---------------------------------------------------------------- ignore
IGNORE = "set too_fast_vram_access ignore"


def ignore():
    tcl = 'L "setting [set too_fast_vram_access]"\n' + IGNORE + "\n"
    w, ev, f0 = recorded("speeds", EU, f"s{gen20.SPEEDS[0]}", f"z{gen20.SPEEDS[-1]}", SHOT,
                         extra=tcl)
    default = next(x[1] for x in w if x[0] == "setting")
    after = dumps(w, "after")[0]
    per, n = gen20.SPEED_ROWS + 1, 32 * gen20.SPEED_ROWS
    want = gen20.text_rows(gen20.SPEED_ROWS).encode()
    whole = [after[32 * (per * k + 1):32 * (per * k + 1) + n] == want for k in range(len(gen20.SPEEDS))]
    assert all(whole) and not fast(w, EU, f0)
    got = msxcap.capture(rom("speeds"), [SHOT], CAPS, "speeds_ignore_eu_f", machine=EU,
                         tcl_setup=IGNORE)
    assert page_text(got[SHOT], EU) == screen_of(after)
    return {"default": default, "whole": sum(whole), "too_soon": 0,
            "bytes": len([e for e in ev if e[1] == 0x98])}


# ---------------------------------------------------------------- reads
def reads():
    out = {}
    n = 32 * gen20.READ_ROWS
    for machine in (EU, JP):
        s = sym("reads")
        res = {}
        for kind, (start, stop, buf) in {"inir": ("r1", "z1", "buf1"),
                                         "ini": ("r2", "z2", "buf2")}.items():
            # the text's rows and the row after them, which the reads do not change
            area = (gen20.addr(gen20.READ_AT["orig"], 0), n + 32)
            w, ev, f0 = recorded("reads", machine, start, stop, 8, area=area,
                                 extra_after=dump("ram", s[buf], n, "memory"))
            lost, after, got = check_model(ev, w, machine, f0, area=area)
            ram = list(dumps(w, "ram")[0])
            assert got == ram, (kind, got[:8], ram[:8])       # the model's reads: the RAM's
            want = list(gen20.text_rows(gen20.READ_ROWS).encode())
            res[kind] = {"wrong": sum(1 for a, b in zip(ram, want) if a != b),
                         "not_made": len(lost), "read": bytes(ram).decode(),
                         "start": list(where(ev[0][0], machine))}
        png = shot("reads", 8, machine)
        pg = screentext.Page(png, machine)
        for kind in ("inir", "ini"):
            r0 = gen20.READ_AT[kind]
            shown = "".join(pg.line(r0 + k) for k in range(gen20.READ_ROWS))
            assert shown == res[kind]["read"], (kind, shown, res[kind]["read"])
        out[machine] = res
    assert out[EU]["ini"]["wrong"] == 0 < out[EU]["inir"]["wrong"]
    return out


# ---------------------------------------------------------------- modes
def longest(slots):
    """the longest a byte waits, in cycles, over every cycle of a line"""
    return max(vdpslots.slot_after(c, slots) - c for c in range(0, LINE))


def modes():
    out = {}
    area = (gen20.MODE_DEST, 6 * 256)
    for machine in (EU, JP):
        w, ev, f0 = recorded("modes", machine, "m0", f"z{2 * len(gen20.MODES) - 1}", 12,
                             area=area)
        lost, after, _ = check_model(ev, w, machine, f0, area=area)
        data = [i for i, e in enumerate(ev) if e[1] == 0x98]
        res, k = {}, 0
        for name, _, _ in gen20.MODES:
            for loop in (18, 23):
                mine = set(data[k * 256:(k + 1) * 256])
                res[f"{name}_{loop}"] = sum(1 for i in lost if i in mine)
                k += 1
        out[machine] = res
    out["longest"] = {"graphic": longest(vdpslots.GFX_SLOTS), "text": longest(vdpslots.TEXT_SLOTS),
                      "off": longest(vdpslots.OFF_SLOTS)}
    out["moments"] = {"graphic": len(vdpslots.GFX_SLOTS), "text": len(vdpslots.TEXT_SLOTS),
                      "off": len(vdpslots.OFF_SLOTS)}
    assert out[EU]["text_18"] == 0 and out[EU]["graphic1_18"] > 0
    return out


# ---------------------------------------------------------------- page
def page():
    out = {}
    for name in ("otir", "outi"):
        w, ev, f0 = recorded(name, EU, "s1", "z1", 10)
        lost, after, _ = check_model(ev, w, EU, f0)
        data = [e for e in ev if e[1] == 0x98]
        assert len(data) == 768
        png = shot(name, 10, EU)
        assert page_text(png, EU) == screen_of(after)
        if name == "otir":
            taken = {}
            vram = bytearray(16384)
            vram[NAMES:NAMES + 768] = dumps(w, "before")[0]
            vdpslots.play(ev, EU, vram, regs=start_regs(w), taken=taken)
            idx = [i for i, e in enumerate(ev) if e[1] == 0x98]
            line0 = where(ev[idx[0]][0], EU)[0]
            first = []
            for k, i in enumerate(idx[:12]):
                at = taken.get(i)
                line, t = where(ev[i][0], EU)
                first.append({"byte": k, "line": line - line0, "t": t, "lost": i in lost,
                              "taken": None if at is None else [where(at, EU)[0] - line0,
                                                                where(at, EU)[1]],
                              "after": None if i not in lost else idx.index(next(
                                  j for j in idx if j > i))})
        out[name] = {"lost": len(lost), "trailing": len(after) - len(after.rstrip(b" ")),
                     "start": list(where(data[0][0], EU)), "end": list(where(data[-1][0], EU)),
                     "rows_right": sum(1 for r in range(24) if after[32 * r:32 * r + 32].decode() ==
                                       gen20.page_rows()[r])}
    out["otir"]["first"] = first
    assert out["outi"]["lost"] == 0 and out["otir"]["lost"] > 0
    return out


# ---------------------------------------------------------------- answers
def build_temp(name, text):
    import shutil
    import subprocess
    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix=f"{name}_"))
    (tmp / f"{name}.asm").write_text(text)
    for inc in ("msx.inc", "bios.inc"):
        shutil.copy(HERE / inc, tmp)
    subprocess.run(["sjasmplus", "--nologo", "--msg=err", "--syntax=bFw", f"--sym={name}.sym",
                    f"{name}.asm"], cwd=tmp, check=True)
    return tmp


Q2_LATER = 5000


def answers():
    import shutil
    out = {}
    # 1: beat.asm with 22 T-states between the two bytes
    tmp = build_temp("q1", gen20.beat(22, "q1"))
    try:
        out["q1"] = beat_one(EU, 22, "q1", tmp, photo=False)["runs"]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    # the T-states a frame outside the VDP's busy lines, and the bytes
    # unrolled OUTI writes in them
    out["free"] = {m: {"t": (vdpslots.LINES[m] - 192) * LINE // PER_T,
                       "bytes": (vdpslots.LINES[m] - 192) * LINE // PER_T // 18} for m in (EU, JP)}
    # 2: window.asm started 5,000 T-states later: the bytes before the paper
    win = json.loads((HERE / "meas20.json").read_text())["window"]
    out["q2"] = {m: {"free_t": win[m]["free_t"], "later": Q2_LATER,
                     "bytes": math.ceil((win[m]["free_t"] - Q2_LATER) / 18)} for m in (EU, JP)}
    # 4: the longest a byte waits in the busy lines, every cycle of a line
    #    on the T-state grid tried; and the probe's pairs at 25 and 26
    longest = max(vdpslots.slot_after(c, True) - c for c in range(0, LINE))
    pr = json.loads((HERE / "meas20.json").read_text())["probe"]
    out["q4"] = {"longest_cycles": longest, "longest_t": round(longest / PER_T, 3),
                 "lost_25": sum(pr[m]["by_gap"]["25"]["paper_lost"] for m in (EU, JP)),
                 "lost_26": sum(pr[m]["by_gap"]["26"]["paper_lost"] for m in (EU, JP))}
    assert out["q4"]["lost_26"] == 0 < out["q4"]["lost_25"]
    return out


# ---------------------------------------------------------------- openmsx
OPENMSX_SECTIONS = ["beat", "beats", "probe", "speeds", "blank", "off", "edge", "window", "sprites",
                    "ignore", "reads", "modes", "page", "answers"]


def openmsx():
    if not versions.builds():
        return {"skipped": "OPENMSX_BUILDS not set"}
    return versions.every_build(["ch20"], OPENMSX_SECTIONS)


SECTIONS = {"beat": beat, "beats": beats, "probe": probe, "speeds": speeds, "blank": blank,
            "off": off, "edge": edge, "window": window, "sprites": sprites, "ignore": ignore,
            "reads": reads, "modes": modes, "page": page, "answers": answers, "openmsx": openmsx}


def main(names=()):
    CAPS.mkdir(exist_ok=True)
    path = HERE / "meas20.json"
    m = json.loads(path.read_text()) if names and path.exists() else {}
    if list(names) == ["--missing"]:
        names = [k for k in SECTIONS if k not in m]
    for name in names or SECTIONS:
        print(name, flush=True)
        m[name] = SECTIONS[name]()
        m = {k: m[k] for k in SECTIONS if k in m}
        path.write_text(json.dumps(m, indent=1) + "\n")
    return m


if __name__ == "__main__":
    out = main(sys.argv[1:])
    print(json.dumps({k: out[k] for k in (sys.argv[1:] or out) if k in out}, indent=1)[:4000])
