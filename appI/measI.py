#!/usr/bin/env python3
"""measI.py -- Appendix I's measurements: every number of the Workshops'
answers, found again or measured here.

    python3 measI.py [step ...] [chNN ...]

    probes    the programs of genI.py: the price and the R of every
              instruction an answer prices (prices.rom, against Zilog's
              price and one T-state for each M1); chapter 1's byte 4,100,
              ball at x = 120 (and chapter 1's own at 124, counted the same
              way), sprite 0 at Y = 208 and stripe 244 T-states late;
              chapter 2's two sums and two LDs; chapter 3's keyboard with Q
              and W held; chapter 4's two scripts, their last lines, and
              check.asm next to msx.inc renamed MSX.INC; and the code of
              solutions.rom, run with inputs known
    chapters  the measuring program of each chapter an answer draws on, run
              again in a copy of its folder without its results (no
              meas*.json, no captures, no shots; the copy's neighbours are
              links to the repository's other folders, which the programs
              read and do not write), with the steps that measure what the
              answers print and the steps those need first, in the order of
              the program's own table; then every value the appendix takes
              from it is compared with the one the chapter delivered

Chapter numbers after the steps limit "chapters" to those folders, and
"probes" to those chapters' probes. Writes measI.json, and captures/ for
the probes' photographs.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
RESULTS = HERE / "measI.json"
CAPS = HERE / "captures"
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(HERE))
sys.dont_write_bytecode = True
import meas        # noqa: E402
import msxcap      # noqa: E402
import probe       # noqa: E402
import genI        # noqa: E402

CLOCK = probe.CLOCK
EU, JP = "MSXBOOK_EU16", "MSXBOOK_JP16"
PX, PY = 32, 24                          # the paper's top left pixel in a capture (chapter 1)


def load():
    return json.loads(RESULTS.read_text()) if RESULTS.exists() else {}


def save(res):
    RESULTS.write_text(json.dumps(res, indent=1, sort_keys=True) + "\n")


# ---------------------------------------------------------------- probes
# Zilog's T-states and the M1s of each case of prices.asm: the MSX adds a
# T-state to every M1 (chapter 14). (Zilog, M1s)
MODEL = {
    "nop": (4, 1), "ld_a_n": (7, 1), "ld_b_n": (7, 1), "ld_c_n": (7, 1), "ld_de_nn": (10, 1),
    "xor_d": (4, 1), "inc_hl": (6, 1), "exx": (4, 1), "di": (4, 1), "ei": (4, 1),
    "ld_a_mem": (13, 1), "ld_hl_mem": (16, 1), "ld_mem_hl": (16, 1), "push_hl": (11, 1),
    "pop_hl": (10, 1), "ld_a_ix5": (19, 2), "set_1_ix2": (23, 2), "out_n_a": (11, 1),
    "out_c_a": (12, 2), "jp_nn": (10, 1), "jp_nz_taken": (10, 1), "jp_nz_not": (10, 1),
    "jr_taken": (12, 1), "jr_nz_not": (7, 1), "djnz_taken": (13, 1), "djnz_not": (8, 1),
    "ret": (10, 1), "ldi": (16, 2), "ldir_1": (16, 2), "ldir_2": (21 + 16, 4),
    "ldir_256": (255 * 21 + 16, 512), "outi": (16, 2), "otir_1": (16, 2), "otir_2": (21 + 16, 4),
    "otir_128": (127 * 21 + 16, 256), "otir_256": (255 * 21 + 16, 512),
}


def prices():
    s = probe.sym(HERE / "prices.sym")
    names = [p[0] for p in genI.PRICES]
    assert sorted(names) == sorted(MODEL)
    labels = {f"{e}_{n}": s[f"{e}_{n}"] for n in names for e in ("p", "q")}
    got = probe.times(HERE / "prices.rom", labels, frames=3)
    out = {}
    for n in names:
        (t0, r0), (t1, r1) = got[f"p_{n}"][0][:2], got[f"q_{n}"][0][:2]
        out[n] = {"t": round((t1 - t0) * CLOCK), "r": (r1 - r0) % 128}
        z, m1 = MODEL[n]
        assert out[n] == {"t": z + m1, "r": m1 % 128}, (n, out[n], MODEL[n])
    for k, (a, b) in genI.DERIVED.items():
        out[k] = {"t": out[a]["t"] - (out[b]["t"] if b else 0)}
    return out


def bright(p):
    return sum(p) > 600                  # white (15) against everything else, as chapter 1


def photo(rom, frame, tag, **kw):
    CAPS.mkdir(exist_ok=True)
    return msxcap.capture(rom, [frame], CAPS, tag, **kw)[frame]


def white_strips(im):
    """the strips, eight pixels of a line in one byte, with any white in
    them: the strips whose colour byte gives white ink"""
    return sum(1 for y in range(PY, PY + 192) for cx in range(32)
               if any(bright(im.getpixel((PX + 8 * cx + i, y))) for i in range(8)))


def chapter1():
    m01 = genI.chapter_module("ch01", "meas01")
    gen01 = m01.gen01
    im = Image.open(photo(HERE / "bit4100.rom", 30, "bit4100_f")).convert("RGB")
    lit = [[x - PX, y - PY] for y in range(PY, PY + 192) for x in range(PX, PX + 256)
           if bright(im.getpixel((x, y)))]
    s120 = white_strips(Image.open(photo(HERE / "clash120.rom", 30, "clash120_f")).convert("RGB"))
    s124 = white_strips(Image.open(photo(REPO / "ch01" / "clash_ball.rom", 30,
                                         "clash124_f")).convert("RGB"))
    row = genI.y208_row(gen01)
    vis = m01.balls_visible(photo(HERE / "y208_0.rom", 30, "y208_0_f"), row[1:])
    CAPS.mkdir(exist_ok=True)
    got = msxcap.capture(HERE / "beam_244.rom", range(30, 35), CAPS, "beam_244_f")
    still = all(got[n].read_bytes() == got[30].read_bytes() for n in range(31, 35))
    for n in range(31, 35):
        got[n].unlink()
    im = Image.open(got[30]).convert("RGB")
    hits = [(x, y) for y in range(240) for x in range(320) if bright(im.getpixel((x, y)))]
    rows = sorted({y for _, y in hits})
    return {"byte4100": {"pixels": lit}, "clash120": {"strips": s120}, "clash124": {"strips": s124},
            "y208_first": {"visible": vis},
            "beam244": {"rows": rows, "x_first": min(x for x, y in hits if y == rows[0]),
                        "x_last": max(x for x, y in hits if y == rows[-1]), "pixels": len(hits),
                        "still": still}}


def chapter2():
    s = probe.sym(HERE / "flags.sym")
    v = probe.memory(HERE / "flags.rom", s["stop"], 0xC000, 4, frames=10)
    return {"flags": {"add": {"f": v[0], "a": v[1]}, "sub": {"f": v[2], "a": v[3]}},
            "ld_hl": probe.assemble_lines(["ld hl,$1800", "ld hl,6144"])}


QW = (4, 0x40, 5, 0x10)          # Q: row 4, bit 6; W: row 5, bit 4


def chapter3():
    m03 = genI.chapter_module("ch03", "meas03")
    fr = m03.gen03.KEY_EVENT[0]
    r4, b4, r5, b5 = QW
    CAPS.mkdir(exist_ok=True)
    got = msxcap.capture(REPO / "ch03" / "keys.rom", [fr + 10], CAPS, "keys_qw_f",
                         events={fr: f"keymatrixdown {r4} 0x{b4:02X}\nkeymatrixdown {r5} 0x{b5:02X}"})
    rows, _ = m03.keys_read(got[fr + 10])
    return {"qw": rows}


def chapter4():
    home = Path(tempfile.mkdtemp(prefix="measI_home_"))
    try:
        env = {**os.environ, "HOME": str(home)}
        a = subprocess.run([sys.executable, "-B", "install_machines.py"], cwd=REPO, env=env,
                           capture_output=True, text=True, timeout=600)
        last = a.stdout.strip().splitlines()[-1].replace(str(home), "~")
    finally:
        shutil.rmtree(home, ignore_errors=True)
    b = subprocess.run([sys.executable, "-B", "verify.py"], cwd=REPO, capture_output=True,
                       text=True, timeout=3600)
    assert a.returncode == 0 and b.returncode == 0, (a.returncode, b.returncode)
    return {"install_last": last, "verify_last": b.stdout.strip().splitlines()[-1],
            "upper": upper()}


def upper():
    """check.asm next to msx.inc renamed MSX.INC: sjasmplus's first error"""
    tmp = Path(tempfile.mkdtemp(prefix="measI_upper_"))
    try:
        shutil.copy(REPO / "ch04" / "check.asm", tmp)
        shutil.copy(REPO / "ch04" / "msx.inc", tmp / "MSX.INC")
        p = subprocess.run(["sjasmplus", "--nologo", "check.asm"], cwd=tmp,
                           capture_output=True, text=True, timeout=60)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    text = p.stdout + p.stderr
    lines = [l for l in text.splitlines() if "error" in l.lower()]
    return {"rc": p.returncode, "first": lines[0],
            "errors": int(re.search(r"Errors: (\d+)", text).group(1)),
            "labels": sum("Label not found" in l for l in lines),
            "macros": sum("Unrecognized instruction" in l for l in lines)}


