#!/usr/bin/env python3
"""meas49.py -- the samples, measured.

    python3 gen49.py && ./build.sh && python3 meas49.py
                                  python3 meas49.py recordings quality   only these

openMSX records each of the PSG's three channels on its own, into a WAV of
one sample every 16 T-states (set PSG_chN_record, chapter 36), from INIT
until the sounds are over; a watchpoint logs every write to the PSG's two
ports, with its T-state, from power-on.

  recordings  one.rom, three.rom and skip.rom on each machine. walk.py runs
              each program from INIT to done, as its listing says: every
              write to the PSG comes where walk.py puts it, the same number
              of T-states after INIT; psg36.py (chapter 36) makes every
              sample of the three channels from the writes, and the
              recordings agree, sample by sample; and the T-states between
              one sample's writes and the next's
  quality     what the recordings sound like against the sounds as gen49.py
              made them: each recorded level against the level the sample
              means, held from the moment its first write is heard, for each
              sound; the error as a signal-to-noise ratio; when each sound
              begins and how long it lasts
  pieces      the parts of the recordings the figures show, cut out and
              checked against the model (figures 49.1 to 49.5)
  prices      what play1 and play3 cost, from walk.py, both ways through
              play1 and through skip.asm's loop; the fastest each can go
  answers     the workshop, tried (for Appendix I)
  openmsx     all of it again with every other build (tools/versions.py)
"""
import json
import math
import shutil
import subprocess
import sys
import tempfile
import wave
from collections import Counter
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "tools"))
import msxcap      # noqa: E402
import probe as dbg  # noqa: E402
import versions    # noqa: E402
sys.path.insert(0, str(HERE))
import gen49       # noqa: E402
sys.path.remove(str(HERE))
sys.path.insert(0, str(HERE))      # other chapters came first: this folder's files win
for mod in ("walk", "psg36"):
    sys.modules.pop(mod, None)
import walk        # noqa: E402
import psg36       # noqa: E402

assert Path(walk.__file__).parent == HERE and Path(psg36.__file__).parent == HERE

CAPS = HERE / "captures"
SHOTS = HERE / "shots"
EU, JP = gen49.EU, gen49.JP
TAG = {EU: "eu", JP: "jp"}
CLOCK = gen49.CLOCK
RATE = CLOCK / psg36.SAMPLE_T           # recorded samples a second
PERIOD = gen49.PERIOD
FRAMES = 90                             # enough for the sounds on both machines
PROGS = gen49.PROGRAMS

WATCH = ('set ::wlog {}\n'
         'debug set_watchpoint write_io {0xA0 0xA1} {} '
         '{ lappend ::wlog "[format %.17g [machine_info time]] [expr {$::wp_last_address & 255}] '
         '$::wp_last_value" }\n')


def rom(name, d=HERE):
    return Path(d) / f"{name}.rom"


def t_state(seconds):
    t = float(seconds) * CLOCK
    assert abs(t - round(t)) < 1e-3, seconds
    return round(t)


# ---------------------------------------------------------------- recordings
_recordings = {}


def recording(name, machine, d=HERE, keep=True):
    """{"ch": the three channels' samples, "writes": [(T, register, byte)],
    "start": the T-state the recording starts at, INIT's}"""
    key = (str(d), name, machine)
    if key in _recordings:
        return _recordings[key]
    out = (SHOTS if keep else Path(tempfile.mkdtemp(prefix="rec49_"))) / f"{name}_{TAG[machine]}"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    start = "".join(f"set PSG_ch{c}_record {{{out / f'ch{c}.wav'}}}\n" for c in (1, 2, 3))
    start += 'L "rec [format %.17g [machine_info time]]"\n'
    stop = 'foreach x $::wlog { L "w $x" }; ' + "".join(f"set PSG_ch{c}_record {{}}; " for c in (1, 2, 3))
    home = msxcap.make_home()
    log, script = home / "msxcap.log", home / "cap.tcl"
    script.write_text(msxcap.tcl_session(log, msxcap.rom_init(rom(name, d)), FRAMES, {},
                                         msxcap.DEFAULT_SPEED, WATCH, start, stop))
    msxcap.run_openmsx(rom(name, d), machine, script, home, 600)
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
    if not keep:
        shutil.rmtree(out.parent, ignore_errors=True)
    r = {"ch": ch, "writes": writes, "start": rec, "machine": machine}
    _recordings[key] = r
    return r


