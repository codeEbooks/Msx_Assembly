#!/usr/bin/env python3
"""meas50.py -- the tape and the disk, measured.

    python3 gen50.py && ./build.sh && python3 meas50.py
                                  python3 meas50.py tapes load    only these

openMSX plays a tape into the cassette input, bit 7 of PSG register 14, when
a cartridge turns the motor on (bit 4 of PPI port C at 0): screen.wav as it
is, sample by sample, and screen.cas after making a signal of its own from
it. The debugger logs when things happen, with breakpoints that take
themselves away after their first hit, and reads the RAM.

  cbios    C-BIOS's tape entries, read from its ROM: each of the six sends
           its name to the debug device (mode on port $2E, characters on
           $2F) and returns, TAPION, TAPIN, TAPOON and TAPOUT with the carry
           set; STMOTR alone works
  tapes    the two tapes without openMSX: screen.wav decoded by a Python
           decoder of its own (edges, pulses, bits, bytes) and screen.cas
           split at its marks: both hold the blocks gen50.py meant
  scope    scope.rom on each tape and machine: the input sampled every 55
           T-states from the first start bit; the pulses in T-states, and
           the bytes they spell (figure 50.1)
  load     load.rom on each tape and machine: when the tones and the blocks
           begin, in T-states from power-on, the threshold, the RAM after loading (the file, byte for
           byte), every pulse getbyte measured (figure 50.3), and two
           photos, the page while the data block loads and the picture
           (figure 50.2), read back cell by cell and pixel by pixel
  fixed    fixed.rom on each tape: the 1,200 baud tape loads; the .CAS does
           not, and every pulse it measured is shorter than its threshold
  prices   walk.py: the loader's loops, and getbyte reading a modelled byte
           at both speeds; the time between an edge and the next look
  disk     screen.dsk read by mtools (mdir, mcopy, minfo): the file comes out
           as gen50.py put it; and by a Python reader of the BIOS parameter
           block and the FAT
  answers  the workshop, tried (for Appendix I)
  openmsx  all of it again with every other build (tools/versions.py)
"""
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import wave
from collections import Counter
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "tools"))
import meas        # noqa: E402
import msxcap      # noqa: E402
import probe as dbg  # noqa: E402
import screentext  # noqa: E402
import versions    # noqa: E402
sys.path.insert(0, str(HERE))
import gen50       # noqa: E402
sys.path.remove(str(HERE))
sys.path.insert(0, str(HERE))      # other chapters came first: this folder's files win
sys.modules.pop("walk", None)
import walk        # noqa: E402

assert Path(walk.__file__).parent == HERE

CAPS = HERE / "captures"
SHOTS = HERE / "shots"
EU, JP = "MSXBOOK_EU16", "MSXBOOK_JP16"
TAG = {EU: "eu", JP: "jp"}
FPS = {EU: gen50.CLOCK / meas.T_PER_FRAME[EU], JP: gen50.CLOCK / meas.T_PER_FRAME[JP]}
CLOCK = gen50.CLOCK
TAPES = {"wav": "screen.wav", "cas": "screen.cas"}
SECONDS = 26                           # long enough for the slower tape, from INIT
SAMPLE_T = 55                          # scope.asm: T-states a sample


def frames(machine, seconds=SECONDS):
    return math.ceil(seconds * FPS[machine])


def t_state(seconds):
    return round(float(seconds) * CLOCK)


def rom(name, d=HERE):
    return Path(d) / f"{name}.rom"


def tape_args(tape, d=HERE):
    return ["-cassetteplayer", str((Path(d) / tape).resolve())]


LST_LINE = re.compile(r"^\s*\d+\+?\s+([0-9A-F]{4}) ((?:[0-9A-F]{2} ?)+)\s+(.*)$")


def dbg_lines(path):
    """[(address, bytes, source)] of the instruction lines of a listing"""
    out = []
    for line in Path(path).read_text().splitlines():
        m = LST_LINE.match(line)
        if m and "..." not in line:
            src = m.group(3).split(";")[0].strip()
            src = re.sub(r"^[\w.]+:\s*", "", src)
            out.append((int(m.group(1), 16), [int(x, 16) for x in m.group(2).split()],
                        m.group(3).strip() if src.startswith("call header") else src))
    return out


def after_call(sym, label):
    """the address after the CALL at LABEL: the instruction that sees C"""
    return sym[label] + 3


# ================================================================ cbios
TAPE_CALLS = {0x00E1: "TAPION", 0x00E4: "TAPIN", 0x00E7: "TAPIOF", 0x00EA: "TAPOON",
              0x00ED: "TAPOUT", 0x00F0: "TAPOOF", 0x00F3: "STMOTR"}


