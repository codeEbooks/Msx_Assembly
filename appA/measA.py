#!/usr/bin/env python3
"""measA.py -- every documented instruction, timed and run, on openMSX.

    python3 genA.py && ./build.sh && python3 measA.py [step ...]

    times    times.rom on MSXBOOK_EU16: the time, R, F and the word on top of
             the stack at every label. Each instruction's time and the
             fetches that R counts, against its cycles (chapter 14's
             cycles.py, and cyclesA.py for the jumps, the block
             instructions, HALT and the interrupt's answer), on the MSX and
             in Zilog's manual; a turn of HALT, from two HALTs of different
             lengths; the answer in each mode
    flags    flags.rom: every register, the shadow ones too, and the bytes
             around after each of its runs. The same program run on
             z80.py, this appendix's model of the processor, must give the
             same numbers; each of the six documented flags of each
             instruction is then unchanged, always 1, always 0, or set by
             what the instruction did, and P/V is checked against what it
             stands for in each instruction: the overflow, the parity, BC
             not 0, IFF2, Z, the byte popped or swapped in (INI to OTDR
             apart: Appendix B)
    before   the times of chapters 11, 12, 13, 14 and 17, against these
    bus      each instruction on the model alone: every fetch, read, write
             and port cycle starts where its cycles put it
    table    the appendix's rows: times, fetches, cycles and flags
    example  chapter 13's three copies and its OTIR, priced from the rows,
             against what chapter 13 measured; OUTI and JP NZ against the
             29 T-states of chapter 20
    openmsx  times and flags again with every other build (tools/versions.py)

Writes measA.json.
"""
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
for d in ("tools", "ch14"):
    sys.path.insert(0, str(REPO / d))
sys.path.insert(0, str(HERE))
import msxcap      # noqa: E402
import probe       # noqa: E402
import versions    # noqa: E402
import cycles      # noqa: E402
import cyclesA     # noqa: E402
import iset        # noqa: E402
import genA        # noqa: E402
import z80         # noqa: E402
from asmparts import IM2_VECTOR  # noqa: E402

CLOCK = probe.CLOCK
FLAG_BITS = [("S", 7), ("Z", 6), ("H", 4), ("PV", 2), ("N", 1), ("C", 0)]
DOCUMENTED = 0xD7               # S Z H P/V N C: bits 3 and 5 are Appendix B's
OUT_JSON = HERE / "measA.json"


def rom_bytes(name):
    return (HERE / f"{name}.rom").read_bytes()


def T(a, b):
    return round((b - a) * CLOCK)


# ---------------------------------------------------------------- times
LOG = '[machine_info time] [reg r] [reg af] [peek16 [reg sp]]'


def times_tcl(s, cs):
    """the debugger's commands for times.rom, which measA.py also keeps in
    times.tcl: B prints a mark's name, the time, R, AF and the word on top
    of the stack"""
    out = ["# times.tcl - written by measA.py: openMSX's breakpoints for times.rom",
           f'proc B {{name}} {{ L "B $name {LOG}" }}']
    for c, (r, what, setup, rst) in enumerate(cs, start=1):
        out.append(f'debug set_bp 0x{s[f"t{c}"]:04X} {{}} {{B t{c}}}')
        if rst is None:
            out.append(f'debug set_bp 0x{s[f"e{c}"]:04X} {{}} {{B e{c}}}')
    out.append("# an RST lands in the BIOS: back to e, the address it pushed")
    for q in range(0, 64, 8):
        out.append(f'debug set_bp 0x{q:04X} {{[reg sp] == 0x{genA.RSTK - 2:04X}}} '
                   f'{{B rst{q:02X}; reg pc [peek16 [reg sp]]}}')
    for k in range(1, len(genA.HALT_TURNS) + 1):
        out.append(f'debug set_bp 0x{s[f"h{k}"]:04X} {{}} {{B h{k}}}')
    out.append(f'debug set_bp 0x{IM2_VECTOR:04X} {{}} {{B vec}}')
    out.append("# modes 1 and 0 go to $0038: back to the byte after HALT, as RET would")
    out.append(f'debug set_bp 0x0038 {{[reg sp] == 0x{genA.ISTK - 2:04X}}} '
               '{B int; reg pc [peek16 [reg sp]]; reg sp [expr {[reg sp] + 2}]}')
    out.append(f'debug set_bp 0x{s["done"]:04X} {{}} {{B done; L done; exit}}')
    return "\n".join(out) + "\n"


def run_times():
    s = probe.sym(HERE / "times.sym")
    cs = genA.cases()
    tcl = times_tcl(s, cs)
    (HERE / "times.tcl").write_text(tcl)
    lines = msxcap.run_tcl(HERE / "times.rom", 600, tcl)
    marks = []
    for l in lines:
        if l.startswith("B "):
            _, name, t, r, af, w = l.split()
            marks.append((name, float(t), int(r), int(af), int(w)))
    return s, cs, marks


