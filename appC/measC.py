#!/usr/bin/env python3
"""measC.py -- every port of the book's machine, and every register of the
VDP, the PSG and the PPI, written and read back on openMSX.

    python3 genC.py && ./build.sh && python3 measC.py [step ...]

    ports    ports.rom on MSXBOOK_EU16 and MSXBOOK_JP16: the three tables of
             reads, and after each OUT of the nine passes the VDP's
             registers, its address and latch, four bytes of the VRAM, the
             PSG's sixteen registers, the PPI's ports A and C (read by the
             debugger, which does not change them) and the printer port's
             strobe and data; a printer logger is plugged in before the
             second state, and what it printed is read at the end. A model
             of the port map, the table the appendix prints, must give
             every number; and the same on MSXBOOK_EU16M, the book's machine
             with each chip on eight ports, as in some makers' files
    start    what C-BIOS leaves when it calls INIT, on both machines
    vdp      vdp.rom on both machines: the VDP's registers, address, latches,
             status and four places of the VRAM at each case, and the
             interrupts counted at $0038
    vdps     vdp.rom on the book's machine with each VDP openMSX's MSX1 files
             name: the kept bits, the status, and the 4 KB mode
    psg      psg.rom on MSXBOOK_EU16, EU16AY, EU16P and JP16: the registers
             and what IN gave at each case, and the kana lamp sampled
    joy      psg.rom on both machines, the joysticks' switches held one at a
             time with xdotool: register 14 for each value of register 15
    ppi      ppi.rom on both machines, a silent tape in the player: the slots
             page by page, port C, the rows, the control port, the CAPS lamp
             and the tape's position; then again, recording the sound
    sound    sound.rom on both machines, recorded: the tone of each bit of a
             period alone, and the range of each bit of a volume alone
    keys     keys.rom on both machines: every key of rows 0 to 10 pressed
             alone, the CAPS and CODE keys twice, four pairs, and what CHGET
             gave for each; the lamps sampled
    files    openMSX's MSX1 machine files: the VDP and the PSG each names,
             and the ports each chip answers
    before   the results against the chapters that measured the same things
    openmsx  the steps again with every other build (tools/versions.py)

Writes measC.json.
"""
import json
import os
import re
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(HERE))
import msxcap      # noqa: E402
import probe       # noqa: E402
import versions    # noqa: E402
import genC        # noqa: E402

OUT_JSON = HERE / "measC.json"
STRICT = "MSXCAP_OPENMSX" not in os.environ     # the book's openMSX: every rule asserted;
                                # with another build (tools/versions.py) the rules
                                # that may change are recorded, and compared
MACHINES = {"eu": "MSXBOOK_EU16", "jp": "MSXBOOK_JP16"}
HEX = ('proc H {d a n} { binary scan [debug read_block $d $a $n] H* h; return $h }\n'
       # a debuggable's byte 0, or "-" if this openMSX has no such debuggable: 17.0
       # and 18.0 show neither the VDP's latches nor its access status
       'proc D {d} { if {[lsearch -exact [debug list] $d] < 0} {return -}; '
       'return [debug read $d 0] }\n')


# ---------------------------------------------------------------- the port map
# The table the appendix prints: who answers each port of the book's machines,
# reading and writing. Everything else reads $FF and takes nothing.
READ = {0x90: "printer status", 0x98: "VDP data", 0x99: "VDP status", 0xA2: "PSG data",
        0xA8: "PPI A", 0xA9: "PPI B", 0xAA: "PPI C", 0xAB: "PPI control"}
WRITE = {0x90: "printer strobe", 0x91: "printer data", 0x98: "VDP data", 0x99: "VDP control",
         0xA0: "PSG select", 0xA1: "PSG data", 0xA8: "PPI A", 0xAA: "PPI C",
         0xAB: "PPI control"}


def model_read(port, state, slots, status, control, dev="port"):
    """what IN gives from PORT in a state of ports.asm (genC.S1 or S2), the
    printer plugged in or not; DEV, if given, the device that answers it"""
    s = state
    dev = READ.get(port) if dev == "port" else dev
    if dev is None:
        return 0xFF
    return {"printer status": 0xFD if s is genC.S2 else 0xFF,     # bit 1, busy, 0 with one
            "VDP data": s["vram"], "VDP status": status, "PSG data": s["psg"],
            "PPI A": slots, "PPI B": 0xFE if s is genC.S2 else 0xFF,   # SPACE, row 8 bit 0
            "PPI C": s["c"], "PPI control": control}[dev]


# ---------------------------------------------------------------- ports
STATE = ('[H {physical VRAM} 0x%04X 3] [H {physical VRAM} 0x%04X 1] [H {VDP regs} 0 8] '
         '[H {VRAM pointer} 0 2] [D {VDP register latch status}] '
         '[H {PSG regs} 0 16] [debug read ioports 0xA8] [debug read ioports 0xAA] '
         '[H {Printer Port} 0 2]') % (genC.W_ADDR, genC.W_CTRL)
FIELDS = ["vram", "ctrl", "regs", "pointer", "latch", "psg", "a", "c", "printer"]


def ports_tcl(s, plog):
    out = [HEX,
           f'debug set_bp 0x{s["state2"]:04X} {{}} {{plug printerport logger; '
           f'keymatrixdown {genC.SPACE[0]} 0x{genC.SPACE[1]:02X}; L "S2"}}']
    for name in ("r1", "r3", "r2"):
        k = ["r1", "r3", "r2"].index(name)
        out.append(f'debug set_bp 0x{s[name + "done"]:04X} {{}} '
                   f'{{L "R {name} [H memory 0x{0xC000 + 256 * k:04X} 256]"}}')
    for name, *_ in genC.WRITES:
        out.append(f'debug set_bp 0x{s[name + "probe"]:04X} {{}} '
                   f'{{L "W {name} [expr {{[reg bc] & 255}}] {STATE}"}}')
    out.append(f'debug set_bp 0x{s["done"]:04X} {{}} {{L "end"; L done; exit}}')
    return "\n".join(out) + "\n"


def run_ports(machine):
    s = probe.sym(HERE / "ports.sym")
    d = Path(tempfile.mkdtemp(prefix="plog_"))
    plog = d / "printer.log"
    setup = f"set printerlogfilename {{{plog}}}\n"
    lines = msxcap.run_tcl(HERE / "ports.rom", 400, ports_tcl(s, plog), machine=machine,
                           tcl_setup=setup, timeout=1200)
    printed = plog.read_bytes() if plog.exists() else b""
    reads, writes = {}, {}
    for l in lines:
        w = l.split()
        if w[0] == "R":
            reads[w[1]] = list(bytes.fromhex(w[2]))
        elif w[0] == "W":
            name, port, rest = w[1], int(w[2]), w[3:]
            writes.setdefault(name, {})[port] = dict(zip(FIELDS, rest))
    assert "end" in lines and "S2" in lines
    return reads, writes, printed


def changed(name, before, after):
    """what a write of pass NAME did: the devices whose state is not what the
    pass's set-up left"""
    out = set()
    vram = bytes.fromhex(after["vram"])
    ctrl = bytes.fromhex(after["ctrl"])[0]
    psg_ = bytes.fromhex(after["psg"])
    p = genC.PSG_TEST
    if name == "w1" and vram[0] == 0x15:
        out.add("VDP data")
    if name == "w2" and ctrl == 0x55:
        out.add("VDP control")
    if name == "w3" and psg_[p] == 0x15:
        out.add("PSG select")
    if name == "w4" and psg_[p] == 0x15:
        out.add("PSG data")
    if name == "w5" and int(after["a"]) == 0x15:
        out.add("PPI A")
    if name == "w6" and int(after["c"]) == 0x15:
        out.add("PPI C")
    if name == "w7" and int(after["c"]) == 0xF4:
        out.add("PPI control")
    pr = bytes.fromhex(after["printer"])
    if name == "w8" and pr[1] == 0x15:
        out.add("printer data")
    if name == "w9" and pr[0] == 0:
        out.add("printer strobe")
    return out


MIRROR = "MSXBOOK_EU16M"         # the book's machine, its VDP, PSG and PPI answering 8 ports
MIRROR_IO = {"VDP": '<io base="0x98" num="8"/>', "PSG": '<io base="0xA0" num="8"/>',
             "PPI": '<io base="0xA8" num="8"/>'}


