#!/usr/bin/env python3
"""meas53.py -- chapter 53's picture, packed and unpacked, measured.

    python3 gen53.py && ./build.sh && python3 meas53.py
                                  python3 meas53.py sizes films   only these

  sizes     pack53.py's three packers on the picture's two halves and on
            LANTERN KEEP's sixteen rooms (chapter 45): the bytes, the parts,
            each packed stream unpacked again by Python; and count(), the
            T-states of each program from go to whole worked out from the
            parts and the listing's prices, without running anything
  films     each program on each machine, from INIT: the debugger stops at
            go, half and whole, a watchpoint logs every byte to and from the
            VDP's ports, openMSX's too_fast_vram_access callback logs every
            byte too soon, and the VRAM is read where the picture is whole.
            The same program walked by walk.py from INIT, with a VDP that
            keeps a VRAM for the reads: the T-states between the labels, and
            every port operation, value and moment, held against the
            debugger's. The debugger's bytes played through vdpslots.py
            (chapter 20): the VRAM it gives against the debugger's, the bytes
            it loses against openMSX's callback; the least gap between two
            accesses to $98 while the paper is drawn; from the walk, the
            T-states each row of cells took to be whole
  photos    frames of each program photographed, each against vdpscreen.py's
            picture of the VRAM line by line, as the bytes reached it
            (figures 53.1 to 53.3); the first frame that shows the picture
            as it stays
  rooms     the sixteen rooms unpacked by each unpacker of the cartridges,
            by walk.py, straight into the name table, against chapter 45's
            unpack into the RAM
  answers   the workshop, tried (for Appendix I)
  openmsx   films and photos again with every other build (tools/versions.py)
"""
import json
import math
import shutil
import sys
import tempfile
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
for mod in ("vdpscreen", "walk", "vdpslots"):
    sys.modules.pop(mod, None)
import gen53       # noqa: E402
import pack53      # noqa: E402
import pic53       # noqa: E402
import vdpscreen   # noqa: E402
import walk        # noqa: E402
import vdpslots    # noqa: E402

assert Path(vdpscreen.__file__).parent == HERE and Path(walk.__file__).parent == HERE
assert Path(vdpslots.__file__).parent == HERE

CAPS = HERE / "captures"
SHOTS = HERE / "shots"
EU, JP = gen53.EU, gen53.JP
MACHINES = gen53.MACHINES
TAG = {EU: "eu", JP: "jp"}
PROGRAMS = gen53.PROGRAMS
LINE = vdpslots.LINE
FT = {EU: 71364, JP: 59736}
POS = "[machine_info VDP_frame_count] [machine_info VDP_cycle_in_frame]"
PALETTE = [tuple(c) for c in json.loads((REPO / "ch01" / "meas01.json").read_text())["palette"]["rgb"]]
CODE = {rgb: n for n, rgb in enumerate(PALETTE) if n}
OUT_JSON = HERE / "meas53.json"
MARKS = ("go", "half", "whole")
HALF_AT = {"patterns": 0x0000, "colours": 0x2000}

STATE = r"""
proc VR {tag addr n} {
    binary scan [debug read_block VRAM $addr $n] H* h
    L "$tag vram $h"
}
"""
TOO_FAST = ('proc ::toofast_cb {args} { L "fast [machine_info VDP_frame_count] '
            '[machine_info VDP_cycle_in_frame]" }\n'
            'set VDP.too_fast_vram_access_callback ::toofast_cb\n')
F0 = 'L "i0 [machine_info VDP_frame_count] [machine_info VDP_cycle_in_frame]"\n'
PORTS = ('debug set_watchpoint write_io {0x98 0x99} {} '
         '{ L "o [expr {$::wp_last_address & 255}] $::wp_last_value ' + POS + '" }\n'
         'debug set_watchpoint read_io 0x98 {} { L "i 152 - ' + POS + '" }\n')


def num(f):
    return int(f) if f == int(f) else round(float(f), 2)


def sym(name, folder=HERE):
    return dbg.sym(folder / f"{name}.sym")


def codes(png):
    im = Image.open(png).convert("RGB")
    px = im.load()
    return [[CODE.get(px[x, y]) for x in range(im.width)] for y in range(im.height)]


# ---------------------------------------------------------------- sizes and the count
def parts_of(packed, kind):
    """the parts of a packed stream: how many of each, the bytes they give,
    the longest; for lz, the copies that end in the next page of the VRAM"""
    t = pack53.tokens(packed, kind)
    out = {"bytes": len(packed), "gives": sum(g for _, g, _ in t)}
    for what in ("lit", "run", "copy"):
        ts = [g for k, g, _ in t if k == what]
        if ts:
            out[what] = {"parts": len(ts), "bytes": sum(ts), "longest": max(ts)}
    if kind == "lz":
        at, crossing = 0, 0
        for what, g, _ in t:
            crossing += what == "copy" and (at & 255) + g > 255
            at += g
        out["copy"]["crossing"] = crossing
    return out