def cbios():
    """the BIOS's tape entries in C-BIOS, read from its ROM files: where each
    jumps, and what is there. Six save registers, send their name to the
    debug device (C-BIOS's print_debug: the mode to port $2E, the characters
    to $2F), and return, four of them with the carry set: the BIOS's sign of
    an error. STMOTR alone does its job: it reads PPI port C, sets or clears
    bit 4 and writes it back"""
    out = {}
    for f in ("cbios_main_msx1_eu.rom", "cbios_main_msx1_jp.rom"):
        d = (msxcap.CBIOS / f).read_bytes()
        got = {}
        for at, name in TAPE_CALLS.items():
            assert d[at] == 0xC3
            to = d[at + 1] | d[at + 2] << 8
            code = d[to:to + 12]
            if name == "STMOTR":
                body = d[to:to + 24]
                assert code[2:4] == bytes([0xDB, 0xAA])                    # IN A,($AA)
                for op in ((0xCB, 0xE7), (0xCB, 0xA7), (0xD3, 0xAA)):      # SET 4,A; RES 4,A; OUT ($AA),A
                    assert bytes(op) in body, (name, op)
                got[name] = {"to": to, "does": "reads PPI port C, sets or clears bit 4, writes it back"}
                continue
            assert code[:3] == bytes([0xE5, 0xF5, 0x21])                    # PUSH HL, PUSH AF, LD HL,msg
            msg = d[code[3] | code[4] << 8:][:8].split(b"\0")[0].decode()
            assert msg == name and code[5] == 0xCD and code[8:10] == bytes([0xF1, 0xE1])
            pd = code[6] | code[7] << 8                                     # print_debug
            assert d[pd:pd + 4] == bytes([0x3E, 0x23, 0xD3, 0x2E]) and d[pd + 4] == 0xCD
            sub = d[pd + 5] | d[pd + 6] << 8
            assert bytes([0xD3, 0x2F]) in d[sub:sub + 12]                    # OUT ($2F),A: a character
            got["print_debug"] = {"to": pd, "mode_port": 0x2E, "data_port": 0x2F}
            carry = code[10] == 0x37                                        # SCF
            assert code[10 + carry] == 0xC9                                 # RET
            got[name] = {"to": to, "carry": carry}
        out[f] = got
    return out


# ================================================================ tapes
def wav_read(path):
    with wave.open(str(path)) as w:
        assert w.getnchannels() == 1 and w.getsampwidth() == 1
        return w.getframerate(), w.readframes(w.getnframes())


def decode_wav(path):
    """a decoder of its own: the samples above and below the middle, the runs
    between changes, the runs as pulses, the pulses as bits (a long one half
    a 0, a short one a quarter of a 1), the bits as bytes framed by a 0 and
    two 1s; silence (the middle) splits the blocks. -> {"rate", "parts":
    [("silence", seconds) | ("tone", 1 bits) | ("bytes", [...])]}"""
    rate, s = wav_read(path)
    parts, i, n = [], 0, len(s)
    while i < n:
        if s[i] == 128:
            j = i
            while j < n and s[j] == 128:
                j += 1
            parts.append(("silence", round((j - i) / rate, 3)))
            i = j
            continue
        runs, j = [], i
        while j < n and s[j] != 128:
            k = j
            while k < n and s[k] != 128 and (s[k] > 128) == (s[j] > 128):
                k += 1
            runs.append(k - j)
            j = k
        short = min(runs)
        bits, k = [], 0
        while k < len(runs):
            if runs[k] > 1.5 * short:
                bits.append(0)
                k += 2
            else:
                bits.append(1)
                k += 4
        tone = 0
        while tone < len(bits) and bits[tone] == 1:
            tone += 1
        data, k = [], tone
        while k + 11 <= len(bits):
            frame = bits[k:k + 11]
            assert frame[0] == 0 and frame[9:] == [1, 1], frame
            data.append(sum(b << m for m, b in enumerate(frame[1:9])))
            k += 11
        assert k == len(bits)
        parts.append(("tone", tone))
        parts.append(("bytes", data))
        i = j
    return {"rate": rate, "parts": parts}


def split_cas(data):
    """the blocks of a .CAS: what follows each mark, a mark only where the
    offset is a multiple of 8"""
    marks = [k for k in range(0, len(data), 8) if data[k:k + 8] == gen50.SYNC]
    return [data[a + 8:b] for a, b in zip(marks, marks[1:] + [len(data)])]


def tapes():
    w = decode_wav(HERE / "screen.wav")
    blocks = [p[1] for p in w["parts"] if p[0] == "bytes"]
    assert blocks == [list(gen50.HEADER_BLOCK), list(gen50.DATA_BLOCK)]
    tones = [p[1] for p in w["parts"] if p[0] == "tone"]
    silences = [p[1] for p in w["parts"] if p[0] == "silence"]
    assert tones == [gen50.LONG_TONE, gen50.SHORT_TONE]
    c = split_cas((HERE / "screen.cas").read_bytes())
    assert c == [gen50.HEADER_BLOCK, gen50.DATA_BLOCK]
    rate, s = wav_read(HERE / "screen.wav")
    return {"wav": {"rate": rate, "samples": len(s), "seconds": round(len(s) / rate, 3),
                    "tones": tones, "silences": silences,
                    "blocks": [len(b) for b in blocks]},
            "cas": {"bytes": len((HERE / "screen.cas").read_bytes()), "blocks": [len(b) for b in c]},
            "file": {"start": gen50.START, "end": gen50.END, "exec": gen50.EXEC,
                     "data": len(gen50.DATA), "shapes": len(gen50.SHAPES) // 8,
                     "header_block": list(gen50.HEADER_BLOCK), "data_block_head": list(gen50.DATA_BLOCK[:6])}}


