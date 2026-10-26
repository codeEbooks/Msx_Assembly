#!/bin/sh
# build.sh -- assemble every program of chapter 2 into its .rom cartridge,
# and notation.asm into a listing
cd "$(dirname "$0")"
for f in *.asm; do
  [ "$f" = notation.asm ] && continue
  sjasmplus --nologo --msg=err --sym="${f%.asm}.sym" "$f" || exit 1
done
sjasmplus --nologo --msg=err --lst=notation.lst notation.asm || exit 1
