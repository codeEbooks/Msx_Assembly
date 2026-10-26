#!/usr/bin/env python3
"""meas36.py -- the PSG, measured.

    python3 gen36.py && ./build.sh && python3 meas36.py
                                  python3 meas36.py levels tones   only these

openMSX records each of the PSG's three channels on its own, into a WAV of
one sample every 16 T-states (`set PSG_ch1_record`), from INIT to the end of
the program's script; a watchpoint logs every write to ports $A0 and $A1
from power-on, with its T-state. psg36.py, the model, works out every sample
of every recording from those writes, and every section below holds the
recordings against it, and against the arithmetic of the data sheet.
The whole recordings go to shots/ (made again by every run, and not in the
book's zip); the pieces the figures draw go to captures/.

  model      every recording against psg36.py, sample by sample: the six
             sound programs on both machines, four on the AY-3-8910, and
             mixer.asm on three machines
  levels     levels.asm: the sixteen volumes, on both PSGs
  tones      tones.asm: the chord, a tone shut and opened, a period cut short
  scale      scale.asm: C4 to C5, each note's cycle counted in the recording
  noise      noise.asm: how long the noise holds a bit; the noise register
             read off the recording and stepped back to its start
  env        env.asm: the sixteen shapes, the levels, YM2149 and AY-3-8910
  buzz       buzz.asm: the envelope as a wave, its cycle
  rules      psg36.py with each of its rules taken out in turn
  photos     tones.asm's screen of registers against the registers read
  mixer      WHERE IT BREAKS: mixer.asm on the book's two machines and on
             MSXBOOK_EU16P, whose PSG minds register 7's top bits (figure 36.5)
  prices     walk.py's T-states for psg, step and show
  standard   openMSX's machine files: which PSG, and whether its ports mind
             register 7
  answers    the workshop, tried (for Appendix I)
  openmsx    all of it again with every other build (tools/versions.py)
"""
import json
import math
import shutil
import sys
import wave
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "tools"))
import meas        # noqa: E402
import msxcap      # noqa: E402
import probe as dbg  # noqa: E402
import versions    # noqa: E402
sys.path.insert(0, str(REPO / "ch35"))
import meas35      # noqa: E402  (chapter 35: the joysticks, and its screens)
sys.path.insert(0, str(HERE))
import gen36       # noqa: E402
import psg36       # noqa: E402
sys.path.remove(str(HERE))
sys.path.insert(0, str(HERE))      # gen36 put chapters 34 and 35 first: this folder's files win
for mod in ("vdpscreen", "walk"):
    sys.modules.pop(mod, None)
import vdpscreen   # noqa: E402
import walk        # noqa: E402

assert Path(vdpscreen.__file__).parent == HERE and Path(walk.__file__).parent == HERE

CAPS = HERE / "captures"
SHOTS = HERE / "shots"
EU, JP, AY, PORTS = gen36.EU, gen36.JP, gen36.AY, gen36.PORTS
TAG = {EU: "eu", JP: "jp", AY: "ay", PORTS: "p"}
KIND = {AY: "AY8910"}
CLOCK = gen36.CLOCK
RATE = CLOCK / psg36.SAMPLE_T           # samples a second
FRAME_T = {EU: 71364, JP: 59736, AY: 71364, PORTS: 71364}

# every write to the PSG's two output ports from power-on, with its T-state
WATCH = ('set ::wlog {}\n'
         'debug set_watchpoint write_io {0xA0 0xA1} {} '
         '{ lappend ::wlog "[format %.17g [machine_info time]] [expr {$::wp_last_address & 255}] '
         '$::wp_last_value" }\n')


def rom(name):
    return HERE / f"{name}.rom"


def sym(name):
    return dbg.sym(HERE / f"{name}.sym")


def moves(name):
    """NAME.events: [(frame, port, the switches held from then on)]"""
    out = []
    path = HERE / f"{name}.events"
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        line = line.split("#")[0].strip()
        if line:
            f, p, *held = line.split()
            out.append((int(f), int(p), frozenset() if held == ["-"] else frozenset(held)))
    return out


def t_state(seconds):
    t = float(seconds) * CLOCK
    assert abs(t - round(t)) < 1e-3, seconds
    return round(t)


# ---------------------------------------------------------------- recordings
_recordings = {}


