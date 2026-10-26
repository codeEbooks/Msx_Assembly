#!/bin/sh
# build.sh -- assemble check.asm and edge.asm into their cartridges; case.asm
# is assembled by meas04.py only, to see what each assembler says about it
cd "$(dirname "$0")"
for f in check edge; do
  sjasmplus --nologo --msg=err --sym=$f.sym $f.asm || exit 1
done
