#!/usr/bin/env python3
"""gen03.py - the programs of chapter 3.

    python3 gen03.py && ./build.sh

    memmap.asm     every one of the 65,536 addresses the processor can reach:
                   write the complement, read it back, put the old byte back.
                   One box per kilobyte, one row per 16 KB page.
    slots.asm      the same question asked of every slot behind every page:
                   the program changes the slot register at port $A8, adds up
                   the 16 KB it then sees, and counts the bytes that keep a
                   write and the bytes that are not $FF.
    sysvars.asm    the registers the cartridge is handed, and fourteen of the
                   system variables the BIOS leaves in its work area.
    timing.asm     500 copies each of ten instructions, timed by the openMSX
                   debugger; and the 500 NOPs copied into RAM and timed there.
    nops.asm       three white stripes in the bottom border, four lines each:
                   0, 16 and 32 NOPs between the two writes that start and end
                   each line of a stripe.
    vdp.asm        the VDP's ports: four bytes written across the end of the
                   VRAM and read back, the status read twice, and port $99
                   read just after a register write.
    psg.asm        the PSG's sixteen registers as the BIOS left them, and
                   after $FF was written into each (the mixer kept safe).
    keys.asm       the eleven keyboard rows read through the PPI, the PSG's
                   joystick register, and ports $AA and $A8, once a frame.
                   Q is held down from frame 50 (keys.events).
    page0_di.asm   at frame 50 the program switches page 0 to slot 2, adds up
                   what is there and switches back, with interrupts off.
    page0_ei.asm   WHERE IT BREAKS: the same with interrupts on.

The routines come from tools/asmparts.py.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
from asmparts import (HEAD, TAIL, TEXT_PAGE, SHOW_PAGE, library, PUTD16,  # noqa: E402
                      FATBITS, BOX_EMPTY, BOX_FULL, steady)


def head(name, what):
    return HEAD.format(name=name, chapter=3, what=what)


# ---------------------------------------------------------------- memmap
MM_ROW0 = 3                 # the row of page 0; the pages are two rows apart
MM_COLS = {"page": 0, "start": 2, "boxes": 8, "kept": 25}


def memmap():
    return head("memmap", "every address, written and read back") + f"""counts  EQU VARS + 16           ; 64 counts of 2 bytes, one for each kilobyte
total   EQU VARS + 12           ; all the addresses that kept a write
""" + TEXT_PAGE + f"""        ld hl, counts
        ld b, 128
.zero:  ld (hl), 0
        inc hl
        djnz .zero
test_start:
        call memtest
test_end:
        ld b, {MM_ROW0 - 2}
        ld c, 0
        ld hl, t_head
        call puts
        ld ix, counts
        ld hl, 0
        ld (total), hl
        ld b, {MM_ROW0}
        xor a                   ; the page
page:   push af
        ld c, {MM_COLS['page']}
        call hexdig             ; the page number
        ld c, {MM_COLS['start']}
        ld a, '$'
        call putc
        inc c
        pop af
        push af
        rrca
        rrca                    ; page x $40: the high byte of its first address
        call puthex
        xor a
        call puthex
        ld c, {MM_COLS['boxes']}
        ld hl, 0                ; the page's count
        ld e, 16                ; sixteen kilobytes
kb:     push de
        ld e, (ix+0)
        ld d, (ix+1)
        add hl, de
        ld a, d
        or e
        ld a, {BOX_EMPTY}                 ; no address of the kilobyte kept a write
        jr z, .put
        ld a, d
        cp 4                    ; 1,024 = $0400: all of them did
        ld a, {BOX_FULL}
        jr z, .put
        ld a, '?'               ; some did: the program says it cannot tell
.put:   call putc
        inc c
        inc ix
        inc ix
        pop de
        dec e
        jr nz, kb
        push hl
        ld de, (total)
        add hl, de
        ld (total), hl
        pop hl
        ld c, {MM_COLS['kept']}
        call putd16
        pop af
        inc b
        inc b
        inc a
        cp 4
        jr nz, page
        ld c, 0
        ld hl, t_total
        call puts
        ld hl, (total)
        ld c, {MM_COLS['kept']}
        call putd16
