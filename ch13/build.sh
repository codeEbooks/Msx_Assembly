#!/bin/sh
# build.sh -- assemble the programs of chapter 13, with --syntax=bF (chapter 8)
cd "$(dirname "$0")"
for f in copy overlap cpir flip lines sine qsmul moire cost otir; do
  sjasmplus --nologo --msg=err --syntax=bF --sym=$f.sym $f.asm || exit 1
done