def recording(name, machine):
    """{"ch": the three channels' samples, "writes": [(T, register, byte)],
    "start": the T-state the recording starts at}, made once a run"""
    key = (name, machine)
    if key in _recordings:
        return _recordings[key]
    out = SHOTS / f"{name}_{TAG[machine]}"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    frames = gen36.length(gen36.SCRIPTS[name]) + 5
    start = "".join(f"set PSG_ch{c}_record {{{out / f'ch{c}.wav'}}}\n" for c in (1, 2, 3))
    start += 'L "rec [format %.17g [machine_info time]]"\n'
    stop = 'foreach x $::wlog { L "w $x" }; ' + "".join(f"set PSG_ch{c}_record {{}}; " for c in (1, 2, 3))
    mv = moves(name)
    home = msxcap.make_home()
    log, script = home / "msxcap.log", home / "cap.tcl"
    script.write_text(msxcap.tcl_session(log, msxcap.rom_init(rom(name)), frames,
                                         meas35.tcl_events(mv) if mv else {}, msxcap.DEFAULT_SPEED,
                                         WATCH + (meas35.PLUG if mv else ""), start, stop))
    msxcap.run_openmsx(rom(name), machine, script, home, 600)
    lines = log.read_text().splitlines() if log.exists() else []
    assert "done" in lines, (name, machine, lines[-3:])
    shutil.rmtree(home, ignore_errors=True)
    writes, chosen, rec = [], 0, None
    for line in lines:
        p = line.split()
        if p[0] == "w":
            t, port, v = t_state(p[1]), int(p[2]), int(p[3])
            if port == 0xA0:
                chosen = v & 15
            else:
                writes.append((t, chosen, v))
        elif p[0] == "rec":
            rec = t_state(p[1])
    ch = []
    for c in (1, 2, 3):
        w = wave.open(str(out / f"ch{c}.wav"))
        assert w.getnchannels() == 1 and w.getsampwidth() == 2 and w.getframerate() == round(RATE)
        ch.append(np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(int))
    assert len({len(x) for x in ch}) == 1
    r = {"ch": ch, "writes": writes, "start": rec, "frames": frames, "machine": machine}
    _recordings[key] = r
    return r


