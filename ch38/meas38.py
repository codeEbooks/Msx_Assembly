#!/usr/bin/env python3
"""meas38.py -- slots and memory, measured.

    python3 gen38.py && ./build.sh && python3 meas38.py
                                  python3 meas38.py pages carts      only these

  pages     pages.rom on the five machines: the screen against the debugger
            (port $A8, EXPTBL, SLTTBL, slotselect, and each expanded slot's
            register, read through openMSX's "slotted memory") and against
            the machine files (what each page shows); photos (figure 38.1)
  carts     cart32, own32, quick32 and stay32 on the five machines: the slot
            page 2 shows after the switch, the line, the sum, against a model
            of each way of switching; photos (figures 38.2 and 38.3)
  enaslt    C-BIOS's ENASLT watched on the expander: its writes to port $A8
            and to $FFFF against a model read from its source; twelve
            machines made for the purpose, the RAM and the expander in every
            pair of slots, with C-BIOS as it is and with the one byte its bug
            report names changed
  prices    the T-states of here, setpage2, quick and subreg: walk.py (the
            listing's prices) against the debugger; RSLREG and ENASLT from the
            debugger; how long page 3 is not RAM
  breaks    WHERE IT BREAKS: stay32 and quick32 followed into page 2
  same      chapter 37's tune.rom on three machines: the same writes to the
            PSG, at the same T-states after each interrupt
  memory    where the book's programs keep their bytes: the RAM labels of every
            .sym in the repository; tune.rom's writes to $C000-$FFFF
  standard  openMSX's MSX1 machines: the slot of the RAM under the BIOS's work
            area, the cartridge slots, the expanded ones
  answers   the workshop, tried (for Appendix I)
  openmsx   all of it again with every other build (tools/versions.py)
"""
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "tools"))
import meas        # noqa: E402
import msxcap      # noqa: E402
import probe as dbg  # noqa: E402
import versions    # noqa: E402
sys.path.insert(0, str(HERE))
import gen38       # noqa: E402
import gen34       # noqa: E402
sys.path.remove(str(HERE))
sys.path.insert(0, str(HERE))      # gen38 put chapters 34 and 35 first: this folder's files win
for mod in ("vdpscreen", "walk"):
    sys.modules.pop(mod, None)
import vdpscreen   # noqa: E402
import walk        # noqa: E402  (chapter 25's, with what chapters 28 to 32 added)

assert Path(vdpscreen.__file__).parent == HERE and Path(walk.__file__).parent == HERE

CAPS = HERE / "captures"
EU, JP, EXP_RAM, EXPANDER, BIG = gen38.EU, gen38.JP, gen38.EXP_RAM, gen38.EXPANDER, gen38.BIG
MACHINES = gen38.MACHINES
TAG = {EU: "eu", EXP_RAM: "eux", EXPANDER: "eue", BIG: "eu64", JP: "jp"}
CLOCK = dbg.CLOCK
FRAME_T = {EU: 71364, EXP_RAM: 71364, EXPANDER: 71364, BIG: 71364, JP: 59736}
PALETTE = [tuple(c) for c in json.loads((REPO / "ch01" / "meas01.json").read_text())["palette"]["rgb"]]
CODE = {rgb: n for n, rgb in enumerate(PALETTE) if n}
LOGO = msxcap.CBIOS / "cbios_logo_msx1.rom"
SHOT = 30                       # the frame of every photo: the programs are done by then
WORKERS = 6

# the state of the machine, logged under a tag: the BIOS's tables, what $FFFF
# reads with page 3 on each primary slot (openMSX's "slotted memory": the
# register, complemented, for an expanded slot; the byte at $FFFF for one
# that is not), port $A8, slotselect, the CPU, the program's variables and the
# names of the screen
STATE = r"""
proc S {tag} {
    set v {}
    foreach a {0xFCC1 0xFCC2 0xFCC3 0xFCC4} { lappend v [debug read memory $a] }
    L "$tag exp $v"
    set v {}
    foreach a {0xFCC5 0xFCC6 0xFCC7 0xFCC8} { lappend v [debug read memory $a] }
    L "$tag slt $v"
    set v {}
    for {set p 0} {$p < 4} {incr p} { lappend v [debug read {slotted memory} [expr {($p << 18) | 0xFFFF}]] }
    L "$tag ffff $v"
    L "$tag a8 [debug read ioports 0xA8]"
    L "$tag sel [string map {\n |} [slotselect]]"
    L "$tag cpu [reg pc] [reg sp] [reg iff] [expr {[machine_info VDP_frame_count] - $::f0}]"
    set v {}
    for {set i 0} {$i < 16} {incr i} { lappend v [debug read memory [expr {0xC100 + $i}]] }
    L "$tag vars $v"
    binary scan [debug read_block VRAM 0x1800 768] H* h
    L "$tag names $h"
}
proc V {tag} {
    binary scan [debug read_block VRAM 0 16384] H* h
    L "$tag vram $h"
    set v {}
    for {set i 0} {$i < 8} {incr i} { lappend v [debug read {VDP regs} $i] }
    L "$tag regs $v"
}
"""
SEL = re.compile(r"([0-9A-F]{4}): slot (\d)(?:\.(\d))?")


def rom(name):
    return HERE / f"{name}.rom"


def sym(name):
    return dbg.sym(HERE / f"{name}.sym")


def t_state(seconds):
    t = float(seconds) * CLOCK
    assert abs(t - round(t)) < 1e-3, seconds
    return round(t)


def run(rom_path, machine, frames, at_init="", events=None, setup=""):
    """the log of a run, split into words"""
    lines = msxcap.run_tcl(rom_path, frames, at_init, machine=machine, events=events or {},
                           tcl_setup=STATE + setup, timeout=900)
    return [l.split() for l in lines]


def parallel(jobs, fn):
    with ThreadPoolExecutor(WORKERS) as ex:
        return list(ex.map(fn, jobs))


def state(w, tag):
    """the values S logged under TAG"""
    out = {}
    for x in w:
        if x[0] != tag or len(x) < 2:
            continue
        k, v = x[1], x[2:]
        if k in ("exp", "slt", "ffff", "vars"):
            out[k] = [int(a) for a in v]
        elif k == "a8":
            out[k] = int(v[0])
        elif k == "sel":
            out[k] = [(int(p), None if s == "" else int(s)) for _, p, s in SEL.findall(" ".join(v))]
        elif k == "cpu":
            out["pc"], out["sp"], out["iff"], out["frame"] = (int(a) for a in v)
        elif k == "names":
            out[k] = list(bytes.fromhex(v[0]))
        elif k == "vram":
            out[k] = bytes.fromhex(v[0])
        elif k == "regs":
            out[k] = [int(a) for a in v]
    return out