# ================================================================ scope
def pulses(bits):
    """runs of equal samples -> [(level, samples)]"""
    out, c = [], 1
    for a, b in zip(bits, bits[1:]):
        if a == b:
            c += 1
        else:
            out.append((a, c))
            c = 1
    out.append((bits[-1], c))
    return out


def spell(runs, short):
    """the runs from the start bit's other half: the bytes they spell, and
    the sample where each byte's start bit begins (None for the first,
    whose start the samples do not hold)"""
    at = [0]
    for _, n in runs:
        at.append(at[-1] + n)
    k, bits = 1, [(0, None)]            # runs[0]: the rest of the start bit
    while k < len(runs) - 4:
        if runs[k][1] > 1.5 * short:
            bits.append((0, at[k]))
            k += 2
        else:
            bits.append((1, at[k]))
            k += 4
    out, starts = [], []
    while len(bits) >= 11:
        if bits[0][0] == 0:
            out.append(sum(b << m for m, (b, _) in enumerate(bits[1:9])))
            starts.append(bits[0][1])
            assert [b for b, _ in bits[9:11]] == [1, 1], bits[:11]
            bits = bits[11:]
        else:
            bits = bits[1:]             # anything until a start bit
    return out, starts


def scope_run(tape, machine, d=HERE):
    s = dbg.sym(Path(d) / "scope.sym")
    tcl = (f'set ::b [debug set_bp {s["done"]} {{}} {{ debug remove_bp $::b; '
           f'L "D [reg D]"; binary scan [debug read_block memory {gen50.SAMPLES_AT} {gen50.N_SAMPLES}] '
           f'H* h; L "S $h" }}]')
    lines = msxcap.run_tcl(rom("scope", d), frames(machine, 16), tcl, machine=machine,
                           extra_args=tape_args(TAPES[tape], d))
    raw = bytes.fromhex(next(l for l in lines if l.startswith("S "))[2:])
    return {"d": int(next(l for l in lines if l.startswith("D "))[2:]), "bits": [b >> 7 for b in raw]}


def scope():
    out = {}
    for tape in TAPES:
        got = {}
        for mc in (EU, JP):
            got[TAG[mc]] = scope_run(tape, mc)
        assert got["eu"] == got["jp"], tape
        r = got["jp"]
        runs = pulses(r["bits"])
        lens = [n for _, n in runs[1:-1]]
        short = Counter(n for n in lens if n < 1.5 * min(lens)).most_common(1)[0][0]
        shorts = [n for n in lens if n < 1.5 * short]
        longs = [n for n in lens if n >= 1.5 * short]
        spelt, starts = spell(runs, short)
        expect = list(gen50.HEADER_BLOCK)
        assert spelt[:len(expect)] == expect[:len(spelt)] and len(spelt) >= 8, (tape, spelt[:20])
        s_t = sum(shorts) / len(shorts) * SAMPLE_T
        l_t = sum(longs) / len(longs) * SAMPLE_T
        span = (starts[-1] - starts[1]) * SAMPLE_T          # from the 2nd byte's start bit to the last's
        out[tape] = {"d": r["d"], "bits": r["bits"], "runs": runs[:400], "spelt": spelt,
                     "short_t": round(s_t, 1), "long_t": round(l_t, 1),
                     "bytes_timed": len(starts) - 2, "bit_t": round(span / (11 * (len(starts) - 2)), 1),
                     "baud": round(CLOCK * 11 * (len(starts) - 2) / span),
                     "same_on_both": True}
    return out


