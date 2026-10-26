#!/usr/bin/env python3
"""meas10.py -- logic, bits, shifts and rotates, measured.

    python3 gen10.py && ./build.sh && python3 meas10.py
                                  python3 meas10.py shifts div   only these
                                  python3 meas10.py --missing    those not measured yet

The models: Zilog's rules for the flags, bits 5 and 3 from Sean Young;
Zilog's T-states plus one for every M1 (chapters 3 and 7); Python's own
arithmetic and bit operations; the character shapes of the BIOS file.

  logic     AND, OR and XOR on all 65,536 pairs: how often each value of F
            came out
  sprite    the six panels of figure 10.1 read back pixel by pixel, against
            the same operations in Python; the collision count
  bits      BIT b,A in all 4,096 cases, SET and RES in 96
  cost      bytes, T-states and R of each instruction of the chapter
  rotate    the rows of figure 10.2 read back from the screen
  shifts    the twelve on every A, from F = $00 and $FF: 6,144 cases
  mul       four products timed; all 65,536 summed and mixed
  friction  the three lists of halved speeds
  scroll    the 64 pixel lines of figure 10.3, against the words shifted in
            Python; one call of scroll1 timed
  mirror    the two arrows of figure 10.4; every byte mirrored; the calls timed
  div       five divisions timed against a model that follows the loop bit
            by bit; 0 to 65,535 divided by 10
  bcd       RLD and RRD on four scores, timed
  answers   the workshop, tried: questions 1, 4 and 6 on the MSX (for Appendix I)
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
import gen10       # noqa: E402

CAPS = HERE / "captures"
CLOCK = probe.CLOCK
RESULTS = 0xC000


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


def call_t(name, labels, frames=3, hits=1):
    """the T-states from each label to the instruction after its CALL"""
    s = sym(name)
    got = probe.times(rom(name), {lab: s[lab] for lab in labels} |
                      {lab + "_": s[lab] + 3 for lab in labels}, frames=frames, hits=hits)
    return {lab: [round((b[0] - a[0]) * CLOCK) for a, b in zip(got[lab], got[lab + "_"])]
            for lab in labels}


# ---------------------------------------------------------------- the models
def parity(v):
    return bin(v).count("1") % 2 == 0


def szp(res):
    """S, Z, bits 5 and 3, and P/V as parity, from a result"""
    return (res & 0xA8) | (0x40 if res == 0 else 0) | (0x04 if parity(res) else 0)


def logic8(op, a, b):
    res = {"and": a & b, "or": a | b, "xor": a ^ b}[op]
    return res, szp(res) | (0x10 if op == "and" else 0)       # H set by AND only; N, C 0


def bit_model(b, a, f):
    z = not (a >> b) & 1
    return ((0x80 if b == 7 and a & 0x80 else 0) | (0x40 if z else 0) | (a & 0x28) |
            0x10 | (0x04 if z else 0) | (f & 0x01))


def shift_model(ins, a, f):
    c = f & 1
    op = ins.split()[0]
    if op in ("rlca", "rlc"):
        res, cy = ((a << 1) | (a >> 7)) & 0xFF, a >> 7
    elif op in ("rrca", "rrc"):
        res, cy = (a >> 1) | ((a & 1) << 7), a & 1
    elif op in ("rla", "rl"):
        res, cy = ((a << 1) | c) & 0xFF, a >> 7
    elif op in ("rra", "rr"):
        res, cy = (a >> 1) | (c << 7), a & 1
    elif op == "sla":
        res, cy = (a << 1) & 0xFF, a >> 7
    elif op == "sra":
        res, cy = (a >> 1) | (a & 0x80), a & 1
    elif op == "srl":
        res, cy = a >> 1, a & 1
    elif op == "sll":
        res, cy = ((a << 1) | 1) & 0xFF, a >> 7
    else:
        raise ValueError(ins)
    if op in ("rlca", "rrca", "rla", "rra"):
        fl = (f & 0xC4) | (res & 0x28) | cy          # S, Z and P/V kept; H, N cleared
    else:
        fl = szp(res) | cy
    return res, fl


# Zilog's T-states and M1 cycles; the MSX adds one T-state to every M1
ZILOG = {"and b": (4, 1), "or $0f": (7, 1), "xor (hl)": (7, 1), "cpl": (4, 1),
         "scf": (4, 1), "ccf": (4, 1), "bit 3,a": (8, 2), "set 3,a": (8, 2),
         "bit 3,(hl)": (12, 2), "set 3,(hl)": (15, 2), "res 3,(ix+2)": (23, 2),
         "rlca": (4, 1), "rrca": (4, 1), "rla": (4, 1), "rra": (4, 1), "rlc a": (8, 2),
         "rrc a": (8, 2), "rl a": (8, 2), "rr a": (8, 2), "sla a": (8, 2), "sra a": (8, 2),
         "srl a": (8, 2), "sll a": (8, 2), "sra (hl)": (15, 2), "rld": (18, 2), "rrd": (18, 2)}
T = {"call": 18, "ret": 11, "ld r,n": 8, "ld r,r": 5, "add hl,hl": 12, "add hl,de": 12,
     "jr_taken": 13, "jr_not": 8, "djnz": 14, "djnz_last": 9, "or a": 5, "rr (hl)": 17,
     "inc l": 5, "rr c": 10, "rla": 5, "xor a": 5, "sub c": 5, "cp c": 5, "ld hl,nn": 11,
     "rld": 20, "dec hl": 7}


def t_mul8(h):
    """CALL, LD D,n, LD L,D, LD B,n; eight turns of ADD HL,HL and JR NC, with
    ADD HL,DE and the JR not taken for each 1 in H; seven DJNZs taken and one
    not; RET"""
    k = bin(h).count("1")
    return (T["call"] + T["ld r,n"] + T["ld r,r"] + T["ld r,n"] + 8 * T["add hl,hl"] +
            (8 - k) * T["jr_taken"] + k * (T["jr_not"] + T["add hl,de"]) + 7 * T["djnz"] +
            T["djnz_last"] + T["ret"])


def t_scroll1(w):
    return (T["call"] + T["or a"] + T["ld r,n"] + w * (T["rr (hl)"] + T["inc l"]) +
            (w - 1) * T["djnz"] + T["djnz_last"] + T["ret"])


def t_mirror():
    return (T["call"] + T["ld r,r"] + T["ld r,n"] + 8 * (T["rr c"] + T["rla"]) + 7 * T["djnz"] +
            T["djnz_last"] + T["ret"])


def t_div(n, d):
    """div, followed bit by bit: CALL, XOR A, LD B,n; then for each of 16 bits
    ADD HL,HL and RLA, and one of three ways on; DJNZ; RET. Returns the
    time, the quotient and the remainder."""
    t = T["call"] + T["xor a"] + T["ld r,n"]
    hl, a = n, 0
    for i in range(16):
        t += T["add hl,hl"] + T["rla"]
        top = hl >> 15
        hl = (hl << 1) & 0xFFFF
        a9 = (a << 1) | top
        a = a9 & 0xFF
        if a9 > 0xFF:                   # JR C taken, then SUB C and INC L
            t += T["jr_taken"] + T["sub c"] + T["inc l"]
            a, hl = (a - d) & 0xFF, hl | 1
        elif a < d:                     # JR C not taken, CP C, JR C taken
            t += T["jr_not"] + T["cp c"] + T["jr_taken"]
        else:                           # both not taken, SUB C, INC L
            t += T["jr_not"] + T["cp c"] + T["jr_not"] + T["sub c"] + T["inc l"]
            a, hl = a - d, hl | 1
        t += T["djnz"] if i < 15 else T["djnz_last"]
    return t + T["ret"], hl, a


def t_bcd():
    return T["call"] + T["ld hl,nn"] + T["xor a"] + 3 * T["rld"] + 2 * T["dec hl"] + T["ret"]


# ---------------------------------------------------------------- logic
def logic():
    n = len(gen10.LOGIC_OPS)
    v = probe.block(rom("logic"), sym("logic")["stop"], gen10.TABLE, 512 * n, frames=300)
    out = {}
    for k, name in enumerate(gen10.LOGIC_OPS):
        got = [v[512 * k + i] + 256 * v[512 * k + 256 + i] for i in range(256)]
        want = [0] * 256
        for a in range(256):
            for b in range(256):
                want[logic8(name, a, b)[1]] += 1
        assert got == want, name
        flags = {fl: sum(c for f, c in enumerate(got) if f & bit)
                 for fl, bit in (("S", 0x80), ("Z", 0x40), ("H", 0x10), ("P", 0x04),
                                 ("N", 0x02), ("C", 0x01))}
        out[name] = {"counts": got, "flags": flags, "values": sum(1 for c in got if c)}
    return out


# ---------------------------------------------------------------- sprite
def sprite():
    png = finished("sprite", 12)
    back, shape, mask = gen10.sprite_rows()
    want = {"BACK": back, "SHAPE": shape,
            "OR": [b | s for b, s in zip(back, shape)],
            "MASK": [(b & m) | s for b, s, m in zip(back, shape, mask)],
            "XOR": [b ^ s for b, s in zip(back, shape)],
            "XOR XOR": back}
    page = screentext.Page(png)
    panels = []
    for label, _, col, row in gen10.PANELS:
        got = bitmap(png, col, row, gen10.SIZE, gen10.SIZE)
        assert got == want[label], label
        assert page.text(row + gen10.SIZE // 8 + 1, col, len(label)) == label
        panels.append({"label": label, "ink": sum(bin(v).count("1") for v in got)})
    hits = probe.memory(rom("sprite"), sym("sprite")["done"], RESULTS, 1, frames=12)[0]
    nbytes = gen10.SIZE * gen10.SIZE // 8
    py = sum(1 for y in range(gen10.SIZE) for i in range(4)
             if (back[y] >> (8 * (3 - i))) & (shape[y] >> (8 * (3 - i))) & 0xFF)
    assert hits == py, (hits, py)
    return {"panels": panels, "pixels": len(panels) * gen10.SIZE * gen10.SIZE,
            "hits": hits, "bytes": nbytes, "frame": 12}


# ---------------------------------------------------------------- bits
def bits():
    s = sym("bits")
    v = probe.block(rom("bits"), s["stop"], gen10.TABLE, 8 * 512, frames=10)
    for b in range(8):
        for half, f in enumerate((0x00, 0xFF)):
            for a in range(256):
                got = v[512 * b + 256 * half + a]
                assert got == bit_model(b, a, f), (b, hex(a), hex(f), hex(got))
    sr = probe.block(rom("bits"), s["stop"], gen10.SETRES, 2 * 16 * len(gen10.SETRES_PAIRS),
                     frames=10)
    k = 0
    for b in range(8):
        for op in ("set", "res"):
            for a, f in gen10.SETRES_PAIRS:
                want_a = a | (1 << b) if op == "set" else a & ~(1 << b) & 0xFF
                assert (sr[2 * k], sr[2 * k + 1]) == (want_a, f), (op, b, a, f)
                k += 1
    return {"cases": 8 * 512, "setres_cases": k,
            "examples": {"3,08": v[512 * 3 + 0x08], "3,F7": v[512 * 3 + 0xF7]}}


# ---------------------------------------------------------------- cost
def cost():
    s = sym("cost")
    n = len(gen10.COST)
    labels = {f"t{k}": s[f"t{k}"] for k in range(n + 1)}
    got = probe.times(rom("cost"), labels)
    data = rom("cost").read_bytes()
    rows = []
    for k, ins in enumerate(gen10.COST):
        (t0, r0), (t1, r1) = got[f"t{k}"][0][:2], got[f"t{k + 1}"][0][:2]
        t, dr = round((t1 - t0) * CLOCK), (r1 - r0) % 128
        z, m1 = ZILOG[ins]
        assert t == z + m1 and dr == m1, (ins, t, dr, z, m1)
        a0, a1 = labels[f"t{k}"], labels[f"t{k + 1}"]
        rows.append({"instr": ins, "bytes": list(data[a0 - 0x4000:a1 - 0x4000]), "t": t,
                     "zilog": z})
    return {"rows": rows}


# ---------------------------------------------------------------- rotate
def rotate():
    png = finished("rotate", 10)
    page = screentext.Page(png)
    rows = []
    for k, ins in enumerate([None] + gen10.ROTATES):
        line = page.line(gen10.ROT_ROWS[k])
        assert line[:6].strip() == ("START" if ins is None else gen10.shown(ins)), line
        got = []
        for c0, f in ((gen10.COL_C0, 0x00), (gen10.COL_C1, 0x01)):
            res, cy = (gen10.START, f) if ins is None else shift_model(ins, gen10.START, f)
            want = f"{res:08b}"
            assert line[c0:c0 + 8] == want and line[c0 + 9] == str(cy & 1), (ins, line, want)
            got.append({"byte": res, "carry": cy & 1})
        rows.append({"instr": ins, "from_0": got[0], "from_1": got[1]})
    return {"rows": rows, "frame": 10}


# ---------------------------------------------------------------- shifts
def shifts():
    n = len(gen10.ROTATES)
    v = probe.block(rom("shifts"), sym("shifts")["stop"], gen10.SHIFT_TABLE, 1024 * n, frames=12)
    cases = 0
    for k, ins in enumerate(gen10.ROTATES):
        for half, f in enumerate((0x00, 0xFF)):
            for a in range(256):
                i = 1024 * k + 512 * half + 2 * a
                got = (v[i], v[i + 1])
                assert got == shift_model(ins, a, f), (ins, hex(a), hex(f), got)
                cases += 1
    return {"cases": cases}


# ---------------------------------------------------------------- mul
def mul():
    labels = [f"m{k}" for k in range(len(gen10.MUL_TIMED))]
    t = call_t("mul", labels)
    timed = []
    for (h, e), lab in zip(gen10.MUL_TIMED, labels):
        assert t[lab] == [t_mul8(h)], (h, t[lab], t_mul8(h))
        timed.append({"h": h, "e": e, "product": h * e, "ones": bin(h).count("1"), "t": t[lab][0]})
    s = sym("mul")
    v = probe.memory(rom("mul"), s["stop"], RESULTS, 7 + 2 * len(labels), frames=900)
    total = v[1] | v[2] << 8 | v[3] << 16 | v[4] << 24
    check = v[5] | v[6] << 8
    prods = [v[7 + 2 * k] | v[8 + 2 * k] << 8 for k in range(len(labels))]
    want_check = 0
    for a in range(256):
        for b in range(256):
            want_check ^= a * b
    assert total == (255 * 256 // 2) ** 2 and check == want_check, (total, check)
    assert prods == [h * e for h, e in gen10.MUL_TIMED]
    return {"timed": timed, "total": total, "check": check,
            "fastest": t_mul8(0)}


# ---------------------------------------------------------------- friction
def friction():
    v = probe.memory(rom("friction"), sym("friction")["stop"], RESULTS + 0x10, 0x30)
    signed = [x - 256 if x > 127 else x for x in v]
    lists = [signed[0:gen10.FRAMES], signed[0x10:0x10 + gen10.FRAMES],
             signed[0x20:0x20 + gen10.FRAMES]]

    def halve(x, mend=False):
        if mend and x < 0:
            x += 1
        return x >> 1                           # Python's >> rounds down, as SRA

    want = []
    for start, mend in ((gen10.FRICTION[0], False), (gen10.FRICTION[1], False),
                        (gen10.FRICTION[1], True)):
        x, out = start, []
        for _ in range(gen10.FRAMES):
            x = halve(x, mend)
            out.append(x)
        want.append(out)
    assert lists == want, (lists, want)
    # SRA on all 256 values: halving rounded down (the shifts table agrees)
    assert all(((a >> 1) | (a & 0x80)) == ((a - 256 if a > 127 else a) >> 1) & 0xFF
               for a in range(256))
    return {"from": list(gen10.FRICTION), "lists": lists}


# ---------------------------------------------------------------- scroll
def scroll():
    png = finished("scroll", 12)
    shapes, _ = screentext.font()
    page = screentext.Page(png)
    w = gen10.SCROLL_W
    got = bitmap(png, gen10.SCROLL_COL, gen10.SCROLL_ROW0, 8 * w, 8 * gen10.SCROLL_ROWS)
    for k in range(gen10.SCROLL_ROWS):
        for j in range(8):
            base = 0
            for i in range(w):
                ch = gen10.SCROLL_TEXT[i] if i < len(gen10.SCROLL_TEXT) else None
                base = (base << 8) | (shapes[ord(ch)][j] if ch else 0)
            assert got[8 * k + j] == base >> k, (k, j)
        assert page.line(gen10.SCROLL_ROW0 + k)[0] == str(k)
    t = call_t("scroll", ["t1"])["t1"][0]
    assert t == t_scroll1(w), (t, t_scroll1(w))
    return {"rows": gen10.SCROLL_ROWS, "lines": 8 * gen10.SCROLL_ROWS, "call_t": t, "width": w,
            "frame": 12}


# ---------------------------------------------------------------- mirror
def mirror():
    png = finished("mirror", 10)
    arrow = [int(r, 2) for r in gen10.ARROW]
    flip = [int(r[::-1], 2) for r in gen10.ARROW]
    for (col, row), want in zip(gen10.MIRROR_AT, (arrow, flip)):
        assert bitmap(png, col, row, 16, 16) == want, (col, row)
    s = sym("mirror")
    table = probe.block(rom("mirror"), s["done"], gen10.MIRROR_TABLE, 256, frames=10)
    assert table == [int(f"{a:08b}"[::-1], 2) for a in range(256)]
    t = call_t("mirror", ["t1"], frames=10, hits=256)["t1"]
    assert len(t) == 256 and set(t) == {t_mirror()}, (set(t), t_mirror())
    return {"call_t": t[0], "bytes": 256, "pixels": 2 * 256, "frame": 10}


# ---------------------------------------------------------------- div
def div():
    labels = [f"d{k}" for k in range(len(gen10.DIV_TIMED))]
    t = call_t("div", labels)
    s = sym("div")
    n = len(labels)
    v = probe.memory(rom("div"), s["stop"], RESULTS, 12 + 3 * n, frames=1200)
    qsum = v[2] | v[3] << 8 | v[4] << 16 | v[5] << 24
    rsum = v[6] | v[7] << 8 | v[8] << 16 | v[9] << 24
    qmix = v[10] | v[11] << 8
    q = [v[12 + 2 * k] | v[13 + 2 * k] << 8 for k in range(n)]
    r = v[12 + 2 * n:12 + 3 * n]
    timed = []
    for k, ((num_, d), lab) in enumerate(zip(gen10.DIV_TIMED, labels)):
        mt, mq, mr = t_div(num_, d)
        assert (t[lab][0], q[k], r[k]) == (mt, num_ // d, num_ % d) and (mq, mr) == (q[k], r[k]), \
            (num_, d, t[lab], mt, q[k], r[k])
        timed.append({"n": num_, "d": d, "q": q[k], "r": r[k], "t": mt})
    D = gen10.DIVISOR
    want_m = 0                          # 0: every quotient comes up an even number of
    for x in range(65536):              # times, ten each and six for the last
        want_m ^= x // D
    assert (qsum, rsum, qmix) == (sum(x // D for x in range(65536)),
                                  sum(x % D for x in range(65536)), want_m)
    all_t = [t_div(x, D)[0] for x in range(65536)]
    return {"timed": timed, "qsum": qsum, "rsum": rsum, "qmix": qmix,
            "t10_range": [min(all_t), max(all_t)]}


# ---------------------------------------------------------------- bcd
def bcd():
    n = len(gen10.BCD_TESTS)
    labels = [f"up{k}" for k in range(n)] + [f"down{k}" for k in range(n)]
    t = call_t("bcd", labels)
    assert all(v == [t_bcd()] for v in t.values()), (t, t_bcd())
    got = probe.memory(rom("bcd"), sym("bcd")["stop"], RESULTS + 3, 8 * n)
    rows = []
    for k, x in enumerate(gen10.BCD_TESTS):
        dec = int(f"{x:06X}")                     # the BCD digits, read as decimal
        up_d, up = divmod(dec * 10, 10 ** 6)
        down, down_d = divmod(dec, 10)
        g = got[8 * k: 8 * k + 8]
        g_up = int("".join(f"{b:02X}" for b in g[1:4]))
        g_down = int("".join(f"{b:02X}" for b in g[5:8]))
        assert (g[0], g_up, g[4], g_down) == (up_d, up, down_d, down), (k, g)
        rows.append({"score": dec, "up": up, "up_digit": up_d, "down": down, "down_digit": down_d})
    return {"rows": rows, "call_t": t_bcd()}


# ---------------------------------------------------------------- answers
LINE6 = [0x80, 0x01, 0xFF, 0x00, 0x5A, 0xA5, 0x81, 0x7E,
         0xC3, 0x3C, 0x0F, 0xF0, 0x12, 0x34, 0x56, 0x89]
ANSWERS = """LINE    EQU RAM_START + $10     ; question 6: a line of 16 bytes
        ld a, $1F
        and $0F
        ld (RESULTS), a         ; question 1: the foreground cleared
        or $50
        ld (RESULTS + 1), a     ; and made 5
        ld b, 0                 ; question 4: BIT 0,A against AND 1, every A
        ld c, 0                 ; C: how many times Z disagrees