def slot_id(p, s):
    """the BIOS's slot ID, E000SSPP"""
    return p if s is None else 0x80 | s << 2 | p


def slot_text(p, s):
    return f"{p}" if s is None else f"{p}-{s}"


def reg_of(st, p):
    """the secondary slot register of primary slot P: the debugger's read, complemented"""
    return ~st["ffff"][p] & 255


# ---------------------------------------------------------------- the machine files
def machine_xml(machine, folder=None):
    """{(primary, secondary or None): [(device id, base, size)]}, the expanded
    primary slots, the external slots in the order the file gives them"""
    root = ET.parse((folder or REPO / "machines") / f"{machine}.xml").getroot()
    slots, expanded, external = {}, set(), []

    def walk_(node, p, s):
        for ch in node:
            if ch.tag == "primary":
                pp = int(ch.get("slot"))
                if ch.get("external") == "true":
                    external.append((pp, None))
                walk_(ch, pp, None)
            elif ch.tag == "secondary":
                expanded.add(p)
                ss = int(ch.get("slot"))
                if ch.get("external") == "true":
                    external.append((p, ss))
                walk_(ch, p, ss)
            elif p is not None:
                for m in ch.findall("mem"):
                    slots.setdefault((p, s), []).append((ch.get("id"), int(m.get("base"), 0),
                                                         int(m.get("size"), 0)))
    walk_(root.find("devices"), None, None)
    return slots, expanded, external


def device_at(xml, slot, address):
    """what the machine file puts at ADDRESS in SLOT: a device's id, "cartridge"
    for the slot the cartridge goes in, None for nothing"""
    slots, _, external = xml
    if slot == external[0]:
        return "cartridge"
    for dev, base, size in slots.get(slot, []):
        if base <= address < base + size:
            return "C-BIOS Main ROM" if dev.startswith("C-BIOS Main ROM") else dev
    return None


def expect_pages(xml):
    """what each page shows at INIT, by the machine file: the BIOS, the
    cartridge, the RAM in page 2 if the machine has some there or else the
    logo ROM that shares slot 0 with the BIOS (chapter 15), and the RAM"""
    slots = xml[0]
    ram2 = any(dev == "Main RAM" and base <= 0x8000 < base + size
               for devs in slots.values() for dev, base, size in devs)
    return ["C-BIOS Main ROM", "cartridge", "Main RAM" if ram2 else "C-BIOS Logo ROM", "Main RAM"]


# ---------------------------------------------------------------- screens
def codes(png):
    im = Image.open(png).convert("RGB")
    px = im.load()
    return [[CODE.get(px[x, y]) for x in range(im.width)] for y in range(im.height)]


def mismatch(model, photo):
    return sum(1 for y in range(meas.CAPTURE_H) for x in range(meas.DRAWN[0], meas.DRAWN[1] + 1)
               if model[y][x] != photo[y][x])


def capture_of(paper, border):
    return [[(paper[y - meas.PAPER_Y0][x - meas.PAPER_X0]
              if 0 <= x - meas.PAPER_X0 < 256 and 0 <= y - meas.PAPER_Y0 < 192 else border)
             if meas.DRAWN[0] <= x <= meas.DRAWN[1] else None
             for x in range(meas.CAPTURE_W)] for y in range(meas.CAPTURE_H)]


def screen(names):
    """the capture a program of this chapter makes with these names"""
    v = bytearray(16384)
    v[0:1024] = bytes(gen34.own_shapes())
    v[0x2000:0x2020] = bytes([0x1F]) * 32
    v[0x1800:0x1B00] = bytes(names)
    v[0x1B00] = 0xD0
    return capture_of(vdpscreen.draw(v, gen34.TEXT_REGS), 15)


def from_vram(vram, regs):
    """the capture the VRAM and the registers make, drawn by vdpscreen"""
    return capture_of(vdpscreen.draw(bytearray(vram), regs), regs[7] & 15)


def put(names, row, col, text):
    for i, ch in enumerate(text):
        names[32 * row + col + i] = ord(ch)


def text_at(names, row, col, n):
    return "".join(chr(c) for c in names[32 * row + col: 32 * row + col + n])


def photo(prog, machine, frame=SHOT):
    """a photo of PROG on MACHINE at FRAME, in captures/"""
    return msxcap.capture(rom(prog), [frame], CAPS, f"{prog}_{TAG[machine]}_f", machine=machine,
                          timeout=900)[frame]


# ---------------------------------------------------------------- pages
def pages_names(st):
    """the names pages.asm should have printed, from the debugger's values"""
    r, c = gen38.P_ROWS, gen38.P_COLS
    n = gen34.page(gen38.pages_texts())
    put(n, r["a8"], c["a8"], f"{st['a8']:02X}")
    for page, (p, s) in enumerate(st["sel"]):
        put(n, r["pages"] + 1 + page, c["slot"], slot_text(p, s))
        put(n, r["pages"] + 1 + page, c["id"], f"{slot_id(p, s):02X}")
    for p in range(4):
        row = r["slots"] + 1 + p
        put(n, row, c["exp"], f"{st['exp'][p]:02X}")
        put(n, row, c["slt"], f"{st['slt'][p]:02X}")
        put(n, row, c["reg"], f"{reg_of(st, p):02X}" if st["exp"][p] & 0x80 else "--")
    return n


