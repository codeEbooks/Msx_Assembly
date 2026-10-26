#!/usr/bin/env python3
"""gen06.py - the programs of chapter 6.

    python3 gen06.py && ./build.sh

The debugger is the subject of chapter 6, not a new program: the sessions in
the chapter stop, step and watch two programs of chapter 5, written here again
with chapter 5's own generator so that this folder is complete in itself.

    border.asm   chapter 5's first program: the border turns light green
    biosway.asm  the same through the BIOS's WRTVDP: a CALL to step over
    time.tcl     the chapter's measuring script: T-states from INIT to stop
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "ch05"))
import gen05  # noqa: E402

TIME_TCL = """# time.tcl -- chapter 6: the T-states border.rom takes from INIT to stop.
# openmsx -machine MSXBOOK_EU16 -carta border.rom -script time.tcl
debug set_bp 0x4010 {} { set ::t0 [machine_info time] }
debug set_bp 0x4019 {} {
    if {[info exists ::t0]} {
        set t [expr {([machine_info time] - $::t0) * 3579545}]
        message "INIT to stop: [expr {round($t)}] T-states"
        unset ::t0
    }
}
"""


def main():
    files = {name: text for name, text in gen05.sources().items()
             if name in ("border.asm", "biosway.asm")}
    files["time.tcl"] = TIME_TCL
    for name, text in files.items():
        with open(os.path.join(HERE, name), "w") as f:
            f.write(text)
    print(len(files), "files written")


if __name__ == "__main__":
    main()
