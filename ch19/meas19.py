#!/usr/bin/env python3
"""meas19.py -- the VDP's ports, measured.

    python3 gen19.py && ./build.sh && python3 meas19.py
                                  python3 meas19.py ports regs    only these
                                  python3 meas19.py --missing      those not measured yet

  ports     ports.rom on both machines: the bytes at $0006 and $0007, read by
            the debugger and printed by the program; the three loops' times
            against their prices; the three alphabets in the photograph
  regs      regs.rom: the eight registers and the tables they point at; R#7
            and the VRAM's address after every pair of bytes, against
            vdpport.py played with the program's own lines
  address   address.rom: the bytes in the VRAM, the photograph, and the eight
            bytes from $3FFC that wrap round to $0000 (figure 19.1)
  readback  readback.rom: what the INs gave and where the OUTs went, against
            vdpport.py; the photograph (figure 19.2)
  status    status.rom on both machines: the frame flag seen with every
            interrupt off; where the loop saw it; every pixel of the
            photograph against the times (figure 19.3)
  split     WHERE IT BREAKS: split.rom, every interrupt taken and every one
            that fell between the two bytes of an address; the name table
            against the model; the photograph (figure 19.4)
  fixed     fixed.rom: the same, with the interrupts off round the address
  share     share.rom: fixed.rom with an interrupt routine that prints too; every
            interrupt taken among a text's bytes, and where the rest went
            (figure 19.5)
  whole     whole.rom: the interrupts off round each whole text
  bios      the BIOS's WRTVRM, SETWRT, RDVRM and FILVRM, followed into C-BIOS
            with the console (bios.txt), priced from their own instructions,
            and timed on both machines
  answers   the workshop, tried (for Appendix I)
  openmsx   all of it again with every other build (tools/versions.py)

Every run also counts the VDP's accesses that came too soon (openMSX's
too_fast_vram_access_callback): none may.
"""
import json
import math
import re
import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "ch14"))
sys.path.insert(0, str(HERE))
import console     # noqa: E402
import cycles      # noqa: E402
import meas        # noqa: E402
import msxcap      # noqa: E402
import probe       # noqa: E402
import screentext  # noqa: E402
import versions    # noqa: E402
import gen19       # noqa: E402
import vdpport     # noqa: E402
from asmparts import BOX_SHAPES  # noqa: E402

CAPS = HERE / "captures"
CLOCK = probe.CLOCK
EU, JP = "MSXBOOK_EU16", "MSXBOOK_JP16"
TAG = {EU: "eu", JP: "jp"}
VDP_PER_T = 6
L = 228
ROW0 = {EU: 45, JP: 18}             # the capture's first row is this line (chapter 18)
FRAME_T = {EU: 71364, JP: 59736}
POS = "[machine_info VDP_frame_count] [machine_info VDP_cycle_in_frame]"
SHOT = 10                           # the film frame photographed
PTR = "[format %02X%02X [debug read {VRAM pointer} 1] [debug read {VRAM pointer} 0]]"
REGS = "[debug read {VDP regs} 0] " + " ".join(f"[debug read {{VDP regs}} {i}]" for i in range(1, 8))
# every run: count the accesses to the VRAM that came too soon
TOO_FAST = ('set ::toofast 0\nproc ::toofast_cb {args} { incr ::toofast; L "toofast" }\n'
            'set VDP.too_fast_vram_access_callback ::toofast_cb\n')
# MSX prices of the jumps, taken and not (chapters 11 and 12); the rest from
# chapter 14's cycles.py, and OUTI from its cycles: M1 5, M1 5 + 1, MR 3, IO 4
JUMPS = {"djnz": (14, 9), "jp": (11, 11), "jr": (13, 8), "call": (18, 18), "ret": (11, 11)}
BLOCK = {(0xED, 0xA3): 18}
RET_CC = (12, 6)            # RET cc: Zilog's 11 and 5, and the M1


def rom(name):
    return HERE / f"{name}.rom"


def sym(name):
    return probe.sym(HERE / f"{name}.sym")


def run(name, frames, tcl, machine=EU, events=None):
    lines = msxcap.run_tcl(rom(name), frames, TOO_FAST + tcl, machine=machine, events=events)
    assert "toofast" not in lines, f"{name}: an access to the VRAM came too soon"
    return [l.split() for l in lines]


def equs():
    """the names of msx.inc and bios.inc"""
    out = {}
    for f in ("msx.inc", "bios.inc"):
        for line in (HERE / f).read_text().splitlines():
            m = re.match(r"^(\w+)\s+EQU\s+\$([0-9A-Fa-f]+)", line) or \
                re.match(r"^(\w+)\s+EQU\s+(\d+)", line)
            if m:
                out[m.group(1)] = int(m.group(2), 16 if "$" in line.split("EQU")[1] else 10)
    return out


def source(name, first, last):
    """the lines of NAME.asm from the one labelled FIRST to the one before LAST"""
    lines = (HERE / f"{name}.asm").read_text().splitlines()
    i = next(k for k, l in enumerate(lines) if l.startswith(first + ":"))
    j = next(k for k, l in enumerate(lines) if l.startswith(last + ":"))
    return lines[i:j]


