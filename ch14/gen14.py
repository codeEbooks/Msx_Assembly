#!/usr/bin/env python3
"""gen14.py - the programs of chapter 14.

    python3 gen14.py && ./build.sh

    all.asm        every Z80 instruction that does not jump, once each; a
                   routine puts the pointer registers back after any
                   instruction that changed them. meas14.py stops before every
                   one and reads the time and R.
    price.asm      16 characters printed by putc, with the display off: the
                   time of one character, and of the line.
    budget.asm     a loop of exactly one frame, 71,364 T-states on the 50 Hz
                   machine and 59,736 on the 60 Hz one, that runs six
                   routines, each with the border in its own colour, and the
                   display off, so that the border fills the screen (figure
                   14.1).
    slow.asm       WHERE IT BREAKS: a wait of one 50 Hz frame worked out from
                   Zilog's table, and 256 NOPs, as the MSX runs them.

The prices the programs are built from are Zilog's plus one for every M1
(chapter 3), and all.asm measures every one of them that does not jump.
build.sh assembles with --syntax=bF (chapter 8).
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
from asmparts import HEAD, TAIL, TEXT_PAGE, SHOW_PAGE, library  # noqa: E402


def head(name, what):
    return HEAD.format(name=name, chapter=14, what=what)


# ------------------------------------------------------------------ all.asm
# where the pointer registers point while the instructions run: all of it
# in the RAM. C is the VDP's data port, for the instructions that use (C).
PTR = {"bc": 0xC098, "de": 0xC100, "hl": 0xC200, "ix": 0xC300, "iy": 0xC400}
NN = 0xC500                 # the address in the instructions that carry one
D = 5                       # the distance in (IX+d) and (IY+d)
N = 0x5A                    # the number in the instructions that carry one
PORT = 0x98                 # the VDP's data port, with the display off
LD_SP = "ld sp,SYS_AREA"    # the test of LD SP,nn

R8 = ["b", "c", "d", "e", "h", "l", "(hl)", "a"]
ALU = ["add a,", "adc a,", "sub ", "sbc a,", "and ", "xor ", "or ", "cp "]
ROT = ["rlc", "rrc", "rl", "rr", "sla", "sra", "sll", "srl"]
POINTER_PARTS = {"b", "c", "d", "e", "h", "l", "bc", "de", "hl",
                 "ix", "iy", "ixh", "ixl", "iyh", "iyl"}


def io_tests():
    """the instructions that use a port"""
    t = [f"in a,(${PORT:02X})", f"out (${PORT:02X}),a"]
    for r in "bcdehla":
        t.append(f"in {r},(c)")
    for r in "bcdehla":
        t.append(f"out (c),{r}")
    return t


def plain_tests():
    t = ["nop"]
    for y in range(8):
        for z in range(8):
            if not (y == 6 and z == 6):
                t.append(f"ld {R8[y]},{R8[z]}")
    for y in range(8):
        t.append(f"ld {R8[y]},${N:02X}")
    for a in ALU:
        for r in R8:
            t.append(a + r)
        t.append(a + f"${N:02X}")
    for op in ("inc", "dec"):
        for r in R8:
            t.append(f"{op} {r}")
        for rr in ("bc", "de", "hl", "sp"):
            t.append(f"{op} {rr}")
    for rr in ("bc", "de", "hl", "sp"):
        t.append(f"add hl,{rr}")
    t += [f"ld bc,${PTR['bc']:04X}", f"ld de,${PTR['de']:04X}", f"ld hl,${PTR['hl']:04X}",
          LD_SP, "ld a,(bc)", "ld a,(de)", "ld (bc),a", "ld (de),a",
          f"ld a,(${NN:04X})", f"ld (${NN:04X}),a", f"ld hl,(${NN:04X})",
          f"ld (${NN:04X}),hl", "ld sp,hl",
          "rlca", "rrca", "rla", "rra", "daa", "cpl", "scf", "ccf",
          "ex af,af'", "exx", "ex de,hl", "ex (sp),hl", "ei", "di"]
    for qq in ("bc", "de", "hl", "af"):
        t += [f"push {qq}", f"pop {qq}"]
    return t


def cb_tests():
    t = []
    for rot in ROT:
        for r in R8:
            t.append(f"{rot} {r}")
    for op in ("bit", "res", "set"):
        for b in range(8):
            for r in R8:
                t.append(f"{op} {b},{r}")
    return t


def ed_tests():
    t = []
    for rr in ("bc", "de", "hl", "sp"):
        t += [f"sbc hl,{rr}", f"adc hl,{rr}"]
    for rr in ("bc", "de", "sp"):              # LD (nn),HL is the short form
        t += [f"ld (${NN:04X}),{rr}", f"ld {rr},(${NN:04X})"]
    t += ["neg", "im 0", "im 2", "im 1", "ld i,a", "ld r,a", "ld a,i", "ld a,r",
          "rrd", "rld"]
    return t


def index_tests(ix):
    h, l = ix + "h", ix + "l"
    m = f"({ix}+{D})"
    t = [f"ld {ix},${PTR[ix]:04X}", f"ld (${NN:04X}),{ix}", f"ld {ix},(${NN:04X})",
         f"inc {ix}", f"dec {ix}", f"push {ix}", f"pop {ix}", f"ex (sp),{ix}",
         f"ld sp,{ix}"]
    for rr in ("bc", "de", ix, "sp"):
        t.append(f"add {ix},{rr}")
    for r in "bcdehla":
        t += [f"ld {r},{m}", f"ld {m},{r}"]
    t.append(f"ld {m},${N:02X}")
    for a in ALU:
        t += [a + m, a + h, a + l]
    t += [f"inc {m}", f"dec {m}", f"inc {h}", f"dec {h}", f"inc {l}", f"dec {l}"]
    for r in ("b", "c", "d", "e", "a", h, l):
        t += [f"ld {r},{h}", f"ld {r},{l}"]
    for r in ("b", "c", "d", "e", "a"):
        t += [f"ld {h},{r}", f"ld {l},{r}"]
    t += [f"ld {h},${N:02X}", f"ld {l},${N:02X}"]
    for rot in ROT:
        t.append(f"{rot} {m}")
    for op in ("bit", "res", "set"):
        for b in range(8):
            t.append(f"{op} {b},{m}")
    return t


def tests():
    return io_tests() + plain_tests() + cb_tests() + ed_tests() + index_tests("ix") + \
        index_tests("iy")


def writes(ins):
    """what an instruction may change among the pointer registers and SP:
    'sp', 'ptr', or None"""
    op, _, args = ins.partition(" ")
    first = args.split(",")[0]
    if op == "ld" and first == "sp" or ins in ("inc sp", "dec sp"):
        return "sp"
    if op in ("exx", "ex") and ins != "ex af,af'":
        return "ptr"
    if op == "pop" and args != "af":
        return "ptr"
    if op in ("ld", "inc", "dec", "add", "adc", "sbc", "in") and first in POINTER_PARTS:
        return "ptr"
    if op in ROT + ["res", "set"]:
        target = args.split(",")[-1]
        if target in POINTER_PARTS:
            return "ptr"
    return None


def all_():
    lines, k = [], 0
    for ins in tests():
        lines.append(f"{f't{k}:':<8}{ins}")
        k += 1
        w = writes(ins)
        if w == "sp":
            lines.append(f"{f'f{k}:':<8}ld sp,TOP               ; the stack back")
        elif w == "ptr":
            lines.append(f"{f'f{k}:':<8}call fix")
    return head("all", "every instruction that does not jump") + f"""; Every instruction that does not jump, once each. The pointer registers
