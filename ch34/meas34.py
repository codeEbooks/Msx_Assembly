#!/usr/bin/env python3
"""meas34.py -- the keyboard, measured.

    python3 gen34.py && ./build.sh && python3 meas34.py
                                  python3 meas34.py matrix define     only these

Every program is given its keys by its events file (NAME.events, written by
gen34.py), and the debugger reads what the program read, every frame. The
model of the keyboard is the events themselves: a key is held from the frame
its keymatrixdown runs to the frame of its keymatrixup, a row reads 0 where
its keys are held, and on a machine with ghosting every row that shares a
held column with another reads the other's keys too. The photographs are
vdpscreen.py's drawing of what the program wrote, to the pixel.

  matrix     matrix.rom on both machines and on MSXBOOK_EU16G: all 88 keys
             one at a time, three combinations, rows 11 to 15 (figure 34.2)
  legend     legend.rom: the BIOS's character for each key of rows 0 to 5,
             against C-BIOS's own tables (figure 34.1)
  snsmat     snsmat.rom: row 8 from the ports, from SNSMAT and from NEWKEY,
             every frame, for taps of one to three frames and a long hold
             (figure 34.3)
  define     define.rom: the five keys chosen, one refused, and the figure
             moved, against a model of the program (figure 34.4)
  rowonly    WHERE IT BREAKS: rowonly.rom against matrix.rom: port C, the
             CAPS lamp and a tape in the cassette player
  layouts    data: openMSX's keyboard maps and machine files, C-BIOS's tables,
             and what openMSX does when a machine file says nothing
  prices     walk.py's T-states, against a model of the PPI
  replay     define's keys as an openMSX replay: the same run
  answers    the workshop, tried (for Appendix I)
  openmsx    all of it again with every other build (tools/versions.py)
"""
import json
import os
import re
import shutil
import sys
import tempfile
import wave
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
import gen34       # noqa: E402
sys.path.remove(str(HERE))
sys.path.insert(0, str(HERE))      # gen34 put chapters 26 and 30 first: this folder's files win
for mod in ("vdpscreen", "walk"):
    sys.modules.pop(mod, None)
import vdpscreen   # noqa: E402
import walk        # noqa: E402  (chapter 32's)

assert Path(vdpscreen.__file__).parent == HERE and Path(walk.__file__).parent == HERE

CAPS = HERE / "captures"
EU, JP, EUG = gen34.EU, gen34.JP, gen34.EUG
TAG = {EU: "eu", JP: "jp", EUG: "eug"}
FT = gen34.FRAME_T
POS = "[expr {[machine_info VDP_frame_count] - $::f0}] [machine_info VDP_cycle_in_frame]"
F0 = 'L "f0 [machine_info VDP_frame_count]"\n'
TOO_FAST = ('proc ::toofast_cb {args} { L "fast [machine_info VDP_frame_count]" }\n'
            'set VDP.too_fast_vram_access_callback ::toofast_cb\n')
OPENMSX_SHARE = Path(os.environ.get("OPENMSX_SYSTEM_DATA", "/usr/share/openmsx"))

PALETTE = [tuple(c) for c in json.loads((REPO / "ch01" / "meas01.json").read_text())["palette"]["rgb"]]
CODE = {rgb: n for n, rgb in enumerate(PALETTE) if n}


def rom(name):
    return HERE / f"{name}.rom"


def sym(name):
    return dbg.sym(HERE / f"{name}.sym")


def events(name):
    """NAME.events: {frame: Tcl}, the frame counted from INIT"""
    ev = {}
    for line in (HERE / f"{name}.events").read_text().splitlines():
        line = line.split("#")[0].strip()
        if line:
            n, cmd = line.split(None, 1)
            ev[int(n)] = (ev[int(n)] + "; " + cmd) if int(n) in ev else cmd
    return ev


def run(name, frames, tcl, machine, ev=None, setup=""):
    lines = msxcap.run_tcl(rom(name), frames, F0 + TOO_FAST + tcl, machine=machine,
                           events=events(name) if ev is None else ev, tcl_setup=setup)
    w = [l.split() for l in lines]
    assert not [x for x in w if x[0] == "fast"], (name, machine, "an access too soon")
    return w


def codes(png):
    im = Image.open(png).convert("RGB")
    px = im.load()
    return [[CODE.get(px[x, y]) for x in range(im.width)] for y in range(im.height)]


def mismatch(model, photo):
    return sum(1 for y in range(meas.CAPTURE_H) for x in range(meas.DRAWN[0], meas.DRAWN[1] + 1)
               if model[y][x] != photo[y][x])


def capture_of(paper, border=15):
    """the capture of a paper of 192 x 256 codes, in a border of one colour"""
    return [[(paper[y - meas.PAPER_Y0][x - meas.PAPER_X0]
              if 0 <= x - meas.PAPER_X0 < 256 and 0 <= y - meas.PAPER_Y0 < 192 else border)
             if meas.DRAWN[0] <= x <= meas.DRAWN[1] else None
             for x in range(meas.CAPTURE_W)] for y in range(meas.CAPTURE_H)]


def bytes_of(hexes):
    return list(bytes.fromhex(hexes))


# ---------------------------------------------------------------- the keyboard
def held_keys(ev, frame):
    """the keys (row, bit) the events hold down in FRAME"""
    held = set()
    for f in sorted(ev):
        if f > frame:
            break
        for cmd in ev[f].split(";"):
            w = cmd.split()
            if not w or w[0] not in ("keymatrixdown", "keymatrixup"):
                continue
            row, mask = int(w[1]), int(w[2], 16)
            for b in range(8):
                if mask >> b & 1:
                    (held.add if w[0] == "keymatrixdown" else held.discard)((row, b))
    return held