def times(res):
    s, cs, marks = run_times()
    rom = rom_bytes("times")
    k = 0

    def take(name):
        nonlocal k
        m = marks[k]
        assert m[0] == name, (m, name, k)
        k += 1
        return m

    out = []
    for c, (r, what, setup, rst) in enumerate(cs, start=1):
        hits = [take(f"t{c}")]
        while marks[k][0] == f"t{c}":                   # a block instruction going round
            hits.append(take(f"t{c}"))
        end = take(f"rst{rst:02X}" if rst is not None else f"e{c}")
        ms = hits + [end]
        ts = [T(a[1], b[1]) for a, b in zip(ms, ms[1:])]
        rs = [(b[2] - a[2]) % 128 for a, b in zip(ms, ms[1:])]
        a0, a1 = s[f"t{c}"], s[f"e{c}"]
        out.append({"c": c, "n": r["n"], "what": what, "t": ts, "r": rs,
                    "f": [hits[0][3] & 255, end[3] & 255], "word": end[4], "e": a1,
                    "bytes": list(rom[a0 - 0x4000:a1 - 0x4000])})
    halts = []
    for kk, (im, turns) in enumerate(genA.HALT_TURNS, start=1):
        take("vec")                                     # the HALT that waits for the signal
        h = take(f"h{kk}")
        e = take("vec" if im == 2 else "int")
        halts.append({"im": im, "dt": T(h[1], e[1]), "dr": (e[2] - h[2]) % 128,
                      "f": [h[3] & 255, e[3] & 255], "ret": e[4], "h": s[f"h{kk}"]})
    take("done")
    assert all(m[0] == "done" for m in marks[k:])      # exit takes a moment
    res["times"] = check_times(cs, out, halts)


def msx_cycles(r, b, taken=True):
    """the MSX's cycles and Zilog's of one case"""
    if r["kind"] == "plain":
        z = cycles.of(b)
    else:
        z = cyclesA.of(r["key"], taken)
    return cyclesA.msx(z), z


def check_times(cs, out, halts):
    rows = {r["n"]: r for r in iset.rows()}
    by_row = {}
    for x in out:
        r = rows[x["n"]]
        key = list(r["key"])
        b = x["bytes"]
        # the bytes are the instruction's: its prefixes and opcode, with the
        # distance between them for DD CB and FD CB
        if len(key) == 3 and key[1] == 0xCB:
            assert b[:2] == key[:2] and b[3] == key[2] and b[2] == genA.D, (r["text"], b)
        else:
            assert b[:len(key)] == key, (r["text"], b, key)
        if r["kind"] == "repeat":
            again, zagain = msx_cycles(r, b, True)
            last, zlast = msx_cycles(r, b, False)
            n = len(x["t"])
            assert x["t"] == [cyclesA.tstates(again)] * (n - 1) + [cyclesA.tstates(last)], x
            assert x["r"] == [cyclesA.fetches(again)] * (n - 1) + [cyclesA.fetches(last)], x
            want = 2 if x["what"] == "found" else genA.TURNS
            assert n == want, (r["text"], x["t"])
            cyc, zcyc = [again, last], [zagain, zlast]
        else:
            taken = x["what"] != "not"
            m, z = msx_cycles(r, b, taken)
            cyc, zcyc = [m], [z]
            assert x["t"] == [cyclesA.tstates(m)], (r["text"], x["what"], x["t"])
            if r["text"] != "LD R,A":                   # R is what A was, not a count
                assert x["r"] == [cyclesA.fetches(m)], (r["text"], x["what"], x["r"])
            if r["text"].startswith("RST"):             # F as it was, at the BIOS
                assert x["f"][0] == x["f"][1] == int(x["what"][1:], 16), x
                assert x["word"] == x["e"], x           # the address after RST
        # the wait: one T-state for every fetch
        for m, z in zip(cyc, zcyc):
            assert cyclesA.tstates(m) - cyclesA.tstates(z) == cyclesA.fetches(z)
        by_row.setdefault(str(x["n"]), []).append({
            "what": x["what"], "t": x["t"], "r": x["r"],
            "zilog": [cyclesA.tstates(z) for z in zcyc],
            "cycles": [cyclesA.pattern(m) for m in cyc],
            "zcycles": [cyclesA.pattern(z) for z in zcyc], "f": x["f"]})
    # HALT: N turns, then the answer. The two in mode 2 wait different
    # numbers of turns: the difference in time over the difference in
    # turns is a turn's length
    for h in halts:
        h["turns"] = h["dr"] - 2                        # less EI and the answer
        assert 3 <= h["turns"] <= 100, h
    a, b = halts[0], halts[1]
    turn = (b["dt"] - a["dt"]) / (b["turns"] - a["turns"])
    halt_t = cyclesA.tstates(cyclesA.msx(cyclesA.halt()))
    assert turn == halt_t == 5, turn
    ei = cyclesA.tstates(cyclesA.msx(cycles.of([0xFB])))
    for h in halts:
        h["answer"] = h["dt"] - ei - halt_t * h["turns"]
        assert h["answer"] == cyclesA.tstates(cyclesA.msx(cyclesA.answer(h["im"]))), h
        assert h["ret"] == h["h"] + 2                   # back to the byte after HALT
    for h, f in zip(halts, genA.HALT_F):
        assert h["f"] == [f, f], h                      # F as it was
    return {"cases": len(out), "rows": by_row, "halts": halts, "turn": turn, "ei": ei}


