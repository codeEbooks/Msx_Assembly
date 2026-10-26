#!/usr/bin/env python3
"""measB.py -- the instructions the manual leaves out, timed and run, and
every instruction's bits 3 and 5 of F, and MEMPTR, on openMSX.

    python3 genB.py && ./build.sh && python3 measB.py [step ...]

    times    undoc.rom on MSXBOOK_EU16: the time, R, F and the word on top of
             the stack at every label (undoc.tcl). Each instruction's time
             and the fetches that R counts, against the cycles of the
             instruction it is a copy of, with one fetch more, 5 T-states on
             the MSX, for each prefix the manual does not have; and against
             Appendix A's times
    hidden   hidden_1.rom and hidden_2.rom (hidden.tcl, the same for both):
             after each run, at after or at away, every register, the bytes
             around, the PSG's register 0; and F after the BIT 0,(HL) that
             follows, whose bits 5 and 3 are MEMPTR's high byte's. The same
             cartridges run from INIT on hidden.py's model must give the
             same numbers. R at INIT and a digest of all openMSX's numbers
             go into measB.json, for another build to match
    copies   each copy against the instruction it copies, run for run: the
             same numbers, but R
    rules    where bits 5 and 3 of F come from, instruction by instruction,
             checked on every run; the same for MEMPTR, through the BIT
             after each run, and against the model's MEMPTR; told counts
             the runs in which the BIT's two bits differ from those MEMPTR
             had before the instruction
    before   the times chapters 13 and 14 printed of these instructions,
             against this appendix's
    bus      each of isetB.py's instructions alone on the model: every
             fetch, read, write and port cycle starts where its cycles put it
    table    the appendix's rows
    openmsx  times and hidden again with every other build (tools/versions.py)

Writes measB.json.
"""
import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
for d in ("tools", "ch14", "appA"):
    sys.path.insert(0, str(REPO / d))
sys.path.insert(0, str(HERE))
import msxcap      # noqa: E402
import probe       # noqa: E402
import versions    # noqa: E402
import cycles      # noqa: E402
import cyclesA     # noqa: E402
import iset        # noqa: E402
import isetB       # noqa: E402
import genA        # noqa: E402
import genB        # noqa: E402
import z80         # noqa: E402
import hidden as hm  # noqa: E402
from cycles import M1, IO  # noqa: E402

T = lambda a, b: round((b - a) * probe.CLOCK)
OUT_JSON = HERE / "measB.json"
LOG = '[machine_info time] [reg r] [reg af] [peek16 [reg sp]]'


# ---------------------------------------------------------------- times
def predicted(r, taken=True):
    """Zilog's cycles of B's row r: those of the instruction it runs as, and
    an opcode fetch for each prefix more"""
    k, g, t = list(r["key"]), r["group"], r["text"]
    if g in ("sll", "xcb"):
        code = [k[0], 0xCB, genB.D, k[2]] if len(k) == 3 else k
        return cycles.of(code)
    if g == "half":
        return cycles.of(k)
    if g == "ed":
        if r["twin"]:
            tw = r["twin"]
            return cycles.ED[tw[1]] if tw[1] in cycles.ED else cyclesA.of(tw, taken)
        if t in ("IN F,(C)", "OUT (C),0"):
            return [M1, M1, IO]
        return [M1, M1]                                 # IM ? and ED NOP
    base = genB.like(r)                                 # prefix, chain
    rest = k[1:]
    if base["kind"] == "plain":
        return [M1] + cycles.of(rest + [0, 0])
    return [M1] + cyclesA.of(tuple(rest), taken)


def times_tcl(s, cs):
    out = ["# undoc.tcl - written by measB.py: openMSX's breakpoints for undoc.rom",
           f'proc B {{name}} {{ L "B $name {LOG}" }}']
    for c, (r, what, setup, rst) in enumerate(cs, start=1):
        out.append(f'debug set_bp 0x{s[f"t{c}"]:04X} {{}} {{B t{c}}}')
        if rst is None:
            out.append(f'debug set_bp 0x{s[f"e{c}"]:04X} {{}} {{B e{c}}}')
    out.append("# an RST lands in the BIOS: back to e, the address it pushed")
    for q in range(0, 64, 8):
        out.append(f'debug set_bp 0x{q:04X} {{[reg sp] == 0x{genA.RSTK - 2:04X}}} '
                   f'{{B rst{q:02X}; reg pc [peek16 [reg sp]]}}')
    out.append(f'debug set_bp 0x{s["done"]:04X} {{}} {{B done; L done; exit}}')
    return "\n".join(out) + "\n"


