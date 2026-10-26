"""vdpscreen.py -- the picture the TMS9918A draws, from its VRAM and its
registers: chapter 21's model, chapter 22's three rules more, and chapter
23's sprites.

    mode(regs)              "graphic1", "text", "multicolour", "graphic2",
                            "text+multicolour" for M1 and M2 together, and
                            "text+graphic2", "multicolour+graphic2" for M1 or
                            M2 with M3
    bases(regs)             where the tables start
    draw(vram, regs)        the paper: 192 rows of 256 colour codes, 1 to 15,
                            the sprites over the picture
    address(x, y)           Graphic II with names 0 to 255 in each third: the
                            address of the byte of pixel (x, y), in the
                            patterns and, from the colours' start, the colours

The rules are those of Texas Instruments' manual for the TMS9918A, as chapter
21 states them:
  1. Three bits choose the mode: M3, bit 1 of R#0; M1, bit 4 of R#1; M2, bit 3
     of R#1. None: Graphic I. M1: text. M2: multicolour. M3: Graphic II.
  2. The names start at R#2 x $400, the colours at R#3 x $40 and the patterns
     at R#4 x $800; in Graphic II, R#3 and R#4 also mask the address (chapter
     22 takes the masks apart; the programs of this chapter set every mask bit).
  3. A pattern byte's bits are pixels, bit 7 on the left: 1 is the ink, 0 the
     paper. Text mode draws the six bits 7 to 2 of each byte, 40 characters a
     line, and takes both colours from R#7: the ink in its high four bits.
  4. Multicolour draws no pixels: a pattern byte is two blocks of 4 x 4, the
     high four bits on the left; a name's row of the screen, counted in fours,
     picks the two bytes of its pattern that it shows.
  5. Colour 0 is transparent: the backdrop, the low four bits of R#7, shows.
     With bit 6 of R#1 at 0 the screen is all backdrop.
And one that is not in the manual: with M1 and M2 together openMSX draws 40
stripes of four pixels of R#7's ink and two of its backdrop (its
CharacterConverter::renderBogus).

Chapter 22's three, from openMSX's source (src/video/VDP.cc and
CharacterConverter.cc):
  6. In Graphic II the address of a pattern byte is also masked by the low
     five bits of R#3, at bits 6 to 10, on the TMS99x8 and TMS9929 (both of
     the book's machines): openMSX's authors write that some of the colour
     register's bits leak into the pattern base. LEAK = False leaves it out.
  7. M1 with M3 is text mode whose shapes are taken from the third of the
     screen the line is in, masked by R#4 as Graphic II's are.
  8. M2 with M3 is multicolour that does the same. M1, M2 and M3 together
     draw the stripes.

And chapter 23's, from the manual, for the programs of that chapter:
  9. Sprites are drawn over the picture in Graphic I, Graphic II and
     multicolour, from the attribute table at R#5 x $80: four bytes each, Y,
     X, the pattern and the colour, up to the first Y of $D0 (208). The
     patterns are at R#6 x $800, 8 x 8, or 16 x 16 with bit 1 of R#1 (four
     patterns from a multiple of 4: the left half's 16 bytes, then the
     right's); bit 0 of R#1 doubles every pixel. Colour 0 is transparent;
     bit 7 of the colour byte moves the sprite 32 pixels left. Where two
     sprites meet, the one earlier in the table is drawn. The first line of
     a sprite is its Y plus SPRITE_DY, measured. Chapters 26 and 27 take the
     rest: four sprites on a line, and what happens to a fifth.

TEXT_X0, where text mode's 240 pixels begin in the 256 of the paper, is
measured (meas21.py fits it to the photographs), and so is SPRITE_DY
(meas23.py).
"""
TEXT_X0 = 9                 # text mode: pixels 9 to 248 of the paper (measured)
LEAK = True                 # rule 6: R#3's low five bits mask the patterns too
SPRITE_DY = 1               # rule 9: a sprite's first line is its Y + 1 (measured)


def mode(regs):
    m1, m2, m3 = regs[1] >> 4 & 1, regs[1] >> 3 & 1, regs[0] >> 1 & 1
    return {(0, 0, 0): "graphic1", (1, 0, 0): "text", (0, 1, 0): "multicolour",
            (1, 1, 0): "text+multicolour", (0, 0, 1): "graphic2",
            (1, 0, 1): "text+graphic2", (0, 1, 1): "multicolour+graphic2",
            (1, 1, 1): "text+multicolour"}[m1, m2, m3]