def mirror_machines():
    """a folder with the book's machines and MIRROR: MSXBOOK_EU16 with each
    chip's io lines replaced by one of 8 ports, as 21 of openMSX's MSX1 files
    have their VDP"""
    d = Path(tempfile.mkdtemp(prefix="machinesC_"))
    for x in (REPO / "machines").glob("*.xml"):
        (d / x.name).write_text(x.read_text())
    text = (REPO / "machines" / "MSXBOOK_EU16.xml").read_text()
    for dev, io in MIRROR_IO.items():
        text = re.sub(rf'(<{dev} id="[^"]*">)(.*?)(</{dev}>)',
                      lambda m: m.group(1) + re.sub(r"\s*<io [^>]*/>", "", m.group(2), count=0)
                      .replace("\n", "\n      " + io + "\n", 1) + m.group(3), text, flags=re.S)
    text = text.replace("<code>MSX1 EU 16K</code>", "<code>MSX1 EU 16K mirrors</code>")
    (d / f"{MIRROR}.xml").write_text(text)
    return d


def ports(res):
    out = {}
    folder = mirror_machines()
    for m, machine in list(MACHINES.items()) + [("mirror", MIRROR)]:
        saved = msxcap.MACHINES
        msxcap.MACHINES = folder
        try:
            reads, writes, printed = run_ports(machine)
        finally:
            msxcap.MACHINES = saved
        if m == "mirror":
            r1 = reads["r1"]
            out[m] = mirror_result(reads, writes, printed, r1[0xA8], r1[0x99], r1[0xAB])
            continue
        r1, r3, r2 = reads["r1"], reads["r3"], reads["r2"]
        assert r1 == r3, [hex(p) for p in range(256) if r1[p] != r3[p]]     # B does not matter
        slots, status, control = r1[0xA8], r1[0x99], r1[0xAB]
        assert slots >> 2 & 3 == genC.SLOT_TEST, hex(slots)
        unlike = {}                     # ports that read other than the map says
        for p in range(256):
            for st, r, k in ((genC.S1, r1, "r1"), (genC.S2, r2, "r2")):
                if r[p] != model_read(p, st, slots, status, control):
                    assert not STRICT, (m, k, hex(p), hex(r[p]))
                    unlike[f"{k} {p:02X}"] = r[p]       # openMSX 17.0, 18.0: $91 as $90
        answers = {}
        for name, *_ in genC.WRITES:
            w = writes[name]
            assert sorted(w) == list(range(256)), (name, len(w))
            for port, st in w.items():
                for dev in changed(name, None, st):
                    answers.setdefault(dev, []).append(port)
        assert {d: ps for d, ps in answers.items()} == {d: [p] for p, d in WRITE.items()}, answers
        assert printed == bytes([genC.PRN_BYTE]), printed
        out[m] = {"r1": r1, "r2": r2, "slots": slots, "status": status, "control": control,
                  "answers": {d: ps for d, ps in sorted(answers.items())},
                  "printed": list(printed), "probes": sum(len(v) for v in writes.values()),
                  "unlike": unlike}
    res["ports"] = out


# ---------------------------------------------------------------- vdp
VSTATE = ('[H {VDP regs} 0 8] [H {VRAM pointer} 0 2] [D {VDP register latch status}] '
          '[D {VDP data latch value}] [D {VRAM access status}] '
          '[debug read {VDP status regs} 0] [H memory 0x%04X 8] [H {physical VRAM} 0 4] '
          '[H {physical VRAM} 0x%04X 4] [H {physical VRAM} 0x%04X 4] [H {physical VRAM} 0x3FFC 4] '
          '$::irq [machine_info time]') % (genC.RES, genC.PREFETCH, genC.AFTER_W)
VFIELDS = ["regs", "pointer", "latch", "dlatch", "access", "status", "res", "v0000", "v2000",
           "v2100", "v3ffc", "irq", "time"]


def vdp_tcl(s):
    out = [HEX, "set ::irq 0", 'debug set_bp 0x0038 {} {incr ::irq}']
    for name, _ in genC.vdp_cases():
        extra = ' [H {physical VRAM} 0 16384]' if name == "k4" else ""
        out.append(f'debug set_bp 0x{s["v" + name]:04X} {{}} {{L "V {name} {VSTATE}{extra}"}}')
    out.append(f'debug set_bp 0x{s["done"]:04X} {{}} {{L "end"; L done; exit}}')
    return "\n".join(out) + "\n"


def run_vdp(machine):
    s = probe.sym(HERE / "vdp.sym")
    lines = msxcap.run_tcl(HERE / "vdp.rom", 300, vdp_tcl(s), machine=machine, timeout=600)
    out = {}
    for l in lines:
        w = l.split()
        if w[0] == "V":
            out[w[1]] = dict(zip(VFIELDS + ["vram"], w[2:]))
            out[w[1]]["time"] = round(float(out[w[1]]["time"]) * CLOCK)     # in T-states
    assert "end" in lines
    return out


CLOCK = 3579545                 # the Z80's T-states a second
FRAME_T = {"eu": 313 * 228, "jp": 262 * 228}    # a frame's T-states (chapter 18)
KEEP = [0x03, 0xFB, 0x0F, 0xFF, 0x07, 0x7F, 0x07, 0xFF]     # what openMSX keeps of $FF


def k4_map(a):
    """the 4 KB mode, measured: bits 6 to 11 of the address move up one, bit 12
    goes to bit 6, bits 0 to 5 and 13 stay"""
    return (a & 0x203F) | (a & 0x0FC0) << 1 | (a & 0x1000) >> 6


def vdp_facts(v, m):
    """every case of vdp.asm against what the appendix says of it"""
    regs = lambda c: list(bytes.fromhex(v[c]["regs"]))
    ptr = lambda c: int.from_bytes(bytes.fromhex(v[c]["pointer"]), "little")
    res = lambda c: list(bytes.fromhex(v[c]["res"]))
    vram = lambda c, k: list(bytes.fromhex(v[c][k]))
    base = genC.BASE_REGS
    for r in range(8):                                          # what each register keeps
        assert regs(f"keep{r}ff") == base[:r] + [KEEP[r]] + base[r + 1:], (r, regs(f"keep{r}ff"))
        assert regs(f"keep{r}00") == base[:r] + [0] + base[r + 1:]
        # and a register write leaves the address: the value, and the register's number
        assert ptr(f"keep{r}ff") == r << 8 | 0xFF and ptr(f"keep{r}00") == r << 8
    for n in range(8, 16):                                      # numbers 8 to 15: n AND 7
        want = [0] * 8
        want[n & 7] = KEEP[n & 7]
        assert regs(f"num{n}") == want, (n, regs(f"num{n}"))
    for x in genC.HIGH_NUMS:                                    # and bits 4 and 5 too
        want = [0] * 8
        want[x & 7] = KEEP[x & 7]
        assert regs(f"high{x:02X}") == want, (hex(x), regs(f"high{x:02X}"))
    for n in range(8):                                          # bit 6 changes nothing
        want = [0] * 8
        want[n] = KEEP[n]
        assert regs(f"bit6_{n}") == want
    # the first byte goes into the address's low byte at once, the latch waits
    want_latch = {"first": "1", "second": "0", "cleared1": "0", "cleared2": "1", "bydata1": "0",
                  "bydata2": "1"}
    latch = lambda c: v[c]["latch"] in ("-", want_latch[c])     # "-": openMSX 17.0, 18.0
    assert not STRICT or all(v[c]["latch"] != "-" for c in want_latch)
    assert latch("first") and ptr("first") & 0xFF == 0x34
    assert latch("second") and ptr("second") == 0x1234
    assert latch("cleared1") and latch("cleared2")              # the status read clears it
    assert ptr("cleared2") == 0x1256 and ptr("cleared3") == 0x1A56     # the next byte a first
    assert latch("bydata1") and latch("bydata2")                # and so does a data read
    assert ptr("bydata2") == 0x1A41
    assert vram("wrap_w", "v3ffc")[3] == 0xC1 and vram("wrap_w", "v0000")[0] == 0xC2
    assert res("wrap_r")[:2] == [0xC1, 0xC2]
    # the byte read ahead: a read address fetches; IN gives it and fetches the next;
    # a write goes where the address has got to and becomes the byte read ahead
    assert ptr("pre1") == genC.PREFETCH + 1 and res("pre2")[2] == 0x11 and ptr("pre2") == genC.PREFETCH + 2
    assert vram("pre3", "v2000") == [0x11, 0x22, 0xEE, 0x44] and res("pre4")[3] == 0xEE
    assert res("wthenr")[4] == 0x44 and ptr("wthenr") == genC.AFTER_W + 1   # no fetch: old byte
    k4 = bytes.fromhex(v["k4"]["vram"])
    where = {k + 1: [i for i in range(len(k4)) if k4[i] == k + 1] for k in range(len(genC.MARKS))}
    for k, a in enumerate(genC.MARKS):
        assert where[k + 1] == [k4_map(a)], (hex(a), where[k + 1])
    f = res("fwait")
    assert f[5] == 0x9F and f[6] == 0x1F                        # F, then cleared
    s1, s2 = res("sprites")[6:8], res("sprites2")[6:8]
    assert s1 == [0xA5, 0x05] and s2 == [0xE4, 0x04], (s1, s2)
    seconds = (v["ieonend"]["time"] - v["ieonstart"]["time"]) / CLOCK
    frames = seconds * CLOCK / FRAME_T[m]
    irq = int(v["ieonend"]["irq"]) - int(v["ieonstart"]["irq"])
    assert int(frames) <= irq <= int(frames) + 1, (irq, frames)    # one interrupt a frame
    assert v["ieoffend"]["irq"] == v["ieoffstart"]["irq"], irq   # and none with IE at 0
    return {"keep": KEEP, "k4": {f"{a:04X}": f"{k4_map(a):04X}" for a in genC.MARKS},
            "status": {"f": f[5:7], "sprites": s1, "sprites2": s2},
            "irq": irq, "irq_frames": round(seconds * CLOCK / FRAME_T[m], 2)}


