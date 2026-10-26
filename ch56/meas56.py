#!/usr/bin/env python3
"""meas56.py -- releasing the two games, measured.

    python3 gen56.py && ./build.sh && python3 meas56.py && python3 label56.py
                                       python3 meas56.py release photos   only these

  files     the release cartridges against chapter 44's and chapter 54's
            game.rom, byte for byte; the EPROM images against their cartridges;
            the texts' SHA-256; LICENCE
  release   release.py on the two cartridges, with their EPROM images on the
            boards they are for: its report, and its printout in
            report_grin_alley.txt and report_lantern_keep.txt; and, WHERE IT
            BREAKS, LANTERN KEEP's two images each on the other board, in
            report_wrong.txt
  guess     lantern_keep_a14.bin, the image for the other board, given to
            openMSX as a cartridge file: with no -romtype, its pictures
            against lantern_keep.rom's, what the processor reads at $4000
            and $8000, and what the cartridge's slot holds in its four
            pages; with -romtype page12, the board's own mapping: what the
            processor reads there from lantern_keep.rom; and, from the
            image, the frames at which INIT and the address $0000 were
            reached, and the bytes INIT runs
  photos    the frames the labels and figure 56.3 are made of, each held
            against vdpscreen.py's picture of the VRAM the debugger read at
            the start of that frame
  answers   the workshop, tried (for Appendix I)
  openmsx   release, guess, photos and answers again with every other build
"""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "tools"))
import meas        # noqa: E402
import msxcap      # noqa: E402
import versions    # noqa: E402
sys.path.insert(0, str(HERE))
for mod in ("vdpscreen",):
    sys.modules.pop(mod, None)
import vdpscreen   # noqa: E402
import gen56       # noqa: E402
import pack56      # noqa: E402
import release     # noqa: E402
import label56     # noqa: E402

assert Path(vdpscreen.__file__).parent == HERE

CAPS = HERE / "captures"
OUT_JSON = HERE / "meas56.json"
EU, JP, E8 = "MSXBOOK_EU16", "MSXBOOK_JP16", "MSXBOOK_EU8"
K16 = 0x4000
PALETTE = [tuple(c) for c in json.loads((REPO / "ch01" / "meas01.json").read_text())["palette"]["rgb"]]
CODE = {rgb: n for n, rgb in enumerate(PALETTE) if n}
GRIN, KEEP = (HERE / f"{n}.rom" for n in gen56.GAMES)
A14, X2 = HERE / "lantern_keep_a14.bin", HERE / "grin_alley_x2.bin"
BOARDS = {"grin_alley": [(X2, "a15"), (X2, "a14")],
          "lantern_keep": [(KEEP, "a15"), (A14, "a14")]}
WRONG = [(A14, "a15"), (KEEP, "a14")]          # each image on the other board
TITLE_AFTER = {"grin_alley": 43, "lantern_keep": 28}     # frames after INIT: chapters 44 and 54's
WORDS_FRAME = 200               # label.rom's page, long finished

POWER_TCL = r"""
set ::log [open {%LOG%} w]
proc L {s} { puts $::log $s; flush $::log }
set speed 2000
%BPS%
proc tick {} {
    set f [machine_info VDP_frame_count]
    if {[lsearch -exact {%READ%} $f] >= 0} {
        binary scan [debug read_block VRAM 0 0x4000] H* h
        set r {}
        for {set i 0} {$i < 8} {incr i} { lappend r [debug read {VDP regs} $i] }
        L "read $f $h [join $r ,]"
        foreach a {%MEM%} { binary scan [debug read_block memory $a 16] H* m; L "mem $f $a $m" }
        foreach a {%SLOT%} { binary scan [debug read_block {slotted memory} [expr {%BASE% + $a}] 16] H* m; L "slot $f $a $m" }
    }
    if {$f >= %LAST%} { L "done"; exit }
    after frame tick
}
after frame tick
"""


