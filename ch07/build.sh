#!/bin/sh
# build.sh -- assemble the cartridges of chapter 7, and the four listings
cd "$(dirname "$0")"
for f in regs cost rcount pairs flags flagtest cond ixh shapes loop loop_ok; do
  sjasmplus --nologo --msg=err --sym=$f.sym $f.asm || exit 1
done
for f in grid families index fake; do
  sjasmplus --nologo --msg=err --lst=$f.lst $f.asm || exit 1
done
