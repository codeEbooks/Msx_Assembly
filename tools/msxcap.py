#!/usr/bin/env python3
"""msxcap.py -- the capture of the MSX Assembly book.

openMSX runs a cartridge on one of the book's machines, inside an Xvfb display
that nobody sees, and records a FILM of every frame from the moment the
cartridge starts: `record start -videoonly` writes a ZMBV video (lossless,
320 x 240, one pixel per MSX pixel, one row per line), and ffmpeg turns it into
one PNG per frame. The film is the source of every figure in the book.

Why a film and not `screenshot`: a screenshot is the last frame the renderer
*presented*. At 100% speed that is every frame; above 100% openMSX skips
frames to keep up, and a screenshot can show a frame several frames old
(measured on day 1: at 200% the counter repeats or jumps 34 times in 300
frames). The recorder gets every frame at any speed (300 out of 300 at 2000%).

Frame numbers count from the cartridge, not from power-on. A breakpoint on the
cartridge's INIT address (read from its header) starts the film: FILM FRAME 0
is the frame during which INIT was called, film frame k is the k-th frame
after it. C-BIOS shows its logo for about 2.7 s before it starts a cartridge,
so a time in seconds would mean nothing.

The PNGs are written from their pixels only (no metadata), so two captures of
the same frame are the same file.

Environment:
  MSXCAP_OPENMSX   the openMSX binary (default: openmsx)
  MSXCAP_FFMPEG    the ffmpeg binary (default: ffmpeg)
  MSXCAP_CBIOS     the folder with the C-BIOS ROMs (default: /usr/share/cbios)
  MSXCAP_MACHINES  the folder with the book's machines (default: ../machines)
  MSXCAP_KEEP=1    keep the temporary HOME, the film and the openMSX log
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
OPENMSX = os.environ.get("MSXCAP_OPENMSX", "openmsx")
FFMPEG = os.environ.get("MSXCAP_FFMPEG", "ffmpeg")
CBIOS = Path(os.environ.get("MSXCAP_CBIOS", "/usr/share/cbios"))
MACHINES = Path(os.environ.get("MSXCAP_MACHINES", HERE.parent / "machines"))
DEFAULT_MACHINE = "MSXBOOK_EU16"
DEFAULT_SPEED = 2000


def rom_init(rom):
    """The INIT address from a cartridge header ("AB", INIT)."""
    head = Path(rom).read_bytes()[:4]
    if head[:2] != b"AB":
        raise ValueError(f"{rom}: no cartridge header (\"AB\")")
    return head[2] | head[3] << 8


def make_home():
    """A throw-away HOME with the C-BIOS ROMs and the book's machines in it."""
    home = Path(tempfile.mkdtemp(prefix="msxcap_"))
    share = home / ".openMSX" / "share"
    (share / "systemroms").mkdir(parents=True)
    (share / "machines").mkdir(parents=True)
    for rom in CBIOS.glob("*.rom"):
        shutil.copy(rom, share / "systemroms" / rom.name)
    for xml in MACHINES.glob("*.xml"):
        shutil.copy(xml, share / "machines" / xml.name)
    return home


