#!/usr/bin/env python3
"""meas14.py -- the price of every instruction, measured on the MSX.

    python3 gen14.py && ./build.sh && python3 meas14.py
                                  python3 meas14.py all price    only these
                                  python3 meas14.py --missing    those not measured yet

The model: every instruction's machine cycles from its bytes (cycles.py), as
Zilog's manual lists them, with one more T-state in every M1 (chapter 3).

  all       the time and R before every instruction of all.asm: the time and
            the fetches of each, against cycles.py; and the prices gen14.py
            builds the other programs from, against what all.asm measured
  price     16 calls of putc and the line around them, against the sum of
            their instructions
  budget    budget.rom on both machines: the loop starts at the same T-state
            of every frame, every change of colour at its price, every pixel
            of figure 14.1 the colour the prices give it, the waits on their own
  slow      the wait worked out from Zilog's table, and 256 NOPs, as the MSX
            runs them
  answers   the workshop, tried: questions 1, 3, 4 and 5 (for Appendix I)
  openmsx   all of it again with every other build (tools/versions.py)
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(HERE))
import meas        # noqa: E402
import msxcap      # noqa: E402
import probe       # noqa: E402
import versions    # noqa: E402
import asmparts    # noqa: E402
import cycles      # noqa: E402
import gen14       # noqa: E402

CAPS = HERE / "captures"
CLOCK = probe.CLOCK
EU, JP = "MSXBOOK_EU16", "MSXBOOK_JP16"
POS = "[machine_info VDP_frame_count] [machine_info VDP_cycle_in_frame]"
VDP_PER_T = 6               # the VDP's clock is six times the processor's


def rom(name):
    return HERE / f"{name}.rom"


def sym(name):
    return probe.sym(HERE / f"{name}.sym")


def tstates(a, b):
    return round((b - a) * CLOCK)


def listing(path):
    """[{line, addr, bytes, src}] for every line of a sjasmplus listing with
    bytes; a line whose bytes run on to the next line is joined up"""
    out = []
    for l in Path(path).read_text().splitlines():
        m = re.match(r"\s*(\d+)\+?\s+([0-9A-F]{4}) ((?:[0-9A-F]{2}(?: |$))+)\s*(.*)", l)
        if not m:
            continue
        num, addr = int(m.group(1)), int(m.group(2), 16)
        code, src = [int(x, 16) for x in m.group(3).split()], m.group(4).strip()
        if out and out[-1]["line"] == num:
            out[-1]["bytes"] += code
        else:
            out.append({"line": num, "addr": addr, "bytes": code, "src": src})
    return out


def instr_of(src):
    return " ".join(re.sub(r"^[\w.]+:\s*", "", src).split(";")[0].split())


def build_temp(name, text):
    tmp = Path(tempfile.mkdtemp(prefix=f"{name}_"))
    (tmp / f"{name}.asm").write_text(text)
    shutil.copy(HERE / "msx.inc", tmp)
    subprocess.run(["sjasmplus", "--nologo", "--msg=err", "--syntax=bF", f"--sym={name}.sym",
                    f"--lst={name}.lst", f"{name}.asm"], cwd=tmp, check=True)
    return tmp


# the jumps, calls and returns: chapters 11 and 12
JUMPS = {"call": 18, "ret": 11, "ret_not": 6, "jr": 13, "jr_not": 8, "djnz": 14,
         "djnz_last": 9, "jp": 11}


def price_of(lst, a, b):
    """the MSX price of the instructions of LST from address A up to, not
    including, B, each run once: cycles.py for all but CALL and RET"""
    out = 0
    for x in lst:
        if a <= x["addr"] < b:
            op = instr_of(x["src"]).split()[0]
            out += JUMPS[op] if op in ("call", "ret") else cycles.msx(x["bytes"])
    return out


# ---------------------------------------------------------------- all
def all_():
    s = sym("all")
    lst = {x["addr"]: x for x in listing(HERE / "all.lst")}
    marks = sorted((a, lab) for lab, a in s.items() if re.fullmatch(r"[tf]\d+|done", lab))
    got = probe.times(rom("all"), {lab: a for a, lab in marks}, frames=3)
    assert all(len(v) == 1 for v in got.values()), [k for k, v in got.items() if len(v) != 1]
    at = {lab: got[lab][0] for _, lab in marks}
    rows, groups, kinds = [], {}, Counter()
    for (a, lab), (_, nxt) in zip(marks, marks[1:]):
        if not lab.startswith("t"):
            continue
        x = lst[a]
        ins, code = instr_of(x["src"]), x["bytes"]
        t = tstates(at[lab][0], at[nxt][0])
        r = (at[nxt][1] - at[lab][1]) % 128
        zilog, fetch, want = cycles.tstates(code), cycles.fetches(code), cycles.msx(code)
        assert t == want, (ins, [hex(b) for b in code], t, want)
        if ins != "ld r,a":                     # R is what A was, not a count
            assert r == fetch, (ins, r, fetch)
        assert t - zilog == fetch               # the wait: one for every M1
        pat = cycles.msx_pattern(code)
        rows.append({"instr": ins, "bytes": code, "t": t, "zilog": zilog, "r": r,
                     "cycles": pat})
        groups.setdefault(pat, []).append(ins)
        kinds[("DD CB, FD CB" if code[0] in (0xDD, 0xFD) and code[1] == 0xCB else
               "DD, FD" if code[0] in (0xDD, 0xFD) else "CB" if code[0] == 0xCB else
               "ED" if code[0] == 0xED else "none")] += 1
    assert len(rows) == len(gen14.tests())
    # the prices gen14.py builds budget.asm from, against all.asm
    t = {r["instr"]: r["t"] for r in rows}
    z = {r["instr"]: r["zilog"] for r in rows}
    for k, ins in gen14.MEASURED_BY.items():
        assert gen14.T[k] == t[ins], (k, ins, gen14.T[k], t[ins])
        assert gen14.ZILOG_T[k] == z[ins], (k, ins, gen14.ZILOG_T[k], z[ins])
    return {"count": len(rows), "rows": rows, "kinds": dict(kinds),
            "patterns": {p: {"t": sum(int(c) for c in p.split(",")),
                             "zilog": cycles.tstates(next(r["bytes"] for r in rows
                                                          if r["cycles"] == p)),
                             "n": len(g), "first": g[0]} for p, g in groups.items()},
            "gen14_prices": len(gen14.MEASURED_BY)}


# ---------------------------------------------------------------- price
def price():
    s = sym("price")
    lst = listing(HERE / "price.lst")
    cell = price_of(lst, s["at"], s["putc"])                 # at, through its RET
    putc_own = price_of(lst, s["putc"], s["puts"])           # CALL at and RET included
    per_char = JUMPS["call"] + putc_own + cell               # CALL putc too
    n = len(gen14.LINE_TEXT)
    got = probe.times(rom("price"), {"c1": s["c1"], "c2": s["c2"], "p2": s["p2"]},
                      frames=4, hits=n)
    c1, c2, end = [x[0] for x in got["c1"]], [x[0] for x in got["c2"]], got["p2"][0][0]
    calls = [tstates(a, b) for a, b in zip(c1, c2)]
    assert len(calls) == n and set(calls) == {per_char}, (calls, per_char)
    line = tstates(c1[0], end)
    # each character: the call, INC HL, INC C, JR, LD A,(HL), OR A, and a JR Z
    # that does not jump, but for the last, whose JR Z jumps to the end
    turn = sum(cycles.msx(c) for c in ([0x23], [0x0C], [0x7E], [0xB7])) + JUMPS["jr"]
    model = n * per_char + n * turn + (n - 1) * JUMPS["jr_not"] + JUMPS["jr"]
    assert line == model, (line, model)
    # the screen, read back from the VRAM: the line where it was printed
    v = probe.at_address(rom("price"), s["p2"],
                         f'binary scan [debug read_block VRAM {0x1800 + 32 * gen14.PRICE_ROW} 32] '
                         'H* h; L "vram $h"', frames=4)
    text = bytes.fromhex(next(l for l in v if l.startswith("vram ")).split()[1])
    assert text[:n].decode() == gen14.LINE_TEXT
    return {"per_char": per_char, "chars": n, "line": line, "cell": cell, "putc_own": putc_own,
            "loop_turn": turn, "screen": 768 * per_char}


# ---------------------------------------------------------------- budget
BUDGET_FRAMES = 10
SHOWN = 12                  # the frame of the capture: the loop runs from frame 3


def budget_times(machine):
    s = sym("budget")
    waits = ("w50s", "b50") if machine == EU else ("w60s", "b60")
    labels = {"sync": s["w1s"], "frame": s["frame"], "wait": s[waits[0]], "back": s[waits[1]]}
    labels.update({f"o{k}": s[f"o{k}"] + 6 for k in range(len(gen14.BANDS))})  # the second OUT
    return probe.times(rom("budget"), labels, frames=BUDGET_FRAMES + 8, hits=BUDGET_FRAMES,
                       extra=POS, machine=machine)


def budget_one(machine):
    starts, busy, rest = gen14.loop_plan()
    got = budget_times(machine)
    cyc = {k: [int(x[3]) for x in v] for k, v in got.items()}
    frames = {k: [int(x[2]) for x in v] for k, v in got.items()}
    assert all(c % VDP_PER_T == 0 for v in cyc.values() for c in v)
    f0s = [c // VDP_PER_T for c in cyc["frame"]]
    assert len(f0s) == BUDGET_FRAMES and len(set(f0s)) == 1, f0s     # one frame long, exactly
    fr = frames["frame"]
    assert fr == list(range(fr[0], fr[0] + BUDGET_FRAMES)), fr
    f0 = f0s[0]
    second_out = gen14.T["ld r,n"] + gen14.T["out (n),a"] + gen14.T["ld r,n"]
    for k, st in enumerate(starts):
        assert all(c // VDP_PER_T == f0 + st + second_out for c in cyc[f"o{k}"]), (k, cyc[f"o{k}"])
    waited = {tstates(a[0], b[0]) for a, b in zip(got["wait"], got["back"])}
    assert waited == {rest[machine]}, (waited, rest[machine])
    out = {"f0": f0, "frames": BUDGET_FRAMES, "first_frame": fr[0], "wait": rest[machine],
           "sync": cyc["sync"][0] // VDP_PER_T}
    return out, f0


def budget():
    starts, busy, rest = gen14.loop_plan()
    eu, f0 = budget_one(EU)
    assert eu["sync"] == gen14.SYNC_T, (eu["sync"], gen14.SYNC_T)    # gen14's constant
    assert f0 == gen14.F0
    jp, _ = budget_one(JP)
    # where each change of colour shows: a write at T-state w of a line shows
    # at x = ceil(1.5 w - 31) (chapter 8), in capture row line - 45
    shows = []
    for k, st in enumerate(starts):
        line, x = gen14.write_at(f0, st)
        assert meas.DRAWN[0] + gen14.MARGIN <= x <= meas.DRAWN[1] - gen14.MARGIN
        shows.append((line, x, gen14.COLOUR[gen14.BANDS[k][1]]))
    # the photograph: two frames the same, and every pixel of the drawn
    # columns the colour of the last change before it, the last band's
    # colour (from the frame before) above the first
    got = msxcap.capture(rom("budget"), [SHOWN - 1, SHOWN], CAPS, "budget_f")
    a, b = (Image.open(got[n]).convert("RGB") for n in (SHOWN - 1, SHOWN))
    assert a.tobytes() == b.tobytes(), "budget: the bands move from frame to frame"
    got[SHOWN - 1].unlink()
    shot = CAPS / "budget.png"
    got[SHOWN].replace(shot)
    px = Image.open(shot).convert("L").load()          # grey as the print has it
    first = meas.FRAME_LINE_OF_ROW0[EU]
    checked = 0
    for y in range(meas.CAPTURE_H):
        line = first + y
        for x in range(meas.DRAWN[0], meas.DRAWN[1] + 1):
            want = shows[-1][2]
            for l, cx, c in shows:
                if (l, cx) <= (line, x):
                    want = c
            seen = gen14.COLOUR["BLACK"] if px[x, y] < 90 else gen14.COLOUR["LIGHT_GREEN"]
            assert seen == want, (x, y, px[x, y], want)
            checked += 1
    _, n50, e50, f50 = gen14.wait_code(rest[EU], "w50")
    _, n60, e60, f60 = gen14.wait_code(rest[JP], "w60")
    _, n1, e1, f1 = gen14.wait_code(gen14.preamble_wait(), "w1")
    return {"eu": eu, "jp": jp, "starts": starts, "busy": busy,
            "prices": [b[3] for b in gen14.BANDS], "zilog": [b[4] for b in gen14.BANDS],
            "names": [b[0] for b in gen14.BANDS],
            "rows": [l - first for l, _, _ in shows], "xs": [x for _, x, _ in shows],
            "wait_parts": {"eu": [n50, e50, f50], "jp": [n60, e60, f60]},
            "preamble": gen14.preamble_wait(), "preamble_parts": [n1, e1, f1],
            "vdp_reg": gen14.T_VDP_REG, "choose": gen14.T_CHOOSE,
            "pixels": checked, "frame": SHOWN}


# ---------------------------------------------------------------- slow
def slow():
    s = sym("slow")
    got = probe.times(rom("slow"), {k: s[k] for k in ("s1", "s2", "s3")}, frames=4)
    t1, t2, t3 = (got[k][0][0] for k in ("s1", "s2", "s3"))
    wait, nops = tstates(t1, t2), tstates(t2, t3)
    n, sevens, fours = gen14.zilog_wait(gen14.FRAME_T[EU])
    Z = gen14.ZILOG
    zilog = (Z["ld de,nn"] + n * (Z["dec de"] + Z["ld a,d"] + Z["or e"] + Z["jr"]) -
             (Z["jr"] - Z["jr_not"]) + sevens * Z["ld c,0"] + fours * Z["nop"])
    assert zilog == gen14.FRAME_T[EU]
    # the MSX: the same instructions, one more T-state for each M1
    T = gen14.T
    model = (T["ld rr,nn"] + n * (T["dec de"] + T["ld r,r"] + T["or r"] + T["jr"]) -
             (T["jr"] - T["jr_not"]) + sevens * 8 + fours * T["nop"])
    assert wait == model, (wait, model)
    nops_zilog = Z["call"] + gen14.SLOW_NOPS * Z["nop"] + Z["ret"]
    nops_model = JUMPS["call"] + gen14.SLOW_NOPS * T["nop"] + JUMPS["ret"]
    assert nops == nops_model, (nops, nops_model)
    return {"turns": n, "sevens": sevens, "fours": fours, "zilog": zilog, "wait": wait,
            "over": wait - zilog, "lines_over": round((wait - zilog) / gen14.T_PER_LINE, 1),
            "pct": round(100 * (wait - zilog) / zilog, 1),
            "nops_zilog": nops_zilog, "nops": nops,
            "nops_pct": round(100 * (nops - nops_zilog) / nops_zilog, 1)}


# ---------------------------------------------------------------- answers
def lean_library():
    """putc without keeping HL, and at without keeping DE (question 4)"""
    lib = asmparts.library()
    for old, new in (("at:     push de\n        ld l, b", "at:     ld l, b"),
                     ("        or $40\n        out (VDP_CTRL), a\n        pop de\n        ret",
                      "        or $40\n        out (VDP_CTRL), a\n        ret"),
                     ("putc:   push hl\n        push af", "putc:   push af"),
                     ("        out (VDP_DATA), a\n        pop hl\n        ret",
                      "        out (VDP_DATA), a\n        ret")):
        assert lib.count(old) == 1, old
        lib = lib.replace(old, new)
    return lib


def answers():
    out = {}
    a = json.loads((HERE / "meas14.json").read_text())["all"] if (HERE / "meas14.json").exists() \
        else all_()
    rows = {r["instr"]: r for r in a["rows"]}
    q1 = {k: {"cycles": rows[k]["cycles"], "t": rows[k]["t"]}
          for k in ("ld (ix+5),a", "add a,(iy+5)")}
    out["q1"] = q1
    out["q2"] = {k: rows[k]["cycles"] for k in ("inc (hl)", "ld a,(hl)")}
    # question 3: chapter 11's find, a turn that finds nothing
    se = json.loads((REPO / "ch11" / "meas11.json").read_text())["search"]["turn"]
    turn = rows["cp (hl)"]["t"] + JUMPS["ret_not"] + rows["inc hl"]["t"] + JUMPS["djnz"]
    assert turn == se, (turn, se)
    out["q3"] = {"turn": turn, "parts": [rows["cp (hl)"]["t"], JUMPS["ret_not"],
                                         rows["inc hl"]["t"], JUMPS["djnz"]]}
    # questions 4 and 5, run
    text = gen14.head("answers", "the workshop") + asmparts.TEXT_PAGE + f"""        ld b, 10
        ld c, 0
        ld a, '*'