# ================================================================ load
def load_tcl(name, d=HERE):
    """events, logged once each: find (the motor on), the first edge after it
    and the first start bit; at the data block's CALL header the same again;
    loaded (with D, the RAM and VARS); every pulse getbyte measured; tick"""
    s = dbg.sym(Path(d) / f"{name}.sym")
    code = dbg_lines(Path(d) / f"{name}.lst")
    hdr2 = [a for a, b, src in code if src.startswith("call header") and "data block" in src]
    assert len(hdr2) == 1
    sbit = s["getbyte.start"] + 7                       # CALL pulse after JR NC: the start bit found
    seen_s, seen_b = after_call(s, "getbyte.start"), after_call(s, "getbyte.bit")
    seen_h = after_call(s, "header.sum")
    at = {a: b for a, b, src in code}
    assert at[sbit][0] == 0xCD and at[seen_s] == at[seen_b] == [0x7A]      # CALL; LD A,D
    assert at[seen_h] == [0x79]                                            # LD A,C
    return f"""
proc ev {{what}} {{ L "E $what [format %.17g [machine_info time]]" }}
proc once {{addr what {{then {{}}}}}} {{
    set ::bp_$what [debug set_bp $addr {{}} "debug remove_bp \\$::bp_$what; ev $what; $then"]
}}
set ::hs [dict create]
set ::hb [dict create]
set ::hh [dict create]
proc dump {{}} {{ L "HS $::hs"; L "HB $::hb"; L "HH $::hh"; L "LEFT [expr {{[debug read memory {s["left"]}] + 256 * [debug read memory {s["left"] + 1}]}}]"
    binary scan [debug read_block memory {gen50.START} {len(gen50.DATA)}] H* h; L "RAMEND $h" }}
once {s["find"]} find {{once {s["pulse.edge"]} edge1; once {sbit} sbit1}}
once {hdr2[0]} hdr2 {{once {s["pulse.edge"]} edge2; once {sbit} sbit2}}
debug set_bp {seen_s} {{}} {{ dict incr ::hs [reg C] }}
debug set_bp {seen_b} {{}} {{ dict incr ::hb [reg C] }}
debug set_bp {seen_h} {{}} {{ dict incr ::hh [reg C] }}
debug set_bp {s["tick"]} {{}} {{ ev tick }}
once {s["loaded"]} loaded {{L "D [reg D]"; L "POS [cassetteplayer getpos]"; binary scan [debug read_block memory {gen50.START} {len(gen50.DATA)}] H* h; L "RAM $h"; binary scan [debug read_block memory {s["hdr"]} 32] H* v; L "VARS $v"; dump}}
"""


def parse_load(lines):
    ev, ticks, out = {}, [], {}
    for line in lines:
        p = line.split()
        if p[0] == "E":
            if p[1] == "tick":
                ticks.append(t_state(p[2]))
            else:
                ev[p[1]] = t_state(p[2])
        elif p[0] == "f0":
            ev["init"] = t_state(p[3])
        elif p[0] == "D":
            out["d"] = int(p[1])
        elif p[0] == "POS":
            out["pos"] = round(float(p[1]), 6)
        elif p[0] == "RAM":
            out["ram"] = bytes.fromhex(p[1]) if len(p) > 1 else b""
        elif p[0] == "RAMEND":
            out["ram_end"] = bytes.fromhex(p[1])
        elif p[0] == "LEFT":
            out["left"] = int(p[1])
        elif p[0] == "VARS":
            out["vars"] = bytes.fromhex(p[1])
        elif p[0] in ("HS", "HB", "HH"):
            vals = [int(x) for x in p[1:]]
            out[p[0].lower()] = {str(vals[k]): vals[k + 1] for k in range(0, len(vals), 2)}
    out["events"] = ev
    out["ticks"] = ticks
    return out


def load_run(name, tape, machine, d=HERE, seconds=SECONDS):
    n = frames(machine, seconds)
    lines = msxcap.run_tcl(rom(name, d), n, load_tcl(name, d), machine=machine,
                           extra_args=tape_args(TAPES[tape] if tape in TAPES else tape, d),
                           events={n - 1: "dump"})
    return parse_load(lines)


def bits_s(n_bits, baud):
    return n_bits / baud


def structure(r, baud):
    """the tape as the loader met it, in seconds: silence, tone, header block,
    silence, tone; and the tones in bits, from the measured speed"""
    e = {k: v / CLOCK for k, v in r["events"].items()}
    head_end = e["sbit1"] + bits_s(16 * 11 - 0.5, baud)       # sbit1: the middle of the first start bit
    tone1 = e["sbit1"] - e["edge1"] - bits_s(0.5, baud)
    tone2 = e["sbit2"] - e["edge2"] - bits_s(0.5, baud)
    return {"silence1": round(e["edge1"] - e["find"], 3), "tone1": round(tone1, 3),
            "tone1_bits": round(tone1 * baud), "header_block": round(bits_s(16 * 11, baud), 4),
            "silence2": round(e["edge2"] - head_end, 3), "tone2": round(tone2, 3),
            "tone2_bits": round(tone2 * baud),
            "data_block": round(bits_s(len(gen50.DATA_BLOCK) * 11, baud), 3),
            "motor_to_loaded": round(e["loaded"] - e["find"], 3),
            "init_to_loaded": round(e["loaded"] - e["init"], 3)}


def photo_frames(r, machine):
    """film frames from INIT: the page halfway through the data block, and
    the picture 5 frames after loaded"""
    e = {k: v / CLOCK for k, v in r["events"].items()}
    mid = e["sbit2"] + (e["loaded"] - e["sbit2"]) / 2
    return {"mid": round((mid - e["init"]) * FPS[machine]),
            "end": math.ceil((e["loaded"] - e["init"]) * FPS[machine]) + 5}


