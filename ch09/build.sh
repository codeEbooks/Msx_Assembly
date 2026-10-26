#!/bin/sh
# build.sh -- assemble the programs of chapter 9, with --syntax=bF (chapter 8)
cd "$(dirname "$0")"
for f in cost hist neg times10 add32 hl16 stale widen daa score; do
  sjasmplus --nologo --msg=err --syntax=bF --sym=$f.sym $f.asm || exit 1
done
