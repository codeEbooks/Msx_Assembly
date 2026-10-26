#!/bin/sh
# build.sh -- assemble the programs of chapter 41, with --syntax=bFw (chapter 15)
cd "$(dirname "$0")"
for f in rreg lcg xorshift bits rows states; do
  sjasmplus --nologo --msg=err --syntax=bFw --sym=$f.sym --lst=$f.lst $f.asm || exit 1
done