def read_page(png, machine):
    page = screentext.Page(png, machine)
    return [page.line(r) for r in range(24)]


def picture_diff(png):
    """paper pixels that differ from gen50.py's drawing (ink = dark)"""
    px = Image.open(png).convert("RGB").load()
    pic = gen50.PICTURE.load()
    bad = 0
    for y in range(192):
        for x in range(256):
            ink = sum(px[meas.paper(x, y)]) < 384
            bad += ink != bool(pic[x, y])
    return bad


def load():
    out = {}
    CAPS.mkdir(exist_ok=True)
    for tape in TAPES:
        for mc in (EU, JP):
            r = load_run("load", tape, mc)
            assert r["ram"] == gen50.DATA, (tape, mc)
            v = r["vars"]
            assert v[:16] == gen50.HEADER_BLOCK and v[16:22] == gen50.DATA_BLOCK[:6]
            fr = photo_frames(r, mc)
            shots = msxcap.capture(rom("load"), list(fr.values()), SHOTS / f"load_{tape}_{TAG[mc]}",
                                   machine=mc, extra_args=tape_args(TAPES[tape]))
            pages = {k: read_page(shots[f], mc) for k, f in fr.items()}
            for k, f in fr.items():
                shutil.copy(shots[f], CAPS / f"load_{tape}_{TAG[mc]}_{k}.png")
            mid_t = r["events"]["init"] + fr["mid"] / FPS[mc] * CLOCK
            boxes = pages["mid"][10].count("1")
            before = sum(1 for t in r["ticks"] if t < mid_t)
            assert before - 1 <= boxes <= before + 1, (boxes, before)
            bad = picture_diff(shots[fr["end"]])
            assert bad == 0, (tape, mc, bad)
            baud = gen50.BAUD if tape == "wav" else json.loads((HERE / "meas50.json").read_text())["scope"]["cas"]["baud"]
            out.setdefault(tape, {})[TAG[mc]] = {
                "d": r["d"], "events": r["events"], "ticks": len(r["ticks"]), "structure": structure(r, baud),
                "tape_pos": r["pos"],
                "hs": r["hs"], "hb": r["hb"], "hh": r["hh"], "frames": fr, "page_mid": pages["mid"],
                "boxes_mid": boxes, "ticks_before_mid": before, "picture_pixels_off": bad,
                "ram_same": True}
        a, b = out[tape]["eu"], out[tape]["jp"]
        assert (a["d"], a["hs"], a["hb"]) == (b["d"], b["hs"], b["hb"]), tape
    assert out["wav"]["jp"]["d"] == gen50.FIXED        # fixed.asm has load.asm's number at 1,200 baud
    return out


# ================================================================ fixed
def fixed():
    out = {}
    for tape in TAPES:
        for mc in (EU, JP):
            r = load_run("fixed", tape, mc)
            seen = [int(k) for k in r["hs"]]
            got = {"loaded": "loaded" in r["events"], "d": r.get("d"), "hs": r["hs"], "hb": r.get("hb", {}),
                   "longest": max(seen), "events": r["events"]}
            if tape == "wav":
                assert r["ram"] == gen50.DATA and r["d"] == gen50.FIXED
            else:
                assert "loaded" not in r["events"] and "sbit1" not in r["events"]
                assert max(seen) <= gen50.FIXED
                n = frames(mc)
                shots = msxcap.capture(rom("fixed"), [n - 2], SHOTS / f"fixed_{tape}_{TAG[mc]}",
                                       machine=mc, extra_args=tape_args(TAPES[tape]))
                got["page_end"] = read_page(shots[n - 2], mc)
                shutil.copy(shots[n - 2], CAPS / f"fixed_{tape}_{TAG[mc]}_end.png")
            out.setdefault(tape, {})[TAG[mc]] = got
    return out


# ================================================================ prices
class Signal:
    """a modelled tape: edges every half-cycle, a 1 four short halves, a 0
    two long ones, the first edge T0 + a half; read_port gives bit 7"""
    # (defined before prices, used by speeds and reads_at)

    def __init__(self, data, short_t, t0, tone=40):
        self.edges, t = [], t0
        bits = [1] * tone
        for byte in data:
            bits += gen50.bits_of(byte)
        bits += [1] * 8
        for b in bits:
            for _ in range(4 if b else 2):
                t += short_t if b else 2 * short_t
                self.edges.append(t)
        self.t0 = t0

    def __call__(self, port, t):
        if port != 0xA2:
            return 0
        n = sum(1 for e in self.edges if e <= t)
        return 0x80 if n % 2 == 0 else 0x00


def gaps(wk, since):
    """the T-states between one IN of PSG_READ and the next, from since on"""
    t = [p[0] for p in wk.ports if p[1] == 0xA2 and p[0] >= since]
    return Counter(b - a for a, b in zip(t, t[1:]))


