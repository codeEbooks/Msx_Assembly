#!/usr/bin/env python3
"""model54.py - chapter 54's LANTERN KEEP in Python, a loop at a time: the
title drawn a row of cells a frame and shown, the steps of the title
counted, the demo played from its pairs a step at a time (frames.asm: a
frame at a time), a key that ends it, DRAW's six blocks and row 0, and the
best kept only after a game. The rest is chapter 46's model46.Keep, which
meas54.py holds against every loop of every film, as meas46.py did.

    python3 model54.py      play_jp.events and play_eu.events: the keys of a
                            game, SPACE at the title and then the game
                            planned: on the 60 Hz machine the demo's own
                            keys, a step a frame; on the 50 Hz machine
                            chapter 46's player, planning on this model

The VRAM is kept as the Z80 leaves it: unrow below is chapter 53's unlz as
the cartridge runs it, a stream at a time, stopping where a row ends, and
reading its copies back from the VRAM it has written.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "tools"))
sys.path.insert(0, HERE)
import gen54       # noqa: E402
sys.path.insert(0, os.path.join(REPO, "ch46"))
import model46     # noqa: E402  (chapter 46's model, with its own vdpscreen.py and player37.py)
sys.path.remove(os.path.join(REPO, "ch46"))
import probe as dbg  # noqa: E402

gen46, gen45 = gen54.gen46, gen54.gen45
EU, JP = gen54.EU, gen54.JP
TITLE, PLAY, FLIP, MAP, HIT, OVER, WIN, DRAW = range(8)
NAMES = model46.NAMES
EVENT_AHEAD = {}                    # filled from the film of INIT: see ahead() below
SPRITE_NUMBER0 = 31                 # the status's sprite number when INIT ends: the C-BIOS's
                                    # last frame with the display on looked at all 32 (measured)
TAG = {EU: "eu", JP: "jp"}


def unrow(stream, pos, addr, upto, vram):
    """chapter 53's unlz from byte POS of STREAM, writing VRAM from ADDR, until
    ADDR is in page UPTO -> (pos, addr): the next count and the next address"""
    while True:
        if addr >> 8 == upto:
            return pos, addr
        c = stream[pos]
        pos += 1
        assert c, "the end of a stream before its last row"
        if c < 128:
            vram[addr:addr + c] = bytes(stream[pos:pos + c])
            pos += c
            addr += c
        else:
            n, d = c - 128 + 3, stream[pos] + 1
            pos += 1
            src = addr - d
            vram[addr:addr + n] = bytes(vram[src:src + n])      # n <= d: whole before it starts
            addr += n


class Keep(model46.Keep):
    """the game of NAME, game.asm or frames.asm, a loop at a time"""

    def __init__(self, machine=JP, name="game", lamps_frame=False, keep_was=False, sym_path=None):
        self.name = name
        self.lamps_frame, self.keep_was = lamps_frame, keep_was
        self.frames = name == "frames"
        self.sym = dbg.sym(sym_path or os.path.join(HERE, f"{name}.sym"))
        self.pkeys = 0
        self.demo = 0
        self.dleft = 0
        self.dnext = None               # 0 in the RAM until a demo is set up
        self.idle = 0
        self.number = SPRITE_NUMBER0    # the status's sprite number, as INIT finds it
        self.drawn_on = False           # the display on for some of the frame drawn
        self.names_known = False        # the name table: the machine's until the title shows
        self.part = 0
        self.pnext = self.cnext = 0
        self.pvram = self.cvram = 0
        self.upto = 0
        self.r1 = 0xA2
        model46.Keep.__init__(self, machine, rom=os.path.join(HERE, name))
        # INIT has no sets: the tables are what the machine left, until the title
        # is drawn. They are not looked at before then
        self.events = []

    # ---------------------------------------------------------- the status
    def isr_head(self):
        model46.Keep.isr_head(self)
        if self.drawn_on:
            self.number = self.stat & 0x1F
        else:                           # nothing drawn: no sprite looked at, none met
            self.stat = 0x80 | self.number

    # ---------------------------------------------------------- the states
    def run(self, keys=None):
        before = self.r1 & 0x40
        self.run_state()
        self.drawn_on = bool(before or self.r1 & 0x40)

    def run_state(self):
        {TITLE: self.title1, PLAY: self.play1, FLIP: self.flip1, MAP: self.map1, HIT: self.hit1,
         OVER: self.over1, WIN: self.over1, DRAW: self.draw1}[self.state]()

    def go(self, state):
        self.state = state
        self.events.append((self.loop, gen54.STATES[state]))
        {TITLE: self.title0, PLAY: self.play0, FLIP: self.flip0, MAP: self.map0, HIT: self.hit0,
         OVER: self.over0, WIN: self.win0, DRAW: self.draw0}[state]()

    def totitle(self):
        self.r1 = 0xA2
        self.go(TITLE)

    def title0(self):
        self.music.retune()
        self.part = 0
        self.demo = 0
        self.pnext, self.pvram = 0, 0x0000
        self.cnext, self.cvram = 0, 0x2000
        if not self.keep_was:
            self.was = 0
        self.copy = (list(self.copy) + [0] * 13)[:13]     # the 13 bytes sends sends: 5 at INIT's model
        self.copy[0] = 0xD0

    def title1(self):
        if self.part < gen54.ROWS:
            self.pnext, self.pvram = unrow(gen54.TPAT_LZ, self.pnext, self.pvram, self.part + 1, self.vram)
            self.upto = self.part + 1
            self.cnext, self.cvram = unrow(gen54.TCOL_LZ, self.cnext, self.cvram, self.part + 0x21,
                                           self.vram)
            self.upto = self.part + 0x21
            self.part += 1
            return
        if self.part == gen54.ROWS:
            self.part += 1
            self.shown()
            self.idle = 0
            self.due = 0
            return
        self.idle += self.paced()
        if self.presses() & 0x10:
            self.begin(0)
        elif self.idle >= gen54.IDLE:
            self.begin(1)

    def begin(self, demo):
        self.demo = demo
        self.events.append((self.loop, "DEMO" if demo else "PRESSED"))
        self.go(DRAW)

    @property
    def vnames(self):
        return list(self.vram[NAMES:NAMES + 768]) if self.names_known else None

    def shown(self):
        self.names_known = True
        self.vram[NAMES:NAMES + 768] = bytes(list(range(256)) * 3)
        digits = [b >> s & 15 for b in self.hi for s in (4, 0)]
        for k, d in enumerate(digits):
            a = gen54.THI + 8 * k
            self.vram[a:a + 8] = bytes(gen54.glyph(chr(0x30 + d)))
            self.vram[0x2000 + a:0x2000 + a + 8] = bytes([gen54.WHITE << 4 | gen54.BLACK] * 8)
        self.r3, self.r4 = gen45.MAP_R3, gen45.MAP_R4
        self.r1 = 0xE2
        self.events.append((self.loop, "SHOWN"))

    def draw0(self):
        self.r1 = 0xA2
        self.part = 0

    def draw1(self):
        if self.part < gen54.BLOCKS:
            k = self.part
            self.part += 1
            third, colours = k >> 1, k & 1
            a = third * 0x800 + colours * 0x2000
            self.vram[a:a + 2048] = bytes(gen46.colour_set() if colours else gen46.shape_set())
            return
        self.vram[NAMES:NAMES + 32] = bytes(gen46.row0())
        self.setup()
        self.go(FLIP)

    def setup(self):
        model46.Keep.setup(self)
        self.copy[0:13] = gen54.GCOPY
        self.dleft = 1
        self.dnext = 0

    def flip1(self):
        self.r1 = 0xE2
        model46.Keep.flip1(self)

    # ---------------------------------------------------------- the play
    def pad(self):
        if not self.demo:
            self.pkeys = self.held
            return
        self.dleft -= 1
        if self.dleft:
            return
        if self.dnext >= len(gen54.DEMO):
            self.dleft = 1
            self.pkeys = 0xFF
            return
        self.dleft, self.pkeys = gen54.DEMO[self.dnext]
        self.dnext += 1

    def walk(self):
        held, self.held = self.held, self.pkeys
        try:
            return model46.Keep.walk(self)
        finally:
            self.held = held

    def play1(self):
        if self.fresh:
            self.mini()
            self.play0()
            return
        if self.stat & 0x20:
            self.events.append((self.loop, "TOUCH", self.room, list(self.copy[:12])))
            self.go(HIT)
            return
        if self.demo:
            if (self.held | 0xC0) != 0xFF:
                self.events.append((self.loop, "STOPPED"))
                self.totitle()
                return
        elif self.presses() & gen45.MAP_BIT:
            self.go(MAP)
            return
        if self.frames:
            self.pad()
        for _ in range(self.paced()):
            if not self.frames:
                self.pad()
            way = self.walk()
            if way:
                self.leave(way)
                return
            self.guards()
            if self.clock():
                self.go(OVER)
                return
            if self.lamps_frame:
                continue
            self.lamps()
            if self.state != PLAY:
                return
        if self.lamps_frame:
            self.lamps()

    def over1(self):
        if self.dimmed < 16:
            self.glow(self.dimmed, gen46.PAPER_C)
            self.dimmed += 1
        if self.countdown():
            return
        self.totitle()

    def ending(self, text):
        hi = list(self.hi)
        model46.Keep.ending(self, text)
        if self.demo:
            self.hi = hi
            self.put3(NAMES + 32 * gen46.HI_DIG[1] + gen46.HI_DIG[0], self.hi)
            ev = self.events[-1]
            self.events[-1] = ev[:4] + (model46.bcd3(self.hi),) + ev[5:]

    # ---------------------------------------------------------- what the RAM holds
    def ram(self):
        out = model46.Keep.ram(self)
        s = self.sym
        out.update({"pkeys": self.pkeys, "demo": self.demo, "dleft": self.dleft,
                    "dnext": 0 if self.dnext is None else s["dpairs"] + 2 * self.dnext, "idle": self.idle, "part": self.part,
                    "pnext": s["tpat"] + self.pnext, "pvram": self.pvram,
                    "cnext": s["tcol"] + self.cnext, "cvram": self.cvram, "upto": self.upto})
        return out


# ---------------------------------------------------------------- the plays
class DemoPlayer:
    """a game on the 60 Hz machine with the demo's keys: SPACE at the title,
    then for each loop that will take a step the keys of the next step"""

    def __init__(self, press=model46.PRESS, after=model46.AFTER):
        self.k = 0
        self.press, self.after = press, after
        self.ended = None
        self.done = False

    def choose(self, g):
        if g.state == TITLE:
            if self.ended is not None:
                if g.part > gen54.ROWS and g.loop - self.ended >= self.after:
                    self.done = True
                return set()
            return {"space"} if self.press <= g.ticks < self.press + model46.HELD else set()
        if g.state in (OVER, WIN):
            self.ended = g.loop
        if g.state != PLAY or g.fresh or g.stat & 0x20 or g.steps_owed() == 0:
            return set()
        assert g.steps_owed() == 1, "a frame of two steps"
        held = gen54.DEMO_KEYS[self.k]
        self.k += 1
        return {name for b, name in gen54.KEY_NAMES.items() if not held & b}


class Planner(model46.Player):
    """chapter 46's player, on this chapter's game: it leaves the title once
    the title is shown, and stops once the title is shown again"""

    def title(self, g):
        if self.ended is not None:
            if g.part > gen54.ROWS and g.loop - self.ended >= model46.AFTER:
                self.done = True
            return set()
        return {"space"} if model46.PRESS <= g.ticks < model46.PRESS + model46.HELD else set()

    def choose(self, g):
        if g.state in (OVER, WIN):
            self.ended = g.loop
        return model46.Player.choose(self, g)


def plan(machine, player, name="game", limit=40000):
    """the model played by PLAYER: (the keys of each loop, the game)"""
    g = Keep(machine, name)
    keys_by_loop = []
    while not player.done and g.loop < limit:
        g.loop += 1
        g.isr_head()
        keys = player.choose(g)
        g.isr_tail(keys)
        g.sends()
        keys_by_loop.append((g.ticks, frozenset(keys)))
        g.run()
    assert player.done, "the game did not end"
    return keys_by_loop, g


def events_of(keys_by_loop, machine):
    out, last = {}, frozenset()
    for t, k in keys_by_loop:
        if k != last:
            out[t + EVENT_AHEAD[machine]] = k
            last = k
    return out


def events_path(play, machine):
    return os.path.join(HERE, f"{play}_{TAG[machine]}.events")


def write_events(path, ev, machine, what):
    hz = {EU: "50", JP: "60"}[machine]
    lines = [f"# {os.path.basename(path)} -- chapter 54: {what} on the {hz} Hz machine,",
             "# written by model54.py: a frame (from INIT) and the keys held from then on"]
    for f, k in sorted(ev.items()):
        lines.append(f"{f} {' '.join(sorted(k)) or '-'}")
    with open(path, "w") as fh:
        fh.write("\n".join(lines) + "\n")


read_events, keys_at, tcl_events = model46.read_events, model46.keys_at, model46.tcl_events


def replay(ev, loops, machine, name="game"):
    g = Keep(machine, name)
    for _ in range(loops):
        g.step_loop(keys_at(ev, g.ticks + 1 + EVENT_AHEAD[machine]))
    return g


def main():
    for m in (JP, EU):
        player = DemoPlayer() if m == JP else Planner()
        keys, g = plan(m, player)
        ev = events_of(keys, m)
        what = ("a game with the demo's keys, a step a frame" if m == JP else
                "a game planned by chapter 46's player")
        write_events(events_path("play", m), ev, m, what)
        g2 = replay(ev, g.loop + 1, m)
        assert g2.ram() == g.ram() and g2.events == g.events
        ended = [e for e in g.events if e[1] == "ENDED"]
        print(f"play_{TAG[m]}.events: {len(ev)} changes, {g.loop + 1} loops; {ended}")


# the frame of INIT in which the first loop wakes: INIT's T-states, the title's
# first frame included, as meas54.py measured them (checked there)
EVENT_AHEAD.update({JP: 1, EU: 1})

if __name__ == "__main__":
    main()
