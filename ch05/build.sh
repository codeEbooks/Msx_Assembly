#!/bin/sh
# build.sh -- assemble the programs of chapter 5 into their cartridges; typo.asm
# and margin.asm do not assemble, and meas05.py records what sjasmplus says
cd "$(dirname "$0")"
for f in border ba noend wait split biosway; do
  sjasmplus --nologo --msg=err --sym=$f.sym $f.asm || exit 1
done
