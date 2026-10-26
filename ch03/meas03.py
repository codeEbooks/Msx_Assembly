#!/usr/bin/env python3
"""meas03.py -- film the programs of chapter 3, read them back, and check
every number against a model that does not come from the program.

    ./build.sh && python3 meas03.py

The models: the machine definitions in machines/ (where the RAM is, which
slots exist), the ROM files the emulator loads (their sums), openMSX's own
slot map and keyboard map, the openMSX debugger (registers, memory, VRAM and
VDP registers read from outside the program, and the time of any
instruction), and the Zilog timings plus one wait state for every M1 cycle.

Writes captures/*.png and meas03.json, where every number of the chapter
comes from.
"""
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools"))
import msxcap      # noqa: E402
import meas        # noqa: E402
import screentext  # noqa: E402
import gen03       # noqa: E402

CAPS = HERE / "captures"
MACHINES = HERE.parent / "machines"
CLOCK = 3579545.4545454546
EU, JP = "MSXBOOK_EU16", "MSXBOOK_JP16"
T_FRAME = 71364                         # measured on day 1 (tools/meas.py)


def sym(name):
    out = {}
    for line in (HERE / f"{name}.sym").read_text().splitlines():
        lab, _, val = line.partition(": EQU 0x")
        if val:
            out[lab.strip()] = int(val, 16)
    return out


def shot(name, frames, machine=EU, tag=None, events=None, extra=()):
    got = msxcap.capture(HERE / f"{name}.rom", frames, CAPS, f"{tag or name}_f",
                         machine=machine, events=events, extra_args=extra)
    return got


def finished(name, frame, **kw):
    """frames frame - 1 and frame must be the same picture: the page is done"""
    got = shot(name, [frame - 1, frame], **kw)
    a, b = (Image.open(got[n]).convert("RGB") for n in (frame - 1, frame))
    assert a.tobytes() == b.tobytes(), f"{name}: still changing at frame {frame}"
    got[frame - 1].unlink()
    return got[frame]


def sum16(data):
    return sum(data) & 0xFFFF


def tcl_read(addr, n, tag, space="memory"):
    return (f'set s ""; for {{set i 0}} {{$i < {n}}} {{incr i}} '
            f'{{append s " " [debug read {space} [expr {{{addr} + $i}}]]}}; L "{tag}$s"')


def parse(lines, tag):
    for line in lines:
        if line.startswith(tag + " ") or line == tag:
            return [int(v) for v in line[len(tag):].split()]
    raise KeyError(tag)


# ---------------------------------------------------------------- the machine files
def ram_of(machine):
    """(slot, first, last) of every RAM block in a machine definition"""
    root = ET.parse(MACHINES / f"{machine}.xml").getroot()
    out = []
    for prim in root.iter("primary"):
        for ram in prim.iter("RAM"):
            mem = ram.find("mem")
            base, size = int(mem.get("base"), 16), int(mem.get("size"), 16)
            out.append((int(prim.get("slot")), base, base + size - 1))
    return out


def has_secondary(machine):
    root = ET.parse(MACHINES / f"{machine}.xml").getroot()
    return any(True for _ in root.iter("secondary"))


