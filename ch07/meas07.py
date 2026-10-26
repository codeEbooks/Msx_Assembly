#!/usr/bin/env python3
"""meas07.py -- chapter 7: run the programs, read what they found, and check
every number against a model that does not come from the program.

    python3 gen07.py && ./build.sh && python3 meas07.py
                                  python3 meas07.py flags cond   only these
                                  python3 meas07.py --missing    those not measured yet

The models: Zilog's manual (the T-states, the flags each instruction sets,
the opcode patterns), with one wait state for every M1 cycle on the MSX
(chapter 3), and Sean Young's "The Undocumented Z80 Documented" for flag bits
5 and 3; the values the generator wrote into the programs; the character
shapes of the BIOS file (tools/screentext.py); and the clock.

  regs      cpuregs at the stop of regs.rom (listing 7.1), against the values
            loaded, R counted fetch by fetch, and the time from INIT
  cost      a byte from a register and from memory: T-states and R, each
  rcount    the eight readings of R, twice
  pairs     INC HL and INC L on $00FF
  flags     the screen of flags.rom (figure 7.1), read back cell by cell,
            against the bytes the program kept and against the flag model
  flagtest  which flags eighteen instructions set
  cond      the eight conditions on two values of F
  ixh       the halves of IX
  shapes    one instruction of each shape: the disassembly (listing 7.3), the
            T-states and R
  loop      loop.rom and loop_ok.rom four seconds after power-on: the turns
            against the clock
  listings  grid, families, index and fake: every byte against its pattern
  syntax    every program of the book assembled again with --syntax=F
  answers   the workshop, tried (for Appendix I)
  openmsx   all of it again with every other build (tools/versions.py)
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(HERE))
import console     # noqa: E402
import msxcap      # noqa: E402
import screentext  # noqa: E402
import versions    # noqa: E402
import gen07       # noqa: E402

CAPS = HERE / "captures"
# openMSX runs the Z80 at 3,579,545 Hz exactly, not at 315/88 MHz: over the
# 1.3 seconds of loop.rom the difference is more than half a T-state
CLOCK = 3579545
RUNNING = ("time", 4)          # four seconds after power-on, as chapter 6 looked
RESULTS = 0xC000


def sym(name):
    out = {}
    for line in (HERE / f"{name}.sym").read_text().splitlines():
        lab, _, val = line.partition(": EQU 0x")
        if val:
            out[lab.strip()] = int(val, 16)
    return out


def keep(name, entries):
    (HERE / f"{name}.txt").write_text(console.transcript(entries))
    return [list(e) for e in entries]


def answer(entries, line, n=0):
    return [a for l, a, _ in entries if l == line][n]


def at_stop(name, tcl_body, label="stop", frames=3):
    """run name.rom; when it reaches `label`, run tcl_body once (it logs with L)"""
    s = sym(name)
    tcl = f"set ::bp [debug set_bp {s[label]} {{}} {{ {tcl_body}; debug remove_bp $::bp }}]"
    return msxcap.run_tcl(HERE / f"{name}.rom", frames, tcl)


def memory(name, n, label="stop", frames=3):
    """the n bytes from RESULTS when the program reaches `label`"""
    lines = at_stop(name, f'set s ""; for {{set i 0}} {{$i < {n}}} {{incr i}} '
                          f'{{append s " " [debug read memory [expr {{{RESULTS} + $i}}]]}}; L "mem$s"',
                    label, frames)
    return [int(v) for v in next(l for l in lines if l.startswith("mem")).split()[1:]]


# ---------------------------------------------------------------- the models
# Zilog's T-states and M1 cycles; the MSX adds one T-state to every M1
ZILOG = {"di": (4, 1), "nop": (4, 1), "xor a": (4, 1), "ld r,a": (9, 2), "ld a,n": (7, 1),
         "ex af,af'": (4, 1), "exx": (4, 1), "ld rr,nn": (10, 1), "ld ix,nn": (14, 2),
         "ld iy,nn": (14, 2), "ld sp,nn": (10, 1), "ld a,b": (4, 1), "ld a,(hl)": (7, 1),
         "ld a,(nn)": (13, 1), "ld (hl),a": (7, 1), "ld (nn),a": (13, 1), "rlc b": (8, 2),
         "neg": (8, 2), "ld bc,(nn)": (20, 2), "ld a,(ix+d)": (19, 2),
         "ld (ix+d),n": (19, 2), "set b,(ix+d)": (23, 2), "ld hl,nn": (10, 1)}


def key(ins):
    """the instruction's line in ZILOG"""
    i = " ".join(ins.replace(", ", ",").split()).lower()
    i = i.replace("sys_area", "$f380").replace("ram_start", "$c000")
    i = re.sub(r"\(ix\+\d+\)", "(ix+d)", i)
    i = re.sub(r"^set \d,", "set b,", i)
    i = re.sub(r"\(\$[0-9a-f]+\)", "(nn)", i)
    m = re.fullmatch(r"ld (bc|de|hl|sp|ix|iy),\$[0-9a-f]+", i)
    if m:
        return {"bc": "ld rr,nn", "de": "ld rr,nn"}.get(m.group(1), f"ld {m.group(1)},nn")
    return re.sub(r",(\$[0-9a-f]+|\d+)$", ",n", i)


