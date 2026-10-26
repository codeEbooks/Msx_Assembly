#!/usr/bin/env python3
"""meas12.py -- subroutines and the stack, measured.

    python3 gen12.py && ./build.sh && python3 meas12.py
                                  python3 meas12.py keep fill    only these
                                  python3 meas12.py --missing    those not measured yet

The models: a stack kept in Python, push by push; Zilog's T-states plus one
for every M1 (chapters 3 and 7), added up along the path each program takes;
the fill done again in Python, cell by cell, in the same order.

  stack     SP before each PUSH, the six bytes written, the pairs after the POPs
  calls     the console at third, three calls deep (calls.txt); SP and BC at the end
  lost      where the RET of a routine that pushed went
  cost      every stack instruction and exchange, timed one after another
  keep      both sets of registers and the clock before, between and after the calls
  frame     IX and the words above it inside sum3; the times; the sum
  say       the three lines read back from the screen; HL and SP at the end
  where     256 calls timed three times, and the frame line each run began on
  irq       how far below SP the BIOS's interrupt routine wrote
  top       the stack at the top of memory, 320 calls deep: the next interrupt
  fill      figure 12.1 read back cell by cell against the fill in Python; the
            calls counted; how deep the stack went
  fillall   the same on an empty screen
  fast      both fills timed; every byte checked, and the bytes either side
  popsum    the eight sums, the interrupts taken, and the damage to the table
  answers   the workshop, tried: questions 1 and 5 on the MSX (for Appendix I)
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
import console     # noqa: E402
import meas        # noqa: E402
import msxcap      # noqa: E402
import probe       # noqa: E402
import screentext  # noqa: E402
import versions    # noqa: E402
import gen12       # noqa: E402

CAPS = HERE / "captures"
CLOCK = probe.CLOCK
RESULTS = 0xC000
TOP = gen12.STACK_TOP
FRAME_T = meas.T_PER_FRAME["MSXBOOK_EU16"]
CYCLES_PER_LINE = 1368                  # VDP cycles in a line: 228 T x 6


def rom(name):
    return HERE / f"{name}.rom"


def sym(name):
    return probe.sym(HERE / f"{name}.sym")


def tstates(a, b):
    return round((b - a) * CLOCK)


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


def build_temp(name, text, lst=False):
    tmp = Path(tempfile.mkdtemp(prefix=f"{name}_"))
    (tmp / f"{name}.asm").write_text(text)
    shutil.copy(HERE / "msx.inc", tmp)
    subprocess.run(["sjasmplus", "--nologo", "--msg=err", "--syntax=bF", f"--sym={name}.sym",
                    *([f"--lst={name}.lst"] if lst else []), f"{name}.asm"], cwd=tmp, check=True)
    return tmp


def lst_lines(path):
    """[(address, bytes, source)] of the lines of a sjasmplus listing that made
    bytes (a line whose bytes end in '...' is left out)"""
    out = []
    for line in Path(path).read_text().splitlines():
        m = probe.LST.match(line)
        if m:
            fields = m.group(3)[1:13].split()
            if fields and not any("." in f for f in fields):
                out.append((int(m.group(2), 16), [int(x, 16) for x in fields],
                            m.group(3)[13:].split(";")[0].strip()))
    return out


def instr(src):
    """the instruction of a source line, without its label"""
    if not src.split():
        return ""
    return src.split(":", 1)[1].strip() if ":" in src.split()[0] else src


def word(v, a):
    return v[a] | v[a + 1] << 8


# ---------------------------------------------------------------- the models
T = {"call": 18, "ret": 11, "push": 12, "pop": 11, "ld r,n": 8, "ld rr,nn": 11,
     "ld ix,nn": 16, "add ix,rr": 17, "ld r,(ix+d)": 21, "add hl,rr": 12, "or a": 5,
     "ex af": 5, "exx": 5, "djnz": 14, "djnz_last": 9, "ld (hl),r": 8, "inc hl": 7,
     "dec r": 5, "jr": 13, "jr_not": 8, "ld (nn),sp": 22, "ld sp,(nn)": 22, "ld sp,nn": 11}

COST_T = {"push bc": 12, "ex (sp), hl": 20, "pop bc": 11, "push ix": 17, "ex (sp), ix": 25,
          "pop ix": 16, "call sub": 18, "ret": 11, "ex af, af'": 5, "exx": 5, "ex de, hl": 5,
          "ld (keep), sp": 22, "ld hl, $C800": 11, "ld sp, hl": 7, "inc sp": 7, "dec sp": 7,
          "add hl, sp": 12, "ld ix, $C800": 16, "ld sp, ix": 12, "ld sp, $C800": 11,
          "ld sp, (keep)": 22, "nop": 5}


class Stack:
    """a stack in Python: memory and SP"""

    def __init__(self, sp):
        self.sp, self.mem = sp, {}

    def push(self, v):
        self.sp = (self.sp - 1) & 0xFFFF
        self.mem[self.sp] = v >> 8
        self.sp = (self.sp - 1) & 0xFFFF
        self.mem[self.sp] = v & 0xFF

    def pop(self):
        v = self.mem[self.sp] | self.mem[(self.sp + 1) & 0xFFFF] << 8
        self.sp = (self.sp + 2) & 0xFFFF
        return v


# ---------------------------------------------------------------- stack
def stack():
    s = sym("stack")
    marks = {f"p{k}": s[f"p{k}"] for k in range(len(gen12.STACK_PAIRS))} | {"full": s["full"]}
    got = probe.times(rom("stack"), marks, extra="[reg sp]")
    end = probe.times(rom("stack"), {"stop": s["stop"]}, extra="[reg sp] [reg bc] [reg de] [reg hl]")
    mem = probe.memory(rom("stack"), s["stop"], TOP - 6, 6)
    model = Stack(TOP)
    before = []
    for r, v in gen12.STACK_PAIRS:
        before.append(model.sp)
        model.push(v)
    got_before = [int(got[f"p{k}"][0][2]) for k in range(len(gen12.STACK_PAIRS))]
    assert got_before == before and int(got["full"][0][2]) == model.sp, (got_before, got["full"])
    assert mem == [model.mem[a] for a in range(TOP - 6, TOP)], mem
    after = {r: model.pop() for r in ("bc", "de", "hl")}
    sp, bc, de, hl = (int(x) for x in end["stop"][0][2:])
    assert (sp, bc, de, hl) == (model.sp, after["bc"], after["de"], after["hl"])
    return {"sp_before": before, "sp_full": TOP - 6,
            "bytes": {f"${TOP - 6 + i:04X}": b for i, b in enumerate(mem)},
            "after": {"sp": sp, "bc": bc, "de": de, "hl": hl}, "left": True}


# ---------------------------------------------------------------- calls
def calls():
    s = sym("calls")
    model = Stack(TOP)
    model.push(s["back0"])
    model.push(0x1111)
    model.push(s["back1"])
    model.push(s["back2"])
    lines = [f"format %04X [reg sp]"] + [f"format %04X [peek16 0x{model.sp + 2 * k:04X}]"
                                         for k in range(4)]
    e = console.session(rom("calls"), lines, start=s["third"])
    words = [int(a, 16) for _, a, _ in e[1:]]
    assert int(e[0][1], 16) == model.sp and words == [s["back2"], s["back1"], 0x1111, s["back0"]], e
    (HERE / "calls.txt").write_text(console.transcript(e))
    end = probe.times(rom("calls"), {"back0": s["back0"]}, extra="[reg sp] [reg bc]")
    sp_end, bc_end = (int(x) for x in end["back0"][0][2:])
    assert (sp_end, bc_end) == (TOP, 0x1111)
    return {"sp": model.sp, "words": words, "returns": {k: s[k] for k in ("back0", "back1", "back2")},
            "sp_end": sp_end, "bc_end": bc_end, "session": [list(x) for x in e]}


# ---------------------------------------------------------------- lost
def lost():
    s = sym("lost")
    got = probe.times(rom("lost"), {"lost": s["lost"]}, extra="[reg sp] [peek16 [reg sp]]")
    sp, left = (int(x) for x in got["lost"][0][2:])
    back = s["back"]
    assert (sp, left) == (TOP - 2, back), (hex(sp), hex(left))
    return {"pc": s["lost"], "sp": sp, "left": left, "back": back, "lost": s["lost"]}


# ---------------------------------------------------------------- cost
def cost():
    s = sym("cost")
    labels = [lab for lab, _, _ in gen12.COST] + ["sub", "stop"]
    got = probe.times(rom("cost"), {lab: s[lab] for lab in labels})
    events = sorted((got[lab][0][0], lab) for lab in labels)
    tmp = build_temp("cost", (HERE / "cost.asm").read_text(), lst=True)
    try:
        code = {a: b for a, b, _ in lst_lines(tmp / "cost.lst")}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    ins_of = {lab: ins for lab, ins, _ in gen12.COST} | {"sub": "ret"}
    rows = []
    for (t0, lab), (t1, _) in zip(events, events[1:]):
        ins, t = ins_of[lab], tstates(t0, t1)
        assert COST_T[ins] == t, (ins, t)
        rows.append({"instr": ins, "bytes": code[s[lab]], "t": t})
    assert len(rows) == len(gen12.COST) + 1
    return {"rows": rows}


# ---------------------------------------------------------------- keep
REGS = "[reg af] [reg bc] [reg de] [reg hl] [reg af2] [reg bc2] [reg de2] [reg hl2]"


def flags_or(a):
    return (a & 0xA8) | (0x40 if a == 0 else 0) | (0x04 if bin(a).count("1") % 2 == 0 else 0)


def keep():
    s = sym("keep")
    got = probe.times(rom("keep"), {k: s[k] for k in ("k1", "k2", "k3")}, extra=REGS)
    rows = [[got[k][0][0]] + [int(x) for x in got[k][0][2:]] for k in ("k1", "k2", "k3")]
    t1, t2 = tstates(rows[0][0], rows[1][0]), tstates(rows[1][0], rows[2][0])
    work = T["ld r,n"] + T["or a"] + 3 * T["ld rr,nn"]
    assert t1 == T["call"] + 4 * T["push"] + work + 4 * T["pop"] + T["ret"], t1
    assert t2 == T["call"] + 2 * (T["ex af"] + T["exx"]) + work + T["ret"], t2
    want = [gen12.KEEP_IN[r] for r in ("af", "bc", "de", "hl")]
    for r in rows:
        assert r[1:5] == want, [hex(x) for x in r[1:5]]
    a = gen12.WORK[0][1]
    work_regs = [a << 8 | flags_or(a)] + [w for _, w in gen12.WORK[1:]]
    assert rows[1][5:] == rows[0][5:]               # keep1 left the second set alone
    assert rows[2][5:] == work_regs, [hex(x) for x in rows[2][5:]]
    return {"t_push": t1, "t_exx": t2, "work": work, "caller": want,
            "push_pop": 4 * (T["push"] + T["pop"]), "swaps": 2 * (T["ex af"] + T["exx"]),
            "second_before": rows[0][5:], "second_after": rows[2][5:]}


# ---------------------------------------------------------------- frame
def frame():
    s = sym("frame")
    words_tcl = " ".join(f"[peek16 [expr {{[reg ix] + {2 * k}}}]]" for k in range(4))
    a = probe.times(rom("frame"), {"f1": s["f1"], "f3": s["f3"]}, extra="[reg sp]")
    b = probe.times(rom("frame"), {"read": s["read"]}, extra=f"[reg ix] {words_tcl}")
    c = probe.times(rom("frame"), {"f2": s["f2"]}, extra="[reg hl] [reg sp]")
    res = probe.memory(rom("frame"), s["stop"], RESULTS, 2)
    model = Stack(TOP)
    for v in gen12.FRAME_ARGS:
        model.push(v)
    sp0 = int(a["f1"][0][2])
    assert sp0 == model.sp
    model.push(s["f1"] + 3)
    ix, *w = (int(x) for x in b["read"][0][2:])
    assert ix == model.sp and w == [s["f1"] + 3] + gen12.FRAME_ARGS[::-1], (hex(ix), w)
    t_call = tstates(a["f1"][0][0], c["f2"][0][0])
    assert t_call == (T["call"] + T["ld ix,nn"] + T["add ix,rr"] + 6 * T["ld r,(ix+d)"] +
                      2 * T["add hl,rr"] + T["ret"]), t_call
    hl, sp1 = int(c["f2"][0][2]), int(c["f2"][0][3])
    t_pops = tstates(c["f2"][0][0], a["f3"][0][0])
    assert hl == word(res, 0) == sum(gen12.FRAME_ARGS) and sp1 == sp0 and int(a["f3"][0][2]) == TOP
    assert t_pops == 3 * T["pop"]
    return {"args": gen12.FRAME_ARGS, "ix": ix, "words": w, "t_call": t_call, "t_pops": t_pops,
            "sum": hl, "sp_in": sp0, "ld_ix": T["ld r,(ix+d)"]}


# ---------------------------------------------------------------- say
SAY_FRAME = 10


def say():
    png = finished("say", SAY_FRAME)
    page = screentext.Page(png)
    lines = []
    for r, c, t in gen12.SAY_TEXTS:
        got = page.text(r, c, len(t) + 1)
        assert got == t + " ", (r, got)
        lines.append(got.rstrip())
    s = sym("say")
    end = probe.times(rom("say"), {"s_end": s["s_end"]}, frames=SAY_FRAME, extra="[reg hl] [reg sp]")
    hl, sp = (int(x) for x in end["s_end"][0][2:])
    assert (hl, sp) == (gen12.SAY_HL, TOP)
    return {"lines": lines, "hl": hl, "sp": sp, "frame": SAY_FRAME}


# ---------------------------------------------------------------- where
def where():
    s = sym("where")
    marks = {f"w{k}": s[f"w{k}"] for k in range(1, 7)}
    got = probe.times(rom("where"), marks, frames=4,
                      extra="[machine_info VDP_cycle_in_frame] [reg sp]")
    model = (T["call"] + T["ld r,n"] + gen12.WHERE_CALLS * (T["call"] + T["ret"] + T["djnz"]) -
             (T["djnz"] - T["djnz_last"]) + T["ret"])
    first = meas.PAPER_FRAME_LINE0["MSXBOOK_EU16"]
    runs = []
    for a, b, display in (("w1", "w2", False), ("w3", "w4", True), ("w5", "w6", True)):
        t = tstates(got[a][0][0], got[b][0][0])
        l0, l1 = (int(got[x][0][2]) // CYCLES_PER_LINE for x in (a, b))
        sp = int(got[a][0][3])
        assert t == model, (a, t, model)
        if display:
            assert first <= l0 and l1 < first + 192, (a, l0, l1)
        runs.append({"sp": sp, "display": display, "lines": [l0, l1], "t": t})
    assert runs[1]["sp"] == TOP and runs[2]["sp"] == gen12.LOW_STACK
    return {"model": model, "runs": runs, "paper_lines": [first, first + 191]}


# ---------------------------------------------------------------- irq
def irq():
    s = sym("irq")
    low = gen12.IRQ_LOW
    got = [probe.block(rom("irq"), s[m], low, TOP - low, frames=4) for m in ("m1", "m2")]
    # a byte written with the paint's own value does not show: painted twice,
    # two ways, every byte written shows in one or the other
    changed = [{low + i for i, x in enumerate(b) if x != paint}
               for b, paint in zip(got, gen12.IRQ_PAINT)]
    both = sorted(changed[0] | changed[1])
    assert both == list(range(min(both), TOP)), both        # one block, from SYS_AREA down
    return {"bytes": TOP - min(both), "lowest": [min(c) for c in changed],
            "shown": [len(c) for c in changed]}


# ---------------------------------------------------------------- top
TOP_FRAMES = 330
HOOK = 0xFD9A                           # H.KEYI, the first hook the routine calls


def top():
    s = sym("top")
    tcl = f"""set ::n 0
