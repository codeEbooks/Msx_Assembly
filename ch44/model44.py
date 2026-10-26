#!/usr/bin/env python3
"""model44.py - GRIN ALLEY finished, in Python, and a player who plans a play.

    python3 model44.py          game_eu.events and game_jp.events

Grin is the game as gen44.py writes it, a loop at a time, on one of the two
machines: the interrupt (the status, from the frame the sends before drew,
by vdpscreen.py's rules 11 and 12; the frame counted; its lines owed to the
game's steps; chapter 37's player, ticking when its pace says, read from the
cartridge by player37.py), the sends, and the state's routine, which takes a
step of the game for each 262 lines owed. It keeps what the RAM keeps, the
player's page too, and what the name table holds, so that meas44.py can hold
every loop of a film against it, and every write of the player to the PSG.

Player chooses the keys of each loop from the game as the loop's logic
finds it, knowing how many steps the loop will take: it walks to the nearest
gem; it crosses an alley only when the face there stays clear of the
runner's box, by MARGIN pixels, all the way over; it moves only as far as
the loop's steps take it exactly; from the round after CAREFUL it walks into
alley 0's face, until GAME OVER and the title again. A plan for each
machine: the same keys at the 50 Hz machine's loops would not be the same
play.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gen44       # noqa: E402
import vdpscreen   # noqa: E402
import player37    # noqa: E402

assert os.path.dirname(os.path.abspath(vdpscreen.__file__)) == HERE
gen41 = gen44.gen41

EU, JP = gen44.EU, gen44.JP
TITLE, PLAY, HIT, OVER = range(4)
NAMES = 0x1800
SAT, SPAT = 0x1B00, 0x3800
REGS = [0x02, 0xE2, 0x06, 0x9F, 0x00, 0x36, 0x07, gen44.BORDER]
EVENT_AHEAD = 1                     # keys for the loop whose ticks is t: events at frame t + 1
ROW8 = {"space": 0x01, "left": 0x10, "up": 0x20, "down": 0x40, "right": 0x80}
JOY_IDLE = 0xBF                     # joystick 1 with nothing held, as joy reads it
PACE_LINES = 313                    # chapter 37's player: a tick every 313 lines
SOUND = gen44.SOUND


def bcd(n):
    return int(f"{n:02X}")


def tobcd(n):
    return int(str(n), 16)


def bcd_add(num, points_bcd, tens=False):
    v = int("".join(f"{b:02X}" for b in num)) + bcd(points_bcd) * (10 if tens else 1)
    s = f"{v % 10 ** 6:06d}"
    return [int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)]


def keys_byte(keys):
    """row 8 of the keyboard with KEYS held, as keys turns it into register
    14's way (chapter 35), ANDed with the idle joystick: the byte held gets"""
    row8 = 0xFF
    for k in keys:
        row8 &= ~ROW8[k] & 0xFF
    a = gen44.gen35.kbd_table()[(row8 >> 4) & 15] | (row8 & 1) << 4 | 0xE0
    return a & JOY_IDLE


def cells_under(x, y):
    """the cells (row, column, number) walled and pick look at for a sprite
    at X, Y"""
    line = (y + 1) & 255
    r0, c0 = (line >> 3) & 31, (x >> 3) & 31
    nr = 2 if line & 7 == 0 else 3
    nc = 2 if x & 7 == 0 else 3
    return [((r0 + i) & 31, (c0 + j) & 31, 32 * r0 + j + 32 * i + c0) for i in range(nr) for j in range(nc)]


def patrol_step(x, s):
    """chapter 43's patrol: X a step S on, turning outside X_MIN to X_MAX"""
    n = (x + s) & 255
    if (n - gen44.X_MIN) & 255 >= gen44.X_MAX - gen44.X_MIN + 1:
        s = -s
        n = (x + s) & 255
    return n, s


