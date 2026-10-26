#!/usr/bin/env python3
"""model45.py - LANTERN KEEP's world, in Python, and a player who plans a
walk through every room.

    python3 model45.py          game_eu.events and game_jp.events

Keep is the game as gen45.py writes it, a loop at a time, on one of the two
machines: the interrupt (the status, from the frame the sends before drew,
by vdpscreen.py's rule 11; the frame counted; its lines owed to the game's
steps; the keys), the sends (the explorer's attributes, the names queued,
the whole page when one was left), and the state's routine, which takes a
step for each 262 lines owed. It keeps what the RAM keeps, the copy of the
names, the map's page and the rooms' pictures too, and what the VRAM holds,
so that meas45.py can hold every loop of a film against it.

Player chooses the keys of each loop from the game as the loop's logic finds
it, knowing how many steps the loop will take. It goes to the nearest room
not yet seen, a room at a time, through the doors; across each room it
takes, each loop, the keys whose steps bring it nearest the door it goes out
by, counted in steps of walk's own (distances below). When the sixth room
has been seen it looks at the map for a while; when all sixteen have, it
looks again, and the walk ends. A plan for each machine: the same keys at
the 50 Hz machine's loops would not be the same walk.
"""
import os
import sys
from collections import deque

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gen45       # noqa: E402
import vdpscreen   # noqa: E402

assert os.path.dirname(os.path.abspath(vdpscreen.__file__)) == HERE

EU, JP = gen45.EU, gen45.JP
TITLE, PLAY, FLIP, MAP = range(4)
NAMES = 0x1800
SAT, SPAT = 0x1B00, 0x3800
LINES = {EU: 313, JP: 262}
STEPL = 262
EVENT_AHEAD = 5                     # keys for the loop whose ticks is t: events at frame t + 5,
                                    # for INIT's sets fill frames 0 to 5 and the loop with ticks t
                                    # wakes in frame t + 5 (meas45.py holds every loop to it)
ROW8 = {"space": 0x01, "left": 0x10, "up": 0x20, "down": 0x40, "right": 0x80}
ROW4 = {"m": 0x04}
JOY_IDLE = 0xBF                     # joystick 1 with nothing held, as joy reads it
N, E, S, W = gen45.N, gen45.E, gen45.S, gen45.W
WAY_OF = {0: N, 1: E, 2: S, 3: W}


def bcd(n):
    return int(f"{n:02X}")


def tobcd(n):
    return int(str(n), 16)


def keys_byte(keys):
    """rows 8 and 4 of the keyboard with KEYS held, as keys turns them into
    register 14's way, ANDed with the idle joystick: the byte held gets"""
    row8 = 0xFF
    for k in keys:
        row8 &= ~ROW8.get(k, 0) & 0xFF
    a = gen45.gen35.kbd_table()[(row8 >> 4) & 15] | (row8 & 1) << 4 | 0xE0
    if "m" in keys:
        a &= 0xDF
    return a & JOY_IDLE


def regs_of(r3, r4):
    return [0x02, 0xE2, 0x06, r3, r4, 0x36, 0x07, gen45.BORDER]


def picture_bytes(names):
    """mini: a room's picture from the copy's rows 1 to 23, 24 rows of 4 bytes"""
    out = []
    for r in range(1, 24):
        for cx in range(4):
            v = 0
            for c in range(8):
                v = v << 1 | (names[32 * r + 8 * cx + c] >= gen45.BRICK)
            out.append(v)
    return out + [0, 0, 0, 0]


def picture_order(pic):
    """picture: the 96 bytes as they go to the VRAM, a name's eight lines at
    a time: names in rows of four, each a column of the picture"""
    out = []
    for cy in range(3):
        for cx in range(4):
            for j in range(8):
                out.append(pic[4 * (8 * cy + j) + cx])
    return out


