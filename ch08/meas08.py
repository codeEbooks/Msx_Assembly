#!/usr/bin/env python3
"""meas08.py -- LD and its addressing modes, measured.

    python3 gen08.py && ./build.sh && python3 meas08.py
                                  python3 meas08.py modes copy4   only these
                                  python3 meas08.py --missing     those not measured yet

The models: Zilog's manual (the load group, the T-states), with one wait
state for every M1 cycle on the MSX (chapters 3 and 7); the values the
generator wrote into the programs; the character shapes of the BIOS file;
the geometry of the capture (tools/meas.py); and the clock.

  stats     how many of the instructions in chapters 1-7's programs are LD
  matrix    every LD sjasmplus assembles with --syntax=bF, eight and sixteen
            bits, against the load group in Zilog's manual
  modes     one load of each mode: bytes, T-states and R against Zilog + M1;
            the console's disassembly of the end of the program (listing 8.1)
  sixteen   EX DE,HL, LD H,D and LD L,E, a sixteen-bit store
  records   the bars on the screen (figure 8.1) against the records, and each
            turn of the loop timed against Zilog + M1
  selfmod   the program that changes itself, in the ROM and in the RAM; the
            console stopped at each (listing 8.4)
  copy4     the four copies read back from the RAM; the bands in the bottom
            border (figure 8.2) read as T-states, against the debugger's
            clock and against Zilog + M1; five frames the same
  ldai      what LD A,I and LD A,R read and the flags they set, against Zilog
  paren     paren.lst and what sjasmplus says with each setting; a distance
            out of range; every source of the book with --syntax=bF
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
import gen08       # noqa: E402

CAPS = HERE / "captures"
CLOCK = probe.CLOCK
RESULTS = 0xC000
BOOK = [f"ch{n:02d}" for n in range(1, 8)]          # the book before this chapter


def rom(name):
    return HERE / f"{name}.rom"


def sym(name):
    return probe.sym(HERE / f"{name}.sym")


def keep(name, entries):
    (HERE / f"{name}.txt").write_text(console.transcript(entries))
    return [list(e) for e in entries]


def answer(entries, line, n=0):
    return [a for l, a, _ in entries if l == line][n]


# ---------------------------------------------------------------- the models
# Zilog's T-states and M1 cycles for the instructions of this chapter
ZILOG = {"ld a,b": (4, 1), "ld a,n": (7, 1), "ld a,(hl)": (7, 1), "ld a,(bc)": (7, 1),
         "ld a,(de)": (7, 1), "ld a,(nn)": (13, 1), "ld a,(ix+d)": (19, 2),
         "ld (hl),n": (10, 1), "ld (ix+d),n": (19, 2), "ld hl,nn": (10, 1),
         "ld de,nn": (10, 1), "ld ix,nn": (14, 2), "ld hl,(nn)": (16, 1),
         "ld bc,(nn)": (20, 2), "ld ix,(nn)": (20, 2), "ld (nn),hl": (16, 1),
         "ld sp,hl": (6, 1), "ex de,hl": (4, 1), "ld a,i": (9, 2), "ld (nn),a": (13, 1),
         "ld (hl),a": (7, 1), "inc de": (6, 1), "inc hl": (6, 1), "inc ix": (10, 2),
         "out (n),a": (11, 1), "or n": (7, 1), "djnz": (13, 1), "djnz_last": (8, 1),
         "ld b,n": (7, 1)}


def msx(key):
    z, m1 = ZILOG[key]
    return z + m1


def key(ins):
    """an instruction of the chapter, as a line of ZILOG"""
    i = " ".join(ins.replace(", ", ",").split()).lower()
    i = re.sub(r"\(ix\+\d+\)", "(ix+d)", i)
    i = re.sub(r"\((var|\$[0-9a-f]+)\)", "(nn)", i)
    i = re.sub(r",(\$[0-9a-f]+|%[01]+|\d+)$", ",n", i)
    i = {"ld hl,n": "ld hl,nn", "ld de,n": "ld de,nn", "ld ix,n": "ld ix,nn"}.get(i, i)
    return i


# ---------------------------------------------------------------- stats
MACROS = {"vdp_reg": ["ld", "out", "ld", "out"], "vram_write": ["ld", "out", "ld", "out"]}
DIRECTIVES = {"include", "output", "org", "cart_header", "equ", "db", "dw", "ds", "assert",
              "macro", "endm", "disp", "ent", "defb", "defw", "defs"}


def programs(chapters):
    """the cartridges of these chapters that run: the sources whose ROM is in
    the repository (not the listings, not the ones wrong on purpose)"""
    out = []
    for ch in chapters:
        for asm in sorted((REPO / ch).glob("*.asm")):
            text = asm.read_text()
            outs = re.findall(r'^\s*OUTPUT\s+"([^"]+)"', text, re.M)
            if (outs and outs[0].endswith(".rom") and (REPO / ch / outs[0]).exists()
                    and "does not assemble, on purpose" not in text.splitlines()[0]):
                out.append(asm)
    return out


def stats():
    """every instruction line, by mnemonic; a macro of msx.inc counts as the
    instructions it stands for, and a run of identical lines (the 500 NOPs
    chapter 3 timed, the pauses of chapter 1) counts once"""
    count, files, runs = {}, programs(BOOK), 0
    for f in files:
        prev = None
        for line in f.read_text().splitlines():
            code = line.split(";")[0]
            code = re.sub(r"^\s*\.?[A-Za-z_]\w*:", "", code).strip()
            if not code:
                continue
            word = code.split()[0].lower()
            if word in DIRECTIVES or (len(code.split()) > 1 and code.split()[1].upper() == "EQU"):
                continue
            norm = " ".join(code.lower().split())
            if norm == prev:
                runs += 1
                continue
            prev = norm
            for m in MACROS.get(word, [word]):
                count[m] = count.get(m, 0) + 1
    total = sum(count.values())
    top = sorted(count.items(), key=lambda x: -x[1])[:6]
    return {"programs": len(files), "instructions": total, "ld": count["ld"], "repeats": runs,
            "ld_share": round(count["ld"] / total, 3), "top": top,
            "chapters": {ch: sum(1 for f in files if f.parent.name == ch) for ch in BOOK}}


# ---------------------------------------------------------------- matrix
OPS8 = ["a", "b", "c", "d", "e", "h", "l", "(hl)", "(bc)", "(de)", "($C000)",
        "(ix+5)", "(iy+5)", "$12", "i", "r"]
OPS16 = ["bc", "de", "hl", "sp", "ix", "iy", "($C000)", "$1234"]


def zilog8(d, s):
    """Zilog's eight-bit load group"""
    R = {"a", "b", "c", "d", "e", "h", "l"}
    X = {"(ix+5)", "(iy+5)"}
    return ((d in R and (s in R or s in {"(hl)", "$12"} | X)) or
            (d == "(hl)" and (s in R or s == "$12")) or
            (d in X and (s in R or s == "$12")) or
            (d == "a" and s in {"(bc)", "(de)", "($C000)", "i", "r"}) or
            (s == "a" and d in {"(bc)", "(de)", "($C000)", "i", "r"}))