; point into the RAM, and fix puts them back after any instruction that
; changed them. The port is the VDP's data port, with the display off: what
; goes in and out is harmless. meas14.py stops before each instruction and
; reads the time and R.
TOP     EQU SYS_AREA - 2        ; the stack, with a word above it for EX (SP),HL
init:   di
        ld sp, TOP
        VDP_REG 1, $80          ; display off
        call fix
""" + "\n".join(lines) + f"""
done:   im 1
stop:   jr stop

; fix: the pointer registers back where they belong
fix:    ld bc,${PTR['bc']:04X}
        ld de,${PTR['de']:04X}
        ld hl,${PTR['hl']:04X}
        ld ix,${PTR['ix']:04X}
        ld iy,${PTR['iy']:04X}
        ret
""" + TAIL


# ---------------------------------------------------------------- price.asm
LINE_TEXT = "Sixteen letters."
PRICE_ROW = 10


def price():
    return head("price", "a line printed by putc, timed") + f"""; A line of text printed by putc, with the display off: the time of each
; character and of the line.
""" + TEXT_PAGE + f"""        ld hl, text
        ld b, {PRICE_ROW}                ; the row
        ld c, 0                 ; the column
p1:     ld a, (hl)
        or a
        jr z, p2                ; the 0 at the end