def msx_t(ins):
    z, m1 = ZILOG[key(ins)]
    return z + m1, z, m1


def parity(v):
    return bin(v).count("1") % 2 == 0


def alu(op, a, n=0, f_in=0):
    """(A after, F after) from Zilog's tables; bits 5 and 3 from Young: a copy
    of the result's, but of the operand's for CP"""
    S, Z, Y, H, X, V, N, C = 0x80, 0x40, 0x20, 0x10, 0x08, 0x04, 0x02, 0x01
    if op in ("add", "sub", "cp"):
        r = a + n if op == "add" else a - n
        res = r & 0xFF
        f = (res & S) | (Z if res == 0 else 0)
        if op == "add":
            f |= (H if (a & 15) + (n & 15) > 15 else 0) | (V if (~(a ^ n) & (a ^ res) & 0x80) else 0)
            f |= C if r > 255 else 0
        else:
            f |= (H if (a & 15) < (n & 15) else 0) | (V if ((a ^ n) & (a ^ res) & 0x80) else 0)
            f |= N | (C if a < n else 0)
        f |= ((n if op == "cp" else res) & (Y | X))
        return (a if op == "cp" else res), f
    if op in ("inc", "dec"):
        res = (a + (1 if op == "inc" else -1)) & 0xFF
        f = (res & (S | Y | X)) | (Z if res == 0 else 0) | (f_in & C)
        if op == "inc":
            f |= (H if a & 15 == 15 else 0) | (V if a == 0x7F else 0)
        else:
            f |= (H if a & 15 == 0 else 0) | (V if a == 0x80 else 0) | N
        return res, f
    res = {"and": a & n, "or": a | n, "xor": a ^ n}[op]
    f = (res & (S | Y | X)) | (Z if res == 0 else 0) | (V if parity(res) else 0)
    f |= H if op == "and" else 0
    return res, f


def flags_model(before, ins):
    """the instruction of flags.asm, worked out by alu()"""
    w = ins.replace(",", " ").split()
    op = w[0]
    if op in ("inc", "dec"):
        return alu(op, before)
    n = int(w[-1].replace("$", "0x"), 0) if w[-1] != "a" else before
    return alu(op, before, n)


# the documented flags each instruction of flagtest.asm sets, from Zilog
SETS = {"ld a, b": "", "add a, b": "SZHVNC", "sub b": "SZHVNC", "cp b": "SZHVNC",
        "inc a": "SZHVN", "dec a": "SZHVN", "and b": "SZHVNC", "or b": "SZHVNC",
        "xor b": "SZHVNC", "rlca": "HNC", "cpl": "HN", "neg": "SZHVNC", "scf": "HNC",
        "inc hl": "", "dec bc": "", "add hl, de": "HNC", "out (PSG_ADDR), a": "", "jr $+2": ""}
BITS = {"S": 7, "Z": 6, "H": 4, "V": 2, "N": 1, "C": 0}


