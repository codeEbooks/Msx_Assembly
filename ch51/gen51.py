#!/usr/bin/env python3
"""gen51.py - the programs of chapter 51: one cartridge, many machines.

    python3 gen51.py && ./build.sh

    which.asm   a cartridge that asks the machine it is in what it is, and
                writes the answers on a page: the BIOS's three bytes at
                $002B-$002D, the frame measured in turns of 57 T-states, the
                VDP (asked only on an MSX2 or later), the PSG (register 1
                read back), the slot of the RAM in page 3 and BOTTOM, how
                many of 64 bytes reach the VRAM at 18, 23, 25 and 29
                T-states a byte in the paper's lines, the characters the
                BIOS makes of seven keys, and a strip of the fifteen colours
    blind.asm   WHERE IT BREAKS: which.asm without the look at $002D before
                the VDP is asked: S#1 is read on every machine

The page is drawn in Graphic I with the BIOS's own character set, so that each
machine writes in its own letters. The variables are at $E000, above the 8 KB
machine's floor, so that every machine of the book runs the cartridge.
build.sh assembles with --syntax=bFw.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
for ch in ("tools", "ch26"):
    sys.path.insert(0, os.path.join(REPO, ch))
from asmparts import HEAD, CART_END, TEXT_PAGE, library, PUTDEC, PUTD16  # noqa: E402
from gen26 import tidy  # noqa: E402  (chapter 26)

VARS_AT = 0xE000                # the 8 KB machine has RAM from $E000 (chapter 3)
TURN = 57                       # the frame's loop: four turns a line
VRAM_AT = 0x3C00                # four rows of 64 bytes, in sprite patterns no sprite uses
N_BYTES = 64
SPEEDS = [18, 23, 25, 29]       # T-states a byte of the four loops
DELAY = {313: 1217, 262: 830}   # 30-T turns from the flag to the paper's 40th line (chapter 20)
KEYS = [(1, 3), (1, 4), (1, 5), (1, 6), (1, 7), (2, 0), (2, 1)]   # (row, column) of the matrix
KEY_FIRST, KEY_EVERY, KEY_HELD = 24, 12, 6      # frames from INIT: the keys meas51.py presses
WIDTH = 30                      # the page's columns 1-30: what figure 51.2 shows
ROWS = 13                       # and its rows 0-12

MSX_NAMES = ["MSX1", "MSX2", "MSX2+", "turbo R"]
KEYBOARD_NAMES = ["Japanese", "international", "French", "UK", "German"]

# where each answer is written: (row, column)
AT = {"title": (0, 1), "bios": (2, 1), "board": (3, 1), "frame": (4, 1), "vdp": (5, 1),
      "psg": (6, 1), "ram": (7, 1), "from": (8, 1), "vram": (9, 1), "kept": (10, 1),
      "keys": (11, 1), "strip": (12, 1)}
LABELS = {"title": "WHICH MSX IS THIS?", "bios": "BIOS", "board": "keyboard", "frame": "frame",
          "vdp": "VDP", "psg": "PSG", "ram": "RAM  page 3 in slot", "from": "     from $",
          "vram": "VRAM" + "".join(f" {t} T" for t in SPEEDS), "kept": "kept", "keys": "keys"}


def head(name, what):
    text = HEAD.format(name=name, chapter=51, what=what)
    old = "VARS    EQU RAM_START + $100    ; the program's variables: the code is in ROM\n"
    assert old in text
    return text.replace(old, f"VARS    EQU ${VARS_AT:04X}           ; the variables: above the 8 KB "
                             "machine's floor\n")


EQUS = f"""        INCLUDE "bios.inc"
BOTTOM  EQU $FC48               ; the BIOS: the lowest address of the RAM
idb     EQU VARS + $10          ; the BIOS's bytes at $002B, $002C, $002D
psgr    EQU VARS + $13          ; PSG register 1, read back
slotp   EQU VARS + $14          ; page 3's primary slot
slots   EQU VARS + $15          ; and its secondary one, or $FF
turns   EQU VARS + $16          ; the frame, in turns of {TURN} T-states
lines   EQU VARS + $18          ; and in lines
s1      EQU VARS + $1A          ; S#1 as the VDP gave it, or $FF if not asked
kept    EQU VARS + $1B          ; the bytes each loop got into the VRAM: 4
delay   EQU VARS + $20          ; 30-T turns from the flag to the paper's line 40
keybuf  EQU VARS + $22          ; the characters of the keys, and a 0
"""

# the page is drawn with the display off: the strip's shapes and colours, the
# 256 bytes the loops write to, all $FF, and the labels
DRAW = f"""        ld b, 15                ; the strip: characters 136, 144 ... 248 solid
        ld de, $0400 + 64       ; the shape of character 136: 8 x 136
