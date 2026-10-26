#!/usr/bin/env python3
"""meas09.py -- the arithmetic of chapter 9, measured.

    python3 gen09.py && ./build.sh && python3 meas09.py
                                  python3 meas09.py hist daa   only these
                                  python3 meas09.py --missing  those not measured yet

The models: Zilog's rules for the flags, with bits 5 and 3 and DAA from Sean
Young's "The Undocumented Z80 Documented"; Zilog's T-states plus one for
every M1 (chapters 3 and 7); Python's own arithmetic; the character shapes
of the BIOS file.

  cost      bytes, T-states and R of each arithmetic instruction
  hist      for ADD, ADC, SUB and SBC on all 65,536 pairs, how often each
            value of F came out, against the flag model
  neg       NEG on all 256 values of A, against SUB from 0
  times10   HL x 10 by sums alone, and one call timed
  add32     the nine lines on the screen (figure 9.1) against Python's
            32-bit arithmetic; one call of add32 and of sub32 timed
  hl16      HL and F after each sixteen-bit test, against the flag model;
            the console after the first (listing 9.3)
  stale     SBC HL,DE with the carry left set, and cleared
  widen     a signed byte added to a position, done right and as unsigned
  daa       A and F after DAA in all 2,048 cases, against Young's rules
  score     the twenty rows on the screen (figure 9.2) against 37 x the
            frame; the two sums and the two conversions timed on every frame
  answers   the workshop, tried (for Appendix I)
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
import msxcap      # noqa: E402
import probe       # noqa: E402
import screentext  # noqa: E402
import versions    # noqa: E402
import gen09       # noqa: E402

CAPS = HERE / "captures"
CLOCK = probe.CLOCK
RESULTS = 0xC000


def rom(name):
    return HERE / f"{name}.rom"


def sym(name):
    return probe.sym(HERE / f"{name}.sym")


def keep(name, entries):
    (HERE / f"{name}.txt").write_text(console.transcript(entries))
    return [list(e) for e in entries]


def finished(name, frame):
    got = msxcap.capture(rom(name), [frame - 1, frame], CAPS, f"{name}_f")
    a, b = (Image.open(got[n]).convert("RGB") for n in (frame - 1, frame))
    assert a.tobytes() == b.tobytes(), f"{name}: still changing at frame {frame}"
    got[frame - 1].unlink()
    return got[frame]


# ---------------------------------------------------------------- the models
def parity(v):
    return bin(v).count("1") % 2 == 0


def add8(a, b, c):
    r = a + b + c
    res = r & 0xFF
    return res, ((res & 0xA8) | (0x40 if res == 0 else 0) |
                 (0x10 if (a & 0xF) + (b & 0xF) + c > 0xF else 0) |
                 (0x04 if (~(a ^ b)) & (a ^ res) & 0x80 else 0) |
                 (0x01 if r > 0xFF else 0))


def sub8(a, b, c):
    r = a - b - c
    res = r & 0xFF
    return res, ((res & 0xA8) | (0x40 if res == 0 else 0) |
                 (0x10 if (a & 0xF) - (b & 0xF) - c < 0 else 0) |
                 (0x04 if (a ^ b) & (a ^ res) & 0x80 else 0) | 0x02 |
                 (0x01 if r < 0 else 0))


HIST_MODEL = {"add": lambda a, b: add8(a, b, 0), "adc": lambda a, b: add8(a, b, 1),
              "sub": lambda a, b: sub8(a, b, 0), "sbc": lambda a, b: sub8(a, b, 1)}


def run16(code, hl, de, f, a=0):
    """the sixteen-bit tests, instruction by instruction"""
    for ins in code:
        c = f & 1
        if ins == "or a":
            f = (a & 0xA8) | (0x40 if a == 0 else 0) | (0x04 if parity(a) else 0)
        elif ins == "add hl,de":
            r = hl + de
            res = r & 0xFFFF
            f = ((f & 0xC4) | ((res >> 8) & 0x28) |
                 (0x10 if (hl & 0xFFF) + (de & 0xFFF) > 0xFFF else 0) | (0x01 if r > 0xFFFF else 0))
            hl = res
        elif ins == "adc hl,de":
            r = hl + de + c
            res = r & 0xFFFF
            f = (((res >> 8) & 0xA8) | (0x40 if res == 0 else 0) |
                 (0x10 if (hl & 0xFFF) + (de & 0xFFF) + c > 0xFFF else 0) |
                 (0x04 if (~(hl ^ de)) & (hl ^ res) & 0x8000 else 0) | (0x01 if r > 0xFFFF else 0))
            hl = res
        elif ins == "sbc hl,de":
            r = hl - de - c
            res = r & 0xFFFF
            f = (((res >> 8) & 0xA8) | (0x40 if res == 0 else 0) |
                 (0x10 if (hl & 0xFFF) - (de & 0xFFF) - c < 0 else 0) |
                 (0x04 if (hl ^ de) & (hl ^ res) & 0x8000 else 0) | 0x02 | (0x01 if r < 0 else 0))
            hl = res
        else:
            raise ValueError(ins)
    return hl, f


def daa_model(a, f):
    """DAA as The Undocumented Z80 Documented sets it out"""
    c, h, n = f & 1, (f >> 4) & 1, (f >> 1) & 1
    lo = a & 0xF
    diff, c_out = 0, 0
    if c or a > 0x99:
        diff, c_out = 0x60, 1
    if h or lo > 9:
        diff |= 0x06
    res = (a - diff) & 0xFF if n else (a + diff) & 0xFF
    h_out = (h and lo < 6) if n else lo > 9
    return res, ((res & 0xA8) | (0x40 if res == 0 else 0) | (0x10 if h_out else 0) |
                 (0x04 if parity(res) else 0) | (n << 1) | c_out)


# Zilog's T-states and M1 cycles; the MSX adds one T-state to every M1
ZILOG = {"add a,b": (4, 1), "adc a,(hl)": (7, 1), "sub $12": (7, 1), "daa": (4, 1),
         "neg": (8, 2), "add hl,de": (11, 1), "adc hl,de": (15, 2), "sbc hl,de": (15, 2),
         "add ix,de": (15, 2), "inc hl": (6, 1)}
T = {"call": 18, "ret": 11, "ld r,n": 8, "or a": 5, "ld a,(de)": 8, "adc a,(hl)": 8,
     "ld (de),a": 8, "inc de": 7, "inc hl": 7, "djnz": 14, "djnz_last": 9, "ld r,r": 5,
     "add hl,rr": 12, "ld hl,nn": 11, "ld a,(hl)": 8, "add a,n": 8, "daa": 5, "ld (hl),a": 8,
     "dec hl": 7, "ld hl,(nn)": 17, "ld de,nn": 11, "ld (nn),hl": 17, "rrca": 5, "and n": 8,
     "ld bc,nn": 11, "inc a": 5, "jr_taken": 13, "jr_not": 8, "sbc hl,rr": 17}


def t_add32(n=4):
    """one call of add32 or sub32: CALL, LD B,n, OR A, n turns of the loop
    (n - 1 DJNZs taken, one not), RET"""
    turn = T["ld a,(de)"] + T["adc a,(hl)"] + T["ld (de),a"] + T["inc de"] + T["inc hl"]
    return T["call"] + T["ld r,n"] + T["or a"] + n * turn + (n - 1) * T["djnz"] + \
        T["djnz_last"] + T["ret"]


def t_times10():
    return T["call"] + 2 * T["ld r,r"] + 4 * T["add hl,rr"] + T["ret"]


def t_bcd_sum():
    # LD HL,nn; then per byte LD A,(HL), ADD/ADC A,n, DAA, LD (HL),A; two DEC HL
    return T["ld hl,nn"] + 3 * (T["ld a,(hl)"] + T["add a,n"] + T["daa"] + T["ld (hl),a"]) + \
        2 * T["dec hl"]


def t_bin_sum():
    return T["ld hl,(nn)"] + T["ld de,nn"] + T["add hl,rr"] + T["ld (nn),hl"]


def t_bcdtxt():
    turn = (T["ld a,(hl)"] + 4 * T["rrca"] + T["and n"] + T["add a,n"] + T["ld (de),a"] +
            T["inc de"] + T["ld a,(hl)"] + T["and n"] + T["add a,n"] + T["ld (de),a"] +
            T["inc de"] + T["inc hl"])
    return T["call"] + 2 * T["ld hl,nn"] + T["ld r,n"] + 3 * turn + 2 * T["djnz"] + \
        T["djnz_last"] + T["ret"]


def t_bintxt(n):
    def digit(d):
        # LD A,n; d+1 times INC A and ADD HL,BC; d JRs taken and one not;
        # SBC HL,BC; LD (DE),A; INC DE; RET
        return (T["ld r,n"] + (d + 1) * (T["inc a"] + T["add hl,rr"]) + d * T["jr_taken"] +
                T["jr_not"] + T["sbc hl,rr"] + T["ld (de),a"] + T["inc de"] + T["ret"])
    digits = [int(c) for c in f"{n:05d}"]
    return (T["call"] + T["ld hl,(nn)"] + T["ld de,nn"] +
            sum(T["ld bc,nn"] + T["call"] + digit(d) for d in digits[:4]) +
            T["ld r,r"] + T["add a,n"] + T["ld (de),a"] + T["ret"])


# ---------------------------------------------------------------- cost
def cost():
    s = sym("cost")
    n = len(gen09.COST)
    labels = {f"t{k}": s[f"t{k}"] for k in range(n + 1)}
    got = probe.times(rom("cost"), labels)
    data = rom("cost").read_bytes()
    rows = []
    for k, ins in enumerate(gen09.COST):
        (t0, r0), (t1, r1) = got[f"t{k}"][0][:2], got[f"t{k + 1}"][0][:2]
        t, dr = round((t1 - t0) * CLOCK), (r1 - r0) % 128
        z, m1 = ZILOG[ins]
        assert t == z + m1 and dr == m1, (ins, t, dr, z, m1)
        a0, a1 = labels[f"t{k}"], labels[f"t{k + 1}"]
        rows.append({"instr": ins, "bytes": list(data[a0 - 0x4000:a1 - 0x4000]), "t": t,
                     "zilog": z})
    return {"rows": rows}


# ---------------------------------------------------------------- hist
def hist():
    n = len(gen09.HIST_OPS)
    v = probe.memory(rom("hist"), sym("hist")["stop"], gen09.TABLE, 512 * n, frames=420)
    out = {}
    for k, (name, _) in enumerate(gen09.HIST_OPS):
        lo, hi = v[512 * k: 512 * k + 256], v[512 * k + 256: 512 * k + 512]
        got = [l + 256 * h for l, h in zip(lo, hi)]
        want = [0] * 256
        f_of = HIST_MODEL[name]
        for a in range(256):
            for b in range(256):
                want[f_of(a, b)[1]] += 1
        assert got == want, (name, [(i, g, w) for i, (g, w) in enumerate(zip(got, want)) if g != w][:5])
        assert sum(got) == 65536
        flags = {fl: sum(c for f, c in enumerate(got) if f & bit)
                 for fl, bit in (("S", 0x80), ("Z", 0x40), ("5", 0x20), ("H", 0x10),
                                 ("3", 0x08), ("V", 0x04), ("N", 0x02), ("C", 0x01))}
        out[name] = {"counts": got, "flags": flags, "values": sum(1 for c in got if c)}
    return out


# ---------------------------------------------------------------- neg
def neg():
    v = probe.memory(rom("neg"), sym("neg")["stop"], gen09.TABLE, 512)
    same, c_set, v_set, z_set = [], 0, [], []
    for a in range(256):
        got = (v[2 * a], v[2 * a + 1])
        want = sub8(0, a, 0)
        assert got == want, (a, got, want)
        if got[0] == a:
            same.append(a)
        c_set += got[1] & 1
        if got[1] & 0x04:
            v_set.append(a)
        if got[1] & 0x40:
            z_set.append(a)
    return {"cases": 256, "same": same, "c_set": c_set, "v_set": v_set, "z_set": z_set}


# ---------------------------------------------------------------- times10
def times10():
    s = sym("times10")
    n = len(gen09.TIMES10)
    v = probe.memory(rom("times10"), s["stop"], RESULTS, 4 * n)
    rows = []
    for k, x in enumerate(gen09.TIMES10):
        hl, carry = v[4 * k] | v[4 * k + 1] << 8, v[4 * k + 2]
        assert hl == (10 * x) & 0xFFFF, (x, hl)
        # the carry of the last ADD HL,HL: 5x doubled past 65,535
        assert carry == (1 if 2 * ((5 * x) & 0xFFFF) > 0xFFFF else 0), (x, carry)
        rows.append({"x": x, "hl": hl, "carry": carry})
    got = probe.times(rom("times10"), {"c0": s["c0"], "after": s["c0"] + 3})
    t = round((got["after"][0][0] - got["c0"][0][0]) * CLOCK)
    assert t == t_times10(), (t, t_times10())
    return {"rows": rows, "call_t": t}


# ---------------------------------------------------------------- add32
def add32():
    png = finished("add32", 10)
    page = screentext.Page(png)
    lines = []
    for k, (a, op, b) in enumerate(gen09.SUMS32):
        r = a + b if op == "+" else a - b
        carry = 1 if (r > 0xFFFFFFFF or r < 0) else 0
        r &= 0xFFFFFFFF
        want = f"{a:08X}{op}{b:08X}={r:08X}".ljust(gen09.CARRY_COL) + f"C={carry}"
        got = page.line(gen09.SUM_ROW0 + gen09.SUM_STEP * k).rstrip()
        assert got == want, (k, got, want)
        lines.append({"a": a, "op": op, "b": b, "result": r, "carry": carry, "text": got})
    s = sym("add32")
    k_sub = next(k for k, (_, op, _) in enumerate(gen09.SUMS32) if op == "-")
    got = probe.times(rom("add32"), {"a0": s["c0"], "a1": s["c0"] + 3,
                                     "s0": s[f"c{k_sub}"], "s1": s[f"c{k_sub}"] + 3},
                      frames=10)
    calls = [round((got["a1"][0][0] - got["a0"][0][0]) * CLOCK),
             round((got["s1"][0][0] - got["s0"][0][0]) * CLOCK)]
    assert calls == [t_add32()] * 2, (calls, t_add32())
    return {"lines": lines, "call_t": calls[0], "bytes_add32": s["sub32"] - s["add32"],
            "frame": 10}


# ---------------------------------------------------------------- hl16
def hl16():
    s = sym("hl16")
    v = probe.memory(rom("hl16"), s["stop"], RESULTS, 4 * len(gen09.HL16))
    rows = []
    for k, (code, hl, de, f) in enumerate(gen09.HL16):
        got = (v[4 * k] | v[4 * k + 1] << 8, v[4 * k + 2])
        want = run16(code, hl, de, f)
        assert got == want, (code, hex(hl), hex(de), hex(f), [hex(x) for x in got],
                             [hex(x) for x in want])
        rows.append({"code": code, "hl": hl, "de": de, "f_before": f,
                     "hl_after": got[0], "f_after": got[1]})
    e = console.session(rom("hl16"), ["reg hl", "reg f", "format %08b [reg f]"], start=s["first"])
    assert int(e[0][1]) == rows[0]["hl_after"] and int(e[1][1]) == rows[0]["f_after"]
    return {"rows": rows, "session": keep("hl16", e)}


# ---------------------------------------------------------------- stale
def stale():
    s = sym("stale")
    got = probe.times(rom("stale"), {"p1": s["p1"], "p2": s["p2"]}, extra="[reg hl]")
    left, cleared = int(got["p1"][0][2]), int(got["p2"][0][2])
    assert left == 0x1000 - 0x0001 - 1 and cleared == 0x1000 - 0x0001
    return {"left": left, "cleared": cleared}


# ---------------------------------------------------------------- widen
def widen():
    v = probe.memory(rom("widen"), sym("widen")["stop"], RESULTS, 4 * len(gen09.WIDEN))
    rows = []
    for k, (p, vel) in enumerate(gen09.WIDEN):
        right, wrong = v[4 * k] | v[4 * k + 1] << 8, v[4 * k + 2] | v[4 * k + 3] << 8
        assert right == (p + vel) & 0xFFFF and wrong == (p + (vel & 0xFF)) & 0xFFFF
        rows.append({"pos": p, "vel": vel, "byte": vel & 0xFF, "right": right, "wrong": wrong})
    return {"rows": rows}


# ---------------------------------------------------------------- daa
def daa():
    n = 256 * len(gen09.DAA_FLAGS)
    v = probe.memory(rom("daa"), sym("daa")["stop"], gen09.TABLE, 2 * n)
    agree, table = 0, {}
    for i in range(n):
        f, a = gen09.DAA_FLAGS[i // 256], i % 256
        got = (v[2 * i], v[2 * i + 1])
        want = daa_model(a, f)
        assert got == want, (hex(a), hex(f), [hex(x) for x in got], [hex(x) for x in want])
        agree += 1
        table[f"{a:02X}/{f:02X}"] = got
    ex = {}
    for k, (a, op, b) in {"19+28": (0x19, "+", 0x28), "37+74": (0x37, "+", 0x74),
                          "99+01": (0x99, "+", 0x01), "42+17": (0x42, "+", 0x17),
                          "42-17": (0x42, "-", 0x17), "19-28": (0x19, "-", 0x28)}.items():
        res, f = add8(a, b, 0) if op == "+" else sub8(a, b, 0)
        f &= 0x13                                  # what DAA reads: N, H, C
        after, f2 = table[f"{res:02X}/{f:02X}"]
        ex[k] = {"binary": res, "h": (f >> 4) & 1, "c": f & 1, "after": after, "carry": f2 & 1}
    return {"cases": n, "agree": agree, "examples": ex}


# ---------------------------------------------------------------- score
def score():
    n = gen09.FRAMES
    png = finished("score", n + 15)
    page = screentext.Page(png)
    rows = []
    for k in range(1, n + 1):
        total = gen09.POINTS * k
        want = {"bcd": f"{total:06d}", "hex": f"{total:04X}", "dec": f"{total:05d}"}
        line = page.line(gen09.SCORE_ROW0 + k - 1)
        got = {"bcd": line[gen09.COL_BCD:gen09.COL_BCD + 6],
               "hex": line[gen09.COL_HEX:gen09.COL_HEX + 4],
               "dec": line[gen09.COL_DEC:gen09.COL_DEC + 5]}
        assert got == want, (k, got, want)
        rows.append(total)
    assert page.line(0).split() == ["BCD", "HEX", "DECIMAL"], page.line(0)
    s = sym("score")
    labels = {k: s[k] for k in ("bcdsum", "binsum", "t1", "t2", "t3")}
    # bcdsum follows HALT, and openMSX stops there while the HALT is still
    # waiting too: the time of a frame's sum is the last stop before binsum
    got = probe.times(rom("score"), labels, frames=n + 10, hits=10 * n)
    frames = []
    for k in range(n):
        b, c, d, e = (got[lab][k][0] for lab in ("binsum", "t1", "t2", "t3"))
        a = max(t for t, *_ in got["bcdsum"] if t < b)
        t = [round((b - a) * CLOCK), round((c - b) * CLOCK), round((d - c) * CLOCK),
             round((e - d) * CLOCK)]
        total = gen09.POINTS * (k + 1)
        want = [t_bcd_sum(), t_bin_sum(), t_bcdtxt(), t_bintxt(total)]
        assert t == want, (k, t, want)
        frames.append({"total": total, "bcd_sum": t[0], "bin_sum": t[1], "bcdtxt": t[2],
                       "bintxt": t[3]})
    return {"totals": rows, "frames": frames, "frame": n + 15,
            "bintxt_range": [min(f["bintxt"] for f in frames), max(f["bintxt"] for f in frames)]}


# ---------------------------------------------------------------- answers
ANSWERS = """        ld bc, $8001
        push bc
        pop af                  ; A = $80, the carry set
        ld b, $80
        add a, b
        push af
        pop hl
        ld (RESULTS), hl        ; question 1: ADD A,B
        ld bc, $8001
        push bc
        pop af
        ld b, $80
        adc a, b
        push af
        pop hl
        ld (RESULTS + 2), hl    ; question 1: ADC A,B
        ld a, $15
        add a, $27
        push af
        pop hl
        ld (RESULTS + 4), hl    ; question 5: $15 + $27 before DAA
        daa
        push af
        pop hl
        ld (RESULTS + 6), hl    ; and after