def vdp(res):
    out = {}
    for m, machine in MACHINES.items():
        v = run_vdp(machine)
        out[m] = {"facts": vdp_facts(v, m), "cases": v}
    res["vdp"] = out


# ---------------------------------------------------------------- start
def start(res):
    """what C-BIOS leaves when it calls a cartridge's INIT: the VDP's
    registers, its status (peeked, so not cleared) and address, the PSG's
    registers, the PPI's ports A and C, and the Z80's SP, IM and IFF"""
    out = {}
    for m, machine in MACHINES.items():
        tcl = (HEX + 'L "S [H {VDP regs} 0 8] [debug read {VDP status regs} 0] '
               '[H {VRAM pointer} 0 2] [H {PSG regs} 0 16] [debug read ioports 0xA8] '
               '[debug read ioports 0xAA] [reg sp] [reg im] [reg iff]"\n')    # run at INIT
        lines = msxcap.run_tcl(HERE / "vdp.rom", 1, tcl, machine=machine, timeout=300)
        w = next(l for l in lines if l.startswith("S ")).split()[1:]
        out[m] = {"vdp": w[0], "status": int(w[1]),
                  "pointer": int.from_bytes(bytes.fromhex(w[2]), "little"), "psg": w[3],
                  "a": int(w[4]), "c": int(w[5]), "sp": int(w[6]), "im": int(w[7]),
                  "iff": int(w[8])}
    # bit 6 of register 14 on a Japanese machine whose file says the other layout of
    # the kana keys, JIS (MSXBOOK_JP16's says 50on)
    d = Path(tempfile.mkdtemp(prefix="jisC_"))
    for x in (REPO / "machines").glob("*.xml"):
        (d / x.name).write_text(x.read_text())
    jp = (REPO / "machines" / "MSXBOOK_JP16.xml").read_text()
    assert jp.count("<keyboardlayout>50on</keyboardlayout>") == 1
    (d / "MSXBOOK_JP16J.xml").write_text(jp.replace("<keyboardlayout>50on</keyboardlayout>",
                                                    "<keyboardlayout>jis</keyboardlayout>"))
    saved = msxcap.MACHINES
    msxcap.MACHINES = d
    try:
        lines = msxcap.run_tcl(HERE / "vdp.rom", 1, HEX + 'L "S [H {PSG regs} 14 1]"\n',
                               machine="MSXBOOK_JP16J", timeout=300)
    finally:
        msxcap.MACHINES = saved
    out["jis_r14"] = int(next(l for l in lines if l.startswith("S ")).split()[1], 16)
    res["start"] = out


# ---------------------------------------------------------------- vdps
# the VDPs openMSX's MSX1 files name (the files step counts them), but the
# V9938, an MSX2's, which eight give an MSX1
VDP_VERSIONS = ["T6950NTSC", "T6950PAL", "T7937ANTSC", "T7937APAL", "TMS9118", "TMS9128",
                "TMS9129", "TMS9918A", "TMS9928A", "TMS9929A", "TMS99X8A", "YM2220NTSC",
                "YM2220PAL"]


def vdps(res):
    """vdp.rom on the book's machine with each of VDP_VERSIONS: the kept bits,
    the status in fwait, sprites and sprites2, and where the 4 KB mode's
    marks landed: as written ("16 KB": the bit changes nothing) or moved"""
    d = Path(tempfile.mkdtemp(prefix="vdpsC_"))
    for x in (REPO / "machines").glob("*.xml"):
        (d / x.name).write_text(x.read_text())
    book = (REPO / "machines" / "MSXBOOK_EU16.xml").read_text()
    assert "<version>TMS9929A</version>" in book
    for ver in VDP_VERSIONS:
        (d / f"MSXBOOK_V{ver}.xml").write_text(book.replace("<version>TMS9929A</version>",
                                                             f"<version>{ver}</version>"))
    out = {}
    saved = msxcap.MACHINES
    msxcap.MACHINES = d
    try:
        for ver in VDP_VERSIONS:
            v = run_vdp(f"MSXBOOK_V{ver}")
            k4 = bytes.fromhex(v["k4"]["vram"])
            where = [[i for i in range(len(k4)) if k4[i] == k + 1] for k in range(len(genC.MARKS))]
            kind = ("16 KB" if where == [[a] for a in genC.MARKS] else
                    "moved" if where == [[k4_map(a)] for a in genC.MARKS] else "other")
            regs = lambda c: bytes.fromhex(v[c]["regs"])
            st = lambda c: list(bytes.fromhex(v[c]["res"]))
            out[ver] = {"k4": kind, "keep": [regs(f"keep{r}ff")[r] for r in range(8)],
                        "status": st("fwait")[5:7] + st("sprites")[6:8] + st("sprites2")[6:8]}
    finally:
        msxcap.MACHINES = saved
    if STRICT:
        assert all(e["keep"] == KEEP and e["status"] == [0x9F, 0x1F, 0xA5, 0x05, 0xE4, 0x04]
                   for e in out.values()), out
        assert {k: e["k4"] for k, e in out.items() if e["k4"] == "moved"} == {
            k: "moved" for k in ("TMS9918A", "TMS9928A", "TMS9929A", "TMS99X8A")}, out
        assert all(e["k4"] in ("16 KB", "moved") for e in out.values())
    res["vdps"] = out


# ---------------------------------------------------------------- psg
PSG_MACHINES = {"eu": "MSXBOOK_EU16", "ay": "MSXBOOK_EU16AY", "p": "MSXBOOK_EU16P",
                "jp": "MSXBOOK_JP16"}
SWITCHES = ["up", "down", "left", "right", "a", "b"]        # bits 0 to 5 of register 14
# the key-joysticks of chapter 35: the host's keys that move each, pressed with
# xdotool; openMSX 17 to 19 call them keyjoystick, 20 and later msxjoystick
KEYS = {1: dict(up="I", down="K", left="J", right="L", a="U", b="O"),
        2: dict(up="T", down="G", left="F", right="H", a="R", b="Y")}
SETTING = {"a": "triga", "b": "trigb"}
PLUG = ('if {"keyjoystick1" in [machine_info pluggable]} {\n' +
        "plug joyporta keyjoystick1\nplug joyportb keyjoystick2\n" +
        "".join(f"set keyjoystick{p}.{SETTING.get(s, s)} {k}\n" for p in KEYS for s, k in KEYS[p].items()) +
        "} else {\nplug joyporta msxjoystick1\nplug joyportb msxjoystick2\n" +
        "".join(f"set msxjoystick{p}_config {{" +
                " ".join(f"{s.upper()} {{{{keyb {k}}}}}" for s, k in KEYS[p].items()) + "}\n" for p in KEYS) +
        "}\n")
FOCUS = "exec xdotool search --class openMSX windowfocus --sync; "
HOLD_FROM, HOLD, GAP = 30, 4, 3          # frames: the first hold, each hold, the gap after


def holds():
    """[(first frame, last frame, port, switch)]: each switch of each port held alone"""
    out, f = [], HOLD_FROM
    for port in (1, 2):
        for sw in SWITCHES:
            out.append((f, f + HOLD - 1, port, sw))
            f += HOLD + GAP
    return out


