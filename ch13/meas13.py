#!/usr/bin/env python3
"""meas13.py -- blocks, tables and the index registers, measured.

    python3 gen13.py && ./build.sh && python3 meas13.py
                                  python3 meas13.py copy cost    only these
                                  python3 meas13.py --missing    those not measured yet

The models: Python's own copies, searches, bit reversals and products;
Zilog's T-states plus one for every M1 (chapters 3 and 7), added up along
the path each program takes; Graphic II's layout (chapter 22).

  copy      three copies timed and read back; the registers and flags LDIR
            and LDI leave; a block filled by LDIR
  overlap   figure 13.1 read back from the screen against Python's copies
  cpir      four searches: the time, HL, BC and the flags
  flip      the table and both sets of 32 bytes; the three times
  lines     the 384 bytes of the tables; the three times
  sine      figure 13.2 read back pixel by pixel against the table of heights
  qsmul     the table, eight products and their times, the sum of all 65,536
  moire     figure 13.3 read back pixel by pixel against Python's products
  cost      every block instruction and the halves of IX, timed one by one
  otir      the turns of OTIR timed; the 256 bytes read back from the VRAM
  answers   the workshop, tried: questions 1, 2, 3, 5 and 6 (for Appendix I)
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
import gen13       # noqa: E402

CAPS = HERE / "captures"
CLOCK = probe.CLOCK
RESULTS = 0xC000


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


def inks(png):
    """{(x, y): 1 or 0} for every pixel of the paper, 1 where the ink is"""
    px = Image.open(png).convert("RGB").load()
    out = {}
    for y in range(192):
        for x in range(256):
            sx, sy = meas.paper(x, y)
            out[(x, y)] = 1 if sum(px[sx, sy]) < 384 else 0
    return out


def build_temp(name, text):
    tmp = Path(tempfile.mkdtemp(prefix=f"{name}_"))
    (tmp / f"{name}.asm").write_text(text)
    shutil.copy(HERE / "msx.inc", tmp)
    subprocess.run(["sjasmplus", "--nologo", "--msg=err", "--syntax=bF", f"--sym={name}.sym",
                    f"{name}.asm"], cwd=tmp, check=True)
    return tmp


def vram_block(rom_path, stop, start, n, frames=3):
    """n bytes of the VRAM from start when the program first reaches stop"""
    lines = probe.at_address(rom_path, stop, f'binary scan [debug read_block VRAM {start} {n}] H* h; '
                                             'L "vram $h"', frames)
    return list(bytes.fromhex(next(l for l in lines if l.startswith("vram ")).split()[1]))


def word(v, a):
    return v[a] | v[a + 1] << 8


# ---------------------------------------------------------------- the models
T = {"call": 18, "ret": 11, "ld rr,nn": 11, "ld r,n": 8, "ld r,r": 5, "ld r,(hl)": 8,
     "ld (rr),a": 8, "inc rr": 7, "inc r": 5, "djnz": 14, "djnz_last": 9, "jr": 13, "jr_not": 8,
     "jp": 11, "cp n": 8, "and n": 8, "rrca": 5, "push": 12, "pop": 11, "rr r": 10, "rla": 5,
     "srl r": 10, "add hl,rr": 12, "alu r": 5, "neg": 10, "sbc hl,rr": 17, "ldi": 18,
     "ldir": 23, "ld iy,nn": 16, "ld xh,n": 13, "ld r,xh": 10, "inc xh": 10,
     "ld r,(iy+d)": 21, "ld (iy+d),r": 21, "inc (iy+d)": 25}
T_MIRROR = (T["call"] + T["ld r,r"] + T["ld r,n"] + 8 * (T["rr r"] + T["rla"] + T["djnz"]) -
            (T["djnz"] - T["djnz_last"]) + T["ret"])           # chapter 10: 269
DOC = 0xD7                  # S Z . H . P/V N C: the flags Zilog documents


def loop(n, body, last_saving):
    """n turns of a body, the last one cheaper by last_saving"""
    return n * body - last_saving


# ---------------------------------------------------------------- copy
def t_loopcp():
    return (T["call"] + 2 * T["ld rr,nn"] + T["ld r,n"] +
            loop(256, T["ld r,(hl)"] + T["ld (rr),a"] + 2 * T["inc rr"] + T["djnz"],
                 T["djnz"] - T["djnz_last"]) + T["ret"])


def t_ldircp():
    return T["call"] + 3 * T["ld rr,nn"] + T["ldir"] * 255 + T["ldi"] + T["ret"]


def t_ldicp():
    return T["call"] + 3 * T["ld rr,nn"] + 16 * (16 * T["ldi"] + T["jp"]) + T["ret"]


REGS = "[reg af] [reg bc] [reg de] [reg hl]"


def copy():
    s = sym("copy")
    labels = ["c1", "c2", "c3", "c4", "f1", "f2", "l1", "l2", "l3", "fl1", "fl2"]
    got = probe.times(rom("copy"), {k: s[k] for k in labels}, frames=4, extra=REGS)
    g = {k: (got[k][0][0], *[int(x) for x in got[k][0][2:]]) for k in labels}
    t_loop, t_ldir, t_ldi = (tstates(g[a][0], g[b][0]) for a, b in (("c1", "c2"), ("c2", "c3"),
                                                                      ("c3", "c4")))
    assert (t_loop, t_ldir, t_ldi) == (t_loopcp(), t_ldircp(), t_ldicp()), (t_loop, t_ldir, t_ldi)
    src = [(gen13.STEP * k) & 0xFF for k in range(256)]
    stop = s["stop"]
    dst = probe.block(rom("copy"), stop, gen13.DST[0], 768, frames=4)
    assert dst == src * 3
    flags_mem = probe.block(rom("copy"), stop, gen13.FLAGS_AT, 4, frames=4)
    assert flags_mem == src[:4]
    af0 = g["f1"][1]
    af1, bc1, de1, hl1 = g["f2"][1:]
    assert af0 & 0xFF == 0xFF and (af1 & DOC) == 0xC1, hex(af1)       # S, Z, C kept; H, P/V, N 0
    assert (bc1, de1, hl1) == (0, gen13.FLAGS_AT + 4, gen13.SRC + 4)
    (fa, ba), (fb, bb), (fc, bc_) = ((g[k][1] & 0xFF, g[k][2]) for k in ("l1", "l2", "l3"))
    assert (ba, bb, bc_) == (2, 1, 0)
    assert (fb & DOC) == (fa & 0xC1) | 0x04 and (fc & DOC) == (fb & 0xC1), (hex(fb), hex(fc))
    t_fill = tstates(g["fl1"][0], g["fl2"][0])
    assert t_fill == T["ld rr,nn"] + T["ldir"] * (gen13.FILL_LEN - 2) + T["ldi"], t_fill
    fill = probe.block(rom("copy"), stop, gen13.FILL_AT, gen13.FILL_LEN, frames=4)
    assert fill == [gen13.FILL_BYTE] * gen13.FILL_LEN
    return {"loop": t_loop, "ldir": t_ldir, "ldi": t_ldi, "bytes": 256,
            "ldir_f": af1 & 0xFF, "ldi_f": [fb, fc], "after": {"bc": bc1, "de": de1, "hl": hl1},
            "fill": {"t": t_fill - T["ld rr,nn"], "len": gen13.FILL_LEN, "byte": gen13.FILL_BYTE},
            "per": {"ldir": T["ldir"], "ldi": T["ldi"],
                    "loop": T["ld r,(hl)"] + T["ld (rr),a"] + 2 * T["inc rr"] + T["djnz"]}}


# ---------------------------------------------------------------- overlap
OVERLAP_FRAME = 10


def overlap():
    png = finished("overlap", OVERLAP_FRAME)
    page = screentext.Page(png)
    line = list(gen13.SAMPLE + " ")
    fwd = line[:]
    for i in range(gen13.OV_W - 1):             # LDIR: from the left end
        fwd[i + 1] = fwd[i]
    back = line[:]
    for i in range(gen13.OV_W - 2, -1, -1):     # LDDR: from the right end
        back[i + 1] = back[i]
    want = dict(zip(gen13.OV_ROWS, ("".join(line), "".join(fwd), "".join(back))))
    for r, t in gen13.OV_LABELS:
        assert page.line(r).rstrip() == t, (r, page.line(r))
    for r, t in want.items():
        assert page.line(r) == t, (r, page.line(r), t)
    return {"rows": {str(r): t for r, t in want.items()}, "frame": OVERLAP_FRAME}


# ---------------------------------------------------------------- cpir
def cpir():
    s = sym("cpir")
    n = len(gen13.FIND)
    got = probe.times(rom("cpir"), {f"{p}{k}": s[f"{p}{k}"] for k in range(n) for p in "se"},
                      extra=REGS)
    rows = []
    for k, target in enumerate(gen13.FIND):
        t = tstates(got[f"s{k}"][0][0], got[f"e{k}"][0][0]) - T["ld rr,nn"]
        af, bc, de, hl = (int(x) for x in got[f"e{k}"][0][2:])
        pos = gen13.LIST.index(target) if target in gen13.LIST else None
        looked = pos + 1 if pos is not None else gen13.LIST_LEN
        f = af & 0xFF
        z, pv, nf, c = bool(f & 0x40), bool(f & 0x04), bool(f & 0x02), bool(f & 0x01)
        assert t == T["ldir"] * (looked - 1) + T["ldi"], (k, t)
        assert hl == s["list"] + looked and bc == gen13.LIST_LEN - looked
        assert z == (pos is not None) and pv == (bc != 0) and nf and c, (k, hex(f))
        rows.append({"value": target, "at": pos, "looked": looked, "t": t, "z": int(z),
                     "pv": int(pv), "bc": bc, "hl_past": hl - s["list"]})
    return {"rows": rows, "list": gen13.LIST_LEN, "per": T["ldir"], "last": T["ldi"]}


# ---------------------------------------------------------------- flip
def mirrored(b):
    return int(f"{b:08b}"[::-1], 2)


def flip():
    s = sym("flip")
    got = probe.times(rom("flip"), {f"t{k}": s[f"t{k}"] for k in range(6)}, frames=4)
    ts = [got[f"t{k}"][0][0] for k in range(6)]
    table = probe.block(rom("flip"), s["stop"], gen13.MIRRORS, 256, frames=4)
    both = probe.block(rom("flip"), s["stop"], gen13.SPRITE_RAM, 64, frames=4)
    assert table == [mirrored(n) for n in range(256)]
    want = [mirrored(x) for x in gen13.SPRITE]
    assert both == want * 2
    make, rout, tab = tstates(ts[0], ts[1]), tstates(ts[2], ts[3]), tstates(ts[4], ts[5])
    assert make == (T["call"] + T["ld rr,nn"] +
                    loop(256, T["ld r,r"] + T_MIRROR + T["ld (rr),a"] + T["inc r"] + T["jr"],
                         T["jr"] - T["jr_not"]) + T["ret"]), make
    assert rout == (T["call"] + loop(32, T["ld r,(hl)"] + T["push"] + T_MIRROR + T["pop"] +
                                     T["ld (rr),a"] + T["inc rr"] + T["djnz"],
                                     T["djnz"] - T["djnz_last"]) + T["ret"]), rout
    assert tab == (T["call"] + T["ld r,n"] +
                   loop(32, T["ld r,(hl)"] + T["ld r,r"] + T["ld r,(hl)"] + T["ld (rr),a"] +
                        T["inc rr"] + T["djnz"], T["djnz"] - T["djnz_last"]) + T["ret"]), tab
    return {"make": make, "routine": rout, "table": tab, "bytes": 32, "mirror_call": T_MIRROR}


# ---------------------------------------------------------------- lines
def g2_line(y):
    """the address in Graphic II's patterns of pixel line y at the left edge"""
    return (y >> 3) * 256 + (y & 7)