def lst_lines(name):
    """[(source, address, bytes)] of every instruction in NAME.lst (the
    padding's ds, shown with "...", left out)"""
    out = []
    for line in (HERE / f"{name}.lst").read_text().splitlines():
        m = probe.LST.match(line)
        if not m or "..." in m.group(3)[1:13] or not m.group(3)[1:13].strip():
            continue
        _, a, code, src = probe.lst_fields(m)
        src = re.sub(r"^\s*[\w.]+:", "", src.split(";")[0].lstrip(">")).strip()
        if src and not src.lower().startswith(("db", "dw", "ds")):
            out.append((src, a, code))
    return out


def price(src, code):
    """the MSX price of one instruction, as (taken, not taken)"""
    op = src.split()[0].lower()
    if op == "ret" and len(src.split()) > 1:
        return RET_CC
    if op in JUMPS:
        return JUMPS[op]
    if tuple(code[:2]) in BLOCK:
        t = BLOCK[tuple(code[:2])]
        return t, t
    t = cycles.msx(code)
    return t, t


def segment(name, first, last):
    """[(source, address, bytes)] from the instruction at label FIRST to the
    one before label LAST"""
    s = sym(name)
    return [(src, a, c) for src, a, c in lst_lines(name) if s[first] <= a < s[last]]


def loop_price(name, start, loop, end, n):
    """T-states from START to END: the lines before LOOP once, the lines from
    LOOP to END n times, the last time with the closing jump not taken"""
    setup = sum(price(src, c)[0] for src, _, c in segment(name, start, loop))
    body = segment(name, loop, end)
    taken = sum(price(src, c)[0] for src, _, c in body)
    last = price(body[-1][0], body[-1][2])
    return setup + n * taken - (last[0] - last[1])


def hexblock(addr, n, space="VRAM"):
    return f'[debug read_block {space} {addr} {n}]'


def page(png, machine=EU):
    return screentext.Page(png, machine)


def shot(name, frames, machine=EU, keep=None):
    keep = keep if keep is not None else frames[-1]
    got = msxcap.capture(rom(name), list(frames), CAPS, f"{name}_{TAG[machine]}_f", machine=machine)
    if len(frames) == 2:
        a, b = (Image.open(got[n]).convert("RGB") for n in frames)
        assert a.tobytes() == b.tobytes(), f"{name}: the picture changes from frame to frame"
        got[frames[0]].unlink()
    return got[keep]


def dump(label, addr, n, space="VRAM"):
    """Tcl that logs N bytes of SPACE from ADDR in hexadecimal"""
    return f'binary scan [debug read_block {{{space}}} {addr} {n}] H* h; L "{label} $h"'


def dumps(w, label):
    return [bytes.fromhex(x[1]) for x in w if x[0] == label]


# ---------------------------------------------------------------- ports
def ports():
    out = {}
    s = sym("ports")
    prices = {"out_n": loop_price("ports", "l1", "w1", "l2", 26),
              "out_c": loop_price("ports", "l2", "w2", "l3", 26),
              "outi": loop_price("ports", "l3", "w3", "l4", 26)}
    per = {k: sum(price(src, c)[0] for src, _, c in segment("ports", w, e))
           for k, w, e in (("out_n", "w1", "l2"), ("out_c", "w2", "l3"), ("outi", "w3", "l4"))}
    for machine in (EU, JP):
        w = run("ports", 3, dump("mem", 6, 2, "memory"), machine)
        dr, dw = dumps(w, "mem")[0]
        t = probe.times(rom("ports"), {k: s[k] for k in ("l1", "l2", "l3", "l4")}, frames=5,
                        machine=machine)
        at = {k: t[k][0][0] for k in t}
        took = {"out_n": round((at["l2"] - at["l1"]) * CLOCK),
                "out_c": round((at["l3"] - at["l2"]) * CLOCK),
                "outi": round((at["l4"] - at["l3"]) * CLOCK)}
        assert took == prices, (machine, took, prices)
        pg = page(shot("ports", (SHOT - 1, SHOT), machine), machine)
        printed = [pg.text(2, 2, 19), pg.text(3, 2, 19)]
        assert printed == [f"VDP_DR ($0006): ${dr:02X}", f"VDP_DW ($0007): ${dw:02X}"], printed
        rows = [pg.text(r, gen19.PORT_COL, 26) for r in gen19.PORT_ROWS]
        assert rows == [gen19.ABC] * 3, rows
        out[machine] = {"vdp_dr": dr, "vdp_dw": dw, "printed": printed, "rows": rows, "took": took}
    assert out[EU]["vdp_dr"] == out[EU]["vdp_dw"] == 0x98 and out[JP]["vdp_dw"] == 0x98
    out["model"] = prices
    out["load_c"] = sum(price(src, c)[0] for src, _, c in segment("ports", "l2", "w2")[:2])
    out["per_byte"] = per
    out["setup"] = {k: prices[k] - 26 * per[k] + (5 if k != "outi" else 0) for k in per}
    return out