def solutions():
    s = probe.sym(HERE / "solutions.sym")
    v = probe.memory(HERE / "solutions.rom", s["stop"], 0xC000, 0x34, frames=10)
    word = lambda i: v[i] | v[i + 1] << 8
    out = {"9.4": [], "15.2": v[genI.RES["15.2"]:genI.RES["15.2"] + 4]}
    for k, (hl, bc) in enumerate(genI.PAIRS_94):
        at = genI.RES["9.4"] + 4 * k
        out["9.4"].append({"hl": hl, "bc": bc, "hl_after": word(at), "f": v[at + 2]})
    at = genI.RES["16.3"]
    out["16.3"] = {"own_pv": v[at] >> 2 & 1, "callix_pv": v[at + 2] >> 2 & 1}
    x, y, dx, dy = genI.BALL_15
    assert out["15.2"] == [(x + dx) & 255, (y + dy) & 255, dx, dy], out["15.2"]
    assert [r["hl_after"] for r in out["9.4"]] == [hl for hl, _ in genI.PAIRS_94]
    assert out["16.3"] == {"own_pv": 1, "callix_pv": 0}
    return out


PROBES = {"prices": prices, "ch01": chapter1, "ch02": chapter2, "ch03": chapter3,
          "solutions": solutions, "ch04": chapter4}