# ---------------------------------------------------------------- 1. memmap
def memmap():
    s = sym("memmap")
    vram = {k: HERE / f"_vram_{k}.bin" for k in ("before", "after")}
    tcl = "\n".join(
        f'debug set_bp {s[lab]} {{}} {{set f [open {{{vram[k]}}} wb]; fconfigure $f -translation binary; '
        f'puts -nonewline $f [debug read_block VRAM 0 0x4000]; close $f; L "{k} [machine_info time]"}}'
        for lab, k in (("test_start", "before"), ("test_end", "after")))
    tcl += '\nL "a8 [debug read ioports 0xA8]"'
    lines = msxcap.run_tcl(HERE / "memmap.rom", 160, tcl)
    a8 = parse(lines, "a8")[0]
    t = {k: float(next(l for l in lines if l.startswith(k + " ")).split()[1]) for k in vram}
    same = vram["before"].read_bytes() == vram["after"].read_bytes()
    for p in vram.values():
        p.unlink()
    # the model: which slot each page shows ($A8), and where that slot has RAM
    rams = ram_of(EU)
    model = []
    for kb in range(64):
        page, lo = kb // 16, kb * 1024
        slot = (a8 >> (2 * page)) & 3
        model.append(sum(1 for a in range(lo, lo + 1024)
                         if any(sl == slot and f <= a <= l for sl, f, l in rams)))
    png = finished("memmap", 160)
    pg = screentext.Page(png)
    C = gen03.MM_COLS
    pages = []
    for p in range(4):
        line = pg.line(gen03.MM_ROW0 + 2 * p)
        boxes = line[C["boxes"]:C["boxes"] + 16]
        kept = int(line[C["kept"]:C["kept"] + 5])
        want = "".join("1" if model[16 * p + k] == 1024 else "0" for k in range(16))
        assert line[C["page"]] == str(p) and line[C["start"]:C["start"] + 5] == f"${p * 0x4000:04X}"
        assert boxes == want and kept == sum(model[16 * p:16 * p + 16]), (p, boxes, kept)
        pages.append({"page": p, "boxes": boxes, "kept": kept})
    total = int(pg.line(gen03.MM_ROW0 + 8)[C["kept"]:C["kept"] + 5])
    assert total == sum(model)
    return {"a8": f"{a8:02X}", "pages": pages, "total": total, "vram_unchanged": same,
            "test_T": round((t["after"] - t["before"]) * CLOCK),
            "test_frames": round((t["after"] - t["before"]) * CLOCK / T_FRAME, 1)}


# ---------------------------------------------------------------- 2. slots
def slotmap(romtype=None):
    """openMSX's own view, from outside the program: the device in every slot
    and page ({(slot, page): name}) and, through the debuggable "slotted
    memory", the 16 KB each page of each slot holds, read without switching
    anything"""
    extra = ("-romtype", romtype) if romtype else ()
    rom = HERE / "slots.rom"
    home = msxcap.make_home()
    log, script = home / "msxcap.log", home / "sm.tcl"
    dump = "\n".join(
        f'set f [open {{{home}/s{s}p{p}.bin}} wb]; fconfigure $f -translation binary; '
        f'puts -nonewline $f [debug read_block {{slotted memory}} {(s * 4) * 0x10000 + p * 0x4000} 0x4000]; close $f'
        for s in range(4) for p in range(4))
    script.write_text(msxcap.tcl_session(
        log, msxcap.rom_init(rom), 1, {}, msxcap.DEFAULT_SPEED, "",
        'foreach l [split [slotmap] "\\n"] {L "SM $l"}\n' + dump, "set ::stopped 1"))
    msxcap.run_openmsx(rom, EU, script, home, 120, extra)
    names, mem, slot = {}, {}, None
    for line in log.read_text().splitlines():
        m = re.match(r"SM slot (\d)", line)
        if m:
            slot = int(m.group(1))
            continue
        m = re.match(r"SM ([0-9A-F]{4}): ?(.*)", line)
        if m:
            names[(slot, int(m.group(1), 16) >> 14)] = m.group(2).strip()
    for s in range(4):
        for p in range(4):
            mem[(s, p)] = (home / f"s{s}p{p}.bin").read_bytes()
    import shutil
    shutil.rmtree(home, ignore_errors=True)
    return names, mem


def slots_read(png):
    pg = screentext.Page(png)
    grid = {}
    for s in range(4):
        r = gen03.SL_ROW0 + 3 * s
        top, low = pg.line(r), pg.line(r + 1)
        assert top[1] == str(s), top
        for p, c in enumerate(gen03.SL_COLS):
            kind = top[c:c + 3].strip()
            if kind == "ROM":
                grid[(s, p)] = ("ROM", low[c:c + 4])
            elif kind == "RAM":
                grid[(s, p)] = ("RAM", int(low[c:c + 5]))
            else:
                assert kind == "-" and low[c:c + 5].strip() == "", (s, p, kind)
                grid[(s, p)] = ("-", None)
    a8 = pg.line(gen03.SL_A8_ROW)
    m = re.match(r"port \$A8: ([0-9A-F]{2}) ([01]{8})", a8)
    assert m and int(m.group(1), 16) == int(m.group(2), 2), a8
    return grid, m.group(1)


