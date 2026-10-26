#!/usr/bin/env python3
"""meas55.py -- testing on real hardware: check.rom and dirty.rom, measured.

    python3 gen55.py && ./build.sh && python3 meas55.py
                                       python3 meas55.py runs photos   only these

  runs      check.rom on the book's twelve machines and dirty.rom on its
            three 50 Hz machines of 16 KB that differ only in their RAM. The
            debugger reads the eight bytes at $E87C at INIT, A and F before
            and after each SCF, every operation on the VDP's ports from the
            first run to the count, with its cycle, and at the end the
            variables, the VRAM and the VDP's registers. They are held
            against: the RAM as the machine's file says it starts (openMSX
            fills it with $FF where the file says nothing); the PSG the file
            names; (F OR A) AND $28 of the A and F the debugger read before
            each SCF; a frame of 313 or 262 lines of 228 T-states, in turns of
            57; and vdpslots.py, which, given the port operations, gives the
            bytes each run lost and the VRAM, as many as openMSX's warnings
            of a byte too soon. The debugger's cycles say that every run's
            bytes went exactly its speed apart, 5 T-states more between two
            blocks, and that each run met all 228 T-states of the line with
            a byte that had another its speed after it; and the name table
            is the page the model writes
  photos    the pages photographed, the figures' among them, against
            vdpscreen.py's picture of the VRAM the debugger read
  patterns  what the descriptions of the MSX1 machines that come with
            openMSX say their RAM holds when switched on
  sweep     every cartridge of the book on MSXBOOK_EU16, MSXBOOK_EU16B and
            MSXBOOK_EU16S: the VRAM and the VDP's registers frame by frame,
            every frame the log has from INIT, 302 for a run of 300
  answers   the workshop, tried (for Appendix I)
  openmsx   runs, photos, sweep and answers again with every other build
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zlib
import base64
from fractions import Fraction
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
import gen55       # noqa: E402
sys.path.remove(str(HERE))
sys.path.insert(0, str(HERE))      # gen55 put chapter 51 first: this folder's files win
for mod in ("vdpslots", "vdpscreen"):
    sys.modules.pop(mod, None)
import vdpslots    # noqa: E402
import vdpscreen   # noqa: E402

assert Path(vdpslots.__file__).parent == HERE and Path(vdpscreen.__file__).parent == HERE

CAPS = HERE / "captures"
OUT_JSON = HERE / "meas55.json"
EU, JP = "MSXBOOK_EU16", "MSXBOOK_JP16"
B, S = "MSXBOOK_EU16B", "MSXBOOK_EU16S"
BOOK = [EU, JP, "MSXBOOK_EU8", "MSXBOOK_EU32", "MSXBOOK_EU64", "MSXBOOK_EU16AY", "MSXBOOK_EU16X",
        "MSXBOOK_EU16E", "MSXBOOK_EU16G", "MSXBOOK_EU16P", B, S]
RUNS_ON = {"check": BOOK, "dirty": [EU, B, S]}
LINE = vdpslots.LINE
PER_T = vdpslots.PER_T
FRAMES = 60                     # the page is finished well before
PHOTO = FRAMES - 2              # the frame photographed
POS = "[machine_info VDP_frame_count] [machine_info VDP_cycle_in_frame]"
PALETTE = [tuple(c) for c in json.loads((REPO / "ch01" / "meas01.json").read_text())["palette"]["rgb"]]
CODE = {rgb: n for n, rgb in enumerate(PALETTE) if n}
SWEEP_FRAMES = 300
SHARE = Path(os.environ.get("OPENMSX_SYSTEM_DATA", "/usr/share/openmsx"))

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


def num(f):
    return int(f) if f == int(f) else round(float(f), 2)


# ---------------------------------------------------------------- the machines' files
def machine_file(machine):
    """the VDP, the PSG and the RAM's first bytes at power-on, as the file says"""
    root = ET.parse(REPO / "machines" / f"{machine}.xml").getroot()
    psg = root.find(".//PSG/type")
    ram = None
    for dev in root.iter():
        if dev.tag in ("RAM", "MemoryMapper"):
            ic = dev.find("initialContent")
            mem = dev.find("mem")
            base, size = int(mem.get("base"), 16), int(mem.get("size"), 16)
            if base + size == 0x10000:
                ram = (base, None if ic is None else content(ic.get("encoding"), ic.text))
    return {"vdp": root.find(".//VDP/version").text,
            "psg": psg.text if psg is not None else "AY8910", "ram": ram}