def times(res):
    s = probe.sym(HERE / "undoc.sym")
    cs = genB.cases()
    tcl = times_tcl(s, cs)
    (HERE / "undoc.tcl").write_text(tcl)
    lines = msxcap.run_tcl(HERE / "undoc.rom", 600, tcl)
    marks = []
    for l in lines:
        if l.startswith("B "):
            _, name, t, r, af, w = l.split()
            marks.append((name, float(t), int(r), int(af), int(w)))
    rom = (HERE / "undoc.rom").read_bytes()
    k = 0

    def take(name):
        nonlocal k
        m = marks[k]
        assert m[0] == name, (m, name, k)
        k += 1
        return m

    rows = {r["n"]: r for r in isetB.rows()}
    by_row, ed_nop = {}, {}
    for c, (r, what, setup, rst) in enumerate(cs, start=1):
        a = take(f"t{c}")
        e = take(f"rst{rst:02X}" if rst is not None else f"e{c}")
        b = list(rom[s[f"t{c}"] - 0x4000:s[f"e{c}"] - 0x4000])
        key = list(r["key"])
        if len(key) == 3 and key[1] == 0xCB:
            assert b[:2] == key[:2] and b[3] == key[2] and b[2] == genB.D, (r["text"], b)
        else:
            assert b[:len(key)] == key, (r["text"], b, key)
        z = predicted(rows[r["n"]], what != "not")
        m = cyclesA.msx(z)
        t, dr = T(a[1], e[1]), (e[2] - a[2]) % 128
        assert dr == cyclesA.fetches(m), (r["text"], what, dr)
        if r["text"] == "ED NOP":
            # openMSX charges ED and a code after it that is no instruction
            # one fetch's time, 5 T-states, though R counts both fetches:
            # the cycles say 4,4, 5,5 on the MSX
            assert t == 5 and cyclesA.tstates(m) == 10, (r["show"], t)
            ed_nop[r["show"]] = t
        else:
            assert t == cyclesA.tstates(m), (r["text"], what, t, m)
        if genB.text_of(r).startswith("RST"):
            assert a[3] & 255 == e[3] & 255 == int(what[1:], 16) and e[4] == s[f"e{c}"]
        by_row.setdefault(str(r["n"]), []).append({
            "what": what, "t": t, "r": dr, "zilog": cyclesA.tstates(z),
            "cycles": cyclesA.pattern(m)})
    take("done")
    assert all(m[0] == "done" for m in marks[k:])
    # each prefix the manual does not have costs one fetch, 5 T-states
    doc = json.loads((REPO / "appA" / "measA.json").read_text())["times"]["rows"]
    more = {}
    for r in isetB.rows():
        b = genB.like(r)
        if r["group"] not in ("prefix", "chain") and not (r["group"] == "ed" and b):
            continue
        extra = len(r["key"]) - len(b["key"])
        for x in by_row[str(r["n"])]:
            y = next(y for y in doc[str(b["n"])] if y["what"] == x["what"])
            assert (x["t"] - y["t"][0], x["r"] - y["r"][0]) == (5 * extra, extra), (r, x, y)
            more[str(extra)] = more.get(str(extra), 0) + 1
    assert len(ed_nop) == 178
    res["times"] = {"cases": len(cs), "rows": by_row, "against_A": more,
                    "ed_nop": {"count": len(ed_nop), "t": 5, "r": 2, "cycles": 10}}


# ---------------------------------------------------------------- hidden
NAMES = ["af", "bc", "de", "hl", "ix", "iy", "sp", "i", "r", "iff1", "iff2", "im", "af2",
         "bc2", "de2", "hl2", "win0", "win4", "stk", "psg", "away", "probe"]


def hidden_tcl(s):
    after, away = s["after"], s["away"]
    regs = ('[reg af] [reg bc] [reg de] [reg hl] [reg ix] [reg iy] [reg sp] [reg i] [reg r] '
            '[reg iff] [reg im] [reg af2] [reg bc2] [reg de2] [reg hl2] '
            f'[H 0x{genA.WIN:04X} 8] [H 0x{genA.STK - 2:04X} 4] [debug read {{PSG regs}} 0]')
    return "\n".join([
        "# hidden.tcl - written by measB.py: openMSX's breakpoints for hidden_1.rom and",
        "# hidden_2.rom: at after and away every register, the bytes at WIN and around",
        "# STK, the PSG's register 0; after the BIT 0,(HL) that follows, F",
        'proc H {a n} { binary scan [debug read_block memory $a $n] H* h; return $h }',
        'L "I [reg r] [debug read ioports 0xA8]"',
        f'debug set_bp 0x{after:04X} {{}} {{L "A 0 {regs}"}}',
        f'debug set_bp 0x{away:04X} {{}} {{L "A 1 {regs}"}}',
        f'debug set_bp 0x{after + 2:04X} {{}} {{L "P [reg af]"}}',
        f'debug set_bp 0x{away + 2:04X} {{}} {{L "P [reg af]"}}',
        f'debug set_bp 0x{s["done"]:04X} {{}} {{L done; exit}}']) + "\n"


def le32(h):
    return int.from_bytes(bytes.fromhex(h), "little")


def emu_part(p):
    s = probe.sym(HERE / f"hidden_{p}.sym")
    tcl = hidden_tcl(s)
    if p == 1:
        (HERE / "hidden.tcl").write_text(tcl)
    assert tcl == (HERE / "hidden.tcl").read_text()     # the same for both parts
    lines = msxcap.run_tcl(HERE / f"hidden_{p}.rom", 6000, tcl, timeout=3000)
    init = next(l for l in lines if l.startswith("I ")).split()
    out, cur = [], None
    for l in lines:
        if l.startswith("A "):
            v = l.split()[1:]
            away = int(v[0])
            af, bc, de, hl, ix, iy, sp, i, r, iff, im, af2, bc2, de2, hl2 = (int(x) for x in v[1:16])
            cur = [af, bc, de, hl, ix, iy, sp, i, r, iff & 1, iff >> 1 & 1, im, af2, bc2, de2,
                   hl2, le32(v[16][:8]), le32(v[16][8:]), le32(v[17]), int(v[18]), away]
        elif l.startswith("P "):
            out.append(cur + [int(l.split()[1]) & 0x28])
            cur = None
    return s, {"r": int(init[1]), "a8": int(init[2])}, out