T_CALC = (T["call"] + T["ld r,r"] + T["and n"] + T["ld r,r"] + T["ld r,r"] + 3 * T["rrca"] +
          T["and n"] + T["ld r,r"] + T["ret"])
T_LINE = (T["call"] + T["ld r,r"] + T["ld r,n"] + T["ld r,(hl)"] + T["inc r"] + T["ld r,(hl)"] +
          T["ld r,r"] + T["ret"])


def lines():
    s = sym("lines")
    got = probe.times(rom("lines"), {f"l{k}": s[f"l{k}"] for k in range(4)}, frames=4)
    ts = [got[f"l{k}"][0][0] for k in range(4)]
    mem = probe.block(rom("lines"), s["stop"], gen13.LINES, 512, frames=4)
    for y in range(192):
        assert mem[y] | mem[256 + y] << 8 == g2_line(y), y
    make, look, calc = tstates(ts[0], ts[1]), tstates(ts[1], ts[2]), tstates(ts[2], ts[3])
    tail = T["inc r"] + T["ld r,r"] + T["cp n"] + T["jr"]           # INC E, LD A,E, CP, JR NZ
    last = T["jr"] - T["jr_not"]
    assert make == (T["call"] + T["ld r,n"] +
                    loop(192, T["ld r,r"] + T_CALC + T["ld r,n"] + T["ld r,r"] + T["ld (rr),a"] +
                         T["inc r"] + T["ld r,r"] + T["ld (rr),a"] + tail, last) + T["ret"]), make
    assert look == T["ld r,n"] + loop(192, T["ld r,r"] + T_LINE + tail, last), look
    assert calc == T["ld r,n"] + loop(192, T["ld r,r"] + T_CALC + tail, last), calc
    return {"make": make, "look": look, "calc": calc, "line_t": T_LINE, "calc_t": T_CALC,
            "lines": 192}


