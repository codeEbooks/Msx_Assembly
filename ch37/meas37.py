#!/usr/bin/env python3
"""meas37.py -- the sound engine, measured.

    python3 gen37.py && ./build.sh && python3 meas37.py
                                  python3 meas37.py writes pace   only these

openMSX runs each cartridge from INIT with three instruments on: a
watchpoint that logs every write to ports $A0 and $A1 (and every read of
$A2) with its T-state, breakpoints where isr starts and where it returns,
and the VGM recorder of openMSX's own scripts (`vgm_rec start PSG`), which
keeps every write to R0-R13 the way music players read it; and openMSX
records each of the PSG's channels (chapter 36). Against them: player37.py,
the player in Python, for every byte sent; walk.py, the cartridge's own code
run outside openMSX, for every byte and every T-state; chapter 36's
psg36.py for every sample of every recording. The whole recordings go to
shots/ (made again by every run, and not in the book's zip); the pieces the
figures draw go to captures/.

  bytes      the music's bytes in the cartridges, against music37.py
  writes     every write to the PSG of tune, effects, fast and sixth, on
             both machines, against player37.py and pace's arithmetic
  walk       the same writes and their T-states from walk.py, and isr's
             length in every frame, against the debugger
  vgm        openMSX's VGM file of tune.asm against the debugger's log
  model      every recording against psg36.py, sample by sample
  pace       the tune's length on the two machines, three ways of pacing
  effects    effects.asm: the ten requests, the answers, channel C
  latch      WHERE IT BREAKS: latch.asm, the joystick read with the
             interrupts on
  photos     the screens against what the player had when show ran
  prices     the comments' prices, and where the time goes
  answers    the workshop, tried (for Appendix I)
  openmsx    all of it again with every other build (tools/versions.py)
"""
import json
import shutil
import struct
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
import meas35      # noqa: E402  (chapter 35: the screens)
sys.path.insert(0, str(REPO / "ch36"))
import psg36       # noqa: E402  (chapter 36: the PSG's model)
sys.path.insert(0, str(HERE))
import gen37       # noqa: E402
import music37     # noqa: E402
import player37    # noqa: E402
sys.path.remove(str(HERE))
sys.path.insert(0, str(HERE))      # gen37 put other chapters first: this folder's files win
for mod in ("vdpscreen", "walk"):
    sys.modules.pop(mod, None)
import vdpscreen   # noqa: E402
import walk        # noqa: E402

assert Path(vdpscreen.__file__).parent == HERE and Path(walk.__file__).parent == HERE
assert Path(psg36.__file__).parent == REPO / "ch36"

CAPS = HERE / "captures"
SHOTS = HERE / "shots"
EU, JP = gen37.EU, gen37.JP
TAG = {EU: "eu", JP: "jp"}
CLOCK = music37.CLOCK
RATE = CLOCK / psg36.SAMPLE_T
FRAME_T = {EU: 71364, JP: 59736}
LINES = gen37.LINES
LINE_T = 228
VGM_RATE = 44100

# every write to the PSG's two output ports, every read of its input, with its T-state
WATCH = ('set ::wlog {}\n'
         'debug set_watchpoint write_io {0xA0 0xA1} {} '
         '{ lappend ::wlog "w [format %.17g [machine_info time]] [expr {$::wp_last_address & 255}] '
         '$::wp_last_value" }\n'
         'debug set_watchpoint read_io 0xA2 {} '
         '{ lappend ::wlog "r [format %.17g [machine_info time]]" }\n')


def rom(name):
    return HERE / f"{name}.rom"


def sym(name):
    return dbg.sym(HERE / f"{name}.sym")


def t_state(seconds):
    t = float(seconds) * CLOCK
    assert abs(t - round(t)) < 1e-3, seconds
    return round(t)


def isr_ret(name):
    """the address of isr's last RET, from the listing"""
    s = sym(name)
    code = walk.Walk(HERE / name).code
    return min(a for a, c in code.items() if a >= s["isr"] and c == b"\xc9")


# the frames each run lasts, counted from INIT, and whether it is recorded
TICKS = music37.TICKS


