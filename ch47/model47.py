#!/usr/bin/env python3
"""model47.py -- chapter 47's three prototypes in Python, a loop at a time.

    python3 model47.py          each prototype run for gen47.FRAMES loops,
                                and the plain checks of the plans

Cave, Jump and Maze each keep what their cartridge keeps in the RAM, and
make, in order, the bytes their loop sends to the VDP's two ports; from those
bytes they keep the VRAM. Each also says, for every frame, the picture its
cartridge means to show, worked out from the world and not from the VRAM:
the cave's pixels at the scroll's place and the ship; the ledges, every dot
so far and the runner; the frame, the map, the view from the cell shown and
the arrow. meas47.py holds the debugger's RAM and port log against the
first, and the screen line by line, as the bytes reached the VRAM, against
the second.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gen47  # noqa: E402
sys.path.remove(HERE)
sys.path.insert(0, HERE)
for _m in ("vdpscreen",):
    sys.modules.pop(_m, None)
import vdpscreen  # noqa: E402

assert os.path.dirname(os.path.abspath(vdpscreen.__file__)) == HERE

SAT, SPAT = 0x1B00, 0x3800
D, C = 0x98, 0x99                   # the VDP's data and control ports


def sprite_rows(rows16_):
    return gen47.big(rows16_)


class Proto:
    """what the three share: the VDP's ports, the demo's pad, isr"""
    def __init__(self, name, regs, demo, sym):
        self.name = name
        self.sym = sym
        self.vram = bytearray(16384)
        self.regs = list(regs)
        self.addr = 0
        self.ports = []
        self.demo = demo
        self.ticks = 0
        self.held = 0
        self.dleft = 1
        self.dnext = 0              # the next pair's index in the demo
        self.stat = 0
        self.loop = -1

    # ---------------------------------------------------------- the VDP's ports
    def setw(self, addr):
        self.ports += [(C, addr & 0xFF), (C, (addr >> 8) & 0x3F | 0x40)]
        self.addr = addr & 0x3FFF

    def setr(self, addr):
        self.ports += [(C, addr & 0xFF), (C, (addr >> 8) & 0x3F)]
        self.addr = addr & 0x3FFF
        v = self.vram[self.addr]        # the VDP reads ahead
        self.addr = (self.addr + 1) & 0x3FFF
        return v

    def out(self, v):
        self.ports.append((D, v))
        self.vram[self.addr] = v
        self.addr = (self.addr + 1) & 0x3FFF

    def reg(self, r, v):
        self.ports += [(C, v), (C, 0x80 | r)]
        self.regs[r] = v

    # ---------------------------------------------------------- the frame
    def status(self):
        five, number = vdpscreen.sprite_status(self.vram, self.regs)
        c, _ = vdpscreen.coincidence(self.vram, self.regs)
        return 0x80 | five << 6 | c << 5 | number

    def isr(self):
        self.stat = self.status()
        self.ticks = (self.ticks + 1) & 0xFFFF

    def pad(self):
        self.dleft = (self.dleft - 1) & 255
        if self.dleft == 0:
            if self.dnext >= len(self.demo):
                self.dnext = 0
            n, held = self.demo[self.dnext]
            self.dleft = n
            self.held = held
            self.dnext += 1
        return self.held

    def step_loop(self):
        """a loop: the interrupt that wakes it, the sends, the run -> the
        bytes it sent to the VDP: (sends', run's)"""
        self.loop += 1
        self.isr()
        self.ports = []
        self.sends()
        sent = self.ports
        self.ports = []
        self.run()
        return sent, self.ports

    def ram_common(self):
        return {"stat": self.stat, "ticks": self.ticks, "held": self.held, "dleft": self.dleft,
                "dnext": self.sym["demo"] + 2 * self.dnext, "copy": list(self.copy)}

    def picture_frame(self):
        """the paper the cartridge means the next frame to show: colour codes"""
        raise NotImplementedError


def put_sprite(pic, rows, x, y, colour, size=16):
    """a sprite's pixels over PIC, at X and line Y (its attribute's Y + 1)"""
    for j in range(size):
        line = y + j
        if not 0 <= line < 192:
            continue
        bits = rows[j]
        for i in range(size):
            if bits >> (size - 1 - i) & 1 and 0 <= x + i < 256:
                pic[line][x + i] = colour


# ================================================================ the cave
class Cave(Proto):
    def __init__(self, sym):
        g = gen47
        super().__init__("cave", [0x02, 0xE2, 0x06, 0x9F, 0x00, 0x36, 0x07, g.CAVE_BORDER],
                         g.CAVE_DEMO, sym)
        self.col, self.shift, self.table = 0, 1, 0x18
        self.shown = 0                  # the window in the table shown
        self.copy = [g.CAVE_Y0 - 1, g.SHIP_AT[0], 0, g.SHIP_COLOUR, 0xD0]
        v = self.vram
        shp = self.patterns(0)
        v[8:8 + len(shp)] = bytes(shp)
        v[0x2000:0x2008] = bytes([g.CEIL_C] * 8)
        cols = [b for a, b2 in g.PAIRS for b in g.pair_colours(a, b2)]
        v[0x2008:0x2008 + len(cols)] = bytes(cols)
        for tb, w in ((0x1800, 0), (0x1C00, 1)):
            for i, r in enumerate(g.SCROLL_ROWS):
                v[tb + 32 * r:tb + 32 * r + 32] = bytes(self.row_names(i, w))
        v[SAT] = 0xD0
        v[SPAT:SPAT + 32] = bytes(gen47.big(g.SHIP))
        self.offsets = []
        self.spans = [(0, 8 + 8 * g.NP), (0x2000, 0x2008 + 8 * g.NP), (0x1800, 0x1B00), (0x1C00, 0x1F00),
                      (SAT, SAT + 1), (SPAT, SPAT + 32)]               # the world's pixel at the left of each frame shown

    @staticmethod
    def patterns(s):
        return [b for a, b2 in gen47.PAIRS for b in gen47.shifted(a, b2, s)]

    @staticmethod
    def row_names(i, w):
        row = gen47.PMAP[i]
        return [row[(w + c) % gen47.W] for c in range(32)]

    def sends(self):
        self.setw(SAT)
        for b in self.copy:
            self.out(b)
        self.setw(0x0008)
        for b in self.patterns(self.shift):
            self.out(b)
        if self.shift == 0:
            self.table ^= 0x18 ^ 0x1C
            self.reg(2, self.table >> 2)
            self.shown = (self.shown + 1) % gen47.W
        self.offsets.append(8 * self.shown + self.shift)

    def run(self):
        k = ~self.pad() & 0xFF
        x, y = gen47.ship_step(self.copy[1], self.copy[0] + 1, k)
        self.copy[0], self.copy[1] = y - 1, x
        if self.shift == 0:
            self.window((self.col + 1) % gen47.W)
        self.shift = (self.shift + 1) & 7
        if self.shift == 0:
            self.col = (self.col + 1) % gen47.W

    def window(self, w):
        hidden = self.table ^ (0x18 ^ 0x1C)
        self.setw((hidden << 8) + 32)
        for i in range(4):
            for n in self.row_names(i, w):
                self.out(n)
        self.setw((hidden << 8) + 32 * 17)
        for i in range(4, 11):
            for n in self.row_names(i, w):
                self.out(n)

    def ram(self):
        return dict(self.ram_common(), col=self.col, shift=self.shift, table=self.table)

    WORLD = None

    @classmethod
    def world(cls):
        """the world's picture, twice round: 192 lines of 1,024 colour codes"""
        if cls.WORLD is None:
            g = gen47
            out = []
            for y in range(192):
                r = y >> 3
                ink = (g.DARK_BLUE if g.CEIL_ROWS[0] <= r <= g.CEIL_ROWS[1] else
                       g.LIGHT_GREEN if g.GROUND_ROWS[0] <= r <= g.GROUND_ROWS[1] else g.BLACK)
                row = [ink if g.cave_pixel(x, y) else g.BLACK for x in range(8 * g.W)]
                out.append(row + row)
            cls.WORLD = out
        return cls.WORLD

    def picture(self, offset=None, copy=None):
        g = gen47
        o = self.offsets[-1] if offset is None else offset
        cp = self.copy if copy is None else copy
        pic = [row[o:o + 256] for row in self.world()]
        put_sprite(pic, g.SHIP, cp[1], (cp[0] + 1) & 0xFF, g.SHIP_COLOUR)
        return pic