# ---------------------------------------------------------------- regs
REG_BASES = {2: ("names", 0x400, 32), 3: ("colours", 0x40, 32), 4: ("patterns", 0x800, 2048),
             5: ("sprite attributes", 0x80, 1)}


def regs():
    s = sym("regs")
    labels = [f"r{k}" for k in range(0, 11)]
    tcl = "\n".join(f'debug set_bp {s[k]} {{}} {{ L "{k} {POS} {PTR} {REGS} [reg a]" }}' for k in labels)
    w = run("regs", 3, tcl)
    st = {}
    for x in w:
        if x[0] in labels and x[0] not in st:
            st[x[0]] = {"frame": int(x[1]), "ptr": int(x[3], 16), "regs": [int(v) for v in x[4:12]],
                        "a": int(x[12])}
    r0 = st["r0"]["regs"]
    # the tables, at the bases r0's registers give, read a pair later, when
    # TEXT_PAGE's last byte has reached the VRAM (the VDP takes a byte at its
    # next free moment, chapter 20)
    bases = {}
    tcl2 = f'debug set_bp {s["r2"]} {{}} {{ ' + "; ".join(
        dump(f"b{r}", r0[r] * k, n) for r, (_, k, n) in REG_BASES.items()) + " }"
    w2 = run("regs", 3, tcl2)
    font, _ = screentext.font(EU)
    for r, (what, k, n) in REG_BASES.items():
        got = dumps(w2, f"b{r}")[0]
        bases[what] = {"register": r, "value": r0[r], "address": r0[r] * k, "first": got[0]}
    b = {r: dumps(w2, f"b{r}")[0] for r in REG_BASES}
    assert b[2] == b" " * 32                                  # names: every cell a space
    assert b[3] == bytes([0x1F]) * 32                        # colours: black on white
    expect = bytearray(b"".join(bytes(f) for f in font))
    for code, shape in BOX_SHAPES.items():
        expect[8 * code: 8 * code + 8] = bytes(shape)
    assert b[4] == bytes(expect)                              # patterns: the BIOS's set and the boxes
    assert b[5] == bytes([0xD0])                              # sprite attributes: none
    # the model, started from r0's registers and address, played with the lines
    eq = equs()
    port = vdpport.Port(regs=r0)
    port.addr = st["r0"]["ptr"]
    rows = []
    order = labels[1:]
    prev = "r0"
    for k in order:
        lines = source("regs", prev, k)
        before = len(port.writes)
        got = vdpport.play(port, lines, eq)
        new = port.writes[before:]
        assert port.regs == st[k]["regs"], (k, port.regs, st[k]["regs"])
        assert port.addr == st[k]["ptr"], (k, hex(port.addr), hex(st[k]["ptr"]))
        sent = [vdpport.value(re.sub(r"^\s*[\w.]+:", "", l.split(";")[0]).split(",", 1)[1], eq)
                for l in lines if "ld a," in l.replace(", ", ",")]
        rows.append({"label": k, "sent": sent, "r7": st[k]["regs"][7], "ptr": st[k]["ptr"],
                     "ins": got, "writes": new})
        prev = k
    # the stray '*', in the VRAM where the model says
    star = next(r for r in rows if r["label"] == "r6")["writes"]
    assert len(star) == 1 and star[0][1] == ord("*")
    w3 = run("regs", 3, f'debug set_bp {s["r6"]} {{}} {{ {dump("star", star[0][0], 1)} }}')
    assert dumps(w3, "star")[0] == b"*"
    # the same, typed into the console when the program reaches r6
    lines = ['debug read "VDP regs" 7', 'debug read "VRAM pointer" 1',
             'debug read "VRAM pointer" 0', f"debug read VRAM 0x{star[0][0]:04X}"]
    e = console.session(rom("regs"), lines, start=s["r6"])
    assert not any(err for _, _, err in e), e
    (HERE / "regs.txt").write_text(console.transcript(e))
    got = [int(a) for _, a, _ in e]
    assert got == [st["r6"]["regs"][7], st["r6"]["ptr"] >> 8, st["r6"]["ptr"] & 0xFF, ord("*")], got
    return {"r0": r0, "bases": bases, "rows": rows, "star_at": star[0][0], "console": got}


