#!/usr/bin/env python3
"""release.py - before a cartridge goes out: this book's checks, in one command.

    python3 release.py ROM [IMAGE WIRING ...] [--ram KB] [--json FILE] [--machines A,B,...]

    ROM           the cartridge to release, a plain ROM of 8, 16 or 32 KB
    IMAGE WIRING  an EPROM image and the board it is for, a15 or a14
                  (pack56.py): the 32 KB the processor reads through that
                  wiring is run with openMSX told the board's own mapping,
                  -romtype page12, instead of leaving openMSX to guess it

It checks:
  file      the size; the header: "AB" at the start, INIT inside the
            cartridge, STATEMENT, DEVICE, TEXT and the six bytes after them
            0; and gives the SHA-256
  machines  the cartridge on every machine in the book's folder machines/
            and on openMSX's twelve C-BIOS machines with at least KB of RAM
            up to $FFFF (16, the book's floor, unless --ram says otherwise;
            the others are listed, not run), from power-on, with no key
            pressed. The debugger reads the VRAM and the VDP's registers
            at the start of every frame, from INIT to FRAMES frames after it;
            vdpscreen.py makes the picture they give. The pictures must be
            those of the book's machine of the same rate, MSXBOOK_EU16 at
            50 Hz or MSXBOOK_JP16 at 60, from SETTLE frames after INIT to
            SETTLE before the end, all of them, perhaps up to SHIFT frames
            earlier or later. (The report counts too the frames whose
            16 KB of VRAM were the same, byte for byte: not a condition.)
            INIT must be called once. A machine's rate is the time from
            one frame to the next after INIT, as openMSX gives it
  boards    each EPROM image, so, on MSXBOOK_EU16, against the cartridge
            there
A check that fails makes the exit status 1.

The C-BIOS machines come from openMSX's share folder (RELEASE_STOCK_MACHINES,
by default /usr/share/openmsx/machines); without them the book's machines
alone are run, and the report says so.
"""
import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(HERE))
import msxcap      # noqa: E402
import vdpscreen   # noqa: E402
import pack56      # noqa: E402

FRAMES = 900                    # frames after INIT
SETTLE = 10                     # left out at each end of the comparison
SHIFT = 3                       # a machine may run the same pictures this many frames apart
LIMIT = 1500                    # frames from power-on, if INIT never comes
REF = {50: "MSXBOOK_EU16", 60: "MSXBOOK_JP16"}
STOCK = [f"C-BIOS_{v}{r}" for v in ("MSX1", "MSX2", "MSX2+") for r in ("", "_EU", "_JP", "_BR")]
STOCK_FROM = Path(os.environ.get("RELEASE_STOCK_MACHINES", "/usr/share/openmsx/machines"))

# The Tcl: a breakpoint on INIT, and at the start of every frame the time, the
# VDP's eight registers and, of the VRAM's sixteen blocks of 1 KB, those that
# changed since the frame before
TCL = r"""
set ::log [open {%LOG%} w]
proc L {s} { puts $::log $s; flush $::log }
set speed 2000
for {set i 0} {$i < 16} {incr i} { set ::last($i) -1 }
debug set_bp %INIT% {} { L "init [machine_info VDP_frame_count]"; if {![info exists ::init]} { set ::init [machine_info VDP_frame_count] } }
proc tick {} {
    set f [machine_info VDP_frame_count]
    for {set i 0} {$i < 16} {incr i} {
        set b [debug read_block VRAM [expr {$i * 1024}] 1024]
        set c [zlib crc32 $b]
        if {$c != $::last($i)} { binary scan $b H* h; L "v $f $i $h"; set ::last($i) $c }
    }
    set r {}
    for {set i 0} {$i < 8} {incr i} { lappend r [debug read {VDP regs} $i] }
    L "c $f [machine_info time] [join $r ,]"
    if {([info exists ::init] && $f >= $::init + %FRAMES%) || $f >= %LIMIT%} { L "done"; exit }
    after frame tick
}
after frame tick
"""


