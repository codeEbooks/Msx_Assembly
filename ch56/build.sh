#!/bin/sh
# build.sh -- assemble the programs of chapter 56, with --syntax=bFw (chapter 15),
# and make the release's other files from the two cartridges (pack56.py)
cd "$(dirname "$0")"
for f in grin_alley lantern_keep label; do
  sjasmplus --nologo --msg=err --syntax=bFw --sym=$f.sym --lst=$f.lst $f.asm || exit 1
done
python3 pack56.py || exit 1
