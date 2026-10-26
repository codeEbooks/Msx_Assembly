; paren.asm - WHERE IT BREAKS. Only LD A loads from an address in the
; instruction. Written for B, the parentheses are just parentheses:
; sjasmplus reads ($C000) as the number $C000, and ($C0) as $C0.
        OUTPUT "paren.bin"
        ORG $4000
        ld a,($C000)            ; the byte at $C000
        ld b,($C000)            ; $00, low byte of $C000
        ld b,($C0)              ; $C0, and not a word
