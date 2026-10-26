#!/usr/bin/env python3
"""meas35.py -- the joysticks, measured.

    python3 gen35.py && ./build.sh && python3 meas35.py
                                  python3 meas35.py sticks pins     only these

openMSX's joysticks moved by keys are plugged into both ports: keyjoystick1
into port A, keyjoystick2 into port B (msxjoystick1 and msxjoystick2 from
openMSX 20 on), each moved by six keys of the host's keyboard. At each frame
of a program's events file, the Tcl script pauses the machine at the frame's
start, has xdotool press and let go of those keys on the X display openMSX
runs on, and lets the machine go 0.2 seconds later: the joystick changes at
the start of that frame, every run the same. The model of the joysticks is
the events file itself.

  sticks     sticks.rom on both machines: the moves of sticks.events, and the
             sixteen ways to hold the four switches on each port (figure 35.1)
  gtstck     gtstck.rom: GTSTCK and GTTRIG against the model and against
             sticks.asm's dir, their T-states, the interrupts after them
  pins       pins.rom: register 14 after fourteen values of register 15,
             with nothing, A, B, UP and all three held; the KANA lamp after
             each value
  players    players.rom: two figures, joystick 1 and the cursor keys for
             player 1, joystick 2 for player 2 (figure 35.2)
  leftover   WHERE IT BREAKS: leftover.rom (figure 35.3)
  prices     walk.py's T-states for joy, dir, keys, move and a frame
  standard   openMSX's machine files with a keyboard, and with a PSG
  answers    the workshop, tried (for Appendix I)
  openmsx    all of it again with every other build (tools/versions.py)
"""
import json
import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "tools"))
import meas        # noqa: E402
import msxcap      # noqa: E402
import probe as dbg  # noqa: E402
import versions    # noqa: E402
sys.path.insert(0, str(HERE))
import gen35       # noqa: E402
import gen34       # noqa: E402
sys.path.remove(str(HERE))
sys.path.insert(0, str(HERE))      # gen35 put chapter 34 first: this folder's files win
for mod in ("vdpscreen", "walk"):
    sys.modules.pop(mod, None)
import vdpscreen   # noqa: E402
import walk        # noqa: E402  (chapter 32's)

assert Path(vdpscreen.__file__).parent == HERE and Path(walk.__file__).parent == HERE

CAPS = HERE / "captures"
EU, JP = gen35.EU, gen35.JP
TAG = {EU: "eu", JP: "jp"}
POS = "[expr {[machine_info VDP_frame_count] - $::f0}] [machine_info VDP_cycle_in_frame]"
F0 = 'L "f0 [machine_info VDP_frame_count]"\n'
TOO_FAST = ('proc ::toofast_cb {args} { L "fast [machine_info VDP_frame_count]" }\n'
            'set VDP.too_fast_vram_access_callback ::toofast_cb\n')
PALETTE = [tuple(c) for c in json.loads((REPO / "ch01" / "meas01.json").read_text())["palette"]["rgb"]]
CODE = {rgb: n for n, rgb in enumerate(PALETTE) if n}

# the host's keys that move each key-joystick
KEYS = {1: dict(up="I", down="K", left="J", right="L", a="U", b="O"),
        2: dict(up="T", down="G", left="F", right="H", a="R", b="Y")}
SETTING = {"a": "triga", "b": "trigb"}
ROW8 = dict(up=0x20, down=0x40, left=0x10, right=0x80, a=0x01)     # the cursor keys and SPACE
# openMSX 17 to 19 have key-joysticks, each key a setting of its own; from 20
# on the pluggable is an MSX joystick, whose keys are one setting, a dict
PLUG = ('if {"keyjoystick1" in [machine_info pluggable]} {\n' +
        "plug joyporta keyjoystick1\nplug joyportb keyjoystick2\n" +
        "".join(f"set keyjoystick{p}.{SETTING.get(s, s)} {k}\n" for p in KEYS for s, k in KEYS[p].items()) +
        "} else {\nplug joyporta msxjoystick1\nplug joyportb msxjoystick2\n" +
        "".join(f"set msxjoystick{p}_config {{" +
                " ".join(f"{s.upper()} {{{{keyb {k}}}}}" for s, k in KEYS[p].items()) + "}\n" for p in KEYS) +
        "}\n")
