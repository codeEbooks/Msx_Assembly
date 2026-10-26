#!/usr/bin/env python3
"""meas30.py -- fonts and text, measured.

    python3 gen30.py && ./build.sh && python3 meas30.py
                                  python3 meas30.py bios page     only these

Every photograph must be vdpscreen.py's drawing of the VRAM and the registers
the debugger reads for it, and the shapes, colours and names gen30.py's model
of them, vram_of(), byte for byte; the BIOS's shapes in the model come from
the ROM file of the machine, not from the program.

  bios      bios.rom: the address at $0004, the 256 shapes copied, both
            machines' sets (figure 30.1)
  own       own.rom: the set of shapes30.py (figure 30.2)
  page      page.rom: the page printed, then a film of the score (figure 30.3)
  binary    binary.rom: five numbers kept in binary, printed by digits
  bar       WHERE IT BREAKS: bar.rom against the line as the 50 Hz machine
            shows it (figure 30.4)
  prices    walk.py's T-states for the copies, the page, at, print, show and
            step, against the debugger's
  answers   the workshop, tried (for Appendix I)
  openmsx   all of it again with every other build (tools/versions.py)
"""
import json
import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "ch20"))
import meas        # noqa: E402
import msxcap      # noqa: E402
import probe as dbg  # noqa: E402
import screentext  # noqa: E402
import versions    # noqa: E402
import vdpslots    # noqa: E402  (chapter 20)
sys.path.insert(0, str(HERE))
import gen30       # noqa: E402
for mod in ("vdpscreen", "walk"):
    sys.modules.pop(mod, None)
import vdpscreen   # noqa: E402
import walk        # noqa: E402  (chapter 28's, with DAA)

assert Path(vdpscreen.__file__).parent == HERE and Path(walk.__file__).parent == HERE

CAPS = HERE / "captures"
EU, JP = gen30.EU, gen30.JP
TAG = {EU: "eu", JP: "jp"}
CLOCK = 3579545
POS = "[machine_info VDP_frame_count] [machine_info VDP_cycle_in_frame] [machine_info time]"
REGS = " ".join(f"[debug read {{VDP regs}} {i}]" for i in range(8))
VRAM = 'binary scan [debug read_block {VRAM} 0 16384] H* h; L "vram $h"'
F0 = 'L "f0 [machine_info VDP_frame_count]"\n'
TOO_FAST = ('proc ::toofast_cb {args} { L "fast [machine_info time]" }\n'
            'set VDP.too_fast_vram_access_callback ::toofast_cb\n')

PALETTE = [tuple(c) for c in json.loads((REPO / "ch01" / "meas01.json").read_text())["palette"]["rgb"]]
CODE = {rgb: n for n, rgb in enumerate(PALETTE) if n}


def rom(name):
    return HERE / f"{name}.rom"


def sym(name):
    return dbg.sym(HERE / f"{name}.sym")


def codes(png):
    im = Image.open(png).convert("RGB")
    px = im.load()
    return [[CODE.get(px[x, y]) for x in range(im.width)] for y in range(im.height)]


def against(model, photo, backdrop):
    bad = 0
    for y in range(240):
        for x in range(meas.DRAWN[0], meas.DRAWN[1] + 1):
            px, py = x - meas.PAPER_X0, y - meas.PAPER_Y0
            want = model[py][px] if 0 <= px < 256 and 0 <= py < 192 else backdrop
            bad += photo[y][x] != want
    return bad


def paper_of(photo):
    return [[photo[meas.PAPER_Y0 + y][meas.PAPER_X0 + x] for x in range(256)] for y in range(192)]


def once(addr, body, tag):
    return f'set ::{tag} [debug set_bp {addr} {{}} {{ {body}; debug remove_bp $::{tag} }}]\n'


def run(name, frames, tcl, machine):
    lines = msxcap.run_tcl(rom(name), frames, F0 + TOO_FAST + tcl, machine=machine)
    w = [l.split() for l in lines]
    assert not [x for x in w if x[0] == "fast"], (name, machine, "an access too soon")
    return w


SPANS = [(0, 0x800), (0x1800, 0x1B01), (0x2000, 0x2800)]   # shapes, names and sprites' end, colours


def tables_differ(vram, want):
    return sum(1 for a, b in SPANS for i in range(a, b) if vram[i] != want[i])


def cells_differ(a, b, cells):
    """the pixels of two pictures of the paper that differ, in these cells (row, column)"""
    return sum(1 for r, c in cells for y in range(8 * r, 8 * r + 8) for x in range(8 * c, 8 * c + 8)
               if a[y][x] != b[y][x])