strip:  ld a, e
        out (VDP_CTRL), a
        ld a, d
        or $40
        out (VDP_CTRL), a
        ld a, $FF
        ld c, 8
.row:   out (VDP_DATA), a
        dec c
        jr nz, .row
        ld hl, 64
        add hl, de
        ex de, hl               ; the next one: 8 characters on
        djnz strip
        VRAM_WRITE $2011        ; colour entries 17-31: ink and paper both k
        ld a, $11
.paint: out (VDP_DATA), a
        add a, $11
        jr nc, .paint           ; $11, $22 ... $FF
        VRAM_WRITE ${VRAM_AT:04X}        ; where the loops write: 256 bytes of $FF
        ld b, 0
        ld a, $FF
.fill:  out (VDP_DATA), a
        djnz .fill
""" + "".join(f"""        ld b, {AT[k][0]}
        ld c, {AT[k][1]}
        ld hl, l_{k}
        call puts
""" for k in LABELS)

# ---------------------------------------------------------------- what the BIOS says
ASK_BIOS = """askbios: ld hl, $002B            ; the BIOS's ID bytes, in the ROM of slot 0
        ld de, idb
        ld bc, 3
        ldir
"""

ASK_PSG = """askpsg: ld a, 1
        out (PSG_ADDR), a       ; register 1: the top four bits of tone A
        ld a, $FF
        out (PSG_WRITE), a
        in a, (PSG_READ)        ; a YM2149 keeps all eight, an AY-3-8910 four
        ld (psgr), a
        xor a
        out (PSG_WRITE), a      ; and 0 again
"""

ASK_RAM = """askram: in a, (PPI_A)           ; the primary slots of the four pages
        rlca
        rlca
        and 3                   ; bits 7-6: page 3's
        ld (slotp), a
        ld e, a
        ld d, 0
        ld hl, EXPTBL
        add hl, de
        ld a, (hl)              ; bit 7: that slot is expanded
        rla
        ld a, $FF               ; not expanded: no secondary slot
        jr nc, .flat
        ld a, ($FFFF)           ; the secondary slot register, complemented
        cpl
        rlca
        rlca
        and 3                   ; bits 7-6: page 3's secondary slot
.flat:  ld (slots), a
"""

# ---------------------------------------------------------------- what the machine says
FRAME = f"""frame:  VDP_REG 1, $C0          ; display on, the frame's interrupt off
        ld de, 0                ; DE: the turns
        in a, (VDP_CTRL)        ; the flag cleared
.sync:  in a, (VDP_CTRL)        ; 12
        and a                   ;  5
        jp p, .sync             ; 11  until the flag is up: a frame begins
.turn:  in a, (VDP_CTRL)        ; 12  the status: bit 7 is the flag
        and a                   ;  5
        jp m, .up               ; 11  up again: a frame has gone by
        inc de                  ;  7
        jp .wait                ; 11
.wait:  jp .turn                ; 11  a turn of {TURN}: four to a line
.up:    ld (turns), de
        srl d
        rr e
        srl d
        rr e                    ; / 4: lines
        ld (lines), de
        ld hl, (turns)
        ld de, -1150
        add hl, de              ; carry: 1,150 turns or more, 313 lines
        ld hl, {DELAY[313]}              ; 313 lines: the paper's 40th line is 160 lines on
        jr c, .fifty
        ld hl, {DELAY[262]}               ; 262 lines: 109 lines on
