"""vdpslots.py -- when the TMS99x8 takes the processor's bytes (chapter 20).

    slot_after(cycle, slots)        the VDP cycle at which a byte written at
                                    CYCLE (of the frame) reaches the VRAM
    moments(cycle, machine, regs)   the moments of a line that apply at CYCLE
    play(events, machine, vram, regs=...)
                                    the VRAM after a run of port operations,
                                    the bytes the reads gave, and the lost ones

Time is counted in the VDP's cycles, six to a T-state, 1,368 to a line, from
the start of a frame, the units openMSX's debugger gives (chapter 8).

The rules, as chapter 20 states them:
  1. While the VDP draws the paper's 192 lines, from T-state 33 2/3 of the
     paper's first line to the same point of the line after its last (the
     left border of each line included), it lets the processor at the VRAM at
     19 moments of a line in Graphic I and II, GFX_SLOTS, and at 91 in text
     mode, TEXT_SLOTS. With the display off, and in every other line of the
     frame, at the 107 moments of OFF_SLOTS, 8 or 16 cycles apart.
  2. A byte written to $98, or a byte to be read from it, is dealt with at
     the first of those moments at least REACH cycles after the OUT or the IN.
  3. Until then the VDP is busy with it. A byte written in the meantime takes
     the place of the one waiting, which is lost, and the address goes up by
     one for the two; a read asked for in the meantime is not made, and the IN
     gives the byte the VDP last read or was given.
  4. A byte written to $99 never waits. (The address rules, the byte read
     ahead and the byte kept are chapter 19's.)

GFX_SLOTS, TEXT_SLOTS and OFF_SLOTS are the TMS9918A's memory cycles free for
the processor, four VDP cycles to one of the chip's own, as openMSX's authors
worked them out from Texas Instruments' manual and the timing drawings of Karl
Guttag, one of the chip's designers, and list them in openMSX's source
(src/video/VDPAccessSlots.cc); REACH is openMSX's 28 cycles, 4 2/3 T-states.
The chapter's pairs fix REACH and the start of the busy lines by themselves,
and meas20.py checks every byte of every program against this file.

Chapter 51 adds the V9938 and the V9958 of the MSX2 and the MSX2+, from the
same file of openMSX's source: in a character mode with the sprites on, the
31 moments of V99_CHAR_SPRITES a line while the paper is drawn, and the 154 of
V99_OFF in the other lines and with the display off; a byte reaches the first
of them V99_REACH cycles after its OUT, 16 (openMSX's VDP.cc: DELTA_16 for a
V99x8, DELTA_28 for an MSX1's VDP). A machine is one of these when CHIP says
"v99"; PAPER0 and LINES take any machine's numbers.
"""
LINE = 1368                 # VDP cycles a line: 228 T-states
PER_T = 6                   # VDP cycles a T-state
REACH = 28                  # cycles from a write to the first moment for it
BORDER_IN = 202             # the cycle of a line at which the VDP starts and
                            # stops drawing: T-state 33 2/3, where chapter 17
                            # found the frame's signal
PAPER0 = {"MSXBOOK_EU16": 69, "MSXBOOK_JP16": 42}    # the paper's first line
LINES = {"MSXBOOK_EU16": 313, "MSXBOOK_JP16": 262}   # lines a frame

# the moments of a line, in VDP cycles from its start, at which the VDP lets
# the processor at the VRAM while it draws Graphic I or II; in text mode; and
# in a line it does not draw. The last of each line is followed by the next
# line's first.
GFX_SLOTS = [4, 12, 20, 28, 116, 124, 132, 140, 220, 348, 476, 604, 732,
             860, 988, 1116, 1236, 1244, 1364]
TEXT_SLOTS = (list(range(4, 229, 8)) + [244] + list(range(268, 1181, 24)) +
              list(range(1196, 1365, 8)))
OFF_SLOTS = (list(range(4, 205, 8)) + list(range(220, 1229, 16)) +
             list(range(1236, 1365, 8)))


# chapter 51: the V9938's and the V9958's moments, from the same file of
# openMSX's source: a character mode (Graphic I, II) with the sprites on, and
# the lines it does not draw or the display off
V99_CHAR_SPRITES = [32, 96, 166, 174, 188, 220, 252, 316, 348, 380, 444, 476, 508, 572, 604,
                    636, 700, 732, 764, 828, 860, 892, 956, 988, 1020, 1084, 1116, 1148, 1212,
                    1268, 1334]