def model_part(p, s, init):
    """hidden_P.rom on hidden.py's model, from INIT with openMSX's R: the
    numbers at the same places, and MEMPTR after each instruction"""
    rom = (HERE / f"hidden_{p}.rom").read_bytes()
    z = hm.Hidden(rom, z80.Ports(init["a8"]))
    z.pc = rom[2] | rom[3] << 8
    z.r = init["r"]
    m = z.m
    rd16 = lambda a: m[a] | m[a + 1] << 8
    rd32 = lambda a: rd16(a) | rd16(a + 2) << 16
    after, away, done = s["after"], s["away"], s["done"]
    out, mps, cur = [], [], None
    while z.pc != done:
        if z.pc in (after, away):
            cur = [z.af, z.bc, z.de, z.hl, z.ix, z.iy, z.sp, z.i, z.r, z.iff1, z.iff2, z.im,
                   z.a_ << 8 | z.f_, z.b_ << 8 | z.c_, z.d_ << 8 | z.e_, z.h_ << 8 | z.l_,
                   rd32(genA.WIN), rd32(genA.WIN + 4), rd32(genA.STK - 2), z.ports.psg[0],
                   int(z.pc == away)]
            mps.append(z.memptr)
        elif z.pc in (after + 2, away + 2):
            out.append(cur + [z.f & 0x28])
        z.step()
    return out, mps


def planned():
    """[(source, row, block, state, F)] in the order the cartridges make
    them, part by part"""
    gs = genB.groups()
    out = []
    for part in genB.parts():
        p = []
        for src, r, lab, pre, ins, grp in part:
            for s in gs[grp]:
                for f in genA.FVALS:
                    p.append((src, r, lab, dict(s, pre=pre, ins=ins, grp=grp), f))
        out.append(p)
    return out


def run_all(info=None):
    """[(source, row, block, state, F, {name: value}, MEMPTR by the model, part)];
    in INFO, if given, each part's R and port $A8 at INIT, and a digest of
    every number openMSX gave, so that another build is held to the same"""
    plan = planned()
    runs, differ, values = [], {}, 0
    for p in range(1, genB.PARTS + 1):
        s, init, emu = emu_part(p)
        if info is not None:
            info.append(dict(init, sha256=hashlib.sha256(json.dumps(emu).encode()).hexdigest()))
        model, mps = model_part(p, s, init)
        assert len(emu) == len(model) == len(plan[p - 1]), (p, len(emu), len(model))
        for x, a, b, mp in zip(plan[p - 1], emu, model, mps):
            for name, u, v in zip(NAMES, a, b):
                values += 1
                if u != v:
                    key = f"{x[0]} {x[1]['text']} {name}"
                    differ[key] = differ.get(key, 0) + 1
            runs.append(x + (dict(zip(NAMES, a)), mp, p))
    return runs, differ, values


def hidden(res):
    info = []
    runs, differ, values = run_all(info)
    for k, v in sorted(differ.items())[:60]:
        print("  differs:", k, v)
    assert not differ, len(differ)
    res["hidden"] = {"runs": len(runs), "values": values, "blocks": len(genB.runs()),
                     "parts": [len(p) for p in planned()],
                     "names": len(NAMES), "init": info}


# ---------------------------------------------------------------- runs, as the steps read them
class Runs:
    """the cartridges' runs as openMSX gave them (the model agrees), with
    what each needs: by row, each run's MEMPTR before the instruction"""

    def __init__(self):
        self.all, differ, _ = run_all()
        assert not differ
        self.by = {}
        for x in self.all:
            self.by.setdefault((x[0], x[1]["n"]), []).append(x)
        self.doc = {r["key"]: r for r in iset.rows()}
        self.syms = {p: probe.sym(HERE / f"hidden_{p}.sym") for p in range(1, genB.PARTS + 1)}
        self.away = self.syms[1]["away"]

    def of(self, src, r):
        return self.by[(src, r["n"])]

    def here(self, x):
        """the instruction's address in buf: its label inside the block"""
        return self.syms[x[7]][f"i{x[2][1:]}"]

    def mp_before(self, x):
        """MEMPTR before the instruction: nn + 1 after LD (nn),SP, in the
        block or in base before it"""
        pre = x[3]["pre"]
        if pre and pre[0].startswith("ld ($"):
            return int(pre[0][5:9], 16) + 1
        return genB.BASE + 1

    def before(self, x, reg):
        v = x[3][reg] if reg != "a" else x[3]["a"]
        for p in x[3]["pre"]:
            if p.startswith(f"ld {reg},$"):
                v = int(p.split("$")[1], 16)
        return v

    def nn(self, x):
        return genB.CARRY if f"(${genB.CARRY:04x})" in x[3]["ins"].lower() else genA.M

    def ixd(self, x):
        s, ins = x[3], x[3]["ins"].lower()
        reg = "iy" if "(iy" in ins or ins.startswith("db $fd") else "ix"
        base = s[reg]
        for p in s["pre"]:
            if p.startswith(f"ld {reg},$"):
                base = int(p.split("$")[1], 16)
        d = -genB.D if f"{reg}-{genB.D})" in ins or f",-{genB.D}," in ins else genB.D
        return (base + d) & 0xFFFF


def mem_after(a, at):
    """the byte at AT, WIN to WIN+7, after a run"""
    return (a["win0"] | a["win4"] << 32) >> 8 * (at - genA.WIN) & 0xFF


REG = {"A": ("af", 8), "B": ("bc", 8), "C": ("bc", 0), "D": ("de", 8), "E": ("de", 0),
       "H": ("hl", 8), "L": ("hl", 0), "IXH": ("ix", 8), "IXL": ("ix", 0), "IYH": ("iy", 8),
       "IYL": ("iy", 0)}


def reg(state, name, after=True):
    if name.startswith("("):
        return mem_after(state, genA.M) if after else state["win"][4]
    pair, shift = REG[name]
    if not after and pair == "af":
        return state["a"]
    return state[pair] >> shift & 0xFF