def slots():
    main = (msxcap.CBIOS / "cbios_main_msx1_eu.rom").read_bytes()
    logo = (msxcap.CBIOS / "cbios_logo_msx1.rom").read_bytes()
    cart = (HERE / "slots.rom").read_bytes()
    files = {"C-BIOS Main ROM": [main[:0x4000], main[0x4000:]], "C-BIOS Logo ROM": [logo],
             "slots.rom": [cart]}
    out = {}
    for romtype, frame in ((None, 600), ("normal", 600)):
        png = finished("slots", frame, tag="slots" if not romtype else f"slots_{romtype}",
                       extra=("-romtype", romtype) if romtype else ())
        grid, a8 = slots_read(png)
        names, mem = slotmap(romtype)
        seen = {}
        for (s, p), (kind, val) in grid.items():
            dev, data = names[(s, p)], mem[(s, p)]
            assert len(data) == 0x4000
            if dev == "Main RAM":
                assert kind == "RAM" and val == 16384, (s, p, kind, val)
            elif data == b"\xff" * 0x4000:
                assert kind == "-", (s, p, kind)
            else:
                assert kind == "ROM" and val == f"{sum16(data):04X}", (s, p, kind, val)
                # and the same bytes as the file the emulator loaded
                parts = files[dev]
                part = parts[p] if dev == "C-BIOS Main ROM" else parts[0]
                assert data == part, (s, p, dev)
            seen[f"{s}{p}"] = [kind, val, dev]
        out[romtype or "default"] = {"grid": seen, "a8": a8}
    return out


# ---------------------------------------------------------------- 3. sysvars and the switch-on
def sysvars():
    png = finished("sysvars", 30)
    pg = screentext.Page(png)
    s = sym("sysvars")
    tcl = [tcl_read(addr, 2 if kind == "w" else kind, f"M{addr:04X}")
           for _, addr, kind in gen03.SYSVARS]
    tcl.append('L "REG ' + " ".join(f"[reg {r.lower()}]" for r in gen03.REGS) +
               ' [reg i] [reg im] [reg iff] [reg pc]"')
    tcl.append(tcl_read(0, 8, "VDPR", "{VDP regs}"))
    tcl.append('set n 0; while {[debug read memory [expr {0xFD9A + $n}]] == 0xC9} {incr n}; L "HOOKS $n"')
    tcl.append(tcl_read(0x0004, 2, "CGTABL"))
    lines = msxcap.run_tcl(HERE / "sysvars.rom", 2, "\n".join(tcl))
    out = {"vars": {}}
    C = gen03.SV_COLS
    for i, (name, addr, kind) in enumerate(gen03.SYSVARS):
        line = pg.line(gen03.SV_ROW0 + 1 + i)
        assert line[C["name"]:C["name"] + 7].strip() == name and line[C["addr"]:C["addr"] + 4] == f"{addr:04X}"
        shown = line[C["value"]:].split()
        mem = parse(lines, f"M{addr:04X}")
        want = [f"{mem[0] | mem[1] << 8:04X}"] if kind == "w" else [f"{b:02X}" for b in mem]
        assert shown == want, (name, shown, want)
        out["vars"][name] = shown
    regs = parse(lines, "REG")
    at_init = dict(zip([r for r in gen03.REGS] + ["I", "IM", "IFF", "PC"], regs))
    shown = {}
    for k, r in enumerate(gen03.REGS):
        line = pg.line(gen03.SV_REG_ROW + 1 + k // 3)
        col = 10 * (k % 3)
        assert line[col:col + 2] == r, line
        shown[r] = line[col + 3:col + 7]
        assert int(shown[r], 16) == at_init[r], (r, shown[r], at_init[r])
    iline = pg.line(gen03.SV_REG_ROW + 3)
    shown["I"] = iline[23:25]
    assert int(shown["I"], 16) == at_init["I"]
    iff = pg.line(gen03.SV_REG_ROW + 4)
    shown["IFF2"] = int(iff.split(":")[1])
    assert shown["IFF2"] == (at_init["IFF"] >> 1) & 1, (iff, at_init["IFF"])
    out["regs"] = shown
    out["at_init"] = {"IM": at_init["IM"], "IFF": at_init["IFF"], "PC": f"{at_init['PC']:04X}",
                      "init_label": f"{s['init']:04X}"}
    assert at_init["PC"] == s["init"]
    vdpr = parse(lines, "VDPR")
    sav = [int(b, 16) for b in out["vars"]["RG0SAV"] + out["vars"]["RG4SAV"]]
    out["vdp_regs"] = [f"{v:02X}" for v in vdpr]
    out["rgsav_equals_vdp"] = sav == vdpr
    out["hooks_c9_bytes"] = parse(lines, "HOOKS")[0]
    cg = parse(lines, "CGTABL")
    out["cgtabl"] = f"{cg[0] | cg[1] << 8:04X}"
    rams = ram_of(EU)
    out["model"] = {"ram_first": f"{min(f for _, f, _ in rams):04X}", "sys_area": "F380",
                    "secondary_slots": has_secondary(EU)}
    return out


def switch_on():
    out = {}
    tcl = "\n".join([tcl_read(0xFC48, 2, "BOTTOM"), 'L "A8 [debug read ioports 0xA8]"'])
    for machine in ("MSXBOOK_EU8", EU, "MSXBOOK_EU32", "MSXBOOK_EU64", JP):
        lines = msxcap.run_tcl(HERE / "sysvars.rom", 1, tcl, machine=machine)
        f0 = next(l for l in lines if l.startswith("f0 ")).split()
        b = parse(lines, "BOTTOM")
        rams = ram_of(machine)
        out[machine] = {"init_frame": int(f0[1]), "seconds": round(float(f0[3]), 3),
                        "bottom": f"{b[0] | b[1] << 8:04X}", "a8": f"{parse(lines, 'A8')[0]:02X}",
                        "ram": [f"{f:04X}-{l:04X}" for _, f, l in rams]}
    # what the screen shows meanwhile: the film from power-on
    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix="power_"))
    got, init, _ = msxcap.film_power(HERE / "sysvars.rom", range(2, 140), tmp, "p")
    colours = {n: len(Image.open(p).convert("RGB").getcolors(1 << 16)) for n, p in got.items()}
    logo = [n for n, c in colours.items() if c >= 5]
    assert logo == list(range(logo[0], logo[-1] + 1)), "the logo comes and goes"
    out["film"] = {"init_frame": init, "logo_first": logo[0], "logo_last": logo[-1],
                   "logo_frames": len(logo)}
    for p in got.values():
        p.unlink()
    tmp.rmdir()
    return out


