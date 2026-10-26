#!/bin/sh
# build.sh -- assemble the programs of chapter 39, with --syntax=bFw (chapter 15)
cd "$(dirname "$0")"
for f in walls corners ytop flags shapes meet blame; do
  sjasmplus --nologo --msg=err --syntax=bFw --sym=$f.sym --lst=$f.lst $f.asm || exit 1
done