class Grin:
    """the game, a loop at a time, on MACHINE"""

    def __init__(self, machine=JP, once=True, every=gen44.EVERY, award_first=False,
                 frames_paced=False, rom=None):
        self.machine = machine
        self.lines = gen44.LINES[machine]
        self.once, self.every, self.award_first = once, every, award_first
        self.frames_paced = frames_paced
        self.player = player37.Player(rom or os.path.join(HERE, "extra" if not once else "game"))
        self.owed = 0
        self.psg = []                           # (loop, the 11 bytes a tick sent)
        self.fx_asked = []                      # (loop, sound, taken)
        # what INIT leaves: the variables' page all 0, then the start
        self.ticks = 0
        self.seed = 0
        self.state = TITLE
        self.left = 0
        self.lives = 0
        self.gems = 0
        self.roundno = 0
        self.held = None
        self.stale = 0
        self.shownl = 0
        self.queue = []
        self.copy = [0] * 21
        self.steps = [0, 0, 0, 0]
        self.due = 0
        self.value = 0
        self.bonus = 0
        self.tock = 0
        self.awarded = 0
        self.names = None
        self.score = [0, 0, 0]
        self.hi = list(gen44.HI_START)
        self.shown = self.score + self.hi
        self.vnames = [32] * 768
        self.vsat = [0xD0] + [0] * 31
        self.drawn_sat = list(self.vsat)
        self.stat = None
        self.loop = -1
        self.steps_taken = []                   # (loop, steps) for each loop that took some
        self.events = []
        self.title0()

    # ---------------------------------------------------------- the VRAM
    def vram(self):
        """the VRAM the frame after the sends draws, for vdpscreen"""
        v = bytearray(16384)
        v[0:32] = bytes(gen44.TILE_SHAPES)
        v[0x100:0x100 + 768] = bytes(gen44.FONT)
        v[0x2000:0x2020] = bytes(gen44.TILE_COLOURS)
        v[0x2100:0x2100 + 768] = bytes([gen44.PAPER_C] * 768)
        v[NAMES:NAMES + 768] = bytes(self.vnames)
        v[SAT:SAT + 32] = bytes(self.vsat)
        v[SPAT:SPAT + 64] = bytes(gen44.SPRITE_PATTERNS)
        return v

    @staticmethod
    def status_of(sat):
        v = bytearray(16384)
        v[SAT:SAT + 32] = bytes(sat)
        v[SPAT:SPAT + 64] = bytes(gen44.SPRITE_PATTERNS)
        five, number = vdpscreen.sprite_status(v, REGS)
        c, _ = vdpscreen.coincidence(v, REGS)
        return 0x80 | five << 6 | c << 5 | number

    def say(self, col, row, text):
        for k, ch in enumerate(text):
            self.vnames[32 * row + col + k] = ord(ch)

    # ---------------------------------------------------------- the interrupt and the sends
    def isr(self, keys):
        self.isr_head()
        self.isr_tail(keys)

    def isr_head(self):
        """the interrupt up to the keys: the status, the frame, the lines"""
        self.screen = False
        self.stat = self.status_of(self.drawn_sat)
        self.ticks = (self.ticks + 1) & 0xFFFF
        self.due = (self.due + (gen44.LINES_A_STEP if self.frames_paced else self.lines)) & 0xFFFF

    def isr_tail(self, keys):
        """the keys, and the player"""
        self.held = keys_byte(keys)
        o = self.owed + self.lines
        if o >= PACE_LINES:
            self.owed = o - PACE_LINES
            self.psg.append((self.loop, list(self.player.shadow)))     # tochip: last tick's
            self.player.play()
        else:
            self.owed = o

    def sends(self):
        self.vsat[0:21] = self.copy
        for addr, name in self.queue:
            self.vnames[(addr & 0x3FFF) - NAMES] = name
        self.queue = []
        for num, at, k0 in ((self.score, gen44.SCORE_AT, 0), (self.hi, gen44.HI_AT, 3)):
            for i in range(3):
                if num[i] != self.shown[k0 + i]:
                    self.shown[k0 + i] = num[i]
                    self.vnames[at + 2 * i] = gen44.DIGIT0 + (num[i] >> 4)
                    self.vnames[at + 2 * i + 1] = gen44.DIGIT0 + (num[i] & 15)
        if self.lives != self.shownl:
            self.shownl = self.lives
            self.vnames[gen44.LIVES_AT] = gen44.DIGIT0 + self.lives
        self.drawn_sat = list(self.vsat)

    def run(self, keys=None):
        {TITLE: self.title1, PLAY: self.play1, HIT: self.hit1, OVER: self.over1}[self.state](keys)

    def go(self, state):
        self.state = state
        self.events.append((self.loop, ["TITLE", "PLAY", "HIT", "OVER"][state]))
        {TITLE: self.title0, PLAY: self.play0, HIT: self.hit0, OVER: self.over0}[state]()

    def step_loop(self, keys):
        self.loop += 1
        self.isr(keys)
        self.sends()
        self.run()

    def steps_owed(self):
        """what paced will give this loop's logic"""
        return self.due // gen44.LINES_A_STEP

    def paced(self):
        b = self.due // gen44.LINES_A_STEP
        self.due -= b * gen44.LINES_A_STEP
        assert 1 <= b <= 255, b
        self.steps_taken.append((self.loop, b))
        return b

    def sounding(self):
        """the game's sound on chan_x, if one is sounding"""
        x = self.player.chans[3]
        if not x["WAITS"]:
            return None
        at = self.player.sym["effects"]
        for k, (name, *_) in enumerate(gen44.SOUNDS):
            prio, instr, note, _ = self.player.mem[at + 4 * k:at + 4 * k + 4]
            if (prio, instr & 0x7F, note) == (x["PRIO"], x["INSTR"], x["NOTE"]):
                return name
        raise AssertionError("an effect that is none of the game's")

    def fx(self, name):
        before = self.sounding()
        taken = self.player.sfx(SOUND[name])
        self.fx_asked.append((self.loop, name, taken, before))

    # ---------------------------------------------------------- the states
    def title0(self):
        self.screen = True
        self.vnames = gen44.title_names()
        self.shown = [0xFF] * 6
        self.lives = gen44.LIVES
        self.shownl = 0xFF
        self.copy[0:9] = gen44.title_copy()
        self.steps[0] = gen44.TITLE_FACE[2]

    def title1(self, keys):
        for _ in range(self.paced()):
            self.patrol(0)
        if self.held & 0x10:
            return
        self.seed = self.ticks or 1
        self.setup()
        self.round()
        self.events.append((self.loop, "PRESSED"))
        self.go(PLAY)

    def setup(self):
        arena = gen44.arena_names()
        self.screen = True
        self.names = list(arena)
        self.vnames = list(arena)
        self.score = [0, 0, 0]
        self.shown = [0xFF] * 6
        self.lives = gen44.LIVES
        self.shownl = 0xFF
        self.copy = gen44.gen43.first_copy()
        self.steps = [s for _, s in gen44.FACES]
        self.queue = []
        self.stale = 0
        self.roundno = 0
        self.awarded = 0

    def random(self):
        self.seed = gen41.xorshift(self.seed)
        return self.seed >> 8

    def post(self, cell, name):
        self.names[cell] = name
        self.queue.append((0x1800 + 0x4000 + cell, name))
        assert len(self.queue) <= gen44.QUEUE_MAX, len(self.queue)

    def post2(self, cell, byte):
        self.post(cell, gen44.DIGIT0 + (byte >> 4))
        self.post(cell + 1, gen44.DIGIT0 + (byte & 15))

    def sow(self):
        tries = self.__dict__.setdefault("tries", {"wall": 0, "runner": 0, "gem": 0, "sown": 0})
        while True:
            row = gen44.GEM_ROWS[self.random() & 7]
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
            if self.names[cell] != gen44.PAPER:
                tries["gem"] += 1
                continue
            tries["sown"] += 1
            self.post(cell, gen44.GEM)
            return cell

    def speeds(self):
        c = (self.roundno - 1) & 255
        for k, (_, f) in enumerate(gen44.FACES):
            a = min(abs(f) + c, gen44.MAXS)
            self.steps[k] = -a if self.steps[k] < 0 else a

    def round(self):
        self.roundno = tobcd(bcd(self.roundno) + 1)
        self.post2(gen44.ROUND_AT, self.roundno)
        self.value = min(self.roundno, gen44.CAP) << 4
        self.speeds()
        self.bonus = gen44.BONUS0
        self.post2(gen44.BONUS_AT, self.bonus)
        self.tock = self.every
        cells = [self.sow() for _ in range(gen44.GEMS)]
        self.gems = gen44.GEMS
        self.events.append((self.loop, "ROUND", bcd(self.roundno), cells, list(self.steps),
                            list(self.score)))

    def cleared(self):
        self.fx("S_ROUND")
        if self.award_first:
            self.award()
            self.score = bcd_add(self.score, self.bonus, tens=True)
        else:
            self.score = bcd_add(self.score, self.bonus, tens=True)
            self.award()
        self.events.append((self.loop, "CLEARED", bcd(self.roundno), self.bonus, list(self.score)))
        self.round()

    def award(self):
        if self.once and self.awarded:
            return
        if self.score[0] == 0 and self.score[1] < gen44.EXTRA_AT:
            return
        self.awarded = 1
        if self.lives < gen44.MAX_LIVES:
            self.lives += 1
        self.events.append((self.loop, "LIFE", self.lives, list(self.score)))
        self.fx("S_EXTRA")

    def drop(self):
        self.tock -= 1
        if self.tock:
            return
        self.tock = self.every
        if self.bonus == 0:
            return
        self.bonus = tobcd(bcd(self.bonus) - 1)
        self.post2(gen44.BONUS_AT, self.bonus)

    def play0(self):
        pass

    def walled(self, x, y):
        return any(self.names[c] >= gen44.BRICK for _, _, c in cells_under(x, y))

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
        at = 4 + 4 * k + 1
        self.copy[at], self.steps[k] = patrol_step(self.copy[at], self.steps[k])

    def pick(self):
        for _, _, cell in cells_under(self.copy[1], self.copy[0]):
            if self.names[cell] == gen44.GEM:
                self.post(cell, gen44.PAPER)
                self.score = bcd_add(self.score, self.value)
                self.gems -= 1
                self.events.append((self.loop, "TOOK", cell, bcd(self.roundno)))
                self.fx("S_GEM")
                self.award()

    def play1(self, keys):
        if self.gems == 0:
            self.cleared()
        for _ in range(self.paced()):
            self.walk()
            for k in range(4):
                self.patrol(k)
            self.drop()
        self.pick()
        if self.score > self.hi:
            self.hi = list(self.score)
        if self.stale:
            self.stale -= 1
            return
        if self.stat & 0x20:
            self.go(HIT)

    def countdown(self):
        b = self.paced()
        self.left = max(0, self.left - b)
        return self.left

    def hit0(self):
        self.lives -= 1
        self.left = gen44.STILL
        self.fx("S_TOUCH")

    def hit1(self, keys):
        if self.countdown():
            return
        if self.lives == 0:
            self.go(OVER)
            return
        self.copy[0], self.copy[1] = gen44.HOME[1], gen44.HOME[0]
        self.stale = 1
        self.go(PLAY)

    def over0(self):
        self.screen = True
        self.say(gen44.OVER_AT[0], gen44.OVER_AT[1], gen44.OVER_TEXT)
        self.left = gen44.ENDS
        self.fx("S_OVER")

    def over1(self, keys):
        if self.countdown():
            return
        self.go(TITLE)

    # ---------------------------------------------------------- what the RAM holds
    def ram(self):
        return {"stat": self.stat, "ticks": self.ticks, "seed": self.seed, "state": self.state,
                "left": self.left, "lives": self.lives, "gems": self.gems, "roundno": self.roundno,
                "stale": self.stale, "shownl": self.shownl, "queued": len(self.queue),
                "copy": list(self.copy), "steps": [s & 255 for s in self.steps], "due": self.due,
                "value": self.value, "bonus": self.bonus, "tock": self.tock, "awarded": self.awarded,
                "score": list(self.score), "hi": list(self.hi), "shown": list(self.shown)}

    def engine(self):
        """the player's page, as the Z80 keeps it: [(offset, bytes)]"""
        p = self.player
        out = [(0, [p.ticks & 255, p.ticks >> 8, self.owed & 255, self.owed >> 8, self.lines & 255,
                    self.lines >> 8, p.tick, p.step & 255, p.step >> 8, p.barno, p.rowno])]
        body = list(p.shadow)
        for ch in p.chans:
            for f in player37.FIELDS:
                v = ch[f]
                body += [v & 255, v >> 8] if f in player37.WORDS else [v & 255]
        out.append((gen44.gen37.SHADOW_AT, body))
        return out

    def faces(self):
        return [(self.copy[4 + 4 * k], self.copy[5 + 4 * k], self.steps[k]) for k in range(4)]

    def gem_cells(self):
        if self.names is None:
            return []
        return [(r, c) for r in gen44.GEM_ROWS for c in range(1, 31) if self.names[32 * r + c] == gen44.GEM]


