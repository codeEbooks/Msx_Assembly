#!/usr/bin/env python3
"""meas16.py -- the BIOS as a library, measured on C-BIOS.

    python3 gen16.py && ./build.sh && python3 meas16.py
                                  python3 meas16.py calls stick    only these
                                  python3 meas16.py --missing      those not measured yet

  jump      the jump table, read through the debugger: a JP at every entry
            point, where each goes, and which go to C-BIOS's stub that only
            reports its name; the two bytes of VDP_DR and VDP_DW
  session   WRTVDP and CHPUT followed into C-BIOS with the console's disasm
            (wrtvdp.txt, chput.txt)
  print     figure 16.1: the page CHPUT printed, read back from the name table;
            the time of CHGMOD and of every character; the variables after
  calls     five calls, each with the registers before and after, the system
            variables it wrote, the interrupts it left on, the hooks it went
            through; the same jobs through the ports, timed
  copies    register 1 and RG1SAV, the BIOS's copy of it, after a write
            through the port, DISSCR, ENASCR, and a write through WRTVDP
  hooks     the 112 hooks at INIT; the CALLs to them in C-BIOS's 32 KB; which
            ones hook.asm goes through; figure 16.2, the border in bands, one
            for every character, checked pixel by pixel against the times of
            the hook's OUTs; the hook's price, against the model
  stick     GTSTCK and stick with each of the nine ways to hold the cursor
            keys, from INIT on
  chget     CHGET with the interrupts off: a key held 140 frames after INIT,
            and one held only in the first 127
  ints      WHERE IT BREAKS: the same loop before and after one CHPUT
  answers   the workshop, tried (for Appendix I)
  openmsx   all of it again with every other build (tools/versions.py)

Every number is C-BIOS 0.29a's; a real MSX BIOS has the same entry points and
other routines behind them.
"""
import json
import math
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
sys.path.insert(0, str(HERE))
import meas        # noqa: E402
import msxcap      # noqa: E402
import probe       # noqa: E402
import console     # noqa: E402
import versions    # noqa: E402
import gen16       # noqa: E402

CAPS = HERE / "captures"
CLOCK = probe.CLOCK
RESULTS = 0xC000
REGS = ["af", "bc", "de", "hl", "ix", "iy", "af2", "bc2", "de2", "hl2"]
SYSVARS = 0xF380            # the BIOS's work area, to $FFFF (chapter 3)


def rom(name):
    return HERE / f"{name}.rom"


def sym(name):
    return probe.sym(HERE / f"{name}.sym")


def tstates(a, b):
    return round((b - a) * CLOCK)


def inc_names():
    """{name: value} of bios.inc"""
    out = {}
    for l in (HERE / "bios.inc").read_text().splitlines():
        m = re.match(r"(\w+)\s+EQU\s+\$([0-9A-F]+)", l)
        if m:
            out[m.group(1)] = int(m.group(2), 16)
    return out


def vram(rom_path, stop, start, n, frames):
    lines = probe.at_address(rom_path, stop, f'binary scan [debug read_block VRAM {start} {n}] H* h; '
                                             'L "vram $h"', frames)
    return bytes.fromhex(next(l for l in lines if l.startswith("vram ")).split()[1])


# ---------------------------------------------------------------- jump
# the entry points of the jump table, three bytes apart: $0041 to $0062, then
# from $0066, the Z80's NMI address, to $0159 (the MSX1 standard)
ENTRIES = list(range(0x41, 0x63, 3)) + list(range(0x66, 0x15C, 3))


def stub_name(rom_bytes, target):
    """C-BIOS's stub for a routine it does not have: PUSH HL, PUSH AF, LD HL,
    the name, CALL the routine that reports it, POP AF, POP HL, RET. The name
    it reports, or None"""
    c = rom_bytes[target:target + 11]
    if c[:3] == bytes([0xE5, 0xF5, 0x21]) and c[5] == 0xCD and c[8:10] == bytes([0xF1, 0xE1]):
        a = c[3] | c[4] << 8
        return rom_bytes[a:rom_bytes.index(0, a)].decode("ascii")
    return None