c1:     call putc
c2:     inc hl
        inc c
        jr p1
p2:     nop
""" + SHOW_PAGE + library() + f'text:   db "{LINE_TEXT}", 0\n' + TAIL


# --------------------------------------------------------------- budget.asm
FRAME_T = {"MSXBOOK_EU16": 71364, "MSXBOOK_JP16": 59736}     # tools/meas.py
T_PER_LINE = 228
FIRST_LINE = 45             # the top line a capture shows (tools/meas.py)
DRAWN = (19, 302)           # the columns the VDP draws (tools/meas.py)
MARGIN = 6                  # no change of colour this close to their edges

# the MSX prices the programs are built from: Zilog's plus one for every M1.
# meas14.py checks every one that does not jump against all.asm; the jumps
# are chapter 11's, CALL and RET chapter 12's, LDIR and CPIR chapter 13's.
T = {"nop": 5, "ld r,n": 8, "ld rr,nn": 11, "ld a,(de)": 8, "ld (de),a": 8,
     "ld r,r": 5, "ld a,(hl)": 8, "ld (hl),a": 8, "ld (hl),n": 11, "inc de": 7,
     "inc l": 5, "dec de": 7, "or r": 5, "push": 12, "pop": 11, "rr r": 10,
     "rla": 5, "ld a,(nn)": 14, "out (n),a": 12,
     "djnz": 14, "djnz_last": 9, "jr": 13, "jr_not": 8, "jp": 11, "jp cc": 11,
     "call": 18, "ret": 11, "ldir": 23, "ldir_last": 18, "cpir": 23, "cpir_last": 18}
# which all.asm instruction measures each of them
MEASURED_BY = {"nop": "nop", "ld r,n": "ld b,$5A", "ld rr,nn": "ld de,$C100",
               "ld a,(de)": "ld a,(de)", "ld (de),a": "ld (de),a", "ld r,r": "ld a,d",
               "ld a,(hl)": "ld a,(hl)", "ld (hl),a": "ld (hl),a", "ld (hl),n": "ld (hl),$5A",
               "inc de": "inc de", "inc l": "inc l", "dec de": "dec de", "or r": "or e",
               "push": "push hl", "pop": "pop hl", "rr r": "rr c", "rla": "rla",
               "ld a,(nn)": "ld a,($C500)", "out (n),a": "out ($98),a"}

# how many opcode fetches each of them makes, and so Zilog's own price
FETCHES = {k: 1 for k in T}
FETCHES.update({"rr r": 2, "ldir": 2, "ldir_last": 2, "cpir": 2, "cpir_last": 2})
ZILOG_T = {k: T[k] - FETCHES[k] for k in T}

T_VDP_REG = 2 * T["ld r,n"] + 2 * T["out (n),a"]          # chapter 5's macro: 40
WRITE_AT = T["ld r,n"] + T["out (n),a"] + T["ld r,n"] + 8  # the register is written 8 T
                                                           # into the second OUT


def t_mirror(P):
    """a call of chapter 10's mirror"""
    return (P["call"] + P["ld r,r"] + P["ld r,n"] +
            8 * (P["rr r"] + P["rla"] + P["djnz"]) - (P["djnz"] - P["djnz_last"]) + P["ret"])