def rooms():
    """LANTERN KEEP's sixteen rooms as chapter 45 has them: 736 names each,
    rows 1 to 23, and chapter 45's own runs"""
    sys.path.insert(0, str(REPO / "ch45"))
    try:
        import gen45
    finally:
        sys.path.remove(str(REPO / "ch45"))
    return ([[t for row in gen45.grid(k) for t in row] for k in range(gen45.ROOMS)],
            [len(r) for r in gen45.RUN_BYTES])


# the prices of the parts, from the listings' comments, worked out by hand
# from them; films holds them against walk.py and the debugger
VRAM_WRITE = 8 + 12 + 8 + 12            # VRAM_WRITE: LD A,n, OUT (n),A twice
LD16, LD8, CALL = 11, 8, 18
NEXT = 8 + 7 + 5 + 6 + 11               # a count read, not 0, JP M either way
END = 8 + 7 + 5 + 12                    # the count 0: RET Z taken


def send_t(pages):
    """send: LD C and LD B, then each page's 256 OUTIs and JP NZs, DEC D and
    JP NZ; the RET"""
    return 8 + 8 + pages * (256 * 29 + 5 + 11) + 11


def part_t(fmt, what, n, e):
    """one part giving N bytes, the low byte of the VRAM address E where it
    starts (lz's copies take 16 T-states more when they cross a page: JP NC
    not taken, INC D and JP)"""
    if fmt in ("rlec", "otir"):
        if what == "lit":
            return NEXT + 5 + (29 * n if fmt == "rlec" else 23 * n - 5) + 11
        return NEXT + 8 + 5 + 8 + 7 + 30 * n + 11
    if fmt == "rlem":
        if what == "lit":
            return (8 + 7 + 5 + 8 + 12 + 11) * n
        return 8 + 7 + 5 + 13 + 8 + 7 + 5 + 6 + 5 + 8 + 7 + 30 * n + 11
    if fmt == "lz":
        if what == "lit":
            return NEXT + 5 + 5 + 5 + 13 + 29 * n + 11
        return (NEXT + 8 + 5 + 5 + 5 + 8 + 7 + 12 + 5 + 8 + 12 + 12 + 11 + 29 * n +
                5 + 8 + 5 + 12 + 5 + 8 + 12 + 29 * n + 5 + 11 + 5 + 5 +
                (11 + 5 + 11 if e + n > 255 else 11))
    if fmt == "lzram":
        if what == "lit":
            return NEXT + 5 + 8 + 23 * n - 5 + 11
        return NEXT + 8 + 5 + 5 + 5 + 8 + 7 + 12 + 5 + 5 + 8 + 5 + 8 + 23 * n - 5 + 11 + 11
    raise ValueError(fmt)


def count(name):
    """T-states from go to half and from half to whole, from the packed parts
    and the prices above, nothing run"""
    out = []
    for half in gen53.HALVES:
        if name == "raw":
            out.append(VRAM_WRITE + LD16 + LD8 + CALL + send_t(gen53.PAGES))
            continue
        fmt = {"rlem": "rlem", "rlec": "rlec", "lz": "lz", "lzram": "lzram",
               "otir": "otir", "dark": "otir"}[name]
        kind = gen53.FORMAT[name]
        t = {"rlem": VRAM_WRITE + LD16 + CALL + 8 + 7 + 8, "rlec": VRAM_WRITE + LD16 + CALL + 8,
             "otir": VRAM_WRITE + LD16 + CALL + 8, "lz": LD16 + LD16 + CALL + 8 + 5 + 12 + 5 + 8 + 12,
             "lzram": LD16 + LD16 + CALL}[fmt]
        e = 0
        for what, n, _ in pack53.tokens(gen53.packed(kind, half), kind):
            if what == "end":
                t += END if fmt != "rlem" else 8 + 7 + 5 + 13 + 8 + 7 + 5 + 12
            else:
                t += part_t(fmt, what, n, e)
                e = (e + n) & 255
        if fmt == "lzram":
            t += VRAM_WRITE + LD16 + LD8 + CALL + send_t(gen53.PAGES)
        out.append(t)
    return out