CART_SLOT = 1                   # the book's machines take the cartridge in slot 1, not expanded


def power(rom, read=(), last=None, bps=None, mem=(), extra=(), machine=EU, slot=()):
    """ROM run from power-on: at the start of each frame in READ, the VRAM, the
    VDP's registers, 16 bytes at each address in MEM as the processor reads
    them and at each address in SLOT of the cartridge's slot, whatever page
    the processor has selected; the frames at which the breakpoints BPS
    {address: tag} were reached"""
    home = msxcap.make_home()
    log, script = home / "power.log", home / "power.tcl"
    last = last if last is not None else max(read) + 1
    bp = "".join(f'debug set_bp {a} {{}} {{ L "bp {t} [machine_info VDP_frame_count]" }}\n'
                 for a, t in (bps or {}).items())
    script.write_text(POWER_TCL.replace("%LOG%", str(log)).replace("%BPS%", bp)
                      .replace("%READ%", " ".join(str(f) for f in read))
                      .replace("%MEM%", " ".join(str(a) for a in mem)).replace("%LAST%", str(last))
                      .replace("%SLOT%", " ".join(str(a) for a in slot))
                      .replace("%BASE%", str(0x10000 * 4 * CART_SLOT)))
    msxcap.run_openmsx(Path(rom).resolve(), machine, script, home, 1800, list(extra))
    lines = log.read_text().splitlines()
    shutil.rmtree(home, ignore_errors=True)
    assert lines[-1] == "done", (rom, lines[-3:])
    out = {"read": {}, "mem": {}, "bp": {}, "slot": {}}
    for line in lines:
        w = line.split()
        if w[0] == "read":
            out["read"][int(w[1])] = (bytes.fromhex(w[2]), [int(v) for v in w[3].split(",")])
        elif w[0] == "mem":
            out["mem"][(int(w[1]), int(w[2]))] = bytes.fromhex(w[3])
        elif w[0] == "slot":
            out["slot"][(int(w[1]), int(w[2]))] = bytes.fromhex(w[3])
        elif w[0] == "bp":
            out["bp"].setdefault(w[1], []).append(int(w[2]))
    return out


# ---------------------------------------------------------------- the files
def files():
    out = {}
    for name, ch in (("grin_alley", 44), ("lantern_keep", 54)):
        rom = (HERE / f"{name}.rom").read_bytes()
        book = (REPO / f"ch{ch}" / "game.rom").read_bytes()
        assert rom == book, name
        f = release.check_file(HERE / f"{name}.rom")
        assert f["pass"], f
        text = (HERE / f"{name}.txt").read_text()
        assert f["sha256"] in text and f"{len(rom):,} bytes" in text
        out[name] = {"size": len(rom), "sha256": f["sha256"], "init": f["init"], "book": f"ch{ch}/game.rom",
                     "text_lines": len(text.splitlines())}
    grin, keep = GRIN.read_bytes(), KEEP.read_bytes()
    assert X2.read_bytes() == grin + grin
    assert A14.read_bytes() == keep[K16:] + keep[:K16]
    for w in pack56.WIRINGS:
        assert pack56.cpu_view(X2.read_bytes(), w) == grin + grin
    assert pack56.cpu_view(A14.read_bytes(), "a14") == keep and pack56.cpu_view(keep, "a15") == keep
    assert pack56.cpu_view(A14.read_bytes(), "a15") == A14.read_bytes()
    lic = (REPO / "LICENCE").read_text()
    # the MIT licence, in the two authors' name (the publisher's until the
    # repository was made public, 26 October 2026)
    assert lic.startswith("MIT License") and \
        "Copyright (c) 2026 Aravind J. Deshmukh and Henry Radclyffe\n" in lic
    out["images"] = {p.name: len(p.read_bytes()) for p in (X2, A14)}
    out["keep_at_4010"] = keep[K16 + 0x10:K16 + 0x18].hex()
    out["licence_lines"] = len(lic.splitlines())
    print("files", out, flush=True)
    return out


