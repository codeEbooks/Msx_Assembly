#!/usr/bin/env python3
"""measF.py -- the BIOS of Appendix F, measured on C-BIOS 0.29a.

    python3 genF.py && ./build.sh && python3 measF.py [step ...]

    calls    calls.rom on both machines, the debugger logging as it happens
             everything but the reads of memory and the writes below $F380:
             each of the 27 entry points of bios.inc called once, seven of
             them again with the interrupts on, and for each call the
             registers before and after, the T-states from the CALL to the
             instruction after it, the frame interrupts that fell inside and
             their time, every port it wrote and read, the bytes it sent to
             the VRAM, the VDP registers it set, the system variables it
             wrote, the hooks it went through; the frame interrupt over the
             whole run; the keys of the last part held from frame KEY_FRAME
             (SPACE and RIGHT, row 8)
    jump     the entry points from $0000 to $0159, read from C-BIOS's page 0:
             a JP at each, where it goes, which go to C-BIOS's stub that only
             reports its name; the data bytes among them
    vars     the variables and hooks of bios.inc: the value of each at INIT on
             both machines, and who writes it: which calls, and the frame
             interrupt
    uses     which chapters' programs use each name of bios.inc
    documents  what C-BIOS changed against what the MSX Red Book says each
             call changes, and the interrupts it leaves on or off; the work
             area at INIT against the first values of the Red Book and of
             the MSX2 Technical Handbook
    before   the numbers against chapters 16, 17, 19, 21, 34 and 38
    openmsx  the steps again with every other build (tools/versions.py)

Every number is C-BIOS's. What a real MSX's BIOS does differently comes from
its documents, in DOCUMENTED and DOC_INIT below, and is compared, not
measured.

Writes measF.json.
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(HERE))
import msxcap      # noqa: E402
import probe       # noqa: E402
import versions    # noqa: E402
import genF        # noqa: E402

OUT_JSON = HERE / "measF.json"
CLOCK = probe.CLOCK
EU, JP = "MSXBOOK_EU16", "MSXBOOK_JP16"
MACHINES = (EU, JP)
TAG = {EU: "eu", JP: "jp"}
KEY_FRAME = 140                 # SPACE and RIGHT pressed, frames after INIT
FRAMES = 180
SYSVARS, SYSVARS_N = 0xF380, 0x10000 - 0xF380
REGS = ["af", "bc", "de", "hl", "ix", "iy", "af2", "bc2", "de2", "hl2", "sp", "iff", "im"]
HOOKS = range(0xFD9A, 0xFFCA, 5)
CASES = genF.CASES + genF.ON + genF.KEYED


def rom():
    return HERE / "calls.rom"


def sym():
    return probe.sym(HERE / "calls.sym")


def inc_names():
    """{name: value} of bios.inc, in its order"""
    out = {}
    for l in (HERE / "bios.inc").read_text().splitlines():
        m = re.match(r"(\w+)\s+EQU\s+\$([0-9A-F]+)", l)
        if m:
            out[m.group(1)] = int(m.group(2), 16)
    return out


# ---------------------------------------------------------------- calls
# Everything is logged the moment it happens, in order: E lines carry the
# case the program is in ("-" between calls) and whether the frame
# interrupt's routine is running (from $0038 to the return to the address it
# left, at the same stack depth)
TCL = r"""
set ::win "-"
set ::isr 0
set ::n98 0
set ::r98 0
proc E {s} { L "E $::win $::isr $s" }
proc regs {} {
    set s ""
    foreach r {af bc de hl ix iy af2 bc2 de2 hl2 sp iff im} { append s " " [reg $r] }
    return $s
}
proc state {} {
    set s "[binary encode hex [debug read_block VRAM 0 0x4000]]"
    append s " [binary encode hex [debug read_block memory @SYS@ @SYSN@]] [peek @WRSLT@]"
    for {set i 0} {$i < 8} {incr i} { append s " " [debug read {VDP regs} $i] }
    return $s
}
debug probe set_bp z80.acceptIRQ {} { set ::acc [machine_info time] }
debug set_bp 0x0038 {} {
    set ::isr 1
    set ::isp [reg sp]
    E "I $::acc [format %04X [peek16 [reg sp]]]"
    set ::rbp [debug set_bp [peek16 [reg sp]] {[reg sp] == $::isp + 2} {
        E "R [machine_info time]"
        set ::isr 0
        debug remove_bp $::rbp
    }]
}
debug set_watchpoint write_io {0x00 0xFF} {} {
    set p [expr {$::wp_last_address & 0xFF}]
    if {$p == 0x98} { incr ::n98 } else { E "o [format %02X $p] $::wp_last_value" }
}
debug set_watchpoint read_io {0x00 0xFF} {} {
    set p [expr {$::wp_last_address & 0xFF}]
    if {$p == 0x98} { incr ::r98 } else { E "i [format %02X $p]" }
}
debug set_watchpoint write_mem {@SYS@ 0xFFFF} {} {
    E "m [format %04X $::wp_last_address] $::wp_last_value"
}
L "INIT [machine_info time] [machine_info VDP_frame_count][regs] [state]"
"""


def tcl():
    s = sym()
    t = (TCL.replace("@SYS@", f"0x{SYSVARS:04X}").replace("@SYSN@", str(SYSVARS_N))
         .replace("@WRSLT@", f"0x{genF.WRSLT_AT:04X}"))
    for a in HOOKS:
        t += f'debug set_bp 0x{a:04X} {{}} {{ E "h {a:04X}" }}\n'
    for label, *_ in CASES:
        t += (f'debug set_bp 0x{s["b_" + label]:04X} {{}} {{ set ::win {label}; set ::n98 0; set ::r98 0; '
              f'L "B {label} [machine_info time] [machine_info VDP_frame_count][regs] [state]" }}\n'
              f'debug set_bp 0x{s["a_" + label]:04X} {{}} {{ '
              f'L "A {label} [machine_info time] [machine_info VDP_frame_count][regs] $::n98 $::r98 [state]"; '
              f'set ::win "-" }}\n')
    for label in ("keys", "settle", "done"):
        t += (f'set ::n_{label} 0\n'
              f'debug set_bp 0x{s[label]:04X} {{}} {{ incr ::n_{label}; if {{$::n_{label} == 1}} '
              f'{{ L "P {label} [machine_info time] [machine_info VDP_frame_count]" }} }}\n')
    return t


def run(machine):
    """the log of one run of calls.rom, split into its lines' words"""
    lines = msxcap.run_tcl(rom(), FRAMES, tcl(), machine=machine,
                           events={KEY_FRAME: "keymatrixdown 8 0x81"})
    return [l.split() for l in lines]