def holds(cond, f):
    bit = {"z": 6, "c": 0, "p": 2, "m": 7}
    name = cond.replace("n", "") if cond in ("nz", "nc") else cond
    if cond in ("po", "pe"):
        v = bool(f >> 2 & 1)
        return v if cond == "pe" else not v
    if cond in ("p", "m"):
        v = bool(f >> 7 & 1)
        return v if cond == "m" else not v
    v = bool(f >> bit[name] & 1)
    return not v if cond.startswith("n") else v


def times(name, labels):
    """machine_info time and R at each label, the first time it is reached"""
    s = sym(name)
    tcl = "\n".join(f'set ::b{lab} [debug set_bp {s[lab]} {{}} '
                    f'{{L "T {lab} [machine_info time] [reg r]"; debug remove_bp $::b{lab}}}]'
                    for lab in labels)
    lines = msxcap.run_tcl(HERE / f"{name}.rom", 2, tcl)
    t, r = {}, {}
    for line in lines:
        if line.startswith("T "):
            _, lab, v, rr = line.split()
            t[lab], r[lab] = float(v), int(rr)
    return t, r


def timed_rows(name, instrs):
    labels = [f"t{i}" for i in range(len(instrs) + 1)]
    t, r = times(name, labels)
    rows = []
    for i, ins in enumerate(instrs):
        T = round((t[labels[i + 1]] - t[labels[i]]) * CLOCK)
        dr = (r[labels[i + 1]] - r[labels[i]]) % 128
        model, z, m1 = msx_t(ins)
        assert T == model and dr == m1, (ins, T, model, dr, m1)
        rows.append({"ins": ins, "t": T, "zilog": z, "r": dr})
    return rows


# ---------------------------------------------------------------- regs
def regs():
    s = sym("regs")
    e = console.session(HERE / "regs.rom", ["cpuregs", "reg b", "reg c"], start=s["stop"])
    got = dict(re.findall(r"(\S+?)\s*=\s*([0-9A-F]+)", answer(e, "cpuregs")))
    # what the registers held at INIT: AF' before the program swapped it in
    lines = msxcap.run_tcl(HERE / "regs.rom", 1, 'L "init [reg af2] [machine_info time]"\n'
                           f'set ::bp [debug set_bp {s["stop"]} {{}} '
                           '{ L "stop [machine_info time]"; debug remove_bp $::bp }]')
    af2_init = int(next(l for l in lines if l.startswith("init ")).split()[1])
    t_init = float(next(l for l in lines if l.startswith("init ")).split()[2])
    t_stop = float(next(l for l in lines if l.startswith("stop ")).split()[1])
    # the model: the values loaded, and what EX AF,AF' and EXX swap
    xor_f = alu("xor", 0, 0)[1]
    want = {"BC'": 0x1111, "DE'": 0x2222, "HL'": 0x3333}
    want.update({r.upper(): v for r, v in gen07.REGS_SECOND})
    want["AF'"] = gen07.REGS_A << 8 | xor_f
    want["AF"] = gen07.REGS_A2 << 8 | (af2_init & 0xFF)       # F: the old F'
    want["SP"] = 0xF380
    want["PC"] = s["stop"]
    # R: 0 after LD R,A, then one for each opcode fetch until the stop
    src = (HERE / "regs.asm").read_text().split("ld r, a")[1].split("stop:")[0]
    after = [l.split(";")[0].strip() for l in src.splitlines()[1:] if l.split(";")[0].strip()]
    want["R"] = sum(msx_t(i)[2] for i in after)
    body = (HERE / "regs.asm").read_text().split("init:")[1].split("stop:")[0]
    instrs = [l.split(";")[0].strip() for l in body.splitlines() if l.split(";")[0].strip()]
    t_model = sum(msx_t(i)[0] for i in instrs)
    t = round((t_stop - t_init) * CLOCK)
    same = {k: int(got[k], 16) == v for k, v in want.items()}
    assert all(same.values()) and t == t_model, (same, got, t, t_model)
    assert int(answer(e, "reg b")) == 0x12 and int(answer(e, "reg c")) == 0x34
    return {"session": keep("regs", e), "registers": got, "checked": sorted(same),
            "instructions": len(instrs), "after_ld_r": len(after), "fetches_after_ld_r": want["R"],
            "t_init_to_stop": t, "af2_at_init": f"{af2_init:04X}", "xor_a_f": xor_f}


