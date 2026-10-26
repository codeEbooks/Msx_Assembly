#!/usr/bin/env python3
"""meas04.py -- do the tools give the book's answers? Measured, not assumed.

    ./build.sh && python3 meas04.py              every section
                  python3 meas04.py edge windows only these, kept with the others
                  python3 meas04.py --missing    the sections not measured yet

What it measures, and with what:

  versions      the book's own sjasmplus, openMSX and C-BIOS
  check         check.rom on the book's two machines, on openMSX's own
                C-BIOS_MSX1_EU and on openMSX's default machine, read back
                from the screen; the default machine's BIOS font is read from
                the file openMSX's own machine definition names
  emulators     the measuring scripts of chapters 1 to 3, run again in a copy
                of the repository with other builds of openMSX; every number
                and every capture compared with the book's (tools/versions.py)
  windows       the Windows build of openMSX, under Wine, filming programs of
                chapters 2 to 4: every frame compared with the book's openMSX
  assemblers    verify.py with the Windows sjasmplus (under Wine) and with
                older releases built from their source
  case          case.asm, assembled by the Linux and the Windows sjasmplus
  speed         check.rom filmed at three speeds
  edge          edge.rom on every build of openMSX: where a change of the border
                colour shows, near the left and right edges of the picture
  downloads     the archives the chapter names: size, SHA-256, what is inside
  troubles      what the book's programs say when something is wrong
  setup         setup_linux.sh run in a scratch home folder

Programs that are not in the repository are found through environment
variables, and their SHA-256 sums are recorded in meas04.json:

  OPENMSX_BUILDS   a file of lines "label<TAB>openmsx binary<TAB>its share folder"
  OPENMSX_WIN      openmsx.exe from openmsx-21.0-windows-vc-x64-bin.zip
  SJASMPLUS_WIN    sjasmplus.exe from sjasmplus-1.24.0.win.zip
  SJASMPLUS_OLD    older sjasmplus binaries, separated by ':'
  DOWNLOADS        the folder with the downloaded archives
  WINEPREFIX       the Wine prefix to use
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "tools"))
import msxcap      # noqa: E402
import screentext  # noqa: E402
import versions as builds_of_openmsx  # noqa: E402
import gen04       # noqa: E402

CAPS = HERE / "captures"
EU, JP = "MSXBOOK_EU16", "MSXBOOK_JP16"
FRAME_T = {EU: 71364, JP: 59736}       # tools/meas.py, measured on day 1
CHECK_FRAME = 60


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    return r.returncode, (r.stdout + r.stderr)


def first_line(text):
    return next((l.strip() for l in text.splitlines() if l.strip()), "")


# ---------------------------------------------------------------- reading check.rom
def read_check(png, machine=EU, rom_file=None):
    pg = screentext.Page(png, machine, rom_file)
    v = gen04.VALUE_COL
    line = {k: pg.line(r) for k, r in gen04.ROWS.items()}
    out = {"assembler": line["asm"][v:].strip(),
           "bios_sum": line["sum"][v:v + 4],
           "b002B": line["hz"][v:v + 2], "hz": line["hz"][v + 4:].strip(),
           "b002D": line["msx"][v:v + 2], "msx": line["msx"][v + 4:].strip(),
           "ram_from": line["ram"][v:v + 4],
           "turns": int(line["turns"][v:v + 5])}
    assert line["title"].strip() == "check: what runs this cartridge", line["title"]
    return out


def default_machine_rom(openmsx_share="/usr/share/openmsx"):
    """the main BIOS file of openMSX's default machine, from its own definition"""
    xml = Path(openmsx_share) / "machines" / "C-BIOS_MSX2+.xml"
    name = re.search(r"<filename>(cbios_main[^<]+)</filename>", xml.read_text()).group(1)
    return msxcap.CBIOS / name


