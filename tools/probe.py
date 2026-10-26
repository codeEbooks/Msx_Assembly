"""probe.py -- run a cartridge and read it with the debugger: the helpers the
chapters of Part II share.

    sym("ch08/modes.sym")                    {label: address}
    at_address(rom, addr, 'L "a [reg a]"')   run Tcl the first time PC reaches addr
    memory(rom, stop, start, n)              n bytes from start, when PC reaches stop
    block(rom, stop, start, n)               the same, for thousands of bytes
    times(rom, {"t0": a0, ...})              machine_info time and R at each address,
                                             every time it is reached (up to hits), on
                                             either machine
    read_lst(path)                           [(source, bytes)] of a sjasmplus listing
    assemble_lines(lines, args)              the bytes sjasmplus gives each line

Every one runs openMSX through tools/msxcap.py, on the book's machine, from
the cartridge's INIT; nothing here knows what the program is about.
"""
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import msxcap

# openMSX runs the Z80 at 3,579,545 Hz exactly (chapter 7 found that 315/88
# MHz is half a T-state out after 1.3 seconds)
CLOCK = 3579545


def sym(path):
    out = {}
    for line in Path(path).read_text().splitlines():
        lab, _, val = line.partition(": EQU 0x")
        if val:
            out[lab.strip()] = int(val, 16)
    return out


def at_address(rom, addr, tcl_body, frames=3):
    """run rom; the first time PC reaches addr, run tcl_body (it logs with L)"""
    tcl = f"set ::bp [debug set_bp {addr} {{}} {{ {tcl_body}; debug remove_bp $::bp }}]"
    return msxcap.run_tcl(rom, frames, tcl)


def memory(rom, stop, start, n, frames=3):
    """the n bytes from start when the program first reaches stop"""
    lines = at_address(rom, stop, f'set s ""; for {{set i 0}} {{$i < {n}}} {{incr i}} '
                                  f'{{append s " " [debug read memory [expr {{{start} + $i}}]]}}; '
                                  'L "mem$s"', frames)
    return [int(v) for v in next(l for l in lines if l.startswith("mem")).split()[1:]]


def block(rom, stop, start, n, frames=3):
    """like memory(), for many bytes: debug read_block, logged in hexadecimal"""
    lines = at_address(rom, stop, f'binary scan [debug read_block memory {start} {n}] H* h; '
                                  'L "blk $h"', frames)
    h = next(l for l in lines if l.startswith("blk ")).split()[1]
    return list(bytes.fromhex(h))


def times(rom, labels, frames=2, hits=1, extra="", machine=msxcap.DEFAULT_MACHINE):
    """{label: [(time, R, extra...), ...]}: the first `hits` times PC reaches
    each address; extra is more Tcl words to log, in brackets"""
    tcl = "\n".join(f'set ::n{lab} 0\nset ::b{lab} [debug set_bp {a} {{}} {{'
                    f'incr ::n{lab}; L "T {lab} [machine_info time] [reg r] {extra}"; '
                    f'if {{$::n{lab} >= {hits}}} {{debug remove_bp $::b{lab}}}}}]'
                    for lab, a in labels.items())
    lines = msxcap.run_tcl(rom, frames, tcl, machine=machine)
    out = {lab: [] for lab in labels}
    for line in lines:
        if line.startswith("T "):
            _, lab, t, r, *more = line.split()
            out[lab].append((float(t), int(r), *more))
    return out


LST = re.compile(r"^\s*(\d+)\s+([0-9A-F]{4})(.*)$")


def lst_fields(m):
    """(line number, address, bytes, source) of a matched listing line: the
    bytes are in the twelve columns after the address"""
    rest = m.group(3)
    return m.group(1), int(m.group(2), 16), [int(x, 16) for x in rest[1:13].split()], rest[13:]


def read_lst(path):
    """[(source line without its comment, address, bytes)] for every line of
    a sjasmplus listing that made bytes; a line whose bytes run on to the
    next line of the listing is joined up"""
    out, last = [], None
    for line in Path(path).read_text().splitlines():
        m = LST.match(line)
        if not m:
            continue
        num, addr, code, src = lst_fields(m)
        if num == last and out:
            out[-1][2].extend(code)
        elif code:
            out.append((src.split(";")[0].strip(), addr, code))
        last = num
    return out


def assemble_lines(lines, args=("--syntax=bF",)):
    """the bytes sjasmplus gives each line, assembled on their own at $4000;
    None for a line it refuses"""
    out = []
    tmp = Path(tempfile.mkdtemp(prefix="asm_"))
    try:
        for line in lines:
            (tmp / "x.asm").write_text(f"        ORG $4000\n        {line}\n")
            r = subprocess.run(["sjasmplus", "--nologo", "--msg=none", *args, "--lst=x.lst", "x.asm"],
                               cwd=tmp, capture_output=True, text=True)
            got = None
            if r.returncode == 0:
                got = next((c for _, a, c in read_lst(tmp / "x.lst") if a == 0x4000), None)
            out.append(got)
        return out
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
