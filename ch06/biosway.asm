; biosway.asm -- chapter 5: the same border, through the BIOS
        INCLUDE "msx.inc"
        OUTPUT "biosway.rom"
        ORG $4000
WRTVDP  EQU $0047               ; BIOS: register C <- B
        CART_HEADER init        ; "AB" and init's address
init:   di                      ; interrupts off
        ld b, LIGHT_GREEN       ; the value
        ld c, 7                 ; the register
        call WRTVDP
stop:   jr stop                 ; for ever
        ds $8000 - $, $FF       ; fill to 16 KB
