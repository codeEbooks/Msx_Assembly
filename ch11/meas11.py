#!/usr/bin/env python3
"""meas11.py -- decisions, measured.

    python3 gen11.py && ./build.sh && python3 meas11.py
                                  python3 meas11.py cost table   only these
                                  python3 meas11.py --missing    those not measured yet

The models: Python's own comparisons and arithmetic; Zilog's T-states plus
one for every M1 (chapters 3 and 7), added up along the path each program
takes.

  map       both pictures of figure 11.1 read back pixel by pixel, against
            A < E worked out in Python, unsigned and signed
  cmp       all 131,072 answers of the two tables, against Python
  cost      every jump, call and return, taken and not, timed one after
            another, against Zilog + M1
  jrfar     jrfar.lst, and sjasmplus on a JR one byte further each way
  loops     the turns DJNZ makes, and the time of four loops
  table     which routine ran and how long each call took, table and chain
  abs       the 512 answers and the time of every call
  idioms    the 1,536 answers, against Python
  bounce    the black cells of figure 11.2, against the same moves made in
            Python; the count of turns
  search    found or not, where, and how long
  answers   the workshop, tried: questions 2, 4, 5 and 6 on the MSX (for
            Appendix I)
  openmsx   all of it again with every other build (tools/versions.py)
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(HERE))
import meas        # noqa: E402
import msxcap      # noqa: E402
import probe       # noqa: E402
import screentext  # noqa: E402
import versions    # noqa: E402
import gen11       # noqa: E402

CAPS = HERE / "captures"
CLOCK = probe.CLOCK
RESULTS = 0xC000
VARS = RESULTS + 0x100


def rom(name):
    return HERE / f"{name}.rom"


def sym(name):
    return probe.sym(HERE / f"{name}.sym")


def finished(name, frame):
    got = msxcap.capture(rom(name), [frame - 1, frame], CAPS, f"{name}_f")
    a, b = (Image.open(got[n]).convert("RGB") for n in (frame - 1, frame))
    assert a.tobytes() == b.tobytes(), f"{name}: still changing at frame {frame}"
    got[frame - 1].unlink()
    return got[frame]


def ink(px, x, y):
    """a pixel of the paper, 1 where the ink is (black on white)"""
    sx, sy = meas.paper(x, y)
    return 1 if sum(px[sx, sy]) < 384 else 0


def bitmap(png, col, row, width, height):
    """the pixels of a block of the paper, a number of `width` bits a line"""
    px = Image.open(png).convert("RGB").load()
    out = []
    for y in range(height):
        v = 0
        for x in range(width):
            v = (v << 1) | ink(px, 8 * col + x, 8 * row + y)
        out.append(v)
    return out


def call_t(rom_path, syms, labels, frames=3, hits=1):
    """the T-states from each label to the instruction after its CALL"""
    got = probe.times(rom_path, {lab: syms[lab] for lab in labels} |
                      {lab + "_": syms[lab] + 3 for lab in labels}, frames=frames, hits=hits)
    return {lab: [round((b[0] - a[0]) * CLOCK) for a, b in zip(got[lab], got[lab + "_"])]
            for lab in labels}


def build_temp(name, text, lst=False):
    tmp = Path(tempfile.mkdtemp(prefix=f"{name}_"))
    (tmp / f"{name}.asm").write_text(text)
    shutil.copy(HERE / "msx.inc", tmp)
    subprocess.run(["sjasmplus", "--nologo", "--msg=err", "--syntax=bF", f"--sym={name}.sym",
                    *([f"--lst={name}.lst"] if lst else []), f"{name}.asm"], cwd=tmp, check=True)
    return tmp


def lst_code(path, addrs):
    """{address: bytes} of the instructions at these addresses, from a
    sjasmplus listing (the bytes are in the twelve columns after the address)"""
    code = {}
    for line in Path(path).read_text().splitlines():
        m = probe.LST.match(line)
        if m and int(m.group(2), 16) in addrs and int(m.group(2), 16) not in code:
            fields = m.group(3)[1:13].split()
            if fields and not any("." in f for f in fields):
                code[int(m.group(2), 16)] = [int(x, 16) for x in fields]
    return code


def signed(v):
    return v - 256 if v & 0x80 else v


def less(a, e, sign):
    return (signed(a) < signed(e)) if sign else (a < e)


# ---------------------------------------------------------------- the models
# Zilog's T-states plus one for each M1, for the instructions on the paths
T = {"call": 18, "call_not": 11, "ret": 11, "ret_cc": 12, "ret_cc_not": 6, "jp": 11,
     "jr": 13, "jr_not": 8, "djnz": 14, "djnz_last": 9, "jp (hl)": 5, "jp (ix)": 10,
     "ld r,n": 8, "ld r,r": 5, "ld rr,nn": 11, "ld ix,nn": 16, "ld r,(hl)": 8,
     "add a,a": 5, "add hl,rr": 12, "inc hl": 7, "ex de,hl": 5, "or a": 5, "cp n": 8,
     "cp (hl)": 8, "nop": 5, "neg": 10, "alu r": 5, "dec bc": 7}

COST_T = {("jp z, c2", True): T["jp"], ("jp nz, never", False): T["jp"], ("jp c4", True): T["jp"],
          ("jr z, c5", True): T["jr"], ("jr nz, never", False): T["jr_not"],
          ("jr c7", True): T["jr"], ("ld b, 2", False): T["ld r,n"],
          ("djnz c8", True): T["djnz"], ("djnz c8", False): T["djnz_last"],
          ("call z, sub", True): T["call"], ("call nz, never", False): T["call_not"],
          ("call sub2", True): T["call"], ("ld hl, c14", False): T["ld rr,nn"],
          ("jp (hl)", True): T["jp (hl)"], ("ld ix, c16", False): T["ld ix,nn"],
          ("jp (ix)", True): T["jp (ix)"], ("nop", False): T["nop"],
          ("ret nz", False): T["ret_cc_not"], ("ret z", True): T["ret_cc"], ("ret", True): T["ret"]}


def t_loop(turns):
    """LD B,n; each turn a NOP and a DJNZ; the last DJNZ falls through"""
    return T["ld r,n"] + turns * (T["nop"] + T["djnz"]) - (T["djnz"] - T["djnz_last"])


BIG_TURN = T["dec bc"] + T["ld r,r"] + T["alu r"] + T["jr"]


def t_big(n):
    return T["ld rr,nn"] + n * BIG_TURN - (T["jr"] - T["jr_not"])


def t_dispatch():
    return (T["call"] + T["add a,a"] + T["ld r,r"] + T["ld r,n"] + T["ld rr,nn"] + T["add hl,rr"] +
            T["ld r,(hl)"] + T["inc hl"] + T["ld r,(hl)"] + T["ex de,hl"] + T["jp (hl)"] +
            T["ld r,n"] + T["ret"])


def t_chain(k):
    tail = T["ld r,n"] + T["ret"]                          # the routine
    if k == 0:
        return T["call"] + T["or a"] + T["jr"] + tail
    return (T["call"] + T["or a"] + T["jr_not"] + (k - 1) * (T["cp n"] + T["jr_not"]) +
            T["cp n"] + T["jr"] + tail)


def t_absj(a):
    return T["call"] + T["or a"] + T["jp"] + (T["neg"] if a & 0x80 else 0) + T["ret"]


def t_absn():
    return T["call"] + 6 * T["alu r"] + T["ret"]


SEARCH_TURN = T["cp (hl)"] + T["ret_cc_not"] + T["inc hl"] + T["djnz"]


def t_find(pos):
    """found in place pos (from 0), or None for not found"""
    if pos is None:
        n = gen11.SEARCH_LEN
        return (T["call"] + (n - 1) * SEARCH_TURN + T["cp (hl)"] + T["ret_cc_not"] + T["inc hl"] +
                T["djnz_last"] + T["ret"])
    return T["call"] + pos * SEARCH_TURN + T["cp (hl)"] + T["ret_cc"]


# ---------------------------------------------------------------- map
MAP_FRAME = 30


def map_():
    png = finished("map", MAP_FRAME)
    side, step = gen11.MAP_SIDE, gen11.MAP_STEP
    counts = []
    for col, sign in zip(gen11.MAP_COLS, (False, True)):
        got = bitmap(png, col, gen11.MAP_ROW, side, side)
        n = 0
        for y in range(side):
            for x in range(side):
                bit = (got[y] >> (side - 1 - x)) & 1
                assert bit == less(step * x, step * y, sign), (sign, x, y)
                n += bit
        counts.append(n)
    page = screentext.Page(png)
    for r, c, t in gen11.MAP_LABELS:
        assert page.text(r, c, len(t)) == t, (r, page.line(r))
    return {"pixels": 2 * side * side, "set": counts, "frame": MAP_FRAME, "step": step}


# ---------------------------------------------------------------- cmp
def cmp_():
    s = sym("cmp")
    tables = {False: probe.block(rom("cmp"), s["half"], gen11.TABLE, 8192, frames=80),
              True: probe.block(rom("cmp"), s["stop"], gen11.TABLE, 8192, frames=250)}
    out, bits = {}, {}
    for sign, got in tables.items():
        b = []
        for d in range(256):
            for e in range(256):
                bit = (got[32 * d + e // 8] >> (7 - e % 8)) & 1
                assert bit == less(d, e, sign), (sign, d, e)
                b.append(bit)
        bits[sign] = b
        out["signed" if sign else "unsigned"] = sum(b)
    out["differ"] = sum(1 for a, b in zip(bits[False], bits[True]) if a != b)
    out["opposite"] = sum(1 for d in range(256) for e in range(256) if (d ^ e) & 0x80)
    out["pairs"] = 2 * 65536
    return out


# ---------------------------------------------------------------- cost
def cost():
    s = sym("cost")
    labels = [lab for lab, _, _ in gen11.COST + gen11.COST_SUBS if lab and lab != "never"]
    got = probe.times(rom("cost"), {lab: s[lab] for lab in labels + ["stop"]}, hits=2)
    events = sorted((t, lab) for lab in got for t, *_ in got[lab])
    tmp = build_temp("cost", (HERE / "cost.asm").read_text(), lst=True)
    try:
        code = lst_code(tmp / "cost.lst", {s[lab] for lab in labels})
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    ins_of = {lab: ins for lab, ins, _ in gen11.COST + gen11.COST_SUBS if lab}
    events = events[:events.index(next(e for e in events if e[1] == "stop")) + 1]
    rows = []
    for (t0, lab), (t1, nxt) in zip(events, events[1:]):
        a = s[lab]
        taken = s[nxt] != a + len(code[a])
        t = round((t1 - t0) * CLOCK)
        ins = ins_of[lab]
        assert COST_T[(ins, taken)] == t, (ins, taken, t)
        rows.append({"instr": ins, "bytes": code[a], "taken": taken, "t": t})
    assert len(rows) == len(COST_T), (len(rows), len(COST_T))
    return {"rows": rows}


# ---------------------------------------------------------------- jrfar
def jrfar():
    found = {}
    for line in (HERE / "jrfar.lst").read_text().splitlines():
        m = probe.LST.match(line)
        if m and m.group(3)[13:].lstrip().startswith(("fwd:", "back:")):
            _, addr, code, src = probe.lst_fields(m)
            found[src.split(":")[0].strip()] = (addr, code)
    assert found["fwd"][1] == [0x18, 0x7F] and found["back"][1] == [0x18, 0x80], found
    out = {"fwd": found["fwd"][1], "back": found["back"][1],
           "fwd_at": found["fwd"][0], "back_at": found["back"][0]}
    tests = {"further_fwd": "        ORG $4000\n        jr ahead\n        ds 128\nahead:  nop\n",
             "further_back": "        ORG $4000\nbehind: nop\n        ds 126\n        jr behind\n"}
    for name, text in tests.items():
        tmp = Path(tempfile.mkdtemp())
        try:
            (tmp / "t.asm").write_text(text)
            r = subprocess.run(["sjasmplus", "--nologo", "--msg=err", "--syntax=bF", "t.asm"],
                               cwd=tmp, capture_output=True, text=True)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        msg = [l for l in (r.stdout + r.stderr).splitlines() if "error" in l]
        assert r.returncode != 0 and msg, (name, r.returncode)
        out[name] = {"exit": r.returncode, "messages": msg}
    return out


# ---------------------------------------------------------------- loops
def loops():
    s = sym("loops")
    n = len(gen11.LOOP_COUNTS)
    marks = [f"{p}{k}" for k in range(len(gen11.LOOP_TIMED)) for p in "df"] + ["g0", "g2"]
    got = probe.times(rom("loops"), {m: s[m] for m in marks})
    tm = {m: got[m][0][0] for m in marks}
    v = probe.memory(rom("loops"), s["stop"], RESULTS, 2 * n)
    turns = [v[2 * k] | v[2 * k + 1] << 8 for k in range(n)]
    assert turns == [256 if b == 0 else b for b in gen11.LOOP_COUNTS], turns
    timed = []
    for k, b in enumerate(gen11.LOOP_TIMED):
        t = round((tm[f"f{k}"] - tm[f"d{k}"]) * CLOCK)
        n_ = 256 if b == 0 else b
        assert t == t_loop(n_), (b, t, t_loop(n_))
        timed.append({"b": b, "turns": n_, "t": t})
    t = round((tm["g2"] - tm["g0"]) * CLOCK)
    assert t == t_big(gen11.BIG_LOOP), (t, t_big(gen11.BIG_LOOP))
    return {"turns": dict(zip(map(str, gen11.LOOP_COUNTS), turns)), "timed": timed,
            "big": {"count": gen11.BIG_LOOP, "t": t, "turn": BIG_TURN},
            "model": {"ld": T["ld r,n"], "nop": T["nop"], "djnz": T["djnz"],
                      "djnz_last": T["djnz_last"]}}


# ---------------------------------------------------------------- table
def table():
    s = sym("table")
    n = gen11.ROUTINES
    t = call_t(rom("table"), s, [f"{p}{k}" for k in range(n) for p in "ab"])
    v = probe.memory(rom("table"), s["stop"], RESULTS, 2 * n)
    rows = []
    for k in range(n):
        assert v[k] == v[n + k] == 17 * k, (k, v[k], v[n + k])
        assert (t[f"a{k}"], t[f"b{k}"]) == ([t_dispatch()], [t_chain(k)]), (k, t[f"a{k}"], t[f"b{k}"])
        rows.append({"k": k, "table": t[f"a{k}"][0], "chain": t[f"b{k}"][0]})
    return {"rows": rows, "step": t_chain(2) - t_chain(1)}


# ---------------------------------------------------------------- abs
def abs_():
    s = sym("abs")
    t = call_t(rom("abs"), s, ["j2", "n2"], frames=5, hits=256)
    got = probe.block(rom("abs"), s["stop"], gen11.ABS_J, 512, frames=5)
    assert len(t["j2"]) == len(t["n2"]) == 256
    for a in range(256):
        want = abs(signed(a)) & 0xFF
        assert got[a] == got[256 + a] == want, (a, got[a], got[256 + a], want)
        assert t["j2"][a] == t_absj(a) and t["n2"][a] == t_absn(), (a, t["j2"][a], t["n2"][a])
    return {"jump": sorted(set(t["j2"])), "nojump": sorted(set(t["n2"])),
            "same_80": got[0x80] == 0x80, "of_81": got[0x81]}


# ---------------------------------------------------------------- idioms
def idioms():
    got = probe.block(rom("idioms"), sym("idioms")["stop"], gen11.IDIOM_TABLE, 256)
    tests = [lambda a: a & 0x80, lambda a: a & 15 == 0, lambda a: a & 1,
             lambda a: a == 1, lambda a: a == 255, lambda a: a >= 100]
    n = len(gen11.IDIOMS)
    yes = [0] * n
    for a in range(256):
        for k, test in enumerate(tests):
            bit = (got[a] >> (8 - n + k)) & 1
            assert bit == bool(test(a)), (a, k, bit)
            yes[k] += bit
    return {"yes": yes, "cases": 256 * n}


# ---------------------------------------------------------------- bounce
BOUNCE_FRAME = 15


def bounce():
    png = finished("bounce", BOUNCE_FRAME)
    x = y = 0
    dx = dy = 1
    seen, turns = set(), 0
    for _ in range(gen11.BOUNCE_STEPS):
        seen.add((x, y))
        x += dx
        if x in (0, gen11.BOUNCE_W - 1):
            dx, turns = -dx, turns + 1
        y += dy
        if y in (0, gen11.BOUNCE_H - 1):
            dy, turns = -dy, turns + 1
    seen.add((x, y))
    px = Image.open(png).convert("RGB").load()
    got = set()
    for r in range(gen11.BOUNCE_H):
        for c in range(gen11.BOUNCE_W):
            cell = sum(ink(px, 8 * c + i, 8 * r + j) for i in range(8) for j in range(8))
            assert cell in (0, 64), (c, r, cell)        # all ink or all paper
            if cell:
                got.add((c, r))
    assert got == seen, (len(got), len(seen))
    n = probe.memory(rom("bounce"), sym("bounce")["done"], VARS + 0x12, 1, frames=BOUNCE_FRAME)[0]
    assert n == turns, (n, turns)
    return {"cells": len(seen), "turns": turns, "end": [x, y], "frame": BOUNCE_FRAME}


# ---------------------------------------------------------------- search
def search():
    s = sym("search")
    data, n = gen11.SEARCH_DATA, len(gen11.SEARCH)
    t = call_t(rom("search"), s, [f"s{k}" for k in range(n)])
    v = probe.memory(rom("search"), s["stop"], RESULTS, 3 * n)
    rows = []
    for k, target in enumerate(gen11.SEARCH):
        where, found = v[2 * k] | v[2 * k + 1] << 8, v[2 * n + k]
        pos = data.index(target) if target in data else None
        want_where = s["list"] + (gen11.SEARCH_LEN if pos is None else pos)
        assert (found, where) == (int(pos is not None), want_where), (k, found, hex(where))
        assert t[f"s{k}"] == [t_find(pos)], (k, t[f"s{k}"], t_find(pos))
        rows.append({"value": target, "at": pos, "found": found, "t": t[f"s{k}"][0]})
    return {"rows": rows, "turn": SEARCH_TURN, "first": t_find(0)}


# ---------------------------------------------------------------- answers
ANSWERS = """        ld hl, 0                ; question 2: how many pairs have D > E, signed
        ld d, 0