def zilog16(d, s):
    """Zilog's sixteen-bit load group, less PUSH and POP"""
    P = {"bc", "de", "hl", "sp", "ix", "iy"}
    return ((d in P and s in {"$1234", "($C000)"}) or
            (d == "($C000)" and s in P) or
            (d == "sp" and s in {"hl", "ix", "iy"}))


def matrix():
    pairs8 = [(d, s) for d in OPS8 if d != "$12" for s in OPS8]
    pairs16 = [(d, s) for d in OPS16[:-1] for s in OPS16]
    got8 = probe.assemble_lines([f"ld {d},{s}" for d, s in pairs8])
    got16 = probe.assemble_lines([f"ld {d},{s}" for d, s in pairs16])
    m8, m16 = {}, {}
    for (d, s), b in zip(pairs8, got8):
        assert (b is not None) == zilog8(d, s), (d, s, b)
        if b:
            m8[f"{d},{s}"] = b
    for (d, s), b in zip(pairs16, got16):
        assert (b is not None) == zilog16(d, s), (d, s, b)
        if b:
            m16[f"{d},{s}"] = b
    return {"eight": m8, "sixteen": m16, "n8": len(m8), "n16": len(m16),
            "tried8": len(pairs8), "tried16": len(pairs16)}


# ---------------------------------------------------------------- modes
def timed(name, n, hits=1):
    """t0 ... tn: the time and R at each label, and the bytes between them"""
    s = sym(name)
    labels = {f"t{k}": s[f"t{k}"] for k in range(n + 1)}
    got = probe.times(rom(name), labels, hits=hits)
    data = rom(name).read_bytes()
    rows = []
    for k in range(n):
        (t0, r0), (t1, r1) = got[f"t{k}"][0][:2], got[f"t{k + 1}"][0][:2]
        a0, a1 = labels[f"t{k}"], labels[f"t{k + 1}"]
        rows.append({"t": round((t1 - t0) * CLOCK), "r": (r1 - r0) % 128,
                     "bytes": list(data[a0 - 0x4000:a1 - 0x4000])})
    return rows