set ::after_deep 0
debug set_bp {s['deep']} {{}} {{ set ::after_deep 1; L "deep [machine_info time] [reg sp] [machine_info VDP_frame_count]" }}
set ::bi [debug set_bp 0x0038 {{$::after_deep}} {{ L "isr [machine_info time] [reg sp]"; debug remove_bp $::bi }}]
set ::bh [debug set_bp {HOOK} {{$::after_deep}} {{ L "hook [machine_info time] [debug read memory {HOOK}] [debug read memory {HOOK + 1}]"; debug remove_bp $::bh }}]
set ::bz [debug set_bp 0x0000 {{$::after_deep}} {{ L "zero [machine_info time] [machine_info VDP_frame_count]"; debug remove_bp $::bz }}]
debug set_bp {s['init']} {{$::after_deep}} {{ L "init [machine_info time] [machine_info VDP_frame_count] [reg sp] [debug read memory {HOOK}]" }}
"""
    lines = msxcap.run_tcl(rom("top"), TOP_FRAMES, tcl)
    ev = {}
    for line in lines:
        k, *rest = line.split()
        if k in ("deep", "isr", "hook", "zero", "init") and k not in ev:
            ev[k] = rest
    assert all(k in ev for k in ("deep", "isr", "hook", "zero", "init")), (ev, lines[-5:])
    deep_t, deep_sp, deep_f = float(ev["deep"][0]), int(ev["deep"][1]), int(ev["deep"][2])
    assert deep_sp == 0x10000 - 2 * gen12.TOP_DEPTH, deep_sp
    hook_bytes = [int(x) for x in ev["hook"][1:3]]
    ret = s["dig"] + 8                  # the way back pushed by CALL dig inside dig
    assert hook_bytes == [ret & 0xFF, ret >> 8], (hook_bytes, hex(ret))
    zero_f, init_f = int(ev["zero"][1]), int(ev["init"][1])
    return {"depth": gen12.TOP_DEPTH, "sp_deep": deep_sp, "frame_deep": deep_f,
            "isr_after": tstates(deep_t, float(ev["isr"][0])),
            "hook_after": tstates(float(ev["isr"][0]), float(ev["hook"][0])),
            "zero_after": tstates(float(ev["hook"][0]), float(ev["zero"][0])),
            "hook_bytes": hook_bytes, "way_back": ret, "frame_zero": zero_f,
            "frame_init": init_f, "frames_to_init": init_f - zero_f,
            "init_sp": int(ev["init"][2]), "hook_after_restart": int(ev["init"][3])}


# ---------------------------------------------------------------- fill
def fill_model(walls, seed):
    """the fill as a recursive function, in the order fill.asm takes the cells"""
    sys.setrecursionlimit(10000)
    wall, filled, st = set(walls), set(), {"deep": 0, "calls": 0}

    def f(x, y, d):
        st["calls"] += 1
        st["deep"] = max(st["deep"], d)
        if not (0 <= x < gen12.W and 0 <= y < gen12.H):
            return
        st["deep"] = max(st["deep"], d + 1)     # cell, one call deeper
        if (x, y) in wall or (x, y) in filled:
            return
        filled.add((x, y))
        f(x + 1, y, d + 1)
        f(x - 1, y, d + 1)
        f(x, y + 1, d + 1)
        f(x, y - 1, d + 1)
    f(*seed, 1)
    return filled, st["deep"], st["calls"]


def cells_of(png):
    """each cell of the paper: 'black' (all ink), 'wall' (ink and paper) or 'white'"""
    px = Image.open(png).convert("RGB").load()
    out = {}
    for r in range(gen12.H):
        for c in range(gen12.W):
            n = sum(ink(px, 8 * c + i, 8 * r + j) for i in range(8) for j in range(8))
            out[(c, r)] = "black" if n == 64 else "white" if n == 0 else "wall"
    return out


def stack_depth(name, rom_path, syms, paint_low, frames):
    """how many bytes below SYS_AREA the stack changed, read when fill is done"""
    mem = probe.block(rom_path, syms["filled"], paint_low, TOP - paint_low, frames=frames)
    changed = [paint_low + i for i, b in enumerate(mem) if b != gen12.PAINT]
    assert changed == list(range(min(changed), TOP)), f"{name}: not one block"
    return TOP - min(changed), min(changed)


def fill_step(name, walls, seed, frame):
    png = finished(name, frame)
    got = cells_of(png)
    filled, deepest, calls_ = fill_model(walls, seed)
    for cell, kind in got.items():
        want = "black" if cell in filled else "wall" if cell in walls else "white"
        assert kind == want, (cell, kind, want)
    # every byte fill writes on the stack is a byte of a way back, and no way
    # back has the painted byte in it
    tmp = build_temp(name, (HERE / f"{name}.asm").read_text(), lst=True)
    try:
        rets = [a + len(b) for a, b, src in lst_lines(tmp / f"{name}.lst")
                if instr(src) in ("call fill", "call cell")]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    assert rets and all(gen12.PAINT not in (a & 0xFF, a >> 8) for a in rets)
    s = sym(name)
    n = len(probe.times(rom(name), {"fill": s["fill"]}, frames=frame, hits=10 * calls_)["fill"])
    depth, lowest = stack_depth(name, rom(name), s, gen12.PAINT_LOW, frame)
    assert n == calls_ and depth == 2 * deepest, (n, calls_, depth, deepest)
    return {"cells": len(filled), "walls": len(walls), "calls": n, "deepest": deepest,
            "stack_bytes": depth, "lowest": lowest, "frame": frame}


FILL_FRAME, FILLALL_FRAME = 20, 25


def fill():
    return fill_step("fill", gen12.ring(), gen12.FILL_SEED, FILL_FRAME)


def fillall():
    return fill_step("fillall", [], (0, 0), FILLALL_FRAME)


# ---------------------------------------------------------------- fast
def t_slow():
    n = gen12.BUF_LEN // 256
    return (T["call"] + T["ld rr,nn"] + T["ld r,n"] + T["ld r,n"] +
            n * (T["ld r,n"] + 256 * (T["ld (hl),r"] + T["inc hl"] + T["djnz"]) -
                 (T["djnz"] - T["djnz_last"]) + T["dec r"] + T["jr"]) - (T["jr"] - T["jr_not"]) +
            T["ret"])


def t_quick():
    n = gen12.BUF_LEN // 32
    return (T["call"] + T["ld (nn),sp"] + T["ld sp,nn"] + T["ld rr,nn"] + T["ld r,n"] +
            n * (16 * T["push"] + T["djnz"]) - (T["djnz"] - T["djnz_last"]) + T["ld sp,(nn)"] +
            T["ret"])


def fast():
    s = sym("fast")
    b, n = gen12.BUFFER, gen12.BUF_LEN
    got = probe.times(rom("fast"), {k: s[k] for k in ("f1", "f2", "f3")}, frames=8)
    slow_t, quick_t = tstates(got["f1"][0][0], got["f2"][0][0]), tstates(got["f2"][0][0], got["f3"][0][0])
    assert (slow_t, quick_t) == (t_slow(), t_quick()), (slow_t, quick_t, t_slow(), t_quick())
    before = probe.block(rom("fast"), s["f1"], b - 1, n + 2, frames=8)
    mid = probe.block(rom("fast"), s["f2"], b - 1, n + 2, frames=8)
    after = probe.block(rom("fast"), s["f3"], b - 1, n + 2, frames=8)
    assert mid[1:-1] == [gen12.SLOW_BYTE] * n and after[1:-1] == [gen12.QUICK_WORD & 0xFF] * n
    assert (after[0], after[-1]) == (before[0], before[-1]) == (mid[0], mid[-1])
    return {"slow": slow_t, "quick": quick_t, "bytes": n,
            "per_byte": [round(slow_t / n, 2), round(quick_t / n, 2)],
            "push": T["push"], "ld_inc_djnz": T["ld (hl),r"] + T["inc hl"] + T["djnz"]}


# ---------------------------------------------------------------- popsum
def popsum():
    s = sym("popsum")
    n = 2 * gen12.PASSES
    t = gen12.TABLE
    jf = probe.times(rom("popsum"), {"e0": s["e0"], "e1": s["e1"]}, frames=20,
                     extra=f"[peek16 {gen12.JIFFY}]")
    interrupts = (int(jf["e1"][0][2]) - int(jf["e0"][0][2])) & 0xFFFF
    v = probe.memory(rom("popsum"), s["stop"], RESULTS, 2 * n, frames=20)
    sums = [word(v, 2 * k) for k in range(n)]
    mem = probe.block(rom("popsum"), s["stop"], t, 2 * gen12.TABLE_WORDS, frames=20)
    want_sum = sum(range(gen12.TABLE_WORDS)) & 0xFFFF
    table = [x for k in range(gen12.TABLE_WORDS) for x in (k & 0xFF, k >> 8)]
    damaged = [i for i, (a, b) in enumerate(zip(mem, table)) if a != b]
    blocks = []
    for i in damaged:
        if blocks and i == blocks[-1][1] + 1:
            blocks[-1][1] = i
        else:
            blocks.append([i, i])
    off, on = sums[:gen12.PASSES], sums[gen12.PASSES:]
    assert off == [want_sum] * gen12.PASSES, off
    assert on[0] == want_sum and all(x != want_sum for x in on[1:]), on
    assert damaged and interrupts >= 1, (interrupts, blocks)
    return {"sum": want_sum, "off": off, "on": on, "interrupts": interrupts,
            "blocks": [[t + a, b - a + 1] for a, b in blocks], "damaged": len(damaged)}


# ---------------------------------------------------------------- answers
ANSWERS = """        ld sp, $E000            ; question 1
        ld bc, $1234
        push bc
        ld (RESULTS), sp
        ld sp, SYS_AREA