def state(words):
    """(VRAM, system variables, the byte at WRSLT_AT, VDP registers 0-7)"""
    vram, sysv, e0, *vdp = words
    return bytes.fromhex(vram), bytes.fromhex(sysv), int(e0), [int(v) for v in vdp]


HALVES = [("af", "A", "F"), ("bc", "B", "C"), ("de", "D", "E"), ("hl", "H", "L")]


def changed_regs(rb, ra):
    """the registers a call changed, named as the documents name them: a
    pair when both its halves changed, else the half; the other set the same
    way, with a prime"""
    out = []
    for p in ("", "2"):
        for pair, hi, lo in HALVES:
            x, y = rb[pair + p], ra[pair + p]
            h, l = (x >> 8) != (y >> 8), (x & 0xFF) != (y & 0xFF)
            q = "'" if p else ""
            out += [pair.upper() + q] if h and l else [hi + q] if h else [lo + q] if l else []
        if not p:
            out += [r.upper() for r in ("ix", "iy") if rb[r] != ra[r]]
    return out


def span(addrs):
    """how many bytes of a sorted list of addresses, the first, the last"""
    return {"bytes": len(addrs), "first": addrs[0], "last": addrs[-1]} if addrs else {"bytes": 0}


def vdp_writes(values):
    """the bytes a call wrote to port $99, in pairs: register writes and
    the VRAM addresses set"""
    assert len(values) % 2 == 0, values
    out = []
    for lo, hi in zip(values[::2], values[1::2]):
        if hi & 0x80:
            assert hi & 0x78 == 0, values          # a register 0 to 7, as C-BIOS writes them
            out.append(["R", hi & 0x07, lo])
        else:
            out.append(["W" if hi & 0x40 else "R_addr", (hi & 0x3F) << 8 | lo])
    return out