def content(encoding, text):
    text = text.strip()
    if encoding == "hex":
        return bytes.fromhex(text)
    if encoding == "base64":
        return base64.b64decode(text)
    if encoding == "gz-base64":
        return zlib.decompress(base64.b64decode(text))
    raise ValueError(encoding)


def ram_at(info, addr, n):
    """the RAM at power-on: the file's pattern from the RAM's first byte,
    over and over; $FF where the file has none"""
    base, pat = info["ram"]
    if pat is None:
        return bytes([0xFF] * n)
    return bytes(pat[(a - base) % len(pat)] for a in range(addr, addr + n))


def lines_of(info):
    return 313 if info["vdp"] == "TMS9929A" else 262


def slots_for(machine, info):
    """vdpslots.py's tables are the reference machines'; the others have the
    same VDP as one of them"""
    ref = EU if lines_of(info) == 313 else JP
    vdpslots.PAPER0[machine] = vdpslots.PAPER0[ref]
    vdpslots.LINES[machine] = vdpslots.LINES[ref]


# ---------------------------------------------------------------- the page the model writes
class Screen:
    def __init__(self):
        self.rows = [[" "] * 32 for _ in range(24)]

    def put(self, row, col, text):
        for i, ch in enumerate(text):
            r, c = row + (col + i) // 32, (col + i) % 32
            self.rows[r][c] = ch

    def text(self):
        return ["".join(r) for r in self.rows]


def page_model(ram8, psgr, xy, turns, lost, least):
    sc = Screen()
    for k, s in gen55.LABELS.items():
        sc.put(*gen55.AT[k], s)
    sc.put(*gen55.AT["rambytes"], " ".join(f"{b:02X}" for b in ram8))
    chip = {0xFF: "YM2149", 0x0F: "AY-3-8910"}.get(psgr, "?")
    sc.put(gen55.AT["psg"][0], gen55.col_after("psg"), f"{psgr:02X} {chip}")
    sc.put(gen55.AT["scf"][0], gen55.col_after("scf"), " ".join(f"{v:02X}" for v in xy))
    sc.put(gen55.AT["frame"][0], gen55.col_after("frame") - 1, f"{turns:5d} x {gen55.TURN} T")
    for i, t in enumerate(gen55.SPEEDS):
        sc.put(gen55.AT["speeds"][0], gen55.CELLS + 3 * i, f"{t:3d}")
        sc.put(gen55.AT["lost"][0], gen55.CELLS + 3 * i, f"{lost[i]:3d}")
    sc.put(gen55.AT["least"][0], gen55.col_after("least") - 1, f"{least:3d} T")
    return sc.text()


def page_read(vram):
    names = vram[0x1800:0x1B00]
    return ["".join(chr(b) for b in names[32 * r:32 * r + 32]) for r in range(24)]


# ---------------------------------------------------------------- the runs
def scf_addresses(name, folder=HERE):
    """the address of each SCF or CCF of flags, from the listing"""
    out = []
    for line in (folder / f"{name}.lst").read_text().splitlines():
        m = dbg.LST.match(line)
        if not m or "..." in m.group(3)[1:13]:
            continue
        _, a, code, src = dbg.lst_fields(m)
        if code in ([0x37], [0x3F]) and src.split(";")[0].strip() in ("scf", "ccf"):
            out.append(a)
    assert len(out) == len(gen55.FLAG_CASES), out
    return out


