#!/usr/bin/env python3
"""meas15.py -- what the assembler did, checked.

    python3 gen15.py && ./build.sh && python3 meas15.py
                                  python3 meas15.py names rows    only these
                                  python3 meas15.py --missing     those not measured yet

  names     the symbol table against the listing; the records against chapter
            8's; the name table the program printed
  symbols   the symbol table loaded into openMSX's own debugger: 21.0 reads it
            (symbols.txt), 19.1 has no such command (needs OPENMSX_BUILDS)
  exprs     every line of exprs.lst against the same sums in Python
  fits      the warnings in fits.lst, and the same source with w (fits_out.txt)
  macro     the time and the bytes of eight uses of a macro and of a
            subroutine, against their instructions' prices (chapter 14)
  rows      the two tables in rows.rom against chapter 13's, as its program
            made them in the RAM; line 100 looked up; what sjasmplus prints
            for rows.asm, and with -DUNALIGNED (rows_out.txt)
  picture   picture.rom and rowwise.rom photographed: every pixel against the
            picture gen15.py drew
  cart      cartridges of 8, 16 and 32 KB and of 16,385 bytes: what openMSX
            puts in each page of slot 1, and what the program finds at INIT
  big       WHERE IT BREAKS: big.asm assembled four ways, and run
  wall      every source of chapters 1 to 15 assembled with --syntax=bFw
  answers   the workshop, tried: questions 1, 3, 4, 5 and 6 (for Appendix I)
  openmsx   all of it again with every other build (tools/versions.py)

Sources are assembled for a check only in temporary folders.
"""
import glob
import json
import os
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
sys.path.insert(0, str(REPO / "ch14"))
sys.path.insert(0, str(HERE))
import meas        # noqa: E402
import msxcap      # noqa: E402
import probe       # noqa: E402
import versions    # noqa: E402
import cycles      # noqa: E402  chapter 14's price of an instruction
import gen15       # noqa: E402

CAPS = HERE / "captures"
CLOCK = probe.CLOCK
RESULTS = 0xC000


def rom(name):
    return HERE / f"{name}.rom"


def sym(name, folder=HERE):
    return probe.sym(Path(folder) / f"{name}.sym")


def tstates(a, b):
    return round((b - a) * CLOCK)


def listing(path):
    """[{line, addr, bytes, src}] for every line of a sjasmplus listing with
    bytes; the copies a macro or DUP wrote are marked > and kept; a line whose
    bytes run on to the next line is joined up"""
    out = []
    for l in Path(path).read_text().splitlines():
        m = re.match(r"\s*(\d+)\+?\s+([0-9A-F]{4}) ((?:[0-9A-F]{2}(?: |$))+)\s*(>?)\s*(.*)", l)
        if not m:
            continue
        num, addr = int(m.group(1)), int(m.group(2), 16)
        code, src = [int(x, 16) for x in m.group(3).split()], m.group(5).strip()
        if out and out[-1]["line"] == num and out[-1]["addr"] + len(out[-1]["bytes"]) == addr \
                and not src:
            out[-1]["bytes"] += code
        else:
            out.append({"line": num, "addr": addr, "bytes": code, "src": src,
                        "copy": m.group(4) == ">"})
    return out