def check():
    out = {}
    runs = [("book_eu", EU, None), ("book_jp", JP, None), ("openmsx_msx1_eu", "C-BIOS_MSX1_EU", None),
            ("default", None, default_machine_rom())]
    for key, machine, rom_file in runs:
        png = msxcap.capture(HERE / "check.rom", [CHECK_FRAME], CAPS, f"check_{key}_f",
                             machine=machine)[CHECK_FRAME]
        r = read_check(png, machine or "default", rom_file)
        out[key] = {"machine": machine or "(none: openMSX's default)", **r}
    # the models: the version sjasmplus reports, the sum of the BIOS file,
    # the bits of $002B, and the frame of each machine in turns of the loop
    ver = first_line(run(["sjasmplus", "--version"])[1])
    for key in ("book_eu", "book_jp", "openmsx_msx1_eu", "default"):
        # the version, digits and dots; the Japanese font draws "l" and "|" alike,
        # so "sjasmplus" itself reads back as "sjasmp?us" there
        assert out[key]["assembler"].split()[-1] == ver.split(" v")[1].split()[0], out[key]
    for key, machine in (("book_eu", EU), ("book_jp", JP)):
        rom = (msxcap.CBIOS / screentext.bios_file(machine)).read_bytes()
        assert out[key]["bios_sum"] == f"{sum(rom[:0x4000]) & 0xFFFF:04X}"
        assert out[key]["b002B"] == f"{rom[0x2B]:02X}" and out[key]["b002D"] == f"{rom[0x2D]:02X}"
        t = FRAME_T[machine]
        assert abs(out[key]["turns"] * gen04.TURN_T - t) < gen04.TURN_T, (key, out[key]["turns"])
        out[key]["frame_T"] = t
    rom = default_machine_rom().read_bytes()
    assert out["default"]["bios_sum"] == f"{sum(rom[:0x4000]) & 0xFFFF:04X}"
    out["default"]["bios_file"] = default_machine_rom().name
    out["turn_T"] = gen04.TURN_T
    return out


# ---------------------------------------------------------------- other openMSX builds
def emulators():
    """the meas scripts of chapters 1 to 3, the chapters before this one, run
    again with every other build (tools/versions.py)"""
    if not builds_of_openmsx.builds():
        return {"skipped": "OPENMSX_BUILDS not set"}
    return builds_of_openmsx.every_build(["ch01", "ch02", "ch03"])


# ---------------------------------------------------------------- edge
def edge_stripes(png):
    """[first, last] column of the white on the first line of each stripe"""
    im = Image.open(png).convert("RGB")
    out, prev = [], None
    for y in range(im.height):
        xs = [x for x in range(im.width) if sum(im.getpixel((x, y))) > 600]
        if xs and prev is None:
            assert xs == list(range(xs[0], xs[-1] + 1)), (y, "a broken stripe")
            out.append([xs[0], xs[-1]])
        prev = xs or None
    return out


def edge():
    """edge.rom on the book's openMSX and on every other build: where the
    three stripes start and end"""
    builds = [("book", "openmsx", None)]
    if os.environ.get("OPENMSX_BUILDS"):
        for line in Path(os.environ["OPENMSX_BUILDS"]).read_text().splitlines():
            if line.strip() and not line.startswith("#"):
                builds.append(tuple(line.split("\t")))
    # where nops.asm's stripes start, measured by chapter 3
    x0 = json.loads((REPO / "ch03" / "meas03.json").read_text())["nops"]["frame30"][0]["x_first"]
    model = []
    for shift, n in gen04.EDGE:
        first = x0 + round(1.5 * shift)
        model.append([first, first + round((28 + 5 * n) * 1.5) - 1])
    clamped = [[0 if a < gen04.DRAWN[0] else a, gen04.LAST_X if b > gen04.DRAWN[1] else b]
               for a, b in model]
    out = {"model": model, "model_clamped": clamped, "drawn": list(gen04.DRAWN), "builds": {}}
    for label, binary, share in builds:
        old = msxcap.OPENMSX
        env_old = os.environ.get("OPENMSX_SYSTEM_DATA")
        msxcap.OPENMSX = binary
        if share:
            os.environ["OPENMSX_SYSTEM_DATA"] = share
        try:
            tag = "book" if label == "book" else label.split()[0].replace(".", "")
            got = msxcap.capture(HERE / "edge.rom", range(30, 35), CAPS, f"edge_{tag}_f")
        finally:
            msxcap.OPENMSX = old
            if share:
                if env_old is None:
                    os.environ.pop("OPENMSX_SYSTEM_DATA", None)
                else:
                    os.environ["OPENMSX_SYSTEM_DATA"] = env_old
        st = edge_stripes(got[30])
        still = all(got[n].read_bytes() == got[30].read_bytes() for n in range(31, 35))
        out["builds"][label] = {"stripes": st, "capture": got[30].name, "still_30_34": still,
                                "as_written": st == model, "as_clamped": st == clamped}
        for n in range(31, 35):
            got[n].unlink()
        if label != "book" and not label.startswith("21.0"):
            got[30].unlink()
        print(f"  edge {label}: {st}")
    assert out["builds"]["book"]["as_written"] and out["builds"]["book"]["still_30_34"], out
    return out