def debug_run(name, machine, folder=HERE):
    """the debugger's log of NAME on MACHINE"""
    s = dbg.sym(folder / f"{name}.sym")
    rom = folder / f"{name}.rom"
    scfs = scf_addresses(name, folder)
    tcl = (f'M ram {gen55.SAMPLE} 8\nL "c0 [machine_info VDP_cycle_in_frame]"\n' + TOO_FAST +
           "".join(f'debug set_bp {a} {{}} {{ L "before {k} [reg af]" }}\n'
                   f'debug set_bp {a + 1} {{}} {{ L "after {k} [reg af]" }}\n' for k, a in enumerate(scfs)) +
           f'debug set_bp {s["vram"]} {{}} {{ L "vram {POS}"; '
           f'set ::w1 [debug set_watchpoint write_io {{0x98 0x99}} {{}} '
           f'{{ L "o [expr {{$::wp_last_address & 255}}] $::wp_last_value {POS}" }}] }}\n'
           f'debug set_bp {s["count"]} {{}} {{ L "count {POS}"; debug remove_watchpoint $::w1 }}\n'
           f'set ::shown 0\n'
           f'debug set_bp {s["done"]} {{}} {{ if {{!$::shown}} {{ set ::shown 1; L "fin {POS}" }} }}\n')
    # the end read in the last frame: a byte written at done may still be on its way
    end = f"M vars {gen55.VARS_AT} 64; VR end 0 16384; DB regs {{VDP regs}} 8"
    lines = msxcap.run_tcl(rom, FRAMES, tcl, machine=machine, tcl_setup=STATE, timeout=900,
                           events={FRAMES - 1: end})
    w = [x.split() for x in lines]
    f0 = int(next(x for x in w if x[0] == "f0")[1])
    out = {"ops": [], "fast": [], "mem": {}, "before": {}, "after": {},
           "init": int(next(x for x in w if x[0] == "c0")[1])}
    for x in w:
        if x[0] in ("vram", "count", "fin"):
            out[x[0]] = [int(x[1]) - f0, int(x[2])]
        elif x[0] in ("before", "after"):
            out[x[0]][int(x[1])] = int(x[2])
        elif x[0] == "o":
            out["ops"].append((int(x[3]) - f0, int(x[4]), int(x[1]), int(x[2])))
        elif x[0] == "fast":
            out["fast"].append((int(x[1]) - f0, int(x[2])))
        elif len(x) == 3 and x[1] in ("mem", "vram", "db"):
            out["mem"][x[0]] = bytes.fromhex(x[2])
    assert "fin" in out and len(out["before"]) == len(gen55.FLAG_CASES), (name, machine)
    return out


def run_blocks(ops):
    """the port operations split into the runs: each run is the two writes
    to $99 of its address and then its bytes to $98, with the index of each
    operation"""
    blocks, cur = [], None
    k = 0
    while k < len(ops):
        f, c, port, v = ops[k]
        if port == 0x99:
            assert ops[k + 1][2] == 0x99, k
            addr = v | (ops[k + 1][3] & 0x3F) << 8
            cur = {"addr": addr, "bytes": [], "index": []}
            blocks.append(cur)
            k += 2
            continue
        cur["bytes"].append((f, c, v))
        cur["index"].append(k)
        k += 1
    assert len(blocks) == len(gen55.SPEEDS), len(blocks)
    return blocks


def expected_gaps(t, split=True):
    """the T-states from each byte of the run of speed T to the next: T, and
    T + 5 from the last byte of a block to the first of the next"""
    out = []
    for k, n in enumerate(gen55.blocks(t, split)):
        out += [t] * (n - 1) + ([t + gen55.SHIFT] if k < len(gen55.blocks(t, split)) - 1 else [])
    return out


def flag_rules(before):
    """what SCF leaves in bits 5 and 3 by three rules, from A and F before it:
    openMSX's, (F OR A); a Zilog's as Patrik Rak and David Banks found it,
    A's own bits when the instruction before SCF changed the flags and
    (F OR A) when it did not; and a NEC NMOS Z80's as David Banks found it,
    A's own bits every time"""
    out = {"openmsx": [], "zilog": [], "nec": []}
    for k, (_, _, between, _) in enumerate(gen55.FLAG_CASES):
        a, f = before[k] >> 8, before[k] & 0xFF
        changed = between is None                   # CP right before SCF
        out["openmsx"].append((f | a) & 0x28)
        out["zilog"].append(a & 0x28 if changed else (f | a) & 0x28)
        out["nec"].append(a & 0x28)
    return out


