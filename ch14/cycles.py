"""cycles.py - the price of a Z80 instruction, from its machine cycles.

Zilog's manual describes every instruction as a list of machine cycles, and
each kind of cycle has a length in T-states:

    M1   opcode fetch       4   the processor also refreshes a row of memory
                                and adds 1 to R; 5 on the MSX, which adds a
                                wait state to every M1 (chapter 3)
    MR   memory read        3
    MW   memory write       3
    IO   port read or write 4
    +n   the processor working inside itself: an M1 or a read stretched by
         n T-states, or a cycle of its own of n T-states

This file turns an instruction's bytes into that list, from the opcode's bit
fields, and the list into T-states and R: Zilog's, and the MSX's, which is
Zilog's with one more T-state in every M1. It knows the instructions that do
not jump; the jumps, calls and returns are chapter 11's and 12's, and the
block instructions chapter 13's.
"""

# a cycle is (name, T-states)
M1, MR, MW, IO = ("M1", 4), ("MR", 3), ("MW", 3), ("IO", 4)


def m1(extra=0):
    return ("M1", 4 + extra)


def mr(extra=0):
    return ("MR", 3 + extra)


def internal(n):
    return ("+", n)


ALU_N = {0xC6, 0xCE, 0xD6, 0xDE, 0xE6, 0xEE, 0xF6, 0xFE}


def plain(op):
    """the cycles of an unprefixed opcode (with (HL) where the opcode has it)"""
    x, y, z = op >> 6, (op >> 3) & 7, op & 7
    if x == 1:                                  # LD r,r'
        if op == 0x76:
            raise ValueError("HALT")
        if z == 6 or y == 6:
            return [M1, MR] if z == 6 else [M1, MW]
        return [M1]
    if x == 2:                                  # ADD, ADC, SUB, SBC, AND, XOR, OR, CP
        return [M1, MR] if z == 6 else [M1]
    if op in ALU_N:
        return [M1, MR]
    table = {
        0x00: [M1],                             # NOP
        0x02: [M1, MW], 0x12: [M1, MW],         # LD (BC),A  LD (DE),A
        0x0A: [M1, MR], 0x1A: [M1, MR],         # LD A,(BC)  LD A,(DE)
        0x22: [M1, MR, MR, MW, MW],             # LD (nn),HL
        0x2A: [M1, MR, MR, MR, MR],             # LD HL,(nn)
        0x32: [M1, MR, MR, MW],                 # LD (nn),A
        0x3A: [M1, MR, MR, MR],                 # LD A,(nn)
        0x07: [M1], 0x0F: [M1], 0x17: [M1], 0x1F: [M1],   # RLCA RRCA RLA RRA
        0x08: [M1], 0x27: [M1], 0x2F: [M1], 0x37: [M1], 0x3F: [M1],
        0xD9: [M1], 0xEB: [M1], 0xF3: [M1], 0xFB: [M1],   # EXX EX DE,HL DI EI
        0xD3: [M1, MR, IO], 0xDB: [M1, MR, IO],           # OUT (n),A  IN A,(n)
        0xE3: [M1, MR, mr(1), MW, ("MW", 5)],             # EX (SP),HL
        0xF9: [m1(2)],                                    # LD SP,HL
    }
    if op in table:
        return table[op]
    if x == 0 and z == 1:                       # LD rr,nn  /  ADD HL,rr
        return [M1, MR, MR] if y % 2 == 0 else [M1, internal(4), internal(3)]
    if x == 0 and z == 3:                       # INC rr, DEC rr
        return [m1(2)]
    if x == 0 and z in (4, 5):                  # INC r, DEC r
        return [M1, mr(1), MW] if y == 6 else [M1]
    if x == 0 and z == 6:                       # LD r,n
        return [M1, MR, MW] if y == 6 else [M1, MR]
    if x == 3 and z == 5 and y % 2 == 0:        # PUSH qq
        return [m1(1), MW, MW]
    if x == 3 and z == 1 and y % 2 == 0:        # POP qq
        return [M1, MR, MR]
    raise ValueError(f"not priced here: {op:02X}")