# ---------------------------------------------------------------- sine
SINE_FRAME = 20


def sine():
    png = finished("sine", SINE_FRAME)
    got = inks(png)
    for (x, y), v in got.items():
        assert v == (gen13.SINE[x] == y), (x, y)
    return {"ink": sum(got.values()), "low": min(gen13.SINE), "high": max(gen13.SINE),
            "frame": SINE_FRAME}


# ---------------------------------------------------------------- qsmul
def sq4(n):
    return n * n // 4


T_MUL_HEAD = (T["call"] + T["ld r,r"] + T["alu r"] + T["ld r,r"] + T["ld r,n"] + T["ld r,n"] +
              T["ld r,r"] + T["ld r,(hl)"] + 2 * T["inc r"] + T["ld r,(hl)"] + T["ld r,r"] +
              T["alu r"])
T_MUL_TAIL = (T["ld r,r"] + T["ld r,n"] + T["ld r,(hl)"] + 2 * T["inc r"] + T["ld r,(hl)"] +
              2 * T["ld r,r"] + T["alu r"] + T["sbc hl,rr"] + T["ret"])


def t_mul(a, e):
    return T_MUL_HEAD + (T["jr"] if a >= e else T["jr_not"] + T["neg"]) + T_MUL_TAIL


def t_sqinit():
    turn = (T["ld r,r"] + T["ld (rr),a"] + 2 * T["inc r"] + T["ld r,r"] + T["ld (rr),a"] +
            2 * T["inc r"] + T["inc rr"] + T["push"] + T["srl r"] + T["rr r"] + T["add hl,rr"] +
            T["pop"] + T["inc rr"] + T["ld r,r"] + T["cp n"] + T["jr"])
    return T["call"] + 3 * T["ld rr,nn"] + loop(511, turn, T["jr"] - T["jr_not"]) + T["ret"]