def joy_events():
    ev = {}
    for a, b, port, sw in holds():
        key = KEYS[port][sw].lower()
        ev[a] = f"{FOCUS}exec xdotool keydown {key}"     # the machine waits for exec
        ev[b + 1] = f"{FOCUS}exec xdotool keyup {key}"
    return ev


def psg_tcl(s):
    out = [HEX]
    for name, _ in genC.psg_cases():
        out.append(f'debug set_bp 0x{s["p" + name]:04X} {{}} {{L "P {name} '
                   f'[expr {{[machine_info VDP_frame_count] - $::f0}}] [H {{PSG regs}} 0 16] '
                   f'[H memory 0x{genC.RES:04X} 80]"}}')
    out.append(f'debug set_bp 0x{s["done"]:04X} {{}} {{L "end"; L done; exit}}')
    return "\n".join(out) + "\n"


LAMP_AT = (7, 17)               # frames inside the lamp's two phases of psg.asm


def sample(what):
    """an event: the machine paused, and 0.3 s later, when openMSX has caught
    up with its lamps, WHAT logged and the machine let go"""
    return f"set ::pause on; after realtime 0.3 {{{what}; set ::pause off}}"


def psg_run(machine, events):
    s = probe.sym(HERE / "psg.sym")
    lines = msxcap.run_tcl(HERE / "psg.rom", 200, psg_tcl(s), machine=machine, timeout=900,
                           tcl_setup=PLUG, events=events)
    out = {}
    for l in lines:
        w = l.split()
        if w[0] == "P":
            rec = dict(frame=int(w[2]), regs=w[3], res=w[4])
            if w[1] == "joy":
                out.setdefault("joy", []).append(rec)
            else:
                out[w[1]] = rec
        elif w[0] == "LAMP":
            out.setdefault("lamp", []).append((int(w[1]), w[2]))
    assert "end" in lines
    return out


def run_psg(machine):
    """psg.rom with the kana lamp sampled, which pauses the machine; no key held"""
    return psg_run(machine, {f: sample('L "LAMP [expr {[machine_info VDP_frame_count] - '
                                       '$::f0}] $::led_kana"') for f in LAMP_AT})


AY_KEEP = {1: 0x0F, 3: 0x0F, 5: 0x0F, 6: 0x1F, 8: 0x1F, 9: 0x1F, 10: 0x1F, 13: 0x0F}


def pins_low(r15, q):
    """the pins 6 and 7 that register 15 holds at 0 on port Q (1 or 2), as
    register 14's bits 4 and 5, the buttons"""
    return (~r15 >> (0 if q == 1 else 2) & 3) << 4


def psg_facts(v, m):
    """psg.asm's cases against what the appendix says"""
    res = list(bytes.fromhex(v["joyend"]["res"]))
    keep = {r: (res[2 * r], res[2 * r + 1]) for r in range(16)}
    ay = m == "ay"
    honours = m == "p"                          # MSXBOOK_EU16P: register 7's bits 6 and 7 count
    for r in range(16):
        if r == 14:
            want = (0xBF, 0xBF)                 # an input: the joystick port, whatever is written
        elif r == 7 and not honours:
            want = (0xBF, 0x80)                 # bits 7 and 6 read 1 0, whatever is written
        else:
            want = (AY_KEEP.get(r, 0xFF) if ay else 0xFF, 0x00)
        assert keep[r] == want, (m, r, keep[r], want)
    sel = res[32:32 + len(genC.SELECTS)]
    for k, x in enumerate(genC.SELECTS):        # a number above 15: its low 4 bits
        assert sel[k] == (AY_KEEP.get(x & 15, 0xFF) & 0x5A if ay else 0x5A)
        regs = bytes.fromhex(v[f"sel{x:02x}"]["regs"])
        assert regs[x & 15] == (AY_KEEP.get(x & 15, 0xFF) & 0x5A if ay else 0x5A)
    # register 15 at $CA: port 2 chosen, its pin 6 at 0. Pins 6 and 7 change nothing,
    # or (openMSX 17.0 and 18.0, chapter 35) a pin at 0 reads as its button held
    d = res[32 + len(genC.SELECTS):32 + len(genC.SELECTS) + 6]
    pins67 = "ignored" if d[5] == 0xBF else "counted"
    assert not STRICT or pins67 == "ignored", d
    b = 0xBF & ~pins_low(0xCA, 2) if pins67 == "counted" else 0xBF
    if honours:
        assert d == [0x55, 0xBF, 0xFF, 0xBF, 0xCA, b], d       # port B an input: pins high
    else:
        assert d == [0xBF, 0xBF, 0xCA, b, 0xCA, b], d
    lamp = dict((f, l) for f, l in v["lamp"])
    assert [lamp[f] for f in LAMP_AT] == ["on", "off"], v["lamp"]
    return {"keep": {r: list(keep[r]) for r in range(16)}, "dirs": d, "pins67": pins67}


def psg(res):
    out = {}
    for m, machine in PSG_MACHINES.items():
        v = run_psg(machine)
        out[m] = {"facts": psg_facts(v, m), "cases": v}
    res["psg"] = out


# ---------------------------------------------------------------- joy
def joy_facts(v, m):
    """psg.rom's joy case, the switches held one at a time: register 14 of
    the port bit 6 of register 15 chooses, read while its pin 8 is low"""
    at = genC.RES_PSG_JOY - genC.RES
    rows = {}
    for a_, b_, port, sw in holds():
        frames = [j["frame"] for j in v["joy"] if a_ + 1 <= j["frame"] <= b_]
        got = {bytes.fromhex(j["res"])[at:at + 2 * len(genC.PINS15)] for j in v["joy"]
               if j["frame"] in frames}
        assert len(got) == 1, (sw, port, got)
        got = list(got.pop())
        bit = 0xBF ^ (1 << SWITCHES.index(sw))
        for k, r15 in enumerate(genC.PINS15):
            pin8_high = r15 >> (4 if port == 1 else 5) & 1
            for q, val in ((1, got[2 * k]), (2, got[2 * k + 1])):
                assert val == (bit if q == port and not pin8_high else 0xBF), \
                    (m, sw, port, hex(r15), q, hex(val))
        rows[f"{port} {sw}"] = got[0] if port == 1 else got[1]
    return {"r14": rows}


def joy(res):
    """the joysticks held: chapter 35's key-joysticks, whose keys xdotool
    presses on the virtual display. Left out of the openmsx step: under the
    virtual display openMSX 20.0 and 21.0 took the keys only in part, run to
    run (chapter 35 compares the joysticks of all five builds)"""
    out = {}
    for m, machine in MACHINES.items():
        v = psg_run(machine, joy_events())
        out[m] = {"facts": joy_facts(v, m), "cases": {"joy": v["joy"]}}
    res["joy"] = out


# ---------------------------------------------------------------- ppi
TAPE_RATE = 44100


def silent_tape(path, seconds=5):
    import wave
    w = wave.open(str(path), "wb")
    w.setnchannels(1)
    w.setsampwidth(1)
    w.setframerate(TAPE_RATE)
    w.writeframes(bytes([128]) * TAPE_RATE * seconds)
    w.close()


ROWS_DOWN, ROWS_UP = 5, 11      # the frames the keys of ppi.asm go down and up
MODE_WORDS = [0x82, 0x9B, 0x82] # written by the debugger at the end: the BIOS's mode
                                # word again, all three ports inputs, and the BIOS's again


def ppi_tcl(s):
    out = [HEX]
    for name, _ in genC.ppi_cases():
        body = (f'L "I {name} [expr {{[machine_info VDP_frame_count] - $::f0}}] '
                f'[H memory 0x{genC.RES:04X} 80] [H memory 0xC100 256] [H memory 0xC200 16] '
                f'[debug read ioports 0xA8] [debug read ioports 0xAA]"')
        out.append(f'debug set_bp 0x{s["i" + name]:04X} {{}} {{{body}}}')
    end = "; ".join(f'debug write ioports 0xAB 0x{w:02X}; L "M {k} {w} [debug read ioports 0xA8] '
                    f'[debug read ioports 0xA9] [debug read ioports 0xAA]"'
                    for k, w in enumerate(MODE_WORDS))
    out.append(f'debug set_bp 0x{s["done"]:04X} {{}} {{L "end"; {end}; L done; exit}}')
    return "\n".join(out) + "\n"