# ---------------------------------------------------------------- flags
NAMES = ["af", "bc", "de", "hl", "ix", "iy", "sp", "i", "r", "iff1", "iff2", "im",
         "af2", "bc2", "de2", "hl2", "win0", "win4", "stk"]


def flags_tcl(after, done):
    """the debugger's commands for flags.rom, kept in flags.tcl too: R and
    port $A8 at INIT, for the model; at after, every register and the bytes
    at WIN and around STK, in hexadecimal"""
    return "\n".join([
        "# flags.tcl - written by measA.py: openMSX's breakpoints for flags.rom",
        'proc H {a n} { binary scan [debug read_block memory $a $n] H* h; return $h }',
        'L "I [reg r] [debug read ioports 0xA8]"',
        f'debug set_bp 0x{after:04X} {{}} {{L "A [reg af] [reg bc] [reg de] [reg hl] [reg ix] '
        '[reg iy] [reg sp] [reg i] [reg r] [reg iff] [reg im] [reg af2] [reg bc2] [reg de2] '
        f'[reg hl2] [H 0x{genA.WIN:04X} 8] [H 0x{genA.STK - 2:04X} 4]"}}',
        f'debug set_bp 0x{done:04X} {{}} {{L done; exit}}']) + "\n"


def le32(h):
    return int.from_bytes(bytes.fromhex(h), "little")


def run_flags():
    s = probe.sym(HERE / "flags.sym")
    tcl = flags_tcl(s["after"], s["done"])
    (HERE / "flags.tcl").write_text(tcl)
    lines = msxcap.run_tcl(HERE / "flags.rom", 3000, tcl)
    init = next(l for l in lines if l.startswith("I ")).split()
    out = []
    for l in lines:
        if l.startswith("A "):
            v = l.split()[1:]
            af, bc, de, hl, ix, iy, sp, i, r, iff, im, af2, bc2, de2, hl2 = (int(x) for x in v[:15])
            out.append([af, bc, de, hl, ix, iy, sp, i, r, iff & 1, iff >> 1 & 1, im,
                        af2, bc2, de2, hl2, le32(v[15][:8]), le32(v[15][8:]), le32(v[16])])
    return s, {"r": int(init[1]), "a8": int(init[2])}, out


def model_runs(s, init):
    """flags.rom on z80.py, from INIT with openMSX's R: the same numbers at
    the same places"""
    rom = rom_bytes("flags")
    z = z80.Z80(rom, z80.Ports(init["a8"]))
    z.pc = rom[2] | rom[3] << 8
    z.r = init["r"]
    m = z.m
    rd16 = lambda a: m[a] | m[a + 1] << 8
    rd32 = lambda a: rd16(a) | rd16(a + 2) << 16
    after, done = s["after"], s["done"]
    out = []
    while z.pc != done:
        if z.pc == after:
            out.append([z.af, z.bc, z.de, z.hl, z.ix, z.iy, z.sp, z.i, z.r, z.iff1, z.iff2, z.im,
                        z.a_ << 8 | z.f_, z.b_ << 8 | z.c_, z.d_ << 8 | z.e_, z.h_ << 8 | z.l_,
                        rd32(genA.WIN), rd32(genA.WIN + 4), rd32(genA.STK - 2)])
        z.step()
    return out


def parity(v):
    return 1 - bin(v).count("1") % 2