.fifty: ld (delay), hl
"""

ASK_VDP = """askvdp: ld a, (idb + 2)         ; $002D: 0 on an MSX1, whose VDP has no S#1
        or a
        ld a, $FF
        jr z, .msx1             ; not asked
"""
ASK_VDP_TAIL = """        VDP_REG 15, 1           ; the status register to read: S#1
        in a, (VDP_CTRL)        ; S#1: bits 5-1 are the chip's ID
        ld b, a
        VDP_REG 15, 0           ; S#0 again, which the BIOS reads
        ld a, b
.msx1:  ld (s1), a
"""

PAPER40 = """
; paper40: waits for the frame's flag, then for the paper's 40th line
paper40:
        in a, (VDP_CTRL)        ; the flag cleared
.sync:  in a, (VDP_CTRL)
        and a
        jp p, .sync
        ld bc, (delay)
.wait:  dec bc                  ;  7
        ld a, b                 ;  5
        or c                    ;  5
        jr nz, .wait            ; 13: 30 a turn
        ret
"""


def loops():
    a = VRAM_AT
    out = f"""vram:   call paper40
        VRAM_WRITE ${a:04X}
        ld hl, bytes
        ld c, VDP_DATA
        DUP {N_BYTES}
        outi                    ; 18 a byte
        EDUP
        call paper40
        VRAM_WRITE ${a + N_BYTES:04X}
        ld hl, bytes
        ld bc, {N_BYTES} << 8 | VDP_DATA
        otir                    ; 23 a byte, 18 the last
        call paper40
        VRAM_WRITE ${a + 2 * N_BYTES:04X}
        ld hl, bytes
        DUP {N_BYTES}
        ld a, (hl)              ;  8
        inc l                   ;  5
        out (VDP_DATA), a       ; 12: 25 a byte
        EDUP
        call paper40
        VRAM_WRITE ${a + 3 * N_BYTES:04X}
        ld hl, bytes
        ld bc, {N_BYTES} << 8 | VDP_DATA
.o29:   outi                    ; 18
        jp nz, .o29             ; 11: 29 a byte
"""
    return out


COUNT = f"""count:  ld a, low ${VRAM_AT:04X}         ; the four rows read back: a byte that came
        out (VDP_CTRL), a       ; is no longer $FF
        ld a, high ${VRAM_AT:04X}        ; bit 6 clear: an address to read from
        out (VDP_CTRL), a
        ld hl, kept
        ld c, 4
.loop:  ld b, {N_BYTES}
        ld e, 0
.byte:  in a, (VDP_DATA)        ; 12
        inc a                   ;  5  $FF becomes 0
        jr z, .gone             ;  8 / 13
        inc e                   ;  5
.gone:  djnz .byte              ; 14: 44 a byte, either way
        ld (hl), e
        inc hl
        dec c
        jr nz, .loop
"""

ASK_KEYS = f"""askkeys: ld a, 1
        ld (SCNCNT), a          ; the BIOS looks at the keys at the next interrupt
        VDP_REG 1, $E0          ; the frame's interrupt on: the BIOS reads keys
        im 1
        ei
        ld hl, keybuf
        ld b, {len(KEYS)}
.key:   push hl
        push bc
        call CHGET              ; the BIOS's character for the next key pressed
        pop bc
        pop hl
        ld (hl), a
        inc hl
        djnz .key
        ld (hl), 0
        di
        VDP_REG 1, $C0          ; and off again
"""

# ---------------------------------------------------------------- the answers, written
def col_after(k):
    """the column just after label K"""
    return AT[k][1] + len(LABELS[k])


SHOW = f"""show:   ld b, {AT['bios'][0]}
        ld c, {col_after('bios') + 1}
        ld hl, idb
        ld e, 3
.hex:   ld a, (hl)
        call puthex
        inc c
        inc hl
        dec e
        jr nz, .hex
        dec c
        ld a, ':'
        call putc
        inc c
        inc c
        ld a, (idb + 2)         ; $002D: the version
        cp 4
        jr c, .ver
        ld a, 4
