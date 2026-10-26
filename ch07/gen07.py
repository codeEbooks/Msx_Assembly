#!/usr/bin/env python3
"""gen07.py - the programs of chapter 7.

    python3 gen07.py && ./build.sh

Cartridges, run and read by meas07.py. They keep what they find in the RAM
from $C000 (RESULTS), because the cartridge itself is ROM; the debugger reads
it there.

    regs.asm      a value in every register a program can load, then a stop:
                  the console's cpuregs at the stop is listing 7.1
    cost.asm      A loaded from a register, from memory through HL, from RAM
                  and ROM by address, and stored back: one instruction each,
                  timed by the debugger
    rcount.asm    R set with LD R,A and read eight times in a loop of five
                  opcode fetches, from $7E and from $FE
    pairs.asm     INC HL and INC L on $00FF, with HL and F after each
    flags.asm     eleven instructions, each started with every flag clear:
                  A before, the instruction, A after, and F as eight boxes,
                  printed on the screen (figure 7.1)
    flagtest.asm  eighteen instructions, each run with every flag clear and
                  with every flag set: the flags each one sets
    cond.asm      JP with each of the eight conditions, on two values of F
    ixh.asm       LD A,IXH and LD B,IXL, which Zilog's manual does not list
    shapes.asm    one instruction of each shape, timed by the debugger: its
                  disassembly is listing 7.3
    loop.asm      WHERE IT BREAKS: a count of three that tests the wrong flag
                  and never ends (listing 7.2)
    loop_ok.asm   the same count, testing BC itself

Listings, assembled and not run: the assembler's bytes are the result.

    grid.asm      LD r,r' for all 64 pairs of registers
    families.asm  every instruction built from a register or a pair number,
                  and every conditional jump, call and return
    index.asm     instructions that use HL, with their IX and IY forms
    fake.asm      WHERE IT BREAKS: two instructions the Z80 does not have,
                  which sjasmplus takes

The routines of flags.asm come from tools/asmparts.py. Every number the
programs print or keep is worked out by the Z80 when it runs, not by this
generator: the generator only writes the questions.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
from asmparts import HEAD, TAIL, TEXT_PAGE, SHOW_PAGE, library, FATBITS  # noqa: E402

RESULTS = "RESULTS EQU RAM_START          ; what the program found: the debugger reads it here\n"


def head(name, what):
    return HEAD.format(name=name, chapter=7, what=what)


def cart(name, what, body):
    """a cartridge that runs `body` with the interrupts off and stops"""
    return head(name, what) + RESULTS + f"""init:   di
        ld sp, SYS_AREA
{body}stop:   jr stop
""" + TAIL


def listing_only(name, what, body):
    return f"""; {name}.asm - chapter 7: {what}
; Not a program: assemble it with --lst and read the listing.
        OUTPUT "{name}.bin"
        ORG $4000
{body}"""


# ---------------------------------------------------------------- regs
# (register, value) in the order the program loads them; EXX comes after HL
REGS_FIRST = [("bc", 0x1111), ("de", 0x2222), ("hl", 0x3333)]
REGS_SECOND = [("bc", 0x1234), ("de", 0x5678), ("hl", 0x9ABC), ("ix", 0xC000), ("iy", 0xC010)]
REGS_A, REGS_A2 = 0xAA, 0x55


def regs():
    first = "".join(f"        ld {r}, ${v:04X}\n" for r, v in REGS_FIRST)
    second = "".join(f"        ld {r}, ${v:04X}\n" for r, v in REGS_SECOND)
    body = f"""        xor a
        ld r, a                 ; R = 0: from here it counts
        ld a, ${REGS_A:02X}
        ex af, af'              ; A and F go to the second set
{first}        exx                     ; the second BC, DE and HL come in
{second}        ld a, ${REGS_A2:02X}
"""
    # the stop is the program's last instruction; the debugger reads it there
    return cart("regs", "a value in every register", body)


# ---------------------------------------------------------------- cost
COST = [("ld a, b", "a register"), ("ld a, (hl)", "memory, HL"),
        ("ld a, (RAM_START)", "RAM, by address"), ("ld a, ($4000)", "ROM, by address"),
        ("ld (hl), a", "memory, HL"), ("ld (RAM_START), a", "RAM, by address")]


def timed(instrs):
    """t0: ... tN: a label before every instruction and one after the last"""
    out = ""
    for i, ins in enumerate(instrs):
        out += f"t{i}:\n        {ins}\n"
    return out + f"t{len(instrs)}:\n"


def cost():
    body = """        ld hl, RAM_START
        ld b, $42
