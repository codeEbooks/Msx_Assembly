; ba.asm -- chapter 5: border.asm with "BA" where "AB" should be
        INCLUDE "msx.inc"
        OUTPUT "ba.rom"
        ORG $4000
        db "BA"                 ; the wrong way round
        dw init
        ds 12, 0
init:   di                      ; interrupts off
        ld a, LIGHT_GREEN       ; the value: colour 3
        out (VDP_CTRL), a
        ld a, $80 | 7           ; $80 + register number
        out (VDP_CTRL), a       ; register 7: the border
stop:   jr stop                 ; for ever
        ds $8000 - $, $FF       ; fill to 16 KB