def probes(res, only=()):
    """all the probes; with chapter numbers, only those chapters', the others
    kept as they were"""
    out = dict(res.get("probes", {})) if only else {}
    took = dict(res.get("probe_seconds", {})) if only else {}
    for name, fn in PROBES.items():
        if not only or name in only:
            t0 = time.monotonic()
            out[name] = fn()
            took[name] = round(time.monotonic() - t0)
    res["probes"] = {k: out[k] for k in PROBES}
    res["probe_seconds"] = {k: took[k] for k in PROBES if k in took}
    save(res)
    print("probes", {k: len(v) for k, v in out.items()}, flush=True)


# ---------------------------------------------------------------- chapters
# folder: (steps of its measuring program, the values the appendix prints,
# none inside another). Made from appendixI.py's own list of the keys it reads
# (appendixI.py --keys), the steps those keys are in, and the steps those
# steps read first. "ALL": the program takes no steps and measures everything.
CASES = {
    'ch01': (['ALL'], [
        'beam["16"]',
        'beam["228"]',
        'clash.strips_made_white',
        'fill_order.cells_per_frame',
        'tick.JP.T_per_frame',
    ]),
    'ch03': (['ALL'], [
        'jiffy.isr_T',
        'memmap.test_T',
        'nops.model',
        'page0.page0_di.look_T',
    ]),
    'ch04': (['check', 'case', 'windows'], [
        'case.linux.lines',
        'check.book_eu',
        'check.book_jp',
        'check.default',
        'check.turn_T',
    ]),
    'ch05': (['noend', 'bios', 'answers'], [
        'answers.early',
        'answers.ret',
        'bios.biosway.t_states',
        'noend.bytes_walked',
        'noend.first_ff_frame',
        'noend.page2_frame',
        'noend.t_per_byte',
    ]),
    'ch06': (['stop', 'answers'], [
        'answers.biosway_time',
        'answers.byte_0038',
        'answers.disasm_0038',
        'answers.writes_through_reset',
        'stop.session[0]',
        'stop.session[4]',
    ]),
    'ch07': (['flags', 'flagtest', 'answers'], [
        'answers.dec_hl',
        'answers.dec_l',
        'answers.iy',
        'answers.ld_e_h',
        'flags.rows[9]',
        'flagtest.rows[15]',
    ]),
    'ch08': (['matrix', 'sixteen', 'records', 'selfmod', 'answers'], [
        'answers.q2',
        'answers.q2_t',
        'answers.q3_turn',
        'answers.q5',
        'answers.q6',
        'matrix.eight',
        'matrix.n8',
        'matrix.tried8',
        'records.turn',
        'selfmod.results[0]',
        'selfmod.results[1]',
    ]),
    'ch09': (['add32', 'answers'], [
        'add32.call_t',
        'answers.q1',
        'answers.q2_t',
        'answers.q5',
        'answers.q6',
    ]),
    'ch10': (['scroll', 'answers'], [
        'answers.q1',
        'answers.q2',
        'answers.q4_disagree',
        'answers.q6',
        'scroll.call_t',
    ]),
    'ch11': (['table', 'answers'], [
        'answers.q2',
        'answers.q4',
        'answers.q5',
        'answers.q6',
        'table.rows',
        'table.step',
    ]),
    'ch12': (['calls', 'keep', 'frame', 'fill', 'fillall', 'answers'], [
        'answers.q1',
        'answers.q5',
        'calls.returns',
        'calls.sp',
        'calls.words',
        'fillall.deepest',
        'fillall.stack_bytes',
        'keep.caller',
    ]),
    'ch13': (['qsmul', 'answers'], [
        'answers.q1',
        'answers.q3',
        'answers.q6',
        'qsmul.after_511',
    ]),
    'ch14': (['all', 'price', 'answers'], [
        'answers.q1',
        'answers.q2',
        'answers.q3',
        'answers.q4',
        'answers.q5',
        'answers.q6',
    ]),
    'ch15': (['macro', 'rows', 'picture', 'answers'], [
        'answers.q1',
        'answers.q3',
        'answers.q4',
        'answers.q5',
        'answers.q6',
        'rows.end',
        'rows.highs',
        'rows.lines',
    ]),
    'ch16': (['jump', 'session', 'print', 'answers'], [
        'answers.q1',
        'answers.q4',
        'answers.q5',
        'jump.report_ports',
        'jump.stubs',
        'print.per_line',
        'session.wrtvdp.session[1]',
    ]),
    'ch17': (['signal', 'modes', 'bios', 'timi', 'clock', 'iff', 'keys', 'answers'], [
        'answers.q1',
        'answers.q2',
        'answers.q6',
        'bios.kinds',
        'bios.plain',
        'bios.with_key',
        'clock.code',
        'keys.chain.costs',
        'modes.bus',
    ]),
    'ch18': (['lines', 'ruler', 'drift', 'seconds', 'answers'], [
        'answers.q2',
        'answers.q4',
        'lines.MSXBOOK_EU16.paper_line',
        'lines.MSXBOOK_JP16.paper_line',
        'ruler.per_line',
        'ruler.step',
        'seconds.MSXBOOK_EU16',
        'seconds.MSXBOOK_JP16',
    ]),
    'ch19': (['ports', 'regs', 'address', 'status', 'split', 'fixed', 'answers'], [
        'answers.q1',
        'answers.q2',
        'answers.q4',
        'answers.q5',
        'fixed.at.t',
        'fixed.hits',
        'ports.per_byte.out_c',
        'ports.per_byte.out_n',
        'regs.r0',
        'split.at.t',
        'status.MSXBOOK_EU16.frames',
        'status.MSXBOOK_EU16.turn',
        'status.MSXBOOK_JP16.turn',
    ]),
    'ch20': (['beat', 'probe', 'blank', 'window', 'page', 'answers'], [
        'answers.free.MSXBOOK_EU16.t',
        'answers.free.MSXBOOK_JP16.t',
        'answers.q1',
        'answers.q2',
        'answers.q4',
        'blank.MSXBOOK_EU16["23"]',
        'blank.MSXBOOK_JP16["23"]',
        'page.otir',
        'page.outi',
        'probe.MSXBOOK_EU16.by_gap',
        'probe.MSXBOOK_JP16.by_gap',
        'window.MSXBOOK_EU16',
        'window.MSXBOOK_JP16',
    ]),
    'ch21': (['keep', 'bios', 'bits', 'answers'], [
        'answers.q1',
        'answers.q2',
        'answers.q3',
        'answers.q4',
        'answers.q5',
        'answers.q6',
        'bits.eu[4]',
        'bits.jp[4]',
        'keep.kept',
    ]),
    'ch22': (['bytes', 'colours', 'diag', 'tiles', 'masks', 'leak', 'answers'], [
        'answers.q1',
        'answers.q2',
        'answers.q3',
        'answers.q4',
        'answers.q5',
        'answers.q6',
        'diag.eu.vaddr_t',
        'diag.priced.vaddr_call',
        'leak.eu.m3',
        'tiles.eu.tiles1.reads',
        'tiles.eu.tiles1.regs',
    ]),
    'ch23': (['ways', 'answers'], [
        'answers.q1',
        'answers.q2',
        'answers.q3',
        'answers.q4',
        'answers.q5',
        'ways.oneink.eu.cost',
        'ways.sprite.eu.cost',
    ]),
    'ch24': (['meta', 'copies', 'prices', 'answers'], [
        'answers.q1',
        'answers.q2',
        'answers.q3',
        'answers.q4',
        'answers.q5',
        'copies.full.eu',
        'copies.full.jp',
        'meta.bytes',
        'prices.dirty.a',
        'prices.dirty.b',
    ]),
    'ch25': (['cost', 'fan', 'buffer', 'answers'], [
        'answers.q1',
        'answers.q2',
        'answers.q4',
        'fan.fan.eu.read_margin',
        'fan.tight.eu.read_margin',
        'fan.tight.jp.read_margin',
    ]),
    'ch26': (['rows', 'herd', 'answers'], [
        'answers.q1',
        'answers.q2',
        'answers.q3',
        'answers.q4',
        'answers.q5',
        'answers.q6',
    ]),
    'ch27': (['status', 'answers'], [
        'answers.q1',
        'answers.q2',
        'answers.q3',
    ]),
    'ch28': (['walk', 'swarm', 'cross', 'answers'], [
        'answers.q1',
        'answers.q2',
        'answers.q3',
        'answers.q4',
        'answers.q5',
    ]),
    'ch29': (['coarse', 'sets', 'pairs', 'vertical', 'answers'], [
        'answers.q1',
        'answers.q2',
        'answers.q3',
        'answers.q4',
        'answers.q5',
        'coarse.jp.show',
        'pairs.eu.step',
    ]),
    'ch30': (['bios', 'own', 'binary', 'answers'], [
        'answers.q1',
        'answers.q2',
        'answers.q3',
        'answers.q4',
        'answers.q5',
    ]),
    'ch31': (['blank', 'otir', 'chain', 'paper', 'any', 'fill', 'irq', 'double', 'fixed', 'prices', 'answers'], [
        'answers.q1',
        'answers.q2',
        'answers.q3',
        'answers.q4',
        'answers.q5',
        'answers.q6',
        'answers.q7',
        'answers.q8',
        'answers.q9',
        'double.jp.write',
        'fixed.jp',
        'irq.halt.eu.isr_to_burst',
        'prices.blank',
        'prices.chain128',
        'prices.loop128',
    ]),
    'ch32': (['poll', 'fifth', 'steady', 'split', 'crowd', 'prices', 'answers'], [
        'answers.q1',
        'answers.q10',
        'answers.q11',
        'answers.q2',
        'answers.q3',
        'answers.q4',
        'answers.q5',
        'answers.q6',
        'answers.q7',
        'answers.q8',
        'answers.q9',
        'poll.eu.step',
        'poll.jp.step',
        'steady.eu.step',
        'steady.jp.step',
    ]),
    'ch33': (['order', 'nocount', 'edge', 'speed', 'first', 'prices', 'answers'], [
        'answers.q1',
        'answers.q11',
        'answers.q12',
        'answers.q2',
        'answers.q3',
        'answers.q4',
        'answers.q5',
        'answers.q6',
        'answers.q7',
        'answers.q8',
        'answers.q9',
        'nocount.jp.moved',
        'order.jp.moved',
        'prices.isr',
    ]),
    'ch34': (['matrix', 'legend', 'snsmat', 'define', 'rowonly', 'prices', 'answers'], [
        'answers.q1',
        'answers.q10',
        'answers.q11',
        'answers.q2',
        'answers.q3',
        'answers.q4',
        'answers.q5',
        'answers.q6',
        'answers.q7',
        'answers.q8',
        'answers.q9',
    ]),
    'ch35': (['sticks', 'gtstck', 'pins', 'players', 'leftover', 'prices', 'answers'], [
        'answers.q1',
        'answers.q10',
        'answers.q2',
        'answers.q3',
        'answers.q4',
        'answers.q5',
        'answers.q6',
        'answers.q7',
        'answers.q8',
        'answers.q9',
    ]),
    'ch36': (['levels', 'tones', 'noise', 'env', 'photos', 'mixer', 'prices', 'answers'], [
        'answers.q1',
        'answers.q10',
        'answers.q11',
        'answers.q12',
        'answers.q2',
        'answers.q3',
        'answers.q4',
        'answers.q5',
        'answers.q6',
        'answers.q7',
        'answers.q8',
        'answers.q9',
    ]),
    'ch37': (['bytes', 'writes', 'walk', 'vgm', 'pace', 'effects', 'latch', 'answers'], [
        'answers.q1',
        'answers.q2',
        'answers.q3_owed0',
        'answers.q3_owed51',
        'answers.q4',
        'answers.q5',
        'answers.q6',
        'answers.q7',
        'answers.q9',
        'effects.requests',
        'pace.tune.eu.seconds',
        'walk.effects.eu.isr_max',
        'walk.tune.eu.isr_max',
        'walk.tune.jp.isr_max',
    ]),
    'ch38': (['pages', 'carts', 'enaslt', 'prices', 'breaks', 'answers'], [
        'answers.q1',
        'answers.q10',
        'answers.q2',
        'answers.q3',
        'answers.q4',
        'answers.q5',
        'answers.q6',
        'answers.q7',
        'answers.q8',
        'answers.q9',
    ]),
    'ch39': (['walls', 'flags', 'shapes', 'pairs', 'prices', 'answers'], [
        'answers.q1',
        'answers.q10',
        'answers.q2',
        'answers.q3',
        'answers.q4',
        'answers.q5',
        'answers.q6',
        'answers.q7',
        'answers.q8',
        'answers.q9',
    ]),
    'ch40': (['films', 'prices', 'answers'], [
        'answers.q1',
        'answers.q2',
        'answers.q3',
        'answers.q4',
        'answers.q5',
        'answers.q6',
    ]),
    'ch41': (['rreg', 'lcg', 'xorshift', 'rows', 'states', 'prices', 'answers'], [
        'answers.q1',
        'answers.q2',
        'answers.q3',
        'answers.q4',
        'answers.q5',
        'answers.q6',
        'prices.rowrej',
        'rows.took.once',
    ]),
    'ch42': (['films', 'prices', 'answers'], [
        'answers.q1',
        'answers.q2',
        'answers.q3',
        'answers.q4',
        'answers.q5',
        'answers.q6',
        'prices',
    ]),
    'ch43': (['films', 'answers'], [
        'answers.q1',
        'answers.q2',
        'answers.q3',
        'answers.q4',
        'answers.q5',
        'answers.q6',
        'films.game.eu.events',
        'films.game.eu.summary.to_paper',
        'films.game.jp.rows[815].halt',
        'films.game.jp.rows[896].halt',
        'films.game.jp.summary.states.PLAY.halt',
        'films.game.jp.summary.to_paper',
    ]),
    'ch44': (['films', 'machines', 'answers'], [
        'answers.q1',
        'answers.q2',
        'answers.q3',
        'answers.q4',
        'films.game.eu.summary.halt_max',
        'films.game.eu.summary.left',
        'films.game.jp.summary.halt_max',
        'films.game.jp.summary.left',
        'machines.MSXBOOK_EU8',
    ]),
    'ch45': (['films', 'prices', 'answers'], [
        'answers.q1',
        'answers.q2',
        'answers.q3',
        'answers.q4',
        'answers.q5',
        'answers.q6',
        'prices.visit_new',
        'prices.visit_old',
    ]),
    'ch46': (['films', 'answers'], [
        'answers.q1',
        'answers.q2',
        'answers.q3',
        'answers.q4',
        'answers.q5',
        'answers.q6',
    ]),
    'ch47': (['films', 'prices', 'answers'], [
        'answers.q1',
        'answers.q2',
        'answers.q3',
        'answers.q4',
        'answers.q5',
        'answers.q6',
        'prices.blank',
        'prices.cave_sends["shift 0"]',
        'prices.window',
    ]),
    'ch48': (['films', 'mappers', 'answers'], [
        'answers.q1',
        'answers.q2',
        'answers.q3',
        'answers.q4',
        'answers.q5',
        'films.long.jp.summary.halt_max',
    ]),
    'ch49': (['quality', 'prices', 'answers'], [
        'answers.q1',
        'answers.q2',
        'answers.q3',
        'answers.q4',
        'answers.q5',
    ]),
    'ch50': (['scope', 'load', 'disk', 'answers'], [
        'answers.q1',
        'answers.q2',
        'answers.q3',
        'answers.q4',
        'answers.q5',
    ]),
    'ch51': (['machines', 'which', 'blind', 'games', 'answers'], [
        'answers.q1',
        'answers.q2',
        'answers.q3',
        'answers.q5',
        'which.C-BIOS_MSX2_EU.strip_grey',
        'which.MSXBOOK_EU16.strip_grey',
    ]),
    'ch52': (['films', 'prices', 'count', 'answers'], [
        'answers.q1',
        'answers.q2',
        'answers.q3',
        'answers.q4',
        'answers.q5',
        'count.most',
    ]),
    'ch53': (['rooms', 'answers'], [
        'answers.q1',
        'answers.q2',
        'answers.q3',
        'answers.q4',
    ]),
    'ch54': (['films', 'demo', 'answers'], [
        'answers.q1',
        'answers.q2',
        'answers.q3',
        'answers.q4',
    ]),
    'ch55': (['runs', 'answers'], [
        'answers.q1',
        'answers.q2',
        'answers.q3',
        'answers.q4',
    ]),
    'ch56': (['answers'], [
        'answers.q1',
        'answers.q2',
        'answers.q3',
        'answers.q4',
    ]),
}