def t_sumall():
    t = T["call"] + T["ld iy,nn"] + T["ld xh,n"]
    total = 0
    for a in range(256):
        t += T["ld xh,n"]
        for e in range(256):
            t += (2 * T["ld r,xh"] + t_mul(a, e) + 2 * (T["ld r,(iy+d)"] + T["alu r"] +
                                                       T["ld (iy+d),r"]))
            low = (total & 0xFFFF) + a * e
            total += a * e
            if low < 0x10000:
                t += T["jr"]                            # JR NC jumps
            else:
                t += T["jr_not"] + T["inc (iy+d)"]
                t += T["jr"] if (total >> 16) & 0xFF else T["jr_not"] + T["inc (iy+d)"]
            t += T["inc xh"] + (T["jr"] if e < 255 else T["jr_not"])
        t += T["inc xh"] + (T["jr"] if a < 255 else T["jr_not"])
    return t + T["ret"], total


QSMUL_FRAMES = 420


def qsmul():
    s = sym("qsmul")
    n = len(gen13.MUL_PAIRS)
    marks = {k: s[k] for k in ("q0", "q1", "s0", "s1")}
    marks |= {f"{p}{k}": s[f"{p}{k}"] for k in range(n) for p in "mn"}
    got = probe.times(rom("qsmul"), marks, frames=QSMUL_FRAMES, extra="[reg hl]")
    t_init = tstates(got["q0"][0][0], got["q1"][0][0])
    assert t_init == t_sqinit(), (t_init, t_sqinit())
    prods = []
    for k, (a, e) in enumerate(gen13.MUL_PAIRS):
        t = tstates(got[f"m{k}"][0][0], got[f"n{k}"][0][0])
        hl = int(got[f"n{k}"][0][2])
        assert hl == a * e and t == t_mul(a, e), (a, e, hl, t, t_mul(a, e))
        prods.append({"a": a, "e": e, "hl": hl, "t": t})
    t_sum = tstates(got["s0"][0][0], got["s1"][0][0])
    v = probe.memory(rom("qsmul"), s["stop"], RESULTS, 4, frames=QSMUL_FRAMES)
    total = v[0] | v[1] << 8 | v[2] << 16 | v[3] << 24
    want_t, want_total = t_sumall()
    assert total == want_total == sum(range(256)) ** 2, (total, want_total)
    assert t_sum == want_t, (t_sum, want_t)
    mem = probe.block(rom("qsmul"), s["stop"], gen13.SQ, 1024, frames=QSMUL_FRAMES)
    lo, hi = mem[:512], mem[512:]
    for k in range(511):
        assert lo[k] | hi[k] << 8 == sq4(k), k
    return {"init": t_init, "products": prods, "sum": total, "sum_t": t_sum, "pairs": 65536,
            "per_pair": round(t_sum / 65536, 1), "mul_t": sorted({p["t"] for p in prods}),
            "after_511": [lo[511], hi[511]]}


