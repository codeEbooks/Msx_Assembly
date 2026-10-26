; split.asm -- chapter 5: the BIOS's interrupt between the two OUTs
        INCLUDE "msx.inc"
        OUTPUT "split.rom"
        ORG $4000
        CART_HEADER init        ; "AB" and init's address
init:   ei                      ; interrupts ON
        ld a, LIGHT_GREEN       ; the value: colour 3
        out (VDP_CTRL), a
        halt                    ; wait for an interrupt
        ld a, $80 | 7           ; $80 + register number
        out (VDP_CTRL), a       ; register 7: the border
stop:   jr stop                 ; for ever
        ds $8000 - $, $FF       ; fill to 16 KB
