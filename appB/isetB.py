"""isetB.py - what the Z80 does that Zilog's manual leaves out, as Appendix B
lists it.

    rows()      1,086 instructions outside Appendix A's 698, in six groups,
                each a dict as in ../appA/iset.py (family, text, asm, show,
                key, kind, cc, n) and:
        group   "sll", "half", "prefix", "ed", "xcb" or "chain"
        twin    the key of the documented instruction it is a copy or a
                variant of, if any: what it does is checked against it

    sll     SLL r, SLL (HL), SLL (IX+d), SLL (IY+d): CB 30 to 37, DD CB d 36
            and FD CB d 36. A 1 comes in at bit 0 (chapter 10)
    half    the halves of IX and IY (chapters 7 and 13): DD or FD before
            an instruction without a prefix that names H or L and not (HL)
    prefix  DD or FD before any other instruction without a prefix that
            the manual does not have with DD or FD, HALT apart: it runs as
            if the prefix were not there (EX DE,HL and EXX among them)
    ed      ED before an opcode the manual leaves out: copies of NEG,
            RETN and IM, IN F,(C), OUT (C),0, and the rest, which do nothing
    xcb     DD CB d op and FD CB d op where the manual has only op's last
            three bits 110: the result also goes into a register, and BIT
            does the same whichever register
    chain   two prefixes in a row: four LD IX,nn and LD IY,nn, and NEG
            after DD ED and FD ED
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "appA"))
import iset

R8 = iset.R8
IDX = iset.IDX
ROT = ["RLC", "RRC", "RL", "RR", "SLA", "SRA", "SLL", "SRL"]
HALF = {"IX": ("IXH", "IXL"), "IY": ("IYH", "IYL")}


def documented():
    return {r["key"]: r for r in iset.rows()}


def row(group, text, asm, key, twin=None, like=None, args=""):
    """LIKE: the documented row whose kind, cc and text decide how the
    instruction is timed and run"""
    show = " ".join(f"{b:02X}" for b in key) + (" " + args if args else "")
    if len(key) == 3 and key[1] == 0xCB:                # DD CB d op, as in appA
        show = f"{key[0]:02X} CB d {key[2]:02X}"
    r = {"group": group, "family": group, "form": text, "text": text, "asm": asm,
         "show": show.strip(),
         "key": tuple(key), "twin": twin, "kind": "plain", "cc": None, "like": None}
    if like is not None:
        r.update(kind=like["kind"], cc=like["cc"], like=like["text"])
    return r


def sll():
    out = []
    for z in [0, 1, 2, 3, 4, 5, 7, 6]:
        out.append(row("sll", f"SLL {R8[z]}", f"sll {iset.asm_r(R8[z])}", [0xCB, 0x30 + z]))
    for ix, p in IDX:
        out.append(row("sll", f"SLL ({ix}+d)", f"db ${p:02X},$CB,{{d}},$36", [p, 0xCB, 0x36]))
    return out


def half():
    out = []
    doc = documented()
    for ix, p in IDX:
        hi, lo = HALF[ix]
        name = {"H": hi, "L": lo}
        for op in range(0x100):
            base = doc.get((op,))
            if base is None or (p, op) in doc or op == 0x76:
                continue
            x, y, z = op >> 6, op >> 3 & 7, op & 7
            uses = ((x == 1 and (y in (4, 5) or z in (4, 5)) and 6 not in (y, z))
                    or (x == 2 and z in (4, 5))
                    or (x == 0 and z in (4, 5, 6) and y in (4, 5)))
            if not uses:
                continue
            text = base["text"]
            if x == 1:
                text = f"LD {name.get(R8[y], R8[y])},{name.get(R8[z], R8[z])}"
            elif x == 2:
                head = iset.ALU[y][1]
                text = f"{head}{name[R8[z]]}"
            else:
                what = {4: "INC", 5: "DEC", 6: "LD"}[z]
                text = f"{what} {name[R8[y]]}" + (",n" if z == 6 else "")
            asm = text.lower().replace(",n", ",{n}")
            out.append(row("half", text, asm, [p, op], twin=(op,), like=base,
                           args="n" if z == 6 and x == 0 else ""))
    return out


def prefix():
    out = []
    doc = documented()
    halves = {r["key"] for r in half()}
    for ix, p in IDX:
        for op in range(0x100):
            base = doc.get((op,))
            if base is None or (p, op) in doc or (p, op) in halves or op == 0x76:
                continue
            asm = f"db ${p:02X}\n        " + base["asm"]
            out.append(row("prefix", f"{ix[0:2].replace('IX', 'DD').replace('IY', 'FD')} "
                           f"{base['text']}", asm, [p, op], twin=(op,), like=base,
                           args=base["show"][3:]))
    return out


def ed():
    out = []
    doc = documented()
    for op in range(0x100):
        if (0xED, op) in doc:
            continue
        x, y, z = op >> 6, op >> 3 & 7, op & 7
        twin = like = None
        if x == 1 and z == 4:
            twin, text = (0xED, 0x44), "NEG"
        elif x == 1 and z == 5:
            twin, text = (0xED, 0x45), "RETN"
        elif x == 1 and z == 6:
            text = "IM ?"                               # which mode: measured
        elif op == 0x70:
            text = "IN F,(C)"
        elif op == 0x71:
            text = "OUT (C),0"
        else:
            text = "ED NOP"
        if twin:
            like = doc[twin]
        out.append(row("ed", text, f"db $ED,${op:02X}", [0xED, op], twin=twin, like=like))
    return out


def xcb():
    out = []
    doc = documented()
    for ix, p in IDX:
        for op in range(0x100):
            x, y, z = op >> 6, op >> 3 & 7, op & 7
            if z == 6:
                continue                                # documented, or SLL (IX+d)
            twin = (p, 0xCB, (op & 0xF8) | 6)
            if x == 0:
                text = f"{ROT[y]} ({ix}+d),{R8[z]}"
            elif x == 1:
                text = f"BIT {y},({ix}+d)"
            else:
                text = f"{('RES', 'SET')[x - 2]} {y},({ix}+d),{R8[z]}"
            like = doc.get(twin)
            out.append(row("xcb", text, f"db ${p:02X},$CB,{{d}},${op:02X}", [p, 0xCB, op],
                           twin=twin if like else None, like=like))
    return out


def chain():
    doc = documented()
    out = []
    for pre, then, ix in ((0xDD, 0xFD, "IY"), (0xFD, 0xDD, "IX"), (0xDD, 0xDD, "IX"),
                          (0xFD, 0xFD, "IY")):
        twin = (then, 0x21)
        asm = f"db ${pre:02X}\n        ld {ix.lower()},{{nn}}"
        out.append(row("chain", f"{pre:02X} LD {ix},nn", asm, [pre, then, 0x21], twin=twin,
                       like=doc[twin], args="n n"))
    for pre in (0xDD, 0xFD):
        out.append(row("chain", f"{pre:02X} NEG", f"db ${pre:02X},$ED,$44", [pre, 0xED, 0x44],
                       twin=(0xED, 0x44), like=doc[(0xED, 0x44)]))
    return out


GROUPS = [("sll", sll), ("half", half), ("prefix", prefix), ("ed", ed), ("xcb", xcb),
          ("chain", chain)]


def rows():
    out = []
    for name, make in GROUPS:
        out += make()
    for k, r in enumerate(out, start=1):
        r["n"] = k
    keys = [r["key"] for r in out]
    assert len(set(keys)) == len(keys)
    return out


if __name__ == "__main__":
    from collections import Counter
    rs = rows()
    print(len(rs), dict(Counter(r["group"] for r in rs)))
    print(dict(Counter(r["text"] for r in rs if r["group"] == "ed")))