class Keep:
    """the game, a loop at a time, on MACHINE; TORN: torn.asm"""

    def __init__(self, machine=JP, torn=False, onethird=False, pic_flip1=False):
        self.machine, self.torn = machine, torn
        self.onethird, self.pic_flip1 = onethird, pic_flip1
        self.lines = LINES[machine]
        # what INIT leaves: the variables' page all 0, the copies all 0
        self.ticks = 0
        self.state = TITLE
        self.held = None
        self.was = 0
        self.room = 0
        self.seen = 0
        self.fresh = 0
        self.queue = []
        self.keepy = 0
        self.whole = 0
        self.wsrc = 0
        self.wr3 = self.wr4 = 0
        self.copy = [0] * 5
        self.due = 0
        self.been = [0] * 16
        self.names = [0] * 768
        self.mapn = [0] * 736
        self.minis = [[0] * 96 for _ in range(16)]
        # the VRAM: INIT's sets, the explorer's patterns, no sprites
        self.vram = bytearray(16384)
        for t in range(3):
            self.vram[0x800 * t:0x800 * t + 2048] = bytes(gen45.shape_set())
            self.vram[0x2000 + 0x800 * t:0x2000 + 0x800 * t + 2048] = bytes(gen45.colour_set())
        self.vram[SPAT:SPAT + 32] = bytes(gen45.SPRITE_PATTERNS)
        self.vram[SAT] = 0xD0
        self.r3, self.r4 = gen45.GAME_R3, gen45.GAME_R4
        self.drawn_sat = bytes(self.vram[SAT:SAT + 32])
        self.drawn_regs = (self.r3, self.r4)
        self.stat = None
        self.loop = -1
        self.steps_taken = []           # (loop, steps) for each loop that took some
        self.events = []
        self.screen = False             # a page sent this loop
        self.title0()

    # ---------------------------------------------------------- the VRAM
    @property
    def vnames(self):
        return list(self.vram[NAMES:NAMES + 768])

    def regs(self):
        return regs_of(self.r3, self.r4)

    def status_of(self, sat):
        v = bytearray(16384)
        v[SAT:SAT + 32] = sat
        v[SPAT:SPAT + 32] = bytes(gen45.SPRITE_PATTERNS)
        five, number = vdpscreen.sprite_status(v, regs_of(gen45.GAME_R3, gen45.GAME_R4))
        c, _ = vdpscreen.coincidence(v, regs_of(gen45.GAME_R3, gen45.GAME_R4))
        return 0x80 | five << 6 | c << 5 | number

    # ---------------------------------------------------------- the interrupt and the sends
    def isr(self, keys):
        self.isr_head()
        self.isr_tail(keys)

    def isr_head(self):
        self.screen = False
        self.stat = self.status_of(self.drawn_sat)
        self.ticks = (self.ticks + 1) & 0xFFFF
        self.due = (self.due + self.lines) & 0xFFFF

    def isr_tail(self, keys):
        self.held = keys_byte(keys)

    def show(self, src, r3, r4):
        """the registers and rows 1 to 23 of a page to the VRAM"""
        self.r3, self.r4 = r3, r4
        self.vram[NAMES + 32:NAMES + 768] = bytes(src)
        self.screen = True

    def sends(self):
        self.vram[SAT:SAT + 5] = bytes(self.copy)
        for addr, name in self.queue:
            self.vram[(addr & 0x3FFF)] = name
        self.queue = []
        if self.whole:
            self.whole = 0
            self.show(self.names[32:] if self.wsrc == "names" else self.mapn, self.wr3, self.wr4)
        self.drawn_sat = bytes(self.vram[SAT:SAT + 32])
        self.drawn_regs = (self.r3, self.r4)

    def run(self, keys=None):
        {TITLE: self.title1, PLAY: self.play1, FLIP: self.flip1, MAP: self.map1}[self.state]()

    def go(self, state):
        self.state = state
        self.events.append((self.loop, gen45.STATES[state]))
        {TITLE: self.title0, PLAY: self.play0, FLIP: self.flip0, MAP: self.map0}[state]()

    def step_loop(self, keys):
        self.loop += 1
        self.isr(keys)
        self.sends()
        self.run()

    def steps_owed(self):
        """what paced will give this loop's logic: none in a picture's loop"""
        if self.state != PLAY or self.fresh:
            return 0
        return self.due // STEPL

    def paced(self):
        b = self.due // STEPL
        self.due -= b * STEPL
        assert 1 <= b <= 255, b
        self.steps_taken.append((self.loop, b))
        return b

    def presses(self):
        b = self.was
        self.was = self.held
        return ~self.held & b & 0xFF

    def page(self, src, r3, r4):
        self.wsrc, self.wr3, self.wr4, self.whole = src, r3, r4, 1

    def post(self, cell, name):
        self.names[cell] = name
        self.queue.append((0x1800 + 0x4000 + cell, name))
        assert len(self.queue) <= gen45.QUEUE_MAX, len(self.queue)

    def post2(self, cell, byte):
        self.post(cell, 0x30 + (byte >> 4))
        self.post(cell + 1, 0x30 + (byte & 15))

    # ---------------------------------------------------------- the states
    def title0(self):
        self.vram[NAMES:NAMES + 768] = bytes(gen45.title_names())
        self.screen = True
        self.copy = gen45.title_copy()

    def title1(self):
        if self.held & 0x10:
            return
        self.setup()
        self.events.append((self.loop, "PRESSED"))
        self.go(FLIP)

    def setup(self):
        self.seen = 0
        self.queue = []
        self.been = [0] * 16
        self.room = gen45.START
        self.copy = gen45.first_copy()

    def unpack(self, k):
        cells = []
        for t, n in gen45.ROOM_RUNS[k]:
            cells += [t] * n
        self.names[32:] = cells

    def flip0(self):
        self.unpack(self.room)
        self.post(gen45.ROOM_AT, ord("ABCD"[self.room & 3]))
        self.post(gen45.ROOM_AT + 1, ord("1") + (self.room >> 2 & 3))
        self.fresh = 0
        if not self.been[self.room]:
            self.been[self.room] = 1
            self.fresh = 1
            self.seen = tobcd(bcd(self.seen) + 1)
            self.post2(gen45.SEEN_AT, self.seen)
        self.events.append((self.loop, "ROOM", self.room, self.fresh, list(self.copy[:2])))
        if self.torn:
            self.show(self.names[32:], gen45.GAME_R3, gen45.GAME_R4)
        else:
            self.page("names", gen45.GAME_R3, gen45.GAME_R4)

    def flip1(self):
        if self.pic_flip1 and self.fresh:
            self.mini()
        self.go(PLAY)

    def play0(self):
        self.due = 0
        self.was = self.held

    def walk(self):
        """one step: None, or the way out"""
        h = self.held
        y, x = self.copy[0], self.copy[1]
        b = x
        if not h & 4:
            if b == 0:
                return W
            b -= 2
        if not h & 8:
            if b == gen45.X_LAST:
                return E
            b += 2
        if not self.walled(b, y):
            self.copy[1] = b
        x = self.copy[1]
        c = y
        if not h & 1:
            if c == gen45.Y_FIRST:
                return N
            c -= 2
        if not h & 2:
            if c == gen45.Y_LAST:
                return S
            c += 2
        if not self.walled(x, c):
            self.copy[0] = c
        return None

    def walled(self, x, y):
        line = (y + 1) & 255
        r0, c0 = line >> 3, x >> 3
        nr = 2 if line & 7 == 0 else 3
        nc = 2 if x & 7 == 0 else 3
        cells = [32 * (r0 + i) + c0 + j for i in range(nr) for j in range(nc)]
        assert max(cells) < 768 and c0 + nc <= 32
        return any(self.names[c] >= gen45.BRICK for c in cells)

    def leave(self, way):
        self.events.append((self.loop, "OUT", self.room, way, list(self.copy[:2])))
        self.room = gen45.neighbour(self.room, way)
        x, y = gen45.entry(way, self.copy[1], self.copy[0])
        self.copy[0], self.copy[1] = y, x
        self.go(FLIP)

    def play1(self):
        if self.fresh:
            self.mini()
            self.play0()
            return
        if self.presses() & gen45.MAP_BIT:
            self.go(MAP)
            return
        for _ in range(self.paced()):
            way = self.walk()
            if way:
                self.leave(way)
                return

    def mini(self):
        self.fresh = 0
        pic = picture_bytes(self.names)
        self.minis[self.room] = pic
        a = gen45.picvram()[self.room] & 0x3FFF
        self.vram[a:a + 96] = bytes(picture_order(pic))
        self.events.append((self.loop, "MINI", self.room))

    def map0(self):
        self.keepy = self.copy[0]
        self.copy[0] = 0xD0
        self.mapbuild()
        if self.onethird:
            self.page("mapn", gen45.GAME_R3, gen45.GAME_R4)
        else:
            self.page("mapn", gen45.MAP_R3, gen45.MAP_R4)

    def mapbuild(self):
        m = gen45.map_names()
        for k in range(16):
            if not self.been[k]:
                continue
            first = gen45.CURRENT if k == self.room else gen45.mini_name(k)
            at = gen45.mapat()[k] - gen45.MAPN_AT
            for cy in range(3):
                for cx in range(4):
                    m[at + 32 * cy + cx] = first + 4 * cy + cx
        self.mapn = m
        a = gen45.curvram()[self.room] & 0x3FFF
        self.vram[a:a + 96] = bytes(picture_order(self.minis[self.room]))

    def map1(self):
        if not self.presses() & gen45.MAP_BIT:
            return
        self.copy[0] = self.keepy
        self.page("names", gen45.GAME_R3, gen45.GAME_R4)
        self.go(PLAY)

    # ---------------------------------------------------------- what the RAM holds
    def ram(self):
        return {"stat": self.stat, "ticks": self.ticks, "state": self.state, "was": self.was,
                "room": self.room, "seen": self.seen, "fresh": self.fresh, "queued": len(self.queue),
                "keepy": self.keepy, "whole": self.whole,
                "wsrc": {0: 0, "names": gen45.NAMES_AT + 32, "mapn": gen45.MAPN_AT}[self.wsrc],
                "wr3": self.wr3, "wr4": self.wr4, "copy": list(self.copy), "due": self.due,
                "lines": self.lines, "been": list(self.been)}


