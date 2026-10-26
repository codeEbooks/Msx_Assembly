; typo.asm -- chapter 5: a misspelt name. It does not assemble, on purpose.
        INCLUDE "msx.inc"
        OUTPUT "typo.rom"
        ORG $4000
        CART_HEADER init        ; "AB" and init's address
init:   di                      ; interrupts off
        ld a, LIGHT_GREN        ; the value: colour 3
        out (VDP_CTRL), a
        ld a, $80 | 7           ; $80 + register number
        out (VDP_CTRL), a       ; register 7: the border
stop:   jr stop                 ; for ever
        ds $8000 - $, $FF       ; fill to 16 KB