""" + SHOW_PAGE + f"""
; memtest: every address from $0000 to $FFFF. The byte is turned over (CPL),
; written, compared, and the old byte put back at once; an address that kept
; the write adds one to the count of its kilobyte. Interrupts are off.
memtest:
        ld hl, 0
.next:  ld a, (hl)
        ld b, a                 ; B: the byte as it was
        cpl                     ; every bit turned over: certainly different
        ld (hl), a
        cp (hl)                 ; Z if the address kept it
        ld (hl), b              ; put the old byte back (LD does not touch F)
        jr nz, .skip
        push hl
        ld a, h
        rrca
        rrca                    ; H / 4: the kilobyte, 0 to 63
        and %00111111
        add a, a                ; two bytes a count
        ld e, a
        ld d, 0
        ld hl, counts
        add hl, de
        inc (hl)
        jr nz, .nc
        inc hl
        inc (hl)
.nc:    pop hl
.skip:  inc hl
        ld a, h
        or l
        jr nz, .next            ; until HL wraps round to 0
        ret

t_head: db "pg start  one box a KB    kept", 0
t_total: db "  of 65536 addresses", 0
""" + library(PUTD16, FATBITS) + TAIL


# ---------------------------------------------------------------- slots
PROBE_RAM = 0xC400          # where the probe is copied to test pages 0 to 2
SL_ROW0, SL_COLS = 3, (5, 12, 19, 26)
SL_A8_ROW = 16


def slots():
    return head("slots", "every slot behind every page") + f"""PROBE_RAM EQU ${PROBE_RAM:04X}             ; a copy of the probe, in page 3
slotreg EQU VARS + 12           ; port $A8 as the BIOS left it
slot    EQU VARS + 13
pg      EQU VARS + 14
cellp   EQU VARS + 15           ; 2 bytes: where the next result goes
cells   EQU VARS + 32           ; 16 results of 6 bytes: sum, kept, not $FF
""" + TEXT_PAGE + f"""        ld hl, probe            ; a copy that can run while pages 0-2 change
        ld de, PROBE_RAM
        ld bc, probe_end - probe
        ldir
        in a, (PPI_A)
        ld (slotreg), a
        ld hl, cells
        ld (cellp), hl
        xor a
        ld (slot), a
sloop:  xor a
        ld (pg), a
ploop:  ld a, (pg)              ; the slot register with this page's two
        ld b, a                 ; bits replaced by the slot under test
        ld a, (slot)
        ld c, %11111100         ; C: the mask, D: the slot, both moved to the page
        ld d, a
        inc b
        jr .first
.move:  rlc c
        rlc c
        sla d
        sla d
.first: djnz .move
        ld a, (slotreg)
        and c
        or d                    ; A: the value for port $A8
        ld e, a
        ld a, (pg)
        rrca
        rrca                    ; the page's first address, high byte
        ld h, a
        ld a, e
        ld l, a
        ld a, (pg)
        cp 3
        ld a, l
        jr z, .p3
        call PROBE_RAM          ; pages 0-2: the copy in page 3
        jr .got
.p3:    call probe              ; page 3: the original, in page 1
.got:   exx
        push bc                 ; the bytes that are not $FF
        exx
        push iy                 ; the bytes that kept a write
        push ix                 ; the sum
        ld hl, (cellp)
        ld b, 3
.store: pop de
        ld (hl), e
        inc hl
        ld (hl), d
        inc hl
        djnz .store
        ld (cellp), hl
        ld a, (pg)
        inc a
        ld (pg), a
        cp 4
        jr nz, ploop
        ld a, (slot)
        inc a
        ld (slot), a
        cp 4
        jr nz, sloop
; the page
        ld b, {SL_ROW0 - 2}
        ld c, 0
        ld hl, t_head
        call puts
        ld ix, cells
        ld b, {SL_ROW0}
        xor a
srow:   push af
        ld c, 1
        call hexdig             ; the slot
        ld e, 0                 ; the page