# ---------------------------------------------------------------- a still
def still(name, machine, labels=("c0", "c1")):
    """the program run to done: the registers, the VRAM, the RAM's first
    bytes, the T-states between two labels, and its photograph"""
    s = sym(name)
    tcl = "".join(once(s[l], f'L "{l} {POS}"', l) for l in labels)
    tcl += once(s["done"], f'L "regs {REGS}"; {VRAM}; '
                'binary scan [debug read_block memory 0xC100 8] H* r; L "ram $r"; '   # VARS
                f'L "done {POS}"', "d")
    w = run(name, 40, tcl, machine)
    f0 = int(next(x for x in w if x[0] == "f0")[1])
    regs = [int(v) for v in next(x for x in w if x[0] == "regs")[1:]]
    vram = bytes.fromhex(next(x for x in w if x[0] == "vram")[1])
    ram = bytes.fromhex(next(x for x in w if x[0] == "ram")[1])
    at = {x[0]: float(x[3]) for x in w if x[0] in labels}
    took = round((at[labels[1]] - at[labels[0]]) * CLOCK)
    shot = int(next(x for x in w if x[0] == "done")[1]) - f0 + 2
    png = msxcap.capture(rom(name), [shot], CAPS, f"{name}_{TAG[machine]}_f", machine=machine)[shot]
    photo = codes(png)
    assert regs == gen30.REGS, regs
    assert against(vdpscreen.draw(vram, regs), photo, regs[7] & 15) == 0, (name, machine)
    return {"vram": vram, "ram": ram, "photo": photo, "shot": shot, "took": took}


def bios():
    out, papers = {}, {}
    for m in (EU, JP):
        st = still("bios", m)
        shapes, at = screentext.font(m)
        assert st["ram"][0] | st["ram"][1] << 8 == at
        assert tables_differ(st["vram"], gen30.vram_of("bios", m)) == 0, m
        papers[m] = paper_of(st["photo"])
        out[TAG[m]] = {"cgtabl": at, "copy": st["took"], "shot": st["shot"]}
    eu, jp = screentext.font(EU)[0], screentext.font(JP)[0]
    r0, c0 = gen30.GRID
    grid = [(r0 + r, c0 + c) for r in range(16) for c in range(16)]
    out["differ"] = {"codes": sum(eu[c] != jp[c] for c in range(256)),
                     "codes_32_126": sum(eu[c] != jp[c] for c in range(32, 127)),
                     "codes_128_255": sum(eu[c] != jp[c] for c in range(128, 256)),
                     "same": [c for c in range(256) if eu[c] == jp[c]],
                     "pixels": cells_differ(papers[EU], papers[JP], grid)}
    out["ink"] = {TAG[m]: sum(bin(b).count("1") for s in screentext.font(m)[0] for b in s)
                  for m in (EU, JP)}
    return out


def own():
    out, papers = {}, {}
    for m in (EU, JP):
        st = still("own", m)
        assert tables_differ(st["vram"], gen30.vram_of("own", m)) == 0, m
        papers[m] = paper_of(st["photo"])
        out[TAG[m]] = {"copy": st["took"], "shot": st["shot"]}
    out["eu_jp_pixels"] = sum(1 for y in range(192) for x in range(256) if papers[EU][y][x] != papers[JP][y][x])
    ink = [sum(bin(b).count("1") for b in gen30.FONT[8 * k:8 * k + 8]) for k in range(96)]
    out["ink"] = sum(ink)
    used = 0
    for b in gen30.FONT:
        used |= b
    out["columns"] = [i for i in range(8) if used & 0x80 >> i]
    return out


def binary():
    out = {}
    labels = [l for i in range(len(gen30.NUMBERS)) for l in (f"n{i}", f"n{i}e")]
    for m in (EU, JP):
        s = sym("binary")
        tcl = "".join(once(s[l], f'L "{l} {POS}"', l) for l in labels)
        tcl += once(s["done"], f'L "regs {REGS}"; {VRAM}; L "done {POS}"', "d")
        w = run("binary", 40, tcl, m)
        f0 = int(next(x for x in w if x[0] == "f0")[1])
        regs = [int(v) for v in next(x for x in w if x[0] == "regs")[1:]]
        vram = bytes.fromhex(next(x for x in w if x[0] == "vram")[1])
        at = {x[0]: float(x[3]) for x in w if x[0] in labels}
        shot = int(next(x for x in w if x[0] == "done")[1]) - f0 + 2
        png = msxcap.capture(rom("binary"), [shot], CAPS, f"binary_{TAG[m]}_f", machine=m)[shot]
        assert regs == gen30.REGS
        assert against(vdpscreen.draw(vram, regs), codes(png), regs[7] & 15) == 0, m
        assert tables_differ(vram, gen30.vram_of("binary", m)) == 0, m
        out[TAG[m]] = {"shot": shot, "digits": [round((at[f"n{i}e"] - at[f"n{i}"]) * CLOCK)
                                                for i in range(len(gen30.NUMBERS))]}
    out["numbers"] = gen30.NUMBERS
    return out