def jiffy():
    """the BIOS's frame counter and the time its interrupt routine takes, read
    by the debugger in page0_di.rom (the BIOS takes the interrupts there): from
    the entry at $0038 to the return into the program, just after its HALT"""
    back = sym("page0_di")["main"] + 1
    tcl = (f'debug set_bp 0x0038 {{}} {{ set ::t0 [machine_info time] }}\n'
           f'debug set_bp {back} {{}} {{ if {{[info exists ::t0]}} '
           f'{{ L "isr [expr {{round(([machine_info time] - $::t0) * {CLOCK})}}]"; unset ::t0 }} }}')
    lines = msxcap.run_tcl(HERE / "page0_di.rom", 45, tcl,
                           events={20: tcl_read(0xFC9E, 2, "J20"), 40: tcl_read(0xFC9E, 2, "J40")})
    a, b = parse(lines, "J20"), parse(lines, "J40")
    isr = [int(line.split()[1]) for line in lines if line.startswith("isr ")]
    later = isr[1:]
    common = max(set(later), key=later.count)
    return {"j20": a[0] | a[1] << 8, "j40": b[0] | b[1] << 8,
            "per_20_frames": (b[0] | b[1] << 8) - (a[0] | a[1] << 8),
            "isr_first": isr[0], "isr_frames": len(later), "isr_T": common,
            "isr_same": later.count(common), "isr_pct": round(100 * common / T_FRAME, 2)}


# ---------------------------------------------------------------- 4. timing
ZILOG = {"nop": (4, 1), "inc hl": (6, 1), "ld a,(hl)": (7, 1), "ld a,$55": (7, 1),
         "push hl": (11, 1), "pop hl": (10, 1), "out (c),a": (12, 2), "sla a": (8, 2),
         "ld a,(ix+0)": (19, 2), "bit 0,(ix+0)": (20, 2), "jr $+2": (12, 1)}


