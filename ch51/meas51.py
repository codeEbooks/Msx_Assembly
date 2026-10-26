#!/usr/bin/env python3
"""meas51.py -- one cartridge, many machines, measured.

    python3 gen51.py && ./build.sh && python3 meas51.py
                                       python3 meas51.py which games   only these

  machines  the 22 machines from their files: the book's ten (machines/) and
            openMSX's twelve C-BIOS machines (its share folder): the VDP,
            the PSG, the keyboard, where the RAM is, the BIOS's ROM, and
            the BIOS's three bytes at $002B-$002D read from that ROM
  which     which.rom on every machine, keys pressed from frame 24: the
            page photographed at frame 130 and held cell by cell against
            the page the files say it must show (the characters drawn with
            that machine's own BIOS set); the debugger's log of the VRAM
            tests (every OUT and IN of the VDP's ports, with its cycle)
            played through vdpslots.py, which gives the bytes each loop
            keeps; the program's variables and the VRAM read by the
            debugger; the colours of the strip; where INIT was called
  blind     blind.rom the same way: R#7 and the status the IN read
  games     GRIN ALLEY (chapter 44) and LANTERN KEEP (chapter 46) on every
            machine, with the play planned for its rate moved to the frame
            of the first loop (play51.py), loop for loop against the
            model; the last frame of each play against the book's machine
            of the same rate, colour code for colour code
  prices    the T-states of the loops, from walk.py, against the debugger
  answers   the workshop, tried (for Appendix I)
  openmsx   all of it again with every other build (tools/versions.py)
"""
import atexit
import gzip
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "tools"))
import meas        # noqa: E402
import msxcap      # noqa: E402
import probe as dbg  # noqa: E402
import screentext  # noqa: E402
import versions    # noqa: E402
sys.path.insert(0, str(HERE))
import gen51       # noqa: E402
for mod in ("vdpslots", "walk"):
    sys.modules.pop(mod, None)
import vdpslots    # noqa: E402
import walk        # noqa: E402

assert Path(vdpslots.__file__).parent == HERE and Path(walk.__file__).parent == HERE

CAPS = HERE / "captures"
SHOTS = HERE / "shots"
BOOK = ["MSXBOOK_EU16", "MSXBOOK_JP16", "MSXBOOK_EU8", "MSXBOOK_EU32", "MSXBOOK_EU64",
        "MSXBOOK_EU16AY", "MSXBOOK_EU16X", "MSXBOOK_EU16E", "MSXBOOK_EU16G", "MSXBOOK_EU16P"]
STOCK = [f"C-BIOS_{v}{r}" for v in ("MSX1", "MSX2", "MSX2+") for r in ("", "_EU", "_JP", "_BR")]
MACHINES = BOOK + STOCK
REF = {50: "MSXBOOK_EU16", 60: "MSXBOOK_JP16"}      # the book's machine of each rate
CLOCK = 3579545
LINE = 1368                 # VDP cycles a line
PER_T = 6
FRAME_LINES = {50: 313, 60: 262}
PHOTO = 130                 # the frame photographed: the page finished
FRAMES = PHOTO + 2
POS = "[machine_info VDP_frame_count] [machine_info VDP_cycle_in_frame]"
SHARE = Path(os.environ.get("OPENMSX_SYSTEM_DATA", "/usr/share/openmsx"))
# The twelve C-BIOS machines are openMSX's, from the share folder of the openMSX
# the book was measured with: the same files for every build that runs them
# (openMSX 17.0's and 18.0's packages have none of their own), put next to the
# book's machines in the folder msxcap.py gives openMSX.
STOCK_FROM = Path(os.environ.get("MEAS51_STOCK_MACHINES", "/usr/share/openmsx/machines"))


def machines_folder():
    d = Path(tempfile.mkdtemp(prefix="machines51_"))
    atexit.register(shutil.rmtree, d, True)
    for xml in sorted((REPO / "machines").glob("*.xml")):
        shutil.copy(xml, d)
    for name in STOCK:
        shutil.copy(STOCK_FROM / f"{name}.xml", d)
    os.environ["MSXCAP_MACHINES"] = str(d)      # for play51.py too
    msxcap.MACHINES = d
    return d


