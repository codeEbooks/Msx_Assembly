#!/bin/sh
# build.sh -- assemble the programs of chapter 14, with --syntax=bF (chapter 8)
cd "$(dirname "$0")"
for f in all price budget slow; do
  sjasmplus --nologo --msg=err --syntax=bF --sym=$f.sym --lst=$f.lst $f.asm || exit 1
done
