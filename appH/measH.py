#!/usr/bin/env python3
"""measH.py -- Appendix H's measurements: every mistake of the book run again.

    python3 measH.py [step ...] [chNN ...]

    chapters  the measuring program of each chapter with a mistake, run again
              in a copy of its folder without its results (no meas*.json, no
              captures, no shots; the copy's neighbours are links to the
              repository's other folders, which the programs read and do not
              write), with the steps that measure its broken programs and the
              steps those need first, in the order of the program's own
              table; then every value the appendix takes from it is compared
              with the one the chapter delivered
    gallery   the photographs of figure H.1, filmed again from the broken
              programs, each against the chapter's own photograph of it

Chapter numbers after the steps limit "chapters" to those folders. Writes
measH.json, and captures/ for the gallery.
"""
import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
RESULTS = HERE / "measH.json"
sys.path.insert(0, str(REPO / "tools"))


def load():
    return json.loads(RESULTS.read_text()) if RESULTS.exists() else {}


def save(res):
    RESULTS.write_text(json.dumps(res, indent=1, sort_keys=True) + "\n")


# ---------------------------------------------------------------- the cases
# id: (folder, steps of its measuring program, the values compared: those the
# appendix takes from the case and others its chapter measured with them, none
# inside another). "ALL": the program takes no steps and measures everything.
# The id is the chapter and the mistake's number in the census of the book.
CASES = {
    "01_1": ("ch01", ["ALL"], [
        "sprites.y208.visible_of_on_screen",
        "sprites.y209.visible_of_on_screen"]),
    "02_1": ("ch02", ["ALL"], [
        "addr.addr_hex.bytes[0][1]",
        "addr.addr_hex.bytes[1][1]",
        "addr.addr_hex.bytes[2][1]",
        "addr.addr_hex.bytes[3][1]",
        "addr.addr_dec.bytes[0][1]",
        "addr.addr_dec.bytes[1][1]",
        "addr.addr_dec.bytes[2][1]",
        "addr.addr_dec.bytes[3][1]",
        "addr.addr_dec.vram_addr",
        "addr.addr_dec.changed",
        "addr.addr_dec.vram_at",
        "addr.addr_dec.vram_names_row0",
        "addr.addr_dec.top_row",
        "addr.addr_hex.ink",
        "addr.addr_dec.ink"]),
    "03_1": ("ch03", ["ALL"], [
        "page0.page0_di.sum",
        "page0.page0_di.look_T",
        "page0.page0_di.look_frames",
        "page0.page0_di.counted",
        "page0.page0_ei.counted",
        "page0.page0_ei.pc",
        "page0.page0_ei.iff",
        "page0.page0_ei.sp",
        "page0.page0_ei.ram_pattern_bytes",
        "page0.page0_ei.ram_all_pattern"]),
    "04_1": ("ch04", ["check", "default_setting"], [
        "check.default.bios_sum",
        "check.default.bios_file",
        "check.default.b002D",
        "check.default.msx",
        "check.default.hz",
        "check.default.turns",
        "check.book_eu.turns",
        "check.default.ram_from",
        "default_setting.second_start"]),
    "04_2": ("ch04", ["case"], [
        "case.linux.rc",
        "case.linux.lines",
        "case.windows.rc",
        "case.windows.lines[2]"]),
    "05_1": ("ch05", ["ba"], [
        "ba.settled_from",
        "ba.init_called",
        "ba.border",
        "ba.text"]),
    "05_2": ("ch05", ["errors", "assembly"], [
        "errors.typo.rc",
        "errors.typo.errors",
        "errors.typo.rom_written",
        "errors.typo.R7",
        "errors.typo.border_frame60",
        "assembly.rom_bytes"]),
    "05_3": ("ch05", ["errors", "assembly"], [
        "errors.margin.rc",
        "errors.margin.errors",
        "errors.margin.code",
        "errors.margin.R7",
        "errors.margin.border_frame60"]),
    "05_5": ("ch05", ["noend"], [
        "noend.bytes_walked",
        "noend.rst38_before_page2",
        "noend.first_ff_frame",
        "noend.page2_frame",
        "noend.t_per_byte",
        "noend.vram_writes_in_page2",
        "noend.back_frame",
        "noend.back_to",
        "noend.end_frame",
        "noend.end_bytes",
        "noend.photos_alike"]),
    "06_1": ("ch06", ["dollar"], [
        "dollar.session[0][1]",
        "dollar.session[1][1]",
        "dollar.session[2][1]",
        "dollar.session[3][1]",
        "dollar.bios_byte_4010"]),
    "07_1": ("ch07", ["loop"], [
        "loop.loop.pc",
        "loop.loop.bc",
        "loop.clock.decs",
        "loop.clock.turn",
        "loop.clock.wraps",
        "loop.clock.seconds",
        "loop.loop_ok.pc",
        "loop.loop_ok.bc"]),
    "07_2": ("ch07", ["listings"], [
        "listings.fake.listing[0].bytes",
        "listings.fake.listing[1].bytes",
        "listings.fake.syntax.default.said",
        "listings.fake.syntax[\"--syntax=f\"].said[0]",
        "listings.fake.syntax[\"--syntax=F\"].exit"]),
    "08_1": ("ch08", ["selfmod"], [
        "selfmod.rpatch",
        "selfmod.mpatch",
        "selfmod.results[0]",
        "selfmod.results[1]",
        "selfmod.disasm[0]",
        "selfmod.disasm[1]"]),
    "08_2": ("ch08", ["paren"], [
        "paren.listing[1].bytes",
        "paren.listing[2].bytes",
        "paren.settings.err.messages",
        "paren.settings.war.messages[0]",
        "paren.settings.b.exit"]),
    "09_1": ("ch09", ["stale"], [
        "stale.left",
        "stale.cleared"]),
    "10_1": ("ch10", ["friction"], [
        "friction.from[0]",
        "friction.from[1]",
        "friction.lists[0]",
        "friction.lists[1]",
        "friction.lists[2]"]),
    "11_1": ("ch11", ["cmp"], [
        "cmp.differ",
        "cmp.opposite",
        "cmp.pairs"]),
    "12_1": ("ch12", ["popsum", "cost", "irq"], [
        "cost.rows[3].t",
        "irq.bytes",
        "popsum.sum",
        "popsum.off",
        "popsum.interrupts",
        "popsum.on[0]",
        "popsum.on[1]",
        "popsum.on[2]",
        "popsum.on[3]",
        "popsum.damaged"]),
    "12_2": ("ch12", ["lost"], [
        "lost.sp",
        "lost.left",
        "lost.pc",
        "lost.lost"]),
    "12_3": ("ch12", ["top"], [
        "top.depth",
        "top.sp_deep",
        "top.isr_after",
        "top.hook_after",
        "top.hook_bytes",
        "top.way_back",
        "top.zero_after",
        "top.frames_to_init",
        "top.init_sp",
        "top.hook_after_restart"]),
    "13_1": ("ch13", ["cpir"], [
        "cpir.rows[2].z",
        "cpir.rows[2].pv",
        "cpir.rows[2].bc",
        "cpir.rows[3].z",
        "cpir.rows[3].pv",
        "cpir.rows[3].bc"]),
    "14_1": ("ch14", ["slow"], [
        "slow.zilog",
        "slow.turns",
        "slow.wait",
        "slow.over",
        "slow.lines_over",
        "slow.nops_zilog",
        "slow.nops"]),
    "15_1": ("ch15", ["big"], [
        "big.with_tail",
        "big.cartridges",
        "big.warnings.said[0]",
        "big.bF.exit",
        "big.bytes",
        "big.seen",
        "big.away",
        "big.changed",
        "big.chars[0]",
        "big.chars[1]",
        "big.names",
        "big.bF.said",
        "big.bFw.exit"]),
    "16_1": ("ch16", ["ints"], [
        "ints.before",
        "ints.after",
        "ints.isr_inside",
        "ints.each",
        "ints.jiffy",
        "ints.isr_during_chput"]),
    "16_3": ("ch16", ["chget"], [
        "chget.pressed",
        "chget.key",
        "chget.returned_frame",
        "chget.scncnt",
        "chget.early_pressed[0]",
        "chget.early_pressed[1]"]),
    "17_1": ("ch17", ["forgot"], [
        "forgot.per_frame[\"1\"]",
        "forgot.period",
        "forgot.ret",
        "forgot.turns_frozen",
        "forgot.pixels"]),
    "17_2": ("ch17", ["paint"], [
        "paint.unsaved.bands[0]",
        "paint.unsaved.bands[9]",
        "paint.unsaved.isr_at",
        "paint.saved.bands"]),
    "17_3": ("ch17", ["late"], [
        "late.rows[0].off",
        "late.rows[0].signals",
        "late.rows[0].after_ei",
        "late.rows[1].off",
        "late.rows[1].signals",
        "late.rows[1].after_ei",
        "late.rows[2].off",
        "late.rows[2].signals",
        "late.rows[2].after_ei"]),
    "17_5": ("ch17", ["keys"], [
        "keys.nokeys.pc_end",
        "keys.nokeys.ticks",
        "keys.nokeys.jiffy",
        "keys.nokeys.returned",
        "keys.chain.returned",
        "keys.steal.jiffy",
        "keys.steal.returned"]),
    "18_1": ("ch18", ["lines", "wrong"], [
        "wrong.turn_measured",
        "wrong.turns[0][1]",
        "wrong.turns[1][1]",
        "wrong.turns[2][1]",
        "wrong.moved",
        "wrong.seen[0].x0",
        "wrong.seen[11].x0",
        "wrong.fits[0]"]),
    "18_2": ("ch18", ["seconds"], [
        "seconds.MSXBOOK_EU16.film_frames",
        "seconds.MSXBOOK_JP16.film_frames",
        "seconds.MSXBOOK_EU16.seconds",
        "seconds.MSXBOOK_JP16.seconds"]),
    "19_1": ("ch19", ["split", "fixed"], [
        "split.frames",
        "split.ticks",
        "split.hits"]),
    "19_2": ("ch19", ["regs"], [
        "regs.rows[1].ptr",
        "regs.rows[2].ptr",
        "regs.rows[3].ptr",
        "regs.rows[4].ptr",
        "regs.star_at",
        "regs.r0[7]"]),
    "20_1": ("ch20", ["page"], [
        "page.otir.lost",
        "page.otir.rows_right",
        "page.otir.start[0]",
        "page.otir.end[0]",
        "page.outi.lost",
        "page.outi.start[0]",
        "page.outi.end[0]"]),
    "21_1": ("ch21", ["bits"], [
        "bits.eu[4].ink_pixels",
        "bits.eu[1].film"]),
    "22_1": ("ch22", ["leak"], [
        "leak.eu.m3.regs[4]",
        "leak.eu.m3.regs[3]",
        "leak.eu.m3.reads.colours",
        "leak.eu.m3.wrong_no_rule6",
        "leak.jp.m3.wrong_no_rule6",
        "leak.eu.m3.wrong",
        "leak.eu.after_table[0]",
        "leak.eu.fix.reads.colours",
        "leak.eu.fix.regs[3]",
        "leak.eu.shape_differs.fix"]),
    "23_1": ("ch23", ["ways"], [
        "ways.zero.summary.wrong[0]",
        "ways.zero.summary.wrong[1]"]),
    "24_1": ("ch24", ["meta", "copies", "prices", "answers"], [
        "answers.q2.jp",
        "copies.full.summary.jp.into_paper",
        "copies.full.summary.jp.fast_per_send[0]",
        "copies.full.summary.jp.fast_per_send[1]",
        "copies.full.summary.jp.fast",
        "copies.full.summary.jp.frames_wrong",
        "copies.full.jp.wrong_names"]),
    "25_1": ("ch25", ["fan", "hidden"], [
        "hidden.hidden.eu.set",
        "hidden.hidden.eu.inside",
        "hidden.hidden.cells",
        "hidden.hidden.eu.seen",
        "hidden.shown.eu.seen"]),
    "26_1": ("ch26", ["fall"], [
        "fall.fall.eu.frames",
        "fall.fall.eu.lost_at_y[0]",
        "fall.fall.eu.seen_when_lost[0]",
        "fall.fall.eu.figure_pixels",
        "fall.park.eu.frames",
        "fall.last.eu.frames"]),
    "26_2": ("ch26", ["tear"], [
        "tear.eu.first_new[0]",
        "tear.eu.taken_line[0]",
        "tear.eu.write_t",
        "tear.jp.write_t",
        "tear.eu.taken_t",
        "tear.jp.taken_t"]),
    "27_1": ("ch27", ["adaptive", "reads"], [
        "adaptive.poll.eu.frames",
        "adaptive.poll.eu.found_f[0]",
        "adaptive.poll.eu.ored[0]",
        "reads.eu.reads",
        "reads.jp.reads",
        "reads.eu.with_5s",
        "reads.eu.runs[1][0]",
        "reads.eu.lines_5s[0]",
        "reads.eu.lines_5s[1]",
        "reads.eu.runs[2][0]",
        "reads.eu.runs[33][1]",
        "reads.eu.runs[33][0]",
        "reads.eu.runs[34][0]",
        "adaptive.keep.eu.shown_per_figure[0]",
        "adaptive.keep.eu.frames",
        "reads.eu.runs[33][2]"]),
    "27_2": ("ch27", ["five"], [
        "five.eu.seen[0][1]",
        "five.eu.seen[4][1]",
        "five.eu.seen[4][0]",
        "five.eu.ball_lines[0]",
        "five.eu.ball_lines[1]",
        "five.eu.rule10_pixels"]),
    "28_1": ("ch28", ["cross"], [
        "cross.overlap.eu.off_ideal"]),
    "29_1": ("ch29", ["pillar"], [
        "pillar.eu.off_ideal[0].level",
        "pillar.eu.off_ideal[1].level",
        "pillar.eu.off_ideal[2].level",
        "pillar.eu.off_ideal[3].level",
        "pillar.eu.off_ideal[4].level",
        "pillar.eu.off_ideal[5].level",
        "pillar.eu.off_ideal[6].level",
        "pillar.eu.off_ideal[7].level"]),
    "30_1": ("ch30", ["bar"], [
        "bar.jp.bar_ink",
        "bar.eu.bar_ink",
        "bar.jp.bar",
        "bar.jp.label"]),
    "31_1": ("ch31", ["fixed"], [
        "fixed.jp.after[0]",
        "fixed.jp.end_line",
        "fixed.jp.fast",
        "fixed.jp.wrong_end",
        "fixed.jp.off"]),
    "32_1": ("ch32", ["crowd"], [
        "crowd.eu.bar_line[0]",
        "crowd.eu.bar_line[1]",
        "crowd.eu.bar_line[8]",
        "crowd.eu.jumped",
        "crowd.eu.frames",
        "crowd.eu.hidden_lines[9]",
        "crowd.eu.hidden_px[9]",
        "crowd.eu.hidden_px[8]",
        "crowd.eu.hidden_px[0]"]),
    "33_1": ("ch33", ["first"], [
        "first.eu.torn[0].send[0]",
        "first.eu.torn[0].fast",
        "first.eu.torn[0].wrong",
        "first.eu.torn[0].send[1]",
        "first.eu.torn[0].off"]),
    "34_1": ("ch34", ["rowonly"], [
        "rowonly.rowonly.portc",
        "rowonly.matrix.portc",
        "rowonly.rowonly.caps[0][1]",
        "rowonly.rowonly.tape_from",
        "rowonly.rowonly.tape_per_frame[0]",
        "rowonly.rowonly.tape_end",
        "rowonly.matrix.caps",
        "rowonly.matrix.tape_end"]),
    "34_2": ("ch34", ["matrix", "layouts"], [
        "matrix.ghost.held",
        "matrix.ghost.extra",
        "layouts.machines.with_ppi",
        "layouts.machines.ghosting_on",
        "layouts.machines.sgc.true",
        "layouts.machines.sgc.false",
        "layouts.machines.ghosting_off",
        "matrix.eu.combos[\"RIGHT+SPACE+S\"][5]",
        "matrix.jp.combos[\"RIGHT+SPACE+S\"][5]"]),
    "35_1": ("ch35", ["leftover"], [
        "leftover.eu.wrong",
        "leftover.eu.frames",
        "leftover.eu.first"]),
    "36_1": ("ch36", ["mixer", "standard"], [
        "mixer.script[1][1][0]",
        "mixer.script[2][1][0]",
        "mixer.script[3][1][0]",
        "mixer.eu.seen[\"70\"][1]",
        "mixer.p.dead_from",
        "mixer.p.seen[\"41\"][2]",
        "mixer.p.seen[\"71\"][2]",
        "mixer.script[3][0]",
        "mixer.p.seen[\"115\"][2]",
        "mixer.p.dead",
        "standard.machines",
        "standard.ignorePortDirections.false",
        "standard.ignorePortDirections.true",
        "standard.ignorePortDirections.unsaid",
        "mixer.eu.dead",
        "mixer.jp.dead"]),
    "37_1": ("ch37", ["latch"], [
        "latch.eu.frames",
        "latch.eu.r15_byte",
        "latch.eu.louder",
        "latch.eu.own_level_back",
        "latch.jp.frames",
        "latch.jp.r15_byte",
        "latch.jp.louder",
        "latch.jp.own_level_back",
        "latch.eu.r14_misreads",
        "latch.jp.r14_misreads"]),
    "37_2": ("ch37", ["pace", "photos"], [
        "pace.fast.jp.seconds",
        "pace.tune.eu.seconds",
        "pace.tune.jp.seconds",
        "pace.fast.jp.ticks_in_313_frames",
        "photos.fast_jp.seen[\"779\"].barno",
        "photos.fast_jp.seen[\"779\"].rowno",
        "photos.tune_jp.seen[\"779\"].barno",
        "photos.tune_jp.seen[\"779\"].rowno"]),
    "38_1": ("ch38", ["breaks", "carts"], [
        "breaks.logo_text",
        "breaks[\"stay32 eu\"].path[7][0]",
        "breaks[\"stay32 eu\"].back.vram_writes",
        "breaks[\"stay32 eu\"].back.T",
        "carts.stay32.eu.sum",
        "breaks[\"stay32 eu64\"].c000.rst",
        "breaks[\"stay32 eu64\"].c000.frame"]),
    "38_2": ("ch38", ["breaks"], [
        "breaks[\"quick32 eue\"].c000.rst",
        "breaks[\"quick32 eue\"].T_per_byte",
        "breaks[\"quick32 eue\"].c000.frame",
        "breaks[\"quick32 eue\"].rst_total",
        "breaks[\"quick32 eue\"].ended"]),
    "38_3": ("ch38", ["carts", "enaslt"], [
        "carts.cart32.eue.page2",
        "carts.cart32.eue.line",
        "enaslt.cbios.slttbl1",
        "enaslt.cbios.a8_writes",
        "enaslt.cbios.ffff_write.byte",
        "enaslt.cbios.ram_ffff[0]",
        "enaslt.cbios.register1",
        "enaslt.fixed.a8_writes",
        "enaslt.fixed.register1[1]",
        "enaslt.fails"]),
    "39_1": ("ch39", ["walls", "flags", "shapes", "pairs", "prices", "answers"], [
        "pairs.blame.stopped[0]",
        "pairs.blame.apart_at_stop[0][0]",
        "pairs.blame.apart_at_stop[0][1]",
        "answers.q9.further[0].apart[0]",
        "answers.q9.further[1].apart[0]"]),
    "40_1": ("ch40", ["films", "prices"], [
        "prices.redraw",
        "films.blink.eu.torn",
        "films.blink.eu.pictures",
        "films.blink.eu.torn_cells",
        "films.blink.jp.torn_cells",
        "films.blink.eu.torn_places"]),
    "41_1": ("ch41", ["rreg"], [
        "rreg.eu.count",
        "rreg.eu.differences",
        "rreg.eu.halts[1].r_up",
        "rreg.eu.halts[2].r_up",
        "rreg.jp.halts[5].r_up",
        "rreg.jp.halts[1].r_up"]),
    "42_1": ("ch42", ["films", "prices"], [
        "films.over.jp.summary.loops",
        "films.over.jp.summary.lost",
        "prices.nextwin_once",
        "prices.mark",
        "films.over.jp.summary.lost_loops"]),
    "43_1": ("ch43", ["films"], [
        "films.game.jp.events[24][0]",
        "films.stale.eu.touches[1].loop",
        "films.stale.eu.touches[1].lag",
        "films.stale.eu.touches[2].loop",
        "films.stale.eu.events[29][0]"]),
    "44_1": ("ch44", ["films"], [
        "films.extra.jp.events[33][0]",
        "films.extra.jp.events[33][2]",
        "films.extra.jp.events[21][0]"]),
    "45_1": ("ch45", ["films", "prices", "photos"], [
        "prices.flip0_old[3]",
        "prices.flip0_new[4]",
        "films.torn.jp.pages[23].t",
        "films.torn.jp.pages[21].t",
        "films.torn.jp.pages[23].behind",
        "films.torn.jp.pages[21].behind",
        "films.torn.eu.pages[21].behind",
        "films.game.jp.summary.to_paper",
        "films.game.eu.summary.to_paper",
        "prices.runs[4]"]),
    "46_1": ("ch46", ["films"], [
        "films.late.jp.events[28][0]",
        "films.late.jp.events[28][1]",
        "films.late.eu.events[28][0]",
        "films.late.eu.events[28][1]",
        "films.late.jp.events[26][4][0]",
        "films.late.jp.events[26][4][1]"]),
    "48_1": ("ch48", ["films", "mappers", "photos"], [
        "mappers.types.guess.type",
        "mappers.types.guess.votes.ascii16",
        "mappers.types.guess.votes.konamiscc",
        "mappers.types.guess.lds[\"7000\"]",
        "films.guess.jp.type",
        "photos.guess.jp.figs[0]",
        "photos.guess.jp.figs[1]",
        "films.guess.jp.wrong.frames",
        "mappers.types.long.type",
        "mappers.types.long.lds[\"77FF\"]"]),
    "48_2": ("ch48", ["films", "prices", "photos"], [
        "photos.long.jp.loops[1]",
        "films.far.jp.wrong.runs[0][0]",
        "films.far.jp.wrong.runs[0][1]",
        "films.far.jp.wrong.pixels[0]",
        "films.far.jp.wrong.pixels[1]",
        "films.far.jp.wrong.frames",
        "prices.long_sends[\"a frame\"]",
        "prices.far_sends[\"a frame\"]"]),
    "49_1": ("ch49", ["recordings", "quality", "prices", "answers", "pieces"], [
        "prices.skip[\"a new sample\"]",
        "prices.skip[\"the same\"]",
        "prices.play3",
        "answers.q4.short",
        "prices.sizes.three.sound",
        "quality.three.jp.vowel[0].begins",
        "quality.skip.jp.vowel[0].begins",
        "quality.three.jp.vowel[0].lasts",
        "quality.skip.jp.vowel[0].lasts",
        "quality.three.jp.vowel[0].band_grid",
        "quality.skip.jp.vowel[0].band_grid",
        "quality.skip.jp.vowel[0].band",
        "recordings.skip.jp.gaps[\"465\"]",
        "recordings.skip.jp.gaps[\"790\"]"]),
    "50_1": ("ch50", ["fixed"], [
        "fixed.wav.jp.d",
        "fixed.wav.jp.loaded",
        "fixed.cas.jp.loaded",
        "fixed.cas.jp.longest",
        "fixed.cas.eu.longest",
        "fixed.cas.eu.loaded",
        "fixed.cas.jp.hs",
        "fixed.cas.jp.page_end[2]"]),
    "51_1": ("ch51", ["machines", "which", "games"], [
        "games[\"44\"].MSXBOOK_EU8.first",
        "games[\"44\"].MSXBOOK_EU8.start.isr",
        "games[\"44\"].MSXBOOK_EU8.start.main",
        "games[\"46\"].MSXBOOK_EU8.first",
        "games[\"46\"].MSXBOOK_EU8.start.isr",
        "games[\"46\"].MSXBOOK_EU8.start.main"]),
    "51_2": ("ch51", ["machines", "blind"], [
        "blind.MSXBOOK_EU16.text[5]",
        "blind.MSXBOOK_EU16.regs[7]",
        "blind.MSXBOOK_EU16.s0",
        "blind.MSXBOOK_EU16.program.s1",
        "blind.MSXBOOK_EU16.program.kept[0]",
        "blind.MSXBOOK_EU16.program.kept[1]",
        "blind.MSXBOOK_EU16.program.kept[2]",
        "blind.MSXBOOK_EU16.program.kept[3]",
        "machines.MSXBOOK_EU16.vdp",
        "machines.MSXBOOK_EU16.bios"]),
    "52_2": ("ch52", ["films", "photos"], [
        "photos.corners.settled_loop",
        "photos.corners.piles[\"right top\"]",
        "photos.corners.piles[\"left bottom\"]",
        "photos.corners.piles[\"right bottom\"]",
        "photos.corners.piles[\"left top\"]",
        "films.inrom.jp.summary.score",
        "photos.corners.last_score_loop",
        "films.patch.jp.summary.score",
        "films.inrom.jp.summary.bumps",
        "films.inrom.jp.summary.loops",
        "films.patch.jp.summary.bumps",
        "films.inrom.eu.summary.bumps",
        "films.patch.eu.summary.bumps"]),
    "53_1": ("ch53", ["films", "photos"], [
        "films.otir.eu.fast",
        "films.otir.jp.fast",
        "films.otir.eu.lost",
        "films.otir.jp.lost",
        "films.otir.eu.damage.first_row",
        "films.otir.jp.damage.first_row",
        "films.otir.eu.damage.patterns",
        "films.otir.jp.damage.patterns",
        "films.otir.eu.damage.colours",
        "films.dark.eu.fast",
        "films.dark.jp.fast",
        "photos.dark.eu.complete"]),
    "54_1": ("ch54", ["demo"], [
        "demo.broken.touches[0]",
        "demo.broken.touches[1]",
        "demo.broken.touches[2]",
        "demo.broken.ended_loop",
        "demo.broken.ended[0]",
        "demo.broken.ended[1]",
        "demo.broken.ended[5]",
        "demo.broken.jp_loops_same"]),
    "55_1": ("ch55", ["runs"], [
        "runs.dirty.MSXBOOK_EU16B.least",
        "runs.dirty.MSXBOOK_EU16S.least",
        "runs.dirty.MSXBOOK_EU16.least",
        "runs.dirty.MSXBOOK_EU16B.least_model",
        "runs.dirty.MSXBOOK_EU16B.ram",
        "runs.dirty.MSXBOOK_EU16B.lost"]),
    "56_1": ("ch56", ["files", "release", "guess"], [
        "guess.page12.inits[0]",
        "guess.page12.inits[1]",
        "guess.page12.period",
        "guess.page12.runs",
        "release.wrong.boards[0].inits",
        "files.lantern_keep.init"]),
}


