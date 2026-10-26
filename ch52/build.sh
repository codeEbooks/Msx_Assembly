#!/bin/sh
# build.sh -- assemble the programs of chapter 52, with --syntax=bFw (chapter 15)
cd "$(dirname "$0")"
for f in win tests sends moves patch inrom; do
  sjasmplus --nologo --msg=err --syntax=bFw --sym=$f.sym --lst=$f.lst $f.asm || exit 1
done
