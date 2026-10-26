#!/usr/bin/env python3
"""gen53.py - the programs of chapter 53: a picture packed, and unpacked
straight into the VRAM.

    python3 gen53.py && ./build.sh

The picture is pic53.py's, THE KEEP AT NIGHT, a whole screen of Graphic II:
6,144 bytes of patterns and 6,144 of colours. pack53.py packs each half in
three ways. Each program below sets Graphic II with the display off, the
names 0 to 255 in each third, the patterns clear and the colours white on
black, switches the display on, and then, from go, with the interrupts off,
writes the patterns and then the colours while the VDP draws, so that the
picture is seen as it arrives: first the patterns, white, then the colours.

    raw.asm     the picture as it is, 12,288 bytes, sent at 29 T-states a
                byte, OUTI and JP NZ: the yardstick
    rlem.asm    runs with a marker: every byte looked at, 51 T-states a byte
                that stands for itself, 30 a byte of a run
    rlec.asm    runs and counts: 29 T-states a byte as it is, OUTI and JP
                NZ, and 30 a byte of a run, OUT (C),A, DEC B and JP NZ
    lz.asm      copies: 29 T-states a byte as it is; a copy, from 1 to 256
                bytes back, read back from the VRAM into a page of the RAM
                with INI, then written again with OUTI, 29 T-states a byte
                each way
    lzram.asm   the same packed bytes, each half unpacked into 6,144 bytes
                of the RAM with LDIR, then sent at 29 T-states a byte
    otir.asm    WHERE IT BREAKS: rlec.asm with the bytes as they are sent
                by OTIR, 23 T-states a byte, while the VDP draws
    dark.asm    otir.asm with the display off until the picture is whole

Labels go, half and whole mark where the patterns start, where the colours
start and where the picture is whole, for meas53.py's debugger and walk.py.
build.sh assembles with --syntax=bFw.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
for ch in ("tools", "ch26"):
    sys.path.insert(0, os.path.join(REPO, ch))
from asmparts import HEAD, CART_END  # noqa: E402
from gen26 import tidy, db_rows  # noqa: E402  (chapter 26)
sys.path.insert(0, HERE)
import pic53  # noqa: E402
import pack53  # noqa: E402

EU, JP = "MSXBOOK_EU16", "MSXBOOK_JP16"
MACHINES = [EU, JP]
PROGRAMS = ["raw", "rlem", "rlec", "lz", "lzram", "otir", "dark"]
BROKEN = "otir"
FORMAT = {"raw": None, "rlem": "rlem", "rlec": "rlec", "lz": "lz", "lzram": "lz",
          "otir": "rlec", "dark": "rlec"}
HALVES = {"patterns": (0x0000, pic53.PATTERNS), "colours": (0x2000, pic53.COLOURS)}
START_COLOUR = pic53.WHITE << 4 | pic53.BLACK   # the colours before: white on black
BUFFER = 0xC200                         # lz.asm: a copy's bytes, a page of their own
RAMPIC = 0xC200                         # lzram.asm: a half of the picture, 6,144 bytes
PAGES = 24                              # 6,144 bytes: 24 pages of 256

WHAT = {"raw": "the picture as it is, sent at 29 T-states",
        "rlem": "runs with a marker, unpacked into the VRAM",
        "rlec": "runs and counts, unpacked into the VRAM",
        "lz": "copies read back from the VRAM",
        "lzram": "copies unpacked in the RAM, then sent",
        "otir": "WHERE IT BREAKS: OTIR while the VDP draws",
        "dark": "OTIR with the display off"}


def packed(fmt, half):
    data = list(HALVES[half][1])
    return data if fmt is None else pack53.PACKERS[fmt][0](data)


INIT = f"""init:   di
        ld sp, SYS_AREA
        VDP_REG 1, $80          ; the display off while the tables are set
        VDP_REG 0, $02          ; Graphic II (chapter 22)
        VDP_REG 2, $06          ; names              $1800
        VDP_REG 3, $FF          ; colours            $2000, 6,144 bytes
        VDP_REG 4, $03          ; patterns           $0000, 6,144 bytes
        VDP_REG 5, $36          ; sprite attributes  $1B00
        VDP_REG 6, $07          ; sprite patterns    $3800
        VDP_REG 7, BLACK        ; the border black
        VRAM_WRITE $0000        ; the patterns clear
        xor a
        ld d, {PAGES}
        call fill
        VRAM_WRITE $2000        ; the colours white on black
        ld a, WHITE << 4 | BLACK
        ld d, {PAGES}
        call fill
        VRAM_WRITE $1800        ; the names: 0 to 255 in each third
        ld d, 3
        xor a