# openMSX 20 and later open their window without the focus, which xdotool's
# keys go to: the events give it to the window first
FOCUS = "exec xdotool search --class openMSX windowfocus --sync; "


def rom(name):
    return HERE / f"{name}.rom"


def sym(name):
    return dbg.sym(HERE / f"{name}.sym")


# ---------------------------------------------------------------- the joysticks
def moves(name):
    """NAME.events: [(frame, port, the switches held from then on)]"""
    out = []
    for line in (HERE / f"{name}.events").read_text().splitlines():
        line = line.split("#")[0].strip()
        if line:
            f, p, *held = line.split()
            out.append((int(f), p if p == "k" else int(p), frozenset() if held == ["-"] else frozenset(held)))
    return out


def held_at(mv, frame):
    """{port: the switches held in FRAME}"""
    state = {1: frozenset(), 2: frozenset(), "k": frozenset()}
    for f, p, held in sorted(mv, key=lambda m: m[0]):
        if f > frame:
            break
        state[p] = held
    return state


def tcl_events(mv):
    """{frame: Tcl}: the machine paused at the frame's start, the keys pressed
    and let go with xdotool, the machine let go 0.2 seconds later"""
    state = {1: frozenset(), 2: frozenset(), "k": frozenset()}
    ev = {}
    for f in sorted({m[0] for m in mv}):
        down, up, matrix = [], [], ""
        for _, p, held in [m for m in mv if m[0] == f]:
            if p == "k":                # the keyboard: row 8 of the matrix (chapter 34)
                for s in sorted(held - state[p]):
                    matrix += f"keymatrixdown 8 0x{ROW8[s]:02X}; "
                for s in sorted(state[p] - held):
                    matrix += f"keymatrixup 8 0x{ROW8[s]:02X}; "
            else:
                down += [KEYS[p][s].lower() for s in sorted(held - state[p])]
                up += [KEYS[p][s].lower() for s in sorted(state[p] - held)]
            state[p] = held
        cmd = matrix + "set pause on; "
        if down or up:
            cmd += FOCUS
        if down:
            cmd += f"exec xdotool keydown {' '.join(down)}; "
        if up:
            cmd += f"exec xdotool keyup {' '.join(up)}; "
        ev[f] = cmd + "after realtime 0.2 {set pause off}"
    return ev


def r14(held, top):
    """register 14 of a port: TOP in bits 6 and 7, a 0 for each switch held"""
    return top | sum(1 << b for b, s in enumerate(gen35.SWITCHES) if s not in held)


def way(held):
    return gen35.direction(*[s in held for s in gen35.SWITCHES[:4]])


def run(name, frames, tcl, machine):
    lines = msxcap.run_tcl(rom(name), frames, F0 + TOO_FAST + tcl, machine=machine,
                           events=tcl_events(moves(name)), tcl_setup=PLUG)
    w = [l.split() for l in lines]
    assert not [x for x in w if x[0] == "fast"], (name, machine, "an access too soon")
    return w


def reads(name, machine, frames, regs, extra=""):
    """the bytes REGS (names of the program's RAM) at `read`, every frame"""
    s = sym(name)
    tcl = (f'debug set_bp {s["read"]} {{}} {{ L "v {POS} ' +
           " ".join(f"[debug read memory {s[r] if isinstance(r, str) else r}]" for r in regs) +
           '" }\n') + extra
    w = run(name, frames, tcl, machine)
    return {int(x[1]): [int(y) for y in x[3:]] for x in w if x[0] == "v"}, w


# ---------------------------------------------------------------- screens
def codes(png):
    im = Image.open(png).convert("RGB")
    px = im.load()
    return [[CODE.get(px[x, y]) for x in range(im.width)] for y in range(im.height)]


def mismatch(model, photo):
    return sum(1 for y in range(meas.CAPTURE_H) for x in range(meas.DRAWN[0], meas.DRAWN[1] + 1)
               if model[y][x] != photo[y][x])


def capture_of(paper, border=15):
    return [[(paper[y - meas.PAPER_Y0][x - meas.PAPER_X0]
              if 0 <= x - meas.PAPER_X0 < 256 and 0 <= y - meas.PAPER_Y0 < 192 else border)
             if meas.DRAWN[0] <= x <= meas.DRAWN[1] else None
             for x in range(meas.CAPTURE_W)] for y in range(meas.CAPTURE_H)]