T_MIRROR = t_mirror(T)

ZERO = 0xD000               # 512 bytes made 0, for LDIR and CPIR to work on
BYTES = 0xC300              # 32 bytes turned round, every frame
MIRRORS = 0xC400            # chapter 13's table of turned-round bytes

# the six routines: the name, the border colour, the code, and the price from a
# table of prices, the MSX's or Zilog's. The colours are black and light green,
# not white: figure 14.1 is all border, and must show where the screen ends on a
# white page.
_BANDS = [
    ("nop256", "BLACK", """        ld b, 0
b1:     nop                     ; 256 NOPs in a DJNZ loop
        djnz b1
""", lambda P: P["ld r,n"] + 256 * (P["nop"] + P["djnz"]) - (P["djnz"] - P["djnz_last"])),
    ("ldir320", "LIGHT_GREEN", f"""        ld hl, ${ZERO:04X}
        ld de, ${ZERO + 0x200:04X}
        ld bc, 320
        ldir                    ; 320 bytes copied
""", lambda P: 3 * P["ld rr,nn"] + 319 * P["ldir"] + P["ldir_last"]),
    ("mirror32", "BLACK", f"""        ld de, ${BYTES:04X}
        ld b, 32
b3:     ld a, (de)
        push bc
        call mirror             ; 32 bytes turned round by chapter 10's mirror
        pop bc
        ld (de), a
        inc de
        djnz b3
""", lambda P: (P["ld rr,nn"] + P["ld r,n"] +
                32 * (P["ld a,(de)"] + P["push"] + t_mirror(P) + P["pop"] + P["ld (de),a"] +
                      P["inc de"] + P["djnz"]) - (P["djnz"] - P["djnz_last"]))),
    ("table32", "LIGHT_GREEN", f"""        ld de, ${BYTES:04X}
        ld b, 32
        ld h, high MIRRORS
b4:     ld a, (de)
        ld l, a
        ld a, (hl)              ; and back again with chapter 13's table
        ld (de), a
        inc de
        djnz b4
""", lambda P: (P["ld rr,nn"] + 2 * P["ld r,n"] +
                32 * (P["ld a,(de)"] + P["ld r,r"] + P["ld a,(hl)"] + P["ld (de),a"] +
                      P["inc de"] + P["djnz"]) - (P["djnz"] - P["djnz_last"]))),
    ("push100", "BLACK", """        ld b, 100
b5:     push hl
        pop hl                  ; 100 PUSHes and POPs
        djnz b5
""", lambda P: (P["ld r,n"] + 100 * (P["push"] + P["pop"] + P["djnz"]) -
                (P["djnz"] - P["djnz_last"]))),
    ("cpir256", "LIGHT_GREEN", f"""        ld hl, ${ZERO:04X}
        ld bc, 256
        ld a, $FF               ; a byte that is not there
        cpir                    ; 256 bytes searched
""", lambda P: 2 * P["ld rr,nn"] + P["ld r,n"] + 255 * P["cpir"] + P["cpir_last"]),
]
BANDS = [(name, colour, text, price(T), price(ZILOG_T)) for name, colour, text, price
         in _BANDS]

T_CHOOSE = T["ld a,(nn)"] + T["rla"] + T["jp cc"]         # which frame: $002B
COLOUR = {"BLACK": 1, "LIGHT_GREEN": 3}   # 3 and 176 in grey: the page is white


