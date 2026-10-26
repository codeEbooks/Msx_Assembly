#!/usr/bin/env python3
"""gen50.py - the programs and the files of chapter 50: tape and disk.

    python3 gen50.py && ./build.sh

    load.asm    a tape loader in the cartridge: C-BIOS has no tape routines,
                so the cartridge reads the cassette input itself (PSG
                register 14, bit 7), measures the tone before each block to
                tell short pulses from long ones, reads a binary file into
                RAM and shows the picture it holds
    fixed.asm   WHERE IT BREAKS: load.asm with the threshold written in, the
                one load.asm measured on the 1,200 baud tape
    scope.asm   load.asm's ears without its head: after the first start bit
                it samples the input every 55 T-states into RAM, for the
                figure of a byte on tape

    screen.wav  the tape: the file at 1,200 baud, made here sample by sample
    screen.cas  the same file as a .CAS image, which openMSX turns into a
                signal of its own
    screen.dsk  the same file on a 720 KB disk, as BSAVE writes it: $FE and
                the three addresses first

The picture is the book's own: a cassette, drawn here with PIL, cut into
8 x 8 cells for Graphic I. The file holds the names (768 bytes), the colours
(32) and the shapes the names use (8 bytes each), and loads at $D000.
build.sh assembles with --syntax=bFw.
"""
import math
import os
import struct
import sys
import wave

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
for ch in ("tools", "ch26"):
    sys.path.insert(0, os.path.join(REPO, ch))
from asmparts import HEAD, CART_END, TEXT_PAGE, library, PUTDEC  # noqa: E402
from gen26 import tidy, db_rows  # noqa: E402  (chapter 26)

CLOCK = 3579545                 # the processor's T-states in a second
BAUD = 1200                     # the MSX's standard speed on tape
RATE = 9600                     # screen.wav's samples a second: 8 to a 1,200 Hz cycle
FILE_AT = 0xD000                # where the file loads: clear of VARS and the stack
NAME = "SCREEN"                 # six characters on tape
SYNC = bytes([0x1F, 0xA6, 0xDE, 0xBA, 0xCC, 0x13, 0x7D, 0x74])   # a .CAS block's mark
BINARY = 0xD0                   # ten of these: a binary file's header block

# The tape's tones and silences, in bits and seconds, as openMSX makes them
# from a .CAS (measured in meas50.py, "cas"), so that screen.wav is the same
# tape at 1,200 baud: a long tone before the header block, a short one before
# the data block.
LONG_TONE, SHORT_TONE = 8000, 2000      # 1 bits
FIRST_SILENCE, GAP_SILENCE, LAST_SILENCE = 2.0, 1.0, 0.5   # seconds

# The threshold load.asm measured on screen.wav, in turns of pulse (meas50.py
# checks it): fixed.asm has it written in.
FIXED = 28


# ================================================================ the picture
def drawing():
    """the cassette, 256 x 192, 1 = ink"""
    im = Image.new("1", (256, 192), 0)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((24, 32, 231, 163), radius=10, outline=1, width=2)     # the shell
    d.rounded_rectangle((40, 44, 215, 120), radius=4, outline=1, width=1)      # the label
    for y in (52, 60):
        d.line((56, y, 199, y), fill=1)                                       # lines to write on
    d.rectangle((96, 72, 159, 96), outline=1, width=1)                        # the window
    d.line((96, 92, 159, 92), fill=1)                                         # the tape in it
    for cx in (80, 176):                                                      # the two reels
        d.ellipse((cx - 14, 70, cx + 14, 98), outline=1, width=2)
        d.ellipse((cx - 5, 79, cx + 5, 89), outline=1, width=1)
        for k in range(6):
            a = k * math.pi / 3
            d.line((cx + 5 * math.cos(a), 84 + 5 * math.sin(a),
                    cx + 11 * math.cos(a), 84 + 11 * math.sin(a)), fill=1, width=1)
    d.polygon([(64, 163), (76, 136), (179, 136), (191, 163)], outline=1)      # where the heads go
    for x in (88, 112, 143, 167):
        d.ellipse((x - 3, 147, x + 3, 153), outline=1)
    for x, y in ((32, 40), (223, 40), (32, 155), (223, 155), (128, 150)):    # the screws
        d.ellipse((x - 2, y - 2, x + 2, y + 2), fill=1)
    return im