# ---------------------------------------------------------------- copies
def copies(res, R=None):
    R = R or Runs()
    out = {"runs": {}}

    def count(g, n):
        out["runs"][g] = out["runs"].get(g, 0) + n

    def same(x, y, but=()):
        """the same numbers after X as after Y, but BUT; the word below
        STK only where the instruction pushes"""
        a, b = x[5], y[5]
        pushes = a["sp"] == x[3]["sp"] - 2 and genB.text_of(x[1]).startswith(("PUSH", "CALL"))
        if not pushes and (a["stk"] ^ b["stk"]) >> 16:
            return False
        return all(a[k] == b[k] for k in NAMES if k not in but + (() if pushes else ("stk",)))

    for r in isetB.rows():
        if genB.text_of(r).startswith("RST"):
            continue
        ours = R.of("B", r)
        g, t = r["group"], r["text"]
        tw = genB.like(r) if g != "half" else None
        if g == "xcb" and tw is None:                   # SLL (IX+d),r: as SLL (IX+d)
            tw = next(b for b in isetB.rows() if b["key"] == (r["key"][0], 0xCB, 0x36))
            theirs = R.of("B", tw)
        elif tw is not None:
            theirs = R.of("A", tw)
        if tw is not None:
            assert len(ours) == len(theirs), t
            for x, y in zip(ours, theirs):
                a, b = x[5], y[5]
                if g == "xcb" and not tw["text"].startswith("BIT"):
                    # the result into the register as well as into memory
                    name = "BCDEHL.A"[r["key"][2] & 7]
                    assert reg(a, name) == mem_after(a, genA.M) == mem_after(b, genA.M), t
                    pair = REG[name][0]
                    assert same(x, y, ("r", pair)), t
                    other = 0xFF00 if REG[name][1] == 0 else 0x00FF
                    assert a[pair] & other == b[pair] & other, t
                else:
                    assert same(x, y, ("r",)), (t, x[3]["pre"], a, b)
            count(g, len(ours))
            continue
        if g == "ed" and t in ("ED NOP", "IM ?"):
            if t == "IM ?":
                # the mode each puts the processor in, whichever it was in
                # before: 1, as the program sets it, 0 or 1 after IM 0 or IM 1
                ims = {x[5]["im"] for x in ours}
                assert len(ims) == 1 and {tuple(x[3]["pre"]) for x in ours} == {
                    (), ("im 0",), ("im 1",)}
                out.setdefault("modes", {})[f"{r['key'][1]:02X}"] = ims.pop()
                count("im", len(ours))
                ours = [x for x in ours if not x[3]["pre"]]
            nop = R.of("A", R.doc[(0x00,)])
            assert len(ours) == len(nop)
            for x, y in zip(ours, nop):
                assert same(x, y, ("r",) + (("im",) if t == "IM ?" else ())), t
            if t == "ED NOP":
                count("ed_nop", len(ours))
        elif t == "IN F,(C)":
            ina = R.of("A", R.doc[(0xED, 0x78)])
            assert len(ours) == len(ina)
            for x, y in zip(ours, ina):
                assert x[5]["af"] & 0xFF == y[5]["af"] & 0xFF and x[5]["af"] >> 8 == x[3]["a"]
                assert same(x, y, ("af", "r"))
            count("in_f", len(ours))
        elif t == "OUT (C),0":
            # to the PSG's port $A1, 0, whatever B and the byte before
            psg = [x for x in ours if R.before(x, "bc") & 0xFF == genB.OUT0_PORT]
            assert all(x[5]["psg"] == 0 and x[3]["psg"] == 0x5A for x in psg)
            assert {R.before(x, "bc") >> 8 for x in psg} == {0x00, 0x12}
            count("out_0", len(psg))
        elif g == "sll":
            k = r["key"]
            sla = R.doc[(k[0], 0xCB, 0x26)] if len(k) == 3 else R.doc[(0xCB, k[1] - 0x10)]
            assert len(ours) == len(R.of("A", sla))
            for x, y in zip(ours, R.of("A", sla)):
                name = t.split(" ")[1].split(",")[0]
                name = "(HL)" if name.startswith("(") else name
                v, w = reg(x[5], name), reg(y[5], name)
                assert v == w | 1 and x[5]["af"] & 1 == y[5]["af"] & 1, t
                assert x[5]["af"] & 0xFE == z80.SZP[v] & 0xFE, t
            count("sll", len(ours))
        elif g == "half":
            if t.startswith("LD"):           # the loads: what they move
                for x in ours:
                    dst, src = t[3:].split(",")
                    want = genA.N if src == "n" else reg(x[3], src, after=False)
                    assert reg(x[5], dst) == want, t
            else:
                # ADD A,IXH ... DEC IXL: as ADD A,H ... DEC L, whose states
                # hold the same numbers in H and L
                mine = next(b for b in iset.rows() if b["text"] == re.sub(r"I[XY]([HL])",
                                                                            r"\1", t))
                assert len(ours) == len(R.of("A", mine))
                for x, y in zip(ours, R.of("A", mine)):
                    assert x[5]["af"] == y[5]["af"], t
                    if t.startswith(("INC", "DEC")):
                        nm = t.split(" ")[1]
                        assert reg(x[5], nm) == reg(y[5], nm[-1]), t
            count("half", len(ours))
        else:
            raise ValueError(t)
    res["copies"] = out


# ---------------------------------------------------------------- rules
def effective(r):
    """the text whose rules a row follows: a copy's, its documented
    instruction's; SLL (IX+d),r's, SLL (IX+d)'s; the others their own"""
    if "group" not in r:
        return r["text"]
    if r["group"] == "xcb" and r["twin"] is None:
        return r["text"].split("),")[0] + ")"
    return genB.text_of(r)