def get(d, path):
    """the value at PATH in D: names joined by dots, [n] and ["key"]"""
    for name, sub in re.findall(r'(?:^|\.)([^.\[\]]+)|\[("[^"]*"|\d+)\]', path):
        if name:
            d = d[name]
        else:
            d = d[json.loads(sub)] if sub.startswith('"') else d[int(sub)]
    return d


def short(v):
    """a value as the json keeps it: itself if short, else its length and
    SHA-256"""
    text = json.dumps(v, sort_keys=True)
    return v if len(text) <= 200 else {"json_bytes": len(text),
                                       "sha256": hashlib.sha256(text.encode()).hexdigest()}


def program_of(folder):
    return sorted((REPO / folder).glob("meas[0-9]*.py"))[0]


def table_of(program):
    """the names of a measuring program's steps, in the order of its table
    (SECTIONS or STEPS), or None"""
    tree = ast.parse(program.read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict) and \
                any(isinstance(t, ast.Name) and t.id in ("SECTIONS", "STEPS") for t in node.targets):
            return [k.value for k in node.value.keys if isinstance(k, ast.Constant)]
    return None


def steps_of(folder):
    """the steps a folder's cases need, in the order of the program's table"""
    want = []
    for f, steps, _ in CASES.values():
        if f == folder:
            want += [s for s in steps if s not in want]
    if want == ["ALL"]:
        return []
    assert "ALL" not in want, folder
    table = table_of(program_of(folder))
    assert table and set(want) <= set(table), (folder, want, table)
    return [s for s in table if s in want]


