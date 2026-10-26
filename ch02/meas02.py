#!/usr/bin/env python3
"""meas02.py -- film the programs of chapter 2 and read their pages back.

    ./build.sh && python3 meas02.py

The figures of this chapter are text and boxes that the MSX drew, so they are
read back cell by cell: every 8 x 8 cell of the capture is compared with the
character shapes in the BIOS ROM of the machine that ran the program (read
from the ROM file, not from the program) and with the two box shapes of
tools/asmparts.py, and each line of the page becomes a string again.

Then the strings are checked against an independent model: Python does the
same sums with its own arithmetic (8 bits, carry, two's-complement overflow),
the same shifts and the same 16-bit additions, and the two must agree on every
line. The openMSX debugger reads the bytes the programs left in memory and in
the VRAM, and sjasmplus's own listings give the bytes it assembled.

Writes captures/*.png and meas02.json, where every number of the chapter
comes from.
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
sys.path.insert(0, str(HERE.parent / "tools"))
import msxcap  # noqa: E402
import meas    # noqa: E402
import gen02   # noqa: E402
from asmparts import BOX_SHAPES, BOX_EMPTY, BOX_FULL  # noqa: E402

CAPS = HERE / "captures"
FRAME = 30                      # each program draws its page once, then shows it
EU, JP = "MSXBOOK_EU16", "MSXBOOK_JP16"
BIOS = {EU: "cbios_main_msx1_eu.rom", JP: "cbios_main_msx1_jp.rom"}


# ---------------------------------------------------------------- reading a page
def font(machine):
    """the 256 character shapes of a machine's BIOS, from the ROM file:
    the address of the set is the word at $0004 (CGTABL)"""
    rom = (msxcap.CBIOS / BIOS[machine]).read_bytes()
    at = rom[4] | rom[5] << 8
    return [tuple(rom[at + 8 * c: at + 8 * c + 8]) for c in range(256)], at


def shape_table(machine):
    """shape -> character, for the codes the programs print (32-126) and the
    two boxes, read as the bits they stand for"""
    shapes, _ = font(machine)
    table = {}
    for c in range(32, 127):
        # two codes with one shape cannot be read back: such a cell reads "?"
        table[shapes[c]] = "?" if shapes[c] in table else chr(c)
    table[tuple(BOX_SHAPES[BOX_EMPTY])] = "0"
    table[tuple(BOX_SHAPES[BOX_FULL])] = "1"
    return table


def cell(px, col, row):
    """the 8 bytes of a character cell, as the screen shows them (ink = 1)"""
    x0, y0 = meas.paper(8 * col, 8 * row)
    return tuple(sum((sum(px[x0 + i, y0 + j]) < 384) << (7 - i) for i in range(8))
                 for j in range(8))


def read_line(png, row, table):
    px = Image.open(png).convert("RGB").load()
    return "".join(table.get(cell(px, c, row), "?") for c in range(32))


def shot(name, machine=EU, tag=None):
    """frames FRAME - 1 and FRAME; the two must be the same picture: the page
    is finished"""
    prefix = f"{tag or name}_f"
    got = msxcap.capture(HERE / f"{name}.rom", [FRAME - 1, FRAME], CAPS, prefix, machine=machine)
    a, b = (Image.open(got[n]).convert("RGB") for n in (FRAME - 1, FRAME))
    assert a.tobytes() == b.tobytes(), f"{name}: the page still changes at frame {FRAME}"
    got[FRAME - 1].unlink()
    return got[FRAME]


def debug_read(name, reads, machine=EU):
    """read bytes with the openMSX debugger at frame FRAME: reads is
    {key: (debuggable, address, count)}; returns {key: [bytes]}"""
    tcl = []
    for key, (dbg, addr, n) in reads.items():
        tcl.append(f'set s "{key}"; for {{set i 0}} {{$i < {n}}} {{incr i}} '
                   f'{{append s " " [debug read {dbg} [expr {{{addr} + $i}}]]}}; L $s')
    lines = msxcap.run_tcl(HERE / f"{name}.rom", FRAME + 1, "", machine=machine,
                           events={FRAME: "; ".join(tcl)})
    out = {}
    for line in lines:
        key, _, rest = line.partition(" ")
        if key in reads:
            out[key] = [int(v) for v in rest.split()]
    assert set(out) == set(reads), (name, lines[-5:])
    return out


# ---------------------------------------------------------------- the model
def model(a, b, op):
    """the sum the Z80 was asked to do, done by Python"""
    if op == "add":
        full = a + b
        r = full & 0xFF
        carry = full > 0xFF
        over = bool((a ^ r) & (b ^ r) & 0x80)
    else:
        r = (a - b) & 0xFF
        carry = a < b
        over = bool((a ^ b) & (a ^ r) & 0x80)
    return r, carry, over


def signed(r):
    return r - 256 if r & 0x80 else r


# ---------------------------------------------------------------- the assembler
def assemble(src_text=None, src=None, lst=True):
    """assemble in a temporary folder; returns (returncode, messages, listing lines)"""
    tmp = Path(tempfile.mkdtemp(prefix="meas02_"))
    try:
        shutil.copy(HERE / "msx.inc", tmp)
        if src:
            shutil.copy(HERE / src, tmp)
            name = src
        else:
            name = "probe.asm"
            (tmp / name).write_text(src_text)
        args = ["sjasmplus", "--nologo", "--msg=err"] + (["--lst=out.lst"] if lst else []) + [name]
        r = subprocess.run(args, cwd=tmp, capture_output=True, text=True)
        listing = (tmp / "out.lst").read_text().splitlines() if (tmp / "out.lst").exists() else []
        return r.returncode, (r.stdout + r.stderr).strip(), listing
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


LST = re.compile(r"\s*\d+\+?\s+([0-9A-F]{4}) ((?:[0-9A-F]{2} )+)\s*(>?)\s*(.*)")


def lst_entries(listing):
    """(address, [bytes], source) for every listing line that made bytes"""
    out = []
    for line in listing:
        m = LST.match(line.rstrip())
        if m:
            out.append((m.group(1), m.group(2).split(), m.group(4).strip()))
    return out


def macro_bytes(listing, call):
    """the bytes of the LAST expansion of a macro call, e.g. 'VRAM_WRITE 1800'"""
    start = max(i for i, l in enumerate(listing) if l.split(";")[0].strip().endswith(call))
    out = []
    for line in listing[start + 1:]:
        m = LST.match(line.rstrip())
        if not m or m.group(3) != ">":
            break
        out.append((m.group(1), m.group(2).split(), m.group(4).strip()))
    return out


# ---------------------------------------------------------------- the measurements
def main():
    CAPS.mkdir(exist_ok=True)
    res = {}
    T = {EU: shape_table(EU), JP: shape_table(JP)}
    shapes = {EU: font(EU)[0], JP: font(JP)[0]}
    res["cgtabl"] = {m: f"{font(m)[1]:04X}" for m in (EU, JP)}

    # ---- count: every line read back and checked against Python
    p = shot("count")
    rows = []
    for k in range(16):
        line = read_line(p, gen02.COUNT_ROW + k, T[EU])
        for c0, v in zip(gen02.COUNT_COLS, (k, gen02.PICKS[k])):
            dec, hx, bits = line[c0:c0 + 3], line[c0 + 4:c0 + 6], line[c0 + 7:c0 + 15]
            assert (int(dec), int(hx, 16), int(bits, 2)) == (v, v, v), (v, dec, hx, bits)
            rows.append((v, hx, bits))
    res["count"] = sorted(rows)
    res["count_heading"] = read_line(p, gen02.COUNT_ROW - 2, T[EU]).strip()

    # ---- arith: the Z80's answers, and Python's
    p = shot("arith")
    C = gen02.COLS
    sums = []
    for i, (text, a, b, op) in enumerate(gen02.SUMS):
        line = read_line(p, gen02.ROW0 + gen02.STEP * i, T[EU])
        got = {"text": line[C["sum"]:C["bits"]].strip(),
               "bits": line[C["bits"]:C["bits"] + 8],
               "hex": line[C["hex"]:C["hex"] + 2],
               "dec": int(line[C["dec"]:C["dec"] + 3]),
               "sgn": int(line[C["sgn"]:C["sgn"] + 4]),
               "C": line[C["C"]] == "C", "V": line[C["V"]] == "V"}
        r, carry, over = model(a, b, op)
        want = {"text": text, "bits": f"{r:08b}", "hex": f"{r:02X}", "dec": r,
                "sgn": signed(r), "C": carry, "V": over}
        assert got == want, (text, got, want)
        assert line[C["C"]] in "C-" and line[C["V"]] in "V-", line
        sums.append(got)
    res["sums"] = sums
    last = read_line(p, gen02.ROW0 + gen02.STEP * len(gen02.SUMS) + 1, T[EU])
    m = re.search(r"HL=\$([0-9A-F]{4})\s+\$C000:([0-9A-F]{2})\s+\$C001:([0-9A-F]{2})", last)
    assert m, last
    res["hl"], res["mem_c000"], res["mem_c001"] = m.groups()
    mem = debug_read("arith", {"mem": ("memory", gen02.STORE_AT, 2)})["mem"]
    assert [f"{b:02X}" for b in mem] == [res["mem_c000"], res["mem_c001"]], mem
    assert mem == [gen02.HL_VALUE & 0xFF, gen02.HL_VALUE >> 8]
    res["mem_debugger"] = [f"{b:02X}" for b in mem]

    # ---- fields: four numbers out of one status byte, checked against Python
    p = shot("fields")
    F = gen02.FIELD_COLS
    fields = []
    for k, v in enumerate(gen02.STATUS_SHOWN):
        line = read_line(p, gen02.FIELD_ROW + 2 * k, T[EU])
        got = {"hex": line[F["hex"]:F["hex"] + 2], "bits": line[F["bits"]:F["bits"] + 8],
               "F": int(line[F["F"]]), "5S": int(line[F["5S"]]),
               "C": int(line[F["C"]]), "spr": int(line[F["spr"]:F["spr"] + 3])}
        want = {"hex": f"{v:02X}", "bits": f"{v:08b}", "F": v >> 7, "5S": (v >> 6) & 1,
                "C": (v >> 5) & 1, "spr": v & 31}
        assert got == want, (v, got, want)
        fields.append(got)
    res["fields"] = fields

    # ---- shifts: doubling and halving, and the carries
    p = shot("shifts")
    for c0, start, op in zip(gen02.SHIFT_COLS, gen02.SHIFT_START, ("sla", "srl")):
        seq, v, cy = [], start, 0
        for k in range(gen02.SHIFT_STEPS + 1):
            line = read_line(p, gen02.SHIFT_ROW + 2 * k, T[EU])
            got = (int(line[c0:c0 + 3]), line[c0 + 4:c0 + 12], line[c0 + 13] == "C")
            assert got == (v, f"{v:08b}", bool(cy)), (op, k, got, v, cy)
            seq.append({"value": v, "carry": bool(cy)})
            if op == "sla":
                cy, v = v >> 7, (v << 1) & 0xFF
            else:
                cy, v = v & 1, v >> 1
        res[op] = seq

    # ---- chars: on both machines, every cell is that machine's ROM shape for its code
    chars = {}
    for machine, tag in ((EU, "chars"), (JP, "chars_jp")):
        p = shot("chars", machine, tag)
        px = Image.open(p).convert("RGB").load()
        n = 0
        for hi in range(2, 16):
            row = gen02.CHAR_ROW + hi - 2
            for lo in range(16):
                assert cell(px, gen02.CHAR_COL + lo, row) == shapes[machine][16 * hi + lo], \
                    (machine, hex(16 * hi + lo))
                n += 1
            side = read_line(p, row, T[machine])[gen02.CHAR_COL - 2]
            assert side == f"{hi:X}", (machine, hi, side)
        top = read_line(p, gen02.CHAR_ROW - 1, T[machine])
        assert top[gen02.CHAR_COL:gen02.CHAR_COL + 16] == "0123456789ABCDEF", top
        blank = sum(shapes[machine][c] == (0,) * 8 for c in range(128, 256))
        chars[machine] = {"cells": n, "blank_128_255": blank}
    same = [c for c in range(32, 256) if shapes[EU][c] == shapes[JP][c]]
    chars["same_shape_codes"] = same
    chars["differ_32_126"] = sum(shapes[EU][c] != shapes[JP][c] for c in range(32, 127))
    chars["differ_128_255"] = sum(shapes[EU][c] != shapes[JP][c] for c in range(128, 256))
    res["chars"] = chars

    # ---- fixed: sixteen-bit positions, checked against Python
    p = shot("fixed")
    fixed = {}
    for c0, st in zip(gen02.FIX_COLS, gen02.FIX_STEPS):
        seq, pos = [], 0
        for k in range(gen02.FIX_N):
            line = read_line(p, gen02.FIX_ROW + 2 * k, T[EU])
            got = (line[c0:c0 + 4], int(line[c0 + 5:c0 + 8]))
            assert got == (f"{pos:04X}", pos >> 8), (st, k, got, pos)
            seq.append({"hex": got[0], "px": got[1]})
            pos = (pos + st) & 0xFFFF
        fixed[f"{st:04X}"] = seq
    res["fixed"] = fixed

    # ---- addr_hex / addr_dec: one dollar sign apart
    addr = {}
    for name, target in (("addr_hex", "$1800"), ("addr_dec", "1800")):
        p = shot(name)
        px = Image.open(p).convert("RGB").load()
        top = read_line(p, 0, T[EU])
        changed = []
        for k in range(16):
            code = gen02.WITNESS_FIRST + k
            got = cell(px, 2 * k, gen02.WITNESS_ROW)
            if got != shapes[EU][code]:
                assert got == (BOX_FULL,) * 8, (name, hex(code), got)
                changed.append(code)
        ink = sum(sum(px[meas.paper(x, y)]) < 384 for y in range(192) for x in range(256))
        rc, msg, listing = assemble(src=f"{name}.asm")
        assert rc == 0, msg
        vram_addr = int(target.lstrip("$"), 16 if target.startswith("$") else 10)
        vr = debug_read(name, {"at": ("VRAM", vram_addr, 32),
                               "names": ("VRAM", 0x1800, 32)})
        addr[name] = {"target": target, "vram_addr": f"{vram_addr:04X}",
                      "top_row": top, "changed": changed, "ink": ink,
                      "bytes": macro_bytes(listing, f"VRAM_WRITE {target}"),
                      "vram_at": vr["at"], "vram_names_row0": vr["names"]}
    h, d = addr["addr_hex"], addr["addr_dec"]
    assert h["top_row"] == "1" * 32 and d["top_row"].strip() == ""
    assert h["changed"] == [] and d["changed"] == [0xE1, 0xE2, 0xE3, 0xE4]
    assert d["vram_addr"] == "0708" and d["vram_at"] == [BOX_FULL] * 32
    assert h["vram_at"] == [BOX_FULL] * 32 and d["vram_names_row0"] == [32] * 32
    res["addr"] = addr

    # ---- notation: the assembler's own listing, and two notations tried on it
    rc, msg, listing = assemble(src="notation.asm")
    assert rc == 0, msg
    res["notation"] = [e for e in lst_entries(listing)
                       if e[2].startswith(("db ", "dw ", "ld hl,"))]
    assert {tuple(e[1]) for e in res["notation"] if e[2].startswith("db ")} == {("FF",)}
    rc, msg, _ = assemble("        ORG $4000\n        db &HFF\n")
    res["basic_hex"] = {"rc": rc, "message": msg.split(": ", 1)[1] if ": " in msg else msg}
    assert rc != 0
    rc, msg, _ = assemble("        ORG $4000\n        db FFh\n")
    res["suffix_no_digit"] = {"rc": rc, "message": msg.split(": ", 1)[1] if ": " in msg else msg}
    assert rc != 0
    rc, msg, listing = assemble("        ORG $4000\n        db 0b11111111\n")
    res["c_binary"] = {"rc": rc, "bytes": [e[1] for e in lst_entries(listing)]}
    assert rc == 0 and res["c_binary"]["bytes"] == [["FF"]]

    (HERE / "meas02.json").write_text(json.dumps(res, indent=1) + "\n")
    return res


if __name__ == "__main__":
    r = main()
    for s in r["sums"]:
        print(f"  {s['text']:8s} {s['bits']} {s['hex']} {s['dec']:4d} {s['sgn']:5d} "
              f"{'C' if s['C'] else '-'} {'V' if s['V'] else '-'}")
    print(f"  HL=${r['hl']}  $C000:{r['mem_c000']}  $C001:{r['mem_c001']}  "
          f"(debugger: {' '.join(r['mem_debugger'])})")
    print(f"  count: {len(r['count'])} numbers read back, all agree with Python")
    for f in r["fields"]:
        print(f"  status {f['hex']} {f['bits']} F{f['F']} 5S{f['5S']} C{f['C']} sprite {f['spr']}")
    for op in ("sla", "srl"):
        print(f"  {op}: " + " ".join(f"{x['value']}{'C' if x['carry'] else ''}" for x in r[op]))
    c = r["chars"]
    print(f"  chars: {c[EU]['cells']} cells on {EU}, {c[JP]['cells']} on {JP}, each its ROM's shape;"
          f" shapes that differ: {c['differ_32_126']} of 95 (32-126), {c['differ_128_255']} of 128;"
          f" same: {c['same_shape_codes']}")
    for st, seq in r["fixed"].items():
        print(f"  fixed {st}: " + " ".join(str(x["px"]) for x in seq))
    for name, a in r["addr"].items():
        print(f"  {name}: target {a['target']} = ${a['vram_addr']}, ink {a['ink']}, "
              f"changed {[hex(x) for x in a['changed']]}, bytes "
              + "; ".join(" ".join(b) for _, b, _ in a["bytes"]))
    for a, b, s in r["notation"]:
        print(f"  {a} {' '.join(b):10s} {s}")
    print(f"  &HFF: rc {r['basic_hex']['rc']}, {r['basic_hex']['message']}")
    print(f"  FFh: rc {r['suffix_no_digit']['rc']}, {r['suffix_no_digit']['message']}")
    print(f"  0b11111111: {r['c_binary']['bytes']}")
