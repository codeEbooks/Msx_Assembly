#!/usr/bin/env python3
"""meas17.py -- the interrupt, taken over: measured.

    python3 gen17.py && ./build.sh && python3 meas17.py
                                  python3 meas17.py modes bios     only these
                                  python3 meas17.py --missing      those not measured yet

  session   the BIOS's interrupt routine, followed from $0038 with the
            console's disasm (bios.txt)
  signal    where in the frame the VDP raises its signal, on both machines,
            and when the BIOS's routine takes it down
  modes     one interrupt in each mode: the signal, the moment the processor
            takes it, the first instruction of the routine, the stack, the
            switches; the two bytes mode 2 reads from the table
  bios      the BIOS's routine, interrupt after interrupt, from the moment it
            is taken to the return: what it costs, the hooks it calls, the
            stack it uses
  timi      the same with tick in H.TIMI: tick's price, against the model
  clock     the program's own routine: what it costs, against the model; the
            clock after 505 frames at 50 Hz and 606 at 60 Hz; figure 17.1
  paint     saved.asm and unsaved.asm: the name table, cell by cell, against
            the number of cells painted when each interrupt came; figure 17.2
  late      the interrupts off across the signal: when each is taken
  iff       LD A,I's answer in P/V, and the interrupts after keep and keep2, as
            usual and with the signal coming while LD A,I runs
  keys      CHGET in mode 2: alone, behind a routine that goes on into the
            BIOS's, and behind one that reads the status first
  forgot    WHERE IT BREAKS: a routine that does not read the status;
            figure 17.3, checked pixel by pixel against its OUTs
  answers   the workshop, tried (for Appendix I)
  openmsx   all of it again with every other build (tools/versions.py)
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
sys.path.insert(0, str(HERE))
import meas        # noqa: E402
import msxcap      # noqa: E402
import probe       # noqa: E402
import console     # noqa: E402
import versions    # noqa: E402
import gen17       # noqa: E402

CAPS = HERE / "captures"
CLOCK = probe.CLOCK
EU, JP = "MSXBOOK_EU16", "MSXBOOK_JP16"
VDP_PER_T = 6               # the VDP's clock is six times the processor's
LINE_VDP = 1368             # VDP cycles in a line: 228 T-states
POS = "[machine_info VDP_frame_count] [machine_info VDP_cycle_in_frame]"
RESULTS = 0xC000
JUMPS = {"ret": 11, "jp": 11, "jr": 13, "jr_not": 8}     # chapters 11 and 12


def rom(name):
    return HERE / f"{name}.rom"


def sym(name):
    return probe.sym(HERE / f"{name}.sym")


def inc_names():
    out = {}
    for l in (HERE / "bios.inc").read_text().splitlines():
        m = re.match(r"(\w+)\s+EQU\s+\$([0-9A-F]+)", l)
        if m:
            out[m.group(1)] = int(m.group(2), 16)
    return out


def run(name, frames, tcl, machine=EU, events=None):
    """the log of a run, split into words"""
    return [l.split() for l in msxcap.run_tcl(rom(name), frames, tcl, machine=machine,
                                              events=events)]


def at(words):
    """(frame, VDP cycle) of a logged position"""
    return int(words[0]), int(words[1])


def lst_code(name, first, last):
    """[(source, bytes)] of NAME.lst from the line labelled FIRST to the one
    whose instruction is LAST, both included"""
    out = None
    for line in (HERE / f"{name}.lst").read_text().splitlines():
        m = probe.LST.match(line)
        if not m or not m.group(3)[1:13].strip() or "..." in m.group(3):
            continue
        src = m.group(3)[13:].split(";")[0].strip()
        if src.startswith(first + ":"):
            out = []
        if out is not None:
            code = src.split(":", 1)[1].strip() if re.match(r"^[\w.]+:", src) else src
            out.append((code, [int(x, 16) for x in m.group(3)[1:13].split()]))
            if code == last:
                return out
    raise ValueError((name, first, last))


def price(code):
    """the MSX price of each instruction, run once: chapter 14's cycles.py for
    all but jumps, calls and returns (chapters 11 and 12)"""
    sys.path.insert(0, str(REPO / "ch14"))
    import cycles
    out = []
    for src, b in code:
        op = src.split()[0]
        out.append((src, JUMPS[op] if op in ("ret", "jp") else
                    None if op in ("jr", "djnz") else cycles.msx(b)))   # those: taken or not
    return out


# the cost of an interrupt as the program sees it: from the moment the
# processor takes it (openMSX's probe z80.acceptIRQ) to the moment it is back
# at the instruction it would have run next
COST_TCL = f'''
proc back {{}} {{
  L "ret {POS} [machine_info time]"
  debug remove_bp $::bb
}}
debug probe set_bp z80.acceptIRQ {{}} {{
  L "acc {POS} [machine_info time] [reg pc] [reg sp] [peek 0xF3F6]"
  set ::bb [debug set_bp [reg pc] {{}} back]
}}
'''


def costs(lines):
    """[(frame, T-states, SCNCNT when taken, return address)] from COST_TCL's log"""
    out, acc = [], None
    for w in lines:
        if w[0] == "acc":
            acc = (int(w[1]), float(w[3]), int(w[4]), int(w[6]))
        elif w[0] == "ret" and acc:
            out.append((acc[0], round((float(w[3]) - acc[1]) * CLOCK), acc[3], acc[2]))
            acc = None
    return out