def check_cases():
    """every case's keys under its steps, and no key inside another of its
    folder"""
    for case, (folder, steps, keys) in CASES.items():
        tops = {re.match(r"[^.\[]+", k).group(0) for k in keys}
        assert steps == ["ALL"] or tops <= set(steps), (case, tops, steps)
    for folder in {f for f, _, _ in CASES.values()}:
        keys = [k for f, _, ks in CASES.values() if f == folder for k in ks]
        for a in keys:
            for b in keys:
                assert a == b or not (b.startswith(a + ".") or b.startswith(a + "[")), (a, b)


MADE = ("captures", "shots")           # what the steps fill, emptied in the copy


def copy_of(folder, work):
    """WORK/FOLDER: the chapter's folder without what its measuring program
    makes (photographs, results) and without compiled Python; WORK's other
    entries point at the repository's"""
    for p in REPO.iterdir():
        if p.name != folder:
            (work / p.name).symlink_to(p)
    dst = work / folder
    shutil.copytree(REPO / folder, dst, symlinks=True,
                    ignore=shutil.ignore_patterns(*MADE, "__pycache__", "meas[0-9]*.json"))
    (dst / (program_of(folder).stem + ".json")).write_text("{}\n")   # some add their steps to one
    for d in MADE:
        if (REPO / folder / d).is_dir():
            (dst / d).mkdir()
    return dst