def flags(res):
    s, init, emu = run_flags()
    runs = planned_runs()
    assert len(emu) == len(runs), (len(emu), len(runs))
    model = model_runs(s, init)
    assert len(model) == len(runs)
    # openMSX and the model, number by number; F's bits 3 and 5 apart
    differ, hidden = 0, {}
    for (r, st, f), a, b in zip(runs, emu, model):
        for name, x, y in zip(NAMES, a, b):
            if name == "af":
                if (x ^ y) & 0xFF00 or (x ^ y) & DOCUMENTED:
                    differ += 1
                    print("  differs:", r["text"], name, hex(x), hex(y), hex(f), st)
                elif (x ^ y) & 0x28:
                    hidden[r["text"]] = hidden.get(r["text"], 0) + 1
            elif x != y:
                differ += 1
                print("  differs:", r["text"], name, hex(x), hex(y), hex(f), st)
    assert differ == 0, differ
    by = {}
    for (r, st, f), a in zip(runs, emu):
        by.setdefault(r["n"], []).append((r, st, f, dict(zip(NAMES, a))))
    rows = {str(n): classify(v) for n, v in by.items()}
    res["flags"] = {"runs": len(runs), "values": len(runs) * len(NAMES), "rows": rows,
                    "hidden": hidden, "states": sum(len(v) for v in genA.groups().values()),
                    "facts": facts(by), "sz": sum(c["sz_checked"] for c in rows.values()),
                    "groups": {g: len(v) for g, v in genA.groups().items()},
                    "group_rows": group_rows(), "init_r": init["r"]}


def group_rows():
    """how many instructions run with each group"""
    out = {}
    for r, lab, pre, ins, grp in genA.flag_runs():
        out.setdefault(grp, set()).add(r["n"])
    return {g: len(v) for g, v in out.items()}


def facts(by):
    """what the appendix says of a few instructions, from their runs"""
    text = {}
    for r in iset.rows():
        text.setdefault(r["text"], r["n"])          # LD HL,(nn): the short one
    runs = lambda t: by[text[t]]
    out = {}
    # CCF: H is the carry as it was
    assert all((a["af"] >> 4 & 1) == (f & 1) for _, s, f, a in runs("CCF"))
    out["ccf"] = len(runs("CCF"))
    # SBC A,A: A is 0, or $FF if the carry was set, and the carry stays
    assert all(a["af"] >> 8 == (0xFF if f & 1 else 0) and (a["af"] & 1) == (f & 1)
               for _, s, f, a in runs("SBC A,A"))
    out["sbc_aa"] = len(runs("SBC A,A"))
    # SUB A and CP A: A minus itself
    for t in ("SUB A", "CP A", "XOR A"):
        assert all((a["af"] & 0xFF) & DOCUMENTED == {"SUB A": 0x42, "CP A": 0x42, "XOR A": 0x44}[t]
                   for _, s, f, a in runs(t)), t
    # RR: S is the carry that goes in at bit 7
    assert all((a["af"] >> 7 & 1) == (f & 1) for _, s, f, a in runs("RR B"))
    # LD A,I and LD A,R: P/V is IFF2, 0 after DI, 1 after EI
    for t in ("LD A,I", "LD A,R"):
        pv = {("ei" in s["pre"], a["af"] >> 2 & 1) for _, s, f, a in runs(t)}
        assert pv == {(False, 0), (True, 1)}, (t, pv)
    # IN r,(C): what each port read
    got = {}
    for _, s, f, a in runs("IN A,(C)"):
        port = s["bc"] & 0xFF
        got.setdefault(f"{port:02X}", set()).add(a["af"] >> 8)
        assert a["af"] >> 8 == (s["psg"] if port == genA.IN_PORT else 0xFF), (s, a)
    out["in"] = {k: sorted(v) for k, v in sorted(got.items())}
    # the block instructions that move a byte through a port: N is its bit 7
    for t in ("INI", "IND", "INIR", "INDR", "OUTI", "OUTD", "OTIR", "OTDR"):
        for _, s, f, a in runs(t):
            n = a["af"] >> 1 & 1
            if t.startswith("IN"):
                hl = (a["hl"] - (1 if t in ("INI", "INIR") else -1)) & 0xFFFF
                byte = (a["win0"] | a["win4"] << 32) >> 8 * (hl - genA.WIN) & 0xFF
            else:
                last = (a["hl"] - (1 if t in ("OUTI", "OTIR") else -1)) & 0xFFFF
                byte = s["win"][last - genA.WIN]
            assert n == byte >> 7, (t, s, a)
    out["n_bit7"] = True
    # ADD HL,ss, ADD IX,pp and ADD IY,rr: H is the carry out of bit 11
    for t in [r["text"] for r in iset.rows() if r["form"] in ("ADD HL,ss", "ADD IX,pp", "ADD IY,rr")]:
        for _, s, f, a in runs(t):
            x = s["hl"] if "HL" in t[:6] else s[t[4:6].lower()]
            y = {"BC": s["bc"], "DE": s["de"], "SP": s["sp"]}.get(t[-2:], x)
            assert (a["af"] >> 4 & 1) == ((x & 0xFFF) + (y & 0xFFF) > 0xFFF), (t, s, a)
    out["h11"] = True
    # the eight-bit sums: H is the carry (or the borrow) out of bit 3
    for r in iset.rows():
        t = r["text"]
        if r["family"] != "arith8" or not t.startswith(("ADD", "ADC", "SUB", "SBC", "CP")):
            continue
        for _, s, f, a in runs(t):
            x, y = s["a"] & 15, operand(r, s) & 15
            c = f & 1 if t.startswith(("ADC", "SBC")) else 0
            h = x + y + c > 15 if t.startswith(("ADD", "ADC")) else x - y - c < 0
            assert (a["af"] >> 4 & 1) == h, (t, s, a)
    out["h3"] = True
    # BIT b: Z when the bit is 0; S only for bit 7 set
    for r in iset.rows():
        t = r["text"]
        if not t.startswith("BIT"):
            continue
        b = int(t[4])
        for _, s, f, a in runs(t):
            v = reg8(s, t.split(",")[1])
            assert (a["af"] >> 6 & 1) == (not v >> b & 1), (t, s, a)
            assert (a["af"] >> 7 & 1) == (b == 7 and v >> 7), (t, s, a)
    out["bit"] = True
    # CPI and CPD: Z when the byte at HL is A
    for t in ("CPI", "CPD"):
        for _, s, f, a in runs(t):
            byte = s["win"][s["hl"] - genA.WIN]
            assert (a["af"] >> 6 & 1) == (byte == s["a"]), (t, s, a)
    # INI, IND, OUTI, OUTD: Z when B reaches 0
    for t in ("INI", "IND", "OUTI", "OUTD"):
        for _, s, f, a in runs(t):
            assert (a["af"] >> 6 & 1) == (a["bc"] >> 8 == 0), (t, s, a)
    out["z"] = True
    return out