""" + timed([i for i, _ in COST])
    return cart("cost", "a byte from a register and from memory", body)


# ---------------------------------------------------------------- rcount
R_STARTS = [0x7E, 0xFE]
R_READS = 8


def rcount():
    body = ""
    for k, r0 in enumerate(R_STARTS):
        body += f"""        ld a, ${r0:02X}
        ld r, a                 ; R = ${r0:02X}
        ld hl, RESULTS + {R_READS * k}
        ld b, {R_READS}
read{k}:  ld a, r                  ; 2 opcode fetches (ED 5F)
        ld (hl), a              ; 1
        inc hl                  ; 1
        djnz read{k}             ; 1: five a turn
"""
    return cart("rcount", "R counts opcode fetches", body)


# ---------------------------------------------------------------- pairs
PAIRS_VALUE = 0x00FF
PAIRS = ["inc hl", "inc l"]


def pairs():
    body = ""
    for k, ins in enumerate(PAIRS):
        body += f"""        ld hl, ${PAIRS_VALUE:04X}
        ld de, 0
        push de
        pop af                  ; A = 0 and F = 0: every flag clear
        {ins}
        push af
        ld (RESULTS + {3 * k}), hl      ; HL afterwards
        pop de
        ld a, e
        ld (RESULTS + {3 * k + 2}), a   ; and F
"""
    return cart("pairs", "sixteen bits from two registers", body)


# ---------------------------------------------------------------- flags
# (A before, the instruction): the screen shows the instruction as written
FLAGS = [(0x7F, "add a,1"), (0xFF, "add a,1"), (0x80, "add a,$80"), (0x00, "sub 1"),
         (0x05, "cp 5"), (0x0F, "inc a"), (0x80, "dec a"), (0xF0, "and $0F"),
         (0x02, "or 1"), (0x55, "xor a"), (0x28, "add a,0")]
FLAG_ROW0, FLAG_STEP = 3, 2
FLAG_COLS = {"before": 0, "text": 4, "after": 17, "bits": 21, "F": 30}
FLAG_HEADS = {"before": "A", "text": "instruction", "after": "A", "bits": "SZ5H3VNC", "F": "F"}


def shown(ins):
    """the instruction as the screen prints it"""
    return ins.upper()


def flags():
    heads = "".join(f"""        ld c, {FLAG_COLS[k]}
        ld hl, h_{k}
        call puts
""" for k in FLAG_COLS)
    rows = []
    for i, (before, ins) in enumerate(FLAGS):
        rows.append(f"""; {shown(ins)} on ${before:02X}
        ld b, {FLAG_ROW0 + FLAG_STEP * i}
        ld a, ${before:02X}
        ld hl, i{i}
        call before
        ld de, ${before:02X}00
        push de
        pop af                  ; A = ${before:02X}, every flag clear
        {ins}
        call after
""")
    texts = "".join(f'i{i}:     db "{shown(ins)}", 0\n' for i, (_, ins) in enumerate(FLAGS))
    hs = "".join(f'h_{k}:  db "{v}", 0\n' for k, v in FLAG_HEADS.items())
    return head("flags", "what each instruction leaves in F") + RESULTS + TEXT_PAGE + f"""        ld ix, RESULTS          ; A and F after each, kept for the debugger
        ld b, {FLAG_ROW0 - 2}
{heads}""" + "".join(rows) + SHOW_PAGE + f"""
; before: A = A before, HL = the instruction's text, B = the row
before: ld c, {FLAG_COLS['before']}
        call puthex
        ld c, {FLAG_COLS['text']}
        jp puts

; after: prints A and F as the instruction left them, and keeps them
after:  push af
        pop de                  ; D = A, E = F
        ld (ix+0), d
        ld (ix+1), e
        inc ix
        inc ix
        ld c, {FLAG_COLS['after']}
        ld a, d
        call puthex
        ld c, {FLAG_COLS['bits']}
        ld a, e
        call fatbits            ; bit 7 on the left
        ld c, {FLAG_COLS['F']}
        ld a, e
        jp puthex