# ---------------------------------------------------------------- release.py
def release_sec():
    out = {}
    for name, boards in BOARDS.items():
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rep = release.release(HERE / f"{name}.rom", boards)
            release.show(rep)
        (HERE / f"report_{name}.txt").write_text(buf.getvalue())
        ms = rep["machines"]
        assert all(v["pass"] for v in ms.values()) and rep["file"]["pass"], name
        assert len(ms) == 23 and list(rep["skipped"]) == [E8] and rep["stock_machines"] == 12
        out[name] = rep
        print("release", name, rep["pass"], {m: v["shift"] for m, v in ms.items() if v["shift"]},
              [(b["image"], b["wiring"], b["pass"], b["inits"]) for b in rep["boards"]], flush=True)
    assert out["grin_alley"]["pass"] and out["lantern_keep"]["pass"]
    # WHERE IT BREAKS: each of LANTERN KEEP's images on the other board
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rep = release.release(KEEP, WRONG, [EU])
        release.show(rep)
    (HERE / "report_wrong.txt").write_text(buf.getvalue())
    assert not rep["pass"] and not any(b["pass"] for b in rep["boards"])
    out["wrong"] = rep
    print("release wrong", [(b["image"], b["wiring"], b["inits"], b["different"]) for b in rep["boards"]],
          flush=True)
    return out


# ---------------------------------------------------------------- what openMSX guesses
def guess():
    keep = KEEP.read_bytes()
    init = release.check_file(KEEP)["init"]
    out = {}
    ref = release.film(KEEP, EU, init)
    refa = release.against(ref, None)
    ok = release.against(release.film(A14, EU, init), (ref[0], ref[1]))
    out["guessed"] = ok
    assert ok["pass"] and ok["shift"] == 0 and ok["init"] == refa["init"], ok
    r = power(A14, read=[refa["init"] + 100], mem=[0x4000, 0x8000],
              slot=[0x0000, 0x4000, 0x8000, 0xC000])
    f = refa["init"] + 100
    at4, at8 = r["mem"][(f, 0x4000)], r["mem"][(f, 0x8000)]
    assert at4 == keep[:16] and at8 == keep[K16:K16 + 16]
    # the cartridge's slot, every page: the file from $0000, and again from $8000
    a14 = A14.read_bytes()
    sl = {a: r["slot"][(f, a)] for a in (0x0000, 0x4000, 0x8000, 0xC000)}
    assert sl[0x0000] == sl[0x8000] == a14[:16] and sl[0x4000] == sl[0xC000] == a14[K16:K16 + 16]
    out["slot"] = {f"{a:04X}": v.hex() for a, v in sl.items()}
    out["reads"] = {"4000": at4.hex(), "8000": at8.hex(), "file_4000": A14.read_bytes()[K16:K16 + 16].hex(),
                    "file_0000": A14.read_bytes()[:16].hex()}
    # the board's own mapping, page12: lantern_keep.rom read from $4000 in its order
    r = power(KEEP, read=[f], mem=[0x4000, 0x8000], extra=["-romtype", "page12"])
    assert r["mem"][(f, 0x4000)] == keep[:16] and r["mem"][(f, 0x8000)] == keep[K16:K16 + 16]
    out["page12_keep"] = {"4000": r["mem"][(f, 0x4000)].hex(), "8000": r["mem"][(f, 0x8000)].hex()}
    r = power(A14, read=[], last=1000, bps={init: "init", 0: "reset"}, extra=["-romtype", "page12"])
    inits, resets = r["bp"].get("init", []), r["bp"].get("reset", [])
    gaps = sorted({b - a for a, b in zip(inits, inits[1:])})
    assert len(gaps) == 1 and inits[0] == refa["init"], (inits, resets)
    # each INIT is followed by a start from $0000, in the same frame or the next
    after = [min((x for x in resets if x >= i), default=None) for i in inits]
    out["page12"] = {"inits": inits, "period": gaps[0], "resets": resets, "reset_after_init": after,
                     "runs": A14.read_bytes()[0x10:0x18].hex()}
    assert pack56.cpu_view(A14.read_bytes(), "a15")[0x10:0x18] == keep[K16 + 0x10:K16 + 0x18]
    print("guess", out, flush=True)
    return out