PPI_SAMPLES = {"rows": 6, "phase0": 15, "phase1": 25}    # frames of ppi.asm: port C at
                                # $50, then in its two phases (the probes' frames)


def ppi_events():
    keys = "; ".join(f"keymatrixdown {r} 0x{1 << b:02X}" for r, b in genC.ROW_KEYS)
    ups = "; ".join(f"keymatrixup {r} 0x{1 << b:02X}" for r, b in genC.ROW_KEYS)
    ev = {ROWS_DOWN: keys, ROWS_UP: ups}
    for name, f in PPI_SAMPLES.items():
        ev[f] = (ev[f] + "; " if f in ev else "") + sample(
            f'L "LAMP {name} [expr {{[machine_info VDP_frame_count] - $::f0}}] $::led_caps '
            f'[cassetteplayer getpos]"')
    return ev


def run_ppi(machine):
    s = probe.sym(HERE / "ppi.sym")
    d = Path(tempfile.mkdtemp(prefix="tape_"))
    silent_tape(d / "silence.wav")
    lines = msxcap.run_tcl(HERE / "ppi.rom", 60, ppi_tcl(s), machine=machine, timeout=600,
                           tcl_setup=f"cassetteplayer insert {{{d / 'silence.wav'}}}\n",
                           events=ppi_events())
    out = {"rows": [], "lamp": {}, "mode": {}}
    for l in lines:
        w = l.split()
        if w[0] == "I":
            rec = dict(frame=int(w[2]), res=w[3], cback=w[4], rows=w[5], a=int(w[6]), c=int(w[7]))
            if w[1] == "rows":
                out["rows"].append(rec)
            else:
                out[w[1]] = rec
        elif w[0] == "LAMP":
            out["lamp"][w[1]] = [int(w[2]), w[3], round(float(w[4]), 6)]    # seconds
        elif w[0] == "M":
            out["mode"][w[1]] = [int(x) for x in w[2:]]        # the word, then A, B, C
    assert "end" in lines
    return out


def wav_samples(path):
    import array
    import wave
    w = wave.open(str(path))
    data = w.readframes(w.getnframes())
    a = array.array("h", data) if w.getsampwidth() == 2 else array.array("B", data)
    return list(a[::w.getnchannels()]), w.getframerate()


def crossings(seg):
    """how many times SEG crosses the middle of its range, and that range"""
    lo, hi = min(seg), max(seg)
    mid = (lo + hi) / 2
    return sum(1 for i in range(1, len(seg)) if (seg[i - 1] - mid) * (seg[i] - mid) < 0), hi - lo


def run_ppi_audio(machine, frames, hz):
    """ppi.asm's sound, recorded from INIT, and the cassette output, recorded
    while the motor runs: in phase 0 bit 7 (the click) and bit 5 (the
    output) turn over together; the frequency of each, in phase 0, and the
    sound's range in phase 1"""
    d = Path(tempfile.mkdtemp(prefix="ppiaudio_"))
    cas = d / "casout.wav"
    msxcap.record_audio(HERE / "ppi.rom", 40, d / "sound.wav", machine=machine,
                        events={0: f"cassetteplayer new {{{cas}}}", 36: "cassetteplayer eject"})
    snd, rate = wav_samples(d / "sound.wav")
    t = lambda f: int(f / hz * rate)
    a0, a1 = frames["rowsend"] + 1, frames["phase0"]          # phase 0's whole frames
    seg = snd[t(a0):t(a1)]
    quiet = snd[t(frames["phase0"] + 2):t(frames["phase1"])]
    cs, crate = wav_samples(cas)
    return {"click_hz": round(rate_of(seg, rate)), "click_range": max(seg) - min(seg),
            "quiet_range": max(quiet) - min(quiet), "tape_seconds": round(len(cs) / crate, 3),
            "tape_hz": round(rate_of(cs, crate)), "tape_range": [min(cs), max(cs)]}


def rate_of(seg, rate):
    """a square wave's frequency: its rises counted from the first to the last"""
    up = rises(seg)
    return (len(up) - 1) * rate / (up[-1] - up[0])


SIGN = {(0, 0): "F3C3", (0, 1): "4142", (1, 0): "0000", (1, 1): "4142", (2, 0): "432D",
        (2, 1): "4142", (3, 3): "524D"}     # what each page shows from each slot; $FFFF else


def ppi_facts(v, m):
    res = bytes.fromhex(v["cend"]["res"])
    slots = {(page, slot): res[2 * (4 * page + slot):2 * (4 * page + slot) + 2].hex().upper()
             for page in range(4) for slot in range(4)}
    assert slots == {k: SIGN.get(k, "FFFF") for k in slots}, slots
    cb = bytes.fromhex(v["cend"]["cback"])
    assert list(cb) == list(range(256))                 # port C reads back what was written
    want = [0xFF ^ (1 << b) for r, b in genC.ROW_KEYS] + [0xFF] * (16 - len(genC.ROW_KEYS))
    rows = [bytes.fromhex(r["rows"]) for r in v["rows"]]
    frames = [r["frame"] for r in v["rows"]]
    for f, r in zip(frames, rows):
        assert list(r) == (want if ROWS_DOWN <= f < ROWS_UP else [0xFF] * 16), (f, r.hex())
    ctrl = list(res[32:32 + 16 * len(genC.CTRL_STARTS) + 1])
    for k, start in enumerate(genC.CTRL_STARTS):        # each command from $00 and from $FF:
        for b in range(8):                              # its bit set or reset from 0 and
            for val in (0, 1):                          # from 1, and no other bit moved
                c = start & ~(1 << b) | val << b
                assert ctrl[16 * k + 2 * b + val] == c, (k, b, val, hex(ctrl[16 * k + 2 * b + val]))
    assert ctrl[-1] == 0x82                             # the control port read: the mode word
    # the debugger peeks: an output port gives its latch, port A as an input 0 (openMSX)
    assert v["mode"] == {"0": [0x82, 0xC4, 0xFF, genC.C_BASE], "1": [0x9B, 0x00, 0xFF, 0xFF],
                         "2": [0x82, 0xC4, 0xFF, genC.C_BASE]}, v["mode"]
    lamp = v["lamp"]
    assert [lamp[k][1] for k in ("rows", "phase0", "phase1")] == ["off", "on", "off"]
    hz = {"eu": 50, "jp": 60}[m]
    t0, t1, t2 = (lamp[k][2] for k in ("rows", "phase0", "phase1"))
    assert abs(t2 - genC.PHASE_FRAMES / hz) < 0.01 and t0 < 0.01   # 10 frames of motor
    a = v["audio"]
    t_half = 788                                                   # T-states a half period
    assert abs(a["click_hz"] - CLOCK / 2 / t_half) < 3 and a["quiet_range"] < a["click_range"] / 10
    # the cassette output as openMSX records it: the click's frequency, for as long as the
    # motor ran (openMSX 17.0 and 18.0 record it shorter)
    assert not STRICT or abs(a["tape_hz"] - a["click_hz"]) < 10 and abs(a["tape_seconds"] - t2) < 0.01
    return {"slots": {f"{pg} {sl}": v_ for (pg, sl), v_ in slots.items()}, "tape": [t0, t1, t2],
            "click_hz": a["click_hz"], "tape_hz": a["tape_hz"]}


def ppi(res):
    out = {}
    for m, machine in MACHINES.items():
        v = run_ppi(machine)
        frames = {k: v[k]["frame"] for k in ("rowsend", "phase0", "phase1")}
        v["audio"] = run_ppi_audio(machine, frames, {"eu": 50, "jp": 60}[m])
        out[m] = {"facts": ppi_facts(v, m), "cases": v}
    res["ppi"] = out


