"""iset.py - the Z80's documented instructions, as Appendix A lists them.

    rows()      the 698 instructions of Zilog's manual, family by family,
                each a dict:
        family  the table it goes in (FAMILIES)
        form    the instruction as the manual writes it, with letters for
                what changes ("LD r,r'"): r and r' a register, B C D E H L
                A; n a byte, nn two; d a distance, e a jump's; cc a
                condition; b a bit; p an RST's address; dd and ss the pairs
                BC DE HL SP; qq BC DE HL AF; pp BC DE IX SP; rr BC DE IY SP
        text    the instruction itself ("LD B,C", "JR NZ,e")
        asm     the line sjasmplus assembles, with {n}, {nn}, {d}, {t} for
                the numbers and the target that the program gives it
        show    the bytes as the table prints them ("DD 36 d n")
        key     the bytes that say which instruction it is: the prefixes
                and the opcode, without the numbers ((0xDD, 0x36))
        kind    "plain", or what else it is: "jump" (always jumps),
                "cond" (jumps if cc holds), "block" (LDI ...), "repeat"
                (LDIR ...), "halt"
        cc      the condition of a "cond" row (NZ, Z, NC, C, PO, PE, P, M)
        n       its number in the appendix, 1 to 698, in table order: by
                family, and in a family by form, the registers in the
                order of their bits, B C D E H L A

Only the instructions the manual documents are here: SLL, the halves of IX
and IY, the prefixes that change nothing and the second copies of ED
opcodes are Appendix B's.
"""
R8 = ["B", "C", "D", "E", "H", "L", "(HL)", "A"]
CC = ["NZ", "Z", "NC", "C", "PO", "PE", "P", "M"]
SS = ["BC", "DE", "HL", "SP"]
QQ = ["BC", "DE", "HL", "AF"]
ALU = [("ADD", "ADD A,"), ("ADC", "ADC A,"), ("SUB", "SUB "), ("SBC", "SBC A,"),
       ("AND", "AND "), ("XOR", "XOR "), ("OR", "OR "), ("CP", "CP ")]
ROT = ["RLC", "RRC", "RL", "RR", "SLA", "SRA", None, "SRL"]      # 6 is SLL: Appendix B
IDX = [("IX", 0xDD), ("IY", 0xFD)]

FAMILIES = [
    ("load8", "8-bit loads"),
    ("load16", "16-bit loads, the stack and the exchanges"),
    ("arith8", "8-bit arithmetic"),
    ("arith16", "16-bit arithmetic"),
    ("logic", "Logic and the carry"),
    ("rot", "Rotations and shifts"),
    ("bits", "Testing, setting and resetting bits"),
    ("jumps", "Jumps, calls and returns"),
    ("block", "Block instructions"),
    ("ports", "Ports"),
    ("control", "Control"),
]


def hexes(bs):
    return " ".join(f"{b:02X}" for b in bs)


def row(family, form, text, asm, key, args="", kind="plain", cc=None):
    """KEY the opcode bytes; ARGS what follows them, as the table shows it
    (for DD CB and FD CB the distance comes between: ARGS is then "d" and
    the last opcode byte is printed after it)"""
    if len(key) == 3 and key[1] == 0xCB:                # DD CB d op
        show = f"{key[0]:02X} CB d {key[2]:02X}"
    else:
        show = (hexes(key) + " " + args).strip()
    return {"family": family, "form": form, "text": text, "asm": asm, "show": show,
            "key": tuple(key), "kind": kind, "cc": cc}


def asm_r(r, ix=None):
    """a register of R8 as sjasmplus writes it, (HL) as (IX+d) with ix"""
    if r == "(HL)":
        return f"({ix.lower()}+{{d}})" if ix else "(hl)"
    return r.lower()


def text_r(r, ix=None):
    return f"({ix}+d)" if (r == "(HL)" and ix) else r