# ---------------------------------------------------------------- the photographs
def codes(png):
    im = Image.open(png).convert("RGB")
    px = im.load()
    return [[CODE.get(px[x, y]) for x in range(im.width)] for y in range(im.height)]


def picture_of(vram, regs):
    """vdpscreen.py's picture, in the capture's drawn columns: the paper, and
    the border round it"""
    paper = vdpscreen.draw(vram, regs)
    border = regs[7] & 15
    out = []
    for y in range(meas.CAPTURE_H):
        row = [None] * meas.CAPTURE_W
        for x in range(meas.DRAWN[0], meas.DRAWN[1] + 1):
            px, py = x - meas.PAPER_X0, y - meas.PAPER_Y0
            row[x] = (paper[py][px] or border) if 0 <= px < 256 and 0 <= py < 192 else border
        out.append(row)
    return out


def shoot(rom, frame, extra=()):
    """the frame FRAME from power-on, filmed with openMSX's arguments EXTRA"""
    orig = msxcap.run_openmsx

    def run(rom_, machine, script, home, timeout, extra_args=()):
        return orig(rom_, machine, script, home, timeout, list(extra_args) + list(extra))
    msxcap.run_openmsx = run
    try:
        tmp = Path(tempfile.mkdtemp(prefix="ph56_"))
        res, _, _ = msxcap.film_power(rom, [frame], tmp, "p", timeout=900)
    finally:
        msxcap.run_openmsx = orig
    return res[frame], tmp


def photo(tag, rom, frame, extra=()):
    """FRAME of ROM photographed and held against the model of the VRAM the
    debugger read at the start of that frame: what the VDP drew in it, when
    the program writes to the VRAM only between two frames' pictures. Whether
    the VRAM was the same at the start of the frame after is recorded"""
    r = power(rom, read=[frame, frame + 1], extra=extra)
    vram, regs = r["read"][frame]
    still = r["read"][frame + 1][0] == vram and r["read"][frame + 1][1] == regs
    png, tmp = shoot(rom, frame, extra)
    got, want = codes(png), picture_of(vram, regs)
    bad = sum(1 for y in range(meas.CAPTURE_H) for x in range(meas.DRAWN[0], meas.DRAWN[1] + 1)
              if got[y][x] != want[y][x])
    assert bad == 0, (tag, bad, still)
    CAPS.mkdir(exist_ok=True)
    shutil.copy(png, CAPS / f"{tag}.png")
    shutil.rmtree(tmp)
    names = vram[0x1800:0x1B00] if not regs[1] & 0x10 else vram[0x0000:0x03C0]
    return {"frame": frame, "different": bad, "still": still, "mode": vdpscreen.mode(regs),
            "regs": regs, "names": names.hex()}


def photos():
    out = {}
    init = {n: release.against(release.film(HERE / f"{n}.rom", EU, release.check_file(HERE / f"{n}.rom")["init"]),
                               None)["init"] for n in gen56.GAMES}
    out["label_words"] = photo("label_words", HERE / "label.rom", WORDS_FRAME)
    for n in gen56.GAMES:
        out[f"title_{n}"] = photo(f"title_{n}", HERE / f"{n}.rom", init[n] + TITLE_AFTER[n])
    # figure 56.3: the image for the A14 board, given to openMSX as a cartridge,
    # guessed, and on the A15 board: C-BIOS's own page, after it found the header
    out["wrong_guessed"] = photo("wrong_guessed", A14, init["lantern_keep"] + TITLE_AFTER["lantern_keep"])
    g = json.loads(OUT_JSON.read_text())["guess"]["page12"] if OUT_JSON.exists() else guess()["page12"]
    out["wrong_board"] = photo("wrong_board", A14, g["inits"][0] + 2, extra=["-romtype", "page12"])
    text = bytes.fromhex(out["wrong_board"]["names"]).decode("latin-1")
    assert "Init ROM in slot: 1" in text, text
    out["init"] = init
    print("photos", {k: v["different"] for k, v in out.items() if isinstance(v, dict) and "different" in v},
          flush=True)
    return out