def ram_kb(xml):
    """the RAM a machine has below $10000, in KB, from its file: a RAM or a
    memory mapper whose window ends at $FFFF"""
    out = 0
    for dev in ET.parse(xml).getroot().iter():
        mem = dev.find("mem") if dev.tag in ("RAM", "MemoryMapper") else None
        if mem is not None:
            base, size = int(mem.get("base"), 16), int(mem.get("size"), 16)
            if base + size == 0x10000:
                out = max(out, size // 1024)
    return out


def machines_folder(names):
    """the machines' files in a folder of their own, for msxcap.py"""
    d = Path(tempfile.mkdtemp(prefix="release_"))
    for xml in sorted((REPO / "machines").glob("*.xml")):
        shutil.copy(xml, d)
    stock = [n for n in STOCK if (STOCK_FROM / f"{n}.xml").exists()]
    for n in stock:
        shutil.copy(STOCK_FROM / f"{n}.xml", d)
    msxcap.MACHINES = d
    found = sorted(p.stem for p in d.glob("*.xml"))
    book = [m for m in found if m.startswith("MSXBOOK_")]
    order = [REF[50], REF[60]] + [m for m in book if m not in REF.values()] + stock
    return d, [m for m in order if not names or m in names or m in REF.values()], len(stock)


def picture(vram, regs):
    """what the screen shows: the paper, with the sprites, and the border; or
    the border alone with the display off"""
    border = regs[7] & 15
    if not regs[1] & 0x40:
        return ("off", border)
    return (tuple(map(tuple, vdpscreen.draw(bytes(vram), regs))), border)


def film(rom, machine, init, extra=()):
    """the run of ROM on MACHINE: the frames at which INIT was called, and
    from the first, the time and a fingerprint of the picture of each frame"""
    home = msxcap.make_home()
    log, script = home / "release.log", home / "release.tcl"
    script.write_text(TCL.replace("%LOG%", str(log)).replace("%INIT%", str(init))
                      .replace("%FRAMES%", str(FRAMES)).replace("%LIMIT%", str(LIMIT)))
    msxcap.run_openmsx(Path(rom).resolve(), machine, script, home, 1800, list(extra))
    lines = log.read_text().splitlines() if log.exists() else []
    shutil.rmtree(home, ignore_errors=True)
    assert lines and lines[-1] == "done", (rom, machine, lines[-3:])
    vram, cache = bytearray(16384), {}
    inits, frames = [], {}
    for line in lines:
        w = line.split()
        if w[0] == "init":
            inits.append(int(w[1]))
        elif w[0] == "v":
            i = int(w[2])
            vram[i * 1024:(i + 1) * 1024] = bytes.fromhex(w[3])
        elif w[0] == "c":
            regs = [int(v) for v in w[3].split(",")]
            key = (hashlib.sha1(vram).digest(), tuple(regs))
            if key not in cache:
                cache[key] = hashlib.sha1(repr(picture(vram, regs)).encode()).hexdigest()
            frames[int(w[1])] = (float(w[2]), cache[key], key[0])
    return inits, frames


def against(run, ref):
    """the run against the reference's: the shift, from -SHIFT to SHIFT, that
    leaves the fewest pictures different, and how many"""
    inits, frames = run
    if not inits:
        return {"inits": 0, "pass": False}
    i0 = inits[0]
    t = [frames[i0 + k][0] for k in (5, 6)]
    rate = round(1 / (t[1] - t[0]))
    out = {"init": i0, "inits": len(inits), "rate": rate}
    if ref is None:
        return out
    r0, rf = ref[0][0], ref[1]
    best = None
    for s in range(-SHIFT, SHIFT + 1):
        diff = [k for k in range(SETTLE, FRAMES - SETTLE + 1)
                if frames.get(i0 + k + s, (0, None))[1] != rf[r0 + k][1]]
        if best is None or len(diff) < len(best[1]):
            best = (s, diff)
    s = best[0]
    same_vram = sum(1 for k in range(SETTLE, FRAMES - SETTLE + 1)
                    if frames.get(i0 + k + s, (0, None, None))[2] == rf[r0 + k][2])
    out.update(shift=s, different=len(best[1]), first_different=best[1][0] if best[1] else None,
               compared=FRAMES - 2 * SETTLE + 1, same_vram=same_vram)
    out["pass"] = out["inits"] == 1 and out["different"] == 0
    return out


def check_file(rom):
    data = Path(rom).read_bytes()
    init = data[2] | data[3] << 8 if len(data) >= 4 else 0
    out = {"file": Path(rom).name, "size": len(data), "sha256": hashlib.sha256(data).hexdigest(),
           "header": data[:2] == b"AB", "init": init,
           "init_inside": 0x4000 + 16 <= init < 0x4000 + len(data),
           "rest_zero": data[4:16] == bytes(12), "size_ok": len(data) in (0x2000, 0x4000, 0x8000)}
    out["pass"] = out["header"] and out["init_inside"] and out["rest_zero"] and out["size_ok"]
    return out


def release(rom, boards=(), names=(), ram=16):
    report = {"file": check_file(rom), "ram": ram}
    if not report["file"]["header"]:
        report["pass"] = False
        return report
    init = report["file"]["init"]
    before = msxcap.MACHINES
    folder, machines, nstock = machines_folder(names)
    report["stock_machines"] = nstock
    report["skipped"] = {m: ram_kb(folder / f"{m}.xml") for m in machines
                         if ram_kb(folder / f"{m}.xml") < ram}
    machines = [m for m in machines if m not in report["skipped"]]
    try:
        with ThreadPoolExecutor(2) as ex:
            runs = dict(zip(machines, ex.map(lambda m: film(rom, m, init), machines)))
        refs = {}
        for rate, m in REF.items():
            a = against(runs[m], None)
            assert a["rate"] == rate, (m, a)
            refs[rate] = (runs[m][0], runs[m][1])
        report["machines"] = {}
        for m in machines:
            a = against(runs[m], None)
            report["machines"][m] = against(runs[m], refs.get(a.get("rate")))
        report["boards"] = []
        for image, wiring in boards:
            view = pack56.cpu_view(Path(image).read_bytes(), wiring)
            tmp = Path(tempfile.mkdtemp(prefix="board_"))
            (tmp / "view.rom").write_bytes(view)
            run = film(tmp / "view.rom", REF[50], init, ["-romtype", "page12"])
            shutil.rmtree(tmp)
            b = against(run, refs[50])
            b.update(image=Path(image).name, wiring=wiring,
                     sha256=hashlib.sha256(Path(image).read_bytes()).hexdigest())
            report["boards"].append(b)
    finally:
        msxcap.MACHINES = before
        shutil.rmtree(folder, ignore_errors=True)
    report["pass"] = (report["file"]["pass"] and all(v["pass"] for v in report["machines"].values())
                      and all(b["pass"] for b in report["boards"]))
    return report


def show(report):
    """the report, in lines of at most 80 characters"""
    f = report["file"]
    lines = [f"{f['file']}: {f['size']:,} bytes", f"  SHA-256 {f['sha256']}",
             f"  header {'AB' if f['header'] else 'missing'}, INIT ${f['init']:04X}"
             f"{'' if f['init_inside'] else ' outside the cartridge'}"
             f"{'' if f['rest_zero'] else ', the rest of the header not 0'}"
             f"{'' if f['size_ok'] else ', not 8, 16 or 32 KB'}"]
    for m, v in report.get("machines", {}).items():
        if not v.get("inits"):
            lines.append(f"  {m:<16} FAIL INIT never called")
            continue
        again = "" if v["inits"] == 1 else f", {v['inits'] - 1} more"
        lines.append(f"  {m:<16} {'ok  ' if v['pass'] else 'FAIL'} {v['rate']} Hz  INIT at {v['init']}{again}"
                     f"  {v['different']:>3} of {v['compared']} different  shift {v['shift']:+d}")
    for b in report.get("boards", []):
        lines.append(f"  board {b['wiring']}: {b['image']:<21} {'ok  ' if b['pass'] else 'FAIL'} INIT "
                     f"{b['inits']} {'time' if b['inits'] == 1 else 'times'}, "
                     f"{b.get('different', '-')} of {b.get('compared', '-')} different")
    for m, kb in report.get("skipped", {}).items():
        lines.append(f"  {m:<16} not run: {kb} KB of RAM, --ram is {report['ram']}")
    if report.get("stock_machines") == 0:
        lines.append("  (openMSX's C-BIOS machines not found: the book's machines only)")
    lines.append("pass" if report["pass"] else "FAIL")
    assert all(len(line) <= 80 for line in lines), [line for line in lines if len(line) > 80]
    print("\n".join(lines))


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("rom")
    ap.add_argument("boards", nargs="*", help="IMAGE WIRING pairs")
    ap.add_argument("--json")
    ap.add_argument("--machines", default="")
    ap.add_argument("--ram", type=int, default=16)
    a = ap.parse_args(argv)
    assert len(a.boards) % 2 == 0 and all(w in pack56.WIRINGS for w in a.boards[1::2])
    boards = list(zip(a.boards[0::2], a.boards[1::2]))
    report = release(a.rom, boards, [m for m in a.machines.split(",") if m], a.ram)
    if a.json:
        Path(a.json).write_text(json.dumps(report, indent=1) + "\n")
    show(report)
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
