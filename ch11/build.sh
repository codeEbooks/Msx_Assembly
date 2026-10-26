#!/bin/sh
# build.sh -- assemble the programs of chapter 11, with --syntax=bF (chapter 8).
# jrfar.asm is not a cartridge: it is assembled into a listing, jrfar.lst.
cd "$(dirname "$0")"
for f in map cmp cost loops table abs idioms bounce search; do
  sjasmplus --nologo --msg=err --syntax=bF --sym=$f.sym $f.asm || exit 1
done
sjasmplus --nologo --msg=err --syntax=bF --lst=jrfar.lst jrfar.asm || exit 1