# ---------------------------------------------------------------- address
def address():
    s = sym("address")
    t_at = gen19.addr(*gen19.TITLE_AT)
    l_at = gen19.addr(*gen19.LONG_AT)
    c_at = gen19.addr(*gen19.CHAR0_AT)
    tcl = (f'debug set_bp {s["wr"]} {{}} {{ {dump("before", 0, 8)} }}\n'
           f'debug set_bp {s["done"]} {{}} {{ {dump("title", t_at, len(gen19.TITLE))}; '
           f'{dump("long", l_at, 64)}; {dump("top", 0x3FF8, 8)}; {dump("bottom", 0, 8)}; '
           f'{dump("c0", c_at, gen19.CHAR0_N)}; L "ptr {PTR}" }}\n')
    w = run("address", 3, tcl)
    assert dumps(w, "title")[0].decode() == gen19.TITLE
    assert dumps(w, "long")[0].decode() == gen19.LONG
    top, bottom, before = dumps(w, "top")[0], dumps(w, "bottom")[0], dumps(w, "before")[0]
    port = vdpport.Port()
    port.ctrl(gen19.WRAP_FROM & 0xFF)
    port.ctrl(gen19.WRAP_FROM >> 8 | 0x40)
    for _ in range(gen19.WRAP_N):
        port.data(0xFF)
    model = [a for a, _ in port.writes]
    assert all(top[a - 0x3FF8] == 0xFF for a in model if a >= 0x3FF8)
    assert all(bottom[a] == 0xFF for a in model if a < 8)
    assert before == bytes(8) and bottom[4:] == bytes(4)
    ptr = int(next(x for x in w if x[0] == "ptr")[1], 16)
    png = shot("address", (SHOT - 1, SHOT))
    pg = page(png)
    rows = {r: pg.line(r) for r in (2, 5, 6, 8)}
    assert rows[2][2:2 + len(gen19.TITLE)] == gen19.TITLE
    r8, c8, t8 = gen19.CHAR0_LABEL
    assert rows[r8][c8:c8 + len(t8)] == t8
    assert rows[5] + rows[6] == gen19.LONG
    px = Image.open(png).convert("RGB").load()
    r, c = gen19.CHAR0_AT
    cells = {screentext.cell(px, c + k, r) for k in range(gen19.CHAR0_N)}
    assert cells == {(255, 255, 255, 255, 0, 0, 0, 0)}, cells
    return {"wrote_to": model, "top": top.hex(), "bottom": bottom.hex(), "ptr_after": ptr,
            "char0_cell": list(cells.pop()), "rows": rows}


# ---------------------------------------------------------------- readback
def readback():
    s = sym("readback")
    n = len(gen19.WORD)
    rows = {k: gen19.addr(r, 0) for k, r in gen19.RB_ROWS.items()}
    tcl = (f'debug set_bp {s["nv"]} {{}} {{ {dump("pre", rows["naive"], 32)} }}\n'
           f'debug set_bp {s["done"]} {{}} {{ ' + "; ".join(dump(k, a, 32) for k, a in rows.items()) +
           f'; {dump("ins", 0xC120, n, "memory")} }}\n')
    w = run("readback", 3, tcl)
    vram = {k: dumps(w, k)[0] for k in rows}
    ins = list(dumps(w, "ins")[0])
    # the model: the row as it was before the loop, then the loop's port operations
    port = vdpport.Port()
    pre = dumps(w, "pre")[0]
    base = rows["naive"]
    port.vram[base:base + 32] = pre
    a = gen19.addr(gen19.RB_ROWS["naive"], gen19.RB_COL)
    port.ctrl(a & 0xFF)
    port.ctrl(a >> 8)
    got = []
    for _ in range(n):
        v = port.read()
        got.append(v)
        port.data(v | 0x20)
    assert got == ins, (got, ins)
    assert bytes(port.vram[base:base + 32]) == vram["naive"], (port.vram[base:base + 32], vram["naive"])
    word = gen19.WORD.encode()
    c = gen19.RB_COL
    assert vram["orig"][c:c + n] == word and vram["copy"][c:c + n] == word
    assert vram["right"][c:c + n] == word.lower()
    landed = [x - a for x, _ in port.writes]
    pg = page(shot("readback", (SHOT - 1, SHOT)))
    lines = {k: pg.line(r) for k, r in gen19.RB_ROWS.items()}
    assert all(lines[k].encode() == vram[k] for k in lines), lines
    return {"ins": [chr(v) for v in ins], "landed": landed, "rows": lines}