def fingerprint():
    """every file of the repository but appH's and compiled Python: its size
    and modification time"""
    out = {}
    for p in REPO.rglob("*"):
        if p.is_file() and "__pycache__" not in p.parts and p.parts[len(REPO.parts)] != "appH":
            st = p.stat()
            out[str(p.relative_to(REPO))] = (st.st_size, st.st_mtime_ns)
    return out


def chapters(res, only=()):
    """each chapter's measuring program again, in a copy, from nothing"""
    check_cases()
    out = res.get("chapters", {})
    folders = sorted({f for f, _, _ in CASES.values()})
    env = {k: v for k, v in os.environ.items() if k != "OPENMSX_BUILDS"}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    for folder in folders:
        if only and folder not in only:
            continue
        before = fingerprint()
        steps = steps_of(folder)
        program = program_of(folder)
        work = Path(tempfile.mkdtemp(prefix="measH-"))
        try:
            dst = copy_of(folder, work)
            t0 = time.monotonic()
            p = subprocess.run([sys.executable, "-B", program.name, *steps], cwd=dst, env=env,
                               stdin=subprocess.DEVNULL, capture_output=True, text=True,
                               timeout=4 * 3600)
            took = round(time.monotonic() - t0)
            made = dst / (program.stem + ".json")
            fresh = json.loads(made.read_text()) if made.exists() else {}
        finally:
            shutil.rmtree(work, ignore_errors=True)
        touched = sorted(k for k, v in fingerprint().items() if before.get(k) != v)
        delivered = json.loads((REPO / folder / (program.stem + ".json")).read_text())
        for case, (f, _, keys) in CASES.items():
            if f != folder:
                continue
            r = {"folder": folder, "steps": steps or ["ALL"], "exit": p.returncode,
                 "seconds": took, "differ": [], "values": {}, "touched": touched}
            for k in keys:
                try:
                    now = get(fresh, k)
                except (KeyError, IndexError, TypeError):
                    now = "missing"
                if now != get(delivered, k):
                    r["differ"].append(k)
                r["values"][k] = short(now)
            out[case] = r
            print("chapters", case, folder, "exit", p.returncode, "differ", r["differ"],
                  "touched", touched[:5], f"({took} s)", flush=True)
        if p.returncode:
            print(p.stdout[-2000:], p.stderr[-3000:], flush=True)
        res["chapters"] = {k: out[k] for k in sorted(out)}
        save(res)


