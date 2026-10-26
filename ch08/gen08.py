#!/usr/bin/env python3
"""gen08.py - the programs of chapter 8.

    python3 gen08.py && ./build.sh

    modes.asm      one LD of each addressing mode, and the sixteen-bit ones,
                   timed by the debugger (meas08.py). The data the loads
                   write is copied into the RAM first, to var: the cartridge
                   is ROM.
    sixteen.asm    EX DE,HL against LD H,D and LD L,E, and a sixteen-bit
                   store, low byte first.
    records.asm    five records of three bytes, an address in the VDP's name
                   table and a character, read through IX: the same
                   instructions print each as a bar (figure 8.1).
    selfmod.asm    the number in LD A,n is a byte of the program, and the
                   program changes it: in the cartridge nothing happens; the
                   same four lines copied into the RAM change themselves.
                   WHERE IT BREAKS.
    copy4.asm      one job four ways: the same eight bytes copied into the
                   RAM by direct, register indirect, indexed and immediate
                   loads. A new border colour before each way, so the bottom
                   border draws how long each took (figure 8.2).
    ldai.asm       LD A,I and LD A,R, on $80 and $00, with interrupts off and
                   on, each with every flag clear and with every flag set:
                   the two loads that set flags, and what they set.
    paren.asm      WHERE IT BREAKS: LD B,($C000) is not a load from memory.
                   Read through its listing; assembled without --syntax=b,
                   the way sjasmplus is set up unless told otherwise.

From this chapter on build.sh assembles with --syntax=bF: parentheses round a
whole operand mean memory, and sjasmplus's made-up instructions are refused
(chapter 7).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
from asmparts import HEAD, TAIL, TEXT_PAGE, SHOW_PAGE, BOX_FULL, BOXES  # noqa: E402

RESULTS = "RESULTS EQU RAM_START          ; what the program found: the debugger reads it here\n"


def head(name, what):
    return HEAD.format(name=name, chapter=8, what=what)


# ---------------------------------------------------------------- the clock
# Zilog's T-states plus one for every M1 (chapter 7), for the instructions of
# the loop of copy4.asm, which must know its own length (see copy4 below).
# meas08.py times the same loop with the debugger.
T_MSX = {"ld a,n": 8, "out (n),a": 12, "ld b,n": 8, "ld a,(nn)": 14, "ld (nn),a": 14,
         "djnz": 14, "djnz_last": 9, "ld de,nn": 11, "ld hl,nn": 11, "ld a,(de)": 8,
         "ld (hl),a": 8, "inc de": 7, "inc hl": 7, "ld ix,nn": 16, "ld a,(ix+d)": 21,
         "ld (hl),n": 11, "nop": 5, "ld a,(hl)": 8, "jr": 13, "halt": 5, "in a,(n)": 12,
         "ei": 5, "ret": 11, "jp nn": 11, "im2": 20}


# --------------------------------------------------------------- modes.asm
# (the instruction, the addressing mode it shows)
MODES = [
    ("ld a,b", "register"),
    ("ld a,$12", "immediate"),
    ("ld a,(hl)", "register indirect"),
    ("ld a,(bc)", "register indirect"),
    ("ld a,(var)", "direct"),
    ("ld a,(ix+2)", "indexed"),
    ("ld (hl),$12", "immediate to register indirect"),
    ("ld (ix+2),$12", "immediate to indexed"),
    ("ld hl,$1234", "immediate, 16 bits"),
    ("ld hl,(var)", "direct, 16 bits"),
    ("ld bc,(var)", "direct, 16 bits"),
    ("ld ix,(var)", "direct, 16 bits"),
    ("ld (var),hl", "direct, 16 bits"),
    ("ld sp,hl", "register, 16 bits"),
    ("ex de,hl", "exchange"),
    ("ld a,i", "register"),
]


def modes():
    body = "".join(f"t{k}:     {i:<24}; {m}\n" if k < 10 else f"t{k}:    {i:<24}; {m}\n"
                   for k, (i, m) in enumerate(MODES))
    return head("modes", "one load of each addressing mode") + f"""var     EQU RAM_START + $40     ; the RAM copy of value
