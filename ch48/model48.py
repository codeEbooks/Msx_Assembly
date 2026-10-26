#!/usr/bin/env python3
"""model48.py -- chapter 48's long cave in Python, a loop at a time.

    python3 model48.py          long, far and guess run for gen48.FRAMES loops,
                                and the plain checks of the plans

Long keeps what the cartridge keeps in the RAM, and what the cartridge's
mapper holds: for an ASCII16 cartridge the bank each of pages 1 and 2 shows,
for a Konami SCC one, as openMSX takes guess.rom, the 8 KB block each of the
four windows from $4000 shows. It makes, in order, the bytes the loop sends
to the VDP's two ports, from the bank the mapper puts in page 2, and keeps
the VRAM. It also says, for every frame, two pictures, worked out from the
world and not from the VRAM: the one the cartridge means to show, the world
at the window's column with the rock and colours of the window's bank; and
the one the mapper serves, the world at the column of the bytes page 2
really held when the window was written. meas48.py holds the debugger's
RAM, mapper and port log against the first, and the screen line by line
against the pictures.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gen48  # noqa: E402
sys.path.remove(HERE)
sys.path.insert(0, HERE)
for _m in ("vdpscreen",):
    sys.modules.pop(_m, None)
import vdpscreen  # noqa: E402

assert os.path.dirname(os.path.abspath(vdpscreen.__file__)) == HERE

gen47 = gen48.gen47
SAT, SPAT = 0x1B00, 0x3800
D, C = 0x98, 0x99                   # the VDP's data and control ports
BLOCKS = 16                         # the cartridge's 8 KB blocks: 128 KB


class Mapper:
    """the cartridge's mapper, as openMSX works it: ASCII16, a register for
    page 1 at $6000-$67FF and one for page 2 at $7000-$77FF, a bank of 16 KB
    each, both bank 0 at the start; or Konami SCC, a register for each 8 KB
    window from $4000 at $5000, $7000, $9000 and $B000, 2 KB each, blocks 0
    to 3 at the start"""
    def __init__(self, kind):
        self.kind = kind
        self.blocks = [0, 1, 0, 1] if kind == "ascii16" else [0, 1, 2, 3]

    def write(self, addr, v):
        if self.kind == "ascii16":
            if 0x6000 <= addr < 0x6800:
                b = v % (BLOCKS // 2)
                self.blocks[0:2] = [2 * b, 2 * b + 1]
            elif 0x7000 <= addr < 0x7800:
                b = v % (BLOCKS // 2)
                self.blocks[2:4] = [2 * b, 2 * b + 1]
        else:
            for w, base in enumerate((0x5000, 0x7000, 0x9000, 0xB000)):
                if base <= addr < base + 0x800:
                    self.blocks[w] = v % BLOCKS

    def romblocks(self):
        """what openMSX's debuggable NAME.rom romblocks reads at $4000,
        $6000, $8000 and $A000: the mapper's own block, 16 KB or 8 KB"""
        if self.kind == "ascii16":
            return [b // 2 for b in self.blocks]
        return list(self.blocks)

    def bank2(self):
        """the 16 KB bank of the cartridge page 2 shows"""
        a, b = self.blocks[2:4]
        assert a % 2 == 0 and b == a + 1, ("page 2 shows two halves of different banks", self.blocks)
        return a // 2


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


STRIPS = {}


def strip(bank, c):
    """the world's tile column C drawn with bank's tiles: 192 rows of 8 codes"""
    key = (bank, c % gen48.COLS)
    if key not in STRIPS:
        out = []
        for y in range(192):
            row = []
            for i in range(8):
                bit, ink = gen48.pixel(8 * (c % gen48.COLS) + i, y, bank)
                row.append(ink if bit else gen48.BLACK)
            out.append(row)
        STRIPS[key] = out
    return STRIPS[key]


def world_picture(col, shift, bank, copy):
    """the paper: the world from pixel SHIFT of column COL, with bank's rock
    and colours, and the ship at its attributes COPY"""
    strips = [strip(bank, col + j) for j in range(33)]
    pic = [sum((s[y] for s in strips), [])[shift:shift + 256] for y in range(192)]
    put_sprite(pic, gen47.SHIP, copy[1], (copy[0] + 1) & 0xFF, gen47.SHIP_COLOUR)
    return pic


class Long:
    """long.asm, far.asm or guess.asm; and the workshop's round.asm and
    once.asm. MAPPER: the type openMSX is told, if not the one it takes"""
    def __init__(self, sym, kind="long", mapper=None, start=None):
        g = gen47
        self.kind = kind
        self.sym = sym
        self.mapper = Mapper(mapper or ("konamiscc" if kind == "guess" else "ascii16"))
        self.bank2_at = gen48.BANK2_GUESS if kind == "guess" else gen48.BANK2
        self.vram = bytearray(16384)
        self.regs = [0x02, 0xE2, 0x06, 0x9F, 0x00, 0x36, 0x07, g.CAVE_BORDER]
        self.addr = 0
        self.ports = []
        self.demo = g.CAVE_DEMO
        self.ticks, self.held, self.dleft, self.dnext, self.stat = 0, 0, 1, 0, 0
        self.loop = -1
        self.copy = [g.CAVE_Y0 - 1, g.SHIP_AT[0], 0, g.SHIP_COLOUR, 0xD0]
        self.shift, self.table, self.fresh = 0, 0, 0
        self.wbank, self.wseg, self.woff = start or gen48.START
        self.pending = self.shown = 0
        self.want = {}                  # each table's window: (column, bank) meant
        self.served = {}                # and (column, bank) of the bytes page 2 held
        self.states = []
        self.snaps = {}                 # far.asm: the VRAM of each frame whose pairs are another bank's
        # ---- setup, as the cartridge does it before its first frame
        v = self.vram
        v[0x2000:0x2008] = bytes([gen48.SKY_C] * 8)
        self.table = 0x1C
        self.window()
        self.shown = self.pending
        self.table = 0x18
        self.window()
        self.fresh = 1
        self.mapper.write(self.bank2_at, self.shown)
        self.bshow()
        self.shift = 1
        v[SAT] = 0xD0
        v[SPAT:SPAT + 32] = bytes(gen47.big(g.SHIP))
        self.ports = []
        nb = 8 * max(gen48.NPS.values())
        self.spans = [(0, 8 + nb), (0x2000, 0x2008 + nb), (0x1800, 0x1B00), (0x1C00, 0x1F00),
                      (SAT, SAT + 1), (SPAT, SPAT + 32)]

    # ---------------------------------------------------------- the VDP's ports
    def setw(self, addr):
        self.ports += [(C, addr & 0xFF), (C, (addr >> 8) & 0x3F | 0x40)]
        self.addr = addr & 0x3FFF

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

    def bshow(self):
        """the bshow of the bank page 2 shows: its pairs at the shift, and
        their colours when fresh says so"""
        b = self.mapper.bank2()
        pairs = gen48.BANK_DATA[b][0]
        self.setw(0x0008)
        for a, b2 in pairs:
            for x in gen48.shifted(b, a, b2, self.shift):
                self.out(x)
        if self.fresh:
            self.fresh = 0
            self.setw(0x2008)
            for a, b2 in pairs:
                for x in gen48.pair_colours(b, a, b2):
                    self.out(x)
        return b

    def sends(self):
        self.setw(SAT)
        for x in self.copy:
            self.out(x)
        if self.shift == 0:
            same = self.pending == self.shown
            self.shown = self.pending
            self.fresh = 0 if same else 1
            if self.kind == "once":
                self.mapper.write(self.bank2_at, self.shown)
        if self.kind not in ("far", "once"):
            self.mapper.write(self.bank2_at, self.shown)
        self.sent_bank = self.bshow()
        if self.shift == 0:
            self.table ^= 0x18 ^ 0x1C
            self.reg(2, self.table >> 2)
        self.states.append(self.picture_state())
        if self.kind == "far" and self.sent_bank != self.want[self.table][1]:
            self.snaps[len(self.states) - 1] = (bytes(self.vram), list(self.regs))

    def run(self):
        k = ~self.pad() & 0xFF
        x, y = gen47.ship_step(self.copy[1], self.copy[0] + 1, k)
        self.copy[0], self.copy[1] = y - 1, x
        if self.shift == 0:
            self.window()
        self.shift = (self.shift + 1) & 7

    def window(self):
        self.pending = self.wbank
        self.mapper.write(self.bank2_at, self.wbank)
        b = self.mapper.bank2()
        hidden = self.table ^ (0x18 ^ 0x1C)
        rows = gen48.BANK_DATA[b][1][self.wseg]
        self.want[hidden] = (gen48.col_of(self.wbank, self.wseg, self.woff), self.wbank)
        self.served[hidden] = (gen48.col_of(b, self.wseg, self.woff), b)
        self.setw((hidden << 8) + 32)
        for i in range(4):
            for n in rows[i][self.woff:self.woff + 32]:
                self.out(n)
        self.setw((hidden << 8) + 32 * 17)
        for i in range(4, 11):
            for n in rows[i][self.woff:self.woff + 32]:
                self.out(n)
        if self.kind == "once":
            self.mapper.write(self.bank2_at, self.shown)
        self.woff += 1
        if self.woff == gen48.SEGW:
            self.woff = 0
            self.wseg += 1
            if self.wseg == gen48.SEGS:
                self.wseg = 0
                self.wbank += 1
                if self.wbank == gen48.BANKS + 1:
                    self.wbank = 1

    def step_loop(self):
        self.loop += 1
        self.isr()
        self.ports = []
        self.sends()
        sent = self.ports
        self.ports = []
        self.run()
        return sent, self.ports

    def ram(self):
        return {"stat": self.stat, "ticks": self.ticks, "held": self.held, "dleft": self.dleft,
                "dnext": self.sym["demo"] + 2 * self.dnext, "copy": list(self.copy),
                "shift": self.shift, "table": self.table, "wbank": self.wbank, "wseg": self.wseg,
                "woff": self.woff, "pending": self.pending, "shown": self.shown, "fresh": self.fresh,
                "blocks": self.mapper.romblocks()}

    # ---------------------------------------------------------- the pictures
    def picture_state(self):
        """what the pictures need, as the sends left it: the window meant
        and its bank, the window served and its bank, the bank whose pairs
        were sent, the shift and the ship"""
        return (self.want[self.table], self.served[self.table], self.sent_bank, self.shift,
                tuple(self.copy))

    @staticmethod
    def picture(want, served, sent, shift, copy):
        """the picture the cartridge means to show"""
        return world_picture(want[0], shift, want[1], copy)

    @staticmethod
    def served_picture(want, served, sent, shift, copy):
        """the picture of the bytes the mapper served, when the pairs sent
        are the served bank's: None when they are not"""
        if sent != served[1]:
            return None
        return world_picture(served[0], shift, served[1], copy)


MODELS = {"long": Long, "far": lambda s: Long(s, "far"), "guess": lambda s: Long(s, "guess"),
          "round": lambda s: Long(s, "round", start=(gen48.BANKS, gen48.SEGS - 1, gen48.START[2])),
          "once": lambda s: Long(s, "once")}


def checks():
    """the plans' plain facts"""
    g = gen48
    b, s, o = g.START
    first_next = (g.SEGW - o)           # windows before the next bank's first
    return {"pairs": dict(g.NPS), "columns": g.COLS, "banks": g.BANKS, "segments": g.SEGS,
            "segment_columns": g.SEGW, "pmap_pages": g.SEGS * len(g.SCROLL_ROWS),
            "pmap_bytes": g.SEGS * len(g.SCROLL_ROWS) * 256, "bshow_at": g.BSHOW_AT,
            "start": list(g.START), "windows_to_bank2": first_next,
            "frames_world": 8 * g.COLS}


if __name__ == "__main__":
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
    import probe
    print(checks())
    for name in ("long", "far", "guess"):
        m = MODELS[name](probe.sym(os.path.join(HERE, f"{name}.sym")))
        n = 0
        for _ in range(gen48.FRAMES):
            s, r = m.step_loop()
            n += len(s) + len(r)
        print(name, "ports", n, m.ram())