# ---------------------------------------------------------------- session
SESSION = ["disasm 0x0038 1", "disasm [peek16 0x0039] 22"]


def disasm_code(text):
    return [" ".join(re.match(r"^[0-9A-F]{4}\s+(.*?)\s{2,}[0-9A-F]{2}( [0-9A-F]{2})*$", l)
                     .group(1).split()) for l in text.splitlines()]


def session():
    e = console.session(rom("bios"), SESSION)
    assert not any(err for _, _, err in e), e
    (HERE / "bios.txt").write_text(console.transcript(e))
    body = disasm_code(e[1][1])
    inc = inc_names()
    assert body[:10] == ["push hl", "push de", "push bc", "push af", "exx", "ex af,af'",
                         "push hl", "push de", "push bc", "push af"], body
    keyi, timi = body.index(f"call #{inc['H_KEYI']:04x}"), body.index(f"call #{inc['H_TIMI']:04x}")
    status = body.index("in a,(#99)")
    assert keyi < status < timi
    return {"lines": len(body), "pushes": sum(1 for b in body if b.startswith("push")),
            "keyi": keyi, "status": status, "timi": timi}


# ---------------------------------------------------------------- signal
def signal():
    out = {}
    s = sym("bios")
    for machine in (EU, JP):
        tcl = (f'debug probe set_bp VDP.IRQvertical {{}} {{ L "irq [debug probe read VDP.IRQvertical] {POS}" }}\n'
               f'debug set_bp 0x38 {{}} {{ L "x38 {POS}" }}\n')
        w = run("bios", 6, tcl, machine)
        up = [at(x[2:4]) for x in w if x[0] == "irq" and x[1] == "1"]
        down = [at(x[2:4]) for x in w if x[0] == "irq" and x[1] == "0"]
        entry = [at(x[1:3]) for x in w if x[0] == "x38"]
        assert len({c for _, c in up}) == 1 and len(up) >= 5
        cyc = up[0][1]
        line, rest = divmod(cyc, LINE_VDP)
        # the status read: so many T-states after $0038, every frame the same
        after = {(d[1] - e[1]) / VDP_PER_T for e, d in zip(entry, down)}
        assert len(after) == 1
        out[machine] = {"cycle": cyc, "line": line, "in_line_vdp": rest,
                        "t": cyc / VDP_PER_T, "down_after_entry": after.pop()}
    assert out[EU]["line"] - meas.PAPER_FRAME_LINE0[EU] == 192
    assert out[JP]["line"] - meas.PAPER_FRAME_LINE0[JP] == 192
    return out