; HL, BC and IX point at var; nothing uses the stack after the copy.
init:   di
        ld sp, SYS_AREA
        ld hl, (value)          ; value, from the cartridge ...
        ld (var), hl
        ld hl, (value + 2)
        ld (var + 2), hl        ; ... to var, in the RAM, which keeps a store
        ld hl, var
        ld bc, var
        ld ix, var
""" + body + f"""t{len(MODES)}:
stop:   jr stop

value:  dw $1234
        dw $5678
""" + TAIL


# ------------------------------------------------------------- sixteen.asm
def sixteen():
    return head("sixteen", "two pairs swapped, copied and stored") + """store   EQU RAM_START               ; two bytes of RAM
; There is no LD HL,DE. EX DE,HL swaps the two pairs; two LDs copy one into
; the other; LD (nn),HL stores low byte first.
init:   di
        ld sp, SYS_AREA
        ld hl, $1234
        ld de, $5678
        ex de, hl               ; HL = $5678, DE = $1234
p1:     ld h, d
        ld l, e                 ; HL = DE = $1234: a copy
p2:     ld (store), hl          ; $34 at store, $12 after it
p3:     jr p3
""" + TAIL


# ------------------------------------------------------------- records.asm
# (column, row, character): where each object is, and what it is drawn with
OBJECTS = [(3, 3, BOX_FULL), (20, 5, "#"), (9, 9, "X"), (25, 13, "="), (5, 17, "O")]
BAR = 3                     # cells in a bar


def char_of(c):
    return f"{c}" if isinstance(c, int) else f"'{c}'"


def records():
    data = "".join(f"""        dw {f"NAMES+{r}*32+{c}":<24}; object {k + 1}: its first cell
        db {char_of(ch):<24}; {"a filled box" if ch == BOX_FULL else "its character"}
""" for k, (c, r, ch) in enumerate(OBJECTS))
    outs = "".join("        out (VDP_DATA), a\n" for _ in range(BAR - 1)) + \
        f"        out (VDP_DATA), a       ; {BAR} cells: the VDP moves on by itself\n"
    return head("records", "five records read through IX") + """NAMES   EQU $1800                   ; the name table: one byte a cell
""" + TEXT_PAGE + f"""        ld ix, objects
        ld b, {len(OBJECTS)}
next:   ld a, (ix+0)            ; the address: low byte ...
        out (VDP_CTRL), a
        ld a, (ix+1)            ; ... and high byte,
        or $40                  ; with bit 6 set: a write
        out (VDP_CTRL), a
        ld a, (ix+2)            ; the character
""" + outs + """        inc ix
        inc ix
        inc ix                  ; IX to the next record
        djnz next               ; five times (chapter 11)
""" + SHOW_PAGE + """
objects:
""" + data + BOXES + TAIL


# ------------------------------------------------------------- selfmod.asm
SELF_A = 0x47


def selfmod():
    return head("selfmod", "a program that changes its own number") + RESULTS + f"""; The number in LD A,n is the byte after the opcode, and the program writes
; to it. Run in the cartridge, the write changes nothing; the same four lines
; copied into the RAM change themselves. WHERE IT BREAKS.
init:   di
        ld sp, SYS_AREA
        call inrom              ; the routine where the cartridge has it
        ld (RESULTS), a         ; what LD A,n loaded
        ld hl, copy             ; the same routine, copied into the RAM ...
        ld de, inram
        ld bc, copy_end - copy
        ldir                    ; (LDIR copies BC bytes: chapter 13)
        call inram              ; ... and run there
        ld (RESULTS + 1), a
stop:   jr stop

inrom:  ld a, ${SELF_A:02X}
        ld (rpatch + 1), a      ; the byte after the opcode, in the ROM
rpatch: ld a, $00               ; assembled as LD A,0
        ret

copy:                           ; the same lines, assembled to run at $C010
        DISP RAM_START + $10
inram:  ld a, ${SELF_A:02X}
        ld (mpatch + 1), a      ; the byte after the opcode, in the RAM
mpatch: ld a, $00               ; assembled as LD A,0
        ret
        ENT