ALU_A = ("ADD", "ADC", "SUB", "SBC", "AND", "XOR", "OR")
ROTS = ("RLC", "RRC", "RL ", "RR ", "SLA", "SRA", "SLL", "SRL")


def rule35(t):
    """where bits 3 and 5 of F come from, after the instruction T"""
    if t in ("POP AF", "EX AF,AF'"):
        return "loaded"
    if t in ("SCF", "CCF"):
        return "F OR A"
    if t.startswith("CP ") and t not in ("CPI", "CPD", "CPIR", "CPDR"):
        return "operand"
    if t.startswith(ALU_A) and not t.startswith(("ADD HL", "ADD IX", "ADD IY", "ADC HL",
                                                 "SBC HL")):
        return "A"
    if t in ("NEG", "DAA", "CPL", "RLCA", "RRCA", "RLA", "RRA", "RLD", "RRD", "LD A,I",
             "LD A,R"):
        return "A"
    if t.startswith(("INC ", "DEC ")) and not re.match(r"(INC|DEC) (BC|DE|HL|SP|IX|IY)$", t):
        return "result"
    if t.startswith(ROTS) or re.match(r"IN [A-EHLF],\(C\)", t):
        return "result"
    if t.startswith(("ADD HL", "ADD IX", "ADD IY", "ADC HL", "SBC HL")):
        return "high"
    if t.startswith("BIT"):
        return "MEMPTR" if "(" in t else "tested"
    if t in ("LDI", "LDD", "LDIR", "LDDR"):
        return "A+n"
    if t in ("CPI", "CPD", "CPIR", "CPDR"):
        return "A-n-H"
    if t in ("INI", "IND", "INIR", "INDR", "OUTI", "OUTD", "OTIR", "OTDR"):
        return "B"
    return "kept"


def operand_of(t, s):
    src = t[3:]
    if src == "n":
        return int(s["ins"].split("$")[-1], 16)
    return reg(s, "(HL)" if src.startswith("(") else src, after=False)


def port_byte(s, bc):
    """what IN reads from port BC in state S: port $A2 the PSG's register 0,
    as the state set it; the others nothing answers, $FF"""
    return s["psg"] if bc & 0xFF == genA.IN_PORT else 0xFF


def f_before(s, f):
    """F before the instruction: the run's, or CP $28's after it"""
    if s["pre"] == ["cp $28"]:
        z = z80.Z80()
        z.a, z.f = s["a"], f
        z.alu(7, 0x28)
        return z.f
    return f


def want35(t, rule, x, R):
    """bits 3 and 5 after run X, as RULE says"""
    src, r, blk, s, f, a, mp, p = x
    f0 = f_before(s, f)
    A = a["af"] >> 8
    if rule == "kept":
        v = f0
    elif rule == "loaded":
        v = s["spw"] if t == "POP AF" else s["af2"]
    elif rule == "F OR A":
        v = f0 | R.before(x, "a")
    elif rule == "operand":
        v = operand_of(t, s)
    elif rule == "A":
        v = A
    elif rule == "result":
        if t.startswith("IN ") and t != "IN F,(C)":
            v = reg(a, t[3])
        elif t == "IN F,(C)":
            v = port_byte(s, R.before(x, "bc"))
        else:
            name = t.split(" ")[1].split(",")[0]
            v = reg(a, "(HL)" if name.startswith("(") else name)
    elif rule == "high":
        v = a[t.split(" ")[1][:2].lower()] >> 8
    elif rule == "tested":
        v = reg(a, t.split(",")[1])
    elif rule == "MEMPTR":
        v = want_mp(t, "IX+d" if "(I" in t else "kept", x, R) >> 8
    elif rule == "A+n":
        step = 1 if t in ("LDI", "LDIR") else -1
        n = (A + mem_after(a, (a["de"] - step) & 0xFFFF)) & 0xFF
        v = (n & 0x08) | (n & 0x02) << 4
    elif rule == "A-n-H":
        step = 1 if t in ("CPI", "CPIR") else -1
        byte = s["win"][((a["hl"] - step) & 0xFFFF) - genA.WIN]
        n = (A - byte - (a["af"] >> 4 & 1)) & 0xFF
        v = (n & 0x08) | (n & 0x02) << 4
    elif rule == "B":
        v = a["bc"] >> 8
    return v & 0x28


def rule_mp(t):
    """what MEMPTR holds after the instruction T"""
    if "(IX+d)" in t or "(IY+d)" in t:
        return "IX+d"
    table = {"LD A,(BC)": "BC+1", "LD A,(DE)": "DE+1", "LD A,(nn)": "nn+1",
             "LD (BC),A": "A, BC+1", "LD (DE),A": "A, DE+1", "LD (nn),A": "A, nn+1",
             "RLD": "HL+1", "RRD": "HL+1", "IN A,(n)": "A n+1", "OUT (n),A": "A, n+1",
             "JP nn": "nn", "CALL nn": "nn", "JR e": "went", "RET": "went", "RETI": "went",
             "RETN": "went", "DJNZ e": "went if", "CPI": "MEMPTR+1", "CPD": "MEMPTR-1",
             "CPIR": "MEMPTR+1", "CPDR": "MEMPTR-1", "LDIR": "here+1", "LDDR": "here+1",
             "INI": "BC+1 B before", "INIR": "BC+1 B before", "IND": "BC-1 B before",
             "INDR": "BC-1 B before", "OUTI": "BC+1 B after", "OTIR": "BC+1 B after",
             "OUTD": "BC-1 B after", "OTDR": "BC-1 B after",
             "IN F,(C)": "BC+1", "OUT (C),0": "BC+1"}
    if t in table:
        return table[t]
    if re.match(r"LD (HL|IX|IY|BC|DE|SP),\(nn\)$|LD \(nn\),(HL|IX|IY|BC|DE|SP)$", t):
        return "nn+1"
    if re.match(r"(ADD|ADC|SBC) (HL|IX|IY),", t):
        return t.split(" ")[1][:2] + "+1"
    if t.startswith("EX (SP),"):
        return t[8:] + " after"
    if re.match(r"(JP|CALL) [A-Z]+,nn", t):
        return "nn"
    if re.match(r"(JR [A-Z]+,e|RET [A-Z]+)$", t):
        return "went if"
    if re.match(r"(IN [A-EHL],\(C\)|OUT \(C\),[A-EHL])$", t):
        return "BC+1"
    return "kept"