MACHINE_FILES = machines_folder()

STATE = r"""
proc M {tag addr n} {
    binary scan [debug read_block memory $addr $n] H* h
    L "$tag mem $h"
}
proc VR {tag addr n} {
    binary scan [debug read_block VRAM $addr $n] H* h
    L "$tag vram $h"
}
proc DB {tag name n} {
    binary scan [debug read_block $name 0 $n] H* h
    L "$tag db $h"
}
"""
TOO_FAST = ('proc ::toofast_cb {args} { L "fast ' + POS + '" }\n'
            'set VDP.too_fast_vram_access_callback ::toofast_cb\n')


# ---------------------------------------------------------------- the machines' files
def xml_of(machine):
    return MACHINE_FILES / f"{machine}.xml"


def rom_index():
    """sha1 -> bytes of every ROM file openMSX may use: C-BIOS's folder, and
    the share folder's machines/ and systemroms/ (some builds keep them there)"""
    out = {}
    places = [msxcap.CBIOS, SHARE / "machines", SHARE / "systemroms"]
    for place in places:
        if not place.exists():
            continue
        for p in sorted(place.rglob("*")):
            if not p.is_file() or not p.name.lower().endswith((".rom", ".rom.gz")):
                continue
            data = p.read_bytes()
            if p.name.endswith(".gz"):
                data = gzip.decompress(data)
            out.setdefault(hashlib.sha1(data).hexdigest(), (str(p), data))
    return out


ROMS = None


def machine_file(machine):
    """what a machine's file says: its type, VDP, PSG, keyboard, the RAM that
    holds page 3 and how much of pages 2-3 it covers, and its main ROM"""
    global ROMS
    if ROMS is None:
        ROMS = rom_index()
    root = ET.parse(xml_of(machine)).getroot()
    vdp = root.find(".//VDP/version").text
    psg = root.find(".//PSG/type")
    out = {"type": root.find("./info/type").text, "vdp": vdp,
           "psg": psg.text if psg is not None else "AY8910",
           "keyboard": root.find(".//PPI/keyboard_type").text}
    for prim in root.iter("primary"):
        secs = prim.findall("secondary")
        for sec in (secs or [prim]):
            for dev in sec:
                if dev.tag == "ROM" and dev.find("mem").get("base") == "0x0000" and \
                        prim.get("slot") == "0" and "Main" in dev.get("id"):
                    sha1 = dev.find(".//sha1").text
                    out["rom"] = ROMS[sha1][0]
                    out["rom_sha1"] = sha1
                if dev.tag in ("RAM", "MemoryMapper"):
                    mem = dev.find("mem")
                    base, size = int(mem.get("base"), 16), int(mem.get("size"), 16)
                    if base + size == 0x10000:
                        out["ram_slot"] = prim.get("slot") + (f"-{sec.get('slot')}" if secs else "")
                        kb = dev.find("size")
                        out["ram_kb"] = int(kb.text) if kb is not None else size // 1024
                        out["ram_from"] = max(base, 0x8000)
    out["expanded"] = sorted(p.get("slot") for p in root.iter("primary") if p.findall("secondary"))
    return out


def bios_bytes(rom):
    data = ROMS_DATA(rom)
    return list(data[0x2B:0x2E])


def ROMS_DATA(path):
    for p, data in ROMS.values():
        if p == path:
            return data
    raise KeyError(path)


def scancodes(data):
    """the BIOS's table of characters for the keys without SHIFT: the row
    whose row 0 is "01234567", whose row 1 starts "89-" and whose row 2 ends
    "ab" (the keypad's table starts with the same digits)"""
    mark = b"0123456789-"
    at = data.find(mark)
    while at >= 0 and data[at + 22:at + 24] != b"ab":   # not the keypad's: row 2 ends "ab"
        at = data.find(mark, at + 1)
    assert at > 0, "the table"
    return data[at:at + 8 * 11]


def rate_of(info):
    return 50 if info["bios"][0] & 0x80 else 60