copy_end:
""" + TAIL


# --------------------------------------------------------------- copy4.asm
GLYPH = [0b00011000, 0b00111100, 0b01100110, 0b11011011,
         0b11011011, 0b01100110, 0b00111100, 0b00011000]
BUFS = "RAM_START + $40"            # four copies of eight bytes
WAYS = [  # (label, the border colour while it runs)
    ("LD A,(nn)", "BLACK"),
    ("LD A,(DE)", "DARK_BLUE"),
    ("LD A,(IX+d)", "LIGHT_GREEN"),
    ("LD (HL),n", "BLACK"),
]
REPEAT = 4                  # each way runs four times in a row
# PAUSE: turns of a DJNZ loop between the interrupt and the first change of
# colour, so that every change falls well inside the columns the VDP draws
# (19-302, chapter 4): 185 T-states, worked out from a first capture without
# it, and checked by meas08.py on every change.
PAUSE = 13
# The loop keeps its place from frame to frame when the answer to the
# interrupt, the handler, the loop and the HALT add up to the frame, modulo
# the HALT's 5-T steps: chapter 1's rule (asmparts.steady). copy4() asserts
# it, and meas08.py checks five frames.
FRAME_T = 71364


def way_lines(k):
    buf = f"BUF{k + 1}"
    if k == 0:
        return "".join(f"""        ld a, (glyph+{i})
        ld ({buf}+{i}), a
""" for i in range(8)), ["ld a,(nn)", "ld (nn),a"] * 8
    if k == 1:
        return f"""        ld de, glyph
        ld hl, {buf}
""" + "".join("""        ld a, (de)
        ld (hl), a
        inc de
        inc hl
""" for _ in range(8)), ["ld de,nn", "ld hl,nn"] + ["ld a,(de)", "ld (hl),a", "inc de", "inc hl"] * 8
    if k == 2:
        return f"""        ld ix, glyph
        ld hl, {buf}
""" + "".join(f"""        ld a, (ix+{i})
        ld (hl), a
        inc hl
""" for i in range(8)), ["ld ix,nn", "ld hl,nn"] + ["ld a,(ix+d)", "ld (hl),a", "inc hl"] * 8
    return f"""        ld hl, {buf}
""" + "".join(f"""        ld (hl), %{GLYPH[i]:08b}
        inc hl
""" for i in range(8)), ["ld hl,nn"] + ["ld (hl),n", "inc hl"] * 8


def one_pass(k):
    return sum(T_MSX[i] for i in way_lines(k)[1])


def loop_t():
    """the T-states of the main loop from HALT's end to JR main, by the model"""
    vdp_reg = 2 * (T_MSX["ld a,n"] + T_MSX["out (n),a"])
    t = pause_t()
    for k in range(len(WAYS)):
        t += vdp_reg + T_MSX["ld b,n"] + REPEAT * one_pass(k) + \
            (REPEAT - 1) * T_MSX["djnz"] + T_MSX["djnz_last"]
    t += vdp_reg
    return t


def pause_t():
    return T_MSX["ld b,n"] + (PAUSE - 1) * T_MSX["djnz"] + T_MSX["djnz_last"]


def trip_t():
    """chapter 1's sum: the answer, the handler, the loop, JP main, HALT"""
    return T_MSX["im2"] + T_MSX["in a,(n)"] + T_MSX["ei"] + T_MSX["ret"] + loop_t() + \
        T_MSX["jp nn"] + T_MSX["halt"]