# ---------------------------------------------------------------- cost
def cost():
    return {"rows": timed_rows("cost", [i for i, _ in gen07.COST])}


# ---------------------------------------------------------------- rcount
def rcount():
    got = memory("rcount", gen07.R_READS * len(gen07.R_STARTS))
    out = {}
    for k, r0 in enumerate(gen07.R_STARTS):
        # LD R,A, then LD HL,nn and LD B,n (2 fetches), then each turn: LD A,R
        # reads R after its own 2 fetches, and the turn has 5
        model, r = [], r0
        r = (r & 0x80) | ((r + 2) & 0x7F)
        for _ in range(gen07.R_READS):
            r = (r & 0x80) | ((r + 2) & 0x7F)
            model.append(r)
            r = (r & 0x80) | ((r + 3) & 0x7F)
        read = got[gen07.R_READS * k: gen07.R_READS * (k + 1)]
        assert read == model, (r0, read, model)
        out[f"from_{r0:02x}"] = read
    out["per_turn"] = (out["from_7e"][1] - out["from_7e"][0]) % 128
    return out


# ---------------------------------------------------------------- pairs
def pairs():
    got = memory("pairs", 6)
    out = {}
    for k, ins in enumerate(gen07.PAIRS):
        hl, f = got[3 * k] | got[3 * k + 1] << 8, got[3 * k + 2]
        v = gen07.PAIRS_VALUE
        if ins == "inc hl":
            model = ((v + 1) & 0xFFFF, 0)                       # no flag at all
        else:
            l, fl = alu("inc", v & 0xFF)
            model = ((v & 0xFF00) | l, fl)
        assert (hl, f) == model, (ins, hl, f, model)
        out[ins.replace(" ", "_")] = {"hl": hl, "f": f}
    return out


# ---------------------------------------------------------------- flags
FLAGS_FRAME = 10


def flags():
    got = msxcap.capture(HERE / "flags.rom", [FLAGS_FRAME - 1, FLAGS_FRAME], CAPS, "flags_f")
    from PIL import Image
    a, b = (Image.open(got[n]).convert("RGB") for n in (FLAGS_FRAME - 1, FLAGS_FRAME))
    assert a.tobytes() == b.tobytes(), "the page is still changing"
    got[FLAGS_FRAME - 1].unlink()
    page = screentext.Page(got[FLAGS_FRAME])
    kept = memory("flags", 2 * len(gen07.FLAGS), label="done", frames=6)
    C = gen07.FLAG_COLS
    rows = []
    for i, (before, ins) in enumerate(gen07.FLAGS):
        line = page.line(gen07.FLAG_ROW0 + gen07.FLAG_STEP * i)
        a_after, f = flags_model(before, ins)
        seen = {"before": line[C["before"]:C["before"] + 2], "text": line[C["text"]:C["after"]].strip(),
                "after": line[C["after"]:C["after"] + 2], "bits": line[C["bits"]:C["bits"] + 8],
                "F": line[C["F"]:C["F"] + 2]}
        want = {"before": f"{before:02X}", "text": gen07.shown(ins), "after": f"{a_after:02X}",
                "bits": f"{f:08b}", "F": f"{f:02X}"}
        assert seen == want, (seen, want)
        assert kept[2 * i: 2 * i + 2] == [a_after, f], (ins, kept[2 * i: 2 * i + 2])
        rows.append({"text": want["text"], "before": before, "after": a_after, "f": f})
    head = page.line(gen07.FLAG_ROW0 - 2)
    return {"rows": rows, "frame": FLAGS_FRAME, "heading": head.rstrip()}