def modes():
    rows = timed("modes", len(gen08.MODES))
    out = []
    for (ins, mode), row in zip(gen08.MODES, rows):
        z, m1 = ZILOG[key(ins)]
        assert row["t"] == z + m1 and row["r"] == m1, (ins, row, z, m1)
        out.append({"instr": ins, "mode": mode, "bytes": row["bytes"], "t": row["t"],
                    "zilog": z, "m1": m1})
    # the console at the end: the loop the program ends in, and value after it
    s = sym("modes")
    e = console.session(rom("modes"), ["disasm [reg pc] 5"], start=s["stop"])
    dis = [l for l in e[0][1].splitlines() if l.strip()]
    data = rom("modes").read_bytes()
    for l in dis:
        a = int(l.split()[0], 16)
        code = [int(x, 16) for x in l[26:].split()]
        assert list(data[a - 0x4000:a - 0x4000 + len(code)]) == code, l
    assert int(dis[1].split()[0], 16) == s["value"]
    return {"rows": out, "session": keep("modes", e), "disasm": dis,
            "value": s["value"], "var": s["var"]}


# ---------------------------------------------------------------- sixteen
def sixteen():
    s = sym("sixteen")
    got = probe.times(rom("sixteen"), {k: s[k] for k in ("p1", "p2", "p3")},
                      extra="[reg hl] [reg de] [debug read memory 0xC000] "
                            "[debug read memory 0xC001]")
    v = {k: [int(x) for x in got[k][0][2:]] for k in got}
    assert v["p1"][:2] == [0x5678, 0x1234] and v["p2"][:2] == [0x1234, 0x1234]
    assert v["p3"][2:] == [0x34, 0x12]
    t = round((got["p2"][0][0] - got["p1"][0][0]) * CLOCK)
    assert t == 2 * msx("ld a,b")                       # LD H,D and LD L,E: 5 each
    return {"after_ex": v["p1"][:2], "after_copy": v["p2"][:2], "stored": v["p3"][2:],
            "copy_t": t}


# ---------------------------------------------------------------- records
RECORDS_FRAME = 10


def finished(name, frame):
    got = msxcap.capture(rom(name), [frame - 1, frame], CAPS, f"{name}_f")
    a, b = (Image.open(got[n]).convert("RGB") for n in (frame - 1, frame))
    assert a.tobytes() == b.tobytes(), f"{name}: still changing at frame {frame}"
    got[frame - 1].unlink()
    return got[frame]