def repeats(t, s):
    """how many times a block instruction runs in state S"""
    if not t.endswith("R"):
        return 1
    bc, k = s["bc"], 0
    hl = s["hl"]
    step = 1 if t in ("LDIR", "CPIR") else -1
    while True:
        k += 1
        bc = (bc - 1) & 0xFFFF
        if t.startswith("CP"):
            if s["win"][hl - genA.WIN] == s["a"] or bc == 0:
                return k
            hl += step
        elif bc == 0:
            return k


def want_mp(t, rule, x, R):
    """MEMPTR after run X, as RULE says"""
    src, r, blk, s, f, a, mp, p = x
    mp0, here = R.mp_before(x), R.here(x)
    A = R.before(x, "a")
    if rule == "kept":
        return mp0
    if rule in ("nn+1", "A, nn+1"):
        v = (R.nn(x) + 1) & 0xFFFF
        return v if rule == "nn+1" else A << 8 | v & 0xFF
    if rule in ("BC+1", "DE+1", "HL+1", "IX+1", "IY+1"):
        return (R.before(x, rule[:2].lower()) + 1) & 0xFFFF
    if rule.endswith(("B before", "B after")):
        b = a["bc"] >> 8
        b = (b + 1) & 0xFF if rule.endswith("before") else b
        return ((b << 8 | a["bc"] & 0xFF) + (1 if rule[2] == "+" else -1)) & 0xFFFF
    if rule in ("A, BC+1", "A, DE+1"):
        return A << 8 | (R.before(x, rule[3:5].lower()) + 1) & 0xFF
    if rule == "IX+d":
        return R.ixd(x)
    if rule.endswith(" after"):
        return a[rule[:2].lower()]
    if rule == "nn":
        return R.away
    if rule == "went":
        assert a["away"]
        return R.away
    if rule == "went if":
        return R.away if a["away"] else mp0
    n = 0xFF if "$ff)" in s["ins"].lower() else (
        genA.IN_PORT if rule == "A n+1" else genA.OUT_PORT)
    if rule == "A n+1":
        return ((A << 8 | n) + 1) & 0xFFFF
    if rule == "A, n+1":
        return A << 8 | (n + 1) & 0xFF
    if rule in ("MEMPTR+1", "MEMPTR-1", "here+1"):
        # the repeating ones: here + 1 while going round, then as the
        # one-turn instruction from there
        turns = repeats(t, s)
        step = {"MEMPTR+1": 1, "MEMPTR-1": -1, "here+1": 0}[rule]
        start = mp0 if turns == 1 else (here + 1) & 0xFFFF
        return (start + step) & 0xFFFF if rule != "here+1" else (mp0 if turns == 1 else start)
    raise ValueError(rule)


def rules(res, R=None):
    R = R or Runs()
    out35, outmp = {}, {}
    rows = [("A", r) for r in iset.rows()] + [("B", r) for r in isetB.rows()]
    base_bits = (genB.BASE + 1) >> 8 & 0x28
    for src, r in rows:
        if (src, r["n"]) not in R.by:
            continue                                    # HALT and the RSTs
        xs = R.by[(src, r["n"])]
        t = effective(r)
        k35, kmp = rule35(t), rule_mp(t)
        told = 0
        for x in xs:
            a = x[5]
            got = a["af"] & 0x28
            assert got == want35(t, k35, x, R), (r["text"], k35, x[3], x[4], a)
            w = want_mp(t, kmp, x, R)
            assert x[6] == w, (r["text"], kmp, hex(x[6]), hex(w), x[3])      # the model's
            assert a["probe"] == w >> 8 & 0x28, (r["text"], kmp, x[3], a)  # openMSX's two bits
            told += (w >> 8 & 0x28) != (R.mp_before(x) >> 8 & 0x28)
        changed = sum(1 for x in xs if want35(t, "kept", x, R) != x[5]["af"] & 0x28)
        e = out35.setdefault(k35, {"rows": 0, "runs": 0, "changed": 0, "texts": []})
        e["rows"] += 1
        e["runs"] += len(xs)
        e["changed"] += changed
        e["texts"].append(r["text"])
        e = outmp.setdefault(kmp, {"rows": 0, "runs": 0, "told": 0, "texts": [], "untold": []})
        e["rows"] += 1
        e["runs"] += len(xs)
        e["told"] += told
        e["texts"].append(r["text"])
        if not told and kmp != "kept":
            e["untold"].append(r["text"])               # the BIT cannot tell its rule
    assert base_bits == 0
    res["rules"] = {"bits35": out35, "memptr": outmp, "io": io_flags(R), "bit_hl": bit_hl(R),
                    "bit_ixd": bit_ixd(R), "scf": scf(R), "port_ff": port_ff(R),
                    "runs": len(R.all), "base": genB.BASE + 1}


