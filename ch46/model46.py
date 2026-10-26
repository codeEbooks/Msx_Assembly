#!/usr/bin/env python3
"""model46.py - LANTERN KEEP finished, in Python, and a player who plans a
game through every room, lighting every lantern.

    python3 model46.py          game_eu.events, game_jp.events, over_eu.events
                                and over_jp.events

Keep is the game as gen46.py writes it, a loop at a time, on one of the two
machines: chapter 45's model45.Keep, with the guards, the lanterns, the
lives, the time, the score, the end and the music. The interrupt reads the
status from the frame the sends before drew (vdpscreen.py's rules 11 and
12: the C bit, from the sprites' pixels); counts the frame and its lines;
reads the keys; and ticks chapter 37's player, read from the cartridge by
player37.py: the tune at the title, hush in every other state. The sends
and the states' routines follow; it keeps what the RAM keeps, and what the
VRAM holds, so that meas46.py can hold every loop of a film against it.

Player chooses the keys of each loop. In a room it goes for a lantern not
yet lit, then for the door towards the nearest room with a lantern still
dark (rooms below). Its way is searched a loop at a time, over every place
the explorer can stand and every loop to come: the guards' rounds are known
(patrol's rule, a step at a time), and a place where the explorer's 16 x 16
pixels would share a column and a line with a guard's, at the end of a loop,
is not a place to be. It looks at the map once, when half the lanterns are
lit. OverPlayer walks into the gate hall's guard three times.
"""
import os
import sys
from collections import deque

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
CH45 = os.path.join(os.path.dirname(HERE), "ch45")
sys.path.insert(0, HERE)
import gen46       # noqa: E402
for _mod in ("vdpscreen", "player37", "model45"):
    sys.modules.pop(_mod, None)
sys.path.insert(0, CH45)                # chapter 45's model, with its own vdpscreen.py
import model45     # noqa: E402
sys.path.remove(CH45)
sys.modules.pop("vdpscreen", None)
sys.path.remove(HERE)
sys.path.insert(0, HERE)                # and this folder's files for this model
import vdpscreen   # noqa: E402
import player37    # noqa: E402
assert os.path.dirname(os.path.abspath(vdpscreen.__file__)) == HERE
assert os.path.dirname(os.path.abspath(player37.__file__)) == HERE

gen45 = gen46.gen45
EU, JP = gen46.EU, gen46.JP
TITLE, PLAY, FLIP, MAP, HIT, OVER, WIN = range(7)
NAMES = 0x1800
SAT, SPAT = 0x1B00, 0x3800
LINES = {EU: 313, JP: 262}
STEPL = 262
PACE_LINES = 313                    # the player's tick: 313 lines (chapter 37)
EVENT_AHEAD = {JP: 6, EU: 5}        # keys for the loop whose ticks is t: events at frame t + 6 on
                                    # the 60 Hz machine, t + 5 on the 50 Hz one, for INIT fills
                                    # frames 0 to 6, or 0 to 5, and the loop with ticks t wakes in
                                    # that frame (meas46.py holds every loop to it)
N, E, S, W = gen46.N, gen46.E, gen46.S, gen46.W
keys_byte, regs_of = model45.keys_byte, model45.regs_of
picture_order = model45.picture_order
MIXER_OFF = player37.MIXER_OFF


def bcd(n):
    return int(f"{n:02X}")


def tobcd(n):
    return int(str(n), 16)


def bcd3(num):
    return int("".join(f"{b:02X}" for b in num))


def to3(n):
    s = f"{n:06d}"
    return [int(s[i:i + 2], 16) for i in (0, 2, 4)]


class Music(player37.Player):
    """chapter 37's player, read from the cartridge, with this chapter's
    hush and retune"""

    def hush(self):
        """a tick with the music silent, and the game's sound over C"""
        self.shadow[7] = MIXER_OFF
        self.shadow[8:11] = [0, 0, 0]
        x = self.chans[3]
        if x["WAITS"]:
            x["WAITS"] -= 1
            self.sound(x)
        return list(self.shadow)

    def retune(self):
        """the tune from its first bar: shadow and the channels from start"""
        self.tick, self.barno, self.rowno = 1, 0, 0
        self.step = self.sym["song"] - 6
        at = self.sym["start"]
        self.shadow = list(self.mem[at:at + 11])
        at += 11
        for ch in self.chans:
            for f in player37.FIELDS:
                if f in player37.WORDS:
                    ch[f] = self.word(at)
                    at += 2
                else:
                    ch[f] = self.mem[at]
                    at += 1