def records():
    png = finished("records", RECORDS_FRAME)
    page = screentext.Page(png)
    bars = []
    for c, r, ch in gen08.OBJECTS:
        want = "1" if ch == gen08.BOX_FULL else ch            # the box reads as 1
        line = page.line(r)
        assert line[c:c + gen08.BAR] == want * gen08.BAR and line[c + gen08.BAR] == " " \
            and line[c - 1] == " ", (c, r, line)
        bars.append({"col": c, "row": r, "char": want})
    # every other cell of the page is a space
    cells = sum(1 for r in range(24) for x in page.line(r) if x != " ")
    assert cells == gen08.BAR * len(gen08.OBJECTS), cells
    s = sym("records")
    data = rom("records").read_bytes()[s["objects"] - 0x4000:][:3 * len(gen08.OBJECTS)]
    stored = [list(data[3 * k:3 * k + 3]) for k in range(len(gen08.OBJECTS))]
    for (c, r, ch), b in zip(gen08.OBJECTS, stored):
        a = 0x1800 + 32 * r + c
        assert b == [a & 0xFF, a >> 8, ch if isinstance(ch, int) else ord(ch)], (c, r, b)
    got = probe.times(rom("records"), {"next": s["next"]}, hits=len(gen08.OBJECTS), frames=4)
    ts = [t for t, *_ in got["next"]]
    turns = [round((b - a) * CLOCK) for a, b in zip(ts, ts[1:])]
    model = 3 * msx("ld a,(ix+d)") + 2 * msx("out (n),a") + msx("or n") + \
        gen08.BAR * msx("out (n),a") + 3 * msx("inc ix") + msx("djnz")
    assert len(turns) == len(gen08.OBJECTS) - 1 and all(t == model for t in turns), (turns, model)
    return {"bars": bars, "checked_cells": gen08.BAR * len(bars), "stored": stored,
            "turn": model, "turns": turns, "indexed_t": 3 * msx("ld a,(ix+d)"),
            "outs_t": (2 + gen08.BAR) * msx("out (n),a"), "frame": RECORDS_FRAME}


# ---------------------------------------------------------------- selfmod
def selfmod():
    s = sym("selfmod")
    got = probe.memory(rom("selfmod"), s["stop"], RESULTS, 2)
    ram = probe.memory(rom("selfmod"), s["stop"], s["mpatch"] + 1, 1)[0]
    data = rom("selfmod").read_bytes()
    in_rom = data[s["rpatch"] + 1 - 0x4000]
    # the RAM copy: the bytes after copy, as assembled
    assert got == [0x00, gen08.SELF_A] and ram == gen08.SELF_A and in_rom == 0, (got, ram, in_rom)
    lines = ["disasm [reg pc] 1", "step_in", "reg a", f"debug set_bp 0x{s['mpatch']:04X}",
             "debug cont", "disasm [reg pc] 1", "step_in", "reg a"]
    e = console.session(rom("selfmod"), lines, start=s["rpatch"])
    regs = [int(a) for l, a, _ in e if l == "reg a"]
    dis = [a for l, a, _ in e if l.startswith("disasm")]
    assert regs == [0, gen08.SELF_A], regs
    assert dis[0].split()[0] == f"{s['rpatch']:04X}" and dis[1].split()[0] == f"{s['mpatch']:04X}"
    return {"results": got, "rom_byte": in_rom, "ram_byte": ram, "rpatch": s["rpatch"],
            "mpatch": s["mpatch"], "inram": s["inram"], "copy_bytes": s["copy_end"] - s["copy"],
            "session": keep("selfmod", e), "disasm": dis}


# ---------------------------------------------------------------- copy4
COPY4_FRAMES = list(range(10, 15))
SHOWN = 12