{hs}{texts}""" + library(FATBITS) + TAIL


# ---------------------------------------------------------------- flagtest
# (instruction, the registers it works on, set before it)
FLAGTEST = [("ld a, b", "ld b, $01"), ("add a, b", "ld b, $01"), ("sub b", "ld b, $01"),
            ("cp b", "ld b, $01"), ("inc a", ""), ("dec a", ""), ("and b", "ld b, $0F"),
            ("or b", "ld b, $0F"), ("xor b", "ld b, $0F"), ("rlca", ""), ("cpl", ""),
            ("neg", ""), ("scf", ""), ("inc hl", "ld hl, $FFFF"), ("dec bc", "ld bc, $0001"),
            ("add hl, de", "ld hl, $FFFF\n        ld de, $0001"), ("out (PSG_ADDR), a", ""),
            ("jr $+2", "")]
FLAGTEST_A = 0xFF
FLAGTEST_F = [0x00, 0xFF]


def flagtest():
    body = ""
    for i, (ins, setup) in enumerate(FLAGTEST):
        for k, f in enumerate(FLAGTEST_F):
            at = 2 * (2 * i + k)
            body += f"""; {ins}, with every flag {"clear" if f == 0 else "set"}
{"        " + setup + chr(10) if setup else ""}        ld iy, ${FLAGTEST_A:02X}{f:02X}
        push iy
        pop af                  ; A = ${FLAGTEST_A:02X}, F = ${f:02X}
        {ins}
        push af
        pop iy
        ld (RESULTS + {at}), iy         ; F, then A
"""
    return cart("flagtest", "which flags each instruction sets", body)


# ---------------------------------------------------------------- cond
CONDS = ["nz", "z", "nc", "c", "po", "pe", "p", "m"]
COND_F = [0x94, 0x51]           # two values of F from figure 7.1


def cond():
    body = ""
    for k, f in enumerate(COND_F):
        for c, name in enumerate(CONDS):
            at, lab = 8 * k + c, f"j{k}{c}"
            body += f"""        ld iy, ${f:04X}
        push iy
        pop af                  ; A = 0, F = ${f:02X}
        jp {name}, {lab}
        jr {lab}s                ; not taken: 0
{lab}:    ld a, 1                 ; taken: 1
{lab}s:   ld (RESULTS + {at}), a
"""
    return cart("cond", "JP with each condition", body)


# ---------------------------------------------------------------- ixh
IXH_IX, IXH_HL = 0x9ABC, 0x1234


def ixh():
    body = f"""        ld ix, ${IXH_IX:04X}
        ld hl, ${IXH_HL:04X}
        ld a, ixh               ; DD 7C: LD A,H with the IX prefix
        ld b, ixl               ; DD 45: LD B,L with the IX prefix
"""
    return cart("ixh", "the halves of IX", body)


# ---------------------------------------------------------------- shapes
SHAPES = ["nop", "ld a, $55", "ld hl, $1234", "ld a, (RAM_START)", "rlc b", "neg",
          "ld bc, (RAM_START)", "ld ix, RAM_START", "ld a, (ix+5)", "ld (ix+5), $AA",
          "set 1, (ix+2)"]


def shapes():
    return cart("shapes", "one instruction of each shape", timed(SHAPES))


# ---------------------------------------------------------------- loop
LOOP_COUNT = 3


def loop(ok):
    test = """        ld a, b
        or c                    ; Z = 1 only when B and C are both 0
""" if ok else ""
    what = ("the count of three, testing BC itself" if ok else
            "WHERE IT BREAKS: the count that never ends")
    body = f"""        ld a, 1
        or a                    ; Z = 0: A is not 0
        ld bc, {LOOP_COUNT}                ; three turns