def machines():
    out = {}
    for m in MACHINES:
        info = machine_file(m)
        data = ROMS_DATA(info["rom"])
        info["bios"] = list(data[0x2B:0x2E])
        table = scancodes(data)
        info["keys"] = [table[8 * r + c] for r, c in gen51.KEYS]
        info["rate"] = rate_of(info)
        info["rom"] = Path(info["rom"]).name
        out[m] = info
        print("machine", m, info, flush=True)
    return out


# ---------------------------------------------------------------- the page the files say
class Screen:
    def __init__(self):
        self.rows = [[" "] * 32 for _ in range(24)]

    def put(self, row, col, text):
        for i, ch in enumerate(text):
            self.rows[row][col + i] = ch

    def text(self, row):
        return "".join(self.rows[row])


def d16(n):
    return f"{n:5d}"


def dec(n):
    return f"{n:3d}"


def page_model(info, kept, s1=None):
    """which.rom's page on a machine, from its files: KEPT, the four counts
    vdpslots.py gives; S1, for blind.rom on an MSX1, the status it reads"""
    sc = Screen()
    for k, s in gen51.LABELS.items():
        sc.put(*gen51.AT[k], s)
    b = info["bios"]
    row, col = gen51.AT["bios"][0], gen51.col_after("bios") + 1
    sc.put(row, col, f"{b[0]:02X} {b[1]:02X} {b[2]:02X}: ")
    name = gen51.MSX_NAMES[b[2]] if b[2] < 4 else "?"
    sc.put(row, col + 10, f"{name}, {'50' if b[0] & 0x80 else '60'} Hz")
    kb = b[1] & 15
    sc.put(gen51.AT["board"][0], gen51.col_after("board") + 1,
           gen51.KEYBOARD_NAMES[kb] if kb < 5 else "?")
    lines = 313 if info["vdp"] == "TMS9929A" or (info["vdp"].startswith("V99") and b[0] & 0x80) \
        else 262
    turns = lines * meas.T_PER_LINE // gen51.TURN
    sc.put(gen51.AT["frame"][0], gen51.col_after("frame"),
           d16(turns) + f" x {gen51.TURN} T:" + d16(lines) + " lines")
    row, col = gen51.AT["vdp"][0], gen51.col_after("vdp") + 2
    if info["vdp"].startswith("V99") or s1 is not None:
        ident = {"V9938": 0, "V9958": 2}[info["vdp"]] if s1 is None else (s1 >> 1) & 0x1F
        chip = {0: "V9938", 2: "V9958"}.get(ident, "V99x8")
        sc.put(row, col, f"{chip}, S#1 ID" + dec(ident))
    else:
        sc.put(row, col, "TMS9929A" if lines == 313 else "TMS9918A/28A")
    chip, back = {"YM2149": ("YM2149", 0xFF), "AY8910": ("AY-3-8910", 0x0F)}[info["psg"]]
    sc.put(gen51.AT["psg"][0], gen51.col_after("psg") + 2, f"{chip}, R1 reads {back:02X}")
    sc.put(gen51.AT["ram"][0], gen51.col_after("ram") + 1, info["ram_slot"])
    sc.put(gen51.AT["from"][0], gen51.col_after("from"), f"{info['ram_from']:04X}")
    row = gen51.AT["kept"][0]
    for i, k in enumerate(kept):
        sc.put(row, gen51.AT["vram"][1] + 6 + 5 * i, dec(k))
    sc.put(gen51.AT["keys"][0], gen51.col_after("keys") + 1, "".join(chr(c) for c in info["keys"]))
    return sc


def ink(px, col, row):
    x0, y0 = meas.paper(8 * col, 8 * row)
    return tuple(sum((sum(px[x0 + i, y0 + j]) < 384) << (7 - i) for i in range(8)) for j in range(8))