# ---------------------------------------------------------------- sound
def run_sound(machine):
    """sound.rom: the time of each phase, from a run with breakpoints, and
    the sound of another run, recorded from INIT; each phase's frequency and
    range, from its second frame to the frame before the next phase"""
    s = probe.sym(HERE / "sound.sym")
    cases = [n for n, _ in genC.sound_cases()]
    tcl = "".join(f'debug set_bp 0x{s["s" + n]:04X} {{}} {{L "S {n} [machine_info time]"}}\n'
                  for n in cases)
    frames = len(cases) * genC.SOUND_FRAMES + 10
    lines = msxcap.run_tcl(HERE / "sound.rom", frames, tcl, machine=machine, timeout=600)
    t0 = float(next(l for l in lines if l.startswith("f0 ")).split()[3])
    at = {l.split()[1]: float(l.split()[2]) - t0 for l in lines if l.startswith("S ")}
    assert list(at) == cases, at
    d = Path(tempfile.mkdtemp(prefix="soundC_"))
    msxcap.record_audio(HERE / "sound.rom", frames, d / "sound.wav", machine=machine)
    snd, rate = wav_samples(d / "sound.wav")
    hz = {"MSXBOOK_EU16": 50, "MSXBOOK_JP16": 60}[machine]
    out = {}
    for k, n in enumerate(cases):
        # from the 10th frame: the recording takes the sound's mean away slowly,
        # and a new volume moves the mean
        a = at[n] + SETTLE_FRAMES / hz
        b = (at[cases[k + 1]] if k + 1 < len(cases) else at[n] + genC.SOUND_FRAMES / hz) - 1 / hz
        seg = snd[int(a * rate):int(b * rate)]
        up = rises(seg)
        out[n] = {"hz": round((len(up) - 1) * rate / (up[-1] - up[0]), 1) if len(up) > 2 else 0,
                  "range": max(seg) - min(seg)}
    return out


SETTLE_FRAMES = 10


def rises(seg):
    """the samples where SEG goes from its low quarter to its high quarter,
    the quarters of the range between its 10th and 90th percentiles (the
    recordings' peaks drift: the cassette output starts high and settles)"""
    s = sorted(seg)
    lo, hi = s[len(s) // 10], s[len(s) * 9 // 10]
    low, high, state, out = lo + (hi - lo) / 4, hi - (hi - lo) / 4, None, []
    for i, x in enumerate(seg):
        if x < low:
            state = "low"
        elif x > high and state == "low":
            state = "high"
            out.append(i)
    return out


def sound_facts(v):
    """each period's tone at the PSG's clock / 16 / the period, within 1 %;
    each volume's range against openMSX's table of levels, 3 dB a step,
    within 2 %"""
    for p in genC.TONES:
        want = CLOCK / 2 / 16 / p
        assert abs(v[f"t{p:03X}"]["hz"] / want - 1) < 0.01, (p, v[f"t{p:03X}"], want)
    ref = v["v15"]["range"]
    levels = {x: v[f"v{x}"]["range"] / ref for x in genC.VOLUMES}
    for x, lv in levels.items():
        assert abs(lv / 2 ** ((x - 15) / 2) - 1) < 0.02, (x, lv)     # 3 dB, half a bit, a step
    assert v["off"]["range"] < ref / 100
    return {"tones": {f"{p}": v[f"t{p:03X}"]["hz"] for p in genC.TONES},
            "levels": {f"{x}": round(lv, 4) for x, lv in levels.items()}}


def sound(res):
    out = {}
    for m, machine in MACHINES.items():
        v = run_sound(machine)
        out[m] = {"facts": sound_facts(v), "cases": v}
    res["sound"] = out


# ---------------------------------------------------------------- keys
LAMPS = 'L "LAMP [expr {[machine_info VDP_frame_count] - $::f0}] $::led_caps $::led_kana"'


def keys_events():
    """each press down for 4 frames; the lamps before the first and after
    each press of a toggle, in the press's last frame"""
    ev = {genC.KEY_FROM - 2: sample(LAMPS)}
    for f, ks in genC.presses():
        ev[f] = "; ".join(f"keymatrixdown {r} 0x{1 << b:02X}" for r, b in ks)
        ev[f + 4] = "; ".join(f"keymatrixup {r} 0x{1 << b:02X}" for r, b in ks)
        if len(ks) == 1 and tuple(ks[0]) in genC.TOGGLES:
            ev[f + genC.KEY_EVERY - 1] = sample(LAMPS)
    return ev


def run_keys(machine):
    s = probe.sym(HERE / "keys.sym")
    last = genC.presses()[-1][0] + genC.KEY_EVERY
    tcl = (f'debug set_bp 0x{s["got"]:04X} {{}} '
           f'{{L "K [expr {{[machine_info VDP_frame_count] - $::f0}}] [reg a]"}}\n')
    lines = msxcap.run_tcl(HERE / "keys.rom", last + 4, tcl, machine=machine, timeout=900,
                           events=keys_events())
    got = [(int(l.split()[1]), int(l.split()[2])) for l in lines if l.startswith("K ")]
    lamps = {int(l.split()[1]): l.split()[2:] for l in lines if l.startswith("LAMP ")}
    out = []
    for f, ks in genC.presses():
        chars = [c for g, c in got if f <= g < f + genC.KEY_EVERY]
        rec = {"frame": f, "keys": [list(k) for k in ks], "chars": chars}
        lamp = [v for g, v in lamps.items() if f <= g < f + genC.KEY_EVERY]
        if lamp:
            rec["lamps"] = lamp[0]
        out.append(rec)
    assert sum(len(o["chars"]) for o in out) == len(got), "a character outside every press"
    first = [v for g, v in lamps.items() if g < genC.KEY_FROM]
    assert len(first) == 1 and len(lamps) == 1 + 2 * len(genC.TOGGLES), lamps
    return {"presses": out, "lamps_before": first[0]}


# the keys of rows 6 to 10 by name, as chapter 34 names them, and the code
# C-BIOS types for the ones that type one
NAMES = {(6, 0): "SHIFT", (6, 1): "CTRL", (6, 2): "GRAPH", (6, 3): "CAPS", (6, 4): "CODE",
         (6, 5): "F1", (6, 6): "F2", (6, 7): "F3", (7, 0): "F4", (7, 1): "F5", (7, 2): "ESC",
         (7, 3): "TAB", (7, 4): "STOP", (7, 5): "BS", (7, 6): "SELECT", (7, 7): "RETURN",
         (8, 0): "SPACE", (8, 1): "HOME", (8, 2): "INS", (8, 3): "DEL", (8, 4): "LEFT",
         (8, 5): "UP", (8, 6): "DOWN", (8, 7): "RIGHT"}
CODES = {"ESC": 0x1B, "TAB": 0x09, "BS": 0x08, "RETURN": 0x0D, "SPACE": 0x20, "HOME": 0x0C,
         "LEFT": 0x1D, "UP": 0x1E, "DOWN": 0x1F, "RIGHT": 0x1C}
PAD = "*+/0123456789-,."                # rows 9 and 10, the keypad, bit 0 first


def keys_facts(v, m):
    """what C-BIOS typed for each key alone, the keys that typed nothing,
    the toggles and the combinations; checked against the order of digits,
    letters and keypad, against NAMES and CODES, and against chapter 34's
    differences between the two keyboards"""
    alone = {}
    for o in v["presses"]:
        if len(o["keys"]) == 1:
            k = tuple(o["keys"][0])
            assert len(o["chars"]) <= 1, o
            assert alone.setdefault(k, o["chars"]) == o["chars"], (k, o["chars"])  # the same each time
    assert sorted(alone) == [(r, b) for r in range(11) for b in range(8)]
    ch = {k: chr(c[0]) if c else "" for k, c in alone.items()}
    order = [(r, b) for r in range(11) for b in range(8)]
    assert "".join(ch[k] for k in order[:10]) == "0123456789"
    assert "".join(ch[k] for k in order[22:48]) == "abcdefghijklmnopqrstuvwxyz"
    assert "".join(ch[k] for k in order[72:]) == PAD
    typed = {name: ord(ch[k]) for k, name in NAMES.items() if ch[k]}
    assert typed == CODES, typed
    silent = sorted(k for k, c in ch.items() if not c)
    named_silent = [k for k in NAMES if NAMES[k] not in CODES]
    assert silent == sorted(named_silent + ([(2, 5)] if m == "eu" else [])), silent
    assert v["lamps_before"] == ["off", "off"]
    lamps = [o["lamps"] for o in v["presses"] if "lamps" in o]
    assert lamps == [["off", "off"]] * 2 * len(genC.TOGGLES)      # C-BIOS turns neither on
    pairs = [o for o in v["presses"] if len(o["keys"]) > 1]
    combos = {"+".join(NAMES.get(tuple(k), "A") for k in o["keys"]): "".join(map(chr, o["chars"]))
              for o in pairs[:len(genC.COMBOS)]}
    assert combos == {"SHIFT+A": "A", "CTRL+A": "a", "GRAPH+A": "a", "CODE+A": "a"}, combos
    shifted = {}
    for o in pairs[len(genC.COMBOS):]:
        assert o["keys"][0] == list(genC.SHIFT) and len(o["chars"]) <= 1, o
        r, b = o["keys"][1]
        shifted[f"{r},{b}"] = chr(o["chars"][0]) if o["chars"] else ""
    assert len(shifted) == 8 * len(genC.SHIFTED)
    letters = [f"{r},{b}" for r in range(11) for b in range(8)][22:48]
    assert "".join(shifted[k] for k in letters) == "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    return {"chars": {f"{r},{b}": c for (r, b), c in sorted(ch.items())},
            "typed": sum(1 for c in ch.values() if c), "silent": [list(k) for k in silent],
            "combos": combos, "shifted": shifted, "lamps": "off"}


