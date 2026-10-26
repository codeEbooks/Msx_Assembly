#!/usr/bin/env python3
"""pack56.py - the release's files, made from the two cartridges build.sh assembled.

    grin_alley_x2.bin     GRIN ALLEY twice, 32 KB, for a 27C256: whichever of
                          the slot's address lines drives the EPROM's A14,
                          page 1 reads a whole copy
    lantern_keep_a14.bin  LANTERN KEEP for a board that drives the 27C256's A14
                          from the slot's A14: the two halves of 16 KB the
                          other way round. A board that drives it from A15
                          takes lantern_keep.rom as it is
    grin_alley.txt, lantern_keep.txt
                          what goes with each cartridge: what it is, its file
                          and its SHA-256, the machines, the keys, the EPROM

The board, as this file models it (chapter 56): a 27C256 with one of its two
enables, /CE and /OE, on the slot's /SLTSL, low when this slot's memory is
read or written, and the other on its /CS12, low when $4000-$BFFF is read in
any slot: together, a read of $4000-$BFFF in this slot. The EPROM's A0-A13
are the slot's A0-A13, and its A14 is the slot's A15 ("a15", the A15 board)
or A14 ("a14", the A14 board).
"""
import hashlib
import os

HERE = os.path.dirname(os.path.abspath(__file__))
K16 = 0x4000
WIRINGS = ("a15", "a14")


def chip_address(cpu, wiring):
    """the EPROM's address that CPU address CPU ($4000-$BFFF) reads"""
    assert 0x4000 <= cpu < 0xC000
    bit = (cpu >> 15) & 1 if wiring == "a15" else (cpu >> 14) & 1
    return (cpu & 0x3FFF) | bit << 14


def cpu_view(chip, wiring):
    """the 32 KB the processor reads from $4000 to $BFFF, from an EPROM's bytes"""
    assert len(chip) == 2 * K16
    return bytes(chip[chip_address(a, wiring)] for a in range(0x4000, 0xC000))


def chip_image(rom, wiring):
    """the EPROM's bytes that make the processor read ROM from $4000: a 16 KB
    ROM twice; a 32 KB one with its halves where the wiring wants them"""
    if len(rom) == K16:
        return rom + rom
    assert len(rom) == 2 * K16
    chip = bytearray(2 * K16)
    for a in range(0x4000, 0xC000):
        chip[chip_address(a, wiring)] = rom[a - 0x4000]
    return bytes(chip)


TEXT = {
    "grin_alley": """GRIN ALLEY
A game for MSX1 computers, from the book MSX Assembly (chapters 43 and 44).
(c) 2026 CODE & BOOKS

Cartridge  a plain ROM of 16 KB, from $4000 to $7FFF; no mapper
File       grin_alley.rom, {size:,} bytes
SHA-256    {sha}
Machines   an MSX1 or later, with 16 KB of RAM or more, at 50 or 60 Hz
Keys       the cursor keys or joystick 1; SPACE or button A at the title
Emulator   openMSX: openmsx -carta grin_alley.rom
EPROM      a 27C128 on the slot's /SLTSL and /CS1: grin_alley.rom as it is.
           A 27C256 on /SLTSL and /CS12: grin_alley_x2.bin, the game twice,
           whichever of the slot's lines drives the EPROM's A14
Source     ch56/grin_alley.asm, chapter 44's game.asm, in the book's repository
Licence    MIT, as the whole repository (LICENCE)
""",
    "lantern_keep": """LANTERN KEEP
A game for MSX1 computers, from the book MSX Assembly (chapters 45, 46 and 54).
(c) 2026 CODE & BOOKS

Cartridge  a plain ROM of 32 KB, from $4000 to $BFFF; no mapper. It selects
           its slot for page 2 itself
File       lantern_keep.rom, {size:,} bytes
SHA-256    {sha}
Machines   an MSX1 or later, with 16 KB of RAM or more, at 50 or 60 Hz
Keys       the cursor keys or joystick 1; SPACE or button A at the title;
           M or button B for the map
Emulator   openMSX: openmsx -carta lantern_keep.rom
EPROM      a 27C256 on the slot's /SLTSL and /CS12. If the board drives the
           EPROM's A14 from the slot's A15: lantern_keep.rom as it is. If
           from the slot's A14: lantern_keep_a14.bin, its two halves of 16 KB
           the other way round
Source     ch56/lantern_keep.asm, chapter 54's game.asm, in the book's repository
Licence    MIT, as the whole repository (LICENCE)
""",
}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def main():
    rom = {n: open(os.path.join(HERE, f"{n}.rom"), "rb").read() for n in TEXT}
    files = {
        "grin_alley_x2.bin": chip_image(rom["grin_alley"], "a15"),
        "lantern_keep_a14.bin": chip_image(rom["lantern_keep"], "a14"),
    }
    # the images make the processor read the cartridges, through their wirings
    assert chip_image(rom["grin_alley"], "a14") == files["grin_alley_x2.bin"]
    for w in WIRINGS:
        assert cpu_view(files["grin_alley_x2.bin"], w) == rom["grin_alley"] * 2
    assert chip_image(rom["lantern_keep"], "a15") == rom["lantern_keep"]
    assert cpu_view(files["lantern_keep_a14.bin"], "a14") == rom["lantern_keep"]
    assert files["lantern_keep_a14.bin"] == rom["lantern_keep"][K16:] + rom["lantern_keep"][:K16]
    for n, text in TEXT.items():
        files[f"{n}.txt"] = text.format(size=len(rom[n]), sha=sha256(rom[n])).encode()
    for name, data in files.items():
        with open(os.path.join(HERE, name), "wb") as f:
            f.write(data)
    print(" ".join(files))


if __name__ == "__main__":
    main()