def parse(lines):
    """{case: everything about it}, the events outside the cases, and the
    log's other lines"""
    s_init = next(w for w in lines if w[0] == "INIT")
    out, events = {}, {"-": []}
    begin = {}
    for w in lines:
        if w[0] == "B":
            begin[w[1]] = w
            events[w[1]] = []
        elif w[0] == "E":
            events.setdefault(w[1], []).append((int(w[2]), w[3:]))
        elif w[0] == "A":
            b, label = begin[w[1]], w[1]
            rb = dict(zip(REGS, map(int, b[4:4 + len(REGS)])))
            ra = dict(zip(REGS, map(int, w[4:4 + len(REGS)])))
            n98, r98 = int(w[4 + len(REGS)]), int(w[5 + len(REGS)])
            vb, sb, eb, gb = state(b[4 + len(REGS):])
            va, sa, ea, ga = state(w[6 + len(REGS):])
            ev = events[label]
            own = [x for isr, x in ev if not isr]
            isr = [x for i, x in ev if i]
            # the interrupts inside: their time, from the Z80 taking each to its return
            starts = [float(x[1]) for x in isr if x[0] == "I"]
            ends = [float(x[1]) for x in isr if x[0] == "R"]
            assert len(starts) == len(ends), label
            in_isr = sum(e - s for s, e in zip(starts, ends))
            t = round((float(w[2]) - float(b[2])) * CLOCK)
            writes = {}
            for x in own:
                if x[0] == "o":
                    writes.setdefault(x[1], []).append(int(x[2]))
            reads = {}
            for x in own:
                if x[0] == "i":
                    reads[x[1]] = reads.get(x[1], 0) + 1
            mem = {}
            for x in own:
                if x[0] == "m":
                    mem.setdefault(int(x[1], 16), []).append(int(x[2]))
            out[label] = {
                "t": t, "t_less_isr": round(t - in_isr * CLOCK), "interrupts": len(starts),
                "isr_t": [round((e - s) * CLOCK) for s, e in zip(starts, ends)],
                "isr_at": [x[2] for x in isr if x[0] == "I"],
                "before": rb, "after": ra, "changed": changed_regs(rb, ra),
                "vram_writes": n98, "vram_reads": r98,
                "vdp": vdp_writes(writes.pop("99", [])),
                "vdp_regs": [[r, gb[r], ga[r]] for r in range(8) if gb[r] != ga[r]],
                "vram_changed": span([i for i in range(0x4000) if vb[i] != va[i]]),
                "ports_written": writes, "ports_read": reads,
                "sysvars": {f"{a:04X}": v for a, v in sorted(mem.items())},
                "sysvars_changed": [f"{SYSVARS + i:04X}" for i in range(SYSVARS_N) if sb[i] != sa[i]],
                "hooks": [x[1] for x in own if x[0] == "h"],
                "isr_hooks": sorted({x[1] for x in isr if x[0] == "h"}),
                "isr_sysvars": sorted({x[1] for x in isr if x[0] == "m"}),
                "e000": [eb, ea],
            }
    others = {w[1]: (float(w[2]), int(w[3])) for w in lines if w[0] == "P"}
    init = {"time": float(s_init[1]), "frame": int(s_init[2]),
            "regs": dict(zip(REGS, map(int, s_init[3:3 + len(REGS)])))}
    v, sv, e0, g = state(s_init[3 + len(REGS):])
    init.update(sysvars=sv.hex(), vdp_regs=g, e000=e0)
    return out, events, others, init


def isr_summary(lines):
    """the frame interrupt over the whole run: what each one cost (from the
    Z80 taking it to the return), in runs of the same cost, the variables,
    ports and hooks it touched, and what one of each cost did, in order"""
    costs, mem, io, hooks, acc, seq, cur, orders = {}, {}, {}, {}, None, [], [], {}
    for w in lines:
        if w[0] != "E" or w[2] != "1":
            continue
        x = w[3:]
        if x[0] == "I":
            acc, cur = float(x[1]), []
        elif x[0] == "R":
            t = round((float(x[1]) - acc) * CLOCK)
            costs[t] = costs.get(t, 0) + 1
            if seq and seq[-1][0] == t:
                seq[-1][1] += 1
            else:
                seq.append([t, 1])
            orders.setdefault(str(t), cur)
            # each interrupt of the same cost did the same things in the same
            # order: the same ports, the same values to them, the same
            # variables (their values change: JIFFY counts)
            kind = lambda e: e if e.split()[0] in ("out", "in", "hook") else e.split()[0]
            assert [kind(e) for e in cur] == [kind(e) for e in orders[str(t)]], t
        else:
            if x[0] == "m":
                mem[x[1]] = mem.get(x[1], 0) + 1
                cur.append(f"{work_name(int(x[1], 16))} {x[2]}")
            elif x[0] in ("o", "i"):
                k = ("out " if x[0] == "o" else "in ") + x[1]
                io[k] = io.get(k, 0) + 1
                cur.append(k + (f" {int(x[2]):02X}" if x[0] == "o" else ""))
            elif x[0] == "h":
                hooks[x[1]] = hooks.get(x[1], 0) + 1
                cur.append("hook " + x[1])
    return {"costs": {str(k): v for k, v in sorted(costs.items())}, "seq": seq,
            "sysvars": dict(sorted(mem.items())), "ports": dict(sorted(io.items())),
            "hooks": dict(sorted(hooks.items())), "orders": orders}


# the bytes of the work area the calls and the interrupt wrote, named as the
# MSX2 Technical Handbook's work area listing (appendix 4) names them: the
# address, the name, the length
WORK = [(0xF3B0, "LINLEN", 1), (0xF3B3, "TXTNAM", 2), (0xF3B5, "TXTCOL", 2), (0xF3B7, "TXTCGP", 2),
        (0xF3B9, "TXTATR", 2), (0xF3BB, "TXTPAT", 2), (0xF3BD, "T32NAM", 2), (0xF3BF, "T32COL", 2),
        (0xF3C1, "T32CGP", 2), (0xF3C3, "T32ATR", 2), (0xF3C5, "T32PAT", 2), (0xF3C7, "GRPNAM", 2),
        (0xF3C9, "GRPCOL", 2), (0xF3CB, "GRPCGP", 2), (0xF3CD, "GRPATR", 2), (0xF3CF, "GRPPAT", 2),
        (0xF3D1, "MLTNAM", 2), (0xF3D3, "MLTCOL", 2), (0xF3D5, "MLTCGP", 2), (0xF3D7, "MLTATR", 2),
        (0xF3D9, "MLTPAT", 2), (0xF3DC, "CSRY", 1), (0xF3DD, "CSRX", 1)] + \
       [(0xF3DF + n, f"RG{n}SAV", 1) for n in range(8)] + \
       [(0xF3E7, "STATFL", 1), (0xF3E8, "TRGFLG", 1), (0xF3E9, "FORCLR", 1), (0xF3EA, "BAKCLR", 1),
        (0xF3EB, "BDRCLR", 1), (0xF3F6, "SCNCNT", 1), (0xF3F7, "REPCNT", 1), (0xF3F8, "PUTPNT", 2),
        (0xF3FA, "GETPNT", 2), (0xF661, "TTYPOS", 1), (0xF922, "NAMBAS", 2), (0xF924, "CGPBAS", 2),
        (0xF926, "PATBAS", 2), (0xF928, "ATRBAS", 2), (0xFBB2, "LINTTB", 24), (0xFBD9, "CLIKFL", 1),
        (0xFBDA, "OLDKEY", 11), (0xFBE5, "NEWKEY", 11), (0xFBF0, "KEYBUF", 40), (0xFC9E, "JIFFY", 2),
        (0xFCA6, "GRPHED", 1), (0xFCAF, "SCRMOD", 1), (0xFCB0, "OLDSCR", 1), (0xFCC1, "EXPTBL", 4),
        (0xFCC5, "SLTTBL", 4)]


