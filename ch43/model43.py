#!/usr/bin/env python3
"""model43.py - GRIN ALLEY in Python, and a player who plans a play of it.

    python3 model43.py          game.events: the planned play's keys

Grin is the game as gen43.py writes it, a loop at a time: the interrupt
(the status, from the frame the sends before drew, by vdpscreen.py's rules
11 and 12; the frame counted), the sends (the copy of the sprites'
attributes, the names queued, the status line's digits), and the state's
routine. It keeps what the RAM keeps and what the name table holds, so that
meas43.py can hold every loop of a film against it.

Player chooses the keys of each loop from the game as the loop's logic finds
it: where the runner is, where each face is and which way it goes, which
cells hold gems. It walks to the nearest gem; it crosses an alley only when
the face there stays clear of the runner's box, by MARGIN pixels, all the
way over; after the CAREFUL-th round's RECKLESS-th gem it walks into alley
0's face, until GAME OVER and the title again. The keys go to openMSX as
events (tools/msxcap.py): a loop woken by the signal of frame n reads the
keys of the events up to frame n, and its ticks is n - 1 (meas43.py checks
it in every loop of every film).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gen43       # noqa: E402
import vdpscreen   # noqa: E402

assert os.path.dirname(os.path.abspath(vdpscreen.__file__)) == HERE

TITLE, PLAY, HIT, OVER = range(4)
NAMES = 0x1800
SAT, SPAT = 0x1B00, 0x3800
REGS = [0x02, 0xE2, 0x06, 0x9F, 0x00, 0x36, 0x07, gen43.BORDER]
EVENT_AHEAD = 1                     # keys for the loop whose ticks is t: events at frame t + 1
ROW8 = {"space": 0x01, "left": 0x10, "up": 0x20, "down": 0x40, "right": 0x80}
JOY_IDLE = 0xBF                     # joystick 1 with nothing held, as joy reads it


def bcd_add(num, points):
    v = int("".join(f"{b:02X}" for b in num)) + int(f"{points:02X}")
    s = f"{v % 10 ** 6:06d}"
    return [int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)]


def keys_byte(keys):
    """row 8 of the keyboard with KEYS held, as keys turns it into register
    14's way (chapter 35), ANDed with the idle joystick: the byte held gets"""
    row8 = 0xFF
    for k in keys:
        row8 &= ~ROW8[k] & 0xFF
    a = gen43.gen35.kbd_table()[(row8 >> 4) & 15] | (row8 & 1) << 4 | 0xE0
    return a & JOY_IDLE


def cells_under(x, y):
    """the cells (row, column) walled and pick look at for a sprite at X, Y"""
    line = (y + 1) & 255
    r0, c0 = (line >> 3) & 31, (x >> 3) & 31
    nr = 2 if line & 7 == 0 else 3
    nc = 2 if x & 7 == 0 else 3
    return [((r0 + i) & 31, (c0 + j) & 31, 32 * r0 + j + 32 * i + c0) for i in range(nr) for j in range(nc)]