def keys(res):
    out = {}
    for m, machine in MACHINES.items():
        v = run_keys(machine)
        out[m] = {"facts": keys_facts(v, m), "cases": v}
    eu, jp = (out[m]["facts"]["chars"] for m in ("eu", "jp"))
    out["differ"] = [[*map(int, k.split(",")), eu[k], jp[k]] for k in eu if eu[k] != jp[k]]
    res["keys"] = out


# ---------------------------------------------------------------- files
SHARE = Path(os.environ.get("OPENMSX_SYSTEM_DATA", "/usr/share/openmsx"))


def io_of(text, dev):
    """the ports a device answers in a machine file: {"r": [...], "w": [...]}"""
    m = re.search(rf'<{dev} id="[^"]*">(.*?)</{dev}>', text, re.S)
    if not m:
        return None
    out = {"r": set(), "w": set()}
    for base, num, typ in re.findall(r'<io base="(0x[0-9A-Fa-f]+)" num="(\d+)"(?: type="(\w+)")?',
                                     m.group(1)):
        ports = range(int(base, 16), int(base, 16) + int(num))
        if typ in ("", "IO", "I"):
            out["r"].update(ports)
        if typ in ("", "IO", "O"):
            out["w"].update(ports)
    return {k: sorted(v) for k, v in out.items()}


def span(ports):
    return f"${ports[0]:02X}-${ports[-1]:02X}" if len(ports) > 1 else f"${ports[0]:02X}"


TAG = re.compile(r"<(/?)([A-Za-z_][\w.-]*)([^>]*?)(/?)>")


def io_lines(text):
    """[(device, port, type)] of a machine file: every io line, with the
    element it sits in. A small reader of its own, not an XML parser: two of
    openMSX's files are not well-formed XML, which openMSX itself accepts"""
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    stack, out = [], []
    for close, tag, attrs, empty in TAG.findall(text):
        if close:
            if tag in stack:
                while stack.pop() != tag:
                    pass
        elif tag == "io":
            a = dict(re.findall(r'(\w+)="([^"]*)"', attrs))
            base = int(a["base"], 16)
            for port in range(base, base + int(a.get("num", "1"))):
                out.append((stack[-1], port, a.get("type", "IO")))
        elif not empty:
            stack.append(tag)
    return out


def io_map(texts):
    """for each kind of device, the ports it answers and in how many of the
    machines: [[device, first, last, machines]], a run of ports a row"""
    count = {}
    for text in texts:
        for dev, port in {(d, p) for d, p, _ in io_lines(text)}:
            count[(dev, port)] = count.get((dev, port), 0) + 1
    rows = []
    for (dev, port), n in sorted(count.items(), key=lambda k: (k[0][1], k[0][0])):
        last = next((r for r in reversed(rows) if r[0] == dev), None)
        if last and last[2] == port - 1 and last[3] == n:
            last[2] = port
        else:
            rows.append([dev, port, port, n])
    return rows


def files(res):
    """the MSX1 machines openMSX describes, real models only (as chapter 55
    counts them): the VDP's and the PSG's chips, and the ports the VDP, the
    PSG and the PPI answer"""
    count, vdp_, psg_, ports_, texts, vdp_ports = 0, {}, {}, {}, [], {}
    for x in sorted((SHARE / "machines").glob("*.xml")):
        if x.is_symlink() or x.name.startswith("C-BIOS"):
            continue
        text = x.read_text(errors="replace")
        t = re.search(r"<type>([^<]*)</type>", text)
        if not t or t.group(1) != "MSX":
            continue
        count += 1
        texts.append(text)
        m = re.search(r'<VDP id="[^"]*">(.*?)</VDP>', text, re.S)
        v = re.search(r"<version>([^<]+)</version>", m.group(1)) if m else None
        vdp_[v.group(1) if v else "none"] = vdp_.get(v.group(1) if v else "none", 0) + 1
        m = re.search(r'<PSG id="[^"]*">(.*?)</PSG>', text, re.S)
        ty = re.search(r"<type>([^<]+)</type>", m.group(1)) if m else None
        k = ty.group(1) if ty else "no type"
        psg_[k] = psg_.get(k, 0) + 1
        for dev in ("VDP", "PSG", "PPI"):
            io = io_of(text, dev)
            key = f"{dev} r {span(io['r'])} w {span(io['w'])}"
            ports_[key] = ports_.get(key, 0) + 1
        io = io_of(text, "VDP")                 # which VDP takes which writes
        key = f"{v.group(1) if v else 'none'} w {span(io['w'])}"
        vdp_ports[key] = vdp_ports.get(key, 0) + 1
    assert not STRICT or sorted(set(vdp_) - {"V9938"}) == VDP_VERSIONS, vdp_
    res["files"] = {"share": str(SHARE), "msx1": count, "vdp": vdp_, "psg": psg_,
                    "iomap": io_map(texts), "vdp_ports": dict(sorted(vdp_ports.items())),
                    "ports": dict(sorted(ports_.items()))}


MIRROR_PERIOD = {0x98: 2, 0xA0: 4, 0xA8: 4}   # each chip's 8 ports: the same 2, 4, 4 again


def mirrored(table):
    """READ or WRITE on MIRROR: each port of a chip's 8 acts as the port of its
    first 2 or 4 that it equals modulo the period"""
    out = {}
    for base, period in MIRROR_PERIOD.items():
        for p in range(base, base + 8):
            first = base + (p - base) % period
            if first in table:
                out[p] = table[first]
    out.update({p: d for p, d in table.items() if p < 0x98})          # the printer, as it was
    return out


def mirror_result(reads, writes, printed, slots, status, control):
    answers = {}
    for name, *_ in genC.WRITES:
        for port, st in writes[name].items():
            for dev in changed(name, None, st):
                answers.setdefault(dev, []).append(port)
    want = {}
    for p, d in mirrored(WRITE).items():
        want.setdefault(d, []).append(p)
    assert answers == {d: sorted(ps) for d, ps in want.items()}, answers
    rd = mirrored(READ)
    for p in range(256):
        for st, r in ((genC.S1, reads["r1"]), (genC.S2, reads["r2"])):
            if r[p] != model_read(p, st, slots, status, control, dev=rd.get(p)):
                assert not STRICT, (hex(p), hex(r[p]))
    assert reads["r1"] == reads["r3"]
    return {"r1": reads["r1"], "r2": reads["r2"],
            "answers": {d: ps for d, ps in sorted(answers.items())}, "printed": list(printed)}


# ---------------------------------------------------------------- before
def chapter(n):
    return json.loads((REPO / f"ch{n:02d}" / f"meas{n:02d}.json").read_text())


def gen35():
    """chapter 35's generator, for the fourteen values its pins.asm writes"""
    sys.path.insert(0, str(REPO / "ch35"))
    sys.path.insert(1, str(REPO / "ch34"))
    import gen35 as g
    return g


def before(res):
    """appendix C's results against the chapters that measured the same
    things first, with their own programs: each check a number or a table
    of a chapter, rebuilt from what this appendix found. With another build
    of openMSX the checks are recorded, not asserted: the chapters' numbers
    are the book's build's"""
    out = {}
    for name, check in CHECKS.items():
        try:
            check(res)
            out[name] = True
        except AssertionError:
            assert not STRICT, name
            out[name] = False
    res["before"] = out


def ch19(res):
    """eight bytes written from $3FFC landed at $3FFC-$3FFF and $0000-$0003"""
    for m in MACHINES:
        v = res["vdp"][m]["cases"]
        assert v["wrap_w"]["v3ffc"][6:] == "c1" and v["wrap_w"]["v0000"][:2] == "c2"
    assert chapter(19)["address"]["wrote_to"] == [(0x3FFC + k) & 0x3FFF for k in range(8)]


def ch17(res):
    """the status the BIOS's interrupt read: F set and nothing else seen; and
    the interrupt mode C-BIOS calls INIT in"""
    for m in MACHINES:
        f = res["vdp"][m]["facts"]["status"]["f"]
        assert chapter(17)["bios"]["status_at_timi"] == [f[0]] == [0x9F]
        assert chapter(17)["modes"]["im_at_init"] == res["start"][m]["im"] == 0


