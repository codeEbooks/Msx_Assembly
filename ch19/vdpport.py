"""vdpport.py -- the VDP's two ports, as chapter 19 describes them: a model
that knows nothing of openMSX, played with the port operations a program makes.

    port = Port(vram)               vram: a bytearray of 16,384
    port.ctrl(v)                    a byte to $99
    port.data(v)                    a byte to $98
    port.read()                     a byte from $98 (the byte read ahead)
    port.status()                   a byte from $99 (the frame flag, cleared)
    play(port, source_lines, eq)    the port operations of a run of assembly
                                    lines with nothing but LD A, OUT, IN and NOP

The rules, one per port operation:
  $99, first byte    kept; on the TMS99x8 it also goes straight into the low
                     eight bits of the address
  $99, second byte   bit 7 set: the first byte goes to register (byte AND 7),
                     and the address's top six bits take the byte's low six;
                     bit 7 clear: the address is the six bits and the first
                     byte; bit 6 clear (a read): the byte at the address is
                     read ahead into the buffer and the address goes up by one
  $98, write         the byte goes to the buffer and to the VRAM at the
                     address; the address goes up by one; a first byte kept
                     is forgotten
  $98, read          the buffer is the answer; the byte at the address is read
                     into it and the address goes up by one; a first byte kept
                     is forgotten
  $99, read          the status is the answer; the frame flag goes down; a
                     first byte kept is forgotten
Every address is fourteen bits: after $3FFF comes $0000.
"""
import re


class Port:
    def __init__(self, vram=None, regs=None, status=0):
        self.vram = bytearray(16384) if vram is None else bytearray(vram)
        self.regs = list(regs or [0] * 8)
        self.addr = 0
        self.held = None            # the first byte, while the VDP waits for the second
        self.buffer = 0
        self.stat = status
        self.writes = []            # (address, value) of every write to the VRAM

    def ctrl(self, v):
        if self.held is None:
            self.held = v
            self.addr = (self.addr & 0x3F00) | v
            return
        first, self.held = self.held, None
        if v & 0x80:
            self.regs[v & 7] = first
            self.addr = ((v & 0x3F) << 8) | (self.addr & 0xFF)
        else:
            self.addr = ((v & 0x3F) << 8) | first
            if not v & 0x40:
                self.buffer = self.vram[self.addr]
                self.addr = (self.addr + 1) & 0x3FFF

    def data(self, v):
        self.held = None
        self.buffer = v
        self.vram[self.addr] = v
        self.writes.append((self.addr, v))
        self.addr = (self.addr + 1) & 0x3FFF

    def read(self):
        self.held = None
        out = self.buffer
        self.buffer = self.vram[self.addr]
        self.addr = (self.addr + 1) & 0x3FFF
        return out

    def status(self):
        self.held = None
        out = self.stat
        self.stat &= 0x7F
        return out


def value(word, eq):
    """the number an operand of LD A,n stands for"""
    word = word.strip()
    if re.fullmatch(r"'.'", word):
        return ord(word[1])
    if word.startswith("$"):
        return int(word[1:], 16)
    if word.isdigit():
        return int(word)
    return eq[word]


def play(port, lines, eq):
    """the port operations of LINES (source, comments allowed); returns the
    bytes the INs gave, in order"""
    a, got = None, []
    for line in lines:
        code = re.sub(r"^\s*[\w.]+:", "", line.split(";")[0])        # a label
        code = " ".join(code.replace(", ", ",").split()).lower()
        if not code or code == "nop":
            continue
        if code.startswith("ld a,"):
            a = value(re.sub(r"^\s*[\w.]+:", "", line.split(";")[0]).split(",", 1)[1], eq)
        elif code == "out (vdp_ctrl),a":
            port.ctrl(a)
        elif code == "out (vdp_data),a":
            port.data(a)
        elif code == "in a,(vdp_ctrl)":
            a = port.status()
            got.append(a)
        elif code == "in a,(vdp_data)":
            a = port.read()
            got.append(a)
        else:
            raise ValueError(f"not a port operation: {line}")
    return got