class Grin:
    """the game, a loop at a time"""

    def __init__(self, stale_bug=False, holds=gen43.HOLD, steps=None):
        self.stale_bug = stale_bug
        self.holds = holds
        self.first_steps = [s for _, s in gen43.FACES] if steps is None else list(steps)
        # what INIT leaves
        self.ticks = 0
        self.seed = 0                           # not yet set: TITLE sets it
        self.state = TITLE
        self.left = 0
        self.lives = 0
        self.gems = 0
        self.last = 0
        self.held = None                        # not yet read
        self.stale = 0
        self.shownl = 0
        self.queue = []
        self.copy = [0] * 21                    # INIT clears the page of the variables
        self.steps = [0, 0, 0, 0]
        self.names = None                       # the copy of the names: none before a game
        self.score = [0, 0, 0]
        self.hi = list(gen43.HI_START)
        self.shown = self.score + self.hi
        self.vnames = [32] * 768                # title0 at INIT: the name table
        self.vsat = [0xD0] + [0] * 31           # the VRAM's attribute table
        self.drawn_sat = list(self.vsat)        # the attributes the last frame was drawn with
        self.stat = None
        self.loop = -1
        self.events = []                        # (loop, what)
        self.title0()

    # ---------------------------------------------------------- the VRAM
    def vram(self):
        """the VRAM the frame after the sends draws, for vdpscreen"""
        v = bytearray(16384)
        tiles = [0] * 8 + list(gen43.BRICK_SHAPE) + [0] * 8 + list(gen43.GEM_SHAPE)
        v[0:32] = bytes(tiles)
        v[0x100:0x100 + 768] = bytes(gen43.FONT)
        v[0x2000:0x2020] = bytes([gen43.PAPER_C] * 8 + [gen43.BRICK_C] * 8 + [gen43.ALLEY_C] * 8 +
                                 [gen43.GEM_C] * 8)
        v[0x2100:0x2100 + 768] = bytes([gen43.PAPER_C] * 768)
        v[NAMES:NAMES + 768] = bytes(self.vnames)
        v[SAT:SAT + 32] = bytes(self.vsat)
        v[SPAT:SPAT + 64] = bytes(gen43.SPRITE_PATTERNS)
        return v

    def status_of(self, sat):
        v = bytearray(16384)
        v[SAT:SAT + 32] = bytes(sat)
        v[SPAT:SPAT + 64] = bytes(gen43.SPRITE_PATTERNS)
        five, number = vdpscreen.sprite_status(v, REGS)
        c, _ = vdpscreen.coincidence(v, REGS)
        return 0x80 | five << 6 | c << 5 | number

    def say(self, col, row, text):
        for k, ch in enumerate(text):
            self.vnames[32 * row + col + k] = ord(ch)

    # ---------------------------------------------------------- a loop
    def isr(self):
        self.screen = False                     # no names written in the logic yet
        self.stat = self.status_of(self.drawn_sat)
        self.ticks = (self.ticks + 1) & 0xFFFF

    def sends(self):
        self.vsat[0:21] = self.copy
        for addr, name in self.queue:
            self.vnames[(addr & 0x3FFF) - NAMES] = name
        self.queue = []
        for num, at, k0 in ((self.score, gen43.SCORE_AT, 0), (self.hi, gen43.HI_AT, 3)):
            for i in range(3):
                if num[i] != self.shown[k0 + i]:
                    self.shown[k0 + i] = num[i]
                    self.vnames[at + 2 * i] = gen43.DIGIT0 + (num[i] >> 4)
                    self.vnames[at + 2 * i + 1] = gen43.DIGIT0 + (num[i] & 15)
        if self.lives != self.shownl:
            self.shownl = self.lives
            self.vnames[gen43.LIVES_AT] = gen43.DIGIT0 + self.lives
        self.drawn_sat = list(self.vsat)        # the frame after the sends shows these

    def run(self, keys):
        {TITLE: self.title1, PLAY: self.play1, HIT: self.hit1, OVER: self.over1}[self.state](keys)

    def go(self, state):
        self.state = state
        self.events.append((self.loop, ["TITLE", "PLAY", "HIT", "OVER"][state]))
        {TITLE: self.title0, PLAY: self.play0, HIT: self.hit0, OVER: self.over0}[state]()

    def step_loop(self, keys):
        """one loop: the interrupt, the sends, the state's routine"""
        self.loop += 1
        self.isr()
        self.sends()
        self.run(keys)

    # ---------------------------------------------------------- the states
    def title0(self):
        self.screen = True
        self.vnames = [32] * 768
        for col, row, text in gen43.TITLE_TEXT:
            self.say(col, row, text)
        self.copy[0:9] = gen43.title_copy()

    def title1(self, keys):
        self.held = keys_byte(keys)
        if self.held & 0x10:
            return
        self.seed = self.ticks or 1
        self.setup()
        self.round()
        self.go(PLAY)

    def setup(self):
        arena = gen43.arena_names()
        self.screen = True
        self.names = list(arena)
        self.vnames = list(arena)
        self.score = [0, 0, 0]
        self.shown = [0xFF] * 6
        self.lives = gen43.LIVES
        self.shownl = 0xFF
        self.copy = gen43.first_copy()
        self.steps = list(self.first_steps)
        self.queue = []
        self.stale = 0

    def random(self):
        self.seed = gen43.gen41.xorshift(self.seed)
        return self.seed >> 8

    def post(self, cell, name):
        self.names[cell] = name
        self.queue.append((0x1800 + 0x4000 + cell, name))
        assert len(self.queue) <= gen43.QUEUE_MAX

    def sow(self):
        tries = self.__dict__.setdefault("tries", {"wall": 0, "runner": 0, "gem": 0, "sown": 0})
        while True:
            row = gen43.GEM_ROWS[self.random() & 7]
            col = self.random() & 31
            if col in (0, 31):
                tries["wall"] += 1
                continue
            ry = (((self.copy[0] + 1) & 255) >> 3) & 31
            if (row - ry + 1) & 255 < 5:
                cx = (self.copy[1] >> 3) & 31
                if (col - cx + 1) & 255 < 5:
                    tries["runner"] += 1
                    continue
            cell = 32 * row + col
            if self.names[cell] != gen43.PAPER:
                tries["gem"] += 1
                continue
            tries["sown"] += 1
            self.post(cell, gen43.GEM)
            return cell

    def round(self):
        cells = [self.sow() for _ in range(gen43.GEMS)]
        self.gems = gen43.GEMS
        self.events.append((self.loop, "ROUND", cells))

    def play0(self):
        self.last = self.ticks & 255

    def walled(self, x, y):
        return any(self.names[c] == gen43.BRICK for _, _, c in cells_under(x, y))

    def walk(self):
        h = self.held
        y, x = self.copy[0], self.copy[1]
        b = x
        if not h & 4:
            b = (b - 2) & 255
        if not h & 8:
            b = (b + 2) & 255
        if not self.walled(b, y):
            self.copy[1] = b
        x = self.copy[1]
        c = y
        if not h & 1:
            c = (c - 2) & 255
        if not h & 2:
            c = (c + 2) & 255
        if not self.walled(x, c):
            self.copy[0] = c

    def patrol(self, k):
        x = self.copy[4 + 4 * k + 1]
        s = self.steps[k]
        n = (x + s) & 255
        if (n - gen43.X_MIN) & 255 >= gen43.X_MAX - gen43.X_MIN + 1:
            s = -s
            self.steps[k] = s
            n = (x + s) & 255
        self.copy[4 + 4 * k + 1] = n

    def pick(self):
        for _, _, cell in cells_under(self.copy[1], self.copy[0]):
            if self.names[cell] == gen43.GEM:
                self.post(cell, gen43.PAPER)
                self.score = bcd_add(self.score, gen43.POINTS)
                self.gems -= 1
                self.events.append((self.loop, "TOOK", cell))

    def play1(self, keys):
        self.held = keys_byte(keys)
        if self.gems == 0:
            self.round()
        t = self.ticks & 255
        counted = (t - self.last) & 255
        self.last = t
        for _ in range(counted):
            self.walk()
            for k in range(4):
                self.patrol(k)
        self.counted = counted
        self.pick()
        if self.score > self.hi:
            self.hi = list(self.score)
        if self.stale:
            self.stale -= 1
            return
        if self.stat & 0x20:
            self.go(HIT)

    def hit0(self):
        self.lives -= 1
        self.left = self.holds

    def hit1(self, keys):
        self.left -= 1
        if self.left:
            return
        if self.lives == 0:
            self.go(OVER)
            return
        self.copy[0], self.copy[1] = gen43.HOME[1], gen43.HOME[0]
        if not self.stale_bug:
            self.stale = 1
        self.go(PLAY)

    def over0(self):
        self.screen = True
        self.say(gen43.OVER_AT[0], gen43.OVER_AT[1], gen43.OVER_TEXT)
        self.left = gen43.WAITS

    def over1(self, keys):
        self.left -= 1
        if self.left:
            return
        self.go(TITLE)

    # ---------------------------------------------------------- what the RAM holds
    def ram(self):
        return {"stat": self.stat, "ticks": self.ticks, "seed": self.seed, "state": self.state,
                "left": self.left, "lives": self.lives, "gems": self.gems, "last": self.last,
                "stale": self.stale, "shownl": self.shownl, "queued": len(self.queue),
                "copy": list(self.copy), "steps": [s & 255 for s in self.steps],
                "score": list(self.score), "hi": list(self.hi), "shown": list(self.shown)}

    def faces(self):
        return [(self.copy[4 + 4 * k], self.copy[5 + 4 * k], self.steps[k]) for k in range(4)]

    def gem_cells(self):
        if self.names is None:
            return []
        return [(r, c) for r in gen43.GEM_ROWS for c in range(1, 31) if self.names[32 * r + c] == gen43.GEM]


