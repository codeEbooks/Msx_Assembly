#!/usr/bin/env python3
"""meas05.py -- chapter 5, measured.

    ./build.sh && python3 meas05.py              every section
                  python3 meas05.py start ba    only these, kept with the others
                  python3 meas05.py --missing   the sections not measured yet

  assembly   sjasmplus border.asm as a reader runs it; the listing; the bytes
             of the cartridge against the Z80's opcodes, assembled by hand here
  errors     typo.asm and margin.asm: what sjasmplus says, the exit code, the
             cartridge it writes anyway, and what that cartridge does
  start      border.rom filmed from power-on: the frame and the line in which
             INIT runs, against the frame and the row where the border turns
  japan      the same on the Japanese machine: when it starts, its page, the loop
  clock      frame 1 of a film from INIT is the frame after INIT's, from power-on
  loop       how many times JR stop runs in one frame, against 71,364 / 13
  ba         the header "BA": C-BIOS's own screen, read back character by character
  noend      no last line: where the processor goes, with the debugger; and the
             photographs, against border.rom's
  di         the two OUTs a frame apart (wait.asm) and an interrupt between them
             (split.asm): register 7 from the debugger, the border from the film
  monitor    the console commands the chapter prints, run as printed
  bios       border.rom against biosway.rom, which calls the BIOS's WRTVDP:
             time, bytes, the BIOS's copy of register 7, the interrupts after
  photograph msxcap.py run as the chapter tells the reader to run it
  answers    the workshop's last question, tried (for Appendix I)
  openmsx    all of the above again with every other build of openMSX
             (tools/versions.py; the builds are listed in OPENMSX_BUILDS)
"""
import json
import os
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
import meas        # noqa: E402
import msxcap      # noqa: E402
import screentext  # noqa: E402
import versions    # noqa: E402

CAPS = HERE / "captures"
EU = "MSXBOOK_EU16"
CLOCK = 3579545
FRAME_T = meas.T_PER_FRAME[EU]
INIT = 0x4010
# the colour codes as openMSX shows them, measured by chapter 1's palette.rom
RGB = {(0, 0, 0): 0, (0, 5, 0): 1, (115, 217, 124): 3, (91, 96, 223): 4, (130, 130, 238): 5,
       (98, 228, 235): 7, (249, 255, 248): 15}
DARK_BLUE, LIGHT_GREEN = 4, 3


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    return r.returncode, r.stdout + r.stderr


def colour(png, xy=(5, 5)):
    rgb = Image.open(png).convert("RGB").getpixel(xy)
    return RGB.get(rgb, str(rgb))


def same(a, b):
    return Image.open(a).convert("RGB").tobytes() == Image.open(b).convert("RGB").tobytes()


def assemble_copy(name, extra=()):
    """sjasmplus name.asm in a copy of the folder: (exit code, output lines, the
    cartridge it wrote or None, the folder)"""
    tmp = Path(tempfile.mkdtemp(prefix="asm05_"))
    for f in (f"{name}.asm", "msx.inc"):
        shutil.copy(HERE / f, tmp / f)
    rc, text = run(["sjasmplus", *extra, f"{name}.asm"], cwd=tmp)
    lines = [l for l in text.splitlines() if l.strip()]
    rom = tmp / f"{name}.rom"
    return rc, lines, (rom.read_bytes() if rom.exists() else None), tmp


def printed(lines):
    """the output as the book prints it: without the time it took"""
    return [re.sub(r", work time: [0-9.]+ seconds", "", l) for l in lines]


# ---------------------------------------------------------------- assembly
# the Z80's opcodes for the six instructions of border.asm (Zilog's tables)
OPCODES = {"di": [0xF3], "ld a,n": [0x3E], "out (n),a": [0xD3], "jr e": [0x18]}