.ver:   ld hl, msx_names
        call pick
        call puts
        ld hl, l_comma
        call puts
        ld hl, l_60
        ld a, (idb)             ; $002B bit 7: 50 Hz
        rla
        jr nc, .hz
        ld hl, l_50
.hz:    call puts
        ld b, {AT['board'][0]}
        ld c, {col_after('board') + 1}
        ld a, (idb + 1)         ; $002C bits 3-0: the keyboard
        and $0F
        cp 5
        jr c, .kb
        ld a, 5
.kb:    ld hl, board_names
        call pick
        call puts
        ld b, {AT['frame'][0]}
        ld c, {col_after('frame')}
        ld hl, (turns)
        call putd16
        ld hl, l_turn
        call puts
        ld hl, (lines)
        call putd16
        ld hl, l_lines
        call puts
        ld b, {AT['vdp'][0]}
        ld c, {col_after('vdp') + 2}
        ld a, (s1)
        cp $FF
        jr nz, .v99             ; asked: a V99x8
        ld hl, l_9929           ; not asked: a TMS99x8, 50 or 60 Hz
        ld de, (lines)
        ld a, e
        cp low 313
        jr z, .tms
        ld hl, l_9918
.tms:   call puts
        jr .vdpok
.v99:   rrca
        and $1F                 ; bits 5-1: the ID
        ld e, a
        ld hl, l_9938
        or a
        jr z, .id
        ld hl, l_9958
        cp 2
        jr z, .id
        ld hl, l_99x8
.id:    call puts
        ld hl, l_s1
        call puts
        ld a, e
        call putdec
.vdpok: ld b, {AT['psg'][0]}
        ld c, {col_after('psg') + 2}
        ld a, (psgr)
        ld hl, l_ym
        cp $FF
        jr z, .chip
        ld hl, l_ay
        cp $0F
        jr z, .chip
        ld hl, l_unknown
.chip:  push af
        call puts
        ld hl, l_reads
        call puts
        pop af
        call puthex
        ld b, {AT['ram'][0]}
        ld c, {col_after('ram') + 1}
        ld a, (slotp)
        add a, '0'
        call putc
        inc c
        ld a, (slots)
        cp $FF
        jr z, .one
        ld a, '-'
        call putc
        inc c
        ld a, (slots)
        add a, '0'
        call putc
.one:   ld b, {AT['from'][0]}
        ld c, {col_after('from')}
        ld a, (BOTTOM + 1)
        call puthex
        ld a, (BOTTOM)
        call puthex
        ld b, {AT['kept'][0]}
        ld c, {AT['vram'][1] + 6}
        ld hl, kept
        ld e, 4
.kept:  ld a, (hl)
        push de
        push hl
        call putdec
        pop hl
        pop de
        inc c
        inc c
        inc hl
        dec e
        jr nz, .kept
        ld b, {AT['keys'][0]}
        ld c, {col_after('keys') + 1}
        ld hl, keybuf
        call puts
        ld b, {AT['strip'][0]}
        ld c, {AT['strip'][1]}
        ld a, 136
.strip: call putc
        inc c
        inc c
        add a, 8
        jr nz, .strip           ; 136 ... 248: the colours 1 to 15
done:   jr done

; pick: A = n -> HL = the n-th text of the list at HL (texts end in 0)
pick:   or a
        ret z
        ld e, a
.skip:  ld a, (hl)
        inc hl
        or a
        jr nz, .skip
        dec e
        jr nz, .skip
        ret