def bounded_call(wk, label, limit, watch=None, **regs):
    """walk.call with a limit in T-states: False if it runs out. watch:
    {address: Counter}, C counted each time the walk gets there"""
    for k, v in regs.items():
        wk.r[k] = v
    t0 = wk.t
    wk.push(walk.SENTINEL)
    wk.t += 18
    wk.pc = wk.sym[label]
    while wk.pc != walk.SENTINEL:
        if watch and wk.pc in watch:
            watch[wk.pc][wk.r["c"]] += 1
        wk.step()
        if wk.t - t0 > limit:
            return False
    return True


SPEED_DATA = [0xD0, 0x53, 0x00, 0xFF, 0x55, 0xAA]


def reads_at(baud, counts=None):
    """does load.asm's header and getbyte read a modelled tape at BAUD?
    -> (right, D); counts, a dict, gets the counts header and getbyte saw"""
    sig = Signal(SPEED_DATA, CLOCK / (4 * baud), -80, tone=300)
    wk = walk.Walk(HERE / "load", read_port=sig)
    s = wk.sym
    hw = {after_call(s, "header.sum"): Counter()}
    gw = {after_call(s, "getbyte.start"): Counter(), after_call(s, "getbyte.bit"): Counter()}
    wk.r["e"] = 0x80
    end = sig.edges[-1]
    done = bounded_call(wk, "header", end, watch=hw)
    if counts is not None:
        counts["header"] = {str(k): v for k, v in sorted(sum(hw.values(), Counter()).items())}
    if not done:
        return False, None
    d, got = wk.r["d"], []
    for _ in SPEED_DATA:
        if not bounded_call(wk, "getbyte", end - wk.t + 10, watch=gw, d=d):
            break
        got.append(wk.r["a"])
    if counts is not None:
        counts["getbyte"] = {str(k): v for k, v in sorted(sum(gw.values(), Counter()).items())}
    return got == SPEED_DATA, d


def speeds():
    """the speeds load.asm reads, in walk.py: from 1,200 baud in steps of
    100 up to 3,800, then of 25 up to 5,400"""
    bauds = list(range(1200, 3800, 100)) + list(range(3800, 5401, 25))
    res = {b: reads_at(b) for b in bauds}
    first_wrong = min(k for k, v in res.items() if not v[0])
    no_header = min(k for k, v in res.items() if v[1] is None)
    assert all(res[k][1] is None for k in res if k >= no_header)
    return {"tried": {str(k): list(v) for k, v in sorted(res.items())},
            "right_up_to": max(k for k in res if k < first_wrong), "first_wrong": first_wrong,
            "right_again": [k for k, v in res.items() if v[0] and k > first_wrong],
            "header_never_from": no_header,
            "d_at": {str(k): res[k][1] for k in (1200, 2400, 3700, first_wrong - 25, first_wrong)},
            "counts": {str(k): counts_at(k) for k in (first_wrong, no_header)}}


def counts_at(baud):
    c = {}
    reads_at(baud, c)
    return c


def prices():
    out = {"speeds": speeds()}
    sig = Signal([0xD0], CLOCK / (4 * 3744), -80, tone=300)
    wk = walk.Walk(HERE / "load", read_port=sig)
    wk.r["e"] = 0x80
    assert bounded_call(wk, "header", sig.edges[-1])
    out["header_gaps"] = {str(k): v for k, v in sorted(gaps(wk, 0).items())}
    wk = walk.Walk(HERE / "load")
    wk.read_port = lambda port, t: 0x80
    out["turn"] = wk.lap("pulse.wait", e=0x80)                  # no edge: one turn
    for tape, short in (("wav", CLOCK / (4 * gen50.BAUD)), ("cas", None)):
        if short is None:
            short = json.loads((HERE / "meas50.json").read_text())["scope"]["cas"]["short_t"]
        data = [0xD0, 0x53, 0x00, 0xFF]
        wk = walk.Walk(HERE / "load", read_port=Signal(data, short, -80))   # an edge 80 T before
        d = json.loads((HERE / "meas50.json").read_text())["load"][tape]["jp"]["d"]
        got = []
        wk.r["e"] = 0x80
        for _ in data:
            wk.call("getbyte", d=d)
            got.append(wk.r["a"])
        assert got == data, (tape, got)
        g = gaps(wk, 0)
        out[tape] = {"short_t": round(short, 1), "bytes": got, "gaps": {str(k): v for k, v in sorted(g.items())}}
    # the work between two bytes of .load: from getbyte's return to its next call
    wk = walk.Walk(HERE / "load")
    s = wk.sym
    s["after_get"] = s["find.load"] + 3                         # after its CALL getbyte
    for name, low in (("no box", 0x10), ("a box", 0x3F)):
        wk.r.update(a=0x55, b=0, c=0)
        for at, v in ((s["ptr"], low), (s["ptr"] + 1, 0xD0), (s["left"], 5), (s["left"] + 1, 0),
                      (s["bar"], 4)):
            wk.poke(at, v)
        out.setdefault("between_bytes", {})[name] = wk.run("after_get", "find.load") + 18
    return out