def page_against(png, sc, rom_data):
    """the cells of the photo's rows 0-11, columns 1-30, that are not the
    model's characters in this BIOS's set; and the strip's colours"""
    at = rom_data[4] | rom_data[5] << 8
    shapes = [tuple(rom_data[at + 8 * c: at + 8 * c + 8]) for c in range(256)]
    px = Image.open(png).convert("RGB").load()
    bad = []
    for r in range(gen51.ROWS - 1):
        for c in range(1, 1 + gen51.WIDTH):
            if ink(px, c, r) != shapes[ord(sc.rows[r][c])]:
                bad.append((r, c))
    row = gen51.AT["strip"][0]
    strip = []
    for k in range(15):
        x0, y0 = meas.paper(8 * (gen51.AT["strip"][1] + 2 * k), 8 * row)
        cols = {px[x0 + i, y0 + j] for i in range(8) for j in range(8)}
        strip.append(list(cols.pop()) if len(cols) == 1 else None)
    return bad, strip


# ---------------------------------------------------------------- which.rom and blind.rom
def keys_events():
    ev = {}
    for k, (r, c) in enumerate(gen51.KEYS):
        f = gen51.KEY_FIRST + gen51.KEY_EVERY * k
        ev[f] = f"keymatrixdown {r} 0x{1 << c:02X}"
        ev[f + gen51.KEY_HELD] = f"keymatrixup {r} 0x{1 << c:02X}"
    return ev


def debug_run(name, machine, folder=HERE):
    """the debugger's log of a run: where INIT was called, the BIOS's
    keyboard count and frame count there; the status at askvdp; every port
    operation of the VDP from vram to askkeys; the variables, the VRAM the
    loops wrote, the VDP's registers and palette at show"""
    s = dbg.sym(folder / f"{name}.sym")
    tcl = (f'L "c0 [machine_info VDP_cycle_in_frame] jiffy [peek16 0xFC9E] scncnt [peek 0xF3F6]"\n'
           f'debug set_bp {s["askvdp"]} {{}} {{ L "askvdp {POS} s0 [debug read {{VDP status regs}} 0]" }}\n'
           f'debug set_bp {s["vram"]} {{}} {{ L "vram {POS}"; '
           f'set ::w1 [debug set_watchpoint write_io {{0x98 0x99}} {{}} '
           f'{{ L "o [expr {{$::wp_last_address & 255}}] $::wp_last_value {POS}" }}]; '
           f'set ::w2 [debug set_watchpoint read_io 0x98 {{}} {{ L "i 152 - {POS}" }}] }}\n'
           f'debug set_bp {s["askkeys"]} {{}} {{ L "askkeys {POS}"; debug remove_watchpoint $::w1; '
           f'debug remove_watchpoint $::w2 }}\n'
           f'set ::shown 0\n'
           f'debug set_bp {s["done"]} {{}} {{ if {{!$::shown}} {{ set ::shown 1; L "fin {POS}"; '
           f'M vars {gen51.VARS_AT} 64; VR test {gen51.VRAM_AT} 256; DB regs {{VDP regs}} 8; '
           f'DB pal {{VDP palette}} 32 }} }}\n')
    lines = msxcap.run_tcl(folder / f"{name}.rom", FRAMES, TOO_FAST + tcl, machine=machine,
                           tcl_setup=STATE, events=keys_events(), timeout=600)
    w = [l.split() for l in lines]
    out = {"ops": [], "fast": [], "mem": {}}
    f0 = int(next(x for x in w if x[0] == "f0")[1])
    for x in w:
        if x[0] == "c0":
            out.update(c0=int(x[1]), jiffy=int(x[3]), scncnt=int(x[5]))
        elif x[0] in ("askvdp", "vram", "askkeys", "fin"):
            out[x[0]] = [int(x[1]) - f0, int(x[2])]
            if x[0] == "askvdp":
                out["s0"] = int(x[4])
        elif x[0] in ("o", "i"):
            out["ops"].append((int(x[3]) - f0, int(x[4]), int(x[1]),
                               None if x[2] == "-" else int(x[2])))
        elif x[0] == "fast":
            out["fast"].append((int(x[1]) - f0, int(x[2])))
        elif len(x) == 3 and x[1] in ("mem", "vram", "db"):
            out["mem"][x[0]] = list(bytes.fromhex(x[2]))
    return out