def assembly():
    rc, lines, rom, tmp = assemble_copy("border")
    (HERE / "border_out.txt").write_text("\n".join(printed(lines)) + "\n")
    rc2, _, _, tmp2 = assemble_copy("border", ["--lst=border.lst"])
    lst = (tmp2 / "border.lst").read_text()
    (HERE / "border.lst").write_text(lst)
    shutil.rmtree(tmp, ignore_errors=True)
    shutil.rmtree(tmp2, ignore_errors=True)
    assert rom == (HERE / "border.rom").read_bytes(), "the reader's border.rom is the book's"
    # the program, assembled by hand: LIGHT_GREEN is 3, VDP_CTRL is $99,
    # register 7 is $80 | 7, and JR stop jumps to itself: -2 from the next address
    model = (OPCODES["di"] + OPCODES["ld a,n"] + [3] + OPCODES["out (n),a"] + [0x99] +
             OPCODES["ld a,n"] + [0x80 | 7] + OPCODES["out (n),a"] + [0x99] +
             OPCODES["jr e"] + [(-2) & 0xFF])
    code = list(rom[INIT - 0x4000:INIT - 0x4000 + len(model)])
    assert code == model, (code, model)
    header = list(rom[:16])
    assert header[:4] == [0x41, 0x42, INIT & 0xFF, INIT >> 8] and not any(header[4:])
    pad = rom[INIT - 0x4000 + len(model):]
    assert set(pad) == {0xFF} and len(rom) == 0x4000
    return {"rc": rc, "output": printed(lines), "rom_bytes": len(rom),
            "header": [f"{b:02X}" for b in header], "code": [f"{b:02X}" for b in code],
            "code_at": f"{INIT:04X}", "padding": len(pad), "stop": f"{INIT + len(model) - 2:04X}"}


# ---------------------------------------------------------------- errors
def errors():
    out = {}
    for name in ("typo", "margin"):
        rc, lines, rom, tmp = assemble_copy(name)
        errs = [l for l in printed(lines) if "): error" in l or l.startswith("Errors:")]
        (HERE / f"{name}_out.txt").write_text("\n".join(errs) + "\n")
        code = list(rom[INIT - 0x4000:INIT - 0x4000 + 12]) if rom else None
        got = r7 = None
        if rom:
            r = tmp / f"{name}.rom"
            shot = msxcap.capture(r, [60], tmp / "c", "f")
            got = colour(shot[60])
            lines = msxcap.run_tcl(r, 61, "", events={60: 'L "R7 [format %02X [debug read {VDP regs} 7]]"'})
            r7 = next(l for l in lines if l.startswith("R7 ")).split()[1]
        shutil.rmtree(tmp, ignore_errors=True)
        out[name] = {"rc": rc, "errors": errs, "rom_written": rom is not None,
                     "code": [f"{b:02X}" for b in code] if code else None, "border_frame60": got,
                     "R7": r7}
    return out


# ---------------------------------------------------------------- start
def frame_log(rom, frames, bp=None):
    """run from power-on, logging every frame's start and, at bp, the frame,
    the time and the VDP's position in its frame"""
    setup = '''
proc fr {} { L "frame [machine_info VDP_frame_count] [machine_info time]"; after frame fr }
after frame fr
'''
    if bp is not None:
        setup += f'''debug set_bp {bp} {{}} {{ if {{![info exists ::bp]}} {{ set ::bp 1; L "bp [machine_info VDP_frame_count] [machine_info time] [machine_info VDP_cycle_in_frame]" }} }}
'''
    return msxcap.run_tcl(rom, frames, "", tcl_setup=setup)