names:  out (VDP_DATA), a
        inc a
        jr nz, names
        dec d
        jr nz, names
        VRAM_WRITE $1B00        ; no sprites
        ld a, $D0
        out (VDP_DATA), a
"""

ON = """        VDP_REG 1, $C0          ; the display on: the screen black
"""

FILL = """
; fill: A = a byte, D = pages of 256 -> D pages of it at the VDP's write
; address, 26 T-states a byte: for the display off only. Uses B, D
fill:   ld b, 0                 ;  8
.byte:  out (VDP_DATA), a       ; 12
        djnz .byte              ; 14, or 9
        dec d                   ;  5
        jr nz, .byte            ; 13, or 8
        ret                     ; 11
"""

SEND = """
; send: HL = bytes, D = pages of 256 -> sent to the VDP's write address at
; 29 T-states a byte, OUTI and JP NZ. Uses BC, D, HL
send:   ld c, VDP_DATA          ;  8
        ld b, 0                 ;  8  256 bytes a page
.byte:  outi                    ; 18
        jp nz, .byte            ; 11  29 T-states a byte
        dec d                   ;  5
        jp nz, .byte            ; 11
        ret                     ; 11
"""

UNRLEM = """
; unrlem: HL = packed bytes, runs with a marker -> unpacked to the VDP's
; write address, 29 T-states a byte or more. The first byte is the marker;
; after it, a byte is itself, but the marker, count, byte is a run of count
; bytes, and the marker, 0 is the end. Uses A, BC, E, HL
unrlem: ld e, (hl)              ;  8  E: the marker
        inc hl                  ;  7
        ld c, VDP_DATA          ;  8
.next:  ld a, (hl)              ;  8  a byte
        inc hl                  ;  7
        cp e                    ;  5
        jr z, .run              ; 13, or 8  the marker: a run
        out (VDP_DATA), a       ; 12  any other: itself
        jp .next                ; 11  51 T-states a byte
.run:   ld a, (hl)              ;  8  the count
        inc hl                  ;  7
        or a                    ;  5
        ret z                   ; 12, or 6  0: the end
        ld b, a                 ;  5
        ld a, (hl)              ;  8  the byte
        inc hl                  ;  7
.out:   out (c), a              ; 14
        dec b                   ;  5
        jp nz, .out             ; 11  30 T-states a byte
        jp .next                ; 11
"""

UNRLEC = """
; unrlec: HL = packed bytes, runs and counts -> unpacked to the VDP's write
; address, 29 T-states a byte or more. A count, then: 1 to 127, that many
; bytes as they are; 128 to 255, one byte, (count - 128) + 3 times; 0, the
; end. Uses A, BC, HL
unrlec: ld c, VDP_DATA          ;  8
.next:  ld a, (hl)              ;  8  a count
        inc hl                  ;  7
        or a                    ;  5
        ret z                   ; 12, or 6  0: the end
        jp m, .run              ; 11  128 to 255: a run
        ld b, a                 ;  5  1 to 127: bytes as they are
.lit:   outi                    ; 18
        jp nz, .lit             ; 11  29 T-states a byte
        jp .next                ; 11
.run:   sub 128 - 3             ;  8  its length, 3 to 130
        ld b, a                 ;  5
        ld a, (hl)              ;  8  its byte
        inc hl                  ;  7
.out:   out (c), a              ; 14
        dec b                   ;  5
        jp nz, .out             ; 11  30 T-states a byte
        jp .next                ; 11
