#!/usr/bin/env python3
"""gen05.py - the programs of chapter 5, written exactly as the book prints
them: the chapter's programs are meant to be typed, so they carry no line
saying which program wrote them.

    python3 gen05.py && ./build.sh

    border.asm   the first program: the border turns light green
    typo.asm     border.asm with the colour's name misspelt
    margin.asm   border.asm with the first OUT at the left margin
    ba.asm       border.asm with its header's two letters the wrong way round:
                 C-BIOS finds no cartridge (Where it breaks)
    noend.asm    border.asm without its last instruction
    wait.asm     a wait of more than a frame between the two OUTs, with
                 interrupts off: the border still changes
    split.asm    the BIOS's interrupt routine between the two OUTs: it does not
    biosway.asm  the same border through the BIOS's routine WRTVDP
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
COLOUR = "LIGHT_GREEN"      # 176 in grey, against the 109 of C-BIOS's dark blue

HEAD = '''; {name}.asm -- chapter 5: {what}
        INCLUDE "msx.inc"
        OUTPUT "{name}.rom"
        ORG $4000
'''
HEADER = '''        CART_HEADER init        ; "AB" and init's address
'''
FIRST = '''init:   di                      ; interrupts off
        ld a, {colour}       ; the value: colour 3
        out (VDP_CTRL), a
'''
SECOND = '''        ld a, $80 | 7           ; $80 + register number
        out (VDP_CTRL), a       ; register 7: the border
'''
STOP = '''stop:   jr stop                 ; for ever
'''
FILL = '''        ds $8000 - $, $FF       ; fill to 16 KB
'''


def program(name, what, header=HEADER, first=None, between="", stop=STOP):
    first = first if first is not None else FIRST.format(colour=COLOUR)
    return HEAD.format(name=name, what=what) + header + first + between + SECOND + stop + FILL


def sources():
    """{file name: text} of every program of the chapter"""
    return {
        "border.asm": program("border", "the first program. The border turns light green."),
        "typo.asm": program("typo", "a misspelt name. It does not assemble, on purpose.",
                            first=FIRST.format(colour="LIGHT_GREN ")),
        "margin.asm": program("margin", "an OUT at the margin. It does not assemble, on purpose.",
                              first=FIRST.format(colour=COLOUR).replace(
                                  "        out (VDP_CTRL), a\n", "out (VDP_CTRL), a\n")),
        "ba.asm": program("ba", "border.asm with \"BA\" where \"AB\" should be",
                          header='''        db "BA"                 ; the wrong way round
        dw init
        ds 12, 0
'''),
        "noend.asm": program("noend", "border.asm without its last line", stop=""),
        "wait.asm": program("wait", "more than a frame between the two OUTs",
                            between='''        ld bc, 0                ; 65,536 turns of 30 T
wait:   dec bc
        ld a, b
        or c
        jr nz, wait
'''),
        "split.asm": program("split", "the BIOS's interrupt between the two OUTs",
                             first=FIRST.format(colour=COLOUR).replace(
                                 '''init:   di                      ; interrupts off''',
                                 '''init:   ei                      ; interrupts ON'''),
                             between='''        halt                    ; wait for an interrupt
'''),
        "biosway.asm": HEAD.format(name="biosway", what="the same border, through the BIOS") +
        """WRTVDP  EQU $0047               ; BIOS: register C <- B
""" + HEADER + """init:   di                      ; interrupts off
        ld b, LIGHT_GREEN       ; the value
        ld c, 7                 ; the register
        call WRTVDP
""" + STOP + FILL,
    }


def main():
    files = sources()
    for name, text in files.items():
        with open(os.path.join(HERE, name), "w") as f:
            f.write(text)
    print(len(files), "sources written")


if __name__ == "__main__":
    main()