def loop_plan():
    """the T-state of each band's start from the start of the loop, the
    loop's price without the wait, and the wait that makes each frame"""
    t, starts = 0, []
    for name, colour, text, price, _ in BANDS:
        starts.append(t)
        t += T_VDP_REG + price
    busy = t + T_CHOOSE + T["jp"]
    return starts, busy, {m: f - busy for m, f in FRAME_T.items()}


def wait_code(total, label):
    """code that takes exactly TOTAL T-states on the MSX: a sixteen-bit
    count, as chapter 11 counted it (30 a turn, 5 less for the last, 11 to
    load), and NOPs of 5 and LD C,0 of 8 to make up the rest"""
    turn = T["dec de"] + T["ld r,r"] + T["or r"] + T["jr"]
    for eights in range(0, 8):
        for fives in range(0, 8):
            rest = total - T["ld rr,nn"] + (T["jr"] - T["jr_not"]) - 8 * eights - 5 * fives
            if rest > 0 and rest % turn == 0:
                n = rest // turn
                code = f"""{label + 's:':<8}ld de, {n}
{label + ':':<8}dec de
        ld a, d
        or e
        jr nz, {label}
""" + "        ld c, 0\n" * eights + "        nop\n" * fives
                return code, n, eights, fives
    raise ValueError(total)


def write_at(f0, start):
    """(line, x) where the change of colour of the band that starts at
    START, in a loop that starts at T-state F0 of the frame, shows: a write
    at T-state w of a line shows at x = ceil(1.5 w - 31) (chapter 8)"""
    line, w = divmod(f0 + start + WRITE_AT, T_PER_LINE)
    return line, math.ceil(1.5 * w - 31)


def choose_f0():
    """where the loop starts on the 50 Hz machine: the first T-state of line
    FIRST_LINE - 1 or later that puts the first change of colour above the top
    of the capture and every change well inside the columns the VDP draws"""
    starts, _, _ = loop_plan()
    for f0 in range((FIRST_LINE - 1) * T_PER_LINE, FIRST_LINE * T_PER_LINE):
        where = [write_at(f0, s) for s in starts]
        if where[0][0] == FIRST_LINE - 1 and \
                all(DRAWN[0] + MARGIN <= x <= DRAWN[1] - MARGIN for _, x in where):
            return f0
    raise ValueError("no start fits")


F0 = choose_f0()
# SYNC_T: the T-state of the frame at which the program is when the HALT has
# returned and the interrupts are off again, on the 50 Hz machine: where
# C-BIOS's interrupt routine hands back. Measured by meas14.py (budget),
# which checks it every run; everything after it is priced.
SYNC_T = 60064


def preamble_wait():
    w = (F0 - SYNC_T) % FRAME_T["MSXBOOK_EU16"]
    return w if w >= 100 else w + FRAME_T["MSXBOOK_EU16"]