REG8 = {"B": ("bc", 8), "C": ("bc", 0), "D": ("de", 8), "E": ("de", 0), "H": ("hl", 8),
        "L": ("hl", 0)}


def reg8(state, name):
    """register NAME of a state before (a dict of genA's) or after (the
    numbers read), (HL) and the like the byte at WIN+4"""
    if name.startswith("("):
        return state["win"][4] if "win" in state else state["win4"] & 0xFF
    if name == "A":
        return state["a"] if "win" in state else state["af"] >> 8
    pair, shift = REG8[name]
    return state[pair] >> shift & 0xFF


def signed(v, bits):
    return v - (1 << bits) if v >> (bits - 1) else v


def operand(r, s):
    """the second operand of an eight-bit sum, as the state gave it"""
    t = r["text"]
    src = t.split(",")[-1] if "," in t else t.split(" ")[-1]
    if src == "n":
        return int(s["ins"].split("$")[-1], 16)
    return reg8(s, src)


def pv_kind(r):
    t, f = r["text"], r["form"]
    if r["family"] == "arith8":
        return "overflow"
    if t.startswith(("ADC HL", "SBC HL")):
        return "overflow"
    if t.startswith(("AND", "XOR", "OR")) or t in ("RLD", "RRD", "DAA") or f == "IN r,(C)" \
            or (r["family"] == "rot" and r["key"][0] in (0xCB, 0xDD, 0xFD)):
        return "parity"
    if t in ("LDI", "LDD", "LDIR", "LDDR", "CPI", "CPD", "CPIR", "CPDR"):
        return "bc"
    if t in ("LD A,I", "LD A,R"):
        return "iff2"
    if t.startswith("BIT"):
        return "z"
    if t == "POP AF":
        return "popped"
    if t == "EX AF,AF'":
        return "swapped"
    return "other"


def result8(r, a):
    """the eight-bit result the instruction left, or None"""
    t = r["text"]
    # CP leaves no result, and neither do CPL (which "CP" also catches: it sets
    # neither S nor Z), SCF and CCF
    if r["family"] in ("arith8", "logic") and not t.startswith("CP") and t not in ("SCF", "CCF"):
        if t.startswith(("INC", "DEC")):
            return reg8(a, t.split(" ")[1])
        return a["af"] >> 8
    if t in ("RLD", "RRD"):
        return a["af"] >> 8
    if r["family"] == "rot" and r["key"][0] in (0xCB, 0xDD, 0xFD):
        return reg8(a, t.split(" ")[1])
    if r["form"] == "IN r,(C)":
        return reg8(a, t.split(" ")[1].split(",")[0])
    return None


