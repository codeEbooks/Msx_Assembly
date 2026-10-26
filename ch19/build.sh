#!/bin/sh
# build.sh -- assemble the programs of chapter 19, with --syntax=bFw (chapter 15)
cd "$(dirname "$0")"
for f in ports regs address readback status split fixed share whole bios; do
  sjasmplus --nologo --msg=err --syntax=bFw --sym=$f.sym --lst=$f.lst $f.asm || exit 1
done
