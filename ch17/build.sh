#!/bin/sh
# build.sh -- assemble the programs of chapter 17, with --syntax=bFw (chapter 15)
cd "$(dirname "$0")"
for f in modes bios timi clock saved unsaved late iff nokeys chain steal forgot; do
  sjasmplus --nologo --msg=err --syntax=bFw --sym=$f.sym --lst=$f.lst $f.asm || exit 1
done