def start_xvfb():
    """Start Xvfb on a free display; return (process, ':N')."""
    r, w = os.pipe()
    proc = subprocess.Popen(
        ["Xvfb", "-displayfd", str(w), "-screen", "0", "1024x768x24", "-nolisten", "tcp"],
        pass_fds=(w,), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    os.close(w)
    num = b""
    while not num.endswith(b"\n"):
        ch = os.read(r, 1)
        if not ch:
            raise RuntimeError("Xvfb did not start")
        num += ch
    os.close(r)
    return proc, ":" + num.decode().strip()


def clean_png(src, dst):
    """Rewrite a PNG from its pixels only."""
    Image.open(src).convert("RGB").save(dst)


def run_openmsx(rom, machine, script, home, timeout, extra_args=()):
    xvfb, display = start_xvfb()
    env = dict(os.environ, HOME=str(home), DISPLAY=display, SDL_AUDIODRIVER="dummy")
    try:
        # machine None: openMSX's own default machine, as a double-click gets
        subprocess.run([OPENMSX, *(["-machine", machine] if machine else []), "-carta", str(rom),
                        "-script", str(script), *extra_args],
                       env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=timeout, check=False)
    finally:
        xvfb.terminate()
        xvfb.wait()


def tcl_session(log, init, last, events, speed, setup, on_start, on_stop):
    """The Tcl that starts at INIT, runs events frame by frame and stops after `last`."""
    ev = "\n".join(f"dict set ::events {n} {{{cmd}}}" for n, cmd in sorted(events.items()))
    return f"""
set ::log [open {{{log}}} w]
proc L {{s}} {{ puts $::log $s; flush $::log }}
{setup}
set speed {speed}
set ::events [dict create]
{ev}
set ::last {last}
proc tick {{}} {{
    set n [expr {{[machine_info VDP_frame_count] - $::f0}}]
    if {{[dict exists $::events $n]}} {{ eval [dict get $::events $n]; L "event $n" }}
    if {{$n > $::last}} {{ {on_stop}; L "done"; exit }}
    after frame tick
}}
debug set_bp {init} {{}} {{
    if {{![info exists ::f0]}} {{
        set ::f0 [machine_info VDP_frame_count]
        L "f0 $::f0 time [machine_info time]"
        {on_start}
        if {{[dict exists $::events 0]}} {{ eval [dict get $::events 0]; L "event 0" }}
        after frame tick
    }}
}}
after time 3600 {{ L "timeout"; exit }}
"""


def capture(rom, frames, outdir, prefix="f", machine=DEFAULT_MACHINE, speed=DEFAULT_SPEED,
            events=None, tcl_setup="", timeout=600, extra_args=()):
    """Run `rom`, film it from INIT, and keep the film frames in `frames`.

    events: {n: "tcl"} run when frame n begins (for example keymatrixdown 8 0x01).
    Returns {frame: path}.
    """
    rom = Path(rom).resolve()
    outdir = Path(outdir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    frames = sorted(set(int(f) for f in frames))
    events = {int(k): v for k, v in (events or {}).items()}
    last = max(frames + list(events) + [0]) + 2
    home = make_home()
    log, film = home / "msxcap.log", home / "film.avi"
    script = home / "cap.tcl"
    script.write_text(tcl_session(log, rom_init(rom), last, events, speed, tcl_setup,
                                  f"record start -videoonly {{{film}}}", "record stop"))
    run_openmsx(rom, machine, script, home, timeout, extra_args)
    lines = log.read_text().splitlines() if log.exists() else []
    if "done" not in lines:
        raise RuntimeError(f"capture of {rom.name} did not finish: {lines[-3:]} (HOME {home})")
    pngs = home / "png"
    pngs.mkdir()
    subprocess.run([FFMPEG, "-v", "error", "-i", str(film), "-start_number", "0",
                    str(pngs / "%05d.png")], check=True)
    count = len(list(pngs.glob("*.png")))
    result = {}
    for n in frames:
        src = pngs / f"{n:05d}.png"
        if not src.exists():
            raise RuntimeError(f"frame {n} missing: the film has {count} frames (HOME {home})")
        dst = outdir / f"{prefix}{n:04d}.png"
        clean_png(src, dst)
        result[n] = dst
    if os.environ.get("MSXCAP_KEEP") != "1":
        shutil.rmtree(home, ignore_errors=True)
    return result


def record_audio(rom, frames, wav, machine=DEFAULT_MACHINE, speed=DEFAULT_SPEED,
                 events=None, tcl_setup="", timeout=600):
    """Record the sound from INIT for `frames` frames into `wav`."""
    rom = Path(rom).resolve()
    wav = Path(wav).resolve()
    home = make_home()
    log, tmpwav = home / "msxcap.log", home / "sound.wav"
    script = home / "cap.tcl"
    script.write_text(tcl_session(log, rom_init(rom), int(frames), events or {}, speed, tcl_setup,
                                  f"record start -audioonly -mono {{{tmpwav}}}", "record stop"))
    run_openmsx(rom, machine, script, home, timeout)
    lines = log.read_text().splitlines() if log.exists() else []
    if "done" not in lines or not tmpwav.exists():
        raise RuntimeError(f"recording of {rom.name} did not finish: {lines[-3:]} (HOME {home})")
    shutil.copy(tmpwav, wav)
    if os.environ.get("MSXCAP_KEEP") != "1":
        shutil.rmtree(home, ignore_errors=True)
    return wav


def run_tcl(rom, frames, tcl_at_init, machine=DEFAULT_MACHINE, speed=DEFAULT_SPEED,
            events=None, tcl_setup="", timeout=600, extra_args=()):
    """Run `rom` for `frames` frames after INIT with no film; return the log lines.

    tcl_at_init runs once at INIT (set breakpoints and watchpoints there; they
    can write to the log with L). extra_args go to openMSX after the rest
    (chapter 48: -romtype).
    """
    rom = Path(rom).resolve()
    home = make_home()
    log = home / "msxcap.log"
    script = home / "cap.tcl"
    script.write_text(tcl_session(log, rom_init(rom), int(frames), events or {}, speed, tcl_setup,
                                  tcl_at_init, "set ::stopped 1"))
    run_openmsx(rom, machine, script, home, timeout, extra_args)
    lines = log.read_text().splitlines() if log.exists() else []
    if "done" not in lines:
        raise RuntimeError(f"run of {rom.name} did not finish: {lines[-3:]} (HOME {home})")
    if os.environ.get("MSXCAP_KEEP") != "1":
        shutil.rmtree(home, ignore_errors=True)
    return lines


def film_power(rom, frames, outdir, prefix="p", machine=DEFAULT_MACHINE, speed=DEFAULT_SPEED,
               timeout=600):
    """Film from power-on, not from INIT. Frame k is the frame during which
    openMSX's VDP_frame_count is k: frame 0 is the one the machine is switched
    on in, and the debugger's frame numbers are the same numbers (chapter 5
    checks it: the frame in which INIT changes the border shows the change
    halfway down). The film starts at the first frame openMSX can record,
    frame 1. Returns ({frame: path}, the frame in which the cartridge's INIT
    was called, the log)."""
    rom = Path(rom).resolve()
    outdir = Path(outdir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    frames = sorted(set(int(f) for f in frames))
    home = make_home()
    log, film = home / "msxcap.log", home / "film.avi"
    script = home / "power.tcl"
    try:            # a cartridge without "AB" has no INIT: nothing to watch for
        watch_init = (f"debug set_bp {rom_init(rom)} {{}} {{\n"
                      f"    if {{![info exists ::init]}} {{ set ::init 1; "
                      f"L \"init [machine_info VDP_frame_count]\" }}\n}}")
    except ValueError:
        watch_init = ""
    script.write_text(f"""
set ::log [open {{{log}}} w]
proc L {{s}} {{ puts $::log $s; flush $::log }}
set speed {speed}
# openMSX 20 and later cannot record before its renderer is up, so the
# recording starts at a frame boundary, the first one at which it can: then
# the film's first frame is the frame that follows, in every version
proc try_record {{}} {{
    if {{[catch {{record start -videoonly {{{film}}}}}]}} {{ after frame try_record; return }}
    L "start [machine_info VDP_frame_count] time [machine_info time]"
}}
after frame try_record
{watch_init}
proc tick {{}} {{
    if {{[machine_info VDP_frame_count] > {max(frames) + 2}}} {{ record stop; L "done"; exit }}
    after frame tick
}}
after frame tick
after time 3600 {{ L "timeout"; exit }}
""")
    run_openmsx(rom, machine, script, home, timeout)
    lines = log.read_text().splitlines() if log.exists() else []
    if "done" not in lines:
        raise RuntimeError(f"film of {rom.name} did not finish: {lines[-3:]} (HOME {home})")
    pngs = home / "png"
    pngs.mkdir()
    subprocess.run([FFMPEG, "-v", "error", "-i", str(film), "-start_number", "0",
                    str(pngs / "%05d.png")], check=True)
    # film frame 0 is the frame that began at the boundary where the recording
    # started: the frame whose count the log line gives
    first = int(next(l for l in lines if l.startswith("start ")).split()[1])
    result = {}
    for n in frames:
        src = pngs / f"{n - first:05d}.png"
        if n < first or not src.exists():
            raise RuntimeError(f"frame {n} missing: the film starts at frame {first} (HOME {home})")
        dst = outdir / f"{prefix}{n:04d}.png"
        clean_png(src, dst)
        result[n] = dst
    init = next((int(l.split()[1]) for l in lines if l.startswith("init ")), None)
    if os.environ.get("MSXCAP_KEEP") != "1":
        shutil.rmtree(home, ignore_errors=True)
    return result, init, lines


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("rom")
    ap.add_argument("frames", help="comma-separated film frame numbers, or a-b")
    ap.add_argument("--out", default="captures")
    ap.add_argument("--prefix", default=None)
    ap.add_argument("--machine", default=DEFAULT_MACHINE)
    ap.add_argument("--speed", type=int, default=DEFAULT_SPEED)
    a = ap.parse_args(argv)
    frames = []
    for part in a.frames.split(","):
        if "-" in part:
            lo, hi = part.split("-")
            frames += range(int(lo), int(hi) + 1)
        else:
            frames.append(int(part))
    prefix = a.prefix or Path(a.rom).stem + "_f"
    for n, p in capture(a.rom, frames, a.out, prefix, a.machine, a.speed).items():
        print(n, p)


if __name__ == "__main__":
    main(sys.argv[1:])
