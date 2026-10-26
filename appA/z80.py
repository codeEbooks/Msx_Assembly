"""z80.py - the MSX's processor, instruction by instruction, written from
Zilog's manual and from what the Z80 is known to do beyond it (bits 3 and 5
of F, the flags of the block instructions on ports: Appendix B): what each
instruction does to the registers, the flags and the memory, and the cycles
it puts on the bus, each opcode fetch 5 T-states long (chapter 3).

    cpu = Z80(rom)           a cartridge's bytes at $4000, the RAM from $C000
    cpu.pc = init            and the registers as the program needs them
    cpu.step()               one instruction
    cpu.log = []             if a list: (cycle, T-state) for every fetch,
                             read, write and port access

The book's machine as appA's programs see it: page 0 the BIOS, which they
never read, pages 1 and 2 the cartridge, page 3 the RAM; the ports of
MSXBOOK_EU16 that they use: the PSG's register select ($A0), write ($A1)
and read back ($A2, chapter 36), the primary slot register ($A8) and the
VDP's ($98, $99), whose writes go nowhere here. Any other port reads $FF.
No interrupt comes: the programs keep the VDP's signal off.
"""

# flags
FC, FN, FP, F3, FH, F5, FZ, FS = 1, 2, 4, 8, 16, 32, 64, 128
WAIT = 1                    # the MSX's wait state in every M1


def _parity(v):
    v ^= v >> 4
    v ^= v >> 2
    v ^= v >> 1
    return 0 if v & 1 else FP


SZP = [(v & (FS | F3 | F5)) | (FZ if v == 0 else 0) | _parity(v) for v in range(256)]
SZ = [(v & (FS | F3 | F5)) | (FZ if v == 0 else 0) for v in range(256)]


class Ports:
    """the ports of the book's machine that the programs use"""
    def __init__(self, a8=0):
        self.psg = [0] * 16
        self.latch = 0
        self.a8 = a8

    def read(self, port):
        p = port & 0xFF
        if p == 0xA2:
            return self.psg[self.latch]
        if p == 0xA8:
            return self.a8
        assert p not in (0x98, 0x99, 0xA9, 0xAA, 0xAB, 0x90, 0x91), hex(p)
        return 0xFF

    def write(self, port, v):
        p = port & 0xFF
        if p == 0xA0:
            self.latch = v & 0x0F
        elif p == 0xA1:
            self.psg[self.latch] = v
        elif p == 0xA8:
            self.a8 = v