def bit_hl(R):
    """BIT b,(HL)'s runs, by what came before it: MEMPTR, bits 5 and 3, the
    bytes tested, and how many runs"""
    out = {}
    for r in iset.rows():
        if r["form"] != "BIT b,(HL)":
            continue
        for x in R.of("A", r):
            pre = x[3]["pre"][0][4:9] if x[3]["pre"] else "base"
            e = out.setdefault(pre, {"memptr": set(), "bits": set(), "bytes": set(), "runs": 0})
            e["memptr"].add(x[6])
            e["bits"].add(x[5]["af"] & 0x28)
            e["bytes"].add(x[3]["win"][4])
            e["runs"] += 1
    for e in out.values():
        for k in ("memptr", "bits", "bytes"):
            e[k] = sorted(e[k])
        assert len(e["memptr"]) == len(e["bits"]) == 1
        assert e["bits"][0] == e["memptr"][0] >> 8 & 0x28
    return out


def bit_ixd(R):
    """BIT b,(IX+d) and BIT b,(IY+d), the manual's and their copies, by what
    came before: IX+d, its high byte's bits 5 and 3, IXH's, and F's"""
    out = {}
    for src, rs in (("A", iset.rows()), ("B", isetB.rows())):
        for r in rs:
            t = r["text"]
            if not (t.startswith("BIT") and ("(IX+d)" in t or "(IY+d)" in t)):
                continue
            for x in R.of(src, r):
                pre = x[3]["pre"][0][7:] if x[3]["pre"] else "base"
                rg = "iy" if "(IY+d)" in t else "ix"
                at = R.ixd(x)
                e = out.setdefault(pre, {"at": set(), "high": set(), "half": set(),
                                         "bits": set(), "runs": 0})
                e["at"].add(at)
                e["high"].add(at >> 8 & 0x28)
                e["half"].add(x[5][rg] >> 8 & 0x28)
                e["bits"].add(x[5]["af"] & 0x28)
                e["runs"] += 1
    for e in out.values():
        for k in ("at", "high", "half", "bits"):
            e[k] = sorted(e[k])
        assert e["bits"] == e["high"]
    return out


def port_ff(R):
    """IN A,(n) and OUT (n),A with n $FF: A before, MEMPTR, and the two bits
    the BIT after them found"""
    out = {}
    for src, rs in (("A", iset.rows()), ("B", isetB.rows())):
        for r in rs:
            t = genB.text_of(r) if src == "B" else r["text"]
            if t not in ("IN A,(n)", "OUT (n),A"):
                continue
            for x in R.of(src, r):
                if "$ff)" not in x[3]["ins"].lower():
                    continue
                out.setdefault(t, set()).add((R.before(x, "a"), x[6], x[5]["probe"]))
    return {k: sorted(v) for k, v in out.items()}


def scf(R):
    """SCF's and CCF's runs: after base's LD (nn),SP or after CP $28; A and F
    as they went in, and bits 5 and 3 after: openMSX's rule is (F OR A) both
    times, where a Zilog's is A's alone after CP (chapter 55)"""
    out = {}
    for t in ("SCF", "CCF"):
        r = next(r for r in iset.rows() if r["text"] == t)
        for x in R.of("A", r):
            s, f, a = x[3], x[4], x[5]
            key = f"{t} {'cp' if s['pre'] else 'base'} {s['a']:02X} {f:02X}"
            out.setdefault(key, set()).add(a["af"] & 0x28)
    assert all(len(v) == 1 for v in out.values())
    return {k: v.pop() for k, v in out.items()}


def io_flags(R):
    """INI to OTDR: S, Z, 5 and 3 from B after, N from bit 7 of the byte v
    moved, H and C set when k = v + (C + 1), v + (C - 1) or, for OUTI and
    its kind, v + L after, passes 255, P/V the parity of (k AND 7) XOR B"""
    n = 0
    for r in iset.rows():
        t = r["text"]
        if t not in ("INI", "IND", "INIR", "INDR", "OUTI", "OUTD", "OTIR", "OTDR"):
            continue
        step = 1 if t in ("INI", "INIR", "OUTI", "OTIR") else -1
        for x in R.of("A", r):
            s, a = x[3], x[5]
            b = a["bc"] >> 8
            if t.startswith("IN"):
                v = mem_after(a, (a["hl"] - step) & 0xFFFF)  # the byte it stored
                k = v + ((s["bc"] + step) & 0xFF)
            else:
                v = s["win"][((a["hl"] - step) & 0xFFFF) - genA.WIN]
                k = v + (a["hl"] & 0xFF)
            F = a["af"] & 0xFF
            want = (z80.SZ[b] | (0x02 if v & 0x80 else 0) | (0x11 if k > 255 else 0)
                    | (z80.SZP[(k & 7) ^ b] & 0x04))
            assert F == want, (t, s, a)
            n += 1
    return n


# ---------------------------------------------------------------- before
def before(res):
    """the times chapters 13 and 14 printed of the instructions the manual
    leaves out, against this appendix's: chapter 14's by their bytes,
    chapter 13's halves of IX by their text"""
    t = json.loads(OUT_JSON.read_text())["times"]["rows"]
    rows = isetB.rows()
    by_key = {r["key"]: r for r in rows}
    by_text = {r["text"]: r for r in rows if r["group"] == "half"}
    doc = {r["key"] for r in iset.rows()}

    def ours(r):
        cs = t[str(r["n"])]
        assert len(cs) == 1, r["text"]
        return cs[0]["t"]

    load = lambda ch: json.loads((REPO / ch / f"meas{ch[2:]}.json").read_text())
    n14 = 0
    for x in load("ch14")["all"]["rows"]:
        b = x["bytes"]
        k = (b[0], 0xCB, b[3]) if b[0] in (0xDD, 0xFD) and b[1] == 0xCB else (
            (b[0], b[1]) if b[0] in (0xCB, 0xED, 0xDD, 0xFD) else (b[0],))
        if k in doc:
            continue                                    # Appendix A's
        r = by_key[k]
        assert ours(r) == x["t"] and t[str(r["n"])][0]["r"] == x["r"], (x, r["text"])
        n14 += 1
    n13 = 0
    for x in load("ch13")["cost"]["rows"]:
        if "ix" not in x["instr"]:
            continue                                    # Appendix A's
        text = re.sub(r"\$[0-9A-F]{2}", "n", x["instr"].upper().replace(", ", ","))
        assert ours(by_text[text]) == x["t"], (x, text)
        n13 += 1
    res["before"] = {"ch14": n14, "ch13": n13}


