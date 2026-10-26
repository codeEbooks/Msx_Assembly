#!/usr/bin/env python3
"""genF.py - the program of Appendix F: every BIOS entry point this book
calls, called once with inputs known.

    python3 genF.py && ./build.sh

    calls.asm   each of the 27 entry points of bios.inc, called in turn just
                after a frame's interrupt, with every register first set to
                a value of its own and then the entry's inputs; a label
                before each CALL and one after it, where measF.py has the
                debugger read the registers, the time and the interrupts.
                Then the seven that leave the interrupts off, again with
                them on; then, with the keyboard row 8 read on the PPI's
                ports until SPACE is held, the five calls that want a key:
                GTSTCK, GTTRIG, SNSMAT, CHSNS and CHGET.

The program runs with the BIOS as C-BIOS leaves it at INIT, page 0 in slot 0,
and lets the BIOS's interrupt run between the calls (EI and HALT), so that
the keyboard is read as the BIOS reads it. build.sh assembles with
--syntax=bFw (chapter 15).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
for d in ("tools", "ch26"):
    sys.path.insert(0, os.path.join(REPO, d))
from gen26 import tidy  # noqa: E402  (chapter 26)

# the book's machines (chapter 38): the BIOS in slot 0, the cartridge in slot
# 1, the RAM in slot 3, none expanded
BIOS_SLOT, CART_SLOT, RAM_SLOT = 0x00, 0x01, 0x03
WRSLT_AT, WRSLT_BYTE = 0xE000, 0x5A
FILL_N = 28                     # FILVRM's count, chapter 19's

# the values every register is given before a call's inputs: each its own
MARKERS = {"af": 0xA5C3, "bc": 0xB1C1, "de": 0xD1E1, "hl": 0x4171, "ix": 0x1F2F,
           "iy": 0x3F4F, "af2": 0x5AC5, "bc2": 0xB2C2, "de2": 0xD2E2, "hl2": 0x4272}

# the calls: (label, entry, inputs, what), in the order they run; the
# second part waits for keys
CASES = [
    ("rdslt", "RDSLT", ["ld a, $00", "ld hl, $002B"], "the byte at $002B of slot 0"),
    ("wrslt", "WRSLT", [f"ld a, ${RAM_SLOT:02X}", f"ld hl, ${WRSLT_AT:04X}", f"ld e, ${WRSLT_BYTE:02X}"],
     f"${WRSLT_BYTE:02X} to ${WRSLT_AT:04X} of slot {RAM_SLOT}, the RAM"),
    ("calslt", "CALSLT", ["ld iy, $0000", "ld ix, RSLREG"], "RSLREG, in slot 0"),
    ("enaslt", "ENASLT", [f"ld a, ${CART_SLOT:02X}", "ld h, $40"], "page 1 to slot 1, where it is"),
    ("disscr", "DISSCR", [], "the display off"),
    ("enascr", "ENASCR", [], "the display on"),
    ("wrtvdp", "WRTVDP", ["ld b, $F4", "ld c, 7"], "$F4 to R#7"),
    ("rdvrm", "RDVRM", ["ld hl, $1800"], "the byte at $1800"),
    ("wrtvrm", "WRTVRM", ["ld hl, $1800", "ld a, $41"], "$41 to $1800"),
    ("setrd", "SETRD", ["ld hl, $1800"], "a read address, $1800"),
    ("setwrt", "SETWRT", ["ld hl, $1800"], "a write address, $1800"),
    ("filvrm", "FILVRM", ["ld hl, $1800", f"ld bc, {FILL_N}", "ld a, $20"],
     f"{FILL_N} bytes of $20 from $1800, as chapter 19 filled"),
    ("ldirvm", "LDIRVM", ["ld hl, text", "ld de, $1800", "ld bc, 16"], "16 bytes from the ROM to $1800"),
    ("chgmod", "CHGMOD", ["ld a, 1"], "screen mode 1, Graphic I"),
    ("inimlt", "INIMLT", [], "multicolour"),
    ("inigrp", "INIGRP", [], "Graphic II"),
    ("init32", "INIT32", [], "Graphic I"),
    ("initxt", "INITXT", [], "text mode"),
    ("chput", "CHPUT", ["ld a, $41"], "the letter A"),
    ("chsns", "CHSNS", [], "no key waiting"),
    ("beep", "BEEP", [], "a beep"),
    ("gtstck", "GTSTCK", ["ld a, 0"], "the cursor keys, none held"),
    ("gttrig", "GTTRIG", ["ld a, 0"], "SPACE, not held"),
    ("rslreg", "RSLREG", [], "port $A8"),
    ("wslreg", "WSLREG", ["in a, (PPI_A)"], "port $A8 written as it is"),
    ("snsmat", "SNSMAT", ["ld a, 8"], "row 8, nothing held"),
]
# the calls that leave the interrupts as they found them, or turn them off,
# again with the interrupts on (EI just before the CALL)
ON = [(f"{label}_e", entry, inputs + ["ei"], what + ", the interrupts on")
      for label, entry, inputs, what in CASES if label in ("rdslt", "wrslt", "calslt", "enaslt", "beep",
                                                           "rslreg", "wslreg")]
KEYED = [
    ("gtstck_k", "GTSTCK", ["ld a, 0"], "the cursor keys, RIGHT held"),
    ("gttrig_k", "GTTRIG", ["ld a, 0"], "SPACE, held"),
    ("snsmat_k", "SNSMAT", ["ld a, 8"], "row 8, SPACE and RIGHT held"),
    ("chsns_k", "CHSNS", [], "a key waiting"),
    ("chget_k", "CHGET", [], "the key waiting"),
]
SETTLE = 10                     # frames of interrupts after SPACE is seen


def markers():
    """the routine that gives every register its marker; AF through the
    stack, the only way to load F"""
    m = MARKERS
    body = [f"ld hl, ${m['af2']:04X}", "push hl", "pop af", "ex af, af'",
            "exx", f"ld bc, ${m['bc2']:04X}", f"ld de, ${m['de2']:04X}", f"ld hl, ${m['hl2']:04X}", "exx",
            f"ld hl, ${m['af']:04X}", "push hl", "pop af",
            f"ld bc, ${m['bc']:04X}", f"ld de, ${m['de']:04X}", f"ld hl, ${m['hl']:04X}",
            f"ld ix, ${m['ix']:04X}", f"ld iy, ${m['iy']:04X}", "ret"]
    return "markers: " + "\n        ".join(body) + "\n"


def case(label, entry, inputs, what):
    lines = [f"; {entry}: {what}", f"{label}:", "        ei", "        halt                    ; just after a frame's interrupt", "        di",
             "        call markers            ; every register a value of its own"]
    lines += ["        " + l for l in inputs]
    lines += [f"b_{label}:", f"        call {entry}", f"a_{label}:", "        nop"]
    return "\n".join(lines) + "\n"


def calls():
    body = "".join(case(*c) for c in CASES + ON)
    keyed = "".join(case(*c) for c in KEYED)
    return f"""; calls.asm -- appendix F: every BIOS entry point of bios.inc, called once