q2a:    ld e, 0
q2b:    ld a, e                 ; D > E is E < D:
        push de
        ld e, d                 ; the two swapped
        call slt
        pop de
        jr nc, q2c
        inc hl
q2c:    inc e
        jr nz, q2b
        inc d
        jr nz, q2a
        ld (RESULTS), hl
d4:     ld b, 0                 ; question 4: 256 turns of a body of 20 T-states
e4:     nop
        nop
        nop
        nop
        djnz e4
f4:     nop
"""


def answers():
    out = {}
    # 1: after CP 10, A is 10 or more (0 to 255) when there is no borrow: NC
    out["q1"] = "NC"
    tmp = build_temp("answers", gen11.cart("answers", "the workshop", ANSWERS, after=gen11.SLT))
    try:
        r, s = tmp / "answers.rom", probe.sym(tmp / "answers.sym")
        v = probe.memory(r, s["stop"], RESULTS, 2, frames=150)
        got = probe.times(r, {"d4": s["d4"], "f4": s["f4"]}, frames=150)
        t4 = round((got["f4"][0][0] - got["d4"][0][0]) * CLOCK)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    # 2: slt with the two swapped: D > E signed in 32,640 pairs, as Python counts
    gt = sum(1 for d in range(256) for e in range(256) if signed(d) > signed(e))
    assert v[0] | v[1] << 8 == gt == 32640
    out["q2"] = gt
    # 4: LD B,0, then 256 turns of 20 + DJNZ, the last DJNZ falling through
    want4 = T["ld r,n"] + 256 * (20 + T["djnz"]) - (T["djnz"] - T["djnz_last"])
    assert t4 == want4, (t4, want4)
    out["q4"] = t4
    # 5: a ninth routine: dispatch costs the same, the chain one step more
    tmp = build_temp("table", gen11.table(9))
    try:
        r, s = tmp / "table.rom", probe.sym(tmp / "table.sym")
        t = call_t(r, s, ["a8", "b8"])
        w = probe.memory(r, s["stop"], RESULTS, 18)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    assert w[8] == w[17] == 8 * 17 and t == {"a8": [t_dispatch()], "b8": [t_chain(8)]}, (w, t)
    out["q5"] = {"dispatch": t["a8"][0], "chain": t["b8"][0]}
    # 6: absn on $81 (from the abs section's table): 127
    out["q6"] = 0x7F
    return out


# ---------------------------------------------------------------- openmsx
OPENMSX_SECTIONS = ["map", "cmp", "cost", "loops", "table", "abs", "idioms", "bounce",
                    "search", "answers"]


def openmsx():
    if not versions.builds():
        return {"skipped": "OPENMSX_BUILDS not set"}
    return versions.every_build(["ch11"], OPENMSX_SECTIONS)


SECTIONS = {"map": map_, "cmp": cmp_, "cost": cost, "jrfar": jrfar, "loops": loops,
            "table": table, "abs": abs_, "idioms": idioms, "bounce": bounce, "search": search,
            "answers": answers, "openmsx": openmsx}


def main(names=()):
    CAPS.mkdir(exist_ok=True)
    path = HERE / "meas11.json"
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