# ---------------------------------------------------------------- flagtest
def flagtest():
    got = memory("flagtest", 4 * len(gen07.FLAGTEST))
    rows = []
    for i, (ins, _) in enumerate(gen07.FLAGTEST):
        f0, f1 = got[4 * i], got[4 * i + 2]          # F after, from F = $00 and $FF
        sets = "".join(n for n, b in BITS.items() if (f0 >> b & 1) == (f1 >> b & 1))
        left = "".join(n for n, b in BITS.items() if (f0 >> b & 1) == 0 and (f1 >> b & 1) == 1)
        assert len(sets) + len(left) == 6, (ins, f0, f1)
        assert sets == SETS[ins], (ins, sets, SETS[ins])
        rows.append({"instr": ins, "sets": sets, "f_from_00": f0, "f_from_ff": f1})
    return {"rows": rows, "agree": len(rows)}


# ---------------------------------------------------------------- cond
def cond():
    got = memory("cond", 8 * len(gen07.COND_F))
    rows = []
    for k, f in enumerate(gen07.COND_F):
        taken = got[8 * k: 8 * k + 8]
        assert taken == [int(holds(c, f)) for c in gen07.CONDS], (f, taken)
        rows.append({"f": f, "taken": taken})
    return {"rows": rows}


# ---------------------------------------------------------------- ixh
def ixh():
    lines = at_stop("ixh", 'L "regs [reg a] [reg b] [reg hl] [reg ix]"')
    a, b, hl, ix = (int(v) for v in next(l for l in lines if l.startswith("regs")).split()[1:])
    assert (a, b, hl, ix) == (gen07.IXH_IX >> 8, gen07.IXH_IX & 0xFF, gen07.IXH_HL, gen07.IXH_IX)
    lst = assemble_lines(["ld a,ixh", "ld b,ixl", "ld a,h", "ld b,l"])
    return {"a": a, "b": b, "hl": hl, "ix": ix, "bytes": lst}


# ---------------------------------------------------------------- shapes
def shapes():
    s = sym("shapes")
    n = len(gen07.SHAPES)
    e = console.session(HERE / "shapes.rom", [f"disasm [reg pc] {n + 1}"], start=s["t0"])
    dis = [l for l in e[0][1].splitlines() if l.strip()]
    rom = (HERE / "shapes.rom").read_bytes()
    lens = []
    for l in dis:
        addr = int(l.split()[0], 16)
        code = [int(x, 16) for x in l[26:].split()]
        assert list(rom[addr - 0x4000: addr - 0x4000 + len(code)]) == code, l
        lens.append(len(code))
    rows = timed_rows("shapes", gen07.SHAPES)
    for row, k in zip(rows, lens):
        row["bytes"] = k
    lst = assemble_lines([ins.replace("RAM_START", "$C000") for ins in gen07.SHAPES])
    for row, b in zip(rows, lst):
        row["code"] = b
        assert len(b) == row["bytes"]
    return {"session": keep("shapes", e), "rows": rows, "disasm": dis}


# ---------------------------------------------------------------- loop
def loop():
    out = {}
    for name in ("loop", "loop_ok"):
        s = sym(name)
        e = console.session(HERE / f"{name}.rom", ["reg pc", "reg bc"], start=RUNNING)
        out[name] = {"session": keep(name, e), "pc": int(answer(e, "reg pc")),
                     "bc": int(answer(e, "reg bc"))}
    # the clock: when loop.rom loads BC, and the same moment the session looked
    s = sym("loop")
    home = msxcap.make_home()
    log = home / "loop.log"
    (home / "loop.tcl").write_text(f"""
set ::log [open {{{log}}} w]
proc L {{s}} {{ puts $::log $s; flush $::log }}
set ::bp [debug set_bp {s["count"] - 3} {{}} {{ L "ldbc [machine_info time]"; debug remove_bp $::bp }}]
# at the same moment, a breakpoint on the DEC BC: the next turn's start
after time {RUNNING[1]} {{
    debug set_bp {s["count"]} {{}} {{ L "at [machine_info time] [reg bc] [reg pc]"; exit }}
}}
""")
    msxcap.run_openmsx(HERE / "loop.rom", msxcap.DEFAULT_MACHINE, home / "loop.tcl", home, 300)
    lines = log.read_text().splitlines()
    shutil.rmtree(home, ignore_errors=True)
    t_ldbc = float(next(l for l in lines if l.startswith("ldbc")).split()[1])
    _, t_at, bc, pc = next(l for l in lines if l.startswith("at")).split()
    bc, pc = int(bc), int(pc)
    # the breakpoint set at that moment stops the next DEC BC that has not
    # started yet: it finds the session's BC, or one less
    assert pc == s["count"] and bc in (out["loop"]["bc"], (out["loop"]["bc"] - 1) % 65536)
    assert out["loop"]["pc"] in (s["count"], s["count"] + 1)
    # the turn: DEC BC (6 + 1) and JR NZ taken (12 + 1)
    turn = 7 + 13
    elapsed = round((float(t_at) - t_ldbc) * CLOCK) - 11       # after LD BC,nn (10 + 1)
    assert elapsed % turn == 0, elapsed
    decs = elapsed // turn
    assert bc == (gen07.LOOP_COUNT - decs) % 65536, (bc, decs)
    assert out["loop_ok"]["pc"] == sym("loop_ok")["done"] and out["loop_ok"]["bc"] == 0
    out["clock"] = {"t_states": elapsed, "turn": turn, "decs": decs, "wraps": decs // 65536,
                    "ld_bc_time": t_ldbc, "seconds": RUNNING[1]}
    return out