q4a:    call putc               ; question 4: putc that keeps only AF's A
q4b:    nop
""" + gen14.wait_code(1000, "q5")[0] + """q5e:    nop
""" + asmparts.SHOW_PAGE + lean_library() + asmparts.TAIL
    tmp = build_temp("answers", text)
    try:
        r, s = tmp / "answers.rom", probe.sym(tmp / "answers.sym")
        got = probe.times(r, {k: s[k] for k in ("q4a", "q4b", "q5s", "q5e")}, frames=4)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    lean = tstates(got["q4a"][0][0], got["q4b"][0][0])
    full = json.loads((HERE / "meas14.json").read_text())["price"]["per_char"]
    assert lean == full - 2 * (gen14.T["push"] + gen14.T["pop"]), (lean, full)
    out["q4"] = {"t": lean, "saved": full - lean}
    _, n, e, f = gen14.wait_code(1000, "q5")
    q5 = tstates(got["q5s"][0][0], got["q5e"][0][0])
    assert q5 == 1000
    out["q5"] = {"t": q5, "turns": n, "ld_c": e, "nops": f}
    out["q6"] = {"lines": round(3000 / gen14.T_PER_LINE, 1)}
    return out


# ---------------------------------------------------------------- openmsx
OPENMSX_SECTIONS = ["all", "price", "budget", "slow", "answers"]


def openmsx():
    if not versions.builds():
        return {"skipped": "OPENMSX_BUILDS not set"}
    return versions.every_build(["ch14"], OPENMSX_SECTIONS)


SECTIONS = {"all": all_, "price": price, "budget": budget, "slow": slow, "answers": answers,
            "openmsx": openmsx}


def main(names=()):
    CAPS.mkdir(exist_ok=True)
    path = HERE / "meas14.json"
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
    print(json.dumps({k: (out[k] if k != "all" else {x: y for x, y in out[k].items() if x != "rows"})
                      for k in (sys.argv[1:] or out) if k in out}, indent=1)[:4000])
