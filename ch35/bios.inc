; bios.inc -- the BIOS entry points and system variables this book calls by
; name (chapter 16). The MSX standard fixes every address: behind each entry
; point every MSX BIOS, C-BIOS included, has a JP to a routine of its own.
; Call them with page 0 showing the BIOS, as it does when INIT is called.

; entry points
DISSCR   EQU $0041      ; the display off
ENASCR   EQU $0044      ; the display on
WRTVDP   EQU $0047      ; B to VDP register C
RDVRM    EQU $004A      ; A = the byte of the VRAM at HL (chapter 19)
WRTVRM   EQU $004D      ; A to the VRAM at HL
SETRD    EQU $0050      ; the VDP's address set to HL, to read
SETWRT   EQU $0053      ; the VDP's address set to HL, to write
FILVRM   EQU $0056      ; BC bytes of A to the VRAM from HL
LDIRVM   EQU $005C      ; BC bytes from HL to the VRAM at DE
CHGMOD   EQU $005F      ; the screen mode in A
INITXT   EQU $006C      ; text mode, 40 x 24, with the BIOS's tables (chapter 21)
INIT32   EQU $006F      ; Graphic I, 32 x 24
INIGRP   EQU $0072      ; Graphic II
INIMLT   EQU $0075      ; multicolour
CHSNS    EQU $009C      ; Z if no key waits in the buffer (chapter 34)
CHGET    EQU $009F      ; wait for a key; A = its code
CHPUT    EQU $00A2      ; print the character in A
BEEP     EQU $00C0      ; a beep (C-BIOS: none)
GTSTCK   EQU $00D5      ; A = 0: the cursor keys; A = their direction, 0-8
GTTRIG   EQU $00D8      ; A = 0 SPACE, 1-4 a joystick's button: A = $FF if held
SNSMAT   EQU $0141      ; A = the keys of keyboard row A, 0 = held (chapter 34)

; two bytes of data: the VDP's ports, for programs that ask
VDP_DR   EQU $0006      ; the port the VRAM is read from
VDP_DW   EQU $0007      ; the port it is written to

; system variables
LINLEN   EQU $F3B0      ; the width of a line of text
TXTNAM   EQU $F3B3      ; where INITXT puts the tables: names, colours,
TXTCOL   EQU $F3B5      ; patterns, sprite attributes, sprite patterns
TXTCGP   EQU $F3B7      ; (chapter 21); two bytes each
TXTATR   EQU $F3B9
TXTPAT   EQU $F3BB
T32NAM   EQU $F3BD      ; the same for INIT32
T32COL   EQU $F3BF
T32CGP   EQU $F3C1
T32ATR   EQU $F3C3
T32PAT   EQU $F3C5
GRPNAM   EQU $F3C7      ; for INIGRP
GRPCOL   EQU $F3C9
GRPCGP   EQU $F3CB
GRPATR   EQU $F3CD
GRPPAT   EQU $F3CF
MLTNAM   EQU $F3D1      ; for INIMLT
MLTCOL   EQU $F3D3
MLTCGP   EQU $F3D5
MLTATR   EQU $F3D7
MLTPAT   EQU $F3D9
CSRY     EQU $F3DC      ; the cursor's line, from 1
CSRX     EQU $F3DD      ; and its column, from 1
RG0SAV   EQU $F3DF      ; the copy of VDP register n is at RG0SAV + n
STATFL   EQU $F3E7      ; the last status the BIOS read
FORCLR   EQU $F3E9      ; ink, paper and border, for CHGMOD
BAKCLR   EQU $F3EA
BDRCLR   EQU $F3EB
SCNCNT   EQU $F3F6      ; interrupts left before the BIOS reads the keyboard
PUTPNT   EQU $F3F8      ; where the next key goes into the key buffer
GETPNT   EQU $F3FA      ; where CHGET takes the next one from
NEWKEY   EQU $FBE5      ; the eleven rows, as the BIOS last read them
JIFFY    EQU $FC9E      ; one more every frame interrupt
SCRMOD   EQU $FCAF      ; the screen mode
EXPTBL   EQU $FCC1      ; which slots are expanded

; hooks: five bytes each, RET until a program puts a jump there
H_KEYI   EQU $FD9A      ; H.KEYI, every interrupt
H_TIMI   EQU $FD9F      ; H.TIMI, every frame interrupt
H_CHPU   EQU $FDA4      ; H.CHPU, every character CHPUT prints
H_CHGE   EQU $FDC2      ; H.CHGE, every call of CHGET