def jump():
    s = sym("print")
    low = bytes(probe.block(rom("print"), s["stop"], 0, 0x2000, frames=20))   # page 0, slot 0
    out, stubs = [], {}
    for a in ENTRIES:
        assert low[a] == 0xC3, hex(a)                       # JP nn at every one
        t = low[a + 1] | low[a + 2] << 8
        name = stub_name(low, t)
        if name is None and low[t] == 0xC3:                 # a JP on to a stub
            name = stub_name(low, low[t + 1] | low[t + 2] << 8)
            if name:
                name = "→" + name
        out.append([a, t, name])
        if name:
            stubs[f"{a:04X}"] = name
    inc = inc_names()
    for n in ("WRTVDP", "LDIRVM", "CHGMOD", "CHGET", "CHPUT", "GTSTCK"):
        a = inc[n]
        assert a in ENTRIES and f"{a:04X}" not in stubs, n
    assert stubs[f"{inc['BEEP']:04X}"] == "BEEP"
    assert low[inc["VDP_DR"]] == low[inc["VDP_DW"]] == 0x98
    names = [n.lstrip("→") for n in stubs.values()]
    # what a stub does with the name: the routine it calls writes to two ports
    t = next(t for a, t, n in out if n == "BEEP")
    report = low[t + 6] | low[t + 7] << 8
    code = low[report:report + 40]
    ports = sorted({code[i + 1] for i in range(len(code) - 1) if code[i] == 0xD3})
    assert ports == [0x2E, 0x2F], ports
    return {"entries": len(ENTRIES), "first": ENTRIES[0], "last": ENTRIES[-1],
            "stubs": stubs, "stub_routines": len(set(names)), "vdp_dr": low[inc["VDP_DR"]],
            "vdp_dw": low[inc["VDP_DW"]], "wrtvdp_target": next(t for a, t, _ in out if a == 0x47),
            "report": report, "report_ports": ports}


# ---------------------------------------------------------------- session
SESSIONS = {"wrtvdp": ["disasm 0x0047 1", "disasm [peek16 0x0048] 16"],
            "chput": ["disasm 0x00A2 1", "disasm [peek16 0x00A3] 9"]}


def disasm_code(text):
    """the instructions of the console's disasm, without addresses and bytes"""
    return [" ".join(re.match(r"^[0-9A-F]{4}\s+(.*?)\s{2,}[0-9A-F]{2}( [0-9A-F]{2})*$", l)
                     .group(1).split()) for l in text.splitlines()]


def session():
    out = {}
    for name, lines in SESSIONS.items():
        e = console.session(rom("print"), lines)
        assert not any(err for _, _, err in e), e
        (HERE / f"{name}.txt").write_text(console.transcript(e))
        out[name] = {"session": [list(x) for x in e], "lines": len(e[1][1].splitlines())}
    body = disasm_code(out["wrtvdp"]["session"][1][1])
    assert body[0] == "di" and "ei" in body and body[-1] == "ret"
    # CHPUT: HL, DE, BC and AF on the stack, then the hook, then AF back
    body = disasm_code(out["chput"]["session"][1][1])
    hook = inc_names()["H_CHPU"]
    assert body[:5] == ["push hl", "push de", "push bc", "push af", f"call #{hook:04x}"], body
    assert body[-1] == "pop af", body
    return out


# ---------------------------------------------------------------- print
PRINT_FRAME = 20


def text_bytes():
    """the bytes of print.asm's text, up to the 0, as the cartridge has them"""
    s = sym("print")
    data = rom("print").read_bytes()
    a = s["text"] - 0x4000
    return list(data[a:data.index(0, a)])