# ---------------------------------------------------------------- the Windows openMSX, under Wine
def win(p):
    return "Z:" + str(p).replace("/", "\\")


def wine_film(exe, rom, frames, machine=EU, events=None):
    """film with openmsx.exe under Wine, as msxcap.capture does with Linux openMSX"""
    home = msxcap.make_home()
    log, film = home / "msxcap.log", home / "film.avi"
    events = {int(k): v for k, v in (events or {}).items()}
    last = max(list(frames) + list(events)) + 2
    (home / "cap.tcl").write_text(msxcap.tcl_session(
        win(log).replace("\\", "/"), msxcap.rom_init(rom), last, events, msxcap.DEFAULT_SPEED, "",
        f"record start -videoonly {{{win(film).replace(chr(92), '/')}}}", "record stop"))
    xv, disp = msxcap.start_xvfb()
    env = dict(os.environ, DISPLAY=disp, WINEDEBUG="-all", OPENMSX_HOME=win(home / ".openMSX"),
               SDL_AUDIODRIVER="dummy")
    try:
        subprocess.run(["wine", exe, "-machine", machine, "-carta", win(rom), "-script", win(home / "cap.tcl")],
                       env=env, capture_output=True, timeout=900)
    finally:
        xv.terminate()
        xv.wait()
    pngs = home / "png"
    pngs.mkdir()
    subprocess.run([msxcap.FFMPEG, "-v", "error", "-i", str(film), "-start_number", "0",
                    str(pngs / "%05d.png")], check=True)
    out = {n: Image.open(pngs / f"{n:05d}.png").convert("RGB").tobytes() for n in frames}
    shutil.rmtree(home, ignore_errors=True)
    return out


def linux_film(rom, frames, machine=EU, events=None):
    tmp = Path(tempfile.mkdtemp(prefix="lin_"))
    got = msxcap.capture(rom, frames, tmp, "f", machine=machine, events=events)
    out = {n: Image.open(p).convert("RGB").tobytes() for n, p in got.items()}
    shutil.rmtree(tmp, ignore_errors=True)
    return out


WINDOWS_RUNS = [("ch02/count.rom", range(1, 61), EU, None),
                ("ch03/nops.rom", range(1, 61), EU, None),
                ("ch03/keys.rom", range(1, 81), EU, {50: "keymatrixdown 4 0x40"}),
                ("ch04/check.rom", range(1, 61), EU, None),
                ("ch04/check.rom", range(1, 61), JP, None)]


def windows():
    exe = os.environ.get("OPENMSX_WIN")
    if not exe:
        return {"skipped": "OPENMSX_WIN not set"}
    rc, text = run(["wine", exe, "-v"], env=dict(os.environ, WINEDEBUG="-all"))
    runs = []
    for rom, frames, machine, events in WINDOWS_RUNS:
        a = wine_film(exe, REPO / rom, list(frames), machine, events)
        b = linux_film(REPO / rom, list(frames), machine, events)
        same = sum(a[n] == b[n] for n in frames)
        runs.append({"rom": rom, "machine": machine, "frames": len(frames), "identical": same})
        print(f"  windows {rom} {machine}: {same}/{len(frames)}")
    return {"exe_sha256": sha256(exe), "runs": runs}