def bar():
    out, papers = {}, {}
    ideal = vdpscreen.draw(gen30.vram_of("bar", EU), gen30.REGS)
    label = [(gen30.BAR_ROW, 2 + i) for i in range(len(gen30.LABEL))]
    bars = [(gen30.BAR_ROW, gen30.BAR_AT + i) for i in range(gen30.BAR_LEN)]
    for m in (EU, JP):
        st = still("bar", m)
        assert tables_differ(st["vram"], gen30.vram_of("bar", m)) == 0, m
        pp = paper_of(st["photo"])
        papers[m] = pp
        whole = sum(1 for y in range(192) for x in range(256) if pp[y][x] != ideal[y][x])
        out[TAG[m]] = {"shot": st["shot"], "copy": st["took"], "off": whole, "label": cells_differ(pp, ideal, label),
                       "bar": cells_differ(pp, ideal, bars),
                       "bar_ink": sum(1 for r, c in bars for y in range(8 * r, 8 * r + 8)
                                      for x in range(8 * c, 8 * c + 8) if pp[y][x] == gen30.BLACK)}
    return out


# ---------------------------------------------------------------- page
def page(machine_list=(EU, JP)):
    out = {}
    path = list(range(gen30.FRAMES))
    for m in machine_list:
        s = sym("page")
        read = f'L "regs {REGS}"; {VRAM}'
        tcl = (once(s["c0"], f'L "c0 {POS}"', "c0") + once(s["c1"], f'L "c1 {POS}"', "c1") +
               once(s["p0"], f'L "p0 {POS}"', "p0") + once(s["p1"], f'L "p1 {POS}"', "p1") +
               f'debug set_bp {s["m0"]} {{}} {{ {read}; L "a {POS}" }}\n'
               f'debug set_bp {s["m1"]} {{}} {{ L "b {POS}" }}\n'
               f'debug set_bp {s["s1"]} {{}} {{ L "c {POS}" }}\n' +
               once(s["done"], f'{read}; L "end"', "e"))
        w = run("page", len(path) + 40, tcl, m)
        f0 = int(next(x for x in w if x[0] == "f0")[1])
        t = {x[0]: float(x[3]) for x in w if x[0] in ("c0", "c1", "p0", "p1")}
        a_s = [x for x in w if x[0] == "a"]
        b_s = [x for x in w if x[0] == "b"]
        c_s = [x for x in w if x[0] == "c"]
        regs = [[int(v) for v in x[1:]] for x in w if x[0] == "regs"][1:]
        vrams = [bytes.fromhex(x[1]) for x in w if x[0] == "vram"][1:]
        assert len(a_s) == len(b_s) == len(c_s) == len(regs) == len(vrams) == len(path)
        bad = [tables_differ(v, gen30.vram_of("page", m, k)) + (r != gen30.REGS)
               for v, r, k in zip(vrams, regs, path)]
        assert not any(bad), (m, bad[:8])
        frames_at = [int(a[1]) - f0 for a in a_s]
        assert frames_at == list(range(frames_at[0], frames_at[0] + len(path))), m
        show = [round((float(b[3]) - float(a[3])) * CLOCK) for a, b in zip(a_s, b_s)]
        step = [round((float(c[3]) - float(b[3])) * CLOCK) for b, c in zip(b_s, c_s)]
        shots = sorted({f + d for f in frames_at for d in (0, 1, 2)})
        pngs = msxcap.capture(rom("page"), shots, CAPS, f"page_{TAG[m]}_f", machine=m)
        photos = {f: codes(pngs[f]) for f in shots}
        fits = [d for d in (0, 1, 2)
                if all(against(vdpscreen.draw(v, r), photos[f + d], r[7] & 15) == 0
                       for v, r, f in zip(vrams, regs, frames_at))]
        assert 1 in fits, (m, fits)
        for f in shots:
            if f not in {f + 1 for f in frames_at}:
                pngs[f].unlink()
        lines = [int(a[2]) // vdpslots.LINE for a in a_s]
        out[TAG[m]] = {"frames": [f + 1 for f in frames_at], "fits": fits, "show": show,
                       "step": step, "lines": sorted(set(lines)),
                       "copy": round((t["c1"] - t["c0"]) * CLOCK),
                       "page": round((t["p1"] - t["p0"]) * CLOCK),
                       "scores": [gen30.score_of(k) for k in (path[0], path[-1])]}
    out["chars"] = sum(len(text) for _, _, _, text in gen30.LINES)
    out["lines"] = len(gen30.LINES)
    return out


# ---------------------------------------------------------------- prices
def prices():
    m = json.loads((HERE / "meas30.json").read_text())
    out = {}
    for name in ("bios", "own", "bar"):
        wk = walk.Walk(HERE / name)
        wk.run("init", "c0")
        out[name] = {"copy": wk.run("c0", "c1")}
    wk = walk.Walk(HERE / "page", read_port=lambda port, t: 0x80 if port == 0x99 else 0)
    wk.run("init", "c0")
    out["page"] = {"copy": wk.run("c0", "c1")}
    wk.run("c1", "p0")
    out["page"]["page"] = wk.run("p0", "p1")
    wk.run("p1", "m0")
    shows, steps, scores = [], [], []
    for _ in range(16):
        shows.append(wk.run("m0", "m1"))
        steps.append(wk.run("m1", "s1"))
        sc = wk.mem[0xC100:0xC103].hex()
        scores.append(int(sc))
        wk.run("s1", "m0")
    out["page"].update(show=shows, step=steps)
    assert scores == [gen30.score_of(k + 1) for k in range(16)], scores
    out["at"] = walk.Walk(HERE / "page").call("at", d=gen30.SCORE_ROW, e=2)
    w3 = walk.Walk(HERE / "page")
    text = w3.sym["lines"] + 3                          # the first line's characters
    out["print"] = {"chars": len(gen30.LINES[0][3]),
                    "t": w3.call("print", h=text >> 8, l=text & 255, b=gen30.SECOND)}
    out["digits"] = [walk.Walk(HERE / "binary").call("digits", h=n >> 8, l=n & 255)
                     for n in gen30.NUMBERS]
    for t in ("eu", "jp"):
        assert m["binary"][t]["digits"] == out["digits"], t
        for name in ("bios", "own", "bar"):
            assert m[name][t]["copy"] == out[name]["copy"], (name, t)
        assert m["page"][t]["copy"] == out["page"]["copy"] and m["page"][t]["page"] == out["page"]["page"]
        assert m["page"][t]["show"][:16] == shows and m["page"][t]["step"][:16] == steps
    return out


# ---------------------------------------------------------------- answers
def answers():
    m = json.loads((HERE / "meas30.json").read_text())
    at = m["bios"]["eu"]["cgtabl"]
    out = {}
    # 1: the BIOS's A, code 65: where its eight bytes are
    out["q1"] = {"cgtabl": at, "a": at + 8 * 65}
    # 2: our set sent to pattern 0, not 32: what SCORE 001250 prints as
    text = "SCORE 001250"
    shown = "".join(chr(ord(ch) + 32) if ord(ch) + 32 < 128 else "?" for ch in text)
    out["q2"] = {"text": text, "shown": shown}
    # 3: print's characters in the lines a 60 Hz frame does not draw
    out["q3"] = {"per": 56, "jp": 15960 // 56, "eu": 27588 // 56}
    # 4: three bytes of BCD, and the same three as a binary number
    out["q4"] = {"bcd": 999999, "binary": 2 ** 24 - 1}
    # 5: the sets in the text mode's six columns: the pixels in columns 6 and 7
    cut = {}
    for mach, tag in ((EU, "eu"), (JP, "jp")):
        shapes, _ = screentext.font(mach)
        cut[tag] = [chr(c) for c in range(32, 127) if any(r & 3 for r in shapes[c])]
    cut["own"] = [chr(32 + k) for k in range(96) if any(b & 3 for b in gen30.FONT[8 * k:8 * k + 8])]
    out["q5"] = cut
    return out


# ---------------------------------------------------------------- openmsx
OPENMSX_SECTIONS = ["bios", "own", "page", "binary", "bar"]


def openmsx():
    if not versions.builds():
        return {"skipped": "OPENMSX_BUILDS not set"}
    return versions.every_build(["ch30"], OPENMSX_SECTIONS)


SECTIONS = {"bios": bios, "own": own, "page": page, "binary": binary, "bar": bar, "prices": prices,
            "answers": answers, "openmsx": openmsx}


def main(names=()):
    CAPS.mkdir(exist_ok=True)
    path = HERE / "meas30.json"
    m = json.loads(path.read_text()) if names and path.exists() else {}
    for name in names or SECTIONS:
        print(name, flush=True)
        m[name] = SECTIONS[name]()
        m = {k: m[k] for k in SECTIONS if k in m}
        path.write_text(json.dumps(m, indent=1) + "\n")
    return m


if __name__ == "__main__":
    main(sys.argv[1:])