def start():
    rom = HERE / "border.rom"
    got, init, _ = msxcap.film_power(rom, range(128, 141), CAPS, "border_p")
    # the debugger: when the second OUT starts ($4017), and where the VDP is
    lines = frame_log(rom, 2, bp=0x4017)
    bp = next(l for l in lines if l.startswith("bp ")).split()
    f_out, t_out, cyc = int(bp[1]), float(bp[2]), int(bp[3])
    line, t_in_line = cyc // 1368, (cyc % 1368) // 6
    f0 = next(l for l in lines if l.startswith("f0 ")).split()
    t_init = float(f0[3])
    frame_start = {int(l.split()[1]): float(l.split()[2]) for l in lines if l.startswith("frame ")}
    # the film: the first pixel, in raster order, that is light green
    kinds = {n: (colour(p), colour(p, (5, 235))) for n, p in got.items()}
    split = [n for n, (top, bottom) in kinds.items() if bottom == LIGHT_GREEN != top]
    assert len(split) == 1, kinds
    n = split[0]
    im = Image.open(got[n]).convert("RGB")
    # inside the columns the VDP draws, where every openMSX agrees (chapter 4)
    x0, x1 = meas.DRAWN
    first = next((y, x) for y in range(240) for x in range(x0, x1 + 1)
                 if RGB.get(im.getpixel((x, y))) == LIGHT_GREEN)
    # the model: frame line `line` is capture row line - 45 (tools/meas.py); the
    # OUT (n),A writes 8 T-states after it starts, 2 sooner than OUT (C),r, whose
    # write shows at x = ceil(1.5 t - 16)
    row_model = line - meas.FRAME_LINE_OF_ROW0[EU]
    x_model = -(-(3 * (t_in_line - 2) - 32) // 2)
    info = screentext.Page(got[n + 1], light_ink=True)
    text = [info.line(r).strip() for r in range(24) if info.line(r).strip()]
    keep = {n, n + 1}
    for k, p in got.items():
        if k not in keep:
            p.unlink()
    out = {"init_frame": init, "init_seconds": round(t_init, 4),
           "out_frame": f_out, "out_line": line, "out_t_in_line": t_in_line,
           "out_t_in_frame": round((t_out - frame_start[f_out]) * CLOCK),
           "init_t_in_frame": round((t_init - frame_start[init]) * CLOCK),
           "split_frame": n, "first_green_row": first[0], "first_green_x_drawn": first[1],
           "row_model": row_model, "x_model": x_model,
           "whole_frame": n + 1, "frames": {str(k): v for k, v in kinds.items()},
           "screen_text": text}
    assert n == init == f_out and first == (row_model, max(x_model, x0)), out
    # DI 5, LD A,n 8, OUT (n),A 12, LD A,n 8: from INIT to the second OUT
    assert out["out_t_in_frame"] - out["init_t_in_frame"] == 5 + 8 + 12 + 8, out
    return out


# ---------------------------------------------------------------- japan
def japan():
    """the same cartridge on the Japanese machine"""
    jp = "MSXBOOK_JP16"
    tmp = Path(tempfile.mkdtemp(prefix="jp_"))
    try:
        got, init, _ = msxcap.film_power(HERE / "border.rom", range(130, 150), tmp, "j",
                                         machine=jp)
        kinds = {n: (colour(p), colour(p, (5, 235))) for n, p in got.items()}
        whole = min(n for n, (t, b) in kinds.items() if t == b == LIGHT_GREEN)
        page = screentext.Page(got[whole], machine=jp, light_ink=True)
        text = [page.line(r).strip() for r in range(24) if page.line(r).strip()]
        ev = {10: 'set ::turns 0', 11: 'L "turns $::turns"'}
        lines = msxcap.run_tcl(HERE / "border.rom", 12, "set ::turns 0\n"
                               "debug set_bp 0x4019 {} { incr ::turns }", machine=jp, events=ev)
        turns = int(next(l for l in lines if l.startswith("turns ")).split()[1])
        assert abs(turns - meas.T_PER_FRAME[jp] / 13) < 1 and whole == init + 1, (turns, whole, init)
        return {"init_frame": init, "whole_frame": whole, "text": text, "turns_in_a_frame": turns,
                "model": meas.T_PER_FRAME[jp] / 13}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------- clock
def clock():
    tmp = Path(tempfile.mkdtemp(prefix="clock_"))
    try:
        a = msxcap.capture(HERE / "border.rom", [1, 2], tmp, "i")
        b, init, _ = msxcap.film_power(HERE / "border.rom", [136, 137], tmp, "p")
        return {"init": init, "from_init_1_is_power": init + 1 if same(a[1], b[init + 1]) else None,
                "from_init_2_is_power": init + 2 if same(a[2], b[init + 2]) else None}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------- loop
def loop():
    stop = int(json.loads((HERE / "meas05.json").read_text())["assembly"]["stop"], 16) \
        if (HERE / "meas05.json").exists() else 0x4019
    tcl = f'''set ::turns 0
debug set_bp {stop} {{}} {{ incr ::turns }}'''
    ev = {10: 'set ::turns 0', 11: 'L "turns $::turns iff [reg iff]"'}
    lines = msxcap.run_tcl(HERE / "border.rom", 12, tcl, events=ev)
    turns = int(next(l for l in lines if l.startswith("turns ")).split()[1])
    iff = int(next(l for l in lines if l.startswith("turns ")).split()[3])
    assert abs(turns - FRAME_T / 13) < 1, turns
    return {"turns_in_a_frame": turns, "model": FRAME_T / 13, "jr_t": 13, "iff": iff}


# ---------------------------------------------------------------- ba
def ba():
    got, init, _ = msxcap.film_power(HERE / "ba.rom", list(range(128, 161)) + [400], CAPS, "ba_p")
    final = got[400]
    settled = min(n for n in got if all(same(got[m], final) for m in got if m >= n))
    page = screentext.Page(final, light_ink=True)
    text = [(r, page.line(r).strip()) for r in range(24) if page.line(r).strip()]
    for k, p in got.items():
        if k != 400:
            p.unlink()
    assert init is None and any("No cartridge found." in t for _, t in text)
    return {"init_called": init is not None, "settled_from": settled, "text": text,
            "border": colour(final)}


# ---------------------------------------------------------------- noend
def noend():
    rom = HERE / "noend.rom"
    code_end = 0x4019                      # border.rom's JR stop, which noend.asm has not
    tcl = rf'''
set ::seen [dict create]
set ::rst 0
proc once {{tag}} {{
    if {{![dict exists $::seen $tag]}} {{
        dict set ::seen $tag 1
        L "$tag [machine_info VDP_frame_count] [machine_info time] [format %02X [debug read ioports 0xA8]] [format %04X [reg pc]] [format %02X%02X [debug read memory [reg pc]] [debug read memory [expr {{[reg pc] + 1}}]]] $::rst"
    }}
}}
# where INIT would return to, if it returned: the address on the stack now
set ::back [expr {{[debug read memory [reg sp]] | [debug read memory [expr {{[reg sp] + 1}}]] << 8}}]
L "back [format %04X $::back]"
debug set_bp $::back {{}} {{ once BACK }}
debug set_bp {code_end} {{}} {{ once FIRST }}
debug set_bp 0x0038 {{}} {{ if {{![dict exists $::seen PAGE2]}} {{ incr ::rst }} }}
debug set_bp 0x7FFF {{}} {{ once LAST }}
debug set_bp 0x8000 {{}} {{ once PAGE2 }}
# bytes sent to the VRAM: in page 2, and after the return into C-BIOS
set ::vram [dict create PAGE2 0 BACK 0]
debug set_watchpoint write_io 0x98 {{}} {{
    if {{[dict exists $::seen BACK]}} {{ dict incr ::vram BACK }} elseif {{[dict exists $::seen PAGE2]}} {{ dict incr ::vram PAGE2 }}
}}
'''
    lines = msxcap.run_tcl(rom, 200, tcl,
                           events={180: 'L "vram [dict get $::vram PAGE2] [dict get $::vram BACK]"',
                                   190: 'L "end [format %04X [reg pc]] [format %02X%02X [debug read memory [reg pc]] [debug read memory [expr {[reg pc] + 1}]]] [format %02X [debug read ioports 0xA8]] [reg iff]"'})
    ev = {l.split()[0]: l.split()[1:] for l in lines
          if l.split()[0] in ("back", "BACK", "FIRST", "LAST", "PAGE2", "end", "vram")}
    t_first, t_last = float(ev["FIRST"][1]), float(ev["LAST"][1])
    rsts = int(ev["PAGE2"][5])
    per_byte = (t_last - t_first) * CLOCK / (0x7FFF - code_end)
    # where it ends: a breakpoint there, once, to know the frame it got there in
    end_pc = int(ev["end"][0], 16)
    lines2 = msxcap.run_tcl(rom, 200, f'''debug set_bp {end_pc} {{}} {{ if {{![info exists ::e]}} {{ set ::e 1; L "arrive [machine_info VDP_frame_count] [machine_info time]" }} }}''')
    arrive = next(l for l in lines2 if l.startswith("arrive ")).split()
    # the photographs: noend.rom against border.rom, from power-on; the last
    # one is kept for the figure, and its text read back
    tmp = Path(tempfile.mkdtemp(prefix="noend_"))
    frames = [136, 185, int(ev["BACK"][0]), int(ev["BACK"][0]) + 1, int(arrive[1]) + 1, 400]
    a, _, _ = msxcap.film_power(rom, frames, tmp, "n")
    b, _, _ = msxcap.film_power(HERE / "border.rom", frames, tmp, "b")
    alike = [n for n in frames if same(a[n], b[n])]
    shutil.copy(a[400], CAPS / "noend_p0400.png")
    page = screentext.Page(a[400], light_ink=True)
    text = [(r, page.line(r).strip()) for r in range(24) if page.line(r).strip()]
    shutil.rmtree(tmp, ignore_errors=True)
    out = {"first_ff_frame": int(ev["FIRST"][0]), "first_ff_byte": ev["FIRST"][4][:2],
           "last_byte_frame": int(ev["LAST"][0]), "page2_frame": int(ev["PAGE2"][0]),
           "page2_a8": ev["PAGE2"][2], "page2_bytes": ev["PAGE2"][4],
           "rst38_before_page2": rsts, "bytes_walked": 0x8000 - code_end,
           "t_per_byte": round(per_byte, 1),
           "seconds_to_page2": round(t_last - t_first, 3),
           "end_pc": ev["end"][0], "end_bytes": ev["end"][1], "end_a8": ev["end"][2],
           "end_iff": int(ev["end"][3]), "end_frame": int(arrive[1]),
           "back_to": ev["back"][0], "back_frame": int(ev["BACK"][0]),
           "vram_writes_in_page2": int(ev["vram"][0]), "vram_writes_after": int(ev["vram"][1]),
           "photos_alike": alike, "photo_frames": frames, "text": text}
    assert ev["end"][1] == "18FE", "it ends on a jump to itself"
    assert alike == frames[:3] and any("No cartridge found." in t for _, t in text), (alike, text)
    assert out["rst38_before_page2"] >= out["bytes_walked"]
    return out


# ---------------------------------------------------------------- di
def di():
    out = {}
    for name in ("wait", "split"):
        rom = HERE / f"{name}.rom"
        sym = {l.split(":")[0]: int(l.split("0x")[1], 16)
               for l in (HERE / f"{name}.sym").read_text().splitlines() if ": EQU 0x" in l}
        stop = sym["stop"]
        tcl = rf'''
set ::isr 0
set ::armed 0
debug set_bp {INIT + 1 + 2 + 2} {{}} {{ set ::armed 1; L "first [machine_info VDP_frame_count] [machine_info time]" }}
debug set_bp 0x0038 {{}} {{ if {{$::armed}} {{ incr ::isr }} }}
debug set_bp {stop} {{}} {{ if {{$::armed}} {{ set ::armed 0; L "second [machine_info VDP_frame_count] [machine_info time] $::isr" }} }}
'''
        ev = {60: 'L "R7 [format %02X [debug read {VDP regs} 7]]"'}
        lines = msxcap.run_tcl(rom, 61, tcl, events=ev)
        first = next(l for l in lines if l.startswith("first ")).split()
        second = next(l for l in lines if l.startswith("second ")).split()
        r7 = next(l for l in lines if l.startswith("R7 ")).split()[1]
        tmp = Path(tempfile.mkdtemp(prefix="di_"))
        shot = msxcap.capture(rom, [60], tmp, "d")
        out[name] = {"gap_frames": round((float(second[2]) - float(first[2])) * CLOCK / FRAME_T, 2),
                     "isr_between": int(second[3]), "R7": r7, "border": colour(shot[60])}
        shutil.rmtree(tmp, ignore_errors=True)
    assert out["wait"]["border"] == LIGHT_GREEN and out["split"]["border"] == DARK_BLUE
    return out


# ---------------------------------------------------------------- monitor
CONSOLE = ['debug read "VDP regs" 7', "reg pc", "debug read memory 0xF3E6"]


def monitor():
    """the commands the chapter tells the reader to type in openMSX's console,
    run as they are written, with border.rom running"""
    tcl = "; ".join(f'L "answer {k} [eval {{{c}}}]"' for k, c in enumerate(CONSOLE))
    lines = msxcap.run_tcl(HERE / "border.rom", 61, "", events={60: tcl})
    got = {int(l.split()[1]): l.split(maxsplit=2)[2] for l in lines if l.startswith("answer ")}
    return {"console": [[c, got[k]] for k, c in enumerate(CONSOLE)]}


# ---------------------------------------------------------------- bios
def bios():
    """border.rom against biosway.rom: the time from the instruction after DI
    to stop, the bytes in between, what the BIOS's copy of register 7 says,
    and whether interrupts are on afterwards"""
    out = {}
    tmp = Path(tempfile.mkdtemp(prefix="bios_"))
    for name in ("border", "biosway"):
        rom = HERE / f"{name}.rom"
        sym = {l.split(":")[0]: int(l.split("0x")[1], 16)
               for l in (HERE / f"{name}.sym").read_text().splitlines() if ": EQU 0x" in l}
        stop = sym["stop"]
        tcl = rf'''
set ::isr 0
debug set_bp {INIT + 1} {{}} {{ if {{![info exists ::a]}} {{ set ::a [machine_info time] }} }}
debug set_bp {stop} {{}} {{ if {{![info exists ::b]}} {{ set ::b [machine_info time]; L "took [expr {{($::b - $::a) * {CLOCK}}}]" }} }}
debug set_bp 0x0038 {{}} {{ incr ::isr }}
'''
        ev = {10: 'set ::isr 0',
              20: 'L "at20 [reg iff] [format %02X [debug read memory 0xF3E6]] '
                  '[format %02X [debug read {VDP regs} 7]] $::isr"'}
        lines = msxcap.run_tcl(rom, 21, tcl, events=ev)
        took = float(next(l for l in lines if l.startswith("took ")).split()[1])
        at = next(l for l in lines if l.startswith("at20 ")).split()
        data = rom.read_bytes()[INIT + 1 - 0x4000:stop - 0x4000]
        shot = msxcap.capture(rom, [60], tmp, name)
        out[name] = {"t_states": round(took), "bytes": len(data), "code": [f"{b:02X}" for b in data],
                     "iff": int(at[1]), "RG7SAV": at[2], "R7": at[3], "isr_in_10_frames": int(at[4]),
                     "frame60": shot[60].name}
    out["same_picture"] = same(tmp / out["border"]["frame60"], tmp / out["biosway"]["frame60"])
    shutil.rmtree(tmp, ignore_errors=True)
    for k in ("border", "biosway"):
        del out[k]["frame60"]
    b, w = out["border"], out["biosway"]
    assert b["t_states"] == 8 + 12 + 8 + 12 and b["iff"] == 0 and b["isr_in_10_frames"] == 0
    assert b["R7"] == w["R7"] == "03" and w["RG7SAV"] == "03" and b["RG7SAV"] == "F4"
    return out


# ---------------------------------------------------------------- photograph
def photograph():
    shutil.rmtree(HERE / "shots", ignore_errors=True)
    rc, text = run([sys.executable, "../tools/msxcap.py", "border.rom", "1", "--out", "shots"], cwd=HERE)
    shot = HERE / "shots" / "border_f0001.png"
    if not shot.exists():
        shot = next((HERE / "shots").glob("*.png"))
    st = json.loads((HERE / "meas05.json").read_text())["start"]
    whole = CAPS / f"border_p{st['whole_frame']:04d}.png"
    alike = same(shot, whole)
    shutil.rmtree(HERE / "shots", ignore_errors=True)
    return {"rc": rc, "output": text.strip().replace(str(HERE) + "/", ""), "same_as_power_frame": alike}


# ---------------------------------------------------------------- answers
def answers():
    """the workshop's last question, tried: border.asm with RET for its loop"""
    tmp = Path(tempfile.mkdtemp(prefix="ret_"))
    try:
        src = (HERE / "border.asm").read_text()
        assert "stop:   jr stop" in src
        (tmp / "ret.asm").write_text(src.replace('OUTPUT "border.rom"', 'OUTPUT "ret.rom"')
                                     .replace("stop:   jr stop", "        ret"))
        shutil.copy(HERE / "msx.inc", tmp)
        rc, _ = run(["sjasmplus", "--nologo", "--msg=err", "ret.asm"], cwd=tmp)
        got, init, _ = msxcap.film_power(tmp / "ret.rom", [400], tmp, "r")
        page = screentext.Page(got[400], light_ink=True)
        text = [page.line(r).strip() for r in range(24) if page.line(r).strip()]
        out = {"ret": {"rc": rc, "init": init, "text": text, "border": colour(got[400])}}
        # question 3: stop one instruction earlier, on the second OUT
        a = "        out (VDP_CTRL), a       ; register 7: the border\nstop:   jr stop"
        assert a in src
        (tmp / "early.asm").write_text(src.replace('OUTPUT "border.rom"', 'OUTPUT "early.rom"').replace(
            a, "stop:   out (VDP_CTRL), a       ; register 7: the border\n        jr stop"))
        rc, _ = run(["sjasmplus", "--nologo", "--msg=err", "early.asm"], cwd=tmp)
        data = (tmp / "early.rom").read_bytes()
        lines = msxcap.run_tcl(tmp / "early.rom", 61, "", events={60: 'L "R7 [format %02X [debug read {VDP regs} 7]]"'})
        shot = msxcap.capture(tmp / "early.rom", [60], tmp, "e")
        out["early"] = {"rc": rc, "code": [f"{b:02X}" for b in data[0x10:0x1B]],
                        "R7": next(l for l in lines if l.startswith("R7 ")).split()[1],
                        "border": colour(shot[60])}
        return out
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------- openmsx
def openmsx():
    """every section above, again, with every other build of openMSX"""
    if not versions.builds():
        return {"skipped": "OPENMSX_BUILDS not set"}
    return versions.every_build(["ch05"], [k for k in SECTIONS if k != "openmsx"])


SECTIONS = {"assembly": assembly, "errors": errors, "start": start, "japan": japan, "clock": clock,
            "loop": loop,
            "ba": ba, "noend": noend, "di": di, "monitor": monitor, "bios": bios,
            "photograph": photograph,
            "answers": answers,
            "openmsx": openmsx}


def main(names=()):
    CAPS.mkdir(exist_ok=True)
    path = HERE / "meas05.json"
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