# ---------------------------------------------------------------- assemblers
def verify_with(sjasmplus):
    """verify.py with this sjasmplus first on the PATH"""
    d = Path(tempfile.mkdtemp(prefix="sj_"))
    try:
        (d / "sjasmplus").symlink_to(sjasmplus)
        env = dict(os.environ, PATH=f"{d}:{os.environ['PATH']}")
        rc, text = run([sys.executable, "verify.py"], cwd=REPO, env=env, timeout=3000)
        lines = text.strip().splitlines()
        return {"version_line": lines[0], "summary": lines[-1],
                "different": [l.split()[-1] for l in lines if l.strip().startswith("DIFF")]}
    finally:
        shutil.rmtree(d, ignore_errors=True)


def wine_wrapper(exe):
    d = Path(tempfile.mkdtemp(prefix="sjwin_"))
    w = d / "sjasmplus-win"
    w.write_text(f'#!/bin/sh\nWINEDEBUG=-all exec wine "{exe}" "$@"\n')
    w.chmod(0o755)
    return w


def assemblers():
    out = {"book": first_line(run(["sjasmplus", "--version"])[1])}
    exe = os.environ.get("SJASMPLUS_WIN")
    if exe:
        xv, disp = msxcap.start_xvfb()
        os.environ["DISPLAY"] = disp
        try:
            w = wine_wrapper(exe)
            out["windows"] = {"version": first_line(run([str(w), "--version"])[1]),
                              "sha256": sha256(exe), **verify_with(w)}
        finally:
            xv.terminate()
            xv.wait()
    out["older"] = []
    for binary in filter(None, os.environ.get("SJASMPLUS_OLD", "").split(":")):
        r = verify_with(binary)
        r["version"] = first_line(run([binary, "--version"])[1])
        r["sha256"] = sha256(binary)
        out["older"].append(r)
    return out


def case():
    """case.asm: INCLUDE "MSX.INC" next to a file called msx.inc"""
    out = {}
    tmp = Path(tempfile.mkdtemp(prefix="case_"))
    try:
        shutil.copy(HERE / "case.asm", tmp)
        shutil.copy(HERE / "msx.inc", tmp)
        tools = {"linux": "sjasmplus"}
        if os.environ.get("SJASMPLUS_WIN"):
            tools["windows"] = str(wine_wrapper(os.environ["SJASMPLUS_WIN"]))
        xv, disp = msxcap.start_xvfb()
        try:
            for k, tool in tools.items():
                rc, text = run([tool, "--nologo", "case.asm"], cwd=tmp,
                               env=dict(os.environ, DISPLAY=disp))
                # the time sjasmplus took changes from run to run: it is left out
                text = re.sub(r", work time: [0-9.]+ seconds", "", text.replace("\r", ""))
                kept = [l for l in text.splitlines() if "error" in l.lower() or l.startswith("Errors")]
                (HERE / f"case_{k}.txt").write_text("\n".join(kept) + "\n")
                out[k] = {"rc": rc, "lines": kept}
        finally:
            xv.terminate()
            xv.wait()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return out


# ---------------------------------------------------------------- speed
def speed():
    frames = list(range(1, CHECK_FRAME + 1))
    films = {}
    for s in (100, 400, 2000):
        tmp = Path(tempfile.mkdtemp(prefix="speed_"))
        got = msxcap.capture(HERE / "check.rom", frames, tmp, "f", speed=s)
        films[s] = [got[n].read_bytes() for n in frames]
        shutil.rmtree(tmp, ignore_errors=True)
    same = all(films[s] == films[100] for s in films)
    return {"speeds": sorted(films), "frames": len(frames), "identical": same}


# ---------------------------------------------------------------- downloads
def pe_machine(data):
    off = int.from_bytes(data[0x3C:0x40], "little")
    return {0x14C: "i386 (32-bit)", 0x8664: "x86-64 (64-bit)"}.get(
        int.from_bytes(data[off + 4:off + 6], "little"), "?")


def macho(path):
    import struct
    b = Path(path).read_bytes()
    _, cpu, _, _, ncmds, _, _, _ = struct.unpack("<8I", b[:32])
    off, minos = 32, None
    for _ in range(ncmds):
        cmd, size = struct.unpack("<2I", b[off:off + 8])
        if cmd == 0x32:                                    # LC_BUILD_VERSION
            v = struct.unpack("<I", b[off + 12:off + 16])[0]
            minos = f"{v >> 16}.{(v >> 8) & 255}"
        off += size
    return {0x0100000C: "arm64", 0x01000007: "x86-64"}.get(cpu, hex(cpu)), minos


