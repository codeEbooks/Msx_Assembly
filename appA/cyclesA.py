"""cyclesA.py - the cycles that chapter 14's cycles.py leaves out, and the
MSX's price of every cycle list.

cycles.py prices every instruction that does not jump. These are the
others, written the same way, from the machine cycles of Zilog's manual:
the jumps, calls and returns, which chapters 11 and 12 timed; the block
instructions, chapter 13's; HALT; and the interrupt's answer, chapter 17's.
INI and its kind are the one place they differ from the manual, which
prints 4,5,3,4 as for OUTI: the port is read (4) before the byte is
written (3), 4,5,4,3.

    of(key, taken)  Zilog's cycles of the instruction whose prefixes and
                    opcode are KEY: for a jump on a condition, TAKEN says
                    whether it jumps; for LDIR and the other repeating block
                    instructions, whether it goes round again
    halt()          one turn of HALT
    answer(im)      the interrupt's answer in mode IM
    msx(cycles)     the same cycles as the MSX runs them: every opcode
                    fetch one T-state longer (chapter 3); the answer's own
                    first cycle is not a fetch from memory, and keeps its 7
                    (chapter 17 measured 13 and 19, Zilog's)

A cycle is (name, T-states), as in cycles.py; "INT" is the answer's own
first cycle, which reads no opcode from memory.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "ch14"))
from cycles import M1, MR, MW, IO, WAIT, m1, mr, internal  # noqa: E402

MW5 = ("MW", 5)                 # a write, and 2 T-states more


def jump(op, taken):
    if op == 0xC3:                                      # JP nn
        return [M1, MR, MR]
    if op & 0xC7 == 0xC2:                               # JP cc,nn: the same either way
        return [M1, MR, MR]
    if op == 0x18:                                      # JR e
        return [M1, MR, internal(5)]
    if op in (0x20, 0x28, 0x30, 0x38):                  # JR cc,e
        return [M1, MR, internal(5)] if taken else [M1, MR]
    if op == 0x10:                                      # DJNZ e
        return [m1(1), MR, internal(5)] if taken else [m1(1), MR]
    if op == 0xE9:                                      # JP (HL)
        return [M1]
    if op == 0xCD:                                      # CALL nn
        return [M1, MR, mr(1), MW, MW]
    if op & 0xC7 == 0xC4:                               # CALL cc,nn
        return [M1, MR, mr(1), MW, MW] if taken else [M1, MR, MR]
    if op == 0xC9:                                      # RET
        return [M1, MR, MR]
    if op & 0xC7 == 0xC0:                               # RET cc
        return [m1(1), MR, MR] if taken else [m1(1)]
    if op & 0xC7 == 0xC7:                               # RST p
        return [m1(1), MW, MW]
    raise ValueError(f"not a jump: {op:02X}")


def block(op, again):
    """ED op, op $A0 to $BB: one turn; AGAIN, a repeating one goes round"""
    z = op & 3
    turn = {0: [M1, M1, MR, MW5],                       # LDI: the byte read, written
            1: [M1, M1, MR, internal(5)],               # CPI: read, compared
            2: [M1, m1(1), IO, MW],                     # INI: from the port, written
            3: [M1, m1(1), MR, IO]}[z]                  # OUTI: read, to the port
    return turn + ([internal(5)] if again else [])


def of(key, taken=True):
    key = list(key)
    if key[0] == 0xED:
        if key[1] in (0x45, 0x4D):                      # RETN, RETI
            return [M1, M1, MR, MR]
        if 0xA0 <= key[1] <= 0xBB:
            return block(key[1], taken and key[1] >= 0xB0)
        raise ValueError(f"not priced here: ED {key[1]:02X}")
    if key[0] in (0xDD, 0xFD):
        if key[1] == 0xE9:                              # JP (IX), JP (IY)
            return [M1, M1]
        raise ValueError(f"not priced here: {key}")
    if key[0] == 0x76:
        return halt()
    return jump(key[0], taken)


def halt():
    """a turn of HALT: the processor fetches HALT again and again"""
    return [M1]


def answer(im):
    """the answer in mode 1, and in mode 0, where the MSX's bus holds $FF
    (chapter 17), RST 56: PC pushed; mode 2: and the address read from the
    table"""
    return [("INT", 7), MW, MW] + ([MR, MR] if im == 2 else [])


def msx(cycles):
    """the MSX's cycles: every M1 longer by the wait state"""
    return [(name, t + WAIT) if name == "M1" else (name, t) for name, t in cycles]


def tstates(cycles):
    return sum(t for _, t in cycles)


def fetches(cycles):
    """the cycles that add 1 to R: the fetches, and the answer's own"""
    return sum(1 for name, _ in cycles if name in ("M1", "INT"))


def pattern(cycles):
    return ",".join(str(t) for _, t in cycles)