# ---------------------------------------------------------------- moire
MOIRE_FRAME = 280


def moire():
    png = finished("moire", MOIRE_FRAME)
    got = inks(png)
    for (x, y), v in got.items():
        assert v == (x * y >> gen13.MOIRE_BIT) & 1, (x, y)
    return {"pixels": len(got), "ink": sum(got.values()), "bit": gen13.MOIRE_BIT,
            "frame": MOIRE_FRAME}


# ---------------------------------------------------------------- cost
SINGLE = {"ldi": 18, "ldd": 18, "cpi": 18, "cpd": 18, "ini": 18, "ind": 18, "outi": 18,
          "outd": 18, "ld ixh, $12": 13, "ld ixl, $34": 13, "ld a, ixh": 10, "ld e, ixl": 10,
          "inc ixh": 10, "dec ixl": 10, "add a, ixl": 10, "cp ixh": 10, "nop": 5,
          "ld bc, 2": 11, "ld bc, 4": 11, "ld bc, $0498": 11, "ld b, 2": 8, "ld b, 4": 8}
REPEAT = {"ldir", "lddr", "cpir", "cpdr", "inir", "indr", "otir", "otdr"}


def cost():
    s = sym("cost")
    labels = [lab for lab, _, _ in gen13.COST if lab]
    got = probe.times(rom("cost"), {lab: s[lab] for lab in labels + ["stop"]}, hits=3)
    events = sorted((t, lab) for lab in got for t, *_ in got[lab])
    events = events[:events.index(next(e for e in events if e[1] == "stop")) + 1]
    # the instructions without a label between one label and the next
    after = {}
    cur = None
    for lab, ins, _ in gen13.COST:
        if lab:
            cur = lab
            after[cur] = []
        else:
            after[cur].append(ins)
    ins_of = {lab: ins for lab, ins, _ in gen13.COST if lab}
    rows = []
    for (t0, lab), (t1, nxt) in zip(events, events[1:]):
        ins, t = ins_of[lab], tstates(t0, t1)
        again = nxt == lab
        if not again:
            t -= sum(SINGLE[x] for x in after[lab])
        want = (T["ldir"] if again else T["ldi"]) if ins in REPEAT else SINGLE[ins]
        assert t == want, (ins, t, want)
        rows.append({"instr": ins, "t": t, "again": again})
    assert len([r for r in rows if not r["again"]]) == len(labels)
    assert all(sum(1 for r in rows if r["instr"] == x and r["again"]) == 1 for x in REPEAT)
    return {"rows": rows}


# ---------------------------------------------------------------- otir
def otir():
    s = sym("otir")
    got = probe.times(rom("otir"), {"o1": s["o1"], "o2": s["o2"]}, frames=4, hits=300)
    turns = [x[0] for x in got["o1"]]
    gaps = sorted({tstates(a, b) for a, b in zip(turns, turns[1:])})
    last = tstates(turns[-1], got["o2"][0][0])
    total = tstates(turns[0], got["o2"][0][0])
    assert len(turns) == 256 and gaps == [T["ldir"]] and last == T["ldi"], (len(turns), gaps, last)
    vram = vram_block(rom("otir"), s["stop"], gen13.OTIR_AT, 256, frames=4)
    assert vram == list(range(256))
    return {"turns": len(turns), "gap": gaps[0], "last": last, "total": total, "bytes": 256}


