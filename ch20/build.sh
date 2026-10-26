#!/bin/sh
# build.sh -- assemble the programs of chapter 20, with --syntax=bFw (chapter 15)
cd "$(dirname "$0")"
for f in beat beat12 beat17 beat24 beat25 beat26 probe speeds blank off edge bottom window sprites reads modes otir outi; do
  sjasmplus --nologo --msg=err --syntax=bFw --sym=$f.sym --lst=$f.lst $f.asm || exit 1
done