def sizes():
    out = {"picture": {}, "rooms": {}}
    for half, (_, data) in gen53.HALVES.items():
        out["picture"][half] = {"raw": len(data)}
        for kind, (pack, unpack) in pack53.PACKERS.items():
            p = pack(list(data))
            assert unpack(p) == list(data), (half, kind)
            out["picture"][half][kind] = parts_of(p, kind)
        out["picture"][half]["marker"] = pack53.marker(list(data))
    rs, ch45 = rooms()
    out["rooms"] = {"raw": sum(map(len, rs)), "count": len(rs), "ch45": sum(ch45),
                    "ch45_each": ch45}
    for kind, (pack, unpack) in pack53.PACKERS.items():
        each = []
        for r in rs:
            p = pack(r)
            assert unpack(p) == r
            each.append(len(p))
        out["rooms"][kind] = sum(each)
        out["rooms"][kind + "_each"] = each
    out["count"] = {name: count(name) for name in PROGRAMS}
    return out


# ---------------------------------------------------------------- walk.py with a VRAM
class VramFollow:
    """the VRAM as a walk's port operations so far leave it, for its INs:
    chapter 19's rules for the address, the byte read ahead and the byte
    kept, and no time at all (the films hold the time)"""
    def __init__(self, wk):
        self.wk, self.seen = wk, 0
        self.vram, self.addr, self.held, self.kept = bytearray(16384), 0, None, 0

    def follow(self):
        for _, port, v in self.wk.ports[self.seen:]:
            if port == 0x99:
                if v is None:
                    self.held = None
                elif self.held is None:
                    self.held, self.addr = v, (self.addr & 0x3F00) | v
                else:
                    first, self.held = self.held, None
                    if not v & 0x80:
                        self.addr = (v & 0x3F) << 8 | first
                        if not v & 0x40:                # a read address: read ahead
                            self.kept = self.vram[self.addr]
                            self.addr = (self.addr + 1) & 0x3FFF
            elif port == 0x98:
                self.held = None
                if v is None:
                    self.kept = self.vram[self.addr]
                else:
                    self.kept = self.vram[self.addr] = v
                self.addr = (self.addr + 1) & 0x3FFF
        self.seen = len(self.wk.ports)

    def read(self, port, t):
        self.follow()
        return self.kept if port == 0x98 else 0


KIND = {(0xD3,): "OUT (n),A", (0xED, 0x79): "OUT (C),A", (0xED, 0xA3): "OUTI", (0xED, 0xB3): "OTIR",
        (0xED, 0xA2): "INI"}


def walked(name, folder=HERE):
    """name walked from init to done: the T-states at go, half and whole from
    INIT, every port operation (T-state of its instruction's start, port,
    value or None, the instruction), and the VRAM it leaves"""
    wk = walk.Walk(folder / name)
    vf = VramFollow(wk)
    wk.read_port = vf.read
    marks, ops = {}, []
    labels = {wk.sym[k]: k for k in reversed(MARKS)}
    wk.pc, t0 = wk.sym["init"], wk.t
    while True:
        k = labels.get(wk.pc)
        if k and k not in marks:
            marks[k] = wk.t - t0
        if wk.pc == wk.sym["done"] and "whole" in marks:
            break
        n, code = len(wk.ports), wk.code_at(wk.pc)
        wk.step()
        for t, p, v in wk.ports[n:]:
            ops.append((t - t0, p, v, KIND[tuple(code[:1 if code[0] == 0xD3 else 2])]))
        if wk.t - t0 > 4_000_000:
            raise RuntimeError(name)
    vf.follow()
    return marks, ops, bytes(vf.vram)


# ---------------------------------------------------------------- the films
def frames_for(name, machine, marks):
    return math.ceil(marks["whole"] / FT[machine]) + 3


def film(name, machine, frames, folder=HERE):
    """the debugger's log of NAME from INIT"""
    s = sym(name, folder)
    tcl = (F0 + TOO_FAST + PORTS +
           "".join(f'debug set_bp {s[k]} {{}} {{ L "{k} {POS}" }}\n' for k in ("go", "half")) +
           f'set ::whole 0\ndebug set_bp {s["whole"]} {{}} '
           f'{{ if {{!$::whole}} {{ set ::whole 1; L "whole {POS}" }} }}\n')
    lines = msxcap.run_tcl(folder / f"{name}.rom", frames, tcl, machine=machine, tcl_setup=STATE,
                           events={frames - 1: "VR end 0 16384"}, timeout=3000)
    w = [line.split() for line in lines]
    f0 = next(x for x in w if x[0] == "i0")
    fr0, c0 = int(f0[1]), int(f0[2])
    flen = vdpslots.LINES[machine] * LINE

    def t_of(fr, cyc):                  # T-states from INIT
        return Fraction((int(fr) - fr0) * flen + int(cyc) - c0, 6)
    out = {"f0": (fr0, c0), "marks": {}, "ops": [], "fast": [], "end": None}
    for x in w:
        if x[0] in MARKS:
            out["marks"][x[0]] = t_of(x[1], x[2])
            out.setdefault("mark_frames", {})[x[0]] = int(x[1]) - fr0
        elif x[0] in ("o", "i"):
            out["ops"].append((int(x[3]) - fr0, int(x[4]), int(x[1]), None if x[2] == "-" else int(x[2])))
        elif x[0] == "fast":
            out["fast"].append(t_of(x[1], x[2]))
        elif x[0] == "end":
            out["end"] = bytes.fromhex(x[2])
    return out


