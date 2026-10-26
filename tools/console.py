"""console.py -- type commands into openMSX's console, and keep what it answers.

The chapters that print a console session (chapter 6 and after) do not copy
it from a screen: this module runs openMSX on a hidden screen with the book's
machine and cartridge, stops the machine where the session starts, and runs
the lines one by one exactly as they are written, as the console would. Each
line's answer is kept, an error included. A line that sets the machine going
again (step_in, step_over, debug step, debug cont, run_to ...) is followed by
waiting for the machine to stop; the next line runs when it has.

    lines = session("border.rom", ["cpuregs", "step_in", "reg pc"], start=0x4010)
    -> [("cpuregs", "AF =1F08 ..."), ("step_in", ""), ("reg pc", "16401")]

The session starts at the first time the processor reaches `start`; with
start=None it starts at the cartridge's INIT; with start=("time", s) it starts
s seconds after power-on, wherever the program is, the way a reader opens the
console on a program that is running.
"""
from pathlib import Path

import msxcap

RESUMES = ("step", "step_in", "step_over", "step_out", "debug step", "debug cont", "run_to", "reset")


def resumes(line):
    return any(line == r or line.startswith(r + " ") for r in RESUMES)


def tcl_quote(s):
    """a Tcl word that is exactly s"""
    return "{" + s + "}" if s.count("{") == s.count("}") and not s.endswith("\\") else \
        '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$").replace("[", "\\[") + '"'


def session(rom, lines, start=None, machine=msxcap.DEFAULT_MACHINE, timeout=300, setup=""):
    rom = Path(rom).resolve()
    start = msxcap.rom_init(rom) if start is None else start
    if isinstance(start, tuple):
        begin = f"after time {start[1]} next_line"         # typed while it runs
    else:
        begin = f"set ::start_bp [debug set_bp {start}]"
    home = msxcap.make_home()
    log = home / "console.log"
    words = "\n".join("    " + tcl_quote(l) for l in lines)
    resume = " ".join(tcl_quote(r) for r in RESUMES)
    (home / "console.tcl").write_text(f'''
set ::log [open {{{log}}} w]
proc L {{tag s}} {{ puts $::log "$tag [string length $s] $s"; flush $::log }}
set ::lines {{
{words}
}}
set ::resumes [list {resume}]
set ::i 0
proc resumes {{c}} {{
    foreach r $::resumes {{ if {{$c eq $r || [string first "$r " $c] == 0}} {{ return 1 }} }}
    return 0
}}
proc next_line {{}} {{
    while {{$::i < [llength $::lines]}} {{
        set c [lindex $::lines $::i]
        incr ::i
        L CMD $c
        if {{[catch {{uplevel #0 $c}} r]}} {{ L ERR $r }} else {{ L OUT $r }}
        if {{[resumes $c]}} {{ return }}
    }}
    L END ""
    exit
}}
proc on_break {{}} {{ after break on_break; next_line }}
after break on_break
{setup}
{begin}
after realtime {timeout} {{ L TIMEOUT ""; exit }}
''')
    msxcap.run_openmsx(rom, machine, home / "console.tcl", home, timeout + 30)
    data = log.read_text() if log.exists() else ""
    if "END 0" not in data:
        raise RuntimeError(f"the session did not finish (HOME {home}): {data[-300:]}")
    # entries are "TAG length text", the text possibly over several lines
    out, pos = [], 0
    while pos < len(data):
        tag, rest = data[pos:].split(" ", 1)
        n, rest = rest.split(" ", 1)
        text = rest[:int(n)]
        pos += len(tag) + 1 + len(n) + 1 + int(n) + 1
        if tag == "CMD":
            out.append([text, None, False])
        elif tag in ("OUT", "ERR"):
            out[-1][1] = text
            out[-1][2] = tag == "ERR"
    import shutil
    import os
    if os.environ.get("MSXCAP_KEEP") != "1":
        shutil.rmtree(home, ignore_errors=True)
    return [tuple(e) for e in out]


def transcript(entries, prompt="> "):
    """the session as the console shows it: each line after a prompt, its
    answer under it"""
    out = []
    for line, answer, error in entries:
        out.append(prompt + line)
        if answer:
            out.extend(answer.rstrip("\n").splitlines())
    return "\n".join(out) + "\n"
