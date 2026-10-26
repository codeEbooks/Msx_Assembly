#!/usr/bin/env python3
"""pic53.py - the picture of chapter 53, THE KEEP AT NIGHT, drawn here.

    picture()               192 rows of 256 colours, the TMS9918's numbers
    graphic2(rows)          -> (patterns, colours), 6,144 bytes each in the
                            order of the VRAM, for names 0 to 255 in each
                            third: the bytes the packers of pack53.py pack
    shown(patterns, colours)
                            the 192 rows of 256 colours the VDP shows from
                            them: graphic2's way back

Nothing is copied from another picture. The keep stands on its hill under a
sky that goes from black at the top to dark blue at the hills, through a
band of dots; it has towers, walls with battlements, lit windows and a lit
gate, and a road that comes down from the gate in the moonlight. Four
colours, four greys apart in print (chapter 1): black, dark blue, light red,
which prints as chapter 1's light green does, and white.
Graphic II gives each row of eight pixels of a cell two colours, and the
picture is drawn so that no row of eight pixels has more: graphic2 checks
it, and shown(graphic2(picture())) is picture() again.
"""

BLACK, DARK_BLUE, LIGHT_RED, WHITE = 1, 4, 9, 15
GREY = {BLACK: 3, DARK_BLUE: 109, LIGHT_RED: 176, WHITE: 252}   # ch01/meas01.json
W, H = 256, 192
BAYER = [[0, 8, 2, 10],                 # the dots of the band of sky: a cell
         [12, 4, 14, 6],                # of the sky goes dark blue where its
         [3, 11, 1, 9],                 # number is below the band's level
         [15, 7, 13, 5]]
SKY_TOP, SKY_LOW = 40, 100              # the band: black above, dark blue below


def hill(x):
    """the hill's top at column x, the line where the ground starts"""
    d = (x - 128) / 128
    return int(146 + 22 * d * d)


def castle():
    """the keep, towers and walls as rectangles: (x0, y0, x1, y1), the
    corners included"""
    parts = []

    def block(x0, x1, top, bottom, merlon=8):
        parts.append((x0, top, x1, bottom))
        x = x0
        while x + merlon - 1 <= x1:                     # the battlements
            parts.append((x, top - 8, x + merlon - 1, top - 1))
            x += 2 * merlon
    block(40, 215, 124, 151)                            # the curtain wall
    block(24, 47, 108, 155)                             # its towers
    block(208, 231, 108, 155)
    block(72, 95, 100, 151)                             # the keep's towers
    block(160, 183, 100, 151)
    block(96, 159, 84, 151)                             # the keep
    block(112, 143, 56, 83)                             # its high tower
    return parts


WINDOWS = [(120, 66), (132, 66),                        # the high tower
           (104, 96), (148, 96), (104, 114), (148, 114),  # the keep
           (80, 112), (172, 112), (32, 120), (216, 120)]  # the towers
WINDOW = ["0110", "1111", "1111", "1111", "1111", "1111"]  # four by six
GATE = (120, 128, 135, 151)                             # the gate, lit
LANTERNS = [(110, 144), (144, 144)]                     # beside the gate
STARS = 44
MOON = (200, 30, 13, 206, 26, 11)                       # a disc less a disc


def stars():
    """the stars, from a fixed sequence: (x, y, big)"""
    out, s = [], 53
    while len(out) < STARS:
        s = (s * 1103515245 + 12345) & 0x7FFFFFFF
        x, y, big = s % 251 + 2, (s >> 9) % (SKY_TOP - 4) + 2, (s >> 20) % 5 == 0
        mx, my = MOON[0], MOON[1]
        if (x - mx) ** 2 + (y - my) ** 2 < 22 ** 2:
            continue
        if any(abs(x - a) < 6 and abs(y - b) < 6 for a, b, _ in out):
            continue
        out.append((x, y, big))
    return out