def matrix_of(held, ghosting=False, rows=16):
    """the bytes the rows read: a 0 for each key held; with ghosting, rows
    that share a held column are joined, as the wires of a keyboard without
    diodes join them, and every row of a group reads the keys of all"""
    m = [0xFF] * rows
    for r, b in held:
        if r < gen34.ROWS:
            m[r] &= ~(1 << b) & 0xFF
    if ghosting:
        group = list(range(rows))

        def find(r):
            while group[r] != r:
                r = group[r]
            return r
        for a in range(rows):
            for c in range(a + 1, rows):
                if (m[a] | m[c]) != 0xFF:          # a column held in both
                    group[find(a)] = find(c)
        joined = {}
        for r in range(rows):
            joined[find(r)] = joined.get(find(r), 0xFF) & m[r]
        m = [joined[find(r)] for r in range(rows)]
    return m


# ---------------------------------------------------------------- screens
def own_vram(names, sprites=b"\xD0"):
    v = bytearray(16384)
    v[0:1024] = bytes(gen34.own_shapes())
    v[0x2000:0x2020] = bytes([0x1F]) * 32
    v[0x1800:0x1B00] = bytes(names)
    v[0x1B00:0x1B00 + len(sprites)] = sprites
    v[0x3800:0x3820] = bytes(gen34.FIGURE)
    return v


def hex2(v):
    return f"{v:02X}"


def matrix_screen(rows, portc):
    names = gen34.matrix_names()
    for r in range(gen34.ALL):
        at = 32 * (gen34.TOP + r)
        for b in range(8):
            names[at + gen34.BOX_COL + 7 - b] = gen34.BOX_FULL if not rows[r] >> b & 1 else gen34.BOX_EMPTY
        names[at + gen34.HEX_COL:at + gen34.HEX_COL + 2] = [ord(c) for c in hex2(rows[r])]
    at = 32 * gen34.PORT_ROW
    for b in range(8):
        names[at + gen34.BOX_COL + 7 - b] = gen34.BOX_FULL if portc >> b & 1 else gen34.BOX_EMPTY
    names[at + gen34.HEX_COL:at + gen34.HEX_COL + 2] = [ord(c) for c in hex2(portc)]
    return capture_of(vdpscreen.draw(own_vram(names), gen34.TEXT_REGS))


# ---------------------------------------------------------------- matrix
def scans(name, machine, frames, ev=None, extra=""):
    """the rows the program read in each frame: {film frame: 16 bytes}"""
    s = sym(name)
    tcl = (f'debug set_bp {s["scanned"]} {{}} {{ binary scan [debug read_block memory {s["rows"]} 16] H* h; '
           f'L "rows {POS} $h [debug read memory {s["portc"]}]" }}\n') + extra
    w = run(name, frames, tcl, machine, ev)
    return {int(x[1]): (bytes_of(x[3]), int(x[4])) for x in w if x[0] == "rows"}, w


def offset_of(read, ev, ghosting, label):
    """the frame of the events each frame's reading answers to: one offset for all"""
    fits = [d for d in (-1, 0, 1)
            if all(rows == matrix_of(held_keys(ev, f + d), ghosting) for f, (rows, _) in read.items())]
    assert len(fits) == 1, (label, fits)
    return fits[0]


def matrix_photos(name, machine, read, ev, shots, ghosting=False, portc=0x5F):
    """the photographs of SHOTS against the screen drawn from the rows read
    E frames before, one E for all"""
    pngs = msxcap.capture(rom(name), shots, CAPS, f"{name}_{TAG[machine]}_f", machine=machine, events=ev)
    ph = {f: codes(pngs[f]) for f in shots}
    fits = []
    for e in (-2, -1, 0):
        if all(f + e in read and mismatch(matrix_screen(read[f + e][0], portc), ph[f]) == 0 for f in shots):
            fits.append(e)
    assert len(fits) == 1, (name, machine, fits)
    return fits[0], len(shots)


def matrix():
    ev = events("matrix")
    out = {}
    singles = [gen34.MATRIX_FROM + gen34.MATRIX_EVERY * k for k in range(8 * gen34.ROWS)]
    combos = [f + k for f, n, _ in gen34.COMBOS for k in (1, 2, n)]   # the first and the last tell the lag
    for m in (EU, JP, EUG):
        ghosting = m == EUG
        read, _ = scans("matrix", m, gen34.MATRIX_FRAMES, ev)
        d = offset_of(read, ev, ghosting, ("matrix", m))
        # every key alone: its own row and bit, and nothing else
        alone = 0
        for k, f in enumerate(singles):
            r, b = k // 8, k % 8
            for g in (f, f + 1):
                rows = read[g - d][0]
                assert rows == [0xFF if i != r else 0xFF & ~(1 << b) for i in range(16)], (m, k, rows)
            alone += 1
        assert all(rows[11:] == [0xFF] * 5 for rows, _ in read.values())
        assert {pc for f, (_, pc) in read.items() if f > min(read)} == {0x5F}
        combo = {"+".join(names): [hex2(v) for v in read[f + 1 - d][0][:11]]
                 for f, _, names in gen34.COMBOS}
        shots = {EU: [f + 2 for f in singles] + combos + [10],
                 JP: [f + 2 for f in singles[::8]] + combos + [10],
                 EUG: combos + [10]}[m]
        e, n = matrix_photos("matrix", m, read, ev, sorted(shots), ghosting)
        out[TAG[m]] = {"offset": d, "keys_alone": alone, "frames_read": len(read),
                       "rows_11_15": "FF", "portc": hex2(0x5F), "combos": combo,
                       "photo_lag": e, "photos": n}
    # the ghost: three keys held, and on MSXBOOK_EU16G a fourth read
    f, _, names = gen34.COMBOS[-1]
    held = held_keys(ev, f + 1)
    plain, ghost = matrix_of(held), matrix_of(held, True)
    extra = [(r, b) for r in range(11) for b in range(8) if not ghost[r] >> b & 1 and plain[r] >> b & 1]
    out["ghost"] = {"held": names, "extra": [gen34.NAMES[8 * r + b] for r, b in extra],
                    "extra_at": extra}
    assert out["ghost"]["extra"] == ["Z"]
    return out