def timing():
    s = sym("timing")
    labels = [f"t_{k}" for k, _, _ in gen03.TIMED] + ["t_end", "t_ldir", "t_ldir_end"]
    ram0, ram1 = gen03.RAM_NOPS, gen03.RAM_NOPS + gen03.N_TIMED
    bps = [(lab, s[lab]) for lab in labels] + [("ram_nops", ram0), ("ram_ret", ram1)]
    tcl = "\n".join(f'debug set_bp {a} {{}} {{L "T {lab} [machine_info time] [reg r]"}}' for lab, a in bps)
    lines = msxcap.run_tcl(HERE / "timing.rom", 4, tcl)
    t, rr = {}, {}
    for line in lines:
        if line.startswith("T "):
            _, lab, v, r = line.split()
            t.setdefault(lab, float(v))
            rr.setdefault(lab, int(r))
    rows = []
    for i, (k, ins, nbytes) in enumerate(gen03.TIMED):
        T = round((t[labels[i + 1]] - t[labels[i]]) * CLOCK)
        assert T % gen03.N_TIMED == 0, (ins, T)
        z, m1 = ZILOG[ins]
        # R: the processor adds one to its low seven bits in every M1 cycle
        dr = (rr[labels[i + 1]] - rr[labels[i]]) % 128
        assert dr == (gen03.N_TIMED * m1) % 128, (ins, dr, m1)
        rows.append({"ins": ins, "bytes": nbytes, "zilog": z, "m1": m1, "model": z + m1,
                     "measured": T // gen03.N_TIMED, "r_moved_mod128": dr})
    ldir = round((t["t_ldir_end"] - t["t_ldir"]) * CLOCK)
    ram = round((t["ram_ret"] - t["ram_nops"]) * CLOCK)
    n = gen03.N_TIMED
    out = {"rows": rows, "ldir": {"bytes": n, "T": ldir, "model": (n - 1) * (21 + 2) + 16 + 2,
                                  "zilog": (n - 1) * 21 + 16},
           "ram_nops": {"T": ram, "per": ram / n}}
    assert all(r["measured"] == r["model"] for r in rows), rows
    assert ldir == out["ldir"]["model"] and ram == 5 * n
    out["frame_T"] = T_FRAME
    out["nops_per_frame"] = T_FRAME / 5
    out["nops_per_frame_zilog"] = T_FRAME / 4
    return out


# ---------------------------------------------------------------- 5. nops
def stripes(png):
    im = Image.open(png).convert("RGB")
    out = []
    for y in range(meas.PAPER_Y0 + 192, meas.CAPTURE_H):
        xs = [x for x in range(meas.CAPTURE_W) if sum(im.getpixel((x, y))) > 600]
        if xs:
            assert xs == list(range(xs[0], xs[-1] + 1)), (y, "a broken stripe")
            out.append({"row": y, "x_first": xs[0], "x_last": xs[-1], "length": len(xs)})
    return out


def nops():
    got = shot("nops", range(30, 35))
    frames = {}
    for n, p in got.items():
        rows = stripes(p)
        # group the lines into stripes: consecutive rows, the same pixels
        groups = []
        for r in rows:
            if groups and r["row"] == groups[-1][-1]["row"] + 1:
                groups[-1].append(r)
            else:
                groups.append([r])
        assert len(groups) == len(gen03.NOPS), rows
        st = []
        for g in groups:
            assert len(g) == gen03.STRIPE_LINES and len({(r["x_first"], r["x_last"]) for r in g}) == 1, g
            st.append({"rows": [g[0]["row"], g[-1]["row"]], "x_first": g[0]["x_first"],
                       "x_last": g[0]["x_last"], "length": g[0]["length"]})
        frames[n] = st
        if n != 30:
            p.unlink()
    lengths = [s["length"] for s in frames[30]]
    model = [round((5 * k + 28) * meas.PX_PER_T) for k in gen03.NOPS]
    zilog = [round((4 * k + 24) * meas.PX_PER_T) for k in gen03.NOPS]
    for st in frames.values():
        assert [s["length"] for s in st] == lengths
        assert len({s["x_first"] for s in st}) == 1, "the stripes do not start together"
        assert st == frames[30], "the stripes move from frame to frame"
    assert lengths == model, (lengths, model)
    first = [s["rows"][0] for s in frames[30]]
    assert all(b - a == gen03.STRIPE_EVERY for a, b in zip(first, first[1:])), first
    return {"frame30": frames[30], "lengths": lengths, "model": model, "zilog": zilog,
            "x_first_by_frame": {n: st[0]["x_first"] for n, st in frames.items()},
            "rows": [s["rows"] for s in frames[30]]}


# ---------------------------------------------------------------- 5b. the VDP's ports
def vdp():
    png = finished("vdp", 30)
    pg = screentext.Page(png)
    at = gen03.VDP_AT
    addrs = [(at + k) & 0x3FFF for k in range(len(gen03.VDP_BYTES))]
    lines = msxcap.run_tcl(HERE / "vdp.rom", 30, "", events={29: "; ".join(
        f'L "V{a:04X} [debug read VRAM {a}]"' for a in addrs)})
    vram = [parse(lines, f"V{a:04X}")[0] for a in addrs]
    assert vram == list(gen03.VDP_BYTES), vram
    wrote = pg.line(gen03.VD_ROW0).split(":")[1].split()
    read = pg.line(gen03.VD_ROW0 + 2).split(":")[1].split()
    st = pg.line(gen03.VD_ROW0 + 4).split(":")[1].split()
    reg = pg.line(gen03.VD_ROW0 + 6).split(":")[-1].split()
    want = [f"{v:02X}" for v in gen03.VDP_BYTES]
    assert wrote == want and read == want, (wrote, read)
    s1, s2, s3 = (int(v, 16) for v in st + reg)
    assert s1 & 0x80 and not s2 & 0x80 and s1 & 0x7F == s2 & 0x7F and s3 != 0xF4
    return {"addresses": [f"{a:04X}" for a in addrs], "bytes": want, "read": read,
            "status": [f"{s1:02X}", f"{s2:02X}"], "after_reg": f"{s3:02X}"}


# the AY-3-8910 data sheet: the bits each register has (R14 and R15 are ports)
AY_BITS = {0: 8, 1: 4, 2: 8, 3: 4, 4: 8, 5: 4, 6: 5, 7: 8, 8: 5, 9: 5, 10: 5,
           11: 8, 12: 8, 13: 4, 14: 8, 15: 8}


def psg_read(png):
    pg = screentext.Page(png)
    out = []
    for row in (gen03.PS_ROW0, gen03.PS_ROW0 + 6):
        vals = pg.line(row + 1).split() + pg.line(row + 3).split()
        assert len(vals) == 16
        out.append(vals)
    return out


def psg():
    out = {}
    for machine, tag in ((EU, "psg"), ("MSXBOOK_EU16AY", "psg_ay")):
        before, after = psg_read(finished("psg", 30, machine=machine, tag=tag))
        lines = msxcap.run_tcl(HERE / "psg.rom", 1, tcl_read(0, 16, "PSG", "{PSG regs}"), machine=machine)
        regs = parse(lines, "PSG")
        assert [f"{v:02X}" for v in regs] == before, (before, regs)
        out[machine] = {"before": before, "after": after}
    ym, ay = out[EU]["after"], out["MSXBOOK_EU16AY"]["after"]
    for r in range(16):
        if r in (7, 14):
            continue
        assert ym[r] == "FF", (r, ym[r])
        if r != 15:
            assert int(ay[r], 16) == (1 << AY_BITS[r]) - 1, (r, ay[r])
    out["ay_bits"] = AY_BITS
    out["r7_written"] = f"{gen03.PSG_TEST_R7:02X}"
    return out


# ---------------------------------------------------------------- 6. keys and ports
def keys_read(png, machine=EU):
    pg = screentext.Page(png, machine)
    rows = []
    C = gen03.KY_COLS
    for r in range(gen03.KEY_ROWS):
        line = pg.line(gen03.KY_ROW0 + r)
        bits, hx = line[C["bits"]:C["bits"] + 8], line[C["hex"]:C["hex"] + 2]
        assert int(line[C["row"]:C["row"] + 2], 16) == r and int(bits, 2) == int(hx, 16), line
        rows.append(hx)
    ports = {}
    for k, name in enumerate(("R14", "AA", "A8")):
        line = pg.line(gen03.KY_PORT_ROW + 2 * k)
        bits, hx = line[C["bits"]:C["bits"] + 8], line[C["bits"] + 9:C["bits"] + 11]
        assert int(bits, 2) == int(hx, 16), line
        ports[name] = hx
    return rows, ports


def keys():
    fr, row, mask = gen03.KEY_EVENT
    got = shot("keys", [fr - 10, fr + 10], events={fr: f"keymatrixdown {row} 0x{mask:02X}"})
    idle, ports = keys_read(got[fr - 10])
    held, ports2 = keys_read(got[fr + 10])
    assert idle == ["FF"] * gen03.KEY_ROWS and ports == ports2
    changed = [(r, v) for r, v in enumerate(held) if v != "FF"]
    assert changed == [(row, f"{0xFF ^ mask:02X}")], changed
    # the model: openMSX's own keyboard map, asked to type the letter q
    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix="typeq_"))
    films = msxcap.capture(HERE / "keys.rom", range(fr, fr + 12), tmp, "q", events={fr: "type q"})
    typed = set()
    for p in films.values():
        rows, _ = keys_read(p)
        typed |= {(r, v) for r, v in enumerate(rows) if v != "FF"}
        p.unlink()
    tmp.rmdir()
    assert typed == {(row, f"{0xFF ^ mask:02X}")}, typed
    # the same program on the Japanese machine
    jp = shot("keys", [fr - 10], machine=JP, tag="keys_jp")
    _, ports_jp = keys_read(jp[fr - 10], JP)
    return {"idle": idle, "held": held, "held_row": row, "held_bit": mask.bit_length() - 1,
            "ports": ports, "ports_jp": ports_jp, "type_q": sorted(typed)}