def load8():
    out = []
    for y in range(8):                                  # LD r,r'
        for z in range(8):
            if y != 6 and z != 6:
                out.append(row("load8", "LD r,r'", f"LD {R8[y]},{R8[z]}",
                               f"ld {asm_r(R8[y])},{asm_r(R8[z])}", [0x40 + 8 * y + z]))
    for y in range(8):
        if y != 6:
            out.append(row("load8", "LD r,n", f"LD {R8[y]},n", f"ld {asm_r(R8[y])},{{n}}",
                           [0x06 + 8 * y], "n"))
    for y in range(8):
        if y != 6:
            out.append(row("load8", "LD r,(HL)", f"LD {R8[y]},(HL)", f"ld {asm_r(R8[y])},(hl)",
                           [0x46 + 8 * y]))
    for ix, p in IDX:
        for y in range(8):
            if y != 6:
                out.append(row("load8", f"LD r,({ix}+d)", f"LD {R8[y]},({ix}+d)",
                               f"ld {asm_r(R8[y])},({ix.lower()}+{{d}})", [p, 0x46 + 8 * y], "d"))
    for z in range(8):
        if z != 6:
            out.append(row("load8", "LD (HL),r", f"LD (HL),{R8[z]}", f"ld (hl),{asm_r(R8[z])}",
                           [0x70 + z]))
    for ix, p in IDX:
        for z in range(8):
            if z != 6:
                out.append(row("load8", f"LD ({ix}+d),r", f"LD ({ix}+d),{R8[z]}",
                               f"ld ({ix.lower()}+{{d}}),{asm_r(R8[z])}", [p, 0x70 + z], "d"))
    out.append(row("load8", "LD (HL),n", "LD (HL),n", "ld (hl),{n}", [0x36], "n"))
    for ix, p in IDX:
        out.append(row("load8", f"LD ({ix}+d),n", f"LD ({ix}+d),n",
                       f"ld ({ix.lower()}+{{d}}),{{n}}", [p, 0x36], "d n"))
    out += [row("load8", "LD A,(BC)", "LD A,(BC)", "ld a,(bc)", [0x0A]),
            row("load8", "LD A,(DE)", "LD A,(DE)", "ld a,(de)", [0x1A]),
            row("load8", "LD A,(nn)", "LD A,(nn)", "ld a,({nn})", [0x3A], "n n"),
            row("load8", "LD (BC),A", "LD (BC),A", "ld (bc),a", [0x02]),
            row("load8", "LD (DE),A", "LD (DE),A", "ld (de),a", [0x12]),
            row("load8", "LD (nn),A", "LD (nn),A", "ld ({nn}),a", [0x32], "n n"),
            row("load8", "LD A,I", "LD A,I", "ld a,i", [0xED, 0x57]),
            row("load8", "LD A,R", "LD A,R", "ld a,r", [0xED, 0x5F]),
            row("load8", "LD I,A", "LD I,A", "ld i,a", [0xED, 0x47]),
            row("load8", "LD R,A", "LD R,A", "ld r,a", [0xED, 0x4F])]
    return out


