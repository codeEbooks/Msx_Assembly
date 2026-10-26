#!/bin/sh
# build.sh - assemble the programs of Appendix G (sjasmplus 1.24.0), with
# --syntax=bFw (chapter 15); the probe's listing and symbols too.
set -e
cd "$(dirname "$0")"
sjasmplus --nologo --msg=err --syntax=bFw --sym=probe.sym --lst=probe.lst probe.asm
sjasmplus --nologo --msg=err --syntax=bFw --sym=cart.sym --lst=cart.lst cart.asm
echo "appendix G: probe.bin, cart.rom, their listings and symbols"
