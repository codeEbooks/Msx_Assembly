# hidden.tcl - written by measB.py: openMSX's breakpoints for hidden_1.rom and
# hidden_2.rom: at after and away every register, the bytes at WIN and around
# STK, the PSG's register 0; after the BIT 0,(HL) that follows, F
proc H {a n} { binary scan [debug read_block memory $a $n] H* h; return $h }
L "I [reg r] [debug read ioports 0xA8]"
debug set_bp 0xC810 {} {L "A 0 [reg af] [reg bc] [reg de] [reg hl] [reg ix] [reg iy] [reg sp] [reg i] [reg r] [reg iff] [reg im] [reg af2] [reg bc2] [reg de2] [reg hl2] [H 0xE1FC 8] [H 0xE20E 4] [debug read {PSG regs} 0]"}
debug set_bp 0xC815 {} {L "A 1 [reg af] [reg bc] [reg de] [reg hl] [reg ix] [reg iy] [reg sp] [reg i] [reg r] [reg iff] [reg im] [reg af2] [reg bc2] [reg de2] [reg hl2] [H 0xE1FC 8] [H 0xE20E 4] [debug read {PSG regs} 0]"}
debug set_bp 0xC812 {} {L "P [reg af]"}
debug set_bp 0xC817 {} {L "P [reg af]"}
debug set_bp 0x413A {} {L done; exit}