# ---------------------------------------------------------------- distances
KEYSETS = [("left",), ("right",), ("up",), ("down",), ("left", "up"), ("left", "down"),
           ("right", "up"), ("right", "down")]
HELD_OF = {k: keys_byte(set(k)) for k in KEYSETS}


class Room:
    """walk's steps in room K, for every place and every keyset"""

    def __init__(self, k):
        self.k = k
        self.g = gen45.grid(k)
        self.places = [(x, y) for x in range(0, gen45.X_LAST + 1, 2)
                       for y in range(gen45.Y_FIRST, gen45.Y_LAST + 1, 2)
                       if not gen45.solid_at(self.g, x, y)]
        self.fields = {}

    def solid(self, x, y):
        return gen45.solid_at(self.g, x, y)

    def step(self, p, keys):
        """walk's step from P with KEYS held: a place, or a way out"""
        x, y = p
        b = x
        if "left" in keys:
            if b == 0:
                return W
            b -= 2
        if "right" in keys:
            if b == gen45.X_LAST:
                return E
            b += 2
        if not self.solid(b, y):
            x = b
        c = y
        if "up" in keys:
            if c == gen45.Y_FIRST:
                return N
            c -= 2
        if "down" in keys:
            if c == gen45.Y_LAST:
                return S
            c += 2
        if not self.solid(x, c):
            y = c
        return (x, y)

    def field(self, way):
        """the steps from each place to the step out by WAY"""
        if way in self.fields:
            return self.fields[way]
        back = {}
        for p in self.places:
            for ks in KEYSETS:
                q = self.step(p, ks)
                back.setdefault(q, []).append(p)
        dist = {way: 0}
        waiting = deque([way])
        while waiting:
            q = waiting.popleft()
            for p in back.get(q, []):
                if p not in dist:
                    dist[p] = dist[q] + 1
                    waiting.append(p)
        self.fields[way] = dist
        return dist