def kept_model(ops, machine, info):
    """the four counts vdpslots.py gives for the debugger's port operations:
    the VRAM after them, row by row, the bytes no longer $FF"""
    vdpslots.PAPER0[machine] = meas.PAPER_FRAME_LINE0["MSXBOOK_EU16" if info["lines"] == 313
                                                      else "MSXBOOK_JP16"]
    vdpslots.LINES[machine] = info["lines"]
    if info["vdp"].startswith("V99"):
        vdpslots.CHIP[machine] = "v99"
    frame_cycles = info["lines"] * LINE
    f_first = ops[0][0]
    events = [((f - f_first) * frame_cycles + c, port, v) for f, c, port, v in ops]
    vram = bytearray(16384)
    vram[gen51.VRAM_AT:gen51.VRAM_AT + 256] = b"\xff" * 256
    after, reads, lost = vdpslots.play(events, machine, vram=vram,
                                       regs=[0, 0xC0, 0, 0, 0, 0, 0, 0])
    rows = [after[gen51.VRAM_AT + gen51.N_BYTES * k: gen51.VRAM_AT + gen51.N_BYTES * (k + 1)]
            for k in range(4)]
    return [sum(1 for b in r if b != 0xFF) for r in rows], list(after[gen51.VRAM_AT:gen51.VRAM_AT + 256]), \
        lost, reads


def photo(name, machine, keep=None):
    tmp = Path(tempfile.mkdtemp(prefix="mc51_"))
    pngs = msxcap.capture(HERE / f"{name}.rom", [PHOTO], tmp, "f", machine=machine,
                          events=keys_events(), timeout=600)
    dst = (keep or tmp) / f"{name}_{machine}.png"
    shutil.copy(pngs[PHOTO], dst)
    shutil.rmtree(tmp) if keep else None
    return dst


def grey(rgb):
    return Image.new("RGB", (1, 1), tuple(rgb)).convert("L").getpixel((0, 0))