"""


def fill_pushing(name):
    """fill.asm's routine with PUSH DE at the top and POP DE before every RET"""
    src = (HERE / f"{name}.asm").read_text()
    body = src[src.index("fill:   ld a, d"):src.index("; cell:")]
    new = body.replace("fill:   ld a, d", "fill:   push de                 ; question 5\n        ld a, d")
    new = new.replace("ret nc", "jr nc, fx").replace("ret nz", "jr nz, fx")
    new = new.replace("        inc e\n        ret\n", "        inc e\nfx:     pop de\n        ret\n")
    assert new.count("fx") == 4
    low = TOP - 4096
    src = src.replace(body, new).replace(f"${gen12.PAINT_LOW:04X}", f"${low:04X}")
    src = src.replace(f"${gen12.PAINT_LOW + 1:04X}", f"${low + 1:04X}")
    src = src.replace(f"ld bc, {TOP - gen12.PAINT_LOW} - 1", f"ld bc, {TOP - low} - 1")
    return src, low


def answers():
    out = {}
    tmp = build_temp("answers", gen12.cart("answers", "the workshop", ANSWERS))
    try:
        r, s = tmp / "answers.rom", probe.sym(tmp / "answers.sym")
        v = probe.memory(r, s["stop"], RESULTS, 2)
        m = probe.memory(r, s["stop"], 0xDFFE, 2)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    assert word(v, 0) == 0xDFFE and m == [0x34, 0x12]
    out["q1"] = {"sp": word(v, 0), "c_at": 0xDFFE, "b_at": 0xDFFF}
    src, low = fill_pushing("fillall")
    tmp = build_temp("fillall", src)
    try:
        r, s = tmp / "fillall.rom", probe.sym(tmp / "fillall.sym")
        depth, _ = stack_depth("fillall+push", r, s, low, FILLALL_FRAME)
        png = msxcap.capture(r, [FILLALL_FRAME], tmp, "q5_f")[FILLALL_FRAME]
        black = sum(1 for k in cells_of(png).values() if k == "black")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    assert black == gen12.W * gen12.H
    out["q5"] = {"stack_bytes": depth, "cells": black}
    return out


# ---------------------------------------------------------------- openmsx
OPENMSX_SECTIONS = ["stack", "calls", "lost", "cost", "keep", "frame", "say", "where", "irq",
                    "top", "fill", "fillall", "fast", "popsum", "answers"]


def openmsx():
    if not versions.builds():
        return {"skipped": "OPENMSX_BUILDS not set"}
    return versions.every_build(["ch12"], OPENMSX_SECTIONS)


SECTIONS = {"stack": stack, "calls": calls, "lost": lost, "cost": cost, "keep": keep,
            "frame": frame, "say": say, "where": where, "irq": irq, "top": top, "fill": fill,
            "fillall": fillall, "fast": fast, "popsum": popsum, "answers": answers,
            "openmsx": openmsx}


def main(names=()):
    CAPS.mkdir(exist_ok=True)
    path = HERE / "meas12.json"
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