# ---------------------------------------------------------------- modes
def modes():
    s = sym("modes")
    tcl = (f'L "im [reg im]"\n'
           f'debug probe set_bp VDP.IRQvertical {{}} {{ L "irq [debug probe read VDP.IRQvertical] {POS}" }}\n'
           f'debug probe set_bp z80.acceptIRQ {{}} {{ L "acc {POS} [reg pc] [reg im]" }}\n'
           f'debug set_bp 0x38 {{}} {{ L "go {POS} [reg pc] [reg sp] [peek16 [reg sp]] [reg iff]" }}\n'
           f'debug set_bp {gen17.VECTOR} {{}} {{ L "go {POS} [reg pc] [reg sp] [peek16 [reg sp]] [reg iff]" }}\n'
           f'debug set_bp {s["e2"]} {{}} {{ set ::armed 1 }}\n'
           f'debug set_watchpoint read_mem {{{gen17.TABLE} {gen17.TABLE + 256}}} {{}} '
           f'{{ if {{[info exists ::armed]}} {{ L "rd $::wp_last_address {POS}" }} }}\n')
    w = run("modes", 6, tcl)
    im_init = int(next(x for x in w if x[0] == "im")[1])
    ups = [at(x[2:4]) for x in w if x[0] == "irq" and x[1] == "1"]
    accs = [x for x in w if x[0] == "acc"]
    gos = [x for x in w if x[0] == "go"]
    reads = [(int(x[1]), at(x[2:4])) for x in w if x[0] == "rd"]
    rows = []
    halts = {2: s["e2"] + 3, 1: s["e1"] + 3, 0: s["e0"] + 3}      # after IN A,(n) and EI: the HALT
    for mode, a, g in zip((2, 1, 0), accs, gos):
        fa, ca = at(a[1:3])
        fg, cg = at(g[1:3])
        up = next(c for f, c in ups if f == fa)
        assert fa == fg and int(a[4]) == mode
        rows.append({"mode": mode, "pc": int(g[3]), "signal": up, "taken": ca, "entry": cg,
                     "wait_vdp": ca - up, "answer": (cg - ca) / VDP_PER_T,
                     "sp": int(g[4]), "ret": int(g[5]), "iff": int(g[6]), "halt": halts[mode]})
    for r in rows:
        assert r["ret"] == r["halt"] + 1 and r["iff"] == 0 and r["sp"] == 0xF380 - 2, r
        assert r["answer"] == gen17.T_TAKE[r["mode"]], r                  # Zilog's
        assert 0 < r["wait_vdp"] <= 5 * VDP_PER_T
    assert rows[0]["pc"] == gen17.VECTOR and rows[1]["pc"] == rows[2]["pc"] == 0x38
    m2 = rows[0]
    assert [a for a, _ in reads] == [gen17.TABLE + 255, gen17.TABLE + 256], reads
    after = [(c - m2["taken"]) / VDP_PER_T for _, (f, c) in reads]
    return {"im_at_init": im_init, "rows": rows, "reads": [a for a, _ in reads], "read_after": after,
            "bus": reads[0][0] & 0xFF}


# ---------------------------------------------------------------- bios
BIOS_FRAMES = 460


def bios_run(name):
    inc = inc_names()
    tcl = COST_TCL + (
        f'debug set_bp {inc["H_KEYI"]} {{}} {{ L "keyi {POS}" }}\n'
        f'debug set_bp {inc["H_TIMI"]} {{}} {{ L "timi {POS} [reg a] [reg sp]" }}\n'
        f'set ::low 0x10000\n'
        f'debug set_watchpoint write_mem {{0xF200 0xF37F}} {{}} '
        f'{{ if {{$::wp_last_address < $::low}} {{ set ::low $::wp_last_address }} }}\n'
        f'debug probe set_bp z80.acceptIRQ {{}} {{ L "low $::low"; set ::low 0x10000 }}\n')
    ev = {0: 'L "jiffy [peek16 0xFC9E]"', BIOS_FRAMES - 1: 'L "jiffy [peek16 0xFC9E]"'}
    return run(name, BIOS_FRAMES, tcl, events=ev)


def bios_summary(w):
    c = costs(w)
    lows = [int(x[1], 0) for x in w if x[0] == "low"][1:] + [None]
    kinds = {}
    for (f, t, sc, ret), low in zip(c, lows):
        kinds.setdefault(t, []).append((f, sc, low))
    timi = [x for x in w if x[0] == "timi"]
    keyi = [x for x in w if x[0] == "keyi"]
    jiffy = [int(x[1]) for x in w if x[0] == "jiffy"]
    return c, kinds, timi, keyi, jiffy