# ---------------------------------------------------------------- the listings
LST = re.compile(r"^\s*(\d+)\s+([0-9A-F]{4})(.*)$")


def lst_fields(m):
    """(line number, bytes, source) of a matched listing line: the bytes are
    in the twelve columns after the address"""
    rest = m.group(3)
    return m.group(1), [int(x, 16) for x in rest[1:13].split()], rest[13:]


def read_lst(name):
    """[(source line, bytes)] for every line of name.lst that made bytes"""
    out, last = [], None
    for line in (HERE / f"{name}.lst").read_text().splitlines():
        m = LST.match(line)
        if not m:
            continue
        num, code, src = lst_fields(m)
        if num == last and out:
            out[-1][1].extend(code)
        elif code:
            out.append((src.split(";")[0].strip(), code))
        last = num
    return out


def assemble_lines(lines):
    """the bytes sjasmplus gives each line, assembled on their own"""
    tmp = Path(tempfile.mkdtemp(prefix="asm7_"))
    try:
        (tmp / "x.asm").write_text("        ORG $4000\n" + "".join(f"        {l}\n" for l in lines))
        subprocess.run(["sjasmplus", "--nologo", "--msg=err", "--lst=x.lst", "x.asm"], cwd=tmp,
                       check=True, capture_output=True)
        out = []
        for line in (tmp / "x.lst").read_text().splitlines():
            m = LST.match(line)
            if m and lst_fields(m)[2].strip() and not lst_fields(m)[2].strip().startswith("ORG"):
                code = lst_fields(m)[1]
                if code:
                    out.append(code)
        return out
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def pattern(family, line):
    """the bytes an instruction must have, from its family's bit pattern"""
    R = {r: i for i, r in enumerate(gen07.RN)}
    P = {p: i for i, p in enumerate(gen07.PN)}
    Q = {q: i for i, q in enumerate(gen07.QN)}
    w = line.replace(",", " ").split()
    if family == "ld r,n":
        return [0x06 | R[w[1]] << 3, 0x12]
    if family in ("inc r", "dec r"):
        return [(0x04 if family == "inc r" else 0x05) | R[w[1]] << 3]
    if family == "alu r":
        op = next(i for i, o in enumerate(gen07.ALU) if line.startswith(o.rstrip(",")))
        return [0x80 | op << 3 | R[w[-1]]]
    if family == "rot r":
        return [0xCB, gen07.ROT.index(w[0]) << 3 | R[w[1]]]
    if family in ("bit", "res", "set"):
        return [0xCB, {"bit": 0x40, "res": 0x80, "set": 0xC0}[family] | int(w[1]) << 3 | R[w[2]]]
    if family == "ld rr,nn":
        return [0x01 | P[w[1]] << 4, 0x34, 0x12]
    simple = {"inc rr": 0x03, "dec rr": 0x0B, "add hl,rr": 0x09}
    if family in simple:
        return [simple[family] | P[w[-1]] << 4]
    if family in ("push qq", "pop qq"):
        return [(0xC5 if family == "push qq" else 0xC1) | Q[w[1]] << 4]
    if family in ("sbc hl,rr", "adc hl,rr"):
        return [0xED, (0x42 if family == "sbc hl,rr" else 0x4A) | P[w[-1]] << 4]
    c = gen07.CONDS.index(w[1])
    return {"jp cc,nn": [0xC2 | c << 3, 0x34, 0x12], "call cc,nn": [0xC4 | c << 3, 0x34, 0x12],
            "ret cc": [0xC0 | c << 3], "jr cc,e": [0x20 | c << 3, 0x00]}[family]