def bands_of(png):
    """the changes of colour under the paper, in raster order, in the columns
    the VDP draws: (row, x, colour)"""
    px = Image.open(png).convert("RGB").load()
    first_row = meas.PAPER_Y0 + meas.PAPER_H
    prev, out = px[meas.DRAWN[0], first_row], []
    for y in range(first_row, meas.CAPTURE_H):
        for x in range(meas.DRAWN[0], meas.DRAWN[1] + 1):
            if px[x, y] != prev:
                out.append((y, x, px[x, y]))
                prev = px[x, y]
    return out


def copy4():
    got = msxcap.capture(rom("copy4"), COPY4_FRAMES, CAPS, "copy4_f")
    pics = [Image.open(got[n]).convert("RGB").tobytes() for n in COPY4_FRAMES]
    assert all(p == pics[0] for p in pics), "the bands move from frame to frame"
    for n in COPY4_FRAMES:
        if n != SHOWN:
            got[n].unlink()
    changes = bands_of(got[SHOWN])
    n_ways = len(gen08.WAYS)
    assert len(changes) == n_ways + 1, changes
    # every change well inside the drawn columns: not at their edges, where a
    # change outside them would show
    assert all(meas.DRAWN[0] + 6 <= x <= meas.DRAWN[1] - 6 for _, x, _ in changes), changes
    raster = [meas.raster(x, y) for y, x, _ in changes]
    bands_px = [(b - a) / meas.PX_PER_T for a, b in zip(raster, raster[1:])]
    bands = [round(b) for b in bands_px]
    assert all(abs(b - r) < 0.7 for b, r in zip(bands, bands_px)), bands_px
    # the debugger: when each second OUT of VDP_REG 7 starts, in a frame of
    # the film, and where in the frame
    s = sym("copy4")
    outs = {f"col{k}": s[f"col{k}"] + 6 for k in range(1, n_ways + 2)}
    t = probe.times(rom("copy4"), outs, frames=SHOWN + 1, hits=SHOWN,
                    extra="[machine_info VDP_frame_count] [machine_info VDP_cycle_in_frame]")
    last = {k: v[-1] for k, v in t.items()}
    frames = {int(v[2]) for v in last.values()}
    assert len(frames) == 1, last
    bands_dbg = [round((last[f"col{k + 1}"][0] - last[f"col{k}"][0]) * CLOCK)
                 for k in range(1, n_ways + 1)]
    # the model: Zilog + M1. From the start of one OUT to the start of the
    # next one's: the OUT, LD B,n, the passes, the DJNZs, LD A,n, OUT, LD A,n
    passes = []
    for k in range(n_ways):
        _, instrs = gen08.way_lines(k)
        passes.append(sum(msx(i) for i in instrs))
    over = msx("out (n),a") + msx("ld b,n") + (gen08.REPEAT - 1) * msx("djnz") + \
        msx("djnz_last") + 2 * msx("ld a,n") + msx("out (n),a")
    model = [gen08.REPEAT * p + over for p in passes]
    assert bands == bands_dbg == model, (bands, bands_dbg, model)
    # where each change shows: the OUT's write is 8 T after its start, the
    # line is VDP_cycle_in_frame // 1368 (6 VDP cycles a T-state), the row
    # of the capture is the line - 45, and a write made at T-state w of a
    # line shows at x = ceil(1.5 w - 31) (tools/meas.py: OUT (C),r, whose
    # write is 10 T after its start, shows at ceil(1.5 t - 16))
    import math
    where, writes = [], []
    for k in range(1, n_ways + 2):
        cyc = int(last[f"col{k}"][3]) + 6 * 8
        line, w = divmod(cyc, 1368)
        where.append((line - meas.FRAME_LINE_OF_ROW0["MSXBOOK_EU16"], math.ceil(1.5 * w / 6 - 31)))
        writes.append({"line": line, "t": w / 6, "row": where[-1][0], "x": where[-1][1]})
    assert where == [(y, x) for y, x, _ in changes], (where, changes)
    # one pass of each way, by the debugger: from its label to the same label
    # the next time round, less the DJNZ that went back
    ways = probe.times(rom("copy4"), {f"way{k}": s[f"way{k}"] for k in range(1, n_ways + 1)},
                       frames=3, hits=2)
    one = [round((v[1][0] - v[0][0]) * CLOCK) - msx("djnz") for v in ways.values()]
    assert one == passes, (one, passes)
    size = [s[f"col{k + 1}"] - s[f"way{k}"] - 2 for k in range(1, n_ways + 1)]
    bufs = probe.memory(rom("copy4"), s[f"col{n_ways + 1}"], 0xC040, 32, frames=3)
    assert bufs == gen08.GLYPH * 4, bufs
    return {"one_pass": passes, "bands": bands, "bands_debugger": bands_dbg, "model": model,
            "overhead": over, "repeat": gen08.REPEAT, "bytes": size, "changes": changes,
            "frame": SHOWN, "copies_checked": 4, "pause_t": gen08.pause_t(), "writes": writes}


