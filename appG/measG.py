#!/usr/bin/env python3
"""measG.py -- sjasmplus and openMSX, as this book uses them, tried.

    python3 genG.py && ./build.sh && python3 measG.py [step ...]

    help      what sjasmplus 1.24.0 says of itself: its version, and the lines
              of its --help and --help=syntax for the options build.sh uses
    probe     probe.bin against the bytes the directives should give, worked
              out here in Python from what each directive means; the marks of
              probe.lst (+, >, ~, ...) in the lines Listing G.1 prints, and
              the form and the order of probe.sym
    options   the options of build.sh tried on the cases of genG.py, each in a
              temporary folder and with --nologo: what sjasmplus printed, its
              exit status, the files it wrote (even when it failed), the bytes
    messages  the book's own sources that are wrong on purpose (the list
              chapter 15's wall found), assembled again with --syntax=bFw:
              the message of each
    book      every build.sh: how it stops, the --syntax it gives; for every
              option, directive and openMSX command of this appendix, the
              first chapter whose programs use it (a tool counts from the
              chapter that first imports it), each against the chapter this
              file expects; every directive word of the book's sources, and
              that probe.asm uses them all
    start     openMSX started with the options of the book: what the machine
              says it is, which cartridge and tape it holds, what page 2 of
              slot 1 reads with and without -romtype normal
    console   three console sessions on cart.rom, typed by tools/console.py as
              chapter 6's were: two from INIT, with the commands of this
              book's chapters and tools and a few more, and one a second after
              power-on, under C-BIOS's logo, for the probe of the frame
              interrupt; each answer checked against cart.asm and the machine
              (a command that answers nothing, that it does)
    before    the numbers against chapters 5, 6, 15 and 17 and appendix A
    openmsx   start and console again with every other build of openMSX

Writes measG.json and the first two sessions as text (session_a.txt,
session_b.txt).
"""
import ast
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tokenize
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(HERE))
import console     # noqa: E402
import meas        # noqa: E402
import msxcap      # noqa: E402
import probe       # noqa: E402
import versions    # noqa: E402
import genG        # noqa: E402

OUT_JSON = HERE / "measG.json"
SJASM = os.environ.get("SJASMPLUS", "sjasmplus")
BOOK = ["--nologo", "--msg=err", "--syntax=bFw"]          # build.sh's options
EU, JP = "MSXBOOK_EU16", "MSXBOOK_JP16"


def sym(name):
    return probe.sym(HERE / f"{name}.sym")


def run_sjasm(args, files, cwd=None):
    """sjasmplus with ARGS in a temporary folder holding FILES ({name:
    bytes}): (exit status, what it printed, {name: bytes} it wrote)"""
    tmp = Path(tempfile.mkdtemp(prefix="sjG_"))
    try:
        for n, b in files.items():
            (tmp / n).write_bytes(b)
        r = subprocess.run([SJASM, *args], cwd=tmp, capture_output=True, text=True)
        made = {p.name: p.read_bytes() for p in tmp.iterdir() if p.name not in files}
        text = re.sub(r"work time: [0-9.]+ seconds", "work time: … seconds", r.stdout + r.stderr)
        text = text.replace(str(tmp), "DIR")                        # --cleanonerror names it
        return r.returncode, text, made
    finally:
        shutil.rmtree(tmp)


# ---------------------------------------------------------------- help
USED = ["--nologo", "--msg=", "--sym=", "--lst[", "-D<NAME>", "--syntax="]


def help_(res):
    r = subprocess.run([SJASM, "--version"], capture_output=True, text=True)
    version = (r.stdout + r.stderr).strip().splitlines()[0]
    h = subprocess.run([SJASM, "--help"], capture_output=True, text=True)
    lines = (h.stdout + h.stderr).splitlines()
    used = {u: next(l.strip() for l in lines if l.strip().startswith(u)) for u in USED}
    s = subprocess.run([SJASM, "--help=syntax"], capture_output=True, text=True)
    letters = {}
    for l in (s.stdout + s.stderr).splitlines():
        m = re.match(r"^  ([a-zA-Z])(?: ([a-zA-Z]))?\s{2,}(.*)$", l)
        if m:
            letters[m.group(1)] = m.group(3)
            if m.group(2):
                letters[m.group(2)] = m.group(3)
    assert version.startswith("SjASMPlus Z80 Cross-Assembler v1.24.0"), version
    assert {"b", "F", "w"} <= set(letters)
    res["help"] = {"version": version, "options": used,
                   "letters": {k: letters[k] for k in ("b", "F", "w")}}


# ---------------------------------------------------------------- probe
WINDOW = (3, 15)        # the lines of probe.lst that Listing G.1 prints


def expected_probe():
    """probe.bin, byte for byte, from what each directive of probe.asm means:
    built here without sjasmplus"""
    org, out = genG.ORG, []
    out += [1, ord("A"), ord("B"), 0xFF, 0x00, 0x34, 0x12]                     # 3>2 is -1, 3<2 is 0
    out += [0xA0 + k for k in range(genG.DUP_N)]                              # DUP 2, k: k = 0, 1
    fill = -(org + len(out)) % genG.ALIGN_TO                                  # ALIGN: zeros
    out += [0] * fill
    aligned = org + len(out)
    out += [0xBB, 0x77, 0x77]                                                 # db; TWICE $77
    out += [0x34, 0x12, org & 0xFF, org >> 8]                                 # dw $1234, start
    out += [0x78, 0x56, 0x34, 0x12]                                           # dd $12345678
    out += [0x55] * 3                                                         # ds 3, $55
    out += [0xAA] * 2                                                         # DUP 2
    out += [genG.PROBE_INC]                                                   # from probe.inc
    out += [0, 0]                                                             # ds 2: zeros
    out += [0x99] * (-(org + len(out)) % 4)                                   # ALIGN 4, $99
    out += [ord("#")]                                                         # db '#'
    out += [1 + 5]                                                            # COUNT = 1, then + FIVE
    out += [1, 2, 0x34, 0x12]                                                 # p1: the defaults
    out += [7, 8, 0xCD, 0xAB]                                                 # p2 {7, 8, $ABCD}
    out += [4, 2]                                                             # POINT, POINT.w
    out += [genG.DISP_AT & 0xFF, genG.DISP_AT >> 8]                           # DISP: dw moved
    after = org + len(out)
    out += [after & 0xFF, after >> 8]                                         # ENT: dw after
    out += list(genG.BLOB)                                                    # INCBIN
    out += [0xCC]                                                             # IFNDEF
    out += [0x10] * 4 + [0xFF, 5]                                             # $10 #10 0x10 10h 0FFh %101
    out += [0xEE]                                                             # OUTEND: $DD in no file;
    return bytes(out), aligned, after, fill                                   # OUTPUT .., a: $EE added