def listings():
    # grid: $40 + 8 x destination + source, HALT where LD (HL),(HL) would be
    grid = read_lst("grid")
    assert len(grid) == 64
    codes = {}
    for k, (src, code) in enumerate(grid):
        d, s = divmod(k, 8)
        assert code == [0x40 + 8 * d + s], (src, code)
        codes[f"{d}{s}"] = code[0]
    assert grid[54][0] == "halt" and codes["66"] == 0x76
    # families
    fam = read_lst("families")
    want = [(name, l) for name, lines in gen07.families() for l in lines]
    assert len(fam) == len(want)
    counts = {"unprefixed": 0, "cb": 0, "ed": 0}
    by_family = {}
    for (src, code), (name, line) in zip(fam, want):
        assert src == line and code == pattern(name, line), (src, code, pattern(name, line))
        counts["cb" if code[0] == 0xCB else "ed" if code[0] == 0xED else "unprefixed"] += 1
        by_family.setdefault(name, []).append(code[0] if code[0] not in (0xCB, 0xED) else code[1])
    # index: DD or FD in front of the HL form; (HL) -> (IX+d) with d after the
    # opcode, or after CB and before the last byte
    idx = read_lst("index")
    rows = []
    for k, (hl, ix) in enumerate(gen07.INDEX):
        (s0, b0), (s1, b1), (s2, b2) = idx[3 * k: 3 * k + 3]
        assert s0 == hl and s1 == ix
        if "(ix+" in ix:
            d = int(ix.split("+")[1].split(")")[0])
            want_ix = ([0xDD, 0xCB, d, b0[1]] if b0[0] == 0xCB else [0xDD, b0[0], d] + b0[1:])
        else:
            want_ix = [0xDD] + b0
        assert b1 == want_ix and b2 == [0xFD] + want_ix[1:], (hl, b0, b1, b2)
        rows.append({"hl": hl, "ix": ix, "hl_bytes": b0, "ix_bytes": b1, "iy_bytes": b2})
    # fake: what sjasmplus made of the two
    fk = read_lst("fake")
    real = assemble_lines(["ld b,d", "ld c,e", "ld l,(ix+1)", "ld h,(ix+2)"])
    assert fk[0][1] == real[0] + real[1] and fk[1][1] == real[2] + real[3]
    syntax = {}
    for opt in ("", "--syntax=f", "--syntax=F"):
        tmp = Path(tempfile.mkdtemp(prefix="fake7_"))
        shutil.copy(HERE / "fake.asm", tmp)
        r = subprocess.run(["sjasmplus", "--nologo", *([opt] if opt else []), "fake.asm"], cwd=tmp,
                           capture_output=True, text=True)
        shutil.rmtree(tmp, ignore_errors=True)
        said = [l.split(": ", 1)[1] for l in (r.stdout + r.stderr).splitlines()
                if "fake.asm(" in l]
        syntax[opt or "default"] = {"exit": r.returncode, "said": said}
    return {"grid": {"opcodes": codes, "checked": len(grid)},
            "families": {"checked": len(fam), **counts,
                         "lines": {k: v for k, v in by_family.items()}},
            "index": {"rows": rows, "checked": len(rows) * 3},
            "fake": {"listing": [{"src": s, "bytes": b} for s, b in fk], "syntax": syntax}}