def run_page(name, files):
    """name.rom on every machine: the page against the model, the counts
    against vdpslots.py, the variables, the colours"""
    CAPS.mkdir(exist_ok=True)
    out = {}
    for m in MACHINES:
        info = dict(files[m])
        info["lines"] = 313 if info["vdp"] == "TMS9929A" or \
            (info["vdp"].startswith("V99") and info["bios"][0] & 0x80) else 262
        d = debug_run(name, m)
        model_kept, model_vram, lost, reads = kept_model(d["ops"], m, info)
        v = d["mem"]["vars"]
        o = 0x10
        prog = {"idb": v[o:o + 3], "psgr": v[o + 3], "slotp": v[o + 4], "slots": v[o + 5],
                "turns": v[o + 6] | v[o + 7] << 8, "lines": v[o + 8] | v[o + 9] << 8,
                "s1": v[o + 10], "kept": v[o + 11:o + 15], "delay": v[o + 16] | v[o + 17] << 8,
                "keys": v[o + 18:o + 18 + len(gen51.KEYS)]}
        msx1 = info["bios"][2] == 0
        s1 = d["s0"] if (name == "blind" and msx1) else None
        png = photo(name, m, keep=CAPS)
        sc = page_model(info, model_kept, s1=s1)
        rom_data = ROMS_DATA(rom_path(m))
        bad, strip = page_against(png, sc, rom_data)
        regs = d["mem"]["regs"]
        outs = [6 * 0 + (f * info["lines"] * LINE + c) for f, c, port, v in d["ops"]
                if port == 0x98 and v is not None]
        gaps = [sorted({(b - a) // PER_T for a, b in zip(outs[64 * k:64 * k + 64], outs[64 * k + 1:64 * k + 64])})
                for k in range(4)]
        out[m] = {"gaps": gaps, "init_cycle": d["c0"], "init_line": d["c0"] // LINE, "jiffy": d["jiffy"],
                  "scncnt": d["scncnt"], "program": prog, "model_kept": model_kept,
                  "vram_same": d["mem"]["test"] == model_vram, "lost": len(lost),
                  "fast": len(d["fast"]), "page_cells_wrong": len(bad), "wrong_cells": bad[:6],
                  "strip": strip, "strip_grey": [grey(c) if c else None for c in strip],
                  "regs": regs, "palette": d["mem"]["pal"] if not msx1 else None,
                  "frames": {k: d[k] for k in ("askvdp", "vram", "askkeys", "fin")},
                  "s0": d["s0"], "text": [sc.text(r)[1:1 + gen51.WIDTH] for r in range(gen51.ROWS - 1)]}
        assert prog["kept"] == model_kept, (name, m, prog["kept"], model_kept)
        print(name, m, {k: out[m][k] for k in ("init_cycle", "model_kept", "vram_same", "fast",
                                              "page_cells_wrong", "s0")}, flush=True)
    return out


def rom_path(machine):
    return machine_file(machine)["rom"]


def which():
    return run_page("which", machines_cached())


def blind():
    return run_page("blind", machines_cached())


MACHINES_DONE = {}


def machines_cached():
    if not MACHINES_DONE:
        path = HERE / "meas51.json"
        old = json.loads(path.read_text()) if path.exists() else {}
        files = old.get("machines") or machines()
        for m in MACHINES:
            f = dict(files[m])
            info = machine_file(m)
            f["rom"] = info["rom"]
            f["bios"] = list(ROMS_DATA(info["rom"])[0x2B:0x2E])
            f["keys"] = [scancodes(ROMS_DATA(info["rom"]))[8 * r + c] for r, c in gen51.KEYS]
            MACHINES_DONE[m] = f
    return MACHINES_DONE


# ---------------------------------------------------------------- the games
def code_map(strip):
    """RGB -> colour code, from a machine's strip of colours 1-15"""
    return {tuple(c): k + 1 for k, c in enumerate(strip) if c}


def codes(png, cmap):
    im = Image.open(png).convert("RGB")
    px = im.load()
    return [[cmap.get(px[x, y]) for x in range(meas.DRAWN[0], meas.DRAWN[1] + 1)]
            for y in range(im.height)]


def strips_now():
    """each machine's strip of colours, from which.rom photographed again: for a
    run of games without the which section (tools/versions.py runs them apart)"""
    files = machines_cached()
    tmp = Path(tempfile.mkdtemp(prefix="strip51_"))
    out = {}
    try:
        for m in MACHINES:
            png = photo("which", m, keep=tmp)
            info = dict(files[m])
            _, strip = page_against(png, page_model(info, [64] * 4), ROMS_DATA(rom_path(m)))
            out[m] = {"strip": strip}
    finally:
        shutil.rmtree(tmp)
    return out


def games():
    files = machines_cached()
    path = HERE / "meas51.json"
    old = json.loads(path.read_text()) if path.exists() else {}
    strips = old["which"] if "which" in old else strips_now()
    out = {}
    for chapter in (44, 46):
        ref_first, ref_codes = {}, {}
        res = {}
        for m in [REF[50], REF[60]] + [x for x in MACHINES if x not in REF.values()]:
            rate = files[m]["rate"]
            args = [sys.executable, str(HERE / "play51.py"), str(chapter), m, str(rate)]
            if m not in REF.values():
                args.append(str(ref_first[rate]))
            r = subprocess.run(args, capture_output=True, text=True, timeout=7200,
                               cwd=HERE, env=os.environ)
            last = [l for l in r.stdout.splitlines() if l.startswith("{")]
            assert last, (chapter, m, r.stdout[-500:], r.stderr[-2000:])
            j = json.loads(last[-1])
            if m in REF.values():
                ref_first[rate] = j["first"]
            if "photo" in j:
                c = codes(j["photo"], code_map(strips[m]["strip"]))
                if m in REF.values():
                    ref_codes[rate] = c
                ref = ref_codes[rate]
                j["photo_cells"] = sum(1 for y in range(len(c)) for x in range(len(c[0]))
                                       if c[y][x] != ref[y][x])
                j["photo_unknown"] = sum(1 for row in c for v in row if v is None)
                shutil.rmtree(Path(j["photo"]).parent, ignore_errors=True)
                del j["photo"]
            res[m] = j
            print("game", chapter, m, j, flush=True)
        out[str(chapter)] = res
    return out


# ---------------------------------------------------------------- prices
def prices():
    """walk.py through which.rom's frame count and VRAM loops, with a frame
    flag that rises every frame of the 50 Hz machine; the OUTs' spacing, and
    the debugger's"""
    frame_t = meas.T_PER_FRAME["MSXBOOK_EU16"]
    flag = {"next": 1000}

    def read_port(port, t):
        if port == 0x99:
            if t >= flag["next"]:
                while flag["next"] <= t:
                    flag["next"] += frame_t
                return 0x80
            return 0
        if port == 0x98:
            return 0xFF
        return 0
    wk = walk.Walk(HERE / "which")
    wk.read_port = read_port
    wk.mem[0x2B:0x2E] = bytes([0xA1, 0x02, 0x00])
    t = wk.run("frame", "askvdp")
    s = dbg.sym(HERE / "which.sym")
    turns = wk.mem[s["turns"]] | wk.mem[s["turns"] + 1] << 8
    wk.ports.clear()
    t2 = wk.run("vram", "count")
    outs = [tt for tt, p, v in wk.ports if p == 0x98]
    gaps = [b - a for a, b in zip(outs, outs[1:])]
    per = [sorted(set(gaps[64 * k: 64 * k + 63])) for k in range(4)]
    d = json.loads((HERE / "meas51.json").read_text())["which"]
    return {"turns_walk": turns, "frame_t": frame_t, "turn_t": gen51.TURN,
            "loops_gaps": per, "vram_to_count": t2}


# ---------------------------------------------------------------- the workshop
def build_variant(kind):
    """the workshop's variant of which.asm, assembled in a folder of its own"""
    name, src = gen51.variant(kind)
    d = Path(tempfile.mkdtemp(prefix=f"{kind}51_"))
    for inc in ("msx.inc", "bios.inc"):
        shutil.copy(HERE / inc, d)
    (d / f"{name}.asm").write_text(src)
    subprocess.run(["sjasmplus", "--nologo", "--msg=err", "--syntax=bFw", f"--sym={name}.sym",
                    f"--lst={name}.lst", f"{name}.asm"], cwd=d, check=True)
    return name, d


def sweep(chip, rate, spacings=range(16, 31)):
    """vdpslots.py's bytes kept of 64 written SPACING T-states apart in the
    paper's 40th line, the first OUT at each T-state of the line: the fewest
    and the most"""
    m = f"sweep_{chip}_{rate}"
    vdpslots.PAPER0[m] = meas.PAPER_FRAME_LINE0[REF[rate]]
    vdpslots.LINES[m] = FRAME_LINES[rate]
    if chip == "v99":
        vdpslots.CHIP[m] = "v99"
    out = {}
    for sp in spacings:
        kept = []
        for o in range(meas.T_PER_LINE):
            t0 = (vdpslots.PAPER0[m] + 40) * LINE + PER_T * o
            ev = [(t0 - 6 * 40, 0x99, 0x00), (t0 - 6 * 20, 0x99, 0x7C)]      # write from $3C00
            ev += [(t0 + PER_T * sp * k, 0x98, k) for k in range(gen51.N_BYTES)]
            vram = bytearray(16384)
            vram[0x3C00:0x3C40] = b"\xff" * 64
            after, _, _ = vdpslots.play(ev, m, vram=vram, regs=[0, 0xC0, 0, 0, 0, 0, 0, 0])
            kept.append(sum(1 for b in after[0x3C00:0x3C40] if b != 0xFF))
        out[sp] = [min(kept), max(kept), sum(1 for k in kept if k == 64)]
    return out


def keys_run(folder, name, machine):
    """a run with the keys pressed, the BIOS's frame count, SCNCNT and the
    key buffer's two pointers logged at INIT and at the start of every frame"""
    ev = keys_events()
    for f in range(1, FRAMES):
        log = ('L "k ' + str(f) + ' [peek16 0xFC9E] [peek 0xF3F6] [peek16 0xF3F8] [peek16 0xF3FA]"')
        ev[f] = (ev[f] + "; " + log) if f in ev else log
    lines = msxcap.run_tcl(folder / f"{name}.rom", FRAMES,
                           'L "k 0 [peek16 0xFC9E] [peek 0xF3F6] [peek16 0xF3F8] [peek16 0xF3FA]"\n',
                           machine=machine, events=ev, timeout=600)
    rows = [list(map(int, l.split()[1:])) for l in lines if l.startswith("k ")]
    init = rows[0]
    rows = rows[1:]
    scans = [f for (f, j, sc, put, get), (f2, j2, sc2, put2, get2) in zip(rows, rows[1:])
             if sc2 > sc or (sc2 == 3 and j2 > j)]
    put = rows[-1][3] - 0xFBF0
    return {"first_scan": scans[0] if scans else None, "put": put, "taken": rows[-1][4] - 0xFBF0,
            "jiffy": init[1], "scncnt": init[2]}


def answers():
    d = json.loads((HERE / "meas51.json").read_text())
    out = {}
    # 1. the spacing that never loses a byte, wherever it starts; and w26.rom
    out["q1"] = {"tms_50": sweep("tms", 50), "tms_60": sweep("tms", 60),
                 "v99_50": sweep("v99", 50), "v99_60": sweep("v99", 60)}
    name, folder = build_variant("w26")
    try:
        w26 = {}
        for m in MACHINES:
            r = debug_run(name, m, folder)
            v = r["mem"]["vars"]
            w26[m] = v[0x10 + 11:0x10 + 15]
        out["q1"]["w26"] = w26
    finally:
        shutil.rmtree(folder)
    # 2. SCNCNT as the BIOS left it
    name, folder = build_variant("noscan")
    try:
        out["q2"] = {m: keys_run(folder, name, m) for m in MACHINES}
    finally:
        shutil.rmtree(folder)
    out["q2_which"] = {m: keys_run(HERE, "which", m) for m in (REF[50], REF[60])}
    # 3. the first loop of each game: INIT's place, main's, the interrupt's
    out["q3"] = {}
    for ch, res in d["games"].items():
        rows = {}
        for m, j in res.items():
            st = j["start"]
            fc = FRAME_LINES[j["rate"]] * LINE
            init_t = None
            if st["main"]:
                init_t = (st["main"][0] * fc + st["main"][1] - st["init"][1]) / PER_T
            rows[m] = {"init_t": init_t, "main": st["main"], "isr": st["isr"], "first": j["first"],
                       "shift": j.get("shift")}
        out["q3"][ch] = rows
    # 4. the greys of the strip, by VDP: in the which section, strip_grey
    # 5. the character each layout gives the keys of row 1 and 2
    out["q5"] = {}
    for m in (REF[50], REF[60]):
        table = scancodes(ROMS_DATA(rom_path(m)))
        out["q5"][m] = [chr(c) if 32 <= c < 127 else c for c in table[8:24]]
    return out


# ---------------------------------------------------------------- openMSX's builds
def openmsx():
    """every section again with every build, the games apart: a run of meas51.py
    in versions.rerun() must end within its time limit"""
    if not versions.builds():
        return {"skipped": "OPENMSX_BUILDS not set"}
    out = {}
    for part in OPENMSX_SECTIONS:
        for label, r in versions.every_build(["ch51"], part).items():
            o = out.setdefault(label, {"values": 0, "same_values": 0, "captures": 0,
                                       "same_captures": 0, "same_in_drawn": 0, "failed": [],
                                       "different": []})
            for k in ("values", "same_values", "failed", "different"):
                o[k] += r[k]
            for k in ("captures", "same_captures", "same_in_drawn"):
                o[k] = max(o[k], r[k])          # the captures are compared in each part
            o["version"], o["sha256"] = r["version"], r["sha256"]
    return out


OPENMSX_SECTIONS = [["machines", "which", "blind", "prices"], ["games", "answers"]]
SECTIONS = {"machines": machines, "which": which, "blind": blind, "prices": prices,
            "games": games, "answers": answers, "openmsx": openmsx}


def main(names=()):
    path = HERE / "meas51.json"
    old = json.loads(path.read_text()) if path.exists() else {}
    for n in (names or SECTIONS):
        old[n] = SECTIONS[n]()
        path.write_text(json.dumps(old, indent=1, sort_keys=True))
        print(n, "done", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
