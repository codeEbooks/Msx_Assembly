; msx.inc -- the canonical header of the MSX Assembly book.
; Ports and addresses of the MSX1 standard, and the cartridge header.

VDP_DATA    EQU $98         ; VRAM data, read and write
VDP_CTRL    EQU $99         ; write: register / address set-up; read: status
PSG_ADDR    EQU $A0         ; PSG register select
PSG_WRITE   EQU $A1         ; PSG data write
PSG_READ    EQU $A2         ; PSG data read
PPI_A       EQU $A8         ; primary slot register
PPI_B       EQU $A9         ; keyboard columns (read)
PPI_C       EQU $AA         ; keyboard row (bits 0-3), cassette, CAPS LED, click
PPI_MODE    EQU $AB         ; PPI control

RAM_START   EQU $C000       ; the book's 16 KB floor: $C000-$FFFF
SYS_AREA    EQU $F380       ; BIOS work area starts here: programs stay below
CGTABL      EQU $0004       ; BIOS: the address of the character set (2 bytes)

; the sixteen colour codes of the VDP (chapter 1 photographed them)
TRANSPARENT  EQU 0
BLACK        EQU 1
MEDIUM_GREEN EQU 2
LIGHT_GREEN  EQU 3
DARK_BLUE    EQU 4
LIGHT_BLUE   EQU 5
DARK_RED     EQU 6
CYAN         EQU 7
MEDIUM_RED   EQU 8
LIGHT_RED    EQU 9
DARK_YELLOW  EQU 10
LIGHT_YELLOW EQU 11
DARK_GREEN   EQU 12
MAGENTA      EQU 13
GREY         EQU 14
WHITE        EQU 15

; cartridge header: "AB", INIT, STATEMENT, DEVICE, TEXT, 6 reserved bytes
    MACRO CART_HEADER init_addr
        db "AB"
        dw init_addr
        dw 0, 0, 0
        ds 6, 0
    ENDM

; write value to VDP register reg (2 OUTs; interrupts must be off)
    MACRO VDP_REG reg, value
        ld a, value
        out (VDP_CTRL), a
        ld a, $80 | (reg)
        out (VDP_CTRL), a
    ENDM

; set the VRAM write address (2 OUTs; interrupts must be off)
    MACRO VRAM_WRITE addr
        ld a, low (addr)
        out (VDP_CTRL), a
        ld a, high (addr) | $40
        out (VDP_CTRL), a
    ENDM