scell:  ld hl, cols
        ld d, 0
        add hl, de
        ld c, (hl)              ; the column of this page
        push de
        ld l, (ix+2)
        ld h, (ix+3)            ; kept
        ld a, h
        cp $40                  ; 16,384 kept: RAM
        jr nz, .notram
        ld hl, t_ram
        call puts
        inc b
        ld a, c
        sub 3
        ld c, a
        ld l, (ix+2)
        ld h, (ix+3)
        call putd16
        dec b
        jr .next
.notram:
        ld a, (ix+4)
        or (ix+5)               ; no byte other than $FF: nothing there
        jr nz, .some
        ld hl, t_none
        call puts
        jr .next
.some:  ld a, (ix+2)
        or (ix+3)
        ld hl, t_rom            ; no byte kept a write: ROM
        jr z, .rom
        ld hl, t_what
.rom:   call puts
        inc b
        ld a, c
        sub 3
        ld c, a
        ld a, (ix+1)
        call puthex             ; the sum, in hexadecimal
        ld a, (ix+0)
        call puthex
        dec b
.next:  ld de, 6
        add ix, de
        pop de
        inc e
        ld a, e
        cp 4
        jr nz, scell
        pop af
        inc b
        inc b
        inc b
        inc a
        cp 4
        jr nz, srow
        ld b, {SL_A8_ROW}
        ld c, 0
        ld hl, t_a8
        call puts
        ld a, (slotreg)
        call puthex
        inc c
        ld a, (slotreg)
        call fatbits
        ld b, {SL_A8_ROW + 1}
        ld c, 10
        ld hl, t_pages
        call puts
""" + SHOW_PAGE + f"""
; probe: A = the value for port $A8, H = the first address of the page.
; Returns IX = the sum of the page's 16,384 bytes (16 bits), IY = how many
; kept a write, BC' = how many are not $FF. While the page shows the slot
; under test it uses no memory but that page and no stack, so it can test the
; page that holds the stack. Only relative jumps: it runs wherever it is put.
probe:  ld e, a                 ; E: the value under test
        in a, (PPI_A)
        ld d, a                 ; D: the value to put back
        ld l, 0
        ld ix, 0
        ld iy, 0
        exx
        ld bc, 0
        exx
        ld a, e
        out (PPI_A), a          ; the page now shows the slot under test
.byte:  ld a, (hl)
        ld c, a
        ld b, 0
        add ix, bc              ; the sum
        cp $FF
        jr z, .ff
        exx
        inc bc                  ; not $FF
        exx
.ff:    cpl
        ld (hl), a
        cp (hl)
        ld (hl), c              ; the byte put back
        jr nz, .kept
        inc iy                  ; it kept the write
.kept:  inc hl
        ld a, h
        and %00111111
        or l
        jr nz, .byte            ; until HL reaches the next page
        ld a, d
        out (PPI_A), a          ; the slots as they were
        ret
probe_end:

cols:   db {", ".join(str(c) for c in SL_COLS)}
t_head: db "slot $0000  $4000  $8000  $C000", 0
t_ram:  db "RAM", 0
t_rom:  db "ROM", 0
t_none: db " - ", 0
t_what: db "???", 0
t_a8:   db "port $A8: ", 0
t_pages: db "33221100 page", 0
""" + library(PUTD16, FATBITS) + TAIL


# ---------------------------------------------------------------- sysvars
# (name, address, 'w' for a 16-bit word or a count of bytes)
SYSVARS = [("BOTTOM", 0xFC48, "w"), ("HIMEM", 0xFC4A, "w"), ("STKTOP", 0xF674, "w"),
           ("EXPTBL", 0xFCC1, 4), ("CGPNT", 0xF91F, 3), ("SCRMOD", 0xFCAF, 1),
           ("FORCLR", 0xF3E9, 3), ("RG0SAV", 0xF3DF, 4), ("RG4SAV", 0xF3E3, 4),
           ("STATFL", 0xF3E7, 1), ("JIFFY", 0xFC9E, "w"), ("CLIKSW", 0xF3DB, 1),
           ("H.KEYI", 0xFD9A, 5), ("H.TIMI", 0xFD9F, 5)]
SV_ROW0, SV_REG_ROW = 2, 17
SV_COLS = {"name": 0, "addr": 7, "value": 13}
REGS = ["AF", "BC", "DE", "HL", "IX", "IY", "SP"]


def sysvars():
    rows = []
    for i, (name, addr, kind) in enumerate(SYSVARS):
        r = SV_ROW0 + 1 + i
        rows.append(f"""        ld b, {r}
        ld c, {SV_COLS['name']}
        ld hl, n{i}
        call puts
        ld c, {SV_COLS['addr']}
        ld a, ${addr >> 8:02X}
        call puthex
        ld a, ${addr & 0xFF:02X}
        call puthex
        ld c, {SV_COLS['value']}