class Keep(model45.Keep):
    """the game, a loop at a time, on MACHINE; LATE: late.asm"""

    def __init__(self, machine=JP, late=False, rom=None, hit_play=False, tune_always=False,
                 guards=None, cp=25):
        self.late = late
        self.hit_play, self.tune_always, self.cp = hit_play, tune_always, cp
        self.gtab = gen46.gtab(guards)
        self.music = Music(rom or os.path.join(HERE, "late" if late else "game"))
        self.owed = 0
        self.psg = []                       # (loop, the 11 bytes a tick sent)
        self.fx_asked = []                  # (loop, sound, taken)
        self.lives = 0
        self.nlit = 0
        self.time = [0, 0]
        self.tock = 0
        self.left = 0
        self.dimmed = 0
        self.back = [0, 0]
        self.lit = [0] * 32
        self.gd = [[0, 0, 0, 0], [0, 0, 0, 0]]
        self.score = [0, 0, 0]
        self.hi = list(gen46.HI_START)
        model45.Keep.__init__(self, machine)
        for t in range(3):
            self.vram[0x800 * t:0x800 * t + 2048] = bytes(gen46.shape_set())
            self.vram[0x2000 + 0x800 * t:0x2000 + 0x800 * t + 2048] = bytes(gen46.colour_set())
        self.vram[SPAT:SPAT + 64] = bytes(gen46.SPRITE_PATTERNS)
        self.title0()
        self.events = []

    # ---------------------------------------------------------- the interrupt and the sends
    def status_of(self, sat):
        v = bytearray(16384)
        v[SAT:SAT + 32] = sat
        v[SPAT:SPAT + 64] = bytes(gen46.SPRITE_PATTERNS)
        regs = regs_of(gen45.GAME_R3, gen45.GAME_R4)
        five, number = vdpscreen.sprite_status(v, regs)
        c, _ = vdpscreen.coincidence(v, regs)
        return 0x80 | five << 6 | c << 5 | number

    def isr_tail(self, keys):
        self.held = keys_byte(keys)
        o = self.owed + self.lines
        if o >= PACE_LINES:
            self.owed = o - PACE_LINES
            self.psg.append((self.loop, list(self.music.shadow)))     # tochip: last tick's
            if self.state == TITLE or self.tune_always:
                self.music.play()
            else:
                self.music.hush()
        else:
            self.owed = o

    def sends(self):
        self.vram[SAT:SAT + 13] = bytes(self.copy)
        for addr, name in self.queue:
            self.vram[(addr & 0x3FFF)] = name
        self.queue = []
        if self.whole:
            self.whole = 0
            self.show(self.names[32:] if self.wsrc == "names" else self.mapn, self.wr3, self.wr4)
        self.drawn_sat = bytes(self.vram[SAT:SAT + 32])
        self.drawn_regs = (self.r3, self.r4)

    def run(self, keys=None):
        {TITLE: self.title1, PLAY: self.play1, FLIP: self.flip1, MAP: self.map1, HIT: self.hit1,
         OVER: self.over1, WIN: self.over1}[self.state]()

    def go(self, state):
        self.state = state
        self.events.append((self.loop, gen46.STATES[state]))
        {TITLE: self.title0, PLAY: self.play0, FLIP: self.flip0, MAP: self.map0, HIT: self.hit0,
         OVER: self.over0, WIN: self.win0}[state]()

    def fx(self, name):
        taken = self.music.sfx(gen46.SOUND[name])
        self.fx_asked.append((self.loop, name, taken))

    # ---------------------------------------------------------- the VRAM written by the run
    def vwrite(self, addr, data):
        self.vram[addr:addr + len(data)] = bytes(data)

    def put3(self, addr, num):
        self.vwrite(addr, [0x30 + (b >> s & 15) for b in num for s in (4, 0)])

    # ---------------------------------------------------------- the states
    def title0(self):
        self.music.retune()
        self.vram[NAMES:NAMES + 768] = bytes(gen46.title_names())
        self.put3(NAMES + 32 * gen46.TITLE_HI[1] + gen46.TITLE_HI[0], self.hi)
        self.screen = True
        self.copy = gen46.title_copy()
        self.gd[0] = gen46.tround()

    def title1(self):
        for _ in range(self.paced()):
            self.patrol(0)
        if self.held & 0x10:
            return
        self.setup()
        self.events.append((self.loop, "PRESSED"))
        self.go(FLIP)

    def setup(self):
        self.queue = []
        self.nlit = 0
        self.been = [0] * 16
        self.lit = [0] * 32
        self.score = [0, 0, 0]
        self.lives = gen46.LIVES
        self.time = list(gen46.TIME0)
        self.tock = gen46.TICKS
        self.room = gen46.START
        self.copy[0:4] = gen46.first_copy()

    def greset(self):
        row = self.gtab[12 * self.room:12 * self.room + 12]
        self.copy[4:6] = row[0:2]
        self.gd[0] = row[2:6]
        self.copy[8:10] = row[6:8]
        self.gd[1] = row[8:12]

    def lights(self):
        for j, (c, r) in enumerate(gen46.LANTERNS[self.room]):
            if self.lit[2 * self.room + j]:
                self.names[32 * r + c] = gen46.LIT

    def flip0(self):
        self.unpack(self.room)
        self.lights()
        self.post(gen46.ROOM_AT, ord("ABCD"[self.room & 3]))
        self.post(gen46.ROOM_AT + 1, ord("1") + (self.room >> 2 & 3))
        self.fresh = 0
        if not self.been[self.room]:
            self.been[self.room] = 1
            self.fresh = 1
        if not self.late:
            self.greset()
        self.back = [self.copy[0], self.copy[1]]
        self.events.append((self.loop, "ROOM", self.room, self.fresh, list(self.copy[:2])))
        self.page("names", gen45.GAME_R3, gen45.GAME_R4)

    def flip1(self):
        if self.late:
            self.greset()
        self.go(PLAY)

    def patrol(self, k):
        at, lo, n, step = self.gd[k]
        i = at - (gen46.COPY_AT & 255)
        v = self.copy[i]
        a = (v + step) & 255
        if (a - lo) & 255 >= n:
            step = (-step) & 255
            self.gd[k][3] = step
            a = (v + step) & 255
        self.copy[i] = a

    def guards(self):
        self.patrol(0)
        self.patrol(1)

    def clock(self):
        """a step of the time -> True when none is left"""
        self.tock -= 1
        if self.tock:
            return False
        self.tock = gen46.TICKS
        n = bcd(self.time[0]) * 100 + bcd(self.time[1]) - 1
        self.time = [n // 100, tobcd(n % 100)]
        self.post(gen46.TIME_AT, 0x30 + self.time[0])
        self.post2(gen46.TIME_AT + 1, self.time[1])
        return n == 0

    def addten(self, a):
        self.score = to3(bcd3(self.score) + 10 * bcd(a))

    def lamps(self):
        for j in range(2):
            self.lamp(2 * self.room + j)
        if self.nlit == 0x32:
            self.go(WIN)

    def lamp(self, n):
        if self.lit[n]:
            return
        c, r = gen46.LANTERNS[n // 2][n % 2]
        x, y = self.copy[1], self.copy[0]
        if (x + 16 - 8 * c) & 255 >= self.cp or (y + 17 - 8 * r) & 255 >= self.cp:
            return
        self.lit[n] = 1
        self.post(32 * r + c, gen46.LIT)
        self.addten(0x10)
        self.nlit = tobcd(bcd(self.nlit) + 1)
        self.post2(gen46.LIT_AT, self.nlit)
        self.fx("S_LAMP")
        self.events.append((self.loop, "LAMP", n // 2, n, [x, y], bcd(self.nlit),
                            bcd(self.time[0]) * 100 + bcd(self.time[1])))
        if self.lit[n & ~1] and self.lit[n | 1]:
            self.glow(n // 2, gen46.GLOW_C)

    def glow(self, k, c):
        a = gen46.piccol()[k] & 0x3FFF
        self.vwrite(a, gen46.picture_colours(c))

    def play0(self):
        self.due = 0
        self.was = self.held

    def play1(self):
        if self.fresh:
            self.mini()
            self.play0()
            return
        if self.stat & 0x20:
            self.events.append((self.loop, "TOUCH", self.room, list(self.copy[:12])))
            self.go(HIT)
            return
        if self.presses() & gen45.MAP_BIT:
            self.go(MAP)
            return
        for _ in range(self.paced()):
            way = self.walk()
            if way:
                self.leave(way)
                return
            self.guards()
            if self.clock():
                self.go(OVER)
                return
        self.lamps()

    def hit0(self):
        self.lives -= 1
        self.post(gen46.LIVES_AT, 0x30 + self.lives)
        self.left = gen46.STILL
        self.fx("S_TOUCH")

    def countdown(self):
        b = self.paced()
        self.left = max(0, self.left - b)
        return self.left

    def hit1(self):
        if self.countdown():
            return
        if self.lives == 0:
            self.go(OVER)
            return
        self.copy[0], self.copy[1] = self.back
        if self.hit_play:
            self.greset()
            self.go(PLAY)
            return
        self.go(FLIP)

    def over0(self):
        self.fx("S_OVER")
        self.ending(gen46.OVER_TEXT)

    def win0(self):
        self.score = to3(bcd3(self.score) + bcd(self.time[0]) * 100 + bcd(self.time[1]))
        self.fx("S_WIN")
        self.ending(gen46.WIN_TEXT)

    def ending(self, text):
        self.copy[0] = 0xD0
        if self.score > self.hi:
            self.hi = list(self.score)
        box = gen46.box_names(text)
        for r in range(gen46.BOX_H):
            self.vwrite(NAMES + 32 * (gen46.BOX_ROW + r) + gen46.BOX_COL, box[24 * r:24 * r + 24])
        self.put3(NAMES + 32 * gen46.SCORE_DIG[1] + gen46.SCORE_DIG[0], self.score)
        self.put3(NAMES + 32 * gen46.HI_DIG[1] + gen46.HI_DIG[0], self.hi)
        self.left = gen46.ENDS
        self.dimmed = 0
        self.events.append((self.loop, "ENDED", text, bcd3(self.score), bcd3(self.hi), self.lives,
                            bcd(self.time[0]) * 100 + bcd(self.time[1]), bcd(self.nlit)))

    def over1(self):
        if self.dimmed < 16:
            self.glow(self.dimmed, gen46.PAPER_C)
            self.dimmed += 1
        if self.countdown():
            return
        self.go(TITLE)

    # ---------------------------------------------------------- what the RAM holds
    def ram(self):
        out = model45.Keep.ram(self)
        del out["seen"]
        out.update({"lives": self.lives, "nlit": self.nlit, "time": list(self.time),
                    "tock": self.tock, "left": self.left, "dimmed": self.dimmed,
                    "back": list(self.back), "lit": list(self.lit),
                    "gd": [list(g) for g in self.gd], "score": list(self.score),
                    "hi": list(self.hi)})
        return out

    def engine(self):
        """the player's page, as the Z80 keeps it: [(offset, bytes)]"""
        p = self.music
        out = [(0, [p.ticks & 255, p.ticks >> 8, self.owed & 255, self.owed >> 8, self.lines & 255,
                    self.lines >> 8, p.tick, p.step & 255, p.step >> 8, p.barno, p.rowno])]
        body = list(p.shadow)
        for ch in p.chans:
            for f in player37.FIELDS:
                v = ch[f]
                body += [v & 255, v >> 8] if f in player37.WORDS else [v & 255]
        out.append((gen46.gen37.SHADOW_AT, body))
        return out

    def guard_places(self):
        """[(X, Y, step, the coordinate's index in the copy, least, places)] of
        the guards shown"""
        out = []
        for k in range(2):
            y, x = self.copy[4 + 4 * k], self.copy[5 + 4 * k]
            if y == 0xD0:
                continue
            at, lo, n, step = self.gd[k]
            out.append((x, y, step, at - (gen46.COPY_AT & 255), lo, n))
        return out


# ---------------------------------------------------------------- the search
XS_ALL = list(range(0, gen46.X_LAST + 1, 2))
YS_ALL = list(range(gen46.Y_FIRST, gen46.Y_LAST + 1, 2))
NX, NY = len(XS_ALL), len(YS_ALL)
PX = np.repeat(np.array(XS_ALL), NY)
PY = np.tile(np.array(YS_ALL), NX)
KEYSETS = [(), ("left",), ("right",), ("up",), ("down",), ("left", "up"), ("left", "down"),
           ("right", "up"), ("right", "down")]
OUT = {N: -1, E: -2, S: -3, W: -4}
WAY_OF_OUT = {v: k for k, v in OUT.items()}


def index(x, y):
    return (x // 2) * NY + (y - gen46.Y_FIRST) // 2


class Room:
    """walk's step in room K, from every place, with every keyset"""

    def __init__(self, k):
        self.k = k
        self.r = model45.Room(k)
        self.free = np.zeros(NX * NY, dtype=bool)
        for x, y in self.r.places:
            self.free[index(x, y)] = True
        self.trans = np.full((len(KEYSETS), NX * NY), -9, dtype=np.int64)
        for p in np.flatnonzero(self.free):
            x, y = int(PX[p]), int(PY[p])
            for c, ks in enumerate(KEYSETS):
                q = self.r.step((x, y), ks)
                self.trans[c, p] = OUT[q] if q in OUT else index(*q)


ROOMS_W = {}


def room_of(k):
    if k not in ROOMS_W:
        ROOMS_W[k] = Room(k)
    return ROOMS_W[k]


def schedule(due, lines, n):
    """the steps of the next N loops from DUE, as paced gives them"""
    out = []
    for _ in range(n):
        b = due // STEPL
        out.append(b)
        due = due - b * STEPL + lines
    return out


def future(guards, steps):
    """each guard's (X, Y) after 0 to STEPS steps of patrol's rule"""
    out = []
    for x, y, step, i, lo, n in guards:
        v = x if i % 4 == 1 else y
        s = step - 256 if step > 127 else step
        row = []
        for _ in range(steps + 1):
            row.append((v, y) if i % 4 == 1 else (x, v))
            a = v + s
            if not 0 <= a - lo < n:
                s = -s
                a = v + s
            v = a
        out.append(row)
    return out


MEET = np.zeros((31, 31), dtype=bool)          # [dy + 15, dx + 15]: the explorer at 0, a guard at dx, dy
for _dx, _dy in gen46.MEETS:
    MEET[_dy + 15, _dx + 15] = True


def search(g, goal, horizon=1200, safe=True, way=None):
    """the earliest way from where the explorer stands to GOAL (a mask of
    places, or a function of the loop and the guards' places giving one),
    a loop at a time, never ending a loop where its pixels' box meets a
    guard's -> [(keys, the place after, or the way out)]"""
    rm = room_of(g.room)
    sched = schedule(g.due, g.lines, horizon)
    cum = np.cumsum(sched)
    fut = future(g.guard_places(), int(cum[-1]))
    layer = np.zeros(NX * NY, dtype=bool)
    layer[index(g.copy[1], g.copy[0])] = True
    parents = []
    for t in range(horizon):
        b = sched[t]
        ok = np.ones(NX * NY, dtype=bool)
        gs = [row[cum[t]] for row in fut]
        if safe:
            for gx, gy in gs:
                ok &= ~((np.abs(PX - gx) <= 15) & (np.abs(PY - gy) <= 15))
        nxt = np.full(NX * NY, -1, dtype=np.int64)
        how = np.zeros(NX * NY, dtype=np.int8)
        src = np.flatnonzero(layer)
        out_hit = None
        for c in range(len(KEYSETS)):
            dst = src.copy()
            gone = np.zeros(len(src), dtype=np.int64)
            for _ in range(b):
                live = gone == 0
                d = rm.trans[c, dst[live]]
                outs = d < 0
                idx = np.flatnonzero(live)
                gone[idx[outs]] = d[outs]
                dst[idx[~outs]] = d[~outs]
            if way is not None and out_hit is None:
                w = np.flatnonzero(gone == OUT[way])
                if w.size:
                    out_hit = (int(src[w[0]]), c)
            keep = (gone == 0)
            d, s = dst[keep], src[keep]
            keep2 = ok[d] & (nxt[d] < 0)
            nxt[d[keep2]] = s[keep2]
            how[d[keep2]] = c
        if out_hit is not None:
            i, c = out_hit
            path = [(KEYSETS[c], ("out", way))]
            for k in range(t - 1, -1, -1):
                prv, hw = parents[k]
                path.append((KEYSETS[hw[i]], i))
                i = int(prv[i])
            return _places(path[::-1])
        parents.append((nxt, how))
        layer = nxt >= 0
        mask = goal(t, gs) if callable(goal) else goal
        if mask is not None:
            hit = np.flatnonzero(layer & mask)
            if hit.size:
                i = int(hit[0])
                path = []
                for k in range(t, -1, -1):
                    prv, hw = parents[k]
                    path.append((KEYSETS[hw[i]], i))
                    i = int(prv[i])
                return _places(path[::-1])
        if not layer.any():
            break
    return None


def _places(path):
    """[(keys, place index or ('out', way))] -> [(keys, (X, Y) or the way)]"""
    out = []
    for ks, at in path:
        if isinstance(at, tuple):
            out.append((ks, at[1]))
        else:
            out.append((ks, (int(PX[at]), int(PY[at]))))
    return out


def lantern_goal(g):
    places = np.zeros(NX * NY, dtype=bool)
    any_ = False
    for j, (c, r) in enumerate(gen46.LANTERNS[g.room]):
        if not g.lit[2 * g.room + j]:
            places |= (((PX + 16 - 8 * c) & 255) < 25) & (((PY + 17 - 8 * r) & 255) < 25)
            any_ = True
    return places if any_ else None


def way_to(room, lit):
    """the way out of ROOM towards the nearest room with a lantern not lit"""
    prev, q = {room: None}, deque([room])
    while q:
        k = q.popleft()
        if k != room and not (lit[2 * k] and lit[2 * k + 1]):
            while prev[k][0] != room:
                k = prev[k][0]
            return prev[k][1]
        for w in (N, E, S, W):
            if gen46.EXITS[k] & w:
                n = gen45.neighbour(k, w)
                if n not in prev:
                    prev[n] = (k, w)
                    q.append(n)
    return None


# ---------------------------------------------------------------- the players
PRESS = 80                  # the loop (its ticks) from which SPACE is held at the title
HELD = 3                    # for three loops
PEEK = 16                   # the lanterns lit when it looks at the map
LOOK = 60                   # loops it looks at the map
M_HELD = 2                  # loops M is held for a press
AFTER = 40                  # loops of the title again before the end


class Player:
    """chooses the keys of each loop from the game as its logic finds it"""

    def __init__(self, peek=PEEK, look=LOOK):
        self.peek, self.look = peek, look
        self.looks = 0
        self.holding = 0
        self.looking = None
        self.done = False
        self.ended = None
        self.plan = None            # [(keys, where it will be)], from the next loop on
        self.plans = []             # (loop, room, the goal, loops)

    def hold_m(self):
        self.holding = M_HELD - 1
        return {"m"}

    def title(self, g):
        if self.ended is not None:
            if g.loop - self.ended >= AFTER:
                self.done = True
            return set()
        return {"space"} if PRESS <= g.ticks < PRESS + HELD else set()

    def choose(self, g):
        if self.holding:
            self.holding -= 1
            return {"m"}
        st = g.state
        if st == TITLE:
            return self.title(g)
        if st in (OVER, WIN):
            if self.ended is None:
                self.ended = g.loop + 10 ** 6
            self.plan = None
            return set()
        if st == MAP:
            self.looking += 1
            return self.hold_m() if self.looking == self.look else set()
        if st != PLAY or g.fresh:
            self.plan = None
            return set()
        if self.looks == 0 and bcd(g.nlit) >= self.peek:
            self.looks = 1
            self.looking = 0
            self.plan = None
            return self.hold_m()
        return self.walk(g)

    def walk(self, g):
        here = (g.copy[1], g.copy[0])
        if self.plan and self.plan[0][2] == g.room and self.plan[0][3] == here:
            ks, at, _, _ = self.plan.pop(0)
            return set(ks)
        self.plan = None
        goal = lantern_goal(g)
        way = None
        if goal is None:
            way = way_to(g.room, g.lit)
            assert way is not None, (g.loop, g.room)
        found = search(g, goal, way=way)
        assert found, (g.loop, g.room, here, way)
        self.plans.append((g.loop, g.room, "door" if way else "lantern", len(found)))
        plan, at = [], here
        for ks, nxt in found:
            plan.append((ks, nxt, g.room, at))
            at = nxt
        self.plan = plan
        ks, _, _, _ = self.plan.pop(0)
        return set(ks)


class OverPlayer(Player):
    """walks into the gate hall's guard, three times"""

    def choose(self, g):
        st = g.state
        if st == TITLE:
            return self.title(g)
        if st in (OVER, WIN):
            if self.ended is None:
                self.ended = g.loop + 10 ** 6
            return set()
        if st != PLAY or g.fresh:
            self.plan = None
            return set()
        here = (g.copy[1], g.copy[0])
        if self.plan and self.plan[0][3] == here:
            ks, _, _, _ = self.plan.pop(0)
            return set(ks)
        if self.plan == []:
            return set()                        # there: wait for the touch

        def goal(t, gs):
            x0, y0 = gs[0]
            return MEET[np.clip(y0 - PY + 15, 0, 30), np.clip(x0 - PX + 15, 0, 30)] & \
                (np.abs(y0 - PY) <= 15) & (np.abs(x0 - PX) <= 15)
        found = search(g, goal, safe=False)
        assert found, (g.loop, "no way to the guard")
        plan, at = [], here
        for ks, nxt in found:
            plan.append((ks, nxt, g.room, at))
            at = nxt
        self.plan = plan
        self.plans.append((g.loop, g.room, "guard", len(found)))
        ks, _, _, _ = self.plan.pop(0)
        return set(ks)


LATE_ROUTE = [13, 9, 10, 6, 10, 6]  # late.asm's walk: B4, B3, C3, C2, C3, then north into C2 again
LATE_DOOR = (120, gen46.Y_FIRST)    # where it waits in C3: in the north door
AFTER_HIT = 60                      # loops of play after the touch's wait, before the end


class LatePlayer(Player):
    """late.asm's walk: through B3 and C3 to C2 and back to C3, lighting
    nothing; there it waits in the north door until leaving would put C3's
    lower guard over it in C2, and goes"""

    def __init__(self):
        Player.__init__(self)
        self.route = list(LATE_ROUTE)
        self.hit_over = None

    def choose(self, g):
        st = g.state
        if st == TITLE:
            return self.title(g)
        if st == HIT:
            self.plan = None
            self.hit_over = None
            return set()
        if self.hit_over is None and any(e[1] == "TOUCH" for e in g.events):
            self.hit_over = g.loop
        if self.hit_over is not None and g.loop - self.hit_over >= AFTER_HIT:
            self.done = True
        if st != PLAY or g.fresh:
            self.plan = None
            return set()
        if self.route and self.route[0] == g.room:
            self.route.pop(0)
            self.plan = None
        here = (g.copy[1], g.copy[0])
        if self.route:
            nxt = self.route[0]
            way = next(w for w in (N, E, S, W) if gen46.EXITS[g.room] & w and
                       gen45.neighbour(g.room, w) == nxt)
            if g.room == 10 and len(self.route) == 1:
                return self.wait_north(g, here)
            if self.plan and self.plan[0][3] == here:
                ks, _, _, _ = self.plan.pop(0)
                return set(ks)
            found = search(g, None, way=way)
            assert found, (g.loop, g.room, way)
            self.plan, at = [], here
            for ks, nx in found:
                self.plan.append((ks, nx, g.room, at))
                at = nx
            self.plans.append((g.loop, g.room, "door", len(found)))
            ks, _, _, _ = self.plan.pop(0)
            return set(ks)
        return set()

    def wait_north(self, g, here):
        if here != LATE_DOOR:
            if self.plan and self.plan[0][3] == here:
                ks, _, _, _ = self.plan.pop(0)
                return set(ks)
            goal = np.zeros(NX * NY, dtype=bool)
            goal[index(*LATE_DOOR)] = True
            found = search(g, goal)
            assert found, (g.loop, "the door")
            self.plan, at = [], here
            for ks, nx in found:
                self.plan.append((ks, nx, g.room, at))
                at = nx
            self.plans.append((g.loop, g.room, "wait", len(found)))
            ks, _, _, _ = self.plan.pop(0)
            return set(ks)
        gy, gx = g.copy[8], g.copy[9]            # C3's lower guard, where leaving leaves it
        if (gx - LATE_DOOR[0], gy - gen46.Y_LAST) in gen46.MEETS:
            self.route.pop(0)
            return {"up"}
        return set()


# ---------------------------------------------------------------- a game
def fix_title_end(player, g):
    if player.ended is not None and player.ended > 10 ** 5 and g.state == TITLE:
        player.ended = g.loop


def plan(machine, player=None, game=None, limit=40000):
    """the model on MACHINE played by PLAYER: (the keys of each loop, the
    game, the loops' records)"""
    player = player or Player()
    g = game or Keep(machine)
    keys_by_loop, recs = [], []
    while not player.done and g.loop < limit:
        g.loop += 1
        g.isr_head()
        fix_title_end(player, g)
        keys = player.choose(g)
        g.isr_tail(keys)
        g.sends()
        keys_by_loop.append((g.ticks, frozenset(keys)))
        g.run()
        recs.append(g.ram())
    assert player.done, "the game did not end"
    return keys_by_loop, g, recs


tcl_events, keys_at = model45.tcl_events, model45.keys_at


def events_of(keys_by_loop, machine):
    out, last = {}, frozenset()
    for t, k in keys_by_loop:
        if k != last:
            out[t + EVENT_AHEAD[machine]] = k
            last = k
    return out


read_events = model45.read_events


def replay(ev, loops, machine, **kw):
    g = Keep(machine, **kw)
    recs = []
    for _ in range(loops):
        g.step_loop(keys_at(ev, g.ticks + 1 + EVENT_AHEAD[machine]))
        recs.append(g.ram())
    return g, recs


TAG = {EU: "eu", JP: "jp"}
PLAYS = {"game": Player, "over": OverPlayer, "late": LatePlayer}


def events_path(play, machine):
    return os.path.join(HERE, f"{play}_{TAG[machine]}.events")


def write_events(path, ev, play, machine):
    hz = {EU: "50", JP: "60"}[machine]
    what = {"game": "the game planned", "over": "three touches and GAME OVER, planned",
            "late": "late.asm's walk to C3's north door, planned"}[play]
    lines = [f"# {play}_{TAG[machine]}.events -- chapter 46: the keys of {what} for the "
             f"{hz} Hz machine,",
             "# written by model46.py: a frame (from INIT) and the keys held from then on"]
    for f, k in sorted(ev.items()):
        lines.append(f"{f} {' '.join(sorted(k)) or '-'}")
    with open(path, "w") as fh:
        fh.write("\n".join(lines) + "\n")


def main(plays=("game", "over", "late")):
    for play in plays:
        for m in (JP, EU):
            player = PLAYS[play]()
            late = play == "late"
            keys, g, recs = plan(m, player=player, game=Keep(m, late=late))
            ev = events_of(keys, m)
            write_events(events_path(play, m), ev, play, m)
            g2, recs2 = replay(ev, len(recs), m, late=late)
            assert recs2 == recs
            lamps = [e for e in g.events if e[1] == "LAMP"]
            touches = [e for e in g.events if e[1] == "TOUCH"]
            ended = [e for e in g.events if e[1] == "ENDED"]
            print(f"{os.path.basename(events_path(play, m))}: {len(ev)} changes, {len(recs)} loops; "
                  f"{len(lamps)} lanterns, {len(touches)} touches, {ended}")


if __name__ == "__main__":
    main(sys.argv[1:] or ("game", "over", "late"))