def cb(op, indexed=False):
    """the cycles after the prefix bytes of CB op, on a register or (HL);
    indexed: DD CB d op or FD CB d op"""
    x, z = op >> 6, op & 7
    if indexed:
        # DD, CB fetched as opcodes; d read; op read, and 2 to add d to IX;
        # then the byte read (and one more), and written back unless BIT
        head = [M1, M1, MR, mr(2)]
        return head + ([mr(1)] if x == 1 else [mr(1), MW])
    if z != 6:
        return [M1, M1]
    return [M1, M1, mr(1)] if x == 1 else [M1, M1, mr(1), MW]


ED = {}
for _y, _r in enumerate("bcdehl.a"):
    if _r != ".":
        ED[0x40 + 8 * _y] = [M1, M1, IO]                  # IN r,(C)
        ED[0x41 + 8 * _y] = [M1, M1, IO]                  # OUT (C),r
for _p in range(4):
    ED[0x42 + 16 * _p] = [M1, M1, internal(4), internal(3)]   # SBC HL,rr
    ED[0x4A + 16 * _p] = [M1, M1, internal(4), internal(3)]   # ADC HL,rr
    ED[0x43 + 16 * _p] = [M1, M1, MR, MR, MW, MW]             # LD (nn),rr
    ED[0x4B + 16 * _p] = [M1, M1, MR, MR, MR, MR]             # LD rr,(nn)
ED.update({0x44: [M1, M1],                                    # NEG
           0x46: [M1, M1], 0x56: [M1, M1], 0x5E: [M1, M1],    # IM 0, 1, 2
           0x47: [M1, m1(1)], 0x4F: [M1, m1(1)],              # LD I,A  LD R,A
           0x57: [M1, m1(1)], 0x5F: [M1, m1(1)],              # LD A,I  LD A,R
           0x67: [M1, M1, MR, internal(4), MW],               # RRD
           0x6F: [M1, M1, MR, internal(4), MW]})              # RLD


def indexed(op):
    """the cycles of DD op or FD op: the instruction op with IX or IY in
    place of HL, of H and L, or of (HL) with a distance"""
    x, y, z = op >> 6, (op >> 3) & 7, op & 7
    uses_mem = ((x == 1 and (z == 6 or y == 6) and op != 0x76) or (x == 2 and z == 6)
                or op in (0x34, 0x35, 0x36))
    if uses_mem:
        if op == 0x36:                          # LD (IX+d),n
            return [M1, M1, MR, mr(2), MW]
        if op in (0x34, 0x35):                  # INC, DEC (IX+d)
            return [M1, M1, MR, internal(5), mr(1), MW]
        base = plain(op)                        # LD r,(IX+d), LD (IX+d),r, ALU
        return [M1, M1, MR, internal(5)] + base[1:]
    return [M1] + plain(op)                     # IX for HL, IXH and IXL for H and L


def of(code):
    """the machine cycles of the instruction whose bytes are CODE"""
    b = list(code)
    if b[0] == 0xCB:
        return cb(b[1])
    if b[0] == 0xED:
        if b[1] not in ED:
            raise ValueError(f"not priced here: ED {b[1]:02X}")
        return ED[b[1]]
    if b[0] in (0xDD, 0xFD):
        if b[1] == 0xCB:
            return cb(b[3], indexed=True)
        return indexed(b[1])
    return plain(b[0])


def tstates(code):
    return sum(t for _, t in of(code))


def fetches(code):
    """how many opcode fetches, and so how much R goes up by"""
    return sum(1 for name, _ in of(code) if name == "M1")


def pattern(code):
    """the cycles written the way Zilog's manual writes them, e.g. 4,3,3"""
    return ",".join(str(t) for _, t in of(code))


# ---------------------------------------------------------------- the MSX
WAIT = 1                    # the wait state the MSX adds to every M1 (chapter 3)


def msx_of(code):
    """the machine cycles of CODE as the MSX runs them: every M1 one longer"""
    return [(name, t + WAIT) if name == "M1" else (name, t) for name, t in of(code)]


def msx(code):
    """the MSX price: Zilog's, plus one for every opcode fetch"""
    return sum(t for _, t in msx_of(code))


def msx_pattern(code):
    """the MSX cycles written the way Zilog writes them, e.g. 5,3"""
    return ",".join(str(t) for _, t in msx_of(code))