def overflow(r, s, f):
    t, c = r["text"], f & 1
    if t.startswith(("ADC HL", "SBC HL")):
        x = signed(s["hl"], 16)
        y = {"BC": s["bc"], "DE": s["de"], "HL": s["hl"], "SP": s["sp"]}[t[-2:]]
        y = signed(y, 16)
        v = x + y + c if t.startswith("ADC") else x - y - c
        return not -32768 <= v <= 32767
    if t == "NEG":
        return s["a"] == 0x80
    if t.startswith("INC"):
        return reg8(s, t.split(" ")[1]) == 0x7F
    if t.startswith("DEC"):
        return reg8(s, t.split(" ")[1]) == 0x80
    x, y = signed(s["a"], 8), signed(operand(r, s), 8)
    c = c if t.startswith(("ADC", "SBC")) else 0
    v = x + y + c if t.startswith(("ADD", "ADC")) else x - y - c
    return not -128 <= v <= 127


def classify(runs):
    """each documented flag of one row, from all its runs: '-' unchanged,
    '0', '1', or '*' set by what the instruction did; P/V's '*' as 'V' or
    'P' where it is the overflow or the parity"""
    r = runs[0][0]
    out = {}
    for name, bit in FLAG_BITS:
        pairs = {((f >> bit) & 1, (a["af"] >> bit) & 1) for _, _, f, a in runs}
        if all(i == o for i, o in pairs):
            out[name] = "-"
        elif all(o == 1 for _, o in pairs):
            out[name] = "1"
        elif all(o == 0 for _, o in pairs):
            out[name] = "0"
        else:
            out[name] = "*"
    checked = {"sz": 0}
    for _, s, f, a in runs:
        F = a["af"] & 0xFF
        pv = F >> 2 & 1
        res = result8(r, a)
        if res is not None:                             # S and Z describe the result
            assert (F >> 7 & 1) == res >> 7 and (F >> 6 & 1) == (res == 0), (r["text"], s, a)
            checked["sz"] += 1
        if out["PV"] != "*":
            continue
        kind = pv_kind(r)
        if kind == "overflow" and r["text"] != "DAA":
            assert pv == overflow(r, s, f), (r["text"], s, hex(f), hex(a["af"]))
        elif kind == "parity" or r["text"] == "DAA":
            assert pv == parity(res), (r["text"], s, a)
        elif kind == "bc":
            assert pv == (a["bc"] != 0), (r["text"], s, a)
        elif kind == "iff2":
            assert pv == a["iff2"], (r["text"], s, a)
        elif kind == "z":
            assert pv == (F >> 6 & 1), (r["text"], s, a)
        elif kind == "popped":                          # the word on the stack's bit 2
            assert pv == (s["spw"] >> 2 & 1), (r["text"], s, a)
        elif kind == "swapped":                         # bit 2 of F prime
            assert pv == (s["af2"] >> 2 & 1), (r["text"], s, a)
    if out["PV"] == "*":
        kind = "parity" if r["text"] == "DAA" else pv_kind(r)
        out["pv"] = kind
        out["PV"] = {"overflow": "V", "parity": "P"}.get(kind, "*")
    out["runs"] = len(runs)
    out["sz_checked"] = checked["sz"]
    return out


def planned_runs():
    """[(row, state, F)] in the order flags.asm makes them"""
    gs = genA.groups()
    out = []
    for r, lab, pre, ins, grp in genA.flag_runs():
        for s in gs[grp]:
            for f in genA.FVALS:
                out.append((r, dict(s, pre=pre, ins=ins), f))
    return out


# ---------------------------------------------------------------- before
def key_of(b):
    """the prefixes and opcode of an instruction's bytes, as iset.py keys them"""
    if b[0] in (0xDD, 0xFD) and b[1] == 0xCB:
        return (b[0], 0xCB, b[3])
    if b[0] in (0xCB, 0xED, 0xDD, 0xFD):
        return (b[0], b[1])
    return (b[0],)


