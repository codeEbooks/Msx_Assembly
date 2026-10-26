"""screentext.py -- read back the text a program drew on a Graphic I page.

The programs of this book print with the BIOS's own character set (copied into
the VDP by tools/asmparts.py) and two bit boxes. This module reads a capture
cell by cell: each 8 x 8 cell is compared with the character shapes in the
BIOS ROM file of the machine that ran the program -- read from the file, not
from the program -- and with the boxes, which read as "0" and "1".
"""
from pathlib import Path

from PIL import Image

import meas
import msxcap
from asmparts import BOX_SHAPES, BOX_EMPTY, BOX_FULL

def bios_file(machine):
    """the BIOS ROM of one of the book's machines: the Japanese one, or the
    European one that every other machine in machines/ uses"""
    return "cbios_main_msx1_jp.rom" if "JP" in machine else "cbios_main_msx1_eu.rom"


def font(machine="MSXBOOK_EU16", rom_file=None):
    """the 256 character shapes of a machine's BIOS, and where they are: the
    address of the set is the word at $0004 (CGTABL). rom_file: read them
    from that BIOS file instead (a machine that is not one of the book's)"""
    rom = Path(rom_file).read_bytes() if rom_file else (msxcap.CBIOS / bios_file(machine)).read_bytes()
    at = rom[4] | rom[5] << 8
    return [tuple(rom[at + 8 * c: at + 8 * c + 8]) for c in range(256)], at


def shape_table(machine="MSXBOOK_EU16", rom_file=None):
    """shape -> character for the codes 32-126 and the two boxes; a shape
    two codes share cannot be read back and reads "?" """
    shapes, _ = font(machine, rom_file)
    table = {}
    for c in range(32, 127):
        table[shapes[c]] = "?" if shapes[c] in table else chr(c)
    table[tuple(BOX_SHAPES[BOX_EMPTY])] = "0"
    table[tuple(BOX_SHAPES[BOX_FULL])] = "1"
    return table


def cell(px, col, row, light_ink=False):
    """the 8 bytes of a character cell as the screen shows them (ink = 1):
    dark ink on light paper, as the book's pages are, or with light_ink white
    ink on a darker paper, as C-BIOS writes its own screens"""
    x0, y0 = meas.paper(8 * col, 8 * row)
    if light_ink:
        return tuple(sum((sum(px[x0 + i, y0 + j]) >= 600) << (7 - i) for i in range(8))
                     for j in range(8))
    return tuple(sum((sum(px[x0 + i, y0 + j]) < 384) << (7 - i) for i in range(8))
                 for j in range(8))


class Page:
    """a capture, read as 24 lines of 32 characters"""

    def __init__(self, png, machine="MSXBOOK_EU16", rom_file=None, light_ink=False):
        self.px = Image.open(png).convert("RGB").load()
        self.table = shape_table(machine, rom_file)
        self.light_ink = light_ink

    def line(self, row):
        return "".join(self.table.get(cell(self.px, c, row, self.light_ink), "?") for c in range(32))

    def text(self, row, col, n):
        return self.line(row)[col:col + n]