"""


def build_temp(name, text):
    tmp = Path(tempfile.mkdtemp(prefix=f"{name}_"))
    (tmp / f"{name}.asm").write_text(text)
    shutil.copy(HERE / "msx.inc", tmp)
    subprocess.run(["sjasmplus", "--nologo", "--msg=err", "--syntax=bF", f"--sym={name}.sym",
                    f"{name}.asm"], cwd=tmp, check=True)
    return tmp


def answers():
    out = {}
    tmp = build_temp("answers", gen09.cart("answers", "the workshop", ANSWERS))
    try:
        v = probe.memory(tmp / "answers.rom", probe.sym(tmp / "answers.sym")["stop"], RESULTS, 8)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    out["q1"] = {"add": {"a": v[1], "f": v[0]}, "adc": {"a": v[3], "f": v[2]}}
    assert (v[1], v[0]) == add8(0x80, 0x80, 0) and (v[3], v[2]) == add8(0x80, 0x80, 1)
    out["q5"] = {"binary": v[5], "f_before": v[4], "after": v[7], "f_after": v[6]}
    assert v[7] == daa_model(v[5], v[4])[0] and v[6] == daa_model(v[5], v[4])[1]
    # question 2: add32 on 24 bits
    src = (HERE / "add32.asm").read_text().replace("add32:  ld b, 4", "add32:  ld b, 3")
    tmp = build_temp("add32", src)
    try:
        s = probe.sym(tmp / "add32.sym")
        got = probe.times(tmp / "add32.rom", {"a0": s["c0"], "a1": s["c0"] + 3})
        out["q2_t"] = round((got["a1"][0][0] - got["a0"][0][0]) * CLOCK)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    assert out["q2_t"] == t_add32(3)
    # question 6: C and V both, in all 65,536 ADD A,E
    out["q6"] = sum(1 for a in range(256) for b in range(256)
                    if add8(a, b, 0)[1] & 0x05 == 0x05)
    return out


# ---------------------------------------------------------------- openmsx
OPENMSX_SECTIONS = ["cost", "hist", "neg", "times10", "add32", "hl16", "stale", "widen",
                    "daa", "score", "answers"]


def openmsx():
    if not versions.builds():
        return {"skipped": "OPENMSX_BUILDS not set"}
    return versions.every_build(["ch09"], OPENMSX_SECTIONS)


SECTIONS = {"cost": cost, "hist": hist, "neg": neg, "times10": times10, "add32": add32,
            "hl16": hl16, "stale": stale, "widen": widen, "daa": daa, "score": score,
            "answers": answers, "openmsx": openmsx}


def main(names=()):
    CAPS.mkdir(exist_ok=True)
    path = HERE / "meas09.json"
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