ROOMS_W = {}


def room_of(k):
    if k not in ROOMS_W:
        ROOMS_W[k] = Room(k)
    return ROOMS_W[k]


def way_to(room, seen):
    """the way out of ROOM towards the nearest room not seen"""
    prev, q = {room: None}, deque([room])
    while q:
        k = q.popleft()
        if not seen[k]:
            while prev[k][0] != room:
                k = prev[k][0]
            return prev[k][1]
        for w in (N, E, S, W):
            if gen45.EXITS[k] & w:
                n = gen45.neighbour(k, w)
                if n not in prev:
                    prev[n] = (k, w)
                    q.append(n)
    return None


# ---------------------------------------------------------------- the player
PRESS = 80                  # the loop (its ticks) from which SPACE is held at the title
HELD = 3                    # for three loops
PEEK = 6                    # the rooms seen when it first looks at the map
LOOK = 60                   # loops it looks at the map
M_HELD = 2                  # loops M is held for a press


class Player:
    """chooses the keys of each loop from the game as its logic finds it"""

    def __init__(self, peek=PEEK, look=LOOK):
        self.peek, self.look = peek, look
        self.looks = 0
        self.holding = 0            # loops of M still to hold
        self.looking = None         # loops looked at the map this time
        self.done = False
        self.way = None             # (room, the way out chosen)
        self.choices = []           # (loop, keys, steps, distance before, after)

    def hold_m(self):
        self.holding = M_HELD - 1
        return {"m"}

    def choose(self, g):
        if self.holding:
            self.holding -= 1
            return {"m"}
        st = g.state
        if st == TITLE:
            return {"space"} if PRESS <= g.ticks < PRESS + HELD else set()
        if st == FLIP:
            return set()
        n_seen = sum(g.been)
        if st == MAP:
            self.looking += 1
            if self.looking == self.look:
                if n_seen == 16:
                    self.done = True
                    return set()
                return self.hold_m()
            return set()
        if g.fresh:
            return set()
        if self.looks == 0 and n_seen >= self.peek or self.looks == 1 and n_seen == 16:
            self.looks += 1
            self.looking = 0
            return self.hold_m()
        b = g.steps_owed()
        if self.way is None or self.way[0] != g.room:
            self.way = (g.room, way_to(g.room, g.been))
        way = self.way[1]
        rm = room_of(g.room)
        dist = rm.field(way)
        here = (g.copy[1], g.copy[0])
        d0 = dist[here]
        best = None
        for ks in KEYSETS:
            p, value = here, None
            for _ in range(b):
                q = rm.step(p, ks)
                if q in (N, E, S, W):
                    value = -1 if q == way else 10 ** 6
                    break
                p = q
            if value is None:
                value = dist.get(p, 10 ** 6)
            if best is None or value < best[0]:
                best = (value, ks)
        assert best[0] < d0, (g.loop, g.room, here, b, d0, best)
        self.choices.append((g.loop, best[1], b, d0, best[0]))
        return set(best[1])