q4:     ld a, b
        bit 0, a
        push af
        pop de                  ; E = F after BIT
        ld a, b
        and 1
        push af
        pop hl                  ; L = F after AND
        ld a, e
        xor l
        and $40                 ; Z the same?
        jr z, q4same
        inc c
q4same: inc b
        jr nz, q4
        ld a, c
        ld (RESULTS + 2), a
        ld hl, line
        ld de, LINE
        ld bc, 16
        ldir                    ; question 6: the line into the RAM
        ld hl, LINE + 15        ; the rightmost byte first
t6:     call left1              ; one pixel left
"""
ANSWERS_AFTER = """left1:  or a                    ; a 0 comes in at the right edge
        ld b, 16
lf1:    rl (hl)
        dec l
        djnz lf1
        ret
line:   db """ + ", ".join(f"${b:02X}" for b in LINE6) + "\n"


def build_temp(name, text):
    tmp = Path(tempfile.mkdtemp(prefix=f"{name}_"))
    (tmp / f"{name}.asm").write_text(text)
    shutil.copy(HERE / "msx.inc", tmp)
    subprocess.run(["sjasmplus", "--nologo", "--msg=err", "--syntax=bF", f"--sym={name}.sym",
                    f"{name}.asm"], cwd=tmp, check=True)
    return tmp


def answers():
    out = {}
    tmp = build_temp("answers", gen10.cart("answers", "the workshop", ANSWERS, after=ANSWERS_AFTER))
    try:
        r, s = tmp / "answers.rom", probe.sym(tmp / "answers.sym")
        v = probe.memory(r, s["stop"], RESULTS, 0x20)
        got = probe.times(r, {"a": s["t6"], "b": s["t6"] + 3})
        t6 = round((got["b"][0][0] - got["a"][0][0]) * CLOCK)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    # 1: AND $0F clears the foreground (the high four bits), OR $50 makes it 5
    assert (v[0], v[1]) == (0x1F & 0x0F, (0x1F & 0x0F) | 0x50)
    out["q1"] = {"before": 0x1F, "cleared": v[0], "five": v[1]}
    # 2: A AND E = A exactly when every 1 of A is a 1 of E: 3^8 pairs
    out["q2"] = sum(1 for a in range(256) for e in range(256) if a & e == a)
    assert out["q2"] == 3 ** 8
    # 4: AND 1 sets Z exactly as BIT 0,A does, for every A
    assert v[2] == 0
    out["q4_disagree"] = v[2]
    # 5: RLCA eight times and RLA nine times give the byte back
    for a in range(256):
        x, f = a, 0
        for _ in range(8):
            x, f = shift_model("rlca", x, f)
        assert x == a
        for c in (0, 1):
            x, f = a, c
            for _ in range(9):
                x, f = shift_model("rla", x, f)
            assert x == a and f & 1 == c
    out["q5"] = "both give the byte back; RLA nine times the carry too"
    # 6: from the rightmost byte, RL (HL) and DEC L: the line one pixel left
    n = int.from_bytes(bytes(LINE6), "big")
    want = list(((n << 1) & ((1 << 128) - 1)).to_bytes(16, "big"))
    assert v[0x10:0x20] == want, (v[0x10:0x20], want)
    assert t6 == t_scroll1(16), (t6, t_scroll1(16))
    out["q6"] = {"line": LINE6, "after": v[0x10:0x20], "call_t": t6}
    return out


# ---------------------------------------------------------------- openmsx
OPENMSX_SECTIONS = ["logic", "sprite", "bits", "cost", "rotate", "shifts", "mul", "friction",
                    "scroll", "mirror", "div", "bcd", "answers"]


def openmsx():
    if not versions.builds():
        return {"skipped": "OPENMSX_BUILDS not set"}
    return versions.every_build(["ch10"], OPENMSX_SECTIONS)


SECTIONS = {"logic": logic, "sprite": sprite, "bits": bits, "cost": cost, "rotate": rotate,
            "shifts": shifts, "mul": mul, "friction": friction, "scroll": scroll,
            "mirror": mirror, "div": div, "bcd": bcd, "answers": answers, "openmsx": openmsx}


def main(names=()):
    CAPS.mkdir(exist_ok=True)
    path = HERE / "meas10.json"
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