# ================================================================ the ledges
class Jump(Proto):
    def __init__(self, sym):
        g = gen47
        super().__init__("jump", [0x02, 0xE2, 0x06, 0xFF, 0x03, 0x36, 0x07, g.JUMP_BORDER],
                         g.JUMP_DEMO, sym)
        self.runner = g.Runner()
        self.copy = [g.RUNNER_AT[1] - 1, g.RUNNER_AT[0], 0, g.RUNNER_COLOUR, 0xD0]
        v = self.vram
        for r in range(24):
            for c in range(32):
                a = 0x100 * r + 8 * c
                led = g.ledge(c, r)
                v[a:a + 8] = bytes(g.gen39.BRICK if led else [0] * 8)
                v[0x2000 + a:0x2000 + a + 8] = bytes([g.BRICK_C if led else g.SKY_C] * 8)
        v[0x1800:0x1B00] = bytes(list(range(256)) * 3)
        v[SAT] = 0xD0
        v[SPAT:SPAT + 32] = bytes(gen47.big(g.RUNNER))
        self.dots = set()
        self.spans = [(0, 0x1800), (0x2000, 0x3800), (0x1800, 0x1B00), (SAT, SAT + 1), (SPAT, SPAT + 32)]

    def sends(self):
        self.setw(SAT)
        for b in self.copy:
            self.out(b)
        r = self.runner
        x, y = r.x + 7, (r.y >> 8) + 15
        a = (y >> 3) * 256 + (x & 0xF8) + (y & 7)
        b = self.setr(a)
        self.setw(a)
        self.out(b | 0x80 >> (x & 7))
        self.dots.add((x, y))

    def run(self):
        k = ~self.pad() & 0xFF
        self.runner.step(k)
        r = self.runner
        self.copy[0], self.copy[1] = ((r.y >> 8) - 1) & 0xFF, r.x

    def ram(self):
        r = self.runner
        return dict(self.ram_common(), rx=r.x, ry=r.y >> 8, yfrac=r.y & 255, vy=r.vy,
                    landed=int(r.ground))

    BASE = None

    def picture(self, dots=None, copy=None):
        g = gen47
        dots = self.dots if dots is None else dots
        cp = self.copy if copy is None else copy
        if Jump.BASE is None:
            Jump.BASE = [[(g.BLACK if g.gen39.BRICK[y & 7] >> (7 - (x & 7)) & 1 else g.DARK_RED)
                          if g.ledge(x >> 3, y >> 3) else g.BLACK for x in range(256)] for y in range(192)]
        pic = [list(row) for row in Jump.BASE]
        for x, y in dots:
            assert not g.ledge(x >> 3, y >> 3)
            pic[y][x] = g.WHITE
        put_sprite(pic, g.RUNNER, cp[1], (cp[0] + 1) & 0xFF, g.RUNNER_COLOUR)
        return pic


