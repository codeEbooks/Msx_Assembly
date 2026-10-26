#!/bin/sh
# build.sh -- assemble the programs of chapter 53, with --syntax=bFw (chapter 15)
cd "$(dirname "$0")"
for f in raw rlem rlec lz lzram otir dark; do
  sjasmplus --nologo --msg=err --syntax=bFw --sym=$f.sym --lst=$f.lst $f.asm || exit 1
done