LST_LINE = re.compile(r"^\s*(\d+)(\+?)\s+([0-9A-F]{4}) (.{12})(.)(.*)$")


def lst_lines(path):
    """an assembler listing as (number, included, address, bytes, mark,
    source) for each line that has a number"""
    out = []
    for l in Path(path).read_text().splitlines():
        m = LST_LINE.match(l.ljust(40))
        if m:
            out.append((int(m.group(1)), m.group(2) == "+", int(m.group(3), 16),
                        m.group(4).strip(), m.group(5), m.group(6).rstrip()))
    return out


def window(path, first, last):
    """the lines of a listing from the one numbered FIRST to the last one
    numbered LAST, in the file itself (included files' lines too)"""
    lines = Path(path).read_text().splitlines()
    nums = [re.match(r"^\s*(\d+)(\+?)\s", l) for l in lines]
    a = next(i for i, m in enumerate(nums) if m and not m.group(2) and int(m.group(1)) == first)
    b = max(i for i, m in enumerate(nums) if m and not m.group(2) and int(m.group(1)) == last)
    return lines[a:b + 1]


def marks(lines):
    """the marks of listing lines: +, >, ~, ... and a line that goes on"""
    rows = [x for x in (LST_LINE.match(l.ljust(40)) for l in lines) if x]
    out = {"included": [], "copied": [], "kept": [], "filled": [], "goes_on": []}
    prev = None
    for m in rows:
        n, inc, src, mark = int(m.group(1)), m.group(2), m.group(6).strip(), m.group(5)
        if inc:
            out["included"].append(n)
        elif mark == ">":
            out["copied"].append(n)
        elif m.group(4).startswith("~"):
            out["kept"].append(n)
        if "..." in m.group(4):
            out["filled"].append(n)
        if prev == (n, inc) and mark != ">" and not src:
            out["goes_on"].append(n)
        prev = (n, inc)
    return out


def bodies(asm):
    """the line numbers of a source between MACRO and ENDM, and between
    STRUCT and ENDS: the lines sjasmplus keeps and does not assemble there"""
    out, inside = set(), False
    for i, l in enumerate(Path(asm).read_text().splitlines(), 1):
        w = (directive_of(l) or "").upper()
        if w in ("ENDM", "ENDS"):
            inside = False
        elif inside and code_of(l).strip():
            out.add(i)
        if w in ("MACRO", "STRUCT"):
            inside = True
    return out


def probe_(res):
    want, aligned, after, fill = expected_probe()
    got = (HERE / "probe.bin").read_bytes()
    assert got == want, (got.hex(), want.hex())
    assert (got[3], got[4]) == (0xFF, 0x00)                     # 3>2 and 3<2
    s = sym("probe")
    assert s["aligned"] == aligned and s["after"] == after and s["moved"] == genG.DISP_AT
    assert s["FIVE"] == 5 and s["COUNT"] == 6 and s["POINT"] == 4 and s["POINT.w"] == 2
    assert s["here"] % 4 == 0 and want[s["here"] - genG.ORG] == ord("#")   # ALIGN 4, then '#'
    assert s["PROBE_INC"] == genG.PROBE_INC and s["k"] == genG.DUP_N - 1   # the counter keeps its last value
    # the marks Listing G.1 shows, in its lines; the same marks in the whole of
    # probe.lst and cart.lst mean the same
    win = marks(window(HERE / "probe.lst", *WINDOW))
    assert all(win.values()), win
    for name in ("probe", "cart"):
        every = marks((HERE / f"{name}.lst").read_text().splitlines())
        src = {n: l for n, inc, _, _, _, l in lst_lines(HERE / f"{name}.lst") if not inc}
        assert all(directive_of(src[n]).upper() in ("ALIGN", "DS") for n in every["filled"]), every
        assert set(every["kept"]) <= bodies(HERE / f"{name}.asm"), (name, every["kept"])
    every = marks((HERE / "probe.lst").read_text().splitlines())
    assert set(every["kept"]) == bodies(HERE / "probe.asm")
    # INCBIN lists no byte: its line is bare, the next starts three bytes on
    rows = [r for r in lst_lines(HERE / "probe.lst") if not r[1]]
    inc = next(i for i, r in enumerate(rows) if r[5].split()[:1] == ["INCBIN"])
    assert rows[inc][3] == "" and rows[inc + 1][2] == rows[inc][2] + len(genG.BLOB)
    syms = (HERE / "probe.sym").read_text().splitlines()
    names = [l.split(":")[0] for l in syms]
    assert all(re.fullmatch(r"[\w.]+: EQU 0x[0-9A-F]{8}", l) for l in syms)
    assert names == sorted(names) and names[0][0].isupper() and names[-1][0].islower()  # by code
    res["probe"] = {"bytes": len(got), "hex": got.hex(), "aligned": aligned, "after": after,
                    "true": got[3], "false": got[4], "align_fill": fill,
                    "window": list(WINDOW), "marks": win, "kept": sorted(every["kept"]),
                    "sym_line": syms[0], "symbols": len(syms), "first_sym": names[0],
                    "last_sym": names[-1], "incbin_line": rows[inc][0]}


# ---------------------------------------------------------------- options
def case(name):
    return {f"{name}.asm": (HERE / "cases" / f"{name}.asm").read_bytes()}


TRIES = (("warn", []), ("warn_err", ["--msg=err"]), ("warn_w", ["--syntax=w"]),
         ("warn_w_err", ["--msg=err", "--syntax=w"]), ("fake", []), ("fake_F", ["--syntax=F"]),
         ("paren", []), ("paren_b", ["--syntax=b"]), ("define", []), ("define_D", ["-DFAST"]),
         ("equ", []), ("value_D", ["-DFAST"]), ("value_D7", ["-DFAST=7"]),
         ("hex", []), ("assert", []), ("paren_clean", ["--syntax=b", "--cleanonerror"]))