CBIOS_NAMES = ("cbios_main_msx1_eu.rom", "cbios_main_msx1_jp.rom", "cbios_logo_msx1.rom")


def install_from(place):
    """install_machines.py, given one place to find C-BIOS in: how many ROMs it found"""
    home = Path(tempfile.mkdtemp(prefix="from_"))
    try:
        rc, text = run([sys.executable, str(REPO / "install_machines.py"), str(place)],
                       env=dict(os.environ, HOME=str(home)))
        return {"rc": rc, "found": sum(1 for l in text.splitlines() if l.endswith("  ok"))}
    finally:
        shutil.rmtree(home, ignore_errors=True)


def downloads():
    dl = os.environ.get("DOWNLOADS")
    if not dl:
        return {"skipped": "DOWNLOADS not set"}
    dl = Path(dl)
    out = {"files": {}}
    for p in sorted(dl.iterdir()):
        out["files"][p.name] = {"bytes": p.stat().st_size, "sha256": sha256(p)}
    book = {n: hashlib.sha1((msxcap.CBIOS / n).read_bytes()).hexdigest() for n in CBIOS_NAMES}
    out["cbios_book_sha1"] = book
    with zipfile.ZipFile(dl / "sjasmplus-1.24.0.win.zip") as z:
        name = next(n for n in z.namelist() if n.endswith("sjasmplus.exe"))
        out["sjasmplus_exe"] = pe_machine(z.read(name))
    with zipfile.ZipFile(dl / "openmsx-21.0-windows-vc-x64-bin.zip") as z:
        out["openmsx_exe"] = pe_machine(z.read("openmsx.exe"))
        out["windows_zip_cbios_same"] = all(
            hashlib.sha1(z.read(f"share/machines/{n}")).hexdigest() == book[n] for n in CBIOS_NAMES)
    with zipfile.ZipFile(dl / "openmsx-21.0-linux-x86_64-bin.zip") as z:
        out["linux_zip_cbios_same"] = all(
            hashlib.sha1(z.read(f"share/machines/{n}")).hexdigest() == book[n] for n in CBIOS_NAMES)
    with zipfile.ZipFile(dl / "cbios-0.29a.zip") as z:
        out["cbios_zip_same"] = all(
            hashlib.sha1(z.read(f"cbios-0.29a/roms/{n}")).hexdigest() == book[n] for n in CBIOS_NAMES)
    # install_machines.py, pointed at each place a reader has C-BIOS in
    out["install_from"] = {"cbios-0.29a.zip": install_from(dl / "cbios-0.29a.zip")}
    tmp = Path(tempfile.mkdtemp(prefix="winzip_"))
    try:
        with zipfile.ZipFile(dl / "openmsx-21.0-windows-vc-x64-bin.zip") as z:
            z.extractall(tmp)
        out["install_from"]["share\\machines of the Windows zip"] = install_from(tmp / "share" / "machines")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    out["mac"] = {}
    for arch in ("aarch64", "x86_64"):
        tmp = Path(tempfile.mkdtemp(prefix="dmg_"))
        try:
            subprocess.run(["7z", "x", "-y", str(dl / f"openmsx-21.0-mac-{arch}-bin.dmg")], cwd=tmp,
                           capture_output=True)
            app = next(tmp.rglob("openMSX.app"))
            cpu, minos = macho(app / "Contents/MacOS/openmsx")
            share = app / "Contents/Resources/share/machines"
            same = all(hashlib.sha1((share / n).read_bytes()).hexdigest() == book[n] for n in CBIOS_NAMES)
            user = b"~/.openMSX" in (app / "Contents/MacOS/openmsx").read_bytes()
            out["install_from"][f"openMSX.app, {arch}"] = install_from(app / "Contents/Resources/share")
            out["mac"][arch] = {"cpu": cpu, "minimum_macos": minos, "cbios_same": same,
                                "user_folder_string": "~/.openMSX" if user else None}
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    return out