# ---------------------------------------------------------------- syntax
def syntax():
    """every source of the book, assembled again with fake instructions
    refused: the same bytes, or a refusal"""
    same, refused, broken = [], [], []
    for asm in sorted(REPO.glob("ch*/*.asm")):
        first = asm.read_text().splitlines()[0]
        outs = re.findall(r'^\s*OUTPUT\s+"([^"]+)"', asm.read_text(), re.M)
        if not outs:
            continue
        rel = f"{asm.parent.name}/{asm.name}"
        if "does not assemble, on purpose" in first:
            broken.append(rel)
            continue
        tmp = Path(tempfile.mkdtemp(prefix="synF_"))
        try:
            for f in asm.parent.iterdir():
                if f.suffix in (".asm", ".inc", ".bin"):
                    shutil.copy(f, tmp)
            r = subprocess.run(["sjasmplus", "--nologo", "--msg=err", "--syntax=F", asm.name],
                               cwd=tmp, capture_output=True, text=True)
            ok = r.returncode == 0 and all((tmp / o).read_bytes() == (asm.parent / o).read_bytes()
                                           for o in outs)
            (same if ok else refused).append(rel)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    assert refused == ["ch07/fake.asm"], refused
    return {"same": len(same), "refused": refused, "broken_on_purpose": broken}


# ---------------------------------------------------------------- answers
def answers():
    out = {}
    out["ld_e_h"] = assemble_lines(["ld e,h"])[0]
    assert out["ld_e_h"] == [0x40 + 8 * 3 + 4]
    out["iy"] = assemble_lines(["ld iy,$1234", "bit 7,(iy+3)"])
    # question 3: pairs.asm with DEC HL and DEC L on $0100
    tmp = Path(tempfile.mkdtemp(prefix="pairs7_"))
    try:
        src = (HERE / "pairs.asm").read_text().replace("inc hl", "dec hl").replace("inc l", "dec l")
        src = src.replace(f"${gen07.PAIRS_VALUE:04X}", "$0100")
        (tmp / "pairs.asm").write_text(src)
        shutil.copy(HERE / "msx.inc", tmp)
        subprocess.run(["sjasmplus", "--nologo", "--msg=err", "--sym=pairs.sym", "pairs.asm"],
                       cwd=tmp, check=True)
        s = {l.split(":")[0]: int(l.split("0x")[1], 16)
             for l in (tmp / "pairs.sym").read_text().splitlines() if ": EQU 0x" in l}
        lines = msxcap.run_tcl(tmp / "pairs.rom", 3,
                               f'set ::bp [debug set_bp {s["stop"]} {{}} {{ set s ""; '
                               'for {set i 0} {$i < 6} {incr i} '
                               f'{{append s " " [debug read memory [expr {{{RESULTS} + $i}}]]}}; '
                               'L "mem$s"; debug remove_bp $::bp }]')
        got = [int(v) for v in next(l for l in lines if l.startswith("mem")).split()[1:]]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    dl, fl = alu("dec", 0x00)
    assert got == [0xFF, 0x00, 0x00, dl, 0x01, fl], got
    out["dec_hl"] = {"hl": got[0] | got[1] << 8, "f": got[2]}
    out["dec_l"] = {"hl": got[3] | got[4] << 8, "f": got[5]}
    return out


# ---------------------------------------------------------------- openmsx
OPENMSX_SECTIONS = ["regs", "cost", "rcount", "pairs", "flags", "flagtest", "cond", "ixh",
                    "shapes", "loop", "answers"]


def openmsx():
    if not versions.builds():
        return {"skipped": "OPENMSX_BUILDS not set"}
    return versions.every_build(["ch07"], OPENMSX_SECTIONS)


SECTIONS = {"regs": regs, "cost": cost, "rcount": rcount, "pairs": pairs, "flags": flags,
            "flagtest": flagtest, "cond": cond, "ixh": ixh, "shapes": shapes, "loop": loop,
            "listings": listings, "syntax": syntax, "answers": answers, "openmsx": openmsx}


def main(names=()):
    CAPS.mkdir(exist_ok=True)
    path = HERE / "meas07.json"
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
    print(json.dumps(main(sys.argv[1:]), indent=1)[:3000])