; generated by genF.py
        INCLUDE "msx.inc"
        INCLUDE "bios.inc"
        OUTPUT "calls.rom"
        ORG $4000
        CART_HEADER init
; Before each call every register gets a value of its own (markers, at the
; end), then the call's inputs.
init:   di
        ld sp, SYS_AREA
{body}
; the keys: wait, frame by frame, until row 8 of the keyboard shows SPACE
; held, read on the PPI's own ports, then {SETTLE} frames for the BIOS to read them
keys:   ei
        halt
        di
        in a, (PPI_C)
        and $F0
        or 8
        out (PPI_C), a          ; row 8
        in a, (PPI_B)
        bit 0, a                ; SPACE: 0 while held
        jr nz, keys
        ld b, {SETTLE}
settle: ei
        halt
        djnz settle
{keyed}
done:   di
        jr done

; every register a value of its own: AF ${MARKERS['af']:04X}, BC ${MARKERS['bc']:04X}, DE ${MARKERS['de']:04X}, HL ${MARKERS['hl']:04X},
; IX ${MARKERS['ix']:04X}, IY ${MARKERS['iy']:04X}, AF' ${MARKERS['af2']:04X}, BC' ${MARKERS['bc2']:04X}, DE' ${MARKERS['de2']:04X}, HL' ${MARKERS['hl2']:04X}
{markers()}
text:   db "THE BIOS, CALLED"       ; LDIRVM's sixteen bytes
        ASSERT $ - text == 16
        ASSERT $ <= $8000, the program is longer than the cartridge
        ds $8000 - $, $FF       ; pad the cartridge to 16 KB
"""


def main():
    with open(os.path.join(HERE, "calls.asm"), "w") as f:
        f.write(tidy(calls()))
    for name in ("msx.inc", "bios.inc"):
        with open(os.path.join(REPO, name)) as a, open(os.path.join(HERE, name), "w") as b:
            b.write(a.read())
    print("appendix F: calls.asm,", len(CASES) + len(ON) + len(KEYED), "calls")


if __name__ == "__main__":
    main()
