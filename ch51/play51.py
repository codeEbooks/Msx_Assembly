#!/usr/bin/env python3
"""play51.py - one of the book's finished games on one machine, against its model.

    python3 play51.py 44|46 MACHINE 50|60 [FIRST]     one line of JSON

The game of chapter 44 (GRIN ALLEY) or 46 (LANTERN KEEP) is played on MACHINE
with the play planned for its rate, loop for loop against the chapter's model,
with the chapter's own measuring code (meas44.py, meas46.py). The plays were
planned as keys at frames counted from INIT; a machine whose BIOS calls INIT at
another point of its frame wakes the game's first loop a frame earlier or
later, so the keys move with it: SHIFT frames, the difference between the
frame of the first loop here and on the book's machine of the same rate,
FIRST. With no FIRST given, the program finds it: it runs the game on that
machine without keys until the first loop wakes.

The JSON: the INIT's place in its frame, the first loop's frame, the shift, the
loops played, the ones whose RAM is not the model's, and the paths of the
photographs of the play's last frame and of the strip-free title.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent


def load(chapter):
    folder = REPO / f"ch{chapter}"
    sys.path.insert(0, str(folder))
    os.chdir(folder)
    return __import__(f"meas{chapter}")


def first_wake(M, chapter, machine, real, frames=16):
    """the frame (from INIT) whose interrupt wakes the game's first loop, with
    no keys; and where INIT was called, where main was reached and where the
    first interrupt after it came, (frame from INIT, cycle of that frame)"""
    rows, st = (loops44 if chapter == 44 else loops46)(M, machine, real, {}, 0, frames=frames,
                                                       compare=False)
    return st, (rows[0]["frame"] if rows else None)


def start(w, f0, c0):
    main = next(([int(x[1]) - f0, int(x[2])] for x in w if x[0] == "main"), None)
    isr = None
    if main:
        isr = next(([int(x[1]) - f0, int(x[2])] for x in w if x[0] == "isr" and
                    [int(x[1]) - f0, int(x[2])] > main), None)
    return {"init": [0, c0], "main": main, "isr": isr}


def loops44(M, machine, real, ev, shift, frames=None, compare=True):
    import model44
    frames = frames or M.PLAY_FRAMES[real] + shift
    s = M.sym("game")
    tcl = 'L "c0 [machine_info VDP_cycle_in_frame]"\n'
    tcl += "".join(f'debug set_bp {s[k]} {{}} {{ L "{k} {M.POS}" }}\n'
                   for k in ("main", "isr", "isrend", "woke", "sent", "ran", "touch", "input"))
    tcl += f'debug set_bp {s["woke"]} {{}} {{ M v {M.VARS[0]} 128; M n {M.NUMS[0]} {M.NUMS[1]} }}\n'
    w = M.run("game", machine, frames, tcl, ev=ev, real=real)
    c0 = int(next(x for x in w if x[0] == "c0")[1])
    f0 = int(next(x for x in w if x[0] == "f0")[1])
    evs, pend = [], {}
    for x in w:
        if x[0] in M.KINDS:
            f, c = M.t_abs(x[1], x[2])
            pend = {"kind": x[0], "frame": f - f0, "t": f * M.FT[real] + c}
            evs.append(pend)
        elif len(x) == 3 and x[1] == "mem":
            pend[x[0]] = bytes.fromhex(x[2])
    rows = M.loops_of(evs)
    if not compare:
        return [{"frame": lp["wake"]["frame"]} for lp in rows], start(w, f0, c0)
    g = M.model_for("game", real)
    bad = []
    planned = M.events(real)
    for k, lp in enumerate(rows):
        v, n = lp["woke"]["v"], lp["woke"]["n"]
        got = list(v[:16]) + list(v[0x40:0x55]) + list(n[:6])
        g.loop += 1
        g.isr(model44.keys_at(planned, g.ticks + 1 + model44.EVENT_AHEAD))
        head, tail = M.model_light(g)
        if k > 0 and (got[:16] != head or got[16:] != tail):
            bad.append(k)
        g.sends()
        g.run()
    return len(rows), bad, M.PLAY_FRAMES[real]


def loops46(M, machine, real, ev, shift, frames=None, compare=True):
    import model46
    s = M.sym("game")
    tcl = 'L "c0 [machine_info VDP_cycle_in_frame]"\n'
    tcl += "".join(f'debug set_bp {s[k]} {{}} {{ L "{k} {M.POS}" }}\n'
                  for k in ("main", "isr", "isrend", "woke", "sent", "ran", "input"))
    tcl += (f'debug set_bp {s["woke"]} {{}} {{ M v {M.VARS[0]} {M.VARS[1]}; M e {M.ENGINE[0]} {M.ENGINE[1]}; '
            f'M nm {M.NAMES_RAM[0]} {M.NAMES_RAM[1]} }}\n')
    full = M.play_frames("game", real)
    w = M.run(M.rom("game"), machine, frames or full + shift, tcl, ev)
    c0 = int(next(x for x in w if x[0] == "c0")[1])
    f0 = int(next(x for x in w if x[0] == "f0")[1])
    evs, pend = [], {}
    for x in w:
        if x[0] in M.KINDS:
            f, c = M.t_abs(x[1], x[2])
            pend = {"kind": x[0], "frame": f - f0, "t": f * M.FT[real] + c}
            evs.append(pend)
        elif len(x) == 3 and x[1] == "mem":
            pend[x[0]] = bytes.fromhex(x[2])
    rows = M.loops_of(evs)
    if not compare:
        return [{"frame": lp["wake"]["frame"]} for lp in rows], start(w, f0, c0)
    g = M.model_for("game", real)
    planned = M.events("game", real)
    bad = []
    for k, lp in enumerate(rows):
        r = lp["woke"]
        g.loop += 1
        g.isr(model46.keys_at(planned, g.ticks + 1 + M.EVENT_AHEAD[real]))
        if M.ram_state(s, r["v"], r["e"]) != M.model_ram(g) or list(r["nm"]) != g.names or \
                M.engine_same(r["e"], g):
            bad.append(k)
        g.sends()
        g.run()
    return len(rows), bad, full


def main(argv):
    chapter, machine, rate = int(argv[1]), argv[2], int(argv[3])
    M = load(chapter)
    real = M.EU if rate == 50 else M.JP
    st, first = first_wake(M, chapter, machine, real)
    out = {"chapter": chapter, "machine": machine, "rate": rate, "start": st, "first": first}
    if first is None:                       # the game never gets to its loop
        print(json.dumps(out))
        return
    if len(argv) > 4:
        ref = int(argv[4])
    else:
        _, ref = first_wake(M, chapter, real, real)
    shift = first - ref
    planned = M.events(real) if chapter == 44 else M.events("game", real)
    ev = {f + shift: k for f, k in planned.items()}
    n, bad, frames = (loops44 if chapter == 44 else loops46)(M, machine, real, ev, shift)
    out.update({"shift": shift, "loops": n, "wrong": len(bad), "first_wrong": bad[:5]})
    last = frames - 2 + shift
    tmp = Path(tempfile.mkdtemp(prefix=f"play51_{chapter}_"))
    tev = (M.model44.tcl_events(ev) if chapter == 44 else M.model46.tcl_events(ev))
    pngs = M.msxcap.capture(M.rom("game"), [last], tmp, "f", machine=machine, events=tev,
                            timeout=3600)
    out.update({"last": last, "photo": str(pngs[last])})
    print(json.dumps(out))


if __name__ == "__main__":
    main(sys.argv)