# ---------------------------------------------------------------- status
def status_one(machine):
    s = sym("status")
    sig = json.loads((REPO / "ch17" / "meas17.json").read_text())["signal"][machine]
    n = 14
    tcl = (f'set ::k 0\nset ::bs [debug set_bp {s["seen"]} {{}} {{ incr ::k; L "seen {POS} [reg a]"; '
           f'if {{$::k >= {n}}} {{ debug remove_bp $::bs }} }}]\n'
           f'debug probe set_bp VDP.IRQvertical {{}} {{ L "irq [debug probe read VDP.IRQvertical]" }}\n'
           f'debug probe set_bp z80.acceptIRQ {{}} {{ L "acc" }}\n')
    w = run("status", n + 2, tcl, machine)
    seen = [(int(x[1]), int(x[2]), int(x[3])) for x in w if x[0] == "seen"]
    assert not [x for x in w if x[0] in ("irq", "acc")], "an interrupt with bit 5 of R#1 off"
    assert len(seen) == n and len({f for f, _, _ in seen}) == n
    status = {a for _, _, a in seen}
    # the loop's turn: IN, AND, JP P; the IN that saw the flag began a turn
    # before `seen`, and the one before it, which did not, a turn earlier
    turn = sum(price(src, c)[0] for src, _, c in segment("status", "poll", "seen"))
    starts = [(c / VDP_PER_T - turn) - sig["t"] for _, c, _ in seen]
    # where the border goes black, and white again: the prices of every line
    # from `seen` to the OUT that writes each, the DJNZ loop counted whole
    band_t = gen19.BAND_TURNS * JUMPS["djnz"][0] - (JUMPS["djnz"][0] - JUMPS["djnz"][1])
    lines = segment("status", "seen", "at")
    outs = [i for i, (src, _, _) in enumerate(lines) if src.lower().startswith("out (vdp_ctrl)")]
    def t_to(i):
        t = 0
        for src, _, c in lines[:i]:
            t += band_t if src.lower().startswith("djnz") else price(src, c)[0]
        return t + 8                                 # OUT (n),A writes 8 T-states in
    t_black, t_white = t_to(outs[1]), t_to(outs[3])
    # the photograph of film frame SHOT, against the times of that frame
    png = shot("status", (SHOT,), machine)
    f0 = int(msxcap.run_tcl(rom("status"), 1, "", machine=machine)[0].split()[1])
    cyc = next(c for f, c, _ in seen if f == f0 + SHOT)
    t0 = cyc / VDP_PER_T
    black = shows_at(t0 + t_black, machine)
    white = shows_at(t0 + t_white, machine)
    px = Image.open(png).convert("RGB").load()
    count = 0
    for y in range(meas.CAPTURE_H):
        for x in range(meas.DRAWN[0], meas.DRAWN[1] + 1):
            on_paper = meas.PAPER_Y0 <= y < meas.PAPER_Y0 + meas.PAPER_H and \
                meas.PAPER_X0 <= x < meas.PAPER_X0 + meas.PAPER_W
            want = "WHITE" if on_paper else "BLACK" if black <= (y, x) < white else "LIGHT_GREEN"
            got = colour(px[x, y])
            assert got == want, (machine, x, y, got, want, black, white)
            count += 1
    return {"signal_t": sig["t"], "signal_line": sig["line"], "status": sorted(status),
            "turn": turn, "in_starts": [round(v, 2) for v in starts],
            "to_black": t_black, "to_white": t_white, "black_from": list(black),
            "white_from": list(white), "pixels": count, "frames": n}


RGB = {"BLACK": (0, 5, 0), "LIGHT_GREEN": (115, 217, 124), "WHITE": (249, 255, 248)}


def colour(px):
    """the nearest of the colours a page of this chapter uses (openMSX's, in the captures)"""
    return min(RGB, key=lambda c: sum((a - b) ** 2 for a, b in zip(RGB[c], px)))


def shows_at(t, machine):
    """(capture row, x) where a change written at frame T-state T shows"""
    line, w = divmod(t, L)
    return int(line) - ROW0[machine], math.ceil(1.5 * w - 31)


def status():
    out = {m: status_one(m) for m in (EU, JP)}
    s = sym("status")
    w = run("status", 4, f'debug set_bp {s["band"]} {{}} {{ {dump("st", 0xC110, 2, "memory")} }}')
    st = dumps(w, "st")[0]
    out["seen1"], out["seen2"] = st[0], st[1]
    assert st[0] & 0x80 and not st[1] & 0x80
    return out


# ---------------------------------------------------------------- split, fixed
N_FRAMES = 150


def window(name):
    """the addresses at which an interrupt taken falls between at's two OUTs
    to $99: after the first, up to the second"""
    s = sym(name)
    code = [(src, a) for src, a, c in lst_lines(name) if s["at"] <= a < s["putc"]]
    outs = [a for src, a in code if src.lower().replace(", ", ",") == "out (vdp_ctrl),a"]
    assert len(outs) == 2
    return [a for _, a in code if outs[0] < a <= outs[1]]


def print_window(name):
    """the addresses in print at which an interrupt taken falls after the
    address and before the text's last byte: from the instruction after
    CALL at to the loop's last"""
    s = sym(name)
    code = [(src, a) for src, a, c in lst_lines(name) if s["print"] <= a < s["isr"]]
    i = next(k for k, (src, _) in enumerate(code) if src.lower() == "call at")
    j = next(k for k, (src, _) in enumerate(code) if src.lower().startswith("jr .next"))
    return {src.split()[0].lower() + (" hl" if src.lower() in ("pop hl", "inc hl") else ""): a
            for src, a in code[i + 1: j + 1]}