def tables(im):
    """Graphic I: (names, colours, shapes): each 8 x 8 cell a shape, the same
    cell the same shape, the blank cell shape 0"""
    px = im.load()
    shapes, names = {}, []
    blank = (0,) * 8
    shapes[blank] = 0
    for ty in range(24):
        for tx in range(32):
            s = tuple(sum((px[tx * 8 + x, ty * 8 + y] & 1) << (7 - x) for x in range(8)) for y in range(8))
            if s not in shapes:
                shapes[s] = len(shapes)
            names.append(shapes[s])
    order = sorted(shapes, key=shapes.get)
    colours = [0x1F] * 32               # black ink (1) on white paper (15)
    return names, colours, [b for s in order for b in s]


PICTURE = drawing()
NAMES, COLOURS, SHAPES = tables(PICTURE)
DATA = bytes(NAMES + COLOURS + SHAPES)  # the file's bytes, from FILE_AT
START, END, EXEC = FILE_AT, FILE_AT + len(DATA) - 1, 0  # END is the last byte's address
assert len(NAMES) == 768 and len(SHAPES) // 8 <= 256 and END < 0xF000


def le(n):
    return bytes([n & 255, n >> 8])


HEADER_BLOCK = bytes([BINARY] * 10) + NAME.encode()         # 16 bytes
DATA_BLOCK = le(START) + le(END) + le(EXEC) + DATA           # on tape
DISK_FILE = bytes([0xFE]) + le(START) + le(END) + le(EXEC) + DATA   # on disk


# ================================================================ the tape
def cas_image():
    """a .CAS: each block after the 8-byte mark, the mark where the file's
    length is a multiple of 8"""
    out = SYNC + HEADER_BLOCK
    assert len(out) % 8 == 0
    return out + SYNC + DATA_BLOCK


def bits_of(byte):
    """a byte on tape: a start bit 0, the eight bits from the lowest, two stop bits 1"""
    return [0] + [(byte >> i) & 1 for i in range(8)] + [1, 1]