def sample_at(r, t):
    """the first sample at or after T-state T"""
    return max(0, -(-(t - r["start"] - psg36.FIRST) // psg36.SAMPLE_T))


def writes_after(r):
    return [w for w in r["writes"] if w[0] > r["start"]]


def model_of(r, chip=psg36.PSG):
    return [np.array(x) for x in psg36.run(r["writes"], r["start"], len(r["ch"][0]),
                                          KIND.get(r["machine"], "YM2149"), chip)]


def off(r, chip=psg36.PSG):
    """the samples of all three channels the model gets wrong"""
    m = model_of(r, chip)
    return sum(int(np.count_nonzero(m[c] != r["ch"][c])) for c in range(3))


FIG_TONES = 1712                # two cycles of C4
FIG_NOISE = (2480, 400, 1712)   # forty bits at period 31; period 1; two cycles of C4
FIG_ENV = 4460                  # a frame of the 50 Hz machine
FIG_MARGIN = 2000               # samples before and after a part
FIG_CUT = 1200                  # samples around the cut in tones.asm


def piece(name, machine, channel, first, n):
    """N samples of a channel from FIRST, into captures/ for the figures"""
    r = recording(name, machine)
    x = r["ch"][channel][first:first + n]
    assert len(x) == n
    path = CAPS / f"{name}_{TAG[machine]}_ch{channel + 1}_{first}_{n}.wav"
    w = wave.open(str(path), "wb")
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(round(RATE))
    w.writeframes(x.astype("<i2").tobytes())
    w.close()
    return path.name


# ---------------------------------------------------------------- model
MODEL_RUNS = ([(n, m) for n in gen36.SOUNDS for m in (EU, JP)]
              + [(n, AY) for n in ("levels", "noise", "env", "buzz")]
              + [("mixer", m) for m in (EU, JP, PORTS)])


def model():
    out, total = {}, 0
    for name, m in MODEL_RUNS:
        r = recording(name, m)
        bad = off(r)
        assert bad == 0, (name, m, bad)
        out.setdefault(name, {})[TAG[m]] = len(r["ch"][0])
        total += 3 * len(r["ch"][0])
    # the recordings start at different moments on the two machines, and find
    # the chip in the same state: the noise register, read off each
    starts = {TAG[m]: round(recording("noise", m)["start"] / CLOCK, 4) for m in (EU, JP)}
    return {"recordings": len(MODEL_RUNS), "runs": out, "samples": total, "off": 0,
            "rate": round(RATE, 2), "first": psg36.FIRST, "noise_starts_s": starts}


# ---------------------------------------------------------------- levels
def held(x, a, b):
    """the one value samples A to B-1 hold"""
    v = set(x[a:b].tolist())
    assert len(v) == 1, (a, b, sorted(v)[:5])
    return v.pop()


def levels():
    out = {}
    for m in (EU, JP, AY):
        r = recording("levels", m)
        ramp = [w for w in writes_after(r) if w[1] == 8][:17]      # 15, then 14 down to 0, then 15
        assert [w[2] for w in ramp[:16]] == list(range(15, -1, -1))
        vals = {}
        for (t, _, v), (t2, _, _) in zip(ramp, ramp[1:]):
            vals[v] = held(r["ch"][0], sample_at(r, t), sample_at(r, t2))
        out[TAG[m]] = [vals[v] for v in range(16)]
    assert out["eu"] == out["jp"] == out["ay"] == psg36.VOLUME
    r = recording("levels", EU)
    ramp = [w for w in writes_after(r) if w[1] == 8]
    at = sample_at(r, ramp[0][0]) - FIG_MARGIN               # figure 36.2: 15 down to 0, and on
    pieces = [piece("levels", EU, 0, at, sample_at(r, ramp[16][0]) - at + FIG_MARGIN)]
    db = [None] + [round(20 * math.log10(v / out["eu"][15]), 1) for v in out["eu"][1:]]
    steps = sorted({round(20 * math.log10(b / a), 2) for a, b in zip(out["eu"][1:], out["eu"][2:])})
    return {"levels": out["eu"], "db": db, "step_db": steps, "same": ["eu", "jp", "ay"], "pieces": pieces,
            "ratio_15_1": round(out["eu"][15] / out["eu"][1], 1)}


# ---------------------------------------------------------------- tones
def turns(x, a, b):
    """the samples from A to B at which the value changes"""
    d = np.nonzero(np.diff(x[a:b]))[0] + 1 + a
    return d.tolist()


def tones():
    out = {}
    for m in (EU, JP):
        r = recording("tones", m)
        steps = gen36.frames_of(gen36.TONES)
        w = writes_after(r)
        res = {}
        # the chord: each channel's half-cycles, in samples, while all three sound
        chord_from = [t for t, reg, v in w if reg == 7 and v == gen36.mixer((0, 1, 2))][0]
        chord_to = [t for t, reg, v in w if reg == 7 and v == gen36.mixer((1, 2))][0]
        a, b = sample_at(r, chord_from), sample_at(r, chord_to)
        for c in range(3):
            tp = r_period(w, c, chord_from)
            halves = set(np.diff(turns(r["ch"][c], a, b)).tolist())
            assert halves == {tp}, (m, c, halves, tp)
            res[c] = {"tp": tp, "hz": round(RATE / (2 * tp), 2), "level": max(r["ch"][c][a:b].tolist())}
        # A shut: its level, unbroken; opened: on from where its count got to
        shut = sample_at(r, chord_to)
        opened = [t for t, reg, v in w if reg == 7 and v == gen36.mixer((0, 1, 2)) and t > chord_to][0]
        held(r["ch"][0], shut, sample_at(r, opened))
        # the cut: the period written below the count; the output turns over at the next sample
        cut = [t for t, reg, v in w if reg == 1 and v == 0 and t > opened][0]
        spy = Spy.at(r, cut)
        j = sample_at(r, cut)
        after = turns(r["ch"][0], j - 1, j + 300)
        res["cut"] = {"count": spy[0], "period_before": spy[1], "period": spy[2], "turned": after[0] - j}
        assert spy[0] >= spy[2] and after[0] - j == 1
        res["shut_frames"] = steps[5][0] - steps[4][0]
        if m == EU:            # figure 36.3: two cycles of C4, the chord's three channels; A shut
            at = a + 2 * round(RATE / 50)    # and opened; A across the cut
            res["pieces"] = [piece("tones", EU, c, at, FIG_TONES) for c in range(3)]
            s0, s1 = shut - FIG_MARGIN, sample_at(r, opened) + FIG_MARGIN
            res["pieces"].append(piece("tones", EU, 0, s0, s1 - s0))
            res["pieces"].append(piece("tones", EU, 0, j - FIG_CUT // 2, FIG_CUT))
        out[TAG[m]] = res
    assert out["eu"][0] == out["jp"][0]
    out["notes"] = {c: gen36.name(n) for c, n in enumerate((gen36.C4, gen36.E4, gen36.G4))}
    return out


def r_period(w, c, before):
    """channel C's period after the writes up to T-state BEFORE"""
    lo = [v for t, reg, v in w if reg == 2 * c and t <= before][-1]
    hi = [v for t, reg, v in w if reg == 2 * c + 1 and t <= before][-1]
    return lo | (hi & 15) << 8


class Spy(psg36.PSG):
    """the model, noting channel A's count when a period is written"""
    seen = {}

    def write(self, reg, value):
        if reg in (0, 1):
            Spy.seen[Spy.now] = (self.count[0], self.period(0))
        super().write(reg, value)
        if reg in (0, 1):
            Spy.seen[Spy.now] += (self.period(0),)

    @staticmethod
    def at(r, t):
        """(count, period before, period after) at the write at T-state T"""
        Spy.seen, Spy.now = {}, None
        writes = sorted(r["writes"])
        regs, k = [0] * 16, 0
        while k < len(writes) and writes[k][0] <= r["start"]:
            regs[writes[k][1]] = writes[k][2]
            k += 1
        chip = Spy(regs)
        n = sample_at(r, t) + 1
        for j in range(n):
            now = r["start"] + psg36.FIRST + psg36.SAMPLE_T * j
            while k < len(writes) and writes[k][0] <= now:
                Spy.now = writes[k][0]
                chip.write(writes[k][1], writes[k][2])
                k += 1
            chip.sample()
        return Spy.seen[t]


# ---------------------------------------------------------------- scale
def cents(f, want):
    return round(1200 * math.log2(f / want), 1)


def scale():
    out = []
    r = recording("scale", EU)
    w = [x for x in writes_after(r) if x[1] == 1 or x[1] == 0]
    starts = sorted({t for t, reg, v in w if reg == 1})
    starts.append([t for t, reg, v in writes_after(r) if reg == 8 and v == 0][0])
    for k, n in enumerate(gen36.SCALE):
        a, b = sample_at(r, starts[k]), sample_at(r, starts[k + 1])
        fa = a + int(RATE / 50)              # skip the first frame, and the last
        tt = turns(r["ch"][0], fa, b - int(RATE / 50))
        cycle = (tt[-1] - tt[0]) / ((len(tt) - 1) / 2)
        tp = gen36.period(gen36.hz(n))
        assert set(np.diff(tt).tolist()) == {tp}
        heard = RATE / cycle
        out.append({"note": gen36.name(n), "want": round(gen36.hz(n), 2), "tp": tp,
                    "from_tp": round(CLOCK / (32 * tp), 2), "cents": cents(CLOCK / (32 * tp), gen36.hz(n)),
                    "heard": round(heard, 2)})
        assert abs(heard - CLOCK / (32 * tp)) < 1e-6
    return {"notes": out, "worst_cents": max(abs(x["cents"]) for x in out)}


# ---------------------------------------------------------------- noise
def back(n):
    """the noise register one move before N"""
    return (n << 1 & 0x1FFFF) | ((n >> 16 ^ n >> 2) & 1)


def noise():
    out = {}
    r = recording("noise", EU)
    w = writes_after(r)
    x = r["ch"][0]
    sets = [(t, v) for t, reg, v in w if reg == 6]
    holds = {}
    for (t, v), (t2, _) in zip(sets[:4], sets[1:5]):    # periods 31, 15, 1 and 0, each to the next write
        a, b = sample_at(r, t), sample_at(r, t2)
        runs = np.diff(turns(x, a, b))
        holds[v] = int(np.gcd.reduce(runs[1:-1]))
        assert holds[v] == 2 * max(1, v), (v, holds[v])
    # the register, read off the recording at period 31, and stepped back to its start
    reads = {}
    for m in (EU, JP):
        reads[TAG[m]] = read_register(recording("noise", m))
        assert reads[TAG[m]]["seed"] == f"{psg36.SEED:04X}", reads
    first = reads["eu"]["first"]
    out = {"holds": {str(k): v for k, v in holds.items()}, "states": 131071,
           "read": {k: {q: v[q] for q in ("bits", "state", "moves_back", "seed")} for k, v in reads.items()}}
    out["repeat"] = {str(p): {"moves": round(RATE / (2 * p)), "seconds": round(131071 * 2 * p / RATE, 2)}
                     for p in (1, 4, 15, 31)}
    out["mixer"] = [f"{v:02X}" for v in sorted({v for _, reg, v in w if reg == 7}, reverse=True)]
    # figure 36.3: the noise at period 31, at period 1, and with C4 on the same channel
    with_tone = [t for t, reg, v in w if reg == 7 and v == gen36.mixer((0,), (0,))][0]
    p1 = [t for t, reg, v in w if reg == 6 and v == 1][0]
    beside = [t for t, reg, v in w if reg == 7 and v == gen36.mixer((0,), (1,))][0]
    out["pieces"] = [piece("noise", EU, 0, first, FIG_NOISE[0]),
                     piece("noise", EU, 0, sample_at(r, p1) + round(RATE / 50), FIG_NOISE[1]),
                     piece("noise", EU, 0, sample_at(r, with_tone) + round(RATE / 50), FIG_NOISE[2]),
                     piece("noise", EU, 1, sample_at(r, beside) + round(RATE / 50), FIG_NOISE[2])]
    return out


def read_register(r):
    """the noise register read off noise.asm's recording at period 31: the
    first 17 whole bits, and the register stepped back to the recording's start"""
    w = writes_after(r)
    x = r["ch"][0]
    sets = [(t, v) for t, reg, v in w if reg == 6]
    opened = [t for t, reg, v in w if reg == 7 and v == gen36.mixer((), (0,))][0]
    a, b = sample_at(r, max(sets[0][0], opened)), sample_at(r, sets[1][0])
    slot = 2 * sets[0][1]
    first = k = turns(x, a, b)[0]
    bits = []
    while k + slot <= b:
        bits.append(1 if held(x, k, k + slot) else 0)
        k += slot
    assert all(bits[n + 17] == bits[n] ^ bits[n + 3] for n in range(len(bits) - 17))
    state = sum(bit << i for i, bit in enumerate(bits[:17]))
    moves = Moves.count(r, first)
    s = state
    for _ in range(moves):
        s = back(s)
    return {"bits": len(bits), "state": f"{state:05X}", "moves_back": moves, "seed": f"{s:04X}",
            "first": first}


class Moves(psg36.PSG):
    """the model, counting the noise register's moves"""
    moved = 0

    def move(self):
        super().move()
        Moves.moved += self.ncount == 0         # the count goes back to 0 at each move

    @staticmethod
    def count(r, upto):
        """the noise's moves from the recording's start to sample UPTO"""
        Moves.moved = 0
        writes = sorted(r["writes"])
        regs, k = [0] * 16, 0
        while k < len(writes) and writes[k][0] <= r["start"]:
            regs[writes[k][1]] = writes[k][2]
            k += 1
        chip = Moves(regs)
        for j in range(upto):
            now = r["start"] + psg36.FIRST + psg36.SAMPLE_T * j
            while k < len(writes) and writes[k][0] <= now:
                chip.write(writes[k][1], writes[k][2])
                k += 1
            chip.sample()
        return Moves.moved


# ---------------------------------------------------------------- env
def env():
    out = {}
    for m in (EU, AY):
        r = recording("env", m)
        x = r["ch"][0]
        w13 = [(t, v) for t, reg, v in writes_after(r) if reg == 13]
        end = [t for t, reg, v in writes_after(r) if reg == 8 and v == 0][-1]
        spans = {}
        for (t, v), (t2, _) in zip(w13, w13[1:] + [(end, None)]):
            spans.setdefault(v, []).append(x[sample_at(r, t):sample_at(r, t2)])
        n = min(len(s) for ss in spans.values() for s in ss)
        groups = {}
        for v in range(16):
            groups.setdefault(tuple(spans[v][0][:n].tolist()), []).append(v)
        # 15 written twice: the second write started it again
        again = len(spans[15]) == 2 and np.array_equal(spans[15][0][:n], spans[15][1][:n])
        down = spans[8][0][:n]                 # R13 = 8: down, and again
        runs = np.diff(turns(down, 0, n))
        values = sorted(set(x.tolist()))
        out[TAG[m]] = {"shapes": sorted(groups.values()), "again": bool(again),
                       "step": int(np.gcd.reduce(runs)), "levels": values,
                       "distinct": len(values) - 1}
        # figure 36.4: a frame from each write of R13 = 8 to 15; and R13 = 8's first ramp on both PSGs
        first_of = {v: t for t, v in reversed(w13)}
        if m == EU:
            out[TAG[m]]["pieces"] = [piece("env", m, 0, sample_at(r, first_of[v]), FIG_ENV) for v in range(8, 16)]
        out[TAG[m]]["ramp"] = piece("env", m, 0, sample_at(r, first_of[8]), 32 * gen36.ENV_PERIOD)
    assert out["eu"]["shapes"] == out["ay"]["shapes"]
    assert out["eu"]["levels"] == psg36.LEVELS and out["eu"]["step"] == gen36.ENV_PERIOD
    assert out["ay"]["levels"] == psg36.VOLUME and out["ay"]["step"] == 2 * gen36.ENV_PERIOD
    out["period"] = gen36.ENV_PERIOD
    out["ramp_T"] = 32 * gen36.ENV_PERIOD * psg36.SAMPLE_T
    return out


# ---------------------------------------------------------------- buzz
def repeat(x, a, b):
    """the smallest p that the samples from A to B repeat with"""
    seg = x[a:b]
    for p in range(1, len(seg) // 3):
        if np.array_equal(seg[p:], seg[:-p]):
            return p
    raise AssertionError("no repeat")


def buzz():
    out = []
    r = recording("buzz", EU)
    w = writes_after(r)
    w13 = [t for t, reg, v in w if reg == 13]
    names = ["sawtooth, R13 = 8", "triangle, R13 = 10", "sawtooth and tone"]
    eps = [gen36.SAW_PERIOD, gen36.TRI_PERIOD, gen36.SAW_PERIOD]
    for k, t in enumerate(w13):
        t2 = min(q for q, reg, v in w if q > t)          # to the next write
        a, b = sample_at(r, t) + 200, sample_at(r, t2)
        p = repeat(r["ch"][0], a, b)
        cycle = (32 if k != 1 else 64) * eps[k]
        assert p == cycle, (k, p, cycle)
        out.append({"wave": names[k], "ep": eps[k], "cycle": p, "cycle_T": p * psg36.SAMPLE_T,
                    "hz": round(RATE / p, 2)})
    return {"waves": out, "tone_tp": 8 * gen36.SAW_PERIOD}


# ---------------------------------------------------------------- rules
class Zero(psg36.PSG):
    """a tone's period of 0 stays 0: the count never reaches it"""
    def period(self, c):
        return (self.r[2 * c] | (self.r[2 * c + 1] & 15) << 8) or 4096


class Wrap(psg36.PSG):
    """a count past a new period runs on to 4,095 and round to it"""
    def write(self, reg, value):
        keep = self.count[:]
        super().write(reg, value)
        self.count = keep

    def move(self):
        for c in range(3):
            self.count[c] = (self.count[c] + 1) % 4096
            if self.count[c] == self.period(c) % 4096:
                self.count[c] = 0
                self.high[c] ^= 1
        tones = self.count[:], self.high[:]
        self.period, real = (lambda c: 10 ** 9), self.period     # the tones moved already
        super().move()
        self.period = real
        self.count, self.high = tones


class Still(psg36.PSG):
    """a shut tone's count stands still"""
    def move(self):
        keep = [(self.count[c], self.high[c]) for c in range(3)]
        super().move()
        for c in range(3):
            if self.r[7] >> c & 1:
                self.count[c], self.high[c] = keep[c]


class Quick(psg36.PSG):
    """the noise moves at the tones' rate"""
    def nperiod(self):
        return max(1, self.r[6] & 31)


class NoiseZero(psg36.PSG):
    """a noise period of 0 counts as 32"""
    def nperiod(self):
        return 2 * ((self.r[6] & 31) or 32)


class Seed(psg36.PSG):
    """the noise register at 1 when the recording starts"""
    def __init__(self, regs, kind="YM2149"):
        super().__init__(regs, kind)
        self.noise = 1


class Sixteen(psg36.PSG):
    """the YM2149's envelope in sixteen levels too"""
    def level(self):
        return psg36.VOLUME[psg36.envelope(self.r[13], self.estep) >> 1]


class Same(psg36.PSG):
    """R13 written with the value it holds leaves the envelope alone"""
    def write(self, reg, value):
        if reg == 13 and value == self.r[13]:
            return
        super().write(reg, value)


RULES = [("a sample every 16 T-states, the first 6 after the start", None),
         ("a tone's period of 0 counts as 1", Zero),
         ("a shut tone's count goes on", Still),
         ("a count past a new period turns over at the next sample", Wrap),
         ("the noise moves every 2 x R6 samples", Quick),
         ("a noise period of 0 counts as 1", NoiseZero),
         ("the noise register starts at the seed", Seed),
         ("the YM2149's envelope has 32 levels", Sixteen),
         ("R13 starts the envelope again, whatever it held", Same)]


def rules():
    runs = [(n, m) for n in gen36.SOUNDS for m in (EU, JP)]
    out = []
    for text, chip in RULES:
        by = {}
        if chip is None:
            for first in (psg36.FIRST - 1, psg36.FIRST + 1):
                keep, psg36.FIRST = psg36.FIRST, first
                try:
                    for n, m in runs:
                        bad = off(recording(n, m))
                        if bad:
                            by[n] = by.get(n, 0) + bad
                finally:
                    psg36.FIRST = keep
        else:
            for n, m in runs:
                bad = off(recording(n, m), chip)
                if bad:
                    by[n] = by.get(n, 0) + bad
        assert by, text
        out.append({"rule": text, "needed_by": sorted(by, key=gen36.SOUNDS.index), "off": sum(by.values())})
    return out


# ---------------------------------------------------------------- photos
# the frames tones.asm writes in, and the frames after them (the first frame read is 1)
TONE_SHOTS = sorted({f + d for f, _ in gen36.frames_of(gen36.TONES) for d in (0, 1)})


def regs_screen(vals):
    n = meas35.gen34.page(gen36.regs_texts("tones.asm"))
    for r, v in enumerate(vals):
        side = r // 7
        row = gen36.TOP + r % 7
        meas35.put(n, row, gen36.BOX_COL[side], meas35.boxes(v, 1))
        meas35.put(n, row, gen36.HEX_COL[side], f"{v:02X}")
    return meas35.screen(n)


def script_regs(steps, frame, start):
    """R0 to R13 after the script's writes up to FRAME"""
    regs = list(start)
    for f, writes in gen36.frames_of(steps):
        if f <= frame:
            for reg, v in writes:
                regs[reg] = v
    return regs


def photos():
    out = {}
    s = sym("tones")
    for m in (EU, JP):
        tcl = (meas35.F0 + meas35.TOO_FAST +
               f'debug set_bp {s["read"]} {{}} {{ binary scan [debug read_block {{PSG regs}} 0 14] cu* v; '
               f'L "v [expr {{[machine_info VDP_frame_count] - $::f0}}] $v" }}\n')
        lines = msxcap.run_tcl(rom("tones"), max(TONE_SHOTS) + 2, tcl, machine=m)
        assert not [l for l in lines if l.startswith("fast")]
        vals = {int(l.split()[1]): [int(x) for x in l.split()[2:]] for l in lines if l.startswith("v ")}
        first = min(vals)
        assert first == 1, first
        boot = vals[first]                       # what the BIOS left: R7 = $B8
        assert boot == [0] * 7 + [0xB8] + [0] * 6, boot
        # every frame's registers as the script says, counted from the first frame read
        for f, v in vals.items():
            assert v == script_regs(gen36.TONES, f - first + 1, boot), (m, f, v)
        pngs = msxcap.capture(rom("tones"), TONE_SHOTS, CAPS, f"tones_{TAG[m]}_f", machine=m)
        ph = {f: meas35.codes(pngs[f]) for f in TONE_SHOTS}
        fits = [e for e in (-2, -1, 0) if all(f + e in vals and meas35.mismatch(regs_screen(vals[f + e]), ph[f]) == 0
                                              for f in TONE_SHOTS)]
        assert len(fits) == 1, (m, fits)
        out[TAG[m]] = {"photos": len(TONE_SHOTS), "lag": fits[0], "frames": len(vals), "first": first}
    return out


# ---------------------------------------------------------------- mixer
# the frames the joystick or register 7 changes in, the frames after them, and one late frame
MIX_SHOTS = sorted({f + d for f in [gen36.MIX_HELD[0][0]] + [f for f, _ in gen36.frames_of(gen36.MIXER)][:4]
                    for d in (0, 1)} | {115})


def mixer_expected(f, machine, first):
    """(register 14 of port 1, register 7, register 15) as mixer.asm reads them in frame F"""
    k = f - first + 1                            # the script's frame
    right = f >= gen36.MIX_HELD[0][0]
    stick = 0xB7 if right else 0xBF
    steps = gen36.frames_of(gen36.MIXER)
    r7 = 0xB8
    for frame, writes in steps:
        if frame <= k:
            r7 = dict(writes).get(7, r7)
    if machine != PORTS:
        return (stick, (r7 & 0x3F) | 0x80, 0x8F)    # the book's PSG: bits 6 and 7 read 1 and 0
    wrong_from = steps[1][0]
    if k < wrong_from:
        return (stick, r7, 0x8F)
    if r7 & 0x80 == 0:                           # port B an input: its pins float high
        return (0xBF, r7, 0xFF)
    return (0xBF, r7, 0xBF)                      # joy wrote back $FF & $BF: pin 8 high


def mix_screen(vals):
    n = meas35.gen34.page(gen36.mixer_texts())
    for key, v in zip(("port1", "r7", "r15"), vals):
        row = gen36.MIX_ROWS[key]
        meas35.put(n, row, gen36.MIX_COL, meas35.boxes(v, 0 if key == "port1" else 1))
        meas35.put(n, row, gen36.MIX_COL + 10, f"{v:02X}")
    return meas35.screen(n)


def mixer():
    out = {}
    s = sym("mixer")
    mv = moves("mixer")
    for m in (EU, JP, PORTS):
        tcl = (meas35.F0 + meas35.TOO_FAST +
               f'debug set_bp {s["read"]} {{}} {{ L "v {meas35.POS} [debug read memory {s["port1"]}] '
               f'[debug read memory {s["r7"]}] [debug read memory {s["r15"]}]" }}\n')
        lines = msxcap.run_tcl(rom("mixer"), gen36.length(gen36.MIXER) + 5, tcl, machine=m,
                               events=meas35.tcl_events(mv), tcl_setup=meas35.PLUG)
        assert not [l for l in lines if l.startswith("fast")]
        vals = {int(l.split()[1]): [int(x) for x in l.split()[3:]] for l in lines if l.startswith("v ")}
        first = min(vals)
        fits = [d for d in (-1, 0, 1) if all(tuple(v) == mixer_expected(f + d, m, first) for f, v in vals.items())]
        assert len(fits) == 1, (m, fits, [(f, [hex(x) for x in v]) for f, v in list(vals.items())[::10]])
        dead = [f for f, v in vals.items() if v[0] == 0xBF and f >= gen36.MIX_HELD[0][0] + 1]
        pngs = msxcap.capture(rom("mixer"), MIX_SHOTS, CAPS, f"mixer_{TAG[m]}_f", machine=m,
                              events=meas35.tcl_events(mv), tcl_setup=meas35.PLUG)
        ph = {f: meas35.codes(pngs[f]) for f in MIX_SHOTS}
        lags = [e for e in (-2, -1, 0) if all(f + e in vals and meas35.mismatch(mix_screen(vals[f + e]), ph[f]) == 0
                                              for f in MIX_SHOTS)]
        assert len(lags) == 1, (m, lags)
        out[TAG[m]] = {"offset": fits[0], "frames": len(vals), "dead": len(dead),
                       "dead_from": min(dead) if dead else None, "lag": lags[0], "photos": len(MIX_SHOTS),
                       "seen": {str(f): [f"{x:02X}" for x in vals[f]] for f in MIX_SHOTS}}
    steps = gen36.frames_of(gen36.MIXER)
    out["script"] = [[f, [f"{v:02X}" for r, v in w if r == 7]] for f, w in steps]
    return out


# ---------------------------------------------------------------- prices
def prices():
    out = {}
    wk = walk.Walk(HERE / "tones")
    out["psg"] = wk.call("psg", a=7, e=0xBE) - 18
    assert out["psg"] == 12 + 5 + 12 + 11
    s = wk.sym
    for label, count, script_step in (("count", 2, 0), ("writes_4", 1, 1), ("over", 0, 0)):
        wk = walk.Walk(HERE / "tones")
        wk.mem[s["count"]] = count
        at = s["script"] + 1                    # the first step's writes
        for f, (n, writes) in enumerate(gen36.TONES[:script_step]):
            at += 2 * len(writes) + 2
        wk.mem[s["next"]] = at & 255
        wk.mem[s["next"] + 1] = at >> 8
        out[f"step_{label}"] = wk.call("step") - 18
    # show: the fourteen registers of tones.asm's chord, as the PSG gives them back

    def read_port(port, t, regs=script_regs(gen36.TONES, 41, [0] * 7 + [0xB8] + [0] * 6)):
        chosen = [v for _, p, v in wk.ports if p == 0xA0][-1]
        return regs[chosen] if port == 0xA2 else 0
    wk = walk.Walk(HERE / "tones", read_port=read_port)
    out["show"] = wk.call("show") - 18
    out["writes_in_step_4"] = len(gen36.TONES[1][1])
    return out


# ---------------------------------------------------------------- standard
UNSAID = "MSXBOOK_EU16N"        # made for this section: the book's machine, its PSG's type left out
TAG[UNSAID] = "n"
KIND[UNSAID] = "AY8910"


def standard():
    import os
    import re
    import tempfile
    # what openMSX takes a PSG for when its machine file does not say
    tmp = Path(tempfile.mkdtemp(prefix="machines_"))
    for x in msxcap.MACHINES.glob("*.xml"):
        shutil.copy(x, tmp)
    text = (tmp / f"{EU}.xml").read_text()
    unsaid = re.sub(r"\s*<type>YM2149</type>", "", text, count=1)
    assert unsaid != text
    (tmp / f"{UNSAID}.xml").write_text(unsaid)
    keep, msxcap.MACHINES = msxcap.MACHINES, tmp
    try:
        r = recording("env", UNSAID)
    finally:
        msxcap.MACHINES = keep
        shutil.rmtree(tmp, ignore_errors=True)
    default = {"levels": len(set(r["ch"][0].tolist())) - 1, "off_as_ay": off(r)}
    assert default == {"levels": 15, "off_as_ay": 0}, default
    share = Path(os.environ.get("OPENMSX_SYSTEM_DATA", "/usr/share/openmsx"))
    kinds, dirs = {}, {}
    files = 0
    for x in sorted((share / "machines").glob("*.xml")):
        text = x.read_text(errors="replace")
        m = re.search(r"<PSG\b.*?</PSG>", text, re.S)
        if not m or "<PPI" not in text:
            continue
        files += 1
        psg = m.group(0)
        t = re.search(r"<type>\s*(\w+)\s*</type>", psg)
        kinds[t.group(1) if t else "none"] = kinds.get(t.group(1) if t else "none", 0) + 1
        d = re.search(r"<ignorePortDirections>\s*(\w+)\s*</ignorePortDirections>", psg)
        key = d.group(1) if d else "unsaid"
        dirs[key] = dirs.get(key, 0) + 1
    return {"machines": files, "type": kinds, "ignorePortDirections": dirs, "unsaid_type": default}


# ---------------------------------------------------------------- answers
def answers():
    m = json.loads((HERE / "meas36.json").read_text())
    out = {}
    tp = 2 * gen36.period(gen36.hz(gen36.C4))          # an octave down: twice the period
    out["q1"] = {"c3_tp": tp, "hz": round(CLOCK / (32 * tp), 2)}
    lv = m["levels"]["levels"]
    out["q2"] = {"ratio_15_9": round(lv[15] / lv[9], 2), "db": round(20 * math.log10(lv[15] / lv[9]), 1)}
    out["q3"] = {"seconds": m["noise"]["repeat"]["31"]["seconds"]}
    shapes = m["env"]["eu"]["shapes"]
    out["q4"] = {"like_9": [v for g in shapes if 9 in g for v in g if v != 9],
                 "like_15": [v for g in shapes if 15 in g for v in g if v != 15]}
    ep = round(RATE / (32 * 440))
    hz = RATE / (32 * ep)
    out["q5"] = {"ep": ep, "hz": round(hz, 2), "cents": cents(hz, 440)}
    out["q6"] = {"r7": f"{gen36.mixer((0,), (1,)):02X}"}
    mx = m["mixer"]["p"]["seen"]
    out["q7"] = {"r15_after": mx[str(max(int(k) for k in mx))][2]}
    pr = m["prices"]
    out["q8"] = {"show": pr["show"], "eu": round(100 * pr["show"] / FRAME_T[EU], 2),
                 "jp": round(100 * pr["show"] / FRAME_T[JP], 2)}
    out["q9"] = {"samples": m["env"]["ay"]["step"], "t": m["env"]["ay"]["step"] * psg36.SAMPLE_T}
    cut = m["tones"]["eu"]["cut"]
    out["q10"] = {"count": cut["count"], "period": cut["period"], "turned": cut["turned"]}
    hold = m["noise"]["holds"]["15"]
    out["q11"] = {"samples": hold, "t": hold * psg36.SAMPLE_T}
    out["q12"] = {"sample": lv[8], "db": m["levels"]["db"][8]}
    return out


OPENMSX_SECTIONS = ["model", "levels", "tones", "scale", "noise", "env", "buzz", "photos", "mixer"]


def openmsx():
    if not versions.builds():
        return {"skipped": "OPENMSX_BUILDS not set"}
    return versions.every_build(["ch36"], OPENMSX_SECTIONS)


SECTIONS = {"model": model, "levels": levels, "tones": tones, "scale": scale, "noise": noise,
            "env": env, "buzz": buzz, "rules": rules, "photos": photos, "mixer": mixer,
            "prices": prices, "standard": standard, "answers": answers, "openmsx": openmsx}


def main(names=()):
    CAPS.mkdir(exist_ok=True)
    SHOTS.mkdir(exist_ok=True)
    path = HERE / "meas36.json"
    m = json.loads(path.read_text()) if names and path.exists() else {}
    for name in names or SECTIONS:
        print(name, flush=True)
        m[name] = SECTIONS[name]()
        m = {k: m[k] for k in SECTIONS if k in m}
        path.write_text(json.dumps(m, indent=1) + "\n")
    return m


if __name__ == "__main__":
    main(sys.argv[1:])