def printer_run(name, kind="pair"):
    s = sym(name)
    win = window(name) if kind == "pair" else list(print_window(name).values())
    f0 = int(msxcap.run_tcl(rom(name), 1, "")[0].split()[1])
    tcl = (f'debug probe set_bp z80.acceptIRQ {{}} {{ L "acc {POS} [reg pc] {PTR} [peek {s["which"]}] '
           f'[reg hl]" }}\n')
    events = {N_FRAMES: f'{dump("nt", gen19.NAMES, 768)}; {dump("var", s["ticks"], 4, "memory")}'}
    w = run(name, N_FRAMES + 1, tcl, events=events)
    acc = [{"frame": int(x[1]) - f0, "cycle": int(x[2]), "pc": int(x[3]), "ptr": int(x[4], 16),
            "which": int(x[5]), "hl": int(x[6])} for x in w if x[0] == "acc"]
    nt = dumps(w, "nt")[0]
    var = dumps(w, "var")[0]
    ticks = var[0] | var[1] << 8
    taken = [a for a in acc if a["frame"] < N_FRAMES]
    assert len(taken) == ticks, (len(taken), ticks)          # every frame's interrupt, none lost
    hits = [a for a in taken if a["pc"] in win]
    # the model: each text where it belongs; and each text whose address was
    # split goes from the address made of the high byte the VDP had (the end
    # of the text printed before it) and the second byte, taken for a first
    texts = gen19.TEXTS
    start = [gen19.addr(r, c) for r, c, _ in texts]
    end = [a + len(t) for a, (_, _, t) in zip(start, texts)]
    model = bytearray(b" " * 768)
    strays = []
    if kind == "pair":
        for h in hits:
            k = h["which"] - 1
            before = end[k - 1] if k else end[-1]
            assert h["ptr"] == (before & 0x3F00) | (start[k] & 0xFF), (h, hex(before))
            dest = (before & 0x3F00) | (start[k] >> 8 | 0x40)
            strays.append({"frame": h["frame"], "text": texts[k][2], "at": dest, "ptr": h["ptr"],
                           "second": start[k] >> 8 | 0x40})
    else:
        # the routine's own address, after its two digits; the rest of the
        # text from the byte the interrupt found the loop at
        pw = print_window(name)
        dest = gen19.addr(*gen19.COUNT_AT) + 2
        for h in hits:
            k = h["which"] - 1
            text = texts[k][2]
            if h["pc"] == pw["pop hl"]:
                rest = 0                                # the address set, no byte yet
            else:
                rest = h["hl"] - s[f"text{k + 1}"] + (1 if h["pc"] == pw["inc hl"] else 0)
            if text[rest:]:
                strays.append({"frame": h["frame"], "text": text[rest:], "at": dest,
                               "of": text, "from": rest})
    for st in strays:
        for i, ch in enumerate(st["text"]):
            model[st["at"] - gen19.NAMES + i] = ord(ch)
    for a, (_, _, t) in zip(start, texts):
        model[a - gen19.NAMES: a - gen19.NAMES + len(t)] = t.encode()
    if kind != "pair":                                  # the routine's count, last
        c = gen19.addr(*gen19.COUNT_AT) - gen19.NAMES
        model[c: c + 2] = f"{ticks & 0xFF:02X}".encode()
    assert bytes(model) == nt, ("the name table is not the model's", bytes(model), nt)
    # the routine's count changes every frame: share and whole are photographed once
    png = shot(name, (N_FRAMES - 1, N_FRAMES) if kind == "pair" else (N_FRAMES,))
    pg = page(png)
    shown = [pg.line(r) for r in range(24)]
    assert "".join(shown).encode() == nt
    # how long each interrupt waited: from the VDP's signal (chapter 17) to the
    # moment the processor took it
    sig = json.loads((REPO / "ch17" / "meas17.json").read_text())["signal"][EU]["cycle"]
    waits = [(a["cycle"] - sig) / VDP_PER_T for a in taken]
    assert min(waits) >= 0
    return {"frames": N_FRAMES, "ticks": ticks, "first": taken[0]["frame"], "window": win,
            "wait_max": round(max(waits), 2),
            "hits": strays, "accepted_at": sorted({a["pc"] for a in taken}),
            "rows": {r: shown[r] for r in range(24) if shown[r].strip()}}


def at_call(name):
    """the address of print's CALL at, and of the instruction after it"""
    s = sym(name)
    code = [(src, a) for src, a, c in lst_lines(name) if s["print"] <= a < s["isr"]]
    k = next(i for i, (src, _) in enumerate(code) if src.lower() == "call at")
    return code[k][1], code[k + 1][1]


def at_model(name, on):
    """the price of a call of at, from its lines: the CALL, and the way
    through at with the interrupts on or off"""
    s = sym(name)
    body = [(src, a, c) for src, a, c in lst_lines(name) if s["at"] <= a < s["putc"]]
    where = {a: n for n, (_, a, _) in enumerate(body)}
    t, i = JUMPS["call"][0], 0
    while True:
        src, a, c = body[i]
        op = src.lower()
        if op.startswith("jp pe"):
            t += JUMPS["jp"][0]
            if on:                                  # P/V 1: the second LD A,I left out
                i = where[s["at.on"]]
                continue
        elif op.startswith("ret po"):
            if not on:
                t += RET_CC[0]
                break
            t += RET_CC[1]
        elif op == "ret":
            t += JUMPS["ret"][0]
            break
        else:
            t += price(src, c)[0]
        i += 1
    return t