def model_of(r):
    return [np.array(x) for x in psg36.run(r["writes"], r["start"], len(r["ch"][0]))]


def off(r):
    m = model_of(r)
    return sum(int(np.count_nonzero(m[c] != r["ch"][c])) for c in range(3))


def walked(name, d=HERE):
    """walk.py from INIT to done: [(T after INIT, register, byte)] of the
    writes to the PSG, the way recording() keeps them; the T-state each turn
    of the player's loop starts at; and the T-states to done"""
    wk = walk.Walk(Path(d) / name)
    wk.mem[0x2B] = 0
    nxt = wk.sym["play1.next" if "play1.next" in wk.sym else "play3.next"]
    stop = wk.sym["done"]
    wk.pc, turns = wk.sym["init"], []
    while wk.pc != stop:
        if wk.pc == nxt:
            turns.append(wk.t)
        wk.step()
    out, chosen = [], 0
    for tt, port, v in wk.ports:
        if port == 0xA0:
            chosen = v & 15
        elif port == 0xA1:
            out.append((tt, chosen, v))
    return out, turns, wk.t


def after(r):
    return [w for w in r["writes"] if w[0] > r["start"]]


def firsts(ww, turns):
    """each turn of the loop that writes: its first write's T-state"""
    data = [t for t, reg, v in ww if t >= turns[0]]
    out, j = [], 0
    for k in range(len(turns)):
        end = turns[k + 1] if k + 1 < len(turns) else math.inf
        if j < len(data) and data[j] < end:
            out.append(data[j])
            while j < len(data) and data[j] < end:
                j += 1
    return out


def gaps(ww, turns):
    """the T-states from a sample's first write to the next sample's"""
    f = firsts(ww, turns)
    return Counter(b - a for a, b in zip(f, f[1:]))


def check(name, machine, d=HERE, keep=True):
    """a recording against walk.py and psg36.py"""
    r = recording(name, machine, d, keep)
    ww, turns, t_done = walked(name, d)
    got = after(r)
    assert len(got) == len(ww), (name, machine, len(got), len(ww))
    lag = Counter(g[0] - r["start"] - w[0] for g, w in zip(got, ww))
    assert len(lag) == 1 and all(g[1:] == w[1:] for g, w in zip(got, ww)), (name, machine, lag)
    bad = off(r)
    assert bad == 0, (name, machine, "samples off", bad)
    r["walk"] = (ww, turns, list(lag)[0])
    return r, ww, list(lag)[0], t_done


def recordings():
    out = {}
    for name in PROGS:
        for mc in (EU, JP):
            r, ww, lag, t_done = check(name, mc)
            turns = r["walk"][1]
            t1 = turns[1]                       # the second turn: a sample like any other
            seen = [w[0] - r["start"] - t1 for w in after(r) if t1 <= w[0] - r["start"] < turns[2]]
            out.setdefault(name, {})[TAG[mc]] = {
                "within": seen,
                "writes": len(ww), "samples": len(r["ch"][0]), "checked": 3 * len(r["ch"][0]),
                "lag": lag, "init_to_done": t_done,
                "turns": len(turns), "gaps": {str(k): v for k, v in sorted(gaps(ww, turns).items())}}
            print("recording", name, TAG[mc], len(ww), out[name][TAG[mc]]["gaps"], flush=True)
    return out


# ---------------------------------------------------------------- quality
def heard(r):
    """the three channels added up"""
    return r["ch"][0] + r["ch"][1] + r["ch"][2]