def options(res):
    out = {}
    probe_files = {n: (HERE / n).read_bytes() for n in ("probe.asm", "probe.inc", "blob.bin")}
    rc, text, made = run_sjasm(["probe.asm"], probe_files)
    out["plain"] = {"rc": rc, "text": text, "made": sorted(made)}
    rc, text, made = run_sjasm(["--nologo", "probe.asm"], probe_files)
    out["nologo"] = {"rc": rc, "text": text}
    assert out["plain"]["text"].splitlines()[0].startswith("SjASMPlus Z80 Cross-Assembler v1.24.0")
    assert out["plain"]["text"].splitlines()[1:] == text.splitlines()
    for name, args in TRIES:
        src = name.split("_")[0]
        rc, text, made = run_sjasm(["--nologo", *args, f"{src}.asm"], case(src))
        out[name] = {"rc": rc, "text": text, "made": sorted(made),
                     "bin": made.get(f"{src}.bin", b"").hex()}
    rc, text, made = run_sjasm(["--nologo", "--msg=err", "--sym=probe.sym", "--lst=probe.lst",
                                "probe.asm"], probe_files)
    out["files"] = {"rc": rc, "text": text, "made": sorted(made)}
    # -DNOWHERE: the lines IFNDEF leaves out are listed with ~
    rc, text, made = run_sjasm(["--nologo", "--msg=err", "-DNOWHERE", "--lst=probe.lst", "probe.asm"],
                               probe_files)
    src = (HERE / "probe.asm").read_text().splitlines()
    cc = next(i for i, l in enumerate(src, 1) if l.split(";")[0].split() == ["db", "$CC"])
    tmp = Path(tempfile.mkdtemp(prefix="lstG_"))
    try:
        (tmp / "probe.lst").write_bytes(made["probe.lst"])
        kept = marks((tmp / "probe.lst").read_text().splitlines())["kept"]
    finally:
        shutil.rmtree(tmp)
    assert rc == 0 and cc in kept and cc not in marks((HERE / "probe.lst").read_text().splitlines())["kept"]
    out["nowhere"] = {"rc": rc, "line": cc, "kept": kept}
    o = out
    err = lambda k: [l.split(": error: ", 1)[1] for l in o[k]["text"].splitlines() if ": error: " in l]
    assert o["warn"]["rc"] == 0 and "warning: value 0x100 is truncated" in o["warn"]["text"]
    assert o["warn"]["bin"] == "3e00"                                        # LD A,0
    assert o["warn_err"]["rc"] == 0 and o["warn_err"]["text"] == ""          # warnings not shown
    assert o["warn_w"]["rc"] == 1 and err("warn_w") == ["value 0x100 is truncated to 8bit value: 0x00"]
    assert o["warn_w_err"]["text"].strip().splitlines() == [
        "warn.asm(5): error: value 0x100 is truncated to 8bit value: 0x00"]
    assert o["fake"]["rc"] == 0 and o["fake"]["bin"] == "626b" and ": warning" not in o["fake"]["text"]
    assert o["fake_F"]["rc"] == 1 and "Fake instructions are not enabled" in o["fake_F"]["text"]
    assert o["paren"]["rc"] == 0 and o["paren"]["bin"] == "0600"             # LD B,0
    assert "paren.asm(5): warning: value 0xC000 is truncated to 8bit value: 0x00" in o["paren"]["text"]
    assert o["paren_b"]["rc"] == 1 and "can't access memory" in o["paren_b"]["text"]
    assert o["define"]["bin"] == "0201" and o["define_D"]["bin"] == "01"     # -D: as DEFINE
    assert o["equ"]["bin"] == "0201"                                         # IFNDEF sees no EQU
    assert o["value_D"]["rc"] == 1 and err("value_D") == ["Expression expected"]   # empty text
    assert o["value_D7"]["rc"] == 0 and o["value_D7"]["bin"] == "07"
    assert o["hex"]["rc"] == 1 and err("hex") == ["Label not found: FFh"]
    assert o["assert"]["rc"] == 1 and err("assert") == [
        "[ASSERT] Assertion failed:  FIVE == 6, FIVE is not 6", "[ASSERT] Assertion failed:  FIVE == 7"]
    # the output file is written even when sjasmplus fails (chapter 15),
    # unless --cleanonerror asks for it to be deleted
    assert o["paren_clean"]["rc"] == 1 and o["paren_clean"]["made"] == []
    failed = [k for k, _ in TRIES if o[k]["rc"] == 1 and k != "paren_clean"]
    assert all(o[k]["made"] == [f"{k.split('_')[0]}.bin"] for k in failed), {k: o[k]["made"] for k in failed}
    out["written_on_failure"] = {k: len(o[k]["bin"]) // 2 for k in failed}
    # --msg=err keeps DISPLAY's line: it is the program's own message, not the assembler's
    assert o["files"]["made"] == ["probe.bin", "probe.lst", "probe.sym"]
    assert o["files"]["text"] == f"> aligned at 0x{expected_probe()[1]:04X}\n", o["files"]["text"]
    assert o["plain"]["made"] == ["probe.bin"]
    plain = o["plain"]["text"].splitlines()
    assert [l for l in plain if l.startswith("Pass ")] == [
        "Pass 1 complete (0 errors)", "Pass 2 complete (0 errors)", "Pass 3 complete"]  # three times
    assert f"> aligned at 0x{expected_probe()[1]:04X}" in plain                          # DISPLAY
    assert sum(l.startswith("include data: name=blob.bin") for l in plain) == 1, plain   # INCBIN
    res["options"] = out


# ---------------------------------------------------------------- messages
# the sources chapter 15's wall found wrong on purpose
BROKEN = ["ch04/case.asm", "ch05/margin.asm", "ch05/typo.asm", "ch07/fake.asm", "ch08/paren.asm",
          "ch15/big.asm", "ch15/fits.asm"]


def own_build(folder, name):
    """the options build.sh of FOLDER gives sjasmplus for NAME, or None if
    it does not assemble it"""
    stem = name[:-4]
    lines = (REPO / folder / "build.sh").read_text().splitlines()
    loop = None
    for l in lines:
        m = re.match(r"\s*for f in (.*); do", l)
        if m:
            loop = m.group(1).split()
            continue
        if "sjasmplus " in l and not l.lstrip().startswith("#"):
            words = l.split("||")[0].split()[1:]
            if name in words or (loop and stem in loop and "$f.asm" in words):
                return [w for w in words if w.startswith("-") and not w.startswith(("--sym", "--lst"))]
        if l.strip() == "done":
            loop = None
    return None


def messages(res):
    out = {}
    for path in BROKEN:
        folder, name = path.split("/")
        files = {p.name: p.read_bytes() for p in (REPO / folder).iterdir()
                 if p.is_file() and p.suffix in (".asm", ".inc", ".bin")}
        rc, text, _ = run_sjasm([*BOOK, name], files)
        first = next(l for l in text.splitlines() if ": error: " in l)
        own = own_build(folder, name)
        out[path] = {"rc": rc, "message": first.split(": error: ", 1)[1], "line": first, "own": own,
                     "errors": sum(": error: " in l for l in text.splitlines())}
        if own is not None:
            out[path]["own_rc"] = run_sjasm([*own, name], files)[0]
            out[path]["own_warnings"] = sum(": warning" in l for l in run_sjasm(
                [*[o for o in own if o != "--msg=err"], name], files)[1].splitlines())
        assert rc == 1, path
    w15 = json.loads((REPO / "ch15" / "meas15.json").read_text())["wall"]["failed"]
    assert sorted(w15) == sorted(BROKEN)
    assert all("error: " + out[p]["message"] == w15[p] for p in BROKEN), (out, w15)
    # four are built in their own chapter, where they assemble
    built = [p for p in BROKEN if out[p]["own"] is not None]
    assert built == ["ch07/fake.asm", "ch08/paren.asm", "ch15/big.asm", "ch15/fits.asm"], built
    assert all(out[p]["own_rc"] == 0 for p in built)
    res["messages"] = out


# ---------------------------------------------------------------- book
Z80 = set("""adc add and bit call ccf cp cpd cpdr cpi cpir cpl daa dec di djnz ei ex exx halt im in
inc ind indr ini inir jp jr ld ldd lddr ldi ldir neg nop or otdr otir out outd outi pop push res
ret reti retn rl rla rlc rlca rld rr rra rrc rrca rrd rst sbc scf set sla sll sl1 sli sra srl sub
xor""".split())


def folders(appendices=True):
    """the chapters' folders in the book's order, then the appendices'
    (this one left out)"""
    ds = [d for d in REPO.iterdir() if d.is_dir() and re.fullmatch(r"ch\d\d|app[A-F]", d.name)]
    ds = sorted(ds, key=lambda d: (d.name.startswith("app"), d.name))
    return ds if appendices else [d for d in ds if d.name.startswith("ch")]


def code_of(line):
    line = line.replace("af'", "af").replace("AF'", "AF")
    return re.sub(r'"[^"]*"|\'[^\']*\'', '""', line).split(";")[0]


def directive_of(line):
    """the directive or instruction of a source line: its first word, or
    the word after a label (a label that begins the line, or one glued to
    it with a colon, as in g_INC16:db 6)"""
    code = code_of(line)
    words = code.split()
    if not words:
        return None
    if code[0] not in " \t":
        head, colon, rest = words[0].partition(":")
        if colon and rest:
            return rest
        words = words[1:]
    return words[0] if words else None


def operands_of(line):
    code = code_of(line)
    d = directive_of(line)
    return code.split(d, 1)[1].strip() if d else ""


def census(paths):
    """every directive word of these sources, in lower case, with the form a
    few of them take: {form: (file, line number, line)} for the first
    line of each; a macro's name counts as <macro>, a structure's as
    <struct>, and the Z80's instructions are left out"""
    texts = [(p, p.read_text(errors="replace").splitlines()) for p in paths]
    macros, structs = set(), set()
    for _, lines in texts:
        for l in lines:
            d = (directive_of(l) or "").upper()
            if d in ("MACRO", "STRUCT"):
                (macros if d == "MACRO" else structs).add(operands_of(l).split()[0].upper())
    out = {}
    for p, lines in texts:
        for i, l in enumerate(lines, 1):
            d = directive_of(l)
            if not d or not re.fullmatch(r"[A-Za-z_][\w.]*|=", d) or d.lower() in Z80:
                continue
            ops = operands_of(l)
            form = ("<macro>" if d.upper() in macros else
                    "<struct> {...}" if d.upper() in structs and ops.startswith("{") else
                    "<struct>" if d.upper() in structs else d.lower())
            if form in ("dup", "ds", "align", "assert"):         # with one operand, or two
                form += " n" if "," not in ops else " n, m"
            if form == "output" and re.fullmatch(r'""\s*,\s*a', ops):
                form = "output ..., a"
            if form == "db":                                     # strings in either quote
                raw = l.split(";")[0]
                form = "db '...'" if "'" in raw else 'db "..."' if '"' in raw else "db"
                out.setdefault("db", (p, i, l.rstrip()))
            out.setdefault(form, (p, i, l.rstrip()))
    return out


def program_lines(path):
    """(number, text) of the lines of a program that are code: a Python
    file's docstrings and comments left out, a shell's or Tcl's comments"""
    text = path.read_text(errors="replace")
    lines = text.splitlines()
    if path.suffix != ".py":
        return [(i, l) for i, l in enumerate(lines, 1) if not l.lstrip().startswith("#")]
    drop, cut = set(), {}
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            b = node.body
            if b and isinstance(b[0], ast.Expr) and isinstance(b[0].value, ast.Constant) \
                    and isinstance(b[0].value.value, str):
                drop.update(range(b[0].lineno, b[0].end_lineno + 1))
    for t in tokenize.generate_tokens(io.StringIO(text).readline):
        if t.type == tokenize.COMMENT:
            cut[t.start[0]] = t.start[1]
    return [(i, l[:cut.get(i, len(l))]) for i, l in enumerate(lines, 1)
            if i not in drop and l[:cut.get(i, len(l))].strip()]


def programs(folder):
    return sorted(folder.glob("*.py")) + sorted(folder.glob("*.tcl")) + sorted(folder.glob("build.sh"))


def tool_chapters():
    """{tool: the first chapter whose programs import it}"""
    out = {}
    for t in sorted((REPO / "tools").glob("*.py")):
        pat = re.compile(rf"^\s*(import {t.stem}\b|from {t.stem} import)")
        out[t.name] = next((d.name for d in folders(False) for f in programs(d)
                            if any(pat.match(l) for _, l in lines_of(f))), None)
    return out


def first_use(pattern, tools):
    """the first chapter whose programs, or a tool it brought in, match
    PATTERN: (chapter folder, file, line number, line), or None"""
    rx = re.compile(pattern)
    order = {d.name: k for k, d in enumerate(folders())}
    hits = []
    for t, ch in tools.items():
        hit = next(((i, l) for i, l in lines_of(REPO / "tools" / t) if rx.search(l)), None)
        if ch and hit:
            hits.append((order[ch], ch, f"tools/{t}", hit[0], hit[1].strip()))
    for d in folders():
        hit = next(((f, i, l) for f in programs(d) for i, l in lines_of(f) if rx.search(l)), None)
        if hit:
            hits.append((order[d.name], d.name, f"{d.name}/{hit[0].name}", hit[1], hit[2].strip()))
            break
    return min(hits)[1:] if hits else None


_LINES = {}


def lines_of(path):
    if path not in _LINES:
        _LINES[path] = program_lines(path)
    return _LINES[path]


# sjasmplus: an option, the pattern of its use, the chapter that first uses it
OPTION_USE = {"--nologo": (r"--nologo", "ch01"), "--msg=err": (r"--msg=err", "ch01"),
              "--sym": (r"--sym=", "ch01"), "--lst": (r"--lst=", "ch02"),
              "b": (r"--syntax=[A-Za-z]*b", "ch08"), "F": (r"--syntax=[A-Za-z]*F", "ch07"),
              "w": (r"--syntax=[A-Za-z]*w", "ch15"), "-D": (r"""["']-D[A-Z_]+(=\w+)?["']""", "ch15"),
              "-D=": (r"""["']-D[A-Z_]+=\w""", "")}
ROMTYPES = {"normal": "ch03", "ascii16": "ch48", "ascii8": "ch48", "konami": "ch48",
            "konamiscc": "ch48", "page12": "ch56"}
# openMSX: a command or an option of this appendix, the pattern of its use,
# and the chapter that first uses it ("" for none: this appendix)
OPENMSX_USE = {
    "-machine": (r"-machine", "ch01"), "-carta": (r"-carta", "ch01"),
    "-romtype": (r"-romtype", "ch03"), "-script": (r"-script", "ch01"),
    "-cassetteplayer": (r"-cassetteplayer", "ch50"),
    "reg pc": (r"\breg pc\b", "ch03"), "cpuregs": (r"\bcpuregs\b", "ch06"),
    "disasm": (r"\bdisasm\b", "ch06"), "step_in": (r"\bstep_in\b", "ch06"),
    "debug set_bp": (r"debug set_bp\b", "ch01"), "debug list_bp": (r"debug list_bp", ""),
    "debug cont": (r"debug cont\b", "ch06"), "step_over": (r"\bstep_over\b", "ch06"),
    "debug remove_bp": (r"debug remove_bp\b", "ch07"),
    "peek": (r"""[\["'{;]\s*peek """, "ch16"), "peek16": (r"\bpeek16\b", "ch12"), "vpeek": (r"\bvpeek\b", ""),
    "poke": (r"(?<![\w.\"])poke (0x|\$)", ""),
    "debug read": (r"debug read\b(?!_)", "ch01"), "debug write": (r"debug write\b(?!_)", "ch06"),
    "debug read_block": (r"debug read_block\b", "ch01"),
    "keymatrixdown": (r"\bkeymatrixdown\b", "ch03"), "keymatrixup": (r"\bkeymatrixup\b", "ch16"),
    "machine_info time": (r"machine_info time\b", "ch01"),
    "machine_info VDP_frame_count": (r"machine_info VDP_frame_count\b", "ch01"),
    "machine_info VDP_cycle_in_frame": (r"machine_info VDP_cycle_in_frame\b", "ch05"),
    "debug probe list": (r"debug probe list\b", ""),
    "debug probe set_bp": (r"debug probe set_bp\b", "ch17"),
    "debug probe remove_bp": (r"debug probe remove_bp\b", ""),
    "debug set_watchpoint": (r"debug set_watchpoint\b", "ch05"),
    "debug list_watchpoints": (r"debug list_watchpoints\b", ""),
    "debug remove_watchpoint": (r"debug remove_watchpoint\b", "ch51"),
    "wp_last_value": (r"wp_last_value\b", "ch20"),
    "after time": (r"\bafter time\b", "ch01"), "after frame": (r"\bafter frame\b", "ch01"),
    "record start": (r"record start\b", "ch01"), "screenshot": (r"\bscreenshot\b", ""),
    "reset": (r"""["'{\[;]\s*reset\s*["'}\];]""", "ch06"),
    "set speed": (r"\bset speed\b", "ch01"), "[set speed]": (r"\[set speed\]", "")}


def book(res):
    out = {}
    # every build.sh: how it stops, the --syntax of each sjasmplus line
    stops, syntax = {}, {}
    for d in folders():
        lines = [l for _, l in program_lines(d / "build.sh")]
        calls = [l for l in lines if l.lstrip().startswith("sjasmplus ")]
        stops[d.name] = ("set -e" if "set -e" in lines else
                         "|| exit 1" if all(l.rstrip().endswith("|| exit 1") for l in calls) else None)
        syntax[d.name] = sorted({(re.findall(r"--syntax=(\w+)", l) or [""])[0] for l in calls})
        assert calls and stops[d.name], d.name
        assert all("--nologo --msg=err" in l for l in calls), d.name
    out["build_stops"], out["build_syntax"] = stops, syntax
    both = {d.name: all("--sym=" in l and "--lst=" in l for _, l in lines_of(d / "build.sh")
                        if l.lstrip().startswith("sjasmplus ")) for d in folders()}
    names = [d.name for d in folders()]
    out["sym_lst_from"] = next(n for k, n in enumerate(names) if all(both[x] for x in names[k:]))
    # the options, and the plain run of chapter 5
    tools = tool_chapters()
    out["tools"] = tools
    uses = {}
    for name, (pat, want) in OPTION_USE.items():
        hit = first_use(pat, tools)
        assert (hit[0] if hit else "") == want, (name, hit, want)
        uses[name] = list(hit) if hit else None
    shown = [d.name for d in folders(False) for t in sorted(d.glob("*_out.txt"))
             if t.read_text().startswith("SjASMPlus Z80 Cross-Assembler")]
    assert shown[0] == "ch05", shown
    uses["plain"] = [shown[0], "ch05/border_out.txt", 1, ""]
    out["options"] = uses
    # openMSX's commands and options
    used = {}
    for name, (pat, want) in OPENMSX_USE.items():
        hit = first_use(pat, tools)
        assert (hit[0] if hit else "") == want, (name, hit, want)
        used[name] = list(hit) if hit else None
    out["openmsx"] = used
    # every directive word of the book's sources, and probe.asm's
    srcs = [f for d in folders() for f in sorted(d.glob("*.asm")) + sorted(d.glob("*.inc"))
            if f"{d.name}/{f.name}" != "ch05/margin.asm"]          # an instruction read as a label
    book_forms = census(srcs)
    probe_forms = census([HERE / "probe.asm", HERE / "probe.inc"])
    missing = sorted(set(book_forms) - set(probe_forms))
    assert not missing, missing
    out["directives"] = {k: [f"{p.parent.name}/{p.name}", i, l] for k, (p, i, l) in book_forms.items()}
    out["probe_only"] = sorted(set(probe_forms) - set(book_forms))
    # the -romtype values and the machines the book's programs use
    out["romtypes"] = {}
    for v, want in ROMTYPES.items():
        hit = first_use(rf"""["']{v}["']""", tools)
        assert hit and hit[0] == want, (v, hit, want)
        out["romtypes"][v] = list(hit)
    out["machines"] = {}
    for m in sorted(p.stem for p in (REPO / "machines").glob("*.xml")):
        hit = first_use(rf"\b{m}\b", tools)
        assert hit, m
        out["machines"][m] = hit[0]
    assert msxcap.DEFAULT_MACHINE == EU and console.session.__defaults__[1] == EU
    res["book"] = out


# ---------------------------------------------------------------- start
START_TCL = ('L "cfg [machine_info config_name]"; L "cart [carta]"; '
             'L "page2 [debug read {slotted memory} [expr {0x40000 + 0x8000}]]"; '
             'L "page1 [debug read {slotted memory} [expr {0x40000 + 0x4000}]]"; '
             'L "tape [cassetteplayer]"')


def start(res):
    out = {}
    tape = str((HERE / "tape.wav").resolve())
    for tag, machine, extra in (("eu", EU, []), ("jp", JP, []), ("normal", EU, ["-romtype", "normal"]),
                                ("tape", EU, ["-cassetteplayer", tape])):
        lines = msxcap.run_tcl(HERE / "cart.rom", 1, START_TCL, machine=machine, extra_args=extra)
        got = {l.split(" ", 1)[0]: l.split(" ", 1)[1] if " " in l else "" for l in lines
               if l.split(" ", 1)[0] in ("cfg", "cart", "page1", "page2", "tape")}
        got["cart"] = os.path.basename(got["cart"].split(": ", 1)[1])
        got["tape"] = got["tape"].replace(tape, "tape.wav")
        out[tag] = got
    # -script: the file runs as openMSX starts, before the MSX has run at all
    home = msxcap.make_home()
    try:
        log = home / "script.log"
        (home / "first.tcl").write_text(f"set f [open {{{log}}} w]\n"
                                        "puts $f \"[machine_info time] [reg pc]\"\nclose $f\nexit\n")
        msxcap.run_openmsx(HERE / "cart.rom", EU, home / "first.tcl", home, 120)
        t0, pc0 = log.read_text().split()
    finally:
        shutil.rmtree(home, ignore_errors=True)
    assert float(t0) == 0 and int(pc0) == 0, (t0, pc0)
    out["script"] = {"time": float(t0), "pc": int(pc0)}
    assert out["eu"]["cfg"] == EU and out["jp"]["cfg"] == JP
    assert all(v["cart"] == "cart.rom" for k, v in out.items() if k != "script")
    assert out["eu"]["page2"] == out["eu"]["page1"] == str(ord("A"))      # the cartridge, again
    assert out["normal"]["page2"] == "255" and out["normal"]["page1"] == str(ord("A"))
    assert out["eu"]["tape"] == "cassetteplayer: {} stop" and out["tape"]["tape"] == \
        "cassetteplayer: tape.wav play"
    res["start"] = out


# ---------------------------------------------------------------- console
RAM_AT, RAM_BYTE = 0xE123, 0xA5         # session b's byte, poked before the reset


def session_a(s, film, shot):
    call = s["back"] - 3
    return ["reg pc", "cpuregs", "disasm", "step_in", "reg pc",
            f"set bp [debug set_bp 0x{call:04X}]", "debug list_bp", "debug cont", "reg pc",
            "step_over", "reg pc", "reg b", "debug remove_bp $bp",
            "peek 0x4000", "peek16 0x0004", "vpeek 0x1800",
            "debug read {VDP regs} 7", "debug write {VDP regs} 7 1", "debug read {VDP regs} 7",
            "binary encode hex [debug read_block memory 0x4000 4]",
            "keymatrixdown 8 0x01", "debug read keymatrix 8", "keymatrixup 8 0x01",
            "debug read keymatrix 8",
            "machine_info time", "machine_info VDP_frame_count", "machine_info VDP_cycle_in_frame",
            "debug probe list", "set p [debug probe set_bp VDP.IRQvertical]", "debug cont",
            "machine_info VDP_cycle_in_frame", "reg pc", "debug probe remove_bp $p", "set speed",
            "after time 0.1 {debug break}", f"record start -videoonly {film}", "debug cont",
            "record stop", f"file exists {film}", f"screenshot {shot}", f"file exists {shot}",
            "set ::f0 [machine_info VDP_frame_count]",
            "after frame {set ::f1 [machine_info VDP_frame_count]; debug break}", "debug cont",
            "expr {$::f1 - $::f0}"]


def session_b():
    return ["machine_info time",
            "debug set_watchpoint write_io 0x99", "debug list_watchpoints", "debug cont", "reg pc",
            "debug remove_watchpoint wp#1", "set ::seen {}",
            "proc seen {} {lappend ::seen [format %02X $::wp_last_value]}",
            "debug set_watchpoint write_io 0x99 {} seen",
            "after time 0.1 {debug break}", "debug cont", "set ::seen",
            f"peek 0x{RAM_AT:04X}", f"poke 0x{RAM_AT:04X} 0x{RAM_BYTE:02X}",
            "after time 0.1 reset", "debug cont", "reg pc", f"peek 0x{RAM_AT:04X}",
            "machine_info time"]


def session_c():
    """C-BIOS's logo, a second after power-on, its interrupt handler at work:
    the probe stops when the signal rises and when the handler's read of the
    status lets it fall"""
    return ["set p [debug probe set_bp VDP.IRQvertical]",
            "debug cont", "debug probe read VDP.IRQvertical", "machine_info VDP_cycle_in_frame",
            "debug cont", "debug probe read VDP.IRQvertical", "machine_info VDP_cycle_in_frame",
            "peek16 [expr {[reg pc] - 2}]"]


class Answers:
    """a session's answers, each read by a check: at the end no line is left
    that no check read"""

    def __init__(self, ses):
        self.ses, self.read = ses, set()

    def __call__(self, line, k=0):
        i = [i for i, (l, _, _) in enumerate(self.ses) if l == line][k]
        self.read.add(i)
        return self.ses[i][1]

    def every(self, line):
        idx = [i for i, (l, _, _) in enumerate(self.ses) if l == line]
        assert idx, line
        self.read.update(idx)
        return [self.ses[i][1] for i in idx]

    def quiet(self, *lines):
        for line in lines:
            assert all(x == "" for x in self.every(line)), (line, self.every(line))

    def done(self):
        left = [self.ses[i][0] for i in range(len(self.ses)) if i not in self.read]
        assert not left, left


REGS = ["AF", "BC", "DE", "HL", "AF'", "BC'", "DE'", "HL'", "IX", "IY", "PC", "SP",
        "I", "R", "IM", "IFF"]


def console_(res):
    s = sym("cart")
    rom = HERE / "cart.rom"
    image = rom.read_bytes()
    tmp = Path(tempfile.mkdtemp(prefix="conG_"))
    try:
        film, shot = tmp / "film.avi", tmp / "shot.png"
        a = console.session(rom, session_a(s, film, shot), timeout=200)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    b = console.session(rom, session_b(), timeout=200)
    c = [list(x) for x in console.session(rom, session_c(), start=("time", 1.0), timeout=200)]
    a = [[l.replace(str(tmp), "DIR"), (x or "").replace(str(tmp), "DIR"), e] for l, x, e in a]
    # an after's name counts every after since the machine started, the
    # tools' own too: it says nothing about the command
    a, b = ([[l, re.sub(r"^after#\d+$", "after#…", x or ""), e] for l, x, e in ses] for ses in (a, b))
    assert not any(e for _, _, e in a + b), [x for x in a + b if x[2]]
    (HERE / "session_a.txt").write_text(console.transcript([tuple(x) for x in a]))
    (HERE / "session_b.txt").write_text(console.transcript([tuple(x) for x in b]))
    A, B = Answers(a), Answers(b)
    init, call, back, stop = s["init"], s["back"] - 3, s["back"], s["stop"]
    lst = (HERE / "cart.lst").read_text()
    outs = [int(m.group(1), 16) for m in re.finditer(r"^\s*\d+\+?\s+([0-9A-F]{4}) D3 99", lst, re.M)]
    # -------- session a: the CPU
    pcs = [int(x) for x in A.every("reg pc")]
    assert pcs == [init, init + 1, call, back, stop], pcs   # DI is one byte; over the CALL; JR
    regs = dict(re.findall(r"(\S+?)\s*=\s*([0-9A-F]+)", A("cpuregs")))
    assert list(regs) == REGS and int(regs["PC"], 16) == init and regs["IFF"] == "00", regs
    dis = [l.split() for l in A("disasm").splitlines()]
    assert len(dis) == 8 and dis[0][1] == "di"
    at = init
    for row in dis:                       # each line: the address, the instruction, its bytes
        n = sum(1 for w in row if re.fullmatch(r"[0-9A-F]{2}", w))
        assert int(row[0], 16) == at and bytes.fromhex("".join(row[-n:])) == \
            image[at - 0x4000:at - 0x4000 + n], row
        at += n
    A.quiet("step_in", "step_over", "debug cont", "debug remove_bp $bp",
            "debug write {VDP regs} 7 1", "keymatrixdown 8 0x01", "keymatrixup 8 0x01",
            "debug probe remove_bp $p", "record stop")
    assert A("after time 0.1 {debug break}") == "after#…"
    assert A("record start -videoonly DIR/film.avi") == "Recording to DIR/film.avi"
    assert A("file exists DIR/film.avi") == A("file exists DIR/shot.png") == "1"
    assert A("screenshot DIR/shot.png") in ("DIR/shot.png", "")      # 21.0: nothing
    assert A(f"set bp [debug set_bp 0x{call:04X}]") == "bp#2"            # console.py's is bp#1
    bps = A("debug list_bp").strip().splitlines()
    assert len(bps) == 2 and re.fullmatch(rf"bp#1 (0x{init:04x}|{init}) \{{\}} \{{debug break\}}", bps[0]) \
        and bps[1] == f"bp#2 0x{call:04x} {{}} {{debug break}}", bps
    assert A("reg b") == "0"                                            # sub ran: its DJNZ to 0
    # -------- session a: memory, the VDP, the keys
    assert A("peek 0x4000") == str(image[0])                            # the A of "AB"
    cg = json.loads((REPO / "ch02" / "meas02.json").read_text())["cgtabl"][EU]
    assert int(A("peek16 0x0004")) == int(cg, 16)                       # CGTABL: chapter 2
    assert A("vpeek 0x1800") == str(genG.VRAM_BYTE)
    assert A.every("debug read {VDP regs} 7") == [str(s["LIGHT_GREEN"]), "1"]
    assert A("binary encode hex [debug read_block memory 0x4000 4]") == image[:4].hex()
    assert A.every("debug read keymatrix 8") == [str(0xFF ^ 0x01), "255"]
    # -------- session a: time
    t, frames = float(A("machine_info time")), int(A("machine_info VDP_frame_count"))
    cyc0, cyc = (int(x) for x in A.every("machine_info VDP_cycle_in_frame"))
    tf = meas.T_PER_FRAME[EU]
    assert 6 * meas.T_PER_LINE * meas.LINES_PER_FRAME[EU] == 6 * tf      # six VDP cycles a T-state
    late = t * probe.CLOCK - (frames * tf + cyc0 / 6)                   # T-states
    assert abs(late) < 1e-3, late                                     # exactly, to the T-state
    pl = A("debug probe list").split()
    assert "VDP.IRQvertical" in pl and "z80.acceptIRQ" in pl
    assert A("set p [debug probe set_bp VDP.IRQvertical]") == "pp#1"
    assert float(A("set speed")) == 100                                 # console.py sets none
    f0 = int(A("set ::f0 [machine_info VDP_frame_count]"))
    assert f0 > frames and A("after frame {set ::f1 [machine_info VDP_frame_count]; debug break}") \
        == "after#…" and A("expr {$::f1 - $::f0}") == "1"                # the next frame
    A.done()
    # -------- session b
    t0, t1 = (float(x) for x in B.every("machine_info time"))
    assert t1 == t0 or t1 > t0 + 0.2, (t0, t1)         # 19.1 counts again from 0; 21.0 goes on
    assert B.every("debug set_watchpoint write_io 0x99") == ["wp#1"]
    assert B("debug set_watchpoint write_io 0x99 {} seen") == "wp#2"
    assert re.fullmatch(r"wp#1 write_io 0x0*99 \{\} \{debug break\}", B("debug list_watchpoints").strip())
    B.quiet("debug cont", "debug remove_watchpoint wp#1", "set ::seen {}",
            "proc seen {} {lappend ::seen [format %02X $::wp_last_value]}",
            f"poke 0x{RAM_AT:04X} 0x{RAM_BYTE:02X}")
    pcs = [int(x) for x in B.every("reg pc")]
    assert pcs == [outs[0] + 2, init], (pcs, outs)       # after the first OUT; INIT, after reset
    assert B.every("after time 0.1 {debug break}") == B.every("after time 0.1 reset") == ["after#…"]
    seen = B("set ::seen").split()
    assert seen == [f"{0x80 | 7:02X}", f"{genG.VRAM_AT & 0xFF:02X}",
                    f"{genG.VRAM_AT >> 8 | 0x40:02X}"], seen  # R#7's second byte, the address
    before_, after_ = (int(x) for x in B.every(f"peek 0x{RAM_AT:04X}"))
    assert before_ != RAM_BYTE and after_ == RAM_BYTE                   # reset keeps the RAM
    B.done()
    # -------- session c
    C = Answers(c)
    C.quiet("debug cont")
    assert C("set p [debug probe set_bp VDP.IRQvertical]") == "pp#1"
    assert C.every("debug probe read VDP.IRQvertical") == ["1", "0"]
    up, down = (int(x) for x in C.every("machine_info VDP_cycle_in_frame"))
    assert down > up and int(C("peek16 [expr {[reg pc] - 2}]")) == 0x99DB    # after IN A,($99)
    C.done()
    res["console"] = {"a": a, "b": b, "c": c, "up": up, "down": down, "irq_cycle": cyc, "init": init, "call": call, "back": back,
                      "stop": stop, "first_out": outs[0], "late": late, "ram_before": before_,
                      "time_at_init": t0, "time_after_reset": t1}


# ---------------------------------------------------------------- before
def before(res):
    out = {}
    c = res["console"]
    # chapter 6: the same registers at INIT, the same disassembly, the
    # watchpoint after the same OUT
    m6 = json.loads((REPO / "ch06" / "meas06.json").read_text())
    regs = dict(re.findall(r"(\S+?)\s*=\s*([0-9A-F]+)", next(x for l, x, _ in c["a"] if l == "cpuregs")))
    assert regs == m6["stop"]["registers"], (regs, m6["stop"]["registers"])
    out["ch06_registers"] = len(regs)
    dis = next(x for l, x, _ in c["a"] if l == "disasm").splitlines()
    d6 = next(x for l, x, _ in m6["stop"]["session"] if l == "disasm").splitlines()
    assert len(dis) == len(d6) == m6["stop"]["disasm_lines"], (len(dis), len(d6))
    same = next(k for k in range(len(dis) + 1) if k == len(dis) or dis[k] != d6[k])
    assert same == 5, (dis, d6)                     # VDP_REG 7: the two cartridges begin alike
    out["ch06_disasm_lines"], out["ch06_disasm_same"] = len(dis), same
    w6 = int(next(a for l, a, _ in m6["watch"]["session"] if l == "reg pc"))
    assert w6 == int(next(x for l, x, _ in c["b"] if l == "reg pc"))
    out["ch06_watch"] = w6
    # chapter 15: the truncation warning
    m15 = json.loads((REPO / "ch15" / "meas15.json").read_text())
    fits = next(r for r in m15["fits"]["rows"] if r["src"] == "ld a,256")
    assert fits["warning"] in res["options"]["warn"]["text"]
    out["ch15_fits"] = fits["warning"]
    # chapter 17: the frame interrupt's signal, in VDP cycles; the probe stops
    # the machine at the end of the instruction the signal came in: stop's
    # JR, 13 T-states on the MSX (appendix A)
    sig = json.loads((REPO / "ch17" / "meas17.json").read_text())["signal"][EU]["cycle"]
    jr = next(r for r in json.loads((REPO / "appA" / "measA.json").read_text())["table"]
              if r["form"] == "JR e")
    assert jr["t"] == "13" and jr["zilog"] == "12"
    assert 0 <= c["irq_cycle"] - sig < 13 * 6, (c["irq_cycle"], sig)
    assert 0 <= c["up"] - sig < 25 * 6, (c["up"], sig)        # an instruction of C-BIOS's, at most 25
    out["irq_cycle"], out["ch17_signal"], out["jr_t"] = c["irq_cycle"], sig, int(jr["t"])
    # chapter 5: the same lines of a plain run
    b5 = (REPO / "ch05" / "border_out.txt").read_text().splitlines()
    plain = res["options"]["plain"]["text"].splitlines()
    shape = lambda ls: [re.sub(r"\d+", "N", l.split(",")[0]) for l in ls
                        if not l.startswith(("include", ">"))]
    assert shape(b5) == shape(plain), (b5, plain)
    out["ch05_lines"] = len(b5)
    res["before"] = out


# ---------------------------------------------------------------- openmsx
def openmsx(res):
    if not versions.builds():
        res["openmsx"] = {"skipped": "OPENMSX_BUILDS not set"}
        return
    import hashlib
    roms = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()[:16] for p in sorted(HERE.glob("*.rom"))}
    out = versions.every_build(["appG"], ["start", "console"], keep=None, values=True)
    res["openmsx"] = {"roms": roms, **out}


# ---------------------------------------------------------------- the main
STEPS = ["help", "probe", "options", "messages", "book", "start", "console", "before", "openmsx"]
RUN = {"help": help_, "probe": probe_, "options": options, "messages": messages, "book": book,
       "start": start, "console": console_, "before": before, "openmsx": openmsx}


def main(names=()):
    res = json.loads(OUT_JSON.read_text()) if names and OUT_JSON.exists() else {}
    for name in STEPS:
        if names and name not in names:
            continue
        sub = json.loads(json.dumps(res))      # a step sees the steps before it, as saved
        RUN[name](sub)
        res[name] = json.loads(json.dumps(sub[name]))
        res = {k: res[k] for k in STEPS if k in res}
        OUT_JSON.write_text(json.dumps(res, indent=1) + "\n")
        print(" ", name, "ok", flush=True)
    return res


if __name__ == "__main__":
    main(sys.argv[1:])