def at_price(name, on):
    """at's price, worked out and timed: the most common time from print's
    CALL at to the instruction after, over forty calls (an interrupt in
    between makes a call longer)"""
    from collections import Counter
    c, r = at_call(name)
    t = probe.times(rom(name), {"c": c, "r": r}, frames=6, hits=40)
    took = Counter(round((b[0] - a[0]) * CLOCK) for a, b in zip(t["c"], t["r"]))
    best, n = took.most_common(1)[0]
    model = at_model(name, on)
    assert best == model, (name, took, model)
    return {"t": best, "calls": len(t["c"]), "same": n}


def split():
    out = printer_run("split")
    assert len({h["text"] for h in out["hits"]}) == 3
    out["at"] = at_price("split", True)
    return out


def fixed():
    out = printer_run("fixed")
    assert not out["hits"]
    s = sym("fixed")
    # the interrupts that came while at had them off were taken after its
    # EI and the instruction after it: back in print, at the POP HL
    back = s["print"] + 4                     # PUSH HL (1), CALL at (3)
    out["after_ei"] = sum(1 for pc in out["accepted_at"] if pc == back)
    out["at"] = at_price("fixed", True)
    return out


def share():
    out = printer_run("share", "bytes")
    assert out["hits"]
    return out


def whole():
    out = printer_run("whole", "bytes")
    assert not out["hits"]
    out["at"] = at_price("whole", False)                # called with the interrupts off
    return out


# ---------------------------------------------------------------- bios
BIOS_SESSION = ["disasm 0x004D 1", "disasm [peek16 0x004E] 5", "disasm [peek16 0x0054] 9",
                "disasm 0x004A 1", "disasm [peek16 0x004B] 4"]
CALLS = {"WRTVRM": ("c1", "a1"), "SETWRT": ("c2", "a2"), "RDVRM": ("c3", "a3"),
         "FILVRM": ("c4", "a4")}


def disasm_map(text):
    """{address: (instruction, bytes)} from the console's disasm"""
    out = {}
    for line in text.splitlines():
        m = re.match(r"^([0-9A-F]{4})\s+(.*?)\s{2,}((?:[0-9A-F]{2} ?)+)$", line)
        if m:
            out[int(m.group(1), 16)] = (" ".join(m.group(2).split()),
                                        [int(b, 16) for b in m.group(3).split()])
    return out


def run_code(code, entry, regs):
    """the price of a call to ENTRY, played instruction by instruction
    through CODE (the disassembly), with B and C followed for the loops"""
    pc, stack, t, z = entry, ["back"], JUMPS["call"][0], False
    r = dict(regs)
    while pc != "back":
        ins, b = code[pc]
        nxt = pc + len(b)
        op, _, arg = ins.partition(" ")
        if op == "call":
            stack.append(nxt)
            t += JUMPS["call"][0]
            pc = int(arg[1:], 16)
            continue
        if op == "ret":
            t += JUMPS["ret"][0]
            pc = stack.pop()
            continue
        if op == "jp":
            t += JUMPS["jp"][0]
            pc = int(arg[1:], 16)
            continue
        if op == "jr":
            cond, target = arg.split(",")
            taken = not z if cond == "nz" else None
            t += JUMPS["jr"][0] if taken else JUMPS["jr"][1]
            pc = int(target[1:], 16) if taken else nxt
            continue
        if ins == "dec bc":
            v = ((r["b"] << 8 | r["c"]) - 1) & 0xFFFF
            r["b"], r["c"] = v >> 8, v & 0xFF
        elif ins in ("dec b", "dec c", "inc c"):
            reg = ins[-1]
            r[reg] = (r[reg] + (1 if ins.startswith("inc") else -1)) & 0xFF
            z = r[reg] == 0
        elif ins == "ld a,b":
            r["a"] = r["b"]
        elif ins == "ld b,c":
            r["b"] = r["c"]
        elif ins == "ld c,a":
            r["c"] = r["a"]
        t += cycles.msx(b)
        pc = nxt
    return t


def bios():
    e = console.session(rom("bios"), BIOS_SESSION)
    assert not any(err for _, _, err in e), e
    (HERE / "bios.txt").write_text(console.transcript(e))
    e2 = console.session(rom("bios"), ["disasm 0x0040 12", "disasm 0x0245 60"])
    code = {}
    for _, text, _ in e2:
        code.update(disasm_map(text))
    eq = equs()
    model = {"WRTVRM": run_code(code, eq["WRTVRM"], {}),
             "SETWRT": run_code(code, eq["SETWRT"], {}),
             "RDVRM": run_code(code, eq["RDVRM"], {}),
             "FILVRM": run_code(code, eq["FILVRM"], {"b": 0, "c": gen19.FILL_N, "a": 0})}
    s = sym("bios")
    labels = {k: s[k] for pair in CALLS.values() for k in pair}
    out = {"model": model}
    for machine in (EU, JP):
        t = probe.times(rom("bios"), labels, frames=5, extra="[reg iff]", machine=machine)
        took = {n: round((t[a][0][0] - t[c][0][0]) * CLOCK) for n, (c, a) in CALLS.items()}
        iff = {n: int(t[a][0][2]) != 0 for n, (c, a) in CALLS.items()}
        assert took == model, (machine, took, model)
        assert all(iff.values())                        # every one: the interrupts on after
        w = run("bios", 4, f'debug set_bp {s["a4"]} {{}} {{ {dump("v", gen19.NAMES, 768)}; '
                           f'{dump("got", s["got"], 1, "memory")} }}', machine)
        v = dumps(w, "v")[0]
        a = gen19.addr(*gen19.BIOS_AT) - gen19.NAMES
        f = gen19.addr(*gen19.FILL_AT) - gen19.NAMES
        assert v[a:a + 2] == b"WS" and v[f:f + gen19.FILL_N] == b"-" * gen19.FILL_N
        assert dumps(w, "got")[0] == b"W"
        out[machine] = {"took": took, "iff_on": iff}
    body = disasm_map(e[2][1])
    out["setwrt"] = [ins for ins, _ in body.values()]
    assert out["setwrt"][0] == "di" and out["setwrt"][-2:] == ["ei", "ret"]
    return out