def work_name(a):
    """the variable the byte at A belongs to, or None"""
    return next((n for at, n, k in WORK if at <= a < at + k), None)


def calls(res):
    out = {}
    for machine in MACHINES:
        lines = run(machine)
        rows, events, marks, init = parse(lines)
        isr = isr_summary(lines)
        for label, r in rows.items():
            for a in list(r["sysvars"]) + r["isr_sysvars"]:
                assert work_name(int(a, 16)), (label, a)            # every byte named
            r["sysvars_named"] = sorted({work_name(int(a, 16)) for a in r["sysvars"]},
                                        key=lambda n: next(at for at, m, k in WORK if m == n))
        for a in isr["sysvars"]:
            assert work_name(int(a, 16)), a
        f0 = init["frame"]
        out[TAG[machine]] = {"rows": rows, "init": init, "isr": isr,
                             "marks": {k: v[1] - f0 for k, v in marks.items()}}
    eu, jp = out["eu"]["rows"], out["jp"]["rows"]
    assert list(eu) == list(jp) == [c[0] for c in CASES]           # every call came back
    for label in eu:
        a, b = eu[label], jp[label]
        assert a["t_less_isr"] == b["t_less_isr"], label             # the same on both machines
        assert a["vram_writes"] == b["vram_writes"] and a["sysvars_named"] == b["sysvars_named"], label
        assert a["hooks"] == b["hooks"] and a["ports_written"] == b["ports_written"], label
        assert all(t == int(min(out["eu"]["isr"]["costs"], key=int)) for t in a["isr_t"] + b["isr_t"])
    res["calls"] = out


# ---------------------------------------------------------------- jump
# the MSX1 entry points from $0000 to $0159, in the names of the BIOS
# table at map.grauw.nl (msxbios.php); the data bytes among them, as the
# msx.org wiki names them (Data for MSX description from Main-ROM BIOS)
STANDARD = [(0x0000, "CHKRAM"), (0x0008, "SYNCHR"), (0x000C, "RDSLT"), (0x0010, "CHRGTR"),
            (0x0014, "WRSLT"), (0x0018, "OUTDO"), (0x001C, "CALSLT"), (0x0020, "DCOMPR"),
            (0x0024, "ENASLT"), (0x0028, "GETYPR"), (0x0030, "CALLF"), (0x0038, "KEYINT"),
            (0x003B, "INITIO"), (0x003E, "INIFNK")] + [(0x0041 + 3 * k, n) for k, n in enumerate(
    "DISSCR ENASCR WRTVDP RDVRM WRTVRM SETRD SETWRT FILVRM LDIRMV LDIRVM CHGMOD CHGCLR".split())] + \
    [(0x0066 + 3 * k, n) for k, n in enumerate(
        "NMI CLRSPR INITXT INIT32 INIGRP INIMLT SETTXT SETT32 SETGRP SETMLT CALPAT CALATR GSPSIZ "
        "GRPPRT GICINI WRTPSG RDPSG STRTMS CHSNS CHGET CHPUT LPTOUT LPTSTT CNVCHR PINLIN INLIN "
        "QINLIN BREAKX ISCNTC CKCNTC BEEP CLS POSIT FNKSB ERAFNK DSPFNK TOTEXT GTSTCK GTTRIG GTPAD "
        "GTPDL TAPION TAPIN TAPIOF TAPOON TAPOUT TAPOOF STMOTR LFTQ PUTQ RIGHTC LEFTC UPC TUPC DOWNC "
        "TDOWNC SCALXY MAPXY FETCHC STOREC SETATR READC SETC NSETCX GTASPC PNTINI SCANR SCANL CHGCAP "
        "CHGSND RSLREG WSLREG RDVDP SNSMAT PHYDIO FORMAT ISFLIO OUTDLP GETVCP GETVC2 KILBUF "
        "CALBAS".split())]