def bios():
    w = bios_run("bios")
    c, kinds, timi, keyi, jiffy = bios_summary(w)
    first = c[0][0]
    assert len(timi) == len(keyi) == len(c)
    assert {int(x[4]) for x in timi} == {0xF380 - 24}                 # 24 bytes, chapter 12
    status = {int(x[3]) for x in timi}
    # which frames read the keyboard: SCNCNT was 1 when the interrupt came
    scan = [t for f, t, sc, ret in c if sc == 1]
    plain = [t for f, t, sc, ret in c if sc != 1]
    assert len(set(plain)) == 1
    lows = {t: min(l for _, _, l in v if l is not None) for t, v in kinds.items()}
    steady = c[127:]                                                     # after the first look
    # the same, with the space bar held for ten frames, as chain.asm holds it
    held = run("bios", gen17.KEY_FRAMES, COST_TCL, events={gen17.KEY_FRAME: "keymatrixdown 8 0x01",
                                                           gen17.KEY_UP: "keymatrixup 8 0x01"})
    hc = costs(held)
    f0 = int(held[0][1])
    with_key = sorted({t for f, t, sc, ret in hc if sc == 1 and gen17.KEY_FRAME <= f - f0 <= gen17.KEY_UP})
    after_key = sorted({t for f, t, sc, ret in hc if sc == 1 and f - f0 > gen17.KEY_UP})
    per_frame = sum(t for _, t, _, _ in steady) / len(steady)
    return {"frames": len(c), "first_frame": first, "plain": plain[0], "scans": sorted(set(scan)),
            "kinds": {str(t): len(v) for t, v in sorted(kinds.items())},
            "first_scan": next(i for i, x in enumerate(c) if x[2] == 1),
            "lowest": {str(t): l for t, l in lows.items()}, "status_at_timi": sorted(status),
            "jiffy": jiffy, "per_frame_after": round(per_frame, 1),
            "pct_plain": round(100 * plain[0] / gen17.FRAME_T, 2),
            "pct_scan": round(100 * max(scan) / gen17.FRAME_T, 2),
            "pct_after": round(100 * per_frame / gen17.FRAME_T, 2),
            "with_key": with_key, "after_key": after_key,
            "pct_key": round(100 * max(with_key) / gen17.FRAME_T, 2)}


# ---------------------------------------------------------------- timi
def timi():
    w = bios_run("timi")
    c, kinds, tm, keyi, jiffy = bios_summary(w)
    b = json.loads((HERE / "meas17.json").read_text())["bios"] if (HERE / "meas17.json").exists() \
        else bios()
    plain = [t for f, t, sc, ret in c if sc != 1]
    scan = sorted({t for f, t, sc, ret in c if sc == 1})
    assert len(set(plain)) == 1
    # tick, and its JP where H.TIMI had a RET
    body = price(lst_code("timi", "tick", "ret"))
    model = sum(t for _, t in body[:-1]) + JUMPS["jp"]    # tick's RET takes the place of H.TIMI's
    assert plain[0] - b["plain"] == model, (plain[0], b["plain"], model)
    assert [s - x for s, x in zip(scan, b["scans"])] == [model] * len(scan)
    t_end = run("timi", BIOS_FRAMES, "", events={BIOS_FRAMES - 1: f'L "end [peek16 {RESULTS}] '
                                                               f'[peek16 0xFC9E]"'})
    end = next(x for x in t_end if x[0] == "end")
    assert len(tm) == len(c)
    return {"plain": plain[0], "scans": scan, "model": model, "body": body,
            "status_at_tick": sorted({int(x[3]) for x in tm}),
            "ticks_end": int(end[1]), "jiffy_end": int(end[2]), "jiffy": jiffy}


# ---------------------------------------------------------------- clock
CLOCK_SHOT = 505            # the film frame of figure 17.1
CLOCK_JP = 606              # ten seconds at 60 Hz


def clock():
    s = sym("clock")
    out = {}
    w = run("clock", 120, COST_TCL + f'debug set_bp {s["isr"]} {{}} {{ L "isr {POS} [reg sp]" }}\n')
    c = costs(w)
    sps = {int(x[3]) for x in w if x[0] == "isr"}
    ts = sorted({t for _, t, _, _ in c})
    code = price(lst_code("clock", "isr", "ret"))
    names = [src for src, _ in code]
    jr = names.index("jr nz, isr1")
    short = sum(t for _, t in code[:jr]) + JUMPS["jr"] + sum(t for _, t in code[names.index("pop hl"):])
    long = sum(t for _, t in code[:jr]) + JUMPS["jr_not"] + sum(t for _, t in code[jr + 1:])
    code[jr] = (code[jr][0], [JUMPS["jr"], JUMPS["jr_not"]])
    take = gen17.T_TAKE[2] + JUMPS["jp"]
    assert ts == [take + short, take + long], (ts, take, short, long)
    longs = sum(1 for _, t, _, _ in c if t == take + long)
    assert sps == {0xF380 - 2}
    # the clock, read from the RAM and from the screen, after ten seconds
    for machine, frame in ((EU, CLOCK_SHOT), (JP, CLOCK_JP)):
        ev = {frame: f'L "clk [peek16 {s["frames"]}] [peek16 {s["seconds"]}] [peek {s["rate"]}]"; '
                     'binary scan [debug read_block VRAM [expr 0x1800 + 32 * '
                     f'{gen17.CLOCK_ROW}] 96] H* h; L "names $h"'}
        w = run("clock", frame + 1, "", machine, events=ev)
        clk = next(x for x in w if x[0] == "clk")
        names_ = bytes.fromhex(next(x for x in w if x[0] == "names")[1]).decode("latin1")
        shown = (names_[18:23].strip(), names_[64 + 18:64 + 23].strip())
        out[machine] = {"frames": int(clk[1]), "seconds": int(clk[2]), "rate": int(clk[3]),
                        "shown": shown, "frame": frame}
    assert out[EU]["rate"] == 50 and out[JP]["rate"] == 60
    assert out[EU]["seconds"] == out[JP]["seconds"] == 10
    shots = msxcap.capture(rom("clock"), [CLOCK_SHOT - 1, CLOCK_SHOT], CAPS, "clock_f")
    shots[CLOCK_SHOT - 1].unlink()
    return {"costs": ts, "take": take, "short": short, "long": long, "runs": len(c),
            "long_runs": longs, "code": code, **out,
            "stack": 0xF380 - min(sps) + 2 * sum(1 for src, _ in code if src.startswith("push")),
            "frame": CLOCK_SHOT}


