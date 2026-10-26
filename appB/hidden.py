"""hidden.py - Appendix A's model of the processor with the register it
leaves out, MEMPTR, and with what MEMPTR decides: bits 3 and 5 of F after
BIT b,(HL).

    Hidden      appA/z80.py's Z80, and:
        memptr  MEMPTR, the address the processor keeps from one
                instruction to the next (the rules below)
        step()  one instruction; then MEMPTR, and F's bits 3 and 5 after
                BIT b,(HL): those of MEMPTR's high byte

openMSX, like this model, gives SCF and CCF bits 3 and 5 of (F OR A) every
time (chapter 55): it keeps no Q, the copy of F that real Z80s use there.

MEMPTR, instruction by instruction (the same with IX or IY for HL):

    LD A,(BC) LD A,(DE) LD A,(nn)       the address + 1
    LD (BC),A LD (DE),A LD (nn),A       A, and the address's low byte + 1
    LD rr,(nn) LD (nn),rr               nn + 1
    ADD ADC SBC HL,rr                   HL + 1, HL before
    RLD RRD                             HL + 1
    EX (SP),HL                          HL after
    (IX+d), (IY+d)                      IX+d or IY+d
    JP nn  JP cc,nn  CALL  CALL cc      nn, jumping or not
    JR DJNZ  JR cc  RET cc              where it goes, if it jumps
    RET RETI RETN RST                   where it goes
    IN A,(n)                            A n, before, + 1
    OUT (n),A                           A, and n + 1
    IN r,(C) OUT (C),r                  BC + 1
    INI INIR  IND INDR                  BC + 1 or - 1, B before
    OUTI OTIR  OUTD OTDR                BC + 1 or - 1, B after
    CPI CPD                             MEMPTR + 1 or - 1
    LDIR LDDR CPIR CPDR going round     the address of the instruction + 1
    anything else                       as it was
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "appA"))
from z80 import Z80, F3, F5  # noqa: E402

PREFIX = (0xDD, 0xFD)


class Hidden(Z80):
    memptr = 0

    def step(self):
        m, pc = self.m, self.pc
        if self.halted:
            Z80.step(self)
            return
        k = pc
        while m[k] in PREFIX:
            k = (k + 1) & 0xFFFF
        idx = {0xDD: "ix", 0xFD: "iy"}.get(m[(k - 1) & 0xFFFF]) if k != pc else None
        op, op2 = m[k], m[(k + 1) & 0xFFFF]
        a, f = self.a, self.f
        bc, de, hl = self.bc, self.de, self.hl
        hx = getattr(self, idx) if idx else hl
        mp = self.memptr
        Z80.step(self)
        self.memptr = self.rule(m, pc, k, idx, op, op2, a, f, bc, de, hl, hx, mp, self.pc)
        if op == 0xCB and not idx and op2 >> 6 == 1 and op2 & 7 == 6:     # BIT b,(HL)
            self.f = (self.f & ~(F3 | F5)) | (self.memptr >> 8 & (F3 | F5))

    def rule(self, m, here, k, idx, op, op2, a, f, bc, de, hl, hx, mp, after):
        """MEMPTR after the instruction that starts at HERE, whose opcode,
        after any prefix, is at K: from the registers before it and AFTER,
        where it went"""
        nn = m[(k + 1) & 0xFFFF] | m[(k + 2) & 0xFFFF] << 8
        n = m[(k + 1) & 0xFFFF]
        x, y, z = op >> 6, op >> 3 & 7, op & 7
        d = m[(k + 1) & 0xFFFF]
        ixd = (hx + (d - 256 if d > 127 else d)) & 0xFFFF
        if idx and (op == 0xCB or op == 0x36 or op in (0x34, 0x35)
                    or (x == 1 and (y == 6) != (z == 6)) or (x == 2 and z == 6)):
            return ixd                                  # (IX+d)
        if op in (0x0A, 0x1A):
            return ((bc if op == 0x0A else de) + 1) & 0xFFFF
        if op in (0x02, 0x12):
            return a << 8 | (((bc if op == 0x02 else de) + 1) & 0xFF)
        if op == 0x3A:
            return (nn + 1) & 0xFFFF
        if op == 0x32:
            return a << 8 | ((nn + 1) & 0xFF)
        if op in (0x22, 0x2A):
            return (nn + 1) & 0xFFFF
        if x == 0 and z == 1 and y & 1:                 # ADD HL,rr
            return (hx + 1) & 0xFFFF
        if op == 0xE3:                                  # EX (SP),HL
            return getattr(self, idx) if idx else self.hl
        if op in (0xC3, 0xCD) or (x == 3 and z in (2, 4)):
            return nn                                   # JP, CALL: jumping or not
        if op in (0x18, 0xC9) or (x == 3 and z == 7):
            return after                                # JR, RET, RST
        if op == 0x10:                                  # DJNZ: if it jumps
            return after if (bc >> 8) != 1 else mp
        if (x == 0 and z == 0 and y >= 4) or (x == 3 and z == 0):
            self.f, f0 = f, self.f                      # JR cc, RET cc: if it jumps
            taken = self.cond(y - 4 if x == 0 else y)
            self.f = f0
            return after if taken else mp
        if op == 0xDB:
            return ((a << 8 | n) + 1) & 0xFFFF
        if op == 0xD3:
            return a << 8 | ((n + 1) & 0xFF)
        if op != 0xED:
            return mp
        x2, y2, z2 = op2 >> 6, op2 >> 3 & 7, op2 & 7
        if x2 == 1:
            if z2 in (0, 1):                            # IN r,(C)  OUT (C),r
                return (bc + 1) & 0xFFFF
            if z2 == 2:                                 # ADC, SBC HL,rr
                return (hl + 1) & 0xFFFF
            if z2 == 3:                                 # LD (nn),rr  LD rr,(nn)
                nn = m[(k + 2) & 0xFFFF] | m[(k + 3) & 0xFFFF] << 8
                return (nn + 1) & 0xFFFF
            if z2 == 5:                                 # RETN, RETI
                return after
            if z2 == 7 and y2 in (4, 5):                # RRD, RLD
                return (hl + 1) & 0xFFFF
            return mp
        if x2 == 2 and y2 >= 4 and z2 <= 3:
            down = y2 & 1
            again = after == here
            if z2 == 0:                                 # LDI ... LDDR
                return (here + 1) & 0xFFFF if again else mp
            if z2 == 1:                                 # CPI ... CPDR
                return (here + 1) & 0xFFFF if again else (mp + (-1 if down else 1)) & 0xFFFF
            if z2 == 2:                                 # INI ... INDR
                return (bc + (-1 if down else 1)) & 0xFFFF
            b1 = ((bc >> 8) - 1) & 255                  # OUTI ... OTDR
            return ((b1 << 8 | (bc & 255)) + (-1 if down else 1)) & 0xFFFF
        return mp