V99_OFF = [0, 8, 16, 24, 32, 40, 48, 56, 64, 72, 80, 88, 96, 104,
           112, 120, 164, 172, 180, 188, 196, 204, 212, 220, 228, 236, 244, 252,
           260, 268, 276, 292, 300, 308, 316, 324, 332, 340, 348, 356, 364, 372,
           380, 388, 396, 404, 420, 428, 436, 444, 452, 460, 468, 476, 484, 492,
           500, 508, 516, 524, 532, 548, 556, 564, 572, 580, 588, 596, 604, 612,
           620, 628, 636, 644, 652, 660, 676, 684, 692, 700, 708, 716, 724, 732,
           740, 748, 756, 764, 772, 780, 788, 804, 812, 820, 828, 836, 844, 852,
           860, 868, 876, 884, 892, 900, 908, 916, 932, 940, 948, 956, 964, 972,
           980, 988, 996, 1004, 1012, 1020, 1028, 1036, 1044, 1060, 1068, 1076, 1084, 1092,
           1100, 1108, 1116, 1124, 1132, 1140, 1148, 1156, 1164, 1172, 1188, 1196, 1204, 1212,
           1220, 1228, 1268, 1276, 1284, 1292, 1300, 1308, 1316, 1324, 1334, 1344, 1352, 1360]
V99_REACH = 16              # cycles from a write to the first moment for it, on a V99x8
CHIP = {}                   # machine -> "v99" for a V9938 or a V9958


def busy(cycle, machine):
    """is CYCLE (counted from the start of any frame) in the paper's lines?"""
    cycle %= LINES[machine] * LINE
    first = PAPER0[machine] * LINE + BORDER_IN
    return first <= cycle < first + 192 * LINE


def moments(cycle, machine, regs):
    """the moments that apply at CYCLE: the display on (R#1 bit 6) and the
    paper being drawn, Graphic I and II, or text mode (R#1 bit 4); else off.
    On a V99x8 (chapter 51), Graphic I and II with the sprites on"""
    if CHIP.get(machine) == "v99":
        if not regs[1] & 0x40 or not busy(cycle, machine):
            return V99_OFF
        assert not regs[1] & 0x10, "the V99x8's text mode is not in this file"
        return V99_CHAR_SPRITES
    if not regs[1] & 0x40 or not busy(cycle, machine):
        return OFF_SLOTS
    return TEXT_SLOTS if regs[1] & 0x10 else GFX_SLOTS


def active(cycle, machine, display_on=True):
    """the paper being drawn, the display on"""
    return display_on and busy(cycle, machine)


def slot_after(cycle, slots, reach=REACH):
    """the cycle at which a byte written at CYCLE is taken; SLOTS: a list of
    moments, or True for Graphic I and II's and False for the others'"""
    if slots is True or slots is False:
        slots = GFX_SLOTS if slots else OFF_SLOTS
    start = cycle + reach
    line, at = divmod(start, LINE)
    for s in slots:
        if s >= at:
            return line * LINE + s
    return (line + 1) * LINE + slots[0]


def play(events, machine, vram=None, address=0, regs=None, display_on=True, taken=None):
    """events: [(cycle, port, value)] in order, the cycles counted from the
    start of one frame and on through the next; port 0x98 or 0x99; value
    None for a read. REGS: the VDP's registers before the first (by default
    Graphic I, the display on or off as DISPLAY_ON says). Returns (vram,
    reads, lost): the bytes the reads of $98 gave, and the indexes of the
    events whose byte was lost or whose read was not made. TAKEN, a dict if
    given, gets the cycle at which each event's byte was dealt with."""
    vram = bytearray(16384) if vram is None else bytearray(vram)
    if not regs:
        regs = [0, 0xC0 if display_on else 0x80, 0, 0, 0, 0, 0, 0]
    regs = list(regs)
    held = None                 # chapter 19: a first byte on $99
    kept = 0                    # chapter 19: the byte read ahead, or written
    waiting = None              # [cycle it is dealt with, "r" or "w", index]
    reads, lost = [], []

    def settle(now):
        nonlocal waiting, address, kept
        if waiting and waiting[0] <= now:
            if taken is not None:
                taken[waiting[2]] = waiting[0]
            if waiting[1] == "w":
                vram[address] = kept
            else:
                kept = vram[address]
            address = (address + 1) & 0x3FFF
            waiting = None

    def ask(cycle, kind, i):
        nonlocal waiting
        if not waiting:
            at = slot_after(cycle, moments(cycle, machine, regs),
                            V99_REACH if CHIP.get(machine) == "v99" else REACH)
            waiting = [at, kind, i]
        elif kind == "w" and waiting[1] == "w":
            lost.append(waiting[2])         # too soon: this byte takes its place
            waiting[2] = i
        else:
            lost.append(i)                  # too soon: not made

    for i, (cycle, port, value) in enumerate(events):
        settle(cycle)
        if port == 0x99:
            if value is None:               # the status
                held = None
            elif held is None:
                held = value
                address = (address & 0x3F00) | value
            else:
                first, held = held, None
                low = address & 0xFF if value & 0x80 else first
                address = ((value & 0x3F) << 8) | low
                if value & 0x80:
                    regs[value & 7] = first
                elif not value & 0x40:      # a read address: read ahead
                    ask(cycle, "r", i)
            continue
        held = None
        if value is None:                   # IN from $98
            reads.append(kept)
            ask(cycle, "r", i)
        else:                               # OUT to $98
            kept = value
            ask(cycle, "w", i)
    settle(1 << 40)
    return vram, reads, lost