# ================================================================ disk
def mtools(*args):
    r = subprocess.run(list(args), capture_output=True, text=True, check=True)
    return r.stdout


def bpb(img):
    f = struct_unpack("<HBHBHHBHHH", img[11:28])
    keys = ["bytes_per_sector", "sectors_per_cluster", "reserved", "fats", "root_entries",
            "sectors", "media", "sectors_per_fat", "sectors_per_track", "heads"]
    return dict(zip(keys, f))


def struct_unpack(fmt, b):
    import struct
    return struct.unpack(fmt, b)


def fat_chain(img, b, first):
    fat = img[b["reserved"] * 512:(b["reserved"] + b["sectors_per_fat"]) * 512]

    def entry(n):
        k = n * 3 // 2
        v = fat[k] | fat[k + 1] << 8
        return (v >> 4) if n & 1 else (v & 0xFFF)
    chain, n = [], first
    while n < 0xFF8:
        chain.append(n)
        n = entry(n)
    return chain, entry(0), entry(1)


def disk():
    img = (HERE / "screen.dsk").read_bytes()
    listing = mtools("mdir", "-i", str(HERE / "screen.dsk"), "::")
    tmp = Path(tempfile.mkdtemp(prefix="dsk50_"))
    try:
        mtools("mcopy", "-n", "-i", str(HERE / "screen.dsk"), "::SCREEN.BIN", str(tmp / "s.bin"))
        got = (tmp / "s.bin").read_bytes()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    assert got == gen50.DISK_FILE
    info = mtools("minfo", "-i", str(HERE / "screen.dsk"), "::")
    mi = {key: int(re.search(pat, info).group(1), 0) for key, pat in (
        ("bytes_per_sector", r"sector size: (\d+) bytes"), ("sectors_per_cluster", r"cluster size: (\d+) sectors"),
        ("reserved", r"reserved \(boot\) sectors: (\d+)"), ("fats", r"fats: (\d+)"),
        ("root_entries", r"root directory slots: (\d+)"), ("sectors", r"small size: (\d+) sectors"),
        ("media", r"media descriptor byte: (0x\w+)"), ("sectors_per_fat", r"sectors per fat: (\d+)"),
        ("sectors_per_track", r"sectors per track: (\d+)"), ("heads", r"heads: (\d+)"))}
    m = re.search(r"SCREEN\s+BIN\s+(\d+)\s", listing)
    free = re.search(r"([\d ]+) bytes free", listing)
    b = bpb(img)
    root = (b["reserved"] + b["fats"] * b["sectors_per_fat"]) * 512
    entry = img[root:root + 32]
    first, size = entry[26] | entry[27] << 8, int.from_bytes(entry[28:32], "little")
    chain, e0, e1 = fat_chain(img, b, first)
    data0 = root + b["root_entries"] * 32
    clusters = (b["sectors"] - data0 // 512) // b["sectors_per_cluster"]
    assert size == len(gen50.DISK_FILE) and len(chain) == math.ceil(size / 1024)
    assert mi == b, (mi, b)
    return {"mdir_size": int(m.group(1).replace(" ", "")), "mdir_free": int(free.group(1).replace(" ", "")),
            "mcopy_same": True, "minfo": mi, "minfo_media": re.search(r"media descriptor byte: (0x\w+)", info).group(1),
            "bpb": b, "image_bytes": len(img), "root_sector": root // 512, "data_sector": data0 // 512,
            "clusters": clusters, "file_size": size, "first_cluster": first, "chain": chain,
            "fat0": e0, "fat1": e1, "file_head": list(gen50.DISK_FILE[:7]),
            "entry": entry.hex()}


# ================================================================ answers
def tmp_copy(extra):
    d = Path(tempfile.mkdtemp(prefix="var50_"))
    for f in ("load.rom", "load.sym", "load.lst"):
        shutil.copy(HERE / f, d)
    for name, data in extra.items():
        (d / name).write_bytes(data)
    return d


def wav_bytes(samples):
    d = Path(tempfile.mkdtemp(prefix="w50_"))
    gen50.write_wav(str(d / "x.wav"), samples)
    b = (d / "x.wav").read_bytes()
    shutil.rmtree(d)
    return b


def answers():
    out = {}
    # 1. the same tape at 2,400 baud
    d = tmp_copy({"fast.wav": wav_bytes(gen50.wav_samples(2400))})
    try:
        r = load_run("load", "fast.wav", JP, d)
    finally:
        shutil.rmtree(d)
    out["q1"] = {"d": r["d"], "ram_same": r.get("ram") == gen50.DATA,
                 "motor_to_loaded": round((r["events"]["loaded"] - r["events"]["find"]) / CLOCK, 3)}
    # 2. a dropout: 20 ms of silence in the middle of the data block
    s = bytearray(gen50.wav_samples())
    w = decode_wav(HERE / "screen.wav")
    at = len(s) - round(gen50.LAST_SILENCE * gen50.RATE) - round(len(gen50.DATA_BLOCK) * 11 / gen50.BAUD *
                                                                  gen50.RATE / 2)
    s[at:at + round(0.02 * gen50.RATE)] = bytes([128]) * round(0.02 * gen50.RATE)
    d = tmp_copy({"drop.wav": wav_bytes(bytes(s))})
    try:
        r = load_run("load", "drop.wav", JP, d, seconds=40)
    finally:
        shutil.rmtree(d)
    ram = r["ram_end"]
    off = [k for k, (a, b) in enumerate(zip(ram, gen50.DATA)) if a != b]
    tail = range(off[0] + 8, len(gen50.DATA) - 8)
    shift = max(range(0, 5), key=lambda k: sum(ram[i] == gen50.DATA[i + k] for i in tail if i + k < len(gen50.DATA)))
    same_shifted = sum(ram[i] == gen50.DATA[i + shift] for i in tail if i + shift < len(gen50.DATA))
    out["q2"] = {"loaded": "loaded" in r["events"], "at_sample": at,
                 "at_byte": round((at / gen50.RATE - gen50.FIRST_SILENCE - (gen50.LONG_TONE + 16 * 11) / gen50.BAUD -
                                   gen50.GAP_SILENCE - gen50.SHORT_TONE / gen50.BAUD) * gen50.BAUD / 11) - 6,
                 "left": r["left"], "bytes_off": len(off), "first_off": off[0] if off else None,
                 "shift": shift, "same_shifted": same_shifted, "tail": len(tail),
                 "last_off": off[-1] if off else None}
    del w
    # 3. the addresses printed before the data, not after
    name, src = gen50.variant("early")
    d = Path(tempfile.mkdtemp(prefix="early50_"))
    try:
        shutil.copy(HERE / "msx.inc", d)
        (d / f"{name}.asm").write_text(src)
        subprocess.run(["sjasmplus", "--nologo", "--msg=err", "--syntax=bFw", f"--sym={name}.sym",
                        f"--lst={name}.lst", f"{name}.asm"], cwd=d, check=True)
        for t in TAPES:
            shutil.copy(HERE / TAPES[t], d)
        wk = walk.Walk(d / name)
        code = dbg_lines(d / f"{name}.lst")
        s_ = wk.sym
        first = min(a for a, b, src in code if src == "ld b, 8" and s_["find.ad"] < a < s_["find.load"])
        wk.sym["print"] = first
        q3 = {"print_t": wk.run("print", "find.load")}
        for t in TAPES:
            r = load_run(name, t, JP, d)
            ram = r.get("ram", b"")
            q3[t] = {"loaded": "loaded" in r["events"],
                     "off": [[k, a, b] for k, (a, b) in enumerate(zip(ram, gen50.DATA)) if a != b][:8],
                     "bytes_off": sum(a != b for a, b in zip(ram, gen50.DATA))}
    finally:
        shutil.rmtree(d)
    out["q3"] = q3
    # 4. the disk: clusters, and the room left in the last
    dk = json.loads((HERE / "meas50.json").read_text())["disk"]
    free = dk["mdir_free"] // 1024
    out["q4"] = {"clusters": len(dk["chain"]), "cluster_bytes": 1024,
                 "unused_in_last": len(dk["chain"]) * 1024 - dk["file_size"],
                 "free_bytes": dk["mdir_free"], "free_clusters": free,
                 "more_by_clusters": free // len(dk["chain"]),
                 "more_by_entries": dk["bpb"]["root_entries"] - 1}
    # 5. one threshold for both tapes?
    ld = json.loads((HERE / "meas50.json").read_text())["load"]
    ranges = {}
    for t in TAPES:
        hs = {int(k): v for k, v in ld[t]["jp"]["hs"].items()}
        hb = {int(k): v for k, v in ld[t]["jp"]["hb"].items()}
        both = Counter(hs) + Counter(hb)
        d_ = ld[t]["jp"]["d"]
        ranges[t] = {"short_max": max(k for k in both if 0 < k <= d_),
                     "long_min": min(k for k in both if k > d_)}
    out["q5"] = ranges
    return out


# ================================================================ openmsx
def openmsx():
    if not versions.builds():
        return {"skipped": "OPENMSX_BUILDS not set"}
    return versions.every_build(["ch50"], OPENMSX_SECTIONS)


OPENMSX_SECTIONS = ["tapes", "scope", "load", "fixed", "prices", "disk", "answers"]
SECTIONS = {"cbios": cbios, "tapes": tapes, "scope": scope, "load": load, "fixed": fixed, "prices": prices,
            "disk": disk, "answers": answers, "openmsx": openmsx}


def main(names=()):
    path = HERE / "meas50.json"
    old = json.loads(path.read_text()) if path.exists() else {}
    for n in (names or SECTIONS):
        old[n] = SECTIONS[n]()
        path.write_text(json.dumps(old, indent=1, sort_keys=True))
        print(n, "done", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