""")
        if kind == "w":
            rows.append(f"""        ld hl, (${addr:04X})
        ld a, h
        call puthex
        ld a, l
        call puthex
""")
        else:
            rows.append(f"""        ld hl, ${addr:04X}
        ld e, {kind}
        call bytes
""")
    names = "\n".join(f'n{i}:     db "{name}", 0' for i, (name, _, _) in enumerate(SYSVARS))
    regs = []
    for k, r in enumerate(REGS):
        row, col = SV_REG_ROW + 1 + k // 3, 10 * (k % 3)
        regs.append(f"""        ld b, {row}
        ld c, {col}
        ld hl, rn{k}
        call puts
        ld hl, (r_{r.lower()})
        ld a, h
        call puthex
        ld a, l
        call puthex
""")
    rnames = "\n".join(f'rn{k}:    db "{r} ", 0' for k, r in enumerate(REGS))
    return head("sysvars", "the registers at INIT and the BIOS's work area") + f"""r_af    EQU VARS + 16           ; the registers as the cartridge found them
r_bc    EQU VARS + 18
r_de    EQU VARS + 20
r_hl    EQU VARS + 22
r_ix    EQU VARS + 24
r_iy    EQU VARS + 26
r_sp    EQU VARS + 28
r_i     EQU VARS + 30           ; I, then the flags of LD A,I
""" + TEXT_PAGE.replace("init:   di\n", """init:   ld (r_sp), sp           ; before anything changes them
        push af
        ld (r_bc), bc
        ld (r_de), de
        ld (r_hl), hl
        ld (r_ix), ix
        ld (r_iy), iy
        pop hl
        ld (r_af), hl
        ld a, i                 ; P/V: the interrupt enable flip-flop IFF2
        ld (r_i), a
        push af
        pop hl
        ld a, l
        ld (r_i + 1), a
        di
""") + f"""        ld b, {SV_ROW0 - 1}
        ld c, 0
        ld hl, t_head
        call puts
""" + "".join(rows) + f"""        ld b, {SV_REG_ROW}
        ld c, 0
        ld hl, t_regs
        call puts
""" + "".join(regs) + f"""        ld b, {SV_REG_ROW + 3}
        ld c, 20
        ld hl, t_i
        call puts
        ld a, (r_i)
        call puthex
        ld b, {SV_REG_ROW + 4}
        ld c, 0
        ld hl, t_iff
        call puts
        ld a, (r_i + 1)
        and %00000100           ; P/V after LD A,I is IFF2
        ld a, '0'
        jr z, .iff
        ld a, '1'
.iff:   call putc
""" + SHOW_PAGE + f"""
; bytes: E bytes from HL, in hexadecimal, a space between. C moves on.
bytes:  ld a, (hl)
        call puthex
        inc c
        inc hl
        dec e
        jr nz, bytes
        ret

t_head: db "name   addr  value", 0
t_regs: db "the registers at INIT", 0
t_i:    db "I  ", 0
t_iff:  db "interrupts on (IFF2): ", 0
{names}
{rnames}
""" + library() + TAIL


# ---------------------------------------------------------------- timing
TIMED = [("nop", "nop", 1), ("inchl", "inc hl", 1), ("ldahl", "ld a,(hl)", 1),
         ("ldan", "ld a,$55", 2), ("push", "push hl", 1), ("pop", "pop hl", 1),
         ("outc", "out (c),a", 2), ("sla", "sla a", 2), ("ldix", "ld a,(ix+0)", 3),
         ("bitix", "bit 0,(ix+0)", 4), ("jr", "jr $+2", 2)]
N_TIMED = 500
RAM_NOPS = 0xC200           # the NOP block, copied here and timed again


def timing():
    blocks = []
    for key, ins, _ in TIMED:
        blocks.append(f"t_{key}:\n" + "".join(f"        {ins}\n" for _ in range(N_TIMED)))
    return head("timing", f"{N_TIMED} copies of each of {len(TIMED)} instructions") + f"""; The debugger times each block, from its label to the next one.
