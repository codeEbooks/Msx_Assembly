"""vdpscreen.py -- the picture the TMS9918A draws, from its VRAM and its
registers (chapter 21).

    mode(regs)              "graphic1", "text", "multicolour", "graphic2", or
                            "text+multicolour" for M1 and M2 together
    bases(regs)             where the tables start
    draw(vram, regs)        the paper: 192 rows of 256 colour codes, 1 to 15

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
CharacterConverter::renderBogus); M3 with M1 or M2 is chapter 22's.

TEXT_X0, where text mode's 240 pixels begin in the 256 of the paper, is
measured (meas21.py fits it to the photographs). Sprites are left out
(chapters 26 and 27): every program of this chapter that has them ends the
sprite attribute table at its first entry with $D0.
"""
TEXT_X0 = 9                 # text mode: pixels 9 to 248 of the paper (measured)


def mode(regs):
    m1, m2, m3 = regs[1] >> 4 & 1, regs[1] >> 3 & 1, regs[0] >> 1 & 1
    if m3:
        assert not (m1 or m2), "M3 with M1 or M2: chapter 22"
        return "graphic2"
    return {(0, 0): "graphic1", (1, 0): "text", (0, 1): "multicolour",
            (1, 1): "text+multicolour"}[m1, m2]


def bases(regs):
    """where the tables start; in Graphic II R#3 and R#4 give only the top bit
    of the address, and their other bits are masks (chapter 22)"""
    names = (regs[2] & 0x0F) * 0x400
    if regs[0] & 2:
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
            "text+multicolour": stripes_line}[mode(regs)]
    return [line(vram, regs, bases(regs), y) for y in range(192)]


def text_line(vram, regs, b, y):
    ink, paper = colour(regs[7] >> 4, regs), colour(0, regs)
    row = [paper] * TEXT_X0
    for col in range(40):
        name = vram[b["names"] + y // 8 * 40 + col]
        shape = vram[b["patterns"] + name * 8 + y % 8]
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
    for col in range(32):
        name = vram[b["names"] + y // 8 * 32 + col]
        index = (y // 64 * 256 + name) * 8 + y % 8      # 13 bits: a third,
        p_mask = (regs[4] & 3) << 11 | 0x7FF            # a name, a line
        c_mask = (regs[3] & 0x7F) << 6 | 0x3F
        shape = vram[b["patterns"] | index & p_mask]
        c = vram[b["colours"] | index & c_mask]
        row += bits8(shape, colour(c >> 4, regs), colour(c & 15, regs))
    return row


def multi_line(vram, regs, b, y):
    row = []
    for col in range(32):
        name = vram[b["names"] + y // 8 * 32 + col]
        pair = 2 * (y // 8 % 4)                         # the row, in fours
        c = vram[b["patterns"] + name * 8 + pair + y % 8 // 4]
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
        c_mask = (regs[3] & 0x7F) << 6 | 0x3F
        for index in range(6144):
            got["patterns"].add(b["patterns"] | index & p_mask)
            got["colours"].add(b["colours"] | index & c_mask)
    return {k: len(v) for k, v in got.items()}