# ---------------------------------------------------------------- the player
PRESS = 80                  # the loop (its ticks) from which SPACE is held at the title
HELD = 3                    # for three loops
CAREFUL = 4                 # rounds played with care; from the next, the faces are sought
MARGIN = 4                  # pixels kept between the boxes when crossing
AFTER = 40                  # loops of the title again before the end
ZONE_Y = [gen44.HOME[1] + 16] + [y + 15 for y in gen44.LANES]  # home's lowest Y, the corridors'
assert ZONE_Y == [39, 71, 103, 135, 167]


def steps_ahead(due, lines, n):
    """the steps of the next N loops from DUE, as paced gives them"""
    out = []
    for _ in range(n):
        b = due // gen44.LINES_A_STEP
        out.append(b)
        due = due - b * gen44.LINES_A_STEP + lines
    return out


class Player:
    """chooses the keys of each loop from the game as its logic finds it"""

    def __init__(self, careful=CAREFUL, margin=MARGIN, press=PRESS):
        self.careful, self.margin, self.press = careful, margin, press
        self.goal = None
        self.rounds = 0
        self.last_round = 0
        self.last_state = None
        self.title_again = None
        self.done = False
        self.reckless_from = None
        self.asked = {}             # round: crossings asked of safe
        self.waited = {}            # round: and refused

    def safe(self, x, y0, y1, faces, ahead):
        """the runner from Y0 to Y1 at X, two lines a step, as far each loop
        as its steps take it exactly (AHEAD: the loops' steps): no face
        within the margin of its box in any step"""
        d = 2 if y1 > y0 else -2
        y = y0
        for b in ahead:
            move = abs(y1 - y) >= 2 * b
            for _ in range(b):
                if move:
                    y += d
                faces = [(fy, *patrol_step(fx, st)) for fy, fx, st in faces]
                for fy, fx, _ in faces:
                    if abs(fx - x) < 16 + self.margin and abs(fy - y) < 16:
                        return False
            if y == y1:
                return True
        raise AssertionError("a crossing longer than the steps looked at")

    @staticmethod
    def toward(x, tx, b):
        if abs(tx - x) < 2 * b:
            return set()
        return {"right"} if x < tx else {"left"}

    @staticmethod
    def vertical(y, goal, b):
        if abs(goal - y) < 2 * b:
            return set()
        return {"down"} if goal > y else {"up"}

    def choose(self, g):
        st = g.state
        if st != self.last_state:
            if st == TITLE and self.rounds:
                self.title_again = 0
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
        b = g.steps_owed()
        rnd = bcd(g.roundno) + (1 if g.gems == 0 else 0)     # cleared comes first
        self.rounds = max(self.rounds, rnd)
        y, x = g.copy[0], g.copy[1]
        faces = g.faces()
        if self.goal is not None:
            if y == self.goal:
                self.goal = None
            else:
                return self.vertical(y, self.goal, b)
        if rnd > self.careful:
            if self.reckless_from is None:
                self.reckless_from = g.loop
            lane = gen44.LANES[0] - 1
            if y != lane:
                self.goal = lane
                return self.vertical(y, lane, b)
            return self.toward(x, faces[0][1], b) or {"left" if faces[0][1] < x else "right"}
        zone = Player.zone_of(y)
        cells = g.gem_cells()
        if g.gems == 0 or not cells or zone is None:
            return set()
        zone_of_row = {r: 1 + gen44.GEM_ROWS.index(r) // 2 for r in gen44.GEM_ROWS}

        def target_x(c):
            return min(max(8 * (c - 1), gen44.X_MIN), gen44.X_MAX)
        r, c = min(cells, key=lambda rc: (60 * abs(zone_of_row[rc[0]] - zone) +
                                          abs(target_x(rc[1]) - x), rc))
        tz, tx = zone_of_row[r], target_x(c)
        if tz == zone:
            return self.toward(x, tx, b)
        nz = zone + (1 if tz > zone else -1)
        y1 = ZONE_Y[nz]
        self.asked[rnd] = self.asked.get(rnd, 0) + 1
        if self.safe(x, y, y1, faces, steps_ahead(g.due, g.lines, 64)):
            self.goal = y1
            return self.vertical(y, y1, b)
        self.waited[rnd] = self.waited.get(rnd, 0) + 1
        return self.toward(x, tx, b)

    @staticmethod
    def zone_of(y):
        if y <= ZONE_Y[0]:
            return 0
        return ZONE_Y.index(y) if y in ZONE_Y else None


# ---------------------------------------------------------------- a play
def keys_at(events, frame):
    held = set()
    for f in sorted(events):
        if f > frame:
            break
        held = events[f]
    return held


def plan(machine, player=None, game=None, limit=8000):
    """the model on MACHINE played by PLAYER: (the keys of each loop, the
    game, the loops' records)"""
    player = player or Player()
    g = game or Grin(machine)
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
    assert player.done, "the play did not end"
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
        mask = 0
        for name in k:
            mask |= ROW8[name]
        out[f] = "keymatrixup 8 0xF1" + (f"; keymatrixdown 8 0x{mask:02X}" if mask else "")
    return out


def replay(ev, loops, machine, **kw):
    g = Grin(machine, **kw)
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
    lines = [f"# game_{TAG[machine]}.events -- chapter 44: the keys of the play planned for the "
             f"{hz} Hz machine,",
             "# written by model44.py: a frame (from INIT) and the cursor keys and SPACE held from then on"]
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
        print(f"{os.path.basename(events_path(m))}: {len(ev)} changes, {len(recs)} loops; "
              f"reckless from {player.reckless_from}; asked {player.asked}, waited {player.waited}")
        for e in g.events:
            if e[1] not in ("TOOK",):
                print("  ", e[:3] if e[1] != "ROUND" else (e[0], e[1], e[2], e[4], e[5]))


if __name__ == "__main__":
    main()