"""

UNRLEC_OTIR = UNRLEC.replace(
    """; unrlec: HL = packed bytes, runs and counts -> unpacked to the VDP's write
; address, 29 T-states a byte or more. A count""",
    """; unrlec: HL = packed bytes, runs and counts -> unpacked to the VDP's write
; address; the bytes as they are by OTIR, 23 T-states a byte. A count""").replace(
    """        ld b, a                 ;  5  1 to 127: bytes as they are
.lit:   outi                    ; 18
        jp nz, .lit             ; 11  29 T-states a byte
""", """        ld b, a                 ;  5  1 to 127: bytes as they are
        otir                    ; 23 a byte, 18 the last
""")
assert UNRLEC_OTIR.count("otir") == 1 and "OTIR, 23" in UNRLEC_OTIR

UNLZ = f"""
; unlz: HL = packed bytes, copies; DE = the VRAM address they unpack to ->
; unpacked there, 29 T-states a byte or more. A count, then: 1 to 127, that
; many bytes as they are; 128 to 255, a byte, a distance back less one, and
; (count - 128) + 3 bytes copied from 1 to 256 bytes back, never more than
; the distance: read from the VRAM into a page of the RAM, then written
; again; 0, the end. Uses A, BC, DE, HL
unlz:   ld c, VDP_DATA          ;  8
        ld a, e                 ;  5  the VDP's write address: DE
        out (VDP_CTRL), a       ; 12
        ld a, d                 ;  5
        or $40                  ;  8
        out (VDP_CTRL), a       ; 12
.next:  ld a, (hl)              ;  8  a count
        inc hl                  ;  7
        or a                    ;  5
        ret z                   ; 12, or 6  0: the end
        jp m, .copy             ; 11  128 to 255: a copy
        ld b, a                 ;  5  1 to 127: bytes as they are
        add a, e                ;  5  DE: on past them
        ld e, a                 ;  5
        jr nc, .lit             ; 13, or 8
        inc d                   ;  5
.lit:   outi                    ; 18
        jp nz, .lit             ; 11  29 T-states a byte
        jp .next                ; 11
.copy:  sub 128 - 3             ;  8  its length, 3 to 130
        ld b, a                 ;  5
        ld a, e                 ;  5  the VDP's read address: DE less
        scf                     ;  5  the byte, and one more
        sbc a, (hl)             ;  8
        inc hl                  ;  7
        out (VDP_CTRL), a       ; 12
        ld a, d                 ;  5
        sbc a, 0                ;  8
        out (VDP_CTRL), a       ; 12  bit 6 clear: a read; the VDP reads ahead
        push hl                 ; 12
        ld hl, BUFFER           ; 11  a page of its own: L counts the bytes
.in:    ini                     ; 18
        jp nz, .in              ; 11  29 T-states a byte
        ld b, l                 ;  5  B: the length again
        ld l, 0                 ;  8
        ld a, e                 ;  5  the write address again
        out (VDP_CTRL), a       ; 12
        ld a, d                 ;  5
        or $40                  ;  8
        out (VDP_CTRL), a       ; 12
.out:   outi                    ; 18
        jp nz, .out             ; 11  29 T-states a byte
        ld a, l                 ;  5  the length
        pop hl                  ; 11
        add a, e                ;  5  DE: on past the copy
        ld e, a                 ;  5
        jp nc, .next            ; 11
        inc d                   ;  5
        jp .next                ; 11
"""

UNLZR = """
; unlzr: HL = packed bytes, copies; DE = where in the RAM -> unpacked
; there by LDIR, the copies too. Uses A, BC, DE, HL
unlzr:  ld a, (hl)              ;  8  a count
        inc hl                  ;  7
        or a                    ;  5
        ret z                   ; 12, or 6  0: the end
        jp m, .copy             ; 11  128 to 255: a copy
        ld c, a                 ;  5  1 to 127: bytes as they are
        ld b, 0                 ;  8
        ldir                    ; 23 a byte, 18 the last
        jp unlzr                ; 11