def screen(names):
    v = bytearray(16384)
    v[0:1024] = bytes(gen34.own_shapes())
    v[0x2000:0x2020] = bytes([0x1F]) * 32
    v[0x1800:0x1B00] = bytes(names)
    v[0x1B00] = 0xD0
    return capture_of(vdpscreen.draw(v, gen35.TEXT_REGS))


def put(names, row, col, text):
    for i, ch in enumerate(text):
        names[32 * row + col + i] = ch if isinstance(ch, int) else ord(ch)


def boxes(v, filled_bit):
    return [gen35.BOX_FULL if (v >> b & 1) == filled_bit else gen35.BOX_EMPTY for b in range(7, -1, -1)]


def sticks_screen(vals):
    p1, p2, r15, r7, w1, w2 = vals
    n = gen34.page(gen35.sticks_texts())
    for p, v, wv in ((1, p1, w1), (2, p2, w2)):
        row = gen35.STICK_ROWS[p]
        put(n, row, gen35.BOX_COL, boxes(v, 0))
        put(n, row, gen35.BOX_COL + 10, f"{v:02X}")
        put(n, row, gen35.WAY_COL, str(wv))
    for r, v in ((15, r15), (7, r7)):
        row = gen35.REG_ROWS[r]
        put(n, row, gen35.BOX_COL, boxes(v, 1))
        put(n, row, gen35.BOX_COL + 10, f"{v:02X}")
    return screen(n)


def photos(name, machine, shots, model_of, values):
    """SHOTS against the screen drawn from the values read E frames before,
    one E for all"""
    pngs = msxcap.capture(rom(name), shots, CAPS, f"{name}_{TAG[machine]}_f", machine=machine,
                          events=tcl_events(moves(name)), tcl_setup=PLUG)
    ph = {f: codes(pngs[f]) for f in shots}
    fits = [e for e in (-2, -1, 0) if all(f + e in values and mismatch(model_of(values[f + e]), ph[f]) == 0
                                          for f in shots)]
    assert len(fits) == 1, (name, machine, fits)
    return fits[0]


# ---------------------------------------------------------------- sticks
def sticks():
    mv = moves("sticks")
    out = {}
    for m in (EU, JP):
        v, _ = reads("sticks", m, gen35.STICKS_FRAMES, ["port1", "port2", "r15", "r7", "way1", "way2"])
        top = {x[0] & 0xC0 for x in v.values()} | {x[1] & 0xC0 for x in v.values()}
        assert len(top) == 1, top
        top = top.pop()
        d = [dd for dd in (-1, 0, 1) if all(
            vals[:2] == [r14(held_at(mv, f + dd)[p], top) for p in (1, 2)] and
            vals[4:] == [way(held_at(mv, f + dd)[p]) for p in (1, 2)] for f, vals in v.items())]
        assert len(d) == 1, (m, d)
        assert {tuple(x[2:4]) for x in v.values()} == {(0xCF, 0xB8)}
        # the sixteen ways to hold the four switches, on each port: dir against
        # the rule (two opposite switches cancel)
        combos = {}
        for f, p, held in gen35.combo_moves():
            if f + 1 in v:
                n = sum(1 << b for b, s in enumerate(gen35.SWITCHES[:4]) if s in held)
                combos.setdefault(p, {})[n] = v[f + 1][4 + p - 1]
        rule = [gen35.direction(*[n >> b & 1 for b in range(4)]) for n in range(16)]
        assert all([c[n] for n in range(16)] == rule for c in combos.values()), combos
        shots = sorted({f + k for f, _, _ in gen35.STICK_MOVES for k in (0, 1)})
        lag = photos("sticks", m, shots, sticks_screen, v)
        out[TAG[m]] = {"offset": d[0], "top": top, "r15": "CF", "r7": "B8", "frames": len(v),
                       "combos": {str(p): [c[n] for n in range(16)] for p, c in combos.items()},
                       "photos": len(shots), "lag": lag,
                       "idle": f"{r14(frozenset(), top):02X}"}
    return out


