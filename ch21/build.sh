#!/bin/sh
# build.sh -- assemble the programs of chapter 21, with --syntax=bFw (chapter 15)
cd "$(dirname "$0")"
for f in text graphic1 graphic2 multi keep bios chars bands flip bits switch; do
  sjasmplus --nologo --msg=err --syntax=bFw --sym=$f.sym --lst=$f.lst $f.asm || exit 1
done
