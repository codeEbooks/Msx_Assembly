# time.tcl -- chapter 6: the T-states border.rom takes from INIT to stop.
# openmsx -machine MSXBOOK_EU16 -carta border.rom -script time.tcl
debug set_bp 0x4010 {} { set ::t0 [machine_info time] }
debug set_bp 0x4019 {} {
    if {[info exists ::t0]} {
        set t [expr {([machine_info time] - $::t0) * 3579545}]
        message "INIT to stop: [expr {round($t)}] T-states"
        unset ::t0
    }
}
