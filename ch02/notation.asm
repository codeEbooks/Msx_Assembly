; notation.asm - one byte, written six ways, and a 16-bit number.
; Not a program: assemble it with --lst and read the listing.
        OUTPUT "notation.bin"
        ORG $4000
        db 255          ; decimal
        db $FF          ; hex, as in this book
        db #FF          ; hex, another prefix
        db 0FFh         ; hex, a suffix
        db 0xFF         ; hex, as in C
        db %11111111    ; binary
        dw $1234        ; 16 bits: 2 bytes
        ld hl,$1234     ; an instruction too