def frames_for(ticks, machine, pace="owed"):
    if pace == "fast" or machine == EU:
        return ticks
    if pace == "sixth":
        return -(-ticks * 6 // 5)
    return -(-ticks * LINES[EU] // LINES[JP])


RUNS = {  # name: (pace, ticks to run)
    "tune": ("owed", TICKS + 12),
    "effects": ("owed", 340),
    "fast": ("fast", TICKS + 12),
    "sixth": ("sixth", TICKS + 12),
    "latch": ("owed", 680),
}


# ---------------------------------------------------------------- the runs
_runs = {}


def session(name, machine):
    """{"ch": the channels' samples, "writes": [(T, register, byte)], "ports":
    [(T, "w"/"r", port, byte)], "isr": [T at isr], "ret": [T at its RET],
    "start": the recording's T-state, "vgm": the VGM file's bytes, "ram":
    the variables at the end}, made once a run"""
    key = (name, machine)
    if key in _runs:
        return _runs[key]
    out = SHOTS / f"{name}_{TAG[machine]}"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    pace, ticks = RUNS[name]
    frames = frames_for(ticks, machine, pace) + 4
    s = sym(name)
    bps = (f'debug set_bp {s["isr"]} {{}} {{ lappend ::wlog "i [format %.17g [machine_info time]]" }}\n'
           f'debug set_bp {isr_ret(name)} {{}} {{ lappend ::wlog "o [format %.17g [machine_info time]]" }}\n')
    start = "".join(f"set PSG_ch{c}_record {{{out / f'ch{c}.wav'}}}\n" for c in (1, 2, 3))
    start += 'L "rec [format %.17g [machine_info time]]"\nvgm_rec start PSG\n'
    ram = (f'binary scan [debug read_block memory {gen37.VARS_AT} 256] cu* v; L "ram $v"; ')
    stop = ('vgm_rec stop; L "end [format %.17g [machine_info time]]"; foreach x $::wlog { L $x }; ' + ram +
            "".join(f"set PSG_ch{c}_record {{}}; " for c in (1, 2, 3)))
    home = msxcap.make_home()
    log, script = home / "msxcap.log", home / "cap.tcl"
    script.write_text(msxcap.tcl_session(log, msxcap.rom_init(rom(name)), frames, {},
                                         msxcap.DEFAULT_SPEED, WATCH + bps, start, stop))
    msxcap.run_openmsx(rom(name), machine, script, home, 1200)
    lines = log.read_text().splitlines() if log.exists() else []
    assert "done" in lines, (name, machine, lines[-3:])
    vgms = sorted(home.rglob("*.vgm"))
    assert len(vgms) == 1, vgms
    vgm = vgms[0].read_bytes()
    (out / "tune.vgm").write_bytes(vgm)
    shutil.rmtree(home, ignore_errors=True)
    writes, ports, isr, ret, chosen, rec, end, ramv = [], [], [], [], 0, None, None, None
    for line in lines:
        p = line.split()
        if p[0] == "w":
            t, port, v = t_state(p[1]), int(p[2]), int(p[3])
            ports.append((t, "w", port, v, float(p[1])))
            if port == 0xA0:
                chosen = v
            else:
                writes.append((t, chosen & 15, v, chosen, float(p[1])))
        elif p[0] == "r":
            ports.append((t_state(p[1]), "r", 0xA2, chosen, float(p[1])))
        elif p[0] == "i":
            isr.append(t_state(p[1]))
        elif p[0] == "o":
            ret.append(t_state(p[1]))
        elif p[0] == "rec":
            rec = t_state(p[1])
        elif p[0] == "end":
            end = float(p[1])
        elif p[0] == "ram":
            ramv = [int(x) for x in p[1:]]
    ch = []
    for c in (1, 2, 3):
        w = wave.open(str(out / f"ch{c}.wav"))
        assert w.getnchannels() == 1 and w.getsampwidth() == 2 and w.getframerate() == round(RATE)
        ch.append(np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(int))
    assert len({len(x) for x in ch}) == 1
    r = {"ch": ch, "writes": writes, "ports": ports, "isr": isr, "ret": ret, "start": rec,
         "end": end, "vgm": vgm, "ram": ramv, "frames": frames, "machine": machine, "name": name}
    _runs[key] = r
    return r


def piece(name, machine, channel, first, n):
    """N samples of a channel from FIRST, into captures/ for the figures"""
    r = session(name, machine)
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


def sample_at(r, t):
    """the first sample at or after T-state T"""
    return max(0, -(-(t - r["start"] - psg36.FIRST) // psg36.SAMPLE_T))


# ---------------------------------------------------------------- bytes
def table(mem, at, ends):
    out = []
    while True:
        out.append(mem[at])
        if mem[at] in ends:
            return out
        at += 1


def decode(stem):
    """the music in a cartridge, read back the way the player reads it"""
    p = player37.Player(HERE / stem)
    mem, s = p.mem, p.sym
    notes = [p.word(s["notes"] + 2 * n) for n in range(music37.HIGHEST + 1)]
    instruments = []
    for k in range(len(music37.INSTRUMENTS)):
        at = s["instruments"] + 6 * k
        vol = table(mem, p.word(at), {music37.END})[:-1]
        pit = [player37.s8(v) if v not in (music37.LOOP, music37.HOLD) else v
               for v in table(mem, p.word(at + 2), {music37.LOOP, music37.HOLD})]
        instruments.append((vol, pit, mem[at + 4], mem[at + 5]))
    effects = [tuple(mem[s["effects"] + 4 * k:s["effects"] + 4 * k + 4]) for k in range(len(music37.EFFECTS))]
    song, at = [], s["song"]
    while p.word(at):
        song.append(tuple(p.word(at + 2 * c) for c in range(3)))
        at += 6
    pats = {}
    for step in song:
        for a in step:
            evs, q = [], a
            while mem[q] != music37.END:
                k = None
                if mem[q] & 0x80:
                    k, q = mem[q] & 0x7F, q + 1
                evs.append((k, mem[q], mem[q + 1]))
                q += 2
            pats[a] = evs
    return {"notes": notes, "instruments": instruments, "effects": effects, "song": song,
            "patterns": pats, "sym": s}


def bytes_():
    out = {}
    want = music37.patterns()
    for name in gen37.PROGRAMS:
        d = decode(name)
        s = d["sym"]
        assert s["notes"] & 255 == 0
        assert d["notes"] == [0] + [music37.period(n) for n in range(1, music37.HIGHEST + 1)]
        for got, (iname, levels, pitches, mix, noisep) in zip(d["instruments"], music37.INSTRUMENTS):
            assert got == (levels, pitches, mix, noisep), (iname, got)
        for got, (ename, prio, instr, n, ticks) in zip(d["effects"], music37.EFFECTS):
            assert got == (prio, 0x80 | music37.INSTR[instr], music37.note(n), ticks), (ename, got)
        names = {s[k]: k for k in want}
        assert [tuple(names[a] for a in step) for step in d["song"]] == music37.SONG
        for a, evs in d["patterns"].items():
            assert evs == want[names[a]], names[a]
        # the music's bytes, from the notes to the last pattern's END
        last = max(d["patterns"])
        end = last + len(music37.pattern_bytes(want[names[last]]))
        sizes = music37.sizes()
        assert end - s["notes"] == sum(sizes.values())
        engine_end = min(s[k] for k in ("sfx", "joy", "show") if k in s)
        out[name] = {"music": end - s["notes"], "engine": engine_end - s["isr"]}
        if "sfx" in s:
            out[name]["sfx"] = s["request"] - s["sfx"]
    out["sizes"] = music37.sizes()
    out["patterns"] = len(want)
    out["events"] = sum(len(e) for e in want.values())
    out["ticks"] = music37.TICKS
    out["seconds_eu"] = round(music37.TICKS * FRAME_T[EU] / CLOCK, 3)
    out["dump_bytes"] = music37.TICKS * gen37.SHADOW_REGS
    return out


# ---------------------------------------------------------------- writes
def pace_frames(pace, machine, n):
    """for each of N frames from the first interrupt: does the player tick?"""
    out, owed, skip = [], 0, 6 if machine == JP else 0
    for _ in range(n):
        if pace == "fast":
            out.append(True)
        elif pace == "sixth":
            if skip == 0:
                out.append(True)
            else:
                skip -= 1
                out.append(skip != 0)
                if skip == 0:
                    skip = 6
        else:
            owed += LINES[machine]
            out.append(owed >= LINES[EU])
            if owed >= LINES[EU]:
                owed -= LINES[EU]
    return out


def requests():
    return [(t, music37.FX[f]) for t, f in gen37.REQUESTS]


def model_sent(name, n):
    sent, answers, _ = player37.run(HERE / name, n, requests() if name == "effects" else ())
    return sent, answers


def by_isr(r):
    """[(isr's T, its RET's T, [(T, register, byte) written in it])], and the writes outside"""
    out, k, outside = [], 0, []
    ws = [w for w in r["writes"] if w[0] > r["isr"][0] - FRAME_T[r["machine"]]]
    for i, o in zip(r["isr"], r["ret"]):
        assert i < o
        inside = []
        while k < len(ws) and ws[k][0] < i:
            outside.append(ws[k])
            k += 1
        while k < len(ws) and ws[k][0] <= o:
            inside.append(ws[k])
            k += 1
        out.append((i, o, inside))
    return out, outside + ws[k:]


def writes():
    out = {}
    for name in ("tune", "effects", "fast", "sixth"):
        pace = RUNS[name][0]
        for m in (EU, JP):
            r = session(name, m)
            groups, outside = by_isr(r)
            assert not outside, (name, m, outside[:3])
            ticks = pace_frames(pace, m, len(groups))
            got = [g[2] for g in groups]
            assert [bool(w) for w in got] == ticks, (name, m)
            sent, answers = model_sent(name, sum(ticks))
            k = 0
            for w in got:
                if w:
                    assert [(reg, v) for _, reg, v, *_ in w] == list(enumerate(sent[k])), (name, m, k)
                    k += 1
            r7 = [v for w in got for _, reg, v, *_ in w if reg == 7]
            assert r7 and all(v & 0xC0 == 0x80 for v in r7)        # bit 7 at 1, bit 6 at 0
            assert all(reg <= 10 for w in got for _, reg, *_ in w)
            out.setdefault(name, {})[TAG[m]] = {"frames": len(groups), "ticks": k,
                                                 "writes": sum(len(w) for w in got), "r7_writes": len(r7)}
    return out


# ---------------------------------------------------------------- walk
IN_ISR = 18             # walk.call's CALL, which the interrupt does not make
RET_T = 11


def walked(name, machine, frames):
    """walk.py through INIT and then FRAMES frames: for each, isr's writes as
    (T-state from isr's first instruction, register, byte), its T-states to
    the start of its RET, and whether it ticked; effects.asm's requests made
    after each, as its main program makes them"""
    w = walk.Walk(HERE / name)
    w.mem[0x002B] = 0x80 if machine == EU else 0x00      # bit 7: the 50 Hz machine
    w.run("init", "main")
    out = []
    for _ in range(frames):
        t0, n = w.t + IN_ISR, len(w.ports)
        t = w.call("isr") - IN_ISR - RET_T
        chosen, ws = None, []
        for at, port, v in w.ports[n:]:
            if port == 0xA0:
                chosen = v
            elif port == 0xA1:
                ws.append((at - t0, chosen & 15, v))
        out.append((ws, t))
        if name == "effects":
            w.call("request")
    return out, w


def walk_():
    out = {}
    for name in ("tune", "effects", "fast", "sixth"):
        for m in (EU, JP):
            r = session(name, m)
            groups, _ = by_isr(r)
            model, w = walked(name, m, len(groups))
            for (i, o, ws), (mws, t) in zip(groups, model):
                assert [(x[0] - i, x[1], x[2]) for x in ws] == mws, (name, m)
                assert o - i == t, (name, m, o - i, t)
            lengths = [t for _, t in model]
            offs = sorted({tuple(x[0] for x in mws) for mws, _ in model if mws})
            assert len(offs) == 1, offs                      # every tick writes at the same T-states
            out.setdefault(name, {})[TAG[m]] = {"frames": len(groups), "isr_min": min(lengths),
                                                "isr_max": max(lengths), "r0": offs[0][0], "r10": offs[0][-1],
                                                "step": offs[0][1] - offs[0][0]}
            if name == "tune" and m == EU:
                out["offsets"] = list(offs[0])
            if name == "effects":
                said = w.mem[gen37.VARS_AT + gen37.SAID_AT:gen37.VARS_AT + gen37.SAID_AT + len(gen37.REQUESTS)]
                ram = r["ram"][gen37.SAID_AT:gen37.SAID_AT + len(gen37.REQUESTS)]
                assert list(said) == ram, (said, ram)
    return out


# ---------------------------------------------------------------- vgm
def read_vgm(data):
    """the header's fields and the writes: [(44,100ths of a second, register, byte)]"""
    assert data[:4] == b"Vgm "
    head = {"eof": struct.unpack_from("<I", data, 4)[0] + 4, "version": struct.unpack_from("<I", data, 8)[0],
            "samples": struct.unpack_from("<I", data, 0x18)[0],
            "data": 0x34 + struct.unpack_from("<I", data, 0x34)[0],
            "ay_clock": struct.unpack_from("<I", data, 0x74)[0]}
    assert head["eof"] == len(data)
    at, t, out = head["data"], 0, []
    while True:
        c = data[at]
        if c == 0xA0:
            out.append((t, data[at + 1], data[at + 2]))
            at += 3
        elif c == 0x61:
            t += struct.unpack_from("<H", data, at + 1)[0]
            at += 3
        elif c == 0x66:
            assert at + 1 == len(data)
            break
        else:
            raise ValueError(f"VGM command ${c:02X}")
    return head, out, t


def vgm_model(r):
    """what vgm_rec writes, from the debugger's log: every write to R0-R13 from
    INIT on, at int((t - t0) x 44,100), t0 the first of them, in seconds"""
    first_isr = r["isr"][0]
    ws = [w for w in r["writes"] if w[0] >= first_isr - FRAME_T[r["machine"]] and w[3] < 14]
    t0 = ws[0][4]
    return [(int((w[4] - t0) * VGM_RATE), w[3], w[2]) for w in ws], int((r["end"] - t0) * VGM_RATE), t0


def vgm():
    out = {}
    for name, m in (("tune", EU), ("tune", JP), ("latch", EU), ("latch", JP)):
        r = session(name, m)
        head, got, t = read_vgm(r["vgm"])
        want, total, t0 = vgm_model(r)
        assert got == want, (name, m, [(a, b) for a, b in zip(got, want) if a != b][:3], len(got), len(want))
        assert head["samples"] == total == t, (head["samples"], total, t)
        assert head["ay_clock"] == 1789773 and head["version"] == 0x161     # half the clock, rounded up
        out[f"{name}_{TAG[m]}"] = {"writes": len(got), "samples": total, "bytes": len(r["vgm"]),
                                   "seconds": round(total / VGM_RATE, 3)}
    return out


# ---------------------------------------------------------------- model
MODEL_RUNS = [(n, m) for n in ("tune", "effects", "fast", "sixth", "latch") for m in (EU, JP)]


# chapter 36's rules count a write from the T-state the debugger gives it,
# the start of an OUT (n),A, whose write to the port is its third machine
# cycle, 8 T-states in (5 + 3). tochip writes with OUTI, whose cycles are
# 5, 6 and 3 before its write, 14 in: six T-states later
OUTI_LATER = (5 + 6 + 3) - (5 + 3)


def chip_writes(r, later=OUTI_LATER):
    """the writes as the PSG gets them: those made inside isr, by OUTI, later"""
    spans = list(zip(r["isr"], r["ret"]))
    out, k = [], 0
    for w in r["writes"]:
        while k < len(spans) and spans[k][1] < w[0]:
            k += 1
        inside = k < len(spans) and spans[k][0] <= w[0] <= spans[k][1]
        out.append((w[0] + (later if inside else 0), w[1], w[2]))
    return out


def model_of(r, later=OUTI_LATER):
    return [np.array(x) for x in psg36.run(chip_writes(r, later), r["start"], len(r["ch"][0]))]


def model():
    out, total = {}, 0
    for name, m in MODEL_RUNS:
        r = session(name, m)
        mod = model_of(r)
        bad = sum(int(np.count_nonzero(mod[c] != r["ch"][c])) for c in range(3))
        assert bad == 0, (name, m, bad)
        out.setdefault(name, {})[TAG[m]] = len(r["ch"][0])
        total += 3 * len(r["ch"][0])
    # the six T-states, needed: the tune's recordings without them, and a T-state either way
    r = session("tune", EU)
    shifts = {}
    for later in (0, OUTI_LATER - 1, OUTI_LATER + 1):
        mod = model_of(r, later)
        shifts[str(later)] = sum(int(np.count_nonzero(mod[c] != r["ch"][c])) for c in range(3))
    assert all(shifts.values())
    return {"recordings": len(MODEL_RUNS), "runs": out, "samples": total, "off": 0,
            "outi_later": OUTI_LATER, "tune_eu_off_with": shifts}


# ---------------------------------------------------------------- pace
def tick_times(name, m):
    """the T-state of each tick's first write (R0's byte), and of each frame's interrupt"""
    groups, _ = by_isr(session(name, m))
    return [ws[0][0] for _, _, ws in groups if ws], [i for i, _, _ in groups]


def pace():
    out = {}
    loop = music37.TICKS
    eu, eu_int = tick_times("tune", EU)
    for name in ("tune", "fast", "sixth"):
        for m in (EU, JP):
            t, ints = tick_times(name, m)
            # the tune from its first bar's first tick (sent at tick 2) to its first bar again
            length = t[loop + 1] - t[1]
            lag = [(t[k] - t[1]) - (eu[k] - eu[1]) for k in range(1, loop + 2)]
            gaps = sorted({t[k + 1] - t[k] for k in range(len(t) - 1)})
            res = {"length_t": length, "seconds": round(length / CLOCK, 4),
                   "against_eu_t": length - (eu[loop + 1] - eu[1]),
                   "lag_lines": [round(min(lag) / LINE_T, 2), round(max(lag) / LINE_T, 2)],
                   "gaps_frames": sorted({round(g / FRAME_T[m]) for g in gaps}),
                   "ticks_in_313_frames": None}
            late = [(t[k] - ints[0]) - (eu[k] - eu_int[0]) for k in range(loop + 2)]
            res["late_lines"] = [round(min(late) / LINE_T), round(max(late) / LINE_T)]
            res["late_first_bar"] = [round(late[1] / LINE_T), round(late[loop + 1] / LINE_T)]
            if m == JP:
                n = len(ints)
                ticked = [bool(ws) for _, _, ws in by_isr(session(name, m))[0]]
                res["ticks_in_313_frames"] = sorted({sum(ticked[a:a + 313]) for a in range(n - 313)})
                res["first_frames"] = ticked[:14]
                res["frames"] = (t[loop + 1] - t[1] + FRAME_T[m] // 2) // FRAME_T[m]
            out.setdefault(name, {})[TAG[m]] = res
    out["eu_rate"] = round(CLOCK / FRAME_T[EU], 4)
    out["jp_rate"] = round(CLOCK / FRAME_T[JP], 4)
    out["tune_seconds"] = round(loop * FRAME_T[EU] / CLOCK, 4)
    return out


# ---------------------------------------------------------------- effects
C_REGS, AB_REGS = (4, 5, 6, 10), (0, 1, 2, 3, 8, 9)
C_BITS, AB_BITS = 0b00100100, 0b00011011


def effects():
    r = session("effects", EU)
    n = RUNS["effects"][1]
    sent, answers = model_sent("effects", n)
    alone, _, _ = player37.run(HERE / "effects", n)       # the same cartridge, nothing asked for
    said = r["ram"][gen37.SAID_AT:gen37.SAID_AT + len(gen37.REQUESTS)]
    assert said == [0 if a else 255 for a in answers], (said, answers)
    assert session("effects", JP)["ram"][gen37.SAID_AT:gen37.SAID_AT + len(gen37.REQUESTS)] == said
    # the ticks whose bytes differ from the music alone: only C's, and only while an effect sounds
    differ, r6_only = [], []
    for k, (a, b) in enumerate(zip(sent, alone)):
        assert all(a[i] == b[i] for i in AB_REGS) and a[7] & AB_BITS == b[7] & AB_BITS, k
        noise = a[7] & 0b00111000 != 0b00111000     # R6 is heard only with a noise open
        if any(a[i] != b[i] for i in C_REGS if i != 6 or noise) or a[7] & C_BITS != b[7] & C_BITS:
            differ.append(k + 1)                # the tick that sends them
        elif a[6] != b[6]:
            r6_only.append(k + 1)
    # each request: what was sounding, the answer, and the ticks it sounded
    rows, playing = [], None
    sounding = set()
    prio = {name: p for name, p, *_ in music37.EFFECTS}
    length = {name: t for name, _, _, _, t in music37.EFFECTS}
    for k, ((tick, fx), ok) in enumerate(zip(gen37.REQUESTS, answers)):
        start = tick + 2                        # asked after play's tick, sent a tick later
        before = None
        if playing and playing[1] + length[playing[0]] > start:
            before = playing[0]
        rows.append({"tick": tick, "effect": fx, "priority": prio[fx], "sounding": before,
                     "answer": "taken" if ok else "refused"})
        if ok:
            if playing:                         # cut short where the new one starts
                sounding -= set(range(start, playing[1] + length[playing[0]]))
            playing = (fx, start)
            sounding |= set(range(start, start + length[fx]))
    # a tick of an effect can send the same bytes the music would: never here
    assert set(differ) <= sounding
    gone = sorted(sounding - set(differ))
    return {"requests": rows, "said": said, "effect_ticks": len(sounding), "differ_ticks": len(differ),
            "r6_only": [min(r6_only), max(r6_only), len(r6_only)] if r6_only else None,
            "same_as_music": gone, "first_heard": min(differ), "last_heard": max(differ)}


# ---------------------------------------------------------------- latch
def inside(spans, t):
    """is T-state T inside one of the (isr, RET) spans?"""
    import bisect
    k = bisect.bisect_right(spans, (t, float("inf"))) - 1
    return k >= 0 and spans[k][0] <= t <= spans[k][1]


def misreads(m):
    """{isr's number, from 1: the byte joy read} for the frames whose interrupt came
    between joy's choice of R14 and its read: R10, the level tochip had just sent"""
    r = session("latch", m)
    spans = list(zip(r["isr"], r["ret"]))
    out, last_main = {}, None
    k = 0
    for t, kind, port, v, *_ in r["ports"]:
        if t < r["isr"][0]:
            continue
        while k < len(spans) and spans[k][1] < t:
            k += 1
        if k < len(spans) and spans[k][0] <= t <= spans[k][1]:
            continue
        if kind == "w" and port == 0xA0:
            last_main = v
        elif kind == "r" and last_main == 14 and v == 10:
            out[k] = None                       # the k-th isr (from 1) came before it
    for k in out:
        ws = [w for w in r["writes"] if spans[k - 1][0] <= w[0] <= spans[k - 1][1] and w[1] == 10]
        out[k] = ws[-1][2]
    return out


def latch():
    out = {}
    for m in (EU, JP):
        r = session("latch", m)
        spans = list(zip(r["isr"], r["ret"]))
        first = r["isr"][0]
        writes = [w for w in r["writes"] if w[0] >= first]
        # joy chooses R15 and writes it, then chooses R14 and reads it: a write of the
        # main program that reached R10 came after an interrupt, whose tochip chose R10
        main_w = [w for w in writes if not inside(spans, w[0])]
        to_r10 = [w for w in main_w if w[3] == 10]
        assert all(w[3] in (10, 15) for w in main_w)
        held, last10 = {}, None                 # what R10 held when each came
        for w in writes:
            if w[3] == 10:
                if not inside(spans, w[0]):
                    held[w[0]] = last10
                last10 = w[2]
        loud = [w for w in to_r10 if w[2] == 0x8F]             # R15's byte: level 15
        louder = [w for w in loud if held[w[0]] != 15]
        assert all(w[2] == held[w[0]] for w in to_r10 if w[2] != 0x8F)   # the rest: R10's own level
        reads = [p for p in r["ports"] if p[1] == "r" and p[0] >= first and not inside(spans, p[0])]
        of_r10 = [p for p in reads if p[3] == 10]
        assert all(p[3] in (10, 14, 15) for p in reads)
        # a read of R10 in place of R15 comes before a write that puts back R10's own
        # level; one in place of R14 is what joy hands back as the joystick
        out[TAG[m]] = {"frames": len(spans), "ticks": sum(1 for _, _, ws in by_isr(r)[0] if ws),
                       "writes_by_main": len(main_w), "reached_r10": len(to_r10),
                       "r15_byte": len(loud), "louder": len(louder),
                       "own_level_back": len(to_r10) - len(loud), "reads_by_main": len(reads),
                       "reads_of_r10": len(of_r10), "r14_misreads": len(misreads(m)),
                       "louder_frames": sorted({sum(1 for i in r["isr"] if i < w[0]) for w in loud})[:12]}
    return out


# ---------------------------------------------------------------- photos
STATE = [("ticks", 0, 2), ("barno", 9, 1), ("rowno", 10, 1), ("levels", gen37.SHADOW_AT + 8, 3),
         ("fx", gen37.SHADOW_AT + gen37.SHADOW_REGS + 3 * gen37.CHAN + gen37.OFFSET["WAITS"], 1),
         ("prio", gen37.SHADOW_AT + gen37.SHADOW_REGS + 3 * gen37.CHAN + gen37.OFFSET["PRIO"], 1),
         ("port1", 14, 1)]


def state_of(ram):
    out = {}
    for key, at, n in STATE:
        v = ram[at:at + n]
        out[key] = v[0] | v[1] << 8 if key == "ticks" else (list(v) if n > 1 else v[0])
    return out


def screen_of(name, st):
    fx, joy = name == "effects", name == "latch"
    n = meas35.gen34.page(gen37.screen_texts(f"{name}.asm", fx, joy))
    sc = gen37.SCREEN
    meas35.put(n, sc["bar"][0], sc["bar"][2], f"{st['barno']:02d}")
    meas35.put(n, sc["row"][0], sc["row"][2], f"{st['rowno']:02d}")
    meas35.put(n, sc["tick"][0], sc["tick"][2], f"{st['ticks']:04X}")
    for k, ch in enumerate("ABC"):
        row, _, col = sc[ch]
        lv = st["levels"][k]
        meas35.put(n, row, col, [gen37.BOX_FULL] * lv + [gen37.BOX_EMPTY] * (15 - lv))
        meas35.put(n, row, gen37.LEVEL_COL, f"{lv:02d}")
    if fx:
        meas35.put(n, gen37.FX_ROW, gen37.FX_COLS[1], f"{st['fx']:02d}")
        meas35.put(n, gen37.FX_ROW, gen37.FX_COLS[3], f"{st['prio']:02d}")
    if joy:
        meas35.put(n, gen37.JOY_ROW, gen37.JOY_COL, meas35.boxes(st["port1"], 0))
        meas35.put(n, gen37.JOY_ROW, gen37.JOY_COL + 10, f"{st['port1']:02X}")
    return meas35.screen(n)


def model_states(name, m, frames):
    """the state show finds after each of FRAMES interrupts, from player37.py and pace"""
    ticked = pace_frames(RUNS[name][0], m, frames)
    p = player37.Player(HERE / name)
    pending = requests() if name == "effects" else []
    out = []
    for t in ticked:
        if t:
            p.play()
        if pending and p.ticks >= pending[0][0]:
            p.sfx(pending.pop(0)[1])
        x = p.chans[3]
        out.append({"ticks": p.ticks, "barno": p.barno, "rowno": p.rowno, "levels": p.shadow[8:11],
                    "fx": x["WAITS"], "prio": x["PRIO"]})
    return out


SECONDS = 13                    # figure 37.1: the three screens this far in
PHOTO_RUNS = [("tune", EU), ("tune", JP), ("fast", JP), ("effects", EU), ("latch", EU)]


def photos():
    out = {}
    for name, m in PHOTO_RUNS:
        s = sym(name)
        n = round(SECONDS * CLOCK / FRAME_T[m]) + 4
        tcl = (meas35.F0 + meas35.TOO_FAST +
               f'debug set_bp {s["show"]} {{}} {{ binary scan [debug read_block memory {gen37.VARS_AT} 128] '
               f'cu* v; L "v [expr {{[machine_info VDP_frame_count] - $::f0}}] $v" }}\n')
        lines = msxcap.run_tcl(rom(name), n + 2, tcl, machine=m)
        assert not [l for l in lines if l.startswith("fast")]
        vals = {int(l.split()[1]): state_of([int(x) for x in l.split()[2:]]) for l in lines if l.startswith("v ")}
        first = min(vals)
        model = model_states(name, m, max(vals) - first + 1)
        keys = ["ticks", "barno", "rowno", "levels"] + (["fx", "prio"] if name == "effects" else [])
        for f, st in vals.items():
            assert all(st[k] == model[f - first][k] for k in keys), (name, m, f, st, model[f - first])
        # the frame SECONDS in, the frame after it, and two early ones
        at = first + round(SECONDS * CLOCK / FRAME_T[m]) - 1
        shots = sorted({first + 40, first + 41, at, at + 1})
        if name == "latch":
            # joy's byte: R14's $BF, but in a frame whose interrupt fell between joy's choice of
            # R14 and its read, R10's: the level tochip had just sent
            misread = misreads(m)
            for f, st in vals.items():
                k = f - first + 1
                assert st["port1"] == (misread[k] if k in misread else 0xBF if k > 1 else 0xFF), (f, st)
            wrong = sorted(f for f in vals if f - first + 1 in misread)
            shots = sorted({wrong[0], wrong[0] + 1, at})
            out["latch_misread_frames"] = len([f for f in vals if f - first + 1 in misread])
        pngs = msxcap.capture(rom(name), shots, CAPS, f"{name}_{TAG[m]}_f", machine=m)
        lags = [e for e in (-2, -1, 0) if all(f + e in vals and
                                              meas35.mismatch(screen_of(name, vals[f + e]), meas35.codes(pngs[f])) == 0
                                              for f in shots)]
        assert len(lags) == 1, (name, m, lags)
        out[f"{name}_{TAG[m]}"] = {"frames": len(vals), "first": first, "shots": shots, "lag": lags[0],
                                   "at": at, "seen": {str(f): vals[f + lags[0]] for f in shots}}
    return out


# ---------------------------------------------------------------- prices
import re  # noqa: E402
sys.path.insert(0, str(REPO / "ch14"))
import cycles  # noqa: E402  (chapter 14)

PRICE = re.compile(r"^\s*(\d+)(?:, or (\d+))?(?:\s|$)")


def price(code):
    """the MSX price of an instruction: one number, or taken and not taken"""
    op = code[0]
    if op in (0x20, 0x28, 0x30, 0x38):
        return (13, 8)
    if op == 0x10:
        return (14, 9)
    if op & 0xC7 == 0xC0:
        return (12, 6)
    if op & 0xC7 == 0xC4:
        return (18, 11)
    fixed = {0x18: 13, 0xC3: 11, 0xCD: 18, 0xC9: 11}
    if op in fixed:
        return (fixed[op],)
    if op & 0xC7 == 0xC2:
        return (11,)
    if op == 0xED and code[1] in (0xA0, 0xA3):          # LDI, OUTI (chapter 13)
        return (18,)
    return (cycles.msx(code),)


def priced_lines(name):
    """(address, source, the comment's prices) of every line from isr on whose comment starts with them"""
    out = []
    s = sym(name)
    for line in (HERE / f"{name}.lst").read_text().splitlines():
        m = dbg.LST.match(line)
        if not m or "..." in m.group(3)[1:13]:
            continue
        _, a, code, src = dbg.lst_fields(m)
        if not code or a < s["isr"] or ";" not in src or src.strip().startswith(";"):
            continue
        c = PRICE.match(src.split(";", 1)[1])
        if c:
            out.append((a, bytes(code), tuple(int(x) for x in c.groups() if x)))
    return out


def prices():
    out = {"checked": {}}
    for name in gen37.PROGRAMS:
        lines = priced_lines(name)
        for a, code, said in lines:
            assert price(code) == said, (name, hex(a), code.hex(), said, price(code))
        out["checked"][name] = len(lines)
    # isr's length by what the frame does, from walk.py, which the debugger agreed with in every frame
    w = walk.Walk(HERE / "tune")
    w.mem[0x002B] = 0x80
    w.run("init", "main")
    kinds = {}
    s = w.sym
    for f in range(TICKS + 2):
        rows = w.mem[s["tick"]] == 1             # this tick reads a row
        before = w.mem[s["barno"]]
        t = w.call("isr") - IN_ISR - RET_T
        kind = "no row" if not rows else ("a row and a new bar" if w.mem[s["barno"]] != before else "a row")
        kinds.setdefault(kind, []).append(t)
    out["isr_eu"] = {k: [min(v), max(v), len(v)] for k, v in kinds.items()}
    # the parts every tick pays the same for
    w2 = walk.Walk(HERE / "tune")
    w2.mem[0x002B] = 0x80
    w2.run("init", "main")
    out["tochip"] = w2.call("tochip") - IN_ISR
    out["pace_tick"] = w2.call("pace") - IN_ISR
    w2.mem[0x002B] = 0
    w3 = walk.Walk(HERE / "tune")
    w3.run("init", "main")
    paces = sorted({w3.call("pace") - IN_ISR for _ in range(313)})
    out["pace_jp"] = paces
    w3 = walk.Walk(HERE / "tune")
    w3.run("init", "main")
    out["isr_skip"] = w3.call("isr") - IN_ISR - RET_T       # the 60 Hz machine's first frame: no tick
    # effects.asm: a tick with an effect over C, and sfx
    w4 = walk.Walk(HERE / "effects")
    w4.mem[0x002B] = 0x80
    w4.run("init", "main")
    fx = []
    sf = []
    for f in range(340):
        on = w4.mem[s["chan_x"] + gen37.OFFSET["WAITS"]] if "chan_x" in s else 0
        t = w4.call("isr") - IN_ISR - RET_T
        fx.append((t, on))
        before = w4.t
        n0 = w4.mem[w4.sym["nextrq"]] | w4.mem[w4.sym["nextrq"] + 1] << 8
        t_rq = w4.call("request") - IN_ISR
        n1 = w4.mem[w4.sym["nextrq"]] | w4.mem[w4.sym["nextrq"] + 1] << 8
        if n1 != n0:
            sf.append(t_rq)
    out["isr_effect"] = [min(t for t, on in fx if on), max(t for t, on in fx if on)]
    out["request_made"] = [min(sf), max(sf)]
    out["show"] = walk.Walk(HERE / "tune").call("show")
    return out


# ---------------------------------------------------------------- pieces
def tick_sample(name, m, k):
    """the first sample of tick K's sending (its R0), K from 1"""
    r = session(name, m)
    t, _ = tick_times(name, m)
    return sample_at(r, t[k - 1])


FIG_TICKS_BAR = (2, 2 + music37.ROWS * music37.SPEED)          # the first bar, as it is sent
FIG_KICK, FIG_SNARE = (2, 12), (12, 32)                          # bar 1: the kick; the hat and the snare
FIG_FX = (288, 338)                                               # COIN, BOOM over it, the drums again
FIG_SECONDS = 5                                                   # figure 37.4
FIG_LATCH = (2, 62)                                               # latch.asm's first sixty ticks


def pieces():
    out = {}
    a, b = FIG_TICKS_BAR
    out["bar"] = [piece("tune", EU, c, tick_sample("tune", EU, a), tick_sample("tune", EU, b) -
                        tick_sample("tune", EU, a)) for c in range(3)]
    out["kick"] = piece("tune", EU, 2, tick_sample("tune", EU, FIG_KICK[0]),
                        tick_sample("tune", EU, FIG_KICK[1]) - tick_sample("tune", EU, FIG_KICK[0]))
    out["snare"] = piece("tune", EU, 2, tick_sample("tune", EU, FIG_SNARE[0]),
                         tick_sample("tune", EU, FIG_SNARE[1]) - tick_sample("tune", EU, FIG_SNARE[0]))
    a, b = FIG_FX
    out["fx"] = [piece(n, EU, 2, tick_sample(n, EU, a), tick_sample(n, EU, b) - tick_sample(n, EU, a))
                 for n in ("tune", "effects")]
    n = round(FIG_SECONDS * RATE)
    out["hz"] = [piece(name, m, 0, tick_sample(name, m, 2), n) for name, m in (("tune", EU), ("tune", JP),
                                                                              ("fast", JP))]
    a, b = FIG_LATCH
    out["latch"] = [piece(name, EU, 2, tick_sample(name, EU, a), tick_sample(name, EU, b) -
                          tick_sample(name, EU, a)) for name in ("tune", "latch")]
    # a burst close up, from a little before its tick's sending to a little after the next:
    # the first of those that make channel C loudest from the quietest
    r = session("latch", EU)
    spans = list(zip(r["isr"], r["ret"]))
    t, _ = tick_times("latch", EU)
    best, loud = None, []
    for w in r["writes"]:
        if w[0] > r["isr"][0] and w[3] == 10 and w[2] == 0x8F and not inside(spans, w[0]):
            k = sum(1 for i in r["isr"] if i < w[0])        # the isr before it, from 1
            level = [x for x in r["writes"] if t[k - 1] <= x[0] < w[0] and x[3] == 10][-1][2]
            loud.append((level, k, w))
    ks = {k for _, k, _ in loud}
    for level, k, w in loud:                                  # one on its own: the next tick sounds right
        if k + 1 not in ks and k - 1 not in ks and (best is None or level < best[0]):
            best = (level, k, w)
    level, k, w = best
    a = sample_at(r, t[k - 1]) - 1000
    out["burst"] = piece("latch", EU, 2, a, sample_at(r, t[k]) + 1000 - a)
    out["burst_at"] = {"tick": k, "level_before": level, "write_t_after_r0": w[0] - t[k - 1],
                       "samples_loud": sample_at(r, t[k] + 10 * 48 + OUTI_LATER) - sample_at(r, w[0])}
    return out


# ---------------------------------------------------------------- answers
import subprocess  # noqa: E402
import tempfile    # noqa: E402


def assemble(name, asm, inc=None):
    """a variant of a program, assembled in a folder of its own: its stem"""
    d = Path(tempfile.mkdtemp(prefix="ch37_"))
    for f in ("msx.inc", "bios.inc"):
        shutil.copy(HERE / f, d / f)
    (d / "music.inc").write_text(inc if inc is not None else (HERE / "music.inc").read_text())
    (d / f"{name}.asm").write_text(asm)
    r = subprocess.run(["sjasmplus", "--nologo", "--msg=err", "--syntax=bFw", f"--sym={name}.sym",
                        f"--lst={name}.lst", f"{name}.asm"], cwd=d, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return d / name


def logged(stem, machine, frames):
    """a variant run in openMSX: its writes (T, register, byte, chosen), its reads
    (T, chosen), and isr's start and end in each frame"""
    s = dbg.sym(stem.with_suffix(".sym"))
    code = walk.Walk(stem).code
    ret = min(a for a, c in code.items() if a >= s["isr"] and c == b"\xc9")
    tcl = (WATCH + f'debug set_bp {s["isr"]} {{}} {{ lappend ::wlog "i [format %.17g [machine_info time]]" }}\n'
           f'debug set_bp {ret} {{}} {{ lappend ::wlog "o [format %.17g [machine_info time]]" }}\n')
    home = msxcap.make_home()
    log, script = home / "msxcap.log", home / "cap.tcl"
    script.write_text(msxcap.tcl_session(log, msxcap.rom_init(stem.with_suffix(".rom")), frames, {},
                                         msxcap.DEFAULT_SPEED, tcl, "", 'foreach x $::wlog { L $x }'))
    msxcap.run_openmsx(stem.with_suffix(".rom"), machine, script, home, 1200)
    lines = log.read_text().splitlines()
    assert "done" in lines
    shutil.rmtree(home, ignore_errors=True)
    writes, reads, isr, ret_, chosen = [], [], [], [], 0
    for line in lines:
        p = line.split()
        if p[0] == "w":
            if int(p[2]) == 0xA0:
                chosen = int(p[3])
            else:
                writes.append((t_state(p[1]), chosen & 15, int(p[3]), chosen))
        elif p[0] == "r":
            reads.append((t_state(p[1]), chosen))
        elif p[0] == "i":
            isr.append(t_state(p[1]))
        elif p[0] == "o":
            ret_.append(t_state(p[1]))
    return writes, reads, list(zip(isr, ret_))


GUARD = """
; joy: latch.asm's, with each register it chooses kept in psgreg first, so
; that isr can choose it again before it returns. Uses A, B
joy:    ld b, a
        ld a, 15
        ld (psgreg), a
        out (PSG_ADDR), a       ; register 15
        in a, (PSG_READ)
        and $BF
        or b
        out (PSG_WRITE), a
        ld a, 14
        ld (psgreg), a
        out (PSG_ADDR), a       ; register 14
        in a, (PSG_READ)
        ret
"""


def guarded_latch():
    """the workshop's latch.asm: joy keeps its register in psgreg, and isr chooses it again"""
    asm = (HERE / "latch.asm").read_text()
    a = asm.index("; joy: A = $00 for port 1")
    b = asm.index("; show:", a)
    asm = asm[:a] + GUARD.lstrip("\n") + "\n" + asm[b:]
    old = "        call play               ; 18\n"
    assert asm.count(old) == 1
    asm = asm.replace(old, old + "        ld a, (psgreg)          ; the program's register, chosen again\n"
                                 "        out (PSG_ADDR), a\n")
    asm = asm.replace("port1   EQU VARS + 14", "psgreg  EQU VARS + 31            ; the register joy chose\n"
                                               "port1   EQU VARS + 14")
    return asm


def answers():
    out = {}
    # 1. SPEED 6: the tune's ticks, seconds and beats a minute
    inc = (HERE / "music.inc").read_text().replace("SPEED   EQU 5 ", "SPEED   EQU 6 ")
    stem = assemble("tune", (HERE / "tune.asm").read_text(), inc)
    p = player37.Player(stem)
    first = None
    seen = []
    for k in range(2000):
        p.play()
        if p.barno == 1 and p.rowno == 0 and p.tick == p.speed:
            seen.append(p.ticks)
            if len(seen) == 2:
                break
    ticks6 = seen[1] - seen[0]
    out["q1"] = {"ticks": ticks6, "seconds": round(ticks6 * FRAME_T[EU] / CLOCK, 2),
                 "bpm": round(CLOCK / FRAME_T[EU] * 60 / (4 * 6), 2),
                 "bpm_now": round(CLOCK / FRAME_T[EU] * 60 / (4 * music37.SPEED), 2)}
    # 2. the frames of the first 313 on the 60 Hz machine without a tick, measured
    groups, _ = by_isr(session("tune", JP))
    ticked = [bool(ws) for _, _, ws in groups]
    skipped = [f for f in range(1, 314) if not ticked[f - 1]]
    assert len(skipped) == 51
    out["q2"] = {"skipped": skipped, "gaps": sorted({b - a for a, b in zip(skipped, skipped[1:])})}
    # 7. how long the effects sound: from their first tick's R0 to the R0 of the tick after their last
    lengths = {}
    for m in (EU, JP):
        t, _ = tick_times("effects", m)
        for name, first, n in (("JUMP", 32, 14), ("BOOM", 238, 20)):
            lengths.setdefault(name, {})[TAG[m]] = round((t[first + n - 1] - t[first - 1]) / CLOCK * 1000, 1)
    # and every place a run of 14 or 20 ticks can fall on the 60 Hz machine: whole frames
    frames = pace_frames("owed", JP, 313 * 3)
    at = [f for f, x in enumerate(frames) if x]
    for name, n in (("JUMP", 14), ("BOOM", 20)):
        spans = sorted({at[k + n] - at[k] for k in range(len(at) - n)})
        lengths[name]["jp_frames"] = spans
        lengths[name]["jp_ms"] = [round(f * FRAME_T[JP] / CLOCK * 1000, 1) for f in spans]
        lengths[name]["eu_ms"] = round(n * FRAME_T[EU] / CLOCK * 1000, 1)
    out["q7"] = lengths
    # 3. owed from 51 on the 60 Hz machine: walk.py through the frames, poked
    for start in (0, 51):
        w = walk.Walk(HERE / "tune")
        w.run("init", "main")
        w.mem[w.sym["owed"]] = start
        tick_frames, n = [], len(w.ports)
        for f in range(1, 314):
            n = len(w.ports)
            w.call("isr")
            if any(port == 0xA1 for _, port, _ in w.ports[n:]):
                tick_frames.append(f)
        lag = [(f - 1) * LINES[JP] - (k - 1) * LINES[EU] for k, f in enumerate(tick_frames, 1)]
        out[f"q3_owed{start}"] = {"first": tick_frames[:4], "ticks": len(tick_frames),
                                 "lag_lines": [min(lag), max(lag)]}
    # 4. the lines a frame put as 60 and 50: one frame in six left out at 60 Hz
    owed, ticks = 0, []
    for _ in range(1536):
        owed += 50
        ticks.append(owed >= 60)
        if owed >= 60:
            owed -= 60
    sixth = pace_frames("sixth", JP, 1536)
    out["q4"] = {"ticks_in_6": sorted({sum(ticks[a:a + 6]) for a in range(1530)}),
                 "sixth_in_6": sorted({sum(sixth[a:a + 6]) for a in range(1530)}),
                 "seconds_60hz": round(-(-music37.TICKS * 6 // 5) * FRAME_T[JP] / CLOCK, 3)}
    # 5. a SHOT asked for at tick 160, and 6. BOOM at priority 1
    _, ans, _ = player37.run(HERE / "effects", 340, sorted(requests() + [(160, music37.FX["SHOT"])]))
    out["q5"] = {"answers": ["taken" if a else "refused" for a in ans]}
    p = player37.Player(HERE / "effects")
    p.mem[p.sym["effects"] + 4 * music37.FX["BOOM"]] = 1
    pending, ans = requests(), []
    for _ in range(340):
        p.play()
        while pending and p.ticks >= pending[0][0]:
            ans.append(p.sfx(pending.pop(0)[1]))
    out["q6"] = {"answers": ["taken" if a else "refused" for a in ans]}
    # 9. latch.asm with joy's register kept and chosen again by isr: no write or read astray
    stem = assemble("latch", guarded_latch())
    res = {}
    for m in (EU, JP):
        ws, rs, spans = logged(stem, m, 680)
        first = spans[0][0]
        main_w = [x for x in ws if x[0] > first and not inside(spans, x[0])]
        main_r = [x for x in rs if x[0] > first and not inside(spans, x[0])]
        res[TAG[m]] = {"writes": len(main_w), "to_r10": sum(1 for x in main_w if x[3] != 15),
                       "reads": len(main_r), "of_r10": sum(1 for x in main_r if x[1] == 10)}
        assert res[TAG[m]]["to_r10"] == res[TAG[m]]["of_r10"] == 0
    out["q9"] = res
    return out


OPENMSX_SECTIONS = ["writes", "walk", "vgm", "model", "pace", "effects", "latch", "photos"]


def openmsx():
    if not versions.builds():
        return {"skipped": "OPENMSX_BUILDS not set"}
    return versions.every_build(["ch37"], OPENMSX_SECTIONS)


SECTIONS = {"bytes": bytes_, "writes": writes, "walk": walk_, "vgm": vgm, "model": model, "pace": pace,
            "effects": effects, "latch": latch, "photos": photos, "prices": prices, "pieces": pieces,
            "answers": answers, "openmsx": openmsx}


def main(names=()):
    CAPS.mkdir(exist_ok=True)
    SHOTS.mkdir(exist_ok=True)
    path = HERE / "meas37.json"
    m = json.loads(path.read_text()) if names and path.exists() else {}
    for name in names or SECTIONS:
        print(name, flush=True)
        m[name] = SECTIONS[name]()
        m = {k: m[k] for k in SECTIONS if k in m}
        path.write_text(json.dumps(m, indent=1) + "\n")
    return m


if __name__ == "__main__":
    res = main(sys.argv[1:])
    for k in sys.argv[1:]:
        print(k, json.dumps(res[k])[:2000])
