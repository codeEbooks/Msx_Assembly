# flags.tcl - written by measA.py: openMSX's breakpoints for flags.rom
proc H {a n} { binary scan [debug read_block memory $a $n] H* h; return $h }
L "I [reg r] [debug read ioports 0xA8]"
debug set_bp 0x40DE {} {L "A [reg af] [reg bc] [reg de] [reg hl] [reg ix] [reg iy] [reg sp] [reg i] [reg r] [reg iff] [reg im] [reg af2] [reg bc2] [reg de2] [reg hl2] [H 0xE1FC 8] [H 0xE20E 4]"}
debug set_bp 0x40FB {} {L done; exit}