def ch27(res):
    """a fifth sprite on a line, F cleared by a read before: 5S and number 4"""
    for m in MACHINES:
        s2 = res["vdp"][m]["facts"]["status"]["sprites2"]
        assert {x & 0x5F for x in chapter(27)["once"][m]["phases"][0]["statuses"]} == {s2[0] & 0x5F}


def ch34(res):
    """rows 11 to 15 read $FF; the six keys the two keyboards place differently"""
    for m in MACHINES:
        rows = [bytes.fromhex(r["rows"]) for r in res["ppi"][m]["cases"]["rows"]]
        assert all(set(r[11:]) == {0xFF} for r in rows)
        assert chapter(34)["matrix"][m]["rows_11_15"] == "FF"
    assert res["keys"]["differ"] == chapter(34)["legend"]["differ"]


def ch35(res):
    """register 15 written fourteen ways, port 1's register 14 with switches
    held, rebuilt from this appendix's rule: the port bit 6 chooses, read
    only while its pin 8 bit (4 for port 1) is 0; the kana lamp lit at bit 7 = 0"""
    c35 = chapter(35)
    pins = c35["pins"]["eu"]["table"]
    for held, got in pins.items():
        down = 0xBF
        for s in held.split():
            if s in SWITCHES:                   # the bit of each switch, as the joy step found
                down &= 0xBF ^ 1 << SWITCHES.index(s)
        want = [f"{down if not r15 & 0x50 else 0xBF:02X}" for r15 in gen35().PIN_VALUES]
        assert got == want, (held, got, want)
    kana = c35["pins"]["eu"]["kana"]
    assert all((x == "on") == (int(r15, 16) < 0x80) for r15, x in kana["changes"])
    assert all(int(r15, 16) < 0x80 for r15 in kana["lit"])


def ch36(res):
    """the volumes' ranges against chapter 36's levels, measured from its own
    recordings"""
    lv = chapter(36)["levels"]["levels"]
    for m in MACHINES:
        for x, got in res["sound"][m]["facts"]["levels"].items():
            assert abs(got / (lv[int(x)] / lv[15]) - 1) < 0.02, (x, got)


def ch38(res):
    """$A8 = $C4 at the start, and what each page then shows"""
    c38 = chapter(38)
    for m in MACHINES:
        sl = res["ppi"][m]["facts"]["slots"]
        pg = c38["pages"]["eu"]
        assert pg["a8"] == "C4" and pg["ids"] == ["00", "01", "00", "03"]
        assert [sl[f"{p} {int(pg['ids'][p])}"] for p in range(4)] == ["F3C3", "4142", "432D", "524D"]
        assert c38["breaks"]["stay32 eu"]["bytes"].startswith(sl["2 0"])


def ch55(res):
    """the MSX1 machines in openMSX's files, the same files as chapter 55's"""
    c55 = chapter(55)["patterns"]
    assert c55["share"] == res["files"]["share"] and c55["msx1"] == res["files"]["msx1"]


CHECKS = {"ch17": ch17, "ch19": ch19, "ch27": ch27, "ch34": ch34, "ch35": ch35, "ch36": ch36,
          "ch38": ch38, "ch55": ch55}


# ---------------------------------------------------------------- openmsx
def kind(path, book, new):
    """what a value that differs with another build is about, from its path
    in measC.json and its two values; "other" if it is none of the kinds
    this appendix explains"""
    w = path.split("/")[1:]
    if w[0] == "files" or w[:2] == ["before", "ch55"]:
        return "files"                          # the build's own machine files
    if w[0] == "vdp" and w[-1] in ("latch", "dlatch", "access") and new == "-":
        return "latches"                        # not shown by 17.0 and 18.0's debugger
    if w[0] == "ports" and w[2] == "r2" and w[3] == str(0x91) and (book, new) == (0xFF, 0xFD):
        return "printer"                        # $91 read as $90: the printer ready
    psg_value = {"r1": genC.S1["psg"], "r2": genC.S2["psg"]}
    if (w[0] == "ports" and w[1] == "mirror" and w[2] in psg_value and
            0xA0 <= int(w[3]) <= 0xA7 and (book, new) == (0xFF, psg_value[w[2]])):
        return "psg reads"                      # every port of the PSG's 8 read
    if w[0] == "psg" and pins_counted(w, book, new):
        return "pins 6 and 7"                   # register 15 at $CA reads button A held
    if w[0] == "ppi" and {"tape_seconds", "tape_hz", "tape_range"} & set(w):
        return "tape"                           # the cassette output as recorded
    if w[0] == "sound":
        return "sound"                          # the recording, as each build makes it
    return "other"


def pins_counted(w, book, new):
    """a value of the psg step that differs only where R14 was read with R15 at
    $CA, port 2's pin 6 at 0, and reads $AF, button A held, instead of $BF"""
    at = 32 + len(genC.SELECTS)                 # psg.asm's dirs bytes, from RES
    if w[2:4] == ["facts", "pins67"]:
        return (book, new) == ("ignored", "counted")
    if w[2:4] == ["facts", "dirs"]:
        return int(w[4]) in (3, 5) and (book, new) == (0xBF, 0xAF)
    if w[2] == "cases" and w[-1] == "res":
        a, b = bytes.fromhex(book), bytes.fromhex(new)
        diff = [i for i in range(len(a)) if a[i] != b[i]]
        return bool(diff) and all(pin_byte(i, a[i], b[i]) for i in diff)
    if w[2] == "cases" and w[-1] == "regs":                 # the PSG's registers: R14 as
        a, b = bytes.fromhex(book), bytes.fromhex(new)      # R15 then made it read
        diff = [i for i in range(len(a)) if a[i] != b[i]]
        q = 2 if a[15] & genC.PORT_B else 1
        return diff == [14] and (a[14], b[14]) == (0xBF, 0xBF & ~pins_low(a[15], q))
    return False


def pin_byte(i, book, new):
    """byte I of psg.asm's results, from RES: R14 read in dirs with R15 at $CA, or
    in joy with R15 at one of PINS15, nothing held; NEW is BOOK with the
    buttons whose pins R15 holds at 0 read held"""
    at = 32 + len(genC.SELECTS)
    if i - at in (3, 5):
        return (book, new) == (0xBF, 0xBF & ~pins_low(0xCA, 2))
    k, q = divmod(i - (genC.RES_PSG_JOY - genC.RES), 2)
    if 0 <= k < len(genC.PINS15):
        r15 = genC.PINS15[k] | (genC.PORT_B if q else 0)
        return book == 0xBF and new == 0xBF & ~pins_low(r15, q + 1)
    return False


def openmsx(res):
    """the steps again with every other build, but joy (see joy); each build's
    differences counted by kind()"""
    if not versions.builds():
        res["openmsx"] = {"skipped": "OPENMSX_BUILDS not set"}
        return
    out = versions.every_build(["appC"], [s for s in STEPS if s not in ("joy", "openmsx")],
                               keep=None, values=True)
    for v in out.values():
        kinds = {}
        vals = v.pop("values_of", {})
        for path in v["different"]:
            k = kind(path, *vals[path])
            kinds[k] = kinds.get(k, 0) + 1
        v["different"] = dict(sorted(kinds.items()))
        # the sound's facts: how far each build's tones (Hz) and volumes (against 15) were
        far = {"tones": 0.0, "levels": 0.0}
        for path, (book, new) in vals.items():
            w = path.split("/")
            if w[1] == "sound" and w[3] == "facts":
                far[w[4]] = max(far[w[4]], abs(new - book) if w[4] == "tones" else
                                abs(new / book - 1))
        v["sound_far"] = {k: round(x, 4) for k, x in far.items()}
    res["openmsx"] = out


# ---------------------------------------------------------------- the main
STEPS = ["ports", "start", "vdp", "vdps", "psg", "joy", "ppi", "sound", "keys", "files", "before", "openmsx"]


def main(names=()):
    res = json.loads(OUT_JSON.read_text()) if names and OUT_JSON.exists() else {}
    for name in STEPS:
        if names and name not in names:
            continue
        sub = dict(res)                 # a step sees the steps before it
        globals()[name](sub)
        res[name] = sub[name]
        res = {k: res[k] for k in STEPS if k in res}
        OUT_JSON.write_text(json.dumps(res, indent=1) + "\n")
        print(" ", name, "ok", flush=True)
    return res


if __name__ == "__main__":
    main(sys.argv[1:])