def pages_one(machine):
    w = run(rom("pages"), machine, 12, events={10: "S at"})
    st = state(w, "at")
    xml = machine_xml(machine)
    model = pages_names(st)
    assert st["names"] == model, (machine, "the screen is not the debugger's values")
    want = expect_pages(xml)
    shows = [device_at(xml, sl, 0x4000 * page) for page, sl in enumerate(st["sel"])]
    assert shows == want, (machine, shows, want)
    assert [e & 0x80 for e in st["exp"]] == [0x80 if p in xml[1] else 0 for p in range(4)], machine
    # each page of an expanded slot: the register's field is the secondary slotselect shows
    for page, (p, s) in enumerate(st["sel"]):
        if s is not None:
            assert reg_of(st, p) >> 2 * page & 3 == s, (machine, page)
    png = photo("pages", machine, 10)
    assert mismatch(screen(model), codes(png)) == 0, (machine, "photo")
    slots, _, external = xml
    layout = {slot_text(*sl): [f"{dev} {base:04X}-{base + size - 1:04X}" for dev, base, size in devs]
              for sl, devs in sorted(slots.items(), key=lambda x: (x[0][0], x[0][1] or 0))}
    for e in external:
        layout.setdefault(slot_text(*e), []).append("socket")
    return {"layout": dict(sorted(layout.items())),
            "a8": f"{st['a8']:02X}",
            "pages": [slot_text(*sl) for sl in st["sel"]],
            "ids": [f"{slot_id(*sl):02X}" for sl in st["sel"]],
            "shows": shows,
            "exptbl": [f"{v:02X}" for v in st["exp"]],
            "slttbl": [f"{v:02X}" for v in st["slt"]],
            "registers": {str(p): f"{reg_of(st, p):02X}" for p in range(4) if st["exp"][p] & 0x80},
            "photo": png.name}


def pages():
    out = dict(zip((TAG[m] for m in MACHINES), parallel(MACHINES, pages_one)))
    # C-BIOS's copy and the register itself, where they differ
    out["slttbl_wrong"] = [f"{t} slot {p}: SLTTBL {out[t]['slttbl'][p]}, register {r}"
                           for t in out for p, r in ((int(k), v) for k, v in out[t]["registers"].items())
                           if out[t]["slttbl"][p] != r]
    return out


# ---------------------------------------------------------------- the four ways to switch page 2
def cbios_enaslt(a8, look, sid, page, fixed=False):
    """C-BIOS 0.29a's ENASLT as slot.asm reads: A = SID, the page in H. For an
    expanded slot it shows the slot's primary in page 3 with
    "in a,(PSL_STAT) / and $C0 / or h / out (PSL_STAT),a", reads $FFFF,
    changes the page's two bits, writes $FFFF back, puts page 3 back and
    copies the byte into SLTTBL for the slot; then it sets the page's primary
    slot in port $A8. FIXED: "and $3F", the line its bug report asks for.
    LOOK(p) is what $FFFF reads with page 3 on primary slot p. Returns (the
    bytes written to port $A8, (the primary slot whose $FFFF is written, the
    byte) or None, port $A8 at the end)"""
    p, s = sid & 3, sid >> 2 & 3
    shift = 2 * page
    mask = 3 << shift
    outs, wrote = [], None
    if sid & 0x80:
        sel = (a8 & (0x3F if fixed else 0xC0)) | p << 6
        outs.append(sel)
        on = sel >> 6                           # the slot page 3 shows while $FFFF is read
        wrote = (on, (~look(on) & 255 & ~mask & 255) | s << shift)
        outs.append(a8)
    end = (a8 & ~mask & 255) | p << shift
    outs.append(end)
    return outs, wrote, end


def own_page2(a8, regs, sid):
    """setpage2 of own32: (port $A8 after, {slot: its register after})"""
    p, s = sid & 3, sid >> 2 & 3
    regs = dict(regs)
    if sid & 0x80:
        regs[p] = regs[p] & 0xCF | s << 4
    return a8 & 0xCF | p << 4, regs


def after_switch(prog, init, sid, fixed=False):
    """(page 2's slot after PROG's switch, by the model, SLTTBL for the
    cartridge's slot after it, or None if the switch leaves it alone), from the
    state at INIT"""
    a8 = init["a8"]
    regs = {p: reg_of(init, p) for p in range(4) if init["exp"][p] & 0x80}
    slt = None
    if prog == "cart32":
        _, wrote, a8 = cbios_enaslt(a8, lambda p: init["ffff"][p], sid, 2, fixed)
        if wrote:
            on, byte = wrote
            if on in regs:
                regs[on] = byte
            slt = byte
    elif prog == "own32":
        a8, regs = own_page2(a8, regs, sid)
        if sid & 0x80:
            slt = regs[sid & 3]
    elif prog == "quick32":
        a8 = a8 & 0xCF | (a8 >> 2 & 3) << 4
    p2 = a8 >> 4 & 3
    return (p2, regs[p2] >> 4 & 3 if p2 in regs else None), slt


def rom_sum(data):
    return sum(data) & 0xFFFF


def cart_names(prog, v, line, total):
    """the names a 32 KB cartridge of this chapter should have printed, from
    its variables (VARS: a8, a8now, myslot, sltwas, sltnow, -, sum)"""
    r, c = gen38.C_ROWS, gen38.C_COLS
    n = gen34.page(gen38.cart_texts(prog))
    sid = v[2]
    put(n, r["slot"], c["value"], f"{sid:02X}")
    put(n, r["slot"], c["name"], slot_text(sid & 3, sid >> 2 & 3 if sid & 0x80 else None))
    put(n, r["a8"], c["value"], f"{v[0]:02X}")
    put(n, r["a8"], c["after"], f"{v[1]:02X}")
    put(n, r["slt"], c["value"], f"{v[3]:02X}")
    put(n, r["slt"], c["after"], f"{v[4]:02X}")
    if line:
        put(n, r["line"], 0, gen38.LINE)
    if total is not None:
        put(n, r["sum"], c["value"], f"{total:04X}")
    return n


