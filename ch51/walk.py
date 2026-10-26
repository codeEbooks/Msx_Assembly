"""walk.py -- a cartridge run as its listing says, without openMSX (chapter 25,
with IX added in chapter 28, DAA in chapter 30 and JP (IX) in chapter 31).

    w = Walk("ch25/fan")                    the .lst, the .sym and the .rom
    w.call("line", b=128, c=96, d=40, e=8)  T-states from the CALL to the
                                            return, and the ports it used
    w.run("init", "done")                   T-states from one label to another

It knows the instructions this book's programs use, from their bytes, and
does what each does to the registers, the flags and the memory; it prices
each the way the chapters do: chapter 14's cycles.msx() for those that do not
jump, and chapters 11, 12 and 13 for the jumps and the block instructions.
The ports do nothing: an OUT is logged with its T-state, and an IN gives
what read_port says, 0 if nothing. Chapter 28 added the IX instructions its
programs use: LD IX,nn, ADD IX,rr, PUSH and POP IX, INC and DEC IX, and the
(IX+d) forms of LD, the arithmetic and logic, INC, DEC, and the CB group.
Chapter 30 added DAA, and with it the half carry that ADD, ADC, SUB, SBC and
CP leave for it, and SBC HL,rr and ADC HL,rr. Chapter 31 added JP (IX).
Chapter 32 added LD rr,(nn) and LD (nn),rr, the ED forms, and LD I,A and IM
0, 1 and 2, which only set I and the mode. Chapter 41 added R, which goes
up by one at every opcode fetch, a prefix's too (chapter 14), its top bit
kept, with LD A,R and LD R,A; and JP (HL). Chapter 47 added LD SP,HL.
Chapter 48 added the cartridges larger than 32 KB, MegaROMs: Walk(stem,
mapper="ascii16") or "konamiscc" puts in pages 1 and 2 the 8 KB blocks the
mapper says, and a write to one of the mapper's registers changes them; the
listing's instructions are kept bank by bank, a bank for each OUTPUT of the
source, and an instruction in pages 1 and 2 is the one of the bank there.
Chapter 51 put OTIR's OUTs at their times: one at the start of each turn
of 23 T-states (from chapter 25 on they were logged 18 apart; the
instruction's T-states were right). Nothing in it comes from openMSX, so the
T-states it finds are the listing's prices, to be held against the debugger's.
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


class Mapper:
    """a MegaROM's mapper (chapter 48): the 8 KB block each window of pages 1
    and 2 shows. ASCII16: a 16 KB bank for page 1 written at $6000-$67FF and
    one for page 2 at $7000-$77FF, both bank 0 at the start. Konami SCC: a
    block for each window, written at $5000, $7000, $9000 and $B000, 2 KB
    each, blocks 0 to 3 at the start"""
    def __init__(self, kind, blocks):
        self.kind, self.count = kind, blocks
        self.blocks = [0, 1, 0, 1] if kind == "ascii16" else [0, 1, 2, 3]

    def write(self, a, v):
        if self.kind == "ascii16":
            for page, base in ((0, 0x6000), (2, 0x7000)):
                if base <= a < base + 0x800:
                    b = v % (self.count // 2)
                    self.blocks[page:page + 2] = [2 * b, 2 * b + 1]
        else:
            for w, base in enumerate((0x5000, 0x7000, 0x9000, 0xB000)):
                if base <= a < base + 0x800:
                    self.blocks[w] = v % self.count


class Walk:
    def __init__(self, stem, read_port=None, mapper=None):
        stem = Path(stem)
        self.sym = dbg.sym(stem.with_suffix(".sym"))
        self.codes = [{}]                       # each OUTPUT's instructions: a bank's
        outputs = 0
        for line in stem.with_suffix(".lst").read_text().splitlines():
            m = dbg.LST.match(line)
            if m and m.group(3)[13:].split(";")[0].strip().upper().startswith("OUTPUT"):
                outputs += 1
                if outputs > 1:
                    self.codes.append({})
                continue
            if not m or "..." in m.group(3)[1:13] or not m.group(3)[1:13].strip():
                continue                        # the padding, ALIGN's and ds's
            _, a, c, src = dbg.lst_fields(m)
            if src.split(";")[0].strip().lower().split()[:1] in (["db"], ["dw"]):
                continue
            code = self.codes[-1]
            if a in code and code[a]:           # a line whose bytes run on
                continue
            code[a] = bytes(c)
        self.code = self.codes[0]
        self.mem = bytearray(65536)
        rom = stem.with_suffix(".rom").read_bytes()
        self.rom = rom
        self.mapper = None
        if mapper:
            assert len(rom) % 0x4000 == 0 and len(self.codes) == len(rom) // 0x4000
            self.mapper = Mapper(mapper, len(rom) // 0x2000)
            self.remap()
        else:
            assert len(rom) <= 0x8000 and len(self.codes) == 1
            self.mem[0x4000:0x4000 + len(rom)] = rom
        self.read_port = read_port or (lambda port, t: 0)
        self.r = dict(a=0, f=0, b=0, c=0, d=0, e=0, h=0, l=0, a_=0, f_=0,
                      b_=0, c_=0, d_=0, e_=0, h_=0, l_=0)
        self.sp, self.pc, self.t = 0xF380, 0, 0
        self.ix = 0
        self.i, self.im = 0, 0
        self.rreg = 0                           # R (chapter 41)
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
        elif self.mapper and 0x4000 <= a < 0xC000:
            self.mapper.write(a, v & 255)       # but its mapper listens
            self.remap()

    def remap(self):
        """pages 1 and 2: the blocks the mapper says"""
        for w, blk in enumerate(self.mapper.blocks):
            self.mem[0x4000 + 0x2000 * w:0x6000 + 0x2000 * w] = self.rom[0x2000 * blk:0x2000 * blk + 0x2000]

    def set_blocks(self, blocks):
        """the mapper as the debugger found it: the 8 KB block of each window"""
        self.mapper.blocks = list(blocks)
        self.remap()

    def code_at(self, pc):
        """the listing's instruction at PC: in pages 1 and 2 of a MegaROM, the
        one of the bank the mapper put there, assembled at $4000 for bank 0
        and at $8000 for the others"""
        if not self.mapper or not 0x4000 <= pc < 0xC000:
            return self.code.get(pc)
        blk = self.mapper.blocks[(pc - 0x4000) >> 13]
        bank = blk // 2
        at = (0x4000 if bank == 0 else 0x8000) + 0x2000 * (blk % 2) + (pc & 0x1FFF)
        return self.codes[bank].get(at)

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
    def flags(self, v, carry, sub=False, keep_c=False, half=False):
        f = (v & 0x80) | (0x40 if v & 255 == 0 else 0) | (0x02 if sub else 0) | (0x10 if half else 0)
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
            c = self.r["f"] & 1 if op == 1 else 0
            s = a + v + c
            self.r["a"] = s & 255
            self.flags(s & 255, s > 255, half=(a & 15) + (v & 15) + c > 15)
        elif op in (2, 3, 7):                   # SUB, SBC, CP
            c = self.r["f"] & 1 if op == 3 else 0
            s = a - v - c
            self.flags(s & 255, s < 0, sub=True, half=(a & 15) - (v & 15) - c < 0)
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

    def refresh(self, fetches):
        """R: one more for each opcode fetch, in its low seven bits"""
        self.rreg = (self.rreg & 0x80) | ((self.rreg + fetches) & 0x7F)

    # ---------------------------------------------------------- one step
    def step(self):
        pc = self.pc
        code = self.code_at(pc)
        if code is None:
            raise ValueError(f"no instruction at ${pc:04X}")
        self.counts[pc] = self.counts.get(pc, 0) + 1
        op, n = code[0], len(code)
        nxt = (pc + n) & 0xFFFF
        imm = code[-1]
        imm16 = code[-2] | code[-1] << 8 if n >= 3 else 0
        t = None                                # None: cycles.msx(code)
        r = self.r
        self.refresh(2 if op in (0xCB, 0xED, 0xDD, 0xFD) else 1)
        if op == 0xDD and code[1] == 0xE9:       # JP (IX) (chapter 31): Zilog's 8, two M1s
            nxt, t = self.ix, 10
        elif op == 0xDD:
            self.ix_step(code)
        elif op == 0xCB:
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
                self.refresh(2 * (moved - 1))   # each repeat fetches ED B3 again
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
                self.refresh(2 * (moved - 1))   # each repeat fetches ED B0 again
            elif sub & 0xC7 == 0x42:            # SBC HL,rr and ADC HL,rr (chapter 30)
                hl, v, c = self.rr("hl"), self.get_rp((sub >> 4) & 3), r["f"] & 1
                if sub & 8:
                    res = hl + v + c
                    carry, half = res > 0xFFFF, (hl & 0xFFF) + (v & 0xFFF) + c > 0xFFF
                    over = not (hl ^ v) & 0x8000 and (hl ^ res) & 0x8000
                else:
                    res = hl - v - c
                    carry, half = res < 0, (hl & 0xFFF) - (v & 0xFFF) - c < 0
                    over = (hl ^ v) & 0x8000 and (hl ^ res) & 0x8000
                res &= 0xFFFF
                self.set_rr("hl", res)
                r["f"] = ((res >> 8) & 0x80) | (0x40 if res == 0 else 0) | (0x10 if half else 0) | \
                    (0x04 if over else 0) | (0 if sub & 8 else 0x02) | (1 if carry else 0)
            elif sub & 0xCF == 0x4B:            # LD rr,(nn) (chapter 32)
                self.set_rp((sub >> 4) & 3, self.word(imm16))
            elif sub & 0xCF == 0x43:            # LD (nn),rr (chapter 32)
                v = self.get_rp((sub >> 4) & 3)
                self.poke(imm16, v & 255)
                self.poke((imm16 + 1) & 0xFFFF, v >> 8)
            elif sub == 0x47:                   # LD I,A (chapter 32)
                self.i = r["a"]
            elif sub == 0x5F:                   # LD A,R (chapter 41): R after its two fetches
                r["a"] = self.rreg
                r["f"] = (r["f"] & 1) | (self.rreg & 0x80) | (0x40 if self.rreg == 0 else 0)
            elif sub == 0x4F:                   # LD R,A (chapter 41)
                self.rreg = r["a"]
            elif sub in (0x46, 0x56, 0x5E):     # IM 0, 1, 2 (chapter 32)
                self.im = {0x46: 0, 0x56: 1, 0x5E: 2}[sub]
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
        elif op == 0x27:                        # DAA (chapter 30)
            a, f = r["a"], r["f"]
            fix, cy = 0, f & 1
            if f & 0x10 or a & 15 > 9:
                fix |= 0x06
            if cy or a > 0x99:
                fix, cy = fix | 0x60, 1
            v = (a - fix if f & 2 else a + fix) & 255
            half = (a & 15) < (fix & 15) if f & 2 else (a & 15) + (fix & 15) > 15
            r["a"] = v
            self.flags(v, cy, sub=bool(f & 2), half=half)
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
        elif op == 0xE9:                        # JP (HL) (chapter 41)
            nxt, t = self.rr("hl"), 5
        elif op == 0xF9:                        # LD SP,HL (chapter 47)
            self.sp = self.rr("hl")
        elif op & 0xC7 == 0xC0:                 # RET cc
            if self.cond((op >> 3) & 7):
                nxt, t = self.pop(), 12
            else:
                t = 6
        else:
            raise ValueError(f"{op:02X} at ${pc:04X}")
        self.t += cycles.msx(list(code)) if t is None else t
        self.pc = nxt

    def ix_step(self, code):
        """the DD instructions: IX as a pair, and (IX+d) as a byte of memory"""
        sub, r = code[1], self.r
        d = (code[2] ^ 0x80) - 0x80 if len(code) > 2 else 0
        at = (self.ix + d) & 0xFFFF
        if sub == 0x21:                         # LD IX,nn
            self.ix = code[2] | code[3] << 8
        elif sub & 0xCF == 0x09:                # ADD IX,rr
            k = sub >> 4
            v = self.ix if k == 2 else self.get_rp(k)
            s = self.ix + v
            self.ix = s & 0xFFFF
            r["f"] = (r["f"] & 0xFE) | (s > 0xFFFF)
        elif sub == 0xE5:
            self.push(self.ix)
        elif sub == 0xE1:
            self.ix = self.pop()
        elif sub == 0x23:
            self.ix = (self.ix + 1) & 0xFFFF
        elif sub == 0x2B:
            self.ix = (self.ix - 1) & 0xFFFF
        elif sub == 0x36:                       # LD (IX+d),n
            self.poke(at, code[3])
        elif 0x40 <= sub < 0x80 and sub & 7 == 6 and sub != 0x76:   # LD r,(IX+d)
            r[R8[(sub >> 3) & 7]] = self.mem[at]
        elif 0x70 <= sub < 0x78 and sub != 0x76:                     # LD (IX+d),r
            self.poke(at, r[R8[sub & 7]])
        elif 0x80 <= sub < 0xC0 and sub & 7 == 6:                    # ALU A,(IX+d)
            self.alu((sub >> 3) & 7, self.mem[at])
        elif sub in (0x34, 0x35):               # INC, DEC (IX+d)
            v = (self.mem[at] + (1 if sub == 0x34 else -1)) & 255
            self.poke(at, v)
            self.flags(v, 0, sub=sub == 0x35, keep_c=True)
        elif sub == 0xCB:                       # the CB group on (IX+d)
            hl = self.rr("hl")
            self.set_rr("hl", at)
            cb = code[3]
            v = self.get8(6)
            if cb < 0x40:
                out, cy = self.rot(cb >> 3, v)
                self.set8(6, out)
                self.flags(out, cy)
            elif cb < 0x80:
                z = not v & (1 << ((cb >> 3) & 7))
                r["f"] = (r["f"] & 1) | (0x40 if z else 0) | 0x10
            elif cb < 0xC0:
                self.set8(6, v & ~(1 << ((cb >> 3) & 7)))
            else:
                self.set8(6, v | 1 << ((cb >> 3) & 7))
            self.set_rr("hl", hl)
        else:
            raise ValueError(f"DD {sub:02X}")

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