DATA = [(0x0004, "CGTABL", 2), (0x0006, "VDP.DR", 1), (0x0007, "VDP.DW", 1), (0x002B, "BASRVN", 2),
        (0x002D, "MSXVER", 1), (0x002E, "MIDI", 1), (0x002F, "reserved", 1)]


def stub_name(rom_bytes, target):
    """chapter 16: C-BIOS's stub for a routine it does not have (PUSH HL,
    PUSH AF, LD HL with the name, CALL the routine that reports it, POP AF,
    POP HL, RET). The name it reports, or None"""
    c = rom_bytes[target:target + 11]
    if c[:3] == bytes([0xE5, 0xF5, 0x21]) and c[5] == 0xCD and c[8:10] == bytes([0xF1, 0xE1]):
        a = c[3] | c[4] << 8
        return rom_bytes[a:rom_bytes.index(0, a)].decode("ascii")
    return None


def page0(machine):
    """the 16 KB of page 0, slot 0, as the program first finds them"""
    tcl = (f'set ::bp [debug set_bp {sym()["rdslt"]} {{}} {{ binary scan [debug read_block memory 0 0x4000] '
           f'H* h; L "blk $h"; debug remove_bp $::bp }}]')
    lines = msxcap.run_tcl(rom(), 3, tcl, machine=machine)
    return bytes.fromhex(next(l for l in lines if l.startswith("blk ")).split()[1])


def jump(res):
    assert len(STANDARD) == 108 and STANDARD[-1] == (0x0159, "CALBAS")
    inc = inc_names()
    out = {}
    for machine in MACHINES:
        low = page0(machine)
        entries = []
        for a, name in STANDARD:
            row = {"at": a, "name": name, "book": name in inc}
            code = low[a:a + 4]
            if code[0] == 0xF3 and code[1] == 0xC3:                  # DI, JP nn
                row["di"] = True
                code = code[1:]
            assert code[0] == 0xC3, (name, low[a:a + 4].hex())      # a JP at every one
            t = code[1] | code[2] << 8
            row["to"] = t
            stub = stub_name(low, t)
            if stub is None and low[t] == 0xC3:                      # a JP on to a stub
                stub = stub_name(low, low[t + 1] | low[t + 2] << 8)
                if stub:
                    row["via"] = True
            if stub:
                row["stub"] = stub
            entries.append(row)
        data = {n: low[a:a + k].hex() for a, n, k in DATA}
        out[TAG[machine]] = {"entries": entries, "data": data}
    eu, jp = out["eu"]["entries"], out["jp"]["entries"]
    assert [(r["name"], r.get("stub")) for r in eu] == [(r["name"], r.get("stub")) for r in jp]
    stubs = [r for r in eu if "stub" in r]
    # each stub reports the routine's own standard name, the one behind CKCNTC
    # ISCNTC's
    assert all(r["stub"] == r["name"] or (r["name"], r["stub"]) == ("CKCNTC", "ISCNTC") for r in stubs)
    # the report: the routine the stubs call writes to two ports, $2E and $2F
    t = next(r["to"] for r in eu if r["name"] == "BEEP")
    low = page0(EU)
    report = low[t + 6] | low[t + 7] << 8
    code = low[report:report + 40]
    ports = sorted({code[i + 1] for i in range(len(code) - 1) if code[i] == 0xD3})
    assert ports == [0x2E, 0x2F], ports
    book = [r for r in eu if r["book"]]
    assert len(book) == 27 and [r["name"] for r in book if "stub" in r] == ["BEEP"]
    out["summary"] = {"entries": len(eu), "stubs": len(stubs), "via": sum(1 for r in stubs if r.get("via")),
                      "real": len(eu) - len(stubs), "book": len(book), "report": report,
                      "report_ports": ports, "di_first": [r["name"] for r in eu if r.get("di")]}
    res["jump"] = out


# ---------------------------------------------------------------- vars
# the length of each variable of bios.inc that is longer than one byte
LENGTH = {"RG0SAV": 8, "PUTPNT": 2, "GETPNT": 2, "NEWKEY": 11, "JIFFY": 2, "EXPTBL": 4, "SLTTBL": 4}
HOOK_LEN = 5


def entry_of(label):
    """the BIOS entry point a case calls"""
    return next(e for l, e, *_ in CASES if l == label)


def var_list():
    """[(name, address, length)] of bios.inc's variables and hooks"""
    inc = inc_names()
    out = []
    for n, a in inc.items():
        if a < SYSVARS:
            continue
        k = HOOK_LEN if n.startswith("H_") else LENGTH.get(n, 2 if n[3:] in ("NAM", "COL", "CGP", "ATR", "PAT")
                                                             else 1)
        out.append((n, a, k))
    return out