def load16():
    out = []
    for p, ss in enumerate(SS):
        out.append(row("load16", "LD dd,nn", f"LD {ss},nn", f"ld {ss.lower()},{{nn}}",
                       [0x01 + 16 * p], "n n"))
    for ix, pre in IDX:
        out.append(row("load16", f"LD {ix},nn", f"LD {ix},nn", f"ld {ix.lower()},{{nn}}",
                       [pre, 0x21], "n n"))
    out.append(row("load16", "LD HL,(nn)", "LD HL,(nn)", "ld hl,({nn})", [0x2A], "n n"))
    for p, ss in enumerate(SS):
        # ED 6B is LD HL,(nn) too, four T-states slower: the manual lists it
        # under LD dd,(nn); an assembler always writes 2A, so it goes in as bytes
        asm = (f"ld {ss.lower()},({{nn}})" if ss != "HL" else "db $ED,$6B\n        dw {nn}")
        out.append(row("load16", "LD dd,(nn)", f"LD {ss},(nn)", asm, [0xED, 0x4B + 16 * p],
                       "n n"))
    for ix, pre in IDX:
        out.append(row("load16", f"LD {ix},(nn)", f"LD {ix},(nn)", f"ld {ix.lower()},({{nn}})",
                       [pre, 0x2A], "n n"))
    out.append(row("load16", "LD (nn),HL", "LD (nn),HL", "ld ({nn}),hl", [0x22], "n n"))
    for p, ss in enumerate(SS):
        asm = (f"ld ({{nn}}),{ss.lower()}" if ss != "HL" else "db $ED,$63\n        dw {nn}")
        out.append(row("load16", "LD (nn),dd", f"LD (nn),{ss}", asm, [0xED, 0x43 + 16 * p],
                       "n n"))
    for ix, pre in IDX:
        out.append(row("load16", f"LD (nn),{ix}", f"LD (nn),{ix}", f"ld ({{nn}}),{ix.lower()}",
                       [pre, 0x22], "n n"))
    out.append(row("load16", "LD SP,HL", "LD SP,HL", "ld sp,hl", [0xF9]))
    for ix, pre in IDX:
        out.append(row("load16", f"LD SP,{ix}", f"LD SP,{ix}", f"ld sp,{ix.lower()}",
                       [pre, 0xF9]))
    for p, qq in enumerate(QQ):
        out.append(row("load16", "PUSH qq", f"PUSH {qq}", f"push {qq.lower()}", [0xC5 + 16 * p]))
    for ix, pre in IDX:
        out.append(row("load16", f"PUSH {ix}", f"PUSH {ix}", f"push {ix.lower()}", [pre, 0xE5]))
    for p, qq in enumerate(QQ):
        out.append(row("load16", "POP qq", f"POP {qq}", f"pop {qq.lower()}", [0xC1 + 16 * p]))
    for ix, pre in IDX:
        out.append(row("load16", f"POP {ix}", f"POP {ix}", f"pop {ix.lower()}", [pre, 0xE1]))
    out += [row("load16", "EX DE,HL", "EX DE,HL", "ex de,hl", [0xEB]),
            row("load16", "EX AF,AF'", "EX AF,AF'", "ex af,af'", [0x08]),
            row("load16", "EXX", "EXX", "exx", [0xD9]),
            row("load16", "EX (SP),HL", "EX (SP),HL", "ex (sp),hl", [0xE3])]
    for ix, pre in IDX:
        out.append(row("load16", f"EX (SP),{ix}", f"EX (SP),{ix}", f"ex (sp),{ix.lower()}",
                       [pre, 0xE3]))
    return out


def alu8(family, ops):
    out = []
    for y in ops:
        name, head = ALU[y]
        for z in range(8):
            if z != 6:
                out.append(row(family, f"{head}r", f"{head}{R8[z]}",
                               f"{head.lower()}{asm_r(R8[z])}", [0x80 + 8 * y + z]))
        out.append(row(family, f"{head}n", f"{head}n", f"{head.lower()}{{n}}", [0xC6 + 8 * y],
                       "n"))
        out.append(row(family, f"{head}(HL)", f"{head}(HL)", f"{head.lower()}(hl)",
                       [0x86 + 8 * y]))
        for ix, p in IDX:
            out.append(row(family, f"{head}({ix}+d)", f"{head}({ix}+d)",
                           f"{head.lower()}({ix.lower()}+{{d}})", [p, 0x86 + 8 * y], "d"))
    return out


def arith8():
    out = alu8("arith8", [0, 1, 2, 3, 7])
    for name, z in (("INC", 4), ("DEC", 5)):
        for y in range(8):
            if y != 6:
                out.append(row("arith8", f"{name} r", f"{name} {R8[y]}",
                               f"{name.lower()} {asm_r(R8[y])}", [8 * y + z]))
        out.append(row("arith8", f"{name} (HL)", f"{name} (HL)", f"{name.lower()} (hl)",
                       [0x30 + z]))
        for ix, p in IDX:
            out.append(row("arith8", f"{name} ({ix}+d)", f"{name} ({ix}+d)",
                           f"{name.lower()} ({ix.lower()}+{{d}})", [p, 0x30 + z], "d"))
    out += [row("arith8", "NEG", "NEG", "neg", [0xED, 0x44]),
            row("arith8", "DAA", "DAA", "daa", [0x27])]
    return out