# ================================================================ the maze
class Maze(Proto):
    def __init__(self, sym):
        g = gen47
        super().__init__("maze", [0x02, 0xE0, 0x06, 0xFF, 0x03, 0x36, 0x07, g.MAZE_BORDER],
                         g.MAZE_DEMO, sym)
        self.pos = 16 * g.START[0] + g.START[1]
        self.face = g.START[2]
        self.stage, self.wset, self.was = 0, 0, 0xFF
        self.buf = bytearray(12 * 256)
        v = self.vram
        v[0x2000:0x3800] = bytes([g.INK_PAPER] * 6144)
        for t in range(3):
            for p, b in g.fixed_patterns().items():
                v[0x800 * t + 8 * p:0x800 * t + 8 * p + 8] = bytes(b)
        v[0x1800:0x1B00] = bytes(g.screen_names(0))
        v[SPAT:SPAT + 32] = bytes(b for f in range(4) for b in g.rows8(*g.ARROWS[f]))
        self.copy = [0xD1, 0, 0, g.ARROW_COLOUR, 0xD0]
        self.here = self.fwd = self.lft = self.rgt = 0
        self.view()
        for i in range(12):                     # send, at the start, into set 0
            a = self.row_address(0, i)
            v[a:a + 96] = self.buf[256 * i:256 * i + 96]
        self.shown_view = (self.pos, self.face)
        self.mark()
        v[SAT] = 0xD0
        self.ports = []
        self.spans = ([(0x2000, 0x3800), (0x1800, 0x1B00), (SAT, SAT + 1), (SPAT, SPAT + 32)] +
                      [(0x800 * t + 8 * p, 0x800 * t + 8 * p + 8) for t in range(3)
                       for p in g.fixed_patterns()] +
                      [(self.row_address(0, i), self.row_address(0, i) + 96) for i in range(12)])

    @staticmethod
    def row_address(s, i):
        t, _, _ = gen47.window_rows()[i]
        return 0x800 * t + 8 * gen47.window_pattern(s, i, 0)

    # ---------------------------------------------------------- the routines
    def view(self):
        g = gen47
        r, c, f = self.pos >> 4, self.pos & 15, self.face
        for i in range(12):
            self.buf[256 * i:256 * i + 96] = bytes(96)
        for line in g.view_lines(r, c, f):
            for x, y in g.line_pixels(*line):
                a, m = g.buf_at(x, y)
                self.buf[a - g.BUF_AT] |= m
        ws = g.ways()[3 * f:3 * f + 3]
        self.fwd, self.lft, self.rgt = ws
        here = self.pos
        for k in range(4):
            if g.MAZE[(here + ws[0]) >> 4 & 15][(here + ws[0]) & 15] or k == 3:
                break
            here = (here + ws[0]) & 255
        self.here = here

    def mark(self):
        g = gen47
        self.copy[0] = 8 * (self.pos >> 4) + 8 * g.MAP_ROW - 1
        self.copy[1] = 8 * (self.pos & 15) + 8 * g.MAP_COL
        self.copy[2] = self.face

    def flip(self):
        self.wset ^= 1
        names = [gen47.window_pattern(self.wset, i, c) for i in range(12) for c in range(12)]
        for i in range(12):
            self.setw(0x1800 + 32 * (gen47.WIN_ROW + i) + gen47.WIN_COL)
            for n in names[12 * i:12 * i + 12]:
                self.out(n)
        self.stage = 0
        self.shown_view = self.sent_view
        self.mark()

    def send(self):
        s = self.wset ^ 1
        for i in range(12):
            self.setw(self.row_address(s, i))
            for b in self.buf[256 * i:256 * i + 96]:
                self.out(b)
        self.stage = 2
        self.sent_view = self.drawn_view

    def sends(self):
        if self.stage == 2:
            self.flip()
        self.setw(SAT)
        for b in self.copy:
            self.out(b)

    def run(self):
        held = self.pad()
        down = ~held & self.was & 0xFF
        self.was = held
        if self.stage == 1:
            self.send()
            return
        if self.stage == 2 or not down:
            return
        g = gen47
        if down & g.LEFT:
            self.face = (self.face - 1) & 0xFF
        if down & g.RIGHT:
            self.face = (self.face + 1) & 0xFF
        self.face &= 3
        if down & g.UP:
            dr, dc = g.DIRS[self.face]
            ahead = (self.pos + 16 * dr + dc) & 255
            if not g.MAZE[ahead >> 4][ahead & 15]:
                self.pos = ahead
        self.view()
        self.drawn_view = (self.pos, self.face)
        self.stage = 1

    def ram(self):
        return dict(self.ram_common(), pos=self.pos, face=self.face, stage=self.stage, wset=self.wset,
                    was=self.was, here=self.here, fwd=self.fwd, lft=self.lft, rgt=self.rgt)

    VIEWS = {}

    def picture(self, shown=None, copy=None):
        g = gen47
        pos, face = self.shown_view if shown is None else shown
        cp = self.copy if copy is None else copy
        if (pos, face) not in Maze.VIEWS:
            Maze.VIEWS[(pos, face)] = g.view_pixels(pos >> 4, pos & 15, face)
        view = Maze.VIEWS[(pos, face)]
        fixed = g.fixed_patterns()
        names = g.screen_names(0)
        pic = []
        for y in range(192):
            row = []
            for x in range(256):
                wx, wy = x - 8 * g.WIN_COL, y - 8 * g.WIN_ROW
                if 0 <= wx < g.WIN and 0 <= wy < g.WIN:
                    on = view[wy][wx]
                else:
                    n = names[32 * (y >> 3) + (x >> 3)]
                    on = fixed[n][y & 7] >> (7 - (x & 7)) & 1
                row.append(g.BLACK if on else g.WHITE)
            pic.append(row)
        arrow = [b << 8 for b in g.rows8(*g.ARROWS[cp[2]])] + [0] * 8
        put_sprite(pic, arrow, cp[1], (cp[0] + 1) & 0xFF, g.ARROW_COLOUR)
        return pic


MODELS = {"cave": Cave, "jump": Jump, "maze": Maze}


def checks():
    """the plans' plain facts"""
    g = gen47
    lands = g.jump_landings(g.JUMP_PATH)
    moves = g.maze_moves()
    assert len(g.MAZE_KEYS) >= g.FRAMES + 10, "the maze's demo must outlast the film"
    return {"pairs": g.NP, "pmap_rows": len(g.PMAP), "lap_cave": len(g.CAVE_KEYS),
            "lap_jump": len(g.JUMP_KEYS), "landings": [list(x) for x in lands],
            "moves": len(moves), "maze_frames": len(g.MAZE_KEYS),
            "demo_pairs": [len(g.CAVE_DEMO), len(g.JUMP_DEMO), len(g.MAZE_DEMO)]}


if __name__ == "__main__":
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
    import probe
    print(checks())
    for name, M in MODELS.items():
        m = M(probe.sym(os.path.join(HERE, f"{name}.sym")))
        n = 0
        for _ in range(gen47.FRAMES):
            s, r = m.step_loop()
            n += len(s) + len(r)
        print(name, "ports", n, m.ram())