""" + f"""init:   di
        ld sp, SYS_AREA
        ld hl, RAM_START + $1000        ; something to read
        ld ix, RAM_START + $1000
        ld c, PSG_ADDR                  ; OUT (C),A selects a PSG register: harmless
        xor a
""" + "".join(blocks) + f"""t_end:
        ld hl, t_nop                    ; the NOP block, into RAM
        ld de, ${RAM_NOPS:04X}
        ld bc, {N_TIMED}
t_ldir: ldir
t_ldir_end:
        ld a, $C9                       ; RET after it
        ld (de), a
        call ${RAM_NOPS:04X}                      ; the debugger times it there
done:   jr done
""" + TAIL


# ---------------------------------------------------------------- nops
NOPS = (0, 16, 32)          # NOPs between the two writes of each stripe
PRE_T = 388                 # T from the interrupt to the first stripe: it
                            # starts at column 20, and the longest ends at 301,
                            # inside the 284 columns every openMSX draws alike
STRIPE_LINES = 4            # each stripe is drawn on four lines in a row
STRIPE_EVERY = 8            # and the stripes start eight lines apart
LINE_T = 228
COST = {"nop": 5, "ld a,(hl)": 8, "inc hl": 7}     # measured by timing.asm


def delay(t):
    """instructions that take exactly t T-states: NOPs and LD A,(HL), and one
    INC HL when nothing else fits"""
    for extra in (0, 7, 14):
        rest = t - extra
        for a in range(rest // 8 + 1):
            if (rest - 8 * a) % 5 == 0:
                out = ["inc hl"] * (extra // 7) + ["ld a,(hl)"] * a + ["nop"] * ((rest - 8 * a) // 5)
                assert sum(COST[i] for i in out) == t
                return [f"        {i}" for i in out]
    raise ValueError(t)


def nops(pre_t=PRE_T, stripes=None, name="nops", what="three stripes: 0, 16 and 32 NOPs long",
         chapter=3):
    """stripes: (shift, n) for each stripe -- it starts `shift` T-states later
    than the first one would, with n NOPs between its two writes"""
    stripes = stripes or [(0, n) for n in NOPS]
    body = delay(pre_t + stripes[0][0])
    for k, (shift, n) in enumerate(stripes):
        for j in range(STRIPE_LINES):
            body += ["        out (c), b              ; value: white",
                     (f"white{k}: " if j == 0 else "        ") + "out (c), e              ; R#7 <- white"]
            body += ["        nop"] * n
            body += ["        out (c), d              ; value: black",
                     (f"black{k}: " if j == 0 else "        ") + "out (c), e              ; R#7 <- black"]
            # from this white write to the next one: one line, or what is left
            # of the eight lines to the next stripe
            last = j == STRIPE_LINES - 1
            if last and k == len(stripes) - 1:
                break
            span = LINE_T * (STRIPE_EVERY - STRIPE_LINES + 1 if last else 1)
            if last:
                span += stripes[k + 1][0] - shift
            body += delay(span - 4 * 14 - 5 * n)
    return HEAD.format(name=name, chapter=chapter, what=what) + f"""IM2_TABLE EQU $C100             ; 257 bytes of $C2: the interrupt vector is $C2C2
IM2_JUMP  EQU $C2C2
init:   di
        ld sp, SYS_AREA
        VDP_REG 1, $80          ; display off while we set up
        VDP_REG 0, $00          ; Graphic I
        VDP_REG 2, $06
        VDP_REG 3, $80
        VDP_REG 4, $00
        VDP_REG 5, $36
        VDP_REG 6, $07
        VDP_REG 7, $01          ; border black
        VRAM_WRITE $2000        ; colour table: black on black
        ld b, 32
        ld a, $11
