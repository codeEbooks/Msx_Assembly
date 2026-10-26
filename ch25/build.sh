#!/bin/sh
# build.sh -- assemble the programs of chapter 25, with --syntax=bFw (chapter 15)
cd "$(dirname "$0")"
for f in over cost fan tight buffer through hidden shown; do
  sjasmplus --nologo --msg=err --syntax=bFw --sym=$f.sym --lst=$f.lst $f.asm || exit 1
done