def first_heard(r, t):
    """the first recorded sample a write at T-state T is heard in"""
    return max(0, -(-(t - r["start"] - psg36.FIRST) // psg36.SAMPLE_T))


def sample_times(r):
    """the T-state of each of the sounds' samples' first write, from the
    recording's start: walk.py's and the lag; a sample that writes nothing
    (skip.asm), where its write would have been"""
    ww, turns, lag = r["walk"]
    turns = turns + [math.inf]
    data = [t for t, reg, v in ww if t >= turns[0]]
    k0 = next(k for k in range(len(turns) - 1) if turns[k] <= data[0] < turns[k + 1])
    gap = data[0] - turns[k0]                   # a turn's first write, after its start
    out, j = [], 0
    for k in range(len(turns) - 1):
        if j < len(data) and data[j] < turns[k + 1]:
            t = data[j]
            gap = t - turns[k]
            while j < len(data) and data[j] < turns[k + 1]:
                j += 1
        else:
            t = turns[k] + gap
        out.append(t + lag)
    assert j == len(data)
    return out


def sample_starts(r):
    """the recorded sample each of the sounds' samples is first heard in"""
    return [first_heard(r, r["start"] + t) for t in sample_times(r)]


def snr(want, got):
    want, got = np.asarray(want, float), np.asarray(got, float)
    s = float(np.sum((want - want.mean()) ** 2))
    e = float(np.sum((want - got) ** 2))
    return round(10 * math.log10(s / e), 1)


BAND = gen49.FS / 2                     # the highest frequency the samples carry


def in_band(x):
    """X, a recording's rate, without what lies above BAND"""
    f = np.fft.rfft(np.asarray(x, float))
    f[np.fft.rfftfreq(len(x), 1 / RATE) > BAND] = 0
    return np.fft.irfft(f, len(x))


def quality_of(name, r):
    """each sound: the recorded levels against the levels its samples mean,
    each held from the recorded sample its first write is heard in until the
    next's: all of it, and below BAND, where the samples' sound is; and
    below BAND on the grid of the ideal timing, 452 T-states a sample from
    the first; and below BAND the samples' levels as the volumes give them,
    held the same way but changed all at once, as if the writes took no
    time ("at_once")"""
    top = gen49.TOP if name == "one" else 3 * gen49.TOP
    x = heard(r)
    times = sample_times(r)
    st = sample_starts(r)
    assert len(st) == gen49.SAMPLES
    grid = [first_heard(r, r["start"] + times[0] + k * PERIOD) for k in range(gen49.SAMPLES + 1)]
    t0 = st[0]
    out = {}
    for sound, a, n in gen49.STARTS:
        want_own, want_grid, got_own, got_grid, held = [], [], [], [], []
        for k in range(a, a + n):
            lev = gen49.level(gen49.WAVE[k]) * top
            vol = gen49.VOLUME[gen49.ONE[k]] if name == "one" else gen49.SUMS[gen49.THREE[k]]
            for j in range(st[k], st[k + 1]):
                want_own.append(lev)
                got_own.append(x[j])
                held.append(vol)
            for j in range(grid[k], grid[k + 1]):
                want_grid.append(lev)
                got_grid.append(x[j])
        out.setdefault(sound, []).append({
            "snr": snr(want_own, got_own), "band": snr(in_band(want_own), in_band(got_own)),
            "band_grid": snr(in_band(want_grid), in_band(got_grid)),
            "at_once": snr(in_band(want_own), in_band(held)),
            "begins": (st[a] - t0) * psg36.SAMPLE_T, "lasts": (st[a + n] - st[a]) * psg36.SAMPLE_T})
    return out


def quantised(name):
    """the same, the samples' levels exactly as the volumes say, without the
    PSG: what the table or the sixteen levels alone allow"""
    out = {}
    for sound, a, n in gen49.STARTS:
        want = [gen49.level(x) for x in gen49.WAVE[a:a + n]]
        if name == "one":
            got = [gen49.VOLUME[v] / gen49.TOP for v in gen49.ONE[a:a + n]]
        else:
            got = [gen49.SUMS[i] / (3 * gen49.TOP) for i in gen49.THREE[a:a + n]]
        out.setdefault(sound, []).append(snr(want, got))
    return out


def quality():
    out = {}
    for name in PROGS:
        for mc in (EU, JP):
            r, _, _, _ = check(name, mc)
            out.setdefault(name, {})[TAG[mc]] = quality_of(name, r)
        assert out[name]["eu"] == out[name]["jp"], name
        if name != "skip":
            out[name]["levels_alone"] = quantised(name)
        print("quality", name, {k: [(x["snr"], x["band"], x["band_grid"], x["at_once"]) for x in v]
                                 for k, v in out[name]["eu"].items()}, flush=True)
    return out


# ---------------------------------------------------------------- pieces
FIG_VOWEL = (2000, 3800)        # figure 49.3: the vowel's sample to start at; recorded samples
FIG_KICK = 5600                 # figure 49.3: the kick's first 25 milliseconds, in recorded samples
FIG_HAT = (120, 4)              # figure 49.1: four samples of the first hi-hat's first 120
FIG_GAPS = 1346                 # figure 49.5: the ramp and the kick, the first 1,346 samples


def digest(x):
    import hashlib
    return hashlib.sha256(np.asarray(x).astype("<i2").tobytes()).hexdigest()[:16]


def cut(r, name, machine, c, first, n):
    """N recorded samples of channel C from FIRST into captures/, for a figure"""
    x = r["ch"][c][first:first + n]
    assert len(x) == n
    path = CAPS / f"{name}_{TAG[machine]}_ch{c + 1}_{first}_{n}.wav"
    CAPS.mkdir(exist_ok=True)
    w = wave.open(str(path), "wb")
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(round(RATE))
    w.writeframes(x.astype("<i2").tobytes())
    w.close()
    return path.name


def turn_gaps(r, upto):
    """from the debugger's writes: for each sample up to UPTO that writes, its
    number and the T-states to the next sample that writes"""
    ww, turns, lag = r["walk"]
    data = [t for t, reg, v in r["writes"] if t > r["start"] + lag + turns[0]]
    f = firsts([(t - r["start"] - lag, 0, 0) for t in data], turns)
    out, k = [], 0
    for t in f:
        while k + 1 < len(turns) and turns[k + 1] <= t:
            k += 1
        out.append((k, t))
    return [[k, t2 - t] for (k, t), (_, t2) in zip(out, out[1:]) if k < upto]


def hat_window(r, st, a):
    """of the first hi-hat's first FIG_HAT[0] samples, the one whose steps in
    between are furthest from both the level before and the level after: the
    four samples from the one before it"""
    x = heard(r)

    def worst(i):
        old, new = x[st[a + i] - 1], x[st[a + i + 1] - 1]
        return max(min(abs(x[j] - old), abs(x[j] - new)) for j in range(st[a + i], st[a + i + 1]))
    k = max(range(FIG_HAT[0]), key=lambda i: (worst(i), -i))
    return max(0, k - 1)


WHOLE_BINS = 1000               # figure 49.2: the whole of the sounds, in a thousand slices
FREQS = (12000, 40, 0.4)     # figure 49.4: up to 12 kHz, 40 Hz a bin, the vowel's middle 0.4 s


def made(r, top):
    """the sounds as gen49.py made them, each sample's level held from the
    recorded sample its first write is heard in until the next's"""
    st = sample_starts(r)
    st = st + [st[-1] + -(-PERIOD // psg36.SAMPLE_T)]
    x = np.zeros(len(heard(r)))
    for k in range(gen49.SAMPLES):
        x[st[k]:st[k + 1]] = gen49.level(gen49.WAVE[k]) * top
    return x


def freqs(r, x=None):
    """the vowel's middle FREQS[2] seconds, the three channels added up (or
    X, on the same timing): each FREQS[1] Hz up to FREQS[0], the strongest
    component, in dB below the strongest of all"""
    st = sample_starts(r)
    a, n = next((a, n) for s_, a, n in gen49.STARTS if s_ == "vowel")
    mid = st[a + n // 2]
    half = round(FREQS[2] * RATE / 2)
    x = (heard(r) if x is None else x)[mid - half:mid + half].astype(float)
    x = (x - x.mean()) * np.hanning(len(x))
    mag = np.abs(np.fft.rfft(x))
    f = np.fft.rfftfreq(len(x), 1 / RATE)
    top = mag.max()
    out = []
    for lo in range(0, FREQS[0], FREQS[1]):
        m = mag[(f >= lo) & (f < lo + FREQS[1])].max()
        out.append(round(20 * math.log10(max(m, 1e-9) / top), 1))
    return out


def envelope(r):
    """the three channels added up, from the first sample's first write to
    the last sample's end, in WHOLE_BINS slices: each slice's lowest and
    highest"""
    st = sample_starts(r)
    a = st[0]
    b = st[-1] + -(-PERIOD // psg36.SAMPLE_T)
    x = heard(r)[a:b]
    edges = [len(x) * i // WHOLE_BINS for i in range(WHOLE_BINS + 1)]
    return [[int(x[e0:e1].min()), int(x[e0:e1].max())] for e0, e1 in zip(edges, edges[1:])]


def pieces():
    out = {}
    a_vowel = next(a for s_, a, n in gen49.STARTS if s_ == "vowel")
    a_hat = next(a for s_, a, n in gen49.STARTS if s_ == "hat")
    for mc in (EU, JP):
        got = {}
        for name in ("one", "three"):
            r, _, _, _ = check(name, mc)
            st = sample_starts(r)
            j0 = st[a_vowel + FIG_VOWEL[0]]
            chans = (0,) if name == "one" else (0, 1, 2)
            got[f"vowel_{name}"] = [cut(r, name, mc, c, j0, FIG_VOWEL[1]) for c in chans]
            got[f"vowel_{name}_samples"] = [r["ch"][c][j0:j0 + FIG_VOWEL[1]].tolist() for c in chans]
            a_kick = next(a for s_, a, n in gen49.STARTS if s_ == "kick")
            k0 = st[a_kick]
            got[f"kick_{name}"] = [cut(r, name, mc, c, k0, FIG_KICK) for c in chans]
            got[f"kick_{name}_samples"] = [r["ch"][c][k0:k0 + FIG_KICK].tolist() for c in chans]
            if name == "three":
                k0 = hat_window(r, st, a_hat)
                h0 = st[a_hat + k0]
                n = st[a_hat + k0 + FIG_HAT[1]] - h0
                got["hat_first"] = k0
                got["hat_three"] = [cut(r, name, mc, c, h0, n) for c in (0, 1, 2)]
                got["hat_three_samples"] = [r["ch"][c][h0:h0 + n].tolist() for c in (0, 1, 2)]
                got["hat_writes"] = [[t - r["start"], reg, v] for t, reg, v in after(r)
                                     if h0 <= first_heard(r, t) < h0 + n]
        for name in ("three", "skip"):
            r, _, _, _ = check(name, mc)
            got[f"gaps_{name}"] = turn_gaps(r, FIG_GAPS)
        for name in ("one", "three"):
            r, _, _, _ = check(name, mc)
            got[f"whole_{name}"] = envelope(r)
            got[f"freqs_{name}"] = freqs(r)
            if name == "three":
                got["freqs_made"] = freqs(r, made(r, 3 * gen49.TOP))
        out[TAG[mc]] = got
    for k in out["eu"]:
        if k.endswith("_samples") or k.startswith("gaps"):
            assert out["eu"][k] == out["jp"][k], ("the two machines", k)
    res = {t: {k: (v if not k.endswith("_samples") else [digest(x) for x in v]) for k, v in out[t].items()}
           for t in out}
    res["same_on_both"] = True
    return res


# ---------------------------------------------------------------- prices
def fresh(name, d=HERE):
    wk = walk.Walk(Path(d) / name)
    wk.mem[0x2B] = 0
    return wk


def set_wait(wk, start, end, op, was, n):
    """the immediate of OP (LD B,n or LD A,n) with WAS between START and END
    -> N, in the listing's instruction walk.py runs"""
    a = next(a for a in sorted(wk.code) if start <= a < end and wk.code[a] == bytes([op, was]))
    wk.code[a] = bytes([op, n])
    wk.mem[a + 1] = n


def prices():
    out = {}
    wk = fresh("one")
    s_ = wk.sym
    snd = s_["sound"]
    ways = {}
    for e, lab in ((2, "high"), (3, "low")):
        ways[lab] = wk.lap("play1.next", h=snd >> 8, l=snd & 255, d=0, e=e)
    out["play1"] = ways
    set_wait(wk, s_["play1"], s_["psg"], 0x06, gen49.WAIT1, 1)
    out["play1_fastest"] = wk.lap("play1.next", h=snd >> 8, l=snd & 255, d=0, e=2)
    wk = fresh("three")
    s_ = wk.sym
    snd, vols = s_["sound"], s_["vols"]
    out["play3"] = wk.lap("play3.next", b=snd >> 8, c=snd & 255, d=0, e=5, h=vols >> 8, l=0)
    set_wait(wk, s_["play3"], s_["psg"], 0x3E, gen49.WAIT3, 1)
    out["play3_fastest"] = wk.lap("play3.next", b=snd >> 8, c=snd & 255, d=0, e=5, h=vols >> 8, l=0)
    wk = fresh("skip")
    s_ = wk.sym
    snd, vols = s_["sound"], s_["vols"]
    first = wk.mem[snd]
    out["skip"] = {"a new sample": wk.lap("play3.next", b=snd >> 8, c=snd & 255, d=0, e=5, h=vols >> 8,
                                          l=(first + 1) & 255),
                   "the same": wk.lap("play3.next", b=snd >> 8, c=snd & 255, d=0, e=5, h=vols >> 8,
                                      l=first)}
    out["psg"] = fresh("one").call("psg", a=7, e=0xBF)
    sizes = {}
    for name in ("one", "three"):
        s_ = dbg.sym(HERE / f"{name}.sym")
        sizes[name] = {"before_sound": s_["sound"] - 0x4000,
                       "sound": (gen49.SAMPLES // 2) if name == "one" else gen49.SAMPLES}
    out["sizes"] = sizes
    return out


# ---------------------------------------------------------------- the workshop
def build_variant(kind):
    name, src = gen49.variant(kind)
    d = Path(tempfile.mkdtemp(prefix=f"var49_{kind}_"))
    shutil.copy(HERE / "msx.inc", d)
    (d / f"{name}.asm").write_text(src)
    subprocess.run(["sjasmplus", "--nologo", "--msg=err", "--syntax=bFw", f"--sym={name}.sym",
                    f"--lst={name}.lst", f"{name}.asm"], cwd=d, check=True)
    return name, d


def answers():
    out = {}
    m = json.loads((HERE / "meas49.json").read_text())
    pr, ql = m["prices"], m["quality"]
    # 1. play1 without its NOP
    name, d = build_variant("nonop")
    q1 = {}
    for mc in (EU, JP):
        r, ww, lag, t_done = check(name, mc, d, keep=False)
        q = quality_of("one", r)
        q1[TAG[mc]] = {"gaps": {str(k): v for k, v in sorted(gaps(ww, r["walk"][1]).items())},
                       "quality": q, "quality_one": ql["one"][TAG[mc]]}
    shutil.rmtree(d)
    out["q1"] = q1
    print("q1", q1["eu"]["gaps"], flush=True)
    # 2. the T-states a game would have, its code in the wait's place
    q2 = {}
    for kind, play, regs in (("nowait1", "play1", {}), ("nowait3", "play3", {})):
        name, d = build_variant(kind)
        wk = fresh(name, d)
        s_ = wk.sym
        snd = s_["sound"]
        if play == "play1":
            ways = [wk.lap("play1.next", h=snd >> 8, l=snd & 255, d=0, e=e) for e in (2, 3)]
        else:
            ways = [wk.lap("play3.next", b=snd >> 8, c=snd & 255, d=0, e=5, h=s_["vols"] >> 8, l=0)]
        shutil.rmtree(d)
        assert len(set(ways)) == 1, ways
        q2[play] = {"work": ways[0], "free": PERIOD - ways[0]}
    out["q2"] = q2
    print("q2", q2, flush=True)
    # 3. seconds of sound in 32 KB of samples
    out["q3"] = {name: {"bytes_a_second": round(per_s, 1), "seconds": round(0x8000 / per_s, 2)}
                 for name, per_s in (("one", gen49.FS / 2), ("three", gen49.FS))}
    # 4. the samples that took skip.asm's short way, sound by sound
    r, ww, lag, _ = check("skip", EU)
    turns = r["walk"][1]
    short = []
    data = sorted(t for t, reg, v in ww if t >= turns[0])
    j = 0
    for k in range(len(turns)):
        end = turns[k + 1] if k + 1 < len(turns) else math.inf
        has = j < len(data) and data[j] < end
        while j < len(data) and data[j] < end:
            j += 1
        if not has:
            short.append(k)
    where = {}
    edges = [("ramp up", 0, gen49.RAMP)] + [(s_, a, n) for s_, a, n in gen49.STARTS] + \
        [("ramp down", gen49.SAMPLES - gen49.RAMP, gen49.RAMP)]
    for k in short:
        lab = next(f"{s_} {i}" for i, (s_, a, n) in enumerate(edges) if a <= k < a + n)
        where[lab] = where.get(lab, 0) + 1
    out["q4"] = {"short": len(short), "where": where,
                 "same_in_data": sum(1 for a, b in zip(gen49.THREE, gen49.THREE[1:]) if a == b) +
                 (gen49.THREE[0] == 0)}
    print("q4", out["q4"], flush=True)
    # 5. the rows of the table that repeat a sum
    seen, again = set(), []
    for i, s_ in enumerate(gen49.SUMS):
        if s_ in seen:
            again.append(i)
        seen.add(s_)
    out["q5"] = {"first_again": again[0], "rows_again": len(again),
                 "sums_below_128": len(set(gen49.SUMS[:128])), "sums_from_128": len(set(gen49.SUMS[128:])),
                 "most_rows_one_sum": max(Counter(gen49.SUMS).values()),
                 "that_sum": Counter(gen49.SUMS).most_common(1)[0][0],
                 "top_steps": [gen49.VOLUME[v + 1] - gen49.VOLUME[v] for v in (12, 13, 14)],
                 "row_step": round(3 * gen49.TOP / 255, 1)}
    print("q5", out["q5"], flush=True)
    return out


# ---------------------------------------------------------------- openmsx
def openmsx():
    if not versions.builds():
        return {"skipped": "OPENMSX_BUILDS not set"}
    return versions.every_build(["ch49"], OPENMSX_SECTIONS)


OPENMSX_SECTIONS = ["recordings", "quality", "pieces", "prices", "answers"]
SECTIONS = {"recordings": recordings, "quality": quality, "pieces": pieces, "prices": prices,
            "answers": answers, "openmsx": openmsx}


def main(names=()):
    path = HERE / "meas49.json"
    old = json.loads(path.read_text()) if path.exists() else {}
    for n in (names or SECTIONS):
        old[n] = SECTIONS[n]()
        path.write_text(json.dumps(old, indent=1, sort_keys=True))


if __name__ == "__main__":
    main(sys.argv[1:])