.col:   out (VDP_DATA), a
        djnz .col
        VRAM_WRITE $1B00        ; no sprites
        ld a, $D0
        out (VDP_DATA), a
        ld hl, IM2_TABLE        ; the IM 2 table
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
        ld c, VDP_CTRL          ; kept for the handler
        ld b, $0F               ; white
        ld d, $01               ; black
        ld e, $87               ; register 7
        VDP_REG 1, $E0          ; display on, frame interrupt on
        ei
main:   halt
        jr main
handler:
        in a, (VDP_CTRL)        ; reading the status acknowledges the interrupt
""" + "\n".join(body + steady(["        in a, (VDP_CTRL)"] + body)) + """
        ei
        ret
""" + TAIL


# ---------------------------------------------------------------- vdp
VDP_BYTES = (0x11, 0x22, 0x33, 0x44)
VDP_AT = 0x3FFE             # two bytes before the end of the VRAM
VD_ROW0 = 2


def vdp():
    return head("vdp", "the VDP's two ports: data, and control and status") + f"""got     EQU VARS + 16           ; 4 bytes read back through port $98
st1     EQU VARS + 20           ; the status, read twice
st2     EQU VARS + 21
st3     EQU VARS + 22           ; port $99 read just after a register write
""" + TEXT_PAGE + f"""        VRAM_WRITE ${VDP_AT:04X}        ; four bytes from two before the end
""" + "".join(f"""        ld a, ${v:02X}
        out (VDP_DATA), a
""" for v in VDP_BYTES) + f"""        ld a, low ${VDP_AT:04X}        ; the same address, to read: bit 6 left 0
        out (VDP_CTRL), a
        ld a, high ${VDP_AT:04X}
        out (VDP_CTRL), a
        ld hl, got
        ld b, 4
.rd:    in a, (VDP_DATA)        ; each IN moves the address on, like each OUT
        ld (hl), a
        inc hl
        djnz .rd
        VDP_REG 1, $C0          ; display on, no interrupts
.wait:  in a, (VDP_CTRL)        ; the status, until the frame flag comes up
        rlca
        jr nc, .wait
        rrca
        ld (st1), a             ; the read that saw the flag
        in a, (VDP_CTRL)
        ld (st2), a             ; and the next one
        VDP_REG 7, $F4          ; a register write ...
        in a, (VDP_CTRL)        ; ... and port $99 read straight after it
        ld (st3), a
        VDP_REG 7, $0F          ; the border white again
        VDP_REG 1, $80          ; display off: the page is drawn
        ld b, {VD_ROW0}
        ld c, 0
        ld hl, t_wrote
        call puts
""" + "".join(f"""        ld a, ${v:02X}
        call puthex
        inc c
""" for v in VDP_BYTES) + f"""        ld b, {VD_ROW0 + 2}
        ld c, 0
        ld hl, t_read
        call puts
        ld hl, got
        ld e, 4
.show:  ld a, (hl)
        call puthex
        inc c
        inc hl
        dec e
        jr nz, .show
        ld b, {VD_ROW0 + 4}
        ld c, 0
        ld hl, t_st
        call puts
        ld a, (st1)
        call puthex
        inc c
        ld a, (st2)
        call puthex
        ld b, {VD_ROW0 + 6}
        ld c, 0
        ld hl, t_reg
        call puts
        ld a, (st3)
        call puthex
""" + SHOW_PAGE + f"""
t_wrote: db "wrote at ${VDP_AT:04X}: ", 0
t_read: db "read from ${VDP_AT:04X}: ", 0
t_st:   db "status, twice:   ", 0
t_reg:  db "R#7 <- F4, then $99: ", 0
""" + library() + TAIL


# ---------------------------------------------------------------- psg
PSG_TEST_R7 = 0xBF          # tones and noise off; port A input, port B output
PS_ROW0 = 2


def psg():
    def show(row, label, src):
        return f"""        ld b, {row}
        ld c, 0
        ld hl, {label}
        call puts
        ld hl, {src}
        ld b, {row + 1}
        ld c, 0
        call regs8
        ld b, {row + 3}
        ld c, 0
        call regs8