# ---------------------------------------------------------------- answers
def build_temp(name, text):
    import shutil
    import subprocess
    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix=f"{name}_"))
    (tmp / f"{name}.asm").write_text(text)
    for inc in ("msx.inc", "bios.inc"):
        shutil.copy(HERE / inc, tmp)
    subprocess.run(["sjasmplus", "--nologo", "--msg=err", "--syntax=bFw", f"--sym={name}.sym",
                    f"{name}.asm"], cwd=tmp, check=True)
    return tmp


def run_temp(name, body, tcl):
    """a cartridge of BODY after TEXT_PAGE, run with TCL at its label `stop`"""
    import shutil
    text = gen19.head(name, "a workshop answer, tried") + gen19.TEXT_PAGE + body + \
        "stop:   jr stop\n" + gen19.library() + gen19.CART_END
    tmp = build_temp(name, text)
    try:
        s = probe.sym(tmp / f"{name}.sym")
        lines = msxcap.run_tcl(tmp / f"{name}.rom", 4, TOO_FAST +
                               f'set ::bs [debug set_bp {s["stop"]} {{}} {{ {tcl}; L "end"; '
                               f'debug remove_bp $::bs }}]\n')
        assert "toofast" not in lines
        return [l.split() for l in lines]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def answers():
    out = {}
    # 1: the VRAM read from $3A10: $10 first, then $3A
    w = run_temp("q1", """        VRAM_WRITE $3A10
        ld a, 'Q'
        out (VDP_DATA), a
        nop
        nop
        nop
        ld a, $10
        out (VDP_CTRL), a
        ld a, $3A
        out (VDP_CTRL), a
        nop
        nop
        nop
        nop
        in a, (VDP_DATA)
""", 'L "a [reg a]"')
    out["q1"] = chr(int(next(x for x in w if x[0] == "a")[1]))
    assert out["q1"] == "Q"
    # 2: $07, then $C8: register 0 takes the $07
    w = run_temp("q2", """        ld a, $07
        out (VDP_CTRL), a
        ld a, $C8
        out (VDP_CTRL), a
""", f'L "r {REGS}"')
    out["q2"] = [int(v) for v in next(x for x in w if x[0] == "r")[1:]]
    assert out["q2"][0] == 0x07 & 0x03                   # R#0 keeps its two bits
    # 4: a read address, then three OUTs and no IN: one cell on, and on
    a = 0x1900
    w = run_temp("q4", f"""        ld a, ${a & 0xFF:02X}
        out (VDP_CTRL), a
        ld a, ${a >> 8:02X}               ; read
        out (VDP_CTRL), a
        nop
        nop
        nop
        nop
        ld b, 3
q4a:    ld a, 'X'
        out (VDP_DATA), a
        nop
        nop
        nop
        djnz q4a
        nop
        nop
        nop
""", dump("v", a, 6))
    v = dumps(w, "v")[0]
    out["q4"] = [i for i in range(6) if v[i] == ord("X")]
    assert out["q4"] == [1, 2, 3]
    # 5: where the band began, frame after frame
    st = json.loads((HERE / "meas19.json").read_text())["status"]
    xs = {}
    for m in (EU, JP):
        sig = st[m]["signal_t"]
        starts = [sig + d + st[m]["turn"] for d in st[m]["in_starts"]]
        xs[m] = [shows_at(t + st[m]["to_black"], m)[1] for t in starts]
    out["q5"] = {m: [min(x), max(x)] for m, x in xs.items()}
    return out


# ---------------------------------------------------------------- openmsx
OPENMSX_SECTIONS = ["ports", "regs", "address", "readback", "status", "split", "fixed", "share",
                    "whole", "bios", "answers"]


def openmsx():
    if not versions.builds():
        return {"skipped": "OPENMSX_BUILDS not set"}
    return versions.every_build(["ch19"], OPENMSX_SECTIONS)


SECTIONS = {"ports": ports, "regs": regs, "address": address, "readback": readback,
            "status": status, "split": split, "fixed": fixed, "share": share, "whole": whole,
            "bios": bios, "answers": answers, "openmsx": openmsx}


def main(names=()):
    CAPS.mkdir(exist_ok=True)
    path = HERE / "meas19.json"
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