# ---------------------------------------------------------------- the workshop
def answers():
    out = {}
    keep, grin = KEEP.read_bytes(), GRIN.read_bytes()
    # 1. LANTERN KEEP with --ram 8: MSXBOOK_EU8 too
    rep = release.release(KEEP, (), [E8], ram=8)
    out["q1"] = {m: {k: v[k] for k in ("pass", "different", "inits", "shift")} for m, v in rep["machines"].items()}
    # 2. GRIN ALLEY once in a 27C256, the other half $FF, on each board
    tmp = Path(tempfile.mkdtemp(prefix="ws56_"))
    once = tmp / "grin_once.bin"
    once.write_bytes(grin + b"\xff" * K16)
    rep = release.release(GRIN, [(once, "a15"), (once, "a14")], [EU])
    out["q2"] = [{k: b.get(k) for k in ("wiring", "pass", "inits", "different")} for b in rep["boards"]]
    # 3. one byte of LANTERN KEEP's padding changed
    pad = max(i for i in range(len(keep)) if keep[i] == 0xFF and all(b == 0xFF for b in keep[i - 15:i + 1]))
    changed = bytearray(keep)
    changed[pad] = 0x00
    mod = tmp / "changed.rom"
    mod.write_bytes(bytes(changed))
    rep = release.release(mod, (), [])
    out["q3"] = {"address": 0x4000 + pad, "pass": rep["pass"], "sha256": rep["file"]["sha256"],
                 "released": release.check_file(KEEP)["sha256"]}
    shutil.rmtree(tmp)
    # 4. the label: a pixel's size, and the title five times enlarged
    out["q4"] = {"pixel_mm": round(label56.TITLE_X * 25.4 / label56.DPI, 3),
                 "x5_dots": 192 * 5, "x5_mm": round(192 * 5 * 25.4 / label56.DPI, 2),
                 "room_dots": label56.FRONT - 2 * label56.MARGIN,
                 "room_mm": round((label56.FRONT - 2 * label56.MARGIN) * 25.4 / label56.DPI, 2)}
    print("answers", out, flush=True)
    return out


# ---------------------------------------------------------------- openMSX's builds
def openmsx():
    if not versions.builds():
        return {"skipped": "OPENMSX_BUILDS not set"}
    out = {}
    for part in OPENMSX_SECTIONS:
        for label, r in versions.every_build(["ch56"], part).items():
            o = out.setdefault(label, {"values": 0, "same_values": 0, "captures": 0,
                                       "same_captures": 0, "same_in_drawn": 0, "failed": [],
                                       "different": []})
            for k in ("values", "same_values", "failed", "different"):
                o[k] += r[k]
            for k in ("captures", "same_captures", "same_in_drawn"):
                o[k] = max(o[k], r[k])
            o["version"], o["sha256"] = r["version"], r["sha256"]
    return out


OPENMSX_SECTIONS = [["release", "guess", "photos", "answers"]]
SECTIONS = {"files": files, "release": release_sec, "guess": guess, "photos": photos,
            "answers": answers, "openmsx": openmsx}


def main(names=()):
    m = json.loads(OUT_JSON.read_text()) if names and OUT_JSON.exists() else {}
    for name in names or SECTIONS:
        print(name, flush=True)
        m[name] = SECTIONS[name]()
        m = {k: m[k] for k in SECTIONS if k in m}
        OUT_JSON.write_text(json.dumps(m, indent=1) + "\n")
    return m


if __name__ == "__main__":
    main(sys.argv[1:])
