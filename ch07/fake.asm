; fake.asm - chapter 7: two instructions the Z80 does not have
; Not a program: assemble it with --lst and read the listing.
        OUTPUT "fake.bin"
        ORG $4000
        ld bc,de                ; sjasmplus takes it
        ld hl,(ix+1)            ; and this