# ---------------------------------------------------------------- bus
def bus(res):
    """each of isetB.py's instructions alone on the model, both ways where it
    jumps on a condition: every fetch, read, write and port cycle starts
    where its MSX cycles, the ones the times above add up, put it"""
    def expected(cyc):
        out, at = [], 0
        for name, n in cyc:
            if name in ("M1", "MR", "MW", "IO"):
                out.append((name, at))
            at += n
        return out, at

    args = {"": [], "n": [genA.N], "d": [genB.D], "d n": [genB.D, genA.N], "n n": [0x00, 0xC5],
            "e": [0x00]}
    n = 0
    for r in isetB.rows():
        key = list(r["key"])
        if len(key) == 3 and key[1] == 0xCB:
            code = [key[0], 0xCB, genB.D, key[2]]
        else:
            code = key + args[r["show"][len(" ".join(f"{b:02X}" for b in key)):].strip()]
        ways = [True, False] if r["kind"] == "cond" else [True]
        for taken in ways:
            z = hm.Hidden()
            z.m[0xC800:0xC800 + len(code)] = bytes(code)
            z.pc, z.sp = 0xC800, 0xE0F0
            z.m[0xE0F0], z.m[0xE0F1] = 0x00, 0xC9           # RET: back to $C900
            for k, v in genA.PTR.items():
                if k in ("ix", "iy"):
                    setattr(z, k, v)
                else:
                    getattr(z, f"set_{k}")(v)
            z.c = genA.IN_PORT                              # a port the model reads
            if r["kind"] == "cond":
                if r["cc"] == "B":
                    z.b = 2 if taken else 1
                else:
                    z.f = genA.TRUE_F[r["cc"]] ^ (0 if taken else 0xFF)
            z.log = []
            z.step()
            want, total = expected(cyclesA.msx(predicted(r, taken)))
            assert z.log == want and z.t == total, (r["text"], taken, z.log, want)
            n += 1
    res["bus"] = {"checked": n}


# ---------------------------------------------------------------- table
def form_of(r):
    """the line of the appendix's tables a row goes in"""
    g, t = r["group"], r["text"]
    if g == "sll":
        return "SLL r" if r["key"][0] == 0xCB and r["key"][1] != 0x36 else t
    if g == "half":
        t = re.sub(r"I[XY]([HL])", r"IX\1", t)
        t = re.sub(r"(?<=[ ,])[BCDEA](?=,|$)", "r", t)
        if t.startswith(("INC", "DEC")):
            return "INC, DEC"
        if t.startswith(("ADD", "ADC", "SUB", "SBC", "AND", "XOR", "OR", "CP")):
            return "ALU"
        return re.sub(r"IX[HL]", "h", t)
    if g == "prefix":
        return genB.like(r)["family"]
    if g == "ed":
        return t if r["twin"] is None else genB.like(r)["text"]
    if g == "xcb":
        return ["rot", "BIT", "RES", "SET"][r["key"][2] >> 6]
    if g == "chain":
        return "LD" if r["key"][-1] == 0x21 else "NEG"
    raise ValueError(t)


def table(res):
    m = json.loads(OUT_JSON.read_text())
    tr = m["times"]["rows"]
    out = {}
    for r in isetB.rows():
        cs = tr[str(r["n"])]
        e = out.setdefault(r["group"], {}).setdefault(form_of(r), {
            "count": 0, "t": set(), "zilog": set(), "m1": set(), "cycles": set(), "keys": []})
        e["count"] += 1
        e["t"].add("/".join(str(c["t"]) for c in cs))
        e["zilog"].add("/".join(str(c["zilog"]) for c in cs))
        e["m1"].add("/".join(str(c["r"]) for c in cs))
        e["cycles"].add("/".join(c["cycles"] for c in cs))
        e["keys"].append(r["show"])
    for g, forms in out.items():
        for f, e in forms.items():
            for k in ("t", "zilog", "m1", "cycles"):
                e[k] = sorted(e[k])
    res["table"] = out


# ---------------------------------------------------------------- openmsx
def openmsx(res):
    if not versions.builds():
        res["openmsx"] = {"skipped": "OPENMSX_BUILDS not set"}
        return
    res["openmsx"] = versions.every_build(["appB"], ["times", "hidden"])


# ---------------------------------------------------------------- the main
STEPS = ["times", "hidden", "copies", "rules", "before", "bus", "table", "openmsx"]


def main(names=()):
    res = json.loads(OUT_JSON.read_text()) if names and OUT_JSON.exists() else {}
    R = None
    for name in STEPS:
        if names and name not in names:
            continue
        sub = {}
        if name in ("copies", "rules"):
            R = R or Runs()
            globals()[name](sub, R)
        else:
            globals()[name](sub)
        res[name] = sub[name]
        res = {k: res[k] for k in STEPS if k in res}
        OUT_JSON.write_text(json.dumps(res, indent=1) + "\n")
        print(" ", name, "ok", flush=True)
    return res


if __name__ == "__main__":
    main(sys.argv[1:])