def before(res):
    """the times the chapters printed, against this appendix's"""
    rows = {r["key"]: r for r in iset.rows()}
    by_text = {r["text"].lower(): r["key"] for r in iset.rows()}
    t = json.loads(OUT_JSON.read_text())["times"]["rows"]

    def ours(key, what):
        r = rows[key]
        cs = t[str(r["n"])]
        if r["kind"] == "repeat":
            return cs[0]["t"][0] if what == "again" else cs[0]["t"][-1]
        if r["kind"] == "cond":
            return next(c["t"][0] for c in cs if c["what"] == ("taken" if what else "not"))
        return cs[0]["t"][0]

    out = {}
    load = lambda ch: json.loads((REPO / ch / f"meas{ch[2:]}.json").read_text())
    # chapter 14: every instruction that does not jump, the undocumented too
    same = other = 0
    for x in load("ch14")["all"]["rows"]:
        k = key_of(x["bytes"])
        if k not in rows:
            other += 1                                  # Appendix B's
            continue
        assert ours(k, None) == x["t"], (x, ours(k, None))
        same += 1
    out["ch14"] = {"same": same, "undocumented": other}
    # chapters 11 and 12: the jumps and the stack
    for ch in ("ch11", "ch12"):
        n = 0
        for x in load(ch)["cost"]["rows"]:
            k = key_of(x["bytes"])
            if k not in rows:
                continue
            assert ours(k, x.get("taken")) == x["t"], (ch, x, ours(k, x.get("taken")))
            n += 1
        out[ch] = n
    # chapter 13: the block instructions, by name, and NOP (the halves of IX
    # and IY that it timed too are Appendix B's)
    n = 0
    for x in load("ch13")["cost"]["rows"]:
        if x["instr"] not in by_text:
            assert "ix" in x["instr"], x
            continue
        k = by_text[x["instr"]]
        assert ours(k, "again" if x["again"] else "last") == x["t"], x
        n += 1
    out["ch13"] = n
    # chapter 17: the interrupt's answer in each mode
    modes = {m["mode"]: round(m["answer"]) for m in load("ch17")["modes"]["rows"]}
    for h in json.loads(OUT_JSON.read_text())["times"]["halts"]:
        assert modes[h["im"]] == h["answer"], (h, modes)
    out["ch17"] = {str(k): v for k, v in sorted(modes.items(), reverse=True)}
    res["before"] = out


# ---------------------------------------------------------------- bus
def bus(res):
    """each instruction alone on the model: the cycle each fetch, read,
    write and port access starts in, against the MSX's cycles"""
    def expected(cyc):
        out, at = [], 0
        for name, n in cyc:
            if name in ("M1", "MR", "MW", "IO", "INT"):
                out.append((name, at))
            at += n
        return out, at

    def machine(code):
        z = z80.Z80()
        z.m[0xC800:0xC800 + len(code)] = bytes(code)
        z.pc, z.sp = 0xC800, 0xE0F0
        z.m[0xE0F0], z.m[0xE0F1] = 0x00, 0xC9               # RET: back to $C900
        for k, v in genA.PTR.items():
            if k in ("ix", "iy"):
                setattr(z, k, v)
            else:
                getattr(z, f"set_{k}")(v)
        z.c = genA.IN_PORT                                  # a port the model reads
        z.log = []
        return z

    n = 0
    for r in iset.rows():
        key = list(r["key"])
        if len(key) == 3:
            code = [key[0], 0xCB, genA.D, key[2]]
        else:
            code = key + {"": [], "n": [genA.IN_PORT], "d": [genA.D], "d n": [genA.D, 0x5A],
                          "n n": [0x00, 0xC5], "e": [0x00]}[r["show"][len(" ".join(
                              f"{b:02X}" for b in key)):].strip()]
        if r["kind"] == "halt":
            ways = [(None, cyclesA.halt())]
        elif r["kind"] in ("cond", "repeat"):
            ways = [(True, cyclesA.of(key, True)), (False, cyclesA.of(key, False))]
        elif r["kind"] in ("jump", "block"):
            ways = [(True, cyclesA.of(key, True))]
        else:
            ways = [(None, cycles.of(code))]
        for taken, cyc in ways:
            z = machine(code)
            if r["kind"] == "cond":
                if r["cc"] == "B":
                    z.b = 2 if taken else 1
                else:
                    z.f = genA.TRUE_F[r["cc"]] ^ (0 if taken else 0xFF)
            if r["kind"] == "repeat":
                if key[1] & 3 >= 2:                         # INIR ... OTDR count with B
                    z.b = 2 if taken else 1
                else:
                    z.set_bc(2 if taken else 1)
                z.a = 0x99                                  # CPIR: not found
            z.step()
            want, total = expected(cyclesA.msx(cyc))
            assert z.log == want, (r["text"], taken, z.log, want)
            assert z.t == total, (r["text"], z.t, total)
            n += 1
    # the interrupt's answer, from HALT
    for im in (0, 1, 2):
        z = machine([0x76])
        z.im, z.i, z.iff1, z.iff2 = im, 0xC2, 1, 1
        z.step()
        z.log, t0 = [], z.t
        z.interrupt()
        want, total = expected(cyclesA.msx(cyclesA.answer(im)))
        assert [(k, t - t0) for k, t in z.log] == want and z.t - t0 == total, (im, z.log)
        n += 1
    res["bus"] = {"checked": n}


