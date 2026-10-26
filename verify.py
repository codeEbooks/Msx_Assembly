#!/usr/bin/env python3
"""verify.py - reassemble every program in the book and compare, byte for byte.

    python3 verify.py            every chapter folder
    python3 verify.py ch01       one chapter

For each source in a chapter folder, the assembler is run in a temporary
folder and the cartridge it writes (the file named by OUTPUT) is compared with
the one in the repository -- the bytes that were photographed for the book.
The assembler is looked for on the PATH; its version is printed next to the
one the book was built with, because a different assembler is a different
experiment.

A source whose first line says it "does not assemble, on purpose" is one of
the book's mistakes (chapter 5's typo.asm): the assembler must refuse it, and
nothing is compared.

Chapter 56's EPROM images are not assembled: pack56.py makes them from two of
its cartridges, which are compared first. They are checked against what they
must be, made here from those cartridges: lantern_keep_a14.bin is
lantern_keep.rom with its two halves of 16 KB the other way round, and
grin_alley_x2.bin is grin_alley.rom twice.
"""
import glob
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
BOOK_SJASMPLUS = "1.24.0"


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def outputs_of(src):
    """the files a source writes: its OUTPUT directives"""
    out = []
    for line in open(src):
        code = line.split(";")[0]
        m = re.search(r'\bOUTPUT\s+"([^"]+)"', code, re.I)
        if m and m.group(1) not in out:     # a MegaROM opens its file once a bank (chapter 48)
            out.append(m.group(1))
    return out


# images made from a chapter's cartridges: (image, cartridge, how)
DERIVED = {"ch56": [("lantern_keep_a14.bin", "lantern_keep.rom", "halves swapped"),
                    ("grin_alley_x2.bin", "grin_alley.rom", "twice")]}


def derived(data, how):
    half = len(data) // 2
    return data[half:] + data[:half] if how == "halves swapped" else data + data


def main(chapters):
    try:
        v = subprocess.run(["sjasmplus", "--version"], capture_output=True, text=True)
    except FileNotFoundError:
        print("sjasmplus: not found on the PATH")
        return 1
    text = v.stdout + v.stderr
    ver = text.split(" v")[1].split()[0] if " v" in text else "missing"
    print(f"sjasmplus {ver} (the book: {BOOK_SJASMPLUS})")
    bad = total = refused = 0
    for ch in chapters:
        folder = os.path.join(ROOT, ch)
        for src in sorted(glob.glob(os.path.join(folder, "*.asm"))):
            outs = outputs_of(src)
            if not outs:
                continue
            broken = "does not assemble, on purpose" in open(src).readline()
            work = tempfile.mkdtemp(prefix="verify-")
            try:
                for f in glob.glob(os.path.join(folder, "*")):
                    if f.endswith((".asm", ".inc", ".bin")):
                        shutil.copy(f, work)
                ok = subprocess.run(["sjasmplus", "--nologo", "--msg=err", os.path.basename(src)],
                                    cwd=work, capture_output=True).returncode == 0
                if broken:
                    refused += 1
                    bad += ok
                    print(f"  {'DIFF' if ok else 'ok  '}  {ch}/{os.path.basename(src)} "
                          "does not assemble, on purpose")
                    continue
                for o in outs:
                    total += 1
                    ref, new = os.path.join(folder, o), os.path.join(work, o)
                    same = ok and os.path.exists(new) and os.path.exists(ref) and sha(new) == sha(ref)
                    bad += not same
                    print(f"  {'ok  ' if same else 'DIFF'}  {ch}/{o}")
            finally:
                shutil.rmtree(work, ignore_errors=True)
        for image, cart, how in DERIVED.get(ch, []):
            total += 1
            want = derived(open(os.path.join(folder, cart), "rb").read(), how)
            same = open(os.path.join(folder, image), "rb").read() == want
            bad += not same
            print(f"  {'ok  ' if same else 'DIFF'}  {ch}/{image} ({cart}, {how})")
    print(f"{total} files, {bad} different")
    return bad


if __name__ == "__main__":
    args = sys.argv[1:] or sorted(d for d in os.listdir(ROOT)
                                  if re.fullmatch(r"ch\d\d|app[A-Z]", d))
    sys.exit(1 if main(args) else 0)