count:  dec bc                  ; BC - 1{"" if ok else ", and no flag changes"}
{test}        jr nz, count            ; {"round again while BC is not 0" if ok else "Z is still OR A's: round again"}
done:   jr done                 ; {"after three turns" if ok else "never reached"}
"""
    return head("loop_ok" if ok else "loop", what) + f"""init:   di
        ld sp, SYS_AREA
{body}""" + TAIL


# ---------------------------------------------------------------- the listings
RN = ["b", "c", "d", "e", "h", "l", "(hl)", "a"]
PN = ["bc", "de", "hl", "sp"]
QN = ["bc", "de", "hl", "af"]
ALU = ["add a,", "adc a,", "sub", "sbc a,", "and", "xor", "or", "cp"]
ROT = ["rlc", "rrc", "rl", "rr", "sla", "sra", None, "srl"]     # 110: SLL, appendix B


def grid():
    lines = []
    for d, dn in enumerate(RN):
        for s, sn in enumerate(RN):
            lines.append("        halt                    ; not ld (hl),(hl)" if d == s == 6
                         else f"        ld {dn},{sn}")
    return listing_only("grid", "LD r,r' for every pair", "\n".join(lines) + "\n")


def families():
    """(family, the lines) in the order meas07.py checks them"""
    fam = []
    fam.append(("ld r,n", [f"ld {r},$12" for r in RN]))
    fam.append(("inc r", [f"inc {r}" for r in RN]))
    fam.append(("dec r", [f"dec {r}" for r in RN]))
    fam.append(("alu r", [op + r if op.endswith(",") else f"{op} {r}" for op in ALU for r in RN]))
    fam.append(("rot r", [f"{op} {r}" for op in ROT if op for r in RN]))
    for name in ("bit", "res", "set"):
        fam.append((name, [f"{name} {b},{r}" for b in range(8) for r in RN]))
    fam.append(("ld rr,nn", [f"ld {p},$1234" for p in PN]))
    fam.append(("inc rr", [f"inc {p}" for p in PN]))
    fam.append(("dec rr", [f"dec {p}" for p in PN]))
    fam.append(("add hl,rr", [f"add hl,{p}" for p in PN]))
    fam.append(("push qq", [f"push {q}" for q in QN]))
    fam.append(("pop qq", [f"pop {q}" for q in QN]))
    fam.append(("sbc hl,rr", [f"sbc hl,{p}" for p in PN]))
    fam.append(("adc hl,rr", [f"adc hl,{p}" for p in PN]))
    fam.append(("jp cc,nn", [f"jp {c},$1234" for c in CONDS]))
    fam.append(("call cc,nn", [f"call {c},$1234" for c in CONDS]))
    fam.append(("ret cc", [f"ret {c}" for c in CONDS]))
    fam.append(("jr cc,e", [f"jr {c},$+2" for c in CONDS[:4]]))
    return fam


def families_asm():
    body = ""
    for name, lines in families():
        body += f"; {name}\n" + "".join(f"        {l}\n" for l in lines)
    return listing_only("families", "the opcodes built from patterns", body)


# (the HL form, the IX form); the IY form is the IX form with iy for ix
INDEX = [("ld hl,$1234", "ld ix,$1234"), ("ld hl,($C000)", "ld ix,($C000)"),
         ("inc hl", "inc ix"), ("add hl,de", "add ix,de"), ("push hl", "push ix"),
         ("ld sp,hl", "ld sp,ix"), ("ex (sp),hl", "ex (sp),ix"), ("jp (hl)", "jp (ix)"),
         ("ld a,(hl)", "ld a,(ix+5)"), ("ld (hl),b", "ld (ix+5),b"),
         ("ld (hl),$AA", "ld (ix+5),$AA"), ("inc (hl)", "inc (ix+5)"),
         ("add a,(hl)", "add a,(ix+5)"), ("bit 3,(hl)", "bit 3,(ix+5)"),
         ("set 1,(hl)", "set 1,(ix+5)")]


def index():
    body = ""
    for hl, ix in INDEX:
        body += f"        {hl}\n        {ix}\n        {ix.replace('ix', 'iy')}\n"
    return listing_only("index", "HL, IX and IY", body)


def fake():
    return listing_only("fake", "two instructions the Z80 does not have", """        ld bc,de                ; sjasmplus takes it
        ld hl,(ix+1)            ; and this
""")


def sources():
    return {"regs.asm": regs(), "cost.asm": cost(), "rcount.asm": rcount(),
            "pairs.asm": pairs(), "flags.asm": flags(), "flagtest.asm": flagtest(),
            "cond.asm": cond(), "ixh.asm": ixh(), "shapes.asm": shapes(),
            "loop.asm": loop(False), "loop_ok.asm": loop(True), "grid.asm": grid(),
            "families.asm": families_asm(), "index.asm": index(), "fake.asm": fake()}


CARTS = ["regs", "cost", "rcount", "pairs", "flags", "flagtest", "cond", "ixh", "shapes",
         "loop", "loop_ok"]
LISTINGS = ["grid", "families", "index", "fake"]


def main():
    files = sources()
    for name, text in files.items():
        with open(os.path.join(HERE, name), "w") as f:
            f.write(text)
    print(len(files), "sources written")


if __name__ == "__main__":
    main()