# ---------------------------------------------------------------- paint
PAINT_FRAMES = 12


def paint_one(name):
    s = sym(name)
    tcl = (f'set ::n 0\n'
           f'debug set_bp {s["cell"]} {{}} {{ set ::armed 1 }}\n'
           f'debug set_watchpoint write_io 0x98 {{}} {{ if {{[info exists ::armed]}} {{ incr ::n }} }}\n'
           f'debug set_bp {s["isr"]} {{}} {{ L "isr $::n {POS}" }}\n'
           f'debug set_bp {s["stop"]} {{}} {{ L "stop $::n {POS}"; '
           'binary scan [debug read_block VRAM 0x1800 768] H* h; L "names $h" }\n')
    w = run(name, PAINT_FRAMES, tcl)
    at_isr = [int(x[1]) for x in w if x[0] == "isr"]
    stop = next(x for x in w if x[0] == "stop")
    names = bytes.fromhex(next(x for x in w if x[0] == "names")[1]).decode("latin1")
    return at_isr, int(stop[1]), names


def paint():
    out = {}
    for name in ("saved", "unsaved"):
        at_isr, cells, names = paint_one(name)
        assert cells == 768
        if name == "saved":
            want = gen17.FIRST * 768
        else:
            want, ch, last = "", gen17.FIRST, 0
            for k, n in enumerate(at_isr + [768]):
                want += ch * (min(n, 768) - last)
                last = min(n, 768)
                ch = chr(ord("0") + k + 1)
        assert names == want, (name, names, want)
        bands = [len(m.group(0)) for m in re.finditer(r"(.)\1*", names)]
        out[name] = {"isr_at": [n for n in at_isr if n < 768], "bands": bands,
                     "chars": "".join(dict.fromkeys(names))}
    shots = msxcap.capture(rom("unsaved"), [PAINT_FRAMES - 1, PAINT_FRAMES], CAPS, "unsaved_f")
    a, b = (Image.open(shots[n]).convert("RGB") for n in (PAINT_FRAMES - 1, PAINT_FRAMES))
    assert a.tobytes() == b.tobytes()
    shots[PAINT_FRAMES - 1].unlink()
    out["frame"] = PAINT_FRAMES
    return out