def analyse(name, machine, folder=HERE, split=True, least_at=None):
    """a run of NAME on MACHINE against the models; the measured values"""
    info = machine_file(machine)
    slots_for(machine, info)
    r = debug_run(name, machine, folder)
    ram8 = r["mem"]["ram"]
    v = r["mem"]["vars"]
    vram = r["mem"]["end"]
    regs = list(r["mem"]["regs"])
    var = lambda label, n=1: v[gen55_var(label) - gen55.VARS_AT:][:n]     # noqa: E731
    got = {"ram": list(var("ramb", 8)), "psgr": var("psgr")[0], "xy": list(var("xy", 4)),
           "turns": int.from_bytes(var("turns", 2), "little"), "lost": list(var("lost", len(gen55.SPEEDS))),
           "least": v[(least_at if least_at is not None else 0x2D)]}
    # the RAM at INIT, as the file says, as the debugger read it, as the cartridge kept it
    model_ram = list(ram_at(info, gen55.SAMPLE, 8))
    assert list(ram8) == got["ram"] == model_ram, (name, machine, list(ram8), got["ram"], model_ram)
    # the PSG
    assert got["psgr"] == {"YM2149": 0xFF, "AY8910": 0x0F}[info["psg"]], (name, machine, got["psgr"])
    # the flags: what the debugger saw after each SCF, the cartridge's, and openMSX's rule
    rules = flag_rules(r["before"])
    after = [r["after"][k] & 0x28 for k in range(len(gen55.FLAG_CASES))]
    assert after == got["xy"] == rules["openmsx"], (name, machine, after, got["xy"], rules)
    # the frame
    lines = lines_of(info)
    assert got["turns"] * gen55.TURN == lines * 228, (name, machine, got["turns"])
    # the runs: the debugger's cycles, vdpslots.py, the VRAM
    runs_ = run_blocks(r["ops"])
    flen = vdpslots.LINES[machine] * LINE
    cover, starts, ends = [], [], []
    for run, t in zip(runs_, gen55.SPEEDS):
        cyc = [f * flen + c for f, c, _ in run["bytes"]]
        assert len(cyc) == gen55.N_BYTES
        gaps = [(b - a) // PER_T for a, b in zip(cyc, cyc[1:])]
        assert all((b - a) % PER_T == 0 for a, b in zip(cyc, cyc[1:]))
        assert gaps == expected_gaps(t, split), (name, machine, t)
        # the T-states of the line at which a byte went with another T after it
        met = {cyc[k] % LINE for k in range(len(gaps)) if gaps[k] == t}
        assert len({x % PER_T for x in met}) == 1
        cover.append(len(met))
        # every byte while the VDP draws the paper, where its moments are few
        assert all(vdpslots.busy(x, machine) for x in cyc), (name, machine, t)
        starts.append((cyc[0] % flen) // LINE - vdpslots.PAPER0[machine])
        ends.append((cyc[-1] % flen) // LINE - vdpslots.PAPER0[machine])
    if split:
        assert cover == [LINE // PER_T] * len(gen55.SPEEDS), (name, machine, cover)
    evs = [(f * flen + c, port, val) for f, c, port, val in r["ops"]]
    start = bytearray(16384)
    area = len(gen55.SPEEDS) * gen55.N_BYTES
    start[gen55.VRAM_AT:gen55.VRAM_AT + area] = b"\xff" * area
    played, _, lost_play = vdpslots.play(evs, machine, vram=bytes(start), regs=list(regs))
    assert played[gen55.VRAM_AT:gen55.VRAM_AT + area] == vram[gen55.VRAM_AT:gen55.VRAM_AT + area], \
        (name, machine, "played")
    assert len(lost_play) == len([x for x in r["fast"] if r["vram"] <= list(x) <= r["count"]]) \
        == len(r["fast"]), (name, machine, len(lost_play), len(r["fast"]))
    # each run's lost bytes: the VRAM's $FF at the end of its bytes, the model's
    # bytes too soon, and, by the model, block by block
    lost_set = set(lost_play)
    vram_lost, per_block = [], []
    for run, t in zip(runs_, gen55.SPEEDS):
        a = run["addr"]
        vram_lost.append(sum(1 for b in vram[a:a + gen55.N_BYTES] if b == 0xFF))
        assert vram_lost[-1] == sum(1 for i in run["index"] if i in lost_set)
        blk, at = [], 0
        for n in gen55.blocks(t, split):
            blk.append(sum(1 for i in run["index"][at:at + n] if i in lost_set))
            at += n
        per_block.append(blk)
    assert vram_lost == got["lost"], (name, machine, vram_lost, got["lost"])
    least_model = min([t for t, n in zip(gen55.SPEEDS, vram_lost) if n == 0], default=0xFF)
    if name == "check":
        assert got["least"] == least_model, (name, machine, got["least"], least_model)
    # the page
    page = page_model(got["ram"], got["psgr"], got["xy"], got["turns"], got["lost"], got["least"])
    assert page_read(vram) == page, (name, machine, page_read(vram), page)
    return {"ram": got["ram"], "psgr": got["psgr"], "psg": info["psg"], "xy": got["xy"],
            "rules": rules, "a_before": [r["before"][k] >> 8 for k in range(len(gen55.FLAG_CASES))],
            "f_before": [r["before"][k] & 0xFF for k in range(len(gen55.FLAG_CASES))],
            "turns": got["turns"], "lines": lines, "lost": got["lost"], "cover": cover,
            "per_block": per_block, "least": got["least"], "least_model": least_model,
            "fast": len(r["fast"]), "runs": len(runs_),
            "start_lines": sorted(set(starts)), "end_lines": [min(ends), max(ends)],
            "init": [r["init"] // LINE, num(Fraction(r["init"] % LINE, PER_T))],
            "frames": {"vram": r["vram"][0], "count": r["count"][0], "done": r["fin"][0]},
            "vram": vram, "regs": regs}


SYMS = {}


def gen55_var(label):
    if label not in SYMS:
        SYMS.update(dbg.sym(HERE / "check.sym"))
    return SYMS[label]


CACHE = {}


def result(name, machine):
    if (name, machine) not in CACHE:
        CACHE[(name, machine)] = analyse(name, machine)
    return CACHE[(name, machine)]


def runs():
    out = {}
    for name, ms in RUNS_ON.items():
        for m in ms:
            res = result(name, m)
            out.setdefault(name, {})[m] = {k: v for k, v in res.items() if k not in ("vram", "regs")}
            print("runs", name, m, res["ram"], res["xy"], res["turns"], res["lost"], res["least"], flush=True)
    return out


# ---------------------------------------------------------------- the photos
def codes(png):
    im = Image.open(png).convert("RGB")
    px = im.load()
    return [[CODE.get(px[x, y]) for x in range(im.width)] for y in range(im.height)]


def picture_of(vram, regs):
    """vdpscreen.py's picture of the page, in the capture's drawn columns:
    the paper, and the border round it"""
    paper = vdpscreen.draw(vram, regs)
    border = regs[7] & 15
    out = []
    for y in range(meas.CAPTURE_H):
        row = [None] * meas.CAPTURE_W
        for x in range(meas.DRAWN[0], meas.DRAWN[1] + 1):
            px, py = x - meas.PAPER_X0, y - meas.PAPER_Y0
            row[x] = (paper[py][px] or border) if 0 <= px < 256 and 0 <= py < 192 else border
        out.append(row)
    return out


FIGURES = {("check", EU): "fig55_1", ("check", JP): "fig55_1", ("dirty", B): "fig55_2"}


def photos():
    CAPS.mkdir(exist_ok=True)
    out = {}
    for name, ms in RUNS_ON.items():
        for m in ms:
            res = result(name, m)
            tmp = Path(tempfile.mkdtemp(prefix="ph55_"))
            pngs = msxcap.capture(HERE / f"{name}.rom", [PHOTO], tmp, "f", machine=m, timeout=900)
            got = codes(pngs[PHOTO])
            want = picture_of(res["vram"], res["regs"])
            bad = sum(1 for y in range(meas.CAPTURE_H) for x in range(meas.DRAWN[0], meas.DRAWN[1] + 1)
                      if got[y][x] != want[y][x])
            assert bad == 0, (name, m, bad)
            if (name, m) in FIGURES:
                shutil.copy(pngs[PHOTO], CAPS / f"{name}_{m}.png")
            shutil.rmtree(tmp)
            out.setdefault(name, {})[m] = {"frame": PHOTO, "different": bad}
            print("photos", name, m, bad, flush=True)
    return out


# ---------------------------------------------------------------- what C-BIOS writes first
def bios():
    """the RAM at INIT on the two machines whose RAM starts $FF and 00/FF:
    the bytes that are not what the machine's file says, so the BIOS's (a
    byte it wrote with the pattern's own value does not show)"""
    out = {}
    for m in (EU, B):
        lines = msxcap.run_tcl(HERE / "check.rom", 2, "M ram 0xC000 0x4000\n", machine=m,
                               tcl_setup=STATE)
        ram = bytes.fromhex(next(x.split()[2] for x in lines if x.startswith("ram mem ")))
        pat = ram_at(machine_file(m), 0xC000, 0x4000)
        diff = [0xC000 + i for i in range(0x4000) if ram[i] != pat[i]]
        low = [a for a in diff if a < gen55_var("SYS_AREA")]
        starts = [a for a in low if a & 0xFF == 0]
        rest = [a for a in low if a & 0xFF]
        out[m] = {"pages": len(starts), "page_values": sorted({ram[a - 0xC000] for a in starts}),
                  "below": [min(rest), max(rest)] if rest else None, "below_n": len(rest),
                  "in_range": len([a for a in low if rest and min(rest) <= a <= max(rest)]),
                  "system": len([a for a in diff if a >= gen55_var("SYS_AREA")])}
    print("bios", out, flush=True)
    return out


# ---------------------------------------------------------------- openMSX's own machines
def patterns():
    """the MSX1 machines described in openMSX's share folder, real models
    only (no C-BIOS machine, no file that is another's second name): how many
    give their RAM a pattern at power-on, and the commonest patterns"""
    groups, total = {}, 0
    for x in sorted((SHARE / "machines").glob("*.xml")):
        if x.is_symlink() or x.name.startswith("C-BIOS"):
            continue                    # a second name for another file; C-BIOS's own
        text = x.read_text(errors="replace")
        t = re.search(r"<type>([^<]*)</type>", text)
        if not t or t.group(1) != "MSX":
            continue
        total += 1
        m = re.search(r'<initialContent encoding="([^"]*)">([^<]*)</initialContent>', text)
        if not m:
            continue
        pat = content(*m.groups())
        groups.setdefault(pat.hex(), []).append(x.stem)
    top = sorted(groups.items(), key=lambda kv: -len(kv[1]))
    # and what openMSX does with a byte too soon when nobody has said
    lines = msxcap.run_tcl(HERE / "check.rom", 2, 'L "setting [set too_fast_vram_access]"\n')
    setting = next(x.split()[1] for x in lines if x.startswith("setting "))
    return {"share": str(SHARE), "msx1": total, "with_pattern": sum(len(v) for v in groups.values()),
            "kinds": len(groups), "too_fast_vram_access": setting,
            "other_bytes": sorted(m for p, v in groups.items() if set(bytes.fromhex(p)) - {0, 0xFF}
                                  for m in v),
            "top": [{"first": p[:16], "bytes": len(p) // 2, "pattern": p, "machines": v}
                    for p, v in top[:4]]}


# ---------------------------------------------------------------- every cartridge of the book
SWEEP_TCL = ('proc ::crcframe {} { set r {}; for {set i 0} {$i < 8} {incr i} '
             '{ lappend r [debug read {VDP regs} $i] }; '
             'L "c [machine_info VDP_frame_count] [zlib crc32 [debug read_block VRAM 0 0x4000]] $r"; '
             'after frame ::crcframe }\n::crcframe\n')


def cartridges():
    return sorted(p for p in REPO.glob("ch*/*.rom") if p.parent.name != "ch55")


def frames_of(rom, machine):
    if rom.read_bytes()[:2] != b"AB":
        return None                     # no header: no INIT to start from
    lines = msxcap.run_tcl(rom, SWEEP_FRAMES, SWEEP_TCL, machine=machine, timeout=600)
    w = [x.split() for x in lines if x.startswith("c ")]
    f0 = int(w[0][1])
    return [(int(x[1]) - f0, " ".join(x[2:])) for x in w]


def sweep():
    from concurrent.futures import ThreadPoolExecutor
    roms = cartridges()
    jobs = [(r, m) for r in roms for m in (EU, B, S)]
    with ThreadPoolExecutor(2) as ex:
        res = list(ex.map(lambda j: frames_of(*j), jobs))
    films = {}
    for (r, m), v in zip(jobs, res):
        films.setdefault(str(r.relative_to(REPO)), {})[m] = v
    out = {"cartridges": len(roms), "frames": SWEEP_FRAMES, "no_header": [], "different": {}}
    for k, v in films.items():
        if v[EU] is None:
            out["no_header"].append(k)
            continue
        for m in (B, S):
            if v[m] != v[EU]:
                diff = [i for i, (a, b) in enumerate(zip(v[EU], v[m])) if a != b]
                out["different"].setdefault(k, {})[m] = {"frames": len(diff), "first": diff[0],
                                                         "of": len(v[EU])}
    print("sweep", out["cartridges"], len(out["no_header"]), out["different"], flush=True)
    return out


# ---------------------------------------------------------------- the workshop
def variant(name, **kw):
    """gen55.program(NAME, **KW) assembled in a folder of its own"""
    tmp = Path(tempfile.mkdtemp(prefix="var55_"))
    for f in ("msx.inc", "bios.inc"):
        shutil.copy(HERE / f, tmp / f)
    (tmp / f"{name}.asm").write_text(gen55.program(name, **kw))
    subprocess.run(["sjasmplus", "--nologo", "--msg=err", "--syntax=bFw", f"--sym={name}.sym",
                    f"--lst={name}.lst", f"{name}.asm"], cwd=tmp, check=True)
    return tmp


def answers():
    out = {}
    # 1. check.rom on the twelve machines: what differs from the machine of its rate
    rn = json.loads(OUT_JSON.read_text())["runs"]["check"]
    keys = ("ram", "psgr", "xy", "turns", "lost", "least")
    q1 = {}
    for m, r in rn.items():
        ref = rn[EU if r["lines"] == 313 else JP]
        q1[m] = sorted(k for k in keys if r[k] != ref[k])
    out["q1"] = q1
    # 2. each run in one block: no NOPs
    tmp = variant("check", split=False)
    out["q2"] = {}
    for m in (EU, JP):
        res = analyse("check", m, folder=tmp, split=False)
        out["q2"][m] = {"lost": res["lost"], "least": res["least"], "cover": res["cover"]}
    shutil.rmtree(tmp)
    # 3. least one byte on: dirty.rom on the two machines of real RAM
    tmp = variant("dirty", least_at=0x2E)
    out["q3"] = {}
    for m in (B, S):
        res = analyse("dirty", m, folder=tmp, least_at=0x2E)
        out["q3"][m] = {"least": res["least"], "ram_byte": list(ram_at(machine_file(m), gen55.VARS_AT + 0x2E, 1))[0]}
    shutil.rmtree(tmp)
    # 4. CCF for SCF
    tmp = variant("check", ccf=True)
    res = analyse("check", EU, folder=tmp)
    out["q4"] = {"xy": res["xy"], "rules": res["rules"]}
    shutil.rmtree(tmp)
    print("answers", out, flush=True)
    return out


# ---------------------------------------------------------------- openMSX's builds
def openmsx():
    """the sections again with every build: each run in versions.rerun() must
    end within its time limit"""
    if not versions.builds():
        return {"skipped": "OPENMSX_BUILDS not set"}
    out = {}
    for part in OPENMSX_SECTIONS:
        for label, r in versions.every_build(["ch55"], part).items():
            o = out.setdefault(label, {"values": 0, "same_values": 0, "captures": 0,
                                       "same_captures": 0, "same_in_drawn": 0, "failed": [],
                                       "different": []})
            for k in ("values", "same_values", "failed", "different"):
                o[k] += r[k]
            for k in ("captures", "same_captures", "same_in_drawn"):
                o[k] = max(o[k], r[k])
            o["version"], o["sha256"] = r["version"], r["sha256"]
    return out


OPENMSX_SECTIONS = [["runs", "photos", "bios", "sweep", "answers"]]
SECTIONS = {"runs": runs, "photos": photos, "bios": bios, "patterns": patterns, "sweep": sweep,
            "answers": answers, "openmsx": openmsx}


def main(names=()):
    m = json.loads(OUT_JSON.read_text()) if names and OUT_JSON.exists() else {}
    for name in names or SECTIONS:
        print(name, flush=True)
        m[name] = SECTIONS[name]()
        m = {k: m[k] for k in SECTIONS if k in m}
        OUT_JSON.write_text(json.dumps(m, indent=1) + "\n")
    return m


if __name__ == "__main__":
    main(sys.argv[1:])