def vars(res):
    c = res["calls"]
    rows = []
    for n, a, k in var_list():
        row = {"name": n, "at": a, "len": k, "writers": [], "interrupt": False}
        for tag in ("eu", "jp"):
            sv = bytes.fromhex(c[tag]["init"]["sysvars"])
            row[tag] = sv[a - SYSVARS:a - SYSVARS + k].hex()
            for label, r in c[tag]["rows"].items():
                hit = [x for x in r["sysvars"] if a <= int(x, 16) < a + k]
                if hit and entry_of(label) not in row["writers"]:
                    row["writers"].append(entry_of(label))
                if any(r2 == h for h in r["hooks"] for r2 in [f"{a:04X}"]):
                    row.setdefault("called_by", [])
                    if entry_of(label) not in row["called_by"]:
                        row["called_by"].append(entry_of(label))
            if any(a <= int(x, 16) < a + k for x in c[tag]["isr"]["sysvars"]):
                row["interrupt"] = True
            if n.startswith("H_") and f"{a:04X}" in c[tag]["isr"]["hooks"]:
                row["interrupt"] = True
        rows.append(row)
    by = {r["name"]: r for r in rows}
    # what the chapters found: JIFFY one more each frame interrupt, SCNCNT
    # counted down by it (chapters 17 and 34), the hooks a RET each at INIT
    assert by["JIFFY"]["interrupt"] and by["SCNCNT"]["interrupt"] and by["STATFL"]["interrupt"]
    assert all(by[h]["eu"] == by[h]["jp"] == "c9" * 5 for h in by if h.startswith("H_"))
    assert by["H_CHPU"]["called_by"] == ["CHPUT"] and by["H_CHGE"]["called_by"] == ["CHGET"]
    assert by["H_KEYI"]["interrupt"] and by["H_TIMI"]["interrupt"]
    differ = [r["name"] for r in rows if r["eu"] != r["jp"]]
    res["vars"] = {"rows": rows, "differ": differ,
                   "nobody": [r["name"] for r in rows if not r["writers"] and not r["interrupt"]
                              and not r["name"].startswith("H_")]}


# ---------------------------------------------------------------- uses
def code_words(path):
    """the words of an assembly file, its comments and strings left out"""
    out = set()
    for line in path.read_text(errors="replace").splitlines():
        line = line.replace("af'", "af").replace("AF'", "AF")      # not a quote
        line = re.sub(r'"[^"]*"|\'[^\']*\'', "", line).split(";")[0]
        out.update(re.findall(r"[A-Za-z_][A-Za-z0-9_.]*", line))
    return out


def uses(res):
    names = list(inc_names())
    out = {n: [] for n in names}
    for d in sorted(REPO.iterdir()):
        if not d.is_dir() or not re.fullmatch(r"ch\d\d|app[A-E]", d.name):
            continue
        words = set()
        for f in sorted(d.glob("*.asm")):
            words |= code_words(f)
        for n in names:
            if n in words:
                out[n].append(d.name)
    # and which use $002B, whose bit 7 is 1 at 50 Hz (chapter 4)
    hz = []
    for d in sorted(REPO.iterdir()):
        if d.is_dir() and re.fullmatch(r"ch\d\d|app[A-E]", d.name) and any(
                "$002B" in l.split(";")[0] for f in sorted(d.glob("*.asm"))
                for l in f.read_text(errors="replace").splitlines()):
            hz.append(d.name)
    res["uses"] = {"by_name": out, "unused": [n for n in names if not out[n]], "reads_002B": hz}


# ---------------------------------------------------------------- documents
# What the MSX Red Book (chapter 4, each routine's "Modifies" line) says each
# entry point changes, and whether it leaves the interrupts on (EI) or off
# (DI); None where it names neither, for RSLREG and WSLREG. CALSLT changes,
# besides, whatever the routine it calls changes (the msx.org wiki).
DOCUMENTED = {"RDSLT": ("AF BC DE", "DI"), "WRSLT": ("AF BC D", "DI"), "CALSLT": ("AF' BC' DE' HL'", "DI"),
              "ENASLT": ("AF BC DE", "DI"), "DISSCR": ("AF BC", "EI"), "ENASCR": ("AF BC", "EI"),
              "WRTVDP": ("AF B", "EI"), "RDVRM": ("AF", "EI"), "WRTVRM": ("", "EI"), "SETRD": ("AF", "EI"),
              "SETWRT": ("AF", "EI"), "FILVRM": ("AF BC", "EI"), "LDIRVM": ("AF BC DE HL", "EI"),
              "CHGMOD": ("AF BC DE HL", "EI"), "INITXT": ("AF BC DE HL", "EI"),
              "INIT32": ("AF BC DE HL", "EI"), "INIGRP": ("AF BC DE HL", "EI"),
              "INIMLT": ("AF BC DE HL", "EI"), "CHSNS": ("AF", "EI"), "CHGET": ("AF", "EI"),
              "CHPUT": ("", "EI"), "BEEP": ("AF BC E", "EI"), "GTSTCK": ("AF B DE HL", "EI"),
              "GTTRIG": ("AF BC", "EI"), "RSLREG": ("A", None), "WSLREG": ("", None),
              "SNSMAT": ("AF C", "EI")}