# ---------------------------------------------------------------- legend
# C-BIOS 0.29a's tables of the characters of rows 0 to 5, no SHIFT, bit 0
# first: src/scancodes_us.asm (the European machine), scancodes_jp.asm, and
# for the other countries C-BIOS can be built for, scancodes_uk, _fr, _de.
# 0 is a dead key. $5C is the backslash in the European set and the yen in
# the Japanese one; $85, $82, $8A, $87, $97, $BF, $E1, $81, $94, $84 and $9C
# are letters of the MSX character set (a grave, e acute ...)
CBIOS_TABLES = {
    "us": [b"01234567", b"89-=\\[];", b"'`,./\x00ab", b"cdefghij", b"klmnopqr", b"stuvwxyz"],
    "jp": [b"01234567", b"89-^\\@[;", b":],./_ab", b"cdefghij", b"klmnopqr", b"stuvwxyz"],
    "uk": [b"01234567", b"89-=\\[];", b"'\x9c,./\x00ab", b"cdefghij", b"klmnopqr", b"stuvwxyz"],
    "fr": [b"\x85&\x82\"'(\xbf\x8a", b"!\x87)-<\x00$m", b"\x97#;:=\x00qb", b"cdefghij", b"kl,nopar",
           b"stuvzxyw"],
    "de": [b"01234567", b"89\xe1\x00<\x81+\x94", b"\x84#,.-\x00ab", b"cdefghij", b"klmnopqr", b"stuvwxzy"],
}
TABLE_OF = {EU: "us", JP: "jp"}


def legend_screen(machine, typed):
    shapes, _ = screentext.font(machine)
    v = bytearray(16384)
    v[0:2048] = bytes(b for s in shapes for b in s)
    for k in (gen34.BOX_EMPTY, gen34.BOX_FULL):
        v[8 * k:8 * k + 8] = bytes(gen34.BOX_SHAPES[k])
    v[0x2000:0x2020] = bytes([0x1F]) * 32
    names = gen34.page(gen34.legend_texts())
    for (r, b), ch in typed.items():
        row, col = gen34.leg_cell(r, b)
        names[32 * row + col] = ch
    v[0x1800:0x1B00] = bytes(names)
    v[0x1B00] = 0xD0
    return capture_of(vdpscreen.draw(v, gen34.TEXT_REGS))


def legend():
    ev = events("legend")
    s = sym("legend")
    out = {}
    for m in (EU, JP):
        rom_bytes = (msxcap.CBIOS / screentext.bios_file(m)).read_bytes()
        table = CBIOS_TABLES[TABLE_OF[m]]
        at = rom_bytes.find(b"".join(table))
        assert at > 0, (m, "C-BIOS's table is not in its ROM")
        tcl = (f'debug set_bp {s["got"]} {{}} {{ L "got {POS} [reg a] [debug read memory {s["cell"]}] '
               f'[debug read memory {s["cell"] + 1}]" }}\n'
               'L "id [debug read memory 0x2B] [debug read memory 0x2C]"\n')
        w = run("legend", gen34.LEGEND_FRAMES, tcl, m, ev)
        got = [(irq_frame(int(x[1]), int(x[2]), m), int(x[3]), int(x[4]) | int(x[5]) << 8)
               for x in w if x[0] == "got"]
        ident = next(x for x in w if x[0] == "id")
        typed, late = {}, []
        k = 0
        for r in range(gen34.LEG_ROWS):
            for b in range(8):
                ch = table[r][b]
                f = gen34.LEGEND_FROM + gen34.LEGEND_EVERY * (8 * r + b)
                if ch == 0:
                    continue                    # a dead key: nothing typed
                frame, a, cell = got[k]
                row, col = gen34.leg_cell(r, b)
                assert (a, cell) == (ch, 0x1800 + 32 * row + col), (m, r, b, a, cell)
                typed[(r, b)] = ch
                late.append(frame - f)
                k += 1
        assert k == len(got)
        shot = gen34.LEGEND_FRAMES - 2
        pngs = msxcap.capture(rom("legend"), [shot], CAPS, f"legend_{TAG[m]}_f", machine=m, events=ev)
        assert mismatch(legend_screen(m, typed), codes(pngs[shot])) == 0, m
        out[TAG[m]] = {"typed": len(typed), "dead": 48 - len(typed), "late": sorted(set(late)),
                       "table_in_rom": hex(at), "id_2b": int(ident[1]), "id_2c": int(ident[2]),
                       "shot": shot}
    # the keys whose characters differ between the two machines
    diff = [(r, b) for r in range(gen34.LEG_ROWS) for b in range(8)
            if CBIOS_TABLES["us"][r][b] != CBIOS_TABLES["jp"][r][b]]
    out["differ"] = [[r, b, chr(CBIOS_TABLES["us"][r][b]) if CBIOS_TABLES["us"][r][b] else "",
                      chr(CBIOS_TABLES["jp"][r][b])] for r, b in diff]
    out["differ_count"] = len(diff)
    # define.asm names those keys by their place
    assert all(gen34.NAMES[8 * r + b].startswith("(") for r, b in diff)
    return out


# ---------------------------------------------------------------- snsmat
SNSMAT_CBIOS = [("CALL SNSMAT", 18), ("JP snsmat, at $0141", 11), ("DI", 5), ("PUSH BC", 12),
                ("LD C,A", 5), ("IN A,($AA)", 12), ("AND $F0", 8), ("OR C", 5), ("OUT ($AA),A", 12),
                ("IN A,($A9)", 12), ("POP BC", 11), ("EI", 5), ("RET", 11)]