def played(res, machine):
    """the film's port operations through vdpslots: the VRAM, the reads, the
    lost, and the moment each byte was taken; the cycles from the start of
    the frame of INIT"""
    flen = vdpslots.LINES[machine] * LINE
    evs = [(fr * flen + cyc, port, v) for fr, cyc, port, v in res["ops"]]
    assert evs == sorted(evs, key=lambda e: e[0])
    taken = {}
    vram, reads, lost = vdpslots.play(evs, machine, vram=bytes(16384), regs=[0, 0xE0, 0, 0, 0, 0, 0, 0],
                                      taken=taken)
    return evs, vram, reads, lost, taken


WRITTEN = [(0x0000, 0x1B01), (0x2000, 0x3800)]      # patterns, names, the sprites' end, colours


def same_written(a, b):
    return all(a[x:y] == b[x:y] for x, y in WRITTEN)


def gaps(res, machine, evs):
    """the least T-states between two accesses to $98 while the VDP draws
    the paper with the display on, and for lz the least from a read address
    to its first IN and from a copy's last IN to the write address after it"""
    on, regs, held = [], [0, 0xE0, 0, 0, 0, 0, 0, 0], None
    acc, least, after_read, before_write = None, None, None, None
    last_in, read_set = None, None
    for cyc, port, v in evs:
        if port == 0x99:
            if held is None:
                held = v
                continue
            first, held = held, None
            if v & 0x80:
                regs[v & 7] = first
            elif not v & 0x40:
                read_set = cyc
                acc = cyc                                   # the read ahead: an access
            elif last_in is not None:
                g = cyc - last_in
                before_write = g if before_write is None else min(before_write, g)
                last_in = None
            continue
        held = None
        if v is None:
            if read_set is not None:
                g = cyc - read_set
                after_read = g if after_read is None else min(after_read, g)
                read_set = None
            last_in = cyc
        else:
            last_in = None
        if acc is not None and regs[1] & 0x40 and vdpslots.busy(acc, machine) and vdpslots.busy(cyc, machine):
            g = cyc - acc
            least = g if least is None else min(least, g)
        acc = cyc
    f = (lambda c: None if c is None else num(Fraction(c, 6)))
    return {"least": f(least), "read_to_in": f(after_read), "in_to_write": f(before_write)}


def check_film(name, machine, res, wmarks, wops, wvram):
    """the debugger against walk.py and vdpslots.py"""
    marks = res["marks"]
    assert set(marks) == set(MARKS), (name, machine, marks)
    spans = {"init": marks["go"], "patterns": marks["half"] - marks["go"],
             "colours": marks["whole"] - marks["half"]}
    wspans = {"init": wmarks["go"], "patterns": wmarks["half"] - wmarks["go"],
              "colours": wmarks["whole"] - wmarks["half"]}
    assert spans == wspans, (name, machine, spans, wspans)
    assert [(p, v) for _, _, p, v in res["ops"]] == [(p, v) for _, p, v, _ in wops], (name, machine)
    flen = vdpslots.LINES[machine] * LINE
    fr0, c0 = res["f0"]
    offsets = {}
    for (fr, cyc, _, _), (t, _, _, kind) in zip(res["ops"], wops):
        d = Fraction(fr * flen + cyc - c0, 6) - t
        offsets.setdefault(kind, set()).add(d)
    assert all(len(v) == 1 for v in offsets.values()), (name, machine, offsets)
    evs, vram, reads, lost, taken = played(res, machine)
    assert same_written(vram, res["end"]), (name, machine, "the VRAM played")
    assert len(lost) == len(res["fast"]), (name, machine, len(lost), len(res["fast"]))
    whole = same_written(res["end"], wvram)
    picture = (res["end"][0:6144] == bytes(pic53.PATTERNS) and
               res["end"][0x2000:0x3800] == bytes(pic53.COLOURS))
    damage = None
    if not picture:
        end = res["end"]
        shown = pic53.shown(list(end[0:6144]), list(end[0x2000:0x3800]))
        good = pic53.picture()
        damage = {"patterns": sum(1 for a, b in zip(end[0:6144], pic53.PATTERNS) if a != b),
                  "colours": sum(1 for a, b in zip(end[0x2000:0x3800], pic53.COLOURS) if a != b),
                  "first_row": next(y for y in range(192) if shown[y] != good[y]),
                  "pixels": sum(1 for y in range(192) for x in range(256) if shown[y][x] != good[y][x])}
    return {"spans": {k: num(v) for k, v in spans.items()}, "ops": len(res["ops"]), "damage": damage,
            "reads": sum(1 for _, _, p, v in res["ops"] if p == 0x98 and v is None),
            "offsets": {k: num(v.pop()) for k, v in offsets.items()},
            "fast": len(res["fast"]), "lost": len(lost), "as_walked": whole, "picture": picture,
            "frames": res["mark_frames"], "gaps": gaps(res, machine, evs)}