.copy:  sub 128 - 3             ;  8  its length, 3 to 130
        ld c, a                 ;  5
        ld a, e                 ;  5  DE less the byte, and one more
        scf                     ;  5
        sbc a, (hl)             ;  8
        inc hl                  ;  7
        push hl                 ; 12
        ld l, a                 ;  5
        ld a, d                 ;  5
        sbc a, 0                ;  8
        ld h, a                 ;  5  HL: where the copy is
        ld b, 0                 ;  8  BC: its length
        ldir                    ; 23 a byte, 18 the last
        pop hl                  ; 11
        jp unlzr                ; 11
"""


def go(name):
    """from go to whole: the two halves"""
    if name == "raw":
        def half(vram, label):
            return (f"        VRAM_WRITE ${vram:04X}        ; the {label}\n"
                    f"        ld hl, {label}\n        ld d, {PAGES}\n        call send\n")
    elif name in ("rlem", "rlec", "otir", "dark"):
        routine = "unrlem" if name == "rlem" else "unrlec"

        def half(vram, label):
            return (f"        VRAM_WRITE ${vram:04X}        ; the {label}\n"
                    f"        ld hl, {label}\n        call {routine}\n")
    elif name == "lz":
        def half(vram, label):
            return f"        ld hl, {label}          ; the {label}\n        ld de, ${vram:04X}\n        call unlz\n"
    else:
        def half(vram, label):
            return (f"        ld hl, {label}          ; the {label}, into the RAM\n"
                    f"        ld de, RAMPIC\n        call unlzr\n"
                    f"        VRAM_WRITE ${vram:04X}        ; and sent\n"
                    f"        ld hl, RAMPIC\n        ld d, {PAGES}\n        call send\n")
    text = "go:\n" + half(0x0000, "patterns") + "half:\n" + half(0x2000, "colours") + "whole:\n"
    if name == "dark":
        text += "        VDP_REG 1, $C0          ; the display on: the picture is whole\n"
    return text + "done:   jr done\n"


SAY = {
    "raw": "; The picture as it is, 12,288 bytes, sent while the VDP draws.\n",
    "rlem": "; The picture packed as runs with a marker, unpacked into the VRAM while\n"
            "; the VDP draws.\n",
    "rlec": "; The picture packed as runs and counts, unpacked into the VRAM while the\n"
            "; VDP draws.\n",
    "lz": "; The picture packed as copies, unpacked into the VRAM while the VDP draws;\n"
          "; each copy read back from the VRAM.\n",
    "lzram": "; The picture packed as copies, each half unpacked into the RAM, then sent\n"
             "; while the VDP draws.\n",
    "otir": "; WHERE IT BREAKS. rlec.asm with the bytes as they are sent by OTIR.\n",
    "dark": "; otir.asm with the display off until the picture is whole.\n",
}


def program(name):
    fmt = FORMAT[name]
    consts = ""
    if name == "lz":
        consts = f"BUFFER  EQU ${BUFFER:04X}               ; a copy's bytes: a page of the RAM\n"
    if name == "lzram":
        consts = f"RAMPIC  EQU ${RAMPIC:04X}               ; a half of the picture: 6,144 bytes\n"
    body = INIT + ("" if name == "dark" else ON) + go(name) + FILL
    body += {"raw": SEND, "rlem": UNRLEM, "rlec": UNRLEC, "lz": UNLZ, "lzram": UNLZR + SEND,
             "otir": UNRLEC_OTIR, "dark": UNRLEC_OTIR}[name]
    data = ""
    for half in HALVES:
        p = packed(fmt, half)
        data += f"\n{half}:{' ' * max(1, 7 - len(half))}; {len(p):,} bytes\n" + db_rows(p)
    return HEAD.format(name=name, chapter=53, what=WHAT[name]) + consts + SAY[name] + \
        tidy(body) + data + CART_END


def main():
    for name in PROGRAMS:
        with open(os.path.join(HERE, f"{name}.asm"), "w") as f:
            f.write(program(name))
    print(" ".join(f"{n}.asm" for n in PROGRAMS))


if __name__ == "__main__":
    main()