# ---------------------------------------------------------------- late
def late():
    s = sym("late")
    tcl = (f'debug probe set_bp VDP.IRQvertical {{}} {{ L "irq [debug probe read VDP.IRQvertical] {POS}" }}\n'
           f'debug probe set_bp z80.acceptIRQ {{}} {{ L "acc {POS} [reg pc]" }}\n'
           + "".join(f'set ::b{k} [debug set_bp {s[k]} {{}} {{ L "{k} {POS} [peek {RESULTS}]"; '
                     f'debug remove_bp $::b{k} }}]\n' for k in ("l1", "l2", "l3", "stop")))
    w = run("late", 12, tcl)
    T = lambda f, c: f * gen17.FRAME_T + c / VDP_PER_T            # T-states from frame 0
    ups = [T(*at(x[2:4])) for x in w if x[0] == "irq" and x[1] == "1"]
    accs = [(T(*at(x[1:3])), int(x[3])) for x in w if x[0] == "acc"]
    eis = {x[0]: (T(*at(x[1:3])), int(x[3])) for x in w if x[0] in ("l1", "l2", "l3", "stop")}
    rows = []
    for k in ("l1", "l2", "l3"):
        t_ei, ticks = eis[k]
        prev = max(a for a, _ in accs if a < t_ei)          # the interrupt before the DI
        # frames whose signal came while the interrupts were off: the VDP's line
        # goes up once and stays up, so the probe sees only the first of them
        sig = ups[0] % gen17.FRAME_T
        signals = sum(1 for f in range(int(prev // gen17.FRAME_T), int(t_ei // gen17.FRAME_T) + 1)
                      if prev < f * gen17.FRAME_T + sig < t_ei)
        nxt = next(a for a in accs if a[0] > t_ei)
        rows.append({"try": k, "off": round((t_ei - prev) / gen17.FRAME_T, 2), "signals": signals,
                     "after_ei": round(nxt[0] - t_ei, 2), "ret": nxt[1], "ticks_before": ticks})
    assert rows[0]["signals"] == 1 and rows[0]["after_ei"] == 5 + 5        # EI, then one NOP
    assert rows[1]["signals"] == 2 and rows[1]["after_ei"] == 5 + 5
    assert [r["ret"] for r in rows[:2]] == [s["l1"] + 2, s["l2"] + 2]      # after the first NOP
    assert rows[2]["signals"] == 1 and rows[2]["after_ei"] > gen17.FRAME_T / 4      # waited for the next
    ticks = [r["ticks_before"] for r in rows] + [eis["stop"][1]]
    assert ticks == [1, 3, 5, 6], ticks
    return {"rows": rows, "ticks": ticks}


# ---------------------------------------------------------------- iff
def iff():
    s = sym("iff")
    tcl = (f'debug probe set_bp VDP.IRQvertical {{}} {{ L "irq [debug probe read VDP.IRQvertical] {POS}" }}\n'
           f'debug probe set_bp z80.acceptIRQ {{}} {{ L "acc {POS} [reg pc]" }}\n'
           + "".join(f'debug set_bp {s[k]} {{}} {{ L "{k} {POS} [reg iff] [reg f]" }}\n'
                     for k in ("keep", "keep2", "k1", "k2ask", "k2on", "a1", "a2", "a3", "a4")))
    w = run("iff", 8, tcl)
    T = lambda f, c: f * gen17.FRAME_T + c / VDP_PER_T
    ev = [(x[0], T(*at(x[2:4] if x[0] == "irq" else x[1:3])), x) for x in w
          if x[0] in ("irq", "acc", "keep", "keep2", "k1", "k2ask", "k2on", "a1", "a2", "a3", "a4")]
    pv = lambda x: int(x[4]) >> 2 & 1                     # P/V is bit 2 of F
    rows = []
    starts = [(k, t) for k, t, _ in ev if k in ("keep", "keep2")]
    for n, (k, t0) in enumerate(starts):
        after = f"a{n + 1}"
        t_after = next(t for k_, t, _ in ev if k_ == after and t > t0)
        sig = [t for k_, t, x in ev if k_ == "irq" and x[1] == "1" and t0 < t < t_after]
        acc = [x for k_, t, x in ev if k_ == "acc" and t0 < t < t_after]
        answers = [pv(x) for k_, t, x in ev if k_ in ("k1", "k2ask", "k2on") and t0 < t < t_after]
        iff_after = int(next(x for k_, t, x in ev if k_ == after and t > t0)[3]) != 0
        rows.append({"call": k, "signal_after_start": round(sig[0] - t0, 2) if sig else None,
                     "taken_at": int(acc[0][3]) - s[k] if acc else None,
                     "pv": answers, "iff_after": iff_after})
    want = [("keep", None, [1], True), ("keep", None, [0], False), ("keep", 2, [0], False),
            ("keep2", 2, [0, 1], True)]
    assert [(r["call"], r["taken_at"], r["pv"], r["iff_after"]) for r in rows] == want, rows
    assert all(0 < r["signal_after_start"] < 11 for r in rows[2:])      # LD A,I: 11 T-states
    return {"rows": rows}


# ---------------------------------------------------------------- keys
def keys():
    out = {}
    for name in ("nokeys", "chain", "steal"):
        s = sym(name)
        ev = {gen17.KEY_FRAME: "keymatrixdown 8 0x01", gen17.KEY_UP: "keymatrixup 8 0x01",
              0: 'L "j0 [peek16 0xFC9E]"',
              gen17.KEY_FRAMES - 1: f'L "end [peek16 {RESULTS}] [peek {RESULTS + 2}] [peek16 0xFC9E] [reg pc]"'}
        tcl = (COST_TCL if name == "chain" else "") + \
            f'debug set_bp {s["k2"]} {{}} {{ L "k2 {POS} [reg a]" }}\n'
        w = run(name, gen17.KEY_FRAMES, tcl, events=ev)
        f0 = int(w[0][1])
        j0 = int(next(x for x in w if x[0] == "j0")[1])
        end = next(x for x in w if x[0] == "end")
        k2 = next((x for x in w if x[0] == "k2"), None)
        r = {"ticks": int(end[1]), "key": int(end[2]), "jiffy": int(end[3]) - j0,
             "returned": int(k2[1]) - f0 if k2 else None, "pc_end": int(end[4])}
        if name == "chain":
            c = costs(w)
            r["costs"] = sorted({t for _, t, _, _ in c})
        out[name] = r
    n, c, st = out["nokeys"], out["chain"], out["steal"]
    assert n["returned"] is None and n["jiffy"] == 0 and n["ticks"] >= gen17.KEY_FRAMES - 2
    assert c["returned"] == gen17.KEY_FRAME + 1 and c["key"] == 32 and c["jiffy"] == c["ticks"]
    assert st["returned"] is None and st["jiffy"] == 0 and st["ticks"] == c["ticks"]
    return out


# ---------------------------------------------------------------- forgot
FORGOT_FRAMES = 10          # film frame of figure 17.3


def forgot():
    s = sym("forgot")
    tcl = (f'debug set_bp {s["o1"]} {{}} {{ L "o1 {POS}" }}\n'
           f'debug set_bp {s["isr"]} {{}} {{ L "isr {POS} [peek16 {RESULTS}] [peek16 [reg sp]]" }}\n')
    ev = {k: f'L "turns {k} [peek16 {RESULTS}]"' for k in (1, 2, 5, FORGOT_FRAMES)}
    w = run("forgot", FORGOT_FRAMES + 1, tcl, events=ev)
    f0 = int(w[0][1])
    isr = [x for x in w if x[0] == "isr"]
    o1 = [at(x[1:3]) for x in w if x[0] == "o1"]
    turns = {int(x[1]): int(x[2]) for x in w if x[0] == "turns"}
    T = lambda f, c: f * gen17.FRAME_T + c / VDP_PER_T
    times = [T(*at(x[1:3])) for x in isr]
    gaps = sorted({round(b - a, 3) for a, b in zip(times, times[1:])})
    rets = {int(x[4]) for x in isr}
    frozen = {int(x[3]) for x in isr[1:]}
    assert len(rets) == 1 and len(frozen) == 1
    per_frame = {}
    for x in isr:
        per_frame[int(x[1]) - f0] = per_frame.get(int(x[1]) - f0, 0) + 1
    # the model: the routine's price, from its bytes, with the answer and the JP
    code = price(lst_code("forgot", "isr", "ret"))
    period = gen17.T_TAKE[2] + JUMPS["jp"] + sum(t for _, t in code)
    assert gaps == [period], (gaps, period)
    # the photograph: every pixel of the drawn columns the colour of the last
    # change before it; OUT (n),A writes 8 T-states after it starts (chapter 8)
    shots = msxcap.capture(rom("forgot"), [FORGOT_FRAMES], CAPS, "forgot_f")
    frame = f0 + FORGOT_FRAMES
    changes = []
    for k, (f, c) in enumerate(o1):
        t = c // VDP_PER_T
        line, w_ = divmod(t + 8, meas.T_PER_LINE)
        changes.append((f, line, math.ceil(1.5 * w_ - 31), "LIGHT_GREEN" if k % 2 == 0 else "BLACK"))
    before = [ch for ch in changes if ch[0] < frame]
    inside = [ch[1:] for ch in changes if ch[0] == frame]
    px = Image.open(shots[FORGOT_FRAMES]).convert("L").load()
    first = meas.FRAME_LINE_OF_ROW0[EU]
    want, k, checked = before[-1][3], 0, 0
    for y in range(meas.CAPTURE_H):
        for x in range(meas.DRAWN[0], meas.DRAWN[1] + 1):
            while k < len(inside) and inside[k][:2] <= (first + y, x):
                want = inside[k][2]
                k += 1
            seen = "BLACK" if px[x, y] < 90 else "LIGHT_GREEN"
            assert seen == want, (x, y, px[x, y], want)
            checked += 1
    return {"period": period, "code": code, "entries": len(isr), "per_frame": per_frame,
            "turns": turns, "turns_frozen": frozen.pop(), "ret": rets.pop(), "main": s["main"],
            "pixels": checked, "frame": FORGOT_FRAMES, "changes_in_frame": len(inside)}


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


def run_temp(name, text, frames, tcl, events=None):
    import shutil
    tmp = build_temp(name, text)
    try:
        s = probe.sym(tmp / f"{name}.sym")
        lines = msxcap.run_tcl(tmp / f"{name}.rom", frames, tcl(s) if callable(tcl) else tcl,
                               events=events)
        return s, [l.split() for l in lines]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def answers():
    out = {}
    # 1: the table at $D000, 257 bytes of $D1
    text = gen17.modes().replace("modes.rom", "q1.rom").replace(
        f"IM2_TABLE EQU ${gen17.TABLE:04X}", "IM2_TABLE EQU $D000").replace(
        f"IM2_JUMP  EQU ${gen17.VECTOR:04X}", "IM2_JUMP  EQU $D1D1")
    s, w = run_temp("q1", text, 4, lambda s: (
        f'debug set_bp {s["e2"]} {{}} {{ set ::armed 1 }}\n'
        f'debug set_watchpoint read_mem {{0xD000 0xD100}} {{}} '
        f'{{ if {{[info exists ::armed]}} {{ L "rd $::wp_last_address" }} }}\n'
        f'debug set_bp 0xD1D1 {{}} {{ L "vec" }}\n'))
    out["q1"] = {"reads": [int(x[1]) for x in w if x[0] == "rd"],
                 "vector": any(x[0] == "vec" for x in w)}
    assert out["q1"] == {"reads": [0xD0FF, 0xD100], "vector": True}, out["q1"]
    # 2: late.asm with LD A,(nn) after its first EI
    text = gen17.late().replace("late.rom", "q2.rom").replace(
        "l1:     ei\n        nop\n", "l1:     ei\n        ld a, (RESULTS + 8)\n", 1)
    assert "ld a, (RESULTS + 8)" in text
    s, w = run_temp("q2", text, 6, lambda s: (
        f'set ::b [debug set_bp {s["l1"]} {{}} {{ L "ei [machine_info time]"; debug remove_bp $::b }}]\n'
        f'debug set_bp {s["l1"]} {{}} {{ set ::armed 1 }}\n'
        f'debug probe set_bp z80.acceptIRQ {{}} {{ if {{[info exists ::armed]}} '
        f'{{ L "acc [machine_info time] [reg pc]"; unset ::armed }} }}\n'))
    ei = float(next(x for x in w if x[0] == "ei")[1])
    acc = next(x for x in w if x[0] == "acc")
    out["q2"] = {"after_ei": round((float(acc[1]) - ei) * CLOCK), "ret": int(acc[2]) - s["l1"]}
    assert out["q2"] == {"after_ei": 5 + 14, "ret": 1 + 3}, out["q2"]
    # 6: a routine in H.KEYI that reads the status
    text = head_q6()
    ev = {gen17.KEY_FRAME: "keymatrixdown 8 0x01", gen17.KEY_UP: "keymatrixup 8 0x01",
          0: 'L "j0 [peek16 0xFC9E]"', gen17.KEY_FRAMES - 1: f'L "end [peek {RESULTS}] [peek16 0xFC9E]"'}
    s, w = run_temp("q6", text, gen17.KEY_FRAMES, "", events=ev)
    j0 = int(next(x for x in w if x[0] == "j0")[1])
    end = next(x for x in w if x[0] == "end")
    out["q6"] = {"key": int(end[1]), "jiffy": int(end[2]) - j0}
    assert out["q6"] == {"key": 255, "jiffy": 0}, out["q6"]
    return out


def head_q6():
    return gen17.head("q6", "a routine in H.KEYI that reads the status") + RESULTS_EQU + """init:   di
        ld sp, SYS_AREA
        ld a, $FF
        ld (RESULTS), a
        ld hl, keyi
        ld (H_KEYI + 1), hl
        ld a, $C3
        ld (H_KEYI), a
        im 1
        in a, (VDP_CTRL)
        ei
        call CHGET
        ld (RESULTS), a
stop:   jr stop

keyi:   in a, (VDP_CTRL)        ; the status, read before the BIOS reads it
        ret
""" + gen17.CART_END


RESULTS_EQU = "RESULTS EQU RAM_START\n"


# ---------------------------------------------------------------- openmsx
OPENMSX_SECTIONS = ["session", "signal", "modes", "bios", "timi", "clock", "paint", "late", "iff",
                    "keys", "forgot", "answers"]


def openmsx():
    if not versions.builds():
        return {"skipped": "OPENMSX_BUILDS not set"}
    return versions.every_build(["ch17"], OPENMSX_SECTIONS)


SECTIONS = {"session": session, "signal": signal, "modes": modes, "bios": bios, "timi": timi,
            "clock": clock, "paint": paint, "late": late, "iff": iff, "keys": keys,
            "forgot": forgot, "answers": answers, "openmsx": openmsx}


def main(names=()):
    CAPS.mkdir(exist_ok=True)
    path = HERE / "meas17.json"
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