def pace(marks, ops):
    """from the walk: for each half, the T-states each row of cells took to
    be whole, from the start of the half or the row before: when the last
    byte of its 256 went to the port"""
    addr, held, last = 0, None, {}
    for t, port, v, _ in ops:
        if port == 0x99:
            if held is None:
                held, addr = v, (addr & 0x3F00) | v
            else:
                first, held = held, None
                if not v & 0x80:
                    addr = (v & 0x3F) << 8 | first
                    if not v & 0x40:
                        addr = (addr + 1) & 0x3FFF
            continue
        held = None
        if v is not None and t >= marks["go"] and (addr < 0x1800 or 0x2000 <= addr < 0x3800):
            last[(addr >= 0x2000, addr % 0x2000 // 256)] = t
        addr = (addr + 1) & 0x3FFF
    out = {}
    for colours, half, start in ((False, "patterns", marks["go"]), (True, "colours", marks["half"])):
        ts = [last[(colours, r)] for r in range(24)]
        out[half] = [ts[0] - start] + [ts[r] - ts[r - 1] for r in range(1, 24)]
    return out


CACHE = {}


def films(folder=HERE, names=PROGRAMS):
    out = {}
    for name in names:
        wmarks, wops, wvram = walked(name, folder)
        out[name] = {"walk": {k: num(v) for k, v in wmarks.items()}, "pace": pace(wmarks, wops)}
        for m in MACHINES:
            res = film(name, m, frames_for(name, m, wmarks), folder)
            CACHE[(name, m)] = res
            out[name][TAG[m]] = check_film(name, m, res, wmarks, wops, wvram)
            print("films", name, TAG[m], out[name][TAG[m]], flush=True)
    return out


# ---------------------------------------------------------------- the photos
def taken_writes(res, machine):
    """the film's bytes as the VRAM took them, through vdpslots: data
    [(cycle, address, value)], the registers' changes [(cycle, register,
    value)], the cycles from the start of the frame of INIT"""
    evs, _, _, _, _ = played(res, machine)
    written = []
    vdpslots.play(evs, machine, vram=bytes(16384), regs=[0, 0xE0, 0, 0, 0, 0, 0, 0], written=written)
    regs_, held = [], None
    for c, port, v in evs:
        if port != 0x99 or v is None:
            held = None
        elif held is None:
            held = v
        else:
            if v & 0x80:
                regs_.append((c, v & 7, held))
            held = None
    return written, regs_


def row_start(frame, machine):
    """the cycle at which the VDP starts drawing the paper's first line in
    frame FRAME after INIT's"""
    return (frame * vdpslots.LINES[machine] + vdpslots.PAPER0[machine]) * LINE + vdpslots.BORDER_IN


def render_line(vram, regs, y):
    if regs[1] & 0x40:
        return vdpscreen.graphic2_line(vram, regs, vdpscreen.bases(regs), y)
    return [vdpscreen.colour(0, regs)] * 256


def line_pictures(data, regs_changes, machine, frames):
    """for each frame of FRAMES, the paper line by line: the VRAM and the
    registers as they stand where the VDP starts drawing the line, and, for a
    line during which a byte reached the VRAM, the line after it too (chapter
    40): {frame: (picture, {line: the other picture}, border)}"""
    vram, regs = bytearray(16384), [0] * 8
    j = k = 0
    out = {}
    for n in sorted(frames):
        rows, mixed = [], {}
        for y in range(192):
            ls = row_start(n, machine) + y * LINE
            while j < len(data) and data[j][0] < ls:
                vram[data[j][1]] = data[j][2]
                j += 1
            while k < len(regs_changes) and regs_changes[k][0] < ls:
                regs[regs_changes[k][1]] = regs_changes[k][2]
                k += 1
            rows.append(render_line(vram, regs, y))
            inside = [d for d in data[j:j + 64] if d[0] < ls + LINE]
            if inside:
                after = bytearray(vram)
                for _, a, v in inside:
                    after[a] = v
                mixed[y] = render_line(after, regs, y)
        out[n] = (rows, mixed, regs[7] & 15)
    return out


def full_picture(paper, border):
    out = []
    for y in range(meas.CAPTURE_H):
        row = [None] * meas.CAPTURE_W
        for x in range(meas.DRAWN[0], meas.DRAWN[1] + 1):
            px, py = x - meas.PAPER_X0, y - meas.PAPER_Y0
            row[x] = paper[py][px] if 0 <= px < 256 and 0 <= py < 192 else border
        out.append(row)
    return out


def against(photo, pic, mixed, border):
    """pixels of the capture's drawn part that are neither the model's line
    nor, in a line where a byte reached the VRAM, the line after it"""
    full = full_picture(pic, border)
    bad = 0
    for y in range(meas.CAPTURE_H):
        py = y - meas.PAPER_Y0
        for x in range(meas.DRAWN[0], meas.DRAWN[1] + 1):
            p = photo[y][x]
            if p != full[y][x]:
                px = x - meas.PAPER_X0
                if not (py in mixed and 0 <= px < 256 and p == mixed[py][px]):
                    bad += 1
    return bad


def photo_set(name, machine, res, frames, keep=(), folder=HERE):
    """FRAMES of NAME photographed and held against the line by line model;
    the one offset between the film's frames and the debugger's that fits"""
    data, regs_ = taken_writes(res, machine)
    want = sorted(frames)
    models = line_pictures(data, regs_, machine, want)
    shots = sorted({c + d for c in want for d in (-1, 0, 1)})
    tmp = Path(tempfile.mkdtemp(prefix="ph53_"))
    pngs = msxcap.capture(folder / f"{name}.rom", shots, tmp, f"{name}_{TAG[machine]}_f", machine=machine,
                          timeout=3000)
    ph = {c: codes(pngs[c]) for c in shots}
    fits = [d for d in (-1, 0, 1) if all(against(ph[c + d], *models[c]) == 0 for c in want)]
    assert len(fits) == 1, (name, machine, fits,
                            [(c, d, against(ph[c + d], *models[c])) for c in want for d in (-1, 0, 1)])
    d = fits[0]
    last = [row[meas.DRAWN[0]:meas.DRAWN[1] + 1] for row in ph[want[-1] + d]]
    complete = next(c for c in want if [row[meas.DRAWN[0]:meas.DRAWN[1] + 1] for row in ph[c + d]] == last)
    out = {}
    for c in want:
        dest = (CAPS if c in keep else SHOTS) / pngs[c + d].name.replace(f"_f{c + d:04d}", f"_f{c:04d}")
        dest.parent.mkdir(exist_ok=True)
        shutil.copy(pngs[c + d], dest)
        out[c] = dest.name
    shutil.rmtree(tmp)
    return d, out, {c: len(models[c][1]) for c in want}, complete


FIGURES = {"whole": ("lz", EU), "composing": ("lz", EU), "broken": ("otir", EU)}
COMPOSING = 4                           # figure 53.2: four frames of the unpacking


def composing_frames(fr):
    """figure 53.2's frames: two while the patterns arrive, two while the
    colours do, evenly between go and whole"""
    go, half, whole = fr["go"], fr["half"], fr["whole"]
    return [go + (half - go) // 3, go + 2 * (half - go) // 3,
            half + (whole - half) // 3, half + 2 * (whole - half) // 3]


def photos(cache=CACHE, folder=HERE, names=PROGRAMS):
    """every frame from the one before go to two after whole, of every
    program on both machines, against the line by line model; the figures'
    frames kept in captures/"""
    out = {}
    for name in names:
        for m in MACHINES:
            res = cache.get((name, m))
            if res is None:
                wm, _, _ = walked(name, folder)
                res = cache[(name, m)] = film(name, m, frames_for(name, m, wm), folder)
            fr = res["mark_frames"]
            frames = list(range(fr["go"] - 1, fr["whole"] + 3))
            keep = set()
            if (name, m) == FIGURES["whole"] or (name, m) == FIGURES["broken"]:
                keep.add(fr["whole"] + 2)
            if (name, m) == FIGURES["composing"]:
                keep |= set(composing_frames(fr))
            d, shots, mixed, complete = photo_set(name, m, res, frames, keep=keep, folder=folder)
            out.setdefault(name, {})[TAG[m]] = {"offset": d, "frames": shots, "kept": sorted(keep),
                                               "mixed": mixed, "complete": complete}
            print("photos", name, TAG[m], d, len(shots), sorted(keep), flush=True)
    return out


# ---------------------------------------------------------------- the rooms
ROOM_AT = 0xD000                        # where walk.py puts a packed room
NAMES_AT = 0x1820                       # rows 1 to 23 of the name table


def room_walks():
    """each room, packed three ways, unpacked by the cartridges' own
    routines, walked from the CALL to the return, into rows 1 to 23 of the
    name table; unrlem and unrlec with the write address set before, as
    VRAM_WRITE sets it (40 T-states more)"""
    rs, _ = rooms()
    out = {}
    for name, routine in (("rlem", "unrlem"), ("rlec", "unrlec"), ("lz", "unlz")):
        ts = []
        for r in rs:
            p = pack53.PACKERS[name][0](r)
            wk = walk.Walk(HERE / name)
            vf = VramFollow(wk)
            wk.read_port = vf.read
            wk.mem[ROOM_AT:ROOM_AT + len(p)] = bytes(p)
            vf.addr = NAMES_AT
            ts.append(wk.call(routine, h=ROOM_AT >> 8, l=ROOM_AT & 255, d=NAMES_AT >> 8, e=NAMES_AT & 255))
            vf.follow()
            assert list(vf.vram[NAMES_AT:NAMES_AT + len(r)]) == r, (name, len(ts))
        out[name] = ts
    p45 = json.loads((REPO / "ch45" / "meas45.json").read_text())["prices"]
    out["ch45"] = {"unpack": p45["unpack"], "sends_page": p45["sends_page"]}
    return out


# ---------------------------------------------------------------- the workshop
AT_IN = {"OUT (n),A": 9, "OUT (C),A": 11, "OUTI": 15, "OTIR": 15, "INI": 12}   # films checks these


def answers():
    """the workshop's answers, tried"""
    out = {}
    pat, col = list(pic53.PATTERNS), list(pic53.COLOURS)
    rs, _ = rooms()
    # 1. rlec with runs of two
    def rlec_sizes():
        return {"patterns": len(pack53.rlec(pat)), "colours": len(pack53.rlec(col)),
                "rooms": sum(len(pack53.rlec(r)) for r in rs)}
    three = rlec_sizes()
    old = pack53.RLEC_MIN, pack53.RLEC_MAX
    pack53.RLEC_MIN, pack53.RLEC_MAX = 2, 129
    try:
        two = rlec_sizes()
        assert pack53.unrlec(pack53.rlec(pat)) == pat and all(pack53.unrlec(pack53.rlec(r)) == r for r in rs)
    finally:
        pack53.RLEC_MIN, pack53.RLEC_MAX = old
    out["q1"] = {"three": three, "two": two}
    # 2. copies longer than their distance
    over = lz_variant(col, far=pack53.LZ_FAR, overlap=True)
    out["q2"] = {"bytes": len(over), "without": len(pack53.lz(col)),
                 "wrong": unlz_walked(over), "ram_wrong": unlzr_walked(over)}
    # 3. a distance of two bytes, as far back as the data goes
    out["q3"] = {"patterns": len(lz_variant(pat, far=65535)), "colours": len(lz_variant(col, far=65535)),
                 "rooms": sum(len(lz_variant(r, far=65535)) for r in rs),
                 "rooms_one": len(lz_variant([t for r in rs for t in r], far=65535)),
                 "one_byte": {"patterns": len(pack53.lz(pat)), "colours": len(pack53.lz(col)),
                              "rooms": sum(len(pack53.lz(r)) for r in rs)}}
    # 4. a room unpacked into the name table from the paper's first line
    out["q4"] = {name: ahead(name, routine) for name, routine in (("rlec", "unrlec"), ("lz", "unlz"))}
    return out


def lz_variant(data, far, overlap=False):
    """pack53.lz with copies from up to FAR bytes back (two bytes of
    distance when FAR is over 256), and, if OVERLAP, longer than their
    distance, LDIR's way"""
    out, lit, i = [], [], 0

    def flush():
        while lit:
            part = lit[:pack53.LIT_MAX]
            del lit[:pack53.LIT_MAX]
            out.extend([len(part)] + part)
    seen = {}
    while i < len(data):
        best, dist = 0, 0
        for j in reversed(seen.get(bytes(data[i:i + pack53.LZ_MIN]), [])):
            d = i - j
            if d > far:
                break
            most = min(pack53.LZ_MAX, len(data) - i, pack53.LZ_MAX if overlap else d)
            n = 0
            while n < most and data[j + n] == data[i + n]:
                n += 1
            if n > best:
                best, dist = n, d
                if n == pack53.LZ_MAX:
                    break
        step = best if best >= pack53.LZ_MIN else 1
        for k in range(i, i + step):
            if k + pack53.LZ_MIN <= len(data):
                seen.setdefault(bytes(data[k:k + pack53.LZ_MIN]), []).append(k)
        if best >= pack53.LZ_MIN:
            flush()
            out += [128 + best - pack53.LZ_MIN] + ([dist - 1] if far <= 256 else [dist & 255, dist >> 8])
        else:
            lit.append(data[i])
        i += step
    flush()
    return out + [0]


def ahead(name, routine):
    """each room unpacked by ROUTINE into rows 1 to 23 of the name table,
    called where the VDP starts the paper's first line: for each row, the
    T-states from the moment the row's last name reached the port to the
    moment the VDP starts the row's first line, 8 lines of 228 a row; the
    least, its room and row, and the rows behind"""
    rs, _ = rooms()
    sys.path.insert(0, str(REPO / "ch45"))
    try:
        import gen45
    finally:
        sys.path.remove(str(REPO / "ch45"))
    least, behind = None, 0
    for k, r in enumerate(rs):
        p = pack53.PACKERS[name][0](r)
        wk = walk.Walk(HERE / name)
        vf = VramFollow(wk)
        wk.read_port = vf.read
        wk.mem[ROOM_AT:ROOM_AT + len(p)] = bytes(p)
        vf.addr = NAMES_AT
        wk.r.update(h=ROOM_AT >> 8, l=ROOM_AT & 255, d=NAMES_AT >> 8, e=NAMES_AT & 255)
        t0, last = wk.t, {}
        wk.push(walk.SENTINEL)
        wk.t += 18
        wk.pc = wk.sym[routine]
        while wk.pc != walk.SENTINEL:
            n, code = len(wk.ports), wk.code_at(wk.pc)
            wk.step()
            for t, port, v in wk.ports[n:]:
                if port == 0x98 and v is not None:
                    kind = KIND[tuple(code[:1 if code[0] == 0xD3 else 2])]
                    vf.follow()
                    row = (vf.addr - 1 - 0x1800) // 32
                    last[row] = t - t0 + AT_IN[kind]
        for row, t in last.items():
            m = 8 * row * 228 - t
            behind += m < 0
            if least is None or m < least[0]:
                least = (m, k, row)
    return {"least": least[0], "room": least[1], "room_name": gen45.room_name(least[1]),
            "row": least[2], "behind": behind}


def unlz_walked(packed, at=0x2000):
    """lz.asm's unlz walked on PACKED: the bytes of the VRAM it gets wrong"""
    wk = walk.Walk(HERE / "lz")
    vf = VramFollow(wk)
    wk.read_port = vf.read
    wk.mem[ROOM_AT:ROOM_AT + len(packed)] = bytes(packed)
    wk.call("unlz", h=ROOM_AT >> 8, l=ROOM_AT & 255, d=at >> 8, e=at & 255)
    vf.follow()
    return sum(1 for a, b in zip(vf.vram[at:at + 6144], pic53.COLOURS) if a != b)


def unlzr_walked(packed):
    """lzram.asm's unlzr walked on PACKED: the bytes of the RAM it gets wrong"""
    wk = walk.Walk(HERE / "lzram")
    wk.mem[0xE000:0xE000 + len(packed)] = bytes(packed)
    wk.call("unlzr", h=0xE0, l=0, d=gen53.RAMPIC >> 8, e=gen53.RAMPIC & 255)
    return sum(1 for a, b in zip(wk.mem[gen53.RAMPIC:gen53.RAMPIC + 6144], pic53.COLOURS) if a != b)


# ---------------------------------------------------------------- openMSX's builds
def openmsx():
    """films, photos and answers again with every build: each run in
    versions.rerun() must end within its time limit"""
    if not versions.builds():
        return {"skipped": "OPENMSX_BUILDS not set"}
    out = {}
    for part in OPENMSX_SECTIONS:
        for label, r in versions.every_build(["ch53"], part).items():
            o = out.setdefault(label, {"values": 0, "same_values": 0, "captures": 0,
                                       "same_captures": 0, "same_in_drawn": 0, "failed": [],
                                       "different": []})
            for k in ("values", "same_values", "failed", "different"):
                o[k] += r[k]
            for k in ("captures", "same_captures", "same_in_drawn"):
                o[k] = max(o[k], r[k])
            o["version"], o["sha256"] = r["version"], r["sha256"]
    return out


def films_section():
    out = films()
    for name, per in out.items():
        for tag in ("eu", "jp"):
            for kind, at in per[tag]["offsets"].items():
                assert AT_IN[kind] == at, (name, tag, kind, at)
    return out


OPENMSX_SECTIONS = [["sizes", "films", "photos", "rooms", "answers"]]
SECTIONS = {"sizes": sizes, "films": films_section, "photos": photos, "rooms": room_walks,
            "answers": answers, "openmsx": openmsx}


def main(names=()):
    CAPS.mkdir(exist_ok=True)
    m = json.loads(OUT_JSON.read_text()) if names and OUT_JSON.exists() else {}
    for name in names or SECTIONS:
        print(name, flush=True)
        m[name] = SECTIONS[name]()
        m = {k: m[k] for k in SECTIONS if k in m}
        OUT_JSON.write_text(json.dumps(m, indent=1) + "\n")
    return m


if __name__ == "__main__":
    main(sys.argv[1:])