# ---------------------------------------------------------------- table
def table(res):
    """the appendix's rows: the measured times and fetches, Zilog's times,
    the cycles, and the flags, one row an instruction"""
    m = json.loads(OUT_JSON.read_text())
    tr, fr = m["times"]["rows"], m["flags"]["rows"]
    out = []
    one = lambda v: str(v[0]) if len(set(v)) == 1 else "/".join(str(x) for x in v)
    for r in iset.rows():
        n = str(r["n"])
        if r["kind"] == "halt":
            h = m["times"]["halts"]
            assert m["times"]["turn"] == 5 and {x["f"][0] for x in h} == {0x00, 0xFF}
            t, z, m1 = [5], [4], [1]
            cyc = [cyclesA.pattern(cyclesA.msx(cyclesA.halt()))]
            flags = dict.fromkeys("S Z H PV N C".split(), "-")
        else:
            cs = tr[n]
            if r["kind"] == "repeat":
                c = cs[-1]                                  # CPIR: the one that runs out
                t, z, m1, cyc = ([c["t"][0], c["t"][-1]], c["zilog"], [c["r"][0], c["r"][-1]],
                                 c["cycles"])
            else:
                t = [c["t"][0] for c in cs]
                z = [c["zilog"][0] for c in cs]
                m1 = [c["r"][0] for c in cs]
                cyc = [c["cycles"][0] for c in cs]
            if r["text"].startswith("RST"):
                assert sorted(c["f"][0] for c in cs) == [0x00, 0xFF]
                flags = dict.fromkeys("S Z H PV N C".split(), "-")
            else:
                f = fr[n]
                flags = {k: f[k] for k in ("S", "Z", "H", "PV", "N", "C")}
        out.append({"n": r["n"], "family": r["family"], "form": r["form"], "text": r["text"],
                    "show": r["show"], "key": list(r["key"]), "kind": r["kind"],
                    "t": one(t), "zilog": one(z), "m1": "2" if r["text"] == "LD R,A" else one(m1),
                    "cycles": one(cyc), "flags": flags, "pv": fr.get(n, {}).get("pv")})
    res["table"] = out


# ---------------------------------------------------------------- example
def example(res):
    """chapter 13's three copies and its OTIR, priced from the rows"""
    tab = json.loads(OUT_JSON.read_text())["table"]
    text = {}
    for r in tab:
        text.setdefault(r["text"], r)
    t = lambda name, k=0: int(text[name]["t"].split("/")[k])
    z = lambda name, k=0: int(text[name]["zilog"].split("/")[k])
    ch13 = json.loads((REPO / "ch13" / "meas13.json").read_text())
    out = {}
    for f, key in ((t, "msx"), (z, "zilog")):
        head = f("CALL nn") + 2 * f("LD HL,nn") + f("RET")
        loop = (head + f("LD B,n") + 256 * (f("LD A,(HL)") + f("LD (DE),A") + f("INC HL")
                                            + f("INC DE") + f("DJNZ e")) - f("DJNZ e") + f("DJNZ e", 1))
        ldir = head + f("LD BC,nn") + 255 * f("LDIR") + f("LDIR", 1)
        ldi = head + f("LD BC,nn") + 16 * (16 * f("LDI") + f("JP PE,nn"))
        otir = 255 * f("OTIR") + f("OTIR", 1)
        out[key] = {"loop": loop, "ldir": ldir, "ldi": ldi, "otir": otir,
                    "outi_jp": f("OUTI") + f("JP NZ,nn")}
    c = ch13["copy"]
    assert (out["msx"]["loop"], out["msx"]["ldir"], out["msx"]["ldi"]) == (c["loop"], c["ldir"],
                                                                         c["ldi"])
    assert out["msx"]["otir"] == ch13["otir"]["total"]
    assert ch13["otir"]["gap"] == t("OTIR") and ch13["otir"]["last"] == t("OTIR", 1)
    ch20 = json.loads((REPO / "ch20" / "meas20.json").read_text())["modes"]["MSXBOOK_EU16"]
    out["ch20"] = {"otir_lost": ch20["graphic1_23"], "outi_jp": 29}
    assert out["msx"]["outi_jp"] == 29 and t("OTIR") == 23
    res["example"] = out


# ---------------------------------------------------------------- openmsx
def openmsx(res):
    if not versions.builds():
        res["openmsx"] = {"skipped": "OPENMSX_BUILDS not set"}
        return
    res["openmsx"] = versions.every_build(["appA"], ["times", "flags"])


# ---------------------------------------------------------------- the main
STEPS = ["times", "flags", "before", "bus", "table", "example", "openmsx"]


def main(names=()):
    """the steps in order; each sees what the steps before it wrote"""
    res = json.loads(OUT_JSON.read_text()) if names and OUT_JSON.exists() else {}
    for name in STEPS:
        if names and name not in names:
            continue
        sub = {}
        globals()[name](sub)
        res[name] = sub[name]
        res = {k: res[k] for k in STEPS if k in res}
        OUT_JSON.write_text(json.dumps(res, indent=1) + "\n")
        print(" ", name, "ok", flush=True)
    return res


if __name__ == "__main__":
    main(sys.argv[1:])