def assemble(src_name, args, folder=HERE, text=None):
    """assemble a copy of SRC_NAME (from FOLDER, or TEXT) in a temporary
    folder: (exit code, what it printed, {file it wrote: bytes})"""
    work = Path(tempfile.mkdtemp(prefix="meas15-"))
    try:
        for f in Path(folder).glob("*"):
            if f.suffix in (".asm", ".inc", ".bin"):
                shutil.copy(f, work)
        if text is not None:
            (work / src_name).write_text(text)
        r = subprocess.run(["sjasmplus", "--nologo", *args, src_name], cwd=work,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        files = {p.name: p.read_bytes() for p in work.glob("*")
                 if p.suffix not in (".asm", ".inc", ".bin")}
        return r.returncode, r.stdout, files
    finally:
        shutil.rmtree(work, ignore_errors=True)


def vram_block(rom_path, stop, start, n, frames=4):
    lines = probe.at_address(rom_path, stop, f'binary scan [debug read_block VRAM {start} {n}] H* h; '
                                             'L "vram $h"', frames)
    return list(bytes.fromhex(next(l for l in lines if l.startswith("vram ")).split()[1]))


def word(b, i):
    return b[i] | b[i + 1] << 8


# ---------------------------------------------------------------- names
OWN = ["NAMES", "OBJECTS", "obj", "obj.cell", "obj.char", "start", "start.next", "paint",
       "paint.next", "objects"]


def names():
    s = sym("names")
    lst = listing(HERE / "names.lst")
    # every label is the address of its line in the listing; a local label's
    # full name is the global label before it, a dot, and its own
    glob_label, want = None, {}
    for l in (HERE / "names.lst").read_text().splitlines():
        m = re.match(r"\s*\d+\s+([0-9A-F]{4})(?: [0-9A-F]{2})*\s+([.\w]+):", l)
        if not m:
            continue
        name = m.group(2)
        if name.startswith("."):
            name = glob_label + name
        else:
            glob_label = name
        want[name] = int(m.group(1), 16)
    want.update({"NAMES": gen15.NAMES_ADDR, "OBJECTS": 5, "obj": 3, "obj.cell": 0,
                 "obj.char": 2})
    for n, v in want.items():
        assert s[n] == v, (n, s[n], v)
    assert all(n in want for n in OWN)
    inc = [l.split()[0] for l in (HERE / "msx.inc").read_text().splitlines()
           if re.match(r"\w+\s+EQU\s", l)]
    others = sorted(n for n in s if n not in OWN)
    assert all(n in s for n in inc)
    assert set(others) == set(inc) | (set(want) - set(OWN)) | {"VARS"}, \
        set(others) ^ (set(inc) | (set(want) - set(OWN)) | {"VARS"})
    # the records: the same 15 bytes as chapter 8's
    ours = rom("names").read_bytes()[s["objects"] - 0x4000:][:15]
    c8 = sym("records", REPO / "ch08")
    theirs = (REPO / "ch08" / "records.rom").read_bytes()[c8["objects"] - 0x4000:][:15]
    assert ours == theirs, (ours.hex(), theirs.hex())
    # run it: the name table when it has finished
    stop = next(x["addr"] for x in lst if x["src"].startswith("jr $ "))
    table = vram_block(rom("names"), stop, gen15.NAMES_ADDR, 768, frames=10)
    painted = {}
    for k in range(5):
        cell = word(ours, 3 * k) - gen15.NAMES_ADDR
        for c in range(3):
            painted[cell + c] = ours[3 * k + 2]
    for i, ch in enumerate(table):
        assert ch == painted.get(i, ord(" ")), (i, ch)
    return {"symbols": len(s), "own": {n: s[n] for n in OWN}, "inc": len(inc),
            "page": len(others) - len(inc), "cells": len(painted), "record_bytes": ours.hex(),
            "stop": stop}


# ---------------------------------------------------------------- symbols
# typed while the program runs, after it has finished its page: the
# breakpoint is set by name, and a reset runs the program again into it
SESSION = ["debug symbols load names.sym", "debug set_bp $sym(paint)", "reset",
           "format %04X [reg ix]", "debug symbols lookup -value [reg ix]"]
SESSION_AT = 5.0            # seconds after power-on: the page is finished
CHILD = """import json, sys
sys.path.insert(0, {tools!r})
import console
e = console.session({rom!r}, {lines!r}, start=("time", {at!r}))
print(json.dumps(e))
"""


def build_of(version):
    """(label, binary, share) of the OPENMSX_BUILDS line for VERSION"""
    return next((b for b in versions.builds() if b[0].split()[0] == version), None)


def session_with(version, lines):
    label, binary, share = build_of(version)
    env = dict(os.environ, MSXCAP_OPENMSX=binary, OPENMSX_SYSTEM_DATA=share)
    code = CHILD.format(tools=str(REPO / "tools"), rom=str(rom("names")), lines=lines,
                        at=SESSION_AT)
    r = subprocess.run([sys.executable, "-c", code], cwd=HERE, env=env, capture_output=True,
                       text=True, timeout=600, check=True)
    return [tuple(x) for x in json.loads(r.stdout.strip().splitlines()[-1])]


def symbols():
    if not (build_of("21.0") and build_of("19.1")):
        return {"skipped": "OPENMSX_BUILDS not set"}
    s = sym("names")
    new = session_with("21.0", SESSION)
    old = session_with("19.1", SESSION[:1])
    assert [l for l, _, _ in new] == SESSION and not any(err for _, _, err in new), new
    assert int(new[3][1], 16) == s["objects"], new
    assert new[4][1] == "{filename names.sym name objects}", new
    assert old[0][2] and "Unknown subcommand 'symbols'" in old[0][1], old
    (HERE / "symbols.txt").write_text(console_transcript(new))
    return {"session": [list(x) for x in new], "old": list(old[0]), "ix": int(new[3][1], 16)}


def console_transcript(entries):
    import console
    return console.transcript(entries)


# ---------------------------------------------------------------- exprs
def c_div(a, b):
    """division that rounds towards 0, as C does"""
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b >= 0) else -q