"""
    return head("psg", "the PSG's sixteen registers, as left and as written") + f"""before  EQU VARS + 16           ; the registers as the BIOS left them
after   EQU VARS + 32           ; and after $FF was written to each
""" + TEXT_PAGE + f"""        ld hl, before           ; read all sixteen before touching any
        call readall
        ld a, 7                 ; the mixer first: every tone and noise off,
        out (PSG_ADDR), a       ; port A an input, port B an output
        ld a, ${PSG_TEST_R7:02X}
        out (PSG_WRITE), a
        ld e, 0                 ; then $FF into every other register but 14
.wr:    ld a, e
        cp 7
        jr z, .skip
        cp 14
        jr z, .skip
        out (PSG_ADDR), a
        ld a, $FF
        out (PSG_WRITE), a
.skip:  inc e
        ld a, e
        cp 16
        jr nz, .wr
        ld hl, after
        call readall
        ld a, 8                 ; silence: the three volumes back to 0
        call zero
        ld a, 9
        call zero
        ld a, 10
        call zero
        ld b, {PS_ROW0 - 1}
        ld c, 0
        ld hl, t_num
        call puts
""" + show(PS_ROW0, "t_before", "before") + show(PS_ROW0 + 6, "t_after", "after") + SHOW_PAGE + f"""
; readall: the sixteen registers into 16 bytes from HL
readall:
        ld e, 0
.r:     ld a, e
        out (PSG_ADDR), a
        in a, (PSG_READ)
        ld (hl), a
        inc hl
        inc e
        ld a, e
        cp 16
        jr nz, .r
        ret

; zero: register A := 0
zero:   out (PSG_ADDR), a
        xor a
        out (PSG_WRITE), a
        ret

; regs8: 8 bytes from HL, two hexadecimal digits and a space each
regs8:  ld e, 8
.n:     ld a, (hl)
        call puthex
        inc c
        inc c
        inc hl
        dec e
        jr nz, .n
        ret

t_num:  db "R0-R7, then R8-R15", 0
t_before: db "as the BIOS left them:", 0
t_after: db "after writing $FF:", 0
""" + library() + TAIL


# ---------------------------------------------------------------- keys
KEY_ROWS = 11
KY_ROW0 = 2                 # the row of keyboard row 0
KY_COLS = {"row": 0, "bits": 4, "hex": 13}
KEY_EVENT = (50, 4, 0x40)   # frame, keyboard row, bit mask: Q on this keyboard
KY_PORT_ROW = 15            # then PSG R14, port $AA and port $A8, two rows apart


def keys():
    return head("keys", "the keyboard rows, and three more ports") + TEXT_PAGE + f"""        ld b, {KY_ROW0 - 1}
        ld c, 0
        ld hl, t_head
        call puts
        ld b, {KY_PORT_ROW}
        ld c, 0
        ld hl, t_psg
        call puts
        ld b, {KY_PORT_ROW + 2}
        ld c, 0
        ld hl, t_aa
        call puts
        ld b, {KY_PORT_ROW + 4}
        ld c, 0
        ld hl, t_a8
        call puts
        VDP_REG 1, $C0          ; display on; no interrupts: the program polls
main:   in a, (VDP_CTRL)        ; wait for the frame flag (bit 7 of the status)
        rlca
        jr nc, main
        ld b, {KY_ROW0}
        ld e, 0                 ; the keyboard row
krow:   ld c, {KY_COLS['row']}
        ld a, e
        call puthex
        in a, (PPI_C)
        and $F0                 ; keep the click, the LED and the cassette bits
        or e
        out (PPI_C), a          ; select the row
        in a, (PPI_B)           ; and read its eight keys: 0 = held down
        ld c, {KY_COLS['bits']}
        push af
        call fatbits
        pop af
        ld c, {KY_COLS['hex']}
        call puthex
        inc b
        inc e
        ld a, e
        cp {KEY_ROWS}
        jr nz, krow
        ld b, {KY_PORT_ROW:<18}; the PSG's register 14: the joystick port
        ld c, {KY_COLS['bits']}
        ld a, 14
        out (PSG_ADDR), a
        in a, (PSG_READ)
        call byte
        ld b, {KY_PORT_ROW + 2:<18}; port $AA: the PPI's port C, as last written
        ld c, {KY_COLS['bits']}
        in a, (PPI_C)
        call byte
        ld b, {KY_PORT_ROW + 4:<18}; port $A8: the slots
        ld c, {KY_COLS['bits']}
        in a, (PPI_A)
        call byte
        jp main