def get(d, path):
    """the value at PATH in D: names joined by dots, [n] and ["key"]"""
    for name, sub in re.findall(r'(?:^|\.)([^.\[\]]+)|\[("[^"]*"|-?\d+)\]', path):
        if name:
            d = d[name]
        else:
            d = d[json.loads(sub)] if sub.startswith('"') else d[int(sub)]
    return d


def short(v):
    """a value as the json keeps it: itself if short, else its length and
    SHA-256"""
    text = json.dumps(v, sort_keys=True)
    return v if len(text) <= 200 else {"json_bytes": len(text),
                                       "sha256": hashlib.sha256(text.encode()).hexdigest()}


def program_of(folder):
    return sorted((REPO / folder).glob("meas[0-9]*.py"))[0]


MADE = ("captures", "shots")           # what the steps fill, emptied in the copy


def copy_of(folder, work):
    """WORK/FOLDER: the chapter's folder without what its measuring program
    makes (photographs, results) and without compiled Python, with empty
    captures/ and shots/ for it to fill; WORK's other entries point at the
    repository's"""
    for p in REPO.iterdir():
        if p.name != folder:
            (work / p.name).symlink_to(p)
    dst = work / folder
    shutil.copytree(REPO / folder, dst, symlinks=True,
                    ignore=shutil.ignore_patterns(*MADE, "__pycache__", "meas[0-9]*.json"))
    (dst / (program_of(folder).stem + ".json")).write_text("{}\n")   # some add their steps to one
    for d in MADE:                      # empty, whether the repository has them or not
        (dst / d).mkdir(exist_ok=True)
    return dst