# ---------------------------------------------------------------- figure H.1
# key: (folder, the program, the machine, the frame, "init" for a film from
# INIT or "power" for one from power-on, openMSX's arguments, the chapter's
# photograph of it)
EU, JP = "MSXBOOK_EU16", "MSXBOOK_JP16"
GALLERY = {
    "ba": ("ch05", "ba.rom", EU, 400, "power", [], "ba_p0400.png"),
    "wrong_board": ("ch56", "lantern_keep_a14.bin", EU, 137, "power", ["-romtype", "page12"],
                    "wrong_board.png"),
    "forgot": ("ch17", "forgot.rom", EU, 10, "init", [], "forgot_f0010.png"),
    "full": ("ch24", "full.rom", JP, 5, "init", [], "full_jp_f0005.png"),
    "otir": ("ch20", "otir.rom", EU, 10, "init", [], "otir_eu_f0010.png"),
    "split": ("ch19", "split.rom", EU, 150, "init", [], "split_eu_f0150.png"),
    "y208": ("ch01", "y208.rom", EU, 30, "init", [], "y208_f0030.png"),
    "overlap": ("ch28", "overlap.rom", EU, 46, "init", [], "overlap_eu_f0046.png"),
    "bits": ("ch21", "bits.rom", EU, 23, "init", [], "bits1_eu_f0023.png"),
    "zero": ("ch23", "zero.rom", EU, 54, "init", [], "zero_eu_f0054.png"),
    "unsaved": ("ch17", "unsaved.rom", EU, 12, "init", [], "unsaved_f0012.png"),
    "stay32": ("ch38", "stay32.rom", EU, 30, "init", [], "stay32_eu_f0030.png"),
}


