; jrfar.asm -- chapter 11: JR as far as it goes. The distance counts from
; the byte after the JR, and it is one signed byte: 127 forward, 128 back.
; Not a cartridge: build.sh assembles it into a listing, jrfar.lst.
        ORG $4000
fwd:    jr ahead                ; 127 bytes on from the next instruction
        ds 127
ahead:  nop
behind: nop
        ds 125
back:   jr behind               ; 128 bytes back from the next instruction