def wav_samples(baud=BAUD):
    """screen.wav, a sample at a time: at 1,200 baud a 0 is one cycle of
    1,200 Hz, a 1 two of 2,400 Hz, each cycle high then low; silence is the
    middle"""
    hi, lo, mid = 228, 28, 128
    per_bit = RATE // baud                  # 8 samples at 1,200 baud
    assert per_bit % 4 == 0
    out = bytearray()

    def silence(s):
        out.extend([mid] * round(s * RATE))

    def bit(b):
        if b:
            out.extend(([hi] * (per_bit // 4) + [lo] * (per_bit // 4)) * 2)
        else:
            out.extend([hi] * (per_bit // 2) + [lo] * (per_bit // 2))

    def block(tone, data):
        for _ in range(tone):
            bit(1)
        for byte in data:
            for b in bits_of(byte):
                bit(b)

    silence(FIRST_SILENCE)
    block(LONG_TONE, HEADER_BLOCK)
    silence(GAP_SILENCE)
    block(SHORT_TONE, DATA_BLOCK)
    silence(LAST_SILENCE)
    return bytes(out)


def write_wav(path, samples):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(1)                   # 8 bits, unsigned
        w.setframerate(RATE)
        w.writeframes(samples)


# ================================================================ the disk
SECTOR = 512
DISK = dict(sectors=1440, per_track=9, heads=2, per_cluster=2, reserved=1, fats=2,
            fat_sectors=3, root_entries=112, media=0xF9)     # 720 KB, double sided
DOS_DATE = ((2026 - 1980) << 9) | (10 << 5) | 22             # 22 October 2026
DOS_TIME = (12 << 11) | (0 << 5) | 0                         # 12:00:00


def boot_sector():
    """a jump, a name, the BIOS parameter block, and where a boot program
    would go: here only RET"""
    b = bytearray(SECTOR)
    b[0:3] = bytes([0xEB, 0xFE, 0x90])
    b[3:11] = b"MSXBOOK "
    b[11:30] = struct.pack("<HBHBHHBHHH", SECTOR, DISK["per_cluster"], DISK["reserved"], DISK["fats"],
                           DISK["root_entries"], DISK["sectors"], DISK["media"], DISK["fat_sectors"],
                           DISK["per_track"], DISK["heads"]) + bytes(2)
    b[30] = 0xC9                            # RET: nothing to boot
    return b


def fat12(chain_lengths):
    """the FAT: the media byte and two $FF, then a 12-bit entry per cluster,
    each file's clusters one after the other from cluster 2"""
    entries = [0xF00 | DISK["media"], 0xFFF]
    for n in chain_lengths:
        first = len(entries)
        entries += [first + k + 1 for k in range(n - 1)] + [0xFFF]
    entries += [0] * (DISK["fat_sectors"] * SECTOR * 2 // 3 - len(entries))
    out = bytearray()
    for i in range(0, len(entries), 2):
        a, b = entries[i], entries[i + 1]
        out += bytes([a & 255, (a >> 8) | ((b & 15) << 4), b >> 4])
    return out[:DISK["fat_sectors"] * SECTOR]


def disk_image():
    cluster = DISK["per_cluster"] * SECTOR
    clusters = -(-len(DISK_FILE) // cluster)
    img = bytearray(DISK["sectors"] * SECTOR)
    img[0:SECTOR] = boot_sector()
    fat = fat12([clusters])
    for k in range(DISK["fats"]):
        at = (DISK["reserved"] + k * DISK["fat_sectors"]) * SECTOR
        img[at:at + len(fat)] = fat
    root = (DISK["reserved"] + DISK["fats"] * DISK["fat_sectors"]) * SECTOR
    entry = (b"SCREEN  BIN" + bytes([0x20]) + bytes(10) +
             struct.pack("<HHHI", DOS_TIME, DOS_DATE, 2, len(DISK_FILE)))
    img[root:root + 32] = entry
    first_data = root + DISK["root_entries"] * 32
    img[first_data:first_data + len(DISK_FILE)] = DISK_FILE
    return bytes(img)


# ================================================================ the programs
def head(name, what):
    return HEAD.format(name=name, chapter=50, what=what)


PULSE = """
; pulse: E = the input as last read -> waits for bit 7 of R14 to change.
;        C = the turns it waited, 44 T-states each; 0 if the edge came
;        before it looked, or if it waited more than 255 turns: a
;        silence ended. E = the input now. Uses A
pulse:  ld c, 0                 ;  8
.wait:  in a, (PSG_READ)        ; 12  bit 7: the tape
        xor e                   ;  5
        jp m, .edge             ; 11  bit 7 changed: an edge
        inc c                   ;  5
        jp nz, .wait            ; 11  44 T-states a turn
.quiet: in a, (PSG_READ)        ; 12  no edge in 256 turns: C = 0, and
        xor e                   ;  5  wait on for the one that ends
        jp p, .quiet            ; 11  the silence
.edge:  xor e                   ;  5  the input again
        ld e, a                 ;  5
        ret                     ; 11
"""

GETBYTE = """
; getbyte: D = the threshold -> A = the next byte on tape. A pulse longer
;          than D turns is half a 0, a shorter one a quarter of a 1. Waits
;          for a start bit, then reads eight bits, the lowest first. Uses
;          BC, L
getbyte:
.start: call pulse              ; 18  the tone, or stop bits: short
        ld a, d                 ;  5
        cp c                    ;  5
        jr nc, .start           ; 13, or 8  until a long one: a start bit
        call pulse              ; 18  its other half
        ld b, 8                 ;  8
.bit:   call pulse              ; 18  a bit's first half
        ld a, d                 ;  5
        cp c                    ;  5  carry: C > D, long: a 0
        jr c, .zero             ; 13, or 8
        call pulse              ; 18  a 1: three more short ones
        call pulse              ; 18
        call pulse              ; 18
        scf                     ;  5  the bit is 1
        jr .next                ; 13
.zero:  call pulse              ; 18  a 0: its other long half
        or a                    ;  5  the bit is 0
.next:  rr l                    ; 10  into L from the top: the lowest comes first
        djnz .bit               ; 14, or 9
        ld a, l                 ;  5
        ret                     ; 11
"""

HEADER = """
; header: waits for the tone before a block and measures it: D = twice
;         its mean pulse, in turns. A long pulse is twice a short one, and
;         every pulse is counted low: the work between two pulses eats
;         into them. Uses A, BC, HL
header: call pulse
        ld a, c
        or a
        jr z, header            ; a silence ended: the tone starts
        ld hl, 0                ; the sum of 256 pulses
        ld b, l
.sum:   call pulse              ; 18
        ld a, c                 ;  5
        or a                    ;  5
        jr z, header            ; 13, or 8  a silence: again
        add a, l                ;  5
        ld l, a                 ;  5
        jr nc, .nc              ; 13, or 8
        inc h                   ;  5
.nc:    djnz .sum               ; 14, or 9
        add hl, hl              ; twice the sum
        ld d, h                 ; / 256: twice the mean
        ret
"""
# fixed.asm: the same, but the last line keeps the number load.asm found at 1,200 baud
HEADER_FIXED = HEADER.replace("        ld d, h                 ; / 256: twice the mean\n",
                              f"        ld d, {FIXED}               ; written in: load.asm's at 1,200 baud\n")
assert HEADER_FIXED != HEADER

MESSAGES = """
t_look: db "MOTOR ON: LOOKING FOR A FILE", 0
t_thr:  db "TONE: THRESHOLD", 0
t_name: db "FOUND", 0
t_from: db "FROM $      TO $", 0
t_done: db "LOADED", 0
"""

BLKVARS = """hdr     EQU VARS + $10          ; the header block: 16 bytes
start   EQU VARS + $20          ; the data block's three addresses
end     EQU VARS + $22
exec    EQU VARS + $24
left    EQU VARS + $26          ; bytes still to load
bar     EQU VARS + $28          ; the progress bar's next column
ptr     EQU VARS + $2A          ; where the next byte goes
"""


FINDER = f"""find:   call header             ; D: the threshold, from the tone
        ld hl, hdr
        ld b, 16
.hd:    push bc
        push hl
        call getbyte
        pop hl
        pop bc
        ld (hl), a              ; the header block
        inc hl
        djnz .hd
        ld hl, hdr
        ld b, 10
.d0:    ld a, (hl)
        cp ${BINARY:02X}
        jr nz, find             ; not ten ${BINARY:02X}: not a binary file
        inc hl
        djnz .d0
"""


SHOW_D = """        push de
        ld hl, t_thr
        ld bc, $0402
        call puts
        pop de
        push de
        ld a, d                 ; the threshold, shown
        ld bc, $0412
        call putdec
        pop de                  ; putdec uses DE: D and E back
"""

FROMTO = """        ld b, 8
        ld c, 2
        ld hl, t_from
        call puts
        ld c, 8
        ld a, (start + 1)
        call puthex
        ld a, (start)
        call puthex
        ld c, 18
        ld a, (end + 1)
        call puthex
        ld a, (end)
        call puthex
"""

AFTER = f"""        ld b, 6
        ld c, 2
        ld hl, t_name
        call puts
        inc c
        ld hl, hdr + 10         ; the six characters of the name
        ld b, 6
.nm:    ld a, (hl)
        push bc
        ld b, 6
        call putc
        pop bc
        inc c
        inc hl
        djnz .nm
{{data_d}}        ld hl, start
        ld b, 6
.ad:    push bc
        push hl
        call getbyte
        pop hl
        pop bc
        ld (hl), a              ; start, end, exec: low byte first
        inc hl
        djnz .ad
        ld hl, (end)
        ld bc, (start)
        or a
        sbc hl, bc
        inc hl
        ld (left), hl           ; END is the last byte: END - START + 1 bytes
        ld a, 2
        ld (bar), a
        ld hl, (start)
        ld (ptr), hl
{{early}}.load:  call getbyte
        ld hl, (ptr)
        ld (hl), a              ; a byte of the file
        inc hl
        ld (ptr), hl
        ld a, l
        and 63
        call z, tick            ; a box every 64 bytes
        ld hl, (left)
        dec hl
        ld (left), hl
        ld a, h
        or l
        jr nz, .load
        in a, (PPI_C)
        or %00010000            ; bit 4 = 1: the motor stops
        out (PPI_C), a
{{late}}        ld hl, t_done
        ld bc, $0C02
        call puts
loaded: ld hl, (start)          ; the file: names, colours, shapes
        VDP_REG 1, $80          ; display off
        VRAM_WRITE $1800
        ld bc, 768
        call copy
        VRAM_WRITE $2000
        ld bc, 32
        call copy
        VRAM_WRITE $0000
        push hl
        ld hl, (end)
        ld de, (start)
        or a
        sbc hl, de
        ld de, -800 + 1
        add hl, de
        ld b, h
        ld c, l                 ; the rest of the file: the shapes
        pop hl
        call copy
        VDP_REG 1, $C0          ; display on: the picture
done:   jr done

; tick: one more box on the progress bar. Keeps DE
tick:   ld a, (bar)
        ld c, a
        inc a
        ld (bar), a
        ld b, 10
        ld a, 2                 ; a filled box
        jp putc

; copy: HL = from, BC = bytes -> to the VRAM, from the address set. HL moves on
copy:   ld a, (hl)
        out (VDP_DATA), a
        inc hl
        dec bc
        ld a, b
        or c
        jr nz, copy
        ret
"""

MOTOR = """        ld hl, t_look
        ld bc, $0202
        call puts
        VDP_REG 1, $C0          ; display on: the page, while it loads
        in a, (PPI_C)
        and %11101111           ; bit 4 = 0: the motor turns
        out (PPI_C), a
        ld a, 14
        out (PSG_ADDR), a       ; R14 from now on: bit 7 is the tape
        in a, (PSG_READ)
        ld e, a                 ; E: the input as last read
"""

SAMPLES_AT = FILE_AT
N_SAMPLES = 8192

SCOPE = f"""find:   call header             ; D: the threshold
.first: call pulse
        ld a, d
        cp c
        jr nc, .first           ; until a long pulse: the first start bit
        ld hl, ${SAMPLES_AT:04X}            ; from its other half on
        ld bc, {N_SAMPLES}
.s:     in a, (PSG_READ)        ; 12  a sample of bit 7
        ld (hl), a              ;  8
        inc hl                  ;  7
        dec bc                  ;  7
        ld a, b                 ;  5
        or c                    ;  5
        jp nz, .s               ; 11  55 T-states a sample
        in a, (PPI_C)
        or %00010000
        out (PPI_C), a          ; the motor stops
done:   jr done
"""

SAY = {
    "load": f"""; A tape loader in the cartridge. C-BIOS has no tape routines: the cartridge
; reads the cassette input itself and loads the binary file {NAME} at the
; address its data block gives, then shows the picture the file holds.
""",
    "fixed": """; WHERE IT BREAKS. load.asm with the threshold written in, the number load.asm
; measured on the 1,200 baud tape: right near that speed, wrong on the .CAS.
""",
    "scope": f"""; The loader's ears: after the first start bit on the tape, {N_SAMPLES:,} samples
; of the input, one every 55 T-states, from ${SAMPLES_AT:04X}.
""",
}
WHAT = {"load": "a tape loader in the cartridge", "fixed": "a loader that does not measure the tone",
        "scope": "the tape, sampled"}


def program(name):
    lib = library(PUTDEC)
    if name == "scope":
        body = TEXT_PAGE + MOTOR + SCOPE + PULSE + HEADER + lib + MESSAGES
    else:
        data_d = "        call header             ; the data block's tone: D again\n"
        body = (TEXT_PAGE + MOTOR + FINDER + SHOW_D + AFTER.format(data_d=data_d, early="",
                                                                    late=FROMTO) +
                PULSE + GETBYTE + (HEADER if name == "load" else HEADER_FIXED) + lib + MESSAGES)
    return head(name, WHAT[name]) + BLKVARS + SAY[name] + tidy(body) + CART_END


PROGRAMS = ["load", "fixed", "scope"]


def variant(kind):
    """the workshop's program: early.asm, load.asm with the addresses printed
    as soon as they are read, before the data, not after"""
    assert kind == "early"
    lib = library(PUTDEC)
    data_d = "        call header             ; the data block's tone: D again\n"
    body = (TEXT_PAGE + MOTOR + FINDER + SHOW_D + AFTER.format(data_d=data_d, early=FROMTO, late="") +
            PULSE + GETBYTE + HEADER + lib + MESSAGES)
    src = head("early", "the addresses printed too soon") + BLKVARS + SAY["load"] + tidy(body) + CART_END
    return "early", src


def main():
    for name in PROGRAMS:
        with open(os.path.join(HERE, f"{name}.asm"), "w") as f:
            f.write(program(name))
    with open(os.path.join(HERE, "screen.cas"), "wb") as f:
        f.write(cas_image())
    write_wav(os.path.join(HERE, "screen.wav"), wav_samples())
    with open(os.path.join(HERE, "screen.dsk"), "wb") as f:
        f.write(disk_image())
    PICTURE.save(os.path.join(HERE, "screen.png"))
    print(" ".join(f"{n}.asm" for n in PROGRAMS), "screen.cas/.wav/.dsk/.png",
          f"file {len(DATA)} bytes ${START:04X}-${END:04X}, {len(SHAPES) // 8} shapes")


if __name__ == "__main__":
    main()
