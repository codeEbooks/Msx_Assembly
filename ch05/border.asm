; border.asm -- chapter 5: the first program. The border turns light green.
        INCLUDE "msx.inc"
        OUTPUT "border.rom"
        ORG $4000
        CART_HEADER init        ; "AB" and init's address
init:   di                      ; interrupts off
        ld a, LIGHT_GREEN       ; the value: colour 3
        out (VDP_CTRL), a
        ld a, $80 | 7           ; $80 + register number
        out (VDP_CTRL), a       ; register 7: the border
stop:   jr stop                 ; for ever
        ds $8000 - $, $FF       ; fill to 16 KB