def print_():
    s = sym("print")
    text = text_bytes()
    beep = probe.block(rom("print"), s["stop"], 0x00C1, 2, frames=PRINT_FRAME)
    got = probe.times(rom("print"), {"c0": s["c0"], "c1": s["c1"], "p1": s["p1"], "p2": s["p2"],
                                     "beep": beep[0] | beep[1] << 8, "isr": 0x38},
                      frames=PRINT_FRAME, hits=len(text) + 1, extra="[peek 0xF3DC] [peek 0xF3DD]")
    isr = [x[0] for x in got["isr"]]
    chgmod = tstates(got["c0"][0][0], got["c1"][0][0])
    chgmod_isr = sum(1 for x in isr if got["c0"][0][0] < x < got["c1"][0][0])
    each, lines, codes, with_isr = [], {}, {}, []
    for c, a, b in zip(text, got["p1"], got["p2"]):
        t = tstates(a[0], b[0])
        hit = any(a[0] < x < b[0] for x in isr)
        each.append(t)
        if hit:
            with_isr.append(t)
            continue
        if c in (7, 8, 9, 10, 12, 13, 27):
            codes.setdefault(str(c), set()).add(t)
        elif a is not None:
            lines.setdefault(int(a[2]), set()).add(t)
    assert len(each) == len(text) and len(got["beep"]) == 1
    # a letter's price depends on its line and on nothing else (the ESC Y
    # bytes, which only move the cursor, are the cheap ones of their line)
    letters, esc, after_esc = {}, 0, []
    for c, a, t in zip(text, got["p1"], each):
        if esc:                     # the Y and the two bytes of ESC Y
            esc -= 1
            after_esc.append(t)
            continue
        if c == 27:
            esc = 3
        elif 32 <= c < 127 and t not in with_isr:
            letters.setdefault(int(a[2]), []).append(t)
    per_line = {y: max(set(v), key=v.count) for y, v in letters.items()}
    assert all(sorted(per_line.values()) == list(per_line.values()) for _ in [0])
    isr_extra = sorted({t - per_line[int(a[2])] for c, a, t in zip(text, got["p1"], each)
                        if t in with_isr and 32 <= c < 127})
    # the page, read back from the name table
    names = vram(rom("print"), s["stop"], 0x1800, 768, PRINT_FRAME)
    rows = {r: names[32 * r:32 * r + 32].decode("latin1") for r in range(24)}
    shown = {r: (len(t) - len(t.lstrip()), t.strip()) for r, t in rows.items() if t.strip()}
    want = {2: (5, "Printed by CHPUT,"), 3: (2, "a character at a time."), 6: (5, "TAB: next stop"),
            8: (5, "BS: aXc"), 10: (2, "A line longer than the twenty"),
            11: (2, "-nine columns wraps.")}
    assert shown == want, shown
    v = probe.at_address(rom("print"), s["stop"],
                         'L "v [peek 0xF3DC] [peek 0xF3DD] [peek 0xFCAF] [peek 0xF3B0] '
                         '[peek 0xF3E6]"; binary scan [debug read_block VRAM 0x2000 32] H* h; L "c $h"',
                         PRINT_FRAME)
    csry, csrx, scrmod, linlen, rg7 = (int(x) for x in next(l for l in v if l.startswith("v ")).split()[1:])
    colours = bytes.fromhex(next(l for l in v if l.startswith("c ")).split()[1])
    assert (scrmod, linlen) == (1, 29) and set(colours) == {0x1F} and rg7 == 0x13
    # the photograph
    shots = msxcap.capture(rom("print"), [PRINT_FRAME - 1, PRINT_FRAME], CAPS, "print_f")
    a, b = (Image.open(shots[n]).convert("RGB") for n in (PRINT_FRAME - 1, PRINT_FRAME))
    assert a.tobytes() == b.tobytes()
    shots[PRINT_FRAME - 1].unlink()
    assert all(len(v) == 1 for v in codes.values()), codes
    return {"chgmod": chgmod, "chgmod_isr": chgmod_isr, "chars": len(text), "each": each,
            "per_line": {str(y): t for y, t in sorted(per_line.items())},
            "codes": {k: min(v) for k, v in codes.items()}, "with_isr": len(with_isr),
            "isr_extra": isr_extra, "esc_y": sorted(set(after_esc)),
            "rows": {str(r): list(v) for r, v in shown.items()}, "csry": csry, "csrx": csrx,
            "scrmod": scrmod, "linlen": linlen, "rg7": rg7, "frame": PRINT_FRAME,
            "total": sum(each)}


# ---------------------------------------------------------------- calls
KNOWN = {0xF3DC: "CSRY", 0xF3DD: "CSRX", 0xF3E6: "RG7SAV", 0xF3F6: "SCNCNT", 0xFBB2: "LINTTB",
         0xFC9E: "JIFFY", 0xF661: "TTYPOS"}
CALL_FRAMES = 8


def hook_labels():
    return {f"h{a:04X}": a for a in range(0xFD9A, 0xFFCA, 5)}