# The first values the documents give the work area: the Red Book's (the
# bytes its BIOS copies from 7F27H in its ROM to F380H-F40FH at power-up,
# the VDP registers' copies for 40 x 24 text mode; JIFFY and SCRMOD, beyond
# them, 0 since CHKRAM clears the whole work area) and the MSX2 Technical
# Handbook's (appendix 4); None where one says nothing, "unused" where the
# Handbook says so. The Red Book's start then runs INIT32 (7C76H) before it
# calls a cartridge's INIT.
DOC_INIT = {  # name: (Red Book, Handbook), one byte or a word each
    "LINLEN": (37, 29), "TXTNAM": (0x0000, 0x0000), "TXTCOL": (0x0000, "unused"),
    "TXTCGP": (0x0800, 0x0800), "TXTATR": (0x0000, "unused"), "TXTPAT": (0x0000, "unused"),
    "T32NAM": (0x1800, 0x1800), "T32COL": (0x2000, 0x2000), "T32CGP": (0x0000, 0x0000),
    "T32ATR": (0x1B00, 0x1B00), "T32PAT": (0x3800, 0x3800), "GRPNAM": (0x1800, 0x1800),
    "GRPCOL": (0x2000, 0x2000), "GRPCGP": (0x0000, 0x0000), "GRPATR": (0x1B00, 0x1B00),
    "GRPPAT": (0x3800, 0x3800), "MLTNAM": (0x0800, 0x0800), "MLTCOL": (0x0000, "unused"),
    "MLTCGP": (0x0000, 0x0000), "MLTATR": (0x1B00, 0x1B00), "MLTPAT": (0x3800, 0x3800),
    "CSRY": (1, 1), "CSRX": (1, 1), "RG0SAV": (0x00, 0x00), "RG1SAV": (0xF0, 0xE0),
    "RG2SAV": (0x00, 0x00), "RG3SAV": (0x00, 0x00), "RG4SAV": (0x01, 0x00), "RG5SAV": (0x00, 0x00),
    "RG6SAV": (0x00, 0x00), "RG7SAV": (0xF4, 0x00), "STATFL": (0xCA, 0x00), "TRGFLG": (0xF1, 0xFF),
    "FORCLR": (15, 15), "BAKCLR": (4, 4), "BDRCLR": (4, 7), "SCNCNT": (1, 1), "REPCNT": (1, 50),
    "PUTPNT": (0xFBF0, 0xFBF0), "GETPNT": (0xFBF0, 0xFBF0), "JIFFY": (0x0000, None),
    "SCRMOD": (0, None)}


def bytes_of(names):
    """the 8-bit registers a list of names stands for: AF is A and F"""
    out = set()
    for n in names:
        p = "'" if n.endswith("'") else ""
        n = n.rstrip("'")
        out |= {n + p} if len(n) == 1 or n in ("IX", "IY") else {n[0] + p, n[1] + p}
    return out


def documents(res):
    rows = res["calls"]
    out = {}
    for entry, (doc, ints) in DOCUMENTED.items():
        cases = [l for l, e, *_ in CASES if e == entry]
        got = set()
        on = []
        for tag in ("eu", "jp"):
            for l in cases:
                r = rows[tag]["rows"][l]
                got |= bytes_of(r["changed"])
                on.append([l, bool(r["after"]["iff"] & 1)])         # IFF1
        said = bytes_of(doc.split())
        extra = got - said - ({"A"} if entry == "CALSLT" else set())  # RSLREG's own A
        out[entry] = {"cbios": sorted(got), "documented": doc, "kept": sorted(said - got),
                      "beyond": sorted(extra), "interrupts": ints, "on_after": on}
        assert not extra, (entry, extra)        # C-BIOS changes nothing the documents keep
        if ints == "DI":
            assert not any(v for _, v in on), entry
    # where C-BIOS leaves the interrupts off and the documents say EI: CHGET
    # with a key waiting
    off = sorted({l for e, v in out.items() if v["interrupts"] == "EI" for l, x in v["on_after"] if not x})
    assert off == ["beep", "chget_k"], off
    # where they name neither, C-BIOS leaves them as they were
    for e, v in out.items():
        if v["interrupts"] is None:
            assert all(x == l.endswith("_e") for l, x in v["on_after"]), e
    # the work area at INIT against the documents' values at power-up
    init = {}
    for tag in ("eu", "jp"):
        sv = bytes.fromhex(rows[tag]["init"]["sysvars"])
        for n, (rb, hb) in DOC_INIT.items():
            at, k = next((a, k) for a, m, k in WORK if m == n)
            v = sv[at - SYSVARS] | (sv[at - SYSVARS + 1] << 8 if k == 2 else 0)
            init.setdefault(n, {"red_book": rb, "handbook": hb})[tag] = v
    agree = [n for n, v in init.items() if v["eu"] == v["jp"] == v["red_book"] and
             v["handbook"] in (v["eu"], "unused")]
    res["documents"] = {"by_entry": out, "ei_but_off": off, "init": init, "init_agree": agree,
                        "init_differ": [n for n in init if n not in agree]}