class Z80:
    def __init__(self, rom=b"", ports=None):
        self.m = bytearray(b"\xFF" * 65536)
        self.m[0x4000:0x4000 + len(rom)] = rom
        self.ports = ports or Ports()
        self.a = self.f = self.b = self.c = self.d = self.e = self.h = self.l = 0
        self.a_ = self.f_ = self.b_ = self.c_ = self.d_ = self.e_ = self.h_ = self.l_ = 0
        self.ix = self.iy = self.sp = self.pc = 0
        self.i = self.r = 0
        self.iff1 = self.iff2 = 0
        self.im = 0
        self.halted = False
        self.t = 0
        self.log = None

    # ------------------------------------------------------------ the bus
    def cycle(self, name, n):
        if self.log is not None:
            self.log.append((name, self.t))
        self.t += n

    def fetch(self):
        """an opcode fetch: 4 T-states and the wait"""
        a = self.pc
        self.cycle("M1", 4 + WAIT)
        self.pc = (a + 1) & 0xFFFF
        self.r = (self.r & 0x80) | ((self.r + 1) & 0x7F)
        return self.m[a]

    def rd(self, a):
        self.cycle("MR", 3)
        return self.m[a & 0xFFFF]

    def wr(self, a, v):
        a &= 0xFFFF
        self.cycle("MW", 3)
        if a >= 0xC000:                 # below, the ROMs
            self.m[a] = v & 255

    def hold(self, n):
        """n T-states inside the processor"""
        self.t += n

    def arg(self):
        a = self.pc
        self.pc = (a + 1) & 0xFFFF
        return self.rd(a)

    def arg16(self):
        lo = self.arg()
        return lo | self.arg() << 8

    def port_in(self, port):
        self.cycle("IO", 4)
        return self.ports.read(port)

    def port_out(self, port, v):
        self.cycle("IO", 4)
        self.ports.write(port, v & 255)

    def push(self, v):
        self.sp = (self.sp - 1) & 0xFFFF
        self.wr(self.sp, v >> 8)
        self.sp = (self.sp - 1) & 0xFFFF
        self.wr(self.sp, v & 255)

    def pop(self):
        lo = self.rd(self.sp)
        hi = self.rd(self.sp + 1)
        self.sp = (self.sp + 2) & 0xFFFF
        return lo | hi << 8

    # ------------------------------------------------------------ registers
    @property
    def bc(self): return self.b << 8 | self.c

    @property
    def de(self): return self.d << 8 | self.e

    @property
    def hl(self): return self.h << 8 | self.l

    @property
    def af(self): return self.a << 8 | self.f

    def set_bc(self, v): self.b, self.c = v >> 8 & 255, v & 255
    def set_de(self, v): self.d, self.e = v >> 8 & 255, v & 255
    def set_hl(self, v): self.h, self.l = v >> 8 & 255, v & 255

    def rr(self, p, idx=None):
        """BC, DE, HL (or IX, IY), SP"""
        if p == 0:
            return self.bc
        if p == 1:
            return self.de
        if p == 2:
            return self.hl if idx is None else getattr(self, idx)
        return self.sp

    def set_rr(self, p, v, idx=None):
        v &= 0xFFFF
        if p == 0:
            self.set_bc(v)
        elif p == 1:
            self.set_de(v)
        elif p == 2:
            if idx is None:
                self.set_hl(v)
            else:
                setattr(self, idx, v)
        else:
            self.sp = v

    def get8(self, k, idx=None):
        """register k: B C D E H L - A; H and L as IXH and IXL after a prefix"""
        if k == 0: return self.b
        if k == 1: return self.c
        if k == 2: return self.d
        if k == 3: return self.e
        if k == 4: return self.h if idx is None else getattr(self, idx) >> 8
        if k == 5: return self.l if idx is None else getattr(self, idx) & 255
        return self.a

    def set8(self, k, v, idx=None):
        v &= 255
        if k == 0: self.b = v
        elif k == 1: self.c = v
        elif k == 2: self.d = v
        elif k == 3: self.e = v
        elif k == 4:
            if idx is None: self.h = v
            else: setattr(self, idx, (getattr(self, idx) & 0xFF) | v << 8)
        elif k == 5:
            if idx is None: self.l = v
            else: setattr(self, idx, (getattr(self, idx) & 0xFF00) | v)
        else: self.a = v

    def cond(self, y):
        f = self.f
        return [not f & FZ, bool(f & FZ), not f & FC, bool(f & FC),
                not f & FP, bool(f & FP), not f & FS, bool(f & FS)][y]

    # ------------------------------------------------------------ arithmetic
    def alu(self, y, v):
        a = self.a
        if y in (0, 1):                                  # ADD, ADC
            cy = self.f & FC if y == 1 else 0
            r = a + v + cy
            self.f = (SZ[r & 255] | (FC if r > 255 else 0) | ((a ^ v ^ r) & FH)
                      | (FP if (~(a ^ v) & (a ^ r) & 0x80) else 0))
            self.a = r & 255
        elif y in (2, 3, 7):                             # SUB, SBC, CP
            cy = self.f & FC if y == 3 else 0
            r = a - v - cy
            f = (SZ[r & 255] | FN | (FC if r < 0 else 0) | ((a ^ v ^ r) & FH)
                 | (FP if ((a ^ v) & (a ^ r) & 0x80) else 0))
            if y == 7:
                self.f = (f & ~(F3 | F5)) | (v & (F3 | F5))
            else:
                self.f = f
                self.a = r & 255
        elif y == 4:                                     # AND
            self.a = a & v
            self.f = SZP[self.a] | FH
        elif y == 5:                                     # XOR
            self.a = a ^ v
            self.f = SZP[self.a]
        else:                                            # OR
            self.a = a | v
            self.f = SZP[self.a]

    def inc8(self, v):
        r = (v + 1) & 255
        self.f = (self.f & FC) | SZ[r] | (FH if (r & 15) == 0 else 0) | (FP if r == 0x80 else 0)
        return r

    def dec8(self, v):
        r = (v - 1) & 255
        self.f = (self.f & FC) | SZ[r] | FN | (FH if (r & 15) == 15 else 0) | (FP if r == 0x7F else 0)
        return r

    def rot(self, y, v):
        """the rotations and shifts after CB"""
        c = self.f & FC
        if y == 0: out, r = v >> 7, (v << 1 | v >> 7)              # RLC
        elif y == 1: out, r = v & 1, (v >> 1 | (v & 1) << 7)       # RRC
        elif y == 2: out, r = v >> 7, (v << 1 | c)                 # RL
        elif y == 3: out, r = v & 1, (v >> 1 | c << 7)            # RR
        elif y == 4: out, r = v >> 7, v << 1                       # SLA
        elif y == 5: out, r = v & 1, (v >> 1 | (v & 0x80))         # SRA
        elif y == 6: out, r = v >> 7, (v << 1 | 1)                 # SLL (Appendix B)
        else: out, r = v & 1, v >> 1                               # SRL
        r &= 255
        self.f = SZP[r] | (FC if out else 0)
        return r

    def add16(self, x, y):
        r = x + y
        self.f = ((self.f & (FS | FZ | FP)) | (FC if r > 0xFFFF else 0)
                  | ((x ^ y ^ r) >> 8 & FH) | (r >> 8 & (F3 | F5)))
        return r & 0xFFFF

    def adc16(self, x, y, sub):
        c = self.f & FC
        r = x - y - c if sub else x + y + c
        r16 = r & 0xFFFF
        v = ((x ^ y) & (x ^ r) & 0x8000) if sub else (~(x ^ y) & (x ^ r) & 0x8000)
        self.f = ((FS if r16 & 0x8000 else 0) | (FZ if r16 == 0 else 0)
                  | (FC if (r < 0 or r > 0xFFFF) else 0) | (FP if v else 0)
                  | ((x ^ y ^ r) >> 8 & FH) | (FN if sub else 0) | (r16 >> 8 & (F3 | F5)))
        return r16

    # ------------------------------------------------------------ running
    def step(self):
        """one instruction, or one turn of HALT"""
        if self.halted:
            self.cycle("M1", 4 + WAIT)
            self.r = (self.r & 0x80) | ((self.r + 1) & 0x7F)
        else:
            self.execute(self.fetch())

    def interrupt(self):
        """the answer: in mode 2 through the table at I, in modes 0 and 1 to
        $0038 (in mode 0 the MSX's bus holds $FF, RST 56)"""
        if self.halted:
            self.halted = False
            self.pc = (self.pc + 1) & 0xFFFF
        self.iff1 = self.iff2 = 0
        self.r = (self.r & 0x80) | ((self.r + 1) & 0x7F)
        self.cycle("INT", 7)
        self.push(self.pc)
        if self.im == 2:
            v = self.i << 8 | 0xFF
            self.pc = self.rd(v) | self.rd(v + 1) << 8
        else:
            self.pc = 0x38

    def execute(self, op, idx=None):
        x, y, z = op >> 6, op >> 3 & 7, op & 7
        p, q = y >> 1, y & 1
        if x == 1:
            if op == 0x76:                              # HALT
                self.halted = True
                self.pc = (self.pc - 1) & 0xFFFF
            elif z == 6:                                # LD r,(HL)
                self.set8(y, self.rd(self.addr(idx)))
            elif y == 6:                                # LD (HL),r
                a = self.addr(idx)
                self.wr(a, self.get8(z))
            else:
                self.set8(y, self.get8(z, idx), idx)
        elif x == 2:                                    # ALU A,r
            v = self.rd(self.addr(idx)) if z == 6 else self.get8(z, idx)
            self.alu(y, v)
        elif x == 0:
            self.x0(y, z, p, q, idx)
        else:
            self.x3(op, y, z, p, q, idx)

    def addr(self, idx):
        """(HL), or (IX+d): d read, and 5 T-states adding it"""
        if idx is None:
            return self.hl
        d = self.arg()
        self.hold(5)
        return (getattr(self, idx) + (d - 256 if d > 127 else d)) & 0xFFFF

    def jr(self):
        d = self.arg()
        self.hold(5)
        self.pc = (self.pc + (d - 256 if d > 127 else d)) & 0xFFFF

    def x0(self, y, z, p, q, idx):
        if z == 0:
            if y == 0:
                pass                                    # NOP
            elif y == 1:                                # EX AF,AF'
                self.a, self.a_ = self.a_, self.a
                self.f, self.f_ = self.f_, self.f
            elif y == 2:                                # DJNZ
                self.hold(1)
                self.b = (self.b - 1) & 255
                if self.b:
                    self.jr()
                else:
                    self.arg()
            elif y == 3:                                # JR
                self.jr()
            elif self.cond(y - 4):                      # JR cc
                self.jr()
            else:
                self.arg()
        elif z == 1:
            if q == 0:                                  # LD rr,nn
                self.set_rr(p, self.arg16(), idx)
            else:                                       # ADD HL,rr
                self.hold(7)
                self.set_rr(2, self.add16(self.rr(2, idx), self.rr(p, idx)), idx)
        elif z == 2:
            if p in (0, 1):                             # LD (BC),A  LD A,(BC) ...
                a = self.bc if p == 0 else self.de
                if q == 0:
                    self.wr(a, self.a)
                else:
                    self.a = self.rd(a)
            elif p == 2:                                # LD (nn),HL  LD HL,(nn)
                nn = self.arg16()
                if q == 0:
                    v = self.rr(2, idx)
                    self.wr(nn, v & 255)
                    self.wr(nn + 1, v >> 8)
                else:
                    lo = self.rd(nn)
                    self.set_rr(2, lo | self.rd(nn + 1) << 8, idx)
            else:                                       # LD (nn),A  LD A,(nn)
                nn = self.arg16()
                if q == 0:
                    self.wr(nn, self.a)
                else:
                    self.a = self.rd(nn)
        elif z == 3:                                    # INC rr, DEC rr
            self.hold(2)
            self.set_rr(p, self.rr(p, idx) + (1 if q == 0 else -1), idx)
        elif z in (4, 5):                               # INC r, DEC r
            f = self.inc8 if z == 4 else self.dec8
            if y == 6:
                a = self.addr(idx)
                v = self.rd(a)
                self.hold(1)
                self.wr(a, f(v))
            else:
                self.set8(y, f(self.get8(y, idx)), idx)
        elif z == 6:                                    # LD r,n
            if y == 6:
                if idx is None:
                    self.wr(self.hl, self.arg())
                else:
                    d = self.arg()
                    n = self.arg()
                    self.hold(2)
                    self.wr((getattr(self, idx) + (d - 256 if d > 127 else d)) & 0xFFFF, n)
            else:
                self.set8(y, self.arg(), idx)
        else:                                           # z == 7
            a, f = self.a, self.f
            if y == 0:                                  # RLCA
                self.a = (a << 1 | a >> 7) & 255
                self.f = (f & (FS | FZ | FP)) | (a >> 7) | (self.a & (F3 | F5))
            elif y == 1:                                # RRCA
                self.a = (a >> 1 | a << 7) & 255
                self.f = (f & (FS | FZ | FP)) | (a & 1) | (self.a & (F3 | F5))
            elif y == 2:                                # RLA
                self.a = (a << 1 | f & FC) & 255
                self.f = (f & (FS | FZ | FP)) | (a >> 7) | (self.a & (F3 | F5))
            elif y == 3:                                # RRA
                self.a = (a >> 1 | (f & FC) << 7) & 255
                self.f = (f & (FS | FZ | FP)) | (a & 1) | (self.a & (F3 | F5))
            elif y == 4:                                # DAA
                c = f & FC
                corr = 0
                if f & FH or (a & 15) > 9:
                    corr |= 6
                if c or a > 0x99:
                    corr |= 0x60
                    c = FC
                if f & FN:
                    r = (a - corr) & 255
                    h = FH if (f & FH and (a & 15) < 6) else 0
                else:
                    r = (a + corr) & 255
                    h = FH if (a & 15) > 9 else 0
                self.a = r
                self.f = SZP[r] | c | h | (f & FN)
            elif y == 5:                                # CPL
                self.a = a ^ 255
                self.f = (f & (FS | FZ | FP | FC)) | FH | FN | (self.a & (F3 | F5))
            elif y == 6:                                # SCF
                self.f = (f & (FS | FZ | FP)) | FC | ((f | a) & (F3 | F5))
            else:                                       # CCF
                self.f = ((f & (FS | FZ | FP)) | (FH if f & FC else 0)
                          | (0 if f & FC else FC) | ((f | a) & (F3 | F5)))

    def x3(self, op, y, z, p, q, idx):
        if z == 0:                                      # RET cc
            self.hold(1)
            if self.cond(y):
                self.pc = self.pop()
        elif z == 1:
            if q == 0:                                  # POP
                v = self.pop()
                if p == 3:
                    self.a, self.f = v >> 8, v & 255
                else:
                    self.set_rr(p, v, idx)
            elif p == 0:                                # RET
                self.pc = self.pop()
            elif p == 1:                                # EXX
                self.b, self.b_ = self.b_, self.b
                self.c, self.c_ = self.c_, self.c
                self.d, self.d_ = self.d_, self.d
                self.e, self.e_ = self.e_, self.e
                self.h, self.h_ = self.h_, self.h
                self.l, self.l_ = self.l_, self.l
            elif p == 2:                                # JP (HL)
                self.pc = self.rr(2, idx)
            else:                                       # LD SP,HL
                self.hold(2)
                self.sp = self.rr(2, idx)
        elif z == 2:                                    # JP cc,nn
            nn = self.arg16()
            if self.cond(y):
                self.pc = nn
        elif z == 3:
            if y == 0:                                  # JP nn
                self.pc = self.arg16()
            elif y == 1:                                # CB
                if idx is None:
                    self.cb(self.fetch())
                else:
                    self.xcb(idx)
            elif y == 2:                                # OUT (n),A
                self.port_out(self.a << 8 | self.arg(), self.a)
            elif y == 3:                                # IN A,(n)
                self.a = self.port_in(self.a << 8 | self.arg())
            elif y == 4:                                # EX (SP),HL
                lo = self.rd(self.sp)
                hi = self.rd(self.sp + 1)
                self.hold(1)
                v = self.rr(2, idx)
                self.wr(self.sp + 1, v >> 8)
                self.wr(self.sp, v & 255)
                self.hold(2)
                self.set_rr(2, lo | hi << 8, idx)
            elif y == 5:                                # EX DE,HL
                self.d, self.h = self.h, self.d
                self.e, self.l = self.l, self.e
            elif y == 6:                                # DI
                self.iff1 = self.iff2 = 0
            else:                                       # EI
                self.iff1 = self.iff2 = 1
        elif z == 4:                                    # CALL cc,nn
            lo = self.arg()
            hi = self.arg()
            if self.cond(y):
                self.hold(1)
                self.push(self.pc)
                self.pc = lo | hi << 8
        elif z == 5:
            if q == 0:                                  # PUSH
                self.hold(1)
                self.push(self.af if p == 3 else self.rr(p, idx))
            elif p == 0:                                # CALL nn
                lo = self.arg()
                hi = self.arg()
                self.hold(1)
                self.push(self.pc)
                self.pc = lo | hi << 8
            elif p == 1:                                # DD
                self.execute(self.fetch(), "ix")
            elif p == 2:                                # ED
                self.ed(self.fetch())
            else:                                       # FD
                self.execute(self.fetch(), "iy")
        elif z == 6:                                    # ALU A,n
            self.alu(y, self.arg())
        else:                                           # RST
            self.hold(1)
            self.push(self.pc)
            self.pc = y * 8

    def cb(self, op):
        x, y, z = op >> 6, op >> 3 & 7, op & 7
        if z == 6:
            a = self.hl
            v = self.rd(a)
            self.hold(1)
        else:
            v = self.get8(z)
        if x == 1:                                      # BIT
            r = v & (1 << y)
            self.f = (self.f & FC) | FH | (SZP[r] & ~(F3 | F5)) | (v & (F3 | F5))
            return
        if x == 0:
            r = self.rot(y, v)
        elif x == 2:
            r = v & ~(1 << y)                           # RES
        else:
            r = v | 1 << y                              # SET
        if z == 6:
            self.wr(a, r)
        else:
            self.set8(z, r)

    def xcb(self, idx):
        """DD CB d op: d and op read, 2 T-states adding d"""
        d = self.arg()
        op = self.arg()
        self.hold(2)
        a = (getattr(self, idx) + (d - 256 if d > 127 else d)) & 0xFFFF
        x, y, z = op >> 6, op >> 3 & 7, op & 7
        v = self.rd(a)
        self.hold(1)
        if x == 1:
            r = v & (1 << y)
            self.f = (self.f & FC) | FH | (SZP[r] & ~(F3 | F5)) | (a >> 8 & (F3 | F5))
            return
        r = self.rot(y, v) if x == 0 else (v & ~(1 << y) if x == 2 else v | 1 << y)
        self.wr(a, r)
        if z != 6:
            self.set8(z, r)

    def ed(self, op):
        x, y, z = op >> 6, op >> 3 & 7, op & 7
        p, q = y >> 1, y & 1
        if x == 1:
            if z == 0:                                  # IN r,(C)
                v = self.port_in(self.bc)
                if y != 6:
                    self.set8(y, v)
                self.f = (self.f & FC) | SZP[v]
            elif z == 1:                                # OUT (C),r
                self.port_out(self.bc, 0 if y == 6 else self.get8(y))
            elif z == 2:                                # SBC HL,rr  ADC HL,rr
                self.hold(7)
                self.set_hl(self.adc16(self.hl, self.rr(p), q == 0))
            elif z == 3:                                # LD (nn),rr  LD rr,(nn)
                nn = self.arg16()
                if q == 0:
                    v = self.rr(p)
                    self.wr(nn, v & 255)
                    self.wr(nn + 1, v >> 8)
                else:
                    lo = self.rd(nn)
                    self.set_rr(p, lo | self.rd(nn + 1) << 8)
            elif z == 4:                                # NEG
                v = self.a
                self.a = 0
                self.alu(2, v)
            elif z == 5:                                # RETN, RETI
                self.iff1 = self.iff2
                self.pc = self.pop()
            elif z == 6:                                # IM
                self.im = [0, 0, 1, 2][y & 3]
            else:
                if y == 0:                              # LD I,A
                    self.hold(1)
                    self.i = self.a
                elif y == 1:                            # LD R,A
                    self.hold(1)
                    self.r = self.a
                elif y in (2, 3):                       # LD A,I  LD A,R
                    self.hold(1)
                    self.a = self.i if y == 2 else self.r
                    self.f = (self.f & FC) | SZ[self.a] | (FP if self.iff2 else 0)
                elif y in (4, 5):                       # RRD, RLD
                    a = self.hl
                    v = self.rd(a)
                    self.hold(4)
                    if y == 4:
                        r = (self.a << 4 | v >> 4) & 255
                        self.a = (self.a & 0xF0) | (v & 15)
                    else:
                        r = (v << 4 | self.a & 15) & 255
                        self.a = (self.a & 0xF0) | v >> 4
                    self.wr(a, r)
                    self.f = (self.f & FC) | SZP[self.a]
        elif x == 2 and y >= 4 and z <= 3:              # the block instructions
            step = 1 if y in (4, 6) else -1             # I or D; y 6, 7: repeat
            if z == 0:                                  # LDI LDD LDIR LDDR
                v = self.rd(self.hl)
                self.set_bc(self.bc - 1)
                self.wr(self.de, v)
                self.hold(2)
                n = (v + self.a) & 255
                self.f = ((self.f & (FS | FZ | FC)) | (FP if self.bc else 0)
                          | (n & F3) | (F5 if n & 2 else 0))
                if y >= 6 and self.bc:
                    self.hold(5)
                    self.pc = (self.pc - 2) & 0xFFFF
                self.set_hl(self.hl + step)
                self.set_de(self.de + step)
            elif z == 1:                                # CPI CPD CPIR CPDR
                v = self.rd(self.hl)
                r = (self.a - v) & 255
                self.hold(5)
                self.set_bc(self.bc - 1)
                h = (self.a ^ v ^ r) & FH
                f = ((self.f & FC) | FN | (FP if self.bc else 0) | h
                     | (0 if r else FZ) | (r & FS))
                n = (r - 1) & 255 if h else r
                self.f = f | (n & F3) | (F5 if n & 2 else 0)
                if y >= 6 and self.bc and r:
                    self.hold(5)
                    self.pc = (self.pc - 2) & 0xFFFF
                self.set_hl(self.hl + step)
            elif z == 2:                                # INI IND INIR INDR
                self.hold(1)
                v = self.port_in(self.bc)
                self.wr(self.hl, v)
                self.b = (self.b - 1) & 255
                n = (v + ((self.c + step) & 255)) & 255
                self.f = ((FN if v & 0x80 else 0) | (FH | FC if n < v else 0)
                          | (SZP[(n & 7) ^ self.b] & FP) | SZ[self.b])
                if y >= 6 and self.b:
                    self.hold(5)
                    self.pc = (self.pc - 2) & 0xFFFF
                self.set_hl(self.hl + step)
            else:                                       # OUTI OUTD OTIR OTDR
                self.hold(1)
                v = self.rd(self.hl)
                self.b = (self.b - 1) & 255
                self.port_out(self.bc, v)
                self.set_hl(self.hl + step)
                n = (v + self.l) & 255
                self.f = ((FN if v & 0x80 else 0) | (FH | FC if n < v else 0)
                          | (SZP[(n & 7) ^ self.b] & FP) | SZ[self.b])
                if y >= 6 and self.b:
                    self.hold(5)
                    self.pc = (self.pc - 2) & 0xFFFF
        # anything else after ED does nothing (Appendix B)