# ---------------------------------------------------------------- ldai
def ldai():
    s = sym("ldai")
    n = 2 * len(gen08.LDAI_TESTS)
    v = probe.memory(rom("ldai"), s["stop"], RESULTS, n)
    rows = []
    for k, (reg, val, ei, f) in enumerate(gen08.LDAI_TESTS):
        got_f, got_a = v[2 * k], v[2 * k + 1]
        # I as it was put; R moved on by the six opcode fetches after LD R,A,
        # its own two included (chapter 7), bit 7 kept
        read = val if reg == "i" else (val & 0x80) | ((val + 6) & 0x7F)
        assert got_a == read, (reg, hex(val), hex(got_a), hex(read))
        # Zilog: S and Z from the value, H and N cleared, P/V = IFF2, C kept
        want = (0x80 if read & 0x80 else 0) | (0x40 if read == 0 else 0) | \
               (0x04 if ei else 0) | (f & 0x01)
        assert got_f & 0xD7 == want, (reg, hex(val), ei, hex(f), hex(got_f), hex(want))
        rows.append({"reg": reg, "value": val, "ei": ei, "f_before": f,
                     "a_after": got_a, "f_after": got_f})
    return {"rows": rows}


# ---------------------------------------------------------------- paren
WRONG = {"ch04/case.asm", "ch05/typo.asm", "ch05/margin.asm", "ch07/fake.asm",
         "ch08/paren.asm"}                     # wrong on purpose


def run_sjasm(args, src, cwd):
    r = subprocess.run(["sjasmplus", "--nologo", *args, src], cwd=cwd, capture_output=True, text=True)
    msg = [re.sub(r", work time: [0-9.]+ seconds", "", l)
           for l in (r.stdout + r.stderr).strip().splitlines() if not l.startswith("Pass ")]
    return r.returncode, msg