SIGNAL_LINE = {EU: 261, JP: 234, EUG: 261}     # F rises on this line (chapter 19)


def irq_frame(frame, cycle, machine):
    """the frame whose interrupt a reading after HALT follows: the reading's
    own, or the one before when the BIOS's routine ran past the frame's end"""
    return frame - (1 if cycle < SIGNAL_LINE[machine] * 228 * 6 else 0)


SNSMAT_SHOTS = [151, 152, 153, 154, 246]


def snsmat_screen(values):
    names = gen34.page(gen34.snsmat_texts())
    for (row, _), val in zip(gen34.SNS_LINES, values):
        for b in range(8):
            names[32 * row + gen34.SNS_BOX + 7 - b] = gen34.BOX_FULL if not val >> b & 1 else gen34.BOX_EMPTY
        names[32 * row + gen34.SNS_HEX:32 * row + gen34.SNS_HEX + 2] = [ord(c) for c in hex2(val)]
    return capture_of(vdpscreen.draw(own_vram(names), gen34.TEXT_REGS))


def snsmat_photos(machine, ev, values):
    """SNSMAT_SHOTS against the three readings that followed the interrupt
    of the frame E before, one E for all"""
    pngs = msxcap.capture(rom("snsmat"), SNSMAT_SHOTS, CAPS, f"snsmat_{TAG[machine]}_f",
                          machine=machine, events=ev)
    ph = {f: codes(pngs[f]) for f in SNSMAT_SHOTS}
    fits = [e for e in (0, 1, 2) if all(f - e in values and
                                        mismatch(snsmat_screen(values[f - e]), ph[f]) == 0
                                        for f in SNSMAT_SHOTS)]
    assert len(fits) == 1, (machine, fits)
    return fits[0]