# ---------------------------------------------------------------- 7. page 0, interrupts off and on
def page0():
    out = {}
    for name in ("page0_di", "page0_ei"):
        s = sym(name)
        tcl = "\n".join([f'debug set_bp {s["look"]} {{}} {{L "look [machine_info time]"}}',
                         f'debug set_bp {s["looked"]} {{}} {{L "looked [machine_info time]"}}'])
        events = {100: "; ".join([
            'L "R [reg pc] [reg sp] [reg iff]"',
            'set f [open {%s} wb]; fconfigure $f -translation binary; '
            'puts -nonewline $f [debug read_block memory 0xC000 0x4000]; close $f'
            % (HERE / f"_{name}_ram.bin")])}
        lines = msxcap.run_tcl(HERE / f"{name}.rom", 101, tcl, events=events)
        pc, sp, iff = parse(lines, "R")
        ram = (HERE / f"_{name}_ram.bin").read_bytes()
        (HERE / f"_{name}_ram.bin").unlink()
        t = {k: float(l.split()[1]) for l in lines for k in ("look", "looked") if l.startswith(k + " ")}
        png = shot(name, [100])[100]
        pg = screentext.Page(png)
        counted = int(pg.line(3)[15:20])
        sumline = pg.line(5)
        r = {"pc": f"{pc:04X}", "sp": f"{sp:04X}", "iff": iff, "counted": counted,
             "sum": sumline[20:24] if sumline.startswith("page 0") else None,
             "look_reached_end": "looked" in t}
        if "looked" in t:
            T = round((t["looked"] - t["look"]) * CLOCK)
            r["look_T"], r["look_frames"] = T, round(T / T_FRAME, 2)
        # the RAM: how much of it is the pattern 39 00 that RST $38 leaves
        pairs = sum(1 for i in range(0, len(ram) - 1, 2)
                    if (ram[i], ram[i + 1]) in ((0x39, 0x00), (0x00, 0x39)))
        r["ram_pattern_bytes"] = 2 * pairs
        r["ram_all_pattern"] = all(b in (0x00, 0x39) for b in ram) and \
            all(ram[i] != ram[i + 1] for i in range(len(ram) - 1))
        out[name] = r
    di, ei = out["page0_di"], out["page0_ei"]
    assert di["sum"] == "C000" and ei["sum"] is None and ei["counted"] == gen03.PAGE0_AT
    assert ei["pc"] in ("0038", "0039") and ei["ram_all_pattern"]
    assert abs(100 - di["counted"] - di["look_frames"]) < 3, di
    return out


def main():
    CAPS.mkdir(exist_ok=True)
    m = {"memmap": memmap(), "slots": slots(), "sysvars": sysvars(), "switch_on": switch_on(),
         "jiffy": jiffy(), "timing": timing(), "nops": nops(), "vdp": vdp(), "psg": psg(),
         "keys": keys(), "page0": page0()}
    (HERE / "meas03.json").write_text(json.dumps(m, indent=1) + "\n")
    return m


if __name__ == "__main__":
    print(json.dumps(main(), indent=1))