def cart_one(job, folder=None):
    """PROG on MACHINE: the state at INIT and at frame SHOT, against the model"""
    prog, machine = job[:2]
    fixed = len(job) > 2 and job[2]
    w = run(rom(prog), machine, SHOT + 1, at_init="S init", events={SHOT: "S end"})
    init, end = state(w, "init"), state(w, "end")
    xml = machine_xml(machine, folder)
    cart = xml[2][0]
    sid = slot_id(*cart)
    v = end["vars"]
    page2, slt = after_switch(prog, init, sid, fixed)
    content = device_at(xml, page2, 0x8000)
    image = rom(prog).read_bytes()
    sums = {"cartridge": rom_sum(image[0x4000:0x8000]), "C-BIOS Logo ROM": rom_sum(LOGO.read_bytes())}
    line = text_at(end["names"], gen38.C_ROWS["line"], 0, len(gen38.LINE)) == gen38.LINE
    shown = text_at(end["names"], gen38.C_ROWS["sum"], gen38.C_COLS["value"], 4)
    total = int(shown, 16) if shown.strip() else None
    s = sym(prog)
    # the program's own reading of its slot, port $A8 and SLTTBL, against the debugger
    assert v[2] == sid and v[0] == init["a8"] and v[3] == init["slt"][cart[0]], (prog, machine)
    assert end["sel"][2] == page2, (prog, machine, "page 2", end["sel"][2], page2)
    if slt is not None:
        assert v[4] == slt, (prog, machine, "SLTTBL", v[4], slt)
    assert line == (content == "cartridge"), (prog, machine, "line")
    if total is not None:
        assert total == sums[content] == v[6] | v[7] << 8, (prog, machine, "sum")
    done = end["pc"] == s["init.end"]
    if content == "cartridge":
        assert done and total is not None and end["names"] == cart_names(prog, v, True, total), (prog, machine)
        # RSLREG and ENASLT, or none of the BIOS, and the interrupts still off at the end
        assert end["iff"] == 0, (prog, machine, "interrupts")
    return {"slot": slot_text(*cart), "id": f"{sid:02X}", "a8": [f"{v[0]:02X}", f"{v[1]:02X}"],
            "slttbl": [f"{v[3]:02X}", f"{v[4]:02X}"], "page2": slot_text(*page2), "content": content,
            "line": line, "sum": None if total is None else f"{total:04X}", "ended": done,
            "pc": f"{end['pc']:04X}", "iff": end["iff"]}


CART_SHOTS = [("cart32", EU), ("own32", EXPANDER), ("cart32", EXPANDER), ("stay32", EU),
              ("quick32", EXPANDER)]


def cart_photo(job):
    """a photo at frame SHOT, and the frame drawn from the VRAM read then"""
    prog, machine = job
    w = run(rom(prog), machine, SHOT + 1, events={SHOT: "S end; V end"})
    end = state(w, "end")
    png = photo(prog, machine)
    ph = codes(png)
    drawn = mismatch(from_vram(end["vram"], end["regs"]), ph)
    v = end["vars"]
    printed = text_at(end["names"], gen38.C_ROWS["line"], 0, len(gen38.LINE)) == gen38.LINE
    model = None
    if printed:
        model = mismatch(screen(cart_names(prog, v, True, v[6] | v[7] << 8)), ph)
    return {"photo": png.name, "against_vram": drawn, "against_model": model,
            "regs": [f"{r:02X}" for r in end["regs"]]}


def carts():
    jobs = [(p, m) for p in gen38.CARTS for m in MACHINES]
    res = parallel(jobs, cart_one)
    out = {p: {} for p in gen38.CARTS}
    for (p, m), r in zip(jobs, res):
        out[p][TAG[m]] = r
    out["photos"] = {f"{p}_{TAG[m]}": r for (p, m), r in zip(CART_SHOTS, parallel(CART_SHOTS, cart_photo))}
    for k, r in out["photos"].items():
        assert r["against_vram"] == 0 and r["against_model"] in (None, 0), (k, r)
    out["works"] = {p: [t for t, r in out[p].items() if r["line"]] for p in gen38.CARTS}
    return out


# ---------------------------------------------------------------- ENASLT, watched
AND_AT = 0x24B5                 # the operand of ENASLT's "and $C0", in both BIOS files
AND_BYTES = bytes.fromhex("DBA86FE6C0B4D3A8")   # in a,($A8) / ld l,a / and $C0 / or h / out ($A8),a
BIOS_FILES = {"eu": "cbios_main_msx1_eu.rom", "jp": "cbios_main_msx1_jp.rom"}


# the five instructions round the operand, as the BIOS files hold them
ENASLT_LINES = [(0x24B1, "DB A8", "in a, ($A8)"), (0x24B3, "6F", "ld l, a"),
                (0x24B4, "E6 C0", "and $C0"), (0x24B6, "B4", "or h"),
                (0x24B7, "D3 A8", "out ($A8), a")]


def enaslt_txt():
    """ch38/enaslt.txt: the five instructions, checked against both BIOS files"""
    out = ["; enaslt.txt -- C-BIOS 0.29a's ENASLT puts the slot in page 3; written by",
           "; meas38.py from cbios_main_msx1_eu.rom and cbios_main_msx1_jp.rom, the same",
           "; bytes in both"]
    for a, code, text in ENASLT_LINES:
        for name in BIOS_FILES.values():
            data = (msxcap.CBIOS / name).read_bytes()
            assert data[a:a + len(code.split())] == bytes.fromhex(code), (name, a)
        out.append(f"        {text:<24}; ${a:04X}: {code}")
    (HERE / "enaslt.txt").write_text("\n".join(out) + "\n")
    return out[3:]


def fixed_bios(name):
    """a BIOS file with ENASLT's "and $C0" made "and $3F"; the bytes around it checked"""
    data = bytearray((msxcap.CBIOS / name).read_bytes())
    assert data.count(AND_BYTES) == 1 and data.index(AND_BYTES) == AND_AT - 4, name
    data[AND_AT] = 0x3F
    return bytes(data)


def grid_xml(ram, exp, bios, sha1, code):
    """a machine of 16 KB like the book's: the RAM in primary slot RAM, a slot
    expander in primary slot EXP with the cartridge in its socket 1; RAM == EXP
    puts the RAM in the expander's socket 0"""
    base = (REPO / "machines" / f"{EXPANDER}.xml").read_text()
    head, rest = base.split('    <primary slot="0">', 1)
    _, tail = rest.split("    <PPI", 1)
    ram_dev = ('      <RAM id="Main RAM">\n        <mem base="0xC000" size="0x4000"/>\n'
               '      </RAM>\n')
    slots = ('    <primary slot="0">\n      <ROM id="C-BIOS Main ROM">\n'
             '        <mem base="0x0000" size="0x8000"/>\n'
             f'        <rom>\n          <sha1>{sha1}</sha1>\n          <filename>{bios}</filename>\n'
             '        </rom>\n      </ROM>\n'
             '      <ROM id="C-BIOS Logo ROM">\n        <mem base="0x8000" size="0x4000"/>\n'
             '        <rom>\n          <sha1>9fbbe400dbaf186aeba42e170d9424b032412c42</sha1>\n'
             '          <filename>cbios_logo_msx1.rom</filename>\n        </rom>\n      </ROM>\n' +
             (ram_dev if ram == 0 else "") + '    </primary>\n')
    for p in (1, 2, 3):
        if p == exp:
            slots += f'    <primary slot="{p}">\n'
            if ram == exp:
                slots += '      <secondary slot="0">\n' + ram_dev.replace("\n      ", "\n        ").replace(
                    "      <RAM", "        <RAM", 1) + '      </secondary>\n'
            slots += '      <secondary external="true" slot="1"/>\n    </primary>\n'
        elif p == ram:
            slots += f'    <primary slot="{p}">\n' + ram_dev + '    </primary>\n'
    head = re.sub(r"<code>.*</code>", f"<code>{code}</code>", head)
    head = re.sub(r"<description>.*</description>",
                  "<description>Chapter 38's test machine: the RAM and a slot expander.</description>", head)
    return head + slots + "\n    <PPI" + tail