def calls():
    s = sym("calls")
    labels = {"t0": s["init"] + 1, "pg": s["pg"], "stop": s["stop"]}
    for n in range(1, 6):
        labels[f"b{n}"], labels[f"a{n}"] = s[f"b{n}"], s[f"a{n}"]
    for q in ("q3", "q3e", "q4", "q5", "q2", "q6"):
        labels[q] = s[q]
    regs = " ".join(f"[reg {r}]" for r in REGS) + " [reg iff]"
    got = probe.times(rom("calls"), labels, frames=CALL_FRAMES, hits=1,
                      extra=regs + f" [binary encode hex [debug read_block memory {SYSVARS} "
                                   f"{0x10000 - SYSVARS}]]")
    events = probe.times(rom("calls"), dict(hook_labels(), isr=0x38), frames=CALL_FRAMES, hits=100)
    ev = sorted((x[0], lab) for lab, v in events.items() for x in v)
    rows = []
    inc = inc_names()
    names = {v: k for k, v in inc.items()}
    names.update(KNOWN)
    for n, name, _, what in gen16.CALLS:
        b, a = got[f"b{n}"][0], got[f"a{n}"][0]
        rb, ra = [int(x) for x in b[2:13]], [int(x) for x in a[2:13]]
        changed = [r for r, x, y in zip(REGS, rb, ra) if x != y]
        mb, ma = bytes.fromhex(b[13]), bytes.fromhex(a[13])
        written = [SYSVARS + i for i in range(len(mb)) if mb[i] != ma[i]]
        assert all(w in names for w in written), [hex(w) for w in written]
        inside = [lab for t, lab in ev if b[0] < t < a[0]]
        rows.append({"n": n, "call": name, "what": what, "t": tstates(b[0], a[0]),
                     "changed": changed, "a_after": ra[0] >> 8, "written": [names[w] for w in written],
                     "iff_before": rb[10], "iff_after": ra[10],
                     "interrupts": inside.count("isr"),
                     "hooks": sorted({lab for lab in inside if lab.startswith("h")})})
    by = {r["call"]: r for r in rows}
    assert all(r["iff_before"] == 0 and r["iff_after"] != 0 for r in rows)   # every one: on
    assert by["CHPUT"]["hooks"] == [f"h{inc['H_CHPU']:04X}"] and by["CHPUT"]["changed"] == []
    assert by["WRTVDP"]["written"] == ["RG7SAV"] and by["WRTVDP"]["changed"] == ["af", "bc"]
    assert by["LDIRVM"]["written"] == [] and by["GTSTCK"]["written"] == []
    assert by["CHGMOD"]["interrupts"] >= 1 and "JIFFY" in by["CHGMOD"]["written"]
    for r in rows:
        if r["call"] != "CHGMOD":
            assert r["interrupts"] == 0 and (r["hooks"] == [] or r["call"] == "CHPUT"), r
    # the ports: the same jobs
    t = lambda x, y: tstates(got[x][0][0], got[y][0][0])
    ports = {"page": t("t0", "pg") + 5, "vdp_reg": t("q3", "q3e"), "otir": t("q4", "q5"),
             "stick": t("q5", "q2"), "putc": t("q2", "q6")}
    p14 = json.loads((REPO / "ch14" / "meas14.json").read_text())["price"]["per_char"]
    assert ports["vdp_reg"] == 40 and ports["putc"] == 8 + 8 + 8 + p14
    # the 768 bytes reached the name table either way
    names_v = vram(rom("calls"), s["q5"], 0x1800, 768, CALL_FRAMES)
    assert list(names_v) == [32 + k % 96 for k in range(768)]
    return {"rows": rows, "ports": ports, "putc": p14}


# ---------------------------------------------------------------- copies
COPY_STEPS = ["CHGMOD", "the port", "DISSCR", "ENASCR", "WRTVDP", "DISSCR", "ENASCR"]


def copies():
    s = sym("copies")
    rg1 = inc_names()["RG0SAV"] + 1
    got = probe.times(rom("copies"), {f"r{k}": s[f"r{k}"] for k in range(7)}, frames=6,
                      extra=f"[vdpreg 1] [peek {rg1}]")
    rows = [[step, int(got[f"r{k}"][0][2]), int(got[f"r{k}"][0][3])]
            for k, step in enumerate(COPY_STEPS)]
    v = [r[1] for r in rows]
    c = [r[2] for r in rows]
    first = v[0]
    assert c[0] == first and first & 2 == 0
    assert v[1] == first | 2 and c[1] == first                  # the copy not told
    assert v[2] == c[2] == first & ~0x40                        # DISSCR, from the copy: bit 1 lost
    assert v[3] == c[3] == first
    assert v[4] == c[4] == first | 2                            # through WRTVDP: the copy knows
    assert v[5] == c[5] == (first | 2) & ~0x40 and v[6] == c[6] == first | 2
    return {"rows": rows}


# ---------------------------------------------------------------- hooks
# the 112 hooks of the MSX1, five bytes apart from $FD9A (the MSX standard)
HOOK_NAMES = """KEYI TIMI CHPU DSPC ERAC DSPF ERAF TOTE CHGE INIP KEYC KYEA NMI PINL QINL INLI
ONGO DSKO SETS NAME KILL IPL COPY CMD DSKF DSKI ATTR LSET RSET FIEL MKI$ MKS$ MKD$ CVI CVS
CVD GETP SETF NOFO NULO NTFL MERG SAVE BINS BINL FILE DGET FILO INDS RSLF SAVD LOC LOF EOF
FPOS BAKU PARD NODE POSD DEVN GEND RUNC CLEA LOPD STKE ISFL OUTD CRDO DSKC DOGR PRGE ERRP
ERRF READ MAIN DIRD FINI FINE CRUN CRUS ISRE NTFN NOTR SNGF NEWS GONE CHRG RETU PRTF COMP
FINP TRMN FRME NTPL EVAL OKNO FING ISMI WIDT LIST BUFL FRQI SCNE FRET PTRG PHYD FORM ERRO
LPTO LPTS SCRE PLAY""".split()
HOOKS = {0xFD9A + 5 * k: "H." + n for k, n in enumerate(HOOK_NAMES)}
CALLED = {"H.KEYI", "H.TIMI", "H.CHPU", "H.TOTE", "H.CHGE", "H.NMI", "H.PINL", "H.QINL", "H.RUNC",
          "H.STKE", "H.OUTD", "H.CHRG", "H.PHYD", "H.FORM", "H.LPTO", "H.LPTS"}