def fingerprint():
    """every file of the repository but appI's and compiled Python: its size
    and modification time"""
    out = {}
    for p in REPO.rglob("*"):
        if p.is_file() and "__pycache__" not in p.parts and p.parts[len(REPO.parts)] != "appI":
            st = p.stat()
            out[str(p.relative_to(REPO))] = (st.st_size, st.st_mtime_ns)
    return out


def check_cases():
    for folder, (steps, keys) in CASES.items():
        for a in keys:
            for b in keys:
                assert a == b or not (b.startswith(a + ".") or b.startswith(a + "[")), (a, b)


def chapters(res, only=()):
    """each chapter's measuring program again, in a copy, from nothing"""
    check_cases()
    out = res.get("chapters", {})
    env = {k: v for k, v in os.environ.items() if k != "OPENMSX_BUILDS"}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    for folder in sorted(CASES):
        if only and folder not in only:
            continue
        steps, keys = CASES[folder]
        before = fingerprint()
        program = program_of(folder)
        work = Path(tempfile.mkdtemp(prefix="measI-"))
        try:
            dst = copy_of(folder, work)
            t0 = time.monotonic()
            argv = [] if steps == ["ALL"] else steps
            p = subprocess.run([sys.executable, "-B", program.name, *argv], cwd=dst, env=env,
                               stdin=subprocess.DEVNULL, capture_output=True, text=True,
                               timeout=6 * 3600)
            took = round(time.monotonic() - t0)
            made = dst / (program.stem + ".json")
            fresh = json.loads(made.read_text()) if made.exists() else {}
        finally:
            shutil.rmtree(work, ignore_errors=True)
        touched = sorted(k for k, v in fingerprint().items() if before.get(k) != v)
        delivered = json.loads((REPO / folder / (program.stem + ".json")).read_text())
        r = {"steps": steps, "exit": p.returncode, "seconds": took, "differ": [], "values": {},
             "touched": touched}
        for k in keys:
            try:
                now = get(fresh, k)
            except (KeyError, IndexError, TypeError):
                now = "missing"
            if now != get(delivered, k):
                r["differ"].append(k)
            r["values"][k] = short(now)
        out[folder] = r
        print("chapters", folder, "exit", p.returncode, "differ", r["differ"][:5],
              "touched", touched[:5], f"({took} s)", flush=True)
        if p.returncode:
            print(p.stdout[-2000:], p.stderr[-3000:], flush=True)
        res["chapters"] = {k: out[k] for k in sorted(out)}
        save(res)


STEPS = {"probes": probes, "chapters": chapters}


def main(names=()):
    steps = [n for n in names if n in STEPS] or list(STEPS)
    only = [n for n in names if re.fullmatch(r"ch\d\d", n)]
    res = load()
    for s in steps:
        STEPS[s](res, only)


if __name__ == "__main__":
    main(sys.argv[1:])