def arith16():
    out = []
    for p, ss in enumerate(SS):
        out.append(row("arith16", "ADD HL,ss", f"ADD HL,{ss}", f"add hl,{ss.lower()}",
                       [0x09 + 16 * p]))
    for p, ss in enumerate(SS):
        out.append(row("arith16", "ADC HL,ss", f"ADC HL,{ss}", f"adc hl,{ss.lower()}",
                       [0xED, 0x4A + 16 * p]))
    for p, ss in enumerate(SS):
        out.append(row("arith16", "SBC HL,ss", f"SBC HL,{ss}", f"sbc hl,{ss.lower()}",
                       [0xED, 0x42 + 16 * p]))
    for ix, pre in IDX:
        for p, ss in enumerate(SS):
            ss = ix if ss == "HL" else ss
            out.append(row("arith16", f"ADD {ix},{'pp' if ix == 'IX' else 'rr'}", f"ADD {ix},{ss}",
                           f"add {ix.lower()},{ss.lower()}", [pre, 0x09 + 16 * p]))
    for name, z in (("INC", 0x03), ("DEC", 0x0B)):
        for p, ss in enumerate(SS):
            out.append(row("arith16", f"{name} ss", f"{name} {ss}", f"{name.lower()} {ss.lower()}",
                           [z + 16 * p]))
        for ix, pre in IDX:
            out.append(row("arith16", f"{name} {ix}", f"{name} {ix}",
                           f"{name.lower()} {ix.lower()}", [pre, z + 0x20]))
    return out


def logic():
    return alu8("logic", [4, 5, 6]) + [
        row("logic", "CPL", "CPL", "cpl", [0x2F]),
        row("logic", "SCF", "SCF", "scf", [0x37]),
        row("logic", "CCF", "CCF", "ccf", [0x3F])]


def rot():
    out = [row("rot", "RLCA", "RLCA", "rlca", [0x07]), row("rot", "RRCA", "RRCA", "rrca", [0x0F]),
           row("rot", "RLA", "RLA", "rla", [0x17]), row("rot", "RRA", "RRA", "rra", [0x1F])]
    for y, name in enumerate(ROT):
        if name is None:
            continue
        for z in [0, 1, 2, 3, 4, 5, 7, 6]:              # the registers, then (HL)
            form = f"{name} (HL)" if z == 6 else f"{name} r"
            out.append(row("rot", form, f"{name} {R8[z]}", f"{name.lower()} {asm_r(R8[z])}",
                           [0xCB, 8 * y + z]))
        for ix, p in IDX:
            out.append(row("rot", f"{name} ({ix}+d)", f"{name} ({ix}+d)",
                           f"{name.lower()} ({ix.lower()}+{{d}})", [p, 0xCB, 8 * y + 6], "d"))
    out += [row("rot", "RLD", "RLD", "rld", [0xED, 0x6F]),
            row("rot", "RRD", "RRD", "rrd", [0xED, 0x67])]
    return out


def bits():
    out = []
    for x, name in ((1, "BIT"), (2, "RES"), (3, "SET")):
        for b in range(8):                              # the registers, then (HL)
            for z in (0, 1, 2, 3, 4, 5, 7):
                out.append(row("bits", f"{name} b,r", f"{name} {b},{R8[z]}",
                               f"{name.lower()} {b},{asm_r(R8[z])}", [0xCB, 64 * x + 8 * b + z]))
        for b in range(8):
            out.append(row("bits", f"{name} b,(HL)", f"{name} {b},(HL)", f"{name.lower()} {b},(hl)",
                           [0xCB, 64 * x + 8 * b + 6]))
        for ix, p in IDX:
            for b in range(8):
                out.append(row("bits", f"{name} b,({ix}+d)", f"{name} {b},({ix}+d)",
                               f"{name.lower()} {b},({ix.lower()}+{{d}})",
                               [p, 0xCB, 64 * x + 8 * b + 6], "d"))
    return out