# ---------------------------------------------------------------- gtstck
def gtstck():
    mv = moves("gtstck")
    s = sym("gtstck")
    out = {}
    for m in (EU, JP):
        stops = ["s1", "s2", "g1", "g2", "g3", "g4", "after"]
        # each stop: where in the frame, and IFF1, the interrupts on or off
        tcl = "".join(f'debug set_bp {s[k]} {{}} {{ L "t {k} {POS} [expr {{[reg iff] & 1}}]" }}\n'
                      for k in stops)
        v, w = reads("gtstck", m, gen35.STICKS_FRAMES,
                     [s["bios"] + k for k in range(6)] + ["way1", "way2", "iff"], tcl)
        d = []
        for dd in (-1, 0, 1):
            ok = True
            for f, vals in v.items():
                h = held_at(mv, f + dd)
                want = [way(h[1]), way(h[2])] + \
                    [0xFF if btn in h[port] else 0 for btn, port in (("a", 1), ("a", 2), ("b", 1), ("b", 2))] + \
                    [way(h[1]), way(h[2]), 4]
                if vals != want:
                    ok = False
                    break
            if ok:
                d.append(dd)
        assert len(d) == 1, (m, d)
        # the T-states of each call, from the debugger's stops
        t, iff = {}, {}
        for x in w:
            if x[0] == "t":
                t.setdefault(int(x[2]), {})[x[1]] = int(x[3])
                iff.setdefault(x[1], set()).add(x[4])
        # the interrupts: off at the first call (DI after HALT), on after each
        assert iff == {"s1": {"0"}, **{k: {"1"} for k in stops[1:]}}, iff
        cost = {}
        for a, b, extra in (("s1", "s2", 22), ("s2", "g1", 22), ("g1", "g2", 22), ("g2", "g3", 22),
                            ("g3", "g4", 22), ("g4", "after", 14)):
            got = sorted({(c[b] - c[a]) // 6 - extra for c in t.values() if a in c and b in c})
            cost[a] = got
        # GTTRIG's T-states with its button let go and held, from the frames
        # the events hold it in
        trig = {}
        for k, (btn, port) in zip(("g1", "g2", "g3", "g4"), (("a", 1), ("a", 2), ("b", 1), ("b", 2))):
            nxt = stops[stops.index(k) + 1]
            by = {}
            for f, c in t.items():
                if k in c and nxt in c:
                    by.setdefault("held" if btn in held_at(mv, f + d[0])[port] else "idle", set()).add(
                        (c[nxt] - c[k]) // 6 - (14 if nxt == "after" else 22))
            assert all(len(x) == 1 for x in by.values()), (k, by)
            trig[str(port + 2 * (btn == "b"))] = {h: x.pop() for h, x in sorted(by.items())}
        # what GTTRIG does to register 15: in frame 5 the debugger writes $80
        # there before each call, pins 6 and 7 of both ports low, and reads it
        # back after the call
        tcl = "".join(f'debug set_bp {s[k]} {{[expr {{[machine_info VDP_frame_count] - $::f0}}] == 5}} '
                      f'{{ debug write "PSG regs" 15 0x80 }}\n'
                      f'debug set_bp {s[k] + 3} {{[expr {{[machine_info VDP_frame_count] - $::f0}}] == 5}} '
                      f'{{ L "r15 {k} [debug read "PSG regs" 15]" }}\n' for k in ("g1", "g2", "g3", "g4"))
        w = run("gtstck", 8, tcl, m)
        r15 = {x[1]: f"{int(x[2]):02X}" for x in w if x[0] == "r15"}
        # the model: C-BIOS's GTTRIG ORs $03 into register 15 for port 1, and
        # $4C for port 2: its pins 6 and 7 high, and the port chosen
        assert r15 == {"g1": "83", "g2": "CC", "g3": "83", "g4": "CC"}, r15
        out[TAG[m]] = {"offset": d[0], "frames": len(v), "iff_on": len(v),
                       "iff_at": {k: iff[k].pop() for k in stops},
                       "gtstck_1": cost["s1"], "gtstck_2": cost["s2"],
                       "gttrig": [cost["g1"], cost["g2"], cost["g3"], cost["g4"]], "gttrig_by": trig,
                       "r15_from_80": r15}
    return out


# ---------------------------------------------------------------- pins
def pins():
    mv = moves("pins")
    s = sym("pins")
    out = {}
    for m in (EU, JP):
        # the KANA lamp: openMSX passes a lamp's changes on at once, but at
        # most one every tenth of a second of real time; so in the loop's
        # first frame the debugger stops the machine for 0.3 seconds after
        # each OUT, and every change of the lamp comes in with its value
        tcl = (f'debug set_bp {s["written"]} {{}} {{ set ::lastval [reg a] }}\n'
               f'debug set_bp {s["written"] + 2} {{}} {{\n'
               '    set n [expr {[machine_info VDP_frame_count] - $::f0}]\n'
               '    if {![info exists ::kf]} { set ::kf $n; L "kf $n" }\n'
               '    if {$n == $::kf} { debug break; after realtime 0.3 {debug cont} }\n}\n'
               'trace add variable ::led_kana write {apply {{a b c} '
               f'{{L "kana $::led_kana $::lastval {POS}"}}}}}}\n')
        v, w = reads("pins", m, gen35.PINS_FRAMES, [s["pins"] + k for k in range(len(gen35.PIN_VALUES))], tcl)
        top = v[min(v)][0] & 0xC0
        kf = int(next(x for x in w if x[0] == "kf")[1])
        changes = [[f"{int(x[2]):02X}", x[1]] for x in w if x[0] == "kana" and int(x[3]) == kf]
        lit, state = [], "off"
        for value in gen35.PIN_VALUES:
            state = next((c[1] for c in changes if c[0] == f"{value:02X}"), state)
            if state == "on":
                lit.append(f"{value:02X}")
        want, state = [], "off"         # the model: bit 7 at 0 lights the lamp
        for value in gen35.PIN_VALUES:
            if ("on" if not value & 0x80 else "off") != state:
                state = "on" if state == "off" else "off"
                want.append([f"{value:02X}", state])
        assert changes == want, (m, changes, want)
        kana = {"frame": kf, "changes": changes, "lit": lit}
        # register 14 after each value, for each way of holding port 1 in the events
        table = {}
        for f, p, held in mv:
            if f + 1 in v:
                table[" ".join(sorted(held)) or "-"] = v[f + 1]
        table["-"] = v[min(v)]
        # the model: bit 6 chooses the port; a port's pin 8 high (bit 4 for
        # port 1, bit 5 for port 2) and its joystick reads no switch at all.
        # Pins 6 and 7 (bits 0 and 1 for port 1, 2 and 3 for port 2) are the
        # buttons' own wires: one model has a 0 there read as its button held,
        # the other has the bits make no difference; exactly one must fit
        def model(value, held, pins67):
            port = 2 if value & 0x40 else 1
            pin8 = value >> (4 if port == 1 else 5) & 1
            want = r14(frozenset() if pin8 or port == 2 else held, top)
            if pins67 == "held":
                low = ~value >> (2 * (port - 1)) & 3
                want &= ~(low << 4) & 0xFF
            return want
        fits = [k for k in ("ignored", "held") if all(
            got == model(value, frozenset() if name == "-" else frozenset(name.split()), k)
            for name, vals in table.items() for value, got in zip(gen35.PIN_VALUES, vals))]
        assert len(fits) == 1, (m, fits, table)
        out[TAG[m]] = {"top": top, "table": {k: [f"{x:02X}" for x in t] for k, t in table.items()},
                       "pins67": fits[0], "kana": kana}
    return out


# ---------------------------------------------------------------- players
def bits_of(held):
    """a port's bits 0 to 5, a 0 for each switch held"""
    return sum(1 << b for b, s in enumerate(gen35.SWITCHES) if s not in held)


def players_model(mv, first, last):
    """the figures before each frame's logic, from the frame of the first
    reading: player 1 the cursor keys and joystick 1 together, player 2
    joystick 2; a pixel for each switch held, a press of A swaps the colours"""
    fig = {p: [gen35.STARTS[p][1], gen35.STARTS[p][0], gen35.COLOURS[p][0]] for p in (1, 2)}
    before = {1: 0x3F, 2: 0x3F}
    out = {}
    for f in range(first, last + 1):
        h = held_at(mv, f)
        out[f] = fig[1] + fig[2]
        for p, now in ((1, bits_of(h[1]) & bits_of(h["k"])), (2, bits_of(h[2]))):
            y, x, c = fig[p]
            y = (y - (not now & 1) + (not now & 2)) & 0xFF
            x = (x - (not now & 4) + (not now & 8)) & 0xFF
            if not now & 0x10 and before[p] & 0x10:
                c = gen35.COLOURS[p][1] if c == gen35.COLOURS[p][0] else gen35.COLOURS[p][0]
            fig[p] = [y, x, c]
            before[p] = now
    return out


def players_screen(vals):
    y1, x1, c1, y2, x2, c2 = vals
    v = bytearray(16384)
    v[0:1024] = bytes(gen34.own_shapes())
    v[0x2000:0x2020] = bytes([0x1F]) * 32
    v[0x1800:0x1B00] = bytes(gen34.page(gen35.players_texts()))
    v[0x1B00:0x1B09] = bytes([y1, x1, 0, c1, y2, x2, 0, c2, 0xD0])
    v[0x3800:0x3820] = bytes(gen34.FIGURE)
    return capture_of(vdpscreen.draw(v, gen35.SPRITE_REGS))


PLAYERS_SHOTS = [11, 12, 41, 45, 53, 63, 64, 77, 87, 101]


def players():
    mv = moves("players")
    s = sym("players")
    out = {}
    for m in (EU, JP):
        regs = [s["fig1"] + k for k in (0, 1, 3)] + [s["fig2"] + k for k in (0, 1, 3)]
        v, _ = reads("players", m, gen35.PLAYERS_FRAMES, regs)
        first = min(v)
        fits = [d for d in (-1, 0, 1)
                if all(v[f] == players_model(mv, first + d, max(v) + 1)[f + d] for f in v)]
        assert len(fits) == 1, (m, fits)
        mo = players_model(mv, first, max(v) + 1)
        lag = photos("players", m, PLAYERS_SHOTS, players_screen, v)
        end = v[max(v)]
        out[TAG[m]] = {"offset": fits[0], "frames": len(v), "end": end, "photos": len(PLAYERS_SHOTS),
                       "lag": lag, "swaps": {p: sum(1 for a, b in zip(sorted(mo), sorted(mo)[1:])
                                                    if mo[a][3 * p - 1] != mo[b][3 * p - 1]) for p in (1, 2)}}
    return out


# ---------------------------------------------------------------- leftover
def left_screen(vals):
    n = gen34.page(gen35.leftover_texts())
    for (row, _, _), wv in zip(gen35.LEFT_LINES, vals):
        put(n, row, 9, str(wv))
    return screen(n)


def leftover():
    mv = moves("leftover")
    out = {}
    for m in (EU, JP):
        v, _ = reads("leftover", m, gen35.LEFTOVER_FRAMES, ["way1", "way2"])
        first = min(v)
        d = [dd for dd in (-1, 0, 1) if all(
            vals == [way(held_at(mv, f + dd)[1 if f == first else 2]), way(held_at(mv, f + dd)[2])]
            for f, vals in v.items())]
        assert len(d) == 1, (m, d)
        wrong = [f for f, vals in v.items() if vals[0] != way(held_at(mv, f + d[0])[1])]
        shots = [10, 11, 20, 21]
        lag = photos("leftover", m, shots, left_screen, v)
        out[TAG[m]] = {"offset": d[0], "first": first, "frames": len(v), "wrong": len(wrong),
                       "wrong_from": min(wrong), "lag": lag}
    return out


# ---------------------------------------------------------------- prices
def prices():
    out = {}
    for port in (0x00, 0x40):
        wk = walk.Walk(HERE / "sticks", read_port=lambda p, t: 0xBF if p == 0xA2 else 0)
        out[f"joy_{port:02X}"] = wk.call("joy", a=port) - 18
    wk = walk.Walk(HERE / "sticks")
    out["dir"] = wk.call("dir", a=0xBF) - 18
    assert out["joy_00"] == 5 + 8 + 12 + 12 + 8 + 5 + 12 + 8 + 12 + 12 + 11
    wk = walk.Walk(HERE / "players", read_port=lambda p, t: {0xAA: 0x50, 0xA9: 0xFF}.get(p, 0))
    out["keys"] = wk.call("keys") - 18
    for name, bits in (("move_none", 0x3F), ("move_fire", 0x2F)):
        wk = walk.Walk(HERE / "players")
        s_ = wk.sym
        wk.ix = s_["fig1"]
        wk.mem[s_["last1"]] = 0x3F
        out[name] = wk.call("move1", a=bits, h=s_["last1"] >> 8, l=s_["last1"] & 0xFF) - 18
    # a frame of players.asm with nothing held: from the VRAM's address to JP main
    wk = walk.Walk(HERE / "players", read_port=lambda p, t: {0xAA: 0x50, 0xA9: 0xFF, 0xA2: 0xBF}.get(p, 0))
    for k in ("last1", "last2"):
        wk.mem[wk.sym[k]] = 0x3F
    out["frame"] = wk.run("frame", "main")
    return out


# ---------------------------------------------------------------- standard
def standard():
    """openMSX's machine files: those with a keyboard (a PPI), and of them those
    with a PSG, which brings the two joystick ports"""
    import os
    share = Path(os.environ.get("OPENMSX_SYSTEM_DATA", "/usr/share/openmsx"))
    xmls = sorted((share / "machines").glob("*.xml"))
    ppi = [x for x in xmls if "<PPI" in x.read_text(errors="replace")]
    psg = [x for x in ppi if "<PSG" in x.read_text(errors="replace")]
    return {"files": len(xmls), "with_ppi": len(ppi), "with_psg": len(psg)}


# ---------------------------------------------------------------- answers
def answers():
    m = json.loads((HERE / "meas35.json").read_text())
    st, gt, pi, pr, lo = (m[k] for k in ("sticks", "gtstck", "pins", "prices", "leftover"))
    out = {}
    out["q1"] = {"idle": st["eu"]["idle"], "top": st["eu"]["top"]}
    c = st["eu"]["combos"]["1"]
    out["q2"] = {"up_down": c[3], "left_right": c[12], "all": c[15], "up_down_left": c[7]}
    own = pr["joy_00"] + pr["dir"] + 2 * 18        # with their CALLs, as GTSTCK's price is
    out["q3"] = {"gtstck": gt["eu"]["gtstck_1"][0], "own": own,
                 "times": round(gt["eu"]["gtstck_1"][0] / own, 1)}
    g = gt["eu"]["gttrig_by"]["1"]
    out["q4"] = {"gttrig_1": g, "less_held": g["idle"] - g["held"]}
    table = pi["eu"]["table"]
    out["q5"] = {"9F_with_a": table["a"][gen35.PIN_VALUES.index(0x9F)],
                 "AF_with_a": table["a"][gen35.PIN_VALUES.index(0xAF)]}
    out["q6"] = pi["eu"]["kana"]["lit"]
    assert out["q6"] == [f"{v:02X}" for v in gen35.PIN_VALUES if not v & 0x80]
    held = bits_of(frozenset(["up"])) & bits_of(frozenset(["down"]))
    out["q7"] = {"bits": f"{held:02X}", "way": gen35.direction(True, True, False, False)}
    out["q8"] = {"frame": pr["frame"], "eu": round(100 * pr["frame"] / 71364, 2),
                 "jp": round(100 * pr["frame"] / 59736, 2)}
    out["q9"] = {"wrong": lo["eu"]["wrong"], "frames": lo["eu"]["frames"], "first": lo["eu"]["first"]}
    out["q10"] = {"both_ports": 2 * own, "gtstck_both": gt["eu"]["gtstck_1"][0] + gt["eu"]["gtstck_2"][0]}
    return out


OPENMSX_SECTIONS = ["sticks", "gtstck", "pins", "players", "leftover"]


def openmsx():
    if not versions.builds():
        return {"skipped": "OPENMSX_BUILDS not set"}
    return versions.every_build(["ch35"], OPENMSX_SECTIONS)


SECTIONS = {"sticks": sticks, "gtstck": gtstck, "pins": pins, "players": players, "leftover": leftover,
            "prices": prices, "standard": standard,
            "answers": answers, "openmsx": openmsx}


def main(names=()):
    CAPS.mkdir(exist_ok=True)
    path = HERE / "meas35.json"
    m = json.loads(path.read_text()) if names and path.exists() else {}
    for name in names or SECTIONS:
        print(name, flush=True)
        m[name] = SECTIONS[name]()
        m = {k: m[k] for k in SECTIONS if k in m}
        path.write_text(json.dumps(m, indent=1) + "\n")
    return m


if __name__ == "__main__":
    main(sys.argv[1:])