# ---------------------------------------------------------------- troubles
def openmsx_once(args, home_setup=None, env_extra=None, binary="openmsx"):
    """start openMSX for one second in a scratch home; its error, or the machine it ran"""
    home = Path(tempfile.mkdtemp(prefix="om_"))
    (home / ".openMSX" / "share").mkdir(parents=True)
    if home_setup:
        home_setup(home)
    out = home / "out.txt"
    (home / "t.tcl").write_text(f'after time 2 {{ set f [open {{{out}}} w]; '
                                f'puts $f [machine_info config_name]; close $f; exit }}\n')
    xv, disp = msxcap.start_xvfb()
    env = dict(os.environ, HOME=str(home), DISPLAY=disp, SDL_AUDIODRIVER="dummy", **(env_extra or {}))
    env.pop("OPENMSX_SYSTEM_DATA", None) if not (env_extra or {}).get("OPENMSX_SYSTEM_DATA") else None
    try:
        r = subprocess.run([binary, *args, "-script", str(home / "t.tcl")], env=env,
                           capture_output=True, text=True, timeout=120, cwd=home)
    finally:
        xv.terminate()
        xv.wait()
    text = (r.stdout + r.stderr).replace(str(home), "~")
    # the MIDI sequencer of a machine without sound hardware is not an error of ours
    err = next((l.strip() for l in text.splitlines() if "rror" in l and "sequencer" not in l), None)
    ran = out.read_text().strip() if out.exists() else None
    shutil.rmtree(home, ignore_errors=True)
    return {"ran": ran, "error": err}


def troubles():
    out = {}
    rc, text = run([sys.executable, "verify.py"], cwd=REPO, env=dict(os.environ, PATH="/usr/bin:/bin"))
    out["no_sjasmplus"] = first_line(text)
    # Ubuntu's openmsx package: the C-BIOS machines, with an empty user folder
    out["package_cbios_eu"] = openmsx_once(["-machine", "C-BIOS_MSX1_EU"])
    out["package_cbios_jp"] = openmsx_once(["-machine", "C-BIOS_MSX1_JP"])
    out["book_machine_not_installed"] = openmsx_once(["-machine", EU])

    def installed(home):
        subprocess.run([sys.executable, str(REPO / "install_machines.py")], env=dict(os.environ, HOME=str(home)),
                       capture_output=True, check=True)
    out["book_machine_installed"] = openmsx_once(["-machine", EU], installed)
    out["package_cbios_eu_installed"] = openmsx_once(["-machine", "C-BIOS_MSX1_EU"], installed)
    linked = sorted(p.name for p in Path("/usr/share/openmsx/systemroms").iterdir() if p.is_symlink())
    out["package_missing_links"] = sorted(set(p.name for p in Path("/usr/share/cbios").iterdir()
                                              if p.name.startswith("cbios_main")) - set(linked))
    builds = os.environ.get("OPENMSX_BUILDS")
    if builds:
        for line in Path(builds).read_text().splitlines():
            if line.startswith("21.0"):
                _, binary, share = line.split("\t")
                out["official_zip_no_system_data"] = openmsx_once([], binary=binary)
                out["official_zip_with_system_data"] = openmsx_once(
                    [], binary=binary, env_extra={"OPENMSX_SYSTEM_DATA": share})
    return out


# ---------------------------------------------------------------- setup_linux.sh, the photograph, the file
def setup():
    """setup_linux.sh in a scratch home folder; the tarball is put there first,
    as the script leaves it after its first run (this machine cannot reach the
    download)"""
    home = Path(tempfile.mkdtemp(prefix="setup_"))
    work = home / "ch04"
    shutil.copytree(REPO, home / "repo", ignore=shutil.ignore_patterns("__pycache__", "captures"))
    work = home / "repo" / "ch04"
    src = os.environ.get("SJASMPLUS_SRC")
    if src:
        shutil.copy(src, work)
    r = subprocess.run(["sh", "setup_linux.sh"], cwd=work, env=dict(os.environ, HOME=str(home)),
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=3000)
    rc, text = r.returncode, r.stdout          # in the order a terminal shows it
    lines = [l.replace(str(home), "~") for l in text.splitlines() if l.strip()]
    shutil.rmtree(home, ignore_errors=True)
    return {"rc": rc, "last_lines": lines[-6:]}


