; wait.asm -- chapter 5: more than a frame between the two OUTs
        INCLUDE "msx.inc"
        OUTPUT "wait.rom"
        ORG $4000
        CART_HEADER init        ; "AB" and init's address
init:   di                      ; interrupts off
        ld a, LIGHT_GREEN       ; the value: colour 3
        out (VDP_CTRL), a
        ld bc, 0                ; 65,536 turns of 30 T
wait:   dec bc
        ld a, b
        or c
        jr nz, wait
        ld a, $80 | 7           ; $80 + register number
        out (VDP_CTRL), a       ; register 7: the border
stop:   jr stop                 ; for ever
        ds $8000 - $, $FF       ; fill to 16 KB