"""


def texts():
    out = []
    for k, s in LABELS.items():
        assert AT[k][1] + len(s) <= 1 + WIDTH, k
        out.append(f'l_{k}: db "{s}", 0')
    out += ['l_comma: db ", ", 0', 'l_50: db "50 Hz", 0', 'l_60: db "60 Hz", 0',
            f'l_turn: db " x {TURN} T:", 0', 'l_lines: db " lines", 0',
            'l_9929: db "TMS9929A", 0', 'l_9918: db "TMS9918A/28A", 0',
            'l_9938: db "V9938", 0', 'l_9958: db "V9958", 0', 'l_99x8: db "V99x8", 0',
            'l_s1: db ", S#1 ID", 0',
            'l_ym: db "YM2149", 0', 'l_ay: db "AY-3-8910", 0', 'l_unknown: db "?", 0',
            'l_reads: db ", R1 reads ", 0']
    for label, names in (("msx_names", MSX_NAMES), ("board_names", KEYBOARD_NAMES)):
        out.append(f"{label}:")                 # the texts pick chooses from, and "?"
        out += [f'        db "{n}", 0' for n in names + ["?"]]
    out.append("        ALIGN 256")
    out.append("bytes:                          ; the loops' 64 bytes: 0 to 63")
    out += ["        db " + ", ".join(str(i) for i in range(k, k + 16)) for k in range(0, N_BYTES, 16)]
    return "\n".join(out) + "\n"


SAY = {
    "which": """; One cartridge, many machines. The cartridge asks the machine it is in what it
; is, the BIOS first and then the chips, and writes the answers on the page.
""",
    "blind": """; WHERE IT BREAKS. which.asm without its look at $002D: the VDP is asked for S#1
; on every machine, the MSX1s too, whose VDP has no S#1 and no register 15.
""",
}
WHAT = {"which": "which MSX is this?", "blind": "the VDP asked without looking"}


def program(name):
    ask_vdp = (ASK_VDP if name == "which" else "") + ASK_VDP_TAIL
    if name == "blind":
        ask_vdp = "askvdp:" + ask_vdp[len("askvdp:"):].replace(".msx1:  ld (s1), a", "        ld (s1), a")
    body = (TEXT_PAGE + DRAW + ASK_BIOS + ASK_PSG + ASK_RAM + FRAME + ask_vdp + loops() + COUNT +
            ASK_KEYS + SHOW + PAPER40 + library(PUTDEC, PUTD16) + texts())
    return head(name, WHAT[name]) + EQUS + SAY[name] + tidy(body) + CART_END


PROGRAMS = ["which", "blind"]


def variant(kind):
    """the workshop's programs: w26.asm, which.asm whose third loop writes a
    byte every 26 T-states (OUTI, then an LD A,(HL) that does nothing); and
    noscan.asm, which.asm without the two lines that set SCNCNT"""
    src = program("which")
    if kind == "w26":
        old = "        ld a, (hl)              ;  8\n        inc l                   ;  5\n" \
              "        out (VDP_DATA), a       ; 12: 25 a byte\n"
        assert src.count(old) == 1
        src = src.replace(old, "        outi                    ; 18\n"
                               "        ld a, (hl)              ;  8: 26 a byte, A unused\n")
        old = "        ld hl, bytes\n        DUP 64\n        outi"
        assert src.count(old) == 1                  # the third loop, OUTI now: C is the port
        src = src.replace(old, "        ld hl, bytes\n        ld c, VDP_DATA\n        DUP 64\n        outi")
        old = 'l_vram: db "VRAM 18 T 23 T 25 T 29 T", 0'
        assert src.count(old) == 1
        src = src.replace(old, 'l_vram: db "VRAM 18 T 23 T 26 T 29 T", 0')
        what = "the third loop at 26 T-states a byte"
    elif kind == "noscan":
        old = "askkeys: ld a, 1\n        ld (SCNCNT), a          ; the BIOS looks at the keys at the next interrupt\n" \
              "        VDP_REG 1, $E0"
        assert src.count(old) == 1
        src = src.replace(old, "askkeys: VDP_REG 1, $E0")
        what = "SCNCNT left as the BIOS left it"
    else:
        raise ValueError(kind)
    first_line = src.splitlines()[0]
    src = src.replace(first_line, f"; {kind}.asm -- chapter 51: {what}", 1)
    src = src.replace('OUTPUT "which.rom"', f'OUTPUT "{kind}.rom"')
    return kind, src


def main():
    for name in PROGRAMS:
        with open(os.path.join(HERE, f"{name}.asm"), "w") as f:
            f.write(program(name))
    print(" ".join(f"{n}.asm" for n in PROGRAMS))


if __name__ == "__main__":
    main()