def photograph():
    shutil.rmtree(HERE / "shots", ignore_errors=True)
    rc, text = run(["sh", "photograph.sh"], cwd=HERE)
    (HERE / "photograph.txt").write_text(text.replace(str(HERE) + "/", ""))
    shot = HERE / "shots" / f"check_f{CHECK_FRAME:04d}.png"
    same = shot.read_bytes() == (CAPS / f"check_book_eu_f{CHECK_FRAME:04d}.png").read_bytes()
    shutil.rmtree(HERE / "shots", ignore_errors=True)
    return {"rc": rc, "output": text.strip().replace(str(HERE) + "/", ""), "same_as_figure": same}


def cartridge():
    data = (HERE / "check.rom").read_bytes()
    head = data[:16]
    (HERE / "header.txt").write_text(" ".join(f"{b:02X}" for b in head) + "\n")
    used = len(data.rstrip(b"\xff"))
    return {"bytes": len(data), "header": [f"{b:02X}" for b in head],
            "init": f"{head[2] | head[3] << 8:04X}", "used": used}


def listings():
    """the outputs the chapter prints: verify.py and install_machines.py, run
    as a reader runs them (the installer into a scratch home folder)"""
    rc, text = run([sys.executable, "verify.py"], cwd=REPO)
    lines = text.strip().splitlines()
    (HERE / "verify_linux.txt").write_text("\n".join(lines[:3] + ["  ..."] + lines[-2:]) + "\n")
    home = Path(tempfile.mkdtemp(prefix="inst_"))
    rc2, text2 = run([sys.executable, "../install_machines.py", "/usr/share/cbios"], cwd=HERE,
                     env=dict(os.environ, HOME=str(home)))
    (HERE / "install_linux.txt").write_text(text2.replace(str(home), "~"))
    shutil.rmtree(home, ignore_errors=True)
    return {"verify": {"rc": rc, "first": lines[0], "summary": lines[-1]},
            "install": {"rc": rc2, "lines": text2.replace(str(home), "~").strip().splitlines()}}


def default_setting():
    """openMSX's setting default_machine: set once, remembered at the next start"""
    home = Path(tempfile.mkdtemp(prefix="dm_"))
    subprocess.run([sys.executable, str(REPO / "install_machines.py")], env=dict(os.environ, HOME=str(home)),
                   capture_output=True, check=True)
    xv, disp = msxcap.start_xvfb()
    env = dict(os.environ, HOME=str(home), DISPLAY=disp, SDL_AUDIODRIVER="dummy")
    out = []
    try:
        for script in ("set default_machine MSXBOOK_EU16\nafter time 2 { L; exit }",
                       "after time 2 { L; exit }"):
            (home / "t.tcl").write_text(
                f"proc L {{}} {{ set f [open {{{home}/o.txt}} w]; puts $f [machine_info config_name]; close $f }}\n"
                + script + "\n")
            subprocess.run(["openmsx", "-script", str(home / "t.tcl")], env=env, capture_output=True,
                           timeout=120, cwd=home)
            out.append((home / "o.txt").read_text().strip())
    finally:
        xv.terminate()
        xv.wait()
        shutil.rmtree(home, ignore_errors=True)
    return {"first_start": out[0], "second_start": out[1]}


def versions():
    return {"sjasmplus": first_line(run(["sjasmplus", "--version"])[1]),
            "openmsx": first_line(run(["openmsx", "-v"])[1]),
            "cbios": run(["dpkg-query", "-W", "-f=${Version}", "cbios"])[1].strip()}


SECTIONS = {"versions": versions, "check": check, "cartridge": cartridge, "photograph": photograph,
            "speed": speed, "edge": edge, "troubles": troubles, "case": case,
            "assemblers": assemblers, "downloads": downloads, "emulators": emulators,
            "windows": windows, "setup": setup, "listings": listings,
            "default_setting": default_setting}


def main(names=()):
    """every section, or only the ones named (their results replace the old
    ones in meas04.json, the others are kept); --missing runs the sections
    meas04.json does not have yet. The file is written after every section."""
    CAPS.mkdir(exist_ok=True)
    path = HERE / "meas04.json"
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
    print(json.dumps(main(sys.argv[1:]), indent=1)[:4000])