def copy4():
    ways = []
    for k, (label, colour) in enumerate(WAYS):
        body, _ = way_lines(k)
        ways.append(f"""col{k + 1}:   VDP_REG 7, {colour:<12}; way {k + 1}, {label}, starts
        ld b, {REPEAT}                ; {REPEAT} times, for a band long enough to see
way{k + 1}:
""" + body + f"""        djnz way{k + 1}               ; B - 1, and again until B is 0 (chapter 11)
""")
    bufs = "".join(f"BUF{k + 1}    EQU {BUFS} + {8 * k}\n" for k in range(4))
    assert trip_t() % 5 == FRAME_T % 5, trip_t()
    delay = f"""        ld b, {PAUSE}                ; a pause: every change of colour falls
pause:  djnz pause              ; in the columns the VDP draws (gen08.py)
"""
    return head("copy4", "one job, four ways") + bufs + """IM2_TABLE EQU $C100             ; 257 bytes of $C2: the interrupt vector is $C2C2
IM2_JUMP  EQU $C2C2
; The same eight bytes copied into the RAM four ways. Each way starts by
; changing the border colour and runs four times, so the bottom border draws
; how long each takes: figure 8.2.
""" + TEXT_PAGE + """        ld hl, IM2_TABLE        ; an interrupt of our own (chapter 17)
        ld (hl), $C2
        ld de, IM2_TABLE + 1
        ld bc, 256
        ldir
        ld a, $C3               ; JP handler, at $C2C2
        ld (IM2_JUMP), a
        ld hl, handler
        ld (IM2_JUMP + 1), hl
        ld a, high IM2_TABLE
        ld i, a
        im 2
        VDP_REG 1, $E0          ; display on, frame interrupt on
        ei
main:   halt                    ; the frame interrupt: the beam leaves the paper
""" + delay + "".join(ways) + f"""col{len(WAYS) + 1}:   VDP_REG 7, WHITE        ; all four done
        jp main                 ; too far back for JR

handler:
        in a, (VDP_CTRL)        ; reading the status answers the interrupt
        ei
        ret

glyph:  db """ + ", ".join(f"%{g:08b}" for g in GLYPH) + "\n" + BOXES + TAIL


# ---------------------------------------------------------------- ldai.asm
# (the register read, the value put in it, interrupts on, F before)
LDAI_TESTS = [(reg, v, ei, f) for reg in ("i", "r") for v in (0x80, 0x00)
              for ei in (0, 1) for f in (0x00, 0xFF)]


def ldai():
    body = []
    for k, (reg, v, ei, f) in enumerate(LDAI_TESTS):
        body.append(f"""        ld a, ${v:02X}
        ld {reg}, a                 ; {reg.upper()} = ${v:02X}
        {'ei' if ei else 'di'}                      ; interrupts {'on' if ei else 'off'}
        ld bc, ${f:02X}
        push bc
        pop af                  ; F = ${f:02X}
        ld a, {reg}
        push af
        pop hl
        {f'ld (RESULTS+{2 * k}), hl':<24}; F, then A
""")
    return head("ldai", "the two loads that set flags") + RESULTS + """; LD A,I and LD A,R, with $80 and $00 put in I or R, interrupts off and on,
; and F clear and set before each load. What F and A became goes into the
; RAM, two bytes a test. The frame interrupt comes first, so that no other
; comes in the middle and moves R on.
init:   di
        ld sp, SYS_AREA
        im 1
        ei
        halt                    ; the frame interrupt, and C-BIOS's routine
""" + "".join(body) + """        di
        xor a
        ld i, a                 ; I as C-BIOS had it
stop:   jr stop
""" + TAIL


# --------------------------------------------------------------- paren.asm
PAREN = """; paren.asm - WHERE IT BREAKS. Only LD A loads from an address in the
; instruction. Written for B, the parentheses are just parentheses:
; sjasmplus reads ($C000) as the number $C000, and ($C0) as $C0.
        OUTPUT "paren.bin"
        ORG $4000
        ld a,($C000)            ; the byte at $C000
        ld b,($C000)            ; $00, low byte of $C000
        ld b,($C0)              ; $C0, and not a word
"""


def sources():
    return {"modes.asm": modes(), "sixteen.asm": sixteen(), "records.asm": records(),
            "selfmod.asm": selfmod(), "copy4.asm": copy4(), "ldai.asm": ldai(),
            "paren.asm": PAREN}


CARTS = ["modes", "sixteen", "records", "selfmod", "copy4", "ldai"]


def main():
    files = sources()
    for name, text in files.items():
        with open(os.path.join(HERE, name), "w") as f:
            f.write(text)
    print(len(files), "sources written; copy4's loop:", loop_t(), "T by the model")


if __name__ == "__main__":
    main()