def paren():
    lst = probe.read_lst(HERE / "paren.lst")
    out = {}
    for name, args in (("err", ["--msg=err"]), ("war", ["--msg=war"]),
                       ("b", ["--msg=war", "--syntax=b"])):
        tmp = Path(tempfile.mkdtemp(prefix="paren_"))
        shutil.copy(HERE / "paren.asm", tmp)
        code, msg = run_sjasm(args, "paren.asm", tmp)
        out[name] = {"exit": code, "messages": msg}
        shutil.rmtree(tmp, ignore_errors=True)
    (HERE / "paren_b_out.txt").write_text("\n".join(out["b"]["messages"]) + "\n")
    assert out["err"]["messages"] == [] and out["err"]["exit"] == 0
    assert out["b"]["exit"] != 0
    # a distance out of range
    off = probe.assemble_lines(["ld a,(ix-1)", "ld a,(ix+127)"])
    tmp = Path(tempfile.mkdtemp(prefix="off_"))
    (tmp / "o.asm").write_text("        ORG $4000\n        ld a,(ix+130)\n")
    code, omsg = run_sjasm(["--msg=err"], "o.asm", tmp)
    shutil.rmtree(tmp, ignore_errors=True)
    # every source of the book, chapters 1 to 8, with the settings build.sh
    # uses from this chapter on, in copies: the same bytes
    same, total = [], 0
    for ch in BOOK + ["ch08"]:
        for asm in sorted((REPO / ch).glob("*.asm")):
            rel = f"{ch}/{asm.name}"
            text = asm.read_text()
            outs = re.findall(r'^\s*OUTPUT\s+"([^"]+)"', text, re.M)
            if not outs or rel in WRONG or "does not assemble, on purpose" in text.splitlines()[0]:
                continue
            total += 1
            tmp = Path(tempfile.mkdtemp(prefix="bF_"))
            try:
                for f in asm.parent.iterdir():
                    if f.suffix in (".asm", ".inc", ".bin"):
                        shutil.copy(f, tmp)
                c, _ = run_sjasm(["--msg=err", "--syntax=bF"], asm.name, tmp)
                if c == 0 and all((tmp / o).read_bytes() == (asm.parent / o).read_bytes()
                                  for o in outs):
                    same.append(rel)
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
    assert len(same) == total, (total, len(same))
    return {"listing": [{"src": s_, "bytes": b} for s_, _, b in lst], "settings": out,
            "offset": {"bytes": off, "messages": omsg, "exit": code},
            "book_programs": total}


# ---------------------------------------------------------------- answers
def answers():
    out = {}
    out["q2"] = probe.assemble_lines(["ld a,($C100)", "ld c,a", "ld hl,$C100", "ld c,(hl)"])
    out["q2_t"] = [msx("ld a,(nn)"), msx("ld a,b"), msx("ld hl,nn"), msx("ld a,(hl)")]
    # question 3: four cells a bar; the turn timed again
    tmp = Path(tempfile.mkdtemp(prefix="rec4_"))
    try:
        src = (HERE / "records.asm").read_text().replace(
            "        out (VDP_DATA), a       ; 3 cells",
            "        out (VDP_DATA), a\n        out (VDP_DATA), a       ; 4 cells")
        assert src != (HERE / "records.asm").read_text()
        (tmp / "records.asm").write_text(src)
        shutil.copy(HERE / "msx.inc", tmp)
        subprocess.run(["sjasmplus", "--nologo", "--msg=err", "--syntax=bF", "--sym=records.sym",
                        "records.asm"], cwd=tmp, check=True)
        s = probe.sym(tmp / "records.sym")
        got = probe.times(tmp / "records.rom", {"next": s["next"]}, hits=2, frames=4)
        out["q3_turn"] = round((got["next"][1][0] - got["next"][0][0]) * CLOCK)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    out["q5"] = probe.assemble_lines(["ld de,($C040)", "ld hl,($C040)"])
    out["q6"] = [msx("ld a,(nn)"), msx("ld (nn),a")]
    return out


# ---------------------------------------------------------------- openmsx
OPENMSX_SECTIONS = ["modes", "sixteen", "records", "selfmod", "copy4", "ldai", "answers"]


def openmsx():
    if not versions.builds():
        return {"skipped": "OPENMSX_BUILDS not set"}
    return versions.every_build(["ch08"], OPENMSX_SECTIONS)


SECTIONS = {"stats": stats, "matrix": matrix, "modes": modes, "sixteen": sixteen,
            "records": records, "selfmod": selfmod, "copy4": copy4, "ldai": ldai,
            "paren": paren, "answers": answers, "openmsx": openmsx}


def main(names=()):
    CAPS.mkdir(exist_ok=True)
    path = HERE / "meas08.json"
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
