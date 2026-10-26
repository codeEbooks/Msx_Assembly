#!/bin/sh
# build.sh -- assemble the programs of chapter 18, with --syntax=bFw (chapter 15)
cd "$(dirname "$0")"
for f in lines ruler paper box f71363 f71364 f71365 f59735 f59736 f59737 wrong; do
  sjasmplus --nologo --msg=err --syntax=bFw --sym=$f.sym --lst=$f.lst $f.asm || exit 1
done