def budget():
    starts, busy, rest = loop_plan()
    w50, *_ = wait_code(rest["MSXBOOK_EU16"], "w50")
    w60, *_ = wait_code(rest["MSXBOOK_JP16"], "w60")
    w1, *_ = wait_code(preamble_wait(), "w1")
    bands = "".join(f"""{f'o{k}:':<8}VDP_REG 7, {colour:<13}; the border {colour.lower().replace('_', ' ')}: {name}
""" + text for k, (name, colour, text, _, _) in enumerate(BANDS))
    return head("budget", "a loop of exactly one frame") + f"""; A loop that takes exactly one frame and runs six routines, each with the
; border in its own colour. The display is off, so that the border fills the
; screen (figure 14.1). Every price is the MSX's, Zilog's plus one for every
; M1, and the wait at the end makes up the rest of the frame: {FRAME_T['MSXBOOK_EU16']:,}
; T-states on a 50 Hz machine, {FRAME_T['MSXBOOK_JP16']:,} on a 60 Hz one.
ZERO    EQU ${ZERO:04X}           ; 512 bytes of 0, for LDIR and CPIR
MIRRORS EQU ${MIRRORS:04X}           ; chapter 13's table
init:   di
        ld sp, SYS_AREA
        ld hl, ZERO
        ld de, ZERO + 1
        ld (hl), 0
        ld bc, 511
        ldir                    ; the bytes LDIR and CPIR work on: all 0
        call mktab              ; chapter 13's table
        VDP_REG 1, $A0          ; display off, the frame interrupt on
        in a, (VDP_CTRL)        ; clear a frame flag left from before (chapter 4)
        im 1
        ei
        halt                    ; the end of a picture, and C-BIOS's routine
        di                      ; from here on, nothing but this program
""" + w1 + """frame:
""" + bands + """        ld a, ($002B)           ; bit 7 is 1 on a 50 Hz machine (chapter 4)
        rla                     ; into the carry
        jp nc, w60s             ; 60 Hz: the shorter wait
""" + w50 + """b50:    jp frame
""" + w60 + f"""b60:    jp frame

; mktab: the 256-byte table at MIRRORS: byte n holds n mirrored
mktab:  ld hl, MIRRORS
mk1:    ld a, l
        call mirror
        ld (hl), a
        inc l
        jr nz, mk1
        ret

; mirror: A = A with its bits in the opposite order. Uses B and C.
mirror: ld c, a
        ld b, 8
mr1:    rr c
        rla
        djnz mr1
        ret
""" + TAIL


# ----------------------------------------------------------------- slow.asm
ZILOG = {"ld de,nn": 10, "dec de": 6, "ld a,d": 4, "or e": 4, "jr": 12, "jr_not": 7,
         "ld c,0": 7, "nop": 4, "call": 17, "ret": 10}      # Zilog's own table
SLOW_NOPS = 256


def zilog_wait(total):
    """the wait of listing 14.3 worked out from Zilog's table, as a book for
    another Z80 machine would: 26 a turn, 5 less for the last, 10 to load,
    and LD C,0 of 7 and NOPs of 4 to make up the rest"""
    turn = ZILOG["dec de"] + ZILOG["ld a,d"] + ZILOG["or e"] + ZILOG["jr"]
    for sevens in range(0, 8):
        for fours in range(0, 8):
            rest = (total - ZILOG["ld de,nn"] + (ZILOG["jr"] - ZILOG["jr_not"]) -
                    ZILOG["ld c,0"] * sevens - ZILOG["nop"] * fours)
            if rest > 0 and rest % turn == 0:
                return rest // turn, sevens, fours
    raise ValueError(total)


def slow():
    n, sevens, fours = zilog_wait(FRAME_T["MSXBOOK_EU16"])
    return head("slow", "a wait worked out from Zilog's table") + f"""; WHERE IT BREAKS. A wait of one 50 Hz frame, {FRAME_T['MSXBOOK_EU16']:,} T-states, worked out
; from Zilog's table: 10 for LD DE,nn, 26 a turn and 5 less for the last,
; 7 for LD C,0 and 4 for a NOP. Then 256 NOPs and a RET, called: 1,051 by
; the same table. meas14.py times both on the MSX.
init:   di
        ld sp, SYS_AREA
s1:     ld de, {n}
wz:     dec de
        ld a, d
        or e
        jr nz, wz
""" + "        ld c, 0\n" * sevens + "        nop\n" * fours + f"""s2:     call nops
s3:     nop
stop:   jr stop

nops:   DUP {SLOW_NOPS}                 ; sjasmplus writes the next line {SLOW_NOPS} times
        nop
        EDUP
        ret
""" + TAIL


def main():
    files = {"all.asm": all_(), "price.asm": price(), "budget.asm": budget(), "slow.asm": slow()}
    for name, text in files.items():
        with open(os.path.join(HERE, name), "w") as f:
            f.write("\n".join(l.rstrip() for l in text.split("\n")))    # no spaces at line ends
    print(len(files), "sources written")


if __name__ == "__main__":
    main()