; byte: A as eight boxes and two hexadecimal digits
byte:   push af
        call fatbits
        pop af
        inc c
        jp puthex

t_head: db "row port $A9", 0
t_psg:  db "R14", 0
t_aa:   db "$AA", 0
t_a8:   db "$A8", 0
""" + library(FATBITS) + TAIL


# ---------------------------------------------------------------- page 0
PAGE0_AT = 50               # the frame count at which the program looks
PAGE0_SLOT = 2              # the slot it looks at: nothing is there


def page0(di):
    name = "page0_di" if di else "page0_ei"
    why = ("page 0 switched to slot 2 with interrupts off" if di else
           "WHERE IT BREAKS: page 0 switched to slot 2 with interrupts on")
    return head(name, why) + f"""count   EQU VARS + 16           ; frames the program has counted
sum     EQU VARS + 18
""" + TEXT_PAGE + f"""        ld hl, 0
        ld (count), hl
        ld b, 1
        ld c, 0
        ld hl, t_title
        call puts
        VDP_REG 1, $E0          ; display on, frame interrupt on
        im 1                    ; the interrupt goes to $0038: the BIOS
        ei
main:   halt
        ld hl, (count)
        inc hl
        ld (count), hl
        ld b, 3
        ld c, 0
        ld hl, t_frame
        call puts
        ld hl, (count)
        call putd16
        ld hl, (count)
        ld a, h
        or a
        jr nz, main
        ld a, l
        cp {PAGE0_AT}
        call z, look
        jr main

; look: page 0 shows slot {PAGE0_SLOT} while the program adds up its 16,384 bytes
look:{'''
        di                      ; nothing may run from page 0 meanwhile''' if di else ''}
        in a, (PPI_A)
        ld e, a                 ; the slots as they are
        and %11111100
        or {PAGE0_SLOT}                    ; page 0: slot {PAGE0_SLOT}
        out (PPI_A), a
        ld hl, 0
        ld ix, 0
        ld b, 0
.add:   ld c, (hl)
        add ix, bc
        inc hl
        ld a, h
        cp $40
        jr nz, .add
        ld a, e
        out (PPI_A), a          ; the BIOS back in page 0{'''
        ei''' if di else ''}
looked: ld (sum), ix
        ld b, 5
        ld c, 0
        ld hl, t_sum
        call puts
        ld a, (sum + 1)
        call puthex
        ld a, (sum)
        call puthex
        ret

t_title: db "{'interrupts off' if di else 'interrupts on'}", 0
t_frame: db "frames counted ", 0
t_sum:  db "page 0, slot {PAGE0_SLOT}: sum ", 0
""" + library(PUTD16) + TAIL


def main():
    files = {"memmap.asm": memmap(), "slots.asm": slots(), "sysvars.asm": sysvars(),
             "timing.asm": timing(), "nops.asm": nops(), "vdp.asm": vdp(), "keys.asm": keys(),
             "psg.asm": psg(),
             "page0_di.asm": page0(True), "page0_ei.asm": page0(False)}
    for name, text in files.items():
        with open(os.path.join(HERE, name), "w") as f:
            f.write(text)
    with open(os.path.join(HERE, "keys.events"), "w") as f:
        fr, row, mask = KEY_EVENT
        f.write(f"# frame  Tcl: the Q key (row {row}, bit {mask.bit_length() - 1}) "
                f"held down from frame {fr}\n{fr} keymatrixdown {row} 0x{mask:02X}\n")
    print(len(files), "sources written, and keys.events")


if __name__ == "__main__":
    main()
