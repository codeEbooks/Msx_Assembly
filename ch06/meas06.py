#!/usr/bin/env python3
"""meas06.py -- chapter 6: the console sessions, run as the book prints them.

    ./build.sh && python3 meas06.py              every section
                  python3 meas06.py step watch  only these, kept with the others
                  python3 meas06.py --missing   the sections not measured yet

Every session is typed into openMSX's console by tools/console.py, line by
line, and its answers are kept in a .txt file, which the chapter prints. Each
section then checks the answers against something that is not the console:

  stop       a running border.rom, a breakpoint on INIT, reset: the registers
             against chapter 3's at INIT, the disassembly against the cartridge
  step       the two OUTs one instruction at a time: A, the VDP's latch and its
             register 7 after each
  watch      a watchpoint on writes to port $99: where it stops, what the latch
             holds; and how many times C-BIOS writes $99 before INIT
  over       biosway.rom: step_in goes into the BIOS, step_over does not
  write      the console writes register 7 and the VRAM of a running program;
             the frames before and after, filmed
  dollar     $4010, 4010 and 0x4010 typed as addresses
  time       time.tcl run as the chapter tells the reader to run it
  answers    the workshop's questions 5 and 6, tried (for Appendix I)
  openmsx    all of it again with every other build (tools/versions.py)
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "tools"))
import console     # noqa: E402
import msxcap      # noqa: E402
import versions    # noqa: E402

CAPS = HERE / "captures"
INIT, STOP = 0x4010, 0x4019
RUNNING = ("time", 4)          # 4 seconds after power-on border.rom is in its loop


def keep(name, entries):
    (HERE / f"{name}.txt").write_text(console.transcript(entries))
    return [list(e) for e in entries]


def answer(entries, line, n=0):
    return [a for l, a, _ in entries if l == line][n]


# ---------------------------------------------------------------- stop
def stop():
    e = console.session(HERE / "border.rom",
                        ["reg pc", "debug set_bp 0x4010", "reset", "cpuregs", "disasm"],
                        start=RUNNING)
    regs = dict(re.findall(r"(\S+?)\s*=\s*([0-9A-F]+)", answer(e, "cpuregs")))
    # chapter 3 read the registers at INIT with the debugger's own reads
    ch3 = json.loads((REPO / "ch03" / "meas03.json").read_text())["sysvars"]
    rom = (HERE / "border.rom").read_bytes()
    dis = [l for l in answer(e, "disasm").splitlines() if l.strip()]
    for l in dis:
        addr, *rest = l.split()
        code = [int(b, 16) for b in re.findall(r"\b[0-9A-F]{2}\b", l.split("  ")[-1])]
        assert list(rom[int(addr, 16) - 0x4000:int(addr, 16) - 0x4000 + len(code)]) == code, l
    assert int(answer(e, "reg pc")) == STOP and int(regs["PC"], 16) == INIT
    same = {k: regs[k] == v for k, v in ch3["regs"].items() if k in regs}
    assert all(same.values()) and regs["IFF"] == "00" and int(regs["IM"]) == ch3["at_init"]["IM"], same
    return {"session": keep("stop", e), "registers": regs, "disasm_lines": len(dis),
            "same_as_chapter_3": sorted(same)}


# ---------------------------------------------------------------- step
STEP = ["step_in", "step_in", "reg a",
        "step_in", "debug read {VDP register latch status} 0", "debug read {VDP regs} 7",
        "step_in", "step_in", "debug read {VDP register latch status} 0",
        "debug read {VDP regs} 7", "reg pc"]


def step():
    e = console.session(HERE / "border.rom", STEP, start=INIT)
    latch = [a for l, a, _ in e if l.startswith("debug read {VDP register latch")]
    r7 = [a for l, a, _ in e if l.startswith("debug read {VDP regs}")]
    # the latch debuggables are not in every openMSX: the older builds answer
    # "No such debuggable", and versions.py counts the answers that differ
    readable = not any(x.startswith("No such debuggable") for x in latch)
    assert answer(e, "reg a") == "3" and r7 == ["244", "3"] and (latch == ["1", "0"] or not readable)
    assert int(answer(e, "reg pc")) == STOP
    return {"session": keep("step", e), "latch_readable": readable}


# ---------------------------------------------------------------- watch
WATCH = ["debug set_watchpoint write_io 0x99", "debug cont", "reg pc",
         "debug read {VDP data latch value} 0", "debug cont", "reg pc", "debug read {VDP regs} 7"]


def watch():
    e = console.session(HERE / "border.rom", WATCH, start=INIT)
    pcs = [int(a) for l, a, _ in e if l == "reg pc"]
    latch = answer(e, "debug read {VDP data latch value} 0")
    assert pcs == [0x4015, STOP] and (latch == "3" or latch.startswith("No such debuggable"))
    # C-BIOS's own writes to $99, from power-on to INIT
    tcl_setup = ('set ::n 0\ndebug set_watchpoint write_io 0x99 {} { incr ::n }\n')
    lines = msxcap.run_tcl(HERE / "border.rom", 1, 'L "writes $::n"', tcl_setup=tcl_setup)
    n = int(next(l for l in lines if l.startswith("writes ")).split()[1])
    return {"session": keep("watch", e), "cbios_writes_before_init": n}


# ---------------------------------------------------------------- over
def over():
    a = console.session(HERE / "biosway.rom",
                        ["step_in", "step_in", "step_in", "reg pc", "step_over", "reg pc", "reg iff"],
                        start=INIT)
    b = console.session(HERE / "biosway.rom", ["step_in", "step_in", "step_in", "step_in", "reg pc"],
                        start=INIT)
    pcs = [int(x) for l, x, _ in a if l == "reg pc"]
    into = int([x for l, x, _ in b if l == "reg pc"][0])
    assert pcs == [0x4015, 0x4018] and into == 0x0047, (pcs, into)
    return {"session": keep("over", a), "step_in_pc": into, "iff": answer(a, "reg iff")}


# ---------------------------------------------------------------- write
WRITE = ["debug write {VDP regs} 7 1",
         "set a 0x1A82",
         'foreach c [split "Written by the console" ""] { vpoke $a [scan $c %c]; incr a }']


def write():
    e = console.session(HERE / "border.rom", WRITE, start=RUNNING)
    # the same lines, typed into a film between frame 60 and 61 after INIT
    got = msxcap.capture(HERE / "border.rom", [60, 62], CAPS, "write_f",
                         events={61: "; ".join(WRITE)})
    before, after = (Image.open(got[n]).convert("RGB") for n in (60, 62))
    assert before.getpixel((5, 5)) == (115, 217, 124) and after.getpixel((5, 5)) == (0, 5, 0)
    import screentext
    text = screentext.Page(got[62], light_ink=True).line(20).strip()
    assert text == "Written by the console", text
    return {"session": keep("write", e), "row20": text, "frames": [60, 62]}


# ---------------------------------------------------------------- dollar
DOLLAR = ["debug read memory 0x4010", "debug read memory 4010", "debug read memory $4010",
          "format %04X 4010"]


def dollar():
    e = console.session(HERE / "border.rom", DOLLAR, start=RUNNING)
    bios = (Path(msxcap.CBIOS) / "cbios_main_msx1_eu.rom").read_bytes()
    assert answer(e, "debug read memory 0x4010") == str(0xF3)
    assert answer(e, "debug read memory 4010") == str(bios[4010])
    assert [x for l, x, err in e if err] == ['can\'t read "4010": no such variable']
    return {"session": keep("dollar", e), "bios_byte_4010": bios[4010]}


# ---------------------------------------------------------------- time
def time():
    home = msxcap.make_home()
    (home / "stop.tcl").write_text("after time 4 exit\n")
    xv, disp = msxcap.start_xvfb()
    try:
        r = subprocess.run([msxcap.OPENMSX, "-machine", "MSXBOOK_EU16", "-carta", "border.rom",
                            "-script", "time.tcl", "-script", str(home / "stop.tcl")],
                           cwd=HERE, env=dict(__import__("os").environ, HOME=str(home), DISPLAY=disp,
                                              SDL_AUDIODRIVER="dummy"),
                           capture_output=True, text=True, timeout=300)
    finally:
        xv.terminate()
        xv.wait()
        shutil.rmtree(home, ignore_errors=True)
    lines = [l for l in r.stdout.splitlines() if "INIT to stop" in l]
    (HERE / "time_out.txt").write_text("\n".join(lines) + "\n")
    t = int(re.search(r"(\d+) T-states", lines[0]).group(1))
    assert len(lines) == 1 and t == 5 + 8 + 12 + 8 + 12, lines
    return {"output": lines, "t_states": t}


# ---------------------------------------------------------------- answers
def answers():
    """the workshop: the byte at $0038, and time.tcl pointed at biosway.rom"""
    bios = (Path(msxcap.CBIOS) / "cbios_main_msx1_eu.rom").read_bytes()
    e = console.session(HERE / "border.rom", ["debug read memory 0x0038", "disasm 0x0038 2"],
                        start=RUNNING)
    tmp = Path(tempfile.mkdtemp(prefix="time6_"))
    try:
        sym = {l.split(":")[0]: int(l.split("0x")[1], 16)
               for l in (HERE / "biosway.sym").read_text().splitlines() if ": EQU 0x" in l}
        (tmp / "time.tcl").write_text((HERE / "time.tcl").read_text()
                                      .replace("0x4019", f"0x{sym['stop']:04X}"))
        (tmp / "stop.tcl").write_text("after time 4 exit\n")
        shutil.copy(HERE / "biosway.rom", tmp)
        home = msxcap.make_home()
        xv, disp = msxcap.start_xvfb()
        try:
            r = subprocess.run([msxcap.OPENMSX, "-machine", "MSXBOOK_EU16", "-carta", "biosway.rom",
                                "-script", "time.tcl", "-script", "stop.tcl"], cwd=tmp,
                               env=dict(__import__("os").environ, HOME=str(home), DISPLAY=disp,
                                        SDL_AUDIODRIVER="dummy"),
                               capture_output=True, text=True, timeout=300)
        finally:
            xv.terminate()
            xv.wait()
            shutil.rmtree(home, ignore_errors=True)
        biosway = [l for l in r.stdout.splitlines() if "INIT to stop" in l]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    # question 2: a watchpoint set before reset sees C-BIOS's writes too
    w = console.session(HERE / "border.rom", ["set ::n 0", "debug set_watchpoint write_io 0x99 {} {incr ::n}",
                                               "debug set_bp 0x4019", "reset", "set ::n"], start=RUNNING)
    assert answer(e, "debug read memory 0x0038") == str(bios[0x38])
    return {"byte_0038": answer(e, "debug read memory 0x0038"), "disasm_0038": answer(e, "disasm 0x0038 2"),
            "biosway_time": biosway, "biosway_stop": f"{sym['stop']:04X}",
            "writes_through_reset": int(answer(w, "set ::n"))}


# ---------------------------------------------------------------- openmsx
def openmsx():
    if not versions.builds():
        return {"skipped": "OPENMSX_BUILDS not set"}
    return versions.every_build(["ch06"], [k for k in SECTIONS if k != "openmsx"])


SECTIONS = {"stop": stop, "step": step, "watch": watch, "over": over, "write": write,
            "dollar": dollar, "time": time, "answers": answers, "openmsx": openmsx}


def main(names=()):
    CAPS.mkdir(exist_ok=True)
    path = HERE / "meas06.json"
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
    print(json.dumps(main(sys.argv[1:]), indent=1)[:3000])
