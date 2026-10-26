#!/bin/sh
# build.sh -- assemble the programs of chapter 31, with --syntax=bFw (chapter 15)
cd "$(dirname "$0")"
for f in blank otir chain paper any fill halt hook double fixed; do
  sjasmplus --nologo --msg=err --syntax=bFw --sym=$f.sym --lst=$f.lst $f.asm || exit 1
done