def picture():
    """the picture: 192 rows of 256 colours"""
    rows = []
    for y in range(H):
        level = 16 * (y - SKY_TOP) / (SKY_LOW - SKY_TOP)
        rows.append([DARK_BLUE if BAYER[y % 4][x % 4] < level else BLACK for x in range(W)])
    for x, y, big in stars():
        for dx, dy in ([(0, 0), (-1, 0), (1, 0), (0, -1), (0, 1)] if big else [(0, 0)]):
            rows[y + dy][x + dx] = WHITE
    mx, my, mr, cx, cy, cr = MOON
    for y in range(my - mr, my + mr + 1):
        for x in range(mx - mr, mx + mr + 1):
            if (x - mx) ** 2 + (y - my) ** 2 <= mr * mr and (x - cx) ** 2 + (y - cy) ** 2 > cr * cr:
                rows[y][x] = WHITE
    for x in range(W):                                  # the hill
        for y in range(hill(x), H):
            rows[y][x] = BLACK
    stone = set()
    for x0, y0, x1, y1 in castle():
        for x in range(x0, x1 + 1):
            for y in range(y0, max(y1 + 1, hill(x))):  # down to the hill
                rows[y][x] = BLACK
                if x0 + 2 <= x <= x1 - 2 and y0 + 2 <= y <= y1 - 1 and y1 - y0 > 8:
                    stone.add((x, y))
    for x, y in stone:                                  # the stones' lines, in dots
        if (y % 8 == 0 and x % 4 == 0) or (y % 8 == 4 and x % 16 == 8 * (y // 8 % 2)):
            rows[y][x] = DARK_BLUE
    for wx, wy in WINDOWS:
        for dy, line in enumerate(WINDOW):
            for dx, bit in enumerate(line):
                if bit == "1":
                    rows[wy + dy][wx + dx] = LIGHT_RED
    gx0, gy0, gx1, gy1 = GATE
    for y in range(gy0, gy1 + 1):
        for x in range(gx0, gx1 + 1):
            arch = (x - (gx0 + gx1) / 2) ** 2 + ((y - gy0 - 8) * 1.0) ** 2 <= 8.5 ** 2
            if y >= gy0 + 8 or arch:
                rows[y][x] = BLACK if (x - gx0) % 4 == 3 and y < gy0 + 14 else LIGHT_RED
    for lx, ly in LANTERNS:
        for y in range(ly, ly + 3):
            for x in range(lx, lx + 2):
                rows[y][x] = LIGHT_RED
    for y in range(152, H):                             # the road, in the moonlight
        t = (y - 152) / (H - 152)
        c = 128 + 34 * t * (1 - t) * 4 * (1 if y < 172 else 1) - 20 * t * t
        half = 8 + 22 * t
        for x in range(int(c - half), int(c + half) + 1):
            if 0 <= x < W and (y < 160 or (x + y) % 2 == 0 or abs(x - c) < half - 4):
                rows[y][x] = DARK_BLUE
    for y in range(H):                                  # the stones stop short of
        for x0 in range(0, W, 8):                       # the lights: two colours
            seg = rows[y][x0:x0 + 8]                    # a row of eight
            if len(set(seg)) > 2:
                for x in range(x0, x0 + 8):
                    if (x, y) in stone and rows[y][x] == DARK_BLUE:
                        rows[y][x] = BLACK
    return rows


def graphic2(rows):
    """patterns and colours, 6,144 bytes each, in the VRAM's order: a third,
    a name, a line. Each row of eight pixels gets its two colours, the
    brighter as ink; a row of one colour takes the colours of the byte before
    it in the VRAM when they have its colour, else that colour as ink on
    black, or black on black"""
    patterns, colours = [], []
    for third in range(3):
        for name in range(256):
            for line in range(8):
                y = third * 64 + name // 32 * 8 + line
                x0 = name % 32 * 8
                seg = rows[y][x0:x0 + 8]
                cs = sorted(set(seg), key=GREY.get)
                assert len(cs) <= 2, (x0, y, cs)
                if len(cs) == 2:
                    paper, ink = cs
                else:
                    c = cs[0]
                    prev = colours[-1] if colours else BLACK << 4 | BLACK
                    if prev >> 4 == c or prev & 15 == c:
                        ink, paper = prev >> 4, prev & 15
                    elif c == BLACK:
                        ink, paper = BLACK, BLACK
                    else:
                        ink, paper = c, BLACK
                bits = 0
                for px in seg:
                    bits = bits << 1 | (px == ink and px != paper)
                patterns.append(bits)
                colours.append(ink << 4 | paper)
    return patterns, colours


def shown(patterns, colours):
    """the picture the VDP shows, names 0 to 255 in each third"""
    rows = [[0] * W for _ in range(H)]
    for i, (p, c) in enumerate(zip(patterns, colours)):
        third, rest = divmod(i, 2048)
        name, line = divmod(rest, 8)
        y, x0 = third * 64 + name // 32 * 8 + line, name % 32 * 8
        for b in range(8):
            rows[y][x0 + b] = c >> 4 if p >> (7 - b) & 1 else c & 15
    return rows


def clashes(rows):
    """the rows of eight pixels with more than two colours: (x, y)"""
    return [(x0, y) for y in range(H) for x0 in range(0, W, 8) if len(set(rows[y][x0:x0 + 8])) > 2]


if not clashes(picture()):
    PATTERNS, COLOURS = graphic2(picture())
    assert shown(PATTERNS, COLOURS) == picture()


if __name__ == "__main__":
    import sys
    from PIL import Image
    rgb = {BLACK: (0, 0, 0), DARK_BLUE: (84, 85, 237), LIGHT_RED: (255, 121, 120), WHITE: (255, 255, 255)}
    img = Image.new("RGB", (W, H))
    img.putdata([rgb[c] for row in picture() for c in row])
    img.resize((W * 3, H * 3), Image.NEAREST).save(sys.argv[1] if len(sys.argv) > 1 else "pic53.png")
