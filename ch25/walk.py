"""walk.py -- a cartridge run as its listing says, without openMSX (chapter 25).

    w = Walk("ch25/fan")                    the .lst, the .sym and the .rom
    w.call("line", b=128, c=96, d=40, e=8)  T-states from the CALL to the
                                            return, and the ports it used
    w.run("init", "done")                   T-states from one label to another

It knows the instructions this book's programs use, from their bytes, and
does what each does to the registers, the flags and the memory; it prices
each the way the chapters do: chapter 14's cycles.msx() for those that do not
jump, and chapters 11, 12 and 13 for the jumps and the block instructions.
The ports do nothing: an OUT is logged with its T-state, and an IN gives
what read_port says, 0 if nothing.
OTIR's OUTs are logged 23 T-states apart, one a turn (chapter 52; up to
chapter 51 they were logged 18 apart, and OTIR's own T-states were right).
Nothing in it comes from openMSX, so the
T-states it finds are the listing's prices, to be held against the
debugger's.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools"))
sys.path.insert(0, str(HERE.parent / "ch14"))
import probe as dbg  # noqa: E402
import cycles        # noqa: E402

R8 = "bcdehl_a"         # the register field of an opcode: 6 is (HL)
CC = ["nz", "z", "nc", "c", "po", "pe", "p", "m"]
SENTINEL = 0xFFFE       # the return address that ends a call


class Walk:
    def __init__(self, stem, read_port=None):
        stem = Path(stem)
        self.sym = dbg.sym(stem.with_suffix(".sym"))
        self.code = {}
        for line in stem.with_suffix(".lst").read_text().splitlines():
            m = dbg.LST.match(line)
            if not m or "..." in m.group(3)[1:13] or not m.group(3)[1:13].strip():
                continue                        # the padding, ALIGN's and ds's
            _, a, c, src = dbg.lst_fields(m)
            if src.split(";")[0].strip().lower().split()[:1] in (["db"], ["dw"]):
                continue
            if a in self.code and self.code[a]:  # a line whose bytes run on
                continue
            self.code[a] = bytes(c)
        self.mem = bytearray(65536)
        rom = stem.with_suffix(".rom").read_bytes()
        self.mem[0x4000:0x4000 + len(rom)] = rom
        self.read_port = read_port or (lambda port, t: 0)
        self.r = dict(a=0, f=0, b=0, c=0, d=0, e=0, h=0, l=0, a_=0, f_=0,
                      b_=0, c_=0, d_=0, e_=0, h_=0, l_=0)
        self.sp, self.pc, self.t = 0xF380, 0, 0
        self.ports = []                         # (T-state, port, value or None)
        self.counts = {}                        # address: times executed

    # ---------------------------------------------------------- registers
    def rr(self, name):
        return self.r[name[0]] << 8 | self.r[name[1]]

    def set_rr(self, name, v):
        self.r[name[0]], self.r[name[1]] = (v >> 8) & 255, v & 255

    def get8(self, i):
        return self.mem[self.rr("hl")] if i == 6 else self.r[R8[i]]

    def set8(self, i, v):
        if i == 6:
            self.poke(self.rr("hl"), v)
        else:
            self.r[R8[i]] = v & 255

    def poke(self, a, v):
        if a >= 0xC000:                         # the cartridge is ROM
            self.mem[a] = v & 255

    def word(self, a):
        return self.mem[a] | self.mem[(a + 1) & 0xFFFF] << 8

    def push(self, v):
        self.sp = (self.sp - 2) & 0xFFFF
        self.poke(self.sp, v & 255)
        self.poke(self.sp + 1, v >> 8)

    def pop(self):
        v = self.word(self.sp)
        self.sp = (self.sp + 2) & 0xFFFF
        return v

    # ---------------------------------------------------------- flags
    def flags(self, v, carry, sub=False, keep_c=False):
        f = (v & 0x80) | (0x40 if v & 255 == 0 else 0) | (0x02 if sub else 0)
        f |= (self.r["f"] & 1) if keep_c else (1 if carry else 0)
        f |= 0x04 if bin(v & 255).count("1") % 2 == 0 else 0     # parity, for the logic
        self.r["f"] = f

    def cond(self, k):
        f = self.r["f"]
        return [not f & 0x40, f & 0x40, not f & 1, f & 1,
                not f & 4, f & 4, not f & 0x80, f & 0x80][k]

    def alu(self, op, v):
        a = self.r["a"]
        if op in (0, 1):                        # ADD, ADC
            s = a + v + (self.r["f"] & 1 if op == 1 else 0)
            self.r["a"] = s & 255
            self.flags(s & 255, s > 255)
        elif op in (2, 3, 7):                   # SUB, SBC, CP
            s = a - v - (self.r["f"] & 1 if op == 3 else 0)
            self.flags(s & 255, s < 0, sub=True)
            if op != 7:
                self.r["a"] = s & 255
        else:                                   # AND, XOR, OR
            self.r["a"] = {4: a & v, 5: a ^ v, 6: a | v}[op]
            self.flags(self.r["a"], False)

    def rot(self, kind, v):
        """the CB rotations and shifts: the value and the carry out"""
        c = self.r["f"] & 1
        if kind == 0:
            out, cy = (v << 1 | v >> 7) & 255, v >> 7          # RLC
        elif kind == 1:
            out, cy = (v >> 1 | (v & 1) << 7), v & 1           # RRC
        elif kind == 2:
            out, cy = (v << 1 | c) & 255, v >> 7               # RL
        elif kind == 3:
            out, cy = (v >> 1 | c << 7), v & 1                 # RR
        elif kind == 4:
            out, cy = (v << 1) & 255, v >> 7                   # SLA
        elif kind == 5:
            out, cy = (v >> 1 | (v & 0x80)), v & 1             # SRA
        elif kind == 7:
            out, cy = v >> 1, v & 1                            # SRL
        else:
            raise ValueError("SLL")
        return out, cy

    # ---------------------------------------------------------- one step
    def step(self):
        pc = self.pc
        code = self.code.get(pc)
        if code is None:
            raise ValueError(f"no instruction at ${pc:04X}")
        self.counts[pc] = self.counts.get(pc, 0) + 1
        op, n = code[0], len(code)
        nxt = (pc + n) & 0xFFFF
        imm = code[-1]
        imm16 = code[-2] | code[-1] << 8 if n >= 3 else 0
        t = None                                # None: cycles.msx(code)
        r = self.r
        if op == 0xCB:
            sub, i = code[1], code[1] & 7
            v = self.get8(i)
            if sub < 0x40:
                out, cy = self.rot(sub >> 3, v)
                self.set8(i, out)
                self.flags(out, cy)
            elif sub < 0x80:                    # BIT
                z = not v & (1 << ((sub >> 3) & 7))
                r["f"] = (r["f"] & 1) | (0x40 if z else 0) | 0x10
            elif sub < 0xC0:
                self.set8(i, v & ~(1 << ((sub >> 3) & 7)))
            else:
                self.set8(i, v | 1 << ((sub >> 3) & 7))
        elif op == 0xED:
            sub = code[1]
            if sub == 0x44:                     # NEG
                v = (-r["a"]) & 255
                self.flags(v, r["a"] != 0, sub=True)
                r["a"] = v
            elif sub in (0xA3, 0xB3):           # OUTI, OTIR
                moved = 0
                while True:
                    self.ports.append((self.t + 23 * moved, r["c"], self.mem[self.rr("hl")]))
                    self.set_rr("hl", self.rr("hl") + 1)
                    r["b"] = (r["b"] - 1) & 255
                    moved += 1
                    if sub == 0xA3 or r["b"] == 0:
                        break
                self.flags(r["b"], r["f"] & 1, sub=True, keep_c=True)
                t = 18 if sub == 0xA3 else 23 * (moved - 1) + 18
            elif sub in (0xA0, 0xB0):           # LDI, LDIR
                moved = 0
                while True:
                    self.poke(self.rr("de"), self.mem[self.rr("hl")])
                    self.set_rr("hl", self.rr("hl") + 1)
                    self.set_rr("de", self.rr("de") + 1)
                    self.set_rr("bc", self.rr("bc") - 1)
                    moved += 1
                    if sub == 0xA0 or self.rr("bc") == 0:
                        break
                t = 18 if sub == 0xA0 else 23 * (moved - 1) + 18
            elif sub & 0xC7 == 0x41:            # OUT (C),r
                self.ports.append((self.t, r["c"], self.get8((sub >> 3) & 7)))
            elif sub & 0xC7 == 0x40:            # IN r,(C)
                v = self.read_port(r["c"], self.t)
                self.ports.append((self.t, r["c"], None))
                self.set8((sub >> 3) & 7, v)
                self.flags(v, r["f"] & 1, keep_c=True)
            else:
                raise ValueError(f"ED {sub:02X} at ${pc:04X}")
        elif 0x40 <= op < 0x80:
            if op == 0x76:
                raise ValueError("HALT")
            self.set8((op >> 3) & 7, self.get8(op & 7))
        elif 0x80 <= op < 0xC0:
            self.alu((op >> 3) & 7, self.get8(op & 7))
        elif op & 0xC7 == 0xC6:
            self.alu((op >> 3) & 7, imm)
        elif op & 0xC7 == 0x06:
            self.set8((op >> 3) & 7, imm)
        elif op & 0xC7 == 0x04:                 # INC r
            v = (self.get8((op >> 3) & 7) + 1) & 255
            self.set8((op >> 3) & 7, v)
            self.flags(v, 0, keep_c=True)
        elif op & 0xC7 == 0x05:                 # DEC r
            v = (self.get8((op >> 3) & 7) - 1) & 255
            self.set8((op >> 3) & 7, v)
            self.flags(v, 0, sub=True, keep_c=True)
        elif op & 0xCF == 0x01:                 # LD rr,nn
            self.set_rp(op >> 4, imm16)
        elif op & 0xCF == 0x03:
            self.set_rp(op >> 4, self.get_rp(op >> 4) + 1)
        elif op & 0xCF == 0x0B:
            self.set_rp(op >> 4, self.get_rp(op >> 4) - 1)
        elif op & 0xCF == 0x09:                 # ADD HL,rr
            s = self.rr("hl") + self.get_rp(op >> 4)
            self.set_rr("hl", s & 0xFFFF)
            r["f"] = (r["f"] & 0xFE) | (s > 0xFFFF)
        elif op & 0xCF == 0xC5:                 # PUSH
            self.push(self.get_pp((op >> 4) & 3))
        elif op & 0xCF == 0xC1:                 # POP
            self.set_pp((op >> 4) & 3, self.pop())
        elif op in (0x0A, 0x1A):
            r["a"] = self.mem[self.rr("bc" if op == 0x0A else "de")]
        elif op in (0x02, 0x12):
            self.poke(self.rr("bc" if op == 0x02 else "de"), r["a"])
        elif op == 0x3A:
            r["a"] = self.mem[imm16]
        elif op == 0x32:
            self.poke(imm16, r["a"])
        elif op == 0x2A:
            self.set_rr("hl", self.word(imm16))
        elif op == 0x22:
            self.poke(imm16, r["l"])
            self.poke(imm16 + 1, r["h"])
        elif op in (0x07, 0x0F, 0x17, 0x1F):
            out, cy = self.rot({0x07: 0, 0x0F: 1, 0x17: 2, 0x1F: 3}[op], r["a"])
            r["a"] = out
            r["f"] = (r["f"] & 0xFE) | cy
        elif op == 0x08:                        # EX AF,AF'
            r["a"], r["a_"], r["f"], r["f_"] = r["a_"], r["a"], r["f_"], r["f"]
        elif op == 0xD9:                        # EXX
            for x in "bcdehl":
                r[x], r[x + "_"] = r[x + "_"], r[x]
        elif op == 0xEB:
            r["d"], r["e"], r["h"], r["l"] = r["h"], r["l"], r["d"], r["e"]
        elif op == 0x2F:
            r["a"] ^= 255
        elif op == 0x37:
            r["f"] |= 1
        elif op == 0x3F:
            r["f"] ^= 1
        elif op in (0x00, 0xF3, 0xFB):          # NOP, DI, EI
            pass
        elif op == 0xD3:                        # OUT (n),A
            self.ports.append((self.t, imm, r["a"]))
        elif op == 0xDB:                        # IN A,(n)
            r["a"] = self.read_port(imm, self.t)
            self.ports.append((self.t, imm, None))
        elif op == 0x10:                        # DJNZ
            r["b"] = (r["b"] - 1) & 255
            if r["b"]:
                nxt, t = (nxt + (imm ^ 0x80) - 0x80) & 0xFFFF, 14
            else:
                t = 9
        elif op == 0x18 or op & 0xE7 == 0x20:   # JR, JR cc
            if op == 0x18 or self.cond((op >> 3) & 3):
                nxt, t = (nxt + (imm ^ 0x80) - 0x80) & 0xFFFF, 13
            else:
                t = 8
        elif op == 0xC3 or op & 0xC7 == 0xC2:   # JP, JP cc
            if op == 0xC3 or self.cond((op >> 3) & 7):
                nxt = imm16
            t = 11
        elif op == 0xCD or op & 0xC7 == 0xC4:   # CALL, CALL cc
            if op == 0xCD or self.cond((op >> 3) & 7):
                self.push(nxt)
                nxt, t = imm16, 18
            else:
                t = 11
        elif op == 0xC9:
            nxt, t = self.pop(), 11
        elif op & 0xC7 == 0xC0:                 # RET cc
            if self.cond((op >> 3) & 7):
                nxt, t = self.pop(), 12
            else:
                t = 6
        else:
            raise ValueError(f"{op:02X} at ${pc:04X}")
        self.t += cycles.msx(list(code)) if t is None else t
        self.pc = nxt

    RP = ["bc", "de", "hl", "sp"]

    def get_rp(self, k):
        return self.sp if k == 3 else self.rr(self.RP[k])

    def set_rp(self, k, v):
        if k == 3:
            self.sp = v & 0xFFFF
        else:
            self.set_rr(self.RP[k], v & 0xFFFF)

    def get_pp(self, k):
        return self.r["a"] << 8 | self.r["f"] if k == 3 else self.rr(self.RP[k])

    def set_pp(self, k, v):
        if k == 3:
            self.r["a"], self.r["f"] = v >> 8, v & 255
        else:
            self.set_rr(self.RP[k], v)

    # ---------------------------------------------------------- runs
    def call(self, label, **regs):
        """T-states of CALL label (its 18 included) up to the return"""
        for k, v in regs.items():
            self.r[k] = v
        t0 = self.t
        self.push(SENTINEL)
        self.t += 18
        self.pc = self.sym[label]
        while self.pc != SENTINEL:
            self.step()
        return self.t - t0

    def lap(self, label, **regs):
        """T-states of one pass of a loop: from LABEL until it comes back"""
        for k, v in regs.items():
            self.r[k] = v
        self.pc, t0 = self.sym[label], self.t
        self.step()
        while self.pc != self.sym[label]:
            self.step()
        return self.t - t0

    def run(self, start, stop, limit=10 ** 8):
        """T-states from label START to label STOP"""
        self.pc, t0 = self.sym[start], self.t
        while self.pc != self.sym[stop]:
            self.step()
            if self.t - t0 > limit:
                raise RuntimeError("too long")
        return self.t - t0
