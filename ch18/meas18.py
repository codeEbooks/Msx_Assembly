#!/usr/bin/env python3
"""meas18.py -- the frame, mapped and measured.

    python3 gen18.py && ./build.sh && python3 meas18.py
                                  python3 meas18.py lines ruler    only these
                                  python3 meas18.py --missing      those not measured yet

  lines     lines.rom on both machines: every change of colour, a line apart,
            by the debugger; the frame it repeats; and the photograph, every
            border pixel against the model, for every offset of the capture's
            first row: one fits (figure 18.1)
  ruler     ruler.rom: six changes a line, 38 T-states apart, every line of
            the frame; the photograph against the model (figure 18.2)
  paper     paper.rom: the eight names written, one a line, and the paper,
            pixel by pixel, against the staircase (figure 18.3)
  box       box.rom on both machines: the box where the map aims it, every
            pixel (figure 18.5)
  drift     f71363-f71365 and f59735-f59737: the stripe in twelve frames of
            each film, and the frame lengths that put it there (figure 18.4)
  wrong     WHERE IT BREAKS: wrong.rom's stripe, and its loop (figure 18.6)
  seconds   chapter 17's clock against openMSX's time, ten minutes on each
            machine
  answers   the workshop, tried (for Appendix I)
  openmsx   all of it again with every other build (tools/versions.py)
"""
import json
import math
import sys
import weakref
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(HERE))
import meas        # noqa: E402
import msxcap      # noqa: E402
import probe       # noqa: E402
import versions    # noqa: E402
import gen18       # noqa: E402

CAPS = HERE / "captures"
CLOCK = probe.CLOCK
EU, JP = "MSXBOOK_EU16", "MSXBOOK_JP16"
TAG = {EU: "eu", JP: "jp"}
VDP_PER_T = 6
L = gen18.LINE_T
POS = "[machine_info VDP_frame_count] [machine_info VDP_cycle_in_frame]"
RGB = {"BLACK": (0, 5, 0), "DARK_BLUE": (91, 96, 223), "LIGHT_GREEN": (115, 217, 124),
       "WHITE": (249, 255, 248)}            # openMSX's colours in the captures
SHOT = 10                   # the film frame photographed


def rom(name):
    return HERE / f"{name}.rom"


def sym(name):
    return probe.sym(HERE / f"{name}.sym")


def run(name, frames, tcl, machine=EU, events=None):
    return [l.split() for l in msxcap.run_tcl(rom(name), frames, tcl, machine=machine,
                                              events=events)]


def colour(px):
    return min(RGB, key=lambda c: sum((a - b) ** 2 for a, b in zip(RGB[c], px)))


def shot(name, machine, frames=(SHOT - 1, SHOT), keep=SHOT):
    """the photograph of film frame KEEP, checked to be the same as the
    frame before it when both are asked for"""
    got = msxcap.capture(rom(name), list(frames), CAPS, f"{name}_{TAG[machine]}_f", machine=machine)
    if len(frames) == 2:
        a, b = (Image.open(got[n]).convert("RGB") for n in frames)
        assert a.tobytes() == b.tobytes(), f"{name}: the picture changes from frame to frame"
        got[frames[0]].unlink()
    return {keep: Image.open(got[keep]).convert("RGB")}


def shows(write_t):
    """(line, x) where a change written at T-state WRITE_T of the frame
    shows: x = ceil(1.5 w - 31) for T-state w of the line (chapter 8)"""
    line, w = divmod(write_t, L)
    return line, math.ceil(1.5 * w - 31)


_NAMES = {}


def names(im):
    """the colour of every pixel, by name, worked out once for each picture.
    The cache keeps a weak reference to the picture beside its names: keyed by
    id() alone, a picture made after another was freed can get its id, and
    then its names (a run of every section read the Workshop's second answer
    from another picture's colours that way)"""
    key = id(im)
    if key not in _NAMES or _NAMES[key][0]() is not im:
        px = im.load()
        _NAMES[key] = (weakref.ref(im), {(x, y): colour(px[x, y]) for y in range(meas.CAPTURE_H)
                                         for x in range(meas.DRAWN[0], meas.DRAWN[1] + 1)})
    return _NAMES[key][1]