def address(x, y):
    """the byte of pixel (x, y) in Graphic II with names 0 to 255 in each
    third: the row of characters, then the column, then the line"""
    return (y // 8) * 256 + (x // 8) * 8 + y % 8


def bases(regs):
    """where the tables start; in Graphic II R#3 and R#4 give only the top bit
    of the address, and their other bits are masks (chapter 22)"""
    names = (regs[2] & 0x0F) * 0x400
    if regs[0] & 2 and mode(regs) == "graphic2":
        return {"names": names, "colours": (regs[3] & 0x80) << 6,
                "patterns": (regs[4] & 0x04) << 11}
    return {"names": names, "colours": regs[3] * 0x40,
            "patterns": (regs[4] & 0x07) * 0x800}


def colour(c, regs):
    """colour 0 shows the backdrop"""
    return c if c else regs[7] & 0x0F


def bits8(byte, ink, paper):
    return [ink if byte & (0x80 >> i) else paper for i in range(8)]


def draw(vram, regs):
    """the paper: 192 lines of 256 colour codes"""
    if not regs[1] & 0x40:                              # the display off
        return [[colour(0, regs)] * 256 for _ in range(192)]
    line = {"text": text_line, "graphic1": graphic1_line,
            "graphic2": graphic2_line, "multicolour": multi_line,
            "text+multicolour": stripes_line, "text+graphic2": text_line,
            "multicolour+graphic2": multi_line}[mode(regs)]
    rows = [line(vram, regs, bases(regs), y) for y in range(192)]
    if not regs[1] & 0x10:                              # no sprites in text mode
        sprites(vram, regs, rows)
    return rows


def sprites(vram, regs, rows):
    """rule 9: the sprites over the picture, the first in the table on top"""
    att, pat = (regs[5] & 0x7F) * 0x80, (regs[6] & 7) * 0x800
    big, scale = regs[1] & 2, 2 if regs[1] & 1 else 1
    size = 16 if big else 8
    taken = set()
    for i in range(32):
        y, x, p, c = vram[att + 4 * i:att + 4 * i + 4]
        if y == 0xD0:
            break
        x -= 32 if c & 0x80 else 0
        top = (y + SPRITE_DY) & 0xFF
        top -= 256 if top > 0xE0 else 0
        base = pat + (p & 0xFC if big else p) * 8
        for row in range(size * scale):
            line = top + row
            if not 0 <= line < 192:
                continue
            r = row // scale
            bits = vram[base + r] << 8 | (vram[base + 16 + r] if big else 0)
            for col in range(size * scale):
                px = x + col
                if bits & 0x8000 >> col // scale and 0 <= px < 256 and c & 15 \
                        and (line, px) not in taken:
                    taken.add((line, px))
                    rows[line][px] = c & 15


def third_shape(regs, b, y, name, byte):
    """the pattern byte BYTE of NAME: M1 or M2 alone read the pattern table;
    with M3 they read the third of the screen the line is in, masked by R#4"""
    if not regs[0] & 2:
        return b["patterns"] + name * 8 + byte
    index = (y // 64 * 256 + name) * 8 + byte
    return (regs[4] & 4) << 11 | index & ((regs[4] & 3) << 11 | 0x7FF)


def text_line(vram, regs, b, y):
    ink, paper = colour(regs[7] >> 4, regs), colour(0, regs)
    row = [paper] * TEXT_X0
    for col in range(40):
        name = vram[b["names"] + y // 8 * 40 + col]
        shape = vram[third_shape(regs, b, y, name, y % 8)]
        row += bits8(shape, ink, paper)[:6]             # bits 7 to 2
    return row + [paper] * (256 - len(row))


def graphic1_line(vram, regs, b, y):
    row = []
    for col in range(32):
        name = vram[b["names"] + y // 8 * 32 + col]
        shape = vram[b["patterns"] + name * 8 + y % 8]
        c = vram[b["colours"] + name // 8]              # one for 8 names
        row += bits8(shape, colour(c >> 4, regs), colour(c & 15, regs))
    return row


def graphic2_line(vram, regs, b, y):
    row = []
    p_mask = (regs[4] & 3) << 11 | 0x7FF                # the third, and all
    if LEAK:                                            # of a name and a line
        p_mask &= ~0x7C0 | (regs[3] & 0x1F) << 6        # ... but R#3's say
    c_mask = (regs[3] & 0x7F) << 6 | 0x3F
    for col in range(32):
        name = vram[b["names"] + y // 8 * 32 + col]
        index = (y // 64 * 256 + name) * 8 + y % 8      # 13 bits
        shape = vram[b["patterns"] | index & p_mask]
        c = vram[b["colours"] | index & c_mask]
        row += bits8(shape, colour(c >> 4, regs), colour(c & 15, regs))
    return row


def multi_line(vram, regs, b, y):
    row = []
    for col in range(32):
        name = vram[b["names"] + y // 8 * 32 + col]
        pair = 2 * (y // 8 % 4)                         # the row, in fours
        c = vram[third_shape(regs, b, y, name, pair + y % 8 // 4)]
        row += [colour(c >> 4, regs)] * 4 + [colour(c & 15, regs)] * 4
    return row


def stripes_line(vram, regs, b, y):
    """M1 and M2: openMSX's renderBogus"""
    ink, paper = colour(regs[7] >> 4, regs), colour(0, regs)
    return [paper] * 8 + ([ink] * 4 + [paper] * 2) * 40 + [paper] * 8


def reads(regs):
    """the VRAM addresses the mode reads to draw a page whose names are all
    different where they can be: for the table of chapter 21"""
    m, b = mode(regs), bases(regs)
    got = {"names": set(), "patterns": set(), "colours": set()}
    if m == "text":
        got["names"] = set(range(b["names"], b["names"] + 960))
        got["patterns"] = set(range(b["patterns"], b["patterns"] + 2048))
    elif m == "graphic1":
        got["names"] = set(range(b["names"], b["names"] + 768))
        got["patterns"] = set(range(b["patterns"], b["patterns"] + 2048))
        got["colours"] = set(range(b["colours"], b["colours"] + 32))
    elif m == "multicolour":
        got["names"] = set(range(b["names"], b["names"] + 768))
        got["patterns"] = set(range(b["patterns"], b["patterns"] + 2048))
    elif m == "graphic2":
        got["names"] = set(range(b["names"], b["names"] + 768))
        p_mask = (regs[4] & 3) << 11 | 0x7FF
        if LEAK:
            p_mask &= ~0x7C0 | (regs[3] & 0x1F) << 6
        c_mask = (regs[3] & 0x7F) << 6 | 0x3F
        for index in range(6144):
            got["patterns"].add(b["patterns"] | index & p_mask)
            got["colours"].add(b["colours"] | index & c_mask)
    return {k: len(v) for k, v in got.items()}