def snsmat():
    ev = events("snsmat")
    s = sym("snsmat")
    out = {}
    space = gen34.key("SPACE")
    for m in (EU, JP):
        tcl = (f'debug set_bp {s["stored"]} {{}} {{ L "v {POS} [debug read memory {s["byport"]}] '
               f'[debug read memory {s["bybios"]}] [debug read memory {s["bycopy"]}] '
               f'[debug read memory {s["iff"]}] [debug read memory 0xF3F6]" }}\n'
               f'debug set_bp {s["row8"]} {{}} {{ L "t row8 {POS}" }}\n'
               f'debug set_bp {s["bios"]} {{}} {{ L "t bios {POS}" }}\n'
               f'debug set_bp {s["sbios"]} {{}} {{ L "t sbios {POS}" }}\n'
               'L "jp [debug read memory 0x141] [debug read memory 0x142] [debug read memory 0x143]"\n')
        w = run("snsmat", gen34.SNSMAT_FRAMES, tcl, m, ev)
        # one reading after each interrupt: (the reading's frame, the interrupt's)
        v = [(int(x[1]), irq_frame(int(x[1]), int(x[2]), m), *[int(y) for y in x[3:]])
             for x in w if x[0] == "v"]
        v = [r for r in v if r[1] >= 1]
        assert [r[1] for r in v] == list(range(v[0][1], v[0][1] + len(v)))     # none missed
        rows = [x for x in w if x[0] == "t"]
        jp = [int(y) for y in next(x for x in w if x[0] == "jp")[1:]]
        assert jp[0] == 0xC3
        times = {}
        for x in rows:
            times.setdefault((int(x[2]), int(x[3]) < 1000 * 6), {})[x[1]] = int(x[3])
        costs = {(c["bios"] - c["row8"], c["sbios"] - c["bios"]) for c in times.values() if len(c) == 3}
        assert len(costs) == 1, costs
        ports_t, bios_t = (x // 6 for x in costs.pop())
        assert bios_t == 8 + sum(p for _, p in SNSMAT_CBIOS)
        # the ports and SNSMAT: the events of the reading's frame; the
        # interrupts on after SNSMAT, every time
        d = [dd for dd in (-1, 0, 1)
             if all(p == matrix_of(held_keys(ev, f + dd))[8] for f, _, p, *_ in v)]
        assert len(d) == 1, (m, d)
        assert all(p == b for _, _, p, b, *_ in v)
        assert all(i == 4 for *_, i, _ in v)
        # NEWKEY: row 8 as the keys were in the frame of the last interrupt
        # that read the keyboard: SCNCNT goes 3, 2, 1 and the read sets 3 again
        scans = [r[1] for k, r in enumerate(v) if k and r[6] == 3 and v[k - 1][6] == 1]
        steps = {b - a for a, b in zip(scans, scans[1:])}
        assert steps == {3}, steps
        copy = None
        for f, g, p, b, c, i, scn in v:
            if g in scans:
                copy = matrix_of(held_keys(ev, g + d[0]))[8]
            if copy is not None:
                assert c == copy, (m, f, g, c, copy)
        # how long the interrupt kept the program: from F to the first
        # instruction after HALT, in the frames that read the keyboard and not
        late = {}
        for x in [x for x in rows if x[1] == "row8"][1:]:    # the first: F up since INIT
            f, cyc = int(x[2]), int(x[3])
            g = irq_frame(f, cyc, m)
            t = (f - g) * FT[m] + cyc / 6 - (SIGNAL_LINE[m] * 228 + 101 / 3)
            late.setdefault(g in scans, []).append(t)
        # the taps, as each reading saw them
        taps = []
        for start, n in gen34.TAPS:
            seen = {k: [g + d[0] for f, g, *r in v if start <= g + d[0] < start + n + 4
                        and not r[k] & space[1]] for k in (0, 2)}
            taps.append({"start": start, "held": n, "ports": seen[0], "newkey": seen[2],
                         "late": (seen[2][0] - start) if seen[2] else None})
        lag = snsmat_photos(m, ev, {g: r[0:3] for f, g, *r in v})
        out[TAG[m]] = {"offset": d[0], "ports_t": ports_t, "snsmat_t": bios_t, "jp_0141": jp,
                       "photo_lag": lag, "photos": len(SNSMAT_SHOTS),
                       "first_scan": scans[0], "scan_every": 3, "readings": len(v), "scans": len(scans),
                       "after_next_frame": sum(1 for f, g, *_ in v if f != g),
                       "irq_t": {"keyboard": [round(min(late[True])), round(max(late[True]))],
                                 "other": [round(min(late[False])), round(max(late[False]))]},
                       "taps": taps}
    out["cbios_price"] = SNSMAT_CBIOS
    return out


# ---------------------------------------------------------------- define
def define_model(ev, first):
    """the program's run, frame by frame, from the frame of its first HALT:
    the keys chosen and refused, the frames they were taken in, and the
    figure after the logic of each frame of the game"""
    def keys(f):
        return held_keys(ev, f)
    f = first
    chosen, refused, taken = [], [], []
    while len(chosen) < len(gen34.ACTIONS):
        while keys(f):                      # every key up
            f += 1
        f += 1
        while not keys(f):                  # then one down
            f += 1
        rows = matrix_of(keys(f), rows=gen34.ROWS)
        r = next(i for i, v in enumerate(rows) if v != 0xFF)
        b = next(i for i in range(8) if not rows[r] >> i & 1)
        if (r, b) in chosen:
            refused.append((f, gen34.NAMES[8 * r + b]))
        else:
            chosen.append((r, b))
            taken.append(f)
        f += 1
    x, y = gen34.START
    colour = gen34.COLOUR
    play = {}
    for g in range(f, gen34.DEFINE_FRAMES + 3):
        held = keys(g)
        play[g] = (y, x, colour)            # as the logic finds it
        act = [k in held for k in chosen]
        y = (y - act[0] + act[1]) & 0xFF
        x = (x - act[2] + act[3]) & 0xFF
        colour = gen34.FIRE_COLOUR if act[4] else gen34.COLOUR
    return {"chosen": chosen, "names": [gen34.NAMES[8 * r + b] for r, b in chosen],
            "taken": taken, "refused": refused, "play": play}


def define_screen(model, frame, spr):
    """the VRAM at the end of FRAME's lines not drawn: the names taken in it
    and before, the mark at the action asked for, and the figure from the
    attributes SPR (Y, X, colour)"""
    texts = gen34.define_texts()
    done = [t for t in model["taken"] if t <= frame]
    for k in range(len(done)):
        texts.append((gen34.ACT_TOP + gen34.ACT_STEP * k, gen34.NAME_COL,
                      model["names"][k].ljust(gen34.NAME_LEN)))
    if len(done) < len(gen34.ACTIONS):
        texts.append((gen34.ACT_TOP + gen34.ACT_STEP * len(done), gen34.MARK_COL, ">"))
    names = gen34.page(texts)
    sprites = bytes([spr[0], spr[1], 0, spr[2], 0xD0]) if spr else b"\xD0"
    return capture_of(vdpscreen.draw(own_vram(names, sprites), gen34.SPRITE_REGS))


DEFINE_SHOTS = [20, 36, 46, 56, 76, 86, 120, 150, 170, 185, 200, 218]


def define():
    ev = events("define")
    s = sym("define")
    out = {}
    for m in (EU, JP):
        tcl = (f'debug set_bp {s["again"]} {{}} {{ L "again {POS}" }}\n'
               f'debug set_bp {s["taken"]} {{}} {{ L "taken {POS} [debug read memory {s["index"]}]" }}\n'
               f'debug set_bp {s["logic"]} {{}} {{ binary scan [debug read_block memory {s["spr"]} 4] H* h; '
               f'L "logic {POS} $h" }}\n'
               f'debug set_bp {s["frame"]} {{}} {{ if {{![info exists ::fr]}} {{ set ::fr 1; '
               f'L "first {POS}" }} }}\n')
        w = run("define", gen34.DEFINE_FRAMES, tcl, m, ev)
        first = int(next(x for x in w if x[0] == "first")[1])
        taken = [(int(x[1]), int(x[3])) for x in w if x[0] == "taken"]
        logic = {int(x[1]): bytes_of(x[3]) for x in w if x[0] == "logic"}
        agains = [int(x[1]) for x in w if x[0] == "again"]
        # the model from the frame of the first HALT: the keys taken, in the
        # frames the debugger found, and the figure before every frame's logic
        mo = define_model(ev, first)
        assert [t for t, _ in taken] == mo["taken"], (m, taken, mo["taken"])
        assert [i for _, i in taken] == [8 * r + b for r, b in mo["chosen"]]
        assert all(tuple(logic[g][k] for k in (0, 1, 3)) == mo["play"][g] for g in logic), m
        assert len(agains) == len(gen34.ACTIONS) + len(mo["refused"])
        # the photographs: the screen after the frames before, to the pixel
        pngs = msxcap.capture(rom("define"), DEFINE_SHOTS, CAPS, f"define_{TAG[m]}_f", machine=m, events=ev)
        lags = []
        for e in (0, 1, 2):                     # photo f: the VRAM as frame f - e left it
            ok = True
            for f in DEFINE_SHOTS:
                h = f - e                       # the attributes sent in frame h: logic h's
                spr = tuple(logic[h][k] for k in (0, 1, 3)) if h in logic else None
                if mismatch(define_screen(mo, h, spr), codes(pngs[f])) != 0:
                    ok = False
                    break
            if ok:
                lags.append(e)
        assert len(lags) == 1, (m, lags)
        play = sorted(logic)
        out[TAG[m]] = {"first": first, "names": mo["names"], "taken": mo["taken"],
                       "refused": mo["refused"], "frames_played": len(play),
                       "end": list(mo["play"][play[-1]]), "photos": len(DEFINE_SHOTS), "lag": lags[0]}
    return out


# ---------------------------------------------------------------- rowonly
def blank_tape(path, seconds=30):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(1)
        w.setframerate(22050)
        w.writeframes(bytes([128]) * 22050 * seconds)


def rowonly():
    tmp = Path(tempfile.mkdtemp(prefix="tape34_"))
    tape = tmp / "blank.wav"
    blank_tape(tape)
    out = {}
    try:
        for name in ("matrix", "rowonly"):
            s = sym(name)
            ev = events("rowonly")
            out_at = s["scan.row"] + 1
            extra = (f'cassetteplayer insert {{{tape}}}\n'
                     f'trace add variable ::led_caps write {{apply {{{{a b c}} {{L "caps $::led_caps {POS}"}}}}}}\n'
                     'proc tape {} { L "tape [expr {[machine_info VDP_frame_count] - $::f0}] '
                     '[cassetteplayer getpos]"; after frame tape }\nafter frame tape\n'
                     f'debug set_bp {out_at} {{}} {{ if {{[incr ::outs] <= 16}} {{ L "out [reg a]" }} }}\n')
            read, w = scans(name, EU, gen34.ROWONLY_FRAMES, ev, extra)
            d = offset_of(read, ev, False, name)
            outs = [int(x[1]) for x in w if x[0] == "out"]
            caps = [(x[1], int(x[2])) for x in w if x[0] == "caps"]
            tape_pos = {int(x[1]): float(x[2]) for x in w if x[0] == "tape"}
            moving = sorted(f for f in tape_pos if f - 1 in tape_pos and tape_pos[f] > tape_pos[f - 1])
            out[name] = {"offset": d, "outs": [hex2(o) for o in outs], "caps": caps,
                         "tape_end": round(tape_pos[max(tape_pos)], 4),
                         "tape_from": moving[0] if moving else None,
                         "portc": hex2(read[max(read)][1])}
            if name == "rowonly":
                per = [tape_pos[f] - tape_pos[f - 1] for f in moving[1:]]
                out[name]["tape_per_frame"] = [round(min(per), 5), round(max(per), 5)]
                e, _ = matrix_photos(name, EU, read, ev, [21, 25, 30], portc=0x0F)
                out[name]["photo_lag"] = e
        assert out["matrix"]["outs"] == [hex2(0x50 + r) for r in range(16)]
        assert out["rowonly"]["outs"] == [hex2(r) for r in range(16)]
        assert out["matrix"]["caps"] == [] and out["matrix"]["tape_end"] == 0.0
        assert out["rowonly"]["caps"] and out["rowonly"]["caps"][0][0] == "on"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return out


# ---------------------------------------------------------------- layouts
MSX_MAPS_OUT = ("cvjoy", "sega_int", "sega_jp", "svi")      # not MSX keyboards


def keymap(path):
    """a keyboard map of openMSX: {character: (row, column, modifiers)}"""
    m = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.split("#")[0].strip()
        if not line or line.startswith(("MSX", "DEADKEY")):
            continue
        p = [x.strip() for x in line.split(",")]
        try:
            u = int(p[0], 16)
            int(p[1], 16)
        except ValueError:
            continue                    # "--": a character the keyboard has no key for
        m.setdefault(chr(u), (int(p[1][0], 16), int(p[1][1]), p[2] if len(p) > 2 else ""))
    return m


def layouts():
    out = {}
    maps = OPENMSX_SHARE / "unicodemaps"
    base = keymap(maps / "unicodemap.int")
    named = {"\x1b": "ESC", "\t": "TAB", "\x08": "BS", "\r": "RETURN", " ": "SPACE", "\x0b": "HOME",
             "\x12": "INS", "\x7f": "DEL", "\x1d": "LEFT", "\x1e": "UP", "\x1f": "DOWN", "\x1c": "RIGHT",
             "\x18": "SELECT"}
    moved, fixed, same_named = {}, {}, {}
    for f in sorted(maps.glob("unicodemap.*")):
        kind = f.name.split(".", 1)[1]
        if kind in MSX_MAPS_OUT:
            continue
        m = keymap(f)
        moved[kind] = "".join(c for c in "abcdefghijklmnopqrstuvwxyz"
                              if m.get(c, (None, None))[:2] != base[c][:2])
        fixed[kind] = all(m.get(chr(c), (None, None))[:2] == base[chr(c)][:2]
                          for c in (0x1C, 0x1D, 0x1E, 0x1F, 0x20))
        same_named[kind] = all(m.get(ch, (None, None))[:2] == base[ch][:2] for ch in named)
    out["maps"] = len(moved)
    out["moved"] = {k: v for k, v in moved.items() if v}
    out["arrows_space_fixed"] = sum(fixed.values())
    assert all(fixed.values())
    out["named_fixed"] = sum(same_named.values())
    out["groups"] = {}
    for kind, letters in moved.items():
        out["groups"].setdefault(letters, []).append(kind)
    # where the international map puts the named keys of rows 7 and 8: as NAMES
    for ch, name in named.items():
        r, c, _ = base[ch]
        assert gen34.NAMES[8 * r + c] == name, (name, r, c)
    out["named_checked"] = len(named)
    # the machines: ghosting off, and SHIFT, GRAPH and CODE protected
    xmls = sorted((OPENMSX_SHARE / "machines").glob("*.xml"))
    ppi = [x for x in xmls if "<PPI" in x.read_text(errors="replace")]
    off = [x.stem for x in ppi if re.search(r"<key_ghosting>\s*false", x.read_text(errors="replace"))]
    on = [x for x in ppi if x.stem not in off]
    sgc = {v: sum(1 for x in on if re.search(rf"<key_ghosting_sgc_protected>\s*{v}", x.read_text(errors="replace")))
           for v in ("true", "false")}
    sgc["unsaid"] = len(on) - sgc["true"] - sgc["false"]
    out["machines"] = {"files": len(xmls), "with_ppi": len(ppi), "ghosting_off": off,
                       "ghosting_on": len(on), "sgc": sgc}
    # what openMSX does when the file says nothing: the ghost of matrix.rom's
    # last combination, and SHIFT's, on two machines made for the test
    out["defaults"] = defaults()
    return out


SGC_TEST = {30: "keymatrixdown 6 0x02; keymatrixdown 3 0x02; keymatrixdown 6 0x01",   # CTRL, D, SHIFT
            36: "keymatrixup 6 0x03; keymatrixup 3 0x02"}


def defaults():
    """MSXBOOK_EU16 with no key_ghosting line, and with key_ghosting true and
    no key_ghosting_sgc_protected line: is there a ghost, and is SHIFT's
    column passed to row 3?"""
    tmp = Path(tempfile.mkdtemp(prefix="machines34_"))
    keep = msxcap.MACHINES
    try:
        for x in (REPO / "machines").glob("*.xml"):
            shutil.copy(x, tmp / x.name)
        base = (REPO / "machines" / "MSXBOOK_EU16.xml").read_text()
        line = "      <key_ghosting>false</key_ghosting>\n"
        assert base.count(line) == 1
        (tmp / "TEST_GHOST.xml").write_text(base.replace(line, ""))
        (tmp / "TEST_SGC.xml").write_text(base.replace(line, "      <key_ghosting>true</key_ghosting>\n"))
        msxcap.MACHINES = tmp
        ev = events("matrix")
        f = gen34.COMBOS[-1][0] + 1
        read, _ = scans("matrix", "TEST_GHOST", f + 2, {k: v for k, v in ev.items() if k <= f})
        ghost = read[f][0] == matrix_of(held_keys(ev, f), True)
        read, _ = scans("matrix", "TEST_SGC", 40, SGC_TEST)
        held = held_keys(SGC_TEST, 32)
        shift = read[32][0][3] == matrix_of(held, True)[3]       # row 3 reads SHIFT's column too
        return {"ghosting_unsaid": "on" if ghost else "off",
                "sgc_unsaid": "not protected" if shift else "protected",
                "row3_with_ctrl_d_shift": hex2(read[32][0][3])}
    finally:
        msxcap.MACHINES = keep
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------- prices
def ppi_walker(name, keys=()):
    """walk.py with a model of the PPI: port C keeps what is written to it,
    port B gives the row port C selects, a 0 for each key of KEYS"""
    mtx = matrix_of(set(keys))
    box = {}

    def read_port(port, t):
        wk = box["wk"]
        c = next((v for _, p, v in reversed(wk.ports) if p == 0xAA and v is not None), 0x50)
        if port == 0xAA:
            return c
        if port == 0xA9:
            return mtx[c & 15]
        return 0x80 if port == 0x99 else 0
    wk = walk.Walk(HERE / name, read_port=read_port)
    box["wk"] = wk
    return wk


def prices():
    out = {}
    held = {gen34.key("Q"), gen34.key("SPACE")}
    for n in (gen34.ROWS, gen34.ALL):
        wk = ppi_walker("matrix", [(r, b.bit_length() - 1) for r, b in held])
        wk.mem[0x2B] = 0x80
        t = wk.call("scan", b=n, h=wk.sym["rows"] >> 8, l=wk.sym["rows"] & 0xFF) - 18
        got = list(wk.mem[wk.sym["rows"]:wk.sym["rows"] + n])
        assert got == matrix_of({(r, b.bit_length() - 1) for r, b in held})[:n], got
        assert t == 25 + 63 * n - 5 + 11, (n, t)
        out[f"scan_{n}"] = t
    out["scan_row"] = 63
    wk = ppi_walker("snsmat")
    out["row8_ports"] = wk.run("row8", "bios")
    assert out["row8_ports"] == 12 + 8 + 8 + 12 + 12 + 14
    wk = ppi_walker("define")
    wk.mem[wk.sym["rows"]:wk.sym["rows"] + 11] = bytes([0xFF] * 11)
    wk.mem[wk.sym["keys"]:wk.sym["keys"] + 2] = bytes([8, 1])
    out["held"] = wk.call("held", h=wk.sym["keys"] >> 8, l=wk.sym["keys"] & 0xFF) - 18
    wk = ppi_walker("define")
    out["anykey"] = wk.call("anykey") - 18
    out["anykey_scan"] = out["anykey"] - out["scan_11"] - 18
    wk = ppi_walker("matrix")
    wk.mem[wk.sym["rows"]:wk.sym["rows"] + 16] = bytes([0xFF] * 16)
    out["draw"] = wk.call("draw") - 18          # nothing held
    t = [t for t, port, _ in wk.ports if port == 0x98]
    out["draw_gap"] = min(b - a for a, b in zip(t, t[1:]))     # the closest two writes to the VRAM
    return out


# ---------------------------------------------------------------- replay
def replay():
    """define's keys recorded as an openMSX replay (reverse start at power-on,
    reverse savereplay at the end) and played back: the same keys taken in
    the same frames, the same figure in every frame of the game"""
    out = {}
    s = sym("define")
    tcl = (f'debug set_bp {s["taken"]} {{}} {{ L "taken {POS} [debug read memory {s["index"]}]" }}\n'
           f'debug set_bp {s["logic"]} {{}} {{ binary scan [debug read_block memory {s["spr"]} 4] H* h; '
           f'L "logic {POS} $h" }}\n')
    omr = HERE / "define.omr"
    ev = events("define")
    last = gen34.DEFINE_FRAMES - 1
    ev2 = dict(ev)
    ev2[last] = (ev2.get(last, "") + f"; reverse savereplay {{{omr}}}").lstrip("; ")
    a = [x for x in run("define", gen34.DEFINE_FRAMES, tcl, EU, ev2, setup="reverse start")
         if x[0] in ("taken", "logic")]
    # openMSX writes the cartridge's full path into the replay; the published
    # file names it as define.rom, beside it, as on any reader's machine (the
    # replay plays the same with either, tried before the repository was made
    # public, 26 October 2026)
    import gzip
    xml = gzip.decompress(omr.read_bytes()).decode("utf-8")
    full = str((HERE / "define.rom").resolve())
    assert full in xml
    omr.write_bytes(gzip.compress(xml.replace(full, "define.rom").encode("utf-8"), mtime=0))
    b = [x for x in run("define", gen34.DEFINE_FRAMES, tcl, EU, {},
                        setup=f"reverse loadreplay {{{omr}}}") if x[0] in ("taken", "logic")]
    assert a == b and len(a) > 100
    out["define"] = {"lines": len(a), "same": a == b, "file": omr.name}
    return out


# ---------------------------------------------------------------- answers
def answers():
    m = json.loads((HERE / "meas34.json").read_text())
    pr, sn = m["prices"], m["snsmat"]
    out = {}
    out["q1"] = {"scan_11": pr["scan_11"], "eu": round(100 * pr["scan_11"] / FT[EU], 2),
                 "jp": round(100 * pr["scan_11"] / FT[JP], 2)}
    out["q2"] = {"ports": sn["eu"]["ports_t"] - 14, "snsmat": sn["eu"]["snsmat_t"] - 8}
    fr = CBIOS_TABLES["fr"]
    out["q3"] = {k: chr(fr[r][b.bit_length() - 1]) for k in ("Q", "A", "O", "P")
                 for r, b in [gen34.key(k)]}
    # with RIGHT and SPACE held, every other key alone: the keys read as well
    base = {gen34.key("RIGHT"), gen34.key("SPACE")}
    base = {(r, b.bit_length() - 1) for r, b in base}
    q4 = {}
    for r in range(gen34.ROWS):
        for b in range(8):
            if r == 8:
                continue
            mx = matrix_of(base | {(r, b)}, True)
            plain = matrix_of(base | {(r, b)})
            extra = [gen34.NAMES[8 * rr + bb] for rr in range(gen34.ROWS) for bb in range(8)
                     if not mx[rr] >> bb & 1 and plain[rr] >> bb & 1]
            if extra:
                q4[gen34.NAMES[8 * r + b]] = extra
    out["q4"] = q4
    taps = sn["eu"]["taps"]
    out["q5"] = {n: sum(1 for t in taps if t["held"] == n and not t["newkey"])
                 for n in (1, 2, 3)}
    left = FT[JP] - (SIGNAL_LINE[JP] * 228 + 101 / 3)
    out["q6"] = {"left_jp": round(left), "left_eu": round(FT[EU] - (SIGNAL_LINE[EU] * 228 + 101 / 3)),
                 "keyboard": sn["jp"]["irq_t"]["keyboard"], "late_readings": sn["jp"]["after_next_frame"]}
    # two keys at once for one action: choose takes the first row, the lowest bit
    both = matrix_of({(4, 6), (2, 6)}, rows=gen34.ROWS)
    r = next(i for i, v in enumerate(both) if v != 0xFF)
    out["q7"] = gen34.NAMES[8 * r + next(i for i in range(8) if not both[r] >> i & 1)]
    # Q, A, O, P and SPACE on the machine that ghosts: the threes that make a
    # fourth key read, and whether it is one of the five
    five = {n: (r, b.bit_length() - 1) for n in ("Q", "A", "O", "P", "SPACE") for r, b in [gen34.key(n)]}
    names = list(five)
    q8 = []
    for i in range(5):
        for j in range(i + 1, 5):
            for k in range(j + 1, 5):
                held = {five[names[i]], five[names[j]], five[names[k]]}
                mx, plain = matrix_of(held, True), matrix_of(held)
                extra = [gen34.NAMES[8 * rr + bb] for rr in range(gen34.ROWS) for bb in range(8)
                         if not mx[rr] >> bb & 1 and plain[rr] >> bb & 1]
                if extra:
                    q8.append({"held": [names[i], names[j], names[k]], "extra": extra})
    out["q8"] = q8
    out["q9"] = m["rowonly"]["rowonly"]["portc"]
    out["q10"] = {"eu": m["legend"]["eu"]["id_2c"], "should": 0x11}
    d = m["define"]["eu"]
    out["q11"] = {"refused_at": d["refused"][0][0], "taken": d["taken"][1]}
    return out


OPENMSX_SECTIONS = ["matrix", "legend", "snsmat", "define", "rowonly"]


def openmsx():
    if not versions.builds():
        return {"skipped": "OPENMSX_BUILDS not set"}
    return versions.every_build(["ch34"], OPENMSX_SECTIONS)


SECTIONS = {"matrix": matrix, "legend": legend, "snsmat": snsmat, "define": define, "rowonly": rowonly,
            "layouts": layouts, "prices": prices, "replay": replay, "answers": answers,
            "openmsx": openmsx}


def main(names=()):
    CAPS.mkdir(exist_ok=True)
    path = HERE / "meas34.json"
    m = json.loads(path.read_text()) if names and path.exists() else {}
    for name in names or SECTIONS:
        print(name, flush=True)
        m[name] = SECTIONS[name]()
        m = {k: m[k] for k in SECTIONS if k in m}
        path.write_text(json.dumps(m, indent=1) + "\n")
    return m


if __name__ == "__main__":
    main(sys.argv[1:])