def check(im, changes, last, row0, paper=None):
    """every pixel of the drawn columns against the model: the colour of the
    last change before it in raster order (LAST before the first); PAPER is
    (first row, last row) of the paper, which is white; returns the count"""
    px = names(im)
    k, want, n = 0, last, 0
    for y in range(meas.CAPTURE_H):
        for x in range(meas.DRAWN[0], meas.DRAWN[1] + 1):
            while k < len(changes) and changes[k][:2] <= (row0 + y, x):
                want = changes[k][2]
                k += 1
            inside = paper and paper[0] <= y <= paper[1] and \
                meas.PAPER_X0 <= x < meas.PAPER_X0 + meas.PAPER_W
            if px[x, y] != ("WHITE" if inside else want):
                return None
            n += 1
    return n


# ---------------------------------------------------------------- lines
def lines():
    s = sym("lines")
    out = {}
    for machine in (EU, JP):
        tcl = (f'set ::bb [debug set_bp {s["go"]} {{}} {{ L "back {POS}"; debug remove_bp $::bb }}]\n'
               f'debug set_bp {s["o1"]} {{}} {{ L "o {POS}" }}\n'
               f'debug set_bp {s["o2"]} {{}} {{ L "o {POS}" }}\n')
        w = run("lines", 8, tcl, machine)
        back = next(x for x in w if x[0] == "back")
        f0 = int(back[1])
        outs = [(int(x[1]), int(x[2]) // VDP_PER_T) for x in w if x[0] == "o"]
        frame_t = gen18.FRAME_T[machine]
        n = frame_t // L
        first = [t for f, t in outs if f == f0 + 1] + [t for f, t in outs if f == f0 + 2]
        abs_t = [(f - f0) * frame_t + t for f, t in outs]
        assert all(b - a == L for a, b in zip(abs_t, abs_t[1:])), "a change that is not a line after the last"
        assert len(abs_t) >= 2 * n
        # the frame's changes, from the first after the interrupt: colour k mod 4
        start = abs_t[0]
        changes = []
        for k in range(n):
            t = (start + k * L + 8) % frame_t                 # OUT (n),A writes 8 T-states in
            line, x = shows(t)
            changes.append((line, x, gen18.COLOURS[k % 4]))
        changes.sort()
        last = changes[-1][2]
        im = shot("lines", machine)[SHOT]
        # which line is the capture's first row, and where the paper is: every
        # offset tried, against every pixel
        fits = []
        for row0 in range(0, 100):
            for paper0 in range(16, 33):
                got = check(im, changes, last, row0, (paper0, paper0 + 191))
                if got:
                    fits.append((row0, paper0, got))
        assert len(fits) == 1, fits
        row0, paper0, pixels = fits[0]
        back_line, back_w = divmod(int(back[2]) // VDP_PER_T, L)
        out[machine] = {"lines": n, "frame": frame_t, "back": [back_line, back_w],
                        "first_out": [shows(abs_t[0] % frame_t)[0], abs_t[0] % frame_t % L],
                        "row0": row0, "paper_row": paper0, "paper_line": row0 + paper0,
                        "last_line": row0 + meas.CAPTURE_H - 1, "pixels": pixels}
    assert out[EU]["row0"] == meas.FRAME_LINE_OF_ROW0[EU]
    assert out[EU]["paper_line"] == meas.PAPER_FRAME_LINE0[EU] and \
        out[JP]["paper_line"] == meas.PAPER_FRAME_LINE0[JP]
    return out


# ---------------------------------------------------------------- ruler
def ruler():
    s = sym("ruler")
    n = gen18.RULER_LINES * gen18.RULER_PER_LINE
    picks = [0, 1, 5, 6, 7, n // 2, n - 2, n - 1]
    # each change is OUT (C),A, OUT (C),E, XOR D, NOP: 6 bytes; the second OUT
    # is 2 bytes in, and writes 10 T-states after it starts
    tcl = (f'set ::bb [debug set_bp {s["go"]} {{}} {{ L "back {POS}"; debug remove_bp $::bb }}]\n'
           + "".join(f'debug set_bp {s["frame"] + 6 * j + 2} {{}} {{ L "c {j} {POS}" }}\n'
                     for j in picks))
    w = run("ruler", 4, tcl)
    f0 = int(next(x for x in w if x[0] == "back")[1])
    got = {}
    for x in w:
        if x[0] == "c":
            got.setdefault(int(x[1]), []).append((int(x[2]) - f0) * gen18.FRAME_T[EU] +
                                                 int(x[3]) // VDP_PER_T)
    t0 = got[0][0]
    for j in picks:
        assert [t - t0 for t in got[j]] == [j * gen18.RULER_T + k * gen18.FRAME_T[EU]
                                            for k in range(len(got[j]))], (j, got[j])
    changes = []
    for j in range(n):
        line, x = shows((t0 + j * gen18.RULER_T + 10) % gen18.FRAME_T[EU])
        changes.append((line, x, "BLACK" if j % 2 == 0 else "WHITE"))
    changes.sort()
    im = shot("ruler", EU)[SHOT]
    row0 = meas.FRAME_LINE_OF_ROW0[EU]
    pixels = check(im, changes, changes[-1][2], row0, (24, 215))
    assert pixels, "the ruler is not where the model puts it"
    w_first = (t0 + 10) % L
    edges = sorted(math.ceil(1.5 * ((w_first + k * gen18.RULER_T) % L) - 31) for k in range(6))
    seen = [x for x in edges if meas.DRAWN[0] <= x <= meas.DRAWN[1]]
    return {"first_w": w_first, "edges": edges, "seen": seen, "pixels": pixels,
            "changes": n, "per_line": gen18.RULER_PER_LINE, "step": gen18.RULER_T}


# ---------------------------------------------------------------- paper
def paper():
    s = sym("paper")
    tcl = f'debug set_bp {s["n1"]} {{}} {{ L "n {POS}" }}\n'
    w = run("paper", 6, tcl)
    writes = [(int(x[1]), int(x[2]) // VDP_PER_T) for x in w if x[0] == "n"]
    frames = {}
    for f, t in writes:
        frames.setdefault(f, []).append(t)
    one = frames[sorted(frames)[1]]
    first = 69 + 8 * gen18.PAPER_ROW
    at = [divmod(t + 8, L) for t in one]                       # OUT (n),A: 8 T-states in
    assert [l for l, _ in at] == list(range(first, first + gen18.PAPER_CELLS)), at
    im = shot("paper", EU)[SHOT]
    px = im.load()
    box = [0b11111110] * 7 + [0]                               # asmparts: the filled box
    checked = 0
    for y in range(192):
        line = 69 + y
        for x in range(256):
            cell, cx = divmod(x, 8)
            on = False
            if y // 8 == gen18.PAPER_ROW and cell < gen18.PAPER_CELLS:
                j = y % 8
                on = j >= cell and box[j] >> (7 - cx) & 1        # the box from line c of the row
            want = "BLACK" if on else "WHITE"
            assert colour(px[meas.PAPER_X0 + x, meas.PAPER_Y0 + y]) == want, (x, y)
            checked += 1
    return {"row": gen18.PAPER_ROW, "first_line": first,
            "writes": [[l, w_] for l, w_ in at], "pixels": checked}


# ---------------------------------------------------------------- box
def box():
    s = sym("box")
    out = {}
    for machine in (EU, JP):
        tcl = (f'set ::bb [debug set_bp {s["go"]} {{}} {{ L "go {POS}"; debug remove_bp $::bb }}]\n'
               f'debug set_bp {s["bw"]} {{}} {{ L "w {POS}" }}\n'
               f'debug set_bp {s["bk"]} {{}} {{ L "k {POS}" }}\n')
        w = run("box", 8, tcl, machine)
        go = next(x for x in w if x[0] == "go")
        f0 = int(go[1])
        writes = {}
        for x in w:
            if x[0] in ("w", "k"):
                writes.setdefault(int(x[1]) - f0, []).append((x[0], int(x[2]) // VDP_PER_T + 8))
        frames = [writes[f] for f in sorted(writes) if len(writes[f]) == 2 * gen18.BOX_LINES]
        assert len(frames) >= 2 and all(fr == frames[0] for fr in frames), "the box moves"
        changes = sorted((*shows(t), "WHITE" if k == "w" else "BLACK") for k, t in frames[0])
        im = shot("box", machine)[SHOT]
        row0 = json.loads((HERE / "meas18.json").read_text())["lines"][machine]["row0"] \
            if (HERE / "meas18.json").exists() else meas.FRAME_LINE_OF_ROW0[EU]
        pixels = check(im, changes, "BLACK", row0, (24, 215))
        assert pixels, machine
        px = names(im)
        white = [(x, y) for (x, y), c in px.items() if c == "WHITE" and not
                 (24 <= y <= 215 and meas.PAPER_X0 <= x < meas.PAPER_X0 + meas.PAPER_W)]
        ys, xs = sorted({y for _, y in white}), sorted({x for x, _ in white})
        back = int(go[2]) // VDP_PER_T % L - 5             # the instruction after HALT, before DI
        out[machine] = {"back": back, "lines": [changes[0][0], changes[-1][0]],
                        "rows": [ys[0], ys[-1]], "x": [xs[0], xs[-1]], "white": len(white),
                        "writes": [t % L for _, t in frames[0][:2]], "pixels": pixels}
    assert out[EU]["rows"] == out[JP]["rows"] and out[EU]["x"] == out[JP]["x"] == [100, 204]
    assert out[EU]["back"] == out[JP]["back"] == gen18.BOX_BACK
    return out


# ---------------------------------------------------------------- drift
FILM_N = 12                 # film frames, from the first with the stripe


def stripe_seen(im, row_hint):
    """(row, first x, last x) of the white stripe on the black border"""
    px = im.load()
    for y in range(meas.CAPTURE_H):
        xs = [x for x in range(meas.DRAWN[0], meas.DRAWN[1] + 1) if colour(px[x, y]) == "WHITE"]
        if xs and y < meas.PAPER_Y0:
            assert xs == list(range(xs[0], xs[-1] + 1)), (y, xs)
            return y, xs[0], xs[-1]
    raise ValueError("no stripe")


def drift_one(name, machine, row0, turn_t):
    s = sym(name)
    tcl = f'debug set_bp {s["s1"]} {{}} {{ L "s {POS}" }}\n'
    w = run(name, FILM_N + 8, tcl, machine)
    f0 = int(w[0][1])
    turns = [(int(x[1]) - f0, int(x[2]) // VDP_PER_T) for x in w if x[0] == "s"]
    film = list(range(turns[0][0], turns[0][0] + FILM_N))     # film frame k is frame f0 + k
    turns = [t for t in turns if t[0] in film]
    shots = msxcap.capture(rom(name), film, CAPS, f"{name}_f", machine=machine)
    seen = []
    for k in film:
        im = Image.open(shots[k]).convert("RGB")
        y, x0, x1 = stripe_seen(im, None)
        seen.append({"frame": k, "row": y, "x0": x0, "x1": x1})
        if machine != EU and k not in (film[0], film[-1]):
            shots[k].unlink()           # figures 18.4 and 18.5 keep the 50 Hz films whole
    # the photographs alone: the white was written at T-state w of line
    # row + row0 with ceil(1.5 w - 31) = x0, so w is in ((x0 + 30) / 1.5,
    # (x0 + 31) / 1.5]; for each drift d of T-states a frame, is there a start
    # that puts every frame's stripe where it is?
    lo = [(sn["row"] + row0) * L + (sn["x0"] + 30) / 1.5 for sn in seen]
    hi = [(sn["row"] + row0) * L + (sn["x0"] + 31) / 1.5 for sn in seen]
    fits = []
    for d in range(-12, 13):
        a = max(l - k * d for k, l in enumerate(lo))
        b = min(h - k * d for k, h in enumerate(hi))
        if a < b + 1e-9:
            fits.append(turn_t - d)
    # the stripe's length: the black written 80 T-states after the white
    lengths = sorted({sn["x1"] - sn["x0"] + 1 for sn in seen})
    return {"turn": turn_t, "turns": turns, "seen": seen, "fits": fits,
            "lengths": lengths, "moved": seen[-1]["x0"] - seen[0]["x0"]}


def drift():
    rows = json.loads((HERE / "meas18.json").read_text())["lines"] if (HERE / "meas18.json").exists() \
        else lines()
    out = {}
    for machine, ns in gen18.DRIFT.items():
        for n in ns:
            r = drift_one(f"f{n}", machine, rows[machine]["row0"], n)
            assert r["fits"] == [gen18.FRAME_T[machine]], (n, r["fits"])
            out[f"f{n}"] = r
    return out


# ---------------------------------------------------------------- wrong
def wrong():
    rows = json.loads((HERE / "meas18.json").read_text())["lines"]
    r = drift_one("wrong", EU, rows[EU]["row0"], 71364 - 5)
    assert r["fits"] == [gen18.FRAME_T[EU]], r["fits"]
    t = [(f * gen18.FRAME_T[EU] + c) for f, c in r["turns"]]
    lengths = sorted({b - a for a, b in zip(t, t[1:])})
    assert lengths == [71364 - 5], lengths
    r["turn_measured"] = lengths[0]
    return r


# ---------------------------------------------------------------- seconds
TEN_MINUTES = 600


def seconds():
    out = {}
    clock = REPO / "ch17" / "clock.rom"
    s = probe.sym(REPO / "ch17" / "clock.sym")
    for machine, rate in ((EU, 50), (JP, 60)):
        frames = round(TEN_MINUTES * CLOCK / gen18.FRAME_T[machine])
        ev = {0: 'L "t0 [machine_info time]"',
              frames: f'L "t1 [machine_info time] [peek16 {s["frames"]}] [peek16 {s["seconds"]}]"'}
        w = [l.split() for l in msxcap.run_tcl(clock, frames + 1, "", machine=machine, events=ev)]
        t0 = float(next(x for x in w if x[0] == "t0")[1])
        t1 = next(x for x in w if x[0] == "t1")
        out[machine] = {"film_frames": frames, "emulated": round(float(t1[1]) - t0, 3),
                        "frames": int(t1[2]), "seconds": int(t1[3]), "rate": rate,
                        "per_second": round(CLOCK / gen18.FRAME_T[machine], 4)}
    return out


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


def one_colour_rows(im):
    """True if every row of the border, in the drawn columns, is one colour"""
    px = names(im)
    for y in range(meas.CAPTURE_H):
        cols = {px[x, y] for x in range(meas.DRAWN[0], meas.DRAWN[1] + 1)
                if not (24 <= y < 216 and meas.PAPER_X0 <= x < meas.PAPER_X0 + meas.PAPER_W)}
        if len(cols) != 1:
            return False
    return True


def answers():
    import shutil
    out = {}
    # 2: lines.asm with its writes at T-states 222 and 223 of the line before,
    # and 33 and 34 of the line: which give every row one colour?
    q2 = {}
    saved = gen18.LINES_W
    try:
        for want in (-6, -5, 33, 34):
            gen18.LINES_W = want + 1                 # the program writes a T-state sooner
            text = gen18.lines().replace("lines.rom", "q2.rom")
            tmp = build_temp("q2", text)
            try:
                s = probe.sym(tmp / "q2.sym")
                w = [l.split() for l in msxcap.run_tcl(tmp / "q2.rom", 4,
                                                       f'debug set_bp {s["o1"]} {{}} {{ L "o {POS}" }}\n')]
                t = int(next(x for x in w if x[0] == "o")[2]) // VDP_PER_T + 8
                got = msxcap.capture(tmp / "q2.rom", [SHOT], tmp, "q2_")
                im = Image.open(got[SHOT]).convert("RGB")
                q2[str((t % L + 114) % L - 114)] = one_colour_rows(im)
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
    finally:
        gen18.LINES_W = saved
    assert q2 == {"-6": False, "-5": True, "33": True, "34": False}, q2
    out["q2"] = q2
    # 4: f71365.asm's stripe after 38 frames
    r = json.loads((HERE / "meas18.json").read_text())["drift"]["f71365"]
    k0 = r["seen"][0]["frame"]
    got = msxcap.capture(rom("f71365"), [k0, k0 + 38], CAPS, "q4_")
    xs = [stripe_seen(Image.open(got[k]).convert("RGB"), None)[1] for k in (k0, k0 + 38)]
    for p in got.values():
        p.unlink()
    out["q4"] = {"frames": 38, "moved": xs[1] - xs[0]}
    assert out["q4"]["moved"] == 57, out["q4"]
    return out


# ---------------------------------------------------------------- openmsx
OPENMSX_SECTIONS = ["lines", "ruler", "paper", "box", "drift", "wrong", "seconds", "answers"]


def openmsx():
    if not versions.builds():
        return {"skipped": "OPENMSX_BUILDS not set"}
    return versions.every_build(["ch18"], OPENMSX_SECTIONS)


SECTIONS = {"lines": lines, "ruler": ruler, "paper": paper, "box": box, "drift": drift, "wrong": wrong,
            "seconds": seconds, "answers": answers, "openmsx": openmsx}


def main(names=()):
    CAPS.mkdir(exist_ok=True)
    path = HERE / "meas18.json"
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