HOOK_FRAMES = 20            # figure 16.2: a frame of hook.rom after INIT
JUMPS = {"ret": 11, "jp": 11, "jr": 13, "jr_not": 8}     # chapters 11 and 12


def lst_code(name, first, last):
    """[(source, bytes)] of NAME.lst from the line labelled FIRST to the one
    whose instruction is LAST, both included"""
    out = []
    for line in (HERE / f"{name}.lst").read_text().splitlines():
        m = probe.LST.match(line)
        if not m or not m.group(3)[1:13].strip() or "..." in m.group(3):
            continue
        src = m.group(3)[13:].split(";")[0].strip()
        if src.startswith(first + ":"):
            out = [None]
        if out:
            if out == [None]:
                out = []
            out.append((src.split(":", 1)[-1].strip() if ":" in src.split()[0] else src,
                        [int(x, 16) for x in m.group(3)[1:13].split()]))
            if out[-1][0] == last:
                return out
    raise ValueError((name, first, last))


def price(code):
    """the MSX price of plain instructions, each run once (chapter 14)"""
    sys.path.insert(0, str(REPO / "ch14"))
    import cycles
    return sum(cycles.msx(b) for _, b in code)


def hooks():
    s = sym("hook")
    assert len(HOOKS) == 112 and max(HOOKS) + 5 == 0xFFCA
    inc = inc_names()
    assert all(HOOKS[inc[n]] == n.replace("_", ".") for n in inc if n.startswith("H_"))
    # at INIT: every hook a RET but one
    at_init = bytes(probe.block(rom("print"), sym("print")["init"] + 1, 0xFD9A, 112 * 5, frames=3))
    others = {HOOKS[0xFD9A + i]: at_init[i:i + 5].hex() for i in range(0, 560, 5)
              if at_init[i:i + 5] != bytes([0xC9] * 5)}
    lines = msxcap.run_tcl(rom("print"), 1, 'binary scan [debug read_block {slotted memory} 0 0x8000] '
                                            'H* h; L "rom $h"')         # slot 0, pages 0 and 1
    rom32 = bytes.fromhex(next(l for l in lines if l.startswith("rom ")).split()[1])
    chput = rom32[0xA3] | rom32[0xA4] << 8
    outd = at_init[0xFEE4 - 0xFD9A:0xFEE4 - 0xFD9A + 5]
    assert list(others) == ["H.OUTD"] and outd[0] == 0xC3 and (outd[1] | outd[2] << 8) == chput
    # the CALLs to a hook in C-BIOS's 32 KB
    called = {}
    for i in range(len(rom32) - 2):
        a = rom32[i + 1] | rom32[i + 2] << 8
        if rom32[i] == 0xCD and a in HOOKS:
            called.setdefault(HOOKS[a], []).append(i)
    assert set(called) == CALLED, sorted(called)
    # OUTDO, at $0018: a JP to a routine whose first CALL is to H.OUTD
    outdo = rom32[0x19] | rom32[0x1A] << 8
    assert rom32[0x18] == 0xC3 and called["H.OUTD"] == [outdo + 1]
    # hook.rom: which hooks it goes through, how often
    labels = {f"h{a:04X}": a for a in HOOKS}
    labels["isr"] = 0x38
    hits = probe.times(rom("hook"), labels, frames=HOOK_FRAMES, hits=2000)
    went = {HOOKS[int(k[1:], 16)]: len(v) for k, v in hits.items() if k != "isr" and v}
    n_isr = len(hits["isr"])
    text = text_of("hook")
    # the times of the OUTs that change the border, and what the hook was given
    POS = "[machine_info VDP_frame_count] [machine_info VDP_cycle_in_frame]"
    got = probe.times(rom("hook"), {"o1": s["o1"], "hook": s["hook"]}, frames=HOOK_FRAMES + 4,
                      hits=len(text) * (HOOK_FRAMES + 2), extra=POS + " [reg a] [reg iff]")
    by_frame = {}
    for x in got["o1"]:
        by_frame.setdefault(int(x[2]), []).append(int(x[3]) // 6)
    full = [f for f in sorted(by_frame) if len(by_frame[f]) == len(text)]
    assert len(full) >= HOOK_FRAMES - 4
    outs = by_frame[full[0]]
    assert all(by_frame[f] == outs for f in full), "the bands move"      # the same every frame
    given = [int(x[4]) for x in got["hook"][:len(text)]]
    assert given == text, given                                          # A: the character
    entries = [x for x in got["hook"] if int(x[2]) == full[0]]
    assert [int(x[4]) for x in entries] == text
    iff = [int(x[5]) != 0 for x in entries]           # the interrupts, as the hook found them
    letters_on = sum(iff[4:])
    bands = [b - a for a, b in zip(outs, outs[1:])]
    letter_bands = bands[4:]
    assert len(set(letter_bands)) == 1
    # the loop round CALL CHPUT: LD A,(HL), OR A, JR Z not taken, INC HL, JR back
    loop_code = [c for c in lst_code("hook", "h2", "jr h2") if c[0].split()[0] not in ("jr", "call")]
    loop = price(loop_code) + JUMPS["jr_not"] + JUMPS["jr"]
    with_hook = letter_bands[0] - loop
    done = json.loads((HERE / "meas16.json").read_text()) if (HERE / "meas16.json").exists() else {}
    pr = (done.get("print") or print_())["per_line"]
    line = 12                                                            # CSRY: ESC Y 32+11
    # the hook, and its JP where H.CHPU had a RET
    body = lst_code("hook", "hook", "ret")
    hook_price = price(body[:-1]) + JUMPS["ret"] + JUMPS["jp"] - JUMPS["ret"]
    assert with_hook == pr[str(line)] + hook_price, (with_hook, pr[str(line)], hook_price)
    # the photograph: every border pixel of the drawn columns the colour of
    # the last change before it (chapter 8's rule), the last band's colour
    # (BLACK, from the frame before) above the first
    shots = msxcap.capture(rom("hook"), [HOOK_FRAMES - 1, HOOK_FRAMES], CAPS, "hook_f")
    a, b = (Image.open(shots[n]).convert("RGB") for n in (HOOK_FRAMES - 1, HOOK_FRAMES))
    assert a.tobytes() == b.tobytes()
    shots[HOOK_FRAMES - 1].unlink()
    shows = []
    for k, w in enumerate(outs):            # OUT (n),A writes 8 T after its start (chapter 8)
        line_, t = divmod(w + 8, meas.T_PER_LINE)
        shows.append((line_, math.ceil(1.5 * t - 31), "LIGHT_GREEN" if k % 2 == 0 else "BLACK"))
    px = Image.open(shots[HOOK_FRAMES]).convert("L").load()
    first = meas.FRAME_LINE_OF_ROW0["MSXBOOK_EU16"]
    checked, k, want = 0, 0, shows[-1][2]
    for y in range(meas.CAPTURE_H):
        for x in range(meas.DRAWN[0], meas.DRAWN[1] + 1):
            while k < len(shows) and shows[k][:2] <= (first + y, x):
                want = shows[k][2]
                k += 1
            if meas.PAPER_X0 <= x < meas.PAPER_X0 + meas.PAPER_W and \
                    meas.PAPER_Y0 <= y < meas.PAPER_Y0 + meas.PAPER_H:
                continue
            seen = "BLACK" if px[x, y] < 90 else "LIGHT_GREEN"
            assert seen == want, (x, y, px[x, y], want)
            checked += 1
    # the page under the bands
    lines = msxcap.run_tcl(rom("hook"), HOOK_FRAMES + 1, "", events={
        HOOK_FRAMES: f'binary scan [debug read_block VRAM {0x1800 + 32 * 11} 32] H* h; L "vram $h"'})
    names = bytes.fromhex(next(l for l in lines if l.startswith("vram ")).split()[1])
    assert names.decode("latin1").strip() == "H.CHPU SEES EVERY CHARACTER.", names
    return {"hooks": len(HOOKS), "ret_at_init": 112 - len(others), "outd": outd.hex(),
            "chput": chput, "outdo": outdo, "called": {k: [f"{i:04X}" for i in v] for k, v in sorted(called.items())},
            "went": went, "isr": n_isr, "frames": HOOK_FRAMES, "text": len(text),
            "outs": outs, "bands": bands, "letter": letter_bands[0], "loop": loop,
            "with_hook": with_hook, "without": pr[str(line)], "line": line,
            "hook_price": hook_price, "iff_at_hook": iff, "letters_on": letters_on,
            "first_row": shows[0][0] - first, "last_row": shows[-1][0] - first,
            "pixels": checked, "frame": HOOK_FRAMES}


def text_of(name):
    """the bytes of NAME.asm's text, up to the 0, as the cartridge has them"""
    data = rom(name).read_bytes()
    a = sym(name)["text"] - 0x4000
    return list(data[a:data.index(0, a)])


# ---------------------------------------------------------------- stick
KEYS = {"LEFT": 0x10, "UP": 0x20, "DOWN": 0x40, "RIGHT": 0x80}
HOLDS = [(), ("UP",), ("UP", "RIGHT"), ("RIGHT",), ("DOWN", "RIGHT"), ("DOWN",),
         ("DOWN", "LEFT"), ("LEFT",), ("UP", "LEFT"), ("UP", "DOWN")]


def stick():
    s = sym("stick")
    out = []
    for keys in HOLDS:
        mask = sum(KEYS[k] for k in keys)
        ev = {0: f"keymatrixdown 8 0x{mask:02X}"} if mask else {}
        tcl = "\n".join(f'set ::b{k} [debug set_bp {s[k]} {{}} {{ L "T {k} [machine_info time]"; '
                        f'debug remove_bp $::b{k} }}]' for k in ("s1", "s2", "s3", "s4", "stop"))
        tcl += f'\nset ::bm [debug set_bp {s["stop"]} {{}} {{ L "R [peek {RESULTS}] [peek {RESULTS + 1}]"; ' \
               'debug remove_bp $::bm }]'
        lines = msxcap.run_tcl(rom("stick"), 3, tcl, events=ev)
        tm = {l.split()[1]: float(l.split()[2]) for l in lines if l.startswith("T ")}
        r = next(l for l in lines if l.startswith("R ")).split()[1:]
        bios, own = int(r[0]), int(r[1])
        dx = ("RIGHT" in keys) - ("LEFT" in keys)
        dy = ("DOWN" in keys) - ("UP" in keys)
        assert bios == own == gen16.DIRECTION[(dx, dy)], (keys, bios, own)
        out.append({"keys": list(keys), "gtstck": bios, "stick": own,
                    "t_gtstck": tstates(tm["s1"], tm["s2"]), "t_stick": tstates(tm["s3"], tm["s4"])})
    assert len({o["t_stick"] for o in out}) == 1
    return {"holds": out, "t_stick": out[0]["t_stick"],
            "t_gtstck": sorted({o["t_gtstck"] for o in out})}


# ---------------------------------------------------------------- chget
FIRST_SCAN = 127            # C-BIOS's SCNCNT at INIT: frames before the first look


def chget_run(down, up, frames):
    s = sym("chget")
    tcl = (f'set ::bc [debug set_bp {s["c2"]} {{}} {{ L "c2 [machine_info VDP_frame_count] [reg a] '
           f'[reg iff]"; debug remove_bp $::bc }}]\n'
           f'set ::bi [debug set_bp 0x38 {{}} {{ L "isr [machine_info VDP_frame_count] '
           f'[peek 0xF3F6]"; debug remove_bp $::bi }}]\n'
           f'set ::bh [debug set_bp {inc_names()["H_CHGE"]} {{}} {{ L "hook [reg iff]"; '
           f'debug remove_bp $::bh }}]')
    ev = {down: "keymatrixdown 8 0x01", up: "keymatrixup 8 0x01",
          frames - 1: 'L "end [reg iff] [peek16 0xF3F8] [peek16 0xF3FA] [reg pc]"'}
    ev[0] = 'L "init [peek 0xF3F6] [reg iff]"'
    lines = msxcap.run_tcl(rom("chget"), frames, tcl, events=ev)
    f0 = int(lines[0].split()[1])
    pick = lambda tag: next((l.split()[1:] for l in lines if l.startswith(tag + " ")), None)
    return f0, pick("init"), pick("isr"), pick("c2"), pick("end"), pick("hook")


def chget():
    f0, init, isr, c2, end, hook = chget_run(140, 150, 160)
    assert hook and int(hook[0]) == 0           # H.CHGE, before the interrupts come on
    assert int(init[0]) == FIRST_SCAN and int(init[1]) == 0
    assert isr and int(isr[0]) == f0                    # the first interrupt: the call's own
    assert c2 and int(c2[1]) == 32 and int(c2[2]) != 0
    late = int(c2[0]) - f0
    f0b, initb, isrb, c2b, endb, _ = chget_run(10, 14, 160)
    assert c2b is None and endb[1] == endb[2]            # the key never reached the buffer
    pc = int(endb[3])
    return {"scncnt": FIRST_SCAN, "returned_frame": late, "key": 32, "pressed": 140,
            "early_pressed": [10, 14], "early_lost": True, "early_pc": pc,
            "iff_after": int(c2[2]) != 0}


# ---------------------------------------------------------------- ints
def ints():
    s = sym("ints")
    got = probe.times(rom("ints"), {k: s[k] for k in ("w1", "w2", "w3", "w4")}, frames=10,
                      extra="[peek16 0xFC9E] [reg iff]")
    isr = probe.times(rom("ints"), {"isr": 0x38}, frames=10, hits=20)["isr"]
    t = {k: got[k][0][0] for k in got}
    before, after = tstates(t["w1"], t["w2"]), tstates(t["w3"], t["w4"])
    price = 18 + 11 + 30 * gen16.WAIT_TURNS - 5 + 11
    assert before == price and after > price
    inside = [x for x in isr if t["w3"] < x[0] < t["w4"]]
    during = [x for x in isr if t["w2"] < x[0] < t["w3"]]
    jiffy = [int(got[k][0][2]) for k in ("w1", "w4")]
    assert int(got["w1"][0][3]) == 0 and int(got["w3"][0][3]) != 0
    assert (after - before) % len(inside) == 0
    return {"price": price, "before": before, "after": after, "extra": after - before,
            "isr_inside": len(inside), "each": (after - before) // len(inside),
            "isr_during_chput": len(during), "jiffy": jiffy,
            "chput": tstates(t["w2"], t["w3"])}


# ---------------------------------------------------------------- answers
def build_temp(name, text):
    tmp = Path(tempfile.mkdtemp(prefix=f"{name}_"))
    (tmp / f"{name}.asm").write_text(text)
    for inc in ("msx.inc", "bios.inc"):
        shutil.copy(HERE / inc, tmp)
    subprocess.run(["sjasmplus", "--nologo", "--msg=err", "--syntax=bFw", f"--sym={name}.sym",
                    f"{name}.asm"], cwd=tmp, check=True)
    return tmp


ANSWERS = """        ld a, 1
        call CHGMOD
        di
        ld hl, hello
q1:     ld a, (hl)              ; question 1: HELLO on line 20
        or a
        jr z, q2
        call CHPUT
        di
        inc hl
        jr q1
q2:     ld a, 1                 ; question 4: joystick 1, nothing plugged in
        call GTSTCK
q3:     ld (RESULTS), a
        di
        ld hl, $4000            ; question 5: 6,144 bytes with LDIRVM
        ld de, $0000
        ld bc, 6144
q5:     call LDIRVM
q6:     di
"""


def answers():
    out = {}
    text = gen16.cart("answers", "the workshop", ANSWERS,
                      after='hello:  db 27, "Y", 32+19, 32+2, "HELLO", 0\n')
    tmp = build_temp("answers", text)
    try:
        r, s = tmp / "answers.rom", probe.sym(tmp / "answers.sym")
        call = s["q1"] + 4                      # the CALL CHPUT in the loop
        got = probe.times(r, {"c": call, "after": call + 3, "isr": 0x38, "q5": s["q5"],
                              "q6": s["q6"]}, frames=12, hits=30, extra="[peek 0xF3DC]")
        stick1 = probe.memory(r, s["stop"], RESULTS, 1, frames=12)[0]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    isr = [x[0] for x in got["isr"]]
    each = [(tstates(a[0], b[0]), int(a[2]), any(a[0] < x < b[0] for x in isr))
            for a, b in zip(got["c"], got["after"])]
    letters = [t for t, y, hit in each[4:] if not hit]       # after ESC, Y and its two bytes
    assert all(y == 20 for _, y, _ in each[4:]) and len(set(letters)) == 1
    out["q1"] = {"line": 20, "t": letters[0]}
    out["q4"] = {"gtstck_1": stick1}
    t5 = tstates(got["q5"][0][0], got["q6"][0][0])
    inside = sum(1 for x in isr if got["q5"][0][0] < x < got["q6"][0][0])
    out["q5"] = {"ldirvm": t5, "interrupts": inside, "per_byte": round(t5 / 6144, 1),
                 "otir": 6144 * 23 - 24 * 5}
    return out


# ---------------------------------------------------------------- openmsx
OPENMSX_SECTIONS = ["jump", "session", "print", "calls", "copies", "hooks", "stick", "chget", "ints",
                    "answers"]


def openmsx():
    if not versions.builds():
        return {"skipped": "OPENMSX_BUILDS not set"}
    return versions.every_build(["ch16"], OPENMSX_SECTIONS)


SECTIONS = {"jump": jump, "session": session, "print": print_, "calls": calls, "copies": copies,
            "hooks": hooks, "stick": stick,
            "chget": chget, "ints": ints, "answers": answers, "openmsx": openmsx}


def main(names=()):
    CAPS.mkdir(exist_ok=True)
    path = HERE / "meas16.json"
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
    print(json.dumps({k: out[k] for k in (sys.argv[1:] or out) if k in out}, indent=1)[:5000])