def film(rom, machine, frame, kind, extra):
    """FRAME of ROM on MACHINE, from INIT or from power-on, with openMSX's
    arguments EXTRA: (the png, its folder)"""
    import msxcap
    tmp = Path(tempfile.mkdtemp(prefix="galH-"))
    if kind == "init":
        return msxcap.capture(rom, [frame], tmp, "g", machine=machine, timeout=900,
                              extra_args=extra)[frame], tmp
    orig = msxcap.run_openmsx

    def run(rom_, machine_, script, home, timeout, extra_args=()):
        return orig(rom_, machine_, script, home, timeout, list(extra_args) + list(extra))
    msxcap.run_openmsx = run
    try:
        got, _, _ = msxcap.film_power(rom, [frame], tmp, "g", machine=machine, timeout=900)
    finally:
        msxcap.run_openmsx = orig
    return got[frame], tmp


def gallery(res):
    """each photograph of figure H.1 filmed again, kept in captures/, and held
    against the chapter's own photograph of the same frame"""
    caps = HERE / "captures"
    caps.mkdir(exist_ok=True)
    out = {}
    for key, (folder, rom, machine, frame, kind, extra, theirs) in GALLERY.items():
        png, tmp = film(REPO / folder / rom, machine, frame, kind, extra)
        dst = caps / f"{key}.png"
        shutil.copy(png, dst)
        shutil.rmtree(tmp, ignore_errors=True)
        mine = dst.read_bytes()
        chapter = (REPO / folder / "captures" / theirs).read_bytes()
        out[key] = {"folder": folder, "rom": rom, "machine": machine, "frame": frame,
                    "from": kind, "extra": extra, "chapter_photo": f"{folder}/captures/{theirs}",
                    "same_file": mine == chapter, "sha256": hashlib.sha256(mine).hexdigest()}
        print("gallery", key, out[key]["same_file"], flush=True)
    res["gallery"] = out


STEPS = {"chapters": chapters, "gallery": gallery}


def main(names=()):
    res = load()
    names = list(names)
    only = [n for n in names if n not in STEPS]
    for n in [n for n in names if n in STEPS] or STEPS:
        if n == "chapters":
            chapters(res, only)
        else:
            STEPS[n](res)
        save(res)


if __name__ == "__main__":
    main(sys.argv[1:])