class World:
    """C-BIOS with ENASLT fixed, and the machines that use it, in a temporary
    folder that msxcap uses while the World is open: MSXBOOK_*_FIX are the
    book's five with the fixed BIOS, GRID_R{ram}_E{exp} and GRID_R{ram}_E{exp}_FIX
    the twelve test machines with each BIOS"""
    def __enter__(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ch38world_"))
        cb, mc = self.tmp / "cbios", self.tmp / "machines"
        cb.mkdir()
        mc.mkdir()
        for f in msxcap.CBIOS.glob("*.rom"):
            shutil.copy(f, cb / f.name)
        sha = {}
        for tag, name in BIOS_FILES.items():
            data = fixed_bios(name)
            fix = name.replace(".rom", "_fix.rom")
            (cb / fix).write_bytes(data)
            sha[name] = hashlib.sha1((msxcap.CBIOS / name).read_bytes()).hexdigest()
            sha[fix] = hashlib.sha1(data).hexdigest()
        for f in (REPO / "machines").glob("*.xml"):
            shutil.copy(f, mc / f.name)
        for m in MACHINES:
            text = (REPO / "machines" / f"{m}.xml").read_text()
            for name in BIOS_FILES.values():
                fix = name.replace(".rom", "_fix.rom")
                text = text.replace(f"<sha1>{sha[name]}</sha1>", f"<sha1>{sha[fix]}</sha1>")
                text = text.replace(f"<filename>{name}</filename>", f"<filename>{fix}</filename>")
            assert "_fix.rom" in text, m
            (mc / f"{m}_FIX.xml").write_text(text)
        eu, fix = BIOS_FILES["eu"], BIOS_FILES["eu"].replace(".rom", "_fix.rom")
        for ram, exp in GRID:
            (mc / f"GRID_R{ram}_E{exp}.xml").write_text(grid_xml(ram, exp, eu, sha[eu], f"grid {ram} {exp}"))
            (mc / f"GRID_R{ram}_E{exp}_FIX.xml").write_text(
                grid_xml(ram, exp, fix, sha[fix], f"grid {ram} {exp} fixed"))
        self.folder = mc
        self.saved = msxcap.CBIOS, msxcap.MACHINES
        msxcap.CBIOS, msxcap.MACHINES = cb, mc
        return self

    def __exit__(self, *exc):
        msxcap.CBIOS, msxcap.MACHINES = self.saved
        shutil.rmtree(self.tmp, ignore_errors=True)


GRID = [(ram, exp) for exp in (1, 2, 3) for ram in (0, 1, 2, 3)]


def call_site(prog, target):
    """the address of PROG's "call TARGET" (the first), from its listing"""
    for line in (HERE / f"{prog}.lst").read_text().splitlines():
        m = dbg.LST.match(line)
        if m and "..." not in m.group(3)[1:13]:
            _, a, code, src = dbg.lst_fields(m)
            text = re.sub(r"^\s*[\w.]+:", "", src.split(";")[0]).strip().lower()
            if code and text == f"call {target.lower()}":
                return a
    raise KeyError(target)


WATCH = ('debug set_watchpoint write_io 0xA8 {} '
         '{ L "out [format %.17g [machine_info time]] $::wp_last_value" }\n'
         'debug set_watchpoint write_mem 0xFFFF {} '
         '{ L "poke [format %.17g [machine_info time]] $::wp_last_value [debug read ioports 0xA8]" }\n')


def watched(prog, machine, target):
    """PROG on MACHINE from INIT to the return from "call TARGET": every write to
    port $A8 and to $FFFF between the CALL and the return, with its T-state
    counted from the CALL"""
    at = call_site(prog, target)
    tcl = ("S init\n" + WATCH +
           f'debug set_bp {at} {{}} {{ L "call [format %.17g [machine_info time]]" }}\n'
           f'debug set_bp {at + 3} {{}} {{ L "back [format %.17g [machine_info time]]"; S back }}\n')
    w = run(rom(prog), machine, 3, at_init=tcl)
    t0 = next(t_state(x[1]) for x in w if x[0] == "call")
    t1 = next(t_state(x[1]) for x in w if x[0] == "back")
    outs = [(t_state(x[1]) - t0, int(x[2])) for x in w if x[0] == "out" and t0 <= t_state(x[1]) <= t1]
    pokes = [(t_state(x[1]) - t0, int(x[2]), int(x[3])) for x in w if x[0] == "poke"
             and t0 <= t_state(x[1]) <= t1]
    return {"T": t1 - t0, "outs": outs, "pokes": pokes, "init": state(w, "init"), "back": state(w, "back")}


def grid_one(job):
    ram, exp, fixed = job
    machine = f"GRID_R{ram}_E{exp}" + ("_FIX" if fixed else "")
    r = cart_one(("cart32", machine, fixed), folder=msxcap.MACHINES)
    return r


def enaslt():
    out = {"lines": enaslt_txt()}
    with World():
        for fixed in (False, True):
            m = EXPANDER + ("_FIX" if fixed else "")
            r = watched("cart32", m, "ENASLT")
            init, back = r["init"], r["back"]
            sid = slot_id(1, 1)
            outs, wrote, end = cbios_enaslt(init["a8"], lambda p: init["ffff"][p], sid, 2, fixed)
            assert [v for _, v in r["outs"]] == outs, (m, r["outs"], outs)
            assert [(a8 >> 6, v) for _, v, a8 in r["pokes"]] == [wrote], (m, r["pokes"], wrote)
            out["fixed" if fixed else "cbios"] = {
                "a8_writes": [f"{v:02X}" for v in outs],
                "ffff_write": {"page3_slot": wrote[0], "byte": f"{wrote[1]:02X}"},
                "ram_ffff": [f"{init['ffff'][3]:02X}", f"{back['ffff'][3]:02X}"],
                "register1": [f"{reg_of(init, 1):02X}", f"{reg_of(back, 1):02X}"],
                "slttbl1": [f"{init['slt'][1]:02X}", f"{back['slt'][1]:02X}"],
                "T": r["T"], "dark": [t for t, _ in r["outs"]]}
        jobs = [(ram, exp, fixed) for fixed in (False, True) for ram, exp in GRID]
        res = parallel(jobs, grid_one)
        out["fixed_book"] = {TAG[m]: cart_one(("cart32", m + "_FIX", True), folder=msxcap.MACHINES)["line"]
                             for m in MACHINES}
    grid = {}
    for (ram, exp, fixed), r in zip(jobs, res):
        # the model: ENASLT reads $FFFF with page 3 on (ram | exp); right when that is exp
        works = (ram | exp) == exp
        assert r["line"] == (works or fixed), (ram, exp, fixed, r)
        grid.setdefault(f"ram {ram}, expander {exp}", {})["fixed" if fixed else "cbios"] = r["line"]
    out["grid"] = grid
    out["fails"] = sorted(k for k, v in grid.items() if not v["cbios"])
    return out


# ---------------------------------------------------------------- prices
LAYOUTS = {EU: {"a8": 0xC4, "exp": [0, 0, 0, 0], "reg": {}},
           EXPANDER: {"a8": 0xC4, "exp": [0, 0x80, 0, 0], "reg": {1: 0x04}}}


def walked(prog, machine, target, **regs):
    """walk.py's CALL TARGET in PROG, with port $A8, EXPTBL and the registers
    of MACHINE at INIT: (T-states, [(T, value) written to port $A8], A at the end)"""
    lay = LAYOUTS[machine]
    w = walk.Walk(HERE / prog, read_port=lambda port, t: lay["a8"] if port == 0xA8 else 0)
    for p in range(4):
        w.mem[0xFCC1 + p] = lay["exp"][p]
    # $FFFF as page 3 reads it while the routine has put the slot there: the
    # register, complemented (the routines change page 3 only to read it)
    for p, r in lay["reg"].items():
        w.mem[0xFFFF] = ~r & 255
    t = w.call(target, **regs)
    return t, [(pt, v) for pt, port, v in w.ports if port == 0xA8 and v is not None], w.r["a"]


PRICED = [("own32", EU, "here", {}), ("own32", EXPANDER, "here", {}),
          ("own32", EU, "setpage2", {"a": 0x01}), ("own32", EXPANDER, "setpage2", {"a": 0x85}),
          ("quick32", EU, "quick", {})]
BIOS_ONLY = [("cart32", EU, "here"), ("cart32", EXPANDER, "here"), ("cart32", EU, "RSLREG"),
             ("cart32", EU, "ENASLT"), ("cart32", EXPANDER, "ENASLT")]


def prices():
    out = {"walk_vs_debugger": {}, "debugger": {}}
    for prog, m, target, regs in PRICED:
        t, outs, a = walked(prog, m, target, **regs)
        r = watched(prog, m, target)
        assert t == r["T"] and outs == r["outs"], (prog, m, target, t, r["T"], outs, r["outs"])
        out["walk_vs_debugger"][f"{target} {prog} {TAG[m]}"] = {"T": t, "a8_writes": [[x, f"{v:02X}"] for x, v in outs]}
    for prog, m, target in BIOS_ONLY:
        r = watched(prog, m, target)
        out["debugger"][f"{target} {prog} {TAG[m]}"] = {"T": r["T"], "a8_writes": [[x, f"{v:02X}"] for x, v in r["outs"]]}
    # subreg alone, by walk.py; and how long page 3 is not the RAM: from the
    # write that takes it away to the one that brings it back
    t, outs, a = walked("own32", EXPANDER, "subreg", a=1)
    assert a == 0x04
    out["subreg"] = {"T": t, "dark": outs[1][0] - outs[0][0]}
    pg = out["walk_vs_debugger"]["setpage2 own32 eue"]["a8_writes"]
    out["setpage2_dark"] = pg[1][0] - pg[0][0]
    with World():
        r = watched("cart32", EXPANDER + "_FIX", "ENASLT")
    out["enaslt_fixed"] = {"T": r["T"], "dark": r["outs"][1][0] - r["outs"][0][0]}
    return out


# ---------------------------------------------------------------- where it breaks
FOLLOW = r"""
set ::rst 0
set ::vram 0
set ::in2 0
debug set_bp 0x0038 {} { incr ::rst }
debug set_watchpoint write_io 0x98 {} { if {$::in2} { incr ::vram } }
debug set_bp 0x8000 {} {
    if {!$::in2} {
        set ::in2 1
        binary scan [debug read_block memory 0x8000 16] H* h
        L "first [format %.17g [machine_info time]] [expr {[machine_info VDP_frame_count] - $::f0}] $h"
    }
}
debug set_bp 0xC000 {} { L "c000 [format %.17g [machine_info time]] [expr {[machine_info VDP_frame_count] - $::f0}] $::rst" }
for {set a 0x8000} {$a < 0x8080} {incr a} {
    set ::seen($a) [debug set_bp $a {} "L \"path $a \$::rst\"; debug remove_bp \$::seen($a)"]
}
"""


def follow(job):
    """PROG on MACHINE, followed from the CALL into page 2 for FRAMES frames"""
    prog, machine, frames = job
    back = call_site(prog, "second") + 3
    tcl = (FOLLOW + f'debug set_bp {back} {{}} {{ L "back [format %.17g [machine_info time]] '
           f'[expr {{[machine_info VDP_frame_count] - $::f0}}] $::rst $::vram"; set ::in2 0 }}\n'
           f'debug set_bp {sym(prog)["init.end"]} {{}} {{ if {{![info exists ::ended]}} '
           f'{{ set ::ended 1; L "ended [expr {{[machine_info VDP_frame_count] - $::f0}}]" }} }}\n')
    w = run(rom(prog), machine, frames, at_init=tcl, events={frames - 1: 'S end; L "rst $::rst"'})
    first = next(x for x in w if x[0] == "first")
    t0 = t_state(first[1])
    out = {"bytes": first[3].upper(), "frame": int(first[2])}
    out["path"] = [[f"{int(x[1], 0):04X}", int(x[2])] for x in w if x[0] == "path"][:40]
    out["rst_total"] = int(next(x for x in w if x[0] == "rst")[1])
    c = [x for x in w if x[0] == "c000"]
    if c:
        out["c000"] = {"frame": int(c[0][2]), "T": t_state(c[0][1]) - t0, "rst": int(c[0][3]),
                       "times": len(c)}
    b = [x for x in w if x[0] == "back"]
    if b:
        out["back"] = {"frame": int(b[0][2]), "T": t_state(b[0][1]) - t0, "rst": int(b[0][3]),
                       "vram_writes": int(b[0][4])}
    e = [x for x in w if x[0] == "ended"]
    out["ended"] = int(e[0][1]) if e else None
    end = state(w, "end")
    out["pc"] = f"{end['pc']:04X}"
    return out


BREAKS = [("stay32", EU, 60), ("stay32", JP, 60), ("stay32", BIG, 300), ("quick32", EXPANDER, 300),
          ("cart32", EXPANDER, 300)]


def breaks():
    res = parallel(BREAKS, follow)
    out = {f"{p} {TAG[m]}": r for (p, m, _), r in zip(BREAKS, res)}
    logo = LOGO.read_bytes()
    for k in ("stay32 eu", "stay32 jp"):
        assert out[k]["bytes"] == logo[:16].hex().upper() and out[k]["back"] and out[k]["ended"] is not None
    for k in ("quick32 eue", "cart32 eue"):
        r = out[k]
        assert r["bytes"] == "FF" * 16 and r["c000"]["rst"] == 16384 and r["ended"] is None
        r["T_per_byte"] = round(r["c000"]["T"] / 16384, 1)
    out["logo_text"] = logo[:15].decode()
    return out


# ---------------------------------------------------------------- the same code on other slots
CH37 = REPO / "ch37"
SAME_FRAMES = 300


def psg_log(machine):
    """chapter 37's tune.rom: every write to the PSG's ports, as (the interrupt
    it follows, T-states after that interrupt's ISR began, port, byte)"""
    isr = dbg.sym(CH37 / "tune.sym")["isr"]
    tcl = ('debug set_watchpoint write_io {0xA0 0xA1} {} '
           '{ L "w [format %.17g [machine_info time]] [expr {$::wp_last_address & 255}] $::wp_last_value" }\n'
           f'debug set_bp {isr} {{}} {{ L "i [format %.17g [machine_info time]]" }}\n'
           'L "at [machine_info VDP_cycle_in_frame]"\n')
    w = run(CH37 / "tune.rom", machine, SAME_FRAMES, at_init=tcl)
    out, n, t_isr = [], -1, None
    for x in w:
        if x[0] == "i":
            n, t_isr = n + 1, t_state(x[1])
        elif x[0] == "w":
            out.append((n, None if t_isr is None else t_state(x[1]) - t_isr, int(x[2]), int(x[3])))
    init_at = next(int(x[1]) for x in w if x[0] == "at")
    return out, n + 1, init_at


def same():
    ms = [EU, EXP_RAM, EXPANDER]
    logs = dict(zip(ms, parallel(ms, psg_log)))
    base = logs[EU][0]
    out = {"writes": len(base), "interrupts": logs[EU][1],
           "init_cycle": {TAG[m]: logs[m][2] for m in ms},
           "same": {TAG[m]: logs[m][0] == base for m in ms}}
    assert all(out["same"].values()), out
    return out


# ---------------------------------------------------------------- memory
def labels():
    """the labels every program of the book so far puts in $C000-$F37F, from
    the .sym files: {label at address: the programs}"""
    found = {}
    for f in sorted(REPO.glob("ch*/*.sym")):
        if f.parent.name == "ch38":
            continue
        for lab, a in dbg.sym(f).items():
            if 0xC000 <= a < 0xF380 and lab != "RAM_START" and "." not in lab:
                found.setdefault(a, set()).add(f"{f.parent.name}/{f.stem}")
    return found


def memory():
    found = labels()
    progs = sorted(set().union(*found.values()))
    named = {}
    for f in sorted(REPO.glob("ch*/*.sym")):
        if f.parent.name == "ch38":
            continue
        s = dbg.sym(f)
        for lab in ("RESULTS", "VARS", "IM2_TABLE", "IM2_JUMP"):
            if lab in s:
                named.setdefault(lab, {}).setdefault(f"{s[lab]:04X}", 0)
                named[lab][f"{s[lab]:04X}"] += 1
    # 256-byte blocks of $C000-$F37F: how many programs put a label in each
    blocks = {}
    for a, ps in found.items():
        blocks.setdefault(f"{a & 0xFF00:04X}", set()).update(ps)
    every = [f for f in REPO.glob("ch*/*.sym") if f.parent.name != "ch38"]
    out = {"programs": len(progs), "all_programs": len(every), "named": named,
           "blocks": {k: len(v) for k, v in sorted(blocks.items())},
           "highest": f"{max(found):04X}", "highest_by": sorted(found[max(found)])}
    # chapter 37's tune.rom, watched: every byte it writes in $C000-$FFFF
    tcl = ('debug set_watchpoint write_mem {0xC000 0xFFFF} {} { set ::w($::wp_last_address) 1 }\n')
    w = run(CH37 / "tune.rom", EU, SAME_FRAMES, at_init=tcl,
            events={SAME_FRAMES - 1: 'L "written [lsort -integer [array names ::w]]"'})
    addrs = [int(a) for a in next(x for x in w if x[0] == "written")[1:]]
    runs, start = [], None
    for i, a in enumerate(addrs):
        if start is None:
            start = a
        if i + 1 == len(addrs) or addrs[i + 1] != a + 1:
            runs.append([f"{start:04X}", f"{a:04X}", a - start + 1])
            start = None
    out["tune"] = {"bytes": len(addrs), "runs": runs,
                   "stack_lowest": f"{min(a for a in addrs if a >= 0xE000):04X}",
                   "bios_area": sum(1 for a in addrs if a >= 0xF380)}
    return out


# ---------------------------------------------------------------- standard
def standard():
    """openMSX's MSX1 machine files (type MSX): the slot of the RAM under the
    BIOS's work area ($F380-$FFFF), the expanded slots, the cartridge slots"""
    from collections import Counter
    share = Path(os.environ.get("OPENMSX_SYSTEM_DATA", "/usr/share/openmsx"))
    ram_at, cart_at, expanded, odd, in_expanded = Counter(), Counter(), 0, [], []
    n = 0
    for f in sorted((share / "machines").glob("*.xml")):
        try:
            root = ET.parse(f).getroot()
        except ET.ParseError:
            continue
        if root.findtext("info/type") != "MSX":
            continue
        n += 1
        ram, ext, exp = [], [], set()

        def walk_(node, p, s):
            for ch in node:
                if ch.tag == "primary":
                    pp = int(ch.get("slot"))
                    if ch.get("external") == "true":
                        ext.append(slot_text(pp, None))
                    walk_(ch, pp, None)
                elif ch.tag == "secondary":
                    exp.add(p)
                    ss = int(ch.get("slot"))
                    if ch.get("external") == "true":
                        ext.append(slot_text(p, ss))
                    walk_(ch, p, ss)
                elif ch.tag in ("RAM", "MemoryMapper", "PanasonicRAM"):
                    for m in ch.findall("mem"):
                        b, sz = int(m.get("base"), 0), int(m.get("size"), 0)
                        if b <= 0xF380 and b + sz >= 0x10000:
                            ram.append((p, s))
                else:
                    walk_(ch, p, s)
        walk_(root.find("devices"), None, None)
        if len(ram) != 1:
            odd.append(f.stem)
            continue
        ram_at[slot_text(*ram[0])] += 1
        cart_at[" ".join(sorted(ext))] += 1
        expanded += bool(exp)
        for e in ext:
            if "-" in e:
                in_expanded.append({"machine": f.stem, "cartridge": e, "ram": slot_text(*ram[0]),
                                    "cbios_enaslt_fails": (ram[0][0] | int(e[0])) != int(e[0])})
    return {"msx1": n, "ram": dict(ram_at.most_common()), "cartridge_slots": dict(cart_at.most_common()),
            "with_expanded_slot": expanded, "no_single_ram": odd, "cartridge_in_expanded": in_expanded}


# ---------------------------------------------------------------- answers
def answers():
    m = json.loads((HERE / "meas38.json").read_text())
    pg, ct, en, pr, br = (m[k] for k in ("pages", "carts", "enaslt", "prices", "breaks"))
    out = {}

    def pages_of(a8):
        return [a8 >> 2 * k & 3 for k in range(4)]
    assert ct["cart32"]["eu"]["a8"][1] == "D4" and ct["cart32"]["eu"]["page2"] == "1"
    assert pg["eu64"]["a8"] == "F4" and pg["eu64"]["pages"] == ["0", "1", "3", "3"]
    out["q1"] = {"D4": pages_of(0xD4), "F4": pages_of(0xF4)}
    out["q2"] = {"id": f"{slot_id(3, 2):02X}", "h": "40-7F"}
    reg = 0xE4
    out["q3"] = {"register": f"{reg:02X}", "pages": [f"3-{reg >> 2 * k & 3}" for k in range(4)]}
    r1 = ~0xFB & 255
    assert f"{r1:02X}" == pg["eue"]["registers"]["1"]
    out["q4"] = {"register": f"{r1:02X}", "pages": [f"1-{r1 >> 2 * k & 3}" for k in range(4)]}
    out["q5"] = {"subreg": pr["subreg"]["dark"], "setpage2": pr["setpage2_dark"]}
    right = [k for k, v in en["grid"].items() if v["cbios"]]
    rule = [k for k in en["grid"] if (int(k.split()[1].rstrip(",")) | int(k.split()[-1])) == int(k.split()[-1])]
    assert right == rule
    out["q6"] = {"read_own_register": right, "count": len(right), "rule": "(RAM's slot OR expander's) == expander's"}
    t2, te = pr["walk_vs_debugger"]["setpage2 own32 eue"]["T"], pr["debugger"]["ENASLT cart32 eue"]["T"]
    out["q7"] = {"setpage2": 71364 // t2, "enaslt": 71364 // te, "T": [t2, te]}
    q = round(16384 * br["quick32 eue"]["T_per_byte"])
    out["q8"] = {"T": q, "frames_50": round(q / 71364, 1), "frames_60": round(q / 59736, 1)}
    assert pg["eux"]["exptbl"][1] == "00" and ct["cart32"]["eux"]["slttbl"][0] == "00"
    out["q9"] = {"slttbl_3": pg["eux"]["slttbl"][3], "register_3": pg["eux"]["registers"]["3"],
                 "cart32_slot_on_eux": ct["cart32"]["eux"]["slot"], "exptbl_1_on_eux": pg["eux"]["exptbl"][1],
                 "readers": ["here in cart32, quick32 and stay32: SLTTBL only for an expanded slot 1",
                             "slt in all four: SLTTBL[1], printed", "pages.asm: all four, printed"]}
    # chapter 24's copy of the names at $C400 and its marks at $C700; the sprites after them
    out["q10"] = {"names": ["C400", f"{0xC400 + 768 - 1:04X}"], "marks": ["C700", "C717"],
                  "sprites": ["C800", f"{0xC800 + 127:04X}"],
                  "stack": [f"{0xF380 - 64:04X}", "F37F"]}
    return out


OPENMSX_SECTIONS = ["pages", "carts", "enaslt", "prices", "breaks", "same", "memory"]


def openmsx():
    if not versions.builds():
        return {"skipped": "OPENMSX_BUILDS not set"}
    return versions.every_build(["ch38"], OPENMSX_SECTIONS)


SECTIONS = {"pages": pages, "carts": carts, "enaslt": enaslt, "prices": prices, "breaks": breaks,
            "same": same, "memory": memory, "standard": standard,
            "answers": answers, "openmsx": openmsx}


def main(names=()):
    CAPS.mkdir(exist_ok=True)
    path = HERE / "meas38.json"
    m = json.loads(path.read_text()) if names and path.exists() else {}
    for name in names or SECTIONS:
        print(name, flush=True)
        m[name] = SECTIONS[name]()
        m = {k: m[k] for k in SECTIONS if k in m}
        path.write_text(json.dumps(m, indent=1) + "\n")
    return m


if __name__ == "__main__":
    main(sys.argv[1:])