# ---------------------------------------------------------------- a walk
def keys_at(events, frame):
    held = set()
    for f in sorted(events):
        if f > frame:
            break
        held = events[f]
    return held


def plan(machine, player=None, game=None, limit=20000):
    """the model on MACHINE played by PLAYER: (the keys of each loop, the
    game, the loops' records)"""
    player = player or Player()
    g = game or Keep(machine)
    keys_by_loop, recs = [], []
    while not player.done and g.loop < limit:
        g.loop += 1
        g.isr_head()
        keys = player.choose(g)
        g.isr_tail(keys)
        g.sends()
        keys_by_loop.append((g.ticks, frozenset(keys)))
        g.run()
        recs.append(g.ram())
    assert player.done, "the walk did not end"
    return keys_by_loop, g, recs


def events_of(keys_by_loop):
    out, last = {}, frozenset()
    for t, k in keys_by_loop:
        if k != last:
            out[t + EVENT_AHEAD] = k
            last = k
    return out


def tcl_events(ev):
    out = {}
    for f, k in sorted(ev.items()):
        m8 = 0
        for name in k:
            m8 |= ROW8.get(name, 0)
        cmd = "keymatrixup 8 0xF1; keymatrixup 4 0x04"
        if m8:
            cmd += f"; keymatrixdown 8 0x{m8:02X}"
        if "m" in k:
            cmd += "; keymatrixdown 4 0x04"
        out[f] = cmd
    return out


def replay(ev, loops, machine, **kw):
    g = Keep(machine, **kw)
    recs = []
    for _ in range(loops):
        g.step_loop(keys_at(ev, g.ticks + 1 + EVENT_AHEAD))
        recs.append(g.ram())
    return g, recs


TAG = {EU: "eu", JP: "jp"}


def events_path(machine):
    return os.path.join(HERE, f"game_{TAG[machine]}.events")


def write_events(path, ev, machine):
    hz = {EU: "50", JP: "60"}[machine]
    lines = [f"# game_{TAG[machine]}.events -- chapter 45: the keys of the walk planned for the "
             f"{hz} Hz machine,",
             "# written by model45.py: a frame (from INIT) and the keys held from then on"]
    for f, k in sorted(ev.items()):
        lines.append(f"{f} {' '.join(sorted(k)) or '-'}")
    with open(path, "w") as fh:
        fh.write("\n".join(lines) + "\n")


def read_events(path):
    out = {}
    for line in open(path):
        if line.startswith("#") or not line.strip():
            continue
        f, *k = line.split()
        out[int(f)] = frozenset() if k == ["-"] else frozenset(k)
    return out


def main():
    for m in (JP, EU):
        player = Player()
        keys, g, recs = plan(m, player=player)
        ev = events_of(keys)
        write_events(events_path(m), ev, m)
        g2, recs2 = replay(ev, len(recs), m)
        assert recs2 == recs
        rooms = [e[2] for e in g.events if e[1] == "ROOM"]
        print(f"{os.path.basename(events_path(m))}: {len(ev)} changes, {len(recs)} loops; "
              f"{len(rooms)} flips, rooms {' '.join(gen45.room_name(r) for r in rooms)}")


if __name__ == "__main__":
    main()