# ---------------------------------------------------------------- the player
PRESS = 80                  # the loop (its ticks) from which SPACE is held at the title
HELD = 3                    # for three loops
CAREFUL = 3                 # rounds played with care
RECKLESS = 3                # gems of the last of them before the faces are sought
MARGIN = 4                  # pixels kept between the boxes when crossing
AFTER = 40                  # loops of the title again before the end
ZONE_Y = [gen43.HOME[1] + 16] + [y + 15 for y in gen43.LANES]  # home's lowest Y, the corridors'
assert ZONE_Y == [39, 71, 103, 135, 167]


class Player:
    """chooses the keys of each loop from the game as its logic finds it"""

    def __init__(self, careful=CAREFUL, reckless=RECKLESS, margin=MARGIN, press=PRESS):
        self.careful, self.reckless, self.margin, self.press = careful, reckless, margin, press
        self.goal = None            # a crossing under way: the Y it ends on
        self.rounds = 0
        self.last_gems = 0
        self.last_state = None
        self.title_again = None
        self.done = False
        self.reckless_from = None   # the loop it turned reckless in

    @staticmethod
    def zone_of(y):
        if y <= ZONE_Y[0]:
            return 0
        return ZONE_Y.index(y) if y in ZONE_Y else None

    @staticmethod
    def patrol(x, step):
        n = x + step
        if not gen43.X_MIN <= n <= gen43.X_MAX:
            step = -step
            n = x + step
        return n, step

    def safe(self, x, y0, y1, faces):
        """the runner from Y0 to Y1, two lines a frame, at X: no face within
        the margin of its box in any of those frames"""
        d = 2 if y1 > y0 else -2
        y = y0
        while y != y1:
            y += d
            faces = [(fy, *self.patrol(fx, st)) for fy, fx, st in faces]
            for fy, fx, _ in faces:
                if abs(fx - x) < 16 + self.margin and abs(fy - y) < 16:
                    return False
        return True

    @staticmethod
    def toward(x, tx):
        return {"right"} if x < tx else {"left"} if x > tx else set()

    def choose(self, g):
        st = g.state
        if g.gems > self.last_gems:
            self.rounds += 1                    # the gems sown again: a round
        self.last_gems = g.gems
        if st != self.last_state:
            if st == TITLE and self.rounds:
                self.title_again = 0            # the title after the game
            self.last_state = st
        if st == TITLE:
            if self.title_again is not None:
                self.title_again += 1
                self.done = self.title_again >= AFTER
                return set()
            return {"space"} if self.press <= g.ticks < self.press + HELD else set()
        if st != PLAY:
            self.goal = None
            return set()
        y, x = g.copy[0], g.copy[1]
        faces = g.faces()
        if self.goal is not None:
            if y == self.goal:
                self.goal = None
            else:
                return {"down"} if self.goal > y else {"up"}
        gems_left = g.gems
        reckless = self.rounds > self.careful or (
            self.rounds == self.careful and gems_left <= gen43.GEMS - self.reckless)
        if reckless:
            if self.reckless_from is None:
                self.reckless_from = g.loop
            lane = gen43.LANES[0] - 1
            if y != lane:
                self.goal = lane
                return {"down"} if lane > y else {"up"}
            return self.toward(x, faces[0][1])
        zone = self.zone_of(y)
        cells = g.gem_cells()
        if not cells or zone is None:
            return set()
        zone_of_row = {r: 1 + gen43.GEM_ROWS.index(r) // 2 for r in gen43.GEM_ROWS}

        def target_x(c):
            return min(max(8 * (c - 1), gen43.X_MIN), gen43.X_MAX)
        r, c = min(cells, key=lambda rc: (60 * abs(zone_of_row[rc[0]] - zone) +
                                          abs(target_x(rc[1]) - x), rc))
        tz, tx = zone_of_row[r], target_x(c)
        if tz == zone:
            return self.toward(x, tx)
        nz = zone + (1 if tz > zone else -1)
        y1 = ZONE_Y[nz]
        if self.safe(x, y, y1, faces):
            self.goal = y1
            return {"down"} if y1 > y else {"up"}
        return self.toward(x, tx)


# ---------------------------------------------------------------- a play
def keys_at(events, frame):
    """the keys held at FRAME by a dict {frame: set of keys from then on}"""
    held = set()
    for f in sorted(events):
        if f > frame:
            break
        held = events[f]
    return held


def plan(player=None, game=None, limit=5000):
    """the model played by PLAYER: (the keys of each loop, the game, the
    loops' records)"""
    player = player or Player()
    g = game or Grin()
    keys_by_loop, recs = [], []
    while not player.done and g.loop < limit:
        # the loop's interrupt and sends come before its logic looks at the keys
        g.loop += 1
        g.isr()
        g.sends()
        keys = player.choose(g)
        keys_by_loop.append((g.ticks, frozenset(keys)))
        g.run(keys)
        recs.append(g.ram())
    return keys_by_loop, g, recs


def events_of(keys_by_loop):
    """{frame: set of keys from then on}, at the changes, for the loops'
    ticks"""
    out, last = {}, frozenset()
    for t, k in keys_by_loop:
        if k != last:
            out[t + EVENT_AHEAD] = k
            last = k
    return out


def tcl_events(ev):
    """{frame: openMSX command} for msxcap: row 8 all up, then the keys down"""
    out = {}
    for f, k in sorted(ev.items()):
        mask = 0
        for name in k:
            mask |= ROW8[name]
        out[f] = "keymatrixup 8 0xF1" + (f"; keymatrixdown 8 0x{mask:02X}" if mask else "")
    return out


def replay(ev, loops, stale_bug=False, holds=gen43.HOLD, steps=None):
    """the model fed the keys of events EV for LOOPS loops: the game and the
    loops' records"""
    g = Grin(stale_bug=stale_bug, holds=holds, steps=steps)
    recs = []
    for _ in range(loops):
        g.loop += 1
        g.isr()
        g.sends()
        g.run(keys_at(ev, g.ticks + EVENT_AHEAD))
        recs.append(g.ram())
    return g, recs


def write_events(path, ev):
    lines = ["# game.events -- chapter 43: the keys of the planned play, written by model43.py",
             "# frame (from INIT) and the cursor keys and SPACE held from then on"]
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
    keys, g, recs = plan()
    ev = events_of(keys)
    write_events(os.path.join(HERE, "game.events"), ev)
    # the events give the same play back
    g2, recs2 = replay(ev, len(recs))
    assert recs2 == recs
    print(f"game.events: {len(ev)} changes, {len(recs)} loops")
    for e in g.events:
        if e[1] != "TOOK":
            print(" ", e[:2], (e[2] if len(e) > 2 else ""))


if __name__ == "__main__":
    main()