TRUE = -1
# each line of exprs.asm worked out again in Python: what sjasmplus should
# write, and the other reading a reader might expect
MODEL = {
    "dw 2+3*4": ([2 + 3 * 4], [(2 + 3) * 4]),
    "dw 1<<4+1": ([1 << (4 + 1)], [(1 << 4) + 1]),
    "dw 100/7*7": ([c_div(100, 7) * 7], [100]),
    "dw -7/2": ([c_div(-7, 2)], [-7 // 2]),
    "dw -7%2": ([-7 - 2 * c_div(-7, 2)], [-7 % 2]),
    "dw -16>>2": ([-16 >> 2], [(-16 & 0xFFFF) >> 2]),
    "dw -16>>>28": ([(-16 & 0xFFFFFFFF) >> 28], [(-16 & 0xFFFF) >> 28]),
    "db 3>2, 2>3": ([TRUE, 0], [1, 0]),
    "dw high $1234+1": ([(0x1234 >> 8) + 1], [(0x1234 + 1) >> 8]),
    "dw high ($1234+1)": ([(0x1234 + 1) >> 8], [(0x1234 + 1) >> 8]),
    "dw $F0 & $3C | 3": ([(0xF0 & 0x3C) | 3], [0xF0 & (0x3C | 3)]),
    "dw 7 <? 3, 7 >? 3": ([min(7, 3), max(7, 3)], [min(7, 3), max(7, 3)]),
}


def encode(expr, values):
    size = 1 if expr.startswith("db") else 2
    return [(v >> (8 * i)) & 0xFF for v in values for i in range(size)]


def exprs():
    rows = []
    lst = listing(HERE / "exprs.lst")
    assert len(lst) == len(gen15.EXPRS) == len(MODEL)
    for x, (e, note) in zip(lst, gen15.EXPRS):
        want, other = MODEL[e]
        assert x["src"].startswith(e), (x["src"], e)
        assert x["bytes"] == encode(e, want), (e, x["bytes"], want)
        rows.append({"expr": e.split(None, 1)[1], "bytes": x["bytes"], "values": want,
                     "other": other, "note": note})
    # high, low, and, or ... are operators: a label with one of their names
    text = "        ORG $4000\nstart:  call high\n        jr $\nhigh:   ret\n"
    code, out, _ = assemble("high.asm", ["--msg=war", "--syntax=bF"], text=text)
    said = sorted(set(re.sub(r"^high\.asm\((\d+)\): ", r"line \1: ", l)
                      for l in out.splitlines() if "high.asm(" in l))
    assert code == 1 and any("opkeyword" in l for l in said) and any("error" in l for l in said)
    return {"rows": rows, "high_label": said}


# ---------------------------------------------------------------- fits
def label_addr_num(path, label):
    """the address of a temporary label (a number at the margin, no colon)"""
    for l in Path(path).read_text().splitlines():
        m = re.match(r"\s*\d+\s+([0-9A-F]{4})(?: [0-9A-F]{2})*\s+" + label + r"\s", l)
        if m:
            return int(m.group(1), 16)
    raise KeyError(label)


def fits():
    lines = (HERE / "fits.lst").read_text().splitlines()
    rows, warn = [], None
    for l in lines:
        m = re.match(r"fits\.asm\((\d+)\): warning: (.*)", l)
        if m:
            warn = m.group(2)
            continue
        m = re.match(r"\s*(\d+)\s+([0-9A-F]{4}) ((?:[0-9A-F]{2} )+)\s*(?:1\s+)?(\S.*?)\s*(;.*)?$", l)
        if m:
            rows.append({"src": m.group(4), "bytes": m.group(3).split(), "warning": warn})
        warn = None
    got = {r["src"]: r for r in rows}
    assert got["ld a,256"]["bytes"] == ["3E", "00"] and got["ld a,256"]["warning"]
    assert got["ld a,-200"]["bytes"] == ["3E", f"{-200 & 0xFF:02X}"] and \
        not got["ld a,-200"]["warning"]
    assert got["db 300"]["bytes"] == [f"{300 & 0xFF:02X}"] and got["db 300"]["warning"]
    assert got["dw 70000"]["bytes"] == [f"{70000 & 0xFF:02X}", f"{70000 >> 8 & 0xFF:02X}"]
    one = label_addr_num(HERE / "fits.lst", "1")
    assert got["ld hl,1_B"]["bytes"] == ["21", f"{one & 0xFF:02X}", f"{one >> 8:02X}"]
    assert got["ld hl,1B"]["bytes"] == ["21", "01", "00"] and not got["ld hl,1B"]["warning"]
    jr = next(x for x in listing(HERE / "fits.lst") if x["src"].startswith("jr 1B"))
    assert jr["addr"] + 2 + (jr["bytes"][1] - 256) == one
    # the same source with w: every warning an error, and the exit code 1
    code_w, out_w, _ = assemble("fits.asm", ["--msg=err", "--syntax=bFw"])
    errs = [l for l in out_w.splitlines() if ": error" in l]
    (HERE / "fits_out.txt").write_text(
        "\n".join(sorted(set(errs), key=lambda l: int(re.search(r"\((\d+)\)", l).group(1)))) + "\n")
    # 1B after every instruction that jumps: the label, as after JR
    text = ("        ORG $4000\n1       nop\n        jr 1B\n        jp 1B\n"
            "        call 1B\n        djnz 1B\n        ld hl,1B\n")
    c, o, fl = assemble("jumps.asm", ["--msg=war", "--lst=jumps.lst"], text=text)
    jl = {}
    for l in fl["jumps.lst"].decode().splitlines():
        mm = re.match(r"\s*\d+\s+([0-9A-F]{4}) ((?:[0-9A-F]{2} )+)\s*(\w+) ", l)
        if mm:
            jl[mm.group(3)] = (int(mm.group(1), 16), [int(b, 16) for b in mm.group(2).split()])
    at = 0x4000
    assert c == 0 and "warning" not in o
    assert jl["jr"][1][1] == (at - (jl["jr"][0] + 2)) & 0xFF
    assert jl["djnz"][1][1] == (at - (jl["djnz"][0] + 2)) & 0xFF
    assert jl["jp"][1][1:] == [0x00, 0x40] and jl["call"][1][1:] == [0x00, 0x40]
    assert jl["ld"][1][1:] == [1, 0]
    # where a byte stops being silent: the edges of -256 to 255
    edges = {}
    for v in (-257, -256, -129, -1, 255, 256):
        text = f"        ORG $4000\n        ld a,{v}\n"
        c, o, fl = assemble("edge.asm", ["--msg=war", "--lst=edge.lst"], text=text)
        byte = re.search(r"4000 3E ([0-9A-F]{2})", fl["edge.lst"].decode()).group(1)
        edges[v] = [byte, "warning" in o]
    assert [v for v, (b, w) in edges.items() if not w] == [-256, -129, -1, 255]
    assert all(int(b, 16) == v & 0xFF for v, (b, w) in edges.items())
    code, out, files = assemble("fits.asm", ["--msg=war", "--syntax=bF", "--lst=fits.lst"])
    assert code == 0 and code_w == 1
    assert files["fits.lst"] == (HERE / "fits.lst").read_bytes()
    return {"rows": rows, "warnings": sum(1 for r in rows if r["warning"]), "exit": code,
            "exit_w": code_w, "errors_w": len(set(errs)), "one": one, "edges": edges}


# ---------------------------------------------------------------- macro
def ch12_price(instr):
    rows = json.loads((REPO / "ch12" / "meas12.json").read_text())["cost"]["rows"]
    return next(r["t"] for r in rows if r["instr"] == instr)


def macro():
    s = sym("macro")
    lst = listing(HERE / "macro.lst")
    marks = [s[f"m{k}"] for k in range(4)]
    got = probe.times(rom("macro"), {f"m{k}": a for k, a in enumerate(marks)}, extra="[reg hl]")
    t = [got[f"m{k}"][0][0] for k in range(4)]
    hl = [int(got[f"m{k}"][0][2]) for k in range(4)]
    t_macro, t_call = tstates(t[0], t[1]), tstates(t[2], t[3])
    total = sum(gen15.MACRO_N)
    assert hl[1] == total and hl[3] == total, (hl, total)
    res = probe.memory(rom("macro"), s["stop"], RESULTS, 4)
    assert word(res, 0) == word(res, 2) == total
    # the prices: chapter 14's cycles for the instructions that do not jump,
    # chapter 12's measured CALL and RET
    call, ret = ch12_price("call sub"), ch12_price("ret")
    sub, sub_end = s["addhla"], s["init"]
    body = [x for x in lst if sub <= x["addr"] < sub_end and not x["src"].startswith("ret")]
    t_body = sum(cycles.msx(x["bytes"]) for x in body)
    in_macro = [x for x in lst if marks[0] <= x["addr"] < marks[1]]
    in_call = [x for x in lst if marks[2] <= x["addr"] < marks[3]]
    model_macro = sum(cycles.msx(x["bytes"]) for x in in_macro)
    model_call = sum(call if x["src"].startswith("call") else cycles.msx(x["bytes"])
                     for x in in_call) + 8 * (t_body + ret)
    assert (t_macro, t_call) == (model_macro, model_call), (t_macro, t_call, model_macro, model_call)
    zilog_body = sum(cycles.tstates(x["bytes"]) for x in body)
    # a label inside a macro is defined again at every use; one that starts
    # with a dot is made new for every use
    waits = {}
    for lab in ("again", ".again"):
        text = ("        ORG $4000\n        MACRO WAIT n\n"
                f"        ld b,n\n{lab}: djnz {lab}\n        ENDM\n"
                "        WAIT 10\n        WAIT 20\n")
        code, out, _ = assemble("wait.asm", ["--msg=err", "--syntax=bFw"], text=text)
        waits[lab] = [code, sorted(set(l.split(": ", 1)[1] for l in out.splitlines()
                                       if ": error" in l))]
    assert waits["again"][0] == 1 and waits[".again"] == [0, []]
    b_macro, b_call = marks[1] - marks[0], marks[3] - marks[2]
    b_sub = sub_end - sub
    assert b_macro % 8 == 0 and b_call % 8 == 0
    return {"t_macro": t_macro, "t_call": t_call, "bytes_macro": b_macro, "bytes_call": b_call,
            "bytes_sub": b_sub, "sum": total, "per_use_bytes": [b_macro // 8, b_call // 8],
            "per_use_t": [t_macro // 8, t_call // 8], "t_body": t_body,
            "zilog_body": zilog_body, "call": call, "ret": ret, "waits": waits}


# ---------------------------------------------------------------- rows
def rows():
    s = sym("rows")
    data = rom("rows").read_bytes()
    lines, highs = s["lines"], s["highs"]
    low_t, high_t = data[lines - 0x4000:][:192], data[highs - 0x4000:][:192]
    for y in range(192):
        assert low_t[y] | high_t[y] << 8 == gen15.line_addr(y), y
    # chapter 13's program made the same two tables at run time, in the RAM
    c13 = sym("lines", REPO / "ch13")
    ram = probe.block(REPO / "ch13" / "lines.rom", c13["l1"], 0xD000, 512, frames=3)
    assert bytes(ram[:192]) == low_t and bytes(ram[256:448]) == high_t
    t13 = json.loads((REPO / "ch13" / "meas13.json").read_text())["lines"]["make"]
    # run: line 100 looked up
    got = probe.times(rom("rows"), {"stop": s["stop"]}, extra="[reg hl]")
    hl = int(got["stop"][0][2])
    assert hl == gen15.line_addr(100), hex(hl)
    # what sjasmplus prints, as it is and with UNALIGNED defined
    code, out, files = assemble("rows.asm", ["--msg=err", "--syntax=bFw"])
    assert code == 0 and files["rows.rom"] == data
    shown = [l for l in out.splitlines() if l.startswith(">")]
    code_u, out_u, files_u = assemble("rows.asm", ["--msg=err", "--syntax=bFw", "-DUNALIGNED"])
    (HERE / "rows_out.txt").write_text(
        "$ sjasmplus --nologo --msg=err --syntax=bFw rows.asm\n" + "\n".join(shown) + "\n"
        "$ sjasmplus --nologo --msg=err --syntax=bFw -DUNALIGNED rows.asm\n" +
        "\n".join(l for l in out_u.splitlines() if l.strip()) + "\n")
    u_errs = sorted(set(l for l in out_u.splitlines() if "error" in l))
    assert code_u == 1 and len(u_errs) == 1
    u = files_u["rows.rom"]                 # written all the same (chapter 5)
    code_c, _, files_c = assemble("rows.asm", ["--msg=err", "--syntax=bFw", "-DUNALIGNED",
                                               "--cleanonerror"])
    assert code_c == 1 and "rows.rom" not in files_c
    return {"lines": lines, "highs": highs, "end": highs + 192, "bytes": 384, "ch13_make": t13,
            "hl100": hl, "display": shown, "unaligned_exit": code_u,
            "unaligned_errors": len(u_errs), "unaligned_written": len(u)}


# ---------------------------------------------------------------- picture
PICTURE_FRAME = 20


def finished(name, frame):
    got = msxcap.capture(rom(name), [frame - 1, frame], CAPS, f"{name}_f")
    a, b = (Image.open(got[n]).convert("RGB") for n in (frame - 1, frame))
    assert a.tobytes() == b.tobytes(), f"{name}: still changing at frame {frame}"
    got[frame - 1].unlink()
    return got[frame]


def rowwise_pixel(x, y):
    """the picture's pixel that rowwise.bin puts at screen pixel (x, y): the
    screen takes the byte at pattern_offset, and the file holds line o // 32,
    cell column o % 32 there"""
    o = gen15.pattern_offset(x // 8, y)
    return gen15.ink(8 * (o % 32) + x % 8, o // 32)


def picture():
    out = {}
    for name, model in (("picture", gen15.ink), ("rowwise", rowwise_pixel)):
        png = finished(name, PICTURE_FRAME)
        px = Image.open(png).convert("L").load()
        bad = 0
        for y in range(192):
            for x in range(256):
                sx, sy = meas.paper(x, y)
                bad += (px[sx, sy] < 128) != model(x, y)
        assert bad == 0, (name, bad)
        out[name] = 256 * 192
    p, r = (HERE / "picture.bin").read_bytes(), (HERE / "rowwise.bin").read_bytes()
    assert sorted(p) == sorted(r) and p != r
    for name, b in (("picture", p), ("rowwise", r)):
        s = sym(name)
        assert rom(name).read_bytes()[s["picture"] - 0x4000:][:6144] == b
    # where rowwise.bin's lines land: line l of the file is in cell row l // 8
    # of its third ... (the first lines of the first cell column)
    firsts = [rowwise_pixel_line(0, y) for y in range(8)]
    return {"pixels": out, "bin_bytes": len(p), "frame": PICTURE_FRAME,
            "rowwise_first_lines": firsts}


def rowwise_pixel_line(x, y):
    o = gen15.pattern_offset(x // 8, y)
    return [o // 32, o % 32]


# ---------------------------------------------------------------- cart
def slot1(rom_path):
    """what openMSX puts in the four pages of slot 1, read without switching
    anything; the cartridge's mapper type; and port $A8 at INIT"""
    tcl = ("foreach p {0 1 2 3} { binary scan [debug read_block {slotted memory} "
           "[expr {4 * 0x10000 + $p * 0x4000}] 0x4000] H* h; L \"page $p $h\" }\n"
           "foreach d [machine_info device] { if {[string match \"*.rom\" $d]} "
           "{ L \"type [dict get [machine_info device $d] mappertype]\" } }\n"
           "L \"a8 [debug read ioports 0xA8]\"")
    lines = msxcap.run_tcl(rom_path, 1, tcl)
    pages = [bytes.fromhex(next(l for l in lines if l.startswith(f"page {p} ")).split()[2])
             for p in range(4)]
    kind = next(l for l in lines if l.startswith("type ")).split(None, 1)[1]
    a8 = int(next(l for l in lines if l.startswith("a8 ")).split()[1])
    return pages, kind, a8


def blocks_of(page, data):
    """which 8 KB blocks of the file a page of slot 1 shows, as "a b": the
    file is cut in blocks of 8 KB, the last one filled up with $FF"""
    blocks = [data[i:i + 0x2000] for i in range(0, len(data), 0x2000)]
    blocks[-1] += b"\xff" * (0x2000 - len(blocks[-1]))
    first, second = ([i for i, bl in enumerate(blocks) if bl == half]
                     for half in (page[:0x2000], page[0x2000:]))
    # blocks that are all $FF look alike: two in a row are taken to be in order
    pairs = [(a, b) for a in first for b in second]
    pairs = [(a, b) for a, b in pairs if b == a + 1] or pairs
    return f"{pairs[0][0]} {pairs[0][1]}" if len(pairs) == 1 else "?"


def cart():
    out = {}
    for name in ("cart8", "names", "big", "cart32"):
        data = rom(name).read_bytes()
        pages, kind, a8 = slot1(rom(name))
        shows = [blocks_of(p, data) for p in pages]
        assert "?" not in " ".join(shows), (name, shows)
        out[name] = {"bytes": len(data), "type": kind, "pages": shows, "a8": a8}
    assert {v["type"] for v in out.values()} == {"Mirrored"}
    assert out["cart8"]["pages"] == ["0 0"] * 4 and out["names"]["pages"] == ["0 1"] * 4
    assert out["cart32"]["pages"] == ["2 3", "0 1", "2 3", "0 1"]
    assert out["big"]["pages"][1] == "0 1" and out["big"]["pages"][2] == "2 2"
    # at INIT the BIOS has given page 1 to slot 1, and page 2 to slot 0:
    # cart32 finds slot 0's byte at $8000, not its own second half
    s = sym("cart32")
    got = probe.memory(rom("cart32"), s["stop"], RESULTS, 1)[0]
    c3 = json.loads((REPO / "ch03" / "meas03.json").read_text())["slots"]["default"]["grid"]
    first8000 = msxcap.run_tcl(rom("cart32"), 1, 'L "b [debug read {slotted memory} 0x8000]"')
    logo = int(next(l for l in first8000 if l.startswith("b ")).split()[1])
    assert got == logo != ord(gen15.SECOND[0]) and c3["02"][2] == "C-BIOS Logo ROM"
    assert all(v["a8"] == 0xC4 for v in out.values())
    out["cart32_found"] = got
    out["cart32_own"] = ord(gen15.SECOND[0])
    return out


# ---------------------------------------------------------------- big
BIG_FRAMES = 10
BIG_SHOWN = 5


def big():
    s = sym("big")
    data = rom("big").read_bytes()
    # the cartridges of chapters 1 to 14: how many end with TAIL's ASSERT
    carts, tails = [], []
    for f in sorted(REPO.glob("ch[0-9][0-9]/*.asm")):
        if f.parent.name >= "ch15":
            continue
        t = f.read_text()
        o = re.search(r'OUTPUT\s+"([^"]+)"', t)
        if o and o.group(1).endswith(".rom"):
            carts.append(f"{f.parent.name}/{f.name}")
            if gen15.TAIL.strip() in t:
                tails.append(carts[-1])
    without = sorted({c.split("/")[0] for c in carts if c not in tails})
    out = {"bytes": len(data), "last": s["last"], "cartridges": len(carts),
           "with_tail": len(tails), "without_in": without}
    # assembled four ways
    ways = {"bF": ["--msg=err", "--syntax=bF"], "warnings": ["--msg=war", "--syntax=bF"],
            "bFw": ["--msg=err", "--syntax=bFw"]}
    for k, args in ways.items():
        code, said, files = assemble("big.asm", args)
        out[k] = {"exit": code, "said": [l for l in said.splitlines() if l.strip()],
                  "bytes": len(files.get("big.rom", b""))}
    checked = (HERE / "big.asm").read_text().replace(gen15.TAIL, gen15.CART_END)
    assert checked != (HERE / "big.asm").read_text()
    code, said, files = assemble("checked.asm", ["--msg=err", "--syntax=bF"],
                                 text=checked.replace('"big.rom"', '"checked.rom"'))
    out["checked"] = {"exit": code, "said": [l for l in said.splitlines() if l.strip()],
                      "bytes": len(files.get("checked.rom", b""))}
    assert out["bF"] == {"exit": 0, "said": [], "bytes": 16385}
    assert out["warnings"]["exit"] == 0 and len(out["warnings"]["said"]) == 2
    assert out["bFw"]["exit"] == 1 and out["checked"]["exit"] == 1
    assert any("Assertion failed" in l for l in out["checked"]["said"])
    # run it: the RET at $8000 is not where the processor looks for it. At
    # INIT page 2 is slot 0's, C-BIOS's logo ROM (chapter 3): the processor
    # runs on into it, and its RET comes back to the program
    got = probe.times(rom("big"), {"last": s["last"], "ret": 0x8000, "stop": s["stop"]},
                      frames=BIG_FRAMES, extra="[debug read memory 0x8000] [debug read ioports 0xA8]")
    assert [len(got[k]) for k in ("last", "ret", "stop")] == [1, 1, 1], got
    seen, a8 = int(got["ret"][0][2]), int(got["ret"][0][3])
    c3 = json.loads((REPO / "ch03" / "meas03.json").read_text())["slots"]["default"]["grid"]
    assert data[0x8000 - 0x4000] == 0xC9 and seen != 0xC9 and a8 == 0xC4
    assert c3["02"][2] == "C-BIOS Logo ROM"
    away = tstates(got["ret"][0][0], got["stop"][0][0])
    # what it did meanwhile: the VRAM before the call and at stop
    before = vram_block(rom("big"), s["last"], 0, 0x4000, frames=BIG_FRAMES)
    after = vram_block(rom("big"), s["stop"], 0, 0x4000, frames=BIG_FRAMES)
    regs = probe.at_address(rom("big"), s["stop"], 'L "regs [debug read {VDP regs} 2] '
                            '[debug read {VDP regs} 3] [debug read {VDP regs} 4]"', BIG_FRAMES)
    r2, r3, r4 = (int(x) for x in next(l for l in regs if l.startswith("regs ")).split()[1:])
    names_at, patterns_at = (r2 & 0x0F) << 10, (r4 & 0x07) << 11
    changed = [i for i in range(0x4000) if before[i] != after[i]]
    in_patterns = [i for i in changed if patterns_at <= i < patterns_at + 0x800]
    in_names = [i for i in changed if names_at <= i < names_at + 0x300]
    assert len(in_patterns) + len(in_names) == len(changed)
    chars = sorted({(i - patterns_at) // 8 for i in in_patterns})
    # the photograph: still from frame 4, the border light green, the page
    # C-BIOS left changed
    shots = msxcap.capture(rom("big"), [1, BIG_SHOWN - 1, BIG_SHOWN], CAPS, "big_f")
    ims = {n: Image.open(p).convert("RGB") for n, p in shots.items()}
    assert ims[BIG_SHOWN - 1].tobytes() == ims[BIG_SHOWN].tobytes()
    assert ims[1].tobytes() != ims[BIG_SHOWN].tobytes()
    border = {ims[BIG_SHOWN].getpixel(xy) for xy in ((20, 5), (300, 120), (160, 235))}
    for n in (1, BIG_SHOWN - 1):
        shots[n].unlink()
    shots[BIG_SHOWN].replace(CAPS / "big.png")
    assert len(border) == 1
    grey = Image.new("RGB", (1, 1), next(iter(border))).convert("L").getpixel((0, 0))
    assert grey == 176, grey             # light green, as the plan's palette prints it
    out.update({"seen": seen, "own": 0xC9, "a8": a8, "away": away, "changed": len(changed),
                "patterns": len(in_patterns), "names": len(in_names), "chars": [chars[0], chars[-1]],
                "names_at": names_at, "patterns_at": patterns_at, "frame": BIG_SHOWN,
                "border": list(border.pop())})
    return out


# ---------------------------------------------------------------- wall
WRONG_ON_PURPOSE = {"ch04/case.asm", "ch05/margin.asm", "ch05/typo.asm", "ch07/fake.asm",
                    "ch08/paren.asm", "ch15/fits.asm", "ch15/big.asm"}


def wall():
    """every source of the book so far, assembled with w in a copy of its folder"""
    fails, total = {}, 0
    for folder in sorted(REPO.glob("ch[0-9][0-9]")):
        if folder.name > "ch15":
            continue
        work = Path(tempfile.mkdtemp(prefix="meas15w-"))
        try:
            for f in folder.glob("*"):
                if f.suffix in (".asm", ".inc", ".bin"):
                    shutil.copy(f, work)
            for src in sorted(work.glob("*.asm")):
                total += 1
                r = subprocess.run(["sjasmplus", "--nologo", "--msg=err", "--syntax=bFw", src.name],
                                   cwd=work, capture_output=True, text=True)
                if r.returncode:
                    first = next(l for l in (r.stdout + r.stderr).splitlines() if "error" in l)
                    fails[f"{folder.name}/{src.name}"] = first.split(": ", 1)[1]
        finally:
            shutil.rmtree(work, ignore_errors=True)
    assert set(fails) == WRONG_ON_PURPOSE, set(fails) ^ WRONG_ON_PURPOSE
    return {"sources": total, "failed": fails}


# ---------------------------------------------------------------- answers
def answers():
    out = {}
    # 1: four numbers
    text = "        ORG $4000\n        ld a,-1\n        ld a,255\n        ld a,-256\n        db 3=3\n"
    code, said, files = assemble("q1.asm", ["--msg=war", "--lst=q1.lst"], text=text)
    got = [x["bytes"] for x in listing_text(files["q1.lst"].decode())]
    assert got == [[0x3E, 0xFF], [0x3E, 0xFF], [0x3E, 0x00], [0xFF]] and "warning" not in said
    out["q1"] = {"bytes": got, "warnings": 0}
    # 3: twelve uses
    m = json.loads((HERE / "meas15.json").read_text())["macro"]
    pb, pt = m["per_use_bytes"], m["per_use_t"]
    out["q3"] = {"macro": [12 * pb[0], 12 * pt[0]],
                 "subroutine": [12 * pb[1] + m["bytes_sub"], 12 * pt[1]]}
    # 4: 250 bytes more before the tables
    src = (HERE / "rows.asm").read_text().replace(
        "        IFNDEF UNALIGNED", "        ds 250, 0\n        IFNDEF UNALIGNED")
    code, said, _ = assemble("rows.asm", ["--msg=err", "--syntax=bFw"], text=src)
    out["q4"] = [l for l in said.splitlines() if l.startswith(">")]
    assert code == 0 and out["q4"]
    # 5: a macro BORDER
    text = ('        INCLUDE "msx.inc"\n        ORG $4000\n        MACRO BORDER c\n'
            '        VDP_REG 7, c\n        ENDM\nb0:     BORDER LIGHT_GREEN\nb1:     nop\n')
    code, said, files = assemble("q5.asm", ["--msg=err", "--syntax=bFw", "--sym=q5.sym"], text=text)
    q5 = {}
    for l in files["q5.sym"].decode().splitlines():
        n, _, v = l.partition(": EQU 0x")
        q5[n.strip()] = int(v, 16)
    out["q5"] = {"bytes": q5["b1"] - q5["b0"], "t": 2 * 8 + 2 * 12}
    assert out["q5"]["bytes"] == 8
    # 6: only the first third of picture.bin
    src = (HERE / "picture.asm").read_text().replace('INCBIN "picture.bin"', 'INCBIN "picture.bin",0,2048')
    tmp = Path(tempfile.mkdtemp(prefix="q6_"))
    try:
        for f in HERE.glob("*"):
            if f.suffix in (".inc", ".bin"):
                shutil.copy(f, tmp)
        (tmp / "picture.asm").write_text(src)
        subprocess.run(["sjasmplus", "--nologo", "--msg=err", "--syntax=bFw", "--sym=picture.sym",
                        "picture.asm"], cwd=tmp, check=True)
        got = msxcap.capture(tmp / "picture.rom", [PICTURE_FRAME], tmp / "c", "q6_")
        px = Image.open(got[PICTURE_FRAME]).convert("L").load()
        inked = {}
        for third in range(3):
            inked[third] = sum(1 for y in range(64 * third, 64 * third + 64) for x in range(256)
                               if px[meas.paper(x, y)] < 128)
        # what came after the first third: the bytes of the cartridge that
        # follow, which OTIR sends all the same
        rest = (tmp / "picture.rom").read_bytes()
        s6 = probe.sym(tmp / "picture.sym")
        after = rest[s6["picture"] - 0x4000 + 2048:][:4096]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    want0 = sum(gen15.ink(x, y) for y in range(64) for x in range(256))
    assert inked[0] == want0
    out["q6"] = {"inked": inked, "first_third": want0,
                 "after_ff": sum(1 for b in after if b == 0xFF), "after": len(after)}
    return out


def listing_text(text):
    tmp = Path(tempfile.mkdtemp(prefix="lst_"))
    try:
        (tmp / "x.lst").write_text(text)
        return listing(tmp / "x.lst")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------- openmsx
OPENMSX_SECTIONS = ["names", "symbols", "exprs", "fits", "macro", "rows", "picture", "cart",
                    "big", "wall", "answers"]


def openmsx():
    if not versions.builds():
        return {"skipped": "OPENMSX_BUILDS not set"}
    return versions.every_build(["ch15"], OPENMSX_SECTIONS)


SECTIONS = {"names": names, "symbols": symbols, "exprs": exprs, "fits": fits, "macro": macro,
            "rows": rows, "picture": picture, "cart": cart, "big": big, "wall": wall,
            "answers": answers, "openmsx": openmsx}


def main(names_=()):
    CAPS.mkdir(exist_ok=True)
    path = HERE / "meas15.json"
    m = json.loads(path.read_text()) if names_ and path.exists() else {}
    if list(names_) == ["--missing"]:
        names_ = [k for k in SECTIONS if k not in m]
    for name in names_ or SECTIONS:
        print(name, flush=True)
        m[name] = SECTIONS[name]()
        m = {k: m[k] for k in SECTIONS if k in m}
        path.write_text(json.dumps(m, indent=1) + "\n")
    return m


if __name__ == "__main__":
    out = main(sys.argv[1:])
    print(json.dumps({k: out[k] for k in (sys.argv[1:] or out) if k in out}, indent=1)[:4000])