def jumps():
    out = [row("jumps", "JP nn", "JP nn", "jp {t}", [0xC3], "n n", "jump")]
    for y, cc in enumerate(CC):
        out.append(row("jumps", "JP cc,nn", f"JP {cc},nn", f"jp {cc.lower()},{{t}}",
                       [0xC2 + 8 * y], "n n", "cond", cc))
    out.append(row("jumps", "JR e", "JR e", "jr {t}", [0x18], "e", "jump"))
    for y, cc in enumerate(CC[:4]):
        out.append(row("jumps", "JR cc,e", f"JR {cc},e", f"jr {cc.lower()},{{t}}",
                       [0x20 + 8 * y], "e", "cond", cc))
    out.append(row("jumps", "JP (HL)", "JP (HL)", "jp (hl)", [0xE9], "", "jump"))
    for ix, pre in IDX:
        out.append(row("jumps", f"JP ({ix})", f"JP ({ix})", f"jp ({ix.lower()})", [pre, 0xE9],
                       "", "jump"))
    out.append(row("jumps", "DJNZ e", "DJNZ e", "djnz {t}", [0x10], "e", "cond", "B"))
    out.append(row("jumps", "CALL nn", "CALL nn", "call {t}", [0xCD], "n n", "jump"))
    for y, cc in enumerate(CC):
        out.append(row("jumps", "CALL cc,nn", f"CALL {cc},nn", f"call {cc.lower()},{{t}}",
                       [0xC4 + 8 * y], "n n", "cond", cc))
    out.append(row("jumps", "RET", "RET", "ret", [0xC9], "", "jump"))
    for y, cc in enumerate(CC):
        out.append(row("jumps", "RET cc", f"RET {cc}", f"ret {cc.lower()}", [0xC0 + 8 * y], "",
                       "cond", cc))
    out += [row("jumps", "RETI", "RETI", "reti", [0xED, 0x4D], "", "jump"),
            row("jumps", "RETN", "RETN", "retn", [0xED, 0x45], "", "jump")]
    for k in range(8):
        out.append(row("jumps", "RST p", f"RST ${8 * k:02X}", f"rst ${8 * k:02X}", [0xC7 + 8 * k], "",
                       "jump"))
    return out


def block():
    out = []
    for z, kind in ((0, "LD"), (1, "CP"), (2, "IN"), (3, "OUT")):
        for y, (inc, rep) in ((4, ("I", "")), (6, ("I", "R")), (5, ("D", "")), (7, ("D", "R"))):
            if kind == "OUT":
                name = {"I": "OUTI", "D": "OUTD", "IR": "OTIR", "DR": "OTDR"}[inc + rep]
            else:
                name = kind + inc + rep
            out.append(row("block", name, name, name.lower(), [0xED, 0x80 + 8 * y + z], "",
                           "repeat" if rep else "block"))
    return out


def ports():
    out = [row("ports", "IN A,(n)", "IN A,(n)", "in a,({n})", [0xDB], "n")]
    for y in range(8):
        if y != 6:
            out.append(row("ports", "IN r,(C)", f"IN {R8[y]},(C)", f"in {asm_r(R8[y])},(c)",
                           [0xED, 0x40 + 8 * y]))
    out.append(row("ports", "OUT (n),A", "OUT (n),A", "out ({n}),a", [0xD3], "n"))
    for y in range(8):
        if y != 6:
            out.append(row("ports", "OUT (C),r", f"OUT (C),{R8[y]}", f"out (c),{asm_r(R8[y])}",
                           [0xED, 0x41 + 8 * y]))
    return out


def control():
    return [row("control", "NOP", "NOP", "nop", [0x00]),
            row("control", "HALT", "HALT", "halt", [0x76], "", "halt"),
            row("control", "DI", "DI", "di", [0xF3]),
            row("control", "EI", "EI", "ei", [0xFB]),
            row("control", "IM 0", "IM 0", "im 0", [0xED, 0x46]),
            row("control", "IM 1", "IM 1", "im 1", [0xED, 0x56]),
            row("control", "IM 2", "IM 2", "im 2", [0xED, 0x5E])]


MAKERS = {"load8": load8, "load16": load16, "arith8": arith8, "arith16": arith16,
          "logic": logic, "rot": rot, "bits": bits, "jumps": jumps, "block": block,
          "ports": ports, "control": control}


def rows():
    out = []
    for fam, _ in FAMILIES:
        out += MAKERS[fam]()
    for k, r in enumerate(out, start=1):
        r["n"] = k
    keys = [r["key"] for r in out]
    assert len(set(keys)) == len(keys) == 698, len(keys)
    return out


def counts():
    """how many of each prefix: unprefixed, CB, ED, DD, FD, DD CB, FD CB"""
    from collections import Counter
    c = Counter()
    for r in rows():
        k = r["key"]
        c[("DD CB" if k[0] == 0xDD else "FD CB") if len(k) == 3 and k[1] == 0xCB else
          {0xCB: "CB", 0xED: "ED", 0xDD: "DD", 0xFD: "FD"}.get(k[0], "none")] += 1
    return c


if __name__ == "__main__":
    rs = rows()
    print(len(rs), dict(counts()))
    for fam, title in FAMILIES:
        print(fam, sum(1 for r in rs if r["family"] == fam))