# ---------------------------------------------------------------- answers
BLK = [0x55, 1, 2, 3, 4, 5, 6, 0x55] + list(range(8, 20)) + [0x55] + list(range(21, 39)) + [0x55]
ANSWERS = f"""        ld hl, $C000            ; question 1: 6,144 bytes, with LDIR
        ld de, $D800
        ld bc, 6144
a1:     ldir
a2:     ld hl, $C000            ; and with LDI, sixteen at a time
        ld de, $D800
        ld bc, 6144
a3:     DUP 16
        ldi
        EDUP
        jp pe, a3
a4:     ld hl, $E000 + 99       ; question 2: 100 bytes filled from the end
        ld (hl), $77
        ld de, $E000 + 98
        ld bc, 99
        lddr
        ld hl, blk              ; question 3: how many times A is in blk
        ld bc, {len(BLK)}
        ld a, $55
        ld d, 0
cn1:    cpir
        jr nz, cn2              ; not found again: done
        jp po, cn3              ; found, and BC is 0: the last one
        inc d                   ; one more, and on (INC changes P/V:
        jr cn1                  ; it is tested first)
cn3:    inc d
cn2:    ld a, d
        ld (RESULTS), a
        ld hl, $D000            ; question 6: 0 to 99 at $D000 ...
        xor a
q6a:    ld (hl), a
        inc hl
        inc a
        cp 100
        jr nz, q6a
        ld hl, $D000 + 99       ; ... moved to $D010 with LDDR, from the ends
        ld de, $D010 + 99
        ld bc, 100
        lddr
"""


def answers():
    out = {}
    tmp = build_temp("answers", gen13.cart("answers", "the workshop", ANSWERS,
                                           after="blk:    db " + ", ".join(str(b) for b in BLK) + "\n"))
    try:
        r, s = tmp / "answers.rom", probe.sym(tmp / "answers.sym")
        got = probe.times(r, {k: s[k] for k in ("a1", "a2", "a4")}, frames=10)
        cnt = probe.memory(r, s["stop"], RESULTS, 1, frames=10)[0]
        filled = probe.block(r, s["stop"], 0xE000, 100, frames=10)
        moved = probe.block(r, s["stop"], 0xD010, 100, frames=10)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    t_ldir = tstates(got["a1"][0][0], got["a2"][0][0])
    t_ldi = tstates(got["a2"][0][0], got["a4"][0][0]) - 3 * T["ld rr,nn"]
    assert t_ldir == T["ldir"] * 6143 + T["ldi"] and t_ldi == 384 * (16 * T["ldi"] + T["jp"])
    out["q1"] = {"ldir": t_ldir, "ldi": t_ldi}
    assert filled == [0x77] * 100
    out["q2"] = "the last byte first: HL = end, DE = end - 1, BC = length - 1, LDDR"
    assert cnt == BLK.count(0x55) == 4
    out["q3"] = {"count": cnt, "in_last_place": BLK[-1] == 0x55}
    out["q5"] = "511 entries need two pages; the 512th is never written"
    assert moved == list(range(100))
    out["q6"] = {"hl": 0xD000 + 99, "de": 0xD010 + 99, "bc": 100}
    return out


# ---------------------------------------------------------------- openmsx
OPENMSX_SECTIONS = ["copy", "overlap", "cpir", "flip", "lines", "sine", "qsmul", "moire",
                    "cost", "otir", "answers"]


def openmsx():
    if not versions.builds():
        return {"skipped": "OPENMSX_BUILDS not set"}
    return versions.every_build(["ch13"], OPENMSX_SECTIONS)


SECTIONS = {"copy": copy, "overlap": overlap, "cpir": cpir, "flip": flip, "lines": lines,
            "sine": sine, "qsmul": qsmul, "moire": moire, "cost": cost, "otir": otir,
            "answers": answers, "openmsx": openmsx}


def main(names=()):
    CAPS.mkdir(exist_ok=True)
    path = HERE / "meas13.json"
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