# ---------------------------------------------------------------- before
def before(res):
    c, j = res["calls"], res["jump"]
    eu = c["eu"]["rows"]
    out = {}
    # chapter 16: the jump table from $0041, and its stubs
    m16 = json.loads((REPO / "ch16" / "meas16.json").read_text())
    j16 = m16["jump"]
    tail = [r for r in j["eu"]["entries"] if r["at"] >= 0x41]
    stubs = {f"{r['at']:04X}": ("→" if r.get("via") else "") + r["stub"] for r in tail if "stub" in r}
    assert len(tail) == j16["entries"] and stubs == j16["stubs"]
    out["ch16_jump"] = {"entries": len(tail), "stubs": len(stubs)}
    # chapter 16's calls: the same time where the call and its state are the same
    r16 = {r["call"]: r for r in m16["calls"]["rows"]}
    plain = int(min(c["eu"]["isr"]["costs"], key=int))
    assert r16["CHGMOD"]["t"] - r16["CHGMOD"]["interrupts"] * plain == eu["chgmod"]["t_less_isr"]
    for n in ("WRTVDP", "GTSTCK"):
        assert r16[n]["t"] == eu[n.lower()]["t"]
    out["ch16_calls"] = {"CHGMOD": [r16["CHGMOD"]["t"], r16["CHGMOD"]["interrupts"]],
                         "WRTVDP": r16["WRTVDP"]["t"], "GTSTCK": r16["GTSTCK"]["t"],
                         "CHPUT": r16["CHPUT"]["t"]}             # CHPUT: in Graphic I there
    # chapter 17: the interrupt's own time, a frame it does not read the keys
    m17 = json.loads((REPO / "ch17" / "meas17.json").read_text())["bios"]
    assert plain == m17["plain"] and str(m17["scans"][0]) in c["eu"]["isr"]["costs"]
    out["ch17"] = {"plain": m17["plain"], "scan": m17["scans"][0]}
    # chapter 19: WRTVRM, SETWRT, RDVRM, FILVRM of 28 bytes, measured and modelled
    m19 = json.loads((REPO / "ch19" / "meas19.json").read_text())["bios"]
    for n in ("WRTVRM", "SETWRT", "RDVRM", "FILVRM"):
        assert m19["model"][n] == eu[n.lower()]["t"] == c["jp"]["rows"][n.lower()]["t"], n
    out["ch19"] = m19["model"]
    # chapter 34: SNSMAT, timed there with the LD A,8 before it (8 T-states)
    m34 = json.loads((REPO / "ch34" / "meas34.json").read_text())["snsmat"]
    assert m34["eu"]["snsmat_t"] - 8 == eu["snsmat"]["t"]
    out["ch34"] = {"snsmat_t": m34["eu"]["snsmat_t"], "ld_a_n": 8}
    # chapter 38: RSLREG, and ENASLT for page 2 (here page 1), on EU16
    m38 = json.loads((REPO / "ch38" / "meas38.json").read_text())["prices"]["debugger"]
    assert m38["RSLREG cart32 eu"]["T"] == eu["rslreg"]["t"]
    out["ch38"] = {"RSLREG": m38["RSLREG cart32 eu"]["T"], "ENASLT_page2": m38["ENASLT cart32 eu"]["T"]}
    # chapter 21: its times of the four mode routines, from the CALL to the
    # return less the frame interrupts that fell inside, each at chapter 17's
    # 516; and CHGMOD's own part, the 117 T-states before INIT32
    m21 = json.loads((REPO / "ch21" / "meas21.json").read_text())["bios"]
    assert m21["irq"] == plain
    assert m21["chgmod_dispatch"] == eu["chgmod"]["t_less_isr"] - eu["init32"]["t_less_isr"]
    ch21 = {}
    for n in ("INITXT", "INIT32", "INIGRP", "INIMLT"):
        own = eu[n.lower()]["t_less_isr"]
        assert own == c["jp"]["rows"][n.lower()]["t_less_isr"] == m21[n]["t"], n
        ch21[n] = {"own": own, "interrupts": {t: m21[t][n]["interrupts"] for t in ("eu", "jp")}}
    out["ch21"] = ch21
    out["ch21_interrupts"] = m21["interrupts"]
    out["ch21_chgmod"] = m21["chgmod_dispatch"]
    res["before"] = out


# ---------------------------------------------------------------- openmsx
def openmsx(res):
    if not versions.builds():
        res["openmsx"] = {"skipped": "OPENMSX_BUILDS not set"}
        return
    import hashlib
    roms = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()[:16] for p in sorted(HERE.glob("*.rom"))}
    out = versions.every_build(["appF"], [s for s in STEPS if s not in ("openmsx", "uses", "documents")],
                               keep=None,
                               values=True)
    res["openmsx"] = {"roms": roms, **out}


# ---------------------------------------------------------------- the main
STEPS = ["calls", "jump", "vars", "uses", "documents", "before", "openmsx"]


def main(names=()):
    res = json.loads(OUT_JSON.read_text()) if names and OUT_JSON.exists() else {}
    for name in STEPS:
        if names and name not in names:
            continue
        sub = json.loads(json.dumps(res))      # a step sees the steps before it, as saved
        globals()[name](sub)
        res[name] = json.loads(json.dumps(sub[name]))
        res = {k: res[k] for k in STEPS if k in res}
        OUT_JSON.write_text(json.dumps(res, indent=1) + "\n")
        print(" ", name, "ok", flush=True)
    return res


if __name__ == "__main__":
    main(sys.argv[1:])
